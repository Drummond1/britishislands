#!/usr/bin/env python3
"""Harvest ferry routes from OpenStreetMap via the Overpass API.

What it does
------------
1. Queries Overpass for ``relation["route"="ferry"]`` inside the UK + IE +
   Channel-Islands bounding box (same box used by ``fetch_islands.py``).
2. Pulls every member (route ways, terminal nodes, ferry_terminal=* nodes).
3. Builds a normalised list of ferry-route records into
   ``data/ferries.json#routes`` and a list of terminal records into
   ``data/ferry_terminals.json#terminals``.
4. For each terminal it tries to match the nearest island in
   ``data/islands.json`` within ``ISLAND_PROXIMITY_KM`` (default 1.5 km),
   setting ``terminal.islandId`` when the match is confident.
5. Best-effort maps the OSM ``operator=*`` tag to one of the operator IDs in
   ``data/operators.json`` (case-insensitive substring match on names).
6. Writes atomically to ``data/ferries.json`` and ``data/ferry_terminals.json``
   (preserves the schemaVersion/schema/description header blocks).

Output records preserve every existing route in ``data/ferries.json`` that
wasn't sourced from OSM, so subsequent runs are idempotent.

Run
---
    python3 scripts/fetch_ferries_osm.py
"""

from __future__ import annotations

import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
ISLANDS_PATH = DATA_DIR / "islands.json"
OPERATORS_PATH = DATA_DIR / "operators.json"
FERRIES_PATH = DATA_DIR / "ferries.json"
TERMINALS_PATH = DATA_DIR / "ferry_terminals.json"
RAW_PATH = DATA_DIR / "osm_ferries_raw.json"

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
]

# Same envelope as fetch_islands.py.
UK_BBOX = (49.0, -10.5, 61.5, 2.5)

ISLAND_PROXIMITY_KM = 1.5  # max distance terminal→nearest island for a confident match
USER_AGENT = "isles-of-britain/0.1 (ferry-harvest; static site)"


def overpass_query(bbox: tuple[float, float, float, float]) -> str:
    s, w, n, e = bbox
    bbox_str = f"{s},{w},{n},{e}"
    # Pull route=ferry relations + every ferry_terminal=yes node so we can
    # cross-reference terminals that aren't members of any relation.
    return f"""
[out:json][timeout:300];
(
  relation["route"="ferry"]({bbox_str});
);
out body;
>;
out skel qt;
node["amenity"="ferry_terminal"]({bbox_str});
out body;
""".strip()


def post_overpass(query: str) -> dict:
    last_error: Exception | None = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            print(f"→ querying {endpoint}", file=sys.stderr)
            data = urllib.parse.urlencode({"data": query}).encode("utf-8")
            req = urllib.request.Request(
                endpoint,
                data=data,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=300) as resp:
                payload = resp.read()
            return json.loads(payload)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            print(f"  endpoint failed: {exc}", file=sys.stderr)
            last_error = exc
            time.sleep(3)
    raise RuntimeError(f"All Overpass endpoints failed: {last_error}")


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def slugify(value: str, max_len: int = 80) -> str:
    s = value.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s[:max_len] or "unnamed"


def _load_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_write(path: Path, payload: dict | list) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Operator matching
# ---------------------------------------------------------------------------

EXTRA_OPERATOR_ALIASES: dict[str, list[str]] = {
    # Folds in OSM operator-tag variants we observed in the raw payload.
    "thames-clippers": ["mbna thames clippers", "kpmg thames clippers", "thames clippers"],
    "calmac": ["caledonian macbrayne", "calmac ferries"],
    "iom-steam-packet": ["isle of man steam packet"],
    "po-ferries": ["p&o ferries", "p & o ferries", "p&o ferries/dfds", "p & o frieght"],
    "scilly-travel": ["isles of scilly steamship"],
    "wic-sound-of-harris": ["comhairle nan eilean siar"],
    "dfi-ni": ["dept for infrastructure ni", "department for infrastructure"],
}


def build_operator_matcher(operators_doc: dict) -> list[tuple[str, list[str]]]:
    """Return [(operator_id, [substrings])] sorted by specificity descending."""
    out: list[tuple[str, list[str]]] = []
    for op in operators_doc.get("operators", []):
        names: list[str] = []
        for key in ("name", "shortName"):
            v = op.get(key, "").strip().lower()
            if v:
                names.append(v)
        if op.get("id"):
            names.append(op["id"].lower())
        names.extend(EXTRA_OPERATOR_ALIASES.get(op["id"], []))
        out.append((op["id"], list(dict.fromkeys(names))))
    out.sort(key=lambda kv: -max((len(s) for s in kv[1]), default=0))
    return out


def match_operator(tag_value: str, matcher: list[tuple[str, list[str]]]) -> str | None:
    if not tag_value:
        return None
    v = tag_value.lower()
    for op_id, names in matcher:
        for n in names:
            if n and n in v:
                return op_id
    return None


# ---------------------------------------------------------------------------
# Island matching
# ---------------------------------------------------------------------------

def build_island_index(islands: list[dict]) -> list[dict]:
    """Return a list trimmed to the fields we need for nearest-neighbour search."""
    out: list[dict] = []
    for isl in islands:
        try:
            lat = float(isl["lat"])
            lng = float(isl["lng"])
        except (KeyError, TypeError, ValueError):
            continue
        out.append({
            "id": isl["id"],
            "name": isl.get("name", ""),
            "lat": lat,
            "lng": lng,
            "areaKm2": isl.get("areaKm2"),
        })
    return out


def nearest_island(lat: float, lon: float, idx: list[dict], max_km: float) -> tuple[str | None, float | None]:
    best_id: str | None = None
    best_km: float | None = None
    for isl in idx:
        d = haversine_km(lat, lon, isl["lat"], isl["lng"])
        if d > max_km:
            continue
        if best_km is None or d < best_km:
            best_id = isl["id"]
            best_km = d
    return best_id, best_km


# ---------------------------------------------------------------------------
# Type / seasonality inference
# ---------------------------------------------------------------------------

def infer_type(tags: dict) -> str:
    motor = tags.get("motor_vehicle") or tags.get("motorcar") or tags.get("vehicle") or ""
    foot = tags.get("foot", "")
    if motor.lower() in {"yes", "designated", "permissive"}:
        return "car-and-foot"
    if motor.lower() in {"no"}:
        return "foot-only"
    # Heuristics: if vessel tag mentions hovercraft / passenger, treat as foot
    name = (tags.get("name") or "").lower()
    if "hovercraft" in name or "passenger" in name:
        return "foot-only"
    return "car-and-foot" if not foot else "foot-only" if foot.lower() == "designated" else "car-and-foot"


def infer_seasonality(tags: dict) -> str:
    opening = (tags.get("opening_hours") or "").lower()
    if any(season in opening for season in ("apr-oct", "mar-oct", "may-sep", "summer")):
        return "summer-only"
    if "24/7" in opening or "mo-su" in opening:
        return "year-round"
    return "year-round"  # default; per-operator scrapers will refine


# ---------------------------------------------------------------------------
# Main parse
# ---------------------------------------------------------------------------

def parse_osm(raw: dict, islands_idx: list[dict], op_matcher: list[tuple[str, list[str]]]):
    elements = raw.get("elements", [])
    nodes: dict[int, dict] = {}
    relations: list[dict] = []
    standalone_terminals: list[dict] = []

    for el in elements:
        t = el.get("type")
        if t == "node":
            nodes[el["id"]] = el
            tags = el.get("tags", {}) or {}
            if tags.get("amenity") == "ferry_terminal":
                standalone_terminals.append(el)
        elif t == "relation":
            tags = el.get("tags", {}) or {}
            if tags.get("route") == "ferry":
                relations.append(el)

    print(f"  parsed {len(relations)} ferry relations, {len(nodes)} nodes total, "
          f"{len(standalone_terminals)} standalone ferry_terminal nodes",
          file=sys.stderr)

    terminals_by_node: dict[int, dict] = {}

    def get_or_make_terminal(node: dict) -> dict | None:
        if not node:
            return None
        node_id = node["id"]
        if node_id in terminals_by_node:
            return terminals_by_node[node_id]
        tags = node.get("tags", {}) or {}
        name = tags.get("name") or tags.get("name:en") or ""
        lat = node.get("lat")
        lon = node.get("lon")
        if lat is None or lon is None:
            return None
        island_id, dist = nearest_island(lat, lon, islands_idx, ISLAND_PROXIMITY_KM)
        names = {"en": name or None}
        for k, v in tags.items():
            m = re.match(r"^name:([a-z]{2,3})$", k)
            if m and v:
                names[m.group(1)] = v
        slug_base = name or f"node-{node_id}"
        terminal = {
            "id": f"term-{slugify(slug_base)}-{node_id}" if not name else f"term-{slugify(slug_base)}",
            "name": name or f"OSM node {node_id}",
            "names": {k: v for k, v in names.items() if v},
            "lat": lat,
            "lon": lon,
            "country": None,
            "islandId": island_id,
            "islandDistanceKm": round(dist, 3) if dist is not None else None,
            "osmNodeId": node_id,
            "wikidata": tags.get("wikidata") or None,
            "operatorsServing": [],
            "facilities": {
                "carPark": None,
                "evCharger": None,
                "stepFree": None,
                "ticketOffice": None,
                "cafe": None,
            },
            "driveTimeMinutes": {"London": None, "Glasgow": None, "Edinburgh": None, "Belfast": None, "Dublin": None},
            "tags": tags,
            "lastVerified": str(date.today()),
        }
        terminals_by_node[node_id] = terminal
        return terminal

    # Seed terminals from standalone amenity=ferry_terminal nodes so we don't
    # lose terminals that don't appear in any route relation.
    for n in standalone_terminals:
        get_or_make_terminal(n)

    routes: list[dict] = []

    # Index ways so we can fall back to first/last way-endpoint when a
    # relation lacks explicit terminal-role members.
    ways: dict[int, dict] = {}
    for el in elements:
        if el.get("type") == "way":
            ways[el["id"]] = el

    for rel in relations:
        rid = rel["id"]
        tags = rel.get("tags", {}) or {}
        members = rel.get("members", [])

        terminal_nodes: list[dict] = []
        for m in members:
            if m.get("type") == "node":
                role = (m.get("role") or "").lower()
                n = nodes.get(m["ref"])
                if not n:
                    continue
                ntags = n.get("tags", {}) or {}
                if role in {"stop", "stop_entry_only", "stop_exit_only", "from", "to"} or ntags.get("amenity") == "ferry_terminal":
                    terminal_nodes.append(n)

        if len(terminal_nodes) < 2:
            # Fallback: use the first and last node of the first/last way members.
            way_members = [m for m in members if m.get("type") == "way" and m["ref"] in ways]
            if way_members:
                first_way = ways[way_members[0]["ref"]]
                last_way = ways[way_members[-1]["ref"]]
                first_nodes = first_way.get("nodes", [])
                last_nodes = last_way.get("nodes", [])
                cand_from = nodes.get(first_nodes[0]) if first_nodes else None
                cand_to = nodes.get(last_nodes[-1]) if last_nodes else None
                if cand_from and cand_to and cand_from["id"] != cand_to["id"]:
                    terminal_nodes = [cand_from, cand_to]

        if len(terminal_nodes) < 2:
            continue
        n_from = terminal_nodes[0]
        n_to = terminal_nodes[-1]

        t_from = get_or_make_terminal(n_from)
        t_to = get_or_make_terminal(n_to)
        if not t_from or not t_to:
            continue

        op_tag = tags.get("operator") or tags.get("operator:en") or ""
        op_id = match_operator(op_tag, op_matcher)
        if op_id:
            for term in (t_from, t_to):
                if op_id not in term["operatorsServing"]:
                    term["operatorsServing"].append(op_id)

        # Distance estimate via terminal coordinates (great-circle).
        duration = None
        try:
            d_km = haversine_km(t_from["lat"], t_from["lon"], t_to["lat"], t_to["lon"])
            if d_km > 0:
                # Assume ~14 knots ≈ 26 km/h for typical UK ferries; produces
                # a *very* rough ETA. Per-operator scrapers and GTFS override.
                duration = max(1, int(round(d_km / 26 * 60)))
        except Exception:
            pass

        name = tags.get("name") or f"{t_from['name']} – {t_to['name']}"
        slug = slugify(f"{op_id or 'osm'}-{t_from['name']}-{t_to['name']}")
        route = {
            "id": f"osm-{slug}-{rid}",
            "operatorId": op_id,
            "operatorRouteCode": tags.get("ref") or None,
            "name": name,
            "terminals": {
                "from": {"terminalId": t_from["id"], "islandId": t_from.get("islandId")},
                "to":   {"terminalId": t_to["id"],   "islandId": t_to.get("islandId")},
            },
            "type": infer_type(tags),
            "seasonality": infer_seasonality(tags),
            "frequencyBand": None,
            "durationMinutes": duration,
            "vessel": [],
            "vesselWikidata": [],
            "bookingUrl": tags.get("website") or tags.get("url") or None,
            "timetable": {"source": "osm", "validFrom": None, "validTo": None, "weekly": [], "notes": ""},
            "accessibility": {
                "wheelchair": _bool_tag(tags.get("wheelchair")),
                "bicycle": _bool_tag(tags.get("bicycle")),
                "pets": None,
                "ev": None,
            },
            "fareFromGBP": None,
            "sources": [
                {"type": "osm-relation", "url": f"https://www.openstreetmap.org/relation/{rid}", "id": rid}
            ],
            "lastVerified": str(date.today()),
            "_osmTags": tags,
        }
        routes.append(route)

    # Strip the working _osmTags / tags fields before returning - we kept them
    # on terminals/routes only as breadcrumbs during merge.
    out_terminals = sorted(terminals_by_node.values(), key=lambda t: (t.get("country") or "", t["name"], t["osmNodeId"]))
    for t in out_terminals:
        t.pop("tags", None)
    for r in routes:
        r.pop("_osmTags", None)

    return routes, out_terminals


def _bool_tag(v: str | None):
    if v is None:
        return None
    v = v.lower().strip()
    if v in {"yes", "designated", "permissive"}:
        return True
    if v in {"no"}:
        return False
    return None


def merge_into(file_path: Path, key: str, new_records: list[dict], dedupe_field: str = "id") -> tuple[int, int]:
    """Merge new_records into file_path[key] while keeping non-OSM entries. Returns (added, updated)."""
    doc = _load_json(file_path) or {}
    if not isinstance(doc, dict):
        raise SystemExit(f"{file_path} is not an object")
    existing = doc.get(key, [])
    by_id = {r.get(dedupe_field): r for r in existing if isinstance(r, dict) and r.get(dedupe_field)}

    added = updated = 0
    for rec in new_records:
        if not rec.get(dedupe_field):
            continue
        if rec[dedupe_field] in by_id:
            by_id[rec[dedupe_field]] = {**by_id[rec[dedupe_field]], **rec}
            updated += 1
        else:
            by_id[rec[dedupe_field]] = rec
            added += 1
    doc[key] = list(by_id.values())
    _atomic_write(file_path, doc)
    return added, updated


def main() -> int:
    print("=== fetch_ferries_osm.py ===", file=sys.stderr)
    islands_doc = _load_json(ISLANDS_PATH)
    if not isinstance(islands_doc, list):
        raise SystemExit("data/islands.json must be a list")
    operators_doc = _load_json(OPERATORS_PATH) or {}
    op_matcher = build_operator_matcher(operators_doc)
    islands_idx = build_island_index(islands_doc)
    print(f"  loaded {len(islands_idx)} islands; {len(op_matcher)} operator stubs", file=sys.stderr)

    query = overpass_query(UK_BBOX)
    raw = post_overpass(query)
    RAW_PATH.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    print(f"  cached raw → {RAW_PATH.relative_to(ROOT)}", file=sys.stderr)

    routes, terminals = parse_osm(raw, islands_idx, op_matcher)
    print(f"  produced {len(routes)} routes, {len(terminals)} terminals", file=sys.stderr)

    added_r, updated_r = merge_into(FERRIES_PATH, "routes", routes, "id")
    added_t, updated_t = merge_into(TERMINALS_PATH, "terminals", terminals, "id")
    print(f"  ferries.json: +{added_r} new, {updated_r} updated", file=sys.stderr)
    print(f"  terminals.json: +{added_t} new, {updated_t} updated", file=sys.stderr)

    # Coverage report.
    matched = sum(1 for t in terminals if t.get("islandId"))
    print(f"  terminal→island matches: {matched}/{len(terminals)} ({matched/max(1,len(terminals)):.0%})", file=sys.stderr)
    op_counts: dict[str, int] = {}
    for r in routes:
        op_counts[r.get("operatorId") or "<unknown>"] = op_counts.get(r.get("operatorId") or "<unknown>", 0) + 1
    print("  operator coverage:", file=sys.stderr)
    for op_id, n in sorted(op_counts.items(), key=lambda kv: -kv[1]):
        print(f"    {op_id:30s} {n:3d}", file=sys.stderr)

    print("done.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
