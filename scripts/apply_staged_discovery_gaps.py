#!/usr/bin/env python3
"""Verify staged discovery gap files and merge new islands into islands.json.

Inputs:
  data/discovery/candidates_geonames.json
  data/discovery/candidates_wikipedia_coords.json

Uses ``source_verifier._verify_one`` then ``enricher._to_island_record`` with
``site_update`` duplicate gates. Only **verified** rows with no atlas match are
appended (``classification.confidence=unconfirmed`` when ``needsReview``).

Run::

    python3 scripts/apply_staged_discovery_gaps.py
    python3 scripts/apply_staged_discovery_gaps.py --dry-run --limit 50
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
GEONAMES = DATA / "discovery" / "candidates_geonames.json"
WIKI = DATA / "discovery" / "candidates_wikipedia_coords.json"
REPORT = DATA / "discovery/staged_gaps_apply_report.json"

sys.path.insert(0, str(ROOT / "scripts"))
from discovery import common as c  # noqa: E402
from discovery import enricher as en  # noqa: E402
from discovery import source_verifier as sv  # noqa: E402
from discovery.site_update import _apply_unconfirmed_classification, _record_for_merge  # noqa: E402


def _load_gaps() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in (GEONAMES, WIKI):
        if not path.is_file():
            continue
        chunk = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(chunk, list):
            out.extend(chunk)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    candidates = _load_gaps()
    if args.limit:
        candidates = candidates[: args.limit]

    islands = c.load_islands()
    index = c.build_island_index(islands)
    start_count = len(islands)

    verified = 0
    rejected = 0
    skipped_match = 0
    skipped_dup = 0
    added_rows: list[dict] = []
    added_meta: list[dict] = []

    print(f"Discovery gaps: verifying {len(candidates):,} candidates", flush=True)
    for idx, cand in enumerate(candidates, start=1):
        row = sv._verify_one(cand)
        if not row.get("verified"):
            rejected += 1
            continue
        verified += 1
        merged = {**cand, **row}
        needs_review = en._needs_review(merged)
        match = c.find_existing_match(merged, index, loose=not needs_review)
        if match:
            skipped_match += 1
            continue

        record = en._to_island_record(merged)
        if needs_review:
            _apply_unconfirmed_classification(record, merged)
        record = _record_for_merge(record)

        dup = any(
            c.haversine_km(record["lat"], record["lng"], r["lat"], r["lng"]) <= c.PROXIMITY_KM
            and c.name_key(r["name"]) == c.name_key(record["name"])
            for r in added_rows
        )
        if dup:
            skipped_dup += 1
            continue

        added_rows.append(record)
        added_meta.append({"id": record["id"], "name": record["name"], "nation": record.get("nation")})
        index = c.build_island_index(islands + added_rows)

        if idx % 25 == 0:
            print(f"  {idx}/{len(candidates)} verified={verified} added={len(added_rows)}", flush=True)

    report = {
        "started": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "dryRun": args.dry_run,
        "input": len(candidates),
        "verified": verified,
        "rejected": rejected,
        "skippedExistingMatch": skipped_match,
        "skippedDuplicate": skipped_dup,
        "added": len(added_rows),
        "addedIslands": added_meta[:100],
    }

    if not args.dry_run and added_rows:
        backup = c.ISLANDS_PATH.with_name(
            f"islands.json.before-discovery-gaps-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        )
        backup.write_text(c.ISLANDS_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        islands.extend(added_rows)
        islands.sort(key=lambda r: (r.get("name") or "").lower())
        c.ISLANDS_PATH.write_text(json.dumps(islands, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report["backupPath"] = str(backup)
        report["finalIslandCount"] = len(islands)

    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"Discovery gaps: verified {verified}, added {len(added_rows)}, "
        f"rejected {rejected}, skipped match {skipped_match} "
        f"({start_count} → {start_count + len(added_rows) if not args.dry_run else start_count} islands)",
        flush=True,
    )
    print(f"Report → {REPORT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
