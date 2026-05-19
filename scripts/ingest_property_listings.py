#!/usr/bin/env python3
"""
Match property-for-sale listings to atlas islands.

Sources (see scripts/discover_property_apis.py):
  - curated: data/curated_property_listings.json (maintainer links)
  - homedata: optional API (HOMEDATA_API_KEY); cache in data/cache_homedata_listings.json

Writes ``data/cache_property_listings.json`` keyed by island id for apply_enrichments.py.

CLI::

    python3 scripts/ingest_property_listings.py --source all --commit
    python3 scripts/ingest_property_listings.py --source curated --commit
    python3 scripts/ingest_property_listings.py --source homedata --fetch --cache --commit
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import pickle
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from shapely.geometry import Point, Polygon
    from shapely.prepared import prep
    from shapely.strtree import STRtree
except ImportError:
    sys.exit("shapely is required: pip install shapely")

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import ingest_lighthouses as _il  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS_PATH = DATA / "islands.json"
CURATED_PATH = DATA / "curated_property_listings.json"
HOMEDATA_CACHE = DATA / "cache_homedata_listings.json"
STAGED_CACHE = DATA / "cache_property_listings.json"
REPORT = DATA / "property_listings_ingestion_report.json"
LAND_PICKLE = DATA / "land_polygons.pickle"
OSM_GEOM_CACHE = DATA / "cache_osm_geometries.json"

UK_BBOX = (49.0, -11.5, 61.5, 2.5)
OFFSHORE_MAX_M = 200.0
USER_AGENT = "isles-of-britain/0.8 (ingest_property_listings; static-site)"

ISLAND_KEYWORDS_RE = re.compile(
    r"\b(island|isle|islets?|eilean|inch|inis|ynys|eyot)\b",
    re.I,
)
WHOLE_ISLAND_RE = re.compile(
    r"\b(whole\s+island|private\s+island|island\s+estate|island\s+for\s+sale)\b",
    re.I,
)


@dataclass
class RawListing:
    source: str
    source_listing_id: str
    title: str
    url: str
    lat: float | None = None
    lng: float | None = None
    island_id: str | None = None
    price_gbp: int | None = None
    price_display: str | None = None
    description: str = ""
    notes: str = ""


def _atomic_write_json(path: Path, payload: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _load_dotenv_local() -> None:
    path = ROOT / ".env.local"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def listing_id(source: str, source_listing_id: str) -> str:
    h = hashlib.sha256(f"{source}:{source_listing_id}".encode()).hexdigest()
    return h[:16]


def classify_listing_type(title: str, description: str = "") -> str:
    text = f"{title} {description}"
    if WHOLE_ISLAND_RE.search(text):
        return "whole_island"
    if re.search(r"\b(croft|house|cottage|flat|apartment|bungalow)\b", text, re.I):
        return "residential"
    if re.search(r"\b(land|plot|acre|hectare|farm)\b", text, re.I):
        return "land"
    return "residential"


def fetch_curated_listings() -> list[RawListing]:
    data = _load_json(CURATED_PATH, {})
    rows = data.get("listings") if isinstance(data, dict) else []
    out: list[RawListing] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        iid = (row.get("islandId") or "").strip()
        url = (row.get("url") or "").strip()
        title = (row.get("title") or "").strip()
        sid = (row.get("sourceListingId") or f"curated-{iid}").strip()
        if not iid or not url or not title:
            continue
        out.append(
            RawListing(
                source=(row.get("source") or "curated").strip(),
                source_listing_id=sid,
                title=title,
                url=url,
                island_id=iid,
                lat=row.get("lat"),
                lng=row.get("lng"),
                price_gbp=row.get("priceGBP"),
                price_display=row.get("priceDisplay"),
                description=(row.get("description") or "")[:500],
                notes=(row.get("notes") or "")[:300],
            )
        )
    return out


def _normalize_homedata_item(item: dict) -> RawListing | None:
    """Best-effort normalisation of Homedata live-listings JSON objects."""
    lid = str(item.get("id") or item.get("listing_id") or item.get("uprn") or "")
    if not lid:
        return None
    title = (
        item.get("title")
        or item.get("headline")
        or item.get("property_type")
        or "Property listing"
    )
    url = item.get("url") or item.get("listing_url") or item.get("portal_url") or ""
    if not url and item.get("source_url"):
        url = item["source_url"]
    if not str(url).startswith("http"):
        url = ""
    lat = item.get("lat") or item.get("latitude")
    lng = item.get("lng") or item.get("longitude")
    try:
        lat_f = float(lat) if lat is not None else None
        lng_f = float(lng) if lng is not None else None
    except (TypeError, ValueError):
        lat_f = lng_f = None
    price = item.get("price") or item.get("price_gbp")
    price_gbp = None
    price_display = None
    if isinstance(price, (int, float)):
        price_gbp = int(price)
    elif isinstance(price, str):
        price_display = price.strip()[:40]
    desc = str(item.get("description") or item.get("summary") or "")[:500]
    return RawListing(
        source="homedata",
        source_listing_id=lid,
        title=str(title)[:200],
        url=str(url)[:500] if url else "",
        lat=lat_f,
        lng=lng_f,
        price_gbp=price_gbp,
        price_display=price_display,
        description=desc,
    )


def fetch_homedata_listings(*, use_cache: bool, do_fetch: bool) -> list[RawListing]:
    _load_dotenv_local()
    api_key = os.environ.get("HOMEDATA_API_KEY", "").strip()
    cache = _load_json(HOMEDATA_CACHE, {"listings": [], "meta": {}})

    if use_cache and cache.get("listings"):
        print(f"  homedata: {len(cache['listings']):,} cached raw items", flush=True)
    elif do_fetch and api_key:
        s, w, n, e = UK_BBOX
        # Documented pattern; adjust query params when Homedata key is available.
        base = os.environ.get("HOMEDATA_API_BASE", "https://api.homedata.co.uk/v1").rstrip("/")
        q = urllib.parse.urlencode(
            {
                "south": s,
                "west": w,
                "north": n,
                "east": e,
                "limit": 100,
            }
        )
        url = f"{base}/listings/live?{q}"
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {api_key}", "User-Agent": USER_AGENT},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            items = payload.get("data") or payload.get("listings") or payload.get("results") or []
            if isinstance(items, dict):
                items = items.get("items") or []
            cache["listings"] = items if isinstance(items, list) else []
            cache["meta"] = {
                "fetchedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "url": base + "/listings/live",
            }
            _atomic_write_json(HOMEDATA_CACHE, cache)
            print(f"  homedata: fetched {len(cache['listings']):,} items", flush=True)
            time.sleep(1.0)
        except urllib.error.HTTPError as exc:
            print(f"  homedata: HTTP {exc.code} — using cache only", flush=True)
        except OSError as exc:
            print(f"  homedata: {exc}", flush=True)
    elif do_fetch and not api_key:
        print("  homedata: HOMEDATA_API_KEY not set — skip fetch", flush=True)

    out: list[RawListing] = []
    for item in cache.get("listings") or []:
        if not isinstance(item, dict):
            continue
        norm = _normalize_homedata_item(item)
        if norm and norm.url:
            out.append(norm)
    return out


def _norm_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def match_by_name(listing: RawListing, islands: list[dict]) -> tuple[str | None, str]:
    title = _norm_name(listing.title)
    if not title or not ISLAND_KEYWORDS_RE.search(listing.title + " " + listing.description):
        return None, "low"
    best: tuple[float, str] | None = None
    for isl in islands:
        name = _norm_name(isl.get("name") or "")
        if len(name) < 4 or name not in title:
            continue
        score = len(name)
        if best is None or score > best[0]:
            best = (score, isl["id"])
    if best and best[0] >= 5:
        conf = "medium" if ISLAND_KEYWORDS_RE.search(listing.title) else "low"
        return best[1], conf
    return None, "low"


def build_island_spatial_index(
    islands: list[dict],
    geom_cache: dict,
    land_polys: list[Polygon],
    land_tree: STRtree | None,
) -> tuple[list[dict], list[Polygon | Any], STRtree | None, list[Any]]:
    indexed: list[dict] = []
    polys: list[Any] = []
    for isl in islands:
        poly = _il.polygon_for_island(isl, geom_cache, land_polys, land_tree)
        if poly is None:
            continue
        indexed.append(isl)
        polys.append(poly)
    tree = STRtree(polys) if polys else None
    prepped = [prep(p) for p in polys]
    return indexed, polys, tree, prepped


def match_by_geometry(
    listing: RawListing,
    indexed: list[dict],
    polys: list[Any],
    tree: STRtree | None,
    prepped: list[Any],
) -> tuple[str | None, str, str, bool]:
    if listing.lat is None or listing.lng is None or tree is None:
        return None, "low", "none", False
    pt = Point(listing.lng, listing.lat)
    try:
        cand_idx = tree.query(pt.buffer(0.003), predicate="intersects")
    except Exception:
        cand_idx = []
    lat_mid = listing.lat
    deg_per_m = max(1.0 / 111_111.0, 1.0 / (111_111.0 * max(0.1, math.cos(math.radians(lat_mid)))))
    cutoff_deg = OFFSHORE_MAX_M * deg_per_m
    for idx in cand_idx:
        ii = int(idx)
        poly = polys[ii]
        isl = indexed[ii]
        pprep = prepped[ii]
        if pprep.contains(pt):
            return isl["id"], "high", "polygon", False
        try:
            dist = poly.distance(pt)
        except Exception:
            continue
        if dist <= cutoff_deg:
            return isl["id"], "medium", "proximity", True
    return None, "low", "none", False


def raw_to_public(
    raw: RawListing,
    *,
    island_id: str,
    matched_method: str,
    matched_confidence: str,
    offshore: bool,
) -> dict:
    ltype = classify_listing_type(raw.title, raw.description)
    if raw.island_id and raw.source == "curated":
        row = _load_json(CURATED_PATH, {})
        for c in row.get("listings") or []:
            if c.get("islandId") == island_id and c.get("listingType"):
                ltype = c["listingType"]
                break
    rec = {
        "id": listing_id(raw.source, raw.source_listing_id),
        "listingType": ltype,
        "status": "for_sale",
        "title": raw.title[:200],
        "url": raw.url,
        "source": raw.source,
        "sourceListingId": raw.source_listing_id,
        "priceGBP": raw.price_gbp,
        "priceDisplay": raw.price_display or (f"£{raw.price_gbp:,}" if raw.price_gbp else "POA"),
        "matchedMethod": matched_method,
        "matchedConfidence": matched_confidence,
    }
    if offshore:
        rec["offshore"] = True
    if raw.notes and matched_confidence == "low":
        rec["reviewNote"] = raw.notes[:200]
    return rec


def merge_staged(
    islands: list[dict],
    raw_listings: list[RawListing],
    *,
    geom_cache: dict,
    land_polys: list[Polygon],
    land_tree: STRtree | None,
) -> tuple[dict[str, dict], dict]:
    indexed, polys, tree, prepped = build_island_spatial_index(
        islands, geom_cache, land_polys, land_tree,
    )
    by_island: dict[str, list[dict]] = {}
    stats = {
        "raw": len(raw_listings),
        "matched": 0,
        "unmatched": 0,
        "lowConfidence": 0,
    }
    unmatched_audit: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for raw in raw_listings:
        island_id = raw.island_id
        method = "curated"
        confidence = "high"
        offshore = False

        if island_id:
            isl = next((i for i in islands if i.get("id") == island_id), None)
            if not isl:
                stats["unmatched"] += 1
                unmatched_audit.append({"title": raw.title, "reason": "unknown_island_id"})
                continue
        else:
            island_id, confidence, method, offshore = match_by_geometry(
                raw, indexed, polys, tree, prepped,
            )
            if not island_id:
                island_id, confidence = match_by_name(raw, islands)
                method = "name"
            if not island_id:
                stats["unmatched"] += 1
                if len(unmatched_audit) < 100:
                    unmatched_audit.append(
                        {"title": raw.title, "source": raw.source, "reason": "no_match"},
                    )
                continue

        key = (island_id, listing_id(raw.source, raw.source_listing_id))
        if key in seen:
            continue
        seen.add(key)

        if confidence == "low":
            stats["lowConfidence"] += 1

        pub = raw_to_public(
            raw,
            island_id=island_id,
            matched_method=method,
            matched_confidence=confidence,
            offshore=offshore,
        )
        by_island.setdefault(island_id, []).append(pub)
        stats["matched"] += 1

    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    sources_used = sorted({r.source for r in raw_listings})
    staged: dict[str, dict] = {}
    for iid, listings in by_island.items():
        staged[iid] = {
            "propertyListings": listings,
            "propertyListingsSource": "+".join(sources_used) or "none",
            "propertyListingsConfidence": (
                "high" if all(x["matchedConfidence"] == "high" for x in listings)
                else "medium"
            ),
            "propertyListingsAttribution": (
                "Outbound links to third-party estate agents and brokers; "
                "not scraped from Rightmove or Zoopla. Verify status on the source site."
            ),
            "propertyListingsFetchedAt": fetched_at,
        }

    return staged, {**stats, "unmatchedAudit": unmatched_audit, "islandsWithListings": len(staged)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--source",
        choices=("curated", "homedata", "all"),
        default="all",
    )
    ap.add_argument("--fetch", action="store_true", help="Fetch homedata (if key set)")
    ap.add_argument("--cache", action="store_true", help="Use homedata cache file")
    ap.add_argument("--commit", action="store_true", help="Write cache_property_listings.json")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    islands = _load_json(ISLANDS_PATH, [])
    if not isinstance(islands, list):
        sys.exit("islands.json must be a list")

    raw: list[RawListing] = []
    if args.source in ("curated", "all"):
        curated = fetch_curated_listings()
        print(f"  curated: {len(curated):,} listings", flush=True)
        raw.extend(curated)
    if args.source in ("homedata", "all"):
        hd = fetch_homedata_listings(use_cache=args.cache or not args.fetch, do_fetch=args.fetch)
        print(f"  homedata: {len(hd):,} normalised listings", flush=True)
        raw.extend(hd)

    geom_cache = _load_json(OSM_GEOM_CACHE, {})
    land_polys: list[Polygon] = []
    land_tree = None
    land_polys = []
    if LAND_PICKLE.is_file():
        try:
            land = pickle.load(open(LAND_PICKLE, "rb"))
            land_polys = list(getattr(land, "geoms", [land]))
        except Exception as exc:
            print(f"  WARN: land_polygons.pickle: {exc}", flush=True)
    land_tree = STRtree(land_polys) if land_polys else None

    staged, stats = merge_staged(
        islands, raw, geom_cache=geom_cache, land_polys=land_polys, land_tree=land_tree,
    )

    report = {
        "startedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": args.source,
        "dryRun": args.dry_run or not args.commit,
        **stats,
    }
    _atomic_write_json(REPORT, report)
    print(f"\nMatched {stats['matched']:,} listings → {stats['islandsWithListings']:,} islands")
    print(f"Unmatched: {stats['unmatched']:,}; low confidence: {stats['lowConfidence']:,}")
    print(f"Report → {REPORT.name}")

    if args.dry_run or not args.commit:
        print("\nDRY RUN — cache_property_listings.json not written")
        return 0

    _atomic_write_json(STAGED_CACHE, staged)
    print(f"\nStaged → {STAGED_CACHE.name} ({len(staged):,} islands)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
