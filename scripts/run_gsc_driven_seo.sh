#!/usr/bin/env bash
# GSC-driven SEO/GEO improvement cycle.
# Uses data/gsc_seo_snapshot.json priority islands + local coverage audit.
# Safe with run_seo_geo_improvement.sh lock (skips if that lock is held).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
SITE_ORIGIN="${IOB_SITE_ORIGIN:-https://www.findmyisland.com}"
LOCK="data/.gsc_seo_improvement.lock"
SEO_LOCK="data/.seo_geo_improvement.lock"
STATE="data/.gsc_seo_improvement_state.json"
LOG_DIR="logs"
mkdir -p "$LOG_DIR" data
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$LOG_DIR/gsc-seo-improvement-${STAMP}.log"

log() { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$LOG"; }

if [[ -f "$SEO_LOCK" ]]; then
  log "Skip: SEO/GEO continuous lock held ($SEO_LOCK)"
  exit 0
fi
if [[ -f "$LOCK" ]]; then
  age=$(( $(date +%s) - $(stat -f %m "$LOCK" 2>/dev/null || stat -c %Y "$LOCK") ))
  if (( age < 3600 )); then
    log "Skip: gsc lock held (age ${age}s)"
    exit 0
  fi
  log "Stale gsc lock (${age}s) — removing"
  rm -f "$LOCK"
fi
echo "$$ $(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$LOCK"
trap 'rm -f "$LOCK"' EXIT

log "=== GSC-driven SEO cycle start ${STAMP} ==="
log "Site origin: $SITE_ORIGIN"

# 1) Live deploy probe
DEPLOYED=0
code=$(curl -s -o /dev/null -w "%{http_code}" "$SITE_ORIGIN/islands/scotland/" || echo 000)
if [[ "$code" == "200" ]]; then
  DEPLOYED=1
  log "Live /islands/scotland/ → HTTP $code (deployed)"
else
  log "Live /islands/scotland/ → HTTP $code (NOT deployed — local artifacts only)"
fi

# 2) Refresh priority queue from snapshot (fallback curated list)
python3 - <<'PY' | tee -a "$LOG"
import json
from pathlib import Path
from datetime import datetime, timezone

snap_path = Path("data/gsc_seo_snapshot.json")
ids = [
    "scilly-st-marys", "anglesey", "bute", "lewis-and-harris", "staffa",
    "isle-of-wight", "brownsea", "mainland-orkney", "st-kilda", "lundy",
    "inchcailloch", "eel-pie-island", "isle-of-dogs", "isle-of-man",
    "rathlin", "iona", "lindisfarne", "arran", "mull",
]
if snap_path.is_file():
    snap = json.loads(snap_path.read_text())
    for x in snap.get("priorityIslandIds") or []:
        if x not in ids:
            ids.append(x)

islands = {i["id"]: i for i in json.loads(Path("data/islands.json").read_text()) if i.get("id")}
rows = []
for iid in ids:
    isl = islands.get(iid)
    if not isl:
        continue
    rows.append({
        "id": iid,
        "name": isl.get("name"),
        "seoPath": isl.get("seoPath"),
        "hasDescription": bool(isl.get("shortDescription")),
        "hasPhoto": bool(isl.get("images") or isl.get("image")),
        "reason": "gsc-priority",
    })

# Prefer islands still missing desc/photo first
rows.sort(key=lambda r: (r["hasDescription"] and r["hasPhoto"], r["id"]))
out = {
    "schemaVersion": 1,
    "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "source": "gsc_seo_snapshot + curated spine",
    "ids": [r["id"] for r in rows],
    "items": rows,
}
Path("data/gsc_priority_queue.json").write_text(json.dumps(out, indent=2) + "\n")
need_desc = sum(1 for r in rows if not r["hasDescription"])
need_photo = sum(1 for r in rows if not r["hasPhoto"])
print(f"GSC queue: {len(rows)} islands; need_desc={need_desc} need_photo={need_photo}")
PY

# 3) Targeted description enrich for GSC queue gaps
if [[ -f data/gsc_priority_queue.json ]]; then
  log "--- enrich descriptions (GSC queue) ---"
  python3 scripts/enrich_descriptions_wikipedia.py \
    --queue-file data/gsc_priority_queue.json \
    --limit "${GSC_SEO_DESC_LIMIT:-40}" \
    2>&1 | tee -a "$LOG" || log "description enrich: non-fatal"
fi

# 4) Rebuild index (seoPath) + SEO artifacts + ferry landings
log "--- build islands index ---"
python3 scripts/build_islands_index.py 2>&1 | tee -a "$LOG"

log "--- generate SEO artifacts ---"
IOB_SITE_ORIGIN="$SITE_ORIGIN" python3 scripts/generate_seo_artifacts.py \
  --landing-dir profiles 2>&1 | tee -a "$LOG"

log "--- regenerate ferry landings ---"
python3 scripts/generate_ferry_landing_pages.py 2>&1 | tee -a "$LOG" || log "ferry regen: non-fatal"

# 5) Coverage audit
log "--- audit SEO/GEO coverage ---"
python3 scripts/audit_seo_geo_coverage.py 2>&1 | tee -a "$LOG"

# 6) Update snapshot deploy flag + metrics
python3 - <<PY | tee -a "$LOG"
import json
from pathlib import Path
from datetime import datetime, timezone
snap_path = Path("data/gsc_seo_snapshot.json")
snap = json.loads(snap_path.read_text()) if snap_path.is_file() else {}
report = json.loads(Path("data/seo_geo_coverage_report.json").read_text())
snap["lastGscDrivenCycle"] = {
    "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "islandsDirDeployed": bool($DEPLOYED),
    "averageScore": report.get("averageScore"),
    "pctBoth": report.get("pctBoth"),
    "withDescription": report.get("withDescription"),
    "withPhoto": report.get("withPhoto"),
}
snap_path.write_text(json.dumps(snap, indent=2) + "\n")
state = {
    "lastRunUtc": datetime.now(timezone.utc).isoformat(),
    "deployed": bool($DEPLOYED),
    "averageScore": report.get("averageScore"),
    "pctBoth": report.get("pctBoth"),
    "log": "$LOG",
}
Path("$STATE").write_text(json.dumps(state, indent=2) + "\n")
print(
    f"Done avg={report.get('averageScore')} both%={report.get('pctBoth')} "
    f"deployed={bool($DEPLOYED)}"
)
PY

log "=== GSC-driven SEO cycle done ==="
log "Log: $LOG"
