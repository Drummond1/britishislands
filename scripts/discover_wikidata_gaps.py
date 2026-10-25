#!/usr/bin/env python3
"""Find Wikidata islands not yet matched in the atlas (discovery-push #5).

Queries Wikidata SPARQL for items that are an instance of (or subclass of)
island — which via ``wdt:P279*`` also covers islets, skerries, holms, etc. —
scoped to the UK, Ireland, Isle of Man, Jersey and Guernsey (``wdt:P17``
country statements), then keeps only those that fall inside the atlas
UK+IE bounding box and have no existing match in ``data/islands.json``.

Output schema mirrors ``data/discovery/candidates_geonames.json`` so it can
be reviewed/merged with the same downstream tooling. This script only
writes discovery candidate files — it never touches ``data/islands.json``.

Run::

    python3 scripts/discover_wikidata_gaps.py
    python3 scripts/discover_wikidata_gaps.py --limit=50
    python3 scripts/discover_wikidata_gaps.py --no-network   # cache/seed only
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "discovery" / "candidates_wikidata.json"
REPORT = DATA / "discovery_wikidata_gaps_report.json"
CACHE_PATH = DATA / "cache_discovery_wikidata_gaps.json"
LEGACY_CACHE_PATH = DATA / "cache_wd_islands.json"  # seed source (scripts/ingest_sources.py)

sys.path.insert(0, str(ROOT / "scripts"))
from discovery import common as c  # noqa: E402

MATCH_KM = 1.0
DELAY_S = 0.3

WD_COUNTRIES = [
    ("Q145", "UK"),
    ("Q27", "Ireland"),
    ("Q9676", "Isle of Man"),
    ("Q785", "Jersey"),
    ("Q3311985", "Bailiwick of Guernsey"),
]

# wd:Q23442 = island. wdt:P279* over the class hierarchy also pulls in
# islet, skerry, holm, tidal island, etc. since those are modelled as
# subclasses of island on Wikidata.
WD_QUERY = """
SELECT ?item ?itemLabel ?coord ?wikipedia ?instanceLabel WHERE {
  ?item wdt:P31/wdt:P279* wd:Q23442 .
  ?item wdt:P17 wd:%s .
  ?item wdt:P625 ?coord .
  ?item wdt:P31 ?instance .
  OPTIONAL {
    ?wikipedia schema:about ?item ;
               schema:isPartOf <https://en.wikipedia.org/> .
  }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
"""

FEATURE_KIND_HINTS = (
    ("islet", "islet"),
    ("skerry", "islet"),
    ("stack", "rock"),
    ("rock", "rock"),
    ("holm", "islet"),
)


def _parse_point_wkt(wkt: str) -> tuple[float, float] | None:
    m = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", wkt)
    if not m:
        return None
    return float(m.group(2)), float(m.group(1))  # (lat, lng)


def _seed_cache_from_legacy(cache: dict[str, Any]) -> dict[str, Any]:
    """Reuse scripts/ingest_sources.py's raw SPARQL rows if present, so a
    fresh run doesn't have to re-hit query.wikidata.org for countries we
    already fetched previously."""
    if not LEGACY_CACHE_PATH.exists():
        return cache
    legacy = c.load_json(LEGACY_CACHE_PATH, {})
    for qid, entry in legacy.items():
        if qid not in cache and entry.get("rows"):
            cache[qid] = {"rows": entry["rows"], "fetched": entry.get("fetched"), "seededFromLegacy": True}
    return cache


def _fetch_rows(*, allow_network: bool, refresh: bool) -> list[dict[str, Any]]:
    cache = c.load_json(CACHE_PATH, {})
    if not refresh:
        cache = _seed_cache_from_legacy(cache)
    all_rows: list[dict[str, Any]] = []
    for qid, label in WD_COUNTRIES:
        if not refresh and qid in cache and cache[qid].get("rows") is not None:
            rows = cache[qid]["rows"]
            print(f"  {label} ({qid}) — cached ({len(rows)} rows)", file=sys.stderr)
            all_rows.extend(rows)
            continue
        if not allow_network:
            print(f"  {label} ({qid}) — no cache, network disabled, skipping", file=sys.stderr)
            continue
        try:
            print(f"  querying {label} ({qid})…", file=sys.stderr)
            payload = c.post_sparql(WD_QUERY % qid)
            rows = payload.get("results", {}).get("bindings", [])
            cache[qid] = {"rows": rows, "fetched": time.time()}
            c.save_json(CACHE_PATH, cache)
            print(f"    {len(rows)} rows", file=sys.stderr)
            all_rows.extend(rows)
            time.sleep(DELAY_S)
        except Exception as exc:
            print(f"    failed: {exc!r}", file=sys.stderr)
            cache.setdefault(qid, {"rows": [], "error": str(exc)})
            c.save_json(CACHE_PATH, cache)
    return all_rows


def _feature_kind(name: str, instance_label: str) -> str:
    blob = f"{name} {instance_label}".lower()
    for needle, kind in FEATURE_KIND_HINTS:
        if needle in blob:
            return kind
    return "island"


def _nearest_atlas_km(lat: float, lng: float, islands: list[dict]) -> float:
    best = 9999.0
    for isl in islands:
        ilat, ilng = isl.get("lat"), isl.get("lng") or isl.get("lon")
        if ilat is None or ilng is None:
            continue
        d = c.haversine_km(lat, lng, float(ilat), float(ilng))
        if d < best:
            best = d
    return best


def _normalise_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Dedupe raw SPARQL bindings by Q-ID (an item can match >1 country query
    when it straddles a border, e.g. Ireland/Northern Ireland loughs)."""
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        qid = row["item"]["value"].rsplit("/", 1)[-1]
        if qid in out:
            continue
        wkt = (row.get("coord") or {}).get("value", "")
        latlng = _parse_point_wkt(wkt) if wkt else None
        if not latlng:
            continue
        lat, lng = latlng
        if not c.in_remit(lat, lng):
            continue
        name = (row.get("itemLabel") or {}).get("value", "")
        if not name or name == qid:
            continue
        out[qid] = {
            "qid": qid,
            "name": name,
            "lat": round(lat, 5),
            "lng": round(lng, 5),
            "wikipedia": (row.get("wikipedia") or {}).get("value", ""),
            "instanceLabel": (row.get("instanceLabel") or {}).get("value", ""),
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None, help="cap number of gap candidates written")
    ap.add_argument("--match-km", type=float, default=MATCH_KM)
    ap.add_argument("--no-network", action="store_true", help="use cache/legacy-cache only, no live SPARQL")
    ap.add_argument("--refresh", action="store_true", help="ignore cache and re-query all countries")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    print("→ Wikidata SPARQL by country (island class incl. islet/skerry/holm subclasses)", file=sys.stderr)
    raw_rows = _fetch_rows(allow_network=not args.no_network, refresh=args.refresh)
    points = _normalise_rows(raw_rows)
    print(f"Wikidata: {len(points):,} in-remit island items (deduped by Q-ID)", flush=True)

    islands = c.load_islands()
    index = c.build_island_index(islands)

    candidates: list[dict[str, Any]] = []
    matched = 0
    for point in points.values():
        lat, lng = point["lat"], point["lng"]
        name = point["name"]
        candidate_probe = {"name": name, "lat": lat, "lng": lng, "wikidata": point["qid"]}
        if c.find_existing_match(candidate_probe, index):
            matched += 1
            continue
        d_km = _nearest_atlas_km(lat, lng, islands)
        if d_km <= args.match_km:
            matched += 1
            continue
        candidates.append({
            "candidateId": f"wikidata-{point['qid']}",
            "name": name,
            "lat": lat,
            "lng": lng,
            "nation": c.nation_for(lat, lng),
            "featureKind": _feature_kind(name, point["instanceLabel"]),
            "osmType": None,
            "osmId": None,
            "wikidata": point["qid"],
            "wikipedia": point["wikipedia"],
            "scanConfidence": "high",
            "nearestAtlasKm": round(d_km, 3),
            "sourceHints": [{
                "name": "Wikidata",
                "url": f"https://www.wikidata.org/wiki/{point['qid']}",
                "license": "CC0",
            }],
            "tags": ["island", "wikidata"],
        })
        if args.limit and len(candidates) >= args.limit:
            break

    candidates.sort(key=lambda x: x["name"].lower())

    report = {
        "wikidataItems": len(points),
        "alreadyInDatabase": matched,
        "gaps": len(candidates),
        "matchKm": args.match_km,
        "countries": [label for _, label in WD_COUNTRIES],
    }
    print(
        f"Wikidata gaps: {len(candidates):,} (>{args.match_km} km / no name+QID match against "
        f"{len(islands):,} atlas islands; {matched:,} already matched)",
        flush=True,
    )

    if not args.dry_run:
        c.save_json(OUT, candidates)
        c.save_json(REPORT, report)
        print(f"Wrote {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
