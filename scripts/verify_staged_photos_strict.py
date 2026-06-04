#!/usr/bin/env python3
"""Strict verification pass for staged photo adoptions before merge.

Reads ``data/staging/adoptions/*.json``, scores each candidate against the
matching island in ``islands.json`` (name/geo/licence checks via
``verify_island_images`` helpers), and writes passing rows to
``data/staging/adoptions-verified/<same-filename>.json``.

Run (no islands.json writes)::

    python3 scripts/verify_staged_photos_strict.py
    python3 scripts/verify_staged_photos_strict.py --min-confidence 85
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
STAGING_IN = DATA / "staging" / "adoptions"
STAGING_OUT = DATA / "staging" / "adoptions-verified"
REPORT = DATA / "staged_verify_strict_report.json"
CACHE_COMMONS = DATA / "cache_commons.json"
CACHE_COMMONS_GEO = DATA / "cache_commons_geo.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_island_images import (  # noqa: E402
    _filename_from_image,
    _load_json,
    _name_matched,
    score_lead_image,
)

# Extra base scores for harvester-specific source tags (not in verify_island_images).
STAGING_BASE_SCORES: dict[str, int] = {
    "inaturalist-obs": 82,
    "openverse": 80,
    "commons-regional-category": 85,
    "commons-archipelago-category": 88,
    "commons-depicts-q": 92,
    "wikidata-depicts": 92,
    "wellcome-collection": 78,
    "ogl-tourism": 85,
    "geograph-via-commons": 90,
    "flickr-commons": 85,
    "europeana": 80,
    "web-discovery": 75,
    "kartaview": 80,
    "panoramax": 80,
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


def _has_provenance(rec: dict[str, Any]) -> bool:
    url = (rec.get("url") or "").strip()
    licence = (rec.get("license") or rec.get("licence") or "").strip()
    attr = (rec.get("attribution") or "").strip()
    return bool(url and licence and attr)


def _score_staged(
    island: dict[str, Any],
    rec: dict[str, Any],
    raw_row: dict[str, Any],
    commons_cache: dict,
    geo_cache: dict,
) -> tuple[int, list[str], bool]:
    source = (rec.get("source") or "unknown").strip()
    if source in STAGING_BASE_SCORES:
        confidence = STAGING_BASE_SCORES[source]
        reasons = [f"staging base for {source}: {confidence}"]
        suspect = False

        if source == "inaturalist-obs":
            dist = rec.get("inaturalistDistanceM")
            signal_a = bool(dist is not None or raw_row.get("dualSignal"))
            signal_b = isinstance(dist, (int, float)) and dist <= 5000
            if signal_a and signal_b:
                confidence = 96
                reasons.append(
                    f"atlas-bound obs + within-5km:{dist:.0f}m → 96"
                )
            elif isinstance(dist, (int, float)) and dist <= 500:
                confidence = 85
                reasons.append(f"iNaturalist distance {dist:.0f} m ≤ 500")
            elif isinstance(dist, (int, float)):
                confidence = 70
                suspect = True
                reasons.append(f"iNaturalist distance {dist:.0f} m > 5000 → 70")
            else:
                confidence = 75
                suspect = True
                reasons.append("iNaturalist distance unknown → 75")

        elif source == "openverse":
            if _name_matched(island, rec):
                reasons.append("island name match in title/caption")
            else:
                confidence = 55
                suspect = True
                reasons.append("no island name match → 55")

        elif source in (
            "commons-regional-category",
            "commons-archipelago-category",
            "commons-category",
            "ogl-tourism",
        ):
            signal_a = bool(
                raw_row.get("dualSignal")
                or raw_row.get("category")
                or raw_row.get("categories")
            )
            signal_b = _name_matched(island, rec)
            if signal_a and signal_b:
                confidence = 92
                reasons.append("commons island-category + name match → 92")
            elif signal_b:
                confidence = 85
                reasons.append("island name match in filename/caption")
            else:
                confidence = 70
                suspect = True
                reasons.append("no island name match → 70")

        elif source in ("commons-depicts-q", "wikidata-depicts"):
            pct = raw_row.get("confidencePct")
            rec_src = (rec.get("source") or source).strip()
            if rec_src == "wikidata-depicts" or source == "wikidata-depicts":
                if raw_row.get("depictsVerified") or raw_row.get("subjectVerified"):
                    confidence = int(pct) if isinstance(pct, (int, float)) else 92
                    reasons.append("wikidata depicts/subject verified")
                else:
                    confidence = 65
                    suspect = True
            elif raw_row.get("depictsVerified") and isinstance(pct, (int, float)) and pct >= 90:
                confidence = int(pct)
                reasons.append(f"depictsVerified confidencePct {pct}")
            elif raw_row.get("subjectVerified"):
                confidence = 88
                reasons.append("subjectVerified")
            else:
                confidence = 65
                suspect = True
                reasons.append("depicts/subject not verified")

        elif source == "wellcome-collection":
            if _name_matched(island, rec):
                reasons.append("island name match (Wellcome title)")
            else:
                confidence = 50
                suspect = True
                reasons.append("no island name match (homonym risk) → 50")

        return max(0, min(100, confidence)), reasons, suspect

    return score_lead_image(island, rec, commons_cache, geo_cache)


def verify_row(
    raw: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
    commons_cache: dict,
    geo_cache: dict,
    min_confidence: int,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    island_id = raw.get("id") or raw.get("islandId")
    rec = raw.get("image_record") or raw.get("image") or raw.get("imageRecord")
    if isinstance(rec, dict) and not rec.get("source"):
        top_src = raw.get("source") or raw.get("via")
        if top_src:
            rec = {**rec, "source": top_src}
    meta: dict[str, Any] = {
        "id": island_id,
        "staging_file": raw.get("_staging_file"),
        "accepted": False,
    }

    if not island_id:
        meta["reject_reason"] = "missing-id"
        return None, meta

    island = by_id.get(island_id)
    if not island:
        meta["reject_reason"] = "island-not-in-atlas"
        return None, meta

    if not isinstance(rec, dict) or not rec.get("url"):
        meta["reject_reason"] = "missing-image-record"
        return None, meta

    if not _has_provenance(rec):
        meta["reject_reason"] = "missing-licence-or-attribution"
        return None, meta

    confidence, reasons, suspect = _score_staged(
        island, rec, raw, commons_cache, geo_cache
    )
    meta.update({
        "name": island.get("name"),
        "source": rec.get("source"),
        "confidence": confidence,
        "reasons": reasons,
        "suspect": suspect,
        "filename": _filename_from_image(rec),
    })

    if suspect and confidence < min_confidence:
        meta["reject_reason"] = "suspect-below-threshold"
        return None, meta
    if confidence < min_confidence:
        meta["reject_reason"] = f"confidence-{confidence}-lt-{min_confidence}"
        return None, meta

    meta["accepted"] = True
    out = dict(raw)
    out["id"] = island_id
    out["imageConfidence"] = rec.get("imageConfidence") or raw.get("confidence")
    out["verifyConfidence"] = confidence
    out["verifyReasons"] = reasons
    if not out.get("verifiedAt"):
        out["verifiedAt"] = (
            datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        )
    return out, meta


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Verify staged photo adoptions; write adoptions-verified/",
    )
    ap.add_argument(
        "--input-dir",
        type=Path,
        default=STAGING_IN,
        help="Staging directory (default: data/staging/adoptions)",
    )
    ap.add_argument(
        "--output-dir",
        type=Path,
        default=STAGING_OUT,
        help="Verified output directory",
    )
    ap.add_argument(
        "--min-confidence",
        type=int,
        default=90,
        help="Minimum score to accept (default: 90)",
    )
    args = ap.parse_args()

    in_dir: Path = args.input_dir
    out_dir: Path = args.output_dir
    if not in_dir.is_dir():
        print(f"No staging dir: {in_dir}", file=sys.stderr)
        return 1

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    by_id = {i["id"]: i for i in islands if i.get("id")}
    commons_cache = _load_json(CACHE_COMMONS)
    geo_cache = _load_json(CACHE_COMMONS_GEO)

    out_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(in_dir.glob("*.json"))

    report: dict[str, Any] = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "minConfidence": args.min_confidence,
        "inputDir": str(in_dir.relative_to(ROOT)),
        "outputDir": str(out_dir.relative_to(ROOT)),
        "files": {},
        "acceptedTotal": 0,
        "rejectedTotal": 0,
        "rejected": [],
    }

    for path in files:
        rows = _load_staging_file(path)
        accepted: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            raw = {**raw, "_staging_file": path.name}
            ok, meta = verify_row(
                raw, by_id, commons_cache, geo_cache, args.min_confidence
            )
            if ok:
                ok.pop("_staging_file", None)
                accepted.append(ok)
            else:
                rejected.append(meta)

        out_path = out_dir / path.name
        out_path.write_text(
            json.dumps(accepted, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        report["files"][path.name] = {
            "read": len(rows),
            "accepted": len(accepted),
            "rejected": len(rejected),
        }
        report["acceptedTotal"] += len(accepted)
        report["rejectedTotal"] += len(rejected)
        report["rejected"].extend(rejected)
        print(
            f"{path.name}: {len(accepted)}/{len(rows)} accepted",
            file=sys.stderr,
        )

    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"Verified {report['acceptedTotal']} / "
        f"{report['acceptedTotal'] + report['rejectedTotal']} → {out_dir.relative_to(ROOT)}",
        file=sys.stderr,
    )
    print(f"Report → {REPORT.relative_to(ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
