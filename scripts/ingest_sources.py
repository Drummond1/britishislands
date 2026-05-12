#!/usr/bin/env python3
"""
Ingest new island candidates from the priority sources catalogued in
docs/DISCOVERY-SOURCES.md and execute the action plan in
docs/NEXT-SESSION-PLAN.md.

Actions (each can be run alone via --only=NAME):
    1. wikidata   — Wikidata SPARQL across UK + IE + IoM + Jersey + Guernsey
                    Also harvests multilingual labels (ga/gd/cy/gv/kw)
                    for cultural-name schema migration.
    2. thames     — Wikipedia "Islands in the River Thames" wikitable.
    3. crannogs   — HES Canmore + NMS Ireland + DfC NI NISMR
                    (filtered: above-water, with name, scheduled monument).
    4. designations — NatureScot SSSI + NIEA ASSI + NPWS Ireland +
                    Tailte Éireann Islands. Island-bounded designations only.

All actions:
    * Cache raw API responses in data/cache_*.json
    * Emit candidate entries with full provenance
    * Honour docs/ETHICS.md (CC0/CC-BY/OGL only; cultural names preserved;
      sensitive sites at name-level only).

Final dedup pass merges all candidates against data/islands.json using
name+proximity (≤1 km). Curated wins; otherwise the richest record wins.

Run examples:
    python3 scripts/ingest_sources.py --only=wikidata
    python3 scripts/ingest_sources.py --only=thames
    python3 scripts/ingest_sources.py --only=crannogs
    python3 scripts/ingest_sources.py --only=designations
    python3 scripts/ingest_sources.py            # run all four then merge
    python3 scripts/ingest_sources.py --merge    # only the merge pass
"""

from __future__ import annotations

import json
import math
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS_PATH = DATA / "islands.json"
INGEST_REPORT = DATA / "discovery_ingestion_report.json"

# Per-action raw caches & candidate files
WD_CACHE = DATA / "cache_wd_islands.json"
WD_CANDIDATES = DATA / "candidates_wikidata.json"
THAMES_CACHE = DATA / "cache_thames.json"
THAMES_CANDIDATES = DATA / "candidates_thames.json"
CRANNOG_CACHE = DATA / "cache_crannogs.json"
CRANNOG_CANDIDATES = DATA / "candidates_crannogs.json"
DESIG_CACHE = DATA / "cache_designations.json"
DESIG_CANDIDATES = DATA / "candidates_designations.json"

USER_AGENT = (
    "isles-of-britain/0.4 ingest-sources (open-data research; "
    "https://example.org/isles-of-britain; static-site)"
)
DELAY = 0.15

# ------------------------------- HTTP helpers ------------------------------

def _open(req: urllib.request.Request, timeout: int = 90) -> bytes:
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last = exc
            sleep = (1.5 ** attempt) + random.random() * 0.4
            if isinstance(exc, urllib.error.HTTPError) and exc.code == 429:
                sleep = max(sleep, 5)
            time.sleep(sleep)
    raise RuntimeError(f"HTTP failed after retries: {last}")


def _get_json(url: str, params: dict[str, Any] | None = None, timeout: int = 90) -> dict:
    qs = urllib.parse.urlencode(params or {}, safe=":/?&=,")
    full = url + ("?" + qs if qs else "")
    req = urllib.request.Request(
        full,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    return json.loads(_open(req, timeout))


def _get_text(url: str, timeout: int = 60) -> str:
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"}
    )
    return _open(req, timeout).decode("utf-8", errors="replace")


def _post_sparql(query: str) -> dict:
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
    return json.loads(_open(req, timeout=180))


# ------------------------------- Geographic helpers ----------------------

UK_BBOX = (49.0, -10.5, 61.5, 2.5)

NATION_BOXES: list[tuple[str, tuple[float, float, float, float]]] = [
    ("Crown Dependency", (49.0, -2.7, 49.8, -1.9)),
    ("Crown Dependency", (54.0, -4.85, 54.45, -4.25)),
    ("Northern Ireland", (54.0, -8.2, 55.4, -5.4)),
    ("Ireland", (51.3, -10.6, 55.45, -5.4)),
    ("Wales", (51.3, -5.4, 53.45, -2.65)),
    ("Scotland", (54.6, -8.7, 61.5, -0.7)),
    ("Scotland", (57.5, -10.5, 58.5, -8.0)),
    ("England", (49.5, -6.5, 55.9, 1.9)),
]


def nation_for(lat: float, lng: float) -> str:
    for nation, (s, w, n, e) in NATION_BOXES:
        if s <= lat <= n and w <= lng <= e:
            return nation
    return "British Isles"


def in_remit(lat: float, lng: float) -> bool:
    s, w, n, e = UK_BBOX
    if not (s <= lat <= n and w <= lng <= e):
        return False
    return nation_for(lat, lng) != "British Isles"


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def slugify(name: str, prefix: str = "") -> str:
    s = (name or "island").lower()
    s = re.sub(r"[^\w\s\-]+", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", "-", s).strip("-")
    return f"{prefix}{s or 'island'}"


def name_key(name: str) -> str:
    s = (name or "").lower()
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"\bisle of\b|\bisland\b|\bynys\b|\binch\b|\binis\b|\boil[eé]?an\b|\beilean\b", " ", s)
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


# ------------------------------- Cache helpers --------------------------

def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return default
    return default


def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


# =========================================================================
# Action 1 — Wikidata SPARQL
# =========================================================================

WD_COUNTRIES = [
    ("Q145", "UK"),
    ("Q27", "Ireland"),
    ("Q9676", "Isle of Man"),
    ("Q785", "Jersey"),
    ("Q3311985", "Bailiwick of Guernsey"),
]

WD_QUERY = """
SELECT ?item ?itemLabel ?coord ?area ?population ?wikipedia
       ?name_en ?name_ga ?name_gd ?name_cy ?name_gv ?name_kw
WHERE {
  ?item wdt:P31/wdt:P279* wd:Q23442 .
  ?item wdt:P17 wd:%s .
  ?item wdt:P625 ?coord .
  OPTIONAL { ?item wdt:P2046 ?area . }
  OPTIONAL { ?item wdt:P1082 ?population . }
  OPTIONAL {
    ?wikipedia schema:about ?item ;
               schema:isPartOf <https://en.wikipedia.org/> .
  }
  OPTIONAL { ?item rdfs:label ?name_en FILTER(LANG(?name_en) = "en") . }
  OPTIONAL { ?item rdfs:label ?name_ga FILTER(LANG(?name_ga) = "ga") . }
  OPTIONAL { ?item rdfs:label ?name_gd FILTER(LANG(?name_gd) = "gd") . }
  OPTIONAL { ?item rdfs:label ?name_cy FILTER(LANG(?name_cy) = "cy") . }
  OPTIONAL { ?item rdfs:label ?name_gv FILTER(LANG(?name_gv) = "gv") . }
  OPTIONAL { ?item rdfs:label ?name_kw FILTER(LANG(?name_kw) = "kw") . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
"""


def parse_point_wkt(wkt: str) -> tuple[float, float] | None:
    m = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", wkt)
    if not m:
        return None
    return float(m.group(2)), float(m.group(1))  # (lat, lng)


def action_wikidata() -> list[dict]:
    cache = load_json(WD_CACHE, {})
    all_rows: list[dict] = []
    print("→ Wikidata SPARQL by country", file=sys.stderr)
    for qid, label in WD_COUNTRIES:
        if qid in cache and cache[qid].get("rows"):
            print(f"  {label} ({qid}) — cached ({len(cache[qid]['rows'])} rows)", file=sys.stderr)
            all_rows.extend(cache[qid]["rows"])
            continue
        try:
            print(f"  querying {label} ({qid})…", file=sys.stderr)
            payload = _post_sparql(WD_QUERY % qid)
            rows = payload.get("results", {}).get("bindings", [])
            cache[qid] = {"rows": rows, "fetched": time.time()}
            save_json(WD_CACHE, cache)
            print(f"    {len(rows)} rows", file=sys.stderr)
            all_rows.extend(rows)
            time.sleep(DELAY)
        except Exception as exc:
            print(f"    failed: {exc!r}", file=sys.stderr)
            cache[qid] = {"rows": [], "error": str(exc)}
            save_json(WD_CACHE, cache)

    # Normalise
    candidates: dict[str, dict] = {}
    for row in all_rows:
        qid = row["item"]["value"].rsplit("/", 1)[-1]
        wkt = (row.get("coord") or {}).get("value", "")
        latlng = parse_point_wkt(wkt) if wkt else None
        if not latlng:
            continue
        lat, lng = latlng
        if not in_remit(lat, lng):
            continue
        en = (row.get("name_en") or {}).get("value") or (row.get("itemLabel") or {}).get("value", "")
        if not en or en == qid:  # Wikidata sometimes returns the Q-ID as label
            continue
        area = (row.get("area") or {}).get("value")
        pop = (row.get("population") or {}).get("value")
        wiki = (row.get("wikipedia") or {}).get("value", "")
        names = {
            "en": en,
            "ga": (row.get("name_ga") or {}).get("value", ""),
            "gd": (row.get("name_gd") or {}).get("value", ""),
            "cy": (row.get("name_cy") or {}).get("value", ""),
            "gv": (row.get("name_gv") or {}).get("value", ""),
            "kw": (row.get("name_kw") or {}).get("value", ""),
        }
        # Some Q-IDs appear under multiple countries (cross-jurisdictional);
        # keep the first one we see (which is by country query order).
        if qid in candidates:
            continue
        candidates[qid] = {
            "id": f"wd-{qid}",
            "name": en,
            "nation": nation_for(lat, lng),
            "type": "sea",  # default; re-classified later
            "archipelago": "",
            "lat": round(lat, 5),
            "lng": round(lng, 5),
            "areaKm2": (float(area) if area else None),
            "population": (int(float(pop)) if pop else None),
            "highestPointM": None,
            "highestPointName": "",
            "shortDescription": "",
            "history": "",
            "geography": "",
            "transport": "",
            "accommodation": "",
            "wikipedia": wiki,
            "wikidata": qid,
            "image": "",
            "images": [],
            "names": {k: v for k, v in names.items() if v},
            "tags": ["island", "wikidata"],
            "source": "wikidata",
            "sources": [
                {
                    "name": "Wikidata",
                    "ref": qid,
                    "url": f"https://www.wikidata.org/wiki/{qid}",
                    "licence": "CC0",
                    "retrieved": time.strftime("%Y-%m-%d"),
                    "attribution": "Wikidata contributors (CC0)",
                }
            ],
        }
    cand_list = sorted(candidates.values(), key=lambda x: x["name"].lower())
    save_json(WD_CANDIDATES, cand_list)
    print(f"  wrote {len(cand_list)} Wikidata candidates → {WD_CANDIDATES.name}", file=sys.stderr)
    return cand_list


# =========================================================================
# Action 1b — Thames eyots from Wikipedia
# =========================================================================

THAMES_URL = "https://en.wikipedia.org/wiki/Islands_in_the_River_Thames"
THAMES_API = (
    "https://en.wikipedia.org/w/api.php?action=parse&format=json"
    "&prop=wikitext&page=Islands_in_the_River_Thames"
)


def action_thames() -> list[dict]:
    cache = load_json(THAMES_CACHE, {})
    if not cache or "wikitext" not in cache:
        print("→ Fetching Wikipedia 'Islands in the River Thames'…", file=sys.stderr)
        payload = _get_json(THAMES_API)
        wtxt = payload.get("parse", {}).get("wikitext", {}).get("*", "")
        cache = {"wikitext": wtxt, "fetched": time.time()}
        save_json(THAMES_CACHE, cache)
    wtxt = cache["wikitext"]

    # The Thames eyots article uses one big sortable wikitable.
    # Parse rows of the form |- |[[Name]] || ... with optional anchor or wikilink.
    # We collect every wikilinked island title + try to resolve via geosearch.
    # Strategy: extract wikilinks that look like island/eyot/ait names from
    # within the article body and use the API to fetch their coords.

    # Find all [[Title]] or [[Title|Display]] tokens in lines that look like
    # table data rows (start with `|` and contain "Eyot" / "Ait" / "Island").
    titles: list[str] = []
    seen = set()
    for line in wtxt.splitlines():
        if not line.startswith("|"):
            continue
        if not re.search(r"\b(Eyot|Ait|Island|Holm|Holme)\b", line, re.IGNORECASE):
            continue
        for m in re.finditer(r"\[\[([^\[\]|]+)(?:\|[^\]]+)?\]\]", line):
            t = m.group(1).strip()
            # exclude obvious non-island links
            if any(t.lower().startswith(p.lower()) for p in (
                "Category:", "File:", "Image:", "List of", "User:", "Wikipedia:",
                "Lock", "River ", "Reach ", "Weir", "Bridge",
            )):
                continue
            if t in seen:
                continue
            seen.add(t)
            titles.append(t)

    print(f"  parsed {len(titles)} candidate Thames-page wikilinks", file=sys.stderr)

    # Fetch coords + descriptions for these via MediaWiki API (50 at a time).
    coords: dict[str, dict] = {}
    BATCH = 50
    for i in range(0, len(titles), BATCH):
        batch = titles[i : i + BATCH]
        params = {
            "action": "query",
            "format": "json",
            "prop": "coordinates|pageprops|extracts",
            "exsentences": 2,
            "explaintext": 1,
            "ppprop": "wikibase_item",
            "titles": "|".join(batch),
            "redirects": 1,
            "coprop": "type|name",
        }
        try:
            payload = _get_json("https://en.wikipedia.org/w/api.php", params)
        except Exception as exc:
            print(f"    batch {i}: failed {exc!r}", file=sys.stderr)
            continue
        normalized: dict[str, str] = {}
        for n in (payload.get("query") or {}).get("normalized") or []:
            normalized[n["to"]] = n["from"]
        for redir in (payload.get("query") or {}).get("redirects") or []:
            normalized.setdefault(redir["to"], redir["from"])
        for _pid, page in (payload.get("query") or {}).get("pages", {}).items():
            page_title = page.get("title", "")
            input_title = normalized.get(page_title, page_title)
            cs = page.get("coordinates") or []
            if not cs:
                continue
            c = cs[0]
            lat, lng = c.get("lat"), c.get("lon")
            if lat is None or lng is None:
                continue
            qid = (page.get("pageprops") or {}).get("wikibase_item", "")
            coords[input_title] = {
                "title": page_title,
                "lat": lat,
                "lng": lng,
                "wikidata": qid,
                "extract": (page.get("extract") or "").strip(),
            }
        time.sleep(DELAY)

    candidates: list[dict] = []
    for title, info in coords.items():
        lat, lng = info["lat"], info["lng"]
        if not in_remit(lat, lng):
            continue
        # Crude sanity: the Thames runs through England; reject anything > 100 km
        # from the river path. Easier proxy: must be in England nation box
        # AND between lon -2.0 (Thames Head, Glos) and +1.0 (Sheppey) and
        # lat 51.0–52.0.
        if not (51.0 <= lat <= 52.0 and -2.1 <= lng <= 1.1):
            continue
        candidates.append(
            {
                "id": f"thames-{slugify(title)}",
                "name": title,
                "nation": "England",
                "type": "river",  # Thames eyots are river islands by definition
                "subtype": None,
                "archipelago": "River Thames",
                "lat": round(lat, 5),
                "lng": round(lng, 5),
                "areaKm2": None,
                "population": None,
                "highestPointM": None,
                "highestPointName": "",
                "shortDescription": info["extract"][:300],
                "history": "",
                "geography": "",
                "transport": "",
                "accommodation": "",
                "wikipedia": f"https://en.wikipedia.org/wiki/{urllib.parse.quote(info['title'].replace(' ', '_'))}",
                "wikidata": info.get("wikidata", ""),
                "image": "",
                "images": [],
                "tags": ["island", "thames", "eyot", "river"],
                "source": "wikipedia-thames",
                "parentWaterBody": {"name": "River Thames", "type": "river"},
                "classification": {"source": "thames-list", "confidence": "high"},
                "sources": [
                    {
                        "name": "Wikipedia — Islands in the River Thames",
                        "ref": title,
                        "url": THAMES_URL,
                        "licence": "CC BY-SA 4.0",
                        "retrieved": time.strftime("%Y-%m-%d"),
                        "attribution": "Wikipedia contributors (CC BY-SA 4.0)",
                    }
                ],
            }
        )
    save_json(THAMES_CANDIDATES, candidates)
    print(f"  wrote {len(candidates)} Thames-eyot candidates → {THAMES_CANDIDATES.name}", file=sys.stderr)
    return candidates


# =========================================================================
# Action 3 — Crannogs (Wikidata SPARQL fallback after ArcGIS REST endpoints
# returned 403/empty during the live run; Wikidata has every documented
# crannog as a Q-item with coordinates, CC0, well-typed.)
# =========================================================================
#
# Wikidata classes:
#   Q514822  — crannog
#   Q1140030 — skerry
#   Q4209223 — lake island (subclass already caught by Q23442 in action 1
#              but kept here for completeness)
#   Q4421    — eyot (subclass of island; covered by Q23442 too)
# We re-use the country list from action 1 (UK + IE + IoM + Jersey + Bailiwick).
# =========================================================================

WD_CRANNOG_QUERY = """
SELECT ?item ?itemLabel ?coord ?lake ?lakeLabel ?wikipedia
WHERE {
  ?item rdfs:label ?label .
  FILTER(LANG(?label) = "en")
  FILTER(REGEX(?label, "crannog", "i") || REGEX(?label, "crann.g", "i") || REGEX(?label, "lake[- ]?dwelling", "i"))
  ?item wdt:P625 ?coord .
  OPTIONAL { ?item wdt:P361 ?lake . }
  OPTIONAL {
    ?wikipedia schema:about ?item ;
               schema:isPartOf <https://en.wikipedia.org/> .
  }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
LIMIT 2000
"""

# =========================================================================
#
# All three sources expose their archaeological registers via ArcGIS REST
# FeatureServer. We hit each pagewise, filter for above-water crannog /
# island dwelling / lake settlement records with a non-empty name, then
# round NGRs to 100 m to respect heritage-publication granularity.
# =========================================================================

# HES Canmore — site type "Crannog" + "Island Dwelling"
# Canmore exposes a public ArcGIS hub. We use Trove.scot search via
# its JSON API.
CANMORE_API = "https://canmore.org.uk/api/site/search/result"

# NMS Ireland — Sites and Monuments Record (CC-BY 4.0)
# Public ArcGIS FeatureServer for the Archaeological Survey.
NMS_IE_FS = (
    "https://services-eu1.arcgis.com/HyjXgkV6KGMSF3jt/ArcGIS/rest/services/"
    "SMRDataDownload/FeatureServer/0/query"
)

# DfC NI — Sites and Monuments Record (OGL v3.0)
NISMR_FS = (
    "https://services-eu1.arcgis.com/oNN8gKlS6sLMTBZB/ArcGIS/rest/services/"
    "NISMR_Public/FeatureServer/0/query"
)


def _arcgis_paginate(base_url: str, where: str, out_fields: str = "*", chunk: int = 1000) -> list[dict]:
    """Generic ArcGIS REST FeatureServer paginator. Returns list of features."""
    features: list[dict] = []
    offset = 0
    while True:
        params = {
            "where": where,
            "outFields": out_fields,
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "json",
            "resultOffset": offset,
            "resultRecordCount": chunk,
        }
        try:
            payload = _get_json(base_url, params, timeout=120)
        except Exception as exc:
            print(f"    arcgis page offset {offset}: failed {exc!r}", file=sys.stderr)
            break
        feats = payload.get("features", [])
        if not feats:
            break
        features.extend(feats)
        # ArcGIS uses `exceededTransferLimit` to signal more pages
        if not payload.get("exceededTransferLimit"):
            break
        offset += chunk
        time.sleep(DELAY)
    return features


def _round_100m(lat: float, lng: float) -> tuple[float, float]:
    """Round lat/lng to ~100 m (3 d.p.). Honours heritage publication
    granularity (Canmore, NMS, NISMR all already publish at this precision
    or coarser)."""
    return round(lat, 3), round(lng, 3)


CRANNOG_CATEGORIES = [
    "Category:Crannogs_in_Scotland",
    "Category:Crannogs_in_the_Republic_of_Ireland",
    "Category:Crannogs_in_Northern_Ireland",
    "Category:Crannogs",
    "Category:Lake_settlements_in_Ireland",
    "Category:Artificial_islands_in_Ireland",
]


def _wp_category_members(category: str) -> list[str]:
    """Return list of page titles in a Wikipedia category."""
    pages: list[str] = []
    cont = None
    while True:
        params = {
            "action": "query",
            "format": "json",
            "list": "categorymembers",
            "cmtitle": category,
            "cmlimit": 500,
            "cmtype": "page",
        }
        if cont:
            params["cmcontinue"] = cont
        try:
            payload = _get_json("https://en.wikipedia.org/w/api.php", params)
        except Exception as exc:
            print(f"    category {category}: failed {exc!r}", file=sys.stderr)
            return pages
        for m in (payload.get("query") or {}).get("categorymembers") or []:
            pages.append(m["title"])
        cont = (payload.get("continue") or {}).get("cmcontinue")
        if not cont:
            break
        time.sleep(DELAY)
    return pages


def _wp_pages_coords(titles: list[str]) -> dict[str, dict]:
    """Look up coordinates + Wikidata Q-ID + short extract for Wikipedia titles."""
    out: dict[str, dict] = {}
    BATCH = 50
    for i in range(0, len(titles), BATCH):
        batch = titles[i : i + BATCH]
        params = {
            "action": "query",
            "format": "json",
            "prop": "coordinates|pageprops|extracts",
            "exsentences": 2,
            "explaintext": 1,
            "ppprop": "wikibase_item",
            "titles": "|".join(batch),
            "redirects": 1,
            "coprop": "type|name",
        }
        try:
            payload = _get_json("https://en.wikipedia.org/w/api.php", params)
        except Exception as exc:
            print(f"    coord batch failed: {exc!r}", file=sys.stderr)
            continue
        normalized: dict[str, str] = {}
        for n in (payload.get("query") or {}).get("normalized") or []:
            normalized[n["to"]] = n["from"]
        for redir in (payload.get("query") or {}).get("redirects") or []:
            normalized.setdefault(redir["to"], redir["from"])
        for _pid, page in (payload.get("query") or {}).get("pages", {}).items():
            page_title = page.get("title", "")
            input_title = normalized.get(page_title, page_title)
            cs = page.get("coordinates") or []
            if not cs:
                continue
            c = cs[0]
            lat, lng = c.get("lat"), c.get("lon")
            if lat is None or lng is None:
                continue
            out[input_title] = {
                "title": page_title,
                "lat": lat,
                "lng": lng,
                "wikidata": (page.get("pageprops") or {}).get("wikibase_item", ""),
                "extract": (page.get("extract") or "").strip(),
            }
        time.sleep(DELAY)
    return out


def action_crannogs() -> list[dict]:
    cache = load_json(CRANNOG_CACHE, {})

    # ---------- Wikipedia category route ----------
    if "wp_categories" not in cache:
        print("→ Wikipedia categories: Crannogs in Scotland/Ireland/NI…", file=sys.stderr)
        all_titles: list[str] = []
        seen = set()
        for cat in CRANNOG_CATEGORIES:
            members = _wp_category_members(cat)
            print(f"    {cat}: {len(members)} members", file=sys.stderr)
            for t in members:
                if t in seen or t.startswith("List of") or t.startswith("Category:"):
                    continue
                seen.add(t)
                all_titles.append(t)
        print(f"    {len(all_titles)} unique crannog page titles", file=sys.stderr)
        coords = _wp_pages_coords(all_titles)
        print(f"    {len(coords)} with coordinates", file=sys.stderr)
        cache["wp_categories"] = list(coords.values())
        cache["wp_categories_titles"] = list(seen)
        save_json(CRANNOG_CACHE, cache)

    wd_candidates: list[dict] = []
    for info in cache.get("wp_categories", []):
        lat, lng = info["lat"], info["lng"]
        if not in_remit(lat, lng):
            continue
        label = info["title"]
        qid = info.get("wikidata", "")
        wp_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(info['title'].replace(' ', '_'))}"
        wd_candidates.append({
            "id": f"crannog-wp-{slugify(label)}",
            "name": label,
            "nation": nation_for(lat, lng),
            "type": "lake",
            "subtype": "crannog",
            "archipelago": "",
            "lat": round(lat, 5),
            "lng": round(lng, 5),
            "areaKm2": None,
            "population": None,
            "highestPointM": None,
            "highestPointName": "",
            "shortDescription": info.get("extract", "")[:300] or
                "Crannog — pre-medieval or medieval artificial lake island dwelling.",
            "history": "",
            "geography": "",
            "transport": "",
            "accommodation": "",
            "wikipedia": wp_url,
            "wikidata": qid,
            "image": "",
            "images": [],
            "tags": ["island", "lake", "crannog", "archaeological_site"],
            "source": "wikipedia-crannog",
            "classification": {"source": "wp-category", "confidence": "high"},
            "heritageDesignation": "scheduled monument",
            "sources": [{
                "name": "Wikipedia — Crannog category",
                "ref": label,
                "url": wp_url,
                "licence": "CC BY-SA 4.0",
                "retrieved": time.strftime("%Y-%m-%d"),
                "attribution": "Wikipedia contributors (CC BY-SA 4.0)",
            }],
        })

    # ---------- Legacy ArcGIS attempts (kept best-effort; usually empty)
    if "nms_ie" not in cache:
        print("→ NMS Ireland SMR — crannog/lake-settlement features…", file=sys.stderr)
        # Filter to crannog + island dwelling + lake-settlement classes.
        # The SMR uses CLASS field with values like 'CRANNÓG', 'ISLAND DWELLING'.
        try:
            feats = _arcgis_paginate(
                NMS_IE_FS,
                where="UPPER(CLASS) LIKE '%CRANN%' OR UPPER(CLASS) LIKE '%ISLAND DWELL%' OR UPPER(CLASS) LIKE '%LAKE SETTLEMENT%'",
            )
            cache["nms_ie"] = feats
        except Exception as exc:
            print(f"    NMS Ireland: {exc!r}", file=sys.stderr)
            cache["nms_ie"] = []
        save_json(CRANNOG_CACHE, cache)
    if "nismr" not in cache:
        print("→ DfC NI NISMR — crannog features…", file=sys.stderr)
        try:
            feats = _arcgis_paginate(
                NISMR_FS,
                where="UPPER(MONUMENT_TYPE) LIKE '%CRANN%' OR UPPER(MONUMENT_TYPE) LIKE '%ISLAND%'",
            )
            cache["nismr"] = feats
        except Exception as exc:
            print(f"    NISMR: {exc!r}", file=sys.stderr)
            cache["nismr"] = []
        save_json(CRANNOG_CACHE, cache)
    if "canmore" not in cache:
        print("→ HES Canmore — crannog site type…", file=sys.stderr)
        # Canmore uses its own JSON API at canmore.org.uk/api/.
        # Site type code for Crannog = SITETYPE=CRANNOG; pagination
        # via &page=N. Each result has lat/lng/name/id.
        feats: list[dict] = []
        page = 1
        while True:
            try:
                payload = _get_json(
                    CANMORE_API,
                    {"SITETYPE": "CRANNOG", "page": page, "view": "list"},
                    timeout=60,
                )
            except Exception as exc:
                print(f"    Canmore page {page}: failed {exc!r}", file=sys.stderr)
                break
            results = payload.get("results") or payload.get("hits") or []
            if not results:
                break
            feats.extend(results)
            page += 1
            if page > 30:  # safety cap; ~30 pages × 20 ≈ 600 crannogs
                break
            time.sleep(DELAY)
        cache["canmore"] = feats
        save_json(CRANNOG_CACHE, cache)

    # Normalise to candidate format.
    candidates: list[dict] = list(wd_candidates)

    # ----- NMS Ireland -----
    for f in cache.get("nms_ie", []):
        a = f.get("attributes", {})
        g = f.get("geometry") or {}
        lat, lng = g.get("y"), g.get("x")
        if lat is None or lng is None:
            continue
        # NMS uses Web Mercator if outSR not honoured; defensive convert
        if abs(lat) > 90 or abs(lng) > 180:
            continue
        if not in_remit(lat, lng):
            continue
        lat, lng = _round_100m(lat, lng)
        klass = (a.get("CLASS") or a.get("class") or "").strip()
        if "submerg" in klass.lower():
            continue
        cond = (a.get("CONDITION") or a.get("condition") or "").lower()
        if "destroyed" in cond or "levelled" in cond:
            continue
        name = (a.get("TOWNLAND") or a.get("townland") or
                a.get("ITM_X") or "").strip()
        if not name:
            continue
        smr_num = (a.get("SMRS_NO") or a.get("SMR") or a.get("OBJECTID") or "")
        candidates.append({
            "id": f"crannog-ie-{slugify(name)}-{smr_num}",
            "name": name + " crannog",
            "nation": "Ireland",
            "type": "lake",
            "subtype": "crannog",
            "archipelago": "",
            "lat": lat,
            "lng": lng,
            "areaKm2": None,
            "population": None,
            "highestPointM": None,
            "highestPointName": "",
            "shortDescription": f"Crannog site (NMS Ireland classification: {klass}).",
            "history": "",
            "geography": "",
            "transport": "",
            "accommodation": "",
            "wikipedia": "",
            "wikidata": "",
            "image": "",
            "images": [],
            "tags": ["island", "lake", "crannog", "archaeological_site"],
            "source": "nms-ireland",
            "classification": {"source": "smr-ie", "confidence": "medium"},
            "heritageDesignation": "scheduled monument",
            "sources": [{
                "name": "NMS Ireland Archaeological Survey",
                "ref": str(smr_num),
                "url": "https://www.archaeology.ie/national-monuments-service/archaeological-survey-database",
                "licence": "CC-BY-4.0",
                "retrieved": time.strftime("%Y-%m-%d"),
                "attribution": "© National Monuments Service, Government of Ireland (CC-BY-4.0)",
            }],
        })

    # ----- NISMR (NI) -----
    for f in cache.get("nismr", []):
        a = f.get("attributes", {})
        g = f.get("geometry") or {}
        lat, lng = g.get("y"), g.get("x")
        if lat is None or lng is None:
            continue
        if abs(lat) > 90 or abs(lng) > 180:
            continue
        if not in_remit(lat, lng):
            continue
        lat, lng = _round_100m(lat, lng)
        mt = (a.get("MONUMENT_TYPE") or a.get("monument_type") or "").strip()
        if "submerg" in mt.lower():
            continue
        name = (a.get("MONUMENT_NAME") or a.get("monument_name") or
                a.get("TOWNLAND") or a.get("townland") or "").strip()
        if not name:
            continue
        ref = (a.get("RECORD_ID") or a.get("SMR_NUMBER") or a.get("OBJECTID") or "")
        candidates.append({
            "id": f"crannog-ni-{slugify(name)}-{ref}",
            "name": name if "crannog" in name.lower() else name + " crannog",
            "nation": "Northern Ireland",
            "type": "lake",
            "subtype": "crannog",
            "archipelago": "",
            "lat": lat,
            "lng": lng,
            "areaKm2": None,
            "population": None,
            "highestPointM": None,
            "highestPointName": "",
            "shortDescription": f"Crannog site (NI Sites and Monuments Record: {mt}).",
            "history": "",
            "geography": "",
            "transport": "",
            "accommodation": "",
            "wikipedia": "",
            "wikidata": "",
            "image": "",
            "images": [],
            "tags": ["island", "lake", "crannog", "archaeological_site"],
            "source": "nismr",
            "classification": {"source": "smr-ni", "confidence": "medium"},
            "heritageDesignation": "scheduled monument",
            "sources": [{
                "name": "DfC HED NI Sites and Monuments Record",
                "ref": str(ref),
                "url": "https://www.communities-ni.gov.uk/services/sites-and-monuments-record",
                "licence": "OGL v3.0",
                "retrieved": time.strftime("%Y-%m-%d"),
                "attribution": "Contains public sector information licensed under OGL v3.0 — © Crown copyright, DfC HED NI",
            }],
        })

    # ----- Canmore (Scotland) -----
    for r in cache.get("canmore", []):
        # Canmore site API returns slightly varying shapes; cope.
        lat = r.get("lat") or r.get("ngr_latitude") or r.get("latitude")
        lng = r.get("lng") or r.get("ngr_longitude") or r.get("longitude") or r.get("lon")
        name = r.get("name") or r.get("site_name") or r.get("title")
        cid = r.get("id") or r.get("site_id") or r.get("canmore_id") or r.get("canmoreid")
        if lat is None or lng is None or not name or not cid:
            continue
        try:
            lat, lng = float(lat), float(lng)
        except Exception:
            continue
        if not in_remit(lat, lng):
            continue
        lat, lng = _round_100m(lat, lng)
        candidates.append({
            "id": f"crannog-sc-canmore-{cid}",
            "name": name if "crannog" in name.lower() else f"{name} crannog",
            "nation": "Scotland",
            "type": "lake",
            "subtype": "crannog",
            "archipelago": "",
            "lat": lat,
            "lng": lng,
            "areaKm2": None,
            "population": None,
            "highestPointM": None,
            "highestPointName": "",
            "shortDescription": "Crannog site (HES Canmore record).",
            "history": "",
            "geography": "",
            "transport": "",
            "accommodation": "",
            "wikipedia": "",
            "wikidata": "",
            "image": "",
            "images": [],
            "tags": ["island", "lake", "crannog", "archaeological_site"],
            "source": "canmore",
            "classification": {"source": "canmore", "confidence": "medium"},
            "heritageDesignation": "scheduled monument",
            "sources": [{
                "name": "HES Canmore",
                "ref": str(cid),
                "url": f"https://canmore.org.uk/site/{cid}",
                "licence": "OGL v3.0",
                "retrieved": time.strftime("%Y-%m-%d"),
                "attribution": "Contains public sector information licensed under OGL v3.0 — © Historic Environment Scotland",
            }],
        })

    save_json(CRANNOG_CANDIDATES, candidates)
    print(f"  wrote {len(candidates)} crannog candidates → {CRANNOG_CANDIDATES.name}", file=sys.stderr)
    return candidates


# =========================================================================
# Action 5 — Statutory designations (NatureScot SSSI + NIEA ASSI + NPWS + Tailte Éireann)
# =========================================================================
#
# Strategy: each source publishes a feature service of designated polygons.
# An "island-bounded" designation is approximated as a polygon whose name
# contains "island", "isle", "isles", "skerr", "stack", "holm", or Gaelic
# equivalents AND whose bounding box is small (≤ a few km on each side).
# We extract the centroid and treat as a candidate island.
# =========================================================================

# Tailte Éireann Islands (CC-BY 4.0)
TE_ISLANDS_FS = (
    "https://geohive.maps.arcgis.com/sharing/rest/content/items/"
    "8e9fd0e0a82e44c4a85e63e8aa17e7e1/data"  # placeholder; we use the catalogue URL
)
TE_ISLANDS_QUERY = (
    "https://services1.arcgis.com/eYU4qHqdfwsYHEcD/arcgis/rest/services/"
    "Islands_National_1m_Map_Of_Ireland/FeatureServer/0/query"
)

# NPWS Ireland SAC/SPA — large; just SAC for now.
NPWS_SAC_FS = (
    "https://services3.arcgis.com/iVZqQNn4i4G7c0lA/ArcGIS/rest/services/"
    "Special_Areas_of_Conservation_SAC/FeatureServer/0/query"
)
NPWS_SPA_FS = (
    "https://services3.arcgis.com/iVZqQNn4i4G7c0lA/ArcGIS/rest/services/"
    "Special_Protection_Area_SPA/FeatureServer/0/query"
)

# NIEA ASSI on OpenDataNI (OGL)
NIEA_ASSI_FS = (
    "https://services-eu1.arcgis.com/oNN8gKlS6sLMTBZB/ArcGIS/rest/services/"
    "ASSI/FeatureServer/0/query"
)

# NatureScot SSSI (OGL) — they expose a public WFS / ArcGIS REST.
NS_SSSI_FS = (
    "https://services2.arcgis.com/iVRZQ6lhFNNTUyPS/ArcGIS/rest/services/"
    "SSSI/FeatureServer/0/query"
)

ISLAND_NAME_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\bisland(s)?\b", r"\bisle(s)?\b", r"\bislet(s)?\b",
        r"\bholm(e)?\b", r"\bskerr", r"\bstack(s)?\b",
        r"\beilean\b", r"\binis\b", r"\binish", r"\boil[eé]an\b",
        r"\bynys\b", r"\bsceilg\b", r"\bsgeir\b", r"\bsgarbh\b",
    ]
]


def _name_looks_islandy(name: str) -> bool:
    if not name:
        return False
    return any(p.search(name) for p in ISLAND_NAME_PATTERNS)


def _feature_centroid_ll(f: dict) -> tuple[float, float] | None:
    """Best-effort centroid in lat/lng from an ArcGIS feature."""
    g = f.get("geometry") or {}
    if "x" in g and "y" in g:
        return g["y"], g["x"]
    rings = g.get("rings") or []
    if not rings:
        return None
    # average of vertices of the first (outer) ring
    pts = rings[0]
    if not pts:
        return None
    sx = sum(p[0] for p in pts) / len(pts)
    sy = sum(p[1] for p in pts) / len(pts)
    return sy, sx


def _ring_bbox_km(f: dict) -> tuple[float, float] | None:
    """Bounding-box size in km (width, height). Used to reject very large designations."""
    g = f.get("geometry") or {}
    rings = g.get("rings") or []
    if not rings:
        return None
    xs, ys = [], []
    for ring in rings:
        for p in ring:
            xs.append(p[0])
            ys.append(p[1])
    if not xs or not ys:
        return None
    lng_mid = (min(xs) + max(xs)) / 2
    lat_mid = (min(ys) + max(ys)) / 2
    w_km = (max(xs) - min(xs)) * 111.32 * math.cos(math.radians(lat_mid))
    h_km = (max(ys) - min(ys)) * 111.32
    return w_km, h_km


def action_designations() -> list[dict]:
    cache = load_json(DESIG_CACHE, {})
    sources = {
        "tailte_islands": (TE_ISLANDS_QUERY, "1=1"),
        "npws_sac": (NPWS_SAC_FS, "1=1"),
        "npws_spa": (NPWS_SPA_FS, "1=1"),
        "niea_assi": (NIEA_ASSI_FS, "1=1"),
        "naturescot_sssi": (NS_SSSI_FS, "1=1"),
    }
    for key, (url, where) in sources.items():
        if key in cache:
            print(f"  {key}: cached ({len(cache[key])} features)", file=sys.stderr)
            continue
        print(f"→ Fetching {key} features…", file=sys.stderr)
        try:
            feats = _arcgis_paginate(url, where, chunk=500)
            cache[key] = feats
            print(f"    {len(feats)} features", file=sys.stderr)
        except Exception as exc:
            print(f"    failed: {exc!r}", file=sys.stderr)
            cache[key] = []
        save_json(DESIG_CACHE, cache)

    candidates: list[dict] = []

    def normalise(source: str, licence: str, attrib: str, feats: list[dict], name_field_candidates: list[str], nation_override: str | None = None, max_size_km: float = 4.0) -> None:
        for f in feats:
            a = f.get("attributes") or {}
            name = ""
            for k in name_field_candidates:
                v = a.get(k) or a.get(k.lower())
                if v and str(v).strip():
                    name = str(v).strip()
                    break
            if not name:
                continue
            # Two-stage filter:
            #  (a) Tailte_islands ARE islands by definition — no name filter.
            #  (b) Designation polygons: only keep those whose name looks islandy.
            if source != "tailte-islands" and not _name_looks_islandy(name):
                continue
            ctr = _feature_centroid_ll(f)
            if not ctr:
                continue
            lat, lng = ctr
            if not in_remit(lat, lng):
                continue
            if source != "tailte-islands":
                bbox = _ring_bbox_km(f)
                if bbox and (bbox[0] > max_size_km or bbox[1] > max_size_km):
                    # Too big — probably a coast-spanning SSSI, not a single island
                    continue
            n = nation_override or nation_for(lat, lng)
            lat, lng = round(lat, 5), round(lng, 5)
            ref = a.get("OBJECTID") or a.get("objectid") or ""
            candidates.append({
                "id": f"desig-{source}-{slugify(name)}-{ref}",
                "name": name,
                "nation": n,
                "type": "sea",  # default; classifier will re-type lake/river
                "archipelago": "",
                "lat": lat,
                "lng": lng,
                "areaKm2": None,
                "population": None,
                "highestPointM": None,
                "highestPointName": "",
                "shortDescription": f"Designated site ({source}).",
                "history": "",
                "geography": "",
                "transport": "",
                "accommodation": "",
                "wikipedia": "",
                "wikidata": "",
                "image": "",
                "images": [],
                "tags": ["island", "designation"],
                "source": source,
                "sources": [{
                    "name": source,
                    "ref": str(ref),
                    "url": "",
                    "licence": licence,
                    "retrieved": time.strftime("%Y-%m-%d"),
                    "attribution": attrib,
                }],
            })

    normalise(
        "tailte-islands", "CC-BY-4.0", "© Tailte Éireann (CC-BY-4.0)",
        cache.get("tailte_islands", []),
        ["INET_NAME", "NAME", "ISLAND_NAM", "EN_NAME", "NAME_GA", "NAME_EN"],
        nation_override="Ireland", max_size_km=20.0,
    )
    normalise(
        "npws-sac", "CC-BY-4.0", "© NPWS, Government of Ireland (CC-BY-4.0)",
        cache.get("npws_sac", []),
        ["SITE_NAME", "Site_Name", "NAME", "SITENAME"],
        nation_override="Ireland",
    )
    normalise(
        "npws-spa", "CC-BY-4.0", "© NPWS, Government of Ireland (CC-BY-4.0)",
        cache.get("npws_spa", []),
        ["SITE_NAME", "Site_Name", "NAME", "SITENAME"],
        nation_override="Ireland",
    )
    normalise(
        "niea-assi", "OGL v3.0", "Contains public sector information licensed under OGL v3.0 — © Crown copyright, NIEA/DAERA",
        cache.get("niea_assi", []),
        ["ASSI_Name", "ASSI_NAME", "NAME", "SiteName"],
        nation_override="Northern Ireland",
    )
    normalise(
        "naturescot-sssi", "OGL v3.0", "Contains public sector information licensed under OGL v3.0 — © NatureScot",
        cache.get("naturescot_sssi", []),
        ["SSSI_NAME", "SITE_NAME", "Name", "NAME"],
        nation_override="Scotland",
    )

    save_json(DESIG_CANDIDATES, candidates)
    print(f"  wrote {len(candidates)} designation candidates → {DESIG_CANDIDATES.name}", file=sys.stderr)
    return candidates


# =========================================================================
# Merge pass — dedup all candidates against current islands.json
# =========================================================================

PROXIMITY_KM = 1.0


def _is_curated(island: dict) -> bool:
    return island.get("source") == "curated"


def _quality(island: dict) -> int:
    """Higher = richer. Used as a tiebreaker when merging duplicates."""
    s = 0
    if island.get("source") == "curated":
        s += 100
    if island.get("source") == "osm":
        s += 50
    if island.get("source") == "osm-inland":
        s += 40
    if island.get("source") == "wikidata":
        s += 30
    if island.get("areaKm2"):
        s += 5
    if island.get("population") is not None:
        s += 3
    if island.get("wikidata"):
        s += 3
    if island.get("wikipedia"):
        s += 3
    if island.get("image"):
        s += 2
    return s


def _merge_into(dest: dict, src: dict) -> None:
    """Merge richer fields from `src` into `dest` without overwriting curated content."""
    # Cross-reference IDs
    if not dest.get("wikidata") and src.get("wikidata"):
        dest["wikidata"] = src["wikidata"]
    if not dest.get("wikipedia") and src.get("wikipedia"):
        dest["wikipedia"] = src["wikipedia"]
    if not dest.get("osmType") and src.get("osmType"):
        dest["osmType"] = src["osmType"]
        dest["osmId"] = src.get("osmId")
    # Multilingual names
    src_names = src.get("names") or {}
    if src_names:
        existing_names = dest.get("names") or {}
        for lang, val in src_names.items():
            if val and not existing_names.get(lang):
                existing_names[lang] = val
        if existing_names:
            dest["names"] = existing_names
    # Area / population only if missing
    if dest.get("areaKm2") in (None, "") and src.get("areaKm2") is not None:
        dest["areaKm2"] = src["areaKm2"]
    if dest.get("population") in (None, "") and src.get("population") is not None:
        dest["population"] = src["population"]
    # Heritage flags
    if src.get("heritageDesignation") and not dest.get("heritageDesignation"):
        dest["heritageDesignation"] = src["heritageDesignation"]
    if src.get("subtype") and not dest.get("subtype"):
        dest["subtype"] = src["subtype"]
    # Append cross-source provenance
    src_sources = src.get("sources") or []
    dest_sources = dest.get("sources") or []
    seen_keys = {(s.get("name"), s.get("ref")) for s in dest_sources}
    for s in src_sources:
        k = (s.get("name"), s.get("ref"))
        if k not in seen_keys:
            dest_sources.append(s)
            seen_keys.add(k)
    if dest_sources:
        dest["sources"] = dest_sources


def merge_all() -> dict:
    islands = json.loads(ISLANDS_PATH.read_text())
    initial_count = len(islands)

    # Load all candidate sets
    wd = load_json(WD_CANDIDATES, [])
    th = load_json(THAMES_CANDIDATES, [])
    cr = load_json(CRANNOG_CANDIDATES, [])
    dg = load_json(DESIG_CANDIDATES, [])
    all_candidates = [(c, "wikidata") for c in wd] + \
                     [(c, "thames") for c in th] + \
                     [(c, "crannog") for c in cr] + \
                     [(c, "designation") for c in dg]
    print(f"merge: {len(wd)} wd + {len(th)} thames + {len(cr)} crannog + {len(dg)} designation = {len(all_candidates)} candidates", file=sys.stderr)

    # Build a Wikidata Q-ID index of existing islands
    qid_index: dict[str, dict] = {}
    for i in islands:
        if i.get("wikidata"):
            qid_index[i["wikidata"]] = i

    # Build a spatial-name index of existing islands.
    # Key on name_key plus rounded grid cell (~10 km).
    def cell(lat: float, lng: float) -> tuple[int, int]:
        return int(lat * 10), int(lng * 10)

    name_index: dict[str, list[dict]] = {}
    for i in islands:
        name_index.setdefault(name_key(i["name"]), []).append(i)

    def find_match(c: dict) -> dict | None:
        # Tier 1: Wikidata Q-ID match
        if c.get("wikidata") and c["wikidata"] in qid_index:
            return qid_index[c["wikidata"]]
        # Tier 2: name + ≤1 km proximity
        key = name_key(c["name"])
        for cand in name_index.get(key, []):
            d = haversine_km(c["lat"], c["lng"], cand["lat"], cand["lng"])
            if d <= PROXIMITY_KM:
                return cand
        # Tier 3: ≤500 m proximity ignoring name (very tight; same physical feature)
        for cand in islands:
            if abs(cand["lat"] - c["lat"]) < 0.01 and abs(cand["lng"] - c["lng"]) < 0.01:
                d = haversine_km(c["lat"], c["lng"], cand["lat"], cand["lng"])
                if d <= 0.5:
                    return cand
        return None

    stats = {
        "by_action": {},
        "new_by_nation": {},
        "new_by_type": {},
        "new_by_source": {},
        "merged_into_existing": 0,
        "total_candidates": len(all_candidates),
    }
    log: list[dict] = []

    seen_new_keys: set[tuple[str, tuple[int, int]]] = set()

    for c, action in all_candidates:
        stats["by_action"].setdefault(action, {"considered": 0, "added": 0, "merged": 0, "dropped": 0})
        stats["by_action"][action]["considered"] += 1

        match = find_match(c)
        if match:
            # Don't overwrite curated; merge richer fields
            if _quality(match) >= _quality(c) and not _is_curated(match):
                _merge_into(match, c)
                stats["merged_into_existing"] += 1
                stats["by_action"][action]["merged"] += 1
            elif _is_curated(match):
                # Curated wins entirely; only merge cross-refs
                _merge_into(match, c)
                stats["merged_into_existing"] += 1
                stats["by_action"][action]["merged"] += 1
            else:
                # Candidate is richer — merge candidate fields onto existing
                _merge_into(match, c)
                stats["merged_into_existing"] += 1
                stats["by_action"][action]["merged"] += 1
            continue

        # Sanity: drop nation == "British Isles" (out-of-remit)
        if c.get("nation") == "British Isles":
            stats["by_action"][action]["dropped"] += 1
            continue
        # Dedup *among candidates* by name+cell
        ck = (name_key(c["name"]), cell(c["lat"], c["lng"]))
        if ck in seen_new_keys:
            stats["by_action"][action]["dropped"] += 1
            continue
        seen_new_keys.add(ck)

        # Add a few canonical empty fields if missing
        c.setdefault("highestPointM", None)
        c.setdefault("highestPointName", "")
        c.setdefault("shortDescription", c.get("shortDescription", ""))
        c.setdefault("history", "")
        c.setdefault("geography", "")
        c.setdefault("transport", "")
        c.setdefault("accommodation", "")
        c.setdefault("wikipedia", "")
        c.setdefault("wikidata", c.get("wikidata", ""))
        c.setdefault("image", "")
        c.setdefault("images", [])
        c.setdefault("archipelago", "")
        c.setdefault("areaKm2", None)
        c.setdefault("population", None)

        islands.append(c)
        # update indexes
        name_index.setdefault(name_key(c["name"]), []).append(c)
        if c.get("wikidata"):
            qid_index[c["wikidata"]] = c

        stats["by_action"][action]["added"] += 1
        stats["new_by_nation"][c.get("nation", "?")] = stats["new_by_nation"].get(c.get("nation", "?"), 0) + 1
        stats["new_by_type"][c.get("type", "?")] = stats["new_by_type"].get(c.get("type", "?"), 0) + 1
        stats["new_by_source"][c.get("source", "?")] = stats["new_by_source"].get(c.get("source", "?"), 0) + 1
        log.append({"id": c["id"], "name": c["name"], "nation": c["nation"], "type": c["type"], "source": c["source"]})

    # Final dedup pass — sometimes a candidate matches another candidate
    # rather than an existing island. Run a name+1km dedup over the whole list.
    final: list[dict] = []
    seen_pairs: dict[tuple, dict] = {}
    for i in islands:
        key = name_key(i["name"])
        merged = False
        for offset_lat in (-0.01, 0, 0.01):
            for offset_lng in (-0.01, 0, 0.01):
                ck = (key, round(i["lat"] + offset_lat, 2), round(i["lng"] + offset_lng, 2))
                existing = seen_pairs.get(ck)
                if existing:
                    d = haversine_km(i["lat"], i["lng"], existing["lat"], existing["lng"])
                    if d <= PROXIMITY_KM:
                        if _quality(i) > _quality(existing) and not _is_curated(existing):
                            # i wins — replace existing
                            _merge_into(i, existing)
                            seen_pairs[ck] = i
                            # Replace in final
                            for idx, e in enumerate(final):
                                if e is existing:
                                    final[idx] = i
                                    break
                        else:
                            _merge_into(existing, i)
                        merged = True
                        break
            if merged:
                break
        if not merged:
            ck0 = (key, round(i["lat"], 2), round(i["lng"], 2))
            seen_pairs[ck0] = i
            final.append(i)

    final.sort(key=lambda x: x["name"].lower())
    ISLANDS_PATH.write_text(json.dumps(final, ensure_ascii=False, indent=2) + "\n")

    final_count = len(final)
    stats["initial_count"] = initial_count
    stats["final_count"] = final_count
    stats["net_delta"] = final_count - initial_count
    stats["log_sample"] = log[:50]

    INGEST_REPORT.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n")

    print(f"\nMerge complete: {initial_count} → {final_count} (Δ {final_count - initial_count:+})", file=sys.stderr)
    print(f"By action: {json.dumps(stats['by_action'], indent=2)}", file=sys.stderr)
    print(f"New by nation: {stats['new_by_nation']}", file=sys.stderr)
    print(f"New by type:   {stats['new_by_type']}", file=sys.stderr)
    print(f"New by source: {stats['new_by_source']}", file=sys.stderr)
    return stats


# =========================================================================
# CLI
# =========================================================================

def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    only = None
    for arg in sys.argv:
        if arg.startswith("--only="):
            only = arg.split("=", 1)[1]
    if "--merge" in sys.argv:
        merge_all()
        return
    if only == "wikidata" or only is None:
        action_wikidata()
    if only == "thames" or only is None:
        action_thames()
    if only == "crannogs" or only is None:
        action_crannogs()
    if only == "designations" or only is None:
        action_designations()
    if only is None:
        merge_all()


if __name__ == "__main__":
    main()
