#!/usr/bin/env python3
"""Enrich data/operators.json with Wikipedia URLs from their Wikidata Q-IDs.

For each operator that already has a ``wikidata`` Q-ID, fetch
``wbgetentities`` for the English sitelink and populate ``wikipediaUrl``.

Idempotent and safe to re-run; existing ``wikipediaUrl`` values are preserved.

Run:
    python3 scripts/enrich_ferries_wiki.py
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPERATORS_PATH = ROOT / "data" / "operators.json"

USER_AGENT = "isles-of-britain/0.1 (ferries-wiki-enrich)"
WBGET_URL = "https://www.wikidata.org/w/api.php"


def _get_json(url: str, *, retries: int = 5) -> dict:
    last_exc: Exception | None = None
    delay = 2.0
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                wait = max(delay, float(exc.headers.get("Retry-After") or delay))
                print(f"  429; sleeping {wait:.0f}s", file=sys.stderr)
                time.sleep(wait)
                delay *= 2
                last_exc = exc
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as exc:
            time.sleep(delay)
            delay *= 2
            last_exc = exc
    raise RuntimeError(f"Wikidata request failed after {retries} attempts: {last_exc}")


def fetch_wikipedia_url_by_qid(qid: str) -> tuple[str | None, str | None]:
    """Return (enwiki_url, label) for a given Q-ID."""
    params = {
        "action": "wbgetentities",
        "ids": qid,
        "props": "sitelinks/urls|labels",
        "sitefilter": "enwiki",
        "languages": "en",
        "format": "json",
    }
    url = f"{WBGET_URL}?{urllib.parse.urlencode(params)}"
    data = _get_json(url)
    entities = data.get("entities", {})
    ent = entities.get(qid) or {}
    sitelinks = ent.get("sitelinks", {}) or {}
    enwiki = (sitelinks.get("enwiki") or {}).get("url") or None
    labels = ent.get("labels", {}) or {}
    label = (labels.get("en") or {}).get("value")
    return enwiki, label


def search_wikidata(name: str, *, limit: int = 5) -> list[dict]:
    params = {
        "action": "wbsearchentities",
        "search": name,
        "language": "en",
        "format": "json",
        "limit": limit,
        "type": "item",
    }
    url = f"{WBGET_URL}?{urllib.parse.urlencode(params)}"
    data = _get_json(url)
    return data.get("search", []) or []


def main() -> int:
    doc = json.loads(OPERATORS_PATH.read_text(encoding="utf-8"))
    ops = doc.get("operators", [])
    added = 0
    cleared = 0
    looked_up = 0

    # Step 1: validate any pre-existing Q-IDs. Drop ones whose enwiki label
    # doesn't match the operator name (we previously seeded hallucinated
    # Q-IDs).
    for op in ops:
        qid = (op.get("wikidata") or "").strip()
        if not qid:
            continue
        try:
            url, label = fetch_wikipedia_url_by_qid(qid)
        except Exception as exc:
            print(f"  {op['id']}: lookup failed: {exc}", file=sys.stderr)
            continue
        time.sleep(0.3)
        looked_up += 1
        op_name_l = op["name"].lower()
        short_l = (op.get("shortName") or "").lower()
        label_l = (label or "").lower()
        match = bool(label_l) and (
            label_l in op_name_l or op_name_l in label_l or
            (short_l and (short_l in label_l or label_l in short_l))
        )
        if match and url:
            op["wikipediaUrl"] = url
            print(f"  ✓ {op['id']} verified Q{qid[1:]} → {url}", file=sys.stderr)
        else:
            print(f"  ✗ {op['id']} Q-ID {qid} maps to '{label}' (no name match); clearing", file=sys.stderr)
            op["wikidata"] = ""
            if "wikipediaUrl" in op:
                op.pop("wikipediaUrl")
            cleared += 1

    # Step 2: for operators that no longer have a Q-ID, attempt to find one
    # by searching Wikidata with the operator's full name; pick the first
    # candidate whose description mentions ferry / shipping / boat / cruise.
    for op in ops:
        if (op.get("wikidata") or "").strip():
            continue
        candidates = search_wikidata(op["name"])
        time.sleep(0.3)
        chosen: dict | None = None
        for c in candidates:
            desc = (c.get("description") or "").lower()
            if any(k in desc for k in ("ferry", "shipping", "ferries", "boat", "lake cruise", "river cruise", "river bus", "passenger ship")):
                chosen = c
                break
        if not chosen:
            continue
        qid = chosen["id"]
        try:
            url, label = fetch_wikipedia_url_by_qid(qid)
        except Exception as exc:
            print(f"  {op['id']}: post-search lookup failed: {exc}", file=sys.stderr)
            continue
        time.sleep(0.3)
        looked_up += 1
        if url:
            op["wikidata"] = qid
            op["wikipediaUrl"] = url
            added += 1
            print(f"  + {op['id']} found {qid} → {url}", file=sys.stderr)

    tmp = OPERATORS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(OPERATORS_PATH)
    print(f"done. Lookups: {looked_up}. Cleared bad Q-IDs: {cleared}. Found Wikipedia URLs: {added}.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
