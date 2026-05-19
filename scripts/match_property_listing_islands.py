#!/usr/bin/env python3
"""Match property-research island names to data/islands.json ids."""

from __future__ import annotations

import argparse
import json
import math
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ISLANDS = ROOT / "data" / "islands.json"

ALIASES: dict[tuple[str, str], str] = {
    ("lambay", "Ireland"): "osm-way-329053691",
    ("brownsea", "England"): "brownsea",
    ("tanera", "Scotland"): "osm-relation-1240445",
    ("tanera mor", "Scotland"): "osm-relation-1240445",
    ("tanera more", "Scotland"): "osm-relation-1240445",
    ("st marys scilly", "England"): "scilly-st-marys",
    ("st mary s scilly", "England"): "scilly-st-marys",
    ("st agnes scilly", "England"): "scilly-st-agnes",
    ("eel pie", "England"): "eel-pie-island",
    ("taggs island", "England"): "osm-way-49901778",
    ("tagg s island", "England"): "osm-way-49901778",
    ("taggs island hampton", "England"): "osm-way-49901778",
    ("taggs", "England"): "osm-way-49901778",
    ("inishbarna", "Ireland"): "osm-way-4562119",
    ("inis barna", "Ireland"): "osm-way-4562119",
    ("horse island cork", "Ireland"): "osm-way-4554537",
    ("white island lough erne", "Northern Ireland"): "osm-relation-3998487",
    ("devenish", "Northern Ireland"): "osm-relation-3998376",
    ("inishturk upper lough erne", "Northern Ireland"): "osm-relation-3516509",
    ("eilean mor loch sunart", "Scotland"): "osm-way-750275320",
    ("eilean mòr loch sunart", "Scotland"): "osm-way-750275320",
    ("mullagrach island", "Scotland"): "osm-way-3619206",
    ("middle calf island", "Ireland"): "osm-way-4554655",
    ("inishturk island upper lough erne", "Northern Ireland"): "osm-relation-3516509",
    ("the island thames ditton", "England"): "osm-way-48076585",
    ("pharaohs island", "England"): "osm-way-148442098",
    ("pharaoh s island", "England"): "osm-way-148442098",
    ("thorne island", "Wales"): "osm-way-4001735",
    ("thorne island off angle", "Wales"): "osm-way-4001735",
    ("high island claddaghduff", "Ireland"): "osm-way-4562311",
    ("high island", "Ireland"): "osm-way-4562311",
    ("heir island south", "Ireland"): "osm-way-190629034",
    ("heir island", "Ireland"): "osm-way-190629034",
    ("eilean righ", "Scotland"): "osm-way-200745352",
    ("inishmicatreer", "Ireland"): "osm-relation-3395357",
    ("whiddy island", "Ireland"): "osm-relation-5725196",
    ("turbot island", "Ireland"): "osm-relation-6925696",
    ("st agnes", "England"): "osm-relation-3198786",
    ("st agnes scilly", "England"): "osm-relation-3198786",
    ("whiddy island bantry", "Ireland"): "osm-relation-5725196",
    ("heir island south", "Ireland"): "osm-way-190629034",
    ("turbot island clifden", "Ireland"): "osm-relation-6925696",
    ("inish turbot", "Ireland"): "osm-relation-6925696",
    ("inishmacatreer", "Ireland"): "osm-relation-3395357",
    ("arranmore island", "Ireland"): "osm-relation-8156739",
    ("arranmore", "Ireland"): "osm-relation-8156739",
    ("horse island loop head", "Ireland"): "osm-way-4554537",
    ("dunmore bay horse island", "Ireland"): "osm-way-4554537",
    ("dunmore bay horse island loop head", "Ireland"): "osm-way-4554537",
    ("boa island", "Northern Ireland"): "osm-relation-3512150",
    ("inishmore", "Ireland"): "osm-relation-8158207",
    ("inish more", "Ireland"): "osm-relation-8158207",
    ("valentia island", "Ireland"): "osm-relation-6045364",
    ("arranmore island", "Ireland"): "osm-relation-8156739",
}

HINT_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"sunart|strontian|ardnamurchan", re.I), "osm-way-750275320"),
    (re.compile(r"boa\s*island|waters\s*edge.*boa", re.I), "osm-relation-3512150"),
    (re.compile(r"upper lough erne.*inishturk|inishturk.*upper lough", re.I), "osm-relation-3516509"),
    (re.compile(r"county mayo|clew bay", re.I), "osm-relation-5763894"),
    (re.compile(r"isles of scilly|hugh town", re.I), "scilly-st-marys"),
    (re.compile(r"st agnes.*scilly", re.I), "scilly-st-agnes"),
    (re.compile(r"roaringwater|schull|west cork", re.I), "osm-way-4554537"),
    (re.compile(r"claddaghduff|connemara", re.I), "osm-way-4562311"),
    (re.compile(r"pembrokeshire|angle.*fort", re.I), "osm-way-300065283"),
    (re.compile(r"bantry.*whiddy", re.I), "osm-relation-5725196"),
    (re.compile(r"lough der g.*cameron", re.I), "osm-relation-6046587"),
]


def normalise_name(name: str) -> str:
    raw = name or ""
    # Prefer the segment that names the island (before address tail).
    paren = re.search(r"\(([^)]+)\)", raw)
    if paren and re.search(r"st\s+agnes|scilly|isles of scilly", paren.group(1), re.I):
        raw = paren.group(1)
    if "," in raw:
        parts = [p.strip() for p in raw.split(",")]
        island_part = next(
            (
                p
                for p in parts
                if re.search(
                    r"\b(?:island|inish|inis|eilean|whiddy|turbot|arranmore|heir|oran|horse|"
                    r"micatreer|macatreer|bo a)\b",
                    p,
                    re.I,
                )
            ),
            parts[0],
        )
        raw = island_part
    n = re.sub(r"\([^)]*\)", "", raw)
    n = unicodedata.normalize("NFKD", n)
    n = n.encode("ascii", "ignore").decode()
    n = re.sub(r"[^a-z0-9 ]+", " ", n.lower())
    n = re.sub(r"\s+", " ", n).strip()
    n = re.sub(r"^(?:the |isles? of |island of )", "", n)
    n = re.sub(r"\s+(?:islands?|isles?)$", "", n)
    return n


def ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    r = 6371.0
    t = math.pi / 180
    dlat, dlng = (lat2 - lat1) * t, (lng2 - lng1) * t
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1 * t) * math.cos(lat2 * t) * math.sin(dlng / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def pick_homonym(cands: list[dict], *, lat=None, lng=None) -> dict:
    if lat is not None and lng is not None:
        with_coords = [c for c in cands if isinstance(c.get("lat"), (int, float))]
        if with_coords:
            return min(with_coords, key=lambda c: haversine_km(lat, lng, c["lat"], c["lng"]))
    return max(cands, key=lambda c: (c.get("areaKm2") or 0, len(c.get("name") or "")))


def match_one(cand: dict, idx, by_id: dict[str, dict]) -> dict | None:
    raw_name = (cand.get("islandName") or "").strip()
    nation = (cand.get("nation") or "").strip()
    if not raw_name or not nation:
        return None
    norm = normalise_name(raw_name)
    blob = " ".join(str(cand.get(k) or "") for k in ("notes", "url", "broker", "title"))
    for pat, iid in HINT_RULES:
        if pat.search(blob) and iid in by_id and by_id[iid].get("nation") == nation:
            return row(cand, by_id[iid], "high", "hint")
    iid = ALIASES.get((norm, nation))
    if iid and iid in by_id:
        return row(cand, by_id[iid], "high", "alias")
    exact = idx.get((norm, nation), [])
    if exact:
        isl = pick_homonym(exact, lat=cand.get("lat"), lng=cand.get("lng"))
        conf = "high" if len(exact) == 1 else "medium"
        return row(cand, isl, conf, "exact")
    expanded = idx.get((norm + " island", nation), [])
    if expanded:
        isl = pick_homonym(expanded, lat=cand.get("lat"), lng=cand.get("lng"))
        return row(cand, isl, "high", "suffix-island")
    best: tuple[float, dict] | None = None
    for (key, n), group in idx.items():
        if n != nation:
            continue
        sc = ratio(norm, key)
        if sc < 0.88:
            continue
        isl = pick_homonym(group, lat=cand.get("lat"), lng=cand.get("lng"))
        if best is None or sc > best[0]:
            best = (sc, isl)
    if best:
        conf = "high" if best[0] >= 0.97 else "medium" if best[0] >= 0.92 else "low"
        return row(cand, best[1], conf, "fuzzy")
    return None


def row(cand, isl, confidence, method):
    return {
        **cand,
        "islandId": isl["id"],
        "matchConfidence": confidence,
        "matchedName": isl.get("name"),
        "areaKm2": isl.get("areaKm2"),
        "matchMethod": method,
        "nation": isl.get("nation"),
    }


def build_index(islands: list[dict]) -> dict[tuple[str, str], list[dict]]:
    idx: dict[tuple[str, str], list[dict]] = {}
    for isl in islands:
        nation = isl.get("nation") or ""
        if not nation:
            continue
        keys = {normalise_name(isl.get("name") or "")}
        for v in (isl.get("names") or {}).values():
            if isinstance(v, str):
                keys.add(normalise_name(v))
        for k in keys:
            if k:
                idx.setdefault((k, nation), []).append(isl)
    return idx


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("candidates", type=Path)
    ap.add_argument("-o", "--output", type=Path, required=True)
    args = ap.parse_args()
    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    by_id = {i["id"]: i for i in islands}
    idx = build_index(islands)
    cands = json.loads(args.candidates.read_text(encoding="utf-8"))
    out = [m for c in cands if (m := match_one(c, idx, by_id))]
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"matched {len(out)} / {len(cands)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
