#!/usr/bin/env python3
"""Commons county-island category trees (islands without Wikidata Q-ID)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
STAGING = DATA / "staging" / "adoptions" / "commons-county.json"
CACHE = DATA / "cache_commons_county.json"
COMMONS_CACHE = DATA / "cache_commons_meta.json"
REPORT = DATA / "image_enrichment_commons_county_report.json"

# Nation → Commons category suffix patterns
COUNTY_CATEGORIES = [
    "Category:Islands of County Mayo",
    "Category:Islands of County Galway",
    "Category:Islands of County Kerry",
    "Category:Islands of County Cork",
    "Category:Islands of County Donegal",
    "Category:Islands of County Clare",
    "Category:Islands of the Outer Hebrides",
    "Category:Islands of Orkney",
    "Category:Islands of Shetland",
    "Category:Islands of Argyll and Bute",
    "Category:Islands of Highland (council area)",
    "Category:Islands of Pembrokeshire",
    "Category:Islands of Cornwall",
    "Category:Islands of the Isles of Scilly",
    "Category:Islands of Essex",
    "Category:Islands of Suffolk",
    "Category:Islands of Norfolk",
]

sys.path.insert(0, str(Path(__file__).resolve().parent))
from enrich_images_v5 import (  # noqa: E402
    _canon,
    _load,
    _load_named_index_ids,
    _mentions,
    _name_variants,
    _save,
    build_image_record_from_commons,
    _category_members,
    fetch_commons_meta,
)
from photo_staging_dual import save_staging  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--named-only", action="store_true", default=True)
    ap.add_argument("--limit", type=int, default=300)
    ap.add_argument("--delay", type=float, default=1.5)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    named = _load_named_index_ids() if args.named_only else set()
    pending = [i for i in islands if not (i.get("images") or [])]
    if args.named_only:
        pending = [i for i in pending if i.get("id") in named]
    by_name: dict[str, list[dict]] = {}
    for isl in pending:
        key = _canon(isl.get("name") or "")
        if key:
            by_name.setdefault(key, []).append(isl)

    cache = _load(CACHE)
    commons_cache = _load(COMMONS_CACHE)
    adoptions: list[dict] = []
    report = {"staged": 0, "categories_scanned": 0, "adopted": []}

    for cat in COUNTY_CATEGORIES:
        if len(adoptions) >= args.limit:
            break
        members = cache.get(cat)
        if members is None:
            members = _category_members(cat, limit=200)
            cache[cat] = members
            _save(CACHE, cache)
            time.sleep(args.delay)
        report["categories_scanned"] += 1
        for fname in members:
            canon = _canon(fname)
            meta = fetch_commons_meta([canon], commons_cache).get(canon, {})
            if not meta or not meta.get("url"):
                continue
            title = _canon(fname)
            for key, isls in list(by_name.items()):
                for isl in isls:
                    if _mentions(title, _name_variants(isl)):
                        rec = build_image_record_from_commons(
                            fname,
                            meta,
                            source="commons-county-category",
                            source_ref=cat,
                        )
                        if not rec:
                            continue
                        rec["dualSignal"] = True
                        adoptions.append({
                            "id": isl["id"],
                            "islandId": isl["id"],
                            "image_record": rec,
                            "category": cat,
                            "dualSignal": True,
                            "imageConfidence": "high",
                        })
                        report["adopted"].append({"id": isl["id"], "cat": cat, "file": fname})
                        by_name[key] = [x for x in isls if x["id"] != isl["id"]]
                        break
                if len(adoptions) >= args.limit:
                    break

    report["staged"] = len(adoptions)
    if not args.dry_run:
        _save(COMMONS_CACHE, commons_cache)
        save_staging(STAGING, adoptions)
        REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Commons county staged: {len(adoptions)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
