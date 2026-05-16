#!/usr/bin/env python3
"""
Backfill osmType + osmId on atlas rows that have Wikidata but no OSM id.

Reads Wikidata→OSM hits from data/cache_osm_geometries.json (populated by
compute_island_areas.py --fetch-osm, Step C).

Usage:
  python3 scripts/backfill_osm_from_wikidata.py           # dry-run
  python3 scripts/backfill_osm_from_wikidata.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ISLANDS_PATH = ROOT / "data" / "islands.json"
CACHE_PATH = ROOT / "data" / "cache_osm_geometries.json"
REPORT_PATH = ROOT / "data" / "osm_wikidata_backfill_report.json"


def _atomic_write(path: Path, payload) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def island_qid(island: dict) -> str:
    q = (island.get("wikidata") or "").strip()
    if q:
        return q if q.startswith("Q") else f"Q{q}"
    iid = island.get("id") or ""
    if iid.startswith("wd-Q"):
        return iid[3:]
    return ""


def osm_source_entry(osm_type: str, osm_id: int) -> dict:
    return {
        "name": "openstreetmap",
        "ref": f"{osm_type}/{osm_id}",
        "url": f"https://www.openstreetmap.org/{osm_type}/{osm_id}",
        "license": "ODbL",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Write islands.json")
    args = ap.parse_args()

    if not ISLANDS_PATH.exists():
        print(f"Missing {ISLANDS_PATH}", file=sys.stderr)
        return 1
    if not CACHE_PATH.exists():
        print(
            f"Missing {CACHE_PATH}. Run: python3 scripts/compute_island_areas.py --fetch-osm",
            file=sys.stderr,
        )
        return 1

    islands = json.loads(ISLANDS_PATH.read_text(encoding="utf-8"))
    cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))

    would_apply: list[dict] = []
    skipped_has_osm = 0
    skipped_no_qid = 0
    skipped_cache_miss = 0
    skipped_node_only = 0

    for isl in islands:
        if isl.get("osmId") is not None and isl.get("osmType"):
            skipped_has_osm += 1
            continue
        qid = island_qid(isl)
        if not qid:
            skipped_no_qid += 1
            continue
        entry = cache.get(f"wikidata:{qid}")
        if not entry or entry.get("missing"):
            skipped_cache_miss += 1
            continue
        kind = entry.get("kind")
        osm_id = entry.get("osmId")
        if kind not in ("way", "relation") or osm_id is None:
            if kind == "node":
                skipped_node_only += 1
            else:
                skipped_cache_miss += 1
            continue
        would_apply.append(
            {
                "id": isl.get("id"),
                "name": isl.get("name"),
                "wikidata": qid,
                "osmType": kind,
                "osmId": int(osm_id),
            }
        )

    report = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dryRun": not args.apply,
        "islandsTotal": len(islands),
        "wouldBackfill": len(would_apply),
        "skippedAlreadyHasOsm": skipped_has_osm,
        "skippedNoWikidata": skipped_no_qid,
        "skippedCacheMissOrMissing": skipped_cache_miss,
        "skippedNodeOnly": skipped_node_only,
        "sample": would_apply[:40],
    }

    print(
        f"would_backfill={len(would_apply)} "
        f"cache_miss={skipped_cache_miss} node_only={skipped_node_only} "
        f"already_has_osm={skipped_has_osm}",
        file=sys.stderr,
    )

    if args.apply and would_apply:
        by_id = {r["id"]: r for r in would_apply}
        for isl in islands:
            row = by_id.get(isl.get("id"))
            if not row:
                continue
            isl["osmType"] = row["osmType"]
            isl["osmId"] = row["osmId"]
            src = osm_source_entry(row["osmType"], row["osmId"])
            raw_sources = isl.get("sources") or []
            sources: list = []
            seen: set[tuple] = set()
            for s in raw_sources:
                if isinstance(s, dict):
                    sources.append(s)
                    seen.add((s.get("name"), s.get("ref"), s.get("url")))
            key = (src["name"], src.get("ref"), src.get("url"))
            if key not in seen:
                sources.append(src)
                isl["sources"] = sources
        _atomic_write(ISLANDS_PATH, islands)
        print(f"Wrote {ISLANDS_PATH}", file=sys.stderr)

    _atomic_write(REPORT_PATH, report)
    print(f"Report: {REPORT_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
