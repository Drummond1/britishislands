#!/usr/bin/env python3
"""Populate ``terminal.driveTimeMinutes`` for every mainland ferry
terminal in ``data/ferry_terminals.json``.

Uses the public OSRM demo server (https://router.project-osrm.org/) to
compute driving time from each of five major hub cities to each terminal:

  London, Glasgow, Edinburgh, Belfast, Dublin

We only query mainland terminals (i.e. ``terminal.islandId`` is null or
points to a large island that drivers can reach by road — Great Britain,
Ireland, Anglesey, the Isle of Wight, etc.). Small offshore islands get
``null`` for every origin.

Rate-limit-friendly:
  • Hard 0.4 s sleep between requests.
  • Exponential backoff on 429.
  • Atomic checkpoint write every 50 terminals so a kill doesn't lose
    work.

Run::

    python3 scripts/compute_drive_times.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TERMINALS_PATH = ROOT / "data" / "ferry_terminals.json"

OSRM_BASE = "https://router.project-osrm.org/route/v1/driving"
USER_AGENT = "isles-of-britain/0.1 (drive-time-batch)"

ORIGINS = {
    "London":    (51.5074, -0.1278),
    "Glasgow":   (55.8642, -4.2518),
    "Edinburgh": (55.9533, -3.1883),
    "Belfast":   (54.5973, -5.9301),
    "Dublin":    (53.3498, -6.2603),
}

# Terminals whose islandId points to one of these slugs are still road-
# accessible from the mainland (large islands with bridges or themselves
# the mainland of their nation).
ROAD_ACCESSIBLE_ISLAND_PREFIXES = (
    "osm-",  # too broad to whitelist; require explicit allow-list below
)
ROAD_ACCESSIBLE_NAMES = {
    "great britain", "ireland", "anglesey", "isle of wight", "isle of sheppey",
    "skye", "isle of skye", "seil", "easdale", "kerrera",
    "ynys môn",
    # Holy Island, Lindisfarne accessible via tidal causeway - treat as road
    "lindisfarne", "holy island",
}

REQUEST_DELAY = 0.4
RETRY_BACKOFF = (2, 5, 12, 30, 60)


def _osrm(lat1, lon1, lat2, lon2):
    # Python's bundled SSL stack chokes on OSRM's TLS handshake on some
    # systems, so we shell out to curl - same retry/backoff semantics.
    url = f"{OSRM_BASE}/{lon1},{lat1};{lon2},{lat2}?overview=false&alternatives=false&steps=false"
    for wait in RETRY_BACKOFF:
        try:
            res = subprocess.run(
                [
                    "curl", "-sS", "--max-time", "30",
                    "-H", f"User-Agent: {USER_AGENT}",
                    "-H", "Accept: application/json",
                    "-w", "\nHTTP_CODE=%{http_code}\n",
                    url,
                ],
                capture_output=True, text=True, timeout=45,
            )
        except subprocess.TimeoutExpired:
            time.sleep(wait)
            continue
        body = res.stdout or ""
        # Extract HTTP_CODE line we appended via -w.
        http_code = None
        if "HTTP_CODE=" in body:
            try:
                http_code = int(body.split("HTTP_CODE=")[-1].strip())
                body = body.split("\nHTTP_CODE=")[0]
            except ValueError:
                pass
        if http_code is None or http_code >= 500 or http_code == 429:
            time.sleep(wait)
            continue
        if http_code >= 400:
            return None
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            time.sleep(wait)
            continue
        if data.get("code") != "Ok":
            return None
        routes = data.get("routes") or []
        if not routes:
            return None
        return int(round(routes[0]["duration"] / 60))
    return None


def is_road_accessible(t: dict) -> bool:
    if not t.get("islandId"):
        return True
    isl = (t.get("islandId") or "").lower()
    name = (t.get("name") or "").lower()
    if any(n in name for n in ROAD_ACCESSIBLE_NAMES):
        return True
    if isl.endswith("great-britain") or isl.endswith("ireland"):
        return True
    return False


def _atomic(path: Path, payload):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    doc = json.loads(TERMINALS_PATH.read_text(encoding="utf-8"))
    terminals = doc.get("terminals", [])
    pending = [
        t for t in terminals
        if is_road_accessible(t)
        and isinstance(t.get("lat"), (int, float))
        and isinstance(t.get("lon"), (int, float))
        and any(t.get("driveTimeMinutes", {}).get(city) is None for city in ORIGINS)
    ]
    print(f"=== compute_drive_times.py ===", file=sys.stderr)
    print(f"{len(pending)} terminals × {len(ORIGINS)} origins = "
          f"{len(pending) * len(ORIGINS)} requests; "
          f"ETA ~{len(pending) * len(ORIGINS) * REQUEST_DELAY / 60:.0f} min",
          file=sys.stderr)

    done = 0
    for t in pending:
        d = t.setdefault("driveTimeMinutes",
                         {city: None for city in ORIGINS})
        lat = float(t["lat"])
        lon = float(t["lon"])
        any_change = False
        for city, (olat, olon) in ORIGINS.items():
            if d.get(city) is not None:
                continue
            mins = _osrm(olat, olon, lat, lon)
            d[city] = mins
            any_change = True
            time.sleep(REQUEST_DELAY)
        if any_change:
            done += 1
        if done % 50 == 0 and done:
            _atomic(TERMINALS_PATH, doc)
            print(f"  checkpoint at {done} terminals", file=sys.stderr)
    _atomic(TERMINALS_PATH, doc)
    print(f"done. Wrote drive-times for {done} terminals.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
