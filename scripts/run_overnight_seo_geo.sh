#!/usr/bin/env bash
# Overnight SEO + GEO improvement — time-boxed wrapper.
#
# Prefer the continuous loop for ongoing strategy execution:
#   bash scripts/run_continuous_seo_geo.sh --loop
#
# This overnight script remains for a fixed window (default 8 h):
#   bash scripts/run_overnight_seo_geo.sh --loop
#
# When SEO_GEO_USE_CONTINUOUS=1, --loop delegates to the continuous runner
# with SEO_GEO_MAX_HOURS=OVERNIGHT_HOURS (default 8).
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

LOOP=0
for arg in "$@"; do
  case "$arg" in
    --loop) LOOP=1 ;;
  esac
done

if [[ "${SEO_GEO_USE_CONTINUOUS:-0}" == "1" && "$LOOP" -eq 1 ]]; then
  export SEO_GEO_MAX_HOURS="${OVERNIGHT_HOURS:-8}"
  export SEO_GEO_SLEEP_SEC="${OVERNIGHT_SLEEP_SEC:-2700}"
  export SEO_GEO_CONTINUOUS_PUSH="${SEO_GEO_OVERNIGHT_PUSH:-1}"
  exec bash "$ROOT/scripts/run_continuous_seo_geo.sh" --loop
fi

# --- legacy overnight body continues below ---

LOCK="$ROOT/data/.overnight_seo_geo.lock"
PIDFILE="$ROOT/data/.overnight_seo_geo.pid"
STATE="$ROOT/data/.overnight_seo_geo_state.json"
HISTORY="$ROOT/data/seo_geo_overnight_history.jsonl"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR" "$ROOT/data"

HOURS="${OVERNIGHT_HOURS:-8}"
SLEEP_SEC="${OVERNIGHT_SLEEP_SEC:-2700}"
DESC_LIMIT="${SEO_GEO_DESC_LIMIT:-150}"
PHOTO_LIMIT="${SEO_GEO_PHOTO_LIMIT:-150}"
AUTO_PUSH="${SEO_GEO_OVERNIGHT_PUSH:-1}"
SITE_ORIGIN="${IOB_SITE_ORIGIN:-https://www.findmyisland.com}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$LOG_DIR/overnight-seo-geo-${STAMP}.log"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$LOG"; }

if [[ -f "$LOCK" ]]; then
  age=$(( $(date +%s) - $(stat -f %m "$LOCK" 2>/dev/null || stat -c %Y "$LOCK") ))
  if (( age < 7200 )); then
    log "Abort: overnight SEO lock held (age ${age}s): $LOCK"
    exit 1
  fi
  log "Stale overnight lock (${age}s) — removing"
  rm -f "$LOCK"
fi

echo $$ >"$PIDFILE"
echo "$$ $(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$LOCK"
cleanup() { rm -f "$LOCK"; }
trap cleanup EXIT

wait_for_writers() {
  local waited=0
  while [[ -f "$ROOT/data/.seo_geo_improvement.lock" \
        || -f "$ROOT/data/.continuous_improvement.lock" \
        || -f "$ROOT/data/.gsc_seo_improvement.lock" \
        || -f "$ROOT/data/.overnight_discovery_naming.lock" ]]; do
    log "Waiting for other islands.json writer… (${waited}s)"
    sleep 60
    waited=$((waited + 60))
    if [[ "$waited" -gt 3600 ]]; then
      log "Gave up waiting for writer locks after 1h"
      return 1
    fi
  done
  return 0
}

read_metrics() {
  python3 - <<'PY'
import json
from pathlib import Path
r = {}
p = Path("data/seo_geo_coverage_report.json")
if p.exists():
    r = json.loads(p.read_text())
print(
    f"{r.get('averageScore', 0)}\t{r.get('pctBoth', 0)}\t"
    f"{r.get('withDescription', 0)}\t{r.get('withPhoto', 0)}\t"
    f"{r.get('withDescriptionAndPhoto', 0)}"
)
PY
}

append_history() {
  local cycle="$1" phase="$2" avg="$3" both="$4" desc="$5" photo="$6" bothn="$7"
  python3 -c "
import json, pathlib, datetime
row = {
  'at': datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat(),
  'cycle': int('$cycle'),
  'phase': '$phase',
  'averageScore': float('$avg'),
  'pctBoth': float('$both'),
  'withDescription': int('$desc'),
  'withPhoto': int('$photo'),
  'withDescriptionAndPhoto': int('$bothn'),
  'log': '$LOG',
}
pathlib.Path('$HISTORY').open('a').write(json.dumps(row) + '\n')
"
}

write_state() {
  local cycle="$1" phase="$2" avg="$3" both="$4" desc="$5" photo="$6"
  python3 -c "
import json, pathlib, datetime
p = pathlib.Path('$STATE')
state = json.loads(p.read_text()) if p.exists() else {}
state.update({
  'cycle': int('$cycle'),
  'lastPhase': '$phase',
  'averageScore': float('$avg'),
  'pctBoth': float('$both'),
  'withDescription': int('$desc'),
  'withPhoto': int('$photo'),
  'lastRunUtc': datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat(),
  'lastLog': '$LOG',
  'pid': $$,
  'siteOrigin': '$SITE_ORIGIN',
  'autoPush': bool(int('$AUTO_PUSH')),
})
p.write_text(json.dumps(state, indent=2) + '\n')
"
}

maybe_push() {
  local avg_b="$1" desc_b="$2" photo_b="$3" avg_a="$4" desc_a="$5" photo_a="$6"
  if [[ "$AUTO_PUSH" != "1" ]]; then
    log "Auto-push off (SEO_GEO_OVERNIGHT_PUSH!=1)"
    return 0
  fi
  python3 - <<PY
avg_b, desc_b, photo_b = float("$avg_b"), int("$desc_b"), int("$photo_b")
avg_a, desc_a, photo_a = float("$avg_a"), int("$desc_a"), int("$photo_a")
improved = (avg_a > avg_b + 0.01) or (desc_a > desc_b) or (photo_a > photo_b)
raise SystemExit(0 if improved else 1)
PY
  if [[ $? -ne 0 ]]; then
    log "No material score/coverage gain — skip push"
    return 0
  fi
  log "Material gain detected — committing + pushing for Pages deploy"
  git add \
    data/islands.json \
    data/islands_index.json \
    data/islands_unnamed_index.json \
    data/shards/ \
    data/seo_path_by_id.json \
    data/seo_geo_coverage_report.json \
    data/seo_geo_priority_queue.json \
    data/featured_islands.json \
    data/discovery_topics.json \
    data/description_enrichment_report.json \
    llms.txt robots.txt sitemap.xml \
    index.html ferries/ \
    docs/STATE.md docs/SESSION-LOG.md docs/QUEUE.md \
    2>>"$LOG" || true
  # force-add shards if gitignored
  git add -f data/shards/*.json 2>>"$LOG" || true
  if git diff --cached --quiet 2>/dev/null; then
    log "Nothing staged to push"
    return 0
  fi
  git commit -m "$(cat <<EOF
Overnight SEO/GEO: avg ${avg_b}→${avg_a}, desc ${desc_b}→${desc_a}, photo ${photo_b}→${photo_a}.

Autonomous overnight cycle regenerated coverage and static island landings.
EOF
)" >>"$LOG" 2>&1 || {
    log "Commit skipped/failed (continuing)"
    return 0
  }
  if git push origin HEAD >>"$LOG" 2>&1; then
    log "Pushed to origin — Pages will rebuild"
  else
    log "Push failed (non-fatal)"
  fi
}

run_extra_descriptions() {
  log "=== Extra: multilang + sitelink description pass ==="
  python3 scripts/build_description_priority_queue.py >>"$LOG" 2>&1 || true
  python3 scripts/enrich_descriptions_wikipedia.py \
    --queue-file data/description_priority_queue.json \
    --limit "$DESC_LIMIT" \
    --multilang \
    --include-exhausted \
    --checkpoint 25 >>"$LOG" 2>&1 || true
  python3 scripts/enrich_descriptions_wikipedia.py \
    --queue-file data/seo_geo_priority_queue.json \
    --limit "$(( DESC_LIMIT / 2 ))" \
    --multilang \
    --include-exhausted \
    --checkpoint 20 >>"$LOG" 2>&1 || true
}

run_extra_photos() {
  log "=== Extra: photo-gap staging ==="
  python3 - <<'PY' >>"$LOG" 2>&1 || true
import json
from pathlib import Path
islands = json.loads(Path("data/islands.json").read_text())
ids = []
for i in islands:
    if i.get("nameStatus") == "unknown" or "unnamed" in (i.get("name") or "").lower():
        continue
    if i.get("images") or i.get("image"):
        continue
    if not (i.get("wikidata") or i.get("wikipedia") or i.get("osmId")):
        continue
    ids.append(i["id"])
Path("data/seo_photo_gap_queue.json").write_text(
    json.dumps({"schemaVersion": 1, "ids": ids[:500]}, indent=2) + "\n"
)
print(f"photo gap queue {min(500, len(ids))} of {len(ids)}")
PY
  if [[ -f scripts/enrich_images_geograph_native.py ]]; then
    python3 scripts/enrich_images_geograph_native.py --named-only --limit "$PHOTO_LIMIT" --delay 1.5 >>"$LOG" 2>&1 || true
  fi
  if [[ -f scripts/enrich_images_wikipedia_embedded.py ]]; then
    python3 scripts/enrich_images_wikipedia_embedded.py --named-only --limit "$PHOTO_LIMIT" --delay 1.5 >>"$LOG" 2>&1 || true
  fi
  if [[ -f scripts/enrich_images_v5.py && -f data/seo_photo_gap_queue.json ]]; then
    python3 scripts/enrich_images_v5.py \
      --source p18 --named-only --min-confidence high \
      --queue-file data/seo_photo_gap_queue.json \
      --no-backup --delay 1.5 --limit "$PHOTO_LIMIT" >>"$LOG" 2>&1 || true
  fi
  if [[ -f scripts/verify_staged_photos_strict.py ]]; then
    python3 scripts/verify_staged_photos_strict.py >>"$LOG" 2>&1 || true
  fi
  if [[ -f scripts/merge_staged_photo_adoptions.py ]]; then
    python3 scripts/merge_staged_photo_adoptions.py --no-backup >>"$LOG" 2>&1 || true
  fi
}

run_one_cycle() {
  local cycle="$1"
  local phase_idx=$(( (cycle - 1) % 3 ))
  local phase
  case "$phase_idx" in
    0) phase="seo-rotate+descriptions" ;;
    1) phase="seo-rotate+photos" ;;
    2) phase="seo-rotate+featured-extra" ;;
  esac

  log "=== Overnight SEO/GEO cycle $cycle ($phase) ==="
  wait_for_writers || return 1

  local before
  before="$(read_metrics)"
  local avg_b both_b desc_b photo_b bothn_b
  IFS=$'\t' read -r avg_b both_b desc_b photo_b bothn_b <<<"$before"
  log "Baseline avg=$avg_b both%=$both_b desc=$desc_b photo=$photo_b"

  # Core rotating cycle (handles its own lock)
  SEO_GEO_DESC_LIMIT="$DESC_LIMIT" SEO_GEO_PHOTO_LIMIT="$PHOTO_LIMIT" \
    IOB_SITE_ORIGIN="$SITE_ORIGIN" \
    bash scripts/run_seo_geo_improvement.sh >>"$LOG" 2>&1 || log "seo_geo_improvement: non-zero"

  case "$phase_idx" in
    0) run_extra_descriptions ;;
    1) run_extra_photos ;;
    2)
      run_extra_descriptions
      # Light featured refresh already inside seo script on some cycles
      ;;
  esac

  log "--- rebuild publish artefacts ---"
  python3 scripts/build_islands_index.py >>"$LOG" 2>&1 || true
  IOB_SITE_ORIGIN="$SITE_ORIGIN" python3 scripts/generate_seo_artifacts.py --landing-dir profiles >>"$LOG" 2>&1 || true
  python3 scripts/audit_seo_geo_coverage.py >>"$LOG" 2>&1 || true

  local after
  after="$(read_metrics)"
  local avg_a both_a desc_a photo_a bothn_a
  IFS=$'\t' read -r avg_a both_a desc_a photo_a bothn_a <<<"$after"
  log "After avg=$avg_a both%=$both_a desc=$desc_a photo=$photo_a"

  append_history "$cycle" "$phase" "$avg_a" "$both_a" "$desc_a" "$photo_a" "$bothn_a"
  write_state "$cycle" "$phase" "$avg_a" "$both_a" "$desc_a" "$photo_a"

  # Live probe (non-fatal)
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" "$SITE_ORIGIN/islands/scotland/" || echo 000)
  log "Live /islands/scotland/ → HTTP $code"

  maybe_push "$avg_b" "$desc_b" "$photo_b" "$avg_a" "$desc_a" "$photo_a"
  log "=== Cycle $cycle done ==="
}

# --- main ---
log "Overnight SEO/GEO start (loop=$LOOP hours=$HOURS sleep=${SLEEP_SEC}s push=$AUTO_PUSH)"
log "PID $$ log=$LOG"

CYCLE=0
if [[ -f "$STATE" ]]; then
  CYCLE=$(python3 -c "import json; print(json.load(open('$STATE')).get('cycle',0))" 2>/dev/null || echo 0)
fi

if [[ "$LOOP" -eq 0 ]]; then
  CYCLE=$((CYCLE + 1))
  run_one_cycle "$CYCLE"
  exit 0
fi

END=$(( $(date +%s) + HOURS * 3600 ))
while (( $(date +%s) < END )); do
  CYCLE=$((CYCLE + 1))
  run_one_cycle "$CYCLE" || log "Cycle $CYCLE failed (continuing)"
  remaining=$(( END - $(date +%s) ))
  if (( remaining <= 0 )); then
    break
  fi
  nap=$SLEEP_SEC
  if (( nap > remaining )); then
    nap=$remaining
  fi
  log "Sleeping ${nap}s until next cycle (remaining ~$(( remaining / 60 )) min)"
  sleep "$nap"
done

log "Overnight SEO/GEO finished after $CYCLE cycles"
python3 -c "
import json, pathlib
p=pathlib.Path('$STATE')
s=json.loads(p.read_text()) if p.exists() else {}
s['finishedUtc']=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).replace(microsecond=0).isoformat()
s['cyclesCompleted']=$CYCLE
p.write_text(json.dumps(s, indent=2)+'\n')
" 2>/dev/null || true
