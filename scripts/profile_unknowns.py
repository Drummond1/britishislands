#!/usr/bin/env python3
"""
Read-only diagnostic: profile the 210 (or however many) islands currently
typed as `unknown` so we can plan how to drain them.

Reports:
  - Total `unknown` count and breakdown by nation
  - Q-ID coverage (how many have a Wikidata entry)
  - For QID-equipped ones, their Wikidata P31 (instance of) distribution
    (so we can spot crannogs / river islands / lake islets en bloc)
  - For each unknown, the distance (in metres) to the nearest non-tidal
    OSM water polygon, and that polygon's tagged kind/name
  - Distance histogram so we can pick a sensible Tier-4 radius cut-off

Run:
    python3 scripts/profile_unknowns.py
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter
from pathlib import Path

from shapely.geometry import Point
from shapely.strtree import STRtree
from shapely.ops import nearest_points

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

sys.path.insert(0, str(ROOT / "scripts"))
import reclassify_islands as R  # type: ignore


def deg_distance_to_m(p_lat: float, near_lat: float, near_lng: float, p_lng: float) -> float:
    dy = (p_lat - near_lat) * 111_320
    dx = (p_lng - near_lng) * 111_320 * math.cos(math.radians((p_lat + near_lat) / 2))
    return math.hypot(dx, dy)


def main() -> int:
    islands = json.loads((DATA / "islands.json").read_text(encoding="utf-8"))
    unknowns = [i for i in islands if i.get("type") == "unknown"]
    print(f"Total unknowns: {len(unknowns):,}")
    print()
    print("By nation:")
    for n, c in Counter(i.get("nation", "?") for i in unknowns).most_common():
        print(f"  {n:25s} {c}")
    print()

    qid_count = sum(1 for i in unknowns if i.get("wikidata"))
    print(f"Q-ID coverage: {qid_count}/{len(unknowns)} ({100*qid_count/len(unknowns):.0f}%)")
    print()

    # ---- P31 distribution among QID-equipped unknowns ----
    wd_cache = R._load_cache(R.CACHE_WD, {"islands": {}, "bodies": {}, "classes": {}})
    print("Top Wikidata P31 (instance-of) among QID-equipped unknowns:")
    print("  (requires data/cache_wd_water_body.json — only P206 was fetched; P31 lookup may miss)")
    print()

    # We didn't fetch P31 for the islands themselves (only the bodies they
    # link to via P206).  But for islands with no P206 link, we may still
    # learn something by glancing at the island label.
    label_distribution: Counter = Counter()
    for i in unknowns:
        qid = i.get("wikidata")
        if not qid:
            continue
        entry = (wd_cache.get("islands") or {}).get(qid) or {}
        label_distribution[(entry.get("label") or "").strip()] += 1
    most_common_labels = label_distribution.most_common(15)
    if most_common_labels:
        print("  Most common island-name labels in the Wikidata cache:")
        for lbl, c in most_common_labels:
            print(f"    {c:>3}  {lbl}")
    print()

    # ---- Proximity test against the widened water polygons ----
    print("Building water-polygon spatial index for proximity test…", flush=True)
    water_data = R._load_cache(R.CACHE_WATER, {})
    if not water_data:
        print("  WARN: water_raw_v2.json missing — proximity test skipped", file=sys.stderr)
        return 0
    water_bodies = R.build_water_bodies(water_data, wd_cache=wd_cache)
    body_polys = [b["polygon"] for b in water_bodies]
    body_by_polyid = {id(p): b for p, b in zip(body_polys, water_bodies)}
    tree = STRtree(body_polys) if body_polys else None
    print(f"  built {len(body_polys):,} water polygons", flush=True)
    print()

    if tree is None:
        return 0

    histogram: Counter = Counter()
    type_hits_within_100m: Counter = Counter()
    type_hits_within_500m: Counter = Counter()
    summary_rows: list[tuple[float, dict, dict]] = []  # (dist_m, isl, body)

    for isl in unknowns:
        pt = Point(isl["lng"], isl["lat"])
        try:
            idx = tree.nearest(pt)
            nearest_poly = body_polys[int(idx)]
        except Exception:
            continue
        near_on_poly, _ = nearest_points(nearest_poly, pt)
        dist_m = deg_distance_to_m(isl["lat"], near_on_poly.y, near_on_poly.x, isl["lng"])
        body = body_by_polyid[id(nearest_poly)]
        summary_rows.append((dist_m, isl, body))

        bucket = (
            "0-50m"      if dist_m <= 50 else
            "50-100m"    if dist_m <= 100 else
            "100-200m"   if dist_m <= 200 else
            "200-500m"   if dist_m <= 500 else
            "500m-1km"   if dist_m <= 1000 else
            "1km-5km"    if dist_m <= 5000 else
            ">5km"
        )
        histogram[bucket] += 1
        if dist_m <= 100:
            type_hits_within_100m[body["kind"]] += 1
        if dist_m <= 500:
            type_hits_within_500m[body["kind"]] += 1

    print("Distance from each unknown island's centroid to the nearest non-tidal water polygon:")
    BUCKETS = ["0-50m", "50-100m", "100-200m", "200-500m", "500m-1km", "1km-5km", ">5km"]
    for b in BUCKETS:
        n = histogram.get(b, 0)
        bar = "█" * (n * 50 // max(1, len(unknowns)))
        print(f"  {b:>9s} {n:>4} {bar}")
    print()
    print(f"  ≤100m would resolve: {sum(histogram.get(b,0) for b in ('0-50m','50-100m'))} "
          f"({100*sum(histogram.get(b,0) for b in ('0-50m','50-100m'))/len(unknowns):.0f}%)")
    print(f"  ≤500m would resolve: {sum(histogram.get(b,0) for b in BUCKETS[:4])} "
          f"({100*sum(histogram.get(b,0) for b in BUCKETS[:4])/len(unknowns):.0f}%)")
    print()
    print(f"Water-body kind distribution within 100m: {dict(type_hits_within_100m)}")
    print(f"Water-body kind distribution within 500m: {dict(type_hits_within_500m)}")
    print()

    # Print a few examples at each band so we can sanity-check
    summary_rows.sort(key=lambda r: r[0])
    print("Sample assignments at each distance band:")
    for low, high in [(0, 50), (50, 200), (200, 500), (500, 1000), (1000, 5000)]:
        in_band = [r for r in summary_rows if low < r[0] <= high]
        if not in_band:
            continue
        print(f"\n  {low}-{high}m  ({len(in_band)} islands):")
        for r in in_band[:5]:
            dist_m, isl, body = r
            print(f"    {dist_m:6.1f}m  {isl['name'][:35]:35s}  → "
                  f"{body['kind']:6s} {body['name'] or '(unnamed)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
