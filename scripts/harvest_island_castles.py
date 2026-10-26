#!/usr/bin/env python3
"""Cite islands that have a castle standing on them.

Sources, all with an open licence:

- Wikidata (CC0): castles, castle ruins, and tower houses whose English
  name says castle, inside the atlas box.
- English Wikipedia (CC BY-SA 4.0): castle categories and the national
  lists, then the article lead.
- OpenStreetMap (ODbL): historic=castle.
- Historic Environment Scotland Canmore (OGL).
- National Heritage List for England (OGL v3.0).
- Cadw listed buildings (OGL v3.0).
- Archaeological Survey of Ireland (CC BY 4.0).

A martello tower, a broch, and a fort do not count. A castle on Great
Britain or Ireland does not count. The row names the castle and the
island. It does not name a living owner, a private address, or a way in.

Does not edit islands.json.
"""

from __future__ import annotations

import hashlib
import math
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from ingest_sources import haversine_km, name_key  # noqa: E402
from interest_categories import (  # noqa: E402
    WIKIDATA_ENDPOINT,
    WIKIPEDIA_API,
    _atlas_qids,
    fold,
    http_json,
    row,
    write_candidates,
)

DATA = ROOT / "data"
CACHE = DATA / "cache_island_castles"
SLUG = "island-castles"
MAX_AREA = 8000.0
OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
)

CANMORE_QUERY = (
    "https://inspire.hes.scot/arcgis/rest/services/CANMORE/Canmore_Points/MapServer/0/query"
)
NHLE_QUERY = (
    "https://services-eu1.arcgis.com/ZOdPfBS3aqqDYPUQ/arcgis/rest/services/"
    "National_Heritage_List_for_England_NHLE_v02_VIEW/FeatureServer/0/query"
)
SMR_QUERY = (
    "https://services-eu1.arcgis.com/HyjXgkV6KGMSF3jt/arcgis/rest/services/"
    "SMROpenData/FeatureServer/0/query"
)
CADW_WFS = "https://datamap.gov.wales/geoserver/inspire-wg/wfs"
NI_QUERY = (
    "https://services.arcgis.com/JJzESW51TqeY9uat/arcgis/rest/services/"
    "Historic_Environment_Division_Sites_and_Monuments/FeatureServer/0/query"
)

WIKI_ROOTS = (
    "Category:Castles in Scotland",
    "Category:Castles in England",
    "Category:Castles in Wales",
    "Category:Castles in Ireland",
    "Category:Castles in Northern Ireland",
    "Category:Castles in the Isle of Man",
    "Category:Castles in the Channel Islands",
    "Category:Castles in the Republic of Ireland",
    "Category:Castles on islands",
)
WIKI_LISTS = (
    "List of castles in Scotland",
    "List of castles in England",
    "List of castles in Wales",
    "List of castles in Ireland",
    "List of castles in the Isle of Man",
    "List of castles in the Channel Islands",
    "List of castles in Shetland",
    "List of castles in Orkney",
    "List of castles in the Outer Hebrides",
    "List of castles in the Inner Hebrides",
)

SKIP_CATEGORY = re.compile(
    r"fictional|video game|novel|film|people|images|stamps|template|disambiguation|attacks on",
    re.I,
)
WIKI_BLOCKED = False
NOT_CASTLE_NAME = re.compile(
    r"\b(hotel|farmhouse|farm|cottage|inn|tavern|pub|school|station|railway|"
    r"stables|barn|lodge|pavilion|folly|villa|apartment|terrace|street|road|"
    r"lane|avenue|drive|martello|broch|hillfort|hill fort|promontory fort|ringfort|"
    r"blockhouse|battery|lighthouse|gatehouse|gateway|gate piers|walls?|"
    r"curtain wall|bridge|pier|chapel|church|fort|dun|installations|"
    r"cist|burial|earthwork)\b",
    re.I,
)
CASTLE_WORD = re.compile(r"\bcastles?\b", re.I)
ON_ISLAND = re.compile(
    r"\b(on|upon|at|in) (the )?(isle of |island of |tidal island of )?",
    re.I,
)
SEPARATE_ISLET = re.compile(
    r"\bon (a |an |its own )(small |tiny |tidal |rocky |offshore )?(island|islet|holm|rock)\b",
    re.I,
)
NOT_ON = re.compile(
    r"\b(opposite|overlooking|looking (across|towards)|across from|near to|"
    r"off the coast of|close to|west of|east of|north of|south of)\b",
    re.I,
)
BANNED_SENTENCE = re.compile(
    r"\b(owned by|home of|residence of|private (house|home|residence)|leased to|"
    r"opening hours|admission|how to (get|reach)|directions to|postcode)\b",
    re.I,
)
POSTCODE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b")
LEAD_CASTLE = re.compile(
    r"\b(is|was|stands as) (a |an |the )?(medieval |ruined |royal |tower |moated |"
    r"coastal |clifftop |cliff-top )*(castle|tower house|fortified house)\b",
    re.I,
)
LEAD_OTHER = re.compile(
    r"\b(is|was) (a |an )?(?:[\w-]+ ){0,5}?(broch|martello tower|hillfort|hill fort|"
    r"promontory fort|ringfort|iron[- ]age fort|folly|country house|hunting lodge|"
    r"hotel|lighthouse)\b",
    re.I,
)
GENERIC_KEYS = {
    "castle",
    "island",
    "isle",
    "holm",
    "rock",
    "skerry",
    "point",
    "ness",
    "bay",
    "loch",
    "more",
    "mor",
    "beg",
    "beag",
    "north",
    "south",
    "east",
    "west",
}


def cache_path(name: str) -> Path:
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:24]
    return CACHE / f"{digest}.json"


def cached_json(name: str, url: str, *, data: str | None = None, timeout: int = 120, headers: dict | None = None):
    path = cache_path(name)
    if path.exists():
        try:
            return http_json_file(path)
        except Exception:
            path.unlink(missing_ok=True)
    payload = http_json(url, data=data.encode("utf-8") if data else None, headers=headers, timeout=timeout)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(__import__("json").dumps(payload), encoding="utf-8")
    return payload


def http_json_file(path: Path):
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def wiki_get(params: dict, name: str) -> dict:
    global WIKI_BLOCKED
    url = WIKIPEDIA_API + "?" + urllib.parse.urlencode(params)
    path = cache_path("wiki-" + name)
    if path.exists():
        try:
            return http_json_file(path)
        except Exception:
            path.unlink(missing_ok=True)
    for attempt in range(3):
        try:
            payload = http_json(url, timeout=60)
        except subprocess.CalledProcessError as exc:
            wait = 12 * (attempt + 1)
            print(f"wikipedia retry {attempt + 1} {name}: {exc.returncode}, waiting {wait}s", flush=True)
            time.sleep(wait)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(__import__("json").dumps(payload), encoding="utf-8")
        time.sleep(1.1)
        return payload or {}
    WIKI_BLOCKED = True
    print(f"wikipedia gave up {name}", flush=True)
    return {}


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return [re.sub(r"\s+", " ", part).strip() for part in parts if part.strip()]


def pretty_name(name: str) -> str:
    name = re.sub(r"\s+", " ", name or "").strip(" ,;")
    if name.isupper():
        name = name.title()
    return name


def phrases(island: dict) -> list[str]:
    raw = island.get("name") or ""
    found = []
    base = re.sub(r"\([^)]*\)", " ", raw)
    extras = re.findall(r"\(([^)]+)\)", raw)
    for piece in (raw, base, *extras):
        piece = re.sub(r"\s+", " ", piece).strip(" ,;")
        if len(piece) >= 4:
            found.append(piece)
        short = re.sub(r"^(isle|island|ynys|eilean|inis|inch) of\s+", "", piece, flags=re.I).strip()
        if len(short) >= 4 and short.lower() != piece.lower():
            found.append(short)
    key = name_key(raw)
    if key and len(key) >= 4 and key not in GENERIC_KEYS:
        found.append(key)
    out = []
    seen = set()
    for phrase in found:
        token = fold(phrase)
        if token in seen or token in GENERIC_KEYS or len(token) < 4:
            continue
        seen.add(token)
        out.append(phrase)
    return out


PLACE_WINDOW = re.compile(
    r"\b(sound|loch|lough|firth|strait|bay|point|head|ness|kyle|kyles|channel|"
    r"estuary|harbour|harbor|river|water|sea) of\s*$",
    re.I,
)
OFF_WINDOW = re.compile(
    r"\b(off the coast of|opposite|overlooking|looking (across|towards)|across from|"
    r"near|close to)\s*(the\s+)?(isle of\s+|island of\s+)?$"
    r"|\b(?<!-)(west|east|north|south) of\s*(the\s+)?(isle of\s+|island of\s+)?$",
    re.I,
)
# The words immediately before the island name. "Takes in Skye" is a view,
# not a location. "On the shore of Raasay" and ", Anglesey" are locations.
PLACED_TAIL = re.compile(
    r"("
    r"\b(on|upon|at|in) the"
    r"( (northern|southern|eastern|western|north-eastern|north-western|"
    r"south-eastern|south-western|north-east|north-west|south-east|south-west|"
    r"northeast|northwest|southeast|southwest|north|south|east|west))?"
    r"( (part|shore|coast|end|side|tip|point|edge|grounds))?"
    r" of( the)?( (isle|island) of)?"
    r"|\b(on|upon|at|in) the"
    r"|\b(isle|island) of"
    r"|\bof the (isle|island) of"
    r"|(^|, )"
    r")\s*$",
    re.I,
)
BARE_PREP = re.compile(r"\b(on|upon|at|in)\s+$", re.I)
VIEW_PREP = re.compile(
    r"\b(takes|taking|bringing|coming|falling|set|deep|lying)\s+(in|on)( the)?\s+$",
    re.I,
)


def on_island(island: dict, text: str) -> bool:
    """True when a sentence puts the subject on this island.

    A water-name such as "Sound of Mull" is not the island. "On the northern
    part of the Isle of Arran" and "on the shore of Raasay" are.
    """
    blob = text or ""
    if not blob.strip():
        return False
    for sentence in sentences(blob):
        folded = fold(sentence)
        for phrase in phrases(island):
            token = fold(phrase)
            if len(token) < 4:
                continue
            for match in re.finditer(rf"\b{re.escape(token)}\b", folded):
                window = folded[max(0, match.start() - 80) : match.start()]
                if PLACE_WINDOW.search(window) or OFF_WINDOW.search(window) or VIEW_PREP.search(window):
                    continue
                if PLACED_TAIL.search(window) or BARE_PREP.search(window):
                    return True
                if re.match(rf"{re.escape(token)} (castle|island|islet)\b", folded[match.start() :]):
                    return True
    return False


def name_in_title(island: dict, title: str) -> bool:
    folded = fold(title)
    for phrase in phrases(island):
        token = fold(phrase)
        if len(token) >= 4 and re.search(rf"\b{re.escape(token)}\b", folded):
            return True
    return False


def separate_islet(text: str) -> bool:
    return bool(SEPARATE_ISLET.search(text or ""))


def denies_large(island: dict, text: str) -> bool:
    if (island.get("area") or 0) < 8:
        return False
    return separate_islet(text)


def castle_name_ok(name: str) -> bool:
    if not name or not CASTLE_WORD.search(name):
        return False
    if NOT_CASTLE_NAME.search(name):
        return False
    return True


def lead_is_castle(title: str, text: str, kind: str) -> bool:
    if re.fullmatch(r"Q\d+", title or ""):
        return False
    if re.search(r"\bhouse\b", title or "", re.I) and not re.search(r"\btower house\b", title or "", re.I):
        return False
    head = " ".join(sentences(text)[:3])
    kind_fold = fold(kind)
    if LEAD_OTHER.search(head) and not LEAD_CASTLE.search(head):
        return False
    if re.search(r"\b(martello|broch)\b", head, re.I) and not LEAD_CASTLE.search(head):
        return False
    if LEAD_CASTLE.search(head):
        return castle_name_ok(title) or True
    # Without an article, the name has to say castle, or the Irish/Scottish
    # register has to call it a tower house. A fort, a house, or a dun does not.
    if "tower house" in kind_fold and not NOT_CASTLE_NAME.search(title or ""):
        return True
    return castle_name_ok(title)


def title_key(title: str) -> str:
    text = fold(title)
    text = re.sub(r"\s*-\s*royal yacht squadron\b", " ", text)
    text = re.sub(r"\b(the|ruins?|remains|of|castle|castles|tower|house|and|earlier|settlement)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or fold(title)


def keys_match(left: str, right: str) -> bool:
    left = left.replace("wee ", "little ")
    right = right.replace("wee ", "little ")
    if ("old" in left.split()) != ("old" in right.split()):
        return False
    if left == right or left.replace(" ", "") == right.replace(" ", ""):
        return True
    if len(left) < 4 or len(right) < 4:
        return False
    short, long = (left, right) if len(left) <= len(right) else (right, left)
    if short in GENERIC_KEYS:
        return False
    return bool(re.search(rf"(^| ){re.escape(short)}($| )", long))


def cleaner_title(left: str, right: str) -> str:
    def score(title: str) -> tuple:
        text = fold(title)
        tidy = 1 if re.search(r"\bcastle$", text) else 0
        messy = 1 if ("," in title or "(" in title or len(title) > 48) else 0
        return (tidy, -messy, -len(title))

    return left if score(left) >= score(right) else right


def island_radius(area: float) -> float:
    if area <= 0:
        return 0.4
    return max(0.35, math.sqrt(area / math.pi) * 1.45)


ISLAND_BUCKETS: dict[tuple[int, int], list] = {}


def build_island_buckets(atlas) -> None:
    ISLAND_BUCKETS.clear()
    for island in atlas.islands:
        if (island.get("area") or 0) > MAX_AREA:
            continue
        key = (int(island["lat"] * 2), int(island["lng"] * 2))
        ISLAND_BUCKETS.setdefault(key, []).append(island)


def spatial_hits(atlas, lat: float, lon: float) -> list[dict]:
    hits = []
    if not ISLAND_BUCKETS:
        build_island_buckets(atlas)
    base_y = int(lat * 2)
    base_x = int(lon * 2)
    islands = []
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            islands.extend(ISLAND_BUCKETS.get((base_y + dy, base_x + dx), []))
    for island in islands:
        area = island.get("area") or 0
        radius = island_radius(area)
        dist = haversine_km(lat, lon, island["lat"], island["lng"])
        if dist <= radius:
            hits.append({"island": island, "dist": dist, "radius": radius, "area": area})
    hits.sort(key=lambda hit: (hit["dist"], hit["area"]))
    return hits


def choose_island(atlas, qids: dict, record: dict, extract: str):
    if record.get("lat") is None or record.get("lon") is None:
        return None, "no coordinates"
    options = spatial_hits(atlas, record["lat"], record["lon"])
    if not options:
        return None, "not on an atlas island"
    if not lead_is_castle(record.get("title") or "", extract, record.get("kind") or ""):
        return None, "not a castle"
    text = f"{record.get('title') or ''}\n{extract or ''}"
    context = " ".join(record.get("context") or [])

    for place in record.get("place_qids") or []:
        island = qids.get(place)
        if not island:
            continue
        if any(hit["island"]["id"] == island["id"] for hit in options) and not denies_large(island, text):
            return island, "Wikidata places it on this island"

    named = [hit for hit in options if on_island(hit["island"], text)]
    if len(named) == 1 and not denies_large(named[0]["island"], text):
        return named[0]["island"], "Wikipedia places it on this island"
    if len(named) > 1:
        named.sort(key=lambda hit: (hit["area"], hit["dist"]))
        pick = named[0]
        if denies_large(pick["island"], text):
            smaller = [hit for hit in named if hit["area"] < 8]
            if not smaller:
                return None, "article puts the castle on a smaller island"
            pick = smaller[0]
        return pick["island"], "Wikipedia places it on this island"

    titled = [
        hit
        for hit in options
        if name_in_title(hit["island"], record.get("title") or "")
        and hit["dist"] <= max(1.5, hit["radius"] * 0.95)
    ]
    if len(titled) == 1 and not denies_large(titled[0]["island"], text):
        return titled[0]["island"], "the castle name includes the island"

    small = [
        hit
        for hit in options
        if hit["area"] < 8 and hit["dist"] <= max(0.8, min(hit["radius"], 1.2))
    ]
    says_island = bool(re.search(r"\bon (a |an |the )?(small |tiny |tidal |rocky )?(island|islet)\b", extract or "", re.I))
    named_small = []
    for hit in small:
        titled = name_in_title(hit["island"], record.get("title") or "")
        in_article = on_island(hit["island"], extract or "")
        in_context = not extract and on_island(hit["island"], context)
        if titled or in_article or in_context:
            named_small.append(hit)
    if len(named_small) == 1:
        return named_small[0]["island"], "the castle stands on this small island"
    if says_island and small:
        small.sort(key=lambda hit: hit["dist"])
        if len(small) == 1 or small[0]["dist"] + 0.2 < small[1]["dist"]:
            return small[0]["island"], "the castle stands on this small island"

    for hit in options:
        if hit["area"] < 8:
            continue
        if denies_large(hit["island"], text):
            continue
        if on_island(hit["island"], context) and hit["dist"] <= hit["radius"] * 0.7:
            return hit["island"], "the register places it on this island"
    return None, "no source places this castle on one island"


def safe_summary(title: str, island_name: str, extract: str) -> str:
    kept = []
    for sentence in sentences(extract)[:6]:
        if BANNED_SENTENCE.search(sentence) or POSTCODE.search(sentence):
            continue
        if NOT_ON.search(sentence) and island_name and fold(island_name) not in fold(sentence):
            continue
        if len(sentence) < 40:
            continue
        kept.append(sentence)
        if len(kept) == 2:
            break
    if not kept:
        text = f"{title} is a castle on {island_name}."
    else:
        text = " ".join(kept)
        if island_name and fold(island_name) not in fold(text) and not re.search(
            r"\b(on|in) (the )?(isle|island)\b", text, re.I
        ):
            text = f"{title} is a castle on {island_name}. {text}"
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 520:
        text = text[:500].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    return text


def blank(title: str, **extra) -> dict:
    item = {
        "title": pretty_name(title),
        "lat": None,
        "lon": None,
        "kind": "",
        "source": "",
        "source_url": "",
        "source_title": "",
        "licence": "",
        "external_id": "",
        "wiki_title": "",
        "commons_file": "",
        "place_qids": [],
        "context": [],
        "priority": 1,
    }
    item.update(extra)
    return item


def commons_name(url: str) -> str:
    if not url:
        return ""
    name = urllib.parse.unquote(url.rstrip("/").rsplit("/", 1)[-1]).replace("_", " ")
    if not name or name.lower() in {"special:filepath", "wiki"}:
        return ""
    return name if name.startswith("File:") else f"File:{name}"


def wikidata_bands() -> list[dict]:
    records = []
    bands = ((49.0, 52.0), (52.0, 54.5), (54.5, 56.5), (56.5, 58.5), (58.5, 61.7))
    kinds = (
        ("castle", "?item wdt:P31/wdt:P279* wd:Q23413 ."),
        ("ruin", "?item wdt:P31 wd:Q17715832 ."),
        (
            "tower",
            '?item wdt:P31 wd:Q88293 . ?item rdfs:label ?en . FILTER(LANG(?en)="en") FILTER(CONTAINS(LCASE(?en), "castle")) .',
        ),
    )
    for south, north in bands:
        for kind_name, pattern in kinds:
            name = f"wd-{kind_name}-{south}-{north}"
            query = f"""
SELECT ?item ?itemLabel ?lat ?lon ?article ?image ?place WHERE {{
  {pattern}
  ?item p:P625/psv:P625 ?coord .
  ?coord wikibase:geoLatitude ?lat ; wikibase:geoLongitude ?lon .
  FILTER(?lat >= {south} && ?lat < {north} && ?lon > -11 && ?lon < 2.6)
  OPTIONAL {{ ?article schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> . }}
  OPTIONAL {{ ?item wdt:P18 ?image }}
  OPTIONAL {{ ?item wdt:P276|wdt:P706 ?place }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
"""
            body = urllib.parse.urlencode({"format": "json", "query": query})
            print(f"wikidata {name}", flush=True)
            try:
                payload = cached_json(
                    name,
                    WIKIDATA_ENDPOINT,
                    data=body,
                    timeout=150,
                    headers={"Accept": "application/sparql-results+json", "Content-Type": "application/x-www-form-urlencoded"},
                )
            except (subprocess.CalledProcessError, RuntimeError) as exc:
                print(f"wikidata failed {name}: {exc}", flush=True)
                continue
            grouped: dict[str, dict] = {}
            for binding in ((payload or {}).get("results") or {}).get("bindings") or []:
                qid = (binding.get("item") or {}).get("value", "").rsplit("/", 1)[-1]
                if not qid:
                    continue
                item = grouped.setdefault(
                    qid,
                    blank(
                        (binding.get("itemLabel") or {}).get("value") or qid,
                        kind=kind_name,
                        source="wikidata",
                        source_url=f"https://www.wikidata.org/wiki/{qid}",
                        source_title=(binding.get("itemLabel") or {}).get("value") or qid,
                        licence="CC0",
                        external_id=qid,
                        priority=3,
                        lat=float((binding.get("lat") or {}).get("value")),
                        lon=float((binding.get("lon") or {}).get("value")),
                    ),
                )
                article = (binding.get("article") or {}).get("value") or ""
                if article and "/wiki/" in article:
                    item["wiki_title"] = urllib.parse.unquote(article.split("/wiki/", 1)[1]).replace("_", " ")
                    item["source_url"] = article
                    item["source_title"] = item["wiki_title"]
                    item["licence"] = "CC BY-SA 4.0"
                    item["source"] = "wikipedia"
                    item["priority"] = 4
                image = commons_name((binding.get("image") or {}).get("value") or "")
                if image and not item["commons_file"]:
                    item["commons_file"] = image
                place = (binding.get("place") or {}).get("value") or ""
                if place:
                    place_qid = place.rsplit("/", 1)[-1]
                    if place_qid.startswith("Q") and place_qid not in item["place_qids"]:
                        item["place_qids"].append(place_qid)
            records.extend(grouped.values())
            time.sleep(0.2)
    print(f"wikidata records: {len(records)}", flush=True)
    return records


def category_titles() -> list[str]:
    titles = []
    seen = set()
    queue = [(title, 0) for title in WIKI_ROOTS]
    visited = set()
    while queue and len(titles) < 8000 and not WIKI_BLOCKED:
        title, depth = queue.pop(0)
        if title in visited or depth > 3:
            continue
        visited.add(title)
        cont = ""
        while True:
            params = {
                "action": "query",
                "format": "json",
                "list": "categorymembers",
                "cmtitle": title,
                "cmtype": "page|subcat",
                "cmlimit": "500",
            }
            if cont:
                params["cmcontinue"] = cont
            payload = wiki_get(params, "cat-" + title + "-" + cont)
            members = ((payload.get("query") or {}).get("categorymembers") or [])
            if not members and not cont:
                break
            for member in members:
                name = member.get("title") or ""
                if name.startswith("Category:"):
                    if depth < 3 and not SKIP_CATEGORY.search(name):
                        queue.append((name, depth + 1))
                    continue
                if name.startswith(("File:", "Template:", "Portal:")):
                    continue
                if name not in seen:
                    seen.add(name)
                    titles.append(name)
            cont = (payload.get("continue") or {}).get("cmcontinue") or ""
            if not cont:
                break
            time.sleep(0.2)
    print(f"wikipedia category pages: {len(titles)}", flush=True)
    return titles


def list_titles() -> list[str]:
    titles = []
    seen = set()
    for page in WIKI_LISTS:
        cont = ""
        found = False
        while True:
            params = {
                "action": "query",
                "format": "json",
                "prop": "links",
                "titles": page,
                "plnamespace": "0",
                "pllimit": "500",
            }
            if cont:
                params["plcontinue"] = cont
            payload = wiki_get(params, "list-" + page + "-" + cont)
            pages = ((payload.get("query") or {}).get("pages") or {}).values()
            for entry in pages:
                if entry.get("missing") is not None:
                    continue
                found = True
                for link in entry.get("links") or []:
                    name = link.get("title") or ""
                    if name and name not in seen and not name.startswith("List of"):
                        seen.add(name)
                        titles.append(name)
            cont = (payload.get("continue") or {}).get("plcontinue") or ""
            if not cont:
                break
        if found:
            print(f"list {page}: links kept running total {len(titles)}", flush=True)
    return titles


def coords_for(titles: list[str]) -> list[dict]:
    records = []
    pending = []
    seen = set()
    for title in titles:
        key = fold(title)
        if not key or key in seen:
            continue
        seen.add(key)
        pending.append(title)
    for start in range(0, len(pending), 40):
        batch = pending[start : start + 40]
        params = {
            "action": "query",
            "format": "json",
            "prop": "coordinates|pageprops",
            "ppprop": "wikibase_item",
            "colimit": "40",
            "titles": "|".join(batch),
        }
        payload = wiki_get(params, "coord-" + str(start) + "-" + batch[0])
        for page in (((payload.get("query") or {}).get("pages") or {}).values()):
            if page.get("missing") is not None:
                continue
            coords = page.get("coordinates") or []
            if not coords:
                continue
            title = page.get("title") or ""
            qid = ((page.get("pageprops") or {}).get("wikibase_item")) or ""
            records.append(
                blank(
                    title,
                    lat=coords[0].get("lat"),
                    lon=coords[0].get("lon"),
                    kind="wikipedia",
                    source="wikipedia",
                    source_url="https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_")),
                    source_title=title,
                    licence="CC BY-SA 4.0",
                    external_id=qid,
                    wiki_title=title,
                    priority=4,
                )
            )
        if start and start % 400 == 0:
            print(f"wikipedia coordinates {start}/{len(pending)}", flush=True)
        time.sleep(0.35)
    print(f"wikipedia pages with coordinates: {len(records)}", flush=True)
    return records


def fetch_extracts(titles: list[str]) -> dict[str, str]:
    global WIKI_BLOCKED
    cache_file = CACHE / "extracts.json"
    import json

    stored = {}
    if cache_file.exists():
        stored = json.loads(cache_file.read_text(encoding="utf-8"))
    missing = []
    seen = set()
    for title in titles:
        key = fold(title)
        if not key or key in seen:
            continue
        seen.add(key)
        if key not in stored:
            missing.append(title)
    print(f"extracts cached {len(stored)} missing {len(missing)}", flush=True)
    for start in range(0, len(missing), 16):
        batch = missing[start : start + 16]
        params = {
            "action": "query",
            "format": "json",
            "redirects": "1",
            "prop": "extracts",
            "exintro": "1",
            "explaintext": "1",
            "exchars": "900",
            "titles": "|".join(batch),
        }
        url = WIKIPEDIA_API + "?" + urllib.parse.urlencode(params)
        payload = None
        for attempt in range(2):
            try:
                payload = http_json(url, timeout=60)
                break
            except subprocess.CalledProcessError as exc:
                wait = 8
                print(f"extract retry {attempt + 1}: {exc.returncode}, waiting {wait}s", flush=True)
                time.sleep(wait)
        if not payload:
            print("extract batch left for a later pass", flush=True)
            WIKI_BLOCKED = True
            break
        query = payload.get("query") or {}
        redirect_of = {}
        for item in query.get("redirects") or []:
            redirect_of.setdefault(item.get("to"), []).append(item.get("from"))
        for page in (query.get("pages") or {}).values():
            names = [page.get("title") or "", *(redirect_of.get(page.get("title")) or [])]
            extract = "" if page.get("missing") is not None else (page.get("extract") or "")
            for name in names:
                if name:
                    stored[fold(name)] = extract
        for title in batch:
            stored.setdefault(fold(title), "")
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")
        time.sleep(0.7)
    return stored


def arcgis_pages(url: str, where: str, fields: str, name: str, *, paginate: bool = True) -> list[dict]:
    rows = []
    offset = 0
    while offset < 20000:
        params = {
            "where": where,
            "outFields": fields,
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "json",
        }
        if paginate:
            params["resultOffset"] = str(offset)
            params["resultRecordCount"] = "2000"
        query = url + "?" + urllib.parse.urlencode(params)
        print(f"{name} offset {offset}", flush=True)
        try:
            payload = cached_json(f"{name}-{offset}", query, timeout=120)
        except subprocess.CalledProcessError as exc:
            print(f"{name} failed: {exc.returncode}", flush=True)
            break
        if payload.get("error"):
            print(f"{name} error: {payload['error']}", flush=True)
            break
        features = payload.get("features") or []
        rows.extend(features)
        if len(features) < 2000:
            break
        offset += 2000
    print(f"{name} features {len(rows)}", flush=True)
    return rows


def geom_point(feature: dict) -> tuple[float, float] | None:
    geom = feature.get("geometry") or {}
    if "x" in geom and "y" in geom:
        return float(geom["y"]), float(geom["x"])
    points = geom.get("points") or []
    if points:
        return float(points[0][1]), float(points[0][0])
    if geom.get("type") == "Point":
        lon, lat = geom.get("coordinates") or [None, None]
        if lat is not None:
            return float(lat), float(lon)
    if geom.get("type") == "MultiPoint":
        coords = geom.get("coordinates") or []
        first = coords[0] if coords else None
        while isinstance(first, (list, tuple)) and first and isinstance(first[0], (list, tuple)):
            first = first[0]
        if isinstance(first, (list, tuple)) and len(first) >= 2:
            return float(first[1]), float(first[0])
    attrs = feature.get("attributes") or feature.get("properties") or {}
    lat = attrs.get("LATITUDE") or attrs.get("lat")
    lon = attrs.get("LONGITUDE") or attrs.get("lon")
    if lat is not None and lon is not None:
        return float(lat), float(lon)
    return None


def heritage_records() -> list[dict]:
    records = []
    for feature in arcgis_pages(
        CANMORE_QUERY,
        "SITETYPE LIKE '%CASTLE%'",
        "NMRSNAME,ALTNAME,SITETYPE,LICENCE,CANMOREID,URL,PARISH,COUNTY",
        "canmore-v3",
        paginate=False,
    ):
        attrs = feature.get("attributes") or {}
        licence = (attrs.get("LICENCE") or "").lower()
        if licence and "open government" not in licence and "ogl" not in licence:
            continue
        point = geom_point(feature)
        if not point:
            continue
        name = pretty_name(attrs.get("NMRSNAME") or attrs.get("ALTNAME") or "")
        if not castle_name_ok(name):
            continue
        cid = attrs.get("CANMOREID")
        page = (attrs.get("URL") or "").strip() or (f"https://www.trove.scot/site/{cid}" if cid else "")
        if not page:
            continue
        possible = "POSSIBLE" in (attrs.get("SITETYPE") or "")
        records.append(
            blank(
                name,
                lat=point[0],
                lon=point[1],
                kind=attrs.get("SITETYPE") or "castle",
                source="canmore",
                source_url=page,
                source_title=name,
                licence="OGL",
                external_id=f"canmore-{cid}" if cid else "",
                priority=1 if possible else 2,
                context=[attrs.get("PARISH") or "", attrs.get("COUNTY") or ""],
            )
        )
    for feature in arcgis_pages(
        NHLE_QUERY,
        "Name LIKE '%Castle%'",
        "Name,hyperlink,ListEntry",
        "nhle",
    ):
        attrs = feature.get("attributes") or {}
        point = geom_point(feature)
        name = pretty_name(attrs.get("Name") or "")
        if not point or not castle_name_ok(name):
            continue
        entry = attrs.get("ListEntry")
        page = (attrs.get("hyperlink") or "").strip()
        if entry and not page:
            page = f"https://historicengland.org.uk/listing/the-list/list-entry/{entry}"
        if not page:
            continue
        records.append(
            blank(
                name,
                lat=point[0],
                lon=point[1],
                kind="listed castle",
                source="nhle",
                source_url=page,
                source_title=name,
                licence="OGL v3.0",
                external_id=f"nhle-{entry}" if entry else "",
                priority=2,
            )
        )
    keep_class = ("tower house", "anglo-norman", "hall-house", "unclassified", "masonry castle")
    skip_class = ("motte", "ringwork", "earthwork")
    for feature in arcgis_pages(
        SMR_QUERY,
        "MONUMENT_CLASS LIKE '%Castle%'",
        "SMRS,MONUMENT_CLASS,TOWNLAND,COUNTY,WEBSITE_LINK",
        "smr",
    ):
        attrs = feature.get("attributes") or {}
        kind = attrs.get("MONUMENT_CLASS") or ""
        kind_fold = fold(kind)
        if any(token in kind_fold for token in skip_class):
            continue
        if not any(token in kind_fold for token in keep_class):
            continue
        point = geom_point(feature)
        if not point:
            continue
        townland = pretty_name(attrs.get("TOWNLAND") or "")
        short = "tower house" if "tower house" in kind_fold else "hall-house" if "hall-house" in kind_fold else "castle"
        title = f"{townland} {short}".strip() if townland else short
        page = (attrs.get("WEBSITE_LINK") or "").strip() or "https://www.archaeology.ie/collections-and-publications/open-data/"
        records.append(
            blank(
                title,
                lat=point[0],
                lon=point[1],
                kind=kind,
                source="smr" if "unclassified" not in kind_fold else "heritage-weak",
                source_url=page,
                source_title=f"{kind}, {townland}".strip(", "),
                licence="CC BY 4.0",
                external_id=attrs.get("SMRS") or "",
                priority=2 if "unclassified" not in kind_fold else 1,
                context=[townland, attrs.get("COUNTY") or ""],
            )
        )
    try:
        params = urllib.parse.urlencode(
            {
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "typeNames": "inspire-wg:Cadw_ListedBuildings",
                "CQL_FILTER": "Name LIKE '%Castle%'",
                "count": "3000",
                "outputFormat": "application/json",
            }
        )
        payload = cached_json("cadw-castles", CADW_WFS + "?" + params, timeout=120)
        for feature in payload.get("features") or []:
            props = feature.get("properties") or {}
            name = pretty_name(props.get("Name") or props.get("Name_cy") or "")
            point = geom_point(feature)
            if not point or not castle_name_ok(name):
                continue
            page = props.get("Report") or props.get("Report_welsh") or ""
            if not page:
                continue
            records.append(
                blank(
                    name,
                    lat=point[0],
                    lon=point[1],
                    kind="listed castle",
                    source="cadw",
                    source_url=page,
                    source_title=name,
                    licence="OGL v3.0",
                    external_id=str(props.get("RecordNumber") or ""),
                    priority=2,
                    context=[props.get("Community") or "", props.get("Location") or ""],
                )
            )
        print(f"cadw castle names kept {sum(1 for item in records if item['source']=='cadw')}", flush=True)
    except subprocess.CalledProcessError as exc:
        print(f"cadw skipped: {exc.returncode}", flush=True)
    print(f"heritage records: {len(records)}", flush=True)
    return records


def osm_records() -> list[dict]:
    query = """
[out:json][timeout:180];
(
  node["historic"="castle"](49,-11,61.6,2.6);
  way["historic"="castle"](49,-11,61.6,2.6);
  relation["historic"="castle"](49,-11,61.6,2.6);
);
out center tags;
"""
    payload = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            print(f"overpass {endpoint}", flush=True)
            payload = cached_json(
                "overpass-" + endpoint,
                endpoint,
                data=urllib.parse.urlencode({"data": query}),
                timeout=90,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if payload.get("elements") is not None:
                break
        except subprocess.CalledProcessError as exc:
            print(f"overpass failed {endpoint}: {exc.returncode}", flush=True)
            payload = None
    elements = (payload or {}).get("elements") or []
    records = []
    for element in elements:
        tags = element.get("tags") or {}
        if tags.get("historic") != "castle":
            continue
        name = tags.get("name") or tags.get("name:en") or ""
        lat = element.get("lat") or (element.get("center") or {}).get("lat")
        lon = element.get("lon") or (element.get("center") or {}).get("lon")
        if lat is None or lon is None:
            continue
        wiki = tags.get("wikipedia") or ""
        wiki_title = ""
        source_url = f"https://www.openstreetmap.org/{element.get('type')}/{element.get('id')}"
        licence = "ODbL"
        source = "osm"
        priority = 1
        if wiki.startswith("en:"):
            wiki_title = wiki.split(":", 1)[1].replace("_", " ")
            source_url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(wiki_title.replace(" ", "_"))
            licence = "CC BY-SA 4.0"
            source = "wikipedia"
            priority = 4
        title = pretty_name(name or wiki_title)
        if not title:
            continue
        if re.search(r"\b(martello|broch)\b", title, re.I):
            continue
        records.append(
            blank(
                title,
                lat=float(lat),
                lon=float(lon),
                kind=tags.get("castle_type") or "castle",
                source=source,
                source_url=source_url,
                source_title=wiki_title or title,
                licence=licence,
                external_id=tags.get("wikidata") or f"osm-{element.get('type')}-{element.get('id')}",
                wiki_title=wiki_title,
                priority=priority,
                context=[tags.get("is_in") or "", tags.get("addr:island") or ""],
            )
        )
    print(f"osm castles: {len(records)}", flush=True)
    return records


def prefilter(atlas, records: list[dict]) -> list[dict]:
    kept = []
    for record in records:
        if record.get("lat") is None:
            continue
        if spatial_hits(atlas, record["lat"], record["lon"]):
            kept.append(record)
    print(f"on an atlas island before the article check: {len(kept)} of {len(records)}", flush=True)
    return kept


def better(old: dict, new: dict) -> dict:
    primary = new if new["priority"] > old["priority"] else old
    other = old if primary is new else new
    primary["title"] = cleaner_title(primary.get("title") or "", other.get("title") or "")
    if not primary.get("commons_file"):
        primary["commons_file"] = other.get("commons_file") or ""
    if not primary.get("wiki_title"):
        primary["wiki_title"] = other.get("wiki_title") or ""
    if other.get("source_url") and other["source_url"] not in (primary.get("evidence") or ""):
        note = other.get("source_title") or other.get("source")
        primary["evidence"] = (primary.get("evidence") or "") + f" Also {note}: {other['source_url']}."
    if (other.get("summary") or "") and len(other.get("summary") or "") > len(primary.get("summary") or ""):
        if primary["priority"] <= other["priority"]:
            primary["summary"] = other["summary"]
    return primary


def drop_parent_copies(accepted: dict, atlas) -> tuple[list[dict], list[dict]]:
    """One castle named on a loch islet and again on the parent island keeps the islet."""
    by_id = {island["id"]: island for island in atlas.islands}
    items = list(accepted.values())
    used = set()
    kept = []
    dropped = []
    for index, item in enumerate(items):
        if index in used:
            continue
        key = title_key(item["title"])
        group = [item]
        used.add(index)
        if key and key not in GENERIC_KEYS and len(key) >= 5:
            for other_index in range(index + 1, len(items)):
                if other_index in used:
                    continue
                other = items[other_index]
                if other["island_id"] == item["island_id"]:
                    continue
                if keys_match(key, title_key(other["title"])):
                    group.append(other)
                    used.add(other_index)
        if len(group) == 1:
            kept.append(item)
            continue
        ranked = sorted(
            group,
            key=lambda entry: (
                by_id.get(entry["island_id"], {}).get("area") or 0,
                entry.get("island_name") or "",
            ),
        )
        small_area = by_id.get(ranked[0]["island_id"], {}).get("area") or 0
        for entry in ranked:
            area = by_id.get(entry["island_id"], {}).get("area") or 0
            if entry is ranked[0] or area < 8 or (small_area and area <= small_area * 1.5):
                kept.append(entry)
                continue
            entry["status"] = "rejected"
            entry["reject_reason"] = "the castle stands on a smaller island"
            dropped.append(entry)
    return kept, dropped


def populate_castles(atlas) -> list[dict]:
    CACHE.mkdir(parents=True, exist_ok=True)
    qids = _atlas_qids(atlas)
    raw = []
    raw.extend(wikidata_bands())
    raw.extend(heritage_records())
    raw.extend(osm_records())
    # Wikipedia categories and national lists are read when the API is
    # answering. A rate limit must not delay the Wikidata, heritage, and
    # OpenStreetMap rows, whose own articles are fetched below.
    candidates = prefilter(atlas, raw)
    extract_titles = []
    for record in candidates:
        if record.get("wiki_title"):
            extract_titles.append(record["wiki_title"])
        elif record.get("source") == "wikipedia":
            extract_titles.append(record.get("title") or "")
    extracts = fetch_extracts(extract_titles)
    accepted: dict[tuple[str, str], dict] = {}
    rejected = []
    for record in candidates:
        wiki_title = record.get("wiki_title") or (record.get("title") if record.get("source") == "wikipedia" else "")
        extract = ""
        for key in (wiki_title, record.get("title") or ""):
            if key and extracts.get(fold(key)):
                extract = extracts[fold(key)]
                wiki_title = wiki_title or key
                break
        if (title_l := (record.get("title") or "").lower()).startswith("list of") or "may refer to" in (extract or "")[:220].lower() or re.search(r"\b(near|east of|west of|north of|south of|view of|watermill)\b", title_l):
            rejected.append(
                row(
                    category=SLUG,
                    island_id="",
                    facet="castle",
                    title=record.get("title") or "Castle",
                    source_url=record.get("source_url") or "",
                    status="rejected",
                    reject_reason="list or disambiguation page",
                    evidence="not a single castle",
                )
            )
            continue
        island, reason = choose_island(atlas, qids, record, extract)
        title = record.get("title") or wiki_title or "Castle"
        if island is None:
            rejected.append(
                row(
                    category=SLUG,
                    island_id="",
                    island_name="",
                    facet="castle",
                    title=title,
                    source_url=record.get("source_url") or "",
                    source_title=record.get("source_title") or "",
                    licence=record.get("licence") or "",
                    external_id=record.get("external_id") or "",
                    status="rejected",
                    confidence="medium",
                    reject_reason=reason,
                    evidence=reason,
                )
            )
            continue
        summary = safe_summary(title, island["name"], extract)
        if BANNED_SENTENCE.search(summary) or POSTCODE.search(summary):
            rejected.append(
                row(
                    category=SLUG,
                    island_id=island["id"],
                    island_name=island["name"],
                    facet="castle",
                    title=title,
                    source_url=record.get("source_url") or "",
                    status="rejected",
                    reject_reason="summary named an owner, an address, or a way in",
                    evidence=reason,
                )
            )
            continue
        item = row(
            category=SLUG,
            island_id=island["id"],
            island_name=island["name"],
            facet="castle",
            title=title,
            source_url=record.get("source_url") or "",
            source_title=record.get("source_title") or wiki_title or title,
            licence=record.get("licence") or "",
            external_id=record.get("external_id") or "",
            status="accepted",
            confidence="high" if record.get("priority", 1) >= 3 else "medium",
            evidence=f"{reason}. {record.get('source_title') or record.get('source')}.",
            summary=summary,
        )
        if record.get("commons_file"):
            item["commons_file"] = record["commons_file"]
        if wiki_title:
            item["photo_title"] = wiki_title
        stripped = title
        for phrase in phrases(island):
            stripped = re.sub(rf"^{re.escape(phrase)}\s*,\s*", "", stripped, flags=re.I)
        stripped = stripped.strip(" ,")
        if CASTLE_WORD.search(stripped) or "tower house" in fold(stripped):
            title = stripped
        item["title"] = title
        if fold(title) in {"castle", "the castle"} or re.search(r"\bcity\b", title, re.I):
            continue
        if fold(title) == fold(island["name"]) and not CASTLE_WORD.search(title):
            continue
        item["priority"] = record.get("priority") or 1
        key = (island["id"], title_key(title))
        if not key[1]:
            continue
        existing = next((other for other in accepted if other[0] == island["id"] and keys_match(other[1], key[1])), None)
        if existing:
            accepted[existing] = better(accepted[existing], item)
        else:
            accepted[key] = item
    kept = []
    for item in accepted.values():
        extract = extracts.get(fold(item.get("photo_title") or "")) or extracts.get(fold(item.get("title") or "")) or ""
        island = {"name": item.get("island_name") or "", "area": 0}
        lead = " ".join(sentences(extract)[:2])
        evidence = item.get("evidence") or ""
        head = " ".join(sentences(extract)[:3])
        if extract and LEAD_OTHER.search(head) and not LEAD_CASTLE.search(head):
            item["status"] = "rejected"
            item["reject_reason"] = "not a castle"
            rejected.append(item)
            continue
        weak = evidence.startswith("the castle stands on this small island") or evidence.startswith(
            "the register places"
        )
        if (
            weak
            and extract
            and not on_island(island, extract)
            and not name_in_title(island, item.get("title") or "")
            and not SEPARATE_ISLET.search(lead)
        ):
            item["status"] = "rejected"
            item["reject_reason"] = "the castle's article does not place it on this island"
            rejected.append(item)
            continue
        kept.append(item)
    accepted = { (item["island_id"], title_key(item["title"])): item for item in kept }
    kept, parent_copies = drop_parent_copies(accepted, atlas)
    rejected.extend(parent_copies)
    accepted = { (item["island_id"], title_key(item["title"])): item for item in kept }
    rows = list(accepted.values()) + rejected
    write_candidates(
        SLUG,
        rows,
        {
            "sources": [
                "wikidata",
                "wikipedia",
                "openstreetmap",
                "canmore",
                "nhle",
                "cadw",
                "archaeological-survey-of-ireland",
            ],
            "considered": len(raw),
            "onIsland": len(candidates),
            "rejected": len(rejected),
        },
    )
    print("accepted sample:", flush=True)
    for item in sorted(accepted.values(), key=lambda entry: (entry["island_name"], entry["title"]))[:80]:
        print(f"  {item['island_name']} — {item['title']}", flush=True)
    return rows


def main() -> int:
    from interest_categories import Atlas

    atlas = Atlas()
    print(f"atlas islands: {len(atlas.islands)}", flush=True)
    populate_castles(atlas)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
