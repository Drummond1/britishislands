#!/usr/bin/env python3
"""
Enrich `data/islands.json` with authoritative primary images.

Sources (in priority order, never name-based search):
    1. Wikidata P18  — for entries with `wikidata` Q-ID. Highest confidence.
    2. MediaWiki pageimages — for entries with `wikipedia` URL but no Q-ID.
    3. Existing curated `image` — already trusted, preserved.

The image is fetched alongside Commons file metadata (license, author,
description-URL) so attribution can be rendered in the front-end.

Schema additions per island:
    image:  url (back-compat; mirrors images[0].url)
    images: [
      {
        url, fullUrl, source, sourceRef, sourcePageUrl,
        license, attribution, caption, primary
      }
    ]
    wikidata: "Q...."   (already added by fetch_islands.py)

Run:
    python3 scripts/enrich_images.py            # uses cached API responses where possible
    python3 scripts/enrich_images.py --refresh  # bypasses cache (slow; respect rate limits)

Outputs:
    data/islands.json                  (updated in place)
    data/cache_wikidata.json           (SPARQL cache, keyed by Q-ID)
    data/cache_pageimages.json         (pageimages cache, keyed by title)
    data/cache_commons.json            (commons file metadata cache)
    data/image_enrichment_report.json  (audit + spot-check rows)
"""

from __future__ import annotations

import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
ISLANDS_PATH = DATA_DIR / "islands.json"
WD_CACHE = DATA_DIR / "cache_wikidata.json"
PI_CACHE = DATA_DIR / "cache_pageimages.json"
CM_CACHE = DATA_DIR / "cache_commons.json"
PP_CACHE = DATA_DIR / "cache_pageprops.json"
REPORT_PATH = DATA_DIR / "image_enrichment_report.json"

USER_AGENT = (
    "isles-of-britain/0.3 (image enrichment; "
    "https://github.com/example/isles-of-britain; "
    "static-site prototype)"
)
WD_BATCH = 80           # SPARQL is fine with ~100 VALUES; 80 is comfy
PI_BATCH = 50           # pageimages caps at 50 titles per call
DELAY_S = 0.12          # politeness between batches

WD_ENDPOINT = "https://query.wikidata.org/sparql"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"


# ---------- HTTP helpers ----------

def _open(req: urllib.request.Request, timeout: int = 60) -> bytes:
    last_err = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last_err = exc
            # back off with jitter, longer for 429
            sleep = (1.5 ** attempt) + random.random() * 0.4
            if isinstance(exc, urllib.error.HTTPError) and exc.code == 429:
                sleep = max(sleep, 5)
            time.sleep(sleep)
    raise RuntimeError(f"HTTP failed after retries: {last_err}")


def _get_json(url: str, params: dict[str, Any]) -> dict:
    qs = urllib.parse.urlencode(params, safe=":/?&=,")
    req = urllib.request.Request(
        url + "?" + qs,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    return json.loads(_open(req))


def _post_sparql(query: str) -> dict:
    body = urllib.parse.urlencode({"query": query}).encode()
    req = urllib.request.Request(
        WD_ENDPOINT,
        data=body,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/sparql-results+json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    return json.loads(_open(req, timeout=120))


# ---------- Cache helpers ----------

def _load_cache(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    return {}


def _save_cache(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False))


# ---------- Wikidata P18 ----------

WD_QUERY_TEMPLATE = """
SELECT ?item ?image ?itemLabel ?itemDescription WHERE {
  VALUES ?item { %s }
  OPTIONAL { ?item wdt:P18 ?image . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" }
}
"""


def fetch_wikidata_images(qids: list[str], cache: dict, refresh: bool) -> dict[str, dict]:
    """Returns Q-ID → {filename, label, description}. Filename may be None."""
    missing = [q for q in qids if refresh or q not in cache]
    if missing:
        print(
            f"  Wikidata: {len(missing)} new Q-IDs to fetch in batches of {WD_BATCH}",
            file=sys.stderr,
        )
        # Use a queue so we can split a failing batch into halves and retry
        from collections import deque
        queue: deque[list[str]] = deque()
        for i in range(0, len(missing), WD_BATCH):
            queue.append(missing[i : i + WD_BATCH])
        batch_n = 0
        while queue:
            batch = queue.popleft()
            batch_n += 1
            values = " ".join(f"wd:{q}" for q in batch)
            try:
                payload = _post_sparql(WD_QUERY_TEMPLATE % values)
            except Exception as exc:
                print(
                    f"    batch {batch_n} ({len(batch)} ids): failed {exc!r}",
                    file=sys.stderr,
                )
                if len(batch) > 1:
                    # split and retry the halves later
                    mid = len(batch) // 2
                    queue.appendleft(batch[mid:])
                    queue.appendleft(batch[:mid])
                else:
                    # Single Q-ID failure: cache as empty so we don't loop
                    cache[batch[0]] = {"filename": "", "label": "", "description": ""}
                    _save_cache(WD_CACHE, cache)
                continue
            seen = set()
            for row in payload.get("results", {}).get("bindings", []):
                qid = row["item"]["value"].rsplit("/", 1)[-1]
                seen.add(qid)
                img_url = (row.get("image") or {}).get("value", "")
                # Commons file URL looks like
                #   http://commons.wikimedia.org/wiki/Special:FilePath/Foo.jpg
                filename = ""
                if img_url:
                    filename = urllib.parse.unquote(img_url.rsplit("/", 1)[-1])
                cache[qid] = {
                    "filename": filename,
                    "label": (row.get("itemLabel") or {}).get("value", ""),
                    "description": (row.get("itemDescription") or {}).get("value", ""),
                }
            # Wikidata returns nothing for Q-IDs without an image — make
            # sure we still mark those as fetched so we don't retry.
            for q in batch:
                cache.setdefault(q, {"filename": "", "label": "", "description": ""})
            _save_cache(WD_CACHE, cache)
            print(
                f"    batch {batch_n} ({len(batch)} ids): {len(seen)} hits",
                file=sys.stderr,
            )
            time.sleep(DELAY_S)
    return {q: cache.get(q, {}) for q in qids}


# ---------- MediaWiki pageprops (Wikipedia title → Wikidata Q-ID) ----------

def fetch_pageprops_qids(titles: list[str], cache: dict, refresh: bool) -> dict[str, str]:
    """Returns {lang|title: Q-ID} for Wikipedia pages that have a
    `wikibase_item` pageprop. Used to harvest a Q-ID for entries that
    only have a Wikipedia URL (so they can flow through the P18 path)."""
    by_lang: dict[str, list[str]] = {}
    for t in titles:
        if "|" not in t:
            continue
        lang, title = t.split("|", 1)
        by_lang.setdefault(lang, []).append(title)

    for lang, titles_for_lang in by_lang.items():
        missing = [
            t for t in titles_for_lang if refresh or f"{lang}|{t}" not in cache
        ]
        if not missing:
            continue
        print(
            f"  pageprops [{lang}]: {len(missing)} titles in batches of {PI_BATCH}",
            file=sys.stderr,
        )
        for i in range(0, len(missing), PI_BATCH):
            batch = missing[i : i + PI_BATCH]
            params = {
                "action": "query",
                "format": "json",
                "prop": "pageprops",
                "ppprop": "wikibase_item",
                "titles": "|".join(batch),
                "redirects": 1,
            }
            url = f"https://{lang}.wikipedia.org/w/api.php"
            try:
                payload = _get_json(url, params)
            except Exception as exc:
                print(f"    batch {i}: failed {exc!r}", file=sys.stderr)
                continue
            normalized: dict[str, str] = {}
            for n in (payload.get("query") or {}).get("normalized") or []:
                normalized[n["to"]] = n["from"]
            for redir in (payload.get("query") or {}).get("redirects") or []:
                normalized.setdefault(redir["to"], redir["from"])
            pages = (payload.get("query") or {}).get("pages") or {}
            for _pid, page in pages.items():
                page_title = page.get("title", "")
                input_title = normalized.get(page_title, page_title)
                qid = (page.get("pageprops") or {}).get("wikibase_item", "")
                cache[f"{lang}|{input_title}"] = qid
            for t in batch:
                cache.setdefault(f"{lang}|{t}", "")
            _save_cache(PP_CACHE, cache)
            time.sleep(DELAY_S)

    return {t: cache.get(t, "") for t in titles}


# ---------- MediaWiki pageimages ----------

def fetch_pageimages(titles: list[str], cache: dict, refresh: bool) -> dict[str, dict]:
    """Returns title → {filename, thumbnail_url, original_url} for entries
    that have a lead image."""
    # Group titles by language because pageimages is per-wiki
    by_lang: dict[str, list[str]] = {}
    for t in titles:
        if "|" not in t:
            continue
        lang, title = t.split("|", 1)
        by_lang.setdefault(lang, []).append(title)

    for lang, titles_for_lang in by_lang.items():
        missing = [
            t for t in titles_for_lang if refresh or f"{lang}|{t}" not in cache
        ]
        if not missing:
            continue
        print(
            f"  pageimages [{lang}]: {len(missing)} titles in batches of {PI_BATCH}",
            file=sys.stderr,
        )
        for i in range(0, len(missing), PI_BATCH):
            batch = missing[i : i + PI_BATCH]
            params = {
                "action": "query",
                "format": "json",
                "prop": "pageimages",
                "piprop": "name|thumbnail|original",
                "pithumbsize": 640,
                "titles": "|".join(batch),
                "redirects": 1,
            }
            url = f"https://{lang}.wikipedia.org/w/api.php"
            try:
                payload = _get_json(url, params)
            except Exception as exc:
                print(f"    batch {i}: failed {exc!r}", file=sys.stderr)
                continue
            pages = (payload.get("query") or {}).get("pages") or {}
            # MediaWiki may normalise titles — track which input matched
            normalized: dict[str, str] = {}
            for n in (payload.get("query") or {}).get("normalized") or []:
                normalized[n["to"]] = n["from"]
            for redir in (payload.get("query") or {}).get("redirects") or []:
                normalized.setdefault(redir["to"], redir["from"])
            seen_inputs: set[str] = set()
            for _pid, page in pages.items():
                page_title = page.get("title", "")
                input_title = normalized.get(page_title, page_title)
                seen_inputs.add(input_title)
                if "pageimage" in page or "thumbnail" in page:
                    thumb = page.get("thumbnail") or {}
                    cache[f"{lang}|{input_title}"] = {
                        "filename": page.get("pageimage") or "",
                        "thumb": thumb.get("source", ""),
                        "original": (page.get("original") or {}).get("source", ""),
                        "title": page_title,
                    }
                else:
                    cache[f"{lang}|{input_title}"] = {}
            # Fill misses
            for t in batch:
                cache.setdefault(f"{lang}|{t}", {})
            _save_cache(PI_CACHE, cache)
            print(
                f"    batch {i // PI_BATCH + 1}: {sum(1 for t in batch if cache.get(f'{lang}|{t}', {}).get('filename'))} hits",
                file=sys.stderr,
            )
            time.sleep(DELAY_S)

    return {t: cache.get(t, {}) for t in titles}


# ---------- Commons file metadata (license, author) ----------

def _canon_filename(name: str) -> str:
    """Canonical Commons filename: no `File:` prefix, spaces (not underscores)."""
    if not name:
        return ""
    n = name
    if n.startswith("File:"):
        n = n[len("File:") :]
    return n.replace("_", " ")


def fetch_commons_metadata(filenames: list[str], cache: dict, refresh: bool) -> dict[str, dict]:
    """filename (canonical, with spaces) → {license, attribution, descriptionUrl, ...}"""
    norm = []
    for f in filenames:
        c = _canon_filename(f)
        if c:
            norm.append(c)
    norm = list(dict.fromkeys(norm))  # dedupe, preserve order
    missing = [n for n in norm if refresh or n not in cache]
    if missing:
        print(
            f"  Commons imageinfo: {len(missing)} files in batches of {PI_BATCH}",
            file=sys.stderr,
        )
        for i in range(0, len(missing), PI_BATCH):
            batch = missing[i : i + PI_BATCH]
            params = {
                "action": "query",
                "format": "json",
                "prop": "imageinfo",
                "iiprop": "url|extmetadata|size|mime",
                "iiextmetadatafilter": (
                    "LicenseShortName|Artist|Credit|LicenseUrl|Categories|"
                    "ImageDescription|ObjectName"
                ),
                "iiextmetadatalanguage": "en",
                "titles": "|".join("File:" + n for n in batch),
                "redirects": 1,
            }
            try:
                payload = _get_json(COMMONS_API, params)
            except Exception as exc:
                print(f"    batch {i}: failed {exc!r}", file=sys.stderr)
                continue
            pages = (payload.get("query") or {}).get("pages") or {}
            for _pid, page in pages.items():
                title = page.get("title", "")
                fname = _canon_filename(title)
                info_list = page.get("imageinfo") or []
                if not info_list:
                    cache[fname] = {}
                    continue
                info = info_list[0]
                ext = info.get("extmetadata") or {}
                cache[fname] = {
                    "license": _take(ext, "LicenseShortName"),
                    "licenseUrl": _take(ext, "LicenseUrl"),
                    "attribution": _strip_html(
                        _take(ext, "Artist") or _take(ext, "Credit")
                    ),
                    "caption": _strip_html(
                        _take(ext, "ObjectName") or _take(ext, "ImageDescription")
                    ),
                    "descriptionUrl": info.get("descriptionurl", ""),
                    "url": info.get("url", ""),
                    "width": info.get("width"),
                    "height": info.get("height"),
                    "mime": info.get("mime", ""),
                }
            for f in batch:
                cache.setdefault(f, {})
            _save_cache(CM_CACHE, cache)
            print(
                f"    batch {i // PI_BATCH + 1}: {sum(1 for f in batch if cache.get(f, {}).get('license'))} licensed",
                file=sys.stderr,
            )
            time.sleep(DELAY_S)
    return {f: cache.get(f, {}) for f in norm}


def _take(ext: dict, key: str) -> str:
    v = (ext or {}).get(key) or {}
    return v.get("value", "") if isinstance(v, dict) else ""


_HTML_RE = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", _HTML_RE.sub("", s)).strip()


# ---------- URL builders ----------

def commons_thumb_url(filename: str, width: int) -> str:
    """https://commons.wikimedia.org/wiki/Special:FilePath/<file>?width=N"""
    if not filename:
        return ""
    if filename.startswith("File:"):
        filename = filename[len("File:") :]
    return (
        "https://commons.wikimedia.org/wiki/Special:FilePath/"
        + urllib.parse.quote(filename.replace(" ", "_"))
        + f"?width={width}"
    )


_NON_PHOTO_RE = re.compile(
    r"(?:^|[_ \-])("
    r"flag|coat[_ \-]of[_ \-]arms|coat[_ \-]arms|arms[_ \-]of|"
    r"crest|emblem|seal|logo|badge|"
    r"location[_ \-]map|outline[_ \-]map|locator[_ \-]map|"
    r"map[_ \-]of|map[_ \-]showing"
    r")",
    re.IGNORECASE,
)


def _looks_like_non_photo(filename: str) -> bool:
    """Heuristic: pageimages sometimes returns a flag, coat-of-arms, or
    outline map as the lead image. Reject those."""
    if not filename:
        return True
    if filename.lower().endswith(".svg"):
        return True
    return bool(_NON_PHOTO_RE.search(filename))


_CURATED_URL_RE = re.compile(
    r"https?://"
    r"(?:upload\.wikimedia\.org/.+/|commons\.wikimedia\.org/wiki/Special:FilePath/)"
    r"(.+?)"
    r"(?:/[^/]+)?(?:\?.*)?$"
)
_THUMB_PREFIX_RE = re.compile(r"^\d{2,4}px-", re.IGNORECASE)


def _curated_filename(url: str) -> str:
    """Extract a Commons filename from a curated URL. Strips any erroneous
    `NNNpx-` thumbnail prefix so the canonical original filename is used."""
    if not url:
        return ""
    m = _CURATED_URL_RE.match(url)
    if not m:
        return ""
    fname = urllib.parse.unquote(m.group(1).split("/")[-1])
    fname = _THUMB_PREFIX_RE.sub("", fname)
    return fname


def commons_page_url(filename: str) -> str:
    if not filename:
        return ""
    if filename.startswith("File:"):
        filename = filename[len("File:") :]
    return (
        "https://commons.wikimedia.org/wiki/File:"
        + urllib.parse.quote(filename.replace(" ", "_"))
    )


# ---------- Main ----------

def main() -> None:
    refresh = "--refresh" in sys.argv
    islands = json.loads(ISLANDS_PATH.read_text())

    wd_cache = _load_cache(WD_CACHE)
    pi_cache = _load_cache(PI_CACHE)
    cm_cache = _load_cache(CM_CACHE)
    pp_cache = _load_cache(PP_CACHE)

    # 1) Inventory ---------------------------------------------------------
    qid_to_islands: dict[str, list[dict]] = {}
    for i in islands:
        q = (i.get("wikidata") or "").strip()
        if q and re.match(r"^Q\d+$", q):
            qid_to_islands.setdefault(q, []).append(i)
    print(
        f"Islands with Wikidata Q-IDs (from OSM tags): {len(qid_to_islands)}",
        file=sys.stderr,
    )

    # Harvest Q-IDs for entries with Wikipedia URL but no Q-ID
    wp_only: list[tuple[str, dict]] = []
    for i in islands:
        if i.get("wikidata"):
            continue
        url = i.get("wikipedia") or ""
        m = re.match(r"https?://([a-z\-]+)\.wikipedia\.org/wiki/(.+)$", url)
        if m:
            lang, slug = m.groups()
            title = urllib.parse.unquote(slug).replace("_", " ")
            wp_only.append((f"{lang}|{title}", i))
    print(
        f"Islands with Wikipedia URL but no Q-ID: {len(wp_only)}",
        file=sys.stderr,
    )
    if wp_only:
        pp_results = fetch_pageprops_qids(
            [t for t, _ in wp_only], pp_cache, refresh
        )
        harvested = 0
        for t, isl in wp_only:
            q = pp_results.get(t, "")
            if q and re.match(r"^Q\d+$", q):
                isl["wikidata"] = q
                qid_to_islands.setdefault(q, []).append(isl)
                harvested += 1
        print(f"  pageprops harvested {harvested} new Q-IDs", file=sys.stderr)

    qids = list(qid_to_islands)
    print(f"Total Q-IDs for SPARQL: {len(qids)}", file=sys.stderr)

    # 2) Fetch Wikidata P18 -----------------------------------------------
    wd_results = fetch_wikidata_images(qids, wd_cache, refresh)

    # 3) Fetch pageimages for entries that STILL have no Q-ID -------------
    pi_targets: list[tuple[str, dict]] = []
    for t, isl in wp_only:
        if not isl.get("wikidata"):
            pi_targets.append((t, isl))
    pi_titles = [t for (t, _) in pi_targets]
    pi_results = fetch_pageimages(pi_titles, pi_cache, refresh) if pi_titles else {}

    # 4) Gather all unique filenames to look up Commons metadata ----------
    filenames: set[str] = set()
    for q, info in wd_results.items():
        if info.get("filename"):
            filenames.add(_canon_filename(info["filename"]))
    for t, info in pi_results.items():
        if info.get("filename"):
            filenames.add(_canon_filename(info["filename"]))
    # Curated images that point to Commons FilePath URLs — try to recover
    # the filename so we can attribute properly.
    for i in islands:
        url = i.get("image") or ""
        fname = _canon_filename(_curated_filename(url))
        if fname and not fname.endswith(".svg.png"):
            filenames.add(fname)
    print(f"Unique Commons filenames to inspect: {len(filenames)}", file=sys.stderr)
    cm_results = fetch_commons_metadata(sorted(filenames), cm_cache, refresh)

    # 5) Apply to islands --------------------------------------------------
    counts = {
        "wikidata": 0,
        "pageimage": 0,
        "curated": 0,
        "curated_with_license": 0,
        "none": 0,
    }
    audit_rows: list[dict] = []

    # Determine the canonical curated URL (if any) once per island — we
    # need this both before the rebuild (so we don't lose it) and after
    # (to preserve back-compat with the `image` field).
    curated_urls: dict[str, str] = {}
    for i in islands:
        if i.get("source") != "osm" and i.get("image"):
            curated_urls[i["id"]] = i["image"]
        else:
            # Detect any prior-run curated entry that lived only in images[]
            for img in i.get("images") or []:
                if img.get("source") == "curated":
                    curated_urls.setdefault(
                        i["id"],
                        commons_thumb_url(img.get("sourceRef", ""), 640),
                    )
                    break

    for i in islands:
        images: list[dict] = []

        # 1) Curated image (preserved verbatim if present, but only if the
        #    Commons file actually exists — broken filenames in the
        #    legacy curated.json would otherwise display as 404 holes).
        curated_url = curated_urls.get(i["id"], "")
        if curated_url:
            fname = _canon_filename(_curated_filename(curated_url))
            meta = cm_results.get(fname, {}) if fname else {}
            # `meta` is the dict from Commons imageinfo. If the file doesn't
            # exist on Commons (404), the API returns no imageinfo and we
            # cache an empty {}. Treat that as "broken" and skip.
            has_commons_record = bool(meta)
            if has_commons_record or not fname:
                images.append(
                    {
                        "url": commons_thumb_url(fname, 640) if fname else curated_url,
                        "fullUrl": commons_thumb_url(fname, 1600) if fname else curated_url,
                        "caption": meta.get("caption", "") or i.get("name", ""),
                        "source": "curated",
                        "sourceRef": fname,
                        "sourcePageUrl": commons_page_url(fname) if fname else "",
                        "license": meta.get("license", ""),
                        "attribution": meta.get("attribution", ""),
                        "primary": True,
                    }
                )
                if meta.get("license"):
                    counts["curated_with_license"] += 1
                counts["curated"] += 1
            else:
                counts.setdefault("curated_dropped_broken", 0)
                counts["curated_dropped_broken"] += 1

        # 2) Wikidata P18 image
        q = (i.get("wikidata") or "").strip()
        wd_info = wd_results.get(q, {}) if q else {}
        wd_filename = _canon_filename(wd_info.get("filename", ""))
        if (
            wd_filename
            and not _looks_like_non_photo(wd_filename)
            and not any(
                img.get("sourceRef") == wd_filename or img.get("sourceRef") == q
                for img in images
            )
        ):
            meta = cm_results.get(wd_filename, {})
            images.append(
                {
                    "url": commons_thumb_url(wd_filename, 640),
                    "fullUrl": commons_thumb_url(wd_filename, 1600),
                    "caption": meta.get("caption", "") or wd_info.get("label", ""),
                    "source": "wikidata",
                    "sourceRef": q,
                    "sourcePageUrl": commons_page_url(wd_filename),
                    "license": meta.get("license", ""),
                    "attribution": meta.get("attribution", ""),
                    "primary": not images,
                }
            )
            counts["wikidata"] += 1
            audit_rows.append(
                {
                    "id": i["id"],
                    "name": i["name"],
                    "source": "wikidata",
                    "sourceRef": q,
                    "wikidataLabel": wd_info.get("label"),
                    "wikidataDescription": wd_info.get("description"),
                    "filename": wd_filename,
                    "nameMentionedInWdLabel": (
                        i["name"].lower() in (wd_info.get("label") or "").lower()
                        or (wd_info.get("label") or "").lower() in i["name"].lower()
                    ),
                    "license": meta.get("license"),
                }
            )

        # 3) Wikipedia pageimages fallback (only when no Wikidata image)
        if not any(img.get("source") in ("wikidata",) for img in images):
            url = i.get("wikipedia") or ""
            m = re.match(r"https?://([a-z\-]+)\.wikipedia\.org/wiki/(.+)$", url)
            if m:
                lang, slug = m.groups()
                title = urllib.parse.unquote(slug).replace("_", " ")
                pi_info = pi_results.get(f"{lang}|{title}", {})
                pi_filename = _canon_filename(pi_info.get("filename", ""))
                if (
                    pi_filename
                    and not _looks_like_non_photo(pi_filename)
                    and not any(
                        img.get("sourceRef") == pi_filename for img in images
                    )
                ):
                    meta = cm_results.get(pi_filename, {})
                    images.append(
                        {
                            "url": commons_thumb_url(pi_filename, 640),
                            "fullUrl": commons_thumb_url(pi_filename, 1600),
                            "caption": meta.get("caption", ""),
                            "source": "pageimage",
                            "sourceRef": f"{lang}wiki:{title}",
                            "sourcePageUrl": commons_page_url(pi_filename),
                            "license": meta.get("license", ""),
                            "attribution": meta.get("attribution", ""),
                            "primary": not images,
                        }
                    )
                    counts["pageimage"] += 1
                    audit_rows.append(
                        {
                            "id": i["id"],
                            "name": i["name"],
                            "source": "pageimage",
                            "sourceRef": f"{lang}wiki:{title}",
                            "filename": pi_filename,
                            "nameMentionedInWpTitle": (
                                i["name"].lower() in title.lower()
                                or title.lower() in i["name"].lower()
                            ),
                            "license": meta.get("license"),
                        }
                    )

        # Mark a single primary
        if images:
            for img in images:
                img["primary"] = False
            images[0]["primary"] = True

        if not images:
            counts["none"] += 1

        i["images"] = images
        i["image"] = images[0]["url"] if images else ""

    # 6) Spot-check sample (30 random with images + iconic) ----------------
    iconic = [
        "Isle of Skye",
        "Iona",
        "Lundy",
        "Inchmurrin",
        "Devenish Island",
        "Anglesey (Ynys Môn)",
        "Isle of Wight",
        "Jersey",
        "Lindisfarne (Holy Island)",
        "Staffa",
    ]
    enriched = [i for i in islands if i.get("images")]
    random.seed(42)
    sample = random.sample(enriched, min(30, len(enriched)))
    iconic_sample = [i for i in islands if i["name"] in iconic]
    spot_check = []
    for i in iconic_sample + sample:
        img = (i.get("images") or [None])[0]
        if not img:
            continue
        spot_check.append(
            {
                "name": i["name"],
                "nation": i.get("nation"),
                "type": i.get("type"),
                "source": img["source"],
                "sourceRef": img["sourceRef"],
                "sourcePageUrl": img["sourcePageUrl"],
                "imageUrl": img["url"],
                "caption": img["caption"],
                "license": img["license"],
                "attribution": img["attribution"],
            }
        )

    # 7) Mismatch flagger --------------------------------------------------
    suspect: list[dict] = []
    for row in audit_rows:
        if row["source"] == "wikidata" and row.get("nameMentionedInWdLabel") is False:
            suspect.append(row)
        if row["source"] == "pageimage" and row.get("nameMentionedInWpTitle") is False:
            suspect.append(row)

    # 8) Write outputs -----------------------------------------------------
    ISLANDS_PATH.write_text(json.dumps(islands, ensure_ascii=False, indent=2) + "\n")
    REPORT_PATH.write_text(
        json.dumps(
            {
                "counts": counts,
                "total_islands": len(islands),
                "with_image": sum(1 for i in islands if i.get("images")),
                "without_image": counts["none"],
                "suspect_name_mismatches": suspect,
                "spot_check": spot_check,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )

    print()
    print(f"Total islands:     {len(islands)}", file=sys.stderr)
    print(f"With image:        {sum(1 for i in islands if i.get('images'))}", file=sys.stderr)
    print(f"  wikidata:        {counts['wikidata']}", file=sys.stderr)
    print(f"  pageimage:       {counts['pageimage']}", file=sys.stderr)
    print(f"  curated:         {counts['curated']}", file=sys.stderr)
    print(f"  (curated w/lic): {counts['curated_with_license']}", file=sys.stderr)
    print(f"Without image:     {counts['none']}", file=sys.stderr)
    print(f"Suspect mismatches (audit): {len(suspect)}", file=sys.stderr)
    print(f"Audit written to {REPORT_PATH.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
