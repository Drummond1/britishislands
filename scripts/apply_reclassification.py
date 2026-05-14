#!/usr/bin/env python3
"""
Apply the reclassification proposal at ``data/reclassification_proposal.json``
to ``data/islands.json``.

Strict safety guarantees:

  1. Refuses to run if ``data/islands.json`` doesn't parse as a JSON list.
  2. Writes a timestamped backup ``data/islands.json.before-reclass`` first.
  3. Only mutates islands listed in the proposal.
  4. Uses atomic write (tmp + rename).
  5. Read-back sanity check before exiting.

Flags:
  --dry-run        Show what would change; don't write anything.
  --confidence X   Only apply changes with confidence >= X (high|medium|low).
                   Default: medium.
  --types T,T,…    Only apply transitions producing one of these AFTER types.
  --max N          Apply at most N changes (useful for incremental rollout).
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
PROPOSAL_PATH = DATA / "reclassification_proposal.json"
BACKUP_PATH = DATA / "islands.json.before-reclass"

CONFIDENCE_ORDER = {"high": 3, "medium": 2, "low": 1}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--confidence",
        choices=("high", "medium", "low"),
        default="medium",
        help="Apply changes with confidence >= this threshold (default: medium)",
    )
    parser.add_argument(
        "--types",
        help="Comma-separated AFTER types to allow (e.g. 'lake,river' = only inland-promoting changes)",
    )
    parser.add_argument("--max", type=int, default=None)
    args = parser.parse_args()

    if not PROPOSAL_PATH.exists():
        print(f"FATAL: proposal not found at {PROPOSAL_PATH}", file=sys.stderr)
        return 2
    if not ISLANDS_PATH.exists():
        print(f"FATAL: islands.json not found", file=sys.stderr)
        return 2

    islands = json.loads(ISLANDS_PATH.read_text(encoding="utf-8"))
    if not isinstance(islands, list):
        print("FATAL: islands.json is not a JSON array", file=sys.stderr)
        return 2
    by_id = {i["id"]: i for i in islands if "id" in i}
    print(f"Loaded {len(islands):,} islands ({len(by_id):,} keyed by id)")

    proposals = json.loads(PROPOSAL_PATH.read_text(encoding="utf-8"))
    if not isinstance(proposals, list):
        print("FATAL: proposal is not a JSON array", file=sys.stderr)
        return 2
    print(f"Loaded {len(proposals):,} proposed changes")

    allowed_types = set((args.types or "").split(",")) if args.types else None
    if allowed_types and "" in allowed_types:
        allowed_types.discard("")
    min_conf = CONFIDENCE_ORDER[args.confidence]

    changes: list[dict] = []
    skipped_low_conf = 0
    skipped_type = 0
    skipped_missing = 0
    transitions: Counter = Counter()

    for p in proposals:
        iid = p.get("id")
        if not iid or iid not in by_id:
            skipped_missing += 1
            continue
        conf = (p.get("after") or {}).get("classification", {}).get("confidence") or "low"
        if CONFIDENCE_ORDER.get(conf, 0) < min_conf:
            skipped_low_conf += 1
            continue
        after_type = (p.get("after") or {}).get("type")
        if allowed_types is not None and after_type not in allowed_types:
            skipped_type += 1
            continue
        changes.append(p)
        if args.max and len(changes) >= args.max:
            break

    print(f"  {len(changes):,} eligible changes "
          f"(skipped: low-confidence {skipped_low_conf}, "
          f"out-of-type {skipped_type}, missing-id {skipped_missing})")

    if not changes:
        print("Nothing to apply.")
        return 0

    # Compute the transitions table.
    for p in changes:
        b = (p.get("before") or {}).get("type", "?")
        a = (p.get("after") or {}).get("type", "?")
        transitions[(b, a)] += 1

    print("\nTransitions to be applied:")
    for (b, a), n in sorted(transitions.items(), key=lambda x: -x[1]):
        print(f"  {b:10s} → {a:10s}   {n:>5}")

    if args.dry_run:
        print("\n--dry-run: no files were written.")
        return 0

    # Backup the original.
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    archive = DATA / f"islands.json.before-reclass-{ts}"
    shutil.copy2(ISLANDS_PATH, archive)
    if not BACKUP_PATH.exists():
        shutil.copy2(ISLANDS_PATH, BACKUP_PATH)
    print(f"\nBackup written → {archive.name}")

    # Apply.
    for p in changes:
        iid = p["id"]
        isl = by_id[iid]
        after = p["after"]
        isl["type"] = after["type"]
        if after.get("subtype"):
            isl["subtype"] = after["subtype"]
        elif "subtype" in isl and isl["subtype"] is None:
            isl.pop("subtype", None)
        if after.get("parentWaterBody"):
            isl["parentWaterBody"] = after["parentWaterBody"]
        elif after.get("type") == "sea":
            # Drop a stale inland parentWaterBody when we re-confirm sea.
            isl.pop("parentWaterBody", None)
        isl["classification"] = after["classification"]

    # Atomic write.
    tmp = ISLANDS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(islands, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, ISLANDS_PATH)

    # Read-back sanity.
    reread = json.loads(ISLANDS_PATH.read_text(encoding="utf-8"))
    print(f"\nWrote {len(reread):,} islands to {ISLANDS_PATH.name}")
    type_counts = Counter(i.get("type") for i in reread)
    print(f"  by type now: {dict(type_counts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
