#!/usr/bin/env python3
"""
Remove non-curated atlas rows that are OSM *rocks* mis-tagged as marine
``type: sea`` but lie well inland (dry land), using the same geometry rule
as ``discovery.common.is_terrestrial_inland_rock``.

Does not delete ``source: curated`` entries. Coastal stacks and intertidal
rocks stay (they sit inside the coarse land polygon but within
``TERRESTRIAL_ROCK_MIN_INLAND_DEG`` of its boundary).

Usage:
  python3 scripts/prune_terrestrial_rocks.py
  python3 scripts/prune_terrestrial_rocks.py --apply
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS_PATH = DATA / "islands.json"
CURATED_PATH = DATA / "curated.json"
REPORT_PATH = DATA / "terrestrial_rocks_prune_report.json"

sys.path.insert(0, str(ROOT / "scripts"))
from discovery import common as c  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Write islands.json (default is report-only, no mutation)",
    )
    args = ap.parse_args()

    islands = c.load_islands()
    curated_ids = {x["id"] for x in c.load_json(CURATED_PATH, []) if x.get("id")}

    removed: list[dict] = []
    keep: list[dict] = []
    for isl in islands:
        iid = isl.get("id")
        if isl.get("osmPlace") != "rock" or isl.get("type") != "sea":
            keep.append(isl)
            continue
        if isl.get("source") == "curated" or iid in curated_ids:
            keep.append(isl)
            continue
        if not c.is_terrestrial_inland_rock(
            float(isl["lat"]), float(isl["lng"]), "rock"
        ):
            keep.append(isl)
            continue
        removed.append(
            {
                "id": iid,
                "name": isl.get("name"),
                "lat": isl.get("lat"),
                "lng": isl.get("lng"),
                "osmType": isl.get("osmType"),
                "osmId": isl.get("osmId"),
            }
        )

    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = {
        "prunedAt": ts,
        "rule": (
            "osmPlace==rock AND type==sea AND NOT curated AND "
            "is_terrestrial_inland_rock() "
            f"(min inland deg {c.TERRESTRIAL_ROCK_MIN_INLAND_DEG})"
        ),
        "previousCount": len(islands),
        "newCount": len(keep),
        "removedCount": len(removed),
        "removed": removed,
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"→ {REPORT_PATH.relative_to(ROOT)}", file=sys.stderr)
    print(
        f"Prune plan: remove {len(removed)} / {len(islands)} "
        "terrestrial misclassified rocks (see report).",
        file=sys.stderr,
    )

    if not args.apply:
        print("Dry-run only — pass --apply to mutate islands.json.", file=sys.stderr)
        return 0

    ts_fn = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = DATA / f"islands.json.before-terrestrial-rock-prune-{ts_fn}.bak"
    shutil.copy2(ISLANDS_PATH, backup)
    print(f"→ backup {backup.name}", file=sys.stderr)
    ISLANDS_PATH.write_text(
        json.dumps(keep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
