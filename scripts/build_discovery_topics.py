#!/usr/bin/env python3
"""Build data/discovery_topics.json — curated explore starting points."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
CURATED = DATA / "curated.json"
FERRIES = DATA / "ferries.json"
OUT = DATA / "discovery_topics.json"


def has_photo(island: dict) -> bool:
    return bool(island.get("images")) or bool(island.get("image"))


def lead_thumb(island: dict) -> str | None:
    images = island.get("images")
    if isinstance(images, list) and images:
        return images[0].get("url") or images[0].get("fullUrl")
    return island.get("image")


def ferry_ids(by_id: dict[str, dict]) -> set[str]:
    if not FERRIES.is_file():
        return set()
    data = json.loads(FERRIES.read_text(encoding="utf-8"))
    out: set[str] = set()
    for route in data.get("routes") or []:
        for key in ("from", "to"):
            iid = ((route.get("terminals") or {}).get(key) or {}).get("islandId")
            if iid and iid in by_id:
                out.add(iid)
    return out


def island_tags(island: dict, curated_by_id: dict[str, dict]) -> list[str]:
    tags = island.get("tags")
    if isinstance(tags, list) and tags:
        return [str(t) for t in tags]
    cur = curated_by_id.get(island.get("id") or "")
    if cur and isinstance(cur.get("tags"), list):
        return [str(t) for t in cur["tags"]]
    return []


def card_row(island: dict, curated_by_id: dict[str, dict], ferry_set: set[str]) -> dict:
    iid = island["id"]
    cur = curated_by_id.get(iid) or {}
    blurb = (island.get("shortDescription") or cur.get("shortDescription") or "").strip()
    return {
        "id": iid,
        "name": island.get("name") or iid,
        "nation": island.get("nation"),
        "lat": island.get("lat"),
        "lng": island.get("lng"),
        "shortDescription": blurb[:280] if blurb else "",
        "thumbUrl": lead_thumb(island),
        "hasPhoto": has_photo(island),
        "ferry": iid in ferry_set,
        "tags": island_tags(island, curated_by_id),
        "highestPointM": island.get("highestPointM"),
    }


def pick_ids(candidates: list[dict], *, limit: int) -> list[str]:
    rows = [c for c in candidates if c.get("id")]
    rows.sort(
        key=lambda i: (
            0 if has_photo(i) else 1,
            -(i.get("highestPointM") or 0),
            -(i.get("areaKm2") or 0),
            (i.get("name") or "").lower(),
        ),
    )
    seen: set[str] = set()
    out: list[str] = []
    for i in rows:
        iid = i["id"]
        if iid in seen:
            continue
        out.append(iid)
        seen.add(iid)
        if len(out) >= limit:
            break
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--limit-notable", type=int, default=36)
    p.add_argument("--limit-hopping", type=int, default=42)
    p.add_argument("--limit-thames", type=int, default=28)
    p.add_argument("--limit-summits", type=int, default=32)
    args = p.parse_args()

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    by_id = {i["id"]: i for i in islands if i.get("id")}
    curated_rows = json.loads(CURATED.read_text(encoding="utf-8")) if CURATED.is_file() else []
    curated_by_id = {r["id"]: r for r in curated_rows if isinstance(r, dict) and r.get("id")}
    ferry_set = ferry_ids(by_id)

    notable_candidates = [
        by_id[r["id"]]
        for r in curated_rows
        if isinstance(r, dict) and r.get("id") in by_id
    ]
    notable_ids = pick_ids(notable_candidates, limit=args.limit_notable)

    hop = []
    for iid in ferry_set:
        isl = by_id.get(iid)
        if not isl or isl.get("type") != "sea":
            continue
        tags = island_tags(isl, curated_by_id)
        if iid in curated_by_id or "ferry" in tags or has_photo(isl):
            hop.append(isl)
    hop.sort(
        key=lambda i: (
            0 if i.get("id") in curated_by_id else 1,
            0 if has_photo(i) else 1,
            (i.get("archipelago") or "zzz").lower(),
            (i.get("name") or "").lower(),
        ),
    )
    hopping_ids = pick_ids(hop, limit=args.limit_hopping)

    thames = []
    for isl in islands:
        iid = isl.get("id") or ""
        tags = island_tags(isl, curated_by_id)
        if (
            iid.startswith("thames-")
            or isl.get("source") == "wikipedia-thames"
            or (isl.get("classification") or {}).get("source") == "thames-list"
            or "thames" in tags
        ):
            thames.append(isl)
    thames_ids = pick_ids(thames, limit=args.limit_thames)

    summits = [
        i
        for i in islands
        if isinstance(i.get("highestPointM"), (int, float)) and i["highestPointM"] >= 600
    ]
    summit_ids = pick_ids(summits, limit=args.limit_summits)

    scotland = [i for i in islands if i.get("nation") == "Scotland"]

    def archipelago_match(isl: dict, needle: str) -> bool:
        arch = (isl.get("archipelago") or "").lower()
        return needle.lower() in arch

    scotland_classics = pick_ids(
        [i for i in scotland if i.get("id") in curated_by_id or has_photo(i)],
        limit=40,
    )
    inner_hebrides = pick_ids(
        [i for i in scotland if archipelago_match(i, "inner hebrides") and i.get("type") == "sea"],
        limit=36,
    )
    outer_hebrides = pick_ids(
        [i for i in scotland if archipelago_match(i, "outer hebrides") and i.get("type") == "sea"],
        limit=36,
    )
    orkney_shetland = pick_ids(
        [
            i
            for i in scotland
            if (archipelago_match(i, "orkney") or archipelago_match(i, "shetland"))
            and i.get("type") == "sea"
        ],
        limit=40,
    )
    scotland_ferry = pick_ids(
        [
            i
            for i in scotland
            if i.get("id") in ferry_set and i.get("type") == "sea"
        ],
        limit=42,
    )

    def topic(tid, title, subtitle, island_ids, *, chat_hint="", filter_presets=None):
        cards = [card_row(by_id[iid], curated_by_id, ferry_set) for iid in island_ids if iid in by_id]
        return {
            "id": tid,
            "title": title,
            "subtitle": subtitle,
            "chatHint": chat_hint,
            "filterPresets": filter_presets or {},
            "count": len(cards),
            "islandIds": island_ids,
            "islands": cards,
        }

    topics = [
        topic(
            "notable",
            "Notable islands",
            "Hand-picked classics — the curated spine of the atlas.",
            notable_ids,
            chat_hint="iconic islands with photos",
            filter_presets={"photosFirst": True},
        ),
        topic(
            "island-hopping",
            "Island-hopping",
            "Ferry-linked sea islands worth chaining into a route.",
            hopping_ids,
            chat_hint="ferry islands near Skye with photos",
            filter_presets={"ferry": True, "photosFirst": True},
        ),
        topic(
            "thames-eyots",
            "Thames eyots",
            "River islands and aits on the Thames.",
            thames_ids,
            chat_hint="Thames river islands",
        ),
        topic(
            "high-summits",
            "High summits",
            "Islands with peaks 600 m and above.",
            summit_ids,
            chat_hint="islands with summits",
            filter_presets={"elevation": True, "photosFirst": True},
        ),
        topic(
            "scotland-classics",
            "Scotland classics",
            "Curated and photographed Scottish islands — a sensible place to start.",
            scotland_classics,
            chat_hint="Scottish islands with photos",
            filter_presets={"photosFirst": True},
        ),
        topic(
            "inner-hebrides",
            "Inner Hebrides",
            "Sea islands of the Inner Hebrides — Mull, Skye, Islay, and neighbours.",
            inner_hebrides,
            chat_hint="Inner Hebrides ferry islands",
        ),
        topic(
            "outer-hebrides",
            "Outer Hebrides",
            "Lewis and Harris, Uists, Barra, and the western seaboard.",
            outer_hebrides,
            chat_hint="Outer Hebrides islands",
        ),
        topic(
            "orkney-shetland",
            "Orkney & Shetland",
            "Northern isles — dramatic coasts, birds, and ferry links from the mainland.",
            orkney_shetland,
            chat_hint="Orkney or Shetland islands",
        ),
        topic(
            "scotland-ferry-hops",
            "Scotland ferry hops",
            "Scottish sea islands you can reach by ferry from the mainland.",
            scotland_ferry,
            chat_hint="Scottish ferry islands near Oban",
            filter_presets={"ferry": True, "photosFirst": True},
        ),
    ]

    payload = {
        "schemaVersion": 1,
        "about": "Curated explore topics; regenerate via scripts/build_discovery_topics.py",
        "topics": topics,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for t in topics:
        print(f"  {t['id']:16s} {t['count']:3d} islands")
    print(f"Wrote {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
