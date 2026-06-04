#!/usr/bin/env python3
"""Historical / open photos: Internet Archive, NLS, British Library Flickr, Wellcome.

Targets named atlas islands (``islands_index.json``) still lacking ``images[]``.
Strict licence gate: public domain or permissive CC only (no NC/ND, no ARR).
Prefers geotagged hits and caption/title name matches (v5 ``_mentions``).

Sources (in probe order for each island):
  1. Internet Archive advanced search — ``mediatype:image``, licence filter
  2. National Library of Scotland — digital gallery API probe; Flickr Commons feed
  3. British Library Flickr Commons — institution feed + optional API text search
  4. Wellcome Collection — ``/catalogue/v2/images`` (open + PDM/CC)

Run::

    python3 scripts/enrich_images_archive_nls.py --named-only --limit 300
    python3 scripts/enrich_images_archive_nls.py --dry-run --test iona

Outputs (staging only by default)::

    data/staging/adoptions/archive-nls.json
    data/cache_archive_nls.json
    data/image_enrichment_archive_nls_report.json

Optional ``FLICKR_API_KEY`` in ``.env.local`` enables Flickr REST text search
scoped to BL / NLS Commons accounts (licence id 7).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
STAGING = DATA / "staging" / "adoptions" / "archive-nls.json"
CACHE = DATA / "cache_archive_nls.json"
REPORT = DATA / "image_enrichment_archive_nls_report.json"
ENV_LOCAL = ROOT / ".env.local"

IA_SEARCH = "https://archive.org/advancedsearch.php"
IA_METADATA = "https://archive.org/metadata/"
WELLCOME_IMAGES = "https://api.wellcomecollection.org/catalogue/v2/images"
WELLCOME_IMAGE = "https://api.wellcomecollection.org/catalogue/v2/images/"
FLICKR_REST = "https://www.flickr.com/services/rest/"
FLICKR_FEED = "https://www.flickr.com/services/feeds/photos_public.gne"

USER_AGENT = "isles-of-britain/0.1 archive-nls-enrichment"
DEFAULT_DELAY_S = 1.5
MAX_LIMIT = 300
CONFIDENCE = "medium"
GEO_MAX_KM = 15.0
GEO_MAX_KM_GENERIC = 5.0
IA_ROWS = 12
WELLCOME_PAGE_SIZE = 15
FLICKR_PER_PAGE = 20

# Flickr Commons institution NSIDs (verified 2026-06).
FLICKR_BL_NSID = "12403504@N02"
FLICKR_NLS_NSID = "14456531@N07"
FLICKR_COMMONS_LICENSE = "7"

NLS_GALLERY_PROBE_URLS = (
    "https://digital.nls.uk/discover/search",
    "https://search.nls.uk/solr/select",
)

_GENERIC_NAME_RE = re.compile(
    r"^(?:the\s+)?"
    r"(?:green|black|white|red|blue|brown|grey|gray|great|little|big|small|"
    r"north|south|east|west|middle|inner|outer|high|low|long|short|round|flat|"
    r"rock|stone|sand|shell|reef|holm|skerry|inch|eilean|ynys|inis|holy|saint|"
    r"st\.?)\s+"
    r"(?:island|isle|islets?|islet)$",
    re.IGNORECASE,
)
_NON_PHOTO_TITLE_RE = re.compile(
    r"(?:^|[_ \-\(\[])"
    r"(?:flag|coat[_ \-]of[_ \-]arms|logo|map|diagram|chart|icon|badge|"
    r"illustration|drawing|cartoon|clipart|vector|svg|portrait|selfie|"
    r"cosplay|wedding|party|concert|festival)"
    r"(?:$|[_ \-\)\]])",
    re.IGNORECASE,
)
_CC_URL_RE = re.compile(
    r"creativecommons\.org/licenses/([a-z\-]+)/(\d+\.?\d*)",
    re.IGNORECASE,
)
_CC0_URL_RE = re.compile(r"creativecommons\.org/publicdomain/zero", re.IGNORECASE)
_PDM_URL_RE = re.compile(
    r"creativecommons\.org/(?:publicdomain/mark|share-your-work/public-domain/pdm)",
    re.IGNORECASE,
)
_EXCLUDED_RIGHTS_RE = re.compile(
    r"(?:by-nc|by-nd|nc-nd|noncommercial|non-commercial|all-rights-reserved|"
    r"copyrighted|in-copyright|permission\s+required)",
    re.IGNORECASE,
)
_FLICKR_PHOTO_ID_RE = re.compile(r"flickr\.com/photos/[^/]+/(\d+)")
_IIIF_ID_RE = re.compile(r"/image/([^/]+)/")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from enrich_images_v5 import (  # noqa: E402
    _get_json,
    _haversine_km,
    _load,
    _load_named_index_ids,
    _mentions,
    _name_variants,
    _save,
    _strip_html,
)


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = val


def _is_generic_island_name(name: str) -> bool:
    raw = (name or "").strip()
    if not raw:
        return True
    low = raw.lower()
    if _GENERIC_NAME_RE.match(low):
        return True
    tokens = re.sub(r"[^\w\s'-]", " ", low).split()
    if len(tokens) == 2 and tokens[-1] in ("island", "isle", "islets", "islet"):
        return True
    if len(low) <= 8 and " " not in low:
        return True
    return False


def _island_lon(island: dict) -> float | None:
    lng = island.get("lng")
    if lng is None:
        lng = island.get("lon")
    if isinstance(lng, (int, float)):
        return float(lng)
    return None


def _geo_max_km(island: dict) -> float:
    return (
        GEO_MAX_KM_GENERIC
        if _is_generic_island_name(island.get("name") or "")
        else GEO_MAX_KM
    )


def _nation_context(island: dict) -> str:
    nation = (island.get("nation") or "").strip().lower()
    return {
        "scotland": "Scotland",
        "wales": "Wales",
        "ireland": "Ireland",
        "northern ireland": "Northern Ireland",
        "england": "England",
        "isle of man": "Isle of Man",
        "crown dependency": "Channel Islands",
    }.get(nation, "")


def _title_mentions_nation(title: str, island: dict) -> bool:
    """Reject Wellcome homonyms (e.g. Mount Ararat vs island Ararat)."""
    ctx = _nation_context(island)
    if not ctx:
        return True
    low = (title or "").lower()
    if ctx.lower() in low:
        return True
    nation = (island.get("nation") or "").strip().lower()
    aliases = {
        "scotland": ("scottish", "hebrides", "highlands", "orkney", "shetland"),
        "wales": ("welsh", "cymru", "anglesey", "ynys"),
        "ireland": ("irish", "éire", "eire"),
        "northern ireland": ("ulster", "northern irish"),
        "england": ("english",),
    }
    return any(a in low for a in aliases.get(nation, ()))


def _search_query(island: dict) -> str:
    name = (island.get("name") or "").strip()
    ctx = _nation_context(island)
    return f"{name} {ctx}".strip() if ctx else name


def _search_query_variants(island: dict) -> list[str]:
    """Primary query includes nation; Wellcome often needs name-only fallback."""
    name = (island.get("name") or "").strip()
    if not name:
        return []
    full = _search_query(island)
    out = [full] if full else []
    if name.lower() != full.lower() and name not in out:
        out.append(name)
    return out


def _looks_like_non_photo(title: str) -> bool:
    if not title:
        return True
    return bool(_NON_PHOTO_TITLE_RE.search(title))


def _save_cache(cache: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(cache, ensure_ascii=False, separators=(",", ":"))
    tmp = CACHE.with_suffix(CACHE.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, CACHE)


def _cache_bucket(cache: dict, source: str) -> dict:
    bucket = cache.setdefault(source, {})
    if not isinstance(bucket, dict):
        bucket = {}
        cache[source] = bucket
    return bucket


def _license_from_rights_urls(urls: list[str]) -> tuple[str, str] | None:
    if not urls:
        return None
    joined = " ".join(urls)
    if _EXCLUDED_RIGHTS_RE.search(joined):
        return None
    for u in urls:
        low = u.lower()
        if _CC0_URL_RE.search(low):
            return "CC0-1.0", "https://creativecommons.org/publicdomain/zero/1.0/"
        if _PDM_URL_RE.search(low):
            return "PDM", "https://creativecommons.org/publicdomain/mark/1.0/"
        m = _CC_URL_RE.search(u)
        if m:
            kind, ver = m.group(1).lower(), m.group(2)
            if "nc" in kind or "nd" in kind:
                continue
            if kind == "by":
                return f"CC-BY-{ver}", u
            if kind == "by-sa":
                return f"CC-BY-SA-{ver}", u
    if any(
        x in joined.lower()
        for x in ("publicdomain", "pdmark", "no known copyright")
    ):
        return "PDM", urls[0]
    return None


def _wellcome_license_label(lic: dict | None) -> str | None:
    if not lic or not isinstance(lic, dict):
        return None
    lid = (lic.get("id") or "").strip().lower()
    mapping = {
        "pdm": "PDM",
        "cc-by": "CC-BY-4.0",
        "cc-by-sa": "CC-BY-SA-4.0",
        "cc0": "CC0-1.0",
        "cc-by-4.0": "CC-BY-4.0",
        "cc-by-sa-4.0": "CC-BY-SA-4.0",
    }
    if lid in mapping:
        return mapping[lid]
    if "nc" in lid or "nd" in lid:
        return None
    return None


def _wellcome_open(loc: dict) -> bool:
    for cond in loc.get("accessConditions") or []:
        if not isinstance(cond, dict):
            continue
        status = (cond.get("status") or {}).get("id", "")
        if str(status).lower() == "open":
            return True
    return False


# ---------- Internet Archive ----------

def _ia_license_ok(licenseurl: str) -> tuple[str, str] | None:
    url = (licenseurl or "").strip()
    if not url:
        return None
    return _license_from_rights_urls([url])


def fetch_ia_search(
    island: dict,
    cache: dict,
    delay_s: float,
) -> list[dict]:
    bucket = _cache_bucket(cache, "internet-archive")
    iid = island.get("id") or ""
    if iid in bucket:
        entry = bucket[iid]
        if isinstance(entry, dict) and isinstance(entry.get("docs"), list):
            return entry["docs"]

    q = f"{_search_query(island)} AND mediatype:image"
    params: dict[str, Any] = {
        "q": q,
        "fl[]": ["identifier", "title", "licenseurl"],
        "rows": IA_ROWS,
        "output": "json",
        "page": 1,
    }
    try:
        payload = _get_json(IA_SEARCH, params)
    except Exception as exc:
        print(f"  IA search failed for {iid}: {exc!r}", file=sys.stderr)
        bucket[iid] = {"q": q, "error": repr(exc), "docs": []}
        _save_cache(cache)
        time.sleep(delay_s)
        return []

    docs = payload.get("response", {}).get("docs") or []
    bucket[iid] = {
        "q": q,
        "fetched": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "numFound": payload.get("response", {}).get("numFound"),
        "docs": docs,
    }
    _save_cache(cache)
    time.sleep(delay_s)
    return docs


def fetch_ia_metadata(identifier: str, cache: dict, delay_s: float) -> dict:
    bucket = _cache_bucket(cache, "internet-archive-meta")
    if identifier in bucket:
        return bucket[identifier] if isinstance(bucket[identifier], dict) else {}

    try:
        payload = _get_json(f"{IA_METADATA}{identifier}", {})
    except Exception as exc:
        bucket[identifier] = {"error": repr(exc)}
        _save_cache(cache)
        time.sleep(delay_s * 0.5)
        return {}

    bucket[identifier] = payload
    _save_cache(cache)
    time.sleep(delay_s * 0.5)
    return payload


def _ia_display_url(identifier: str, meta: dict) -> str:
    for f in meta.get("files") or []:
        if not isinstance(f, dict):
            continue
        name = (f.get("name") or "").strip()
        fmt = (f.get("format") or "").strip()
        if not name or "thumb" in name.lower():
            continue
        if fmt in ("JPEG", "PNG", "Item Image", "Image"):
            return f"https://archive.org/download/{identifier}/{urllib.parse.quote(name)}"
    return f"https://archive.org/services/img/{identifier}"


def build_image_record_from_ia(
    doc: dict,
    meta: dict,
) -> dict | None:
    identifier = (doc.get("identifier") or "").strip()
    if not identifier:
        return None
    title = (doc.get("title") or meta.get("metadata", {}).get("title") or "").strip()
    if _looks_like_non_photo(title):
        return None

    lic_url = (
        (doc.get("licenseurl") or "").strip()
        or (meta.get("metadata") or {}).get("licenseurl") or ""
    ).strip()
    lic = _ia_license_ok(lic_url)
    if not lic:
        return None
    license_label, license_url = lic

    url = _ia_display_url(identifier, meta)
    page = f"https://archive.org/details/{identifier}"
    creator = (meta.get("metadata") or {}).get("creator") or ""
    creator = creator if isinstance(creator, str) else ", ".join(creator) if creator else ""
    creator = (creator or "Internet Archive contributor").strip()

    return {
        "url": url,
        "source": "internet-archive",
        "sourceRef": identifier,
        "sourcePageUrl": page,
        "license": license_label,
        "licenseUrl": license_url,
        "attribution": f"\"{title[:120]}\" by {creator} ({license_label}) via Internet Archive",
        "caption": title[:200],
    }


# ---------- NLS digital gallery probe ----------

def probe_nls_gallery_api(cache: dict) -> dict[str, Any]:
    bucket = _cache_bucket(cache, "nls-gallery-probe")
    if bucket.get("probed"):
        return bucket

    results: list[dict[str, str]] = []
    for base in NLS_GALLERY_PROBE_URLS:
        try:
            params = {"q": "Iona", "query": "Iona", "rows": 1, "wt": "json", "format": "json"}
            req = urllib.request.Request(
                f"{base}?{urllib.parse.urlencode(params)}",
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                body = resp.read(200)
            results.append({"url": base, "status": "ok", "sample": body[:120].decode("utf-8", "replace")})
        except Exception as exc:
            results.append({"url": base, "status": "error", "error": repr(exc)})

    bucket.update({
        "probed": True,
        "fetched": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "accessible": any(r.get("status") == "ok" for r in results),
        "results": results,
    })
    _save_cache(cache)
    return bucket


def fetch_nls_gallery(island: dict, cache: dict, delay_s: float) -> list[dict]:
    """No public JSON search API — returns [] after one-time probe."""
    probe = probe_nls_gallery_api(cache)
    if not probe.get("accessible"):
        return []
    return []


# ---------- Flickr Commons (BL + NLS) ----------

def _flickr_rest(method: str, api_key: str, **kwargs: Any) -> dict:
    params: dict[str, Any] = {
        "method": method,
        "api_key": api_key,
        "format": "json",
        "nojsoncallback": 1,
    }
    params.update(kwargs)
    data = _get_json(FLICKR_REST, params)
    if data.get("stat") != "ok":
        raise RuntimeError(data.get("message") or data)
    return data


def _parse_feed_photo_id(link: str) -> str:
    m = _FLICKR_PHOTO_ID_RE.search(link or "")
    return m.group(1) if m else ""


def _license_from_feed_description(desc_html: str) -> tuple[str, str] | None:
    if not desc_html:
        return ("No known copyright restrictions", "https://www.flickr.com/commons/usage/")
    lic = _license_from_rights_urls(re.findall(r'https?://[^\s"<>]+', desc_html))
    if lic:
        return lic
    if "flickr.com/commons" in desc_html.lower() or "no known copyright" in desc_html.lower():
        return "No known copyright restrictions", "https://www.flickr.com/commons/usage/"
    return None


def fetch_flickr_institution_feed(
    island: dict,
    institution: str,
    nsid: str,
    cache: dict,
    delay_s: float,
) -> list[dict]:
    bucket = _cache_bucket(cache, f"flickr-feed-{institution}")
    iid = island.get("id") or ""
    if iid in bucket:
        entry = bucket[iid]
        if isinstance(entry, dict) and isinstance(entry.get("photos"), list):
            return entry["photos"]

    name = (island.get("name") or "").strip()
    safe = re.sub(r"[^\w]+", "", name.lower())
    if len(safe) < 4:
        bucket[iid] = {"photos": []}
        _save_cache(cache)
        return []

    ctx = _nation_context(island).lower().replace(" ", "")
    nation_tag = ctx or "scotland"
    tag_sets = [
        f"{safe},{nation_tag}",
        f"{safe},island",
        safe,
    ]

    photos: list[dict] = []
    seen: set[str] = set()
    for tags in tag_sets:
        params = {
            "id": nsid,
            "tags": tags,
            "tagmode": "all",
            "format": "json",
            "nojsoncallback": 1,
        }
        try:
            payload = _get_json(FLICKR_FEED, params)
        except Exception as exc:
            print(f"  flickr feed {institution} {tags}: {exc!r}", file=sys.stderr)
            continue
        for item in payload.get("items") or []:
            link = (item.get("link") or "").strip()
            pid = _parse_feed_photo_id(link)
            if not pid or pid in seen:
                continue
            title = (item.get("title") or "").strip()
            desc = item.get("description") or ""
            lic = _license_from_feed_description(desc)
            if not lic:
                continue
            media = item.get("media") or {}
            url_m = media.get("m") if isinstance(media, dict) else ""
            url = url_m.replace("_m.", "_b.") if url_m else ""
            photos.append({
                "id": pid,
                "title": title,
                "description": desc,
                "link": link,
                "url_m": url,
                "license": FLICKR_COMMONS_LICENSE,
                "institution": institution,
            })
            seen.add(pid)
        time.sleep(delay_s * 0.4)

    bucket[iid] = {
        "nsid": nsid,
        "tags_tried": tag_sets,
        "fetched": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "photos": photos,
    }
    _save_cache(cache)
    time.sleep(delay_s)
    return photos


def fetch_flickr_institution_api(
    island: dict,
    institution: str,
    nsid: str,
    api_key: str,
    cache: dict,
    delay_s: float,
) -> list[dict]:
    bucket = _cache_bucket(cache, f"flickr-api-{institution}")
    iid = island.get("id") or ""
    if iid in bucket:
        entry = bucket[iid]
        if isinstance(entry, dict) and isinstance(entry.get("photos"), list):
            return entry["photos"]

    text = _search_query(island)
    try:
        data = _flickr_rest(
            "flickr.photos.search",
            api_key,
            user_id=nsid,
            text=text,
            license=FLICKR_COMMONS_LICENSE,
            content_type=1,
            media="photos",
            per_page=FLICKR_PER_PAGE,
            extras="url_m,url_l,license,owner_name,geo,description,tags",
        )
    except Exception as exc:
        print(f"  flickr API {institution} for {iid}: {exc!r}", file=sys.stderr)
        bucket[iid] = {"text": text, "error": repr(exc), "photos": []}
        _save_cache(cache)
        time.sleep(delay_s)
        return []

    photos = data.get("photos", {}).get("photo") or []
    if isinstance(photos, dict):
        photos = [photos]
    for p in photos:
        if isinstance(p, dict):
            p["institution"] = institution
    bucket[iid] = {
        "text": text,
        "fetched": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "photos": photos,
    }
    _save_cache(cache)
    time.sleep(delay_s)
    return photos


def build_image_record_from_flickr_commons(
    photo: dict,
    *,
    institution: str,
) -> dict | None:
    photo_id = str(photo.get("id") or "").strip()
    if not photo_id:
        return None
    title = (photo.get("title") or "").strip()
    if _looks_like_non_photo(title):
        return None

    license_label = "No known copyright restrictions"
    license_url = "https://www.flickr.com/commons/usage/"
    holder = {
        "british-library": "The British Library",
        "nls": "National Library of Scotland",
    }.get(institution, institution)

    url = (photo.get("url_l") or photo.get("url_m") or "").strip()
    if not url:
        url = (photo.get("url_m") or "").replace("_m.", "_b.")
    if not url:
        media = photo.get("media", {})
        if isinstance(media, dict):
            url = (media.get("m") or "").replace("_m.", "_b.")
    if not url:
        return None

    page = (photo.get("link") or "").strip()
    if not page:
        owner = (photo.get("owner") or "").strip()
        page = (
            f"https://www.flickr.com/photos/{owner}/{photo_id}"
            if owner
            else f"https://www.flickr.com/photo.gne?id={photo_id}"
        )

    owner_name = (photo.get("ownername") or holder).strip()
    desc = _strip_html(photo.get("description", "") or "")

    return {
        "url": url,
        "source": "flickr-commons",
        "sourceRef": f"{institution}:{photo_id}",
        "sourcePageUrl": page,
        "license": license_label,
        "licenseUrl": license_url,
        "attribution": (
            f"\"{title or photo_id}\" — {holder} via Flickr Commons "
            f"({license_label})"
        ),
        "caption": title or desc[:120],
    }


# ---------- Wellcome Collection ----------

def fetch_wellcome_search(
    island: dict,
    cache: dict,
    delay_s: float,
) -> list[dict]:
    bucket = _cache_bucket(cache, "wellcome")
    iid = island.get("id") or ""
    if iid in bucket:
        entry = bucket[iid]
        if isinstance(entry, dict) and isinstance(entry.get("results"), list):
            return entry["results"]

    queries = _search_query_variants(island)
    results: list[dict] = []
    used_query = ""
    last_error = ""
    for query in queries:
        params = {"query": query, "pageSize": WELLCOME_PAGE_SIZE}
        try:
            payload = _get_json(WELLCOME_IMAGES, params)
        except Exception as exc:
            last_error = repr(exc)
            print(f"  Wellcome search failed for {iid} ({query}): {exc!r}", file=sys.stderr)
            continue
        results = payload.get("results") or []
        used_query = query
        if results:
            break
        time.sleep(delay_s * 0.3)

    if not results and last_error and not used_query:
        bucket[iid] = {"queries": queries, "error": last_error, "results": []}
        _save_cache(cache)
        time.sleep(delay_s)
        return []

    bucket[iid] = {
        "queries": queries,
        "query_used": used_query,
        "fetched": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "totalResults": len(results),
        "results": results,
    }
    _save_cache(cache)
    time.sleep(delay_s)
    return results


def fetch_wellcome_image_detail(
    image_id: str,
    cache: dict,
    delay_s: float,
) -> dict:
    bucket = _cache_bucket(cache, "wellcome-detail")
    if image_id in bucket:
        return bucket[image_id] if isinstance(bucket[image_id], dict) else {}

    try:
        payload = _get_json(f"{WELLCOME_IMAGE}{image_id}", {})
    except Exception as exc:
        bucket[image_id] = {"error": repr(exc)}
        _save_cache(cache)
        time.sleep(delay_s * 0.3)
        return {}

    bucket[image_id] = payload
    _save_cache(cache)
    time.sleep(delay_s * 0.3)
    return payload


def _wellcome_jpg_url(loc_url: str) -> str:
    m = _IIIF_ID_RE.search(loc_url or "")
    if not m:
        return ""
    iid = m.group(1)
    return f"https://iiif.wellcomecollection.org/image/{iid}/full/760,/0/default.jpg"


def build_image_record_from_wellcome(
    summary: dict,
    detail: dict,
) -> dict | None:
    locs = summary.get("locations") or detail.get("locations") or []
    if not locs or not isinstance(locs[0], dict):
        return None
    loc = locs[0]
    if not _wellcome_open(loc):
        return None
    lic = _wellcome_license_label(loc.get("license"))
    if not lic:
        return None

    src = detail.get("source") or {}
    title = (src.get("title") or "").strip()
    if _looks_like_non_photo(title):
        return None

    image_id = (summary.get("id") or detail.get("id") or "").strip()
    loc_url = (loc.get("url") or "").strip()
    url = _wellcome_jpg_url(loc_url)
    if not url:
        return None

    page = f"https://wellcomecollection.org/works/{src.get('id')}" if src.get("id") else (
        f"https://wellcomecollection.org/images/{image_id}"
    )
    license_url = (loc.get("license") or {}).get("url") or ""

    return {
        "url": url,
        "source": "wellcome-collection",
        "sourceRef": image_id,
        "sourcePageUrl": page,
        "license": lic,
        "licenseUrl": license_url,
        "attribution": f"\"{title[:120]}\" via Wellcome Collection ({lic})",
        "caption": title[:200],
    }


# ---------- Candidate picking ----------

def _score_candidate(
    island: dict,
    rec: dict,
    *,
    lat: float | None = None,
    lon: float | None = None,
    require_geo_for_generic: bool = True,
) -> float | None:
    variants = _name_variants(island)
    if not variants:
        return None
    title = (rec.get("caption") or "").strip()
    if not _mentions(title, variants):
        return None

    max_km = _geo_max_km(island)
    isl_lat = island.get("lat")
    isl_lon = _island_lon(island)

    if lat is not None and lon is not None and isl_lat is not None and isl_lon is not None:
        try:
            dist = _haversine_km(float(isl_lat), float(isl_lon), float(lat), float(lon))
        except (TypeError, ValueError):
            dist = 1e9
        if dist > max_km:
            return None
        return dist

    if require_geo_for_generic and _is_generic_island_name(island.get("name") or ""):
        return None
    return 50.0


def pick_ia_candidate(
    island: dict,
    docs: list[dict],
    cache: dict,
    delay_s: float,
    rejected: list[dict],
) -> tuple[dict, float, str] | None:
    best: tuple[float, dict] | None = None
    variants = _name_variants(island)
    if not variants:
        return None

    for doc in docs:
        title = (doc.get("title") or "").strip()
        lic_url = (doc.get("licenseurl") or "").strip()
        if not _ia_license_ok(lic_url):
            rejected.append({
                "id": island.get("id"),
                "source": "internet-archive",
                "reason": "license-not-open",
                "title": title[:80],
            })
            continue
        if not (_mentions(title, variants)):
            rejected.append({
                "id": island.get("id"),
                "source": "internet-archive",
                "reason": "name-not-in-title",
                "title": title[:80],
            })
            continue
        identifier = doc.get("identifier")
        meta = fetch_ia_metadata(identifier, cache, delay_s)
        rec = build_image_record_from_ia(doc, meta)
        if not rec:
            continue
        score = 50.0
        if best is None or score < best[0]:
            best = (score, rec)

    if best is None:
        return None
    score, rec = best
    return rec, score, "internet-archive; name in title/caption"


def pick_flickr_candidates(
    island: dict,
    photos: list[dict],
    institution: str,
    rejected: list[dict],
) -> tuple[dict, float, str] | None:
    variants = _name_variants(island)
    if not variants:
        return None
    max_km = _geo_max_km(island)
    isl_lat = island.get("lat")
    isl_lon = _island_lon(island)
    best: tuple[float, dict] | None = None

    for photo in photos:
        title = (photo.get("title") or "").strip()
        desc = _strip_html(photo.get("description", "") or "")
        tags = (photo.get("tags") or "").replace(" ", " ")
        blob = f"{title} {desc} {tags}"
        if not (_mentions(title, variants) or _mentions(blob, variants)):
            rejected.append({
                "id": island.get("id"),
                "source": f"flickr-commons-{institution}",
                "reason": "name-not-in-metadata",
                "title": title[:80],
            })
            continue

        lat = photo.get("latitude")
        lon = photo.get("longitude")
        score = 50.0
        if (
            isinstance(lat, (int, float, str))
            and isinstance(lon, (int, float, str))
            and isl_lat is not None
            and isl_lon is not None
        ):
            try:
                dist = _haversine_km(
                    float(isl_lat), float(isl_lon), float(lat), float(lon),
                )
            except (TypeError, ValueError):
                dist = 1e9
            if dist > max_km:
                rejected.append({
                    "id": island.get("id"),
                    "source": institution,
                    "reason": f"geo {dist:.1f} km > {max_km:.0f} km",
                })
                continue
            score = dist

        if _is_generic_island_name(island.get("name") or "") and score >= 50.0:
            rejected.append({
                "id": island.get("id"),
                "source": institution,
                "reason": "generic name requires geo",
            })
            continue

        rec = build_image_record_from_flickr_commons(photo, institution=institution)
        if rec and (best is None or score < best[0]):
            best = (score, rec)

    if best is None:
        return None
    score, rec = best
    reason = (
        f"flickr-commons-{institution}; geo {score:.1f} km"
        if score < max_km
        else f"flickr-commons-{institution}; name match"
    )
    return rec, score, reason


def pick_wellcome_candidate(
    island: dict,
    results: list[dict],
    cache: dict,
    delay_s: float,
    rejected: list[dict],
) -> tuple[dict, float, str] | None:
    variants = _name_variants(island)
    if not variants:
        return None
    best: tuple[float, dict] | None = None

    for summary in results:
        image_id = (summary.get("id") or "").strip()
        if not image_id:
            continue
        detail = fetch_wellcome_image_detail(image_id, cache, delay_s)
        src = detail.get("source") or {}
        title = (src.get("title") or "").strip()
        if not title:
            continue
        if not _mentions(title, variants):
            rejected.append({
                "id": island.get("id"),
                "source": "wellcome-collection",
                "reason": "name-not-in-work-title",
                "title": title[:80],
            })
            continue
        if not _title_mentions_nation(title, island):
            rejected.append({
                "id": island.get("id"),
                "source": "wellcome-collection",
                "reason": "title-lacks-uk-nation-context",
                "title": title[:80],
            })
            continue
        rec = build_image_record_from_wellcome(summary, detail)
        if not rec:
            rejected.append({
                "id": island.get("id"),
                "source": "wellcome-collection",
                "reason": "license-or-access-blocked",
            })
            continue
        score = 50.0
        if best is None or score < best[0]:
            best = (score, rec)

    if best is None:
        return None
    score, rec = best
    return rec, score, "wellcome-collection; name in work title"


def pick_best_for_island(
    island: dict,
    cache: dict,
    delay_s: float,
    flickr_key: str,
    rejected: list[dict],
) -> tuple[dict, float, str, str] | None:
    """Return (image_record, score, reason, winning_source)."""
    candidates: list[tuple[float, dict, str, str]] = []

    ia_docs = fetch_ia_search(island, cache, delay_s)
    ia_pick = pick_ia_candidate(island, ia_docs, cache, delay_s, rejected)
    if ia_pick:
        rec, score, reason = ia_pick
        candidates.append((score, rec, reason, "internet-archive"))

    fetch_nls_gallery(island, cache, delay_s)

    for institution, nsid in (
        ("nls", FLICKR_NLS_NSID),
        ("british-library", FLICKR_BL_NSID),
    ):
        if flickr_key:
            photos = fetch_flickr_institution_api(
                island, institution, nsid, flickr_key, cache, delay_s,
            )
        else:
            photos = fetch_flickr_institution_feed(
                island, institution, nsid, cache, delay_s,
            )
        flickr_pick = pick_flickr_candidates(island, photos, institution, rejected)
        if flickr_pick:
            rec, score, reason = flickr_pick
            candidates.append((score, rec, reason, institution))

    wellcome_results = fetch_wellcome_search(island, cache, delay_s)
    well_pick = pick_wellcome_candidate(
        island, wellcome_results, cache, delay_s, rejected,
    )
    if well_pick:
        rec, score, reason = well_pick
        candidates.append((score, rec, reason, "wellcome-collection"))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    score, rec, reason, src = candidates[0]
    return rec, score, reason, src


def _save_staging(adoptions: list[dict]) -> None:
    STAGING.parent.mkdir(parents=True, exist_ok=True)
    tmp = STAGING.with_suffix(STAGING.suffix + ".tmp")
    tmp.write_text(
        json.dumps(adoptions, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, STAGING)


def main() -> int:
    _load_dotenv(ENV_LOCAL)
    p = argparse.ArgumentParser(
        description="Stage historical/open photos (Archive, NLS, BL Flickr, Wellcome).",
    )
    p.add_argument(
        "--named-only",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Only islands in islands_index.json (default: true).",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=0,
        help=f"Max pending islands to try (0=all, max {MAX_LIMIT}).",
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--delay", type=float, default=DEFAULT_DELAY_S)
    p.add_argument("--test", default="", help="Single island id.")
    args = p.parse_args()

    if args.limit > MAX_LIMIT:
        print(f"FATAL: --limit {args.limit} exceeds max {MAX_LIMIT}", file=sys.stderr)
        return 2
    delay_s = max(0.0, float(args.delay))
    flickr_key = os.environ.get("FLICKR_API_KEY", "").strip()

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    if not isinstance(islands, list):
        print("FATAL: islands.json is not a list", file=sys.stderr)
        return 2

    cache = _load(CACHE)
    adoptions: list[dict] = []
    api_status: dict[str, Any] = {
        "internet_archive": "pending",
        "nls_digital_gallery": "pending",
        "nls_flickr_commons": "pending",
        "british_library_flickr": "pending",
        "wellcome_collection": "pending",
        "flickr_api_key": bool(flickr_key),
    }

    report: dict[str, Any] = {
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "args": {
            "named_only": args.named_only,
            "limit": args.limit,
            "dry_run": args.dry_run,
            "delay": delay_s,
        },
        "api_status": api_status,
        "adopted": [],
        "rejected": [],
    }

    pending = [i for i in islands if not (i.get("images") or [])]
    if args.named_only:
        named_ids = _load_named_index_ids()
        if named_ids:
            before = len(pending)
            pending = [i for i in pending if i.get("id") in named_ids]
            print(
                f"  named-only: {len(pending):,} of {before:,} without images",
                flush=True,
            )
    if args.test:
        pending = [i for i in islands if i.get("id") == args.test]
    if args.limit:
        pending = pending[: args.limit]
    print(f"Pending (archive/NLS): {len(pending):,}", flush=True)

    nls_probe = probe_nls_gallery_api(cache)
    api_status["nls_digital_gallery"] = (
        "ok" if nls_probe.get("accessible") else "unavailable (no public JSON search API)"
    )

    pending_set = {i.get("id") for i in pending}
    n_attempted = 0
    n_adopted = 0
    source_wins: dict[str, int] = {}
    ia_ok = False
    well_ok = False
    bl_feed_ok = False
    nls_feed_ok = False

    for isl in islands:
        if isl.get("id") not in pending_set:
            continue
        n_attempted += 1
        rejected: list[dict] = []
        picked = pick_best_for_island(isl, cache, delay_s, flickr_key, rejected)
        report["rejected"].extend(rejected[:20])

        if picked:
            rec, score, reason, src = picked
            source_wins[src] = source_wins.get(src, 0) + 1
            if src == "internet-archive":
                ia_ok = True
            elif src == "wellcome-collection":
                well_ok = True
            elif src == "british-library":
                bl_feed_ok = True
            elif src == "nls":
                nls_feed_ok = True

            adoption = {
                "id": isl["id"],
                "image_record": rec,
                "confidence": CONFIDENCE,
                "reason": reason,
            }
            adoptions.append(adoption)
            n_adopted += 1
            report["adopted"].append({
                "id": isl["id"],
                "name": isl.get("name", ""),
                "source": rec.get("source"),
                "winning_pipeline": src,
                "license": rec.get("license"),
                "url": rec.get("url"),
                "sourcePageUrl": rec.get("sourcePageUrl"),
                "reason": reason,
                "score": score,
            })
            print(
                f"  ✓ [{n_attempted:4d}/{len(pending):4d}] {isl['id']:45s} "
                f"← {src} {rec.get('license')} {rec.get('caption', '')[:45]}",
                flush=True,
            )

        if n_attempted == 1:
            try:
                fetch_ia_search(isl, cache, delay_s)
                api_status["internet_archive"] = "ok"
                ia_ok = True
            except Exception as exc:
                api_status["internet_archive"] = f"error: {exc!r}"
            try:
                fetch_wellcome_search(isl, cache, delay_s)
                api_status["wellcome_collection"] = "ok"
                well_ok = True
            except Exception as exc:
                api_status["wellcome_collection"] = f"error: {exc!r}"
            try:
                fetch_flickr_institution_feed(
                    isl, "british-library", FLICKR_BL_NSID, cache, delay_s,
                )
                api_status["british_library_flickr"] = (
                    "ok (commons feed)" if flickr_key else "ok (commons feed; set FLICKR_API_KEY for text search)"
                )
                bl_feed_ok = True
            except Exception as exc:
                api_status["british_library_flickr"] = f"error: {exc!r}"
            try:
                fetch_flickr_institution_feed(
                    isl, "nls", FLICKR_NLS_NSID, cache, delay_s,
                )
                api_status["nls_flickr_commons"] = "ok (commons feed)"
                nls_feed_ok = True
            except Exception as exc:
                api_status["nls_flickr_commons"] = f"error: {exc!r}"

        if not args.dry_run and n_attempted % 25 == 0:
            _save_staging(adoptions)
            _save(REPORT, report)

    if ia_ok or n_attempted:
        api_status["internet_archive"] = api_status.get("internet_archive") if api_status["internet_archive"] != "pending" else ("ok" if ia_ok else "ok (searches; low hit rate expected)")
    if well_ok:
        api_status["wellcome_collection"] = "ok"
    if bl_feed_ok:
        api_status["british_library_flickr"] = api_status.get("british_library_flickr", "ok")
    if nls_feed_ok:
        api_status["nls_flickr_commons"] = api_status.get("nls_flickr_commons", "ok")

    if not args.dry_run:
        _save_staging(adoptions)
    _save_cache(cache)

    report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    report["attempted"] = n_attempted
    report["staged_total"] = len(adoptions)
    report["source_wins"] = source_wins
    report["dry_run"] = args.dry_run
    report["staging_path"] = str(STAGING.relative_to(ROOT))
    _save(REPORT, report)

    print()
    print(f"Attempted: {n_attempted:,}")
    print(f"Staged:    {n_adopted:,}")
    if not args.dry_run:
        print(f"Staging  → {STAGING.relative_to(ROOT)} ({len(adoptions):,} records)")
    print(f"Report   → {REPORT.relative_to(ROOT)}")
    print("API status:")
    for k, v in api_status.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
