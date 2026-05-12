#!/usr/bin/env python3
"""Import CalMac (and other GTFS-publishing operators) schedules into
``data/ferries.json``.

CalMac's published schedule is bundled in the Traveline Scotland GTFS feed.
This script accepts a local ``.zip`` (the simplest case for offline runs) or
an HTTPS URL pointing to one. It then:

1. Reads ``agency.txt`` / ``routes.txt`` / ``trips.txt`` / ``stop_times.txt``
   / ``stops.txt`` / ``calendar.txt`` from the zip.
2. Filters to agencies matching ``--operator-name`` (default substring
   "calmac" or "caledonian macbrayne").
3. Joins routes → trips → stop_times → stops to reconstruct a per-route
   weekly schedule.
4. Matches each GTFS stop to an existing terminal in
   ``data/ferry_terminals.json`` by proximity (within 400 m), creating
   terminals on the fly if absent.
5. Writes/updates the corresponding route record in ``data/ferries.json``,
   preserving any OSM-sourced data in ``sources`` (timetables from GTFS win
   over OSM stub timetables).

Usage::

    python3 scripts/import_calmac_gtfs.py --gtfs-zip /path/to/feed.zip
    python3 scripts/import_calmac_gtfs.py --gtfs-url https://example.com/feed.zip
    python3 scripts/import_calmac_gtfs.py --gtfs-url-default     # uses BODS feed

Known GTFS sources (verify before relying on)
---------------------------------------------
* Bus Open Data Service (BODS) - https://data.bus-data.dft.gov.uk/
  Has been used to publish a UK-wide GTFS bundle. Filter agency_id by
  the relevant CalMac NOC code.
* Traveline Scotland - https://www.travelinescotland.com/
  Historically published the canonical Scottish ferry GTFS. The exact
  download URL has changed several times; check the Traveline Scotland
  open-data page before running with ``--gtfs-url-default``.

This script never raises if the network is unreachable: it prints a clear
error message and exits non-zero so it can be skipped in CI.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
FERRIES_PATH = DATA_DIR / "ferries.json"
TERMINALS_PATH = DATA_DIR / "ferry_terminals.json"
OPERATORS_PATH = DATA_DIR / "operators.json"

USER_AGENT = "isles-of-britain/0.1 (gtfs-import)"
DEFAULT_GTFS_URL = "https://data.bus-data.dft.gov.uk/timetable/download/gtfs-file/scotland/"
TERMINAL_PROXIMITY_KM = 0.4


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def slugify(value: str, max_len: int = 80) -> str:
    s = (value or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s[:max_len] or "unnamed"


def _atomic_write(path: Path, payload) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _read_csv_from_zip(z: zipfile.ZipFile, name: str) -> list[dict]:
    if name not in z.namelist():
        return []
    with z.open(name) as fp:
        text = io.TextIOWrapper(fp, encoding="utf-8-sig", newline="")
        return list(csv.DictReader(text))


def fetch_gtfs(args) -> bytes | None:
    if args.gtfs_zip:
        p = Path(args.gtfs_zip)
        if not p.exists():
            print(f"--gtfs-zip {p} does not exist", file=sys.stderr)
            return None
        return p.read_bytes()
    url = args.gtfs_url or (DEFAULT_GTFS_URL if args.gtfs_url_default else None)
    if not url:
        print("No GTFS source. Pass --gtfs-zip or --gtfs-url.", file=sys.stderr)
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        print(f"GTFS download failed: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# GTFS processing
# ---------------------------------------------------------------------------

DAY_KEYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
DAY_SHORT = {
    "monday": "mon", "tuesday": "tue", "wednesday": "wed", "thursday": "thu",
    "friday": "fri", "saturday": "sat", "sunday": "sun",
}


def _gtfs_time(s: str) -> str | None:
    if not s:
        return None
    m = re.match(r"^(\d{1,2}):(\d{2})", s)
    if not m:
        return None
    h, mm = int(m.group(1)), int(m.group(2))
    return f"{h % 24:02d}:{mm:02d}"


def find_calmac_routes(zip_bytes: bytes, operator_substr: str) -> list[dict]:
    z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    agencies = _read_csv_from_zip(z, "agency.txt")
    routes = _read_csv_from_zip(z, "routes.txt")
    trips = _read_csv_from_zip(z, "trips.txt")
    stop_times = _read_csv_from_zip(z, "stop_times.txt")
    stops = _read_csv_from_zip(z, "stops.txt")
    calendar = _read_csv_from_zip(z, "calendar.txt")

    op_substr = operator_substr.lower()
    matching_agency_ids = {a["agency_id"] for a in agencies if op_substr in a.get("agency_name", "").lower()}
    if not matching_agency_ids and any(op_substr in (r.get("agency_id", "") or "").lower() for r in routes):
        matching_agency_ids = {(r.get("agency_id") or "") for r in routes if op_substr in (r.get("agency_id", "") or "").lower()}
    if not matching_agency_ids:
        print(f"No agency matched substring {operator_substr!r}. Agencies found:", file=sys.stderr)
        for a in agencies[:20]:
            print(f"  {a.get('agency_id')!r}: {a.get('agency_name')!r}", file=sys.stderr)
        return []

    print(f"  matched {len(matching_agency_ids)} agency_id(s) for {operator_substr!r}", file=sys.stderr)

    routes_by_id = {r["route_id"]: r for r in routes if r.get("agency_id") in matching_agency_ids}
    if not routes_by_id:
        print("  no routes for matched agencies", file=sys.stderr)
        return []
    trips_by_route: dict[str, list[dict]] = defaultdict(list)
    trip_to_route: dict[str, str] = {}
    for t in trips:
        if t["route_id"] in routes_by_id:
            trips_by_route[t["route_id"]].append(t)
            trip_to_route[t["trip_id"]] = t["route_id"]

    # Group stop_times by trip_id (only for our trips) and order by sequence.
    st_by_trip: dict[str, list[dict]] = defaultdict(list)
    for st in stop_times:
        if st["trip_id"] in trip_to_route:
            st_by_trip[st["trip_id"]].append(st)
    for trip_id, sts in st_by_trip.items():
        sts.sort(key=lambda r: int(r.get("stop_sequence", 0) or 0))

    stops_by_id = {s["stop_id"]: s for s in stops}
    calendar_by_id = {c["service_id"]: c for c in calendar}

    print(f"  routes={len(routes_by_id)}, trips={sum(len(v) for v in trips_by_route.values())}, "
          f"stop_times rows for our trips={sum(len(v) for v in st_by_trip.values())}",
          file=sys.stderr)

    out_routes: list[dict] = []
    for route_id, route in routes_by_id.items():
        rtrips = trips_by_route[route_id]
        if not rtrips:
            continue
        # Group by (origin_stop_id, dest_stop_id) so we capture each
        # direction separately - GTFS may have two directions per route.
        by_od: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for t in rtrips:
            sts = st_by_trip.get(t["trip_id"], [])
            if len(sts) < 2:
                continue
            od = (sts[0]["stop_id"], sts[-1]["stop_id"])
            by_od[od].append(t)

        for (orig, dest), trip_list in by_od.items():
            if orig not in stops_by_id or dest not in stops_by_id:
                continue
            schedule: dict[str, list[str]] = {d: [] for d in DAY_KEYS}
            valid_from: str | None = None
            valid_to: str | None = None
            for t in trip_list:
                sts = st_by_trip.get(t["trip_id"], [])
                if not sts:
                    continue
                dep_time = _gtfs_time(sts[0].get("departure_time") or sts[0].get("arrival_time") or "")
                if not dep_time:
                    continue
                svc = calendar_by_id.get(t["service_id"])
                if not svc:
                    continue
                if not valid_from or (svc.get("start_date") or "") < valid_from:
                    valid_from = svc.get("start_date")
                if not valid_to or (svc.get("end_date") or "") > valid_to:
                    valid_to = svc.get("end_date")
                for day in DAY_KEYS:
                    if svc.get(day) == "1":
                        if dep_time not in schedule[day]:
                            schedule[day].append(dep_time)
            for day in DAY_KEYS:
                schedule[day].sort()
            weekly = [{"day": DAY_SHORT[d], "outbound": schedule[d], "return": []} for d in DAY_KEYS if schedule[d]]
            if not weekly:
                continue

            # First stop times across all trips give duration estimate.
            durations: list[int] = []
            for t in trip_list:
                sts = st_by_trip.get(t["trip_id"], [])
                if len(sts) < 2:
                    continue
                a = _gtfs_time(sts[0].get("departure_time") or sts[0].get("arrival_time") or "")
                b = _gtfs_time(sts[-1].get("arrival_time") or sts[-1].get("departure_time") or "")
                if not a or not b:
                    continue
                ah, am = map(int, a.split(":"))
                bh, bm = map(int, b.split(":"))
                durations.append(((bh * 60 + bm) - (ah * 60 + am)) % (24 * 60))
            dur = int(round(sum(durations) / len(durations))) if durations else None

            out_routes.append({
                "_gtfs": True,
                "route_id": route_id,
                "operator_route_code": route.get("route_short_name") or route.get("route_long_name"),
                "name": route.get("route_long_name") or route.get("route_short_name") or route_id,
                "from_stop": stops_by_id[orig],
                "to_stop": stops_by_id[dest],
                "weekly": weekly,
                "valid_from": _format_gtfs_date(valid_from),
                "valid_to": _format_gtfs_date(valid_to),
                "duration_minutes": dur,
            })

    return out_routes


def _format_gtfs_date(yyyymmdd: str | None) -> str | None:
    if not yyyymmdd or len(yyyymmdd) != 8:
        return None
    try:
        return datetime.strptime(yyyymmdd, "%Y%m%d").date().isoformat()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Terminal matching
# ---------------------------------------------------------------------------

def _stop_to_terminal(stop: dict, terminals: list[dict]) -> dict:
    lat = float(stop["stop_lat"])
    lon = float(stop["stop_lon"])
    name = (stop.get("stop_name") or "").strip()
    for t in terminals:
        try:
            d = haversine_km(lat, lon, float(t["lat"]), float(t["lon"]))
        except (KeyError, TypeError, ValueError):
            continue
        if d <= TERMINAL_PROXIMITY_KM:
            return t
    new_terminal = {
        "id": f"term-gtfs-{slugify(name)}-{stop['stop_id']}",
        "name": name or f"GTFS {stop['stop_id']}",
        "names": {"en": name or None},
        "lat": lat,
        "lon": lon,
        "country": None,
        "islandId": None,
        "islandDistanceKm": None,
        "osmNodeId": None,
        "wikidata": None,
        "operatorsServing": [],
        "facilities": {"carPark": None, "evCharger": None, "stepFree": None, "ticketOffice": None, "cafe": None},
        "driveTimeMinutes": {"London": None, "Glasgow": None, "Edinburgh": None, "Belfast": None, "Dublin": None},
        "lastVerified": str(date.today()),
        "source": "gtfs",
    }
    terminals.append(new_terminal)
    return new_terminal


# ---------------------------------------------------------------------------
# Merge into ferries.json
# ---------------------------------------------------------------------------

def merge(operator_id: str, gtfs_routes: list[dict]) -> tuple[int, int]:
    ferries = json.loads(FERRIES_PATH.read_text(encoding="utf-8"))
    terminals_doc = json.loads(TERMINALS_PATH.read_text(encoding="utf-8"))
    terminals = terminals_doc.setdefault("terminals", [])
    routes = ferries.setdefault("routes", [])

    by_id = {r["id"]: r for r in routes}
    added = updated = 0

    for g in gtfs_routes:
        t_from = _stop_to_terminal(g["from_stop"], terminals)
        t_to = _stop_to_terminal(g["to_stop"], terminals)
        if operator_id not in t_from["operatorsServing"]:
            t_from["operatorsServing"].append(operator_id)
        if operator_id not in t_to["operatorsServing"]:
            t_to["operatorsServing"].append(operator_id)

        slug = slugify(f"{operator_id}-{t_from['name']}-{t_to['name']}")
        rid = f"gtfs-{slug}"

        rec = {
            "id": rid,
            "operatorId": operator_id,
            "operatorRouteCode": g["operator_route_code"],
            "name": g["name"],
            "terminals": {
                "from": {"terminalId": t_from["id"], "islandId": t_from.get("islandId")},
                "to":   {"terminalId": t_to["id"],   "islandId": t_to.get("islandId")},
            },
            "type": "car-and-foot",
            "seasonality": "year-round",
            "frequencyBand": "several-daily",
            "durationMinutes": g["duration_minutes"],
            "vessel": [],
            "vesselWikidata": [],
            "bookingUrl": None,
            "timetable": {
                "source": f"gtfs:{operator_id}",
                "validFrom": g["valid_from"],
                "validTo": g["valid_to"],
                "weekly": g["weekly"],
                "notes": "Auto-imported from GTFS feed; reverify each season.",
            },
            "accessibility": {"wheelchair": None, "bicycle": None, "pets": None, "ev": None},
            "fareFromGBP": None,
            "sources": [{"type": "gtfs", "id": g["route_id"], "url": None}],
            "lastVerified": str(date.today()),
        }
        if rid in by_id:
            by_id[rid].update(rec)
            updated += 1
        else:
            by_id[rid] = rec
            added += 1

    ferries["routes"] = list(by_id.values())
    _atomic_write(FERRIES_PATH, ferries)
    _atomic_write(TERMINALS_PATH, terminals_doc)
    return added, updated


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--gtfs-zip", help="Path to a local GTFS .zip file")
    p.add_argument("--gtfs-url", help="HTTPS URL for a GTFS .zip")
    p.add_argument("--gtfs-url-default", action="store_true",
                   help="Use built-in DEFAULT_GTFS_URL; YMMV depending on upstream")
    p.add_argument("--operator-id", default="calmac", help="Operator ID to write into routes")
    p.add_argument("--operator-name", default="caledonian macbrayne",
                   help="Substring match against agency_name in agency.txt")
    args = p.parse_args()

    print("=== import_calmac_gtfs.py ===", file=sys.stderr)
    data = fetch_gtfs(args)
    if not data:
        print("Aborting; no GTFS data available.", file=sys.stderr)
        return 2

    routes = find_calmac_routes(data, args.operator_name)
    print(f"  produced {len(routes)} routes from GTFS", file=sys.stderr)
    if not routes:
        return 3

    added, updated = merge(args.operator_id, routes)
    print(f"  ferries.json: +{added} new, {updated} updated", file=sys.stderr)
    print("done.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
