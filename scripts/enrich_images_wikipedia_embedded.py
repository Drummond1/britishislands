#!/usr/bin/env python3
"""Harvest embedded Wikipedia images (prop=images), not just lead pageimages."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
STAGING = DATA / "staging" / "adoptions" / "wikipedia-embedded.json"
CACHE = DATA / "cache_wikipedia_embedded.json"
COMMONS_CACHE = DATA / "cache_commons_meta.json"
REPORT = DATA / "image_enrichment_wikipedia_embedded_report.json"
USER_AGENT = "isles-of-britain/0.1 (wikipedia-embedded)"
DELAY = 1.0
SKIP_FILE_RE = re.compile(
    r"(?:flag|coat|arms|logo|map|locator|diagram|chart|icon|svg|relief|"
    r"location|emblem|banner|seal)",
    re.I,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from enrich_images_v5 import (  # noqa: E402
    _canon,
    _load,
    _load_named_index_ids,
    _mentions,
    _name_variants,
    _save,
    build_image_record_from_commons,
    fetch_commons_meta,
)
from photo_staging_dual import save_staging  # noqa: E402

WIKI_SITES = (
    "enwiki", "cywiki", "gawiki", "gdwiki", "frwiki", "dewiki", "scowiki",
)


def _urlopen_json(req: urllib.request.Request, timeout: int = 90, retries: int = 4) -> dict:
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt + 1 < retries:
                time.sleep(15 * (attempt + 1))
                continue
            raise
    return {}


def _wiki_api(site: str, params: dict) -> dict:
    host = site.replace("wiki", ".wikipedia.org")
    if "voyage" in site:
        host = site.replace("wikivoyage", ".wikivoyage.org")
    base = f"https://{host}/w/api.php"
    qs = urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(
        base + "?" + qs,
        headers={"User-Agent": USER_AGENT},
    )
    return _urlopen_json(req)


def _sitelinks(qid: str, cache: dict) -> dict[str, str]:
    if qid in cache:
        return cache[qid]
    params = {
        "action": "wbgetentities",
        "ids": qid,
        "props": "sitelinks",
    }
    req = urllib.request.Request(
        "https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode({**params, "format": "json"}),
        headers={"User-Agent": USER_AGENT},
    )
    data = _urlopen_json(req)
    ent = (data.get("entities") or {}).get(qid) or {}
    sl = {k: v.get("title", "") for k, v in (ent.get("sitelinks") or {}).items()}
    cache[qid] = sl
    _save(CACHE, cache)
    return sl


def _embedded_files(site: str, title: str, cache: dict) -> list[str]:
    ck = f"{site}|{title}"
    if ck in cache:
        return cache[ck]
    data = _wiki_api(site, {
        "action": "query",
        "titles": title,
        "prop": "images",
        "imlimit": "50",
    })
    pages = (data.get("query") or {}).get("pages") or {}
    files: list[str] = []
    for page in pages.values():
        for im in page.get("images") or []:
            t = im.get("title") or ""
            if t.startswith("File:") and not SKIP_FILE_RE.search(t):
                files.append(t[5:])
    cache[ck] = files
    _save(CACHE, cache)
    return files


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--named-only", action="store_true", default=True)
    ap.add_argument("--limit", type=int, default=400)
    ap.add_argument("--delay", type=float, default=DELAY)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--test", default="")
    args = ap.parse_args()

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    named = _load_named_index_ids() if args.named_only else set()
    pending = [i for i in islands if not (i.get("images") or []) and i.get("wikidata")]
    if args.named_only:
        pending = [i for i in pending if i.get("id") in named]
    if args.test:
        pending = [i for i in islands if i.get("id") == args.test]
    pending = pending[: args.limit]

    cache = _load(CACHE)
    commons_cache = _load(COMMONS_CACHE)
    adoptions: list[dict] = []
    report = {"staged": 0, "adopted": [], "skipped": []}

    for isl in pending:
        qid = isl.get("wikidata", "")
        if not qid:
            continue
        sl = _sitelinks(qid, cache)
        time.sleep(args.delay * 0.3)
        variants = _name_variants(isl)
        found = False
        for site in WIKI_SITES:
            title = sl.get(site)
            if not title:
                continue
            for fname in _embedded_files(site, title, cache):
                if _mentions(fname, variants) or _mentions(title.replace("_", " "), variants):
                    canon = _canon(fname)
                    meta = fetch_commons_meta([canon], commons_cache).get(canon, {})
                    if not meta or not meta.get("url"):
                        continue
                    rec = build_image_record_from_commons(
                        fname,
                        meta,
                        source="wikipedia-embedded",
                        source_ref=f"{site}:{title}",
                    )
                    if rec:
                        rec["dualSignal"] = True
                        adoptions.append({
                            "id": isl["id"],
                            "islandId": isl["id"],
                            "image_record": rec,
                            "imageConfidence": rec.get("imageConfidence", "high"),
                            "wikiSite": site,
                            "file": fname,
                            "dualSignal": True,
                        })
                        report["adopted"].append({"id": isl["id"], "file": fname, "site": site})
                        found = True
                        break
            if found:
                break
            time.sleep(args.delay * 0.2)
        if not found:
            report["skipped"].append({"id": isl.get("id")})
        time.sleep(args.delay)

    report["staged"] = len(adoptions)
    if not args.dry_run:
        _save(COMMONS_CACHE, commons_cache)
        save_staging(STAGING, adoptions)
        REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wikipedia embedded staged: {len(adoptions)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
