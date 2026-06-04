#!/usr/bin/env python3
"""Lead-photo enrichment via Europeana Search API and Flickr (CC + Commons feeds).

Targets named atlas islands (``islands_index.json``) still lacking ``images[]``.
Reuses name-matching and geo gates from ``enrich_images_v5`` / Openverse harvester.

API keys (optional but required for Europeana; Flickr CC needs a key):
  - ``EUROPEANA_API_KEY`` or ``EUROPEANA_WSKEY`` — register at https://pro.europeana.eu
  - ``FLICKR_API_KEY`` — https://www.flickr.com/services/api/misc.api_keys.html

Without ``FLICKR_API_KEY``, only Flickr **Commons institution** tag feeds are tried
(public ``photos_public.gne`` JSON; licence fixed to Flickr Commons usage policy).

Run::

    python3 scripts/enrich_images_flickr_europeana.py --named-only --limit 200
    python3 scripts/enrich_images_flickr_europeana.py --dry-run --test iona

Outputs (default: staging only)::

    data/staging/adoptions/flickr-europeana.json
    data/cache_europeana.json
    data/cache_flickr_cc.json
    data/cache_flickr_commons_feed.json
    data/image_enrichment_flickr_europeana_report.json
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
STAGING = DATA / "staging" / "adoptions" / "flickr-europeana.json"
CACHE_EUROPEANA = DATA / "cache_europeana.json"
CACHE_FLICKR = DATA / "cache_flickr_cc.json"
CACHE_FLICKR_FEED = DATA / "cache_flickr_commons_feed.json"
REPORT = DATA / "image_enrichment_flickr_europeana_report.json"
ENV_LOCAL = ROOT / ".env.local"

EUROPEANA_SEARCH = "https://api.europeana.eu/record/v2/search.json"
FLICKR_REST = "https://www.flickr.com/services/rest/"
FLICKR_FEED = "https://www.flickr.com/services/feeds/photos_public.gne"

USER_AGENT = "isles-of-britain/0.1 flickr-europeana-enrichment"
DEFAULT_DELAY_S = 1.5
CONFIDENCE = "medium"
GEO_MAX_KM = 15.0
GEO_MAX_KM_GENERIC = 5.0
EUROPEANA_ROWS = 20
FLICKR_PER_PAGE = 20
# Flickr API licence ids: 4=BY, 5=BY-SA, 9=CC0, 10=PDM (exclude 6=BY-ND)
FLICKR_LICENSE_IDS = "4,5,9,10"

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
_PDM_URL_RE = re.compile(r"creativecommons\.org/publicdomain/mark", re.IGNORECASE)
_EXCLUDED_RIGHTS_RE = re.compile(
    r"(?:by-nc|by-nd|nc-nd|noncommercial|non-commercial|all-rights-reserved|"
    r"copyrighted|in-copyright|permission)",
    re.IGNORECASE,
)
_FLICKR_PHOTO_ID_RE = re.compile(r"flickr\.com/photos/[^/]+/(\d+)")
_MEDIA_URL_RE = re.compile(r'https://live\.staticflickr\.com/[^"\s]+')

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


def _search_query(island: dict) -> str:
    name = (island.get("name") or "").strip()
    nation = (island.get("nation") or "").strip()
    if nation:
        return f'"{name}" {nation}'
    return f'"{name}"'


def _geo_max_km(island: dict) -> float:
    return GEO_MAX_KM_GENERIC if _is_generic_island_name(island.get("name") or "") else GEO_MAX_KM


def _looks_like_non_photo(title: str) -> bool:
    if not title:
        return True
    return bool(_NON_PHOTO_TITLE_RE.search(title))


def _save_cache(path: Path, cache: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(cache, ensure_ascii=False, separators=(",", ":"))
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


def _fetch_bytes(url: str, params: dict[str, Any] | None = None) -> bytes:
    qs = f"?{urllib.parse.urlencode(params)}" if params else ""
    req = urllib.request.Request(
        f"{url}{qs}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json,*/*"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def _license_from_rights_urls(urls: list[str]) -> tuple[str, str] | None:
    """Return (license label, licenseUrl) or None if not clearly open."""
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
            return "PDM", "http://creativecommons.org/publicdomain/mark/1.0/"
        m = _CC_URL_RE.search(u)
        if m:
            kind, ver = m.group(1).lower(), m.group(2)
            if "nc" in kind or "nd" in kind:
                continue
            if kind == "by":
                return f"CC-BY-{ver}", u
            if kind == "by-sa":
                return f"CC-BY-SA-{ver}", u
    if any("publicdomain" in u.lower() or "pdmark" in u.lower() for u in urls):
        return "PDM", urls[0]
    return None


def _flickr_license_label(license_id: str) -> str | None:
    m = {
        "4": "CC-BY-2.0",
        "5": "CC-BY-SA-2.0",
        "9": "CC0-1.0",
        "10": "PDM",
    }
    return m.get(str(license_id).strip())


def _flickr_page_url(photo_id: str, owner: str | None = None) -> str:
    if owner:
        return f"https://www.flickr.com/photos/{owner}/{photo_id}"
    return f"https://www.flickr.com/photo.gne?id={photo_id}"


def _best_image_url_from_flickr(photo: dict) -> str:
    sizes = photo.get("sizes", {}).get("size") or []
    if isinstance(sizes, dict):
        sizes = [sizes]
    best_url = ""
    best_area = 0
    for sz in sizes:
        if not isinstance(sz, dict):
            continue
        label = (sz.get("label") or "").lower()
        if label in ("thumb", "square", "icon"):
            continue
        url = (sz.get("source") or "").strip()
        w = int(sz.get("width") or 0)
        h = int(sz.get("height") or 0)
        area = w * h
        if url and area >= best_area:
            best_area = area
            best_url = url
    if best_url:
        return best_url
    return (photo.get("url_m") or photo.get("url_l") or photo.get("url_o") or "").strip()


# ---------- Europeana ----------

def fetch_europeana(
    island: dict,
    api_key: str,
    cache: dict,
    delay_s: float,
) -> list[dict]:
    key = island.get("id") or _search_query(island)
    if key in cache:
        entry = cache[key]
        if isinstance(entry, dict) and isinstance(entry.get("items"), list):
            return entry["items"]

    q = _search_query(island)
    params: dict[str, Any] = {
        "wskey": api_key,
        "query": q,
        "reusability": "open",
        "qf": "TYPE:IMAGE",
        "profile": "rich",
        "rows": EUROPEANA_ROWS,
        "start": 1,
    }
    lat = island.get("lat")
    lon = _island_lon(island)
    if isinstance(lat, (int, float)) and lon is not None:
        params["qf"] = [params["qf"], f"WHERE:{lat},{lon},25"]

    try:
        payload = _get_json(EUROPEANA_SEARCH, params)
    except Exception as exc:
        print(f"  europeana failed for {key}: {exc!r}", file=sys.stderr)
        cache[key] = {"query": q, "error": repr(exc), "items": []}
        _save_cache(CACHE_EUROPEANA, cache)
        time.sleep(delay_s)
        return []

    items = payload.get("items") or []
    cache[key] = {
        "query": q,
        "params": {k: v for k, v in params.items() if k != "wskey"},
        "fetched": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "itemsCount": payload.get("itemsCount"),
        "totalResults": payload.get("totalResults"),
        "items": items,
    }
    _save_cache(CACHE_EUROPEANA, cache)
    time.sleep(delay_s)
    return items


def _europeana_coords(item: dict) -> tuple[float, float] | None:
    def _first_float(vals: Any) -> float | None:
        if isinstance(vals, list):
            for v in vals:
                try:
                    return float(str(v).strip())
                except (TypeError, ValueError):
                    continue
        if vals is not None:
            try:
                return float(str(vals).strip())
            except (TypeError, ValueError):
                return None
        return None

    lat = _first_float(item.get("edmPlaceLatitude"))
    lon = _first_float(item.get("edmPlaceLongitude"))
    if lat is not None and lon is not None:
        return lat, lon
    return None


def build_image_record_from_europeana(item: dict) -> dict | None:
    rights = item.get("rights") or []
    if isinstance(rights, str):
        rights = [rights]
    lic = _license_from_rights_urls([str(r) for r in rights])
    if not lic:
        return None
    license_label, license_url = lic

    url = (item.get("edmPreview") or "").strip()
    if not url:
        shown = item.get("isShownBy")
        if isinstance(shown, list):
            url = (shown[0] if shown else "").strip()
        elif shown:
            url = str(shown).strip()
    url = str(url).strip()
    if not url or not url.startswith("http"):
        return None

    titles = item.get("title") or []
    if isinstance(titles, str):
        titles = [titles]
    title = (titles[0] if titles else "").strip()
    if _looks_like_non_photo(title):
        return None

    page = (item.get("guid") or item.get("link") or "").strip()
    rec_id = (item.get("id") or "").strip() or page
    creators = item.get("dcCreator") or []
    if isinstance(creators, str):
        creators = [creators]
    creator = (creators[0] if creators else "").strip() or "Unknown"
    provider = (item.get("dataProvider") or item.get("provider") or "Europeana")
    if isinstance(provider, list):
        provider = (provider[0] if provider else "Europeana")
    provider = str(provider).strip()

    return {
        "url": url,
        "source": "europeana",
        "sourceRef": rec_id,
        "sourcePageUrl": page or url,
        "license": license_label,
        "licenseUrl": license_url,
        "attribution": f"\"{title}\" by {creator} via {provider} ({license_label})",
        "caption": title,
    }


def pick_europeana_candidate(
    island: dict,
    items: list[dict],
    rejected: list[dict],
) -> tuple[dict, float, str] | None:
    variants = _name_variants(island)
    if not variants:
        return None
    max_km = _geo_max_km(island)
    isl_lat = island.get("lat")
    isl_lon = _island_lon(island)
    best: tuple[float, dict] | None = None

    for item in items:
        titles = item.get("title") or []
        if isinstance(titles, str):
            titles = [titles]
        title = (titles[0] if titles else "").strip()
        desc_parts = item.get("dcDescription") or []
        if isinstance(desc_parts, str):
            desc_parts = [desc_parts]
        desc = " ".join(str(d) for d in desc_parts)
        spatial = item.get("dctermsSpatial") or []
        if isinstance(spatial, str):
            spatial = [spatial]
        blob = " ".join([title, desc, " ".join(str(s) for s in spatial)])

        if not (_mentions(title, variants) or _mentions(blob, variants)):
            rejected.append({
                "id": island.get("id"),
                "source": "europeana",
                "europeana_id": item.get("id"),
                "reason": "name-not-in-metadata",
                "title": title[:120],
            })
            continue

        coords = _europeana_coords(item)
        if coords and isl_lat is not None and isl_lon is not None:
            dist = _haversine_km(
                float(isl_lat), float(isl_lon), coords[0], coords[1],
            )
            if dist > max_km:
                rejected.append({
                    "id": island.get("id"),
                    "source": "europeana",
                    "reason": f"geo {dist:.1f} km > {max_km:.0f} km",
                    "title": title[:120],
                })
                continue
            score = dist
        else:
            score = 50.0

        rec = build_image_record_from_europeana(item)
        if rec and (best is None or score < best[0]):
            best = (score, rec)

    if best is None:
        return None
    score, rec = best
    reason = (
        f"name match; geo {score:.1f} km (max {max_km:.0f} km)"
        if score < max_km
        else "name match; no result geo"
    )
    return rec, score, reason


# ---------- Flickr API (CC) ----------

def _flickr_rest(method: str, api_key: str, **kwargs: Any) -> dict:
    params: dict[str, Any] = {
        "method": method,
        "api_key": api_key,
        "format": "json",
        "nojsoncallback": 1,
    }
    params.update(kwargs)
    raw = _fetch_bytes(FLICKR_REST, params)
    data = json.loads(raw.decode("utf-8"))
    if data.get("stat") != "ok":
        raise RuntimeError(data.get("message") or data)
    return data


def fetch_flickr_cc(
    island: dict,
    api_key: str,
    cache: dict,
    delay_s: float,
) -> list[dict]:
    key = island.get("id") or ""
    if key in cache:
        entry = cache[key]
        if isinstance(entry, dict) and isinstance(entry.get("photos"), list):
            return entry["photos"]

    name = (island.get("name") or "").strip()
    nation = (island.get("nation") or "").strip()
    text = f"{name} {nation}".strip()
    lat = island.get("lat")
    lon = _island_lon(island)

    kwargs: dict[str, Any] = {
        "text": text,
        "license": FLICKR_LICENSE_IDS,
        "content_type": 1,
        "media": "photos",
        "per_page": FLICKR_PER_PAGE,
        "extras": "url_m,url_l,license,owner_name,geo,description,tags",
    }
    if isinstance(lat, (int, float)) and lon is not None:
        kwargs["lat"] = lat
        kwargs["lon"] = lon
        kwargs["radius"] = 15
        kwargs["radius_units"] = "km"

    try:
        data = _flickr_rest("flickr.photos.search", api_key, **kwargs)
    except Exception as exc:
        print(f"  flickr search failed for {key}: {exc!r}", file=sys.stderr)
        cache[key] = {"text": text, "error": repr(exc), "photos": []}
        _save_cache(CACHE_FLICKR, cache)
        time.sleep(delay_s)
        return []

    photos = data.get("photos", {}).get("photo") or []
    if isinstance(photos, dict):
        photos = [photos]
    cache[key] = {
        "text": text,
        "fetched": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "photos": photos,
    }
    _save_cache(CACHE_FLICKR, cache)
    time.sleep(delay_s)
    return photos


def build_image_record_from_flickr(photo: dict, *, commons: bool = False) -> dict | None:
    photo_id = str(photo.get("id") or "").strip()
    if not photo_id:
        return None
    title = (photo.get("title") or "").strip()
    if _looks_like_non_photo(title):
        return None

    if commons:
        license_label = "No known copyright restrictions"
        license_url = "https://www.flickr.com/commons/usage/"
        source = "flickr-commons"
    else:
        license_label = _flickr_license_label(str(photo.get("license") or ""))
        if not license_label:
            return None
        license_url = {
            "CC-BY-2.0": "https://creativecommons.org/licenses/by/2.0/",
            "CC-BY-SA-2.0": "https://creativecommons.org/licenses/by-sa/2.0/",
            "CC0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
            "PDM": "http://creativecommons.org/publicdomain/mark/1.0/",
        }.get(license_label, "")
        source = "flickr-cc"

    owner = (photo.get("owner") or photo.get("owner_id") or "").strip()
    owner_name = (photo.get("ownername") or photo.get("author") or owner or "Unknown").strip()
    page = _flickr_page_url(photo_id, owner if owner and "@" not in owner else None)

    url = _best_image_url_from_flickr(photo)
    if not url:
        media = photo.get("media", {})
        if isinstance(media, dict):
            url = (media.get("m") or "").replace("_m.", "_b.")
    if not url:
        return None

    desc = _strip_html(photo.get("description", "") or "")
    blob = f"{title} {desc}"

    return {
        "url": url,
        "source": source,
        "sourceRef": photo_id,
        "sourcePageUrl": (photo.get("link") or page).strip(),
        "license": license_label,
        "licenseUrl": license_url,
        "attribution": f"\"{title or photo_id}\" by {owner_name} ({license_label})",
        "caption": title or desc[:120],
    }


def pick_flickr_candidate(
    island: dict,
    photos: list[dict],
    rejected: list[dict],
    *,
    commons: bool,
) -> tuple[dict, float, str] | None:
    variants = _name_variants(island)
    if not variants:
        return None
    max_km = _geo_max_km(island)
    isl_lat = island.get("lat")
    isl_lon = _island_lon(island)
    best: tuple[float, dict] | None = None
    src = "flickr-commons" if commons else "flickr-cc"

    for photo in photos:
        title = (photo.get("title") or "").strip()
        desc = _strip_html(photo.get("description", "") or "")
        tags = (photo.get("tags") or "").replace(" ", " ")
        blob = f"{title} {desc} {tags}"
        if not (_mentions(title, variants) or _mentions(blob, variants)):
            rejected.append({
                "id": island.get("id"),
                "source": src,
                "photo_id": photo.get("id"),
                "reason": "name-not-in-metadata",
                "title": title[:120],
            })
            continue

        lat = photo.get("latitude") or photo.get("lat")
        lon = photo.get("longitude") or photo.get("lon")
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
                    "source": src,
                    "reason": f"geo {dist:.1f} km > {max_km:.0f} km",
                    "title": title[:120],
                })
                continue
            score = dist
        else:
            if not commons and _is_generic_island_name(island.get("name") or ""):
                rejected.append({
                    "id": island.get("id"),
                    "source": src,
                    "reason": "generic name requires geo on photo",
                    "title": title[:120],
                })
                continue
            score = 50.0

        rec = build_image_record_from_flickr(photo, commons=commons)
        if rec and (best is None or score < best[0]):
            best = (score, rec)

    if best is None:
        return None
    score, rec = best
    reason = (
        f"name match; geo {score:.1f} km (max {max_km:.0f} km)"
        if score < max_km
        else "name match; no photo geo"
    )
    return rec, score, reason


# ---------- Flickr Commons tag feeds (no API key) ----------

def _parse_feed_photo_id(link: str) -> str:
    m = _FLICKR_PHOTO_ID_RE.search(link or "")
    return m.group(1) if m else ""


def _license_from_feed_description(desc_html: str) -> tuple[str, str] | None:
    if not desc_html:
        return None
    lic = _license_from_rights_urls(re.findall(r'https?://[^\s"<>]+', desc_html))
    if lic:
        return lic
    if "flickr.com/commons" in desc_html.lower():
        return "No known copyright restrictions", "https://www.flickr.com/commons/usage/"
    return None


def fetch_flickr_commons_feed(
    island: dict,
    cache: dict,
    delay_s: float,
) -> list[dict]:
    name = (island.get("name") or "").strip()
    safe = re.sub(r"[^\w]+", "", name.lower())
    if len(safe) < 4:
        return []
    cache_key = f"{island.get('id')}|{safe}"
    if cache_key in cache:
        entry = cache[cache_key]
        if isinstance(entry, dict) and isinstance(entry.get("photos"), list):
            return entry["photos"]

    nation = (island.get("nation") or "").strip().lower()
    nation_tag = {
        "scotland": "scotland",
        "wales": "wales",
        "england": "england",
        "ireland": "ireland",
        "northern ireland": "northernireland",
        "isle of man": "isleofman",
        "crown dependency": "channelislands",
    }.get(nation, "scotland")

    tag_sets = [
        f"{safe},{nation_tag}",
        f"{safe},island,{nation_tag}",
    ]
    photos: list[dict] = []
    seen: set[str] = set()

    for tags in tag_sets:
        params = {
            "tags": tags,
            "tagmode": "all",
            "format": "json",
            "nojsoncallback": 1,
        }
        try:
            raw = _fetch_bytes(FLICKR_FEED, params)
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            print(f"  flickr feed {tags}: {exc!r}", file=sys.stderr)
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
            author = ""
            m_auth = re.search(r'flickr\.com/people/([^/"]+)/', desc)
            if m_auth:
                author = m_auth.group(1)
            photos.append({
                "id": pid,
                "title": title,
                "description": desc,
                "link": link,
                "url_m": url,
                "owner": author,
                "ownername": author,
                "license": "10",
                "feed_tags": tags,
                "feed_license": lic[0],
            })
            seen.add(pid)
        time.sleep(delay_s * 0.5)

    cache[cache_key] = {
        "tags_tried": tag_sets,
        "fetched": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "photos": photos,
    }
    _save_cache(CACHE_FLICKR_FEED, cache)
    return photos


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
        description="Stage Europeana + Flickr lead photos for named islands without images.",
    )
    p.add_argument("--named-only", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--limit", type=int, default=0, help="Max pending islands to try (0=all).")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--delay", type=float, default=DEFAULT_DELAY_S)
    p.add_argument("--test", default="", help="Single island id.")
    p.add_argument(
        "--skip-europeana",
        action="store_true",
        help="Skip Europeana even if API key is set.",
    )
    p.add_argument(
        "--skip-flickr",
        action="store_true",
        help="Skip Flickr API and feed fallbacks.",
    )
    args = p.parse_args()
    delay_s = max(0.0, float(args.delay))

    europeana_key = (
        os.environ.get("EUROPEANA_API_KEY")
        or os.environ.get("EUROPEANA_WSKEY")
        or ""
    ).strip()
    flickr_key = os.environ.get("FLICKR_API_KEY", "").strip()

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    pending = [i for i in islands if not (i.get("images") or [])]
    if args.named_only:
        named_ids = _load_named_index_ids()
        if named_ids:
            before = len(pending)
            pending = [i for i in pending if i.get("id") in named_ids]
            print(f"  named-only: {len(pending):,} of {before:,} without images", flush=True)
    if args.test:
        pending = [i for i in islands if i.get("id") == args.test]
    if args.limit:
        pending = pending[: args.limit]

    cache_eu = _load(CACHE_EUROPEANA)
    cache_fl = _load(CACHE_FLICKR)
    cache_feed = _load(CACHE_FLICKR_FEED)
    adoptions: list[dict] = []
    report: dict[str, Any] = {
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "args": vars(args),
        "keys": {
            "europeana": bool(europeana_key),
            "flickr_api": bool(flickr_key),
        },
        "geo_max_km": GEO_MAX_KM,
        "geo_max_km_generic": GEO_MAX_KM_GENERIC,
        "pending_considered": len(pending),
        "adopted": [],
        "rejected": [],
        "skipped_sources": [],
    }

    if not europeana_key and not args.skip_europeana:
        msg = (
            "EUROPEANA_API_KEY unset — Europeana skipped. "
            "Register at https://pro.europeana.eu and add key to .env.local"
        )
        report["skipped_sources"].append(msg)
        print(f"WARN: {msg}", file=sys.stderr)
    if not flickr_key and not args.skip_flickr:
        msg = (
            "FLICKR_API_KEY unset — Flickr CC API skipped; "
            "trying Commons-oriented tag feeds only (licence must appear in feed HTML)."
        )
        report["skipped_sources"].append(msg)
        print(f"WARN: {msg}", file=sys.stderr)

    pending_set = {i.get("id") for i in pending}
    n_adopted = 0

    for isl in islands:
        if isl.get("id") not in pending_set:
            continue

        picked: tuple[dict, str, str] | None = None  # record, reason, via

        if europeana_key and not args.skip_europeana:
            items = fetch_europeana(isl, europeana_key, cache_eu, delay_s)
            eu = pick_europeana_candidate(isl, items, report["rejected"])
            if eu:
                rec, _score, reason = eu
                picked = (rec, reason, "europeana")

        if picked is None and flickr_key and not args.skip_flickr:
            photos = fetch_flickr_cc(isl, flickr_key, cache_fl, delay_s)
            fl = pick_flickr_candidate(isl, photos, report["rejected"], commons=False)
            if fl:
                rec, _score, reason = fl
                picked = (rec, reason, "flickr-cc")

        if picked is None and not args.skip_flickr:
            feed_photos = fetch_flickr_commons_feed(isl, cache_feed, delay_s)
            if feed_photos:
                flc = pick_flickr_candidate(
                    isl, feed_photos, report["rejected"], commons=True,
                )
                if flc:
                    rec, _score, reason = flc
                    picked = (rec, reason, "flickr-commons-feed")

        if picked:
            rec, reason, via = picked
            adoption = {
                "id": isl["id"],
                "image_record": rec,
                "confidence": CONFIDENCE,
                "reason": f"{via}: {reason}",
            }
            adoptions.append(adoption)
            report["adopted"].append({
                "id": isl["id"],
                "name": isl.get("name", ""),
                "via": via,
                **{k: rec.get(k) for k in (
                    "source", "license", "sourcePageUrl", "url", "caption",
                )},
                "reason": reason,
            })
            n_adopted += 1
            print(
                f"  ✓ {isl['id']:40s} [{via}] {rec.get('license')} "
                f"{(rec.get('caption') or '')[:45]}",
                flush=True,
            )
        else:
            report["rejected"].append({
                "id": isl["id"],
                "name": isl.get("name", ""),
                "reason": "no qualifying europeana/flickr result",
            })

    if not args.dry_run:
        _save_staging(adoptions)

    report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    report["adopted_total"] = n_adopted
    report["staged_total"] = len(adoptions)
    report["staging_path"] = str(STAGING.relative_to(ROOT))
    _save(REPORT, report)

    print()
    print(f"Attempted: {len(pending):,}")
    print(f"Adopted:   {n_adopted:,}")
    if not args.dry_run:
        print(f"Staging  → {STAGING.relative_to(ROOT)} ({len(adoptions):,} records)")
    print(f"Report   → {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
