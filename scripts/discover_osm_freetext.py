#!/usr/bin/env python3
"""Discover candidate islands via OSM free-text / lexicon sweep (D5).

Scans ``data/osm_raw.json`` (and optionally a streamed subset of water_raw) for
name-bearing elements whose names match island lexicon but are absent from the
atlas within 1 km. Writes review candidates only — no islands.json write.

Also flags mistagged features (name looks like an island but place≠island).

Run::

    python3 scripts/discover_osm_freetext.py
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OSM_RAW = DATA / "osm_raw.json"
OUT = DATA / "discovery" / "candidates_osm_freetext.json"
REPORT = DATA / "discovery_osm_freetext_report.json"
MATCH_KM = 1.0

LEXICON_RE = re.compile(
    r"\b(island|isle|islets?|holms?|holm|skerries|skerry|stacks?|stack|"
    r"eilean|eileanan|inis|inish|ynys|inch|oile[aá]n|crannog|ait|eyot|"
    r"sgeir|stac|carrick|carraig)\b",
    re.I,
)
# Norse / toponymic suffixes common around NI / Hebrides
SUFFIX_RE = re.compile(r"(?:holm|skerry|ay|ey)$", re.I)

sys.path.insert(0, str(ROOT / "scripts"))
from discovery import common as c  # noqa: E402


def _element_coords(el: dict) -> tuple[float, float] | None:
    if "lat" in el and "lon" in el:
        return float(el["lat"]), float(el["lon"])
    center = el.get("center") or {}
    if "lat" in center and "lon" in center:
        return float(center["lat"]), float(center["lon"])
    return None


def _looks_island(name: str, tags: dict) -> bool:
    if not name or len(name) < 3:
        return False
    if LEXICON_RE.search(name) or SUFFIX_RE.search(name.replace(" ", "")):
        return True
    place = (tags.get("place") or "").lower()
    return place in {"island", "islet"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    islands = c.load_json(c.ISLANDS_PATH, [])
    index = c.build_island_index(islands)

    raw = c.load_json(OSM_RAW, {})
    elements = raw.get("elements") or []
    candidates: list[dict] = []
    seen_keys: set[str] = set()
    mistagged = 0

    print(f"OSM freetext: scanning {len(elements):,} osm_raw elements", flush=True)

    for el in elements:
        tags = el.get("tags") or {}
        name = (tags.get("name") or tags.get("name:en") or "").strip()
        if not _looks_island(name, tags):
            continue
        coords = _element_coords(el)
        if not coords:
            continue
        lat, lon = coords
        if not c.in_remit(lat, lon):
            continue
        place = (tags.get("place") or "").lower()
        natural = (tags.get("natural") or "").lower()
        is_proper_tag = place in {"island", "islet"} or natural in {"coastline"}
        if not is_proper_tag and LEXICON_RE.search(name):
            mistagged += 1

        # Dedup key
        osm_type = el.get("type") or "node"
        osm_id = el.get("id")
        key = f"{osm_type}-{osm_id}" if osm_id else f"{name.lower()}|{lat:.4f}|{lon:.4f}"
        if key in seen_keys:
            continue
        seen_keys.add(key)

        # Gap vs atlas
        probe = {
            "lat": lat,
            "lng": lon,
            "name": name,
            "osmType": osm_type,
            "osmId": osm_id,
            "wikidata": tags.get("wikidata") or "",
        }
        if c.find_existing_match(probe, index):
            continue

        nation = c.nation_for(lat, lon)
        candidates.append({
            "candidateId": f"osm-freetext-{key}",
            "name": name,
            "lat": round(lat, 5),
            "lng": round(lon, 5),
            "nation": nation,
            "featureKind": "island",
            "osmType": osm_type,
            "osmId": osm_id,
            "wikidata": tags.get("wikidata") or "",
            "wikipedia": tags.get("wikipedia") or "",
            "scanConfidence": "medium" if is_proper_tag else "low",
            "sourceHints": [{
                "name": "OpenStreetMap",
                "url": f"https://www.openstreetmap.org/{osm_type}/{osm_id}",
                "license": "ODbL",
            }],
            "tags": ["island", "osm-freetext"]
            + (["mistagged-candidate"] if not is_proper_tag else []),
            "osmTags": {
                k: tags[k]
                for k in ("place", "natural", "seamark:type", "name:gd", "name:ga", "name:cy")
                if tags.get(k)
            },
        })

    report = {
        "script": "discover_osm_freetext.py",
        "elementsScanned": len(elements),
        "lexiconHits": len(seen_keys),
        "mistaggedFlagged": mistagged,
        "candidates": len(candidates),
    }
    if not args.dry_run:
        c.save_json(OUT, candidates)
        c.save_json(REPORT, report)
    print(
        f"Wrote {len(candidates):,} gap candidates "
        f"({mistagged} mistagged-flagged) → {OUT}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
