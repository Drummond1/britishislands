#!/usr/bin/env python3
"""British Library Flickr — per-island text search (CC-PD / Commons only).

Unlike tag-feed scans in ``enrich_images_archive_nls.py``, this script runs
``flickr.photos.search`` against the BL Commons account (``12403504@N02``) for
**every** named photoless island name. Only Flickr licence id **7** (no known
copyright restrictions) is accepted.

Requires ``FLICKR_API_KEY`` in ``.env.local`` — register at
https://www.flickr.com/services/api/misc.api_keys.html

Dual-signal: island name in title/description/tags **and** photo geo within
15 km (5 km for generic English island names).

Run::

    python3 scripts/enrich_images_bl_flickr_deep.py --named-only --limit 400
    python3 scripts/enrich_images_bl_flickr_deep.py --dry-run --test iona

Outputs (staging only)::

    data/staging/adoptions/bl-flickr-deep.json
    data/cache_bl_flickr_deep.json
    data/image_enrichment_bl_flickr_deep_report.json
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
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
STAGING = DATA / "staging" / "adoptions" / "bl-flickr-deep.json"
CACHE = DATA / "cache_bl_flickr_deep.json"
REPORT = DATA / "image_enrichment_bl_flickr_deep_report.json"
ENV_LOCAL = ROOT / ".env.local"

FLICKR_REST = "https://www.flickr.com/services/rest/"
FLICKR_BL_NSID = "12403504@N02"
# Licence 7 = No known copyright restrictions (Flickr Commons / PD policy)
FLICKR_PD_LICENSE = "7"
USER_AGENT = "isles-of-britain/0.1 bl-flickr-deep-enrichment"
DEFAULT_DELAY_S = 1.2
DEFAULT_LIMIT = 400
FLICKR_PER_PAGE = 25
SOURCE = "bl-flickr-deep"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from enrich_images_v5 import (  # noqa: E402
    _haversine_km,
    _load,
    _load_named_index_ids,
    _mentions,
    _name_variants,
    _save,
    _strip_html,
)
from photo_staging_dual import (  # noqa: E402
    dual_signal_ok,
    island_lon,
    load_dotenv,
    looks_like_non_photo,
    make_adoption,
    save_staging,
)


def _flickr_rest(method: str, api_key: str, **kwargs: Any) -> dict:
    params: dict[str, Any] = {
        "method": method,
        "api_key": api_key,
        "format": "json",
        "nojsoncallback": 1,
    }
    params.update(kwargs)
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{FLICKR_REST}?{qs}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("stat") != "ok":
        raise RuntimeError(data.get("message") or data)
    return data


def _save_cache(cache: dict) -> None:
    payload = json.dumps(cache, ensure_ascii=False, separators=(",", ":"))
    tmp = CACHE.with_suffix(CACHE.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, CACHE)


def _search_text(island: dict) -> str:
    return (island.get("name") or "").strip()


def fetch_bl_photos(
    island: dict,
    api_key: str,
    cache: dict,
    delay_s: float,
) -> list[dict]:
    iid = island.get("id") or ""
    if iid in cache:
        entry = cache[iid]
        if isinstance(entry, dict) and isinstance(entry.get("photos"), list):
            return entry["photos"]

    text = _search_text(island)
    if len(text) < 3:
        cache[iid] = {"text": text, "photos": [], "reason": "name-too-short"}
        _save_cache(cache)
        return []

    try:
        data = _flickr_rest(
            "flickr.photos.search",
            api_key,
            user_id=FLICKR_BL_NSID,
            text=text,
            license=FLICKR_PD_LICENSE,
            content_type=1,
            media="photos",
            per_page=FLICKR_PER_PAGE,
            extras="url_m,url_l,license,owner_name,geo,description,tags",
        )
    except Exception as exc:
        print(f"  BL Flickr search failed for {iid}: {exc!r}", file=sys.stderr)
        cache[iid] = {"text": text, "error": repr(exc), "photos": []}
        _save_cache(cache)
        time.sleep(delay_s)
        return []

    photos = data.get("photos", {}).get("photo") or []
    if isinstance(photos, dict):
        photos = [photos]
    cache[iid] = {
        "text": text,
        "nsid": FLICKR_BL_NSID,
        "license": FLICKR_PD_LICENSE,
        "fetched": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "photos": photos,
    }
    _save_cache(cache)
    time.sleep(delay_s)
    return photos


def _photo_url(photo: dict) -> str:
    url = (photo.get("url_l") or photo.get("url_m") or "").strip()
    if url and "_m." in url:
        return url.replace("_m.", "_b.")
    return url


def build_image_record(photo: dict) -> dict | None:
    if str(photo.get("license") or "").strip() != FLICKR_PD_LICENSE:
        return None
    photo_id = str(photo.get("id") or "").strip()
    if not photo_id:
        return None
    title = (photo.get("title") or "").strip()
    if looks_like_non_photo(title):
        return None
    url = _photo_url(photo)
    if not url.startswith("http"):
        return None
    owner = (photo.get("owner") or "").strip()
    page = (
        f"https://www.flickr.com/photos/{owner}/{photo_id}"
        if owner
        else f"https://www.flickr.com/photo.gne?id={photo_id}"
    )
    desc = _strip_html(photo.get("description", "") or "")
    return {
        "url": url,
        "source": SOURCE,
        "sourceRef": f"bl:{photo_id}",
        "sourcePageUrl": page,
        "license": "No known copyright restrictions",
        "licenseUrl": "https://www.flickr.com/commons/usage/",
        "attribution": (
            f"\"{title or photo_id}\" — The British Library via Flickr Commons "
            "(no known copyright restrictions)"
        ),
        "caption": title or desc[:120],
    }


def pick_candidate(
    island: dict,
    photos: list[dict],
    rejected: list[dict],
) -> tuple[dict, dict[str, Any]] | None:
    best: tuple[float, dict, dict[str, Any]] | None = None

    for photo in photos:
        if str(photo.get("license") or "").strip() != FLICKR_PD_LICENSE:
            rejected.append({
                "id": island.get("id"),
                "photo_id": photo.get("id"),
                "reason": "not-licence-7-pd",
            })
            continue

        title = (photo.get("title") or "").strip()
        desc = _strip_html(photo.get("description", "") or "")
        tags = (photo.get("tags") or "").replace(" ", " ")
        blob = f"{desc} {tags}"

        try:
            rlat = float(photo.get("latitude"))
            rlon = float(photo.get("longitude"))
        except (TypeError, ValueError):
            rlat, rlon = None, None

        ok, verification = dual_signal_ok(
            island,
            title=title,
            blob=blob,
            result_lat=rlat,
            result_lon=rlon,
            mentions_fn=_mentions,
            name_variants_fn=_name_variants,
            haversine_km_fn=_haversine_km,
        )
        if not ok:
            rejected.append({
                "id": island.get("id"),
                "photo_id": photo.get("id"),
                "reason": verification.get("reason"),
                "title": title[:120],
            })
            continue

        rec = build_image_record(photo)
        if not rec:
            continue
        dist = float(verification.get("distance_km") or 999)
        if best is None or dist < best[0]:
            best = (dist, rec, verification)

    if best is None:
        return None
    _, rec, verification = best
    return rec, verification


def main() -> int:
    load_dotenv(ENV_LOCAL)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--named-only", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Max islands to attempt (default {DEFAULT_LIMIT}).",
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--delay", type=float, default=DEFAULT_DELAY_S)
    p.add_argument("--test", default="", help="Single island id.")
    args = p.parse_args()
    delay_s = max(0.0, float(args.delay))

    flickr_key = os.environ.get("FLICKR_API_KEY", "").strip()
    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    pending = [i for i in islands if not (i.get("images") or [])]
    if args.named_only:
        named_ids = _load_named_index_ids()
        if named_ids:
            before = len(pending)
            pending = [i for i in pending if i.get("id") in named_ids]
            print(f"  named-only: {len(pending):,} of {before:,} without images", flush=True)
    if args.test:
        pending = [i for i in islands if i.get("id") == args.test]
    if args.limit:
        pending = pending[: args.limit]

    cache = _load(CACHE)
    adoptions: list[dict] = []
    report: dict[str, Any] = {
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "script": "enrich_images_bl_flickr_deep.py",
        "source": SOURCE,
        "bl_flickr_nsid": FLICKR_BL_NSID,
        "license_filter": "Flickr id 7 (PD / no known copyright restrictions)",
        "args": vars(args),
        "flickr_api_key_set": bool(flickr_key),
        "dual_signal": "name_match AND geo_match required",
        "attempts": len(pending),
        "staged_by_source": {SOURCE: 0},
        "adopted": [],
        "rejected": [],
        "skipped": [],
    }

    if not flickr_key:
        report["skipped"].append(
            "FLICKR_API_KEY unset — flickr.photos.search requires a key; "
            "tag feeds cannot text-search the BL collection per island."
        )
        print("WARN: FLICKR_API_KEY unset — no BL deep search", file=sys.stderr)
        report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        report["staged_count"] = 0
        report["staged_by_source"][SOURCE] = 0
        if not args.dry_run:
            save_staging(STAGING, [])
        _save(REPORT, report)
        print(f"Attempts: {len(pending):,}")
        print(f"Staged ({SOURCE}): 0")
        print(0)
        return 0

    n_staged = 0
    for n, isl in enumerate(pending, 1):
        photos = fetch_bl_photos(isl, flickr_key, cache, delay_s)
        picked = pick_candidate(isl, photos, report["rejected"])
        if picked:
            rec, verification = picked
            adoptions.append(make_adoption(isl, rec, verification, source_label=SOURCE))
            n_staged += 1
            report["adopted"].append({
                "id": isl["id"],
                "name": isl.get("name", ""),
                "distance_km": verification.get("distance_km"),
                "url": rec.get("url"),
            })
            print(
                f"  ✓ {isl['id']:40s} {verification.get('distance_km')} km",
                flush=True,
            )
        if n % 50 == 0:
            print(f"  … {n}/{len(pending)} attempts; staged={n_staged}", flush=True)

    if not args.dry_run:
        save_staging(STAGING, adoptions)

    report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    report["staged_count"] = n_staged
    report["staged_by_source"][SOURCE] = n_staged
    _save(REPORT, report)

    print()
    print(f"Attempts: {len(pending):,}")
    print(f"Staged ({SOURCE}): {n_staged:,}")
    print(n_staged)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
