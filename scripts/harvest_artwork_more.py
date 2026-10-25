#!/usr/bin/env python3
"""Harvest cited artworks from Wellcome Collection and Yale LUX.

Those catalogues are outside the Wikidata, Commons, Met, Cleveland,
Art Institute of Chicago, V&A, and National Gallery of Art passes.
A source is queried only after its own documentation states CC0, CC BY,
CC BY-SA, or OGL. Images are attached only when the record marks them
for reuse without NC or ND.

If Wellcome and Yale together accept fewer than 30 rows, Minneapolis
Institute of Art metadata is added only when their open-data README
states CC0. Mia images are not CC0 (non-commercial image policy) and
are not copied.

Writes only:
  data/interest/candidates/artwork-more.json
  data/cache_artwork_more/**

Does not publish, and does not edit islands.json.
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

from interest_categories import (  # noqa: E402
    Atlas,
    fold,
    http_json,
    load_json,
    save_json,
    utc_now,
)
from artwork_harvest_common import (  # noqa: E402
    artwork_row,
    existing_artwork_keys,
    match_island_phrase,
    phrase_in_text,
    search_phrases,
)
from ingest_sources import name_key  # noqa: E402

CACHE = ROOT / "data" / "cache_artwork_more"
OUT = ROOT / "data" / "interest" / "candidates" / "artwork-more.json"
UA = "isles-of-britain/0.1 (artwork-more; research)"

SLEEP_S = 0.4
INSPECT_PER_QUERY = 20
PER_ISLAND = 40
OVERALL = 400
EXTRA_PHRASES = 50
MIN_EXTRA_AREA = 20
MIA_THRESHOLD = 30

WELLCOME_DOCS = "https://developers.wellcomecollection.org/docs/catalogue"
WELLCOME_SEARCH = "https://api.wellcomecollection.org/catalogue/v2/works"
YALE_SEARCH = "https://lux.collections.yale.edu/api/search/item"
YALE_OPEN = (
    "https://lux-cms.collections.yale.edu/jsonapi/node/page/"
    "d1883671-2d9e-4d9c-a50c-faa3c2281ec7"
)
MIA_README = "https://raw.githubusercontent.com/artsmia/collection/main/readme.md"
MIA_SEARCH = "https://search.artsmia.org/"

LANDMARKS = [
    "Fingal's Cave",
    "Staffa",
    "Iona",
    "Lindisfarne",
    "Holy Island",
    "St Michael's Mount",
    "Anglesey",
    "Isle of Skye",
    "Isle of Mull",
    "Islay",
    "Jura",
    "Arran",
    "St Kilda",
    "Skellig",
    "Inishmore",
    "Achill",
    "Lundy",
    "Isle of Wight",
    "Isle of Man",
    "Ailsa Craig",
    "Bass Rock",
    "Orkney",
    "Shetland",
    "Scilly",
    "Sark",
]

# Bare archipelago or country words. A hit is kept only when one qualified
# island name in the text resolves through match_island_phrase.
GROUP_WORDS = {"orkney", "shetland", "jersey", "man", "scilly", "skellig"}
GROUP_KEYS = {"orkney", "shetland", "jersey", "man"}

YALE_CLASSES = [
    "painting",
    "drawing",
    "drawings",
    "print",
    "prints",
    "sculpture",
    "watercolor",
    "watercolour",
    "watercolors",
    "etching",
    "etchings",
    "engraving",
    "engravings",
]

ART_WORD = re.compile(
    r"\b(paintings?|drawings?|watercolours?|watercolors?|prints?|"
    r"etchings?|engravings?|aquatints?|lithographs?|woodcuts?|"
    r"mezzotints?|drypoints?|intaglios?|sculptures?|sketches?)\b",
    re.I,
)
PHOTO_WORD = re.compile(
    r"\b(photographs?|photogravures?|daguerreotypes?|albumen|"
    r"gelatin silver|carte de visite|collodion)\b",
    re.I,
)
PRINT_OR_DRAWING = re.compile(
    r"\b(prints?|drawings?|paintings?|watercolours?|watercolors?|"
    r"etchings?|engravings?|aquatints?|lithographs?|woodcuts?|"
    r"mezzotints?|sketches?)\b",
    re.I,
)
QUALIFIED_RE = re.compile(
    r"\b(?:isle of|island of|ynys|eilean|inis|inish|oilean)\s+"
    r"[a-z0-9'’\-]+(?:\s+[a-z0-9'’\-]+){0,5}",
    re.I,
)
HOLY_LINDIS = ("lindisfarne", "northumberland", "farne")
HOLY_ANGLES = ("anglesey", "ynys gybi", "holyhead", "caergybi", "ynys mon")


def soften(text: str) -> str:
    text = (text or "").replace("’", "'").replace("‘", "'").replace("`", "'")
    text = text.replace("´", "'")
    return re.sub(r"\bSt\.", "St", text, flags=re.I)


def phrase_variants(phrase: str) -> list[str]:
    base = soften(phrase).strip()
    variants = [base]
    saint = re.sub(r"\bSt\b", "Saint", base)
    if saint.lower() != base.lower():
        variants.append(saint)
    plain = base.replace("'", "")
    if plain.lower() != base.lower():
        variants.append(plain)
    return variants


def has_phrase(phrase: str, text: str) -> bool:
    """Whole-word match. Accent-folding must not turn tirée into Tiree, and a
    letter restored in square brackets must not become its own word."""
    cleaned = soften(text)
    lowered = cleaned.lower()
    for variant in phrase_variants(phrase):
        if not phrase_in_text(variant, cleaned):
            continue
        pattern = r"\b" + re.escape(variant.lower()) + r"\b"
        for match in re.finditer(pattern, lowered):
            before = lowered[match.start() - 1] if match.start() else ""
            after = lowered[match.end() : match.end() + 1]
            if before == "[" or after == "]":
                continue
            return True
    return False


# Bare names that also mean somewhere else. A hit needs a local cue, or the
# qualified island name already in the phrase.
PLACE_CUES = {
    "jura": ("isle", "island", "hebrides", "argyll", "scotland", "paps", "craighouse", "askaig", "loch", "castle", "sound"),
    "barra": ("isle", "isles", "island", "hebrides", "castlebay", "scotland", "eriskay", "vatersay"),
    "tiree": ("isle", "island", "hebrides", "scotland", "inner hebrides"),
}
FOREIGN_PLACE = re.compile(
    r"\b(s\.?\s*dak|south dakota|dakotas?|new jersey|n\.\s*j|monmouth|"
    r"florida|fla|australia|melbourne|utrecht|ultrecht)\b",
    re.I,
)
MODERN_MAP = re.compile(
    r"british geological survey|pathfinder series|ordnance survey|"
    r"cartographic material|hydrographic|1:\s?25[\s,]*000|1:\s?50[\s,]*000|"
    r"1:\s?250[\s,]*000|sea bed sediments|quaternary geology|solid geology|"
    r"carte routi[eè]re|roadmap of|series of great britain",
    re.I,
)
ANGLESEY_PLACES = ("plas newydd", "menai", "beaumaris", "baron hill", "holyhead", "wales")
PEERAGE_TITLE = (
    r"\b(?:earl|marquis|marquess|duke|lord|baron|baroness|viscount|count|comte|comit[ie])"
    r"\s+(?:of\s+)?"
)


def has_cue(text: str, cues: tuple[str, ...]) -> bool:
    lowered = soften(text).lower()
    return any(cue in lowered for cue in cues)


def place_ok(phrase: str, title: str, description: str, island: dict) -> bool:
    blob = f"{title}\n{description}"
    folded = soften(phrase).lower()
    key = name_key(island.get("name") or "")
    if MODERN_MAP.search(title) or MODERN_MAP.search(description[:180]):
        return False
    if re.search(r"\b(letterpress|cartographic material|volume|mappe|maps?)\b", title, re.I):
        return False
    if not has_phrase(phrase, title):
        window = snippet(description, phrase)
        if re.search(
            r"not to proceed|less convincingly|third possibility|\bpossibly\b|\bperhaps\b",
            window,
            re.I,
        ):
            return False
    if FOREIGN_PLACE.search(blob):
        cornish = re.search(r"\b(cornwall|marazion|penzance)\b", blob, re.I)
        hebridean = re.search(r"\b(scotland|hebrides|cathedral|abbey)\b", blob, re.I)
        if "michael" in folded and cornish:
            pass
        elif key == "iona" and hebridean and not re.search(r"dakota|n\.\s*j\b|new jersey", blob, re.I):
            pass
        else:
            return False
    cues = PLACE_CUES.get(folded) or PLACE_CUES.get(key)
    if cues and not qualified_phrase(phrase) and not has_cue(blob, cues):
        return False
    if folded in {"arran", "anglesey", "st kilda", "saint kilda"} or key in {"arran", "anglesey", "st kilda"}:
        stripped = re.sub(PEERAGE_TITLE + re.escape(soften(phrase)), " ", soften(blob), flags=re.I)
        named = has_phrase(phrase, stripped) or has_phrase(island.get("name") or "", stripped)
        if not named and not (key == "anglesey" and has_cue(blob, ANGLESEY_PLACES)):
            return False
    if key == "st kilda" and re.search(r"\bvictoria\b", blob, re.I) and re.search(r"\baustralia\b", blob, re.I):
        return False
    if folded == "arran" or key == "arran":
        if re.search(r"\b(fla|florida)\b", blob, re.I):
            return False
        if re.search(r"\bcomit[ie]\s+arran\b", blob, re.I) and not has_cue(
            blob, ("isle", "island", "scotland", "goatfell", "clyde", "loch")
        ):
            return False
    return True


def cache_path(kind: str, url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
    return CACHE / kind / f"{digest}.json"


def cached_json(kind: str, url: str) -> dict:
    path = cache_path(kind, url)
    if path.exists():
        payload = load_json(path, None)
        if isinstance(payload, dict):
            return payload
    try:
        payload = http_json(url, timeout=90, user_agent=UA)
    except Exception as exc:
        payload = {"_error": f"{type(exc).__name__}: {exc}"[:400], "_url": url}
    if not isinstance(payload, dict):
        payload = {"_error": "response was not a JSON object", "_url": url, "value": payload}
    save_json(path, payload)
    time.sleep(SLEEP_S)
    return payload


def cached_text(name: str, url: str) -> str:
    dest = CACHE / "docs" / name
    if dest.exists() and dest.stat().st_size > 80:
        return dest.read_text(encoding="utf-8", errors="replace")
    raw = subprocess.check_output(
        ["curl", "-fsSL", "--max-time", "60", "-A", UA, "-H", "Accept: application/json, text/html", url]
    )
    text = raw.decode("utf-8", errors="replace")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    time.sleep(SLEEP_S)
    return text


def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<script.*?>.*?</script>", " ", raw)
    raw = re.sub(r"(?is)<style.*?>.*?</style>", " ", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(raw)).strip()


def sentence_with(text: str, pattern: str) -> str:
    plain = html_to_text(text) if "<" in text[:400] else re.sub(r"\s+", " ", text)
    match = re.search(pattern, plain, re.I)
    if not match:
        return ""
    left = max(plain.rfind(".", 0, match.start()), plain.rfind(";", 0, match.start()))
    right = plain.find(".", match.end())
    end = right + 1 if right != -1 else min(len(plain), match.end() + 220)
    return plain[left + 1 : end].strip()[:500]


def snippet(text: str, phrase: str) -> str:
    cleaned = re.sub(r"\s+", " ", soften(html_to_text(text) if "<" in (text or "") else (text or ""))).strip()
    match = None
    for variant in phrase_variants(phrase):
        match = re.search(r"\b" + re.escape(variant) + r"\b", cleaned, re.I)
        if match:
            break
    if not match:
        return cleaned[:240]
    start = max(0, match.start() - 90)
    end = min(len(cleaned), match.end() + 90)
    return cleaned[start:end].strip()


def qualified_phrase(phrase: str) -> bool:
    return bool(re.search(r"\b(isle of|island of|ynys|eilean|inis|inish|oilean)\b", phrase or "", re.I))


def qualified_islands(atlas: Atlas, text: str) -> list[dict]:
    """Qualified island names actually written in the text, one island each."""
    found: dict[str, dict] = {}
    for match in QUALIFIED_RE.finditer(soften(text)):
        words = match.group(0).split()
        island = None
        for end in range(len(words), 1, -1):
            candidate = " ".join(words[:end])
            island = match_island_phrase(atlas, candidate)
            if island:
                break
        if island:
            found[island["id"]] = island
    return list(found.values())


def holy_island(atlas: Atlas, text: str) -> dict | None:
    folded = soften(text).lower()
    lindisfarne = any(phrase_in_text(cue, folded) for cue in HOLY_LINDIS)
    anglesey = any(phrase_in_text(cue, folded) for cue in HOLY_ANGLES)
    if lindisfarne and not anglesey:
        return match_island_phrase(atlas, "Lindisfarne")
    if anglesey and not lindisfarne:
        return match_island_phrase(atlas, "Holy Island")
    return None


def island_for_hit(atlas: Atlas, phrase: str, text: str) -> dict | None:
    """One atlas island for this hit, or None when the name is not secure."""
    if not text or not has_phrase(phrase, text):
        return None
    folded = soften(phrase).lower()
    if folded == "man":
        return None
    if folded in {"fingal's cave", "fingals cave"}:
        return match_island_phrase(atlas, "Staffa")
    if folded == "holy island":
        return holy_island(atlas, text)
    if folded in GROUP_WORDS:
        found = qualified_islands(atlas, text)
        if len(found) != 1:
            return None
        island = found[0]
        if name_key(island["name"]) == "man" and not has_phrase("Isle of Man", text):
            return None
        return island

    island = match_island_phrase(atlas, phrase)
    if island is None:
        saint = re.sub(r"\bSt\b", "Saint", soften(phrase))
        if saint.lower() != soften(phrase).lower():
            island = match_island_phrase(atlas, saint)
    if island is None:
        return None
    key = name_key(island["name"])
    if key in GROUP_KEYS or folded in GROUP_WORDS:
        if key == "man" or folded == "man":
            if not has_phrase("Isle of Man", text):
                return None
        elif not qualified_phrase(phrase) or not has_phrase(phrase, text):
            found = qualified_islands(atlas, text)
            if len(found) != 1 or found[0]["id"] != island["id"]:
                return None
    return island


def art_ok(*parts: str, allow_sculpture: bool) -> bool:
    blob = " ".join(part or "" for part in parts)
    title = parts[0] if parts else ""
    if PHOTO_WORD.search(blob) and not PRINT_OR_DRAWING.search(title):
        return False
    if not ART_WORD.search(blob):
        return False
    if not allow_sculpture and re.search(r"\bsculptures?\b", blob, re.I):
        if not re.search(
            r"\b(paintings?|drawings?|prints?|etchings?|engravings?|watercolours?|watercolors?)\b",
            blob,
            re.I,
        ):
            return False
    return True


def object_kind(*parts: str) -> str:
    blob = " ".join(part or "" for part in parts).lower()
    for kind in (
        "watercolour",
        "watercolor",
        "etching",
        "engraving",
        "aquatint",
        "lithograph",
        "woodcut",
        "mezzotint",
        "sculpture",
        "drawing",
        "sketch",
        "print",
        "painting",
    ):
        if kind in blob:
            if kind == "sketch":
                return "drawing"
            return kind
    return "artwork"


def open_image_licence(licence_id: str, label: str) -> str:
    """Short licence name when reuse is allowed without NC or ND."""
    token = (licence_id or "").strip().lower()
    pretty = label or ""
    blob = f"{token} {pretty}".lower()
    if re.search(r"\bnc\b|non-?commercial|\bnd\b|no-?deriv", blob):
        return ""
    if token in {"cc0", "cc-zero", "cc-0"} or re.search(r"\bcc0\b|cc-0|creative commons zero", blob):
        return "CC0"
    if "by-sa" in token or "by-sa" in blob or "attribution-sharealike" in blob:
        return "CC BY-SA"
    if token in {"cc-by", "cc-by-4.0"} or re.search(r"\bcc by\b|attribution 4", blob):
        return "CC BY"
    if token in {"pdm", "public-domain"} or "public domain" in blob:
        return "Public Domain Mark"
    if token == "ogl" or "open government licence" in blob:
        return "OGL"
    return ""


def build_queries(atlas: Atlas) -> tuple[list[str], list[str]]:
    queries: list[str] = []
    unresolved: list[str] = []
    seen: set[str] = set()

    def add(phrase: str, must_resolve: bool) -> None:
        token = soften(phrase).lower()
        if not token or token in seen:
            return
        if must_resolve:
            island = match_island_phrase(atlas, phrase)
            if island is None:
                saint = re.sub(r"\bSt\b", "Saint", soften(phrase))
                if saint.lower() != soften(phrase).lower():
                    island = match_island_phrase(atlas, saint)
            if island is None:
                return
            key = name_key(island["name"])
            folded = soften(phrase).lower()
            if folded in GROUP_WORDS or key in GROUP_KEYS:
                if key == "man" and not has_phrase("Isle of Man", phrase):
                    return
                if not qualified_phrase(phrase) and "(" not in phrase:
                    return
            if "mainland" in folded and "orkney" not in folded and "shetland" not in folded and "(" not in phrase:
                return
        elif token in GROUP_WORDS or token in {"fingal's cave", "holy island", "skellig"}:
            # Searched on purpose. The island is decided per hit.
            pass
        elif match_island_phrase(atlas, phrase) is None:
            saint = re.sub(r"\bSt\b", "Saint", soften(phrase))
            if match_island_phrase(atlas, saint) is None and token not in {"fingal's cave"}:
                unresolved.append(phrase)
                if token not in {"skellig", "scilly"}:
                    return
        seen.add(token)
        queries.append(phrase)

    for phrase in LANDMARKS:
        add(phrase, must_resolve=False)
    extra = 0
    for phrase, island in search_phrases(atlas):
        if extra >= EXTRA_PHRASES:
            break
        if (island.get("area") or 0) < MIN_EXTRA_AREA:
            continue
        if soften(phrase).lower() in seen:
            continue
        before = len(queries)
        add(phrase, must_resolve=True)
        if len(queries) > before:
            extra += 1
    return queries, unresolved


def consider(
    atlas: Atlas,
    phrase: str,
    title: str,
    description: str,
    kind_bits: tuple[str, ...],
    seen: set,
    per_island: dict,
    rows: list[dict],
    source: dict,
    allow_sculpture: bool,
) -> bool:
    if len(rows) >= OVERALL:
        return False
    blob = f"{title}\n{description}"
    island = island_for_hit(atlas, phrase, blob)
    if not island:
        return False
    if per_island[island["id"]] >= PER_ISLAND:
        return False
    if not art_ok(title, *kind_bits, allow_sculpture=allow_sculpture):
        return False
    if re.search(r"\bmaps\b", " ".join(kind_bits), re.I):
        return False
    if not place_ok(phrase, title, description, island):
        return False
    field = "Title" if has_phrase(phrase, title) else "Description"
    quoted = title if field == "Title" else description
    institution = source["institution"]
    evidence = f"{field}: {snippet(quoted, phrase)} — {institution}"
    kind = object_kind(title, description, *kind_bits)
    where = institution if institution.lower().endswith("collection") else f"the {institution} collection"
    summary = f"{title} is a {kind} in {where}; the record names {island['name']}."
    built = artwork_row(
        island=island,
        title=title,
        source_url=source["source_url"],
        source_title=title,
        licence=source["licence"],
        evidence=evidence,
        summary=summary,
        external_id=source["external_id"],
        open_image=source.get("image"),
        seen=seen,
    )
    if not built:
        return False
    rows.append(built)
    per_island[island["id"]] += 1
    return True


def confirm_wellcome() -> tuple[bool, str, str]:
    try:
        raw = cached_text("wellcome-catalogue.html", WELLCOME_DOCS)
    except subprocess.CalledProcessError as exc:
        return False, "", f"Wellcome catalogue docs were not fetched ({exc})."
    plain = html_to_text(raw)
    sentence = sentence_with(plain, r"data that has been created by us|CC0|CC BY")
    if re.search(r"created by us", plain, re.I) and re.search(r"\bCC0\b", plain):
        return True, "CC0", sentence
    if re.search(r"creative commons attribution 4\.0|\bcc by 4\.0\b|\bcc by\b(?!-nc)(?!-nd)", plain, re.I):
        return True, "CC BY", sentence
    return False, "", sentence


def confirm_yale() -> tuple[bool, str, str]:
    payload = cached_json("docs", YALE_OPEN)
    if payload.get("_error"):
        return False, "", payload["_error"]
    body = ((payload.get("data") or {}).get("attributes") or {}).get("body") or ""
    if not isinstance(body, str):
        body = str(body)
    plain = html_to_text(body)
    sentence = sentence_with(plain, r"CC-0|CC0|no rights reserved")
    if re.search(r"\bcc-0\b|\bcc0\b", plain, re.I) and re.search(r"metadata", plain, re.I):
        return True, "CC0", sentence
    return False, "", sentence


def confirm_mia() -> tuple[bool, str, str, str]:
    try:
        raw = cached_text("mia-readme.md", MIA_README)
    except subprocess.CalledProcessError as exc:
        return False, "", f"Mia README was not fetched ({exc}).", ""
    plain = html_to_text(raw)
    sentence = sentence_with(plain, r"CC0|Creative Commons Zero")
    images = sentence_with(plain, r"Images aren't included|non-commercial")
    if re.search(r"\bcc0\b|creative commons zero", plain, re.I) and re.search(r"metadata", plain, re.I):
        return True, "CC0", sentence, images
    return False, "", sentence, images


def wellcome_text(work: dict) -> tuple[str, str, list[str]]:
    title = soften(work.get("title") or "")
    alts = []
    for alt in work.get("alternativeTitles") or []:
        if isinstance(alt, str):
            alts.append(alt)
        elif isinstance(alt, dict):
            alts.append(alt.get("title") or alt.get("label") or "")
    bits = [" ".join(alts), work.get("physicalDescription") or "", work.get("lettering") or ""]
    for note in work.get("notes") or []:
        if not isinstance(note, dict):
            continue
        note_type = note.get("noteType") or {}
        label = (note_type.get("label") or note_type.get("id") or "").lower()
        if "reference" in label or "citation" in label or "copyright" in label:
            continue
        contents = note.get("contents") or []
        if isinstance(contents, str):
            contents = [contents]
        bits.extend(str(part) for part in contents)
    genres = []
    for genre in work.get("genres") or []:
        if isinstance(genre, dict):
            genres.append(genre.get("label") or "")
    work_type = work.get("workType") or {}
    if isinstance(work_type, dict):
        genres.append(work_type.get("label") or "")
    description = soften(" ".join(bits))
    return re.sub(r"\s+", " ", title).strip(), re.sub(r"\s+", " ", description).strip(), genres


def wellcome_image(work: dict) -> dict | None:
    thumb = work.get("thumbnail") or {}
    if not isinstance(thumb, dict):
        return None
    licence = thumb.get("license") or {}
    if not isinstance(licence, dict):
        return None
    short = open_image_licence(licence.get("id") or "", licence.get("label") or "")
    url = (thumb.get("url") or "").strip()
    if not short or not url.startswith("http"):
        return None
    return {
        "thumbUrl": url,
        "licence": short,
        "attribution": "Wellcome Collection",
    }


def harvest_wellcome(atlas, queries, seen, per_island, licence: str) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    stats = {"inspected": 0, "accepted": 0, "queries": 0, "errors": 0}
    for phrase in queries:
        if len(rows) >= OVERALL:
            break
        stats["queries"] += 1
        params = urllib.parse.urlencode(
            {
                "query": phrase,
                "pageSize": INSPECT_PER_QUERY,
                "workType": "k",
                "include": "genres",
            }
        )
        payload = cached_json("wellcome", f"{WELLCOME_SEARCH}?{params}")
        if payload.get("_error"):
            stats["errors"] += 1
            print(f"wellcome error {phrase}: {payload['_error'][:160]}", flush=True)
            continue
        inspected = 0
        accepted = 0
        for work in (payload.get("results") or [])[:INSPECT_PER_QUERY]:
            if inspected >= INSPECT_PER_QUERY or len(rows) >= OVERALL:
                break
            inspected += 1
            stats["inspected"] += 1
            title, description, genres = wellcome_text(work)
            if not title:
                continue
            work_id = work.get("id") or ""
            medium = work.get("physicalDescription") or ""
            source = {
                "institution": "Wellcome Collection",
                "licence": licence,
                "source_url": f"https://wellcomecollection.org/works/{work_id}",
                "external_id": f"wellcome:{work_id}",
                "image": wellcome_image(work),
            }
            if consider(
                atlas,
                phrase,
                title,
                description,
                (medium, " ".join(genres)),
                seen,
                per_island,
                rows,
                source,
                allow_sculpture=False,
            ):
                accepted += 1
                stats["accepted"] += 1
        print(
            f"wellcome {phrase!r} inspected {inspected} accepted {accepted} total {len(rows)}",
            flush=True,
        )
    return rows, stats


def yale_query_url(phrase: str) -> str:
    query = {
        "AND": [
            {"text": phrase, "_lang": "en"},
            {
                "OR": [
                    {"classification": {"name": name, "_lang": "en"}}
                    for name in YALE_CLASSES
                ]
            },
        ]
    }
    encoded = urllib.parse.urlencode(
        {"q": json.dumps(query, separators=(",", ":")), "page": 1, "pageLength": INSPECT_PER_QUERY}
    )
    return f"{YALE_SEARCH}?{encoded}"


def yale_parts(obj: dict) -> tuple[str, str, list[str], str]:
    title = obj.get("_label") or ""
    classes = [item.get("_label") or "" for item in obj.get("classified_as") or [] if isinstance(item, dict)]
    descriptions = []
    credit = ""
    for ident in obj.get("identified_by") or []:
        if not isinstance(ident, dict):
            continue
        if ident.get("type") == "Name" and ident.get("content"):
            descriptions.append(ident.get("content") or "")
    for note in obj.get("referred_to_by") or []:
        if not isinstance(note, dict):
            continue
        labels = " ".join(
            (item.get("_label") or "") for item in (note.get("classified_as") or []) if isinstance(item, dict)
        )
        content = note.get("content") or ""
        if re.search(r"credit line", labels, re.I) and content and not credit:
            credit = content
        if re.search(r"dimension|signature|citation|provenance|access statement|credit line", labels, re.I):
            continue
        if re.search(r"material|gallery label|description|catalog|text|abstract", labels, re.I) or not labels:
            descriptions.append(content)
            if re.search(r"material", labels, re.I):
                classes.append(content)
    title = re.sub(r"\s+", " ", soften(title)).strip()
    description = re.sub(r"\s+", " ", soften(" ".join(descriptions))).strip()
    return title, description, classes, credit


def yale_image(obj: dict) -> dict | None:
    """Attach a thumbnail only when the record itself states an open image licence."""
    rights = []
    for note in obj.get("referred_to_by") or []:
        if not isinstance(note, dict):
            continue
        labels = " ".join(
            (item.get("_label") or "") for item in (note.get("classified_as") or []) if isinstance(item, dict)
        )
        if re.search(r"right|licen|copyright|reuse", labels, re.I):
            rights.append(note.get("content") or "")
    blob = " ".join(rights)
    short = open_image_licence("", blob) if blob else ""
    if not short:
        return None
    thumb = ""
    for visual in obj.get("representation") or []:
        if not isinstance(visual, dict):
            continue
        for digital in visual.get("digitally_shown_by") or []:
            if not isinstance(digital, dict):
                continue
            for point in digital.get("access_point") or []:
                if isinstance(point, dict) and str(point.get("id") or "").startswith("http"):
                    thumb = point["id"]
                    break
            if thumb:
                break
        if thumb:
            break
    if not thumb:
        return None
    return {"thumbUrl": thumb, "licence": short, "attribution": "Yale Collections"}


def yale_item_url(data_url: str) -> str:
    match = re.search(r"/object/([0-9a-f-]{16,})", data_url or "", re.I)
    if not match:
        return data_url
    return f"https://lux.collections.yale.edu/view/item/{match.group(1)}"


def harvest_yale(atlas, queries, seen, per_island, licence: str) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    stats = {"inspected": 0, "accepted": 0, "queries": 0, "errors": 0}
    for phrase in queries:
        if len(rows) >= OVERALL:
            break
        stats["queries"] += 1
        payload = cached_json("yale-search", yale_query_url(phrase))
        if payload.get("_error"):
            stats["errors"] += 1
            print(f"yale search error {phrase}: {payload['_error'][:160]}", flush=True)
            continue
        inspected = 0
        accepted = 0
        for item in (payload.get("orderedItems") or [])[:INSPECT_PER_QUERY]:
            if inspected >= INSPECT_PER_QUERY or len(rows) >= OVERALL:
                break
            data_url = item.get("id") if isinstance(item, dict) else ""
            if not data_url:
                continue
            obj = cached_json("yale-object", data_url)
            inspected += 1
            stats["inspected"] += 1
            if obj.get("_error"):
                stats["errors"] += 1
                continue
            title, description, classes, credit = yale_parts(obj)
            if not title:
                continue
            institution = credit.strip() if credit and "Yale" in credit else "Yale Collections (LUX)"
            if len(institution) > 140:
                institution = "Yale Collections (LUX)"
            source = {
                "institution": institution,
                "licence": licence,
                "source_url": yale_item_url(data_url),
                "external_id": f"lux:{data_url.rstrip('/').split('/')[-1]}",
                "image": yale_image(obj),
            }
            if consider(
                atlas,
                phrase,
                title,
                description,
                (title, " ".join(classes)),
                seen,
                per_island,
                rows,
                source,
                allow_sculpture=True,
            ):
                accepted += 1
                stats["accepted"] += 1
        print(
            f"yale {phrase!r} inspected {inspected} accepted {accepted} total {len(rows)}",
            flush=True,
        )
    return rows, stats


def harvest_mia(atlas, queries, seen, per_island, licence: str) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    stats = {"inspected": 0, "accepted": 0, "queries": 0, "errors": 0}
    for phrase in queries:
        if len(rows) >= OVERALL:
            break
        stats["queries"] += 1
        url = MIA_SEARCH + urllib.parse.quote(phrase) + f"?size={INSPECT_PER_QUERY}"
        payload = cached_json("mia", url)
        if payload.get("_error"):
            stats["errors"] += 1
            print(f"mia error {phrase}: {payload['_error'][:160]}", flush=True)
            continue
        hits = ((payload.get("hits") or {}).get("hits") or [])[:INSPECT_PER_QUERY]
        inspected = 0
        accepted = 0
        for hit in hits:
            if inspected >= INSPECT_PER_QUERY or len(rows) >= OVERALL:
                break
            source_row = hit.get("_source") or {}
            inspected += 1
            stats["inspected"] += 1
            title = soften(source_row.get("title") or "")
            description = soften(" ".join(
                str(source_row.get(key) or "") for key in ("text", "medium", "object_name")
            ))
            kind = " ".join(
                str(source_row.get(key) or "") for key in ("classification", "medium", "object_name")
            )
            object_id = source_row.get("id") or hit.get("_id") or ""
            source = {
                "institution": "Minneapolis Institute of Art",
                "licence": licence,
                "source_url": f"https://collections.artsmia.org/art/{object_id}",
                "external_id": f"mia:{object_id}",
            }
            if consider(
                atlas,
                phrase,
                re.sub(r"\s+", " ", title).strip(),
                re.sub(r"\s+", " ", description).strip(),
                (title, kind),
                seen,
                per_island,
                rows,
                source,
                allow_sculpture=True,
            ):
                accepted += 1
                stats["accepted"] += 1
        print(
            f"mia {phrase!r} inspected {inspected} accepted {accepted} total {len(rows)}",
            flush=True,
        )
    return rows, stats


def write_output(rows, meta) -> None:
    save_json(
        OUT,
        {
            "slug": "artwork-more",
            "generatedAt": utc_now(),
            "meta": meta,
            "rows": rows,
        },
    )


def main() -> None:
    atlas = Atlas()
    seen = existing_artwork_keys()
    # This file is rewritten on every run, so its previous rows are not
    # already-published artwork.
    for item in load_json(OUT, {}).get("rows") or []:
        if item.get("island_id") and item.get("title"):
            seen.discard((item["island_id"], fold(item["title"])))
    queries, unresolved = build_queries(atlas)
    print(f"queries {len(queries)} unresolved {unresolved}", flush=True)

    meta = {
        "licences": {},
        "sources": [],
        "skipped": [
            "Wikidata, Wikipedia/Commons, the Met, Cleveland, the Art Institute of Chicago, the V&A, and the National Gallery of Art are covered by other passes and were not queried.",
        ],
        "queries": queries,
        "unresolved_phrases": unresolved,
    }
    rows: list[dict] = []
    per_island: dict[str, int] = defaultdict(int)

    wellcome_ok, wellcome_licence, wellcome_sentence = confirm_wellcome()
    meta["licences"]["wellcome"] = wellcome_sentence or "Wellcome catalogue docs fetched; no CC0 or CC BY sentence found."
    if wellcome_ok:
        wellcome_rows, wellcome_stats = harvest_wellcome(atlas, queries, seen, per_island, wellcome_licence)
        rows.extend(wellcome_rows)
        meta["sources"].append({"id": "wellcome", "used": True, "licence": wellcome_licence, **wellcome_stats})
        write_output(rows, meta)
    else:
        meta["sources"].append({"id": "wellcome", "used": False, "reason": "Catalogue docs did not state CC0, CC BY, CC BY-SA, or OGL."})
        meta["skipped"].append("Wellcome Collection: licence not clearly open.")
        print("skip wellcome", flush=True)

    yale_ok, yale_licence, yale_sentence = confirm_yale()
    meta["licences"]["yale"] = yale_sentence or "Yale LUX open-access page fetched; no CC0 sentence found."
    if yale_ok:
        yale_rows, yale_stats = harvest_yale(atlas, queries, seen, per_island, yale_licence)
        rows.extend(yale_rows)
        meta["sources"].append({"id": "yale-lux", "used": True, "licence": yale_licence, **yale_stats})
        write_output(rows, meta)
    else:
        meta["sources"].append({"id": "yale-lux", "used": False, "reason": "Open-access page did not state CC0, CC BY, CC BY-SA, or OGL."})
        meta["skipped"].append("Yale LUX: licence not clearly open.")
        print("skip yale", flush=True)

    if len(rows) < MIA_THRESHOLD:
        mia_ok, mia_licence, mia_sentence, mia_images = confirm_mia()
        meta["licences"]["mia"] = mia_sentence or "Mia README fetched; no CC0 sentence found."
        if mia_images:
            meta["licences"]["mia_images"] = mia_images
        if mia_ok:
            mia_rows, mia_stats = harvest_mia(atlas, queries, seen, per_island, mia_licence)
            rows.extend(mia_rows)
            meta["sources"].append(
                {
                    "id": "minneapolis",
                    "used": True,
                    "licence": mia_licence,
                    "images": "omitted; README says images are not under the CC0 metadata licence and are limited to non-commercial use",
                    **mia_stats,
                }
            )
        else:
            meta["sources"].append({"id": "minneapolis", "used": False, "reason": "Could not confirm CC0 quickly from the artsmia collection README."})
            meta["skipped"].append("Minneapolis Institute of Art: CC0 not confirmed.")
    else:
        meta["sources"].append(
            {
                "id": "minneapolis",
                "used": False,
                "reason": f"Not required: Wellcome and Yale accepted {len(rows)} rows (threshold {MIA_THRESHOLD}).",
            }
        )
        meta["skipped"].append(
            f"Minneapolis Institute of Art: not queried because Wellcome and Yale already accepted {len(rows)} rows."
        )

    write_output(rows, meta)
    islands = sorted({row["island_name"] for row in rows})
    print(f"wrote {OUT} rows {len(rows)} islands {len(islands)}", flush=True)
    counts = defaultdict(int)
    for row in rows:
        counts[row["island_name"]] += 1
    for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:12]:
        print(f"  {count} {name}", flush=True)


if __name__ == "__main__":
    main()
