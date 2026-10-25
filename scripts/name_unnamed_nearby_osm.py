#!/usr/bin/env python3
"""Name unnamed islands from nearby OSM named nodes (N8 orphan nodes).

Batches Overpass lookups for ``node(around:RADIUS)["name"]`` near unnamed
centroids. Accepts names with island-lexicon morphemes (or short local names
when ``place=island|islet`` / ``natural=rock``).

Run::

    python3 scripts/name_unnamed_nearby_osm.py --limit 200
    python3 scripts/name_unnamed_nearby_osm.py --limit 500 --radius-m 100
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
STAGING = DATA / "staging" / "name_proposals" / "osm-nearby-nodes.json"
CACHE = DATA / "cache_name_nearby_osm.json"
REPORT = DATA / "name_proposals_osm_nearby_report.json"
BATCH = 25
DELAY = 1.2

MORPHEME_RE = re.compile(
    r"\b(island|isle|islets?|holms?|holm|skerries|skerry|stacks?|stack|"
    r"eilean|eileanan|inis|inish|ynys|inch|oile[aá]n|crannog|ait|eyot)\b",
    re.I,
)

sys.path.insert(0, str(ROOT / "scripts"))
from discovery import common as c  # noqa: E402
from name_staging_utils import (  # noqa: E402
    build_proposal,
    haversine_m,
    island_lon,
    is_usable_name,
    load_unnamed,
    save_staging,
)


def _accept_node(tags: dict, name: str) -> bool:
    if not is_usable_name(name):
        return False
    place = (tags.get("place") or "").lower()
    natural = (tags.get("natural") or "").lower()
    if place in {"island", "islet", "archipelago"} or natural in {"rock", "stone", "reef"}:
        return True
    if MORPHEME_RE.search(name):
        return True
    return False


def _overpass_around(batch: list[dict], radius_m: float) -> list[dict]:
    parts = []
    for isl in batch:
        lat, lon = isl["lat"], island_lon(isl)
        parts.append(
            f'  node(around:{int(radius_m)},{lat},{lon})["name"];'
        )
    query = (
        "[out:json][timeout:120];\n(\n"
        + "\n".join(parts)
        + "\n);\nout tags center;"
    )
    payload = c.post_overpass(query)
    return list(payload.get("elements") or [])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=300)
    ap.add_argument("--radius-m", type=float, default=100.0)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--nation", default="")
    args = ap.parse_args()

    pending = load_unnamed(nation=args.nation)
    pending = pending[args.offset :]
    if args.limit:
        pending = pending[: args.limit]

    cache = c.load_json(CACHE, {})
    proposals: list[dict] = []
    report: dict[str, Any] = {
        "script": "name_unnamed_nearby_osm.py",
        "pending": len(pending),
        "offset": args.offset,
        "staged": 0,
        "adopted": [],
        "skipped": [],
    }

    print(
        f"OSM nearby nodes: {len(pending):,} unnamed (offset {args.offset}, "
        f"r={args.radius_m}m)",
        flush=True,
    )

    for i in range(0, len(pending), BATCH):
        batch = pending[i : i + BATCH]
        to_fetch = []
        for isl in batch:
            cid = isl.get("id") or ""
            if cid in cache and not args.dry_run:
                continue
            to_fetch.append(isl)

        elements: list[dict] = []
        if to_fetch:
            try:
                elements = _overpass_around(to_fetch, args.radius_m)
            except Exception as exc:  # noqa: BLE001
                print(f"  Overpass error: {exc}", flush=True)
                time.sleep(20)
                continue
            time.sleep(DELAY)

        # Assign nearest acceptable node to each island in batch
        for isl in batch:
            lat = float(isl["lat"])
            lon = float(island_lon(isl))
            cid = isl.get("id") or ""
            best: tuple[float, dict, str] | None = None
            for el in elements:
                tags = el.get("tags") or {}
                name = (tags.get("name") or "").strip()
                if not _accept_node(tags, name):
                    continue
                elat = el.get("lat")
                elon = el.get("lon")
                if elat is None or elon is None:
                    center = el.get("center") or {}
                    elat, elon = center.get("lat"), center.get("lon")
                if elat is None or elon is None:
                    continue
                d = haversine_m(lat, lon, float(elat), float(elon))
                if d > args.radius_m:
                    continue
                if best is None or d < best[0]:
                    best = (d, el, name)

            cache[cid] = {
                "name": best[2] if best else None,
                "distanceM": round(best[0], 1) if best else None,
                "osmId": best[1].get("id") if best else None,
            }

            if not best:
                report["skipped"].append({"id": cid, "reason": "no-node"})
                continue
            dist, el, name = best
            prop = build_proposal(
                isl,
                proposed_name=name,
                source="osm-nearby-node",
                licence="ODbL",
                source_page_url=f"https://www.openstreetmap.org/node/{el.get('id')}",
                confidence_tier="A",
                name_confidence="high" if dist <= 50 else "medium-high",
                distance_m=dist,
                source_ref=f"osm-node-{el.get('id')}",
                inference_method="osm-orphan-named-node",
                extra={"nodeTags": el.get("tags") or {}},
            )
            if prop:
                proposals.append(prop)
                report["adopted"].append({
                    "id": cid,
                    "name": name,
                    "distanceM": round(dist, 1),
                    "osmId": el.get("id"),
                })

        print(
            f"  batch {i // BATCH + 1}: staged so far {len(proposals)}",
            flush=True,
        )
        if not args.dry_run:
            c.save_json(CACHE, cache)

    report["staged"] = len(proposals)
    if not args.dry_run:
        # Merge with any prior staging for this source (offset runs)
        prior = c.load_json(STAGING, [])
        by_id = {r.get("id"): r for r in prior if isinstance(r, dict)}
        for p in proposals:
            by_id[p["id"]] = p
        save_staging(STAGING, list(by_id.values()))
        c.save_json(REPORT, report)
    print(f"Staged {len(proposals):,} OSM-nearby proposals (file merged)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
