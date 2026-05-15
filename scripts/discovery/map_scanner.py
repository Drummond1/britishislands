"""Map Scanner Agent — coastline / OSM scan for missing landmasses."""

from __future__ import annotations

import sys
from typing import Any

from . import common as c


def _scan_query(bbox: tuple[float, float, float, float]) -> str:
    s, w, n, e = bbox
    return f"""
[out:json][timeout:300];
(
  node["place"~"^(island|islet)$"]["name"]({s},{w},{n},{e});
  way["place"~"^(island|islet)$"]["name"]({s},{w},{n},{e});
  relation["place"~"^(island|islet)$"]["name"]({s},{w},{n},{e});
  node["natural"="rock"]["name"]({s},{w},{n},{e});
  way["natural"="rock"]["name"]({s},{w},{n},{e});
  relation["natural"="rock"]["name"]({s},{w},{n},{e});
  node["seamark:type"="rock"]["name"]({s},{w},{n},{e});
  way["seamark:type"="rock"]["name"]({s},{w},{n},{e});
  relation["seamark:type"="rock"]["name"]({s},{w},{n},{e});
);
out tags center;
""".strip()


def _feature_kind(tags: dict) -> str:
    place = (tags.get("place") or "").lower()
    if place in {"island", "islet"}:
        return place
    if tags.get("natural") == "rock" or tags.get("seamark:type") == "rock":
        return "rock"
    return "offshore"


def _confidence(tags: dict, kind: str) -> str:
    if tags.get("wikidata") or tags.get("wikipedia"):
        return "high"
    if kind in {"island", "islet"} and tags.get("name"):
        return "medium"
    if kind == "rock" and tags.get("name"):
        return "low"
    return "low"


def _normalize_element(el: dict) -> dict | None:
    tags = el.get("tags") or {}
    name = c.display_name(tags)
    if not name:
        return None
    center = c.element_center(el)
    if not center or not c.in_remit(*center):
        return None
    lat, lng = center
    kind = _feature_kind(tags)
    wikipedia = tags.get("wikipedia") or ""
    if wikipedia and ":" in wikipedia and not wikipedia.startswith("http"):
        lang, title = wikipedia.split(":", 1)
        wikipedia = f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}"
    return {
        "candidateId": f"osm-{el['type']}-{el['id']}",
        "name": name,
        "lat": round(lat, 5),
        "lng": round(lng, 5),
        "nation": c.nation_for(lat, lng),
        "featureKind": kind,
        "osmType": el["type"],
        "osmId": el["id"],
        "osmPlace": tags.get("place") or kind,
        "wikidata": tags.get("wikidata") or "",
        "wikipedia": wikipedia if wikipedia.startswith("http") else "",
        "aliases": [v for k, v in tags.items() if k.startswith("name:") and v and k != "name:en"],
        "tags": sorted({t for t in [tags.get("place"), tags.get("natural"), tags.get("seamark:type")] if t}),
        "scanConfidence": _confidence(tags, kind),
        "sourceHints": [
            {
                "name": "openstreetmap",
                "url": f"https://www.openstreetmap.org/{el['type']}/{el['id']}",
                "license": "ODbL",
            }
        ],
    }


def run(*, use_cache: bool = True, limit: int | None = None) -> dict[str, Any]:
    islands = c.load_islands()
    index = c.build_island_index(islands)
    if use_cache and c.CACHE_OSM.exists():
        raw = c.load_json(c.CACHE_OSM, {})
    else:
        print("→ Map Scanner: querying Overpass", file=sys.stderr)
        try:
            raw = c.post_overpass(_scan_query(c.UK_BBOX))
            c.save_json(c.CACHE_OSM, raw)
        except RuntimeError as exc:
            fallback = c.DATA / "osm_raw.json"
            if fallback.exists():
                print(
                    f"Map Scanner: Overpass unavailable ({exc}); using {fallback.name}",
                    file=sys.stderr,
                )
                raw = c.load_json(fallback, {})
            else:
                raise

    missing: list[dict] = []
    matched = 0
    out_of_remit = 0
    unnamed = 0
    skipped_terrestrial_rocks = 0
    for el in raw.get("elements", []):
        candidate = _normalize_element(el)
        if not candidate:
            unnamed += 1
            continue
        if candidate["nation"] == "British Isles":
            out_of_remit += 1
            continue
        if c.is_terrestrial_inland_rock(
            candidate["lat"], candidate["lng"], candidate.get("featureKind")
        ):
            skipped_terrestrial_rocks += 1
            continue
        if c.find_existing_match(candidate, index):
            matched += 1
            continue
        missing.append(candidate)
        if limit and len(missing) >= limit:
            break

    report = {
        "agent": "map_scanner",
        "bbox": c.UK_BBOX,
        "islandsInDatabase": len(islands),
        "elementsScanned": len(raw.get("elements", [])),
        "alreadyInDatabase": matched,
        "outOfRemit": out_of_remit,
        "skippedTerrestrialRocks": skipped_terrestrial_rocks,
        "unnamedOrUnlocated": unnamed,
        "missingCandidates": len(missing),
        "candidates": missing,
    }
    c.save_json(c.SCAN_PATH, report)
    print(
        f"Map Scanner: {len(missing)} missing candidates "
        f"({matched} already in DB, {out_of_remit} out of remit, "
        f"{skipped_terrestrial_rocks} terrestrial rocks skipped)",
        file=sys.stderr,
    )
    return report
