"""Shared helpers for the island discovery pipeline."""

from __future__ import annotations

import json
import math
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
ISLANDS_PATH = DATA / "islands.json"
DISCOVERY_DIR = DATA / "discovery"

SCAN_PATH = DISCOVERY_DIR / "candidates_scan.json"
CATALOG_PATH = DISCOVERY_DIR / "candidates_catalog.json"
VERIFY_PATH = DISCOVERY_DIR / "verification.json"
PHOTOS_PATH = DISCOVERY_DIR / "photos.json"
ENRICH_PATH = DISCOVERY_DIR / "enrichment.json"
REVIEW_PATH = DISCOVERY_DIR / "review_report.json"

CACHE_OSM = DATA / "cache_discovery_osm.json"
CACHE_WD = DATA / "cache_discovery_wikidata.json"
CACHE_COMMONS = DATA / "cache_discovery_commons.json"
CACHE_WP_LISTS = DATA / "cache_discovery_wikipedia_lists.json"
OPEN_NAMES_PATH = DATA / "raw" / "os_opennames.csv"

USER_AGENT = (
    "isles-of-britain/0.9 (discovery-pipeline; static-site; "
    "https://github.com/local-atlas/isles-of-britain)"
)
DELAY_S = 0.15
PROXIMITY_KM = 1.0
UK_BBOX = (49.0, -10.5, 61.5, 2.5)

OVERPASS_ENDPOINTS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
]

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

OPEN_LICENSES = {
    "cc0",
    "cc0-1.0",
    "cc-by",
    "cc-by-2.0",
    "cc-by-2.5",
    "cc-by-3.0",
    "cc-by-4.0",
    "cc-by-sa",
    "cc-by-sa-2.0",
    "cc-by-sa-2.5",
    "cc-by-sa-3.0",
    "cc-by-sa-4.0",
    "public domain",
    "pd",
    "odbl",
    "ogl",
    "ogl v3.0",
    "ogl-3.0",
}


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _open(req: urllib.request.Request, timeout: int = 90) -> bytes:
    last: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last = exc
            sleep = (1.5**attempt) + random.random() * 0.4
            if isinstance(exc, urllib.error.HTTPError) and exc.code == 429:
                sleep = max(sleep, 5)
            time.sleep(sleep)
    raise RuntimeError(f"HTTP failed after retries: {last}")


def get_json(url: str, params: dict[str, Any] | None = None, timeout: int = 90) -> dict:
    qs = urllib.parse.urlencode(params or {}, safe=":/?&=,")
    full = url + ("?" + qs if qs else "")
    req = urllib.request.Request(
        full,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    return json.loads(_open(req, timeout))


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
    return json.loads(_open(req, timeout=180))


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
    raise RuntimeError(f"All Overpass endpoints failed: {last}")


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
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def slugify(name: str, prefix: str = "") -> str:
    s = (name or "island").lower()
    s = re.sub(r"[^\w\s\-]+", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", "-", s).strip("-")
    return f"{prefix}{s or 'island'}"


def name_key(name: str) -> str:
    s = (name or "").lower()
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(
        r"\bisle of\b|\bisland\b|\bynys\b|\binch\b|\binis\b|\boil[eé]?an\b|\beilean\b",
        " ",
        s,
    )
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


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
    for key in ("name:en", "name", "official_name", "alt_name", "loc_name"):
        value = (tags.get(key) or "").strip()
        if value:
            return value
    return ""


def license_ok(license_name: str | None) -> bool:
    if not license_name:
        return False
    norm = license_name.strip().lower()
    if not norm or norm in {"unknown", "n/a", "none", "copyrighted"}:
        return False
    return any(token in norm for token in OPEN_LICENSES)


def is_curated(island: dict) -> bool:
    return island.get("source") == "curated"


def quality_score(island: dict) -> int:
    score = 0
    if island.get("source") == "curated":
        score += 100
    if island.get("areaKm2"):
        score += 5
    if island.get("population") is not None:
        score += 3
    if island.get("wikidata"):
        score += 3
    if island.get("wikipedia"):
        score += 3
    if island.get("image") or island.get("images"):
        score += 2
    return score


def load_islands() -> list[dict]:
    return load_json(ISLANDS_PATH, [])


def build_island_index(islands: list[dict]) -> dict[str, Any]:
    qid_index: dict[str, dict] = {}
    osm_index: dict[tuple[str, int], dict] = {}
    name_index: dict[str, list[dict]] = {}
    for island in islands:
        if island.get("wikidata"):
            qid_index[island["wikidata"]] = island
        if island.get("osmType") and island.get("osmId") is not None:
            osm_index[(island["osmType"], int(island["osmId"]))] = island
        name_index.setdefault(name_key(island.get("name", "")), []).append(island)
    return {
        "qid": qid_index,
        "osm": osm_index,
        "name": name_index,
        "all": islands,
    }


def find_existing_match(candidate: dict, index: dict[str, Any]) -> dict | None:
    osm_type = candidate.get("osmType")
    osm_id = candidate.get("osmId")
    if osm_type and osm_id is not None:
        hit = index["osm"].get((osm_type, int(osm_id)))
        if hit:
            return hit
    qid = candidate.get("wikidata")
    if qid and qid in index["qid"]:
        return index["qid"][qid]
    key = name_key(candidate.get("name", ""))
    for existing in index["name"].get(key, []):
        if haversine_km(candidate["lat"], candidate["lng"], existing["lat"], existing["lng"]) <= PROXIMITY_KM:
            return existing
    for existing in index["all"]:
        if haversine_km(candidate["lat"], candidate["lng"], existing["lat"], existing["lng"]) <= 0.5:
            return existing
    return None
