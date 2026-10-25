#!/usr/bin/env python3
"""Shared matcher for artwork harvest scripts.

Interest filters cite a specific work on a specific atlas island.
Import this module; do not run a write-pipeline from here.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from interest_categories import (  # noqa: E402
    Atlas,
    CANDIDATES,
    fold,
    load_json,
    row,
)

# name_key() strips "isle of" / "island", so these leftovers match the wrong
# place or a common word. A harvest may use them only when the source says
# "Isle of …", "Island of …", "Ynys …", or "Eilean …".
AMBIGUOUS_KEYS = {
    "man",
    "rum",
    "rhum",
    "muck",
    "may",
    "bass",
    "calf",
    "lamb",
    "horse",
    "sheep",
    "coll",
    "harris",
    "lewis",
    "jersey",
    "guernsey",
    "green",
    "long",
    "round",
    "sand",
    "rock",
    "holm",
    "inch",
    "eye",
    "flat",
    "great",
    "little",
    "north",
    "south",
    "east",
    "west",
    "new",
    "old",
    "white",
    "black",
    "red",
    "bull",
    "cow",
    "hen",
    "puffin",
    "seal",
    "hare",
    "ox",
    "ram",
    "crow",
    "rat",
    "mouse",
    "saint",
    "st",
    "holy",
    "fair",
    "wall",
    "canvey",
    "hayling",
    "walney",
    "portland",
    "sheppey",
    "wight",
    "scilly",
    "orkney",
    "shetland",
    "hebrides",
    "britain",
    "england",
    "scotland",
    "wales",
    "ireland",
    "uk",
    "united kingdom",
    "great britain",
    "channel",
}

NATION_PHRASES = {
    "great britain",
    "britain",
    "united kingdom",
    "england",
    "scotland",
    "wales",
    "ireland",
    "northern ireland",
    "republic of ireland",
    "uk",
}

QUALIFIED_PREFIX = re.compile(
    r"\b(isle of|island of|ynys|eilean|inis|inish|oiléan|oilean)\b",
    re.I,
)


def existing_facet_keys(facet: str) -> set[tuple[str, str]]:
    """Island id + folded title already accepted for this facet."""
    keys: set[tuple[str, str]] = set()
    if not CANDIDATES.exists():
        return keys
    for path in CANDIDATES.glob("*.json"):
        payload = load_json(path, {})
        for item in payload.get("rows") or []:
            if item.get("status") != "accepted":
                continue
            item_facet = item.get("facet") or ""
            if facet == "artwork" and item_facet not in ("", "artwork"):
                continue
            if facet != "artwork" and item_facet != facet:
                continue
            island_id = item.get("island_id") or ""
            title = item.get("title") or ""
            if island_id and title:
                keys.add((island_id, fold(title)))
    return keys


def existing_artwork_keys() -> set[tuple[str, str]]:
    """Island id + folded title already accepted as artwork."""
    return existing_facet_keys("artwork")


def existing_music_keys() -> set[tuple[str, str]]:
    """Island id + folded title already accepted as music."""
    return existing_facet_keys("music")


def phrase_in_text(phrase: str, text: str) -> bool:
    """Whole-word match after folding accents."""
    if not phrase or not text:
        return False
    pattern = r"\b" + re.escape(fold(phrase)) + r"\b"
    return re.search(pattern, fold(text)) is not None


def _qualified(phrase: str) -> bool:
    return bool(QUALIFIED_PREFIX.search(phrase or ""))


def match_island_phrase(atlas: Atlas, phrase: str) -> dict | None:
    """Resolve a source phrase to one atlas island, or return None.

    Rejects nations, Great Britain, Ireland, and tiny ambiguous leftovers
    unless the source itself uses a qualified island form.
    """
    cleaned = re.sub(r"\s+", " ", (phrase or "")).strip(" ,.;:-")
    if not cleaned or fold(cleaned) in NATION_PHRASES:
        return None
    island = atlas.match_name(cleaned)
    if not island:
        return None
    if (island.get("area") or 0) > 8000:
        return None
    # Prefer the full atlas name when the source only said the short form
    # and that short form is ambiguous ("Harris", "Man", "Jersey").
    from ingest_sources import name_key

    key = name_key(cleaned)
    if key in AMBIGUOUS_KEYS and not _qualified(cleaned):
        if fold(cleaned) != fold(island["name"]) and not phrase_in_text(island["name"], cleaned):
            return None
        if not _qualified(island["name"]) and fold(cleaned) == key:
            return None
    return island


def search_phrases(atlas: Atlas) -> list[tuple[str, dict]]:
    """Distinctive queries: qualified names, plus longer unique names.

    Returns (query, island) pairs. Callers still have to see the query in
    the hit's title or description.
    """
    from ingest_sources import name_key

    pairs: list[tuple[str, dict]] = []
    seen: set[tuple[str, str]] = set()
    for island in atlas.islands:
        area = island.get("area") or 0
        if area < 1 or area > 8000:
            continue
        name = (island.get("name") or "").strip()
        if not name or fold(name) in NATION_PHRASES:
            continue
        key = name_key(name)
        if len(key) < 4:
            continue
        queries = []
        # Bare short names ("Iona", "Staffa") are useful. Ambiguous leftovers
        # ("Harris", "Man") are only queried in a qualified form.
        if _qualified(name) or (key not in AMBIGUOUS_KEYS and len(key) >= 4):
            queries.append(name)
        if not _qualified(name):
            queries.append(f"Isle of {name}")
            queries.append(f"Island of {name}")
        for query in queries:
            query = query.strip()
            if not query:
                continue
            token = (island["id"], fold(query))
            if token in seen:
                continue
            seen.add(token)
            pairs.append((query, island))
    pairs.sort(key=lambda item: item[1].get("area") or 0, reverse=True)
    return pairs


def artwork_row(
    *,
    island: dict,
    title: str,
    source_url: str,
    source_title: str,
    licence: str,
    evidence: str,
    summary: str,
    external_id: str = "",
    commons_file: str = "",
    open_image: dict | None = None,
    seen: set[tuple[str, str]] | None = None,
) -> dict | None:
    """Build one accepted artwork row, or None when it duplicates or is empty."""
    title = re.sub(r"\s+", " ", (title or "")).strip()
    if not title or not source_url or not island or not island.get("id"):
        return None
    if re.fullmatch(r"Q\d+", title):
        return None
    if re.search(r"\b(possibly|inspired by|untitled photograph)\b", title, re.I):
        return None
    key = (island["id"], fold(title))
    if seen is not None:
        if key in seen:
            return None
        seen.add(key)
    built = row(
        category="film-art-music",
        island_id=island["id"],
        island_name=island["name"],
        facet="artwork",
        title=title[:180],
        source_url=source_url,
        source_title=(source_title or title)[:180],
        licence=licence,
        evidence=evidence[:500],
        external_id=external_id,
        status="accepted",
        confidence="high",
    )
    built["summary"] = summary[:500]
    if commons_file:
        built["commons_file"] = commons_file
    if open_image and open_image.get("thumbUrl") and open_image.get("licence"):
        built["open_image"] = open_image
    return built


def music_row(
    *,
    island: dict,
    title: str,
    source_url: str,
    source_title: str,
    licence: str,
    evidence: str,
    summary: str,
    external_id: str = "",
    commons_file: str = "",
    seen: set[tuple[str, str]] | None = None,
) -> dict | None:
    """Build one accepted music or band row, or None when it duplicates."""
    title = re.sub(r"\s+", " ", (title or "")).strip()
    if not title or not source_url or not island or not island.get("id"):
        return None
    if re.fullmatch(r"Q\d+", title) or re.fullmatch(r"[0-9a-f-]{36}", title):
        return None
    if re.search(r"\b(possibly|inspired by|karaoke|tribute band)\b", title, re.I):
        return None
    key = (island["id"], fold(title))
    if seen is not None:
        if key in seen:
            return None
        seen.add(key)
    built = row(
        category="film-art-music",
        island_id=island["id"],
        island_name=island["name"],
        facet="music",
        title=title[:180],
        source_url=source_url,
        source_title=(source_title or title)[:180],
        licence=licence,
        evidence=evidence[:500],
        external_id=external_id,
        status="accepted",
        confidence="high",
    )
    built["summary"] = summary[:500]
    if commons_file:
        built["commons_file"] = commons_file
    return built
