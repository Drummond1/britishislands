#!/usr/bin/env python3
"""Wikidata nearby entities (lighthouse, NNR, castle) that have P18 landscape photos."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
STAGING = DATA / "staging" / "adoptions" / "wd-nearby-p18.json"
CACHE = DATA / "cache_wd_nearby_p18.json"
COMMONS_CACHE = DATA / "cache_commons_meta.json"
REPORT = DATA / "image_enrichment_wd_nearby_p18_report.json"
USER_AGENT = "isles-of-britain/0.1 (wd-nearby-p18)"
RADIUS_KM = 0.8

NEARBY_TYPES = (
    "wd:Q39715",   # lighthouse
    "wd:Q23413",   # castle
    "wd:Q179049",  # nature reserve
    "wd:Q57821",   # fortification
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from enrich_images_v5 import (  # noqa: E402
    _canon,
    _load,
    _load_named_index_ids,
    _save,
    build_image_record_from_commons,
    fetch_commons_meta,
)
from urllib.parse import unquote  # noqa: E402
from photo_geo_utils import haversine_km  # noqa: E402
from photo_staging_dual import save_staging  # noqa: E402


def _around_query(lat: float, lon: float, radius_km: float) -> str:
    point = f"Point({lon} {lat})"
    types = " ".join(NEARBY_TYPES)
    return f"""
SELECT ?near ?nearLabel ?img WHERE {{
  SERVICE wikibase:around {{
    ?near wdt:P625 ?coord .
    bd:serviceParam wikibase:center "{point}"^^geo:wktLiteral ;
                    wikibase:radius "{radius_km}" .
  }}
  ?near wdt:P18 ?img .
  VALUES ?t {{ {types} }}
  ?near wdt:P31/wdt:P279* ?t .
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}} LIMIT 20
"""


def _commons_filename(img_url: str) -> str:
    if "/wiki/File:" in img_url:
        return unquote(img_url.split("/wiki/File:", 1)[-1])
    if img_url.startswith("http") and "Special:FilePath/" in img_url:
        return unquote(img_url.rsplit("/", 1)[-1])
    return ""


def _sparql(query: str) -> list[dict]:
    body = urllib.parse.urlencode({"query": query}).encode()
    req = urllib.request.Request(
        "https://query.wikidata.org/sparql",
        data=body,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/sparql-results+json",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    return data.get("results", {}).get("bindings", [])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--named-only", action="store_true", default=True)
    ap.add_argument("--limit", type=int, default=250)
    ap.add_argument("--delay", type=float, default=2.5)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    named = _load_named_index_ids() if args.named_only else set()
    pending = [i for i in islands if not (i.get("images") or [])]
    if args.named_only:
        pending = [i for i in pending if i.get("id") in named]
    pending = pending[: args.limit]

    cache = _load(CACHE)
    commons_cache = _load(COMMONS_CACHE)
    adoptions: list[dict] = []
    report = {"staged": 0, "adopted": [], "skipped": []}

    for isl in pending:
        lat, lon = isl.get("lat"), isl.get("lng") or isl.get("lon")
        if lat is None or lon is None:
            continue
        ck = f"{isl['id']}|{RADIUS_KM}"
        if ck in cache:
            rows = cache[ck]
        else:
            try:
                rows = _sparql(_around_query(float(lat), float(lon), RADIUS_KM))
                cache[ck] = rows
                _save(CACHE, cache)
            except Exception as exc:
                report["skipped"].append({"id": isl["id"], "error": str(exc)})
                time.sleep(args.delay)
                continue
            time.sleep(args.delay)

        best = None
        for row in rows:
            img_url = (row.get("img") or {}).get("value", "")
            fname = _commons_filename(img_url)
            if not fname:
                continue
            canon = _canon(fname)
            meta = fetch_commons_meta([canon], commons_cache).get(canon, {})
            if not meta or not meta.get("url"):
                continue
            mlat = meta.get("lat")
            mlon = meta.get("lon")
            if mlat is not None and mlon is not None:
                d = haversine_km(float(lat), float(lon), float(mlat), float(mlon))
                if d > RADIUS_KM:
                    continue
            near = (row.get("near") or {}).get("value", "").rsplit("/", 1)[-1]
            if best is None:
                best = (near, fname, meta)
        if not best:
            report["skipped"].append({"id": isl["id"]})
            continue
        near, fname, meta = best
        rec = build_image_record_from_commons(
            fname,
            meta,
            source="wikidata-nearby-p18",
            source_ref=near,
        )
        if rec:
            rec["dualSignal"] = True
            adoptions.append({
                "id": isl["id"],
                "islandId": isl["id"],
                "image_record": rec,
                "nearbyQid": near,
                "dualSignal": True,
                "imageConfidence": "medium-high",
            })
            report["adopted"].append({"id": isl["id"], "near": near, "file": fname})

    report["staged"] = len(adoptions)
    if not args.dry_run:
        _save(COMMONS_CACHE, commons_cache)
        save_staging(STAGING, adoptions)
        REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"WD nearby P18 staged: {len(adoptions)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
