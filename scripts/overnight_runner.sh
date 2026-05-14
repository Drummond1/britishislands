#!/usr/bin/env bash
# Run the prioritised overnight task chain.
#
# Order:
#   1. Wikipedia lead-extract sweep        (mutates islands.json, ~2-3h)
#   2. Photo enrichment v5                 (mutates islands.json, ~6-10h)
#   3. Duplicate-island sweep              (report only, ~seconds)
#   4. Coordinate sanity sweep             (report only, ~seconds)
#   5. Broken-link audit                   (report only, ~1h)
#
# All steps are idempotent and atomic.  Backups are written before each
# mutating step.  Logs are streamed to logs/overnight-*.log so the user
# can `tail -f` any of them in the morning.

set -u
cd "$(dirname "$0")/.."

LOGDIR="logs"
mkdir -p "$LOGDIR"
TS="$(date -u +'%Y%m%dT%H%M%SZ')"
SUMMARY="$LOGDIR/overnight-${TS}-summary.log"

echo "===== Overnight run started $(date -u '+%F %T UTC') =====" | tee -a "$SUMMARY"

step() {
  local name="$1"; shift
  local log="$LOGDIR/overnight-${TS}-${name}.log"
  echo
  echo "----- [$(date -u '+%F %T UTC')] starting: ${name}" | tee -a "$SUMMARY"
  echo "       command: $*" | tee -a "$SUMMARY"
  echo "       log:     ${log}" | tee -a "$SUMMARY"
  if PYTHONUNBUFFERED=1 "$@" >>"${log}" 2>&1; then
    echo "       status:  ok" | tee -a "$SUMMARY"
  else
    rc=$?
    echo "       status:  FAILED (rc=${rc}) — continuing with next step" | tee -a "$SUMMARY"
  fi
}

# --- 1. Wikipedia lead-extract sweep -----------------------------------------
step wp-descriptions python3 scripts/enrich_descriptions_wikipedia.py --verbose

# --- 2. Photo enrichment (v5) ------------------------------------------------
# v5 re-fetches P18 / OSM tags / Commons text-search / wide geosearch.
# Idempotent; will skip islands that already have an image.
step photos-v5 python3 scripts/enrich_images_v5.py

# --- 3. Quick reports --------------------------------------------------------
step duplicates  python3 scripts/audit_duplicates.py
step coordinates python3 scripts/audit_coordinates.py

# --- 4. Broken-link audit ----------------------------------------------------
step broken-links python3 scripts/audit_broken_links.py --concurrency 6

# --- 5. LLM enrichment (optional; requires OPENAI_API_KEY or .env.local) -----
if [ -f .env.local ] || [ -n "${OPENAI_API_KEY:-}" ]; then
  step llm-descriptions python3 scripts/enrich_descriptions_llm.py --max-cost-usd 6
  step llm-tags python3 scripts/enrich_tags_llm.py --max-cost-usd 4
else
  echo "----- [$(date -u '+%F %T UTC')] skipping LLM steps (no OPENAI_API_KEY)" | tee -a "$SUMMARY"
fi

echo
echo "===== Overnight run finished $(date -u '+%F %T UTC') =====" | tee -a "$SUMMARY"
echo "Summary log: ${SUMMARY}"
