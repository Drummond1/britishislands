#!/usr/bin/env bash
# Continuous SEO + GEO improvement cycle for findmyisland.com.
#
# Each cycle:
#   1. Audit SEO/GEO coverage → priority queue
#   2. Rotate one enrichment action (descriptions / OG photos / featured+topics)
#   3. Rebuild index + regenerate sitemap / robots / llms.txt / crawl links
#   4. Probe live SEO endpoints (non-fatal)
#
# Usage:
#   bash scripts/run_seo_geo_improvement.sh
#   bash scripts/run_seo_geo_improvement.sh --dry-run
#   SEO_GEO_DESC_LIMIT=80 SEO_GEO_PHOTO_LIMIT=100 bash scripts/run_seo_geo_improvement.sh
#
# Recurring (repo root):
#   while true; do
#     bash scripts/run_seo_geo_improvement.sh || true
#     sleep 3600
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

LOCK="$ROOT/data/.seo_geo_improvement.lock"
STATE="$ROOT/data/.seo_geo_improvement_state.json"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR" "$ROOT/data"
LOG="$LOG_DIR/seo-geo-improvement-$(date -u +%Y%m%dT%H%M%SZ).log"
SITE_ORIGIN="${IOB_SITE_ORIGIN:-https://www.findmyisland.com}"
DESC_LIMIT="${SEO_GEO_DESC_LIMIT:-60}"
PHOTO_LIMIT="${SEO_GEO_PHOTO_LIMIT:-80}"

if [[ -f "$LOCK" ]]; then
  echo "SEO/GEO improvement already running (lock: $LOCK). Abort." | tee -a "$LOG"
  exit 1
fi
# Also avoid colliding with the photo continuous-improvement writer.
if [[ -f "$ROOT/data/.continuous_improvement.lock" ]]; then
  echo "Continuous improvement lock held — skipping SEO/GEO cycle to avoid dual writes." | tee -a "$LOG"
  exit 0
fi
trap 'rm -f "$LOCK"' EXIT
echo $$ >"$LOCK"

log() { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$LOG"; }

read_cycle() {
  python3 -c "
import json, pathlib
p=pathlib.Path('$STATE')
print(json.load(open(p)).get('cycle',0) if p.exists() else 0)
" 2>/dev/null || echo 0
}

write_state() {
  local cycle="$1" action="$2" avg="$3" both="$4"
  python3 -c "
import json, pathlib, datetime
p=pathlib.Path('$STATE')
state=json.loads(p.read_text()) if p.exists() else {}
state.update({
  'cycle': int('$cycle'),
  'lastRunUtc': datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat(),
  'lastAction': '$action',
  'averageScore': float('$avg') if '$avg' not in ('', 'None') else None,
  'pctBoth': float('$both') if '$both' not in ('', 'None') else None,
  'lastLog': '$LOG',
  'siteOrigin': '$SITE_ORIGIN',
})
p.write_text(json.dumps(state, indent=2) + '\n')
"
}

run_cmd() {
  local label="$1"
  shift
  log "--- $label ---"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "  [dry-run] would run: $*"
    return 0
  fi
  if "$@" >>"$LOG" 2>&1; then
    log "  $label: ok"
    return 0
  fi
  log "  $label: exited non-zero (continuing)"
  return 0
}

read_report_field() {
  local field="$1"
  python3 -c "
import json, pathlib
p=pathlib.Path('data/seo_geo_coverage_report.json')
if not p.exists():
    print('')
else:
    print(json.load(open(p)).get('$field', ''))
" 2>/dev/null || echo ""
}

probe_live() {
  log "--- live SEO probe ($SITE_ORIGIN) ---"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "  [dry-run] would curl sitemap/robots/llms/home"
    return 0
  fi
  SITE_ORIGIN="$SITE_ORIGIN" python3 - <<'PY' >>"$LOG" 2>&1 || true
import json, os, urllib.request, datetime
from pathlib import Path
origin = os.environ.get("SITE_ORIGIN", "https://www.findmyisland.com").rstrip("/")
paths = ["/", "/sitemap.xml", "/robots.txt", "/llms.txt", "/islands/", "/islands/scotland/", "/islands/scotland/isle-of-skye/", "/profiles/isle-of-skye.html"]
results = []
for path in paths:
    url = origin + path
    row = {"url": url, "ok": False, "status": None, "bytes": 0, "error": None}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "isles-of-britain-seo-geo-loop/1.0"})
        with urllib.request.urlopen(req, timeout=25) as resp:
            body = resp.read()
            row["ok"] = 200 <= resp.status < 300
            row["status"] = resp.status
            row["bytes"] = len(body)
            if path == "/sitemap.xml" and b"<urlset" not in body[:500]:
                row["ok"] = False
                row["error"] = "missing urlset"
            if path == "/robots.txt" and b"Sitemap:" not in body:
                row["error"] = "no Sitemap directive"
            if path == "/llms.txt" and b"findmyisland" not in body.lower():
                row["error"] = "unexpected llms.txt body"
    except Exception as e:
        row["error"] = f"{type(e).__name__}: {e}"
    results.append(row)
    mark = "OK" if row["ok"] else "FAIL"
    print(f"  {mark} {path} status={row['status']} bytes={row['bytes']} err={row['error']}")
out = {
    "probedAt": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat(),
    "origin": origin,
    "results": results,
    "allOk": all(r["ok"] for r in results),
}
Path("data/seo_geo_live_probe.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
print(f"  probe summary allOk={out['allOk']}")
PY
}

CYCLE=$(( $(read_cycle) + 1 ))
# Rotate enrichment focus across cycles.
# Photos twice as often — highest current SEO yield (OG images).
ACTIONS=(photos descriptions photos featured)
ACTION_IDX=$(( (CYCLE - 1) % ${#ACTIONS[@]} ))
ACTION="${ACTIONS[$ACTION_IDX]}"

log "=== SEO/GEO improvement cycle $CYCLE start $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
log "Action this cycle: $ACTION"
log "Site origin: $SITE_ORIGIN"

# ── Phase 0: baseline audit ────────────────────────────────────────────────
run_cmd "audit SEO/GEO coverage" python3 scripts/audit_seo_geo_coverage.py
AVG_BEFORE=$(read_report_field averageScore)
BOTH_BEFORE=$(read_report_field pctBoth)
DESC_BEFORE=$(read_report_field withDescription)
PHOTO_BEFORE=$(read_report_field withPhoto)
log "Baseline avg_score=$AVG_BEFORE pct_both=$BOTH_BEFORE desc=$DESC_BEFORE photo=$PHOTO_BEFORE"

# ── Phase 1: rotating enrichment ───────────────────────────────────────────
case "$ACTION" in
  descriptions)
    log "=== Phase 1: Wikipedia descriptions (SEO meta / JSON-LD / GEO) ==="
    run_cmd "build description priority queue" python3 scripts/build_description_priority_queue.py
    # Description queue puts direct Wikipedia URLs first (highest adopt rate).
    if [[ -f data/description_priority_queue.json ]]; then
      run_cmd "enrich descriptions (Wikipedia-URL queue)" \
        python3 scripts/enrich_descriptions_wikipedia.py \
          --queue-file data/description_priority_queue.json \
          --limit "$DESC_LIMIT" \
          --checkpoint 25
    fi
    # SEO queue covers curated/featured/ferry gaps next.
    if [[ -f data/seo_geo_priority_queue.json ]]; then
      run_cmd "enrich descriptions (SEO queue)" \
        python3 scripts/enrich_descriptions_wikipedia.py \
          --queue-file data/seo_geo_priority_queue.json \
          --limit "$(( DESC_LIMIT / 2 ))" \
          --checkpoint 25
    fi
    ;;
  photos)
    log "=== Phase 1: OG photos for SEO queue (high-confidence + staging) ==="
    run_cmd "build image priority queue" python3 scripts/build_image_priority_queue.py
    run_cmd "v5 P18 (SEO queue order)" \
      python3 scripts/enrich_images_v5.py \
        --source p18 --named-only --min-confidence high \
        --queue-file data/seo_geo_priority_queue.json \
        --no-backup --delay 2 --limit "$PHOTO_LIMIT"
    run_cmd "v5 OSM tags (SEO queue order)" \
      python3 scripts/enrich_images_v5.py \
        --source osm-tags --named-only --min-confidence high \
        --queue-file data/seo_geo_priority_queue.json \
        --no-backup --delay 2 --limit "$PHOTO_LIMIT"
    # Staging harvesters — higher yield than exhausted P18 alone.
    PHOTO_ROTATE=$(( (CYCLE - 1) % 3 ))
    case "$PHOTO_ROTATE" in
      0)
        run_cmd "geograph-native staging" \
          python3 scripts/enrich_images_geograph_native.py --named-only --limit "$PHOTO_LIMIT" --delay 1.5
        ;;
      1)
        run_cmd "wikipedia-embedded staging" \
          python3 scripts/enrich_images_wikipedia_embedded.py --named-only --limit "$PHOTO_LIMIT" --delay 1.5
        ;;
      2)
        run_cmd "commons-county staging" \
          python3 scripts/enrich_images_commons_county.py --named-only --limit "$PHOTO_LIMIT" --delay 1.5
        ;;
    esac
    if [[ -f scripts/verify_staged_photos_strict.py ]]; then
      run_cmd "verify staged photos" python3 scripts/verify_staged_photos_strict.py
    fi
    if [[ -f scripts/merge_staged_photo_adoptions.py ]]; then
      run_cmd "merge staged photos" python3 scripts/merge_staged_photo_adoptions.py --no-backup
    fi
    ;;
  featured)
    log "=== Phase 1: Featured strip + discovery topics (crawl / UI entry) ==="
    run_cmd "build featured islands" python3 scripts/build_featured_islands.py
    run_cmd "build discovery topics" python3 scripts/build_discovery_topics.py
    # Featured islands without descriptions are highest GEO value — force a small desc pass.
    run_cmd "enrich descriptions (featured gaps)" \
      python3 scripts/enrich_descriptions_wikipedia.py \
        --queue-file data/seo_geo_priority_queue.json \
        --limit 40 \
        --checkpoint 20
    ;;
  artifacts)
    log "=== Phase 1: Artifact-only refresh (no dataset mutation beyond regen) ==="
    run_cmd "build featured islands" python3 scripts/build_featured_islands.py
    ;;
esac

# ── Phase 2: publish artefacts crawlers / LLMs see ─────────────────────────
log "=== Phase 2: Index + SEO/GEO artifacts ==="
run_cmd "rebuild islands index" python3 scripts/build_islands_index.py
run_cmd "generate SEO artifacts" \
  env IOB_SITE_ORIGIN="$SITE_ORIGIN" \
  python3 scripts/generate_seo_artifacts.py --landing-dir profiles

# ── Phase 3: re-audit + live probe ─────────────────────────────────────────
run_cmd "re-audit SEO/GEO coverage" python3 scripts/audit_seo_geo_coverage.py
AVG_AFTER=$(read_report_field averageScore)
BOTH_AFTER=$(read_report_field pctBoth)
DESC_AFTER=$(read_report_field withDescription)
PHOTO_AFTER=$(read_report_field withPhoto)
log "After avg_score=$AVG_AFTER pct_both=$BOTH_AFTER desc=$DESC_AFTER photo=$PHOTO_AFTER"

probe_live

if [[ "$DRY_RUN" -eq 0 ]]; then
  write_state "$CYCLE" "$ACTION" "${AVG_AFTER:-0}" "${BOTH_AFTER:-0}"
else
  log "  [dry-run] skip state write"
fi

log "=== Cycle $CYCLE done $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
log "Action=$ACTION avg $AVG_BEFORE → $AVG_AFTER | both% $BOTH_BEFORE → $BOTH_AFTER"
log "Log: $LOG"
