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
| [`SEO-GEO.md`](SEO-GEO.md) | Island profile SEO + JSON-LD; sitemap / `llms.txt` / optional static landings. |
| [`SUPABASE.md`](SUPABASE.md) | Supabase project setup, schema, RLS, keys, storage bucket. |
| [`PROPERTY-LISTINGS.md`](PROPERTY-LISTINGS.md) | For-sale outbound links: curated + optional Homedata; no portal scraping. |
| [`FOR-SALE-ISLANDS.md`](FOR-SALE-ISLANDS.md) | **Full list** of islands currently on the market (generated table + counts). |

## Tier 3 — Methodology

| File | Purpose |
|------|---------|
| [`METHODOLOGY-INLAND.md`](METHODOLOGY-INLAND.md) | Tier A + Tier B inland classifier deep-dive. |
| [`MEASUREMENTS.md`](MEASUREMENTS.md) | Area (`areaKm2`) + elevation (`highestPointM`) sources, methods, licensing, and confidence. |
| [`PRD-USER-CONTRIBUTIONS.md`](PRD-USER-CONTRIBUTIONS.md) | Draft PRD for accounts, photo uploads, moderation. **Shipped v1:** source-linked corrections via GitHub issues (detail panel + `.github/ISSUE_TEMPLATE/island-data-correction.md`). **Crowd pins:** suggest missing islands / unnamed pins → `docs/CROWD-PINS.md` + `data/crowd_pins.json`. |
| [`CROWD-PINS.md`](CROWD-PINS.md) | Community pin workflow: GitHub triage, `crowd_pins.json` fields, ethics. |
| [`DISCOVERY-SOURCES.md`](DISCOVERY-SOURCES.md) | Catalogue of ~85 evaluated discovery sources. |
| [`DISCOVERY-PIPELINE.md`](DISCOVERY-PIPELINE.md) | Five-agent review-first discovery workflow and artifact paths. |
| [`NEXT-SESSION-PLAN.md`](NEXT-SESSION-PLAN.md) | Rolling, executable plan for the next ingestion phase. |
| [`PROMPT-COMPREHENSIVE-LANDMASS-SURVEY.md`](PROMPT-COMPREHENSIVE-LANDMASS-SURVEY.md) | **Multi-agent briefing:** full remit landmass sweep, naming certainty, ledger + closure report (copy/paste prompt). Executable ledger: `scripts/survey_landmass_ledger.py` → `data/survey/`. |
| [`VALIDATION.md`](VALIDATION.md) | Canonical regression set: islands you should always be able to find correctly. |
| [`IMAGE-SOURCES.md`](IMAGE-SOURCES.md) | Image source registry + ranking for enrichment passes. |
| [`OS-MAPS.md`](OS-MAPS.md) | OS Maps detail-view integration: API key setup + the EPSG:27700 Leisure upgrade path. |
| [`FERRIES.md`](FERRIES.md) | Ferry-routes feature: operator inventory (54 operators), data sources (OSM + GTFS + manual), refresh cadence, terminal-mapping rules, UI surface. |
| [`DATA-SOURCES.md`](DATA-SOURCES.md) | Registry of every external dataset ingested into `islands.json`: licence, refresh cadence, attribution string, consuming script. |
| [`SCHEMA-ENRICHMENTS-2026-05-13.md`](SCHEMA-ENRICHMENTS-2026-05-13.md) | Proposal for the 2026-05-13 enrichments (hills, lighthouses, wildlife colonies, geology, census 2022).  Schema, ethics rules, UI render plan, and apply order. |

## Reading order by goal

**"I'm a new agent, what is this?"**
→ `AGENTS.md` → `STATE.md` → `QUEUE.md`

**"I need to change the dataset / run ingestion."**
→ `AGENTS.md` → `STATE.md` → `PIPELINE.md` → `ETHICS.md` → run, then update `STATE.md` + `SESSION-LOG.md`

**"I'm changing the schema."**
→ `DATA-SCHEMA.md` → `ARCHITECTURE.md` (frontend impact) → update both in the same diff

**"I'm extending discovery."**
→ `NEXT-SESSION-PLAN.md` → `DISCOVERY-SOURCES.md` → `DISCOVERY-PIPELINE.md` → `ETHICS.md` → `METHODOLOGY-INLAND.md` if inland-related

**"I'm changing the UI."**
→ `ARCHITECTURE.md` (frontend section) → `app.js`/`styles.css`/`index.html`

**"I'm triaging community map pins."**
→ `CROWD-PINS.md` → `data/crowd_pins.json`

**"I'm verifying a data run."**
→ `VALIDATION.md` → spot-check a sample → check the relevant `data/*_report.json`

**"I'm changing ferry data."**
→ `FERRIES.md` → run `scripts/refresh_ferries.py` (full pipeline minus drivetime) → check `data/ferries_stale_report.json` → update `STATE.md` counts
