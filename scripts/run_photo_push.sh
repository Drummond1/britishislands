#!/usr/bin/env bash
# Sequential photo push toward 6,000+ named atlas islands with verified photos.
# ONE writer at a time — never run in parallel with another enrichment script.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
LOCK="$ROOT/data/.photo_push.lock"
if [[ -f "$LOCK" ]]; then
  echo "Photo push already running (lock: $LOCK). Abort."
  exit 1
fi
trap 'rm -f "$LOCK"' EXIT
echo $$ >"$LOCK"

count_named_photos() {
  python3 -c "
import json
idx={r['id'] for r in json.load(open('data/islands_index.json'))['rows']}
n=sum(1 for i in json.load(open('data/islands.json')) if i.get('id') in idx and (i.get('images') or i.get('image')))
print(n)
"
}

TARGET=6000
echo "=== Photo push start $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "Named with photo: $(count_named_photos) / target $TARGET"

python3 scripts/build_image_priority_queue.py

echo "--- Phase 1: cache-only (high + geosearch name-match ≤500m) ---"
python3 scripts/adopt_photos_from_cache.py --named-only

echo "--- Phase 2: Wikidata P18 + Wikipedia pageimages ---"
python3 scripts/enrich_images_v5.py \
  --source p18 --named-only --min-confidence high \
  --queue-file data/image_priority_queue.json --no-backup --delay 2 || true

echo "--- Phase 3: OSM tags ---"
python3 scripts/enrich_images_v5.py \
  --source osm-tags --named-only --min-confidence high \
  --queue-file data/image_priority_queue.json --no-backup --delay 2 || true

echo "--- Phase 4: Commons text search (batched, polite) ---"
for batch in 1 2 3 4 5 6 7 8 9 10; do
  cur=$(count_named_photos)
  if (( cur >= TARGET )); then break; fi
  echo "  text-search batch $batch (current $cur)"
  python3 scripts/enrich_images_v5.py \
    --source text-search --named-only --min-confidence high \
    --limit 300 --delay 5 \
    --queue-file data/image_priority_queue.json --no-backup || true
  sleep 120
done

echo "--- Phase 5: verified geosearch (500m, name match, adoption cap) ---"
for batch in 1 2 3 4 5; do
  cur=$(count_named_photos)
  if (( cur >= TARGET )); then break; fi
  python3 scripts/enrich_images_geosearch_verified.py \
    --limit 100 --delay 4 || true
  sleep 120
done

echo "--- Verify + index ---"
python3 scripts/verify_island_images.py --min-confidence 90 || true
python3 scripts/build_islands_index.py

echo "=== Done $(date -u +%Y-%m-%dT%H:%M:%SZ): $(count_named_photos) named with photo ==="
