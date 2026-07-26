#!/usr/bin/env python3
"""
Build data/description_priority_queue.json — islands lacking shortDescription,
ordered for learner value (curated → featured → ferry → large area → Wikidata).

Used by enrich_descriptions_wikipedia.py --queue-file.

Run:
  python3 scripts/build_description_priority_queue.py
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
CURATED = DATA / "curated.json"
FERRIES = DATA / "ferries.json"
FEATURED = DATA / "featured_islands.json"
OUT = DATA / "description_priority_queue.json"


def has_description(island: dict) -> bool:
    return bool((island.get("shortDescription") or "").strip())


def has_wp_link(island: dict) -> bool:
    return bool(island.get("wikipedia") or island.get("wikidata"))


def curated_ids() -> set[str]:
    if not CURATED.is_file():
        return set()
    rows = json.loads(CURATED.read_text(encoding="utf-8"))
    return {r["id"] for r in rows if isinstance(r, dict) and r.get("id")}


def featured_ids() -> list[str]:
    if not FEATURED.is_file():
        return []
    data = json.loads(FEATURED.read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else data.get("rows") or data.get("islands") or []
    return [r["id"] for r in rows if isinstance(r, dict) and r.get("id")]


def ferry_island_ids(by_id: dict[str, dict]) -> set[str]:
    if not FERRIES.is_file():
        return set()
    data = json.loads(FERRIES.read_text(encoding="utf-8"))
    ids: set[str] = set()
    for route in data.get("routes") or []:
        terminals = route.get("terminals") or {}
        for key in ("from", "to"):
            iid = (terminals.get(key) or {}).get("islandId")
            if iid and iid in by_id:
                ids.add(iid)
    return ids


def tier(island: dict, curated: set[str], featured_rank: dict[str, int], ferry: set[str]) -> int:
    iid = island.get("id") or ""
    if island.get("wikipedia"):
        return -1
    if iid in curated:
        return 0
    if iid in featured_rank:
        return 1
    if iid in ferry:
        return 2
    area = island.get("areaKm2")
    if isinstance(area, (int, float)) and area >= 1.0:
        return 3
    wd = (island.get("wikidata") or "").strip()
    if re.match(r"^Q\d+$", wd):
        return 4
    return 5


def sort_key(island: dict, curated: set[str], featured_rank: dict[str, int], ferry: set[str]) -> tuple:
    iid = island.get("id") or ""
    t = tier(island, curated, featured_rank, ferry)
    feat = featured_rank.get(iid, 9999)
    area = island.get("areaKm2")
    area_sort = -(float(area) if isinstance(area, (int, float)) else 0.0)
    return (t, feat, area_sort, (island.get("name") or "").lower())


def main() -> int:
    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    by_id = {i["id"]: i for i in islands if i.get("id")}
    curated = curated_ids()
    ferry = ferry_island_ids(by_id)
    feat_list = featured_ids()
    featured_rank = {iid: n for n, iid in enumerate(feat_list)}

    pending = [
        i
        for i in islands
        if i.get("id")
        and not has_description(i)
        and has_wp_link(i)
        and "unnamed" not in (i.get("tags") or [])
    ]
    pending.sort(key=lambda i: sort_key(i, curated, featured_rank, ferry))
    queue_ids = [i["id"] for i in pending]

    payload = {
        "schemaVersion": 1,
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "totalWithoutDescription": len(queue_ids),
        "tierCounts": {
            "wikipediaUrl": sum(1 for i in pending if i.get("wikipedia")),
            "curated": sum(1 for i in pending if i.get("id") in curated),
            "featured": sum(
                1 for i in pending if i.get("id") in featured_rank and i.get("id") not in curated
            ),
            "ferry": sum(
                1
                for i in pending
                if i.get("id") in ferry and i.get("id") not in curated and i.get("id") not in featured_rank
            ),
        },
        "queue": queue_ids,
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT} ({len(queue_ids)} ids)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
