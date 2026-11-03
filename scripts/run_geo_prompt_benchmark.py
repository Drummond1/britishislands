#!/usr/bin/env python3
"""GEO prompt-benchmark templates and validated manual score imports.

Reads the stable prompt set, writes a dated archive, and refreshes latest.json.
This does not query assistants or fabricate answers. Missing scores stay null;
only completed answers with an explicit boolean enter each metric's denominator.
See docs/GEO-BENCHMARK.md for the score format and evidence procedure.

Usage:
  python3 scripts/run_geo_prompt_benchmark.py --assistant "ChatGPT" --model "…"
  python3 scripts/run_geo_prompt_benchmark.py --from-scores path/to/scores.json
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
PROMPTS = DATA / "geo_prompt_benchmark_prompts.json"
LATEST = DATA / "geo_prompt_benchmark_latest.json"
HISTORY_DIR = DATA / "geo_prompt_benchmark_runs"


def _load_json(path: Path):
    def unique_keys(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError(f"Duplicate JSON key: {key}")
            obj[key] = value
        return obj
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_keys)


def _text(value, label: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string or null")
    return value


def _validate_prompts(bundle: dict) -> list[dict]:
    if not isinstance(bundle, dict):
        raise ValueError("Prompt bundle must be an object")
    prompts = bundle.get("prompts") or []
    if not isinstance(prompts, list) or not prompts:
        raise ValueError("Prompt bundle must contain a non-empty prompts list")
    seen = set()
    for row in prompts:
        if not isinstance(row, dict):
            raise ValueError("Each prompt must be an object")
        pid = row.get("id")
        if not isinstance(pid, str) or not pid.strip():
            raise ValueError("Each prompt needs a non-empty string id")
        if pid in seen:
            raise ValueError(f"Duplicate prompt id: {pid}")
        seen.add(pid)
        if not isinstance(row.get("prompt"), str) or not row["prompt"].strip():
            raise ValueError(f"{pid}: prompt text must be a non-empty string")
    return prompts


def _score_rows(raw: dict, prompts: list[dict]) -> tuple[dict, dict]:
    """Accept legacy keyed scores, a scores wrapper, or an edited run payload."""
    if not isinstance(raw, dict):
        raise ValueError("Scores must be an object")
    if "scores" in raw and "results" in raw:
        raise ValueError("Supply either scores or results, not both")
    metadata = raw if "scores" in raw or "results" in raw else {}
    if "results" in raw:
        if not isinstance(raw["results"], list):
            raise ValueError("results must be a list")
        scored = {}
        for row in raw["results"]:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                raise ValueError("Each result needs a string id")
            pid = row["id"]
            if pid in scored:
                raise ValueError(f"Duplicate result id: {pid}")
            scored[pid] = row
    else:
        scored = raw.get("scores", raw)
        if not isinstance(scored, dict):
            raise ValueError("scores must be an object keyed by prompt id")
    known = {row["id"]: row for row in prompts}
    for pid, prior in scored.items():
        if pid not in known:
            raise ValueError(f"Unknown prompt id: {pid}")
        if not isinstance(prior, dict):
            raise ValueError(f"{pid}: score must be an object")
        if "id" in prior and prior["id"] != pid:
            raise ValueError(f"{pid}: score id disagrees with its key")
        if "prompt" in prior and prior["prompt"] != known[pid]["prompt"]:
            raise ValueError(f"{pid}: scored prompt text differs from the prompt set")
    return scored, metadata


def _result(row: dict, prior: dict, assistant: str, model: str) -> dict:
    pid = row["id"]
    scores = {}
    for key in ("findMyIslandCited", "answerCorrect"):
        value = prior.get(key)
        if value is not None and type(value) is not bool:
            raise ValueError(f"{pid}: {key} must be true, false or null")
        scores[key] = value
    # Infer old-format rows without interpreting a notes-only row as a failure.
    inferred = "completed" if any(v is not None for v in scores.values()) else "unrun"
    status = prior.get("status", inferred)
    if status not in ("completed", "failed", "unrun"):
        raise ValueError(f"{pid}: status must be completed, failed or unrun")
    if status != "completed" and any(v is not None for v in scores.values()):
        raise ValueError(f"{pid}: failed/unrun answers must have null scores")

    url = _text(prior.get("citedUrl"), f"{pid}: citedUrl").strip() or None
    if scores["findMyIslandCited"] is True:
        if not url:
            raise ValueError(f"{pid}: a site citation requires citedUrl")
        parsed = urlsplit(url)
        if (parsed.scheme not in ("http", "https")
                or parsed.hostname not in ("findmyisland.com", "www.findmyisland.com")
                or parsed.username or parsed.password or parsed.port is not None
                or any(char.isspace() for char in url)):
            raise ValueError(f"{pid}: citedUrl must be an absolute Find My Island URL")
    elif url:
        raise ValueError(f"{pid}: citedUrl requires findMyIslandCited=true")
    result = {
        "id": pid,
        "intent": row.get("intent"),
        "prompt": row["prompt"],
        "assistant": assistant or _text(prior.get("assistant"), f"{pid}: assistant"),
        "model": model or _text(prior.get("model"), f"{pid}: model"),
        "status": status,
        **scores,
        "citedUrl": url,
        "notes": _text(prior.get("notes"), f"{pid}: notes"),
    }
    # Optional evidence survives a score-import round trip; it is never invented.
    for key in ("answerEvidence", "observedAt", "searchMode", "country", "language",
                "failureReason"):
        if key in prior:
            result[key] = _text(prior[key], f"{pid}: {key}")
    if "freshChat" in prior:
        if prior["freshChat"] is not None and type(prior["freshChat"]) is not bool:
            raise ValueError(f"{pid}: freshChat must be true, false or null")
        result["freshChat"] = prior["freshChat"]
    return result


def _canonical_island_url(url: str) -> bool:
    parsed = urlsplit(url)
    return (
        parsed.scheme == "https"
        and parsed.netloc == "www.findmyisland.com"
        and re.fullmatch(r"/islands/[a-z0-9-]+/[a-z0-9-]+/", parsed.path) is not None
        and not parsed.query and not parsed.fragment
    )


def _rollup(results: list[dict]) -> dict:
    completed = [row for row in results if row["status"] == "completed"]
    citation_scored = [row for row in completed if row["findMyIslandCited"] is not None]
    accuracy_scored = [row for row in completed if row["answerCorrect"] is not None]
    cited = [row for row in citation_scored if row["findMyIslandCited"]]
    correct = sum(row["answerCorrect"] for row in accuracy_scored)
    canonical = sum(_canonical_island_url(row["citedUrl"]) for row in cited)
    urls = sorted({row["citedUrl"] for row in cited})
    return {
        "completedCount": len(completed),
        "failedCount": sum(row["status"] == "failed" for row in results),
        "unrunCount": sum(row["status"] == "unrun" for row in results),
        "citationScoredCount": len(citation_scored),
        "accuracyScoredCount": len(accuracy_scored),
        "fullyScoredCount": sum(row["findMyIslandCited"] is not None
                                and row["answerCorrect"] is not None for row in completed),
        "citationRate": round(len(cited) / len(citation_scored), 4) if citation_scored else None,
        "accuracyPassRate": round(correct / len(accuracy_scored), 4) if accuracy_scored else None,
        "canonicalIslandCitationShare": round(canonical / len(cited), 4) if cited else None,
        "citedCount": len(cited) if citation_scored else None,
        "correctCount": correct if accuracy_scored else None,
        "canonicalIslandCitedCount": canonical if citation_scored else None,
        "uniqueCitedUrlCount": len(urls) if citation_scored else None,
        "uniqueCitedUrls": urls,
    }


def build_run(bundle: dict, raw_scores: dict | None = None, *, assistant: str = "",
              model: str = "", now: datetime | None = None) -> dict:
    prompts = _validate_prompts(bundle)
    scored, metadata = _score_rows(raw_scores if raw_scores is not None else {}, prompts)
    defaults = {key: _text(metadata.get(key), key) for key in ("assistant", "model")}
    results = [_result(row, {**defaults, **scored.get(row["id"], {})}, assistant, model)
               for row in prompts]
    assistant = assistant or defaults["assistant"]
    model = model or defaults["model"]
    groups = sorted({(row["assistant"], row["model"]) for row in results})
    now = now or datetime.now(timezone.utc)
    return {
        "schemaVersion": 2,
        "runAt": now.isoformat().replace("+00:00", "Z"),
        "promptSetUpdated": bundle.get("updated"),
        "promptCount": len(results),
        "assistant": assistant,
        "model": model,
        "kpis": _rollup(results),
        "kpisByAssistant": [
            {"assistant": product, "model": label,
             "kpis": _rollup([row for row in results
                              if (row["assistant"], row["model"]) == (product, label)])}
            for product, label in groups
        ],
        "results": results,
        "instructions": (
            "This runner does not query assistants. Record actual answers and evidence, "
            "set status=completed/failed/unrun and score completed answers with explicit "
            "booleans. Null scores are excluded from their metric's denominator. "
            "Import keyed scores or an edited results payload with --from-scores."
        ),
    }


def write_run(payload: dict, *, history_dir: Path, latest: Path, now: datetime) -> Path:
    """Never replace an archive, even if two runs share a clock timestamp."""
    content = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    history_dir.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%dT%H%M%S%fZ")
    sequence = 0
    while True:
        suffix = f"_{sequence}" if sequence else ""
        hist = history_dir / f"geo_prompt_benchmark_{stamp}{suffix}.json"
        try:
            with hist.open("x", encoding="utf-8") as handle:
                handle.write(content)
            break
        except FileExistsError:
            sequence += 1
    latest.write_text(content, encoding="utf-8")
    return hist


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--assistant", default="", help="Assistant product name for this run")
    ap.add_argument("--model", default="", help="Model id/label for this run")
    ap.add_argument(
        "--from-scores", type=Path, default=None,
        help="JSON with legacy keyed scores, a scores object, or a full results payload",
    )
    args = ap.parse_args()
    now = datetime.now(timezone.utc)
    try:
        bundle = _load_json(PROMPTS)
        scored = _load_json(args.from_scores) if args.from_scores else None
        if args.from_scores and not isinstance(scored, dict):
            raise ValueError("Scores must be an object")
        payload = build_run(bundle, scored, assistant=args.assistant, model=args.model, now=now)
    except (ValueError, OSError) as exc:
        ap.error(str(exc))
    hist = write_run(payload, history_dir=HISTORY_DIR, latest=LATEST, now=now)
    print(f"Wrote {LATEST.relative_to(ROOT)} ({payload['promptCount']} prompts, "
          f"{payload['kpis']['fullyScoredCount']} fully scored)")
    print(f"Archive {hist.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
