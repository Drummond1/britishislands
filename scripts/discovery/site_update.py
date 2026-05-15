"""Site Update Agent — gated merge into islands.json with review report."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import common as c


def _merge_into(dest: dict, src: dict) -> None:
    if not dest.get("wikidata") and src.get("wikidata"):
        dest["wikidata"] = src["wikidata"]
    if not dest.get("wikipedia") and src.get("wikipedia"):
        dest["wikipedia"] = src["wikipedia"]
    if not dest.get("osmType") and src.get("osmType"):
        dest["osmType"] = src["osmType"]
        dest["osmId"] = src.get("osmId")
    src_sources = src.get("sources") or []
    dest_sources = dest.get("sources") or []
    seen = {(s.get("name"), s.get("ref"), s.get("url")) for s in dest_sources}
    for source in src_sources:
        key = (source.get("name"), source.get("ref"), source.get("url"))
        if key not in seen:
            dest_sources.append(source)
            seen.add(key)
    if dest_sources:
        dest["sources"] = dest_sources
    if not dest.get("images") and src.get("images"):
        dest["images"] = src["images"]
    if not dest.get("image") and src.get("image"):
        dest["image"] = src["image"]


def _record_for_merge(candidate: dict) -> dict:
    row = dict(candidate)
    row.pop("discovery", None)
    row.pop("aliases", None)
    return row


def _apply_unconfirmed_classification(row: dict, raw: dict) -> None:
    """Mark atlas rows that are included for mapping but not fully verified."""
    disc = raw.get("discovery") or {}
    reasons: list[str] = []
    vc = disc.get("verificationConfidence") or raw.get("verificationConfidence")
    if vc in {"low", "medium"}:
        reasons.append(f"verification {vc}")
    for note in disc.get("notes") or []:
        if note:
            reasons.append(str(note)[:160])
    if not (row.get("images") or row.get("image")):
        reasons.append("no licence-safe hero image in discovery pass")
    hint = "; ".join(reasons) if reasons else "Discovery pipeline did not clear the automatic review gate"
    row["classification"] = {
        "source": "discovery-pipeline",
        "confidence": "unconfirmed",
        "reviewHint": hint[:800],
    }


def run(*, apply: bool = False, include_uncertain: bool = False) -> dict[str, Any]:
    enrichment = c.load_json(c.ENRICH_PATH, {})
    candidates = list(enrichment.get("records") or [])
    islands = c.load_islands()
    index = c.build_island_index(islands)

    added: list[dict] = []
    added_provisional: list[dict] = []
    skipped_duplicate: list[dict] = []
    skipped_uncertain: list[dict] = []
    skipped_existing_review: list[dict] = []
    merged: list[dict] = []
    skipped_terrestrial_rock: list[dict] = []

    for candidate in candidates:
        fk = (candidate.get("osmPlace") or "").lower()
        if fk == "rock" and c.is_terrestrial_inland_rock(
            float(candidate["lat"]),
            float(candidate["lng"]),
            "rock",
        ):
            skipped_terrestrial_rock.append(
                {
                    "id": candidate.get("id"),
                    "name": candidate.get("name"),
                    "reason": "terrestrial_inland_rock",
                }
            )
            continue
        needs_review = (candidate.get("discovery") or {}).get("needsReview")
        # Uncertain rows: only merge on OSM / Wikidata / name+proximity — never
        # the global 0.5 km fallback (would glue unrelated stacks to neighbours).
        match = c.find_existing_match(candidate, index, loose=not needs_review)
        if match:
            if c.is_curated(match):
                _merge_into(match, candidate)
                skipped_existing_review.append(
                    {
                        "id": match.get("id"),
                        "name": match.get("name"),
                        "reason": "matched_curated_existing",
                    }
                )
            else:
                _merge_into(match, candidate)
                merged.append(
                    {
                        "id": match.get("id"),
                        "name": match.get("name"),
                        "reason": "merged_into_existing",
                    }
                )
            continue

        if needs_review and not include_uncertain:
            skipped_uncertain.append(
                {
                    "id": candidate.get("id"),
                    "name": candidate.get("name"),
                    "reason": "needs_manual_review",
                }
            )
            continue

        key = (c.name_key(candidate["name"]), round(candidate["lat"], 2), round(candidate["lng"], 2))
        if any(
            c.haversine_km(candidate["lat"], candidate["lng"], row["lat"], row["lng"]) <= c.PROXIMITY_KM
            and c.name_key(row["name"]) == c.name_key(candidate["name"])
            for row in added
        ):
            skipped_duplicate.append(
                {
                    "id": candidate.get("id"),
                    "name": candidate.get("name"),
                    "reason": "duplicate_among_candidates",
                }
            )
            continue

        row = _record_for_merge(candidate)
        if needs_review:
            _apply_unconfirmed_classification(row, candidate)
            added_provisional.append({"id": row["id"], "name": row["name"]})
        added.append(row)

    report: dict[str, Any] = {
        "agent": "site_update",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "dryRun": not apply,
        "includeUncertain": include_uncertain,
        "inputRecords": len(candidates),
        "added": [{"id": row["id"], "name": row["name"], "nation": row.get("nation")} for row in added],
        "addedProvisional": added_provisional,
        "merged": merged,
        "skippedDuplicate": skipped_duplicate,
        "skippedUncertain": skipped_uncertain,
        "skippedExistingReview": skipped_existing_review,
        "skippedTerrestrialRock": skipped_terrestrial_rock,
        "counts": {
            "added": len(added),
            "addedProvisional": len(added_provisional),
            "merged": len(merged),
            "skippedDuplicate": len(skipped_duplicate),
            "skippedUncertain": len(skipped_uncertain),
            "skippedExistingReview": len(skipped_existing_review),
            "skippedTerrestrialRock": len(skipped_terrestrial_rock),
        },
    }

    mutated_existing = bool(merged or skipped_existing_review)
    if apply and (added or mutated_existing):
        backup = c.ISLANDS_PATH.with_name(
            f"islands.json.before-discovery-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        )
        backup.write_text(c.ISLANDS_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        if added:
            islands.extend(added)
            islands.sort(key=lambda row: row["name"].lower())
        c.ISLANDS_PATH.write_text(json.dumps(islands, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report["backupPath"] = str(backup)
        report["finalIslandCount"] = len(islands)
        print(
            f"Site Update: applied {len(added)} new, {len(merged)} merged, "
            f"{len(skipped_existing_review)} curated merges (backup {backup.name})",
            file=sys.stderr,
        )
    else:
        print(
            f"Site Update dry-run: would add {len(added)}, merge {len(merged)}, "
            f"skip {len(skipped_uncertain)} uncertain",
            file=sys.stderr,
        )

    c.save_json(c.REVIEW_PATH, report)
    return report
