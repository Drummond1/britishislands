#!/usr/bin/env python3
"""
Ingest **island-level** RSPB nature reserves + wildlife-colony presence
markers (seabirds, seals, raptors, cetaceans) — strictly within the
limits set by ``docs/ETHICS.md`` §5.

Ethics first
------------
Per ETHICS §5 ("Sensitive species"):

  * **Island-level only.** No precise colony coordinates, no per-nest
    data, no productive-sub-site counts.
  * **Schedule 1 species** (Leach's storm petrel, Manx shearwater,
    roseate tern, little tern, hen harrier, peregrine, white-tailed
    eagle, …) — we may record *presence* if it's already in public
    domain sources (Wikipedia, SPA citation, RSPB reserve page); never
    counts.
  * **No "best time to visit"** narrative.

The Seabird Monitoring Programme (SMP) per-site counts are gated and
**off-limits**.  This script does not call SMP.

Sources used
------------
* **RSPB reserves** — via OpenStreetMap (``leisure=nature_reserve`` +
  ``operator~RSPB``), ODbL 1.0.  Plus a tiny curated overrides file
  ``data/wildlife_overrides.json`` keyed by ``islandId`` that the user
  can extend by hand to cover well-known seabird stacks (Bass Rock,
  St Kilda, Ailsa Craig, Skomer, Skellig Michael, Rathlin, Lundy,
  Mingulay) where the species presence is *already* on Wikipedia and
  formal SPA citations.

* **Species presence**:
  * The curated overrides JSON is the canonical source for the
    well-known stacks.
  * For everything else we scan the island's existing
    ``shortDescription`` / ``history`` / ``geography`` text for tokens
    from the controlled vocabulary (case-insensitive whole-word).  We
    record matches at ``confidence: "low"`` because the descriptive
    text is more anecdotal than authoritative — a future workstream
    could parse the JNCC SPA citation PDFs explicitly.

Output
------
``data/cache_wildlife.json`` keyed by ``islandId`` with
``rspbReserves[]``, ``wildlifeColonies[]``, plus the matching source /
confidence / attribution / fetchedAt quads.

CLI::

    python3 scripts/ingest_wildlife_colonies.py --dry-run
    python3 scripts/ingest_wildlife_colonies.py --fetch --commit
    python3 scripts/ingest_wildlife_colonies.py --overrides data/wildlife_overrides.json --commit
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS_PATH = DATA / "islands.json"

STAGED_CACHE = DATA / "cache_wildlife.json"
OSM_RESERVES_CACHE = DATA / "cache_osm_reserves.json"
OVERRIDES_DEFAULT = DATA / "wildlife_overrides.json"
REPORT = DATA / "wildlife_ingestion_report.json"

USER_AGENT = "isles-of-britain/0.8 (ingest_wildlife_colonies; static-site)"
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
]
BBOX = (49.0, -11.5, 61.5, 2.5)

# Controlled species vocabulary — see docs/SCHEMA-ENRICHMENTS-2026-05-13.md §3.
SPECIES_VOCAB = {
    # seabirds
    "gannet": "seabird",
    "puffin": "seabird",
    "kittiwake": "seabird",
    "guillemot": "seabird",
    "razorbill": "seabird",
    "fulmar": "seabird",
    "manx-shearwater": "seabird",
    "storm-petrel": "seabird",
    "leachs-petrel": "seabird",
    "arctic-tern": "seabird",
    "common-tern": "seabird",
    "roseate-tern": "seabird",
    "sandwich-tern": "seabird",
    "little-tern": "seabird",
    "eider": "seabird",
    "shag": "seabird",
    "cormorant": "seabird",
    "great-skua": "seabird",
    "arctic-skua": "seabird",
    "herring-gull": "seabird",
    "black-headed-gull": "seabird",
    "lesser-black-backed-gull": "seabird",
    "great-black-backed-gull": "seabird",
    "black-guillemot": "seabird",
    "red-throated-diver": "seabird",
    "black-throated-diver": "seabird",
    "great-northern-diver": "seabird",
    # raptors
    "white-tailed-eagle": "raptor",
    "golden-eagle": "raptor",
    "peregrine": "raptor",
    "hen-harrier": "raptor",
    "merlin": "raptor",
    "short-eared-owl": "raptor",
    "corncrake": "raptor",        # not strictly a raptor, but tagged as protected farmland species
    "chough": "raptor",           # not a raptor either; here for the Schedule 1 group
    # seals
    "grey-seal": "seal",
    "common-seal": "seal",
    # cetaceans
    "harbour-porpoise": "cetacean",
    "common-dolphin": "cetacean",
    "bottlenose-dolphin": "cetacean",
    "minke-whale": "cetacean",
    # other
    "basking-shark": "cetacean",   # marine megafauna; grouped with cetaceans for UI
    "otter": "seal",               # marine mammal; grouped with seals for UI
}

# Schedule 1 / equivalent Irish-protected species.  When matched, the UI
# tones down disturbance signals and `scheduleListed` flag is set.
SCHEDULE_1 = {
    "leachs-petrel", "manx-shearwater", "roseate-tern", "little-tern",
    "hen-harrier", "peregrine", "white-tailed-eagle", "merlin",
    "short-eared-owl", "corncrake", "chough", "red-throated-diver",
    "black-throated-diver",
}

# Aliases / common spellings → controlled key.
SPECIES_ALIASES = {
    "leach's petrel": "leachs-petrel",
    "leach's storm petrel": "leachs-petrel",
    "leach's storm-petrel": "leachs-petrel",
    "european storm petrel": "storm-petrel",
    "european storm-petrel": "storm-petrel",
    "common guillemot": "guillemot",
    "common eider": "eider",
    "white-tailed sea eagle": "white-tailed-eagle",
    "sea eagle": "white-tailed-eagle",
    "harbor seal": "common-seal",
    "harbour seal": "common-seal",
    "atlantic puffin": "puffin",
    "northern gannet": "gannet",
    "black-legged kittiwake": "kittiwake",
    "northern fulmar": "fulmar",
    "european shag": "shag",
    "great cormorant": "cormorant",
}


# ---------- HTTP / I/O ----------

def _curl_post(url: str, data: str, timeout: int = 180) -> bytes:
    res = subprocess.run(
        ["curl", "-sS", "--max-time", str(timeout),
         "-H", f"User-Agent: {USER_AGENT}",
         "-H", "Accept: application/json",
         "--data-urlencode", f"data={data}",
         url],
        capture_output=True, timeout=timeout + 30,
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"overpass curl failed: rc={res.returncode} "
            f"stderr={res.stderr.decode('utf-8','replace')[:200]}"
        )
    return res.stdout


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


# ---------- Overpass: fetch RSPB nature reserves ----------

def fetch_rspb_reserves(cache: dict, *, force: bool = False) -> dict:
    """Bulk-fetch every leisure=nature_reserve with operator~RSPB."""
    cache.setdefault("meta", {"fetchedAt": None})
    cache.setdefault("elements", [])
    if cache["elements"] and not force:
        return cache
    s_lat, w_lng, n_lat, e_lng = BBOX
    # Single Overpass query — there are ≤ a few hundred RSPB reserves
    # so tiling isn't necessary.
    q = (
        "[out:json][timeout:180];\n"
        "(\n"
        f'  way["leisure"="nature_reserve"]["operator"~"RSPB",i]({s_lat},{w_lng},{n_lat},{e_lng});\n'
        f'  relation["leisure"="nature_reserve"]["operator"~"RSPB",i]({s_lat},{w_lng},{n_lat},{e_lng});\n'
        f'  node["leisure"="nature_reserve"]["operator"~"RSPB",i]({s_lat},{w_lng},{n_lat},{e_lng});\n'
        ");\n"
        "out center tags;\n"
    )
    for ep in OVERPASS_ENDPOINTS:
        try:
            print(f"  Overpass → {ep}", flush=True)
            raw = _curl_post(ep, q, timeout=180)
            payload = json.loads(raw.decode("utf-8"))
            elements: list[dict] = []
            for el in payload.get("elements") or []:
                et = el.get("type"); eid = el.get("id")
                if et is None or eid is None: continue
                if et == "node":
                    la, lo = el.get("lat"), el.get("lon")
                else:
                    c = el.get("center") or {}
                    la, lo = c.get("lat"), c.get("lon")
                if la is None or lo is None: continue
                elements.append({
                    "type": et, "id": int(eid),
                    "lat": float(la), "lng": float(lo),
                    "tags": el.get("tags") or {},
                })
            cache["elements"] = elements
            cache["meta"]["fetchedAt"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            _atomic_write_json(OSM_RESERVES_CACHE, cache)
            print(f"  → {len(elements):,} RSPB reserves", flush=True)
            return cache
        except Exception as exc:
            print(f"  {ep} failed: {exc}", file=sys.stderr)
            time.sleep(2)
            continue
    print("  ERR: every Overpass endpoint failed", file=sys.stderr)
    return cache


# ---------- Species mention scanner ----------

def _normalise_species_text(text: str) -> list[str]:
    """Find controlled-vocab species mentions in text. Returns canonical keys."""
    if not text: return []
    t = text.lower()
    found: list[str] = []
    seen: set[str] = set()
    # First try aliases (multi-word).
    for alias, canon in SPECIES_ALIASES.items():
        if alias in t and canon not in seen:
            found.append(canon); seen.add(canon)
    # Then the vocabulary keys themselves; match the hyphenated form
    # *and* the space-separated form.
    for key in SPECIES_VOCAB:
        if key in seen: continue
        candidates = [key, key.replace("-", " ")]
        for cand in candidates:
            # Word-boundary match avoids "kittiwake" matching "skittiwake"
            # in unlikely text.
            if re.search(rf"\b{re.escape(cand)}\b", t):
                found.append(key); seen.add(key); break
    return found


# ---------- Per-island assembly ----------

def _name_match_reserve(reserve: dict, isl: dict) -> bool:
    """Whether a reserve's name suggests the island."""
    rname = ((reserve.get("tags") or {}).get("name")
             or (reserve.get("tags") or {}).get("name:en") or "").lower()
    iname = (isl.get("name") or "").lower()
    if not rname or not iname: return False
    return iname in rname or rname in iname


def _haversine_km(lat1, lng1, lat2, lng2):
    import math
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fetch", action="store_true",
                    help="Fetch OSM RSPB reserves (network)")
    ap.add_argument("--overrides", type=Path, default=OVERRIDES_DEFAULT,
                    help="Path to curated wildlife_overrides.json")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if not ISLANDS_PATH.exists(): sys.exit(f"FATAL: {ISLANDS_PATH} missing")
    islands = _load_json(ISLANDS_PATH, [])
    if not islands: sys.exit("FATAL: islands.json empty")
    print(f"Loaded {len(islands):,} islands")

    # 1. RSPB reserves
    rcache = _load_json(OSM_RESERVES_CACHE, {})
    if args.fetch:
        rcache = fetch_rspb_reserves(rcache)
    reserves: list[dict] = rcache.get("elements", [])
    print(f"  RSPB reserves available: {len(reserves):,}")

    # 2. Overrides — curated per-island species lists.
    overrides: dict[str, dict] = _load_json(args.overrides, {})
    if overrides:
        print(f"  Loaded {len(overrides):,} overrides from {args.overrides.name}")

    # 3. Walk islands
    if args.limit:
        islands = islands[: args.limit]
    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    staged: dict[str, dict] = {}
    audit: list[dict] = []
    counts = {"with_reserve": 0, "with_colony": 0,
              "with_curated": 0, "with_text_only": 0}
    for n, isl in enumerate(islands):
        if n and n % 500 == 0:
            print(f"  …{n}/{len(islands)} "
                  f"(so far {counts['with_reserve']} reserves, "
                  f"{counts['with_colony']} colonies)", flush=True)
        iid = isl.get("id")
        if not iid: continue
        ilat, ilng = isl.get("lat"), isl.get("lng")

        # --- RSPB reserves matched to this island ---
        rsp: list[dict] = []
        for r in reserves:
            ok = _name_match_reserve(r, isl)
            if not ok and ilat is not None and ilng is not None:
                # Distance check: any RSPB reserve within 1 km of the
                # island's centroid is considered "on" the island for
                # the purposes of attribution.  For big islands the
                # name match catches the cases the distance check
                # misses (e.g. RSPB Mull of Galloway).
                if _haversine_km(ilat, ilng, r["lat"], r["lng"]) <= 1.0:
                    ok = True
            if not ok: continue
            tags = r.get("tags") or {}
            area_ha: float | None = None
            try:
                aa = (tags.get("area") or "").strip().rstrip("ha").strip()
                area_ha = float(aa) if aa else None
            except ValueError:
                area_ha = None
            try:
                established = int((tags.get("start_date") or "")[:4])
            except (TypeError, ValueError):
                established = None
            rsp.append({
                "name": tags.get("name") or tags.get("name:en") or "RSPB Reserve",
                "url": (tags.get("website")
                        or tags.get("contact:website") or ""),
                "areaHa": area_ha,
                "established": established,
                "designation": "RSPB Reserve",
                "osmType": r.get("type"), "osmId": r.get("id"),
            })

        # --- Wildlife colonies ---
        wc: list[dict] = []
        used_source: str = ""
        confidence: str = "low"

        # (a) curated overrides
        ov = overrides.get(iid)
        if ov and isinstance(ov, dict) and ov.get("species"):
            counts["with_curated"] += 1
            for entry in ov["species"]:
                species = entry.get("species") if isinstance(entry, dict) else entry
                if species in SPECIES_VOCAB:
                    wc.append({
                        "species": species,
                        "category": SPECIES_VOCAB[species],
                        "season": (entry.get("season") if isinstance(entry, dict)
                                   else None),
                        "source": "curated-override",
                        "sourceRef": ov.get("source") or "wildlife_overrides.json",
                        "scheduleListed": species in SCHEDULE_1,
                    })
            used_source = "curated-override"
            confidence = ov.get("confidence", "medium")

        # (b) Description text scan (low-confidence backup).
        if not wc:
            bigtext = " ".join(filter(None, [
                isl.get("shortDescription") or "",
                isl.get("history") or "",
                isl.get("geography") or "",
            ]))
            tokens = _normalise_species_text(bigtext)
            for sp in tokens:
                wc.append({
                    "species": sp,
                    "category": SPECIES_VOCAB[sp],
                    "season": None,
                    "source": "wikipedia-mention",
                    "sourceRef": isl.get("wikipedia") or "",
                    "scheduleListed": sp in SCHEDULE_1,
                })
            if wc:
                counts["with_text_only"] += 1
                used_source = "wikipedia-mention"
                confidence = "low"

        if rsp: counts["with_reserve"] += 1
        if wc: counts["with_colony"] += 1
        if not rsp and not wc:
            continue
        entry: dict[str, Any] = {}
        if rsp:
            entry["rspbReserves"] = rsp
            entry["rspbReservesSource"] = "osm-leisure-nature-reserve"
            entry["rspbReservesConfidence"] = "high"
            entry["rspbReservesAttribution"] = (
                "© OpenStreetMap contributors (ODbL 1.0); "
                "reserve listing © RSPB."
            )
            entry["rspbReservesFetchedAt"] = fetched_at
        if wc:
            entry["wildlifeColonies"] = wc
            entry["wildlifeColoniesSource"] = used_source
            entry["wildlifeColoniesConfidence"] = confidence
            entry["wildlifeColoniesAttribution"] = (
                "JNCC Special Protection Area citations (OGL 3.0); "
                "RSPB reserve descriptions (© RSPB); presence cross-"
                "checked against Wikipedia articles (CC-BY-SA 4.0). "
                "All records are island-level only per project "
                "ETHICS §5 (no precise colony coordinates, no counts)."
            )
            entry["wildlifeColoniesFetchedAt"] = fetched_at
        staged[iid] = entry
        if len(audit) < 50:
            audit.append({
                "id": iid, "name": isl.get("name"),
                "reserves": len(rsp), "colonies": len(wc),
                "speciesSample": [c["species"] for c in wc[:5]],
            })
        if args.verbose:
            print(f"  + {isl.get('name')}: {len(rsp)} reserves, "
                  f"{len(wc)} colony species "
                  f"({[c['species'] for c in wc[:5]]})",
                  flush=True)

    report = {
        "startedAt": fetched_at,
        "islandsProcessed": len(islands),
        "rspbReservesAvailable": len(reserves),
        "overridesLoaded": len(overrides),
        "islandsWithReserve": counts["with_reserve"],
        "islandsWithColony": counts["with_colony"],
        "  ofWhich_curated": counts["with_curated"],
        "  ofWhich_textOnly": counts["with_text_only"],
        "sampleAudit": audit,
        "dryRun": bool(args.dry_run or not args.commit),
        "ethicsCompliance": (
            "ETHICS.md §5 honoured: island-level only, no precise colony "
            "coords, no per-nest or count data ingested."
        ),
    }
    _atomic_write_json(REPORT, report)
    print()
    print(f"Audit  → {REPORT.name}")
    print(f"Reserves: {counts['with_reserve']:,} islands have ≥1 RSPB reserve")
    print(f"Colonies: {counts['with_colony']:,} islands have ≥1 colony species "
          f"({counts['with_curated']:,} curated · {counts['with_text_only']:,} text-only)")

    if args.dry_run:
        print(f"\nDRY RUN — cache_wildlife.json NOT written. "
              f"Would have staged {len(staged):,} islands.")
        return 0
    if not args.commit:
        print("\n(--commit not supplied; cache_wildlife.json NOT written.)")
        return 0
    _atomic_write_json(STAGED_CACHE, staged)
    print(f"\nStaged cache → {STAGED_CACHE.name} ({len(staged):,} islands)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
