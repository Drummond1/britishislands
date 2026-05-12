#!/usr/bin/env python3
"""
Classify inland islands (lake / river) using the methodology in the README.

Implements Tier A (parent water body extraction) and Tier B (point-in-polygon
containment) in a single pass.

Tier A
------
For every UK water multipolygon tagged lake/pond/reservoir/lagoon/oxbow OR
river/canal/stream OR (legacy) waterway=riverbank:
  • read the relation's tags (name, salt/tidal flags, water kind)
  • walk its members and treat every `inner` way as an island of that body
  • cross-reference inner-way OSM IDs against data/islands.json
      – matched islands get re-typed as lake/river, with parentWaterBody
      – inner ways that AREN'T already in the dataset but have a name OR
        place=island/islet tag are appended as newly-discovered inland islands

Tier B
------
Build an STRtree over the outer rings of all non-tidal lake/river polygons.
For every island still tagged `sea` (and not classified by Tier A), point-in-
polygon the centroid against the tree. Any hit gets re-typed accordingly.

Tidal / estuary / sea-loch handling
-----------------------------------
A water body with any of:
   salt=yes | tidal=yes | water=tidal | estuary=yes
is treated as sea, and its inner rings are NOT classified as inland. Skye's
sea lochs, the Thames Estuary, Strangford Lough etc. fall into this bucket.

Run:
    python3 scripts/classify_inland.py            # hits Overpass (~2 min)
    python3 scripts/classify_inland.py --cache    # reuses cached response

Outputs:
    data/water_raw.json                            # cached Overpass response
    data/islands.json                              # updated in place
    data/inland_classification_report.json         # full audit trail
"""

from __future__ import annotations

import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

try:
    from shapely.geometry import LineString, MultiPolygon, Point, Polygon
    from shapely.ops import polygonize, unary_union
    from shapely.strtree import STRtree
except ImportError:
    sys.exit(
        "shapely is required: pip install shapely\n"
        "(used for Tier B point-in-polygon containment)",
    )

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
ISLANDS_PATH = DATA_DIR / "islands.json"
WATER_CACHE = DATA_DIR / "water_raw.json"
REPORT_PATH = DATA_DIR / "inland_classification_report.json"

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
]

UK_BBOX = (49.0, -10.5, 61.5, 2.5)

LAKE_WATER = {"lake", "pond", "reservoir", "lagoon", "oxbow", "basin"}
RIVER_WATER = {"river", "stream", "canal"}


def overpass_query(bbox: tuple[float, float, float, float]) -> str:
    s, w, n, e = bbox
    bb = f"{s},{w},{n},{e}"
    return f"""
[out:json][timeout:600];
(
  relation["type"="multipolygon"]["natural"="water"]["water"]({bb});
  relation["type"="multipolygon"]["waterway"="riverbank"]({bb});
  relation["type"="multipolygon"]["landuse"="reservoir"]({bb});
);
out body;
>;
out tags geom;
""".strip()


def post_overpass(query: str) -> dict:
    last = None
    for url in OVERPASS_ENDPOINTS:
        try:
            print(f"→ {url}", file=sys.stderr)
            req = urllib.request.Request(
                url,
                data=urllib.parse.urlencode({"data": query}).encode("utf-8"),
                headers={"User-Agent": "isles-of-britain/0.2 (inland classifier)"},
            )
            with urllib.request.urlopen(req, timeout=600) as r:
                return json.loads(r.read())
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            print(f"  failed: {exc}", file=sys.stderr)
            last = exc
            time.sleep(2)
    raise RuntimeError(f"All Overpass endpoints failed: {last}")


def classify_body(tags: dict) -> tuple[str | None, bool]:
    """Returns (kind, is_tidal). kind is 'lake', 'river', or None to skip."""
    if (
        tags.get("salt") == "yes"
        or tags.get("tidal") == "yes"
        or tags.get("water") == "tidal"
        or tags.get("estuary") in ("yes", "river")
    ):
        return None, True

    water = tags.get("water")
    waterway = tags.get("waterway")
    landuse = tags.get("landuse")

    if water in LAKE_WATER or landuse == "reservoir":
        return "lake", False
    if water in RIVER_WATER or waterway == "riverbank":
        return "river", False
    return None, False


def subtype_for(tags: dict, kind: str) -> str | None:
    water = tags.get("water")
    waterway = tags.get("waterway")
    landuse = tags.get("landuse")
    if kind == "lake":
        if water == "reservoir" or landuse == "reservoir":
            return "reservoir"
        if water in ("pond", "basin"):
            return water
        if water == "lagoon":
            return "lagoon"
        if water == "oxbow":
            return "oxbow"
    elif kind == "river":
        if waterway == "canal" or water == "canal":
            return "canal"
        if water == "stream":
            return "stream"
    return None


def way_centroid(geom: list[dict]) -> tuple[float, float] | None:
    """Centroid of a way's geometry (list of {lat, lon})."""
    if not geom:
        return None
    lats = [p["lat"] for p in geom]
    lons = [p["lon"] for p in geom]
    return sum(lats) / len(lats), sum(lons) / len(lons)


def way_polygon(geom: list[dict]) -> Polygon | None:
    if not geom or len(geom) < 3:
        return None
    coords = [(p["lon"], p["lat"]) for p in geom]
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    try:
        poly = Polygon(coords)
        return poly if poly.is_valid and not poly.is_empty else poly.buffer(0)
    except Exception:
        return None


def assemble_water_polygon(
    relation: dict, ways: dict[int, dict]
) -> tuple[MultiPolygon | Polygon | None, list[int]]:
    """Stitch outer way segments into closed rings via Shapely's polygonize.

    Large lakes (e.g. Lower Lough Erne) and rivers are modelled as 100+
    open line segments in OSM. Naively closing each segment makes degenerate
    slivers; polygonize takes the noded line graph and emits closed
    polygons properly.

    Returns (water polygon — outer rings only, no holes; list of inner way IDs).
    """
    outer_lines: list[LineString] = []
    inner_way_ids: list[int] = []
    for m in relation.get("members") or []:
        if m["type"] != "way":
            continue
        w = ways.get(m["ref"])
        if not w:
            continue
        role = m.get("role") or ""
        geom = w.get("geometry") or []
        if role == "inner":
            inner_way_ids.append(m["ref"])
            continue
        if len(geom) < 2:
            continue
        try:
            outer_lines.append(LineString([(p["lon"], p["lat"]) for p in geom]))
        except Exception:
            continue
    if not outer_lines:
        return None, inner_way_ids
    try:
        polys = list(polygonize(unary_union(outer_lines)))
        if not polys:
            return None, inner_way_ids
        merged = MultiPolygon(polys) if len(polys) > 1 else polys[0]
        if not merged.is_valid:
            merged = merged.buffer(0)
        return merged, inner_way_ids
    except Exception:
        return None, inner_way_ids


def slug_for(name: str, osm_id: int) -> str:
    if not name:
        return f"osm-way-{osm_id}"
    import re
    s = name.lower()
    s = re.sub(r"[^\w\s\-]+", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", "-", s).strip("-")
    return f"{s or 'island'}-w{osm_id}"


def nation_for(lat: float, lng: float) -> str:
    # Same boxes as fetch_islands.py — keep in sync if you tweak there.
    NATION_BOXES = [
        ("Crown Dependency", (49.0, -2.7, 49.8, -1.9)),
        ("Crown Dependency", (54.0, -4.85, 54.45, -4.25)),
        ("Northern Ireland", (54.0, -8.2, 55.4, -5.4)),
        ("Ireland", (51.3, -10.6, 55.45, -5.4)),
        ("Wales", (51.3, -5.4, 53.45, -2.65)),
        ("Scotland", (54.6, -8.7, 61.5, -0.7)),
        ("Scotland", (57.5, -10.5, 58.5, -8.0)),
        ("England", (49.5, -6.5, 55.9, 1.9)),
    ]
    for nation, (s, w, n, e) in NATION_BOXES:
        if s <= lat <= n and w <= lng <= e:
            return nation
    return "British Isles"


def main() -> None:
    use_cache = "--cache" in sys.argv and WATER_CACHE.exists()
    if use_cache:
        print(f"Using cached water response at {WATER_CACHE.relative_to(ROOT)}", file=sys.stderr)
        raw = json.loads(WATER_CACHE.read_text())
    else:
        print("Fetching UK water bodies from Overpass…", file=sys.stderr)
        raw = post_overpass(overpass_query(UK_BBOX))
        WATER_CACHE.write_text(json.dumps(raw, ensure_ascii=False))
        print(f"  cached to {WATER_CACHE.relative_to(ROOT)}", file=sys.stderr)

    elements = raw.get("elements", [])
    relations = [e for e in elements if e["type"] == "relation"]
    ways = {e["id"]: e for e in elements if e["type"] == "way"}
    print(f"  {len(relations)} water relations, {len(ways)} member ways", file=sys.stderr)

    # ----- Build water-body inventory -----
    bodies = []
    skipped_tidal = 0
    for rel in relations:
        tags = rel.get("tags") or {}
        kind, is_tidal = classify_body(tags)
        if is_tidal:
            skipped_tidal += 1
        if not kind:
            continue
        polygon, inner_way_ids = assemble_water_polygon(rel, ways)
        if polygon is None:
            continue
        bodies.append(
            {
                "osmType": "relation",
                "osmId": rel["id"],
                "name": tags.get("name:en") or tags.get("name") or "",
                "wikidata": tags.get("wikidata") or "",
                "kind": kind,
                "subtype": subtype_for(tags, kind),
                "polygon": polygon,
                "innerWayIds": inner_way_ids,
                "areaKm2": _polygon_area_km2(polygon),
                "tags": tags,
            }
        )

    print(
        f"  {len(bodies)} qualifying inland water bodies "
        f"(skipped {skipped_tidal} tidal / salt / estuary)",
        file=sys.stderr,
    )
    kind_counts = Counter(b["kind"] for b in bodies)
    print(f"    by kind: {dict(kind_counts)}", file=sys.stderr)

    # ----- Load existing islands -----
    islands = json.loads(ISLANDS_PATH.read_text())
    by_osm: dict[tuple, dict] = {}
    for i in islands:
        if i.get("osmType") and i.get("osmId"):
            by_osm[(i["osmType"], i["osmId"])] = i
    print(f"  {len(islands)} islands loaded ({len(by_osm)} with OSM IDs)", file=sys.stderr)

    audit = {"tierA": [], "tierA_discovery": [], "tierB": [], "skipped": []}

    # ----- Build inner-way → most-specific-body index -----
    # An inner ring can belong to multiple water multipolygons (e.g. an
    # island in Lough Erne also tagged as inner of the wider Erne river
    # relation). Pick the smallest containing body — that's the most
    # specific parent.
    inner_way_to_body: dict[int, dict] = {}
    for body in bodies:
        for wid in body["innerWayIds"]:
            existing = inner_way_to_body.get(wid)
            if existing is None:
                inner_way_to_body[wid] = body
                continue
            ea = existing["areaKm2"] or float("inf")
            ba = body["areaKm2"] or float("inf")
            # Prefer lake over river when areas tie, and smaller body otherwise
            if ba < ea or (ba == ea and body["kind"] == "lake" and existing["kind"] == "river"):
                inner_way_to_body[wid] = body

    # Index existing islands by name+proximity so we can merge instead of
    # duplicating when discovery finds an alternate OSM geometry for the
    # same physical island.
    existing_by_name: dict[str, list[dict]] = {}
    for i in islands:
        key = _name_key(i["name"])
        existing_by_name.setdefault(key, []).append(i)

    tier_a_reclassified = 0
    tier_a_discovered = 0
    tier_a_merged = 0
    skipped_unnamed = 0
    skipped_non_uk = 0
    for wid, body in inner_way_to_body.items():
        island = by_osm.get(("way", wid))
        way = ways.get(wid)
        if island:
            if not _is_curated_override(island):
                _apply_classification(island, body, source="tier-a", confidence="high")
                tier_a_reclassified += 1
                audit["tierA"].append(
                    {
                        "id": island["id"],
                        "name": island["name"],
                        "new_type": island["type"],
                        "parent": body["name"] or f"OSM rel {body['osmId']}",
                    }
                )
        elif way:
            wtags = way.get("tags") or {}
            wname = wtags.get("name:en") or wtags.get("name")
            wplace = wtags.get("place")
            # Skip unnamed entries (pure noise) and non-island things
            if not wname:
                skipped_unnamed += 1
                continue
            centroid = way_centroid(way.get("geometry") or [])
            if not centroid:
                continue
            lat, lng = centroid
            # Skip discoveries outside the British / Irish remit
            nation = nation_for(lat, lng)
            if nation == "British Isles":
                skipped_non_uk += 1
                continue
            # Dedupe: if an existing island has the same name and is within
            # ~1 km, merge into it (it's the same physical island).
            merged = False
            for candidate in existing_by_name.get(_name_key(wname), []):
                d = _haversine_km(lat, lng, candidate["lat"], candidate["lng"])
                if d < 1.0:
                    if not _is_curated_override(candidate):
                        # Adopt the inner-ring OSM IDs so the front-end can
                        # fetch the proper polygon.
                        candidate["osmType"] = "way"
                        candidate["osmId"] = wid
                        candidate["osmPlace"] = wplace or candidate.get("osmPlace", "")
                        _apply_classification(
                            candidate, body, source="tier-a", confidence="high"
                        )
                        tier_a_merged += 1
                        audit["tierA"].append(
                            {
                                "id": candidate["id"],
                                "name": candidate["name"],
                                "new_type": candidate["type"],
                                "parent": body["name"] or f"OSM rel {body['osmId']}",
                                "merged_from_inner": wid,
                            }
                        )
                    merged = True
                    break
            if merged:
                continue
            new_island = {
                "id": slug_for(wname, wid),
                "name": wname,
                "nation": nation,
                "type": body["kind"],
                "archipelago": body["name"],
                "lat": round(lat, 5),
                "lng": round(lng, 5),
                "areaKm2": _polygon_area_km2(way_polygon(way["geometry"])),
                "population": None,
                "highestPointM": None,
                "highestPointName": "",
                "shortDescription": "",
                "history": "",
                "geography": "",
                "transport": "",
                "accommodation": "",
                "wikipedia": "",
                "image": "",
                "tags": [
                    t for t in [wplace or "island", "inland", body["kind"]] if t
                ],
                "source": "osm-inland",
                "osmType": "way",
                "osmId": wid,
                "osmPlace": wplace or "",
            }
            _apply_classification(
                new_island, body, source="tier-a", confidence="high"
            )
            islands.append(new_island)
            by_osm[("way", wid)] = new_island
            existing_by_name.setdefault(_name_key(wname), []).append(new_island)
            tier_a_discovered += 1
            audit["tierA_discovery"].append(
                {
                    "id": new_island["id"],
                    "name": new_island["name"],
                    "parent": body["name"] or f"OSM rel {body['osmId']}",
                    "type": body["kind"],
                }
            )

    print(
        f"  Tier A: reclassified {tier_a_reclassified} existing islands, "
        f"merged {tier_a_merged} alternate geometries, "
        f"discovered {tier_a_discovered} new ones "
        f"(skipped {skipped_unnamed} unnamed, {skipped_non_uk} outside UK/Ireland)",
        file=sys.stderr,
    )

    # ----- Tier B: point-in-polygon containment for remaining sea islands -----
    body_polys = [b["polygon"] for b in bodies]
    tree = STRtree(body_polys)
    # Index back to the body record by polygon's wkb
    poly_to_body = {id(p): b for p, b in zip(body_polys, bodies)}

    tier_b_reclassified = 0
    for island in islands:
        if _is_curated_override(island):
            continue
        if island.get("classification", {}).get("source") in ("tier-a", "manual"):
            continue
        if island["type"] != "sea":
            continue
        pt = Point(island["lng"], island["lat"])
        # Shapely 2.x: query(geom, predicate='intersects') gives candidate
        # tree-index hits via the bounding box. Then verify with proper
        # polygon.contains(point) (point.within would also work).
        candidate_idx = tree.query(pt, predicate="intersects")
        if len(candidate_idx) == 0:
            continue
        best = None
        best_area = math.inf
        for idx in candidate_idx:
            poly = body_polys[int(idx)]
            if not poly.contains(pt):
                continue
            body = poly_to_body[id(poly)]
            a = body["areaKm2"] or float("inf")
            if a < best_area:
                best_area = a
                best = body
        if best:
            _apply_classification(island, best, source="tier-b", confidence="medium")
            tier_b_reclassified += 1
            audit["tierB"].append(
                {
                    "id": island["id"],
                    "name": island["name"],
                    "new_type": island["type"],
                    "parent": best["name"] or f"OSM rel {best['osmId']}",
                }
            )

    print(f"  Tier B: reclassified {tier_b_reclassified} additional islands", file=sys.stderr)

    # ----- Write outputs -----
    islands.sort(key=lambda i: i["name"].lower())
    ISLANDS_PATH.write_text(json.dumps(islands, ensure_ascii=False, indent=2) + "\n")

    REPORT_PATH.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")

    # Final stats
    by_type = Counter(i["type"] for i in islands)
    print(f"\nFinal: {len(islands)} islands", file=sys.stderr)
    print(f"  by type: {dict(by_type)}", file=sys.stderr)
    print(f"  audit written to {REPORT_PATH.relative_to(ROOT)}", file=sys.stderr)


def _is_curated_override(island: dict) -> bool:
    """Don't overwrite hand-curated type tags — they trump auto-classification."""
    return island.get("source") == "curated" and island.get("type") in (
        "lake",
        "river",
    )


def _apply_classification(island: dict, body: dict, *, source: str, confidence: str) -> None:
    island["type"] = body["kind"]
    if body.get("subtype"):
        island["subtype"] = body["subtype"]
    island["parentWaterBody"] = {
        "name": body["name"],
        "type": body["kind"],
        "osmType": body["osmType"],
        "osmId": body["osmId"],
        "wikidata": body["wikidata"],
    }
    island["classification"] = {"source": source, "confidence": confidence}


def _name_key(name: str) -> str:
    import re
    s = (name or "").lower()
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"\bisle of\b|\bisland\b|\bynys\b|\binch\b", "", s)
    s = re.sub(r"[^\w\s]", "", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _polygon_area_km2(poly) -> float | None:
    if poly is None:
        return None
    try:
        # Approximate using degrees → metres at the polygon's centroid latitude.
        # Cheap and accurate enough for ranking; not for cartographic use.
        c = poly.centroid
        lat = c.y
        deg_to_m_lat = 111_320
        deg_to_m_lng = 111_320 * math.cos(math.radians(lat))
        # Shapely's .area is in (degree²). Convert.
        a_m2 = poly.area * deg_to_m_lat * deg_to_m_lng
        return round(a_m2 / 1_000_000, 4)
    except Exception:
        return None


if __name__ == "__main__":
    main()
