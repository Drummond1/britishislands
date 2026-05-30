#!/usr/bin/env python3
"""
Emit data/islands_index.json — compact first paint for the web app.

Strips long prose, full sources, and image galleries. The browser fetches this
before data/islands.json and merges full records in place (see app.js loadIslands).

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

# Omitted from index; merged later from islands.json / nation shards.
DROP_KEYS = frozenset(
    {
        "history",
        "geography",
        "transport",
        "accommodation",
        "sources",
        "provenance",
        "images",
    }
)


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
    data = json.loads(src.read_text(encoding="utf-8"))
    slim = [slim_record(x) for x in data]
    out.write_text(
        json.dumps(slim, separators=(",", ":"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_shards(data)
    print(
        f"wrote {len(slim)} rows -> {out.name} "
        f"({out.stat().st_size / 1024 / 1024:.2f} MiB); "
        f"full {src.name} {src.stat().st_size / 1024 / 1024:.2f} MiB",
    )


if __name__ == "__main__":
    main()
