#!/usr/bin/env python3
"""Recover deleted OSM ``name`` tags via OSM element version history (#3).

Uses the public OSM API ``/way/{id}/history`` (and relation) to find the newest
historic version that carried ``name=`` when the current object is unnamed.

Run::

    python3 scripts/name_unnamed_ohsome.py --limit 100
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
STAGING = DATA / "staging" / "name_proposals" / "ohsome-restored.json"
CACHE = DATA / "cache_name_osm_history.json"
REPORT = DATA / "name_proposals_ohsome_report.json"
OSM_API = "https://api.openstreetmap.org/api/0.6"
USER_AGENT = "isles-of-britain/0.1 (name-osm-history; contact@findmyisland.com)"
DELAY = 1.2

sys.path.insert(0, str(ROOT / "scripts"))
from discovery import common as c  # noqa: E402
from name_staging_utils import (  # noqa: E402
    build_proposal,
    load_unnamed,
    pick_english_name,
    save_staging,
)

NAME_KEYS = ("name", "name:en", "official_name", "loc_name", "alt_name")


def _load_cache() -> dict:
    return c.load_json(CACHE, {})


def _save_cache(cache: dict) -> None:
    c.save_json(CACHE, cache)


def _fetch_history(osm_type: str, osm_id: int) -> list[dict[str, Any]]:
    url = f"{OSM_API}/{osm_type}/{osm_id}/history"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=90) as resp:
        root = ET.fromstring(resp.read())
    versions: list[dict[str, Any]] = []
    for el in root.findall(osm_type):
        tags = {t.get("k"): t.get("v") for t in el.findall("tag")}
        try:
            ver = int(el.get("version") or 0)
        except ValueError:
            ver = 0
        versions.append({"version": ver, "tags": tags})
    return versions


def _best_historic_name(versions: list[dict]) -> tuple[str, dict[str, str], int] | None:
    for row in sorted(versions, key=lambda x: x.get("version") or 0, reverse=True):
        tags = row.get("tags") or {}
        if not any((tags.get(k) or "").strip() for k in NAME_KEYS):
            continue
        english, alts = pick_english_name(tags)
        if english:
            return english, alts, int(row.get("version") or 0)
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=150)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    pending = load_unnamed()
    pending = [i for i in pending if i.get("osmType") and i.get("osmId") is not None]
    if args.limit:
        pending = pending[: args.limit]

    cache = _load_cache()
    proposals: list[dict] = []
    report: dict[str, Any] = {"pending": len(pending), "staged": 0, "adopted": [], "skipped": []}

    print(f"OSM version history: {len(pending):,} unnamed islands", flush=True)
    for isl in pending:
        osm_type = isl.get("osmType") or "way"
        osm_id = int(isl["osmId"])
        ck = f"{osm_type}/{osm_id}"
        if ck in cache:
            versions = cache[ck]
        else:
            try:
                versions = _fetch_history(osm_type, osm_id)
                cache[ck] = versions
                _save_cache(cache)
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ET.ParseError) as exc:
                report["skipped"].append({"id": isl["id"], "reason": str(exc)})
                time.sleep(DELAY)
                continue
            time.sleep(DELAY)

        pick = _best_historic_name(versions)
        if not pick:
            report["skipped"].append({"id": isl["id"], "reason": "no historic name"})
            continue
        english, alts, ver = pick
        row = build_proposal(
            isl,
            proposed_name=english,
            source="ohsome-restored",
            licence="ODbL",
            source_page_url=f"https://www.openstreetmap.org/{osm_type}/{osm_id}",
            confidence_tier="B",
            name_confidence="medium-high",
            distance_m=0.0,
            source_ref=f"osm-v{ver}",
            alternate_names=alts,
            inference_method="osm-api-version-history",
            extra={"osmVersion": ver},
        )
        if row:
            proposals.append(row)
            report["adopted"].append({"id": isl["id"], "name": english, "version": ver})
            print(f"  staged {isl['id']} ← {english} (v{ver})", flush=True)

    report["staged"] = len(proposals)
    if not args.dry_run:
        save_staging(STAGING, proposals)
        REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Staged: {len(proposals)} / {len(pending)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
