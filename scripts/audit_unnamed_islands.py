#!/usr/bin/env python3
"""
Find unnamed (or weakly named) island features in OpenStreetMap, Wikidata,
and Wikipedia within the Isles of Britain remit.

Read-only: writes data/unnamed_islands_audit.json and prints a summary.
Does not modify data/islands.json.

Run:
    python3 scripts/audit_unnamed_islands.py
    python3 scripts/audit_unnamed_islands.py --cache
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS_PATH = DATA / "islands.json"
OSM_CACHE = DATA / "cache_unnamed_osm.json"
WD_CACHE = DATA / "cache_unnamed_wikidata.json"
WP_CACHE = DATA / "cache_unnamed_wikipedia.json"
REPORT_PATH = DATA / "unnamed_islands_audit.json"
WATER_CACHE = DATA / "water_raw.json"

UK_BBOX = (49.0, -10.5, 61.5, 2.5)
OVERPASS_ENDPOINTS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
]
USER_AGENT = "isles-of-britain/0.8 (unnamed-island-audit; static-site)"
DELAY = 0.2


def post_overpass(query: str) -> dict:
    last: Exception | None = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            data = urllib.parse.urlencode({"data": query}).encode("utf-8")
            req = urllib.request.Request(
                endpoint,
                data=data,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=300) as resp:
                return json.loads(resp.read())
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last = exc
            time.sleep(2)
    raise RuntimeError(f"Overpass failed: {last}")


def get_json(url: str, params: dict | None = None, timeout: int = 120) -> dict:
    qs = urllib.parse.urlencode(params or {}, safe=":/?&=,")
    full = url + ("?" + qs if qs else "")
    req = urllib.request.Request(
        full,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def post_sparql(query: str) -> dict:
    body = urllib.parse.urlencode({"query": query}).encode()
    req = urllib.request.Request(
        "https://query.wikidata.org/sparql",
        data=body,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/sparql-results+json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read())


def in_bbox(lat: float, lng: float) -> bool:
    s, w, n, e = UK_BBOX
    return s <= lat <= n and w <= lng <= e


def element_center(el: dict) -> tuple[float, float] | None:
    if el.get("type") == "node":
        lat, lng = el.get("lat"), el.get("lon")
    else:
        center = el.get("center") or {}
        lat, lng = center.get("lat"), center.get("lon")
    if lat is None or lng is None:
        return None
    return float(lat), float(lng)


def display_name(tags: dict) -> str:
    for key in ("name:en", "name", "alt_name", "loc_name", "official_name"):
        value = (tags.get(key) or "").strip()
        if value:
            return value
    return ""


def osm_unnamed_query(bbox: tuple[float, float, float, float]) -> str:
    s, w, n, e = bbox
    return f"""
[out:json][timeout:300];
(
  node["place"~"^(island|islet)$"][!"name"]({s},{w},{n},{e});
  way["place"~"^(island|islet)$"][!"name"]({s},{w},{n},{e});
  relation["place"~"^(island|islet)$"][!"name"]({s},{w},{n},{e});
  node["place"~"^(island|islet)$"]["name"~""]({s},{w},{n},{e});
  way["place"~"^(island|islet)$"]["name"~""]({s},{w},{n},{e});
  relation["place"~"^(island|islet)$"]["name"~""]({s},{w},{n},{e});
);
out tags center;
""".strip()


def audit_osm(islands: list[dict], use_cache: bool) -> dict:
    if use_cache and OSM_CACHE.exists():
        raw = json.loads(OSM_CACHE.read_text())
    else:
        raw = post_overpass(osm_unnamed_query(UK_BBOX))
        OSM_CACHE.write_text(json.dumps(raw, ensure_ascii=False))

    known_osm = {
        (i.get("osmType"), i.get("osmId"))
        for i in islands
        if i.get("osmType") and i.get("osmId")
    }
    samples: list[dict] = []
    with_alt_only = 0
    in_dataset = 0
    for el in raw.get("elements", []):
        tags = el.get("tags") or {}
        center = element_center(el)
        if not center or not in_bbox(*center):
            continue
        name = display_name(tags)
        if name:
            with_alt_only += 1
            continue
        key = (el["type"], el["id"])
        if key in known_osm:
            in_dataset += 1
        if len(samples) < 40:
            samples.append(
                {
                    "osmType": el["type"],
                    "osmId": el["id"],
                    "lat": round(center[0], 5),
                    "lng": round(center[1], 5),
                    "place": tags.get("place"),
                    "natural": tags.get("natural"),
                    "inDataset": key in known_osm,
                }
            )

    return {
        "rawElements": len(raw.get("elements", [])),
        "withoutAnyNameTag": len(raw.get("elements", [])) - with_alt_only,
        "withAltNameOnlySkipped": with_alt_only,
        "alreadyInDataset": in_dataset,
        "samples": samples,
    }


def audit_osm_inner_rings(islands: list[dict], use_cache: bool) -> dict:
    if not WATER_CACHE.exists():
        return {"skipped": True, "reason": f"missing {WATER_CACHE.name}"}

    raw = json.loads(WATER_CACHE.read_text())
    ways = {e["id"]: e for e in raw.get("elements", []) if e["type"] == "way"}
    known_way = {
        i["osmId"]
        for i in islands
        if i.get("osmType") == "way" and i.get("osmId")
    }
    unnamed_inner = 0
    named_inner_missing = 0
    samples: list[dict] = []
    for rel in raw.get("elements", []):
        if rel.get("type") != "relation":
            continue
        tags = rel.get("tags") or {}
        if tags.get("type") != "multipolygon":
            continue
        body_name = display_name(tags)
        for member in rel.get("members") or []:
            if member.get("role") != "inner":
                continue
            if member.get("type") != "way":
                continue
            wid = member["ref"]
            wtags = (ways.get(wid) or {}).get("tags") or {}
            wname = display_name(wtags)
            if not wname:
                unnamed_inner += 1
                if len(samples) < 40:
                    samples.append(
                        {
                            "osmWayId": wid,
                            "parentWaterBody": body_name or None,
                            "parentOsmId": rel["id"],
                            "inDataset": wid in known_way,
                            "place": wtags.get("place"),
                        }
                    )
            elif wid not in known_way:
                named_inner_missing += 1

    return {
        "unnamedInnerWays": unnamed_inner,
        "namedInnerWaysNotInDataset": named_inner_missing,
        "samples": samples,
    }


WD_QUERY = """
SELECT ?item ?itemLabel ?coord ?enLabel ?gaLabel ?gdLabel WHERE {
  ?item wdt:P31/wdt:P279* wd:Q23442 .
  ?item wdt:P625 ?coord .
  OPTIONAL { ?item rdfs:label ?enLabel FILTER(LANG(?enLabel) = "en") . }
  OPTIONAL { ?item rdfs:label ?gaLabel FILTER(LANG(?gaLabel) = "ga") . }
  OPTIONAL { ?item rdfs:label ?gdLabel FILTER(LANG(?gdLabel) = "gd") . }
  FILTER((?enLabel = "" || !BOUND(?enLabel)) && (!BOUND(?gaLabel) || ?gaLabel = "") && (!BOUND(?gdLabel) || ?gdLabel = ""))
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
LIMIT 5000
"""


def parse_point_wkt(wkt: str) -> tuple[float, float] | None:
    m = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", wkt)
    if not m:
        return None
    return float(m.group(2)), float(m.group(1))


def audit_wikidata(islands: list[dict], use_cache: bool) -> dict:
    if use_cache and WD_CACHE.exists():
        rows = json.loads(WD_CACHE.read_text())
    else:
        payload = post_sparql(WD_QUERY)
        rows = payload.get("results", {}).get("bindings", [])
        WD_CACHE.write_text(json.dumps(rows, ensure_ascii=False))
        time.sleep(DELAY)

    known_q = {i.get("wikidata") for i in islands if i.get("wikidata")}
    in_remit = 0
    in_dataset = 0
    label_is_qid = 0
    samples: list[dict] = []
    for row in rows:
        qid = row["item"]["value"].rsplit("/", 1)[-1]
        wkt = (row.get("coord") or {}).get("value", "")
        latlng = parse_point_wkt(wkt) if wkt else None
        if not latlng or not in_bbox(*latlng):
            continue
        in_remit += 1
        label = (row.get("itemLabel") or {}).get("value", "")
        if label == qid:
            label_is_qid += 1
        if qid in known_q:
            in_dataset += 1
        if len(samples) < 40:
            samples.append(
                {
                    "wikidata": qid,
                    "label": label,
                    "lat": round(latlng[0], 5),
                    "lng": round(latlng[1], 5),
                    "inDataset": qid in known_q,
                }
            )

    return {
        "rowsWithoutEnGaGdLabel": in_remit,
        "labelLooksLikeQid": label_is_qid,
        "alreadyInDataset": in_dataset,
        "samples": samples,
    }


def audit_wikipedia(islands: list[dict], use_cache: bool) -> dict:
    if use_cache and WP_CACHE.exists():
        cache = json.loads(WP_CACHE.read_text())
    else:
        params = {
            "action": "query",
            "format": "json",
            "list": "categorymembers",
            "cmtitle": "Category:Unnamed_islands",
            "cmlimit": "500",
            "cmtype": "page",
        }
        cache = get_json("https://en.wikipedia.org/w/api.php", params)
        WP_CACHE.write_text(json.dumps(cache, ensure_ascii=False))
        time.sleep(DELAY)

    members = (cache.get("query") or {}).get("categorymembers") or []
    islandish = [
        m
        for m in members
        if re.search(r"\bisland\b|\bislet\b|\bholm\b|\beyot\b|\bait\b", m.get("title", ""), re.I)
    ]

    known_titles = {
        (i.get("wikipedia") or "").rsplit("/", 1)[-1].replace("_", " ").lower()
        for i in islands
        if i.get("wikipedia")
    }
    missing = []
    for m in islandish:
        title = m.get("title", "")
        if title.lower() not in known_titles:
            missing.append({"title": title, "pageid": m.get("pageid")})

    return {
        "category": "Category:Unnamed_islands",
        "memberCount": len(members),
        "islandishTitles": len(islandish),
        "notLinkedFromDatasetByTitle": len(missing),
        "samples": missing[:40],
    }


def main() -> None:
    use_cache = "--cache" in sys.argv
    islands = json.loads(ISLANDS_PATH.read_text())
    print(f"Loaded {len(islands)} islands", file=sys.stderr)

    report = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "datasetCount": len(islands),
        "bbox": UK_BBOX,
        "openstreetmap": audit_osm(islands, use_cache),
        "openstreetmapInnerRings": audit_osm_inner_rings(islands, use_cache),
        "wikidata": audit_wikidata(islands, use_cache),
        "wikipedia": audit_wikipedia(islands, use_cache),
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    print(f"Wrote {REPORT_PATH.relative_to(ROOT)}", file=sys.stderr)
    print("OSM unnamed place=island|islet:", report["openstreetmap"]["withoutAnyNameTag"], file=sys.stderr)
    print("OSM unnamed inner ways:", report["openstreetmapInnerRings"].get("unnamedInnerWays"), file=sys.stderr)
    print("Wikidata no en/ga/gd label in bbox:", report["wikidata"]["rowsWithoutEnGaGdLabel"], file=sys.stderr)
    print("Wikipedia Category:Unnamed_islands islandish:", report["wikipedia"]["islandishTitles"], file=sys.stderr)


if __name__ == "__main__":
    main()
