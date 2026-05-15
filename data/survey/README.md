# Survey outputs (`data/survey/`)

Artifacts produced by **`scripts/survey_landmass_ledger.py`** (no network; reads local JSON).

| File | Purpose |
|------|---------|
| `landmass_ledger.json` | Full ledger: every atlas row + every pipeline candidate + `outstandingRows`. |
| `survey_summary.json` | Counts only — quick dashboard. |

**Regenerate after** refreshing discovery (`discover_islands_pipeline.py` stages) or editing `islands.json`:

```bash
python3 scripts/survey_landmass_ledger.py
# or if you only have enrichment.json:
python3 scripts/survey_landmass_ledger.py --from-enrichment
```

Operational briefing: [`docs/PROMPT-COMPREHENSIVE-LANDMASS-SURVEY.md`](../docs/PROMPT-COMPREHENSIVE-LANDMASS-SURVEY.md).
