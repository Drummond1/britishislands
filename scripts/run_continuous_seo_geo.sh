#!/usr/bin/env bash
# Continuous SEO + GEO improvement loop for Find My Island.
#
# Unlike run_overnight_seo_geo.sh (fixed OVERNIGHT_HOURS window), this runs
# until stopped. It follows docs/SEO-GEO-STRATEGY.md while respecting the
# project decision: do NOT noindex/deindex Tier C atlas pages.
#
# Strategy-aligned rotation (per cycle):
#   0 descriptions — Wikipedia/multilang leads (entity facts / GEO answers)
#   1 photos       — OG images for crawlers + social
#   2 featured     — featured strip + discovery topics + flagship priority
#   3 authority    — regenerate landings/hubs/trust/sitemaps + GEO benchmark stub
#   4 gsc          — GSC-driven priority enrichment (when snapshot present)
#
# Start (detached recommended):
#   nohup bash scripts/run_continuous_seo_geo.sh --loop >> logs/continuous-seo-geo.out 2>&1 &
#
# One cycle:
#   bash scripts/run_continuous_seo_geo.sh
#
# Stop cleanly:
#   touch data/.continuous_seo_geo.stop
#   # or: kill "$(cat data/.continuous_seo_geo.pid)"
#
# Env:
#   SEO_GEO_SLEEP_SEC=2700          # default 45 min between cycles
#   SEO_GEO_DESC_LIMIT=150
#   SEO_GEO_PHOTO_LIMIT=150
#   SEO_GEO_CONTINUOUS_PUSH=1       # auto commit+push on coverage gains
#   IOB_SITE_ORIGIN=https://www.findmyisland.com
#   SEO_GEO_MAX_CYCLES=0            # 0 = unlimited; >0 stops after N cycles
#   SEO_GEO_MAX_HOURS=0             # 0 = unlimited; >0 stops after wall clock
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

LOOP=0
for arg in "$@"; do
  case "$arg" in
    --loop) LOOP=1 ;;
  esac
done

LOCK="$ROOT/data/.continuous_seo_geo.lock"
PIDFILE="$ROOT/data/.continuous_seo_geo.pid"
STOPFILE="$ROOT/data/.continuous_seo_geo.stop"
STATE="$ROOT/data/.continuous_seo_geo_state.json"
HISTORY="$ROOT/data/seo_geo_continuous_history.jsonl"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR" "$ROOT/data"

SLEEP_SEC="${SEO_GEO_SLEEP_SEC:-2700}"
DESC_LIMIT="${SEO_GEO_DESC_LIMIT:-150}"
PHOTO_LIMIT="${SEO_GEO_PHOTO_LIMIT:-150}"
AUTO_PUSH="${SEO_GEO_CONTINUOUS_PUSH:-${SEO_GEO_OVERNIGHT_PUSH:-1}}"
SITE_ORIGIN="${IOB_SITE_ORIGIN:-https://www.findmyisland.com}"
MAX_CYCLES="${SEO_GEO_MAX_CYCLES:-0}"
MAX_HOURS="${SEO_GEO_MAX_HOURS:-0}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$LOG_DIR/continuous-seo-geo-${STAMP}.log"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$LOG"; }

should_stop() {
  if [[ -f "$STOPFILE" ]]; then
    return 0
  fi
  return 1
}

if [[ -f "$LOCK" ]]; then
  age=$(( $(date +%s) - $(stat -f %m "$LOCK" 2>/dev/null || stat -c %Y "$LOCK") ))
  if (( age < 7200 )); then
    log "Abort: continuous SEO lock held (age ${age}s): $LOCK"
    exit 1
  fi
  log "Stale continuous lock (${age}s) — removing"
  rm -f "$LOCK"
fi

if [[ "$LOOP" -eq 1 && -f "$STOPFILE" ]]; then
  log "Abort: stop file present ($STOPFILE). Remove it to re-arm the continuous loop."
  exit 1
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
        || -f "$ROOT/data/.overnight_seo_geo.lock" \
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
  'mode': 'continuous',
}
pathlib.Path('$HISTORY').open('a').write(json.dumps(row) + '\n')
"
}

write_state() {
  local cycle="$1" phase="$2" avg="$3" both="$4" desc="$5" photo="$6" status="$7"
  python3 -c "
import json, pathlib, datetime
p = pathlib.Path('$STATE')
state = json.loads(p.read_text()) if p.exists() else {}
state.update({
  'mode': 'continuous',
  'status': '$status',
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
  'sleepSec': int('$SLEEP_SEC'),
  'strategyDoc': 'docs/SEO-GEO-STRATEGY.md',
  'policy': 'improve-without-deindexing',
})
if '$status' == 'stopped':
    state['stoppedUtc'] = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
else:
    state.pop('stoppedUtc', None)
    state.pop('finishedUtc', None)
p.write_text(json.dumps(state, indent=2) + '\n')
"
}

maybe_push() {
  local avg_b="$1" desc_b="$2" photo_b="$3" avg_a="$4" desc_a="$5" photo_a="$6"
  if [[ "$AUTO_PUSH" != "1" ]]; then
    log "Auto-push off (SEO_GEO_CONTINUOUS_PUSH!=1)"
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
    data/seo_path_by_id.json \
    data/seo_geo_coverage_report.json \
    data/seo_geo_priority_queue.json \
    data/featured_islands.json \
    data/discovery_topics.json \
    data/description_enrichment_report.json \
    data/flagship_editorial_coverage.json \
    data/geo_prompt_benchmark_latest.json \
    about/ methodology/ editorial-policy/ corrections/ sources-licensing/ contact/ dataset/ collections/ \
    llms.txt robots.txt sitemap.xml sitemap-*.xml \
    index.html landing.css ferries/ \
    docs/STATE.md docs/SESSION-LOG.md docs/QUEUE.md \
    2>>"$LOG" || true
  git add -f data/shards/*.json 2>>"$LOG" || true
  if git diff --cached --quiet 2>/dev/null; then
    log "Nothing staged to push"
    return 0
  fi
  git commit -m "$(cat <<EOF
Continuous SEO/GEO: avg ${avg_b}→${avg_a}, desc ${desc_b}→${desc_a}, photo ${photo_b}→${photo_a}.

Autonomous continuous cycle (strategy-aligned, no deindex) regenerated coverage and landings.
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
  log "=== Extra: multilang + sitelink description pass (flagship-first queues) ==="
  python3 scripts/build_description_priority_queue.py >>"$LOG" 2>&1 || true
  python3 scripts/enrich_descriptions_wikipedia.py \
    --queue-file data/description_priority_queue.json \
    --limit "$DESC_LIMIT" \
    --multilang \
    --include-exhausted \
    --checkpoint 25 >>"$LOG" 2>&1 || true
  if [[ -f data/seo_geo_priority_queue.json ]]; then
    python3 scripts/enrich_descriptions_wikipedia.py \
      --queue-file data/seo_geo_priority_queue.json \
      --limit "$(( DESC_LIMIT / 2 ))" \
      --multilang \
      --include-exhausted \
      --checkpoint 20 >>"$LOG" 2>&1 || true
  fi
}

run_extra_photos() {
  log "=== Extra: photo-gap staging (named islands only) ==="
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

audit_flagship_editorial() {
  log "=== Authority: flagship editorial coverage audit ==="
  python3 - <<'PY' >>"$LOG" 2>&1 || true
import json
from pathlib import Path

islands = {i["id"]: i for i in json.loads(Path("data/islands.json").read_text()) if i.get("id")}
curated = {c.get("id") for c in json.loads(Path("data/curated.json").read_text()) if c.get("id")}
featured = set()
fp = Path("data/featured_islands.json")
if fp.exists():
    raw = json.loads(fp.read_text())
    if isinstance(raw, list):
        for x in raw:
            if isinstance(x, dict) and x.get("id"):
                featured.add(str(x["id"]))
            elif isinstance(x, str):
                featured.add(x)
    elif isinstance(raw, dict):
        featured = {str(x) for x in (raw.get("ids") or [])}

sections = ("geography", "history", "transport", "accommodation", "wildlife", "geology")
rows = []
for iid in sorted(curated | featured):
    isl = islands.get(iid)
    if not isl:
        continue
    present = [k for k in sections if str(isl.get(k) or "").strip()]
    rows.append({
        "id": iid,
        "name": isl.get("name"),
        "hasShortDescription": bool(str(isl.get("shortDescription") or "").strip()),
        "hasPhoto": bool(isl.get("images") or isl.get("image")),
        "sectionCount": len(present),
        "sections": present,
        "completeFour": all(str(isl.get(k) or "").strip() for k in ("geography", "history", "transport", "accommodation")),
    })

complete = sum(1 for r in rows if r["completeFour"])
with_desc = sum(1 for r in rows if r["hasShortDescription"])
with_photo = sum(1 for r in rows if r["hasPhoto"])
out = {
    "schemaVersion": 1,
    "policy": "Tier C remains indexable (no deindex in this loop)",
    "flagshipCount": len(rows),
    "completeFourEditorial": complete,
    "withDescription": with_desc,
    "withPhoto": with_photo,
    "rows": rows,
}
Path("data/flagship_editorial_coverage.json").write_text(json.dumps(out, indent=2) + "\n")
print(f"flagship {len(rows)} | completeFour={complete} desc={with_desc} photo={with_photo}")
PY
}

run_authority_phase() {
  log "=== Authority: regenerate SEO artifacts + GEO benchmark stub ==="
  audit_flagship_editorial
  python3 scripts/build_islands_index.py >>"$LOG" 2>&1 || true
  IOB_SITE_ORIGIN="$SITE_ORIGIN" python3 scripts/generate_seo_artifacts.py --landing-dir profiles >>"$LOG" 2>&1 || true
  python3 scripts/audit_seo_geo_coverage.py >>"$LOG" 2>&1 || true
  if [[ -f scripts/run_geo_prompt_benchmark.py ]]; then
    python3 scripts/run_geo_prompt_benchmark.py --assistant "continuous-loop" >>"$LOG" 2>&1 || true
  fi
  for path in /about/ /methodology/ /collections/ /collections/flagship-islands/ /islands/scotland/fair-isle/ /sitemap.xml /llms.txt; do
    code=$(curl -s -o /dev/null -w "%{http_code}" "$SITE_ORIGIN$path" || echo 000)
    log "Probe $path → HTTP $code"
  done
}

run_gsc_phase() {
  log "=== GSC: priority enrichment from Search Console snapshot ==="
  if [[ ! -f data/gsc_seo_snapshot.json ]]; then
    log "No gsc_seo_snapshot.json — falling back to seo_geo_improvement"
    SEO_GEO_DESC_LIMIT="$DESC_LIMIT" SEO_GEO_PHOTO_LIMIT="$PHOTO_LIMIT" \
      IOB_SITE_ORIGIN="$SITE_ORIGIN" \
      bash scripts/run_seo_geo_improvement.sh >>"$LOG" 2>&1 || true
    return 0
  fi
  if [[ -f scripts/run_gsc_driven_seo.sh ]]; then
    IOB_SITE_ORIGIN="$SITE_ORIGIN" bash scripts/run_gsc_driven_seo.sh >>"$LOG" 2>&1 || true
  else
    SEO_GEO_DESC_LIMIT="$DESC_LIMIT" SEO_GEO_PHOTO_LIMIT="$PHOTO_LIMIT" \
      IOB_SITE_ORIGIN="$SITE_ORIGIN" \
      bash scripts/run_seo_geo_improvement.sh >>"$LOG" 2>&1 || true
  fi
}

run_one_cycle() {
  local cycle="$1"
  local phase_idx=$(( (cycle - 1) % 5 ))
  local phase
  case "$phase_idx" in
    0) phase="descriptions" ;;
    1) phase="photos" ;;
    2) phase="featured-flagship" ;;
    3) phase="authority-artifacts" ;;
    4) phase="gsc-priority" ;;
  esac

  log "=== Continuous SEO/GEO cycle $cycle ($phase) ==="
  log "Policy: improve coverage + landings; do NOT deindex Tier C pages"
  wait_for_writers || return 1

  local before
  before="$(read_metrics)"
  local avg_b both_b desc_b photo_b bothn_b
  IFS=$'\t' read -r avg_b both_b desc_b photo_b bothn_b <<<"$before"
  log "Baseline avg=$avg_b both%=$both_b desc=$desc_b photo=$photo_b"

  case "$phase_idx" in
    0)
      SEO_GEO_DESC_LIMIT="$DESC_LIMIT" SEO_GEO_PHOTO_LIMIT="$PHOTO_LIMIT" \
        IOB_SITE_ORIGIN="$SITE_ORIGIN" \
        bash scripts/run_seo_geo_improvement.sh >>"$LOG" 2>&1 || log "seo_geo_improvement: non-zero"
      run_extra_descriptions
      ;;
    1)
      SEO_GEO_DESC_LIMIT="$DESC_LIMIT" SEO_GEO_PHOTO_LIMIT="$PHOTO_LIMIT" \
        IOB_SITE_ORIGIN="$SITE_ORIGIN" \
        bash scripts/run_seo_geo_improvement.sh >>"$LOG" 2>&1 || log "seo_geo_improvement: non-zero"
      run_extra_photos
      ;;
    2)
      SEO_GEO_DESC_LIMIT="$DESC_LIMIT" SEO_GEO_PHOTO_LIMIT="$PHOTO_LIMIT" \
        IOB_SITE_ORIGIN="$SITE_ORIGIN" \
        bash scripts/run_seo_geo_improvement.sh >>"$LOG" 2>&1 || log "seo_geo_improvement: non-zero"
      audit_flagship_editorial
      run_extra_descriptions
      ;;
    3)
      run_authority_phase
      ;;
    4)
      run_gsc_phase
      python3 scripts/build_islands_index.py >>"$LOG" 2>&1 || true
      IOB_SITE_ORIGIN="$SITE_ORIGIN" python3 scripts/generate_seo_artifacts.py --landing-dir profiles >>"$LOG" 2>&1 || true
      python3 scripts/audit_seo_geo_coverage.py >>"$LOG" 2>&1 || true
      ;;
  esac

  if [[ "$phase_idx" -ne 3 ]]; then
    log "--- rebuild publish artefacts ---"
    python3 scripts/build_islands_index.py >>"$LOG" 2>&1 || true
    IOB_SITE_ORIGIN="$SITE_ORIGIN" python3 scripts/generate_seo_artifacts.py --landing-dir profiles >>"$LOG" 2>&1 || true
    python3 scripts/audit_seo_geo_coverage.py >>"$LOG" 2>&1 || true
  fi

  local after
  after="$(read_metrics)"
  local avg_a both_a desc_a photo_a bothn_a
  IFS=$'\t' read -r avg_a both_a desc_a photo_a bothn_a <<<"$after"
  log "After avg=$avg_a both%=$both_a desc=$desc_a photo=$photo_a"

  append_history "$cycle" "$phase" "$avg_a" "$both_a" "$desc_a" "$photo_a" "$bothn_a"
  write_state "$cycle" "$phase" "$avg_a" "$both_a" "$desc_a" "$photo_a" "running"

  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" "$SITE_ORIGIN/islands/scotland/" || echo 000)
  log "Live /islands/scotland/ → HTTP $code"

  maybe_push "$avg_b" "$desc_b" "$photo_b" "$avg_a" "$desc_a" "$photo_a"
  log "=== Cycle $cycle done ==="
}

# --- main ---
log "Continuous SEO/GEO start (loop=$LOOP sleep=${SLEEP_SEC}s push=$AUTO_PUSH maxCycles=$MAX_CYCLES maxHours=$MAX_HOURS)"
log "Strategy: docs/SEO-GEO-STRATEGY.md | Policy: no deindex"
log "PID $$ log=$LOG"
log "Stop with: touch data/.continuous_seo_geo.stop"

CYCLE=0
if [[ -f "$STATE" ]]; then
  CYCLE=$(python3 -c "import json; print(json.load(open('$STATE')).get('cycle',0))" 2>/dev/null || echo 0)
fi

if [[ "$LOOP" -eq 0 ]]; then
  CYCLE=$((CYCLE + 1))
  run_one_cycle "$CYCLE"
  metrics="$(read_metrics)"
  IFS=$'\t' read -r avg both desc photo bothn <<<"$metrics"
  write_state "$CYCLE" "single" "$avg" "$both" "$desc" "$photo" "idle"
  exit 0
fi

START_EPOCH=$(date +%s)
END_EPOCH=0
if [[ "$MAX_HOURS" -gt 0 ]]; then
  END_EPOCH=$(( START_EPOCH + MAX_HOURS * 3600 ))
  log "Wall-clock limit: ${MAX_HOURS}h"
fi

while true; do
  if should_stop; then
    log "Stop file detected — exiting continuous loop after $CYCLE cycles"
    write_state "$CYCLE" "stop-file" 0 0 0 0 "stopped"
    rm -f "$STOPFILE"
    break
  fi
  if [[ "$MAX_CYCLES" -gt 0 && "$CYCLE" -ge "$MAX_CYCLES" ]]; then
    log "Reached SEO_GEO_MAX_CYCLES=$MAX_CYCLES — exiting"
    write_state "$CYCLE" "max-cycles" 0 0 0 0 "stopped"
    break
  fi
  if [[ "$END_EPOCH" -gt 0 && $(date +%s) -ge "$END_EPOCH" ]]; then
    log "Reached SEO_GEO_MAX_HOURS wall clock — exiting"
    write_state "$CYCLE" "max-hours" 0 0 0 0 "stopped"
    break
  fi

  CYCLE=$((CYCLE + 1))
  run_one_cycle "$CYCLE" || log "Cycle $CYCLE failed (continuing)"

  if should_stop; then
    log "Stop file detected after cycle — exiting"
    write_state "$CYCLE" "stop-file" 0 0 0 0 "stopped"
    rm -f "$STOPFILE"
    break
  fi
  if [[ "$MAX_CYCLES" -gt 0 && "$CYCLE" -ge "$MAX_CYCLES" ]]; then
    log "Reached SEO_GEO_MAX_CYCLES=$MAX_CYCLES — exiting"
    break
  fi
  if [[ "$END_EPOCH" -gt 0 && $(date +%s) -ge "$END_EPOCH" ]]; then
    log "Reached SEO_GEO_MAX_HOURS — exiting"
    break
  fi

  log "Sleeping ${SLEEP_SEC}s until next cycle (touch $STOPFILE to halt)"
  remaining=$SLEEP_SEC
  while (( remaining > 0 )); do
    if should_stop; then
      log "Stop file during sleep — exiting"
      write_state "$CYCLE" "stop-file" 0 0 0 0 "stopped"
      rm -f "$STOPFILE"
      exit 0
    fi
    chunk=60
    if (( chunk > remaining )); then chunk=$remaining; fi
    sleep "$chunk"
    remaining=$(( remaining - chunk ))
  done
done

log "Continuous SEO/GEO loop ended (cycles=$CYCLE)"
rm -f "$PIDFILE"
