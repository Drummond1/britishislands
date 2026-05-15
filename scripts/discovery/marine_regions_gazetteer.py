"""Marine Regions gazetteer — island-type points in the UK / Ireland bbox (CC-BY).

Uses the public REST endpoint documented at
https://www.marineregions.org/gazetteer.php?p=webservices

We sample a coarse WGS84 grid and keep only records whose ``placeType`` is
exactly ``Island`` (filters out seas, EEZs, archipelagos, etc.).  In practice
the lat/long endpoint often returns administrative/marine regions inside the
UK bbox; genuine islets may appear under other types or not at all in this
view, so this pass may yield **zero** usable points while still caching the
grid for transparency.  Results are
cached under ``data/cache_discovery_marine_regions.json`` so re-runs are polite
to marineregions.org.

Licence: Marine Regions gazetteer products are CC-BY (see project site).
"""

from __future__ import annotations

import sys
import time
from typing import Any

from . import common as c

CACHE_PATH = c.DATA / "cache_discovery_marine_regions.json"
MR_BASE = "https://www.marineregions.org/mrgid/"
MR_ABOUT = "https://www.marineregions.org/about.php"

CACHE_VERSION = 2

# ~1.5° lat × 2.5° lng ≈ 55 cells over the project bbox; radius 0.9° overlaps
# cells so we do not miss narrow sounds between islands.
LAT_STEP = 1.5
LNG_STEP = 2.5
RADIUS_DEG = 0.9


def _grid_cells() -> list[tuple[float, float]]:
    s, w, n, e = c.UK_BBOX
    out: list[tuple[float, float]] = []
    lat = s
    while lat <= n + 1e-6:
        lng = w
        while lng <= e + 1e-6:
            out.append((round(lat, 3), round(min(179.0, max(-179.0, lng)), 3)))
            lng += LNG_STEP
        lat += LAT_STEP
    return out


def _cell_key(lat: float, lng: float) -> str:
    return f"{lat:.3f},{lng:.3f}"


def _row_to_candidate(row: dict[str, Any]) -> dict[str, Any] | None:
    if (row.get("placeType") or "").strip().lower() != "island":
        return None
    name = (row.get("preferredGazetteerName") or "").strip()
    if len(name) < 2:
        return None
    try:
        lat = float(row.get("latitude"))
        lng = float(row.get("longitude"))
    except (TypeError, ValueError):
        return None
    if not c.in_remit(lat, lng):
        return None
    mrgid = row.get("MRGID") or row.get("accepted")
    if mrgid is None:
        return None
    mrgid = int(mrgid)
    return {
        "candidateId": f"mr-gaz-{mrgid}",
        "name": name,
        "lat": round(lat, 5),
        "lng": round(lng, 5),
        "nation": c.nation_for(lat, lng),
        "featureKind": "island",
        "osmType": None,
        "osmId": None,
        "osmPlace": "island",
        "wikidata": "",
        "wikipedia": "",
        "aliases": [],
        "tags": ["island", "marine-regions"],
        "scanConfidence": "medium",
        "sourceHints": [
            {
                "name": "Marine Regions Gazetteer",
                "url": f"{MR_BASE}{mrgid}",
                "license": "CC-BY-4.0",
            },
            {
                "name": "Marine Regions (about / citation)",
                "url": MR_ABOUT,
                "license": "CC-BY-4.0",
            },
        ],
    }


def collect_candidates(*, refresh: bool = False) -> list[dict[str, Any]]:
    cache: dict[str, Any] = c.load_json(CACHE_PATH, {})
    cells: dict[str, list[dict[str, Any]]] = cache.get("cells") or {}
    expected = len(_grid_cells())
    if (
        not refresh
        and cache.get("version") == CACHE_VERSION
        and cache.get("complete")
        and len(cells) >= expected
    ):
        merged: dict[int, dict[str, Any]] = {}
        for _k, rows in cells.items():
            for row in rows:
                if not isinstance(row, dict):
                    continue
                cand = _row_to_candidate(row)
                if not cand:
                    continue
                mrgid = int((row.get("MRGID") or row.get("accepted") or 0))
                if mrgid and mrgid not in merged:
                    merged[mrgid] = cand
        out = list(merged.values())
        print(f"→ Marine Regions: cached ({len(out)} island points)", file=sys.stderr)
        return out

    print("→ Marine Regions: sampling gazetteer grid (first run may take ~30s)", file=sys.stderr)
    cells = {}
    grid = _grid_cells()
    for i, (lat, lng) in enumerate(grid, start=1):
        url = (
            "https://www.marineregions.org/rest/"
            f"getGazetteerRecordsByLatLong.json/{lat}/{lng}/{RADIUS_DEG}/"
        )
        try:
            payload = c.fetch_json(url, timeout=120)
        except Exception as exc:
            print(f"  cell {lat},{lng}: {exc!r}", file=sys.stderr)
            cells[_cell_key(lat, lng)] = []
            time.sleep(c.DELAY_S)
            continue
        if not isinstance(payload, list):
            cells[_cell_key(lat, lng)] = []
        else:
            cells[_cell_key(lat, lng)] = payload
        if i % 10 == 0:
            print(f"  Marine Regions: {i}/{len(grid)} cells", file=sys.stderr)
        time.sleep(max(c.DELAY_S, 0.22))

    cache = {
        "version": CACHE_VERSION,
        "complete": True,
        "fetched": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "radiusDeg": RADIUS_DEG,
        "cells": cells,
    }
    c.save_json(CACHE_PATH, cache)

    merged: dict[int, dict[str, Any]] = {}
    for _k, rows in cells.items():
        for row in rows:
            if not isinstance(row, dict):
                continue
            cand = _row_to_candidate(row)
            if not cand:
                continue
            mrgid = int(row.get("MRGID") or row.get("accepted") or 0)
            if mrgid:
                merged.setdefault(mrgid, cand)
    out = list(merged.values())
    print(f"  Marine Regions: {len(out)} unique island gazetteer points", file=sys.stderr)
    return out
