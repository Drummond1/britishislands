#!/usr/bin/env python3
"""
Build a priority-ordered queue of atlas islands that lack a lead image.

Order (stable tiers, then name within tier):
  1. Hand-curated spine (data/curated.json ids)
  2. Ferry-linked (islandId on data/ferries.json routes)
  3. Larger area (areaKm2 descending)
  4. Wikidata Q-ID present

Writes data/image_priority_queue.json for enrich_images_v5.py --queue-file.

Run:
  python3 scripts/build_image_priority_queue.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
CURATED = DATA / "curated.json"
FERRIES = DATA / "ferries.json"
OUT = DATA / "image_priority_queue.json"


def has_image(island: dict) -> bool:
    if island.get("images"):
        return True
    return bool(island.get("image"))


def curated_ids() -> set[str]:
    if not CURATED.is_file():
        return set()
    rows = json.loads(CURATED.read_text(encoding="utf-8"))
    return {r["id"] for r in rows if isinstance(r, dict) and r.get("id")}


def ferry_island_ids(islands_by_id: dict[str, dict]) -> set[str]:
    if not FERRIES.is_file():
        return set()
    data = json.loads(FERRIES.read_text(encoding="utf-8"))
    ids: set[str] = set()
    for route in data.get("routes") or []:
        terminals = route.get("terminals") or {}
        for key in ("from", "to"):
            iid = (terminals.get(key) or {}).get("islandId")
            if iid and iid in islands_by_id:
                ids.add(iid)
    return ids


def tier(island: dict, curated: set[str], ferry: set[str]) -> int:
    iid = island.get("id") or ""
    if iid in curated:
        return 0
    if iid in ferry:
        return 1
    area = island.get("areaKm2")
    if isinstance(area, (int, float)) and area >= 1.0:
        return 2
    wd = (island.get("wikidata") or "").strip()
    if re.match(r"^Q\d+$", wd):
        return 3
    return 4


def sort_key(island: dict, curated: set[str], ferry: set[str]) -> tuple:
    t = tier(island, curated, ferry)
    area = island.get("areaKm2")
    area_sort = -(float(area) if isinstance(area, (int, float)) else 0.0)
    return (t, area_sort, (island.get("name") or "").lower())


def main() -> int:
    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    by_id = {i["id"]: i for i in islands if i.get("id")}
    curated = curated_ids()
    ferry = ferry_island_ids(by_id)
    pending = [i for i in islands if not has_image(i)]
    pending.sort(key=lambda i: sort_key(i, curated, ferry))
    queue_ids = [i["id"] for i in pending]
    payload = {
        "schemaVersion": 1,
        "generated": __import__("time").strftime("%Y-%m-%dT%H:%M:%S"),
        "totalWithoutImage": len(queue_ids),
        "tierCounts": {
            "curated": sum(1 for i in pending if (i.get("id") in curated)),
            "ferry": sum(
                1
                for i in pending
                if i.get("id") in ferry and i.get("id") not in curated
            ),
            "largeArea": sum(
                1
                for i in pending
                if tier(i, curated, ferry) == 2
            ),
            "wikidata": sum(1 for i in pending if tier(i, curated, ferry) == 3),
            "other": sum(1 for i in pending if tier(i, curated, ferry) >= 4),
        },
        "ids": queue_ids,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(queue_ids):,} ids → {OUT.relative_to(ROOT)}")
    print(f"  tiers: {payload['tierCounts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
