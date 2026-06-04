# Frontend performance

How the homepage loads ~7,000 islands without blocking the main thread for tens of seconds.

## Design goal

**Interactive within ~7 s** on typical 4G; list + map shell often **1–3 s**. Markers and ferries fill in after first paint.

## Critical path (~400 KB gzip)

| Asset | ~Size (gzip) | Blocking? |
|-------|----------------|-----------|
| `index.html` | 8 KB | yes |
| Leaflet + markercluster (unpkg) | ~55 KB | sync scripts |
| `app.js` + imports | ~90 KB | module |
| **`data/islands_index.json`** | **~196 KB** | yes (loader) |
| Google Fonts | ~120–200 KB | optional delay |
| **proj4** | — | **deferred** (detail map only) |
| **Three.js / island-3d** | — | **deferred** (showcase profiles) |

Monolithic **`data/islands.json`** (~2.1 MB gzip) is **not** fetched on findmyisland.com when index succeeds.

## Index v2 format

Built by `scripts/build_islands_index.py`:

```json
{ "version": 2, "rows": [ { "id", "n", "y", "x", "t", "o", … } ] }
```

Expanded in `app.js` via `parseIndexPayload()` → `expandIndexRow()`. Short keys save ~90% vs old 12 MB list payload.

**Named** rows → `islands_index.json` (7,041). **Unnamed** (`nameStatus: unknown`) → `islands_unnamed_index.json` (4,310), loaded only for Unnamed filter or `?island=osm-…` URLs.

## Boot sequence (`loadIslands`)

```
setAppLoading(true)
  → await _indexPayloadPromise (started at module init)
  → state.islands / state.byId
  → applyFilters({ skipMarkers: true, skipSort: true })
  → applyRouteFromUrl()
  → rAF × 2
  → setAppLoading(false)          ← loader hides here
  → runWhenIdle:
       rebuildMarkerLayer({ chunked: true })
       loadCrowdPins, loadFerries, featured, discovery
```

### Do not regress

- **No eager shard preload** — `ensureNationShardLoaded(nation)` on profile open only.
- **No full-table sort on boot** — sort runs when user searches/filters.
- **No sync proj4** in `index.html`.
- **No static import** of `island-3d.js` in `app.js` (dynamic `import()` only).

## Markers

| Mechanism | Purpose |
|-----------|---------|
| `islandsForMarkerPaint()` | Viewport cull (all islands visible at zoom ≤7 UK view) |
| `rebuildMarkerLayer({ chunked })` | 350 markers per `requestAnimationFrame` after idle |
| `markerBootGraceUntil` | Suppress duplicate rebuild on first `moveend` |
| Lazy tooltips | No `bindTooltip` at zoom ≤7 until hover |
| `propertyListingMapLayer` | For-sale £ badges (not in main cluster) |

## Deferred (idle / on demand)

| Fetch | Trigger |
|-------|---------|
| `data/ferries.json` + terminals + operators | `requestIdleCallback` after boot |
| `data/discovery_topics.json` | idle |
| `data/featured_islands.json` | idle |
| `data/crowd_pins.json` | idle |
| `data/shards/{nation}.json` | Profile open |
| `data/islands_unnamed_index.json` | Unnamed filter |
| `data/galleries.json` | Island click |

## Profile open (double render)

`focusIsland()` calls `renderDetails()` twice when shard not merged:

1. Stub from index (immediate)
2. Full record after `ensureNationShardLoaded`

3D terrain uses **`scheduleIsland3DMount()`** with a generation token so only the final mount wins. See [`3D-TERRAIN.md`](3D-TERRAIN.md).

## HTML optimisations

```html
<link rel="preload" href="data/islands_index.json" as="fetch" crossorigin="anonymous" />
<link rel="modulepreload" href="app.js" />
```

## Troubleshooting

| Symptom | Check |
|---------|--------|
| Loader stuck >7 s | Network tab: `islands.json` fallback? Index 404? |
| Loader gone, map empty | `rebuildMarkerLayer` early return (bounds); pan map |
| Slow repeat visit | CDN `max-age=600`; normal |
| List thumbs missing | Expected until shard merge (stubs have `hasImage` flag only) |

## Regenerate after data change

```bash
python3 scripts/build_islands_index.py
# Commit data/islands_index.json, islands_unnamed_index.json, data/shards/
# Or rely on CI on push to main
```

## Related

- [`DEPLOYMENT.md`](DEPLOYMENT.md) — `_site/` artifact
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — broader frontend map
- [`AGENT-QUICKREF.md`](AGENT-QUICKREF.md) — one-page summary
