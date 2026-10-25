"""Shared helpers for unnamed-island name proposal staging."""

from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
STAGING_DIR = DATA / "staging" / "name_proposals"
VERIFIED_DIR = DATA / "staging" / "name_proposals-verified"

GENERIC_NAME_RE = re.compile(
    r"^(?:unnamed\s+island|unknown\s+island|island|islet|rock|skerry|holm)$",
    re.I,
)

TIER_MAX_DISTANCE_M = {
    "A": 150,
    "B": 200,
    "C": 500,
}


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return haversine_km(lat1, lon1, lat2, lon2) * 1000.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = val


def load_islands() -> list[dict[str, Any]]:
    return json.loads(ISLANDS.read_text(encoding="utf-8"))


def load_unnamed(*, nation: str = "") -> list[dict[str, Any]]:
    out = [
        i
        for i in load_islands()
        if i.get("nameStatus") == "unknown"
        or (i.get("name") or "").strip().lower() == "unnamed island"
    ]
    if nation:
        out = [i for i in out if (i.get("nation") or "") == nation]
    return out


def island_lon(island: dict) -> float | None:
    lng = island.get("lng")
    if lng is None:
        lng = island.get("lon")
    return float(lng) if isinstance(lng, (int, float)) else None


def is_usable_name(name: str) -> bool:
    raw = (name or "").strip()
    if len(raw) < 2:
        return False
    if GENERIC_NAME_RE.match(raw):
        return False
    return True


def pick_english_name(
    tags: dict[str, str],
    *,
    wikidata_label: str = "",
) -> tuple[str, dict[str, str]]:
    """Return (english, alternates by lang code)."""
    alternates: dict[str, str] = {}
    for key, val in tags.items():
        if not val or not isinstance(val, str):
            continue
        if key.startswith("name:") and len(key) == 7:
            alternates[key[5:]] = val.strip()
    for lang in ("gd", "ga", "cy", "gv", "kw", "sco"):
        if lang in alternates and lang not in alternates:
            pass
    english = (
        tags.get("name:en")
        or tags.get("name")
        or tags.get("official_name")
        or wikidata_label
        or tags.get("loc_name")
        or tags.get("alt_name")
        or ""
    ).strip()
    if not english and alternates.get("en"):
        english = alternates["en"]
    return english, alternates


def build_proposal(
    island: dict,
    *,
    proposed_name: str,
    source: str,
    licence: str,
    source_page_url: str,
    confidence_tier: str,
    name_confidence: str,
    distance_m: float | None = None,
    source_ref: str = "",
    alternate_names: dict[str, str] | None = None,
    dual_source: bool = False,
    inference_method: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not is_usable_name(proposed_name):
        return None
    lat = island.get("lat")
    lon = island_lon(island)
    row: dict[str, Any] = {
        "id": island.get("id"),
        "islandId": island.get("id"),
        "proposedName": proposed_name.strip(),
        "nameConfidence": name_confidence,
        "confidenceTier": confidence_tier,
        "source": source,
        "sourceRef": source_ref,
        "sourcePageUrl": source_page_url,
        "licence": licence,
        "retrievedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "dualSource": bool(dual_source),
        "nation": island.get("nation"),
        "lat": lat,
        "lng": lon,
    }
    if distance_m is not None:
        row["distanceM"] = round(distance_m, 1)
    if alternate_names:
        row["alternateNames"] = {k: v for k, v in alternate_names.items() if v}
    if inference_method:
        row["inferenceMethod"] = inference_method
    if extra:
        row.update(extra)
    return row


def save_staging(path: Path, proposals: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(proposals, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def spatial_index(
    points: list[dict[str, Any]],
    *,
    lat_key: str = "lat",
    lon_key: str = "lon",
    cell: float = 0.02,
) -> dict[tuple[int, int], list[dict[str, Any]]]:
    grid: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for pt in points:
        lat, lon = pt.get(lat_key), pt.get(lon_key)
        if lat is None or lon is None:
            continue
        key = (int(float(lat) / cell), int(float(lon) / cell))
        grid.setdefault(key, []).append(pt)
    return grid


def nearest_in_index(
    lat: float,
    lon: float,
    index: dict[tuple[int, int], list[dict[str, Any]]],
    *,
    max_m: float,
    cell: float = 0.02,
    lat_key: str = "lat",
    lon_key: str = "lon",
) -> tuple[dict[str, Any] | None, float]:
    cx, cy = int(lat / cell), int(lon / cell)
    best: tuple[float, dict[str, Any]] | None = None
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for pt in index.get((cx + dx, cy + dy), []):
                plat, plon = pt.get(lat_key), pt.get(lon_key)
                if plat is None or plon is None:
                    continue
                d = haversine_m(lat, lon, float(plat), float(plon))
                if d <= max_m and (best is None or d < best[0]):
                    best = (d, pt)
    if not best:
        return None, 9999.0
    return best[1], best[0]
