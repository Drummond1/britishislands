#!/usr/bin/env python3
"""Assign controlled semantic tags with an LLM (additive only).

Tags must come from ``data/chat_tag_vocabulary.json``.  Evidence for each
adopted tag is stored in ``data/llm_tag_evidence.json`` for review.

Usage::

    python3 scripts/enrich_tags_llm.py --limit 100
    python3 scripts/enrich_tags_llm.py --max-cost-usd 3
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
    allowed_tag_ids,
    island_facts,
    load_json,
    load_tag_vocab,
    save_json_atomic,
)

ISLANDS = DATA / "islands.json"
BACKUP = DATA / "islands.json.before-llmtags"
REPORT = DATA / "tags_llm_enrichment_report.json"
CACHE = DATA / "cache_llm_tags.json"
EVIDENCE = DATA / "llm_tag_evidence.json"


def build_system_prompt() -> str:
    ids = sorted(allowed_tag_ids())
    return (
        "You classify islands for a British Isles atlas search engine. "
        "Choose tags ONLY from this allowlist:\n"
        + ", ".join(ids)
        + "\nPick 0-8 tags supported by the facts. "
        "Do not guess wildlife, access rules, or ferry service unless stated. "
        'Return JSON: {"tags": string[], "notes": string}.'
    )


def merge_tags(existing: list, new_tags: list[str]) -> list[str]:
    out = []
    seen = set()
    for t in (existing or []) + new_tags:
        if not isinstance(t, str):
            continue
        t = t.strip()
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--checkpoint", type=int, default=60)
    ap.add_argument("--max-cost-usd", type=float, default=6.0)
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only-missing", action="store_true",
                    help="skip islands that already carry any allowlisted tag")
    args = ap.parse_args()

    islands = load_json(ISLANDS, [])
    if not islands:
        sys.exit("islands.json missing/empty")
    cache = load_json(CACHE, {})
    evidence = load_json(EVIDENCE, {})
    allow = allowed_tag_ids()
    vocab = load_tag_vocab()

    candidates = []
    for idx, isl in enumerate(islands):
        if not isinstance(isl, dict):
            continue
        if args.only_missing:
            tags = set(isl.get("tags") or [])
            if tags & allow:
                continue
        candidates.append(idx)
    print(f"tag candidates: {len(candidates)} (allowlist size {len(allow)})")
    if args.limit:
        candidates = candidates[: args.limit]

    if not args.dry_run and not BACKUP.exists():
        BACKUP.write_text(json.dumps(islands, indent=2, ensure_ascii=False), encoding="utf-8")

    client = None if args.dry_run else OpenAIJsonClient(model=args.model, temperature=0.2)
    system = build_system_prompt()
    report = {
        "startedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "model": args.model,
        "vocabularyTags": len(vocab),
        "candidates": len(candidates),
        "updated": 0,
        "tagsAdded": 0,
        "errors": 0,
        "samples": [],
    }
    adopted_since_flush = 0

    try:
        for n, idx in enumerate(candidates, 1):
            isl = islands[idx]
            iid = isl.get("id") or f"idx-{idx}"
            if iid in cache:
                chosen = cache[iid].get("tags") or []
            else:
                if args.dry_run:
                    continue
                if client and client.cost_usd >= args.max_cost_usd:
                    print(f"! budget cap ${args.max_cost_usd:.2f} reached", flush=True)
                    break
                try:
                    parsed = client.complete_json(
                        system,
                        "Island facts:\n" + json.dumps(island_facts(isl), ensure_ascii=False),
                        max_tokens=180,
                    )
                except Exception as exc:
                    report["errors"] += 1
                    print(f"  [{n}/{len(candidates)}] ! {isl.get('name')}: {exc}", flush=True)
                    continue
                raw = parsed.get("tags") or []
                chosen = [t for t in raw if isinstance(t, str) and t in allow]
                cache[iid] = {"tags": chosen, "notes": parsed.get("notes") or ""}

            if args.dry_run:
                continue

            before = list(isl.get("tags") or [])
            after = merge_tags(before, chosen)
            added = [t for t in after if t not in before]
            if not added:
                continue
            isl["tags"] = after
            isl["tagsSource"] = f"llm-{args.model}"
            isl["tagsFetchedAt"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            evidence[iid] = {
                "name": isl.get("name"),
                "added": added,
                "notes": cache[iid].get("notes") or "",
                "fetchedAt": isl["tagsFetchedAt"],
            }
            report["updated"] += 1
            report["tagsAdded"] += len(added)
            adopted_since_flush += 1
            if len(report["samples"]) < 20:
                report["samples"].append({"id": iid, "name": isl.get("name"), "added": added})
            print(f"  [{n}/{len(candidates)}] ✓ {isl.get('name')}: +{', '.join(added)}", flush=True)

            if adopted_since_flush >= args.checkpoint:
                save_json_atomic(ISLANDS, islands)
                save_json_atomic(CACHE, cache)
                save_json_atomic(EVIDENCE, evidence)
                save_json_atomic(REPORT, report)
                adopted_since_flush = 0
    finally:
        if not args.dry_run:
            save_json_atomic(ISLANDS, islands)
        save_json_atomic(CACHE, cache)
        save_json_atomic(EVIDENCE, evidence)
        report["finishedAt"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        if client:
            report["promptTokens"] = client.prompt_tokens
            report["completionTokens"] = client.completion_tokens
            report["costUsd"] = round(client.cost_usd, 4)
        save_json_atomic(REPORT, report)
        print(
            f"updated={report['updated']} tagsAdded={report['tagsAdded']} "
            f"errors={report['errors']} report→{REPORT.name}"
        )


if __name__ == "__main__":
    main()
