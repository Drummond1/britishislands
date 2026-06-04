#!/usr/bin/env python3
"""Bulk Overpass harvest of OSM photo tags for named photoless islands.

Fetches ``image``, ``wikimedia_commons``, ``wikipedia`` / ``wikipedia:*``,
and ``wikidata`` in tiled bbox queries (one curl POST per tile), then applies
``enrich_images_v5.try_osm_tags`` for adoption candidates.

Highest-confidence staging: direct ``File:`` on ``wikimedia_commons`` or
``image`` URL on allowed hosts (Commons / Geograph). Wikipedia lead images and
Commons categories are medium confidence.

Run::

    python3 scripts/enrich_images_osm_bulk.py
    python3 scripts/enrich_images_osm_bulk.py --limit 50
    python3 scripts/enrich_images_osm_bulk.py --cache-only
    python3 scripts/enrich_images_osm_bulk.py --test sgeir-bhuidhe

Outputs (default: staging only)::

    data/staging/adoptions/osm-bulk.json
    data/cache_osm_tags_bulk.json
    data/image_enrichment_osm_bulk_report.json

Reuses ``data/cache_osm_tags_v5.json`` keys when present; writes through to both
caches after each tile so reruns are resumable.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
STAGING = DATA / "staging" / "adoptions" / "osm-bulk.json"
REPORT = DATA / "image_enrichment_osm_bulk_report.json"
CACHE_BULK = DATA / "cache_osm_tags_bulk.json"

# UK + Ireland + Crown Dependencies + fringe (same as highpoints script).
BBOX = (49.0, -11.5, 61.5, 2.5)  # south, west, north, east
TILE_LAT = 1.5
TILE_LNG = 2.0

WIKI_LANG_KEYS = (
    "wikipedia",
    "wikipedia:en",
    "wikipedia:gd",
    "wikipedia:cy",
    "wikipedia:ga",
    "wikipedia:kw",
    "wikipedia:gv",
    "wikipedia:fr",
)

HIGH_SOURCES = frozenset({
    "osm-image-tag",
    "geograph",
    "osm-commons-file",
})

sys.path.insert(0, str(Path(__file__).resolve().parent))
from enrich_images_v5 import (  # noqa: E402
    CACHE_COMMONS,
    CACHE_OSM_TAGS,
    CACHE_WP_PI,
    DELAY_S,
    OVERPASS_ENDPOINTS,
    USER_AGENT,
    _atomic_write_islands,
    _load,
    _load_named_index_ids,
    _save,
    fetch_commons_meta,
    fetch_osm_extra_tags,
    fetch_wp_pageimages,
    try_osm_tags,
)

BACKUP = DATA / "islands.json.before-osm-bulk"


def _save_staging(adoptions: list[dict]) -> None:
    STAGING.parent.mkdir(parents=True, exist_ok=True)
    tmp = STAGING.with_suffix(STAGING.suffix + ".tmp")
    tmp.write_text(
        json.dumps(adoptions, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, STAGING)


def _island_lon(island: dict) -> float | None:
    lng = island.get("lng")
    if lng is None:
        lng = island.get("lon")
    if isinstance(lng, (int, float)):
        return float(lng)
    return None


def _osm_key(island: dict) -> str | None:
    osm_type = (island.get("osmType") or "").lower()
    osm_id = str(island.get("osmId") or "").strip()
    if osm_type not in ("node", "way", "relation") or not osm_id:
        return None
    return f"{osm_type}/{osm_id}"


def _has_photo_tags(entry: dict) -> bool:
    return bool(
        (entry.get("image") or "").strip()
        or (entry.get("wikimedia_commons") or "").strip()
        or (entry.get("wikipedia") or "").strip()
    )


def _extract_photo_tags(tags: dict[str, str]) -> dict[str, str]:
    wp = ""
    for k in WIKI_LANG_KEYS:
        if tags.get(k):
            wp = tags[k]
            break
    return {
        "wikipedia": wp,
        "wikimedia_commons": tags.get("wikimedia_commons") or "",
        "image": tags.get("image") or "",
        "wikidata": tags.get("wikidata") or "",
    }


def _bbox_tiles() -> list[tuple[float, float, float, float]]:
    s_lat, w_lng, n_lat, e_lng = BBOX
    tiles: list[tuple[float, float, float, float]] = []
    lat = s_lat
    while lat < n_lat:
        lng = w_lng
        while lng < e_lng:
            tiles.append((
                lat,
                lng,
                min(lat + TILE_LAT, n_lat),
                min(lng + TILE_LNG, e_lng),
            ))
            lng += TILE_LNG
        lat += TILE_LAT
    return tiles


def _bbox_overpass_query(s: float, w: float, n: float, e: float) -> str:
    bb = f"{s},{w},{n},{e}"
    parts: list[str] = []
    for kind in ("node", "way", "relation"):
        parts.append(f'{kind}({bb})["image"];')
        parts.append(f'{kind}({bb})["wikimedia_commons"];')
        parts.append(f'{kind}({bb})["wikidata"];')
        for wk in WIKI_LANG_KEYS:
            parts.append(f'{kind}({bb})["{wk}"];')
    return f"[out:json][timeout:120];({''.join(parts)});out tags;"


def _curl_overpass(query: str) -> dict | None:
    for ep in OVERPASS_ENDPOINTS:
        try:
            res = subprocess.run(
                [
                    "curl", "-sS", "--max-time", "180",
                    "-X", "POST",
                    "-A", USER_AGENT,
                    "-H", "Content-Type: application/x-www-form-urlencoded",
                    "--data-urlencode", f"data={query}",
                    ep,
                ],
                capture_output=True,
                text=True,
                timeout=200,
            )
        except subprocess.TimeoutExpired:
            print(f"  overpass {ep}: curl timed out", file=sys.stderr, flush=True)
            time.sleep(2)
            continue
        if res.returncode != 0:
            print(
                f"  overpass {ep}: rc={res.returncode} "
                f"stderr={res.stderr[:200]!r}",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(2)
            continue
        stdout = res.stdout or ""
        if not stdout.strip():
            print(
                f"  overpass {ep}: empty stdout stderr={res.stderr[:200]!r}",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(2)
            continue
        try:
            return json.loads(stdout)
        except json.JSONDecodeError as exc:
            print(
                f"  overpass {ep}: JSON {exc!r} body[:200]={stdout[:200]!r}",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(2)
            continue
    return None


def fetch_osm_tags_bulk_tiles(
    target_keys: set[str],
    cache_bulk: dict,
    cache_v5: dict,
    *,
    cache_only: bool,
    force: bool,
) -> dict[str, dict]:
    """Populate tag dicts for ``target_keys`` via tiled bbox Overpass."""
    merged = dict(cache_bulk)
    for k, v in cache_v5.items():
        if k in target_keys and k not in merged:
            merged[k] = v

    meta = cache_bulk.setdefault("meta", {})
    done_tiles = set(tuple(t) for t in meta.get("tilesDone", []))
    tiles = _bbox_tiles()
    print(f"  Overpass tiles: {len(tiles)} (lat×lng grid)", flush=True)

    for i, (s, w, n, e) in enumerate(tiles):
        if (s, w, n, e) in done_tiles and not force:
            continue
        if cache_only:
            continue
        q = _bbox_overpass_query(s, w, n, e)
        print(
            f"  tile {i + 1}/{len(tiles)} bbox {s:.2f},{w:.2f},{n:.2f},{e:.2f}",
            flush=True,
        )
        payload = _curl_overpass(q)
        if payload is None:
            print("  WARN: tile fetch failed; continuing", file=sys.stderr, flush=True)
            time.sleep(DELAY_S)
            continue

        n_matched = 0
        for el in payload.get("elements") or []:
            t = el.get("type")
            i_ = str(el.get("id") or "")
            k = f"{t}/{i_}"
            if k not in target_keys:
                continue
            tags = _extract_photo_tags(el.get("tags") or {})
            if not any(tags.values()):
                continue
            merged[k] = tags
            cache_bulk[k] = tags
            cache_v5[k] = tags
            n_matched += 1

        done_tiles.add((s, w, n, e))
        meta["tilesDone"] = [list(t) for t in sorted(done_tiles)]
        meta["fetchedAt"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        _save(CACHE_BULK, cache_bulk)
        _save(CACHE_OSM_TAGS, cache_v5)
        print(
            f"    elements={len(payload.get('elements') or [])} "
            f"matched_targets={n_matched}",
            flush=True,
        )
        time.sleep(DELAY_S)

    return {k: merged.get(k, {}) for k in target_keys}


def fetch_osm_tags_by_id_fallback(
    pending: list[dict],
    cache_osm: dict,
    *,
    cache_only: bool,
) -> int:
    """v5-style ``node/way/relation(id:…)`` batches for keys still missing photo tags."""
    if cache_only:
        return 0
    specs: list[tuple[str, str]] = []
    for isl in pending:
        ok = _osm_key(isl)
        if not ok:
            continue
        entry = cache_osm.get(ok) or {}
        if _has_photo_tags(entry):
            continue
        t, i = ok.split("/", 1)
        specs.append((t, i))
    if not specs:
        return 0
    print(
        f"  ID fallback: {len(specs):,} OSM elements without photo tags after bbox",
        flush=True,
    )
    # v5 only queries keys absent from cache; drop stale empty rows so we refetch.
    for t, i in specs:
        k = f"{t}/{i}"
        if not _has_photo_tags(cache_osm.get(k) or {}):
            cache_osm.pop(k, None)
    fetch_osm_extra_tags(specs, cache_osm)
    return len(specs)


def _confidence_for_record(rec: dict) -> tuple[str, str]:
    src = (rec.get("source") or "").strip()
    if src in HIGH_SOURCES:
        if src == "geograph":
            return "high", "OSM image= Geograph URL"
        if src == "osm-commons-file":
            return "high", "OSM wikimedia_commons File:"
        return "high", "OSM image= Commons URL"
    if src == "osm-wikipedia":
        return "medium", "OSM wikipedia= → Wikipedia lead image"
    if src == "osm-commons-category":
        return "medium", "OSM wikimedia_commons Category:"
    return "medium", f"OSM tag path ({src})"


def main() -> int:
    p = argparse.ArgumentParser(
        description="Bulk OSM tag Overpass + v5 try_osm_tags staging.",
    )
    p.add_argument(
        "--cache-only",
        action="store_true",
        help="Skip Overpass; use existing osm tag caches only.",
    )
    p.add_argument(
        "--skip-bbox",
        action="store_true",
        help="Skip tiled bbox Overpass (use after a prior bbox pass).",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Re-fetch all bbox tiles even if marked done.",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Write adopted images into islands.json (default: staging).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write staging or islands.json.",
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
        default=0,
        help="Stop after N pending islands (0 = all).",
    )
    p.add_argument(
        "--test",
        default="",
        help="Process only this island id.",
    )
    p.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip backup when --apply.",
    )
    p.add_argument(
        "--delay",
        type=float,
        default=None,
        metavar="SECONDS",
        help=f"Seconds between Overpass tiles (default {DELAY_S}).",
    )
    args = p.parse_args()
    use_staging = not args.apply

    if args.delay is not None:
        import enrich_images_v5 as v5_mod  # noqa: E402

        v5_mod.DELAY_S = max(0.0, float(args.delay))
        print(f"  API delay: {v5_mod.DELAY_S}s", flush=True)

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    if not isinstance(islands, list):
        print("FATAL: islands.json is not a list", file=sys.stderr)
        return 2

    pending = [i for i in islands if not (i.get("images") or [])]
    if args.named_only:
        named_ids = _load_named_index_ids()
        pending = [i for i in pending if i.get("id") in named_ids]
    pending = [i for i in pending if _osm_key(i)]
    if args.test:
        pending = [i for i in islands if i.get("id") == args.test]
    if args.limit:
        pending = pending[: args.limit]

    target_keys = {_osm_key(i) for i in pending if _osm_key(i)}
    print(
        f"Pending named photoless with OSM id: {len(pending):,} "
        f"({len(target_keys):,} unique OSM keys)",
        flush=True,
    )

    cache_bulk = _load(CACHE_BULK)
    cache_v5 = _load(CACHE_OSM_TAGS)
    cache_commons = _load(CACHE_COMMONS)
    cache_wp_pi = _load(CACHE_WP_PI)

    if not args.cache_only and not args.skip_bbox:
        fetch_osm_tags_bulk_tiles(
            target_keys,
            cache_bulk,
            cache_v5,
            cache_only=False,
            force=args.force,
        )
    elif args.skip_bbox:
        print("  --skip-bbox: skipping tiled Overpass", flush=True)
    else:
        print("  --cache-only: skipping Overpass", flush=True)

    fetch_osm_tags_by_id_fallback(
        pending,
        cache_v5,
        cache_only=args.cache_only,
    )
    for k in target_keys:
        if k in cache_v5:
            cache_bulk[k] = cache_v5[k]

    # Merge caches for try_osm_tags (v5 reads cache_osm dict in-memory).
    cache_osm = dict(cache_v5)
    for k in target_keys:
        if k in cache_bulk and isinstance(cache_bulk.get(k), dict):
            cache_osm[k] = cache_bulk[k]

    adoptions: list[dict] = []
    report: dict[str, Any] = {
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "args": {**vars(args), "staging": use_staging},
        "staging_path": str(STAGING.relative_to(ROOT)),
        "pending_with_osm": len(pending),
        "target_osm_keys": len(target_keys),
        "cache_only": args.cache_only,
        "adopted": [],
        "rejected": [],
    }

    if (
        args.apply
        and not args.dry_run
        and not args.no_backup
        and not BACKUP.exists()
    ):
        BACKUP.write_text(
            json.dumps(islands, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Backup → {BACKUP.relative_to(ROOT)}", flush=True)

    n_attempted = 0
    n_staged = 0
    pending_set = {i.get("id") for i in pending}

    for isl in islands:
        if isl.get("id") not in pending_set:
            continue
        n_attempted += 1
        ok = _osm_key(isl)
        tags = cache_osm.get(ok or "", {}) if ok else {}
        if not _has_photo_tags(tags):
            report["rejected"].append({
                "id": isl.get("id"),
                "reason": "no photo tags in cache after bulk fetch",
            })
            continue

        rec = try_osm_tags(isl, cache_osm, cache_commons, cache_wp_pi)
        if not rec:
            report["rejected"].append({
                "id": isl.get("id"),
                "reason": "try_osm_tags returned None",
                "tags": tags,
            })
            continue

        conf, reason = _confidence_for_record(rec)
        entry = {
            "id": isl.get("id"),
            "image_record": rec,
            "confidence": conf,
            "reason": reason,
        }
        adoptions.append(entry)
        n_staged += 1
        if args.apply and not args.dry_run:
            isl.setdefault("images", []).append(rec)
        print(
            f"  ✓ {isl.get('id', ''):45s} [{conf}] "
            f"{rec.get('source', '')} {rec.get('sourcePageUrl', '')[:60]}",
            flush=True,
        )
        report["adopted"].append({
            "id": isl.get("id"),
            "name": isl.get("name"),
            "confidence": conf,
            "source": rec.get("source"),
            "sourcePageUrl": rec.get("sourcePageUrl"),
        })

    if not args.dry_run:
        if use_staging:
            _save_staging(adoptions)
        if args.apply:
            _atomic_write_islands(islands)
        _save(CACHE_OSM_TAGS, cache_osm)
        _save(CACHE_BULK, cache_bulk)

    report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    report["attempted"] = n_attempted
    report["staged_total"] = n_staged
    report["dry_run"] = args.dry_run
    _save(REPORT, report)

    print()
    print(f"Attempted:  {n_attempted:,}")
    print(f"Staged:     {n_staged:,}")
    if use_staging and not args.dry_run:
        print(f"Staging  → {STAGING.relative_to(ROOT)} ({len(adoptions):,} rows)")
    print(f"Report   → {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
