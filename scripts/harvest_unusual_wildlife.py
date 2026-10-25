#!/usr/bin/env python3
"""Cite unusual wildlife on atlas islands.

Reads Wikidata (endemic to, or named after, an island) and the research
files in data/interest/research/wildlife-*.json. A row is accepted only when
the source page itself names the species and the island. The published
paragraph is taken from that page.

Island-level only. Colony coordinates, nest counts, and visit advice are
not stored. Does not edit islands.json and does not publish the filter.
"""

from __future__ import annotations

import html
import re
import sys
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from interest_categories import (  # noqa: E402
    Atlas,
    _atlas_qids,
    _commons_file,
    _qid,
    _sentences,
    fold,
    http_json,
    name_key,
    row,
    utc_now,
    wikipedia_plain,
    write_candidates,
)

DATA = ROOT / "data"
RESEARCH = DATA / "interest" / "research"
CACHE = DATA / "cache_wildlife_interest"
WIKIDATA_CACHE = DATA / "cache_wikidata_wildlife.json"
VERSION = 2

# One atlas id for a name that is not shared. Ambiguous names are resolved
# from the source text, not from this table.
ALIASES = {
    "orkney": "mainland-orkney",
    "orkney islands": "mainland-orkney",
    "the orkney islands": "mainland-orkney",
    "shetland": "mainland-shetland",
    "shetland islands": "mainland-shetland",
    "isles of scilly": "scilly-st-marys",
    "scilly isles": "scilly-st-marys",
    "scilly": "scilly-st-marys",
    "st kilda": "st-kilda",
    "saint kilda": "st-kilda",
    "hirta": "st-kilda",
    "farne islands": "osm-relation-3077272",
    "the farne islands": "osm-relation-3077272",
    "inner farne": "osm-relation-3077272",
    "treshnish isles": "osm-way-4009570",
    "treshnish islands": "osm-way-4009570",
    "aran islands": "osm-relation-6045552",
    "inis mor": "osm-relation-6045552",
    "inis mór": "osm-relation-6045552",
    "rum": "osm-relation-929839",
    "rhum": "osm-relation-929839",
    "isle of rum": "osm-relation-929839",
    "canna": "osm-way-4004501",
    "handa": "osm-way-417926365",
    "handa island": "osm-way-417926365",
    "bass rock": "osm-way-3469292",
    "the bass rock": "osm-way-3469292",
    "isle of may": "osm-way-3469279",
    "noss": "osm-way-8590977",
    "isle of noss": "osm-way-8590977",
    "foula": "osm-relation-8249591",
    "fair isle": "fair-isle",
    "skomer": "osm-relation-2856487",
    "skomer island": "osm-relation-2856487",
    "skokholm": "osm-way-1493746497",
    "skokholm island": "osm-way-1493746497",
    "grassholm": "osm-way-27013704",
    "ramsey": "osm-relation-3012320",
    "ramsey island": "osm-relation-3012320",
    "bardsey": "osm-relation-6046655",
    "bardsey island": "osm-relation-6046655",
    "ynys enlli": "osm-relation-6046655",
    "lundy": "lundy",
    "lundy island": "lundy",
    "brownsea": "brownsea",
    "brownsea island": "brownsea",
    "rathlin": "rathlin",
    "rathlin island": "rathlin",
    "tory": "osm-way-4558807",
    "tory island": "osm-way-4558807",
    "coquet": "wd-Q2755722",
    "coquet island": "wd-Q2755722",
    "ailsa craig": "osm-way-495525351",
    "lambay": "osm-way-329053691",
    "lambay island": "osm-way-329053691",
    "rockabill": "osm-relation-1146449",
    "great saltee": "osm-way-128077107",
    "saltee islands": "osm-way-128077107",
    "the saltees": "osm-way-128077107",
    "cape clear": "osm-relation-8495304",
    "cape clear island": "osm-relation-8495304",
    "clear island": "osm-relation-8495304",
    "inchconnachan": "osm-way-4821984",
    "calf of man": "osm-way-25987471",
    "the calf of man": "osm-way-25987471",
    "alderney": "osm-relation-12913146",
    "isle of arran": "arran",
    "arran": "arran",
    "islay": "islay",
    "isle of islay": "islay",
    "isle of mull": "mull",
    "mull": "mull",
    "iona": "iona",
    "eigg": "osm-relation-1663615",
    "isle of eigg": "osm-relation-1663615",
    "colonsay": "osm-relation-6045516",
    "unst": "osm-relation-6045406",
    "jersey": "jersey",
    "guernsey": "guernsey",
    "sark": "osm-way-2956937",
    "herm": "osm-way-2956897",
    "isle of wight": "isle-of-wight",
    "lindisfarne": "lindisfarne",
    "holy island lindisfarne": "lindisfarne",
    "steep holm": "osm-way-30782387",
    "flat holm": "osm-way-126546636",
    "staffa": "staffa",
    "papa westray": "osm-way-4569530",
    "north ronaldsay": "osm-way-4569485",
    "auskerry": "osm-relation-17748758",
    "copinsay": "osm-way-4569437",
    "mousa": "osm-way-179220328",
    "mingulay": "osm-way-885235014",
    "jura": "osm-relation-4619204",
    "isle of jura": "osm-relation-4619204",
    "isle of skye": "isle-of-skye",
    "skye": "isle-of-skye",
    "gigha": "osm-relation-6949620",
    "isle of gigha": "osm-relation-6949620",
    "fetlar": "osm-relation-6045499",
    "bressay": "osm-relation-2291884",
    "whalsay": "osm-way-10303169",
    "yell": "osm-relation-8684336",
    "hoy": "osm-relation-12597159",
    "westray": "osm-relation-3148465",
    "rousay": "osm-relation-13008771",
    "stronsay": "osm-relation-12597195",
    "sanday orkney": "osm-relation-3075243",
    "tresco": "osm-relation-3214114",
    "bryher": "osm-relation-3217444",
    "st martin's": "osm-relation-3210701",
    "st martins": "osm-relation-3210701",
    "st agnes": "osm-relation-3198786",
    "st agnes isles of scilly": "osm-relation-3198786",
    "gugh": "osm-way-237654372",
    "st mary's": "scilly-st-marys",
    "st marys": "scilly-st-marys",
    "burhou": "osm-way-3404592",
    "jethou": "osm-way-2956901",
    "great copeland": "osm-relation-6565329",
    "great copeland island": "osm-relation-6565329",
    "copeland islands": "osm-relation-6565329",
    "scolt head": "osm-relation-9795458",
    "scolt head island": "osm-relation-9795458",
    "dursey": "osm-relation-8609288",
    "dursey island": "osm-relation-8609288",
    "sherkin": "osm-relation-5208439",
    "sherkin island": "osm-relation-5208439",
    "little saltee": "osm-way-4555134",
    "papa stour": "osm-way-173383816",
    "barra": "osm-relation-380646",
    "isle of barra": "osm-relation-380646",
}

# The same island is sometimes stored twice. Keep the curated id.
PREFER_ID = {
    "osm-relation-8305331": "st-kilda",
}

NOT_AN_ISLAND = {
    "ireland",
    "great britain",
    "britain",
    "united kingdom",
    "england",
    "scotland",
    "wales",
    "northern ireland",
    "uk",
}

LIVESTOCK = re.compile(
    r"\b(sheep|pony|ponies|cattle|horse|terrier|pig|goat|breed)\b",
    re.I,
)
TOO_COMMON = re.compile(
    r"^(grey seals?|gray seals?|harbour seals?|harbor seals?|common seals?|"
    r"red deer|rabbits?|european rabbits?|brown rats?|otters?|european otters?|"
    r"herring gulls?|great black-backed gulls?|lesser black-backed gulls?|"
    r"fulmars?|northern fulmars?|shags?|european shags?|cormorants?|"
    r"great cormorants?|eiders?|common eiders?|seabirds?|birds?|wildlife)$",
    re.I,
)
RARE_WORD = re.compile(
    r"\b(endemic|near-endemic|restricted|confined|only|rare|threatened|endangered|"
    r"vulnerable|stronghold|principal|largest|biggest|important|famous|known for|"
    r"noted for|renowned|subspecies|unique|one of the|world's|britain's|ireland's|"
    r"reintroduc\w*|nationally scarce|red list|exclusively|home to)\b",
    re.I,
)
GRID = re.compile(
    r"\b[A-HJ-Z]{2}\s?\d{2,5}\s?\d{2,5}\b|\b[A-Z]{1,2}\d{6,8}\b|\bNGR\b|grid reference",
    re.I,
)
LATLONG = re.compile(r"\b\d{1,2}\.\d{3,}\s*,\s*-?\d{1,3}\.\d{3,}\b")
COUNT = re.compile(
    r"\b(?:about|around|approximately|some|over|nearly|more than|up to|at least|c\.|ca\.?)?\s*"
    r"\d[\d,\.]*(?:\s*(?:–|-|to)\s*\d[\d,\.]*)?\s*"
    r"(?:breeding\s+)?(?:pairs?|nests?|burrows?|apparently occupied(?:\s+\w+)?|aons?|aobs?|"
    r"chicks?|fledglings?|territories)\b",
    re.I,
)
VISIT = re.compile(
    r"\b(best time to visit|when to visit|visitors should|do not approach|"
    r"avoid disturbing|landing is prohibited|no landing)\b",
    re.I,
)
OPEN_PAGE = re.compile(
    r"open government licence|\bogl\b|creative commons|\bcc[- ]?by\b|cc0\b",
    re.I,
)
WHY_SCORE = {
    "endemic": 40,
    "named-for-island": 30,
    "rare-stronghold": 20,
    "unusual-introduction": 10,
}

def _wildlife_query(qids: list[str], prop: str) -> str:
    places = " ".join(f"wd:{qid}" for qid in qids)
    return f"""
SELECT DISTINCT ?taxon ?taxonLabel ?sci ?place ?placeLabel ?article ?image WHERE {{
  VALUES ?place {{ {places} }}
  ?taxon wdt:{prop} ?place .
  ?taxon wdt:P105 ?rank .
  VALUES ?rank {{ wd:Q7432 wd:Q68947 wd:Q767728 }}
  OPTIONAL {{ ?taxon wdt:P225 ?sci }}
  OPTIONAL {{ ?taxon wdt:P18 ?image }}
  OPTIONAL {{ ?article schema:about ?taxon ; schema:isPartOf <https://en.wikipedia.org/> . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
"""


def _mentions(text: str, name: str) -> bool:
    token = fold(name).replace(".", "").strip()
    if len(token) < 3:
        return False
    blob = fold(text).replace(".", "")
    return re.search(rf"\b{re.escape(token)}\b", blob) is not None


def _mentions_scientific(text: str, scientific: str) -> bool:
    parts = [part for part in (scientific or "").split() if part]
    if len(parts) < 2:
        return False
    blob = fold(text)
    return all(re.search(rf"\b{re.escape(fold(part))}\b", blob) for part in parts[:2])


def _scrub_counts(sentence: str) -> str:
    text = re.sub(r"\([^)]*\b(?:pairs?|nests?|burrows?|chicks?|individuals?)[^)]*\)", "", sentence, flags=re.I)
    text = COUNT.sub("", text)
    text = re.sub(r"\(\s*(?:,\s*)?(?:as of \d{4})?\s*\)", "", text)
    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r",\s*,", ", ", text)
    text = re.sub(r"\(\s*,", "(", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _article_sentences(text: str, taxon: str) -> list[str]:
    cleaned = re.sub(r"==+[^=]+==+", "\n", text or "")
    cleaned = re.sub(r"\[\d+\]", "", cleaned)
    cleaned = re.sub(
        rf"^{re.escape(taxon)}\s+(?={re.escape(taxon)}\b)",
        "",
        cleaned.strip(),
        count=1,
        flags=re.I,
    )
    sentences = []
    for block in re.split(r"\n+", cleaned):
        sentences.extend(_sentences(block))
    usable = []
    for sentence in sentences:
        if VISIT.search(sentence) or GRID.search(sentence) or LATLONG.search(sentence):
            continue
        sentence = _scrub_counts(sentence)
        if GRID.search(sentence) or LATLONG.search(sentence) or re.search(r"\bpairs?\b", sentence, re.I):
            continue
        sentence = re.sub(r"\s*\(see [^)]*\)", "", sentence)
        sentence = re.split(r"\bNotable localities\b", sentence, maxsplit=1)[0]
        sentence = re.sub(r"\s{2,}", " ", sentence).strip(" ,;")
        if re.search(r"\bfrom\s+in\b", sentence, re.I):
            continue
        if re.search(r"\b(intend to|plans to|planned to|not to be confused)\b", sentence, re.I):
            continue
        if re.search(r"\b[A-Za-z]+'s of\b", sentence):
            continue
        if len(sentence) < 40 and not re.search(r"\b(endemic|only|restricted)\b", sentence, re.I):
            continue
        if len(sentence) < 28 or re.search(r"\b[A-Z]\.$", sentence):
            continue
        if re.search(r"\b(with|of|about|around|approximately|including)\s*\.?$", sentence, re.I):
            continue
        leftover = re.sub(
            r"\b\d+(?:\.\d+)?\s*(?:km|kilometres?|kilometers?|mi|miles?|metres?|meters?|feet|ft|cm|mm|kg|grams?|oz)\b",
            "",
            sentence,
            flags=re.I,
        )
        leftover = re.sub(r"\b(?:1[5-9]\d{2}|20\d{2})\b", "", leftover)
        if re.search(r"\b\d{3,}\b", leftover):
            continue
        usable.append(sentence)
    return usable


_TAXON_STOP = {
    "island",
    "northern",
    "european",
    "atlantic",
    "common",
    "lesser",
    "great",
    "white",
    "black",
    "red",
    "grey",
    "gray",
    "western",
    "eastern",
    "little",
}


def _about_taxon(text: str, taxon: str, scientific: str) -> bool:
    if _mentions(text, taxon) or _mentions_scientific(text, scientific):
        return True
    words = [word for word in re.findall(r"[a-z]{4,}", fold(taxon)) if word not in _TAXON_STOP]
    if not words:
        return False
    head = words[-1]
    if not re.search(rf"\b{re.escape(head)}s?\b", fold(text)):
        return False
    others = words[:-1]
    if not others:
        return True
    blob = fold(text)
    if any(re.search(rf"\b{re.escape(word)}\b", blob) for word in others):
        return True
    return bool(re.search(r"\b(endemic|subspecies|colon(?:y|ies)|breed(?:s|ing)?)\b", text, re.I))


def _range_excludes(paragraph: str, island_name: str) -> bool:
    match = re.search(r"only (?:known|found) (?:from|on|in) ([^.]+)", paragraph or "", re.I)
    if not match:
        return False
    tokens = [
        token
        for token in re.findall(r"[A-Za-zÀ-ÿ'’]{4,}", island_name or "")
        if fold(token) not in {"isle", "island", "isles", "mainland", "holy"}
    ]
    if not tokens:
        return False
    return not any(_mentions(match.group(1), token) for token in tokens)


def _usable_sentence(sentence: str) -> str:
    if not sentence or VISIT.search(sentence) or GRID.search(sentence) or LATLONG.search(sentence):
        return ""
    cleaned = _scrub_counts(sentence)
    if GRID.search(cleaned) or LATLONG.search(cleaned) or len(cleaned) < 40:
        return ""
    return cleaned


def _named_for_place(taxon: str, places: list[str]) -> bool:
    label = fold(taxon)
    for place in places:
        token = fold(place)
        if len(token) >= 4 and token in label:
            return True
    return False


def _unusual(text: str, taxon: str, why: str, places: list[str]) -> bool:
    if TOO_COMMON.match((taxon or "").strip()):
        return False
    if _named_for_place(taxon, places):
        return True
    if why == "endemic":
        return bool(
            re.search(
                r"\b(endemic|restricted to|confined to|found only|only found|occurs only|only on|only in)\b",
                text or "",
                re.I,
            )
        )
    return bool(RARE_WORD.search(text or ""))


def _compose(text: str, taxon: str, scientific: str, places: list[str], why: str) -> str:
    """One or two sentences from the source: what the species is, and the island link."""
    sentences = _article_sentences(text, taxon)
    place_names = [place for place in places if fold(place) not in NOT_AN_ISLAND and len(fold(place)) >= 3]
    if not sentences or not place_names:
        return ""
    lead = sentences[0] if _about_taxon(sentences[0], taxon, scientific) else ""
    ranked = []
    for index, sentence in enumerate(sentences):
        if not any(_mentions(sentence, place) for place in place_names):
            continue
        about = _about_taxon(sentence, taxon, scientific)
        if about:
            passage = sentence
            if lead and lead != sentence and not _mentions(sentence, taxon):
                passage = f"{lead} {sentence}"
        elif lead and lead != sentence and RARE_WORD.search(sentence):
            # "It is endemic to the island of Arran" does not repeat the plant's name.
            passage = f"{lead} {sentence}"
        else:
            continue
        if not _unusual(passage, taxon, why, place_names):
            continue
        if _laundry_list(passage):
            continue
        score = 0
        if _place_besides_name(sentence, taxon, place_names):
            score += 6
        if _mentions(sentence, taxon) and any(_mentions(sentence, place) for place in place_names):
            score += 5
        if RARE_WORD.search(sentence):
            score += 4
        if index < 3:
            score += 1
        if sentence.count(",") >= 5:
            score -= 4
        if re.search(r"\b(legislation|statutory instrument)\b", sentence, re.I):
            score -= 8
        ranked.append((score, -len(passage), passage))
    if not ranked:
        return ""
    ranked.sort(reverse=True)
    for _, _, paragraph in ranked:
        paragraph = paragraph.strip()
        if not re.search(
            r"\b(endemic|only|restricted|confined|home to|largest|stronghold|rare|famous|important|exclusively|subspecies|found in)\b",
            paragraph,
            re.I,
        ):
            continue
        if len(paragraph) > 680:
            paragraph = paragraph[:660].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
        return paragraph
    return ""


def _place_besides_name(sentence: str, taxon: str, places: list[str]) -> bool:
    stripped = re.sub(re.escape(taxon), " ", sentence or "", flags=re.I)
    return any(_mentions(stripped, place) for place in places)


def _laundry_list(sentence: str) -> bool:
    heads = (
        "puffin",
        "razorbill",
        "guillemot",
        "kittiwake",
        "fulmar",
        "gannet",
        "shearwater",
        "skua",
        "tern",
    )
    blob = fold(sentence)
    hits = [head for head in heads if re.search(rf"\b{head}", blob)]
    if len(hits) < 3:
        return False
    return not re.search(r"\b(largest|principal|endemic|only|stronghold)\b", sentence, re.I)


def _limited_to_somewhere_else(text: str, island_name: str) -> bool:
    for match in re.finditer(
        r"(?:only (?:grows|found|known|occurs|recorded)|(?:grows|occurs|found) only) (?:on|in|from) ([^.]+)",
        text or "",
        re.I,
    ):
        if _range_excludes(f"only found on {match.group(1)}", island_name):
            return True
    return False


def _context_score(island: dict, context: str) -> int:
    ctx = fold(context)
    lat = island["lat"]
    lng = island["lng"]
    score = 1 if (island["area"] or 0) > 0 else 0
    name = fold(island["name"])
    if "arran" in ctx and 55.45 <= lat <= 55.7 and lng <= -4.9:
        score += 8
    if any(word in ctx for word in ("anglesey", "ynys gybi", "holyhead")) and 53.15 <= lat <= 53.4 and -4.8 <= lng <= -4.4:
        score += 8
    if any(word in ctx for word in ("lindisfarne", "northumberland")) and island["id"] == "lindisfarne":
        score += 8
    if "treshnish" in ctx and abs(lat - 56.49) < 0.08 and abs(lng + 6.43) < 0.2:
        score += 8
    if any(word in ctx for word in ("galway", "connemara")) and lat < 54.3 and "inishbofin" in name:
        score += 8
    if "donegal" in ctx and lat > 54.8 and "inishbofin" in name:
        score += 8
    if any(word in ctx for word in ("aran", "galway bay")) and 53.0 <= lat <= 53.25 and lng <= -9.4:
        score += 6
    if any(word in ctx for word in ("barra", "gannet", "barra head")) and abs(lat - 56.78) < 0.12 and "berneray" in name:
        score += 8
    if "uist" in ctx and abs(lat - 57.72) < 0.12 and "berneray" in name:
        score += 8
    if any(word in ctx for word in ("st kilda", "hirta")) and lng < -8.2:
        score += 8
    if "skye" in ctx and abs(lat - 57.15) < 0.15 and "soay" in name:
        score += 6
    if "canna" in ctx and abs(lat - 57.05) < 0.08 and "sanday" in name:
        score += 8
    if "orkney" in ctx and 58.7 <= lat <= 59.5:
        score += 5
    if "shetland" in ctx and lat >= 59.8:
        score += 5
    if any(word in ctx for word in ("anglesey", "penmon", "priestholm")) and abs(lat - 53.32) < 0.08 and abs(lng + 4.03) < 0.15:
        score += 8
    if "kerry" in ctx and 51.6 <= lat <= 52.15 and lng <= -10.0:
        score += 6
    if "scilly" in ctx and lat < 50.05 and lng < -6.0:
        score += 6
    if any(word in ctx for word in ("pembrokeshire", "pembroke", "skomer", "skokholm")) and 51.6 <= lat <= 52.05 and -5.7 <= lng <= -4.8:
        score += 4
    if any(word in ctx for word in ("firth of lorn", "scarba", "luing")) and abs(lat - 56.21) < 0.08 and abs(lng + 5.7) < 0.15:
        score += 8
    return score


def _same_place(left: dict, right: dict) -> bool:
    return abs(left["lat"] - right["lat"]) < 0.04 and abs(left["lng"] - right["lng"]) < 0.06


def _prefer_curated(hits: list[dict]) -> dict | None:
    curated = [
        island
        for island in hits
        if not str(island["id"]).startswith(("osm-", "wd-", "csv-"))
    ]
    if len(curated) == 1:
        return curated[0]
    return None


def _canonical(atlas: Atlas, island: dict | None) -> dict | None:
    if island is None:
        return None
    preferred = atlas.by_id.get(PREFER_ID.get(island["id"]) or "")
    return preferred or island


def resolve_island(atlas: Atlas, names: list[str], context: str) -> tuple[dict | None, str]:
    """Return the atlas island and the place name the source actually uses."""
    cleaned = []
    for name in names:
        label = re.sub(r"\s+", " ", (name or "").strip())
        if label and fold(label) not in NOT_AN_ISLAND:
            cleaned.append(label)
    for name in cleaned:
        island_id = ALIASES.get(fold(name))
        island = atlas.by_id.get(island_id) if island_id else None
        if island and (island.get("area") or 0) <= 8000:
            return _canonical(atlas, island), name
    hits = []
    seen = set()
    for name in cleaned:
        target = fold(name)
        key = name_key(name)
        for island in atlas.islands:
            if island["id"] in seen:
                continue
            exact = fold(island["name"]) == target
            loose = len(key) >= 5 and name_key(island["name"]) == key
            if exact or loose:
                if (island.get("area") or 0) > 8000:
                    continue
                if fold(island["name"]) in NOT_AN_ISLAND or name_key(island["name"]) in NOT_AN_ISLAND:
                    continue
                seen.add(island["id"])
                hits.append(island)
    if not hits:
        return None, cleaned[0] if cleaned else ""
    if len(hits) == 1:
        return _canonical(atlas, hits[0]), cleaned[0]
    clustered = [island for island in hits if _same_place(island, hits[0])]
    if len(clustered) == len(hits):
        chosen = _prefer_curated(hits) or max(hits, key=lambda island: island.get("area") or 0)
        return _canonical(atlas, chosen), cleaned[0]
    ranked = sorted(hits, key=lambda island: (_context_score(island, context), island.get("area") or 0), reverse=True)
    if _context_score(ranked[0], context) >= _context_score(ranked[1], context) + 3:
        return _canonical(atlas, ranked[0]), cleaned[0]
    return None, cleaned[0]


def _wiki_title(url: str) -> str:
    if "/wiki/" not in (url or ""):
        return ""
    return urllib.parse.unquote(url.split("/wiki/", 1)[1]).replace("_", " ")


def _page_text(url: str) -> tuple[str, str]:
    """Return (text, reject_reason). Wikipedia and pages that state an open licence."""
    if not url.startswith("https://"):
        return "", "source URL is not https"
    if "wikipedia.org/wiki/" in url:
        title = _wiki_title(url)
        if not title:
            return "", "Wikipedia URL has no page title"
        try:
            return wikipedia_plain(title), ""
        except RuntimeError as exc:
            return "", str(exc)
    host = urllib.parse.urlparse(url).netloc.lower()
    if host.endswith((".wikipedia.org", "wikidata.org")):
        return "", "use the English Wikipedia article"
    CACHE.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", url)[:140]
    cache = CACHE / f"{safe}.txt"
    if cache.exists():
        text = cache.read_text(encoding="utf-8", errors="replace")
    else:
        import subprocess

        try:
            raw = subprocess.check_output(
                [
                    "curl",
                    "-fsS",
                    "--max-time",
                    "40",
                    "-A",
                    "isles-of-britain/0.1 (unusual-wildlife; research)",
                    "-L",
                    url,
                ],
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError:
            return "", "could not fetch the source page"
        text = raw.decode("utf-8", errors="replace")
        text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
        text = re.sub(r"(?is)<[^>]+>", " ", text)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        cache.write_text(text, encoding="utf-8")
        time.sleep(0.4)
    if not OPEN_PAGE.search(text):
        return "", "page does not state an open licence"
    return text, ""


def _licence_for(url: str) -> str:
    if "wikipedia.org" in url:
        return "CC BY-SA 4.0"
    if "wikidata.org" in url:
        return "CC0"
    return "OGL v3.0"


def _photo_title(taxon: str, photo_page: str, source_url: str) -> str:
    title = _wiki_title(photo_page) or _wiki_title(source_url)
    if title and fold(title) != fold(taxon) and _wiki_title(photo_page):
        return _wiki_title(photo_page)
    if title and "wikipedia.org" in (photo_page or source_url):
        # Prefer the species article over an island article.
        if _wiki_title(photo_page):
            return _wiki_title(photo_page)
        if fold(taxon) and fold(taxon) in fold(title):
            return title
    return taxon


def _load_research() -> list[dict]:
    found = []
    if not RESEARCH.exists():
        return found
    for path in sorted(RESEARCH.glob("wildlife-*.json")):
        import json

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"skipping unreadable {path.name}")
            continue
        rows = payload.get("rows") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            continue
        for item in rows:
            if isinstance(item, dict):
                item["_file"] = path.name
                found.append(item)
    return found


def _bindings(qids: list[str], reason: str, prop: str) -> list[dict]:
    if not qids:
        return []
    try:
        payload = http_json(
            "https://query.wikidata.org/sparql",
            data=urllib.parse.urlencode({"format": "json", "query": _wildlife_query(qids, prop)}).encode("utf-8"),
            headers={
                "Accept": "application/sparql-results+json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=60,
        )
    except Exception as exc:
        print(f"wikidata batch skipped ({reason}): {exc}")
        return []
    found = []
    for binding in payload.get("results", {}).get("bindings", []):
        found.append(
            {
                "taxon": binding.get("taxonLabel", {}).get("value") or "",
                "scientific": binding.get("sci", {}).get("value") or "",
                "place": _qid(binding.get("place", {}).get("value") or ""),
                "place_label": binding.get("placeLabel", {}).get("value") or "",
                "article": binding.get("article", {}).get("value") or "",
                "image": binding.get("image", {}).get("value") or "",
                "why": reason,
                "taxon_qid": _qid(binding.get("taxon", {}).get("value") or ""),
            }
        )
    time.sleep(2.0)
    return found


def _wikidata_rows(qids: list[str]) -> list[dict]:
    import json

    ordered = sorted(set(qids))
    cache = {"version": VERSION, "batches": {}}
    if WIKIDATA_CACHE.exists():
        cached = json.loads(WIKIDATA_CACHE.read_text(encoding="utf-8"))
        if cached.get("version") == VERSION and isinstance(cached.get("batches"), dict):
            cache = cached
    done = cache.setdefault("batches", {})
    print(f"querying Wikidata wildlife for {len(ordered)} islands")
    step = 40
    batches = [ordered[start : start + step] for start in range(0, len(ordered), step)]
    for index, batch in enumerate(batches, start=1):
        key = ",".join(batch)
        if key in done:
            continue
        endemic = _bindings(batch, "endemic", "P183")
        named = _bindings(batch, "named-for-island", "P138")
        done[key] = endemic + named
        WIKIDATA_CACHE.parent.mkdir(parents=True, exist_ok=True)
        WIKIDATA_CACHE.write_text(
            json.dumps({"version": VERSION, "fetchedAt": utc_now(), "batches": done}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if done[key] or index == 1 or index % 10 == 0:
            print(f"wikidata batch {index}/{len(batches)}: {len(done[key])} links")
    rows = []
    for group in done.values():
        rows.extend(group)
    print(f"wikidata wildlife: {len(rows)} links")
    return rows


def _reject(taxon: str, reason: str, **extra) -> dict:
    built = row(
        category="unusual-wildlife",
        island_id=extra.get("island_id") or "",
        island_name=extra.get("island_name") or "",
        facet="wildlife",
        title=taxon or "Unknown",
        source_url=extra.get("source_url") or "https://www.wikidata.org/",
        status="rejected",
        confidence="medium",
        licence=extra.get("licence") or "",
        evidence=extra.get("evidence") or "",
        external_id=extra.get("external_id") or "",
        source_title=extra.get("source_title") or "",
        reject_reason=reason,
    )
    return built


def _consider_wikidata(item: dict, atlas: Atlas, by_qid: dict) -> dict | None:
    taxon = (item.get("taxon") or "").strip()
    if not taxon or re.fullmatch(r"Q\d+", taxon):
        return None
    if LIVESTOCK.search(taxon):
        return _reject(taxon, "livestock or a breed, not wildlife")
    why = item.get("why") or "endemic"
    place_label = item.get("place_label") or ""
    island = _canonical(atlas, by_qid.get(item.get("place") or ""))
    place_name = place_label
    if island is None:
        island, place_name = resolve_island(atlas, [place_label], f"{place_label} {taxon}")
    if island is None:
        return _reject(taxon, "the place is not one atlas island", evidence=place_label)
    article = item.get("article") or ""
    if "wikipedia.org/wiki/" not in article:
        return _reject(
            taxon,
            "no English Wikipedia article to check the island connection",
            island_id=island["id"],
            island_name=island["name"],
            external_id=item.get("taxon_qid") or "",
        )
    text, problem = _page_text(article)
    if problem:
        return _reject(taxon, problem, source_url=article, island_id=island["id"], island_name=island["name"])
    places = [place_name, place_label, island["name"]]
    # Archipelago rows are attached to the principal island, so the
    # paragraph has to name the group the source used.
    if fold(place_label) in ALIASES and fold(place_label) not in fold(island["name"]):
        places.append(place_label)
    paragraph = _compose(text, taxon, item.get("scientific") or "", places, why)
    if paragraph and (_range_excludes(paragraph, island["name"]) or _limited_to_somewhere_else(text, island["name"])):
        paragraph = ""
    if not paragraph:
        return _reject(
            taxon,
            "the article does not tie this species to that island as unusual wildlife",
            source_url=article,
            island_id=island["id"],
            island_name=island["name"],
            external_id=item.get("taxon_qid") or "",
            licence="CC BY-SA 4.0",
        )
    built = row(
        category="unusual-wildlife",
        island_id=island["id"],
        island_name=island["name"],
        facet="wildlife",
        title=taxon,
        source_url=article,
        source_title=_wiki_title(article),
        licence="CC BY-SA 4.0",
        evidence=f"Wikidata {item.get('taxon_qid') or ''} is {why.replace('-', ' ')} {place_label}. The Wikipedia article names both.",
        external_id=item.get("taxon_qid") or "",
        status="accepted",
        confidence="high",
    )
    built["summary"] = paragraph
    built["photo_title"] = _photo_title(taxon, article, article)
    built["commons_file"] = _commons_file(item.get("image") or "")
    built["why"] = why
    return built


def _consider_research(item: dict, atlas: Atlas) -> dict | None:
    taxon = (item.get("taxon") or "").strip()
    source_url = (item.get("source_url") or "").strip()
    if not taxon or not source_url:
        return None
    if LIVESTOCK.search(taxon):
        return _reject(taxon, "livestock or a breed, not wildlife", source_url=source_url)
    why = (item.get("why_unusual") or "rare-stronghold").strip()
    if why not in WHY_SCORE:
        why = "rare-stronghold"
    names = item.get("island_names") or []
    if isinstance(names, str):
        names = [names]
    context = " ".join(
        [
            taxon,
            item.get("scientific") or "",
            item.get("connection") or "",
            " ".join(names),
        ]
    )
    island, place_name = resolve_island(atlas, names, context)
    if island is None:
        return _reject(
            taxon,
            "no single atlas island matches that name",
            source_url=source_url,
            evidence=", ".join(names),
        )
    text, problem = _page_text(source_url)
    if problem:
        return _reject(
            taxon,
            problem,
            source_url=source_url,
            island_id=island["id"],
            island_name=island["name"],
        )
    places = [place_name, island["name"], *names]
    paragraph = _compose(text, taxon, item.get("scientific") or "", places, why)
    if paragraph and (_range_excludes(paragraph, island["name"]) or _limited_to_somewhere_else(text, island["name"])):
        paragraph = ""
    if not paragraph:
        return _reject(
            taxon,
            "the source page does not tie this species to that island as unusual wildlife",
            source_url=source_url,
            island_id=island["id"],
            island_name=island["name"],
            licence=_licence_for(source_url),
        )
    photo = item.get("photo_page") or ""
    built = row(
        category="unusual-wildlife",
        island_id=island["id"],
        island_name=island["name"],
        facet="wildlife",
        title=taxon,
        source_url=source_url,
        source_title=_wiki_title(source_url) or (item.get("source_title") or taxon),
        licence=_licence_for(source_url),
        evidence=f"The source names {taxon!r} and {place_name!r}.",
        external_id="",
        status="accepted",
        confidence="high" if "wikipedia.org" in source_url else "medium",
    )
    built["summary"] = paragraph
    built["photo_title"] = _photo_title(taxon, photo, source_url)
    built["why"] = why
    return built


def _same_story(left: dict, right: dict) -> bool:
    a = fold(left.get("summary") or "")
    b = fold(right.get("summary") or "")
    if len(a) < 50 or len(b) < 50:
        return False
    return a[:70] == b[:70] or a[:70] in b or b[:70] in a


def _latin_title(title: str) -> bool:
    parts = [part for part in (title or "").split() if part]
    if len(parts) < 2:
        return False
    # "Islay shrew" is a common name. A binomial's words are not ordinary English.
    ordinary = {
        "shrew", "vole", "wren", "mouse", "bee", "cabbage", "beetle", "weevil",
        "tern", "leek", "orchid", "lizard", "squirrel", "hedgehog", "puffin",
        "petrel", "peony", "whitebeam", "dandelion", "charr", "chickweed",
        "adder", "tongue", "razorbill", "tree", "fern", "toad", "frog",
    }
    if any(fold(part.strip("'-")) in ordinary for part in parts):
        return False
    return (
        parts[0][:1].isupper()
        and parts[0].isalpha()
        and parts[1][:1].islower()
        and parts[1].isalpha()
    )


def _cap_islands(rows: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    others = []
    for item in rows:
        if item.get("status") != "accepted" or not item.get("island_id"):
            others.append(item)
            continue
        grouped.setdefault(item["island_id"], []).append(item)
    kept = []
    for island_id, group in grouped.items():
        deduped = []
        seen = {}
        for item in sorted(group, key=lambda row_: (0 if "wikipedia.org" in (row_.get("source_url") or "") else 1, -len(row_.get("summary") or ""))):
            key = fold(item.get("title") or "")
            previous = seen.get(key)
            if previous is not None:
                if len(item.get("summary") or "") <= len(previous.get("summary") or ""):
                    item["status"] = "rejected"
                    item["reject_reason"] = "a stronger source already cites this species on this island"
                    others.append(item)
                    continue
                previous["status"] = "rejected"
                previous["reject_reason"] = "a stronger source already cites this species on this island"
                others.append(previous)
                deduped.remove(previous)
            match = next((earlier for earlier in deduped if _same_story(item, earlier)), None)
            if match is not None:
                prefer_common = _latin_title(match.get("title") or "") and not _latin_title(item.get("title") or "")
                if not prefer_common:
                    item["status"] = "rejected"
                    item["reject_reason"] = "a stronger source already cites this species on this island"
                    others.append(item)
                    continue
                match["status"] = "rejected"
                match["reject_reason"] = "the same species is already cited under its common name"
                others.append(match)
                deduped.remove(match)
                seen.pop(fold(match.get("title") or ""), None)
                if len(match.get("summary") or "") > len(item.get("summary") or ""):
                    item["summary"] = match["summary"]
                if fold(item.get("photo_title") or "") in {fold(item.get("title") or ""), ""}:
                    item["photo_title"] = match.get("photo_title") or match.get("source_title") or item.get("photo_title")
            seen[key] = item
            deduped.append(item)
        plain = [item for item in deduped if not _latin_title(item.get("title") or "")]
        blob = fold(" ".join((item.get("summary") or "") + " " + (item.get("title") or "") for item in plain))
        for item in deduped:
            if not _latin_title(item.get("title") or ""):
                continue
            if fold(item.get("title") or "") in blob:
                item["status"] = "rejected"
                item["reject_reason"] = "the same species is already cited under its common name"
                others.append(item)
                continue
            plain.append(item)
        deduped = plain
        deduped.sort(
            key=lambda row_: (
                WHY_SCORE.get(row_.get("why") or "", 0),
                0 if re.search(r"\bextinct\b", row_.get("summary") or "", re.I) else 1,
                len(row_.get("summary") or ""),
            ),
            reverse=True,
        )
        for item in deduped[:3]:
            kept.append(item)
        for item in deduped[3:]:
            item["status"] = "rejected"
            item["reject_reason"] = "this island already has three stronger cited species"
            others.append(item)
    return kept + others


def populate_wildlife(atlas: Atlas) -> list[dict]:
    by_qid = _atlas_qids(atlas)
    alias_ids = set(ALIASES.values())
    qids = [qid for qid, island in by_qid.items() if island["id"] in alias_ids]
    rows = []
    research = _load_research()
    print(f"research notes: {len(research)}", flush=True)
    for item in research:
        built = _consider_research(item, atlas)
        if built:
            rows.append(built)
    for item in _wikidata_rows(qids):
        built = _consider_wikidata(item, atlas, by_qid)
        if built:
            rows.append(built)
    rows = _cap_islands(rows)
    accepted = [item for item in rows if item.get("status") == "accepted"]
    islands = {item["island_id"] for item in accepted}
    with_summary = sum(1 for item in accepted if len(item.get("summary") or "") > 80)
    write_candidates(
        "unusual-wildlife",
        rows,
        {
            "sources": ["wikidata", "wikipedia", "open-government"],
            "version": VERSION,
            "acceptedIslands": len(islands),
            "withParagraph": with_summary,
        },
    )
    print(f"unusual wildlife paragraphs: {with_summary} of {len(accepted)} accepted rows")
    return rows


def main(argv: list[str]) -> int:
    atlas = Atlas()
    print(f"atlas islands: {len(atlas.islands)}")
    populate_wildlife(atlas)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
