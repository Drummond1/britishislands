#!/usr/bin/env python3
"""Name proposals from Canmore (Scotland) and NHLE (England) site names (#46, #49).

Reuses OGL heritage MapServer queries. Accepts site titles containing island
morphemes (Island, Eilean, Holm, …) within 400 m of the unnamed polygon centroid.

Run::

    python3 scripts/name_unnamed_heritage.py --limit 150
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
STAGING = DATA / "staging" / "name_proposals" / "heritage-canmore-nhle.json"
CACHE = DATA / "cache_name_heritage.json"
REPORT = DATA / "name_proposals_heritage_report.json"
DELAY = 1.0
MAX_DISTANCE_M = 400

MORPHEME_RE = re.compile(
    r"\b(island|isle|islets?|holms?|holm|skerries|skerry|stacks?|stack|"
    r"eilean|eileanan|inis|inise|ynys|ynysod|inch|oileán|oiléan|crannog)\b",
    re.I,
)

sys.path.insert(0, str(ROOT / "scripts"))
from discovery import common as c  # noqa: E402
from enrich_images_heritage_ogl import (  # noqa: E402
    query_canmore_near,
    query_nhle_near,
)
from name_staging_utils import (  # noqa: E402
    build_proposal,
    haversine_m,
    load_unnamed,
    save_staging,
)


def _load_cache() -> dict:
    return c.load_json(CACHE, {})


def _save_cache(cache: dict) -> None:
    c.save_json(CACHE, cache)


def _extract_name(site_name: str) -> str | None:
    raw = (site_name or "").strip()
    if not raw or not MORPHEME_RE.search(raw):
        return None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    for part in parts:
        if MORPHEME_RE.search(part) and len(part) >= 4:
            return part
    return raw if len(raw) <= 80 else None


def _pick_record(
    records: list[dict],
    lat: float,
    lon: float,
) -> tuple[dict | None, float]:
    best: tuple[float, dict] | None = None
    for rec in records:
        name = _extract_name(rec.get("name") or "")
        if not name:
            continue
        rlat, rlon = rec.get("lat"), rec.get("lon")
        if rlat is not None and rlon is not None:
            d = haversine_m(lat, lon, float(rlat), float(rlon))
        else:
            d = 0.0  # Canmore prefiltered spatially; trust 400 m query radius
        if d > MAX_DISTANCE_M:
            continue
        if best is None or d < best[0]:
            best = (d, {**rec, "extractedName": name})
    if not best:
        return None, 9999.0
    return best[1], best[0]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    pending = load_unnamed()
    pending = [i for i in pending if i.get("nation") in ("Scotland", "England", "Wales", "Northern Ireland")]
    if args.limit:
        pending = pending[: args.limit]

    cache = _load_cache()
    proposals: list[dict] = []
    report: dict[str, Any] = {"pending": len(pending), "staged": 0, "adopted": [], "skipped": []}

    print(f"Heritage names: {len(pending):,} unnamed (GB)", flush=True)
    for isl in pending:
        lat = isl.get("lat")
        lon = isl.get("lng") or isl.get("lon")
        if lat is None or lon is None:
            continue
        nation = isl.get("nation") or ""
        ck = f"{isl['id']}|{nation}"
        if ck in cache:
            recs = cache[ck]
        else:
            recs = []
            if nation in ("Scotland", "Wales", "Northern Ireland"):
                recs.extend(query_canmore_near(float(lat), float(lon), distance_m=MAX_DISTANCE_M))
            if nation == "England":
                recs.extend(query_nhle_near(float(lat), float(lon), distance_m=MAX_DISTANCE_M))
            cache[ck] = recs
            _save_cache(cache)
            time.sleep(DELAY)

        pick, dist_m = _pick_record(recs, float(lat), float(lon))
        if not pick:
            report["skipped"].append({"id": isl["id"], "reason": "no island morpheme site"})
            continue

        src = pick.get("source") or "heritage-ogl"
        source_code = "canmore-sitename" if "canmore" in src else "nhle-locality"
        row = build_proposal(
            isl,
            proposed_name=pick["extractedName"],
            source=source_code,
            licence=pick.get("license") or "OGL v3.0",
            source_page_url=pick.get("pageUrl") or "https://www.trove.scot/",
            confidence_tier="A",
            name_confidence="medium-high",
            distance_m=dist_m,
            source_ref=str(pick.get("canmoreId") or pick.get("listEntry") or ""),
            extra={"heritageSiteName": pick.get("name")},
        )
        if row:
            proposals.append(row)
            report["adopted"].append({"id": isl["id"], "name": pick["extractedName"], "source": source_code})
            print(f"  staged {isl['id']} ← {pick['extractedName']} ({source_code})", flush=True)

    report["staged"] = len(proposals)
    if not args.dry_run:
        save_staging(STAGING, proposals)
        REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Staged: {len(proposals)} / {len(pending)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
