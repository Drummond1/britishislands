#!/usr/bin/env bash
# Priority photo harvesters (P1–P5) → strict verify → merge → index.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
LOCK="$ROOT/data/.priority_photo_push.lock"
LOG="${PRIORITY_PHOTO_LOG:-$ROOT/logs/priority-photo-push-$(date -u +%Y%m%dT%H%M%SZ).log}"
mkdir -p "$ROOT/logs"

LIMIT="${PHOTO_PUSH_LIMIT:-200}"
DELAY="${PHOTO_PUSH_DELAY:-1.5}"

if [[ -f "$LOCK" ]]; then
  echo "Priority photo push locked ($LOCK)" | tee -a "$LOG"
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

START=$(count_named_photos)
log "=== Priority photo push start ==="
log "Named with photo: $START (limit/island=$LIMIT)"

# P1 Geograph native API
run_phase "P1 geograph-native" \
  python3 scripts/enrich_images_geograph_native.py --named-only --limit "$LIMIT" --delay "$DELAY"

# P2 Wikipedia embedded images
run_phase "P2 wikipedia-embedded" \
  python3 scripts/enrich_images_wikipedia_embedded.py --named-only --limit "$LIMIT" --delay 1.2

# P3 Flickr statutory (skipped if no API key)
run_phase "P3 flickr-statutory" \
  python3 scripts/enrich_images_flickr_statutory.py --named-only --limit "$LIMIT" --delay 2

# P4 Commons county categories
run_phase "P4 commons-county" \
  python3 scripts/enrich_images_commons_county.py --named-only --limit "$LIMIT" --delay "$DELAY"

# P5 Wikidata nearby P18
run_phase "P5 wd-nearby-p18" \
  python3 scripts/enrich_images_wd_nearby_p18.py --named-only --limit "$LIMIT" --delay 2.5

log "--- verify staged (strict) ---"
python3 scripts/verify_staged_photos_strict.py >>"$LOG" 2>&1 || true

log "--- merge staged ---"
python3 scripts/merge_staged_photo_adoptions.py --no-backup >>"$LOG" 2>&1 || true

log "--- rebuild index ---"
python3 scripts/build_islands_index.py >>"$LOG" 2>&1 || true

END=$(count_named_photos)
log "=== Done: $START -> $END (+$((END - START))) ==="
log "Log: $LOG"
