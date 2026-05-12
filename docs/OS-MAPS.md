# Ordnance Survey Maps integration

The per-island details panel renders a **second, navigable Leaflet map**
centred on the island. Three basemaps are available, shown via a small
button row above the map:

| Basemap     | Projection   | Coverage           | Notes |
| ----------- | ------------ | ------------------ | ----- |
| OS Leisure  | EPSG:27700   | Great Britain only | The paper-style OS Explorer 1:25k / Landranger 1:50k raster. Footpaths, contours, named features. Default when available. |
| OS Outdoor  | EPSG:3857    | UK-wide            | Web-mercator OS cartography. Faster, wider coverage, less detailed. |
| OSM         | EPSG:3857    | Worldwide          | Universal fallback. No API key required. |

Selection priority:

1. Saved preference (`localStorage.detailBasemap`) if still available for
   this island.
2. Otherwise Leisure if available (key set, island is in GB, proj4leaflet
   loaded).
3. Otherwise Outdoor (key set, but island outside GB or proj4leaflet
   missing).
4. Otherwise OSM.

Disabled buttons show users what would unlock with a key / inside GB.

---

## What ships today

- A second Leaflet map (`#detail-map`) is mounted inside the details panel
  in `app.js` via `renderDetailMap(island)`.
- Basemap switcher (`#detail-map-switcher`) renders three pill buttons:
  Leisure / Outdoor / OSM. Clicking destroys and rebuilds the Leaflet
  instance with the new CRS (Leisure → EPSG:27700, others → EPSG:3857).
- BNG CRS is built lazily and cached via `getBngCrs()`. proj4 +
  proj4leaflet are loaded from unpkg before `app.js` (≈98 KB combined).
- The detail map's basemap preference is persisted in
  `localStorage.detailBasemap` so it survives island switches and page
  reloads.
- API key resolution:
  1. `window.OS_MAPS_API_KEY` — set this in an untracked `config.local.js`
     loaded **before** `app.js`.
  2. `localStorage.osMapsApiKey` — settable interactively from the browser
     devtools (useful for QA without redeploys).
  3. No key → only OSM is enabled, with a hint explaining how to unlock.
- Auto-zoom: each basemap has its own zoom band because they have very
  different scale resolutions.
  - Leisure (z=0..9): river → z9, <0.5 km² → z9, <5 km² → z8, <50 km² → z7, else z6.
  - Outdoor / OSM: river → z15, <0.5 km² → z14, <5 km² → z13, <50 km² → z12, else z11.
- A circle marker pins the island on every basemap.
- The Leaflet instance is torn down on island switch, basemap switch and
  "back to list" so we don't leak tile requests / event listeners.

### OS DataHub tile endpoints used

```
# Leisure (EPSG:27700 — paper-style detail, GB only)
https://api.os.uk/maps/raster/v1/zxy/Leisure_27700/{z}/{x}/{y}.png?key={KEY}

# Outdoor (EPSG:3857 — web-mercator)
https://api.os.uk/maps/raster/v1/zxy/Outdoor_3857/{z}/{x}/{y}.png?key={KEY}
```

Other EPSG:3857 styles available with the same key, swap the path segment:

| Style              | Path                  | Notes                                  |
| ------------------ | --------------------- | -------------------------------------- |
| Road               | `Road_3857`           | Clean cartography, good at low zoom.   |
| Outdoor            | `Outdoor_3857`        | Contours, footpaths, web-mercator.     |
| Light              | `Light_3857`          | Muted base for thematic overlays.      |
| Leisure _(BNG)_    | `Leisure_27700`       | Paper-style 1:25k/1:50k. GB only.      |

**Attribution** (Crown copyright) is rendered in Leaflet's attribution
control and is required by the OS Open Data Terms.

### BNG CRS definition (EPSG:27700)

For reference, the CRS used by `getBngCrs()` in `app.js`:

```js
new L.Proj.CRS(
  "EPSG:27700",
  "+proj=tmerc +lat_0=49 +lon_0=-2 +k=0.9996012717 " +
    "+x_0=400000 +y_0=-100000 +ellps=airy " +
    "+towgs84=446.448,-125.157,542.06,0.15,0.247,0.842,-20.489 " +
    "+units=m +no_defs",
  {
    origin: [-238375.0, 1376256.0],
    resolutions: [896, 448, 224, 112, 56, 28, 14, 7, 3.5, 1.75],
    bounds: L.bounds([-238375.0, 0.0], [900000.0, 1376256.0]),
  },
)
```

Resolutions and origin match the OS DataHub Leisure_27700 tile matrix set.

---

## Getting an API key

1. Sign up for free at **<https://osdatahub.os.uk/>**.
2. Create a project, add **OS Maps API**.
3. Copy the project's API key.
4. Either:
   - Open the site, open devtools, run
     `localStorage.osMapsApiKey = "YOUR_KEY"`, then reload, **or**
   - Create `config.local.js` next to `index.html`:
     ```js
     window.OS_MAPS_API_KEY = "YOUR_KEY";
     ```
     and add a `<script src="config.local.js"></script>` tag **before**
     `<script src="app.js"></script>` in `index.html`. Add
     `config.local.js` to `.gitignore`.

The free tier currently allows 250 transactions/second and ~1m per month —
plenty for an interactive atlas.

---

## Future work

- **Northern Ireland coverage**: Leisure is GB only. NI uses OSNI's "Land
  & Property Services" tiles, which are not served via OS DataHub. We
  currently fall back to Outdoor/OSM for NI islands. Long-term: add an
  OSNI tile source as a fourth basemap when the island's nation is
  Northern Ireland.
- **Ireland coverage**: OSi (Ordnance Survey Ireland) publishes the
  similar "OSi Discovery" raster via their own portal. Same shape of
  integration as OSNI.
- **Channel Islands / Isle of Man**: no detailed raster equivalent is
  freely available; OSM is the practical best.
- **Lazy-init the detail map**: today we build the Leaflet instance the
  moment a user clicks an island. If a Leisure tile fetch is in flight
  and they click another island fast, we cancel via `.remove()`. That's
  fine, but we could defer init by an IntersectionObserver if profiling
  shows it's a problem.

---

## Privacy and ethics

- Keys are read client-side from the user's browser; we never proxy them
  through our infrastructure, so each visitor pays their own quota.
- We don't log tile requests anywhere.
- Attribution is always rendered, per OS terms.

---

## Troubleshooting

| Symptom                                        | Likely cause                                                       |
| ---------------------------------------------- | ------------------------------------------------------------------ |
| OS toggle missing in layers control            | No key found. Check `getOsMapsKey()` in console.                   |
| OS tiles 401/403                               | Key wrong, project doesn't have OS Maps API enabled, or quota hit. |
| Map is grey                                    | Container hidden when initialised — `invalidateSize()` runs at 60 ms; if the panel is still hidden, the issue is upstream. |
| Wrong zoom for tiny islands                    | Adjust the size-band thresholds in `renderDetailMap()`.            |
