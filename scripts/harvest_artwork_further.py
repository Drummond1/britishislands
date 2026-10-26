#!/usr/bin/env python3
"""Harvest paintings, prints, and named sculptures from further catalogues.

A catalogue is queried only after its own documentation has been fetched
and states that the metadata is CC0, CC BY, or CC BY-SA. An image URL is
stored only when the same docs, or the object record, put that image under
CC0, CC BY, CC BY-SA, or public domain. CC BY-NC, CC BY-ND, and
all-rights-reserved images stay off the row.

Does not query catalogues already harvested (Met, Cleveland, Art Institute
of Chicago, National Gallery of Art, National Gallery London, Wikidata,
Commons, Wellcome, Yale). Does not publish.

Writes only:
  data/interest/candidates/artwork-further.json
  data/cache_artwork_further/**
"""

from __future__ import annotations

import csv
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
    artwork_row,
    existing_artwork_keys,
    match_island_phrase,
    phrase_in_text,
    search_phrases,
)
from ingest_sources import name_key  # noqa: E402
from interest_categories import (  # noqa: E402
    Atlas,
    fold,
    load_env,
    load_json,
    row,
    save_json,
    utc_now,
)

CACHE = ROOT / "data" / "cache_artwork_further"
OUT = ROOT / "data" / "interest" / "candidates" / "artwork-further.json"
UA = "isles-of-britain/0.1 (artwork-further; research)"

SLEEP_S = 0.55
INSPECT_PER_QUERY = 40
DESC_INSPECT = 15
PER_ISLAND = 14
OVERALL = 220
MAX_FETCHES = 900
REJECT_CAP = 70
DUP_NOTES = 12
CC0_URL = "https://creativecommons.org/publicdomain/zero/1.0/"
PDM_URL = "https://creativecommons.org/publicdomain/mark/1.0/"
BY_URL = "https://creativecommons.org/licenses/by/4.0/"
BY_SA_URL = "https://creativecommons.org/licenses/by-sa/4.0/"

RIJKS_POLICY = "https://data.rijksmuseum.nl/policy/information-and-data-policy"
RIJKS_SEARCH = "https://data.rijksmuseum.nl/search/collection"
HARVARD_README = "https://raw.githubusercontent.com/harvardartmuseums/api-docs/master/README.md"
HARVARD_LICENCE = "https://harvardartmuseums.org/licensing"
WALTERS_README = "https://raw.githubusercontent.com/WaltersArtMuseum/api-thewalters-org/main/README.md"
WALTERS_RIGHTS = "https://thewalters.org/about/policies/rights-reproductions/"
WALTERS_ART = "https://raw.githubusercontent.com/WaltersArtMuseum/api-thewalters-org/main/art.csv"
WALTERS_CREATORS = "https://raw.githubusercontent.com/WaltersArtMuseum/api-thewalters-org/main/creators.csv"
MIA_README = "https://raw.githubusercontent.com/artsmia/collection/main/readme.md"
MIA_OPEN = "https://collections.artsmia.org/info/open-access"
MIA_SEARCH = "https://search.artsmia.org/"
BROOKLYN_TERMS = "https://www.brooklynmuseum.org/opencollection/api/docs/termsofuse"
BROOKLYN_SITE = "https://www.brooklynmuseum.org/terms"
PMA_OPEN = "https://openn.library.upenn.edu/html/0031.html"

# Famous subjects and qualified island names. Bare ambiguous leftovers
# (man, rum, may, bass, holy, harris, wight) are not searched on their own.
LANDMARKS = [
    "Fingal's Cave",
    "Staffa",
    "Iona",
    "Lindisfarne",
    "Holy Island",
    "Isle of Skye",
    "Skye",
    "Isle of Mull",
    "Isle of Arran",
    "Arran",
    "Islay",
    "Jura",
    "St Kilda",
    "Skellig Michael",
    "Skellig",
    "Lundy",
    "Ailsa Craig",
    "Bass Rock",
    "Anglesey",
    "Isle of Wight",
    "Isle of Jersey",
    "Isle of Guernsey",
    "Sark",
    "Isles of Scilly",
    "Orkney",
    "Shetland",
    "Achill Island",
    "Achill",
    "Aran Islands",
    "Tory Island",
    "Valentia Island",
    "Inishmore",
    "Burgh Island",
    "Saint Michael's Mount",
    "Caldey",
    "Bardsey",
    "Rathlin",
    "Lambay",
    "Isle of May",
    "Tresco",
    "Skomer",
    "Brownsea Island",
    "Fair Isle",
    "Isle of Hoy",
]

GROUP_WORDS = {
    "orkney",
    "shetland",
    "jersey",
    "guernsey",
    "man",
    "scilly",
    "isles of scilly",
    "skellig",
    "skellig michael",
    "aran islands",
}
HOLY_LINDIS = ("lindisfarne", "northumberland", "farne")
HOLY_ANGLES = ("anglesey", "ynys gybi", "holyhead", "ynys mon", "caergybi")

ART_WORD = re.compile(
    r"\b(paintings?|schilderijen?|drawings?|tekeningen?|watercolou?rs?|watercolors?|"
    r"aquarellen?|prints?|prenten?|prent|etchings?|etsen?|engravings?|gravures?|"
    r"aquatints?|lithographs?|lithograf\w*|woodcuts?|houtsneden?|mezzotints?|"
    r"drypoints?|sculptures?|beeldhouw\w*|statues?|standbeelden?|sketches?|"
    r"olieverf|oil on canvas|gouaches?)\b",
    re.I,
)
PHOTO_WORD = re.compile(
    r"\b(photographs?|fotograf\w*|photogravures?|daguerreotypes?|albumen|"
    r"gelatin silver|carte de visite|collodion|snapshots?|cyanotypes?)\b",
    re.I,
)
MAP_WORD = re.compile(r"\b(maps?|charts?|sea[- ]charts?|karte|landkaart|kaarten?)\b", re.I)
PORTRAIT_WORD = re.compile(r"\b(portrait of|porträt|portret van|bust of)\b", re.I)
VIEW_WORD = re.compile(
    r"\b(views?|depicts|depiction|depicting|coasts?|shores?|bays?|caves?|"
    r"cliffs?|landscapes?|harbou?rs?|headlands?|looking (?:toward|towards|across|at)|"
    r"gezicht op|zicht op)\b",
    re.I,
)
SOUVENIR_WORD = re.compile(
    r"\b(souvenirs?|medals?|postage stamps?|costumes?|porcelain|ceramics?|"
    r"jewell?ery|jewelry|furniture|textiles?)\b",
    re.I,
)
SPECIMEN_WORD = re.compile(r"\b(specimens?|herbari(?:um|a)|botanical plates?)\b", re.I)
SITTER_WORD = re.compile(
    r"\b(lived|resident|born|died|sitter|while (?:he|she) was|his house|her house|"
    r"sought refuge|known primarily|painted on|stayed on|visited)\b",
    re.I,
)
OTHER_WORK = re.compile(
    r"\b(?:his|her|the|this|an|another|turner'?s)?\s*(?:oil\s+)?"
    r"(?:painting|picture|watercolou?r|watercolor|canvas|print|etching)\b",
    re.I,
)
MODERN_MAP = re.compile(
    r"ordnance survey|geological survey|hydrographic|1:\s?25[\s,]*000|"
    r"1:\s?50[\s,]*000|carte routi[eè]re",
    re.I,
)
FOREIGN_PLACE = re.compile(
    r"\b(new jersey|n\.\s*j\b|south dakota|s\.?\s*dak|florida|\bfla\b|"
    r"australia|melbourne|new zealand|hudson|new york|angola|dande)\b",
    re.I,
)
PLACE_CUES = {
    "barra": ("isle", "island", "hebrides", "castlebay", "scotland", "outer hebrides"),
    "yell": ("shetland", "isle", "island"),
}
QUALIFIED_RE = re.compile(
    r"\b(?:isle of|island of|ynys|eilean|inis|inish|oilean)\s+"
    r"[a-z0-9'’\-]+(?:\s+[a-z0-9'’\-]+){0,4}",
    re.I,
)
ROLE_RE = re.compile(
    r"\b(painter|artist|printmaker|engraver|etcher|lithographer|draughtsman|"
    r"draftsman|sculptor|designer)\s*:\s*([^,;(]{2,80})",
    re.I,
)
ROLE_RANK = {
    "painter": 0,
    "artist": 1,
    "sculptor": 2,
    "printmaker": 3,
    "etcher": 4,
    "engraver": 5,
    "lithographer": 6,
    "draughtsman": 7,
    "draftsman": 7,
    "designer": 8,
}
KIND_RULES = (
    ("watercolour", re.compile(r"watercolou?r|watercolor|aquarel|gouache", re.I)),
    ("etching", re.compile(r"\betchings?\b|\betsen?\b|eau-forte", re.I)),
    ("engraving", re.compile(r"engravings?|gravures?", re.I)),
    ("lithograph", re.compile(r"lithographs?|lithograf", re.I)),
    ("woodcut", re.compile(r"woodcuts?|houtsnede", re.I)),
    ("mezzotint", re.compile(r"mezzotints?", re.I)),
    ("aquatint", re.compile(r"aquatints?", re.I)),
    ("drawing", re.compile(r"\bdrawings?\b|\btekeningen?\b|\bdessins?\b|\bsketches?\b", re.I)),
    ("sculpture", re.compile(r"sculptures?|beeldhouw|standbeeld|\bstatues?\b", re.I)),
    ("painting", re.compile(r"\bpaintings?\b|schilderij|olieverf|oil on", re.I)),
    ("print", re.compile(r"\bprints?\b|\bprent(?:en)?\b|\bestampes?\b", re.I)),
)


def soften(text: str) -> str:
    text = html.unescape(text or "")
    text = (
        text.replace("’", "'")
        .replace("‘", "'")
        .replace("`", "'")
        .replace("´", "'")
    )
    text = re.sub(r"(?i)\bSt\.", "St", text)
    return text


def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<script.*?>.*?</script>", " ", raw or "")
    raw = re.sub(r"(?is)<style.*?>.*?</style>", " ", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", soften(raw)).strip()


def md_text(raw: str) -> str:
    raw = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", raw or "")
    return re.sub(r"\s+", " ", soften(raw)).strip()


def sentence_with(text: str, pattern: str) -> str:
    plain = re.sub(r"\s+", " ", text or "")
    match = re.search(pattern, plain, re.I)
    if not match:
        return ""
    left = max(plain.rfind(".", 0, match.start()), plain.rfind(";", 0, match.start()))
    right = plain.find(".", match.end())
    end = right + 1 if right != -1 else min(len(plain), match.end() + 240)
    return plain[left + 1 : end].strip()[:500]


def variants(phrase: str) -> list[str]:
    base = soften(phrase).strip()
    found = []
    for item in (
        base,
        re.sub(r"\bSt\b", "Saint", base),
        re.sub(r"\bSaint\b", "St", base),
        base.replace("'", ""),
    ):
        item = re.sub(r"\s+", " ", item).strip()
        if item and item.lower() not in {v.lower() for v in found}:
            found.append(item)
    return found


def contains_phrase(phrase: str, text: str) -> bool:
    """Whole-word match. Folding alone must not turn tirée into Tiree."""
    cleaned = soften(text)
    lowered = cleaned.lower()
    for variant in variants(phrase):
        if not phrase_in_text(variant, cleaned):
            continue
        if re.search(r"\b" + re.escape(variant.lower()) + r"\b", lowered):
            return True
    return False


def snippet(text: str, phrase: str) -> str:
    cleaned = re.sub(r"\s+", " ", soften(text)).strip()
    match = None
    for variant in variants(phrase):
        match = re.search(r"\b" + re.escape(variant) + r"\b", cleaned, re.I)
        if match:
            break
    if not match:
        return cleaned[:240]
    start = max(0, match.start() - 100)
    end = min(len(cleaned), match.end() + 100)
    return cleaned[start:end].strip()


def qualified_phrase(phrase: str) -> bool:
    return bool(re.search(r"\b(isle of|island of|ynys|eilean|inis|inish|oilean)\b", phrase or "", re.I))


def object_kind(*parts: str) -> str:
    blob = " ".join(part or "" for part in parts)
    for kind, pattern in KIND_RULES:
        if pattern.search(blob):
            return kind
    return "artwork"


def licence_url(short: str) -> str:
    return {
        "CC0": CC0_URL,
        "Public Domain": PDM_URL,
        "CC BY": BY_URL,
        "CC BY-SA": BY_SA_URL,
    }.get(short, "")


def open_rights(blob: str) -> str:
    """Return a short open licence, or empty when reuse is not open."""
    low = (blob or "").lower()
    if re.search(r"by-nc|non-?commercial|\bnc\b|by-nd|no-?deriv|all rights reserved|in copyright|©", low):
        return ""
    if "publicdomain/zero" in low or re.search(r"\bcc0\b|cc-0|creative commons zero", low):
        return "CC0"
    if "by-sa" in low or "attribution-sharealike" in low:
        return "CC BY-SA"
    if re.search(r"creativecommons.org/licenses/by/|cc by\b|attribution 4\.0", low):
        return "CC BY"
    if "publicdomain/mark" in low or "public domain" in low or re.search(r"\bpdm\b", low):
        return "Public Domain"
    return ""


def cache_path(kind: str, url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
    return CACHE / kind / f"{digest}.json"


def fetch_bytes(url: str, accept: str, timeout: int = 70) -> bytes:
    cmd = [
        "curl",
        "-fsS",
        "--max-time",
        str(timeout),
        "-A",
        UA,
        "-H",
        f"Accept: {accept}",
        "-L",
        url,
    ]
    return subprocess.check_output(cmd)


def cached_json(kind: str, url: str, accept: str = "application/json") -> dict:
    path = cache_path(kind, url)
    if path.exists():
        payload = load_json(path, None)
        if isinstance(payload, dict):
            return payload
    try:
        payload = json.loads(fetch_bytes(url, accept).decode("utf-8"))
        if not isinstance(payload, dict):
            payload = {"_error": "response was not a JSON object", "_url": url}
    except Exception as exc:
        payload = {"_error": f"{type(exc).__name__}: {exc}"[:400], "_url": url}
    save_json(path, payload)
    time.sleep(SLEEP_S)
    return payload


def cached_text(name: str, url: str) -> str:
    dest = CACHE / "docs" / name
    if dest.exists() and dest.stat().st_size > 40:
        return dest.read_text(encoding="utf-8", errors="replace")
    raw = fetch_bytes(url, "text/html, application/json, text/plain", timeout=60)
    text = raw.decode("utf-8", errors="replace")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    time.sleep(SLEEP_S)
    return text


def cached_file(name: str, url: str) -> Path:
    dest = CACHE / "files" / name
    if dest.exists() and dest.stat().st_size > 1000:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    temporary = dest.with_suffix(dest.suffix + ".part")
    subprocess.check_call(
        ["curl", "-fsSL", "--max-time", "180", "-A", UA, "-o", str(temporary), url]
    )
    temporary.replace(dest)
    time.sleep(SLEEP_S)
    return dest


def env_has(*needles: str) -> bool:
    for key, value in load_env().items():
        if not value.strip():
            continue
        hay = key.lower()
        if any(needle in hay for needle in needles):
            return True
    return False


def plain_summary(title: str, kind: str, artist: str, island_name: str) -> str:
    kind = kind or "artwork"
    article = "an" if kind[:1].lower() in "aeiou" else "a"
    if artist:
        sentence = f"{title} is {article} {kind} by {artist}. It depicts {island_name}."
    else:
        sentence = f"{title} is {article} {kind}. It depicts {island_name}."
    return sentence[:500]


def challenge(text: str) -> bool:
    low = (text or "")[:800].lower()
    return "just a moment" in low or "vercel security checkpoint" in low or "cf-mitigated" in low


class Harvest:
    def __init__(self, atlas: Atlas):
        self.atlas = atlas
        self.rows: list[dict] = []
        self.rejected: list[dict] = []
        self.seen = existing_artwork_keys()
        previous = load_json(OUT, {})
        for item in previous.get("rows") or []:
            if item.get("status") == "accepted" and item.get("island_id") and item.get("title"):
                self.seen.discard((item["island_id"], fold(item["title"])))
        self.per_island: dict[str, int] = defaultdict(int)
        self.reject_ids: set[str] = set()
        self.dup_notes = 0
        self.reason_notes: dict[str, int] = defaultdict(int)

    def full(self) -> bool:
        return len(self.rows) >= OVERALL

    def reject(self, *, island, title, source_url, external_id, licence, evidence, reason) -> None:
        if len(self.rejected) >= REJECT_CAP:
            return
        family = reason.split(",")[0][:48]
        limit = 8 if family.startswith("Photograph") else 4 if family.startswith("Bare name") or "does not name one atlas island" in reason else 0
        if limit and self.reason_notes[family] >= limit:
            return
        self.reason_notes[family] += 1
        token = external_id or source_url or title
        if token in self.reject_ids:
            return
        self.reject_ids.add(token)
        title = re.sub(r"\s+", " ", soften(title)).strip()
        if not title:
            return
        item = row(
            category="film-art-music",
            island_id=(island or {}).get("id") or "",
            island_name=(island or {}).get("name") or "",
            facet="artwork",
            title=title[:180],
            source_url=source_url,
            source_title=title[:180],
            licence=licence,
            evidence=(evidence or "")[:500],
            external_id=external_id,
            status="rejected",
            confidence="low",
            reject_reason=reason[:300],
        )
        item["summary"] = ""
        self.rejected.append(item)

    def accept(
        self,
        *,
        island,
        phrase,
        title,
        description,
        kind_text,
        artist,
        institution,
        source_url,
        external_id,
        licence,
        image,
    ) -> bool:
        if self.full():
            return False
        title = re.sub(r"\s+", " ", soften(title)).strip()
        description = re.sub(r"\s+", " ", soften(description)).strip()
        if not title or not source_url:
            return False
        if re.fullmatch(r"untitled", title, re.I):
            return False
        reason = rejection_reason(phrase, title, description, kind_text, island)
        evidence_field = "Title" if contains_phrase(phrase, title) else "Description"
        quoted = title if evidence_field == "Title" else snippet(description or title, phrase)
        evidence = f"{evidence_field}: {quoted} — {institution}"
        if reason:
            if contains_phrase(phrase, title) or contains_phrase(phrase, description):
                self.reject(
                    island=island,
                    title=title,
                    source_url=source_url,
                    external_id=external_id,
                    licence=licence,
                    evidence=evidence,
                    reason=reason,
                )
            return False
        if self.per_island[island["id"]] >= PER_ISLAND:
            return False
        key = (island["id"], fold(title))
        if key in self.seen:
            if self.dup_notes < DUP_NOTES and contains_phrase(phrase, title):
                self.dup_notes += 1
                self.reject(
                    island=island,
                    title=title,
                    source_url=source_url,
                    external_id=external_id,
                    licence=licence,
                    evidence=evidence,
                    reason="This title is already an accepted artwork for this island.",
                )
            return False
        kind = object_kind(title, description, kind_text)
        summary = plain_summary(title, kind, artist, island["name"])
        built = artwork_row(
            island=island,
            title=title,
            source_url=source_url,
            source_title=title,
            licence=licence,
            evidence=evidence,
            summary=summary,
            external_id=external_id,
            open_image=image,
            seen=self.seen,
        )
        if not built:
            return False
        self.rows.append(built)
        self.per_island[island["id"]] += 1
        return True


def qualified_islands(atlas: Atlas, text: str) -> list[dict]:
    found: dict[str, dict] = {}
    for match in QUALIFIED_RE.finditer(soften(text)):
        words = match.group(0).split()
        island = None
        for end in range(len(words), 1, -1):
            island = match_island_phrase(atlas, " ".join(words[:end]))
            if island:
                break
        if island:
            found[island["id"]] = island
    return list(found.values())


def resolve_island(atlas: Atlas, phrase: str, text: str) -> tuple[dict | None, str]:
    if not text or not contains_phrase(phrase, text):
        return None, ""
    folded = soften(phrase).lower()
    if folded in {"fingal's cave", "fingals cave"}:
        return match_island_phrase(atlas, "Staffa"), ""
    if folded == "holy island":
        low = soften(text).lower()
        lind = any(phrase_in_text(cue, low) for cue in HOLY_LINDIS)
        ang = any(phrase_in_text(cue, low) for cue in HOLY_ANGLES)
        if lind and not ang:
            return match_island_phrase(atlas, "Lindisfarne"), ""
        if ang and not lind and any(phrase_in_text(cue, low) for cue in ("ynys gybi", "ynys mon", "isle of")):
            return match_island_phrase(atlas, "Holy Island"), ""
        if lind and ang:
            return None, "Holy Island could be Lindisfarne or Anglesey."
        return None, "Bare name Holy Island, without Isle of, Ynys, or Eilean."
    if folded in GROUP_WORDS:
        found = qualified_islands(atlas, text)
        if len(found) == 1:
            island = found[0]
            if name_key(island["name"]) == "man" and not contains_phrase("Isle of Man", text):
                return None, "Bare name Man, without Isle of Man."
            return island, ""
        return None, f"{phrase} does not name one atlas island."
    island = match_island_phrase(atlas, phrase)
    if island is None:
        saint = re.sub(r"\bSt\b", "Saint", soften(phrase))
        if saint.lower() != soften(phrase).lower():
            island = match_island_phrase(atlas, saint)
    if island is None:
        return None, ""
    key = name_key(island["name"])
    if key in AMBIGUOUS_KEYS and not qualified_phrase(phrase):
        if not qualified_phrase(text):
            return None, f"Bare name {phrase} needs Isle of, Ynys, or Eilean."
    return island, ""


def place_problem(phrase: str, title: str, description: str, island: dict) -> str:
    blob = f"{title}\n{description}"
    folded = soften(phrase).lower()
    key = name_key(island.get("name") or "")
    if MODERN_MAP.search(title) or MODERN_MAP.search(description[:200]):
        return "Modern regional map or chart, not a painting or print of the island."
    if FOREIGN_PLACE.search(blob):
        cornish = re.search(r"\b(cornwall|marazion|penzance)\b", blob, re.I)
        hebridean = re.search(r"\b(scotland|hebrides|cathedral|abbey)\b", blob, re.I)
        if "michael" in folded and cornish:
            pass
        elif key == "iona" and hebridean and not re.search(r"dakota|new jersey|hudson|new york", blob, re.I):
            pass
        else:
            return "The place name refers to somewhere outside the atlas island."
    cues = PLACE_CUES.get(key) or PLACE_CUES.get(folded)
    if cues and not qualified_phrase(phrase) and not any(phrase_in_text(cue, blob) for cue in cues):
        return f"{island['name']} is named without an island cue."
    if key == "skye" and re.search(r"\bterriers?\b", blob, re.I) and not re.search(
        r"\b(isle|island|scotland|hebrides|portree|dunvegan)\b", blob, re.I
    ):
        return "Skye here is a dog breed, not the island."
    if key in {"jura", "arran"} and not qualified_phrase(phrase):
        cues = (
            "isle", "island", "hebrides", "hebriden", "scotland", "schotland", "schotse",
            "argyll", "paps", "goatfell", "clyde", "lochranza", "loch ranza",
        )
        if not any(phrase_in_text(cue, blob) for cue in cues):
            return f"{island['name']} is named without a Hebridean or island cue."
    if key == "arran" and re.search(r"\b(earl|comte|count|lord)\s+(?:of\s+)?arran\b", blob, re.I):
        if not any(phrase_in_text(cue, blob) for cue in ("isle", "island", "scotland", "goatfell")):
            return "Arran here is a peerage title, not the island."
    if re.search(r"\bnear\s+" + re.escape(soften(phrase)) + r"\b", soften(title), re.I):
        return "The title is a place near the island, not the island itself."
    return ""


def photo_type(kind_text: str) -> bool:
    """Albumen prints and stereographs are photographs. Collotypes and photochroms are prints."""
    if re.search(r"photomechanical|photochrom|collotype", kind_text, re.I):
        return False
    return bool(
        re.search(
            r"\b(photographs?|photographic|stereographs?|stereofotos?|"
            r"albumen(?:\s+prints?)?|albuminedruk)\b",
            kind_text,
            re.I,
        )
    )


def rejection_reason(phrase: str, title: str, description: str, kind_text: str, island: dict) -> str:
    if not island:
        return ""
    blob = f"{title}\n{description}\n{kind_text}"
    title_hit = contains_phrase(phrase, title)
    desc_hit = contains_phrase(phrase, description)
    if not title_hit and not desc_hit:
        return ""
    problem = place_problem(phrase, title, description, island)
    if problem:
        return problem
    if photo_type(kind_text) or (PHOTO_WORD.search(blob) and not ART_WORD.search(title)):
        return "Photograph, not a painting, print, or named sculpture."
    if MAP_WORD.search(title) or MAP_WORD.search(kind_text):
        return "Map or chart of a region, not a painting or print of the island."
    if SPECIMEN_WORD.search(blob):
        return "Specimen plate, not a depiction of the island."
    if SOUVENIR_WORD.search(title) or SOUVENIR_WORD.search(kind_text):
        return "Souvenir or decorative object, not a painting, print, or named sculpture."
    if PORTRAIT_WORD.search(title) and not VIEW_WORD.search(title):
        return "Portrait of a person, not a depiction of the island."
    if not ART_WORD.search(blob):
        return "The catalogue does not describe this as a painting, print, drawing, or sculpture."
    if not title_hit:
        window = snippet(description, phrase)
        if OTHER_WORK.search(window):
            return "The description names the island only as another work, not as the subject of this one."
        if SITTER_WORD.search(window):
            return "The text is about a person associated with the island, not a depiction of it."
        if not VIEW_WORD.search(window) and not re.search(
            r"\b(on|at|from)\s+(?:scotland's\s+)?(?:the\s+)?(?:isle|island)\b",
            window,
            re.I,
        ):
            return "The description names the island but does not say this work depicts it."
    return ""


def image_payload(thumb: str, page: str, attribution: str, short: str) -> dict | None:
    if not thumb or not short or not thumb.startswith("http"):
        return None
    payload = {
        "thumbUrl": thumb,
        "pageUrl": page,
        "attribution": attribution[:180],
        "licence": short,
        "licenceUrl": licence_url(short),
    }
    return payload


def build_queries(atlas: Atlas) -> tuple[list[str], list[str]]:
    queries: list[str] = []
    unresolved: list[str] = []
    seen: set[str] = set()

    def add(phrase: str) -> None:
        token = soften(phrase).lower()
        if token and token not in seen:
            seen.add(token)
            queries.append(phrase)

    for phrase in LANDMARKS:
        folded = soften(phrase).lower()
        island = match_island_phrase(atlas, phrase)
        if island is None and folded not in {"fingal's cave", "holy island"} and folded not in GROUP_WORDS:
            saint = re.sub(r"\bSt\b", "Saint", soften(phrase))
            if saint.lower() != folded:
                island = match_island_phrase(atlas, saint)
            if island is None:
                unresolved.append(phrase)
                continue
        if folded in GROUP_WORDS:
            unresolved.append(phrase)
        add(phrase)

    covered = set()
    extra = 0
    for phrase, island in search_phrases(atlas):
        if extra >= 30:
            break
        if (island.get("area") or 0) < 30:
            continue
        if island["id"] in covered:
            continue
        if soften(phrase).lower().startswith("island of "):
            continue
        if "mainland" in soften(phrase).lower() and not qualified_phrase(phrase):
            continue
        if soften(phrase).lower() in seen:
            covered.add(island["id"])
            continue
        covered.add(island["id"])
        add(phrase)
        extra += 1
    return queries, unresolved


def confirm_rijks() -> dict:
    try:
        raw = cached_text("rijks-policy.html", RIJKS_POLICY)
    except subprocess.CalledProcessError as exc:
        return {"ok": False, "sentence": f"Rijksmuseum policy page was not fetched ({exc})."}
    plain = html_to_text(raw)
    if challenge(plain):
        return {"ok": False, "sentence": "Rijksmuseum policy page returned a bot challenge."}
    sentence = sentence_with(
        plain,
        r"Public Domain Mark \(PDM\) and/or the Creative Commons Zero 1\.0 \(CC0 1\.0\)",
    )
    images = sentence_with(plain, r"provides this Information and Data with the Creative Commons Zero 1\.0")
    ok = bool(re.search(r"Creative Commons Zero 1\.0 \(CC0 1\.0\)", plain)) and "information and data" in plain.lower()
    return {
        "ok": ok,
        "licence": "CC0" if ok else "",
        "sentence": sentence,
        "image_sentence": images,
        "images_open": ok,
    }


def rijks_contents(node) -> list[tuple[str, str, str]]:
    found = []

    def walk(item) -> None:
        if isinstance(item, dict):
            content = item.get("content")
            if isinstance(content, str) and content.strip():
                langs = " ".join(
                    (lang.get("id") or "")
                    for lang in (item.get("language") or [])
                    if isinstance(lang, dict)
                )
                found.append((item.get("type") or "", content.strip(), langs))
            for value in item.values():
                walk(value)
        elif isinstance(item, list):
            for value in item:
                walk(value)

    walk(node)
    return found


def rijks_artist(obj: dict) -> str:
    best = ("", 99)
    for kind, content, langs in rijks_contents(obj.get("produced_by")):
        if "300388277" not in langs and not re.search(r"[A-Za-z]", content):
            continue
        match = ROLE_RE.search(soften(content))
        if not match:
            continue
        rank = ROLE_RANK.get(match.group(1).lower(), 9)
        name = re.sub(r"\s*\(.*?\)", "", match.group(2)).strip(" .;")
        if rank < best[1] and 2 <= len(name) <= 80:
            best = (name, rank)
    return best[0]


def rijks_image(obj: dict, page: str, artist: str) -> dict | None:
    found = []

    def walk(item) -> None:
        if isinstance(item, dict):
            points = item.get("access_point")
            urls = []
            if isinstance(points, dict):
                points = [points]
            if isinstance(points, list):
                for point in points:
                    url = point.get("id") if isinstance(point, dict) else point
                    if isinstance(url, str) and ("iiif" in url or "micr.io" in url):
                        urls.append(url)
            if urls:
                rights = json.dumps(
                    {
                        "referred_to_by": item.get("referred_to_by"),
                        "subject_to": item.get("subject_to"),
                    },
                    ensure_ascii=False,
                )
                found.append((urls[0], rights))
            for value in item.values():
                walk(value)
        elif isinstance(item, list):
            for value in item:
                walk(value)

    walk(obj)
    for url, rights in found:
        short = open_rights(rights)
        if not short:
            continue
        thumb = url.replace("/full/max/", "/full/!400,400/").replace("/full/full/", "/full/!400,400/")
        attribution = f"{artist}, Rijksmuseum" if artist else "Rijksmuseum"
        return image_payload(thumb, page, attribution, short)
    return None


def rijks_parts(obj: dict) -> tuple[str, str, str, str, str]:
    if isinstance(obj.get("@graph"), list):
        for item in obj["@graph"]:
            if isinstance(item, dict) and item.get("type") == "HumanMadeObject":
                obj = item
                break
    names = []
    number = ""
    for ident in obj.get("identified_by") or []:
        if not isinstance(ident, dict):
            continue
        content = soften(ident.get("content") or "")
        if ident.get("type") == "Identifier" and re.search(r"[A-Z]{1,4}-", content) and not number:
            number = content.split()[0]
        if ident.get("type") != "Name" or not content:
            continue
        if re.fullmatch(r"[\d\s\-–—./]+", content):
            continue
        langs = " ".join(
            (lang.get("id") or "") for lang in (ident.get("language") or []) if isinstance(lang, dict)
        )
        classes = json.dumps(ident.get("classified_as") or "", ensure_ascii=False)
        names.append((content, langs, "300404670" in classes))
    english_titles = [content for content, langs, is_title in names if is_title and "300388277" in langs]
    any_titles = [content for content, _langs, is_title in names if is_title]
    english_names = [content for content, langs, _is_title in names if "300388277" in langs]
    title = (
        english_titles[0]
        if english_titles
        else any_titles[0]
        if any_titles
        else english_names[0]
        if english_names
        else (names[0][0] if names else "")
    )
    notes = []
    for kind, content, langs in rijks_contents(obj.get("referred_to_by")):
        if kind != "LinguisticObject":
            continue
        if re.search(r"\b(height|width|blad:|mm x|collector)", content, re.I):
            continue
        if ROLE_RE.search(content):
            continue
        notes.append((content, langs))
    english_notes = [content for content, langs in notes if "300388277" in langs]
    description = " ".join(english_notes or [content for content, _langs in notes[:4]])
    artist = rijks_artist(obj)
    short = " ".join(content for _kind, content, _langs in rijks_contents(obj) if len(content) < 80)
    kind_text = f"{short} {english_notations(obj)}"
    return soften(title), soften(description), artist, kind_text, number


def english_notations(obj: dict) -> str:
    found: list[str] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            notation = node.get("notation")
            if isinstance(notation, list):
                for item in notation:
                    if isinstance(item, dict) and item.get("@language") == "en" and item.get("@value"):
                        found.append(str(item["@value"]))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(obj)
    return " ".join(dict.fromkeys(found))


def harvest_rijks(bag: Harvest, queries: list[str], licence: str) -> dict:
    stats = {"inspected": 0, "accepted": 0, "with_image": 0, "queries": 0, "errors": 0, "fetches": 0}
    seen_ids: set[str] = set()

    def take(phrase: str, ids: list[str], limit: int) -> None:
        inspected = 0
        accepted = 0
        for oid in ids:
            if bag.full() or stats["fetches"] >= MAX_FETCHES or inspected >= limit:
                break
            if oid in seen_ids:
                continue
            obj = cached_json("rijks-object", oid, accept="application/ld+json")
            stats["fetches"] += 1
            inspected += 1
            stats["inspected"] += 1
            if obj.get("_error"):
                stats["errors"] += 1
                continue
            title, description, artist, kind_text, number = rijks_parts(obj)
            if not title:
                continue
            if not contains_phrase(phrase, f"{title}\n{description}"):
                continue
            seen_ids.add(oid)
            island, reason = resolve_island(bag.atlas, phrase, f"{title}\n{description}")
            page = f"https://www.rijksmuseum.nl/en/collection/{number}" if number else oid
            if reason and contains_phrase(phrase, title):
                bag.reject(
                    island=island,
                    title=title,
                    source_url=page,
                    external_id=f"rijks:{oid.rstrip('/').split('/')[-1]}",
                    licence=licence,
                    evidence=f"Title: {title} — Rijksmuseum",
                    reason=reason,
                )
                continue
            if not island:
                continue
            image = rijks_image(obj, page, artist)
            before = len(bag.rows)
            if bag.accept(
                island=island,
                phrase=phrase,
                title=title,
                description=description,
                kind_text=kind_text,
                artist=artist,
                institution="Rijksmuseum",
                source_url=page,
                external_id=f"rijks:{oid.rstrip('/').split('/')[-1]}",
                licence=licence,
                image=image,
            ):
                accepted += 1
                stats["accepted"] += 1
                if len(bag.rows) > before and bag.rows[-1].get("open_image"):
                    stats["with_image"] += 1
        print(
            f"rijks {phrase!r} inspected {inspected} accepted {accepted} total {len(bag.rows)}",
            flush=True,
        )

    for phrase in queries:
        if bag.full() or stats["fetches"] >= MAX_FETCHES:
            break
        stats["queries"] += 1
        url = RIJKS_SEARCH + "?" + urllib.parse.urlencode({"title": phrase, "imageAvailable": "true"})
        payload = cached_json("rijks-search", url)
        if payload.get("_error"):
            stats["errors"] += 1
            print(f"rijks error {phrase}: {payload['_error'][:160]}", flush=True)
            continue
        ids = [item.get("id") for item in (payload.get("orderedItems") or []) if isinstance(item, dict) and item.get("id")]
        total = ((payload.get("partOf") or {}).get("totalItems")) or len(ids)
        take(phrase, ids, INSPECT_PER_QUERY)
        if total == 0 and phrase in LANDMARKS and stats["fetches"] < MAX_FETCHES and not bag.full():
            desc_url = RIJKS_SEARCH + "?" + urllib.parse.urlencode(
                {"description": phrase, "imageAvailable": "true"}
            )
            desc_payload = cached_json("rijks-search", desc_url)
            if not desc_payload.get("_error"):
                desc_ids = [
                    item.get("id")
                    for item in (desc_payload.get("orderedItems") or [])
                    if isinstance(item, dict) and item.get("id")
                ]
                take(phrase, desc_ids, DESC_INSPECT)
    return stats


def confirm_harvard() -> dict:
    sentence = ""
    try:
        raw = cached_text("harvard-licensing.html", HARVARD_LICENCE)
        plain = html_to_text(raw)
        sentence = sentence_with(plain, r"personal, noncommercial use")
    except subprocess.CalledProcessError as exc:
        sentence = f"Harvard licensing page was not fetched ({exc})."
    readme = ""
    try:
        readme_raw = cached_text("harvard-readme.md", HARVARD_README)
        readme = sentence_with(md_text(readme_raw), r"API key|apikey")
    except subprocess.CalledProcessError as exc:
        readme = f"Harvard API README was not fetched ({exc})."
    return {
        "ok": False,
        "sentence": sentence,
        "readme": readme,
        "reason": "No Harvard Art Museums API key in .env.local.",
    }


def confirm_walters() -> dict:
    try:
        raw = cached_text("walters-readme.md", WALTERS_README)
    except subprocess.CalledProcessError as exc:
        return {"ok": False, "sentence": f"Walters API README was not fetched ({exc})."}
    plain = md_text(raw)
    sentence = sentence_with(plain, r"data and images are made available to the public under a CC0 licen")
    ok = "cc0" in plain.lower() and "data and images" in plain.lower()
    rights = ""
    try:
        rights_raw = cached_text("walters-rights.html", WALTERS_RIGHTS)
        rights_plain = html_to_text(rights_raw)
        if challenge(rights_plain):
            rights = "Walters rights page returned a bot challenge and was not used."
        else:
            rights = sentence_with(rights_plain, r"Creative Commons Zero|CC0")
    except subprocess.CalledProcessError as exc:
        rights = f"Walters rights page was not fetched ({exc})."
    return {
        "ok": ok,
        "licence": "CC0" if ok else "",
        "sentence": sentence,
        "rights": rights,
        "images_open": ok,
    }


def walters_creators(path: Path) -> dict[str, str]:
    names = {}
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        for item in csv.DictReader(handle):
            names[item.get("id") or ""] = (item.get("name") or "").strip()
    return names


def walters_image(item: dict, page: str, artist: str, description: str) -> dict | None:
    """Documented CC0 image path. The image host itself is not re-downloaded."""
    filename = next((part.strip() for part in (item.get("Images") or "").split("|") if part.strip()), "")
    if not filename:
        return None
    record_rights = f"{item.get('CreditLine') or ''} {description[:500]}"
    if re.search(r"©|all rights reserved|in copyright", record_rights, re.I):
        return None
    thumb = "https://art.thewalters.org/images/art/" + urllib.parse.quote(filename)
    attribution = f"{artist}, Walters Art Museum" if artist else "Walters Art Museum"
    return image_payload(thumb, page, attribution, "CC0")


def harvest_walters(bag: Harvest, queries: list[str], licence: str, images_open: bool) -> dict:
    stats = {"inspected": 0, "accepted": 0, "with_image": 0, "queries": len(queries), "errors": 0}
    try:
        art_path = cached_file("art.csv", WALTERS_ART)
        creator_path = cached_file("creators.csv", WALTERS_CREATORS)
    except subprocess.CalledProcessError as exc:
        stats["errors"] += 1
        stats["error"] = f"Walters CSV was not fetched ({exc})."
        return stats
    creators = walters_creators(creator_path)
    csv.field_size_limit(min(sys.maxsize, 10_000_000))
    compiled = [(phrase, re.compile(r"\b" + re.escape(soften(phrase)) + r"\b", re.I)) for phrase in queries]
    with art_path.open(encoding="utf-8", errors="replace", newline="") as handle:
        for item in csv.DictReader(handle):
            if bag.full() or stats["inspected"] >= 400:
                break
            title = html_to_text(item.get("Title") or "")
            description = html_to_text(item.get("Description") or "")
            kind_text = " ".join(item.get(key) or "" for key in ("ObjectName", "Classification", "Medium"))
            blob = f"{title}\n{description}"
            if not title:
                continue
            matched = [phrase for phrase, pattern in compiled if pattern.search(soften(blob))]
            if not matched:
                continue
            stats["inspected"] += 1
            phrase = next((item_phrase for item_phrase in matched if contains_phrase(item_phrase, title)), matched[0])
            island, reason = resolve_island(bag.atlas, phrase, blob)
            artist_ids = [part for part in (item.get("Creators") or "").split("|") if part]
            artist = ", ".join(name for name in (creators.get(part) or "" for part in artist_ids[:3]) if name)
            object_id = item.get("ObjectID") or ""
            accession = item.get("AccessionNumber") or object_id
            page = item.get("ResourceURL") or f"https://purl.thewalters.org/art/{accession}"
            external_id = f"walters:{object_id}"
            if reason:
                bag.reject(
                    island=island,
                    title=title,
                    source_url=page,
                    external_id=external_id,
                    licence=licence,
                    evidence=f"Title: {snippet(title, phrase)} — Walters Art Museum",
                    reason=reason,
                )
                continue
            if not island:
                continue
            image = walters_image(item, page, artist, description) if images_open else None
            before = len(bag.rows)
            if bag.accept(
                island=island,
                phrase=phrase,
                title=title,
                description=description,
                kind_text=kind_text,
                artist=artist,
                institution="Walters Art Museum",
                source_url=page,
                external_id=external_id,
                licence=licence,
                image=image,
            ):
                stats["accepted"] += 1
                if len(bag.rows) > before and bag.rows[-1].get("open_image"):
                    stats["with_image"] += 1
    print(
        f"walters inspected {stats['inspected']} accepted {stats['accepted']} images {stats['with_image']}",
        flush=True,
    )
    return stats


def confirm_mia() -> dict:
    try:
        raw = cached_text("mia-readme.md", MIA_README)
    except subprocess.CalledProcessError as exc:
        return {"ok": False, "sentence": f"Mia README was not fetched ({exc})."}
    plain = md_text(raw)
    sentence = sentence_with(plain, r"published metadata for our artworks as .{0,24} under a CC0")
    images = sentence_with(plain, r"Images aren't included|limited non-commercial")
    ok = bool(sentence) and "cc0" in sentence.lower()
    open_page = ""
    try:
        page = html_to_text(cached_text("mia-open-access.html", MIA_OPEN))
        if challenge(page) or len(page) < 400:
            open_page = "Mia open-access page did not include a licence sentence in the fetched HTML."
        else:
            open_page = sentence_with(page, r"Public Domain|CC0|commercial purposes")
    except subprocess.CalledProcessError as exc:
        open_page = f"Mia open-access page was not fetched ({exc})."
    # The README is the licence that was actually fetched. It keeps images
    # out of the CC0 metadata grant and limits them to non-commercial use.
    return {
        "ok": ok,
        "licence": "CC0" if ok else "",
        "sentence": sentence,
        "image_sentence": images,
        "open_page": open_page,
        "images_open": False,
    }


def harvest_mia(bag: Harvest, queries: list[str], licence: str) -> dict:
    stats = {"inspected": 0, "accepted": 0, "with_image": 0, "queries": 0, "errors": 0}
    for phrase in queries:
        if bag.full():
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
            if bag.full() or inspected >= INSPECT_PER_QUERY:
                break
            source = hit.get("_source") or {}
            title = soften(source.get("title") or "")
            description = soften(source.get("text") or "")
            kind_text = " ".join(
                str(source.get(key) or "") for key in ("classification", "medium", "object_name")
            )
            if not title:
                continue
            inspected += 1
            stats["inspected"] += 1
            blob = f"{title}\n{description}"
            if not contains_phrase(phrase, blob):
                continue
            island, reason = resolve_island(bag.atlas, phrase, blob)
            object_id = source.get("id") or hit.get("_id") or ""
            page = f"https://collections.artsmia.org/art/{object_id}"
            external_id = f"mia:{object_id}"
            if reason:
                bag.reject(
                    island=island,
                    title=title,
                    source_url=page,
                    external_id=external_id,
                    licence=licence,
                    evidence=f"Title: {snippet(title, phrase)} — Minneapolis Institute of Art",
                    reason=reason,
                )
                continue
            if not island:
                continue
            if bag.accept(
                island=island,
                phrase=phrase,
                title=title,
                description=description,
                kind_text=f"{title} {kind_text}",
                artist=soften(source.get("artist") or ""),
                institution="Minneapolis Institute of Art",
                source_url=page,
                external_id=external_id,
                licence=licence,
                image=None,
            ):
                accepted += 1
                stats["accepted"] += 1
        print(f"mia {phrase!r} inspected {inspected} accepted {accepted} total {len(bag.rows)}", flush=True)
    return stats


def confirm_brooklyn() -> dict:
    text = ""
    error = ""
    for name, url in (("brooklyn-terms.html", BROOKLYN_TERMS), ("brooklyn-site-terms.html", BROOKLYN_SITE)):
        try:
            raw = cached_text(name, url)
        except subprocess.CalledProcessError as exc:
            error = f"Brooklyn terms were not fetched ({exc})."
            continue
        plain = html_to_text(raw)
        if challenge(plain):
            error = "Brooklyn terms page returned a bot challenge."
            continue
        text += "\n" + plain
    if not text.strip():
        return {"ok": False, "sentence": error or "Brooklyn terms were not fetched."}
    if re.search(r"CC BY-?\s*NC|non-?commercial", text, re.I):
        sentence = sentence_with(text, r"CC BY-?\s*NC|non-?commercial")
        return {"ok": False, "sentence": sentence, "reason": "Brooklyn terms are non-commercial, not CC0, CC BY, or CC BY-SA."}
    sentence = sentence_with(text, r"CC0|CC BY|Creative Commons")
    ok = bool(re.search(r"\bcc0\b|cc by(?!-nc)(?!-nd)", text, re.I))
    return {
        "ok": ok,
        "licence": "CC BY" if ok else "",
        "sentence": sentence or "Fetched Brooklyn terms did not state CC0, CC BY, or CC BY-SA.",
        "reason": "" if ok else "Fetched Brooklyn terms did not state an open licence.",
    }


def confirm_pma() -> dict:
    try:
        raw = cached_text("pma-openn.html", PMA_OPEN)
    except subprocess.CalledProcessError as exc:
        return {"ok": False, "sentence": f"Philadelphia Museum of Art open-data page was not fetched ({exc})."}
    plain = html_to_text(raw)
    if challenge(plain):
        return {"ok": False, "sentence": "Philadelphia open-data page returned a bot challenge."}
    meta = sentence_with(plain, r"waived all copyright and related or neighboring rights to its metadata")
    images = sentence_with(plain, r"free of known copyright restrictions and in the public domain")
    ok = "cc0" in plain.lower() and "public domain" in plain.lower() and "metadata" in plain.lower()
    return {
        "ok": ok,
        "licence": "CC0" if ok else "",
        "sentence": meta,
        "image_sentence": images,
        "page": plain,
    }


def harvest_pma_page(bag: Harvest, plain: str, licence: str) -> dict:
    """Scan the one open-data page. It lists manuscripts, not a painting search."""
    stats = {"inspected": 1, "accepted": 0, "with_image": 0, "queries": 1, "errors": 0}
    for phrase in LANDMARKS:
        if not contains_phrase(phrase, plain):
            continue
        island, reason = resolve_island(bag.atlas, phrase, plain)
        if reason or not island:
            bag.reject(
                island=island,
                title=f"Philadelphia Museum of Art manuscripts mentioning {phrase}",
                source_url=PMA_OPEN,
                external_id=f"pma-openn:{fold(phrase)[:40]}",
                licence=licence,
                evidence=f"Page text names {phrase} — Philadelphia Museum of Art on OPenn",
                reason=reason or "The open-data page does not give a painting, print, or sculpture title for this name.",
            )
    print(f"pma page scan accepted {stats['accepted']}", flush=True)
    return stats


def write_output(bag: Harvest, meta: dict) -> None:
    save_json(
        OUT,
        {
            "slug": "artwork-further",
            "generatedAt": utc_now(),
            "meta": meta,
            "rows": bag.rows + bag.rejected,
        },
    )


def source_record(source_id: str, used: bool, **extra) -> dict:
    record = {"id": source_id, "used": used}
    record.update(extra)
    return record


def main() -> None:
    atlas = Atlas()
    queries, unresolved = build_queries(atlas)
    print(f"queries {len(queries)} unresolved {unresolved}", flush=True)
    bag = Harvest(atlas)
    meta = {
        "licences": {},
        "sources": [],
        "queries": queries,
        "unresolved_phrases": unresolved,
        "skipped": [
            "Met, Cleveland, Art Institute of Chicago, National Gallery of Art, National Gallery London, Wikidata, Wikimedia Commons, Wellcome, and Yale were already harvested and were not queried.",
            "V&A, Tate, and Art UK were not queried.",
        ],
    }

    rijks = confirm_rijks()
    meta["licences"]["rijksmuseum"] = rijks.get("sentence") or "Rijksmuseum policy fetched; no CC0 sentence found."
    if rijks.get("image_sentence"):
        meta["licences"]["rijksmuseum_images"] = rijks["image_sentence"]
    if rijks.get("ok"):
        stats = harvest_rijks(bag, queries, rijks["licence"])
        meta["sources"].append(source_record("rijksmuseum", True, licence=rijks["licence"], url=RIJKS_POLICY, **stats))
        write_output(bag, meta)
    else:
        meta["sources"].append(source_record("rijksmuseum", False, reason=rijks.get("sentence") or "Licence not confirmed."))
        print("skip rijks", flush=True)

    harvard = confirm_harvard()
    meta["licences"]["harvard"] = harvard.get("sentence") or "Harvard licensing page fetched; no open-licence sentence found."
    if harvard.get("readme"):
        meta["licences"]["harvard_readme"] = harvard["readme"]
    if env_has("harvard"):
        reason = "A Harvard key is present, but the licensing page does not put images under CC0, CC BY, or CC BY-SA."
    else:
        reason = harvard["reason"]
        if harvard.get("sentence"):
            reason += " The licensing page says images are for personal, noncommercial use, so the API was not called."
    meta["sources"].append(source_record("harvard-art-museums", False, reason=reason))
    print("skip harvard", flush=True)

    walters = confirm_walters()
    meta["licences"]["walters"] = walters.get("sentence") or "Walters README fetched; no CC0 sentence found."
    if walters.get("rights"):
        meta["licences"]["walters_rights_page"] = walters["rights"]
    if walters.get("ok"):
        stats = harvest_walters(bag, queries, walters["licence"], bool(walters.get("images_open")))
        meta["sources"].append(
            source_record(
                "walters",
                True,
                licence=walters["licence"],
                url=WALTERS_README,
                images="CC0 URLs from the README; art.thewalters.org challenged the research user-agent, so the files were not re-downloaded",
                **stats,
            )
        )
        write_output(bag, meta)
    else:
        meta["sources"].append(source_record("walters", False, reason=walters.get("sentence") or "Licence not confirmed."))
        print("skip walters", flush=True)

    mia = confirm_mia()
    meta["licences"]["mia"] = mia.get("sentence") or "Mia README fetched; no CC0 sentence found."
    if mia.get("image_sentence"):
        meta["licences"]["mia_images"] = mia["image_sentence"]
    if mia.get("open_page"):
        meta["licences"]["mia_open_access_page"] = mia["open_page"]
    if mia.get("ok"):
        stats = harvest_mia(bag, queries, mia["licence"])
        meta["sources"].append(
            source_record(
                "minneapolis",
                True,
                licence=mia["licence"],
                url=MIA_README,
                images="omitted; README says images are not under the CC0 metadata licence and are limited to non-commercial use",
                **stats,
            )
        )
        write_output(bag, meta)
    else:
        meta["sources"].append(source_record("minneapolis", False, reason=mia.get("sentence") or "Licence not confirmed."))
        print("skip mia", flush=True)

    brooklyn = confirm_brooklyn()
    meta["licences"]["brooklyn"] = brooklyn.get("sentence") or "Brooklyn terms were not fetched."
    meta["sources"].append(
        source_record("brooklyn", False, reason=brooklyn.get("reason") or brooklyn.get("sentence") or "Licence not confirmed.")
    )
    print("skip brooklyn", flush=True)

    if len(bag.rows) < 25:
        pma = confirm_pma()
        meta["licences"]["philadelphia"] = pma.get("sentence") or "Philadelphia open-data page fetched; no CC0 sentence found."
        if pma.get("image_sentence"):
            meta["licences"]["philadelphia_images"] = pma["image_sentence"]
        if pma.get("ok"):
            stats = harvest_pma_page(bag, pma.get("page") or "", pma["licence"])
            meta["sources"].append(
                source_record(
                    "philadelphia",
                    True,
                    licence=pma["licence"],
                    url=PMA_OPEN,
                    note="OPenn manuscript list scanned; no separate painting search API is documented on that page.",
                    **stats,
                )
            )
        else:
            meta["sources"].append(
                source_record("philadelphia", False, reason=pma.get("sentence") or "Licence not confirmed.")
            )
            print("skip philadelphia", flush=True)
    else:
        meta["sources"].append(
            source_record(
                "philadelphia",
                False,
                reason=f"Not required: earlier catalogues accepted {len(bag.rows)} rows (threshold 25).",
            )
        )

    write_output(bag, meta)
    islands = sorted({item["island_name"] for item in bag.rows if item.get("island_name")})
    with_image = sum(1 for item in bag.rows if item.get("open_image"))
    print(
        f"wrote {OUT} accepted {len(bag.rows)} rejected {len(bag.rejected)} islands {len(islands)} with_image {with_image}",
        flush=True,
    )


if __name__ == "__main__":
    main()
