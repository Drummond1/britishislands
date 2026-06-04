#!/usr/bin/env python3
"""Stage OGL / Creative Commons photos from People's Collection Wales (discover HTML).

Wales atlas islands only (``nation: wales``). Uses the public discover UI with the
``keywords`` query parameter (not ``search``), then parses item pages for
``field-licence-type``, geolocation, and image URL. Only Open Government Licence
and Creative Commons (no NC/ND, no Creative Archive — non-commercial) are staged.

Run::

    python3 scripts/enrich_images_peoples_collection_wales.py --limit 100
    python3 scripts/enrich_images_peoples_collection_wales.py --test skomer

Outputs (staging only)::

    data/staging/adoptions/pcw.json
    data/cache_peoples_collection_wales.json
    data/image_enrichment_peoples_collection_wales_report.json
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
STAGING = DATA / "staging" / "adoptions" / "pcw.json"
CACHE = DATA / "cache_peoples_collection_wales.json"
REPORT = DATA / "image_enrichment_peoples_collection_wales_report.json"

DISCOVER = "https://www.peoplescollection.wales/discover"
ITEM_BASE = "https://www.peoplescollection.wales/items/"
USER_AGENT = "isles-of-britain/0.1 pcw-enrichment"
DEFAULT_DELAY_S = 1.0
GEO_MAX_KM = 12.0
RESULTS_PER_QUERY = 12

_NON_PHOTO_RE = re.compile(
    r"(?:^|[_ \-\(\[])"
    r"(?:flag|coat[_ \-]of[_ \-]arms|logo|map|diagram|chart|icon|badge|"
    r"illustration|drawing|cartoon|clipart|vector|svg|portrait|document|"
    r"brochure|program|ledger|memorial)"
    r"(?:$|[_ \-\)\]])",
    re.IGNORECASE,
)

sys.path.insert(0, str(ROOT / "scripts"))
from enrich_images_v5 import (  # noqa: E402
    _haversine_km,
    _load,
    _load_named_index_ids,
    _mentions,
    _name_variants,
    _save,
    _strip_html,
)


def _open_html(url: str, delay_s: float) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read().decode("utf-8", "replace")
    time.sleep(delay_s)
    return body


def _island_lat(island: dict) -> float | None:
    lat = island.get("lat")
    return float(lat) if isinstance(lat, (int, float)) else None


def _island_lon(island: dict) -> float | None:
    lng = island.get("lng")
    if lng is None:
        lng = island.get("lon")
    return float(lng) if isinstance(lng, (int, float)) else None


def _licence_ok(label: str) -> tuple[bool, str]:
    low = (label or "").strip().lower()
    if not low:
        return False, ""
    if "creative archive" in low:
        return False, "creative-archive-nc"
    if "non-commercial" in low or "non commercial" in low:
        return False, "non-commercial"
    if "all rights" in low:
        return False, "arr"
    if "open government" in low or low.startswith("ogl"):
        return True, "OGL"
    if "creative commons" in low or re.search(r"\bcc[\s\-]?by", low):
        if "nc" in low or "nd" in low:
            return False, "cc-restricted"
        if "cc0" in low or "cc-0" in low:
            return True, "CC0"
        if "sa" in low:
            return True, "CC-BY-SA"
        return True, "CC-BY"
    if "public domain" in low:
        return True, "Public Domain"
    return False, "unknown-licence"


def _parse_discover(html: str) -> list[tuple[str, str]]:
    """Return [(item_id, card_title), ...] from discover HTML."""
    rows: list[tuple[str, str]] = []
    for m in re.finditer(
        r'href="https://www\.peoplescollection\.wales/items/(\d+)"[^>]*>\s*<span>([^<]+)</span>',
        html,
        re.I,
    ):
        rows.append((m.group(1), _strip_html(m.group(2))))
    if rows:
        return rows
    for m in re.finditer(r'href="(/items/(\d+))"[^>]*>\s*<span>([^<]+)</span>', html, re.I):
        rows.append((m.group(2), _strip_html(m.group(3))))
    return rows


def _field_anchor(html: str, field: str) -> str:
    m = re.search(
        rf'field--name-field-{field}[^>]*>.*?field__item[^>]*>\s*<a[^>]*>([^<]+)</a>',
        html,
        re.S | re.I,
    )
    if m:
        return _strip_html(m.group(1))
    m = re.search(
        rf'field--name-field-{field}[^>]*>.*?field__item[^>]*>([^<]+)',
        html,
        re.S | re.I,
    )
    return _strip_html(m.group(1)) if m else ""


def _parse_item_page(html: str, item_id: str) -> dict[str, Any]:
    licence = _field_anchor(html, "licence-type")
    description = _field_anchor(html, "english-description")
    creator = _field_anchor(html, "creator") or "Unknown"
    title = ""
    m = re.search(r'<h1[^>]*class="[^"]*page-title[^"]*"[^>]*>\s*([^<]+)', html, re.S)
    if m:
        title = _strip_html(m.group(1))
    if not title:
        m = re.search(r"<title>([^<|]+)", html)
        if m:
            title = _strip_html(m.group(1))

    lat = lon = None
    m = re.search(r'"lat"\s*:\s*([0-9.\-]+)\s*,\s*"lng"\s*:\s*([0-9.\-]+)', html)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))

    img_path = ""
    for pat in (
        r'styles/widescreen[^"\']+public/images/[^"\']+',
        r'styles/3_2/public/images/[^"\']+',
        r'sites/default/files/styles/[^"\']+public/images/[^"\']+',
    ):
        m = re.search(pat, html)
        if m:
            img_path = m.group(0).replace("&amp;", "&")
            break
    if img_path.startswith("/"):
        img_url = "https://www.peoplescollection.wales" + img_path
    elif img_path:
        img_url = "https://www.peoplescollection.wales/" + img_path.lstrip("/")
    else:
        img_url = ""

    return {
        "itemId": item_id,
        "title": title,
        "description": description,
        "creator": creator,
        "licenceLabel": licence,
        "lat": lat,
        "lon": lon,
        "imageUrl": img_url,
        "pageUrl": f"{ITEM_BASE}{item_id}",
    }


def _build_image_record(meta: dict, licence_code: str, island: dict) -> dict | None:
    url = (meta.get("imageUrl") or "").strip()
    if not url or _NON_PHOTO_RE.search(meta.get("title", "") + " " + url):
        return None
    title = meta.get("title") or island.get("name", "")
    lic_display = meta.get("licenceLabel") or licence_code
    return {
        "url": url,
        "source": "peoples-collection-wales",
        "sourceRef": f"pcw:item:{meta.get('itemId')}",
        "sourcePageUrl": meta.get("pageUrl", ""),
        "license": lic_display,
        "attribution": (
            f"Photo by {meta.get('creator', 'Unknown')}, "
            f"People's Collection Wales ({lic_display})"
        ),
        "caption": meta.get("description") or title,
        "imageConfidence": "high",
        "verifiedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }


def fetch_discover(
    query: str,
    cache: dict,
    delay_s: float,
) -> list[tuple[str, str]]:
    bucket = cache.setdefault("discover", {})
    if query in bucket:
        return [(r["id"], r["title"]) for r in bucket[query].get("results", [])]

    params = urllib.parse.urlencode({"keywords": query, "type[item]": "item"})
    html = _open_html(f"{DISCOVER}?{params}", delay_s)
    results = _parse_discover(html)
    bucket[query] = {
        "fetched": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "results": [{"id": i, "title": t} for i, t in results],
    }
    _save(CACHE, cache)
    return results


def fetch_item(item_id: str, cache: dict, delay_s: float) -> dict[str, Any]:
    bucket = cache.setdefault("items", {})
    if item_id in bucket:
        return bucket[item_id]
    html = _open_html(f"{ITEM_BASE}{item_id}", delay_s)
    meta = _parse_item_page(html, item_id)
    bucket[item_id] = meta
    _save(CACHE, cache)
    return meta


def try_pcw_photo(
    island: dict,
    cache: dict,
    delay_s: float,
) -> tuple[dict | None, dict[str, Any]]:
    variants = _name_variants(island)
    queries = [island.get("name", "").strip()]
    names = island.get("names") or {}
    for key in ("cy", "en"):
        alt = (names.get(key) or "").strip()
        if alt and alt not in queries:
            queries.append(alt)
    queries = [q for q in queries if q and len(q) >= 4][:3]

    lat_i, lon_i = _island_lat(island), _island_lon(island)
    notes: dict[str, Any] = {"queries": queries, "candidates": []}

    for query in queries:
        cards = fetch_discover(query, cache, delay_s)[:RESULTS_PER_QUERY]
        for item_id, card_title in cards:
            text = f"{card_title}"
            if not _mentions(text, variants):
                notes["candidates"].append({
                    "itemId": item_id,
                    "reason": "title-no-name-match",
                    "title": card_title,
                })
                continue
            meta = fetch_item(item_id, cache, delay_s)
            ok, lic_code = _licence_ok(meta.get("licenceLabel", ""))
            if not ok:
                notes["candidates"].append({
                    "itemId": item_id,
                    "reason": f"licence-blocked:{lic_code}",
                    "licence": meta.get("licenceLabel"),
                })
                continue
            if lat_i is not None and lon_i is not None:
                lat_m, lon_m = meta.get("lat"), meta.get("lon")
                if lat_m is not None and lon_m is not None:
                    km = _haversine_km(lat_i, lon_i, lat_m, lon_m)
                    if km > GEO_MAX_KM:
                        notes["candidates"].append({
                            "itemId": item_id,
                            "reason": f"geo-{km:.1f}km",
                        })
                        continue
            rec = _build_image_record(meta, lic_code, island)
            if rec:
                notes["chosen"] = item_id
                return rec, notes
            notes["candidates"].append({
                "itemId": item_id,
                "reason": "no-image-url-or-non-photo",
            })
    return None, notes


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--test", metavar="ID")
    p.add_argument(
        "--include-unnamed",
        action="store_true",
        help="Include islands not in islands_index.json (default: named only).",
    )
    p.add_argument("--delay", type=float, default=DEFAULT_DELAY_S)
    args = p.parse_args()
    delay_s = max(0.3, float(args.delay))

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    pending = [
        i for i in islands
        if not (i.get("images") or [])
        and (i.get("nation") or "").strip().lower() == "wales"
    ]
    if not args.include_unnamed:
        named_ids = _load_named_index_ids()
        if named_ids:
            pending = [i for i in pending if i.get("id") in named_ids]
    if args.test:
        pending = [i for i in islands if i.get("id") == args.test]
    if args.limit:
        pending = pending[: args.limit]

    cache = _load(CACHE)
    report: dict[str, Any] = {
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "args": vars(args),
        "pending": len(pending),
        "adopted": [],
        "rejected": [],
        "licence_policy": "OGL and Creative Commons only; Creative Archive excluded (NC)",
    }
    print(f"Pending Wales islands without images: {len(pending):,}", flush=True)

    staged: list[dict[str, Any]] = []
    n_adopted = 0
    for idx, isl in enumerate(pending, 1):
        rec, notes = try_pcw_photo(isl, cache, delay_s)
        if rec:
            entry = {
                "id": isl["id"],
                "name": isl.get("name", ""),
                "imageConfidence": "high",
                "source": "peoples-collection-wales",
                "sourceRef": rec.get("sourceRef"),
                "license": rec.get("license"),
                "sourcePageUrl": rec.get("sourcePageUrl"),
                "image": rec,
                "notes": notes,
            }
            staged.append(entry)
            report["adopted"].append(entry)
            n_adopted += 1
            print(f"  ✓ {isl['id']:40s} → {rec.get('license', '')}", flush=True)
        else:
            report["rejected"].append({
                "id": isl["id"],
                "name": isl.get("name", ""),
                "notes": notes,
            })
        if idx % 25 == 0:
            print(f"  … {idx}/{len(pending)}", flush=True)

    STAGING.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pipeline": "enrich_images_peoples_collection_wales",
        "attempted": len(pending),
        "staged_count": n_adopted,
        "adoptions": staged,
    }
    STAGING.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    report["staged_total"] = n_adopted
    _save(REPORT, report)

    print(f"Staging → {STAGING.relative_to(ROOT)} ({n_adopted:,})")
    print(f"Report  → {REPORT.relative_to(ROOT)}")
    return n_adopted


if __name__ == "__main__":
    count = main()
    print(f"adoption_count={count}")
    raise SystemExit(0)
