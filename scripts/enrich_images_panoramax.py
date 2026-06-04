#!/usr/bin/env python3
"""Lead-photo enrichment via Panoramax federated street imagery (CC-BY-SA).

Targets **named** atlas islands (``islands_index.json``) without ``images[]`` and
with known ``areaKm2`` < 0.3. Queries the Panoramax STAC search API
(``https://api.panoramax.xyz/api/search``) with a tight bbox around each centroid,
then adopts only when picture coordinates are within 250 m of the island centre
and the item licence is **CC-BY-SA** (per docs/ETHICS.md).

Run::

    python3 scripts/enrich_images_panoramax.py --named-only --limit 150
    python3 scripts/enrich_images_panoramax.py --dry-run --limit 20
    python3 scripts/enrich_images_panoramax.py --test isle-of-muck

Outputs (staging only — does not mutate islands.json)::

    data/staging/adoptions/panoramax.json
    data/cache_panoramax.json
    data/image_enrichment_panoramax_report.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
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
ISLANDS_INDEX = DATA / "islands_index.json"
STAGING = DATA / "staging" / "adoptions" / "panoramax.json"
CACHE = DATA / "cache_panoramax.json"
REPORT = DATA / "image_enrichment_panoramax_report.json"

PANORAMAX_SEARCH = "https://api.panoramax.xyz/api/search"
USER_AGENT = (
    "isles-of-britain/0.1 (panoramax image enrichment; "
    "https://www.findmyisland.com; static-site)"
)
DEFAULT_DELAY_S = 1.0
DEFAULT_MAX_DISTANCE_M = 250.0
DEFAULT_MAX_AREA_KM2 = 0.3
SEARCH_LIMIT = 25
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


def _bbox_pad_deg(lat: float, pad_m: float) -> tuple[float, float, float, float]:
    """min_lon, min_lat, max_lon, max_lat (STAC / OGC order)."""
    dlat = pad_m / 111_320.0
    cos_lat = max(0.05, math.cos(math.radians(lat)))
    dlon = pad_m / (111_320.0 * cos_lat)
    return -dlon, -dlat, dlon, dlat


def _feature_coords(feature: dict) -> tuple[float, float] | None:
    geom = feature.get("geometry")
    if not isinstance(geom, dict) or geom.get("type") != "Point":
        return None
    coords = geom.get("coordinates")
    if not isinstance(coords, (list, tuple)) or len(coords) < 2:
        return None
    try:
        lon, lat = float(coords[0]), float(coords[1])
    except (TypeError, ValueError):
        return None
    return lat, lon


def _feature_license_ok(feature: dict) -> bool:
    props = feature.get("properties") or {}
    lic = (props.get("license") or "").strip().lower()
    if lic and ("by-sa" in lic or lic == "cc-by-sa-4.0"):
        return True
    for link in feature.get("links") or []:
        if link.get("rel") != "license":
            continue
        href = (link.get("href") or "").lower()
        title = (link.get("title") or "").lower()
        if "by-sa" in href or "by-sa" in title:
            return True
    return False


def _picture_url(feature: dict) -> str:
    assets = feature.get("assets") or {}
    for key in ("sd", "thumb", "hd"):
        asset = assets.get(key)
        if isinstance(asset, dict):
            href = (asset.get("href") or "").strip()
            if href:
                return href
    return ""


def _picture_page_url(feature: dict) -> str:
    for link in feature.get("links") or []:
        if link.get("rel") == "self" and link.get("href"):
            return str(link["href"])
    pic_id = str(feature.get("id") or "").strip()
    if pic_id:
        return f"https://api.panoramax.xyz/api/collections/items/{pic_id}"
    return "https://api.panoramax.xyz/"


def build_image_record(feature: dict, island: dict, distance_m: float) -> dict | None:
    url = _picture_url(feature)
    if not url:
        return None
    pic_id = str(feature.get("id") or "").strip()
    if not pic_id:
        return None

    props = feature.get("properties") or {}
    caption_bits = ["Panoramax street-level photo"]
    if props.get("datetime"):
        caption_bits.append(f"captured {props['datetime']}")
    if props.get("view:azimuth") is not None:
        caption_bits.append(f"azimuth {props['view:azimuth']}°")
    caption_bits.append(f"{distance_m:.0f} m from island centroid")

    return {
        "url": url,
        "source": "panoramax",
        "sourceRef": pic_id,
        "sourcePageUrl": _picture_page_url(feature),
        "license": LICENSE,
        "attribution": "© Panoramax contributors, CC BY-SA 4.0",
        "caption": "; ".join(caption_bits),
        "primary": True,
        "imageConfidence": CONFIDENCE,
        "verifiedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "panoramaxDistanceM": round(distance_m, 1),
        "islandId": island.get("id"),
    }


def fetch_pictures_near(
    lat: float,
    lon: float,
    cache: dict[str, Any],
    *,
    island_id: str,
    radius_m: float,
    refresh: bool,
    delay_s: float,
) -> list[dict]:
    cache_key = island_id or f"{lat:.5f},{lon:.5f}"
    if not refresh and cache_key in cache:
        entry = cache[cache_key]
        if isinstance(entry, dict) and isinstance(entry.get("features"), list):
            return entry["features"]

    dlon, dlat, _, _ = _bbox_pad_deg(lat, radius_m)
    min_lon, max_lon = lon + dlon, lon - dlon
    min_lat, max_lat = lat + dlat, lat - dlat
    if min_lon > max_lon:
        min_lon, max_lon = max_lon, min_lon
    if min_lat > max_lat:
        min_lat, max_lat = max_lat, min_lat

    params = {
        "bbox": f"{min_lon:.6f},{min_lat:.6f},{max_lon:.6f},{max_lat:.6f}",
        "limit": SEARCH_LIMIT,
    }
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{PANORAMAX_SEARCH}?{qs}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json"},
    )
    try:
        raw = _open(req, timeout=45)
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        cache[cache_key] = {
            "bbox": params["bbox"],
            "error": repr(exc),
            "fetched": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "features": [],
        }
        _save(CACHE, cache)
        time.sleep(delay_s)
        return []

    features = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(features, list):
        features = []

    cache[cache_key] = {
        "bbox": params["bbox"],
        "fetched": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "count": len(features),
        "features": features,
    }
    _save(CACHE, cache)
    time.sleep(delay_s)
    return features


def pick_best_picture(
    features: list[dict],
    island_lat: float,
    island_lon: float,
    max_distance_m: float,
) -> tuple[dict, float] | None:
    best: tuple[float, dict] | None = None
    for feature in features:
        if not _feature_license_ok(feature):
            continue
        coords = _feature_coords(feature)
        if not coords:
            continue
        plat, plon = coords
        dist = _haversine_m(island_lat, island_lon, plat, plon)
        if dist > max_distance_m:
            continue
        if best is None or dist < best[0]:
            best = (dist, feature)
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
        description="Stage CC-BY-SA Panoramax photos for small named islands without images.",
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
        default=150,
        help="Max pending islands to attempt (default 150). 0 = all.",
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
    p.add_argument("--refresh", action="store_true", help="Bypass Panoramax response cache.")
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
            skipped_size.append({
                "id": isl.get("id"),
                "name": isl.get("name", ""),
                "reason": reason,
            })

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
        "script": "enrich_images_panoramax.py",
        "args": {
            "named_only": args.named_only,
            "limit": args.limit,
            "max_distance_m": args.max_distance_m,
            "max_area_km2": args.max_area_km2,
            "dry_run": args.dry_run,
            "delay": delay_s,
        },
        "license": LICENSE,
        "api": PANORAMAX_SEARCH,
        "pending_considered": len(pending),
        "skipped_not_small": len(skipped_size),
        "adopted": [],
        "rejected": [],
        "skipped": [],
    }

    print(
        f"Pending (Panoramax, area < {args.max_area_km2} km²): {len(pending):,} "
        f"(skipped {len(skipped_size):,} area ineligible)",
        flush=True,
    )

    n_attempted = 0
    n_adopted = 0

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
            features = fetch_pictures_near(
                float(lat),
                float(lon),
                cache,
                island_id=str(iid),
                radius_m=args.max_distance_m,
                refresh=args.refresh,
                delay_s=delay_s,
            )
        except Exception as exc:
            report["rejected"].append({"id": iid, "name": name, "reason": str(exc)})
            continue

        picked = pick_best_picture(
            features,
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
                    f"({len(features)} in bbox)"
                ),
            })
            continue

        feature, dist_m = picked
        rec = build_image_record(feature, isl, dist_m)
        if not rec:
            report["rejected"].append({
                "id": iid,
                "name": name,
                "reason": "feature missing usable image URL",
            })
            continue

        reason = (
            f"Panoramax {rec['license']}; {dist_m:.0f} m from centroid; "
            f"areaKm2={isl.get('areaKm2')}"
        )
        adoption = {
            "id": iid,
            "name": name,
            "source": "panoramax",
            "image_record": rec,
            "confidence": CONFIDENCE,
            "reason": reason,
        }
        adoptions.append(adoption)
        report["adopted"].append({
            "id": iid,
            "name": name,
            "pictureId": rec["sourceRef"],
            "distanceM": round(dist_m, 1),
            "license": rec["license"],
            "sourcePageUrl": rec["sourcePageUrl"],
            "confidence": CONFIDENCE,
        })
        n_adopted += 1
        print(
            f"  ✓ [{n_adopted:4d}] {iid:45s} {rec['sourceRef'][:8]}… "
            f"@ {dist_m:.0f} m",
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
