#!/usr/bin/env python3
"""
Emit data/islands_index.json — compact first paint for the web app.

Strips long prose, full sources, and image galleries. The browser fetches this
before data/islands.json and merges full records in place (see app.js loadIslands).

Run after any change to data/islands.json:
  python3 scripts/build_islands_index.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Omitted from index; merged later from islands.json.
DROP_KEYS = frozenset(
    {
        "history",
        "geography",
        "transport",
        "accommodation",
        "sources",
        "provenance",
        "images",
    }
)


def slim_record(island: dict) -> dict:
    return {k: v for k, v in island.items() if k not in DROP_KEYS}


def main() -> None:
    src = ROOT / "data" / "islands.json"
    out = ROOT / "data" / "islands_index.json"
    data = json.loads(src.read_text(encoding="utf-8"))
    slim = [slim_record(x) for x in data]
    out.write_text(
        json.dumps(slim, separators=(",", ":"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {len(slim)} rows -> {out.name} "
        f"({out.stat().st_size / 1024 / 1024:.2f} MiB); "
        f"full {src.name} {src.stat().st_size / 1024 / 1024:.2f} MiB",
    )


if __name__ == "__main__":
    main()
