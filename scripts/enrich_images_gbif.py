#!/usr/bin/env python3
"""Lead-photo enrichment via GBIF occurrence records with CC StillImage media.

Targets **named** atlas islands (``islands_index.json``) without ``images[]``.
Queries the GBIF Occurrence API for **research-grade** iNaturalist observations
(dataset ``50c9509d-22c7-4a22-a47d-8c48425ef4a7``) with explicit CC0 / CC-BY /
CC-BY-SA licences and StillImage media, then adopts only when occurrence
coordinates fall within 300 m of the island centroid (verified via haversine).

Run::

    python3 scripts/enrich_images_gbif.py --named-only --limit 200
    python3 scripts/enrich_images_gbif.py --dry-run --limit 20
    python3 scripts/enrich_images_gbif.py --test isle-of-muck

Outputs (staging only — does not mutate islands.json)::

    data/staging/adoptions/gbif.json
    data/cache_gbif.json
    data/image_enrichment_gbif_report.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
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
STAGING = DATA / "staging" / "adoptions" / "gbif.json"
CACHE = DATA / "cache_gbif.json"
REPORT = DATA / "image_enrichment_gbif_report.json"

GBIF_SEARCH = "https://api.gbif.org/v1/occurrence/search"
INAT_RESEARCH_DATASET = "50c9509d-22c7-4a22-a47d-8c48425ef4a7"
USER_AGENT = (
    "isles-of-britain/0.1 (gbif occurrence image enrichment; "
    "https://www.findmyisland.com; static-site)"
)
DEFAULT_DELAY_S = 0.6
DEFAULT_MAX_DISTANCE_M = 300.0
QUERY_PAD_M = 350.0
PER_PAGE = 50
CONFIDENCE = "medium"

ALLOWED_GBIF_LICENSES = frozenset({
    "CC0_1_0",
    "CC_BY_4_0",
    "CC_BY_SA_4_0",
})

CC_URL_RE = re.compile(
    r"creativecommons\.org/licenses/(by|by-sa|zero)/",
    re.IGNORECASE,
)

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


def _bbox_polygon_wkt(lat: float, lon: float, pad_m: float) -> str:
    dlat = pad_m / 111_320.0
    cos_lat = max(0.05, math.cos(math.radians(lat)))
    dlon = pad_m / (111_320.0 * cos_lat)
    return (
        f"POLYGON(("
        f"{lon - dlon} {lat - dlat},"
        f"{lon + dlon} {lat - dlat},"
        f"{lon + dlon} {lat + dlat},"
        f"{lon - dlon} {lat + dlat},"
        f"{lon - dlon} {lat - dlat}"
        f"))"
    )


def _normalize_license_url(url: str | None) -> str | None:
    raw = (url or "").strip().lower()
    if not raw:
        return None
    if "nc" in raw or "nd" in raw:
        return None
    if "publicdomain" in raw or "/zero/" in raw or "/cc0" in raw:
        return "CC0-1.0"
    if "/by-sa/" in raw or "by-sa" in raw:
        return "CC-BY-SA-4.0"
    if "/by/" in raw or CC_URL_RE.search(raw):
        return "CC-BY-4.0"
    return None


def _occurrence_coords(occ: dict) -> tuple[float, float] | None:
    lat = occ.get("decimalLatitude")
    lon = occ.get("decimalLongitude")
    if lat is None or lon is None:
        return None
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None


def _pick_cc_media(occ: dict) -> dict | None:
    occ_lic = _normalize_license_url(occ.get("license"))
    for media in occ.get("media") or []:
        if not isinstance(media, dict):
            continue
        if (media.get("type") or "").lower() != "stillimage":
            continue
        media_lic = _normalize_license_url(media.get("license"))
        if not media_lic and not occ_lic:
            continue
        if not media_lic:
            media_lic = occ_lic
        if not media_lic:
            continue
        identifier = (media.get("identifier") or "").strip()
        if not identifier or not identifier.startswith("http"):
            continue
        return {**media, "_license_label": media_lic}
    return None


def _image_url(identifier: str) -> str:
    url = identifier.strip()
    for size in ("medium", "large"):
        candidate = re.sub(r"/original\.", f"/{size}.", url)
        if candidate != url:
            return candidate
    return url


def _gbif_page_url(gbif_id: str | int) -> str:
    return f"https://www.gbif.org/occurrence/{gbif_id}"


def _source_page_url(occ: dict) -> str:
    ref = (occ.get("references") or occ.get("occurrenceID") or "").strip()
    if ref.startswith("http"):
        return ref
    gbif_id = occ.get("key")
    if gbif_id is not None:
        return _gbif_page_url(gbif_id)
    return "https://www.gbif.org/"


def build_image_record(occ: dict, media: dict, island: dict, distance_m: float) -> dict | None:
    license_label = media.get("_license_label") or _normalize_license_url(occ.get("license"))
    if not license_label:
        return None

    url = _image_url(media.get("identifier") or "")
    if not url:
        return None

    gbif_id = str(occ.get("key") or "").strip()
    if not gbif_id:
        return None

    caption_bits = []
    if occ.get("species"):
        caption_bits.append(str(occ["species"]))
    elif occ.get("scientificName"):
        caption_bits.append(str(occ["scientificName"]))
    else:
        caption_bits.append("GBIF research-grade observation")
    if occ.get("eventDate"):
        caption_bits.append(f"recorded {occ['eventDate']}")
    caption_bits.append(f"{distance_m:.0f} m from island centroid")

    creator = (media.get("creator") or occ.get("recordedBy") or "").strip()
    rights = (media.get("rightsHolder") or creator or "GBIF contributor").strip()
    attribution = f"© {rights} ({license_label}) via GBIF / iNaturalist"

    return {
        "url": url,
        "source": "gbif-occurrence",
        "sourceRef": gbif_id,
        "sourcePageUrl": _source_page_url(occ),
        "license": license_label,
        "attribution": attribution,
        "caption": "; ".join(caption_bits),
        "primary": True,
        "imageConfidence": CONFIDENCE,
        "verifiedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "gbifDistanceM": round(distance_m, 1),
        "islandId": island.get("id"),
    }


def fetch_occurrences_near(
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

    geometry = _bbox_polygon_wkt(lat, lon, QUERY_PAD_M)
    params: list[tuple[str, str | int]] = [
        ("datasetKey", INAT_RESEARCH_DATASET),
        ("hasCoordinate", "true"),
        ("hasGeospatialIssue", "false"),
        ("mediaType", "StillImage"),
        ("geometry", geometry),
        ("limit", PER_PAGE),
    ]
    for lic in sorted(ALLOWED_GBIF_LICENSES):
        params.append(("license", lic))

    qs = urlencode(params)
    req_url = f"{GBIF_SEARCH}?{qs}"
    try:
        import urllib.request

        req = urllib.request.Request(
            req_url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        raw = _open(req, timeout=45)
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        cache[cache_key] = {
            "geometry": geometry,
            "error": repr(exc),
            "fetched": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "results": [],
        }
        _save(CACHE, cache)
        time.sleep(delay_s)
        return []

    results = payload.get("results") or []
    cache[cache_key] = {
        "geometry": geometry,
        "fetched": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "count": payload.get("count"),
        "results": results,
    }
    _save(CACHE, cache)
    time.sleep(delay_s)
    return results


def pick_best_occurrence(
    occurrences: list[dict],
    island_lat: float,
    island_lon: float,
    max_distance_m: float,
) -> tuple[dict, dict, float] | None:
    best: tuple[float, dict, dict] | None = None

    for occ in occurrences:
        media = _pick_cc_media(occ)
        if not media:
            continue
        coords = _occurrence_coords(occ)
        if not coords:
            continue
        olat, olon = coords
        dist = _haversine_m(island_lat, island_lon, olat, olon)
        if dist > max_distance_m:
            continue
        if best is None or dist < best[0]:
            best = (dist, occ, media)

    if best is None:
        return None
    dist, occ, media = best
    return occ, media, dist


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
        description="Adopt CC GBIF occurrence photos for named islands without images.",
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
        help=f"Max occurrence distance from centroid (default {DEFAULT_MAX_DISTANCE_M:.0f}).",
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--refresh", action="store_true", help="Bypass GBIF response cache.")
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
        "script": "enrich_images_gbif.py",
        "args": {
            "named_only": args.named_only,
            "limit": args.limit,
            "max_distance_m": args.max_distance_m,
            "dry_run": args.dry_run,
            "delay": delay_s,
        },
        "dataset_key": INAT_RESEARCH_DATASET,
        "dataset_name": "iNaturalist research-grade observations",
        "allowed_gbif_licenses": sorted(ALLOWED_GBIF_LICENSES),
        "query_pad_m": QUERY_PAD_M,
        "pending_considered": len(pending),
        "adopted": [],
        "rejected": [],
        "skipped": [],
    }

    print(f"Pending (GBIF research-grade CC media): {len(pending):,}", flush=True)

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
            occurrences = fetch_occurrences_near(
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

        picked = pick_best_occurrence(
            occurrences,
            float(lat),
            float(lon),
            args.max_distance_m,
        )
        if not picked:
            report["rejected"].append({
                "id": iid,
                "name": name,
                "reason": (
                    f"no research-grade CC StillImage within {args.max_distance_m:.0f} m "
                    f"({len(occurrences)} in query polygon)"
                ),
            })
            continue

        occ, media, dist_m = picked
        rec = build_image_record(occ, media, isl, dist_m)
        if not rec:
            report["rejected"].append({
                "id": iid,
                "name": name,
                "reason": "ambiguous or non-CC licence on occurrence/media",
            })
            continue

        reason = (
            f"GBIF research-grade {rec['license']}; "
            f"{dist_m:.0f} m from centroid; dataset {INAT_RESEARCH_DATASET[:8]}…"
        )
        adoption = {
            "id": iid,
            "name": name,
            "source": "gbif-occurrence",
            "image_record": rec,
            "confidence": CONFIDENCE,
            "reason": reason,
        }
        adoptions.append(adoption)
        report["adopted"].append({
            "id": iid,
            "name": name,
            "gbifId": rec["sourceRef"],
            "distanceM": round(dist_m, 1),
            "license": rec["license"],
            "sourcePageUrl": rec["sourcePageUrl"],
            "confidence": CONFIDENCE,
        })
        n_adopted += 1
        print(
            f"  ✓ [{n_adopted:4d}] {iid:45s} gbif {rec['sourceRef']} "
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
