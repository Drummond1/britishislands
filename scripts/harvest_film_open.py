#!/usr/bin/env python3
"""Harvest cited films and television works for the atlas film filter.

Writes data/interest/candidates/film-open.json and caches HTTP responses
under data/cache_film_open/. Does not publish the interest index and does
not edit islands.json.

A row is accepted only when an English Wikipedia lead names the work and
one atlas island as a place where it was filmed or set. Wikidata filming
and narrative locations are candidates, not proof on their own.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import subprocess
import sys
import time
import urllib.parse
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from artwork_harvest_common import (  # noqa: E402
    AMBIGUOUS_KEYS,
    NATION_PHRASES,
    existing_facet_keys,
    match_island_phrase,
    phrase_in_text,
)
from ingest_sources import name_key  # noqa: E402
from interest_categories import (  # noqa: E402
    WIKIDATA_ENDPOINT,
    Atlas,
    _atlas_qids,
    fold,
    http_json,
    load_json,
    row,
    save_json,
    utc_now,
    write_candidates,
)

CACHE = ROOT / "data" / "cache_film_open"
OUTPUT_SLUG = "film-open"
USER_AGENT = "isles-of-britain/0.1 (film-open; research)"
WIKI_API = "https://en.wikipedia.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
PLACE_CACHE = ROOT / "data" / "cache_wikidata_place_classes.json"
SLEEP = 1.1
CATEGORY_CAP = 400
MIN_AREA = 0.05
QID_MIN_AREA = 0.15

# Direct classes, plus the subclass walk. Feature films and miniseries are
# included when their type sits under film or television series.
CLASS_ROOTS = ("Q11424", "Q5398426", "Q506240")
DIRECT_CLASSES = ("Q11424", "Q24869", "Q5398426", "Q506240", "Q1259759", "Q24862")

BLOCKED_PLACE_QIDS = {
    "Q145",
    "Q21",
    "Q22",
    "Q25",
    "Q26",
    "Q27",
    "Q236",
    "Q22890",
}

CATEGORIES = (
    ("Films shot in Scotland", "filmed"),
    ("Films shot in Ireland", "filmed"),
    ("Films shot in Wales", "filmed"),
    ("Films shot in England", "filmed"),
    ("Films shot in Northern Ireland", "filmed"),
    ("Films set in Scotland", "set"),
    ("Films set in Ireland", "set"),
    ("Films set in Wales", "set"),
    ("Television series set in Scotland", "set"),
    ("Television series set in Ireland", "set"),
)

# Bare tokens that must not match inside a longer mainland name.
BARE_BLOCK_AFTER = {
    "mull": re.compile(r"\s+of\s+(kintyre|galloway)\b", re.I),
}

# These leftovers are only searched as "Isle of …" or as the atlas name
# when that name is already a qualified island form.
NO_BARE = set(AMBIGUOUS_KEYS) | {"calve"}

OVERSEAS_PHRASES = {
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
    "new jersey",
    "new york",
    "new england",
}

NOT_ATLAS = (
    "skellig michael",
    "great skellig",
    "little skellig",
    "sceilg mhichil",
    "summerisle",
)

FILMED_CUE = re.compile(
    r"\b(shot|filmed|filming|shooting|on location|principal photography|"
    r"exterior shots|exteriors|filming location|location shooting)\b",
    re.I,
)
SET_CUE = re.compile(
    r"\b(set in|set on|is set|was set|were set|setting|takes place|"
    r"take place|took place|taking place|story is set|stories are set)\b",
    re.I,
)
WORK_LEAD = re.compile(
    r"\b(film|television series|tv series|television programme|television program|"
    r"miniseries|mini-series|documentary|sitcom|soap opera|television film|"
    r"drama series|comedy series)\b",
    re.I,
)
OVERSEAS_SENTENCE = re.compile(
    r"\b(ontario|canada|australia|new zealand|california|united states|\busa\b|"
    r"south africa|nova scotia|michigan|florida|new york|chicago|toronto)\b",
    re.I,
)
HOME_SENTENCE = re.compile(
    r"\b(scotland|england|wales|ireland|orkney|shetland|hebrides|cornwall|"
    r"scilly|isle of man|channel islands|argyll|kerry|galway|mayo|donegal|"
    r"pembrokeshire|gwynedd|anglesey|highland|scottish|irish|welsh|english)\b",
    re.I,
)
ADDRESS = re.compile(
    r"\b\d{1,4}\s+[A-Za-z][A-Za-z'’.-]+\s+"
    r"(Street|Road|Lane|Avenue|Drive|Close|Crescent|Terrace|Way)\b"
)
OWNED = re.compile(r"\b(owned by|home owner|homeowner)\b", re.I)
BAD_IMAGE = re.compile(
    r"\.svg(?:$|\?)|\b(flag|coat of arms|coa|locator|location map|map of|"
    r"diagram|icon|pictogram)\b|\bmap\b",
    re.I,
)
DISAMBIG = re.compile(r"\bmay refer to\b", re.I)
ISLAND_PAGE = re.compile(r"\b(is|was)\s+an\s+island\b", re.I)

QUALIFIED_PREFIX = re.compile(
    r"\b(isle of|island of|ynys|eilean|inis|inish|oiléan|oilean)\b",
    re.I,
)


def log(message: str) -> None:
    print(message, flush=True)


def squash(text: str) -> str:
    text = fold(text).replace("’", "'").replace("`", "'")
    return re.sub(r"\s+", " ", text).strip()


def html_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html.unescape(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def norm_title(title: str) -> str:
    text = squash(title)
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def qid_of(value: str) -> str:
    return (value or "").rstrip("/").rsplit("/", 1)[-1]


def wiki_title_from_url(url: str) -> str:
    if "/wiki/" not in (url or ""):
        return ""
    title = urllib.parse.unquote(url.split("/wiki/", 1)[1]).replace("_", " ")
    return title.split("#", 1)[0].strip()


def commons_name(value: str) -> str:
    if not value:
        return ""
    name = value.strip()
    if name.startswith("http"):
        name = urllib.parse.unquote(name.rstrip("/").rsplit("/", 1)[-1])
    name = name.replace("_", " ").split("?", 1)[0].strip()
    if not name or name.lower() in {"special:filepath", "wiki"}:
        return ""
    return name if name.startswith("File:") else f"File:{name}"


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return [part.strip() for part in parts if part.strip()]


def area_ok(island: dict | None) -> bool:
    if not island:
        return False
    area = island.get("area") or 0
    return MIN_AREA <= area <= 8000


def bind_fast_match(atlas: Atlas) -> None:
    """Exact names are looked up in one index. match_island_phrase stays the matcher."""
    exact: dict[str, list] = {}
    for island in atlas.islands:
        exact.setdefault(fold(island["name"]), []).append(island)

    def match_name(*names: str):
        exact_hits = []
        seen_exact = set()
        for name in names:
            if not name:
                continue
            for island in exact.get(fold(name), []):
                if island["id"] not in seen_exact:
                    seen_exact.add(island["id"])
                    exact_hits.append(island)
        chosen = Atlas._prefer_largest(exact_hits)
        if chosen or exact_hits:
            return chosen
        hits = []
        seen = set()
        for name in names:
            if not name:
                continue
            for island in atlas.by_key.get(name_key(name), []):
                if island["id"] in seen:
                    continue
                seen.add(island["id"])
                hits.append(island)
        return Atlas._prefer_largest(hits)

    atlas.match_name = match_name  # type: ignore[method-assign]


def resolve_phrase(atlas: Atlas, phrase: str) -> dict | None:
    cleaned = re.sub(r"\s+", " ", (phrase or "")).strip(" ,.;:-")
    if not cleaned or squash(cleaned) in OVERSEAS_PHRASES:
        return None
    island = match_island_phrase(atlas, cleaned)
    if island:
        return island
    match = re.match(r"^(?:the\s+)?island of\s+(.+)$", cleaned, re.I)
    if match:
        return match_island_phrase(atlas, "Isle of " + match.group(1).strip())
    return None


def build_phrases(atlas: Atlas) -> dict[str, str]:
    """Folded phrase -> island id. Every phrase resolves through match_island_phrase."""
    exact_counts: dict[str, int] = defaultdict(int)
    for island in atlas.islands:
        if area_ok(island):
            exact_counts[squash(island["name"])] += 1
    phrases: dict[str, str] = {}

    def add(phrase: str, island: dict) -> None:
        folded = squash(phrase)
        if len(folded) < 4 or folded in NATION_PHRASES or folded in OVERSEAS_PHRASES:
            return
        if exact_counts.get(folded, 0) > 1:
            return
        resolved = resolve_phrase(atlas, phrase)
        if not resolved or resolved["id"] != island["id"] or not area_ok(resolved):
            return
        phrases[folded] = island["id"]

    for island in atlas.islands:
        if not area_ok(island):
            continue
        name = (island.get("name") or "").strip()
        if not name or squash(name) in NATION_PHRASES:
            continue
        add(name, island)
        base = re.sub(r"\s*\([^)]*\)", "", name).strip()
        if base and squash(base) != squash(name):
            add(base, island)
        paren = re.search(r"\(([^)]+)\)", name)
        if paren:
            add(paren.group(1).strip(), island)
        key = name_key(name)
        if key and len(key) >= 4 and " " not in key:
            add(f"Isle of {key}", island)
            add(f"island of {key}", island)
            # "Barry Island" must not match the word Barry, and "Inch Kenneth"
            # must not match Kenneth. A bare token is kept only when the
            # atlas name is that word, or "Isle of" that word.
            bare_name = squash(base or name)
            if key not in NO_BARE and bare_name in {key, f"isle of {key}"}:
                add(key, island)
    log(f"phrases: {len(phrases)} island forms")
    return phrases


def phrase_index(phrases: dict[str, str]) -> dict[str, list[tuple[str, str]]]:
    by_first: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for phrase, island_id in phrases.items():
        first = phrase.split(" ", 1)[0]
        by_first[first].append((phrase, island_id))
    for bucket in by_first.values():
        bucket.sort(key=lambda item: len(item[0]), reverse=True)
    return by_first


def mentions_phrase(phrase: str, text: str) -> bool:
    if not phrase or not text:
        return False
    if phrase == "mull":
        cleaned = re.sub(r"\bmull\s+of\s+(kintyre|galloway)\b", " ", squash(text))
        return re.search(r"\bmull\b", cleaned) is not None
    return phrase_in_text(phrase, text)


def find_phrase_hits(text: str, by_first: dict[str, list[tuple[str, str]]]) -> list[tuple[str, str]]:
    folded = squash(text)
    found: list[tuple[int, int, str, str]] = []
    for match in re.finditer(r"[a-z0-9]+(?:'[a-z0-9]+)?", folded):
        start = match.start()
        token = match.group()
        for phrase, island_id in by_first.get(token, ()):
            end = start + len(phrase)
            if folded[start:end] != phrase:
                continue
            if start > 0 and (folded[start - 1].isalnum() or folded[start - 1] == "'"):
                continue
            if end < len(folded) and (folded[end].isalnum() or folded[end] == "'"):
                continue
            guard = BARE_BLOCK_AFTER.get(phrase)
            if guard and guard.match(folded[end : end + 24]):
                continue
            found.append((start, end, phrase, island_id))
    found.sort(key=lambda item: (item[1] - item[0]), reverse=True)
    kept: list[tuple[str, str]] = []
    spans: list[tuple[int, int]] = []
    seen: set[str] = set()
    for start, end, phrase, island_id in found:
        if any(not (end <= left or start >= right) for left, right in spans):
            continue
        spans.append((start, end))
        if island_id in seen:
            continue
        seen.add(island_id)
        kept.append((phrase, island_id))
    return kept


def cue_relation(sentence: str) -> str:
    filmed = bool(FILMED_CUE.search(sentence or ""))
    # "Filming took place" is a shoot. It is not a narrative setting.
    setting = bool(
        re.search(
            r"\b(set in|set on|is set|was set|were set|story is set|stories are set)\b",
            sentence or "",
            re.I,
        )
    )
    if filmed and setting:
        return "filmed and set"
    if filmed:
        return "filmed"
    if setting:
        return "set"
    return ""


def located_mention(phrase: str, sentence: str) -> bool:
    """A one-word island name has to be used as a place, not as a surname or a breed."""
    if not mentions_phrase(phrase, sentence):
        return False
    folded_phrase = squash(phrase)
    text = squash(sentence)
    if folded_phrase == "skye":
        text = re.sub(r"\bskye\s+(terrier|boat|song|blue)\b", " ", text)
        if not re.search(r"\bskye\b", text):
            return False
    if " " in folded_phrase:
        return True
    if re.search(rf"\b(?:isle|island)\s+of\s+{re.escape(folded_phrase)}\b", text):
        return True
    return bool(
        re.search(
            rf"\b(?:on|in|off|from|to|at|around|across|near)\s+(?:the\s+)?(?:[\w'-]+\s+){{0,6}}{re.escape(folded_phrase)}\b",
            text,
        )
    )


def best_sentence(text: str, phrase: str) -> tuple[str, str]:
    found = ""
    relation = ""
    for sentence in sentences(text):
        if not located_mention(phrase, sentence):
            continue
        role = cue_relation(sentence)
        clauses = [clause.strip() for clause in re.split(r"[,;]", sentence) if mentions_phrase(phrase, clause)]
        if len(clauses) == 1:
            clause_role = cue_relation(clauses[0])
            if clause_role:
                role = clause_role
        if not role:
            continue
        if OVERSEAS_SENTENCE.search(sentence) and not HOME_SENTENCE.search(sentence):
            continue
        return sentence, role
    return found, relation


def title_in_text(title: str, aliases: list[str], text: str) -> bool:
    seen: set[str] = set()
    for raw in [title, *aliases]:
        if not raw:
            continue
        for candidate in (raw, re.sub(r"\s*\([^)]*\)", " ", raw)):
            cleaned = re.sub(r"\s+", " ", candidate).strip(" .")
            folded = squash(cleaned)
            if len(folded) < 4 or folded in seen:
                continue
            seen.add(folded)
            if phrase_in_text(cleaned, text):
                return True
    return False


def is_work_lead(text: str) -> bool:
    if not text or DISAMBIG.search(text[:500]):
        return False
    first = sentences(text)[:1]
    head = first[0] if first else text[:400]
    if ISLAND_PAGE.search(head) and not WORK_LEAD.search(head):
        return False
    return bool(WORK_LEAD.search(text[:900]))


def kind_from(text: str, fallback: str) -> str:
    first = ""
    parts = sentences(text)
    if parts:
        first = parts[0]
    patterns = (
        (r"television mini-?series", "television miniseries"),
        (r"documentary film|\bdocumentary\b", "documentary"),
        (r"television film|tv film", "television film"),
        (r"television series|tv series|sitcom", "television series"),
        (r"short film", "short film"),
        (r"\bfilm\b", "film"),
    )
    # The opening sentence says what the work is. A later mention of another
    # series it spun off from does not change that.
    for blob in (first, " ".join((text or "").split()[:80])):
        if not blob:
            continue
        for pattern, kind in patterns:
            if re.search(pattern, blob, re.I):
                return kind
    return fallback or "film"


def place_prose(name: str) -> str:
    base = re.sub(r"\s*\([^)]*\)", "", name or "").strip()
    if base.lower() in {"mainland", "holy island"}:
        shown = name
    else:
        shown = base or name
    if re.match(r"^(isle|island|ynys|eilean|inis|inish)\b", shown, re.I):
        return f"the {shown}"
    return shown


def relation_phrase(role: str) -> str:
    if role == "filmed and set":
        return "filmed and set on"
    if role == "filmed":
        return "filmed on"
    return "set on"


def one_summary(title: str, lead: str, place: str, role: str, kind_fallback: str) -> str:
    plain = re.sub(r"\s*\([^)]*\)\s*$", "", title).strip() or title
    plain = re.sub(r"\s+", " ", plain)
    relation = relation_phrase(role)
    first = sentences(lead)[:1]
    sentence = first[0] if first else ""
    sentence = re.sub(r"\s+", " ", sentence).strip()
    sentence = re.sub(r"\bQ\d+\b", "", sentence)
    usable = (
        sentence
        and len(sentence) <= 320
        and not ADDRESS.search(sentence)
        and not OWNED.search(sentence)
        and phrase_in_text(plain, sentence)
        and mentions_phrase(place, sentence)
        and cue_relation(sentence)
    )
    if usable:
        text = sentence if sentence.endswith((".", "!", "?")) else sentence + "."
    else:
        kind = kind_from(lead, kind_fallback)
        text = f"{plain} is a {kind}, {relation} {place}."
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\bQ\d+\b", "", text)
    return text[:500]


def evidence_text(sentence: str, title: str, island_name: str) -> str:
    sentence = re.sub(r"\s+", " ", sentence or "").strip()
    if not sentence or ADDRESS.search(sentence) or OWNED.search(sentence):
        return f"Wikipedia lead names '{title}' and '{island_name}'."
    if len(sentence) > 480:
        sentence = sentence[:460].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    return sentence


def licence_ok(short: str) -> bool:
    text = html_text(short).lower()
    if not text:
        return False
    if re.search(r"non-?commercial|no-?derivatives|noncommercial|\bfair use\b|\ball rights\b", text):
        return False
    if re.search(r"(^|[^a-z])(nc|nd)([^a-z]|$)", text):
        return False
    if re.search(r"\bcc[ -]?0\b|\bpublic domain\b|\bpd\b|\bcc[ -]?by[ -]?sa\b|\bcc[ -]?by\b", text):
        return True
    if text in {"attribution", "attribution-sharealike", "attribution sharealike"}:
        return True
    if "sharealike" in text.replace(" ", "") or "share alike" in text:
        return True
    return False


def cache_file(kind: str, key: str) -> Path:
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:24]
    path = CACHE / kind / f"{digest}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def polite(kind: str, key: str, fetch):
    path = cache_file(kind, key)
    if path.exists():
        return load_json(path, {}), False
    payload = fetch()
    save_json(path, payload)
    time.sleep(SLEEP)
    return payload, True


def wikidata_sparql(query: str, attempts: int = 2, timeout: int = 70) -> dict:
    body = urllib.parse.urlencode({"format": "json", "query": query}).encode("utf-8")
    last_error = None
    for attempt in range(attempts):
        try:
            payload = http_json(
                WIKIDATA_ENDPOINT,
                data=body,
                headers={
                    "Accept": "application/sparql-results+json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                timeout=timeout,
                user_agent=USER_AGENT,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            last_error = exc
            wait = 15 * (attempt + 1)
            log(f"wikidata attempt {attempt + 1} failed ({exc}); waiting {wait}s")
            time.sleep(wait)
            continue
        if not isinstance(payload, dict) or payload.get("results") is None:
            last_error = RuntimeError(str(payload)[:240])
            wait = 15 * (attempt + 1)
            log(f"wikidata attempt {attempt + 1} returned no results; waiting {wait}s")
            time.sleep(wait)
            continue
        return payload
    raise RuntimeError(f"Wikidata request failed: {last_error}")


def wiki_get(params: dict, endpoint: str = WIKI_API) -> dict:
    """GET a MediaWiki API. Back off on rate limits instead of retrying at once."""
    url = endpoint + "?" + urllib.parse.urlencode(params)
    last_error = None
    for attempt in range(4):
        try:
            return http_json(url, timeout=60, user_agent=USER_AGENT)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            last_error = exc
            wait = 25 * (attempt + 1)
            log(f"wikipedia attempt {attempt + 1} failed; waiting {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"Wikipedia request failed: {last_error}")


def values_clause(items: list[str], prefix: str = "wd:") -> str:
    return " ".join(prefix + item for item in items)


def query_by_qid(qids: list[str], subclass: bool) -> str:
    places = values_clause(qids)
    if subclass:
        typed = f"""
  ?work wdt:P31/wdt:P279* ?class .
  VALUES ?class {{ {values_clause(list(CLASS_ROOTS))} }}"""
    else:
        typed = f"""
  ?work wdt:P31 ?class .
  VALUES ?class {{ {values_clause(list(DIRECT_CLASSES))} }}"""
    return f"""
SELECT DISTINCT ?work ?workLabel ?place ?placeLabel ?article ?image ?direct WHERE {{
  VALUES ?place {{ {places} }}
  VALUES ?direct {{ wdt:P915 wdt:P840 }}
  ?work ?direct ?place .
  FILTER(?work != ?place)
  {typed}
  OPTIONAL {{ ?article schema:about ?work ; schema:isPartOf <https://en.wikipedia.org/> . }}
  OPTIONAL {{ ?work wdt:P18 ?image }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
"""


def query_by_label(labels: list[str], subclass: bool) -> str:
    quoted = " ".join(json.dumps(label) + "@en" for label in labels)
    if subclass:
        typed = f"""
  ?work wdt:P31/wdt:P279* ?class .
  VALUES ?class {{ {values_clause(list(CLASS_ROOTS))} }}"""
    else:
        typed = f"""
  ?work wdt:P31 ?class .
  VALUES ?class {{ {values_clause(list(DIRECT_CLASSES))} }}"""
    return f"""
SELECT DISTINCT ?work ?workLabel ?place ?placeLabel ?article ?image ?direct WHERE {{
  VALUES ?label {{ {quoted} }}
  ?place rdfs:label ?label .
  FILTER(LANG(?label) = "en")
  VALUES ?direct {{ wdt:P915 wdt:P840 }}
  ?work ?direct ?place .
  FILTER(?work != ?place)
  {typed}
  OPTIONAL {{ ?article schema:about ?work ; schema:isPartOf <https://en.wikipedia.org/> . }}
  OPTIONAL {{ ?work wdt:P18 ?image }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
"""


def parse_bindings(payload: dict) -> list[dict]:
    rows = []
    for binding in payload.get("results", {}).get("bindings", []):
        rows.append(
            {
                "work": qid_of(binding.get("work", {}).get("value") or ""),
                "label": (binding.get("workLabel", {}).get("value") or "").strip(),
                "place": qid_of(binding.get("place", {}).get("value") or ""),
                "placeLabel": (binding.get("placeLabel", {}).get("value") or "").strip(),
                "article": binding.get("article", {}).get("value") or "",
                "image": binding.get("image", {}).get("value") or "",
                "prop": (binding.get("direct", {}).get("value") or "").rsplit("/", 1)[-1],
            }
        )
    return rows


# Subclass walks (P279*) time out more often than a direct class list.
# After two failures, later batches use the direct list only.
PREFER_DIRECT = False


def run_query_batches(kind: str, batches: list[list[str]], query_fn, failed: list[str]) -> list[dict]:
    global PREFER_DIRECT
    found: list[dict] = []
    subclass_failures = 0
    log(f"{kind}: {sum(len(batch) for batch in batches)} values, {len(batches)} batches")
    for index, batch in enumerate(batches, start=1):
        key = kind + ":" + "|".join(batch)
        path = cache_file("sparql", key)
        if path.exists():
            payload = load_json(path, {})
            rows = payload.get("rows") or []
            found.extend(rows)
            log(f"{kind} batch {index}/{len(batches)} cached ({len(rows)} rows)")
            continue
        rows: list[dict] = []
        chunks = [batch]
        ok = True
        while chunks:
            chunk = chunks.pop(0)
            subkey = kind + ":" + "|".join(chunk)
            subpath = cache_file("sparql", subkey)
            if subpath.exists() and subkey != key:
                rows.extend(load_json(subpath, {}).get("rows") or [])
                continue
            payload = None
            modes = (False,) if PREFER_DIRECT else (True, False)
            for subclass in modes:
                try:
                    payload = wikidata_sparql(
                        query_fn(chunk, subclass),
                        attempts=1 if subclass else 2,
                        timeout=45 if subclass else 70,
                    )
                    break
                except RuntimeError as exc:
                    log(f"{kind} {'subclass' if subclass else 'direct'} failed: {exc}")
                    payload = None
                    if subclass:
                        subclass_failures += 1
                        if subclass_failures >= 2:
                            PREFER_DIRECT = True
                            log("wikidata subclass queries are failing; later batches use direct classes")
            if payload is None:
                if len(chunk) > 1:
                    mid = len(chunk) // 2
                    chunks.insert(0, chunk[mid:])
                    chunks.insert(0, chunk[:mid])
                    log(f"splitting a {kind} batch of {len(chunk)}")
                    continue
                ok = False
                failed.append(subkey)
                log(f"skipping {subkey}")
                continue
            parsed = parse_bindings(payload)
            save_json(subpath, {"rows": parsed})
            time.sleep(SLEEP)
            if subkey != key:
                rows.extend(parsed)
            else:
                rows = parsed
        if ok:
            save_json(path, {"rows": rows, "ok": True})
        found.extend(rows)
        log(f"{kind} batch {index}/{len(batches)}: {len(rows)} links")
    return found


def usable_qids(atlas: Atlas) -> dict[str, dict]:
    by_qid = _atlas_qids(atlas)
    flags = (load_json(PLACE_CACHE, {}) or {}).get("places") or {}
    usable = {}
    for qid, island in by_qid.items():
        if qid in BLOCKED_PLACE_QIDS or flags.get(qid) is False:
            continue
        if squash(island.get("name") or "") in NATION_PHRASES:
            continue
        area = island.get("area") or 0
        if area < QID_MIN_AREA or area > 8000:
            continue
        usable[qid] = island
    log(f"wikidata places: {len(by_qid)} atlas QIDs, {len(usable)} usable")
    return usable


def place_to_island(atlas: Atlas, by_qid: dict[str, dict], qid: str, label: str) -> dict | None:
    if qid in BLOCKED_PLACE_QIDS:
        return None
    island = by_qid.get(qid)
    if island and area_ok(island) and squash(island.get("name") or "") not in NATION_PHRASES:
        return island
    for phrase in (label, f"Isle of {label}" if label else ""):
        resolved = resolve_phrase(atlas, phrase)
        if resolved and area_ok(resolved):
            return resolved
    return None


def foreign_film_keys() -> set[tuple[str, str]]:
    keys = existing_facet_keys("film")
    own = ROOT / "data" / "interest" / "candidates" / f"{OUTPUT_SLUG}.json"
    if own.exists():
        for item in (load_json(own, {}) or {}).get("rows") or []:
            if item.get("status") != "accepted":
                continue
            island_id = item.get("island_id") or ""
            title = item.get("title") or ""
            if island_id and title:
                keys.discard((island_id, fold(title)))
    loose = {(island_id, norm_title(title)) for island_id, title in keys}
    return keys | loose


def already_known(seen: set[tuple[str, str]], island_id: str, title: str) -> bool:
    folded = fold(title)
    norm = norm_title(title)
    if (island_id, folded) in seen or (island_id, norm) in seen:
        return True
    # "Waking Ned" is the same film as the accepted title "Waking Ned Devine".
    if len(norm) < 10:
        return False
    for seen_id, seen_title in seen:
        if seen_id != island_id or len(seen_title) < 10:
            continue
        if seen_title.startswith(norm + " ") or norm.startswith(seen_title + " "):
            return True
    return False


def remember(seen: set[tuple[str, str]], island_id: str, title: str) -> None:
    seen.add((island_id, fold(title)))
    seen.add((island_id, norm_title(title)))


def category_members(failed: list[str]) -> list[tuple[str, str]]:
    pages: list[tuple[str, str]] = []
    for title, role in CATEGORIES:
        key = "category:" + title

        def fetch(title: str = title) -> dict:
            return wiki_get(
                {
                    "action": "query",
                    "format": "json",
                    "list": "categorymembers",
                    "cmtitle": "Category:" + title,
                    "cmnamespace": "0",
                    "cmtype": "page",
                    "cmlimit": str(CATEGORY_CAP),
                }
            )

        try:
            payload, fresh = polite("categories", key, fetch)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError, RuntimeError) as exc:
            failed.append("wikipedia category " + title)
            log(f"category failed {title}: {exc}")
            continue
        members = ((payload.get("query") or {}).get("categorymembers") or [])[:CATEGORY_CAP]
        log(f"category {title}: {len(members)} pages" + ("" if fresh else " (cached)"))
        for member in members:
            page = (member.get("title") or "").strip()
            if not page or page.startswith(("List of ", "Lists of ", "Timeline of ", "Index of ")):
                continue
            pages.append((page, role))
    return pages


def fetch_extracts(titles: list[str], failed: list[str]) -> dict[str, dict]:
    records: dict[str, dict] = {}
    missing = []
    for title in titles:
        path = cache_file("extracts", squash(title))
        if path.exists():
            records[squash(title)] = load_json(path, {})
        else:
            missing.append(title)
    log(f"extracts: {len(titles)} pages, {len(missing)} to fetch")
    for start in range(0, len(missing), 6):
        batch = missing[start : start + 6]
        key = "batch:" + "|".join(squash(title) for title in batch)

        def fetch(batch: list[str] = batch) -> dict:
            return wiki_get(
                {
                    "action": "query",
                    "format": "json",
                    "redirects": "1",
                    "prop": "extracts|pageimages",
                    "exintro": "1",
                    "explaintext": "1",
                    "exlimit": "max",
                    "piprop": "name",
                    "titles": "|".join(batch),
                }
            )

        try:
            payload, _fresh = polite("extract-batches", key, fetch)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError, RuntimeError) as exc:
            failed.append("wikipedia extracts " + batch[0])
            log(f"extract batch failed ({exc})")
            continue
        query = payload.get("query") or {}
        redirect_to = {}
        for item in query.get("redirects") or []:
            redirect_to.setdefault(item.get("to") or "", []).append(item.get("from") or "")
        seen_titles = set()
        for page in (query.get("pages") or {}).values():
            canonical = page.get("title") or ""
            names = [canonical, *(redirect_to.get(canonical) or [])]
            record = {
                "title": canonical,
                "extract": "" if page.get("missing") is not None else (page.get("extract") or ""),
                "pageimage": "" if page.get("missing") is not None else (page.get("pageimage") or ""),
                "missing": page.get("missing") is not None,
            }
            for name in names:
                if not name:
                    continue
                seen_titles.add(squash(name))
                save_json(cache_file("extracts", squash(name)), record)
                records[squash(name)] = record
        for title in batch:
            if squash(title) in seen_titles:
                continue
            record = {"title": title, "extract": "", "pageimage": "", "missing": True}
            save_json(cache_file("extracts", squash(title)), record)
            records[squash(title)] = record
        log(f"extracts fetched {min(start + 6, len(missing))}/{len(missing)}")
    return records


def image_record(filename: str, failed: list[str]) -> dict:
    file_title = commons_name(filename)
    if not file_title or BAD_IMAGE.search(file_title):
        return {}
    path = cache_file("images", file_title)

    def fetch(file_title: str = file_title) -> dict:
        return wiki_get(
            {
                "action": "query",
                "format": "json",
                "prop": "imageinfo",
                "iiprop": "url|extmetadata|mime",
                "iiurlwidth": "960",
                "titles": file_title,
            },
            endpoint=COMMONS_API,
        )

    try:
        payload, _fresh = polite("images", file_title, fetch)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError, RuntimeError) as exc:
        failed.append("commons " + file_title)
        log(f"commons failed {file_title}: {exc}")
        return {}
    pages = ((payload.get("query") or {}).get("pages") or {}).values()
    page = next(iter(pages), {})
    info = (page.get("imageinfo") or [{}])[0]
    mime = (info.get("mime") or "").lower()
    if "svg" in mime:
        return {"usable": False}
    meta = info.get("extmetadata") or {}
    short = html_text((meta.get("LicenseShortName") or {}).get("value") or "")
    if not licence_ok(short):
        return {"usable": False, "licence": short}
    artist = html_text((meta.get("Artist") or {}).get("value") or "")
    credit = html_text((meta.get("Credit") or {}).get("value") or "")
    thumb = info.get("thumburl") or ""
    if not thumb:
        return {"usable": False, "licence": short}
    file_name = page.get("title") or file_title
    return {
        "usable": True,
        "commons_file": file_name if file_name.startswith("File:") else file_title,
        "open_image": {
            "thumbUrl": thumb,
            "pageUrl": info.get("descriptionurl") or "",
            "attribution": (artist or credit or "Wikimedia Commons")[:240],
            "licence": short,
            "licenceUrl": (meta.get("LicenseUrl") or {}).get("value") or "",
        },
    }


def fallback_kind(roles: set[str], props: set[str]) -> str:
    if "filmed" in roles or "P915" in props:
        return "film"
    return "television series" if "set" in roles else "film"


def reject_row(
    *,
    title: str,
    source_url: str,
    island: dict | None,
    reason: str,
    evidence: str,
    licence: str,
) -> dict:
    built = row(
        category="film-art-music",
        island_id=(island or {}).get("id") or "",
        island_name=(island or {}).get("name") or "",
        facet="film",
        title=(title or "Untitled")[:180],
        source_url=source_url,
        source_title=(title or "")[:180],
        licence=licence,
        evidence=evidence[:500],
        status="rejected",
        confidence="high",
        reject_reason=reason,
    )
    return built


def check_phrases(atlas: Atlas, phrases: dict[str, str]) -> None:
    samples = (
        "isle of mull",
        "mull",
        "skye",
        "papa westray",
        "isle of coll",
        "isle of jersey",
        "barra",
        "foula",
        "south uist",
        "anglesey",
        "isle of wight",
        "fair isle",
        "jersey",
        "harris",
        "skellig michael",
    )
    islands = {island["id"]: island for island in atlas.islands}
    for phrase in samples:
        island_id = phrases.get(phrase, "")
        name = islands.get(island_id, {}).get("name", "")
        log(f"phrase {phrase!r} -> {name or '—'}")


def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    atlas = Atlas()
    bind_fast_match(atlas)
    islands = {island["id"]: island for island in atlas.islands}
    phrases = build_phrases(atlas)
    by_first = phrase_index(phrases)
    if "--check" in sys.argv:
        check_phrases(atlas, phrases)
        return

    failed: list[str] = []
    seen = foreign_film_keys()
    by_qid = usable_qids(atlas)
    qid_batches = [
        sorted(by_qid)[start : start + 12] for start in range(0, len(by_qid), 12)
    ]
    raw = run_query_batches("qid", qid_batches, query_by_qid, failed)

    def display_label(island: dict) -> str:
        name = re.sub(r"\s*\([^)]*\)", "", island.get("name") or "").strip()
        resolved = resolve_phrase(atlas, name)
        if resolved and resolved["id"] == island["id"]:
            return name
        key = name_key(island.get("name") or "")
        cased = " ".join(part[:1].upper() + part[1:] for part in key.split() if part)
        return f"Isle of {cased}" if cased else name

    labels_seen: set[str] = set()
    labels: list[str] = []
    for island in islands.values():
        area = island.get("area") or 0
        folded_name = squash(island.get("name") or "")
        famous = any(
            token in folded_name
            for token in (
                "papa westray",
                "foula",
                "staffa",
                "iona",
                "fair isle",
                "lundy",
                "bass rock",
                "isle of may",
                "calve",
                "skomer",
                "lindisfarne",
                "brownsea",
                "rathlin",
                "inishmore",
                "achill",
                "valentia",
                "cape clear",
                "alderney",
                "sark",
                "tresco",
            )
        )
        if area < 5 and not famous:
            continue
        if not area_ok(island):
            continue
        label = display_label(island)
        folded = squash(label)
        if not label or folded in labels_seen or folded in NATION_PHRASES:
            continue
        labels_seen.add(folded)
        labels.append(label)
    labels.sort(key=squash)
    label_batches = [labels[start : start + 6] for start in range(0, len(labels), 6)]
    raw.extend(run_query_batches("label", label_batches, query_by_label, failed))

    pages: dict[str, dict] = {}

    def page_slot(title: str) -> dict:
        key = squash(title)
        slot = pages.get(key)
        if slot is None:
            slot = {
                "title": title,
                "aliases": [],
                "article": "",
                "qid": "",
                "image": "",
                "props": set(),
                "roles": set(),
                "hints": [],
            }
            pages[key] = slot
        return slot

    for item in raw:
        label = item.get("label") or ""
        if not label or re.fullmatch(r"Q\d+", label):
            continue
        article = item.get("article") or ""
        wiki_title = wiki_title_from_url(article)
        island = place_to_island(atlas, by_qid, item.get("place") or "", item.get("placeLabel") or "")
        prop = item.get("prop") or ""
        if wiki_title:
            slot = page_slot(wiki_title)
            slot["article"] = article or slot["article"]
            slot["qid"] = item.get("work") or slot["qid"]
            if label and label not in slot["aliases"]:
                slot["aliases"].append(label)
            if item.get("image") and not slot["image"]:
                slot["image"] = item["image"]
            if prop:
                slot["props"].add(prop)
            if island:
                slot["hints"].append({"id": island["id"], "prop": prop, "label": item.get("placeLabel") or ""})
        elif island:
            # No English article to verify. Kept as a rejection below.
            slot = page_slot(label)
            slot["qid"] = item.get("work") or slot["qid"]
            slot["aliases"].append(label)
            slot["hints"].append({"id": island["id"], "prop": prop, "label": item.get("placeLabel") or ""})
            slot["no_article"] = True

    for title, role in category_members(failed):
        slot = page_slot(title)
        slot["roles"].add(role)
        if not slot["article"]:
            slot["article"] = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))

    titles = [slot["title"] for slot in pages.values() if slot.get("article") and not slot.get("no_article")]
    extracts = fetch_extracts(titles, failed)

    accepted_rows = []
    rejected_rows = []
    unnamed_rejects = 0
    picture_queue = []

    for slot in pages.values():
        title = slot["title"]
        article = slot.get("article") or ""
        if slot.get("no_article") or not article:
            hint = (slot.get("hints") or [None])[0]
            island = islands.get((hint or {}).get("id") or "")
            source_url = f"https://www.wikidata.org/wiki/{slot['qid']}" if slot.get("qid") else ""
            if island and source_url and not already_known(seen, island["id"], title):
                rejected_rows.append(
                    reject_row(
                        title=title,
                        source_url=source_url,
                        island=island,
                        reason="page does not name the island",
                        evidence="No English Wikipedia lead names the work and the island.",
                        licence="CC0",
                    )
                )
            continue
        record = extracts.get(squash(title)) or {}
        lead = record.get("extract") or ""
        page_title = record.get("title") or title
        aliases = list(slot.get("aliases") or [])
        if page_title and page_title not in aliases:
            aliases.append(page_title)
        source_url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(page_title.replace(" ", "_"))
        hints = slot.get("hints") or []
        if not is_work_lead(lead):
            if hints:
                hint_island = islands.get(hints[0]["id"])
                rejected_rows.append(
                    reject_row(
                        title=page_title,
                        source_url=source_url,
                        island=hint_island,
                        reason="page does not name the island",
                        evidence="The English Wikipedia lead is not a film or television work that names the island.",
                        licence="CC BY-SA 4.0",
                    )
                )
            continue
        if not title_in_text(page_title, aliases, lead):
            if hints:
                rejected_rows.append(
                    reject_row(
                        title=page_title,
                        source_url=source_url,
                        island=islands.get(hints[0]["id"]),
                        reason="page does not name the island",
                        evidence="The English Wikipedia lead does not name this work.",
                        licence="CC BY-SA 4.0",
                    )
                )
            continue
        hits = find_phrase_hits(lead, by_first)
        matched = []
        for phrase, island_id in hits:
            island = islands.get(island_id)
            if not island:
                continue
            sentence, role = best_sentence(lead, phrase)
            if not sentence:
                continue
            props = {hint.get("prop") for hint in hints if hint.get("id") == island_id}
            if "P915" in props and role == "set":
                role = "filmed and set"
            elif "P915" in props and not role:
                role = "filmed"
            matched.append((island, phrase, sentence, role))
        if matched:
            for island, phrase, sentence, role in matched:
                display = page_title
                if already_known(seen, island["id"], display) or already_known(seen, island["id"], title):
                    continue
                place = place_prose(island["name"])
                summary = one_summary(display, lead, place, role, fallback_kind(slot.get("roles") or set(), slot.get("props") or set()))
                built = row(
                    category="film-art-music",
                    island_id=island["id"],
                    island_name=island["name"],
                    facet="film",
                    title=display[:180],
                    source_url=source_url,
                    source_title=display[:180],
                    licence="CC BY-SA 4.0",
                    evidence=evidence_text(sentence, display, island["name"]),
                    external_id=slot.get("qid") or page_title.replace(" ", "_"),
                    status="accepted",
                    confidence="high",
                )
                built["summary"] = summary
                built["location_role"] = role
                accepted_rows.append(built)
                remember(seen, island["id"], display)
                picture_queue.append((built, record.get("pageimage") or "", slot.get("image") or ""))
            continue
        # Nothing in the lead survived.
        named_gap = ""
        folded_lead = squash(lead)
        for phrase in NOT_ATLAS:
            if phrase_in_text(phrase, lead) or phrase in folded_lead:
                named_gap = phrase
                break
        if named_gap:
            rejected_rows.append(
                reject_row(
                    title=page_title,
                    source_url=source_url,
                    island=None,
                    reason="wrong island",
                    evidence=f"The lead names {named_gap}, which is not an atlas island.",
                    licence="CC BY-SA 4.0",
                )
            )
            continue
        if hints:
            hint_island = islands.get(hints[0]["id"])
            rejected_rows.append(
                reject_row(
                    title=page_title,
                    source_url=source_url,
                    island=hint_island,
                    reason="page does not name the island",
                    evidence="Wikidata links a place, but the English Wikipedia lead does not say the work was filmed or set on that island.",
                    licence="CC BY-SA 4.0",
                )
            )
            continue
        if unnamed_rejects < 80 and re.search(r"\b(island|isle|filmed|shot|set)\b", lead, re.I):
            unnamed_rejects += 1
            rejected_rows.append(
                reject_row(
                    title=page_title,
                    source_url=source_url,
                    island=None,
                    reason="page does not name the island",
                    evidence="The lead does not name an atlas island as a filming location or setting.",
                    licence="CC BY-SA 4.0",
                )
            )

    with_image = 0
    for built, pageimage, wikidata_image in picture_queue:
        chosen = {}
        for candidate in (pageimage, wikidata_image):
            if not candidate:
                continue
            info = image_record(candidate, failed)
            if info.get("usable"):
                chosen = info
                break
        if not chosen:
            continue
        built["commons_file"] = chosen["commons_file"]
        built["open_image"] = chosen["open_image"]
        with_image += 1

    rows = accepted_rows + rejected_rows
    rows.sort(key=lambda item: (item.get("status") != "accepted", squash(item.get("island_name") or ""), squash(item.get("title") or "")))
    sources = []
    if raw:
        sources.append("wikidata")
    if extracts:
        sources.append("wikipedia")
    if with_image:
        sources.append("commons")
    write_candidates(
        OUTPUT_SLUG,
        rows,
        {
            "meta": {
                "accepted": len(accepted_rows),
                "rejected": len(rejected_rows),
                "withImage": with_image,
                "sources": sources,
                "failed": failed[:40],
            }
        },
    )
    island_names = sorted({item["island_name"] for item in accepted_rows})
    log(
        f"SUMMARY accepted={len(accepted_rows)} rejected={len(rejected_rows)} "
        f"islands={len(island_names)} withImage={with_image} failed={len(failed)}"
    )
    for item in accepted_rows[:20]:
        picture = "picture" if item.get("commons_file") else "no picture"
        log(
            f"ACCEPT {item['title']} | {item['island_name']} | {item['island_id']} | "
            f"{item.get('location_role')} | {item['source_url']} | {picture}"
        )
    for item in rejected_rows[:10]:
        log(f"REJECT {item['title']} | {item.get('reject_reason')} | {item.get('evidence', '')[:140]}")
    if failed:
        log("FAILED " + "; ".join(failed[:20]))


if __name__ == "__main__":
    main()
