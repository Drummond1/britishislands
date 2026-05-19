#!/usr/bin/env python3
"""Copy verified research manifest into curated_property_listings.json and run ingest."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERIFIED = ROOT / "data" / "discovery" / "property_listings_verified.json"
CURATED = ROOT / "data" / "curated_property_listings.json"


def main() -> int:
    data = json.loads(VERIFIED.read_text(encoding="utf-8"))
    listings = data.get("verified") or []
    if not listings:
        print("No verified listings in manifest", file=sys.stderr)
        return 1
    out = {
        "meta": {
            "version": 2,
            "description": (
                "Maintainer-curated outbound links only — each row must name a specific "
                "island on a live broker page. No generic portal searches."
            ),
            "updatedAt": data.get("researchedAt", ""),
            "researchFile": "data/discovery/property_listings_verified.json",
        },
        "listings": listings,
    }
    CURATED.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {CURATED} ({len(listings)} listings)")
    for cmd in (
        [sys.executable, str(ROOT / "scripts/ingest_property_listings.py"), "--source", "curated", "--commit"],
        [sys.executable, str(ROOT / "scripts/apply_enrichments.py"), "--apply", "--only", "property", "--force"],
        [sys.executable, str(ROOT / "scripts/build_islands_index.py")],
    ):
        print("+", " ".join(cmd))
        subprocess.check_call(cmd, cwd=ROOT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
