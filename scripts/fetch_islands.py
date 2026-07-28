#!/usr/bin/env python3
"""
Fetch UK islands from OpenStreetMap via the Overpass API and merge them
with the hand-curated dataset.

Output: data/islands.json — a single ranked list (curated entries first,
then OSM-imported entries), capped at MAX_ISLANDS.

Run:
    python3 scripts/fetch_islands.py
"""

from __future__ import annotations

import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CURATED_PATH = DATA_DIR / "curated.json"
OUT_PATH = DATA_DIR / "islands.json"
RAW_PATH = DATA_DIR / "osm_raw.json"

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
]

# Bounding box: (south, west, north, east)
# Covers the British Isles + Channel Islands + a generous offshore buffer
# (~50 miles) so we catch outliers like Rockall, North Rona, St Kilda etc.
UK_BBOX = (49.0, -10.5, 61.5, 2.5)

MAX_ISLANDS = 60000  # effectively uncapped; OSM has ~5,800 named UK/Irish islands

# Approximate nation bounding polygons (lat, lng pairs).
# Used as a cheap reverse-geocode for tagging entries by nation.
# Order matters — first match wins. Crown dependencies and Northern Ireland
# come first because they sit inside the wider Scotland/England boxes.
NATION_BOXES: list[tuple[str, tuple[float, float, float, float]]] = [
    ("Crown Dependency", (49.0, -2.7, 49.8, -1.9)),     # Channel Islands
    ("Crown Dependency", (54.0, -4.85, 54.45, -4.25)),  # Isle of Man
    ("Northern Ireland", (54.0, -8.2, 55.4, -5.4)),
    # Republic of Ireland (within the user's 50-mile-of-UK remit)
    ("Ireland", (51.3, -10.6, 55.45, -5.4)),
    ("Wales", (51.3, -5.4, 53.45, -2.65)),
    ("Scotland", (54.6, -8.7, 61.5, -0.7)),
    ("Scotland", (57.5, -10.5, 58.5, -8.0)),            # St Kilda
    ("England", (49.5, -6.5, 55.9, 1.9)),
]


def overpass_query(bbox: tuple[float, float, float, float]) -> str:
    s, w, n, e = bbox
    bbox_str = f"{s},{w},{n},{e}"
    return f"""
[out:json][timeout:300];
(
  node["place"~"^(island|islet)$"]["name"]({bbox_str});
  way["place"~"^(island|islet)$"]["name"]({bbox_str});
  relation["place"~"^(island|islet)$"]["name"]({bbox_str});
);
out tags center;
""".strip()


def post_overpass(query: str) -> dict:
    last_error: Exception | None = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            print(f"→ querying {endpoint}", file=sys.stderr)
            data = urllib.parse.urlencode({"data": query}).encode("utf-8")
            req = urllib.request.Request(
                endpoint,
                data=data,
                headers={
                    "User-Agent": "isles-of-britain/0.1 (prototype; static site)",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=300) as resp:
                payload = resp.read()
            return json.loads(payload)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            print(f"  endpoint failed: {exc}", file=sys.stderr)
            last_error = exc
            time.sleep(2)
    raise RuntimeError(f"All Overpass endpoints failed: {last_error}")


def slugify(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^\w\s\-]+", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", "-", s).strip("-")
    return s or "island"


def nation_for(lat: float, lng: float) -> str:
    for nation, (s, w, n, e) in NATION_BOXES:
        if s <= lat <= n and w <= lng <= e:
            return nation
    return "British Isles"


def parse_area(tags: dict) -> float | None:
    """Look at common OSM tags that might encode an area."""
    for key in ("area", "ele:area", "wikidata:area"):
        v = tags.get(key)
        if not v:
            continue
        try:
            v = v.replace(",", "").strip()
            num = float(re.findall(r"[\d.]+", v)[0])
            if "ha" in v.lower():
                return num / 100.0
            if "km" in v.lower():
                return num
            if "m" in v.lower():
                return num / 1_000_000.0
        except Exception:
            continue
    return None


def parse_population(tags: dict) -> int | None:
    v = tags.get("population")
    if not v:
        return None
    try:
        return int(re.sub(r"[^\d]", "", v))
    except Exception:
        return None


def normalize_element(el: dict) -> dict | None:
    tags = el.get("tags") or {}
    name = tags.get("name:en") or tags.get("name")
    if not name:
        return None

    if el["type"] == "node":
        lat, lng = el.get("lat"), el.get("lon")
    else:
        center = el.get("center") or {}
        lat, lng = center.get("lat"), center.get("lon")
    if lat is None or lng is None:
        return None

    place = (tags.get("place") or "island").lower()

    image = tags.get("image") or tags.get("wikimedia_commons")
    if image and image.startswith("File:"):
        # Convert to a Wikimedia thumbnail URL
        fname = image[len("File:"):].replace(" ", "_")
        # Use the Special:Redirect endpoint for stable URLs
        image = (
            "https://commons.wikimedia.org/wiki/Special:FilePath/"
            + urllib.parse.quote(fname)
            + "?width=640"
        )

    wikipedia = tags.get("wikipedia")
    if wikipedia and ":" in wikipedia:
        lang, title = wikipedia.split(":", 1)
        wikipedia = f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"

    return {
        "id": f"osm-{el['type']}-{el['id']}",
        "name": name,
        "nation": nation_for(lat, lng),
        "type": "sea",  # default; curated entries override this
        "archipelago": tags.get("is_in") or tags.get("is_in:archipelago") or "",
        "lat": round(lat, 5),
        "lng": round(lng, 5),
        "areaKm2": parse_area(tags),
        "population": parse_population(tags),
        "highestPointM": None,
        "highestPointName": tags.get("ele:name") or "",
        "shortDescription": tags.get("description") or "",
        "history": "",
        "geography": "",
        "transport": "",
        "accommodation": "",
        "wikipedia": wikipedia or "",
        "wikidata": tags.get("wikidata") or "",
        "image": image or "",
        "images": [],
        "tags": [t for t in [place, tags.get("natural"), tags.get("tourism")] if t],
        "source": "osm",
        "osmType": el["type"],
        "osmId": el["id"],
        "osmPlace": place,
    }


def dedupe(entries: list[dict]) -> list[dict]:
    """Remove duplicate islands when the same place is tagged on multiple
    geometry types (very common in OSM)."""
    seen: dict[tuple, dict] = {}
    for e in entries:
        # Round to ~1 km to merge tagging variants of the same island
        key = (e["name"].lower(), round(e["lat"], 2), round(e["lng"], 2))
        existing = seen.get(key)
        if not existing:
            seen[key] = e
            continue
        # Prefer the entry with richer data (relation > way > node, has area, has wikipedia)
        if rank_quality(e) > rank_quality(existing):
            seen[key] = e
    return list(seen.values())


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _names_loosely_match(a: str, b: str) -> bool:
    """True when names refer to the same place (not Island↔Point false friends)."""
    classifiers = {
        "point",
        "rock",
        "rocks",
        "ledge",
        "reef",
        "skerry",
        "stack",
        "scar",
        "carr",
    }

    def norm(s: str) -> str:
        s = s.lower()
        s = re.sub(r"\(.*?\)", "", s)  # drop parenthetical
        s = re.sub(r"\bisle of\b|\bisland\b|\bynys\b", "", s)
        s = re.sub(r"[^\w\s]", "", s)
        return re.sub(r"\s+", " ", s).strip()

    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    ta, tb = set(na.split()), set(nb.split())
    # "Burgh Island" → "burgh" must not match OSM "Burgh Point" → "burgh point"
    if (ta & classifiers) != (tb & classifiers):
        return False
    return na in nb or nb in na


def rank_quality(e: dict) -> int:
    type_score = {"relation": 3, "way": 2, "node": 1}.get(e.get("osmType", ""), 0)
    return (
        type_score
        + (5 if e.get("areaKm2") else 0)
        + (3 if e.get("wikipedia") else 0)
        + (2 if e.get("image") else 0)
        + (1 if e.get("population") is not None else 0)
    )


def rank_for_capping(e: dict) -> float:
    """Higher = more notable. Used to keep the best 1000 when capping."""
    score = 0.0
    if e.get("areaKm2"):
        score += math.log10(e["areaKm2"] + 1) * 10
    if e.get("population"):
        score += math.log10(e["population"] + 1) * 4
    if e.get("wikipedia"):
        score += 8
    if e.get("image"):
        score += 3
    if e.get("osmType") == "relation":
        score += 4
    elif e.get("osmType") == "way":
        score += 2
    if e.get("osmPlace") == "island":
        score += 3  # prefer islands over islets when capping
    return score


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Optional --max=N flag to override the cap.
    max_islands = MAX_ISLANDS
    for arg in sys.argv:
        if arg.startswith("--max="):
            try:
                max_islands = int(arg.split("=", 1)[1])
            except ValueError:
                pass

    use_cache = "--cache" in sys.argv and RAW_PATH.exists()
    if use_cache:
        print(f"Using cached Overpass response at {RAW_PATH.relative_to(ROOT)}", file=sys.stderr)
        raw = json.loads(RAW_PATH.read_text())
    else:
        print("Fetching UK islands from Overpass…", file=sys.stderr)
        raw = post_overpass(overpass_query(UK_BBOX))
        RAW_PATH.write_text(json.dumps(raw, ensure_ascii=False))
        print(f"  cached raw response to {RAW_PATH.relative_to(ROOT)}", file=sys.stderr)
    elements = raw.get("elements", [])
    print(f"  got {len(elements)} raw elements", file=sys.stderr)

    osm_entries: list[dict] = []
    for el in elements:
        norm = normalize_element(el)
        if norm:
            osm_entries.append(norm)
    print(f"  normalized {len(osm_entries)} entries", file=sys.stderr)

    osm_entries = dedupe(osm_entries)
    print(f"  {len(osm_entries)} after dedupe", file=sys.stderr)

    # --- merge with curated ---
    curated: list[dict] = []
    if CURATED_PATH.exists():
        curated = json.loads(CURATED_PATH.read_text())
        for c in curated:
            c.setdefault("source", "curated")
        print(f"  loaded {len(curated)} curated entries", file=sys.stderr)

    # For each curated entry, find the closest OSM entry within ~25 km
    # whose name loosely matches — and copy in the OSM IDs so the frontend
    # can lazy-fetch the polygon. Drop the matched OSM entry from the dump.
    matched_osm_ids: set[tuple] = set()
    matches_made = 0
    for c in curated:
        # Prefer maintainer-pinned OSM ids (avoids Island↔Point near-misses).
        pinned_type = c.get("osmType")
        pinned_id = c.get("osmId")
        if pinned_type and pinned_id is not None:
            matched_osm_ids.add((pinned_type, pinned_id))
            matches_made += 1
            continue
        best, best_d = None, 25.0  # km
        for e in osm_entries:
            if not _names_loosely_match(c["name"], e["name"]):
                continue
            d = _haversine_km(c["lat"], c["lng"], e["lat"], e["lng"])
            if d < best_d:
                best, best_d = e, d
        if best:
            c["osmType"] = best.get("osmType")
            c["osmId"] = best.get("osmId")
            c["osmPlace"] = best.get("osmPlace")
            matched_osm_ids.add((best["osmType"], best["osmId"]))
            matches_made += 1
    print(f"  matched {matches_made}/{len(curated)} curated → OSM IDs", file=sys.stderr)

    deduped_osm = [
        e
        for e in osm_entries
        if (e["osmType"], e["osmId"]) not in matched_osm_ids
    ]
    print(f"  {len(deduped_osm)} OSM entries remain after curated overlap", file=sys.stderr)

    # Drop anything we couldn't classify as British / Irish — those are
    # Faroes / French outliers caught by our wide bbox.
    before = len(deduped_osm)
    deduped_osm = [e for e in deduped_osm if e["nation"] != "British Isles"]
    print(f"  dropped {before - len(deduped_osm)} unclassified (Faroes/France)", file=sys.stderr)

    # Cap by notability
    deduped_osm.sort(key=rank_for_capping, reverse=True)
    keep = max(0, max_islands - len(curated))
    osm_kept = deduped_osm[:keep]
    print(
        f"  cap={max_islands}; keeping top {len(osm_kept)} OSM by notability",
        file=sys.stderr,
    )

    combined = curated + osm_kept
    combined.sort(key=lambda e: e["name"].lower())

    OUT_PATH.write_text(json.dumps(combined, ensure_ascii=False, indent=2) + "\n")
    print(
        f"\nWrote {len(combined)} islands to {OUT_PATH.relative_to(ROOT)} "
        f"({len(curated)} curated + {len(osm_kept)} from OSM).",
        file=sys.stderr,
    )

    by_nation: dict[str, int] = {}
    for e in combined:
        by_nation[e["nation"]] = by_nation.get(e["nation"], 0) + 1
    print("By nation:", json.dumps(by_nation, indent=2), file=sys.stderr)


if __name__ == "__main__":
    main()
