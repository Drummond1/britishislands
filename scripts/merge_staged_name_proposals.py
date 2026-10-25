#!/usr/bin/env python3
"""Merge verified name proposals into islands.json (unnamed islands only).

Reads ``data/staging/name_proposals-verified/*.json``. Never overwrites curated
islands or islands that already have a real name.

Run after ``verify_staged_names.py``::

    python3 scripts/merge_staged_name_proposals.py
    python3 scripts/merge_staged_name_proposals.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
VERIFIED = DATA / "staging" / "name_proposals-verified"
REPORT = DATA / "staged_names_merge_report.json"

CONFIDENCE_RANK = {"high": 4, "medium-high": 3, "medium": 2, "low": 1}


def _atomic_write(path: Path, payload: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _score(row: dict) -> int:
    conf = CONFIDENCE_RANK.get((row.get("nameConfidence") or "").lower(), 0)
    return conf * 10 + int(row.get("verifyScore") or 0)


def _load_verified() -> list[dict]:
    rows: list[dict] = []
    for path in sorted(VERIFIED.glob("*.json")):
        try:
            chunk = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(chunk, list):
            for row in chunk:
                row = dict(row)
                row["_file"] = path.name
                rows.append(row)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-backup", action="store_true")
    args = ap.parse_args()

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    by_id = {i["id"]: i for i in islands}

    candidates = _load_verified()
    best: dict[str, dict] = {}
    for row in candidates:
        iid = row.get("id") or row.get("islandId")
        if not iid:
            continue
        prev = best.get(iid)
        if prev is None or _score(row) > _score(prev):
            best[iid] = row

    unnamed_before = sum(
        1 for i in islands
        if i.get("nameStatus") == "unknown"
        or (i.get("name") or "").strip().lower() == "unnamed island"
    )

    merged = 0
    skipped_named = 0
    skipped_curated = 0
    skipped_missing = 0
    by_source: dict[str, int] = {}

    for iid, row in best.items():
        isl = by_id.get(iid)
        if not isl:
            skipped_missing += 1
            continue
        if isl.get("source") == "curated":
            skipped_curated += 1
            continue
        if isl.get("nameStatus") != "unknown":
            skipped_named += 1
            continue

        new_name = (row.get("proposedName") or "").strip()
        if not new_name:
            continue

        if args.dry_run:
            merged += 1
            src = row.get("source") or "unknown"
            by_source[src] = by_source.get(src, 0) + 1
            continue

        isl["name"] = new_name
        isl.pop("nameStatus", None)
        tags = list(isl.get("tags") or [])
        for t in ("unnamed", "needs-name"):
            if t in tags:
                tags.remove(t)
        if "named-via-staging" not in tags:
            tags.append("named-via-staging")
        isl["tags"] = tags

        alts = row.get("alternateNames") or {}
        if alts:
            names = dict(isl.get("names") or {})
            for lang, val in alts.items():
                if val and lang not in names:
                    names[lang] = val
            if names:
                isl["names"] = names

        isl["nameProvenance"] = {
            "source": row.get("source"),
            "licence": row.get("licence"),
            "url": row.get("sourcePageUrl"),
            "sourceRef": row.get("sourceRef"),
            "retrievedAt": row.get("retrievedAt"),
            "confidenceTier": row.get("confidenceTier"),
            "nameConfidence": row.get("nameConfidence"),
            "distanceM": row.get("distanceM"),
            "dualSource": row.get("dualSource", False),
            "mergedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
        if row.get("wikidata") or (row.get("extra") or {}).get("wikidata"):
            isl["wikidata"] = row.get("wikidata") or (row.get("extra") or {}).get("wikidata")

        merged += 1
        src = row.get("source") or "unknown"
        by_source[src] = by_source.get(src, 0) + 1
        print(f"  ✓ {iid} → {new_name} ({src})", flush=True)

    unnamed_after = sum(
        1 for i in islands
        if i.get("nameStatus") == "unknown"
        or (i.get("name") or "").strip().lower() == "unnamed island"
    )

    if not args.dry_run and merged:
        if not args.no_backup:
            stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
            backup = DATA / f"islands.json.before-name-merge-{stamp}.bak"
            shutil.copy2(ISLANDS, backup)
            print(f"Backup → {backup.name}", flush=True)
        _atomic_write(ISLANDS, islands)

    report = {
        "dryRun": args.dry_run,
        "candidates": len(candidates),
        "uniqueIslands": len(best),
        "merged": merged,
        "skippedNamed": skipped_named,
        "skippedCurated": skipped_curated,
        "skippedMissing": skipped_missing,
        "unnamedBefore": unnamed_before,
        "unnamedAfter": unnamed_after if not args.dry_run else unnamed_before,
        "bySource": by_source,
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"Merged: {merged}; unnamed "
        f"{report['unnamedBefore']} → {report['unnamedAfter']}",
        flush=True,
    )
    print(f"Report → {REPORT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
