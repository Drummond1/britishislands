#!/usr/bin/env python3
"""
Build data/featured_islands.json — editorial "notable" picks for the UI strip.

Starts from curated.json, then scores islands.json rows (photo, ferry, area,
shortDescription, curated source) up to --limit (default 120).

Run after islands.json changes:
  python3 scripts/build_featured_islands.py
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
CURATED = DATA / "curated.json"
FERRIES = DATA / "ferries.json"
OUT = DATA / "featured_islands.json"


def has_photo(island: dict) -> bool:
    return bool(island.get("images")) or bool(island.get("image"))


def lead_thumb(island: dict) -> str | None:
    images = island.get("images")
    if isinstance(images, list) and images:
        return images[0].get("url") or images[0].get("fullUrl")
    return island.get("image")


def ferry_ids(by_id: dict[str, dict]) -> set[str]:
    if not FERRIES.is_file():
        return set()
    data = json.loads(FERRIES.read_text(encoding="utf-8"))
    out: set[str] = set()
    for route in data.get("routes") or []:
        for key in ("from", "to"):
            iid = ((route.get("terminals") or {}).get(key) or {}).get("islandId")
            if iid and iid in by_id:
                out.add(iid)
    return out


def score(island: dict, curated_set: set[str], ferry_set: set[str]) -> float:
    iid = island.get("id") or ""
    s = 0.0
    if iid in curated_set:
        s += 1000
    if island.get("source") == "curated":
        s += 400
    if island.get("shortDescription"):
        s += 250
    if has_photo(island):
        s += 200
    if iid in ferry_set:
        s += 120
    area = island.get("areaKm2")
    if isinstance(area, (int, float)):
        s += min(80, float(area) * 0.05)
    if re.match(r"^Q\d+$", (island.get("wikidata") or "").strip()):
        s += 30
    if island.get("type") == "sea":
        s += 15
    return s


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=120, help="Max featured rows")
    args = p.parse_args()

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    by_id = {i["id"]: i for i in islands if i.get("id")}
    curated_rows = json.loads(CURATED.read_text(encoding="utf-8")) if CURATED.is_file() else []
    curated_set = {r["id"] for r in curated_rows if isinstance(r, dict) and r.get("id")}
    ferry_set = ferry_ids(by_id)

    # Merge curated prose into atlas rows when present.
    curated_by_id = {r["id"]: r for r in curated_rows if isinstance(r, dict) and r.get("id")}

    ordered_ids: list[str] = []
    seen: set[str] = set()
    seen_names: set[str] = set()

    for cid in curated_rows:
        if not isinstance(cid, dict):
            continue
        iid = cid.get("id")
        if not iid or iid not in by_id or iid in seen:
            continue
        name_key = (by_id[iid].get("name") or "").strip().lower()
        if name_key and name_key in seen_names:
            continue
        if name_key:
            seen_names.add(name_key)
        ordered_ids.append(iid)
        seen.add(iid)

    ranked = sorted(
        [i for i in islands if i.get("id") and i["id"] not in seen],
        key=lambda i: (-score(i, curated_set, ferry_set), (i.get("name") or "").lower()),
    )
    for i in ranked:
        if len(ordered_ids) >= args.limit:
            break
        name_key = (i.get("name") or "").strip().lower()
        if name_key and name_key in seen_names:
            continue
        if name_key:
            seen_names.add(name_key)
        ordered_ids.append(i["id"])
        seen.add(i["id"])

    featured = []
    for iid in ordered_ids:
        isl = by_id[iid]
        cur = curated_by_id.get(iid) or {}
        blurb = (isl.get("shortDescription") or cur.get("shortDescription") or "").strip()
        if not blurb and has_photo(isl):
            blurb = f"{isl.get('nation', '')} · {isl.get('type', 'island')}".strip(" ·")
        featured.append(
            {
                "id": iid,
                "name": isl.get("name") or iid,
                "nation": isl.get("nation"),
                "type": isl.get("type"),
                "lat": isl.get("lat"),
                "lng": isl.get("lng"),
                "shortDescription": blurb[:280] if blurb else "",
                "thumbUrl": lead_thumb(isl),
                "hasPhoto": has_photo(isl),
                "ferry": iid in ferry_set,
                "tier": "curated" if iid in curated_set else "atlas",
            }
        )

    payload = {
        "schemaVersion": 1,
        "about": "Editorial notable islands for the home sidebar strip; regenerate via scripts/build_featured_islands.py",
        "limit": args.limit,
        "count": len(featured),
        "islands": featured,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with_photo = sum(1 for f in featured if f.get("hasPhoto"))
    print(f"Wrote {len(featured)} featured islands ({with_photo} with photo) → {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
