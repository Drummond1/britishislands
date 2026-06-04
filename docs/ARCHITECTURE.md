# Architecture

How this project is wired together. Skim this before touching frontend or
ingestion code.

## 1. Top-level layout

```
.
├── Frontend (no build step)
│   ├── index.html          ← page shell, script + CSS links
│   ├── styles.css          ← all styling (CSS variables for theme)
│   ├── app.js              ← ES module entrypoint (map, list, chat, details)
│   ├── island-3d.js        ← Three.js terrain (dynamic import only)
│   ├── crowd-pins.js       ← community pins
│   └── seo-meta.js         ← per-island head tags + JSON-LD
│
├── Data (canonical artefacts)
│   ├── data/islands.json              ← canonical full dataset (local / CI source)
│   ├── data/islands_index.json        ← v2 compact first paint (~0.9 MB)
│   ├── data/islands_unnamed_index.json← lazy unnamed overlay (~0.8 MB)
│   ├── data/shards/*.json             ← nation shards (on-demand profile merge)
│   ├── data/terrain/*.json            ← 3D heightmaps (10 showcase islands)
│   ├── data/curated.json              ← hand-curated 27-island spine
│   ├── data/*_raw.json     ← cached upstream API responses
│   ├── data/cache_*.json   ← per-script polite-fetch caches
│   ├── data/candidates_*.json ← pre-merge discovery candidates
│   └── data/*_report.json  ← audit trails (provenance)
│
├── Ingestion (Python, no framework)
│   └── scripts/*.py        ← OSM, Wikidata, MediaWiki, classifier, enrichment
│
└── Docs
    ├── AGENTS.md           ← orientation entry point
    └── docs/*.md           ← everything else
```

## 2. Runtime data flow (browser)

Production uses a **split payload** — not monolithic `islands.json` on findmyisland.com.

```
index.html
  ├── import map (Three.js — for dynamic island-3d load)
  ├── preload islands_index.json
  ├── Leaflet + markercluster (sync)
  └── app.js (module)
        ├── _indexPayloadPromise → data/islands_index.json  (~0.9 MB, v2 compact)
        ├── applyFilters (list only; skip markers + sort on boot)
        ├── setAppLoading(false)
        └── idle → rebuildMarkerLayer (chunked) + ferries/crowd/featured

On profile open:
  ensureNationShardLoaded(nation) → data/shards/{slug}.json
  renderDetails(island)
  scheduleIsland3DMount(island)     → dynamic import island-3d.js
                                    → data/terrain/{id}.json

On “Unnamed” filter:
  loadUnnamedIslandOverlay() → data/islands_unnamed_index.json
```

See [`FRONTEND-PERFORMANCE.md`](FRONTEND-PERFORMANCE.md) for boot timing and troubleshooting.

### Key UI affordances

- **Marker clustering** on by default (`#cluster-toggle`).
- **Virtualised list**: ~30 visible `<button>` rows.
- **Polygon overlay**: lazy Overpass fetch on click; session cache.
- **Tooltips** on markers (lazy at zoom ≤7).
- **OS Maps detail map**: Leisure / Outdoor / OSM switcher; proj4 loaded on demand.
- **3D terrain**: 10 showcase islands; see [`3D-TERRAIN.md`](3D-TERRAIN.md).

## 3. Build-time data flow (ingestion)

```
                  ┌─────────────────────────────┐
                  │ scripts/fetch_islands.py    │
                  │ Overpass: place=island      │
                  │   + curated.json merge      │
                  └────────────┬────────────────┘
                               │ writes
                               ▼
                  ┌─────────────────────────────┐
                  │ data/osm_raw.json (cache)   │
                  │ data/islands.json (v0)      │
                  └────────────┬────────────────┘
                               │
                  ┌────────────▼────────────────┐
                  │ scripts/classify_inland.py  │
                  │ Overpass: natural=water     │
                  │  Tier A: inner-ring extract │
                  │  Tier B: point-in-polygon   │
                  └────────────┬────────────────┘
                               │ writes / mutates
                               ▼
                  ┌─────────────────────────────┐
                  │ data/water_raw.json (cache) │
                  │ data/inland_classification_ │
                  │      report.json            │
                  │ data/islands.json (v1)      │
                  └────────────┬────────────────┘
                               │
                  ┌────────────▼────────────────┐
                  │ (discovery extension scripts)│
                  │  Wikidata SPARQL, Thames,   │
                  │  crannogs, designations …   │
                  └────────────┬────────────────┘
                               │
                  ┌────────────▼────────────────┐
                  │ data/candidates_*.json      │
                  │ data/discovery_ingestion_   │
                  │      report.json            │
                  │ data/islands.json (v2)      │
                  └────────────┬────────────────┘
                               │
                  ┌────────────▼────────────────┐
                  │ scripts/enrich_images.py    │
                  │  Wikidata P18 → Wikipedia   │
                  │  pageimages → Commons       │
                  └────────────┬────────────────┘
                               │ writes
                               ▼
                  ┌─────────────────────────────┐
                  │ data/image_enrichment_      │
                  │      report.json            │
                  │ data/islands.json (final)   │
                  └─────────────────────────────┘
```

Every script:

- **Reads & writes a cache** (`data/cache_*.json` or the relevant `*_raw.json`)
  so reruns are cheap and reproducible.
- **Writes an audit report** (`data/*_report.json`) keyed by island id.
- **Logs at INFO/WARN** to stdout so the run can be tailed.
- **Is idempotent**: rerunning produces the same dataset (modulo upstream API
  changes).

See [`PIPELINE.md`](PIPELINE.md) for the exact run order and CLI flags.

## 4. Key invariants

- `data/islands.json` is **always a JSON array** of island records matching
  [`DATA-SCHEMA.md`](DATA-SCHEMA.md).
- **Every island has a stable `id`**: lowercased, hyphenated, ASCII-folded
  name; collisions disambiguated by parent body or island group. IDs are
  stable across runs.
- **Curated entries are never deleted** by any pipeline; they are the spine
  for regression and merge tiebreakers.
- **Pipelines write to a `.before-ingest` backup** of `islands.json` before
  mutating it (see `data/islands.json.before-ingest`).
- **All images have provenance**. An `images[i]` without `source`, `license`,
  and `sourcePageUrl` is a bug.

## 5. Frontend module map

`app.js` is the main entrypoint (~8k lines). Key areas by comment block:

| Area | Functions / notes |
|------|-------------------|
| Data load | `loadIslands`, `parseIndexPayload`, `ensureNationShardLoaded`, `loadUnnamedIslandOverlay` |
| Filters / list | `applyFilters`, `renderList`, `renderListWindow`, `_scoreIsland` |
| Markers | `rebuildMarkerLayer`, `makeMarker`, `islandsForMarkerPaint` |
| Details | `focusIsland`, `renderDetails`, `renderDetailMap`, `loadAndShowPolygon` |
| 3D terrain | `scheduleIsland3DMount`, `loadIsland3dModule` (see `island-3d.js`) |
| Chat | `CHAT_*` dictionaries, `chatAutoLoadFromUrl` |
| Ferries | `loadFerries`, trip planner, `refreshFerriesInPlace` |

When the dataset shape changes, update the relevant pipeline **and** `renderDetails` in the same diff.

## 6. Networking & rate limits

| Service | Used by | Polite-fetch posture |
|---|---|---|
| Overpass (`overpass-api.de`) | `fetch_islands.py`, `classify_inland.py`, browser polygon overlay | 1 rps; rotating endpoint list; respect 429; cached in `*_raw.json` |
| Wikidata SPARQL | `enrich_images.py`, discovery scripts | 5 s timeout per query; cached; UA includes contact email |
| MediaWiki API (en.wikipedia.org) | `enrich_images.py` | batched (50 per call); cached in `cache_pageimages.json` |
| Wikimedia Commons API | `enrich_images.py` | batched; cached in `cache_commons.json` |
| OS Maps API | `app.js` detail map | Client key; proj4 on demand; see [`OS-MAPS.md`](OS-MAPS.md) |

All HTTP clients in `scripts/` set a contactable `User-Agent` per Wikimedia
policy.

## 7. Deployment

**Production:** https://www.findmyisland.com via GitHub Pages (`main` → `.github/workflows/pages.yml`).

CI builds `_site/` with `prepare_pages_artifact.py` (shards, profiles, terrain; **no** monolithic `islands.json`). Push workflow changes via **SSH** if HTTPS OAuth lacks `workflow` scope.

Full detail: [`DEPLOYMENT.md`](DEPLOYMENT.md). Agent cheat sheet: [`AGENT-QUICKREF.md`](AGENT-QUICKREF.md).
