#!/usr/bin/env python3
"""
One-shot script: load ``data/coastline_raw.json`` (OSM ``natural=coastline``
ways for the UK/Ireland bounding box), polygonise them into land polygons,
and pickle the result to ``data/land_polygons.pickle`` for fast reuse by
``scripts/reclassify_islands.py`` Tier 2.

This is a heavy one-time cost so we factor it out of the classifier.
Subsequent reclassify runs just `pickle.load` the result in a second.

Run:
    python3 scripts/build_land_polygons.py            # full build
    python3 scripts/build_land_polygons.py --check    # verify cached pickle
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import sys
import time
from pathlib import Path

from shapely.geometry import LineString, MultiPolygon, Polygon, Point
from shapely.ops import polygonize, unary_union

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
COAST = DATA / "coastline_raw.json"
OUT = DATA / "land_polygons.pickle"
MAINLAND_OUT = DATA / "mainland_polygons.pickle"

# Mainland = land polygons larger than this many km².  In the British-Isles
# bbox, only Great Britain (~218k km²) and Ireland (~83k km²) clear this
# threshold; the next-biggest is Lewis & Harris at ~2,140 km².  An island
# whose centroid sits inside the mainland polygon is necessarily inland
# (river / lake / canal), because the OSM `natural=coastline` mask does
# NOT cut holes for inland freshwater.
MAINLAND_AREA_KM2 = 5_000


def build_lines(elements: list[dict]) -> list[LineString]:
    nodes = {}
    for e in elements:
        if e["type"] == "node":
            nodes[e["id"]] = (e["lon"], e["lat"])
    lines: list[LineString] = []
    for e in elements:
        if e["type"] != "way":
            continue
        coords = []
        for nid in e.get("nodes") or []:
            if nid in nodes:
                coords.append(nodes[nid])
        if len(coords) >= 2:
            try:
                lines.append(LineString(coords))
            except Exception:
                continue
    return lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="Load the cached pickle and run a self-test")
    args = parser.parse_args()

    if args.check:
        if not OUT.exists():
            print(f"FATAL: {OUT} not found; run without --check first", file=sys.stderr)
            return 2
        t0 = time.time()
        land = pickle.load(open(OUT, "rb"))
        print(f"Loaded pickle in {time.time()-t0:.1f}s; {len(getattr(land,'geoms',[land]))} all-land component(s)")
        if MAINLAND_OUT.exists():
            mainland = pickle.load(open(MAINLAND_OUT, "rb"))
            print(f"  mainland pickle: {len(getattr(mainland,'geoms',[mainland]))} component(s)")
        else:
            mainland = None
            print("  mainland pickle MISSING")
        # Self-test: random known points
        # (all-land, mainland) expected values
        SAMPLES = [
            # name,                              lat,      lng,      all_land, mainland
            ("London (Tower Bridge)",            51.5055,  -0.0754,  True,     True),
            ("Atlantic west of Cornwall",        49.0,    -10.0,     False,    False),
            ("North Sea off Aberdeen",           57.2,     0.0,      False,    False),
            ("Glasgow city centre",              55.8642, -4.2518,   True,     True),
            ("Loch Ness centre",                 57.3229, -4.4244,   True,     True),
            ("Iona centroid (real island)",      56.330,  -6.410,    True,     False),
            ("Lewis & Harris centroid",          58.133,  -6.658,    True,     False),
            ("Bodinbo Island (river island)",    55.916,  -4.460,    True,     True),
            ("Andersey Island (river island)",   51.664,  -1.272,    True,     True),
            ("Channel Islands (Jersey)",         49.214,  -2.133,    True,     False),
        ]
        for name, lat, lng, want_all, want_main in SAMPLES:
            pt = Point(lng, lat)
            got_all = land.contains(pt)
            got_main = mainland.contains(pt) if mainland is not None else None
            ok_all = "✓" if got_all == want_all else "✗"
            ok_main = "✓" if got_main == want_main else "✗"
            print(f"  {ok_all}{ok_main}  {name:35s}  all={got_all} main={got_main} (expected {want_all},{want_main})")
        return 0

    print(f"Loading coastline payload from {COAST.name}…", flush=True)
    t0 = time.time()
    data = json.loads(COAST.read_text(encoding="utf-8"))
    print(f"  done in {time.time()-t0:.1f}s; {len(data.get('elements') or [])} elements", flush=True)

    print("Building LineStrings…", flush=True)
    t0 = time.time()
    lines = build_lines(data.get("elements") or [])
    print(f"  done in {time.time()-t0:.1f}s; {len(lines):,} lines", flush=True)

    print("unary_union(lines)…", flush=True)
    t0 = time.time()
    merged = unary_union(lines)
    print(f"  done in {time.time()-t0:.1f}s", flush=True)

    print("polygonize(merged)…", flush=True)
    t0 = time.time()
    polys = list(polygonize(merged))
    print(f"  done in {time.time()-t0:.1f}s; {len(polys):,} polygons", flush=True)

    print("Assembling MultiPolygon…", flush=True)
    t0 = time.time()
    if len(polys) > 1:
        land = MultiPolygon(polys)
    elif polys:
        land = polys[0]
    else:
        print("FATAL: no polygons produced", file=sys.stderr)
        return 1
    if not land.is_valid:
        print("  invalid; running buffer(0) to repair…", flush=True)
        land = land.buffer(0)
    print(f"  done in {time.time()-t0:.1f}s", flush=True)

    print(f"Pickling to {OUT.name}…", flush=True)
    t0 = time.time()
    tmp = OUT.with_suffix(".pickle.tmp")
    with open(tmp, "wb") as f:
        pickle.dump(land, f, protocol=pickle.HIGHEST_PROTOCOL)
    tmp.replace(OUT)
    print(f"  wrote {OUT.stat().st_size/1024/1024:.1f} MB in {time.time()-t0:.1f}s", flush=True)

    print(f"Computing mainland polygons (> {MAINLAND_AREA_KM2:,} km²)…", flush=True)
    t0 = time.time()

    def _area_km2(p):
        c = p.centroid
        lat = c.y
        return (p.area * 111_320 * 111_320 * math.cos(math.radians(lat))) / 1_000_000

    big = []
    for p in polys:
        try:
            if _area_km2(p) > MAINLAND_AREA_KM2:
                big.append(p)
        except Exception:
            continue
    if len(big) > 1:
        mainland = MultiPolygon(big)
    elif big:
        mainland = big[0]
    else:
        print("  WARN: no polygon exceeded the mainland threshold", file=sys.stderr)
        mainland = None
    if mainland is not None and not mainland.is_valid:
        mainland = mainland.buffer(0)
    print(f"  done in {time.time()-t0:.1f}s; {len(big)} mainland component(s)", flush=True)

    if mainland is not None:
        tmp2 = MAINLAND_OUT.with_suffix(".pickle.tmp")
        with open(tmp2, "wb") as f:
            pickle.dump(mainland, f, protocol=pickle.HIGHEST_PROTOCOL)
        tmp2.replace(MAINLAND_OUT)
        print(f"  wrote {MAINLAND_OUT.name}: {MAINLAND_OUT.stat().st_size/1024/1024:.1f} MB", flush=True)
    print("\nDone. Run with --check to self-test the pickle.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
