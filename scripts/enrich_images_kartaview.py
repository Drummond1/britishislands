#!/usr/bin/env python3
"""Lead-photo enrichment via KartaView / OpenStreetCam CC-BY-SA imagery.

Targets **named** atlas islands (``islands_index.json``) without ``images[]`` and
with ``areaKm2`` < 0.3 (strict — unknown or larger areas are skipped). Queries
``https://api.openstreetcam.org/2.0/photo/`` around each centroid and adopts only
when photo coordinates are within 200 m of the island centre. KartaView imagery is
**CC-BY-SA 4.0** (community street-level photos).

Run::

    python3 scripts/enrich_images_kartaview.py --named-only --limit 200
    python3 scripts/enrich_images_kartaview.py --dry-run --limit 20
    python3 scripts/enrich_images_kartaview.py --test isle-of-muck

Outputs (staging only — does not mutate islands.json)::

    data/staging/adoptions/kartaview.json
    data/cache_kartaview.json
    data/image_enrichment_kartaview_report.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
ISLANDS_INDEX = DATA / "islands_index.json"
STAGING = DATA / "staging" / "adoptions" / "kartaview.json"
CACHE = DATA / "cache_kartaview.json"
REPORT = DATA / "image_enrichment_kartaview_report.json"

KARTAVIEW_API = "https://api.openstreetcam.org/2.0/photo/"
USER_AGENT = (
    "isles-of-britain/0.1 (kartaview image enrichment; "
    "https://www.findmyisland.com; static-site)"
)
DEFAULT_DELAY_S = 2.0
DEFAULT_MAX_DISTANCE_M = 200.0
DEFAULT_MAX_AREA_KM2 = 0.3
API_RADIUS_M = 250
API_TIMEOUT_S = 35
LICENSE = "CC-BY-SA-4.0"
CONFIDENCE = "medium"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from enrich_images_v5 import _load, _load_named_index_ids, _open, _save  # noqa: E402


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _island_lon(island: dict) -> float | None:
    lng = island.get("lng")
    if lng is None:
        lng = island.get("lon")
    if isinstance(lng, (int, float)):
        return float(lng)
    return None


def _eligible_area(island: dict, max_area_km2: float) -> tuple[bool, str]:
    area = island.get("areaKm2")
    if area is None:
        return False, "areaKm2 unknown"
    try:
        if float(area) < float(max_area_km2):
            return True, f"areaKm2={area} < {max_area_km2}"
    except (TypeError, ValueError):
        return False, "invalid areaKm2"
    return False, f"areaKm2={area} >= {max_area_km2}"


def _photo_coords(photo: dict) -> tuple[float, float] | None:
    for lat_key, lon_key in (("lat", "lng"), ("matchLat", "matchLng")):
        lat = photo.get(lat_key)
        lon = photo.get(lon_key)
        if lat is None or lon is None:
            continue
        try:
            return float(lat), float(lon)
        except (TypeError, ValueError):
            continue
    return None


def _photo_url(photo: dict) -> str:
    for key in ("imageProcUrl", "imageLthUrl", "imageThUrl", "fileurlProc", "fileurl"):
        url = (photo.get(key) or "").strip()
        if url and "{{" not in url:
            return url
    return ""


def _kartaview_page_url(photo: dict) -> str:
    seq = str(photo.get("sequenceId") or "").strip()
    idx = str(photo.get("sequenceIndex") or "0").strip()
    if seq:
        return f"https://kartaview.org/details/{seq}/{idx}"
    photo_id = str(photo.get("id") or "").strip()
    if photo_id:
        return f"https://kartaview.org/photo/{photo_id}"
    return "https://kartaview.org/"


def build_image_record(photo: dict, island: dict, distance_m: float) -> dict | None:
    url = _photo_url(photo)
    if not url:
        return None

    photo_id = str(photo.get("id") or "").strip()
    if not photo_id:
        return None

    caption_bits = ["KartaView street-level photo"]
    if photo.get("shotDate"):
        caption_bits.append(f"captured {photo['shotDate']}")
    if photo.get("heading") is not None:
        caption_bits.append(f"heading {photo['heading']}°")
    caption_bits.append(f"{distance_m:.0f} m from island centroid")

    return {
        "url": url,
        "source": "kartaview",
        "sourceRef": photo_id,
        "sourcePageUrl": _kartaview_page_url(photo),
        "license": LICENSE,
        "attribution": "© KartaView contributors, CC BY-SA 4.0",
        "caption": "; ".join(caption_bits),
        "primary": True,
        "imageConfidence": CONFIDENCE,
        "verifiedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "kartaviewDistanceM": round(distance_m, 1),
        "islandId": island.get("id"),
    }


def fetch_photos_near(
    lat: float,
    lon: float,
    cache: dict[str, Any],
    *,
    island_id: str,
    refresh: bool,
    delay_s: float,
) -> list[dict]:
    cache_key = island_id or f"{lat:.5f},{lon:.5f}"
    if not refresh and cache_key in cache:
        entry = cache[cache_key]
        if isinstance(entry, dict) and isinstance(entry.get("data"), list):
            return entry["data"]

    params = {
        "lat": lat,
        "lng": lon,
        "radius": API_RADIUS_M,
    }
    qs = urlencode(params)
    req_url = f"{KARTAVIEW_API}?{qs}"
    try:
        import urllib.request

        req = urllib.request.Request(
            req_url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        raw = _open(req, timeout=API_TIMEOUT_S)
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        cache[cache_key] = {
            "params": params,
            "error": repr(exc),
            "fetched": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "data": [],
        }
        _save(CACHE, cache)
        time.sleep(delay_s)
        return []

    result = payload.get("result") if isinstance(payload, dict) else None
    rows = result.get("data") if isinstance(result, dict) else None
    if not isinstance(rows, list):
        rows = []

    cache[cache_key] = {
        "params": params,
        "fetched": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "count": len(rows),
        "data": rows,
    }
    _save(CACHE, cache)
    time.sleep(delay_s)
    return rows


def pick_best_photo(
    photos: list[dict],
    island_lat: float,
    island_lon: float,
    max_distance_m: float,
) -> tuple[dict, float] | None:
    best: tuple[float, dict] | None = None

    for photo in photos:
        if (photo.get("visibility") or "public").lower() not in ("public", ""):
            continue
        if (photo.get("status") or "active").lower() not in ("active", ""):
            continue
        coords = _photo_coords(photo)
        if not coords:
            continue
        plat, plon = coords
        dist = _haversine_m(island_lat, island_lon, plat, plon)
        if dist > max_distance_m:
            continue
        if best is None or dist < best[0]:
            best = (dist, photo)

    if best is None:
        return None
    return best[1], best[0]


def _save_staging(adoptions: list[dict]) -> None:
    STAGING.parent.mkdir(parents=True, exist_ok=True)
    tmp = STAGING.with_suffix(STAGING.suffix + ".tmp")
    tmp.write_text(
        json.dumps(adoptions, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, STAGING)


def main() -> int:
    p = argparse.ArgumentParser(
        description="Adopt CC-BY-SA KartaView photos for small named islands without images.",
    )
    p.add_argument(
        "--named-only",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Only islands in islands_index.json (default: true).",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Max pending islands to attempt (default 200). 0 = all.",
    )
    p.add_argument(
        "--max-distance-m",
        type=float,
        default=DEFAULT_MAX_DISTANCE_M,
        help=f"Max photo distance from centroid (default {DEFAULT_MAX_DISTANCE_M:.0f}).",
    )
    p.add_argument(
        "--max-area-km2",
        type=float,
        default=DEFAULT_MAX_AREA_KM2,
        help=f"Only islands with areaKm2 < this (default {DEFAULT_MAX_AREA_KM2}).",
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--refresh", action="store_true", help="Bypass KartaView response cache.")
    p.add_argument("--delay", type=float, default=DEFAULT_DELAY_S)
    p.add_argument("--test", default="", help="Process only the island with this id.")
    args = p.parse_args()
    delay_s = max(0.0, float(args.delay))

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    if not isinstance(islands, list):
        print("FATAL: islands.json is not a list", file=sys.stderr)
        return 2

    named_ids: set[str] = set()
    if args.named_only:
        named_ids = _load_named_index_ids()
        if not named_ids:
            print("FATAL: islands_index.json missing or empty", file=sys.stderr)
            return 2

    pending = [i for i in islands if not (i.get("images") or [])]
    if args.named_only:
        before = len(pending)
        pending = [i for i in pending if i.get("id") in named_ids]
        print(f"  named-only: {len(pending):,} of {before:,} without images", flush=True)

    eligible: list[dict] = []
    skipped_size: list[dict] = []
    for isl in pending:
        ok, reason = _eligible_area(isl, args.max_area_km2)
        if ok:
            eligible.append(isl)
        else:
            skipped_size.append({"id": isl.get("id"), "name": isl.get("name", ""), "reason": reason})

    pending = eligible
    if args.test:
        pending = [i for i in islands if i.get("id") == args.test]
        if not pending:
            print(f"FATAL: no island id {args.test!r}", file=sys.stderr)
            return 2
    if args.limit:
        pending = pending[: args.limit]

    cache = _load(CACHE)
    adoptions: list[dict] = []
    report: dict[str, Any] = {
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "script": "enrich_images_kartaview.py",
        "args": {
            "named_only": args.named_only,
            "limit": args.limit,
            "max_distance_m": args.max_distance_m,
            "max_area_km2": args.max_area_km2,
            "dry_run": args.dry_run,
            "delay": delay_s,
        },
        "license": LICENSE,
        "api_radius_m": API_RADIUS_M,
        "pending_considered": len(pending),
        "skipped_not_small": len(skipped_size),
        "adopted": [],
        "rejected": [],
        "skipped": [],
    }

    print(
        f"Pending (KartaView, area < {args.max_area_km2} km²): {len(pending):,} "
        f"(skipped {len(skipped_size):,} area ineligible)",
        flush=True,
    )

    n_attempted = 0
    n_adopted = 0
    n_checkpoint = 25
    last_checkpoint = 0
    started_at = time.time()

    for isl in pending:
        n_attempted += 1
        iid = isl.get("id", "")
        name = isl.get("name", "")
        lat = isl.get("lat")
        lon = _island_lon(isl)
        if lat is None or lon is None:
            report["skipped"].append({"id": iid, "reason": "missing lat/lng"})
            continue

        try:
            photos = fetch_photos_near(
                float(lat),
                float(lon),
                cache,
                island_id=str(iid),
                refresh=args.refresh,
                delay_s=delay_s,
            )
        except Exception as exc:
            report["rejected"].append({"id": iid, "name": name, "reason": str(exc)})
            continue

        picked = pick_best_photo(
            photos,
            float(lat),
            float(lon),
            args.max_distance_m,
        )
        if not picked:
            report["rejected"].append({
                "id": iid,
                "name": name,
                "reason": (
                    f"no CC-BY-SA photo within {args.max_distance_m:.0f} m "
                    f"({len(photos)} in {API_RADIUS_M} m query)"
                ),
            })
            continue

        photo, dist_m = picked
        rec = build_image_record(photo, isl, dist_m)
        if not rec:
            report["rejected"].append({
                "id": iid,
                "name": name,
                "reason": "photo missing usable image URL",
            })
            continue

        reason = (
            f"KartaView {rec['license']}; {dist_m:.0f} m from centroid; "
            f"areaKm2={isl.get('areaKm2')}"
        )
        adoption = {
            "id": iid,
            "name": name,
            "source": "kartaview",
            "image_record": rec,
            "confidence": CONFIDENCE,
            "reason": reason,
        }
        adoptions.append(adoption)
        report["adopted"].append({
            "id": iid,
            "name": name,
            "photoId": rec["sourceRef"],
            "distanceM": round(dist_m, 1),
            "license": rec["license"],
            "sourcePageUrl": rec["sourcePageUrl"],
            "confidence": CONFIDENCE,
        })
        n_adopted += 1
        print(
            f"  ✓ [{n_adopted:4d}] {iid:45s} photo {rec['sourceRef']} "
            f"@ {dist_m:.0f} m",
            flush=True,
        )

        if not args.dry_run and n_attempted - last_checkpoint >= n_checkpoint:
            _save_staging(adoptions)
            _save(REPORT, report)
            last_checkpoint = n_attempted
            rate = n_attempted / max(1.0, time.time() - started_at)
            print(
                f"  …checkpoint {n_attempted}/{len(pending)}, "
                f"{n_adopted} staged ({rate:.2f}/s)",
                flush=True,
            )

    if not args.dry_run:
        _save_staging(adoptions)

    report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    report["attempted"] = n_attempted
    report["adopted_total"] = n_adopted
    report["staged_total"] = len(adoptions)
    report["dry_run"] = args.dry_run
    report["staging_path"] = str(STAGING.relative_to(ROOT))
    _save(REPORT, report)

    print()
    print(f"Attempted: {n_attempted:,}")
    print(f"Staged:    {n_adopted:,}" + (" (dry-run)" if args.dry_run else ""))
    if not args.dry_run:
        print(f"Staging  → {STAGING.relative_to(ROOT)} ({len(adoptions):,} records)")
    print(f"Report   → {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
