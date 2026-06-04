#!/usr/bin/env python3
"""
Mapillary API v4 — street-level CC-BY-SA photos near small island centroids.

Targets **named** atlas islands (``data/islands_index.json``) that still lack
``images[]``. Queries ``https://graph.mapillary.com/images`` with a tight bbox
around each centroid, then adopts only when the image geometry is within
300 m of the island centre. When ``areaKm2`` is known, skips islands
≥ 0.5 km² to reduce mainland / shore-mismatch risk.

Licence: Mapillary imagery is **CC-BY-SA 4.0** (acceptable per docs/ETHICS.md).
Adopted records use ``source: mapillary``, ``imageConfidence: medium``.

Authentication (Mapillary docs, 2026):
  All ``graph.mapillary.com`` requests require a **client access token**
  (https://www.mapillary.com/dashboard/developers). There is no anonymous
  metadata access on the Graph API.

  Set ``MAPILLARY_ACCESS_TOKEN`` (or ``MAPILLARY_CLIENT_TOKEN``) in the
  environment. The script probes without a token first and records whether
  that succeeds.

Run::

    python3 scripts/enrich_images_mapillary.py --named-only --limit 50 --dry-run
    python3 scripts/enrich_images_mapillary.py --named-only --limit 50
    python3 scripts/enrich_images_mapillary.py --test isle-of-muck

Outputs::

    data/islands.json                              (mutated unless --dry-run)
    data/islands.json.before-mapillary               (backup)
    data/cache_mapillary.json                        (bbox query cache)
    data/image_enrichment_mapillary_report.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
ISLANDS_INDEX = DATA / "islands_index.json"
BACKUP = DATA / "islands.json.before-mapillary"
CACHE = DATA / "cache_mapillary.json"
REPORT = DATA / "image_enrichment_mapillary_report.json"

GRAPH = "https://graph.mapillary.com/images"
USER_AGENT = (
    "isles-of-britain/0.1 (mapillary image enrichment; "
    "https://www.findmyisland.com; static-site)"
)
DELAY_S = 0.35
DEFAULT_MAX_DISTANCE_M = 300.0
DEFAULT_MAX_AREA_KM2 = 0.5
BBOX_PAD_M = 320.0  # query slightly wider than adopt radius (API max radius is 50 m)
MAPILLARY_FIELDS = "id,thumb_256_url,compass_angle,geometry,captured_at"
LICENSE = "CC-BY-SA-4.0"
CONFIDENCE = "medium"


def _access_token() -> str:
    for key in (
        "MAPILLARY_ACCESS_TOKEN",
        "MAPILLARY_CLIENT_TOKEN",
        "MAPPERILY_ACCESS_TOKEN",  # common typo; documented in header comment
    ):
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    return ""


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _bbox_for_point(lat: float, lon: float, pad_m: float) -> tuple[float, float, float, float]:
    """minLon, minLat, maxLon, maxLat — Mapillary bbox order."""
    dlat = pad_m / 111_320.0
    cos_lat = max(0.05, math.cos(math.radians(lat)))
    dlon = pad_m / (111_320.0 * cos_lat)
    return lon - dlon, lat - dlat, lon + dlon, lat + dlat


def _load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(path: Path, payload: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _named_index_ids() -> set[str]:
    payload = _load_json(ISLANDS_INDEX, {})
    rows = payload.get("rows") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return set()
    return {str(r.get("id", "")).strip() for r in rows if r.get("id")}


def _open(req: urllib.request.Request, timeout: int = 45) -> bytes:
    last: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code in (401, 403):
                raise
            time.sleep((1.4 ** attempt) + random.random() * 0.3)
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            time.sleep((1.4 ** attempt) + random.random() * 0.3)
    raise RuntimeError(f"HTTP failed: {last}")


def _mapillary_get(
    params: dict[str, Any],
    token: str,
    *,
    use_header: bool = True,
) -> dict[str, Any]:
    q = dict(params)
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if use_header and token:
        headers["Authorization"] = f"OAuth {token}"
    else:
        q["access_token"] = token
    qs = urllib.parse.urlencode(q)
    req = urllib.request.Request(f"{GRAPH}?{qs}", headers=headers)
    raw = _open(req)
    return json.loads(raw.decode("utf-8"))


def probe_api(token: str) -> dict[str, Any]:
    """Test Graph API with and without token; return diagnostic dict."""
    lat, lon = 57.15, -7.25  # Hebrides sample
    bbox = _bbox_for_point(lat, lon, 80.0)
    base_params = {
        "fields": "id",
        "bbox": ",".join(f"{x:.6f}" for x in bbox),
        "limit": 1,
    }
    out: dict[str, Any] = {
        "graph_endpoint": GRAPH,
        "token_present": bool(token),
    }

    # Without token (no Authorization header, no access_token query param)
    try:
        qs = urllib.parse.urlencode(base_params)
        req = urllib.request.Request(
            f"{GRAPH}?{qs}",
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            json.loads(resp.read().decode("utf-8"))
        out["works_without_token"] = True
        out["without_token_error"] = None
    except urllib.error.HTTPError as exc:
        out["works_without_token"] = False
        try:
            body = exc.read().decode("utf-8", errors="replace")
            err = json.loads(body).get("error", {}) if body.strip().startswith("{") else {}
            msg = err.get("message") or body[:300] or exc.reason
        except Exception:
            msg = exc.reason
        out["without_token_http"] = exc.code
        out["without_token_error"] = f"HTTP {exc.code}: {msg}"
    except Exception as exc:
        out["works_without_token"] = False
        out["without_token_error"] = str(exc)

    if not token:
        out["works_with_token"] = None
        out["with_token_error"] = "no token in environment"
        return out

    try:
        _mapillary_get(base_params, token, use_header=True)
        out["works_with_token"] = True
        out["with_token_error"] = None
    except urllib.error.HTTPError as exc:
        out["works_with_token"] = False
        try:
            body = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            body = ""
        out["with_token_error"] = f"HTTP {exc.code}: {body or exc.reason}"
    except Exception as exc:
        out["works_with_token"] = False
        out["with_token_error"] = str(exc)

    return out


def _image_coords(img: dict[str, Any]) -> tuple[float, float] | None:
    geom = img.get("geometry") or img.get("computed_geometry")
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


def _mapillary_page_url(image_id: str) -> str:
    return f"https://www.mapillary.com/app/?pKey={image_id}"


def build_mapillary_record(
    img: dict[str, Any],
    island: dict[str, Any],
    distance_m: float,
) -> dict[str, Any]:
    image_id = str(img.get("id", ""))
    thumb = (img.get("thumb_256_url") or "").strip()
    if not thumb:
        thumb = f"https://graph.mapillary.com/{image_id}?fields=thumb_256_url"
    captured = img.get("captured_at")
    caption_bits = []
    if captured:
        caption_bits.append(f"Mapillary capture {captured}")
    if img.get("compass_angle") is not None:
        caption_bits.append(f"compass {img['compass_angle']}°")
    caption_bits.append(f"{distance_m:.0f} m from island centroid")
    return {
        "url": thumb,
        "source": "mapillary",
        "sourceRef": image_id,
        "sourcePageUrl": _mapillary_page_url(image_id),
        "license": LICENSE,
        "attribution": "© Mapillary contributors, CC BY-SA 4.0",
        "caption": "; ".join(caption_bits),
        "primary": True,
        "imageConfidence": CONFIDENCE,
        "verifiedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "mapillaryDistanceM": round(distance_m, 1),
        "islandId": island.get("id"),
    }


def fetch_images_near(
    lat: float,
    lon: float,
    token: str,
    cache: dict[str, Any],
    *,
    refresh: bool,
) -> list[dict[str, Any]]:
    cache_key = f"{lat:.5f},{lon:.5f}"
    if not refresh and cache_key in cache:
        entry = cache[cache_key]
        if isinstance(entry, dict) and isinstance(entry.get("data"), list):
            return entry["data"]

    min_lon, min_lat, max_lon, max_lat = _bbox_for_point(lat, lon, BBOX_PAD_M)
    params = {
        "fields": MAPILLARY_FIELDS,
        "bbox": f"{min_lon:.6f},{min_lat:.6f},{max_lon:.6f},{max_lat:.6f}",
        "limit": 100,
    }
    payload = _mapillary_get(params, token, use_header=True)
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        rows = []
    cache[cache_key] = {
        "fetched": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "bbox": [min_lon, min_lat, max_lon, max_lat],
        "data": rows,
        "raw_count": len(rows),
    }
    return rows


def pick_best_image(
    images: list[dict[str, Any]],
    island_lat: float,
    island_lon: float,
    max_distance_m: float,
) -> tuple[dict[str, Any] | None, float | None]:
    best: dict[str, Any] | None = None
    best_dist: float | None = None
    for img in images:
        coords = _image_coords(img)
        if not coords:
            continue
        ilat, ilon = coords
        dist = _haversine_m(island_lat, island_lon, ilat, ilon)
        if dist > max_distance_m:
            continue
        if best_dist is None or dist < best_dist:
            best, best_dist = img, dist
    return best, best_dist


def main() -> int:
    p = argparse.ArgumentParser(description="Mapillary CC-BY-SA enrichment for named islands.")
    p.add_argument(
        "--all-islands",
        action="store_true",
        help="Process any island without images (default: named index only).",
    )
    p.add_argument("--limit", type=int, default=50,
                   help="Max pending islands to attempt (default 50). 0 = all.")
    p.add_argument("--adopt-limit", type=int, default=0,
                   help="Stop after this many adoptions (0 = no cap).")
    p.add_argument("--max-distance-m", type=float, default=DEFAULT_MAX_DISTANCE_M)
    p.add_argument("--max-area-km2", type=float, default=DEFAULT_MAX_AREA_KM2,
                   help="Skip when areaKm2 is known and >= this (0 disables).")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-backup", action="store_true")
    p.add_argument("--refresh", action="store_true", help="Bypass Mapillary response cache.")
    p.add_argument("--test", default="", help="Single island id.")
    p.add_argument("--delay", type=float, default=DELAY_S)
    args = p.parse_args()

    token = _access_token()
    api_probe = probe_api(token)

    islands = _load_json(ISLANDS, [])
    if not isinstance(islands, list):
        print("FATAL: islands.json is not a list", file=sys.stderr)
        return 2

    named_ids = _named_index_ids()
    use_named = not args.all_islands
    if use_named and not named_ids:
        print("FATAL: islands_index.json missing or empty", file=sys.stderr)
        return 2

    pending = [
        i for i in islands
        if not (i.get("images") or [])
        and (i.get("name") or "").strip()
    ]
    if use_named:
        pending = [i for i in pending if i.get("id") in named_ids]
    if args.test:
        pending = [i for i in islands if i.get("id") == args.test]
        if not pending:
            print(f"FATAL: no island id {args.test!r}", file=sys.stderr)
            return 2
    if args.limit:
        pending = pending[: args.limit]

    if not args.dry_run and not args.no_backup and not BACKUP.exists():
        BACKUP.write_text(
            json.dumps(islands, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Backup → {BACKUP.relative_to(ROOT)}")

    cache = _load_json(CACHE, {})
    if not isinstance(cache, dict):
        cache = {}

    report: dict[str, Any] = {
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "script": "enrich_images_mapillary.py",
        "args": vars(args),
        "api_probe": api_probe,
        "max_distance_m": args.max_distance_m,
        "max_area_km2": args.max_area_km2,
        "pending_considered": len(pending),
        "adopted": [],
        "rejected": [],
        "skipped": [],
        "dry_run": bool(args.dry_run),
    }

    print("Mapillary API probe:", flush=True)
    print(f"  works without token: {api_probe.get('works_without_token')}", flush=True)
    if api_probe.get("without_token_error"):
        print(f"    → {api_probe['without_token_error']}", flush=True)
    if token:
        print(f"  works with token:    {api_probe.get('works_with_token')}", flush=True)
        if api_probe.get("with_token_error"):
            print(f"    → {api_probe['with_token_error']}", flush=True)
    else:
        print("  MAPILLARY_ACCESS_TOKEN: not set", flush=True)

    if not token or not api_probe.get("works_with_token"):
        print(
            "\nCannot adopt images without a valid Mapillary access token.",
            file=sys.stderr,
        )
        report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        report["adopted_total"] = 0
        _save_json(REPORT, report)
        print(f"Report → {REPORT.relative_to(ROOT)}")
        return 1 if not token else 2

    n_adopted = 0
    n_attempted = 0

    for isl in pending:
        if args.adopt_limit and n_adopted >= args.adopt_limit:
            break

        iid = isl.get("id", "")
        name = isl.get("name", "")
        lat = isl.get("lat")
        lon = isl.get("lng") if isl.get("lng") is not None else isl.get("lon")
        if lat is None or lon is None:
            report["skipped"].append({"id": iid, "reason": "missing lat/lng"})
            continue

        area = isl.get("areaKm2")
        if args.max_area_km2 and area is not None:
            try:
                if float(area) >= float(args.max_area_km2):
                    report["skipped"].append({
                        "id": iid,
                        "name": name,
                        "reason": f"areaKm2={area} >= {args.max_area_km2}",
                    })
                    continue
            except (TypeError, ValueError):
                pass

        n_attempted += 1
        time.sleep(max(0.0, args.delay))

        try:
            candidates = fetch_images_near(
                float(lat), float(lon), token, cache, refresh=args.refresh,
            )
        except urllib.error.HTTPError as exc:
            report["rejected"].append({
                "id": iid,
                "name": name,
                "reason": f"API HTTP {exc.code}",
            })
            if exc.code == 429:
                print("Rate limited — stopping early.", file=sys.stderr)
                break
            continue
        except Exception as exc:
            report["rejected"].append({"id": iid, "name": name, "reason": str(exc)})
            continue

        best, dist_m = pick_best_image(
            candidates, float(lat), float(lon), args.max_distance_m,
        )
        if not best or dist_m is None:
            report["rejected"].append({
                "id": iid,
                "name": name,
                "reason": f"no image within {args.max_distance_m:.0f} m "
                f"({len(candidates)} in bbox)",
            })
            continue

        rec = build_mapillary_record(best, isl, dist_m)
        row = {
            "id": iid,
            "name": name,
            "mapillaryId": rec["sourceRef"],
            "distanceM": dist_m,
            "imageConfidence": CONFIDENCE,
            "license": LICENSE,
            "sourcePageUrl": rec["sourcePageUrl"],
            "dry_run": args.dry_run,
        }
        report["adopted"].append(row)
        n_adopted += 1

        if args.dry_run:
            print(
                f"  ✓ [dry-run] {iid:45s} Mapillary {rec['sourceRef']} "
                f"@ {dist_m:.0f} m",
                flush=True,
            )
        else:
            isl.setdefault("images", []).append(rec)
            isl["image"] = rec["url"]
            isl["imageConfidence"] = CONFIDENCE
            print(
                f"  ✓ [{n_adopted}] {iid:45s} Mapillary {rec['sourceRef']} "
                f"@ {dist_m:.0f} m",
                flush=True,
            )

    report["attempted"] = n_attempted
    report["adopted_total"] = n_adopted
    report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")

    _save_json(CACHE, cache)
    _save_json(REPORT, report)

    if not args.dry_run and n_adopted:
        tmp = ISLANDS.with_suffix(ISLANDS.suffix + ".tmp")
        tmp.write_text(json.dumps(islands, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, ISLANDS)

    print()
    print(f"API works without token: {api_probe.get('works_without_token')}")
    print(f"Attempted: {n_attempted:,}")
    print(f"Adopted:   {n_adopted:,}" + (" (dry-run)" if args.dry_run else ""))
    print(f"Report   → {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
