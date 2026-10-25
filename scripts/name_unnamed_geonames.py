#!/usr/bin/env python3
"""Name unnamed islands via GeoNames ISL/ISLT spatial join (N7 reverse of D1).

Uses already-downloaded ``data/raw/geonames_{GB,IE}.txt``. Gap candidates in
``candidates_geonames.json`` are 1 km+ from the atlas; this script instead joins
GeoNames points to existing ``nameStatus=unknown`` polygons within 150 m.

Run::

    python3 scripts/name_unnamed_geonames.py
    python3 scripts/name_unnamed_geonames.py --limit 500 --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
STAGING = DATA / "staging" / "name_proposals" / "geonames-spatial.json"
REPORT = DATA / "name_proposals_geonames_report.json"
MAX_M = 150.0
ISLAND_CODES = frozenset({"ISL", "ISLT"})

sys.path.insert(0, str(ROOT / "scripts"))
from discovery import common as c  # noqa: E402
from name_staging_utils import (  # noqa: E402
    build_proposal,
    island_lon,
    load_unnamed,
    nearest_in_index,
    save_staging,
    spatial_index,
)


def _parse_geonames(path: Path) -> list[dict[str, Any]]:
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
                "lat": lat,
                "lon": lon,
                "featureCode": cols[7],
                "country": cols[8],
                "alternatenames": cols[3] or "",
            })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-m", type=float, default=MAX_M)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--nation", default="")
    args = ap.parse_args()

    pending = load_unnamed(nation=args.nation)
    if args.limit:
        pending = pending[: args.limit]

    points: list[dict[str, Any]] = []
    for code in ("GB", "IE"):
        points.extend(_parse_geonames(RAW / f"geonames_{code}.txt"))
    index = spatial_index(points, lat_key="lat", lon_key="lon", cell=0.02)

    proposals: list[dict] = []
    report: dict[str, Any] = {
        "script": "name_unnamed_geonames.py",
        "geonamesPoints": len(points),
        "pending": len(pending),
        "staged": 0,
        "adopted": [],
        "skipped": [],
    }

    print(
        f"GeoNames→unnamed: {len(points):,} ISL/ISLT × {len(pending):,} unnamed",
        flush=True,
    )

    for isl in pending:
        lat = isl.get("lat")
        lon = island_lon(isl)
        if lat is None or lon is None:
            continue
        hit, dist = nearest_in_index(
            float(lat), float(lon), index, max_m=args.max_m, cell=0.02
        )
        if not hit:
            report["skipped"].append({"id": isl.get("id"), "reason": "no-geonames"})
            continue
        alts: dict[str, str] = {}
        for part in (hit.get("alternatenames") or "").split(","):
            part = part.strip()
            if part and part != hit["name"]:
                alts[f"alt{len(alts)}"] = part
                if len(alts) >= 4:
                    break
        prop = build_proposal(
            isl,
            proposed_name=hit["name"],
            source="geonames-spatial",
            licence="CC-BY-4.0",
            source_page_url=f"https://www.geonames.org/{hit['geonameId']}",
            confidence_tier="A",
            name_confidence="high" if dist <= 75 else "medium-high",
            distance_m=dist,
            source_ref=f"geonames:{hit['geonameId']}",
            alternate_names=alts or None,
            inference_method="geonames-isl-islt-spatial-join",
            extra={"featureCode": hit.get("featureCode"), "geonamesCountry": hit.get("country")},
        )
        if not prop:
            report["skipped"].append({"id": isl.get("id"), "reason": "unusable-name"})
            continue
        proposals.append(prop)
        report["adopted"].append({
            "id": isl.get("id"),
            "name": hit["name"],
            "distanceM": round(dist, 1),
            "geonameId": hit["geonameId"],
        })

    report["staged"] = len(proposals)
    if not args.dry_run:
        save_staging(STAGING, proposals)
        c.save_json(REPORT, report)
    print(f"Staged {len(proposals):,} GeoNames name proposals → {STAGING}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
