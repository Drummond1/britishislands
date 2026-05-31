#!/usr/bin/env python3
"""
Emit compact atlas index files for fast first paint.

Outputs:
  data/islands_index.json       — v2 compact stubs (~1 MiB) for map + list
  data/islands_unnamed_index.json — lazy overlay for unnamed landmasses
  data/shards/*.json            — full records merged on demand per nation

Run after any change to data/islands.json:
  python3 scripts/build_islands_index.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARD_DIR = ROOT / "data" / "shards"
INDEX_VERSION = 2

NATION_SHARD: dict[str, str] = {
    "Scotland": "scotland",
    "Ireland": "ireland",
    "England": "england",
    "Northern Ireland": "northern-ireland",
    "Wales": "wales",
    "Crown Dependency": "crown-dependency",
    "Isle of Man": "isle-of-man",
}


def is_unnamed(island: dict) -> bool:
    if island.get("nameStatus") == "unknown":
        return True
    return "unnamed" in (island.get("tags") or [])


def compact_stub(island: dict) -> dict:
    """Minimal fields for map markers, list, filters, and search."""
    row: dict = {
        "id": island["id"],
        "n": island.get("name") or "Unnamed island",
        "y": round(float(island["lat"]), 4),
        "x": round(float(island["lng"]), 4),
        "t": island.get("type") or "sea",
        "o": island.get("nation") or "",
    }
    area = island.get("areaKm2")
    if area:
        row["a"] = round(float(area), 3)
    arch = (island.get("archipelago") or "").strip()
    if arch:
        row["g"] = arch
    subtype = island.get("subtype")
    if subtype:
        row["s"] = subtype
    pop = island.get("population")
    if pop is not None:
        row["p"] = pop
    hp = island.get("highestPointM")
    if hp:
        row["h"] = hp
    if island.get("osmType"):
        row["ot"] = island["osmType"]
    if island.get("osmId") is not None:
        row["oi"] = int(island["osmId"])
    if island.get("images") or island.get("image"):
        row["img"] = 1
    if island.get("propertyListings"):
        row["sale"] = 1
    conf = (island.get("classification") or {}).get("confidence")
    if conf and conf != "high":
        row["c"] = conf
    return row


def slim_unnamed_stub(island: dict) -> dict:
    parent = island.get("parentWaterBody") or {}
    row = {
        "id": island["id"],
        "n": "Unnamed island",
        "ns": "unknown",
        "y": round(float(island["lat"]), 4),
        "x": round(float(island["lng"]), 4),
        "t": island.get("type") or "lake",
        "o": island.get("nation") or "",
    }
    if island.get("areaKm2"):
        row["a"] = round(float(island["areaKm2"]), 3)
    if island.get("subtype"):
        row["s"] = island["subtype"]
    if island.get("osmType"):
        row["ot"] = island["osmType"]
    if island.get("osmId") is not None:
        row["oi"] = int(island["osmId"])
    if parent.get("name") or parent.get("type"):
        row["wb"] = parent.get("name") or ""
        row["wt"] = parent.get("type") or ""
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

    main_rows = [compact_stub(x) for x in data if not is_unnamed(x)]
    unnamed_rows = [slim_unnamed_stub(x) for x in data if is_unnamed(x)]

    index_payload = {"version": INDEX_VERSION, "rows": main_rows}
    out.write_text(
        json.dumps(index_payload, separators=(",", ":"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    unnamed_payload = {"version": 1, "rows": unnamed_rows}
    unnamed_out.write_text(
        json.dumps(unnamed_payload, separators=(",", ":"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_shards(data)
    print(
        f"wrote {len(main_rows)} compact rows -> {out.name} "
        f"({out.stat().st_size / 1024 / 1024:.2f} MiB); "
        f"{len(unnamed_rows)} unnamed -> {unnamed_out.name} "
        f"({unnamed_out.stat().st_size / 1024 / 1024:.2f} MiB); "
        f"full {src.name} {src.stat().st_size / 1024 / 1024:.2f} MiB",
    )


if __name__ == "__main__":
    main()
