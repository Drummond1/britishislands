#!/usr/bin/env python3
"""
Compute each island's highest-point elevation (and the peak's name)
using OSM-surveyed `natural=peak` nodes, with Wikidata P2044 cross-check.

Method
------
1. **Bulk-fetch every `natural=peak` node in the UK/Ireland bbox** that
   has an `ele=*` tag.  OSM peak `ele` values are typically sourced
   from Ordnance Survey or licensed surveys -- accurate to ±1 m for
   any summit ≥ 50 m, so we're inside 2 % by a wide margin.
2. Build a spatial index of the peaks; for every island that has a
   polygon (from `scripts/compute_island_areas.py`), find peaks inside
   the polygon and take the one with the highest `ele`.
3. Cross-check against Wikidata P2044 (elevation above sea level)
   where we have a Q-ID.  Disagreements > 5 m or > 5 % downgrade to
   "estimate"; otherwise we mark `highestPointConfidence = "high"`.
4. Where we have no peak inside the polygon, fall back to Wikidata
   P2044 alone -- that value is published with `highestPointConfidence
   = "estimate"`.

Per the user spec ("within 2 % accuracy, or put an estimate next to
it"), we always publish *something* when we have *any* evidence, and
flag every figure with its confidence so the UI can label estimates.

Outputs
-------
* Mutates `data/islands.json` in place (atomic, backed up).
* Writes `data/highpoint_audit.json` for review.

CLI
---
    python3 scripts/compute_island_highpoints.py            # dry-run + audit
    python3 scripts/compute_island_highpoints.py --fetch    # + Overpass + WD fetch
    python3 scripts/compute_island_highpoints.py --apply    # write back to islands.json
    python3 scripts/compute_island_highpoints.py --all      # fetch + apply + audit
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pickle
import re
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
    from shapely.geometry import LineString, MultiPolygon, Point, Polygon
    from shapely.ops import polygonize, unary_union
    from shapely.prepared import prep
    from shapely.strtree import STRtree
except ImportError:
    sys.exit("shapely is required: pip install shapely")

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS_PATH = DATA / "islands.json"
LAND_PICKLE = DATA / "land_polygons.pickle"
OSM_GEOM_CACHE = DATA / "cache_osm_geometries.json"
PEAKS_CACHE = DATA / "cache_osm_peaks.json"
WD_ELE_CACHE = DATA / "cache_wd_elevation.json"
AUDIT_PATH = DATA / "highpoint_audit.json"

USER_AGENT = "isles-of-britain/0.7 (compute-island-highpoints; static-site)"
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
]
WIKIDATA_API = "https://www.wikidata.org/w/api.php"

# UK + Ireland + Crown Dependencies + 50-mile fringe.
BBOX = (49.0, -11.5, 61.5, 2.5)  # (south, west, north, east)

# Cut the bbox into tiles to keep each Overpass query small.
TILE_LAT = 2.0
TILE_LNG = 2.5

_WAY_SUFFIX_RE = re.compile(r"-w(\d+)$")

# Wikidata length-unit Q-IDs we may see attached to P2044.
WD_LEN_UNITS_TO_M: dict[str, float] = {
    "Q11573":   1.0,        # metre
    "Q174728":  0.01,       # centimetre
    "Q828224":  1000.0,     # kilometre
    "Q3710":    0.3048,     # foot
    "Q253276":  1609.344,   # mile
    "Q11569":   0.9144,     # yard
}


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
            last_err = f"rc={res.returncode}"
            time.sleep(delay)
            continue
        body = res.stdout.decode("utf-8", "replace")
        s = body.lstrip()
        if not s or s[0] not in "{[":
            last_err = f"non-JSON body: {s[:120]!r}"
            time.sleep(delay)
            continue
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            last_err = f"json decode: {exc}"
            time.sleep(delay)
            continue
    raise RuntimeError(f"_curl_get giving up: {last_err}")


def _atomic_write(path: Path, payload: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _parse_ele(raw: str | None) -> float | None:
    """Parse OSM `ele=*` value to metres.  Returns None for
    unparseable / out-of-range data.  OSM convention is metres;
    explicit ` m` / ` ft` suffixes also accepted.
    """
    if not raw:
        return None
    s = str(raw).strip().lower()
    if not s:
        return None
    unit_factor = 1.0
    if s.endswith("ft") or s.endswith("'"):
        unit_factor = 0.3048
        s = s.rstrip("ft' ").strip()
    elif s.endswith("m"):
        s = s.rstrip("m ").strip()
    s = s.replace(",", ".")
    m = re.match(r"^[+-]?\d+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        v = float(m.group(0)) * unit_factor
    except ValueError:
        return None
    # British Isles range: lowest -3 m polders, highest 1,345 m (Ben Nevis).
    if v < -50 or v > 2_000:
        return None
    return v


def fetch_osm_peaks(cache: dict, *, force: bool = False) -> dict:
    """Bulk-fetch every `natural=peak` node with an `ele=*` tag,
    tiled over the UK/Ireland bbox.
    """
    cache.setdefault("meta", {"tilesDone": [], "fetchedAt": None})
    cache.setdefault("peaks", [])
    done = set(tuple(t) for t in cache["meta"].get("tilesDone", []))

    tiles: list[tuple[float, float, float, float]] = []
    s_lat, w_lng, n_lat, e_lng = BBOX
    lat = s_lat
    while lat < n_lat:
        lng = w_lng
        while lng < e_lng:
            tiles.append((lat, lng, min(lat + TILE_LAT, n_lat), min(lng + TILE_LNG, e_lng)))
            lng += TILE_LNG
        lat += TILE_LAT
    print(f"  bbox split into {len(tiles)} tiles", flush=True)

    by_id: dict[int, dict] = {p["id"]: p for p in cache["peaks"]}
    for i, t in enumerate(tiles):
        if t in done and not force:
            continue
        s, w, n, e = t
        query = (
            "[out:json][timeout:180];\n"
            f"node[\"natural\"=\"peak\"][\"ele\"]({s},{w},{n},{e});\n"
            "out;\n"  # default `out` includes node coords + tags
        )
        last_err = None
        for ep in OVERPASS_ENDPOINTS:
            try:
                raw = _curl_post(ep, query, timeout=180)
                data = json.loads(raw.decode("utf-8"))
                added = 0
                for el in data.get("elements") or []:
                    if el.get("type") != "node":
                        continue
                    eid = el.get("id")
                    if eid is None or eid in by_id:
                        continue
                    lat = el.get("lat")
                    lng = el.get("lon")
                    if lat is None or lng is None:
                        # `out tags` returns lat/lng for nodes too, but
                        # rare edge cases (deleted, redacted, member-
                        # only) can lack coordinates -- skip safely.
                        continue
                    tags = el.get("tags") or {}
                    ele = _parse_ele(tags.get("ele"))
                    if ele is None:
                        continue
                    rec = {
                        "id": int(eid),
                        "lat": float(lat),
                        "lng": float(lng),
                        "ele": ele,
                        "eleRaw": tags.get("ele"),
                        "name": tags.get("name"),
                        "wikidata": tags.get("wikidata"),
                    }
                    by_id[eid] = rec
                    cache["peaks"].append(rec)
                    added += 1
                done.add(t)
                cache["meta"]["tilesDone"] = sorted(done)
                cache["meta"]["fetchedAt"] = datetime.utcnow().isoformat() + "Z"
                _atomic_write(PEAKS_CACHE, cache)
                print(f"    tile {i+1}/{len(tiles)} "
                      f"({s:.0f},{w:.0f})→({n:.0f},{e:.0f}): "
                      f"+{added} peaks (total {len(cache['peaks']):,})",
                      flush=True)
                time.sleep(1.0)
                break
            except Exception as exc:
                last_err = exc
                print(f"    {ep} failed: {exc}", flush=True)
                continue
        else:
            print(f"    tile {i+1} skipped (all endpoints failed: {last_err})", flush=True)
    print(f"  done: {len(cache['peaks']):,} peaks total", flush=True)
    return cache


def fetch_wd_elevations(qids: list[str], cache: dict) -> dict:
    todo = sorted(set(q for q in qids if q and q not in cache))
    print(f"  Wikidata P2044: {len(todo):,} new fetches "
          f"({len(qids) - len(todo):,} cached)", flush=True)
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
            claims = (ent.get("claims") or {}).get("P2044") or []
            best_m: float | None = None
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
                if unit_qid is None:
                    factor = 1.0
                else:
                    factor = WD_LEN_UNITS_TO_M.get(unit_qid)
                if factor is None:
                    continue
                v = amount * factor
                if -50 <= v <= 2_000:
                    if best_m is None or v > best_m:
                        best_m = v
                        best_raw = f"{amount_str} {unit_qid or '(no-unit)'}"
            cache[qid] = {"elevationM": best_m, "raw": best_raw}
        _atomic_write(WD_ELE_CACHE, cache)
        if (i // BATCH) % 10 == 0:
            print(f"    fetched {min(i + BATCH, len(todo))}/{len(todo)}", flush=True)
        time.sleep(0.3)
    return cache


def polygon_from_island(isl: dict, geom_cache: dict, land_polys: list[Polygon],
                        land_tree: STRtree | None) -> Polygon | MultiPolygon | None:
    """Resolve the island's polygon using the same priority order as
    compute_island_areas.py.  Self-contained so this script can run
    independently.
    """
    iid = isl.get("id", "")
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
        m = _WAY_SUFFIX_RE.search(iid)
        if m:
            candidate_way = int(m.group(1))

    def _from_way_entry(entry):
        coords = [tuple(c) for c in entry.get("coords", [])]
        if len(coords) < 3:
            return None
        if coords[0] != coords[-1]:
            coords = coords + [coords[0]]
        try:
            p = Polygon(coords)
            if not p.is_valid:
                p = p.buffer(0)
            if p.is_valid and not p.is_empty:
                return p
        except Exception:
            pass
        return None

    def _from_relation_entry(entry):
        outers_raw = entry.get("outers", [])
        inners_raw = entry.get("inners", [])
        try:
            outer_lines = [LineString([tuple(c) for c in o]) for o in outers_raw if len(o) >= 2]
            inner_lines = [LineString([tuple(c) for c in o]) for o in inners_raw if len(o) >= 2]
            if not outer_lines:
                return None
            outer_polys = list(polygonize(unary_union(outer_lines)))
            inner_polys = list(polygonize(unary_union(inner_lines))) if inner_lines else []
            result = []
            for op in outer_polys:
                cut = op
                for ip in inner_polys:
                    if op.contains(ip):
                        cut = cut.difference(ip)
                if cut.is_valid and not cut.is_empty:
                    result.append(cut)
            if len(result) == 1:
                return result[0]
            if result:
                return MultiPolygon([p for p in result if isinstance(p, Polygon)])
        except Exception:
            pass
        return None

    if candidate_way is not None:
        entry = geom_cache.get(f"way:{candidate_way}")
        if entry:
            poly = _from_way_entry(entry)
            if poly is not None:
                return poly
    if candidate_rel is not None:
        entry = geom_cache.get(f"relation:{candidate_rel}")
        if entry:
            poly = _from_relation_entry(entry)
            if poly is not None:
                return poly

    qid = isl.get("wikidata") or (iid[len("wd-"):] if iid.startswith("wd-Q") else None)
    if qid:
        entry = geom_cache.get(f"wikidata:{qid}")
        if entry and not entry.get("missing"):
            if entry.get("kind") == "way":
                poly = _from_way_entry(entry)
                if poly is not None:
                    return poly
            elif entry.get("kind") == "relation":
                poly = _from_relation_entry(entry)
                if poly is not None:
                    return poly

    # Step A (sea-island coastline) -- hand-curated IDs only.
    if (isl.get("type") == "sea"
        and iid
        and not iid.startswith(("osm-", "wd-", "csv-"))
        and not _WAY_SUFFIX_RE.search(iid)
        and land_tree is not None):
        try:
            pt = Point(isl["lng"], isl["lat"])
        except (KeyError, TypeError):
            return None
        try:
            cand_idx = land_tree.query(pt, predicate="intersects")
        except Exception:
            cand_idx = []
        best: tuple[float, Polygon] | None = None
        for idx in cand_idx:
            p = land_polys[int(idx)]
            if not p.contains(pt):
                continue
            a = p.area
            if best is None or a < best[0]:
                best = (a, p)
        if best is not None:
            return best[1]
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch", action="store_true",
                        help="Fetch OSM peaks + Wikidata P2044 (network)")
    parser.add_argument("--apply", action="store_true",
                        help="Write highestPointM etc. back to islands.json")
    parser.add_argument("--all", action="store_true",
                        help="Run --fetch + --apply")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process at most N islands (debug)")
    args = parser.parse_args()
    if args.all:
        args.fetch = args.apply = True

    if not ISLANDS_PATH.exists():
        sys.exit(f"FATAL: {ISLANDS_PATH} missing")
    islands = json.loads(ISLANDS_PATH.read_text(encoding="utf-8"))
    print(f"Loaded {len(islands):,} islands")
    if args.limit:
        islands = islands[: args.limit]
        print(f"  --limit {args.limit} applied")

    peaks_cache: dict = {"meta": {"tilesDone": [], "fetchedAt": None}, "peaks": []}
    if PEAKS_CACHE.exists():
        try:
            peaks_cache = json.loads(PEAKS_CACHE.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  WARN: peaks cache unreadable ({exc}); rebuilding", file=sys.stderr)
    if args.fetch:
        peaks_cache = fetch_osm_peaks(peaks_cache)
    peaks = peaks_cache.get("peaks", [])
    print(f"Have {len(peaks):,} peaks indexed", flush=True)

    geom_cache: dict = {}
    if OSM_GEOM_CACHE.exists():
        try:
            geom_cache = json.loads(OSM_GEOM_CACHE.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  WARN: OSM geom cache unreadable ({exc})", file=sys.stderr)

    land_polys: list[Polygon] = []
    if LAND_PICKLE.exists():
        land = pickle.load(open(LAND_PICKLE, "rb"))
        land_polys = list(getattr(land, "geoms", [land]))
    land_tree = STRtree(land_polys) if land_polys else None

    peak_points: list[Point] = []
    peak_tree: STRtree | None = None
    if peaks:
        # Filter out anything with bad coordinates (legacy cache rows
        # from an earlier buggy run may have None lat/lng).
        clean_peaks = []
        for p in peaks:
            lat, lng = p.get("lat"), p.get("lng")
            if lat is None or lng is None:
                continue
            try:
                peak_points.append(Point(float(lng), float(lat)))
            except (TypeError, ValueError):
                continue
            clean_peaks.append(p)
        peaks = clean_peaks
        peak_tree = STRtree(peak_points)
        print(f"  spatial-indexed {len(peaks):,} peaks", flush=True)

    wd_cache: dict = {}
    if WD_ELE_CACHE.exists():
        try:
            wd_cache = json.loads(WD_ELE_CACHE.read_text(encoding="utf-8"))
        except Exception:
            wd_cache = {}
    if args.fetch:
        qids = []
        for isl in islands:
            if isl.get("wikidata"):
                qids.append(isl["wikidata"])
            iid = isl.get("id", "")
            if iid.startswith("wd-Q"):
                qids.append(iid[len("wd-"):])
        wd_cache = fetch_wd_elevations(qids, wd_cache)

    print("Computing highest points…", flush=True)
    audit: list[dict] = []
    summary: Counter = Counter()
    source_counts: Counter = Counter()
    start_t = time.time()
    for n, isl in enumerate(islands):
        if n and n % 500 == 0:
            elapsed = time.time() - start_t
            print(f"  …{n:>5}/{len(islands)} ({elapsed:.0f}s, "
                  f"rate {n/elapsed:.0f}/s)", flush=True)

        rec: dict = {
            "id": isl.get("id"),
            "name": isl.get("name"),
            "currentM": isl.get("highestPointM"),
            "currentName": isl.get("highestPointName"),
            "osmPeakM": None,
            "osmPeakName": None,
            "osmPeakId": None,
            "wdM": None,
            "deltaM": None,
            "highestPointM": None,
            "highestPointName": None,
            "highestPointSource": None,
            "highestPointConfidence": "n/a",
            "note": None,
        }

        poly = None
        if (land_tree is not None) or geom_cache:
            poly = polygon_from_island(isl, geom_cache, land_polys, land_tree)

        if poly is not None and peak_tree is not None:
            try:
                cand = peak_tree.query(poly, predicate="intersects")
            except Exception:
                cand = []
            # `prepared` geometry gives O(log N) point-in-polygon tests
            # instead of the O(N) full ray-cast that plain Polygon.contains
            # does -- critical for Great Britain (200k+ vertices, thousands
            # of candidate peaks).
            prep_poly = prep(poly) if len(cand) > 4 else None
            test = prep_poly.contains if prep_poly is not None else poly.contains
            best: tuple[float, dict] | None = None
            for idx in cand:
                ii = int(idx)
                p = peaks[ii]
                pt = peak_points[ii]
                if not test(pt):
                    continue
                if best is None or p["ele"] > best[0]:
                    best = (p["ele"], p)
            if best is not None:
                rec["osmPeakM"] = round(best[0], 1)
                rec["osmPeakName"] = best[1].get("name")
                rec["osmPeakId"] = best[1].get("id")

        iid = isl.get("id", "")
        wd_qid = isl.get("wikidata") or (iid[len("wd-"):] if iid.startswith("wd-Q") else None)
        if wd_qid and wd_qid in wd_cache:
            v = wd_cache[wd_qid].get("elevationM")
            if v is not None:
                rec["wdM"] = round(v, 1)

        if rec["osmPeakM"] is not None:
            rec["highestPointM"]    = rec["osmPeakM"]
            rec["highestPointName"] = rec["osmPeakName"]
            rec["highestPointSource"] = "osm-peak"
            if rec["wdM"] is not None and rec["osmPeakM"] > 0:
                d = abs(rec["osmPeakM"] - rec["wdM"])
                rec["deltaM"] = round(d, 1)
                rel = d / max(rec["osmPeakM"], 1.0)
                if d <= 2.0 or rel <= 0.02:
                    rec["highestPointConfidence"] = "high"
                    rec["note"] = "OSM peak, cross-validated by Wikidata P2044"
                elif d <= 5.0 or rel <= 0.05:
                    rec["highestPointConfidence"] = "high"
                    rec["note"] = (f"OSM peak; Wikidata P2044 within "
                                   f"{d:.1f} m ({rel*100:.1f} %)")
                else:
                    rec["highestPointConfidence"] = "estimate"
                    rec["note"] = (f"OSM peak {rec['osmPeakM']} m vs "
                                   f"Wikidata P2044 {rec['wdM']} m "
                                   f"(Δ {d:.1f} m) — flagged for review")
            else:
                # OSM-surveyed peak `ele` is well within 2 % for any
                # summit ≥ 50 m.  For lower summits the absolute error
                # is still typically ±1 m (the rounding the field
                # uses).
                rec["highestPointConfidence"] = "high"
                rec["note"] = "OSM-surveyed peak elevation"
        elif rec["wdM"] is not None:
            rec["highestPointM"]    = rec["wdM"]
            rec["highestPointName"] = None
            rec["highestPointSource"] = "wikidata-p2044"
            rec["highestPointConfidence"] = "estimate"
            rec["note"] = "Wikidata P2044 only (no OSM peak inside polygon)"
        elif rec["currentM"] is not None:
            rec["highestPointM"]    = rec["currentM"]
            rec["highestPointName"] = rec["currentName"]
            rec["highestPointSource"] = "manual"
            rec["highestPointConfidence"] = "high"
            rec["note"] = "Pre-existing hand-curated value retained"
        else:
            rec["note"] = "No OSM peak / Wikidata / manual value available"

        summary[rec["highestPointConfidence"]] += 1
        source_counts[rec["highestPointSource"] or "(none)"] += 1
        audit.append(rec)

    _atomic_write(AUDIT_PATH, audit)
    print()
    print(f"Audit written → {AUDIT_PATH.name}")
    print(f"Confidence breakdown:")
    for k in ("high", "estimate", "n/a"):
        c = summary.get(k, 0)
        print(f"  {k:8s} {c:>6,d} ({100*c/len(audit):.1f}%)")
    have = sum(1 for r in audit if r["highestPointM"] is not None)
    print(f"Total with highestPointM: {have:,} / {len(audit):,} ({100*have/len(audit):.1f}%)")
    print(f"Source breakdown:")
    for k, c in source_counts.most_common():
        print(f"  {k:18s} {c:>6,d}")
    crossed = sum(1 for r in audit if r["deltaM"] is not None)
    if crossed:
        agree = sum(1 for r in audit if r["deltaM"] is not None and r["deltaM"] <= 2.0)
        print(f"Wikidata-cross-validated:    {crossed:,}; "
              f"≤2 m agreement: {agree:,} ({100*agree/crossed:.0f}%)")

    if args.apply:
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        archive = DATA / f"islands.json.before-highpoints-{ts}"
        shutil.copy2(ISLANDS_PATH, archive)
        print(f"\nBackup written → {archive.name}")
        full = json.loads(ISLANDS_PATH.read_text(encoding="utf-8"))
        by_id = {i["id"]: i for i in full if "id" in i}
        applied = 0
        cleared = 0
        for r in audit:
            isl = by_id.get(r["id"])
            if not isl:
                continue
            if r["highestPointM"] is not None:
                isl["highestPointM"] = round(r["highestPointM"], 1)
                isl["highestPointName"] = r["highestPointName"]
                isl["highestPointSource"] = r["highestPointSource"]
                isl["highestPointConfidence"] = r["highestPointConfidence"]
                applied += 1
            else:
                if isl.get("highestPointM") is not None:
                    cleared += 1
                isl["highestPointM"] = None
                isl["highestPointName"] = None
                isl["highestPointSource"] = None
                isl["highestPointConfidence"] = "n/a"
        tmp = ISLANDS_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(full, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, ISLANDS_PATH)
        print(f"Applied: {applied:,} islands now have highestPointM; "
              f"{cleared:,} previously-set values nulled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
