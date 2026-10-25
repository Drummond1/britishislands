#!/usr/bin/env python3
"""Name proposals from for-sale listing notes / titles (N9).

Mines ``property_listings_registry.json`` and ``property_listings_verified.json``
for island-lexicon phrases. Joins extracted names to nearby unnamed polygons
(≤500 m). Tier C — single commercial source; fusion can promote.

Run::

    python3 scripts/name_unnamed_property_adjacent.py
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
REGISTRY = DATA / "discovery" / "property_listings_registry.json"
VERIFIED = DATA / "discovery" / "property_listings_verified.json"
STAGING = DATA / "staging" / "name_proposals" / "property-adjacent.json"
REPORT = DATA / "name_proposals_property_adjacent_report.json"
MAX_M = 500.0

MORPHEME_RE = re.compile(
    r"\b([A-Z][A-Za-z'’\-]+(?:\s+[A-Z][A-Za-z'’\-]+){0,3}\s+"
    r"(?:Island|Isle|Islet|Holm|Skerry|Eilean|Inish|Ynys|Ait|Eyot)|"
    r"Eilean\s+[A-ZÀ-Ú][A-Za-zà-ú'’\-]+|"
    r"Inish[a-z]+|Ynys\s+[A-Z][A-Za-z'’\-]+)\b"
)

sys.path.insert(0, str(ROOT / "scripts"))
from discovery import common as c  # noqa: E402
from name_staging_utils import (  # noqa: E402
    build_proposal,
    island_lon,
    is_usable_name,
    load_islands,
    load_unnamed,
    nearest_in_index,
    save_staging,
    spatial_index,
)


def _extract_names(*texts: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for text in texts:
        if not text:
            continue
        for m in MORPHEME_RE.finditer(text):
            name = m.group(0).strip().rstrip(".,;")
            key = name.lower()
            if key in seen or not is_usable_name(name):
                continue
            seen.add(key)
            found.append(name)
    return found


def _collect_named_points() -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    reg = c.load_json(REGISTRY, {})
    for row in reg.get("islands") or []:
        lat, lon = row.get("lat"), row.get("lng")
        if lat is None or lon is None:
            continue
        texts = [row.get("name") or ""]
        url = ""
        for listing in row.get("listings") or []:
            texts.append(listing.get("title") or "")
            texts.append(listing.get("notes") or "")
            url = url or listing.get("url") or ""
        for name in _extract_names(*texts):
            # Skip the primary listed island name itself (already named in atlas)
            primary = (row.get("name") or "").strip().lower()
            if name.lower() == primary or name.lower() in primary:
                continue
            points.append({
                "name": name,
                "lat": float(lat),
                "lon": float(lon),
                "url": url or "https://www.findmyisland.com/",
                "fromIslandId": row.get("islandId"),
            })

    ver = c.load_json(VERIFIED, {})
    by_id = {i["id"]: i for i in load_islands()}
    for row in ver.get("verified") or []:
        iid = row.get("islandId")
        isl = by_id.get(iid) if iid else None
        if not isl:
            continue
        lat, lon = isl.get("lat"), island_lon(isl)
        if lat is None or lon is None:
            continue
        names = _extract_names(
            row.get("title") or "",
            row.get("notes") or "",
            isl.get("name") or "",
        )
        primary = (isl.get("name") or "").strip().lower()
        for name in names:
            if name.lower() == primary or name.lower() in primary:
                continue
            points.append({
                "name": name,
                "lat": float(lat),
                "lon": float(lon),
                "url": row.get("url") or "https://www.findmyisland.com/",
                "fromIslandId": iid,
            })
    return points


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-m", type=float, default=MAX_M)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    pending = load_unnamed()
    if args.limit:
        pending = pending[: args.limit]
    points = _collect_named_points()
    index = spatial_index(points, lat_key="lat", lon_key="lon", cell=0.05)

    # Also index unnamed for reverse: named listing island near unnamed
    named_atlas = [
        {
            "name": i.get("name"),
            "lat": i.get("lat"),
            "lon": island_lon(i),
            "url": "https://www.findmyisland.com/",
            "id": i.get("id"),
        }
        for i in load_islands()
        if i.get("nameStatus") != "unknown"
        and i.get("lat") is not None
        and island_lon(i) is not None
        and is_usable_name(i.get("name") or "")
    ]
    # Property-listed islands only (stronger signal for adjacent skerries)
    listed_ids = {
        row.get("islandId")
        for row in (c.load_json(REGISTRY, {}).get("islands") or [])
        if row.get("islandId")
    }
    listed_points = [p for p in named_atlas if p.get("id") in listed_ids]
    listed_index = spatial_index(listed_points, lat_key="lat", lon_key="lon", cell=0.05)

    proposals: list[dict] = []
    report: dict[str, Any] = {
        "script": "name_unnamed_property_adjacent.py",
        "extractedPoints": len(points),
        "listedIslands": len(listed_points),
        "pending": len(pending),
        "staged": 0,
        "adopted": [],
    }

    print(
        f"Property adjacent: {len(points)} extracted names, "
        f"{len(listed_points)} listed islands × {len(pending)} unnamed",
        flush=True,
    )

    seen: set[str] = set()
    for isl in pending:
        lat = isl.get("lat")
        lon = island_lon(isl)
        if lat is None or lon is None:
            continue
        # Prefer explicit adjacent names from listing text
        hit, dist = nearest_in_index(
            float(lat), float(lon), index, max_m=args.max_m, cell=0.05
        )
        if not hit:
            # Fallback: do not propose the listed island's own name onto neighbour
            continue
        key = f"{isl.get('id')}|{hit['name'].lower()}"
        if key in seen:
            continue
        seen.add(key)
        prop = build_proposal(
            isl,
            proposed_name=hit["name"],
            source="property-adjacent",
            licence="reference-fair-use",
            source_page_url=hit.get("url") or "https://www.findmyisland.com/",
            confidence_tier="C",
            name_confidence="medium",
            distance_m=dist,
            source_ref=f"property:{hit.get('fromIslandId') or ''}",
            inference_method="property-listing-adjacent-name",
        )
        if prop:
            proposals.append(prop)
            report["adopted"].append({
                "id": isl.get("id"),
                "name": hit["name"],
                "distanceM": round(dist, 1),
            })

    # Silence unused for lint clarity
    _ = listed_index

    report["staged"] = len(proposals)
    if not args.dry_run:
        save_staging(STAGING, proposals)
        c.save_json(REPORT, report)
    print(f"Staged {len(proposals):,} property-adjacent proposals → {STAGING}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
