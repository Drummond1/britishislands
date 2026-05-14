#!/usr/bin/env python3
"""
Curated gallery sample for 10 flagship islands.

For each of the ten sample islands, build a curated, diverse, beautifully
representative gallery of 6-8 photographs by:

  1. Pooling candidate Commons filenames from three sources:
       - the island's Wikidata Commons category (P373 / sitelink) plus a
         one-hop walk into useful sub-categories (e.g. "Beaches of <X>")
       - the island's Wikipedia article (every image referenced in the
         en-wiki page that lives on Commons)
       - whatever already lives in islands.json + galleries.json for that
         island (so the existing primary is preserved and re-scored)

  2. Fetching full Commons imageinfo + extmetadata for each candidate.

  3. Scoring each candidate on:
       - quality badge (Quality / Featured / Valued)
       - resolution (>= 1600 px wide preferred)
       - has structured caption + attributable author
       - photo-vs-document (rejects maps, logos, charts, SVGs)
       - name match against the island's known variants
       - geographic anchor (nation / archipelago name in caption/categories)

  4. Categorising each candidate into one of:
       landscape, heritage, coast, harbour, wildlife,
       aerial, atmospheric, detail
     and picking the top scorer from each present category until we have
     between MIN_PHOTOS and MAX_PHOTOS for the island.

Outputs:
    data/galleries_curated.json    keyed by island ID, value is
                                   { "images": [...], "curatedAt": iso,
                                     "sources": ["wd-category", ...] }
    data/curated_galleries_report.json  per-island audit log

The image schema is intentionally identical to the existing islands.json
images[] schema (url, fullUrl, source, sourceRef, sourcePageUrl, license,
licenseUrl, attribution, caption, fileName, primary). Frontend treats
curated entries as a *replacement* for the legacy galleries.json extras
when both exist.

Run:
    python3 scripts/curate_galleries_sample.py             # all 10
    python3 scripts/curate_galleries_sample.py --only iona # one island
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

# Reuse the well-tested v3 helpers for Commons + Wikidata access. The v3
# script uses urllib.request which works fine for the small volume of
# calls we make here (10 islands × ~3-4 endpoints).
sys.path.insert(0, str(ROOT / "scripts"))
from enrich_images_v3 import (  # noqa: E402
    _canon_filename,
    _get_json,
    _load_cache,
    _save_cache,
    _strip_html,
    category_members,
    commons_category_for_qid,
    commons_page_url,
    commons_thumb_url,
    fetch_commons_meta,
    CACHE_CC,
    CACHE_CM,
    COMMONS_API,
    DELAY_S,
)

OUT_PATH = DATA / "galleries_curated.json"
REPORT_PATH = DATA / "curated_galleries_report.json"
ISLANDS_PATH = DATA / "islands.json"
GALLERIES_PATH = DATA / "galleries.json"

# Sample roster: ten islands chosen for varied nation, archipelago and
# character. The keys are the island IDs that exist in islands.json today.
SAMPLE_ISLANDS: list[str] = [
    "isle-of-skye",          # Scotland · Inner Hebrides · mountains
    "iona",                  # Scotland · Inner Hebrides · abbey + white beaches
    "staffa",                # Scotland · Inner Hebrides · basalt columns
    "lindisfarne",           # England · tidal causeway · monastic
    "isle-of-wight",         # England · chalk cliffs · Needles
    "osm-relation-6046655",  # Wales · Bardsey / Ynys Enlli · pilgrimage
    "rathlin",               # Northern Ireland · puffin colony
    "osm-relation-6045552",  # Ireland · Inishmore · Dún Aonghasa
    "osm-way-2956937",       # Crown Dependency · Sark · no-cars cliff-top
    "lundy",                 # England · Bristol Channel · granite + puffins
]

# Min/max photos in the final curated gallery (lead + extras combined).
MIN_PHOTOS = 6
MAX_PHOTOS = 8

# Maximum sub-categories of the main Commons category to walk into.
SUBCAT_LIMIT = 6
SUBCAT_TOPICS = (
    "beaches", "cliffs", "harbours", "lighthouses",
    "churches", "abbey", "castle", "village",
    "wildlife", "fauna", "puffins", "seals",
    "landscape", "panoramas", "aerial",
)

# Resolution thresholds used by the scorer.
LOW_RES_W = 1024  # below this, heavy penalty
GOOD_RES_W = 1600  # at/above this, bonus
EXC_RES_W = 2800  # bonus for crisp prints

# Categorisation keyword bags. Order matters: the FIRST bag matched wins,
# so "aerial" beats "landscape" for an aerial photo.
CATEGORIES: list[tuple[str, tuple[str, ...]]] = [
    (
        "aerial",
        ("aerial", "from the air", "drone", "from above", "satellite"),
    ),
    (
        "atmospheric",
        ("sunset", "sunrise", "dawn", "dusk", "mist", "fog", "storm",
         "snow", "winter", "rainbow", "moonlight", "night"),
    ),
    (
        "wildlife",
        ("puffin", "seal ", "seabird", "gannet", "razorbill", "fulmar",
         "guillemot", "deer", "soay sheep", "manx shearwater", "tern",
         "kittiwake", "wildlife", "ponies", "horses on", "fauna"),
    ),
    (
        "heritage",
        ("abbey", "priory", "castle", "lighthouse", "fort", "broch",
         "chapel", "church", "cathedral", "tower", "monastery",
         "round tower", "dún aonghasa", "dun aonghasa", "village hall",
         "henge", "ruin"),
    ),
    (
        "harbour",
        ("harbour", "harbor", "pier", "quay", "jetty", "marina",
         "ferry terminal", "boatyard", "fishing boat"),
    ),
    (
        "coast",
        ("cliff", "cliffs", "stack", "arch", "cove", "bay", "beach",
         "shore", "shoreline", "coast", "rocks", "geo "),
    ),
    (
        "landscape",
        ("mountain", "ridge", "hill", "moor", "moorland", "valley",
         "loch", "lake", "river", "meadow", "view", "panorama",
         "skyline", "from "),
    ),
]

# Patterns that disqualify a file outright (in filename or caption).
NON_PHOTO_RE = re.compile(
    r"(?:^|[\b_ \-])(?:"
    r"flag|coat[_ \-]of[_ \-]arms|crest|emblem|seal[_ \-]of|logo|badge|"
    r"location[_ \-]map|locator[_ \-]map|outline[_ \-]map|"
    r"map[_ \-]of|map[_ \-]showing|"
    r"sketch[_ \-]map|chart[_ \-]of|"
    r"plat[_ \-]of|atlas[_ \-]of|"
    r"floor[_ \-]plan|plan[_ \-]of|"
    r"diagram|graph|"
    r"stamp[_ \-]of|coin|banknote|postmark|"
    r"poster|advert|"
    r"painting|engraving|"
    r"book[_ \-]cover|page[_ \-]from|"
    r"dpla[_ \-]|dpla[A-Z]"
    r")",
    re.IGNORECASE,
)
NON_PHOTO_EXT = (".svg", ".pdf", ".tif", ".tiff", ".djvu", ".ogv", ".webm")

# Tokens that appear in Commons category strings for files that are not
# photographs of the place. Any match disqualifies the candidate.
NON_PHOTO_CATEGORY_TOKENS = (
    "paintings of", "paintings by", "paintings in",
    "drawings of", "drawings by", "drawings in",
    "engravings of", "engravings by",
    "watercolour", "watercolor",
    "lithograph", "etching",
    "artworks",
    "pd-art",
    "maps of", "maps showing", "old maps", "antique maps",
    "historical maps", "1800s maps", "1810s maps", "1820s maps",
    "1830s maps", "1840s maps", "1850s maps", "1860s maps",
    "1870s maps", "1880s maps", "1890s maps", "1900s maps",
    "1910s maps", "1920s maps", "1930s maps",
    "atlases", "atlas of",
    "charts of", "nautical charts",
    "illustrations from", "illustrations of",
    "book illustrations",
    "diagrams of",
    "stamps of", "coins of", "banknotes",
    "posters", "advertisements",
    "logos", "coats of arms",
    "scans of",
)


def _norm(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower()


def _name_variants(island: dict) -> list[str]:
    """All forms we'll treat as a 'mention' of this island."""
    bag: set[str] = set()
    raw_keys = [
        island.get("name") or "",
        island.get("altName") or "",
    ]
    for v in raw_keys:
        v = (v or "").strip()
        if not v:
            continue
        nv = _norm(v)
        bag.add(nv)
        # Strip common honorifics and add cleaned variants.
        cleaned = nv
        for prefix in ("isle of ", "the "):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):]
        bag.add(cleaned)
        # Variant without trailing " island".
        if cleaned.endswith(" island"):
            bag.add(cleaned[: -len(" island")])
    # Manually-asserted Gaelic / Irish / Welsh names for the ten samples.
    cultural = {
        "iona": ("ì chaluim chille",),
        "isle-of-skye": ("an t-eilean sgitheanach", "eilean a' cheò"),
        "rathlin": ("reachlainn", "reachra"),
        "staffa": ("stafa",),
        "lindisfarne": ("holy island of lindisfarne", "lindisfarena"),
        "lundy": ("lundy island",),
        "osm-relation-6046655": ("bardsey", "ynys enlli", "ynys-enlli"),
        "osm-relation-6045552": ("inishmore", "inis mor", "inis mór", "árainn", "arainn"),
        "osm-way-2956937": ("sark", "sercq", "île de sercq"),
        "isle-of-wight": ("isle of wight", "wight", "vectis"),
    }
    for cv in cultural.get(island.get("id", ""), ()):
        bag.add(_norm(cv))
    return [v for v in bag if len(v) >= 3]


def _mentions(text: str, variants: list[str]) -> bool:
    """True if any variant appears as a whole-phrase substring."""
    if not text:
        return False
    t = _norm(text)
    return any(re.search(rf"(?<![a-z0-9]){re.escape(v)}(?![a-z0-9])", t) for v in variants)


def _looks_like_non_photo(filename: str, caption: str = "", categories: str = "") -> bool:
    if not filename:
        return True
    fl = filename.lower()
    if fl.endswith(NON_PHOTO_EXT):
        return True
    if NON_PHOTO_RE.search(filename):
        return True
    if caption and NON_PHOTO_RE.search(caption):
        return True
    # Commons categories are the most reliable signal: e.g. "Paintings of
    # Iona|Maps of Iona|Artworks…". One match disqualifies.
    if categories:
        cl = categories.lower()
        if any(tok in cl for tok in NON_PHOTO_CATEGORY_TOKENS):
            return True
    return False


def categorise(meta: dict) -> str:
    """Return a single category label using whole-word matching."""
    blob = " ".join(
        [
            (meta.get("fileName") or ""),
            (meta.get("caption") or ""),
            (meta.get("categories") or ""),
        ]
    ).lower()
    for label, kws in CATEGORIES:
        for kw in kws:
            # Whole-word / phrase match — prevents "tern" matching "in*tern*al"
            # or "bay" matching "Bayley". Trailing-space keywords already
            # encode a word boundary on the right, just need the left.
            pat = r"(?<![a-z0-9])" + re.escape(kw.strip()) + r"(?![a-z0-9])"
            if re.search(pat, blob):
                return label
    return "landscape"


def quality_badge(meta: dict) -> str:
    """Return Featured | Quality | Valued | '' from category memberships."""
    cats = (meta.get("categories") or "").lower()
    if "featured pictures on wikimedia commons" in cats or "featured picture" in cats:
        return "Featured"
    if "quality images" in cats or "qualityimage" in cats:
        return "Quality"
    if "valued images" in cats:
        return "Valued"
    return ""


def score(meta: dict, island: dict) -> tuple[int, dict]:
    """Heuristic score in [-200, 200]. Returns (score, breakdown)."""
    breakdown: dict[str, int] = {}
    s = 50  # baseline

    variants = _name_variants(island)
    fn = meta.get("fileName") or ""
    cap = meta.get("caption") or ""
    cats = meta.get("categories") or ""

    # Reject files we couldn't fetch metadata for at all (descriptionurl
    # missing implies the file isn't actually on Commons under that name).
    if not meta.get("descriptionUrl") and not meta.get("url"):
        breakdown["empty-meta"] = -200
        return -200, breakdown

    if _looks_like_non_photo(fn, cap, cats):
        breakdown["non-photo"] = -200
        return -200, breakdown

    # Hard requirement: the island name must appear somewhere (filename,
    # caption or categories). Without this, Wikipedia article-image walks
    # leak unrelated illustrations (e.g. "Fogo Isle" arriving via the IoW
    # article). Files whose metadata is too thin to verify are dropped.
    name_appears = (
        _mentions(fn, variants)
        or _mentions(cap, variants)
        or _mentions(cats, variants)
    )
    if not name_appears:
        breakdown["no-name-anchor"] = -200
        return -200, breakdown

    # Reject obvious pre-1920 artworks: filename or caption containing a
    # year in the 1600-1919 range, OR an "(18thC)/(19thC)" tag.
    if re.search(r"\((1[6-9]\d{2}|190\d|191\d)\b|\b(?:18thC|19thC|17thC|16thC)\b", fn + " " + cap):
        breakdown["historical-date"] = -200
        return -200, breakdown

    # Name match: filename, caption, categories.
    if _mentions(fn, variants):
        s += 25
        breakdown["name-in-filename"] = 25
    if _mentions(cap, variants):
        s += 15
        breakdown["name-in-caption"] = 15
    if _mentions(cats, variants):
        s += 10
        breakdown["name-in-categories"] = 10

    # Quality badges.
    badge = quality_badge(meta)
    if badge == "Featured":
        s += 60
        breakdown["badge-featured"] = 60
    elif badge == "Quality":
        s += 35
        breakdown["badge-quality"] = 35
    elif badge == "Valued":
        s += 20
        breakdown["badge-valued"] = 20

    # Resolution.
    w = meta.get("width") or 0
    if w >= EXC_RES_W:
        s += 25
        breakdown["res-exc"] = 25
    elif w >= GOOD_RES_W:
        s += 15
        breakdown["res-good"] = 15
    elif 0 < w < LOW_RES_W:
        s -= 25
        breakdown["res-low"] = -25

    # Has named attribution.
    if (meta.get("attribution") or "").strip():
        s += 5
        breakdown["has-attribution"] = 5

    # Has structured caption (not just filename echo).
    capN = cap.strip()
    if capN and capN.lower() != fn.lower().rsplit(".", 1)[0].replace("_", " ").lower():
        s += 5
        breakdown["has-caption"] = 5

    # Mime type penalty (only true raster photos welcome).
    mime = (meta.get("mime") or "").lower()
    if mime and not mime.startswith("image/"):
        s -= 100
        breakdown["non-image-mime"] = -100
    if mime in ("image/svg+xml", "image/tiff"):
        s -= 50
        breakdown["bad-mime"] = -50

    return s, breakdown


_SERIES_RE = re.compile(r"[\s_\-]*\(\s*\d+\s*\)\s*\.(?:jpe?g|png|webp)$", re.IGNORECASE)


def _series_key(fn: str, attr: str) -> str:
    """Approximate key that groups members of a photographer's series.

    Examples that collide on the same key:
      "2016 - Skye (25751180664).jpg" and "2016 - Skye (25751183274).jpg"
        attributed to the same uploader.
    """
    stem = _SERIES_RE.sub("", fn)
    # Also strip trailing "_NNN" or "-NNN".
    stem = re.sub(r"[\s_\-]+\d{2,}\s*\.(?:jpe?g|png|webp)$", "", stem, flags=re.IGNORECASE)
    stem_words = re.split(r"[\s_\-]+", stem)[:4]
    stem_key = " ".join(stem_words).lower()
    return f"{stem_key}|{(attr or '').lower()[:40]}"


def pick_diverse(
    pool: list[dict], island: dict, min_n: int = MIN_PHOTOS, max_n: int = MAX_PHOTOS
) -> list[dict]:
    """Pick up to max_n images preferring diversity across CATEGORIES."""
    ordered_cats = [c for c, _ in CATEGORIES]
    chosen: list[dict] = []
    seen_files: set[str] = set()
    seen_series: set[str] = set()

    def _take(cand: dict) -> None:
        chosen.append(cand)
        seen_files.add(cand["fileName"])
        seen_series.add(_series_key(cand["fileName"], cand.get("attribution") or ""))

    def _series_clash(cand: dict) -> bool:
        return _series_key(cand["fileName"], cand.get("attribution") or "") in seen_series

    # 1) Force the existing primary first, if it scored above the floor.
    primary = next((p for p in pool if p.get("__is_primary")), None)
    if primary and primary["__score"] > 0:
        _take(primary)

    # 2) Walk categories in our preferred order, picking the top-scoring
    #    unchosen file in each, skipping series-mates of an already-chosen
    #    file so one prolific uploader can't dominate the gallery.
    by_cat: dict[str, list[dict]] = {c: [] for c in ordered_cats}
    for cand in pool:
        cat = cand.get("__category", "landscape")
        by_cat.setdefault(cat, []).append(cand)
    for cat in ordered_cats:
        if len(chosen) >= max_n:
            break
        bucket = sorted(by_cat.get(cat, []), key=lambda x: -x["__score"])
        for cand in bucket:
            if cand["fileName"] in seen_files:
                continue
            if cand["__score"] <= 0:
                break
            if _series_clash(cand):
                continue
            _take(cand)
            break  # one per category in first pass

    # 3) Second pass: if we're below min_n, fill from highest-scoring
    #    remaining files regardless of category, still avoiding series.
    if len(chosen) < min_n:
        remaining = sorted(
            (c for c in pool if c["fileName"] not in seen_files),
            key=lambda x: -x["__score"],
        )
        for cand in remaining:
            if len(chosen) >= max_n:
                break
            if cand["__score"] <= 0:
                break
            if _series_clash(cand):
                continue
            _take(cand)

    # 4) Last-resort pass: if still below min_n, allow series mates so
    #    that a thin pool (e.g. Lindisfarne) doesn't end with an empty
    #    gallery. Quality still bounded by __score > 0.
    if len(chosen) < min_n:
        remaining = sorted(
            (c for c in pool if c["fileName"] not in seen_files),
            key=lambda x: -x["__score"],
        )
        for cand in remaining:
            if len(chosen) >= max_n:
                break
            if cand["__score"] <= 0:
                break
            _take(cand)

    return chosen


# ---------- Candidate sources ----------

def candidates_from_commons_category(qid: str, cc_cache: dict) -> list[str]:
    """Walk the Commons category attached to the Wikidata Q-ID, one hop
    into useful sub-categories."""
    if not qid:
        return []
    sl_map = commons_category_for_qid([qid], cc_cache)
    sitelink = sl_map.get(qid, "")
    if not sitelink:
        return []
    out: list[str] = list(category_members(sitelink, limit=80))

    # One-hop subcat walk. Fetch the list of sub-categories of the main
    # category and pull files from those whose name mentions a topic.
    if sitelink.startswith("Category:"):
        params = {
            "action": "query",
            "format": "json",
            "list": "categorymembers",
            "cmtitle": sitelink,
            "cmtype": "subcat",
            "cmlimit": "100",
        }
        try:
            payload = _get_json(COMMONS_API, params)
            members = (payload.get("query") or {}).get("categorymembers") or []
        except Exception as exc:
            print(f"  subcat fetch failed for {sitelink}: {exc!r}", file=sys.stderr)
            members = []
        picked = 0
        for m in members:
            if picked >= SUBCAT_LIMIT:
                break
            title = m.get("title", "")
            tl = title.lower()
            # Skip subcats that almost certainly hold non-photo material.
            if any(tok in tl for tok in NON_PHOTO_CATEGORY_TOKENS):
                continue
            if not any(t in tl for t in SUBCAT_TOPICS):
                continue
            out.extend(category_members(title, limit=30))
            picked += 1
            time.sleep(DELAY_S)
    return out


def candidates_from_wikipedia(island: dict) -> list[str]:
    """List Commons-hosted image filenames used in the en-wiki article."""
    name = island.get("name") or ""
    if not name:
        return []
    candidates_titles = [name]
    # Disambiguation hints for islands sharing names with mainland places.
    candidates_titles.append(f"{name} (island)")
    # Per-island manual page overrides for the ten samples.
    overrides = {
        "isle-of-skye": ["Isle of Skye"],
        "iona": ["Iona"],
        "staffa": ["Staffa"],
        "lindisfarne": ["Lindisfarne", "Holy Island, Northumberland"],
        "isle-of-wight": ["Isle of Wight"],
        "osm-relation-6046655": ["Bardsey Island", "Ynys Enlli"],
        "rathlin": ["Rathlin Island"],
        "osm-relation-6045552": ["Inishmore", "Inis Mór"],
        "osm-way-2956937": ["Sark"],
        "lundy": ["Lundy"],
    }
    iid = island.get("id", "")
    if iid in overrides:
        candidates_titles = overrides[iid] + candidates_titles
    if "wikipedia" in island and island["wikipedia"]:
        candidates_titles.insert(0, island["wikipedia"])
    seen: set[str] = set()
    out: list[str] = []
    for title in candidates_titles:
        params = {
            "action": "query",
            "format": "json",
            "prop": "images",
            "imlimit": "60",
            "titles": title,
            "redirects": 1,
        }
        try:
            payload = _get_json("https://en.wikipedia.org/w/api.php", params)
        except Exception as exc:
            print(f"  wp images failed for {title}: {exc!r}", file=sys.stderr)
            continue
        pages = (payload.get("query") or {}).get("pages") or {}
        for _pid, page in pages.items():
            if page.get("missing"):
                continue
            for img in page.get("images") or []:
                t = img.get("title", "")
                if not t.startswith("File:"):
                    continue
                fn = _canon_filename(t)
                if fn in seen:
                    continue
                seen.add(fn)
                out.append(fn)
        if out:
            break
        time.sleep(DELAY_S)
    return out


def candidates_from_commons_text(island: dict, limit: int = 30) -> list[str]:
    """Last-ditch fallback: Commons file search by island name. Used when
    the Wikidata category and Wikipedia article between them yield fewer
    than MIN_PHOTOS candidates. Strict name-anchor check in score() will
    still filter out homonyms."""
    name = island.get("name") or ""
    if not name:
        return []
    queries: list[str] = [name]
    # Add common disambiguation hints.
    nation = (island.get("nation") or "").strip()
    if nation:
        queries.append(f"{name} {nation}")
    queries.append(f"{name} island")
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": q,
            "srnamespace": "6",  # File:
            "srlimit": str(limit),
            "srprop": "",
        }
        try:
            payload = _get_json(COMMONS_API, params)
        except Exception as exc:
            print(f"  commons-text failed for {q!r}: {exc!r}", file=sys.stderr)
            continue
        hits = (payload.get("query") or {}).get("search") or []
        for h in hits:
            title = h.get("title", "")
            if not title.startswith("File:"):
                continue
            fn = _canon_filename(title)
            if fn in seen:
                continue
            seen.add(fn)
            out.append(fn)
        time.sleep(DELAY_S)
        if len(out) >= limit:
            break
    return out


def candidates_from_existing(island_id: str, islands: dict, galleries: dict) -> list[tuple[str, bool]]:
    """Return [(filename, is_primary)] from islands.json + galleries.json."""
    out: list[tuple[str, bool]] = []
    isl = islands.get(island_id) or {}
    for img in isl.get("images") or []:
        fn = img.get("fileName")
        if not fn:
            # Try to recover from URL.
            url = img.get("url") or img.get("fullUrl") or ""
            m = re.search(r"/([^/]+\.(?:jpe?g|png|webp))(?:\?|$)", url, re.IGNORECASE)
            if m:
                fn = _canon_filename(m.group(1))
        if fn:
            out.append((fn, bool(img.get("primary"))))
    extras = galleries.get(island_id) or []
    if isinstance(extras, dict):
        extras = extras.get("images") or []
    for img in extras:
        fn = img.get("fileName")
        if fn:
            out.append((fn, False))
    return out


# ---------- Build curated entry ----------

def build_for_island(
    island: dict,
    islands_by_id: dict,
    galleries_by_id: dict,
    cm_cache: dict,
    cc_cache: dict,
    report: dict,
) -> dict | None:
    iid = island["id"]
    name = island.get("name") or iid
    qid = island.get("wikidata") or ""
    print(f"\n=== {name}  ({iid}, {qid}) ===", flush=True)

    # Gather candidate filenames from all sources.
    pool_files: dict[str, dict[str, Any]] = {}  # fileName -> {sources, is_primary}

    for fn, is_primary in candidates_from_existing(iid, islands_by_id, galleries_by_id):
        rec = pool_files.setdefault(fn, {"sources": set(), "is_primary": False})
        rec["sources"].add("existing")
        if is_primary:
            rec["is_primary"] = True

    for fn in candidates_from_commons_category(qid, cc_cache):
        rec = pool_files.setdefault(fn, {"sources": set(), "is_primary": False})
        rec["sources"].add("wd-category")

    for fn in candidates_from_wikipedia(island):
        rec = pool_files.setdefault(fn, {"sources": set(), "is_primary": False})
        rec["sources"].add("wikipedia")

    # Thin-pool fallback: top up via Commons text search. Strict
    # name-anchor filter in score() means false-positives are dropped.
    if len(pool_files) < 30:
        for fn in candidates_from_commons_text(island, limit=40):
            rec = pool_files.setdefault(fn, {"sources": set(), "is_primary": False})
            rec["sources"].add("commons-text")

    print(f"  pool: {len(pool_files)} candidate files", flush=True)
    if not pool_files:
        return None

    # Fetch Commons metadata for every candidate (will hit cache mostly).
    meta_map = fetch_commons_meta(list(pool_files.keys()), cm_cache)

    scored: list[dict] = []
    for fn, info in pool_files.items():
        meta = dict(meta_map.get(fn) or {})
        if not meta:
            continue
        meta["fileName"] = fn
        s, breakdown = score(meta, island)
        cat = categorise(meta)
        rec = {
            **meta,
            "fileName": fn,
            "__score": s,
            "__breakdown": breakdown,
            "__category": cat,
            "__sources": sorted(info["sources"]),
            "__is_primary": info["is_primary"],
        }
        scored.append(rec)

    scored.sort(key=lambda x: -x["__score"])
    chosen = pick_diverse(scored, island)
    if not chosen:
        return None

    # Emit final image objects (drop the __debug fields, keep audit in report).
    images_out: list[dict] = []
    for idx, rec in enumerate(chosen):
        fn = rec["fileName"]
        page_url = rec.get("descriptionUrl") or commons_page_url(fn)
        thumb_url = commons_thumb_url(fn, width=960)
        full_url = rec.get("url") or commons_thumb_url(fn, width=2400)
        # Use the badge to expose curation quality on the front-end.
        badge = quality_badge(rec)
        images_out.append(
            {
                "url": thumb_url,
                "fullUrl": full_url,
                "source": "curated-v1",
                "sourceRef": ",".join(rec["__sources"]),
                "sourcePageUrl": page_url,
                "license": rec.get("license", ""),
                "licenseUrl": rec.get("licenseUrl", ""),
                "attribution": rec.get("attribution", ""),
                "caption": rec.get("caption", "").strip()
                or _canon_filename(fn).rsplit(".", 1)[0].replace("_", " "),
                "fileName": fn,
                "primary": idx == 0,
                "category": rec["__category"],
                "badge": badge,
                "width": rec.get("width") or None,
                "height": rec.get("height") or None,
            }
        )

    report[iid] = {
        "name": name,
        "qid": qid,
        "poolSize": len(pool_files),
        "selected": [
            {
                "fileName": i["fileName"],
                "category": i["category"],
                "badge": i.get("badge", ""),
                "score": next(
                    (c["__score"] for c in scored if c["fileName"] == i["fileName"]), None
                ),
            }
            for i in images_out
        ],
        "rejected": [
            {
                "fileName": c["fileName"],
                "score": c["__score"],
                "category": c["__category"],
                "breakdown": c["__breakdown"],
            }
            for c in scored
            if c["fileName"] not in {i["fileName"] for i in images_out}
        ][:30],
    }

    return {
        "islandId": iid,
        "curatedAt": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "sources": sorted({s for c in chosen for s in c["__sources"]}),
        "images": images_out,
    }


# ---------- Main ----------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="Curate just one island ID")
    args = parser.parse_args()

    islands = json.loads(ISLANDS_PATH.read_text(encoding="utf-8"))
    islands_by_id = {i["id"]: i for i in islands}

    galleries_raw = json.loads(GALLERIES_PATH.read_text(encoding="utf-8"))
    # galleries.json is either {id: [imgs]} or {id: {"images": [imgs]}}
    galleries_by_id: dict[str, list] = {}
    for k, v in galleries_raw.items():
        if isinstance(v, list):
            galleries_by_id[k] = v
        elif isinstance(v, dict):
            galleries_by_id[k] = v.get("images") or []

    cm_cache = _load_cache(CACHE_CM)
    cc_cache = _load_cache(CACHE_CC)

    out: dict[str, Any] = {}
    if OUT_PATH.exists():
        try:
            out = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        except Exception:
            out = {}
    report: dict[str, Any] = {}
    if REPORT_PATH.exists():
        try:
            report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        except Exception:
            report = {}

    targets = [args.only] if args.only else SAMPLE_ISLANDS
    for iid in targets:
        isl = islands_by_id.get(iid)
        if not isl:
            print(f"!!! island '{iid}' not found in islands.json, skipping", flush=True)
            continue
        try:
            entry = build_for_island(
                isl, islands_by_id, galleries_by_id, cm_cache, cc_cache, report
            )
        except Exception as exc:
            print(f"!!! {iid} failed: {exc!r}", flush=True)
            continue
        if entry:
            out[iid] = entry
            tmp = OUT_PATH.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(out, ensure_ascii=False, indent=2))
            tmp.replace(OUT_PATH)
            tmp = REPORT_PATH.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2))
            tmp.replace(REPORT_PATH)
            print(f"  -> kept {len(entry['images'])} images", flush=True)
        time.sleep(DELAY_S)

    _save_cache(CACHE_CM, cm_cache)
    _save_cache(CACHE_CC, cc_cache)
    print(f"\nWrote curated entries for {len(out)} islands to {OUT_PATH}")


if __name__ == "__main__":
    main()
