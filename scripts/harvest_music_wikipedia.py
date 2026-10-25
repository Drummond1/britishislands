#!/usr/bin/env python3
"""Harvest music and band rows from English Wikipedia categories.

Walks place categories (musical groups, musicians, songs, albums, and so on),
keeps a page only when it is a cited music work or musician and the place
resolves to one atlas island, and writes

  data/interest/candidates/music-wikipedia.json

Does not publish, and does not edit the island catalogue.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.parse
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from artwork_harvest_common import (  # noqa: E402
    existing_music_keys,
    match_island_phrase,
    music_row,
    phrase_in_text,
)
from ingest_sources import name_key  # noqa: E402
from interest_categories import (  # noqa: E402
    Atlas,
    fold,
    http_json,
    load_json,
    save_json,
    utc_now,
)

WIKI_API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "IslesOfBritain/0.1 (https://www.findmyisland.com)"
CACHE = ROOT / "data" / "cache_music_wikipedia"
PARTIAL = CACHE / "_partial_rows.json"
OUT = ROOT / "data" / "interest" / "candidates" / "music-wikipedia.json"

PREFIXES = (
    "Musical groups from",
    "Musicians from",
    "Singers from",
    "Bands from",
    "Songwriters from",
    "Composers from",
    "Songs about",
    "Albums recorded in",
    "Albums recorded at",
    "Music of",
)

# Bare topics that also collide with an "Isle of …" / "… Island" name key.
# "Songs about dogs" is not Dogs Island. A qualified category still matches
# because its phrase is "Dogs Island" or "Isle of Dogs", not "dogs".
BARE_TOPICS = {
    "dog",
    "dogs",
    "cat",
    "cats",
    "bird",
    "birds",
    "fish",
    "horse",
    "horses",
    "sheep",
    "cow",
    "cows",
    "love",
    "war",
    "peace",
    "death",
    "life",
    "home",
    "christmas",
    "summer",
    "winter",
    "spring",
    "autumn",
    "night",
    "fire",
    "water",
    "rain",
    "snow",
    "sea",
    "ocean",
    "river",
    "women",
    "men",
    "girl",
    "girls",
    "boy",
    "boys",
    "children",
    "people",
    "god",
    "gods",
    "time",
    "world",
    "heart",
    "dream",
    "dreams",
    "freedom",
    "money",
    "food",
    "wine",
    "beer",
    "whisky",
    "islands",
    "island",
    "music",
    "song",
    "songs",
    "band",
    "bands",
}

# Nations and the whole of Great Britain or Ireland are not island categories.
NATION_PHRASES = {
    "great britain",
    "britain",
    "ireland",
    "england",
    "scotland",
    "wales",
    "united kingdom",
    "the united kingdom",
    "uk",
    "northern ireland",
    "republic of ireland",
    "british isles",
    "the british isles",
}

# These names also belong to well-known places outside the atlas. A category
# counts only when the phrase resolves to one atlas island, so a bare overseas
# homonym is not enough. A UK or Irish country in the category title keeps it.
OVERSEAS_HOMONYMS = {
    "long island",
    "rhode island",
    "prince edward island",
    "staten island",
    "coney island",
    "vancouver island",
    "manhattan island",
    "roosevelt island",
    "ellis island",
    "liberty island",
    "treasure island",
    "city island",
    "hilton head island",
    "galveston island",
    "amelia island",
    "merritt island",
    "new york",
    "new jersey",
    "new england",
}

# Towns and Thames aits that share a label with a small atlas island.
# "Composers from Oxford" is the city, not the Thames ait. A category that
# uses the island's own name ("Ramsey Island", "Cardigan Island") still matches.
MAINLAND_TOWNS = {
    "oxford",
    "douglas",
    "chiswick",
    "twickenham",
    "brentford",
    "maidenhead",
    "isleworth",
    "datchet",
    "dorney",
    "surbiton",
    "tilehurst",
    "weybridge",
    "staines",
    "staines-upon-thames",
    "medmenham",
    "kingston",
    "ramsey",
    "peel",
    "preston",
    "cardigan",
    "staffin",
    "tarbert",
    "moelfre",
    "cambridge",
    "windsor",
    "richmond",
    "chiswick",
}

HOME_QUALIFIER = re.compile(
    r"\b(Scotland|Scottish|England|English|Wales|Welsh|Ireland|Irish|"
    r"Isle of Man|Manx|United Kingdom|Channel Islands|Hebrides|Orkney|"
    r"Shetland|Guernsey|Jersey|Cornwall|Cornish|Argyll|Highland|"
    r"Cork|Mayo|Galway|Kerry|Donegal|Dublin|Antrim|Down|Devon|Dorset|"
    r"Kent|Essex|Suffolk|Norfolk|Hampshire|Sussex|Cumbria|Northumberland|"
    r"Anglesey|Pembrokeshire|Gwynedd|Outer Hebrides|Inner Hebrides)\b"
)

TRAILING_REGION = re.compile(
    r",\s*(?:in\s+)?(?:Scotland|England|Wales|Ireland|Northern Ireland|"
    r"the United Kingdom|United Kingdom|Great Britain|Britain|"
    r"the British Isles|British Isles|the UK|UK|"
    r"the Hebrides|Hebrides|the Inner Hebrides|Inner Hebrides|"
    r"the Outer Hebrides|Outer Hebrides|"
    r"the Channel Islands|Channel Islands)\s*$",
    re.I,
)

YEAR_PHRASE = re.compile(
    r"^(?:the\s+)?(?:(?:early|mid|late)\s+)?(?:1[0-9]{3}|20[0-9]{2})s?$"
    r"|^(?:the\s+)?\d{1,2}(?:st|nd|rd|th)\s+century$",
    re.I,
)
YEAR_TITLE = re.compile(
    r"^(?:category:|template:)?"
    r"(?:(?:the\s+)?(?:1[0-9]{3}|20[0-9]{2})s?(?:\s+in\b.*)?"
    r"|(?:1[0-9]{3}|20[0-9]{2})\s+in\b.*"
    r"|(?:1[0-9]{3}|20[0-9]{2})s?\s+(?:albums?|songs?|singles?|compositions?|in music)"
    r"|(?:the\s+)?\d{1,2}(?:st|nd|rd|th)\s+century(?:\b.*)?)$",
    re.I,
)

DISAMBIGUATION = re.compile(r"\b(?:may|might|can)\s+refer to\b", re.I)
OTHER_PERSON = re.compile(
    r"\b(?:his|her|their)\s+(?:father|mother|parents|son|daughter|brother|"
    r"sister|husband|wife|uncle|aunt|grandfather|grandmother|family|"
    r"children|child)\b",
    re.I,
)
WINDOW_CUT = re.compile(
    r"\b(?:known|famous|noted|celebrated|remembered)\s+for\b|\bhome to\b|"
    r"\bwho\b|\bwhich\b|\bwhose\b|\bwhere\b",
    re.I,
)
EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?:\+44[\s-]?|0)(?:\d[\s()-]?){9,}\d")
POSTCODE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.I)
STREET = re.compile(
    r"\b\d{1,4}\s+[A-Z][\w'.-]*(?:\s+[A-Z][\w'.-]*){0,4}\s+"
    r"(?:Street|St\.|Road|Rd\.|Avenue|Ave\.|Lane|Ln\.|Drive|Dr\.|Close|"
    r"Crescent|Way|Place|Terrace|Gardens|Court|Square|Row|Mews)\b"
)
CITATION = re.compile(r"\[(?:\s*\d+\s*|citation needed|nb\s*\d+)\]", re.I)

# Leftmost hit in the identity window wins. Performer words are included
# because Wikipedia leads say "guitarist" or "piper" rather than "musician".
ROLES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("singer-songwriter", re.compile(r"\bsinger-songwriters?\b", re.I)),
    ("musical group", re.compile(r"\bmusical groups?\b", re.I)),
    ("pipe band", re.compile(r"\bpipe bands?\b", re.I)),
    ("brass band", re.compile(r"\bbrass bands?\b", re.I)),
    ("ceilidh band", re.compile(r"\bceilidh bands?\b", re.I)),
    ("folk band", re.compile(r"\bfolk bands?\b", re.I)),
    ("rock band", re.compile(r"\brock bands?\b", re.I)),
    ("pop band", re.compile(r"\bpop bands?\b", re.I)),
    ("punk band", re.compile(r"\bpunk bands?\b", re.I)),
    ("jazz band", re.compile(r"\bjazz bands?\b", re.I)),
    ("indie band", re.compile(r"\bindie bands?\b", re.I)),
    ("boy band", re.compile(r"\bboy bands?\b", re.I)),
    ("band", re.compile(r"\bbands?\b(?!\s+of\b)", re.I)),
    ("folk group", re.compile(r"\bfolk groups?\b", re.I)),
    ("rock group", re.compile(r"\brock groups?\b", re.I)),
    ("pop group", re.compile(r"\bpop groups?\b", re.I)),
    ("girl group", re.compile(r"\bgirl groups?\b", re.I)),
    ("hip hop group", re.compile(r"\bhip[- ]hop groups?\b", re.I)),
    ("musical duo", re.compile(r"\b(?:musical|singing|pop|folk|vocal) duos?\b", re.I)),
    ("record producer", re.compile(r"\brecord producers?\b", re.I)),
    ("multi-instrumentalist", re.compile(r"\bmulti-instrumentalists?\b", re.I)),
    ("instrumentalist", re.compile(r"\binstrumentalists?\b", re.I)),
    ("guitarist", re.compile(r"\bguitarists?\b", re.I)),
    ("bassist", re.compile(r"\bbassists?\b", re.I)),
    ("drummer", re.compile(r"\bdrummers?\b", re.I)),
    ("pianist", re.compile(r"\bpianists?\b", re.I)),
    ("violinist", re.compile(r"\bviolinists?\b", re.I)),
    ("fiddler", re.compile(r"\bfiddlers?\b", re.I)),
    ("piper", re.compile(r"\bpipers?\b", re.I)),
    ("harpist", re.compile(r"\bharpists?\b", re.I)),
    ("cellist", re.compile(r"\bcellists?\b", re.I)),
    ("organist", re.compile(r"\borganists?\b", re.I)),
    ("saxophonist", re.compile(r"\bsaxophonists?\b", re.I)),
    ("trumpeter", re.compile(r"\btrumpeters?\b", re.I)),
    ("flautist", re.compile(r"\b(?:flautists?|flutists?)\b", re.I)),
    ("accordionist", re.compile(r"\baccordionists?\b", re.I)),
    ("vocalist", re.compile(r"\bvocalists?\b", re.I)),
    ("rapper", re.compile(r"\brappers?\b", re.I)),
    ("disc jockey", re.compile(r"\b(?:djs?|disc jockeys?)\b", re.I)),
    ("conductor", re.compile(r"\bconductors?\b", re.I)),
    ("singer", re.compile(r"\bsingers?\b", re.I)),
    ("songwriter", re.compile(r"\bsongwriters?\b", re.I)),
    ("composer", re.compile(r"\bcomposers?\b", re.I)),
    ("musician", re.compile(r"\bmusicians?\b", re.I)),
    ("soprano", re.compile(r"\bsopranos?\b", re.I)),
    ("mezzo-soprano", re.compile(r"\bmezzo-sopranos?\b", re.I)),
    ("contralto", re.compile(r"\bcontraltos?\b", re.I)),
    ("tenor", re.compile(r"\btenors?\b", re.I)),
    ("baritone", re.compile(r"\bbaritones?\b", re.I)),
    ("countertenor", re.compile(r"\bcountertenors?\b", re.I)),
    ("choir", re.compile(r"\bchoirs?\b", re.I)),
    ("orchestra", re.compile(r"\borchestras?\b", re.I)),
    ("string quartet", re.compile(r"\bstring quartets?\b", re.I)),
    ("opera", re.compile(r"\boperas?\b", re.I)),
    ("symphony", re.compile(r"\bsymphonies?\b", re.I)),
    ("concerto", re.compile(r"\bconcertos?\b", re.I)),
    ("cantata", re.compile(r"\bcantatas?\b", re.I)),
    ("sonata", re.compile(r"\bsonatas?\b", re.I)),
    ("album", re.compile(r"\balbums?\b", re.I)),
    (
        "single",
        re.compile(
            r"\bsingles?\b(?![\s-](?:storey|story|parent|handed|sex|track|line|"
            r"deck|mind|celled|phase|use|family|malt|room|bed)\b)",
            re.I,
        ),
    ),
    ("song", re.compile(r"\bsongs?\b", re.I)),
    ("ballad", re.compile(r"\bballads?\b", re.I)),
    ("hymn", re.compile(r"\bhymns?\b", re.I)),
    ("anthem", re.compile(r"\banthems?\b", re.I)),
    (
        "composition",
        re.compile(
            r"\bcompositions?\b(?!\s+of\s+the\s+(?:population|council|rock|soil|"
            r"island|committee|water|band))\b",
            re.I,
        ),
    ),
)

PER_ISLAND = 60
PAGES_PER_CATEGORY = 40
EXTRACT_BATCH = 15
SLEEP_SECONDS = 1.0

STATS = {"http": 0, "cache": 0, "fail": 0}
ATTEMPTED: set[str] = set()
FAILURES: list[str] = []
EMPTY_PREFIXES: list[str] = []


def cache_path(url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
    kind = "query"
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    if query.get("list"):
        kind = query["list"][0]
    elif query.get("prop"):
        kind = "extracts"
    return CACHE / f"wiki_{kind}_{digest}.json"


def api_url(params: dict) -> str:
    encoded = urllib.parse.urlencode(params, doseq=True, safe="|")
    return WIKI_API + "?" + encoded


def fetch(url: str) -> dict:
    """Cached GET. A failed response is stored and the walk continues."""
    path = cache_path(url)
    cached = load_json(path, None) if path.exists() else None
    if isinstance(cached, dict) and not cached.get("_error"):
        STATS["cache"] += 1
        return cached
    if url in ATTEMPTED and isinstance(cached, dict):
        return cached
    ATTEMPTED.add(url)
    STATS["http"] += 1
    try:
        payload = http_json(url, timeout=120, user_agent=USER_AGENT)
    except Exception as exc:
        payload = {"_error": f"{type(exc).__name__}: {exc}"[:500], "_url": url}
    if not isinstance(payload, dict):
        payload = {"_error": "response was not a JSON object", "_url": url}
    if payload.get("error") and not payload.get("_error"):
        info = payload["error"]
        text = info.get("info") if isinstance(info, dict) else str(info)
        payload = {"_error": str(text)[:500], "_url": url, "error": info}
    if payload.get("_error"):
        STATS["fail"] += 1
        FAILURES.append(payload["_error"][:240])
    save_json(path, payload)
    time.sleep(SLEEP_SECONDS)
    if STATS["http"] % 25 == 0:
        print(
            f"http {STATS['http']} cache {STATS['cache']} fail {STATS['fail']}",
            flush=True,
        )
    return payload


def paginate(params: dict):
    base = dict(params)
    seen_tokens: set[str] = set()
    current = dict(base)
    pages = 0
    while pages < 2500:
        pages += 1
        payload = fetch(api_url(current))
        if payload.get("_error"):
            yield payload
            return
        yield payload
        cont = payload.get("continue") or {}
        if not cont:
            return
        token = json.dumps(cont, sort_keys=True)
        if token in seen_tokens:
            return
        seen_tokens.add(token)
        current = dict(base)
        current.update({key: str(value) for key, value in cont.items()})


def clean_phrase(value: str) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"\s+", " ", text).strip(" ,.;:-–—")
    return text


def strip_trailing_region(value: str) -> str:
    current = clean_phrase(value)
    for _ in range(3):
        nxt = clean_phrase(TRAILING_REGION.sub("", current))
        if not nxt or fold(nxt) == fold(current):
            break
        current = nxt
    return current


def phrase_variants(raw: str) -> list[str]:
    raw = clean_phrase(raw)
    if not raw:
        return []
    seeds = [raw]
    no_paren = clean_phrase(re.sub(r"\s*\([^)]*\)", " ", raw))
    if no_paren:
        seeds.append(no_paren)
    expanded: list[str] = []
    for seed in seeds:
        expanded.append(seed)
        expanded.append(clean_phrase(re.split(r"\s+by\s+", seed, maxsplit=1, flags=re.I)[0]))
        trimmed = strip_trailing_region(seed)
        expanded.append(trimmed)
        expanded.append(clean_phrase(re.split(r"\s+by\s+", trimmed, maxsplit=1, flags=re.I)[0]))
    out: list[str] = []
    seen: set[str] = set()
    for seed in expanded:
        options = [seed]
        bare = re.sub(r"^the\s+", "", seed, flags=re.I).strip()
        if bare and bare != seed:
            options.append(bare)
        for item in options:
            item = clean_phrase(item)
            key = fold(item)
            if item and key not in seen:
                seen.add(key)
                out.append(item)
    return out


def place_after_prefix(category: str, prefix: str) -> str:
    name = category.split(":", 1)[1] if category.lower().startswith("category:") else category
    name = clean_phrase(name)
    match = re.match(r"^" + re.escape(prefix) + r"\s+(.+)$", name, flags=re.I)
    if not match:
        return ""
    return clean_phrase(match.group(1))


def is_year_phrase(phrase: str) -> bool:
    return bool(YEAR_PHRASE.match(fold(phrase)))


def could_be_island(phrase: str, names: set[str], keys: set[str]) -> bool:
    if fold(phrase) in names:
        return True
    key = name_key(phrase)
    return bool(key) and key in keys


def too_many_namesakes(atlas: Atlas, island: dict) -> bool:
    """Identical names on several small skerries do not resolve to one island."""
    same = [item for item in atlas.islands if fold(item["name"]) == fold(island["name"])]
    if len(same) < 3:
        return False
    largest = max(item.get("area") or 0 for item in same)
    return largest < 20


def overseas_homonym(phrase: str, category: str) -> bool:
    if fold(phrase) not in OVERSEAS_HOMONYMS:
        return False
    # "New England" contains "England"; ignore the phrase itself when looking
    # for a UK or Irish qualifier.
    remainder = re.sub(re.escape(phrase), " ", category or "", flags=re.I)
    return HOME_QUALIFIER.search(remainder) is None


# Countries, territories, and regions. A skerry that happens to share the name
# is not "Music of France" or "Music of Gibraltar".
NOT_OUR_PLACES = {
    "africa",
    "alaska",
    "algeria",
    "america",
    "argentina",
    "asia",
    "australia",
    "austria",
    "bahamas",
    "bangladesh",
    "barbados",
    "belgium",
    "bermuda",
    "brazil",
    "california",
    "canada",
    "chile",
    "china",
    "colombia",
    "cuba",
    "cyprus",
    "denmark",
    "egypt",
    "europe",
    "finland",
    "florida",
    "france",
    "germany",
    "ghana",
    "gibraltar",
    "greece",
    "greenland",
    "hawaii",
    "holland",
    "hong kong",
    "iceland",
    "india",
    "indonesia",
    "iran",
    "iraq",
    "israel",
    "italy",
    "jamaica",
    "japan",
    "kenya",
    "korea",
    "lebanon",
    "malta",
    "mexico",
    "monaco",
    "morocco",
    "nepal",
    "netherlands",
    "new england",
    "new jersey",
    "new york",
    "new zealand",
    "nigeria",
    "norway",
    "pakistan",
    "peru",
    "philippines",
    "poland",
    "portugal",
    "russia",
    "singapore",
    "south africa",
    "spain",
    "sri lanka",
    "sweden",
    "switzerland",
    "taiwan",
    "tasmania",
    "texas",
    "thailand",
    "tunisia",
    "turkey",
    "united states",
    "usa",
    "vietnam",
}


def not_our_place(phrase: str, island: dict) -> bool:
    if fold(phrase) not in NOT_OUR_PLACES:
        return False
    return (island.get("area") or 0) < 200


def generic_named_island(phrase: str, island: dict, category: str) -> bool:
    """'Songs about China' is not the skerry China Island.

    A category that actually says 'China Island', or a substantial island
    known by the short name (Rathlin Island, area 14 km²), still matches.
    """
    name = fold(island["name"])
    short = fold(phrase)
    if name not in {f"{short} island", f"{short} islands"}:
        return False
    if phrase_in_text(island["name"], category):
        return False
    return (island.get("area") or 0) < 1


def mainland_collision(phrase: str, island: dict, category: str) -> bool:
    """Reject a town or Thames ait that merely shares an island's short name."""
    island_id = str(island.get("id") or "")
    if island_id.startswith("thames-") and not re.search(r"\b(Thames|ait)\b", category or "", re.I):
        return True
    if fold(phrase) not in MAINLAND_TOWNS:
        return False
    # "Musicians from Ramsey Island" names the island. "Musicians from Ramsey" is the town.
    if phrase_in_text(island["name"], category) and fold(phrase) != fold(island["name"]):
        return False
    return True


def resolve_category(
    atlas: Atlas,
    category: str,
    prefix: str,
    names: set[str],
    keys: set[str],
) -> dict | None:
    raw = place_after_prefix(category, prefix)
    if not raw or is_year_phrase(raw):
        return None
    found: list[tuple[str, dict]] = []
    for variant in phrase_variants(raw):
        if fold(variant) in NATION_PHRASES or fold(variant) in BARE_TOPICS or is_year_phrase(variant):
            continue
        if len(fold(variant)) < 3:
            continue
        if not could_be_island(variant, names, keys):
            continue
        island = match_island_phrase(atlas, variant)
        if not island:
            continue
        if not phrase_in_text(variant, category) and not phrase_in_text(island["name"], category):
            continue
        if overseas_homonym(variant, category) or too_many_namesakes(atlas, island):
            continue
        if mainland_collision(variant, island, category):
            continue
        if not_our_place(variant, island) or generic_named_island(variant, island, category):
            continue
        found.append((variant, island))
    ids = {island["id"] for _, island in found}
    if len(ids) != 1:
        return None
    phrase, island = max(found, key=lambda item: len(item[0]))
    return {"name": category, "phrase": phrase, "island": island, "prefix": prefix}


def list_prefix(prefix: str, atlas: Atlas, names: set[str], keys: set[str]) -> list[dict]:
    matched: list[dict] = []
    seen: set[str] = set()
    found = 0
    errored = False
    params = {
        "action": "query",
        "format": "json",
        "list": "allcategories",
        "acprefix": prefix,
        "aclimit": "500",
    }
    for payload in paginate(params):
        if payload.get("_error"):
            errored = True
            FAILURES.append(f"{prefix}: {payload['_error'][:180]}")
            break
        batch = (payload.get("query") or {}).get("allcategories") or []
        found += len(batch)
        for item in batch:
            name = item.get("*") or item.get("category") or ""
            if not name:
                continue
            token = fold(name)
            if token in seen:
                continue
            resolved = resolve_category(atlas, name, prefix, names, keys)
            if not resolved:
                continue
            seen.add(token)
            matched.append(resolved)
        print(
            f"{prefix!r} +{len(batch)} scanned {found} matched {len(matched)}",
            flush=True,
        )
    if found == 0 and not errored:
        print(f"prefix returned no categories: {prefix}", flush=True)
    if not matched:
        EMPTY_PREFIXES.append(prefix)
    return matched


def skip_page_title(title: str) -> bool:
    low = (title or "").casefold().strip()
    if not low:
        return True
    if re.match(r"^(?:the\s+)?lists?\s+of\b", low):
        return True
    if "disambiguation" in low:
        return True
    if re.match(
        r"^(?:Category|Template|Wikipedia|Portal|File|Draft|Module|Help|User|"
        r"Talk|TimedText|MediaWiki):",
        title or "",
    ):
        return True
    if YEAR_TITLE.match(low):
        return True
    return False


def wiki_url(title: str) -> str:
    slug = urllib.parse.quote(title.replace(" ", "_"), safe="/:@!$&'()*+,;=")
    return "https://en.wikipedia.org/wiki/" + slug


def sentences(text: str) -> list[str]:
    text = CITATION.sub("", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    protected = re.sub(r"\b([A-Z])\.", r"\1§", text)
    protected = re.sub(
        r"\b(St|Mr|Mrs|Ms|Dr|Jr|Sr|No|Prof|Mt|Ft|Jan|Feb|Mar|Apr|Jun|Jul|Aug|"
        r"Sep|Sept|Oct|Nov|Dec)\.",
        lambda match: match.group(0).replace(".", "§"),
        protected,
    )
    parts = re.split(r"(?<=[.!?])\s+", protected)
    return [part.replace("§", ".").strip() for part in parts if part.strip()]


def first_sentence(text: str) -> str:
    found = sentences(text)
    return found[0] if found else ""


def find_role(text: str) -> str | None:
    best = None
    best_at = 10**9
    for label, pattern in ROLES:
        match = pattern.search(text or "")
        if match and match.start() < best_at:
            best = label
            best_at = match.start()
    return best


def detect_role(title: str, extract: str) -> str | None:
    if DISAMBIGUATION.search((extract or "")[:500]):
        return None
    paren = re.search(r"\(([^)]*)\)\s*$", title or "")
    if paren:
        role = find_role(paren.group(1))
        if role:
            return role
    for sentence in sentences(extract)[:4]:
        if DISAMBIGUATION.search(sentence):
            return None
        for match in re.finditer(r"\b(?:is|was|are|were)\b", sentence, flags=re.I):
            prefix = sentence[max(0, match.start() - 60) : match.start()]
            if OTHER_PERSON.search(prefix) and OTHER_PERSON.search(prefix).end() == len(prefix.rstrip()):
                continue
            window = sentence[match.end() : match.end() + 220]
            window = WINDOW_CUT.split(window, maxsplit=1)[0]
            window = OTHER_PERSON.split(window, maxsplit=1)[0]
            role = find_role(window)
            if role:
                return role
    return None


def scrub(text: str) -> str:
    cleaned = CITATION.sub("", text or "")
    cleaned = EMAIL.sub("", cleaned)
    cleaned = PHONE.sub("", cleaned)
    cleaned = POSTCODE.sub("", cleaned)
    cleaned = STREET.sub("", cleaned)
    cleaned = re.sub(r"\b(?:call|e-?mail|telephone)\b(?:\s+or\b)*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+,", ",", cleaned)
    cleaned = re.sub(r"(?<=\b(?:at|in|on|to))\s*,", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    cleaned = re.sub(r"\.{2,}", ".", cleaned)
    return cleaned.strip(" ,;:-")


def article(noun: str) -> str:
    return "an" if re.match(r"[aeiou]", noun or "", flags=re.I) else "a"


def mentions_island(island: dict, phrase: str, extract: str, category: str) -> bool:
    for blob in (extract or "", category or ""):
        if phrase_in_text(island["name"], blob):
            return True
        if phrase and phrase_in_text(phrase, blob):
            return True
    return False


def summary_title(title: str) -> str:
    stripped = re.sub(r"\s*\([^)]*\)\s*$", "", title or "").strip()
    return stripped or title


def linked_place(name: str) -> str:
    if re.match(r"(?:isle|island) of\b", name or "", flags=re.I):
        return f"the {name}"
    return name


def build_summary(title: str, extract: str, island_name: str, phrase: str, role: str) -> str:
    sentence = scrub(first_sentence(extract))
    if (
        sentence
        and find_role(sentence)
        and (
            phrase_in_text(island_name, sentence)
            or (phrase and phrase_in_text(phrase, sentence))
        )
    ):
        if sentence[-1:] not in ".!?":
            sentence += "."
        return sentence[:500]
    noun = role or "musician"
    place = linked_place(island_name)
    plural = noun.endswith("band") or noun.endswith("group") or noun in {
        "choir",
        "orchestra",
        "musical duo",
    }
    verb = "are" if plural else "is"
    return f"{summary_title(title)} {verb} {article(noun)} {noun} linked to {place}."[:500]


def commons_name(pageimage: str) -> str:
    name = (pageimage or "").strip().replace("_", " ")
    if not name:
        return ""
    if name.lower().startswith("file:"):
        return "File:" + name.split(":", 1)[1].strip()
    return f"File:{name}"


def member_titles(category: str) -> list[str]:
    titles: list[str] = []
    params = {
        "action": "query",
        "format": "json",
        "list": "categorymembers",
        "cmtitle": f"Category:{category}",
        "cmtype": "page",
        "cmlimit": str(PAGES_PER_CATEGORY),
    }
    for payload in paginate(params):
        if payload.get("_error"):
            FAILURES.append(f"members {category}: {payload['_error'][:180]}")
            break
        for item in (payload.get("query") or {}).get("categorymembers") or []:
            title = item.get("title") or ""
            if title:
                titles.append(title)
            if len(titles) >= PAGES_PER_CATEGORY:
                return titles[:PAGES_PER_CATEGORY]
        if len(titles) >= PAGES_PER_CATEGORY or not payload.get("continue"):
            break
    return titles[:PAGES_PER_CATEGORY]


def title_batches(titles: list[str]):
    batch: list[str] = []
    for title in titles:
        if "|" in title:
            if batch:
                yield batch
                batch = []
            yield [title]
            continue
        batch.append(title)
        if len(batch) >= EXTRACT_BATCH:
            yield batch
            batch = []
    if batch:
        yield batch


def fetch_pages(titles: list[str]) -> list[dict]:
    found: list[dict] = []
    seen: set[str] = set()
    for batch in title_batches(titles):
        params = {
            "action": "query",
            "format": "json",
            "redirects": "1",
            "prop": "extracts|pageimages",
            "exintro": "1",
            "explaintext": "1",
            "exlimit": str(EXTRACT_BATCH),
            "piprop": "name",
            "pithumbsize": "960",
            "pilimit": str(EXTRACT_BATCH),
            "titles": "|".join(batch),
        }
        payload = fetch(api_url(params))
        if payload.get("_error"):
            FAILURES.append(f"extracts: {payload['_error'][:180]}")
            continue
        query = payload.get("query") or {}
        pages = query.get("pages") or {}
        page_list = pages.values() if isinstance(pages, dict) else pages
        for page in page_list:
            if not isinstance(page, dict):
                continue
            if page.get("missing") is not None:
                continue
            title = page.get("title") or ""
            if not title or fold(title) in seen:
                continue
            seen.add(fold(title))
            found.append(
                {
                    "title": title,
                    "extract": page.get("extract") or "",
                    "commons_file": commons_name(page.get("pageimage") or ""),
                }
            )
    return found


def save_partial(rows: list[dict], stage: str) -> None:
    save_json(
        PARTIAL,
        {
            "stage": stage,
            "savedAt": utc_now(),
            "emptyPrefixes": list(EMPTY_PREFIXES),
            "rows": rows,
        },
    )


def write_output(rows: list[dict]) -> None:
    ordered = sorted(rows, key=lambda item: (fold(item.get("island_name") or ""), fold(item.get("title") or "")))
    save_json(
        OUT,
        {
            "slug": "music-wikipedia",
            "generatedAt": utc_now(),
            "sources": ["wikipedia-categories"],
            "rows": ordered,
        },
    )


def harvest(categories: list[dict], seen: set[tuple[str, str]], rows: list[dict], counts: Counter) -> None:
    for index, cat in enumerate(categories, start=1):
        island = cat["island"]
        if counts[island["id"]] >= PER_ISLAND:
            print(
                f"[{index}/{len(categories)}] {cat['name']} -> {island['name']} cap",
                flush=True,
            )
            continue
        try:
            titles = [title for title in member_titles(cat["name"]) if not skip_page_title(title)]
            added = 0
            for page in fetch_pages(titles):
                if counts[island["id"]] >= PER_ISLAND:
                    break
                title = page["title"]
                extract = page["extract"]
                if skip_page_title(title) or DISAMBIGUATION.search((extract or "")[:500]):
                    continue
                role = detect_role(title, extract)
                if not role:
                    continue
                if not mentions_island(island, cat["phrase"], extract, cat["name"]):
                    continue
                summary = build_summary(title, extract, island["name"], cat["phrase"], role)
                built = music_row(
                    island=island,
                    title=title,
                    source_url=wiki_url(title),
                    source_title=title,
                    licence="CC BY-SA 4.0",
                    evidence=f'English Wikipedia category "{cat["name"]}".',
                    summary=summary,
                    external_id=title.replace(" ", "_"),
                    commons_file=page.get("commons_file") or "",
                    seen=seen,
                )
                if not built:
                    continue
                rows.append(built)
                counts[island["id"]] += 1
                added += 1
            print(
                f"[{index}/{len(categories)}] {cat['name']} -> {island['name']} +{added} "
                f"({counts[island['id']]}/{PER_ISLAND})",
                flush=True,
            )
        except Exception as exc:
            FAILURES.append(f"{cat['name']}: {exc}")
            print(f"category failed {cat['name']}: {exc}", flush=True)
        if index % 5 == 0:
            save_partial(rows, "harvest")


def report(rows: list[dict]) -> None:
    by_island: Counter = Counter()
    for item in rows:
        by_island[item.get("island_name") or item.get("island_id") or "?"] += 1
    print("ACCEPTED", len(rows), flush=True)
    print("ISLANDS", len(by_island), flush=True)
    print("TOP12", flush=True)
    for name, count in by_island.most_common(12):
        print(f"  {count}\t{name}", flush=True)
    print("SAMPLES", flush=True)
    picked: list[dict] = []
    used: set[str] = set()
    for item in rows:
        island_id = item.get("island_id") or ""
        if island_id in used:
            continue
        picked.append(item)
        used.add(island_id)
        if len(picked) >= 8:
            break
    for item in rows:
        if len(picked) >= 8:
            break
        if item not in picked:
            picked.append(item)
    for item in picked[:8]:
        print(
            "  SAMPLE\t{island}\t{title}\t{url}".format(
                island=item.get("island_name") or "",
                title=item.get("title") or "",
                url=item.get("source_url") or "",
            ),
            flush=True,
        )
    print("EMPTY_PREFIXES", flush=True)
    if EMPTY_PREFIXES:
        for name in EMPTY_PREFIXES:
            print(f"  {name}", flush=True)
    else:
        print("  (none)", flush=True)
    print("FAILURES", len(FAILURES), flush=True)
    for line in FAILURES[:20]:
        print(f"  {line}", flush=True)
    print("OUTPUT", OUT, flush=True)
    print(
        f"http {STATS['http']} cache {STATS['cache']} fail {STATS['fail']}",
        flush=True,
    )


def assert_resolution(atlas: Atlas, names: set[str], keys: set[str]) -> None:
    expectations = (
        ("Musical groups from the Isle of Man", "Musical groups from", "isle of man"),
        ("Music of the Isle of Man", "Music of", "isle of man"),
        ("Music of Scotland", "Music of", None),
        ("Music of Great Britain", "Music of", None),
        ("Music of Ireland", "Music of", None),
        ("Musicians from England", "Musicians from", None),
        ("Musicians from Wales", "Musicians from", None),
        ("Musicians from Britain", "Musicians from", None),
        ("Musicians from the United Kingdom", "Musicians from", None),
        ("Musicians from Skye", "Musicians from", "isle of skye"),
        ("Songs about the Isle of Skye", "Songs about", "isle of skye"),
        ("Musical groups from Anglesey", "Musical groups from", "anglesey"),
        ("Musical groups from Canvey Island", "Musical groups from", "canvey island"),
        ("Albums recorded at the Isle of Wight", "Albums recorded at", "isle of wight"),
        ("Albums recorded in Skye", "Albums recorded in", "isle of skye"),
        ("Composers from the Isle of Wight", "Composers from", "isle of wight"),
        ("Musicians from Mull", "Musicians from", "isle of mull"),
        ("Musicians from the Isle of Mull", "Musicians from", "isle of mull"),
        ("Musical groups from Jersey", "Musical groups from", None),
        ("Musicians from Orkney", "Musicians from", None),
        ("Musicians from Shetland", "Musicians from", None),
        ("Musical groups from New Jersey", "Musical groups from", None),
        ("Musical groups from Long Island", "Musical groups from", None),
        ("Musical groups from Asbury Park, New Jersey", "Musical groups from", None),
        ("Albums recorded at Abbey Road", "Albums recorded at", None),
        ("Songs about dogs", "Songs about", None),
        ("Songs about islands", "Songs about", None),
        ("Songs about love", "Songs about", None),
        ("Songs about Christmas", "Songs about", None),
        ("Bands from Liverpool", "Bands from", None),
        ("Musicians from Manchester", "Musicians from", None),
        ("Musicians from Glasgow", "Musicians from", None),
        ("Musicians from Dublin", "Musicians from", None),
        ("Musicians from London", "Musicians from", None),
        ("Musicians from Paris", "Musicians from", None),
        ("Composers from Oxford", "Composers from", None),
        ("Musicians from Douglas", "Musicians from", None),
        ("Musicians from Ramsey", "Musicians from", None),
        ("Musicians from Ramsey Island", "Musicians from", "ramsey island"),
        ("Musicians from Chiswick", "Musicians from", None),
        ("Musicians from Peel", "Musicians from", None),
        ("Songs about China", "Songs about", None),
        ("Songs about France", "Songs about", None),
        ("Songs about kings", "Songs about", None),
        ("Songs about prison", "Songs about", None),
        ("Music of China", "Music of", None),
        ("Music of France", "Music of", None),
        ("Music of Gibraltar", "Music of", None),
        ("Music of New England", "Music of", None),
        ("Albums recorded in France", "Albums recorded in", None),
        ("Music of the United States", "Music of", None),
        ("Music of Africa", "Music of", None),
        ("Musical groups from the Highlands", "Musical groups from", None),
    )
    bad = []
    for category, prefix, expected in expectations:
        resolved = resolve_category(atlas, category, prefix, names, keys)
        got = fold(resolved["island"]["name"]) if resolved else None
        if expected is None:
            ok = got is None
        else:
            ok = got is not None and expected in got
        if not ok:
            bad.append((category, expected, got))
    if bad:
        for category, expected, got in bad:
            print(f"RESOLVE FAIL {category!r} expected {expected!r} got {got!r}", flush=True)
        raise SystemExit(1)
    print(f"resolution checks passed ({len(expectations)})", flush=True)


def load_resume(seen: set[tuple[str, str]]) -> tuple[list[dict], Counter]:
    partial = load_json(PARTIAL, {})
    rows = []
    counts: Counter = Counter()
    if partial.get("stage") == "done":
        return rows, counts
    for item in partial.get("rows") or []:
        if item.get("status") != "accepted":
            continue
        island_id = item.get("island_id") or ""
        title = item.get("title") or ""
        if not island_id or not title:
            continue
        rows.append(item)
        seen.add((island_id, fold(title)))
        counts[island_id] += 1
    return rows, counts


def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    atlas = Atlas()
    names = {fold(island["name"]) for island in atlas.islands if island.get("name")}
    keys = set(atlas.by_key)
    print(f"atlas islands {len(atlas.islands)}", flush=True)
    assert_resolution(atlas, names, keys)
    if os.environ.get("MUSIC_WIKI_CHECK_ONLY") == "1":
        print("check only, no harvest", flush=True)
        return

    seen = set(existing_music_keys())
    print(f"existing music keys {len(seen)}", flush=True)
    rows, counts = load_resume(seen)
    if rows:
        print(f"resuming with {len(rows)} partial rows", flush=True)

    matched: list[dict] = []
    seen_cats: set[str] = set()
    for prefix in PREFIXES:
        try:
            found = list_prefix(prefix, atlas, names, keys)
        except Exception as exc:
            FAILURES.append(f"{prefix}: {exc}")
            EMPTY_PREFIXES.append(prefix)
            print(f"prefix failed {prefix}: {exc}", flush=True)
            continue
        for cat in found:
            token = fold(cat["name"])
            if token in seen_cats:
                continue
            seen_cats.add(token)
            matched.append(cat)
        save_partial(rows, f"listed:{prefix}")
    print(f"matched categories {len(matched)}", flush=True)
    for cat in matched:
        print(f"  CAT\t{cat['island']['name']}\t{cat['name']}", flush=True)

    harvest(matched, seen, rows, counts)
    write_output(rows)
    save_partial(rows, "done")
    report(rows)


if __name__ == "__main__":
    main()
