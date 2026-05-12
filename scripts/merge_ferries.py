#!/usr/bin/env python3
"""Merge ``data/ferries_manual.json`` into ``data/ferries.json`` and
``data/ferry_terminals.json``.

Manual entries are layered on top of (and have priority over) any record
with the same ``id``. Re-running is idempotent.

Also assigns ``terminal.islandId`` for any manual terminal that didn't get
one in ``seed_ferries_manual.py`` by finding the nearest island in
``data/islands.json`` within 1.5 km.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FERRIES = ROOT / "data" / "ferries.json"
MANUAL = ROOT / "data" / "ferries_manual.json"
TERMINALS = ROOT / "data" / "ferry_terminals.json"
ISLANDS = ROOT / "data" / "islands.json"

ISLAND_PROXIMITY_KM = 1.5


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _atomic(path: Path, payload):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    manual = json.loads(MANUAL.read_text(encoding="utf-8"))
    ferries = json.loads(FERRIES.read_text(encoding="utf-8"))
    terminals_doc = json.loads(TERMINALS.read_text(encoding="utf-8"))
    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))

    isl_idx = []
    for isl in islands:
        try:
            isl_idx.append({"id": isl["id"], "lat": float(isl["lat"]), "lng": float(isl["lng"])})
        except (KeyError, TypeError, ValueError):
            continue

    def nearest_island_id(lat, lon):
        best = None
        bestd = ISLAND_PROXIMITY_KM
        for isl in isl_idx:
            d = haversine_km(lat, lon, isl["lat"], isl["lng"])
            if d < bestd:
                best = isl["id"]
                bestd = d
        return best, (None if best is None else bestd)

    # Merge terminals
    by_id = {t["id"]: t for t in terminals_doc.get("terminals", [])}
    t_added = t_updated = 0
    for t in manual.get("terminals", []):
        # Auto-link island if missing.
        if not t.get("islandId"):
            try:
                isl_id, dist = nearest_island_id(float(t["lat"]), float(t["lon"]))
                if isl_id:
                    t["islandId"] = isl_id
                    t["islandDistanceKm"] = round(dist, 3)
            except (KeyError, TypeError, ValueError):
                pass
        if t["id"] in by_id:
            by_id[t["id"]].update(t)
            t_updated += 1
        else:
            by_id[t["id"]] = t
            t_added += 1
    terminals_doc["terminals"] = list(by_id.values())

    # Cross-reference terminal.islandId into manual routes if missing.
    term_lookup = {t["id"]: t for t in terminals_doc["terminals"]}
    for r in manual.get("routes", []):
        for side in ("from", "to"):
            ep = r.get("terminals", {}).get(side, {})
            tid = ep.get("terminalId")
            t = term_lookup.get(tid)
            if t and not ep.get("islandId"):
                ep["islandId"] = t.get("islandId")

    # Merge routes
    by_rid = {r["id"]: r for r in ferries.get("routes", [])}
    r_added = r_updated = 0
    for r in manual.get("routes", []):
        if r["id"] in by_rid:
            by_rid[r["id"]].update(r)
            r_updated += 1
        else:
            by_rid[r["id"]] = r
            r_added += 1
    ferries["routes"] = list(by_rid.values())

    _atomic(TERMINALS, terminals_doc)
    _atomic(FERRIES, ferries)

    matched = sum(1 for t in terminals_doc["terminals"] if t.get("islandId"))
    print(f"terminals: +{t_added} new, {t_updated} updated, total {len(terminals_doc['terminals'])} "
          f"({matched} with islandId, {matched/max(1,len(terminals_doc['terminals'])):.0%})")
    print(f"routes:    +{r_added} new, {r_updated} updated, total {len(ferries['routes'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
