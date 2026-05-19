# AGENTS.md — Isles of Britain

**You are a coding agent working on this project. This file is your starting point.**
Read it whenever you join a fresh session before doing anything else. It exists
so a new agent or human can pick up the project without replaying chat history.

---

## 1. What this project is

A static web app that lists and visually represents **every island within ~50
miles of the United Kingdom and Ireland**, including inland islands in rivers
and lakes. Each island has a profile with description, photo(s), water-body
context, classification provenance, and (planned) an Ordnance Survey detail
view.

Stack: **vanilla HTML/CSS/ES-modules + Leaflet + Leaflet.markercluster**, with
**Python scripts** for data ingestion. No build step. Serve locally with
`python3 -m http.server`.

## 2. The single source of truth

Read these in order before any action that touches data or scope:

1. [`docs/INDEX.md`](docs/INDEX.md) — map of every document in this project.
2. [`docs/STATE.md`](docs/STATE.md) — **live snapshot**: dataset counts, last
   pipeline run, what's currently running, file inventory.
3. [`docs/QUEUE.md`](docs/QUEUE.md) — pending follow-ups, in priority order.
4. [`docs/SESSION-LOG.md`](docs/SESSION-LOG.md) — chronological log of what each
   session changed and why.
5. [`docs/ETHICS.md`](docs/ETHICS.md) — **non-negotiable** guardrails for data
   sourcing, attribution, privacy, and licensing. The ethics charter wins over
   every other guideline in this repo.

After those five, branch into the topic-specific docs from `INDEX.md` only as
needed.

## 3. Hard rules (do not break)

- **Never break `data/islands.json`'s schema** without updating
  [`docs/DATA-SCHEMA.md`](docs/DATA-SCHEMA.md) in the same change.
- **Never add an island without provenance** (`source`, and one of
  `osmId`/`wikidata`/curated reference).
- **Never add an image without attribution + licence** in the `images[]` entry.
  See [`docs/ETHICS.md`](docs/ETHICS.md) §2 and `enrich_images.py`'s policy.
- **Never delete a curated island**. Curated entries are the regression spine.
  See [`docs/VALIDATION.md`](docs/VALIDATION.md).
- **Do not commit secrets**. The OS Maps API key, if added, belongs in
  `.env.local` (gitignored) and is loaded at runtime.
- **Be polite to free APIs**. Overpass, Wikidata, MediaWiki, and Commons all
  have rate limits — every script in `scripts/` uses caching (`--cache`) and a
  user-agent. Reuse them.
- **Do not run write-pipelines while another agent is running them**. Check
  `docs/STATE.md` "Currently running" block first.

## 4. Where things live

```
.
├── AGENTS.md                ← you are here
├── README.md                ← public-facing project doc
├── index.html               ← entry HTML (incl. chat launcher + panel)
├── styles.css               ← all styling
├── app.js                   ← Leaflet + UI logic + chatbot (ES module)
├── crowd-pins.js            ← community pins: fetch + GitHub issue URLs + popups
├── seo-meta.js              ← per-island head tags + JSON-LD (SEO / GEO)
├── data/
│   ├── islands.json         ← canonical dataset (DO NOT hand-edit)
│   ├── islands_index.json   ← slim first paint; run scripts/build_islands_index.py after islands edits
│   ├── crowd_pins.json      ← maintainer-curated community pins (see docs/CROWD-PINS.md)
│   ├── curated.json         ← hand-curated spine of 27 islands
│   ├── osm_raw.json         ← cached Overpass response (islands)
│   ├── water_raw.json       ← cached Overpass response (water bodies)
│   ├── inland_classification_report.json
│   ├── discovery_ingestion_report.json
│   ├── image_enrichment_report.json      ← v2 (Wikidata P18 + pageimages)
│   └── image_enrichment_v3_report.json   ← v3 (Commons cat/geo + OSM tag)
├── scripts/
│   ├── fetch_islands.py     ← Tier 0: OSM island ingestion
│   ├── classify_inland.py   ← Tier A + B inland classifier
│   ├── enrich_images.py     ← v2: Wikidata + Wikipedia image harvest
│   ├── enrich_images_v3.py  ← v3: Commons category + OSM tag + geosearch
│   └── (discovery scripts — see docs/ARCHITECTURE.md)
├── docs/
│   ├── INDEX.md             ← table of contents for all docs
│   ├── STATE.md             ← live dataset & process snapshot
│   ├── QUEUE.md             ← pending follow-ups
│   ├── SESSION-LOG.md       ← chronological session log
│   ├── ARCHITECTURE.md      ← code + data-flow overview
│   ├── DATA-SCHEMA.md       ← island record spec
│   ├── PIPELINE.md          ← how to rebuild end-to-end
│   ├── METHODOLOGY-INLAND.md← Tier A + B classifier deep-dive
│   ├── VALIDATION.md        ← canonical regression set
│   ├── IMAGE-SOURCES.md     ← brainstorm + source registry (provenance)
│   ├── CROWD-PINS.md        ← community pin triage + `crowd_pins.json` fields
│   ├── ETHICS.md            ← permanent ethics charter
│   ├── DISCOVERY-SOURCES.md ← catalogue of evaluated data sources
│   └── NEXT-SESSION-PLAN.md ← rolling action plan
└── .cursor/rules/
    └── project.mdc          ← always-apply rule pointing here
```

### Chatbot ("Island finder")

A local-only natural-language island finder lives at the bottom-right of the
page (floating "Ask" button → drawer). Implementation: `app.js` after the
`// ---------- Chatbot` comment. Parser recognises nation, type, subtype,
archipelago, feature keywords, area constraints, sort directives, and
**proximity** ("near Oban", "within 30 km of Mallaig") via the
`CHAT_PLACES` gazetteer. Each query is reflected into the URL as
`?ask=…` so they're shareable; `chatAutoLoadFromUrl()` replays the
permalink on page load. No external API calls — everything runs in the
browser. To extend it, add synonyms to the `CHAT_*` dictionaries or
extra cities to `CHAT_PLACES`.

### Islands for sale (property listings)

Outbound broker links only — no Rightmove/Zoopla scrape. **Full list (read this first):**
[`docs/FOR-SALE-ISLANDS.md`](docs/FOR-SALE-ISLANDS.md). Machine registry:
`data/discovery/property_listings_registry.json`. Weekly refresh: Cursor skill
`.cursor/skills/weekly-island-property-discovery/SKILL.md` or
`python3 scripts/run_property_discovery_weekly.py`. Pipeline detail:
[`docs/PROPERTY-LISTINGS.md`](docs/PROPERTY-LISTINGS.md).

### OS Maps detail view

The island details panel includes a second Leaflet map (`#detail-map`,
`renderDetailMap` in `app.js`). When an OS Maps API key is configured
(`window.OS_MAPS_API_KEY` or `localStorage.osMapsApiKey`), the basemap is
**OS Outdoor** (EPSG:3857) from the OS DataHub ZXY endpoint. Otherwise
OpenStreetMap is used as a graceful fallback. Full setup, attribution
rules, and the upgrade path to EPSG:27700 OS Leisure live in
[`docs/OS-MAPS.md`](docs/OS-MAPS.md).

## 5. How to make changes safely

1. **Update `STATE.md` "Currently running"** before kicking off any long script,
   and clear it when done.
2. **Add a `SESSION-LOG.md` entry** for every session that materially changes
   data, schema, or behaviour. One entry per session, append-only.
3. **When you finish a queue item**, move it from `QUEUE.md` to `SESSION-LOG.md`
   with a short outcome note.
4. **When you change the schema**, update `DATA-SCHEMA.md` in the same diff.
5. **When you discover a new methodology**, write it into a new
   `docs/METHODOLOGY-<topic>.md` and link from `INDEX.md`.
6. **Validation**: run mental or actual regression against
   `docs/VALIDATION.md` before declaring a data run successful.

## 6. Tone & UX principles (carried forward)

- Visual-first. Photos and the map matter as much as the data.
- Performance: the dataset is large (6k+ islands). Always use marker clustering
  and virtualised lists.
- Respectful naming. Gaelic / Welsh / Irish / Manx / Scots / Cornish names are
  preserved alongside English where known (see ETHICS §4).
- Accessibility: list items are real `<button>`s; map markers have tooltips.

## 7. If you're stuck

- Bizarre data: check `data/*_report.json` — every pipeline writes an audit
  trail.
- Schema confusion: `docs/DATA-SCHEMA.md` with examples.
- "How was X classified?" `inland_classification_report.json` keyed by island
  id.
- "Why is this image here?" `image_enrichment_report.json` with sourcePageUrl.
- "How do I rebuild from scratch?" `docs/PIPELINE.md`.
