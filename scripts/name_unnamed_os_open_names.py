#!/usr/bin/env python3
"""Spatial join unnamed islands to OS Open Names island/islet features (#16).

Requires ``data/raw/os_opennames.csv`` (run ``scripts/fetch_os_open_names.py``).
OGL v3.0; Tier A gate ≤100 m centroid match.

Run::

    python3 scripts/name_unnamed_os_open_names.py
    python3 scripts/name_unnamed_os_open_names.py --max-distance-m 100
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OPEN_NAMES = DATA / "raw" / "os_opennames.csv"
STAGING = DATA / "staging" / "name_proposals" / "os-open-names.json"
REPORT = DATA / "name_proposals_os_open_names_report.json"

sys.path.insert(0, str(ROOT / "scripts"))
from discovery import common as c  # noqa: E402
from name_staging_utils import (  # noqa: E402
    build_proposal,
    load_unnamed,
    nearest_in_index,
    save_staging,
    spatial_index,
)


def _parse_row(row: dict[str, str]) -> dict[str, Any] | None:
    name = (row.get("NAME1") or row.get("name") or "").strip()
    if not name:
        return None
    try:
        lat = float(row.get("LATITUDE") or row.get("lat") or "")
        lon = float(row.get("LONGITUDE") or row.get("lng") or row.get("lon") or "")
    except ValueError:
        return None
    if not c.in_remit(lat, lon):
        return None
    feature = (row.get("LOCAL_TYPE") or row.get("FEATURE_TYPE") or "").lower()
    if feature and "island" not in feature and "islet" not in feature:
        return None
    alternates: dict[str, str] = {}
    for key, val in row.items():
        ku = key.upper()
        if ku.startswith("NAME") and ku != "NAME1" and val and val.strip() != name:
            alternates[ku.lower()] = val.strip()
    name2 = (row.get("NAME2") or "").strip()
    if name2 and name2 != name:
        alternates["gd"] = name2  # often Gaelic/Welsh in NAME2
    return {
        "name": name,
        "lat": lat,
        "lon": lon,
        "localType": feature,
        "alternates": alternates,
        "id": row.get("ID") or row.get("FEATURE_ID") or "",
    }


def _load_open_names_points() -> list[dict[str, Any]]:
    if not OPEN_NAMES.is_file():
        return []
    points: list[dict[str, Any]] = []
    with OPEN_NAMES.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            pt = _parse_row(row)
            if pt:
                points.append(pt)
    return points


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-distance-m", type=float, default=100.0)
    ap.add_argument("--nation", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    points = _load_open_names_points()
    if not points:
        print(
            f"Missing or empty {OPEN_NAMES} — run: python3 scripts/fetch_os_open_names.py",
            file=sys.stderr,
        )
        return 1

    pending = load_unnamed(nation=args.nation)
    # OS Open Names covers GB; skip Ireland ROI for spatial join
    pending = [i for i in pending if i.get("nation") != "Ireland"]
    if args.limit:
        pending = pending[: args.limit]

    index = spatial_index(points, lat_key="lat", lon_key="lon")
    proposals: list[dict] = []
    report: dict[str, Any] = {
        "openNamesPoints": len(points),
        "pending": len(pending),
        "staged": 0,
        "adopted": [],
        "skipped": [],
    }

    print(f"OS Open Names join: {len(points):,} features × {len(pending):,} unnamed", flush=True)
    for isl in pending:
        lat, lon = isl.get("lat"), isl.get("lng") or isl.get("lon")
        if lat is None or lon is None:
            continue
        hit, dist_m = nearest_in_index(
            float(lat), float(lon), index, max_m=args.max_distance_m,
        )
        if not hit:
            report["skipped"].append({"id": isl["id"], "reason": "no match"})
            continue
        row = build_proposal(
            isl,
            proposed_name=hit["name"],
            source="os-open-names",
            licence="OGL v3.0",
            source_page_url="https://osdatahub.os.uk/downloads/open/OpenNames",
            confidence_tier="A",
            name_confidence="high",
            distance_m=dist_m,
            source_ref=str(hit.get("id") or ""),
            alternate_names=hit.get("alternates") or {},
            extra={"localType": hit.get("localType")},
        )
        if row:
            proposals.append(row)
            report["adopted"].append({"id": isl["id"], "name": hit["name"], "distanceM": dist_m})
            print(f"  staged {isl['id']} ← {hit['name']} ({dist_m:.0f} m)", flush=True)

    report["staged"] = len(proposals)
    if not args.dry_run:
        save_staging(STAGING, proposals)
        REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Staged: {len(proposals)} / {len(pending)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
