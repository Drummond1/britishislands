#!/usr/bin/env python3
"""Name proposals from Commons geosearch title consensus (N10).

Reads ``data/cache_commons_geo.json`` (already fetched photo geosearches).
When ≥2 geotagged Commons titles near an unnamed centroid share a normalised
island-lexicon phrase, emit a Tier B proposal. Single strong File: titles that
look like a proper island name land as Tier C (review).

Run::

    python3 scripts/name_unnamed_photo_titles.py
    python3 scripts/name_unnamed_photo_titles.py --min-agree 2
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = DATA / "cache_commons_geo.json"
STAGING = DATA / "staging" / "name_proposals" / "photo-title-consensus.json"
REPORT = DATA / "name_proposals_photo_titles_report.json"

MORPHEME_RE = re.compile(
    r"\b(island|isle|islets?|holms?|holm|skerries|skerry|stacks?|stack|"
    r"eilean|eileanan|inis|inish|ynys|inch|oile[aá]n|crannog|ait|eyot|ey)\b",
    re.I,
)
FILE_RE = re.compile(r"^File:(.+?)(?:\.[A-Za-z0-9]+)?$", re.I)
NOISE_RE = re.compile(
    r"\b(from|view|looking|towards|near|geograph|commons|enclosure|"
    r"lighthouse|harbour|bay|beach|cliff|map|sign|kayaker|golf|course|"
    r"path|across|within|and the|in the|in lake|in loch|in lough)\b",
    re.I,
)
DESC_RE = re.compile(
    r"^(island|isle|islet|skerry|holm|rock)\b.*\b(in|on|at|within|near)\b",
    re.I,
)

sys.path.insert(0, str(ROOT / "scripts"))
from discovery import common as c  # noqa: E402
from name_staging_utils import (  # noqa: E402
    build_proposal,
    haversine_m,
    island_lon,
    is_usable_name,
    load_unnamed,
    save_staging,
)


def _norm(s: str) -> str:
    t = unicodedata.normalize("NFKD", s or "")
    t = t.encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9\s'-]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


GENERIC_LEAD_RE = re.compile(
    r"^(?:small|large|wooded|rocky|tiny|little)?\s*"
    r"(?:island|isle|islet|skerry|holm|rock|stack)s?\b",
    re.I,
)


def _title_to_name(title: str) -> str | None:
    raw = (title or "").strip()
    m = FILE_RE.match(raw)
    if m:
        raw = m.group(1).replace("_", " ").strip()
    # Drop trailing " - geograph.org.uk - NNNNN"
    raw = re.sub(r"\s*-\s*geograph\.org\.uk\s*-\s*\d+\s*$", "", raw, flags=re.I)
    raw = re.sub(r"\s*\(\d+\)\s*$", "", raw).strip()
    if not raw or not MORPHEME_RE.search(raw):
        return None
    if NOISE_RE.search(raw):
        return None
    if DESC_RE.match(raw):
        return None
    # Prefer a short clause containing the morpheme
    parts = re.split(r"\s[-–—|/]\s", raw)
    candidates = []
    for part in parts:
        part = part.strip()
        if (
            MORPHEME_RE.search(part)
            and 3 <= len(part) <= 50
            and is_usable_name(part)
            and not NOISE_RE.search(part)
            and not DESC_RE.match(part)
            and not GENERIC_LEAD_RE.match(part)
            and len(part.split()) <= 5
        ):
            candidates.append(part)
    if (
        not candidates
        and 3 <= len(raw) <= 50
        and is_usable_name(raw)
        and len(raw.split()) <= 5
        and not DESC_RE.match(raw)
        and not GENERIC_LEAD_RE.match(raw)
    ):
        candidates.append(raw)
    for name in candidates:
        # Must start with a capital letter (proper name), not "island…"
        if name[0].isupper() and not GENERIC_LEAD_RE.match(name):
            return name
    return None


def _load_geo_points() -> list[dict[str, Any]]:
    cache = c.load_json(CACHE, {})
    points: list[dict[str, Any]] = []
    if not isinstance(cache, dict):
        return points
    for _key, payload in cache.items():
        items = payload if isinstance(payload, list) else []
        for it in items:
            if not isinstance(it, dict):
                continue
            lat, lon = it.get("lat"), it.get("lon")
            title = it.get("title") or ""
            name = _title_to_name(title)
            if lat is None or lon is None or not name:
                continue
            points.append({
                "lat": float(lat),
                "lon": float(lon),
                "name": name,
                "norm": _norm(name),
                "title": title,
            })
    return points


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--radius-m", type=float, default=200.0)
    ap.add_argument("--min-agree", type=int, default=2)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--nation", default="")
    args = ap.parse_args()

    pending = load_unnamed(nation=args.nation)
    if args.limit:
        pending = pending[: args.limit]
    points = _load_geo_points()

    # Grid for photo points
    cell = 0.02
    grid: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for pt in points:
        grid[(int(pt["lat"] / cell), int(pt["lon"] / cell))].append(pt)

    proposals: list[dict] = []
    report: dict[str, Any] = {
        "script": "name_unnamed_photo_titles.py",
        "photoPoints": len(points),
        "pending": len(pending),
        "staged": 0,
        "adopted": [],
    }

    print(
        f"Photo titles: {len(points):,} lexicon hits × {len(pending):,} unnamed",
        flush=True,
    )

    for isl in pending:
        lat = isl.get("lat")
        lon = island_lon(isl)
        if lat is None or lon is None:
            continue
        lat_f, lon_f = float(lat), float(lon)
        cx, cy = int(lat_f / cell), int(lon_f / cell)
        nearby: list[dict] = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for pt in grid.get((cx + dx, cy + dy), []):
                    d = haversine_m(lat_f, lon_f, pt["lat"], pt["lon"])
                    if d <= args.radius_m:
                        nearby.append({**pt, "distanceM": d})
        if not nearby:
            continue
        counts = Counter(pt["norm"] for pt in nearby)
        best_norm, best_n = counts.most_common(1)[0]
        exemplars = [pt for pt in nearby if pt["norm"] == best_norm]
        exemplars.sort(key=lambda p: p["distanceM"])
        name = exemplars[0]["name"]
        dist = exemplars[0]["distanceM"]
        if best_n >= args.min_agree:
            tier, conf = "B", "medium-high"
            dual = True
        else:
            # Single photo titles are review-only (never auto-merge as Tier C medium)
            continue
        prop = build_proposal(
            isl,
            proposed_name=name,
            source="photo-title-consensus",
            licence="CC-BY-SA-4.0",
            source_page_url=(
                f"https://commons.wikimedia.org/wiki/{exemplars[0]['title'].replace(' ', '_')}"
                if str(exemplars[0]["title"]).startswith("File:")
                else "https://commons.wikimedia.org/"
            ),
            confidence_tier=tier,
            name_confidence=conf,
            distance_m=dist,
            source_ref=f"commons-geo×{best_n}",
            dual_source=dual,
            inference_method="commons-geosearch-title-consensus",
            extra={"agreeCount": best_n, "sampleTitles": [e["title"] for e in exemplars[:3]]},
        )
        if prop:
            proposals.append(prop)
            report["adopted"].append({
                "id": isl.get("id"),
                "name": name,
                "agree": best_n,
                "tier": tier,
            })

    report["staged"] = len(proposals)
    if not args.dry_run:
        save_staging(STAGING, proposals)
        c.save_json(REPORT, report)
    print(f"Staged {len(proposals):,} photo-title proposals → {STAGING}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
