#!/usr/bin/env python3
"""
Emit data/islands_index.json — compact first paint for the web app.

Also writes data/islands_unnamed_index.json (lazy-loaded overlay) and
data/shards/*.json nation files for deferred detail merge in app.js.

Run after any change to data/islands.json:
  python3 scripts/build_islands_index.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARD_DIR = ROOT / "data" / "shards"

NATION_SHARD: dict[str, str] = {
    "Scotland": "scotland",
    "Ireland": "ireland",
    "England": "england",
    "Northern Ireland": "northern-ireland",
    "Wales": "wales",
    "Crown Dependency": "crown-dependency",
    "Isle of Man": "isle-of-man",
}

# Omitted from index; merged later from nation shards.
DROP_KEYS = frozenset(
    {
        "history",
        "geography",
        "transport",
        "accommodation",
        "sources",
        "provenance",
        "images",
        "discoveryConfidence",
        "discoverySourceKind",
        "shortDescription",
        "wikipedia",
        "wikidata",
        "aliases",
    }
)


def is_unnamed(island: dict) -> bool:
    if island.get("nameStatus") == "unknown":
        return True
    tags = island.get("tags") or []
    return "unnamed" in tags


def lead_thumb_url(island: dict) -> str | None:
    images = island.get("images") or []
    if images:
        img = images[0]
        return img.get("thumbUrl") or img.get("url") or None
    legacy = island.get("image")
    return legacy if isinstance(legacy, str) and legacy.strip() else None


def slim_record(island: dict) -> dict:
    row = {k: v for k, v in island.items() if k not in DROP_KEYS}
    images = island.get("images") or []
    row["hasImage"] = bool(images or island.get("image"))
    thumb = lead_thumb_url(island)
    if thumb:
        row["thumbUrl"] = thumb
    listings = island.get("propertyListings") or []
    row["hasPropertyListing"] = bool(listings)
    cls = row.get("classification")
    if isinstance(cls, dict):
        row["classification"] = {
            k: cls[k]
            for k in ("source", "confidence")
            if k in cls
        }
    parent = row.get("parentWaterBody")
    if isinstance(parent, dict):
        row["parentWaterBody"] = {
            k: parent[k]
            for k in ("name", "type")
            if parent.get(k)
        }
    return row


def slim_unnamed_stub(island: dict) -> dict:
    parent = island.get("parentWaterBody") or {}
    row = {
        "id": island["id"],
        "name": island.get("name") or "Unnamed island",
        "nameStatus": "unknown",
        "nation": island.get("nation"),
        "type": island.get("type"),
        "subtype": island.get("subtype"),
        "lat": island["lat"],
        "lng": island["lng"],
        "areaKm2": island.get("areaKm2"),
        "osmType": island.get("osmType"),
        "osmId": island.get("osmId"),
        "source": island.get("source"),
        "tags": ["unnamed"],
        "hasImage": False,
        "hasPropertyListing": False,
        "classification": {"confidence": "high", "source": "unnamed-discovery"},
    }
    if parent.get("name") or parent.get("type"):
        row["parentWaterBody"] = {
            "name": parent.get("name") or "",
            "type": parent.get("type") or "",
        }
    return row


def write_shards(data: list[dict]) -> None:
    SHARD_DIR.mkdir(parents=True, exist_ok=True)
    by_slug: dict[str, list[dict]] = {}
    for island in data:
        nation = island.get("nation") or "unknown"
        slug = NATION_SHARD.get(nation, "other")
        by_slug.setdefault(slug, []).append(island)

    manifest_shards: list[dict] = []
    total_bytes = 0
    for slug in sorted(by_slug):
        rows = by_slug[slug]
        fname = f"{slug}.json"
        path = SHARD_DIR / fname
        path.write_text(
            json.dumps(rows, separators=(",", ":"), ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        size = path.stat().st_size
        total_bytes += size
        manifest_shards.append(
            {
                "slug": slug,
                "file": fname,
                "nation": rows[0].get("nation") if rows else slug,
                "count": len(rows),
            }
        )

    manifest = {
        "version": 1,
        "total": len(data),
        "shards": manifest_shards,
    }
    manifest_path = SHARD_DIR / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, separators=(",", ":"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {len(manifest_shards)} nation shards -> {SHARD_DIR.name}/ "
        f"({total_bytes / 1024 / 1024:.2f} MiB); manifest {manifest_path.name}",
    )


def main() -> None:
    src = ROOT / "data" / "islands.json"
    out = ROOT / "data" / "islands_index.json"
    unnamed_out = ROOT / "data" / "islands_unnamed_index.json"
    data = json.loads(src.read_text(encoding="utf-8"))

    main_rows = [slim_record(x) for x in data if not is_unnamed(x)]
    unnamed_rows = [slim_unnamed_stub(x) for x in data if is_unnamed(x)]

    out.write_text(
        json.dumps(main_rows, separators=(",", ":"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    unnamed_out.write_text(
        json.dumps(unnamed_rows, separators=(",", ":"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_shards(data)
    print(
        f"wrote {len(main_rows)} rows -> {out.name} "
        f"({out.stat().st_size / 1024 / 1024:.2f} MiB); "
        f"{len(unnamed_rows)} unnamed -> {unnamed_out.name} "
        f"({unnamed_out.stat().st_size / 1024 / 1024:.2f} MiB); "
        f"full {src.name} {src.stat().st_size / 1024 / 1024:.2f} MiB",
    )


if __name__ == "__main__":
    main()
