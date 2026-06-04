#!/usr/bin/env python3
"""Lead-photo enrichment via iNaturalist research-grade CC observations.

Targets **named** atlas islands (``islands_index.json`` ids) that still lack
``images[]`` and are small (``areaKm2`` < 1) or skerry-like. Queries the
iNaturalist observations API around each centroid, then adopts landscape /
coastal observations whose coordinates fall within 300 m of the island centre.
Both the observation and the chosen photo must carry an explicit CC-BY,
CC-BY-SA, or CC0 licence (skip when ambiguous or NC/ND).

Run::

    python3 scripts/enrich_images_inaturalist.py --named-only --limit 300
    python3 scripts/enrich_images_inaturalist.py --dry-run --limit 20
    python3 scripts/enrich_images_inaturalist.py --test isle-of-muck

Outputs (default: staging only — does not mutate islands.json)::

    data/staging/adoptions/inaturalist.json
    data/cache_inaturalist.json
    data/image_enrichment_inaturalist_report.json
"""

from __future__ import annotations

import argparse
import json
import math
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
ISLANDS_INDEX = DATA / "islands_index.json"
STAGING = DATA / "staging" / "adoptions" / "inaturalist.json"
CACHE = DATA / "cache_inaturalist.json"
REPORT = DATA / "image_enrichment_inaturalist_report.json"

INATURALIST_API = "https://api.inaturalist.org/v1/observations"
USER_AGENT = (
    "isles-of-britain/0.1 (inaturalist image enrichment; "
    "https://www.findmyisland.com; static-site)"
)
DEFAULT_DELAY_S = 1.0
DEFAULT_MAX_DISTANCE_M = 300.0
DEFAULT_MAX_AREA_KM2 = 1.0
API_RADIUS_KM = 0.5
PER_PAGE = 30
CONFIDENCE = "medium"

ALLOWED_LICENSES = frozenset({"cc-by", "cc-by-sa", "cc0"})
LICENSE_PARAM = "CC-BY,CC-BY-SA,CC0"

# Iconic taxa that usually show habitat / coastal context on small islets.
LANDSCAPE_ICONIC_TAXA = frozenset({
    "Plantae",
    "Chromista",
    "Aves",
    "Animalia",
    "Mollusca",
    "Actinopterygii",
    "Amphibia",
    "Reptilia",
    "Fungi",
})
MACRO_ICONIC_TAXA = frozenset({"Insecta", "Arachnida"})

COASTAL_PLACE_RE = re.compile(
    r"\b(?:sea|coast|shore|beach|cliff|rock|harbour|harbor|bay|island|"
    r"skerry|skerries|loch|tidal|headland|promontory|peninsula|strait|"
    r"sound|firth|estuary|lagoon|dune|machair|reef|shingle|pebble)\b",
    re.IGNORECASE,
)
SKERRY_NAME_RE = re.compile(
    r"\b(?:skerry|skerries|sgeir|sgeirean|holm|holms|eyot|ait|"
    r"rock|rocks|reef|carr|stack|stac)\b",
    re.IGNORECASE,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from enrich_images_v5 import _get_json, _load, _load_named_index_ids, _save  # noqa: E402


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


def _is_unnamed(island: dict) -> bool:
    if island.get("nameStatus") == "unknown":
        return True
    return "unnamed" in (island.get("tags") or [])


def _is_skerry_like(island: dict) -> bool:
    if _is_unnamed(island):
        return True
    tags = " ".join(str(t) for t in (island.get("tags") or []))
    if "skerry" in tags.lower():
        return True
    subtype = (island.get("subtype") or "").lower()
    if "skerry" in subtype:
        return True
    name = (island.get("name") or "").strip()
    return bool(name and SKERRY_NAME_RE.search(name))


def _eligible_island(island: dict, max_area_km2: float) -> tuple[bool, str]:
    if _is_skerry_like(island):
        return True, "skerry-like or unnamed"
    area = island.get("areaKm2")
    if area is None:
        return False, "areaKm2 unknown and not skerry-like"
    try:
        if float(area) < float(max_area_km2):
            return True, f"areaKm2={area} < {max_area_km2}"
    except (TypeError, ValueError):
        return False, "invalid areaKm2"
    return False, f"areaKm2={area} >= {max_area_km2}"


def _normalize_license(code: str | None) -> str | None:
    raw = (code or "").strip().lower()
    if not raw:
        return None
    if raw in ALLOWED_LICENSES:
        return raw
    if "nc" in raw or "nd" in raw or raw in ("all-rights-reserved", "copyright"):
        return None
    return None


def _format_license(code: str) -> str:
    if code == "cc0":
        return "CC0-1.0"
    if code == "cc-by":
        return "CC-BY-4.0"
    if code == "cc-by-sa":
        return "CC-BY-SA-4.0"
    return ""


def _obs_coords(obs: dict) -> tuple[float, float] | None:
    loc = (obs.get("location") or "").strip()
    if loc and "," in loc:
        try:
            lat_s, lon_s = loc.split(",", 1)
            return float(lat_s), float(lon_s)
        except (TypeError, ValueError):
            pass
    geom = obs.get("geojson")
    if isinstance(geom, dict) and geom.get("type") == "Point":
        coords = geom.get("coordinates")
        if isinstance(coords, (list, tuple)) and len(coords) >= 2:
            try:
                return float(coords[1]), float(coords[0])
            except (TypeError, ValueError):
                return None
    return None


def _photo_url(photo: dict) -> str:
    url = (photo.get("url") or "").strip()
    if not url:
        return ""
    for size in ("medium", "large"):
        candidate = re.sub(r"/square\.", f"/{size}.", url)
        if candidate != url:
            return candidate
    return url


def _photo_is_landscape(photo: dict) -> bool:
    dims = photo.get("original_dimensions") or {}
    try:
        w = int(dims.get("width") or 0)
        h = int(dims.get("height") or 0)
    except (TypeError, ValueError):
        return False
    return w > 0 and h > 0 and w >= h


def _is_landscape_coastal_obs(obs: dict, photo: dict) -> bool:
    if obs.get("captive"):
        return False
    if (obs.get("quality_grade") or "").lower() != "research":
        return False

    taxon = obs.get("taxon") or {}
    iconic = (taxon.get("iconic_taxon_name") or "").strip()
    place = (obs.get("place_guess") or "").strip()
    common = (taxon.get("preferred_common_name") or obs.get("species_guess") or "").strip()

    if iconic in LANDSCAPE_ICONIC_TAXA:
        return True
    if COASTAL_PLACE_RE.search(place) or COASTAL_PLACE_RE.search(common):
        return True
    if _photo_is_landscape(photo):
        return True
    if iconic in MACRO_ICONIC_TAXA:
        return False
    return _photo_is_landscape(photo)


def _pick_cc_photo(obs: dict) -> dict | None:
    obs_lic = _normalize_license(obs.get("license_code"))
    if not obs_lic:
        return None
    for photo in obs.get("photos") or []:
        if not isinstance(photo, dict):
            continue
        photo_lic = _normalize_license(photo.get("license_code"))
        if not photo_lic:
            continue
        if photo.get("hidden"):
            continue
        url = _photo_url(photo)
        if not url:
            continue
        return photo
    return None


def _observation_page_url(obs_id: str | int) -> str:
    return f"https://www.inaturalist.org/observations/{obs_id}"


def build_image_record(obs: dict, photo: dict, island: dict, distance_m: float) -> dict | None:
    obs_lic = _normalize_license(obs.get("license_code"))
    photo_lic = _normalize_license(photo.get("license_code"))
    if not obs_lic or not photo_lic:
        return None
    license_label = _format_license(photo_lic)
    if not license_label:
        return None

    url = _photo_url(photo)
    if not url:
        return None

    obs_id = str(obs.get("id") or "").strip()
    if not obs_id:
        return None

    taxon = obs.get("taxon") or {}
    caption_bits = [
        taxon.get("preferred_common_name") or obs.get("species_guess") or "iNaturalist observation",
    ]
    if obs.get("observed_on"):
        caption_bits.append(f"observed {obs['observed_on']}")
    caption_bits.append(f"{distance_m:.0f} m from island centroid")

    attribution = (photo.get("attribution") or "").strip()
    if not attribution:
        user = (obs.get("user") or {}).get("login") or "iNaturalist contributor"
        attribution = f"© {user} ({license_label}) via iNaturalist"

    return {
        "url": url,
        "source": "inaturalist-obs",
        "sourceRef": obs_id,
        "sourcePageUrl": _observation_page_url(obs_id),
        "license": license_label,
        "attribution": attribution,
        "caption": "; ".join(caption_bits),
        "primary": True,
        "imageConfidence": CONFIDENCE,
        "verifiedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "inaturalistDistanceM": round(distance_m, 1),
        "islandId": island.get("id"),
    }


def fetch_observations_near(
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
        if isinstance(entry, dict) and isinstance(entry.get("results"), list):
            return entry["results"]

    params = {
        "lat": lat,
        "lng": lon,
        "radius": API_RADIUS_KM,
        "photos": "true",
        "quality_grade": "research",
        "license": LICENSE_PARAM,
        "per_page": PER_PAGE,
        "order_by": "observed_on",
        "order": "desc",
    }
    try:
        payload = _get_json(INATURALIST_API, params)
    except Exception as exc:
        cache[cache_key] = {
            "params": params,
            "error": repr(exc),
            "fetched": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "results": [],
        }
        _save(CACHE, cache)
        time.sleep(delay_s)
        return []

    results = payload.get("results") or []
    cache[cache_key] = {
        "params": params,
        "fetched": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total_results": payload.get("total_results"),
        "results": results,
    }
    _save(CACHE, cache)
    time.sleep(delay_s)
    return results


def pick_best_observation(
    observations: list[dict],
    island_lat: float,
    island_lon: float,
    max_distance_m: float,
) -> tuple[dict, dict, float] | None:
    best: tuple[float, float, dict, dict] | None = None

    for obs in observations:
        photo = _pick_cc_photo(obs)
        if not photo:
            continue
        if not _is_landscape_coastal_obs(obs, photo):
            continue
        coords = _obs_coords(obs)
        if not coords:
            continue
        olat, olon = coords
        dist = _haversine_m(island_lat, island_lon, olat, olon)
        if dist > max_distance_m:
            continue
        landscape_bonus = 0.0
        iconic = ((obs.get("taxon") or {}).get("iconic_taxon_name") or "").strip()
        if iconic in LANDSCAPE_ICONIC_TAXA:
            landscape_bonus -= 20.0
        if _photo_is_landscape(photo):
            landscape_bonus -= 10.0
        score = dist + landscape_bonus
        if best is None or score < best[0]:
            best = (score, dist, obs, photo)

    if best is None:
        return None
    _, dist, obs, photo = best
    return obs, photo, dist


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
        description="Adopt CC iNaturalist observations for small named islands without images.",
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
        default=300,
        help="Max pending islands to attempt (default 300). 0 = all.",
    )
    p.add_argument(
        "--max-distance-m",
        type=float,
        default=DEFAULT_MAX_DISTANCE_M,
        help=f"Max observation distance from centroid (default {DEFAULT_MAX_DISTANCE_M:.0f}).",
    )
    p.add_argument(
        "--max-area-km2",
        type=float,
        default=DEFAULT_MAX_AREA_KM2,
        help=f"Only islands with areaKm2 < this, unless skerry-like (default {DEFAULT_MAX_AREA_KM2}).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Evaluate and report without writing staging.",
    )
    p.add_argument(
        "--refresh",
        action="store_true",
        help="Bypass iNaturalist response cache.",
    )
    p.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY_S,
        help=f"Seconds between API calls (default {DEFAULT_DELAY_S}).",
    )
    p.add_argument(
        "--test",
        default="",
        help="Process only the island with this id.",
    )
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
        ok, reason = _eligible_island(isl, args.max_area_km2)
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
        "script": "enrich_images_inaturalist.py",
        "args": {
            "named_only": args.named_only,
            "limit": args.limit,
            "max_distance_m": args.max_distance_m,
            "max_area_km2": args.max_area_km2,
            "dry_run": args.dry_run,
            "delay": delay_s,
        },
        "allowed_licenses": sorted(ALLOWED_LICENSES),
        "api_radius_km": API_RADIUS_KM,
        "pending_considered": len(pending),
        "skipped_not_small": len(skipped_size),
        "adopted": [],
        "rejected": [],
        "skipped": [],
    }

    print(
        f"Pending (iNaturalist, small/skerry): {len(pending):,} "
        f"(skipped {len(skipped_size):,} too large)",
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
            observations = fetch_observations_near(
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

        picked = pick_best_observation(
            observations,
            float(lat),
            float(lon),
            args.max_distance_m,
        )
        if not picked:
            report["rejected"].append({
                "id": iid,
                "name": name,
                "reason": (
                    f"no landscape/coastal CC obs within {args.max_distance_m:.0f} m "
                    f"({len(observations)} in {API_RADIUS_KM} km query)"
                ),
            })
            continue

        obs, photo, dist_m = picked
        rec = build_image_record(obs, photo, isl, dist_m)
        if not rec:
            report["rejected"].append({
                "id": iid,
                "name": name,
                "reason": "ambiguous or non-CC licence on observation/photo",
            })
            continue

        reason = (
            f"iNaturalist research-grade {rec['license']}; "
            f"{dist_m:.0f} m from centroid; landscape/coastal candidate"
        )
        adoption = {
            "id": iid,
            "image_record": rec,
            "confidence": CONFIDENCE,
            "reason": reason,
        }
        adoptions.append(adoption)
        report["adopted"].append({
            "id": iid,
            "name": name,
            "observationId": rec["sourceRef"],
            "distanceM": round(dist_m, 1),
            "license": rec["license"],
            "sourcePageUrl": rec["sourcePageUrl"],
            "caption": rec.get("caption"),
            "confidence": CONFIDENCE,
        })
        n_adopted += 1
        print(
            f"  ✓ [{n_adopted:4d}] {iid:45s} obs {rec['sourceRef']} "
            f"@ {dist_m:.0f} m ({rec['license']})",
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
