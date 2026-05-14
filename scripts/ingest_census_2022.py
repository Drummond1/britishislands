#!/usr/bin/env python3
"""
Ingest Census 2022 / 2021 island-level population from the five
authoritative bodies in the British Isles:

* **NRS Scotland (2022)** — "Scotland's Inhabited Islands" report,
  61 inhabited islands.  OGL v3.0.
  <https://www.nrscotland.gov.uk/statistics-and-data/statistics/scotlands-census/scotlands-census-2022-results>

* **ONS England + Wales (2021)** — most via Output Area aggregation;
  IoW, Hayling, Canvey, Lindisfarne published directly.  OGL v3.0.
  <https://www.ons.gov.uk/peoplepopulationandcommunity/populationandmigration/populationestimates>

* **NISRA Northern Ireland (2021)** — Rathlin Island published
  directly; others via SOA/DZ aggregation.  OGL v3.0.
  <https://build.nisra.gov.uk/en/standard/2021>

* **CSO Ireland (2022)** — offshore-islands summary report.  PSI
  Re-use (OGL-equivalent).
  <https://www.cso.ie/en/csolatestnews/presspages/2023/offshoreislands/>

* **Isle of Man Census (2021)** — single number.  OGL IoM.

* **States of Jersey + Guernsey (2021/22)** — per-bailiwick.

Method
------
This script does **not** scrape — each body has a different schedule
and varying API surface, and CSO Ireland publishes only as PDFs at
island granularity.  Instead we accept *staged* CSVs at:

    data/census2022_nrs.csv          (Scotland)
    data/census2022_ons.csv          (England + Wales)
    data/census2022_nisra.csv        (Northern Ireland)
    data/census2022_cso.csv          (Ireland)
    data/census2022_iom.csv          (Isle of Man)
    data/census2022_states.csv       (Channel Islands)

Each CSV must have these columns (others ignored)::

    island_name, population, year, source, attribution
    (optional) households, age_under_16, age_16_64, age_65_plus,
               gaelic_speakers, welsh_speakers, irish_speakers

The script normalises ``island_name`` for matching against
``islands.json`` and stages an ``islandId -> populationDetails`` payload
into ``data/cache_census2022.json``.  **It never overwrites a newer
``population`` value with an older figure** (see "Rules" below).

CLI::

    python3 scripts/ingest_census_2022.py --dry-run
    python3 scripts/ingest_census_2022.py --commit
    python3 scripts/ingest_census_2022.py --commit --limit 50 --verbose

Rules
-----
* When the staged CSV says e.g. NRS 2022 and the island already has a
  ``populationYear: 2024`` (none currently, but reserved), the staging
  step skips that island and records ``skipped_newer_present: …``.
* When the staged CSV is missing for a nation, that nation's islands
  are not touched.  The user can stage CSVs incrementally.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS_PATH = DATA / "islands.json"

STAGED_CACHE = DATA / "cache_census2022.json"
REPORT = DATA / "census2022_ingestion_report.json"

CSV_PATHS = {
    "nrs":    DATA / "census2022_nrs.csv",
    "ons":    DATA / "census2022_ons.csv",
    "nisra":  DATA / "census2022_nisra.csv",
    "cso":    DATA / "census2022_cso.csv",
    "iom":    DATA / "census2022_iom.csv",
    "states": DATA / "census2022_states.csv",
}

# Attribution strings per body, used as the canonical
# `populationAttribution` value.
ATTRIBUTIONS = {
    "nrs":    "© Crown copyright, National Records of Scotland (OGL v3.0). Source: Scotland's Census 2022 — Scotland's Inhabited Islands report.",
    "ons":    "© Crown copyright, Office for National Statistics (OGL v3.0). Source: ONS Census 2021 (England and Wales).",
    "nisra":  "© Crown copyright, Northern Ireland Statistics and Research Agency (OGL v3.0). Source: NISRA Census 2021 (Northern Ireland).",
    "cso":    "© Government of Ireland, Central Statistics Office (PSI Re-use). Source: CSO Census 2022 — Offshore Islands report.",
    "iom":    "© Isle of Man Government (OGL IoM). Source: Isle of Man Census 2021.",
    "states": "© States of Jersey and States of Guernsey (Mixed open licences). Source: Bailiwick censuses 2021/22.",
}


# ---------- IO ----------

def _atomic_write_json(path: Path, payload: Any, *, compact: bool = False) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    body = (json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            if compact else json.dumps(payload, ensure_ascii=False, indent=2))
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, path)


def _load_json(path: Path, default):
    if not path.exists(): return default
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"  WARN: {path.name} unreadable ({exc})", file=sys.stderr)
        return default


# ---------- Name normalisation ----------

_NAME_NOISE_RE = re.compile(r"\b(isle|island|islands|isles|of|the)\b", re.IGNORECASE)
_PUNCT_RE = re.compile(r"[^a-z0-9]+")


def _norm_name(s: str) -> str:
    """Diacritic-fold, lowercase, strip 'isle of'/'island' filler, collapse."""
    if not s: return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = _NAME_NOISE_RE.sub(" ", s)
    s = _PUNCT_RE.sub(" ", s)
    return " ".join(s.split())


def _build_name_index(islands: list[dict]) -> dict[str, list[str]]:
    """Map normalised name -> list[islandId], deduplicated & ranked.

    When multiple islands share a normalised name (e.g. several
    'Inch' islands, or 'Skye' = the main isle + a small OSM way also
    labelled 'Skye'), we prefer hand-curated IDs (no `osm-`/`wd-`/
    `csv-` prefix) over discovery-tagged ones.
    """
    raw: dict[str, set[str]] = {}
    for isl in islands:
        if not isinstance(isl, dict) or not isl.get("id"):
            continue
        names_seen: set[str] = set()
        names_seen.add(_norm_name(isl.get("name") or ""))
        for nm in (isl.get("names") or {}).values():
            names_seen.add(_norm_name(nm or ""))
        if isl.get("aliases"):
            for nm in (isl.get("aliases") or []):
                names_seen.add(_norm_name(nm or ""))
        for k in names_seen:
            if not k: continue
            raw.setdefault(k, set()).add(isl["id"])
    # Rank: hand-curated IDs first, then OSM, then wd-, then csv-.
    def _rank(iid: str) -> tuple[int, str]:
        if iid.startswith("csv-"):       return (3, iid)
        if iid.startswith("wd-"):        return (2, iid)
        if iid.startswith("osm-"):       return (1, iid)
        return (0, iid)
    return {k: sorted(v, key=_rank) for k, v in raw.items()}


# ---------- CSV reader ----------

def _try_int(s: Any) -> int | None:
    if s is None: return None
    s = str(s).strip()
    if s in ("", "-", ".."): return None
    try: return int(float(s))
    except (TypeError, ValueError): return None


def parse_census_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        rdr = csv.DictReader(f)
        for raw in rdr:
            # Lower-case keys for tolerance.
            row = {(k or "").strip().lower(): (v or "").strip()
                   for k, v in raw.items()}
            name = row.get("island_name") or row.get("name") or ""
            if not name: continue
            pop = _try_int(row.get("population"))
            year = _try_int(row.get("year"))
            source = (row.get("source") or "").strip()
            attribution = (row.get("attribution") or "").strip()
            households = _try_int(row.get("households"))
            ages = {
                "under16": _try_int(row.get("age_under_16")),
                "16to64":  _try_int(row.get("age_16_64")),
                "65plus":  _try_int(row.get("age_65_plus")),
            }
            ages = {k: v for k, v in ages.items() if v is not None}
            rows.append({
                "name": name, "population": pop, "year": year,
                "source": source, "attribution": attribution,
                "households": households,
                "ageStructure": ages or None,
                "gaelicSpeakers": _try_int(row.get("gaelic_speakers")),
                "welshSpeakers":  _try_int(row.get("welsh_speakers")),
                "irishSpeakers":  _try_int(row.get("irish_speakers")),
            })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if not ISLANDS_PATH.exists(): sys.exit(f"FATAL: {ISLANDS_PATH} missing")
    islands = _load_json(ISLANDS_PATH, [])
    if not islands: sys.exit("FATAL: islands.json empty")
    print(f"Loaded {len(islands):,} islands")

    # Index for name lookup.
    idx = _build_name_index(islands)
    print(f"  Indexed {sum(len(v) for v in idx.values()):,} name aliases "
          f"({len(idx):,} unique normalised names)")
    if args.limit:
        islands_subset = set(i["id"] for i in islands[: args.limit] if i.get("id"))
    else:
        islands_subset = None

    # Existing population values, by islandId, for the "don't overwrite newer"
    # rule.
    by_id = {i["id"]: i for i in islands if isinstance(i, dict) and i.get("id")}

    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    staged: dict[str, dict] = {}
    nation_counts: dict[str, int] = {}
    missing_nation_csvs: list[str] = []
    skipped_newer: list[dict] = []
    unmatched: list[dict] = []
    matched_sample: list[dict] = []
    ambiguous_sample: list[dict] = []

    for nation, csv_path in CSV_PATHS.items():
        rows = parse_census_csv(csv_path)
        if not rows:
            missing_nation_csvs.append(f"{nation} ({csv_path.name})")
            continue
        print(f"  {nation.upper()}: {len(rows)} rows from {csv_path.name}")
        for r in rows:
            nkey = _norm_name(r["name"])
            if not nkey:
                continue
            candidates = idx.get(nkey, [])
            if not candidates:
                unmatched.append({"nation": nation, "csvName": r["name"],
                                  "norm": nkey})
                continue
            # The index is already ranked: hand-curated (no prefix) <
            # osm- < wd- < csv-.  When the top candidate is uniquely
            # rank 0 (hand-curated) we accept it; otherwise check
            # whether multiple share the same top rank.
            def _rkey(iid_):
                if iid_.startswith("csv-"): return 3
                if iid_.startswith("wd-"):  return 2
                if iid_.startswith("osm-"): return 1
                return 0
            top_rank = _rkey(candidates[0])
            top_candidates = [c for c in candidates if _rkey(c) == top_rank]
            if len(top_candidates) > 1:
                ambiguous_sample.append({
                    "nation": nation, "csvName": r["name"],
                    "norm": nkey, "candidates": candidates[:5],
                })
                continue
            iid = top_candidates[0]
            if islands_subset is not None and iid not in islands_subset:
                continue
            existing = by_id.get(iid) or {}
            cur_year = existing.get("populationYear")
            if isinstance(cur_year, int) and isinstance(r["year"], int) and cur_year > r["year"]:
                skipped_newer.append({
                    "id": iid, "currentYear": cur_year, "csvYear": r["year"],
                })
                continue
            # Compose populationDetails.
            details: dict[str, Any] = {}
            if r.get("households") is not None: details["households"] = r["households"]
            if r.get("ageStructure"): details["ageStructure"] = r["ageStructure"]
            for langkey in ("gaelicSpeakers", "welshSpeakers", "irishSpeakers"):
                if r.get(langkey) is not None:
                    details[langkey] = r[langkey]
            staged[iid] = {
                "population": r["population"],
                "populationYear": r["year"],
                "populationSource": (r["source"]
                                     or f"{nation}-{r['year']}"
                                     or nation),
                "populationConfidence": "high",
                "populationAttribution": (r["attribution"]
                                          or ATTRIBUTIONS.get(nation, "")),
                "populationFetchedAt": fetched_at,
                "populationDetails": details or None,
            }
            nation_counts[nation] = nation_counts.get(nation, 0) + 1
            if len(matched_sample) < 50:
                matched_sample.append({
                    "id": iid, "nation": nation, "csvName": r["name"],
                    "population": r["population"], "year": r["year"],
                })
            if args.verbose:
                print(f"  + [{nation}] {r['name']} → {iid}: pop {r['population']}",
                      flush=True)

    report = {
        "startedAt": fetched_at,
        "islandsLoaded": len(islands),
        "stagedCount": len(staged),
        "stagedByNation": nation_counts,
        "missingNationCsvs": missing_nation_csvs,
        "skippedDueToNewerExisting": skipped_newer[:50],
        "unmatchedCsvRows": unmatched[:50],
        "ambiguousCsvRows": ambiguous_sample[:50],
        "matchedSample": matched_sample,
        "dryRun": bool(args.dry_run or not args.commit),
    }
    _atomic_write_json(REPORT, report)
    print()
    print(f"Audit  → {REPORT.name}")
    if missing_nation_csvs:
        print(f"Skipped (no CSV staged): {', '.join(missing_nation_csvs)}")
    print(f"Staged: {len(staged):,} islands populated from 2022 census")
    print(f"  by nation: {nation_counts}")
    if unmatched:
        print(f"  unmatched CSV rows: {len(unmatched)} "
              f"(top 5: {[u['csvName'] for u in unmatched[:5]]})")
    if ambiguous_sample:
        print(f"  ambiguous: {len(ambiguous_sample)} — "
              f"resolve by adding `island_id` column to the CSV.")

    if args.dry_run:
        print(f"\nDRY RUN — cache_census2022.json NOT written. "
              f"Would have staged {len(staged):,} islands.")
        return 0
    if not args.commit:
        print("\n(--commit not supplied; cache_census2022.json NOT written.)")
        return 0
    _atomic_write_json(STAGED_CACHE, staged)
    print(f"\nStaged cache → {STAGED_CACHE.name} ({len(staged):,} islands)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
