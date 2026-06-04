#!/usr/bin/env python3
"""Merge staged photo adoptions from data/staging/adoptions/*.json into islands.json.

Reads all JSON files in the staging directory, normalises adoption rows, dedupes by
island id (highest imageConfidence wins; ties favour earlier file order), and applies
only to islands that still have no images[].

Writes:
  data/islands.json.before-staged-merge   (backup, unless --no-backup)
  data/islands.json                       (atomic replace)
  data/staged_merge_report.json

Run after harvesters finish (no parallel writers to islands.json)::

    python3 scripts/verify_staged_photos_strict.py   # gate → adoptions-verified/
    python3 scripts/merge_staged_photo_adoptions.py
    python3 scripts/merge_staged_photo_adoptions.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
BACKUP = DATA / "islands.json.before-staged-merge"
STAGING_DIR = DATA / "staging" / "adoptions"
STAGING_VERIFIED = DATA / "staging" / "adoptions-verified"
REPORT = DATA / "staged_merge_report.json"
INDEX = DATA / "islands_index.json"

CONFIDENCE_RANK = {
    "high": 4,
    "medium-high": 3,
    "medium": 2,
    "low": 1,
}


def _confidence_score(label: str | None) -> int:
    if not label:
        return 0
    return CONFIDENCE_RANK.get(str(label).strip().lower(), 0)


def _stamp_record(rec: dict[str, Any], confidence: str | None) -> dict[str, Any]:
    out = dict(rec)
    if confidence and not out.get("imageConfidence"):
        out["imageConfidence"] = confidence
    if not out.get("verifiedAt"):
        out["verifiedAt"] = (
            datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        )
    return out


def _normalise_row(raw: dict[str, Any], staging_file: str) -> dict[str, Any] | None:
    island_id = raw.get("id") or raw.get("islandId")
    if not island_id:
        return None

    rec = (
        raw.get("image_record")
        or raw.get("image")
        or raw.get("imageRecord")
    )
    if not isinstance(rec, dict) or not rec.get("url"):
        return None

    confidence = (
        raw.get("imageConfidence")
        or raw.get("confidence")
        or rec.get("imageConfidence")
    )
    source = (
        raw.get("source")
        or raw.get("via")
        or rec.get("source")
        or staging_file.replace(".json", "")
    )
    rec = _stamp_record(rec, confidence)

    return {
        "id": island_id,
        "name": raw.get("name", ""),
        "source": source,
        "staging_file": staging_file,
        "imageConfidence": rec.get("imageConfidence"),
        "image_record": rec,
        "score": _confidence_score(rec.get("imageConfidence")),
    }


def _load_staging_file(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  skip {path.name}: {exc}", file=sys.stderr)
        return []

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        adoptions = data.get("adoptions")
        if isinstance(adoptions, list):
            return adoptions
    print(f"  skip {path.name}: unrecognised shape", file=sys.stderr)
    return []


def _resolve_staging_dir(
    staging_dir: Path | None,
    prefer_verified: bool,
) -> tuple[Path, str]:
    """Pick verified dir when present and non-empty, else raw adoptions."""
    if staging_dir is not None:
        return staging_dir, "explicit"
    if prefer_verified and STAGING_VERIFIED.is_dir():
        verified_files = list(STAGING_VERIFIED.glob("*.json"))
        if verified_files:
            return STAGING_VERIFIED, "verified"
    return STAGING_DIR, "raw"


def _collect_adoptions(
    staging_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not staging_dir.is_dir():
        return [], {"staging_files": [], "rows_read": 0, "staging_dir": str(staging_dir)}

    files = sorted(staging_dir.glob("*.json"))
    merged: dict[str, dict[str, Any]] = {}
    meta: dict[str, Any] = {
        "staging_dir": str(staging_dir.relative_to(ROOT)),
        "staging_files": [],
        "rows_read": 0,
        "rows_by_file": {},
        "parse_skipped": 0,
    }

    for path in files:
        rows = _load_staging_file(path)
        meta["staging_files"].append(path.name)
        meta["rows_by_file"][path.name] = len(rows)
        meta["rows_read"] += len(rows)
        n_ok = 0
        for raw in rows:
            if not isinstance(raw, dict):
                meta["parse_skipped"] += 1
                continue
            norm = _normalise_row(raw, path.name)
            if not norm:
                meta["parse_skipped"] += 1
                continue
            n_ok += 1
            iid = norm["id"]
            prev = merged.get(iid)
            if prev is None or norm["score"] > prev["score"]:
                merged[iid] = norm
            elif norm["score"] == prev["score"]:
                # Same confidence: keep first file in sorted order (prev).
                pass
        meta["rows_by_file"][path.name] = {
            "raw": len(rows),
            "normalised": n_ok,
        }

    return list(merged.values()), meta


def _atomic_write_islands(payload: list) -> None:
    tmp = ISLANDS.with_suffix(ISLANDS.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, ISLANDS)


def _count_named_with_photo(islands: list[dict[str, Any]]) -> int:
    if not INDEX.exists():
        return sum(1 for i in islands if i.get("images") or i.get("image"))
    idx = json.loads(INDEX.read_text(encoding="utf-8"))
    named_ids = {r["id"] for r in idx.get("rows", []) if r.get("id")}
    return sum(
        1
        for i in islands
        if i.get("id") in named_ids and (i.get("images") or i.get("image"))
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Merge staged photo adoptions into islands.json (photoless only).",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Report merges without writing islands.json.",
    )
    ap.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip timestamped islands.json.before-staged-merge-* backup.",
    )
    ap.add_argument(
        "--staging-dir",
        type=Path,
        default=None,
        help="Override staging directory (default: adoptions-verified if non-empty, else adoptions).",
    )
    ap.add_argument(
        "--no-prefer-verified",
        action="store_true",
        help="Always read data/staging/adoptions even if adoptions-verified exists.",
    )
    ap.add_argument(
        "--inline-verify",
        action="store_true",
        help="Run verify_staged_photos_strict inline before merge (when not using verified dir).",
    )
    ap.add_argument(
        "--min-confidence",
        type=int,
        default=90,
        help="Min confidence for inline verify (default: 90).",
    )
    args = ap.parse_args()

    staging_dir, staging_source = _resolve_staging_dir(
        args.staging_dir,
        prefer_verified=not args.no_prefer_verified,
    )

    if staging_source == "raw" or args.inline_verify:
        from verify_staged_photos_strict import main as verify_main  # noqa: WPS433

        old_argv = sys.argv
        sys.argv = [
            "verify_staged_photos_strict.py",
            "--input-dir",
            str(STAGING_DIR),
            "--output-dir",
            str(STAGING_VERIFIED),
            "--min-confidence",
            str(args.min_confidence),
        ]
        verify_main()
        sys.argv = old_argv
        staging_dir, staging_source = STAGING_VERIFIED, "inline-verified"

    candidates, load_meta = _collect_adoptions(staging_dir)
    load_meta["staging_source"] = staging_source
    print(f"Staging dir: {staging_dir.relative_to(ROOT)} ({staging_source})")
    print(f"Files: {len(load_meta.get('staging_files', []))}")
    print(f"Candidates after dedupe: {len(candidates):,}")

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    if not isinstance(islands, list):
        print("FATAL: islands.json is not a list", file=sys.stderr)
        return 2

    named_before = _count_named_with_photo(islands)
    by_id = {i.get("id"): i for i in islands if i.get("id")}

    merged_by_source: dict[str, int] = {}
    merged_rows: list[dict[str, Any]] = []
    skipped_has_image: list[str] = []
    skipped_missing_island: list[str] = []

    for cand in candidates:
        iid = cand["id"]
        isl = by_id.get(iid)
        if not isl:
            skipped_missing_island.append(iid)
            continue
        if isl.get("images"):
            skipped_has_image.append(iid)
            continue
        rec = cand["image_record"]
        src = rec.get("source") or cand.get("source") or "unknown"
        merged_by_source[src] = merged_by_source.get(src, 0) + 1
        merged_rows.append({
            "id": iid,
            "name": isl.get("name") or cand.get("name"),
            "source": src,
            "staging_file": cand.get("staging_file"),
            "imageConfidence": rec.get("imageConfidence"),
            "verifiedAt": rec.get("verifiedAt"),
            "sourcePageUrl": rec.get("sourcePageUrl"),
            "_image_record": rec,
        })

    backup_path: Path | None = None
    if not args.dry_run and merged_rows:
        if not args.no_backup:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup_path = DATA / f"islands.json.before-staged-merge-{stamp}.bak"
            shutil.copy2(ISLANDS, backup_path)
            print(f"Backup → {backup_path.relative_to(ROOT)}")
        for row in merged_rows:
            isl = by_id[row["id"]]
            rec = row.pop("_image_record")
            isl.setdefault("images", []).append(rec)
            conf = rec.get("imageConfidence")
            if conf:
                isl["imageConfidence"] = conf
    else:
        for row in merged_rows:
            row.pop("_image_record", None)

    report: dict[str, Any] = {
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "dry_run": args.dry_run,
        "backup": str(backup_path.relative_to(ROOT)) if backup_path else None,
        "staging_source": staging_source,
        "load": load_meta,
        "candidates_deduped": len(candidates),
        "merged_total": len(merged_rows),
        "merged_by_source": merged_by_source,
        "merged_by_staging_file": {},
        "skipped_already_has_image": len(skipped_has_image),
        "skipped_missing_island": len(skipped_missing_island),
        "named_with_photo_before": named_before,
        "merged": merged_rows,
    }
    for row in merged_rows:
        sf = row.get("staging_file") or "unknown"
        report["merged_by_staging_file"][sf] = (
            report["merged_by_staging_file"].get(sf, 0) + 1
        )

    if not args.dry_run and merged_rows:
        _atomic_write_islands(islands)
        named_after = _count_named_with_photo(islands)
    else:
        named_after = named_before + (
            0 if args.dry_run else len(merged_rows)
        )
        if args.dry_run:
            named_after = named_before + len(merged_rows)

    report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    report["named_with_photo_after"] = (
        _count_named_with_photo(islands)
        if not args.dry_run
        else named_after
    )
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print()
    print(f"Merged:                 {len(merged_rows):,}")
    print(f"Skipped (has image):    {len(skipped_has_image):,}")
    print(f"Skipped (no island):    {len(skipped_missing_island):,}")
    print(f"Named with photo:       {report['named_with_photo_after']:,} "
          f"(was {named_before:,})")
    if merged_by_source:
        print("By source:")
        for src, n in sorted(merged_by_source.items(), key=lambda x: -x[1]):
            print(f"  {src}: {n}")
    print(f"Report → {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
