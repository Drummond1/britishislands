#!/usr/bin/env python3
"""Flickr CC/OGL accounts: Natural England, NRW, NatureScot, JNCC."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
STAGING = DATA / "staging" / "adoptions" / "flickr-statutory.json"
CACHE = DATA / "cache_flickr_statutory.json"
REPORT = DATA / "image_enrichment_flickr_statutory_report.json"

ACCOUNTS = {
    "naturalengland": "39353554@N07",
    "naturalresourceswales": "95679720@N08",
    "naturescot": "141388163@N03",
    "jncc_uk": "141960297@N08",
}
# licence 4=CC BY, 5=CC BY-SA, 7=No known copyright, 9=CC0, 10=PD
LICENSES = "4,5,7,9,10"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from enrich_images_v5 import _load, _load_named_index_ids, _mentions, _name_variants, _save  # noqa: E402
from photo_geo_utils import haversine_km  # noqa: E402
from photo_staging_dual import dual_signal_ok, load_dotenv, save_staging  # noqa: E402

load_dotenv(ROOT / ".env.local")


def _flickr_search(api_key: str, user_id: str, text: str, lat: float, lon: float) -> list[dict]:
    params = {
        "method": "flickr.photos.search",
        "api_key": api_key,
        "user_id": user_id,
        "text": text,
        "lat": str(lat),
        "lon": str(lon),
        "radius": "2",
        "radius_units": "km",
        "license": LICENSES,
        "content_type": "1",
        "per_page": "15",
        "extras": "url_l,license,geo,description,tags",
        "format": "json",
        "nojsoncallback": "1",
    }
    url = "https://api.flickr.com/services/rest/?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "isles-of-britain/0.1"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    return (data.get("photos") or {}).get("photo") or []


def _licence_label(code: str) -> str:
    return {
        "4": "CC-BY 2.0",
        "5": "CC-BY-SA 2.0",
        "7": "Public Domain",
        "9": "CC0 1.0",
        "10": "Public Domain",
    }.get(str(code), "CC-BY 2.0")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--named-only", action="store_true", default=True)
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--delay", type=float, default=1.5)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    api_key = os.environ.get("FLICKR_API_KEY", "").strip()
    if not api_key:
        print("FLICKR_API_KEY missing in .env.local — skip", flush=True)
        REPORT.write_text(json.dumps({"error": "no FLICKR_API_KEY", "staged": 0}), encoding="utf-8")
        return 0

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    named = _load_named_index_ids() if args.named_only else set()
    pending = [i for i in islands if not (i.get("images") or [])]
    if args.named_only:
        pending = [i for i in pending if i.get("id") in named]
    pending = pending[: args.limit]

    cache = _load(CACHE)
    adoptions: list[dict] = []
    report = {"staged": 0, "by_account": {}, "adopted": []}

    for isl in pending:
        lat, lon = isl.get("lat"), isl.get("lng") or isl.get("lon")
        if lat is None or lon is None:
            continue
        name = isl.get("name", "")
        variants = _name_variants(isl)
        for acct, uid in ACCOUNTS.items():
            ck = f"{uid}|{name}"
            if ck in cache:
                photos = cache[ck]
            else:
                try:
                    photos = _flickr_search(api_key, uid, name, float(lat), float(lon))
                    cache[ck] = photos
                    _save(CACHE, cache)
                except Exception:
                    time.sleep(args.delay)
                    continue
                time.sleep(args.delay)
            for ph in photos:
                title = ph.get("title") or ""
                desc = ph.get("description", {}).get("_content", "") if isinstance(ph.get("description"), dict) else ""
                blob = f"{title} {desc} {ph.get('tags','')}"
                plat = ph.get("latitude")
                plon = ph.get("longitude")
                ok, ver = dual_signal_ok(
                    isl, title=title, blob=blob,
                    result_lat=float(plat) if plat else None,
                    result_lon=float(plon) if plon else None,
                    mentions_fn=_mentions,
                    name_variants_fn=lambda _: variants,
                    haversine_km_fn=haversine_km,
                )
                if not ok:
                    continue
                url = ph.get("url_l") or ""
                if not url:
                    continue
                pid = ph.get("id")
                rec = {
                    "url": url,
                    "source": "flickr-statutory",
                    "sourceRef": f"{acct}:{pid}",
                    "sourcePageUrl": f"https://www.flickr.com/photos/{ph.get('owner')}/{pid}",
                    "license": _licence_label(ph.get("license", "")),
                    "attribution": f"{title} / {acct} on Flickr",
                    "imageConfidence": "high",
                    "dualSignal": True,
                }
                adoptions.append({
                    "id": isl["id"],
                    "islandId": isl["id"],
                    "image_record": rec,
                    "imageConfidence": "high",
                    "account": acct,
                    "dualSignal": True,
                })
                report["adopted"].append({"id": isl["id"], "account": acct})
                report["by_account"][acct] = report["by_account"].get(acct, 0) + 1
                break
            else:
                continue
            break

    report["staged"] = len(adoptions)
    if not args.dry_run:
        save_staging(STAGING, adoptions)
        REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Flickr statutory staged: {len(adoptions)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
