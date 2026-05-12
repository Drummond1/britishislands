# Documentation Index

Single map of every document in this repository. Always start at the top.

## Tier 1 — Orientation (read first)

| File | Purpose | Update cadence |
|------|---------|----------------|
| [`../AGENTS.md`](../AGENTS.md) | Entry point. What this project is, hard rules, where things live. | When structure or top-level rules change. |
| [`STATE.md`](STATE.md) | Live snapshot: dataset counts, last pipeline run, what's currently running. | After every pipeline run or schema change. |
| [`QUEUE.md`](QUEUE.md) | Pending follow-ups, in priority order. | After every session. |
| [`SESSION-LOG.md`](SESSION-LOG.md) | Chronological log of session-by-session changes. | Append after every material session. |
| [`ETHICS.md`](ETHICS.md) | **Permanent** guardrails for data sourcing, attribution, privacy. | Rarely; only when a new ethical concern emerges. |

## Tier 2 — Architecture & schema

| File | Purpose |
|------|---------|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Code layout, data flow, how the frontend renders 6k+ islands. |
| [`DATA-SCHEMA.md`](DATA-SCHEMA.md) | Full island record spec with every field, type, and example. |
| [`PIPELINE.md`](PIPELINE.md) | How to rebuild `data/islands.json` end-to-end. |

## Tier 3 — Methodology

| File | Purpose |
|------|---------|
| [`METHODOLOGY-INLAND.md`](METHODOLOGY-INLAND.md) | Tier A + Tier B inland classifier deep-dive. |
| [`DISCOVERY-SOURCES.md`](DISCOVERY-SOURCES.md) | Catalogue of ~85 evaluated discovery sources. |
| [`NEXT-SESSION-PLAN.md`](NEXT-SESSION-PLAN.md) | Rolling, executable plan for the next ingestion phase. |
| [`VALIDATION.md`](VALIDATION.md) | Canonical regression set: islands you should always be able to find correctly. |
| [`IMAGE-SOURCES.md`](IMAGE-SOURCES.md) | Image source registry + ranking for enrichment passes. |
| [`OS-MAPS.md`](OS-MAPS.md) | OS Maps detail-view integration: API key setup + the EPSG:27700 Leisure upgrade path. |
| [`FERRIES.md`](FERRIES.md) | Ferry-routes feature: operator inventory (54 operators), data sources (OSM + GTFS + manual), refresh cadence, terminal-mapping rules, UI surface. |

## Reading order by goal

**"I'm a new agent, what is this?"**
→ `AGENTS.md` → `STATE.md` → `QUEUE.md`

**"I need to change the dataset / run ingestion."**
→ `AGENTS.md` → `STATE.md` → `PIPELINE.md` → `ETHICS.md` → run, then update `STATE.md` + `SESSION-LOG.md`

**"I'm changing the schema."**
→ `DATA-SCHEMA.md` → `ARCHITECTURE.md` (frontend impact) → update both in the same diff

**"I'm extending discovery."**
→ `NEXT-SESSION-PLAN.md` → `DISCOVERY-SOURCES.md` → `ETHICS.md` → `METHODOLOGY-INLAND.md` if inland-related

**"I'm changing the UI."**
→ `ARCHITECTURE.md` (frontend section) → `app.js`/`styles.css`/`index.html`

**"I'm verifying a data run."**
→ `VALIDATION.md` → spot-check a sample → check the relevant `data/*_report.json`

**"I'm changing ferry data."**
→ `FERRIES.md` → run `scripts/refresh_ferries.py` (full pipeline minus drivetime) → check `data/ferries_stale_report.json` → update `STATE.md` counts
