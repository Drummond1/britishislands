#!/usr/bin/env python3
"""Discover islands named in Scottish seal haul-out designations (D6).

Parses the Protection of Seals (Designation of Haul-Out Sites) (Scotland)
Order 2014 schedule from legislation.gov.uk ``data.xml`` (Crown legislation;
redistribution of site names + coords under OGL practice for statutory lists).

Ethics: island-level presence only — no haul-out timing/counts.

Run::

    python3 scripts/discover_seal_haulouts.py
    python3 scripts/discover_seal_haulouts.py --refresh
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = DATA / "cache_seal_haulouts_ssi.xml"
OUT = DATA / "discovery" / "candidates_seal_haulouts.json"
REPORT = DATA / "discovery_seal_haulouts_report.json"
URL = "https://www.legislation.gov.uk/ssi/2014/185/schedule/made/data.xml"
USER_AGENT = "isles-of-britain/0.1 (discover-seal-haulouts; research)"

ISLANDISH_RE = re.compile(
    r"\b(island|isle|holm|skerry|sgeir|stack|stac|rock|reef|carrick|"
    r"eilean|inch|ay|ey)\b",
    re.I,
)
DMS_RE = re.compile(
    r"(\d{1,2})°(\d{1,2})′(\d{1,2}(?:\.\d+)?)″([NS])\s+"
    r"(\d{1,3})°(\d{1,2})′(\d{1,2}(?:\.\d+)?)″([EW])"
)
ROW_RE = re.compile(
    r">([^<]{3,90})</td>\s*<td[^>]*>"
    r"(\d{1,2}°[^<]+)</td>\s*<td[^>]*>"
    r"(\d{1,2}°[^<]+)</td>\s*<td[^>]*>"
    r"(\d{1,2}°[^<]+)</td>\s*<td[^>]*>"
    r"(\d{1,2}°[^<]+)</td>",
    re.I,
)

sys.path.insert(0, str(ROOT / "scripts"))
from discovery import common as c  # noqa: E402


def _fetch_xml() -> str:
    if CACHE.is_file() and CACHE.stat().st_size > 1000:
        return CACHE.read_text(encoding="utf-8", errors="replace")
    req = urllib.request.Request(URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(text, encoding="utf-8")
    return text


def _dms_to_decimal(text: str) -> tuple[float, float] | None:
    m = DMS_RE.search(text.replace(" ", " "))
    if not m:
        # tolerate alternate primes
        alt = (
            text.replace("'", "′")
            .replace('"', "″")
            .replace("´", "′")
            .replace("″", "″")
        )
        m = DMS_RE.search(alt)
    if not m:
        return None
    lat = int(m.group(1)) + int(m.group(2)) / 60 + float(m.group(3)) / 3600
    if m.group(4) == "S":
        lat = -lat
    lon = int(m.group(5)) + int(m.group(6)) / 60 + float(m.group(7)) / 3600
    if m.group(8) == "W":
        lon = -lon
    return lat, lon


def _parse_sites(xml: str) -> list[dict[str, Any]]:
    sites: list[dict[str, Any]] = []
    for m in ROW_RE.finditer(xml):
        name = m.group(1).strip()
        name = re.sub(r"\s+", " ", name)
        # Drop parenthetical locality notes for matching but keep display
        if name.lower() in {"site name", "column 1", "column 2"}:
            continue
        if not ISLANDISH_RE.search(name) and not re.search(
            r"(Skerry|Holm|Sgeir|Eilean|Stack|Rock|Isle|Island)", name
        ):
            continue
        coords: list[tuple[float, float]] = []
        for g in m.groups()[1:]:
            pair = _dms_to_decimal(g)
            if pair:
                coords.append(pair)
        if len(coords) < 2:
            continue
        lat = sum(p[0] for p in coords) / len(coords)
        lon = sum(p[1] for p in coords) / len(coords)
        if not c.in_remit(lat, lon):
            continue
        sites.append({
            "name": name,
            "lat": round(lat, 5),
            "lng": round(lon, 5),
        })
    by_name: dict[str, dict] = {}
    for s in sites:
        by_name.setdefault(s["name"].lower(), s)
    return list(by_name.values())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    if args.refresh and CACHE.exists():
        CACHE.unlink()

    xml = _fetch_xml()
    sites = _parse_sites(xml)
    islands = c.load_json(c.ISLANDS_PATH, [])
    index = c.build_island_index(islands)

    candidates: list[dict] = []
    for s in sites:
        probe = {"lat": s["lat"], "lng": s["lng"], "name": s["name"]}
        if c.find_existing_match(probe, index):
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", s["name"].lower()).strip("-")
        candidates.append({
            "candidateId": f"seal-haulout-{slug}",
            "name": s["name"],
            "lat": s["lat"],
            "lng": s["lng"],
            "nation": "Scotland",
            "featureKind": "island",
            "osmType": None,
            "osmId": None,
            "wikidata": "",
            "wikipedia": "",
            "scanConfidence": "medium",
            "sourceHints": [{
                "name": "SSI 2014/185 seal haul-out schedule",
                "url": "https://www.legislation.gov.uk/ssi/2014/185/schedule/made",
                "license": "OGL / Crown legislation",
            }],
            "tags": ["island", "seal-haulout", "scotland"],
        })

    report = {
        "script": "discover_seal_haulouts.py",
        "sitesParsed": len(sites),
        "candidates": len(candidates),
        "sourceUrl": URL,
    }
    if not args.dry_run:
        c.save_json(OUT, candidates)
        c.save_json(REPORT, report)
    print(
        f"Seal haul-outs: parsed {len(sites)}, gap candidates {len(candidates)} → {OUT}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
