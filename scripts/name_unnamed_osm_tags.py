#!/usr/bin/env python3
"""Name proposals from OSM tags on unnamed island polygons (#1, #2, #6 partial).

Harvests ``wikidata=``, ``name:*``, ``official_name``, ``alt_name``, ``loc_name``
from the same OSM way/relation as each ``nameStatus=unknown`` island. Wikidata
labels fetched when ``wikidata=`` present but no name tag.

Run::

    python3 scripts/name_unnamed_osm_tags.py
    python3 scripts/name_unnamed_osm_tags.py --limit 200 --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
STAGING = DATA / "staging" / "name_proposals" / "osm-tags.json"
CACHE = DATA / "cache_name_osm_tags.json"
REPORT = DATA / "name_proposals_osm_tags_report.json"
WD_API = "https://www.wikidata.org/w/api.php"
USER_AGENT = "isles-of-britain/0.1 (name-osm-tags)"
BATCH = 80
DELAY = 0.4

sys.path.insert(0, str(ROOT / "scripts"))
from discovery import common as c  # noqa: E402
from name_staging_utils import (  # noqa: E402
    build_proposal,
    island_lon,
    load_unnamed,
    pick_english_name,
    save_staging,
)

NAME_TAG_KEYS = (
    "name", "name:en", "official_name", "alt_name", "loc_name",
    "name:gd", "name:ga", "name:cy", "name:gv", "name:kw", "wikidata",
)


def _load_cache() -> dict:
    return c.load_json(CACHE, {})


def _save_cache(cache: dict) -> None:
    c.save_json(CACHE, cache)


def _overpass_batch(elements: list[tuple[str, int]]) -> dict[int, dict]:
    if not elements:
        return {}
    parts = []
    for osm_type, osm_id in elements:
        parts.append(f"  {osm_type}({osm_id});")
    query = (
        "[out:json][timeout:180];\n(\n"
        + "\n".join(parts)
        + "\n);\nout tags center;"
    )
    payload = c.post_overpass(query)
    out: dict[int, dict] = {}
    for el in payload.get("elements") or []:
        osm_id = el.get("id")
        if osm_id is None:
            continue
        out[int(osm_id)] = {
            "tags": el.get("tags") or {},
            "center": el.get("center") or {},
        }
    return out


def _wikidata_labels(qids: list[str], cache: dict) -> dict[str, str]:
    missing = [q for q in qids if q not in cache]
    for i in range(0, len(missing), 50):
        batch = missing[i : i + 50]
        params = {
            "action": "wbgetentities",
            "ids": "|".join(batch),
            "props": "labels",
            "languages": "en",
            "format": "json",
        }
        req = urllib.request.Request(
            WD_API + "?" + urllib.parse.urlencode(params),
            headers={"User-Agent": USER_AGENT},
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                time.sleep(20)
                continue
            raise
        for qid, ent in (data.get("entities") or {}).items():
            label = ((ent.get("labels") or {}).get("en") or {}).get("value", "")
            cache[qid] = label
        time.sleep(DELAY)
    _save_cache(cache)
    return {q: cache.get(q, "") for q in qids}


def _has_name_signal(tags: dict) -> bool:
    if (tags.get("wikidata") or "").strip():
        return True
    for k in NAME_TAG_KEYS:
        if k != "wikidata" and (tags.get(k) or "").strip():
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--nation", default="")
    args = ap.parse_args()

    pending = load_unnamed(nation=args.nation)
    if args.limit:
        pending = pending[: args.limit]

    cache = _load_cache()
    proposals: list[dict] = []
    report: dict[str, Any] = {
        "script": "name_unnamed_osm_tags.py",
        "pending": len(pending),
        "staged": 0,
        "adopted": [],
        "skipped": [],
    }

    print(f"OSM name tags: {len(pending):,} unnamed islands", flush=True)
    batch_elems: list[tuple[str, int]] = []
    batch_islands: list[dict] = []

    def flush_batch() -> None:
        nonlocal batch_elems, batch_islands
        if not batch_elems:
            return
        try:
            osm_map = _overpass_batch(batch_elems)
        except Exception as exc:
            for isl in batch_islands:
                report["skipped"].append({"id": isl["id"], "reason": str(exc)})
            batch_elems, batch_islands = [], []
            time.sleep(2)
            return

        qids: list[str] = []
        for osm_id, meta in osm_map.items():
            q = (meta.get("tags") or {}).get("wikidata", "").strip()
            if q:
                qids.append(q)
        labels = _wikidata_labels(qids, cache)

        for isl in batch_islands:
            osm_id = isl.get("osmId")
            if osm_id is None:
                report["skipped"].append({"id": isl["id"], "reason": "no osmId"})
                continue
            meta = osm_map.get(int(osm_id))
            if not meta:
                report["skipped"].append({"id": isl["id"], "reason": "osm miss"})
                continue
            tags = meta.get("tags") or {}
            if not _has_name_signal(tags):
                report["skipped"].append({"id": isl["id"], "reason": "no name tags"})
                continue

            qid = (tags.get("wikidata") or "").strip()
            wd_label = labels.get(qid, "") if qid else ""
            english, alternates = pick_english_name(tags, wikidata_label=wd_label)
            if not english:
                report["skipped"].append({"id": isl["id"], "reason": "unusable name"})
                continue

            source = "osm-wikidata-label" if wd_label and english == wd_label else "osm-name-tag"
            tier = "A" if source == "osm-name-tag" else "B"
            row = build_proposal(
                isl,
                proposed_name=english,
                source=source,
                licence="ODbL",
                source_page_url=f"https://www.openstreetmap.org/{isl.get('osmType')}/{osm_id}",
                confidence_tier=tier,
                name_confidence="high" if source == "osm-name-tag" else "medium-high",
                distance_m=0.0,
                source_ref=qid or ",".join(f"{k}={tags[k]}" for k in NAME_TAG_KEYS if tags.get(k)),
                alternate_names=alternates,
                extra={"osmTags": {k: tags[k] for k in NAME_TAG_KEYS if tags.get(k)}},
            )
            if row:
                proposals.append(row)
                report["adopted"].append({"id": isl["id"], "name": english, "source": source})
                print(f"  staged {isl['id']} ← {english} ({source})", flush=True)

        batch_elems, batch_islands = [], []
        time.sleep(DELAY)

    for isl in pending:
        osm_type = isl.get("osmType") or "way"
        osm_id = isl.get("osmId")
        if osm_id is None:
            continue
        batch_elems.append((osm_type, int(osm_id)))
        batch_islands.append(isl)
        if len(batch_elems) >= BATCH:
            flush_batch()
    flush_batch()

    report["staged"] = len(proposals)
    if not args.dry_run:
        save_staging(STAGING, proposals)
        REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Staged: {len(proposals)} / {len(pending)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
