#!/usr/bin/env python3
"""
Landmass survey ledger — reconcile atlas + discovery artifacts into one table.

Reads:
  - data/islands.json
  - data/discovery/verification.json (preferred) or enrichment.json
  - data/discovery/review_report.json (optional, for last apply counts)
  - data/discovery/candidates_scan.json (optional, for scan stats)

Writes:
  - data/survey/landmass_ledger.json
  - data/survey/survey_summary.json

Does not call Overpass by default; run map_scanner / full discovery first if stale.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DISC = DATA / "discovery"
SURVEY = DATA / "survey"

sys.path.insert(0, str(ROOT / "scripts"))
from discovery import common as c  # noqa: E402


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _name_confidence_atlas(row: dict) -> str:
    cl = row.get("classification") or {}
    conf = (cl.get("confidence") or "").lower()
    if conf == "unconfirmed":
        return "unconfirmed"
    if row.get("source") == "curated":
        return "high"
    if row.get("wikidata"):
        return "high" if conf == "high" else "medium"
    if row.get("osmType") and row.get("osmId") is not None and (row.get("name") or "").strip():
        return "medium"
    if (row.get("name") or "").strip():
        return "low"
    return "none"


def _ledger_row_from_island(isl: dict) -> dict[str, Any]:
    conf = _name_confidence_atlas(isl)
    sources: list[str] = []
    if isl.get("wikipedia"):
        sources.append(isl["wikipedia"])
    if isl.get("wikidata"):
        sources.append(f"https://www.wikidata.org/wiki/{isl['wikidata']}")
    if isl.get("osmType") and isl.get("osmId") is not None:
        sources.append(f"https://www.openstreetmap.org/{isl['osmType']}/{isl['osmId']}")
    return {
        "candidateId": f"atlas-{isl['id']}",
        "kind": "in_atlas",
        "islandId": isl["id"],
        "name": isl.get("name") or "",
        "lat": isl.get("lat"),
        "lng": isl.get("lng"),
        "nation": isl.get("nation"),
        "nameConfidence": conf,
        "nameSources": sources[:12],
        "mergedToAtlas": True,
        "outstandingReason": None,
        "featureKind": isl.get("osmPlace") or isl.get("type"),
        "classificationSource": (isl.get("classification") or {}).get("source"),
    }


def _ledger_row_pipeline_candidate(rec: dict, match: dict | None) -> dict[str, Any]:
    disc0 = rec.get("discovery") or {}
    vc = (
        rec.get("verificationConfidence")
        or disc0.get("verificationConfidence")
        or rec.get("scanConfidence")
        or disc0.get("scanConfidence")
        or "low"
    ).lower()
    if vc == "high":
        nconf = "high"
    elif vc == "medium":
        nconf = "medium"
    else:
        nconf = "low"
    sources = [s.get("url") for s in (rec.get("sources") or []) if s.get("url")]
    hints = [s.get("url") for s in (rec.get("sourceHints") or []) if s.get("url")]
    for u in hints:
        if u not in sources:
            sources.append(u)
    if rec.get("wikipedia") and rec["wikipedia"] not in sources:
        sources.insert(0, rec["wikipedia"])
    if rec.get("wikidata"):
        wd = f"https://www.wikidata.org/wiki/{rec['wikidata']}"
        if wd not in sources:
            sources.insert(0, wd)

    disc = rec.get("discovery") or {}
    cid = (
        rec.get("candidateId")
        or disc.get("candidateId")
        or rec.get("id")
        or ""
    )
    if match:
        return {
            "candidateId": cid,
            "kind": "pipeline_matched_atlas",
            "islandId": match["id"],
            "name": rec.get("name") or match.get("name"),
            "lat": rec.get("lat"),
            "lng": rec.get("lng"),
            "nation": rec.get("nation") or match.get("nation"),
            "nameConfidence": nconf,
            "nameSources": sources[:12],
            "mergedToAtlas": True,
            "outstandingReason": None,
            "featureKind": rec.get("featureKind") or rec.get("osmPlace"),
            "atlasNameConfidence": _name_confidence_atlas(match),
        }

    return {
        "candidateId": cid,
        "kind": "outstanding_not_in_atlas",
        "islandId": None,
        "name": rec.get("name") or "",
        "lat": rec.get("lat"),
        "lng": rec.get("lng"),
        "nation": rec.get("nation"),
        "nameConfidence": nconf,
        "nameSources": sources[:12],
        "mergedToAtlas": False,
        "outstandingReason": "no strict atlas match — run site_update --include-uncertain --apply or widen OSM/name index",
        "featureKind": rec.get("featureKind") or rec.get("osmPlace"),
    }


def run(*, from_enrichment: bool = False) -> dict[str, Any]:
    SURVEY.mkdir(parents=True, exist_ok=True)
    islands = c.load_islands()
    index = c.build_island_index(islands)

    atlas_rows = [_ledger_row_from_island(isl) for isl in islands]
    by_conf: dict[str, int] = {}
    for r in atlas_rows:
        by_conf[r["nameConfidence"]] = by_conf.get(r["nameConfidence"], 0) + 1

    path_ver = DISC / "verification.json"
    path_enr = DISC / "enrichment.json"
    candidates: list[dict] = []
    source_file = ""
    if from_enrichment and path_enr.exists():
        doc = c.load_json(path_enr, {})
        candidates = list(doc.get("records") or [])
        source_file = str(path_enr.relative_to(ROOT))
    elif path_ver.exists():
        doc = c.load_json(path_ver, {})
        candidates = [r for r in (doc.get("records") or []) if r.get("verified")]
        source_file = str(path_ver.relative_to(ROOT))
    else:
        source_file = "(none)"

    pipeline_rows: list[dict] = []
    outstanding: list[dict] = []
    matched_pipeline = 0
    for rec in candidates:
        key = {
            "name": rec.get("name"),
            "lat": rec.get("lat"),
            "lng": rec.get("lng"),
            "wikidata": rec.get("wikidata"),
            "osmType": rec.get("osmType"),
            "osmId": rec.get("osmId"),
        }
        match = c.find_existing_match(key, index, loose=False)
        row = _ledger_row_pipeline_candidate(rec, match)
        pipeline_rows.append(row)
        if row["kind"] == "outstanding_not_in_atlas":
            outstanding.append(row)
        else:
            matched_pipeline += 1

    scan_unnamed = 0
    scan_missing = 0
    scan_path = DISC / "candidates_scan.json"
    if scan_path.exists():
        scan = c.load_json(scan_path, {})
        scan_unnamed = int(scan.get("unnamedOrUnlocated") or 0)
        scan_missing = int(scan.get("missingCandidates") or 0)

    review = c.load_json(DISC / "review_report.json", {})
    review_counts = review.get("counts") or {}

    summary = {
        "generatedAt": _iso_now(),
        "remit": {"bbox": list(c.UK_BBOX), "note": "in_remit per discovery.common"},
        "atlasIslandCount": len(islands),
        "atlasNameConfidenceBreakdown": by_conf,
        "pipelineSourceFile": source_file,
        "pipelineCandidates": len(candidates),
        "pipelineMatchedAtlas": matched_pipeline,
        "outstandingNotInAtlas": len(outstanding),
        "scanReportUnnamedOrUnlocated": scan_unnamed,
        "scanReportMissingCandidates": scan_missing,
        "lastReviewReportCounts": review_counts,
        "closureHints": {
            "added": review_counts.get("added"),
            "merged": review_counts.get("merged"),
            "skippedUncertain": review_counts.get("skippedUncertain"),
        },
    }

    ledger_doc = {
        "schemaVersion": 1,
        "generatedAt": summary["generatedAt"],
        "summary": summary,
        "atlasRows": atlas_rows,
        "pipelineRows": pipeline_rows,
        "outstandingRows": outstanding,
    }

    (SURVEY / "landmass_ledger.json").write_text(
        json.dumps(ledger_doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (SURVEY / "survey_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2), file=sys.stderr)
    print(f"→ Wrote {SURVEY / 'landmass_ledger.json'}", file=sys.stderr)
    print(f"→ Wrote {SURVEY / 'survey_summary.json'}", file=sys.stderr)
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Build landmass survey ledger from atlas + discovery.")
    ap.add_argument(
        "--from-enrichment",
        action="store_true",
        help="Use enrichment.json rows instead of verification.json",
    )
    args = ap.parse_args()
    run(from_enrichment=args.from_enrichment)


if __name__ == "__main__":
    main()
