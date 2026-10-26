#!/usr/bin/env python3
"""Cite a local custom, festival, dance, or craft on an atlas island.

A row is kept only when an English Wikipedia article describes the practice
and a sentence places it on that island. The summary is the article's own
sentences. The picture is an open-licence photograph of the custom, or the
island's own photograph when the article has none.

Great Britain and Ireland do not count. A legend with no practice, a breed,
a book, a film, and a monastic pilgrimage do not count. Does not edit
islands.json.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from harvest_island_books import island_photo  # noqa: E402
from interest_categories import (  # noqa: E402
    MAPISH_IMAGE,
    WIKIPEDIA_API,
    _commons_records,
    _image_from_file,
    _load_media_cache,
    _sentences,
    _wiki_query,
    fold,
    row,
    wikipedia_plain,
    write_candidates,
)

SLUG = "local-traditions"
DATA = ROOT / "data"
CACHE = DATA / "cache_local_traditions"

# A sentence has to describe a practice, not merely name a place.
PRACTICE = re.compile(
    r"\b(festival|custom|tradition|celebrat\w*|dance[ds]?|woven|weaving|knit\w*|"
    r"observ\w*|held|rite|procession|bonfire|yule|christmas|parliament|mailboat|"
    r"mail boat|guga|gannet|tweed|plough\w*|assembly|wren|branchage|clameur|"
    r"skimming|gig|storytell\w*|dyke|sword|tynwald|lace|jumper|sweater|gansey|"
    r"brownie|crucifix|paint\w*|race[sd]?|king|elected|julian|championship)\b",
    re.I,
)
BLOCK = re.compile(
    r"\b(inspired by|based on|filmed|may refer to|best time to visit|how to get|"
    r"postcode|private address)\b",
    re.I,
)
SKIP_FILE = re.compile(
    r"portrait|signature|logo|icon|stamp|coin|flag|coat[_ -]?of|\bcoa\b|"
    r"locator|diagram|map|svg|disambig|wikidata|painting_by|triskelion|emblem",
    re.I,
)
WEAK = re.compile(
    r"\b(old norse|etymolog|modern name|fomorian|balor|evil eye|"
    r"inaccurate|loosely|very generally|leap year|pyramid roof|cast a spell|"
    r"best known for|population of|breeding pairs|lord's prayer)\b",
    re.I,
)
STRONG = re.compile(
    r"\b(festival|custom|tradition|celebrat\w*|held|christmas|hunt|carnival|"
    r"dance|woven|knit\w*|championship|parliament|mailboat|mail boat|dyke|"
    r"sword|jumper|sweater|gansey|tweed|skimming|races|racing|crucifix|paint\w*|plough\w*|horse\w*|"
    r"assembly|procession|law|enforceable|speciality|doughnut)\b",
    re.I,
)

# Wikipedia titles to try, the name we show, phrases the article must use,
# and the atlas islands that may receive a row. An island is kept only when
# one sentence places the practice there.
SEEDS = [
    {
        "titles": ["Up Helly Aa"],
        "name": "Up Helly Aa",
        "need": ["up helly aa", "helly"],
        "places": [
            ("mainland-shetland", ["Lerwick", "Shetland"]),
            ("osm-relation-6045406", ["Unst"]),
            ("osm-relation-8684336", ["Yell"]),
            ("osm-relation-6045499", ["Fetlar"]),
            ("osm-way-10303169", ["Whalsay"]),
            ("osm-relation-2291884", ["Bressay"]),
            ("osm-relation-8249591", ["Foula"]),
            ("fair-isle", ["Fair Isle"]),
            ("osm-way-173383816", ["Papa Stour"]),
        ],
    },
    {
        "titles": ["Kirkwall Ba game", "The Ba (game)", "Ba game"],
        "name": "The Ba",
        "need": ["kirkwall", "ba"],
        "places": [("mainland-orkney", ["Kirkwall", "Orkney"])],
    },
    {
        "titles": ["Hop-tu-Naa"],
        "name": "Hop-tu-Naa",
        "need": ["hop-tu-naa", "hop tu naa"],
        "places": [("isle-of-man", ["Isle of Man"])],
    },
    {
        "titles": ["Hunt the Wren", "Hunting the wren", "Wren Day"],
        "name": "Hunt the Wren",
        "need": ["wren"],
        "places": [("isle-of-man", ["Isle of Man"])],
    },
    {
        "titles": ["Tynwald Day"],
        "name": "Tynwald Day",
        "need": ["tynwald"],
        "places": [("isle-of-man", ["Isle of Man"])],
    },
    {
        "titles": ["Yn Chruinnaght"],
        "name": "Yn Chruinnaght",
        "need": ["chruinnaght", "manx"],
        "places": [("isle-of-man", ["Isle of Man"])],
    },
    {
        "titles": ["Papa Stour sword dance", "Papa Stour"],
        "name": "Papa Stour sword dance",
        "need": ["sword"],
        "places": [("osm-way-173383816", ["Papa Stour"])],
    },
    {
        "titles": ["Foula"],
        "name": "Old Christmas",
        "need": ["julian", "old style", "6 january", "old christmas", "yule"],
        "places": [("osm-relation-8249591", ["Foula"])],
    },
    {
        "titles": ["Fair Isle (technique)", "Fair Isle knitting"],
        "name": "Fair Isle knitting",
        "need": ["fair isle", "knit"],
        "places": [("fair-isle", ["Fair Isle"])],
    },
    {
        "titles": ["South Ronaldsay", "Festival of the Horse", "Boys' Ploughing Match"],
        "name": "Festival of the Horse",
        "need": ["horse", "horses", "plough", "ploughing"],
        "places": [("osm-relation-3601567", ["South Ronaldsay", "St Margaret's Hope"])],
    },
    {
        "titles": ["North Ronaldsay"],
        "name": "North Ronaldsay sheep dyke",
        "need": ["dyke"],
        "places": [("osm-way-4569485", ["North Ronaldsay"])],
    },
    {
        "titles": ["Orkney chair"],
        "name": "Orkney chair",
        "need": ["chair", "straw"],
        "places": [("mainland-orkney", ["Orkney"])],
    },
    {
        "titles": ["Tory Island"],
        "name": "King of Tory",
        "need": ["king"],
        "places": [("osm-way-4558807", ["Tory"])],
    },
    {
        "titles": ["Jersey"],
        "name": "Battle of Flowers",
        "need": ["battle of flowers"],
        "places": [("jersey", ["Jersey"])],
    },
    {
        "titles": ["Black butter", "Black butter (Jersey)"],
        "name": "Black butter",
        "need": ["black butter", "nier beurre"],
        "places": [("jersey", ["Jersey"])],
    },
    {
        "titles": ["Jersey"],
        "name": "Jersey wonders",
        "need": ["jersey wonders"],
        "places": [("jersey", ["Jersey"])],
    },
    {
        "titles": ["Clameur de Haro"],
        "name": "Clameur de Haro",
        "need": ["clameur", "haro"],
        "places": [
            ("jersey", ["Jersey"]),
            ("guernsey", ["Guernsey"]),
            ("osm-way-2956937", ["Sark"]),
        ],
    },
    {
        "titles": ["Viaer Marchi", "Lé Viaer Marchi"],
        "name": "Viaer Marchi",
        "need": ["viaer", "marchi"],
        "places": [("guernsey", ["Guernsey"])],
    },
    {
        "titles": ["Bean jar"],
        "name": "Bean jar",
        "need": ["bean jar"],
        "places": [("guernsey", ["Guernsey"])],
    },
    {
        "titles": ["Guernsey (clothing)"],
        "name": "Guernsey sweater",
        "need": ["knit", "gansey", "sweater", "frock"],
        "places": [("guernsey", ["Guernsey"])],
    },
    {
        "titles": ["Alderney"],
        "name": "Milk-a-Punch Sunday",
        "need": ["milk-a-punch", "milk a punch"],
        "places": [("osm-relation-12913146", ["Alderney"])],
    },
    {
        "titles": ["World Pilot Gig Championships", "Cornish pilot gig"],
        "name": "Pilot gig racing",
        "need": ["gig"],
        "places": [("scilly-st-marys", ["Isles of Scilly", "Scilly", "St Mary's"])],
    },
    {
        "titles": ["World Stone Skimming Championships", "Easdale"],
        "name": "Stone skimming",
        "need": ["skimming"],
        "places": [("osm-relation-8815463", ["Easdale"])],
    },
    {
        "titles": ["Aran jumper", "Aran sweater"],
        "name": "Aran knitting",
        "need": ["aran", "knit", "jumper", "sweater"],
        "places": [
            ("osm-relation-6045552", ["Aran Islands", "Inishmore", "Inis Mór"]),
            ("osm-relation-8158177", ["Inishmaan", "Inis Meáin"]),
            ("osm-relation-3235264", ["Inisheer", "Inis Oírr"]),
        ],
    },
    {
        "titles": ["Harris Tweed"],
        "name": "Harris Tweed",
        "need": ["tweed", "woven", "weave"],
        "places": [
            ("lewis-and-harris", ["Lewis and Harris", "Isle of Lewis", "Lewis", "Harris", "Outer Hebrides"]),
            ("osm-relation-380685", ["North Uist"]),
            ("osm-relation-380670", ["South Uist"]),
            ("osm-relation-380684", ["Benbecula"]),
            ("osm-relation-380646", ["Barra"]),
        ],
    },
    {
        "titles": ["Sula Sgeir", "Sùla Sgeir"],
        "name": "The guga hunt",
        "need": ["guga", "gannet", "gannets"],
        "places": [
            ("osm-way-20594001", ["Sula Sgeir", "Sùla Sgeir"]),
            ("lewis-and-harris", ["Lewis", "Isle of Lewis"]),
        ],
    },
    {
        "titles": ["St Kilda, Scotland"],
        "name": "St Kilda parliament",
        "need": ["parliament"],
        "places": [("st-kilda", ["St Kilda", "Hirta"])],
    },
    {
        "titles": ["St Kilda mailboat", "St Kilda, Scotland"],
        "name": "St Kilda mailboat",
        "need": ["mailboat", "mail boat", "mail-boat"],
        "places": [("st-kilda", ["St Kilda", "Hirta"])],
    },
    {
        "titles": ["Islay single malts"],
        "name": "Fèis Ìle",
        "need": ["feis", "fèis", "festival of malt"],
        "places": [("islay", ["Islay"])],
    },
    {
        "titles": ["Fèis Bharraigh", "Feis Bharraigh"],
        "name": "Fèis Bharraigh",
        "need": ["barra", "bharraigh", "feis", "fèis"],
        "places": [("osm-relation-380646", ["Barra"])],
    },
    {
        "titles": ["Scoil Acla"],
        "name": "Scoil Acla",
        "need": ["acla", "achill"],
        "places": [("osm-relation-6045364", ["Achill"])],
    },
    {
        "titles": ["Cape Clear Island"],
        "name": "Cape Clear storytelling",
        "need": ["storytell"],
        "places": [("osm-relation-8495304", ["Cape Clear", "Oileán Chléire"])],
    },
    {
        "titles": ["Omey Island"],
        "name": "Omey races",
        "need": ["races", "racing", "horse race"],
        "places": [("osm-relation-3414078", ["Omey"])],
    },
    {
        "titles": ["Davaar Island"],
        "name": "Davaar cave painting",
        "need": ["painting", "painted", "crucifix"],
        "places": [("osm-relation-10323151", ["Davaar"])],
    },
    {
        "titles": ["Seil, Scotland", "Seil"],
        "name": "Tigh an Truish",
        "need": ["truish", "trousers"],
        "places": [("osm-relation-3833751", ["Seil"])],
    },
]


def squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", fold(text or "")).strip()


def _prepared(sentence: str) -> str:
    text = squash(sentence)
    text = text.replace("harris tweed", " ")
    text = text.replace("new jersey", " ")
    text = re.sub(r"\bjersey (wonder|wonders|cattle|cow|fabric|cloth)s?\b", " ", text)
    text = re.sub(r"\bguernsey (sweater|gansey|frock|jumper)s?\b", " ", text)
    text = re.sub(r"\bshetland (pony|sheepdog|sheep dog)s?\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def has_need(text: str, need: list[str]) -> bool:
    hay = squash(text)
    return any(
        re.search(rf"(?<![a-z0-9]){re.escape(squash(phrase))}(?![a-z0-9])", hay)
        for phrase in need
        if squash(phrase)
    )


def locates(sentence: str, alias: str) -> bool:
    """The sentence puts the practice on the island, not only in the name of a craft."""
    hay = _prepared(sentence)
    needle = squash(alias)
    if not needle or not re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", hay):
        return False
    return bool(
        re.search(
            rf"(?:on|in|at|from|of|off|to|after|across|around|throughout|held|played|celebrated|"
            rf"observed|originated)\s+(?:the\s+)?(?:isle\s+of\s+|island\s+of\s+)?{re.escape(needle)}(?![a-z0-9])"
            rf"|\b(?:and|or|,)\s+{re.escape(needle)}(?![a-z0-9])"
            rf"|(?<![a-z0-9]){re.escape(needle)}\s+(?:island|isle|islanders)(?![a-z0-9])"
            rf"|^{re.escape(needle)}\s+is\b",
            hay,
        )
    )


def article_is_island(title: str, aliases: list[str]) -> bool:
    hay = squash(title)
    if re.search(
        r"\b(knitting|sheep|game|clothing|culture|breed|technique|jumper|sweater|festival|tweed|malt|whisky|chair|butter)\b",
        hay,
    ):
        return False
    for alias in aliases:
        needle = squash(alias)
        if not needle:
            continue
        if hay == needle or hay.startswith(needle + " ") or hay.endswith(" " + needle):
            return True
    return False


def clean_body(body: str) -> str:
    body = re.split(
        r"\n==\s*(See also|References|External links|Notes|Further reading|Bibliography|Gallery)\s*==",
        body,
        maxsplit=1,
        flags=re.I,
    )[0]
    body = re.sub(r"==+[^=\n]+==+", " ", body)
    # A closing quote is a sentence boundary: us." The next point.
    body = re.sub(r'([.!?])["\u201d](\s+)', r"\1\2", body)
    return body


def fetch_article(titles: list[str], need: list[str]) -> tuple[str, str]:
    for title in titles:
        text = ""
        for attempt in range(3):
            try:
                text = wikipedia_plain(title)
                break
            except RuntimeError as exc:
                print(f"fetch failed {title} ({attempt + 1}): {exc}", flush=True)
                time.sleep(25 * (attempt + 1))
        if not text:
            continue
        parts = text.split("\n", 1)
        page_title = (parts[0] if parts else title).strip()
        body = clean_body(parts[1] if len(parts) > 1 else "")
        if not body.strip():
            continue
        if re.search(r"\b(may refer to|can mean any of the following)\b", body[:400], re.I):
            continue
        first = re.split(r"(?<=[.!?])\s+", body.strip(), maxsplit=1)[0]
        if re.search(r"\bis a breed\b", first, re.I):
            continue
        if re.search(r"\bsheep\b", page_title, re.I) and re.search(r"\b(breed|originating)\b", body[:400], re.I):
            continue
        if re.search(r"\bfilm festival\b", body[:800], re.I):
            continue
        if need and not has_need(body, need):
            continue
        return page_title, body
    return "", ""


def _follows(sentence: str) -> bool:
    return bool(re.match(r"^(This|It|They|The custom|The holiday|The game|Play)\b", sentence or ""))


def _placed(sentence: str, aliases: list[str], page_title: str) -> bool:
    if any(locates(sentence, alias) for alias in aliases):
        return True
    if article_is_island(page_title, aliases):
        return True
    return bool(
        re.search(r"\b(originated|of the same name|channel island)\b", sentence, re.I)
        and any(squash(alias) in squash(page_title) for alias in aliases)
    )


def _candidate_score(sentence: str, need: list[str], aliases: list[str], page_title: str) -> int | None:
    if not has_need(sentence, need) or BLOCK.search(sentence) or WEAK.search(sentence):
        return None
    if re.search(r"\bfilm festival\b", sentence, re.I):
        return None
    if re.search(r"\b(died|his death|her death)\b", sentence, re.I) and not re.search(
        r"\b(held the post|king of|elected)\b", sentence, re.I
    ):
        return None
    if not _placed(sentence, aliases, page_title):
        return None
    score = 4
    if any(locates(sentence, alias) for alias in aliases):
        score += 10
    elif re.search(r"\b(originated|of the same name|channel island)\b", sentence, re.I):
        score += 10
    if STRONG.search(sentence):
        score += 6
    # A definition opens with the practice ("Tynwald Day is the National Day"), not "the goal is the sea".
    if re.search(r"\bis (?:a|an|the)\b", sentence[:180]) and has_need(sentence[:90], need):
        score += 8
    if sentence.count(",") >= 5:
        score -= 8
    if re.search(r"\bnamed after\b", sentence, re.I):
        score += 2
    if re.search(r"\b(died|his death|her death)\b", sentence, re.I):
        score -= 12
    return score


def build_copy(body: str, page_title: str, need: list[str], aliases: list[str]) -> tuple[str, str] | None:
    sentences = _sentences(clean_body(body))
    if not sentences:
        return None
    best: tuple[int, int, str] | None = None
    for index, sentence in enumerate(sentences):
        nxt = sentences[index + 1] if index + 1 < len(sentences) else ""
        prev = sentences[index - 1] if index else ""
        options = [sentence]
        continuation = bool(
            nxt
            and has_need(sentence, need)
            and not BLOCK.search(nxt)
            and not WEAK.search(nxt)
            and not re.search(r"\b(film festival|died)\b", nxt, re.I)
            and (
                has_need(nxt, need)
                or (_follows(nxt) and STRONG.search(nxt))
                or (index < 4 and STRONG.search(nxt))
                or re.search(r"\bnamed after\b", nxt, re.I)
            )
            and len(sentence) + len(nxt) < 520
        )
        if continuation:
            current_locates = any(locates(sentence, alias) for alias in aliases)
            next_locates = any(locates(nxt, alias) for alias in aliases)
            # Don't glue an unrelated sentence in front of the one that names the island.
            if current_locates or not next_locates or _follows(nxt) or re.search(r"\bnamed after\b", nxt, re.I):
                options.append(f"{sentence} {nxt}")
        if prev and re.search(r"\bnamed after\b", sentence, re.I) and has_need(prev, need) and PRACTICE.search(prev):
            options.append(f"{prev} {sentence}")
        for text in options:
            score = _candidate_score(text, need, aliases, page_title)
            if score is None:
                continue
            longer = best is not None and score == best[0] and index == best[1] and len(text) > len(best[2])
            if best is None or score > best[0] or (score == best[0] and index < best[1]) or longer:
                best = (score, index, text)
    if not best:
        return None
    summary = re.sub(r"\s+", " ", best[2]).strip()
    if len(summary) > 650:
        summary = summary[:630].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    tie = summary if len(summary) <= 420 else summary[:400].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    on_page = article_is_island(page_title, aliases)
    if not any(squash(alias) in squash(summary) for alias in aliases) and not on_page:
        return None
    return summary, tie


def attach_pictures(items: list[dict], islands_raw: dict) -> None:
    cache_path = CACHE / "images.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    titles = []
    for item in items:
        title = item.get("source_title") or ""
        if title and title not in titles:
            titles.append(title)
    missing = [title for title in titles if not (cache.get(fold(title)) or {}).get("images")]
    for start in range(0, len(missing), 8):
        batch = missing[start : start + 8]
        payload = _wiki_query(
            WIKIPEDIA_API,
            {
                "action": "query",
                "format": "json",
                "redirects": "1",
                "prop": "pageimages|images",
                "piprop": "name",
                "imlimit": "12",
                "titles": "|".join(batch),
            },
        )
        query = payload.get("query") or {}
        if not query:
            print("picture list skipped after a rate limit", flush=True)
            break
        redirect_of = {}
        for redir in query.get("redirects") or []:
            redirect_of.setdefault(redir.get("to"), []).append(redir.get("from"))
        for page in (query.get("pages") or {}).values():
            page_title = page.get("title") or ""
            names = [page_title, *(redirect_of.get(page_title) or [])]
            images = [img.get("title") or "" for img in page.get("images") or [] if img.get("title")]
            lead = page.get("pageimage") or ""
            if lead:
                images = [lead, *[name for name in images if name != lead]]
            record = {"title": page_title, "images": images[:12]}
            for name in names:
                if name:
                    cache[fold(name)] = record
        time.sleep(0.8)
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    media = _load_media_cache()
    filenames = []
    for item in items:
        record = cache.get(fold(item.get("source_title") or "")) or {}
        filenames.extend(record.get("images") or [])
    _commons_records(filenames, media)

    for item in items:
        record = cache.get(fold(item.get("source_title") or "")) or {}
        island_article = article_is_island(item.get("source_title") or "", [item.get("island_name") or ""])
        custom_tokens = [
            token
            for token in re.findall(r"[a-z0-9]{4,}", squash(item.get("title") or ""))
            if token not in set(re.findall(r"[a-z0-9]{4,}", squash(item.get("island_name") or "")))
            and token not in {"isle", "island", "local", "tradition"}
        ]
        chosen = ""
        best = 0
        for name in record.get("images") or []:
            if not name or MAPISH_IMAGE.search(name) or SKIP_FILE.search(name):
                continue
            if not _image_from_file(name, media):
                continue
            file_hay = squash(name)
            score = 0
            if any(len(token) >= 5 and token in file_hay for token in custom_tokens):
                score += 6
            if re.search(
                r"festival|dance|knit|galley|guiser|fire|procession|tweed|gig|flower|"
                r"wren|plough|skimm|butter|parade|torch|dyke|guga|gannet|mail|sword|"
                r"tynwald|\bba\b|race|turnip|cardigan|gansey|bean|clameur|helly",
                name,
                re.I,
            ):
                score += 4
            if score > best:
                best = score
                chosen = name if name.startswith("File:") else f"File:{name}"
        # A picture of the island's article is not a picture of the custom.
        if chosen and not (island_article and best < 4):
            item["commons_file"] = chosen
            continue
        photo = island_photo({"images": islands_raw.get(item["island_id"]) or []})
        if photo:
            item["open_image"] = photo
            item["image_note"] = "Photograph of the island"


def populate_traditions(atlas) -> list[dict]:
    missing = sorted({place[0] for seed in SEEDS for place in seed["places"] if place[0] not in atlas.by_id})
    if missing:
        raise SystemExit("missing atlas ids: " + ", ".join(missing))
    accepted: dict[tuple[str, str], dict] = {}
    rejected = []
    for seed in SEEDS:
        page_title, body = fetch_article(seed["titles"], seed["need"])
        if not body:
            rejected.append(
                row(
                    category=SLUG,
                    island_id="",
                    facet="tradition",
                    title=seed["name"],
                    source_url="",
                    licence="CC BY-SA 4.0",
                    evidence="No Wikipedia article contained the practice.",
                    status="rejected",
                    confidence="low",
                    reject_reason="no article named the practice",
                )
            )
            print(f"miss {seed['name']}", flush=True)
            continue
        source_url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(page_title.replace(" ", "_"))
        for island_id, aliases in seed["places"]:
            island = atlas.by_id[island_id]
            if (island.get("area") or 0) > 8000:
                continue
            built = build_copy(body, page_title, seed["need"], aliases)
            if not built:
                rejected.append(
                    row(
                        category=SLUG,
                        island_id=island_id,
                        island_name=island["name"],
                        facet="tradition",
                        title=seed["name"],
                        source_url=source_url,
                        source_title=page_title,
                        licence="CC BY-SA 4.0",
                        evidence=f"{page_title} does not place {seed['name']} on {island['name']}.",
                        status="rejected",
                        confidence="medium",
                        reject_reason="the article does not place the custom on this island",
                    )
                )
                continue
            summary, tie = built
            key = (island_id, fold(seed["name"]))
            if key in accepted:
                continue
            item = row(
                category=SLUG,
                island_id=island_id,
                island_name=island["name"],
                facet="tradition",
                title=seed["name"],
                source_url=source_url,
                source_title=page_title,
                licence="CC BY-SA 4.0",
                evidence=tie,
                status="accepted",
                confidence="high",
                summary=summary,
            )
            item["tie"] = tie
            accepted[key] = item
            print(f"keep {island['name']} | {seed['name']}", flush=True)
    items = list(accepted.values())
    raw = json.loads((DATA / "islands.json").read_text(encoding="utf-8"))
    images = {island.get("id"): island.get("images") or [] for island in raw if island.get("id")}
    attach_pictures(items, images)
    rows = items + rejected
    write_candidates(
        SLUG,
        rows,
        {
            "sources": ["english-wikipedia"],
            "rule": (
                "The English Wikipedia article describes the custom and places it on the island. "
                "The summary is the article's own sentences. "
                "A legend with no practice, a breed, a book, a film, and a monastic pilgrimage do not count."
            ),
        },
    )
    pictured = sum(1 for item in items if item.get("commons_file") or item.get("open_image"))
    print(
        f"accepted {len(items)} on {len({item['island_id'] for item in items})} islands, {pictured} with a picture",
        flush=True,
    )
    return rows


def main() -> int:
    from interest_categories import Atlas

    atlas = Atlas()
    populate_traditions(atlas)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
