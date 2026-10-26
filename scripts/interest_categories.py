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
        "blurb": "Islands tied to a specific film, artwork, band, or piece of music.",
        "sortOrder": 10,
    },
    {
        "slug": "whisky-distilleries",
        "label": "Whisky",
        "blurb": "Working distilleries, silent stills, and the whisky stories that name the island.",
        "sortOrder": 20,
        "subdivisions": [
            {
                "id": "islay",
                "label": "Islay",
                "match": "subdivision",
                "blurb": "A protected Scotch whisky region. These stills stand on Islay.",
            },
            {
                "id": "hebrides",
                "label": "Hebrides",
                "match": "subdivision",
                "blurb": "Island malts off the west of Scotland, outside the Islay region.",
            },
            {
                "id": "orkney",
                "label": "Orkney",
                "match": "subdivision",
                "blurb": "Whisky made on Orkney, including Sanday.",
            },
            {
                "id": "other",
                "label": "Other isles",
                "match": "subdivision",
                "blurb": "A still the source places on Shetland, and whiskey recorded on the Isle of Man.",
            },
            {
                "id": "silent",
                "label": "Silent stills",
                "match": "facet",
                "blurb": "Closed distilleries the source places on this island.",
            },
            {
                "id": "story",
                "label": "Stories",
                "match": "facet",
                "blurb": "A wreck, a film, or a festival that the source ties to this island.",
            },
            {
                "id": "planned",
                "label": "Planned",
                "match": "facet",
                "blurb": "Named on the island, and not yet making whisky.",
            },
        ],
    },
    {
        "slug": "for-sale",
        "label": "For sale",
        "blurb": "Islands with a current broker listing.",
        "sortOrder": 30,
    },
    {
        "slug": "unusual-wildlife",
        "label": "Unusual wildlife",
        "blurb": "Islands with a rare, endemic, or remarkable animal or plant.",
        "sortOrder": 25,
    },
    {
        "slug": "tidal-islands",
        "label": "Tidal islands",
        "blurb": "Islands joined to other land at low tide and cut off at high tide.",
        "sortOrder": 35,
    },
    {
        "slug": "island-castles",
        "label": "Islands with Castles",
        "blurb": "Islands with a castle standing on them.",
        "sortOrder": 40,
    },
    {
        "slug": "island-books",
        "label": "Books",
        "blurb": "Novels, memoirs, and stories set on the island.",
        "sortOrder": 22,
    },
    {
        "slug": "local-traditions",
        "label": "Local traditions",
        "blurb": "A custom, festival, dance, or craft the source places on the island.",
        "sortOrder": 24,
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


def http_json(
    url: str,
    data: bytes | None = None,
    headers: dict | None = None,
    timeout: int = 90,
    user_agent: str | None = None,
):
    """curl, not urllib: the system Python 3.9 SSL stack fails against some hosts."""
    cmd = [
        "curl",
        "-fsS",
        "--max-time",
        str(timeout),
        "-A",
        user_agent or USER_AGENT,
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
        exact_hits = []
        seen_exact = set()
        for name in names:
            if not name:
                continue
            target = fold(name)
            for island in self.islands:
                if fold(island["name"]) == target and island["id"] not in seen_exact:
                    seen_exact.add(island["id"])
                    exact_hits.append(island)
        chosen = self._prefer_largest(exact_hits)
        if chosen or exact_hits:
            return chosen
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
        return self._prefer_largest(hits)

    @staticmethod
    def _prefer_largest(hits: list[dict]) -> dict | None:
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
    summary: str = "",
    subdivision: str = "",
    skip_image: bool = False,
) -> dict:
    item = {
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
    if summary:
        item["summary"] = summary
    if subdivision:
        item["subdivision"] = subdivision
    if skip_image:
        item["skip_image"] = True
    return item


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


def _whisky_region(island_id: str, island_name: str) -> str:
    """Working-distillery subdivision. Silent stills, stories, and planned stills set their own."""
    name = fold(island_name)
    if island_id == "islay" or name == "islay":
        return "islay"
    # The large Sanday is the Orkney one. The small Sanday beside Canna is not.
    if island_id in {"mainland-orkney", "osm-relation-3075243"} or "orkney" in name:
        return "orkney"
    if island_id in {"osm-relation-376677", "mainland-shetland", "isle-of-man"} or name in {
        "shetland",
        "mainland",
        "isle of man",
        "achill island",
    }:
        if "shetland" in name or island_id in {"osm-relation-376677", "mainland-shetland"}:
            return "other"
        if name == "isle of man" or island_id == "isle-of-man" or name == "achill island":
            return "other"
    if island_id == "anglesey" or "anglesey" in name:
        return "other"
    return "hebrides"


def _stamp_whisky_subdivisions(rows: list[dict]) -> None:
    for item in rows:
        if item.get("status") != "accepted" or item.get("category_slug") != "whisky-distilleries":
            continue
        if item.get("subdivision"):
            continue
        if item.get("facet") != "distillery":
            continue
        item["subdivision"] = _whisky_region(item.get("island_id") or "", item.get("island_name") or "")


def _page_has(text: str, *needles: str) -> bool:
    folded = fold(text)
    return all(fold(needle) in folded for needle in needles if needle)


def _whisky_sentence(text: str, *needles: str) -> str:
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text or ""):
        if _page_has(sentence, *needles):
            return sentence.strip()
    return ""


def _expand_whisky(atlas: Atlas, rows: list[dict], add) -> None:
    """Silent stills, stories, and stills the source says are not yet whisky.

    A gin brand, a stalled plan, and a distillery whose site the page does not
    place on the island are left out. Barra's own article says the whisky
    still is under construction, so that row is not filed as a working distillery.
    """
    for item in rows:
        if item.get("status") != "accepted" or item.get("external_id") != "Isle_of_Barra_distillery":
            continue
        try:
            barra_text = wikipedia_plain("Isle of Barra distillery")
        except RuntimeError as exc:
            print(f"whisky barra reclassify skip: {exc}")
            break
        if _page_has(barra_text, "gin distillery", "planned", "whisky", "first whisky", "Barra"):
            item["facet"] = "planned"
            item["subdivision"] = "planned"
            item["confidence"] = "high"
            item["summary"] = (
                "The Isle of Barra distillery in Castlebay makes gin. "
                "A second distillery is being built on Barra so the island can start single malt whisky, "
                "which would be its first."
            )
            item["evidence"] = (
                "Wikipedia says the Castlebay site is a gin distillery and that a whisky distillery "
                "is still being built on Barra."
            )
        break

    def cited(island: dict | None, **kwargs) -> None:
        if island is None:
            return
        title = kwargs["title"]
        if any(
            r.get("status") == "accepted"
            and r.get("island_id") == island["id"]
            and name_key(r.get("title") or "") == name_key(title)
            for r in rows
        ):
            return
        add(
            row(
                category="whisky-distilleries",
                island_id=island["id"],
                island_name=island["name"],
                licence="CC BY-SA 4.0",
                status="accepted",
                **kwargs,
            )
        )

    try:
        islay_text = wikipedia_plain("Islay single malts")
    except RuntimeError as exc:
        print(f"whisky Islay page skip: {exc}")
        islay_text = ""
    islay = atlas.match_name("Islay")
    if islay_text and islay is not None and island_mentioned(islay, islay_text):
        silent = [
            (
                "Ardenistle distillery",
                ("Ardenistle", "Laphroaig"),
                "Ardenistle was a distillery on Islay from 1837. It was later called Kildalton, then Islay, and was taken into Laphroaig in 1853.",
            ),
            (
                "Ardmore (Islay)",
                ("Ardmore (1817", "Lagavulin"),
                "Ardmore was a distillery on Islay from 1817 to 1835. Lagavulin took it over in 1837.",
            ),
            (
                "Daill distillery",
                ("Daill", "Port Askaig", "Bridgend"),
                "Daill was a legal distillery on Islay from 1814 to 1830. The ruins are on the road between Port Askaig and Bridgend.",
            ),
            (
                "Kildalton distillery",
                ("Kildalton (1817", "Lagavulin"),
                "Kildalton was a distillery on Islay from 1817 to 1837, then merged with Lagavulin.",
            ),
            (
                "Killarow distillery",
                ("Killarow", "Bridgend"),
                "Killarow was a distillery on Islay from about 1760. From 1818 it was called Bridgend, and it closed in 1822. The ruins are in the village.",
            ),
            (
                "Lossit distillery",
                ("Lossit", "Ballygrant"),
                "Lossit, later called Ballygrant, was a distillery on Islay. It closed in 1860. The ruins are south of the village, beside the A846.",
            ),
            (
                "Malt Mill",
                ("Malt Mill", "Lagavulin"),
                "Malt Mill was a distillery on Islay from 1908 to 1962. The site is now part of Lagavulin.",
            ),
            (
                "Mulindry distillery",
                ("Mulindry", "Laggan"),
                "Mulindry was a distillery on Islay in 1826 and 1827, where the Neriby Burn meets the River Laggan. It is now in ruins.",
            ),
            (
                "Newton distillery (Islay)",
                ("Newton (1819", "Port Askaig", "Bridgend"),
                "Newton was a distillery on Islay from 1819 to 1837. The ruins are beside the road between Port Askaig and Bridgend.",
            ),
            (
                "Octomore distillery",
                ("Octomore (1816", "Port Charlotte"),
                "Octomore was a distillery on Islay from 1816 to 1852. The ruins are near Port Charlotte.",
            ),
            (
                "Tallant distillery",
                ("Tallant", "Bowmore"),
                "Tallant was a distillery on Islay from 1821 to 1852, at Tallant farm south of Bowmore.",
            ),
        ]
        for title, needles, summary in silent:
            if not _page_has(islay_text, *needles):
                print(f"whisky silent skip {title}: source page no longer has the place-names")
                continue
            cited(
                islay,
                facet="silent",
                subdivision="silent",
                title=title,
                source_url="https://en.wikipedia.org/wiki/Islay_single_malts",
                source_title="Islay single malts",
                external_id="Islay_single_malts",
                confidence="high",
                summary=summary,
                skip_image=True,
                evidence=(
                    "The Wikipedia article Islay single malts lists this closed distillery on Islay. "
                    + " ".join(needles)
                    + "."
                ),
            )
        if _page_has(islay_text, "protected by law", "23 distilleries", "Bowmore", "1779"):
            cited(
                islay,
                facet="story",
                subdivision="story",
                title="Islay single malts",
                source_url="https://en.wikipedia.org/wiki/Islay_single_malts",
                source_title="Islay single malts",
                external_id="Islay_single_malts",
                confidence="high",
                skip_image=True,
                summary=(
                    "Islay is one of five Scotch whisky regions whose name is protected by law. "
                    "The same article says as many as 23 distilleries once worked on the island, "
                    "and that Bowmore in 1779 is the oldest legal distillery on record there."
                ),
                evidence="Wikipedia article Islay single malts names the protected region, the closed count, and Bowmore.",
            )
        if _page_has(islay_text, "Fèis Ìle", "Islay"):
            cited(
                islay,
                facet="story",
                subdivision="story",
                title="Fèis Ìle",
                source_url="https://en.wikipedia.org/wiki/Islay_single_malts",
                source_title="Islay single malts",
                external_id="Islay_single_malts",
                confidence="high",
                skip_image=True,
                summary=(
                    "Islay hosts Fèis Ìle, a festival of malt and music, in the last week of May. "
                    "The tastings are part of the island's whisky year."
                ),
                evidence="Wikipedia article Islay single malts names Fèis Ìle on Islay.",
            )
        if _page_has(islay_text, "Portintruan", "Port Ellen", "Laphroaig"):
            cited(
                islay,
                facet="planned",
                subdivision="planned",
                title="Portintruan distillery",
                source_url="https://en.wikipedia.org/wiki/Islay_single_malts",
                source_title="Islay single malts",
                external_id="Islay_single_malts",
                confidence="medium",
                skip_image=True,
                summary=(
                    "Portintruan is a distillery being built on Islay, on the road between Port Ellen and Laphroaig. "
                    "The article records that work started in 2020. It is not a working distillery yet."
                ),
                evidence="Wikipedia article Islay single malts places Portintruan between Port Ellen and Laphroaig.",
            )
        if _page_has(islay_text, "Irish monks", "distill", "illegal whisky", "Islay"):
            cited(
                islay,
                facet="story",
                subdivision="story",
                title="Illicit stills on Islay",
                source_url="https://en.wikipedia.org/wiki/Islay_single_malts",
                source_title="Islay single malts",
                external_id="Islay_single_malts",
                confidence="high",
                skip_image=True,
                summary=(
                    "The Islay single malts article says Irish monks may have distilled on Islay in the early 1300s, "
                    "and that the island's early distilleries hid in glens and caves when the excise man came. "
                    "It also records home distilling, smuggling, and illegal whisky production, "
                    "and says the eight older legal distilleries began as illicit stills."
                ),
                evidence=(
                    "Wikipedia article Islay single malts places monastic distillation, smuggling, "
                    "and illegal whisky production on Islay."
                ),
            )

    try:
        kimbland_text = wikipedia_plain("Kimbland distillery")
    except RuntimeError as exc:
        print(f"whisky Kimbland page skip: {exc}")
        kimbland_text = ""
    if kimbland_text and _whisky_sentence(kimbland_text, "Lerwick Distillery", "Shetland", "whisky"):
        shetland = atlas.match_name("Shetland")
        if shetland is not None and island_mentioned(shetland, kimbland_text):
            cited(
                shetland,
                facet="distillery",
                subdivision="other",
                title="Lerwick Distillery",
                source_url="https://en.wikipedia.org/wiki/Kimbland_distillery",
                source_title="Kimbland distillery",
                external_id="Kimbland_distillery",
                confidence="medium",
                skip_image=True,
                summary=(
                    "The Kimbland article says the Lerwick Distillery was established in Shetland in 2022, "
                    "and that it took over the claim of most northerly Scotch whisky distillery."
                ),
                evidence=(
                    "Wikipedia's Kimbland distillery article says the Lerwick Distillery was established "
                    "in Shetland in 2022. Lerwick is the port on the island recorded here as Shetland."
                ),
            )
    deerness_sentence = _whisky_sentence(kimbland_text, "Deerness distillery", "Mainland", "Orkney")
    if deerness_sentence:
        orkney = atlas.match_name("Mainland (Orkney)")
        if orkney is not None and island_mentioned(orkney, deerness_sentence):
            cited(
                orkney,
                facet="distillery",
                subdivision="orkney",
                title="Deerness distillery",
                source_url="https://en.wikipedia.org/wiki/Kimbland_distillery",
                source_title="Kimbland distillery",
                external_id="Kimbland_distillery",
                confidence="medium",
                skip_image=True,
                summary=(
                    "Deerness distillery is in Deerness on Mainland, Orkney. "
                    "The Kimbland article describes it as a new Scotch whisky distillery, "
                    "announced as the first on Orkney since Scapa opened in 1885, a claim Kimbland disputed."
                ),
                evidence="Wikipedia's Kimbland distillery article places Deerness distillery in Deerness, Mainland, Orkney.",
            )

    try:
        manx_text = wikipedia_plain("Culture of the Isle of Man")
    except RuntimeError as exc:
        print(f"whisky Manx page skip: {exc}")
        manx_text = ""
    if _whisky_sentence(manx_text, "Isle of Man", "whiskey distillery", "Manx Whiskey Company"):
        man = atlas.match_name("Isle of Man")
        if man is not None:
            cited(
                man,
                facet="distillery",
                subdivision="other",
                title="Manx Whiskey Company",
                source_url="https://en.wikipedia.org/wiki/Culture_of_the_Isle_of_Man",
                source_title="Culture of the Isle of Man",
                external_id="Culture_of_the_Isle_of_Man",
                confidence="medium",
                skip_image=True,
                summary=(
                    "Wikipedia's article on the culture of the Isle of Man says that, as of 2019, "
                    "the island had a whiskey distillery run by the Manx Whiskey Company."
                ),
                evidence=(
                    "The culture article states that as of 2019 the Isle of Man had a whiskey distillery "
                    "run by the Manx Whiskey Company."
                ),
            )

    try:
        wreck_text = wikipedia_plain("SS Politician")
    except RuntimeError as exc:
        print(f"whisky Politician skip: {exc}")
        wreck_text = ""
    eriskay = atlas.match_name("Eriskay")
    if wreck_text and eriskay is not None and island_mentioned(eriskay, wreck_text) and _page_has(
        wreck_text, "whisky", "Eriskay"
    ):
        cited(
            eriskay,
            facet="story",
            subdivision="story",
            title="SS Politician",
            source_url="https://en.wikipedia.org/wiki/SS_Politician",
            source_title="SS Politician",
            external_id="SS_Politician",
            confidence="high",
            summary=(
                "SS Politician ran aground off Eriskay in 1941. Her cargo included 22,000 cases of Scotch whisky. "
                "Islanders salvaged whisky from the wreck, and Customs prosecuted them because the duty had not been paid."
            ),
            evidence="Wikipedia's SS Politician article places the wreck, and its whisky cargo, off Eriskay.",
        )

    try:
        film_text = wikipedia_plain("Whisky Galore! (1949 film)")
    except RuntimeError as exc:
        print(f"whisky Galore skip: {exc}")
        film_text = ""
    barra = atlas.match_name("Barra")
    if film_text and barra is not None and island_mentioned(barra, film_text) and _page_has(
        film_text, "Barra", "whisky", "filmed"
    ):
        cited(
            barra,
            facet="story",
            subdivision="story",
            title="Whisky Galore!",
            source_url="https://en.wikipedia.org/wiki/Whisky_Galore!_(1949_film)",
            source_title="Whisky Galore! (1949 film)",
            external_id="Whisky_Galore!_(1949_film)",
            confidence="high",
            summary=(
                "Whisky Galore! is the 1949 Ealing comedy about a shipwrecked cargo of whisky. "
                "It was filmed on Barra, and the story is drawn from the grounding of the SS Politician."
            ),
            evidence="Wikipedia's article on the 1949 film says it was filmed on Barra and that the cargo was whisky.",
        )

    try:
        lochranza_text = wikipedia_plain("Lochranza distillery")
    except RuntimeError as exc:
        print(f"whisky Lochranza skip: {exc}")
        lochranza_text = ""
    arran = atlas.match_name("Arran")
    if lochranza_text and arran is not None and island_mentioned(arran, lochranza_text):
        if _page_has(lochranza_text, "fifty", "illegal", "Arran"):
            cited(
                arran,
                facet="story",
                subdivision="story",
                title="Arran's illicit stills",
                source_url="https://en.wikipedia.org/wiki/Lochranza_distillery",
                source_title="Lochranza distillery",
                external_id="Lochranza_distillery",
                confidence="high",
                skip_image=True,
                summary=(
                    "The Lochranza distillery article says about fifty distilleries once stood on Arran, "
                    "and that most of them were moonlight or illegal stills."
                ),
                evidence="Wikipedia's Lochranza distillery article places those illegal stills on Arran.",
            )
        if _page_has(lochranza_text, "Lagg", "1837", "Arran", "2019"):
            cited(
                arran,
                facet="silent",
                subdivision="silent",
                title="Old Lagg distillery",
                source_url="https://en.wikipedia.org/wiki/Lochranza_distillery",
                source_title="Lochranza distillery",
                external_id="Lochranza_distillery",
                confidence="high",
                skip_image=True,
                summary=(
                    "The Lochranza distillery article says a legal distillery called Lagg on Arran closed in 1837. "
                    "The same article says a later distillery at Lagg, at the south end of the island, "
                    "began production in 2019. This row is the closed 1837 still."
                ),
                evidence=(
                    "Wikipedia's Lochranza distillery article says the legal distillery called Lagg on Arran closed in 1837."
                ),
            )

    try:
        bunna_text = wikipedia_plain("Bunnahabhain distillery")
    except RuntimeError as exc:
        print(f"whisky Bunnahabhain village skip: {exc}")
        bunna_text = ""
    if islay is not None and _page_has(bunna_text, "village of Bunnahabhain", "workers", "Islay", "1881"):
        cited(
            islay,
            facet="story",
            subdivision="story",
            title="Bunnahabhain village",
            source_url="https://en.wikipedia.org/wiki/Bunnahabhain_distillery",
            source_title="Bunnahabhain distillery",
            external_id="Bunnahabhain_distillery",
            confidence="high",
            skip_image=True,
            summary=(
                "Bunnahabhain distillery was founded in 1881 near Port Askaig on Islay. "
                "The village of Bunnahabhain was founded to house its workers."
            ),
            evidence="Wikipedia's Bunnahabhain distillery article places the village, built for the workers, on Islay.",
        )

    try:
        tobermory_text = wikipedia_plain("Tobermory distillery")
    except RuntimeError as exc:
        print(f"whisky Ledaig skip: {exc}")
        tobermory_text = ""
    mull = atlas.match_name("Mull")
    if mull is not None and island_mentioned(mull, tobermory_text) and _page_has(
        tobermory_text, "formerly known as Ledaig", "Mull", "peated"
    ):
        cited(
            mull,
            facet="story",
            subdivision="story",
            title="Ledaig",
            source_url="https://en.wikipedia.org/wiki/Tobermory_distillery",
            source_title="Tobermory distillery",
            external_id="Tobermory_distillery",
            confidence="high",
            skip_image=True,
            summary=(
                "Tobermory distillery on Mull opened in 1798 under the name Ledaig and later closed more than once. "
                "The peated whisky from the same still is still bottled as Ledaig."
            ),
            evidence=(
                "Wikipedia's Tobermory distillery article says the Mull distillery was formerly Ledaig "
                "and still uses that name for its peated whisky."
            ),
        )

    try:
        park_text = wikipedia_plain("Highland Park distillery")
    except RuntimeError as exc:
        print(f"whisky Highland Park story skip: {exc}")
        park_text = ""
    orkney_main = atlas.match_name("Mainland (Orkney)")
    # "on the Orkney Islands" does not match the bare "on Orkney" test.
    if orkney_main is not None and _page_has(
        park_text, "illegally distilling", "1798", "Kirkwall on the Orkney Islands"
    ):
        cited(
            orkney_main,
            facet="story",
            subdivision="story",
            title="Illicit still at Highland Park",
            source_url="https://en.wikipedia.org/wiki/Highland_Park_distillery",
            source_title="Highland Park distillery",
            external_id="Highland_Park_distillery",
            confidence="high",
            skip_image=True,
            summary=(
                "Highland Park stands in Kirkwall on Mainland, Orkney. "
                "The article says whisky was being distilled illegally on that site in 1798, "
                "and that the distillery received a licence in 1826."
            ),
            evidence=(
                "Wikipedia's Highland Park article places illegal distillation in 1798 "
                "on the Kirkwall site in Orkney."
            ),
        )

    try:
        novel_text = wikipedia_plain("Whisky Galore (novel)")
    except RuntimeError as exc:
        print(f"whisky novel skip: {exc}")
        novel_text = ""
    if novel_text and eriskay is not None and island_mentioned(eriskay, novel_text) and _page_has(
        novel_text, "Eriskay", "SS Politician", "malt whisky"
    ):
        cited(
            eriskay,
            facet="story",
            subdivision="story",
            title="Whisky Galore novel",
            source_url="https://en.wikipedia.org/wiki/Whisky_Galore_(novel)",
            source_title="Whisky Galore (novel)",
            external_id="Whisky_Galore_(novel)",
            confidence="high",
            skip_image=True,
            summary=(
                "Compton Mackenzie's novel Whisky Galore is based on the SS Politician running aground off Eriskay in 1941. "
                "The article says the cargo included 28,000 cases of malt whisky, and that Little Todday takes its geography from Eriskay."
            ),
            evidence="Wikipedia's article on the novel places the wreck it is based on off Eriskay, and Little Todday's geography on Eriskay.",
        )
    if novel_text and barra is not None and island_mentioned(barra, novel_text) and _page_has(
        novel_text, "Barra", "wrote the novel", "Isle of Barra"
    ):
        cited(
            barra,
            facet="story",
            subdivision="story",
            title="Whisky Galore novel",
            source_url="https://en.wikipedia.org/wiki/Whisky_Galore_(novel)",
            source_title="Whisky Galore (novel)",
            external_id="Whisky_Galore_(novel)",
            confidence="high",
            skip_image=True,
            summary=(
                "Compton Mackenzie wrote the novel Whisky Galore while living on Barra. "
                "The article says Great Todday takes its geography from Barra."
            ),
            evidence="Wikipedia's article on the novel says Mackenzie wrote it while living on Barra, and that Great Todday follows Barra.",
        )

    try:
        thorn_text = wikipedia_plain("Thorne Island")
    except RuntimeError as exc:
        print(f"whisky Loch Shiel skip: {exc}")
        thorn_text = ""
    thorn = atlas.match_name("Thorne Island")
    if (
        thorn is not None
        and thorn.get("id") == "osm-way-4001735"
        and island_mentioned(thorn, thorn_text)
        and _page_has(thorn_text, "Loch Shiel", "1894", "Scotch whisky", "Thorne Island")
    ):
        cited(
            thorn,
            facet="story",
            subdivision="story",
            title="Loch Shiel",
            source_url="https://en.wikipedia.org/wiki/Thorne_Island",
            source_title="Thorne Island",
            external_id="Thorne_Island",
            confidence="high",
            skip_image=True,
            summary=(
                "In 1894 the sailing ship Loch Shiel ran onto rocks off Thorne Island, at the mouth of Milford Haven. "
                "The island's Wikipedia article says she was carrying Scotch whisky from Scotland to Adelaide, "
                "including cases of Glasgow whisky, and that the rescue is remembered as Wales' Whisky Galore."
            ),
            evidence=(
                "Wikipedia's Thorne Island article says the 1894 Loch Shiel wreck off the island "
                "was carrying a cargo of Scotch whisky."
            ),
        )

    try:
        laggan_text = wikipedia_plain("Laggan Bay (винокурня)", lang="uk")
    except RuntimeError as exc:
        print(f"whisky Laggan Bay skip: {exc}")
        laggan_text = ""
    if islay is not None and _page_has(
        laggan_text, "Laggan Bay", "Айла", "віскі", "Bowmore", "Port Ellen", "2026"
    ):
        cited(
            islay,
            facet="distillery",
            subdivision="islay",
            title="Laggan Bay distillery",
            source_url="https://uk.wikipedia.org/wiki/Laggan_Bay_(%D0%B2%D0%B8%D0%BD%D0%BE%D0%BA%D1%83%D1%80%D0%BD%D1%8F)",
            source_title="Laggan Bay (винокурня)",
            external_id="Q141284142",
            confidence="medium",
            skip_image=True,
            summary=(
                "Laggan Bay is a malt whisky distillery on Islay, on the shore of Laggan Bay between Bowmore and Port Ellen, near the airport. "
                "The Ukrainian Wikipedia article says Ian Macleod Distillers opened it on 2 April 2026, "
                "and that it is the eleventh working distillery in the Islay region. "
                "Wikidata Q141284142 records the same still, on Islay, with no English Wikipedia article yet."
            ),
            evidence=(
                "Ukrainian Wikipedia places Laggan Bay distillery on Islay between Bowmore and Port Ellen. "
                "Wikidata Q141284142 is a whisky distillery at 55.6838,-6.2456."
            ),
        )

    try:
        nuns_text = wikipedia_plain("Nun's Island Distillery")
    except RuntimeError as exc:
        print(f"whisky Nun's Island skip: {exc}")
        nuns_text = ""
    # Galway's river island, not the lake islands that share the name.
    nuns = atlas.by_id.get("wd-Q59728286")
    if nuns is not None and _page_has(nuns_text, "Nun's Island", "Galway", "whiskey", "1908"):
        cited(
            nuns,
            facet="silent",
            subdivision="silent",
            title="Nun's Island Distillery",
            source_url="https://en.wikipedia.org/wiki/Nun%27s_Island_Distillery",
            source_title="Nun's Island Distillery",
            external_id="Nun's_Island_Distillery",
            confidence="high",
            skip_image=True,
            summary=(
                "Nun's Island Distillery made Irish whiskey on Nun's Island in Galway. "
                "The article says it was working from at least 1815, and possibly the late 1700s, until about 1908."
            ),
            evidence=(
                "Wikipedia's Nun's Island Distillery article places the Irish whiskey still "
                "on Nun's Island, Galway, and says production ceased about 1908."
            ),
        )

    try:
        welsh_text = wikipedia_plain("Welsh whisky")
    except RuntimeError as exc:
        print(f"whisky Anglesey skip: {exc}")
        welsh_text = ""
    anglesey = atlas.by_id.get("anglesey")
    if anglesey is not None and _page_has(
        welsh_text, "Anglesey Môn distillery", "Pentraeth", "on Anglesey", "2018"
    ):
        cited(
            anglesey,
            facet="distillery",
            subdivision="other",
            title="Anglesey Môn distillery",
            source_url="https://en.wikipedia.org/wiki/Welsh_whisky",
            source_title="Welsh whisky",
            external_id="Welsh_whisky",
            confidence="medium",
            skip_image=True,
            summary=(
                "The Welsh whisky article lists Anglesey Môn distillery near Pentraeth on Anglesey, "
                "established in 2018, among the working whisky distilleries in Wales as of December 2022. "
                "It has no article of its own."
            ),
            evidence=(
                "Wikipedia's Welsh whisky article places Anglesey Môn distillery near Pentraeth on Anglesey."
            ),
        )

    achill_placed = False
    for achill_title in ("List of whiskey distilleries in Ireland", "Irish whiskey", "Achill Island"):
        try:
            achill_text = wikipedia_plain(achill_title)
        except RuntimeError as exc:
            print(f"whisky Achill skip {achill_title}: {exc}")
            continue
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", achill_text or ""):
            low = fold(sentence)
            if "achill" not in low or "distill" not in low:
                continue
            if not re.search(r"\b(on|at) (the )?(island of )?achill\b", low):
                continue
            if "whisky" not in low and "whiskey" not in low:
                continue
            achill = atlas.match_name("Achill Island")
            if achill is None or not island_mentioned(achill, sentence):
                continue
            achill_placed = True
            cited(
                achill,
                facet="distillery",
                subdivision="other",
                title="Achill Island Distillery",
                source_url="https://en.wikipedia.org/wiki/" + urllib.parse.quote(achill_title.replace(" ", "_")),
                source_title=achill_title,
                external_id=achill_title.replace(" ", "_"),
                confidence="medium",
                summary=(
                    "Wikipedia places Achill Island Distillery on Achill Island. "
                    "It makes Irish whiskey."
                ),
                evidence=f"Wikipedia page {achill_title} places the distillery on Achill.",
            )
            break
        if achill_placed:
            break
    if not achill_placed:
        print("whisky Achill left out: no Wikipedia sentence places the still on the island")


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
        ("Benbecula Distillery", "Benbecula_distillery", ["Benbecula"]),
        ("Kimbland distillery", "Kimbland_distillery", ["Sanday"]),
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

    _expand_whisky(atlas, rows, add)
    _stamp_whisky_subdivisions(rows)

    write_candidates(
        "whisky-distilleries",
        rows,
        {
            "wikidata": len(wikidata),
            "overpass": len(overpass.get("elements") or []),
        },
    )
    return rows


def wikipedia_plain(title: str, lang: str = "en") -> str:
    cache_dir = DATA / "cache_wikipedia_interest"
    cache_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", title)[:120]
    if lang != "en":
        safe = f"{lang}_{safe}"
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
        api = WIKIPEDIA_API if lang == "en" else f"https://{lang}.wikipedia.org/w/api.php"
        url = api + "?" + urllib.parse.urlencode(params)
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


STORY_SLUGS = (
    "film-art-music",
    "whisky-distilleries",
    "unusual-wildlife",
    "tidal-islands",
    "island-castles",
    "island-books",
    "local-traditions",
)
MAPISH_IMAGE = re.compile(
    r"map|locator|range|distribution|diagram|chart|flag|coat[_ -]?of|\bcoa\b|icon|\.svg",
    re.I,
)
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
MEDIA_CACHE = DATA / "cache_wikipedia_interest" / "_media_index.json"
OPEN_IMAGE_LICENCE = re.compile(
    r"^(cc[ -]?0|cc[ -]?by([ -]sa)?([ -][0-9.]+)?|public domain|pd|pdm)\b",
    re.I,
)
CLOSED_IMAGE_LICENCE = re.compile(
    r"non-?commercial|\bno derivatives\b|\bfair use\b|\ball rights\b|(^|[^a-z])(nc|nd)([^a-z]|$)",
    re.I,
)


def _html_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#039;", "'")
    )
    return re.sub(r"\s+", " ", text).strip()


def _sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(
        r"\b[A-Za-z]\.(?:\s*[A-Za-z]\.)+",
        lambda match: match.group(0).replace(".", "§"),
        text,
    )
    text = re.sub(r"\b([A-Z])\.(?=\s+[a-z])", r"\1§", text)
    text = re.sub(r"\b(?:[A-Z]\.){2,}", lambda match: match.group(0).replace(".", "§"), text)
    text = re.sub(
        r"\b(Op|No|St|Dr|Mr|Mrs|Ms|Jr|Sr|vs|approx|var|sp|spp)\.",
        lambda match: match.group(0).replace(".", "§"),
        text,
    )
    parts = re.split(r"(?<=[.!?])\s+", text)
    cleaned = [part.replace("§", ".").strip() for part in parts]
    return [part for part in cleaned if len(part) > 40]


def _island_phrase(evidence: str) -> str:
    found = re.findall(r"'([^']+)'", evidence or "")
    if found:
        return found[-1]
    match = re.search(r"\band\s+(.+?)\.?$", evidence or "")
    return match.group(1).strip() if match else ""


def _island_in_sentence(island: str) -> str:
    name = (island or "").strip()
    low = name.lower()
    if low.startswith("the "):
        return name
    if low.startswith("isle ") or low.startswith("island "):
        return f"the {name}"
    return name


def _relation_clause(props: str, island: str) -> str:
    """A plain sentence for why a work belongs to the island."""
    place = _island_in_sentence(island)
    low = (props or "").lower()
    if "depict" in low:
        return f"It depicts {place}."
    if "main subject" in low:
        return f"The work takes {place} as its subject."
    if "named after" in low:
        return f"It is named after {place}."
    if "filming" in low:
        return f"It was filmed on {place}."
    if "narrative" in low:
        return f"It is set on {place}."
    if "creation" in low:
        return f"It was created on {place}."
    if "formation" in low:
        return f"It was formed on {place}."
    if "birth" in low:
        return f"The artist was born on {place}."
    if "work location" in low:
        return f"The artist worked on {place}."
    return f"It is connected with {place}."


def _readable_connection(text: str) -> str:
    """Turn 'X is a painting linked to Y (depicts)' into a sentence."""
    match = re.fullmatch(
        r"(.+?) is (an? .+?) linked to '([^']+)' \(([^)]+)\)\.?",
        (text or "").strip(),
    )
    if not match:
        return (text or "").strip()
    name, kind, island, props = match.groups()
    clause = _relation_clause(props, island)
    if clause.startswith("It "):
        return f"{name} is {kind} that {clause[3:]}"
    return f"{name} is {kind}. {clause}"


def _summarize(lead: str, full: str, title: str, phrase: str) -> str:
    """What the work is, then the sentence that ties it to the island."""
    island = phrase if phrase and phrase.lower() not in {"the island", "this island", "the work"} else ""
    sentences = _sentences(lead) or _sentences(full)
    title_parts = [part.strip() for part in re.split(r"[,:]", title or "") if len(part.strip()) > 3]

    def mentions_island(sentence: str) -> bool:
        return bool(island) and island.lower() in sentence.lower()

    def mentions_work(sentence: str) -> bool:
        low = sentence.lower()
        if title and title.lower() in low:
            return True
        return any(part.lower() in low for part in title_parts)

    identity = next((sentence for sentence in sentences if mentions_work(sentence)), "")
    connection = next(
        (
            sentence
            for sentence in sentences
            if mentions_island(sentence) and sentence != identity
        ),
        "",
    )
    chosen = [sentence for sentence in (identity, connection) if sentence]
    if not chosen and island:
        for sentence in _sentences(full):
            if mentions_island(sentence):
                chosen.append(sentence)
                break
    if not chosen:
        chosen = sentences[:2]
    text = " ".join(chosen[:2])
    if len(text) > 520:
        text = text[:500].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    return text


def _load_media_cache() -> dict:
    payload = load_json(MEDIA_CACHE, {})
    payload.setdefault("pages", {})
    payload.setdefault("files", {})
    return payload


def _wiki_query(endpoint: str, params: dict) -> dict:
    url = endpoint + "?" + urllib.parse.urlencode(params)
    for attempt in range(5):
        try:
            return http_json(url, timeout=45)
        except subprocess.CalledProcessError:
            wait = 12 * (attempt + 1)
            print(f"picture lookup waiting {wait}s after a rate limit", flush=True)
            time.sleep(wait)
    print(f"picture lookup skipped after a rate limit: {endpoint}", flush=True)
    return {}


def _page_records(titles: list[str], cache: dict) -> None:
    missing = []
    seen = set()
    for title in titles:
        key = fold(title)
        if not key or key in seen:
            continue
        seen.add(key)
        record = cache["pages"].get(key) or {}
        if record.get("extract") or record.get("absent"):
            continue
        missing.append(title.replace("_", " "))
    for start in range(0, len(missing), 16):
        batch = missing[start : start + 16]
        try:
            payload = _wiki_query(
                WIKIPEDIA_API,
                {
                    "action": "query",
                    "format": "json",
                    "redirects": "1",
                    "prop": "extracts|pageimages",
                    "exintro": "1",
                    "explaintext": "1",
                    "exchars": "900",
                    "piprop": "thumbnail|name",
                    "pithumbsize": "960",
                    "pilimit": "1",
                    "titles": "|".join(batch),
                },
            )
        except RuntimeError as exc:
            print(f"leaving {len(batch)} articles for a later picture pass: {exc}", flush=True)
            break
        if not payload.get("query"):
            print(f"leaving {len(batch)} articles for a later picture pass", flush=True)
            break
        query = payload.get("query") or {}
        redirect_of = {}
        for item in query.get("redirects") or []:
            redirect_of.setdefault(item.get("to"), []).append(item.get("from"))
        returned = list((query.get("pages") or {}).values())
        for page in returned:
            if page.get("missing") is not None:
                continue
            thumb = (page.get("thumbnail") or {}).get("source") or ""
            record = {
                "title": page.get("title") or "",
                "extract": page.get("extract") or "",
                "image": page.get("pageimage") or "",
                "thumb": thumb,
            }
            names = [page.get("title") or "", *(redirect_of.get(page.get("title")) or [])]
            if page.get("missing") is not None:
                for name in names:
                    if not name:
                        continue
                    key = fold(name)
                    if (cache["pages"].get(key) or {}).get("extract"):
                        continue
                    cache["pages"][key] = {
                        "title": name,
                        "extract": "",
                        "image": "",
                        "thumb": "",
                        "absent": True,
                        "imageChecked": True,
                    }
                continue
            for name in names:
                if name:
                    cache["pages"][fold(name)] = record
        for title in batch:
            key = fold(title)
            if (cache["pages"].get(key) or {}).get("extract"):
                continue
            cache["pages"].setdefault(
                key,
                {"title": title, "extract": "", "image": "", "thumb": "", "absent": True, "imageChecked": True},
            )
        save_json(MEDIA_CACHE, cache)
        time.sleep(1.1)


def _fill_images(titles: list[str], cache: dict) -> None:
    """Page images are a separate request. Combined with extracts, Wikipedia returns one picture."""
    missing = []
    seen = set()
    for title in titles:
        key = fold(title)
        if not key or key in seen:
            continue
        seen.add(key)
        record = cache["pages"].get(key) or {}
        if record.get("image") or record.get("imageChecked"):
            continue
        missing.append(title.replace("_", " "))
    for start in range(0, len(missing), 12):
        batch = missing[start : start + 12]
        try:
            payload = _wiki_query(
                WIKIPEDIA_API,
                {
                    "action": "query",
                    "format": "json",
                    "redirects": "1",
                    "prop": "pageimages",
                    "piprop": "thumbnail|name",
                    "pithumbsize": "960",
                    "titles": "|".join(batch),
                },
            )
        except RuntimeError as exc:
            print(f"leaving {len(batch)} pictures for a later pass: {exc}", flush=True)
            break
        if not payload.get("query"):
            print(f"leaving {len(batch)} pictures for a later pass", flush=True)
            break
        query = payload.get("query") or {}
        redirect_of = {}
        for item in query.get("redirects") or []:
            redirect_of.setdefault(item.get("to"), []).append(item.get("from"))
        seen_titles = set()
        for page in (query.get("pages") or {}).values():
            names = [page.get("title") or "", *(redirect_of.get(page.get("title")) or [])]
            thumb = (page.get("thumbnail") or {}).get("source") or ""
            image = "" if page.get("missing") is not None else (page.get("pageimage") or "")
            for name in names:
                if not name:
                    continue
                seen_titles.add(fold(name))
                record = cache["pages"].setdefault(fold(name), {"title": name, "extract": "", "image": "", "thumb": ""})
                record["image"] = image
                record["thumb"] = thumb
                record["imageChecked"] = True
        for title in batch:
            record = cache["pages"].setdefault(fold(title), {"title": title, "extract": "", "image": "", "thumb": ""})
            if fold(title) not in seen_titles:
                record["imageChecked"] = True
        save_json(MEDIA_CACHE, cache)
        time.sleep(1.2)


def _commons_records(filenames: list[str], cache: dict) -> None:
    missing = []
    for name in filenames:
        if not name:
            continue
        file_title = name if name.startswith("File:") else f"File:{name}"
        if file_title not in cache["files"]:
            missing.append(file_title)
    for start in range(0, len(missing), 16):
        batch = missing[start : start + 16]
        try:
            payload = _wiki_query(
                COMMONS_API,
                {
                    "action": "query",
                    "format": "json",
                    "prop": "imageinfo",
                    "iiprop": "url|extmetadata",
                    "iiurlwidth": "960",
                    "titles": "|".join(batch),
                },
            )
        except RuntimeError as exc:
            print(f"leaving {len(batch)} Commons files for a later pass: {exc}", flush=True)
            break
        if not (payload.get("query") or {}).get("pages"):
            print(f"leaving {len(batch)} Commons files for a later pass", flush=True)
            break
        for page in ((payload.get("query") or {}).get("pages") or {}).values():
            title = page.get("title") or ""
            info = (page.get("imageinfo") or [{}])[0]
            meta = info.get("extmetadata") or {}
            licence = _html_text((meta.get("LicenseShortName") or {}).get("value") or "")
            artist = _html_text((meta.get("Artist") or {}).get("value") or "")
            credit = _html_text((meta.get("Credit") or {}).get("value") or "")
            licence_url = (meta.get("LicenseUrl") or {}).get("value") or ""
            usable = bool(licence) and OPEN_IMAGE_LICENCE.search(licence) and not CLOSED_IMAGE_LICENCE.search(licence)
            cache["files"][title] = {
                "usable": usable,
                "thumbUrl": info.get("thumburl") or "",
                "pageUrl": info.get("descriptionurl") or "",
                "attribution": artist or credit or "Wikimedia Commons",
                "licence": licence,
                "licenceUrl": licence_url,
            }
        for title in batch:
            cache["files"].setdefault(
                title,
                {"usable": False, "thumbUrl": "", "pageUrl": "", "attribution": "", "licence": "", "licenceUrl": ""},
            )
        save_json(MEDIA_CACHE, cache)
        time.sleep(1.1)


def _distillery_story(lead: str, island: str) -> str:
    """Where the distillery is, then one sentence about what makes it notable."""
    sentences = _sentences(lead)
    if not sentences:
        return ""
    hints = (
        "oldest",
        "founded",
        "established",
        "first ",
        "peated",
        "northernmost",
        "classic malt",
        "shore",
        "coast",
        "only ",
        "legal",
    )
    named = []
    hinted = []
    for sentence in sentences[1:5]:
        low = sentence.lower()
        has_hint = any(hint in low for hint in hints)
        has_island = bool(island and island.lower() in low)
        if has_hint and has_island:
            named.append(sentence)
        elif has_hint:
            hinted.append(sentence)
    interesting = ""
    if named:
        interesting = named[0]
    elif hinted:
        interesting = hinted[0]
    elif len(sentences) > 1:
        interesting = sentences[1]
    identity = re.sub(r"\s*\([^)]{0,140}\)", "", sentences[0])
    identity = re.sub(r"\s{2,}", " ", identity).strip()
    notable_names_island = bool(interesting and island and island.lower() in interesting.lower())
    parts = [interesting, identity] if notable_names_island else [identity, interesting]
    parts = [part for part in parts if part]
    text = " ".join(part[:1].upper() + part[1:] if part else part for part in parts)
    if len(text) > 520:
        text = text[:500].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    return text


def _image_from_file(filename: str, cache: dict) -> dict | None:
    if not filename or MAPISH_IMAGE.search(filename):
        return None
    file_title = filename if filename.startswith("File:") else f"File:{filename}"
    candidates = (
        file_title,
        file_title.replace("_", " "),
        file_title.replace(" ", "_"),
    )
    usable = [cache["files"].get(key) or {} for key in candidates]
    file_info = next((info for info in usable if info.get("usable")), None) or {}
    if not (file_info.get("usable") and file_info.get("thumbUrl")):
        return None
    return {
        "thumbUrl": file_info["thumbUrl"],
        "pageUrl": file_info.get("pageUrl") or "",
        "attribution": file_info.get("attribution") or "Wikimedia Commons",
        "licence": file_info.get("licence") or "",
        "licenceUrl": file_info.get("licenceUrl") or "",
    }


def _wildlife_story(item: dict, cache: dict) -> dict:
    """The picture is the species. The paragraph is the one already checked against the source."""
    summary = re.sub(r"\s+", " ", (item.get("summary") or "")).strip()
    if len(summary) > 700:
        summary = summary[:680].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    filename = ""
    for label in (item.get("photo_title") or "", item.get("source_title") or "", item.get("title") or ""):
        page = cache["pages"].get(fold(label)) or {}
        candidate = page.get("image") or ""
        if candidate and not MAPISH_IMAGE.search(candidate):
            filename = candidate
            break
    if not filename:
        filename = item.get("commons_file") or ""
    source = item.get("source_title") or item.get("title") or ""
    source_url = item.get("source_url") or ""
    if "/wiki/" in source_url:
        source = urllib.parse.unquote(source_url.split("/wiki/", 1)[1]).replace("_", " ")
    return {
        "title": item.get("title") or "",
        "facet": "wildlife",
        "summary": summary,
        "sourceUrl": source_url,
        "sourceTitle": source,
        "image": _image_from_file(filename, cache),
    }


def _tidal_story(item: dict, cache: dict) -> dict:
    """The paragraph already says where the island joins, and that the link floods."""
    del cache
    summary = re.sub(r"\s+", " ", (item.get("summary") or "")).strip()
    if len(summary) > 700:
        summary = summary[:680].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    return {
        "title": item.get("title") or "",
        "facet": "tidal",
        "summary": summary,
        "sourceUrl": item.get("source_url") or "",
        "sourceTitle": item.get("source_title") or "Tidal island",
        "image": None,
    }


def _castle_story(item: dict, cache: dict) -> dict:
    """The picture is the castle. The paragraph already places it on the island."""
    summary = re.sub(r"\s+", " ", (item.get("summary") or "")).strip()
    if len(summary) > 700:
        summary = summary[:680].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    filename = item.get("commons_file") or ""
    if not filename or MAPISH_IMAGE.search(filename):
        filename = ""
        for label in (item.get("photo_title") or "", item.get("source_title") or "", item.get("title") or ""):
            page = cache["pages"].get(fold(label)) or {}
            candidate = page.get("image") or ""
            if candidate and not MAPISH_IMAGE.search(candidate):
                filename = candidate
                break
    source = item.get("source_title") or item.get("title") or ""
    source_url = item.get("source_url") or ""
    if "/wiki/" in source_url:
        source = urllib.parse.unquote(source_url.split("/wiki/", 1)[1]).replace("_", " ")
    return {
        "title": item.get("title") or "",
        "facet": "castle",
        "summary": summary,
        "sourceUrl": source_url,
        "sourceTitle": source,
        "image": _image_from_file(filename, cache),
    }


def _book_story(item: dict, cache: dict) -> dict:
    """The picture is the book, or a photograph of the island. The paragraph sets the book there."""
    summary = re.sub(r"\s+", " ", (item.get("summary") or "")).strip()
    if len(summary) > 700:
        summary = summary[:680].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    filename = item.get("commons_file") or ""
    if not filename or MAPISH_IMAGE.search(filename):
        filename = ""
        for label in (item.get("source_title") or "", item.get("title") or ""):
            page = cache["pages"].get(fold(label)) or {}
            candidate = page.get("image") or ""
            if candidate and not MAPISH_IMAGE.search(candidate):
                filename = candidate
                break
    image = _image_from_file(filename, cache)
    if image is None:
        supplied = item.get("open_image") or {}
        supplied_licence = supplied.get("licence") or ""
        supplied_url = supplied.get("thumbUrl") or ""
        if (
            supplied_url
            and supplied_licence
            and OPEN_IMAGE_LICENCE.search(supplied_licence)
            and not CLOSED_IMAGE_LICENCE.search(supplied_licence)
        ):
            image = {
                "thumbUrl": supplied_url,
                "pageUrl": supplied.get("pageUrl") or "",
                "attribution": supplied.get("attribution") or "Wikimedia Commons",
                "licence": supplied_licence,
                "licenceUrl": supplied.get("licenceUrl") or "",
                "note": item.get("image_note") or "Photograph of the island",
                "alt": item.get("island_name") or item.get("title") or "",
            }
    source = item.get("source_title") or item.get("title") or ""
    source_url = item.get("source_url") or ""
    if "/wiki/" in source_url:
        source = urllib.parse.unquote(source_url.split("/wiki/", 1)[1]).replace("_", " ")
    return {
        "title": item.get("title") or "",
        "facet": "book",
        "summary": summary,
        "sourceUrl": source_url,
        "sourceTitle": source,
        "image": image,
    }


def _tradition_story(item: dict, cache: dict) -> dict:
    """The picture is the custom, or a photograph of the island. The paragraph places it there."""
    story = _book_story(item, cache)
    story["facet"] = "tradition"
    tie = re.sub(r"\s+", " ", (item.get("tie") or "")).strip()
    if len(tie) > 420:
        tie = tie[:400].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    if tie:
        story["tie"] = tie
    return story


def _story_for(item: dict, cache: dict) -> dict:
    if item.get("facet") == "tradition":
        return _tradition_story(item, cache)
    if item.get("facet") == "book":
        return _book_story(item, cache)
    if item.get("facet") == "wildlife":
        return _wildlife_story(item, cache)
    if item.get("facet") == "tidal":
        return _tidal_story(item, cache)
    if item.get("facet") == "castle":
        return _castle_story(item, cache)
    phrase = item.get("island_name") or _island_phrase(item.get("evidence") or "")
    work = item.get("title") or ""
    source_url = item.get("source_url") or ""
    source = item.get("source_title") or work
    if "/wiki/" in source_url:
        source = urllib.parse.unquote(source_url.split("/wiki/", 1)[1]).replace("_", " ")
    work_page = cache["pages"].get(fold(work)) or {}
    source_page = cache["pages"].get(fold(source)) or {}
    # The cited article is the story. A title-only lookup can land on a
    # different page, such as a disambiguation or an unrelated work.
    summary_page = source_page if source_page.get("extract") else (work_page or source_page)
    if source_page.get("image"):
        image_page = source_page
    elif work_page.get("image"):
        image_page = work_page
    else:
        image_page = {}
    full = ""
    external_id = item.get("external_id") or ""
    # Wikidata ids and MusicBrainz uuids are not Wikipedia titles. Looking
    # them up asks for a page that does not exist and trips the rate limit.
    if external_id and not re.fullmatch(r"Q\d+", external_id) and not re.fullmatch(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        external_id,
    ):
        try:
            full = wikipedia_plain(external_id)
        except RuntimeError:
            full = ""
    summary = _summarize(
        (summary_page or {}).get("extract") or "",
        full,
        work,
        phrase,
    )
    connection = _readable_connection((item.get("summary") or "").strip())
    if connection and phrase and phrase.lower() not in summary.lower():
        summary = f"{summary} {connection}".strip() if summary else connection
    elif not summary:
        summary = connection
    summary = _readable_connection(summary)
    if item.get("facet") == "distillery":
        distilled = _distillery_story((summary_page or {}).get("extract") or "", phrase)
        if distilled:
            summary = distilled
    preset = re.sub(r"\s+", " ", (item.get("summary") or "")).strip()
    # Silent stills, stories, and stills cited from another article carry their own paragraph.
    # A Wikidata distillery has no preset, so its Wikipedia lead is still used.
    if preset and item.get("facet") in {"silent", "story", "planned", "distillery"}:
        summary = preset
    if len(summary) > 520:
        summary = summary[:500].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    image = None
    filename = (image_page or {}).get("image") or item.get("commons_file") or ""
    file_title = filename if filename.startswith("File:") else f"File:{filename}" if filename else ""
    file_info = {}
    if file_title:
        candidates = (
            file_title,
            file_title.replace("_", " "),
            file_title.replace(" ", "_"),
        )
        usable = [cache["files"].get(key) or {} for key in candidates]
        file_info = next((info for info in usable if info.get("usable")), None) or (usable[0] if usable else {})
    if file_info.get("usable") and file_info.get("thumbUrl"):
        image = {
            "thumbUrl": file_info["thumbUrl"],
            "pageUrl": file_info.get("pageUrl") or "",
            "attribution": file_info.get("attribution") or "Wikimedia Commons",
            "licence": file_info.get("licence") or "",
            "licenceUrl": file_info.get("licenceUrl") or "",
        }
    else:
        supplied = item.get("open_image") or {}
        supplied_licence = supplied.get("licence") or ""
        supplied_url = supplied.get("thumbUrl") or ""
        if (
            supplied_url
            and supplied_licence
            and OPEN_IMAGE_LICENCE.search(supplied_licence)
            and not CLOSED_IMAGE_LICENCE.search(supplied_licence)
        ):
            image = {
                "thumbUrl": supplied_url,
                "pageUrl": supplied.get("pageUrl") or item.get("source_url") or "",
                "attribution": supplied.get("attribution") or "Open collection",
                "licence": supplied_licence,
                "licenceUrl": supplied.get("licenceUrl") or "",
            }
    if item.get("facet") == "silent" or item.get("skip_image"):
        image = None
    source_title = (summary_page or {}).get("title") or source
    story = {
        "title": work,
        "facet": item.get("facet") or "",
        "summary": summary,
        "sourceUrl": item.get("source_url") or "",
        "sourceTitle": source_title,
        "image": image,
    }
    if item.get("subdivision"):
        story["subdivision"] = item["subdivision"]
    return story


def build_stories(accepted: list[dict]) -> dict:
    """Picture and cited lead for film, art, music, and distilleries."""
    wanted = [item for item in accepted if item.get("category_slug") in STORY_SLUGS]
    cache = _load_media_cache()
    titles = []
    for item in wanted:
        if item.get("facet") == "tidal":
            continue
        source_url = item.get("source_url") or ""
        if "/wiki/" in source_url:
            slug = urllib.parse.unquote(source_url.split("/wiki/", 1)[1])
            titles.append(slug.replace("_", " "))
        if item.get("source_title"):
            titles.append(item["source_title"])
        if item.get("title"):
            titles.append(item["title"])
        if item.get("photo_title"):
            titles.append(item["photo_title"])
    _page_records(titles, cache)
    _fill_images(titles, cache)
    filenames = [item.get("commons_file") or "" for item in wanted]
    for item in wanted:
        for name in (item.get("title"), item.get("source_title"), item.get("photo_title")):
            page = cache["pages"].get(fold(name or "")) or {}
            if page.get("image"):
                filenames.append(page["image"])
    _commons_records(filenames, cache)
    stories = {slug: {} for slug in STORY_SLUGS}
    for item in wanted:
        slug = item["category_slug"]
        island_id = item.get("island_id")
        if not island_id:
            continue
        story = _story_for(item, cache)
        bucket = stories[slug].setdefault(island_id, [])
        if any(existing["title"] == story["title"] for existing in bucket):
            continue
        bucket.append(story)
    with_image = sum(1 for slug in stories.values() for rows in slug.values() for row in rows if row.get("image"))
    total = sum(len(rows) for slug in stories.values() for rows in slug.values())
    print(f"stories: {total} cited, {with_image} with an open-licence picture")
    return stories


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
        "schemaVersion": 2,
        "generatedAt": utc_now(),
        "categories": categories,
        "members": members,
        "highlights": highlights,
        "stories": build_stories(accepted),
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
    chunks = [
        "alter table public.interest_memberships drop constraint if exists interest_memberships_facet_check;",
        "alter table public.interest_memberships add constraint interest_memberships_facet_check "
        "check (facet is null or facet in ('film', 'artwork', 'music', 'distillery', 'listing', 'wildlife', 'tidal', 'silent', 'story', 'planned', 'castle', 'book', 'tradition'));",
        "insert into public.interest_categories "
        "(slug, label, blurb, status, sort_order, populator, acceptance_rules) values ("
        "'whisky-distilleries', 'Whisky', "
        "'Working distilleries, silent stills, and the whisky stories that name the island.', "
        "'published', 20, 'wikidata_and_wikipedia', "
        "'The still is on the island. A working distillery, a silent still the source places on the island, "
        "a still the source says is not yet producing, or a whisky story (wreck, film, or festival) whose page names the island. "
        "Gin, a stalled plan, a brand whose still is elsewhere, and a closed site the page cannot locate are out.'"
        ") on conflict (slug) do update set label = excluded.label, blurb = excluded.blurb, "
        "status = 'published', sort_order = excluded.sort_order, populator = excluded.populator, "
        "acceptance_rules = excluded.acceptance_rules;",
        "insert into public.interest_categories "
        "(slug, label, blurb, status, sort_order, populator, acceptance_rules) values ("
        "'unusual-wildlife', 'Unusual wildlife', "
        "'Islands with a rare, endemic, or remarkable animal or plant.', "
        "'published', 25, 'cited_research', "
        "'A Wikipedia, Wikidata, or Open Government Licence page names the species and the island. "
        "The species is endemic, named for the island, or a principal stronghold. "
        "No colony coordinates, nest counts, or visit advice. The picture is of the species.'"
        ") on conflict (slug) do update set label = excluded.label, blurb = excluded.blurb, "
        "status = 'published', sort_order = excluded.sort_order, populator = excluded.populator, "
        "acceptance_rules = excluded.acceptance_rules;",
        "insert into public.interest_categories "
        "(slug, label, blurb, status, sort_order, populator, acceptance_rules) values ("
        "'tidal-islands', 'Tidal islands', "
        "'Islands joined to other land at low tide and cut off at high tide.', "
        "'published', 35, 'wikipedia_tidal_island', "
        "'The English Wikipedia article Tidal island names the island for Britain, Ireland, "
        "Guernsey, or Jersey, and the link is exposed at low tide and submerged at high tide. "
        "A permanent causeway named on that page is out. No crossing times.'"
        ") on conflict (slug) do update set label = excluded.label, blurb = excluded.blurb, "
        "status = 'published', sort_order = excluded.sort_order, populator = excluded.populator, "
        "acceptance_rules = excluded.acceptance_rules;",
        "insert into public.interest_categories "
        "(slug, label, blurb, status, sort_order, populator, acceptance_rules) values ("
        "'island-castles', 'Islands with Castles', "
        "'Islands with a castle standing on them.', "
        "'published', 40, 'cited_castle', "
        "'A castle stands on the atlas island. The citation is English Wikipedia, Wikidata, "
        "OpenStreetMap, Canmore, the National Heritage List for England, Cadw, or the "
        "Archaeological Survey of Ireland. A martello tower, a broch, and a fort do not count. "
        "Great Britain and Ireland do not count. No living owner, private address, or way in.'"
        ") on conflict (slug) do update set label = excluded.label, blurb = excluded.blurb, "
        "status = 'published', sort_order = excluded.sort_order, populator = excluded.populator, "
        "acceptance_rules = excluded.acceptance_rules;",
        "insert into public.interest_categories "
        "(slug, label, blurb, status, sort_order, populator, acceptance_rules) values ("
        "'island-books', 'Books', "
        "'Novels, memoirs, and stories set on the island.', "
        "'published', 22, 'cited_book', "
        "'The English Wikipedia article sets the book on the atlas island. "
        "Inspired by, based on, and filmed on do not count. "
        "Great Britain and Ireland do not count. The picture is an open-licence image of the book, "
        "or a photograph of the island when the cover is not open.'"
        ") on conflict (slug) do update set label = excluded.label, blurb = excluded.blurb, "
        "status = 'published', sort_order = excluded.sort_order, populator = excluded.populator, "
        "acceptance_rules = excluded.acceptance_rules;",
        "insert into public.interest_categories "
        "(slug, label, blurb, status, sort_order, populator, acceptance_rules) values ("
        "'local-traditions', 'Local traditions', "
        "'A custom, festival, dance, or craft the source places on the island.', "
        "'published', 24, 'cited_tradition', "
        "'The English Wikipedia article describes the custom and places it on the atlas island. "
        "The summary is the article''s own sentences. A legend with no practice, a breed, a book, "
        "a film, and a monastic pilgrimage do not count. Great Britain and Ireland do not count. "
        "The picture is an open-licence photograph of the custom, or of the island when the article has none.'"
        ") on conflict (slug) do update set label = excluded.label, blurb = excluded.blurb, "
        "status = 'published', sort_order = excluded.sort_order, populator = excluded.populator, "
        "acceptance_rules = excluded.acceptance_rules;",
        "delete from public.interest_memberships where category_slug in "
        "('film-art-music','whisky-distilleries','for-sale','unusual-wildlife','tidal-islands','island-castles','island-books','local-traditions');",
    ]
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
    for slug in ("film-art-music", "whisky-distilleries", "for-sale", "unusual-wildlife", "tidal-islands", "island-castles", "island-books", "local-traditions"):
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


MB_API = "https://musicbrainz.org/ws/2"
MB_USER_AGENT = "IslesOfBritain/0.1 ( https://www.findmyisland.com )"
MB_CACHE = DATA / "cache_musicbrainz_interest"
WIKIDATA_CULTURE_CACHE = DATA / "cache_wikidata_culture_open.json"
WIKIDATA_PLACE_CACHE = DATA / "cache_wikidata_place_classes.json"
OPEN_CULTURE_VERSION = 1

# Direct Wikidata links only. "Inspired by the region" is not a property we query.
WORK_TYPES = {
    "Q7366": ("music", "song"),
    "Q482994": ("music", "album"),
    "Q134556": ("music", "single"),
    "Q34627": ("music", "EP"),
    "Q215380": ("music", "musical group"),
    "Q3305213": ("artwork", "painting"),
    "Q860861": ("artwork", "sculpture"),
    "Q93184": ("artwork", "drawing"),
    "Q11060274": ("artwork", "print"),
}
HUMAN_OCCS = {
    "Q639669": ("music", "musician"),
    "Q177220": ("music", "singer"),
    "Q36834": ("music", "composer"),
    "Q488205": ("music", "singer-songwriter"),
    "Q855091": ("music", "guitarist"),
    "Q1028181": ("artwork", "painter"),
    "Q1281618": ("artwork", "sculptor"),
    "Q3391743": ("artwork", "visual artist"),
}
PLACE_PROPS = {
    "P921": "main subject",
    "P180": "depicts",
    "P840": "narrative location",
    "P915": "filming location",
    "P138": "named after",
    "P740": "location of formation",
    "P1071": "location of creation",
    "P19": "place of birth",
    "P937": "work location",
}
MB_REGION_NAMES = {
    "united kingdom",
    "uk",
    "ireland",
    "republic of ireland",
    "northern ireland",
    "scotland",
    "england",
    "wales",
    "isle of man",
    "jersey",
    "guernsey",
    "orkney",
    "shetland",
    "outer hebrides",
    "inner hebrides",
    "hebrides",
    "channel islands",
    "na h-eileanan siar",
}
MB_CHILD_TYPES = {"City", "Town", "Village", "Municipality", "District", "Parish"}
ISLAND_TYPE_WORDS = ("island", "islet", "skerry", "holm", "ait", "eyot", "stack", "rock")
SETTLEMENT_TYPE_WORDS = (
    "city",
    "town",
    "village",
    "human settlement",
    "big city",
    "civil parish",
    "suburb",
    "borough",
    "community",
    "neighbourhood",
)
OK_COUNTRY_LABELS = {
    "united kingdom",
    "ireland",
    "republic of ireland",
    "scotland",
    "england",
    "wales",
    "northern ireland",
    "isle of man",
    "jersey",
    "guernsey",
    "bailiwick of guernsey",
    "bailiwick of jersey",
}
MB_SKIP_AREA_NAMES = {
    "great britain",
    "britain",
    "ireland",
    "united kingdom",
    "england",
    "scotland",
    "wales",
    "island",
    "islands",
}


def _wikidata_sparql(query: str) -> dict:
    body = urllib.parse.urlencode({"format": "json", "query": query}).encode("utf-8")
    last_error = None
    for attempt in range(4):
        try:
            return http_json(
                WIKIDATA_ENDPOINT,
                data=body,
                headers={
                    "Accept": "application/sparql-results+json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                timeout=120,
            )
        except subprocess.CalledProcessError as exc:
            last_error = exc
            print(f"wikidata attempt {attempt + 1} failed: {exc.returncode}")
            time.sleep(15 * (attempt + 1))
    raise RuntimeError(f"Wikidata request failed: {last_error}")


def _qid(value: str) -> str:
    return (value or "").rstrip("/").rsplit("/", 1)[-1]


def _commons_file(url: str) -> str:
    if not url:
        return ""
    name = urllib.parse.unquote(url.rstrip("/").rsplit("/", 1)[-1]).replace("_", " ")
    if not name or name.lower() in {"special:filepath", "wiki"}:
        return ""
    return name if name.startswith("File:") else f"File:{name}"


def _atlas_qids(atlas: Atlas) -> dict[str, dict]:
    islands = load_json(DATA / "islands.json", [])
    mapping: dict[str, dict] = {}
    for island in islands:
        qid = island.get("wikidata") or ""
        if not qid.startswith("Q"):
            continue
        area = island.get("areaKm2") or 0
        if area > 8000:
            continue
        known = atlas.by_id.get(island.get("id"))
        if not known:
            continue
        previous = mapping.get(qid)
        if previous and (previous.get("area") or 0) >= (known.get("area") or 0):
            continue
        mapping[qid] = known
    return mapping


def _culture_query(qids: list[str]) -> str:
    places = " ".join(f"wd:{qid}" for qid in qids)
    work_types = " ".join(f"wd:{qid}" for qid in WORK_TYPES)
    occupations = " ".join(f"wd:{qid}" for qid in HUMAN_OCCS)
    return f"""
SELECT DISTINCT ?work ?workLabel ?place ?type ?article ?mbArtist ?image ?direct WHERE {{
  VALUES ?place {{ {places} }}
  {{
    VALUES ?direct {{ wdt:P921 wdt:P180 wdt:P840 wdt:P915 wdt:P138 wdt:P740 wdt:P1071 }}
    ?work ?direct ?place .
    ?work wdt:P31 ?type .
    VALUES ?type {{ {work_types} }}
  }} UNION {{
    VALUES ?direct {{ wdt:P19 wdt:P937 }}
    ?work ?direct ?place .
    ?work wdt:P31 wd:Q5 .
    ?work wdt:P106 ?type .
    VALUES ?type {{ {occupations} }}
  }}
  OPTIONAL {{ ?article schema:about ?work ; schema:isPartOf <https://en.wikipedia.org/> . }}
  OPTIONAL {{ ?work wdt:P434 ?mbArtist }}
  OPTIONAL {{ ?work wdt:P18 ?image }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
"""


def _binding_row(binding: dict) -> dict:
    direct = binding.get("direct", {}).get("value") or ""
    return {
        "work": _qid(binding.get("work", {}).get("value") or ""),
        "label": binding.get("workLabel", {}).get("value") or "",
        "place": _qid(binding.get("place", {}).get("value") or ""),
        "type": _qid(binding.get("type", {}).get("value") or ""),
        "article": binding.get("article", {}).get("value") or "",
        "mb": binding.get("mbArtist", {}).get("value") or "",
        "image": binding.get("image", {}).get("value") or "",
        "prop": direct.rsplit("/", 1)[-1],
    }


def fetch_wikidata_culture(qids: list[str]) -> list[dict]:
    cache = load_json(WIKIDATA_CULTURE_CACHE, {})
    if cache.get("version") != OPEN_CULTURE_VERSION:
        cache = {"version": OPEN_CULTURE_VERSION, "batches": {}}
    batches = cache.setdefault("batches", {})
    ordered = sorted(set(qids))
    pending = [ordered[start : start + 30] for start in range(0, len(ordered), 30)]
    print(f"wikidata culture: {len(ordered)} islands, {len(pending)} batches")
    for index, batch in enumerate(pending, start=1):
        key = ",".join(batch)
        if key in batches:
            continue
        rows: list[dict] | None = None
        chunks = [batch]
        while chunks:
            chunk = chunks.pop(0)
            try:
                payload = _wikidata_sparql(_culture_query(chunk))
            except RuntimeError:
                if len(chunk) > 6:
                    mid = len(chunk) // 2
                    chunks.append(chunk[:mid])
                    chunks.append(chunk[mid:])
                    print(f"splitting a Wikidata batch of {len(chunk)}")
                    continue
                print(f"skipping Wikidata batch of {len(chunk)} after repeated failures")
                payload = {"results": {"bindings": []}}
            rows_chunk = [_binding_row(binding) for binding in payload.get("results", {}).get("bindings", [])]
            if rows is None:
                rows = []
            rows.extend(rows_chunk)
            time.sleep(1.2)
        batches[key] = rows or []
        save_json(WIKIDATA_CULTURE_CACHE, cache)
        print(f"wikidata batch {index}/{len(pending)}: {len(batches[key])} links")
    found = []
    for rows in batches.values():
        found.extend(rows)
    return found


def _facet_and_kinds(types: list[str]) -> tuple[str, str]:
    music = []
    art = []
    for type_id in types:
        if type_id in HUMAN_OCCS and HUMAN_OCCS[type_id][0] == "music":
            music.append(HUMAN_OCCS[type_id][1])
        elif type_id in WORK_TYPES and WORK_TYPES[type_id][0] == "music":
            music.append(WORK_TYPES[type_id][1])
        elif type_id in HUMAN_OCCS:
            art.append(HUMAN_OCCS[type_id][1])
        elif type_id in WORK_TYPES:
            art.append(WORK_TYPES[type_id][1])
    kinds = list(dict.fromkeys(music or art))
    facet = "music" if music else "artwork"
    return facet, ", ".join(kinds)


def _label_has_word(label: str, words: tuple[str, ...]) -> bool:
    low = fold(label)
    return any(re.search(rf"\b{re.escape(word)}\b", low) for word in words)


def fetch_island_place_qids(qids: list[str]) -> set[str]:
    """Keep QIDs that are islands in Britain or Ireland.

    Some river-island records reuse a town QID (Oxford the city, not an ait).
    A town QID would pull in every painter born there.
    """
    cache = load_json(WIKIDATA_PLACE_CACHE, {})
    if cache.get("version") != OPEN_CULTURE_VERSION:
        cache = {"version": OPEN_CULTURE_VERSION, "places": {}}
    places = cache.setdefault("places", {})
    missing = [qid for qid in sorted(set(qids)) if qid not in places]
    print(f"checking {len(missing)} Wikidata places")
    for start in range(0, len(missing), 40):
        batch = missing[start : start + 40]
        values = " ".join(f"wd:{qid}" for qid in batch)
        query = f"""
SELECT ?place ?typeLabel ?countryLabel WHERE {{
  VALUES ?place {{ {values} }}
  OPTIONAL {{ ?place wdt:P31 ?type }}
  OPTIONAL {{ ?place wdt:P17 ?country }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
"""
        try:
            payload = _wikidata_sparql(query)
        except RuntimeError:
            print("place check failed for a batch; those islands are left out this run")
            continue
        grouped: dict[str, dict] = {}
        for binding in payload.get("results", {}).get("bindings", []):
            qid = _qid(binding.get("place", {}).get("value") or "")
            slot = grouped.setdefault(qid, {"types": [], "countries": []})
            type_label = binding.get("typeLabel", {}).get("value") or ""
            country = binding.get("countryLabel", {}).get("value") or ""
            if type_label and type_label not in slot["types"]:
                slot["types"].append(type_label)
            if country and country not in slot["countries"]:
                slot["countries"].append(country)
        for qid in batch:
            slot = grouped.get(qid) or {"types": [], "countries": []}
            types = slot["types"]
            countries = {fold(name) for name in slot["countries"]}
            islandish = any(_label_has_word(label, ISLAND_TYPE_WORDS) for label in types)
            settlement = any(_label_has_word(label, SETTLEMENT_TYPE_WORDS) for label in types)
            country_ok = not countries or bool(countries & OK_COUNTRY_LABELS)
            places[qid] = bool(islandish and country_ok and not (settlement and not islandish))
        save_json(WIKIDATA_PLACE_CACHE, cache)
        time.sleep(1.2)
    return {qid for qid, ok in places.items() if ok}


def _wikidata_rows(
    raw: list[dict],
    by_qid: dict[str, dict],
    seen: set[tuple[str, str]],
    island_qids: set[str],
) -> list[dict]:
    grouped: dict[tuple[str, str], dict] = {}
    for item in raw:
        if item["work"] == item["place"] or item["prop"] not in PLACE_PROPS:
            continue
        if item["place"] not in island_qids:
            continue
        island = by_qid.get(item["place"])
        if not island:
            continue
        label = (item.get("label") or "").strip()
        if not label or re.fullmatch(r"Q\d+", label):
            continue
        if re.search(r"\bpossibly\b", label, re.I):
            continue
        bucket = grouped.setdefault(
            (item["work"], item["place"]),
            {"item": item, "types": [], "props": [], "island": island},
        )
        if item["type"] and item["type"] not in bucket["types"]:
            bucket["types"].append(item["type"])
        if item["prop"] not in bucket["props"]:
            bucket["props"].append(item["prop"])
        if item.get("article"):
            bucket["item"]["article"] = item["article"]
        if item.get("mb"):
            bucket["item"]["mb"] = item["mb"]
        if item.get("image"):
            bucket["item"]["image"] = item["image"]
    rows = []
    for bucket in grouped.values():
        item = bucket["item"]
        island = bucket["island"]
        human = any(type_id in HUMAN_OCCS for type_id in bucket["types"])
        if human and not item.get("article") and not item.get("mb"):
            continue
        if human and not any(prop in {"P19", "P937"} for prop in bucket["props"]):
            continue
        facet, kind = _facet_and_kinds(bucket["types"])
        if not kind:
            continue
        key = (island["id"], fold(item["label"]))
        if key in seen:
            continue
        seen.add(key)
        props = " and ".join(PLACE_PROPS[prop] for prop in bucket["props"] if prop in PLACE_PROPS)
        island_name = island["name"]
        article = item.get("article") or ""
        mb = item.get("mb") or ""
        if article:
            source_url = article
            licence = "CC BY-SA 4.0"
        elif mb:
            source_url = f"https://musicbrainz.org/artist/{mb}"
            licence = "CC0"
        else:
            source_url = f"https://www.wikidata.org/wiki/{item['work']}"
            licence = "CC0"
        article_word = "an" if fold(kind)[:1] in "aeiou" else "a"
        summary = f"{item['label']} is {article_word} {kind} linked to '{island_name}' ({props})."
        evidence = f"Wikidata {item['work']}: {kind}; {props} '{island_name}'."
        if mb:
            evidence += f" MusicBrainz artist {mb}."
        built = row(
            category="film-art-music",
            island_id=island["id"],
            island_name=island_name,
            facet=facet,
            title=item["label"],
            source_url=source_url,
            source_title=urllib.parse.unquote(article.rsplit("/", 1)[-1]).replace("_", " ") if article else item["label"],
            licence=licence,
            evidence=evidence,
            status="accepted",
            confidence="high",
        )
        built["summary"] = summary
        built["commons_file"] = _commons_file(item.get("image") or "")
        rows.append(built)
    return rows


def _mb_get(path: str) -> dict:
    MB_CACHE.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", path)[:180]
    cache_path = MB_CACHE / f"{safe}.json"
    if cache_path.exists():
        return load_json(cache_path, {})
    url = MB_API + path
    payload = {}
    ok = False
    for attempt in range(4):
        try:
            payload = http_json(url, timeout=60, user_agent=MB_USER_AGENT)
            ok = True
            break
        except subprocess.CalledProcessError as exc:
            print(f"musicbrainz attempt {attempt + 1} failed: {exc.returncode} {path[:80]}")
            time.sleep(5 * (attempt + 1))
    if ok:
        save_json(cache_path, payload)
    time.sleep(1.1)
    return payload


def _mb_ancestors(area_id: str, depth: int = 0) -> list[str]:
    if depth > 6 or not area_id:
        return []
    area = _mb_get(f"/area/{area_id}?inc=area-rels&fmt=json")
    names = []
    for rel in area.get("relations") or []:
        if rel.get("type") != "part of" or rel.get("direction") != "backward":
            continue
        parent = rel.get("area") or {}
        name = parent.get("name") or ""
        if name:
            names.append(name)
        names.extend(_mb_ancestors(parent.get("id") or "", depth + 1))
    return names


def _mb_child_ids(area_id: str) -> list[str]:
    area = _mb_get(f"/area/{area_id}?inc=area-rels&fmt=json")
    children = []
    for rel in area.get("relations") or []:
        if rel.get("type") != "part of" or rel.get("direction") != "forward":
            continue
        child = rel.get("area") or {}
        if child.get("type") in MB_CHILD_TYPES and child.get("id"):
            children.append(child["id"])
    return children[:25]


def _mb_artists(area_id: str) -> list[dict]:
    found = []
    offset = 0
    total = None
    while total is None or offset < total:
        payload = _mb_get(f"/artist?area={area_id}&fmt=json&limit=100&offset={offset}")
        batch = payload.get("artists") or []
        found.extend(batch)
        total = int(payload.get("artist-count") or len(found))
        offset += 100
        if not batch or offset >= 100:
            break
    return found


def _island_for_mb_area(atlas: Atlas, name: str, ancestors: list[str]) -> dict | None:
    if fold(name) in MB_SKIP_AREA_NAMES:
        return None
    region_names = {fold(name), *(fold(part) for part in ancestors)}
    if not region_names & MB_REGION_NAMES:
        return None
    options = []
    if any("orkney" in fold(part) for part in ancestors):
        options.append(f"{name} (Orkney)")
    elif any("shetland" in fold(part) for part in ancestors):
        options.append(f"{name} (Shetland)")
    options.extend([name, f"Isle of {name}", f"Island of {name}", f"Ynys {name}"])
    island = atlas.match_name(*options)
    if not island or (island.get("area") or 0) > 8000:
        return None
    return island


def _enrich_musicbrainz(artists: list[dict]) -> dict[str, dict]:
    """Wikipedia article and Commons file for a MusicBrainz artist id, via Wikidata."""
    cache_path = DATA / "cache_wikidata_mb_artists.json"
    cache = load_json(cache_path, {})
    if cache.get("version") != OPEN_CULTURE_VERSION:
        cache = {"version": OPEN_CULTURE_VERSION, "artists": {}}
    known = cache.setdefault("artists", {})
    missing = []
    seen = set()
    for artist in artists:
        mbid = artist.get("id") or ""
        if mbid and mbid not in known and mbid not in seen:
            seen.add(mbid)
            missing.append(mbid)
    print(f"wikidata lookup for {len(missing)} MusicBrainz artists")
    for start in range(0, len(missing), 40):
        batch = missing[start : start + 40]
        values = " ".join(f'"{mbid}"' for mbid in batch)
        query = f"""
SELECT ?item ?article ?image ?mb WHERE {{
  VALUES ?mb {{ {values} }}
  ?item wdt:P434 ?mb .
  OPTIONAL {{ ?article schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> . }}
  OPTIONAL {{ ?item wdt:P18 ?image }}
}}
"""
        try:
            payload = _wikidata_sparql(query)
        except RuntimeError:
            print("wikidata lookup failed for a MusicBrainz batch; it will be retried next run")
            continue
        found_ids = set()
        for binding in payload.get("results", {}).get("bindings", []):
            mbid = binding.get("mb", {}).get("value") or ""
            if not mbid:
                continue
            found_ids.add(mbid)
            current = known.get(mbid) or {}
            article = binding.get("article", {}).get("value") or ""
            image = binding.get("image", {}).get("value") or ""
            if article and not current.get("article"):
                current["article"] = article
            if image and not current.get("image"):
                current["image"] = image
            current["qid"] = _qid(binding.get("item", {}).get("value") or "")
            known[mbid] = current
        for mbid in batch:
            known.setdefault(mbid, {})
            if mbid not in found_ids and mbid not in known:
                known[mbid] = {}
        save_json(cache_path, cache)
        time.sleep(1.2)
    return known


def _musicbrainz_rows(atlas: Atlas, seen: set[tuple[str, str]]) -> list[dict]:
    areas = []
    offset = 0
    total = None
    while total is None or offset < total:
        payload = _mb_get(f"/area?query=type:island&fmt=json&limit=100&offset={offset}")
        batch = payload.get("areas") or []
        areas.extend(batch)
        total = int(payload.get("count") or len(areas))
        offset += 100
        if not batch:
            break
    print(f"musicbrainz island areas: {len(areas)}")
    matched = []
    for area in areas:
        name = area.get("name") or ""
        if fold(name) in MB_SKIP_AREA_NAMES:
            continue
        if name_key(name) not in atlas.by_key and fold(name) not in {fold(island["name"]) for island in atlas.islands}:
            continue
        ancestors = _mb_ancestors(area.get("id") or "")
        island = _island_for_mb_area(atlas, name, ancestors)
        if not island:
            continue
        matched.append((area, island, ancestors))
    print(f"musicbrainz areas matched to atlas islands: {len(matched)}")
    collected = []
    for area, island, _ancestors in matched:
        area_ids = [area.get("id")] + _mb_child_ids(area.get("id") or "")
        artists = []
        for area_id in area_ids:
            artists.extend(_mb_artists(area_id))
        if len(artists) > 80:
            artists = [
                artist
                for artist in artists
                if artist.get("type") == "Group"
                or island["name"].lower() in (artist.get("disambiguation") or "").lower()
                or (area.get("name") or "").lower() in (artist.get("disambiguation") or "").lower()
            ]
        for artist in artists:
            artist["_island"] = island
            artist["_area"] = area.get("name") or ""
            collected.append(artist)
    enrichment = _enrich_musicbrainz(collected)
    rows = []
    used_mb = set()
    for artist in collected:
        name = (artist.get("name") or "").strip()
        mbid = artist.get("id") or ""
        if not name or not mbid or mbid in used_mb:
            continue
        if re.search(r"\b(fictional|course at)\b", artist.get("disambiguation") or "", re.I):
            continue
        island = artist["_island"]
        key = (island["id"], fold(name))
        if key in seen:
            continue
        info = enrichment.get(mbid) or {}
        article = info.get("article") or ""
        kind = {
            "Person": "musician",
            "Group": "musical group",
            "Choir": "choir",
            "Orchestra": "orchestra",
        }.get(artist.get("type") or "", "musician")
        island_name = island["name"]
        area_name = artist.get("_area") or island_name
        article_word = "an" if fold(kind)[:1] in "aeiou" else "a"
        summary = f"{name} is {article_word} {kind} from '{island_name}', in the MusicBrainz area {area_name}."
        if article:
            source_url = article
            licence = "CC BY-SA 4.0"
            source_title = urllib.parse.unquote(article.rsplit("/", 1)[-1]).replace("_", " ")
        else:
            source_url = f"https://musicbrainz.org/artist/{mbid}"
            licence = "CC0"
            source_title = name
        evidence = (
            f"MusicBrainz artist {mbid} is listed in the {area_name} area, matched to '{island_name}'."
        )
        built = row(
            category="film-art-music",
            island_id=island["id"],
            island_name=island_name,
            facet="music",
            title=name,
            source_url=source_url,
            source_title=source_title,
            licence=licence,
            evidence=evidence,
            status="accepted",
            confidence="high",
        )
        built["summary"] = summary
        built["commons_file"] = _commons_file(info.get("image") or "")
        rows.append(built)
        seen.add(key)
        used_mb.add(mbid)
    return rows


def populate_open_culture(atlas: Atlas) -> list[dict]:
    """Music, bands, and art from Wikidata statements and MusicBrainz areas.

    Wikipedia seeds stay in film-art-music.json. This file adds rows those
    pages did not already accept. A row still names one work or artist and
    one island.
    """
    seen = set()
    existing = load_json(CANDIDATES / "film-art-music.json", {})
    for item in existing.get("rows") or []:
        if item.get("status") == "accepted" and item.get("island_id") and item.get("title"):
            seen.add((item["island_id"], fold(item["title"])))
    by_qid = _atlas_qids(atlas)
    wikidata_raw = fetch_wikidata_culture(list(by_qid))
    island_qids = fetch_island_place_qids([item["place"] for item in wikidata_raw if item.get("place")])
    rows = _wikidata_rows(wikidata_raw, by_qid, seen, island_qids)
    rows.extend(_musicbrainz_rows(atlas, seen))
    write_candidates(
        "film-art-music-open",
        rows,
        {"sources": ["wikidata", "musicbrainz"], "version": OPEN_CULTURE_VERSION},
    )
    return rows


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else "all"
    known = {"for-sale", "whisky", "culture", "culture-open", "wildlife", "tidal", "castles", "books", "traditions", "publish", "sync", "all"}
    if command not in known:
        print(
            "usage: interest_categories.py [for-sale|whisky|culture|culture-open|wildlife|tidal|castles|books|traditions|publish|sync|all]",
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
    if command in ("culture-open", "all"):
        rows.extend(populate_open_culture(atlas))
    if command == "wildlife":
        from harvest_unusual_wildlife import populate_wildlife

        populate_wildlife(atlas)
        return 0
    if command == "tidal":
        from harvest_tidal_islands import populate_tidal

        populate_tidal(atlas)
        return 0
    if command == "castles":
        from harvest_island_castles import populate_castles

        populate_castles(atlas)
        return 0
    if command == "books":
        from harvest_island_books import populate_books

        populate_books()
        return 0
    if command == "traditions":
        from harvest_local_traditions import populate_traditions

        populate_traditions(atlas)
        return 0
    if command == "all":
        publish(rows)
        sync_supabase(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
