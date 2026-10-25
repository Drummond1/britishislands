#!/usr/bin/env python3
"""Harvest island names + coordinates from Wikipedia list-article wikitext (#76).

Parses ``{{Coord|…}}`` and ``{{coord|…}}`` templates on curated list pages,
flags rows not within 1 km of an existing atlas island.

Run::

    python3 scripts/discover_wikipedia_coord_lists.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "discovery" / "candidates_wikipedia_coords.json"
REPORT = DATA / "discovery_wikipedia_coords_report.json"
CACHE = DATA / "cache_discovery_wiki_coords.json"
USER_AGENT = "isles-of-britain/0.1 (discover-wiki-coords)"
MATCH_KM = 1.0

# High-yield list articles (extend as needed)
LIST_PAGES = [
    "List of islands of Scotland",
    "List of islands of England",
    "List of islands of Wales",
    "List of islands of Ireland",
    "List of islands in the Inner Hebrides",
    "List of islands in the Outer Hebrides",
    "List of islands of the Orkney Islands",
    "List of islands of Shetland",
    "List of islands in Loch Maree",
    "List of islands in Loch Lomond",
    "List of islands of the Isles of Scilly",
    "List of islands in the River Thames",
    "List of islands of County Donegal",
    "List of islands of County Galway",
    "List of islands of County Mayo",
    "List of islands of County Kerry",
    "List of islands of County Cork",
    "List of islands in Clew Bay",
    "List of islands of Northern Ireland",
    "List of islands in Lough Erne",
    "List of islands in Lough Neagh",
]

COORD_BLOCK_RE = re.compile(
    r"\[\[([^\]|#]+)(?:\|[^\]]+)?\]\][^{]{0,160}\{\{[Cc]oord\|([^}]+)\}\}",
    re.MULTILINE,
)

sys.path.insert(0, str(ROOT / "scripts"))
from discovery import common as c  # noqa: E402


def _wiki_wikitext(title: str) -> str:
    params = {
        "action": "query",
        "format": "json",
        "prop": "revisions",
        "rvprop": "content",
        "titles": title,
        "rvslots": "main",
    }
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"https://en.wikipedia.org/w/api.php?{qs}",
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        data = json.loads(resp.read())
    pages = (data.get("query") or {}).get("pages") or {}
    for page in pages.values():
        revs = page.get("revisions") or []
        if revs:
            slots = revs[0].get("slots") or {}
            main = slots.get("main") or revs[0]
            return main.get("*") or ""
    return ""


def _coord_template_to_decimal(body: str) -> tuple[float | None, float | None]:
    """Parse Wikipedia {{coord|…}} bodies (DMS or decimal, N/S/E/W)."""
    parts = [p.strip() for p in body.split("|") if p.strip()]
    if len(parts) < 2:
        return None, None

    def _hemi_mult(idx: int, pos: str, neg: str) -> float:
        if idx < len(parts) and parts[idx].upper() in (pos, neg):
            return -1.0 if parts[idx].upper() == neg else 1.0
        return 1.0

    try:
        if len(parts) >= 4 and parts[2].upper() in ("N", "S"):
            lat = float(parts[0]) + float(parts[1]) / 60.0
            lat *= _hemi_mult(2, "N", "S")
            lon = float(parts[3]) + (float(parts[4]) / 60.0 if len(parts) > 4 else 0.0)
            lon *= _hemi_mult(5 if len(parts) > 5 else 4, "E", "W")
            return lat, lon
        if len(parts) >= 6 and parts[3].upper() in ("N", "S"):
            lat = float(parts[0]) + float(parts[1]) / 60 + float(parts[2]) / 3600
            lat *= _hemi_mult(3, "N", "S")
            lon = float(parts[4]) + float(parts[5]) / 60 + (float(parts[6]) / 3600 if len(parts) > 6 else 0)
            lon *= _hemi_mult(7 if len(parts) > 7 else 6, "E", "W")
            return lat, lon
        lat, lon = float(parts[0]), float(parts[1])
        return lat, lon
    except (ValueError, IndexError):
        return None, None


def _parse_coords(text: str, list_page: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[tuple[str, float, float]] = set()

    for m in COORD_BLOCK_RE.finditer(text):
        name = m.group(1).strip()
        lat, lon = _coord_template_to_decimal(m.group(2))
        if lat is None or lon is None:
            continue
        key = (name.lower(), round(lat, 4), round(lon, 4))
        if key in seen:
            continue
        seen.add(key)
        found.append({"name": name, "lat": lat, "lon": lon, "listPage": list_page})

    return found


def _nearest_atlas_km(lat: float, lon: float, islands: list[dict]) -> float:
    best = 9999.0
    for isl in islands:
        ilat, ilon = isl.get("lat"), isl.get("lng") or isl.get("lon")
        if ilat is None or ilon is None:
            continue
        d = c.haversine_km(lat, lon, float(ilat), float(ilon))
        if d < best:
            best = d
    return best


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--match-km", type=float, default=MATCH_KM)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cache = c.load_json(CACHE, {})
    all_coords: list[dict[str, Any]] = []

    for page in LIST_PAGES:
        if page in cache:
            text = cache[page]
        else:
            print(f"→ {page}", flush=True)
            try:
                text = _wiki_wikitext(page)
                cache[page] = text
                c.save_json(CACHE, cache)
            except Exception as exc:
                print(f"  skip: {exc}", file=sys.stderr)
                continue
            time.sleep(c.DELAY_S)
        rows = _parse_coords(text, page)
        print(f"  {len(rows)} coord hits", flush=True)
        all_coords.extend(rows)

    islands = c.load_islands()
    candidates: list[dict[str, Any]] = []
    for row in all_coords:
        lat, lon = row["lat"], row["lon"]
        if not c.in_remit(lat, lon):
            continue
        d_km = _nearest_atlas_km(lat, lon, islands)
        if d_km <= args.match_km:
            continue
        name = row.get("name") or f"Island near {row['listPage']}"
        slug = c.slugify(name)
        candidates.append({
            "candidateId": f"wiki-coord-{slug}-{round(lat, 3)}",
            "name": name,
            "lat": round(lat, 5),
            "lng": round(lon, 5),
            "nation": c.nation_for(lat, lon),
            "featureKind": "island",
            "scanConfidence": "medium" if row.get("name") else "low",
            "nearestAtlasKm": round(d_km, 3),
            "listPage": row["listPage"],
            "sourceHints": [{
                "name": "Wikipedia list coordinates",
                "url": f"https://en.wikipedia.org/wiki/{row['listPage'].replace(' ', '_')}",
                "license": "CC-BY-SA-4.0",
            }],
            "tags": ["island", "wikipedia-coord-list"],
        })

    report = {"coordHits": len(all_coords), "gaps": len(candidates), "lists": len(LIST_PAGES)}
    print(f"Wikipedia coord gaps: {len(candidates):,}", flush=True)

    if not args.dry_run:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(candidates, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
