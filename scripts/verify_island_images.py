#!/usr/bin/env python3
"""Audit lead photos in islands.json and assign confidence scores (0–100).

Reuses name-match and geo-verification helpers from enrich_images_v5.py.

Run::

    python3 scripts/verify_island_images.py
    python3 scripts/verify_island_images.py --min-confidence 90
    python3 scripts/verify_island_images.py --fix-suspect --min-confidence 85

Outputs::

    data/image_verification_report.json
    data/islands.json.before-verify   (only when --fix-suspect)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
BACKUP = DATA / "islands.json.before-verify"
REPORT = DATA / "image_verification_report.json"
CACHE_COMMONS = DATA / "cache_commons.json"
CACHE_COMMONS_GEO = DATA / "cache_commons_geo.json"

# Import shared verification helpers from v5 (same directory).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from enrich_images_v5 import (  # noqa: E402
    _canon,
    _filename_from_commons_url,
    _haversine_km,
    _mentions,
    _name_variants,
    _passes_geo_anchor,
)

# Base confidence by source type (before dynamic adjustments).
BASE_SCORES: dict[str, int] = {
    "wikidata": 95,
    "wikidata-p18": 95,
    "wikipedia": 90,
    "osm-wikipedia": 90,
    "osm-image-tag": 92,
    "osm-commons-file": 92,
    "osm-commons-category": 85,
    "commons-text-search": 88,  # adjusted down when geo fails
    "commons-geosearch": 70,  # adjusted up/down by verification
    "curated": 98,
    "geograph": 90,
    "commons-category": 85,
}

NO_NAME_MATCH_PENALTY = 15  # osm-commons-category / commons-category → 70


def _load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _lead_image(island: dict) -> dict | None:
    imgs = island.get("images") or []
    if imgs:
        return imgs[0]
    url = (island.get("image") or "").strip()
    if url:
        return {"url": url, "source": "legacy-image-field"}
    return None


def _filename_from_image(img: dict) -> str:
    spu = (img.get("sourcePageUrl") or "").strip()
    if "/wiki/File:" in spu:
        return urllib.parse.unquote(spu.split("/wiki/File:", 1)[1])
    fn = _filename_from_commons_url(img.get("url") or "")
    if fn:
        return fn
    fn = _filename_from_commons_url(img.get("fullUrl") or "")
    if fn:
        return fn
    cap = (img.get("caption") or "").strip()
    if cap and ".jpg" in cap.lower():
        m = re.search(r"([^/\\]+\.(?:jpg|jpeg|png|webp))", cap, re.I)
        if m:
            return m.group(1)
    return ""


def _name_matched(island: dict, img: dict) -> bool:
    variants = _name_variants(island)
    if not variants:
        return False
    fname = _filename_from_image(img)
    caption = img.get("caption") or ""
    return _mentions(fname, variants) or _mentions(caption, variants)


def _parse_geosearch_source_ref(source_ref: str) -> tuple[float, float, int] | None:
    """Parse ``lat,lng;radius_m`` from v3-style sourceRef."""
    if not source_ref or ";" not in source_ref:
        return None
    coord_part, radius_part = source_ref.rsplit(";", 1)
    if "," not in coord_part:
        return None
    try:
        lat_s, lon_s = coord_part.split(",", 1)
        return float(lat_s), float(lon_s), int(radius_part)
    except (ValueError, TypeError):
        return None


def _geosearch_dist_m(
    island: dict,
    img: dict,
    geo_cache: dict,
) -> float | None:
    """Estimate file distance (metres) from geosearch cache or island centroid."""
    fname_raw = _filename_from_image(img)
    if not fname_raw:
        return None
    target = _canon(f"File:{fname_raw}")

    lat = island.get("lat")
    lon = island.get("lng") if island.get("lng") is not None else island.get("lon")
    if lat is None or lon is None:
        return None

    keys: list[str] = []
    sr = (img.get("sourceRef") or "").strip()
    parsed = _parse_geosearch_source_ref(sr)
    if parsed:
        keys.append(sr)
    for radius in (800, 1000, 1500):
        keys.append(f"{float(lat):.4f},{float(lon):.4f};{radius}")

    seen: set[str] = set()
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        hits = geo_cache.get(key) or []
        for hit in hits:
            title = _canon(hit.get("title") or "")
            if title == target:
                dist = hit.get("dist")
                if isinstance(dist, (int, float)):
                    return float(dist)

    # Fallback: haversine from search centre in sourceRef to island (usually ~0).
    if parsed:
        ref_lat, ref_lon, _ = parsed
        return _haversine_km(float(lat), float(lon), ref_lat, ref_lon) * 1000.0

    return None


def _commons_meta_for_image(img: dict, commons_cache: dict) -> dict:
    fname = _filename_from_image(img)
    if not fname:
        return {}
    return commons_cache.get(_canon(f"File:{fname}"), {})


def _text_search_passes_geo(
    island: dict,
    img: dict,
    commons_cache: dict,
) -> tuple[bool, str]:
    meta = _commons_meta_for_image(img, commons_cache)
    fname = _filename_from_image(img)
    # Without cached coords we rely on caption/category anchors only.
    ok, reason = _passes_geo_anchor(island, None, meta, max_km=15.0)
    if ok:
        return True, reason
    # If we had coords in cache we'd use them — geo cache is geosearch-only.
    if not meta:
        return False, "no-commons-cache-metadata"
    return False, reason


def score_lead_image(
    island: dict,
    img: dict,
    commons_cache: dict,
    geo_cache: dict,
) -> tuple[int, list[str], bool]:
    """Return (confidence 0–100, reasons, is_suspect_for_review)."""
    source = (img.get("source") or "unknown").strip()
    reasons: list[str] = []
    suspect = bool(img.get("suspect"))

    if source == "legacy-image-field":
        return 50, ["legacy top-level image field without provenance"], True

    if source not in BASE_SCORES:
        return 45, [f"unrecognised source type: {source}"], True

    confidence = BASE_SCORES[source]
    reasons.append(f"base score for {source}: {confidence}")

    if source in ("osm-commons-category", "commons-category"):
        if _name_matched(island, img):
            reasons.append("island name found in filename/caption")
        else:
            confidence -= NO_NAME_MATCH_PENALTY
            reasons.append("no island name match in filename/caption (−15)")
            suspect = True

    elif source == "commons-text-search":
        if not _name_matched(island, img):
            confidence = 60
            reasons.append("no island name match in filename/caption → 60")
            suspect = True
        else:
            ok, geo_reason = _text_search_passes_geo(island, img, commons_cache)
            if ok:
                confidence = 88
                reasons.append(f"geo verification passed: {geo_reason}")
            else:
                confidence = 60
                reasons.append(f"geo verification failed: {geo_reason}")
                suspect = True

    elif source == "commons-geosearch":
        if suspect or img.get("suspect") is True:
            confidence = 75
            reasons.append("explicit suspect flag → 75")
        elif _name_matched(island, img):
            dist_m = _geosearch_dist_m(island, img, geo_cache)
            if dist_m is not None and dist_m <= 500:
                confidence = 85
                reasons.append(
                    f"name match + estimated distance {dist_m:.0f} m ≤ 500 m → 85"
                )
            elif dist_m is not None:
                confidence = 70
                reasons.append(
                    f"name match but estimated distance {dist_m:.0f} m > 500 m → 70"
                )
                suspect = True
            else:
                confidence = 70
                reasons.append("name match but distance unknown → 70")
                suspect = True
        else:
            confidence = 70
            reasons.append("no island name match in filename/caption → 70")
            suspect = True

    confidence = max(0, min(100, confidence))
    return confidence, reasons, suspect


def _band(confidence: int) -> str:
    if confidence >= 90:
        return "gte90"
    if confidence >= 80:
        return "80-89"
    return "lt80"


def audit_islands(
    islands: list[dict],
    min_confidence: int,
    commons_cache: dict,
    geo_cache: dict,
) -> dict:
    bands = {"gte90": 0, "80-89": 0, "lt80": 0}
    by_source: dict[str, int] = {}
    below_90: list[dict] = []
    suspect_review: list[dict] = []
    scored: list[dict] = []

    for island in islands:
        lead = _lead_image(island)
        if not lead:
            continue

        confidence, reasons, suspect = score_lead_image(
            island, lead, commons_cache, geo_cache
        )
        source = lead.get("source") or "unknown"
        by_source[source] = by_source.get(source, 0) + 1
        bands[_band(confidence)] += 1

        entry = {
            "id": island.get("id"),
            "name": island.get("name"),
            "source": source,
            "confidence": confidence,
            "reasons": reasons,
            "url": lead.get("url") or island.get("image"),
            "filename": _filename_from_image(lead),
        }
        scored.append(entry)

        if confidence < 90:
            below_90.append(entry)

        if suspect or lead.get("suspect") or confidence < 80:
            suspect_review.append({**entry, "suspect": True})

    below_threshold = [e for e in scored if e["confidence"] < min_confidence]

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "minConfidence": min_confidence,
        "summary": {
            "totalWithImages": len(scored),
            "bands": bands,
            "bySource": dict(sorted(by_source.items(), key=lambda x: -x[1])),
            "belowThreshold": len(below_threshold),
        },
        "below90": below_90,
        "belowThreshold": below_threshold,
        "suspectReview": suspect_review,
    }


def _remove_lead_image(island: dict) -> bool:
    """Remove lead photo; return True if island was modified."""
    imgs = island.get("images") or []
    if imgs:
        island["images"] = imgs[1:]
        if island["images"]:
            island["image"] = island["images"][0].get("url") or ""
            if "primary" not in island["images"][0]:
                island["images"][0]["primary"] = True
        else:
            island.pop("images", None)
            island.pop("image", None)
        return True
    if island.get("image"):
        island.pop("image", None)
        return True
    return False


def _should_remove(lead: dict, confidence: int, min_confidence: int) -> bool:
    if lead.get("suspect"):
        return True
    return confidence < min_confidence


def apply_fixes(
    islands: list[dict],
    min_confidence: int,
    commons_cache: dict,
    geo_cache: dict,
) -> int:
    if ISLANDS.exists():
        shutil.copy2(ISLANDS, BACKUP)
        print(f"Backup written → {BACKUP}", file=sys.stderr)

    removed = 0
    for island in islands:
        lead = _lead_image(island)
        if not lead:
            continue
        confidence, _, _ = score_lead_image(island, lead, commons_cache, geo_cache)
        if _should_remove(lead, confidence, min_confidence):
            if _remove_lead_image(island):
                removed += 1

    tmp = ISLANDS.with_suffix(ISLANDS.suffix + ".tmp")
    tmp.write_text(
        json.dumps(islands, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, ISLANDS)
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit lead photos in islands.json and score confidence."
    )
    parser.add_argument(
        "--min-confidence",
        type=int,
        default=90,
        help="Flag islands below this confidence (default: 90)",
    )
    parser.add_argument(
        "--fix-suspect",
        action="store_true",
        help="Remove suspect or below-threshold lead images (creates backup)",
    )
    args = parser.parse_args()

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    commons_cache = _load_json(CACHE_COMMONS)
    geo_cache = _load_json(CACHE_COMMONS_GEO)

    report = audit_islands(
        islands, args.min_confidence, commons_cache, geo_cache
    )

    if args.fix_suspect:
        removed = apply_fixes(
            islands, args.min_confidence, commons_cache, geo_cache
        )
        report["fixSuspect"] = {
            "removed": removed,
            "backup": str(BACKUP.relative_to(ROOT)),
        }

    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    s = report["summary"]
    print(f"Islands with lead photo: {s['totalWithImages']}", file=sys.stderr)
    print(
        f"Confidence bands: ≥90={s['bands']['gte90']}  "
        f"80–89={s['bands']['80-89']}  <80={s['bands']['lt80']}",
        file=sys.stderr,
    )
    print(
        f"Below --min-confidence {args.min_confidence}: {s['belowThreshold']}",
        file=sys.stderr,
    )
    print(f"Suspect / review list: {len(report['suspectReview'])}", file=sys.stderr)
    print(f"Report → {REPORT}", file=sys.stderr)

    if args.fix_suspect:
        print(f"Removed {report['fixSuspect']['removed']} lead images", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
