#!/usr/bin/env python3
"""
Re-classify every island in `data/islands.json` using a stacked-evidence
pipeline.  **Phase 1** (this script): zero-cost public sources only.

Tiers, in priority order:

  T0  Manual / curated overrides                        → respected as-is
  T1  Wikidata P206 (located in or next to body of water)
      cross-referenced with the body's P31 (instance of) to infer
      sea / lake / river / canal / reservoir / estuary           (free, ~half a day)
  T2  OSM coastline -- positive sea verification.  We polygonise
      `natural=coastline` ways and pull out the Britain + Ireland
      MAINLAND polygons (anything > 5,000 km²; produced offline by
      scripts/build_land_polygons.py and pickled).  Then:
        - centroid INSIDE mainland → island is genuinely inland
          (river / lake) but no specific water body matched → `unknown`
        - centroid OUTSIDE mainland → island has its own coastline
          polygon, i.e. it's a real marine island → confirm `sea`     (free)
  T3  Widened OSM water polygons (point-in-polygon)
      - relation["type"="multipolygon"]["natural"="water"]  (no water=*)
      - relation["natural"="water"]
      - way["natural"="water"]                                    (small ponds)
      - way["landuse"="reservoir"]
      - way["waterway"="riverbank"]
                                                                  (free)
  T4  Proximity fallback: nearest inland water polygon
      - ≤ 200 m → medium confidence
      - 200-500 m → low confidence (geocoded centroid drift)
                                                                  (free)
  T5  Manual review queue                                         → `unknown`

The script writes a **proposal file** at
``data/reclassification_proposal.json`` showing every island whose
classification would change, with full evidence.  It NEVER mutates
``data/islands.json`` -- a separate apply step does that once the user
has reviewed the proposal.

Stages can be run independently::

    python3 scripts/reclassify_islands.py --fetch-wd    # Tier 1 only
    python3 scripts/reclassify_islands.py --fetch-coast # Tier 2 only
    python3 scripts/reclassify_islands.py --fetch-water # Tier 3 only
    python3 scripts/reclassify_islands.py --classify    # consume caches, emit proposal
    python3 scripts/reclassify_islands.py --all         # do everything

Outputs:
    data/cache_wd_water_body.json     Wikidata P206 + body P31 lookups
    data/coastline_raw.json           OSM natural=coastline ways
    data/water_raw_v2.json            Widened OSM water polygons
    data/reclassification_proposal.json
    data/reclassification_summary.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from shapely.geometry import LineString, MultiPolygon, Point, Polygon
    from shapely.ops import nearest_points, polygonize, unary_union
    from shapely.strtree import STRtree
except ImportError:
    sys.exit("shapely is required: pip install shapely")


def _deg_distance_to_m(p_lat: float, near_lat: float, near_lng: float, p_lng: float) -> float:
    """Approximate geodesic distance in metres between two lat/lng points.
    Good to ~0.1% for distances under a few km."""
    dy = (p_lat - near_lat) * 111_320
    dx = (p_lng - near_lng) * 111_320 * math.cos(math.radians((p_lat + near_lat) / 2))
    return math.hypot(dx, dy)


# Tier 4 cut-offs.  Reflect a defensible interpretation of "the OSM
# water polygon is mapping the same body the island sits in":
# - ≤ 200m  : crannogs, mid-channel river bars, lake islets whose
#             centroid is in the lake but the polygon's edge is just
#             nearby.  Medium confidence.
# - ≤ 500m  : larger geocoding drift (the island name was matched to a
#             nearby point in Wikidata, the OSM polygon is a couple
#             hundred metres off).  Low confidence.
# - > 500m  : leave as unknown.  The "nearest" polygon is almost
#             certainly an unrelated pond.
TIER4_MEDIUM_M = 200
TIER4_LOW_M = 500

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

ISLANDS_PATH = DATA / "islands.json"
PROPOSAL_PATH = DATA / "reclassification_proposal.json"
SUMMARY_PATH = DATA / "reclassification_summary.json"

CACHE_WD = DATA / "cache_wd_water_body.json"
CACHE_COAST = DATA / "coastline_raw.json"
LAND_PICKLE = DATA / "land_polygons.pickle"
MAINLAND_PICKLE = DATA / "mainland_polygons.pickle"
CACHE_WATER = DATA / "water_raw_v2.json"

USER_AGENT = "isles-of-britain/0.6 (reclassify-islands; static-site)"
DELAY_S = 0.50

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
]
WIKIDATA_API = "https://www.wikidata.org/w/api.php"

UK_BBOX = (49.0, -10.5, 61.5, 2.5)

# -----------------------------------------------------------------------------
# Wikidata body-type ontology
# -----------------------------------------------------------------------------
# Each Q-ID below is an instance-of (P31) value we might see for the body
# Wikidata's P206 points at, mapped to our 3-bucket type vocabulary.
WD_BODY_TYPES: dict[str, tuple[str, str | None]] = {
    # --- Sea / ocean / saltwater inlets ---
    "Q165":     ("sea",   None),               # sea
    "Q9430":    ("sea",   None),               # ocean
    "Q39594":   ("sea",   "estuary"),          # estuary
    "Q3492278": ("sea",   "estuary"),          # ria
    "Q1322134": ("sea",   "tidal-loch"),       # sea loch
    "Q1172599": ("sea",   "tidal-loch"),       # sea loch (Scotland-specific)
    "Q2017137": ("sea",   "tidal-loch"),       # firth
    "Q1210950": ("sea",   None),               # strait (kyle/sound)
    "Q39816":   ("sea",   None),               # gulf
    "Q34022":   ("sea",   None),               # strait
    "Q177380":  ("sea",   None),               # sound (sea)
    "Q41796":   ("sea",   None),               # bay
    "Q1170977": ("sea",   None),               # channel (sea)
    "Q189553":  ("sea",   None),               # coast
    "Q44782":   ("sea",   None),               # cove (mostly sea)
    "Q207326":  ("sea",   None),               # fjord
    "Q37901":   ("sea",   None),               # marginal sea
    "Q1135049": ("sea",   None),               # arm of the sea
    "Q14066528":("sea",   None),               # body of salt water
    "Q190570":  ("sea",   None),               # inlet
    "Q1973404": ("sea",   None),               # roadstead / anchorage

    # --- Lake-family (freshwater, non-flowing) ---
    "Q23397":   ("lake",  None),               # lake
    "Q3253281": ("lake",  None),               # body of water (generic)
    "Q131681":  ("lake",  "reservoir"),        # reservoir
    "Q3859328": ("lake",  "lagoon"),           # lagoon
    "Q204324":  ("lake",  "pond"),             # pond
    "Q124714":  ("lake",  "oxbow"),            # oxbow lake
    "Q2275585": ("lake",  None),               # tarn
    "Q183883":  ("lake",  None),               # loch (generic — most Scottish freshwater)
    "Q31805":   ("lake",  "lagoon"),           # coastal lagoon (brackish but inland)
    "Q9259":    ("lake",  None),               # mere (English freshwater)

    # --- River-family ---
    "Q4022":    ("river", None),               # river
    "Q12284":   ("river", "canal"),            # canal
    "Q47521":   ("river", "stream"),           # stream
    "Q1437299": ("river", None),               # creek
    "Q55659167":("river", None),               # rivulet
    "Q11436":   ("river", None),               # waterway
    "Q21029893":("river", None),               # tributary
    "Q12013012":("river", "canal"),            # ship canal
    "Q3215290": ("river", None),               # brook
    "Q105731":  ("river", None),               # rill
}

# When a P31 isn't in WD_BODY_TYPES, follow its P279 (subclass of) chain
# up to MAX_P279_DEPTH levels to see if a known ancestor matches.
MAX_P279_DEPTH = 3

# Words in a body's English label that strongly hint at the type when
# Wikidata's P31 is missing/ambiguous.  Conservative -- only used as a
# tie-breaker.
LABEL_HINTS: list[tuple[str, str, str | None]] = [
    ("river ",          "river", None),
    (" river",          "river", None),
    ("canal",           "river", "canal"),
    ("loch ",           "lake",  None),
    (" loch",           "lake",  None),
    ("lough ",          "lake",  None),
    (" lough",          "lake",  None),
    ("lake ",           "lake",  None),
    (" lake",           "lake",  None),
    ("reservoir",       "lake",  "reservoir"),
    ("pond",            "lake",  "pond"),
    ("estuary",         "sea",   "estuary"),
    ("firth of",        "sea",   "tidal-loch"),
    ("bay of",          "sea",   None),
    (" bay",            "sea",   None),
    (" sea",            "sea",   None),
    ("english channel", "sea",   None),
    ("celtic sea",      "sea",   None),
    ("irish sea",       "sea",   None),
    ("north sea",       "sea",   None),
    ("atlantic",        "sea",   None),
]

# -----------------------------------------------------------------------------
# HTTP helpers
# -----------------------------------------------------------------------------
def _curl_post(url: str, data: str, timeout: int = 600) -> bytes:
    """POST via curl -- avoids the SSL handshake issues urllib hits with
    some Overpass mirrors."""
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
    """GET with exponential backoff on transient failures / rate limits.

    The Wikidata public API occasionally returns HTML error pages (HTTP
    200 wrapping a 5xx) or hangs.  We retry with growing delays.  An
    empty body or a body that doesn't start with '{' is treated as a
    rate-limit signal.
    """
    qs = urllib.parse.urlencode(params, doseq=True)
    full = f"{url}?{qs}"
    backoff = [1.0, 3.0, 8.0, 20.0, 45.0, 90.0]
    last_err: str | None = None
    for delay in backoff:
        try:
            res = subprocess.run(
                [
                    "curl", "-sS", "--max-time", str(timeout),
                    "-H", f"User-Agent: {USER_AGENT}",
                    "-H", "Accept: application/json",
                    "-w", "\nHTTP_CODE=%{http_code}\n",
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
        # Strip the HTTP_CODE trailer.
        m_idx = body.rfind("\nHTTP_CODE=")
        http_code = 0
        if m_idx >= 0:
            try:
                http_code = int(body[m_idx + len("\nHTTP_CODE=") :].strip())
            except Exception:
                http_code = 0
            body = body[:m_idx]
        body_stripped = body.lstrip()
        if not body_stripped or body_stripped[0] not in "{[":
            last_err = f"non-JSON body (HTTP {http_code}): {body_stripped[:120]!r}"
            time.sleep(delay)
            continue
        if http_code in (429, 503, 502, 504):
            last_err = f"HTTP {http_code}"
            time.sleep(delay)
            continue
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            last_err = f"json decode: {exc}; body[:120]={body[:120]!r}"
            time.sleep(delay)
            continue
    raise RuntimeError(f"_curl_get giving up: {last_err}")


def _atomic_write(path: Path, payload: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _load_cache(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"  WARN: cache {path.name} unreadable ({exc}); using default", file=sys.stderr)
        return default


# -----------------------------------------------------------------------------
# Tier 1: Wikidata P206 + P31
# -----------------------------------------------------------------------------
def fetch_wikidata_water_bodies(qids: list[str], cache: dict, refresh: bool = False) -> dict:
    """For each Q-ID, fetch its P206 claim → set of body Q-IDs, then fetch
    each body's P31 + label.  Results cached under cache["islands"][qid]
    and cache["bodies"][bodyQid].

    Returns the updated cache dict.
    """
    cache.setdefault("islands", {})
    cache.setdefault("bodies", {})

    todo = [q for q in qids if refresh or q not in cache["islands"]]
    print(f"Tier 1 / Wikidata P206: {len(todo)} islands to fetch (cache hits: {len(qids) - len(todo)})", flush=True)

    BATCH = 50
    for i in range(0, len(todo), BATCH):
        batch = todo[i : i + BATCH]
        params = {
            "action": "wbgetentities",
            "format": "json",
            "ids": "|".join(batch),
            "props": "claims|labels",
            "languages": "en",
        }
        try:
            payload = _curl_get(WIKIDATA_API, params)
        except Exception as exc:
            print(f"  batch failed ({exc}); skipping", file=sys.stderr)
            continue
        entities = payload.get("entities") or {}
        for qid in batch:
            ent = entities.get(qid) or {}
            label = ((ent.get("labels") or {}).get("en") or {}).get("value", "")
            claims = ent.get("claims") or {}
            p206 = claims.get("P206") or []
            body_qids: list[str] = []
            for c in p206:
                mainsnak = c.get("mainsnak") or {}
                if mainsnak.get("snaktype") != "value":
                    continue
                dv = (mainsnak.get("datavalue") or {}).get("value") or {}
                bid = dv.get("id")
                if bid:
                    body_qids.append(bid)
            cache["islands"][qid] = {
                "label": label,
                "P206": body_qids,
            }
        _atomic_write(CACHE_WD, cache)
        # Throttle for the public Wikidata endpoint.
        time.sleep(DELAY_S)
        if (i // BATCH) % 5 == 0:
            done = min(i + BATCH, len(todo))
            print(f"  islands fetched: {done}/{len(todo)}", flush=True)

    # Collect every parent-body Q-ID we don't yet have details for.
    body_qids_needed: set[str] = set()
    for entry in cache["islands"].values():
        for bid in entry.get("P206") or []:
            if refresh or bid not in cache["bodies"]:
                body_qids_needed.add(bid)
    body_list = sorted(body_qids_needed)
    print(f"Tier 1 / Wikidata bodies: {len(body_list)} parent bodies to fetch", flush=True)

    for i in range(0, len(body_list), BATCH):
        batch = body_list[i : i + BATCH]
        params = {
            "action": "wbgetentities",
            "format": "json",
            "ids": "|".join(batch),
            "props": "claims|labels",
            "languages": "en",
        }
        try:
            payload = _curl_get(WIKIDATA_API, params)
        except Exception as exc:
            print(f"  body batch failed ({exc}); skipping", file=sys.stderr)
            continue
        entities = payload.get("entities") or {}
        for bid in batch:
            ent = entities.get(bid) or {}
            label = ((ent.get("labels") or {}).get("en") or {}).get("value", "")
            claims = ent.get("claims") or {}
            p31 = []
            for c in claims.get("P31") or []:
                ms = c.get("mainsnak") or {}
                if ms.get("snaktype") != "value":
                    continue
                dv = (ms.get("datavalue") or {}).get("value") or {}
                cid = dv.get("id")
                if cid:
                    p31.append(cid)
            cache["bodies"][bid] = {
                "label": label,
                "P31": p31,
            }
        _atomic_write(CACHE_WD, cache)
        time.sleep(DELAY_S)
        if (i // BATCH) % 5 == 0:
            done = min(i + BATCH, len(body_list))
            print(f"  bodies fetched: {done}/{len(body_list)}", flush=True)

    # ----- P279 climb for unknown P31 values -----
    # Collect every P31 Q-ID we've seen that isn't in our ontology.
    cache.setdefault("classes", {})  # qid -> {label, P279}
    unknown_classes: set[str] = set()
    for body in cache["bodies"].values():
        for p in body.get("P31") or []:
            if p not in WD_BODY_TYPES and p not in (cache.get("classes") or {}):
                unknown_classes.add(p)
    if unknown_classes:
        print(f"Tier 1 / Wikidata classes: climbing P279 for {len(unknown_classes)} unknown P31s", flush=True)
        _fetch_classes_with_p279(unknown_classes, cache, depth=0)

    return cache


def _fetch_classes_with_p279(qids: set[str], cache: dict, depth: int = 0) -> None:
    """Fetch P279 (subclass of) for each given Q-ID, recursively climbing
    the subclass chain up to MAX_P279_DEPTH levels.  We stop early if a
    known root in WD_BODY_TYPES is hit."""
    if depth >= MAX_P279_DEPTH or not qids:
        return
    BATCH = 50
    todo = sorted(q for q in qids if q not in cache["classes"])
    next_level: set[str] = set()
    for i in range(0, len(todo), BATCH):
        batch = todo[i : i + BATCH]
        params = {
            "action": "wbgetentities",
            "format": "json",
            "ids": "|".join(batch),
            "props": "claims|labels",
            "languages": "en",
        }
        try:
            payload = _curl_get(WIKIDATA_API, params)
        except Exception as exc:
            print(f"  classes batch failed ({exc}); skipping", file=sys.stderr)
            continue
        ents = payload.get("entities") or {}
        for qid in batch:
            ent = ents.get(qid) or {}
            label = ((ent.get("labels") or {}).get("en") or {}).get("value", "")
            p279: list[str] = []
            for c in (ent.get("claims") or {}).get("P279") or []:
                ms = c.get("mainsnak") or {}
                if ms.get("snaktype") != "value":
                    continue
                dv = (ms.get("datavalue") or {}).get("value") or {}
                cid = dv.get("id")
                if cid:
                    p279.append(cid)
            cache["classes"][qid] = {"label": label, "P279": p279}
            for parent in p279:
                if parent not in WD_BODY_TYPES and parent not in cache["classes"]:
                    next_level.add(parent)
        _atomic_write(CACHE_WD, cache)
        time.sleep(DELAY_S)
    if next_level:
        _fetch_classes_with_p279(next_level, cache, depth + 1)


def resolve_class_to_type(qid: str, cache: dict, visited: set[str] | None = None) -> tuple[str | None, str | None]:
    """Return (type, subtype) by walking the P279 chain from qid up to a
    known WD_BODY_TYPES root.  Returns (None, None) if no resolution."""
    if qid in WD_BODY_TYPES:
        return WD_BODY_TYPES[qid]
    if visited is None:
        visited = set()
    if qid in visited:
        return (None, None)
    visited.add(qid)
    cls = (cache.get("classes") or {}).get(qid) or {}
    for parent in cls.get("P279") or []:
        t, st = resolve_class_to_type(parent, cache, visited)
        if t is not None:
            return (t, st)
    return (None, None)


def infer_type_from_wikidata(island_qid: str, cache: dict) -> dict | None:
    """Return {type, subtype, parentWaterBody, confidence, evidence} or None."""
    entry = (cache.get("islands") or {}).get(island_qid)
    if not entry or not entry.get("P206"):
        return None
    # We pick the *first* P206 body for now -- in practice islands have
    # one, occasionally two (when they straddle a confluence).
    for body_qid in entry["P206"]:
        body = (cache.get("bodies") or {}).get(body_qid)
        if not body:
            continue
        # Resolve via P31 first (with P279 climb fallback).
        candidate_type: str | None = None
        candidate_subtype: str | None = None
        for p31 in body.get("P31") or []:
            t, st = resolve_class_to_type(p31, cache)
            if t is None:
                continue
            # Sea outranks lake outranks river (a sea-loch tagged as lake
            # in error gets corrected once we learn it's sea via P279).
            ranking = {"sea": 3, "river": 2, "lake": 1}
            if candidate_type is None or ranking[t] > ranking[candidate_type]:
                candidate_type, candidate_subtype = t, st
        # Fall back to label hints.
        if candidate_type is None:
            label = (body.get("label") or "").lower()
            for token, t, st in LABEL_HINTS:
                if token in label:
                    candidate_type, candidate_subtype = t, st
                    break
        if candidate_type is None:
            continue
        return {
            "type": candidate_type,
            "subtype": candidate_subtype,
            "parentWaterBody": {
                "name": body.get("label", ""),
                "type": candidate_type,
                "wikidata": body_qid,
            },
            "confidence": "high",
            "evidence": {
                "source": "wikidata-p206",
                "bodyQid": body_qid,
                "bodyLabel": body.get("label", ""),
                "bodyP31": body.get("P31") or [],
            },
        }
    return None


# -----------------------------------------------------------------------------
# Tier 2: OSM coastline polygon -- positive sea verification
# -----------------------------------------------------------------------------
def fetch_coastline(refresh: bool = False) -> dict:
    if not refresh and CACHE_COAST.exists():
        print(f"  Tier 2 / coastline: cached at {CACHE_COAST.name}", flush=True)
        return _load_cache(CACHE_COAST, {})
    s, w, n, e = UK_BBOX
    query = f"""
[out:json][timeout:600];
(
  way["natural"="coastline"]({s},{w},{n},{e});
);
out body;
>;
out skel qt;
""".strip()
    print("  Tier 2 / coastline: fetching OSM coastline (this can take ~2 min)…", flush=True)
    last_err = None
    for ep in OVERPASS_ENDPOINTS:
        try:
            print(f"    → {ep}", flush=True)
            raw = _curl_post(ep, query, timeout=900)
            data = json.loads(raw.decode("utf-8"))
            _atomic_write(CACHE_COAST, data)
            print(f"    OK; cached {len(data.get('elements') or []):,} elements", flush=True)
            return data
        except Exception as exc:
            last_err = exc
            print(f"    failed: {exc}", flush=True)
    raise RuntimeError(f"all Overpass endpoints failed for coastline: {last_err}")


def build_land_polygons(coastline_data: dict) -> MultiPolygon | None:
    """OSM `natural=coastline` ways are directed so that *land is on the
    LEFT-hand side*.  We polygonise the union of all coastline lines into
    closed rings, then return the land-side polygons.

    For our use this only needs to be accurate enough to test "centroid
    inside land?".
    """
    elements = coastline_data.get("elements") or []
    nodes = {e["id"]: (e["lon"], e["lat"]) for e in elements if e["type"] == "node"}
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
    if not lines:
        return None
    print(f"    polygonising {len(lines):,} coastline ways…", flush=True)
    polys = list(polygonize(unary_union(lines)))
    if not polys:
        return None
    # We don't know which polys are land vs sea-tile-edges, but for the
    # British Isles, every closed coastline polygon IS land (islands).
    merged = MultiPolygon(polys) if len(polys) > 1 else polys[0]
    if not merged.is_valid:
        merged = merged.buffer(0)
    print(f"    land polygons assembled: {len(polys):,} components", flush=True)
    return merged


# -----------------------------------------------------------------------------
# Tier 3: Widened OSM water query
# -----------------------------------------------------------------------------
def fetch_widened_water(refresh: bool = False) -> dict:
    if not refresh and CACHE_WATER.exists():
        print(f"  Tier 3 / water: cached at {CACHE_WATER.name}", flush=True)
        return _load_cache(CACHE_WATER, {})
    s, w, n, e = UK_BBOX
    query = f"""
[out:json][timeout:900];
(
  relation["type"="multipolygon"]["natural"="water"]({s},{w},{n},{e});
  relation["natural"="water"]({s},{w},{n},{e});
  relation["type"="multipolygon"]["waterway"="riverbank"]({s},{w},{n},{e});
  relation["type"="multipolygon"]["landuse"="reservoir"]({s},{w},{n},{e});
  way["natural"="water"]({s},{w},{n},{e});
  way["waterway"="riverbank"]({s},{w},{n},{e});
  way["landuse"="reservoir"]({s},{w},{n},{e});
);
out body;
>;
out tags geom;
""".strip()
    print("  Tier 3 / widened water: fetching (this can take ~3-5 min)…", flush=True)
    last_err = None
    for ep in OVERPASS_ENDPOINTS:
        try:
            print(f"    → {ep}", flush=True)
            raw = _curl_post(ep, query, timeout=1200)
            data = json.loads(raw.decode("utf-8"))
            _atomic_write(CACHE_WATER, data)
            print(f"    OK; cached {len(data.get('elements') or []):,} elements", flush=True)
            return data
        except Exception as exc:
            last_err = exc
            print(f"    failed: {exc}", flush=True)
    raise RuntimeError(f"all Overpass endpoints failed for water: {last_err}")


def classify_water_tags(tags: dict) -> tuple[str | None, str | None, bool]:
    """Same vocabulary as classify_inland.classify_body + subtype.  Returns
    (kind, subtype, is_tidal)."""
    if (
        tags.get("salt") == "yes"
        or tags.get("tidal") == "yes"
        or tags.get("water") == "tidal"
        or tags.get("estuary") in ("yes", "river")
    ):
        return ("sea", "estuary" if tags.get("estuary") in ("yes", "river") else None, True)
    water = tags.get("water")
    waterway = tags.get("waterway")
    landuse = tags.get("landuse")
    natural = tags.get("natural")

    LAKE_WATER = {"lake", "pond", "reservoir", "lagoon", "oxbow", "basin"}
    RIVER_WATER = {"river", "stream", "canal"}

    if water in LAKE_WATER or landuse == "reservoir":
        st = "reservoir" if landuse == "reservoir" or water == "reservoir" else (
            water if water in ("pond", "lagoon", "oxbow", "basin") else None
        )
        return ("lake", st, False)
    if water in RIVER_WATER or waterway == "riverbank":
        st = (
            "canal" if waterway == "canal" or water == "canal"
            else "stream" if water == "stream"
            else None
        )
        return ("river", st, False)
    # Untagged `natural=water` — assume lake (it's an inland pond/pool).
    # If a future tier finds a riverbank, that wins by being more specific.
    if natural == "water":
        return ("lake", None, False)
    return (None, None, False)


def assemble_polygon_from_way(way: dict) -> Polygon | None:
    geom = way.get("geometry") or []
    if len(geom) < 3:
        return None
    coords = [(p["lon"], p["lat"]) for p in geom]
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    try:
        poly = Polygon(coords)
        if not poly.is_valid:
            poly = poly.buffer(0)
        return poly if poly.is_valid and not poly.is_empty else None
    except Exception:
        return None


def assemble_polygon_from_relation(rel: dict, ways: dict[int, dict]) -> Polygon | MultiPolygon | None:
    outer_lines: list[LineString] = []
    for m in rel.get("members") or []:
        if m["type"] != "way":
            continue
        w = ways.get(m["ref"])
        if not w:
            continue
        role = m.get("role") or ""
        if role == "inner":
            continue
        geom = w.get("geometry") or []
        if len(geom) < 2:
            continue
        try:
            outer_lines.append(LineString([(p["lon"], p["lat"]) for p in geom]))
        except Exception:
            continue
    if not outer_lines:
        return None
    try:
        polys = list(polygonize(unary_union(outer_lines)))
        if not polys:
            return None
        merged = MultiPolygon(polys) if len(polys) > 1 else polys[0]
        if not merged.is_valid:
            merged = merged.buffer(0)
        return merged
    except Exception:
        return None


def build_water_bodies(water_data: dict, wd_cache: dict | None = None) -> list[dict]:
    """Return a list of {kind, subtype, name, wikidata, osmType, osmId,
    polygon, areaKm2} for every non-tidal inland water body.

    Important: when a water body carries a `wikidata=Qxxx` tag, we cross-
    reference it against `wd_cache` to verify it's not a sea loch /
    estuary / firth that OSM didn't tag as `salt=yes`.  This avoids
    putting Loch Ewe (sea loch) into the lake bucket.
    """
    elements = water_data.get("elements") or []
    ways = {e["id"]: e for e in elements if e["type"] == "way"}
    relations = [e for e in elements if e["type"] == "relation"]
    bodies: list[dict] = []
    wd_bodies = (wd_cache or {}).get("bodies") or {}
    overridden_sea = 0

    def _wd_override(tags: dict, fallback_kind: str, fallback_subtype: str | None) -> tuple[str, str | None, bool]:
        """If the body has a wikidata tag and the cache says it's sea, return
        ('sea', subtype, True=should-drop).  Otherwise return the fallback."""
        wd_qid = (tags.get("wikidata") or "").strip()
        if not wd_qid or wd_qid not in wd_bodies:
            return (fallback_kind, fallback_subtype, False)
        body = wd_bodies[wd_qid]
        for p31 in body.get("P31") or []:
            t, st = resolve_class_to_type(p31, wd_cache)
            if t == "sea":
                return ("sea", st or fallback_subtype, True)
            if t in ("lake", "river") and fallback_kind != t:
                # Wikidata says something different; trust Wikidata.
                return (t, st or fallback_subtype, False)
        return (fallback_kind, fallback_subtype, False)

    # Relations first (named, larger features).
    for rel in relations:
        tags = rel.get("tags") or {}
        kind, subtype, is_tidal = classify_water_tags(tags)
        if is_tidal or kind not in ("lake", "river"):
            continue
        kind, subtype, drop = _wd_override(tags, kind, subtype)
        if drop:
            overridden_sea += 1
            continue
        poly = assemble_polygon_from_relation(rel, ways)
        if poly is None:
            continue
        bodies.append({
            "osmType": "relation",
            "osmId": rel["id"],
            "kind": kind,
            "subtype": subtype,
            "name": tags.get("name:en") or tags.get("name") or "",
            "wikidata": tags.get("wikidata") or "",
            "polygon": poly,
            "areaKm2": _polygon_area_km2(poly),
            "tags": tags,
        })

    # Then ways that aren't already members of a relation we included.
    member_way_ids: set[int] = set()
    for rel in relations:
        for m in rel.get("members") or []:
            if m["type"] == "way":
                member_way_ids.add(m["ref"])

    for w in ways.values():
        tags = w.get("tags") or {}
        if not tags:  # Likely a node-collected member of a relation; skip.
            continue
        if w["id"] in member_way_ids:
            continue
        kind, subtype, is_tidal = classify_water_tags(tags)
        if is_tidal or kind not in ("lake", "river"):
            continue
        kind, subtype, drop = _wd_override(tags, kind, subtype)
        if drop:
            overridden_sea += 1
            continue
        poly = assemble_polygon_from_way(w)
        if poly is None:
            continue
        bodies.append({
            "osmType": "way",
            "osmId": w["id"],
            "kind": kind,
            "subtype": subtype,
            "name": tags.get("name:en") or tags.get("name") or "",
            "wikidata": tags.get("wikidata") or "",
            "polygon": poly,
            "areaKm2": _polygon_area_km2(poly),
            "tags": tags,
        })
    if overridden_sea:
        print(f"    Wikidata override: dropped {overridden_sea} bodies (sea-lochs etc.)", flush=True)
    return bodies


def _polygon_area_km2(poly) -> float | None:
    if poly is None:
        return None
    try:
        c = poly.centroid
        lat = c.y
        deg_m_lat = 111_320
        deg_m_lng = 111_320 * math.cos(math.radians(lat))
        return round((poly.area * deg_m_lat * deg_m_lng) / 1_000_000, 4)
    except Exception:
        return None


# -----------------------------------------------------------------------------
# Main classifier
# -----------------------------------------------------------------------------
def classify(islands: list[dict], wd_cache: dict, land_poly, water_bodies: list[dict]) -> tuple[list[dict], dict]:
    """Walk every island, build proposed reclassification.  Returns
    (proposal_records, summary)."""
    # Spatial index for water bodies.
    body_polys = [b["polygon"] for b in water_bodies]
    body_index_by_polyid = {id(p): b for p, b in zip(body_polys, water_bodies)}
    water_tree = STRtree(body_polys) if body_polys else None
    print(f"  spatial index: {len(body_polys):,} water polygons", flush=True)

    proposals: list[dict] = []
    summary = {
        "total": len(islands),
        "skippedTierA_B": 0,
        "kept_unchanged": 0,
        "changed": 0,
        "byTier": Counter(),
        "byTypeBefore": Counter(),
        "byTypeAfter": Counter(),
        "transitions": Counter(),
    }

    for isl in islands:
        before_type = isl.get("type") or "unknown"
        summary["byTypeBefore"][before_type] += 1

        # Tier 0: respect existing curated / tier-a / tier-b / thames-list / etc.
        existing_src = (isl.get("classification") or {}).get("source", "")
        if existing_src in {"tier-a", "tier-b", "manual", "curated", "thames-list",
                            "wp-category", "crannog-subtype-override"}:
            summary["skippedTierA_B"] += 1
            summary["byTypeAfter"][before_type] += 1
            continue

        verdict: dict | None = None
        evidence: list[dict] = []

        # Tier 1: Wikidata P206.
        qid = isl.get("wikidata")
        if qid:
            v = infer_type_from_wikidata(qid, wd_cache)
            if v:
                verdict = v
                evidence.append(v["evidence"])

        # Tier 3 (run before Tier 2 because positive water-body containment
        # is stronger evidence than the coastline test): point-in-polygon.
        if verdict is None and water_tree is not None:
            pt = Point(isl["lng"], isl["lat"])
            try:
                cand = water_tree.query(pt, predicate="intersects")
            except Exception:
                cand = []
            best = None
            best_area = math.inf
            for idx in cand:
                poly = body_polys[int(idx)]
                if not poly.contains(pt):
                    continue
                b = body_index_by_polyid[id(poly)]
                a = b["areaKm2"] or float("inf")
                if a < best_area:
                    best_area = a
                    best = b
            if best is not None:
                verdict = {
                    "type": best["kind"],
                    "subtype": best["subtype"],
                    "parentWaterBody": {
                        "name": best["name"],
                        "type": best["kind"],
                        "osmType": best["osmType"],
                        "osmId": best["osmId"],
                        "wikidata": best["wikidata"],
                    },
                    "confidence": "medium",
                    "evidence": {
                        "source": "osm-water-pip",
                        "osmType": best["osmType"],
                        "osmId": best["osmId"],
                        "bodyName": best["name"],
                        "areaKm2": best["areaKm2"],
                    },
                }
                evidence.append(verdict["evidence"])

        # Tier 2 mainland test -- compute up-front so we can gate
        # Tier 4 on it.  Without this gate, a tiny marine islet next
        # to a coastal freshwater stream could get a false-positive
        # river verdict from Tier 4.
        in_mainland = False
        if verdict is None and land_poly is not None:
            pt = Point(isl["lng"], isl["lat"])
            try:
                in_mainland = land_poly.contains(pt)
            except Exception:
                in_mainland = False

        # Tier 4: proximity fallback.  Only runs for islands that are
        # demonstrably inland (centroid inside the GB/Ireland mainland
        # polygon).  Catches crannogs, mid-channel river bars, and
        # small lake islets whose geocoded centroid drifts a few
        # metres off the OSM polygon.
        if verdict is None and in_mainland and water_tree is not None and body_polys:
            pt = Point(isl["lng"], isl["lat"])
            try:
                idx = water_tree.nearest(pt)
                nearest_poly = body_polys[int(idx)]
            except Exception:
                nearest_poly = None
            if nearest_poly is not None:
                near_on_poly, _ = nearest_points(nearest_poly, pt)
                dist_m = _deg_distance_to_m(isl["lat"], near_on_poly.y, near_on_poly.x, isl["lng"])
                if dist_m <= TIER4_LOW_M:
                    body = body_index_by_polyid[id(nearest_poly)]
                    confidence = "medium" if dist_m <= TIER4_MEDIUM_M else "low"
                    verdict = {
                        "type": body["kind"],
                        "subtype": body["subtype"],
                        "parentWaterBody": {
                            "name": body["name"],
                            "type": body["kind"],
                            "osmType": body["osmType"],
                            "osmId": body["osmId"],
                            "wikidata": body["wikidata"],
                        },
                        "confidence": confidence,
                        "evidence": {
                            "source": "osm-water-near",
                            "osmType": body["osmType"],
                            "osmId": body["osmId"],
                            "bodyName": body["name"],
                            "distanceM": round(dist_m, 1),
                            "areaKm2": body["areaKm2"],
                        },
                    }
                    evidence.append(verdict["evidence"])

        # Tier 2 (positive-sea verification): close out the verdict.
        # The mainland membership was already computed above.
        if verdict is None and land_poly is not None:
            if in_mainland:
                # Inland but no positive water-body containment AND
                # nothing within 500 m of a tagged water polygon.
                verdict = {
                    "type": "unknown",
                    "subtype": None,
                    "parentWaterBody": None,
                    "confidence": "low",
                    "evidence": {
                        "source": "land-in-no-water",
                        "note": "centroid sits inside the GB/Ireland mainland "
                                "polygon but no water-body polygon is within "
                                f"{TIER4_LOW_M} m",
                    },
                }
                evidence.append(verdict["evidence"])
            else:
                # Confirmed sea-side of the coastline.
                verdict = {
                    "type": "sea",
                    "subtype": None,
                    "parentWaterBody": None,
                    "confidence": "high",
                    "evidence": {
                        "source": "osm-coastline",
                        "note": "centroid is sea-side of OSM natural=coastline",
                    },
                }
                evidence.append(verdict["evidence"])

        # No verdict at all -- leave as-is but mark for review.
        after_type = (verdict or {}).get("type", before_type)
        summary["byTypeAfter"][after_type] += 1
        summary["byTier"][(verdict or {}).get("evidence", {}).get("source", "no-evidence")] += 1
        if verdict and after_type != before_type:
            summary["changed"] += 1
            summary["transitions"][(before_type, after_type)] += 1
            proposals.append({
                "id": isl["id"],
                "name": isl["name"],
                "nation": isl.get("nation", ""),
                "lat": isl["lat"],
                "lng": isl["lng"],
                "before": {
                    "type": before_type,
                    "subtype": isl.get("subtype"),
                    "parentWaterBody": isl.get("parentWaterBody"),
                    "classification": isl.get("classification"),
                },
                "after": {
                    "type": after_type,
                    "subtype": verdict.get("subtype"),
                    "parentWaterBody": verdict.get("parentWaterBody"),
                    "classification": {
                        "source": verdict["evidence"].get("source"),
                        "confidence": verdict["confidence"],
                    },
                },
                "evidence": evidence,
            })
        else:
            summary["kept_unchanged"] += 1

    return proposals, summary


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch-wd", action="store_true", help="Fetch Wikidata P206 + body P31")
    parser.add_argument("--fetch-coast", action="store_true", help="Fetch OSM coastline")
    parser.add_argument("--fetch-water", action="store_true", help="Fetch widened OSM water")
    parser.add_argument("--classify", action="store_true", help="Run classifier from caches")
    parser.add_argument("--all", action="store_true", help="Run everything end-to-end")
    parser.add_argument("--refresh-wd", action="store_true", help="Ignore cached Wikidata entries")
    parser.add_argument("--refresh-coast", action="store_true", help="Re-fetch coastline")
    parser.add_argument("--refresh-water", action="store_true", help="Re-fetch water")
    parser.add_argument("--limit-wd", type=int, default=None, help="Only fetch first N missing islands")
    args = parser.parse_args()

    if args.all:
        args.fetch_wd = args.fetch_coast = args.fetch_water = args.classify = True
    if not (args.fetch_wd or args.fetch_coast or args.fetch_water or args.classify):
        parser.print_help()
        return 1

    islands = json.loads(ISLANDS_PATH.read_text(encoding="utf-8"))
    print(f"Loaded {len(islands):,} islands from {ISLANDS_PATH.name}")

    wd_cache = _load_cache(CACHE_WD, {"islands": {}, "bodies": {}})

    # ----- Tier 1 fetch -----
    if args.fetch_wd:
        qids = [i["wikidata"] for i in islands if i.get("wikidata")]
        if args.limit_wd:
            missing = [q for q in qids if q not in (wd_cache.get("islands") or {})]
            qids = sorted(set(missing))[: args.limit_wd]
        wd_cache = fetch_wikidata_water_bodies(qids, wd_cache, refresh=args.refresh_wd)

    # ----- Tier 2 fetch -----
    if args.fetch_coast:
        fetch_coastline(refresh=args.refresh_coast)

    # ----- Tier 3 fetch -----
    if args.fetch_water:
        fetch_widened_water(refresh=args.refresh_water)

    # ----- Classify -----
    if args.classify:
        # Tier 2 needs the *mainland* polygon (Britain + Ireland only) --
        # NOT the full land set -- because every island is itself a land
        # polygon, so a generic `land.contains(pt)` test is useless.  The
        # mainland test distinguishes river/lake islets (which sit inside
        # Britain or Ireland) from marine islands (which sit in their own
        # smaller polygon, outside both).  Built offline by
        # scripts/build_land_polygons.py.
        land_poly = None
        if MAINLAND_PICKLE.exists():
            import pickle as _pickle
            print(f"Loading mainland polygons from {MAINLAND_PICKLE.name}…", flush=True)
            with open(MAINLAND_PICKLE, "rb") as f:
                land_poly = _pickle.load(f)
            ncomp = len(getattr(land_poly, "geoms", [land_poly]))
            print(f"  {ncomp:,} mainland components (GB + Ireland)", flush=True)
        elif LAND_PICKLE.exists():
            print(f"WARN: {MAINLAND_PICKLE.name} missing; re-run "
                  f"scripts/build_land_polygons.py to regenerate", file=sys.stderr)
        elif CACHE_COAST.exists():
            print("WARN: no land pickle; run scripts/build_land_polygons.py first", file=sys.stderr)
        else:
            print("WARN: no coastline/land data; running without Tier 2", flush=True)

        if not CACHE_WATER.exists():
            print("WARN: water cache missing; running without Tier 3", flush=True)
            water_bodies: list[dict] = []
        else:
            print("Building water-body polygons from widened water cache…", flush=True)
            water_data = _load_cache(CACHE_WATER, {})
            water_bodies = build_water_bodies(water_data, wd_cache=wd_cache)
            print(f"  built {len(water_bodies):,} water-body polygons", flush=True)

        print("Running classifier…", flush=True)
        proposals, summary = classify(islands, wd_cache, land_poly, water_bodies)

        _atomic_write(PROPOSAL_PATH, proposals)
        # Normalise Counter → dict for JSON
        summary["byTier"] = dict(summary["byTier"])
        summary["byTypeBefore"] = dict(summary["byTypeBefore"])
        summary["byTypeAfter"] = dict(summary["byTypeAfter"])
        summary["transitions"] = {f"{a}→{b}": n for (a, b), n in summary["transitions"].items()}
        _atomic_write(SUMMARY_PATH, summary)

        print()
        print(f"Proposal: {summary['changed']:,} of {summary['total']:,} islands would change")
        print(f"  unchanged: {summary['kept_unchanged']:,}")
        print(f"  protected by Tier 0 (existing classification): {summary['skippedTierA_B']:,}")
        print(f"  type AFTER: {summary['byTypeAfter']}")
        print(f"  transitions: {summary['transitions']}")
        print(f"  → {PROPOSAL_PATH.name}, {SUMMARY_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
