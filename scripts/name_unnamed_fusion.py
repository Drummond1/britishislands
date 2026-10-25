#!/usr/bin/env python3
"""Triangulation fusion — promote names agreed by ≥2 independent sources (#99).

Reads all ``data/staging/name_proposals/*.json`` (except fusion output), groups
by island id + normalised name; emits Tier B proposals when ≥2 distinct sources
agree within 200 m.

Run after other harvesters::

    python3 scripts/name_unnamed_fusion.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
STAGING_DIR = DATA / "staging" / "name_proposals"
OUT = STAGING_DIR / "fusion-triangulation.json"
REPORT = DATA / "name_proposals_fusion_report.json"

sys.path.insert(0, str(ROOT / "scripts"))
from name_staging_utils import (  # noqa: E402
    build_proposal,
    haversine_m,
    load_islands,
    save_staging,
)


def _norm_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "")
    s = s.encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(island|isle|islets?)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _load_proposals() -> list[dict]:
    rows: list[dict] = []
    for path in sorted(STAGING_DIR.glob("*.json")):
        if path.name == OUT.name:
            continue
        try:
            chunk = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(chunk, list):
            for row in chunk:
                row = dict(row)
                row["_file"] = path.name
                rows.append(row)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-sources", type=int, default=2)
    ap.add_argument("--max-distance-m", type=float, default=200.0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    islands_by_id = {i["id"]: i for i in load_islands()}
    proposals_in = _load_proposals()

    buckets: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for row in proposals_in:
        iid = row.get("id") or row.get("islandId")
        name = row.get("proposedName") or ""
        if not iid or not name:
            continue
        buckets[iid][_norm_name(name)].append(row)

    fused: list[dict] = []
    report: dict[str, Any] = {"inputRows": len(proposals_in), "staged": 0, "fused": []}

    for iid, by_name in buckets.items():
        isl = islands_by_id.get(iid)
        if not isl or isl.get("nameStatus") != "unknown":
            continue
        for norm, rows in by_name.items():
            sources = {r.get("source") or r["_file"] for r in rows}
            if len(sources) < args.min_sources:
                continue
            # distance coherence: all proposal distances to same point should be tight
            dists = [float(r["distanceM"]) for r in rows if r.get("distanceM") is not None]
            if len(dists) >= 2 and max(dists) - min(dists) > args.max_distance_m:
                continue
            # pick highest-confidence row as template
            rows.sort(
                key=lambda r: (
                    {"high": 4, "medium-high": 3, "medium": 2}.get(
                        (r.get("nameConfidence") or "").lower(), 1
                    ),
                    -float(r.get("distanceM") or 0),
                ),
                reverse=True,
            )
            best = rows[0]
            name = best.get("proposedName") or ""
            alts: dict[str, str] = {}
            for r in rows:
                for k, v in (r.get("alternateNames") or {}).items():
                    alts.setdefault(k, v)

            row = build_proposal(
                isl,
                proposed_name=name,
                source="fusion-triangulation",
                licence=best.get("licence") or "mixed",
                source_page_url=best.get("sourcePageUrl") or "",
                confidence_tier="B",
                name_confidence="high",
                distance_m=min(dists) if dists else best.get("distanceM"),
                source_ref="|".join(sorted(sources)),
                alternate_names=alts,
                dual_source=True,
                inference_method="multi-source-agreement",
                extra={
                    "agreeingSources": sorted(sources),
                    "agreeingCount": len(sources),
                    "contributors": [r.get("source") for r in rows],
                },
            )
            if row:
                fused.append(row)
                report["fused"].append({
                    "id": iid,
                    "name": name,
                    "sources": sorted(sources),
                })

    report["staged"] = len(fused)
    if not args.dry_run:
        save_staging(OUT, fused)
        REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Fusion staged: {len(fused)} agreements from {len(proposals_in)} input rows", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
