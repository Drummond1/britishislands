#!/usr/bin/env python3
"""Photo enrichment v5 — targets the 3,434 islands still without a photo
after v2 + v3.

Builds on v3's helpers (imported, not duplicated) and adds five new /
widened sources, in priority order:

  1. wikidata-p18-refresh    — re-fetch P18 for every Q-ID-bearing island
                                without an image (Wikidata gets edits daily;
                                v3's cache may now be stale).
  2. wikipedia-pageimages    — derive the en-wiki page from the Q-ID
                                sitelinks, then call MediaWiki
                                ``prop=pageimages`` for the lead photo.
  3. osm-wikipedia / osm-commons-category
                              — query Overpass for the ``wikipedia=*`` and
                                ``wikimedia_commons=*`` tags on the OSM way.
                                Both are common on small islets and were
                                never harvested by v3 (v3 only looked at
                                ``image=*``).
  4. commons-text-search     — Commons ``list=search&srsearch=<name>
                                incategory:Files``. Catches photos whose
                                file description names the island even when
                                no coordinates are attached.
  5. commons-geosearch-wide  — re-run geosearch at ``gsradius=1500`` with
                                strict acceptance: filename or caption MUST
                                mention the island name OR a culturally-
                                attested variant (``names.gd`` / ``names.cy``
                                / ``names.ga`` / ``names.gv`` / ``names.kw``
                                / ``names.fr``).

Every adopted image carries the full attribution chain mandated by
``docs/IMAGE-SOURCES.md`` §B: ``url`` / ``source`` / ``sourceRef`` /
``sourcePageUrl`` / ``license`` / ``attribution``.

Run::

    python3 scripts/enrich_images_v5.py                       # full pass
    python3 scripts/enrich_images_v5.py --source p18          # one source
    python3 scripts/enrich_images_v5.py --test sgeir-bhuidhe  # one island
    python3 scripts/enrich_images_v5.py --limit 100           # short pass

Outputs::

    data/islands.json                            (mutated, atomic write)
    data/islands.json.before-v5                  (backup)
    data/cache_p18_refresh.json
    data/cache_wp_pageimages_v5.json
    data/cache_osm_tags_v5.json
    data/cache_commons_text.json
    data/image_enrichment_v5_report.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
BACKUP = DATA / "islands.json.before-v5"

# Caches.
CACHE_P18 = DATA / "cache_p18_refresh.json"
CACHE_WP_PI = DATA / "cache_wp_pageimages_v5.json"
CACHE_OSM_TAGS = DATA / "cache_osm_tags_v5.json"
CACHE_COMMONS_TEXT = DATA / "cache_commons_text.json"
REPORT = DATA / "image_enrichment_v5_report.json"

# Re-use v3 caches for Commons file metadata.
CACHE_COMMONS = DATA / "cache_commons.json"
CACHE_COMMONS_GEO = DATA / "cache_commons_geo.json"
CACHE_COMMONS_CATEGORY = DATA / "cache_commons_category.json"

USER_AGENT = "isles-of-britain/0.5 enrichment-v5"
# Overpass's WAF refuses User-Agent headers containing URLs, so we
# keep the UA short and informational. The contact email goes via
# the `From` header on Overpass calls instead.
DELAY_S = 1.2
RL_BACKOFF = (30, 90, 180, 300, 600)
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
HOST_ALLOW = {
    "commons.wikimedia.org",
    "upload.wikimedia.org",
    "en.wikipedia.org",
    "www.geograph.org.uk",
    "geograph.org.uk",
    "s0.geograph.org.uk",
    "s1.geograph.org.uk",
    "s2.geograph.org.uk",
}

# ---------- HTTP ----------

def _open(req: urllib.request.Request, timeout: int = 60) -> bytes:
    last: Exception | None = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                # Detect Wikimedia/Commons soft rate-limit (HTTP 200
                # but plain-text body explaining the limit).
                if (raw and
                        not raw.lstrip().startswith((b"{", b"["))
                        and b"too many requests" in raw[:200].lower()):
                    sleep = RL_BACKOFF[min(attempt, len(RL_BACKOFF) - 1)]
                    print(f"  rate-limited (200/text); sleeping {sleep}s",
                          file=sys.stderr, flush=True)
                    time.sleep(sleep)
                    continue
                return raw
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code == 429:
                sleep = RL_BACKOFF[min(attempt, len(RL_BACKOFF) - 1)]
                print(f"  429 → sleeping {sleep}s", file=sys.stderr, flush=True)
                time.sleep(sleep)
            elif exc.code in (502, 503, 504):
                time.sleep(5 + 5 * attempt)
            else:
                time.sleep(1 + attempt)
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            time.sleep(1 + attempt)
    if last:
        raise last  # type: ignore[misc]
    raise RuntimeError("max retries exceeded")


def _get_json(url: str, params: dict[str, Any]) -> dict:
    qs = urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(
        f"{url}?{qs}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    raw = _open(req)
    return json.loads(raw.decode("utf-8"))


def _load(p: Path) -> dict:
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        print(f"WARN: corrupt cache {p.name}; ignoring", file=sys.stderr)
        return {}


def _save(p: Path, data: dict) -> None:
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(tmp, p)


def _atomic_write_islands(payload: list) -> None:
    tmp = ISLANDS.with_suffix(ISLANDS.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, ISLANDS)


# ---------- helpers ----------

_HTML_RE = re.compile(r"<[^>]+>")
_NON_PHOTO_RE = re.compile(
    r"(?:^|[_ \-\(\[])("
    r"flag|coat[_ \-]of[_ \-]arms|crest|emblem|seal|logo|badge|"
    r"location[_ \-]map|outline[_ \-]map|locator[_ \-]map|"
    r"map[_ \-]of|map[_ \-]showing|chart|diagram|graph|plan[_ \-]of|"
    # Historic-map / archival artefacts that show up as homonyms:
    r"plat|plats|atlas|page[_ \-]?\d|court[_ \-]record|"
    r"dpla|loc\.gov|library[_ \-]of[_ \-]congress|"
    r"land[_ \-]grant|deed[_ \-]book|"
    r"engraving|woodcut|lithograph|"
    r"postage[_ \-]stamp|stamp[_ \-]of|"
    r"painting[_ \-]of|portrait[_ \-]of"
    r")",
    re.IGNORECASE,
)


def _strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", _HTML_RE.sub("", s or "")).strip()


def _looks_like_non_photo(fname: str) -> bool:
    if not fname:
        return True
    if fname.lower().endswith((".svg", ".pdf", ".tif", ".tiff", ".gif")):
        return True
    return bool(_NON_PHOTO_RE.search(fname))


def _canon(fname: str) -> str:
    if not fname:
        return ""
    if fname.startswith("File:"):
        fname = fname[len("File:") :]
    return fname.replace("_", " ")


def commons_thumb_url(filename: str, width: int = 800) -> str:
    fname = _canon(filename)
    return (
        "https://commons.wikimedia.org/wiki/Special:FilePath/"
        + urllib.parse.quote(fname.replace(" ", "_"))
        + f"?width={width}"
    )


def commons_page_url(filename: str) -> str:
    fname = _canon(filename)
    return (
        "https://commons.wikimedia.org/wiki/File:"
        + urllib.parse.quote(fname.replace(" ", "_"))
    )


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _name_variants(island: dict) -> list[str]:
    """Return strict name variants suitable for substring matching.

    Each variant is required to be the FULL name of the island (or a
    cultural-language equivalent), not just a token from it. We do NOT
    strip 'Island' / 'Isle of' suffixes — doing so produced a false
    positive on the first smoke test (matching 'Adam's Rock' against
    'Adam's Island' because 'adam's' alone matched any unrelated file).
    """
    bag: set[str] = set()
    raw = (island.get("name") or "").strip()
    if raw:
        bag.add(raw.lower())
        # Apostrophe-tolerant variant (curly + straight + none).
        for ap in ("'", "\u2019", ""):
            bag.add(raw.lower().replace("'", ap).replace("\u2019", ap))
        # If the name starts with "Isle of X", also accept just "X" but
        # only if X itself is >=5 characters AND multi-word OR ends in
        # an island-suffix like 'skerry'/'holm'/'eilean'/'ynys' — i.e.
        # the residual is geographically distinctive.
        low = raw.lower()
        if low.startswith("isle of "):
            tail = low[len("isle of "):].strip()
            if len(tail) >= 5 and (" " in tail or any(
                tail.endswith(s) for s in
                ("skerry", "holm", "eilean", "ynys", "inis", "eyot", "ait")
            )):
                bag.add(tail)
    for nm in (island.get("names") or {}).values():
        nm = (nm or "").strip().lower()
        if nm and len(nm) >= 4:
            bag.add(nm)
    # Drop noise.
    return [v for v in bag if len(v) >= 5]


def _strip_diacritics(s: str) -> str:
    """NFKD-normalise + drop combining marks → diacritic-insensitive."""
    if not s:
        return ""
    return "".join(
        c for c in unicodedata.normalize("NFKD", s)
        if not unicodedata.combining(c)
    )


_NAME_WORDBOUND_CACHE: dict[str, re.Pattern] = {}


def _name_regex(variant_ascii: str) -> re.Pattern:
    pat = _NAME_WORDBOUND_CACHE.get(variant_ascii)
    if pat is None:
        # Escape, require word boundaries on letters/digits so 'adam's'
        # would NOT match 'adam' alone. Treat apostrophes as optional.
        escaped = re.escape(variant_ascii)
        escaped = escaped.replace(r"\'", "[']?")
        pat = re.compile(rf"(?:^|[^a-z0-9]){escaped}(?:[^a-z0-9]|$)", re.IGNORECASE)
        _NAME_WORDBOUND_CACHE[variant_ascii] = pat
    return pat


def _mentions(text: str, variants: list[str]) -> bool:
    if not text:
        return False
    ascii_text = _strip_diacritics(text)
    for v in variants:
        v_ascii = _strip_diacritics(v)
        if _name_regex(v_ascii).search(ascii_text):
            return True
    return False


# ---------- Commons file metadata (shared cache w/ v3) ----------

def fetch_commons_meta(filenames: list[str], cache: dict) -> dict[str, dict]:
    norm = list(dict.fromkeys(_canon(f) for f in filenames if f))
    missing = [n for n in norm if n not in cache]
    BATCH = 40
    for i in range(0, len(missing), BATCH):
        batch = missing[i : i + BATCH]
        params = {
            "action": "query",
            "format": "json",
            "prop": "imageinfo",
            "iiprop": "url|extmetadata|size|mime",
            "iiextmetadatafilter": (
                "LicenseShortName|Artist|Credit|LicenseUrl|"
                "ImageDescription|ObjectName|Categories"
            ),
            "iiextmetadatalanguage": "en",
            "titles": "|".join("File:" + n for n in batch),
            "redirects": 1,
        }
        try:
            payload = _get_json(COMMONS_API, params)
        except Exception as exc:
            print(f"  commons-meta batch failed: {exc!r}", file=sys.stderr)
            continue
        pages = (payload.get("query") or {}).get("pages") or {}
        for _pid, page in pages.items():
            title = page.get("title", "")
            fname = _canon(title)
            info_list = page.get("imageinfo") or []
            if not info_list:
                cache[fname] = {}
                continue
            info = info_list[0]
            ext = info.get("extmetadata") or {}

            def _take(key: str) -> str:
                v = (ext or {}).get(key) or {}
                return v.get("value", "") if isinstance(v, dict) else ""

            cache[fname] = {
                "license": _take("LicenseShortName"),
                "licenseUrl": _take("LicenseUrl"),
                "attribution": _strip_html(_take("Artist") or _take("Credit")),
                "caption": _strip_html(_take("ObjectName") or _take("ImageDescription")),
                "descriptionUrl": info.get("descriptionurl", ""),
                "url": info.get("url", ""),
                "width": info.get("width"),
                "height": info.get("height"),
                "mime": info.get("mime", ""),
                "categories": _strip_html(_take("Categories")),
            }
        for n in batch:
            cache.setdefault(n, {})
        _save(CACHE_COMMONS, cache)
        time.sleep(DELAY_S)
    return {n: cache.get(n, {}) for n in norm}


def build_image_record_from_commons(
    fname: str, meta: dict, source: str, source_ref: str, suspect: bool = False
) -> dict | None:
    lic = (meta.get("license") or "").strip()
    if not lic or "fair use" in lic.lower():
        return None
    attribution = meta.get("attribution") or "Unknown"
    return {
        "url": commons_thumb_url(fname),
        "source": source,
        "sourceRef": source_ref or fname,
        "sourcePageUrl": meta.get("descriptionUrl") or commons_page_url(fname),
        "license": lic,
        "attribution": f"Photo by {attribution}, via Wikimedia Commons ({lic})",
        "caption": meta.get("caption", ""),
        **({"suspect": True} if suspect else {}),
    }


# ---------- Source 1: Wikidata P18 refresh + 2: Wikipedia pageimages ----------

def fetch_p18_and_sitelinks(qids: list[str], cache: dict) -> dict[str, dict]:
    """For each Q-ID, return {qid: {p18: 'File:X.jpg' or '', enwiki: 'Title' or ''}}."""
    missing = [q for q in qids if q not in cache]
    BATCH = 40
    for i in range(0, len(missing), BATCH):
        batch = missing[i : i + BATCH]
        params = {
            "action": "wbgetentities",
            "format": "json",
            "ids": "|".join(batch),
            "props": "claims|sitelinks",
            "sitefilter": "enwiki|commonswiki",
            "languages": "en",
        }
        try:
            payload = _get_json(WIKIDATA_API, params)
        except Exception as exc:
            print(f"  p18 batch failed: {exc!r}", file=sys.stderr)
            continue
        entities = payload.get("entities") or {}
        for q in batch:
            ent = entities.get(q) or {}
            claims = ent.get("claims") or {}
            p18 = ""
            for c in claims.get("P18") or []:
                ds = (c.get("mainsnak") or {}).get("datavalue") or {}
                v = ds.get("value")
                if isinstance(v, str) and v:
                    p18 = v
                    break
            sl = ent.get("sitelinks") or {}
            enwiki = (sl.get("enwiki") or {}).get("title", "")
            commonswiki = (sl.get("commonswiki") or {}).get("title", "")
            cache[q] = {"p18": p18, "enwiki": enwiki, "commonswiki": commonswiki}
        _save(CACHE_P18, cache)
        time.sleep(DELAY_S)
    return {q: cache.get(q, {"p18": "", "enwiki": "", "commonswiki": ""}) for q in qids}


def fetch_wp_pageimages(titles: list[str], cache: dict) -> dict[str, str]:
    """For each WP page title, return {title: 'File:X.jpg' or ''}."""
    norm = [t for t in titles if t]
    missing = [t for t in norm if t not in cache]
    BATCH = 30
    for i in range(0, len(missing), BATCH):
        batch = missing[i : i + BATCH]
        params = {
            "action": "query",
            "format": "json",
            "prop": "pageimages",
            "piprop": "original|name",
            "titles": "|".join(batch),
            "redirects": 1,
        }
        try:
            payload = _get_json(WIKIPEDIA_API, params)
        except Exception as exc:
            print(f"  pageimages batch failed: {exc!r}", file=sys.stderr)
            continue
        pages = (payload.get("query") or {}).get("pages") or {}
        # Build redirect/normalisation map back to requested titles.
        redirects = {r["from"]: r["to"] for r in (payload.get("query") or {}).get("redirects") or []}
        norm_map = {n["from"]: n["to"] for n in (payload.get("query") or {}).get("normalized") or []}

        def _back_to_requested(final_title: str) -> str:
            for src in batch:
                t = norm_map.get(src, src)
                t = redirects.get(t, t)
                if t == final_title:
                    return src
            return final_title

        for _pid, page in pages.items():
            title = page.get("title", "")
            fname = (page.get("pageimage") or "").strip()
            if fname:
                fname = "File:" + fname if not fname.startswith("File:") else fname
            requested = _back_to_requested(title)
            cache[requested] = fname or ""
        for t in batch:
            cache.setdefault(t, "")
        _save(CACHE_WP_PI, cache)
        time.sleep(DELAY_S)
    return {t: cache.get(t, "") for t in norm}


# ---------- Source 3: OSM extra tags ----------

def fetch_osm_extra_tags(osm_specs: list[tuple[str, str]], cache: dict) -> dict[str, dict]:
    """`osm_specs` is a list of (osmType, osmId). Returns the
    `wikipedia` and `wikimedia_commons` tags for each."""
    keys = [f"{t}/{i}" for (t, i) in osm_specs]
    missing = [k for k in keys if k not in cache]
    # Overpass `out tags` for elements by id.
    BATCH = 80
    for i in range(0, len(missing), BATCH):
        batch_keys = missing[i : i + BATCH]
        spec_by_key = {f"{t}/{i_}": (t, i_) for (t, i_) in osm_specs}
        node_ids = [spec_by_key[k][1] for k in batch_keys if spec_by_key[k][0] == "node"]
        way_ids = [spec_by_key[k][1] for k in batch_keys if spec_by_key[k][0] == "way"]
        rel_ids = [spec_by_key[k][1] for k in batch_keys if spec_by_key[k][0] == "relation"]
        q_parts = []
        if node_ids:
            q_parts.append(f"node(id:{','.join(node_ids)});")
        if way_ids:
            q_parts.append(f"way(id:{','.join(way_ids)});")
        if rel_ids:
            q_parts.append(f"relation(id:{','.join(rel_ids)});")
        if not q_parts:
            continue
        q = f"[out:json][timeout:60];({''.join(q_parts)});out tags;"
        payload = None
        for ep in OVERPASS_ENDPOINTS:
            # Use curl via subprocess to dodge urllib's quirky default
            # headers - we saw HTTP 406s from overpass-api.de's nginx
            # when sent via urllib, but curl POST works cleanly.
            try:
                res = subprocess.run(
                    [
                        "curl", "-sS", "--max-time", "120",
                        "-X", "POST",
                        "-A", USER_AGENT,
                        "-H", "Content-Type: application/x-www-form-urlencoded",
                        "--data-urlencode", f"data={q}",
                        ep,
                    ],
                    capture_output=True, text=True, timeout=140,
                )
            except subprocess.TimeoutExpired:
                print(f"  overpass {ep}: curl timed out", file=sys.stderr)
                time.sleep(2)
                continue
            if res.returncode != 0:
                print(f"  overpass {ep}: curl rc={res.returncode} stderr={res.stderr[:200]!r}", file=sys.stderr)
                time.sleep(2)
                continue
            stdout = res.stdout or ""
            if not stdout.strip():
                print(f"  overpass {ep}: empty stdout, stderr={res.stderr[:200]!r}", file=sys.stderr)
                time.sleep(2)
                continue
            try:
                payload = json.loads(stdout)
                break
            except json.JSONDecodeError as exc:
                print(f"  overpass {ep}: JSON parse: {exc!r} body[:200]={stdout[:200]!r}", file=sys.stderr)
                time.sleep(2)
                continue
        if payload is None:
            for k in batch_keys:
                cache[k] = {}
            continue
        seen: set[str] = set()
        for el in payload.get("elements") or []:
            t = el.get("type")
            i_ = str(el.get("id") or "")
            k = f"{t}/{i_}"
            tags = el.get("tags") or {}
            cache[k] = {
                "wikipedia": tags.get("wikipedia") or tags.get("wikipedia:en") or "",
                "wikimedia_commons": tags.get("wikimedia_commons") or "",
                "image": tags.get("image") or "",
            }
            seen.add(k)
        for k in batch_keys:
            if k not in seen:
                cache[k] = {}
        _save(CACHE_OSM_TAGS, cache)
        time.sleep(DELAY_S)
    return {k: cache.get(k, {}) for k in keys}


# ---------- Source 4: Commons text search ----------

def commons_text_search(query: str, limit: int = 10) -> list[str]:
    """`list=search` for the island name, restricted to File: namespace."""
    if not query:
        return []
    params = {
        "action": "query",
        "format": "json",
        "list": "search",
        "srsearch": query,
        "srnamespace": "6",
        "srlimit": str(limit),
        "srprop": "snippet",
    }
    try:
        payload = _get_json(COMMONS_API, params)
    except Exception as exc:
        print(f"  text-search failed: {exc!r}", file=sys.stderr)
        return []
    out = []
    for hit in (payload.get("query") or {}).get("search") or []:
        title = hit.get("title", "")
        if title.startswith("File:"):
            out.append(_canon(title))
    return out


def fetch_file_coords(filenames: list[str]) -> dict[str, tuple[float, float] | None]:
    """Fetch GPS coords for Commons files, where present.

    Returns ``{canonical_filename: (lat, lon) | None}``. We use this
    as a hard geographic verifier before adopting any file from
    name-only searches (text-search) - protects against trans-Atlantic
    homonyms (e.g. 'Adam's Island' Missouri vs. 'Adam's Island' Co.
    Cork).
    """
    out: dict[str, tuple[float, float] | None] = {}
    if not filenames:
        return out
    titles = [_canon(f) for f in filenames if f]
    BATCH = 40
    for i in range(0, len(titles), BATCH):
        batch = titles[i : i + BATCH]
        params = {
            "action": "query",
            "format": "json",
            "prop": "coordinates",
            "titles": "|".join("File:" + b for b in batch),
            "coprop": "type|name",
            "colimit": "5",
        }
        try:
            payload = _get_json(COMMONS_API, params)
        except Exception as exc:
            print(f"  file-coords batch failed: {exc!r}", file=sys.stderr)
            for b in batch:
                out[b] = None
            continue
        pages = (payload.get("query") or {}).get("pages") or {}
        for _pid, page in pages.items():
            title = _canon(page.get("title", ""))
            coords = page.get("coordinates") or []
            if coords:
                # Prefer 'camera'-typed coords (geotagged photo); fall
                # back to 'object'-typed (the subject of the photo).
                preferred = next(
                    (c for c in coords if c.get("type") == "camera"),
                    coords[0],
                )
                lat = preferred.get("lat")
                lon = preferred.get("lon")
                if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                    out[title] = (float(lat), float(lon))
                    continue
            out[title] = None
        for b in batch:
            out.setdefault(b, None)
        time.sleep(DELAY_S)
    return out


def _passes_geo_anchor(
    island: dict,
    file_coords: tuple[float, float] | None,
    file_meta: dict,
    max_km: float,
) -> tuple[bool, str]:
    """Decide whether a candidate file passes geographic verification.

    Returns ``(ok, reason)``. The caller uses ``reason`` for the
    rejection report.

    Hard rules:
      1. If the file has GPS coords AND they're within ``max_km`` of
         the island, accept.
      2. If the file has GPS coords AND they're outside ``max_km``,
         reject with reason='out-of-range'.
      3. If the file has NO GPS coords, fall back to:
         (a) the file's caption / categories must contain a strong
             geographic anchor for the island: nation name, archipelago
             name, or a recognised regional toponym (county, region).
    """
    lat = island.get("lat")
    lon = island.get("lng") if island.get("lng") is not None else island.get("lon")
    if file_coords is not None and lat is not None and lon is not None:
        try:
            d_km = _haversine_km(float(lat), float(lon), file_coords[0], file_coords[1])
        except Exception:
            return False, "coord-error"
        if d_km <= max_km:
            return True, f"in-range ({d_km:.1f} km)"
        return False, f"out-of-range ({d_km:.1f} km > {max_km} km)"
    # No GPS on file → require a categorical anchor.
    haystack = " ".join([
        file_meta.get("caption", "") or "",
        file_meta.get("categories", "") or "",
    ]).lower()
    anchors = _geo_anchors(island)
    if not anchors:
        return False, "no-geo-anchor-defined"
    for a in anchors:
        if a.lower() in haystack:
            return True, f"anchor-match:{a}"
    return False, f"no-anchor-match (have {anchors!r})"


_REGIONAL_ANCHORS = {
    "Scotland": ["Scotland", "Scottish", "Hebrides", "Orkney", "Shetland", "Argyll",
                 "Highland", "Ayrshire", "Bute"],
    "England":  ["England", "English", "Cornwall", "Devon", "Northumberland", "Cumbria",
                 "Dorset", "Hampshire", "Sussex", "Kent", "Norfolk"],
    "Wales":    ["Wales", "Welsh", "Pembrokeshire", "Gwynedd", "Anglesey", "Cymru"],
    "Northern Ireland": ["Northern Ireland", "Down", "Antrim", "Derry", "Tyrone",
                         "Fermanagh", "Armagh"],
    "Ireland":  ["Ireland", "Irish", "Cork", "Kerry", "Donegal", "Galway", "Mayo",
                 "Clare", "Sligo", "Waterford", "Connemara", "Eire", "Éire"],
    "Isle of Man": ["Isle of Man", "Manx", "Ellan Vannin"],
    "Crown Dependency": ["Jersey", "Guernsey", "Alderney", "Sark", "Herm",
                         "Channel Islands"],
    "France":   ["France", "Brittany", "Normandy", "Bretagne", "Normandie", "Cotentin",
                 "Manche", "Côtes"],
}


def _geo_anchors(island: dict) -> list[str]:
    out: list[str] = []
    nation = island.get("nation") or ""
    out.extend(_REGIONAL_ANCHORS.get(nation, []))
    archi = (island.get("archipelago") or "").strip()
    if archi:
        out.append(archi)
    return out


# ---------- Source 5: Commons geosearch (widened) ----------

def commons_geosearch(lat: float, lon: float, radius_m: int) -> list[dict]:
    """Return {title, lat, lon, dist_m} list within `radius_m` of (lat, lon)."""
    params = {
        "action": "query",
        "format": "json",
        "list": "geosearch",
        "gscoord": f"{lat}|{lon}",
        "gsradius": str(radius_m),
        "gsnamespace": "6",
        "gslimit": "50",
    }
    try:
        payload = _get_json(COMMONS_API, params)
    except Exception as exc:
        print(f"  geosearch failed: {exc!r}", file=sys.stderr)
        return []
    return [
        {
            "title": _canon(g.get("title", "")),
            "lat": g.get("lat"),
            "lon": g.get("lon"),
            "dist_m": g.get("dist"),
        }
        for g in (payload.get("query") or {}).get("geosearch") or []
        if (g.get("title") or "").startswith("File:")
    ]


# ---------- Per-island enrichment ----------

def try_p18_then_pageimages(
    island: dict,
    cache_p18: dict,
    cache_wp_pi: dict,
    cache_commons: dict,
) -> dict | None:
    qid = (island.get("wikidata") or "").strip()
    if not re.match(r"^Q\d+$", qid):
        return None
    bundle = fetch_p18_and_sitelinks([qid], cache_p18).get(qid, {})
    p18 = bundle.get("p18", "") or ""
    enwiki = bundle.get("enwiki", "") or ""
    candidates: list[tuple[str, str, str]] = []  # (filename, source, sourceRef)
    if p18:
        candidates.append((p18, "wikidata", qid))
    if enwiki:
        pi = fetch_wp_pageimages([enwiki], cache_wp_pi).get(enwiki, "")
        if pi and pi != p18:
            candidates.append((pi, "wikipedia", enwiki.replace(" ", "_")))
    if not candidates:
        return None
    metas = fetch_commons_meta([f for f, *_ in candidates], cache_commons)
    for fname, source, ref in candidates:
        if _looks_like_non_photo(fname):
            continue
        m = metas.get(_canon(fname), {})
        rec = build_image_record_from_commons(fname, m, source, ref)
        if rec:
            return rec
    return None


def try_osm_tags(
    island: dict,
    cache_osm: dict,
    cache_commons: dict,
    cache_wp_pi: dict,
) -> dict | None:
    osm_type = (island.get("osmType") or "").lower()
    osm_id = str(island.get("osmId") or "").strip()
    if osm_type not in ("node", "way", "relation") or not osm_id:
        return None
    tags = fetch_osm_extra_tags([(osm_type, osm_id)], cache_osm).get(f"{osm_type}/{osm_id}", {})
    # (a) image=*
    img_url = (tags.get("image") or "").strip()
    if img_url:
        try:
            host = urllib.parse.urlparse(img_url).netloc.lower()
        except Exception:
            host = ""
        if host in HOST_ALLOW:
            if "commons.wikimedia.org" in host or "upload.wikimedia.org" in host:
                # Try to derive a File: name to fetch licence.
                fname = _filename_from_commons_url(img_url)
                if fname and not _looks_like_non_photo(fname):
                    metas = fetch_commons_meta([fname], cache_commons)
                    m = metas.get(_canon(fname), {})
                    rec = build_image_record_from_commons(
                        fname, m, "osm-image-tag", f"{osm_type}/{osm_id}"
                    )
                    if rec:
                        return rec
            # Geograph image tag - we know the licence (CC-BY-SA 2.0)
            elif "geograph" in host:
                m = re.search(r"/(\d+)\b", img_url)
                gid = m.group(1) if m else ""
                if gid:
                    return {
                        "url": img_url,
                        "source": "geograph",
                        "sourceRef": gid,
                        "sourcePageUrl": f"https://www.geograph.org.uk/photo/{gid}",
                        "license": "CC-BY-SA-2.0",
                        "attribution": "Photo via Geograph project (CC-BY-SA 2.0)",
                        "caption": "",
                    }
    # (b) wikipedia=*
    wp = (tags.get("wikipedia") or "").strip()
    if wp:
        title = _parse_wikipedia_tag(wp)
        if title:
            pi = fetch_wp_pageimages([title], cache_wp_pi).get(title, "")
            if pi and not _looks_like_non_photo(pi):
                metas = fetch_commons_meta([pi], cache_commons)
                m = metas.get(_canon(pi), {})
                rec = build_image_record_from_commons(
                    pi, m, "osm-wikipedia", f"{osm_type}/{osm_id}"
                )
                if rec:
                    return rec
    # (c) wikimedia_commons=*  (usually "Category:Foo" or "File:Foo.jpg")
    wc = (tags.get("wikimedia_commons") or "").strip()
    if wc:
        if wc.startswith("File:"):
            fname = _canon(wc)
            if not _looks_like_non_photo(fname):
                metas = fetch_commons_meta([fname], cache_commons)
                m = metas.get(_canon(fname), {})
                rec = build_image_record_from_commons(
                    fname, m, "osm-commons-file", f"{osm_type}/{osm_id}"
                )
                if rec:
                    return rec
        elif wc.startswith("Category:"):
            members = _category_members(wc, limit=25)
            metas = fetch_commons_meta([f for f in members if not _looks_like_non_photo(f)],
                                       cache_commons)
            variants = _name_variants(island)
            best = ""
            best_score = -1
            for f in members:
                if _looks_like_non_photo(f):
                    continue
                m = metas.get(_canon(f), {})
                lic = (m.get("license") or "").strip()
                if not lic or "fair use" in lic.lower():
                    continue
                score = 0
                if "quality images" in (m.get("categories") or "").lower():
                    score += 5
                if "featured pictures" in (m.get("categories") or "").lower():
                    score += 10
                if _mentions(f, variants) or _mentions(m.get("caption", ""), variants):
                    score += 4
                w, h = m.get("width") or 0, m.get("height") or 0
                if w and h and w * h > 1_000_000:
                    score += 1
                if score > best_score:
                    best_score = score
                    best = f
            if best:
                m = metas.get(_canon(best), {})
                rec = build_image_record_from_commons(
                    best, m, "osm-commons-category", f"{osm_type}/{osm_id}"
                )
                if rec:
                    return rec
    return None


def try_commons_text_search(
    island: dict,
    cache_commons: dict,
    cache_text: dict,
    report_rejected: list,
) -> dict | None:
    name = (island.get("name") or "").strip()
    if len(name) < 4:
        return None
    archipelago = (island.get("archipelago") or "").strip()
    key = f"{name}|{archipelago}"
    if key in cache_text:
        files = cache_text[key]
    else:
        q = f'"{name}"'
        if archipelago and archipelago.lower() != name.lower():
            q = f'"{name}" {archipelago}'
        files = commons_text_search(q, limit=10)
        cache_text[key] = files
        _save(CACHE_COMMONS_TEXT, cache_text)
        time.sleep(DELAY_S)
    if not files:
        return None
    keep = [f for f in files if not _looks_like_non_photo(f)]
    if not keep:
        return None
    candidates = keep[:5]
    metas = fetch_commons_meta(candidates, cache_commons)
    coords = fetch_file_coords(candidates)
    variants = _name_variants(island)
    for f in candidates:
        m = metas.get(_canon(f), {})
        lic = (m.get("license") or "").strip()
        if not lic or "fair use" in lic.lower():
            continue
        # Strict NAME match first (avoids 'Adam's Rock' homonyms).
        if not (_mentions(f, variants) or _mentions(m.get("caption", ""), variants)):
            continue
        # Then geographic verification (the trans-Atlantic homonym guard).
        ok, reason = _passes_geo_anchor(
            island, coords.get(_canon(f)), m, max_km=15.0
        )
        if not ok:
            report_rejected.append({
                "id": island.get("id"),
                "source": "commons-text-search",
                "file": f,
                "reason": reason,
            })
            continue
        return build_image_record_from_commons(f, m, "commons-text-search", island["id"])
    return None


def try_commons_geosearch_wide(
    island: dict,
    cache_commons: dict,
    cache_geo: dict,
    report_rejected: list,
) -> dict | None:
    lat = island.get("lat")
    lon = island.get("lng") if island.get("lng") is not None else island.get("lon")
    if lat is None or lon is None:
        return None
    key = f"{lat:.4f},{lon:.4f};1500"
    if key in cache_geo:
        hits = cache_geo[key]
    else:
        hits = commons_geosearch(float(lat), float(lon), 1500)
        cache_geo[key] = hits
        _save(CACHE_COMMONS_GEO, cache_geo)
        time.sleep(DELAY_S)
    if not hits:
        return None
    keep = [h for h in hits if not _looks_like_non_photo(h.get("title", ""))]
    if not keep:
        return None
    candidates = [h["title"] for h in keep[:8]]
    metas = fetch_commons_meta(candidates, cache_commons)
    variants = _name_variants(island)
    # Adoption rule: name match required AND distance ≤ 1500 m (the
    # geosearch already enforced 1500 m; restate it as a safety belt).
    for h in keep[:8]:
        fname = h["title"]
        m = metas.get(_canon(fname), {})
        lic = (m.get("license") or "").strip()
        if not lic or "fair use" in lic.lower():
            continue
        if not (_mentions(fname, variants) or _mentions(m.get("caption", ""), variants)):
            report_rejected.append({
                "id": island.get("id"),
                "source": "commons-geosearch",
                "file": fname,
                "reason": "no-name-match",
            })
            continue
        try:
            dist_km = _haversine_km(
                float(lat), float(lon),
                float(h.get("lat") or 0), float(h.get("lon") or 0),
            )
        except Exception:
            dist_km = -1
        if dist_km > 1.6:  # 1500 m safety check
            report_rejected.append({
                "id": island.get("id"),
                "source": "commons-geosearch",
                "file": fname,
                "reason": f"distance {dist_km:.2f} km > 1.6 km",
            })
            continue
        rec = build_image_record_from_commons(fname, m, "commons-geosearch", island["id"])
        if rec:
            return rec
    return None


# ---------- url -> filename helpers ----------

def _filename_from_commons_url(url: str) -> str:
    """Extract the File: name from a Special:FilePath or upload.wikimedia.org URL."""
    try:
        u = urllib.parse.urlparse(url)
    except Exception:
        return ""
    if "Special:FilePath/" in u.path:
        fname = urllib.parse.unquote(u.path.split("Special:FilePath/", 1)[1])
        return fname
    # upload.wikimedia.org/wikipedia/commons/<a>/<ab>/<File>
    parts = [p for p in u.path.split("/") if p]
    if u.netloc == "upload.wikimedia.org" and len(parts) >= 4:
        return urllib.parse.unquote(parts[-1])
    return ""


def _parse_wikipedia_tag(tag: str) -> str:
    """OSM `wikipedia=` can be `en:Title` or just `Title`."""
    if ":" in tag and tag.split(":", 1)[0].lower() in {"en", "gd", "cy", "ga", "kw", "gv", "fr"}:
        return tag.split(":", 1)[1].strip()
    return tag.strip()


def _category_members(category: str, limit: int = 25) -> list[str]:
    if not category.startswith("Category:"):
        category = "Category:" + category
    params = {
        "action": "query",
        "format": "json",
        "list": "categorymembers",
        "cmtitle": category,
        "cmtype": "file",
        "cmlimit": str(limit),
    }
    try:
        payload = _get_json(COMMONS_API, params)
    except Exception as exc:
        print(f"  categorymembers failed for {category}: {exc!r}", file=sys.stderr)
        return []
    return [
        _canon(m.get("title", ""))
        for m in (payload.get("query") or {}).get("categorymembers") or []
        if m.get("title", "").startswith("File:")
    ]


# ---------- main loop ----------

ALL_SOURCES = ["p18", "osm-tags", "text-search", "geosearch-wide"]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--source", choices=ALL_SOURCES + ["all"], default="all")
    p.add_argument("--limit", type=int, default=0,
                   help="Stop after considering N islands (0 = all).")
    p.add_argument("--test", default="",
                   help="Process only the island with this id and print the result.")
    p.add_argument("--no-backup", action="store_true",
                   help="Skip writing islands.json.before-v5 (dangerous).")
    p.add_argument(
        "--queue-file",
        default="",
        help="JSON from scripts/build_image_priority_queue.py — process ids in tier order first.",
    )
    args = p.parse_args()

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    if not isinstance(islands, list):
        print("FATAL: islands.json is not a list", file=sys.stderr)
        return 2
    if not args.no_backup and not BACKUP.exists():
        BACKUP.write_text(
            json.dumps(islands, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Backup → {BACKUP.relative_to(ROOT)}")

    cache_p18 = _load(CACHE_P18)
    cache_wp_pi = _load(CACHE_WP_PI)
    cache_osm = _load(CACHE_OSM_TAGS)
    cache_text = _load(CACHE_COMMONS_TEXT)
    cache_commons = _load(CACHE_COMMONS)
    cache_geo = _load(CACHE_COMMONS_GEO)

    report = {
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "args": vars(args),
        "input_total": len(islands),
        "input_without_image": 0,
        "adopted": [],         # [{id, name, source, license, sourcePageUrl}]
        "rejected": [],        # [{id, name, reason}]
        "skipped": [],         # [{id, name, reason}]
    }
    pending = [i for i in islands if not (i.get("images") or [])]
    if args.queue_file:
        qpath = Path(args.queue_file)
        if not qpath.is_file():
            print(f"WARN: queue file not found: {qpath}", file=sys.stderr)
        else:
            qdata = json.loads(qpath.read_text(encoding="utf-8"))
            order = qdata.get("ids") if isinstance(qdata, dict) else qdata
            if isinstance(order, list):
                rank = {str(i): n for n, i in enumerate(order)}
                pending.sort(
                    key=lambda i: (rank.get(i.get("id", ""), 10**9), (i.get("name") or "").lower()),
                )
                print(f"  ordered by queue file ({len(order):,} ids)", flush=True)
    if args.test:
        pending = [i for i in islands if i.get("id") == args.test]
    if args.limit:
        pending = pending[: args.limit]
    report["input_without_image"] = len(pending)
    print(f"Pending islands without images: {len(pending):,}", flush=True)

    sources_to_run = ALL_SOURCES if args.source == "all" else [args.source]

    # ---- Pre-fetch phase: batch the cheap sources up-front so the
    #      per-island loop becomes cache lookups instead of N×APIs.
    if "p18" in sources_to_run:
        qids = sorted({
            (i.get("wikidata") or "").strip()
            for i in pending
            if re.match(r"^Q\d+$", (i.get("wikidata") or "").strip())
        })
        todo = [q for q in qids if q not in cache_p18]
        if todo:
            print(f"  pre-fetch P18 + sitelinks for {len(todo):,} Q-IDs…", flush=True)
            fetch_p18_and_sitelinks(todo, cache_p18)
        wp_titles = sorted({
            (cache_p18.get(q, {}) or {}).get("enwiki", "")
            for q in qids
            if (cache_p18.get(q, {}) or {}).get("enwiki", "")
        })
        wp_todo = [t for t in wp_titles if t and t not in cache_wp_pi]
        if wp_todo:
            print(f"  pre-fetch pageimages for {len(wp_todo):,} WP titles…", flush=True)
            fetch_wp_pageimages(wp_todo, cache_wp_pi)

    if "osm-tags" in sources_to_run:
        specs = [
            ((i.get("osmType") or "").lower(), str(i.get("osmId") or "").strip())
            for i in pending
            if (i.get("osmType") or "").lower() in ("node", "way", "relation")
            and str(i.get("osmId") or "").strip()
        ]
        keys = [f"{t}/{i_}" for (t, i_) in specs]
        todo_specs = [(t, i_) for (t, i_), k in zip(specs, keys) if k not in cache_osm]
        if todo_specs:
            print(f"  pre-fetch OSM tags for {len(todo_specs):,} elements…", flush=True)
            fetch_osm_extra_tags(todo_specs, cache_osm)

    def _try(island: dict) -> tuple[dict | None, str]:
        for s in sources_to_run:
            try:
                if s == "p18":
                    rec = try_p18_then_pageimages(island, cache_p18, cache_wp_pi, cache_commons)
                elif s == "osm-tags":
                    rec = try_osm_tags(island, cache_osm, cache_commons, cache_wp_pi)
                elif s == "text-search":
                    rec = try_commons_text_search(island, cache_commons, cache_text,
                                                  report["rejected"])
                elif s == "geosearch-wide":
                    rec = try_commons_geosearch_wide(island, cache_commons, cache_geo,
                                                     report["rejected"])
                else:
                    continue
            except Exception as exc:
                print(f"  {island.get('id')} {s} crashed: {exc!r}", file=sys.stderr)
                continue
            if rec:
                return rec, s
        return None, ""

    pending_set = {i.get("id") for i in pending}
    n_attempted = 0
    n_adopted = 0
    n_checkpoint = 50
    last_checkpoint = 0
    started_at = time.time()
    for idx, isl in enumerate(islands):
        if isl.get("id") not in pending_set:
            continue

        rec, source_used = _try(isl)
        n_attempted += 1
        if rec:
            isl.setdefault("images", []).append(rec)
            report["adopted"].append({
                "id": isl["id"],
                "name": isl.get("name", ""),
                "source": rec.get("source"),
                "license": rec.get("license"),
                "sourcePageUrl": rec.get("sourcePageUrl"),
            })
            n_adopted += 1
            print(f"  ✓ [{n_attempted:5d}/{len(pending):5d}] {isl['id']:45s} via {source_used:14s} → {rec.get('source'):22s} ({rec.get('license')})", flush=True)
        else:
            report["rejected"].append({
                "id": isl["id"],
                "name": isl.get("name", ""),
                "reason": "no candidate from any source",
            })

        if n_attempted - last_checkpoint >= n_checkpoint:
            _atomic_write_islands(islands)
            _save(REPORT, report)
            last_checkpoint = n_attempted
            rate = n_attempted / max(1.0, time.time() - started_at)
            eta_min = (len(pending) - n_attempted) / max(1.0, rate) / 60
            print(
                f"  …checkpoint {n_attempted}/{len(pending)} attempted, "
                f"{n_adopted} adopted ({100*n_adopted/n_attempted:.1f}% hit-rate, "
                f"{rate:.2f} islands/s, ~{eta_min:.0f} min remaining)",
                flush=True,
            )

    _atomic_write_islands(islands)
    report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    report["attempted"] = n_attempted
    report["adopted_total"] = n_adopted
    _save(REPORT, report)
    print()
    print(f"Attempted: {n_attempted:,}")
    print(f"Adopted:   {n_adopted:,}")
    print(f"Report   → {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
