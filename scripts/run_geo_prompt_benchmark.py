#!/usr/bin/env python3
"""
Weekly GEO prompt-benchmark scaffold.

Reads the stable prompt set, writes a dated run stub under data/, and refreshes
data/geo_prompt_benchmark_latest.json for trend comparison.

This does not call external LLM APIs. Score each prompt manually (or via a
future assistant harness) by filling cited/correct fields, then re-run with
--from-scores PATH if needed.

Usage:
  python3 scripts/run_geo_prompt_benchmark.py
  python3 scripts/run_geo_prompt_benchmark.py --assistant "ChatGPT" --model "gpt-5"
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
PROMPTS = DATA / "geo_prompt_benchmark_prompts.json"
LATEST = DATA / "geo_prompt_benchmark_latest.json"
HISTORY_DIR = DATA / "geo_prompt_benchmark_runs"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--assistant", default="", help="Assistant product name for this run")
    ap.add_argument("--model", default="", help="Model id/label for this run")
    ap.add_argument(
        "--from-scores",
        type=Path,
        default=None,
        help="Optional JSON file with per-prompt scores keyed by prompt id",
    )
    args = ap.parse_args()

    bundle = _load_json(PROMPTS)
    prompts = bundle.get("prompts") or []
    if not isinstance(prompts, list) or not prompts:
        raise SystemExit(f"No prompts in {PROMPTS}")

    scored: dict[str, dict] = {}
    if args.from_scores:
        raw = _load_json(args.from_scores)
        scored = raw.get("scores") if isinstance(raw.get("scores"), dict) else raw

    now = datetime.now(timezone.utc)
    day = now.strftime("%Y-%m-%d")
    results = []
    cited = 0
    correct = 0
    canonical = 0
    for row in prompts:
        pid = str(row.get("id") or "")
        prior = scored.get(pid) if isinstance(scored.get(pid), dict) else {}
        was_cited = bool(prior.get("findMyIslandCited"))
        was_correct = bool(prior.get("answerCorrect"))
        url = prior.get("citedUrl") or ""
        if was_cited:
            cited += 1
        if was_correct:
            correct += 1
        if isinstance(url, str) and "/islands/" in url:
            canonical += 1
        results.append(
            {
                "id": pid,
                "intent": row.get("intent"),
                "prompt": row.get("prompt"),
                "assistant": args.assistant or prior.get("assistant") or "",
                "model": args.model or prior.get("model") or "",
                "findMyIslandCited": was_cited if prior else None,
                "citedUrl": url or None,
                "answerCorrect": was_correct if prior else None,
                "notes": prior.get("notes") or "",
            }
        )

    n = len(results)
    payload = {
        "schemaVersion": 1,
        "runAt": now.isoformat().replace("+00:00", "Z"),
        "promptCount": n,
        "assistant": args.assistant,
        "model": args.model,
        "kpis": {
            "citationRate": round(cited / n, 4) if n and args.from_scores else None,
            "accuracyPassRate": round(correct / n, 4) if n and args.from_scores else None,
            "canonicalIslandCitationShare": round(canonical / n, 4)
            if n and args.from_scores
            else None,
            "citedCount": cited if args.from_scores else None,
            "correctCount": correct if args.from_scores else None,
        },
        "results": results,
        "instructions": (
            "Fill findMyIslandCited / citedUrl / answerCorrect per prompt, save as "
            "scores JSON, then re-run with --from-scores to refresh KPIs."
        ),
    }

    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    hist = HISTORY_DIR / f"geo_prompt_benchmark_{stamp}.json"
    hist.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    LATEST.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {LATEST.relative_to(ROOT)} ({n} prompts, run {day})")
    print(f"Archive {hist.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
