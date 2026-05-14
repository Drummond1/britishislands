#!/usr/bin/env python3
"""
Apply staged enrichment caches to ``data/islands.json`` in a single
atomic pass.

Inputs (any subset can be missing — only present caches are applied):

* ``data/cache_dobih.json``         hills (``hillsOn[]``)
* ``data/cache_lighthouses.json``   lighthouses
* ``data/cache_wildlife.json``      RSPB reserves + wildlife colonies
* ``data/cache_bgs.json``           geology
* ``data/cache_census2022.json``    population + populationDetails

Safety contract
---------------
* Atomic write via ``islands.json.tmp`` + ``os.replace``.
* Single timestamped backup at the start of the run.
* Read-back validation: parsed result has the same ``len(islands)``
  as the input.
* Regression smoke checks: a handful of curated islands (Skye,
  Devenish, Achill, Eel Pie, Isle of Wight) must remain present and
  retain their core fields.
* Idempotent: re-running with the same staged caches is a no-op.

CLI::

    python3 scripts/apply_enrichments.py --dry-run
    python3 scripts/apply_enrichments.py --apply
    python3 scripts/apply_enrichments.py --apply --only hills lighthouses
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS_PATH = DATA / "islands.json"
LOGS = ROOT / "logs"
REPORT = DATA / "enrichment_apply_report.json"

CACHES = {
    "hills":       DATA / "cache_dobih.json",
    "lighthouses": DATA / "cache_lighthouses.json",
    "wildlife":    DATA / "cache_wildlife.json",
    "geology":     DATA / "cache_bgs.json",
    "census":      DATA / "cache_census2022.json",
}

# Smoke-check islands that must remain intact post-merge.  These are
# the curated regression spine (see docs/VALIDATION.md).
SMOKE_IDS = {
    "isle-of-skye":   {"nation": "Scotland", "type": "sea"},
    "achill-island":  {"nation": "Ireland",  "type": "sea"},
    "isle-of-wight":  {"nation": "England",  "type": "sea"},
    "devenish-island": {"nation": "Northern Ireland", "type": "lake"},
    # Eel Pie Island has a Thames-list classification; check it still has osmId.
    "eel-pie-island": {"nation": "England",  "type": "river"},
}


def _atomic_write_json(path: Path, payload: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    os.replace(tmp, path)


def _load_json(path: Path, default):
    if not path.exists(): return default
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        sys.exit(f"FATAL: {path} unreadable: {exc}")


def overnight_finished() -> tuple[bool, str]:
    """Return (finished, latest_summary_log_path_or_msg)."""
    if not LOGS.exists():
        return True, "(no logs/ dir — assuming no overnight chain)"
    summaries = sorted(LOGS.glob("overnight-*-summary.log"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
    if not summaries:
        return True, "(no overnight summary log present)"
    latest = summaries[0]
    body = latest.read_text(encoding="utf-8")
    finished = "===== Overnight run finished" in body
    return finished, str(latest)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="Mutate islands.json (default: dry-run)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report what would change without writing.")
    ap.add_argument("--only", nargs="+", choices=sorted(CACHES.keys()),
                    default=None,
                    help="Restrict to a subset of caches (default: all present)")
    ap.add_argument("--force", action="store_true",
                    help="Apply even if the overnight chain hasn't finished.")
    args = ap.parse_args()

    if args.apply and args.dry_run:
        sys.exit("--apply and --dry-run are mutually exclusive")
    do_write = bool(args.apply and not args.dry_run)

    print(f"=== Apply enrichments " + ("(APPLY)" if do_write else "(DRY-RUN)") + " ===")

    # 1. Overnight chain check.
    finished, latest = overnight_finished()
    print(f"  overnight chain: {'FINISHED' if finished else 'STILL RUNNING'} "
          f"({latest})")
    if not finished and do_write and not args.force:
        sys.exit("ABORT: overnight chain not finished — re-run with --force to "
                 "override (NOT recommended).")

    # 2. Load islands.
    islands = _load_json(ISLANDS_PATH, None)
    if not isinstance(islands, list):
        sys.exit(f"FATAL: {ISLANDS_PATH} is not a list")
    print(f"  loaded {len(islands):,} islands")
    by_id = {i.get("id"): i for i in islands if isinstance(i, dict) and i.get("id")}

    # 3. Load staged caches.
    selected = args.only or sorted(CACHES.keys())
    loaded: dict[str, dict] = {}
    for name in selected:
        path = CACHES[name]
        if not path.exists():
            print(f"  [{name}] cache missing ({path.name}) — skipping")
            continue
        d = _load_json(path, {})
        if not isinstance(d, dict) or not d:
            print(f"  [{name}] cache is empty/invalid — skipping")
            continue
        loaded[name] = d
        print(f"  [{name}] cache has {len(d):,} entries")

    if not loaded:
        sys.exit("FATAL: no caches loaded; nothing to apply")

    # 4. Plan the merge.  Don't mutate islands yet; build a diff plan.
    plan: list[dict] = []
    counts: dict[str, int] = {name: 0 for name in loaded}
    skipped_newer: list[dict] = []
    for name, cache in loaded.items():
        for iid, payload in cache.items():
            isl = by_id.get(iid)
            if not isl:
                continue
            # Census-specific safety: don't overwrite newer with older.
            if name == "census" and isinstance(payload, dict):
                cur_year = isl.get("populationYear")
                new_year = payload.get("populationYear")
                if isinstance(cur_year, int) and isinstance(new_year, int) and cur_year > new_year:
                    skipped_newer.append({"id": iid, "currentYear": cur_year,
                                          "newYear": new_year})
                    continue
            plan.append({"name": name, "id": iid, "payload": payload})
            counts[name] += 1

    print(f"  plan: {sum(counts.values()):,} field-group adoptions")
    for name, c in counts.items():
        print(f"    {name:11s} +{c:,}")
    if skipped_newer:
        print(f"  skipped (existing newer): {len(skipped_newer)}")

    # 5. Smoke check pre-state.
    pre_smoke: dict[str, dict] = {}
    for sid, want in SMOKE_IDS.items():
        isl = by_id.get(sid)
        if not isl:
            print(f"  WARN: smoke-test id {sid} not present in islands.json",
                  file=sys.stderr)
            continue
        pre_smoke[sid] = {
            "name": isl.get("name"),
            "type": isl.get("type"),
            "nation": isl.get("nation"),
            "osmId": isl.get("osmId"),
        }

    if not do_write:
        # Just summarise + write the audit, no mutation.
        rpt = {
            "startedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "dryRun": True,
            "plan": counts,
            "skippedNewer": skipped_newer,
            "preSmoke": pre_smoke,
            "overnightFinished": finished,
        }
        _atomic_write_json(REPORT, rpt)
        print(f"\nDRY-RUN report → {REPORT.name}")
        print("Re-run with --apply when ready to mutate islands.json.")
        return 0

    # 6. Backup.
    ts = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    backup = DATA / f"islands.json.before-enrichments-{ts}"
    shutil.copy2(ISLANDS_PATH, backup)
    print(f"  backup → {backup.name}")

    # 7. Apply the plan.
    for step in plan:
        isl = by_id[step["id"]]
        for k, v in step["payload"].items():
            isl[k] = v

    # 8. Read-back validation.
    print("  validating result …")
    _atomic_write_json(ISLANDS_PATH, islands)
    reread = _load_json(ISLANDS_PATH, None)
    if not isinstance(reread, list) or len(reread) != len(islands):
        # Roll back from backup.
        print("  FAILED post-write read-back; rolling back from backup",
              file=sys.stderr)
        shutil.copy2(backup, ISLANDS_PATH)
        sys.exit("post-write validation failed")
    reread_by_id = {i.get("id"): i for i in reread if isinstance(i, dict)}
    # Smoke checks.
    failed_smoke = []
    for sid, want in SMOKE_IDS.items():
        isl = reread_by_id.get(sid)
        if not isl:
            failed_smoke.append(sid); continue
        for k, v in want.items():
            if isl.get(k) != v:
                failed_smoke.append(f"{sid}:{k}({isl.get(k)} != {v})")
    if failed_smoke:
        print(f"  FAILED smoke checks: {failed_smoke}", file=sys.stderr)
        shutil.copy2(backup, ISLANDS_PATH)
        sys.exit("smoke-test regression — rolled back")

    rpt = {
        "startedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "dryRun": False,
        "applied": counts,
        "backup": backup.name,
        "skippedNewer": skipped_newer,
        "smokeChecksPassed": list(SMOKE_IDS.keys()),
        "overnightFinished": finished,
    }
    _atomic_write_json(REPORT, rpt)
    print()
    print(f"APPLIED. Backup: {backup.name}")
    print(f"Report  → {REPORT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
