#!/usr/bin/env python3
"""Build data/chat_corpus.json — a lazy search sidecar for Ask.

The map index keeps first paint small, so it has no loch name, description,
summit name, or Gaelic/Welsh/Irish form. Ask loads this file only when
someone opens the chat. It is derived from data/islands.json. Regenerate
after island records change:

    python3 scripts/build_chat_corpus.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "islands.json"
OUT = ROOT / "data" / "chat_corpus.json"

OSM_WATER = re.compile(r"^OSM relation \d+$", re.I)
NAME_LANGS = ("gd", "ga", "cy", "gv", "kw", "sco", "alt")


def _clean(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def row_for(island: dict) -> dict | None:
    if island.get("nameStatus") == "unknown":
        return None
    name = (island.get("name") or "").strip()
    if not name or name == "Unnamed island":
        return None
    row: dict = {}
    water = ((island.get("parentWaterBody") or {}).get("name") or "").strip()
    if water and not OSM_WATER.match(water):
        row["w"] = water
    description = _clean(island.get("shortDescription") or "", 220)
    if description:
        row["d"] = description
    peak = (island.get("highestPointName") or "").strip()
    if peak:
        row["p"] = peak
    names = island.get("names") if isinstance(island.get("names"), dict) else {}
    alts = []
    for lang in NAME_LANGS:
        value = names.get(lang)
        if isinstance(value, str) and value.strip():
            alts.append(value.strip())
    if alts:
        row["n"] = " · ".join(alts[:6])
    return row or None


def main() -> None:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    rows = {}
    for island in data:
        iid = island.get("id")
        if not iid:
            continue
        row = row_for(island)
        if row:
            rows[str(iid)] = row
    payload = {
        "version": 1,
        "source": "data/islands.json",
        "rows": rows,
    }
    OUT.write_text(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(rows)} rows -> {OUT.name} ({OUT.stat().st_size / 1024:.0f} KiB)")


if __name__ == "__main__":
    main()
