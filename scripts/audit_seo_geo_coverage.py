#!/usr/bin/env python3
"""
Score named islands for SEO / GEO readiness and write actionable queues.

SEO/GEO readiness (0–100) weights what crawlers and generative engines need:
  shortDescription 40  — meta description + JSON-LD description
  photo            30  — og:image / twitter:image
  wikipedia/wd     15  — sameAs provenance
  lat/lng          10  — GeoCoordinates
  nation            5  — addressCountry hint

Outputs:
  data/seo_geo_coverage_report.json
  data/seo_geo_priority_queue.json   — ids missing description and/or photo
  data/seo_geo_score_history.jsonl   — append one summary line per run

Usage:
  python3 scripts/audit_seo_geo_coverage.py
  python3 scripts/audit_seo_geo_coverage.py --limit-queue 500
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
INDEX = DATA / "islands_index.json"
CURATED = DATA / "curated.json"
FEATURED = DATA / "featured_islands.json"
FERRIES = DATA / "ferries.json"
REPORT = DATA / "seo_geo_coverage_report.json"
QUEUE = DATA / "seo_geo_priority_queue.json"
HISTORY = DATA / "seo_geo_score_history.jsonl"


def has_photo(island: dict) -> bool:
    if island.get("images"):
        return True
    return bool(island.get("image"))


def has_description(island: dict) -> bool:
    return bool((island.get("shortDescription") or "").strip())


def has_same_as(island: dict) -> bool:
    return bool(island.get("wikipedia") or island.get("wikidata"))


def has_geo(island: dict) -> bool:
    return island.get("lat") is not None and island.get("lng") is not None


def score_island(island: dict) -> tuple[int, list[str]]:
    s = 0
    gaps: list[str] = []
    if has_description(island):
        s += 40
    else:
        gaps.append("description")
    if has_photo(island):
        s += 30
    else:
        gaps.append("photo")
    if has_same_as(island):
        s += 15
    else:
        gaps.append("sameAs")
    if has_geo(island):
        s += 10
    else:
        gaps.append("geo")
    if island.get("nation"):
        s += 5
    else:
        gaps.append("nation")
    return s, gaps


def load_named_ids() -> set[str]:
    if not INDEX.is_file():
        return set()
    data = json.loads(INDEX.read_text(encoding="utf-8"))
    rows = data.get("rows") if isinstance(data, dict) else data
    return {r["id"] for r in rows if isinstance(r, dict) and r.get("id")}


def curated_ids() -> set[str]:
    if not CURATED.is_file():
        return set()
    rows = json.loads(CURATED.read_text(encoding="utf-8"))
    return {r["id"] for r in rows if isinstance(r, dict) and r.get("id")}


def featured_ids() -> set[str]:
    if not FEATURED.is_file():
        return set()
    data = json.loads(FEATURED.read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else data.get("rows") or data.get("islands") or []
    return {r["id"] for r in rows if isinstance(r, dict) and r.get("id")}


def ferry_ids(by_id: dict[str, dict]) -> set[str]:
    if not FERRIES.is_file():
        return set()
    data = json.loads(FERRIES.read_text(encoding="utf-8"))
    out: set[str] = set()
    for route in data.get("routes") or []:
        terminals = route.get("terminals") or {}
        for key in ("from", "to"):
            iid = (terminals.get(key) or {}).get("islandId")
            if iid and iid in by_id:
                out.add(iid)
    return out


def priority_tier(iid: str, curated: set[str], featured: set[str], ferry: set[str]) -> int:
    if iid in curated:
        return 0
    if iid in featured:
        return 1
    if iid in ferry:
        return 2
    return 3


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-queue", type=int, default=800, help="Max ids in priority queue")
    args = ap.parse_args()

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    named = load_named_ids()
    curated = curated_ids()
    featured = featured_ids()
    by_id = {i["id"]: i for i in islands if i.get("id")}
    ferry = ferry_ids(by_id)

    named_rows = [i for i in islands if i.get("id") in named]
    buckets = {"100": 0, "70-99": 0, "40-69": 0, "0-39": 0}
    with_desc = with_photo = with_both = with_same = 0
    gap_counts = {"description": 0, "photo": 0, "sameAs": 0, "geo": 0, "nation": 0}
    candidates: list[tuple] = []

    for isl in named_rows:
        iid = isl["id"]
        sc, gaps = score_island(isl)
        if has_description(isl):
            with_desc += 1
        if has_photo(isl):
            with_photo += 1
        if has_description(isl) and has_photo(isl):
            with_both += 1
        if has_same_as(isl):
            with_same += 1
        for g in gaps:
            gap_counts[g] = gap_counts.get(g, 0) + 1
        if sc >= 100:
            buckets["100"] += 1
        elif sc >= 70:
            buckets["70-99"] += 1
        elif sc >= 40:
            buckets["40-69"] += 1
        else:
            buckets["0-39"] += 1

        # Queue anyone missing description or photo (the two highest-weight SEO fields).
        if "description" in gaps or "photo" in gaps:
            tier = priority_tier(iid, curated, featured, ferry)
            # Prefer islands that already have a Wikipedia URL (highest yield for descriptions).
            has_wp = 0 if isl.get("wikipedia") else 1
            has_wd = 0 if isl.get("wikidata") else 1
            area = isl.get("areaKm2")
            area_sort = -(float(area) if isinstance(area, (int, float)) else 0.0)
            candidates.append((tier, has_wp, has_wd, -sc, area_sort, iid, gaps, sc))

    candidates.sort()
    queue_rows = []
    for tier, _wp, _wd, neg_sc, _area, iid, gaps, sc in candidates[: args.limit_queue]:
        queue_rows.append(
            {
                "id": iid,
                "score": sc,
                "tier": tier,
                "gaps": gaps,
                "needDescription": "description" in gaps,
                "needPhoto": "photo" in gaps,
            }
        )

    total = len(named_rows) or 1
    avg = (
        sum(score_island(i)[0] for i in named_rows) / total if named_rows else 0.0
    )
    report = {
        "schemaVersion": 1,
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "namedTotal": len(named_rows),
        "averageScore": round(avg, 2),
        "buckets": buckets,
        "withDescription": with_desc,
        "withPhoto": with_photo,
        "withDescriptionAndPhoto": with_both,
        "withSameAs": with_same,
        "pctDescription": round(100 * with_desc / total, 1),
        "pctPhoto": round(100 * with_photo / total, 1),
        "pctBoth": round(100 * with_both / total, 1),
        "gapCounts": gap_counts,
        "queueSize": len(queue_rows),
        "targets": {
            "pctBoth": 50.0,
            "averageScore": 70.0,
            "featuredAllDescribed": True,
        },
        "featuredMissingDescription": sorted(
            iid
            for iid in featured
            if iid in by_id and not has_description(by_id[iid])
        ),
        "curatedMissingDescription": sorted(
            iid for iid in curated if iid in by_id and not has_description(by_id[iid])
        ),
    }

    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    QUEUE.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "generated": report["generated"],
                "source": "audit_seo_geo_coverage.py",
                "queue": queue_rows,
                "ids": [r["id"] for r in queue_rows],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    with HISTORY.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "at": report["generated"],
                    "namedTotal": report["namedTotal"],
                    "averageScore": report["averageScore"],
                    "pctBoth": report["pctBoth"],
                    "withDescription": with_desc,
                    "withPhoto": with_photo,
                    "queueSize": len(queue_rows),
                }
            )
            + "\n"
        )

    print(f"named={report['namedTotal']} avg_score={report['averageScore']}")
    print(
        f"desc={report['pctDescription']}% photo={report['pctPhoto']}% "
        f"both={report['pctBoth']}% sameAs={with_same}"
    )
    print(f"buckets={buckets}")
    print(f"queue={len(queue_rows)} → {QUEUE.relative_to(ROOT)}")
    print(f"report → {REPORT.relative_to(ROOT)}")
    if report["featuredMissingDescription"]:
        print(
            f"featured missing description: {len(report['featuredMissingDescription'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
