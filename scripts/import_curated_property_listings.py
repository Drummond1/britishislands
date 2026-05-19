#!/usr/bin/env python3
"""Merge curated_property_listings.json into cache_property_listings.json."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    script = ROOT / "scripts" / "ingest_property_listings.py"
    cmd = [
        sys.executable,
        str(script),
        "--source",
        "curated",
        "--commit",
    ]
    if "--dry-run" in sys.argv:
        cmd.append("--dry-run")
    print("Running:", " ".join(cmd))
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
