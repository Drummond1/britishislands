#!/usr/bin/env python3
"""
Orchestrate the five-agent island discovery pipeline.

Stages:
  1. map_scanner       — OSM coastline / offshore feature scan
  2. source_verifier   — Wikidata / Wikipedia / OSM provenance check
  3. photo_finder      — licence-safe Commons / pageimage harvest
  4. enricher          — schema-shaped records + review flags
  5. site_update       — gated merge into data/islands.json

Default behaviour is review-first: no writes to islands.json unless
`--apply` is passed to the site_update stage (or the full pipeline with
`--apply`).

Examples:
    python3 scripts/discover_islands_pipeline.py
    python3 scripts/discover_islands_pipeline.py --stage=map_scanner --no-cache
    python3 scripts/discover_islands_pipeline.py --stage=site_update --apply
    python3 scripts/discover_islands_pipeline.py --limit=50
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from discovery import enricher, map_scanner, photo_finder, site_update, source_verifier


STAGES = (
    "map_scanner",
    "source_verifier",
    "photo_finder",
    "enricher",
    "site_update",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the island discovery pipeline.")
    parser.add_argument(
        "--stage",
        choices=STAGES,
        help="Run a single stage instead of the full pipeline.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Cap records processed per stage.")
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass the Overpass cache for map_scanner.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Allow site_update to write new islands into data/islands.json.",
    )
    parser.add_argument(
        "--include-uncertain",
        action="store_true",
        help="Let site_update consider records flagged for manual review.",
    )
    return parser.parse_args()


def run_stage(name: str, args: argparse.Namespace) -> None:
    if name == "map_scanner":
        map_scanner.run(use_cache=not args.no_cache, limit=args.limit)
        return
    if name == "source_verifier":
        source_verifier.run(limit=args.limit)
        return
    if name == "photo_finder":
        photo_finder.run(limit=args.limit)
        return
    if name == "enricher":
        enricher.run(limit=args.limit)
        return
    if name == "site_update":
        site_update.run(apply=args.apply, include_uncertain=args.include_uncertain)
        return
    raise ValueError(f"Unknown stage: {name}")


def main() -> None:
    args = parse_args()
    stages = [args.stage] if args.stage else list(STAGES)
    for name in stages:
        print(f"=== {name} ===", file=sys.stderr)
        run_stage(name, args)


if __name__ == "__main__":
    main()
