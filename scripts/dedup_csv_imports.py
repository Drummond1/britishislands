#!/usr/bin/env python3
"""
One-shot fix-up for `merge_csv.py` duplicates.

The first CSV merge run created a handful of duplicate islands (e.g.
"Lewis and Harris" twice, "Skye (An t-Eilean Sgitheanach)" alongside the
existing "Isle of Skye") because the original `normalise_name` didn't
strip the "Isle of …" prefix. The matcher has since been patched; this
script rebuilds the index with the new normalisation, walks the existing
`source: csv-import` entries, and where it finds a strong match (same
loose name + within 30 km) it folds the CSV row's data into the existing
entry and removes the duplicate.

Atomic write of `data/islands.json` with a backup at
`data/islands.json.before-csv-dedup`. Detailed log to
`data/csv_dedup_report.json`.

Run:
    python3 scripts/dedup_csv_imports.py
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

# Reuse the (now-patched) helpers from the merge script.
from merge_csv import (  # noqa: E402
    build_index,
    normalise_name,
    _haversine_km,
    merge_row_into,
)

DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
BACKUP = DATA / "islands.json.before-csv-dedup"
REPORT = DATA / "csv_dedup_report.json"


def atomic_write_json(path: Path, payload) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def main() -> int:
    with open(ISLANDS, encoding="utf-8") as f:
        islands = json.load(f)
    print(f"Loaded {len(islands):,} islands")

    BACKUP.write_text(json.dumps(islands, ensure_ascii=False, indent=2))
    print(f"  backup → {BACKUP.name}")

    non_csv = [i for i in islands if i.get("source") != "csv-import"]
    idx = build_index(non_csv)

    csv_imports = [i for i in islands if i.get("source") == "csv-import"]
    report = {"deduped": [], "kept": []}

    to_remove_ids: set[str] = set()

    for csv_isl in csv_imports:
        cname = csv_isl.get("name", "")
        clat = csv_isl.get("lat")
        clng = csv_isl.get("lng")
        nm = normalise_name(cname)

        candidates = idx.get(nm, [])
        # If the matcher would still see 0 candidates, keep the CSV entry.
        if not candidates:
            report["kept"].append({"id": csv_isl["id"], "name": cname, "reason": "no name match"})
            continue

        # Find the closest candidate (use 30 km tolerance for big-island
        # cases where CSV centroid coords are coarse).
        best, best_d = None, math.inf
        if isinstance(clat, (int, float)) and isinstance(clng, (int, float)):
            for c in candidates:
                if not (isinstance(c.get("lat"), (int, float)) and isinstance(c.get("lng"), (int, float))):
                    continue
                d = _haversine_km(clat, clng, c["lat"], c["lng"])
                if d < best_d:
                    best, best_d = c, d
        if best is None or best_d > 30:
            report["kept"].append(
                {"id": csv_isl["id"], "name": cname, "reason": "no close-coord match"}
            )
            continue

        # Strong match: fold the CSV row into the existing entry.
        prov_csv = (csv_isl.get("provenance") or {}).get("csv") or {}
        original_row = prov_csv.get("row") or {}

        parsed = {
            "archipelago": csv_isl.get("archipelago"),
            "population": csv_isl.get("population"),
            "areaKm2": csv_isl.get("areaKm2"),
            "alt_name": (csv_isl.get("names") or {}).get("alt"),
            "match_reason": "dedup-coord+name",
        }
        filled = merge_row_into(best, original_row, parsed)
        to_remove_ids.add(csv_isl["id"])
        report["deduped"].append(
            {
                "removed_id": csv_isl["id"],
                "merged_into": best["id"],
                "name": cname,
                "distance_km": round(best_d, 2),
                "fields_filled": filled,
            }
        )

    if to_remove_ids:
        islands = [i for i in islands if i.get("id") not in to_remove_ids]

    print(f"\nDedup summary:")
    print(f"  Removed: {len(to_remove_ids)}")
    print(f"  Kept (no good match): {len(report['kept'])}")
    print(f"  Total after dedup: {len(islands):,}")

    atomic_write_json(ISLANDS, islands)
    atomic_write_json(REPORT, report)
    print(f"\nWrote {ISLANDS}")
    print(f"Wrote {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
