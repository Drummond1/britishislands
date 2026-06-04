#!/usr/bin/env python3
"""Lead-photo enrichment via OpenAerialMap orthomosaic metadata (CC only).

Targets **named** atlas islands (``islands_index.json``) without ``images[]`` and
with known ``areaKm2`` < 0.3. Performs a STAC-style bbox search against the OAM
metadata API (``GET /meta?bbox=…`` — production search surface; see
https://docs.openaerialmap.org/api/api/) and adopts when the island centroid lies
inside the orthomosaic footprint and ``properties.license`` is CC-BY, CC-BY-SA,
or CC0 (excludes CC-BY-NC and ambiguous strings).

Run::

    python3 scripts/enrich_images_openaerialmap.py --named-only --limit 150
    python3 scripts/enrich_images_openaerialmap.py --dry-run --limit 20
    python3 scripts/enrich_images_openaerialmap.py --test isle-of-muck

Outputs (staging only — does not mutate islands.json)::

    data/staging/adoptions/openaerialmap.json
    data/cache_openaerialmap.json
    data/image_enrichment_openaerialmap_report.json
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
STAGING = DATA / "staging" / "adoptions" / "openaerialmap.json"
CACHE = DATA / "cache_openaerialmap.json"
REPORT = DATA / "image_enrichment_openaerialmap_report.json"

OAM_META = "https://api.openaerialmap.org/meta"
USER_AGENT = (
    "isles-of-britain/0.1 (openaerialmap image enrichment; "
    "https://www.findmyisland.com; static-site)"
)
DEFAULT_DELAY_S = 0.8
DEFAULT_MAX_AREA_KM2 = 0.3
SEARCH_PAD_M = 400.0
META_LIMIT = 10
CONFIDENCE = "medium"

NC_RE = re.compile(r"\bnc\b|non[\s\-]?commercial", re.IGNORECASE)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from enrich_images_v5 import _load, _load_named_index_ids, _open, _save  # noqa: E402


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
    dlat = pad_m / 111_320.0
    cos_lat = max(0.05, math.cos(math.radians(lat)))
    dlon = pad_m / (111_320.0 * cos_lat)
    return -dlon, -dlat, dlon, dlat


def _normalize_oam_license(raw: str | None) -> str | None:
    text = (raw or "").strip()
    if not text or NC_RE.search(text):
        return None
    compact = re.sub(r"\s+", " ", text.lower())
    if "cc0" in compact:
        return "CC0-1.0"
    if "by-sa" in compact or "by sa" in compact:
        return "CC-BY-SA-4.0"
    if re.search(r"cc[\s\-]?by", compact):
        return "CC-BY-4.0"
    return None


def _attribution_for_license(license_id: str, title: str, user_name: str) -> str:
    who = user_name or "OpenAerialMap contributor"
    title_bit = f'"{title}"' if title else "orthomosaic"
    if license_id == "CC0-1.0":
        return f"{title_bit} by {who}, CC0 1.0 via OpenAerialMap"
    if license_id == "CC-BY-SA-4.0":
        return (
            f"{title_bit} by {who}, licensed under CC BY-SA 4.0 via OpenAerialMap"
        )
    return f"{title_bit} by {who}, licensed under CC BY 4.0 via OpenAerialMap"


def _result_bbox(result: dict) -> tuple[float, float, float, float] | None:
    bbox = result.get("bbox")
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
        try:
            return tuple(float(x) for x in bbox[:4])  # type: ignore[return-value]
        except (TypeError, ValueError):
            pass
    gj = result.get("geojson") or {}
    if isinstance(gj, dict):
        bb = gj.get("bbox")
        if isinstance(bb, (list, tuple)) and len(bb) >= 4:
            try:
                return tuple(float(x) for x in bb[:4])
            except (TypeError, ValueError):
                pass
    return None


def _point_in_bbox(lon: float, lat: float, bbox: tuple[float, float, float, float]) -> bool:
    min_lon, min_lat, max_lon, max_lat = bbox
    if min_lon > max_lon:
        min_lon, max_lon = max_lon, min_lon
    if min_lat > max_lat:
        min_lat, max_lat = max_lat, min_lat
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def _footprint_area(bbox: tuple[float, float, float, float]) -> float:
    min_lon, min_lat, max_lon, max_lat = bbox
    return abs(max_lon - min_lon) * abs(max_lat - min_lat)


def stac_search_bbox(
    bbox: tuple[float, float, float, float],
    cache: dict[str, Any],
    *,
    cache_key: str,
    limit: int,
    refresh: bool,
    delay_s: float,
) -> list[dict]:
    """STAC Item Search semantics via OAM ``/meta`` (bbox = min_lon,min_lat,max_lon,max_lat)."""
    if not refresh and cache_key in cache:
        entry = cache[cache_key]
        if isinstance(entry, dict) and isinstance(entry.get("results"), list):
            return entry["results"]

    min_lon, min_lat, max_lon, max_lat = bbox
    params = {
        "bbox": f"{min_lon:.6f},{min_lat:.6f},{max_lon:.6f},{max_lat:.6f}",
        "limit": limit,
    }
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{OAM_META}?{qs}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        raw = _open(req, timeout=60)
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        cache[cache_key] = {
            "bbox": list(bbox),
            "error": repr(exc),
            "fetched": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "results": [],
        }
        _save(CACHE, cache)
        time.sleep(delay_s)
        return []

    rows = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        rows = []

    cache[cache_key] = {
        "bbox": list(bbox),
        "fetched": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "found": (payload.get("meta") or {}).get("found") if isinstance(payload, dict) else None,
        "results": rows,
    }
    _save(CACHE, cache)
    time.sleep(delay_s)
    return rows


def _thumbnail_url(result: dict) -> str:
    props = result.get("properties") or {}
    thumb = (props.get("thumbnail") or "").strip()
    if thumb:
        return thumb
    return ""


def _oam_page_url(result: dict) -> str:
    oid = (result.get("_id") or "").strip()
    if oid:
        return f"https://api.openaerialmap.org/meta/{oid}"
    meta_uri = (result.get("meta_uri") or "").strip()
    if meta_uri:
        return meta_uri
    return "https://openaerialmap.org/"


def build_image_record(result: dict, island: dict, license_id: str) -> dict | None:
    url = _thumbnail_url(result)
    if not url:
        return None

    oid = str(result.get("_id") or result.get("uuid") or "").strip()
    if not oid:
        return None

    title = (result.get("title") or "").strip()
    user = result.get("user") if isinstance(result.get("user"), dict) else {}
    user_name = (user.get("name") or "").strip()
    gsd = result.get("gsd")
    caption_bits = ["OpenAerialMap orthomosaic preview"]
    if title:
        caption_bits.append(title)
    if gsd:
        try:
            caption_bits.append(f"GSD {float(gsd):.2f} m")
        except (TypeError, ValueError):
            pass
    caption_bits.append("centroid inside footprint")

    return {
        "url": url,
        "source": "openaerialmap",
        "sourceRef": oid,
        "sourcePageUrl": _oam_page_url(result),
        "license": license_id,
        "attribution": _attribution_for_license(license_id, title, user_name),
        "caption": "; ".join(caption_bits),
        "primary": True,
        "imageConfidence": CONFIDENCE,
        "verifiedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "islandId": island.get("id"),
    }


def pick_best_result(
    results: list[dict],
    island_lat: float,
    island_lon: float,
) -> dict | None:
    candidates: list[tuple[float, dict]] = []
    for result in results:
        props = result.get("properties") or {}
        license_id = _normalize_oam_license(props.get("license"))
        if not license_id:
            continue
        bbox = _result_bbox(result)
        if not bbox or not _point_in_bbox(island_lon, island_lat, bbox):
            continue
        area = _footprint_area(bbox)
        candidates.append((area, result))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


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
        description="Stage CC OpenAerialMap previews for small named islands without images.",
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
        "--max-area-km2",
        type=float,
        default=DEFAULT_MAX_AREA_KM2,
        help=f"Only islands with areaKm2 < this (default {DEFAULT_MAX_AREA_KM2}).",
    )
    p.add_argument(
        "--search-pad-m",
        type=float,
        default=SEARCH_PAD_M,
        help=f"Bbox padding around centroid for STAC search (default {SEARCH_PAD_M:.0f}).",
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--refresh", action="store_true", help="Bypass OAM response cache.")
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
        "script": "enrich_images_openaerialmap.py",
        "args": {
            "named_only": args.named_only,
            "limit": args.limit,
            "max_area_km2": args.max_area_km2,
            "search_pad_m": args.search_pad_m,
            "dry_run": args.dry_run,
            "delay": delay_s,
        },
        "api": OAM_META,
        "search_style": "STAC bbox via GET /meta",
        "pending_considered": len(pending),
        "skipped_not_small": len(skipped_size),
        "adopted": [],
        "rejected": [],
        "skipped": [],
    }

    print(
        f"Pending (OpenAerialMap, area < {args.max_area_km2} km²): {len(pending):,} "
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

        dlon, dlat, _, _ = _bbox_pad_deg(float(lat), args.search_pad_m)
        search_bbox = (
            float(lon) + dlon,
            float(lat) + dlat,
            float(lon) - dlon,
            float(lat) - dlat,
        )
        min_lon = min(search_bbox[0], search_bbox[2])
        max_lon = max(search_bbox[0], search_bbox[2])
        min_lat = min(search_bbox[1], search_bbox[3])
        max_lat = max(search_bbox[1], search_bbox[3])
        bbox = (min_lon, min_lat, max_lon, max_lat)

        try:
            results = stac_search_bbox(
                bbox,
                cache,
                cache_key=str(iid),
                limit=META_LIMIT,
                refresh=args.refresh,
                delay_s=delay_s,
            )
        except Exception as exc:
            report["rejected"].append({"id": iid, "name": name, "reason": str(exc)})
            continue

        best = pick_best_result(results, float(lat), float(lon))
        if not best:
            report["rejected"].append({
                "id": iid,
                "name": name,
                "reason": (
                    f"no CC orthomosaic with centroid in footprint "
                    f"({len(results)} in bbox)"
                ),
            })
            continue

        props = best.get("properties") or {}
        license_id = _normalize_oam_license(props.get("license")) or "CC-BY-4.0"
        rec = build_image_record(best, isl, license_id)
        if not rec:
            report["rejected"].append({
                "id": iid,
                "name": name,
                "reason": "result missing thumbnail URL",
            })
            continue

        reason = (
            f"OpenAerialMap {license_id}; centroid in footprint; "
            f"areaKm2={isl.get('areaKm2')}"
        )
        adoption = {
            "id": iid,
            "name": name,
            "source": "openaerialmap",
            "image_record": rec,
            "confidence": CONFIDENCE,
            "reason": reason,
        }
        adoptions.append(adoption)
        report["adopted"].append({
            "id": iid,
            "name": name,
            "oamId": rec["sourceRef"],
            "license": license_id,
            "sourcePageUrl": rec["sourcePageUrl"],
            "confidence": CONFIDENCE,
        })
        n_adopted += 1
        print(
            f"  ✓ [{n_adopted:4d}] {iid:45s} {rec['sourceRef'][:12]}…",
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
