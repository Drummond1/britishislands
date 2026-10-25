#!/usr/bin/env python3
"""Discover charted offshore rocks via OpenSeaMap ``seamark:name`` tags (D10).

The map_scanner Overpass query requires the generic ``name`` tag; many
OpenSeaMap rocks only carry ``seamark:name``. This harvester fills that gap.

Run::

    python3 scripts/discover_openseamap_rocks.py
    python3 scripts/discover_openseamap_rocks.py --no-cache
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = DATA / "cache_openseamap_rocks.json"
OUT = DATA / "discovery" / "candidates_openseamap_rocks.json"
REPORT = DATA / "discovery_openseamap_rocks_report.json"

sys.path.insert(0, str(ROOT / "scripts"))
from discovery import common as c  # noqa: E402


def _scan_query(bbox: tuple[float, float, float, float]) -> str:
    s, w, n, e = bbox
    return f"""
[out:json][timeout:300];
(
  node["seamark:type"="rock"]["seamark:name"]({s},{w},{n},{e});
  way["seamark:type"="rock"]["seamark:name"]({s},{w},{n},{e});
  relation["seamark:type"="rock"]["seamark:name"]({s},{w},{n},{e});
  node["natural"="rock"]["seamark:name"]({s},{w},{n},{e});
  way["natural"="rock"]["seamark:name"]({s},{w},{n},{e});
);
out tags center;
""".strip()


def _rock_name(tags: dict) -> str:
    for key in ("seamark:name", "name:en", "name", "official_name"):
        value = (tags.get(key) or "").strip()
        if value:
            return value
    return ""


def _normalize_element(el: dict) -> dict | None:
    tags = el.get("tags") or {}
    name = _rock_name(tags)
    if not name:
        return None
    center = c.element_center(el)
    if not center or not c.in_remit(*center):
        return None
    lat, lng = center
    if c.is_terrestrial_inland_rock(lat, lng, "rock"):
        return None
    return {
        "candidateId": f"osm-{el['type']}-{el['id']}",
        "name": name,
        "lat": round(lat, 5),
        "lng": round(lng, 5),
        "nation": c.nation_for(lat, lng),
        "featureKind": "rock",
        "osmType": el["type"],
        "osmId": el["id"],
        "osmPlace": "rock",
        "wikidata": tags.get("wikidata") or "",
        "wikipedia": tags.get("wikipedia") or "",
        "aliases": [],
        "tags": sorted(
            t
            for t in [
                tags.get("natural"),
                tags.get("seamark:type"),
                "seamark:name" if tags.get("seamark:name") else None,
            ]
            if t
        ),
        "scanConfidence": "low",
        "sourceHints": [
            {
                "name": "openstreetmap-openseamap",
                "url": f"https://www.openstreetmap.org/{el['type']}/{el['id']}",
                "license": "ODbL",
            }
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-cache", action="store_true", help="Refresh Overpass cache.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.no_cache and CACHE.exists():
        raw = c.load_json(CACHE, {})
        print(f"OpenSeaMap rocks: using cache ({CACHE.name})", flush=True)
    else:
        print("OpenSeaMap rocks: querying Overpass…", flush=True)
        raw = c.post_overpass(_scan_query(c.UK_BBOX))
        c.save_json(CACHE, raw)

    islands = c.load_islands()
    index = c.build_island_index(islands)
    elements = raw.get("elements") or []

    matched = 0
    out_of_remit = 0
    terrestrial = 0
    unnamed = 0
    candidates: list[dict[str, Any]] = []

    for el in elements:
        candidate = _normalize_element(el)
        if not candidate:
            unnamed += 1
            continue
        if candidate["nation"] == "British Isles":
            out_of_remit += 1
            continue
        if c.find_existing_match(candidate, index):
            matched += 1
            continue
        candidates.append(candidate)

    report = {
        "agent": "openseamap_rocks",
        "bbox": c.UK_BBOX,
        "islandsInDatabase": len(islands),
        "elementsScanned": len(elements),
        "alreadyInDatabase": matched,
        "outOfRemit": out_of_remit,
        "skippedTerrestrialRocks": terrestrial,
        "unnamedOrUnlocated": unnamed,
        "missingCandidates": len(candidates),
        "candidates": candidates,
    }

    print(
        f"OpenSeaMap rocks: {len(candidates)} gap candidates "
        f"({matched} matched, {len(elements)} scanned)",
        flush=True,
    )

    if not args.dry_run:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(candidates, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        slim = {k: v for k, v in report.items() if k != "candidates"}
        slim["candidateCount"] = len(candidates)
        REPORT.write_text(json.dumps(slim, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {OUT}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
