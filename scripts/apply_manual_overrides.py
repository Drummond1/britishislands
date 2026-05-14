#!/usr/bin/env python3
"""
Apply hand-curated overrides from ``data/manual_overrides.json`` to
``data/islands.json``.

Designed for cases where the automatic reclassification pipeline picks
the wrong inland body (e.g. Tier 4 proximity assigning a low-confidence
unnamed pool when the island is really on a named river the OSM water
data doesn't polygonise well).

Each override object **must** have:
    id, name, type, classification.source, classification.confidence

Optional:
    subtype, parentWaterBody, note

The script writes a timestamped backup and verifies the read-back
before exiting.  Pass ``--dry-run`` to inspect without writing.

Run:
    python3 scripts/apply_manual_overrides.py --dry-run
    python3 scripts/apply_manual_overrides.py
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS_PATH = DATA / "islands.json"
OVERRIDES_PATH = DATA / "manual_overrides.json"
ALLOWED_TYPES = {"sea", "lake", "river", "unknown"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not OVERRIDES_PATH.exists():
        print(f"FATAL: overrides not found at {OVERRIDES_PATH}", file=sys.stderr)
        return 2
    if not ISLANDS_PATH.exists():
        print(f"FATAL: islands.json not found", file=sys.stderr)
        return 2

    islands = json.loads(ISLANDS_PATH.read_text(encoding="utf-8"))
    if not isinstance(islands, list):
        print("FATAL: islands.json is not a JSON array", file=sys.stderr)
        return 2
    by_id = {i["id"]: i for i in islands if "id" in i}
    print(f"Loaded {len(islands):,} islands")

    payload = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    overrides = payload.get("overrides") or []
    print(f"Loaded {len(overrides):,} manual overrides "
          f"(version {payload.get('version','?')})")

    applied: list[dict] = []
    skipped_missing = 0
    skipped_invalid = 0
    transitions: Counter = Counter()

    for o in overrides:
        iid = o.get("id")
        if not iid or iid not in by_id:
            print(f"  WARN: id not in dataset: {iid} ({o.get('name','?')})", file=sys.stderr)
            skipped_missing += 1
            continue
        t = o.get("type")
        if t not in ALLOWED_TYPES:
            print(f"  WARN: invalid type '{t}' for {iid}", file=sys.stderr)
            skipped_invalid += 1
            continue
        cls = o.get("classification") or {}
        if not cls.get("source") or not cls.get("confidence"):
            print(f"  WARN: missing classification.source/confidence for {iid}", file=sys.stderr)
            skipped_invalid += 1
            continue
        applied.append(o)
        isl = by_id[iid]
        before = isl.get("type", "?")
        transitions[(before, t)] += 1

    print(f"  {len(applied):,} overrides eligible "
          f"(skipped: missing-id {skipped_missing}, invalid {skipped_invalid})")
    if not applied:
        return 0

    print("\nTransitions:")
    for (b, a), n in sorted(transitions.items(), key=lambda x: -x[1]):
        print(f"  {b:8s} → {a:8s}   {n:>4}")

    if args.dry_run:
        print("\n--dry-run: no files were written.")
        return 0

    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    archive = DATA / f"islands.json.before-overrides-{ts}"
    shutil.copy2(ISLANDS_PATH, archive)
    print(f"\nBackup written → {archive.name}")

    for o in applied:
        isl = by_id[o["id"]]
        isl["type"] = o["type"]
        if "subtype" in o:
            if o["subtype"]:
                isl["subtype"] = o["subtype"]
            elif "subtype" in isl:
                isl.pop("subtype", None)
        if "parentWaterBody" in o:
            if o["parentWaterBody"]:
                isl["parentWaterBody"] = o["parentWaterBody"]
            else:
                isl.pop("parentWaterBody", None)
        isl["classification"] = o["classification"]
        if o.get("note"):
            # Persist the note in a stable field so the audit trail
            # survives in islands.json itself.
            isl["classificationNote"] = o["note"]

    tmp = ISLANDS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(islands, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, ISLANDS_PATH)

    reread = json.loads(ISLANDS_PATH.read_text(encoding="utf-8"))
    print(f"\nWrote {len(reread):,} islands to {ISLANDS_PATH.name}")
    type_counts = Counter(i.get("type") for i in reread)
    print(f"  by type now: {dict(type_counts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
