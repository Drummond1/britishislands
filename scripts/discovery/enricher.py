"""Data Enrichment Agent — structured island records for review."""

from __future__ import annotations

import sys
from typing import Any

from . import common as c


def _island_type(candidate: dict) -> str:
    kind = (candidate.get("featureKind") or candidate.get("osmPlace") or "").lower()
    if kind in {"lake", "river"}:
        return kind
    return "sea"


def _needs_review(candidate: dict) -> bool:
    if candidate.get("verificationConfidence") in {"low", "medium"}:
        return True
    if candidate.get("notes"):
        return True
    if not candidate.get("image"):
        return True
    return False


def _to_island_record(candidate: dict) -> dict:
    name = candidate["name"]
    record = {
        "id": c.slugify(name),
        "name": name,
        "nation": candidate.get("nation") or c.nation_for(candidate["lat"], candidate["lng"]),
        "type": _island_type(candidate),
        "subtype": "tidal" if candidate.get("featureKind") == "rock" else None,
        "tidal": candidate.get("featureKind") == "rock",
        "archipelago": "",
        "lat": candidate["lat"],
        "lng": candidate["lng"],
        "areaKm2": None,
        "population": None,
        "highestPointM": None,
        "highestPointName": "",
        "shortDescription": "",
        "history": "",
        "geography": "",
        "transport": "",
        "accommodation": "",
        "wikipedia": candidate.get("wikipedia") or "",
        "wikidata": candidate.get("wikidata") or "",
        "image": "",
        "images": [],
        "tags": list(candidate.get("tags") or []),
        "source": "discovery",
        "osmType": candidate.get("osmType"),
        "osmId": candidate.get("osmId"),
        "osmPlace": candidate.get("osmPlace") or candidate.get("featureKind") or "island",
        "parentWaterBody": None,
        "classification": {
            "source": "discovery-pipeline",
            "confidence": candidate.get("verificationConfidence") or "medium",
        },
        "sources": candidate.get("sources") or [],
        "aliases": candidate.get("aliases") or [],
        "discovery": {
            "candidateId": candidate.get("candidateId"),
            "scanConfidence": candidate.get("scanConfidence"),
            "verificationConfidence": candidate.get("verificationConfidence"),
            "needsReview": _needs_review(candidate),
            "notes": candidate.get("notes") or [],
        },
    }
    image = candidate.get("image")
    if image:
        record["image"] = image.get("url") or ""
        record["images"] = [image]
    return record


def run(*, limit: int | None = None) -> dict[str, Any]:
    photos = c.load_json(c.PHOTOS_PATH, {})
    rows = [row for row in (photos.get("records") or []) if row.get("verified")]
    if limit:
        rows = rows[:limit]

    enriched = [_to_island_record(row) for row in rows]
    uncertain = [row for row in enriched if row["discovery"]["needsReview"]]
    ready = [row for row in enriched if not row["discovery"]["needsReview"]]

    report = {
        "agent": "data_enrichment",
        "inputVerified": len(rows),
        "readyForMerge": len(ready),
        "needsManualReview": len(uncertain),
        "records": enriched,
    }
    c.save_json(c.ENRICH_PATH, report)
    print(
        f"Data Enrichment: {len(ready)} ready, {len(uncertain)} flagged for review",
        file=sys.stderr,
    )
    return report
