#!/usr/bin/env python3
"""Draft ``shortDescription`` with an LLM for islands still missing prose.

Only fills empty descriptions (never overwrites Wikipedia lead extracts
or existing text).  Grounded strictly in the island fact bundle from
``llm_common.island_facts``.

Usage::

    python3 scripts/enrich_descriptions_llm.py --limit 50
    python3 scripts/enrich_descriptions_llm.py --max-cost-usd 5
    python3 scripts/enrich_descriptions_llm.py --dry-run
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from llm_common import (
    DATA,
    OpenAIJsonClient,
    island_facts,
    load_json,
    save_json_atomic,
)

ISLANDS = DATA / "islands.json"
BACKUP = DATA / "islands.json.before-llmdesc"
REPORT = DATA / "description_llm_enrichment_report.json"
CACHE = DATA / "cache_llm_descriptions.json"

SYSTEM = (
    "You are an atlas editor for the islands of Britain and Ireland. "
    "Write 2-3 short sentences for the island card using ONLY the JSON facts. "
    "Do not invent history, wildlife, transport, or population. "
    "If facts are thin, say less rather than guessing. "
    "Return JSON: {\"description\": string}."
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--checkpoint", type=int, default=40)
    ap.add_argument("--max-cost-usd", type=float, default=8.0)
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    islands = load_json(ISLANDS, [])
    if not islands:
        sys.exit("islands.json missing/empty")
    cache = load_json(CACHE, {})

    candidates = [
        i
        for i, isl in enumerate(islands)
        if isinstance(isl, dict) and not (isl.get("shortDescription") or "").strip()
    ]
    print(f"candidates without shortDescription: {len(candidates)}")
    if args.limit:
        candidates = candidates[: args.limit]

    if not args.dry_run and not BACKUP.exists():
        BACKUP.write_text(json.dumps(islands, indent=2, ensure_ascii=False), encoding="utf-8")

    client = None if args.dry_run else OpenAIJsonClient(model=args.model)
    report = {
        "startedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "model": args.model,
        "candidates": len(candidates),
        "adopted": 0,
        "skippedCached": 0,
        "errors": 0,
        "samples": [],
    }
    adopted_since_flush = 0

    try:
        for n, idx in enumerate(candidates, 1):
            isl = islands[idx]
            iid = isl.get("id") or f"idx-{idx}"
            if iid in cache and cache[iid].get("description"):
                desc = cache[iid]["description"]
                report["skippedCached"] += 1
            else:
                if args.dry_run:
                    continue
                if client and client.cost_usd >= args.max_cost_usd:
                    print(f"! budget cap ${args.max_cost_usd:.2f} reached", flush=True)
                    break
                try:
                    parsed = client.complete_json(
                        SYSTEM,
                        "Island facts:\n" + json.dumps(island_facts(isl), ensure_ascii=False),
                        max_tokens=220,
                    )
                    desc = (parsed.get("description") or "").strip()
                except Exception as exc:
                    report["errors"] += 1
                    print(f"  [{n}/{len(candidates)}] ! {isl.get('name')}: {exc}", flush=True)
                    continue
                if not desc:
                    continue
                cache[iid] = {"description": desc}

            if args.dry_run:
                continue

            isl["shortDescription"] = desc
            isl["descriptionSource"] = f"llm-{args.model}"
            isl["descriptionConfidence"] = "draft"
            isl["descriptionAttribution"] = (
                "AI-drafted from atlas facts on record (review before treating as authoritative)."
            )
            isl["descriptionFetchedAt"] = dt.datetime.now(dt.timezone.utc).isoformat(
                timespec="seconds"
            )
            report["adopted"] += 1
            adopted_since_flush += 1
            if len(report["samples"]) < 20:
                report["samples"].append({"id": iid, "name": isl.get("name"), "description": desc})
            print(f"  [{n}/{len(candidates)}] ✓ {isl.get('name')}", flush=True)

            if adopted_since_flush >= args.checkpoint:
                save_json_atomic(ISLANDS, islands)
                save_json_atomic(CACHE, cache)
                save_json_atomic(REPORT, report)
                adopted_since_flush = 0
    finally:
        if not args.dry_run:
            save_json_atomic(ISLANDS, islands)
        save_json_atomic(CACHE, cache)
        report["finishedAt"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        if client:
            report["promptTokens"] = client.prompt_tokens
            report["completionTokens"] = client.completion_tokens
            report["costUsd"] = round(client.cost_usd, 4)
        save_json_atomic(REPORT, report)
        print(f"adopted={report['adopted']} errors={report['errors']} report→{REPORT.name}")


if __name__ == "__main__":
    main()
