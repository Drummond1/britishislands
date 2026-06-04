#!/usr/bin/env python3
"""Stage island photos mined from Wikipedia article wikitext (galleries, infobox).

For named atlas islands without a lead photo, resolves Wikidata sitelinks (enwiki
preferred, then other ``*wiki``), fetches article wikitext via MediaWiki API, and
parses embedded Commons files from:

  - ``[[File:…]]`` / ``[[Image:…]]`` in the article body
  - ``<gallery>`` blocks and ``{{Gallery}}`` templates
  - ``{{multiple image}}`` / ``{{multiple images}}`` rows (imageN, captionN, altN)
  - infobox ``| image =`` / ``| photo =`` parameters

Each candidate must mention the island name in the wikitext caption or alt text.
Licence is verified via Commons ``imageinfo`` (shared ``cache_commons.json``).
**High** confidence when the file appears in that island's Wikipedia article
(enwiki first; other language wikis → medium-high when the sitelink title matches).

Run::

    python3 scripts/enrich_images_wikipedia_gallery.py --limit 500
    python3 scripts/enrich_images_wikipedia_gallery.py --test iona --dry-run
    python3 scripts/enrich_images_wikipedia_gallery.py --cache-only --limit 50

Outputs (staging only)::

    data/staging/adoptions/wikipedia-gallery.json
    data/cache_wikipedia_gallery_sitelinks.json
    data/cache_wikipedia_gallery_wikitext.json
    data/image_enrichment_wikipedia_gallery_report.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
CACHE_SITELINKS = DATA / "cache_wikipedia_gallery_sitelinks.json"
CACHE_WIKITEXT = DATA / "cache_wikipedia_gallery_wikitext.json"
REPORT = DATA / "image_enrichment_wikipedia_gallery_report.json"
STAGING = DATA / "staging" / "adoptions" / "wikipedia-gallery.json"

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
DELAY_S = 1.2
SOURCE_LABEL = "wikipedia-gallery"

EXCLUDE_SITES = frozenset({
    "commonswiki",
    "wikidatawiki",
    "specieswiki",
    "mediawikiwiki",
    "wikimaniawiki",
    "incubatorwiki",
    "outreachwiki",
    "testwiki",
    "test2wiki",
    "metawiki",
    "strategywiki",
})

# Prefer enwiki, then other encyclopedia wikis (not wikivoyage for this harvester).
SITE_PRIORITY = {
    "enwiki": 0,
    "cywiki": 1,
    "gawiki": 1,
    "gdwiki": 1,
    "frwiki": 2,
    "dewiki": 2,
}

_FILE_LINK_RE = re.compile(
    r"\[\[(?:File|Image):([^\]|#]+)(?:\|([^\]]*))?\]\]",
    re.IGNORECASE,
)
_GALLERY_BLOCK_RE = re.compile(
    r"<gallery[^>]*>(.*?)</gallery>",
    re.IGNORECASE | re.DOTALL,
)
_GALLERY_TEMPLATE_RE = re.compile(
    r"\{\{\s*gallery\s*\|(.*?)\}\}",
    re.IGNORECASE | re.DOTALL,
)
_MULTI_IMAGE_RE = re.compile(
    r"\{\{\s*multiple\s+images?\s*(?:\n|\|)(.*?)\n\}\}",
    re.IGNORECASE | re.DOTALL,
)
_INFOBOX_IMAGE_RE = re.compile(
    r"^\s*\|\s*(?:image\d*|photo\d*|picture\d*)\s*=\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_SKIP_PIPE = re.compile(
    r"^(?:thumb|frame|border|left|right|center|upright|"
    r"none|baseline|sub|sup|top|text-top|middle|text-bottom|bottom)\b",
    re.IGNORECASE,
)

sys.path.insert(0, str(ROOT / "scripts"))
from enrich_images_v5 import (  # noqa: E402
    CACHE_COMMONS,
    RL_BACKOFF,
    _canon,
    _get_json,
    _load,
    _load_named_index_ids,
    _looks_like_non_photo,
    _mentions,
    _name_variants,
    _save,
    build_image_record_from_commons,
    commons_page_url,
    fetch_commons_meta,
)


def license_allowed(license_str: str | None) -> bool:
    if not license_str:
        return False
    norm = license_str.strip().lower()
    if not norm or norm in {"unknown", "n/a", "none", "copyrighted", "all rights reserved"}:
        return False
    if "fair use" in norm or "editorial" in norm or "non-free" in norm:
        return False
    markers = (
        "cc-by",
        "cc by",
        "cc-by-sa",
        "cc by-sa",
        "cc0",
        "cc0-",
        "public domain",
        "pd-",
        "gfdl",
        "free art",
        "fal",
        "odbl",
    )
    return any(m in norm for m in markers)


def _is_wikipedia_site(site: str) -> bool:
    if site in EXCLUDE_SITES:
        return False
    return site.endswith("wiki") and not site.endswith("wikivoyage")


def _wiki_lang(site: str) -> str:
    if site.endswith("wiki"):
        return site[: -len("wiki")]
    return site


def _api_url(site: str) -> str:
    lang = _wiki_lang(site)
    return f"https://{lang}.wikipedia.org/w/api.php"


def _page_url(site: str, title: str) -> str:
    lang = _wiki_lang(site)
    slug = urllib.parse.quote(title.replace(" ", "_"))
    return f"https://{lang}.wikipedia.org/wiki/{slug}"


def _wikitext_cache_key(site: str, title: str) -> str:
    return f"{site}|{title}"


def _site_sort_key(site: str) -> tuple[int, str]:
    return (SITE_PRIORITY.get(site, 5), site)


def _title_from_wikipedia_url(url: str) -> str:
    u = (url or "").strip()
    if not u or "wikipedia.org/wiki/" not in u:
        return ""
    slug = u.split("/wiki/", 1)[-1].split("#")[0].split("?")[0]
    return urllib.parse.unquote(slug).replace("_", " ").strip()


def _normalize_filename(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    raw = re.sub(r"\{\{!?\}\}", "", raw)
    raw = re.sub(r"<br\s*/?>", " ", raw, flags=re.I)
    m = re.search(r"(?:File|Image):([^\]|}<]+)", raw, re.I)
    if m:
        raw = m.group(1)
    raw = raw.strip("[]{}| ")
    if not raw:
        return ""
    if raw.lower().startswith("file:"):
        return "File:" + raw[5:].lstrip()
    return "File:" + raw.replace(" ", "_")


def _parse_file_pipe(pipe: str) -> tuple[str, str]:
    """Return (caption, alt) from a File: link or gallery line pipe string."""
    if not pipe:
        return "", ""
    parts = [p.strip() for p in pipe.split("|")]
    alt = ""
    cap_parts: list[str] = []
    for p in parts:
        if re.match(r"alt\s*=", p, re.I):
            alt = re.sub(r"^alt\s*=\s*", "", p, flags=re.I).strip()
        elif _SKIP_PIPE.match(p) or re.match(r"^\d+px$", p, re.I):
            continue
        elif re.match(r"link\s*=", p, re.I):
            continue
        else:
            cap_parts.append(p)
    caption = " ".join(cap_parts).strip()
    return caption, alt


def _parse_gallery_line(line: str) -> tuple[str, str, str]:
    """Return (raw file token, caption, alt) from one ``<gallery>`` line."""
    line = line.strip()
    if not line:
        return "", "", ""
    parts = [p.strip() for p in line.split("|")]
    raw = parts[0]
    cap, alt = _parse_file_pipe("|".join(parts[1:])) if len(parts) > 1 else ("", "")
    return raw, cap, alt


@dataclass(order=True)
class ImageCandidate:
    sort_index: int
    filename: str = field(compare=False)
    caption: str = field(compare=False, default="")
    alt: str = field(compare=False, default="")
    via: str = field(compare=False, default="body")


def _parse_template_params(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in body.split("\n"):
        line = line.strip().lstrip("|").strip()
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        out[key.strip().lower()] = val.strip()
    return out


def extract_image_candidates(wikitext: str) -> list[ImageCandidate]:
    """Parse wikitext for Commons file references with local caption/alt hints."""
    if not wikitext:
        return []

    found: list[ImageCandidate] = []
    seen: set[str] = set()

    def add(
        raw_name: str,
        caption: str = "",
        alt: str = "",
        via: str = "body",
        priority: int = 50,
    ) -> None:
        fname = _normalize_filename(raw_name)
        if not fname:
            return
        key = _canon(fname).lower()
        if key in seen:
            return
        seen.add(key)
        found.append(
            ImageCandidate(
                sort_index=priority,
                filename=fname,
                caption=caption or "",
                alt=alt or "",
                via=via,
            )
        )

    for m in _INFOBOX_IMAGE_RE.finditer(wikitext):
        val = m.group(1).strip()
        cap_m = re.search(r"\|\s*caption\s*=\s*([^|}\n]+)", val, re.I)
        alt_m = re.search(r"\|\s*alt\s*=\s*([^|}\n]+)", val, re.I)
        add(
            val.split("|")[0],
            caption=(cap_m.group(1).strip() if cap_m else ""),
            alt=(alt_m.group(1).strip() if alt_m else ""),
            via="infobox",
            priority=0,
        )

    for m in _GALLERY_BLOCK_RE.finditer(wikitext):
        block = m.group(1)
        for line in block.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("<!--"):
                continue
            if line.startswith("<"):
                continue
            raw, cap, alt = _parse_gallery_line(line)
            add(raw, caption=cap, alt=alt, via="gallery-html", priority=10)

    for m in _GALLERY_TEMPLATE_RE.finditer(wikitext):
        chunk = m.group(1)
        for token in chunk.split("|"):
            token = token.strip()
            if not token or "=" in token and not re.search(r"(?:File|Image):", token, re.I):
                continue
            parts = token.split("|", 1)
            add(parts[0], caption=parts[1] if len(parts) > 1 else "", via="gallery-template", priority=12)

    for m in _MULTI_IMAGE_RE.finditer(wikitext):
        params = _parse_template_params(m.group(1))
        indices: set[int] = set()
        for key in params:
            km = re.match(r"image(\d+)$", key)
            if km:
                indices.add(int(km.group(1)))
        for idx in sorted(indices):
            img = params.get(f"image{idx}", "")
            cap = params.get(f"caption{idx}", "") or params.get(f"cap{idx}", "")
            alt = params.get(f"alt{idx}", "")
            add(img, caption=cap, alt=alt, via="multiple-image", priority=15)

    for m in _FILE_LINK_RE.finditer(wikitext):
        fname_part = m.group(1).strip()
        pipe = m.group(2) or ""
        cap, alt = _parse_file_pipe(pipe)
        add(fname_part, caption=cap, alt=alt, via="file-link", priority=30)

    found.sort()
    return found


def _gallery_name_variants(island: dict) -> list[str]:
    """Like v5 ``_name_variants`` but keeps short canonical names (e.g. Iona)."""
    variants = list(_name_variants(island))
    seen = {v.lower() for v in variants}
    raw = (island.get("name") or "").strip().lower()
    if raw and len(raw) >= 3 and raw not in seen:
        variants.append(raw)
        seen.add(raw)
    for nm in (island.get("names") or {}).values():
        nm = (nm or "").strip().lower()
        if nm and len(nm) >= 3 and nm not in seen:
            variants.append(nm)
            seen.add(nm)
    return variants


def _caption_alt_ok(island: dict, caption: str, alt: str) -> bool:
    variants = _gallery_name_variants(island)
    return _mentions(f"{caption} {alt}".strip(), variants)


def _title_matches_island(title: str, island: dict) -> bool:
    return _mentions((title or "").replace("_", " "), _gallery_name_variants(island))


def fetch_gallery_sitelinks(
    qids: list[str],
    cache: dict,
    *,
    refresh: bool,
    api_notes: list[str] | None = None,
) -> dict[str, dict[str, str]]:
    missing = [q for q in qids if refresh or q not in cache]
    BATCH = 40
    for i in range(0, len(missing), BATCH):
        batch = missing[i : i + BATCH]
        params = {
            "action": "wbgetentities",
            "format": "json",
            "ids": "|".join(batch),
            "props": "sitelinks",
        }
        try:
            payload = _get_json(WIKIDATA_API, params)
        except Exception as exc:
            print(f"  sitelinks batch failed: {exc!r}", file=sys.stderr)
            if api_notes is not None:
                api_notes.append(f"wbgetentities: {exc!r}")
            continue
        entities = payload.get("entities") or {}
        for q in batch:
            ent = entities.get(q) or {}
            sl = ent.get("sitelinks") or {}
            row: dict[str, str] = {}
            for site, data in sl.items():
                if not _is_wikipedia_site(site):
                    continue
                title = (data or {}).get("title", "")
                if title:
                    row[site] = title
            cache[q] = row
        _save(CACHE_SITELINKS, cache)
        time.sleep(DELAY_S)
    return {q: cache.get(q, {}) for q in qids}


def fetch_wikitext(
    requests: list[tuple[str, str]],
    cache: dict,
    *,
    refresh: bool,
    cache_only: bool,
    api_notes: list[str] | None = None,
) -> dict[str, str]:
    """``requests`` = [(site, title), ...]. Returns {site|title: wikitext}."""
    keys = [_wikitext_cache_key(s, t) for s, t in requests if s and t]
    keys = list(dict.fromkeys(keys))
    missing = [k for k in keys if refresh or k not in cache]
    if cache_only:
        return {k: cache.get(k, "") for k in keys}

    by_site: dict[str, list[str]] = {}
    for key in missing:
        site, _, title = key.partition("|")
        if site and title:
            by_site.setdefault(site, []).append(title)

    BATCH = 15
    for site, titles in by_site.items():
        api = _api_url(site)
        unique = list(dict.fromkeys(titles))
        for i in range(0, len(unique), BATCH):
            batch = unique[i : i + BATCH]
            params = {
                "action": "query",
                "format": "json",
                "prop": "revisions",
                "rvprop": "content",
                "rvslots": "main",
                "titles": "|".join(batch),
                "redirects": 1,
            }
            try:
                payload = _get_json(api, params)
            except Exception as exc:
                print(f"  wikitext [{site}] failed: {exc!r}", file=sys.stderr)
                if api_notes is not None:
                    api_notes.append(f"wikitext[{site}]: {exc!r}")
                continue
            pages = (payload.get("query") or {}).get("pages") or {}
            redirects = {
                r["from"]: r["to"]
                for r in (payload.get("query") or {}).get("redirects") or []
            }
            norm_map = {
                n["from"]: n["to"]
                for n in (payload.get("query") or {}).get("normalized") or []
            }

            def _back_to_requested(final_title: str) -> str:
                for src in batch:
                    t = norm_map.get(src, src)
                    t = redirects.get(t, t)
                    if t == final_title:
                        return src
                return final_title

            for _pid, page in pages.items():
                title = page.get("title", "")
                revs = page.get("revisions") or []
                wtxt = ""
                if revs:
                    slots = revs[0].get("slots") or {}
                    main = slots.get("main") or revs[0]
                    wtxt = main.get("*") or ""
                requested = _back_to_requested(title)
                cache[_wikitext_cache_key(site, requested)] = wtxt
            for t in batch:
                cache.setdefault(_wikitext_cache_key(site, t), "")
            _save(CACHE_WIKITEXT, cache)
            time.sleep(DELAY_S)

    return {k: cache.get(k, "") for k in keys}


def _ordered_article_targets(island: dict, sl: dict[str, str]) -> list[tuple[str, str]]:
    """Return [(site, title), ...] in harvest order."""
    targets: list[tuple[str, str]] = []
    en_title = sl.get("enwiki", "")
    if not en_title:
        en_title = _title_from_wikipedia_url(island.get("wikipedia") or "")
    if en_title:
        targets.append(("enwiki", en_title))
    for site in sorted(sl.keys(), key=_site_sort_key):
        if site == "enwiki":
            continue
        title = sl.get(site, "")
        if title:
            targets.append((site, title))
    # Dedupe while preserving order.
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for site, title in targets:
        key = _wikitext_cache_key(site, title)
        if key in seen:
            continue
        seen.add(key)
        out.append((site, title))
    return out


def pick_best_from_article(
    island: dict,
    site: str,
    title: str,
    wikitext: str,
    commons_cache: dict,
) -> tuple[dict | None, ImageCandidate | None]:
    if not wikitext:
        return None, None
    variants = _gallery_name_variants(island)
    candidates = extract_image_candidates(wikitext)
    shortlist: list[ImageCandidate] = []
    for cand in candidates:
        if _looks_like_non_photo(cand.filename):
            continue
        if not _caption_alt_ok(island, cand.caption, cand.alt):
            continue
        shortlist.append(cand)
    if not shortlist:
        return None, None

    fnames = [_canon(c.filename) for c in shortlist]
    metas = fetch_commons_meta(fnames, commons_cache)
    best: tuple[ImageCandidate, dict, float] | None = None
    for cand in shortlist:
        canon = _canon(cand.filename)
        meta = metas.get(canon, {}) or {}
        lic = (meta.get("license") or "").strip()
        if not license_allowed(lic):
            continue
        w, h = meta.get("width") or 0, meta.get("height") or 0
        score = float(w * h) if w and h else 1.0
        if _mentions(canon, variants):
            score += 500_000.0
        if _mentions(meta.get("caption") or "", variants):
            score += 50_000.0
        score -= cand.sort_index * 1000.0
        if best is None or score > best[2]:
            best = (cand, meta, score)

    if not best:
        return None, None

    cand, meta, _ = best
    lang = _wiki_lang(site)
    source = "wikipedia" if lang == "en" else f"wikipedia-{lang}"
    rec = build_image_record_from_commons(
        cand.filename,
        meta,
        source,
        f"{site}:{title};{cand.via}",
    )
    if not rec:
        return None, None
    rec["sourcePageUrl"] = _page_url(site, title)
    if site == "enwiki":
        rec["imageConfidence"] = "high"
    elif _title_matches_island(title, island):
        rec["imageConfidence"] = "medium-high"
    else:
        rec["imageConfidence"] = "medium"
    rec["verifiedAt"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    if cand.caption:
        rec["caption"] = cand.caption
    rec["wikipediaGalleryVia"] = cand.via
    rec["commonsFile"] = commons_page_url(cand.filename)
    return rec, cand


def try_island(
    island: dict,
    sl_cache: dict,
    wt_cache: dict,
    commons_cache: dict,
    *,
    cache_only: bool,
) -> tuple[dict | None, str, str, str]:
    qid = (island.get("wikidata") or "").strip()
    sl: dict[str, str] = {}
    if re.match(r"^Q\d+$", qid):
        sl = sl_cache.get(qid, {})
    targets = _ordered_article_targets(island, sl)
    if not targets:
        return None, "", "", "no enwiki or wikipedia sitelink"

    for site, title in targets:
        if site != "enwiki" and not _title_matches_island(title, island):
            continue
        wtxt = wt_cache.get(_wikitext_cache_key(site, title), "")
        if not wtxt and cache_only:
            continue
        rec, cand = pick_best_from_article(island, site, title, wtxt, commons_cache)
        if rec and cand:
            return rec, site, title, ""
    return None, "", "", "no wikitext image passed caption/alt + licence gate"


def main() -> int:
    global DELAY_S
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=500, help="Max islands to attempt.")
    ap.add_argument("--test", metavar="ID", help="Single island id.")
    ap.add_argument(
        "--include-unnamed",
        action="store_true",
        help="Include islands not in islands_index.json (default: named only).",
    )
    ap.add_argument("--refresh", action="store_true", help="Ignore caches.")
    ap.add_argument("--cache-only", action="store_true", help="No live API calls.")
    ap.add_argument("--dry-run", action="store_true", help="Do not write staging JSON.")
    ap.add_argument("--delay", type=float, default=None)
    args = ap.parse_args()
    if args.delay is not None:
        DELAY_S = max(0.0, float(args.delay))

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    if not isinstance(islands, list):
        print("FATAL: islands.json is not a list", file=sys.stderr)
        return 2

    api_notes: list[str] = []
    cache_sl = _load(CACHE_SITELINKS)
    cache_wt = _load(CACHE_WIKITEXT)
    cache_commons = _load(CACHE_COMMONS)

    pending = [i for i in islands if not (i.get("images") or [])]
    if not args.include_unnamed:
        named_ids = _load_named_index_ids()
        if named_ids:
            before = len(pending)
            pending = [i for i in pending if i.get("id") in named_ids]
            print(f"  named-only: {len(pending):,} of {before:,} without images", flush=True)

    def _has_wiki_hook(island: dict) -> bool:
        qid = (island.get("wikidata") or "").strip()
        if re.match(r"^Q\d+$", qid):
            return True
        return bool(_title_from_wikipedia_url(island.get("wikipedia") or ""))

    pending = [i for i in pending if _has_wiki_hook(i)]
    if args.test:
        pending = [i for i in pending if i.get("id") == args.test]

    report: dict[str, Any] = {
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "pipeline": "enrich_images_wikipedia_gallery",
        "args": {k: v for k, v in vars(args).items() if not k.startswith("_")},
        "pending": len(pending),
        "adopted": [],
        "rejected": [],
        "by_wiki_site": {},
        "by_via": {},
        "rate_limit_notes": [
            f"DELAY_S={DELAY_S} between Wikimedia API batches.",
            f"HTTP 429 backoff: {list(RL_BACKOFF)}.",
        ],
    }
    print(f"Pending (named, no image, wiki hook): {len(pending):,}", flush=True)

    qids = sorted({
        (i.get("wikidata") or "").strip()
        for i in pending
        if re.match(r"^Q\d+$", (i.get("wikidata") or "").strip())
    })
    if qids and not args.cache_only:
        sl_todo = [q for q in qids if args.refresh or q not in cache_sl]
        if sl_todo:
            print(f"  pre-fetch sitelinks for {len(sl_todo):,} Q-IDs…", flush=True)
        fetch_gallery_sitelinks(qids, cache_sl, refresh=args.refresh, api_notes=api_notes)
    elif qids:
        fetch_gallery_sitelinks(qids, cache_sl, refresh=False, api_notes=api_notes)

    def _has_wikipedia_article(island: dict) -> bool:
        if _title_from_wikipedia_url(island.get("wikipedia") or ""):
            return True
        qid = (island.get("wikidata") or "").strip()
        if not re.match(r"^Q\d+$", qid):
            return False
        sl = cache_sl.get(qid, {})
        return any(_is_wikipedia_site(s) for s in sl)

    if not args.test:
        before = len(pending)
        pending = [i for i in pending if _has_wikipedia_article(i)]
        print(
            f"  with Wikipedia article: {len(pending):,} of {before:,}",
            flush=True,
        )

    def _pending_sort_key(island: dict) -> tuple[int, float, str]:
        qid = (island.get("wikidata") or "").strip()
        sl = cache_sl.get(qid, {}) if re.match(r"^Q\d+$", qid) else {}
        has_en = bool(sl.get("enwiki") or _title_from_wikipedia_url(island.get("wikipedia") or ""))
        area = float(island.get("areaHa") or 0)
        return (0 if has_en else 1, -area, island.get("id") or "")

    pending.sort(key=_pending_sort_key)
    if args.limit:
        pending = pending[: args.limit]

    report["pending"] = len(pending)

    wt_requests: list[tuple[str, str]] = []
    for isl in pending:
        qid = (isl.get("wikidata") or "").strip()
        sl = cache_sl.get(qid, {}) if re.match(r"^Q\d+$", qid) else {}
        wt_requests.extend(_ordered_article_targets(isl, sl))
    wt_requests = list(dict.fromkeys(wt_requests))
    if wt_requests and not args.cache_only:
        wt_missing = [
            (s, t)
            for s, t in wt_requests
            if args.refresh or _wikitext_cache_key(s, t) not in cache_wt
        ]
        if wt_missing:
            print(f"  pre-fetch wikitext for {len(wt_missing):,} articles…", flush=True)
        fetch_wikitext(
            wt_missing or wt_requests,
            cache_wt,
            refresh=args.refresh,
            cache_only=False,
            api_notes=api_notes,
        )
    elif wt_requests:
        fetch_wikitext(wt_requests, cache_wt, refresh=False, cache_only=True, api_notes=api_notes)

    if api_notes:
        report["rate_limit_notes"].extend(api_notes)

    pending_set = {i.get("id") for i in pending}
    staged: list[dict[str, Any]] = []
    n_attempted = 0
    n_staged = 0
    by_site: dict[str, int] = {}
    by_via: dict[str, int] = {}

    for isl in islands:
        if isl.get("id") not in pending_set:
            continue
        n_attempted += 1
        rec, site, title, reject = try_island(
            isl,
            cache_sl,
            cache_wt,
            cache_commons,
            cache_only=args.cache_only,
        )
        if rec:
            via = rec.get("wikipediaGalleryVia", "")
            entry = {
                "id": isl["id"],
                "name": isl.get("name", ""),
                "wikidata": isl.get("wikidata", ""),
                "wikiSite": site,
                "wikiTitle": title,
                "imageConfidence": rec.get("imageConfidence"),
                "source": rec.get("source"),
                "sourceRef": rec.get("sourceRef"),
                "license": rec.get("license"),
                "sourcePageUrl": rec.get("sourcePageUrl"),
                "image_record": rec,
                "confidence": rec.get("imageConfidence"),
                "reason": (
                    f"File in {site} article wikitext ({via}); "
                    "caption/alt names island; Commons licence OK"
                ),
            }
            report["adopted"].append(entry)
            staged.append(entry)
            n_staged += 1
            by_site[site] = by_site.get(site, 0) + 1
            if via:
                by_via[via] = by_via.get(via, 0) + 1
            print(
                f"  ✓ {isl['id']:45s} [{site}] via {via}",
                flush=True,
            )
        else:
            report["rejected"].append({
                "id": isl["id"],
                "name": isl.get("name", ""),
                "reason": reject or "no match",
            })

    if not args.dry_run:
        STAGING.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "pipeline": "enrich_images_wikipedia_gallery",
            "attempted": n_attempted,
            "staged_count": n_staged,
            "by_wiki_site": by_site,
            "by_via": by_via,
            "adoptions": staged,
        }
        STAGING.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Staging  → {STAGING.relative_to(ROOT)} ({n_staged:,} adoptions)")

    report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    report["attempted"] = n_attempted
    report["staged_total"] = n_staged
    report["by_wiki_site"] = by_site
    report["by_via"] = by_via
    if not args.dry_run:
        _save(REPORT, report)

    print()
    print(f"Attempted: {n_attempted:,}")
    print(f"Staged:    {n_staged:,}")
    if by_site:
        print("By wiki:", ", ".join(f"{k}={v}" for k, v in sorted(by_site.items())))
    if by_via:
        print("By via:", ", ".join(f"{k}={v}" for k, v in sorted(by_via.items())))
    if not args.dry_run:
        print(f"Report   → {REPORT.relative_to(ROOT)}")
    return n_staged


if __name__ == "__main__":
    count = main()
    print(f"staged_count={count}")
    raise SystemExit(0)
