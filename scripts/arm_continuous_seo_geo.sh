#!/usr/bin/env bash
# Detach the continuous SEO/GEO strategy loop so it survives Cursor/agent shells.
# Prefers GNU screen (available on macOS). Falls back to nohup.
#
# Usage:
#   bash scripts/arm_continuous_seo_geo.sh
# Stop:
#   touch data/.continuous_seo_geo.stop
#   # or: screen -S iob-seo-geo -X quit
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p logs data
SESSION="iob-seo-geo"

rm -f data/.continuous_seo_geo.stop

if [[ -f data/.continuous_seo_geo.lock ]]; then
  age=$(( $(date +%s) - $(stat -f %m data/.continuous_seo_geo.lock 2>/dev/null || stat -c %Y data/.continuous_seo_geo.lock) ))
  if (( age < 7200 )); then
    if [[ -f data/.continuous_seo_geo.pid ]] && kill -0 "$(cat data/.continuous_seo_geo.pid)" 2>/dev/null; then
      echo "Already running (pid $(cat data/.continuous_seo_geo.pid), lock age ${age}s)."
      echo "Stop: touch data/.continuous_seo_geo.stop"
      exit 0
    fi
    echo "Stale lock (${age}s) with dead pid — clearing"
    rm -f data/.continuous_seo_geo.lock data/.continuous_seo_geo.pid
  else
    rm -f data/.continuous_seo_geo.lock data/.continuous_seo_geo.pid
  fi
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

ENV_PREFIX=(
  env
  "SEO_GEO_CONTINUOUS_PUSH=${SEO_GEO_CONTINUOUS_PUSH:-1}"
  "SEO_GEO_SLEEP_SEC=${SEO_GEO_SLEEP_SEC:-2700}"
  "SEO_GEO_DESC_LIMIT=${SEO_GEO_DESC_LIMIT:-150}"
  "SEO_GEO_PHOTO_LIMIT=${SEO_GEO_PHOTO_LIMIT:-150}"
  "IOB_SITE_ORIGIN=${IOB_SITE_ORIGIN:-https://www.findmyisland.com}"
)

if command -v screen >/dev/null 2>&1; then
  screen -S "$SESSION" -X quit 2>/dev/null || true
  screen -dmS "$SESSION" "${ENV_PREFIX[@]}" bash -lc \
    "cd \"$ROOT\" && exec bash scripts/run_continuous_seo_geo.sh --loop >> logs/continuous-seo-geo.out 2>&1"
  sleep 2
  PID="$(cat data/.continuous_seo_geo.pid 2>/dev/null || true)"
  echo "Armed continuous SEO/GEO in screen session '$SESSION' (pid=${PID:-pending})"
  echo "Attach: screen -r $SESSION"
else
  nohup "${ENV_PREFIX[@]}" bash scripts/run_continuous_seo_geo.sh --loop \
    >> logs/continuous-seo-geo.out 2>&1 &
  sleep 1
  PID="$(cat data/.continuous_seo_geo.pid 2>/dev/null || true)"
  echo "Armed continuous SEO/GEO via nohup (pid=${PID:-pending})"
fi

echo "Logs: logs/continuous-seo-geo.out"
echo "Stop: touch data/.continuous_seo_geo.stop"
