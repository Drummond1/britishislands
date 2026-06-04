#!/usr/bin/env python3
"""Photo enrichment — multilingual Wikipedia / Wikivoyage pageimages.

For named atlas islands that still have no photo, uses Wikidata sitelinks on
cy/ga/gd/fr/de Wikipedia and en + language-variant Wikivoyage, then MediaWiki
``prop=pageimages`` on each wiki. Priority (first hit wins):

  1. enwikivoyage, then other *wikivoyage sitelinks
  2. cywiki, gawiki, gdwiki
  3. frwiki, dewiki

Commons file metadata and licence checks reuse ``fetch_commons_meta`` from v5.

Run::

    python3 scripts/enrich_images_multilang_wiki.py --stage-only --limit 400
    python3 scripts/enrich_images_multilang_wiki.py --limit 200
    python3 scripts/enrich_images_multilang_wiki.py --test iona

Outputs::

    data/staging/adoptions/multilang-wiki.json     (--stage-only; no islands.json write)
    data/islands.json                              (default: mutated, atomic write)
    data/islands.json.before-multilang-wiki        (backup, once)
    data/cache_multilang_sitelinks.json
    data/cache_multilang_pageimages.json
    data/image_enrichment_multilang_report.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
BACKUP = DATA / "islands.json.before-multilang-wiki"
CACHE_SITELINKS = DATA / "cache_multilang_sitelinks.json"
CACHE_PAGEIMAGES = DATA / "cache_multilang_pageimages.json"
REPORT = DATA / "image_enrichment_multilang_report.json"
STAGING = DATA / "staging" / "adoptions" / "multilang-wiki.json"

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
DELAY_S = 1.2

# Sitelink keys to fetch from Wikidata (union of all tiers).
SITELINK_KEYS = (
    "enwikivoyage",
    "cywikivoyage",
    "gawikivoyage",
    "gdwikivoyage",
    "frwikivoyage",
    "dewikivoyage",
    "cywiki",
    "gawiki",
    "gdwiki",
    "frwiki",
    "dewiki",
)

# Try in this order; stop at first licence-valid photo.
SITELINK_PRIORITY = [
    "enwikivoyage",
    "cywikivoyage",
    "gawikivoyage",
    "gdwikivoyage",
    "frwikivoyage",
    "dewikivoyage",
    "cywiki",
    "gawiki",
    "gdwiki",
    "frwiki",
    "dewiki",
]

SOURCE_BY_SITE: dict[str, str] = {
    "enwikivoyage": "wikivoyage",
    "cywikivoyage": "wikivoyage",
    "gawikivoyage": "wikivoyage",
    "gdwikivoyage": "wikivoyage",
    "frwikivoyage": "wikivoyage",
    "dewikivoyage": "wikivoyage",
    "cywiki": "wikipedia-cy",
    "gawiki": "wikipedia-ga",
    "gdwiki": "wikipedia-gd",
    "frwiki": "wikipedia-fr",
    "dewiki": "wikipedia-de",
}

sys.path.insert(0, str(ROOT / "scripts"))
from enrich_images_v5 import (  # noqa: E402
    CACHE_COMMONS,
    RL_BACKOFF,
    build_image_record_from_commons,
    fetch_commons_meta,
    _atomic_write_islands,
    _canon,
    _get_json,
    _load,
    _load_named_index_ids,
    _looks_like_non_photo,
    _save,
)


def _wiki_lang(site: str) -> str:
    if site.endswith("wikivoyage"):
        return site[: -len("wikivoyage")]
    if site.endswith("wiki"):
        return site[: -len("wiki")]
    return site


def _api_url(site: str) -> str:
    lang = _wiki_lang(site)
    host = "wikivoyage.org" if site.endswith("wikivoyage") else "wikipedia.org"
    return f"https://{lang}.{host}/w/api.php"


def _page_url(site: str, title: str) -> str:
    lang = _wiki_lang(site)
    slug = urllib.parse.quote(title.replace(" ", "_"))
    if site.endswith("wikivoyage"):
        return f"https://{lang}.wikivoyage.org/wiki/{slug}"
    return f"https://{lang}.wikipedia.org/wiki/{slug}"


def _pi_cache_key(site: str, title: str) -> str:
    return f"{site}|{title}"


def fetch_multilang_sitelinks(
    qids: list[str],
    cache: dict,
    *,
    refresh: bool,
    api_notes: list[str] | None = None,
) -> dict[str, dict[str, str]]:
    """Return {qid: {site_key: page_title, ...}} for requested sitelinks."""
    missing = [q for q in qids if refresh or q not in cache]
    BATCH = 40
    sitefilter = "|".join(SITELINK_KEYS)
    for i in range(0, len(missing), BATCH):
        batch = missing[i : i + BATCH]
        params = {
            "action": "wbgetentities",
            "format": "json",
            "ids": "|".join(batch),
            "props": "sitelinks",
            "sitefilter": sitefilter,
        }
        try:
            payload = _get_json(WIKIDATA_API, params)
        except Exception as exc:
            print(f"  sitelinks batch failed: {exc!r}", file=sys.stderr)
            if api_notes is not None:
                api_notes.append(f"wbgetentities: {exc!r}")
            continue
        entities = payload.get("entities") or {}
        for q in batch:
            ent = entities.get(q) or {}
            sl = ent.get("sitelinks") or {}
            row: dict[str, str] = {}
            for site in SITELINK_KEYS:
                title = (sl.get(site) or {}).get("title", "")
                if title:
                    row[site] = title
            cache[q] = row
        _save(CACHE_SITELINKS, cache)
        time.sleep(DELAY_S)
    return {q: cache.get(q, {}) for q in qids}


def fetch_multilang_pageimages(
    requests: list[tuple[str, str]],
    cache: dict,
    *,
    refresh: bool,
    api_notes: list[str] | None = None,
) -> dict[str, str]:
    """``requests`` is [(site_key, title), ...]. Returns {site|title: File:… or ''}."""
    norm = [_pi_cache_key(site, title) for site, title in requests if site and title]
    norm = list(dict.fromkeys(norm))
    missing_keys = [k for k in norm if refresh or k not in cache]
    if not missing_keys:
        return {k: cache.get(k, "") for k in norm}

    by_site: dict[str, list[str]] = {}
    for key in missing_keys:
        site, _, title = key.partition("|")
        if site and title:
            by_site.setdefault(site, []).append(title)

    BATCH = 30
    for site, titles in by_site.items():
        api = _api_url(site)
        unique_titles = list(dict.fromkeys(titles))
        for i in range(0, len(unique_titles), BATCH):
            batch = unique_titles[i : i + BATCH]
            params = {
                "action": "query",
                "format": "json",
                "prop": "pageimages",
                "piprop": "original|name",
                "titles": "|".join(batch),
                "redirects": 1,
            }
            try:
                payload = _get_json(api, params)
            except Exception as exc:
                print(f"  pageimages [{site}] failed: {exc!r}", file=sys.stderr)
                if api_notes is not None:
                    api_notes.append(f"pageimages[{site}]: {exc!r}")
                continue
            pages = (payload.get("query") or {}).get("pages") or {}
            redirects = {
                r["from"]: r["to"]
                for r in (payload.get("query") or {}).get("redirects") or []
            }
            norm_map = {
                n["from"]: n["to"]
                for n in (payload.get("query") or {}).get("normalized") or []
            }

            def _back_to_requested(final_title: str) -> str:
                for src in batch:
                    t = norm_map.get(src, src)
                    t = redirects.get(t, t)
                    if t == final_title:
                        return src
                return final_title

            for _pid, page in pages.items():
                title = page.get("title", "")
                fname = (page.get("pageimage") or "").strip()
                if fname and not fname.startswith("File:"):
                    fname = "File:" + fname
                requested = _back_to_requested(title)
                cache[_pi_cache_key(site, requested)] = fname or ""
            for t in batch:
                cache.setdefault(_pi_cache_key(site, t), "")
            _save(CACHE_PAGEIMAGES, cache)
            time.sleep(DELAY_S)

    return {k: cache.get(k, "") for k in norm}


def try_multilang_pageimage(
    island: dict,
    sl_cache: dict,
    pi_cache: dict,
    commons_cache: dict,
) -> tuple[dict | None, str, str]:
    qid = (island.get("wikidata") or "").strip()
    if not re.match(r"^Q\d+$", qid):
        return None, "", ""
    sitelinks = sl_cache.get(qid, {})
    if not sitelinks:
        return None, "", ""

    for site in SITELINK_PRIORITY:
        title = sitelinks.get(site, "")
        if not title:
            continue
        fname = pi_cache.get(_pi_cache_key(site, title), "")
        if not fname or _looks_like_non_photo(fname):
            continue
        canon = _canon(fname)
        meta = fetch_commons_meta([canon], commons_cache).get(canon, {})
        source = SOURCE_BY_SITE.get(site, "wikipedia")
        rec = build_image_record_from_commons(
            canon,
            meta,
            source,
            f"{site}:{title}",
        )
        if rec:
            rec["sourcePageUrl"] = _page_url(site, title)
            return rec, source, site
    return None, "", ""


def main() -> int:
    global DELAY_S
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit", type=int, default=None, help="Max islands to attempt.")
    p.add_argument("--test", metavar="ID", help="Single island id.")
    p.add_argument(
        "--stage-only",
        action="store_true",
        help="Write adoptions to data/staging/adoptions/multilang-wiki.json only.",
    )
    p.add_argument("--no-backup", action="store_true", help="Skip islands.json backup.")
    p.add_argument(
        "--named-only",
        action="store_true",
        help="Only islands in islands_index.json (default).",
    )
    p.add_argument(
        "--include-unnamed",
        action="store_true",
        help="Include islands not in islands_index.json (default: named only).",
    )
    p.add_argument("--refresh", action="store_true", help="Ignore sitelink/pageimage caches.")
    p.add_argument(
        "--delay",
        type=float,
        default=None,
        help=f"Seconds between Wikimedia API calls (default {DELAY_S}).",
    )
    args = p.parse_args()
    if args.delay is not None:
        DELAY_S = max(0.0, float(args.delay))

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    if not isinstance(islands, list):
        print("FATAL: islands.json is not a list", file=sys.stderr)
        return 2

    if (
        not args.stage_only
        and not args.no_backup
        and not BACKUP.exists()
    ):
        BACKUP.write_text(
            json.dumps(islands, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Backup → {BACKUP.relative_to(ROOT)}")

    api_notes: list[str] = []
    cache_sl = _load(CACHE_SITELINKS)
    cache_pi = _load(CACHE_PAGEIMAGES)
    cache_commons = _load(CACHE_COMMONS)

    pending = [i for i in islands if not (i.get("images") or [])]
    if not args.include_unnamed:
        named_ids = _load_named_index_ids()
        if named_ids:
            before = len(pending)
            pending = [i for i in pending if i.get("id") in named_ids]
            print(f"  named-only: {len(pending):,} of {before:,} without images", flush=True)

    pending = [i for i in pending if re.match(r"^Q\d+$", (i.get("wikidata") or "").strip())]
    if args.test:
        pending = [i for i in pending if i.get("id") == args.test]
    if args.limit:
        pending = pending[: args.limit]

    report: dict[str, Any] = {
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "args": vars(args),
        "stage_only": bool(args.stage_only),
        "pending": len(pending),
        "adopted": [],
        "rejected": [],
        "by_source": {},
        "by_wiki_site": {},
        "rate_limit_notes": [
            f"DELAY_S={DELAY_S} between Wikimedia API batches in this script.",
            "HTTP 429 / soft rate-limit: enrich_images_v5._get_json retries "
            f"with backoff {list(RL_BACKOFF)}.",
        ],
    }
    print(f"Pending (named, no image, Wikidata Q-ID): {len(pending):,}", flush=True)

    qids = sorted({(i.get("wikidata") or "").strip() for i in pending})
    sl_todo = [q for q in qids if args.refresh or q not in cache_sl]
    if sl_todo:
        print(f"  pre-fetch sitelinks for {len(sl_todo):,} Q-IDs…", flush=True)
    fetch_multilang_sitelinks(qids, cache_sl, refresh=args.refresh, api_notes=api_notes)

    pi_requests: list[tuple[str, str]] = []
    for q in qids:
        for site in SITELINK_PRIORITY:
            title = (cache_sl.get(q) or {}).get(site, "")
            if title:
                pi_requests.append((site, title))
    pi_requests = list(dict.fromkeys(pi_requests))
    pi_missing = [
        (s, t)
        for s, t in pi_requests
        if args.refresh or _pi_cache_key(s, t) not in cache_pi
    ]
    if pi_missing:
        print(f"  pre-fetch pageimages for {len(pi_missing):,} titles…", flush=True)
        fetch_multilang_pageimages(
            pi_missing, cache_pi, refresh=args.refresh, api_notes=api_notes,
        )
    elif pi_requests:
        fetch_multilang_pageimages(pi_requests, cache_pi, refresh=False, api_notes=api_notes)

    if api_notes:
        report["rate_limit_notes"].extend(api_notes)

    pending_set = {i.get("id") for i in pending}
    staged: list[dict[str, Any]] = []
    n_attempted = 0
    n_adopted = 0
    by_source: dict[str, int] = {}
    by_wiki_site: dict[str, int] = {}
    for isl in islands:
        if isl.get("id") not in pending_set:
            continue
        n_attempted += 1
        rec, source_used, wiki_site = try_multilang_pageimage(
            isl, cache_sl, cache_pi, cache_commons,
        )
        if rec:
            entry = {
                "id": isl["id"],
                "name": isl.get("name", ""),
                "wikidata": isl.get("wikidata", ""),
                "wikiSite": wiki_site,
                "source": rec.get("source"),
                "sourceRef": rec.get("sourceRef"),
                "license": rec.get("license"),
                "sourcePageUrl": rec.get("sourcePageUrl"),
                "image": rec,
            }
            report["adopted"].append(entry)
            by_source[source_used] = by_source.get(source_used, 0) + 1
            if wiki_site:
                by_wiki_site[wiki_site] = by_wiki_site.get(wiki_site, 0) + 1
            if args.stage_only:
                staged.append(entry)
            else:
                isl.setdefault("images", []).append(rec)
            n_adopted += 1
            print(
                f"  ✓ {isl['id']:45s} via {source_used:16s} → {rec.get('license', '')}",
                flush=True,
            )
        else:
            report["rejected"].append({
                "id": isl["id"],
                "name": isl.get("name", ""),
                "reason": "no multilang pageimage with valid licence",
            })

        if not args.stage_only and n_attempted % 50 == 0:
            _atomic_write_islands(islands)
            _save(REPORT, report)

    if args.stage_only:
        STAGING.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "pipeline": "enrich_images_multilang_wiki",
            "attempted": n_attempted,
            "staged_count": n_adopted,
            "by_source": by_source,
            "by_wiki_site": by_wiki_site,
            "adoptions": staged,
        }
        STAGING.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Staging  → {STAGING.relative_to(ROOT)} ({n_adopted:,} adoptions)")
    else:
        _atomic_write_islands(islands)

    report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    report["attempted"] = n_attempted
    report["adopted_total"] = n_adopted
    report["staged_total"] = n_adopted if args.stage_only else 0
    report["by_source"] = by_source
    report["by_wiki_site"] = by_wiki_site
    _save(REPORT, report)

    print()
    print(f"Attempted: {n_attempted:,}")
    label = "Staged" if args.stage_only else "Adopted"
    print(f"{label}:   {n_adopted:,}")
    if by_source:
        print("By source:", ", ".join(f"{k}={v}" for k, v in sorted(by_source.items())))
    if by_wiki_site:
        print("By wiki:", ", ".join(f"{k}={v}" for k, v in sorted(by_wiki_site.items())))
    print(f"Report   → {REPORT.relative_to(ROOT)}")
    return n_adopted


if __name__ == "__main__":
    count = main()
    print(f"adoption_count={count}")
    raise SystemExit(0)
