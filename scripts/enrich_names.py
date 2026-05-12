#!/usr/bin/env python3
"""
Cultural-names enrichment — populate `island.names` with the Wikidata
labels in the islands' regional languages.

Languages targeted:
  * gd  — Scottish Gaelic       (Gàidhlig)
  * cy  — Welsh                 (Cymraeg)
  * ga  — Irish Gaelic          (Gaeilge)
  * gv  — Manx Gaelic           (Gaelg)
  * kw  — Cornish               (Kernewek)
  * sco — Scots                 (Scots)
  * fr  — French                (for the French islands within 50 mi)
  * nrf — Norman                (Channel Islands)

We only set a label if it differs from the English name (case-insensitive
+ diacritic-stripped); otherwise it's noise. We never overwrite a label
that's already set on the island record.

Source: Wikidata `wbgetentities` `props=labels`, batched 50 Q-IDs at a
time. We cache responses in `data/cache_wikidata_labels.json` so reruns
are quick. ~2,700 islands have a Q-ID; the rest are skipped.

Atomic write of `data/islands.json` with backup at
`data/islands.json.before-names`. Report at
`data/names_enrichment_report.json`.

Run:
    python3 scripts/enrich_names.py
    python3 scripts/enrich_names.py --limit 50   # quick test
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS_PATH = DATA / "islands.json"
BACKUP_PATH = DATA / "islands.json.before-names"
CACHE_PATH = DATA / "cache_wikidata_labels.json"
REPORT_PATH = DATA / "names_enrichment_report.json"

WD_API = "https://www.wikidata.org/w/api.php"
USER_AGENT = (
    "isles-of-britain/0.5 (cultural-names enrichment; static-site prototype)"
)
TARGET_LANGS = ["gd", "cy", "ga", "gv", "kw", "sco", "fr", "nrf"]
DELAY_S = 1.2          # polite spacing between batches
BATCH = 50


def _atomic_write(path: Path, payload) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text())
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    _atomic_write(CACHE_PATH, cache)


def _ascii_lower(s: str) -> str:
    n = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return n.lower().strip()


def _get_json(url: str, params: dict, retries: int = 6) -> dict:
    """GET with exponential backoff that respects 429 (Retry-After) and
    transient network errors. Wikidata limits anon clients to a few req/s,
    so we ramp from 4s up to 96s between attempts."""
    qs = urllib.parse.urlencode(params)
    full = url + "?" + qs
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                full,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as exc:
            if attempt + 1 == retries:
                raise
            wait = max(int(exc.headers.get("Retry-After", "0") or 0), 4 * (2 ** attempt))
            print(f"  http {exc.code}; sleeping {wait}s before retry "
                  f"({attempt + 1}/{retries})", file=sys.stderr)
            time.sleep(wait)
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt + 1 == retries:
                raise
            wait = 4 * (2 ** attempt)
            print(f"  network err ({exc!r}); sleeping {wait}s", file=sys.stderr)
            time.sleep(wait)
    return {}


def fetch_labels(qids: list[str], cache: dict, refresh: bool = False) -> None:
    """For each Q-ID, populate cache[qid] = { lang: label, ... } across our
    target languages. Stores empty dict if Wikidata has no entity."""
    missing = [q for q in qids if refresh or q not in cache]
    if not missing:
        return
    print(f"  fetching labels for {len(missing):,} Q-IDs (batch={BATCH})")
    for i in range(0, len(missing), BATCH):
        batch = missing[i : i + BATCH]
        params = {
            "action": "wbgetentities",
            "format": "json",
            "ids": "|".join(batch),
            "props": "labels",
            "languages": "|".join(TARGET_LANGS + ["en"]),
        }
        try:
            payload = _get_json(WD_API, params)
        except Exception as exc:
            print(f"  batch failed: {exc!r}", file=sys.stderr)
            time.sleep(2)
            continue
        entities = payload.get("entities") or {}
        for qid in batch:
            ent = entities.get(qid) or {}
            labels = ent.get("labels") or {}
            cache[qid] = {
                lang: (labels.get(lang) or {}).get("value", "")
                for lang in TARGET_LANGS + ["en"]
                if (labels.get(lang) or {}).get("value")
            }
        if i % (BATCH * 5) == 0:
            _save_cache(cache)
            print(f"    {i + len(batch)}/{len(missing)} processed")
        time.sleep(DELAY_S)
    _save_cache(cache)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0,
                    help="Process only the first N Q-ID islands (debug).")
    ap.add_argument("--refresh", action="store_true",
                    help="Bypass label cache (slow).")
    args = ap.parse_args()

    print(f"Loading {ISLANDS_PATH}…")
    with open(ISLANDS_PATH, encoding="utf-8") as f:
        islands = json.load(f)
    print(f"  {len(islands):,} islands loaded")

    BACKUP_PATH.write_text(json.dumps(islands, ensure_ascii=False, indent=2))
    print(f"  backup → {BACKUP_PATH.name}")

    qid_re = re.compile(r"^Q\d+$")
    with_qid = [i for i in islands if qid_re.match((i.get("wikidata") or "").strip())]
    if args.limit:
        with_qid = with_qid[: args.limit]
    print(f"  islands with Q-ID: {len(with_qid):,}")

    cache = _load_cache()
    qids = sorted({i["wikidata"].strip() for i in with_qid})
    fetch_labels(qids, cache, refresh=args.refresh)

    report = {
        "targets": len(with_qid),
        "filled_per_lang": {lang: 0 for lang in TARGET_LANGS},
        "islands_touched": 0,
        "no_useful_labels": 0,
    }

    for isl in with_qid:
        qid = isl["wikidata"].strip()
        labels = cache.get(qid) or {}
        en_norm = _ascii_lower(labels.get("en") or isl.get("name") or "")
        names = isl.setdefault("names", {})
        # Always keep an English name on file for completeness.
        if "en" not in names:
            names["en"] = isl.get("name", "") or labels.get("en", "")
        touched = False
        for lang in TARGET_LANGS:
            val = labels.get(lang) or ""
            if not val:
                continue
            if _ascii_lower(val) == en_norm:
                continue  # Wikidata fell back to English; ignore.
            if names.get(lang):
                continue  # never overwrite.
            names[lang] = val
            report["filled_per_lang"][lang] = report["filled_per_lang"].get(lang, 0) + 1
            touched = True
        if touched:
            report["islands_touched"] += 1
        elif not any(names.get(l) for l in TARGET_LANGS):
            report["no_useful_labels"] += 1

    _atomic_write(ISLANDS_PATH, islands)
    _atomic_write(REPORT_PATH, report)
    print(f"\nIslands touched: {report['islands_touched']:,}")
    print(f"Islands with no useful labels: {report['no_useful_labels']:,}")
    print("Filled per language:")
    for lang, n in sorted(report["filled_per_lang"].items(), key=lambda x: -x[1]):
        print(f"  {lang}: {n:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
