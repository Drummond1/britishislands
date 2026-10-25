#!/usr/bin/env python3
"""Lead photos via Geograph Britain & Ireland native syndicator API.

Uses ``api.geograph.org.uk/syndicator.php`` by OS/Irish grid reference (not
the Commons export path). CC-BY-SA 2.0 per photo; dual-signal name + geo gate.

Run::

    python3 scripts/enrich_images_geograph_native.py --named-only --limit 200
    python3 scripts/enrich_images_geograph_native.py --dry-run --test isle-of-skye
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
STAGING = DATA / "staging" / "adoptions" / "geograph-native.json"
CACHE = DATA / "cache_geograph_native.json"
REPORT = DATA / "image_enrichment_geograph_native_report.json"

SYNDICATOR = "https://api.geograph.org.uk/syndicator.php"
USER_AGENT = "isles-of-britain/0.1 (geograph-native; https://www.findmyisland.com)"
DEFAULT_DELAY = 1.0
MAX_DISTANCE_KM = 2.0
PER_PAGE = 25
LICENCE = "CC-BY-SA 2.0"
SOURCE = "geograph-native"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from enrich_images_v5 import (  # noqa: E402
    _load,
    _load_named_index_ids,
    _mentions,
    _name_variants,
    _save,
)
from photo_geo_utils import grid_ref_for_island, haversine_km  # noqa: E402
from photo_staging_dual import dual_signal_ok, save_staging  # noqa: E402

_THUMB_RE = re.compile(r"/photos/\d+/(\d+)/(\d+)_", re.I)


def _fetch_syndicator(grid: str, perpage: int = PER_PAGE) -> dict:
    qs = urllib.parse.urlencode({
        "format": "JSON",
        "location": grid,
        "perpage": str(perpage),
    })
    req = urllib.request.Request(
        f"{SYNDICATOR}?{qs}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def _full_image_url(thumb: str, photo_id: str) -> str:
    if thumb:
        m = _THUMB_RE.search(thumb)
        if m:
            folder, pid = m.group(1), m.group(2)
            return f"https://s1.geograph.org.uk/photos/{folder}/{pid}/{pid}.jpg"
    return f"https://www.geograph.org.uk/photo/{photo_id}"


def _pick_best_item(
    island: dict,
    items: list[dict],
) -> tuple[dict | None, dict[str, Any]]:
    lat0 = island.get("lat")
    lon0 = island.get("lng") or island.get("lon")
    if lat0 is None or lon0 is None:
        return None, {"reason": "island missing coords"}
    variants = _name_variants(island)
    best: tuple[float, dict, dict] | None = None
    for it in items:
        title = (it.get("title") or "").split(":", 1)[-1].strip()
        blob = f"{title} {(it.get('description') or '')} {(it.get('category') or '')}"
        try:
            plat = float(it.get("lat") or 0)
            plon = float(it.get("long") or it.get("lon") or 0)
        except (TypeError, ValueError):
            continue
        ok, ver = dual_signal_ok(
            island,
            title=title,
            blob=blob,
            result_lat=plat,
            result_lon=plon,
            mentions_fn=_mentions,
            name_variants_fn=lambda _: variants,
            haversine_km_fn=haversine_km,
        )
        if not ok:
            continue
        dist = haversine_km(float(lat0), float(lon0), plat, plon)
        if dist > MAX_DISTANCE_KM:
            continue
        score = dist
        if best is None or score < best[0]:
            best = (score, it, ver)
    if not best:
        return None, {"reason": "no dual-signal match in feed"}
    return best[1], best[2]


def _image_record(island: dict, item: dict, ver: dict) -> dict[str, Any]:
    pid = str(item.get("guid") or "")
    thumb = item.get("thumb") or ""
    title = (item.get("title") or island.get("name") or "Island").strip()
    url = _full_image_url(thumb, pid)
    author = (item.get("author") or "Geograph contributor").strip()
    page = item.get("link") or f"https://www.geograph.org.uk/photo/{pid}"
    return {
        "url": url,
        "source": SOURCE,
        "sourceRef": pid,
        "sourcePageUrl": page,
        "license": LICENCE,
        "attribution": f"{title} / {author} / Geograph (CC-BY-SA 2.0)",
        "imageConfidence": "high",
        "verifiedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "geographDistanceKm": ver.get("distanceKm"),
        "dualSignal": True,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--named-only", action="store_true", default=True)
    ap.add_argument("--limit", type=int, default=300)
    ap.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--test", default="")
    args = ap.parse_args()

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    named_ids = _load_named_index_ids() if args.named_only else set()
    pending = [i for i in islands if not (i.get("images") or [])]
    if args.named_only:
        pending = [i for i in pending if i.get("id") in named_ids]
    if args.test:
        pending = [i for i in islands if i.get("id") == args.test]
    if args.limit:
        pending = pending[: args.limit]

    cache = _load(CACHE)
    adoptions: list[dict] = []
    report: dict[str, Any] = {
        "script": "enrich_images_geograph_native.py",
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "pending": len(pending),
        "staged": 0,
        "adopted": [],
        "skipped": [],
    }

    print(f"Geograph native: {len(pending):,} islands to try", flush=True)
    for isl in pending:
        iid = isl.get("id", "")
        lat = isl.get("lat")
        lon = isl.get("lng") or isl.get("lon")
        if lat is None or lon is None:
            report["skipped"].append({"id": iid, "reason": "no coords"})
            continue
        grid = grid_ref_for_island(float(lat), float(lon), isl.get("nation", ""), digits=6)
        if not grid:
            report["skipped"].append({"id": iid, "reason": "grid ref failed"})
            continue
        ck = f"{grid}|{PER_PAGE}"
        if not args.refresh and ck in cache:
            payload = cache[ck]
        else:
            try:
                payload = _fetch_syndicator(grid, PER_PAGE)
                cache[ck] = payload
                _save(CACHE, cache)
            except Exception as exc:
                report["skipped"].append({"id": iid, "grid": grid, "reason": str(exc)})
                time.sleep(args.delay)
                continue
            time.sleep(args.delay)

        items = payload.get("items") or []
        pick, ver = _pick_best_item(isl, items)
        if not pick:
            report["skipped"].append({"id": iid, "grid": grid, "reason": ver.get("reason")})
            continue
        rec = _image_record(isl, pick, ver)
        row = {
            "id": iid,
            "islandId": iid,
            "name": isl.get("name"),
            "image_record": rec,
            "imageConfidence": "high",
            "dualSignal": True,
            "gridRef": grid,
            "geographId": pick.get("guid"),
        }
        adoptions.append(row)
        report["adopted"].append({"id": iid, "grid": grid, "geographId": pick.get("guid")})
        print(f"  staged {iid} ← geograph {pick.get('guid')}", flush=True)

    report["staged"] = len(adoptions)
    if not args.dry_run:
        save_staging(STAGING, adoptions)
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Staged: {len(adoptions)} / {len(pending)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
