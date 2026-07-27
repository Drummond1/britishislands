#!/usr/bin/env python3
"""Pull a 1–2 sentence Wikipedia *lead extract* into ``shortDescription``
for every island that doesn't yet have one.

Free, factual, CC-BY-SA via the MediaWiki API.  No LLM, no cost.
Targets islands that have a `wikidata` Q-ID or a `wikipedia` URL but
currently no ``shortDescription``.

Design goals:

  * **Idempotent** — re-running is safe; only fills empty fields.
  * **Atomic** — writes to ``islands.json.tmp`` then ``os.replace``.
  * **Checkpointed** — flushes every ``--checkpoint`` adoptions (default 50)
    so a crash never loses more than that.
  * **Throttled** — Wikipedia's API will reject burst traffic; we sleep
    between calls and back off on 429 / 5xx.
  * **Sitelink preflight** — batched Wikidata ``wbgetentities`` (enwiki +
    Celtic/Scots wikis) into ``cache_wp_lead_extracts.json``.
  * **Multilang** — when enwiki is absent, try gd/cy/ga/sco/gv lead extracts
    (native text; name-matched against ``names.*`` variants).
  * **Provenance** — every adopted blurb carries
    ``descriptionSource`` (``wikipedia-lead-extract`` or
    ``wikipedia-{lang}-lead-extract``),
    ``descriptionConfidence: "high"``,
    ``descriptionAttribution`` (CC-BY-SA notice with article URL),
    ``descriptionFetchedAt`` (ISO timestamp).

Usage::

    python3 scripts/enrich_descriptions_wikipedia.py --prefetch-sitelinks
    python3 scripts/enrich_descriptions_wikipedia.py --limit 100 --multilang
    python3 scripts/enrich_descriptions_wikipedia.py --dry-run

Output::

    data/islands.json                            (mutated, atomic)
    data/islands.json.before-wpdesc              (backup)
    data/cache_wp_lead_extracts.json             (sitelinks + lead extracts)
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
SITELINK_BATCH = 40

# Prefer English, then living Celtic / Scots editions used in the atlas.
# (Skip bot-heavy cebwiki stubs — poor description yield.)
PREFERRED_SITES: list[str] = [
    "enwiki",
    "gdwiki",
    "cywiki",
    "gawiki",
    "scowiki",
    "gvwiki",
]
SITE_TO_LANG = {
    "enwiki": "en",
    "gdwiki": "gd",
    "cywiki": "cy",
    "gawiki": "ga",
    "scowiki": "sco",
    "gvwiki": "gv",
}
SITE_TO_API = {
    "enwiki": "https://en.wikipedia.org/w/api.php",
    "gdwiki": "https://gd.wikipedia.org/w/api.php",
    "cywiki": "https://cy.wikipedia.org/w/api.php",
    "gawiki": "https://ga.wikipedia.org/w/api.php",
    "scowiki": "https://sco.wikipedia.org/w/api.php",
    "gvwiki": "https://gv.wikipedia.org/w/api.php",
}
SITEFILTER = "|".join(PREFERRED_SITES)

GENERIC_PLACE_TOKENS = {
    "island", "islands", "isle", "isles", "rock", "rocks", "skerry",
    "holm", "inch", "eilean", "ynys", "oilean", "oileán",
}


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
    return urllib.parse.unquote(m.group(1)).replace("_", " ")


def _norm_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def name_variants(isl: dict) -> list[str]:
    """Display name + language forms for extract name-matching."""
    out: list[str] = []
    seen: set[str] = set()
    names = isl.get("names") or {}
    alt = names.get("alt") if isinstance(names, dict) else None
    alt_list = alt if isinstance(alt, list) else []
    for cand in (
        isl.get("name"),
        *((names.get(k) for k in ("en", "gd", "cy", "ga", "sco", "gv", "kw")) if isinstance(names, dict) else ()),
        *alt_list,
    ):
        if not isinstance(cand, str) or not cand.strip():
            continue
        n = cand.strip()
        key = _norm_name(n)
        if key and key not in seen:
            seen.add(key)
            out.append(n)
    return out


def extract_cache_key(site: str, title: str) -> str:
    if site == "enwiki":
        return f"wp:{title}"
    return f"wp:{site}:{title}"


def sitelinks_for_qid(qid: str, cache: dict[str, Any]) -> dict[str, str] | None:
    """Return preferred-site sitelink map if prefetched; None if unknown."""
    if not qid:
        return None
    key = f"wdsl:{qid}"
    if key not in cache:
        return None
    v = cache[key]
    return v if isinstance(v, dict) else {}


def apply_sitelink_row(qid: str, row: dict[str, str], cache: dict[str, Any]) -> None:
    """Write enwiki + multilang sitelink map into the shared cache."""
    cache[f"wdsl:{qid}"] = row
    cache[f"wd:{qid}"] = row.get("enwiki") or ""


def prefetch_sitelinks(
    qids: list[str],
    cache: dict[str, Any],
    *,
    refresh: bool = False,
) -> dict[str, int]:
    """Batch Wikidata wbgetentities sitelinks into cache (enwiki + Celtic/Scots).

    Only marks ``wd:QID`` empty when the API responds successfully with no
    enwiki sitelink — failed HTTP calls do not poison the exhausted set.
    """
    unique: list[str] = []
    seen: set[str] = set()
    for q in qids:
        if not q or not re.match(r"^Q\d+$", q) or q in seen:
            continue
        seen.add(q)
        unique.append(q)

    todo: list[str] = []
    for q in unique:
        has_map = f"wdsl:{q}" in cache
        has_en = f"wd:{q}" in cache
        if refresh or not has_map or not has_en:
            todo.append(q)

    stats = {
        "requested": len(unique),
        "fetched": 0,
        "withEnwiki": 0,
        "withAnyPreferred": 0,
    }
    print(
        f"sitelink preflight: {len(todo)} Q-IDs to fetch "
        f"({len(unique) - len(todo)} already cached)",
        flush=True,
    )
    for i in range(0, len(todo), SITELINK_BATCH):
        batch = todo[i : i + SITELINK_BATCH]
        qs = urllib.parse.urlencode({
            "action": "wbgetentities",
            "ids": "|".join(batch),
            "props": "sitelinks",
            "sitefilter": SITEFILTER,
            "format": "json",
            "formatversion": "2",
        })
        data = http_get_json(f"{WD_API}?{qs}")
        if not data:
            print(f"  ! sitelink batch failed ({batch[0]}…); not caching empties", flush=True)
            time.sleep(DELAY_S)
            continue
        entities = data.get("entities") or {}
        for q in batch:
            ent = entities.get(q) or {}
            if ent.get("missing"):
                apply_sitelink_row(q, {}, cache)
                stats["fetched"] += 1
                continue
            sl_raw = ent.get("sitelinks") or {}
            row: dict[str, str] = {}
            for site in PREFERRED_SITES:
                title = ((sl_raw.get(site) or {}).get("title") or "").strip()
                if title:
                    row[site] = title
            apply_sitelink_row(q, row, cache)
            stats["fetched"] += 1
            if row.get("enwiki"):
                stats["withEnwiki"] += 1
            if row:
                stats["withAnyPreferred"] += 1
        save_json_atomic(CACHE, cache)
        print(
            f"  sitelinks {min(i + SITELINK_BATCH, len(todo))}/{len(todo)} "
            f"(enwiki so far {stats['withEnwiki']}, any {stats['withAnyPreferred']})",
            flush=True,
        )
        time.sleep(DELAY_S)
    return stats


def title_from_wikidata(qid: str, cache: dict[str, Any]) -> str | None:
    """Look up the en.wikipedia sitelink for a Wikidata Q-ID (single or cached)."""
    if not qid:
        return None
    key = f"wd:{qid}"
    if key in cache:
        v = cache[key]
        return v if isinstance(v, str) and v else None
    sl = sitelinks_for_qid(qid, cache)
    if sl is not None:
        title = sl.get("enwiki") or None
        cache[key] = title or ""
        return title
    qs = urllib.parse.urlencode({
        "action": "wbgetentities",
        "ids": qid,
        "props": "sitelinks",
        "sitefilter": SITEFILTER,
        "format": "json",
        "formatversion": "2",
    })
    data = http_get_json(f"{WD_API}?{qs}")
    if not data:
        # Do not cache failure as empty — leave miss for retry.
        return None
    try:
        ent = data["entities"][qid]
        if ent.get("missing"):
            apply_sitelink_row(qid, {}, cache)
            return None
        sl_raw = ent.get("sitelinks") or {}
        row: dict[str, str] = {}
        for site in PREFERRED_SITES:
            t = ((sl_raw.get(site) or {}).get("title") or "").strip()
            if t:
                row[site] = t
        apply_sitelink_row(qid, row, cache)
        return row.get("enwiki") or None
    except (KeyError, TypeError):
        apply_sitelink_row(qid, {}, cache)
        return None


def cached_title_pairs(
    isl: dict,
    cache: dict[str, Any],
    *,
    multilang: bool,
) -> list[tuple[str, str]]:
    """Cache-only (site, title) pairs — no live Wikidata fetch."""
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(site: str, title: str | None) -> None:
        if not title:
            return
        key = (site, title)
        if key in seen:
            return
        seen.add(key)
        out.append((site, title))

    wp_url = isl.get("wikipedia")
    add("enwiki", parse_wikipedia_title(wp_url) if wp_url else None)

    qid = isl.get("wikidata")
    if not qid:
        return out

    sl = sitelinks_for_qid(qid, cache)
    if sl is not None:
        sites = PREFERRED_SITES if multilang else ["enwiki"]
        for site in sites:
            add(site, sl.get(site))
        return out

    cached_en = cache.get(f"wd:{qid}")
    if isinstance(cached_en, str) and cached_en:
        add("enwiki", cached_en)
    return out


def resolve_title_candidates(
    isl: dict,
    cache: dict[str, Any],
    *,
    multilang: bool,
) -> list[tuple[str, str]]:
    """Ordered (site, title) candidates; may live-fetch Wikidata once per Q-ID."""
    pairs = cached_title_pairs(isl, cache, multilang=multilang)
    if pairs:
        return pairs
    qid = isl.get("wikidata")
    if not qid:
        return pairs
    if sitelinks_for_qid(qid, cache) is None and f"wd:{qid}" not in cache:
        title_from_wikidata(qid, cache)
        time.sleep(DELAY_S)
    return cached_title_pairs(isl, cache, multilang=multilang)


def fetch_lead_extract(
    title: str,
    cache: dict[str, Any],
    *,
    site: str = "enwiki",
) -> dict | None:
    """Return {extract, pageUrl, title, site, lang} for the article lead."""
    if not title:
        return None
    key = extract_cache_key(site, title)
    if key in cache:
        v = cache[key]
        if v in (None, {}):
            return None
        return v if isinstance(v, dict) else None
    api = SITE_TO_API.get(site) or WP_API
    lang = SITE_TO_LANG.get(site, "en")
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
    data = http_get_json(f"{api}?{qs}")
    if not data:
        # API failure — do not mark exhausted.
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
    host = api.split("/w/api.php")[0]
    result = {
        "extract": extract,
        "pageUrl": page.get("fullurl") or f"{host}/wiki/{urllib.parse.quote(title.replace(' ', '_'))}",
        "title": page.get("title") or title,
        "site": site,
        "lang": lang,
    }
    cache[key] = result
    return result


def clean_extract(text: str, island_name: str, variants: list[str] | None = None) -> str | None:
    """Light cleanup + name sanity check; return at most ~2 sentences."""
    if not text:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(
        r"^\s*\([^()]*?(?:pronunciation|/[^/]+/|listen)[^()]*?\)\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None

    ntext = _norm_name(text)
    names = list(variants or [])
    if island_name and island_name not in names:
        names.insert(0, island_name)
    hit = False
    for name in names:
        nname = _norm_name(name)
        if not nname:
            continue
        if nname in ntext:
            hit = True
            break
        first = nname.split(" ", 1)[0]
        tokens = [t for t in nname.split() if len(t) >= 4 and t not in GENERIC_PLACE_TOKENS]
        if (first and len(first) >= 3 and first in ntext) or any(t in ntext for t in tokens):
            hit = True
            break
    if names and not hit:
        return None

    parts = re.split(r"(?<=[\.\!\?])\s+(?=\S)", text)
    short = " ".join(parts[:2]).strip()
    if len(short) > 480:
        short = short[:479].rsplit(" ", 1)[0] + "…"
    return short or None


def is_exhausted_candidate(
    isl: dict,
    cache: dict[str, Any],
    *,
    multilang: bool = False,
) -> bool:
    """True when cache already proves this island won't yield a lead extract."""
    wp_url = isl.get("wikipedia")
    qid = isl.get("wikidata")
    en_from_url = parse_wikipedia_title(wp_url) if wp_url else None

    if not qid and not en_from_url:
        return True

    pairs = cached_title_pairs(isl, cache, multilang=multilang)

    if qid:
        sl = sitelinks_for_qid(qid, cache)
        if sl is None:
            # No preferred-site map yet. Bare ``wd:`` empty only proves enwiki
            # absence — multilang (gd/cy/ga/…) may still exist.
            if multilang:
                return False
            if f"wd:{qid}" not in cache:
                return False  # never tried
            if cache.get(f"wd:{qid}") == "" and not en_from_url:
                return True
            # enwiki title cached but extract status handled via pairs below
        if not pairs:
            if sl is not None:
                # Prefetch confirmed no preferred sitelinks.
                return not en_from_url
            if not multilang and cache.get(f"wd:{qid}") == "" and not en_from_url:
                return True
            return False

    if not pairs:
        return True

    variants = name_variants(isl)
    for site, title in pairs:
        cached = cache.get(extract_cache_key(site, title))
        if cached is None:
            return False  # title known, extract not fetched yet
        if cached == {}:
            continue
        if isinstance(cached, dict):
            extract = (cached.get("extract") or "").strip()
            if extract and clean_extract(extract, isl.get("name") or "", variants):
                return False
            continue
        return False
    return True


def description_source_for(site: str) -> str:
    lang = SITE_TO_LANG.get(site, "en")
    if lang == "en":
        return "wikipedia-lead-extract"
    return f"wikipedia-{lang}-lead-extract"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0,
                    help="process at most N candidates (0 = no limit)")
    ap.add_argument(
        "--queue-file",
        type=Path,
        default=None,
        help="JSON queue from build_description_priority_queue.py (ids processed in order)",
    )
    ap.add_argument("--checkpoint", type=int, default=50,
                    help="flush islands.json every N adoptions")
    ap.add_argument("--dry-run", action="store_true",
                    help="report only, do not mutate islands.json")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument(
        "--include-exhausted",
        action="store_true",
        help="retry cache-proven dead ends (default: skip them so --limit advances)",
    )
    ap.add_argument(
        "--prefetch-sitelinks",
        action="store_true",
        help="batch-fetch Wikidata sitelinks for candidates before extracts",
    )
    ap.add_argument(
        "--refresh-sitelinks",
        action="store_true",
        help="re-fetch sitelinks even when wd:/wdsl: keys exist (recovers false empties)",
    )
    ap.add_argument(
        "--multilang",
        action="store_true",
        help="also try gd/cy/ga/sco/gv Wikipedia leads when enwiki is absent",
    )
    ap.add_argument(
        "--prefetch-only",
        action="store_true",
        help="run sitelink preflight then exit (implies --prefetch-sitelinks)",
    )
    args = ap.parse_args()
    if args.prefetch_only:
        args.prefetch_sitelinks = True

    islands = load_json(ISLANDS, [])
    if not islands:
        print("! islands.json empty/missing — aborting", file=sys.stderr)
        sys.exit(1)
    cache = load_json(CACHE, {})

    # When refreshing sitelinks, include cache-"exhausted" Q-IDs so we can
    # recover false empties and discover Celtic sitelinks.
    defer_exhaustion = bool(
        args.refresh_sitelinks or args.prefetch_sitelinks or args.multilang
    )

    # Identify candidates.
    by_id_idx = {isl.get("id"): idx for idx, isl in enumerate(islands) if isinstance(isl, dict) and isl.get("id")}
    candidates: list[int] = []
    skipped_exhausted = 0
    if args.queue_file:
        qdata = load_json(args.queue_file, {})
        raw_queue = None
        if isinstance(qdata, dict):
            raw_queue = qdata.get("ids") or qdata.get("queue")
        else:
            raw_queue = qdata
        if not isinstance(raw_queue, list):
            print(f"! invalid queue file: {args.queue_file}", file=sys.stderr)
            sys.exit(1)
        for entry in raw_queue:
            if isinstance(entry, dict):
                iid = entry.get("id")
                if entry.get("needDescription") is False:
                    continue
            else:
                iid = entry
            if not iid:
                continue
            idx = by_id_idx.get(iid)
            if idx is None:
                continue
            isl = islands[idx]
            if (isl.get("shortDescription") or "").strip():
                continue
            if (
                not args.include_exhausted
                and not defer_exhaustion
                and is_exhausted_candidate(isl, cache, multilang=args.multilang)
            ):
                skipped_exhausted += 1
                continue
            candidates.append(idx)
        print(f"queue candidates from {args.queue_file.name}: {len(candidates)}")
    else:
        for idx, isl in enumerate(islands):
            if not isinstance(isl, dict):
                continue
            sd = (isl.get("shortDescription") or "").strip()
            if sd:
                continue
            if not (isl.get("wikipedia") or isl.get("wikidata")):
                continue
            if (
                not args.include_exhausted
                and not defer_exhaustion
                and is_exhausted_candidate(isl, cache, multilang=args.multilang)
            ):
                skipped_exhausted += 1
                continue
            candidates.append(idx)
        print(f"candidates with empty shortDescription + wd/wp link: {len(candidates)}")
    if skipped_exhausted:
        print(f"  skipped exhausted (cache): {skipped_exhausted}")
    if defer_exhaustion and not args.include_exhausted:
        print(
            "  (exhaustion deferred until after sitelink preflight / multilang)",
            flush=True,
        )

    # Prefetch uses the full candidate set (before --limit) so a limited
    # extract pass still warms sitelinks for the wider queue when requested.
    prefetch_pool = list(candidates)
    if args.limit and not args.prefetch_only:
        candidates = candidates[: args.limit]
        print(f"  (limited to {args.limit})")

    if args.prefetch_sitelinks:
        qids = [
            islands[idx].get("wikidata")
            for idx in (prefetch_pool if args.prefetch_only or not args.limit else candidates)
        ]
        # Always warm the broader pool when prefetching with a limit.
        if args.limit and not args.prefetch_only:
            qids = [islands[idx].get("wikidata") for idx in prefetch_pool]
        stats = prefetch_sitelinks(
            [q for q in qids if q],
            cache,
            refresh=args.refresh_sitelinks,
        )
        print(
            f"sitelink preflight done: fetched={stats['fetched']} "
            f"enwiki={stats['withEnwiki']} anyPreferred={stats['withAnyPreferred']}",
            flush=True,
        )
        # Re-filter from the full pool so --limit still fills after sitelink discovery.
        if not args.include_exhausted:
            kept: list[int] = []
            for idx in prefetch_pool:
                if is_exhausted_candidate(islands[idx], cache, multilang=args.multilang):
                    continue
                kept.append(idx)
            skipped_exhausted = len(prefetch_pool) - len(kept)

            def _yield_rank(idx: int) -> tuple:
                isl = islands[idx]
                qid = isl.get("wikidata") or ""
                sl = sitelinks_for_qid(qid, cache) or {}
                has_en = 0 if (sl.get("enwiki") or parse_wikipedia_title(isl.get("wikipedia") or "")) else 1
                has_celtic = 0 if any(sl.get(s) for s in ("gdwiki", "cywiki", "gawiki", "scowiki", "gvwiki")) else 1
                return (has_en, has_celtic, idx)

            kept.sort(key=_yield_rank)
            candidates = kept
            if args.limit and not args.prefetch_only:
                candidates = candidates[: args.limit]
            print(
                f"  candidates after sitelink filter: {len(candidates)} "
                f"(exhausted {skipped_exhausted})",
                flush=True,
            )

    if args.prefetch_only:
        save_json_atomic(CACHE, cache)
        print(f"prefetch-only complete → {CACHE.relative_to(ROOT)}")
        return

    # Backup before first mutation.
    if not args.dry_run and not BACKUP.exists():
        BACKUP.write_text(json.dumps(islands, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"backup → {BACKUP}")

    report = {
        "startedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "totalIslands": len(islands),
        "candidates": len(candidates),
        "multilang": bool(args.multilang),
        "adopted": 0,
        "skippedNoTitle": 0,
        "skippedNoExtract": 0,
        "skippedNameMismatch": 0,
        "adoptionsByNation": {},
        "adoptionsBySource": {},
        "samples": [],
    }
    adopted_since_flush = 0

    try:
        for n, idx in enumerate(candidates, 1):
            isl = islands[idx]
            name = isl.get("name") or "(unnamed)"
            variants = name_variants(isl)
            pairs = resolve_title_candidates(isl, cache, multilang=args.multilang)
            if not pairs:
                report["skippedNoTitle"] += 1
                if args.verbose:
                    print(f"  [{n}/{len(candidates)}] {name}: no wiki title", flush=True)
                continue

            adopted_here = False
            saw_extract = False
            for site, title in pairs:
                # Reject sitelinks whose article title clearly isn't this island
                # (wrong WD link / parent loch / neighbouring feature).
                if not clean_extract(title.replace("_", " "), name, variants):
                    if args.verbose:
                        print(
                            f"  [{n}/{len(candidates)}] {name}: title mismatch '{title}' ({site})",
                            flush=True,
                        )
                    continue
                lead = fetch_lead_extract(title, cache, site=site)
                time.sleep(DELAY_S)
                if not lead:
                    continue
                saw_extract = True
                short = clean_extract(lead["extract"], name, variants)
                if not short:
                    continue
                # Drop loch/lake/hill leads that never call the place an island /
                # eilean / ynys / etc., unless the island name itself is a hill.
                nshort = _norm_name(short)
                name_is_hill = bool(re.search(r"\b(hill|fiold|beinn)\b", _norm_name(name)))
                if not name_is_hill and re.search(
                    r"\b(beinn|hill|mountain)\b", nshort[:80]
                ) and not re.search(
                    r"\b(eilean|island|isle|ynys|oilean|oileán|inis|holm|skerry|rock)\b",
                    nshort,
                ):
                    report["skippedNameMismatch"] += 1
                    if args.verbose:
                        print(
                            f"  [{n}/{len(candidates)}] {name}: hill/mountain lead rejected",
                            flush=True,
                        )
                    continue
                if re.match(r"^(loch|lake)\b", nshort) and _norm_name(name) not in nshort:
                    # Parent waterbody article, not the island.
                    if not any(
                        _norm_name(v) in nshort
                        for v in variants
                        if _norm_name(v) and _norm_name(v) != _norm_name(name)
                    ):
                        report["skippedNameMismatch"] += 1
                        if args.verbose:
                            print(
                                f"  [{n}/{len(candidates)}] {name}: loch/lake lead rejected",
                                flush=True,
                            )
                        continue
                src = description_source_for(site)
                isl["shortDescription"] = short
                isl["descriptionSource"] = src
                isl["descriptionConfidence"] = "high"
                lang = lead.get("lang") or SITE_TO_LANG.get(site, "en")
                lang_note = "" if lang == "en" else f" [{lang}]"
                isl["descriptionAttribution"] = (
                    f"From Wikipedia{lang_note} article \u201c{lead['title']}\u201d "
                    "(CC BY-SA 4.0). "
                    f"Read more: {lead['pageUrl']}"
                )
                isl["descriptionFetchedAt"] = dt.datetime.now(dt.timezone.utc).isoformat(
                    timespec="seconds"
                )
                report["adopted"] += 1
                report["adoptionsBySource"][src] = report["adoptionsBySource"].get(src, 0) + 1
                adopted_since_flush += 1
                nat = isl.get("nation") or "Unknown"
                report["adoptionsByNation"][nat] = report["adoptionsByNation"].get(nat, 0) + 1
                if len(report["samples"]) < 25:
                    report["samples"].append({
                        "id": isl.get("id"),
                        "name": name,
                        "short": short,
                        "title": lead["title"],
                        "site": site,
                        "source": src,
                    })
                print(
                    f"  [{n}/{len(candidates)}] ✓ {name} ({site}): "
                    f"\"{short[:90]}{'…' if len(short) > 90 else ''}\"",
                    flush=True,
                )
                adopted_here = True
                break

            if not adopted_here:
                if saw_extract:
                    report["skippedNameMismatch"] += 1
                    if args.verbose:
                        print(
                            f"  [{n}/{len(candidates)}] {name}: extract name mismatch",
                            flush=True,
                        )
                else:
                    report["skippedNoExtract"] += 1
                    if args.verbose:
                        print(
                            f"  [{n}/{len(candidates)}] {name}: no extract",
                            flush=True,
                        )

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
        print(f"  by source          : {report['adoptionsBySource']}")
        print(f"skipped no title     : {report['skippedNoTitle']}")
        print(f"skipped no extract   : {report['skippedNoExtract']}")
        print(f"skipped name mismatch: {report['skippedNameMismatch']}")
        print(f"report               → {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
