#!/usr/bin/env python3
"""Orchestrator that re-runs every automated ferry-data source in the
right order and re-emits the SEO landing pages.

Designed to be scheduled monthly (e.g. via cron / GitHub Actions). After
each step it logs to ``logs/refresh_ferries.log`` and flags stale routes
(``lastVerified`` older than ``STALE_DAYS_HARD``) in
``data/ferries_stale_report.json`` so a human can re-validate.

Stages (skippable with ``--skip <stage>``)::

    osm       -> scripts/fetch_ferries_osm.py
    gtfs      -> scripts/import_calmac_gtfs.py per Scottish agency
    manual    -> scripts/seed_ferries_manual.py
    merge     -> scripts/merge_ferries.py
    names     -> scripts/enrich_terminal_names.py
    drivetime -> scripts/compute_drive_times.py   (slow; off by default)
    seo       -> scripts/generate_ferry_landing_pages.py

Example::

    python3 scripts/refresh_ferries.py            # everything except drivetime
    python3 scripts/refresh_ferries.py --only seo manual   # subset
    python3 scripts/refresh_ferries.py --include-drivetime
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"
LOGS.mkdir(exist_ok=True)
LOG_FILE = LOGS / "refresh_ferries.log"
STALE_REPORT = ROOT / "data" / "ferries_stale_report.json"
FERRIES_PATH = ROOT / "data" / "ferries.json"

STALE_DAYS_HARD = 180

DEFAULT_STAGES = ["osm", "gtfs", "manual", "merge", "names", "seo"]
ALL_STAGES = DEFAULT_STAGES + ["drivetime"]

SCOTTISH_GTFS_AGENCIES = [
    ("calmac",           "caledonian macbrayne"),
    ("northlink",        "northlink"),
    ("pentland",         "pentland ferries"),
    ("western-ferries",  "western ferries"),
    ("orkney-ferries",   "orkney ferries"),
    ("sic-ferries",      "shetland ferries"),
    ("argyll-bute",      "argyll & bute"),
    ("ulva-ferry",       "ulva ferry"),
    ("skye-ferry",       "skye ferry"),
    ("highland-ferries", "highland ferries"),
]


def _log(msg: str) -> None:
    ts = datetime.utcnow().isoformat(timespec="seconds")
    line = f"[{ts}] {msg}"
    print(line)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _run(*args: str) -> int:
    _log("RUN " + " ".join(args))
    rc = subprocess.call(["python3", *args], cwd=ROOT)
    _log(f"  → exit {rc}")
    return rc


def stage_osm() -> None:
    _run("scripts/fetch_ferries_osm.py")


def stage_gtfs() -> None:
    for op_id, op_name in SCOTTISH_GTFS_AGENCIES:
        _run("scripts/import_calmac_gtfs.py",
             "--gtfs-url-default",
             "--operator-id", op_id,
             "--operator-name", op_name)


def stage_manual() -> None:
    _run("scripts/seed_ferries_manual.py")


def stage_merge() -> None:
    _run("scripts/merge_ferries.py")


def stage_names() -> None:
    _run("scripts/enrich_terminal_names.py")


def stage_drivetime() -> None:
    _run("scripts/compute_drive_times.py")


def stage_seo() -> None:
    _run("scripts/generate_ferry_landing_pages.py")


STAGE_FNS = {
    "osm": stage_osm,
    "gtfs": stage_gtfs,
    "manual": stage_manual,
    "merge": stage_merge,
    "names": stage_names,
    "drivetime": stage_drivetime,
    "seo": stage_seo,
}


def emit_stale_report() -> None:
    doc = json.loads(FERRIES_PATH.read_text(encoding="utf-8"))
    today = date.today()
    stale = []
    for r in doc.get("routes", []):
        lv = r.get("lastVerified")
        if not lv:
            continue
        try:
            d = datetime.strptime(lv, "%Y-%m-%d").date()
        except ValueError:
            continue
        age = (today - d).days
        if age >= STALE_DAYS_HARD:
            stale.append({
                "id": r["id"],
                "name": r.get("name"),
                "operatorId": r.get("operatorId"),
                "lastVerified": lv,
                "ageDays": age,
            })
    STALE_REPORT.write_text(
        json.dumps({"generated": today.isoformat(), "stale": stale}, indent=2),
        encoding="utf-8",
    )
    _log(f"Stale report: {len(stale)} routes flagged in {STALE_REPORT.relative_to(ROOT)}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--only", nargs="+", choices=ALL_STAGES,
                   help="Run only this subset of stages (in order).")
    p.add_argument("--skip", nargs="+", choices=ALL_STAGES, default=[],
                   help="Skip these stages.")
    p.add_argument("--include-drivetime", action="store_true",
                   help="Run the slow OSRM drive-time stage as well.")
    args = p.parse_args()

    if args.only:
        stages = args.only
    else:
        stages = list(DEFAULT_STAGES)
        if args.include_drivetime:
            stages.append("drivetime")
    stages = [s for s in stages if s not in set(args.skip)]

    _log(f"Stages: {stages}")
    for stage in stages:
        STAGE_FNS[stage]()
    emit_stale_report()
    _log("All stages complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
