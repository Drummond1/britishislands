#!/usr/bin/env python3
"""Find GeoNames islands (ISL/ISLT) not yet matched in the atlas (#11).

Downloads ``GB.zip`` and ``IE.zip`` from geonames.org when missing, parses
hydrographic island features, and writes gap candidates to
``data/discovery/candidates_geonames.json``.

Run::

    python3 scripts/discover_geonames_gaps.py
    python3 scripts/discover_geonames_gaps.py --no-download
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
OUT = DATA / "discovery" / "candidates_geonames.json"
REPORT = DATA / "discovery_geonames_report.json"
USER_AGENT = "isles-of-britain/0.1 (discover-geonames)"
MATCH_KM = 1.0

GEONAMES_URLS = {
    "GB": "http://download.geonames.org/export/dump/GB.zip",
    "IE": "http://download.geonames.org/export/dump/IE.zip",
}

sys.path.insert(0, str(ROOT / "scripts"))
from discovery import common as c  # noqa: E402

ISLAND_CODES = frozenset({"ISL", "ISLT"})


def _download_country(code: str) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    dest = RAW / f"geonames_{code}.txt"
    if dest.is_file() and dest.stat().st_size > 1000:
        return dest
    url = GEONAMES_URLS[code]
    print(f"Downloading GeoNames {code}…", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=300) as resp:
        blob = resp.read()
    with zipfile.ZipFile(BytesIO(blob)) as zf:
        inner = f"{code}.txt"
        dest.write_bytes(zf.read(inner))
    print(f"  → {dest} ({dest.stat().st_size // 1024} KiB)", flush=True)
    return dest


def _parse_geonames(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 18:
                continue
            fclass, fcode = cols[6], cols[7]
            if fclass != "T" or fcode not in ISLAND_CODES:
                continue
            try:
                lat, lon = float(cols[4]), float(cols[5])
            except ValueError:
                continue
            if not c.in_remit(lat, lon):
                continue
            name = cols[1] or cols[2]
            if not name:
                continue
            rows.append({
                "geonameId": cols[0],
                "name": name,
                "lat": round(lat, 5),
                "lng": round(lon, 5),
                "featureCode": fcode,
                "country": cols[8],
            })
    return rows


def _nearest_atlas_km(lat: float, lon: float, islands: list[dict]) -> float:
    best = 9999.0
    for isl in islands:
        ilat, ilon = isl.get("lat"), isl.get("lng") or isl.get("lon")
        if ilat is None or ilon is None:
            continue
        d = c.haversine_km(lat, lon, float(ilat), float(ilon))
        if d < best:
            best = d
    return best


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-download", action="store_true")
    ap.add_argument("--match-km", type=float, default=MATCH_KM)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    points: list[dict[str, Any]] = []
    for code in ("GB", "IE"):
        path = RAW / f"geonames_{code}.txt"
        if not path.is_file() and not args.no_download:
            path = _download_country(code)
        elif not path.is_file():
            print(f"Missing {path} — run without --no-download", file=sys.stderr)
            continue
        chunk = _parse_geonames(path)
        print(f"GeoNames {code}: {len(chunk):,} island features", flush=True)
        points.extend(chunk)

    islands = c.load_islands()
    index = c.build_island_index(islands)
    candidates: list[dict[str, Any]] = []
    for pt in points:
        nk = c.name_key(pt["name"])
        if nk and index["name"].get(nk):
            continue
        d_km = _nearest_atlas_km(pt["lat"], pt["lng"], islands)
        if d_km <= args.match_km:
            continue
        gid = pt["geonameId"]
        candidates.append({
            "candidateId": f"geonames-{gid}",
            "name": pt["name"],
            "lat": pt["lat"],
            "lng": pt["lng"],
            "nation": c.nation_for(pt["lat"], pt["lng"]),
            "featureKind": "islet" if pt["featureCode"] == "ISLT" else "island",
            "osmType": None,
            "osmId": None,
            "wikidata": "",
            "wikipedia": "",
            "scanConfidence": "medium",
            "nearestAtlasKm": round(d_km, 3),
            "sourceHints": [{
                "name": "GeoNames",
                "url": f"https://www.geonames.org/{gid}",
                "license": "CC-BY-4.0",
            }],
            "tags": ["island", "geonames", pt["featureCode"].lower()],
        })

    report = {
        "geonamesPoints": len(points),
        "gaps": len(candidates),
        "matchKm": args.match_km,
    }
    print(f"GeoNames gaps: {len(candidates):,} (>{args.match_km} km from nearest atlas island)", flush=True)

    if not args.dry_run:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(candidates, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
