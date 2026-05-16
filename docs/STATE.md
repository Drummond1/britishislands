# STATE — live snapshot

> Update this file whenever counts, schema, or running processes change.
> Stamp the date at the top of each section so we can spot drift.
## Last updated

**2026-05-16 (contribute config + Scotland explore + UX deploy)** — **Contribute:**
GitHub Pages workflow `.github/workflows/pages.yml` injects `CROWD_FORM_EMAIL` secret
into `data/crowd_suggest_config.json`; `scripts/prepare_crowd_config.py`;
`crowd-config.js` + optional `config.local.js`; mailto fallback in modal.
**Scotland explore:** five new topics in `discovery_topics.json` (classics, Inner/
Outer Hebrides, Orkney & Shetland, ferry hops) via `build_discovery_topics.py`.
**UX:** Scotland quick-filter chips, filter tiers, list thumbnails, mobile map peek
(commit `1ae828a` + follow-ups). **P0b in flight:** `ingest_hills_dobih.py` and
`ingest_geology_bgs.py` running locally — apply with
`python3 scripts/apply_enrichments.py --apply --yes --only hills geology` when caches land.

**2026-05-16 (deploy: explore topics + P0b partial apply)** — **Explore** chips:
`data/discovery_topics.json` (notable, island-hopping, thames-eyots, high-summits);
`?explore=<id>` deep links; `scripts/build_discovery_topics.py`. **P0b applied**
(lighthouses **297**, wildlife **38**, census **10** islands) — detail UI for
hills/lighthouses/wildlife/bedrock/census breakdown in `app.js`. **Notable strip**
`featured_islands.json` (120). `islands_index.json` rebuilt (~10.2 MB). Hills/geology
caches still pending. OS key: `config.local.example.js` (copy → `config.local.js`).

**2026-05-16 (featured strip + image priority queue)** — Sidebar **Notable islands**
(`data/featured_islands.json`, 120 rows). Priority queue for v5:
`data/image_priority_queue.json` (3,444 without lead image). Regenerate via
`scripts/build_featured_islands.py` / `build_image_priority_queue.py`; run
`enrich_images_v5.py --queue-file data/image_priority_queue.json` for backfill.

**2026-05-16 (discovery filters + trip planner removed)** — Topbar discovery
filters: **Has photo**, **Ferry** (enabled after `loadFerries()`), **Summit**,
area band (≥1 / ≥10 km²), subtype, curated / hide unconfirmed. Photo filter
sorts with-photo islands first. Ferry trip planner overlay + mobile **Trip** tab
removed; list **⛴** icon and detail **How to get there** unchanged. Chat
synonyms extended (ferry, photo, large, summit, curated).

**2026-05-16 (saved islands email gate)** — Hearts + **Saved** list require a one-time email
(`iobFavoritesEmail` in localStorage); island ids stay in `iobFavoriteIslandIds` on-device only.

**2026-05-16 (native crowd submit)** — In-app **Submit suggestion** for crowd pins
(FormSubmit / Formspree / Web3Forms / webhook via `data/crowd_suggest_config.json` or
`window.IOB_SUGGEST_CONFIG`). GitHub issue remains optional fallback. See
`docs/CROWD-PINS.md`.

**2026-05-16 (Wikidata→OSM backfill)** — `compute_island_areas.py --fetch-osm` (39 new
Wikidata→OSM cache lookups). **`scripts/backfill_osm_from_wikidata.py --apply`**: **83**
rows gained `osmType`/`osmId` (**6,193** / 7,041 now have OSM ids; **848** still without).
Report `data/osm_wikidata_backfill_report.json`. Regenerated `islands_index.json`.
Discovery dry-run: **1** merge candidate; survey ledger **0** strict outstanding.
Backup `data/islands.json.before-osm-backfill-*`.

**2026-05-16 (map first paint + data hygiene)** — **`islands.json` → 7,041** rows
(removed **2** bogus csv-geocoded non-islands: Q26272407 Great Arthur House,
Q66227635 Thorney Island school). **`data/islands_index.json`** slim payload
(~4.5 MB) + two-phase fetch/merge in `app.js` (`loadIslands`). Details panel
**subtype chip** (green pill). **`scripts/build_islands_index.py`** — run after
any `islands.json` edit; see `docs/PIPELINE.md` §5b. **`scripts/recompute_nation_admin1.py`**
(dry-run / experimental): Natural Earth admin-1 **must not** be bulk-applied
— mis-tags NI/ROI and GB border; cache `data/cache_ne10m_admin1_uk_ie.geojson`.

**2026-05-15 (crowd pins v1)** — **Community suggestion layer:** `data/crowd_pins.json`
(maintainer-curated) + map overlay (gold markers), **Suggest island** modal →
pre-filled GitHub issue, **Crowd pins** toggle. Implementation: `crowd-pins.js`,
`app.js`, styles for modal/popup/legend. Workflow: `docs/CROWD-PINS.md`.

**2026-05-15 (SEO + GEO)** — Runtime head tags in `seo-meta.js` (canonical, OG,
Twitter, JSON-LD `Island`); `scripts/generate_seo_artifacts.py` for `llms.txt` +
optional `sitemap.xml` / `robots.txt` / thin `--landing-dir` stubs. See
`docs/SEO-GEO.md`.

**2026-05-15 (terrestrial rock prune)** — Removed **266** non-curated atlas rows:
`osmPlace: rock` + `type: sea` points on **dry land** (well inland of the
simplified UK+IE outline — see `TERRESTRIAL_ROCK_MIN_INLAND_DEG` in
`scripts/discovery/common.py`). Coastal / intertidal stacks (e.g. offshore
sea stacks) **kept**. Script: `scripts/prune_terrestrial_rocks.py --apply`;
audit `data/terrestrial_rocks_prune_report.json`; backup
`data/islands.json.before-terrestrial-rock-prune-20260515T231858Z.bak`.
`map_scanner` now skips the same pattern (`skippedTerrestrialRocks` in
`data/discovery/candidates_scan.json`). **`islands.json` → 7,043** rows.
Discovery **`verification.json` / survey strict “outstanding”** are now **stale**
for former rock OSM ids until you re-run the verifier / ledger pass you trust.

**2026-05-15 (survey ledger runner)** — **`scripts/survey_landmass_ledger.py`**
reconciles `data/islands.json` + `data/discovery/verification.json` (strict
`find_existing_match`, loose=False) into `data/survey/landmass_ledger.json` and
`survey_summary.json`. Latest run after rock prune: atlas **7,043** rows; note
verification bundle still lists many **off-atlas** rock OSM rows that were
**intentionally pruned** — re-run discovery merge or regenerate verification before
trusting **outstanding** counts.

**2026-05-15 (survey prompt)** — **`docs/PROMPT-COMPREHENSIVE-LANDMASS-SURVEY.md`**
— multi-agent copy/paste briefing for full remit landmass + naming sweep, survey
ledger + closure report template; 3 m × 3 m stated as **policy minimum** with
OSM/open-data reality check (not literal wall-to-wall 3 m enumeration).

**2026-05-15 (corrections v1)** — **Suggest a correction** on every island detail
panel: pre-filled GitHub issue (`Drummond1/britishislands`) with island id,
coordinates, OSM/Wikidata links, and required evidence section. Template at
`.github/ISSUE_TEMPLATE/island-data-correction.md`. No on-site accounts;
maintainer review only. Override repo via `window.IOB_CORRECTION_REPO`.

**2026-05-15 (provisional discovery)** — **Unconfirmed classification + site merge.**
`site_update --include-uncertain --apply`: **549** discovery rows merged into
existing atlas records (strict OSM / Wikidata / name match; no global 0.5 km
glue for review-flagged rows). **1** new row: **Wolf Rock Lighthouse** with
`classification.confidence: "unconfirmed"` + `reviewHint` (see
`DATA-SCHEMA.md`). `islands.json` **7,309** (+1). Backup
`data/islands.json.before-discovery-20260515T051857Z`.

**2026-05-15 (trip planner)** — **Ferry trip planner race fix.** `loadFerries()`
could resolve before `islands.json` finished, so `buildFerryIslandRefIndex()`
ran on an empty `byId` and cached an empty ferry graph; Plan route then always
failed until hard refresh. Ferries now wait on `_islandsIndexReady`; islands
load settles that promise; stale empty graphs are invalidated on island load.
Itinerary banner `z-index` raised above the top bar; status line shows a
text summary of the route.

**2026-05-15 05:00 UTC+1** — **Marine Regions discovery cache + site_update fix.**
First full `getGazetteerRecordsByLatLong` grid cached at
`data/cache_discovery_marine_regions.json` (54 cells). Under strict
`placeType=Island` + project bbox, the gazetteer returned **no** usable island
points (only macro / off-remit centroids); the hook remains for transparency
and future filter tuning. **`site_update --apply`** now writes
`islands.json` when there are **merge-only** updates (wikidata/osm/sources on
existing rows), not only new inserts — fixed regression where 5 merges would
stay in-memory. Applied merge pass: **5** enriched existing islands (count
still **7,308**); backup `data/islands.json.before-discovery-20260515T044747Z`.

**2026-05-14 22:45 UTC+1** — **Multi-source catalog discovery applied.**
`scripts/discovery/catalog_scanner.py` harvests Wikidata, Wikipedia island
lists, Thames eyots, crannogs, DoBIH crosswalk, and optional OS Open Names
(`data/raw/os_opennames.csv`). Haswell-Smith, Vision of Britain, and OS
MasterMap stay reference-only. `islands.json` **7,308** (+10 from catalog
merge; backup `data/islands.json.before-discovery-20260514T214253Z`).

**2026-05-14 06:45 UTC+1** — **Autonomous run in progress.** Full
discovery pipeline (`discover_islands_pipeline.py --include-uncertain
--apply`) then overnight enrichment + LLM (≤ $30). Check
`logs/discovery-*.log` and `logs/overnight-*-summary.log`.

**2026-05-13 22:05 UTC+1** — **Five-agent discovery pipeline staged
(`islands.json` untouched).** Orchestrator at
`scripts/discover_islands_pipeline.py` with modules under
`scripts/discovery/` (map scanner, source verifier, photo finder,
enricher, site update). Workflow doc at
[`DISCOVERY-PIPELINE.md`](DISCOVERY-PIPELINE.md). Review-first artifacts
under `data/discovery/` (`candidates_scan.json`, `verification.json`,
`photos.json`, `enrichment.json`, `review_report.json`) plus caches
`data/cache_discovery_*.json`. Dry-run smoke test on 5 candidates:
5 verified, 0 merge-ready without manual review (no licence-safe photos in
the sample). Apply merge only via `--stage=site_update --apply` after
checking **Currently running**.

**2026-05-12 21:45 UTC+1** — **Five-source enrichment scaffold staged
(islands.json untouched).** New ingestion scripts for DoBIH hills,
lighthouses + beacons, RSPB reserves + wildlife colonies, BGS
geology, and Census 2022 population.  Per-source caches at
`data/cache_dobih.json`, `data/cache_lighthouses.json`,
`data/cache_wildlife.json`, `data/cache_bgs.json`,
`data/cache_census2022.json`.  All scripts compile clean, follow the
`<thing>Source` / `<thing>Confidence` / `<thing>Attribution` /
`<thing>FetchedAt` quad, and write atomically with idempotent /
checkpointed / audited behaviour.  Schema proposal at
[`SCHEMA-ENRICHMENTS-2026-05-13.md`](SCHEMA-ENRICHMENTS-2026-05-13.md);
source registry at [`DATA-SOURCES.md`](DATA-SOURCES.md).  The merge
into `islands.json` is gated behind `scripts/apply_enrichments.sh`,
which waits for `scripts/overnight_runner.sh` (PID 71005) to finish.

Dry-run coverage estimates:
* **DoBIH hills** — Wikidata SPARQL fallback covers ~854 hills with
  DoBIH IDs (full DoBIH CSV path also supported).  Expected coverage
  after PIP join: ~250–400 islands have ≥1 classified hill.
* **Lighthouses** — first --fetch run will pull every
  `man_made=lighthouse|beacon` in the UK + Ireland bbox (~600–900
  elements expected from past Overpass runs).
* **RSPB reserves + wildlife** — 25 curated stacks + Wikipedia
  text-scan; first dry-run staged 30 islands (22 curated + 8
  text-scan).
* **BGS geology** — every GB island will resolve a bedrock unit;
  ~2,200 GB islands × ~2 WMS calls each ≈ 4,400 calls at 0.5 s
  polite throttle ≈ 40 minutes.  Dry-run probed 8 large islands
  (Skye, Mull, Anglesey, IoW, Arran, Orkney, Shetland, Lewis) with
  factually-correct bedrock matches.
* **Census 2022** — first 10 islands matched against NRS 2022 sample
  CSV (Skye 10,008; Lewis & Harris 21,031; Mull 3,049; Islay 3,498;
  Arran 4,679; Tiree 653; Iona 177; Eigg 108; Rum 40; Canna 11).
  61 inhabited Scottish islands total once the full NRS table is
  staged.

**2026-05-12 15:45 UTC+1** — **Highest-point elevations published
(293 islands, 4.3 %; up from 27).** New
`scripts/compute_island_highpoints.py` bulk-fetches every
`natural=peak` node with an `ele=*` tag from the UK / Ireland bbox
(18,525 peaks in 42 Overpass tiles), spatial-indexes them, then for
each island polygon finds peaks inside and takes the highest. OSM
`ele` is typically Ordnance-Survey-derived and accurate to ±1 m — well
inside 2 % for any summit ≥ 50 m.

Cross-validated against Wikidata P2044 where both signals exist:

| Conf       | Count | When                                                       |
| ---------- | ----- | ---------------------------------------------------------- |
| `high`     |  239  | OSM-surveyed peak (cross-validated by WD when available)   |
| `estimate` |   54  | Wikidata P2044 only, OR OSM/WD disagree by > 5 m or > 5 %  |
| `n/a`      | 6,483 | No peak inside polygon and no Wikidata elevation           |

Top 30 by computed elevation reads as a who's-who of British / Irish
summits: Ben Nevis (1,345 m) · Carrauntoohil (1,039) · Sgùrr Alasdair
on Skye (992) · Ben More on Mull (966) · Goat Fell on Arran (874) ·
Askival on Rum (812) · An Cliseam on Lewis-and-Harris (799) · Beinn an
Òir on Jura (785) · Croaghaun on Achill (688) · Snaefell on the Isle
of Man (621) — all matching canonical references to the metre.

New fields on each island:
`highestPointM: number | null`,
`highestPointName: string | null`,
`highestPointSource: "osm-peak" | "wikidata-p2044" | "manual" | null`,
`highestPointConfidence: "high" | "estimate" | "n/a"`.

Detail-panel UI updated (`app.js` → `formatHighPointRow`):
high-confidence values render with their source ("· OSM surveyed
peak"); estimate values render with "· estimate · …" so users
immediately see that the figure is unverified.

Backup at `data/islands.json.before-highpoints-20260512T154541Z`.
Full evidence in `data/highpoint_audit.json`.

The 95.7 % `n/a` rate reflects reality: most islands in the dataset
are small islets without OSM-tagged peaks. Future work could sample
SRTM 1-arc-sec or OS Terrain 50 inside each polygon to derive an
elevation; that would be a Phase 2 enhancement.

---

**2026-05-12 15:10 UTC+1** — **Polygon-based island areas published
(85.8 % coverage; 82.4 % at high confidence; the rest N/A).** New
`scripts/compute_island_areas.py` measures each island by geodesic
integration on the WGS84 ellipsoid (`pyproj.Geod.polygon_area_perimeter`),
which is sub-0.01 %-accurate as a *method* — meaning the published
number's uncertainty is entirely the accuracy of the underlying
polygon, not the maths.

Polygons are resolved in priority order:

1. **Step B** — the island's own `osm-way-…` or `osm-relation-…` ID
   (or the `…-w<digits>` suffix embedded in hand-curated IDs) is the
   canonical geometry; fetched in batches from Overpass and cached in
   `data/cache_osm_geometries.json`.
2. **Step C** — for `wd-Q…` IDs we look up the OSM element tagged
   `wikidata=Q…` over Overpass; covers ~60 additional islands where
   the dataset entry doesn't store a way ID directly.
3. **Step A** — only for *hand-curated* IDs (no `osm-`/`wd-`/`csv-`
   prefix and no `-w…` suffix). For these we find the smallest non-
   mainland OSM coastline polygon containing the centroid. The
   allowlist behaviour was a deliberate fix for *islet inheritance*:
   a `wd-Q*` skerry whose centroid happens to fall inside Mull's
   coastline would otherwise be assigned 884 km².

Cross-validation against Wikidata P2046 is treated as a *sanity check*,
not a gate, because the field has many unit-tagging errors (hectares
marked as km², m² marked as km², etc.) — when the OSM/WD ratio matches
a known unit confusion (≈100×, ≈1000×, ≈300×) we keep our number with
a "WD unit mis-tagged" note. Disagreements > 25 % with no unit
explanation downgrade to medium confidence.

Outcome on `islands.json` (6,776 entries):

* **5,581 (82.4 %) — `areaConfidence: "high"`** — polygon-backed
  geodesic, where applicable cross-checked by Wikidata.
* **236 (3.5 %) — `areaConfidence: "medium"`** — small islets with
  minimal polygons, or significant WD disagreement.
* **959 (14.2 %) — `areaConfidence: "n/a"`** — point-only OSM nodes,
  `wd-Q*` islets with no resolvable polygon, csv-geocoded entries
  without an OSM linkage. We honour the spec: "accurate to within
  2 % or N/A".

Spot-checks (computed vs canonical reference, Δ):
GB 218,686 (Δ −4.5 % vs commonly-cited 228,938 which *includes
inhabited adjacent isles*) · Ireland 83,553 (−1.0 %) · L&H 2,149
(−1.4 %) · Skye 1,636 (−1.2 %) · Mull 884.7 (+1.1 %) · Anglesey 679.8
(−4.9 % vs 715 figure that includes Holy Island) · IoM 570.5 (−0.3 %) ·
Arran 429.6 (−0.6 %) · IoW 381.6 (+0.4 %) · Islay 617.6 (−0.2 %) ·
Achill 148.3 (+1.6 %).

New fields on each island:
`areaKm2: number | null`,
`areaSource: "osm-way" | "osm-relation" | "osm-coastline-polygon" | "osm-via-wikidata-…"  | null`,
`areaConfidence: "high" | "medium" | "n/a"`.

Detail-panel UI updated (`app.js` → `formatAreaRow`): high-confidence
areas now render with their source ("· high confidence · OSM way"),
N/A entries show a hoverable tooltip explaining the spec.

Full per-island evidence in `data/area_audit.json` (write-only,
ignored by `.gitignore` if needed); islands backup at
`data/islands.json.before-areas-20260512T151008Z`.

---

**2026-05-12 13:55 UTC+1** — **`unknown` queue drained (210 → 1).** Two
follow-up passes:

1. **Tier 4 added to `scripts/reclassify_islands.py`** — nearest non-tidal
   OSM water polygon ≤200 m = medium-confidence proposal, 200-500 m = low.
   Gated on the mainland test so it can't false-positive a marine islet
   against a coastal freshwater stream. The classifier re-ran in
   ~10 min and proposed 94 transitions (`unknown→river` 38, `unknown→lake`
   56). Applied 76 medium-confidence ones via the existing apply script;
   the 18 low-confidence ones were rolled into the manual sweep instead.
2. **Hand-curated `data/manual_overrides.json`** — 134 entries covering
   the residual unknowns plus the 18 mixed low-confidence Tier-4 ones
   plus a few Tier-4 errors that needed flipping (Cobholm river not
   lake; Eilean na h-Aibhne river not lake; Foaty Island sea not lake;
   Holy-Island-Surrey river not lake; Thorney-Island-Westminster river
   not lake; Great Arthur House kept as unknown). New script
   `scripts/apply_manual_overrides.py` reads the JSON, writes a
   timestamped backup, and supports the same atomic-write + read-back
   safety the auto-apply uses. Persists `classificationNote` so the
   reasoning is preserved in `islands.json` itself.

Final state: `sea: 5,049 · lake: 1,329 · river: 397 · unknown: 1`. The
single remaining unknown is "Great Arthur House Including Boiler House"
(an architectural feature inside the Barbican Estate; needs upstream
CSV cleanup, not a classification fix). Classification-source
distribution: 1,080 tier-a · 249 tier-b · 134 manual-override · 133
osm-water-pip · 80 wikidata-p206 · 76 osm-water-near · 22 thames-list ·
4 wp-category · 3 crannog-subtype-override · 4,995 default-sea-
confirmed.

**2026-05-12 13:15 UTC+1** — **Island categorisation Phase 1.5 applied.**
New Tier 2 added to the reclassification pipeline: every centroid is now
tested against the **GB + Ireland mainland polygons** (built offline by
`scripts/build_land_polygons.py`, pickled to `data/mainland_polygons.pickle`).
An island that sits **inside** the mainland polygon but has **no
positive water-body match** is now flagged `type: unknown` with
classification `{source: "land-in-no-water", confidence: "low"}` rather
than left as the default `sea`. 210 such islands were re-typed in this
pass (`sea → unknown`). Catches: Magurk's Island (Lough MacNean), Bank
Island (Yorkshire Derwent floodplain RSPB reserve), Bingley's Island
(Pegwell Bay marshland), various small Irish lough islets, several
crannogs, plus a handful of tidal/causeway islets (Inchydoney, Corkbeg,
Calbha Mor) that genuinely sit on the line. The UI now ships a fourth
type pill `unknown` (lilac, hatch-textured) labelled **"Unverified
(needs review)"** in legend, type filter, and the details panel.
`islands.json` backup at `data/islands.json.before-reclass-20260512T131152Z`.
Mainland test pickle was built from the cached OSM coastline (40 MB
on disk; 23,354 land polygons, 2 mainland components: GB at 218k km²
and Ireland at 83k km²; clean 39× area gap to next-largest). Type
breakdown now: `sea: 4,991 | lake: 1,257 | river: 318 | unknown: 210`.

**2026-05-12 12:46 UTC+1** — **Island categorisation Phase 1 applied.** 213
islands re-typed from the default `sea` to their correct inland body:
**157 → lake**, **56 → river**. New pipeline at
`scripts/reclassify_islands.py` (Wikidata P206 → P31 + P279 climb, plus
widened OSM water polygon containment). Headline fixes: Kate's Island
(small Yorkshire pond) and Bodinbo Island (River Clyde) both now show
the correct pill. Sea-loch trap solved by cross-referencing each OSM
water body's `wikidata=Q…` tag against the Wikidata cache (Loch Ewe
caught and excluded). Proposal kept at
`data/reclassification_proposal.json` for audit; `islands.json` backup
at `data/islands.json.before-reclass-20260512T124618Z`.

**2026-05-11 20:00 UTC+1** — **Ferry-routes feature complete.** Three new
JSONs: `data/ferries.json` (**347 routes**: 156 OSM + 141 GTFS + 50
manual), `data/operators.json` (**54 operators**), `data/ferry_terminals.json`
(**903 terminals**, 366 matched to islands). Plus `data/ferries_manual.json`
(50 hand-curated routes / 73 hand-curated terminals) and
`data/causeways.json` (11 tidal/bridge entries). UI ships the "How to get
there" block on every island details panel, dashed-polyline ferry layer
on the detail map, `⛴` icons in the sidebar, ferry-aware chatbot intent,
verified/stale badges, drive-time pills (London / Glasgow / Edinburgh /
Belfast / Dublin), Trainline + Discover Cars affiliates with
`rel="sponsored"`, 12 SEO landing pages with `TouristTrip` JSON-LD per
route, and a Dijkstra-backed multi-island itinerary builder triggered
via `?trip=startId,endId`. Orchestrator `scripts/refresh_ferries.py`
runs the full pipeline monthly and emits
`data/ferries_stale_report.json`. Full operator-by-operator notes in
[`FERRIES.md`](FERRIES.md).

**2026-05-11 18:30 UTC+1** — Tier A/B priority shipping. **Per-island
image galleries** (lazy-loaded `data/galleries.json`, harvested by
`scripts/enrich_images_v4.py`, hooked into the existing thumb-strip);
**fuzzy/typeahead sidebar search** (diacritic-insensitive, subsequence-
tolerant, scored not alphabetical); **cultural-names enrichment**
(`scripts/enrich_names.py`) → 184 new label fills across `fr / ga / sco /
cy / gd / kw / gv`; **CSV-skip geocoder** (`scripts/geocode_csv_skips.py`)
launched to recover the 235 unmatched rows via Wikidata
`wbsearchentities` + bbox filtering.

**2026-05-11 17:55 UTC+1** — Big session. **v3 enrichment complete**
(2,263 adoptions; 3,342 / 6,748 islands now have photos, 49.5 %).
**OS Leisure** detail view shipped (EPSG:27700, paper-map detail) with
Leisure/Outdoor/OSM basemap switcher. **User CSV merged**: 399 existing
entries enriched, 7 new entries added (6 archipelago groupings +
Rockall), 7 duplicates auto-deduped via a follow-up pass when the matcher
was patched to handle "Isle of"/"Sanda Island" name variants.

---

## 1. Dataset at a glance (`data/islands.json`)

| Metric | Value |
|---|---|
| **Total islands** | **7,308** |
| File size | 8.0 MB |
| Total lines | ~283,000 (post v3 + CSV + reclass) |

### By type (post `unknown`-queue drain, 2026-05-12)

| Type | Count | Source mix |
|---|---:|---|
| `sea` | **5,049** | tier-a/b/default-confirmed + manual-override 57 + Tier-4 misclassifications corrected |
| `lake` | **1,329** | tier-a 878 · tier-b 213 · wd-p206 24 · osm-water-pip 133 · osm-water-near 44 · wp-category 4 · crannog 3 · manual-override 30 |
| `river` | **397** | tier-a 202 · tier-b 36 · thames-list 22 · wd-p206 56 · osm-water-near 32 · manual-override 47 |
| `unknown` | **1** | Great Arthur House (Barbican Estate building, awaiting upstream CSV cleanup) |

### By nation

| Nation | Count |
|---|---|
| Scotland | 3,128 |
| Ireland | 1,852 |
| England | 953 |
| Northern Ireland | 469 |
| Wales | 187 |
| Crown Dependency (IoM, Channel Is., etc.) | 162 |

### By type

| Type | Count |
|---|---|
| Sea | 5,382 |
| Lake | 1,097 |
| River | 262 |

### Field coverage

| Field | Coverage |
|---|---|
| `osmId` | 5,853 (87%) |
| `wikidata` Q-ID | 2,698 (40%) |
| `wikipedia` URL | 1,043 (15%) |
| `parentWaterBody` (inland) | 1,351 (20%) |
| `images[]` (>=1 image) | **3,342 / 6,748 = 49.5 %** (v3 complete) |
| `galleries.json` (extra images, lazy-loaded) | growing — v4 in flight, target ~3 extras × 3,342 = ~10 k extras |
| `names.{gd,cy,ga,gv,kw,sco,fr,nrf}` (non-English) | **961** islands with ≥1 non-English label (777 pre-existing + 184 new) |
| `population` | 141 (curated mostly) |

---

## 1b. Ferry corpus (`data/ferries.json`)

| Metric | Value |
|---|---|
| Routes | **347** |
| Operators | **54** |
| Terminals | **903** |
| Terminals matched to an islandId | **366** |
| Manually curated routes | 50 |
| Causeways | 11 |

Route sources: `osm-relation` 156 · `gtfs` 141 · `operator-page` (manual) 50.

Operators by country: Scotland 14 · Ireland 13 · England 12 · Wales 3 · Northern Ireland 3 · International 3 · Isle of Man 1 · Channel Is. 4 · France 1.

Harvest methods: `gtfs` 7 · `scrape` 25 · `manual` 22.

See [`FERRIES.md`](FERRIES.md) for the full operator inventory, ToS notes, and refresh cadence.

---

## 2. Currently running

| Process | Started | ETA | Owner | Notes |
|---|---|---|---|---|
| _(none)_ | — | — | — | P0b partial apply done; hills (DoBIH/Wikidata) + geology WMS still to run locally. |
| ~~`scripts/enrich_names.py` → …~~ | 2026-05-14 20:30 UTC+1 | — | — | Superseded / not running. |
| ~~`scripts/autonomous_run.sh`~~ | 2026-05-14 06:45 UTC | — | — | Stalled on Commons 429 during image v5. |
| ~~`scripts/overnight_runner.sh` (PID 71005)~~ | 2026-05-12 20:30 UTC | — | — | Superseded; see QUEUE.md. |
| ~~`python3 scripts/compute_drive_times.py` (PID 70453)~~ ✅ done 2026-05-11 20:25 | 2026-05-11 19:55 | ~30 min | main agent | OSRM batch drive-time bands from London / Glasgow / Edinburgh / Belfast / Dublin to each mainland terminal. Now uses `curl` via `subprocess` after diagnosing a Python TLS handshake failure against the public OSRM demo server. **Result**: 535 of 538 mainland terminals populated; 3 unreachable in OSRM's road graph. |

### Completed today (2026-05-11)
- **Gallery v4 phase 1** — wired `data/galleries.json` lazy-fetch on first
  island click; merge with `island.images[]` is idempotent and cached on
  the island object. Existing thumb-strip + hero-swap UI picks up the
  extras automatically. Tracking-UTM params stripped from Commons URLs.
- **Fuzzy/typeahead search** in the sidebar (`applyFilters` rewrite,
  `_scoreIsland`) — exact > prefix > word-start > substring > subsequence.
  Diacritic-insensitive ("Eilean Mor" → "Eilean Mòr"). Cache normalised
  search strings on the island record so 6,748× per keystroke is cheap.
- **Cultural-names enrichment** — `scripts/enrich_names.py` populated
  `names.{lang}` for 184 islands via Wikidata `wbgetentities labels`.
  Largest wins: 135 fr (Channel Islands), 47 ga, 15 sco. UI already
  rendered these via `renderAltNames`; just needed data.
- **v2** (`scripts/enrich_images.py`, Wikidata P18 + Wikipedia pageimages)
  finished at 12:17 — added 290 photos (789 → 1,079).
- **v3 first attempt** (PID 39072, no checkpointing) was killed at 12:48 with
  800/5,662 processed; all in-memory work lost. Caches survived → fast replay.
- **v3 second run** (PID 56783, checkpointed) finished at 17:13 after ~1 h 45 m.
  Adopted: 172 from Commons category, 5 from OSM `image` tag, 2,086 from
  Commons radial geosearch (the workhorse). Final coverage: 3,342 / 6,748.
- **`areaKm2` mis-scaling fix** applied at ~15:25. 67 entries had their stored
  area divided by 100 (Wikidata returned hectares stored as km² by
  `ingest_sources.py`). Backup at `data/islands.json.before-area-fix`.
- **OS Leisure detail view** shipped at 17:13 via proj4leaflet (EPSG:27700).
- **User CSV merge** (`scripts/merge_csv.py`) at 17:30. 665 rows → 399 enriched,
  16 added → after auto + manual dedup → 7 kept as new entries.

---

## 3. File inventory (data/)

| File | Size | Last write | Purpose |
|---|---|---|---|
| `islands.json` | 5.9 MB | 11:33 | Canonical dataset. |
| `islands_index.json` | ~4.5 MB | 2026-05-16 | Slim map/list/search scaffold; regenerate with `scripts/build_islands_index.py`. |
| `islands.json.before-ingest` | 4.5 MB | 11:33 | Pre-discovery-ingest backup. |
| `curated.json` | 34 KB | 2026-05-10 22:05 | Hand-curated 27-island spine. Do **not** delete entries. |
| `crowd_pins.json` | small | 2026-05-15 | Maintainer-curated community pins (separate from `islands.json`). See `docs/CROWD-PINS.md`. |
| `osm_raw.json` | 1.2 MB | 2026-05-10 22:26 | Cached Overpass island response. |
| `water_raw.json` | 274 MB | 2026-05-11 07:16 | Cached Overpass water-body response (large). |
| `inland_classification_report.json` | 159 KB | 11:33 | Audit trail for Tier A + B classifier. |
| `discovery_ingestion_report.json` | 8 KB | 11:33 | What each discovery source added. |
| `image_enrichment_report.json` | 57 KB | (v1 = 10:28; v2 in flight) | Image provenance + spot-checks. |
| `cache_wd_islands.json` | 2.4 MB | 11:20 | Wikidata SPARQL islands cache. |
| `cache_wikidata.json` | 227 KB | 11:45 | Wikidata P18 image lookups (live-updated). |
| `cache_commons.json` | 435 KB | 10:14 | Commons file-info cache. |
| `cache_pageimages.json` | 10 KB | 10:03 | Wikipedia pageimages cache. |
| `cache_pageprops.json` | 1 KB | 10:13 | Wikipedia pageprops cache. |
| `cache_thames.json` | 27 KB | 11:20 | River Thames discovery cache. |
| `cache_crannogs.json` | 2 KB | 11:32 | Crannog discovery cache. |
| `cache_designations.json` | 107 B | 11:21 | Statutory designations cache (empty, source still pending). |
| `candidates_*.json` | varies | 11:20–11:32 | Pre-merge candidate sets from each discovery source. |
| `ferries.json` | ~ 400 KB | 2026-05-11 | 347 ferry routes (156 OSM + 141 GTFS + 50 manual). |
| `operators.json` | ~ 60 KB | 2026-05-11 | 54 ferry operators with Wikidata IDs, ToS disclosures, harvest methods. |
| `ferry_terminals.json` | ~ 320 KB | 2026-05-11 | 903 canonical terminals incl. drive-times + cultural names. |
| `ferries_manual.json` | ~ 80 KB | 2026-05-11 | 50 hand-curated routes / 73 terminals (input to `merge_ferries.py`). |
| `causeways.json` | ~ 10 KB | 2026-05-11 | 11 tidal / bridge access points (Lindisfarne, St Michael's Mount, Davaar, etc.). |
| `ferries_stale_report.json` | < 1 KB | 2026-05-11 | Auto-generated by `refresh_ferries.py`; routes with `lastVerified` ≥ 180 days. |

---

## 4. Frontend state

- **Two-phase island load**: `data/islands_index.json` first (then merge
  `data/islands.json` in place) so the map can paint sooner on slow links;
  regenerate the index after every `islands.json` mutation.
- Static app served by `python3 -m http.server` (currently port 8767).
- Marker clustering: **on** by default (`#cluster-toggle`).
- List virtualisation: **active** (renders only visible items, ~30 at a time).
- **OS Maps detail view: full Leisure shipped (17:13).** The details panel
  has a three-button basemap switcher: **OS Leisure** (EPSG:27700,
  paper-style 1:25k/1:50k via proj4leaflet — default in GB), **OS
  Outdoor** (EPSG:3857), and **OSM** (universal fallback). Disabled
  buttons indicate what would unlock with a key or inside GB. Selection
  persists across island switches via `localStorage.detailBasemap`.
  proj4 + proj4leaflet load from unpkg (≈98 KB combined). API key from
  `window.OS_MAPS_API_KEY` or `localStorage.osMapsApiKey`. See
  [`OS-MAPS.md`](OS-MAPS.md).
- Polygon overlays: lazy-fetched from Overpass on island click for islands
  with `osmId`.
- **Per-island image galleries**: `data/galleries.json` (separate file,
  lazy-fetched on first island click) supplies up to 3 extra photos per
  island. The merge into `island.images[]` is done once and cached on the
  island object so re-renders are O(1). The existing thumb-strip below the
  hero now shows the full set; clicking a thumb swaps the hero (already
  wired up). See `loadGalleries` / `ensureGalleryMerged` /
  `refreshGalleryInPlace` in `app.js`.
- **Sidebar search is fuzzy/typeahead** as of 2026-05-11: the search box
  scores islands per keystroke with prefix / word-start / substring /
  subsequence matching, diacritic-insensitive. Sort is by score when a query
  is active; alphabetic when the box is empty (with-photo first when **Has
  photo** is on).
- **Discovery filters** (2026-05-16): topbar toggles/selects for photo,
  ferry-accessible, summit/elevation, minimum area, subtype, and
  curated / hide-unconfirmed. Ferries preload after islands load so the
  ferry filter enables without opening an island first.
- **Crowd pins**: optional gold markers from `data/crowd_pins.json`; **Suggest
  island** opens a map pick + GitHub issue (no on-site accounts). Toggle
  **Crowd pins** in filters. See `docs/CROWD-PINS.md` and `crowd-pins.js`.
- **Chatbot ("Island finder")**: floating "Ask" button bottom-right opens a
  chat panel. Local-only NLU. Recognises nation, type, subtype, archipelago,
  feature, size, sort, **proximity (`near <city>` / `within N km of …`,
  resolved against a 30-city UK + IE + Crown gazetteer)**, **ferry intent
  (`ferries to …`, `summer car ferries to the Hebrides`, `ferry from Oban`)**,
  and reflects each query into the URL as `?ask=…` for shareable permalinks.
  Result cards show the image source as a clickable cross-reference. See
  `app.js → CHAT_*`, `renderDetailMap`, and styles `.chat-*` /
  `.detail-map-*` for implementation.
- **Ferry layer**: lazy-loaded on first island click via `loadFerries()` +
  `loadCauseways()`. The details panel ships a "How to get there" block
  with operator-branded ferry cards (route label, duration, frequency /
  seasonality / type pills, verified/stale badge, drive-time pills,
  Trainline + Discover Cars affiliate links, "Book ↗" CTA) and a
  separate "Causeway access" block for tidal-causeway islands. The detail
  map renders dashed-polyline ferry routes + terminal markers; the
  sidebar shows a `⛴` icon next to ferry-accessible islands. SEO landing
  pages (12 of them) ship under `ferries/` with `TouristTrip` JSON-LD per
  route. (Trip-planner overlay removed 2026-05-16.) See [`FERRIES.md`](FERRIES.md).

---

## 5. Known good (smoke checks)

After any data run, the following must remain correct (see `VALIDATION.md` for
the full set):

- `Isle of Skye` → sea, Scotland, large polygon, image present.
- `Devenish Island` → **lake** (Lower Lough Erne), Northern Ireland.
- `Eilean a' Bhuidhe` (Loch Lomond) → lake, Scotland.
- `Isle of Wight` → sea, England.
- `Achill Island` → sea, Ireland.

---

## 6. Known issues / debt

- ~5,400 unnamed inner-ring inland features were intentionally **excluded**
  during Tier A. Some of these may be genuine, named-but-unmapped islands. See
  `METHODOLOGY-INLAND.md` §6.
- `population` is only set for ~141 curated/Wikidata-enriched entries — most
  small islands lack population data anywhere upstream.
- **848** entries still lack an `osmId` (mostly Wikidata-only; OSM has no
  `wikidata=` tag on a way/relation for **841** cached misses). Polygon overlay
  needs `osmType`+`osmId` (way/relation). Re-run `backfill_osm_from_wikidata.py`
  after refreshing cache.
- Belle Isle (Windermere) has no Wikidata Q-ID, so no image source — should
  resolve in v3 via Commons geosearch.
- **`areaKm2` mis-scaling (mostly fixed at 15:25).** Root cause: not
  `fetch_islands.py` but `scripts/ingest_sources.py` line 290 — Wikidata's
  `wdt:P2046` was read raw, which is in **hectares** for individual islands
  but in **km²** for whole-country entries (Great Britain, Ireland). 67
  entries patched. A handful of small islands in the 1–200 km² band may
  still be off (e.g. Cardigan Island shown as 40 km², real ~0.24 km²) — the
  fix's threshold is conservative. **Long-term fix**: rerun the SPARQL
  query with proper unit normalisation in `ingest_sources.py` (extract the
  unit Q-ID alongside the value).
- 235 CSV rows skipped during merge: 71 had ambiguous names (multiple
  matching candidates without DMS coords to disambiguate, e.g. multiple
  "Pabbay"/"Flodday"); 164 are genuinely missing from our OSM data
  (small Hebridean / Irish / French islets). See
  `data/csv_import_report.json` → `skipped_no_coords_no_match`. A future
  pass could geocode them via Wikipedia/Wikidata lookups.
- Geograph direct API now returns 451 ("Unavailable For Legal Reasons") for
  unauthenticated callers. We route around it via Commons geosearch (which
  surfaces Geograph uploads that landed on Commons).
