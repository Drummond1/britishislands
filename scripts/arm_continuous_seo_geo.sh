#!/usr/bin/env bash
# Detach the continuous SEO/GEO strategy loop from the current shell.
# Usage: bash scripts/arm_continuous_seo_geo.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p logs data
rm -f data/.continuous_seo_geo.stop
if [[ -f data/.continuous_seo_geo.lock ]]; then
  age=$(( $(date +%s) - $(stat -f %m data/.continuous_seo_geo.lock 2>/dev/null || stat -c %Y data/.continuous_seo_geo.lock) ))
  if (( age < 7200 )); then
    echo "Already running (lock age ${age}s). Stop first: touch data/.continuous_seo_geo.stop"
    exit 1
  fi
  rm -f data/.continuous_seo_geo.lock
fi
# Clear orphaned single-cycle locks older than 2h
for f in data/.seo_geo_improvement.lock data/.gsc_seo_improvement.lock; do
  if [[ -f "$f" ]]; then
    age=$(( $(date +%s) - $(stat -f %m "$f" 2>/dev/null || stat -c %Y "$f") ))
    if (( age > 7200 )); then
      rm -f "$f"
    fi
  fi
done
nohup env \
  SEO_GEO_CONTINUOUS_PUSH="${SEO_GEO_CONTINUOUS_PUSH:-1}" \
  SEO_GEO_SLEEP_SEC="${SEO_GEO_SLEEP_SEC:-2700}" \
  SEO_GEO_DESC_LIMIT="${SEO_GEO_DESC_LIMIT:-150}" \
  SEO_GEO_PHOTO_LIMIT="${SEO_GEO_PHOTO_LIMIT:-150}" \
  IOB_SITE_ORIGIN="${IOB_SITE_ORIGIN:-https://www.findmyisland.com}" \
  bash scripts/run_continuous_seo_geo.sh --loop \
  >> logs/continuous-seo-geo.out 2>&1 &
echo $! > data/.continuous_seo_geo.launcher.pid
sleep 1
PID="$(cat data/.continuous_seo_geo.pid 2>/dev/null || true)"
echo "Armed continuous SEO/GEO (launcher=$! loop_pid=${PID:-pending})"
echo "Logs: logs/continuous-seo-geo.out"
echo "Stop: touch data/.continuous_seo_geo.stop"
