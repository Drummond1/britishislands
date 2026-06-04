#!/usr/bin/env python3
"""Commons geosearch pass for named islands still without a photo.

Wraps ``enrich_images_v5.try_commons_geosearch_wide`` with a fixed 500 m
radius, strict name match (inherited from v5), and stamps adopted images
with ``imageConfidence: medium-high`` and ``verifiedAt``.

Stops after ``--limit`` **adoptions** (not attempts) to limit API load.

Run::

    python3 scripts/enrich_images_geosearch_verified.py --dry-run --limit 5
    python3 scripts/enrich_images_geosearch_verified.py --limit 10
    python3 scripts/enrich_images_geosearch_verified.py --delay 3 --limit 3

Outputs::

    data/islands.json                    (mutated unless --dry-run)
    data/geosearch_verified_report.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
BACKUP = DATA / "islands.json.before-geosearch-verified"
REPORT = DATA / "geosearch_verified_report.json"

DEFAULT_GEOSEARCH_RADIUS_M = 500
DEFAULT_DELAY_S = 2.0
CONFIDENCE_LABEL = "medium-high"
CONFIDENCE_SCORE = 85

sys.path.insert(0, str(Path(__file__).resolve().parent))
import enrich_images_v5 as v5  # noqa: E402


def _stamp_geosearch_verified(rec: dict) -> dict:
    """Stamp medium-high tier (score 85) on the adopted image record."""
    out = dict(rec)
    out["imageConfidence"] = CONFIDENCE_LABEL
    out["verifiedAt"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return out


def main() -> int:
    p = argparse.ArgumentParser(
        description="Commons geosearch (500 m, name match) for named islands without images.",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Stop after this many adoptions (0 = no cap).",
    )
    p.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY_S,
        metavar="SECONDS",
        help=f"Seconds between geosearch API calls (default {DEFAULT_DELAY_S}).",
    )
    p.add_argument(
        "--geosearch-radius",
        type=int,
        default=DEFAULT_GEOSEARCH_RADIUS_M,
        metavar="METERS",
        help=f"Commons geosearch radius in metres (default {DEFAULT_GEOSEARCH_RADIUS_M}).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Evaluate and report adoptions without writing islands.json.",
    )
    p.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip writing islands.json.before-geosearch-verified.",
    )
    p.add_argument(
        "--test",
        default="",
        help="Process only the island with this id.",
    )
    args = p.parse_args()

    v5.DELAY_S = max(0.0, float(args.delay))
    cfg = v5.EnrichmentConfig(geosearch_radius_m=int(args.geosearch_radius))

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    if not isinstance(islands, list):
        print("FATAL: islands.json is not a list", file=sys.stderr)
        return 2

    if not args.dry_run and not args.no_backup and not BACKUP.exists():
        BACKUP.write_text(
            json.dumps(islands, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Backup → {BACKUP.relative_to(ROOT)}")

    cache_commons = v5._load(v5.CACHE_COMMONS)
    cache_geo = v5._load(v5.CACHE_COMMONS_GEO)

    named_ids = v5._load_named_index_ids()
    if not named_ids:
        print("FATAL: no named index ids (islands_index.json)", file=sys.stderr)
        return 2

    pending = [
        i for i in islands
        if not (i.get("images") or [])
        and i.get("id") in named_ids
        and (i.get("name") or "").strip()
    ]
    if args.test:
        pending = [i for i in islands if i.get("id") == args.test]
        if not pending:
            print(f"FATAL: no island with id {args.test!r}", file=sys.stderr)
            return 2

    report: dict = {
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "script": "enrich_images_geosearch_verified.py",
        "args": vars(args),
        "geosearch_radius_m": cfg.geosearch_radius_m,
        "delay_s": v5.DELAY_S,
        "confidence": {"label": CONFIDENCE_LABEL, "score": CONFIDENCE_SCORE},
        "input_named_without_image": len(pending),
        "adopted": [],
        "rejected": [],
        "skipped": [],
        "dry_run": bool(args.dry_run),
    }
    print(
        f"Named islands without images: {len(pending):,} "
        f"(geosearch {cfg.geosearch_radius_m} m, delay {v5.DELAY_S}s)",
        flush=True,
    )

    n_adopted = 0
    n_attempted = 0
    rejected_geo: list = []

    for isl in pending:
        if args.limit and n_adopted >= args.limit:
            break

        n_attempted += 1
        rec = v5.try_commons_geosearch_wide(
            isl, cache_commons, cache_geo, rejected_geo, cfg,
        )
        if not rec:
            report["rejected"].append({
                "id": isl.get("id"),
                "name": isl.get("name", ""),
                "reason": "no geosearch candidate (name match + licence required)",
            })
            continue

        rec = _stamp_geosearch_verified(rec)
        adopted_row = {
            "id": isl["id"],
            "name": isl.get("name", ""),
            "source": rec.get("source"),
            "license": rec.get("license"),
            "sourcePageUrl": rec.get("sourcePageUrl"),
            "imageConfidence": rec["imageConfidence"],
            "confidenceScore": CONFIDENCE_SCORE,
            "verifiedAt": rec["verifiedAt"],
            "dry_run": args.dry_run,
        }
        report["adopted"].append(adopted_row)
        n_adopted += 1

        if args.dry_run:
            print(
                f"  ✓ [dry-run] {isl['id']:45s} → {rec.get('source')} "
                f"({rec.get('license')}) [{rec['imageConfidence']}]",
                flush=True,
            )
        else:
            isl.setdefault("images", []).append(rec)
            print(
                f"  ✓ [{n_adopted}/{args.limit or '∞'}] {isl['id']:45s} → "
                f"{rec.get('source')} ({rec.get('license')}) [{rec['imageConfidence']}]",
                flush=True,
            )

    report["rejected"].extend(rejected_geo)
    report["attempted"] = n_attempted
    report["adopted_total"] = n_adopted
    report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")

    v5._save(REPORT, report)

    if not args.dry_run and n_adopted:
        tmp = ISLANDS.with_suffix(ISLANDS.suffix + ".tmp")
        tmp.write_text(
            json.dumps(islands, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, ISLANDS)

    print()
    print(f"Attempted: {n_attempted:,}")
    print(f"Adopted:   {n_adopted:,}" + (" (dry-run, not written)" if args.dry_run else ""))
    print(f"Report   → {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
