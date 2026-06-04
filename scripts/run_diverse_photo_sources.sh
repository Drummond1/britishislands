#!/usr/bin/env bash
# Sequential diverse photo enrichment — ONE writer to islands.json.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
LOCK="$ROOT/data/.photo_push.lock"
LOG="${PHOTO_PUSH_LOG:-/tmp/diverse_photo_sources.log}"

if [[ -f "$LOCK" ]]; then
  echo "Locked ($LOCK). Another photo push may be running." | tee -a "$LOG"
  exit 1
fi
trap 'rm -f "$LOCK"' EXIT
echo $$ >"$LOCK"

count_named() {
  python3 -c "
import json
idx={r['id'] for r in json.load(open('data/islands_index.json'))['rows']}
n=sum(1 for i in json.load(open('data/islands.json')) if i.get('id') in idx and (i.get('images') or i.get('image')))
print(n)
"
}

log() { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$LOG"; }

log "=== Diverse photo sources start ==="
START=$(count_named)
log "Named with photo: $START"

run_phase() {
  local name="$1"
  shift
  log "--- $name ---"
  if "$@"; then
    log "$name done; count=$(count_named)"
  else
    log "$name exited non-zero (continuing)"
  fi
}

run_phase "cache adopt" python3 scripts/adopt_photos_from_cache.py --named-only

run_phase "geograph-on-commons (cache)" \
  python3 scripts/enrich_images_geograph_commons.py --named-only --cache-only

run_phase "wikidata P373" \
  python3 scripts/enrich_images_wikidata_p373.py --named-only

run_phase "multilang wiki/voyage" \
  python3 scripts/enrich_images_multilang_wiki.py --named-only --limit 600

run_phase "openverse (batch 1)" \
  python3 scripts/enrich_images_openverse.py --named-only --limit 200 --delay 2

run_phase "openverse (batch 2)" \
  python3 scripts/enrich_images_openverse.py --named-only --limit 200 --delay 2 || true

run_phase "v5 p18 high" \
  python3 scripts/enrich_images_v5.py --source p18 --named-only --min-confidence high \
    --queue-file data/image_priority_queue.json --no-backup --delay 2 || true

run_phase "v5 osm-tags high" \
  python3 scripts/enrich_images_v5.py --source osm-tags --named-only --min-confidence high \
    --queue-file data/image_priority_queue.json --no-backup --delay 2 || true

if [[ -n "${MAPILLARY_ACCESS_TOKEN:-${MAPILLARY_CLIENT_TOKEN:-}}" ]]; then
  run_phase "mapillary" \
    python3 scripts/enrich_images_mapillary.py --named-only --limit 80 --delay 1.5
else
  log "mapillary skipped (no MAPILLARY_ACCESS_TOKEN)"
fi

python3 scripts/build_islands_index.py 2>&1 | tee -a "$LOG"
python3 scripts/verify_island_images.py 2>&1 | tee -a "$LOG" || true

END=$(count_named)
log "=== Done: $START -> $END (+$((END - START))) ==="
