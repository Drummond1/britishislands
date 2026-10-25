#!/usr/bin/env python3
"""Harvest artwork rows from English Wikipedia and Wikimedia Commons categories.

This is a category walk, separate from Wikidata SPARQL and museum APIs.
It writes data/interest/candidates/artwork-commons.json and does not publish.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import sys
import time
import urllib.parse
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from artwork_harvest_common import (  # noqa: E402
    artwork_row,
    existing_artwork_keys,
    match_island_phrase,
    phrase_in_text,
)
from ingest_sources import name_key  # noqa: E402
from interest_categories import (  # noqa: E402
    CLOSED_IMAGE_LICENCE,
    OPEN_IMAGE_LICENCE,
    Atlas,
    fold,
    http_json,
    load_json,
    save_json,
    utc_now,
)

WIKI_API = "https://en.wikipedia.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "IslesOfBritain/0.1 (https://www.findmyisland.com)"
CACHE = ROOT / "data" / "cache_artwork_commons"
PARTIAL = CACHE / "_partial_rows.json"
OUT = ROOT / "data" / "interest" / "candidates" / "artwork-commons.json"

PREFIXES = (
    "Paintings of",
    "Watercolor paintings of",
    "Watercolours of",
    "Drawings of",
    "Etchings of",
    "Prints of",
    "Sculptures of",
    "Sculptures in",
    "Art of",
)

WIKI_PER_ISLAND = 80
COMMONS_PER_ISLAND = 40
TOTAL_PER_ISLAND = 80
PAGES_PER_CATEGORY = 50
FILES_PER_CATEGORY = 40
EXTRACT_BATCH = 20
SLEEP_SECONDS = 1.0

NATION_PHRASES = {
    "great britain",
    "britain",
    "ireland",
    "england",
    "scotland",
    "wales",
    "the united kingdom",
    "united kingdom",
    "uk",
    "northern ireland",
    "republic of ireland",
    "great britain and ireland",
    "british isles",
}

ART_WORDS = re.compile(
    r"\b(paintings?|watercolours?|watercolors?|drawings?|etchings?|engravings?|"
    r"prints?|sculptures?|sculpted|statues?|busts?|murals?|lithographs?|"
    r"woodcuts?|pastels?|sketches?|artworks?|oil on canvas|oil on panel|"
    r"oil on board|tempera|gouache|fresco(?:es)?|triptychs?|altarpieces?|"
    r"portraits?|aquatints?|mezzotints?|wood engravings?|works? of art)\b",
    re.I,
)
_PLACE_ADJECTIVE = (
    r"(?:(?:small|large|tiny|remote|inhabited|uninhabited|scottish|irish|welsh|"
    r"english|british|offshore|tidal|inner|outer|largest|smallest|northernmost|"
    r"southernmost|westernmost|easternmost|main|principal|rocky|flat|volcanic|"
    r"coastal|populated|unpopulated|former|historic|medieval|ruined|ancient|"
    r"low-lying|now-uninhabited)\s+){0,6}"
)
PLACE_ARTICLE = re.compile(
    r"\b(?:is|was)\s+(?:a|an|the)\s+" + _PLACE_ADJECTIVE
    + r"(island|isle|islet|village|town|city|hamlet|parish|civil parish|loch|"
    r"lake|bay|mountain|hill|peninsula|archipelago|settlement|district|"
    r"county|headland|promontory|strait|sound|harbour|harbor|beach|castle|"
    r"church|abbey|cathedral|monastery|priory|lighthouse|munro|peak|river|"
    r"council area|community|suburb|borough|ward|channel)\b"
    r"|\b(?:is|was)\s+one of the\s+(?:(?:small|large|inner|outer|main|scottish|"
    r"irish|welsh|english|british|inhabited|uninhabited)\s+){0,4}(?:islands|isles)\b",
    re.I,
)
_PERSON_ADJECTIVE = (
    r"(?:(?:scottish|irish|welsh|english|british|american|french|dutch|italian|"
    r"german|spanish|flemish|norwegian|swedish|danish|russian|canadian|"
    r"australian|famous|noted|leading|prominent|celebrated|well-known|"
    r"contemporary|modern|romantic|victorian|landscape|portrait|marine|"
    r"watercolour|watercolor|nineteenth-century|eighteenth-century|"
    r"twentieth-century|seventeenth-century)\s+){0,8}"
)
BIO_ARTICLE = re.compile(
    r"\b(?:is|was)\s+an?\s+" + _PERSON_ADJECTIVE
    + r"(painter|artist|sculptor|printmaker|illustrator|photographer|engraver|"
    r"watercolourist|watercolorist|draughtsman|draftsman|poet|novelist|"
    r"writer|composer|musician)\b",
    re.I,
)
_WORK_ADJECTIVE = (
    r"(?:(?:\d{3,4}|british|irish|scottish|welsh|english|american|french|german|"
    r"italian|silent|short|feature|independent|romantic|comic|animated|"
    r"documentary|television|tv|debut|studio|folk|traditional)\s+){0,6}"
)
OTHER_WORK = re.compile(
    r"\b(?:is|was)\s+an?\s+" + _WORK_ADJECTIVE
    + r"(film|movie|album|song|novel|book|poem|play|television series|"
    r"tv series|video game|opera|musical|documentary|single)\b",
    re.I,
)
DISAMBIGUATION = re.compile(r"\b(?:may|can|could)\s+refer to\b", re.I)
PERSON_ONLY = re.compile(
    r"\b(?:sir|dame|lord|lady)\s+[A-Z]|"
    r"(?:^|\s)[A-Z]\.(?:\s*[A-Z]\.)*\s+[A-Z]|"
    r"\b(?:van|von)\s+[A-Z]",
)
ISLAND_WORD = re.compile(
    r"\b(isle|island|ynys|eilean|inis|inish|oile[aá]n)\b",
    re.I,
)
CAMERA_DUMP = re.compile(r"^(?:IMG|DSC|DSCN|DSCF)[_\-\s]?\d", re.I)
TRAILING_REGION = re.compile(
    r",\s*(Scotland|England|Wales|Ireland|Northern Ireland|United Kingdom|"
    r"UK|Great Britain|the Hebrides|Hebrides|Inner Hebrides|Outer Hebrides)\s*$",
    re.I,
)

STATS = {"http": 0, "cache": 0, "fail": 0}
ATTEMPTED: set[str] = set()
EMPTY_PREFIXES: list[str] = []
FAILURES: list[str] = []


def cache_path(url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
    host = "commons" if "commons.wikimedia.org" in url else "wiki"
    kind = "query"
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    if query.get("list"):
        kind = query["list"][0]
    elif query.get("prop"):
        kind = query["prop"][0].split("|")[0]
    return CACHE / f"{host}_{kind}_{digest}.json"


def api_url(endpoint: str, params: dict) -> str:
    encoded = urllib.parse.urlencode(params, doseq=True, safe="|")
    return endpoint + "?" + encoded


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
        payload = {"_error": f"{type(exc).__name__}: {exc}", "_url": url}
    if not isinstance(payload, dict):
        payload = {"_error": "response was not a JSON object", "_url": url}
    if payload.get("error") and not payload.get("_error"):
        info = payload["error"]
        text = info.get("info") if isinstance(info, dict) else str(info)
        payload = {"_error": str(text)[:500], "_url": url, "error": info}
    if payload.get("_error"):
        STATS["fail"] += 1
    save_json(path, payload)
    time.sleep(SLEEP_SECONDS)
    if STATS["http"] % 25 == 0:
        print(
            f"http {STATS['http']} cache {STATS['cache']} fail {STATS['fail']}",
            flush=True,
        )
    return payload


def paginate(endpoint: str, params: dict):
    base = dict(params)
    seen_tokens: set[str] = set()
    current = dict(base)
    pages = 0
    while pages < 2500:
        pages += 1
        payload = fetch(api_url(endpoint, current))
        if payload.get("_error"):
            FAILURES.append(f"{endpoint} {base.get('acprefix') or base.get('srsearch') or base.get('cmtitle')}: {payload['_error'][:180]}")
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


def category_items(payload: dict, kind: str):
    query = payload.get("query") or {}
    if kind == "allcategories":
        for item in query.get("allcategories") or []:
            name = item.get("*") or item.get("category") or ""
            if name:
                yield name, item.get("pages"), item.get("files")
        return
    for item in query.get("search") or []:
        title = item.get("title") or ""
        if title.startswith("Category:"):
            title = title[len("Category:") :]
        if title:
            yield title, None, None


def plain(value: str) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"<[^>]*>", " ", text)
    text = re.sub(r"<[^>]*$", " ", text)
    text = re.sub(r"\{\{[^{}]*\}\}", " ", text)
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.\w+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def phrase_variants(raw: str) -> list[str]:
    raw = re.sub(r"\s+", " ", raw or "").strip(" ,.;:-–—")
    if not raw:
        return []
    seeds = [raw, re.sub(r"\s*\([^)]*\)", " ", raw)]
    expanded: list[str] = []
    for seed in seeds:
        seed = re.sub(r"\s+", " ", seed).strip(" ,.;:-–—")
        if not seed:
            continue
        expanded.append(seed)
        expanded.append(re.split(r"\s+by\s+", seed, maxsplit=1, flags=re.I)[0])
        expanded.append(TRAILING_REGION.sub("", seed))
    out: list[str] = []
    seen: set[str] = set()
    for seed in expanded:
        seed = re.sub(r"\s+", " ", seed).strip(" ,.;:-–—")
        options = [seed]
        bare = re.sub(r"^the\s+", "", seed, flags=re.I).strip()
        if bare != seed:
            options.append(bare)
        for item in options:
            item = re.sub(r"\s+", " ", item).strip(" ,.;:-–—")
            key = fold(item)
            if item and key not in seen:
                seen.add(key)
                out.append(item)
            saint = re.sub(r"^st\.?\s+", "Saint ", item, count=1, flags=re.I)
            if saint != item:
                key = fold(saint)
                if key not in seen:
                    seen.add(key)
                    out.append(saint)
    return out


def place_phrase(category: str) -> str:
    name = category[9:] if category.startswith("Category:") else category
    name = name.strip()
    folded = fold(name)
    if folded.endswith(" in art"):
        return name[: -len(" in art")].strip()
    for prefix in sorted(PREFIXES, key=len, reverse=True):
        head = fold(prefix)
        if folded == head:
            return ""
        if folded.startswith(head + " "):
            return name[len(prefix) :].strip()
    return ""


def is_nation(phrase: str) -> bool:
    return fold(phrase) in NATION_PHRASES


def is_person_only(phrase: str) -> bool:
    if ISLAND_WORD.search(phrase or ""):
        return False
    return bool(PERSON_ONLY.search(phrase or ""))


def could_be_island(phrase: str, names: set[str], keys: set[str]) -> bool:
    if fold(phrase) in names:
        return True
    key = name_key(phrase)
    return bool(key) and key in keys


def _bare_island_name(name: str) -> str:
    bare = re.sub(r"\s*\([^)]*\)", " ", name or "")
    return re.sub(r"\s+", " ", bare).strip()


def _phrase_forms(phrase: str) -> list[str]:
    forms = [phrase]
    saint = re.sub(r"^saint\s+", "St ", phrase, count=1, flags=re.I)
    short = re.sub(r"^st\.?\s+", "Saint ", phrase, count=1, flags=re.I)
    for form in (saint, short):
        if form not in forms:
            forms.append(form)
    return forms


def _proper_phrase(category: str, phrase: str) -> bool:
    """The place words are capitalised in the category title, not 'dogs' or 'hats'."""
    small = {"of", "the", "and", "de", "y", "an", "na", "nam", "nan", "in"}
    for form in _phrase_forms(phrase):
        match = re.search(r"\b" + re.escape(form) + r"\b", category, re.I)
        if not match:
            continue
        words = [word for word in match.group(0).split() if word[:1].isalpha()]
        if not words or not any(word[:1].isupper() for word in words):
            continue
        if all(word[:1].isupper() or word.casefold() in small for word in words):
            return True
    return False


def _name_in_text(name: str, text: str) -> bool:
    for form in _phrase_forms(name):
        if phrase_in_text(form, text):
            return True
    return False


# Single names that are biblical or saintly subjects first, and islands only
# when the category itself says so.
FAMOUS_SMALL = {
    "staffa",
    "ailsa craig",
    "bass rock",
    "saint michael's mount",
    "st michael's mount",
    "burgh island",
    "inchcolm",
    "fidra",
    "calve island",
    "puffin island",
}
# One-word English nouns that must not inherit an "Isle of …" atlas name.
COMMON_SHORT = {
    "grain",
    "corn",
    "wheat",
    "barley",
    "oats",
    "rice",
    "salt",
    "gold",
    "iron",
    "stone",
    "sand",
    "rock",
    "water",
    "fire",
    "wind",
    "wood",
    "glass",
    "wool",
    "silk",
    "bread",
    "wine",
    "fish",
    "fruit",
    "flower",
    "tree",
    "grass",
    "seed",
    "field",
    "farm",
    "mill",
    "bridge",
    "church",
    "castle",
    "tower",
    "house",
    "hall",
    "park",
    "green",
    "black",
    "white",
    "north",
    "south",
    "east",
    "west",
}
PERSON_HOMONYMS = {
    "samson",
    "adam",
    "eve",
    "judith",
    "moses",
    "delilah",
    "goliath",
    "abraham",
    "noah",
}
ADMIN_ASIDE = re.compile(
    r"\((?:italy|france|germany|spain|hungary|poland|austria|belgium|"
    r"netherlands|sweden|norway|denmark|finland|russia|ukraine|greece|"
    r"portugal|switzerland|usa|united states|canada|australia|new zealand|"
    r"india|china|japan|department|province|county|city|town|village|"
    r"mythology|goddess|deity|saint|bible|religion|astronomy|"
    r"cultivars?|plants?|flowers?|genus|species|ship)\)",
    re.I,
)


def _accents_agree(phrase: str, island_name: str) -> bool:
    """Pápa is not Papa. Shared folding would otherwise collapse them."""
    skip = {"of", "the", "and", "isle", "island", "ynys", "eilean", "inis", "inish"}
    island_tokens = _bare_island_name(island_name).split()
    for token in phrase.split():
        if token.casefold() in skip:
            continue
        for other in island_tokens:
            if fold(token) != fold(other):
                continue
            if token.casefold() != other.casefold():
                return False
    return True


def category_names_island(category: str, phrase: str, island: dict) -> bool:
    """Reject name-key collisions such as 'Paintings of dogs' → Dogs Island.

    match_island_phrase strips the word 'island', so a common noun or a
    foreign town can hit a skerry. Keep the hit only when the category
    actually names that island.
    """
    if (island.get("area") or 0) < 0.05:
        return False
    if ADMIN_ASIDE.search(category or ""):
        return False
    # "Long Island in art" is the New York subject, not a small atlas islet.
    if fold(phrase) == "long island" or fold(_bare_island_name(island.get("name") or "")) == "long island":
        if not re.search(
            r"\b(scotland|ireland|kerry|donegal|cork|mayo|galway|highland|hebrides)\b",
            category,
            re.I,
        ):
            return False
    if not _accents_agree(phrase, island.get("name") or ""):
        return False
    bare = _bare_island_name(island.get("name") or "")
    if not bare:
        return False
    if fold(phrase) in PERSON_HOMONYMS and not re.search(
        r"\b(isle|island|scilly|orkney|hebrides|shetland)\b",
        category,
        re.I,
    ):
        return False
    # "Saint Thomas" is not the skerry Saint Thomas Island. "St Kilda" is.
    # Art titled Saint Thomas Island is the Caribbean island, not the skerry.
    if fold(bare) in {"saint thomas island", "st thomas island"}:
        return False
    if re.match(r"^(?:saint|st\.?)\s+\S+$", phrase, re.I) and fold(phrase) != fold(bare):
        return False
    if len(bare.split()) >= 2 and (
        _name_in_text(bare, category) or _name_in_text(island["name"], category)
    ):
        return True
    proper = _proper_phrase(category, phrase)
    if not proper:
        return False
    if fold(phrase) == fold(bare) or fold(phrase) == fold(island.get("name") or ""):
        return True
    if {fold(form) for form in _phrase_forms(phrase)} & {fold(form) for form in _phrase_forms(bare)}:
        return True
    # "Isle of Harris" names the atlas island Harris.
    if (
        len(bare.split()) == 1
        and phrase_in_text(bare, phrase)
        and re.search(r"\b(isle|island|ynys|eilean|inis|inish)\b", phrase, re.I)
    ):
        return True
    qualified = {
        fold(item)
        for item in (
            f"isle of {phrase}",
            f"island of {phrase}",
            f"ynys {phrase}",
            f"eilean {phrase}",
            f"inis {phrase}",
            f"inish {phrase}",
        )
    }
    if fold(bare) in qualified:
        # "Skye" names the Isle of Skye. "Grain" does not name the Isle of Grain
        # when the category is "Grain in art".
        if fold(phrase) in COMMON_SHORT:
            return False
        return True
    if len(phrase.split()) >= 2 and fold(bare) in {
        fold(f"{phrase} Island"),
        fold(f"{phrase} Isle"),
    }:
        return True
    # A substantial island whose atlas name is "{Name} Island" (Achill Island).
    if (
        len(phrase.split()) == 1
        and fold(bare) == fold(f"{phrase} Island")
        and (island.get("area") or 0) >= 5
    ):
        return True
    return False


def resolve_island(atlas: Atlas, category: str, names: set[str], keys: set[str]):
    raw = place_phrase(category)
    if not raw:
        return None
    saw_blocked = False
    for phrase in phrase_variants(raw):
        if is_nation(phrase) or is_person_only(phrase):
            saw_blocked = True
            continue
        if not could_be_island(phrase, names, keys):
            continue
        island = match_island_phrase(atlas, phrase)
        if not island:
            continue
        if not _name_in_text(phrase, category) and not _name_in_text(island["name"], category):
            continue
        if not category_names_island(category, phrase, island):
            continue
        return phrase, island
    if saw_blocked and not any(
        could_be_island(phrase, names, keys)
        for phrase in phrase_variants(raw)
        if not is_nation(phrase) and not is_person_only(phrase)
    ):
        return None
    return None


def list_prefix(endpoint: str, source: str, prefix: str, atlas, names, keys) -> list[dict]:
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
        "acprop": "size",
    }
    for payload in paginate(endpoint, params):
        if payload.get("_error"):
            errored = True
            break
        page_count = 0
        for name, pages, files in category_items(payload, "allcategories"):
            page_count += 1
            found += 1
            if source == "wikipedia" and pages == 0:
                continue
            if source == "commons" and files == 0:
                continue
            token = fold(name)
            if token in seen:
                continue
            resolved = resolve_island(atlas, name, names, keys)
            if not resolved:
                continue
            phrase, island = resolved
            seen.add(token)
            matched.append(
                {
                    "name": name,
                    "phrase": phrase,
                    "island": island,
                    "source": source,
                    "pages": pages,
                    "files": files,
                }
            )
        print(
            f"{source} {prefix!r} +{page_count} scanned {found} matched {len(matched)}",
            flush=True,
        )
    if found == 0 and not errored:
        EMPTY_PREFIXES.append(f"{source}: {prefix}")
        print(f"{source} prefix returned nothing: {prefix}", flush=True)
    return matched


def list_in_art(endpoint: str, source: str, atlas, names, keys) -> list[dict]:
    matched: list[dict] = []
    seen: set[str] = set()
    for limit in ("500", "50"):
        found = 0
        errored = False
        refused = False
        params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": 'intitle:"in art"',
            "srnamespace": "14",
            "srlimit": limit,
            "srprop": "size",
        }
        for payload in paginate(endpoint, params):
            if payload.get("_error"):
                info = str(payload.get("_error") or "")
                if limit == "500" and found == 0:
                    print(f"{source} search limit 500 failed ({info[:120]}), retrying at 50", flush=True)
                    refused = True
                else:
                    errored = True
                break
            page_count = 0
            for name, _pages, _files in category_items(payload, "search"):
                page_count += 1
                if not fold(name).endswith(" in art"):
                    continue
                found += 1
                token = fold(name)
                if token in seen:
                    continue
                resolved = resolve_island(atlas, name, names, keys)
                if not resolved:
                    continue
                phrase, island = resolved
                seen.add(token)
                matched.append(
                    {
                        "name": name,
                        "phrase": phrase,
                        "island": island,
                        "source": source,
                        "pages": None,
                        "files": None,
                    }
                )
            print(
                f"{source} 'in art' +{page_count} kept {found} matched {len(matched)}",
                flush=True,
            )
        if refused:
            continue
        if found == 0 and not errored:
            EMPTY_PREFIXES.append(f"{source}: in art")
            print(f"{source} suffix returned nothing: in art", flush=True)
        return matched
    return matched


def art_name_queries(atlas: Atlas) -> list[str]:
    """One category query per island. 'OR' batches return the wrong categories."""
    from artwork_harvest_common import AMBIGUOUS_KEYS, NATION_PHRASES

    queries: list[str] = []
    seen: set[str] = set()
    for island in atlas.islands:
        area = island.get("area") or 0
        if area < 0.05 or area > 8000:
            continue
        bare = _bare_island_name(island.get("name") or "")
        if not bare or fold(bare) in NATION_PHRASES:
            continue
        # The broad search already walks the popular categories. Named searches
        # cover islands large enough to have an art category, plus a few small
        # subjects (Staffa, Bass Rock) that painters actually went to.
        if area < 1 and fold(bare) not in FAMOUS_SMALL:
            continue
        key = name_key(bare)
        qualified = bool(ISLAND_WORD.search(bare))
        query = bare if qualified or key not in AMBIGUOUS_KEYS else f"Isle of {bare}"
        query = query.replace('"', "").strip()
        if len(query) < 4 or fold(query) in seen:
            continue
        seen.add(fold(query))
        queries.append(query)
    queries.sort(key=len, reverse=True)
    return queries


def list_in_art_named(endpoint: str, source: str, atlas: Atlas, names: set[str], keys: set[str]) -> list[dict]:
    """One search per island name. The broad 'in art' search stops at 10,000 hits."""
    queries = art_name_queries(atlas)
    matched: list[dict] = []
    seen: set[str] = set()
    print(f"{source} named 'in art' queries {len(queries)}", flush=True)
    for index, query in enumerate(queries, start=1):
        params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": f'intitle:"{query}" intitle:"in art"',
            "srnamespace": "14",
            "srlimit": "20",
            "srprop": "size",
        }
        for payload in paginate(endpoint, params):
            if payload.get("_error"):
                break
            for name, _pages, _files in category_items(payload, "search"):
                if not fold(name).endswith(" in art"):
                    continue
                token = fold(name)
                if token in seen:
                    continue
                resolved = resolve_island(atlas, name, names, keys)
                if not resolved:
                    continue
                phrase, island = resolved
                seen.add(token)
                matched.append(
                    {
                        "name": name,
                        "phrase": phrase,
                        "island": island,
                        "source": source,
                        "pages": None,
                        "files": None,
                    }
                )
        if index % 25 == 0 or index == len(queries):
            print(
                f"{source} named 'in art' {index}/{len(queries)} matched {len(matched)}",
                flush=True,
            )
    return matched


def member_titles(endpoint: str, category: str, cmtype: str, cap: int) -> list[str]:
    titles: list[str] = []
    params = {
        "action": "query",
        "format": "json",
        "list": "categorymembers",
        "cmtitle": f"Category:{category}",
        "cmtype": cmtype,
        "cmlimit": str(min(cap, 50)),
    }
    for payload in paginate(endpoint, params):
        if payload.get("_error"):
            break
        for item in (payload.get("query") or {}).get("categorymembers") or []:
            title = item.get("title") or ""
            if title:
                titles.append(title)
            if len(titles) >= cap:
                return titles[:cap]
        if len(titles) >= cap or not payload.get("continue"):
            break
    return titles[:cap]


def skip_page_title(title: str) -> bool:
    low = title.casefold()
    if "list of" in low or "disambiguation" in low:
        return True
    if "category:" in low or "template:" in low:
        return True
    return False


def wiki_link(title: str) -> str:
    slug = urllib.parse.quote(title.replace(" ", "_"), safe="/:@!$&'()*+,;=")
    return "https://en.wikipedia.org/wiki/" + slug


def commons_link(file_title: str) -> str:
    slug = urllib.parse.quote(file_title.replace(" ", "_"), safe="/:@!$&'()*+,;=")
    return "https://commons.wikimedia.org/wiki/" + slug


def sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    protected = re.sub(r"\b([A-Z])\.", r"\1§", text)
    protected = re.sub(
        r"\b(St|Mr|Mrs|Ms|Dr|No|Op|Jr|Sr)\.",
        lambda match: match.group(0).replace(".", "§"),
        protected,
    )
    parts = re.split(r"(?<=[.!?])\s+", protected)
    return [part.replace("§", ".").strip() for part in parts if part.strip()]


def one_sentence(text: str) -> str:
    for sentence in sentences(text)[:4]:
        if ART_WORDS.search(sentence):
            return sentence[:450].rstrip()
    found = sentences(text)
    if found:
        return found[0][:450].rstrip()
    return ""


def defining_clause(extract: str) -> str:
    """The first 'is a …' span. Stop before a comma or 'which is an island'."""
    first = sentences(extract)
    head = first[0] if first else (extract or "")[:400]
    match = re.search(r"\b(?:is|was)\s+(?:an?|the|one of the)\b[^.]{0,90}", head, re.I)
    clause = match.group(0) if match else head[:180]
    clause = re.split(r",|\b(?:which|where|who)\b", clause, maxsplit=1, flags=re.I)[0]
    return clause.strip()


def artwork_article(title: str, extract: str) -> bool:
    if not extract or skip_page_title(title):
        return False
    clause = defining_clause(extract)
    if DISAMBIGUATION.search((extract or "")[:350]):
        return False
    if PLACE_ARTICLE.search(clause):
        return False
    if BIO_ARTICLE.search(clause):
        return False
    if OTHER_WORK.search(clause):
        return False
    if not (ART_WORDS.search(title) or ART_WORDS.search(extract[:1200])):
        return False
    bare = re.sub(r"\s*\([^)]*\)\s*$", "", title).strip()
    if phrase_in_text(bare, extract) or phrase_in_text(title, extract):
        return True
    return fold(bare) in fold(extract)


def fetch_extracts(titles: list[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for start in range(0, len(titles), EXTRACT_BATCH):
        batch = titles[start : start + EXTRACT_BATCH]
        params = {
            "action": "query",
            "format": "json",
            "redirects": "1",
            "prop": "extracts",
            "exintro": "1",
            "explaintext": "1",
            "exlimit": "20",
            "titles": "|".join(batch),
        }
        payload = fetch(api_url(WIKI_API, params))
        if payload.get("_error"):
            continue
        query = payload.get("query") or {}
        redirect_to: dict[str, str] = {}
        for item in query.get("redirects") or []:
            source = item.get("from") or ""
            target = item.get("to") or ""
            if source and target:
                redirect_to[source] = target
        pages = query.get("pages") or {}
        page_list = pages.values() if isinstance(pages, dict) else pages
        by_title: dict[str, str] = {}
        for page in page_list:
            page_title = page.get("title") or ""
            if page.get("missing") is not None or not page_title:
                continue
            by_title[page_title] = page.get("extract") or ""
        for title in batch:
            canonical = redirect_to.get(title, title)
            extract = by_title.get(canonical) or by_title.get(title) or ""
            if extract:
                found[canonical] = extract
    return found


def meta_value(meta: dict, key: str) -> str:
    raw = meta.get(key) or {}
    if isinstance(raw, dict):
        return str(raw.get("value") or "")
    return str(raw or "")


def licence_ok(short: str, extra: str) -> bool:
    short = plain(short)
    if not short or not OPEN_IMAGE_LICENCE.search(short):
        return False
    blob = f"{short} {plain(extra)}"
    return CLOSED_IMAGE_LICENCE.search(blob) is None


def readable_object_name(object_name: str) -> str:
    """Commons sometimes dumps every language into ObjectName."""
    raw = object_name or ""
    english = re.search(r'label QS:Len,"([^"]+)"', raw)
    if not english:
        english = re.search(r'title QS:P1476,en:"([^"]+)"', raw)
    if english:
        return plain(english.group(1))
    text = plain(raw).replace("_", " ")
    if "label QS:" in text or "title QS:" in text or "QS:P1476" in text:
        return ""
    return text


def human_title(file_title: str, object_name: str) -> str | None:
    base = file_title[5:] if file_title.startswith("File:") else file_title
    base = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", base).replace("_", " ")
    base = re.sub(r"\s+", " ", base).strip()
    obj = readable_object_name(object_name)
    obj = re.sub(r"^File:\s*", "", obj)
    obj = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", obj)
    obj = re.sub(r"\s+", " ", obj).strip()
    if obj and not CAMERA_DUMP.match(obj) and fold(obj) != fold(base) and len(obj) > 2:
        chosen = obj
    else:
        chosen = base
    if not chosen or CAMERA_DUMP.match(chosen):
        return None
    if re.fullmatch(r"[\d _\-]+", chosen):
        return None
    return chosen[:180]


def fetch_files(file_titles: list[str]) -> list[dict]:
    records: list[dict] = []
    start = 0
    while start < len(file_titles):
        batch: list[str] = []
        budget = 0
        while start < len(file_titles) and len(batch) < 8 and budget < 1800:
            title = file_titles[start]
            budget += len(urllib.parse.quote(title))
            if batch and budget > 1800:
                break
            batch.append(title)
            start += 1
        params = {
            "action": "query",
            "format": "json",
            "prop": "imageinfo",
            "iiprop": "url|extmetadata|mime",
            "iiurlwidth": "960",
            "titles": "|".join(batch),
        }
        payload = fetch(api_url(COMMONS_API, params))
        if payload.get("_error"):
            continue
        pages = (payload.get("query") or {}).get("pages") or {}
        page_list = pages.values() if isinstance(pages, dict) else pages
        for page in page_list:
            title = page.get("title") or ""
            info = (page.get("imageinfo") or [{}])[0]
            if not title or not info:
                continue
            records.append({"title": title, "info": info})
    return records


def island_room(counts: dict, island_id: str, source: str) -> bool:
    if counts["total"][island_id] >= TOTAL_PER_ISLAND:
        return False
    if source == "commons" and counts["commons"][island_id] >= COMMONS_PER_ISLAND:
        return False
    if source == "wikipedia" and counts["wiki"][island_id] >= WIKI_PER_ISLAND:
        return False
    return True


def take_row(rows: list[dict], counts: dict, source: str, built: dict | None) -> None:
    if not built:
        return
    island_id = built["island_id"]
    if not island_room(counts, island_id, source):
        return
    rows.append(built)
    counts["total"][island_id] += 1
    counts[source][island_id] += 1


def harvest_wikipedia(categories: list[dict], seen: set, rows: list[dict], counts: dict) -> None:
    for index, cat in enumerate(categories, start=1):
        island = cat["island"]
        if not island_room(counts, island["id"], "wikipedia"):
            continue
        if not _name_in_text(cat["phrase"], cat["name"]) and not _name_in_text(island["name"], cat["name"]):
            continue
        try:
            titles = [
                title
                for title in member_titles(WIKI_API, cat["name"], "page", PAGES_PER_CATEGORY)
                if not skip_page_title(title)
            ]
            extracts = fetch_extracts(titles)
            added = 0
            for title, extract in extracts.items():
                if not island_room(counts, island["id"], "wikipedia"):
                    break
                if not artwork_article(title, extract):
                    continue
                summary = one_sentence(extract) or (
                    f"{title} is catalogued in the English Wikipedia category {cat['name']}."
                )
                built = artwork_row(
                    island=island,
                    title=title,
                    source_url=wiki_link(title),
                    source_title=title,
                    licence="CC BY-SA 4.0",
                    evidence=f'English Wikipedia category "{cat["name"]}".',
                    summary=summary,
                    external_id=title.replace(" ", "_"),
                    seen=seen,
                )
                before = len(rows)
                take_row(rows, counts, "wikipedia", built)
                added += len(rows) - before
            print(
                f"wiki [{index}/{len(categories)}] {cat['name']} -> {island['name']} +{added}",
                flush=True,
            )
        except Exception as exc:
            FAILURES.append(f"wikipedia {cat['name']}: {exc}")
            print(f"wiki category failed {cat['name']}: {exc}", flush=True)
        if index % 10 == 0:
            save_partial(rows, "wikipedia")


def harvest_commons(categories: list[dict], seen: set, rows: list[dict], counts: dict) -> None:
    for index, cat in enumerate(categories, start=1):
        island = cat["island"]
        if not island_room(counts, island["id"], "commons"):
            continue
        if not _name_in_text(cat["phrase"], cat["name"]) and not _name_in_text(island["name"], cat["name"]):
            continue
        try:
            files = member_titles(COMMONS_API, cat["name"], "file", FILES_PER_CATEGORY)
            added = 0
            for record in fetch_files(files):
                if not island_room(counts, island["id"], "commons"):
                    break
                info = record["info"]
                mime = info.get("mime") or ""
                if mime and not mime.startswith("image/"):
                    continue
                meta = info.get("extmetadata") or {}
                short = plain(meta_value(meta, "LicenseShortName"))
                extra = " ".join(
                    meta_value(meta, key)
                    for key in ("UsageTerms", "License", "Restrictions")
                )
                if not licence_ok(short, extra):
                    continue
                title = human_title(record["title"], meta_value(meta, "ObjectName"))
                if not title:
                    continue
                page_url = info.get("descriptionurl") or commons_link(record["title"])
                thumb = info.get("thumburl") or ""
                artist = plain(meta_value(meta, "Artist"))
                credit = plain(meta_value(meta, "Credit"))
                attribution = (artist or credit or "Wikimedia Commons")[:300]
                licence_url = plain(meta_value(meta, "LicenseUrl"))
                open_image = None
                if thumb:
                    open_image = {
                        "thumbUrl": thumb,
                        "pageUrl": page_url,
                        "attribution": attribution,
                        "licence": short,
                        "licenceUrl": licence_url,
                    }
                built = artwork_row(
                    island=island,
                    title=title,
                    source_url=commons_link(record["title"]),
                    source_title=title,
                    licence=short,
                    evidence=f'Wikimedia Commons category "{cat["name"]}".',
                    summary=f"{title} is an artwork in the Wikimedia Commons category {cat['name']}.",
                    external_id=record["title"],
                    commons_file=record["title"],
                    open_image=open_image,
                    seen=seen,
                )
                before = len(rows)
                take_row(rows, counts, "commons", built)
                added += len(rows) - before
            print(
                f"commons [{index}/{len(categories)}] {cat['name']} -> {island['name']} +{added}",
                flush=True,
            )
        except Exception as exc:
            FAILURES.append(f"commons {cat['name']}: {exc}")
            print(f"commons category failed {cat['name']}: {exc}", flush=True)
        if index % 10 == 0:
            save_partial(rows, "commons")


def save_partial(rows: list[dict], stage: str) -> None:
    save_json(PARTIAL, {"stage": stage, "savedAt": utc_now(), "rows": rows})


def write_output(rows: list[dict]) -> None:
    save_json(
        OUT,
        {
            "slug": "artwork-commons",
            "generatedAt": utc_now(),
            "sources": ["wikipedia-categories", "wikimedia-commons"],
            "rows": rows,
        },
    )


def dedupe_categories(categories: list[dict]) -> list[dict]:
    kept: list[dict] = []
    seen: set[str] = set()
    for cat in categories:
        token = fold(cat["name"])
        if token in seen:
            continue
        seen.add(token)
        kept.append(cat)
    return kept


def seed_counts(rows: list[dict]) -> dict:
    counts = {"total": Counter(), "wikipedia": Counter(), "commons": Counter()}
    for item in rows:
        island_id = item.get("island_id") or ""
        if not island_id:
            continue
        counts["total"][island_id] += 1
        if "commons.wikimedia.org" in (item.get("source_url") or ""):
            counts["commons"][island_id] += 1
        else:
            counts["wikipedia"][island_id] += 1
    return counts


def report(rows: list[dict]) -> None:
    by_island: Counter = Counter()
    wiki = commons = 0
    for item in rows:
        by_island[item.get("island_name") or item.get("island_id") or "?"] += 1
        if "commons.wikimedia.org" in (item.get("source_url") or ""):
            commons += 1
        else:
            wiki += 1
    print("ACCEPTED", len(rows), flush=True)
    print("ISLANDS", len(by_island), flush=True)
    print("WIKIPEDIA", wiki, flush=True)
    print("COMMONS", commons, flush=True)
    print("TOP", flush=True)
    for name, count in by_island.most_common(15):
        print(f"  {count}\t{name}", flush=True)
    print("SAMPLES", flush=True)
    picked: list[dict] = []
    used: set[str] = set()
    for host in ("en.wikipedia.org", "commons.wikimedia.org"):
        for item in rows:
            if host not in (item.get("source_url") or ""):
                continue
            if item.get("island_id") in used:
                continue
            picked.append(item)
            used.add(item.get("island_id") or "")
            if len(picked) >= 8:
                break
        if len(picked) >= 8:
            break
    for item in rows:
        if len(picked) >= 8:
            break
        if item not in picked:
            picked.append(item)
    for item in picked:
        print(
            "  SAMPLE\t{island}\t{title}\t{url}\t{licence}".format(
                island=item.get("island_name") or "",
                title=item.get("title") or "",
                url=item.get("source_url") or "",
                licence=item.get("licence") or "",
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
    for line in FAILURES[:30]:
        print(f"  {line}", flush=True)
    print("OUTPUT", OUT, flush=True)
    print(
        f"http {STATS['http']} cache {STATS['cache']} fail {STATS['fail']}",
        flush=True,
    )


def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    atlas = Atlas()
    names = {fold(island["name"]) for island in atlas.islands}
    keys = set(atlas.by_key)
    print(f"atlas islands {len(atlas.islands)}", flush=True)
    partial = load_json(PARTIAL, {})
    rows = list(partial.get("rows") or [])
    seen = existing_artwork_keys()
    for item in rows:
        title = item.get("title") or ""
        island_id = item.get("island_id") or ""
        if island_id and title:
            seen.add((island_id, fold(title)))
    counts = seed_counts(rows)
    if rows:
        print(f"resuming with {len(rows)} partial rows", flush=True)

    wiki_matched: list[dict] = []
    commons_matched: list[dict] = []
    for prefix in PREFIXES:
        wiki_matched.extend(list_prefix(WIKI_API, "wikipedia", prefix, atlas, names, keys))
        save_partial(rows, "list-wikipedia")
    wiki_matched.extend(list_in_art(WIKI_API, "wikipedia", atlas, names, keys))
    wiki_matched = dedupe_categories(wiki_matched)
    print(f"wikipedia matched categories {len(wiki_matched)}", flush=True)

    for prefix in PREFIXES:
        commons_matched.extend(list_prefix(COMMONS_API, "commons", prefix, atlas, names, keys))
        save_partial(rows, "list-commons")
    commons_matched.extend(list_in_art(COMMONS_API, "commons", atlas, names, keys))
    commons_matched.extend(list_in_art_named(COMMONS_API, "commons", atlas, names, keys))
    commons_matched = dedupe_categories(commons_matched)
    print(f"commons matched categories {len(commons_matched)}", flush=True)

    # Prefer larger islands when several categories compete for request time.
    wiki_matched.sort(key=lambda cat: cat["island"].get("area") or 0, reverse=True)
    commons_matched.sort(key=lambda cat: cat["island"].get("area") or 0, reverse=True)

    harvest_wikipedia(wiki_matched, seen, rows, counts)
    save_partial(rows, "wikipedia-done")
    harvest_commons(commons_matched, seen, rows, counts)
    write_output(rows)
    save_partial(rows, "done")
    report(rows)


if __name__ == "__main__":
    main()
