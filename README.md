# Isles of Britain — Visual Atlas

An interactive web atlas of **6,776 islands** in and around the British
Isles — sea, lake and river — pulled from OpenStreetMap, deduplicated,
merged with hand‑curated entries, cross-referenced against Wikidata
(CC0), Wikipedia's "Islands in the River Thames" wikitable (CC BY-SA),
and Wikipedia's Crannog categories. A two‑tier classifier discovers
inland islands (and their parent lake / river) by walking OSM
multipolygons. Each island can be clicked to fetch and overlay its real
polygon outline, see local-language names, scroll a photo gallery, and
get every published ferry route serving it.

It's a static site — no build step, no backend.

## What ships in the live build

| Layer | Count |
|---|---|
| Islands across UK + IE + Crown Dependencies | **6,776** |
| With a primary photo (Wikidata P18 / Wikipedia / Commons) | **3,359** |
| With additional lazy-loaded gallery photos | **3,180** islands · 8,953 extra photos |
| Carrying a Wikidata Q-ID | **2,726** |
| Carrying ≥ 1 non-English label (gd / cy / ga / gv / kw / sco / fr / nrf) | **961** |
| Ferry routes | **347** routes across **54 operators** |
| Canonical ferry terminals | **903** (366 island-matched, 535 mainland with drive-times from London/Glasgow/Edinburgh/Belfast/Dublin) |
| Tidal causeways / bridges | **11** |

See [`docs/STATE.md`](docs/STATE.md) for the live snapshot, and
[`docs/FERRIES.md`](docs/FERRIES.md) for the ferry feature.

## What's in the prototype

- **6,741 islands** across Scotland (3,118), Ireland (1,852), England (953),
  Northern Ireland (469), Wales (187) and the Crown Dependencies (162 —
  Isle of Man + Channel Islands). Essentially every named island OSM knows
  about in the UK / Irish bbox, plus 127 inland islands the classifier
  discovered from water-body inner rings, plus 859 Wikidata-only islands,
  22 named Thames eyots, and 4 Wikipedia-categorised crannogs.
- Type breakdown: **5,382 sea**, **1,097 lake**, **262 river**.
- **2,698** islands carry a Wikidata Q-ID (cross-referenced for image
  enrichment + future linkage).
- **2,506** islands carry **multilingual names** — Gaeilge, Gàidhlig,
  Cymraeg, Gaelg, Kernewek — surfaced in the detail panel under the title.
- **2,533** islands carry an explicit `sources` provenance block with
  per-source name, URL, licence, and attribution, rendered in the
  "Sources & attribution" section of the detail panel.
- Each inland island carries its **parent water body** (Loch Lomond, Lower
  Lough Erne, Windermere, the Thames, …) and a **classification audit**
  (which tier classified it, with what confidence).
- **Interactive Leaflet map** with marker clustering (`Leaflet.markercluster`)
  so ~6,700 markers render smoothly. Toggle clustering on/off in the toolbar.
- **Virtualised sidebar list** so 6,700 entries don't choke the DOM.
  Filter by name/region/tag, by island type (sea / lake / river), and by
  nation.
- **Detail view** per island:
  - Curated entries: hero photo, key stats grid, history, geography,
    transport, accommodation, and external links.
  - OSM‑sourced entries: the same skeleton, gracefully indicating it's a
    crowd‑sourced entry and linking back to OSM/Wikipedia/Google Maps.
- **Lazy polygon overlay** — when you click an island, the app queries
  Overpass for the OSM way/relation geometry and overlays the actual
  shape on the map (cached per session so re‑opens are instant). Works
  for ~24 of 27 curated entries and any OSM-sourced entry tagged as a
  way or relation.
- **Base‑map switcher** with five free layers and a wired‑up hook for
  Ordnance Survey Maps (paste your key in `app.js`).

## Run it

It's a plain static site — no build step.

```bash
python3 -m http.server 8767      # then open http://localhost:8767
```

> Open via `http://`, not `file://` — the app loads JSON via `fetch`,
> which browsers block on the `file://` scheme.

## Project structure

```
.
├── index.html                            # Page shell + Leaflet + Markercluster + base-map picker
├── styles.css                            # Dark UI theme
├── app.js                                # Map, list, filters, details, polygon fetch, base-map switching
├── data/
│   ├── curated.json                      # 27 hand-written entries with rich descriptions
│   ├── osm_raw.json                      # Cached: ~5,800 named offshore islands from Overpass
│   ├── water_raw.json                    # Cached: ~9,200 UK water multipolygons from Overpass
│   ├── inland_classification_report.json # Audit trail: per-island Tier A / Tier B verdicts
│   ├── image_enrichment_report.json      # Audit trail: image source / spot-check / mismatch flags
│   ├── discovery_ingestion_report.json   # Audit trail: per-source ingestion counts + provenance
│   ├── cache_wd_islands.json             # Cached Wikidata island SPARQL (by-country)
│   ├── cache_wikidata.json               # Cached Wikidata SPARQL responses (P18 + label/desc)
│   ├── cache_pageprops.json              # Cached MediaWiki pageprops (Wikipedia → Q-ID)
│   ├── cache_pageimages.json             # Cached MediaWiki pageimages lookups
│   ├── cache_commons.json                # Cached Commons imageinfo (license + author)
│   ├── cache_thames.json                 # Cached Wikipedia 'Islands in the River Thames'
│   ├── cache_crannogs.json               # Cached Wikipedia 'Crannog' category members
│   ├── candidates_wikidata.json          # Action 1 raw output (pre-merge)
│   ├── candidates_thames.json            # Action 1b raw output (pre-merge)
│   ├── candidates_crannogs.json          # Action 3 raw output (pre-merge)
│   ├── candidates_designations.json      # Action 5 raw output (pre-merge; blocked)
│   └── islands.json                      # Final merged 6,741-island dataset (loaded by the app)
├── scripts/
│   ├── fetch_islands.py                  # Overpass → dedupe → rank → merge with curated
│   ├── classify_inland.py                # Discover lake / river islands via parent water bodies
│   ├── enrich_images.py                  # Add primary images from Wikidata P18 / pageimages
│   └── ingest_sources.py                 # Wikidata SPARQL + Thames + Crannog ingestion + dedup
├── docs/
│   ├── DISCOVERY-SOURCES.md              # Catalogue of ~85 evaluated open data sources
│   ├── ETHICS.md                         # Human-values guardrails for ingestion
│   └── NEXT-SESSION-PLAN.md              # Top-5 prioritized ingestion actions
└── README.md
```

## Data pipeline

```
                  Overpass API
                       │
                       ▼
              ~5,800 raw islands
                       │
              dedupe (name + ~1km)
                       │
                       ▼
              ~5,750 unique islands
                       │
                       │ ◄── 27 curated entries
                       │     match by name + ≤25km
                       │     and inherit OSM IDs
                       ▼
              rank by notability                          ┌── Wikidata SPARQL
              (area · log + population · log              │   (per-country: UK, IE,
               + wikipedia + image + relation > way > node) │    IoM, Jersey, Guernsey)
                       │                                  │   2,644 candidates
                       ▼                                  │
              cap by notability                           ├── Wikipedia "Islands in
                       │                                  │   the River Thames" (30)
                       ▼                                  │
              data/islands.json (offshore baseline) ◄─────┴── Wikipedia Crannog
                       │                                      categories (10)
                       │ ◄── scripts/ingest_sources.py
                       │     name+proximity dedup against
                       │     existing entries; richer wins,
                       │     curated always wins.
                       ▼
              data/islands.json (after multi-source merge)
                       │
                       │ ◄── scripts/classify_inland.py
                       │     adds Tier A / Tier B inland
                       │     classifications + discoveries
                       ▼
              data/islands.json (final, ~6,741 islands)
                       │
                       │ ◄── scripts/enrich_images.py
                       │     Wikidata P18 → Wikipedia
                       │     pageimages → Commons metadata
                       ▼
              data/islands.json (enriched)
```

### Refresh / rebuild the dataset

```bash
# 1. Fetch offshore islands and merge with the curated set (~2 min cold)
python3 scripts/fetch_islands.py            # hits Overpass
python3 scripts/fetch_islands.py --cache    # reuses data/osm_raw.json

# 2. Discover and classify inland islands (~90 s cold)
pip install shapely                          # one-off
python3 scripts/classify_inland.py           # hits Overpass for water bodies
python3 scripts/classify_inland.py --cache   # reuses data/water_raw.json

# 3. Multi-source ingestion: Wikidata + Thames + Crannogs (~6 min cold; CC0 + CC BY-SA)
python3 scripts/ingest_sources.py            # all actions + merge
python3 scripts/ingest_sources.py --only=wikidata
python3 scripts/ingest_sources.py --only=thames
python3 scripts/ingest_sources.py --only=crannogs
python3 scripts/ingest_sources.py --merge    # merge cached candidates only

# 4. Re-classify after ingestion so new entries get correct lake/river type
python3 scripts/classify_inland.py --cache

# 5. Enrich entries with a primary image + attribution (~5 min cold, instant warm)
python3 scripts/enrich_images.py             # uses cached Wikidata/Commons responses if present
python3 scripts/enrich_images.py --refresh   # bypass cache (slow; respect rate limits)
```

### Ethics & licensing

All ingestion follows the guardrails in [`docs/ETHICS.md`](docs/ETHICS.md):

- **Licensing**: Wikidata is CC0; Wikipedia is CC BY-SA 4.0; OSM is ODbL.
  Every entry carries an explicit `sources[]` block with licence and
  attribution, rendered in the detail panel.
- **Cultural names**: 2,506 islands carry multilingual labels in Gaeilge,
  Gàidhlig, Cymraeg, Gaelg, or Kernewek, surfaced under the title.
- **Heritage sensitivity**: Crannog candidates use 100 m coordinate
  precision (matching publication granularity of HES Canmore / NMS Ireland
  / DfC HED NI). Private dwellings are never identified on inhabited
  islands. No coordinates are published for any species or culturally
  sensitive entry beyond what the public source already published.

The offshore cap is `MAX_ISLANDS` in `scripts/fetch_islands.py`. It's
currently set to 60,000 — effectively unlimited, admitting all ~5,800
named islands OSM has in the UK / Ireland bbox. Lower it if you want to
focus on the most notable entries (ranking is `area · log + population ·
log + wikipedia + image + relation > way > node`). The classifier appends
inland discoveries on top of that baseline.

## Discovering inland islands (lakes & rivers)

The hard problem is **which** islands are inland and **what water body**
they sit in. We solve it by walking OSM's data model rather than guessing
from tags.

### Core insight

> Don't search for inland islands directly. Find the water bodies first,
> then take the islands inside them.

In OSM, a lake or wide river is modelled as a `type=multipolygon` relation
tagged `natural=water`. The lake's shoreline is an **outer** ring; islands
in it are **inner** rings of the same relation. Inland islands are therefore
*already paired* with their parent water body — you just walk the relation.

### Tier A — Inner-ring extraction (high precision)

`scripts/classify_inland.py` queries every UK water multipolygon tagged
lake / pond / reservoir / lagoon / oxbow OR river / canal / stream OR
(legacy) `waterway=riverbank`. For each:

1. Classify the body's `kind` (lake or river) from its tags.
2. **Skip if tidal**: any of `salt=yes`, `tidal=yes`, `water=tidal`,
   `estuary=yes` → it's really sea (Strangford Lough, Thames Estuary).
3. Walk its members; every `role=inner` way is an island of that body.
4. Cross-reference inner-way OSM IDs with our existing dataset:
   - Matched → re-type as lake / river, attach `parentWaterBody`.
   - Matched-by-name+proximity to an existing entry → merge OSM IDs in.
   - Otherwise (named, in UK/Ireland) → append as a **newly-discovered**
     inland island.

When an inner ring belongs to multiple water bodies (e.g. an island in a
lough that's also part of a river system), the **smallest containing body
wins** — that's the most specific parent.

### Tier B — Point-in-polygon containment (recall booster)

Some islands sit inside a lake polygon but **aren't members** of its
multipolygon (large named islands like Devenish on Lower Lough Erne are
modelled as their own multipolygon relation, geographically inside the
lake but not as an `inner` member of it).

For these, we:

1. Polygonise the lake / river outer rings with `shapely.ops.polygonize`
   (Lower Lough Erne's outer boundary is 119 separate way segments — naive
   ring-closing produces degenerate slivers; polygonize stitches them).
2. Build an `STRtree` for fast point-in-polygon lookups.
3. For each island still tagged `sea`, query the tree with its centroid.
4. The smallest containing body wins (specificity again).

### What it skips and why

| OSM modelling | Treatment | Why |
|---|---|---|
| `water=tidal`, `salt=yes`, `tidal=yes`, `estuary=yes` | Skipped | These are sea masquerading as inland water |
| Scottish sea lochs (Loch Linnhe, Loch Long, …) | Never reached | Not modelled as `natural=water` in OSM — they're just open coastline |
| Unnamed inner rings | Dropped | ~20,000 of them in the UK; almost entirely noise (mid-river bars, reservoir grass) |
| Geometries outside the UK / Ireland nation boxes | Dropped | Bbox bleed into France / Faroes |

### Schema additions

```jsonc
{
  "type": "sea | lake | river",
  "parentWaterBody": {
    "name": "Loch Lomond",
    "type": "lake",
    "osmType": "relation",
    "osmId": 1377850,
    "wikidata": "Q210034"
  },
  "classification": {
    "source": "tier-a | tier-b | manual",
    "confidence": "high | medium"
  }
}
```

A full per-island audit trail is written to
`data/inland_classification_report.json` so any classification can be
reviewed.

### Validation (precision spot-check)

| Island | Expected | Result |
|---|---|---|
| Inchmurrin (Loch Lomond) | lake | ✓ tier-a, parent **Loch Lomond** |
| Inchconnachan (Loch Lomond) | lake | ✓ tier-a, parent **Loch Lomond** |
| Belle Isle (Windermere) | lake | ✓ curated |
| Devenish Island (Lough Erne) | lake | ✓ tier-b, parent **Lower Lough Erne** |
| Boa Island (Lough Erne) | lake | ✓ tier-b, parent **Lower Lough Erne** |
| Eel Pie Island (Thames) | river | ✓ curated |
| Cramond Island | sea (tidal) | ✓ stayed sea |
| Lindisfarne | sea (tidal) | ✓ stayed sea |
| Foulness, Canvey | sea (estuary) | ✓ stayed sea |
| Eilean Donan | sea (sea loch) | ✓ stayed sea |
| Iona, Skye, Anglesey, Inchmickery | sea | ✓ stayed sea |

**18/18 in the canonical set; 0 false positives across 10 major Scottish
sea lochs** (last validated against the full 5,892-island dataset).

### Where this can still improve

- **River island recall** is comparatively low (~200 entries) because most
  UK rivers are modelled as **linear ways** in OSM, not polygons.
  Detecting islands in a meandering linear river requires generating a
  buffer around the way and testing intersections — a Tier B' extension.
- **Subtype enrichment** (reservoir vs lake, canal vs river) is already
  parsed by the script (`subtype_for(...)`) and stored on the island, but
  the UI currently only displays it when present.
- **Wikidata Tier C** would pull descriptions, populations and images for
  hundreds of inland-island stubs at once via SPARQL (`?island wdt:P206
  ?body`). Not yet implemented.

### How nations are tagged

Auto-imported entries get a `nation` field by point-in-bounding-box check.
The boxes (`NATION_BOXES` in the script) are intentionally simple —
correct for ~99% of islands and a good signal for the nation filter. If
you need higher accuracy, swap in proper polygons (the UK admin level 4
boundaries from OSM are ideal).

## Image enrichment

Every island that has a Wikidata Q-ID or a Wikipedia article gets a primary
photo (plus attribution + license) pulled from authoritative sources. The
schema is designed so multiple images per island compose into a gallery
naturally — today the detail view shows one hero plus a thumbnail strip;
tomorrow it can hold a full lightbox without any data changes.

**No name-based Commons search.** There are 50+ "White Island"s on Commons;
matching by name is unsafe. Only ground-truthed sources are accepted:

1. **Wikidata P18** (priority 1, ~1,300 islands have a Q-ID). The Q-ID is
   harvested from OSM's `tags.wikidata` and from Wikipedia's `pageprops`.
   The image is whatever the Wikidata editors marked as the entity's
   primary picture.
2. **MediaWiki `pageimages`** (priority 2). Only consulted when an island
   has a `wikipedia` URL but no usable P18. The Wikipedia URL itself is
   the ground truth; flag/coat-of-arms/outline-map files are filtered out
   by a deny-list regex (`flag`, `coat_of_arms`, `outline_map`, `.svg`).
3. **Curated `image` URL** (priority 3, ~20 entries from `curated.json`).
   Filenames are looked up on Commons; entries whose file 404s are
   dropped automatically so the gallery never shows a broken hero.

The pipeline:

```bash
python3 scripts/enrich_images.py            # uses on-disk caches
python3 scripts/enrich_images.py --refresh  # bypass caches (slow)
```

It batches against the Wikidata SPARQL endpoint (80 Q-IDs/query), the
MediaWiki pageprops + pageimages APIs (50 titles/query), and the Commons
imageinfo API (50 files/query). All four caches are written to
`data/cache_*.json` so reruns are instant. A `User-Agent` header
identifies the project; politeness delays of 120 ms sit between batches.

**Fact-check audit.** `data/image_enrichment_report.json` contains:

- Counts per source (wikidata / pageimage / curated / none).
- 30 random spot-check rows + 9 iconic ones, each with the Wikidata label,
  description, Commons file name, license, attribution, and source-page URL.
- A `suspect_name_mismatches` block listing entries whose Wikidata label
  or description doesn't include the island's name — most of these are
  Gaelic / Irish renderings of the same island (e.g. "Cape Clear Island" ↔
  "Cléire", "Bearasay" ↔ "Bearasaigh"), but a few are genuine OSM mistags
  (e.g. Castle Island being tagged with the Q-ID of the surrounding lake).
  Review them periodically; most are benign.

**Coverage today (5,892-island dataset):**

| Source         | Islands with primary image |
| -------------- | -------------------------- |
| Wikidata P18   | 782                        |
| Curated        | 20 (down from 49 — broken filenames dropped) |
| Pageimage      | 0 (all candidates flowed into P18 via pageprops harvesting) |
| **Total**      | **793** (~13.5%)            |

The remaining 5,099 entries are mostly small named offshore rocks and
inner-Hebridean skerries that have no Wikipedia article — i.e. they have
no authoritative source. The audit refuses to invent one.

**Schema** (each island now has an `images` array):

```jsonc
{
  "id": "iona",
  "name": "Iona",
  "wikidata": "Q610",            // top-level Q-ID, harvested for re-use
  "image": "<images[0].url>",    // back-compat with old consumers
  "images": [
    {
      "url":        "https://commons.wikimedia.org/wiki/Special:FilePath/Iona_Abbey%2C_Mull.jpg?width=640",
      "fullUrl":    ".../?width=1600",
      "source":     "wikidata",     // wikidata | pageimage | curated
      "sourceRef":  "Q610",         // the Q-ID, Wikipedia title, or filename
      "sourcePageUrl": "https://commons.wikimedia.org/wiki/File:Iona_Abbey%2C_Mull.jpg",
      "license":    "CC BY-SA 4.0",
      "attribution": "Tim Roberts",
      "caption":    "Iona Abbey, Mull, 2024",
      "primary":    true
    }
    // ...future entries here populate the thumbnail strip automatically
  ]
}
```

**Front-end behaviour:**

- Hero loads lazily (`loading="lazy"`).
- If the primary image fails to load (rare network blip or stale curated
  filename), the front-end auto-advances to the next image in `images[]`
  and re-renders the attribution line.
- Multi-image entries get a thumbnail strip under the attribution; clicking
  a thumb swaps the hero. (List cards never load thumbnails — the heavier
  asset stays detail-view-only.)
- Attribution line format: `Photo: <author> · <license> · <source ↗>`.

## Adding Ordnance Survey Maps

OS Maps is the gold standard for UK navigation, including Outdoor (1:25k)
and Leisure (1:50k) styles.

1. Sign up at <https://osdatahub.os.uk/> (free tier: 250k tile requests/month).
2. Create a project, grab a key for the **OS Maps API (ZXY)**.
3. Open `app.js`:

   ```js
   const OS_MAPS_API_KEY = "your-key-here";
   ```

4. The "OS Maps (Outdoor)" entry in the base‑map dropdown becomes selectable.
   To switch styles, change `Outdoor_3857` in the URL to one of
   `Leisure_3857`, `Light_3857`, or `Road_3857`.

OS data is © Crown copyright — keep the attribution string.

## How polygon overlays work

When you open an island's detail view:

1. The app reads `osmType` (way/relation) and `osmId` from the entry.
2. It POSTs `[out:json][timeout:25];{osmType}({osmId});out geom;` to
   Overpass (with three mirror endpoints as fallback).
3. The response is converted to GeoJSON in‑browser and added as a
   `L.geoJSON` layer styled with the accent colour.
4. The map fits the polygon's bounds.
5. The result is cached in memory so re‑opens are instant.

## Where to take this next

- **More mapping options** (already a Leaflet base layer — drop in):
  - **Ordnance Survey** — covered above.
  - **Maptiler / Stadia / Thunderforest** for nicer terrain styling.
  - **Bing Maps Aerial** with an API key for very high‑res imagery.
  - **Admiralty Vector / Raster Charts** (commercial) for nautical detail.

- **Auto‑enrich OSM entries** instead of just OSM imports. Each OSM tag
  block often has a `wikidata` Q‑ID; one SPARQL query against Wikidata can
  return populations, areas, parent archipelago, lead images, and short
  descriptions for hundreds of islands at once. That would turn the bulk of
  the 1,000 from "crowd‑sourced entry" stubs into rich pages.

- **River-island recall via linear-river buffering.** Tier A/B catches
  every river island where OSM models the river as a polygon (Thames at
  Twickenham, parts of the Severn, several Scottish lochs masquerading as
  rivers). It misses islands on rivers modelled only as linear ways. A
  Tier B' pass that buffers each `waterway=river` line by its `width=*`
  tag and tests intersection would close that gap — most usefully for the
  upper Thames, the Wye, the Trent and the Spey.

- **Vector‑tile the map**. With ~5,900 markers we use clustering and a
  virtualised sidebar; if you want every island's actual polygon (not just
  a marker) rendered at every zoom level, switch to a PMTiles‑backed vector
  tile source served from object storage.

- **Tide‑aware causeway info** for tidal islands like Lindisfarne and Burgh
  via the UK Hydrographic Office's UKHO Admiralty API — show the next
  safe crossing window inline in the detail view.

- **Accommodation deep‑links** to specific operators (Landmark Trust,
  National Trust Holidays, Hostelling Scotland, Sawday's, Cool Places,
  Booking.com) instead of the current generic Google search.

## Data fields

```jsonc
{
  "id": "isle-of-skye",                         // stable ID; OSM imports use osm-{type}-{id}
  "name": "Isle of Skye",
  "nation": "Scotland",                         // Scotland, England, Wales, Northern Ireland,
                                                // Ireland, Crown Dependency
  "type": "sea | lake | river",                 // assigned by the classifier
  "subtype": "reservoir | canal | lagoon |      // optional, set by classify_inland.py
              pond | oxbow | stream | null",
  "archipelago": "Inner Hebrides",
  "lat": 57.273,
  "lng": -6.215,
  "areaKm2": 1656,
  "population": 10008,
  "highestPointM": 992,
  "highestPointName": "Sgùrr Alasdair",
  "shortDescription": "...",
  "history": "...",
  "geography": "...",
  "transport": "...",
  "accommodation": "...",
  "wikipedia": "https://en.wikipedia.org/...",
  "wikidata": "Q107393",                        // harvested from OSM tags / Wikipedia pageprops
  "image":  "<images[0].url>",                  // back-compat mirror of the primary image URL
  "images": [                                   // populated by scripts/enrich_images.py
    {
      "url":           "https://commons.wikimedia.org/.../?width=640",
      "fullUrl":       "https://commons.wikimedia.org/.../?width=1600",
      "source":        "wikidata | pageimage | curated",
      "sourceRef":     "Q107393",               // Q-ID, Wikipedia title, or Commons filename
      "sourcePageUrl": "https://commons.wikimedia.org/wiki/File:...",
      "license":       "CC BY-SA 4.0",
      "attribution":   "Photographer name",
      "caption":       "Optional, default = Wikidata label or filename",
      "primary":       true
    }
  ],
  "tags": ["mountains", "ferry", "bridge"],
  "source": "curated | osm | osm-inland",       // osm-inland = discovered by the classifier
  "osmType": "relation",                        // way | relation | node — used for polygon fetch
  "osmId": 544726,
  "osmPlace": "island",                         // island | islet
  "parentWaterBody": {                          // set for lake / river entries
    "name": "Loch Lomond",
    "type": "lake",
    "osmType": "relation",
    "osmId": 1377850,
    "wikidata": "Q210034"
  },
  "classification": {                           // audit of how the type was assigned
    "source": "tier-a | tier-b | manual",
    "confidence": "high | medium"
  }
}
```

To enrich an OSM stub by hand, copy its entry into `data/curated.json`,
fill in the rich text fields, and re‑run `scripts/fetch_islands.py --cache`
followed by `scripts/classify_inland.py --cache`. The merge will preserve
your curated content and keep the OSM IDs intact; the classifier won't
overwrite a curated `type` of `lake` or `river`.

## Licensing notes

- Imagery in curated entries is hot‑linked from Wikimedia Commons; check
  each file's licence before redistribution. For production, mirror the
  images and keep the attribution.
- OpenStreetMap data is © OSM contributors, ODbL.
- Ordnance Survey tiles are © Crown copyright — attribution is mandatory.
- Esri imagery, OpenTopoMap, CARTO base maps each have their own
  attributions in‑map; do not strip them.
