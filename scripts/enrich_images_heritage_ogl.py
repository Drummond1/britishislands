#!/usr/bin/env python3
"""Stage OGL / permissive-CC photos from UK heritage open-data APIs.

Harvesters (strict: name + place + documented OGL/CC licence in metadata):

  - **historic-england-nhle-arcgis** — NHLE FeatureServer (England); spatial +
    name match; list-entry pages probed for OGL image metadata when reachable.
  - **heritage-gateway-national** — national Heritage Gateway UI (legacy); probed
    at startup; usually blocked (redirect / error).
  - **hes-canmore-points** — HES Canmore_Points MapServer on inspire.hes.scot;
    LICENCE field + spatial/name match; trove/canmore record pages for thumbnails.
  - **cadw-listed-wfs** — Cadw Listed Buildings WFS (Wales); OGL GIS + name/place;
    Cof Cymru report probe (typically no redistributable photos).

Blocked sources are listed in ``data/image_enrichment_heritage_ogl_report.json``.

Run::

    python3 scripts/enrich_images_heritage_ogl.py --named-only --limit 300
    python3 scripts/enrich_images_heritage_ogl.py --test brownsea-island --dry-run
    python3 scripts/enrich_images_heritage_ogl.py --cache-only --limit 50

Outputs (staging only)::

    data/staging/adoptions/heritage-ogl.json
    data/image_enrichment_heritage_ogl_report.json
    data/cache_heritage_ogl.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
ISLANDS_INDEX = DATA / "islands_index.json"
STAGING = DATA / "staging" / "adoptions" / "heritage-ogl.json"
REPORT = DATA / "image_enrichment_heritage_ogl_report.json"
CACHE_PATH = DATA / "cache_heritage_ogl.json"

USER_AGENT = "isles-of-britain/0.1 heritage-ogl-enrichment"
DELAY_S = 1.2

# --- Endpoints ---
NHLE_FS = (
    "https://services-eu1.arcgis.com/ZOdPfBS3aqqDYPUQ/arcgis/rest/services/"
    "National_Heritage_List_for_England_NHLE_v02_VIEW/FeatureServer/0"
)
CANMORE_MS = (
    "https://inspire.hes.scot/arcgis/rest/services/CANMORE/Canmore_Points/MapServer/0"
)
CADW_WFS = "https://datamap.gov.wales/geoserver/inspire-wg/wfs"
HERITAGE_GATEWAY_HOME = "https://www.heritagegateway.org.uk/Gateway/"
CANMORE_LEGACY_API = "https://canmore.org.uk/api/site/search/result"

GEO_MAX_KM = 8.0
GEO_MAX_KM_SMALL = 3.0
SMALL_AREA_KM2 = 0.05

SOURCE_NHLE = "historic-england-nhle-arcgis"
SOURCE_HG = "heritage-gateway-national"
SOURCE_CANMORE = "hes-canmore-points"
SOURCE_TROVE = "hes-trove-scot"
SOURCE_CADW = "cadw-listed-wfs"

OGL_LICENSE_MARKERS = (
    "open government licence",
    "open government license",
    "ogl v3",
    "ogl-3",
    "ogl v3.0",
    "uk-ogl",
    "crown copyright",
    "psi directive",
)
CC_LICENSE_MARKERS = ("cc0", "cc-by", "cc by", "public domain", "pd")

IMAGE_EXT_RE = re.compile(r"\.(?:jpe?g|png|gif|webp)(?:\?|$)", re.I)
_OG_IMAGE_RE = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)
_OG_IMAGE_RE2 = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
    re.I,
)
_LICENCE_LABEL_RE = re.compile(
    r"(?:licen[cs]e|copyright|rights)[^<]{0,80}(open government[^<]{0,120}|"
    r"ogl[^<]{0,40}|creative commons[^<]{0,120}|cc[\s\-]?by[^<]{0,80})",
    re.I,
)
_NON_PHOTO_RE = re.compile(
    r"(?:^|[_ \-\(\[])"
    r"(?:logo|icon|map|diagram|chart|badge|coat[_ \-]of[_ \-]arms|"
    r"placeholder|spacer|blank)"
    r"(?:$|[_ \-\)\]])",
    re.I,
)

SOURCES_BLOCKED_STATIC: list[dict[str, str]] = [
    {
        "id": "hes-canmore-legacy-api",
        "reason": "canmore.org.uk JSON API behind Azure WAF (Jun 2025); use inspire.hes.scot MapServer instead.",
    },
    {
        "id": "hes-trove-scot-thumbnails",
        "reason": "No public image API; trove.scot HTML returns 403 to automated clients; per-image contractual licence.",
    },
    {
        "id": "coflein-rcahmw-images",
        "reason": "Coflein/iBase images are view-only or paid licence; site GIS is OGL but not photo redistribution.",
    },
    {
        "id": "cadw-cof-cymru-portal",
        "reason": "Cof Cymru web portal intermittent; listed-building reports lack OGL photo attachments.",
    },
    {
        "id": "historic-england-archive-ioe",
        "reason": "Historic England Archive photos require reproduction permission unless asset page states OGL/CC.",
    },
]

sys.path.insert(0, str(Path(__file__).resolve().parent))
import enrich_images_v5 as v5  # noqa: E402


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _needs_image(island: dict) -> bool:
    return not (island.get("images") or island.get("image"))


def _island_lat(island: dict) -> float | None:
    lat = island.get("lat")
    return float(lat) if isinstance(lat, (int, float)) else None


def _island_lon(island: dict) -> float | None:
    lng = island.get("lng")
    if lng is None:
        lng = island.get("lon")
    return float(lng) if isinstance(lng, (int, float)) else None


def _geo_max_km(island: dict) -> float:
    area = island.get("areaKm2")
    if isinstance(area, (int, float)) and area <= SMALL_AREA_KM2:
        return GEO_MAX_KM_SMALL
    return GEO_MAX_KM


def license_allowed(license_str: str | None) -> bool:
    if not license_str:
        return False
    norm = license_str.strip().lower()
    if not norm or norm in {"unknown", "n/a", "none", "copyrighted", "all rights reserved"}:
        return False
    if "fair use" in norm or "editorial" in norm or "non-commercial" in norm:
        return False
    if "nc" in norm and "cc" in norm:
        return False
    if any(m in norm for m in OGL_LICENSE_MARKERS):
        return True
    if any(m in norm for m in CC_LICENSE_MARKERS):
        return True
    return any(tok in norm for tok in ("cc-by-sa", "cc-by-sa-2.0", "cc-by-sa-4.0"))


def _http_get(
    url: str,
    *,
    accept: str = "application/json",
    timeout: int = 60,
) -> tuple[int, bytes, str]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": accept},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(), resp.headers.get_content_type() or ""
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), exc.headers.get_content_type() or ""


def _wgs84_bbox(lat: float, lon: float, radius_km: float) -> str:
    """Return WFS 2.0 bbox=minx,miny,maxx,maxy,EPSG:4326 for a square search."""
    dlat = radius_km / 111.0
    cos_lat = max(0.2, math.cos(math.radians(lat)))
    dlon = radius_km / (111.0 * cos_lat)
    return f"{lon - dlon},{lat - dlat},{lon + dlon},{lat + dlat},EPSG:4326"


def _place_tokens(island: dict) -> list[str]:
    tokens: list[str] = []
    pwb = island.get("parentWaterBody") or {}
    for key in ("name",):
        val = (pwb.get(key) or "").strip()
        if val and len(val) >= 4:
            tokens.append(val)
    arch = (island.get("archipelago") or "").strip()
    if arch and len(arch) >= 4:
        tokens.append(arch)
    return tokens


def _name_and_place_match(
    island: dict,
    record_name: str,
    *,
    record_lat: float | None,
    record_lon: float | None,
    location_text: str = "",
    spatially_prefiltered: bool = False,
) -> bool:
    variants = v5._name_variants(island)
    text = f"{record_name} {location_text}"
    if not v5._mentions(text, variants):
        return False
    lat_i, lon_i = _island_lat(island), _island_lon(island)
    if lat_i is None or lon_i is None:
        return False
    if not spatially_prefiltered:
        if record_lat is None or record_lon is None:
            return False
        km = v5._haversine_km(lat_i, lon_i, record_lat, record_lon)
        if km > _geo_max_km(island):
            return False
    place_tokens = _place_tokens(island)
    if not place_tokens:
        return True
    blob = v5._strip_diacritics(f"{record_name} {location_text}").lower()
    for tok in place_tokens:
        if v5._strip_diacritics(tok).lower() in blob:
            return True
    # Small islands: name match + tight geo is enough.
    if _geo_max_km(island) <= GEO_MAX_KM_SMALL:
        return True
    return False


def _arcgis_query(base: str, params: dict[str, Any]) -> dict[str, Any]:
    qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    url = f"{base}/query?{qs}"
    status, body, _ = _http_get(url)
    if status != 200:
        raise RuntimeError(f"arcgis HTTP {status} for {base}")
    return json.loads(body.decode("utf-8"))


def _parse_licence_from_html(html: str) -> str:
    low = html.lower()
    if "open government licence" in low or "open government license" in low:
        return "OGL v3.0"
    m = _LICENCE_LABEL_RE.search(html)
    if m:
        frag = m.group(1).strip()
        if license_allowed(frag):
            return frag[:120]
    if "creative commons" in low or "cc-by" in low:
        if "non-commercial" not in low and "nc" not in low.replace(" ", ""):
            return "CC-BY"
    return ""


def _parse_og_image(html: str) -> str:
    for pat in (_OG_IMAGE_RE, _OG_IMAGE_RE2):
        m = pat.search(html)
        if m:
            url = m.group(1).strip()
            if IMAGE_EXT_RE.search(url) and not _NON_PHOTO_RE.search(url):
                return url
    return ""


def fetch_page_image(
    page_url: str,
    cache: dict,
    *,
    live: bool = True,
) -> dict[str, Any] | None:
    bucket = cache.setdefault("pages", {})
    if page_url in bucket and not live:
        return bucket[page_url] or None
    if page_url in bucket and bucket[page_url].get("fetched"):
        meta = bucket[page_url]
        return meta if meta.get("imageUrl") else None

    status, body, ctype = _http_get(page_url, accept="text/html", timeout=45)
    time.sleep(DELAY_S * 0.5)
    meta: dict[str, Any] = {
        "fetched": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "httpStatus": status,
        "imageUrl": "",
        "license": "",
    }
    if status != 200 or "html" not in ctype and "text" not in ctype:
        bucket[page_url] = meta
        return None
    html = body.decode("utf-8", "replace")
    lic = _parse_licence_from_html(html)
    img = _parse_og_image(html)
    meta["license"] = lic
    meta["imageUrl"] = img
    bucket[page_url] = meta
    if img and license_allowed(lic):
        return meta
    return None


def probe_apis() -> dict[str, Any]:
    probes: dict[str, Any] = {}

    # NHLE ArcGIS
    try:
        payload = _arcgis_query(
            NHLE_FS,
            {
                "where": "1=1",
                "returnCountOnly": "true",
                "f": "json",
            },
        )
        probes[SOURCE_NHLE] = {
            "status": "ok",
            "count": payload.get("count", 0),
            "attachments": False,
        }
    except Exception as exc:
        probes[SOURCE_NHLE] = {"status": f"error:{exc!r}"}

    # Heritage Gateway national UI
    code, _, _ = _http_get(HERITAGE_GATEWAY_HOME, accept="text/html", timeout=25)
    if code in (200, 301, 302):
        probes[SOURCE_HG] = {"status": "reachable", "note": "no stable national image API"}
    else:
        probes[SOURCE_HG] = {"status": f"blocked:http-{code}"}

    # Legacy Canmore API (expected WAF)
    code, body, _ = _http_get(
        f"{CANMORE_LEGACY_API}?searchTerm=test&page=0&pageSize=1",
        accept="application/json,text/html",
        timeout=20,
    )
    probes["hes-canmore-legacy-api"] = {
        "status": "blocked:waf" if b"Azure WAF" in body[:800] or code in (403, 301) else f"http-{code}",
    }

    # Canmore MapServer
    try:
        payload = _arcgis_query(
            CANMORE_MS,
            {
                "where": "LICENCE LIKE '%Open Government%'",
                "returnCountOnly": "true",
                "f": "json",
            },
        )
        probes[SOURCE_CANMORE] = {
            "status": "ok",
            "ogl_records": payload.get("count", 0),
            "attachments": False,
        }
    except Exception as exc:
        probes[SOURCE_CANMORE] = {"status": f"error:{exc!r}"}

    # trove.scot HTML
    code, _, _ = _http_get("https://www.trove.scot/", accept="text/html", timeout=20)
    probes[SOURCE_TROVE] = {
        "status": "blocked:http-403" if code == 403 else f"http-{code}",
        "note": "contractual per-image licence; no harvest API",
    }

    # Cadw WFS
    try:
        bbox = _wgs84_bbox(51.7, -5.3, 8.0)
        url = (
            f"{CADW_WFS}?service=WFS&version=2.0.0&request=GetFeature"
            f"&typeName=inspire-wg:Cadw_ListedBuildings&count=1&outputFormat=application/json"
            f"&bbox={urllib.parse.quote(bbox, safe=',')}"
        )
        status, body, _ = _http_get(url, timeout=45)
        if status == 200:
            data = json.loads(body.decode("utf-8"))
            probes[SOURCE_CADW] = {
                "status": "ok",
                "sample_features": len(data.get("features") or []),
            }
        else:
            probes[SOURCE_CADW] = {"status": f"http-{status}"}
    except Exception as exc:
        probes[SOURCE_CADW] = {"status": f"error:{exc!r}"}

    return probes


def query_nhle_near(lat: float, lon: float, *, distance_m: int = 5000) -> list[dict[str, Any]]:
    payload = _arcgis_query(
        NHLE_FS,
        {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "distance": distance_m,
            "units": "esriSRUnit_Meter",
            "outFields": "Name,hyperlink,ListEntry,NGR",
            "returnGeometry": "true",
            "outSR": "4326",
            "resultRecordCount": "25",
            "f": "json",
        },
    )
    out: list[dict[str, Any]] = []
    for feat in payload.get("features") or []:
        attrs = feat.get("attributes") or {}
        geom = feat.get("geometry") or {}
        pts = geom.get("points") or []
        rlat = rlon = None
        if pts:
            rlon, rlat = float(pts[0][0]), float(pts[0][1])
        out.append(
            {
                "name": attrs.get("Name") or "",
                "pageUrl": attrs.get("hyperlink") or "",
                "listEntry": attrs.get("ListEntry"),
                "ngr": attrs.get("NGR") or "",
                "lat": rlat,
                "lon": rlon,
                "license": "OGL v3.0",
                "source": SOURCE_NHLE,
            }
        )
    return out


def query_canmore_near(lat: float, lon: float, *, distance_m: int = 5000) -> list[dict[str, Any]]:
    payload = _arcgis_query(
        CANMORE_MS,
        {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "distance": distance_m,
            "units": "esriSRUnit_Meter",
            "outFields": "NMRSNAME,ALTNAME,LICENCE,CANMOREID,URL,COUNTY,PARISH",
            "returnGeometry": "false",
            "f": "json",
        },
    )
    out: list[dict[str, Any]] = []
    for feat in payload.get("features") or []:
        attrs = feat.get("attributes") or {}
        lic = (attrs.get("LICENCE") or "").strip()
        if not license_allowed(lic):
            continue
        cid = attrs.get("CANMOREID")
        page = (attrs.get("URL") or "").strip()
        if cid and not page:
            page = f"https://www.trove.scot/site/{cid}"
        out.append(
            {
                "name": (attrs.get("NMRSNAME") or "").strip(),
                "altName": (attrs.get("ALTNAME") or "").strip(),
                "pageUrl": page,
                "canmoreId": cid,
                "location": f"{attrs.get('PARISH') or ''} {attrs.get('COUNTY') or ''}".strip(),
                "license": lic,
                "source": SOURCE_CANMORE,
                "spatially_prefiltered": True,
            }
        )
    return out


def query_cadw_near(lat: float, lon: float, *, distance_m: int = 8000) -> list[dict[str, Any]]:
    bbox = _wgs84_bbox(lat, lon, distance_m / 1000.0)
    params = urllib.parse.urlencode(
        {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeName": "inspire-wg:Cadw_ListedBuildings",
            "count": "25",
            "outputFormat": "application/json",
            "bbox": bbox,
        }
    )
    url = f"{CADW_WFS}?{params}"
    status, body, _ = _http_get(url, timeout=60)
    time.sleep(DELAY_S * 0.5)
    if status != 200:
        return []
    data = json.loads(body.decode("utf-8"))
    out: list[dict[str, Any]] = []
    for feat in data.get("features") or []:
        props = feat.get("properties") or {}
        name = (props.get("Name") or props.get("Name_cy") or "").strip()
        rec = props.get("RecordNumber")
        report = props.get("Report") or props.get("Report_welsh") or ""
        out.append(
            {
                "name": name,
                "pageUrl": report,
                "recordNumber": rec,
                "location": (props.get("Location") or "").strip(),
                "community": (props.get("Community") or "").strip(),
                "license": "OGL v3.0",
                "source": SOURCE_CADW,
                "spatially_prefiltered": True,
            }
        )
    return out


def _build_image_record(
    island: dict,
    *,
    image_url: str,
    page_url: str,
    license_str: str,
    source: str,
    source_ref: str,
    caption: str,
    attribution: str,
) -> dict[str, Any]:
    return {
        "url": image_url,
        "source": source,
        "sourceRef": source_ref,
        "sourcePageUrl": page_url,
        "license": license_str,
        "attribution": attribution,
        "caption": caption,
        "imageConfidence": "medium-high",
        "verifiedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }


def _try_records(
    island: dict,
    records: list[dict[str, Any]],
    cache: dict,
    *,
    live: bool,
) -> tuple[dict | None, str]:
    for rec in records:
        name = rec.get("name") or ""
        loc = rec.get("location") or rec.get("ngr") or ""
        rlat, rlon = rec.get("lat"), rec.get("lon")
        if not _name_and_place_match(
            island,
            name,
            record_lat=rlat,
            record_lon=rlon,
            location_text=loc,
            spatially_prefiltered=bool(rec.get("spatially_prefiltered")),
        ):
            continue
        lic = rec.get("license") or ""
        if not license_allowed(lic):
            continue
        page = (rec.get("pageUrl") or "").strip()
        if not page:
            continue
        page_meta = fetch_page_image(page, cache, live=live)
        if not page_meta or not page_meta.get("imageUrl"):
            continue
        img_url = page_meta["imageUrl"]
        lic_page = page_meta.get("license") or lic
        if not license_allowed(lic_page):
            continue
        src = rec.get("source") or "heritage-ogl"
        ref = f"{island.get('id')};{rec.get('listEntry') or rec.get('canmoreId') or rec.get('recordNumber') or name[:40]}"
        attr = {
            SOURCE_NHLE: "Historic England NHLE / Heritage Gateway (OGL v3.0)",
            SOURCE_CANMORE: "Historic Environment Scotland Canmore (OGL)",
            SOURCE_CADW: "Cadw Listed Buildings, Welsh Government (OGL v3.0)",
        }.get(src, "UK heritage open data")
        caption = f"{name} — {island.get('name', '')}"
        image_rec = _build_image_record(
            island,
            image_url=img_url,
            page_url=page,
            license_str=lic_page if "ogl" in lic_page.lower() else lic,
            source=src,
            source_ref=ref,
            caption=caption[:240],
            attribution=f"Photo via {attr} ({lic_page or lic})",
        )
        return image_rec, src
    return None, ""


def try_island(
    island: dict,
    cache: dict,
    *,
    live: bool,
    api_status: dict[str, Any],
) -> tuple[dict | None, str, dict[str, Any]]:
    notes: dict[str, Any] = {"candidates": 0, "sources_tried": []}
    lat, lon = _island_lat(island), _island_lon(island)
    if lat is None or lon is None:
        return None, "", notes

    nation = (island.get("nation") or "").strip().lower()
    dist_m = int(_geo_max_km(island) * 1000)

    if nation == "england" and api_status.get(SOURCE_NHLE, {}).get("status") == "ok":
        notes["sources_tried"].append(SOURCE_NHLE)
        recs = query_nhle_near(lat, lon, distance_m=dist_m)
        notes["candidates"] += len(recs)
        hit, via = _try_records(island, recs, cache, live=live)
        if hit:
            return hit, via, notes
        time.sleep(DELAY_S)

    if nation == "scotland" and api_status.get(SOURCE_CANMORE, {}).get("status") == "ok":
        notes["sources_tried"].append(SOURCE_CANMORE)
        recs = query_canmore_near(lat, lon, distance_m=dist_m)
        notes["candidates"] += len(recs)
        hit, via = _try_records(island, recs, cache, live=live)
        if hit:
            return hit, via, notes
        time.sleep(DELAY_S)

    if nation == "wales" and api_status.get(SOURCE_CADW, {}).get("status") == "ok":
        notes["sources_tried"].append(SOURCE_CADW)
        recs = query_cadw_near(lat, lon, distance_m=max(dist_m, 8000))
        notes["candidates"] += len(recs)
        hit, via = _try_records(island, recs, cache, live=live)
        if hit:
            return hit, via, notes
        time.sleep(DELAY_S)

    return None, "", notes


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage UK heritage OGL/CC island photos.")
    ap.add_argument("--limit", type=int, default=0, help="Max islands to try (0=all).")
    ap.add_argument("--named-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cache-only", action="store_true", help="Skip live API fetches.")
    ap.add_argument("--test", default="", help="Single island id.")
    args = ap.parse_args()

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    if not isinstance(islands, list):
        print("FATAL: islands.json is not a list", file=sys.stderr)
        return 2

    cache = v5._load(CACHE_PATH)
    live = not args.cache_only

    print("Probing heritage APIs…", file=sys.stderr)
    api_probe = probe_apis() if live else cache.get("api_probe") or {}
    if live:
        cache["api_probe"] = api_probe
        v5._save(CACHE_PATH, cache)
    for sid, meta in api_probe.items():
        print(f"  {sid}: {meta.get('status', meta)}", file=sys.stderr)

    sources_working = [
        sid
        for sid in (SOURCE_NHLE, SOURCE_CANMORE, SOURCE_CADW)
        if str(api_probe.get(sid, {}).get("status", "")).startswith("ok")
    ]
    sources_blocked = list(SOURCES_BLOCKED_STATIC)
    hg = api_probe.get(SOURCE_HG, {})
    if not str(hg.get("status", "")).startswith("ok") and not str(hg.get("status", "")).startswith("reachable"):
        sources_blocked.append(
            {
                "id": SOURCE_HG,
                "reason": f"National Heritage Gateway UI not machine-harvestable ({hg.get('status')}).",
            }
        )
    else:
        sources_blocked.append(
            {
                "id": SOURCE_HG,
                "reason": "No national JSON/SOAP image API with OGL attachments; NHLE ArcGIS used instead.",
            }
        )
    trove = api_probe.get(SOURCE_TROVE, {})
    if "403" in str(trove.get("status", "")):
        sources_blocked.append(
            {
                "id": SOURCE_TROVE,
                "reason": "trove.scot blocks automated thumbnail fetch; contractual licence per image.",
            }
        )

    if args.test:
        targets = [i for i in islands if i.get("id") == args.test]
        if not targets:
            print(f"FATAL: no island {args.test!r}", file=sys.stderr)
            return 2
    else:
        targets = [i for i in islands if _needs_image(i)]
        if args.named_only:
            named_ids = v5._load_named_index_ids()
            if not named_ids:
                print("FATAL: --named-only but islands_index missing", file=sys.stderr)
                return 2
            targets = [i for i in targets if i.get("id") in named_ids]
        # Prefer nations with working heritage APIs
        def _prio(i: dict) -> tuple[int, str]:
            n = (i.get("nation") or "").lower()
            tier = 0 if n in ("england", "scotland", "wales") else 2
            return (tier, i.get("name") or "")

        targets.sort(key=_prio)
        if args.limit:
            targets = targets[: args.limit]

    report: dict[str, Any] = {
        "script": "enrich_images_heritage_ogl.py",
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "args": vars(args),
        "api_probe": api_probe,
        "sources_working": sources_working,
        "sources_blocked": sources_blocked,
        "targets_considered": len(targets),
        "counts": {
            "staged": 0,
            "no_match": 0,
            "page_fetch_blocked": 0,
            "by_source": {SOURCE_NHLE: 0, SOURCE_CANMORE: 0, SOURCE_CADW: 0},
        },
        "adopted_sample": [],
        "no_match_sample": [],
    }

    adoptions: list[dict[str, Any]] = []
    staged = 0

    for n, isl in enumerate(targets, 1):
        if n % 40 == 0:
            print(f"  {n}/{len(targets)} staged={staged}", file=sys.stderr)

        rec, via, notes = try_island(isl, cache, live=live, api_status=api_probe)
        if not rec:
            report["counts"]["no_match"] += 1
            if len(report["no_match_sample"]) < 30:
                report["no_match_sample"].append(
                    {
                        "id": isl.get("id"),
                        "name": isl.get("name"),
                        "nation": isl.get("nation"),
                        "notes": notes,
                    }
                )
            continue

        staged += 1
        report["counts"]["staged"] += 1
        if via in report["counts"]["by_source"]:
            report["counts"]["by_source"][via] += 1

        row = {
            "id": isl["id"],
            "name": isl.get("name", ""),
            "via": via,
            "image_record": rec,
            "imageConfidence": rec.get("imageConfidence", "medium-high"),
            "source": rec.get("source"),
            "sourcePageUrl": rec.get("sourcePageUrl"),
            "license": rec.get("license"),
        }
        adoptions.append(row)
        if len(report["adopted_sample"]) < 25:
            report["adopted_sample"].append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "via": via,
                    "license": row["license"],
                    "sourcePageUrl": row["sourcePageUrl"],
                }
            )
        if args.dry_run or args.test:
            print(json.dumps(row, ensure_ascii=False, indent=2))

    if live:
        v5._save(CACHE_PATH, cache)

    if not args.dry_run:
        _atomic_write_json(
            STAGING,
            {
                "version": 1,
                "generatedAt": report["generatedAt"],
                "source": "heritage-ogl",
                "adoptions": adoptions,
            },
        )

    _atomic_write_json(REPORT, report)

    print(
        f"\nDone. staged={staged} no_match={report['counts']['no_match']} "
        f"by_source={report['counts']['by_source']}",
        file=sys.stderr,
    )
    print(f"APIs working: {', '.join(sources_working) or '(none)'}", file=sys.stderr)
    print(f"Staging → {STAGING.relative_to(ROOT)} ({len(adoptions)} rows)", file=sys.stderr)
    print(f"Report  → {REPORT.relative_to(ROOT)}", file=sys.stderr)
    print(staged)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
