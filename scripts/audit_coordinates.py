#!/usr/bin/env python3
"""Sanity-check every island's coordinates.

Flags any record where:

  * ``lat`` / ``lng`` is missing, non-numeric, or NaN.
  * The point is outside the project's UK + Ireland + Crown Dependency
    bounding box (the 50-mile envelope used elsewhere).
  * Two records share *identical* coords (often a sign of a stub being
    geocoded to a parent island).

Output is a JSON report; nothing is mutated.

Usage::

    python3 scripts/audit_coordinates.py

Output::

    data/coordinate_audit_report.json
"""

from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
REPORT = DATA / "coordinate_audit_report.json"

# Generous British-Isles bounding box (incl. Rockall, Channel Is., Shetland).
LAT_MIN, LAT_MAX = 49.0, 61.5
LNG_MIN, LNG_MAX = -14.0, 2.5


def main():
    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    report = {
        "totalIslands": len(islands),
        "missingOrInvalid": [],
        "outsideBbox": [],
        "exactCoordCollisions": [],
    }
    coord_index: dict[tuple[float, float], list[dict]] = {}
    for isl in islands:
        if not isinstance(isl, dict):
            continue
        lat, lng = isl.get("lat"), isl.get("lng")
        ref = {"id": isl.get("id"), "name": isl.get("name"),
               "nation": isl.get("nation"), "type": isl.get("type")}
        if (not isinstance(lat, (int, float))
                or not isinstance(lng, (int, float))
                or isinstance(lat, bool) or isinstance(lng, bool)):
            report["missingOrInvalid"].append({**ref, "lat": lat, "lng": lng,
                                               "reason": "missing or non-numeric"})
            continue
        if math.isnan(lat) or math.isnan(lng):
            report["missingOrInvalid"].append({**ref, "lat": lat, "lng": lng,
                                               "reason": "NaN"})
            continue
        if not (LAT_MIN <= lat <= LAT_MAX and LNG_MIN <= lng <= LNG_MAX):
            report["outsideBbox"].append({**ref, "lat": lat, "lng": lng})
            continue
        key = (round(lat, 5), round(lng, 5))  # ~1 m tolerance
        coord_index.setdefault(key, []).append(ref)

    for key, recs in coord_index.items():
        if len(recs) > 1:
            report["exactCoordCollisions"].append({"lat": key[0], "lng": key[1],
                                                   "records": recs})
    report["exactCoordCollisions"].sort(key=lambda c: -len(c["records"]))
    report["counts"] = {
        "missingOrInvalid": len(report["missingOrInvalid"]),
        "outsideBbox": len(report["outsideBbox"]),
        "collisionGroups": len(report["exactCoordCollisions"]),
        "collisionRecords": sum(len(c["records"]) for c in report["exactCoordCollisions"]),
    }
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report["counts"], indent=2))
    print(f"report → {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
