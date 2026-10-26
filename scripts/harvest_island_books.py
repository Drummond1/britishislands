#!/usr/bin/env python3
"""Cite books set on an atlas island.

A row is a novel, memoir, autobiography, or story collection whose English
Wikipedia article sets the book on that island. "Inspired by", "based on",
and "filmed on" do not count. Great Britain and Ireland do not count.

The picture is an open-licence image from the article (a cover, a title
page, an illustration, or a photograph the article uses). A fair-use cover
is left out. When the article has no open picture, the island's own
open-licence photograph is used and labelled as a photograph of the island.

Wikipedia text is CC BY-SA 4.0. Commons files keep their own licence.
Does not edit islands.json.
"""

from __future__ import annotations

import re
import sys
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from interest_categories import (  # noqa: E402
    CLOSED_IMAGE_LICENCE,
    MAPISH_IMAGE,
    OPEN_IMAGE_LICENCE,
    WIKIPEDIA_API,
    _commons_records,
    _image_from_file,
    _load_media_cache,
    _sentences,
    _wikidata_sparql,
    fold,
    http_json,
    row,
    write_candidates,
)

DATA = ROOT / "data"
CACHE = DATA / "cache_island_books"
SEEDS = DATA / "interest" / "seeds"
SLUG = "island-books"
MAX_AREA = 8000.0
MAINLANDS = {
    "great britain",
    "britain",
    "ireland",
    "united kingdom",
    "england",
    "scotland",
    "wales",
    "northern ireland",
    "british isles",
    "europe",
}
BLOCK_BARE = {
    "may",
    "man",
    "mainland",
    "island",
    "islands",
    "isle",
    "the",
    "great",
    "little",
    "north",
    "south",
    "east",
    "west",
    "upper",
    "lower",
    "inner",
    "outer",
    "new",
    "old",
    "day",
    "main",
    "rock",
    "stone",
    "point",
    "head",
    "ness",
    "bay",
    "easter",
    "church",
    "cottage",
    "english",
    "taylor",
    "edward",
    "puffin",
    "sisters",
    "green",
    "white",
    "long",
    "round",
    "flat",
    "high",
    "low",
    "black",
    "red",
    "big",
    "small",
    "middle",
    "horse",
    "saint",
    "holy",
    "barry",
    "castle",
    "house",
    "farm",
    "hill",
    "loch",
    "lake",
    "river",
    "sound",
    "channel",
    "firth",
}
# A parenthetical archipelago name is not an alias for every islet in it.
# Mainland keeps the group name, so "set in Orkney" lands on Mainland (Orkney).
ARCHIPELAGO_PAREN = {
    "orkney",
    "shetland",
    "hebrides",
    "outer hebrides",
    "inner hebrides",
    "scilly",
    "isles of scilly",
    "aran",
    "aran islands",
    "channel islands",
}
# Stevenson spells Erraid as Earraid. Papay is Papa Westray.
# Lewis and Harris is one island; novels name the Isle of Lewis.
EXTRA_ALIASES = {
    "osm-relation-9620215": ["Earraid"],
    "osm-way-4569530": ["Papay"],
    "mainland-orkney": ["Orkney", "Orkney Islands"],
    "mainland-shetland": ["Shetland", "Shetland Islands"],
    "lewis-and-harris": ["Isle of Lewis", "Lewis"],
    "scilly-st-marys": ["Isles of Scilly", "Scilly Isles", "Scilly"],
}
EXTRA_CONTEXT = {
    "osm-relation-6045346": ["anglesey", "holyhead", "ynys gybi"],
    "osm-way-4003348": ["arran", "lamlash"],
    "lindisfarne": ["northumberland", "northumbria"],
    "osm-relation-6045552": ["aran", "galway", "kilronan"],
    "osm-relation-3006275": ["lough barry", "fermanagh"],
    "osm-relation-8158177": ["aran"],
    "osm-way-4559234": ["aran"],
    "osm-relation-3235264": ["aran"],
}
BROAD_CAPS = {
    "scotland": 220,
    "ireland": 180,
    "england": 140,
    "wales": 80,
    "northern ireland": 80,
}
BOOK_LEAD = re.compile(
    r"\b(novel|novella|memoir|autobiograph|short stor|children's book|picture book|"
    r"poetry collection|collection of poems|non-?fiction book|book by|account of|"
    r"story collection|collection of (?:short )?stor)\b",
    re.I,
)
NOT_A_BOOK = re.compile(
    r"\b(is an? (?:\d{4} )?(?:british |american |irish |scottish )?(?:film|television|tv series|"
    r"album|song|painting|video game|podcast|opera|documentary)|"
    r"guidebook|travel guide|lonely planet|rough guide|gazetteer|pilot book)\b",
    re.I,
)
INSPIRED = re.compile(
    r"\b(inspired by|based on|loosely based|modell?ed on|thought to be based|filmed on|shot on)\b",
    re.I,
)
PAREN_TITLE = re.compile(
    r"\s*\((?:novel|novella|memoir|book|autobiography|short stor(?:y|ies)(?: collection)?|poetry collection)\)\s*$",
    re.I,
)
CITY_CATEGORY = re.compile(
    r"\b(london|edinburgh|dublin|glasgow|belfast|manchester|birmingham|liverpool|"
    r"cardiff|york|oxford|cambridge|paris|new york|century|future|space|world war|"
    r"victorian|medieval)\b",
    re.I,
)
REMIT_CATEGORY = re.compile(
    r"\b(scotland|ireland|england|wales|britain|british|united kingdom|orkney|shetland|hebrides|"
    r"skye|islay|jura|arran|mull|iona|lewis|harris|guernsey|jersey|sark|alderney|"
    r"herm|scilly|anglesey|wight|lundy|lindisfarne|channel islands|isle of man|"
    r"aran|blasket|highland|cornish|manx)\b",
    re.I,
)
FOREIGN_CATEGORY = re.compile(
    r"\b(united states|american|australia|canadian|canada|india|africa|zealand|"
    r"france|germany|japan|china|russia|italy|spain|mexico|brazil|sweden|norway|"
    r"denmark|iceland|caribbean|hawaii|greece|greek|pacific|asia|columbia|ontario|quebec|alaska|new jersey)\b",
    re.I,
)


def load_islands() -> list[dict]:
    import json

    raw = json.loads((DATA / "islands.json").read_text(encoding="utf-8"))
    islands = []
    for item in raw:
        name = (item.get("name") or "").strip()
        if not name or fold(name) in {"unnamed island", "unnamed"}:
            continue
        area = item.get("areaKm2") or 0
        if area > MAX_AREA or fold(name) in MAINLANDS:
            continue
        water = item.get("parentWaterBody")
        water_name = water.get("name") if isinstance(water, dict) else ""
        islands.append(
            {
                "id": item.get("id"),
                "name": name,
                "area": area or 0,
                "wikidata": item.get("wikidata") or "",
                "nation": item.get("nation") or "",
                "archipelago": item.get("archipelago") or "",
                "water": water_name or "",
                "names": item.get("names") if isinstance(item.get("names"), dict) else {},
                "images": item.get("images") or [],
            }
        )
    return [island for island in islands if island["id"]]


def _clean_alias(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip(" ,;/")
    if not value or len(fold(value)) < 3:
        return ""
    if fold(value) in BLOCK_BARE or fold(value) in MAINLANDS or fold(value) in {"the", "the island", "the isle", "an island"}:
        return ""
    return value


def build_alias_index(islands: list[dict]) -> list[tuple[str, dict]]:
    """Longest alias first, so 'Isle of Skye' beats 'Skye'."""
    pairs: list[tuple[str, dict]] = []
    seen = set()
    for island in islands:
        aliases = [island["name"], *EXTRA_ALIASES.get(island["id"], [])]
        for value in (island.get("names") or {}).values():
            aliases.append(value or "")
        for name in list(aliases):
            match = re.match(r"^(.+?)\s*\((.+)\)\s*$", name.strip())
            if match:
                aliases.append(match.group(1))
                if fold(match.group(2)) not in ARCHIPELAGO_PAREN:
                    aliases.append(match.group(2))
            low = name.lower().strip()
            for prefix in ("isle of ", "island of ", "the "):
                if low.startswith(prefix):
                    aliases.append(name.strip()[len(prefix) :])
            if low.endswith(" island"):
                stem = name.strip()[: -len(" island")]
                # "Scilly" belongs to St Mary's, not the 0.02 km² rock named Scilly Island.
                if fold(stem) not in {"scilly"}:
                    aliases.append(stem)
            if "flannan" in low:
                aliases.extend(["Flannan Isles", "Flannan Islands"])
            if "shiant" in low:
                aliases.extend(["Shiant Isles", "Shiant Islands", "the Shiants"])
        for alias in aliases:
            cleaned = _clean_alias(alias)
            if not cleaned:
                continue
            key = (island["id"], fold(cleaned))
            if key in seen:
                continue
            seen.add(key)
            pairs.append((cleaned, island))
    pairs.sort(key=lambda pair: len(fold(pair[0])), reverse=True)
    return pairs


def qid_index(islands: list[dict]) -> dict[str, dict]:
    mapping: dict[str, dict] = {}
    for island in islands:
        qid = island.get("wikidata") or ""
        if not qid.startswith("Q"):
            continue
        previous = mapping.get(qid)
        if previous is None:
            mapping[qid] = island
            continue
        previous_curated = not re.match(r"^(osm-|wd-|csv-)", previous["id"])
        this_curated = not re.match(r"^(osm-|wd-|csv-)", island["id"])
        if this_curated and not previous_curated:
            mapping[qid] = island
        elif this_curated == previous_curated and island["area"] > previous["area"]:
            mapping[qid] = island
    return mapping


def context_tokens(island: dict) -> set[str]:
    tokens = set()
    for value in (island["nation"], island["archipelago"], island["water"], *EXTRA_CONTEXT.get(island["id"], [])):
        folded = fold(value)
        if folded and folded not in MAINLANDS and folded not in BLOCK_BARE and len(folded) >= 4:
            tokens.add(folded)
    return tokens


def wiki_get(params: dict) -> dict:
    url = WIKIPEDIA_API + "?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            return http_json(
                url,
                timeout=60,
                user_agent="IslesOfBritain/0.1 (https://www.findmyisland.com)",
            )
        except Exception:
            time.sleep(4 * (attempt + 1))
    return {}


def discover_categories() -> list[str]:
    found = []
    for prefix in ("Novels set", "Short stories set", "Children's books set", "Books set", "Memoirs of"):
        payload = wiki_get(
            {
                "action": "query",
                "format": "json",
                "list": "allcategories",
                "acprefix": prefix,
                "aclimit": "500",
            }
        )
        for item in ((payload.get("query") or {}).get("allcategories") or []):
            title = item.get("*") or ""
            if not title or CITY_CATEGORY.search(title) or FOREIGN_CATEGORY.search(title):
                continue
            generic_islands = fold(title) in {
                "novels set on islands",
                "books set on islands",
                "short stories set on islands",
                "children's books set on islands",
            }
            if REMIT_CATEGORY.search(title) or generic_islands:
                found.append(title)
        time.sleep(0.6)
    # Stable order: a category that names a small place comes before a nation.
    def rank(title: str) -> tuple:
        low = title.lower()
        setting = 0 if " set " in f" {low} " else 1
        broad = 1 if re.search(r"\b(scotland|ireland|england|wales|northern ireland|united kingdom|britain)\b", low) else 0
        specific = 0 if re.search(
            r"orkney|shetland|hebrides|skye|islay|jura|arran|mull|guernsey|jersey|scilly|anglesey|wight|lundy|iona|channel|manx",
            low,
        ) else 1
        return (setting, specific, broad, low)

    ordered = []
    seen = set()
    for title in sorted(found, key=rank):
        key = fold(title)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(title)
    return ordered


def category_members(title: str, cap: int) -> list[str]:
    pages = []
    params = {
        "action": "query",
        "format": "json",
        "list": "categorymembers",
        "cmtitle": f"Category:{title}",
        "cmtype": "page",
        "cmlimit": "500",
    }
    while len(pages) < cap:
        payload = wiki_get(params)
        members = (payload.get("query") or {}).get("categorymembers") or []
        for item in members:
            name = item.get("title") or ""
            if name and not name.startswith("List of") and "Category:" not in name:
                pages.append(name)
                if len(pages) >= cap:
                    break
        cont = (payload.get("continue") or {}).get("cmcontinue")
        if not cont or not members:
            break
        params["cmcontinue"] = cont
        time.sleep(1.2)
    return pages


def category_cap(title: str) -> int:
    low = title.lower()
    for nation, cap in BROAD_CAPS.items():
        if re.search(rf"\b{re.escape(nation)}\b", low) and not re.search(
            r"\b(orkney|shetland|hebrides|scilly|skye|mull|islay|arran|guernsey|jersey|anglesey|wight)\b",
            low,
        ):
            return cap
    return 80


def fetch_extracts(titles: list[str]) -> dict[str, dict]:
    """One page at a time. Anonymous Wikipedia returns a single extract per request,
    and exchars cannot exceed 1,200, so a batched request stored blank leads."""
    import json

    cache_path = CACHE / "extracts.json"
    cache = {}
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    missing = []
    seen = set()
    for title in titles:
        key = fold(title)
        if not key or key in seen:
            continue
        seen.add(key)
        existing = cache.get(key) or {}
        if existing.get("extract") or existing.get("absent"):
            continue
        missing.append(title.replace("_", " "))
    for index, title in enumerate(missing, start=1):
        payload = wiki_get(
            {
                "action": "query",
                "format": "json",
                "redirects": "1",
                "prop": "extracts",
                "exchars": "1200",
                "explaintext": "1",
                "titles": title,
            }
        )
        query = payload.get("query") or {}
        if not query:
            print(f"extract failed {title}", flush=True)
            time.sleep(8)
            continue
        redirect_of = {}
        for item in query.get("redirects") or []:
            redirect_of.setdefault(item.get("to"), []).append(item.get("from"))
        stored = False
        for page in (query.get("pages") or {}).values():
            page_title = page.get("title") or title
            if page.get("missing") is not None:
                cache[fold(page_title)] = {"title": page_title, "extract": "", "absent": True}
                cache[fold(title)] = cache[fold(page_title)]
                stored = True
                continue
            extract = page.get("extract") or ""
            if not extract.strip():
                continue
            previous = cache.get(fold(page_title)) or {}
            record = {
                "title": page_title,
                "extract": extract,
                "image": previous.get("image") or "",
                "images": previous.get("images") or [],
                "plot": previous.get("plot") or "",
                "plot_fetched": previous.get("plot_fetched") or False,
            }
            for name in (page_title, title, *(redirect_of.get(page_title) or [])):
                if name:
                    cache[fold(name)] = record
            stored = True
        if stored and index % 25 == 0:
            cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        if index % 25 == 0 or index == len(missing):
            print(f"extracts {index}/{len(missing)}", flush=True)
        time.sleep(1.1)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return cache


def plain_wikitext(text: str) -> str:
    text = re.sub(r"<ref[^>]*>.*?</ref>", " ", text or "", flags=re.S | re.I)
    text = re.sub(r"<ref[^>]*/>", " ", text, flags=re.I)
    for _ in range(3):
        text = re.sub(r"\{\{[^{}]*\}\}", " ", text)
    text = re.sub(r"\[\[(?:[^|\]]+\|)?([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"'{2,}", "", text)
    text = re.sub(r"==+[^=]+==+", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_plot(title: str, cache: dict) -> str:
    """The lead is capped at 1,200 characters. The plot is the next section."""
    import json

    key = fold(title)
    record = dict(cache.get(key) or {})
    if record.get("plot_fetched"):
        return record.get("plot") or ""
    payload = wiki_get(
        {
            "action": "parse",
            "format": "json",
            "redirects": "1",
            "page": title,
            "prop": "wikitext",
            "section": "1",
        }
    )
    wikitext = ((payload.get("parse") or {}).get("wikitext") or {}).get("*") or ""
    plot = plain_wikitext(wikitext)[:4500]
    record["plot"] = plot
    record["plot_fetched"] = True
    record.setdefault("title", title)
    for name in {title, record.get("title") or title}:
        if name:
            cache[fold(name)] = record
    path = CACHE / "extracts.json"
    path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    time.sleep(0.15)
    return plot


def attach_images(titles: list[str], cache: dict) -> None:
    import json

    missing = []
    for title in titles:
        record = cache.get(fold(title)) or {}
        if record.get("images") or record.get("image"):
            continue
        missing.append(record.get("title") or title)
    for start in range(0, len(missing), 16):
        batch = missing[start : start + 16]
        payload = wiki_get(
            {
                "action": "query",
                "format": "json",
                "redirects": "1",
                "prop": "pageimages|images",
                "piprop": "name",
                "imlimit": "8",
                "titles": "|".join(batch),
            }
        )
        for page in ((payload.get("query") or {}).get("pages") or {}).values():
            page_title = page.get("title") or ""
            record = dict(cache.get(fold(page_title)) or {"title": page_title, "extract": ""})
            record["image"] = page.get("pageimage") or record.get("image") or ""
            record["images"] = [img.get("title") or "" for img in page.get("images") or [] if img.get("title")]
            if page_title:
                cache[fold(page_title)] = record
        time.sleep(0.4)
    (CACHE / "extracts.json").write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def wikidata_books() -> list[dict]:
    cache_path = CACHE / "wikidata.json"
    if cache_path.exists():
        import json

        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if cached.get("version") == 3 and cached.get("rows") is not None:
            print(f"wikidata cache {len(cached['rows'])}", flush=True)
            return cached["rows"]
    query = """
SELECT DISTINCT ?work ?workLabel ?place ?placeLabel ?article ?image WHERE {
  {
    ?work wdt:P840 ?place .
  } UNION {
    ?work wdt:P921 ?place .
    ?work wdt:P31/wdt:P279* wd:Q571 .
  }
  ?place wdt:P31/wdt:P279* wd:Q23442 .
  ?place p:P625/psv:P625 [
    wikibase:geoLatitude ?lat ;
    wikibase:geoLongitude ?lon
  ] .
  # Great Britain, Ireland, and the countries are islands in Wikidata.
  # A novel set in the country is not a novel set on a smaller island.
  FILTER(?place NOT IN (wd:Q145, wd:Q236, wd:Q23666, wd:Q21, wd:Q22, wd:Q25, wd:Q26, wd:Q27, wd:Q22890, wd:Q38272))
  FILTER(?lat > 49.6 && ?lat < 61.2 && ?lon > -11.2 && ?lon < 2.2)
  ?article schema:about ?work ; schema:isPartOf <https://en.wikipedia.org/> .
  OPTIONAL { ?work wdt:P18 ?image }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
LIMIT 800
"""
    try:
        payload = _wikidata_sparql(query)
    except Exception as exc:
        print(f"wikidata skipped: {exc}", flush=True)
        return []
    rows = []
    for binding in payload.get("results", {}).get("bindings", []):
        article = binding.get("article", {}).get("value") or ""
        title = urllib.parse.unquote(article.rsplit("/", 1)[-1]).replace("_", " ") if article else ""
        image = binding.get("image", {}).get("value") or ""
        file_name = urllib.parse.unquote(image.rsplit("/", 1)[-1]).replace("_", " ") if image else ""
        place_label = binding.get("placeLabel", {}).get("value") or ""
        if fold(place_label) in MAINLANDS:
            continue
        rows.append(
            {
                "title": title,
                "place": binding.get("place", {}).get("value", "").rsplit("/", 1)[-1],
                "place_label": place_label,
                "qid": binding.get("work", {}).get("value", "").rsplit("/", 1)[-1],
                "image": f"File:{file_name}" if file_name else "",
            }
        )
    import json

    cache_path.write_text(json.dumps({"version": 3, "rows": rows}, ensure_ascii=False), encoding="utf-8")
    print(f"wikidata {len(rows)}", flush=True)
    return rows


def load_seeds() -> list[dict]:
    import json

    seeds = []
    if not SEEDS.exists():
        return seeds
    for path in sorted(SEEDS.glob("books-*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in payload.get("books") or []:
            url = item.get("wikipedia") or ""
            if "/wiki/" not in url:
                continue
            title = urllib.parse.unquote(url.split("/wiki/", 1)[1]).replace("_", " ")
            seeds.append({"title": title, "island": item.get("island") or "", "source": path.name})
    print(f"seeds {len(seeds)}", flush=True)
    return seeds


def lead_is_book(extract: str) -> bool:
    head = (extract or "")[:500]
    if NOT_A_BOOK.search(head) and not BOOK_LEAD.search(head):
        return False
    return bool(BOOK_LEAD.search(head))


def original_sentences(extract: str) -> list[str]:
    parts = _sentences(extract)
    if parts:
        return parts
    text = re.sub(r"\s+", " ", extract or "").strip()
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if len(part.strip()) > 25]


def alias_in_setting(sentence: str, alias: str) -> bool:
    folded = fold(sentence)
    needle = fold(alias)
    if not needle or needle not in folded:
        return False
    if not re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", folded):
        return False
    needle_at = folded.find(needle)
    if needle_at >= 0 and re.search(r"fictional", folded[max(0, needle_at - 55) : needle_at]):
        return False
    direct = [
        rf"\bset (?:mainly |largely |mostly |partly |primarily |briefly )?(?:on|in|at|upon) (?:the )?(?:[\w'-]+ ){{0,3}}(?:isle of |island of |islands of )?{re.escape(needle)}\b",
        rf"\btakes place (?:mainly |largely |mostly |partly )?(?:on|in|at) (?:the )?(?:[\w'-]+ ){{0,3}}(?:isle of |island of |islands of )?{re.escape(needle)}\b",
        rf"\b(?:shipwrecked|marooned|stranded) on (?:the )?(?:isle of |island of )?{re.escape(needle)}\b",
        rf"\b(?:life|childhood|youth|years|time|stay) (?:living |spent )?(?:on|in) (?:the )?(?:isle of |island of )?{re.escape(needle)}\b",
        rf"\bgrew up (?:on|in) (?:the )?(?:isle of |island of )?{re.escape(needle)}\b",
        rf"\b(?:his|her|their) (?:life|years|childhood|time|stay) (?:on|in) (?:the )?(?:isle of |island of )?{re.escape(needle)}\b",
        rf"\baccount of (?:(?:his|her|their) )?(?:life|years|time|stay|visit|journey) (?:on|in|to) (?:the )?(?:isle of |island of |islands of )?{re.escape(needle)}\b",
        rf"\b(?:memoir|autobiography) of (?:(?:his|her|their) )?(?:life|years|childhood) (?:on|in) (?:the )?{re.escape(needle)}\b",
        rf"\bdescribes (?:his|her|their) (?:time|stay|life|years|visit) (?:on|in) (?:the )?(?:isle of |island of )?{re.escape(needle)}\b",
        rf"\brecounts (?:his|her|their) (?:time|stay|life|years) (?:on|in) (?:the )?(?:isle of |island of )?{re.escape(needle)}\b",
    ]
    direct.append(rf"\b(?:live|lives) on (?:the )?(?:isle of |island of |islands of )?{re.escape(needle)}\b")
    direct.append(rf"\bheld on (?:the )?(?:isle of |island of )?{re.escape(needle)}\b")
    direct.append(rf"\bon the (?:isle|island) of {re.escape(needle)}\b")
    if not re.search(r"\bdedicated to\b", folded):
        direct.append(rf"\bto the (?:[\w'-]+ ){{0,2}}(?:isle|island) of {re.escape(needle)}\b")
    direct.append(
        rf"\b(?:returns|sails|goes|comes|travels|travelled|journeys) to the (?:isle|island) of {re.escape(needle)}\b"
    )
    # "visit to the Isle of Lewis ... as the setting for the book"
    direct.append(rf"(?<!\w){re.escape(needle)}(?!\w).{{0,90}}\bsetting\b")
    direct.append(rf"\bsetting\b.{{0,70}}(?<!\w){re.escape(needle)}(?!\w)")
    if needle in {"jersey", "guernsey", "sark", "alderney", "herm"} and re.search(
        r"\bset in the channel islands\b", folded
    ):
        direct.append(rf"(?<!\w){re.escape(needle)}(?!\w)")
    inspired = bool(INSPIRED.search(folded))
    if any(re.search(pattern, folded) for pattern in direct):
        return not inspired or bool(
            re.search(
                rf"\bset (?:on|in|at|upon) (?:the )?(?:isle of |island of )?{re.escape(needle)}\b",
                folded,
            )
        )
    return False


def match_islands(sentence: str, alias_index: list[tuple[str, dict]], hinted: dict | None) -> list[tuple[dict, str]]:
    hits: dict[str, tuple[int, dict, str]] = {}
    for alias, island in alias_index:
        if not alias_in_setting(sentence, alias):
            continue
        score = len(fold(alias))
        previous = hits.get(island["id"])
        if previous is None or score > previous[0]:
            hits[island["id"]] = (score, island, alias)
    if not hits:
        return []
    best_score = max(item[0] for item in hits.values())
    # Drop a shorter shared name when a longer name in the same sentence won.
    contenders = [item for item in hits.values() if item[0] >= best_score - 2]
    if len(contenders) == 1:
        _score, island, alias = contenders[0]
        return [(island, alias)]
    folded = fold(sentence)
    ranked = []
    for score, island, alias in contenders:
        bonus = sum(3 for token in context_tokens(island) if token in folded)
        if hinted and hinted["id"] == island["id"]:
            bonus += 5
        ranked.append((score + bonus, island, alias))
    ranked.sort(key=lambda item: (item[0], item[1]["area"]), reverse=True)
    if ranked[0][0] >= ranked[1][0] + 3:
        return [(ranked[0][1], ranked[0][2])]
    ranked.sort(key=lambda item: (item[0], item[1]["area"]), reverse=True)
    if ranked[0][1]["area"] > max(ranked[1][1]["area"], 0.01) * 8 and ranked[0][1]["area"] > 20:
        return [(ranked[0][1], ranked[0][2])]
    with_area = [item for item in ranked if item[1]["area"] > 0]
    if len(with_area) == 1:
        return [(with_area[0][1], with_area[0][2])]
    qids = {item[1]["wikidata"] for item in ranked if item[1].get("wikidata")}
    if len(qids) == 1:
        curated = [item for item in ranked if not re.match(r"^(osm-|wd-|csv-)", item[1]["id"])]
        if len(curated) == 1:
            return [(curated[0][1], curated[0][2])]
    return []


def display_title(article_title: str) -> str:
    return PAREN_TITLE.sub("", article_title or "").strip()


WORK_TITLE = re.compile(
    r"\b(?:book|novel|novella|memoir|autobiography)\s+"
    r"([A-Z][A-Za-z0-9'’:\-]+(?:\s+[A-Z][A-Za-z0-9'’:\-]+){0,8})"
)


def row_title(article_title: str, extract: str, sentence: str) -> str:
    """Use the book name when the page is the author or the island."""
    shown = display_title(article_title)
    head = re.sub(r"\s+", " ", (extract or "")[:320])
    if re.search(
        rf"\b{re.escape(shown)} is an? (?:[\w'-]+ ){{0,4}}(?:novel|novella|memoir|autobiography|children's book|picture book)\b",
        head,
        re.I,
    ):
        return shown
    match = WORK_TITLE.search(sentence or "") or WORK_TITLE.search(head)
    if match and fold(match.group(1)) != fold(shown):
        return match.group(1).strip(" ,;:")
    return shown


def build_summary(extract: str, setting: str) -> str:
    sentences = original_sentences(extract)
    identity = sentences[0] if sentences else ""
    identity = re.sub(r"\s+", " ", identity).strip()
    setting = re.sub(r"\s+", " ", setting).strip()
    if setting and setting not in identity:
        text = f"{identity} {setting}".strip()
    else:
        text = identity or setting
    if len(text) > 650:
        text = text[:630].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    return text


def island_photo(island: dict) -> dict | None:
    for image in island.get("images") or []:
        licence = image.get("license") or image.get("licence") or ""
        thumb = image.get("thumbUrl") or image.get("url") or ""
        if not thumb or not licence:
            continue
        if not OPEN_IMAGE_LICENCE.search(licence) or CLOSED_IMAGE_LICENCE.search(licence):
            continue
        filename = thumb + (image.get("caption") or "")
        if MAPISH_IMAGE.search(filename):
            continue
        return {
            "thumbUrl": thumb,
            "pageUrl": image.get("sourcePageUrl") or image.get("sourceUrl") or "",
            "attribution": image.get("attribution") or "Wikimedia Commons",
            "licence": licence,
            "licenceUrl": image.get("licenseUrl") or image.get("licenceUrl") or "",
        }
    return None


def choose_commons_file(record: dict, cache: dict) -> str:
    names = []
    if record.get("image"):
        names.append(record["image"])
    names.extend(record.get("images") or [])
    ranked = []
    for name in names:
        if not name or MAPISH_IMAGE.search(name):
            continue
        low = name.lower()
        if re.search(r"portrait|signature|logo|icon|stamp|coin|disambig|wikidata", low):
            continue
        image = _image_from_file(name, cache)
        if not image:
            continue
        score = 1
        if re.search(r"cover|frontispiece|title[-_ ]page|dust[-_ ]jacket|illustration", low):
            score += 5
        ranked.append((score, name if name.startswith("File:") else f"File:{name}"))
    if not ranked:
        return ""
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1]


TARGET_CATEGORIES = (
    "Novels set in the Hebrides",
    "Novels set in the Outer Hebrides",
    "Novels set in the Inner Hebrides",
    "Novels set in Orkney",
    "Novels set in Shetland",
    "Novels set on the Isle of Skye",
    "Novels set in the Isle of Skye",
    "Novels set on Skye",
    "Novels set on the Isle of Mull",
    "Novels set in Islay",
    "Novels set in the Isle of Man",
    "Novels set on the Isle of Man",
    "Novels set on the Isle of Wight",
    "Novels set in the Isle of Wight",
    "Novels set in Guernsey",
    "Novels set in Jersey",
    "Novels set in the Channel Islands",
    "Novels set in the Isles of Scilly",
    "Novels set in Anglesey",
    "Novels set in Scotland",
    "Novels set in Ireland",
    "Novels set in Wales",
    "Novels set in Northern Ireland",
    "Children's books set in Scotland",
    "Children's books set in Ireland",
    "Children's books set in Wales",
    "Children's books set in Guernsey",
    "Children's books set on the Isle of Wight",
    "Children's books set on islands",
    "Short stories set in Scotland",
    "Short stories set in Ireland",
    "Short stories set in Orkney",
    "Short stories set in Shetland",
)
SEARCH_PLACES = (
    "Isle of Skye",
    "Isle of Mull",
    "Iona",
    "Islay",
    "Jura",
    "Isle of Arran",
    "Orkney",
    "Shetland",
    "Isle of Lewis",
    "Harris",
    "Barra",
    "St Kilda",
    "Staffa",
    "Isle of Rum",
    "Eigg",
    "Coll",
    "Tiree",
    "Erraid",
    "Earraid",
    "Guernsey",
    "Jersey",
    "Sark",
    "Alderney",
    "Isle of Man",
    "Isle of Wight",
    "Lundy",
    "Isles of Scilly",
    "Lindisfarne",
    "Anglesey",
    "Bardsey",
    "Burgh Island",
    "Brownsea",
    "Inishmore",
    "Aran Islands",
    "Achill",
    "Rathlin",
    "Tory Island",
    "Cape Clear",
    "Valentia Island",
    "Clare Island",
    "Papa Westray",
    "Fair Isle",
    "Flannan",
    "Shiant",
    "Benbecula",
    "South Uist",
    "North Uist",
    "Bute",
    "Raasay",
    "Hoy",
    "Foula",
    "Skomer",
    "Caldey",
    "St Michael's Mount",
    "Belle Isle",
)


def search_pages(phrase: str) -> list[str]:
    payload = wiki_get(
        {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": f'"{phrase}" ("set on" OR "set in" OR "takes place" OR memoir) (novel OR memoir OR book)',
            "srnamespace": "0",
            "srlimit": "8",
        }
    )
    return [
        item.get("title")
        for item in ((payload.get("query") or {}).get("search") or [])
        if item.get("title")
    ]


def island_page_titles() -> list[str]:
    import json

    cache_path = CACHE / "page_titles_v2.json"
    if cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if cached:
            print(f"page title cache {len(cached)}", flush=True)
            return cached
    found = []
    for category in TARGET_CATEGORIES:
        members = category_members(category, 80)
        print(f"category {category}: {len(members)}", flush=True)
        found.extend(members)
        time.sleep(1.1)
    for phrase in SEARCH_PLACES:
        pages = search_pages(phrase)
        print(f"search {phrase}: {len(pages)}", flush=True)
        found.extend(pages)
        time.sleep(1.1)
    cache_path.write_text(json.dumps(found, ensure_ascii=False), encoding="utf-8")
    return found


def collect_titles(max_pages: int) -> tuple[list[str], dict[str, dict], list[dict]]:
    import json

    titles = []
    hinted: dict[str, dict] = {}
    wikidata_rows = wikidata_books()
    for item in wikidata_rows:
        if item.get("title"):
            titles.append(item["title"])
            hinted[fold(item["title"])] = item
    seeds = load_seeds()
    for item in seeds:
        titles.append(item["title"])
    titles.extend(island_page_titles())
    ordered = []
    seen = set()
    for title in titles:
        key = fold(title)
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(title)
    limit = max(max_pages, 1200)
    return ordered[:limit], hinted, wikidata_rows


def populate_books(atlas=None, max_pages: int = 700) -> list[dict]:
    del atlas
    CACHE.mkdir(parents=True, exist_ok=True)
    islands = load_islands()
    by_qid = qid_index(islands)
    alias_index = build_alias_index(islands)
    print(f"islands {len(islands)} aliases {len(alias_index)}", flush=True)
    titles, hinted, _wikidata_rows = collect_titles(max_pages)
    extracts = fetch_extracts(titles)
    accepted: dict[tuple[str, str], dict] = {}
    rejected = []
    for title in titles:
        record = extracts.get(fold(title)) or {}
        extract = record.get("extract") or ""
        article_title = record.get("title") or title
        if not extract or "may refer to" in extract[:180].lower():
            continue
        bookish = lead_is_book(extract)
        names_setting = bool(re.search(r"\b(setting for|is set|set on|set in|takes place)\b", extract, re.I))
        if not bookish and not names_setting:
            continue
        hint_row = hinted.get(fold(title)) or hinted.get(fold(article_title)) or {}
        hinted_island = by_qid.get(hint_row.get("place") or "")

        def sentences_for(text: str) -> dict[str, tuple[str, str]]:
            found: dict[str, tuple[str, str]] = {}
            for sentence in original_sentences(text):
                for island, alias in match_islands(sentence, alias_index, hinted_island):
                    previous = found.get(island["id"])
                    if previous is None or len(alias) > len(previous[1]):
                        found[island["id"]] = (sentence, alias)
            return found

        matched = sentences_for(extract)
        if bookish and not matched:
            plot = fetch_plot(article_title, extracts)
            if plot:
                matched = sentences_for(extract + "\n" + plot)
        if not matched:
            # Keep a short audit when the article names an island and still fails.
            folded = fold(extract)
            named = [
                island["name"]
                for _alias, island in alias_index
                if len(fold(_alias)) >= 6 and re.search(rf"(?<!\w){re.escape(fold(_alias))}(?!\w)", folded)
            ]
            if named and len(rejected) < 250:
                rejected.append(
                    row(
                        category=SLUG,
                        island_id="",
                        island_name=named[0],
                        facet="book",
                        title=display_title(article_title),
                        source_url="https://en.wikipedia.org/wiki/"
                        + urllib.parse.quote(article_title.replace(" ", "_")),
                        source_title=article_title,
                        licence="CC BY-SA 4.0",
                        evidence=f"The article names {named[0]} without a sentence that sets the book there.",
                        status="rejected",
                        confidence="medium",
                        reject_reason="the article does not set the book on the island",
                    )
                )
            continue
        for island_id, (sentence, alias) in matched.items():
            island = next(item for item in islands if item["id"] == island_id)
            key = (island_id, fold(row_title(article_title, extract, sentence)))
            if key in accepted:
                continue
            summary = build_summary(extract, sentence)
            if fold(island["name"]) not in fold(summary) and fold(alias) not in fold(summary):
                summary = f"{summary} The article sets it on {island['name']}."
            shown = row_title(article_title, extract, sentence)
            if not shown or len(shown) < 2:
                continue
            item = row(
                category=SLUG,
                island_id=island_id,
                island_name=island["name"],
                facet="book",
                title=shown,
                source_url="https://en.wikipedia.org/wiki/" + urllib.parse.quote(article_title.replace(" ", "_")),
                source_title=article_title,
                licence="CC BY-SA 4.0",
                evidence=sentence,
                external_id=hint_row.get("qid") or "",
                status="accepted",
                confidence="high",
                summary=summary,
            )
            item["_extract_key"] = fold(article_title)
            accepted[key] = item
    media = _load_media_cache()
    attach_images([item.get("source_title") or item["title"] for item in accepted.values()], extracts)
    filenames = []
    for item in accepted.values():
        record = extracts.get(item.get("_extract_key") or "") or {}
        if record.get("image"):
            filenames.append(record["image"])
        filenames.extend(record.get("images") or [])
    _commons_records(filenames, media)
    rows = []
    for item in accepted.values():
        record = extracts.get(item.pop("_extract_key", "")) or {}
        commons = choose_commons_file(record, media)
        island = next(island for island in islands if island["id"] == item["island_id"])
        if commons:
            item["commons_file"] = commons
        else:
            photo = island_photo(island)
            if photo:
                item["open_image"] = photo
                item["image_note"] = "Photograph of the island"
        rows.append(item)
    rows.extend(rejected)
    write_candidates(
        SLUG,
        rows,
        {
            "sources": ["english-wikipedia", "wikidata"],
            "rule": "The article sets the book on the island. Inspired by, based on, and filmed on do not count.",
        },
    )
    kept = [item for item in rows if item["status"] == "accepted"]
    pictured = sum(1 for item in kept if item.get("commons_file") or item.get("open_image"))
    print(
        f"accepted {len(kept)} on {len({item['island_id'] for item in kept})} islands, {pictured} with a picture",
        flush=True,
    )
    return rows


def main(argv: list[str]) -> int:
    max_pages = 700
    if "--max-pages" in argv:
        max_pages = int(argv[argv.index("--max-pages") + 1])
    populate_books(max_pages=max_pages)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
