#!/usr/bin/env bash
# Discovery apply → Wikipedia descriptions → image v5 → LLM (≤$30) → audits.
set -u
cd "$(dirname "$0")/.."
mkdir -p logs
TS="$(date -u +'%Y%m%dT%H%M%SZ')"
LOG="logs/autonomous-${TS}.log"

{
  echo "===== Autonomous run started $(date -u '+%F %T UTC') ====="
  echo "----- discovery pipeline (apply, include uncertain) -----"
  PYTHONUNBUFFERED=1 python3 scripts/discover_islands_pipeline.py --include-uncertain --apply
  echo "----- wikipedia descriptions -----"
  PYTHONUNBUFFERED=1 python3 scripts/enrich_descriptions_wikipedia.py --verbose
  echo "----- image enrichment v5 -----"
  PYTHONUNBUFFERED=1 python3 scripts/enrich_images_v5.py
  if [ -f .env.local ] || [ -n "${OPENAI_API_KEY:-}" ]; then
    echo "----- llm descriptions (cap \$18) -----"
    PYTHONUNBUFFERED=1 python3 scripts/enrich_descriptions_llm.py --max-cost-usd 18
    echo "----- llm tags (cap \$12) -----"
    PYTHONUNBUFFERED=1 python3 scripts/enrich_tags_llm.py --max-cost-usd 12
  else
    echo "----- skipping LLM (no OPENAI_API_KEY / .env.local) -----"
  fi
  echo "----- names enrichment -----"
  PYTHONUNBUFFERED=1 python3 scripts/enrich_names.py || true
  echo "----- audits -----"
  PYTHONUNBUFFERED=1 python3 scripts/audit_duplicates.py
  PYTHONUNBUFFERED=1 python3 scripts/audit_coordinates.py
  PYTHONUNBUFFERED=1 python3 scripts/audit_broken_links.py --concurrency 6
  if [ -x scripts/apply_enrichments.sh ]; then
    echo "----- staged enrichments apply -----"
    bash scripts/apply_enrichments.sh --yes || true
  fi
  echo "===== Autonomous run finished $(date -u '+%F %T UTC') ====="
} 2>&1 | tee -a "${LOG}"
