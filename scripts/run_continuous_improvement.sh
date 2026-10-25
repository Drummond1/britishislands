#!/usr/bin/env bash
# Continuous improvement cycle: enrichments first, then photo coverage.
# Safe to run on a loop — single-writer discipline via one global lock.
#
# Usage:
#   bash scripts/run_continuous_improvement.sh          # one cycle
#   bash scripts/run_continuous_improvement.sh --dry-run
#
# Recurring (from repo root):
#   while true; do
#     bash scripts/run_continuous_improvement.sh || true
#     sleep 2700
#   done
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
  esac
done

LOCK="$ROOT/data/.continuous_improvement.lock"
STATE="$ROOT/data/.continuous_improvement_state.json"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/continuous-improvement-$(date -u +%Y%m%dT%H%M%SZ).log"

if [[ -f "$LOCK" ]]; then
  echo "Continuous improvement already running (lock: $LOCK). Abort." | tee -a "$LOG"
  exit 1
fi
trap 'rm -f "$LOCK"' EXIT
echo $$ >"$LOCK"

log() { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$LOG"; }

count_named_photos() {
  python3 -c "
import json
idx={r['id'] for r in json.load(open('data/islands_index.json'))['rows']}
n=sum(1 for i in json.load(open('data/islands.json')) if i.get('id') in idx and (i.get('images') or i.get('image')))
print(n)
"
}

count_enrichment_fields() {
  python3 -c "
import json
islands=json.load(open('data/islands.json'))
keys=['hillsOn','lighthouses','wildlifeColonies','bedrockUnit','populationDetails','propertyListings']
for k in keys:
    n=sum(1 for i in islands if i.get(k))
    print(f'{k}:{n}')
"
}

read_cycle() {
  python3 -c "
import json, pathlib
p=pathlib.Path('$STATE')
print(json.load(open(p)).get('cycle',0) if p.exists() else 0)
" 2>/dev/null || echo 0
}

write_cycle() {
  local cycle="$1" photo_source="$2" photos="$3"
  python3 -c "
import json, pathlib, datetime
p=pathlib.Path('$STATE')
state=json.loads(p.read_text()) if p.exists() else {}
state.update({
  'cycle': int('$cycle'),
  'lastRunUtc': datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat(),
  'lastPhotoSource': '$photo_source',
  'namedWithPhoto': int('$photos'),
  'lastLog': '$LOG',
})
p.write_text(json.dumps(state, indent=2))
"
}

run_py() {
  local label="$1"
  shift
  log "--- $label ---"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "  [dry-run] would run: $*"
    return 0
  fi
  if "$@"; then
    log "  $label: ok"
    return 0
  fi
  log "  $label: exited non-zero (continuing)"
  return 0
}

# Rotate staging harvesters across cycles (P1–P5 priority, then legacy six).
PHOTO_SOURCES=(
  "geograph-native:python3 scripts/enrich_images_geograph_native.py --named-only --limit 200 --delay 1.5"
  "wikipedia-embedded:python3 scripts/enrich_images_wikipedia_embedded.py --named-only --limit 200 --delay 1.5"
  "flickr-statutory:python3 scripts/enrich_images_flickr_statutory.py --named-only --limit 200 --delay 2"
  "commons-county:python3 scripts/enrich_images_commons_county.py --named-only --limit 200 --delay 1.5"
  "wd-nearby-p18:python3 scripts/enrich_images_wd_nearby_p18.py --named-only --limit 200 --delay 2.5"
  "inaturalist:python3 scripts/enrich_images_inaturalist.py --named-only --limit 250 --delay 2"
  "commons-depicts-q:python3 scripts/enrich_images_commons_depicts_q.py --named-only --limit 300 --delay 2.5"
  "wikidata-depicts:python3 scripts/enrich_images_wikidata_depicts.py --named-only --limit 250 --delay 2.5 --no-sparql"
  "commons-archipelago:python3 scripts/enrich_images_commons_archipelago_sweep.py --named-only --delay 2"
  "openverse:python3 scripts/enrich_images_openverse.py --named-only --limit 250 --delay 2"
  "commons-regional:python3 scripts/enrich_images_commons_regional.py --named-only --limit 200"
)

CYCLE=$(( $(read_cycle) + 1 ))
PHOTO_IDX=$(( (CYCLE - 1) % ${#PHOTO_SOURCES[@]} ))
PHOTO_ENTRY="${PHOTO_SOURCES[$PHOTO_IDX]}"
PHOTO_SOURCE="${PHOTO_ENTRY%%:*}"
PHOTO_CMD="${PHOTO_ENTRY#*:}"

log "=== Continuous improvement cycle $CYCLE start $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
log "Photo harvester this cycle: $PHOTO_SOURCE"
START_PHOTOS=$(count_named_photos)
log "Named with photo: $START_PHOTOS / 7000 (target 6000)"
log "Enrichment coverage:"
count_enrichment_fields | while read -r line; do log "  $line"; done

# ── Phase 1: Enrichments (refresh caches → apply) ───────────────────────────
log "=== Phase 1: Enrichments ==="

if [[ ! -s data/cache_dobih.json ]]; then
  run_py "ingest hills (Wikidata fallback)" \
    python3 scripts/ingest_hills_dobih.py --fetch --commit --cache
else
  log "  cache_dobih.json present — skip hills fetch"
fi

if [[ ! -s data/cache_lighthouses.json ]]; then
  run_py "ingest lighthouses" \
    python3 scripts/ingest_lighthouses.py --fetch --commit --cache
fi

if [[ ! -s data/cache_wildlife.json ]]; then
  run_py "ingest wildlife" \
    python3 scripts/ingest_wildlife_colonies.py --fetch --commit --cache
fi

if [[ ! -s data/cache_bgs.json ]]; then
  run_py "ingest geology BGS" \
    python3 scripts/ingest_geology_bgs.py --fetch --commit --cache
fi

if [[ ! -s data/cache_census2022.json ]]; then
  run_py "ingest census 2022" \
    python3 scripts/ingest_census_2022.py --commit
fi

if [[ "$DRY_RUN" -eq 0 ]]; then
  log "--- apply enrichments ---"
  if bash scripts/apply_enrichments.sh --yes --force >>"$LOG" 2>&1; then
    log "  apply enrichments: ok"
  else
    log "  apply enrichments: exited non-zero (continuing)"
  fi
else
  log "  [dry-run] would run: bash scripts/apply_enrichments.sh --yes --force"
fi

# ── Phase 2: Photo coverage (stage → verify → merge → direct adopt) ─────────
log "=== Phase 2: Photo coverage ==="

run_py "build priority queue" python3 scripts/build_image_priority_queue.py

if [[ "$DRY_RUN" -eq 0 ]]; then
  log "--- staging harvester: $PHOTO_SOURCE ---"
  eval "$PHOTO_CMD" >>"$LOG" 2>&1 || log "  staging harvester exited non-zero"
else
  log "  [dry-run] would run: $PHOTO_CMD"
fi

run_py "verify staged (strict)" python3 scripts/verify_staged_photos_strict.py
run_py "merge staged adoptions" python3 scripts/merge_staged_photo_adoptions.py --no-backup

run_py "cache adopt" python3 scripts/adopt_photos_from_cache.py --named-only

run_py "v5 P18 (high)" \
  python3 scripts/enrich_images_v5.py \
    --source p18 --named-only --min-confidence high \
    --queue-file data/image_priority_queue.json --no-backup --delay 2 --limit 150

run_py "v5 OSM tags (high)" \
  python3 scripts/enrich_images_v5.py \
    --source osm-tags --named-only --min-confidence high \
    --queue-file data/image_priority_queue.json --no-backup --delay 2 --limit 150

if [[ "$DRY_RUN" -eq 0 ]]; then
  run_py "rebuild index" python3 scripts/build_islands_index.py
  run_py "verify island images" python3 scripts/verify_island_images.py || true
fi

END_PHOTOS=$(count_named_photos)
DELTA=$(( END_PHOTOS - START_PHOTOS ))
GAP=$(( 6000 - END_PHOTOS ))
if (( GAP < 0 )); then GAP=0; fi

write_cycle "$CYCLE" "$PHOTO_SOURCE" "$END_PHOTOS"

log "=== Cycle $CYCLE done $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
log "Photos: $START_PHOTOS -> $END_PHOTOS (+$DELTA); gap to 6000: $GAP"
log "Log: $LOG"
