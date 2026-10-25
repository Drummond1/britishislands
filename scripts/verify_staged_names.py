#!/usr/bin/env python3
"""Verify staged name proposals against confidence tiers before merge.

Reads ``data/staging/name_proposals/*.json``, writes passing rows to
``data/staging/name_proposals-verified/``.

Run::

    python3 scripts/verify_staged_names.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
STAGING = DATA / "staging" / "name_proposals"
VERIFIED = DATA / "staging" / "name_proposals-verified"
REPORT = DATA / "staged_names_verify_report.json"

sys.path.insert(0, str(ROOT / "scripts"))
from name_staging_utils import (  # noqa: E402
    TIER_MAX_DISTANCE_M,
    is_usable_name,
    load_islands,
)

SOURCE_TIER = {
    "os-open-names": "A",
    "logainm-oil": "A",
    "osm-name-tag": "A",
    "osm-wikidata-label": "B",
    "canmore-sitename": "A",
    "nhle-locality": "A",
    "ohsome-restored": "B",
    "fusion-triangulation": "B",
    "geonames-spatial": "A",
    "osm-nearby-node": "A",
    "photo-title-consensus": "B",
    "property-adjacent": "C",
    "seal-haulout": "A",
}

SOURCE_MAX_M = {
    "os-open-names": 100,
    "logainm-oil": 500,
    "osm-name-tag": 0,
    "osm-wikidata-label": 0,
    "ohsome-restored": 0,
    "fusion-triangulation": 200,
    "canmore-sitename": 400,
    "nhle-locality": 350,
    "geonames-spatial": 150,
    "osm-nearby-node": 100,
    "photo-title-consensus": 200,
    "property-adjacent": 500,
    "seal-haulout": 150,
}


def _score(row: dict[str, Any]) -> int:
    tier = (row.get("confidenceTier") or SOURCE_TIER.get(row.get("source", ""), "C")).upper()
    conf = (row.get("nameConfidence") or "").lower()
    base = {"high": 90, "medium-high": 80, "medium": 70, "low": 50}.get(conf, 60)
    if tier == "A":
        base += 5
    elif tier == "D":
        base -= 40
    if row.get("dualSource"):
        base += 10
    dist = row.get("distanceM")
    if isinstance(dist, (int, float)):
        if dist <= 50:
            base += 5
        elif dist > 300:
            base -= 15
    return base


def _accept(row: dict[str, Any], islands_by_id: dict[str, dict]) -> tuple[bool, str]:
    iid = row.get("id") or row.get("islandId")
    if not iid:
        return False, "missing id"
    isl = islands_by_id.get(iid)
    if not isl:
        return False, "island not found"
    if isl.get("source") == "curated":
        return False, "curated island"
    if isl.get("nameStatus") != "unknown":
        return False, "already named"

    name = row.get("proposedName") or ""
    if not is_usable_name(name):
        return False, "unusable name"

    source = row.get("source") or ""
    tier = (row.get("confidenceTier") or SOURCE_TIER.get(source, "C")).upper()
    if tier == "D":
        return False, "tier D — review only"

    max_m = SOURCE_MAX_M.get(source, TIER_MAX_DISTANCE_M.get(tier, 500))
    dist = row.get("distanceM")
    if dist is not None and float(dist) > max_m:
        return False, f"distance {dist}m > {max_m}m"

    if _score(row) < 75:
        return False, "score below 75"

    if not row.get("licence") or not row.get("sourcePageUrl"):
        return False, "missing licence or source url"

    return True, "ok"


def main() -> int:
    islands_by_id = {i["id"]: i for i in load_islands()}
    VERIFIED.mkdir(parents=True, exist_ok=True)

    total_in = 0
    total_out = 0
    by_file: dict[str, dict[str, int]] = {}
    accepted_rows: list[dict] = []

    for path in sorted(STAGING.glob("*.json")):
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"skip {path.name}: {exc}", file=sys.stderr)
            continue
        if not isinstance(rows, list):
            continue

        passed: list[dict] = []
        for row in rows:
            total_in += 1
            ok, reason = _accept(row, islands_by_id)
            if ok:
                row = dict(row)
                row["verifyScore"] = _score(row)
                passed.append(row)
                total_out += 1
            else:
                row = dict(row)
                row["verifyReject"] = reason

        out_path = VERIFIED / path.name
        out_path.write_text(json.dumps(passed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        by_file[path.name] = {"raw": len(rows), "accepted": len(passed)}
        print(f"{path.name}: {len(passed)}/{len(rows)} accepted", flush=True)
        accepted_rows.extend(passed)

    report = {
        "stagingDir": str(STAGING),
        "verifiedDir": str(VERIFIED),
        "totalIn": total_in,
        "totalAccepted": total_out,
        "byFile": by_file,
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {total_out} / {total_in} → {VERIFIED}", flush=True)
    print(f"Report → {REPORT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
