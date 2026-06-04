# Agent quick reference

> **One-page orientation** for a fresh session. Read this after `AGENTS.md` when you
> need to act fast without replaying chat history. Deep dives link out.

## Production

| Item | Value |
|------|--------|
| Live site | https://www.findmyisland.com |
| GitHub repo | `Drummond1/britishislands` |
| Branch | `main` → auto-deploy via `.github/workflows/pages.yml` |
| Push workflow files | Use **SSH** (`git@github.com:…`); HTTPS OAuth lacks `workflow` scope |

## Dataset scale (2026-05-31)

| Artefact | Count / size | Role |
|----------|----------------|------|
| `data/islands.json` | **11,351** islands (~27 MB) | Canonical; **not** on production CDN |
| `data/islands_index.json` | **7,041** named stubs (~0.9 MB) | Homepage first paint |
| `data/islands_unnamed_index.json` | **4,310** (~0.8 MB) | Lazy overlay (Unnamed filter / OSM URLs) |
| `data/shards/*.json` | 7 nations (~19 MB) | Full records on profile open |
| `data/terrain/*.json` | **10** showcase islands | 3D heightmaps |
| `profiles/*.html` | ~11k static landings | SEO / crawlers |

Regenerate index + shards after any `islands.json` edit:

```bash
python3 scripts/build_islands_index.py
```

## “If X is broken, read Y”

| Symptom | First doc | Likely cause |
|---------|-----------|--------------|
| Homepage slow / stuck on “Loading the atlas…” | [`FRONTEND-PERFORMANCE.md`](FRONTEND-PERFORMANCE.md) | Index fetch, marker rebuild, monolith fallback |
| Blank 3D terrain box / Three.js error | [`3D-TERRAIN.md`](3D-TERRAIN.md) | Missing import map, mount race, terrain 404 |
| Shards or profiles 404 on live site | [`DEPLOYMENT.md`](DEPLOYMENT.md) | `_site/` artifact, Pages source setting |
| Schema / field confusion | [`DATA-SCHEMA.md`](DATA-SCHEMA.md) | |
| Ingestion / rebuild | [`PIPELINE.md`](PIPELINE.md) + [`STATE.md`](STATE.md) | |
| Orange unnamed pins | `discover_unnamed_islands.py` + `nameStatus: "unknown"` in schema | |
| For-sale listings | [`FOR-SALE-ISLANDS.md`](FOR-SALE-ISLANDS.md) | |

## Frontend boot sequence (happy path)

1. `index.html` — import map (Three.js), preload `islands_index.json`, Leaflet sync scripts (**no** proj4).
2. `app.js` — `_indexPayloadPromise` starts fetch; map init; `loadIslands()`.
3. Parse v2 index → `expandIndexRow()` → `applyFilters({ skipMarkers, skipSort })` → list paints.
4. `setAppLoading(false)` → `runWhenIdle` → chunked `rebuildMarkerLayer()`.
5. Profile click → `ensureNationShardLoaded(nation)` merges full record → `renderDetails` + `scheduleIsland3DMount`.

**Never** eager-load all shards or `islands.json` on findmyisland.com.

## Key files (frontend)

| File | Role |
|------|------|
| `app.js` | Map, list, filters, chat, details, load orchestration |
| `island-3d.js` | Three.js terrain (dynamic import only) |
| `crowd-pins.js` | Community pins |
| `seo-meta.js` | Per-island head tags in-browser |
| `scripts/build_islands_index.py` | v2 compact index + shards |
| `scripts/prepare_pages_artifact.py` | Stages `_site/` for Pages |

## Hard rules (reminder)

- No island without provenance; no image without licence in `images[]`.
- Never delete curated islands.
- Update `DATA-SCHEMA.md` if schema changes.
- Append `SESSION-LOG.md` after material sessions; update `STATE.md` counts.
- Check `STATE.md` “Currently running” before long write pipelines.

## Doc map

| Tier | Files |
|------|--------|
| Always | `AGENTS.md` → `STATE.md` → `QUEUE.md` → this file |
| Deploy | [`DEPLOYMENT.md`](DEPLOYMENT.md) |
| Perf | [`FRONTEND-PERFORMANCE.md`](FRONTEND-PERFORMANCE.md) |
| 3D | [`3D-TERRAIN.md`](3D-TERRAIN.md) |
| Architecture | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
