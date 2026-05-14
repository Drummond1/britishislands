#!/usr/bin/env python3
"""Pull a 1–2 sentence Wikipedia *lead extract* into ``shortDescription``
for every island that doesn't yet have one.

Free, factual, CC-BY-SA via the MediaWiki API.  No LLM, no cost.
Targets the ~2,320 islands that have a `wikidata` Q-ID or a `wikipedia`
URL but currently no ``shortDescription``.

Design goals:

  * **Idempotent** — re-running is safe; only fills empty fields.
  * **Atomic** — writes to ``islands.json.tmp`` then ``os.replace``.
  * **Checkpointed** — flushes every ``--checkpoint`` adoptions (default 50)
    so a crash never loses more than that.
  * **Throttled** — Wikipedia's API will reject burst traffic; we sleep
    between calls and back off on 429 / 5xx.
  * **Provenance** — every adopted blurb carries
    ``descriptionSource: "wikipedia-lead-extract"``,
    ``descriptionConfidence: "high"``,
    ``descriptionAttribution`` (CC-BY-SA notice with article URL),
    ``descriptionFetchedAt`` (ISO timestamp).

Usage::

    python3 scripts/enrich_descriptions_wikipedia.py
    python3 scripts/enrich_descriptions_wikipedia.py --limit 100
    python3 scripts/enrich_descriptions_wikipedia.py --dry-run

Output::

    data/islands.json                            (mutated, atomic)
    data/islands.json.before-wpdesc              (backup)
    data/cache_wp_lead_extracts.json             (en.wikipedia.org cache)
    data/description_enrichment_report.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
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
BACKUP = DATA / "islands.json.before-wpdesc"
CACHE = DATA / "cache_wp_lead_extracts.json"
REPORT = DATA / "description_enrichment_report.json"

UA = "isles-of-britain/0.7 (overnight; +https://github.com/local-atlas)"
WP_API = "https://en.wikipedia.org/w/api.php"
WD_API = "https://www.wikidata.org/w/api.php"

DELAY_S = 0.6  # ~100 reqs / min, safely under Wikipedia's published limit


def load_json(p: Path, default):
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json_atomic(p: Path, obj):
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def http_get_json(url: str, max_retries: int = 4) -> dict | None:
    """GET a URL expecting JSON, with backoff on rate-limit / 5xx."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read().decode("utf-8")
                return json.loads(data)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                backoff = (2 ** attempt) * 1.5
                print(f"  ! HTTP {e.code}, backing off {backoff:.1f}s", flush=True)
                time.sleep(backoff)
                continue
            print(f"  ! HTTP {e.code} (final): {url[:120]}", flush=True)
            return None
        except (urllib.error.URLError, TimeoutError, ConnectionResetError, OSError) as e:
            backoff = (2 ** attempt) * 1.5
            print(f"  ! {type(e).__name__}, backing off {backoff:.1f}s", flush=True)
            time.sleep(backoff)
            continue
        except json.JSONDecodeError:
            return None
    return None


def parse_wikipedia_title(url: str) -> str | None:
    """Extract the en.wikipedia title from a URL like
    `https://en.wikipedia.org/wiki/Foo_Island`."""
    if not url or not isinstance(url, str):
        return None
    m = re.search(r"en\.wikipedia\.org/wiki/([^#?]+)", url)
    if not m:
        return None
    return urllib.parse.unquote(m.group(1))


def title_from_wikidata(qid: str, cache: dict[str, Any]) -> str | None:
    """Look up the en.wikipedia sitelink for a Wikidata Q-ID."""
    if not qid:
        return None
    key = f"wd:{qid}"
    if key in cache:
        v = cache[key]
        return v if isinstance(v, str) and v else None
    qs = urllib.parse.urlencode({
        "action": "wbgetentities",
        "ids": qid,
        "props": "sitelinks",
        "sitefilter": "enwiki",
        "format": "json",
        "formatversion": "2",
    })
    data = http_get_json(f"{WD_API}?{qs}")
    title: str | None = None
    if data:
        try:
            sl = data["entities"][qid]["sitelinks"].get("enwiki", {})
            title = sl.get("title") or None
        except (KeyError, TypeError):
            title = None
    cache[key] = title or ""
    return title


def fetch_lead_extract(title: str, cache: dict[str, Any]) -> dict | None:
    """Return {extract, pageUrl} for the first paragraph of the article."""
    if not title:
        return None
    key = f"wp:{title}"
    if key in cache:
        v = cache[key]
        if v in (None, {}):
            return None
        return v if isinstance(v, dict) else None
    qs = urllib.parse.urlencode({
        "action": "query",
        "titles": title,
        "prop": "extracts|info",
        "exintro": "1",
        "explaintext": "1",
        "exsentences": "3",
        "inprop": "url",
        "redirects": "1",
        "format": "json",
        "formatversion": "2",
    })
    data = http_get_json(f"{WP_API}?{qs}")
    if not data:
        cache[key] = {}
        return None
    pages = (data.get("query") or {}).get("pages") or []
    if not pages:
        cache[key] = {}
        return None
    page = pages[0]
    if page.get("missing"):
        cache[key] = {}
        return None
    extract = (page.get("extract") or "").strip()
    if not extract:
        cache[key] = {}
        return None
    result = {
        "extract": extract,
        "pageUrl": page.get("fullurl") or f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title)}",
        "title": page.get("title") or title,
    }
    cache[key] = result
    return result


def clean_extract(text: str, island_name: str) -> str | None:
    """Light cleanup: collapse whitespace, ditch pronunciation pile-ups
    in parentheses if they're at the start, and return at most ~2 sentences.

    Returns None if the text doesn't actually look like it's about the
    island (cheap sanity check)."""
    if not text:
        return None
    # Collapse whitespace.
    text = re.sub(r"\s+", " ", text).strip()
    # If the first paren block contains pronunciation cruft, drop it.
    text = re.sub(
        r"^\s*\([^()]*?(?:pronunciation|/[^/]+/|listen)[^()]*?\)\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    # Sanity check: the extract should mention the island name at least once.
    # We allow case/diacritic-insensitive match by stripping non-alphanumerics.
    norm = lambda s: re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()
    if island_name and norm(island_name) not in norm(text):
        # Look at the first token alone (helps for "Iona" matching "Iona Abbey")
        first = norm(island_name).split(" ", 1)[0]
        if first and first not in norm(text):
            return None
    # Keep at most 2 sentences-ish for the card; full text via Wikipedia link.
    parts = re.split(r"(?<=[\.\!\?])\s+(?=[A-Z])", text)
    short = " ".join(parts[:2]).strip()
    if len(short) > 480:
        short = short[:479].rsplit(" ", 1)[0] + "…"
    return short or None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0,
                    help="process at most N candidates (0 = no limit)")
    ap.add_argument("--checkpoint", type=int, default=50,
                    help="flush islands.json every N adoptions")
    ap.add_argument("--dry-run", action="store_true",
                    help="report only, do not mutate islands.json")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    islands = load_json(ISLANDS, [])
    if not islands:
        print("! islands.json empty/missing — aborting", file=sys.stderr)
        sys.exit(1)
    cache = load_json(CACHE, {})

    # Identify candidates.
    candidates: list[int] = []
    for idx, isl in enumerate(islands):
        if not isinstance(isl, dict):
            continue
        sd = (isl.get("shortDescription") or "").strip()
        if sd:
            continue
        if not (isl.get("wikipedia") or isl.get("wikidata")):
            continue
        candidates.append(idx)
    print(f"candidates with empty shortDescription + wd/wp link: {len(candidates)}")
    if args.limit:
        candidates = candidates[: args.limit]
        print(f"  (limited to {args.limit})")

    # Backup before first mutation.
    if not args.dry_run and not BACKUP.exists():
        BACKUP.write_text(json.dumps(islands, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"backup → {BACKUP}")

    report = {
        "startedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "totalIslands": len(islands),
        "candidates": len(candidates),
        "adopted": 0,
        "skippedNoTitle": 0,
        "skippedNoExtract": 0,
        "skippedNameMismatch": 0,
        "adoptionsByNation": {},
        "samples": [],
    }
    adopted_since_flush = 0

    try:
        for n, idx in enumerate(candidates, 1):
            isl = islands[idx]
            name = isl.get("name") or "(unnamed)"
            qid = isl.get("wikidata")
            wp_url = isl.get("wikipedia")
            title = parse_wikipedia_title(wp_url) if wp_url else None
            if not title and qid:
                title = title_from_wikidata(qid, cache)
                time.sleep(DELAY_S)
            if not title:
                report["skippedNoTitle"] += 1
                if args.verbose:
                    print(f"  [{n}/{len(candidates)}] {name}: no enwiki title", flush=True)
                continue
            lead = fetch_lead_extract(title, cache)
            time.sleep(DELAY_S)
            if not lead:
                report["skippedNoExtract"] += 1
                if args.verbose:
                    print(f"  [{n}/{len(candidates)}] {name}: no extract for '{title}'", flush=True)
                continue
            short = clean_extract(lead["extract"], name)
            if not short:
                report["skippedNameMismatch"] += 1
                if args.verbose:
                    print(f"  [{n}/{len(candidates)}] {name}: extract didn't mention island, skipping", flush=True)
                continue

            # Adopt.
            isl["shortDescription"] = short
            isl["descriptionSource"] = "wikipedia-lead-extract"
            isl["descriptionConfidence"] = "high"
            isl["descriptionAttribution"] = (
                f"From Wikipedia article \u201c{lead['title']}\u201d "
                "(CC BY-SA 4.0). "
                f"Read more: {lead['pageUrl']}"
            )
            isl["descriptionFetchedAt"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            report["adopted"] += 1
            adopted_since_flush += 1
            nat = isl.get("nation") or "Unknown"
            report["adoptionsByNation"][nat] = report["adoptionsByNation"].get(nat, 0) + 1
            if len(report["samples"]) < 25:
                report["samples"].append({"id": isl.get("id"), "name": name,
                                          "short": short, "title": lead["title"]})
            print(f"  [{n}/{len(candidates)}] ✓ {name}: \"{short[:90]}{'…' if len(short)>90 else ''}\"",
                  flush=True)

            # Periodic checkpoint.
            if not args.dry_run and adopted_since_flush >= args.checkpoint:
                save_json_atomic(ISLANDS, islands)
                save_json_atomic(CACHE, cache)
                save_json_atomic(REPORT, report)
                adopted_since_flush = 0
                print(f"  ... checkpoint flushed at {report['adopted']} adoptions", flush=True)

    except KeyboardInterrupt:
        print("\n! interrupted, flushing partial progress", flush=True)
    finally:
        if not args.dry_run:
            save_json_atomic(ISLANDS, islands)
        save_json_atomic(CACHE, cache)
        report["finishedAt"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        save_json_atomic(REPORT, report)
        print()
        print(f"adopted              : {report['adopted']}")
        print(f"  by nation          : {report['adoptionsByNation']}")
        print(f"skipped no title     : {report['skippedNoTitle']}")
        print(f"skipped no extract   : {report['skippedNoExtract']}")
        print(f"skipped name mismatch: {report['skippedNameMismatch']}")
        print(f"report               → {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
