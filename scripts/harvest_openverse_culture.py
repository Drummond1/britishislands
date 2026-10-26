#!/usr/bin/env python3
"""Harvest openly licensed engravings and paintings from Openverse.

A hit is kept only when the title names one atlas island and the title or
tags mark it as a print, painting, or score. Photographs, maps, and portraits
are left out. Does not publish.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from artwork_harvest_common import (  # noqa: E402
    artwork_row,
    existing_artwork_keys,
    existing_music_keys,
    music_row,
    phrase_in_text,
)
from interest_categories import (  # noqa: E402
    CLOSED_IMAGE_LICENCE,
    OPEN_IMAGE_LICENCE,
    Atlas,
    http_json,
    save_json,
    utc_now,
)

CACHE = ROOT / "data" / "cache_openverse_culture"
OUT = ROOT / "data" / "interest" / "candidates" / "openverse-culture.json"
UA = "IslesOfBritain/0.1 ( https://www.findmyisland.com )"
API = "https://api.openverse.org/v1/images/"

WORK_WORDS = (
    "engraving",
    "etching",
    "lithograph",
    "painting",
    "watercolour",
    "watercolor",
    "aquatint",
    "mezzotint",
    "woodcut",
    "sculpture",
    "sheet music",
    "score",
)
REJECT_WORDS = (
    "photograph",
    "photo",
    "portrait",
    "map",
    "postcard",
    "selfie",
    "sunset",
    "beach",
    "aerial",
    "snapshot",
    "sgian",
)
EXTRA_NAMES = (
    "Iona",
    "Staffa",
    "Lindisfarne",
    "St Kilda",
    "Skellig Michael",
    "Bardsey Island",
    "Ailsa Craig",
    "Bass Rock",
    "Fair Isle",
    "Foula",
    "Eigg",
    "Rum",
    "Canna",
    "Lundy",
    "Sark",
    "Alderney",
    "Inishmore",
    "Rathlin Island",
    "Tory Island",
    "Tresco",
    "Eriskay",
    "Mingulay",
    "Isle of Man",
    "Isles of Scilly",
    "Cape Clear Island",
    "Valentia Island",
    "Clare Island",
)


def licence_label(code: str, version: str) -> str:
    code = (code or "").lower().strip()
    version = (version or "").strip()
    if code in {"cc0", "pdm", "publicdomain"}:
        return "CC0"
    if code == "by":
        return f"CC BY {version}".strip()
    if code == "by-sa":
        return f"CC BY-SA {version}".strip()
    return ""


def cache_get(url: str) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".json")
    if path.exists():
        return json.loads(path.read_text())
    payload = http_json(url, timeout=40, user_agent=UA)
    path.write_text(json.dumps(payload))
    time.sleep(1.0)
    return payload


def island_targets(atlas: Atlas) -> list[dict]:
    chosen: dict[str, dict] = {}
    for island in atlas.islands:
        area = island.get("area") or 0
        name = island.get("name") or ""
        if area > 8000 or name.lower() in {"great britain", "britain", "ireland", "england", "scotland", "wales"}:
            continue
        if area >= 40 or name in EXTRA_NAMES:
            previous = chosen.get(island["id"])
            if previous and (previous.get("area") or 0) >= area:
                continue
            chosen[island["id"]] = island
    # One row per name, keeping the larger island when names collide.
    by_name: dict[str, dict] = {}
    for island in chosen.values():
        key = island["name"].lower()
        previous = by_name.get(key)
        if previous and (previous.get("area") or 0) >= (island.get("area") or 0):
            continue
        by_name[key] = island
    return sorted(by_name.values(), key=lambda item: item.get("area") or 0, reverse=True)


def blob(result: dict) -> str:
    tags = " ".join((tag.get("name") or "") for tag in result.get("tags") or [])
    return f"{result.get('title') or ''} {tags}"


def write_out(rows: list[dict], rejected: list[dict]) -> None:
    save_json(
        OUT,
        {
            "slug": "openverse-culture",
            "generatedAt": utc_now(),
            "sources": ["openverse"],
            "rows": rows + rejected,
        },
    )


def main() -> None:
    atlas = Atlas()
    seen = existing_artwork_keys() | existing_music_keys()
    rows = []
    rejected = []
    per_island: dict[str, int] = {}
    stopped = False
    for island in island_targets(atlas):
        if stopped or len(rows) >= 80:
            break
        name = island["name"]
        for kind in ("engraving", "painting"):
            if per_island.get(island["id"], 0) >= 6 or len(rows) >= 80:
                break
            query = f'"{name}" {kind}'
            url = API + "?" + urllib.parse.urlencode(
                {
                    "q": query,
                    "license": "cc0,by,by-sa",
                    "license_type": "commercial",
                    "page_size": "12",
                }
            )
            try:
                payload = cache_get(url)
            except Exception as exc:  # noqa: BLE001 — one query can fail
                print(f"skip {query}: {exc}", flush=True)
                message = str(exc).lower()
                if "429" in message or "503" in message:
                    print("rate limit, saving what is kept", flush=True)
                    stopped = True
                    break
                continue
            for result in payload.get("results") or []:
                title = (result.get("title") or "").strip()
                text = blob(result)
                low = text.lower()
                if not title or not phrase_in_text(name, title):
                    continue
                if not any(word in low for word in WORK_WORDS):
                    continue
                if any(word in low for word in REJECT_WORDS):
                    if len(rejected) < 30:
                        rejected.append(
                            {
                                "title": title[:180],
                                "island_name": name,
                                "status": "rejected",
                                "reject_reason": "Photograph, map, or portrait.",
                            }
                        )
                    continue
                licence = licence_label(result.get("license") or "", result.get("license_version") or "")
                if (
                    not licence
                    or not OPEN_IMAGE_LICENCE.search(licence)
                    or CLOSED_IMAGE_LICENCE.search(licence)
                ):
                    continue
                source = result.get("foreign_landing_url") or result.get("detail_url") or ""
                thumb = result.get("thumbnail") or result.get("url") or ""
                if not source or not thumb:
                    continue
                facet_music = "sheet music" in low or "score" in low
                attribution = result.get("creator") or result.get("source") or "Openverse"
                image = {
                    "thumbUrl": thumb,
                    "pageUrl": source,
                    "attribution": attribution,
                    "licence": licence,
                    "licenceUrl": result.get("license_url") or "",
                }
                common = dict(
                    island=island,
                    title=title,
                    source_url=source,
                    source_title=title,
                    licence=licence,
                    evidence=f"Openverse title names {name} and is tagged as a {kind}.",
                    summary=f"{title} is an openly licensed {kind} whose title names {name}.",
                    external_id=result.get("id") or "",
                    seen=seen,
                )
                if facet_music:
                    built = music_row(**common)
                else:
                    built = artwork_row(**common, open_image=image)
                if not built:
                    continue
                rows.append(built)
                per_island[island["id"]] = per_island.get(island["id"], 0) + 1
                print(f"keep {name}: {title[:70]}", flush=True)
                if per_island[island["id"]] >= 6 or len(rows) >= 80:
                    break
        write_out(rows, rejected)
    write_out(rows, rejected)
    islands = len({row["island_id"] for row in rows})
    print(f"wrote {len(rows)} accepted on {islands} islands, rejected {len(rejected)}", flush=True)


if __name__ == "__main__":
    main()
