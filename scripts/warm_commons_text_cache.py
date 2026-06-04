#!/usr/bin/env python3
"""Warm ``cache_commons_text.json`` for photoless named islands (no islands.json writes).

For each pending island missing a text-cache key, runs Commons ``list=search`` for::

    "{name}"
    "{name}" geograph

Uses the same cache keys as ``enrich_images_v5`` and
``enrich_images_geograph_commons`` (``name|archipelago`` and
``"{name}" geograph|archipelago``).

Stops immediately on HTTP 429 so a later run can resume. Writes only
``data/cache_commons_text.json``.

Run::

    python3 scripts/warm_commons_text_cache.py --delay 3 --limit 500
    python3 scripts/warm_commons_text_cache.py --dry-run --limit 20
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
ISLANDS_INDEX = DATA / "islands_index.json"
CACHE_COMMONS_TEXT = DATA / "cache_commons_text.json"
REPORT = DATA / "warm_commons_text_cache_report.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from enrich_images_v5 import (  # noqa: E402
    COMMONS_API,
    USER_AGENT,
    _canon,
    _load,
    _load_named_index_ids,
    _save,
)


class CommonsRateLimited(Exception):
    """Raised when Commons returns HTTP 429."""


def _commons_search_once(query: str, limit: int) -> list[str]:
    params = {
        "action": "query",
        "format": "json",
        "list": "search",
        "srsearch": query,
        "srnamespace": "6",
        "srlimit": str(limit),
        "srprop": "snippet",
    }
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{COMMONS_API}?{qs}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise CommonsRateLimited("Commons HTTP 429") from exc
        raise
    payload = json.loads(raw.decode("utf-8"))
    out: list[str] = []
    for hit in (payload.get("query") or {}).get("search") or []:
        title = hit.get("title", "")
        if title.startswith("File:"):
            out.append(_canon(title))
    return out


def plain_cache_key(island: dict) -> str:
    name = (island.get("name") or "").strip()
    arch = (island.get("archipelago") or "").strip()
    return f"{name}|{arch}"


def geograph_cache_key(island: dict) -> str:
    name = (island.get("name") or "").strip()
    arch = (island.get("archipelago") or "").strip()
    return f'"{name}" geograph|{arch}'


def plain_query(island: dict) -> str:
    name = (island.get("name") or "").strip()
    return f'"{name}"'


def geograph_query(island: dict) -> str:
    name = (island.get("name") or "").strip()
    return f'"{name}" geograph'


def _pending_named(islands: list[dict], named_only: bool) -> list[dict]:
    pending = [i for i in islands if not (i.get("images") or [])]
    if named_only:
        named_ids = _load_named_index_ids()
        if named_ids:
            pending = [i for i in pending if i.get("id") in named_ids]
    return pending


def main() -> int:
    p = argparse.ArgumentParser(description="Warm cache_commons_text.json (Commons text search).")
    p.add_argument("--delay", type=float, default=3.0, help="Seconds between API calls.")
    p.add_argument("--limit", type=int, default=500, help="Max islands to consider (0 = all).")
    p.add_argument("--sr-limit", type=int, default=50, help="Commons srlimit per query.")
    p.add_argument("--named-only", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--test", default="", help="Single island id.")
    args = p.parse_args()

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    if not isinstance(islands, list):
        print("FATAL: islands.json is not a list", file=sys.stderr)
        return 2

    cache = _load(CACHE_COMMONS_TEXT)
    keys_before = len(cache)

    pending = _pending_named(islands, args.named_only)
    if args.test:
        pending = [i for i in islands if i.get("id") == args.test]
    if args.limit:
        pending = pending[: args.limit]

    report: dict[str, Any] = {
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "args": vars(args),
        "keys_before": keys_before,
        "keys_added": 0,
        "queries_run": 0,
        "islands_considered": len(pending),
        "stopped_on_429": False,
        "warmed": [],
    }

    keys_added = 0
    queries_run = 0

    print(f"Pending islands: {len(pending):,}  cache keys: {keys_before:,}", flush=True)

    try:
        for isl in pending:
            name = (isl.get("name") or "").strip()
            if len(name) < 4:
                continue
            iid = isl.get("id", "")
            warmed_island: list[str] = []

            jobs: list[tuple[str, str, str]] = []
            pk = plain_cache_key(isl)
            if pk not in cache:
                jobs.append((pk, plain_query(isl), "plain"))
            gk = geograph_cache_key(isl)
            if gk not in cache:
                jobs.append((gk, geograph_query(isl), "geograph"))

            if not jobs:
                continue

            for key, query, kind in jobs:
                if args.dry_run:
                    print(f"  [dry-run] {iid} {kind}: {query}", flush=True)
                    continue
                print(f"  search {kind}: {query[:60]}", flush=True)
                files = _commons_search_once(query, args.sr_limit)
                cache[key] = files
                keys_added += 1
                queries_run += 1
                warmed_island.append(kind)
                _save(CACHE_COMMONS_TEXT, cache)
                time.sleep(max(0.0, args.delay))

            if warmed_island:
                report["warmed"].append({
                    "id": iid,
                    "name": name,
                    "kinds": warmed_island,
                })

    except CommonsRateLimited:
        report["stopped_on_429"] = True
        print("Stopped on Commons 429 — resume later.", file=sys.stderr, flush=True)

    report["keys_after"] = len(cache)
    report["keys_added"] = keys_added
    report["queries_run"] = queries_run
    report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")

    if not args.dry_run:
        _save(REPORT, report)

    print()
    print(f"Keys before:   {keys_before:,}")
    print(f"Keys added:    {keys_added:,}")
    print(f"Queries run:   {queries_run:,}")
    print(f"Keys after:    {len(cache):,}")
    if report["stopped_on_429"]:
        print("Stopped on 429.")
    if not args.dry_run:
        print(f"Report → {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
