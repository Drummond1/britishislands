# Data sources — registry & refresh cadence

Every external dataset ingested into `data/islands.json` (or its
satellite files such as `data/galleries.json`, `data/ferries.json`,
`data/ferry_terminals.json`) is catalogued here with its licence,
attribution string, refresh cadence, and the script that consumes it.

This file is reviewed when:

- A new source category is added (workstream cf. `DISCOVERY-SOURCES.md`).
- A licence change at a source is detected during a refresh.
- A community authority issues new naming or sensitivity guidance.

Companion documents:

- [`ETHICS.md`](ETHICS.md) — the binding charter for licensing,
  attribution, privacy, and sensitive species.
- [`IMAGE-SOURCES.md`](IMAGE-SOURCES.md) — the per-photo provenance
  registry (Commons / Geograph / Flickr / OGL bodies).
- [`MEASUREMENTS.md`](MEASUREMENTS.md) — area + elevation methodology.
- [`DATA-SCHEMA.md`](DATA-SCHEMA.md) — field-by-field record spec.

---

## A. Core geographic sources

| # | Source | Licence | Refresh | Used by | Attribution string |
|---|---|---|---|---|---|
| 1 | **OpenStreetMap** (Overpass API) | ODbL 1.0 | Weekly cache; manual rebuild on schema change | `fetch_islands.py`, `compute_island_areas.py`, `compute_island_highpoints.py`, `enrich_images_v5.py`, `ingest_lighthouses.py`, `ingest_wildlife_colonies.py`, `fetch_ferries_osm.py` | `© OpenStreetMap contributors (ODbL 1.0)` |
| 2 | **Wikidata** (SPARQL + REST) | CC0 1.0 | Per-script cache; weekly auto-refresh | `ingest_sources.py`, `compute_island_*`, `enrich_names.py`, `enrich_images_*`, `ingest_hills_dobih.py`, `ingest_lighthouses.py` | `Wikidata contributors (CC0)` |
| 2a | **Marine Regions** gazetteer (REST `getGazetteerRecordsByLatLong`) | CC-BY 4.0 | First full `catalog_scanner` run writes `data/cache_discovery_marine_regions.json`; set `DISCOVERY_REFRESH_MARINE=1` to invalidate | `scripts/discovery/marine_regions_gazetteer.py` (via `catalog_scanner`) | `Marine Regions (CC-BY) — https://www.marineregions.org/` |
| 3 | **Wikipedia** (MediaWiki API) | CC-BY-SA 4.0 (text), file inherits Commons licence | Per-script cache | `enrich_descriptions_wikipedia.py`, `enrich_images_*` | `From Wikipedia article "<title>" (CC-BY-SA 4.0)` |
| 4 | **Wikimedia Commons** (MediaWiki API) | per-file (CC-BY-SA, CC-BY, CC0, PD, OGL) | Per-script cache | `enrich_images_*` | `Photo by <Author>, via Wikimedia Commons (<License>)` |
| 5 | **Ordnance Survey OpenData** (via OSM `ele` tags) | OS OpenData / OGL v3.0 (carried through OSM under ODbL) | On OSM refresh | `compute_island_highpoints.py` | `Implicit via OSM credit; OS-derived heights from Ordnance Survey` |
| 6 | **Logainm.ie** | CC-BY 4.0 | Per-island cache (rare refresh) | `enrich_names.py` | `© Government of Ireland — Logainm.ie contributors (CC-BY 4.0)` |

---

## B. New enrichment sources (2026-05-13)

### B.1 — Hills (Database of British and Irish Hills)

| | |
|---|---|
| **Source** | Database of British and Irish Hills (DoBIH; Jackson, Dawson et al.) |
| **URL** | <https://www.hills-database.co.uk/> |
| **Licence** | CC-BY 4.0 |
| **Refresh cadence** | DoBIH is released ~annually; we refresh the local CSV on user demand. Wikidata SPARQL fallback is live. |
| **Consumed by** | `scripts/ingest_hills_dobih.py` |
| **Output field-group** | `hillsOn[]`, `hillsOnSource`, `hillsOnConfidence`, `hillsOnAttribution`, `hillsOnFetchedAt` |
| **Attribution string** | `Database of British and Irish Hills (Jackson, Dawson, et al.), CC-BY 4.0 — https://www.hills-database.co.uk/` |
| **Acquisition notes** | The official CSV download requires a free registration (email address) at hills-database.co.uk. Drop the downloaded CSV at `data/dobih_v17_3.csv` (or similar) and pass `--dobih-csv` to the ingestion script. If the CSV is absent, the script falls back to Wikidata SPARQL (Q1419786 Munro / Q5172995 Corbett / Q5594127 Graham / Q6760981 Marilyn / Q63432379 HuMP / etc.) which gives DoBIH-equivalent classifications via P5283. |
| **Cache files** | `data/cache_dobih.json` (staged enrichment), `data/cache_wd_hills.json` (raw SPARQL responses) |

### B.2 — Lighthouses & beacons

| | |
|---|---|
| **Source (primary)** | OpenStreetMap (`man_made=lighthouse` / `man_made=beacon`) |
| **Source (cross-check)** | Northern Lighthouse Board, Trinity House, Commissioners of Irish Lights — cited as the underlying statutory authorities; we do not scrape their websites. |
| **URLs** | <https://www.nlb.org.uk/>, <https://www.trinityhouse.co.uk/>, <https://www.cil.ie/> |
| **Licence** | OSM = ODbL 1.0. NLB/Trinity/CIL pages are not republished — only *cited*. |
| **Refresh cadence** | OSM polled every overnight chain; light-character / built-year are stable. |
| **Consumed by** | `scripts/ingest_lighthouses.py` |
| **Output field-group** | `lighthouses[]`, `lighthousesSource`, `lighthousesConfidence`, `lighthousesAttribution`, `lighthousesFetchedAt` |
| **Attribution string** | `© OpenStreetMap contributors (ODbL 1.0); cross-checked against Northern Lighthouse Board, Trinity House, and Commissioners of Irish Lights public station lists.` |
| **`notForNavigation`** | Mandatory `true` on every record (ETHICS §10). |
| **Cache files** | `data/cache_lighthouses.json` (staged), `data/cache_osm_lighthouses.json` (Overpass), `data/cache_wd_lighthouses.json` (Wikidata) |

### B.3 — RSPB reserves & wildlife colonies

| | |
|---|---|
| **Source (reserves)** | OpenStreetMap (`leisure=nature_reserve` + `operator~RSPB`) |
| **Source (colonies)** | JNCC SPA citations (OGL 3.0), NPWS SPA citations (PSI Re-use), RSPB reserve pages, Wikipedia text mentions, plus curated overrides at `data/wildlife_overrides.json`. |
| **Licence** | OSM = ODbL 1.0; JNCC = OGL 3.0; NPWS = PSI Re-use; RSPB pages — descriptions cited, not redistributed. |
| **Refresh cadence** | OSM polled overnight; curated overrides updated as users contribute new SPA citations. |
| **Consumed by** | `scripts/ingest_wildlife_colonies.py` |
| **Output field-groups** | `rspbReserves[]` + quad, `wildlifeColonies[]` + quad |
| **Attribution string** | `© OpenStreetMap contributors (ODbL 1.0); reserve listing © RSPB.` (reserves) — `Joint Nature Conservation Committee SPA citations (OGL 3.0); RSPB reserve descriptions (© RSPB); presence cross-checked against Wikipedia articles (CC-BY-SA 4.0).` (colonies) |
| **Ethics — non-negotiable** | Per ETHICS §5 we ingest **island-level presence only**: no precise colony coordinates, no per-nest data, no counts that could indicate productive sub-sites, no "best time to visit" narrative. The Seabird Monitoring Programme per-site counts are off-limits. Schedule 1 species (Leach's storm petrel, Manx shearwater, peregrine, white-tailed eagle, hen harrier, …) are flagged `scheduleListed: true` so the UI tones down disturbance signals. |
| **Cache files** | `data/cache_wildlife.json` (staged), `data/cache_osm_reserves.json` (Overpass), `data/wildlife_overrides.json` (curated overrides — extend by hand) |

### B.4 — Geology (BGS DigMapGB-625)

| | |
|---|---|
| **Source** | British Geological Survey, **DigMapGB-625** (1:625,000 bedrock + superficial). |
| **URL** | <https://ogc.bgs.ac.uk/cgi-bin/BGS_Bedrock_and_Superficial_Geology/wms> |
| **Licence** | **BGS Open Data Licence (OGL v3.0)** |
| **Refresh cadence** | BGS publishes DigMapGB-625 occasionally (~every 2–3 years); we re-cache annually. |
| **Consumed by** | `scripts/ingest_geology_bgs.py` |
| **Output field-group** | `geology` (single nested object with `bedrock`, `superficial`, `source`, `confidence`, `attribution`, `fetchedAt`) |
| **Attribution string** | `Contains British Geological Survey materials © UKRI 2026, licensed under the BGS Open Data Licence (OGL v3.0). Source: BGS DigMapGB-625 Bedrock & Superficial WMS.` |
| **Coverage** | Great Britain only. Northern Ireland (GSNI) and Republic of Ireland (GSI) are equivalent open datasets but require separate WMS clients — queued as a follow-up. Channel Islands and Isle of Man are also outside BGS scope. |
| **Method** | WMS `GetFeatureInfo` per island centroid against layers `GBR_BGS_625k_BLS` (bedrock lithostratigraphy) and `GBR_BGS_625k_SLS` (superficial lithostratigraphy). Cached by 4-dp rounded coords (~11 m), which dedups archipelago-mate queries ~5–10×. |
| **Cache files** | `data/cache_bgs.json` (staged + WMS responses combined; see script) |

### B.5 — Census 2022

| | |
|---|---|
| **Sources** | NRS Scotland (Census 2022), ONS (England + Wales Census 2021), NISRA (NI Census 2021), CSO Ireland (Census 2022), Isle of Man Government (Census 2021), States of Jersey & Guernsey (Census 2021/22). |
| **URLs** | <https://www.nrscotland.gov.uk/>, <https://www.ons.gov.uk/>, <https://www.nisra.gov.uk/>, <https://www.cso.ie/>, <https://www.gov.im/categories/about-the-government/iomgis/> |
| **Licence** | OGL v3.0 (UK bodies); OGL IoM; PSI Re-use (Ireland); States bailiwicks — mixed open. |
| **Refresh cadence** | UK + IE next census ≥ 2031; interim updates very rare at island level. |
| **Consumed by** | `scripts/ingest_census_2022.py` |
| **Output field-group** | `population` (updated), `populationYear`, `populationSource`, `populationConfidence`, `populationAttribution`, `populationFetchedAt`, `populationDetails` |
| **Attribution strings** | Per nation; see `ATTRIBUTIONS` table inside `ingest_census_2022.py`. |
| **Input mechanism** | Staged CSVs at `data/census2022_<nation>.csv` (one per nation). A sample template is at `data/census2022_nrs_SAMPLE.csv`. |
| **Coverage gaps** | NRS publishes 61 inhabited Scottish islands. NISRA publishes Rathlin Island directly; other NI offshore islands are within SOA aggregates. CSO Ireland's 2022 "Offshore Islands" report covers ~31 islands. ONS Census 2021 covers IoW / Hayling / Canvey / Lindisfarne / Foulness / Sheppey directly; most smaller English islands roll up into OAs. **The script honestly leaves `populationDetails` unset when the source doesn't publish at island level** (ETHICS §1 — no fabrication). |

---

## C. Refresh playbook

For each enrichment, the standard workflow is:

```bash
# Dry-run (no network, no mutation):
python3 scripts/ingest_<source>.py --dry-run

# Live network ingest into staged cache:
python3 scripts/ingest_<source>.py --fetch --commit

# When all five are staged and the overnight chain has finished:
bash scripts/apply_enrichments.sh   # interactive confirmation
# or, for unattended automation:
bash scripts/apply_enrichments.sh --yes
```

The apply step writes a single timestamped backup
`data/islands.json.before-enrichments-<ts>` before any mutation, and
re-reads the result to verify the JSON is still parseable and that
the curated regression spine (Skye, Devenish, Achill, Isle of Wight,
Eel Pie) hasn't drifted.

### B.6 — Property listings (for sale — outbound links)

| | |
|---|---|
| **Source (MVP)** | Maintainer-curated [`data/curated_property_listings.json`](../data/curated_property_listings.json) |
| **Source (optional)** | [Homedata UK](https://homedata.co.uk/docs) live-listings API (`HOMEDATA_API_KEY`) |
| **Licence** | Link-out only; no HTML scrape. Homedata: verify [Terms](https://homedata.co.uk/terms) before static redistribution. |
| **Refresh** | Weekly manual or scheduled `ingest_property_listings.py` + `apply_enrichments.py --only property` |
| **Script** | `scripts/discover_property_apis.py`, `scripts/ingest_property_listings.py`, `scripts/import_curated_property_listings.py` |
| **Attribution string** | `Outbound links to third-party estate agents and brokers; not scraped from Rightmove or Zoopla. Verify status on the source site.` |
| **Rejected** | Rightmove, Zoopla, OnTheMarket scrape — see `data/discovery/property_sources.json` |

See [`PROPERTY-LISTINGS.md`](PROPERTY-LISTINGS.md).

---

## D. License compatibility matrix

| Outgoing field-group | Upstream licences | Outgoing project licence |
|----------------------|--------------------|---------------------------|
| `hillsOn[]`                  | CC-BY 4.0 (DoBIH) + CC0 (Wikidata) | CC-BY 4.0 (attribution carried) |
| `lighthouses[]`              | ODbL 1.0 (OSM) + CC0 (Wikidata)    | ODbL 1.0 share-alike |
| `rspbReserves[]`             | ODbL 1.0 (OSM)                     | ODbL 1.0 share-alike |
| `wildlifeColonies[]`         | OGL 3.0 (JNCC) + PSI (NPWS) + CC-BY-SA 4.0 (Wikipedia) | OGL 3.0 + CC-BY-SA 4.0 (combined; project ships under CC-BY-SA 4.0 by default) |
| `geology`                    | OGL 3.0 (BGS)                      | OGL 3.0 (attribution carried) |
| `population` family          | OGL 3.0 + OGL IoM + PSI Re-use      | OGL 3.0 (attribution carried) |
| `propertyListings[]`         | Third-party site Terms (link-out)   | No redistribution of listing media; URLs + metadata only |

When in doubt, the **most restrictive incoming licence** propagates
through the project's redistribution chain. Per ETHICS §1, every
ingested record carries its source `attribution` string so downstream
republishers can honour the obligation.
