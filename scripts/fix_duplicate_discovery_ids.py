#!/usr/bin/env python3
"""
Reassign duplicate name-slug ids (e.g. four rows all named ``sgeir-dhubh``) to
unique ``osm-{type}-{id}`` ids. Discovery used bare slugify(name) before OSM ids
were wired in — the web app then merged every homonym stub from the same shard
row and stacked multiple markers at one coordinate.

Run after editing islands.json:
  python3 scripts/fix_duplicate_discovery_ids.py
  python3 scripts/build_islands_index.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ISLANDS = ROOT / "data" / "islands.json"
REPORT = ROOT / "data" / "duplicate_id_fix_report.json"

sys.path.insert(0, str(ROOT / "scripts"))
from discovery.common import canonical_island_id  # noqa: E402


def main() -> None:
    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    counts = Counter(row["id"] for row in islands)
    dup_ids = {row_id for row_id, n in counts.items() if n > 1}
    existing = {row["id"] for row in islands}

    changes: list[dict] = []
    for row in islands:
        if row["id"] not in dup_ids:
            continue
        new_id = canonical_island_id(row)
        if new_id == row["id"]:
            print(f"  skip {row['id']} — no better id (osm/wikidata missing)", file=sys.stderr)
            continue
        if new_id in existing and new_id != row["id"]:
            print(f"  conflict: {row['id']} → {new_id} already taken", file=sys.stderr)
            sys.exit(1)
        old_id = row["id"]
        row["id"] = new_id
        existing.add(new_id)
        changes.append(
            {
                "oldId": old_id,
                "newId": new_id,
                "name": row.get("name"),
                "osmId": row.get("osmId"),
                "lat": row.get("lat"),
                "lng": row.get("lng"),
            }
        )

    if not changes:
        print("No duplicate ids to fix.")
        return

    backup = ISLANDS.with_name(
        f"islands.json.before-id-fix-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )
    backup.write_text(ISLANDS.read_text(encoding="utf-8"), encoding="utf-8")
    ISLANDS.write_text(json.dumps(islands, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "duplicateIdGroups": len(dup_ids),
        "reassigned": changes,
        "backupPath": str(backup.relative_to(ROOT)),
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Reassigned {len(changes)} rows across {len(dup_ids)} duplicate-id groups → {REPORT.name}")


if __name__ == "__main__":
    main()
