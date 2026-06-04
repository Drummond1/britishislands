"""Shared dual-signal (name + geo) gates for photo staging harvesters."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

GEO_MAX_KM = 15.0
GEO_MAX_KM_GENERIC = 5.0
CONFIDENCE = "medium"

_GENERIC_NAME_RE = re.compile(
    r"^(?:the\s+)?"
    r"(?:green|black|white|red|blue|brown|grey|gray|great|little|big|small|"
    r"north|south|east|west|middle|inner|outer|high|low|long|short|round|flat|"
    r"rock|stone|sand|shell|reef|holm|skerry|inch|eilean|ynys|inis|holy|saint|"
    r"st\.?)\s+"
    r"(?:island|isle|islets?|islet)$",
    re.IGNORECASE,
)
_NON_PHOTO_TITLE_RE = re.compile(
    r"(?:^|[_ \-\(\[])"
    r"(?:flag|coat[_ \-]of[_ \-]arms|logo|map|diagram|chart|icon|badge|"
    r"illustration|drawing|cartoon|clipart|vector|svg|portrait|selfie|"
    r"cosplay|wedding|party|concert|festival)"
    r"(?:$|[_ \-\)\]])",
    re.IGNORECASE,
)


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = val


def island_lon(island: dict) -> float | None:
    lng = island.get("lng")
    if lng is None:
        lng = island.get("lon")
    if isinstance(lng, (int, float)):
        return float(lng)
    return None


def is_generic_island_name(name: str) -> bool:
    raw = (name or "").strip()
    if not raw:
        return True
    low = raw.lower()
    if _GENERIC_NAME_RE.match(low):
        return True
    tokens = re.sub(r"[^\w\s'-]", " ", low).split()
    if len(tokens) == 2 and tokens[-1] in ("island", "isle", "islets", "islet"):
        return True
    if len(low) <= 8 and " " not in low:
        return True
    return False


def geo_max_km(island: dict) -> float:
    return GEO_MAX_KM_GENERIC if is_generic_island_name(island.get("name") or "") else GEO_MAX_KM


def looks_like_non_photo(title: str) -> bool:
    if not title:
        return True
    return bool(_NON_PHOTO_TITLE_RE.search(title))


def save_staging(path: Path, adoptions: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(adoptions, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def dual_signal_ok(
    island: dict,
    *,
    title: str,
    blob: str,
    result_lat: float | None,
    result_lon: float | None,
    mentions_fn,
    name_variants_fn,
    haversine_km_fn,
) -> tuple[bool, dict[str, Any]]:
    """Return (passes, verification dict). Requires name + geo when island has coords."""
    variants = name_variants_fn(island)
    out: dict[str, Any] = {
        "name_match": False,
        "geo_match": False,
        "distance_km": None,
        "generic_name": is_generic_island_name(island.get("name") or ""),
    }
    if not variants:
        out["reason"] = "no-name-variants"
        return False, out

    title_s = (title or "").strip()
    text = f"{title_s} {blob or ''}"
    out["name_match"] = bool(
        mentions_fn(title_s, variants) or mentions_fn(text, variants),
    )
    if not out["name_match"]:
        out["reason"] = "name-not-in-metadata"
        return False, out

    isl_lat = island.get("lat")
    isl_lon = island_lon(island)
    if not (isinstance(isl_lat, (int, float)) and isl_lon is not None):
        out["reason"] = "island-missing-centroid"
        return False, out

    if result_lat is None or result_lon is None:
        out["reason"] = "result-missing-geo"
        return False, out

    try:
        dist = haversine_km_fn(
            float(isl_lat), float(isl_lon), float(result_lat), float(result_lon),
        )
    except (TypeError, ValueError):
        out["reason"] = "invalid-coordinates"
        return False, out

    max_km = geo_max_km(island)
    out["distance_km"] = round(dist, 2)
    if dist > max_km:
        out["reason"] = f"geo-{dist:.1f}-km-exceeds-{max_km:.0f}-km"
        return False, out

    out["geo_match"] = True
    out["reason"] = f"dual-signal: name + geo {dist:.1f} km"
    return True, out


def make_adoption(
    island: dict,
    image_record: dict,
    verification: dict[str, Any],
    *,
    source_label: str,
) -> dict[str, Any]:
    dist = verification.get("distance_km")
    reason = verification.get("reason") or source_label
    if dist is not None:
        reason = f"{source_label}: {reason}"
    return {
        "id": island["id"],
        "image_record": image_record,
        "confidence": CONFIDENCE,
        "reason": reason,
        "verification": {
            "name_match": verification.get("name_match"),
            "geo_match": verification.get("geo_match"),
            "distance_km": verification.get("distance_km"),
        },
    }
