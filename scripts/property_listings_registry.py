#!/usr/bin/env python3
"""
Build / update the for-sale island registry and human-readable full list.

Outputs:
  - data/discovery/property_listings_registry.json  (machine-readable + run history)
  - docs/FOR-SALE-ISLANDS.md                        (full list for humans)
  - data/for_sale_islands_summary.json              (slim stub for scripts/UI)

Run after any property sync:
  python3 scripts/property_listings_registry.py --update
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ISLANDS = ROOT / "data" / "islands.json"
VERIFIED = ROOT / "data" / "discovery" / "property_listings_verified.json"
REGISTRY = ROOT / "data" / "discovery" / "property_listings_registry.json"
SUMMARY = ROOT / "data" / "for_sale_islands_summary.json"
DOC = ROOT / "docs" / "FOR-SALE-ISLANDS.md"


def load_registry() -> dict:
    if REGISTRY.is_file():
        return json.loads(REGISTRY.read_text(encoding="utf-8"))
    return {"version": 1, "runs": [], "islands": []}


def island_rows_from_atlas() -> list[dict]:
    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    rows = []
    for isl in islands:
        pl = isl.get("propertyListings") or []
        if not pl:
            continue
        listings = []
        for p in pl:
            listings.append({
                "title": p.get("title", ""),
                "url": p.get("url", ""),
                "listingType": p.get("listingType", ""),
                "priceDisplay": p.get("priceDisplay", ""),
                "source": p.get("source", ""),
                "sourceListingId": p.get("sourceListingId", ""),
            })
        rows.append({
            "islandId": isl["id"],
            "name": isl.get("name", ""),
            "nation": isl.get("nation", ""),
            "areaKm2": isl.get("areaKm2"),
            "lat": isl.get("lat"),
            "lng": isl.get("lng"),
            "listingCount": len(listings),
            "listings": listings,
        })
    rows.sort(key=lambda r: (r.get("nation") or "", r.get("name") or ""))
    return rows


def merge_first_seen(prev: dict, current: list[dict], now: str) -> list[dict]:
    prev_by_id = {r["islandId"]: r for r in prev.get("islands") or []}
    out = []
    for row in current:
        old = prev_by_id.get(row["islandId"], {})
        out.append({
            **row,
            "firstSeenAt": old.get("firstSeenAt") or now,
            "lastSeenAt": now,
        })
    return out


def write_doc(registry: dict) -> None:
    islands = registry.get("islands") or []
    total = len(islands)
    by_nation = Counter(r.get("nation") or "?" for r in islands)
    updated = registry.get("updatedAt", "")
    last_run = (registry.get("runs") or [{}])[-1] if registry.get("runs") else {}

    lines = [
        "# Islands for sale — full list",
        "",
        f"**Last updated:** {updated[:10] if updated else '—'}  ",
        f"**Total islands with listings:** **{total}**  ",
        "",
        "> **Where to look**",
        "> - This page (human-readable table)",
        "> - Machine registry: [`data/discovery/property_listings_registry.json`](../data/discovery/property_listings_registry.json)",
        "> - Research manifest: [`data/discovery/property_listings_verified.json`](../data/discovery/property_listings_verified.json)",
        "> - On the map: filter **For sale** at [findmyisland.com](https://www.findmyisland.com)",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|------:|",
        f"| Islands on map | {total} |",
    ]
    for nation, n in sorted(by_nation.items()):
        lines.append(f"| {nation} | {n} |")
    if last_run:
        lines.extend([
            "",
            f"**Last discovery run:** {last_run.get('runAt', '—')[:19]}  ",
            f"**Added that run:** {last_run.get('addedCount', 0)}  ",
            f"**Removed that run:** {last_run.get('removedCount', 0)}  ",
        ])
    lines.extend([
        "",
        "## All islands (A–Z by nation)",
        "",
        "| Island | Nation | Type | Price | Listing |",
        "|--------|--------|------|-------|---------|",
    ])
    for r in islands:
        li = (r.get("listings") or [{}])[0]
        ltype = li.get("listingType", "")
        price = (li.get("priceDisplay") or "—").replace("|", "/")
        title = (li.get("title") or "View listing").replace("|", "/")
        url = li.get("url", "")
        link = f"[{title[:48]}]({url})" if url else title[:48]
        lines.append(
            f"| {r.get('name', '')} | {r.get('nation', '')} | {ltype} | {price} | {link} |"
        )
    lines.extend([
        "",
        "---",
        "",
        "Regenerate: `python3 scripts/property_listings_registry.py --update`",
        "",
    ])
    DOC.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_summary(registry: dict) -> None:
    islands = registry.get("islands") or []
    SUMMARY.write_text(
        json.dumps(
            {
                "updatedAt": registry.get("updatedAt"),
                "total": len(islands),
                "islandIds": [r["islandId"] for r in islands],
                "names": [r["name"] for r in islands],
                "doc": "docs/FOR-SALE-ISLANDS.md",
                "registry": "data/discovery/property_listings_registry.json",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--update", action="store_true", help="Rebuild registry from islands.json")
    ap.add_argument(
        "--record-run",
        metavar="JSON",
        help='Append run stats, e.g. \'{"source":"tier4","addedIslandIds":[]}\'',
    )
    ap.add_argument("--print", action="store_true", help="Print summary to stdout")
    args = ap.parse_args()

    if not args.update and not args.record_run and not args.print:
        ap.print_help()
        return 0

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    prev = load_registry()
    current = island_rows_from_atlas()
    current_ids = {r["islandId"] for r in current}
    prev_ids = {r["islandId"] for r in prev.get("islands") or []}

    added_ids = sorted(current_ids - prev_ids)
    removed_ids = sorted(prev_ids - current_ids)

    registry = {
        "version": 1,
        "updatedAt": now,
        "totalIslandsWithListings": len(current),
        "verifiedManifest": str(VERIFIED.relative_to(ROOT)),
        "humanDoc": str(DOC.relative_to(ROOT)),
        "islands": merge_first_seen(prev, current, now),
        "runs": list(prev.get("runs") or []),
    }

    if args.record_run:
        extra = json.loads(args.record_run)
        registry["runs"].append({
            "runAt": now,
            "addedCount": len(added_ids),
            "removedCount": len(removed_ids),
            "addedIslandIds": added_ids,
            "removedIslandIds": removed_ids,
            **extra,
        })
    elif args.update and (added_ids or removed_ids or not registry["runs"]):
        registry["runs"].append({
            "runAt": now,
            "source": "registry_sync",
            "addedCount": len(added_ids),
            "removedCount": len(removed_ids),
            "addedIslandIds": added_ids,
            "removedIslandIds": removed_ids,
        })

    REGISTRY.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_doc(registry)
    write_summary(registry)

    if args.print or args.update:
        print(f"Registry: {len(current)} islands → {REGISTRY}")
        print(f"Full list: {DOC}")
        if added_ids:
            print(f"  +{len(added_ids)} new:", ", ".join(added_ids[:8]), "…" if len(added_ids) > 8 else "")
        if removed_ids:
            print(f"  -{len(removed_ids)} removed")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
