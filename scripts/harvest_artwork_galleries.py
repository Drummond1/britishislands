#!/usr/bin/env python3
"""Harvest cited artworks from gallery open-data the other passes do not use.

Tries the Victoria and Albert Museum, the National Gallery of Art (Washington)
open-data dump, and Smithsonian Open Access. A source is skipped unless its
own documentation states CC0, CC BY, CC BY-SA, or OGL. If those accepted rows
stay under 40, one further confirmed source is queried: the National Gallery,
London collection API (structured data CC0, narrative text CC BY; images are
CC BY-NC-ND and are not copied).

Writes only:
  data/interest/candidates/artwork-galleries.json
  data/cache_artwork_galleries/**

Does not publish, and does not edit islands.json.
"""

from __future__ import annotations

import csv
import html
import re
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from interest_categories import (  # noqa: E402
    Atlas,
    fold,
    http_json,
    load_env,
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

CACHE = ROOT / "data" / "cache_artwork_galleries"
OUT = ROOT / "data" / "interest" / "candidates" / "artwork-galleries.json"
UA = "isles-of-britain/0.1 (artwork-galleries; research)"

SLEEP_S = 0.4
INSPECT_PER_QUERY = 25
PER_ISLAND = 40
OVERALL = 500
MIN_EXTRA_AREA = 15
EXTRA_PHRASES = 80

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
    "Isle of Arran",
    "Jura",
    "Islay",
    "St Kilda",
    "Skellig",
    "Inishmore",
    "Achill",
    "Lundy",
    "Isle of Wight",
    "Ailsa Craig",
    "Bass Rock",
    "Burgh Island",
    "Tresco",
    "Caldey",
    "Bardsey",
    "Skomer",
    "Brownsea",
    "Fair Isle",
    "Channel Island",
    "Sark",
    "Alderney",
    "Herm",
    "Isle of Man",
]

VAM_DOCS = (
    "https://developers.vam.ac.uk/",
    "https://developers.vam.ac.uk/guide/v2/welcome.html",
    "https://www.vam.ac.uk/info/va-websites-terms-conditions",
)
NGA_README = "https://raw.githubusercontent.com/NationalGalleryOfArt/opendata/main/README.md"
NGA_IMAGES_DOC = "https://www.nga.gov/artworks/free-images-and-open-access"
NGA_OBJECTS = "https://raw.githubusercontent.com/NationalGalleryOfArt/opendata/main/data/objects.csv"
NGA_TEXT = "https://raw.githubusercontent.com/NationalGalleryOfArt/opendata/main/data/objects_text_entries.csv"
NGA_IMAGES = "https://raw.githubusercontent.com/NationalGalleryOfArt/opendata/main/data/published_images.csv"
NGA_DICT = "https://raw.githubusercontent.com/NationalGalleryOfArt/opendata/main/documentation/Data%20Dictionary.txt"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
NGL_LICENCE = "https://www.nationalgallery.org.uk/documentation/ngacuk/licences"
NGL_SEARCH = "https://data.ng.ac.uk/es/public/_search"

CORE_CLASSES = {"painting", "drawing", "print", "sculpture"}
PRINT_MEDIUM = re.compile(
    r"\b(etchings?|engravings?|aquatints?|lithographs?|woodcuts?|mezzotints?|drypoints?)\b",
    re.I,
)
ALLOWED_TYPE = re.compile(
    r"\b(paintings?|pictures?|drawings?|watercolours?|watercolors?|prints?|"
    r"etchings?|engravings?|sculptures?|murals?|aquatints?|lithographs?|"
    r"woodcuts?|mezzotints?)\b",
    re.I,
)
REJECT_TYPE = re.compile(
    r"\b(photographs?|photogravures?|photos?|daguerreotypes?|albumen|gelatin silver|"
    r"decorative arts?|ceramics?|porcelains?|textiles?|furniture|costumes?|"
    r"jewell?ery|silverware|glassware|medals?|coins?|sketchbooks?|volume)\b",
    re.I,
)
BARE_CUES = {
    "jura": ("isle", "island", "hebrides", "argyll", "craighouse", "paps", "scotland"),
    "herm": ("isle", "island", "channel", "guernsey", "sark", "jethou"),
    "alderney": ("isle", "island", "channel", "guernsey", "sark", "braye", "aurigny"),
}
JERSEY_CUES = ("channel", "gorey", "elizabeth castle", "mont orgueil", "st helier", "isle")
HOLY_ANGLES = ("anglesey", "ynys gybi", "holyhead", "caergybi", "ynys mon")
HOLY_LINDIS = ("lindisfarne", "northumberland", "farne")


def soften(text: str) -> str:
    text = (text or "").replace("’", "'").replace("‘", "'").replace("`", "'")
    return re.sub(r"\bSt\.", "St", text, flags=re.I)


def phrase_variants(phrase: str) -> list[str]:
    variants = [phrase]
    saint = re.sub(r"\bSt\.?\b", "Saint", phrase)
    if saint.lower() != phrase.lower():
        variants.append(saint)
    return variants


def has_phrase(phrase: str, text: str) -> bool:
    return any(phrase_in_text(soften(variant), soften(text)) for variant in phrase_variants(phrase))


def fetch_text(url: str, name: str, user_agent: str | None = None) -> str:
    dest = CACHE / "docs" / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 200:
        return dest.read_text(encoding="utf-8", errors="replace")
    raw = subprocess.check_output(
        ["curl", "-fsSL", "--max-time", "60", "-A", user_agent or UA, url],
    )
    text = raw.decode("utf-8", errors="replace")
    dest.write_text(text, encoding="utf-8")
    time.sleep(SLEEP_S)
    return text


def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<script.*?>.*?</script>", " ", raw)
    raw = re.sub(r"(?is)<style.*?>.*?</style>", " ", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(raw)).strip()


def sentence_with(text: str, pattern: str) -> str:
    plain = html_to_text(text)
    plain = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", plain)
    match = re.search(pattern, plain, re.I)
    if not match:
        return ""
    left = plain.rfind(". ", 0, match.start())
    right = plain.find(". ", match.end())
    if right == -1:
        right = plain.find(".", match.end())
    end = right + 1 if right != -1 else min(len(plain), match.end() + 220)
    snippet = re.sub(r"\s+", " ", plain[left + 1 : end]).strip()
    return snippet[:500]


def confirms_open(text: str) -> list[str]:
    """Return CC0 / CC BY / CC BY-SA / OGL kinds actually stated in the text."""
    plain = html_to_text(text)
    found = []
    if re.search(r"creative commons zero|\bcc0\b", plain, re.I):
        found.append("CC0")
    if re.search(r"\bcc by-sa\b|attribution-sharealike|cc-by-sa", plain, re.I):
        found.append("CC BY-SA")
    # "CC BY" must not be the start of CC BY-NC / CC BY-ND.
    if re.search(r"creative commons attribution 4\.0|\bcc by 4\.0\b|\bcc by\b(?!-)", plain, re.I):
        if re.search(r"creative commons attribution 4\.0(?!\s*international)?", plain, re.I) or re.search(
            r"\bcc by\b(?!-nc)(?!-nd)", plain, re.I
        ):
            found.append("CC BY")
    if re.search(r"open government licence", plain, re.I):
        found.append("OGL")
    # Drop a bare CC BY hit that only occurs inside CC BY-NC-ND wording.
    if "CC BY" in found and not re.search(
        r"creative commons attribution 4\.0 licence \(cc by\)|\bcc by\b(?!-nc)(?!-nd)",
        plain,
        re.I,
    ):
        found = [item for item in found if item != "CC BY"]
    return found


def download(url: str, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 100_000:
        print(f"cache {dest.name} ({dest.stat().st_size} bytes)", flush=True)
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".part")
    urls = [url]
    if "media.githubusercontent.com/media/" in url:
        urls.append(url.replace("https://media.githubusercontent.com/media/", "https://raw.githubusercontent.com/", 1))
    last_error = None
    for candidate in urls:
        print(f"download {candidate}", flush=True)
        try:
            subprocess.check_call(
                [
                    "curl",
                    "-fL",
                    "--retry",
                    "3",
                    "--retry-delay",
                    "2",
                    "--max-time",
                    "600",
                    "-A",
                    UA,
                    "-o",
                    str(partial),
                    candidate,
                ]
            )
            partial.replace(dest)
            time.sleep(SLEEP_S)
            return
        except subprocess.CalledProcessError as exc:
            last_error = exc
            print(f"download failed {candidate}: {exc}", flush=True)
    raise last_error or RuntimeError(f"download failed {url}")


def clean_markup(text: str) -> str:
    text = soften(text or "")
    text = re.sub(r"_([^_]{1,120})_", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def allowed_object(*parts: str) -> bool:
    classification = (parts[0] if parts else "") or ""
    medium = " ".join(parts[1:]) if len(parts) > 1 else ""
    if REJECT_TYPE.search(medium or ""):
        return False
    words = set(re.findall(r"[a-z]+", classification.lower()))
    if words & {"photograph", "decorative", "volume"}:
        return False
    if "technical" in words and "material" in words:
        return False
    if words & CORE_CLASSES or "picture" in words:
        return True
    # Prints catalogued under a portfolio still name the print medium.
    if "portfolio" in words and PRINT_MEDIUM.search(medium or ""):
        return True
    # Index renderings are watercolours and drawings, not the decorative objects.
    if {"index", "american", "design"} <= words and re.search(
        r"\b(watercolours?|watercolors?|drawings?|graphite|gouache)\b", medium or "", re.I
    ):
        return True
    return False


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
        "mural",
        "sculpture",
        "drawing",
        "print",
        "painting",
        "picture",
    ):
        if kind in blob:
            return "painting" if kind == "picture" else kind
    return "artwork"


def snippet(text: str, phrase: str) -> str:
    cleaned = clean_markup(text)
    match = re.search(r"\b" + re.escape(soften(phrase)) + r"\b", soften(cleaned), re.I)
    if not match:
        return cleaned[:240]
    start = max(0, match.start() - 90)
    end = min(len(cleaned), match.end() + 90)
    return cleaned[start:end].strip()


def resolve_phrase(atlas: Atlas, phrase: str) -> dict | None:
    island = match_island_phrase(atlas, phrase)
    if island:
        return island
    saint = re.sub(r"\bSt\.?\b", "Saint", phrase)
    if saint != phrase:
        return match_island_phrase(atlas, saint)
    return None


def build_queries(atlas: Atlas) -> tuple[list[tuple[str, dict]], list[str]]:
    queries: list[tuple[str, dict]] = []
    unresolved: list[str] = []
    seen: set[str] = set()

    def add(phrase: str, island: dict | None) -> None:
        token = soften(phrase).lower()
        if token in seen:
            return
        if island is None:
            unresolved.append(phrase)
            return
        if soften(phrase).lower() in {"orkney", "shetland", "jersey"}:
            unresolved.append(phrase)
            return
        seen.add(token)
        queries.append((phrase, island))
        for variant in phrase_variants(phrase)[1:]:
            variant_token = soften(variant).lower()
            if variant_token in seen:
                continue
            if resolve_phrase(atlas, variant):
                seen.add(variant_token)
                queries.append((variant, island))

    for phrase in LANDMARKS:
        add(phrase, resolve_phrase(atlas, phrase))
    extra = 0
    for phrase, island in search_phrases(atlas):
        if extra >= EXTRA_PHRASES:
            break
        if (island.get("area") or 0) < MIN_EXTRA_AREA:
            continue
        if soften(phrase).lower() in seen:
            continue
        resolved = resolve_phrase(atlas, phrase)
        if resolved is None:
            continue
        if soften(phrase).lower() in {"orkney", "shetland", "jersey"}:
            continue
        add(phrase, resolved)
        extra += 1
    return queries, unresolved


def place_ok(phrase: str, text: str, island: dict) -> bool:
    """Drop ambiguous hits the whole-word match would otherwise keep."""
    folded_phrase = soften(phrase).lower()
    name = (island.get("name") or "").lower()
    if "jersey" in folded_phrase or "jersey" in name:
        if not any(has_phrase(cue, text) or (cue in soften(text).lower() and " " in cue) for cue in JERSEY_CUES):
            return False
    if folded_phrase == "holy island":
        if any(has_phrase(cue, text) for cue in HOLY_LINDIS):
            return "lindisfarne" in name
        if any(has_phrase(cue, text) for cue in HOLY_ANGLES):
            return fold_name_is_holy(island)
        return False
    bare = folded_phrase.strip()
    cues = BARE_CUES.get(bare)
    if cues and not any(has_phrase(cue, text) for cue in cues):
        return False
    if bare in {"orkney", "shetland"}:
        return False
    return True


def fold_name_is_holy(island: dict) -> bool:
    return soften(island.get("name") or "").lower() in {"holy island"} and (island.get("area") or 0) > 20


def consider(phrase, island, title, description, kind_bits, seen, per_island, rows, source_fields):
    if len(rows) >= OVERALL or per_island[island["id"]] >= PER_ISLAND:
        return False
    blob = f"{title}\n{description}"
    if not has_phrase(phrase, blob):
        return False
    if not allowed_object(*kind_bits):
        return False
    if not place_ok(phrase, blob, island):
        return False
    field = "Title" if has_phrase(phrase, title) else "Description"
    quoted = title if field == "Title" else description
    institution = source_fields["institution"]
    evidence = f"{field}: {snippet(quoted, phrase)} — {institution}"
    kind = object_kind(*kind_bits)
    article = "an" if kind[:1].lower() in "aeiou" else "a"
    summary = (
        f"{title} is {article} {kind} in the {institution} collection; "
        f"the record names {island['name']}."
    )
    licence = source_fields["licence_title"] if field == "Title" else source_fields["licence_text"]
    image = source_fields.get("image")
    row = artwork_row(
        island=island,
        title=title,
        source_url=source_fields["source_url"],
        source_title=title,
        licence=licence,
        evidence=evidence,
        summary=summary,
        external_id=source_fields["external_id"],
        open_image=image,
        seen=seen,
    )
    if not row:
        return False
    rows.append(row)
    per_island[island["id"]] += 1
    print(f"  accept {source_fields['external_id']} {island['name']}: {title[:90]}", flush=True)
    return True


def harvest_nga(atlas_queries, seen, per_island) -> tuple[list[dict], dict]:
    stats = {"inspected": 0, "accepted": 0, "objects": 0}
    nga_dir = CACHE / "nga"
    objects_path = nga_dir / "objects.csv"
    text_path = nga_dir / "objects_text_entries.csv"
    download(NGA_OBJECTS, objects_path)
    download(NGA_TEXT, text_path)

    objects = []
    with objects_path.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        for rec in reader:
            rec = { (key or "").lower(): value for key, value in rec.items() }
            if str(rec.get("isvirtual") or "0").strip() == "1":
                continue
            classification = rec.get("classification") or ""
            medium = rec.get("medium") or ""
            if not allowed_object(classification, medium):
                continue
            title = clean_markup(rec.get("title") or "")
            if not title:
                continue
            objects.append(
                {
                    "id": (rec.get("objectid") or "").strip(),
                    "title": title,
                    "medium": medium,
                    "classification": classification,
                    "attribution": clean_markup(rec.get("attribution") or ""),
                    "description": "",
                }
            )
    by_id = {obj["id"]: obj for obj in objects if obj["id"]}
    stats["objects"] = len(by_id)
    print(f"nga objects of allowed type: {len(by_id)}", flush=True)

    with text_path.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        for rec in reader:
            rec = { (key or "").lower(): value for key, value in rec.items() }
            if (rec.get("texttype") or "").lower() != "brief_narrative":
                continue
            obj = by_id.get((rec.get("objectid") or "").strip())
            if not obj:
                continue
            narrative = clean_markup(rec.get("text") or "")
            if narrative and narrative not in obj["description"]:
                obj["description"] = (obj["description"] + " " + narrative).strip()
    for obj in by_id.values():
        obj["folded"] = fold(soften(f"{obj['title']}\n{obj['description']}"))

    rows = []
    inspected = defaultdict(int)
    with objects_path.open(newline="", encoding="utf-8", errors="replace") as handle:
        peek = csv.DictReader(handle)
        print("nga columns", [name for name in (peek.fieldnames or [])[:8]], flush=True)
    for phrase, island in atlas_queries:
        if len(rows) >= OVERALL:
            break
        for obj in by_id.values():
            if inspected[phrase] >= INSPECT_PER_QUERY or len(rows) >= OVERALL:
                break
            if per_island[island["id"]] >= PER_ISLAND:
                break
            if not any(phrase_in_text(soften(variant), obj["folded"]) for variant in phrase_variants(phrase)):
                continue
            inspected[phrase] += 1
            stats["inspected"] += 1
            source = {
                "institution": "National Gallery of Art, Washington",
                "licence_title": "CC0",
                "licence_text": "CC0",
                "source_url": f"https://www.nga.gov/collection/art-object-page.{obj['id']}.html",
                "external_id": f"nga:{obj['id']}",
            }
            if consider(
                phrase,
                island,
                obj["title"],
                obj["description"],
                (obj["classification"], obj["medium"]),
                seen,
                per_island,
                rows,
                source,
            ):
                stats["accepted"] += 1
    stats["by_phrase"] = {phrase: inspected[phrase] for phrase, _island in atlas_queries if inspected[phrase]}
    return rows, stats


def attach_nga_images(rows: list[dict], images_open: bool) -> int:
    if not images_open:
        return 0
    wanted = {}
    for row in rows:
        external = row.get("external_id") or ""
        if external.startswith("nga:"):
            wanted[external.split(":", 1)[1]] = row
    if not wanted:
        return 0
    path = CACHE / "nga" / "published_images.csv"
    download(NGA_IMAGES, path)
    chosen = {}
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        for rec in reader:
            rec = { (key or "").lower(): value for key, value in rec.items() }
            object_id = (rec.get("depictstmsobjectid") or "").strip()
            if object_id not in wanted:
                continue
            if str(rec.get("openaccess") or "").strip() != "1":
                continue
            thumb = (rec.get("iiifthumburl") or "").strip()
            if not thumb.startswith("http"):
                continue
            primary = (rec.get("viewtype") or "").lower() == "primary"
            previous = chosen.get(object_id)
            if previous and previous["primary"] and not primary:
                continue
            chosen[object_id] = {"thumb": thumb, "primary": primary}
    attached = 0
    for object_id, image in chosen.items():
        row = wanted[object_id]
        artist = ""
        # attribution stays institutional; the title already names the work.
        row["open_image"] = {
            "thumbUrl": image["thumb"],
            "pageUrl": row["source_url"],
            "attribution": f"{row['title']}. National Gallery of Art, Washington.",
            "licence": "public domain",
            "licenceUrl": NGA_IMAGES_DOC,
        }
        if artist:
            row["open_image"]["attribution"] = artist + " " + row["open_image"]["attribution"]
        attached += 1
    return attached


def nga_record(src: dict) -> dict | None:
    title = ""
    summary = src.get("summary") or {}
    if isinstance(summary, dict):
        title = summary.get("title") or ""
    if not title:
        for item in src.get("title") or []:
            if isinstance(item, dict) and item.get("value"):
                title = item["value"]
                break
    title = clean_markup(title)
    descriptions = []
    for item in src.get("description") or []:
        if not isinstance(item, dict):
            continue
        kind = (item.get("type") or "").lower()
        if kind and kind not in {"short text", "long text", ""}:
            continue
        descriptions.append(clean_markup(item.get("value") or item.get("formatted") or ""))
    classes = []
    materials = []
    for item in src.get("classification") or []:
        if isinstance(item, dict) and item.get("value"):
            classes.append(item["value"])
    for item in src.get("material") or []:
        if isinstance(item, dict) and item.get("value"):
            materials.append(str(item["value"]))
    number = ""
    for item in src.get("identifier") or []:
        if isinstance(item, dict) and item.get("type") in {"object number", "display number"} and item.get("value"):
            number = str(item["value"]).strip()
            break
    if not title or not number:
        return None
    return {
        "title": title,
        "description": " ".join(part for part in descriptions if part),
        "classification": " ".join(classes),
        "medium": " ".join(materials),
        "number": number,
    }


def harvest_ngl(queries, seen, per_island) -> tuple[list[dict], dict]:
    stats = {"inspected": 0, "accepted": 0, "queries": 0}
    rows = []
    cache = CACHE / "ngl"
    cache.mkdir(parents=True, exist_ok=True)
    for phrase, island in queries:
        if len(rows) >= OVERALL:
            break
        if per_island[island["id"]] >= PER_ISLAND:
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", soften(phrase).lower()).strip("-")[:80]
        path = cache / f"{slug}.json"
        if path.exists():
            payload = load_json(path, {})
        else:
            body = {
                "size": INSPECT_PER_QUERY,
                "_source": ["summary", "title", "description", "classification", "material", "identifier"],
                "query": {
                    "bool": {
                        "must": [
                            {
                                "bool": {
                                    "should": [
                                        {"match_phrase": {"summary.title": phrase}},
                                        {"match_phrase": {"title.value": phrase}},
                                        {"match_phrase": {"description.value": phrase}},
                                        {"match_phrase": {"description.formatted": phrase}},
                                    ],
                                    "minimum_should_match": 1,
                                }
                            },
                            {"term": {"@datatype.base": "object"}},
                        ]
                    }
                },
            }
            try:
                payload = http_json(
                    NGL_SEARCH,
                    data=json_bytes(body),
                    headers={"Content-Type": "application/json"},
                    timeout=60,
                    user_agent=UA,
                )
            except subprocess.CalledProcessError as exc:
                print(f"ngl query failed {phrase!r}: {exc}", flush=True)
                payload = {"hits": {"hits": []}}
            save_json(path, payload)
            time.sleep(SLEEP_S)
        stats["queries"] += 1
        hits = ((payload.get("hits") or {}).get("hits")) or []
        for hit in hits[:INSPECT_PER_QUERY]:
            if len(rows) >= OVERALL or per_island[island["id"]] >= PER_ISLAND:
                break
            parsed = nga_record(hit.get("_source") or {})
            if not parsed:
                continue
            stats["inspected"] += 1
            phrase_in_title = has_phrase(phrase, parsed["title"])
            source = {
                "institution": "National Gallery, London",
                "licence_title": "CC0",
                "licence_text": "CC BY 4.0",
                "source_url": f"https://www.nationalgallery.org.uk/paintings/{parsed['number']}",
                "external_id": f"national-gallery-london:{parsed['number']}",
            }
            if consider(
                phrase,
                island,
                parsed["title"],
                parsed["description"],
                (parsed["classification"], parsed["medium"]),
                seen,
                per_island,
                rows,
                source,
            ):
                stats["accepted"] += 1
            elif phrase_in_title:
                pass
    return rows, stats


def json_bytes(payload: dict) -> bytes:
    import json

    return json.dumps(payload).encode("utf-8")


def env_has(*needles: str) -> bool:
    env = load_env()
    for key, value in env.items():
        if not value.strip():
            continue
        hay = key.lower()
        if any(needle in hay for needle in needles):
            return True
    return False


def main() -> None:
    atlas = Atlas()
    seen = existing_artwork_keys()
    # This script rewrites its own candidate file. Rows already in that file
    # are not foreign duplicates; other harvesters' files still count.
    previous = load_json(OUT, {})
    for item in previous.get("rows") or []:
        island_id = item.get("island_id") or ""
        title = item.get("title") or ""
        if item.get("status") == "accepted" and island_id and title:
            seen.discard((island_id, fold(title)))
    queries, unresolved = build_queries(atlas)
    print(f"queries {len(queries)} unresolved {len(unresolved)}", flush=True)
    if unresolved:
        print("unresolved: " + ", ".join(unresolved), flush=True)

    licences = {}
    sources = []
    rows: list[dict] = []

    vam_chunks = []
    for index, url in enumerate(VAM_DOCS):
        try:
            vam_chunks.append(fetch_text(url, f"vam-{index}.html"))
        except subprocess.CalledProcessError as exc:
            print(f"vam docs fetch failed {url}: {exc}", flush=True)
    vam_text = "\n".join(vam_chunks)
    vam_open = confirms_open(vam_text) if vam_text else []
    vam_quote = sentence_with(vam_text, r"non-commercial personal and educational purposes")
    if not vam_quote:
        vam_quote = sentence_with(vam_text, r"section 9\.3")
    licences["vam"] = vam_quote or "V&A docs fetched; no CC0, CC BY, CC BY-SA, or OGL sentence found."
    if vam_open:
        sources.append({"id": "vam", "used": False, "reason": f"open labels {vam_open} contradicted by non-commercial terms; not queried"})
    else:
        sources.append(
            {
                "id": "vam",
                "used": False,
                "reason": "Victoria and Albert Museum terms (section 9) are non-commercial API terms, not CC0, CC BY, CC BY-SA, or OGL.",
            }
        )
    print("skip vam:", sources[-1]["reason"], flush=True)

    nga_readme = ""
    nga_images_doc = ""
    try:
        nga_readme = fetch_text(NGA_README, "nga-readme.md")
    except subprocess.CalledProcessError as exc:
        print(f"nga readme failed: {exc}", flush=True)
    licences["nga"] = sentence_with(nga_readme, r"Creative Commons Zero|CC0")
    nga_open = "CC0" in confirms_open(nga_readme)
    images_open = False
    try:
        nga_images_doc = fetch_text(NGA_IMAGES_DOC, "nga-open-access.html", user_agent=BROWSER_UA)
        licences["nga_images"] = sentence_with(
            nga_images_doc, r"public domain|free of charge for any use|Open Access"
        )
        plain_images = html_to_text(nga_images_doc)
        images_open = bool(re.search(r"public domain", plain_images, re.I)) and bool(
            re.search(r"any use|commercial or non-commercial", plain_images, re.I)
        )
    except subprocess.CalledProcessError as exc:
        print(f"nga image policy page blocked: {exc}", flush=True)
        try:
            nga_dict = fetch_text(NGA_DICT, "nga-dictionary.txt")
            licences["nga_images"] = sentence_with(
                nga_dict, r"1 = open access image with no usage restrictions"
            )
            # The dump's own dictionary does not call image files CC0 or public domain.
            # Links are CC0; "the content of the linked sites might still be copyrighted."
            images_open = False
        except subprocess.CalledProcessError as dict_exc:
            licences["nga_images"] = "Open-access image policy page and data dictionary were not both readable."
            print(f"nga dictionary failed: {dict_exc}", flush=True)

    per_island = defaultdict(int)
    nga_stats = {"accepted": 0}
    if nga_open:
        nga_rows, nga_stats = harvest_nga(queries, seen, per_island)
        attached = attach_nga_images(nga_rows, images_open)
        rows.extend(nga_rows)
        sources.append(
            {
                "id": "nga",
                "used": True,
                "accepted": nga_stats["accepted"],
                "inspected": nga_stats["inspected"],
                "open_images": attached,
                "url": NGA_README,
            }
        )
        print(f"nga accepted {nga_stats['accepted']} images {attached}", flush=True)
    else:
        sources.append({"id": "nga", "used": False, "reason": "README did not confirm CC0."})
        print("skip nga: licence not confirmed", flush=True)

    if env_has("smithsonian", "si_api"):
        sources.append({"id": "smithsonian", "used": False, "reason": "Key present but this pass does not call Smithsonian; licence page was not confirmed."})
    else:
        sources.append({"id": "smithsonian", "used": False, "reason": "No Smithsonian API key in .env.local."})
        licences["smithsonian"] = "Skipped: no Smithsonian-related key in .env.local."
    for source_id, needles in (
        ("rijksmuseum", ("rijks",)),
        ("harvard-art-museums", ("harvard",)),
        ("europeana", ("europeana",)),
    ):
        if env_has(*needles):
            sources.append({"id": source_id, "used": False, "reason": "Key is present; not used. This pass adds only one extra source, and only when it is confirmed open."})
        else:
            sources.append({"id": source_id, "used": False, "reason": "No API key in .env.local."})

    if len(rows) < 40:
        ngl_doc = ""
        try:
            ngl_doc = fetch_text(NGL_LICENCE, "ngl-licences.html")
        except subprocess.CalledProcessError as exc:
            print(f"ngl licence page failed: {exc}", flush=True)
        plain_ngl = html_to_text(ngl_doc)
        def ngl_line(pattern: str) -> str:
            match = re.search(pattern, plain_ngl, re.I)
            return re.sub(r"\s+", " ", match.group(0)).strip() if match else ""

        licences["national-gallery-london"] = ngl_line(
            r"Structured data \(as opposed to narrative texts\) are released under a Creative Commons Zero dedication \( ?CC0 ?\)"
        )
        licences["national-gallery-london_text"] = ngl_line(
            r"Descriptions, notes and all other narrative text content are licensed under a Creative Commons Attribution 4\.0 licence \( ?CC BY ?\)"
        )
        licences["national-gallery-london_images"] = ngl_line(
            r"Images are licensed under a Creative Commons Attribution-NonCommercial-NoDerivs 4\.0 licence \( ?CC BY-NC-ND ?\)"
        )
        ngl_kinds = confirms_open(ngl_doc)
        if "CC0" in ngl_kinds and "CC BY" in ngl_kinds:
            ngl_rows, ngl_stats = harvest_ngl(queries, seen, per_island)
            rows.extend(ngl_rows)
            sources.append(
                {
                    "id": "national-gallery-london",
                    "used": True,
                    "accepted": ngl_stats["accepted"],
                    "inspected": ngl_stats["inspected"],
                    "queries": ngl_stats["queries"],
                    "url": NGL_LICENCE,
                    "images": "not used; page states CC BY-NC-ND",
                }
            )
            print(f"ngl accepted {ngl_stats['accepted']}", flush=True)
        else:
            sources.append(
                {
                    "id": "national-gallery-london",
                    "used": False,
                    "reason": f"Licence page did not confirm both CC0 and CC BY (found {ngl_kinds}).",
                }
            )
    else:
        sources.append(
            {
                "id": "national-gallery-london",
                "used": False,
                "reason": f"Not required: V&A + NGA accepted {len(rows)} rows (threshold 40).",
            }
        )

    payload = {
        "slug": "artwork-galleries",
        "generatedAt": utc_now(),
        "sources": sources,
        "licences": licences,
        "unresolved_phrases": unresolved,
        "rows": rows,
    }
    save_json(OUT, payload)
    islands = sorted({row["island_name"] for row in rows})
    print(f"wrote {OUT} rows {len(rows)} islands {len(islands)}", flush=True)
    for name in islands:
        count = sum(1 for row in rows if row["island_name"] == name)
        print(f"  {count:3}  {name}", flush=True)


if __name__ == "__main__":
    main()
