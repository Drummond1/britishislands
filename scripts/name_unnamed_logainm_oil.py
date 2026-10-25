#!/usr/bin/env python3
"""Spatial join unnamed Irish islands to Logainm OIL (oileán) records (#31).

Requires ``LOGAINM_API_KEY`` or ``GAOIS_API_KEY`` in ``.env.local``.
CC-BY 4.0; Tier A gate ≤500 m (Logainm point geometry).

Run::

    python3 scripts/name_unnamed_logainm_oil.py
    python3 scripts/name_unnamed_logainm_oil.py --refresh --max-distance-m 400
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ENV_LOCAL = ROOT / ".env.local"
STAGING = DATA / "staging" / "name_proposals" / "logainm-oil.json"
CACHE = DATA / "cache_logainm_oil.json"
REPORT = DATA / "name_proposals_logainm_oil_report.json"
LOGAINM_API = "https://www.logainm.ie/api/v1.0"
USER_AGENT = "isles-of-britain/0.1 (name-logainm-oil)"
DELAY = 1.2
PER_PAGE = 200

sys.path.insert(0, str(ROOT / "scripts"))
from name_staging_utils import (  # noqa: E402
    build_proposal,
    load_dotenv,
    load_unnamed,
    nearest_in_index,
    save_staging,
    spatial_index,
)


def _api_key() -> str:
    return (
        os.environ.get("LOGAINM_API_KEY")
        or os.environ.get("GAOIS_API_KEY")
        or ""
    ).strip()


def _get_json(path: str, params: dict, api_key: str) -> Any:
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{LOGAINM_API}/{path}?{qs}",
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def _load_cache() -> dict:
    if CACHE.is_file():
        try:
            return json.loads(CACHE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def _save_cache(cache: dict) -> None:
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _parse_place(row: dict) -> dict[str, Any] | None:
    geo = row.get("geography") or row.get("geo") or {}
    lat = geo.get("latitude") or geo.get("lat")
    lon = geo.get("longitude") or geo.get("lon") or geo.get("lng")
    if lat is None or lon is None:
        return None
    name = (
        row.get("placename")
        or row.get("name")
        or row.get("Name")
        or row.get("nameEnglish")
        or ""
    ).strip()
    if not name:
        return None
    ga = (row.get("nameIrish") or row.get("nameGaeilge") or row.get("placenameIrish") or "").strip()
    alternates = {"ga": ga} if ga and ga != name else {}
    pid = row.get("id") or row.get("placeID") or row.get("PlaceID")
    return {
        "name": name,
        "lat": float(lat),
        "lon": float(lon),
        "placeId": pid,
        "alternates": alternates,
        "url": f"https://www.logainm.ie/en/{pid}" if pid else "https://www.logainm.ie/",
    }


def _fetch_oil_bulk(api_key: str, cache: dict, *, refresh: bool) -> list[dict[str, Any]]:
    if cache.get("places") and not refresh:
        return cache["places"]

    places: list[dict[str, Any]] = []
    page = 1
    while True:
        params = {
            "CategoryID": "OIL",
            "Page": page,
            "PerPage": PER_PAGE,
        }
        try:
            payload = _get_json("", params, api_key)
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and page == 1:
                # Fallback: feature filter used by some API versions
                params = {"FeatureID": "OIL", "Page": page, "PerPage": PER_PAGE}
                payload = _get_json("", params, api_key)
            else:
                raise
        rows = payload if isinstance(payload, list) else (
            payload.get("places") or payload.get("results") or payload.get("data") or []
        )
        if not rows:
            break
        for row in rows:
            if not isinstance(row, dict):
                continue
            pt = _parse_place(row)
            if pt:
                places.append(pt)
        print(f"  Logainm OIL page {page}: +{len(rows)} rows ({len(places)} parsed)", flush=True)
        if len(rows) < PER_PAGE:
            break
        page += 1
        time.sleep(DELAY)

    cache["places"] = places
    cache["fetchedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _save_cache(cache)
    return places


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-distance-m", type=float, default=500.0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    load_dotenv(ENV_LOCAL)
    api_key = _api_key()
    if not api_key:
        print("LOGAINM_API_KEY or GAOIS_API_KEY missing in .env.local — skip", file=sys.stderr)
        return 0

    cache = _load_cache()
    try:
        points = _fetch_oil_bulk(api_key, cache, refresh=args.refresh)
    except Exception as exc:
        print(f"Logainm fetch failed: {exc}", file=sys.stderr)
        return 1

    pending = load_unnamed(nation="Ireland") + load_unnamed(nation="Northern Ireland")
    if args.limit:
        pending = pending[: args.limit]

    index = spatial_index(points, lat_key="lat", lon_key="lon", cell=0.01)
    proposals: list[dict] = []
    report: dict[str, Any] = {
        "logainmPlaces": len(points),
        "pending": len(pending),
        "staged": 0,
        "adopted": [],
        "skipped": [],
    }

    print(f"Logainm OIL join: {len(points):,} places × {len(pending):,} unnamed IE/NI", flush=True)
    for isl in pending:
        lat, lon = isl.get("lat"), isl.get("lng") or isl.get("lon")
        if lat is None or lon is None:
            continue
        hit, dist_m = nearest_in_index(
            float(lat), float(lon), index, max_m=args.max_distance_m, cell=0.01,
        )
        if not hit:
            report["skipped"].append({"id": isl["id"]})
            continue
        row = build_proposal(
            isl,
            proposed_name=hit["name"],
            source="logainm-oil",
            licence="CC-BY 4.0",
            source_page_url=hit.get("url", "https://www.logainm.ie/"),
            confidence_tier="A",
            name_confidence="high",
            distance_m=dist_m,
            source_ref=str(hit.get("placeId") or ""),
            alternate_names=hit.get("alternates") or {},
        )
        if row:
            proposals.append(row)
            report["adopted"].append({"id": isl["id"], "name": hit["name"], "distanceM": dist_m})
            print(f"  staged {isl['id']} ← {hit['name']} ({dist_m:.0f} m)", flush=True)

    report["staged"] = len(proposals)
    if not args.dry_run:
        save_staging(STAGING, proposals)
        REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Staged: {len(proposals)} / {len(pending)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
