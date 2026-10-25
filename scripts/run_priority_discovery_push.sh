#!/usr/bin/env bash
# New-island discovery harvesters → gap candidate JSON (no islands.json write).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
LOCK="$ROOT/data/.priority_discovery_push.lock"
LOG="${PRIORITY_DISCOVERY_LOG:-$ROOT/logs/priority-discovery-push-$(date -u +%Y%m%dT%H%M%SZ).log}"
mkdir -p "$ROOT/logs"

if [[ -f "$LOCK" ]]; then
  echo "Discovery push locked ($LOCK)" | tee -a "$LOG"
  exit 1
fi
trap 'rm -f "$LOCK"' EXIT
echo $$ >"$LOCK"

log() { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$LOG"; }

count_islands() {
  python3 -c "import json; print(len(json.load(open('data/islands.json'))))"
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

START=$(count_islands)
log "=== Priority discovery push start ==="
log "Atlas islands: $START"

# D1 — GeoNames ISL/ISLT gaps (#11)
run_phase "D1 geonames-gaps" python3 scripts/discover_geonames_gaps.py

# D2 — Wikipedia list {{coord}} gaps (#76)
run_phase "D2 wikipedia-coords" python3 scripts/discover_wikipedia_coord_lists.py

# D3 — OSM map scanner (named islands / seamark rocks not in atlas)
run_phase "D3 osm-map-scanner" python3 scripts/discover_islands_pipeline.py --stage=map_scanner

# D4 — Catalog scanner (Wikidata lists, DoBIH, optional Open Names)
run_phase "D4 catalog-scanner" python3 scripts/discover_islands_pipeline.py --stage=catalog_scanner

END=$(count_islands)
log "=== Done (candidates only; atlas still $END islands) ==="
log "Outputs: data/discovery/candidates_geonames.json,"
log "          data/discovery/candidates_wikipedia_coords.json,"
log "          data/discovery/candidates_scan.json / candidates_catalog.json"
log "Log: $LOG"
