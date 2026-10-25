#!/usr/bin/env python3
"""Harvest MusicBrainz works, release groups, and linked artists.

The atlas already stores artists whose MusicBrainz area is an island. This
script does not repeat that pass. It keeps a work or release group when
MusicBrainz titles it with an island, and an artist when the disambiguation
or area names the island (a village area with an island comment, for example).

Writes data/interest/candidates/music-musicbrainz.json.
Caches responses under data/cache_musicbrainz_works/.
Does not publish, and does not edit islands.json.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
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
    search_phrases,
)
from interest_categories import (  # noqa: E402
    Atlas,
    fold,
    http_json,
    load_json,
    save_json,
    utc_now,
)

MB_API = "https://musicbrainz.org/ws/2"
MB_USER_AGENT = "IslesOfBritain/0.1 ( https://www.findmyisland.com )"
CACHE = ROOT / "data" / "cache_musicbrainz_works"
OUTPUT = ROOT / "data" / "interest" / "candidates" / "music-musicbrainz.json"

PER_ISLAND_CAP = 40
OVERALL_CAP = 500
LIMIT = 25

LANDMARKS = [
    "Isle of Skye",
    "Skye",
    "Isle of Mull",
    "Iona",
    "Staffa",
    "Islay",
    "Jura",
    "Arran",
    "Barra",
    "Tiree",
    "St Kilda",
    "Orkney",
    "Shetland",
    "Fair Isle",
    "Lindisfarne",
    "Holy Island",
    "Anglesey",
    "Isle of Man",
    "Isle of Wight",
    "Achill",
    "Inishmore",
    "Aran",
    "Skellig",
    "Lundy",
    "Sark",
    "Alderney",
    "Rathlin",
    "Tory Island",
    "Cape Clear",
    "Valentia",
    "Scilly",
    "Tresco",
]

# Phrases that must not be glued onto the archipelago record. The hit has to
# name one constituent island, and that island has to resolve.
SPECIFIC_REGIONS = {
    "orkney": "orkney",
    "shetland": "shetland",
    "scilly": "scilly",
    "aran": "aran",
    "skye": "skye",
    "holy island": "holy",
}

ARCHIPELAGO_NAMES = {"shetland", "orkney", "scilly", "isles of scilly"}

# south, west, north, east
REGION_BOXES = {
    "orkney": (58.55, -3.90, 59.50, -2.15),
    "shetland": (59.85, -2.30, 61.10, -0.55),
    "scilly": (49.84, -6.50, 50.01, -6.10),
    "aran": (53.00, -9.95, 53.20, -9.40),
}

# Famous islands just outside a box, or under 1 km².
EXTRA_MEMBERS = {
    "shetland": ("Fair Isle",),
    "scilly": ("Samson", "Gugh", "Annet"),
}

# Whole-name forms that are common words or brands. Longer names such as
# "Papa Westray" are still allowed.
BLOCK_FORMS = {
    "papa",
    "cava",
    "linga",
    "holm",
    "lamb",
    "balta",
    "oxna",
    "bigga",
    "start point",
    "green",
    "muckle",
    "little",
    "horse",
    "calf",
}

ARTIST_TYPES = {"Person", "Group", "Choir", "Orchestra"}
ARTIST_KIND = {
    "Person": "musician",
    "Group": "musical group",
    "Choir": "choir",
    "Orchestra": "orchestra",
}
SKIP_RELEASE_TYPES = {"spokenword", "interview", "audiobook", "audio drama"}
BAD_TITLE = re.compile(r"\b(karaoke|tribute|inspired by)\b", re.I)
# Bare search_phrases names that are also ordinary words. A title that only
# says the word is not a citation; the hit has to place it geographically.
COMMON_WORD_CUES = {
    "yell": ("shetland", "island", "isle", "isles"),
    "canna": ("island", "isle", "isles", "hebrides", "scotland"),
    "seil": ("island", "isle", "isles", "scotland"),
    "scarp": ("island", "isle", "isles", "harris", "scotland"),
}
PERSIAN_ARAN = re.compile(
    r"\b(persian|iran|iranian|azerbaijan|caucasus|bidgol|isfahan|farsi|tehran)\b",
    re.I,
)
TERRIER = re.compile(r"\bterriers?\b", re.I)

ARAN_ISLANDS = (
    ("Inishmore", ("Inishmore", "Inis Mór", "Inis Mor", "Árainn Mhór")),
    ("Inishmaan", ("Inishmaan", "Inis Meáin", "Inis Meain", "Inismaan")),
    ("Inisheer", ("Inisheer", "Inis Oírr", "Inis Oirr")),
)


def log(message: str) -> None:
    print(message, flush=True)


def soften(text: str) -> str:
    """Fold punctuation that would hide an otherwise exact island name."""
    text = text or ""
    text = (
        text.replace("’", "'")
        .replace("‘", "'")
        .replace("`", "'")
        .replace("–", " ")
        .replace("—", " ")
    )
    text = re.sub(r"\bst\.\s*", "st ", text, flags=re.I)
    text = text.replace(".", " ")
    return re.sub(r"\s+", " ", text).strip()


def has_phrase(phrase: str, text: str) -> bool:
    return phrase_in_text(soften(phrase), soften(text))


def lucene_quote(phrase: str) -> str:
    escaped = (phrase or "").replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def article(kind: str) -> str:
    return "an" if fold(kind)[:1] in "aeiou" else "a"


def archipelago(island: dict | None) -> bool:
    if not island:
        return False
    return fold(island.get("name") or "") in ARCHIPELAGO_NAMES


def in_box(island: dict, box: tuple[float, float, float, float]) -> bool:
    south, west, north, east = box
    return south <= island["lat"] <= north and west <= island["lng"] <= east


def forms_of(island: dict) -> list[str]:
    name = (island.get("name") or "").strip()
    forms = []
    if name:
        forms.append(name)
    base = re.sub(r"\s*\([^)]*\)", "", name).strip()
    if base and fold(base) != fold(name):
        forms.append(base)
    return forms


def mb_get(path: str) -> dict:
    """Cached MusicBrainz GET. Sleeps 1.1s only after a network call."""
    CACHE.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(path.encode("utf-8")).hexdigest()[:12]
    readable = re.sub(r"[^A-Za-z0-9._-]+", "_", path)[:120]
    cache_path = CACHE / f"{readable}_{digest}.json"
    if cache_path.exists():
        cached = load_json(cache_path, {})
        return cached if isinstance(cached, dict) else {}
    url = MB_API + path
    payload: dict = {}
    ok = False
    for attempt in range(4):
        try:
            payload = http_json(url, timeout=60, user_agent=MB_USER_AGENT)
            ok = isinstance(payload, dict)
            break
        except subprocess.CalledProcessError as exc:
            log(f"musicbrainz attempt {attempt + 1} failed: {exc.returncode} {path[:80]}")
            time.sleep(5 * (attempt + 1))
        except Exception as exc:  # noqa: BLE001 — keep the harvest moving
            log(f"musicbrainz attempt {attempt + 1} error: {exc} {path[:80]}")
            time.sleep(5 * (attempt + 1))
    if ok:
        save_json(cache_path, payload)
    else:
        payload = {}
    time.sleep(1.1)
    return payload


def mb_search(entity: str, query: str) -> dict:
    params = urllib.parse.urlencode({"query": query, "fmt": "json", "limit": str(LIMIT)})
    return mb_get(f"/{entity}?{params}")


def release_groups_for(phrase: str) -> list[dict]:
    country = (
        f"release:{lucene_quote(phrase)} AND (country:GB OR country:IE OR country:XE)"
    )
    payload = mb_search("release-group", country)
    groups = payload.get("release-groups") or []
    useful = [item for item in groups if has_phrase(phrase, item.get("title") or "")]
    if useful:
        return groups
    plain = mb_search("release-group", lucene_quote(phrase))
    return plain.get("release-groups") or []


def works_for(phrase: str) -> list[dict]:
    payload = mb_search("work", f"work:{lucene_quote(phrase)}")
    return payload.get("works") or []


def artists_for(phrase: str) -> list[dict]:
    quoted = lucene_quote(phrase)
    query = f"artist:{quoted} AND (area:{quoted} OR comment:{quoted})"
    payload = mb_search("artist", query)
    return payload.get("artists") or []


def credit_bits(item: dict) -> tuple[str, str]:
    """Artist-credit names, plus disambiguation/area strings from those artists."""
    names = []
    extras = []
    for part in item.get("artist-credit") or []:
        if not isinstance(part, dict):
            continue
        names.append(part.get("name") or "")
        artist = part.get("artist") or {}
        extras.append(artist.get("disambiguation") or "")
        for key in ("area", "begin-area"):
            area = artist.get(key) or {}
            if isinstance(area, dict):
                extras.append(area.get("name") or "")
                extras.append(area.get("disambiguation") or "")
    return " ".join(names), " ".join(extras)


def area_text(entity: dict) -> str:
    """Disambiguation and area names, split by ' | ' so a bare area can be read."""
    parts = [entity.get("disambiguation") or ""]
    for key in ("area", "begin-area", "end-area"):
        area = entity.get(key) or {}
        if isinstance(area, dict):
            parts.append(area.get("name") or "")
            parts.append(area.get("disambiguation") or "")
    return " | ".join(part for part in parts if part)


class Hit:
    def __init__(self, title: str, disambiguation: str, credit_names: str, areas: str):
        self.title = soften(title)
        self.disambiguation = soften(disambiguation)
        self.credit_names = soften(credit_names)
        self.areas = soften(areas)

    @classmethod
    def from_item(cls, item: dict) -> "Hit":
        names, credit_extra = credit_bits(item)
        areas = " ".join([area_text(item), credit_extra])
        return cls(item.get("title") or item.get("name") or "", item.get("disambiguation") or "", names, areas)

    def region_text(self) -> str:
        """Title, disambiguation, and artist-credit name. Not a bare area."""
        return " ".join([self.title, self.disambiguation, self.credit_names])

    def place_text(self) -> str:
        """Disambiguation and area strings, where an island has to be named."""
        return " ".join([self.disambiguation, self.areas])


def member_islands(atlas: Atlas, region: str) -> list[dict]:
    box = REGION_BOXES[region]
    found = []
    seen = set()
    for island in atlas.islands:
        area = island.get("area") or 0
        allowed_small = fold(island.get("name") or "") in {fold(name) for name in EXTRA_MEMBERS.get(region, ())}
        if area < 1 and not allowed_small:
            continue
        if archipelago(island):
            continue
        if not in_box(island, box) and not allowed_small:
            continue
        if island["id"] in seen:
            continue
        seen.add(island["id"])
        found.append(island)
    for name in EXTRA_MEMBERS.get(region, ()):
        island = match_island_phrase(atlas, name)
        if island and island["id"] not in seen and not archipelago(island):
            seen.add(island["id"])
            found.append(island)
    return found


def specific_member(atlas: Atlas, region: str, text: str) -> dict | None:
    """A constituent island named in the text, confirmed with match_island_phrase."""
    if region not in REGION_BOXES:
        return None
    if not has_phrase(region, text) and not (region == "scilly" and has_phrase("Isles of Scilly", text)):
        return None
    best: tuple[int, float, dict] | None = None
    for island in member_islands(atlas, region):
        if not in_box(island, REGION_BOXES[region]) and fold(island["name"]) not in {
            fold(name) for name in EXTRA_MEMBERS.get(region, ())
        }:
            continue
        for form in forms_of(island):
            if fold(form) in BLOCK_FORMS or len(fold(form)) < 3:
                continue
            if not has_phrase(form, text):
                continue
            resolved = match_island_phrase(atlas, form)
            if not resolved or resolved["id"] != island["id"]:
                continue
            rank = (len(fold(form)), resolved.get("area") or 0)
            if best is None or rank > best[:2]:
                best = (rank[0], rank[1], resolved)
    if region in {"orkney", "shetland"} and mentions_mainland(region, text):
        label = "Mainland (Orkney)" if region == "orkney" else "Mainland (Shetland)"
        resolved = match_island_phrase(atlas, label)
        if resolved:
            rank = (len(fold(label)), resolved.get("area") or 0)
            if best is None or rank > best[:2]:
                best = (rank[0], rank[1], resolved)
    return best[2] if best else None


def mentions_mainland(region: str, text: str) -> bool:
    folded = fold(soften(text))
    patterns = (
        f"mainland ({region})",
        f"mainland, {region}",
        f"{region} mainland",
        f"mainland of {region}",
        f"{region}'s mainland",
    )
    return any(pattern in folded for pattern in patterns)


def resolve_aran(atlas: Atlas, text: str) -> dict | None:
    if not has_phrase("Aran", text):
        return None
    if PERSIAN_ARAN.search(text or ""):
        return None
    irish = has_phrase("Aran Islands", text) or has_phrase("Aran Island", text) or has_phrase("Galway", text)
    best: tuple[int, float, dict] | None = None
    for canonical, aliases in ARAN_ISLANDS:
        named = False
        matched_len = 0
        for alias in aliases:
            if has_phrase(alias, text):
                named = True
                matched_len = max(matched_len, len(fold(alias)))
        if not named:
            continue
        # "Inis Mor" is also a Scottish name key. Require an Irish Aran cue
        # before accepting an alias that is not the atlas name itself.
        if not has_phrase(canonical, text) and not irish and not has_phrase("Aran", text):
            continue
        if not has_phrase(canonical, text) and not irish:
            continue
        island = match_island_phrase(atlas, canonical)
        if not island or not in_box(island, REGION_BOXES["aran"]):
            continue
        rank = (matched_len, island.get("area") or 0)
        if best is None or rank > best[:2]:
            best = (rank[0], rank[1], island)
    return best[2] if best else None


def skye_place_ok(place: str) -> bool:
    """Area or disambiguation says Skye, Scotland, or names the island."""
    if not place.strip():
        return False
    if has_phrase("Isle of Skye", place) or has_phrase("Island of Skye", place):
        return True
    folded = fold(place)
    if re.search(r"\bskye,?\s+scotland\b", folded):
        return True
    if re.search(r"\bskye\b", folded) and re.search(r"\bisland\b", folded):
        return True
    if re.search(r"\bskye boat\b", folded):
        return True
    if re.search(r"\b(from|on)\s+skye\b", folded):
        return True
    for segment in place.split("|"):
        if fold(segment.strip(" .,")) in {"skye", "isle of skye", "island of skye"}:
            return True
    return False


def resolve_skye(atlas: Atlas, hit: Hit) -> dict | None:
    blob = " ".join([hit.title, hit.place_text()])
    if TERRIER.search(blob):
        return None
    if not has_phrase("Skye", hit.title) and not has_phrase("Skye", hit.place_text()):
        return None
    titled = (
        has_phrase("Isle of Skye", hit.title)
        or has_phrase("Island of Skye", hit.title)
        or re.search(r"\bskye boat\b", fold(hit.title)) is not None
    )
    if not titled and not skye_place_ok(hit.place_text()):
        return None
    return match_island_phrase(atlas, "Isle of Skye") or match_island_phrase(atlas, "Skye")


def resolve_holy(atlas: Atlas, text: str) -> dict | None:
    if not has_phrase("Holy Island", text):
        return None
    folded = fold(soften(text))
    if has_phrase("Lindisfarne", text) or "northumberland" in folded:
        return match_island_phrase(atlas, "Lindisfarne")
    if has_phrase("Arran", text) or "firth of clyde" in folded:
        # match_island_phrase("Holy Island") is the Anglesey island. Do not
        # attach an Arran work to it. The Arran Holy Island shares the name,
        # so it cannot be selected by that call when Anglesey is larger.
        island = match_island_phrase(atlas, "Holy Island")
        if island and 55.3 <= island["lat"] <= 55.7 and -5.4 <= island["lng"] <= -4.8:
            return island
        return None
    if has_phrase("Anglesey", text) or "ynys mon" in folded or "ynys gybi" in folded or "holyhead" in folded:
        island = match_island_phrase(atlas, "Holy Island")
        if island and 53.0 <= island["lat"] <= 53.6:
            return island
        return None
    # Several atlas islands are named Holy Island. Without a place cue,
    # match_island_phrase would silently pick the largest.
    return None


def resolve_phrase(atlas: Atlas, phrase: str, hit: Hit) -> dict | None:
    """Resolve one search phrase against this hit. None means do not keep it."""
    folded = fold(phrase)
    mode = SPECIFIC_REGIONS.get(folded)
    if mode is None and archipelago(match_island_phrase(atlas, phrase)):
        if has_phrase("Shetland", phrase):
            mode = "shetland"
        elif has_phrase("Orkney", phrase):
            mode = "orkney"
        elif has_phrase("Scilly", phrase):
            mode = "scilly"
    # Title, disambiguation, artist-credit name, and area all count as hit text.
    where = " ".join([hit.region_text(), hit.place_text()])
    if mode == "orkney":
        return specific_member(atlas, "orkney", where)
    if mode == "shetland":
        return specific_member(atlas, "shetland", where)
    if mode == "scilly":
        return specific_member(atlas, "scilly", where)
    if mode == "aran":
        return resolve_aran(atlas, " ".join([hit.region_text(), hit.place_text()]))
    if mode == "skye":
        return resolve_skye(atlas, hit)
    if mode == "holy":
        return resolve_holy(atlas, " ".join([hit.region_text(), hit.place_text()]))
    island = match_island_phrase(atlas, phrase)
    if not island or archipelago(island):
        return None
    return island


def place_names_island(atlas: Atlas, island: dict, phrase: str, place: str) -> bool:
    """Artist rule: the disambiguation or area string itself names the island."""
    if not place.strip():
        return False
    folded = fold(phrase)
    if folded == "skye":
        return skye_place_ok(place)
    if folded in {"orkney", "shetland", "scilly"}:
        found = specific_member(atlas, SPECIFIC_REGIONS[folded], place)
        return bool(found and found["id"] == island["id"])
    if folded == "aran":
        found = resolve_aran(atlas, place)
        return bool(found and found["id"] == island["id"])
    if folded == "holy island":
        found = resolve_holy(atlas, place)
        return bool(found and found["id"] == island["id"])
    if raw_has_phrase(phrase, place) or raw_has_phrase(island["name"], place):
        return True
    base = re.sub(r"\s*\([^)]*\)", "", island["name"]).strip()
    if base and fold(base) not in BLOCK_FORMS and has_phrase(base, place):
        resolved = match_island_phrase(atlas, base)
        return bool(resolved and resolved["id"] == island["id"])
    return False


def bad_title(title: str) -> bool:
    return bool(BAD_TITLE.search(title or ""))


def common_word_ok(phrase: str, text: str) -> bool:
    cues = COMMON_WORD_CUES.get(fold(phrase))
    if not cues:
        return True
    return any(has_phrase(cue, text) for cue in cues)


def raw_has_phrase(phrase: str, text: str) -> bool:
    """Whole-word match that does not treat Jūra as Jura."""
    softened = soften(text)
    if any(ord(ch) > 127 for ch in phrase):
        return has_phrase(phrase, softened)
    return re.search(r"\b" + re.escape(phrase) + r"\b", softened, flags=re.I) is not None


# Single-token names that also belong to people, bands, and other languages.
# A bare title needs a British or Irish cue, or at least one other content word.
COLLIDING_PHRASES = {"iona", "jura", "islay", "staffa", "arran", "barra"}
GENERIC_TITLE_WORDS = {
    "ep",
    "album",
    "single",
    "vol",
    "volume",
    "remix",
    "mix",
    "edit",
    "version",
    "dub",
    "rmx",
    "lp",
    "cd",
    "the",
    "a",
    "an",
    "and",
}
GEO_CUES = (
    "scotland",
    "scottish",
    "ireland",
    "irish",
    "england",
    "english",
    "wales",
    "welsh",
    "hebrides",
    "highland",
    "highlands",
    "gaelic",
    "island",
    "isle",
    "orkney",
    "shetland",
    "britain",
    "british",
    "united kingdom",
    "celtic",
)


def geo_cue(text: str) -> bool:
    folded = fold(soften(text))
    for place in ("rhode island", "long island", "staten island"):
        folded = folded.replace(place, " ")
    return any(re.search(rf"\b{re.escape(cue)}\b", folded) for cue in GEO_CUES)


def cited_title(phrase: str, hit: Hit) -> bool:
    """Reject a title that only coincides with the island name."""
    if fold(phrase) not in COLLIDING_PHRASES:
        return True
    if geo_cue(hit.place_text()):
        return True
    words = re.findall(r"[a-z0-9']+", fold(soften(hit.title)))
    own = set(re.findall(r"[a-z0-9']+", fold(phrase)))
    extra = [word for word in words if word not in own and word not in GENERIC_TITLE_WORDS]
    return bool(extra)


def person_credit_only(phrase: str, item: dict) -> bool:
    """True when the island word is only the given name of a credited person."""
    title = fold(soften(item.get("title") or ""))
    if not title:
        return False
    stripped = title
    removed = False
    needle = fold(phrase)
    for part in item.get("artist-credit") or []:
        if not isinstance(part, dict):
            continue
        artist = part.get("artist") or {}
        name = fold(soften(part.get("name") or ""))
        sort = fold(soften(artist.get("sort-name") or ""))
        if not name or not re.search(rf",\s*{re.escape(needle)}\b", sort):
            continue
        if name not in stripped:
            continue
        stripped = stripped.replace(name, " ")
        removed = True
    return removed and not has_phrase(phrase, stripped)


PLACE_FOLLOW = {
    "abbey",
    "boat",
    "song",
    "songs",
    "memories",
    "memory",
    "room",
    "sound",
    "spirit",
    "book",
    "passage",
    "contemplation",
    "meditation",
    "rune",
    "ballad",
    "island",
    "isle",
}


def given_name_title(phrase: str, title: str) -> bool:
    """Iona Brown / (Iona Brown) is a person, not the island."""
    if fold(phrase) not in {"iona", "skye"}:
        return False
    softened = soften(title)
    paren = re.search(rf"\(\s*{re.escape(phrase)}\s+([A-Za-z'’.-]+)\s*\)", softened, re.I)
    if paren and fold(paren.group(1)) not in PLACE_FOLLOW:
        remaining = re.sub(rf"\(\s*{re.escape(phrase)}\s+[A-Za-z'’.-]+\s*\)", " ", softened, flags=re.I)
        if not raw_has_phrase(phrase, remaining):
            return True
    match = re.fullmatch(rf"{re.escape(phrase)}\s+([A-Za-z'’.-]+)", softened, re.I)
    return bool(match and fold(match.group(1)) not in PLACE_FOLLOW)


def jura_ok(hit: Hit) -> bool:
    """Jura the island, not the French department, a given name, or the verb 'swear'."""
    blob = fold(soften(" ".join([hit.title, hit.place_text()])))
    if re.search(r"\b(le|la|du|au)\s+jura\b", blob):
        return False
    if re.search(r"\b(quem|il|elle)\s+jura\b", blob):
        return False
    if re.search(r"\bjura\s+(soyfer|stublic)\b", blob):
        return False
    if re.search(
        r"\b(isle of jura|island of jura|paps of jura|star of jura|sound of jura|jura ceilidh|drink jura)\b",
        blob,
    ):
        return True
    if re.search(r"\bjura\b", blob) and re.search(r"\b(scotland|scottish|hebrides|whisky|whiskey|ceilidh)\b", blob):
        return True
    for segment in hit.place_text().split("|"):
        if fold(segment.strip(" .,")) in {"jura", "isle of jura", "island of jura"}:
            return True
    return False


def arran_ok(hit: Hit) -> bool:
    """Arran the island, not Catalan 'arran de' ('alongside')."""
    blob = fold(soften(" ".join([hit.title, hit.place_text()])))
    if re.search(r"\barran\s+d(e|el|els|ela)\b", blob):
        return False
    if re.search(r"\bsegueu\s+arran\b", blob):
        return False
    if re.search(r"\b(of|in|on|from)\s+arran\b", blob):
        return True
    if re.search(r"\b(isle of arran|island of arran|arran island)\b", blob):
        return True
    if re.search(r"\barran\b", blob) and re.search(r"\b(scotland|scottish|hebrides)\b", blob):
        return True
    for segment in hit.place_text().split("|"):
        if fold(segment.strip(" .,")) in {"arran", "isle of arran", "island of arran"}:
            return True
    return False


def barra_ok(hit: Hit) -> bool:
    """Barra in the Outer Hebrides, not Portuguese/Spanish 'barra' (a bar or a sandbar)."""
    blob = fold(soften(" ".join([hit.title, hit.place_text(), hit.credit_names])))
    if re.search(r"\b(la|una|para|da|na|en)\s+barra\b", blob):
        return False
    if re.search(r"\bbarra\s+(da|de|funda|pesada|tijuca|payan|taoide|edinazzu|cuber)\b", blob):
        return False
    if re.search(r"\bc[oó]digo\s+de\s+barra\b", blob):
        return False
    if re.search(r"\b(from|of)\s+barra\b", blob):
        return True
    if re.search(r"\b(isle of barra|island of barra|barra macneils?|macneil de barra)\b", blob):
        return True
    if re.search(r"\bbarra\b", blob) and re.search(
        r"\b(scotland|scottish|hebrides|waulking|gaelic|flyting)\b", blob
    ):
        return True
    for segment in hit.place_text().split("|"):
        if fold(segment.strip(" .,")) in {"barra", "isle of barra", "island of barra"}:
            return True
    return False


def st_kilda_ok(hit: Hit) -> bool:
    """St Kilda (Hirta), not the Melbourne suburb of the same name."""
    blob = fold(soften(" ".join([hit.title, hit.place_text(), hit.credit_names]))).replace("'", "")
    if re.search(
        r"\b(melbourne|australia|australian|fitzroy|esplanade|espy|foreshores?|kings cross|triple j|like a version)\b",
        blob,
    ):
        return False
    if re.search(r"\blive (in|from|at)\b", blob):
        return False
    if re.search(r"\b(still alright|love in|tapes)\b", blob):
        return False
    if fold(soften(hit.title)) in {"st kilda", "st. kilda"}:
        return False
    return bool(
        re.search(
            r"\b(lost songs|songs of|wedding|leaving|finding|vogel|sounds of|hirta|hebrides|scotland)\b",
            blob,
        )
    )


def lundy_ok(hit: Hit) -> bool:
    """Lundy the Bristol Channel island, not the surname or Lundy Road."""
    blob = fold(soften(" ".join([hit.title, hit.place_text(), hit.credit_names])))
    if re.search(r"\blundy\s+rd\b", blob):
        return False
    if re.search(r"\b(carmen|ted|charlie|clark|john|churchwell)\s+lundy\b", blob):
        return False
    if re.search(r"\b(isle of lundy|lundy island|bristol channel)\b", blob):
        return True
    if re.search(r"\blundy\b", blob) and re.search(r"\b(devon|puffin|island|isle)\b", blob):
        return True
    return False


def sark_ok(hit: Hit) -> bool:
    """Sark in the Channel Islands, not Cutty Sark or the Hungarian North Pole."""
    blob = fold(soften(" ".join([hit.title, hit.place_text(), hit.credit_names])))
    if re.search(r"\b(cutty sark|eszaki)\b", blob):
        return False
    if re.search(r"\b(isle of sark|sark island|channel island|sercq)\b", blob):
        return True
    if re.search(r"\bsark\b", blob) and re.search(r"\b(guernsey|channel islands)\b", blob):
        return True
    return False


def gigha_ok(hit: Hit) -> bool:
    """Gigha the island, not the baroque dance spelled giga/gigha."""
    blob = fold(soften(" ".join([hit.title, hit.place_text(), hit.credit_names])))
    if re.search(r"\b(from gigha|of gigha|isle of gigha|island of gigha)\b", blob):
        return True
    if re.search(r"\b(balletto|baletti|sonata|allegro)\b", blob):
        return False
    if re.search(r"\bgigha\b", blob) and re.search(r"\b(scotland|scottish|hebrides|islay)\b", blob):
        return True
    return False


def valentia_ok(hit: Hit) -> bool:
    """Valentia Island, not the Fire Emblem continent or a Spanish lyric."""
    blob = fold(soften(" ".join([hit.title, hit.place_text(), hit.credit_names])))
    if re.search(r"\b(fire emblem|nacion|vapor|old vienna)\b", blob):
        return False
    if re.search(r"\b(kerry|ireland|irish|knightstown|glanleam|valentia island)\b", blob):
        return True
    return fold(soften(hit.title)) == "valentia"


def foula_ok(hit: Hit) -> bool:
    """Foula in Shetland, not a West African or Creole group name."""
    blob = fold(soften(" ".join([hit.title, hit.place_text(), hit.credit_names])))
    if re.search(r"\b(mamfouana|lousaka|fayda)\b", blob):
        return False
    if re.search(r"\b(da foula|shaalds|of foula|isle of foula|foula reel)\b", blob):
        return True
    if re.search(r"\bfoula\b", blob) and re.search(r"\b(shetland|reel|scotland)\b", blob):
        return True
    return False


def alderney_ok(hit: Hit) -> bool:
    """Alderney in the Channel Islands, not Alderney Landing in Nova Scotia."""
    blob = fold(soften(" ".join([hit.title, hit.place_text(), hit.credit_names])))
    if re.search(r"\b(dartmouth|canada|nova scotia|alderney landing)\b", blob):
        return False
    return True


def lismore_ok(hit: Hit) -> bool:
    """Lismore in Argyll, not the cathedral town of Lismore in County Waterford."""
    blob = fold(soften(" ".join([hit.title, hit.place_text(), hit.credit_names])))
    if re.search(r"\bbells of lismore\b", blob):
        return False
    return True


def phrase_specific_ok(phrase: str, hit: Hit) -> bool:
    check = {
        "jura": jura_ok,
        "arran": arran_ok,
        "st kilda": st_kilda_ok,
        "barra": barra_ok,
        "lundy": lundy_ok,
        "sark": sark_ok,
        "gigha": gigha_ok,
        "valentia": valentia_ok,
        "foula": foula_ok,
        "alderney": alderney_ok,
        "lismore": lismore_ok,
    }.get(fold(phrase))
    if check is None:
        return True
    return check(hit)


def suite_stem(title: str, phrase: str) -> str:
    head, sep, _tail = (title or "").partition(":")
    if not sep:
        return ""
    head = head.strip()
    if head and raw_has_phrase(phrase, head):
        return fold(soften(head))
    return ""


def release_skipped(item: dict) -> bool:
    primary = fold(item.get("primary-type") or "")
    if primary in SKIP_RELEASE_TYPES:
        return True
    secondary = " ".join(item.get("secondary-types") or [])
    return fold(secondary) in SKIP_RELEASE_TYPES or any(
        fold(part) in SKIP_RELEASE_TYPES for part in (item.get("secondary-types") or [])
    )


def kind_of_release(item: dict) -> str:
    primary = (item.get("primary-type") or "release group").strip().lower()
    return primary or "release group"


def kind_of_work(item: dict) -> str:
    raw = item.get("type") or "work"
    if isinstance(raw, dict):
        raw = raw.get("name") or "work"
    kind = str(raw).strip().lower() or "work"
    return kind


def build_phrases(atlas: Atlas) -> list[str]:
    phrases = list(LANDMARKS)
    seen = {fold(phrase) for phrase in phrases}
    covered = set()
    for phrase in LANDMARKS:
        island = match_island_phrase(atlas, phrase)
        if island and not archipelago(island):
            covered.add(island["id"])
    added = 0
    for query, island in search_phrases(atlas):
        if added >= 60:
            break
        if (island.get("area") or 0) < 10:
            continue
        if island["id"] in covered:
            continue
        folded = fold(query)
        if folded in seen:
            continue
        if folded in {
            "isle of shetland",
            "island of shetland",
            "isle of orkney",
            "island of orkney",
            "isle of scilly",
            "isles of scilly",
        }:
            continue
        phrases.append(query)
        seen.add(folded)
        covered.add(island["id"])
        added += 1
    return phrases


class Harvest:
    def __init__(self, atlas: Atlas):
        self.atlas = atlas
        self.seen = set(existing_music_keys())
        self.seen_mbids: set[str] = set()
        self.rows: list[dict] = []
        self.per_island: Counter = Counter()
        self.stems: set[tuple[str, str]] = set()

    def full(self) -> bool:
        return len(self.rows) >= OVERALL_CAP

    def accept(
        self,
        *,
        island: dict,
        title: str,
        mbid: str,
        source_url: str,
        phrase: str,
        kind: str,
        entity: str,
    ) -> bool:
        title = re.sub(r"\s+", " ", title or "").strip()
        if not title or not mbid or not island or not island.get("id"):
            return False
        if bad_title(title):
            return False
        if self.per_island[island["id"]] >= PER_ISLAND_CAP or len(self.rows) >= OVERALL_CAP:
            return False
        if mbid in self.seen_mbids:
            return False
        evidence = f"MusicBrainz {entity} {mbid}: title '{title}' matched phrase '{phrase}'."
        summary = (
            f"{title} is {article(kind)} {kind} whose MusicBrainz record names {island['name']}."
        )
        built = music_row(
            island=island,
            title=title,
            source_url=source_url,
            source_title=title,
            licence="CC0",
            evidence=evidence,
            summary=summary,
            external_id=mbid,
            seen=self.seen,
        )
        if not built:
            return False
        self.rows.append(built)
        self.seen_mbids.add(mbid)
        self.per_island[island["id"]] += 1
        log(f"  + {island['name']}: {title[:80]}")
        return True

    def consider_titled(self, item: dict, phrase: str, entity: str) -> None:
        if self.full():
            return
        title = item.get("title") or ""
        mbid = item.get("id") or ""
        if not mbid or not raw_has_phrase(phrase, title):
            return
        if bad_title(title) or bad_title(item.get("disambiguation") or ""):
            return
        if person_credit_only(phrase, item) or given_name_title(phrase, title):
            return
        if entity == "release group" and release_skipped(item):
            return
        hit = Hit.from_item(item)
        if not common_word_ok(phrase, " ".join([hit.region_text(), hit.place_text()])):
            return
        if not cited_title(phrase, hit):
            return
        if not phrase_specific_ok(phrase, hit):
            return
        island = resolve_phrase(self.atlas, phrase, hit)
        if not island:
            return
        stem = suite_stem(title, phrase)
        title_key = (island["id"], fold(soften(title)))
        stem_key = (island["id"], stem) if stem else None
        if title_key in self.stems or (stem_key and stem_key in self.stems):
            return
        if entity == "release group":
            kind = kind_of_release(item)
            url = f"https://musicbrainz.org/release-group/{mbid}"
        else:
            kind = kind_of_work(item)
            url = f"https://musicbrainz.org/work/{mbid}"
        kept = self.accept(
            island=island,
            title=title,
            mbid=mbid,
            source_url=url,
            phrase=phrase,
            kind=kind,
            entity=entity,
        )
        if kept:
            self.stems.add(title_key)
            if stem_key:
                self.stems.add(stem_key)

    def consider_artist(self, artist: dict, phrase: str) -> None:
        if self.full():
            return
        atype = artist.get("type") or ""
        if atype not in ARTIST_TYPES:
            return
        name = artist.get("name") or ""
        mbid = artist.get("id") or ""
        if not name or not mbid:
            return
        if bad_title(name) or bad_title(artist.get("disambiguation") or ""):
            return
        if re.search(r"\bfictional\b", artist.get("disambiguation") or "", re.I):
            return
        place = area_text(artist)
        # A disambiguation that only repeats "Iona Brown" does not name the island.
        if re.fullmatch(rf"{re.escape(phrase)}\s+\S+", soften(name), re.I):
            place = re.sub(re.escape(soften(name)), " ", soften(place), flags=re.I)
        if not (raw_has_phrase(phrase, name) or raw_has_phrase(phrase, place)):
            return
        hit = Hit(name, "", "", place)
        if not common_word_ok(phrase, place):
            return
        if not phrase_specific_ok(phrase, hit):
            return
        island = resolve_phrase(self.atlas, phrase, hit)
        if not island:
            return
        if not place_names_island(self.atlas, island, phrase, place):
            return
        kind = ARTIST_KIND.get(atype, "musician")
        self.accept(
            island=island,
            title=name,
            mbid=mbid,
            source_url=f"https://musicbrainz.org/artist/{mbid}",
            phrase=phrase,
            kind=kind,
            entity="artist",
        )

    def save(self) -> None:
        save_json(
            OUTPUT,
            {
                "slug": "music-musicbrainz",
                "generatedAt": utc_now(),
                "sources": ["musicbrainz-works"],
                "rows": self.rows,
            },
        )


def self_check(atlas: Atlas) -> None:
    assert specific_member(atlas, "orkney", "An Orkney Wedding") is None
    westray = specific_member(atlas, "orkney", "The Westray Storm, Orkney")
    assert westray and westray["name"] == "Westray"
    papa = specific_member(atlas, "orkney", "Papa Westray, Orkney")
    assert papa and papa["name"] == "Papa Westray"
    assert specific_member(atlas, "shetland", "Shetland fiddle") is None
    unst = specific_member(atlas, "shetland", "Unst, Shetland")
    assert unst and unst["name"] == "Unst"
    mainland = specific_member(atlas, "orkney", "tunes from Mainland, Orkney")
    assert mainland and mainland["name"] == "Mainland (Orkney)"
    assert resolve_aran(atlas, "Aran Persian folk song") is None
    assert resolve_aran(atlas, "The Aran Islands sweater") is None
    inishmore = resolve_aran(atlas, "Inishmore, Aran Islands")
    assert inishmore and inishmore["name"] == "Inishmore"
    assert resolve_skye(atlas, Hit("Skye", "", "", "")) is None
    assert resolve_skye(atlas, Hit("Skye", "", "", "London")) is None
    assert resolve_skye(atlas, Hit("The Skye Boat Song", "", "", "")) is not None
    assert resolve_skye(atlas, Hit("Skye", "Skye, Scotland", "", "")) is not None
    assert resolve_skye(atlas, Hit("Skye", "", "", "Isle of Skye")) is not None
    assert resolve_skye(atlas, Hit("Skye Terrier Club", "", "", "")) is None
    assert raw_has_phrase("Jura", "Jūra") is False
    assert raw_has_phrase("Jura", "The Jura Reel") is True
    assert cited_title("Jura", Hit("Jura EP", "", "", "")) is False
    assert cited_title("Iona", Hit("Iona Memories", "", "", "")) is True
    assert cited_title("Islay", Hit("Islay", "", "", "German metal from Emsland")) is False
    assert cited_title("Iona", Hit("Iona", "", "", "Celtic folk band from the United Kingdom")) is True
    fyfe = {
        "title": "Iona Fyfe",
        "artist-credit": [
            {"name": "Iona Fyfe", "artist": {"sort-name": "Fyfe, Iona", "disambiguation": "Scottish folk singer"}}
        ],
    }
    assert person_credit_only("Iona", fyfe) is True
    assert given_name_title("Iona", "Iona Brown") is True
    assert given_name_title("Iona", "Le Quattro Stagioni (Iona Brown)") is True
    assert given_name_title("Iona", "Iona Memories") is False
    assert jura_ok(Hit("The Star of Jura", "", "", "")) is True
    assert jura_ok(Hit("Reggae From Le Jura", "", "", "")) is False
    assert jura_ok(Hit("Jura", "", "", "Jura")) is True
    assert arran_ok(Hit("The Hills of Arran", "", "", "")) is True
    assert arran_ok(Hit("Arran del mar", "", "", "")) is False
    assert arran_ok(Hit("Segueu arran", "", "", "")) is False
    assert st_kilda_ok(Hit("The Lost Songs of St Kilda", "", "", "")) is True
    assert st_kilda_ok(Hit("From St. Kilda to King's Cross", "", "", "")) is False
    assert st_kilda_ok(Hit("The Espy, St Kilda, Melbourne", "", "", "")) is False
    assert st_kilda_ok(Hit("The Lost Songs of St Kilda", "", "", "")) is True
    assert st_kilda_ok(Hit("St. Kilda", "", "", "")) is False
    assert lundy_ok(Hit("This Is Carmen Lundy", "", "", "")) is False
    assert lundy_ok(Hit("The Isle of Lundy", "", "", "")) is True
    assert sark_ok(Hit("Cutty Sark", "", "", "")) is False
    assert sark_ok(Hit("Sark Island Acid", "", "", "")) is True
    assert gigha_ok(Hit("Sonata for Flute: IV. Gigha", "", "", "")) is False
    assert gigha_ok(Hit("The Hunchback From Gigha", "", "", "")) is True
    assert foula_ok(Hit("The Shaalds of Foula", "", "", "")) is True
    assert foula_ok(Hit("Foula ak fayda", "", "", "")) is False
    assert alderney_ok(Hit("Alderney Landing, Dartmouth, NS, Canada", "", "", "")) is False
    assert barra_ok(Hit("Waulking Songs from Barra", "", "", "")) is True
    assert barra_ok(Hit("The Barra MacNeils", "", "", "")) is True
    assert barra_ok(Hit("Barra da Tijuca", "", "", "")) is False
    assert barra_ok(Hit("La barra", "", "", "")) is False
    assert barra_ok(Hit("Filosofía de barra", "", "", "")) is False
    assert resolve_holy(atlas, "Holy Island") is None
    holy = resolve_holy(atlas, "Holy Island, Anglesey")
    assert holy and abs(holy["lat"] - 53.3) < 0.5
    lindisfarne = resolve_holy(atlas, "Holy Island, Lindisfarne")
    assert lindisfarne and "Lindisfarne" in lindisfarne["name"]
    assert resolve_holy(atlas, "Holy Island, Arran") is None
    iona = match_island_phrase(atlas, "Iona")
    assert iona and iona["id"] == "iona"
    assert match_island_phrase(atlas, "Orkney") is None
    assert match_island_phrase(atlas, "Shetland") is None
    log("self-check ok")


def main() -> int:
    atlas = Atlas()
    self_check(atlas)
    phrases = build_phrases(atlas)
    log(f"atlas islands: {len(atlas.islands)}; phrases: {len(phrases)}")
    harvest = Harvest(atlas)
    try:
        for index, phrase in enumerate(phrases, start=1):
            if harvest.full():
                break
            direct = match_island_phrase(atlas, phrase)
            if (
                fold(phrase) not in SPECIFIC_REGIONS
                and direct
                and not archipelago(direct)
                and harvest.per_island[direct["id"]] >= PER_ISLAND_CAP
            ):
                log(f"[{index}/{len(phrases)}] {phrase} cap reached")
                continue
            log(f"[{index}/{len(phrases)}] {phrase} kept={len(harvest.rows)}")
            groups = sorted(release_groups_for(phrase), key=lambda item: int(item.get("score") or 0), reverse=True)
            for item in groups:
                harvest.consider_titled(item, phrase, "release group")
            for item in sorted(works_for(phrase), key=lambda item: int(item.get("score") or 0), reverse=True):
                harvest.consider_titled(item, phrase, "work")
            for item in sorted(artists_for(phrase), key=lambda item: int(item.get("score") or 0), reverse=True):
                harvest.consider_artist(item, phrase)
            harvest.save()
    finally:
        harvest.save()
    kinds = Counter()
    islands = Counter()
    for row in harvest.rows:
        islands[row["island_name"]] += 1
        url = row["source_url"]
        if "/release-group/" in url:
            kinds["release group"] += 1
        elif "/work/" in url:
            kinds["work"] += 1
        elif "/artist/" in url:
            kinds["artist"] += 1
    log(f"accepted {len(harvest.rows)}")
    log(f"kinds {dict(kinds)}")
    log(f"islands {len(islands)}")
    log(f"top {islands.most_common(15)}")
    log(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
