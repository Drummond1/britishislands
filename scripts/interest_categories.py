#!/usr/bin/env python3
"""Populate interest-category memberships and publish the atlas filter index.

Categories live in Supabase. The public map reads data/interest_index.json,
which this script writes from accepted, cited rows only.

  python3 scripts/interest_categories.py for-sale
  python3 scripts/interest_categories.py whisky
  python3 scripts/interest_categories.py culture
  python3 scripts/interest_categories.py publish
  python3 scripts/interest_categories.py all

Writes use SUPABASE_SERVICE_ROLE_KEY from .env.local when it is set.
Without that key, publish still writes the static index and prints the
row count for a service-role load.
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from ingest_sources import haversine_km, name_key  # noqa: E402

DATA = ROOT / "data"
INTEREST = DATA / "interest"
CANDIDATES = INTEREST / "candidates"
INDEX_PATH = DATA / "interest_index.json"
ATLAS_PATH = DATA / "islands_index.json"
REGISTRY_PATH = DATA / "discovery" / "property_listings_registry.json"
SEEDS_PATH = INTEREST / "culture_seeds.json"
ENV_PATH = ROOT / ".env.local"

USER_AGENT = "isles-of-britain/0.1 (interest-categories; research)"
UK_BBOX = (49.0, -10.5, 61.5, 2.5)  # south, west, north, east
WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"
OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"

PUBLISHED = (
    {
        "slug": "film-art-music",
        "label": "Film, art and music",
        "blurb": "Islands tied to a specific film, artwork, or piece of music.",
        "sortOrder": 10,
    },
    {
        "slug": "whisky-distilleries",
        "label": "Whisky distilleries",
        "blurb": "Islands with a working whisky distillery.",
        "sortOrder": 20,
    },
    {
        "slug": "for-sale",
        "label": "For sale",
        "blurb": "Islands with a current broker listing.",
        "sortOrder": 30,
    },
)

# Equivalent-circle radius times this factor. Large enough for a long
# island such as Skye, and still short of the next island or the mainland.
RADIUS_FACTOR = 1.45
# Great Britain and Ireland are in the atlas, but a distillery on those
# mainlands is not an island distillery. Tiny skerries were stealing
# coastal works because their centroid is closer than the real island's.
MIN_ISLAND_AREA_KM2 = 1.0
MAX_ISLAND_AREA_KM2 = 8000.0


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower()


def http_json(url: str, data: bytes | None = None, headers: dict | None = None, timeout: int = 90):
    """curl, not urllib: the system Python 3.9 SSL stack fails against some hosts."""
    cmd = [
        "curl",
        "-fsS",
        "--max-time",
        str(timeout),
        "-A",
        USER_AGENT,
        "-H",
        "Accept: application/json",
    ]
    for key, value in (headers or {}).items():
        cmd.extend(["-H", f"{key}: {value}"])
    if data is not None:
        cmd.extend(["--data-binary", data.decode("utf-8") if isinstance(data, bytes) else data])
    cmd.append(url)
    raw = subprocess.check_output(cmd)
    return json.loads(raw.decode("utf-8"))


def load_env() -> dict:
    out = {}
    if not ENV_PATH.exists():
        return out
    for line in ENV_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        out[key.strip()] = val.strip().strip('"').strip("'")
    return out


class Atlas:
    def __init__(self):
        payload = load_json(ATLAS_PATH, {})
        rows = payload.get("rows") or []
        self.islands = []
        self.by_id = {}
        self.by_key = {}
        for row in rows:
            island = {
                "id": row.get("id"),
                "name": row.get("n") or "",
                "lat": row.get("y"),
                "lng": row.get("x"),
                "area": row.get("a") or 0,
            }
            if not island["id"] or island["lat"] is None or island["lng"] is None:
                continue
            self.islands.append(island)
            self.by_id[island["id"]] = island
            self.by_key.setdefault(name_key(island["name"]), []).append(island)

    def match_name(self, *names: str) -> dict | None:
        hits = []
        seen = set()
        for name in names:
            if not name:
                continue
            for island in self.by_key.get(name_key(name), []):
                if island["id"] in seen:
                    continue
                seen.add(island["id"])
                hits.append(island)
            exact = fold(name)
            for island in self.islands:
                if fold(island["name"]) == exact and island["id"] not in seen:
                    seen.add(island["id"])
                    hits.append(island)
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            ranked = sorted(hits, key=lambda island: island["area"] or 0, reverse=True)
            if (ranked[0]["area"] or 0) > (ranked[1]["area"] or 0):
                return ranked[0]
        return None

    def match_point(self, lat: float, lng: float) -> tuple[dict | None, float, float]:
        """Nearest atlas island whose centroid radius contains the point."""
        best = None
        best_dist = 1e9
        best_radius = 0.0
        for island in self.islands:
            area = island["area"] or 0
            if area < MIN_ISLAND_AREA_KM2 or area > MAX_ISLAND_AREA_KM2:
                continue
            radius = math.sqrt(area / math.pi) * RADIUS_FACTOR
            dist = haversine_km(lat, lng, island["lat"], island["lng"])
            if dist <= radius and dist < best_dist:
                best = island
                best_dist = dist
                best_radius = radius
        return best, best_dist, best_radius

    def spatial_hits(self, lat: float, lng: float):
        hits = []
        for island in self.islands:
            area = island["area"] or 0
            if area < MIN_ISLAND_AREA_KM2 or area > MAX_ISLAND_AREA_KM2:
                continue
            radius = math.sqrt(area / math.pi) * RADIUS_FACTOR
            dist = haversine_km(lat, lng, island["lat"], island["lng"])
            if dist <= radius * 1.12:
                hits.append((dist, radius, island))
        hits.sort(key=lambda hit: hit[0])
        return hits

    def choose_whisky_island(self, lat: float, lng: float, title: str, article: str):
        """Pick the island that contains the point and is named as the location."""
        hits = self.spatial_hits(lat, lng)
        if not hits:
            return None, 0.0, 0.0
        titled = fold(title)
        named = [hit for hit in hits if _token_in_text(hit[2], titled)]
        if len(named) == 1:
            return named[0][2], named[0][0], named[0][1]
        cite = f"{title}\n{article}"
        confirmed = [hit for hit in hits if article and _location_sentence(hit[2], cite)]
        if confirmed:
            confirmed.sort(key=lambda hit: hit[0])
            return confirmed[0][2], confirmed[0][0], confirmed[0][1]
        dist, radius, island = hits[0]
        # Deep inside one island: a neighbour's name in the article is not required.
        if not article and dist <= radius * 0.45 and len(hits) == 1:
            return island, dist, radius
        if article and dist <= radius * 0.45 and len(hits) == 1 and not confirmed:
            return island, dist, radius
        return None, dist, radius


def row(
    *,
    category: str,
    island_id: str,
    facet: str,
    title: str,
    source_url: str,
    status: str,
    confidence: str = "high",
    licence: str = "",
    evidence: str = "",
    external_id: str = "",
    source_title: str = "",
    reject_reason: str = "",
    island_name: str = "",
) -> dict:
    return {
        "category_slug": category,
        "island_id": island_id,
        "island_name": island_name,
        "facet": facet,
        "title": title,
        "source_url": source_url,
        "source_title": source_title,
        "licence": licence,
        "evidence": evidence,
        "external_id": external_id,
        "confidence": confidence,
        "status": status,
        "reject_reason": reject_reason,
        "fetched_at": utc_now(),
    }


def write_candidates(slug: str, rows: list[dict], meta: dict) -> Path:
    path = CANDIDATES / f"{slug}.json"
    save_json(path, {"slug": slug, "generatedAt": utc_now(), **meta, "rows": rows})
    accepted = sum(1 for r in rows if r["status"] == "accepted")
    islands = len({r["island_id"] for r in rows if r["status"] == "accepted" and r["island_id"]})
    print(f"{slug}: {accepted} accepted rows on {islands} islands ({len(rows)} considered)")
    return path


def populate_for_sale(atlas: Atlas) -> list[dict]:
    registry = load_json(REGISTRY_PATH, {})
    rows = []
    for island in registry.get("islands") or []:
        island_id = island.get("islandId") or ""
        listings = island.get("listings") or []
        if not listings:
            continue
        known = atlas.by_id.get(island_id)
        if not known:
            rows.append(
                row(
                    category="for-sale",
                    island_id=island_id,
                    facet="listing",
                    title=(listings[0].get("title") or island.get("name") or "Listing"),
                    source_url=listings[0].get("url") or "",
                    status="rejected",
                    confidence="medium",
                    reject_reason="island id is not in the atlas index",
                    island_name=island.get("name") or "",
                )
            )
            continue
        # One membership per listing title. The island is already on the map.
        seen_titles = set()
        for listing in listings:
            title = (listing.get("title") or known["name"] or "Listing").strip()
            url = (listing.get("url") or "").strip()
            if not url or title in seen_titles:
                continue
            seen_titles.add(title)
            price = listing.get("priceDisplay") or ""
            evidence = price or listing.get("listingType") or "Broker listing"
            rows.append(
                row(
                    category="for-sale",
                    island_id=island_id,
                    facet="listing",
                    title=title,
                    source_url=url,
                    source_title=title,
                    licence="outbound-link",
                    evidence=evidence,
                    external_id=listing.get("sourceListingId") or "",
                    status="accepted",
                    confidence="high",
                    island_name=known["name"],
                )
            )
    write_candidates(
        "for-sale",
        rows,
        {"source": "data/discovery/property_listings_registry.json"},
    )
    return rows


def _whisky_blob(tags: dict) -> str:
    parts = [
        tags.get("name") or "",
        tags.get("official_name") or "",
        tags.get("product") or "",
        tags.get("drink") or "",
        tags.get("produce") or "",
        tags.get("description") or "",
    ]
    return fold(" ".join(parts))


def osm_is_whisky(tags: dict) -> tuple[bool, str]:
    blob = _whisky_blob(tags)
    if any(word in blob for word in ("whisky", "whiskey")):
        return True, "name or product says whisky"
    if any(word in blob for word in ("gin", "vodka", "rum", "beer", "brewery", "cider")):
        return False, "product is not whisky"
    return False, "craft=distillery without a whisky name or product"


def fetch_overpass() -> dict:
    cache = DATA / "cache_overpass_distilleries.json"
    if cache.exists():
        return load_json(cache, {})
    # The public Overpass mirrors timed out from this environment on 2026-10-25.
    # Wikidata plus the cited gap list cover the island distilleries. A later
    # run can fill data/cache_overpass_distilleries.json and this will use it.
    print("overpass cache missing; whisky uses Wikidata and cited gap pages")
    return {"elements": []}


def fetch_wikidata_whisky() -> list[dict]:
    cache = DATA / "cache_wikidata_whisky_distilleries.json"
    if cache.exists():
        return load_json(cache, [])
    # Q10373548 is "whisky distillery" (Talisker is a direct instance; it has no P1056).
    query = """
SELECT ?item ?itemLabel ?lat ?lon ?article WHERE {
  ?item wdt:P31/wdt:P279* wd:Q10373548 .
  ?item p:P625/psv:P625 ?coord .
  ?coord wikibase:geoLatitude ?lat ;
         wikibase:geoLongitude ?lon .
  FILTER(?lat > 49 && ?lat < 61.5 && ?lon > -10.8 && ?lon < 2.5)
  OPTIONAL {
    ?article schema:about ?item ;
             schema:isPartOf <https://en.wikipedia.org/> .
  }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
"""
    url = WIKIDATA_ENDPOINT + "?" + urllib.parse.urlencode({"format": "json", "query": query})
    last_error = None
    payload = None
    for attempt in range(3):
        try:
            payload = http_json(url, headers={"Accept": "application/sparql-results+json"}, timeout=120)
            break
        except subprocess.CalledProcessError as exc:
            last_error = exc
            print(f"wikidata attempt {attempt + 1} failed: {exc.returncode}")
            time.sleep(65)
    if payload is None:
        print(f"wikidata unavailable, continuing with OpenStreetMap only: {last_error}")
        return []
    rows = []
    for binding in payload.get("results", {}).get("bindings", []):
        qid = binding["item"]["value"].rsplit("/", 1)[-1]
        rows.append(
            {
                "qid": qid,
                "label": binding.get("itemLabel", {}).get("value") or qid,
                "lat": float(binding["lat"]["value"]),
                "lng": float(binding["lon"]["value"]),
                "article": binding.get("article", {}).get("value") or "",
            }
        )
    save_json(cache, rows)
    return rows


def _element_point(element: dict) -> tuple[float, float] | None:
    if "lat" in element and "lon" in element:
        return float(element["lat"]), float(element["lon"])
    center = element.get("center") or {}
    if "lat" in center and "lon" in center:
        return float(center["lat"]), float(center["lon"])
    return None


def populate_whisky(atlas: Atlas) -> list[dict]:
    rows = []
    seen = set()

    def add(item: dict) -> None:
        key = (
            item["island_id"],
            fold(item["title"]),
        )
        if item["status"] == "accepted" and key in seen:
            return
        if item["status"] == "accepted":
            seen.add(key)
        rows.append(item)

    wikidata = fetch_wikidata_whisky()
    for place in wikidata:
        article = place.get("article") or ""
        source = article or f"https://www.wikidata.org/wiki/{place['qid']}"
        licence = "CC BY-SA 4.0" if article else "CC0"
        title = place["label"]
        if re.fullmatch(r"Q\d+", title):
            continue
        if not atlas.spatial_hits(place["lat"], place["lng"]):
            add(
                row(
                    category="whisky-distilleries",
                    island_id="",
                    facet="distillery",
                    title=title,
                    source_url=source,
                    source_title=title,
                    licence=licence,
                    external_id=place["qid"],
                    status="rejected",
                    confidence="medium",
                    reject_reason="coordinates are not on a named atlas island",
                    evidence=f"{place['lat']:.4f},{place['lng']:.4f}",
                )
            )
            continue
        island, dist, radius = atlas.choose_whisky_island(place["lat"], place["lng"], title, "")
        article_text = ""
        if island is None and article:
            wiki_title = urllib.parse.unquote(article.rsplit("/", 1)[-1])
            try:
                article_text = wikipedia_plain(wiki_title)
            except Exception as exc:  # noqa: BLE001 — deep-inside matches can still pass
                print(f"wikipedia skip {title}: {exc}")
            island, dist, radius = atlas.choose_whisky_island(
                place["lat"], place["lng"], title, article_text
            )
        if island is None:
            add(
                row(
                    category="whisky-distilleries",
                    island_id="",
                    facet="distillery",
                    title=title,
                    source_url=source,
                    source_title=title,
                    licence=licence,
                    external_id=place["qid"],
                    status="rejected",
                    confidence="medium",
                    reject_reason="coordinates are not on a named atlas island",
                    evidence=f"{place['lat']:.4f},{place['lng']:.4f}",
                )
            )
            continue
        ratio = dist / radius if radius else 1
        add(
            row(
                category="whisky-distilleries",
                island_id=island["id"],
                facet="distillery",
                title=title,
                source_url=source,
                source_title=title,
                licence=licence,
                external_id=place["qid"],
                status="accepted",
                confidence="high" if ratio <= 0.85 else "medium",
                evidence=(
                    f"Wikidata {place['qid']} at {place['lat']:.4f},{place['lng']:.4f}, "
                    f"{dist:.1f} km from the centroid of {island['name']} "
                    f"(radius {radius:.1f} km)."
                ),
                island_name=island["name"],
            )
        )

    overpass = fetch_overpass()
    for element in overpass.get("elements") or []:
        tags = element.get("tags") or {}
        point = _element_point(element)
        name = (tags.get("name") or "").strip()
        if not point or not name:
            continue
        keep, why = osm_is_whisky(tags)
        osm_type = element.get("type") or "node"
        osm_id = element.get("id")
        source = f"https://www.openstreetmap.org/{osm_type}/{osm_id}"
        external = f"{osm_type}/{osm_id}"
        if not keep:
            continue
        island, dist, radius = atlas.match_point(point[0], point[1])
        if island is None:
            continue
        # Wikidata already covers the same works. OSM fills gaps only.
        if any(
            r["status"] == "accepted"
            and r["island_id"] == island["id"]
            and name_key(r["title"]) == name_key(name)
            for r in rows
        ):
            continue
        ratio = dist / radius if radius else 1
        add(
            row(
                category="whisky-distilleries",
                island_id=island["id"],
                facet="distillery",
                title=name,
                source_url=source,
                source_title=name,
                licence="ODbL",
                external_id=external,
                status="accepted",
                confidence="high" if ratio <= 0.85 else "medium",
                evidence=(
                    f"OpenStreetMap {external} ({why}) at {point[0]:.4f},{point[1]:.4f}, "
                    f"{dist:.1f} km from the centroid of {island['name']} "
                    f"(radius {radius:.1f} km)."
                ),
                island_name=island["name"],
            )
        )

    gap_seeds = [
        ("Isle of Raasay distillery", "Isle_of_Raasay_distillery", ["Raasay"]),
        ("Isle of Harris Distillery", "Isle_of_Harris_Distillery", ["Lewis and Harris", "Harris"]),
        ("Lagg distillery", "Lagg_distillery", ["Isle of Arran", "Arran"]),
        ("Isle of Barra distillery", "Isle_of_Barra_distillery", ["Barra"]),
    ]
    for title, wiki, names in gap_seeds:
        source = f"https://en.wikipedia.org/wiki/{wiki}"
        try:
            text = wikipedia_plain(wiki)
        except Exception as exc:  # noqa: BLE001
            print(f"whisky gap skip {title}: {exc}")
            continue
        if not text.strip() or not _contains_any(text, [title, title.replace(" distillery", "")]):
            continue
        island = atlas.match_name(*names)
        if island is None or not island_mentioned(island, text):
            continue
        if any(
            r["status"] == "accepted" and r["island_id"] == island["id"] and name_key(r["title"]) == name_key(title)
            for r in rows
        ):
            continue
        add(
            row(
                category="whisky-distilleries",
                island_id=island["id"],
                facet="distillery",
                title=title,
                source_url=source,
                source_title=wiki.replace("_", " "),
                licence="CC BY-SA 4.0",
                external_id=wiki,
                status="accepted",
                confidence="high",
                evidence=f"Wikipedia page names the distillery and {island['name']}.",
                island_name=island["name"],
            )
        )

    write_candidates(
        "whisky-distilleries",
        rows,
        {
            "wikidata": len(wikidata),
            "overpass": len(overpass.get("elements") or []),
        },
    )
    return rows


def wikipedia_plain(title: str) -> str:
    cache_dir = DATA / "cache_wikipedia_interest"
    cache_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", title)[:120]
    cache = cache_dir / f"{safe}.json"
    if cache.exists():
        payload = load_json(cache, {})
    else:
        params = {
            "action": "query",
            "prop": "extracts",
            "explaintext": "1",
            "redirects": "1",
            "format": "json",
            "titles": title.replace("_", " "),
        }
        url = WIKIPEDIA_API + "?" + urllib.parse.urlencode(params)
        payload = None
        last_error = None
        for attempt in range(2):
            try:
                payload = http_json(url, timeout=60)
                break
            except subprocess.CalledProcessError as exc:
                last_error = exc
                time.sleep(2.5 * (attempt + 1))
        if payload is None:
            raise RuntimeError(f"Wikipedia fetch failed: {last_error}")
        save_json(cache, payload)
        time.sleep(0.6)
    pages = (payload.get("query") or {}).get("pages") or {}
    chunks = []
    for page in pages.values():
        if page.get("missing") is not None:
            continue
        chunks.append(page.get("title") or "")
        chunks.append(page.get("extract") or "")
    return "\n".join(chunks)


def _token_in_text(island: dict, text: str) -> bool:
    blob = fold(text)
    short = name_key(island["name"])
    if short and len(short) >= 4 and re.search(rf"\b{re.escape(short)}\b", blob):
        return True
    raw = fold(island["name"])
    for token in ("orkney", "harris", "lewis", "skye", "islay", "jura", "mull", "arran", "raasay", "barra", "tiree"):
        if token in raw and re.search(rf"\b{token}\b", blob):
            return True
    return False


def _location_sentence(island: dict, text: str) -> bool:
    """A sentence that places the subject on the island, not merely opposite it."""
    short = name_key(island["name"])
    tokens = [short] if short and len(short) >= 4 else []
    raw = fold(island["name"])
    for token in ("orkney", "harris", "lewis", "skye", "islay", "jura", "mull", "arran", "raasay", "barra", "tiree"):
        if token in raw and token not in tokens:
            tokens.append(token)
    if not tokens:
        return False
    for sentence in re.split(r"[.\n]", text or ""):
        folded = fold(sentence)
        if not any(re.search(rf"\b{re.escape(token)}\b", folded) for token in tokens):
            continue
        positive = False
        for token in tokens:
            if re.search(rf"\b(isle of|island of) {re.escape(token)}\b", folded):
                positive = True
            elif re.search(rf"\b(on|in) {re.escape(token)}\b", folded):
                positive = True
            elif re.search(rf"\b{re.escape(token)} (distillery|island)\b", folded):
                positive = True
        if not positive:
            continue
        # "opposite the Isle of Mull" is not a location. "on the Isle of Islay,
        # beside the Sound of Islay" is.
        if re.search(r"\bopposite the (isle|island) of\b", folded):
            continue
        if re.search(r"\b(opposite|across from|looking towards)\b", folded) and not re.search(
            r"\b(on|in) (the )?(isle|island) of\b", folded
        ):
            continue
        return True
    return False


def island_mentioned(island: dict, text: str) -> bool:
    """True when the citation text names this island, not just a nearby rock."""
    return _token_in_text(island, text) and (
        _token_in_text(island, text.split("\n", 1)[0]) or _location_sentence(island, text)
    )


def _contains_any(text: str, phrases: list[str]) -> str:
    folded = fold(text)
    for phrase in phrases:
        if fold(phrase) and fold(phrase) in folded:
            return phrase
    return ""


def populate_culture(atlas: Atlas) -> list[dict]:
    seeds = load_json(SEEDS_PATH, {}).get("seeds") or []
    rows = []
    for seed in seeds:
        wiki = seed["wikipedia"]
        source = f"https://en.wikipedia.org/wiki/{wiki}"
        try:
            text = wikipedia_plain(wiki)
        except Exception as exc:  # noqa: BLE001 — record the failed fetch
            rows.append(
                row(
                    category="film-art-music",
                    island_id="",
                    facet=seed["facet"],
                    title=seed["title"],
                    source_url=source,
                    status="rejected",
                    confidence="medium",
                    reject_reason=f"could not fetch Wikipedia: {exc}",
                )
            )
            continue
        titles = [seed["title"], *(seed.get("titleAliases") or [])]
        title_hit = _contains_any(text, titles)
        if not text.strip():
            rows.append(
                row(
                    category="film-art-music",
                    island_id="",
                    facet=seed["facet"],
                    title=seed["title"],
                    source_url=source,
                    status="rejected",
                    confidence="medium",
                    reject_reason="Wikipedia page has no extract",
                )
            )
            continue
        if not title_hit:
            rows.append(
                row(
                    category="film-art-music",
                    island_id="",
                    facet=seed["facet"],
                    title=seed["title"],
                    source_url=source,
                    source_title=wiki,
                    licence="CC BY-SA 4.0",
                    status="rejected",
                    confidence="medium",
                    reject_reason="page does not name the work",
                )
            )
            continue
        for island_spec in seed.get("islands") or []:
            phrase = _contains_any(text, island_spec.get("phrases") or [])
            match = atlas.match_name(*(island_spec.get("matchNames") or []))
            if not phrase:
                rows.append(
                    row(
                        category="film-art-music",
                        island_id=match["id"] if match else "",
                        facet=seed["facet"],
                        title=seed["title"],
                        source_url=source,
                        source_title=wiki,
                        licence="CC BY-SA 4.0",
                        status="rejected",
                        confidence="medium",
                        reject_reason="page does not name this island",
                        island_name=match["name"] if match else "",
                    )
                )
                continue
            if match is None:
                rows.append(
                    row(
                        category="film-art-music",
                        island_id="",
                        facet=seed["facet"],
                        title=seed["title"],
                        source_url=source,
                        source_title=wiki,
                        licence="CC BY-SA 4.0",
                        status="rejected",
                        confidence="medium",
                        reject_reason="island name did not match a single atlas id: "
                        + ", ".join(island_spec.get("matchNames") or []),
                        evidence=f"page contains {phrase!r}",
                    )
                )
                continue
            rows.append(
                row(
                    category="film-art-music",
                    island_id=match["id"],
                    facet=seed["facet"],
                    title=seed["title"],
                    source_url=source,
                    source_title=wiki.replace("_", " "),
                    licence="CC BY-SA 4.0",
                    external_id=wiki,
                    status="accepted",
                    confidence="high",
                    evidence=f"Wikipedia page names {title_hit!r} and {phrase!r}.",
                    island_name=match["name"],
                )
            )
    write_candidates("film-art-music", rows, {"seeds": len(seeds)})
    return rows


def load_candidate_rows() -> list[dict]:
    rows = []
    for path in sorted(CANDIDATES.glob("*.json")):
        payload = load_json(path, {})
        rows.extend(payload.get("rows") or [])
    return rows


def accepted_rows(rows: list[dict]) -> list[dict]:
    deduped = []
    seen = set()
    for item in rows:
        if item.get("status") != "accepted" or not item.get("island_id"):
            continue
        key = (
            item.get("category_slug"),
            item.get("island_id"),
            item.get("facet") or "",
            item.get("title"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def publish(rows: list[dict] | None = None) -> dict:
    rows = rows if rows is not None else load_candidate_rows()
    accepted = accepted_rows(rows)
    by_slug: dict[str, list[dict]] = {spec["slug"]: [] for spec in PUBLISHED}
    for item in accepted:
        by_slug.setdefault(item["category_slug"], []).append(item)

    categories = []
    members = {}
    highlights = {}
    for spec in PUBLISHED:
        group = by_slug.get(spec["slug"]) or []
        island_ids = []
        seen = set()
        highlight = {}
        for item in group:
            iid = item["island_id"]
            if iid not in seen:
                seen.add(iid)
                island_ids.append(iid)
            highlight.setdefault(iid, [])
            if item["title"] not in highlight[iid]:
                highlight[iid].append(item["title"])
        categories.append({**spec, "count": len(island_ids)})
        members[spec["slug"]] = island_ids
        highlights[spec["slug"]] = highlight

    index = {
        "schemaVersion": 1,
        "generatedAt": utc_now(),
        "categories": categories,
        "members": members,
        "highlights": highlights,
    }
    save_json(INDEX_PATH, index)
    save_json(INTEREST / "accepted_memberships.json", {"generatedAt": utc_now(), "rows": accepted})
    print(
        "published",
        ", ".join(f"{c['slug']}={c['count']}" for c in categories),
        "->",
        INDEX_PATH.relative_to(ROOT),
    )
    return index


def sql_literal(value) -> str:
    if value is None or value == "":
        return "null"
    return "'" + str(value).replace("'", "''") + "'"


def membership_sql(rows: list[dict]) -> str:
    accepted = accepted_rows(rows)
    chunks = ["delete from public.interest_memberships where category_slug in ('film-art-music','whisky-distilleries','for-sale');"]
    batch = []
    def flush():
        if not batch:
            return
        values = ",\n".join(batch)
        chunks.append(
            "insert into public.interest_memberships "
            "(category_slug, island_id, facet, title, source_url, source_title, licence, evidence, external_id, confidence, status) values\n"
            + values
            + ";"
        )
        batch.clear()

    for item in accepted:
        batch.append(
            "("
            + ", ".join(
                [
                    sql_literal(item["category_slug"]),
                    sql_literal(item["island_id"]),
                    sql_literal(item.get("facet")),
                    sql_literal(item["title"]),
                    sql_literal(item["source_url"]),
                    sql_literal(item.get("source_title")),
                    sql_literal(item.get("licence")),
                    sql_literal(item.get("evidence")),
                    sql_literal(item.get("external_id")),
                    sql_literal(item.get("confidence") or "high"),
                    sql_literal("accepted"),
                ]
            )
            + ")"
        )
        if len(batch) >= 40:
            flush()
    flush()
    return "\n".join(chunks)


def sync_supabase(rows: list[dict]) -> bool:
    env = load_env()
    url = (env.get("SUPABASE_URL") or "").rstrip("/")
    key = env.get("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not url or not key:
        path = INTEREST / "memberships_sync.sql"
        path.write_text(membership_sql(rows), encoding="utf-8")
        print(f"no service role key; wrote {path.relative_to(ROOT)}")
        return False
    accepted = accepted_rows(rows)
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    # Replace the three published categories. Draft stays empty.
    for slug in ("film-art-music", "whisky-distilleries", "for-sale"):
        delete_url = (
            f"{url}/rest/v1/interest_memberships?category_slug=eq.{urllib.parse.quote(slug)}"
        )
        req = urllib.request.Request(delete_url, headers=headers, method="DELETE")
        with urllib.request.urlopen(req, timeout=60):
            pass
    payload = []
    for item in accepted:
        payload.append(
            {
                "category_slug": item["category_slug"],
                "island_id": item["island_id"],
                "facet": item.get("facet"),
                "title": item["title"],
                "source_url": item["source_url"],
                "source_title": item.get("source_title") or None,
                "licence": item.get("licence") or None,
                "evidence": item.get("evidence") or None,
                "external_id": item.get("external_id") or None,
                "confidence": item.get("confidence") or "high",
                "status": "accepted",
            }
        )
    body = json.dumps(payload).encode("utf-8")
    insert_headers = dict(headers)
    insert_headers["Prefer"] = "return=minimal"
    req = urllib.request.Request(
        f"{url}/rest/v1/interest_memberships",
        data=body,
        headers=insert_headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120):
        pass
    print(f"supabase: upserted {len(payload)} accepted memberships")
    return True


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else "all"
    known = {"for-sale", "whisky", "culture", "publish", "sync", "all"}
    if command not in known:
        print(
            "usage: interest_categories.py [for-sale|whisky|culture|publish|sync|all]",
            file=sys.stderr,
        )
        return 2
    if command in ("publish", "sync"):
        rows = load_candidate_rows()
        publish(rows)
        sync_supabase(rows)
        return 0
    atlas = Atlas()
    print(f"atlas islands: {len(atlas.islands)}")
    rows: list[dict] = []
    if command in ("for-sale", "all"):
        rows.extend(populate_for_sale(atlas))
    if command in ("whisky", "all"):
        rows.extend(populate_whisky(atlas))
    if command in ("culture", "all"):
        rows.extend(populate_culture(atlas))
    if command == "all":
        publish(rows)
        sync_supabase(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
