#!/usr/bin/env python3
"""Prove nation_for() on the 26 Oct 2026 location corrections.

Reads coordinates from data/islands.json. Does not rewrite the atlas.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from fetch_islands import NATION_BOXES, nation_for  # noqa: E402

# The general boxes must stay as they were. Overrides sit in front of them.
ORIGINAL_BOXES = [
    ("Crown Dependency", (49.0, -2.7, 49.8, -1.9)),
    ("Crown Dependency", (54.0, -4.85, 54.45, -4.25)),
    ("Northern Ireland", (54.0, -8.2, 55.4, -5.4)),
    ("Ireland", (51.3, -10.6, 55.45, -5.4)),
    ("Wales", (51.3, -5.4, 53.45, -2.65)),
    ("Scotland", (54.6, -8.7, 61.5, -0.7)),
    ("Scotland", (57.5, -10.5, 58.5, -8.0)),
    ("England", (49.5, -6.5, 55.9, 1.9)),
]

SECTION_NATION = {
    1: "England",
    2: "England",
    3: "England",
    4: "Scotland",
    5: "Wales",
    6: "Ireland",
    7: "Ireland",
    8: "Ireland",
    9: "Ireland",
    10: "Ireland",
    11: "Ireland",
    12: "Ireland",
    13: "Ireland",
}

# Already correct in the locations report. nation_for must keep these.
HOLD = {
    "lindisfarne": "England",
    "osm-way-126546636": "Wales",  # Flat Holm
    "osm-way-38867846": "Wales",  # Denny Island
    "osm-way-3098808": "Scotland",  # Hestan Island
    "osm-way-3098796": "Scotland",  # Rough Island at Kippford
    "isle-of-skye": "Scotland",
    "isle-of-wight": "England",
    "osm-relation-6045364": "Ireland",  # Achill
    "osm-relation-3998376": "Northern Ireland",  # Devenish
}


def section_rows() -> list[tuple[int, str]]:
    text = (ROOT / "docs/fact-check/2026-10-26-locations.md").read_text()
    confirmed = text.split("## Suspicions")[0]
    parts = re.split(r"\n### (\d+)\. ", confirmed)
    rows: list[tuple[int, str]] = []
    for i in range(1, len(parts), 2):
        number = int(parts[i])
        if number < 1 or number > 13:
            continue
        for line in parts[i + 1].splitlines():
            if not line.startswith("| `"):
                continue
            rows.append((number, re.findall(r"`([^`]+)`", line)[0]))
    # Section 11 prose, confirmed alongside the Lough Derg table.
    rows.append((11, "wd-Q104348087"))
    return rows


def main() -> None:
    if NATION_BOXES != ORIGINAL_BOXES:
        raise SystemExit("NATION_BOXES changed; the general boxes must stay put")

    islands = json.loads((ROOT / "data/islands.json").read_text())
    by_id = {row["id"]: row for row in islands}
    failures: list[str] = []

    rows = section_rows()
    if len(rows) != 151:
        failures.append(f"expected 151 section rows, parsed {len(rows)}")

    for number, iid in rows:
        rec = by_id.get(iid)
        if rec is None:
            failures.append(f"missing {iid}")
            continue
        got = nation_for(rec["lat"], rec["lng"])
        want = SECTION_NATION[number]
        if got != want:
            failures.append(
                f"section {number} {iid} {rec.get('name')} "
                f"{rec['lat']},{rec['lng']} -> {got}, want {want}"
            )

    for iid, want in HOLD.items():
        rec = by_id[iid]
        got = nation_for(rec["lat"], rec["lng"])
        if got != want:
            failures.append(
                f"hold {iid} {rec.get('name')} {rec['lat']},{rec['lng']} "
                f"-> {got}, want {want}"
            )

    if failures:
        print("\n".join(failures))
        raise SystemExit(f"{len(failures)} nation_for checks failed")
    print(f"ok: {len(rows)} corrected coordinates, {len(HOLD)} holds, boxes unchanged")


if __name__ == "__main__":
    main()
