#!/usr/bin/env python3
"""
EXPERIMENTAL — do not `--apply` without manual review.

Point-in-polygon against Natural Earth admin-1 (10m) can mis-tag features
near the Ireland / Northern Ireland border and the Scotland / England border
(first matching polygon wins).

Intended future use: Knightstone-class bbox fixes with overrides, not blind bulk apply.

Dry-run:
  python3 scripts/recompute_nation_admin1.py

Requires: shapely. Downloads data/cache_ne10m_admin1_uk_ie.geojson once (~20 MB).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = ROOT / "data" / "cache_ne10m_admin1_uk_ie.geojson"
ISLANDS_PATH = ROOT / "data" / "islands.json"
NE_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "v5.0.0/geojson/ne_10m_admin_1_states_provinces.geojson"
)

ALLOW_ADM0 = frozenset({"GBR", "IRL", "IMN", "GGY", "JEY"})


def download_geojson() -> dict:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading Natural Earth admin-1 (10m) -> {CACHE_PATH}", file=sys.stderr)
    req = urllib.request.Request(
        NE_URL,
        headers={"User-Agent": "IslesOfBritain-nation-fix/1.0"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:  # noqa: S310
        raw = resp.read()
    CACHE_PATH.write_bytes(raw)
    return json.loads(raw.decode("utf-8"))


def load_features() -> list:
    if CACHE_PATH.is_file():
        doc = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    else:
        doc = download_geojson()
    kept = []
    for feat in doc.get("features", []):
        props = feat.get("properties") or {}
        adm0 = props.get("adm0_a3")
        if adm0 not in ALLOW_ADM0:
            continue
        geom = feat.get("geometry")
        if not geom:
            continue
        kept.append((props, geom))
    return kept


def props_to_nation(props: dict) -> str | None:
    adm0 = props.get("adm0_a3")
    gu = (props.get("geonunit") or "").strip()
    if adm0 == "IRL":
        return "Ireland"
    if adm0 == "IMN":
        return "Isle of Man"
    if adm0 in ("GGY", "JEY"):
        return "Crown Dependency"
    if adm0 == "GBR" and gu in ("England", "Scotland", "Wales", "Northern Ireland"):
        return gu
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write data/islands.json (else print summary only).",
    )
    args = parser.parse_args()

    try:
        from shapely.geometry import Point, shape
        from shapely.strtree import STRtree
    except ImportError:
        print("Install shapely: pip install shapely", file=sys.stderr)
        sys.exit(1)

    raw_features = load_features()
    polys = []
    meta = []
    for props, geom in raw_features:
        try:
            g = shape(geom)
        except Exception:
            continue
        if g.is_empty:
            continue
        if g.geom_type == "MultiPolygon":
            for sub in g.geoms:
                polys.append(sub)
                meta.append(props)
        elif g.geom_type == "Polygon":
            polys.append(g)
            meta.append(props)

    if not polys:
        print("No polygons loaded — check cache / network", file=sys.stderr)
        sys.exit(1)

    tree = STRtree(polys)

    islands = json.loads(ISLANDS_PATH.read_text(encoding="utf-8"))
    changes = []
    no_hit = 0

    for row in islands:
        lat = float(row["lat"])
        lng = float(row["lng"])
        pt = Point(lng, lat)
        candidates = tree.query(pt, predicate="intersects")
        nation_new = None
        for idx in candidates:
            poly = polys[int(idx)]
            try:
                if poly.contains(pt):
                    nation_new = props_to_nation(meta[int(idx)])
                    if nation_new:
                        break
            except Exception:
                continue
        if nation_new is None:
            no_hit += 1
            continue
        old = row.get("nation")
        if old != nation_new:
            changes.append((row.get("id"), old, nation_new))

    print(
        f"polygons={len(polys)} islands={len(islands)} "
        f"would_change={len(changes)} no_polygon_match={no_hit}",
        file=sys.stderr,
    )
    for tid, o, n in changes[:45]:
        print(f"  {tid}: {o!r} -> {n!r}", file=sys.stderr)
    if len(changes) > 45:
        print(f"  ... and {len(changes) - 45} more", file=sys.stderr)

    if not args.apply:
        return

    id_to_new = {tid: n for tid, o, n in changes}
    for row in islands:
        if row["id"] in id_to_new:
            row["nation"] = id_to_new[row["id"]]

    ISLANDS_PATH.write_text(
        json.dumps(islands, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {ISLANDS_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
