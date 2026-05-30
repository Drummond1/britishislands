#!/usr/bin/env python3
"""
Ingest classified hills (Munros, Corbetts, Grahams, Donalds, Murdos,
Marilyns, HuMPs, Hewitts, Nuttalls, Wainwrights, Birketts) from the
Database of British and Irish Hills (DoBIH; Jackson, Dawson et al.),
and join them to islands via point-in-polygon.

Staging-only: this script NEVER mutates ``data/islands.json``.  It
writes a single staged cache file at ``data/cache_dobih.json`` keyed by
``islandId -> { hillsOn: [...], hillsOnSource, hillsOnConfidence,
hillsOnAttribution, hillsOnFetchedAt }``.  The merge into islands.json
is performed by ``scripts/apply_enrichments.sh`` once the overnight
chain has finished.

Inputs (in priority order)
--------------------------
1. ``--dobih-csv <path>`` — the official DoBIH CSV export from
   <https://www.hills-database.co.uk/downloads.html>.  Requires the
   user to register and download; we never bypass the registration
   gate.  When supplied, this is the canonical source.
2. Wikidata SPARQL fallback — for every hill instance-of
   Munro (Q1419786) / Corbett (Q5172995) / Graham (Q5594127) /
   Donald (Q5294796) / Marilyn (Q6760981) / HuMP (Q63432379) we fetch
   the name, coordinates, P2044 elevation, and (where present) DoBIH
   ID via P5283.  This is fully open (CC0) and gives us a CC-BY 4.0
   citation chain back to DoBIH.
3. OSM ``natural=peak`` (already cached at ``data/cache_osm_peaks.json``)
   — used only to recover coordinates if Wikidata/DoBIH lack them.

Outputs
-------
* ``data/cache_dobih.json`` — staged per-island enrichment payload.
* ``data/cache_wd_hills.json`` — raw Wikidata SPARQL response cache.
* ``data/dobih_ingestion_report.json`` — audit report.

CLI
---
::

    python3 scripts/ingest_hills_dobih.py --dry-run
    python3 scripts/ingest_hills_dobih.py --dry-run --limit 50
    python3 scripts/ingest_hills_dobih.py --fetch          # do the SPARQL
    python3 scripts/ingest_hills_dobih.py --dobih-csv data/dobih_v17_3.csv
    python3 scripts/ingest_hills_dobih.py --fetch --commit # produce final cache_dobih.json

Schema written into the cache (one entry per island that has ≥1 hill):

.. code-block:: jsonc

    {
      "isle-of-skye": {
        "hillsOn": [
          {
            "name": "Sgùrr Alasdair",
            "classifications": ["Munro", "Marilyn"],
            "elevationM": 992,
            "prominenceM": 992,
            "lat": 57.2087, "lng": -6.2236,
            "dobihId": 4061,
            "osmNodeId": 1242503981,
            "wikidata": "Q1369681",
            "wikipedia": "https://en.wikipedia.org/wiki/Sgùrr_Alasdair"
          }, ...
        ],
        "hillsOnSource": "wikidata-p2044+dobih-v17",
        "hillsOnConfidence": "high",
        "hillsOnAttribution": "Database of British and Irish Hills (Jackson, Dawson, et al.), CC-BY 4.0 — https://www.hills-database.co.uk/",
        "hillsOnFetchedAt": "2026-05-13T08:00:00+00:00"
      }, ...
    }
"""

from __future__ import annotations

import argparse
import csv
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
OSM_PEAKS_CACHE = DATA / "cache_osm_peaks.json"

STAGED_CACHE = DATA / "cache_dobih.json"
WD_HILLS_CACHE = DATA / "cache_wd_hills.json"
REPORT = DATA / "dobih_ingestion_report.json"

USER_AGENT = (
    "isles-of-britain/0.8 (ingest_hills_dobih; +https://github.com/local-atlas)"
)

WD_SPARQL = "https://query.wikidata.org/sparql"

# Classification "prestige" order — when a hill belongs to multiple
# classes, the most commonly cited goes first.  This matches the way
# climbers and DoBIH itself rank them.
CLASS_PRIORITY = [
    "Munro", "Furth", "Corbett", "Graham", "Donald",
    "Murdo", "Marilyn", "HuMP", "Hewitt", "Nuttall",
    "Wainwright", "Birkett", "TuMP",
]
CLASS_RANK = {c: i for i, c in enumerate(CLASS_PRIORITY)}

# Wikidata Q-IDs for each classification.  Source:
# https://www.wikidata.org/wiki/Property:P31
CLASS_QID = {
    "Munro":      "Q1419786",
    "Corbett":    "Q5172995",
    "Graham":     "Q5594127",
    "Donald":     "Q5294796",
    "Marilyn":    "Q6760981",
    "HuMP":       "Q63432379",
    "Hewitt":     "Q4127559",
    "Nuttall":    "Q47488815",
    "Wainwright": "Q1408143",
    "Birkett":    "Q4915022",
    "Furth":      "Q5511079",
    "Murdo":      "Q24037280",
}

_WAY_SUFFIX_RE = re.compile(r"-w(\d+)$")

# ---------- HTTP / I/O helpers ----------

def _curl_post(url: str, data: dict[str, str], timeout: int = 120,
               max_retries: int = 5) -> bytes:
    """Form-POST via curl with 429-aware exponential backoff.

    The Wikidata SPARQL endpoint is generous on burst but enforces
    a soft cap: HTTP 429 returns an HTML error page, which won't
    parse as JSON.  We back off and retry, with progressively longer
    sleeps, since the underlying SPARQL is idempotent.
    """
    args_base = ["curl", "-sS", "--max-time", str(timeout),
                 "-H", f"User-Agent: {USER_AGENT}",
                 "-H", "Accept: application/sparql-results+json",
                 "-w", "\nHTTP_STATUS:%{http_code}"]
    for k, v in data.items():
        args_base += ["--data-urlencode", f"{k}={v}"]
    args_base.append(url)
    backoffs = [5.0, 15.0, 45.0, 120.0, 300.0, 600.0]
    last_status = None
    for attempt in range(max_retries):
        res = subprocess.run(args_base, capture_output=True, timeout=timeout + 30)
        if res.returncode != 0:
            raise RuntimeError(
                f"curl failed for {url}: rc={res.returncode} "
                f"stderr={res.stderr.decode('utf-8','replace')[:300]}"
            )
        body = res.stdout
        # Strip trailing 'HTTP_STATUS:<code>' marker we added via -w.
        m = body.rfind(b"\nHTTP_STATUS:")
        if m >= 0:
            try:
                last_status = int(body[m + len(b"\nHTTP_STATUS:"):].strip())
            except ValueError:
                last_status = None
            body = body[:m]
        if last_status == 429 or (last_status and 500 <= last_status < 600):
            sleep = backoffs[min(attempt, len(backoffs) - 1)]
            print(f"    [HTTP {last_status} → sleeping {sleep:.0f}s]",
                  file=sys.stderr, flush=True)
            time.sleep(sleep)
            continue
        if not body.lstrip().startswith(b"{"):
            # JSON expected; got an HTML error page. Back off and retry.
            sleep = backoffs[min(attempt, len(backoffs) - 1)]
            print(f"    [non-JSON body (status={last_status}); sleeping {sleep:.0f}s]",
                  file=sys.stderr, flush=True)
            time.sleep(sleep)
            continue
        return body
    raise RuntimeError(f"_curl_post giving up (last status: {last_status})")


def _atomic_write_json(path: Path, payload: Any, *, compact: bool = False) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    if compact:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    else:
        body = json.dumps(payload, ensure_ascii=False, indent=2)
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, path)


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"  WARN: {path.name} unreadable ({exc}); ignoring", file=sys.stderr)
        return default


# ---------- Polygon resolution (lifted from compute_island_highpoints.py) ----------

def _from_way_entry(entry: dict) -> Polygon | None:
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
        return None
    return None


def _from_relation_entry(entry: dict) -> Polygon | MultiPolygon | None:
    outers_raw = entry.get("outers", [])
    inners_raw = entry.get("inners", [])
    try:
        outer_lines = [LineString([tuple(c) for c in o]) for o in outers_raw if len(o) >= 2]
        inner_lines = [LineString([tuple(c) for c in o]) for o in inners_raw if len(o) >= 2]
        if not outer_lines:
            return None
        outer_polys = list(polygonize(unary_union(outer_lines)))
        inner_polys = list(polygonize(unary_union(inner_lines))) if inner_lines else []
        result: list[Polygon] = []
        for op in outer_polys:
            cut = op
            for ip in inner_polys:
                if op.contains(ip):
                    cut = cut.difference(ip)
            if cut.is_valid and not cut.is_empty and isinstance(cut, Polygon):
                result.append(cut)
        if len(result) == 1:
            return result[0]
        if result:
            return MultiPolygon(result)
    except Exception:
        return None
    return None


def polygon_for_island(
    isl: dict,
    geom_cache: dict,
    land_polys: list[Polygon],
    land_tree: STRtree | None,
) -> Polygon | MultiPolygon | None:
    iid = isl.get("id", "")
    candidate_way: int | None = None
    candidate_rel: int | None = None
    if iid.startswith("osm-way-"):
        try: candidate_way = int(iid[len("osm-way-"):])
        except ValueError: pass
    elif iid.startswith("osm-relation-"):
        try: candidate_rel = int(iid[len("osm-relation-"):])
        except ValueError: pass
    else:
        m = _WAY_SUFFIX_RE.search(iid)
        if m:
            candidate_way = int(m.group(1))
    if candidate_way is not None:
        entry = geom_cache.get(f"way:{candidate_way}")
        if entry:
            p = _from_way_entry(entry)
            if p is not None:
                return p
    if candidate_rel is not None:
        entry = geom_cache.get(f"relation:{candidate_rel}")
        if entry:
            p = _from_relation_entry(entry)
            if p is not None:
                return p
    qid = isl.get("wikidata") or (iid[len("wd-"):] if iid.startswith("wd-Q") else None)
    if qid:
        entry = geom_cache.get(f"wikidata:{qid}")
        if entry and not entry.get("missing"):
            if entry.get("kind") == "way":
                p = _from_way_entry(entry)
                if p is not None: return p
            elif entry.get("kind") == "relation":
                p = _from_relation_entry(entry)
                if p is not None: return p
    # Step A: hand-curated sea islands only.
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


# ---------- DoBIH CSV reader ----------

# Column names in the official DoBIH CSV (as of v17.3, 2025-09-XX). The
# CSV header has 90+ columns; we keep only the ones we need.  We
# deliberately tolerate header variation across releases.
_DOBIH_CLASS_COLS = {
    # DoBIH column suffix -> our classification name.
    "Ma": "Marilyn",
    "Hu": "HuMP",
    "Tu": "TuMP",
    "Sim": "Marilyn",          # Simm: sub-Marilyn — fold under Marilyn for our taxonomy
    "M": "Munro",
    "MT": "Munro",
    "F": "Furth",
    "C": "Corbett",
    "G": "Graham",
    "D": "Donald",
    "DT": "Donald",
    "Mur": "Murdo",
    "Hew": "Hewitt",
    "N": "Nuttall",
    "W": "Wainwright",
    "B": "Birkett",
}


def parse_dobih_csv(path: Path) -> list[dict]:
    """Parse the DoBIH CSV into our internal hill record format."""
    if not path.exists():
        raise FileNotFoundError(path)
    out: list[dict] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            # Coordinates: DoBIH provides Latitude / Longitude (WGS84).
            try:
                lat = float(row.get("Latitude") or row.get("Lat") or "")
                lng = float(row.get("Longitude") or row.get("Lon") or "")
            except (TypeError, ValueError):
                continue
            try:
                ele = float(row.get("Metres") or row.get("Height") or "")
            except (TypeError, ValueError):
                ele = None
            try:
                drop = float(row.get("Drop") or "")
            except (TypeError, ValueError):
                drop = None
            classes: list[str] = []
            seen: set[str] = set()
            for col, label in _DOBIH_CLASS_COLS.items():
                # DoBIH marks classification membership with '1' in that column.
                v = (row.get(col) or "").strip()
                if v == "1" and label not in seen:
                    classes.append(label)
                    seen.add(label)
            if not classes:
                # Not a classified hill in DoBIH; we don't carry these
                # since the dataset is enormous and contains every
                # surveyed bump.
                continue
            classes.sort(key=lambda c: CLASS_RANK.get(c, 99))
            try:
                dobih_id = int(row.get("Number") or row.get("DoBIH Number") or "")
            except (TypeError, ValueError):
                dobih_id = None
            out.append({
                "name": (row.get("Name") or "").strip() or None,
                "lat": lat,
                "lng": lng,
                "elevationM": ele,
                "prominenceM": drop,
                "classifications": classes,
                "dobihId": dobih_id,
                "wikidata": None,           # not in CSV; filled by enrichment if needed
                "osmNodeId": None,
            })
    return out


# ---------- Wikidata SPARQL fallback ----------

_SPARQL_TMPL = """
SELECT ?h ?hLabel ?lat ?lon ?ele ?dobih ?wp WHERE {{
  ?h wdt:P31 wd:{qid} .
  OPTIONAL {{ ?h p:P625 ?stmt . ?stmt psv:P625 ?coord . ?coord wikibase:geoLatitude ?lat ; wikibase:geoLongitude ?lon . }}
  OPTIONAL {{ ?h wdt:P2044 ?ele . }}
  OPTIONAL {{ ?h wdt:P5283 ?dobih . }}
  OPTIONAL {{ ?wp schema:about ?h ; schema:isPartOf <https://en.wikipedia.org/> . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
"""

# Single request for all hill classes — avoids 12× rate-limit hits on WDQS.
_SPARQL_ALL_TMPL = """
SELECT ?h ?hLabel ?classQ ?lat ?lon ?ele ?dobih ?wp WHERE {{
  VALUES ?classQ {{ {values} }}
  ?h wdt:P31 ?classQ .
  OPTIONAL {{ ?h p:P625 ?stmt . ?stmt psv:P625 ?coord .
             ?coord wikibase:geoLatitude ?lat ; wikibase:geoLongitude ?lon . }}
  OPTIONAL {{ ?h wdt:P2044 ?ele . }}
  OPTIONAL {{ ?h wdt:P5283 ?dobih . }}
  OPTIONAL {{ ?wp schema:about ?h ; schema:isPartOf <https://en.wikipedia.org/> . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
"""

QID_TO_CLASS = {qid: label for label, qid in CLASS_QID.items()}


def _parse_wikidata_bindings(rows: list) -> dict[str, dict]:
    """Merge SPARQL bindings into Q-ID keyed hill records with classifications."""
    merged: dict[str, dict] = {}
    for b in rows:
        uri = (b.get("h") or {}).get("value", "")
        q = uri.rsplit("/", 1)[-1] if uri else ""
        if not q.startswith("Q"):
            continue
        class_uri = (b.get("classQ") or {}).get("value", "")
        class_q = class_uri.rsplit("/", 1)[-1] if class_uri else ""
        class_label = QID_TO_CLASS.get(class_q)
        rec = merged.setdefault(q, {
            "wikidata": q,
            "name": None,
            "lat": None,
            "lng": None,
            "elevationM": None,
            "dobihId": None,
            "wikipedia": None,
            "classifications": [],
        })
        if class_label and class_label not in rec["classifications"]:
            rec["classifications"].append(class_label)
        nm = (b.get("hLabel") or {}).get("value") or None
        if nm and not nm.startswith("Q") and not rec["name"]:
            rec["name"] = nm
        la = (b.get("lat") or {}).get("value")
        lo = (b.get("lon") or {}).get("value")
        if la and lo and rec["lat"] is None:
            try:
                rec["lat"] = float(la)
                rec["lng"] = float(lo)
            except ValueError:
                pass
        el = (b.get("ele") or {}).get("value")
        if el and rec["elevationM"] is None:
            try:
                rec["elevationM"] = float(el)
            except ValueError:
                pass
        db = (b.get("dobih") or {}).get("value")
        if db and rec["dobihId"] is None:
            try:
                rec["dobihId"] = int(db)
            except ValueError:
                pass
        wp = (b.get("wp") or {}).get("value")
        if wp and not rec["wikipedia"]:
            rec["wikipedia"] = wp
    for rec in merged.values():
        rec["classifications"] = sorted(
            rec.get("classifications") or [],
            key=lambda c: CLASS_RANK.get(c, 99),
        )
    return merged


def fetch_wikidata_hills_combined(*, cache: dict | None = None) -> dict[str, dict]:
    """One SPARQL query for all hill P31 types (polite to WDQS rate limits)."""
    cache = cache if cache is not None else {}
    cache.setdefault("classes", {})
    cache.setdefault("meta", {"fetchedAt": None})
    values = " ".join(f"wd:{qid}" for qid in CLASS_QID.values())
    print("  SPARQL combined (all hill classes, single request)…", flush=True)
    try:
        raw = _curl_post(
            WD_SPARQL,
            {"query": _SPARQL_ALL_TMPL.format(values=values), "format": "json"},
            timeout=300,
            max_retries=8,
        )
    except Exception as exc:
        print(f"    combined query failed: {exc}", file=sys.stderr)
        return {}
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        print(f"    JSON decode failed: {exc}", file=sys.stderr)
        return {}
    rows = (payload.get("results") or {}).get("bindings") or []
    merged = _parse_wikidata_bindings(rows)
    print(f"    +{len(merged):,} hills from combined query", flush=True)
    # Mirror into per-class cache buckets for compatibility.
    for label in CLASS_QID:
        cache["classes"][label] = {}
    for q, rec in merged.items():
        for label in rec.get("classifications") or []:
            cache["classes"].setdefault(label, {})[q] = {
                k: v for k, v in rec.items() if k != "classifications"
            }
            cache["classes"][label][q]["classifications"] = [label]
    cache["meta"]["fetchedAt"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    _atomic_write_json(WD_HILLS_CACHE, cache)
    return merged


def fetch_wikidata_hills(*, force: bool = False, cache: dict | None = None) -> dict[str, dict]:
    """Return a dict keyed by Q-ID with hill metadata, classifications merged."""
    cache = cache if cache is not None else {}
    cache.setdefault("classes", {})           # classLabel -> {qid -> rec}
    cache.setdefault("meta", {"fetchedAt": None})
    consecutive_429 = 0
    for label, qid in CLASS_QID.items():
        if (not force) and cache["classes"].get(label):
            continue
        print(f"  SPARQL ?P31 = {label} ({qid})", flush=True)
        try:
            raw = _curl_post(WD_SPARQL,
                             {"query": _SPARQL_TMPL.format(qid=qid),
                              "format": "json"},
                             timeout=120,
                             max_retries=8)
        except Exception as exc:
            print(f"    failed: {exc}", file=sys.stderr)
            if "429" in str(exc) or "giving up" in str(exc).lower():
                consecutive_429 += 1
            if consecutive_429 >= 2:
                print(
                    "  Aborting per-class SPARQL — Wikidata rate limit (HTTP 429). "
                    "Retry in a few hours, or use --dobih-csv.",
                    file=sys.stderr,
                )
                break
            continue
        consecutive_429 = 0
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            print(f"    JSON decode failed: {exc}", file=sys.stderr)
            continue
        rows = (payload.get("results") or {}).get("bindings") or []
        by_qid: dict[str, dict] = {}
        for b in rows:
            uri = (b.get("h") or {}).get("value", "")
            q = uri.rsplit("/", 1)[-1] if uri else ""
            if not q.startswith("Q"):
                continue
            rec = by_qid.setdefault(q, {
                "wikidata": q,
                "name": None,
                "lat": None,
                "lng": None,
                "elevationM": None,
                "dobihId": None,
                "wikipedia": None,
            })
            nm = (b.get("hLabel") or {}).get("value") or None
            if nm and not nm.startswith("Q") and not rec["name"]:
                rec["name"] = nm
            la = (b.get("lat") or {}).get("value")
            lo = (b.get("lon") or {}).get("value")
            if la and lo and rec["lat"] is None:
                try:
                    rec["lat"] = float(la); rec["lng"] = float(lo)
                except ValueError:
                    pass
            el = (b.get("ele") or {}).get("value")
            if el and rec["elevationM"] is None:
                try:
                    rec["elevationM"] = float(el)
                except ValueError:
                    pass
            db = (b.get("dobih") or {}).get("value")
            if db and rec["dobihId"] is None:
                try:
                    rec["dobihId"] = int(db)
                except ValueError:
                    pass
            wp = (b.get("wp") or {}).get("value")
            if wp and not rec["wikipedia"]:
                rec["wikipedia"] = wp
        cache["classes"][label] = by_qid
        cache["meta"]["fetchedAt"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        _atomic_write_json(WD_HILLS_CACHE, cache)
        print(f"    +{len(by_qid)} hills (cache flushed)", flush=True)
        time.sleep(8.0)            # polite throttle between per-class fallbacks
    # Merge classes per Q-ID.
    merged: dict[str, dict] = {}
    for label, by_qid in cache["classes"].items():
        for q, rec in by_qid.items():
            ex = merged.setdefault(q, dict(rec))
            cls = ex.setdefault("classifications", [])
            if label not in cls:
                cls.append(label)
    for q, rec in merged.items():
        rec["classifications"] = sorted(
            rec.get("classifications") or [],
            key=lambda c: CLASS_RANK.get(c, 99),
        )
    return merged


# ---------- Main staging logic ----------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dobih-csv", type=Path, default=None,
                    help="Path to a downloaded DoBIH CSV (canonical source)")
    ap.add_argument("--fetch", action="store_true",
                    help="Fetch Wikidata SPARQL fallback (network)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Compute staging in memory; do not write cache_dobih.json")
    ap.add_argument("--commit", action="store_true",
                    help="Write the final cache_dobih.json (otherwise leaves staging in audit only)")
    ap.add_argument("--limit", type=int, default=0,
                    help="Process at most N islands (debug)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if not ISLANDS_PATH.exists():
        sys.exit(f"FATAL: {ISLANDS_PATH} missing")
    islands = _load_json(ISLANDS_PATH, [])
    if not islands:
        sys.exit("FATAL: islands.json empty")
    print(f"Loaded {len(islands):,} islands")

    # --- 1. Source hills ---
    hills: list[dict] = []
    sources_used: list[str] = []
    if args.dobih_csv:
        print(f"Reading DoBIH CSV {args.dobih_csv} …", flush=True)
        try:
            hills = parse_dobih_csv(args.dobih_csv)
        except Exception as exc:
            sys.exit(f"FATAL: DoBIH CSV unreadable: {exc}")
        sources_used.append("dobih-csv")
        print(f"  → {len(hills):,} classified hills (DoBIH)")

    wd_cache = _load_json(WD_HILLS_CACHE, {})
    have_wd_cache = bool((wd_cache or {}).get("classes"))
    if args.fetch:
        print("Wikidata SPARQL fallback (live)…", flush=True)
        wd_hills = fetch_wikidata_hills_combined(cache=wd_cache)
        if not wd_hills:
            print("  Combined query empty — falling back to per-class SPARQL…", flush=True)
            wd_hills = fetch_wikidata_hills(force=True, cache=wd_cache)
        sources_used.append("wikidata-sparql")
    elif have_wd_cache:
        print("Wikidata SPARQL fallback (using cached data only)…", flush=True)
        wd_hills = fetch_wikidata_hills(force=False, cache=wd_cache)
        sources_used.append("wikidata-sparql-cached")
    else:
        wd_hills = {}
        if not hills:
            print("(No DoBIH CSV supplied and no Wikidata cache — "
                  "pass --fetch for a live SPARQL fallback, or "
                  "--dobih-csv to use the official CSV.)", flush=True)
    if wd_hills:
        # Merge: keyed by (lat, lng) rounded to 4 dp to avoid duplicates.
        by_loc: dict[tuple[float, float], dict] = {}
        for h in hills:
            la, lo = h.get("lat"), h.get("lng")
            if la is None or lo is None: continue
            by_loc[(round(float(la), 4), round(float(lo), 4))] = h
        added = 0
        for q, rec in wd_hills.items():
            if rec.get("lat") is None or rec.get("lng") is None:
                continue
            key = (round(float(rec["lat"]), 4), round(float(rec["lng"]), 4))
            if key in by_loc:
                # Merge classifications and fill missing fields.
                ex = by_loc[key]
                cls = ex.setdefault("classifications", [])
                for c in rec.get("classifications") or []:
                    if c not in cls:
                        cls.append(c)
                ex["classifications"] = sorted(cls, key=lambda c: CLASS_RANK.get(c, 99))
                ex.setdefault("wikidata", rec.get("wikidata"))
                ex.setdefault("wikipedia", rec.get("wikipedia"))
                if ex.get("dobihId") is None: ex["dobihId"] = rec.get("dobihId")
                if ex.get("elevationM") is None: ex["elevationM"] = rec.get("elevationM")
            else:
                hills.append({
                    "name": rec.get("name"),
                    "lat": rec.get("lat"),
                    "lng": rec.get("lng"),
                    "elevationM": rec.get("elevationM"),
                    "prominenceM": None,
                    "classifications": rec.get("classifications") or [],
                    "dobihId": rec.get("dobihId"),
                    "wikidata": rec.get("wikidata"),
                    "wikipedia": rec.get("wikipedia"),
                    "osmNodeId": None,
                })
                added += 1
        print(f"  Wikidata SPARQL added {added:,} hills (now {len(hills):,} total)")

    if not hills:
        # In a true cold-start dry-run we want a graceful exit with an
        # informative report rather than an error code.
        if args.dry_run:
            print("\n(No hills available; this is expected on a cold cache "
                  "with no DoBIH CSV. Re-run with --fetch to populate the "
                  "Wikidata cache, or pass --dobih-csv <path>.)")
            _atomic_write_json(REPORT, {
                "startedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "totalHillsLoaded": 0,
                "note": "Cold cache; no hills resolved.  Dry-run only.",
                "dryRun": True,
            })
            return 0
        sys.exit("FATAL: no hills resolved from any source")

    # --- 2. Spatial index hills ---
    print("Spatial-indexing hills…", flush=True)
    hill_pts: list[Point] = []
    clean: list[dict] = []
    for h in hills:
        la, lo = h.get("lat"), h.get("lng")
        if la is None or lo is None:
            continue
        try:
            hill_pts.append(Point(float(lo), float(la)))
        except (TypeError, ValueError):
            continue
        clean.append(h)
    hills = clean
    hill_tree = STRtree(hill_pts) if hill_pts else None
    print(f"  indexed {len(hill_pts):,} hill points")

    # --- 3. Load polygon resources ---
    print("Loading polygon caches…", flush=True)
    geom_cache = _load_json(OSM_GEOM_CACHE, {})
    land_polys: list[Polygon] = []
    if LAND_PICKLE.exists():
        try:
            land = pickle.load(open(LAND_PICKLE, "rb"))
            land_polys = list(getattr(land, "geoms", [land]))
        except Exception as exc:
            print(f"  WARN: land pickle unreadable ({exc})", file=sys.stderr)
    land_tree = STRtree(land_polys) if land_polys else None
    print(f"  geom cache: {len(geom_cache):,} entries; "
          f"land polygons: {len(land_polys):,}")

    # --- 4. Walk islands ---
    if args.limit:
        islands = islands[: args.limit]
    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    staged: dict[str, dict] = {}
    audit: list[dict] = []
    counts: dict[str, int] = {"with_hills": 0, "no_polygon": 0,
                              "no_hills_in_polygon": 0}
    for n, isl in enumerate(islands):
        if n and n % 500 == 0:
            print(f"  …{n}/{len(islands)} (so far: {counts['with_hills']} with hills)",
                  flush=True)
        iid = isl.get("id")
        if not iid:
            continue
        poly = polygon_for_island(isl, geom_cache, land_polys, land_tree)
        if poly is None or hill_tree is None:
            counts["no_polygon"] += 1
            continue
        try:
            cand_idx = hill_tree.query(poly, predicate="intersects")
        except Exception:
            cand_idx = []
        prep_poly = prep(poly) if len(cand_idx) > 4 else None
        test = prep_poly.contains if prep_poly is not None else poly.contains
        matched: list[dict] = []
        for idx in cand_idx:
            ii = int(idx)
            if not test(hill_pts[ii]):
                continue
            h = hills[ii]
            if not h.get("classifications"):
                continue
            matched.append(h)
        if not matched:
            counts["no_hills_in_polygon"] += 1
            continue
        # Sort by elevation desc, then prestige.
        matched.sort(key=lambda h: (
            -(h.get("elevationM") or 0),
            CLASS_RANK.get((h.get("classifications") or ["Marilyn"])[0], 99),
        ))
        hills_payload = []
        for h in matched:
            hills_payload.append({
                "name": h.get("name"),
                "classifications": h.get("classifications") or [],
                "elevationM": round(float(h["elevationM"]), 1) if h.get("elevationM") else None,
                "prominenceM": round(float(h["prominenceM"]), 1) if h.get("prominenceM") else None,
                "lat": round(float(h["lat"]), 5),
                "lng": round(float(h["lng"]), 5),
                "dobihId": h.get("dobihId"),
                "osmNodeId": h.get("osmNodeId"),
                "wikidata": h.get("wikidata"),
                "wikipedia": h.get("wikipedia"),
            })
        # Build the source label from what we actually used.
        if args.dobih_csv and any(h.get("dobihId") for h in matched):
            src = "dobih-v17+wikidata-p2044"
        elif args.dobih_csv:
            src = "dobih-v17"
        else:
            src = "wikidata-p2044+sparql"
        staged[iid] = {
            "hillsOn": hills_payload,
            "hillsOnSource": src,
            "hillsOnConfidence": "high",
            "hillsOnAttribution": (
                "Database of British and Irish Hills "
                "(Jackson, Dawson, et al.), CC-BY 4.0 — "
                "https://www.hills-database.co.uk/"
            ),
            "hillsOnFetchedAt": fetched_at,
        }
        counts["with_hills"] += 1
        if len(audit) < 50:
            audit.append({
                "id": iid, "name": isl.get("name"),
                "hillCount": len(hills_payload),
                "topHill": hills_payload[0] if hills_payload else None,
            })
        if args.verbose:
            top = hills_payload[0]
            print(f"  + {isl.get('name')}: {len(hills_payload)} hills "
                  f"(top: {top.get('name')} {top.get('elevationM')} m "
                  f"{top.get('classifications')})", flush=True)

    # --- 5. Write report + cache ---
    report = {
        "startedAt": fetched_at,
        "sourcesUsed": sources_used,
        "totalHillsLoaded": len(hills),
        "islandsProcessed": len(islands),
        "islandsWithHills": counts["with_hills"],
        "islandsWithoutPolygon": counts["no_polygon"],
        "islandsWithPolygonButNoHill": counts["no_hills_in_polygon"],
        "sampleAudit": audit,
        "dryRun": bool(args.dry_run or not args.commit),
    }
    _atomic_write_json(REPORT, report)
    print()
    print(f"Audit  → {REPORT.name}")
    print(f"Coverage: {counts['with_hills']:,} islands have ≥1 classified hill "
          f"({100 * counts['with_hills'] / max(1, len(islands)):.1f}%)")
    print(f"  islands without polygon       : {counts['no_polygon']:,}")
    print(f"  islands no hill inside polygon: {counts['no_hills_in_polygon']:,}")

    if args.dry_run:
        print(f"\nDRY RUN — cache_dobih.json NOT written. "
              f"Would have staged {len(staged):,} islands.")
        return 0
    if not args.commit:
        print(f"\n(--commit not supplied; "
              f"cache_dobih.json NOT written.  Re-run with --commit to stage.)")
        return 0
    _atomic_write_json(STAGED_CACHE, staged)
    print(f"\nStaged cache → {STAGED_CACHE.name} ({len(staged):,} islands)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
