# 3D terrain viewer

Interactive heightmap models for **10 showcase islands**, rendered with Three.js from pre-generated Terrarium DEM tiles.

## Showcase islands

| ID | Name | Nation |
|----|------|--------|
| `staffa` | Staffa | Scotland |
| `iona` | Iona | Scotland |
| `st-kilda` | St Kilda (Hirta) | Scotland |
| `fair-isle` | Fair Isle | Scotland |
| `inchcailloch` | Inchcailloch | Scotland |
| `lindisfarne` | Lindisfarne | England |
| `lundy` | Lundy | England |
| `brownsea` | Brownsea Island | England |
| `burgh-island` | Burgh Island | England |
| `rathlin` | Rathlin Island | Northern Ireland |

Also listed in `SHOWCASE_3D_ISLAND_META` in `island-3d.js` and `data/terrain/manifest.json`.

## Files

| Path | Role |
|------|------|
| `island-3d.js` | Three.js viewer: fetch terrain, build mesh, OrbitControls |
| `data/terrain/{id}.json` | Height grid + bounds per island |
| `data/terrain/manifest.json` | Index of generated tiles |
| `showcase-3d.html` | Gallery page with all 10 viewers |
| `scripts/build_island_terrain.py` | Regenerate terrain from Mapzen Terrarium tiles |

Attribution (in manifest): Mapzen Terrarium on AWS Open Data.

## Import map requirement

`OrbitControls` imports bare `"three"`. **Every page that loads `island-3d.js` must define:**

```html
<script type="importmap">
  {
    "imports": {
      "three": "https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.js",
      "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.170.0/examples/jsm/"
    }
  }
</script>
```

Present in **`index.html`** and **`showcase-3d.html`**. Missing import map → error:

> Module name, 'three' does not resolve to a valid URL.

`island-3d.js` imports:

```javascript
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
```

## Atlas integration (`app.js`)

- **No static import** of `island-3d.js` (keeps homepage lean).
- `loadIsland3dModule()` → dynamic `import("./island-3d.js")`.
- `isShowcase3DIsland(id)` — inline `SHOWCASE_3D_IDS` set (matches terrain manifest).
- **`scheduleIsland3DMount(island)`** — called from `focusIsland()` after `renderDetails()`, not inside `renderDetails` directly.

### Mount lifecycle (avoid blank box)

Opening a profile triggers **two** `renderDetails()` calls (stub, then shard merge). Mount logic:

1. `cancelTerrainMount()` — bump generation token before wiping DOM
2. `destroyIsland3D(prev)` on old container
3. After layout (rAF × 2), `mountIsland3D()` on new `#island-3d-view`
4. Stale mounts abort when `gen !== _terrainMountGen`

Errors surface in the viewer box (no silent `.catch()`).

## Terrain JSON shape

Accepted fields (normalised in `normalizeTerrain()`):

- Grid: `gridW` / `gridH` (or `cols` / `rows`)
- Heights: `heights` or `elevations` (flat array; `null` = sea)
- `bounds`: `[west, south, east, north]` or object
- `minElev`, `maxElev`

## Regenerate terrain

```bash
python3 scripts/build_island_terrain.py              # all showcase ids
python3 scripts/build_island_terrain.py --ids staffa,iona
python3 scripts/build_island_terrain.py --cache       # reuse tile cache
```

Commit `data/terrain/` — force-included in Pages artifact via `prepare_pages_artifact.py`.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| “three does not resolve…” | Add import map to page |
| Blank dark box, no text | Check mount race / import failure in console |
| “Terrain tile not generated yet” | 404 on `data/terrain/{id}.json`; run build script + deploy |
| “WebGL unavailable” | Browser/GPU blocked WebGL |
| Works on showcase page, not atlas | import map missing on `index.html` |

## Related

- [`FRONTEND-PERFORMANCE.md`](FRONTEND-PERFORMANCE.md) — why 3D is deferred
- [`DEPLOYMENT.md`](DEPLOYMENT.md) — terrain in `_site/`
