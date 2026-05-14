#!/usr/bin/env python3
"""Shared helpers for offline LLM enrichment scripts."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ENV_LOCAL = ROOT / ".env.local"
TAG_VOCAB = DATA / "chat_tag_vocabulary.json"

UA = "isles-of-britain/0.7 (llm-enrichment; +https://github.com/local-atlas)"

# gpt-4o-mini list pricing (USD per 1M tokens) — used for budget guard.
OPENAI_PRICE_IN = 0.15
OPENAI_PRICE_OUT = 0.60


def load_env_local() -> None:
    if not ENV_LOCAL.exists():
        return
    for line in ENV_LOCAL.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = val


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json_atomic(path: Path, obj: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def load_tag_vocab() -> list[dict[str, Any]]:
    data = load_json(TAG_VOCAB, {"tags": []})
    return list(data.get("tags") or [])


def allowed_tag_ids() -> set[str]:
    return {t["id"] for t in load_tag_vocab() if t.get("id")}


def trim_text(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    if len(s) <= limit:
        return s
    return s[: limit - 1].rstrip() + "…"


def island_facts(island: dict[str, Any]) -> dict[str, Any]:
    """Compact, grounded fact bundle for LLM prompts."""
    names = island.get("names") if isinstance(island.get("names"), dict) else {}
    alt_names = [v for v in names.values() if isinstance(v, str) and v.strip()][:6]
    parent = island.get("parentWaterBody")
    parent_name = parent.get("name") if isinstance(parent, dict) else None
    facts: dict[str, Any] = {
        "id": island.get("id"),
        "name": island.get("name"),
        "nation": island.get("nation"),
        "type": island.get("type"),
        "subtype": island.get("subtype"),
        "archipelago": island.get("archipelago"),
        "parentWaterBody": parent_name,
        "lat": island.get("lat"),
        "lng": island.get("lng"),
        "areaKm2": island.get("areaKm2"),
        "areaConfidence": island.get("areaConfidence"),
        "highestPointM": island.get("highestPointM"),
        "highestPointName": island.get("highestPointName"),
        "population": island.get("population"),
        "tags": (island.get("tags") or [])[:20],
        "altNames": alt_names,
        "shortDescription": trim_text(island.get("shortDescription"), 480),
        "geography": trim_text(island.get("geography"), 340),
        "history": trim_text(island.get("history"), 340),
        "transport": trim_text(island.get("transport"), 340),
        "accommodation": trim_text(island.get("accommodation"), 240),
        "wikipedia": island.get("wikipedia"),
    }
    return {k: v for k, v in facts.items() if v not in (None, "", [], {})}


def estimate_cost_usd(prompt_tokens: int, completion_tokens: int) -> float:
    return (prompt_tokens / 1_000_000) * OPENAI_PRICE_IN + (
        completion_tokens / 1_000_000
    ) * OPENAI_PRICE_OUT


class OpenAIJsonClient:
    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0.35):
        load_env_local()
        self.api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not self.api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Export it or add it to .env.local."
            )
        self.model = model
        self.temperature = temperature
        self.prompt_tokens = 0
        self.completion_tokens = 0

    @property
    def cost_usd(self) -> float:
        return estimate_cost_usd(self.prompt_tokens, self.completion_tokens)

    def complete_json(self, system: str, user: str, max_tokens: int = 500) -> dict[str, Any]:
        body = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": UA,
            },
            method="POST",
        )
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=90) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504):
                    time.sleep((2 ** attempt) * 1.5)
                    continue
                detail = e.read().decode("utf-8", errors="replace")[:300]
                raise RuntimeError(f"OpenAI HTTP {e.code}: {detail}") from e
        else:
            raise RuntimeError("OpenAI request failed after retries")

        usage = payload.get("usage") or {}
        self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
        self.completion_tokens += int(usage.get("completion_tokens") or 0)
        raw = payload["choices"][0]["message"]["content"]
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", raw, re.S)
            if not m:
                raise
            return json.loads(m.group(0))
