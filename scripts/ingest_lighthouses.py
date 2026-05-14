#!/usr/bin/env python3
"""
Ingest lighthouses and beacons from OpenStreetMap (``man_made=lighthouse``
and ``man_made=beacon``) cross-referenced with Wikidata for light
characteristic, established year, and operator (Northern Lighthouse
Board, Trinity House, Commissioners of Irish Lights).

Staging-only: writes ``data/cache_lighthouses.json`` keyed by
``islandId -> { lighthouses: [...], lighthousesSource,
lighthousesConfidence, lighthousesAttribution, lighthousesFetchedAt }``.

Approach
--------
1. **Bulk-fetch every ``man_made=lighthouse`` / ``man_made=beacon`` node
   or way in the UK + Ireland bbox.** OSM is the only reusable source
   under an unambiguous open licence (ODbL 1.0).  Statutory bodies
   (NLB / Trinity / CIL) publish lists on their websites but those
   pages don't carry a redistribute-with-attribution licence — we
   *cite* them as the underlying authority but do not scrape them.

2. **Spatial-index the lighthouses.** Same STRtree trick as
   ``compute_island_highpoints.py``.

3. **Attribute to an island** when its coordinates fall inside the
   island polygon (using the existing polygon priority chain).  If the
   coordinates fall *outside* but within 200 m of the polygon, attribute
   with ``offshore: true``.

4. **Cross-check** the OSM record's ``wikidata`` tag against the Wikidata
   API to extract:
   * P1030 (light characteristic)        → ``characteristic``
   * P571 (inception)                    → ``establishedYear``
   * P2048 (height)                      → ``heightM``
   * P137 (operator)                     → ``operator``
   * P5775 (image of lightroom interior) -> not used
   When the wikidata link is missing, fall back to OSM tags
   ``seamark:light:character`` / ``start_date`` / ``height``.

5. **Mandatory** ``notForNavigation: true`` on every record (ETHICS §10).

CLI::

    python3 scripts/ingest_lighthouses.py --dry-run
    python3 scripts/ingest_lighthouses.py --fetch --commit
    python3 scripts/ingest_lighthouses.py --fetch --limit 50 --verbose
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pickle
import re
import subprocess
import sys
import time
import urllib.parse
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

STAGED_CACHE = DATA / "cache_lighthouses.json"
OSM_LIGHT_CACHE = DATA / "cache_osm_lighthouses.json"
WD_LIGHT_CACHE = DATA / "cache_wd_lighthouses.json"
REPORT = DATA / "lighthouses_ingestion_report.json"

USER_AGENT = "isles-of-britain/0.8 (ingest_lighthouses; static-site)"
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
]
WIKIDATA_API = "https://www.wikidata.org/w/api.php"

# UK + Ireland + Crown + 50-mile fringe.
BBOX = (49.0, -11.5, 61.5, 2.5)
TILE_LAT = 2.0
TILE_LNG = 2.5

OFFSHORE_MAX_M = 200.0     # treat as "on island" if within this of polygon boundary

_WAY_SUFFIX_RE = re.compile(r"-w(\d+)$")

# Wikidata Q-IDs for known operators -> canonical name.
OPERATOR_QID = {
    "Q1521410": "Northern Lighthouse Board",
    "Q1554611": "Trinity House",
    "Q5152517": "Commissioners of Irish Lights",
}


# ---------- HTTP helpers ----------

def _curl_post(url: str, data: str, timeout: int = 180) -> bytes:
    res = subprocess.run(
        [
            "curl", "-sS", "--max-time", str(timeout),
            "-H", f"User-Agent: {USER_AGENT}",
            "-H", "Accept: application/json",
            "--data-urlencode", f"data={data}",
            url,
        ],
        capture_output=True, timeout=timeout + 30,
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"overpass curl failed: rc={res.returncode} "
            f"stderr={res.stderr.decode('utf-8','replace')[:200]}"
        )
    return res.stdout


def _curl_get(url: str, params: dict[str, Any], timeout: int = 60) -> dict:
    qs = urllib.parse.urlencode(params, doseq=True)
    full = f"{url}?{qs}"
    backoff = [1.0, 3.0, 8.0, 20.0]
    last: str | None = None
    for d in backoff:
        try:
            res = subprocess.run(
                ["curl", "-sS", "--max-time", str(timeout),
                 "-H", f"User-Agent: {USER_AGENT}",
                 "-H", "Accept: application/json", full],
                capture_output=True, timeout=timeout + 15,
            )
        except subprocess.TimeoutExpired as exc:
            last = f"timeout: {exc}"; time.sleep(d); continue
        if res.returncode != 0:
            last = f"rc={res.returncode}"; time.sleep(d); continue
        body = res.stdout.decode("utf-8", "replace")
        if not body.lstrip().startswith(("{", "[")):
            last = f"non-JSON: {body[:120]!r}"; time.sleep(d); continue
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            last = f"json decode: {exc}"; time.sleep(d); continue
    raise RuntimeError(f"_curl_get giving up: {last}")


def _atomic_write_json(path: Path, payload: Any, *, compact: bool = False) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    body = (json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            if compact else json.dumps(payload, ensure_ascii=False, indent=2))
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, path)


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"  WARN: {path.name} unreadable ({exc})", file=sys.stderr)
        return default


# ---------- Polygon resolution (same as DoBIH) ----------

def _from_way_entry(entry: dict) -> Polygon | None:
    coords = [tuple(c) for c in entry.get("coords", [])]
    if len(coords) < 3: return None
    if coords[0] != coords[-1]: coords = coords + [coords[0]]
    try:
        p = Polygon(coords)
        if not p.is_valid: p = p.buffer(0)
        if p.is_valid and not p.is_empty: return p
    except Exception: return None
    return None


def _from_relation_entry(entry: dict) -> Polygon | MultiPolygon | None:
    outers_raw = entry.get("outers", [])
    inners_raw = entry.get("inners", [])
    try:
        outer_lines = [LineString([tuple(c) for c in o]) for o in outers_raw if len(o) >= 2]
        inner_lines = [LineString([tuple(c) for c in o]) for o in inners_raw if len(o) >= 2]
        if not outer_lines: return None
        outer_polys = list(polygonize(unary_union(outer_lines)))
        inner_polys = list(polygonize(unary_union(inner_lines))) if inner_lines else []
        result: list[Polygon] = []
        for op in outer_polys:
            cut = op
            for ip in inner_polys:
                if op.contains(ip): cut = cut.difference(ip)
            if cut.is_valid and not cut.is_empty and isinstance(cut, Polygon):
                result.append(cut)
        if len(result) == 1: return result[0]
        if result: return MultiPolygon(result)
    except Exception: return None
    return None


def polygon_for_island(isl: dict, geom_cache: dict,
                      land_polys: list[Polygon],
                      land_tree: STRtree | None) -> Polygon | MultiPolygon | None:
    iid = isl.get("id", "")
    cand_way: int | None = None; cand_rel: int | None = None
    if iid.startswith("osm-way-"):
        try: cand_way = int(iid[len("osm-way-"):])
        except ValueError: pass
    elif iid.startswith("osm-relation-"):
        try: cand_rel = int(iid[len("osm-relation-"):])
        except ValueError: pass
    else:
        m = _WAY_SUFFIX_RE.search(iid)
        if m: cand_way = int(m.group(1))
    if cand_way is not None:
        e = geom_cache.get(f"way:{cand_way}")
        if e:
            p = _from_way_entry(e)
            if p is not None: return p
    if cand_rel is not None:
        e = geom_cache.get(f"relation:{cand_rel}")
        if e:
            p = _from_relation_entry(e)
            if p is not None: return p
    qid = isl.get("wikidata") or (iid[len("wd-"):] if iid.startswith("wd-Q") else None)
    if qid:
        e = geom_cache.get(f"wikidata:{qid}")
        if e and not e.get("missing"):
            if e.get("kind") == "way":
                p = _from_way_entry(e)
                if p is not None: return p
            elif e.get("kind") == "relation":
                p = _from_relation_entry(e)
                if p is not None: return p
    if (isl.get("type") == "sea" and iid
            and not iid.startswith(("osm-", "wd-", "csv-"))
            and not _WAY_SUFFIX_RE.search(iid)
            and land_tree is not None):
        try:
            pt = Point(isl["lng"], isl["lat"])
        except (KeyError, TypeError): return None
        try: cand_idx = land_tree.query(pt, predicate="intersects")
        except Exception: cand_idx = []
        best: tuple[float, Polygon] | None = None
        for idx in cand_idx:
            p = land_polys[int(idx)]
            if not p.contains(pt): continue
            a = p.area
            if best is None or a < best[0]: best = (a, p)
        if best is not None: return best[1]
    return None


# ---------- Overpass: fetch lighthouses ----------

def fetch_osm_lighthouses(cache: dict, *, force: bool = False) -> dict:
    """Bulk-fetch every man_made=lighthouse or beacon in the UK/IE bbox."""
    cache.setdefault("meta", {"tilesDone": [], "fetchedAt": None})
    cache.setdefault("elements", [])
    done = set(tuple(t) for t in cache["meta"].get("tilesDone", []))

    tiles: list[tuple[float, float, float, float]] = []
    s_lat, w_lng, n_lat, e_lng = BBOX
    lat = s_lat
    while lat < n_lat:
        lng = w_lng
        while lng < e_lng:
            tiles.append((lat, lng, min(lat + TILE_LAT, n_lat),
                          min(lng + TILE_LNG, e_lng)))
            lng += TILE_LNG
        lat += TILE_LAT
    print(f"  bbox split into {len(tiles)} tiles", flush=True)
    by_key: dict[str, dict] = {f"{e.get('type')}/{e.get('id')}": e
                               for e in cache["elements"]}
    for i, t in enumerate(tiles):
        if t in done and not force:
            continue
        s, w, n, e = t
        # Cover man_made=lighthouse and beacon (which includes beacons,
        # daymarks, perches).  We grab nodes, ways, and relations.
        q = (
            "[out:json][timeout:180];\n"
            "(\n"
            f'  node["man_made"~"^(lighthouse|beacon)$"]({s},{w},{n},{e});\n'
            f'  way["man_made"~"^(lighthouse|beacon)$"]({s},{w},{n},{e});\n'
            f'  relation["man_made"~"^(lighthouse|beacon)$"]({s},{w},{n},{e});\n'
            ");\n"
            "out center tags;\n"   # `center` gives a representative lat/lng for ways/relations
        )
        last_err = None
        for ep in OVERPASS_ENDPOINTS:
            try:
                raw = _curl_post(ep, q, timeout=180)
                payload = json.loads(raw.decode("utf-8"))
                added = 0
                for el in payload.get("elements") or []:
                    et = el.get("type"); eid = el.get("id")
                    if et is None or eid is None: continue
                    key = f"{et}/{eid}"
                    if key in by_key: continue
                    if et == "node":
                        la, lo = el.get("lat"), el.get("lon")
                    else:
                        c = el.get("center") or {}
                        la, lo = c.get("lat"), c.get("lon")
                    if la is None or lo is None: continue
                    rec = {
                        "type": et, "id": int(eid),
                        "lat": float(la), "lng": float(lo),
                        "tags": el.get("tags") or {},
                    }
                    by_key[key] = rec
                    cache["elements"].append(rec)
                    added += 1
                done.add(t)
                cache["meta"]["tilesDone"] = sorted(done)
                cache["meta"]["fetchedAt"] = dt.datetime.now(
                    dt.timezone.utc).isoformat(timespec="seconds")
                _atomic_write_json(OSM_LIGHT_CACHE, cache)
                print(f"    tile {i+1}/{len(tiles)}: +{added} "
                      f"(total {len(cache['elements']):,})", flush=True)
                time.sleep(1.0)
                break
            except Exception as exc:
                last_err = exc
                print(f"    {ep} failed: {exc}", flush=True)
                continue
        else:
            print(f"    tile {i+1} skipped (all endpoints failed: {last_err})",
                  flush=True)
    print(f"  done: {len(cache['elements']):,} OSM lighthouse/beacon elements")
    return cache


# ---------- Wikidata enrichment ----------

def fetch_wd_lighthouses(qids: list[str], cache: dict) -> dict[str, dict]:
    todo = sorted(set(q for q in qids if q and q not in cache and re.match(r"^Q\d+$", q)))
    print(f"  Wikidata: {len(todo):,} new fetches "
          f"({len(qids) - len(todo):,} cached)", flush=True)
    BATCH = 40
    for i in range(0, len(todo), BATCH):
        batch = todo[i: i + BATCH]
        try:
            payload = _curl_get(WIKIDATA_API, {
                "action": "wbgetentities",
                "format": "json",
                "ids": "|".join(batch),
                "props": "claims|sitelinks",
                "sitefilter": "enwiki",
            })
        except Exception as exc:
            print(f"    batch failed: {exc}", file=sys.stderr)
            continue
        ents = payload.get("entities") or {}
        for q in batch:
            ent = ents.get(q) or {}
            cl = ent.get("claims") or {}
            sl = (ent.get("sitelinks") or {}).get("enwiki") or {}
            rec: dict[str, Any] = {"qid": q}
            # P1030 - light characteristic (string statement, free-form)
            for c in cl.get("P1030") or []:
                v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
                if isinstance(v, str) and v.strip():
                    rec["characteristic"] = v.strip(); break
                if isinstance(v, dict) and v.get("text"):
                    rec["characteristic"] = v["text"].strip(); break
            # P571 - inception
            for c in cl.get("P571") or []:
                v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}
                t = (v or {}).get("time") or ""
                m = re.match(r"\+?(\d{4})", t)
                if m:
                    rec["establishedYear"] = int(m.group(1)); break
            # P2048 - height (quantity, must be metres)
            for c in cl.get("P2048") or []:
                v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}
                amt = (v or {}).get("amount") or ""
                unit = (v or {}).get("unit") or ""
                if amt and unit.endswith("Q11573"):    # metre
                    try:
                        rec["heightM"] = float(amt.lstrip("+"))
                        break
                    except ValueError:
                        pass
            # P137 - operator
            for c in cl.get("P137") or []:
                v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}
                qq = v.get("id") if isinstance(v, dict) else None
                if qq and qq in OPERATOR_QID:
                    rec["operator"] = OPERATOR_QID[qq]; break
                elif qq:
                    rec["operator"] = qq    # leave as Q-ID; UI can resolve later
                    break
            if sl.get("title"):
                rec["wikipedia"] = "https://en.wikipedia.org/wiki/" + \
                    urllib.parse.quote((sl["title"] or "").replace(" ", "_"))
            cache[q] = rec
        _atomic_write_json(WD_LIGHT_CACHE, cache)
        if (i // BATCH) % 5 == 0:
            print(f"    fetched {min(i + BATCH, len(todo))}/{len(todo)}", flush=True)
        time.sleep(0.4)
    return cache


# ---------- Build per-island staging payload ----------

# Operators inferred from the OSM `operator=*` tag where the wikidata
# claim is absent.  Keep this list short and authoritative.
OPERATOR_TAGS = {
    "northern lighthouse board": "Northern Lighthouse Board",
    "nlb":                       "Northern Lighthouse Board",
    "trinity house":             "Trinity House",
    "trinity house lighthouse service": "Trinity House",
    "commissioners of irish lights": "Commissioners of Irish Lights",
    "cil":                       "Commissioners of Irish Lights",
    "irish lights":              "Commissioners of Irish Lights",
}


def _operator_from_tags(tags: dict) -> str | None:
    raw = (tags.get("operator") or "").strip().lower()
    if not raw:
        return None
    for k, v in OPERATOR_TAGS.items():
        if k in raw:
            return v
    return raw.title()


def _status_from_tags(tags: dict, wd: dict) -> str:
    if (tags.get("disused") or "").lower() == "yes":
        return "deactivated"
    if (tags.get("man_made") or "") == "beacon":
        return "operational" if tags.get("seamark:light:character") else "passive-marker"
    if tags.get("automated") == "yes":
        return "automated"
    if tags.get("seamark:status") in ("disused", "removed", "destroyed"):
        return "deactivated"
    return "operational"


def _char_from_tags(tags: dict) -> str | None:
    # Compose like "Fl(2) W 30s" from seamark tags when present.
    char = (tags.get("seamark:light:character") or "").strip()
    if not char:
        return None
    colour = (tags.get("seamark:light:colour") or "").strip()
    group = (tags.get("seamark:light:group") or "").strip()
    period = (tags.get("seamark:light:period") or "").strip()
    parts: list[str] = []
    if group:
        parts.append(f"{char.upper()}({group})")
    else:
        parts.append(char.upper())
    if colour:
        parts.append(colour[:1].upper())
    if period:
        parts.append(f"{period}s")
    return " ".join(parts) or None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fetch", action="store_true",
                    help="Run the Overpass + Wikidata fetches (network)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Compute in memory; do not write cache_lighthouses.json")
    ap.add_argument("--commit", action="store_true",
                    help="Write the final cache_lighthouses.json")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if not ISLANDS_PATH.exists():
        sys.exit(f"FATAL: {ISLANDS_PATH} missing")
    islands = _load_json(ISLANDS_PATH, [])
    if not islands: sys.exit("FATAL: islands.json empty")
    print(f"Loaded {len(islands):,} islands")

    # 1. OSM elements
    osm_cache = _load_json(OSM_LIGHT_CACHE, {})
    if args.fetch:
        osm_cache = fetch_osm_lighthouses(osm_cache)
    elements: list[dict] = osm_cache.get("elements", [])
    print(f"  OSM elements available: {len(elements):,}")
    if not elements:
        print("WARN: no OSM data; pass --fetch on first run", file=sys.stderr)

    # 2. Wikidata cross-check
    wd_cache = _load_json(WD_LIGHT_CACHE, {})
    qids = [el["tags"].get("wikidata") for el in elements]
    qids = [q for q in qids if q]
    if args.fetch and qids:
        wd_cache = fetch_wd_lighthouses(qids, wd_cache)
    print(f"  Wikidata enriched: {len(wd_cache):,} entries")

    # 3. Spatial index
    pts: list[Point] = []
    clean: list[dict] = []
    for el in elements:
        try:
            pts.append(Point(float(el["lng"]), float(el["lat"])))
        except (TypeError, KeyError, ValueError):
            continue
        clean.append(el)
    elements = clean
    tree = STRtree(pts) if pts else None
    print(f"  spatial-indexed {len(pts):,} elements")

    # 4. Polygon resources
    geom_cache = _load_json(OSM_GEOM_CACHE, {})
    land_polys: list[Polygon] = []
    if LAND_PICKLE.exists():
        try:
            land = pickle.load(open(LAND_PICKLE, "rb"))
            land_polys = list(getattr(land, "geoms", [land]))
        except Exception as exc:
            print(f"  WARN: land pickle ({exc})", file=sys.stderr)
    land_tree = STRtree(land_polys) if land_polys else None

    # 5. Walk islands
    if args.limit:
        islands = islands[: args.limit]
    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    staged: dict[str, dict] = {}
    audit: list[dict] = []
    counts = {"with_lights": 0, "with_offshore_only": 0, "no_polygon": 0}
    for n, isl in enumerate(islands):
        if n and n % 500 == 0:
            print(f"  …{n}/{len(islands)} (so far {counts['with_lights']} islands)",
                  flush=True)
        iid = isl.get("id")
        if not iid: continue
        poly = polygon_for_island(isl, geom_cache, land_polys, land_tree)
        if poly is None or tree is None:
            counts["no_polygon"] += 1; continue
        # Buffered candidate set: 200 m buffer for offshore detection.
        # OSM uses WGS84 degrees; 200 m at UK latitudes ≈ 0.0022° lat /
        # 0.0035° lng.  We use a degree-buffered envelope as a cheap
        # candidate filter, then test "inside" vs "within 200 m" via
        # planar haversine.
        try:
            cand_idx = tree.query(poly.buffer(0.003), predicate="intersects")
        except Exception:
            cand_idx = []
        prep_poly = prep(poly) if len(cand_idx) > 4 else None
        contains = prep_poly.contains if prep_poly is not None else poly.contains
        matched: list[dict] = []
        for idx in cand_idx:
            ii = int(idx)
            pt = pts[ii]
            el = elements[ii]
            on_island = contains(pt)
            if not on_island:
                # Check planar distance to polygon boundary; if ≤ 200 m, flag offshore.
                try:
                    dx_deg = poly.distance(pt)
                except Exception:
                    continue
                # Approx degrees-to-metres conversion at the island latitude.
                lat_mid = float(isl.get("lat", 55.0))
                deg_per_m_lat = 1.0 / 111_111.0
                deg_per_m_lng = 1.0 / (111_111.0 * max(0.1,
                                                       __import__("math").cos(__import__("math").radians(lat_mid))))
                # Use the larger conversion so we're conservative (more likely to flag).
                cutoff_deg = OFFSHORE_MAX_M * max(deg_per_m_lat, deg_per_m_lng)
                if dx_deg > cutoff_deg:
                    continue
                offshore = True
            else:
                offshore = False
            tags = el.get("tags") or {}
            qid = (tags.get("wikidata") or "").strip()
            wd = wd_cache.get(qid, {}) if qid else {}
            name = (tags.get("name:en") or tags.get("name")
                    or wd.get("name") or "Unnamed lighthouse")
            # Established year: WD wins; OSM start_date fallback.
            est_year = wd.get("establishedYear")
            if est_year is None:
                sd = tags.get("start_date") or ""
                m = re.match(r"(\d{4})", sd)
                if m: est_year = int(m.group(1))
            # Height: WD wins, OSM height=* fallback.
            height_m = wd.get("heightM")
            if height_m is None:
                h = (tags.get("height") or "").strip().rstrip("m").strip()
                try:
                    height_m = float(h) if h else None
                except ValueError:
                    height_m = None
            # Range (nm): OSM seamark:light:range, in nautical miles.
            range_nm = None
            r = (tags.get("seamark:light:range") or "").strip()
            try:
                range_nm = float(r) if r else None
            except ValueError:
                range_nm = None
            # Characteristic: prefer Wikidata P1030 then OSM seamark tags.
            character = wd.get("characteristic") or _char_from_tags(tags)
            operator = (wd.get("operator") or _operator_from_tags(tags))
            status = _status_from_tags(tags, wd)
            rec = {
                "name": name,
                "characteristic": character,
                "rangeNm": range_nm,
                "heightM": round(height_m, 1) if height_m else None,
                "establishedYear": est_year,
                "status": status,
                "operator": operator,
                "lat": round(float(el["lat"]), 5),
                "lng": round(float(el["lng"]), 5),
                "offshore": offshore,
                "osmType": el.get("type"),
                "osmId": el.get("id"),
                "wikidata": qid or None,
                "wikipedia": wd.get("wikipedia"),
                "notForNavigation": True,            # ETHICS §10
            }
            matched.append(rec)
        if not matched:
            continue
        only_offshore = all(r["offshore"] for r in matched)
        if only_offshore:
            counts["with_offshore_only"] += 1
        else:
            counts["with_lights"] += 1
        staged[iid] = {
            "lighthouses": matched,
            "lighthousesSource": "osm-man-made-lighthouse+wikidata",
            "lighthousesConfidence": "high" if not only_offshore else "medium",
            "lighthousesAttribution": (
                "© OpenStreetMap contributors (ODbL 1.0); "
                "cross-checked against Northern Lighthouse Board, "
                "Trinity House, and Commissioners of Irish Lights "
                "public station lists."
            ),
            "lighthousesFetchedAt": fetched_at,
        }
        if len(audit) < 50:
            audit.append({"id": iid, "name": isl.get("name"),
                          "lightCount": len(matched),
                          "first": matched[0]})
        if args.verbose:
            print(f"  + {isl.get('name')}: {len(matched)} lights "
                  f"(first: {matched[0]['name']!r})", flush=True)

    report = {
        "startedAt": fetched_at,
        "totalOSMElements": len(elements),
        "totalWdEntries": len(wd_cache),
        "islandsProcessed": len(islands),
        "islandsWithLights": counts["with_lights"],
        "islandsWithOffshoreOnly": counts["with_offshore_only"],
        "islandsWithoutPolygon": counts["no_polygon"],
        "sampleAudit": audit,
        "dryRun": bool(args.dry_run or not args.commit),
    }
    _atomic_write_json(REPORT, report)
    print()
    print(f"Audit  → {REPORT.name}")
    print(f"Coverage: {counts['with_lights']:,} islands have ≥1 light, "
          f"+{counts['with_offshore_only']:,} with only offshore lights")
    print(f"  without polygon: {counts['no_polygon']:,}")

    if args.dry_run:
        print(f"\nDRY RUN — cache_lighthouses.json NOT written. "
              f"Would have staged {len(staged):,} islands.")
        return 0
    if not args.commit:
        print(f"\n(--commit not supplied; cache_lighthouses.json NOT written.)")
        return 0
    _atomic_write_json(STAGED_CACHE, staged)
    print(f"\nStaged cache → {STAGED_CACHE.name} ({len(staged):,} islands)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
