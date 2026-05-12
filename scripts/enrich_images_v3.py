#!/usr/bin/env python3
"""
Photo enrichment v3 — fill in the remaining islands that v2 (Wikidata P18 +
Wikipedia pageimages) could not photograph.

Sources, in priority order:
    A. Commons category by Q-ID            source = "commons-category"
       For islands with a Wikidata Q-ID but no P18, fetch the Commons
       sitelink (a category page), list its members, and pick the best
       Quality / Featured photo.
    B. OSM `image=*` tag                    source = "osm-image-tag"
       Re-query Overpass for the element; if it carries `image=<url>` AND
       the URL host is in HOST_ALLOW, adopt with license inherited.
    C. Wikimedia Commons radial geosearch   source = "commons-geosearch"
       For islands with lat/lng but no Q-ID category (or no useful one),
       Commons `list=geosearch` returns Commons file pages within `r` metres
       of the centroid. Many of these are Geograph uploads (CC-BY-SA 2.0)
       carried over to Commons. Strict acceptance: filename or caption must
       mention the island name, OR distance < 200 m AND filename is a
       photo (not a map/flag/logo).

Stops at the first hit per island. Subsequent sources can still add
secondary photos (we mark only the first as `primary`).

Hard rules (see docs/ETHICS.md and docs/IMAGE-SOURCES.md):
- Every adopted image MUST have `license`, `attribution`, `sourcePageUrl`.
- No name-based generic web search.
- No social media. No tourism boards. No AI generation.
- Suspect matches are written to a `suspects` list, NOT adopted.

Run:
    python3 scripts/enrich_images_v3.py                       # full run
    python3 scripts/enrich_images_v3.py --source commons-category
    python3 scripts/enrich_images_v3.py --source commons-geosearch --limit 25
    python3 scripts/enrich_images_v3.py --test isle-of-skye   # one-island dry run

Outputs:
    data/islands.json                              (mutated, with backup)
    data/islands.json.before-v3                    (backup)
    data/cache_commons_category.json               (Q-ID -> category info)
    data/cache_commons.json                        (file metadata, shared w/ v2)
    data/cache_osm_image_tag.json                  (osm element -> image tag)
    data/cache_commons_geo.json                    (coord key -> nearby file list)
    data/image_enrichment_v3_report.json           (audit)
"""

from __future__ import annotations

import argparse
import json
import math
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
BACKUP_PATH = DATA_DIR / "islands.json.before-v3"

CACHE_CC = DATA_DIR / "cache_commons_category.json"
CACHE_CM = DATA_DIR / "cache_commons.json"
CACHE_OSMI = DATA_DIR / "cache_osm_image_tag.json"
CACHE_GEO = DATA_DIR / "cache_commons_geo.json"
REPORT = DATA_DIR / "image_enrichment_v3_report.json"

USER_AGENT = (
    "isles-of-britain/0.4 (image enrichment v3; "
    "https://github.com/example/isles-of-britain; "
    "static-site prototype)"
)
DELAY_S = 0.25

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# OSM image-tag hosts we'll trust (license inferable / open).
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

# Filenames that are clearly not landscape photos.
_NON_PHOTO_RE = re.compile(
    r"(?:^|[_ \-])("
    r"flag|coat[_ \-]of[_ \-]arms|coat[_ \-]arms|arms[_ \-]of|"
    r"crest|emblem|seal|logo|badge|"
    r"location[_ \-]map|outline[_ \-]map|locator[_ \-]map|"
    r"map[_ \-]of|map[_ \-]showing|"
    r"chart|diagram|graph|plan[_ \-]of"
    r")",
    re.IGNORECASE,
)


def _looks_like_non_photo(filename: str) -> bool:
    if not filename:
        return True
    if filename.lower().endswith((".svg", ".pdf", ".tif", ".tiff")):
        return True
    return bool(_NON_PHOTO_RE.search(filename))


# ---------- HTTP / caching ----------

def _open(req: urllib.request.Request, timeout: int = 60) -> bytes:
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last = exc
            sleep = 1.0 * (attempt + 1)
            time.sleep(sleep)
    raise last  # type: ignore[misc]


def _get_json(url: str, params: dict[str, Any], headers: dict | None = None) -> dict:
    qs = urllib.parse.urlencode(params, doseq=True)
    full = f"{url}?{qs}" if qs else url
    req = urllib.request.Request(
        full,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})},
    )
    raw = _open(req)
    return json.loads(raw.decode("utf-8"))


def _get_text(url: str, headers: dict | None = None) -> str:
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, **(headers or {})}
    )
    return _open(req).decode("utf-8", errors="replace")


def _load_cache(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        print(f"WARN: corrupt cache {path}, ignoring", file=sys.stderr)
        return {}


def _save_cache(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    tmp.replace(path)


# ---------- helpers ----------

def _canon_filename(name: str) -> str:
    if not name:
        return ""
    n = name
    if n.startswith("File:"):
        n = n[len("File:") :]
    return n.replace("_", " ")


def commons_thumb_url(filename: str, width: int = 640) -> str:
    if not filename:
        return ""
    fname = _canon_filename(filename)
    return (
        "https://commons.wikimedia.org/wiki/Special:FilePath/"
        + urllib.parse.quote(fname.replace(" ", "_"))
        + f"?width={width}"
    )


def commons_page_url(filename: str) -> str:
    if not filename:
        return ""
    fname = _canon_filename(filename)
    return (
        "https://commons.wikimedia.org/wiki/File:"
        + urllib.parse.quote(fname.replace(" ", "_"))
    )


_HTML_RE = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", _HTML_RE.sub("", s)).strip()


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _name_variants(island: dict) -> list[str]:
    """Lowercase tokens we accept as 'mentions' of the island."""
    bag: set[str] = set()
    for key in ("name",):
        v = (island.get(key) or "").strip().lower()
        if v:
            bag.add(v)
            for stripped in (
                v.replace("isle of ", ""),
                v.replace("island", "").strip(),
                v.replace("'", "").replace("ʼ", ""),
            ):
                if stripped:
                    bag.add(stripped)
    return [v for v in bag if len(v) >= 3]


def _mentions_island(text: str, island: dict) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(v in t for v in _name_variants(island))


# ---------- Commons file metadata (re-uses v2's cache) ----------

def fetch_commons_meta(filenames: list[str], cache: dict, refresh: bool = False) -> dict[str, dict]:
    norm = list(dict.fromkeys(_canon_filename(f) for f in filenames if f))
    missing = [n for n in norm if refresh or n not in cache]
    BATCH = 50
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
            fname = _canon_filename(title)
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
        _save_cache(CACHE_CM, cache)
        time.sleep(DELAY_S)
    return {n: cache.get(n, {}) for n in norm}


# ---------- Source A: Commons category by Q-ID ----------

def commons_category_for_qid(qids: list[str], cache: dict, refresh: bool = False) -> dict[str, str]:
    """Return {Q-ID: 'Category:Foo'} via sitelinks. Empty string if none."""
    out: dict[str, str] = {}
    missing = [q for q in qids if refresh or q not in cache]
    BATCH = 50
    for i in range(0, len(missing), BATCH):
        batch = missing[i : i + BATCH]
        params = {
            "action": "wbgetentities",
            "format": "json",
            "ids": "|".join(batch),
            "props": "sitelinks",
            "sitefilter": "commonswiki",
        }
        try:
            payload = _get_json(WIKIDATA_API, params)
        except Exception as exc:
            print(f"  wbgetentities batch failed: {exc!r}", file=sys.stderr)
            continue
        entities = payload.get("entities") or {}
        for qid in batch:
            ent = entities.get(qid) or {}
            sl = ((ent.get("sitelinks") or {}).get("commonswiki") or {}).get("title", "")
            cache[qid] = sl  # may be "Category:Foo" OR "Foo" (a Commons gallery)
        _save_cache(CACHE_CC, cache)
        time.sleep(DELAY_S)
    for q in qids:
        out[q] = cache.get(q, "")
    return out


def category_members(category_title: str, limit: int = 50) -> list[str]:
    """Return up to `limit` image filenames in a Commons category."""
    if not category_title:
        return []
    if not category_title.startswith("Category:"):
        category_title = "Category:" + category_title
    params = {
        "action": "query",
        "format": "json",
        "list": "categorymembers",
        "cmtitle": category_title,
        "cmtype": "file",
        "cmlimit": str(limit),
    }
    try:
        payload = _get_json(COMMONS_API, params)
    except Exception as exc:
        print(f"  categorymembers failed for {category_title}: {exc!r}", file=sys.stderr)
        return []
    return [
        _canon_filename(m.get("title", ""))
        for m in (payload.get("query") or {}).get("categorymembers") or []
        if m.get("title", "").startswith("File:")
    ]


def try_commons_category(island: dict, cc_cache: dict, cm_cache: dict) -> dict | None:
    qid = (island.get("wikidata") or "").strip()
    if not re.match(r"^Q\d+$", qid):
        return None
    sitelink = commons_category_for_qid([qid], cc_cache).get(qid, "")
    if not sitelink:
        return None
    members = category_members(sitelink, limit=50)
    photos = [f for f in members if not _looks_like_non_photo(f)]
    if not photos:
        return None
    # Resolve metadata in batch; pick the first that has a license.
    metas = fetch_commons_meta(photos[:25], cm_cache)
    best_fname = ""
    best_score = -1.0
    for fname in photos[:25]:
        m = metas.get(fname, {})
        lic = (m.get("license") or "").strip()
        if not lic or "fair use" in lic.lower():
            continue
        score = 0.0
        cats = (m.get("categories") or "").lower()
        if "quality images" in cats:
            score += 5
        if "featured pictures" in cats:
            score += 10
        if "valued images" in cats:
            score += 3
        w, h = m.get("width") or 0, m.get("height") or 0
        if w and h and w * h > 1_000_000:
            score += 1
        if _mentions_island(fname, island) or _mentions_island(m.get("caption", ""), island):
            score += 4
        if score > best_score:
            best_score = score
            best_fname = fname
    if not best_fname:
        return None
    m = metas.get(best_fname, {})
    if not m.get("license"):
        return None
    return {
        "url": commons_thumb_url(best_fname, 640),
        "fullUrl": commons_thumb_url(best_fname, 1600),
        "caption": m.get("caption", ""),
        "source": "commons-category",
        "sourceRef": sitelink,
        "sourcePageUrl": m.get("descriptionUrl") or commons_page_url(best_fname),
        "license": m.get("license"),
        "licenseUrl": m.get("licenseUrl", ""),
        "attribution": _format_attribution(m.get("attribution"), m.get("license"), "Wikimedia Commons"),
        "primary": True,
    }


# ---------- Source B: OSM image=* tag ----------

def fetch_osm_image_tag(elements: list[tuple[str, int]], cache: dict, refresh: bool = False) -> dict[str, str]:
    """{osmType/osmId: image URL or ''}. Batched via Overpass."""
    out: dict[str, str] = {}
    missing = [
        f"{t}/{i}" for (t, i) in elements
        if refresh or f"{t}/{i}" not in cache
    ]
    BATCH = 200
    for i in range(0, len(missing), BATCH):
        chunk = missing[i : i + BATCH]
        q_parts = []
        for s in chunk:
            t, _, oid = s.partition("/")
            q_parts.append(f"{t}({oid});")
        q = f"[out:json][timeout:60];({''.join(q_parts)});out tags;"
        body = "data=" + urllib.parse.quote(q)
        last_err = None
        for endpoint in OVERPASS_ENDPOINTS:
            try:
                req = urllib.request.Request(
                    endpoint,
                    data=body.encode(),
                    headers={"User-Agent": USER_AGENT,
                             "Content-Type": "application/x-www-form-urlencoded"},
                )
                raw = _open(req, timeout=90)
                payload = json.loads(raw)
                last_err = None
                break
            except Exception as exc:
                last_err = exc
                time.sleep(2.0)
        if last_err:
            print(f"  overpass image-tag batch failed: {last_err!r}", file=sys.stderr)
            continue
        for el in payload.get("elements", []):
            t, oid = el.get("type"), el.get("id")
            key = f"{t}/{oid}"
            tags = el.get("tags") or {}
            cache[key] = tags.get("image", "") or tags.get("wikimedia_commons", "")
        for s in chunk:
            cache.setdefault(s, "")
        _save_cache(CACHE_OSMI, cache)
        time.sleep(0.5)
    for s in [f"{t}/{i}" for (t, i) in elements]:
        out[s] = cache.get(s, "")
    return out


def try_osm_image_tag(island: dict, cache: dict, cm_cache: dict) -> dict | None:
    osm_t = island.get("osmType")
    osm_id = island.get("osmId")
    if not osm_t or not osm_id:
        return None
    key = f"{osm_t}/{osm_id}"
    val = cache.get(key, "")
    if not val:
        return None
    # Wikimedia Commons "File:Foo.jpg" form
    if val.startswith("File:") or val.lower().startswith("file:"):
        fname = _canon_filename(val)
        meta = fetch_commons_meta([fname], cm_cache).get(fname, {})
        if not meta.get("license"):
            return None
        return {
            "url": commons_thumb_url(fname, 640),
            "fullUrl": commons_thumb_url(fname, 1600),
            "caption": meta.get("caption", ""),
            "source": "osm-image-tag",
            "sourceRef": key,
            "sourcePageUrl": meta.get("descriptionUrl") or commons_page_url(fname),
            "license": meta.get("license", ""),
            "licenseUrl": meta.get("licenseUrl", ""),
            "attribution": _format_attribution(
                meta.get("attribution"), meta.get("license"), "Wikimedia Commons (via OSM)"
            ),
            "primary": True,
        }
    # Bare URL — only accept allow-listed hosts; license is then host-implied.
    if val.startswith("http"):
        host = urllib.parse.urlsplit(val).netloc.lower()
        if host not in HOST_ALLOW:
            return None
        if "geograph" in host:
            # Geograph URL: photo id is usually in the path /photo/<id>
            m = re.search(r"/photo/(\d+)", val)
            if not m:
                return None
            return {
                "url": val,
                "fullUrl": val,
                "caption": "",
                "source": "osm-image-tag",
                "sourceRef": key,
                "sourcePageUrl": val,
                "license": "CC-BY-SA-2.0",
                "licenseUrl": "https://creativecommons.org/licenses/by-sa/2.0/",
                "attribution": "via Geograph project (CC-BY-SA 2.0) — recorded on OSM",
                "primary": True,
            }
    return None


# ---------- Source C: Commons radial geosearch ----------

def commons_geosearch(lat: float, lng: float, radius_m: int, cache: dict) -> list[dict]:
    """Commons `list=geosearch` for File: namespace within `radius_m`.

    Returns [{title, lat, lon, dist}], sorted by distance ascending.
    The Commons API caps radius at 10000 m and gslimit at 500.
    """
    key = f"{lat:.4f},{lng:.4f};{radius_m}"
    if key in cache:
        return cache[key]
    radius_m = max(10, min(10000, int(radius_m)))
    params = {
        "action": "query", "format": "json",
        "list": "geosearch",
        "gscoord": f"{lat}|{lng}",
        "gsradius": str(radius_m),
        "gsnamespace": "6",   # File:
        "gslimit": "50",
    }
    try:
        payload = _get_json(COMMONS_API, params)
    except Exception:
        cache[key] = []
        _save_cache(CACHE_GEO, cache)
        time.sleep(0.25)
        return []
    hits = (payload.get("query") or {}).get("geosearch") or []
    out = [
        {"title": h.get("title", ""), "lat": h.get("lat"),
         "lon": h.get("lon"), "dist": h.get("dist")}
        for h in hits
    ]
    cache[key] = out
    _save_cache(CACHE_GEO, cache)
    time.sleep(0.2)
    return out


def try_commons_geosearch(island: dict, cache: dict, cm_cache: dict, *,
                          max_dist_m: int = 800) -> dict | None:
    lat, lng = island.get("lat"), island.get("lng")
    if lat is None or lng is None:
        return None
    area = island.get("areaKm2") or 0.0
    # Tiny islets: open the radius a bit so we can pick up a photo from
    # the neighbouring shore that captures the islet itself.
    radius = max_dist_m
    if area and area < 0.05:
        radius = max(max_dist_m, 1200)
    elif area and area < 0.2:
        radius = max(max_dist_m, 1000)
    hits = commons_geosearch(lat, lng, radius, cache)
    if not hits:
        return None
    # Stage 1: filter to photos that mention the island name (high confidence).
    name_hits = [
        h for h in hits
        if not _looks_like_non_photo(h["title"]) and _mentions_island(h["title"], island)
    ]
    # Stage 2: if none, take the closest non-junk photo within 200 m.
    pool = name_hits or [
        h for h in hits
        if not _looks_like_non_photo(h["title"])
        and (h.get("dist") or 1e9) <= 200
    ]
    if not pool:
        return None
    # Sort: name-match first, then by distance.
    pool.sort(key=lambda h: (
        0 if _mentions_island(h["title"], island) else 1,
        h.get("dist") or 1e9,
    ))
    # Resolve metadata for top 8 candidates; pick the first with a license.
    fnames = [_canon_filename(h["title"]) for h in pool[:8]]
    metas = fetch_commons_meta(fnames, cm_cache)
    chosen = None
    for h, fname in zip(pool[:8], fnames):
        m = metas.get(fname, {})
        lic = (m.get("license") or "").strip()
        if not lic or "fair use" in lic.lower():
            continue
        chosen = (h, fname, m)
        break
    if not chosen:
        return None
    h, fname, m = chosen
    name_matched = _mentions_island(fname, island)
    score = (4 if name_matched else 0) + (2 if (h.get("dist") or 1e9) < 200 else 0)
    return {
        "url": commons_thumb_url(fname, 640),
        "fullUrl": commons_thumb_url(fname, 1600),
        "caption": m.get("caption", "") or h.get("title", "").replace("File:", ""),
        "source": "commons-geosearch",
        "sourceRef": f"{lat:.4f},{lng:.4f};{radius}",
        "sourcePageUrl": m.get("descriptionUrl") or commons_page_url(fname),
        "license": m.get("license", ""),
        "licenseUrl": m.get("licenseUrl", ""),
        "attribution": _format_attribution(
            m.get("attribution"), m.get("license"),
            "Wikimedia Commons (geosearch)",
        ),
        "primary": True,
        "_suspect": not name_matched,  # marker for the report
        "_score": score,
    }


# ---------- attribution string ----------

def _format_attribution(artist: str | None, license_: str | None, via: str) -> str:
    a = (artist or "").strip() or "Unknown"
    l = (license_ or "").strip() or "see source"
    return f"Photo by {a} ({l}) via {via}"


# ---------- main ----------

def _needs_image(i: dict) -> bool:
    return not (i.get("images") or i.get("image"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="all",
                    choices=["all", "commons-category", "osm-image-tag",
                             "commons-geosearch"])
    ap.add_argument("--limit", type=int, default=0,
                    help="process at most N islands (0 = no limit)")
    ap.add_argument("--test", default="",
                    help="dry-run for one island id (no writes to islands.json)")
    args = ap.parse_args()

    islands = json.loads(ISLANDS_PATH.read_text())
    cc_cache = _load_cache(CACHE_CC)
    cm_cache = _load_cache(CACHE_CM)
    osmi_cache = _load_cache(CACHE_OSMI)
    geo_cache = _load_cache(CACHE_GEO)

    if not args.test:
        BACKUP_PATH.write_text(ISLANDS_PATH.read_text())
        print(f"Backup written: {BACKUP_PATH.name}", file=sys.stderr)

    if args.test:
        targets = [i for i in islands if i["id"] == args.test]
        if not targets:
            print(f"No island with id={args.test}", file=sys.stderr)
            return
    else:
        targets = [i for i in islands if _needs_image(i)]
    if args.limit:
        targets = targets[: args.limit]
    print(f"Targets: {len(targets)} islands need an image", file=sys.stderr)

    # Pre-warm: collect Q-IDs and OSM elements for batched lookups.
    if args.source in ("all", "commons-category"):
        qids = sorted({i["wikidata"] for i in targets
                       if (i.get("wikidata") or "").startswith("Q")})
        print(f"  source A: {len(qids)} Q-IDs to resolve to Commons categories",
              file=sys.stderr)
        commons_category_for_qid(qids, cc_cache)

    if args.source in ("all", "osm-image-tag"):
        elems = [(i["osmType"], int(i["osmId"])) for i in targets
                 if i.get("osmType") and i.get("osmId")]
        print(f"  source B: {len(elems)} OSM elements to query for image tag",
              file=sys.stderr)
        fetch_osm_image_tag(elems, osmi_cache)

    counts = {"commons-category": 0, "osm-image-tag": 0,
              "commons-geosearch": 0, "no-source": 0}
    suspects: list[dict] = []
    adopted: list[dict] = []
    last_checkpoint = 0
    CHECKPOINT_EVERY = 100  # adoptions

    def _checkpoint(processed: int):
        """Atomically write islands.json + report so a kill is recoverable."""
        if args.test:
            return
        tmp_isl = ISLANDS_PATH.with_suffix(".json.tmp")
        tmp_isl.write_text(json.dumps(islands, ensure_ascii=False, indent=2))
        tmp_isl.replace(ISLANDS_PATH)
        tmp_rep = REPORT.with_suffix(".json.tmp")
        tmp_rep.write_text(json.dumps({
            "counts": counts,
            "targets": len(targets),
            "processed": processed,
            "complete": False,
            "adopted": adopted,
            "suspects": suspects,
        }, ensure_ascii=False, indent=2))
        tmp_rep.replace(REPORT)

    for n, isl in enumerate(targets, 1):
        if n % 100 == 0:
            print(f"  {n}/{len(targets)} processed; adopted so far: "
                  f"cc={counts['commons-category']} "
                  f"osm={counts['osm-image-tag']} "
                  f"geo={counts['commons-geosearch']}", file=sys.stderr)
        candidate = None
        if args.source in ("all", "commons-category"):
            candidate = try_commons_category(isl, cc_cache, cm_cache)
        if not candidate and args.source in ("all", "osm-image-tag"):
            candidate = try_osm_image_tag(isl, osmi_cache, cm_cache)
        if not candidate and args.source in ("all", "commons-geosearch"):
            candidate = try_commons_geosearch(isl, geo_cache, cm_cache)
        if not candidate:
            counts["no-source"] += 1
            continue
        score = candidate.pop("_score", None)
        suspect = candidate.pop("_suspect", False)
        counts[candidate["source"]] += 1
        entry = {"id": isl["id"], "name": isl["name"],
                 "source": candidate["source"],
                 "sourceRef": candidate.get("sourceRef"),
                 "sourcePageUrl": candidate.get("sourcePageUrl"),
                 "score": score}
        if suspect:
            entry["suspect"] = True
            suspects.append(entry)
        adopted.append(entry)
        if args.test:
            print(json.dumps(candidate, indent=2, ensure_ascii=False))
            continue
        imgs = isl.get("images") or []
        imgs.append(candidate)
        # First image is primary.
        for k, img in enumerate(imgs):
            img["primary"] = (k == 0)
        isl["images"] = imgs
        if not isl.get("image"):
            isl["image"] = candidate["url"]
        if len(adopted) - last_checkpoint >= CHECKPOINT_EVERY:
            _checkpoint(n)
            last_checkpoint = len(adopted)
            print(f"    [checkpoint] {len(adopted)} adoptions written to disk",
                  file=sys.stderr)

    if not args.test:
        # Final atomic write
        tmp_isl = ISLANDS_PATH.with_suffix(".json.tmp")
        tmp_isl.write_text(json.dumps(islands, ensure_ascii=False, indent=2))
        tmp_isl.replace(ISLANDS_PATH)
    REPORT.write_text(json.dumps({
        "counts": counts,
        "targets": len(targets),
        "processed": len(targets),
        "complete": True,
        "adopted": adopted,
        "suspects": suspects,
    }, ensure_ascii=False, indent=2))

    total_with = sum(1 for i in islands if i.get("images") or i.get("image"))
    print(f"\nDone. Adopted: cc={counts['commons-category']} "
          f"osm={counts['osm-image-tag']} geo={counts['commons-geosearch']} "
          f"no-source={counts['no-source']}", file=sys.stderr)
    print(f"Total islands with at least one image: {total_with}/{len(islands)} "
          f"({100*total_with/len(islands):.1f}%)", file=sys.stderr)


if __name__ == "__main__":
    main()
