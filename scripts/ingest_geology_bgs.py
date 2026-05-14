#!/usr/bin/env python3
"""
Ingest BGS 1:625,000 bedrock and superficial geology for each island
via point-in-polygon against the published WMS.

Source / licence
----------------
British Geological Survey, **DigMapGB-625 (1:625,000)** bedrock and
superficial geology, published as the **BGS Bedrock and Superficial
Geology WMS**:

  https://ogc.bgs.ac.uk/cgi-bin/BGS_Bedrock_and_Superficial_Geology/wms

This is the official 1:625k DigMapGB OGC service, contributing to the
OneGeology initiative.  Licensed under the **BGS Open Data Licence
(OGL v3.0)**.  Attribution required:
"Contains British Geological Survey materials © UKRI 2026 (OGL v3.0)".

Coverage is **Great Britain only** — Northern Ireland, Republic of
Ireland, Isle of Man and the Channel Islands fall outside the WMS
extent.  Those islands get ``geology.confidence: "n/a"``.  The Geological
Survey of Northern Ireland (GSNI) publishes equivalent data; a follow-up
workstream can ingest from GSNI's WMS at a later date.

Method
------
1. For each island, send a ``GetFeatureInfo`` query to the BGS WMS
   centred on the island's centroid.  We use the
   ``GBR_BGS_625k_BLS`` (Bedrock Lithostratigraphy) and
   ``GBR_BGS_625k_SLS`` (Superficial Lithostratigraphy) layers.

2. The response is text/plain key-value pairs; we parse the relevant
   columns:
   * ``LEX_D``  — unit name (e.g. "TORRIDON GROUP")
   * ``RCS_D``  — rock category description (e.g. "SANDSTONE")
   * ``MAX_TIME_D`` / ``MIN_TIME_D`` — age start / end
   * ``MAX_TIME_Y`` / ``MIN_TIME_Y`` — age in years

3. We **cache by rounded centroid** (4 dp ≈ 11 m): adjacent islets in
   the same archipelago hit the same geological unit, so this dedups
   the network traffic ~5–10×.

4. The cache file is ``data/cache_bgs.json``.  The staged enrichment
   file is also ``data/cache_bgs.json`` keyed by ``islandId`` (the same
   file does double duty as cache + staging; the merge step keys on
   ``islandId``).

CLI::

    python3 scripts/ingest_geology_bgs.py --dry-run --limit 20
    python3 scripts/ingest_geology_bgs.py --fetch --commit --limit 200
    python3 scripts/ingest_geology_bgs.py --fetch --commit          # full run

Important: this is the slowest of the five ingestion scripts.  At
~0.5 req/s polite throttle and ~3 km island spacing, expect roughly
one hour per 1,000 unique grid cells.  Use ``--limit`` for first runs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS_PATH = DATA / "islands.json"

STAGED_CACHE = DATA / "cache_bgs.json"
GFI_CACHE = DATA / "cache_bgs_gfi.json"             # per-coord raw responses
REPORT = DATA / "bgs_ingestion_report.json"

BGS_WMS = (
    "https://ogc.bgs.ac.uk/cgi-bin/BGS_Bedrock_and_Superficial_Geology/wms"
)
USER_AGENT = "isles-of-britain/0.8 (ingest_geology_bgs; static-site)"
DELAY_S = 0.5      # polite throttle for the public WMS
CACHE_RES = 4      # decimal places to round coords for the cache key

# GB-only bbox (deliberately tight — outside this we mark n/a).
GB_BBOX = (49.5, -8.5, 61.0, 2.0)


# ---------- HTTP / IO ----------

def _curl_get_text(url: str, *, timeout: int = 60) -> str:
    res = subprocess.run(
        ["curl", "-sS", "--max-time", str(timeout),
         "-H", f"User-Agent: {USER_AGENT}", url],
        capture_output=True, timeout=timeout + 15,
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"BGS curl rc={res.returncode} "
            f"stderr={res.stderr.decode('utf-8','replace')[:200]}"
        )
    return res.stdout.decode("utf-8", "replace")


def _atomic_write_json(path: Path, payload: Any, *, compact: bool = False) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    body = (json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            if compact else json.dumps(payload, ensure_ascii=False, indent=2))
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, path)


def _load_json(path: Path, default):
    if not path.exists(): return default
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"  WARN: {path.name} unreadable ({exc})", file=sys.stderr)
        return default


# ---------- WMS GetFeatureInfo ----------

def _wms_get_feature_info(lat: float, lng: float, layer: str) -> dict | None:
    """Return parsed feature info dict, or None on miss / outside extent.

    Constructs a tiny synthetic bbox around the point (1 km) and
    queries the centre pixel.
    """
    half = 0.005  # ~0.5° / 100 ≈ 555 m at 55° latitude
    s = lat - half; n = lat + half
    w = lng - half; e = lng + half
    params = {
        "SERVICE": "WMS",
        "VERSION": "1.3.0",
        "REQUEST": "GetFeatureInfo",
        "LAYERS": layer,
        "QUERY_LAYERS": layer,
        "CRS": "EPSG:4326",
        "BBOX": f"{s},{w},{n},{e}",
        "WIDTH": "200",
        "HEIGHT": "200",
        "I": "100",
        "J": "100",
        "INFO_FORMAT": "text/plain",
        "STYLES": "",
    }
    url = BGS_WMS + "?" + urllib.parse.urlencode(params)
    try:
        body = _curl_get_text(url, timeout=30)
    except Exception as exc:
        return {"_error": str(exc)}
    if "<ServiceException" in body or not body.strip():
        return None
    # Parse "key = 'value'" pairs.
    out: dict[str, str] = {}
    cur_feature: dict[str, str] | None = None
    features: list[dict[str, str]] = []
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("Feature"):
            if cur_feature: features.append(cur_feature)
            cur_feature = {}
            continue
        m = re.match(r"^([A-Z][A-Z0-9_]+)\s*=\s*'(.*)'\s*$", line)
        if m and cur_feature is not None:
            cur_feature[m.group(1)] = m.group(2)
    if cur_feature: features.append(cur_feature)
    if not features:
        return None
    # Pick the first non-empty feature.
    return features[0] | {"_layer": layer}


def _normalise_bedrock(f: dict) -> dict:
    """Turn a raw GetFeatureInfo feature into our schema."""
    name = (f.get("LEX_D") or "").strip().title() or None
    if name == "":
        name = None
    lith = (f.get("RCS_D") or "").strip().title() or None
    age_start = (f.get("MAX_TIME_D") or "").strip().title() or None
    age_end = (f.get("MIN_TIME_D") or "").strip().title() or None
    try:
        start_y = int(f.get("MAX_TIME_Y", ""))
    except (TypeError, ValueError):
        start_y = None
    try:
        end_y = int(f.get("MIN_TIME_Y", ""))
    except (TypeError, ValueError):
        end_y = None
    out = {
        "name": name,
        "lithology": lith,
        "ageStart": age_start,
        "ageEnd": age_end,
    }
    if start_y: out["ageStartMa"] = round(start_y / 1_000_000, 1)
    if end_y: out["ageEndMa"] = round(end_y / 1_000_000, 1)
    return out


def _normalise_superficial(f: dict) -> dict:
    name = (f.get("LEX_D") or "").strip().title() or None
    lith = (f.get("RCS_D") or "").strip().title() or None
    return {"name": name, "lithology": lith}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fetch", action="store_true",
                    help="Run the BGS WMS queries (network)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--limit", type=int, default=0,
                    help="Process at most N islands (debug)")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--max-fetches", type=int, default=0,
                    help="Cap the number of *new* WMS calls in this run "
                         "(useful for incremental builds; 0 = no cap)")
    args = ap.parse_args()

    if not ISLANDS_PATH.exists(): sys.exit(f"FATAL: {ISLANDS_PATH} missing")
    islands = _load_json(ISLANDS_PATH, [])
    if not islands: sys.exit("FATAL: islands.json empty")
    print(f"Loaded {len(islands):,} islands")

    gfi_cache: dict[str, dict] = _load_json(GFI_CACHE, {})
    print(f"  GFI cache: {len(gfi_cache):,} entries cached")

    if args.limit:
        islands = islands[: args.limit]
    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    attribution = (
        "Contains British Geological Survey materials © UKRI 2026, "
        "licensed under the BGS Open Data Licence (OGL v3.0). "
        "Source: BGS DigMapGB-625 Bedrock & Superficial WMS."
    )

    staged: dict[str, dict] = {}
    audit: list[dict] = []
    counts = {"with_bedrock": 0, "with_superficial": 0,
              "outside_gb": 0, "miss": 0, "fetches": 0}
    new_fetches_this_run = 0
    for n, isl in enumerate(islands):
        if n and n % 200 == 0:
            print(f"  …{n}/{len(islands)} "
                  f"(bedrock {counts['with_bedrock']}, "
                  f"superficial {counts['with_superficial']}, "
                  f"outside-GB {counts['outside_gb']})", flush=True)
        iid = isl.get("id"); ilat = isl.get("lat"); ilng = isl.get("lng")
        if not iid or ilat is None or ilng is None:
            continue
        # Skip islands outside the GB extent — these get a structured
        # n/a so the apply script doesn't have to guess.
        if not (GB_BBOX[0] <= ilat <= GB_BBOX[2]
                and GB_BBOX[1] <= ilng <= GB_BBOX[3]):
            counts["outside_gb"] += 1
            staged[iid] = {
                "geology": {
                    "bedrock": None, "superficial": None,
                    "source": "bgs-digmapgb-625",
                    "confidence": "n/a",
                    "attribution": attribution,
                    "fetchedAt": fetched_at,
                    "_note": "Outside BGS extent (covers GB only); GSNI / GSI / Channel Islands geology is a future workstream.",
                }
            }
            continue
        # Round to 4 dp for caching.
        key = f"{round(float(ilat), CACHE_RES)},{round(float(ilng), CACHE_RES)}"
        cached = gfi_cache.get(key)
        if cached is None:
            if not args.fetch:
                continue
            if args.max_fetches and new_fetches_this_run >= args.max_fetches:
                continue
            try:
                bed = _wms_get_feature_info(float(ilat), float(ilng), "GBR_BGS_625k_BLS")
            except Exception as exc:
                if args.verbose:
                    print(f"  ! bedrock failed for {iid}: {exc}", file=sys.stderr)
                bed = None
            time.sleep(DELAY_S)
            try:
                sup = _wms_get_feature_info(float(ilat), float(ilng), "GBR_BGS_625k_SLS")
            except Exception as exc:
                if args.verbose:
                    print(f"  ! superficial failed for {iid}: {exc}", file=sys.stderr)
                sup = None
            time.sleep(DELAY_S)
            cached = {"bedrock": bed, "superficial": sup,
                      "fetchedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
            gfi_cache[key] = cached
            counts["fetches"] += 1
            new_fetches_this_run += 1
            if counts["fetches"] % 25 == 0:
                _atomic_write_json(GFI_CACHE, gfi_cache, compact=True)
                print(f"    [cache flush, {len(gfi_cache):,} entries]", flush=True)
        bedrock = cached.get("bedrock")
        sup = cached.get("superficial")
        if not bedrock:
            counts["miss"] += 1
            continue
        norm_bed = _normalise_bedrock(bedrock) if bedrock else None
        norm_sup = _normalise_superficial(sup) if sup else None
        if not norm_bed or not norm_bed.get("name"):
            counts["miss"] += 1
            continue
        confidence = "high"
        if norm_bed.get("name") in (None, "", "Unconsolidated Deposits"):
            confidence = "medium"
        staged[iid] = {
            "geology": {
                "bedrock": norm_bed,
                "superficial": norm_sup if norm_sup and norm_sup.get("name") else None,
                "source": "bgs-digmapgb-625",
                "confidence": confidence,
                "attribution": attribution,
                "fetchedAt": fetched_at,
            }
        }
        counts["with_bedrock"] += 1
        if norm_sup and norm_sup.get("name"):
            counts["with_superficial"] += 1
        if len(audit) < 50:
            audit.append({
                "id": iid, "name": isl.get("name"),
                "bedrock": norm_bed, "superficial": norm_sup,
            })
        if args.verbose:
            print(f"  + {isl.get('name')}: "
                  f"{norm_bed.get('name')} ({norm_bed.get('lithology')})",
                  flush=True)

    if args.fetch:
        _atomic_write_json(GFI_CACHE, gfi_cache, compact=True)
        print(f"  GFI cache flushed (final {len(gfi_cache):,} entries)")

    report = {
        "startedAt": fetched_at,
        "islandsProcessed": len(islands),
        "newWMSFetches": counts["fetches"],
        "islandsWithBedrock": counts["with_bedrock"],
        "islandsWithSuperficial": counts["with_superficial"],
        "islandsOutsideGB": counts["outside_gb"],
        "islandsMissingBedrock": counts["miss"],
        "sampleAudit": audit,
        "dryRun": bool(args.dry_run or not args.commit),
    }
    _atomic_write_json(REPORT, report)
    print()
    print(f"Audit  → {REPORT.name}")
    print(f"Coverage: {counts['with_bedrock']:,} islands have bedrock, "
          f"{counts['with_superficial']:,} also have superficial")
    print(f"Outside BGS extent (IE/NI/IoM/CI): {counts['outside_gb']:,}")
    print(f"GB islands with no resolvable bedrock: {counts['miss']:,}")

    if args.dry_run:
        print(f"\nDRY RUN — cache_bgs.json NOT written. "
              f"Would have staged {len(staged):,} islands.")
        return 0
    if not args.commit:
        print("\n(--commit not supplied; cache_bgs.json NOT written.)")
        return 0
    _atomic_write_json(STAGED_CACHE, staged)
    print(f"\nStaged cache → {STAGED_CACHE.name} ({len(staged):,} islands)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
