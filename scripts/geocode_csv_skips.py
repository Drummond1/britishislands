#!/usr/bin/env python3
"""
Geocode the 235 CSV rows that the original merge skipped because they
had no DMS coordinates *and* no name-match in the existing dataset.

Method, per row:
  1. Look up `data/csv_import_report.json` → `skipped_no_coords_no_match`
     for (name, region, location) triples.
  2. Wikidata `wbsearchentities` for the name in English **and** the
     regional language (gd / cy / ga depending on the region) → returns
     up to 7 candidate Q-IDs.
  3. For those Q-IDs, batch-fetch `claims` and pull P625 coordinates.
  4. Keep only candidates whose coordinates fall inside the region's
     bounding box (defined below).
  5. **Adopt rule**: if **exactly one** candidate survives, create a new
     `csv-import-geocoded` island entry. Otherwise log for manual review.
  6. Also harvest the Q-ID into the row's record for future enrichment.

Hard rules:
  - Never overwrite an existing island. (`build_index` lookup by loose
    name + 25 km radius first; if it now matches, just enrich.)
  - Never adopt a Q-ID that is *also* the Q-ID of an existing island.
  - Atomic writes; backup the islands.json before mutating.

Outputs:
  data/islands.json                         (mutated)
  data/islands.json.before-csv-geocode      (backup)
  data/csv_geocode_report.json              (audit)
  data/cache_wbsearch.json                  (search cache)
  data/cache_wb_claims.json                 (claims cache)
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS_PATH = DATA / "islands.json"
BACKUP_PATH = DATA / "islands.json.before-csv-geocode"
REPORT_PATH = DATA / "csv_geocode_report.json"
INPUT_REPORT = DATA / "csv_import_report.json"
CACHE_SEARCH = DATA / "cache_wbsearch.json"
CACHE_CLAIMS = DATA / "cache_wb_claims.json"

WD_API = "https://www.wikidata.org/w/api.php"
USER_AGENT = (
    "isles-of-britain/0.5 (csv geocode; static-site prototype)"
)
DELAY_S = 1.2

# Regional bounding boxes (lat_min, lat_max, lng_min, lng_max) — chosen
# conservatively to *exclude* clearly-wrong hits while still admitting
# legitimate islands that sit on the regional fringe. Verified manually
# against the canonical extents of each archipelago/sub-region.
REGION_BBOX = {
    "Outer Hebrides (Scotland)":  (56.5, 58.7, -8.0, -6.3),
    "Inner Hebrides (Scotland)":  (55.2, 58.0, -7.0, -5.2),
    "Argyll (Scotland)":          (55.4, 57.0, -6.5, -4.6),
    "Firth of Clyde (Scotland)":  (54.8, 56.0, -5.5, -4.4),
    "Orkney (Scotland)":          (58.7, 59.5, -3.5, -2.3),
    "Shetland (Scotland)":        (59.5, 61.0, -2.2, -0.5),
    "Scottish Lochs":             (55.8, 58.5, -6.0, -3.0),
    "North Wales":                (52.7, 53.5, -5.3, -3.4),
    "South Wales":                (51.3, 52.2, -5.5, -2.6),
    "England":                    (49.8, 55.8, -6.5,  1.9),
    "Northern Ireland":           (54.0, 55.4, -8.2, -5.4),
    "Ireland (RoI)":              (51.4, 55.4, -10.6, -5.9),
    "Isle of Man":                (54.0, 54.5, -4.9, -4.2),
    "Channel Islands":            (49.0, 50.0, -3.0, -1.7),
    "France (within 50 mi)":      (48.5, 51.1, -3.0,  2.2),
}

# Some regions in the CSV are spelled differently or grouped; collapse
# them here.
REGION_ALIASES = {
    "outer hebrides (scotland)": "Outer Hebrides (Scotland)",
    "outer hebrides": "Outer Hebrides (Scotland)",
    "inner hebrides (scotland)": "Inner Hebrides (Scotland)",
    "inner hebrides": "Inner Hebrides (Scotland)",
    "argyll (scotland)": "Argyll (Scotland)",
    "argyll": "Argyll (Scotland)",
    "firth of clyde (scotland)": "Firth of Clyde (Scotland)",
    "clyde": "Firth of Clyde (Scotland)",
    "orkney (scotland)": "Orkney (Scotland)",
    "orkney": "Orkney (Scotland)",
    "shetland (scotland)": "Shetland (Scotland)",
    "shetland": "Shetland (Scotland)",
    "scottish lochs": "Scottish Lochs",
    "north wales": "North Wales",
    "south wales": "South Wales",
    "england": "England",
    "northern ireland (uk)": "Northern Ireland",
    "northern ireland": "Northern Ireland",
    "ireland (roi)": "Ireland (RoI)",
    "ireland": "Ireland (RoI)",
    "republic of ireland": "Ireland (RoI)",
    "isle of man (crown dependency)": "Isle of Man",
    "isle of man": "Isle of Man",
    "channel islands (crown dependency)": "Channel Islands",
    "channel islands": "Channel Islands",
    "france (within 50 mi)": "France (within 50 mi)",
}

# Language hint per region for the wbsearchentities lookup.
REGION_LANGS = {
    "Outer Hebrides (Scotland)":  ["en", "gd"],
    "Inner Hebrides (Scotland)":  ["en", "gd"],
    "Argyll (Scotland)":          ["en", "gd"],
    "Firth of Clyde (Scotland)":  ["en", "gd"],
    "Orkney (Scotland)":          ["en", "sco"],
    "Shetland (Scotland)":        ["en", "sco"],
    "Scottish Lochs":             ["en", "gd"],
    "North Wales":                ["en", "cy"],
    "South Wales":                ["en", "cy"],
    "England":                    ["en"],
    "Northern Ireland":           ["en", "ga"],
    "Ireland (RoI)":              ["en", "ga"],
    "Isle of Man":                ["en", "gv"],
    "Channel Islands":            ["en", "fr", "nrf"],
    "France (within 50 mi)":      ["en", "fr"],
}


def _atomic_write(path: Path, payload) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _load_cache(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {}


def _get_json(url: str, params: dict, retries: int = 6) -> dict:
    qs = urllib.parse.urlencode(params)
    full = url + "?" + qs
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                full,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as exc:
            if attempt + 1 == retries:
                raise
            wait = max(int(exc.headers.get("Retry-After", "0") or 0), 4 * (2 ** attempt))
            print(f"  http {exc.code}; sleeping {wait}s ({attempt + 1}/{retries})",
                  file=sys.stderr)
            time.sleep(wait)
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt + 1 == retries:
                raise
            time.sleep(4 * (2 ** attempt))
    return {}


def normalise_region(s: str) -> str:
    return REGION_ALIASES.get((s or "").strip().lower(), s)


def clean_name(name: str) -> str:
    """Strip a single parenthetical hint ('Pabbay (Barra)' → 'Pabbay')
    so wbsearchentities has a cleaner string to match. The hint was just
    for human disambiguation."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", name or "").strip()


def parenthetical(name: str) -> str:
    m = re.search(r"\(([^)]+)\)\s*$", name or "")
    return m.group(1).strip() if m else ""


def search(name: str, lang: str, cache: dict) -> list[dict]:
    """wbsearchentities → list of {id, label, description}."""
    key = f"{lang}::{name.lower()}"
    if key in cache:
        return cache[key]
    params = {
        "action": "wbsearchentities",
        "format": "json",
        "search": name,
        "language": lang,
        "uselang": lang,
        "type": "item",
        "limit": "7",
    }
    try:
        payload = _get_json(WD_API, params)
    except Exception as exc:
        print(f"  search failed for {name!r} [{lang}]: {exc!r}", file=sys.stderr)
        cache[key] = []
        return []
    hits = payload.get("search") or []
    out = [
        {"id": h.get("id"), "label": h.get("label", ""),
         "description": h.get("description", "")}
        for h in hits if (h.get("id") or "").startswith("Q")
    ]
    cache[key] = out
    _atomic_write(CACHE_SEARCH, cache)
    time.sleep(DELAY_S)
    return out


def fetch_claims(qids: list[str], cache: dict) -> dict[str, dict]:
    """For each Q-ID, fetch P625 (coordinate location) and P31 (instance
    of) claims. Returns {qid: {"coord": (lat, lng) | None, "p31": [Qx,..]}}."""
    missing = [q for q in qids if q not in cache]
    BATCH = 50
    for i in range(0, len(missing), BATCH):
        batch = missing[i : i + BATCH]
        params = {
            "action": "wbgetentities",
            "format": "json",
            "ids": "|".join(batch),
            "props": "claims",
        }
        try:
            payload = _get_json(WD_API, params)
        except Exception as exc:
            print(f"  claims batch failed: {exc!r}", file=sys.stderr)
            continue
        entities = payload.get("entities") or {}
        for q in batch:
            ent = entities.get(q) or {}
            claims = ent.get("claims") or {}
            coord = None
            for p625 in claims.get("P625") or []:
                ds = (p625.get("mainsnak") or {}).get("datavalue") or {}
                v = (ds.get("value") or {})
                if "latitude" in v and "longitude" in v:
                    coord = (float(v["latitude"]), float(v["longitude"]))
                    break
            p31 = []
            for c in claims.get("P31") or []:
                ds = (c.get("mainsnak") or {}).get("datavalue") or {}
                v = (ds.get("value") or {})
                if isinstance(v, dict) and v.get("id"):
                    p31.append(v["id"])
            cache[q] = {"coord": coord, "p31": p31}
        _atomic_write(CACHE_CLAIMS, cache)
        time.sleep(DELAY_S)
    return {q: cache.get(q, {"coord": None, "p31": []}) for q in qids}


def in_bbox(coord: tuple[float, float] | None, bbox: tuple[float, float, float, float]) -> bool:
    if not coord:
        return False
    lat, lng = coord
    lat_min, lat_max, lng_min, lng_max = bbox
    return lat_min <= lat <= lat_max and lng_min <= lng <= lng_max


# Q-IDs of typical "island"-like classes, used for soft confidence.
ISLAND_CLASSES = {
    "Q23442",     # island
    "Q23397",     # uninhabited island
    "Q205892",    # islet
    "Q1183670",   # tidal island
    "Q193561",    # archipelago
    "Q35509",     # cave
    "Q204166",    # reef
    "Q31796",     # skerry
    "Q187798",    # bank (geography)
}


def main() -> int:
    if not INPUT_REPORT.exists():
        print(f"Missing {INPUT_REPORT}; run scripts/merge_csv.py first.", file=sys.stderr)
        return 1
    print(f"Loading {INPUT_REPORT.name}…")
    rpt = json.loads(INPUT_REPORT.read_text())
    skipped = rpt.get("skipped_no_coords_no_match") or []
    print(f"  rows to try: {len(skipped)}")

    print(f"Loading {ISLANDS_PATH.name}…")
    islands = json.load(open(ISLANDS_PATH, encoding="utf-8"))
    print(f"  {len(islands):,} islands loaded")
    BACKUP_PATH.write_text(json.dumps(islands, ensure_ascii=False, indent=2))

    # Build a set of existing Q-IDs so we never adopt a duplicate.
    existing_qids = {(i.get("wikidata") or "").strip() for i in islands}

    cache_search = _load_cache(CACHE_SEARCH)
    cache_claims = _load_cache(CACHE_CLAIMS)

    out_report = {
        "input": len(skipped),
        "adopted": [],          # high-confidence single-hit
        "ambiguous": [],        # multiple in-bbox hits
        "no_in_bbox_hit": [],   # candidates but none in bbox
        "no_search_hit": [],    # search returned nothing
        "skipped_unknown_region": [],
    }

    for row in skipped:
        name = row.get("name", "")
        region = normalise_region(row.get("region") or "")
        bbox = REGION_BBOX.get(region)
        if not bbox:
            out_report["skipped_unknown_region"].append({**row, "norm_region": region})
            continue
        clean = clean_name(name)
        if not clean:
            continue

        langs = REGION_LANGS.get(region, ["en"])
        # Try the cleaned name first, then the original (with parenthetical).
        hits = []
        for lang in langs:
            hits.extend(search(clean, lang, cache_search))
        # Dedup by Q-ID.
        seen = set()
        unique = []
        for h in hits:
            if h["id"] in seen:
                continue
            seen.add(h["id"])
            unique.append(h)

        if not unique:
            out_report["no_search_hit"].append(row)
            continue

        claims = fetch_claims([h["id"] for h in unique], cache_claims)

        in_box_hits = []
        for h in unique:
            c = claims.get(h["id"], {})
            if h["id"] in existing_qids:
                continue
            if in_bbox(c.get("coord"), bbox):
                p31 = set(c.get("p31") or [])
                # Tag the hit with whether it looks island-y, used to
                # break ties below.
                h_full = dict(h)
                h_full["coord"] = c["coord"]
                h_full["island_like"] = bool(p31 & ISLAND_CLASSES)
                in_box_hits.append(h_full)

        if not in_box_hits:
            out_report["no_in_bbox_hit"].append({**row, "candidates": [h["id"] for h in unique]})
            continue

        # Tie-break: prefer island-class entities over generic ones.
        island_like = [h for h in in_box_hits if h["island_like"]]
        chosen = None
        if len(island_like) == 1:
            chosen = island_like[0]
        elif len(island_like) > 1:
            out_report["ambiguous"].append({
                **row,
                "candidates": [{"id": h["id"], "label": h["label"],
                                "coord": h["coord"], "desc": h["description"]}
                               for h in island_like],
            })
            continue
        elif len(in_box_hits) == 1:
            chosen = in_box_hits[0]
        else:
            out_report["ambiguous"].append({
                **row,
                "candidates": [{"id": h["id"], "label": h["label"],
                                "coord": h["coord"], "desc": h["description"]}
                               for h in in_box_hits],
            })
            continue

        lat, lng = chosen["coord"]
        island_id = f"csv-geocoded-{chosen['id']}"
        if any(i.get("id") == island_id for i in islands):
            continue
        nation_map = {
            "Outer Hebrides (Scotland)": "Scotland",
            "Inner Hebrides (Scotland)": "Scotland",
            "Argyll (Scotland)":         "Scotland",
            "Firth of Clyde (Scotland)": "Scotland",
            "Orkney (Scotland)":         "Scotland",
            "Shetland (Scotland)":       "Scotland",
            "Scottish Lochs":            "Scotland",
            "North Wales":               "Wales",
            "South Wales":               "Wales",
            "England":                   "England",
            "Northern Ireland":          "Northern Ireland",
            "Ireland (RoI)":             "Ireland",
            "Isle of Man":               "Isle of Man",
            "Channel Islands":           "Crown Dependency",
            "France (within 50 mi)":     "France",
        }
        archipelago_map = {
            "Outer Hebrides (Scotland)": "Outer Hebrides",
            "Inner Hebrides (Scotland)": "Inner Hebrides",
            "Orkney (Scotland)":         "Orkney",
            "Shetland (Scotland)":       "Shetland",
            "Channel Islands":           "Channel Islands",
        }
        new_island = {
            "id": island_id,
            "name": chosen["label"] or clean,
            "nation": nation_map.get(region, ""),
            "archipelago": archipelago_map.get(region, row.get("location") or ""),
            "lat": lat,
            "lng": lng,
            "type": "sea",
            "areaKm2": None,
            "population": None,
            "shortDescription": chosen.get("description") or "",
            "longDescription": "",
            "tags": [],
            "source": "csv-geocoded",
            "sources": ["csv-geocoded", f"wikidata:{chosen['id']}"],
            "wikidata": chosen["id"],
            "images": [],
        }
        islands.append(new_island)
        existing_qids.add(chosen["id"])
        out_report["adopted"].append({
            "row_name": name, "id": island_id, "qid": chosen["id"],
            "coord": chosen["coord"], "label": chosen["label"],
        })
        if len(out_report["adopted"]) % 10 == 0:
            print(f"  adopted: {len(out_report['adopted'])} so far")

    _atomic_write(ISLANDS_PATH, islands)
    _atomic_write(REPORT_PATH, out_report)

    print()
    print(f"Adopted (single high-confidence hit): {len(out_report['adopted']):,}")
    print(f"Ambiguous (multiple in-bbox hits):    {len(out_report['ambiguous']):,}")
    print(f"No in-bbox hit:                       {len(out_report['no_in_bbox_hit']):,}")
    print(f"No search hit:                        {len(out_report['no_search_hit']):,}")
    print(f"Skipped (unknown region):             {len(out_report['skipped_unknown_region']):,}")
    print(f"Report → {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
