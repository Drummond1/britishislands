#!/usr/bin/env python3
"""
Weekly property discovery orchestrator.

1. Optionally merge tier-4 obscure research and apply new islands
2. Re-verify URLs on existing manifest (light pass)
3. Sync curated → islands.json
4. Update registry + docs/FOR-SALE-ISLANDS.md

Usage:
  python3 scripts/run_property_discovery_weekly.py
  python3 scripts/run_property_discovery_weekly.py --apply-tier4
  python3 scripts/run_property_discovery_weekly.py --registry-only
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TIER4_RAW = ROOT / "data" / "discovery" / "property_tier4_obscure_raw.json"


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd, cwd=ROOT)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--apply-tier4",
        action="store_true",
        help="Run discover on property_tier4_obscure_raw.json and apply new islands",
    )
    ap.add_argument(
        "--registry-only",
        action="store_true",
        help="Only rebuild registry/docs from current islands.json",
    )
    ap.add_argument("--delay", type=float, default=1.2, help="Seconds between URL checks")
    args = ap.parse_args()

    py = sys.executable
    source = "registry_only"

    if not args.registry_only:
        if args.apply_tier4 and TIER4_RAW.is_file():
            run([
                py,
                str(ROOT / "scripts/discover_property_tier3.py"),
                "--apply",
                "--raw",
                str(TIER4_RAW),
                "--tier-label",
                "Tier 4",
                "--delay",
                str(args.delay),
            ])
            source = "tier4_apply"
        elif args.apply_tier4:
            print(f"No tier-4 raw file at {TIER4_RAW} — skip discover", flush=True)

        run([py, str(ROOT / "scripts/sync_curated_property_listings.py")])

    run([py, str(ROOT / "scripts/property_listings_registry.py"), "--update", "--print"])

    verified = json.loads(
        (ROOT / "data/discovery/property_listings_verified.json").read_text(encoding="utf-8")
    )
    n = len(verified.get("verified") or [])
    run([
        py,
        str(ROOT / "scripts/property_listings_registry.py"),
        "--record-run",
        json.dumps({"source": source, "verifiedCount": n}),
    ])

    print(f"\n✓ Weekly property pass complete. {n} verified islands.", flush=True)
    print("  Full list: docs/FOR-SALE-ISLANDS.md", flush=True)
    print("  Registry:  data/discovery/property_listings_registry.json", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
