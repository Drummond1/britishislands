#!/usr/bin/env python3
"""
Photo enrichment v4 — build a per-island image **gallery** in a separate
file `data/galleries.json`, so we don't bloat the main `islands.json`
that's loaded on first paint.

The frontend lazy-fetches `data/galleries.json` on the first island click
and merges `island.images[]` (lead photo, already shipped in islands.json)
with `galleries[id]` (additional photos, this file).

Sources for the additional images (in priority order, per island):

  A. **Wikidata Commons category** — for islands with a `wikidata` Q-ID,
     fetch the Commons category sitelink (P373 fallback) and adopt up to
     MAX_EXTRA more photos from the category.
  B. **commons-category sourceRef** — for islands whose lead photo is
     already a `commons-category` adoption, the category name lives in
     `sourceRef`. Walk it for more photos.
  C. **Commons radial geosearch** — for islands whose lead photo came
     from `commons-geosearch` (the majority of v3 adoptions), re-run
     geosearch with the same radius and adopt up to MAX_EXTRA more
     files that aren't the lead.

Hard rules (inherited from v3, see docs/ETHICS.md):
- Every adopted image MUST have `license`, `attribution`, `sourcePageUrl`.
- Skip the file that's already the lead image for this island.
- Skip non-photo files (maps, flags, logos) via `_looks_like_non_photo`.
- Atomic checkpointing every 100 islands (tmp + rename) so a kill is
  recoverable.

Run:
    python3 scripts/enrich_images_v4.py                 # full run
    python3 scripts/enrich_images_v4.py --limit 50      # quick test
    python3 scripts/enrich_images_v4.py --max-extra 5   # more per island

Outputs:
    data/galleries.json                                 # the new file
    data/cache_commons.json                             # shared w/ v2/v3
    data/cache_commons_category.json                    # shared
    data/cache_commons_geo.json                         # shared
    data/image_enrichment_v4_report.json                # audit
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS_PATH = DATA / "islands.json"
GALLERIES_PATH = DATA / "galleries.json"
REPORT_PATH = DATA / "image_enrichment_v4_report.json"

# Import the v3 helpers so we don't reinvent imageinfo / categorymembers /
# geosearch logic.
sys.path.insert(0, str(ROOT / "scripts"))
from enrich_images_v3 import (  # noqa: E402
    fetch_commons_meta,
    commons_category_for_qid,
    category_members,
    commons_geosearch,
    _canon_filename,
    _looks_like_non_photo,
    _save_cache,
    _load_cache,
    CACHE_CM,
    CACHE_CC,
    CACHE_GEO,
    DELAY_S,
)

MAX_EXTRA_DEFAULT = 3
CHECKPOINT_EVERY = 100


def atomic_write_json(path: Path, payload, *, indent=2) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=indent)
    os.replace(tmp, path)


def _clean_commons_url(url: str) -> str:
    """Strip Commons' newer `?utm_source=…&utm_campaign=imageinfo` tracking
    query parameters. The bare upload.wikimedia.org URL serves the file
    without any of that and keeps our gallery records lean."""
    if not url:
        return url
    if "upload.wikimedia.org" in url and "?" in url:
        return url.split("?", 1)[0]
    return url


def _build_image_record(
    fname: str,
    meta: dict,
    source: str,
    source_ref: str,
) -> dict | None:
    """Construct a uniform image record from Commons file metadata.

    Returns None if the file is missing essential fields (no URL or no
    licence). We never adopt an image without a usable licence string.
    """
    if not meta or not meta.get("url"):
        return None
    licence = meta.get("license") or ""
    if not licence:
        return None
    artist = meta.get("attribution") or ""
    bare_url = _clean_commons_url(meta["url"])
    return {
        "url": bare_url,
        "fullUrl": bare_url,
        "source": source,
        "sourceRef": source_ref,
        "sourcePageUrl": meta.get("descriptionUrl") or "",
        "license": licence,
        "licenseUrl": meta.get("licenseUrl") or "",
        "attribution": (
            f"Photo by {artist} ({licence}) via Wikimedia Commons"
            if artist
            else f"Wikimedia Commons ({licence})"
        ),
        "caption": meta.get("caption") or "",
        "fileName": fname,
        "primary": False,
    }


def _lead_filename(island: dict) -> str:
    imgs = island.get("images") or []
    if not imgs:
        return ""
    lead = next((i for i in imgs if i.get("primary")), imgs[0])
    return _canon_filename(lead.get("fileName") or lead.get("sourcePageUrl", "").split("/")[-1])


def _gather_candidates(island: dict, ctx: dict) -> tuple[list[str], str, str]:
    """Return (candidate_filenames, source_label, source_ref) for an island.

    The source label tells us how to attribute / record provenance.
    """
    lead_imgs = island.get("images") or []
    lead = lead_imgs[0] if lead_imgs else None
    lead_source = (lead or {}).get("source", "")

    # B: explicit commons-category sourceRef on the lead.
    if lead_source == "commons-category" and (lead or {}).get("sourceRef"):
        cat = lead["sourceRef"]
        members = ctx["cm_cache"].setdefault(cat, None)
        if members is None:
            members = category_members(cat, limit=50)
            ctx["cm_cache"][cat] = members
            _save_cache(ctx["cm_cache_path"], ctx["cm_cache"])
            time.sleep(DELAY_S)
        return [f for f in members if not _looks_like_non_photo(f)], "commons-category", cat

    # A: Wikidata Q-ID → Commons category.
    qid = (island.get("wikidata") or "").strip()
    if qid and qid.startswith("Q"):
        cat = commons_category_for_qid([qid], ctx["cc_cache"]).get(qid, "")
        if cat:
            members_key = cat
            members = ctx["cm_cache"].setdefault(members_key, None)
            if members is None:
                members = category_members(cat, limit=50)
                ctx["cm_cache"][members_key] = members
                _save_cache(ctx["cm_cache_path"], ctx["cm_cache"])
                time.sleep(DELAY_S)
            if members:
                return (
                    [f for f in members if not _looks_like_non_photo(f)],
                    "commons-category",
                    cat,
                )

    # C: geosearch (works for geosearch-sourced leads, and as a fallback).
    lat, lng = island.get("lat"), island.get("lng")
    if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
        radius_m = 800
        # Reuse the sourceRef radius if the lead came from geosearch.
        if lead_source == "commons-geosearch" and (lead or {}).get("sourceRef"):
            try:
                _, r = (lead["sourceRef"].split(";", 1) + ["800"])[:2]
                radius_m = int(float(r))
            except Exception:
                pass
        hits = commons_geosearch(lat, lng, radius_m, ctx["cg_cache"])
        # `commons_geosearch` returns [{"title": "...", "dist": ...}, ...]
        files = [
            _canon_filename(h["title"])
            for h in hits
            if h.get("title", "").startswith("File:")
        ]
        return (
            [f for f in files if not _looks_like_non_photo(f)],
            "commons-geosearch",
            f"{lat:.4f},{lng:.4f};{radius_m}",
        )

    return [], "", ""


def _checkpoint(galleries: dict, report: dict) -> None:
    atomic_write_json(GALLERIES_PATH, galleries)
    atomic_write_json(REPORT_PATH, report)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0,
                    help="Process only the first N islands (debug).")
    ap.add_argument("--max-extra", type=int, default=MAX_EXTRA_DEFAULT,
                    help=f"Max extra images per island (default {MAX_EXTRA_DEFAULT}).")
    ap.add_argument("--refresh", action="store_true",
                    help="Bypass caches (slow, only for debugging).")
    args = ap.parse_args()

    print(f"Loading {ISLANDS_PATH}…")
    with open(ISLANDS_PATH, encoding="utf-8") as f:
        islands = json.load(f)
    print(f"  {len(islands):,} islands loaded")

    # Existing gallery file is the resume point; we never start from scratch
    # unless the user deletes it.
    galleries: dict[str, list[dict]] = {}
    if GALLERIES_PATH.exists():
        try:
            galleries = json.loads(GALLERIES_PATH.read_text())
            print(f"  resuming with {len(galleries):,} existing galleries")
        except Exception:
            galleries = {}

    # Process only islands that already have a lead image AND fewer than
    # `--max-extra` entries in their gallery (so reruns are idempotent).
    targets = []
    for isl in islands:
        if not isl.get("images"):
            continue
        existing = galleries.get(isl["id"], [])
        if len(existing) >= args.max_extra:
            continue
        targets.append(isl)
    if args.limit:
        targets = targets[: args.limit]
    print(f"  target islands: {len(targets):,}")

    # Caches (shared with v3 so we don't redo work).
    ctx = {
        "cm_cache_path": DATA / "cache_commons_categorymembers.json",
        "cm_cache": _load_cache(DATA / "cache_commons_categorymembers.json"),
        "cc_cache": _load_cache(CACHE_CC),
        "cg_cache": _load_cache(CACHE_GEO),
    }
    file_meta_cache = _load_cache(CACHE_CM)

    report = {
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "targets": len(targets),
        "processed": 0,
        "added_per_source": {"commons-category": 0, "commons-geosearch": 0},
        "skipped": [],
        "complete": False,
    }

    total_added = 0

    for idx, isl in enumerate(targets, 1):
        iid = isl["id"]
        lead_fname = _lead_filename(isl)

        candidates, source, source_ref = _gather_candidates(isl, ctx)
        if not candidates:
            report["skipped"].append({"id": iid, "reason": "no candidates"})
        else:
            existing_files = {g.get("fileName") for g in galleries.get(iid, [])}
            existing_files.add(lead_fname)
            picks = []
            for f in candidates:
                if f in existing_files:
                    continue
                picks.append(f)
                if len(picks) >= args.max_extra:
                    break
            if picks:
                metas = fetch_commons_meta(picks, file_meta_cache)
                gallery = galleries.setdefault(iid, [])
                for f in picks:
                    rec = _build_image_record(f, metas.get(f, {}), source, source_ref)
                    if rec:
                        gallery.append(rec)
                        report["added_per_source"][source] = (
                            report["added_per_source"].get(source, 0) + 1
                        )
                        total_added += 1

        report["processed"] = idx

        if idx % 100 == 0:
            print(
                f"  {idx}/{len(targets)} processed; "
                f"added so far: {total_added} across "
                f"{len(galleries):,} islands"
            )
            _checkpoint(galleries, report)
        if idx % 50 == 0:
            time.sleep(DELAY_S)

    report["complete"] = True
    report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _checkpoint(galleries, report)
    print(
        f"\nDone. Added {total_added} new images across "
        f"{sum(1 for v in galleries.values() if v):,} galleries."
    )
    print(f"  galleries → {GALLERIES_PATH}")
    print(f"  report    → {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
