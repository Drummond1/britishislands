#!/usr/bin/env python3
"""
Merge the user-provided CSV
    /Users/drummondgilberta2aa9/Desktop/british_isles_50mile_islands - british_isles_50mile_islands.csv.csv
into data/islands.json.

Rules of the road (mirrors docs/ETHICS.md and DATA-SCHEMA.md):

  * **Never overwrite** stronger provenance. Curated entries are the
    strongest; OSM entries are medium; CSV is weaker. We only ever
    fill empty fields.
  * **Match strategy**: case-insensitive name (incl. parenthetical
    alt-names stripped) AND a 5 km haversine sanity check when CSV
    coords are parseable. Lower threshold for tiny islands.
  * **Aggregate rows** (e.g. "Shetland aggregate") and rows without
    parseable coords AND no name match are skipped, reported, and not
    added — they would be ghost entries.
  * Atomic write via tmp+rename, with a backup of the pre-merge file
    saved as `data/islands.json.before-csv-merge`.
  * Refuses to run while v3 enrichment is still mutating islands.json.

Outputs:
  * data/islands.json (updated in place, atomically)
  * data/islands.json.before-csv-merge (backup)
  * data/csv_import_report.json (per-row outcome)

Run:
    python3 scripts/merge_csv.py
"""

from __future__ import annotations

import csv
import json
import math
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
ISLANDS_PATH = DATA_DIR / "islands.json"
BACKUP_PATH = DATA_DIR / "islands.json.before-csv-merge"
REPORT_PATH = DATA_DIR / "csv_import_report.json"
CSV_PATH = Path(
    "/Users/drummondgilberta2aa9/Desktop/"
    "british_isles_50mile_islands - british_isles_50mile_islands.csv.csv"
)


# ---------- coord parsing ----------

DMS_RE = re.compile(
    r"(?P<deg>\d{1,3})\s*°"
    r"(?:\s*(?P<min>\d{1,2})\s*['′])?"
    r"(?:\s*(?P<sec>\d{1,2}(?:\.\d+)?)\s*[\"″])?"
    r"\s*(?P<hem>[NSEW])"
)


def parse_dms_pair(s: str) -> Optional[tuple[float, float]]:
    """Parse a "lat lng" DMS string. Returns (lat, lng) or None."""
    if not s:
        return None
    matches = list(DMS_RE.finditer(s))
    if len(matches) < 2:
        return None
    lat = lng = None
    for m in matches[:2]:
        deg = int(m.group("deg"))
        minutes = int(m.group("min") or 0)
        seconds = float(m.group("sec") or 0)
        hem = m.group("hem")
        val = deg + minutes / 60.0 + seconds / 3600.0
        if hem in ("S", "W"):
            val = -val
        if hem in ("N", "S"):
            lat = val
        else:
            lng = val
    if lat is None or lng is None:
        return None
    return (lat, lng)


# ---------- area parsing ----------

AREA_KM2_RE = re.compile(r"([\d,]+(?:\.\d+)?)\s*km²")
AREA_HA_RE = re.compile(r"([\d,]+(?:\.\d+)?)\s*ha\b")
AREA_M2_RE = re.compile(r"([\d,]+(?:\.\d+)?)\s*m²")


def parse_area_km2(s: str) -> Optional[float]:
    if not s:
        return None
    if m := AREA_KM2_RE.search(s):
        return float(m.group(1).replace(",", ""))
    if m := AREA_HA_RE.search(s):
        return float(m.group(1).replace(",", "")) / 100.0
    if m := AREA_M2_RE.search(s):
        return float(m.group(1).replace(",", "")) / 1_000_000.0
    return None


# ---------- population parsing ----------

POP_RE = re.compile(
    r"\bpop(?:ulation|\.)?\s*(?:~|approx\.?\s*|approximately\s*)?[:\s]?\s*"
    r"([\d,]+)",
    re.IGNORECASE,
)


def parse_population(notes: str) -> Optional[int]:
    if not notes:
        return None
    m = POP_RE.search(notes)
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", ""))
    except ValueError:
        return None


# ---------- region → nation/archipelago ----------

REGION_MAP = {
    "Outer Hebrides (Scotland)": ("Scotland", "Outer Hebrides"),
    "Inner Hebrides (Scotland)": ("Scotland", "Inner Hebrides"),
    "Orkney (Scotland)": ("Scotland", "Orkney"),
    "Shetland (Scotland)": ("Scotland", "Shetland"),
    "Firth of Clyde (Scotland)": ("Scotland", "Firth of Clyde"),
    "Firth of Forth (Scotland)": ("Scotland", "Firth of Forth"),
    "Solway Firth / SW Scotland": ("Scotland", "Solway Firth"),
    "North/West Coast Scotland outliers": ("Scotland", None),
    "Wales": ("Wales", None),
    "England": ("England", None),
    "Isle of Man": ("Crown Dependency", "Isle of Man"),
    "Channel Islands (Crown Dependencies)": ("Crown Dependency", "Channel Islands"),
    "French islands within ~50 miles of British Isles": ("France", None),
}


def classify_ireland(notes: str, name: str, coords: Optional[tuple[float, float]]) -> str:
    """Decide Ireland-RoI vs Northern Ireland.

    Heuristic priority:
      1. Note text mentions an NI county / town → Northern Ireland.
      2. Coords inside the NI bbox → Northern Ireland.
      3. Otherwise → Ireland (Republic).
    """
    ni_keywords = (
        "antrim", "down", "armagh", "tyrone", "fermanagh", "londonderry",
        "derry", "belfast", "strangford", "lough neagh", "rathlin", "northern ireland",
    )
    haystack = (notes or "").lower() + " " + (name or "").lower()
    if any(k in haystack for k in ni_keywords):
        return "Northern Ireland"
    if coords:
        lat, lng = coords
        if 54.0 <= lat <= 55.3 and -8.2 <= lng <= -5.4:
            return "Northern Ireland"
    return "Ireland"


# ---------- matching ----------


def slugify(name: str) -> str:
    n = unicodedata.normalize("NFKD", name)
    n = n.encode("ascii", "ignore").decode()
    n = n.lower()
    n = re.sub(r"[^\w\s\-]+", "", n)
    n = re.sub(r"\s+", "-", n).strip("-")
    return n or "island"


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    to_rad = math.pi / 180.0
    dlat = (lat2 - lat1) * to_rad
    dlng = (lng2 - lng1) * to_rad
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1 * to_rad) * math.cos(lat2 * to_rad) * math.sin(dlng / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def normalise_name(name: str) -> str:
    """Lowercase + strip parenthetical alt-name + drop generic prefixes
    ("Isle of", "Island of", "Isles of", "The ") and the trailing generic
    suffix (" island", " islands", " isle", " isles") so that
    "Isle of Skye", "Skye", and "Sanda Island" / "Sanda" all collapse to
    the same key. Collapse whitespace at the end."""
    n = re.sub(r"\([^)]*\)", "", name)  # drop "(Uibhist a Tuath)" etc.
    n = unicodedata.normalize("NFKD", n)
    n = n.encode("ascii", "ignore").decode()
    n = re.sub(r"[^a-z0-9 ]+", " ", n.lower())
    n = re.sub(r"\s+", " ", n).strip()
    n = re.sub(r"^(?:the |isles? of |island of )", "", n)
    n = re.sub(r"\s+(?:islands?|isles?)$", "", n)
    return n


def alt_name_from_parenthetical(name: str) -> Optional[str]:
    m = re.search(r"\(([^)]+)\)", name)
    if not m:
        return None
    alt = m.group(1).strip()
    if not alt or alt.lower() in {"hi", "lt", "ht"}:
        return None
    # Drop noisy parentheticals like "(Grande Île + ~52 named islets at HT, ~365 at LT)".
    if any(t in alt for t in (";", "+", "~", "km", "miles", "mi", "hectares", "ha")):
        return None
    return alt


def build_index(islands: list[dict]) -> dict[str, list[dict]]:
    """Index islands by normalised name for fast match lookups."""
    idx: dict[str, list[dict]] = {}
    for isl in islands:
        nm = normalise_name(isl.get("name", ""))
        if not nm:
            continue
        idx.setdefault(nm, []).append(isl)
    return idx


def find_match(
    row_name: str,
    coords: Optional[tuple[float, float]],
    idx: dict[str, list[dict]],
) -> Optional[tuple[dict, str]]:
    """Return (matched_island, match_reason) or None."""
    nm = normalise_name(row_name)
    if not nm:
        return None
    candidates = idx.get(nm, [])
    if not candidates:
        return None

    # Single hit and either no coords on CSV side, or coords agree within 25 km.
    if len(candidates) == 1:
        c = candidates[0]
        if coords is None or (
            isinstance(c.get("lat"), (int, float))
            and isinstance(c.get("lng"), (int, float))
            and _haversine_km(coords[0], coords[1], c["lat"], c["lng"]) <= 25.0
        ):
            return (c, "name" if coords is None else "name+coord")
        return None

    # Multiple candidates by name (e.g. several "Mew Island"s) — disambiguate
    # by coordinate if we can; else give up.
    if coords is None:
        return None
    best, best_d = None, math.inf
    for c in candidates:
        if not (
            isinstance(c.get("lat"), (int, float))
            and isinstance(c.get("lng"), (int, float))
        ):
            continue
        d = _haversine_km(coords[0], coords[1], c["lat"], c["lng"])
        if d < best_d:
            best, best_d = c, d
    if best is not None and best_d <= 10.0:
        return (best, "name+coord")
    return None


# ---------- merge ----------


def fill_missing(target: dict, src: dict, fields: tuple[str, ...]) -> list[str]:
    """Copy fields from src into target only when target's value is empty.

    Returns the names of fields actually filled (for the report).
    """
    filled = []
    for f in fields:
        v = src.get(f)
        if v in (None, "", [], {}):
            continue
        cur = target.get(f)
        if cur in (None, "", [], {}, 0):
            target[f] = v
            filled.append(f)
    return filled


def merge_row_into(island: dict, row: dict, parsed: dict) -> list[str]:
    """Merge a parsed CSV row into an existing island record. Returns the
    fields actually mutated."""
    filled: list[str] = []
    if not island.get("archipelago") and parsed.get("archipelago"):
        island["archipelago"] = parsed["archipelago"]
        filled.append("archipelago")
    if (island.get("population") in (None, 0)) and parsed.get("population"):
        island["population"] = parsed["population"]
        filled.append("population")
    if not island.get("areaKm2") and parsed.get("areaKm2"):
        # Sanity: don't accept an area absurdly larger than the largest
        # known British island (~8,400 km², ROI of Ireland combined). Skip
        # values >10000.
        if parsed["areaKm2"] <= 10000:
            island["areaKm2"] = parsed["areaKm2"]
            filled.append("areaKm2")
    # Attach the original CSV row + any alt name to provenance.
    prov = island.setdefault("provenance", {})
    csv_block = {
        "row": {k: v for k, v in row.items() if v},
        "merged_via": parsed["match_reason"],
    }
    if not isinstance(prov.get("csv"), dict):
        prov["csv"] = csv_block
        filled.append("provenance.csv")
    if parsed.get("alt_name"):
        names = island.setdefault("names", {})
        if "alt" not in names:
            names["alt"] = parsed["alt_name"]
            filled.append("names.alt")
    if row.get("Notes") and not island.get("shortDescription"):
        # Only set if shortDescription is missing — never overwrite curated.
        island["shortDescription"] = row["Notes"].strip()
        filled.append("shortDescription")
    return filled


def make_new_island(row: dict, parsed: dict) -> dict:
    nation = parsed["nation"]
    archipelago = parsed.get("archipelago")
    coords = parsed["coords"]
    isl = {
        "id": parsed["id"],
        "name": parsed["name"],
        "nation": nation,
        "type": "sea",  # CSV doesn't tell us inland; safe default for offshore.
        "lat": coords[0],
        "lng": coords[1],
        "source": "csv-import",
        "provenance": {
            "csv": {
                "row": {k: v for k, v in row.items() if v},
                "merged_via": "new",
            }
        },
    }
    if archipelago:
        isl["archipelago"] = archipelago
    if parsed.get("areaKm2"):
        isl["areaKm2"] = parsed["areaKm2"]
    if parsed.get("population"):
        isl["population"] = parsed["population"]
    if row.get("Notes"):
        isl["shortDescription"] = row["Notes"].strip()
    if parsed.get("alt_name"):
        isl["names"] = {"alt": parsed["alt_name"]}
    return isl


# ---------- safety: refuse to run while v3 is writing ----------


def v3_is_running() -> Optional[int]:
    try:
        out = subprocess.check_output(["pgrep", "-f", "enrich_images_v3.py"], text=True)
        pids = [int(p) for p in out.strip().splitlines() if p.strip()]
        return pids[0] if pids else None
    except subprocess.CalledProcessError:
        return None
    except FileNotFoundError:
        return None


# ---------- main ----------


def atomic_write_json(path: Path, payload, *, indent=2) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=indent)
    os.replace(tmp, path)


def main() -> int:
    pid = v3_is_running()
    if pid is not None:
        print(
            f"REFUSING TO RUN: enrich_images_v3.py is still active (PID {pid}). "
            "Wait for it to finish or kill it cleanly before running this merge.",
            file=sys.stderr,
        )
        return 1

    if not CSV_PATH.exists():
        print(f"CSV not found at {CSV_PATH}", file=sys.stderr)
        return 1

    print(f"Loading {ISLANDS_PATH}…")
    with open(ISLANDS_PATH, "r", encoding="utf-8") as f:
        islands = json.load(f)
    print(f"  {len(islands):,} islands loaded")

    # Backup before mutating.
    BACKUP_PATH.write_text(json.dumps(islands, ensure_ascii=False, indent=2))
    print(f"  backup → {BACKUP_PATH.name}")

    idx = build_index(islands)

    report = {
        "csv_path": str(CSV_PATH),
        "rows_total": 0,
        "matched_filled": [],     # rows that matched existing entries and filled ≥1 field
        "matched_no_op": [],      # rows that matched but had nothing to fill
        "added": [],              # newly imported rows
        "skipped_aggregate": [],
        "skipped_no_coords_no_match": [],
        "warnings": [],
    }

    new_islands: list[dict] = []

    with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            report["rows_total"] += 1
            name = (row.get("Name") or "").strip()
            region = (row.get("Region/Archipelago") or "").strip()
            size_raw = (row.get("Estimated Size") or "").strip()
            location_raw = (row.get("Location") or "").strip()
            notes = (row.get("Notes") or "").strip()
            if not name:
                continue

            # Skip explicit aggregates — they're not single islands.
            if "Regional aggregates" in region or "aggregate" in name.lower():
                report["skipped_aggregate"].append({"name": name, "region": region})
                continue

            coords = parse_dms_pair(location_raw)
            area_km2 = parse_area_km2(size_raw)
            population = parse_population(notes)

            # Map region → nation / archipelago.
            if region in REGION_MAP:
                nation, archipelago = REGION_MAP[region]
            elif region == "Ireland (RoI & NI)":
                nation = classify_ireland(notes, name, coords)
                archipelago = None
            else:
                nation, archipelago = "British Isles", None

            parsed = {
                "name": name,
                "coords": coords,
                "areaKm2": area_km2,
                "population": population,
                "nation": nation,
                "archipelago": archipelago,
                "alt_name": alt_name_from_parenthetical(name),
                "id": slugify(name),
                "match_reason": None,
            }

            match = find_match(name, coords, idx)
            if match is not None:
                island, reason = match
                parsed["match_reason"] = reason
                filled = merge_row_into(island, row, parsed)
                if filled:
                    report["matched_filled"].append(
                        {
                            "name": name,
                            "matched_id": island.get("id"),
                            "via": reason,
                            "filled": filled,
                        }
                    )
                else:
                    report["matched_no_op"].append(
                        {"name": name, "matched_id": island.get("id"), "via": reason}
                    )
                continue

            # No match: only add if we have coordinates.
            if coords is None:
                report["skipped_no_coords_no_match"].append(
                    {"name": name, "region": region, "location": location_raw}
                )
                continue

            parsed["match_reason"] = "new"
            new_isl = make_new_island(row, parsed)
            # Avoid id collisions with existing entries.
            base_id = new_isl["id"]
            n = 1
            while any(i.get("id") == new_isl["id"] for i in islands) or any(
                i.get("id") == new_isl["id"] for i in new_islands
            ):
                n += 1
                new_isl["id"] = f"{base_id}-{n}"
            new_islands.append(new_isl)
            report["added"].append(
                {
                    "id": new_isl["id"],
                    "name": name,
                    "nation": nation,
                    "lat": coords[0],
                    "lng": coords[1],
                }
            )

    if new_islands:
        islands.extend(new_islands)

    print(f"Rows total:                {report['rows_total']}")
    print(f"  Matched + filled:        {len(report['matched_filled'])}")
    print(f"  Matched (no-op):         {len(report['matched_no_op'])}")
    print(f"  Added new entries:       {len(report['added'])}")
    print(f"  Skipped (aggregates):    {len(report['skipped_aggregate'])}")
    print(f"  Skipped (no coord/no match): {len(report['skipped_no_coords_no_match'])}")

    atomic_write_json(ISLANDS_PATH, islands)
    atomic_write_json(REPORT_PATH, report)
    print(f"\nWrote {ISLANDS_PATH} ({len(islands):,} islands)")
    print(f"Wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
