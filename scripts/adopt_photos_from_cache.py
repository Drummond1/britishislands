#!/usr/bin/env python3
"""Adopt lead photos from existing v5 caches only — no live API calls.

Targets named atlas islands (``islands_index.json`` ids by default) that still
lack ``images[]``. Sources and priority match v5 high-confidence mode:

  1. cache_p18_refresh + cache_wp_pageimages_v5 + cache_commons → Wikidata/WP
  2. cache_osm_tags_v5 → OSM tags (cache miss on element → skip source)
  3. cache_commons_text + cache_commons → text-search with 5 km geo rules

Run::

    python3 scripts/adopt_photos_from_cache.py --named-only
    python3 scripts/adopt_photos_from_cache.py --dry-run --limit 50

Outputs::

    data/islands.json                              (mutated unless --dry-run)
    data/islands.json.before-cache-adopt           (backup)
    data/cache_adopt_report.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
BACKUP = DATA / "islands.json.before-cache-adopt"
REPORT = DATA / "cache_adopt_report.json"

CACHE_P18 = DATA / "cache_p18_refresh.json"
CACHE_WP_PI = DATA / "cache_wp_pageimages_v5.json"
CACHE_OSM_TAGS = DATA / "cache_osm_tags_v5.json"
CACHE_COMMONS_TEXT = DATA / "cache_commons_text.json"
CACHE_COMMONS = DATA / "cache_commons.json"
CACHE_COMMONS_GEO = DATA / "cache_commons_geo.json"
CACHE_CATEGORY_MEMBERS = DATA / "cache_commons_categorymembers.json"
GEOSEARCH_MAX_KM = 0.5

TEXT_SEARCH_MAX_KM = 5.0

sys.path.insert(0, str(Path(__file__).resolve().parent))
from enrich_images_v5 import (  # noqa: E402
    HOST_ALLOW,
    _canon,
    _filename_from_commons_url,
    _haversine_km,
    _load,
    _load_named_index_ids,
    _looks_like_non_photo,
    _mentions,
    _name_variants,
    _parse_wikipedia_tag,
    _passes_geo_anchor,
    build_image_record_from_commons,
)


def _atomic_write_islands(payload: list) -> None:
    tmp = ISLANDS.with_suffix(ISLANDS.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, ISLANDS)


def _stamp_high(rec: dict) -> dict:
    out = dict(rec)
    out["imageConfidence"] = "high"
    out["verifiedAt"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return out


def _meta_from_cache(filenames: list[str], cache_commons: dict) -> dict[str, dict]:
    """Return commons metadata only when already present in cache."""
    out: dict[str, dict] = {}
    for f in filenames:
        key = _canon(f)
        m = cache_commons.get(key)
        if isinstance(m, dict) and m:
            out[key] = m
    return out


def _file_coords_from_commons_cache(fname: str, cache_commons: dict) -> tuple[float, float] | None:
    """GPS from cache_commons entry when lat/lon (or coords) were stored."""
    m = cache_commons.get(_canon(fname)) or {}
    if not isinstance(m, dict):
        return None
    lat = m.get("lat")
    lon = m.get("lon")
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        return float(lat), float(lon)
    coords = m.get("coords")
    if isinstance(coords, (list, tuple)) and len(coords) >= 2:
        try:
            return float(coords[0]), float(coords[1])
        except (TypeError, ValueError):
            pass
    return None


def try_p18_then_pageimages_cached(
    island: dict,
    cache_p18: dict,
    cache_wp_pi: dict,
    cache_commons: dict,
) -> dict | None:
    qid = (island.get("wikidata") or "").strip()
    if not re.match(r"^Q\d+$", qid):
        return None
    if qid not in cache_p18:
        return None
    bundle = cache_p18.get(qid) or {}
    p18 = bundle.get("p18", "") or ""
    enwiki = bundle.get("enwiki", "") or ""
    candidates: list[tuple[str, str, str]] = []
    if p18:
        candidates.append((p18, "wikidata", qid))
    if enwiki and enwiki in cache_wp_pi:
        pi = cache_wp_pi.get(enwiki, "") or ""
        if pi and pi != p18:
            candidates.append((pi, "wikipedia", enwiki.replace(" ", "_")))
    if not candidates:
        return None
    metas = _meta_from_cache([f for f, *_ in candidates], cache_commons)
    for fname, source, ref in candidates:
        if _looks_like_non_photo(fname):
            continue
        m = metas.get(_canon(fname), {})
        rec = build_image_record_from_commons(fname, m, source, ref)
        if rec:
            return rec
    return None


def try_osm_tags_cached(
    island: dict,
    cache_osm: dict,
    cache_commons: dict,
    cache_wp_pi: dict,
    cache_cat_members: dict,
) -> dict | None:
    osm_type = (island.get("osmType") or "").lower()
    osm_id = str(island.get("osmId") or "").strip()
    if osm_type not in ("node", "way", "relation") or not osm_id:
        return None
    key = f"{osm_type}/{osm_id}"
    if key not in cache_osm:
        return None
    tags = cache_osm.get(key) or {}

    img_url = (tags.get("image") or "").strip()
    if img_url:
        try:
            host = urllib.parse.urlparse(img_url).netloc.lower()
        except Exception:
            host = ""
        if host in HOST_ALLOW:
            if "commons.wikimedia.org" in host or "upload.wikimedia.org" in host:
                fname = _filename_from_commons_url(img_url)
                if fname and not _looks_like_non_photo(fname):
                    metas = _meta_from_cache([fname], cache_commons)
                    m = metas.get(_canon(fname), {})
                    rec = build_image_record_from_commons(
                        fname, m, "osm-image-tag", f"{osm_type}/{osm_id}"
                    )
                    if rec:
                        return rec
            elif "geograph" in host:
                m = re.search(r"/(\d+)\b", img_url)
                gid = m.group(1) if m else ""
                if gid:
                    return {
                        "url": img_url,
                        "source": "geograph",
                        "sourceRef": gid,
                        "sourcePageUrl": f"https://www.geograph.org.uk/photo/{gid}",
                        "license": "CC-BY-SA-2.0",
                        "attribution": "Photo via Geograph project (CC-BY-SA 2.0)",
                        "caption": "",
                    }

    wp = (tags.get("wikipedia") or "").strip()
    if wp:
        title = _parse_wikipedia_tag(wp)
        if title and title in cache_wp_pi:
            pi = cache_wp_pi.get(title, "") or ""
            if pi and not _looks_like_non_photo(pi):
                metas = _meta_from_cache([pi], cache_commons)
                m = metas.get(_canon(pi), {})
                rec = build_image_record_from_commons(
                    pi, m, "osm-wikipedia", f"{osm_type}/{osm_id}"
                )
                if rec:
                    return rec

    wc = (tags.get("wikimedia_commons") or "").strip()
    if wc:
        if wc.startswith("File:"):
            fname = _canon(wc)
            if not _looks_like_non_photo(fname):
                metas = _meta_from_cache([fname], cache_commons)
                m = metas.get(_canon(fname), {})
                rec = build_image_record_from_commons(
                    fname, m, "osm-commons-file", f"{osm_type}/{osm_id}"
                )
                if rec:
                    return rec
        elif wc.startswith("Category:"):
            cat_key = wc if wc.startswith("Category:") else f"Category:{wc}"
            members = cache_cat_members.get(cat_key)
            if not isinstance(members, list) or not members:
                return None
            metas = _meta_from_cache(
                [f for f in members if not _looks_like_non_photo(f)],
                cache_commons,
            )
            variants = _name_variants(island)
            best = ""
            best_score = -1
            for f in members:
                if _looks_like_non_photo(f):
                    continue
                m = metas.get(_canon(f), {})
                lic = (m.get("license") or "").strip()
                if not lic or "fair use" in lic.lower():
                    continue
                score = 0
                if "quality images" in (m.get("categories") or "").lower():
                    score += 5
                if "featured pictures" in (m.get("categories") or "").lower():
                    score += 10
                if _mentions(f, variants) or _mentions(m.get("caption", ""), variants):
                    score += 4
                w, h = m.get("width") or 0, m.get("height") or 0
                if w and h and w * h > 1_000_000:
                    score += 1
                if score > best_score:
                    best_score = score
                    best = f
            if best:
                m = metas.get(_canon(best), {})
                rec = build_image_record_from_commons(
                    best, m, "osm-commons-category", f"{osm_type}/{osm_id}"
                )
                if rec:
                    return rec
    return None


def try_commons_text_search_cached(
    island: dict,
    cache_commons: dict,
    cache_text: dict,
    report_rejected: list[dict[str, Any]],
) -> dict | None:
    name = (island.get("name") or "").strip()
    if len(name) < 4:
        return None
    archipelago = (island.get("archipelago") or "").strip()
    key = f"{name}|{archipelago}"
    if key not in cache_text:
        return None
    files = cache_text.get(key) or []
    if not files:
        return None
    keep = [f for f in files if not _looks_like_non_photo(f)]
    if not keep:
        return None
    candidates = keep[:5]
    metas = _meta_from_cache(candidates, cache_commons)
    variants = _name_variants(island)
    for f in candidates:
        m = metas.get(_canon(f), {})
        lic = (m.get("license") or "").strip()
        if not lic or "fair use" in lic.lower():
            continue
        if not (_mentions(f, variants) or _mentions(m.get("caption", ""), variants)):
            continue
        file_coords = _file_coords_from_commons_cache(f, cache_commons)
        ok, reason = _passes_geo_anchor(
            island, file_coords, m, max_km=TEXT_SEARCH_MAX_KM
        )
        if not ok:
            report_rejected.append({
                "id": island.get("id"),
                "source": "commons-text-search",
                "file": f,
                "reason": reason,
            })
            continue
        rec = build_image_record_from_commons(
            f, m, "commons-text-search", island["id"]
        )
        if rec:
            return rec
    return None


def try_commons_geosearch_cached(
    island: dict,
    cache_geo: dict,
    cache_commons: dict,
) -> dict | None:
    """Name-matched geosearch hits within 500 m from cache only."""
    lat = island.get("lat")
    lon = island.get("lng") if island.get("lng") is not None else island.get("lon")
    if lat is None or lon is None:
        return None
    variants = _name_variants(island)
    best: tuple[float, str, dict] | None = None
    for radius in (800, 1500):
        key = f"{float(lat):.4f},{float(lon):.4f};{radius}"
        hits = cache_geo.get(key) or []
        for h in hits:
            fname = _canon(h.get("title", ""))
            if _looks_like_non_photo(fname):
                continue
            m = cache_commons.get(fname) or {}
            if not (_mentions(fname, variants) or _mentions(m.get("caption", ""), variants)):
                continue
            try:
                d_km = _haversine_km(
                    float(lat), float(lon),
                    float(h.get("lat") or 0), float(h.get("lon") or 0),
                )
            except Exception:
                continue
            if d_km > GEOSEARCH_MAX_KM:
                continue
            lic = (m.get("license") or "").strip()
            if not lic or "fair use" in lic.lower():
                continue
            if best is None or d_km < best[0]:
                best = (d_km, fname, m)
    if not best:
        return None
    _, fname, m = best
    rec = build_image_record_from_commons(
        fname, m, "commons-geosearch", island["id"]
    )
    if rec:
        rec["imageConfidence"] = "medium-high"
    return rec


def main() -> int:
    p = argparse.ArgumentParser(
        description="Adopt lead photos from v5 caches only (no API calls).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute adoptions and report without writing islands.json.",
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
        help="Stop after considering N pending islands (0 = all).",
    )
    args = p.parse_args()

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    if not isinstance(islands, list):
        print("FATAL: islands.json is not a list", file=sys.stderr)
        return 2

    if not args.dry_run and not BACKUP.exists():
        BACKUP.write_text(
            json.dumps(islands, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Backup → {BACKUP.relative_to(ROOT)}")

    cache_p18 = _load(CACHE_P18)
    cache_wp_pi = _load(CACHE_WP_PI)
    cache_osm = _load(CACHE_OSM_TAGS)
    cache_text = _load(CACHE_COMMONS_TEXT)
    cache_commons = _load(CACHE_COMMONS)
    cache_geo = _load(CACHE_COMMONS_GEO)
    cache_cat_members = _load(CACHE_CATEGORY_MEMBERS)

    report: dict[str, Any] = {
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mode": "cache-only",
        "args": {
            "dry_run": args.dry_run,
            "named_only": args.named_only,
            "limit": args.limit,
        },
        "text_search_max_km": TEXT_SEARCH_MAX_KM,
        "input_total": len(islands),
        "pending_considered": 0,
        "adopted": [],
        "rejected": [],
    }

    pending = [i for i in islands if not (i.get("images") or [])]
    if args.named_only:
        named_ids = _load_named_index_ids()
        if named_ids:
            before = len(pending)
            pending = [i for i in pending if i.get("id") in named_ids]
            print(f"  named-only: {len(pending):,} of {before:,} without images",
                  flush=True)
    if args.limit:
        pending = pending[: args.limit]
    report["pending_considered"] = len(pending)
    print(f"Pending (cache adopt): {len(pending):,}", flush=True)

    pending_set = {i.get("id") for i in pending}
    n_adopted = 0
    n_attempted = 0

    def _try(island: dict) -> tuple[dict | None, str]:
        for label, fn in (
            ("p18", lambda: try_p18_then_pageimages_cached(
                island, cache_p18, cache_wp_pi, cache_commons)),
            ("osm-tags", lambda: try_osm_tags_cached(
                island, cache_osm, cache_commons, cache_wp_pi, cache_cat_members)),
            ("text-search", lambda: try_commons_text_search_cached(
                island, cache_commons, cache_text, report["rejected"])),
            ("geosearch", lambda: try_commons_geosearch_cached(
                island, cache_geo, cache_commons)),
        ):
            try:
                rec = fn()
            except Exception as exc:
                print(f"  {island.get('id')} {label} error: {exc!r}",
                      file=sys.stderr)
                continue
            if rec:
                if rec.get("imageConfidence") == "medium-high":
                    stamped = dict(rec)
                    stamped["verifiedAt"] = datetime.now(timezone.utc).replace(
                        microsecond=0
                    ).isoformat()
                    return stamped, label
                return _stamp_high(rec), label
        return None, ""

    for isl in islands:
        if isl.get("id") not in pending_set:
            continue
        n_attempted += 1
        rec, source_used = _try(isl)
        if rec:
            if not args.dry_run:
                isl.setdefault("images", []).append(rec)
            row = {
                "id": isl["id"],
                "name": isl.get("name", ""),
                "source": rec.get("source"),
                "via": source_used,
                "license": rec.get("license"),
                "sourcePageUrl": rec.get("sourcePageUrl"),
                "imageConfidence": rec.get("imageConfidence"),
                "verifiedAt": rec.get("verifiedAt"),
            }
            report["adopted"].append(row)
            n_adopted += 1
            print(
                f"  ✓ {isl['id']:45s} via {source_used:12s} → "
                f"{rec.get('source')} [{rec.get('imageConfidence')}]",
                flush=True,
            )
        else:
            report["rejected"].append({
                "id": isl["id"],
                "name": isl.get("name", ""),
                "reason": "no cache-backed candidate",
            })

    if not args.dry_run:
        _atomic_write_islands(islands)

    report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    report["attempted"] = n_attempted
    report["adopted_total"] = n_adopted
    report["dry_run"] = args.dry_run
    tmp = REPORT.with_suffix(REPORT.suffix + ".tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, REPORT)

    print()
    print(f"Attempted: {n_attempted:,}")
    print(f"Adopted:   {n_adopted:,}")
    print(f"Report   → {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
