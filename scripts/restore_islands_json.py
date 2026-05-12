#!/usr/bin/env python3
"""One-shot recovery from a corrupted ``data/islands.json``.

The corruption was detected on 2026-05-11: the file was truncated to
~6 MB with an unterminated string at line 223562. The most recent
verified-good backup is ``islands.json.before-csv-geocode`` (8.0 MB,
6,748 islands). The csv-geocode step that ran after that backup
adopted 28 new entries; those adoptions are fully captured in
``data/csv_geocode_report.json`` so we can replay them without any
further Wikidata calls.

This script is idempotent: if you run it twice, the second run is a
no-op (duplicate-id guard).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
TARGET = DATA / "islands.json"
BACKUP = DATA / "islands.json.before-csv-geocode"
REPORT = DATA / "csv_geocode_report.json"

REGION_TO_NATION = {
    "Outer Hebrides (Scotland)": "Scotland",
    "Inner Hebrides (Scotland)": "Scotland",
    "Argyll (Scotland)":         "Scotland",
    "Firth of Clyde (Scotland)": "Scotland",
    "Orkney (Scotland)":         "Scotland",
    "Shetland (Scotland)":       "Scotland",
    "Scottish Lochs":            "Scotland",
    "North Wales":               "Wales",
    "South Wales":               "Wales",
    "England":                   "England",
    "Northern Ireland":          "Northern Ireland",
    "Ireland (RoI)":             "Ireland",
    "Isle of Man":               "Isle of Man",
    "Channel Islands":           "Crown Dependency",
    "France (within 50 mi)":     "France",
}
REGION_TO_ARCH = {
    "Outer Hebrides (Scotland)": "Outer Hebrides",
    "Inner Hebrides (Scotland)": "Inner Hebrides",
    "Orkney (Scotland)":         "Orkney",
    "Shetland (Scotland)":       "Shetland",
    "Channel Islands":           "Channel Islands",
}


def _atomic_write(path: Path, payload) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, path)


def main() -> int:
    if not BACKUP.exists():
        print(f"FATAL: backup {BACKUP} missing", file=sys.stderr)
        return 2

    # Safety: archive the corrupted file before overwriting.
    if TARGET.exists():
        try:
            with open(TARGET, encoding="utf-8") as f:
                json.load(f)
            print(f"{TARGET} parses OK; nothing to recover.")
            return 0
        except json.JSONDecodeError as exc:
            ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            archive = TARGET.with_name(f"islands.json.corrupt-{ts}")
            shutil.copy2(TARGET, archive)
            print(f"Archived corrupted file → {archive.name}\n  reason: {exc}")

    islands = json.loads(BACKUP.read_text(encoding="utf-8"))
    if not isinstance(islands, list):
        print(f"FATAL: backup is not a list ({type(islands).__name__})", file=sys.stderr)
        return 2
    base = len(islands)
    print(f"Loaded backup with {base:,} islands")

    if not REPORT.exists():
        print(f"WARN: no csv geocode report; restoring backup verbatim")
        _atomic_write(TARGET, islands)
        return 0

    rpt = json.loads(REPORT.read_text(encoding="utf-8"))
    adoptions = rpt.get("adopted") or []
    print(f"Re-applying {len(adoptions)} csv-geocoded adoptions…")

    # Load the original csv import report so we can recover the
    # row's nation/archipelago by name lookup.
    csv_rpt_path = DATA / "csv_import_report.json"
    skipped_by_name = {}
    if csv_rpt_path.exists():
        try:
            csv_rpt = json.loads(csv_rpt_path.read_text(encoding="utf-8"))
            for row in csv_rpt.get("skipped_no_coords_no_match") or []:
                skipped_by_name[row.get("name", "")] = row
        except Exception:
            pass

    existing_ids = {i.get("id") for i in islands}
    existing_qids = {(i.get("wikidata") or "").strip() for i in islands}

    added = 0
    for a in adoptions:
        iid = a.get("id")
        qid = a.get("qid")
        coord = a.get("coord") or []
        label = a.get("label") or a.get("row_name") or ""
        row_name = a.get("row_name") or ""
        if not iid or not qid or len(coord) != 2:
            continue
        if iid in existing_ids or qid in existing_qids:
            continue
        src_row = skipped_by_name.get(row_name) or {}
        region = src_row.get("region") or ""
        nation = REGION_TO_NATION.get(region, "")
        archipelago = REGION_TO_ARCH.get(region, src_row.get("location") or "")
        new_island = {
            "id": iid,
            "name": label or row_name,
            "nation": nation,
            "archipelago": archipelago,
            "lat": float(coord[0]),
            "lng": float(coord[1]),
            "type": "sea",
            "areaKm2": None,
            "population": None,
            "shortDescription": "",
            "longDescription": "",
            "tags": [],
            "source": "csv-geocoded",
            "sources": ["csv-geocoded", f"wikidata:{qid}"],
            "wikidata": qid,
            "images": [],
        }
        islands.append(new_island)
        existing_ids.add(iid)
        existing_qids.add(qid)
        added += 1

    print(f"  added {added} new islands → total {len(islands):,}")
    _atomic_write(TARGET, islands)
    # Sanity: load it back.
    re = json.load(open(TARGET, encoding="utf-8"))
    if len(re) != len(islands):
        print(f"FATAL: post-write read count {len(re)} != expected {len(islands)}", file=sys.stderr)
        return 2
    print(f"OK: {TARGET.relative_to(ROOT)} now holds {len(re):,} islands")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
