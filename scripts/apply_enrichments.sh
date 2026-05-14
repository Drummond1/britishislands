#!/usr/bin/env bash
# Apply the five staged enrichment caches to data/islands.json.
#
# This is a thin wrapper around scripts/apply_enrichments.py that:
#   1. Verifies the overnight chain has finished.
#   2. Confirms all expected caches are present (or prints what's missing).
#   3. Runs the dry-run, then asks for confirmation, then runs --apply.
#
# Order of operations (after the overnight chain finishes):
#
#   1. Stage each ingestion script with --commit (run them in any order):
#        python3 scripts/ingest_hills_dobih.py     --fetch --commit
#        python3 scripts/ingest_lighthouses.py     --fetch --commit
#        python3 scripts/ingest_wildlife_colonies.py --fetch --commit
#        python3 scripts/ingest_geology_bgs.py     --fetch --commit
#        python3 scripts/ingest_census_2022.py     --commit
#
#   2. Run this script:
#        bash scripts/apply_enrichments.sh
#
# The script defaults to interactive confirmation.  Pass --yes to skip
# the prompt (useful for unattended automation, e.g. an overnight
# orchestrator step).

set -u
cd "$(dirname "$0")/.."

YES="no"
EXTRA=()
for arg in "$@"; do
    case "$arg" in
        --yes|-y) YES="yes" ;;
        --force) EXTRA+=("--force") ;;
        --only) shift; EXTRA+=("--only" "$@") ; break ;;
        *) EXTRA+=("$arg") ;;
    esac
done

echo "=== Apply enrichments orchestrator ==="
echo "  working dir : $(pwd)"
echo "  python3     : $(command -v python3 || echo missing)"

# Check overnight chain.
LATEST_SUMMARY="$(ls -1t logs/overnight-*-summary.log 2>/dev/null | head -1 || true)"
if [[ -z "${LATEST_SUMMARY}" ]]; then
    echo "  overnight chain: (no logs/overnight-*-summary.log found)"
else
    echo "  overnight chain: latest summary = ${LATEST_SUMMARY}"
    if grep -q "^===== Overnight run finished" "${LATEST_SUMMARY}"; then
        echo "                   → FINISHED"
    else
        echo "                   → STILL RUNNING (latest tail follows)"
        tail -3 "${LATEST_SUMMARY}" | sed 's/^/                   | /'
        if [[ "${YES}" != "yes" && ! " ${EXTRA[*]} " =~ " --force " ]]; then
            echo
            echo "  Overnight chain still running.  Aborting."
            echo "  Re-run with --force (with care) to override."
            exit 2
        fi
    fi
fi

# Check caches.
echo
echo "  staged caches:"
declare -A names=(
    [hills]="data/cache_dobih.json"
    [lighthouses]="data/cache_lighthouses.json"
    [wildlife]="data/cache_wildlife.json"
    [geology]="data/cache_bgs.json"
    [census]="data/cache_census2022.json"
)
missing=0
for k in hills lighthouses wildlife geology census; do
    f="${names[$k]}"
    if [[ -s "${f}" ]]; then
        size=$(wc -c < "${f}" | tr -d ' ')
        echo "    [present] ${k}: ${f} (${size} bytes)"
    else
        echo "    [missing] ${k}: ${f}"
        missing=$((missing + 1))
    fi
done
if [[ $missing -gt 0 ]]; then
    echo
    echo "  ${missing} cache(s) missing — they'll be skipped."
fi

# Dry-run first.
echo
echo "=== Dry-run ==="
python3 scripts/apply_enrichments.py --dry-run "${EXTRA[@]}" || {
    rc=$?
    echo "Dry-run failed (rc=${rc}).  Not proceeding."
    exit ${rc}
}

# Confirmation.
if [[ "${YES}" != "yes" ]]; then
    echo
    read -rp "Apply changes to data/islands.json? [y/N] " confirm
    if [[ "${confirm}" != "y" && "${confirm}" != "Y" ]]; then
        echo "Aborted."
        exit 1
    fi
fi

# Apply.
echo
echo "=== Apply ==="
python3 scripts/apply_enrichments.py --apply "${EXTRA[@]}"
rc=$?
if [[ ${rc} -eq 0 ]]; then
    echo
    echo "Done.  Verify with:"
    echo "  python3 -c \"import json; print(len(json.load(open('data/islands.json'))))\""
    echo "  cat data/enrichment_apply_report.json"
fi
exit ${rc}
