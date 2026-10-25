#!/usr/bin/env bash
# Overnight discovery + naming cycle (N7–N10, D5–D6 + legacy N3–N6).
# Confirm via verify → merge (names) and discovery verifier → apply (new islands).
#
# One cycle:
#   bash scripts/run_overnight_discovery_naming.sh
# All night (default ~8 h, 45 min between cycles):
#   bash scripts/run_overnight_discovery_naming.sh --loop
#
# Env:
#   OVERNIGHT_HOURS=8          loop duration (hours)
#   OVERNIGHT_SLEEP_SEC=2700   pause between cycles
#   NAMING_NEARBY_LIMIT=400    OSM nearby batch size per cycle
#   NAMING_OHSOME_LIMIT=80
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

LOOP=0
for arg in "$@"; do
  case "$arg" in
    --loop) LOOP=1 ;;
  esac
done

LOCK="$ROOT/data/.overnight_discovery_naming.lock"
STATE="$ROOT/data/.overnight_discovery_naming_state.json"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR" "$ROOT/data/discovery" "$ROOT/data/staging/name_proposals"

HOURS="${OVERNIGHT_HOURS:-8}"
SLEEP_SEC="${OVERNIGHT_SLEEP_SEC:-2700}"
NEARBY_LIMIT="${NAMING_NEARBY_LIMIT:-400}"
OHSOME_LIMIT="${NAMING_OHSOME_LIMIT:-80}"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$LOG"; }

wait_for_writers() {
  # Avoid colliding with SEO / continuous-improvement islands.json writers.
  local waited=0
  while [[ -f "$ROOT/data/.seo_geo_improvement.lock" \
        || -f "$ROOT/data/.continuous_improvement.lock" \
        || -f "$ROOT/data/.priority_naming_push.lock" \
        || -f "$ROOT/data/.priority_discovery_push.lock" \
        || -f "$ROOT/data/.gsc_seo_improvement.lock" ]]; do
    log "Waiting for other islands.json writer lock… (${waited}s)"
    sleep 60
    waited=$((waited + 60))
    if [[ "$waited" -gt 3600 ]]; then
      log "Gave up waiting for writer locks after 1h"
      return 1
    fi
  done
  return 0
}

count_unnamed() {
  python3 -c "
import json
print(sum(1 for i in json.load(open('data/islands.json')) if i.get('nameStatus')=='unknown'))
"
}

count_islands() {
  python3 -c "import json; print(len(json.load(open('data/islands.json'))))"
}

write_state() {
  local cycle="$1" unnamed="$2" islands="$3" phase="$4"
  python3 -c "
import json, pathlib, datetime
p=pathlib.Path('$STATE')
state=json.loads(p.read_text()) if p.exists() else {}
state.update({
  'cycle': int('$cycle'),
  'unnamed': int('$unnamed'),
  'islands': int('$islands'),
  'lastPhase': '$phase',
  'lastRunUtc': datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat(),
  'lastLog': '$LOG',
})
p.write_text(json.dumps(state, indent=2) + '\n')
"
}

run_phase() {
  local name="$1"
  shift
  log "--- $name ---"
  if "$@" >>"$LOG" 2>&1; then
    log "$name: ok"
  else
    log "$name: non-zero (continuing)"
  fi
}

run_one_cycle() {
  local cycle="$1"
  local nearby_offset=$(( (cycle - 1) * NEARBY_LIMIT ))

  if [[ -f "$LOCK" ]]; then
    local oldpid
    oldpid=$(cat "$LOCK" 2>/dev/null || true)
    if [[ -n "$oldpid" ]] && kill -0 "$oldpid" 2>/dev/null; then
      log "Cycle skipped — lock held by PID $oldpid"
      return 1
    fi
    rm -f "$LOCK"
  fi
  echo $$ >"$LOCK"
  trap 'rm -f "$LOCK"' RETURN

  wait_for_writers || return 1

  local start_u start_n
  start_u=$(count_unnamed)
  start_n=$(count_islands)
  log "=== Overnight discovery/naming cycle $cycle ==="
  log "Atlas $start_n islands; unnamed $start_u; nearby offset $nearby_offset"

  # --- Discovery (candidates only) ---
  run_phase "D5 osm-freetext" python3 scripts/discover_osm_freetext.py
  run_phase "D6 seal-haulouts" python3 scripts/discover_seal_haulouts.py
  # D1/D2 are expensive; opt-in via OVERNIGHT_INCLUDE_CATALOG=1 (candidates already on disk)
  if [[ "${OVERNIGHT_INCLUDE_CATALOG:-0}" == "1" && $((cycle % 3)) -eq 1 ]]; then
    run_phase "D1 geonames-gaps" python3 scripts/discover_geonames_gaps.py --no-download
    run_phase "D2 wikipedia-coords" python3 scripts/discover_wikipedia_coord_lists.py
  fi

  # --- Naming harvesters ---
  run_phase "N7 geonames-spatial" python3 scripts/name_unnamed_geonames.py
  run_phase "N9 property-adjacent" python3 scripts/name_unnamed_property_adjacent.py
  run_phase "N10 photo-titles" python3 scripts/name_unnamed_photo_titles.py
  run_phase "N8 osm-nearby" python3 scripts/name_unnamed_nearby_osm.py \
    --limit "$NEARBY_LIMIT" --offset "$nearby_offset"

  # Legacy rotate
  case $((cycle % 3)) in
    1) run_phase "N3 osm-tags" python3 scripts/name_unnamed_osm_tags.py --limit 500 ;;
    2) run_phase "N4 heritage" python3 scripts/name_unnamed_heritage.py --limit 200 ;;
    0) run_phase "N5 ohsome" python3 scripts/name_unnamed_ohsome.py --limit "$OHSOME_LIMIT" ;;
  esac

  run_phase "N6 fusion" python3 scripts/name_unnamed_fusion.py

  wait_for_writers || return 1

  log "--- verify + merge names ---"
  run_phase "verify-names" python3 scripts/verify_staged_names.py
  run_phase "merge-names" python3 scripts/merge_staged_name_proposals.py --no-backup

  log "--- discovery verify + apply gaps ---"
  # Feed new candidate files into pipeline stages when present
  for cand in \
      data/discovery/candidates_geonames.json \
      data/discovery/candidates_wikipedia_coords.json \
      data/discovery/candidates_osm_freetext.json \
      data/discovery/candidates_seal_haulouts.json; do
    if [[ -s "$cand" ]]; then
      log "candidates present: $cand ($(python3 -c "import json;print(len(json.load(open('$cand'))))"))"
    fi
  done
  run_phase "apply-gaps" python3 scripts/apply_staged_discovery_gaps.py
  run_phase "pipeline-verifier" python3 scripts/discover_islands_pipeline.py --stage=source_verifier
  run_phase "pipeline-enricher" python3 scripts/discover_islands_pipeline.py --stage=enricher
  wait_for_writers || true
  run_phase "pipeline-apply" python3 scripts/discover_islands_pipeline.py --stage=site_update --apply

  run_phase "rebuild-index" python3 scripts/build_islands_index.py

  local end_u end_n
  end_u=$(count_unnamed)
  end_n=$(count_islands)
  log "=== Cycle $cycle done: islands ${start_n}->${end_n} (+$((end_n - start_n))); unnamed ${start_u}->${end_u} (-$((start_u - end_u))) ==="
  write_state "$cycle" "$end_u" "$end_n" "complete"
  rm -f "$LOCK"
  trap - RETURN
  return 0
}

# --- entry ---
TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$LOG_DIR/overnight-discovery-naming-${TS}.log"

if [[ "$LOOP" -eq 1 ]]; then
  END_EPOCH=$(( $(date +%s) + HOURS * 3600 ))
  CYCLE=$(python3 -c "
import json, pathlib
p=pathlib.Path('$STATE')
print(json.load(open(p)).get('cycle',0) if p.exists() else 0)
" 2>/dev/null || echo 0)
  log "Overnight LOOP armed for ${HOURS}h (sleep ${SLEEP_SEC}s); start cycle=$((CYCLE + 1))"
  while [[ $(date +%s) -lt $END_EPOCH ]]; do
    CYCLE=$((CYCLE + 1))
    run_one_cycle "$CYCLE" || true
    if [[ $(date +%s) -ge $END_EPOCH ]]; then
      break
    fi
    log "Sleeping ${SLEEP_SEC}s until next cycle…"
    sleep "$SLEEP_SEC"
  done
  log "Overnight LOOP finished after cycle $CYCLE"
else
  CYCLE=$(python3 -c "
import json, pathlib
p=pathlib.Path('$STATE')
print((json.load(open(p)).get('cycle',0) if p.exists() else 0) + 1)
" 2>/dev/null || echo 1)
  run_one_cycle "$CYCLE"
fi
