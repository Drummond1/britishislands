# Architecture

How this project is wired together. Skim this before touching frontend or
ingestion code.

## 1. Top-level layout

```
.
├── Frontend (no build step)
│   ├── index.html          ← page shell, script + CSS links
│   ├── styles.css          ← all styling (CSS variables for theme)
│   ├── app.js              ← ES module entrypoint
│   └── seo-meta.js         ← per-island <title>, meta, OG/Twitter, JSON-LD
│
├── Data (canonical artefacts)
│   ├── data/islands.json   ← THE dataset shipped to the browser
│   ├── data/curated.json   ← hand-curated 27-island spine
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

```
┌────────────────────┐
│ index.html         │
│  loads app.js      │
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐    fetch    ┌──────────────────────┐
│ app.js init()      │───────────▶│ data/islands.json    │
└─────────┬──────────┘             └──────────────────────┘
          │
          ├── populateNationFilter()        (build filter UI)
          ├── renderList()                  (virtualised sidebar list)
          ├── plotMarkers()                 (marker cluster on map)
          └── on click(island) →
                renderDetails(island)       (right-side detail panel)
                └── (optional) loadAndShowPolygon(island)
                      └── fetch Overpass for osm{Type,Id} → GeoJSON overlay
                            └── caches in memory for the session
```

### Key UI affordances

- **Marker clustering** is on by default. The `#cluster-toggle` checkbox in
  the topbar switches between cluster mode (default for 6k+) and raw markers
  (debug only).
- **Virtualised list**: `renderListWindow()` only renders ~30 visible items.
  Items are `<button>` elements, not divs, for accessibility.
- **Polygon overlay**: lazy. We do not pre-load 6k polygons; we fetch on click
  for any island with `osmId`. Cached per session.
- **Tooltips, not popups** on markers — cleaner for dense clusters.
- **OS Maps**: `OS_MAPS_API_KEY` placeholder is in `app.js`. When set, the
  Leisure layer becomes a basemap option. Detail-view OS map is **not yet
  wired** (see `QUEUE.md` P1.2).

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

`app.js` exports nothing — it is a self-contained entrypoint. Function index:

| Function | Role |
|---|---|
| `init()` | bootstraps map, fetches `islands.json`, wires UI events |
| `populateNationFilter(islands)` | builds nation `<select>` from data |
| `applyFilters()` | computes filtered island set (search + nation) |
| `renderList(islands)` | top-level list render; calls `renderListWindow` |
| `renderListWindow(islands)` | virtualised window (renders ~30 items) |
| `ensureListScaffolding()` | sets up the spacer divs for virtual scroll |
| `plotMarkers(islands)` | (re)renders the Leaflet marker layer / cluster |
| `makeMarker(island)` | builds a `circleMarker` sized by `areaKm2` |
| `focusIsland(id)` | flies the map and opens the detail panel |
| `renderDetails(island)` | renders the right-hand details panel |
| `loadAndShowPolygon(island)` | lazy-fetches and overlays the OSM polygon |
| `fetchOsmPolygon(osmType, osmId)` | Overpass call for one element |
| `overpassToGeoJSON(elements)` | Overpass elements → GeoJSON Polygon |
| `fitToPolygon(layer)` | zooms map to a polygon layer |
| `setPolyStatus(message)` | sets the inline polygon-loading status string |
| `formatArea`, `formatPopulation`, `capitalize`, `escapeHtml` | helpers |

When the dataset changes shape, **update both** the relevant pipeline script
**and** `renderDetails` in the same diff.

## 6. Networking & rate limits

| Service | Used by | Polite-fetch posture |
|---|---|---|
| Overpass (`overpass-api.de`) | `fetch_islands.py`, `classify_inland.py`, browser polygon overlay | 1 rps; rotating endpoint list; respect 429; cached in `*_raw.json` |
| Wikidata SPARQL | `enrich_images.py`, discovery scripts | 5 s timeout per query; cached; UA includes contact email |
| MediaWiki API (en.wikipedia.org) | `enrich_images.py` | batched (50 per call); cached in `cache_pageimages.json` |
| Wikimedia Commons API | `enrich_images.py` | batched; cached in `cache_commons.json` |
| OS Maps API | `app.js` (planned detail view) | API key in `.env.local`; client-side only; free tier = 250k tiles/mo |

All HTTP clients in `scripts/` set a contactable `User-Agent` per Wikimedia
policy.

## 7. Deployment

Currently: **local-only**. The whole site is static so it deploys cleanly to
any static host (GitHub Pages, Cloudflare Pages, Netlify) once we're ready.
The OS Maps key would need to be a referrer-restricted public key (or proxied
via a tiny edge function) for production.
