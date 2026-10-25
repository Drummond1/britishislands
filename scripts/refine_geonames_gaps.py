#!/usr/bin/env python3
"""Re-filter GeoNames gap candidates with fixed name_key + fuzzy near-dup drop.

Reads existing ``data/raw/geonames_{GB,IE}.txt`` and writes a cleaned gap file
``data/discovery/candidates_geonames.json`` (overwrites). Also writes
``candidates_geonames_strict.json`` with only gaps that are ≥2 km from every
atlas island AND fail fuzzy name match within 20 km.

Run::

    python3 scripts/discover_geonames_gaps.py --no-download --match-km 2
    # or this cleaner:
    python3 scripts/refine_geonames_gaps.py
"""

from __future__ import annotations

import argparse
import json
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
OUT = DATA / "discovery" / "candidates_geonames.json"
OUT_STRICT = DATA / "discovery" / "candidates_geonames_strict.json"
REPORT = DATA / "discovery_geonames_refine_report.json"
ISLAND_CODES = frozenset({"ISL", "ISLT"})

sys.path.insert(0, str(ROOT / "scripts"))
from discovery import common as c  # noqa: E402

HILL_RE_SKIP = (
    # GeoNames mistags: summits coded as ISL
    "goatfell",
    "goat fell",
    "an cliseam",
    "clisham",
    "great britain",
    "mynydd bodafon",
)

NON_ISLAND_NAME_RE = __import__("re").compile(
    r"\b(salt\s*marsh|mynydd|pond|camas|creag|scar|leap|bar|buoy|buoys)\b|"
    r"^the islands?$|^great britain$",
    __import__("re").I,
)


def _parse(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    with path.open(encoding="utf-8") as f:
        for line in f:
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 18:
                continue
            if cols[6] != "T" or cols[7] not in ISLAND_CODES:
                continue
            try:
                lat, lon = float(cols[4]), float(cols[5])
            except ValueError:
                continue
            if not c.in_remit(lat, lon):
                continue
            name = (cols[1] or cols[2] or "").strip()
            if not name:
                continue
            rows.append({
                "geonameId": cols[0],
                "name": name,
                "lat": round(lat, 5),
                "lng": round(lon, 5),
                "featureCode": cols[7],
            })
    return rows


def _fuzzy_near(name: str, lat: float, lon: float, islands: list[dict], *, km: float = 20.0) -> bool:
    nk = c.name_key(name)
    for isl in islands:
        ilat, ilon = isl.get("lat"), isl.get("lng") or isl.get("lon")
        if ilat is None or ilon is None:
            continue
        if c.haversine_km(lat, lon, float(ilat), float(ilon)) > km:
            continue
        other = c.name_key(isl.get("name") or "")
        if not nk or not other:
            continue
        if nk == other:
            return True
        if SequenceMatcher(None, nk, other).ratio() >= 0.72:
            return True
        # Containment: "skye" in "isle of skye" keys
        if len(nk) >= 4 and (nk in other or other in nk):
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--match-km", type=float, default=2.0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    points: list[dict] = []
    for code in ("GB", "IE"):
        points.extend(_parse(RAW / f"geonames_{code}.txt"))

    islands = c.load_islands()
    index = c.build_island_index(islands)

    gaps: list[dict] = []
    strict: list[dict] = []
    stats = {
        "points": len(points),
        "droppedExactName": 0,
        "droppedProximity": 0,
        "droppedFuzzy": 0,
        "droppedHill": 0,
        "gaps": 0,
        "strict": 0,
    }

    for pt in points:
        name = pt["name"]
        if name.lower() in HILL_RE_SKIP or any(h in name.lower() for h in HILL_RE_SKIP):
            stats["droppedHill"] += 1
            continue
        if NON_ISLAND_NAME_RE.search(name):
            stats["droppedHill"] += 1
            continue
        nk = c.name_key(name)
        if nk and index["name"].get(nk):
            # also require proximity for exact key
            near = False
            for isl in index["name"][nk]:
                if c.haversine_km(pt["lat"], pt["lng"], float(isl["lat"]), float(isl["lng"] or isl.get("lon"))) <= 25:
                    near = True
                    break
            if near:
                stats["droppedExactName"] += 1
                continue

        # nearest distance
        best = 9999.0
        for isl in islands:
            d = c.haversine_km(pt["lat"], pt["lng"], float(isl["lat"]), float(isl.get("lng") or isl.get("lon")))
            if d < best:
                best = d
        if best <= args.match_km:
            stats["droppedProximity"] += 1
            continue

        if _fuzzy_near(name, pt["lat"], pt["lng"], islands, km=20.0):
            stats["droppedFuzzy"] += 1
            continue

        cand = {
            "candidateId": f"geonames-{pt['geonameId']}",
            "name": name,
            "lat": pt["lat"],
            "lng": pt["lng"],
            "nation": c.nation_for(pt["lat"], pt["lng"]),
            "featureKind": "islet" if pt["featureCode"] == "ISLT" else "island",
            "osmType": None,
            "osmId": None,
            "wikidata": "",
            "wikipedia": "",
            "scanConfidence": "medium",
            "nearestAtlasKm": round(best, 3),
            "sourceHints": [{
                "name": "GeoNames",
                "url": f"https://www.geonames.org/{pt['geonameId']}",
                "license": "CC-BY-4.0",
            }],
            "tags": ["island", "geonames", pt["featureCode"].lower(), "refined-gap"],
        }
        gaps.append(cand)
        if best >= 3.0:
            strict.append(cand)

    stats["gaps"] = len(gaps)
    stats["strict"] = len(strict)
    print(json.dumps(stats, indent=2), flush=True)
    if not args.dry_run:
        OUT.write_text(json.dumps(gaps, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        OUT_STRICT.write_text(json.dumps(strict, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        REPORT.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {len(gaps)} gaps → {OUT}", flush=True)
        print(f"Wrote {len(strict)} strict (≥3 km) → {OUT_STRICT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
