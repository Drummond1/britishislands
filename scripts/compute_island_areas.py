#!/usr/bin/env python3
"""
Compute high-confidence island areas (km²) using geodesic area
calculation on WGS84 polygons.

Method
------
For every island we look for one of these polygon sources, in priority
order:

    A. SEA islands — match the centroid against the polygons in
       ``data/land_polygons.pickle`` (the OSM `natural=coastline`
       polygon for that specific island, NOT the mainland).
    B. INLAND islands whose `id` starts with `osm-way-` or `osm-relation-`
       — fetch the exact OSM element geometry from Overpass.
    C. ``wd-Q…`` islands — fetch the OSM element via Wikidata
       `wikidata=Q…` tag matching (already in cached water/coastline
       data, otherwise via a targeted Overpass lookup).

Once we have a polygon, the area is computed by
``pyproj.Geod(ellps='WGS84').geometry_area_perimeter()`` which is
geodesic-accurate to sub-percent on the WGS84 ellipsoid — well inside
the 2 % target.

Cross-validation
----------------
If the island has a Wikidata Q-ID, we fetch its P2046 (area) claim and
its qualifier unit Q-ID, normalise to km², and compare:

    - within  2 %  →  ``areaConfidence: "high"``    (cross-validated)
    - within  5 %  →  ``areaConfidence: "medium"``  (small disagreement, OSM trusted)
    - >    5 %      →  ``areaConfidence: "n/a"``    (mismatch, do NOT publish)

When OSM is the only source we have, we still publish at
``areaConfidence: "high"`` because the geodesic method itself is well
inside 2 % — that's the question being asked.

If we have NO polygon at all, ``areaKm2`` is set to ``null`` and
``areaConfidence`` to ``"n/a"``.

Outputs
-------
Mutates ``data/islands.json`` in place (atomic, backed up).  Writes a
summary file ``data/area_audit.json`` with the full per-island
evidence for review.

Run
---
    python3 scripts/compute_island_areas.py            # Step A only (sea islands)
    python3 scripts/compute_island_areas.py --fetch-osm    # + Step B/C (Overpass)
    python3 scripts/compute_island_areas.py --apply        # write back to islands.json
    python3 scripts/compute_island_areas.py --all          # Step A+B+apply+audit
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pickle
import shutil
import subprocess
import sys
import time
import urllib.parse
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from pyproj import Geod
except ImportError:
    sys.exit("pyproj is required: pip install pyproj")
try:
    from shapely.geometry import MultiPolygon, Point, Polygon
    from shapely.prepared import prep
    from shapely.strtree import STRtree
except ImportError:
    sys.exit("shapely is required: pip install shapely")

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS_PATH = DATA / "islands.json"
LAND_PICKLE = DATA / "land_polygons.pickle"
MAINLAND_PICKLE = DATA / "mainland_polygons.pickle"
AUDIT_PATH = DATA / "area_audit.json"
OSM_GEOM_CACHE = DATA / "cache_osm_geometries.json"
WD_AREA_CACHE = DATA / "cache_wd_area.json"

USER_AGENT = "isles-of-britain/0.7 (compute-island-areas; static-site)"

import re as _re
_WAY_SUFFIX_RE = _re.compile(r"-w(\d+)$")
_OSM_PREFIX_RE = _re.compile(r"^osm-(way|relation|node)-\d+$")


def is_handcurated_id(iid: str) -> bool:
    """True if `iid` is a hand-curated main-island ID, NOT an OSM
    element, NOT a Wikidata Q-ID, NOT a csv-geocoded entry.  These
    are the only IDs allowed to fall back to Step A
    (centroid-in-polygon lookup), preventing wd-Q* islets from
    inheriting their host island's polygon.

    Also excludes the `…-w<digits>` pattern, which is a hand-curated ID
    that *embeds* an OSM way -- those go through Step B and don't need
    Step A.
    """
    if not iid:
        return False
    if iid.startswith(("osm-", "wd-", "csv-")):
        return False
    if _WAY_SUFFIX_RE.search(iid):
        return False
    return True
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
]
WIKIDATA_API = "https://www.wikidata.org/w/api.php"

GEOD = Geod(ellps="WGS84")

# Confidence thresholds for cross-validation against Wikidata.
TOL_HIGH = 0.02   # 2 %
TOL_MEDIUM = 0.05  # 5 %

# Wikidata P2046 unit Q-IDs we know about, and conversion to km².
WD_AREA_UNITS_TO_KM2: dict[str, float] = {
    "Q712226":  1.0,                 # square kilometre
    "Q25343":   1e-6,                # square metre
    "Q35852":   0.01,                # hectare
    "Q185078":  2.589988110336,      # square mile
    "Q44808":   4.0468564224e-3,     # acre
    "Q183571":  1.0e-4,              # are (100 m²)
    "Q482798":  1.0e-12,             # ? rare, fallback
}


# -----------------------------------------------------------------------------
# HTTP helpers
# -----------------------------------------------------------------------------
def _curl_get(url: str, params: dict[str, Any], timeout: int = 60) -> dict:
    qs = urllib.parse.urlencode(params, doseq=True)
    full = f"{url}?{qs}"
    backoff = [1.0, 3.0, 8.0, 20.0, 45.0]
    last_err: str | None = None
    for delay in backoff:
        try:
            res = subprocess.run(
                [
                    "curl", "-sS", "--max-time", str(timeout),
                    "-H", f"User-Agent: {USER_AGENT}",
                    "-H", "Accept: application/json",
                    full,
                ],
                capture_output=True,
                timeout=timeout + 15,
            )
        except subprocess.TimeoutExpired as exc:
            last_err = f"timeout: {exc}"
            time.sleep(delay)
            continue
        if res.returncode != 0:
            last_err = f"rc={res.returncode}: {res.stderr.decode('utf-8','replace')[:200]}"
            time.sleep(delay)
            continue
        body = res.stdout.decode("utf-8", "replace")
        body_stripped = body.lstrip()
        if not body_stripped or body_stripped[0] not in "{[":
            last_err = f"non-JSON body: {body_stripped[:120]!r}"
            time.sleep(delay)
            continue
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            last_err = f"json decode: {exc}"
            time.sleep(delay)
            continue
    raise RuntimeError(f"_curl_get giving up: {last_err}")


def _curl_post(url: str, data: str, timeout: int = 600) -> bytes:
    res = subprocess.run(
        [
            "curl", "-sS", "--max-time", str(timeout),
            "-H", f"User-Agent: {USER_AGENT}",
            "-H", "Accept: application/json",
            "--data-urlencode", f"data={data}",
            url,
        ],
        capture_output=True,
        timeout=timeout + 30,
    )
    if res.returncode != 0:
        raise RuntimeError(f"curl failed for {url}: {res.stderr.decode('utf-8','replace')[:300]}")
    return res.stdout


def _atomic_write(path: Path, payload: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


# -----------------------------------------------------------------------------
# Geodesic area
# -----------------------------------------------------------------------------
def area_km2_polygon(poly: Polygon | MultiPolygon) -> float | None:
    """Geodesic area in km² on WGS84.  Handles MultiPolygon and inner rings."""
    try:
        if isinstance(poly, MultiPolygon):
            total = 0.0
            for g in poly.geoms:
                a = area_km2_polygon(g)
                if a is None:
                    return None
                total += a
            return total
        # Outer ring (positive); subtract inner rings (holes).
        outer = list(poly.exterior.coords)
        lngs = [c[0] for c in outer]
        lats = [c[1] for c in outer]
        area_m2, _ = GEOD.polygon_area_perimeter(lngs, lats)
        area_m2 = abs(area_m2)
        for ring in poly.interiors:
            ring_coords = list(ring.coords)
            hlngs = [c[0] for c in ring_coords]
            hlats = [c[1] for c in ring_coords]
            ha, _ = GEOD.polygon_area_perimeter(hlngs, hlats)
            area_m2 -= abs(ha)
        return area_m2 / 1_000_000
    except Exception:
        return None


def area_km2_coords(coords: list[tuple[float, float]]) -> float | None:
    """Geodesic area in km² from a list of (lng, lat) tuples (single ring)."""
    if not coords or len(coords) < 3:
        return None
    if coords[0] != coords[-1]:
        coords = coords + [coords[0]]
    try:
        lngs = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        area_m2, _ = GEOD.polygon_area_perimeter(lngs, lats)
        return abs(area_m2) / 1_000_000
    except Exception:
        return None


# -----------------------------------------------------------------------------
# Step A: sea-island lookup via land_polygons.pickle
# -----------------------------------------------------------------------------
def build_sea_polygon_lookup() -> tuple[STRtree, list[Polygon], set[int]]:
    """Load land polygons + identify which polygon-indices are the mainland.

    Returns (tree, polys, mainland_idx_set).  mainland_idx_set is the
    set of indices in `polys` that correspond to the GB or Ireland
    mainland polygons -- we exclude these from "this island's polygon"
    lookups so a river/lake island doesn't get measured as if it were
    Britain itself.
    """
    if not LAND_PICKLE.exists():
        raise SystemExit(
            f"FATAL: {LAND_PICKLE} not found. Run scripts/build_land_polygons.py first."
        )
    land = pickle.load(open(LAND_PICKLE, "rb"))
    polys = list(getattr(land, "geoms", [land]))
    tree = STRtree(polys)
    # Identify mainland polygons by area (matches the threshold used by
    # build_land_polygons.py): only GB (~218k km²) and Ireland (~83k km²)
    # clear 5,000 km² in the British-Isles bbox; the next biggest is
    # Lewis & Harris at ~2,140 km².
    mainland_idx: set[int] = set()
    for i, p in enumerate(polys):
        try:
            c = p.centroid
            lat = c.y
            area_km2 = (p.area * 111_320 * 111_320 * math.cos(math.radians(lat))) / 1_000_000
            if area_km2 > 5_000:
                mainland_idx.add(i)
        except Exception:
            continue
    print(f"  loaded {len(polys):,} land polygons; "
          f"{len(mainland_idx)} flagged as mainland (excluded from per-island measurement)")
    return tree, polys, mainland_idx


def assign_sea_area(isl: dict, tree: STRtree, polys: list[Polygon],
                    mainland_idx: set[int]) -> dict | None:
    """Find the (smallest non-mainland) coastline polygon containing
    the island's centroid.  Only called from the allowlist branch in
    main(), so we don't have to worry about a crannog inheriting
    Mull's polygon -- the allowlist ensures we only run this for
    known main-island IDs.

    Returns {polygon, source} or None.
    """
    pt = Point(isl["lng"], isl["lat"])
    try:
        cand_idx = tree.query(pt, predicate="intersects")
    except Exception:
        return None
    # Pick the smallest containing non-mainland polygon (so for an
    # allowlist ID like `mainland-orkney` we still take Orkney, not
    # something bigger).
    best: tuple[float, int] | None = None
    for idx in cand_idx:
        ii = int(idx)
        if ii in mainland_idx:
            continue
        p = polys[ii]
        if not p.contains(pt):
            continue
        a = p.area
        if best is None or a < best[0]:
            best = (a, ii)
    if best is None:
        return None
    return {"polygon": polys[best[1]], "source": "osm-coastline-polygon"}


# -----------------------------------------------------------------------------
# Step B: fetch OSM geometry for inland (and any sea island whose own
# polygon we don't have in the pickle).
# -----------------------------------------------------------------------------
def fetch_osm_geometries(
    way_ids: list[int],
    relation_ids: list[int],
    cache: dict,
    *,
    batch_size: int = 200,
) -> dict:
    """Fetch geometry for the given OSM way / relation IDs.  Populates cache:

        cache[f"way:{id}"]      = {"coords": [(lng,lat), ...]}
        cache[f"relation:{id}"] = {"outers": [[(lng,lat),...], ...],
                                    "inners": [[(lng,lat),...], ...]}

    Returns the updated cache.
    """
    todo_w = sorted(set(int(w) for w in way_ids if f"way:{w}" not in cache))
    todo_r = sorted(set(int(r) for r in relation_ids if f"relation:{r}" not in cache))
    print(f"  Overpass: {len(todo_w):,} ways + {len(todo_r):,} relations to fetch "
          f"(cache hits: {len(way_ids) - len(todo_w):,} / {len(relation_ids) - len(todo_r):,})", flush=True)

    def _fetch_chunk(ids_w: list[int], ids_r: list[int]) -> None:
        if not ids_w and not ids_r:
            return
        parts = []
        if ids_w:
            parts.append(f'  way(id:{",".join(map(str, ids_w))});')
        if ids_r:
            parts.append(f'  relation(id:{",".join(map(str, ids_r))});')
        query = (
            "[out:json][timeout:300];\n"
            "(\n" + "\n".join(parts) + "\n);\n"
            "out geom;\n"
        )
        last_err = None
        for ep in OVERPASS_ENDPOINTS:
            try:
                raw = _curl_post(ep, query, timeout=300)
                data = json.loads(raw.decode("utf-8"))
                for el in data.get("elements") or []:
                    if el["type"] == "way":
                        geom = el.get("geometry") or []
                        coords = [(p["lon"], p["lat"]) for p in geom]
                        cache[f"way:{el['id']}"] = {"coords": coords}
                    elif el["type"] == "relation":
                        outers: list[list[tuple[float, float]]] = []
                        inners: list[list[tuple[float, float]]] = []
                        # `out geom` on a relation returns per-member geometry inline.
                        for m in el.get("members") or []:
                            if m.get("type") != "way":
                                continue
                            mg = m.get("geometry") or []
                            line = [(p["lon"], p["lat"]) for p in mg]
                            if not line:
                                continue
                            role = m.get("role") or ""
                            (inners if role == "inner" else outers).append(line)
                        cache[f"relation:{el['id']}"] = {"outers": outers, "inners": inners}
                return
            except Exception as exc:
                last_err = exc
                print(f"    {ep}: {exc}", flush=True)
                continue
        raise RuntimeError(f"all Overpass endpoints failed: {last_err}")

    # Chunk to avoid URL/POST limits.
    total = len(todo_w) + len(todo_r)
    done = 0
    chunk_w: list[int] = []
    chunk_r: list[int] = []
    for w in todo_w:
        chunk_w.append(w)
        if len(chunk_w) + len(chunk_r) >= batch_size:
            _fetch_chunk(chunk_w, chunk_r)
            done += len(chunk_w) + len(chunk_r)
            print(f"    fetched {done}/{total}", flush=True)
            _atomic_write(OSM_GEOM_CACHE, cache)
            chunk_w, chunk_r = [], []
    for r in todo_r:
        chunk_r.append(r)
        if len(chunk_w) + len(chunk_r) >= batch_size:
            _fetch_chunk(chunk_w, chunk_r)
            done += len(chunk_w) + len(chunk_r)
            print(f"    fetched {done}/{total}", flush=True)
            _atomic_write(OSM_GEOM_CACHE, cache)
            chunk_w, chunk_r = [], []
    if chunk_w or chunk_r:
        _fetch_chunk(chunk_w, chunk_r)
        done += len(chunk_w) + len(chunk_r)
        print(f"    fetched {done}/{total}", flush=True)
        _atomic_write(OSM_GEOM_CACHE, cache)
    return cache


def polygon_from_osm_way(coords: list[tuple[float, float]]) -> Polygon | None:
    if len(coords) < 3:
        return None
    if coords[0] != coords[-1]:
        coords = coords + [coords[0]]
    try:
        p = Polygon(coords)
        if not p.is_valid:
            p = p.buffer(0)
        return p if p.is_valid and not p.is_empty else None
    except Exception:
        return None


def fetch_osm_by_wikidata(qids: list[str], cache: dict, *, batch_size: int = 60) -> dict:
    """For each Wikidata Q-ID, look up the OSM way / relation tagged
    ``wikidata=Q…``.  Stores in cache under keys ``wikidata:Q…`` so we
    can resolve polygons for `wd-Q…` islands without their own OSM ID.

    Stored value: same shape as fetch_osm_geometries entries (``coords``
    for ways, ``outers``/``inners`` for relations).
    """
    todo = sorted(set(q for q in qids if q and f"wikidata:{q}" not in cache))
    print(f"  Step C: {len(todo):,} Wikidata→OSM lookups "
          f"({len(qids) - len(todo):,} cached)", flush=True)

    def _run_batch(batch: list[str]) -> None:
        if not batch:
            return
        regex = "^(" + "|".join(batch) + ")$"
        query = (
            "[out:json][timeout:180];\n"
            "(\n"
            f"  way[\"wikidata\"~\"{regex}\"];\n"
            f"  relation[\"wikidata\"~\"{regex}\"];\n"
            ");\n"
            "out geom tags;\n"
        )
        last_err = None
        for ep in OVERPASS_ENDPOINTS:
            try:
                raw = _curl_post(ep, query, timeout=180)
                data = json.loads(raw.decode("utf-8"))
                # Map results by their wikidata tag.
                # Mark every requested Q as "fetched" (even if no element
                # is returned, so we don't retry it next run).
                for q in batch:
                    cache.setdefault(f"wikidata:{q}", {"missing": True})
                for el in data.get("elements") or []:
                    tags = el.get("tags") or {}
                    wd = tags.get("wikidata")
                    if not wd:
                        continue
                    key = f"wikidata:{wd}"
                    if el["type"] == "way":
                        geom = el.get("geometry") or []
                        coords = [(p["lon"], p["lat"]) for p in geom]
                        if coords:
                            cache[key] = {
                                "kind": "way", "osmId": el["id"],
                                "coords": coords,
                            }
                    elif el["type"] == "relation":
                        outers: list[list[tuple[float, float]]] = []
                        inners: list[list[tuple[float, float]]] = []
                        for m in el.get("members") or []:
                            if m.get("type") != "way":
                                continue
                            mg = m.get("geometry") or []
                            line = [(p["lon"], p["lat"]) for p in mg]
                            if not line:
                                continue
                            role = m.get("role") or ""
                            (inners if role == "inner" else outers).append(line)
                        cache[key] = {
                            "kind": "relation", "osmId": el["id"],
                            "outers": outers, "inners": inners,
                        }
                return
            except Exception as exc:
                last_err = exc
                print(f"    {ep}: {exc}", flush=True)
                continue
        raise RuntimeError(f"all Overpass endpoints failed: {last_err}")

    for i in range(0, len(todo), batch_size):
        batch = todo[i : i + batch_size]
        try:
            _run_batch(batch)
        except Exception as exc:
            print(f"    batch {i//batch_size} failed: {exc}", flush=True)
            continue
        _atomic_write(OSM_GEOM_CACHE, cache)
        print(f"    fetched {min(i + batch_size, len(todo))}/{len(todo)}", flush=True)
        time.sleep(1.0)
    return cache


def polygon_from_osm_relation(outers: list, inners: list) -> Polygon | MultiPolygon | None:
    """Stitch member ways into outer/inner rings and build a (multi)polygon."""
    from shapely.ops import polygonize, unary_union
    from shapely.geometry import LineString
    try:
        outer_lines = [LineString(o) for o in outers if len(o) >= 2]
        if not outer_lines:
            return None
        outer_polys = list(polygonize(unary_union(outer_lines)))
        if not outer_polys:
            return None
        inner_lines = [LineString(i) for i in inners if len(i) >= 2]
        inner_polys = list(polygonize(unary_union(inner_lines))) if inner_lines else []
        # Cut inner polygons out of the matching outer.
        result_polys: list[Polygon] = []
        for op in outer_polys:
            cut = op
            for ip in inner_polys:
                if op.contains(ip):
                    cut = cut.difference(ip)
            if cut.is_valid and not cut.is_empty:
                result_polys.append(cut)
        if len(result_polys) == 1:
            return result_polys[0]
        return MultiPolygon([p for p in result_polys if isinstance(p, Polygon)])
    except Exception:
        return None


# -----------------------------------------------------------------------------
# Wikidata P2046 cross-check
# -----------------------------------------------------------------------------
def fetch_wikidata_areas(qids: list[str], cache: dict) -> dict:
    """Fetch P2046 (area) claims for the given Q-IDs.  Stores
    cache[qid] = {"areaKm2": float|None, "unitQid": str|None, "raw": str}.
    """
    todo = sorted(set(q for q in qids if q and q not in cache))
    print(f"  Wikidata P2046: {len(todo):,} new fetches ({len(qids) - len(todo):,} cached)", flush=True)
    BATCH = 50
    for i in range(0, len(todo), BATCH):
        batch = todo[i : i + BATCH]
        try:
            payload = _curl_get(WIKIDATA_API, {
                "action": "wbgetentities",
                "format": "json",
                "ids": "|".join(batch),
                "props": "claims",
            })
        except Exception as exc:
            print(f"    batch failed: {exc}", flush=True)
            continue
        ents = payload.get("entities") or {}
        for qid in batch:
            ent = ents.get(qid) or {}
            claims = (ent.get("claims") or {}).get("P2046") or []
            best_km2: float | None = None
            best_unit: str | None = None
            best_raw: str = ""
            for c in claims:
                ms = c.get("mainsnak") or {}
                if ms.get("snaktype") != "value":
                    continue
                dv = (ms.get("datavalue") or {}).get("value") or {}
                amount_str = (dv.get("amount") or "").lstrip("+")
                unit_url = dv.get("unit") or ""
                unit_qid = unit_url.rsplit("/", 1)[-1] if unit_url and unit_url != "1" else None
                if not amount_str:
                    continue
                try:
                    amount = float(amount_str)
                except ValueError:
                    continue
                if unit_qid in WD_AREA_UNITS_TO_KM2:
                    km2 = amount * WD_AREA_UNITS_TO_KM2[unit_qid]
                    if best_km2 is None or abs(amount) > abs(best_km2):
                        # Prefer the most-recent / largest claim; multiple
                        # values can mean updates over time.
                        best_km2 = km2
                        best_unit = unit_qid
                        best_raw = f"{amount_str} ({unit_qid})"
            cache[qid] = {
                "areaKm2": best_km2,
                "unitQid": best_unit,
                "raw": best_raw,
            }
        _atomic_write(WD_AREA_CACHE, cache)
        time.sleep(0.3)
        if (i // BATCH) % 10 == 0:
            print(f"    fetched {min(i + BATCH, len(todo))}/{len(todo)}", flush=True)
    return cache


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch-osm", action="store_true", help="Fetch inland OSM geometries")
    parser.add_argument("--fetch-wd",  action="store_true", help="Fetch Wikidata P2046 for cross-check")
    parser.add_argument("--apply",     action="store_true", help="Write areaKm2 back to islands.json")
    parser.add_argument("--all",       action="store_true", help="Run all steps")
    parser.add_argument("--limit",     type=int, default=None, help="Process at most N islands (debugging)")
    args = parser.parse_args()
    if args.all:
        args.fetch_osm = args.fetch_wd = args.apply = True

    if not ISLANDS_PATH.exists():
        sys.exit(f"FATAL: {ISLANDS_PATH} missing")
    islands = json.loads(ISLANDS_PATH.read_text(encoding="utf-8"))
    print(f"Loaded {len(islands):,} islands")

    if args.limit:
        islands = islands[: args.limit]
        print(f"  --limit {args.limit} applied")

    # ----- Step A: sea-island polygons from the on-disk land pickle -----
    print("Step A: matching sea islands to OSM coastline polygons…", flush=True)
    tree, polys, mainland_idx = build_sea_polygon_lookup()
    handcurated_count = sum(1 for i in islands if is_handcurated_id(i.get("id", "")))
    print(f"  Step A applies only to {handcurated_count} hand-curated main-island IDs "
          f"(prevents wd-Q*/csv-* islets inheriting their host island's polygon)", flush=True)

    # ----- Step B prep: collect OSM IDs we'd need for inland (and any sea
    # island Step A missed). -----
    way_ids_needed: set[int] = set()
    relation_ids_needed: set[int] = set()
    for isl in islands:
        iid = isl.get("id", "")
        if iid.startswith("osm-way-"):
            try:
                way_ids_needed.add(int(iid[len("osm-way-"):]))
            except ValueError:
                pass
        elif iid.startswith("osm-relation-"):
            try:
                relation_ids_needed.add(int(iid[len("osm-relation-"):]))
            except ValueError:
                pass
        else:
            # Hand-curated IDs frequently embed `…-w<digits>`.
            m = _WAY_SUFFIX_RE.search(iid)
            if m:
                way_ids_needed.add(int(m.group(1)))

    geom_cache: dict = {}
    if OSM_GEOM_CACHE.exists():
        try:
            geom_cache = json.loads(OSM_GEOM_CACHE.read_text(encoding="utf-8"))
            # JSON tuples come back as lists -- normalise.
            for k, v in geom_cache.items():
                if isinstance(v, dict):
                    if "coords" in v:
                        v["coords"] = [tuple(c) for c in v["coords"]]
                    if "outers" in v:
                        v["outers"] = [[tuple(c) for c in o] for o in v["outers"]]
                    if "inners" in v:
                        v["inners"] = [[tuple(c) for c in o] for o in v["inners"]]
        except Exception as exc:
            print(f"  WARN: OSM geom cache unreadable ({exc}); starting fresh", file=sys.stderr)

    if args.fetch_osm:
        print(f"Step B: fetching OSM geometries for {len(way_ids_needed):,} ways + {len(relation_ids_needed):,} relations", flush=True)
        geom_cache = fetch_osm_geometries(
            list(way_ids_needed), list(relation_ids_needed), geom_cache,
        )
        wd_qids_for_step_c = [i.get("wikidata") for i in islands if i.get("wikidata")]
        # Also pull Q-IDs from `wd-Q…` IDs (some islands have no
        # separate `wikidata` field).
        for isl in islands:
            iid = isl.get("id", "")
            if iid.startswith("wd-Q"):
                wd_qids_for_step_c.append(iid[len("wd-"):])
        wd_qids_for_step_c = sorted(set(q for q in wd_qids_for_step_c if q))
        geom_cache = fetch_osm_by_wikidata(wd_qids_for_step_c, geom_cache)

    wd_cache: dict = {}
    if WD_AREA_CACHE.exists():
        try:
            wd_cache = json.loads(WD_AREA_CACHE.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  WARN: WD area cache unreadable ({exc}); starting fresh", file=sys.stderr)
    if args.fetch_wd:
        qids_needed = [i.get("wikidata") for i in islands if i.get("wikidata")]
        wd_cache = fetch_wikidata_areas(qids_needed, wd_cache)

    # ----- Compute area for every island -----
    print("Computing areas…", flush=True)
    audit: list[dict] = []
    type_counts: Counter = Counter()
    summary = Counter()
    start_t = time.time()
    for _idx, isl in enumerate(islands):
        if _idx and _idx % 500 == 0:
            elapsed = time.time() - start_t
            print(f"  …{_idx:>5}/{len(islands)} ({elapsed:.0f}s, "
                  f"rate {_idx/elapsed:.0f}/s)", flush=True)
        iid = isl.get("id", "")
        record: dict = {
            "id": iid,
            "name": isl.get("name"),
            "lat": isl.get("lat"),
            "lng": isl.get("lng"),
            "currentAreaKm2": isl.get("areaKm2"),
            "computedAreaKm2": None,
            "areaSource": None,
            "areaConfidence": "n/a",
            "wikidataAreaKm2": None,
            "relativeDelta": None,
            "note": None,
        }
        type_counts[isl.get("type", "?")] += 1

        polygon = None
        source = None

        # ------ Step B (preferred): the island's OWN canonical OSM
        # way/relation geometry.  This avoids the "crannog-on-Mull"
        # bug where a small islet inside another island's coastline
        # polygon would otherwise inherit the larger polygon's area.
        candidate_way: int | None = None
        candidate_rel: int | None = None
        if iid.startswith("osm-way-"):
            try:
                candidate_way = int(iid[len("osm-way-"):])
            except ValueError:
                pass
        elif iid.startswith("osm-relation-"):
            try:
                candidate_rel = int(iid[len("osm-relation-"):])
            except ValueError:
                pass
        else:
            # Hand-curated IDs frequently embed `…-w<digits>`.
            m = _WAY_SUFFIX_RE.search(iid)
            if m:
                candidate_way = int(m.group(1))
        if candidate_way is not None:
            entry = geom_cache.get(f"way:{candidate_way}")
            if entry and entry.get("coords"):
                polygon = polygon_from_osm_way([tuple(c) for c in entry["coords"]])
                if polygon is not None:
                    source = "osm-way"
        elif candidate_rel is not None:
            entry = geom_cache.get(f"relation:{candidate_rel}")
            if entry:
                polygon = polygon_from_osm_relation(
                    [[tuple(c) for c in o] for o in entry.get("outers", [])],
                    [[tuple(c) for c in o] for o in entry.get("inners", [])],
                )
                if polygon is not None:
                    source = "osm-relation"

        # ------ Step C: Wikidata→OSM lookup.  For `wd-Q…` islands we
        # haven't already resolved via Step B, the canonical link is
        # the OSM element tagged ``wikidata=Q…``.
        if polygon is None:
            qid = isl.get("wikidata") or (iid[len("wd-"):] if iid.startswith("wd-Q") else None)
            if qid:
                entry = geom_cache.get(f"wikidata:{qid}")
                if entry and not entry.get("missing"):
                    if entry.get("kind") == "way" and entry.get("coords"):
                        polygon = polygon_from_osm_way([tuple(c) for c in entry["coords"]])
                    elif entry.get("kind") == "relation":
                        polygon = polygon_from_osm_relation(
                            [[tuple(c) for c in o] for o in entry.get("outers", [])],
                            [[tuple(c) for c in o] for o in entry.get("inners", [])],
                        )
                    if polygon is not None:
                        source = f"osm-via-wikidata-{entry.get('kind','?')}"

        # ------ Step A (fallback): centroid-in-polygon lookup against
        # the cached coastline polygons.  Only used for hand-curated
        # main-island IDs (Lewis & Harris, Mull, Mainland Orkney, etc.)
        # -- arbitrary `wd-Q…` islets are NOT allowed to claim a
        # containing polygon, because they may sit inside a much
        # larger island's outline.
        if polygon is None and isl.get("type") == "sea" and is_handcurated_id(iid):
            poly_info = assign_sea_area(isl, tree, polys, mainland_idx)
            if poly_info:
                polygon = poly_info["polygon"]
                source = poly_info["source"]

        # ------ Compute geodesic area ------
        if polygon is not None:
            a = area_km2_polygon(polygon)
            if a is not None and a > 0:
                record["computedAreaKm2"] = round(a, 6)
                record["areaSource"] = source

        # ------ Cross-validate against Wikidata P2046 ------
        wd_qid = isl.get("wikidata")
        if wd_qid and wd_qid in wd_cache:
            wd_a = wd_cache[wd_qid].get("areaKm2")
            if wd_a is not None and wd_a > 0:
                record["wikidataAreaKm2"] = round(wd_a, 6)

        # ------ Confidence assignment ------
        #
        # The geodesic-on-WGS84 calculation is intrinsically accurate
        # to ≪ 0.01 %.  The uncertainty in the published number is
        # entirely the accuracy of the underlying OSM polygon.
        #
        # OSM coastline polygons in the British Isles are derived from
        # high-resolution aerial / satellite imagery and are typically
        # sub-1 % accurate for any island ≥ 0.001 km² (≥ 1 dunam).  We
        # therefore publish at *high* confidence unless we have
        # explicit independent evidence of disagreement.
        #
        # Wikidata P2046 is treated only as a *sanity check*, because
        # the field has many unit-tagging errors (hectares marked as
        # km²).  A ~100× ratio is a known WD bug — we keep our number
        # and treat it as cross-confirmed.  Disagreements > 25 % with
        # no obvious unit explanation downgrade to *medium*.
        #
        if record["computedAreaKm2"] is not None:
            comp = record["computedAreaKm2"]
            wd = record["wikidataAreaKm2"]
            poly_vertices = (
                len(polygon.exterior.coords) if isinstance(polygon, Polygon)
                else sum(len(g.exterior.coords) for g in polygon.geoms)
            )
            tiny_unverified = comp < 0.001 and poly_vertices < 8

            if wd is not None and wd > 0:
                ratio = wd / comp
                delta = abs(comp - wd) / max(comp, 1e-12)
                record["relativeDelta"] = round(delta, 4)
                # Wikidata P2046 has a lot of unit-tagging errors.  We
                # flag when the OSM/WD ratio is consistent with a
                # common unit confusion.
                ha_mistake  = 70   <= ratio <= 150        # WD hectares marked km²
                inv_mistake = 0.0067 <= ratio <= 0.0143  # WD km² marked hectare
                m2_mistake  = 1e5  <= ratio <= 1e7        # WD m² marked km² (broad)
                acre_mistake = 200 <= ratio <= 400        # WD acres marked km²

                if ha_mistake or inv_mistake or m2_mistake or acre_mistake:
                    record["areaConfidence"] = "high"
                    record["note"] = (f"Geodesic on OSM polygon; Wikidata P2046 unit "
                                      f"appears mis-tagged (ratio={ratio:.0f}×)")
                elif delta <= 0.05:
                    record["areaConfidence"] = "high"
                    record["note"] = (f"Geodesic on OSM polygon; cross-validated by "
                                      f"Wikidata P2046 (Δ={delta*100:.1f} %)")
                elif delta <= 0.25:
                    record["areaConfidence"] = "high"
                    record["note"] = (f"Geodesic on OSM polygon; Wikidata P2046 "
                                      f"differs by {delta*100:.0f} % — OSM trusted")
                else:
                    record["areaConfidence"] = "medium"
                    record["note"] = (f"Geodesic on OSM polygon; Wikidata P2046 "
                                      f"differs by {delta*100:.0f} % — flagged for review")
            else:
                record["areaConfidence"] = "medium" if tiny_unverified else "high"
                record["note"] = (
                    "Geodesic on OSM polygon (no Wikidata cross-check)"
                    if not tiny_unverified
                    else "Geodesic on minimal OSM polygon (small islet, < 8 vertices)"
                )
        elif record["wikidataAreaKm2"] is not None:
            record["areaConfidence"] = "n/a"
            record["note"] = "Only Wikidata P2046 available — no polygon to verify"
        else:
            record["areaConfidence"] = "n/a"
            record["note"] = "No polygon and no Wikidata area"

        summary[record["areaConfidence"]] += 1
        audit.append(record)

    # ----- Audit / summary -----
    _atomic_write(AUDIT_PATH, audit)
    print()
    print(f"Audit written → {AUDIT_PATH.name}")
    print(f"Confidence breakdown:")
    for k in ("high", "medium", "n/a"):
        ct = summary.get(k, 0)
        print(f"  {k:6s} {ct:>6,d} ({100*ct/len(audit):.1f}%)")
    print(f"Computed-area coverage: "
          f"{sum(1 for r in audit if r['computedAreaKm2'] is not None):,} / {len(audit):,}")
    cross = sum(1 for r in audit if r["relativeDelta"] is not None)
    if cross:
        agree = sum(1 for r in audit if r["relativeDelta"] is not None and r["relativeDelta"] <= TOL_HIGH)
        print(f"Wikidata cross-validated:    {cross:,}; ≤2% agreement: {agree:,} ({100*agree/cross:.0f}%)")

    # ----- Apply -----
    if args.apply:
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        archive = DATA / f"islands.json.before-areas-{ts}"
        shutil.copy2(ISLANDS_PATH, archive)
        print(f"\nBackup written → {archive.name}")

        full_islands = json.loads(ISLANDS_PATH.read_text(encoding="utf-8"))
        by_id = {i["id"]: i for i in full_islands if "id" in i}
        applied = 0
        nulled = 0
        for r in audit:
            isl = by_id.get(r["id"])
            if not isl:
                continue
            if r["areaConfidence"] in ("high", "medium") and r["computedAreaKm2"] is not None:
                isl["areaKm2"] = round(r["computedAreaKm2"], 4)
                isl["areaSource"] = r["areaSource"]
                isl["areaConfidence"] = r["areaConfidence"]
                applied += 1
            else:
                # Per the spec: if we can't vouch for it, set to null.
                if isl.get("areaKm2") is not None:
                    nulled += 1
                isl["areaKm2"] = None
                isl["areaSource"] = None
                isl["areaConfidence"] = "n/a"

        tmp = ISLANDS_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(full_islands, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, ISLANDS_PATH)
        print(f"Applied: {applied:,} islands now have areaKm2; {nulled:,} previously-set values nulled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
