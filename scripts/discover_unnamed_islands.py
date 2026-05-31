#!/usr/bin/env python3
"""
Discover unnamed island landmasses at ≥98% confidence and merge into islands.json.

Sources (OpenStreetMap ODbL):
  1. Inner rings of inland water multipolygons (lake / river) — unnamed ways
     fully enclosed by a parent water body (Tier-A topology).
  2. Standalone place=island|islet ways/relations with no name tags and
     polygon area above type-specific thresholds.

Records use nameStatus=unknown and a placeholder display name. Map pins are
styled separately in app.js (orange) for crowdsourced naming later.

Run:
    python3 scripts/discover_unnamed_islands.py --cache          # dry-run report
    python3 scripts/discover_unnamed_islands.py --cache --apply  # write islands.json

Outputs:
    data/discovery/unnamed_candidates.json
    data/unnamed_islands_ingestion_report.json
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from classify_inland import (  # noqa: E402
    UK_BBOX,
    _polygon_area_km2,
    assemble_water_polygon,
    classify_body,
    nation_for,
    subtype_for,
    way_polygon,
)
from discovery import common as c  # noqa: E402

WATER_CACHE = c.DATA / "water_raw.json"
STANDALONE_CACHE = c.DATA / "cache_unnamed_osm_geom.json"
CANDIDATES_PATH = c.DISCOVERY_DIR / "unnamed_candidates.json"
REPORT_PATH = c.DATA / "unnamed_islands_ingestion_report.json"

MIN_CONFIDENCE = 0.98
MIN_INNER_AREA_KM2 = 0.0008  # ~800 m²
MAX_INNER_AREA_KM2 = 50.0
MIN_ISLAND_AREA_KM2 = 0.002
MIN_ISLET_AREA_KM2 = 0.005
DEDUPE_KM = 0.12

NAME_KEYS = ("name:en", "name", "official_name", "alt_name", "loc_name", "ref")


def has_any_name(tags: dict) -> bool:
    return any((tags.get(k) or "").strip() for k in NAME_KEYS)


def osm_source_url(osm_type: str, osm_id: int) -> str:
    return f"https://www.openstreetmap.org/{osm_type}/{osm_id}"


def standalone_query(bbox: tuple[float, float, float, float]) -> str:
    s, w, n, e = bbox
    return f"""
[out:json][timeout:300];
(
  way["place"~"^(island|islet)$"][!"name"]({s},{w},{n},{e});
  relation["place"~"^(island|islet)$"][!"name"]({s},{w},{n},{e});
  way["place"~"^(island|islet)$"]["name"~""]({s},{w},{n},{e});
  relation["place"~"^(island|islet)$"]["name"~""]({s},{w},{n},{e});
);
out tags center geom;
""".strip()


def element_polygon(el: dict) -> Any | None:
    geom = el.get("geometry") or []
    if not geom:
        return None
    if el.get("type") == "way":
        return way_polygon(geom)
    if el.get("type") == "relation":
        try:
            from shapely.geometry import Polygon

            polys = []
            for part in geom:
                if part.get("type") != "way":
                    continue
                ring = [(p["lon"], p["lat"]) for p in part.get("geometry") or []]
                if len(ring) < 3:
                    continue
                if ring[0] != ring[-1]:
                    ring.append(ring[0])
                p = Polygon(ring)
                if p.is_valid and not p.is_empty:
                    polys.append(p)
            if not polys:
                return None
            merged = polys[0] if len(polys) == 1 else __import__("shapely.ops", fromlist=["unary_union"]).unary_union(polys)
            return merged if not merged.is_empty else None
        except Exception:
            return None
    return None


def confidence_for_inner(area_km2: float) -> float:
    if area_km2 >= MIN_INNER_AREA_KM2:
        return 0.99
    return 0.0


def confidence_for_standalone(place: str, area_km2: float) -> float:
    if place == "island" and area_km2 >= MIN_ISLAND_AREA_KM2:
        return 0.99
    if place == "islet" and area_km2 >= MIN_ISLET_AREA_KM2:
        return 0.985
    return 0.0


def build_record(
    *,
    osm_type: str,
    osm_id: int,
    lat: float,
    lng: float,
    area_km2: float,
    island_type: str,
    confidence: float,
    source_kind: str,
    osm_place: str,
    parent_body: dict | None,
    subtype: str | None = None,
) -> dict:
    record = {
        "id": f"osm-{osm_type}-{osm_id}",
        "name": "Unnamed island",
        "nameStatus": "unknown",
        "nation": nation_for(lat, lng),
        "type": island_type,
        "subtype": subtype,
        "tidal": None,
        "archipelago": "",
        "lat": round(lat, 5),
        "lng": round(lng, 5),
        "areaKm2": round(area_km2, 4) if area_km2 else None,
        "population": None,
        "highestPointM": None,
        "highestPointName": "",
        "shortDescription": "",
        "history": "",
        "geography": "",
        "transport": "",
        "accommodation": "",
        "wikipedia": "",
        "wikidata": "",
        "image": "",
        "images": [],
        "tags": ["unnamed", "needs-name"],
        "source": "osm-unnamed",
        "osmType": osm_type,
        "osmId": osm_id,
        "osmPlace": osm_place,
        "parentWaterBody": parent_body,
        "classification": {
            "source": "unnamed-discovery",
            "confidence": "high",
            "reviewHint": (
                f"Unnamed landmass ({source_kind}); OSM confidence {confidence:.3f}. "
                "Name not yet recorded — crowdsourcing welcome via Contribute."
            )[:800],
        },
        "sources": [
            {
                "name": "openstreetmap",
                "url": osm_source_url(osm_type, osm_id),
                "license": "ODbL",
                "retrievedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            }
        ],
        "discoveryConfidence": round(confidence, 4),
        "discoverySourceKind": source_kind,
    }
    return record


def scan_inner_rings(islands: list[dict], index: dict[str, Any]) -> tuple[list[dict], dict[str, int]]:
    if not WATER_CACHE.exists():
        raise FileNotFoundError(
            f"Missing {WATER_CACHE.name} — run python3 scripts/classify_inland.py --cache first"
        )
    raw = json.loads(WATER_CACHE.read_text(encoding="utf-8"))
    ways = {e["id"]: e for e in raw.get("elements", []) if e["type"] == "way"}
    relations = [e for e in raw.get("elements", []) if e["type"] == "relation"]

    inner_way_to_body: dict[int, dict] = {}
    for rel in relations:
        tags = rel.get("tags") or {}
        kind, is_tidal = classify_body(tags)
        if not kind or is_tidal:
            continue
        _poly, inner_ids = assemble_water_polygon(rel, ways)
        body = {
            "kind": kind,
            "name": tags.get("name:en") or tags.get("name") or "",
            "osmType": "relation",
            "osmId": rel["id"],
            "wikidata": tags.get("wikidata") or "",
            "subtype": subtype_for(tags, kind),
            "areaKm2": _polygon_area_km2(_poly) if _poly is not None else None,
            "innerWayIds": inner_ids,
        }
        for wid in inner_ids:
            existing = inner_way_to_body.get(wid)
            if existing is None:
                inner_way_to_body[wid] = body
                continue
            ea = existing.get("areaKm2") or float("inf")
            ba = body.get("areaKm2") or float("inf")
            if ba < ea or (ba == ea and body["kind"] == "lake" and existing["kind"] == "river"):
                inner_way_to_body[wid] = body

    stats: dict[str, int] = {}
    out: list[dict] = []

    for wid, body in inner_way_to_body.items():
        way = ways.get(wid)
        if not way:
            stats["noWay"] = stats.get("noWay", 0) + 1
            continue
        tags = way.get("tags") or {}
        if has_any_name(tags):
            stats["hasName"] = stats.get("hasName", 0) + 1
            continue
        if index["osm"].get(("way", wid)):
            stats["alreadyInDataset"] = stats.get("alreadyInDataset", 0) + 1
            continue
        poly = way_polygon(way.get("geometry") or [])
        if not poly:
            stats["noPolygon"] = stats.get("noPolygon", 0) + 1
            continue
        area = _polygon_area_km2(poly)
        if not area or area < MIN_INNER_AREA_KM2 or area > MAX_INNER_AREA_KM2:
            stats["areaRejected"] = stats.get("areaRejected", 0) + 1
            continue
        conf = confidence_for_inner(area)
        if conf < MIN_CONFIDENCE:
            stats["lowConfidence"] = stats.get("lowConfidence", 0) + 1
            continue
        lat, lng = poly.centroid.y, poly.centroid.x
        if nation_for(lat, lng) == "British Isles":
            stats["outOfRemit"] = stats.get("outOfRemit", 0) + 1
            continue
        if c.find_existing_match(
            {"lat": lat, "lng": lng, "name": "", "osmType": "way", "osmId": wid},
            index,
            loose=False,
        ):
            stats["matchedExisting"] = stats.get("matchedExisting", 0) + 1
            continue

        parent = None
        if body.get("name") or body.get("osmId"):
            parent = {
                "name": body.get("name") or f"OSM relation {body['osmId']}",
                "type": body["kind"],
                "osmType": body.get("osmType"),
                "osmId": body.get("osmId"),
                "wikidata": body.get("wikidata") or "",
            }
        out.append(
            build_record(
                osm_type="way",
                osm_id=wid,
                lat=lat,
                lng=lng,
                area_km2=area,
                island_type=body["kind"],
                confidence=conf,
                source_kind="osm-inner-ring",
                osm_place=tags.get("place") or "islet",
                parent_body=parent,
                subtype=body.get("subtype"),
            )
        )

    stats["accepted"] = len(out)
    return out, stats


def scan_standalone(islands: list[dict], index: dict[str, Any], *, use_cache: bool) -> tuple[list[dict], dict[str, int]]:
    stats: dict[str, int] = {}
    if use_cache and STANDALONE_CACHE.exists():
        raw = json.loads(STANDALONE_CACHE.read_text(encoding="utf-8"))
    else:
        print("→ Fetching unnamed standalone islands with geometry…", file=sys.stderr)
        try:
            raw = c.post_overpass(standalone_query(UK_BBOX))
            STANDALONE_CACHE.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
            time.sleep(0.5)
        except RuntimeError as exc:
            print(f"Standalone fetch skipped: {exc}", file=sys.stderr)
            stats["fetchFailed"] = 1
            return out, stats

    inner_way_ids: set[int] = set()
    if WATER_CACHE.exists():
        wr = json.loads(WATER_CACHE.read_text(encoding="utf-8"))
        wways = {e["id"]: e for e in wr.get("elements", []) if e["type"] == "way"}
        for rel in wr.get("elements", []):
            if rel.get("type") != "relation":
                continue
            tags = rel.get("tags") or {}
            kind, tidal = classify_body(tags)
            if not kind or tidal:
                continue
            _, inner_ids = assemble_water_polygon(rel, wways)
            inner_way_ids.update(inner_ids)

    out: list[dict] = []
    for el in raw.get("elements", []):
        if el.get("type") not in {"way", "relation"}:
            stats["skipNode"] = stats.get("skipNode", 0) + 1
            continue
        tags = el.get("tags") or {}
        if has_any_name(tags):
            stats["hasName"] = stats.get("hasName", 0) + 1
            continue
        osm_type = el["type"]
        osm_id = el["id"]
        if osm_type == "way" and osm_id in inner_way_ids:
            stats["innerRingDup"] = stats.get("innerRingDup", 0) + 1
            continue
        if index["osm"].get((osm_type, osm_id)):
            stats["alreadyInDataset"] = stats.get("alreadyInDataset", 0) + 1
            continue
        poly = element_polygon(el)
        if not poly:
            stats["noPolygon"] = stats.get("noPolygon", 0) + 1
            continue
        area = _polygon_area_km2(poly)
        if not area:
            stats["areaRejected"] = stats.get("areaRejected", 0) + 1
            continue
        place = (tags.get("place") or "islet").lower()
        conf = confidence_for_standalone(place, area)
        if conf < MIN_CONFIDENCE:
            stats["lowConfidence"] = stats.get("lowConfidence", 0) + 1
            continue
        lat, lng = poly.centroid.y, poly.centroid.x
        if not c.in_remit(lat, lng):
            stats["outOfRemit"] = stats.get("outOfRemit", 0) + 1
            continue
        if c.is_terrestrial_inland_rock(lat, lng, place):
            stats["terrestrialRock"] = stats.get("terrestrialRock", 0) + 1
            continue
        if c.find_existing_match(
            {"lat": lat, "lng": lng, "name": "", "osmType": osm_type, "osmId": osm_id},
            index,
            loose=False,
        ):
            stats["matchedExisting"] = stats.get("matchedExisting", 0) + 1
            continue

        out.append(
            build_record(
                osm_type=osm_type,
                osm_id=osm_id,
                lat=lat,
                lng=lng,
                area_km2=area,
                island_type="sea",
                confidence=conf,
                source_kind="osm-place-tag",
                osm_place=place,
                parent_body=None,
            )
        )

    stats["accepted"] = len(out)
    return out, stats


def dedupe_candidates(candidates: list[dict]) -> tuple[list[dict], int]:
    kept: list[dict] = []
    dropped = 0
    for row in sorted(candidates, key=lambda r: -(r.get("discoveryConfidence") or 0)):
        dup = False
        for existing in kept:
            if c.haversine_km(row["lat"], row["lng"], existing["lat"], existing["lng"]) <= DEDUPE_KM:
                dup = True
                break
        if dup:
            dropped += 1
        else:
            kept.append(row)
    return kept, dropped


def main() -> None:
    use_cache = "--cache" in sys.argv
    apply = "--apply" in sys.argv
    skip_standalone = "--inner-only" in sys.argv

    islands = c.load_islands()
    index = c.build_island_index(islands)
    print(f"Loaded {len(islands)} islands", file=sys.stderr)

    inner, inner_stats = scan_inner_rings(islands, index)
    print(f"Inner-ring candidates: {inner_stats.get('accepted', 0)}", file=sys.stderr)

    standalone: list[dict] = []
    standalone_stats: dict[str, int] = {}
    if not skip_standalone:
        standalone, standalone_stats = scan_standalone(islands, index, use_cache=use_cache)
        print(
            f"Standalone candidates: {standalone_stats.get('accepted', 0)}",
            file=sys.stderr,
        )

    merged = inner + standalone
    deduped, dropped = dedupe_candidates(merged)

    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "minConfidence": MIN_CONFIDENCE,
        "datasetCountBefore": len(islands),
        "innerRingStats": inner_stats,
        "standaloneStats": standalone_stats,
        "combinedBeforeDedupe": len(merged),
        "dedupeDropped": dropped,
        "candidateCount": len(deduped),
        "applied": False,
        "candidates": deduped,
    }
    c.save_json(CANDIDATES_PATH, {"records": deduped, "meta": {k: v for k, v in report.items() if k != "candidates"}})
    c.save_json(REPORT_PATH, report)

    print(f"Wrote {CANDIDATES_PATH.relative_to(ROOT)} ({len(deduped)} candidates)", file=sys.stderr)

    if apply and deduped:
        backup = c.ISLANDS_PATH.with_name(
            f"islands.json.before-unnamed-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        )
        backup.write_text(c.ISLANDS_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        islands.extend(deduped)
        islands.sort(key=lambda row: (row.get("name") or "").lower())
        c.ISLANDS_PATH.write_text(json.dumps(islands, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report["applied"] = True
        report["backupPath"] = str(backup)
        report["datasetCountAfter"] = len(islands)
        c.save_json(REPORT_PATH, report)
        print(
            f"Applied {len(deduped)} unnamed islands → {len(islands)} total (backup {backup.name})",
            file=sys.stderr,
        )
        print("Run: python3 scripts/build_islands_index.py", file=sys.stderr)
    elif not apply:
        print("Dry run — pass --apply to merge into data/islands.json", file=sys.stderr)


if __name__ == "__main__":
    main()
