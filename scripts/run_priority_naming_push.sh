#!/usr/bin/env bash
# Priority naming harvesters (top 5 of 100) → verify → merge → index.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
LOCK="$ROOT/data/.priority_naming_push.lock"
LOG="${PRIORITY_NAMING_LOG:-$ROOT/logs/priority-naming-push-$(date -u +%Y%m%dT%H%M%SZ).log}"
mkdir -p "$ROOT/logs"

LIMIT="${NAMING_PUSH_LIMIT:-0}"
OSM_LIMIT="${NAMING_OSM_LIMIT:-500}"

if [[ -f "$LOCK" ]]; then
  echo "Priority naming push locked ($LOCK)" | tee -a "$LOG"
  exit 1
fi
trap 'rm -f "$LOCK"' EXIT
echo $$ >"$LOCK"

log() { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$LOG"; }

count_unnamed() {
  python3 -c "
import json
n=sum(1 for i in json.load(open('data/islands.json')) if i.get('nameStatus')=='unknown')
print(n)
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

START=$(count_unnamed)
log "=== Priority naming push start ==="
log "Unnamed islands: $START"

# N1 OS Open Names spatial join (#16)
if [[ -s data/raw/os_opennames.csv ]]; then
  ARGS=(python3 scripts/name_unnamed_os_open_names.py)
  [[ "$LIMIT" != "0" ]] && ARGS+=(--limit "$LIMIT")
  run_phase "N1 os-open-names" "${ARGS[@]}"
else
  log "N1 os-open-names: skip (no data/raw/os_opennames.csv — run fetch_os_open_names.py)"
fi

# N2 Logainm OIL bulk (#31)
ARGS=(python3 scripts/name_unnamed_logainm_oil.py)
[[ "$LIMIT" != "0" ]] && ARGS+=(--limit "$LIMIT")
run_phase "N2 logainm-oil" "${ARGS[@]}"

# N3 OSM wikidata + alt-name sweep (#1, #2)
ARGS=(python3 scripts/name_unnamed_osm_tags.py)
[[ "$OSM_LIMIT" != "0" ]] && ARGS+=(--limit "$OSM_LIMIT")
run_phase "N3 osm-tags" "${ARGS[@]}"

# N4 Canmore / NHLE site names (#46, #49)
ARGS=(python3 scripts/name_unnamed_heritage.py)
[[ "$LIMIT" != "0" ]] && ARGS+=(--limit "$LIMIT")
run_phase "N4 heritage-canmore-nhle" "${ARGS[@]}"

# N5 ohsome OSM history (#3)
OHSOME_LIMIT="${NAMING_OHSOME_LIMIT:-100}"
ARGS=(python3 scripts/name_unnamed_ohsome.py --limit "$OHSOME_LIMIT")
run_phase "N5 ohsome-restored" "${ARGS[@]}"

# N7 GeoNames reverse spatial join
run_phase "N7 geonames-spatial" python3 scripts/name_unnamed_geonames.py

# N8 OSM nearby named nodes (sample)
run_phase "N8 osm-nearby" python3 scripts/name_unnamed_nearby_osm.py --limit "${NAMING_NEARBY_LIMIT:-200}"

# N9 property listing adjacent names
run_phase "N9 property-adjacent" python3 scripts/name_unnamed_property_adjacent.py

# N10 Commons photo title consensus
run_phase "N10 photo-titles" python3 scripts/name_unnamed_photo_titles.py

# N6 triangulation fusion (#99)
run_phase "N6 fusion-triangulation" python3 scripts/name_unnamed_fusion.py

log "--- verify staged names ---"
python3 scripts/verify_staged_names.py >>"$LOG" 2>&1 || true

log "--- merge staged names ---"
python3 scripts/merge_staged_name_proposals.py --no-backup >>"$LOG" 2>&1 || true

log "--- rebuild index ---"
python3 scripts/build_islands_index.py >>"$LOG" 2>&1 || true

END=$(count_unnamed)
log "=== Done: unnamed $START -> $END (-$((START - END))) ==="
log "Log: $LOG"
