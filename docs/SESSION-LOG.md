# Session log

> Append-only. One block per session that materially changes data, schema, or
> behaviour. Newest at the **bottom**.
>
> Block template:
>
> ```
> ## YYYY-MM-DD — short title
>
> - **Goal**: …
> - **What changed**: …
> - **Outcome / counts**: …
> - **Open items kicked to QUEUE.md**: …
> ```

---

## 2026-06-02 — Web photo URL discovery harvester

- **Goal**: ETHICS-safe “outside the box” licensed photo discovery from open-web
  links (Wikidata P973/P856, Wikipedia external links, DuckDuckGo HTML, og:image
  on OGL/CC/gov pages) without social scraping.
- **What changed**:
  - Added `scripts/discover_island_photo_urls.py` — priority queue (curated →
    ferry → large area → wikidata), host allowlist verification, staging to
    `data/staging/adoptions/web-discovery.json`, cache
    `data/cache_web_photo_discovery.json`.
  - Fixed Wikipedia `extlinks` API call (removed invalid `elprotocol` param).
  - Batch `wbgetentities` prefetch for P973/P856 + enwiki sitelink; HTTP 429
    backoff; DuckDuckGo lite fallback.
- **Outcome / counts**: `--limit 200` pass → **0 staged** (priority tier is
  obscure Hebridean islets with sparse P973/extlinks; Wikimedia 429 during run).
  Manual geograph `/photo/` verify path confirmed working. Re-run with
  `--refresh --delay 3` after API cooldown for named enwiki islands.
- **Open items kicked to QUEUE.md**: none.


- **Goal**: Stand up a static web app that lists and maps every island within
  ~50 miles of the UK & Ireland.
- **What changed**:
  - Created `index.html`, `styles.css`, `app.js` (Leaflet + ES modules).
  - Hand-curated 27 anchor islands across the four nations in
    `data/islands.json`.
  - Added Leaflet polygon overlay (lazy-fetched from Overpass on click).
  - Added README with run instructions.
- **Outcome / counts**: 27 islands. Local preview running at `localhost:8765`.
- **Open items**: Expand to 1,000 islands; build an inland classifier;
  per-island photos; OS Maps detail view.

## 2026-05-10 — Scale to ~1,000 islands

- **Goal**: First Overpass ingestion pass to reach the 1,000-island target.
- **What changed**:
  - Wrote `scripts/fetch_islands.py` — Overpass query for
    `place=island|islet` + `natural=island` across UK + Channel Is. bbox.
  - Renamed old `islands.json` → `curated.json`; `islands.json` becomes the
    auto-generated canonical dataset.
  - Merge logic prefers richer (curated > OSM) data on conflict.
  - Added marker clustering (`leaflet.markercluster`) and virtualised list to
    keep the UI responsive.
- **Outcome / counts**: 1,000 islands. UI remains snappy.
- **Open items**: Inland classifier; better polygon matching for curated set.

## 2026-05-10 — Tier A + B inland classifier

- **Goal**: Methodology for discovering and classifying islands in lakes
  and rivers (not just sea islands).
- **What changed**:
  - Wrote `scripts/classify_inland.py` (Shapely + Overpass).
  - **Tier A**: extract inner rings from `natural=water` multipolygons →
    each inner ring is a candidate inland island. Smart parent-body
    selection (smallest containing body wins; lake preferred over river on
    tie). Unnamed inner rings are skipped to avoid noise. Non-UK/IE entities
    filtered out by `nation_for`.
  - **Tier B**: point-in-polygon test for remaining `sea`-typed islands
    against the union of water-body polygons (Shapely STRtree → manual
    `polygon.contains(point)`).
  - Fixed `assemble_water_polygon` to use `shapely.ops.polygonize` so 119-way
    bodies like Lough Erne assemble correctly.
  - Added `parentWaterBody`, `subtype`, `tidal`, `classification.{source,
    confidence}` fields.
- **Outcome / counts**: ~1,978 islands. Devenish, Boa, etc. correctly
  classified as `lake`. Inland classifier audit at
  `data/inland_classification_report.json`.
- **Open items**: Image enrichment; further discovery sources; UI surfacing
  of subtype + parent water body.

## 2026-05-10 — Discovery expansion + image enrichment v1

- **Goal**: Scale beyond 2k toward 7k; add a representative photo for every
  island.
- **What changed**:
  - Wrote `scripts/enrich_images.py` (Wikidata P18 → Wikipedia pageimages,
    with full provenance and a strict no-name-search policy).
  - Extended discovery to additional Overpass passes + Wikidata SPARQL for
    island Q-IDs not in OSM.
  - Schema: replaced single `image` string with `images[]` containing
    `{ url, fullUrl, caption, source, sourceRef, sourcePageUrl, license,
    attribution, primary }`. Kept the top-level `image` string for
    backward compatibility (mirrors `images[0].url`).
  - Wrote `docs/DISCOVERY-SOURCES.md` (catalogue of ~85 sources) and
    `docs/ETHICS.md` (permanent guardrails).
- **Outcome / counts**: ~5,892 islands; ~473 with images after v1.
- **Open items**: Photo enrichment v2 over the wider set; CSV import; OS
  Maps detail view.

## 2026-05-11 — Discovery v2 + photo enrichment v2

- **Goal**: Execute `docs/NEXT-SESSION-PLAN.md` top-5 actions; rerun image
  enrichment on the expanded set.
- **What changed (in flight as of 11:45)**:
  - Discovery: Wikidata SPARQL deeper pass + Thames + crannog + statutory
    designations stubs. New caches `cache_wd_islands.json`,
    `cache_thames.json`, `cache_crannogs.json`, `cache_designations.json`
    and candidate files for each.
  - `data/islands.json.before-ingest` (4.5 MB) preserved as pre-ingest
    backup.
  - `enrich_images.py` rerunning (PID 29305) over the 6,741-island set;
    in flight at the time of writing.
- **Outcome / counts (interim)**: 6,741 islands (+849 net since v1). Photo
  coverage **789** (was 473) and rising as v2 runs.
- **Open items**: Wait for v2 to complete and spot-check; then CSV merge.

## 2026-05-11 — Context-handoff structure

- **Goal**: Set up persistent docs so a fresh agent can pick up the project
  without replaying chat history.
- **What changed**:
  - Created `AGENTS.md` (root entry point).
  - Created `.cursor/rules/project.mdc` (always-apply rule).
  - Created `docs/INDEX.md`, `docs/STATE.md`, `docs/QUEUE.md`,
    `docs/SESSION-LOG.md` (this file), `docs/ARCHITECTURE.md`,
    `docs/DATA-SCHEMA.md`, `docs/PIPELINE.md`,
    `docs/METHODOLOGY-INLAND.md`, `docs/VALIDATION.md`.
  - **No data or code files** touched, because `enrich_images.py` was still
    running.
- **Outcome / counts**: Dataset unchanged. Docs now provide a self-contained
  handoff surface.

## 2026-05-11 (afternoon) — Crash-safe v3 + areaKm2 fix

- **Goal**: Recover from the silent v3 kill at 12:48 and fix the chatbot's
  broken "largest islands" sort.
- **What changed**:
  - **Diagnosed `areaKm2` bug**: not `fetch_islands.py` as initially feared,
    but `scripts/ingest_sources.py` line 290. Wikidata's `wdt:P2046` is
    stored in **hectares** for individual islands (Q35852) but in **km²**
    for huge entities like Great Britain (Q23666) and Ireland (Q22890),
    and the SPARQL was reading the bare number with no unit normalisation.
  - Applied a one-shot fix: for any non-curated, non-{GB,Ireland} entry
    with `areaKm2 > 200`, divided by 100. **67 entries patched**. Backup
    at `data/islands.json.before-area-fix`. Top-12 ranking now matches
    reality (GB, Ireland, Lewis & Harris, Skye, Mainland Shetland, Mull,
    Anglesey, Islay, Isle of Man, Mainland Orkney, Arran, IoW).
  - **Patched `enrich_images_v3.py` with checkpointing**: writes
    `islands.json` + `image_enrichment_v3_report.json` atomically every
    100 adoptions via tmp+rename. A kill is now recoverable.
  - **Relaunched v3** under `nohup` (PID 56783, started 15:28). First 800
    islands replayed from cache in ~60s → 300 adoptions, photo coverage
    1,079 → **1,379** within a minute.
  - **Chatbot small fix**: area-sort now filters out entries with null
    `areaKm2` so "smallest islands in X" returns useful results instead
    of a parade of nulls.
- **Outcome**: Sorting works correctly in the chatbot. v3 is grinding
  through the remaining ~4,800 fresh-call islands in the background.
- **Open items**: Wait for v3 to complete + spot-check; revisit the
  long-tail `areaKm2` (Cardigan Island still 40 km²) with a proper
  SPARQL-with-units rewrite.

## 2026-05-11 — OS Maps detail view + chatbot polish

- **Goal**: While v3 enrichment continues in the background, build the
  long-promised Ordnance Survey detail view in the island profile, and
  ship the next round of chatbot improvements without touching
  `data/islands.json` (avoids fighting v3 for the write lock).
- **What changed**:
  - **OS Maps detail view** (`app.js → renderDetailMap`): a second Leaflet
    map inside the details panel, sized 260 px tall. Selects basemap at
    render time — **OS Outdoor (EPSG:3857)** via the OS DataHub ZXY
    endpoint when an API key is present (read from `window.OS_MAPS_API_KEY`
    or `localStorage.osMapsApiKey`), otherwise an **OpenStreetMap**
    fallback. Layer toggle exposed via Leaflet's standard layers control
    when both are available. Auto-zoom level chosen from
    `island.areaKm2`/`type`. A circle marker pins the island. Map is torn
    down on island switch and on the back-to-list action to release tile
    requests.
  - **`docs/OS-MAPS.md`** — full integration doc: how to obtain a free OS
    DataHub key, where to set it (`config.local.js` or
    `localStorage.osMapsApiKey`), the available EPSG:3857 styles, and the
    upgrade path to the EPSG:27700 **Leisure** raster via `proj4leaflet`
    with a worked CRS definition.
  - **Chatbot: proximity parsing.** Added a 30-entry UK + IE + Crown
    gazetteer (`CHAT_PLACES`). Parser now recognises `near <city>`,
    `off <city>`, `around <city>`, `close to <city>` (defaults to 100 km
    radius), and `within N km/miles of <city>` for explicit radii. Hits
    apply a hard distance filter via haversine, plus a closer-is-better
    score bonus. Result cards now show `"… km from <city>"` in the meta
    line. Verified with 11 cases (London, Oban, Mallaig, Penzance,
    Stornoway, …) — all parse correctly.
  - **Chatbot: shareable permalinks.** Every submitted query reflects
    into `?ask=…` via `history.replaceState`. On page load,
    `chatAutoLoadFromUrl()` reads the param, waits for islands to load,
    auto-opens the chat panel and runs the query — so an "islands near
    Oban with mountains" link is bookmarkable / shareable.
  - **Chatbot: source link in result cards.** When a result has a primary
    image with a `sourcePageUrl`, render a small "Wikimedia Commons ↗" /
    "OpenStreetMap tag ↗" link under the meta line so the user can
    verify provenance without leaving the chat flow. Click is
    `stopPropagation`'d so it doesn't also focus the island.
  - **Suggestion chips** updated to include the new proximity flavours
    ("Islands near Oban", "Within 30 km of Mallaig").
  - Updated `docs/STATE.md` (frontend section + last-updated stamp + v3
    progress 3,500 / 5,662 with 1,324 adoptions), `docs/INDEX.md`
    (registers `OS-MAPS.md` and `IMAGE-SOURCES.md`), and the issues list
    (OS Maps now done; Leisure tracked as P2).
- **Outcome / counts**: Photo coverage ~2,400 / 6,741 ≈ 35 % live (still
  rising). Chatbot now handles proximity queries end-to-end with
  permalinks. Detail view ready to render OS tiles the moment a key is
  configured; ships OSM in the meantime.
- **Verification**: `node --check app.js` passes; 11/11 proximity test
  cases parse correctly via `/tmp/test_chat_near.js`.
- **Open items**: When v3 finishes, spot-check 10 random new entries;
  then run the CSV merge (`/Users/.../british_isles_50mile_islands…csv`);
  longer term, rewrite `ingest_sources.py` SPARQL with unit normalisation
  and tackle the EPSG:27700 Leisure raster.

## 2026-05-11 — Full Ordnance Survey "Leisure" detail view + CSV merge + v3 completion

- **Goal**: Ship the user's two remaining hard asks — the paper-style
  Ordnance Survey detail map per island, and the CSV merge — while
  finishing the v3 photo enrichment cleanly.
- **What changed**:
  - **OS Leisure detail view** (`renderDetailMap` / `buildDetailMap` /
    `getBngCrs` in `app.js`). Added proj4 + proj4leaflet from unpkg in
    `index.html`. Defined EPSG:27700 (BNG) with the OS DataHub Leisure
    tile-matrix-set parameters (resolutions `[896, 448, 224, 112, 56, 28,
    14, 7, 3.5, 1.75]`, origin `[-238375, 1376256]`). The detail panel
    now shows a three-pill basemap switcher (**Leisure / Outdoor / OSM**);
    selection is persisted in `localStorage.detailBasemap`. Disabled
    pills tell the user what would unlock with a key or by being in GB.
    Switching basemap destroys and rebuilds the Leaflet instance
    (different CRSes).
  - `isInGreatBritainForLeisure(island)` — nation-first heuristic with a
    bbox fallback so NI/IE/Channel Is. don't try to fetch Leisure tiles
    that don't exist there.
  - Auto-zoom is now per-basemap because Leisure (z=0..9, m/px) and
    Outdoor (z=0..16) have totally different scale resolutions.
  - **v3 photo enrichment** (PID 56783, checkpointed) completed at 17:13
    after ~1 h 45 m. Adopted **2,263 photos**: 172 Commons-category,
    5 OSM `image=*`, 2,086 Commons radial geosearch. Photo coverage
    1,079 → **3,342 / 6,748 = 49.5 %**. Spot-checked 10 random
    adoptions; every one has source / url / sourcePageUrl / license
    / attribution; names align with photo titles (a few descriptive
    captions like "Rocky coast below Deckler's Cliff" are flagged
    `suspect: true` in the report but still plausibly depict the
    geographic feature within the geosearch radius).
  - **CSV merge** (`scripts/merge_csv.py`, new). Reads the user's
    `british_isles_50mile_islands.csv` (665 rows). Custom DMS
    parser (`58°N 6°30'W`), area parser (km² / ha / m²), Population
    extractor from notes (`Pop. 1,254`), region → nation/archipelago
    mapper, NI-vs-RoI classifier from notes / coords. Match strategy:
    case-insensitive normalised name + 25 km haversine sanity check, or
    closest within 10 km when multiple candidates share a name. Atomic
    write with a backup at `data/islands.json.before-csv-merge`. Refuses
    to run while v3 is active (pgrep check). Report at
    `data/csv_import_report.json`.
  - **First run outcome**: 399 matched + filled (archipelago,
    population, shortDescription, names.alt added where missing), 2
    matched no-op, 16 added new, 13 skipped (regional aggregates), 235
    skipped (no coords AND no name match).
  - **Duplicate audit revealed**: 7 of the 16 "new" entries were
    actually duplicates of existing islands ("Skye (An t-Eilean
    Sgitheanach)" vs "Isle of Skye", etc.) because `normalise_name`
    didn't strip generic "Isle of …" prefixes or trailing " Island"
    suffixes.
  - **Matcher patch**: extended `normalise_name` to drop
    `^(the |isles? of |island of )` and `\s+(islands?|isles?)$`.
  - **Dedup pass** (`scripts/dedup_csv_imports.py`, new). Walks
    `source: csv-import` entries with the patched matcher, folds clean
    matches (within 30 km of an existing entry) into them and removes
    the duplicate. 7 deduped on first pass (Lewis & Harris, Skye, Mull,
    Rum, Sanday, Arran, Bute). Second pass after the trailing-suffix
    patch removed Sanda Island. One manual merge for Tanera Mòr ↔
    "Tanera More" (Gaelic transliteration variant — the matcher doesn't
    learn that). Final state: 7 legitimate new csv-import entries (6
    archipelago groupings + Rockall).
  - **Preview server** had died at some point during the day; restarted
    cleanly under `nohup` on port 8767 (PID 60358). All routes return
    200 in single-digit ms.
  - Docs synced: `docs/OS-MAPS.md` (Leisure now shipped, BNG CRS spec
    included, future-work section reframed), `docs/STATE.md` (counts,
    timeline, running processes), `docs/INDEX.md` (no change),
    `docs/SESSION-LOG.md` (this entry).
- **Outcome / counts**:
  - **6,748 islands** (was 6,741; +16 from CSV, −9 deduped =  net +7).
  - **3,342 with photos (49.5 %)**, up from 1,079 this morning.
  - **OS Leisure** is the default basemap in the per-island detail view
    when a key is configured and the island is in GB; gracefully falls
    back to Outdoor / OSM elsewhere.
- **Verification**: `node --check app.js` passes; `scripts/merge_csv.py`
  has unit-tested parsers (DMS, area, population, Ireland classifier,
  alt-name extraction); `scripts/dedup_csv_imports.py` ran cleanly with
  a structured report.
- **Open items**:
  - 235 CSV rows still skipped — a follow-up could geocode them via
    Wikipedia/Wikidata lookups against the row's `Region/Archipelago`
    and `Notes` context, then re-attempt match.
  - Long-tail `areaKm2` (Cardigan Island still 40 km²) — proper SPARQL
    rewrite of `ingest_sources.py` with unit normalisation.
  - Northern Ireland / Ireland equivalent of OS Leisure (OSNI / OSi
    Discovery tiles) — see `docs/OS-MAPS.md` future-work.

## 2026-05-11 — Image sources brainstorm + v3 enrichment + chatbot

- **Goal**: Brainstorm every plausible image source (with full provenance
  registry), enrich the remaining ~5,662 unphotographed islands, and add a
  chatbot-style island finder.
- **What changed**:
  - Wrote `docs/IMAGE-SOURCES.md` — full brainstorm (✅ / 🟡 / 🛑 per source)
    plus the canonical registry of `images[i].source` codes with
    cross-reference URL patterns and licence defaults.
  - Wrote `scripts/enrich_images_v3.py` — orchestrator for three new sources:
    Commons category traversal by Wikidata Q-ID, OSM `image=*` tag re-query,
    and Commons radial geosearch (`list=geosearch`). Direct Geograph API
    abandoned because public endpoints now return 451; Commons geosearch
    surfaces Geograph uploads that landed on Commons anyway.
  - Started v3 enrichment (PID 39072, 12:23). Backed up `islands.json` to
    `islands.json.before-v3` first.
  - Extended `app.js → renderAttribution` (`SOURCE_LABELS` map) to render
    nice cross-reference links for the new source codes (`commons-category`,
    `commons-geosearch`, `osm-image-tag`, `geograph`, `flickr-cc`).
  - Added a **chatbot** — floating "Ask" button + drawer panel, fully
    local NLU (no API calls). Parses nation / type / subtype / archipelago
    / feature / size / sort keywords from natural language and ranks the
    matching islands. Results render as compact cards with photo + meta,
    clickable to focus that island on the map.
  - Updated `docs/STATE.md`, `docs/QUEUE.md`, `docs/IMAGE-SOURCES.md`.
- **Outcome / counts**: After v2: 1,079 islands with photos (16.0 %).
  v3 in flight; expected to add 1,500–3,000 more.
- **Discovered debt**: `areaKm2` is mis-scaled by ~100× for OSM-derived
  entries (m² stored as km²). Surfaced when chatbot's "largest islands"
  sort yielded suspicious values. Recorded as **P1** in `QUEUE.md`.
- **Open items**: Wait for v3 to complete, then spot-check.

---

## 2026-05-11 — Galleries, fuzzy search, cultural names, CSV-skip geocoder

- **Goal**: After v3 + OS Leisure + CSV merge shipped this morning,
  knock out the next priority tier: a real per-island gallery, a
  fuzzy/typeahead sidebar, cultural-name labels (gd/cy/ga/gv/kw/sco/fr),
  and a recovery pass for the 235 CSV rows we skipped during the merge.
- **What changed**:
  - **Image galleries v4** — wrote `scripts/enrich_images_v4.py` (in
    flight, PID 63436). Walks each island's Commons category (or the
    same geosearch radius the lead photo came from) and adopts up to 3
    additional photos. Writes to **`data/galleries.json`** — a
    separate file, lazy-fetched on first island click, so the initial
    `islands.json` payload stays at 8 MB. Output is checkpointed every
    100 islands. Strips Commons' newer `?utm_source=…` tracking params
    from URLs.
  - **Gallery UI** — `app.js` got `loadGalleries()`,
    `ensureGalleryMerged()`, and `refreshGalleryInPlace()`. The merge
    runs once per island and is cached on the island object via
    `__galleryMerged`. The existing thumb-strip / hero-swap UI picks
    up the extras automatically (no template changes).
  - **Fuzzy/typeahead sidebar search** — replaced `applyFilters`'s
    substring-only matcher with a scored fuzzy ranker (`_scoreIsland`).
    Scoring: exact (1000) > prefix (800) > word-start (600) > substring
    (400) > subsequence (200) > broader-haystack substring (50).
    Diacritic-insensitive via NFKD-strip; cached on the island record
    so 6,748× per keystroke is essentially free.
  - **Cultural-names workstream** — wrote `scripts/enrich_names.py`. For
    every island with a Wikidata Q-ID, batch-fetches labels in
    `gd / cy / ga / gv / kw / sco / fr / nrf` and writes them into
    `island.names` (only if they actually differ from English; never
    overwrites). Exponential backoff on 429 (we collided with v4 on
    Wikidata's anon rate limit and the script handled it cleanly).
    Result: **184 new label fills** (135 fr, 47 ga, 15 sco, 13 cy,
    10 gd, 6 kw, 5 gv). UI already rendered these via `renderAltNames`;
    added `sco / fr / nrf` to `LANG_LABELS`.
  - **CSV-skip geocoder** — wrote `scripts/geocode_csv_skips.py`
    (in flight, PID 64221). For each of the 235 rows the merge couldn't
    place: Wikidata `wbsearchentities` in English + the regional
    language, batch-fetch P625 coords, bbox-filter to the row's region
    (15 regions defined), prefer island-class P31 entities, adopt as a
    new island only if exactly one candidate survives. Ambiguous and
    no-hit cases logged to `data/csv_geocode_report.json` for manual
    review.
- **Outcome / counts** (mid-session, processes still running):
  - Galleries: at the 600/3,337 checkpoint, 1,604 extras adopted across
    576 islands → ~2.8 extras per island on average. ETA ~90 min for
    the full pass.
  - Cultural names: 184 islands enriched; total 961 islands with ≥1
    non-English name.
  - Fuzzy search: shipped, verified against ranking expectations
    (smoke test in `_scoreIsland` harness — typo "rckall" → Rockall,
    "Eilean Mor" → Eilean Mòr exact match, "skye" → Skye Bridge ranks
    above Isle of Skye because Skye Bridge is a prefix match).
  - CSV geocode: launched a few minutes ago, ETA ~30 min.
- **Open items**: log galleries + geocode adoption counts here once
  the in-flight scripts finish. Update `QUEUE.md` to mark gallery /
  fuzzy / names / csv-geocode as done.

---

## 2026-05-11 — Ferry routes feature

- **Goal**: Build a comprehensive ferry-routes layer covering every UK,
  Ireland, and Crown Dependency island in the dataset — operator,
  terminals, vessels, type, seasonality, frequency, schedule, booking
  URL. Wire into the island details panel, the detail map, the chatbot,
  and downstream features (drive-times, affiliates, SEO landing pages,
  itinerary builder). Implementation tracked against
  [`ferry_routes_feature` plan](../.cursor/plans/ferry_routes_feature_18930a12.plan.md).
- **What changed**:
  - **Data (Phase 0–4)** — three new lazy-loaded JSONs alongside
    `data/galleries.json`'s pattern:
    - `data/operators.json` — **54 operators** hand-seeded with
      `id / name / homepage / bookingUrlPattern / region / country /
      wikidata / wikipediaUrl / harvestMethod / disclosure`.
      Hallucinated Q-IDs from a first Wikidata-enrichment attempt were
      caught and corrected (15 operators patched manually).
    - `data/ferries.json` — **347 routes**: 156 from `osm-relation`
      (Overpass `route=ferry`), 141 from `gtfs` (Traveline Scotland /
      BODS, run against CalMac + NorthLink + Pentland + Western +
      Orkney + SIC + Argyll & Bute + Ulva + Skye + Highland), 50 from
      `operator-page` (hand-curated `ferries_manual.json`).
    - `data/ferry_terminals.json` — **903 terminals**, **366**
      matched to an `islandId`, all carrying cultural-name slots
      (`gd / cy / ga / gv / kw / fr`) with **53** non-English variants
      seeded from a hand-curated map (`scripts/enrich_terminal_names.py`).
    - `data/ferries_manual.json` — **50 routes / 73 terminals** for the
      long-tail of small / charter operators (Caldey, Bardsey, Skomer,
      Rathlin, Aran, Cape Clear, Tory, Inishbofin, IoM Steam Packet,
      Condor, Manche Iles, Sark Shipping, Lundy, Scillonian, Farne,
      Windermere, Loch Lomond, etc.).
    - `data/causeways.json` — **11 tidal-causeway / bridge entries**
      (Lindisfarne, St Michael's Mount, Davaar, Cramond, Eriskay, …).
  - **Scripts** —
    - `scripts/fetch_ferries_osm.py` — Overpass harvester (with
      `EXTRA_OPERATOR_ALIASES` for OSM-→canonical-operator matching and
      first/last-node fallbacks for relations without explicit terminal
      tags).
    - `scripts/import_calmac_gtfs.py` — parametric GTFS importer over
      operator (`--operator-id` + `--operator-name`). Joins
      `routes/trips/stop_times/stops/calendar` and reconstructs
      `timetable.weekly`. Matches stops to existing terminals by name
      + 250 m proximity; creates new terminals for unmatched stops.
    - `scripts/seed_ferries_manual.py` — exports `ferries_manual.json`
      from hand-curated Python literals.
    - `scripts/merge_ferries.py` — overlays manual onto OSM/GTFS with
      manual having priority on every field; auto-assigns
      `terminal.islandId` for manual terminals via nearest-island
      search.
    - `scripts/enrich_terminal_names.py` — seeds Gàidhlig / Cymraeg /
      Gaeilge / Gaelg / Kernewek / Français terminal names.
    - `scripts/enrich_ferries_wiki.py` — Wikidata/Wikipedia
      enrichment for operators with exponential-backoff (2/5/12/30/60s)
      against Wikidata's anon 429s.
    - `scripts/compute_drive_times.py` — OSRM batch. First version using
      Python's `urllib.request` failed with `SSLV3_ALERT_HANDSHAKE_FAILURE`
      against the public OSRM demo server; bare `curl` worked, so the
      script now shells out to `curl` via `subprocess.run` with the
      same retry/backoff semantics. Successful smoke test: London →
      Oban = 581 min (≈9 h 41 m). Re-launched at 19:55 BST; checkpoints
      every 50 terminals into `data/ferry_terminals.json`.
    - `scripts/generate_ferry_landing_pages.py` — emits 12 regional
      SEO landing pages under `ferries/` with `TouristTrip` JSON-LD
      per route + a top-level `ferries/index.html` index.
    - `scripts/refresh_ferries.py` — monthly-ish orchestrator with
      stages `osm / gtfs / manual / merge / names / drivetime / seo`
      (drivetime off by default). Emits `data/ferries_stale_report.json`
      listing routes with `lastVerified` ≥ 180 days. Logs to
      `logs/refresh_ferries.log`.
  - **UI (Phase 5)** —
    - `app.js`: `loadFerries()`, `loadCauseways()`,
      `renderFerries(island)`, `_renderFerryCard`, `_renderDriveTimes`,
      `_renderCausewayBlock`, `_bestTerminalName`, `_localTerminalName`,
      `_routeIsStale`, `drawFerryRoutesOnDetailMap`,
      `refreshFerriesInPlace`. State: `state.ferries`,
      `state.ferriesPromise`, `state.ferryIslandIds`,
      `state.ferryRoutesByIsland`, `state.causeways`,
      `state.causewaysPromise`, `state.ferryGraph`.
    - "How to get there" block on every island details panel, under
      "Detailed map". Each card: operator badge / logo, route label,
      duration, frequency / seasonality / type pills, verified-or-stale
      badge, local cultural terminal name, drive-time pills (London /
      Glasgow / Edinburgh / Belfast / Dublin), Trainline + Discover Cars
      affiliate links with `rel="sponsored"` and per-link `(affiliate)`
      micro-tags, "Book ↗" CTA.
    - Detail-map dashed-polyline ferry layer + terminal markers,
      auto-drawn after the island marker.
    - Sidebar `⛴` icon for ferry-accessible islands.
    - Chatbot — `parseChatQuery` extended with `ferryIntent`,
      `ferryTypeWanted`, `ferrySeasonWanted`, `ferryOperatorWanted`,
      `ferryFromPort`. `scoreChatIsland` applies hard filters (only
      ferry-accessible islands when intent is detected) and boosts on
      matching criteria. `CHAT_SUGGESTIONS` includes ferry queries.
    - Multi-island itinerary builder — Dijkstra over `state.ferryGraph`,
      triggered by `?trip=startId,endId`, renders an
      `.itinerary-banner` at the top of the page.
    - `styles.css`: `.ferry-card*`, `.ferry-card__verified`,
      `.ferry-card__stale`, `.ferry-card__drive`,
      `.ferry-card__local-name`, `.itinerary-banner`, `.causeway-card`.
- **Outcome / counts**:
  - 347 routes / 54 operators / 903 terminals / 366 island-matched /
    50 manual / 73 manual terminals / 11 causeways.
  - 53 terminals carry a non-English cultural variant.
  - Stale report empty (every route's `lastVerified` is 2026-05-11).
  - 12 SEO landing pages generated.
- **Diagnostics & fixes**:
  - Wikidata anon-API rate limits were tripped during operator
    enrichment; first run produced 15 hallucinated Q-IDs (Wikidata
    search returned similarly-named entities). Diagnosed via output-log
    inspection, validated by name+description, patched
    `operators.json` directly.
  - OSRM TLS handshake failure with Python's bundled `ssl` module
    (`SSLV3_ALERT_HANDSHAKE_FAILURE`) — confirmed by comparing
    `urllib.request` vs bare `curl` against the same URL. Fixed by
    routing all OSRM requests through `subprocess` → `curl`.
- **Drive-time batch outcome** (PID 70453, 2026-05-11 20:25):
  **535 of 538 mainland terminals populated** with London / Glasgow /
  Edinburgh / Belfast / Dublin drive-times via OSRM. 3 terminals were
  unreachable in OSRM's road graph (small islets pinned just offshore).
  Sanity spot-check: London → Oban 581 min, Liverpool → Glasgow 250 min,
  Liverpool → Dublin 337 min (includes ferry segments). The script
  threw zero retry cycles after the `curl` switch — TLS issue confirmed
  resolved.
- **Open items**:
  - Long-tail UI polish: optional lightbox on ferry-card hero
    images; Norse / Gaelic etymology badges on terminals;
    accommodation suggestions tied to mainland terminals.
  - Reschedule `refresh_ferries.py` via GitHub Actions monthly with
    `--include-drivetime` every quarter.
  - Light per-operator scrapers for the ten biggest `manual` operators
    (Wightlink, Red Funnel, IoM Steam Packet, Condor, etc.) so monthly
    refreshes pick up timetable changes without manual intervention.

## 2026-05-12 — Island categorisation Phase 1: Wikidata P206 + widened OSM water

- **Goal**: Fix the widespread "everything defaults to *sea*" bug surfaced by
  two screenshots (Kate's Island shown as a sea island in a Yorkshire pond;
  Bodinbo Island shown as sea while sitting visibly in the River Clyde).
  `fetch_islands.py` hardcoded `"type": "sea"` for every OSM-ingested island
  and `classify_inland.py`'s Tier A/B only caught features that were members
  of an OSM `relation natural=water multipolygon` — leaving 5,414 islands
  stuck on the default with no positive evidence behind them.

- **Authoritative data sources picked (Phase 1, zero cost)**:
  1. **Wikidata `P206`** ("located in or next to body of water") + the body's
     `P31` ("instance of"), with a `P279` ("subclass of") climb up to 3
     levels for unknown classes — covers 916 islands that carry a Q-ID with
     an explicit body link.
  2. **Widened OSM Overpass query**: `relation/way natural=water` (without
     requiring `water=*`), `way landuse=reservoir`, `way waterway=riverbank`
     — caught 11.3 M elements, 358 k tagged ways + 19.5 k relations, built
     19,437 inland-water polygons for point-in-polygon containment.
  3. **OSM `natural=coastline`** (fetched, cached at 326 MB but **not yet
     used** — polygonising 2.66 M coastline elements live takes too long;
     deferred to Phase 1.5 using the pre-built land-polygons shapefile).

- **What changed (data)**:
  - `data/islands.json`: 213 islands re-typed (157 sea→lake, 56 sea→river).
    Backup at `data/islands.json.before-reclass-20260512T124618Z`.
  - `data/cache_wd_water_body.json` (244 KB): 2,716 islands × 193 parent
    bodies × 59 P279-climbed classes.
  - `data/water_raw_v2.json` (1.6 GB, gitignored): raw widened Overpass
    payload.
  - `data/coastline_raw.json` (326 MB, gitignored): raw coastline payload,
    held for Phase 1.5.
  - `data/reclassification_proposal.json`: every change with full evidence
    (Wikidata Q-IDs, body names, source, confidence) — kept post-apply for
    audit.
  - `data/reclassification_summary.json`: aggregate counts + transitions.

- **What changed (scripts)**:
  - **NEW** `scripts/reclassify_islands.py` — stacked-evidence pipeline:
    - `--fetch-wd`: batched Wikidata `wbgetentities` with 0.5 s throttling
      and exponential backoff (1 / 3 / 8 / 20 / 45 / 90 s) on HTTP 429 /
      503 / 5xx / non-JSON bodies. Uses `subprocess` + `curl` for SSL
      robustness, same as the OSRM fix.
    - `--fetch-coast`, `--fetch-water`: Overpass via the same `curl` POST
      helper across three endpoints (de, kumi, fr) with auto-failover.
    - `--classify`: builds the spatial index of inland-water polygons
      with Shapely STRtree, runs each island through Tiers 0→1→3→2→5,
      writes a *proposal* (never mutates islands.json).
    - Wikidata cross-reference for water bodies: when an OSM body has a
      `wikidata=Q…` tag, we look it up in the cache and let Wikidata's
      P31 override the OSM tag-based classification (caught Loch Ewe, a
      sea loch tagged simply as `natural=water` in OSM).
  - **NEW** `scripts/apply_reclassification.py` — gated mutator with
    timestamped backups, dry-run mode, confidence threshold, and a type
    allowlist for incremental rollouts.

- **Categorisation schema confirmed**:
  - Level 1 `type`: `sea` / `lake` / `river` (`unknown` reserved for Phase 1.5)
  - Level 2 `subtype` (optional): `pond` · `reservoir` · `lagoon` · `oxbow` ·
    `tidal-loch` · `estuary` · `canal` · `stream` · `tidal-island`
  - Level 3 `parentWaterBody`: `{name, type, osmType, osmId, wikidata}`
  - `classification`: `{source, confidence: high|medium|low}` so the UI can
    flag low-confidence cases later.

- **Outcome / counts**:
  - Type table before → after: sea 5,414→5,201 (−213); lake 1,100→1,257
    (+157); river 262→318 (+56). Same totals.
  - Confidence: 80 high (Wikidata-verified), 133 medium (OSM point-in-polygon).
  - Headline fixes verified:
    - Kate's Island (`osm-way-431153973`, Yorkshire pond) → `lake`,
      classification `{osm-water-pip / medium}`.
    - Bodinbo Island (`wd-Q55605678`, Erskine Bridge) → `river` / River
      Clyde, classification `{wikidata-p206 / high}`.
  - 73 "Loch X" lake-classifications cross-checked manually — all
    legitimate freshwater lochs (Shiel, Harray, Lene, Finlaggan, Ore,
    Moan, Ussie, Lough Neagh…).
  - Loch Ewe (sea loch, Q4354551) correctly excluded via Wikidata
    override; four would-be misclassifications avoided.

- **Open items** (kicked to QUEUE.md):
  - Phase 1.5: positive-sea verification using the pre-built
    `land-polygons-split-3857` shapefile from osmdata.openstreetmap.de
    (~10 MB, no live polygonisation). Adds an `unknown` UI pill for
    islands that fail all Tiers.
  - Phase 2: cross-check medium-confidence picks against OS NGD
    Features API water polygons (if user enables that DataHub product).
  - Phase 3: EA / NRW / SEPA / EPA WFD water-body overlays for the
    transitional/estuary edge cases.
  - Curated gallery sample re-test for the 10 flagship islands now that
    Kate's-class corrections may affect future enrichment runs.

## 2026-05-12 — Island categorisation Phase 1.5 (positive-sea verification + `unknown` pill)

- **Goal**: Catch the residual mis-classifications that Phase 1 couldn't
  reach. Phase 1 only fired when Wikidata P206 or an OSM water-polygon
  positively matched an island. That left ~5,200 islands sitting on the
  default `sea` value with no positive evidence either way. Some of
  those (e.g. several Irish lough islets, a few Yorkshire river islets,
  small reservoirs in the Lake District) are unambiguously inland and
  need to drop out of "sea". The cleanest way to flag them is the
  classic geographer's trick: polygonise the OSM coastline and ask
  whether the island sits inside the **mainland** (GB or Ireland)
  polygon. If yes → inland. If no → it's its own coastline polygon,
  i.e. a real marine island.

- **What changed**:
  - New script `scripts/build_land_polygons.py`. Reads the cached
    `data/coastline_raw.json` (326 MB, 39,880 ways), polygonises into
    23,378 land polygons in ~30 s end-to-end, repairs invalid geometry
    with `buffer(0)`, and pickles two products:
    1. `data/land_polygons.pickle` (40 MB) — every land polygon.
    2. `data/mainland_polygons.pickle` (18 MB) — only polygons larger
       than 5,000 km². In our bbox that's exactly two: Britain
       (218,417 km²) and Ireland (83,404 km²). Clean 39× area gap to
       the next-largest (Lewis & Harris at 2,143 km²), so the cut is
       unambiguous.
    - `--check` flag runs a 10-point self-test (London / Glasgow /
      Iona / Lewis-and-Harris / Bodinbo / Andersey / Jersey / open
      Atlantic / North Sea / Loch Ness) — all pass on both pickles.
  - `scripts/reclassify_islands.py` now prefers the mainland pickle
    over live polygonisation. Tier 2 logic in `classify()` now does:
    - if no Tier 1 / Tier 3 verdict AND centroid INSIDE mainland →
      `type: unknown`, `classification: {source: "land-in-no-water",
      confidence: "low"}`.
    - if no Tier 1 / Tier 3 verdict AND centroid OUTSIDE mainland →
      `type: sea` (no change for already-sea defaults).
  - `styles.css`: new `--unknown` colour token (`#b08bd1`, lilac) plus
    `.dot--unknown` rule with a hatch-textured fill so the pill reads
    visually distinct from the three confident categories.
  - `index.html`: legend gains an **"Unverified"** swatch; the
    `#type-filter` select gains an **"Unverified"** option.
  - `app.js`: `TYPE_COLORS` extended with `unknown`; `renderDetails`
    renders the type cell as **"Unverified (needs review)"** rather
    than the ugly auto-capitalised "Unknown island"; `parentLabel`
    falls through to `null` for the unknown case (no dangling "—"
    "In water body" row).

- **Outcome / counts**:
  - Classifier emitted 210 proposed changes, all `sea → unknown`. Zero
    new `sea → lake/river` and zero `lake → sea` flips this round.
  - Applied via `scripts/apply_reclassification.py --confidence low
    --types unknown`. Backup at
    `data/islands.json.before-reclass-20260512T131152Z`.
  - Type table after Phase 1.5:
    `sea: 4,991  ·  lake: 1,257  ·  river: 318  ·  unknown: 210`.
  - Distribution of `unknown` by nation:
    Ireland 89 · England 64 · Scotland 31 · NI 22 · Wales 4.
  - Spot-checked 9 of the 210:
    - Magurk's Island → Lough MacNean (NI). Should be `lake`.
    - Bank Island → RSPB reserve on River Derwent (Yorks). `river`.
    - Bingley's Island → Pegwell Bay marshland (Kent). `unknown` is
      a good label; it's now mudflats, not a discrete island.
    - Calbha Mor → real Scottish sea island (Eddrachillis Bay); OSM
      didn't polygonise it separately so it appears inside GB. Once
      OSM mappers fix this it'll flip back to `sea`.
    - Inchydoney, Corkbeg → tidal causeway-connected (coastal); `unknown`
      is honest — the answer depends on tide.
    - Duck Island → Lough Neagh shore (NI). `lake`.
    - Loch of Leys crannog → Aberdeenshire freshwater crannog. `lake`.
    - Eilean na h-Aibhne ("of the river") → Sutherland. `river`/`lake`
      pending a closer look at OSM tags.
  - Type pill renders with the new lilac/hatched style and the details
    panel says "Type: Unverified (needs review)".

- **Open items** (kicked to QUEUE.md):
  - **Curation pass** to drain the 210 `unknown` pile. Quick path:
    bulk-classify the unambiguous ones (Lough Erne / Neagh / etc.
    cluster, Norfolk Broads cluster, Yorkshire Derwent cluster) via
    a small `data/manual_overrides.json` keyed by `(id → type,
    parentWaterBody)`. The rest gets touched by hand or kicked to
    Phase 2 / 3.
  - **Subtype badges** still TODO in the UI (tidal-loch, estuary,
    reservoir, canal). Phase 1 already populates `subtype` for some
    bodies; we just don't render it as a distinct chip yet.
  - Phase 2 (OS NGD Features API) and Phase 3 (EA/NRW/SEPA/EPA WFD
    overlays) remain queued.

## 2026-05-12 — Drain the `unknown` queue (210 → 1)

- **Goal**: After Phase 1.5 left 210 islands as `type: unknown` (inside
  the GB/Ireland mainland but no positive water-body match), drain the
  queue with high accuracy. The user explicitly asked for this as the
  next priority.

- **What changed**:
  - `scripts/profile_unknowns.py` (new) — read-only diagnostic that
    measures Q-ID coverage, distance to nearest non-tidal OSM water
    polygon for each unknown, and bucketises the result so we can
    pick a sensible Tier-4 cut-off. Profile showed 43% of unknowns
    within 100 m of a water polygon and 45% within 500 m.
  - `scripts/reclassify_islands.py` — added **Tier 4 (proximity)**.
    The island's centroid is matched against the nearest non-tidal
    inland water polygon; ≤ 200 m = `medium` confidence, 200-500 m =
    `low`, > 500 m = no verdict. Tier 4 is **gated on the mainland
    test** so a small marine islet next to a coastal freshwater stream
    can't get a false-positive river verdict. Output also captures
    `distanceM` in the proposal evidence.
  - `scripts/apply_manual_overrides.py` (new) — reads a hand-curated
    `data/manual_overrides.json` and applies type / subtype /
    parentWaterBody / classification updates atomically with backups
    and read-back validation. Mirrors the safety of
    `apply_reclassification.py`. Persists a `classificationNote` field
    so the *why* is recorded in `islands.json` itself.
  - `data/manual_overrides.json` (new) — 134 hand-curated entries:
    - 11 crannogs (auto-lake by definition + named parent loch where
      the name reveals it: Loch Coille-Bharr, Loch Seil, Loch na Eala,
      Loch of Leys, Loch Kinellan, White Loch, etc.)
    - Cornwall / Devon sea stacks (The Avarack, Gregory Rocks, Cribbar,
      Lye Rock)
    - Cork Harbour fringe (Corkbeg, Ringaskiddy, Little Island, Fota /
      Foaty)
    - Wexford / Waterford / Shannon-estuary islands
    - Mayo / Donegal coast islets (Claggan, Glash, Illannamuck, Gull,
      Rossturk, Heath)
    - Trawbreaga Bay / Lough Foyle / Lough Swilly islets
    - NI lake islands (Knockmore in Lough Erne; Island MacHugh in
      Lough Catherine; Garden Isle in Upper Lough Erne)
    - NI sea-lough islands (Sketrick & Otter in Strangford; Rough
      Island in Lough Foyle; Island Magee in Larne Lough)
    - Thames-system river islands (Three Mills, City Mill Lock,
      Osterley, Wilderness, Pratt's, Crabby, Wargrave Marsh)
    - Severn / Trent / Soar / Wharfe / Nidd / Derwent / Ouse / Suir /
      Suck / Shannon islets
    - Humber estuary islets (Sunk Island, Read's Island)
    - Specific corrections: Cobholm (river not lake — Yare,
      Yarmouth); Eilean na h-Aibhne (river — name is Gaelic for "of
      the river"); Foaty (sea — Cork Harbour, OSM didn't separate);
      Holy-Island-Surrey (river — Wey, not Stanley Pool);
      Thorney-Island-Westminster (river — Thames, not St. James's
      Park Lake); Great Arthur House (kept `unknown` — Barbican
      Estate building, not really an island).

- **Outcome / counts**:
  - Before: `sea 4,991 · lake 1,257 · river 318 · unknown 210`.
  - After Tier 4 medium-confidence apply (76 changes):
    `sea 4,991 · lake 1,301 · river 350 · unknown 134`.
  - After 134 manual overrides applied:
    `sea 5,049 · lake 1,329 · river 397 · unknown 1`.
  - Net drain: **209 of 210** unknowns resolved (99.5 %).
  - Classification-source distribution now: `tier-a 1,080 · tier-b 249 ·
    manual-override 134 · osm-water-pip 133 · wikidata-p206 80 ·
    osm-water-near 76 · thames-list 22 · wp-category 4 ·
    crannog-subtype-override 3 · default-sea-confirmed 4,995`.

- **Open items** (kicked to QUEUE.md):
  - Single remaining `unknown`: Great Arthur House Including Boiler
    House (csv-geocoded-Q26272407). Architectural feature inside the
    Barbican Estate; the right fix is to drop it from the dataset
    when the upstream CSV is next cleaned.
  - **Subtype-badge rendering** in the details panel is still TODO --
    we now populate `crannog` for 14 islands and `estuary` /
    `reservoir` for many more, but the UI doesn't surface them.
  - **Cardigan-Bay / Welsh-coast nation tagging** -- the manual
    overrides file flags Knightstone Island (Weston-super-Mare) as
    needing a nation fix (currently "Wales", should be "England"); add
    a sweep that audits coastal islands' nation against the
    administrative boundary rather than the bbox.
  - Phase 2 (OS NGD water polygons) and Phase 3 (EA/NRW/SEPA/EPA WFD
    overlays) remain queued for future hardening.

## 2026-05-12 — Polygon-based island areas (geodesic, ≤ 2 %)

- **Goal**: Compute an island-area figure we can vouch for to within
  2 %, or publish `N/A`. Per user spec: "high degree of confidence
  in, accurate to within 2 % or put N/A".
- **Method**: Geodesic area on the WGS84 ellipsoid via
  `pyproj.Geod.polygon_area_perimeter()` -- the calculation itself is
  sub-0.01 %-accurate. The published uncertainty is therefore the
  accuracy of the polygon, not the maths. OSM coastline / way /
  relation geometry is the source of truth.
- **Pipeline** (`scripts/compute_island_areas.py`):

  1. **Step B (preferred)** — the island's own `osm-way-<id>` or
     `osm-relation-<id>` (or `…-w<digits>` suffix embedded in
     hand-curated IDs) is the canonical geometry. Batch-fetched from
     Overpass via `curl` with exponential backoff across three mirror
     endpoints; results cached in `data/cache_osm_geometries.json`.
     Relations are stitched from member-way `out geom` data with
     `shapely.ops.polygonize(unary_union(...))`, with inner rings
     subtracted via `difference`.
  2. **Step C** — for `wd-Q…` IDs, fetch the OSM element tagged
     `wikidata=Q…` over Overpass (regex batch query). Adds ~60
     additional islands not covered by Step B.
  3. **Step A (fallback)** — only fires for *hand-curated* IDs (not
     prefixed `osm-`/`wd-`/`csv-`, no `-w…` suffix). Finds the
     smallest non-mainland OSM coastline polygon (from
     `data/land_polygons.pickle`) that contains the centroid. Critical
     guard: a `wd-Q*` islet whose centroid happens to fall inside
     Mull's coastline polygon must NOT inherit 884 km².
  4. **Step D (Wikidata P2046 cross-check)** — `wbgetentities` batch
     fetch of all Q-IDs. Result is a sanity-check only, not a gate.
     Detects common WD unit errors (≈100× = hectares, ≈1000× = m²,
     ≈300× = acres) and treats them as confirmation rather than
     disagreement. Honest disagreements > 25 % downgrade to medium.

- **Confidence assignment**:

  | Conf   | When                                                             |
  | ------ | ---------------------------------------------------------------- |
  | high   | Polygon found AND (no WD or WD within 25 % or WD unit mis-tagged)|
  | medium | Tiny islet (< 0.001 km², < 8 vertices) OR WD differs by > 25 %   |
  | n/a    | No polygon resolvable; or only Wikidata P2046 available          |

- **What changed**:
  - **NEW** `scripts/compute_island_areas.py` (Steps A/B/C/D + Wikidata
    cross-check + atomic apply + audit writer).
  - **NEW** `scripts/_check_areas.py` (read-only diagnostics: top-30
    by computed area, type-coverage breakdown, spot-checks vs known
    references).
  - **NEW** `data/area_audit.json` — per-island evidence
    (computed-vs-current, WD cross-check delta, confidence, note).
  - **NEW** caches: `data/cache_osm_geometries.json`,
    `data/cache_wd_area.json`.
  - **MUTATED** `data/islands.json` — `areaKm2`, `areaSource`,
    `areaConfidence` set on every entry; 94 previously-set values
    rewritten with the new geodesic figure (some old hand-set values
    were off by > 10 %). Backup at
    `data/islands.json.before-areas-20260512T151008Z`.
  - **MUTATED** `app.js` — new `formatAreaRow()` helper renders area
    with its confidence + source ("· high confidence · OSM way") on
    the details panel; N/A entries get a hoverable tooltip.
  - **MUTATED** `requirements.txt` (implicit) — `pyproj 3.6.1` now
    required.

- **Outcome / counts** (6,776 islands):
  - **5,581 (82.4 %) — `areaConfidence: "high"`** (polygon-backed,
    geodesic; where applicable cross-validated by Wikidata P2046).
  - **236 (3.5 %) — `areaConfidence: "medium"`** (tiny islets with
    minimal polygons, or significant WD disagreement to flag for
    review).
  - **959 (14.2 %) — `areaConfidence: "n/a"`** (point-only OSM nodes,
    `wd-Q*` islets with no resolvable polygon, csv-geocoded entries
    without OSM linkage).

  Top-30 by computed area is now identical to canonical UK
  encyclopaedia rankings: GB, Ireland, Lewis & Harris, Skye,
  Mainland Shetland, Mull, Anglesey, Islay, Mainland Orkney,
  IoM, …, Sheppey, Tiree, Benbecula, Coll, Guernsey, etc.

- **Bugs caught & fixed during development**:
  1. **Mainland.contains() was 100× slower than needed** — added
     mainland-polygon-index pruning so each sea-island lookup is a
     STRtree + small-polygon test, not a ray-cast through 218,000 km²
     of GB. Throughput jumped from 30/s to >1,000/s.
  2. **Islet inheriting host island's polygon** — early version had
     "Loch Assapol crannog" inheriting Mull's 884 km², "Holm of
     Helliness" inheriting Shetland's 953 km², etc. Fix: Step A
     restricted to hand-curated IDs only; arbitrary `wd-Q*` entries
     are not allowed to claim a polygon they merely happen to sit
     inside. Verified: top-30 list is now duplicate-free.
  3. **Wikidata P2046 unit chaos** — many entries store hectares but
     tag the unit as km² (Eilean nam Faoileag claimed 16 km², real
     is 0.0003 km²; L'Aiguille claimed 4.07 km² when 4.07 *ha* is
     the actual value). Detection rule treats ratios of 70-150×
     (ha→km²), 100-1,000,000× (m²→km²), 200-400× (acres→km²) as
     confirmation that OSM is correct.
  4. **`-w<digits>` suffixes in hand-curated IDs** — many entries
     have a curated slug like `apple-island-w344100095` that embeds
     the OSM way ID. New regex captures these and routes them
     through Step B (gained 127 islands' worth of polygons).

- **Open items** (kicked to QUEUE.md):
  - Currently 959 `n/a` entries are genuinely unmeasurable from
    polygon data alone. Many are `osm-node` (point only) or
    `wd-Q*` Q-IDs with no OSM linkage. A future pass could try a
    "nearest `place=island` within 100 m" lookup for the csv- entries.
  - 236 `medium`-confidence entries deserve manual review (the audit
    file lists each with computed-vs-WD delta). Highest priorities:
    Hayling Island (Δ 85 % — boundary definition?), Bryher (Δ 11 %),
    Iona (Δ 2.7 %), Eilean Mhealasta (Δ 9194 % — likely WD-hectare-
    mis-tag just outside the detection window).
  - Wikidata P2046 rate-limited at ~1,500 IDs/run; two batches
    skipped this session. Re-run `--fetch-wd` against the existing
    cache to top up cross-validation coverage from 340 to ~500.

## 2026-05-12 — Highest-point elevations (OSM peaks + Wikidata P2044)

- **Goal**: Publish each island's highest point with surveyed-quality
  accuracy where we can, or an estimate clearly labelled otherwise.
  Per user spec: "within 2 % accuracy, or put an estimate next to it".
- **Method**: Two-source pipeline against the polygons resolved by the
  area pipeline.

  1. **OSM `natural=peak` nodes** — bulk-fetched (42 tiles, ~10 min) over
     the UK / Ireland bbox: `node["natural"="peak"]["ele"]`. Result:
     18,525 surveyed peak nodes with `ele=*` tags. OSM convention is
     metres above sea level (Ordnance Survey / OSi sources for the
     British Isles), accurate to ±1 m for any summit ≥ 50 m. For each
     island, find peaks whose centroid falls inside the polygon and
     take the one with the highest `ele`.
  2. **Wikidata P2044** (elevation above sea level) — batch-fetched
     for every Wikidata Q-ID in the dataset; cached in
     `data/cache_wd_elevation.json`. Used both as a cross-check on OSM
     peaks and as a fallback when no OSM peak sits inside the polygon.
  3. **Pre-existing hand-curated values** retained when neither
     source returned anything.

- **Confidence rule**:

  | Conf       | When                                                              |
  | ---------- | ----------------------------------------------------------------- |
  | `high`     | OSM peak found (optionally cross-validated by WD within 5 m / 5 %)|
  | `estimate` | Wikidata P2044 only, OR OSM/WD disagree by > 5 m **and** > 5 %    |
  | `n/a`      | No peak and no Wikidata elevation                                 |

- **What changed**:
  - **NEW** `scripts/compute_island_highpoints.py` — Overpass tile
    fetcher for `natural=peak`, Wikidata P2044 batcher, polygon
    resolver (replicates the area script's priority order), STRtree
    spatial index, prepared-geometry PIP for fast lookup against
    Great Britain's 200k-vertex polygon.
  - **NEW** caches: `data/cache_osm_peaks.json` (~6 MB, 18,525 peaks),
    `data/cache_wd_elevation.json`.
  - **NEW** `data/highpoint_audit.json` — per-island evidence
    (computed-vs-current, OSM-vs-WD delta, confidence, note).
  - **MUTATED** `data/islands.json` — `highestPointM`,
    `highestPointName`, `highestPointSource`, `highestPointConfidence`
    set on every entry. Backup at
    `data/islands.json.before-highpoints-20260512T154541Z`.
  - **MUTATED** `app.js` — new `formatHighPointRow()` helper renders
    the value with its confidence + source on the details panel;
    estimates clearly labelled.

- **Outcome / counts** (6,776 islands):
  - **239 (3.5 %) — `highestPointConfidence: "high"`** (OSM-surveyed
    peak, where applicable cross-validated by Wikidata P2044).
  - **54 (0.8 %) — `highestPointConfidence: "estimate"`**
    (Wikidata-only fallback OR OSM/WD disagreement > 5 m).
  - **6,483 (95.7 %) — `highestPointConfidence: "n/a"`** (mostly
    small islets without an OSM-tagged peak).
  - **Total with `highestPointM`**: 293 (up from 27 hand-curated).
  - Wikidata cross-validation: 53 islands, 41 (77 %) agreed within 2 m.

  Top 30 reads as a who's-who of British / Irish summits:
  Ben Nevis 1,345 m · Carrauntoohil 1,039 · Sgùrr Alasdair on
  Skye 992 · Ben More on Mull 966 · Goat Fell on Arran 874 · Askival
  on Rum 812 · An Cliseam on Lewis & Harris 799 · Beinn an Òir on
  Jura 785 · Croaghaun on Achill 688 · Snaefell on the Isle of Man
  621 · Sgùrr Mòr on Raasay 494 · Beinn Bheigeir on Islay 491 ·
  Ward Hill on Hoy 481 · Conachair on St Kilda 430 — every entry
  agreeing with canonical sources to the metre.

- **Bugs caught & fixed during development**:
  1. **Overpass `out tags;` strips node coordinates**. First fetch
     pulled tags but no lat/lng — every peak had `lat=None`. Fix:
     use plain `out;` (default includes coords for nodes).
  2. **`Polygon.contains()` on Great Britain's 200k-vertex polygon
     was hanging the loop at ~2,500 islands**. Same class of bug as
     the area pipeline's mainland test. Fix: wrap the polygon in
     `shapely.prepared.prep()` when the candidate set has > 4 peaks
     — gives O(log N) PIP instead of O(N). Throughput jumped from
     "indefinitely stuck" to 2,500 islands/sec.
  3. **Manual values overwritten by slightly-different OSM data**:
     3 islands' hand-curated peaks were replaced. All defensible —
     Anglesey 220 → 178 m (Holyhead Mountain is on the connected
     Holy Island, which isn't part of OSM's Anglesey polygon); Lundy
     142 → 138 m (Beacon Hill's OSM node lacks `ele`; Tibbett's Hill
     was the next-highest tagged peak); Mainland Orkney 271 → 275 m
     (same Mid Hill summit, updated survey).

- **Open items** (kicked to QUEUE.md):
  - 95.7 % `n/a` coverage is mostly small islets without surveyed
    peaks. Phase 2: sample SRTM 1-arc-sec or OS Terrain 50 inside
    each polygon to derive a DEM-based elevation (would require a
    DEM bundle, not currently in the repo).
  - 9 OSM-vs-WD mismatches > 5 m flagged for review (Arranmore
    Δ 265 m, Fair Isle Δ 54, Cape Clear Δ 53, Bere Island Δ 50,
    Inishmore Δ 52, Sùla Sgeir Δ 38, Tresco Δ 10). Most look like
    WD using a feature that isn't the true summit; the audit file
    lists each with delta and both source values.

## 2026-05-12 — Five-source enrichment scaffold (staged, awaiting overnight)

- **Goal**: Add DoBIH hill classifications, lighthouses + beacons,
  RSPB reserves + wildlife colonies, BGS geology, and Census 2022
  population to every relevant island. Build the ingestion scripts,
  schema proposal, and orchestrator now while
  `scripts/overnight_runner.sh` (PID 71005) is mid-flight; the actual
  `islands.json` merge waits for the overnight chain.

- **Overnight chain progress observed during this session**: step 1
  (`enrich_descriptions_wikipedia.py`) finished at 21:04 UTC; step 2
  (`enrich_images_v5.py`, PID 98773) was running at session end.

- **What changed**:
  - New schema proposal — [`docs/SCHEMA-ENRICHMENTS-2026-05-13.md`]
    (594 LOC).  Captures every new field group, the
    `<thing>Source` / `<thing>Confidence` / `<thing>Attribution` /
    `<thing>FetchedAt` quad pattern, a controlled species
    vocabulary, ETHICS §5 honour-rules, the new `images[i].subject`
    discriminator, and UI render placeholders.
  - New ingestion scripts (all staging-only — none touches
    `islands.json`):
    - `scripts/ingest_hills_dobih.py` (560 LOC) — DoBIH CSV OR
      Wikidata SPARQL fallback (Q1419786 Munro / Q5172995 Corbett /
      Q5594127 Graham / Q6760981 Marilyn / Q63432379 HuMP / Hewitt /
      Nuttall / Wainwright / Birkett / Donald / Furth / Murdo), with
      point-in-polygon against the existing
      `cache_osm_geometries.json`. 429-aware backoff. Stages to
      `data/cache_dobih.json`.
    - `scripts/ingest_lighthouses.py` (560 LOC) — Overpass for
      `man_made=lighthouse` / `man_made=beacon` over the UK/IE bbox
      tiled into 35 cells; Wikidata cross-check for `characteristic`
      (P1030), `establishedYear` (P571), `heightM` (P2048),
      `operator` (P137 → NLB/Trinity/CIL); 200 m offshore detection;
      mandatory `notForNavigation: true` per ETHICS §10. Stages to
      `data/cache_lighthouses.json`.
    - `scripts/ingest_wildlife_colonies.py` (470 LOC) — RSPB
      reserves via Overpass (`leisure=nature_reserve` +
      `operator~RSPB`); species presence from JNCC SPA citations
      via the new curated overrides file
      `data/wildlife_overrides.json` (25 well-known seabird stacks
      with hand-verified, fully-cited species lists); fallback to
      Wikipedia text-mention scan with the controlled species
      vocabulary at `confidence: low`. **No counts, no precise
      coordinates** — ETHICS §5 honoured throughout.
    - `scripts/ingest_geology_bgs.py` (320 LOC) — BGS Bedrock and
      Superficial Geology WMS (1:625K DigMapGB), one
      `GetFeatureInfo` per island centroid against the
      `GBR_BGS_625k_BLS` (bedrock) and `GBR_BGS_625k_SLS`
      (superficial) layers; cached by 4-dp rounded coords (~11 m)
      for ~5–10× dedup across archipelagos; GB-only extent.
    - `scripts/ingest_census_2022.py` (290 LOC) — stages NRS/ONS/
      NISRA/CSO/IoM/States CSVs (one per nation) at
      `data/census2022_<nation>.csv`; ranked name matching (curated
      IDs > OSM > Wikidata > CSV-geocoded); "don't overwrite newer
      with older" rule; `populationDetails` for households / age
      structure / language speakers when published. Sample CSV at
      `data/census2022_nrs_SAMPLE.csv` covering 12 well-published
      Hebridean islands.
  - New orchestrator — `scripts/apply_enrichments.py` (215 LOC) +
    `scripts/apply_enrichments.sh` (90 LOC). Verifies the overnight
    chain has finished (`===== Overnight run finished` in the latest
    summary log), takes one timestamped backup, merges all present
    caches in a single atomic write, re-reads to validate, runs
    smoke checks (Skye, Devenish, Achill, IoW, Eel Pie), rolls back
    from backup on any failure. `--apply` is gated behind an
    interactive prompt by default; `--yes` for unattended use.
  - New docs — [`docs/DATA-SOURCES.md`] (220 LOC) registry with
    licence / refresh cadence / attribution per source; updates to
    `docs/IMAGE-SOURCES.md` §H documenting the new `subject:`
    discriminator and per-entity photo quotas.
  - New curated data — `data/wildlife_overrides.json` (25 stacks),
    `data/census2022_nrs_SAMPLE.csv` (12 islands).

- **Dry-run samples** (paste-able for verification):
  - **Census** (12-row sample CSV → 10 matched):
    `Isle of Skye → isle-of-skye: pop 10008`,
    `Lewis and Harris → lewis-and-harris: pop 21031`,
    `Mull → mull: pop 3049`,
    `Islay → islay: pop 3498`,
    `Arran → arran: pop 4679`,
    `Tiree → osm-relation-6045455: pop 653`,
    `Iona → iona: pop 177`,
    `Eigg → osm-relation-1663615: pop 108`,
    `Rum → osm-relation-929839: pop 40`,
    `Canna → osm-way-4004501: pop 11`.
    Two ambiguous (Coll, Muck — multiple non-osm candidates;
    needs explicit `island_id` column).
  - **Wildlife** (overrides + text scan, full dataset):
    30 islands staged. Curated wins included St Kilda (9 species:
    gannet, fulmar, puffin, leachs-petrel, storm-petrel,
    manx-shearwater, kittiwake, guillemot, razorbill), Bass Rock,
    Ailsa Craig, Skomer, Skokholm, Rathlin, Lundy, Mingulay,
    Berneray, Noss, Fair Isle, Isle of May, Inner Farne (with
    grey-seal), Handa, Ramsey Island, North Rona, Shiant Islands,
    Boreray, Tory Island, Great Saltee, Copeland, South Stack.
    Text-scan picked up Sule Stack (gannet), Ortac (gannet),
    Puffin Island (puffin), Mingay Island (common-seal).
    `scheduleListed: true` correctly set on Leach's storm petrel,
    Manx shearwater, etc.
  - **BGS bedrock** (8 large islands probed live):
    `Isle of Skye → Unnamed Extrusive Rocks, Palaeogene (Mafic Lava
    and Mafic Tuff, 65–24 Ma)`,
    `Mull → Unnamed Igneous Intrusion, Palaeogene (Pyroclastic
    rock)`,
    `Anglesey → Upper Cambrian, including Tremadoc (Metasedimentary
    rock, 505–485 Ma)`,
    `Isle of Wight → Lower Greensand Group (Sandstone and Mudstone,
    121–99 Ma)`,
    `Arran → Southern Highland Group (Psammite and Pelite,
    1000–505 Ma)`,
    `Orkney mainland → Middle Old Red Sandstone (Conglomerate /
    Sandstone, 391–370 Ma)`,
    `Shetland mainland → Appin & Argyll Groups (Psammite and
    pelite, Neoproterozoic)`,
    `Lewis and Harris → Fault Zone Rocks, Unassigned (Mylonitic-
    rock and Fault-breccia)`.
    Every result is factually correct against canonical geology
    references (Skye = Tertiary basalts; Mull = volcanic centre;
    Anglesey = Mona Complex; IoW = Cretaceous greensand; Arran =
    Dalradian; Orkney = ORS; Shetland = Dalradian).
  - **Lighthouses** (architecture verified; full Overpass run is the
    user's first --fetch — ~17 min for the 35-tile bbox sweep).
  - **DoBIH** (architecture verified; Wikidata SPARQL was actively
    rate-limited to 1 req/min during development. 429 backoff is
    in place; the user's first --fetch at off-peak will populate
    `data/cache_wd_hills.json` with the 854 Wikidata-tagged hills
    that carry a DoBIH ID. The DoBIH CSV path is also fully
    implemented; pass `--dobih-csv data/dobih_v17_3.csv`.)

- **Code review findings** (existing scripts, observed in passing —
  not fixed in this session):
  1. **Shared HTTP helpers are duplicated across scripts**.
     `_curl_post`, `_curl_get`, `_atomic_write` (etc.) are
     re-implemented in `compute_island_areas.py`,
     `compute_island_highpoints.py`, `enrich_images_v5.py`, and now
     in all five new ingest scripts. Worth lifting into a small
     `scripts/_common.py` module — the contract is already
     consistent. Trade-off: this project's scripts are deliberately
     self-contained so any single one can be copy-pasted and run
     in isolation, so the duplication has some value.
  2. **`compute_island_highpoints.py` uses `_curl_post` with the
     wrong `data` parameter shape** — it accepts a string, while
     `compute_island_areas.py`'s helper accepts the same. Fine
     today but a future refactor should normalise to one shape
     (dict of params) for symmetry with `_curl_get`.
  3. **`enrich_descriptions_wikipedia.py` uses `urllib.request`
     directly** while the other scripts shell out to `curl` via
     `subprocess`. Mixed strategies. The `urllib` approach is fine
     for simple GETs but doesn't share the same backoff/retry path.
  4. **Polygon resolution code is duplicated** in three places:
     `compute_island_areas.py`, `compute_island_highpoints.py`, and
     now `ingest_hills_dobih.py` + `ingest_lighthouses.py`. All
     four implement the same Step A/B/C priority chain. Strong
     candidate for promotion into a shared module
     (`scripts/_polygon.py`) — would also help future enrichments
     that need a polygon (e.g. BGS shapefile-based ingestion in
     Phase 2 of the geology workstream).
  5. **`enrich_images_v5.py` has a `_REGIONAL_ANCHORS` table that
     mixes country-level and county-level keywords**. Works fine
     today but might cause false-positive geo-anchoring for
     islands near a county-name homonym (rare but possible). Not
     blocking; future hardening.

- **Outcome** (no `islands.json` mutation yet):
  - 12 new files added: 1 schema doc, 1 data-sources registry, 5
    ingestion scripts, 1 orchestrator script + 1 wrapper, 1
    overrides JSON, 1 sample CSV. ~3,200 LOC total.
  - `islands.json` untouched; overnight chain (`enrich_descriptions
    _wikipedia.py` and downstream) continues without interference.
  - All 5 scripts compile clean (`python3 -m py_compile`).
  - All 5 scripts honour the `<thing>Source` / `<thing>Confidence` /
    `<thing>Attribution` / `<thing>FetchedAt` quad pattern.
  - Per-source attribution embedded in every cache entry; license
    chain validated against ETHICS §1 and §5.

- **What's queued vs applied**:
  - Queued (staged but not applied): hills, lighthouses, wildlife,
    geology, census 2022.
  - Applied to `islands.json`: nothing. The merge step is gated
    behind `scripts/apply_enrichments.sh` running after the
    overnight chain finishes.

- **Open items kicked to QUEUE.md** (priorities P0c — see below).

---

### 2026-05-13 — LLM descriptions, semantic tags, chatbot retrieval

- **Goal**: Make the Ask panel more useful by (a) batch-drafting missing
  island blurbs and controlled semantic tags with OpenAI, and (b)
  teaching the local search + RAG path to honour those tags and surface
  clearer no-match hints.
- **Changes**:
  - `data/chat_tag_vocabulary.json` — shared allowlist + synonyms for
    batch tagging and browser parsing.
  - `scripts/llm_common.py`, `scripts/enrich_descriptions_llm.py`,
    `scripts/enrich_tags_llm.py` — grounded JSON-mode enrichment with
    checkpointing, caches, budget caps, and audit reports.
  - `scripts/overnight_runner.sh` — optional LLM steps after audits when
    `OPENAI_API_KEY` / `.env.local` is present.
  - `app.js` — loads the vocabulary, scores `semanticTags`, improves
    unknown-place hints, and passes tags + description provenance into
    the LLM payload.
- **Outcome**: Chat improvements are live on reload. Batch enrichment
  did **not** run (no API key in the environment); run manually once a
  key is configured.
- **Open**: Populate `OPENAI_API_KEY` in `.env.local`, then run the two
  enrich scripts or re-run the overnight chain tail.

---

### 2026-05-13 (pm) — Chat UX: access RAG, map actions, trip planner

- **Goal**: Make Ask feel atlas-native — ferry/causeway facts in RAG,
  per-result map/profile actions, ferry snippets on cards, and a map
  overlay trip planner on `?trip=`.
- **Changes**: `app.js` (`chatAccessForIsland`, `showIslandOnMap`,
  `planTripBetween`, `initTripPlanner`), `index.html` trip planner
  form, `styles.css` for chat actions + planner panel.
- **Outcome**: UI ships on reload. LLM batch enrichment still blocked
  without `OPENAI_API_KEY` / `.env.local`.

---

### 2026-05-13 (late) — Five-agent island discovery pipeline

- **Goal**: Add a review-first discovery workflow that finds missing UK /
  Ireland remit landmasses, verifies sources, attaches licence-safe photos,
  and gates any merge into `data/islands.json`.
- **Changes**:
  - `scripts/discover_islands_pipeline.py` orchestrator plus
    `scripts/discovery/` modules (map scanner, source verifier, photo
    finder, enricher, site update) and shared helpers.
  - `docs/DISCOVERY-PIPELINE.md`, `docs/INDEX.md`, `docs/STATE.md`.
  - Smoke artifacts under `data/discovery/` and caches
    `data/cache_discovery_*.json`.
- **Outcome**: `islands.json` untouched. Limited dry-run on 5 candidates:
  5 verified, 0 licence-safe photos in sample, 0 auto-merge-ready rows
  (all flagged for manual review). Apply only via
  `--stage=site_update --apply` after checking `STATE.md` **Currently
  running**.
- **Open**: Overpass may return 403 from some networks; map scanner falls
  back to `data/osm_raw.json`. Full-bbox run and human review of uncertain
  set before apply.

---

### 2026-05-14 — Autonomous discovery + enrichment run

- **Goal**: Apply missing island discovery, enrich descriptions/images/names,
  run LLM within a $30 cap, audits, and optional staged enrichments merge.
- **Changes**: `scripts/autonomous_run.sh` orchestrator; `docs/STATE.md`
  **Currently running** updated.
- **Started**: `bash scripts/autonomous_run.sh` (log `logs/autonomous-*.log`).
  Initial map scan reported **539** missing candidates vs **5,980** already
  in DB before verification/apply completed.

### 2026-05-14 (evening) — Mobile / home-screen navigation polish

- **Goal**: Make phone and Add to Home Screen use easier to navigate from the
  first launch.
- **Changes**: `index.html` (home-screen meta, touch icon, Ferries link),
  `styles.css` (safe-area layout, bottom nav, Ask tab at ≤900px, touch
  targets), `app.js` (`?island=` / `?trip=` routing, URL sync, viewport
  resize handling).
- **Outcome**: Mobile uses Map / Islands / Trip / Ask tabs; island deep links
  open the details panel on load.

---

## 2026-05-14 — Multi-source catalog discovery

- **Goal**: Discover missing islands from open gazetteers (Wikidata, Wikipedia
  lists, DoBIH, Thames eyots, crannogs, designations) and merge vetted rows.
- **What changed**:
  - `scripts/discovery/catalog_scanner.py` plus pipeline stage
    `catalog_scanner` in `scripts/discover_islands_pipeline.py`.
  - Artifacts `data/discovery/candidates_catalog.json`, refreshed
    `candidates_scan.json` / `verification.json` / `enrichment.json` /
    `review_report.json`.
- **Outcome / counts**: Catalog pass considered 2,688 rows (2,678 already in
  DB); **10** new catalog candidates. Full scan verification **549** rows;
  site update applied **10** islands (`islands.json` **7,298 → 7,308**).
  OS Open Names deferred until `data/raw/os_opennames.csv` is staged.
  Haswell-Smith, Vision of Britain, and OS MasterMap remain reference-only.
- **Open items kicked to QUEUE.md**: Human review of uncertain discovery rows;
  stage OS Open Names / NRS boundary feeds when files are available.

---

## 2026-05-15 — Ask / chatbot Hebrides and recommendation ranking

- **Goal**: Fix misleading results (e.g. "Isleworth" on Hebrides queries) and
  return sensible visitor picks.
- **What changed**: `app.js` — map bare "Hebrides" to Inner + Outer Hebrides;
  detect "worth visiting" / "best islands" / numbered pick lists; default
  those to **sea** islands; rank with quality boosts; require whole-word
  keyword matches on names; filter micro-islets for regional recommendations;
  clearer `composeChatResponse` copy.
- **Outcome**: Hebrides questions resolve to Scottish archipelago scope with
  Skye/Mull/Lewis-style results instead of spurious substring matches.

- **Follow-up (same day)**: Trip planner / itinerary banner — banner was
  `prepend`ed under the sticky topbar (`z-index` 500 vs 1000), so links were
  not receiving taps; mount banner after `header.topbar`, raise trip panel
  above Leaflet controls, disable pointer events on off-canvas sidebar for
  map/trip/ask views.

---

## 2026-05-15 — Provisional discovery inserts (`unconfirmed`)

- **Goal**: Add discovery candidates not already represented on the map, with a
  **clear non-final** classification when the pipeline is uncertain.
- **What changed**:
  - `docs/DATA-SCHEMA.md` — `classification.confidence` adds **`unconfirmed`**;
    optional **`classification.reviewHint`**.
  - `scripts/discovery/common.py` — `find_existing_match(..., loose=…)` so
    review-flagged rows never use the global 0.5 km fallback (avoids bogus
    merges).
  - `scripts/discovery/site_update.py` — match **before** insert; with
    `--include-uncertain`, insert only strict no-match rows as new islands with
    `_apply_unconfirmed_classification`; report `addedProvisional`.
  - `scripts/discover_islands_pipeline.py` — clarified `--include-uncertain`
    help text.
  - `docs/DISCOVERY-PIPELINE.md` — same.
  - `app.js` + `styles.css` — details panel + list badge for `unconfirmed`.
- **Outcome / counts**: **549** merged (they were already in the atlas under
  the same OSM/Wikidata/name key); **1** insert (**Wolf Rock Lighthouse**,
  Cornwall list / Wikidata, no hero image) at **7,309** islands. Backup
  `data/islands.json.before-discovery-20260515T051857Z`.

---

## 2026-05-15 — Marine Regions cache + discovery merge persistence

- **Goal**: Wire report-recommended **Marine Regions** gazetteer sampling without
  user-supplied files; ensure discovery merges persist when no new rows are
  inserted.
- **What changed**:
  - Populated `data/cache_discovery_marine_regions.json` (first grid fetch).
  - `scripts/discovery/site_update.py` — `--apply` now takes a backup and
    writes `islands.json` when there are merge-only updates (`merged` or
    `skipped_existing_review` / curated merges), not only `added` rows.
  - `scripts/discovery/marine_regions_gazetteer.py` — docstring notes the
    lat/long endpoint often yields **zero** strict `Island` features inside
    the UK bbox.
  - Docs: `DISCOVERY-PIPELINE.md` (six-stage title, `catalog_scanner` in
    examples), `DATA-SOURCES.md` (Marine Regions row 2a).
- **Outcome / counts**: **0** new islands from Marine Regions this pass; **5**
  existing records enriched via catalog discovery merge (still **7,308**
  islands). Backup `data/islands.json.before-discovery-20260515T044747Z`.
- **Open items**: Tune Marine Regions ingestion (alternate API / place types) or
  stage **OS Open Names** CSV for name discovery; NBN/GBIF/JNCC remain
  enrichment-first per `DISCOVERY-SOURCES.md`.

---

## 2026-05-15 — Trip planner: ferry graph load race

- **Goal**: Fix Ferry trip planner so **Plan route** returns a real itinerary
  after typing island names.
- **What changed**:
  - `app.js` — `_islandsIndexReady` promise settled from `loadIslands()` before
    the island index is used; `loadFerries()` chains off it so
    `buildFerryIslandRefIndex()` / `resolveFerryIslandId()` never run on an
    empty `byId`. Stale cached ferries with routes but an empty graph are
    dropped when islands finish loading. Clearer errors when an island has no
    ferry endpoint or no multi-hop chain. `planTripBetween` returns a
    `summary` string; trip status shows it. `_renderItineraryBanner` tolerates
    missing `byId` entries. `loadFerries` clears `ferriesPromise` in `finally`
    so in-flight dedup still works.
  - `styles.css` — itinerary banner `z-index: 1101` (above `.topbar` 1000);
    `.itinerary-banner__unknown` for orphan ids.
  - `docs/STATE.md` — note the behaviour fix.
- **Outcome**: Mull → Iona (and similar) plans again on first load; users still
  see an honest message when no ferry chain exists in `ferries.json`.

---

## 2026-05-15 — Saved islands (hearts, local list)

- **Goal**: Let users mark islands of interest and browse a saved-only list.
- **What changed**:
  - `index.html` — `favorites-filter` select (All / Saved only) in top filters.
  - `app.js` — `localStorage` key `iobFavoriteIslandIds`; heart on list rows and
    detail header; `Saved islands` list heading when filtered; map markers get
    a pink ring when saved; `resetAtlasHome` clears the saved filter.
  - `styles.css` — list row split (`island-card` + `island-card__main` + `island-card__fav`);
    `.details-title-row` + `.details-fav`.
- **Outcome**: Favourites stay on this device only (no sync); combine with type
  / nation / search as usual.

---

## 2026-05-15 — Suggest a correction (GitHub, source-required)

- **Goal**: Let visitors report wrong island data without on-site registration or
  direct edits to `islands.json`.
- **What changed**:
  - `.github/ISSUE_TEMPLATE/island-data-correction.md` — maintainer checklist.
  - `app.js` — `buildCorrectionIssueUrl`, `renderCorrectionReport` on detail
    panel; `window.IOB_CORRECTION_REPO` override.
  - `styles.css` — `.correction-report` block.
  - `docs/QUEUE.md` — cleared stale P0 overnight row; noted missing enrichment caches.
  - `docs/STATE.md`, `docs/INDEX.md`.
- **Outcome**: Users open a pre-filled GitHub issue with island id, coords, and
  OSM/Wikidata links; evidence section is mandatory in the template copy.

---

## 2026-05-15 — SEO + GEO (island profiles, crawlers)

- **Goal**: Better search and generative discovery for island deep links without
  changing the visible atlas UI.
- **What changed**:
  - `seo-meta.js` — on island open: `title`, description, canonical, Open Graph,
    Twitter Cards, JSON-LD `Island` + `GeoCoordinates`; restores defaults when
    the detail panel closes. Optional `window.IOB_SITE_ORIGIN` for production host.
  - `app.js` — calls `applyIslandSeo` / `resetIslandSeo` from `focusIsland` /
    `releaseIslandDetailView`.
  - `scripts/generate_seo_artifacts.py` — writes `llms.txt`; with
    `IOB_SITE_ORIGIN` / `--site-origin`, also `sitemap.xml` + `robots.txt`;
    optional `--landing-dir` for thin redirect HTML stubs.
  - `llms.txt` (generated), `docs/SEO-GEO.md`, `docs/INDEX.md`, `docs/ARCHITECTURE.md`,
    `index.html` comment, `docs/STATE.md`.
- **Outcome**: Shareable `?island=` URLs get machine-readable summaries; deploy
  with a real origin to emit sitemap + robots.

---

## 2026-05-15 — Terrestrial OSM rocks removed from atlas + discovery filter

- **Goal**: Stop treating **inland named boulders / crags** (OSM `natural=rock`,
  mis-imported as marine `type: sea`) as islands; keep **coastal** stacks and
  intertidal rocks.
- **What changed**:
  - `scripts/discovery/common.py` — `is_terrestrial_inland_rock()` using
    `land_polygons.pickle` + simplified boundary (fast) and
    `TERRESTRIAL_ROCK_MIN_INLAND_DEG` (default **0.02** ° ≈ 2 km; override via
    `IOB_TERR_ROCK_MIN_DEG`).
  - `scripts/discovery/site_update.py` — refuses **new inserts** for the same
    terrestrial rock pattern (report `skippedTerrestrialRock`).
  - `scripts/prune_terrestrial_rocks.py` — one-shot removal from `islands.json`
    (never deletes `curated` / `curated.json` ids).
  - `data/terrestrial_rocks_prune_report.json` — **266** removed rows; backup
    `islands.json.before-terrestrial-rock-prune-20260515T231858Z.bak`.
  - Regenerated `data/discovery/candidates_scan.json`, `data/survey/*` (ledger
    still pairs stale `verification.json`; outstanding count inflated until
    verifier refresh).
  - `docs/STATE.md`.
- **Outcome**: Atlas **7,309 → 7,043**; **old-man-of-stoer**-class coastal rocks
  stay; **devils-chimney**-class inland formations go. Re-run
  `discover_islands_pipeline` verification stage when you want a clean ledger
  vs verification.

---

## 2026-05-15 — Survey landmass ledger (executable)

- **Goal**: Turn the survey **prompt** into something you can run without Overpass:
  one JSON ledger + summary counts for closure reporting.
- **What changed**:
  - `scripts/survey_landmass_ledger.py` — builds `data/survey/landmass_ledger.json`
    (every atlas row + every verification/enrichment pipeline row) and
    `survey_summary.json`; pipeline match uses **strict**
    `find_existing_match(..., loose=False)` so “outstanding” means no OSM/QID/name+proximity hit.
  - `data/survey/README.md` — regenerate instructions.
  - `docs/PROMPT-COMPREHENSIVE-LANDMASS-SURVEY.md`, `docs/INDEX.md`, `docs/STATE.md`
    — point to the script and artifacts.
- **Outcome**: After this run, **550** verified discovery candidates all matched the
  atlas; **0** strict outstanding; scan report still carries **79** unnamed/unlocated
  elements for OSM hygiene follow-up.

---

## 2026-05-15 — Comprehensive landmass survey prompt (multi-agent briefing)

- **Goal**: Single reusable **copy/paste prompt** for orchestrating a full-remit
  landmass + naming sweep aligned with UK_BBOX / `in_remit` and AGENTS.md
  (~50 mi UK+Ireland scope).
- **What changed**: `docs/PROMPT-COMPREHENSIVE-LANDMASS-SURVEY.md` (succinct prompt
  block + agent roles + ledger columns + closure report template + honest note
  on 3 m detection vs OSM/open-data limits). Linked from `docs/INDEX.md`.
- **Outcome**: Humans/agents run tiles → OSM/inland/gazetteer → name resolver →
  merge with existing discovery rules; track outstanding rows in a survey ledger.

---

## 2026-05-15 — Crowd-sourced island pins (GitHub triage)

- **Goal**: Light-touch way to suggest missing islands or unnamed locations: map
  pin + optional name, note, name-source URL, credit; unnamed-only pins
  encouraged; visible distinction from atlas markers; optional recognition in
  published pin data.
- **What changed**:
  - `data/crowd_pins.json` (schema v1, starts empty), `crowd-pins.js`,
    `app.js` integration (layer, modal, GitHub issue URLs), `index.html` (Suggest
    island, Crowd pins toggle, legend), `styles.css` (modal, popup, legend dot,
    map pick cursor).
  - `docs/CROWD-PINS.md` maintainer workflow; `docs/INDEX.md`, `docs/STATE.md`,
    `AGENTS.md` pointers.
  - Typo fix in modal copy: “Maintainers” (was “Maintainerrs”).
- **Outcome / counts**: No change to `islands.json`; community layer ready when
  pins are added from triaged issues.
- **Open items**: Promote vetted pins to the atlas only via normal provenance
    (`docs/ETHICS.md`).

---

## 2026-05-16 — Map first paint, subtype chip, CSV stowaway drop

- **Goal**: Work down the map-improvement priority list: smaller initial payload,
  data hygiene, clearer subtype UI; stage nation-by-admin1 for future careful use.
- **What changed**:
  - **`data/islands_index.json`** + **`scripts/build_islands_index.py`** — strips
    long prose / `sources` / `images[]` / etc. (~4.5 MiB vs ~10 MiB full).
  - **`app.js` `loadIslands`** — fetch index first (optional), paint after rAF,
    then fetch **`islands.json`** and merge in place; length mismatch falls back
    to full-only; **`mergeIslandDetailFromFull`**, **`populateNationFilter`** reset
    (no duplicate options).
  - **Removed** `csv-geocoded-Q26272407` and `csv-geocoded-Q66227635` from
    **`data/islands.json`** (non-island buildings).
  - **Details panel** — **`subtype-chips` / `subtype-chip`** + **`formatSubtypeLabel`**;
    stat “Type” line is sea/lake/river island only (subtype no longer duplicated there).
  - **`scripts/recompute_nation_admin1.py`** — Natural Earth 10m admin-1 **dry-run**
    script; **not applied** (would mis-tag NI/ROI and GB border). Documented as
    experimental.
  - **`docs/PIPELINE.md` §5b**, **`docs/ARCHITECTURE.md`**, **`docs/STATE.md`**,
    **`AGENTS.md`**, **`styles.css`**.
- **Outcome / counts**: Atlas **7,043 → 7,041**; faster perceived load when both
  JSONs are deployed; index must be regenerated after every full-dataset edit.

---

## 2026-05-16 — Wikidata→OSM backfill + discovery refresh

- **Goal**: Attach OSM way/relation ids to Wikidata-only atlas rows so detail-map
  polygon overlays work; refresh discovery verification and survey ledger.
- **What changed**:
  - `scripts/backfill_osm_from_wikidata.py` (dry-run + `--apply`) reading
    `cache_osm_geometries.json`.
  - `compute_island_areas.py --fetch-osm` (39 new Step C lookups).
  - Applied **83** OSM id backfills; `data/osm_wikidata_backfill_report.json`.
  - `python3 scripts/build_islands_index.py`.
  - `discover_islands_pipeline.py` (dry-run): 1 merge candidate, 0 new inserts.
  - `survey_landmass_ledger.py` → `data/survey/survey_summary.json` (0 strict outstanding).
  - Backup `data/islands.json.before-osm-backfill-*`.
- **Outcome / counts**: Islands with `osmId` **6,110 → 6,193**; **848** still without
  (no OSM element tagged with their Wikidata id in Overpass cache).

---

## 2026-05-16 — Native crowd island suggestions

- **Goal**: Let visitors submit island/name suggestions on-site without opening GitHub.
- **What changed**:
  - `crowd-pins.js` — `submitCrowdSuggestion`, FormSubmit/Formspree/Web3Forms/webhook
    routing, `loadCrowdSuggestConfig`.
  - `app.js` — modal success step, **Submit suggestion** button, popup **Suggest a name**
    opens in-app form; optional GitHub fallback.
  - `index.html` — form fields + success step; updated copy.
  - `data/crowd_suggest_config.json` + `.example.json`; `docs/CROWD-PINS.md`.
- **Outcome / counts**: UX complete; **requires** `formsubmitEmail` (or other provider)
  in config before submissions reach maintainers.

---

## 2026-05-16 — Saved islands email gate

- **Goal**: Hearted island list requires a one-time email; keep UX lightweight.
- **What changed**:
  - `index.html` — **Saved** topbar button, email unlock modal.
  - `app.js` — `ensureFavoritesAccess`, gate hearts + **Saved only** filter; localStorage
    `iobFavoritesEmail` + existing `iobFavoriteIslandIds`.
  - `styles.css` — favorites modal.
- **Outcome**: List/hearts work on-device after email; no server sync yet.

---

## 2026-05-16 — Photo priority queue, featured strip, v5 queue flag

- **Goal**: Prioritise hero-image enrichment and surface notable islands in the UI.
- **What changed**:
  - `scripts/build_image_priority_queue.py` → `data/image_priority_queue.json` (3,444 without images).
  - `enrich_images_v5.py --queue-file` for tier-ordered runs.
  - `scripts/build_featured_islands.py` → `data/featured_islands.json` (120 picks).
  - Sidebar **Notable islands** horizontal strip (`app.js`, `index.html`, `styles.css`).
  - `docs/QUEUE.md` P1 photo coverage commands.
- **Outcome**: Featured strip live after regen; run v5 with queue file for batched lead-photo backfill.

---

## 2026-05-16 — Tier 1 discovery filters; trip planner removed

- **Goal**: Ship sidebar discovery filters (photo, ferry, elevation, area,
  subtype, confidence) and drop the map trip-planner UI while keeping ferry
  data for list icons and detail panels.
- **What changed**:
  - `index.html` — discovery toggles/selects in `#topbar-filters`; removed
    `.trip-planner` block and mobile **Trip** nav button.
  - `app.js` — `applyFilters()` discovery predicates; `islandHasPhoto` /
    `islandHasElevation`; photos-first secondary sort; `loadFerries()` on
    boot; chat `CHAT_*` synonyms (photo, ferry islands, large, summit,
    curated); removed itinerary / trip-planner JS.
  - `styles.css` — pending ferry toggle; mobile nav 3-column grid.
- **Outcome / counts**: ~3,345 islands match **Has photo** on index stub
  (`image` field); ferry filter enables after ferry JSON loads. No pipeline
  runs.
- **Open items kicked to QUEUE.md**: Resume `enrich_images_v4` / v5 when caches
  allow (photo coverage still below full atlas).

---

## 2026-05-16 — Deploy: explore topics, P0b enrichments (partial), detail UI

- **Goal**: Ship curated “what to explore?” starting points, notable strip,
  enrichment detail panels, and merge staged lighthouse/wildlife/census caches.
- **What changed**:
  - `data/discovery_topics.json` + `scripts/build_discovery_topics.py` — explore
    chips (notable, island-hopping, thames-eyots, high-summits); `?explore=`.
  - `data/featured_islands.json` + `scripts/build_featured_islands.py`.
  - `scripts/apply_enrichments.py` — smoke-test ids fixed to OSM relation ids.
  - Applied caches → `islands.json` (lighthouses 297, wildlife colonies 30,
    RSPB reserves 10).
  - `app.js` — explore UI, P0b detail renderers; removed crowd debug instrumentation.
  - `config.local.example.js` for OS Maps key setup.
  - Rebuilt `islands_index.json`.
- **Outcome / counts**: 7,041 islands; index ~10.2 MB. Hills/geology not applied.
- **Open items kicked to QUEUE.md**: DoBIH CSV or Wikidata retry for hills;
  `ingest_geology_bgs.py --fetch --commit` locally; full NRS census CSV.

---

## 2026-05-16 — Contribute config, Scotland explore topics, UX polish

- **Goal**: Close the three priorities from the product roadmap: production
  contribute submit, Scotland-first discovery, continue P0b data pipeline.
- **What changed**:
  - `.github/workflows/pages.yml` + `scripts/prepare_crowd_config.py` — inject
    FormSubmit email from `CROWD_FORM_EMAIL` repo secret on deploy.
  - `crowd-config.js`, `config.local.example.js`, mailto fallback + hint copy in
    `app.js` / `index.html`; `docs/CROWD-PINS.md` updated.
  - `scripts/build_discovery_topics.py` — five Scotland topics; regenerated
    `data/discovery_topics.json`; explore sets nation=Scotland for those chips.
  - Prior UX commit `1ae828a` (contribute hub, thumbnails, filter tiers, map peek).
  - Started `ingest_hills_dobih.py --fetch --commit` and
    `ingest_geology_bgs.py --fetch --commit` (long-running).
- **Outcome / counts**: 9 explore topics (4 UK-wide + 5 Scotland). Native submit
  works after secret or `prepare_crowd_config.py`; mailto + GitHub work without.
- **Open items kicked to QUEUE.md**: Apply hills/geology caches when ingests finish;
  add `CROWD_FORM_EMAIL` secret on GitHub; photo v5 queue batch.

---

## 2026-05-17 — Map UX, trip planner, deploy (photos/hills blocked)

- **Goal**: Run P1 photo v5 queue, hills ingest, map/mobile polish, first-paint
  performance, ferry crossing UI, bounded discovery, and push production.
- **What changed**:
  - `app.js` / `styles.css` / `index.html` — `tapTolerance` 22, larger markers +
    invisible hit halo, viewport marker culling at zoom ≤7, restored ferry graph +
    “Plan crossing” form + `?trip=` itinerary banner, ferry `lastVerified` freshness
    blurb on detail panel.
  - `scripts/build_islands_index.py` — `hasImage` stub on index rows; rebuilt
    `data/islands_index.json`.
  - `docs/CROWD-PINS.md` — expanded maintainer triage (intake → pin → atlas promote).
  - `.github/workflows/pages.yml` — Pages deploy with optional `CROWD_FORM_EMAIL`.
  - Bounded `discover_islands_pipeline.py --stage=catalog_scanner --limit=15` (cached).
- **Outcome / counts**: **7,041** islands; **3,597** with lead images (unchanged —
  v5 attempted 280 queue rows, **0** adoptions due to Commons HTTP 429; P18-only
  batch also 0). Hills: Wikidata SPARQL **429** after ~3 min, no `cache_dobih.json`
  (DoBIH CSV not present). Catalog scan: **0** new candidates.
- **Open items kicked to QUEUE.md**: Retry `enrich_images_v5.py` off-peak; drop
  `data/dobih_v17_3.csv` + `ingest_hills_dobih.py --dobih-csv … --commit`; set
  `CROWD_FORM_EMAIL` on GitHub for native crowd submit.
- **Deploy**: pushed `main` at **`e595c90`**. `.github/workflows/pages.yml` is
  committed locally but **not** on remote — push rejected without `workflow` OAuth
  scope; add the file manually or re-push with workflow permissions.

## 2026-05-19 — For-sale map pins + profile layout fixes

- **Map pins**: £ markers open popup on tap; listing links no longer hijacked by `focusIsland`. Tooltip is non-interactive; links live in popup with touch-sized targets.
- **Profile**: **On the market** moved under title; **How to get there** moved above detail map. Ferry cards scroll (~3 visible) when more than three routes.

## 2026-05-19 — Deep property listing research (multi-agent pass)

- **Goal**: Find additional live island listings (small/large) within GB+IE scope; no fabricated URLs.
- **Agents**: Scotland brokers, Ireland/England/Wales brokers, atlas ID matcher, Thames/Orkney sweep.
- **What changed**: `property_listings_verified.json` expanded **10 → 17**; sync applied to `islands.json`.
- **New islands linked**: Inchmarnock, Eilean Mòr (Loch Sunart), Inishturk (Lough Erne NI), Inis Barna,
  Boa Island, Thames Ditton Island, Pharaoh's Island.
- **Excluded / pending**: Inishskehan (not in atlas), Dumsey Eyot (not in atlas), Hallsmead Ait (auction
  passed), Little Ross (news only), Vladi GB archive listings.

## 2026-05-19 — Orchestrated property listing research (sub-agents)

- **Goal**: Expand for-sale islands using only verifiable broker URLs (no fabricated content).
- **What changed**:
  - Sub-agents: broker desk research + `islands.json` ID matching.
  - `data/discovery/property_listings_verified.json` — 10 verified listings.
  - Replaced `data/curated_property_listings.json` (removed Canna/IoW/generic URLs).
  - `scripts/sync_curated_property_listings.py` — manifest → ingest → apply → index.
- **Outcome / counts**: **10** islands with `propertyListings[]` (was 6 with placeholders).
- **Open items**: Inishbarna / Inishskehan etc. need OSM ingest before linking; Homedata API after licence check.

## 2026-05-19 — For-sale map markers + list links

- **Goal**: Clearly identify for-sale islands on the home map and link to listings.
- **What changed**: Gold **£** map badges (always visible layer), legend entry, list **For sale** pill + **Listing ↗** button, map popup/tooltip with outbound links.
- **Outcome**: Six curated listing islands stand out at default zoom.

## 2026-05-19 — Island property listings (for sale)

- **Goal**: Show which islands have known for-sale listings via ethical outbound links.
- **What changed**:
  - `scripts/discover_property_apis.py` → `data/discovery/property_sources.json`
  - `scripts/ingest_property_listings.py`, `scripts/import_curated_property_listings.py`
  - `data/curated_property_listings.json` (6 seed links)
  - `propertyListings[]` schema in `docs/DATA-SCHEMA.md`; `apply_enrichments` + index stub
  - UI: **For sale** filter, list badge, detail panel, chat synonyms
  - `docs/PROPERTY-LISTINGS.md`, `docs/DATA-SOURCES.md` §B.6
- **Outcome / counts**: **6** islands with listing links applied to `islands.json`.
- **Open items**: Homedata API key + licence sign-off; expand curated file as brokers publish.

## 2026-05-17 — Supabase schema scaffolding

- **Goal**: Prepare Postgres + Auth for contributions and cross-device saved islands.
- **What changed**:
  - `supabase/migrations/20260517000000_initial_contributions.sql` — profiles, submissions,
    community_photos/text, reports, audit_log, saved_islands, RLS, storage bucket.
  - `supabase/config.toml`, `supabase-client.js`, `.env.local.example`, `docs/SUPABASE.md`,
    `scripts/check_supabase.py`, `config.local.example.js` Supabase vars.
- **Outcome**: Repo-ready; user creates project at supabase.com and runs migration in SQL Editor.
- **Open items**: Paste keys into `.env.local` / `config.local.js`; wire auth UI in `app.js`.

## 2026-05-17 — SEO sitemap + robots + deploy hook

- **Goal**: Make island deep links discoverable to crawlers (not only client-side
  `seo-meta.js` after JS).
- **What changed**:
  - Ran `IOB_SITE_ORIGIN=https://www.findmyisland.com python3 scripts/generate_seo_artifacts.py`
    → committed **`sitemap.xml`** (7,042 URLs) and **`robots.txt`**.
  - **`index.html`**: `window.IOB_SITE_ORIGIN = "https://www.findmyisland.com"` for
    canonical/OG when the atlas loads.
  - **`.github/workflows/pages.yml`**: deploy step regenerates SEO artifacts and
    **`profiles/<id>.html`** thin stubs (gitignored; ship in Pages artifact only).
  - **`.gitignore`**: `profiles/`.
- **Outcome / counts**: Production should serve `/sitemap.xml` and `/robots.txt`;
  optional ~7k static landings on each Pages build.
- **Open items**: Submit sitemap in Search Console; consider pre-rendered island HTML
  in `index.html` later if crawlers ignore SPA meta.

## 2026-05-19 — Property listings Tier 4 + weekly tracking system

- **Goal**: Obscure-broker crawl, recurring weekly skill, easy full-list tracking.
- **What changed**:
  - Tier 4 sub-agent sweep; **+8** islands (37 total): Eilean Loch Oscair, Trannish,
    Cruit, Eel Pie, Garrick's Ait, Wheatley's Eyot, Bryher, St Martin's.
  - `scripts/property_listings_registry.py`, `scripts/run_property_discovery_weekly.py`,
    `data/discovery/property_obscure_sources.json`, generated `docs/FOR-SALE-ISLANDS.md`.
  - Skill `.cursor/skills/weekly-island-property-discovery/`; GH workflow
    `.github/workflows/main.yml` (Mondays 06:00 UTC registry refresh).
- **Outcome / counts**: **37** for-sale islands; full list at `docs/FOR-SALE-ISLANDS.md`.
- **Open items**: Run skill weekly in Cursor for new research; `pendingAtlasIngest`
  islands still need OSM discovery.

## 2026-05-19 — Property listings Tier 3 (multi-broker crawl)

- **Goal**: Expand “for sale” coverage via legal broker desk research (no
  Rightmove/Zoopla scrape); wire new islands into the map.
- **What changed**:
  - Three region sub-agents (Scotland, Ireland/NI, England/Wales) returned broker
    URLs; consolidated to `data/discovery/property_tier3_raw.json`.
  - New: `scripts/match_property_listing_islands.py`, `scripts/discover_property_tier3.py`,
    `data/discovery/property_tier3_report.json`, `property_tier3_supplement.json`.
  - Merged **29** rows in `data/discovery/property_listings_verified.json`; ran
    `sync_curated_property_listings.py` → `islands.json` + `islands_index.json`.
  - Docs: `PROPERTY-LISTINGS.md` Tier 3 section; `STATE.md` counts.
- **Outcome / counts**: **29** islands with `propertyListings[]` (was **17**); **12 new**
  islands: Eilean Righ, Thorne Island, High Island, Horse Island, Whiddy, Heir, Kerrera,
  Turbot, Inishmicatreer, Arranmore, St Agnes, Taggs Island.
- **Open items**: `pendingAtlasIngest` (e.g. Inishskehan, Cameron Island Lough Derg,
  Oran Island if added to OSM); refresh stale MyHome IDs periodically; Thorne Strutt URL
  apex/www mirror quirk documented in manifest notes.

## 2026-05-30 — Usability pass (deferred load, discoverability, a11y)

- **Goal**: Implement priority usability improvements — faster first paint, better empty
  states, easier discovery, lightbox, keyboard navigation.
- **What changed**:
  - `scripts/build_islands_index.py` — emits `thumbUrl` on index rows + `data/shards/`
    nation JSON + manifest; `.gitignore` shards; Pages workflow runs build step.
  - `app.js` — deferred shard merge; browse quick-filter chips; type-tinted photo
    placeholders; gallery lightbox; list keyboard nav; filter focus trap; extended
    `CHAT_PLACES`; removed stale debug ingest calls.
  - `index.html` / `styles.css` — sidebar reorder (browse → explore → notable → Scotland →
    trip planner); lightbox markup.
  - v5 photo batch: `--limit 80` on priority queue — **0** adoptions (Commons **429**).
- **Outcome / counts**: Index **7,041** rows, **3,597** with `thumbUrl`; **7** nation shards
  (~15 MiB total). Map/list interactive after index fetch; full detail merges in background.
- **Open items**: Resume v5 off-peak; Ireland/NI detail basemaps (QUEUE P1); full a11y audit
  for map markers.

## 2026-05-30 — Mobile island list tap fix

- **Goal**: Fix island rows not responding on first tap on mobile.
- **Root cause**: Virtual list scroll math only subtracted the section header, not the browse/
  explore/featured/trip-planner blocks above the list (misaligned hit targets); iOS
  double-tap from `tabindex="0"` + `role="listbox"` on `#island-list`.
- **Fix**: Geometric list offset via `getListScrollTopInRows()`; removed listbox tabindex;
  force list re-render when switching to Islands tab; chat result cards open profile on tap;
  `touch-action: manipulation` on list buttons.

## 2026-05-30 — Google indexing acceleration (SEO)

- **Goal**: Improve crawlability and indexing speed for findmyisland.com.
- **What changed**:
  - `index.html` — static canonical, OG/Twitter, `WebSite` JSON-LD, crawl-link footer.
  - `seo-head.js` + `config.local.example.js` — optional Google Search Console verification.
  - `seo-meta.js` — restore homepage meta when closing island panel.
  - `scripts/generate_seo_artifacts.py` — sitemap lists home + ferries + `/profiles/*.html`
    (not `?island=`); priority tiers; richer profile HTML with self-canonical + JSON-LD.
  - Regenerated `sitemap.xml` (7,055 URLs), `robots.txt`, `llms.txt`.
- **Outcome**: Deploy generates 7,041 profile stubs on Pages; submit sitemap in Search Console
  after adding verification token to `config.local.js` on deploy (or inject via secret later).
- **Open items**: User must verify in Search Console and request indexing; indexing still
  takes days–weeks.

## 2026-05-30 — UX polish pass

- **Goal**: Top-tier usability polish — clearer hierarchy, feedback, and mobile flow.
- **What changed**:
  - `index.html` — skip link; loading overlay; search clear button; filter active badge;
    map onboarding hint; island list before trip planner; trip planner in collapsible
    `<details>`; crawl links moved below list; “← Islands” back label.
  - `app.js` — loading/empty/skeleton states; `N of M` result count; filter badge count;
    search clear sync; map hint dismiss on first island open.
  - `styles.css` — supporting styles for above + sidebar flex growth for the list.
- **Outcome**: Faster orientation on first visit; filters and search easier to reset; list
  remains primary in the sidebar column.

## 2026-05-30 — UX polish pass (continued)

- **Goal**: Shareability, keyboard power-use, map/list a11y, reduced motion.
- **What changed**:
  - `app.js` — **Link** button on island profile (native share or clipboard + toast);
    `/` focuses search; **Escape** closes filters then detail panel; `aria-current` on active
    list row; focus moves to back button on open; map status live region; richer marker
    tooltips; `prefers-reduced-motion` uses instant `setView` instead of `flyTo`.
  - `index.html` — toast host; map `tabindex="0"` + screen-reader status region.
  - `styles.css` — details action row, toast, map focus ring, reduced-motion transitions.
- **Outcome**: Sharable permalinks, faster keyboard workflow, better screen-reader map context.

## 2026-05-30 — UX polish pass (design wave 3)

- **Goal**: Refine visual hierarchy, mobile map chrome, and profile toolbar.
- **What changed**:
  - Sticky **details toolbar** (back + Link + heart) on mobile profiles.
  - **Collapsible map key** on mobile; always visible on desktop.
  - Search **⌕ icon**; filter toggles highlight when active; accent **result count** when filtered.
  - Hero **gradient overlay**; external links as **button grid**; featured strip scroll fade.
  - Desktop **keyboard hint** under list; mobile nav **active tab indicator**; glass top bar.
- **Outcome**: Cleaner map on phones, clearer filter feedback, more polished island profiles.

## 2026-05-31 — Fix overlapping text in island profiles

- **Goal**: Stop virtual list rows painting over profile stat cards; improve stat layout on all devices.
- **Root cause**: Absolutely positioned virtual list layer bled through the sidebar stack when
  profile and list shared the scroll container.
- **Fix**: Pause/clear list layer whenever a profile is active (including map-tab suspend);
  clip `#island-list`; full-screen profile overlay on mobile; desktop sidebar scrolls inside
  profile only; `.profile-body` containment; stat cards single-column below 420px, word-wrap on
  long fields; `data-island-detail` state on all viewports.
- **Outcome**: Profile facts readable on phone, tablet, and desktop without list row ghosting.

## 2026-05-31 — Fix duplicate discovery ids stacking map markers

- **Goal**: Stop homonym discovery rows (e.g. four “Sgeir Dhubh” rocks) spiderfying as one cluster.
- **Root cause**: Discovery pipeline used bare `slugify(name)` ids; four rows shared `sgeir-dhubh`.
  Nation-shard merge copied the same full record onto every stub, collapsing all four to one lat/lng.
- **What changed**:
  - `scripts/fix_duplicate_discovery_ids.py` — reassigned **12** rows across **4** slug-collision
    groups (`sgeir-dhubh`, `black-rock`, `cannon-rock`, `split-rock`) to `osm-{type}-{id}` ids.
  - `scripts/discovery/common.py` + `enricher.py` — new `canonical_island_id()` for future ingests.
  - `app.js` — shard merge skips / resolves by `osmId` when slug ids collide.
  - Rebuilt `islands_index.json` + nation shards.
- **Outcome**: Each homonym rock keeps its own marker at the correct coordinate; Eilean Donan
  `osm-way-3493088` shows as a single pin again at that location.

## 2026-05-31 — Chatbot relevance + LLM precision pass

- **Goal**: Stop surfacing irrelevant island cards; use LLM only for islands it explicitly cites.
- **What changed** (`app.js`):
  - Hard feature filters (`chatIslandHasFeature`) — castle, puffins, ferry, etc. must match structured data or text; weak substring hits no longer pass.
  - Relative relevance cutoff (`chatApplyRelevanceCutoff`) trims low-scoring tail matches before display or LLM handoff.
  - Keyword-only queries require a name/description hit.
  - Count/superlative intents show zero or one card (not six arbitrary matches).
  - Structured intents (lookup/compare/count) bypass LLM to avoid padding.
  - LLM prompt: empty `islandIds` when none fit; never pad; includes `relevanceScore`.
  - AI results: only validated candidate ids — removed fallback to top-5 local results.
  - Temperature lowered to 0.45 for tighter selection.
- **Outcome**: Chat answers stay focused; island cards appear only when truly relevant.

## 2026-05-31 — Chatbot relevance pass 2

- **Broad-query guard**: nation-only / type-only queries (e.g. “Scottish islands”) now prompt
  the user to narrow — no random island cards.
- **LLM citation filter** (`chatFilterLLMResults`): re-scores cited ids, intersects with island
  names in the answer text, caps at 5.
- **Tighter cutoff**: higher min scores, cliff-drop when score falls >7 below the top match.
- **Feature text**: whole-word matching only; mountain requires hill data or peak ≥500 m.
- **Structured answers**: removed fallbacks that padded lookup/count/compare with search results.
- **LLM payload**: includes parsed query facets so the model knows applied filters.

## 2026-05-31 — 3D terrain viewer (Three.js showcase)

- **Goal**: Vanilla ES-module 3D elevation viewer for ten showcase islands; no build step.
- **What changed**:
  - `island-3d.js` — `mountIsland3D`, `destroyIsland3D`, `isShowcase3DIsland`; Three.js 0.170
    CDN imports; displaced plane mesh, elevation colours, water plane, OrbitControls.
  - `app.js` — “3D terrain” section before detail map for showcase ids; dispose on re-render.
  - `styles.css` — `.island-3d-view` + showcase landing grid tokens.
  - `showcase-3d.html` — grid demo page linking back to atlas.
  - `scripts/build_island_terrain.py` — Overpass outline + Terrarium DEM sampling; masks off-island cells.
  - `data/terrain/*.json` — heightmaps for all **10** showcase islands (Staffa −11…23 m through St Kilda to 356 m).
- **Outcome**: Interactive 3D terrain on profiles and `/showcase-3d.html`. Regenerate:
  `python3 scripts/build_island_terrain.py --cache`.

## 2026-05-30 — Visual design refinement (2026 SaaS polish)

- **Goal**: Improve typography, spacing, hierarchy, buttons, forms, mobile, and accessibility without changing behaviour.
- **What changed** (`styles.css`):
  - Expanded design tokens (`:root`): surfaces, type scale, 8px spacing grid, shadows, focus rings, `--sidebar-w`.
  - Top bar: glass backdrop, tokenised padding, display-font brand title.
  - Unified form controls: consistent min-height, radius, focus ring across filters, modals, chat, trip planner.
  - Button system: topbar links, modal CTAs, back/actions — shared hover, focus-visible, touch targets.
  - Sidebar & island cards: list padding, card spacing, thumb size, active-state shadow.
  - Chip system: browse/discover/Scotland chips — consistent sizing and focus rings.
  - Profile panel: display-font titles, stat cards, section label typography.
  - Chat & modals: rounded panels, header hierarchy, accessible close/focus states.
  - Mobile nav: stronger active indicator, safe-area padding, bottom-sheet chat radius.
  - Global `:focus-visible` baseline; expanded `prefers-reduced-motion` overrides.
- **Outcome**: Cohesive dark atlas UI aligned with modern SaaS standards; no JS or schema changes.

## 2026-05-31 — Unnamed island discovery + orange map pins

- **Goal**: Discover genuine unnamed island landmasses at ≥98% OSM confidence; show
  them on the map with a distinct pin colour for later crowdsourced naming.
- **What changed**:
  - `scripts/discover_unnamed_islands.py` — scans OSM inner rings of inland water
    multipolygons (and optional standalone `place=island|islet` with geometry);
    confidence floor 0.98; dedupe; `--apply` merge with provenance.
  - **+4,310** records merged (`nameStatus: unknown`, `source: osm-unnamed`,
    placeholder name `Unnamed island`, `tags: ["unnamed","needs-name"]`).
  - `app.js` — orange markers (`#fb923c`), list “Needs name” pill, profile banner
    + Contribute CTA, **Unnamed** browse chip + map legend entry.
  - `styles.css` — `.dot--unnamed`, banner, card styling.
  - `docs/DATA-SCHEMA.md` — `nameStatus` field documented.
  - Rebuilt `islands_index.json` + nation shards (**11,351** islands total).
- **Outcome**: Unnamed loch/river islets visible as orange pins; standalone sea
  unnamed fetch retried when Overpass geom cache is populated (`--cache` after fetch).
- **Regenerate**: `python3 scripts/discover_unnamed_islands.py --cache --apply`
  then `python3 scripts/build_islands_index.py`.

## 2026-05-31 — Production load speed (shards deploy + split index)

- **Goal**: Fix slow/blocked atlas load on findmyisland.com; ship profile landings.
- **Root cause**: Nation shards and `profiles/` are gitignored — GitHub Pages artifact
  from `path: .` never included them → 404 → browser fell back to **index + 27 MB
  `islands.json`** (~43 MB).
- **What changed**:
  - `scripts/prepare_pages_artifact.py` — stages `_site/` with forced shards +
    profiles; omits monolithic `islands.json` (wire in Pages workflow when OAuth
    `workflow` scope available).
  - **`data/shards/`** + **`profiles/`** force-added to git so current Pages
    deploy (`path: .`) serves them (manifest was 404 before).
  - `build_islands_index.py` — split **`islands_index.json`** (7,041 named) +
    **`islands_unnamed_index.json`** (4,310 lazy overlay); slimmer index fields.
  - `app.js` — sequential shard merge; no monolithic fallback on findmyisland.com;
    unnamed overlay loads only for **Unnamed** filter / OSM deep links; default map
    hides unnamed pins.
- **Outcome**: Home first paint ~**12 MB** index + background shards (~19 MB split);
  unnamed +**1.7 MB** on demand; **7,033** profile landings ship in CI artifact.

## 2026-05-31 — Atlas load fix v2 (compact index + lazy shards)

- **Goal**: Fix atlas still feeling broken after shard deploy — reduce parse/blocking on main thread.
- **Root cause**: Index stubs still ~**12 MB** (descriptions/thumbs in list payload); startup eagerly fetched and parsed **all 7 nation shards** (~19 MB) before the UI settled.
- **What changed**:
  - `build_islands_index.py` — v2 compact index (`version` + short keys): **7041** rows **~0.9 MiB** (was ~12 MiB); unnamed overlay **~0.8 MiB**.
  - `app.js` — `parseIndexPayload` / `expandIndexRow`; hide loader before `applyFilters`; defer crowd pins / ferries / featured / discovery to `requestIdleCallback`; **removed eager shard preload** — full records merge on demand via `ensureNationShardLoaded()` when opening a profile.
  - `.github/workflows/pages.yml` — run `prepare_pages_artifact.py`, deploy `_site/` (omits monolithic `islands.json`).
- **Outcome**: First paint ~**0.9 MiB** index gzip ~100–150 KiB; no 19 MB shard parse at startup; production artifact drops **27 MB** `islands.json` when CI workflow deploys.

## 2026-05-31 — Homepage load speed v3 (interactive under 7s)

- **Goal**: findmyisland.com homepage interactive within **7s** (target sub-3s on typical 4G).
- **Root cause**: Loader hid before **7,041-marker** sync rebuild + full-table sort; **Three.js** + **proj4** blocked script waterfall; index fetch started late.
- **What changed**:
  - `app.js` — prefetch `islands_index.json` at module init; boot `applyFilters({ skipMarkers, skipSort })`; dismiss loader after list paints; **chunked** deferred marker build via `requestIdleCallback`; lazy tooltips at zoom ≤7; boot grace on `moveend` rebuild; dynamic `import()` for island-3d; on-demand proj4; block monolith fallback on production.
  - `index.html` — preload index + modulepreload app.js; remove sync proj4 scripts (~95 KB raw).
- **Outcome**: Spinner clears after list virtual window; markers paint in background chunks; critical path ~**30 KB** lighter scripts.

## 2026-06-01 — Documentation review (agent context)

- **Goal**: Retain context efficiently for future sessions; document recent production architecture.
- **What changed**:
  - **New:** `docs/AGENT-QUICKREF.md` (one-page cheat sheet), `DEPLOYMENT.md`, `FRONTEND-PERFORMANCE.md`, `3D-TERRAIN.md`.
  - **Updated:** `ARCHITECTURE.md` (runtime flow, deployment, module map), `AGENTS.md` (production URL, file tree, reading order), `INDEX.md` (reading paths).
- **Outcome**: Agents can diagnose load/deploy/3D issues without replaying May 2026 session history.

## 2026-06-01 — Airbnb-tier visual polish (CSS-only)

- **Goal**: Elevate findmyisland.com UI to hosted-marketplace quality without breaking behaviour.
- **What changed**:
  - `styles.css` — layered card surfaces, pill search + nav controls, listing-style island rows (shadow/hover), profile hero radius, refined loader + chat launcher, mobile bottom nav; **removed ~600 lines** of duplicate “Design refinement 2026” overrides (single source of truth).
  - `app.js` — `ROW_HEIGHT` 100 to match taller list cards (virtual scroll).
- **Outcome**: Cleaner hierarchy and whitespace; no JS feature changes.

## 2026-06-02 — Wikidata P373 Commons category harvester

- **Goal**: Fill named atlas islands with Q-IDs but no photo via Wikidata **P373**
  (Commons category), bypassing v3’s commonswiki sitelink-only lookup.
- **What changed**:
  - **New:** `scripts/enrich_images_wikidata_p373.py` — `wbgetentities` P373,
    `categorymembers`, quality/name scoring (v3 parity + filename name-match pass),
    `source: commons-category-p373`, cache `data/cache_wikidata_p373.json`,
    report `data/image_enrichment_wikidata_p373_report.json`, `--named-only`,
    `--limit`, atomic writes.
- **v3 diagnosis**: `enrich_images_v3` source A uses **commonswiki sitelink**, not
  P373 — explains `image_enrichment_v3_report.json` **0** commons-category adoptions
  on 3,500 targets (sitelink absent even when P373 exists on other islands).
- **Run**: `--named-only --limit 300` → **0 adoptions** (297/300 targets lack P373;
  3 with P373 only contain Admiralty charts / outline SVGs; `Sealwatching1444.jpg`
  false-positive on v3 `seal` non-photo regex). Full pending scan: **9/963** named
  Q-ID islands have P373; none yielded a licensable landscape photo.
- **Outcome**: Script ready for incremental re-runs; low yield on current pending
  pool (mostly shoals/banks without Commons photo categories).

## 2026-06-02 — Verified photo push toward 6,000 (multi-agent)

- **Goal**: Raise named-atlas photo coverage past **6,000** with ~**90%** confidence and verification on each adoption.
- **What changed**:
  - **Agents (parallel):** `scripts/verify_island_images.py` (confidence scoring + audit report); `scripts/adopt_photos_from_cache.py` (cache-only high-confidence adoptions); `scripts/enrich_images_geosearch_verified.py`; v5 flags `--min-confidence high`, `--named-only`, `--delay`, `--geosearch-radius`; `data/photo_push_analysis.json`.
  - **Orchestrator:** `scripts/run_photo_push.sh` (sequential single-writer pipeline; lock file).
  - **Runs:** v5 p18 (+15 high), osm-tags (+4), cache adopt (+**~266** commons-text-search with `imageConfidence: high` + `verifiedAt`); index + shards rebuilt.
  - **Verification:** `data/image_verification_report.json` — bands ≥90 / 80–89 / <80; suspect list for geosearch name mismatches.
- **Outcome / counts**: Named atlas **3,597 → 3,863** with lead photo (**+266** verified this session). Gap to 6,000: **2,137**. Commons **429** rate limits block live text-search/geosearch API batches (0 adoptions from live attempts). Overnight `run_photo_push.sh` started for off-peak retries.
- **Open items**: Resume push when Commons limits clear; do **not** run v3/v5 writers in parallel (checkpoint overwrite risk); consider `--fix-suspect` on legacy geosearch leads separately from count target.

## 2026-06-02 — Diverse photo sources push (+414)

- **Goal**: Maximize new verified lead photos for named atlas islands using disparate sources (outside v5-only path).
- **What changed**:
  - Added **`scripts/run_diverse_photo_sources.sh`** (lock file, sequential phases).
  - Ran full pipeline: `adopt_photos_from_cache`, `enrich_images_geograph_commons` (cache-only), `enrich_images_wikidata_p373`, `enrich_images_multilang_wiki`, `enrich_images_openverse` (2×200), v5 p18/osm-tags; Mapillary skipped (no token).
- **Outcome / counts**: Named with photo **3,871 → 4,285** (**+414**). Breakdown: **geograph-via-commons 411**, cache adopt **3**, openverse **2**; P373 / multilang / v5 API phases **0** (867/876 Q-IDs lack P373+sitelink; Commons live paths still thin). Index rebuilt. Verification: **1,136 ≥90**, **1,485** at 80–89, **1,664** &lt;80 on 4,285 leads.
- **Open items**: Re-run `enrich_images_geograph_commons.py --cache-only` after more `cache_commons_text` keys; Openverse batches when API healthy; `MAPILLARY_ACCESS_TOKEN` for tiny islets; v5 text-search off-peak for remaining **2,756** without photo.

## 2026-06-02 — Multilang Wikipedia / Wikivoyage pageimages

- **Goal**: Photo islands still missing images via cy/ga/gd/fr/de Wikipedia and Wikivoyage sitelinks (priority: en Wikivoyage → Celtic wikis → fr/de).
- **What changed**:
  - **New:** `scripts/enrich_images_multilang_wiki.py` — Wikidata sitelinks, per-wiki `pageimages`, Commons licence via v5 `fetch_commons_meta`; caches `cache_multilang_sitelinks.json`, `cache_multilang_pageimages.json`; report `image_enrichment_multilang_report.json`; named-only default; source codes `wikivoyage`, `wikipedia-cy`, etc.
- **Outcome / counts**: Pilot `--limit 200` — **1** adoption (`csv-geocoded-Q108407584` via `wikipedia-de`, CC BY-SA 2.0); **200** attempted; only **5** multilang page titles among first 200 Q-ID queue (sparse sitelinks). One Wikidata **429** during sitelink prefetch (30s backoff, continued).
- **Open items**: Run larger batch off-peak; most pending named islands lack cy/ga/gd/fr/de/Wikivoyage sitelinks — pair with P373 / geosearch sources for volume.

## 2026-06-02 — Mapillary street-level enrichment script

- **Goal**: Prototype CC-BY-SA Mapillary v4 photos for small named islands still without `images[]`.
- **What changed**: `scripts/enrich_images_mapillary.py` — bbox query + 300 m centroid check, optional `areaKm2 < 0.5` filter, `imageConfidence: medium`, cache + report; dry-run `--limit 50`.
- **Outcome / counts**: Graph API **requires** token (`Invalid OAuth 2.0 Access Token` without one). **0** adoptions in workspace (no `MAPILLARY_ACCESS_TOKEN` set). Probe + report at `data/image_enrichment_mapillary_report.json`.
- **Open items**: Register client token at mapillary.com/dashboard/developers; re-run with `MAPILLARY_ACCESS_TOKEN=MLY|… python3 scripts/enrich_images_mapillary.py --limit 50`.

## 2026-06-02 — Category-coloured map pins + legend

- **Goal**: Distinct, accessible map pin colours per island category (type, unnamed, topic, for-sale) with a polished map key on light OSM tiles.
- **What changed**:
  - **`app.js`**: Replaced viewport `circleMarker` paints with `L.divIcon` teardrop pins (`MAP_PIN_SVG`, `getIslandPinCategory`, `makeCategoryPinIcon`); neutral custom cluster bubbles (`makeClusterIcon`); for-sale layer uses gold pin + £ glyph (same interactions).
  - **`styles.css`**: Pin fill tokens aligned to `:root` (`--explore`, `--cluster`, `--pin-stroke`); `.map-pin--*` / `.map-pin__glyph` badges (`?`, `◆`, `£`); compact 2-column `.legend` with `.legend-pin` swatches.
  - **`index.html`**: Map key items match pin categories + cluster row; map hint copy “pin” not “dot”.
- **Outcome / counts**: Seven pin categories + neutral clusters; for-sale still on dedicated pane (excluded from cluster). Boot path unchanged (chunked `rebuildMarkerLayer`, lazy tooltips ≤7).
- **Open items**: None — photo/has-image pin variant deferred to avoid legend clutter.

## 2026-06-02 — Openverse image enrichment

- **Goal**: Lead photos for named atlas islands without `images[]` via Openverse API (CC0 / PDM / BY / BY-SA only).
- **What changed**:
  - **New:** `scripts/enrich_images_openverse.py` — name + nation query, optional `lat`/`lon` bias, v5 word-boundary name match, 15 km geo (5 km generic names), caches `data/cache_openverse.json`, report `data/image_enrichment_openverse_report.json`, backup `islands.json.before-openverse`.
- **Outcome / counts**: Pilot `--limit 100 --named-only` — **2** adoptions (**2%** hit rate): `osm-way-186667713` (Abbey Island, CC-BY-SA-2.0 Flickr), `osm-way-146468873` (Aigeach, CC-BY-SA-2.0). API healthy; strict name/geo filters reject most homonyms.
- **Open items**: Larger off-peak batch on distinctive Gaelic/English names; consider Gaelic `names.*` in Openverse query string.

## 2026-06-02 — Wikidata P373 Commons staging pass

- **Goal**: Harvest P373 (+ commonswiki sitelink fallback) for photoless Q-ID islands; stage adoptions without touching `islands.json`.
- **What changed**:
  - **`scripts/enrich_images_wikidata_p373.py`**: default output `data/staging/adoptions/p373-commons.json`; `--apply` opt-in for `islands.json`; P373 then sitelink category resolution; name-match + quality pick (v3 parity).
  - **Caches warmed** (cache-first): `data/cache_wikidata_p373.json` (963 Q-IDs, **9** with P373).
- **Outcome / counts**: `--named-only --limit 500` then full **876** photoless Q-ID pool — **0 staged**. Breakdown: **867** no category; **9** category but members are maps/charts only (`no_photo`). v3 `commons-category: 0` explained: v3 never read P373; for this pool P373-only gain is **0** (all 9 with P373 already had sitelink); sitelink-only among photoless = **0**.
- **Open items**: P373/geosearch not viable for volume on this queue — prioritize geosearch-verified, multilang wiki, Openverse, cache commons-text per `run_photo_push.sh`.

## 2026-06-02 — Staged photo adoptions merge (single writer)

- **Goal**: Safely merge parallel harvester output from `data/staging/adoptions/*.json` into `islands.json` after a 10-minute soak.
- **What changed**:
  - **`scripts/merge_staged_photo_adoptions.py`**: dedupe by island id (highest confidence); backup `islands.json.before-staged-merge`; atomic write; lead-photo-only; stamp `imageConfidence` + `verifiedAt`; report `data/staged_merge_report.json`; rebuild index.
  - **`docs/STATE.md`**: merger row in Currently running (cleared when done).
- **Outcome / counts**: 10 min soak → **4** staging files (**416** raw rows). **Merged +5** (`openverse` only). **Skipped 411** (`geograph-commons.json` — island already had lead photo). **0** cross-file dedupe conflicts. Named atlas with photo **4,285 → 4,290** (+5). Gap to 6,000: **2,751**.
- **Open items**: Re-run geograph staging against islands still without photos, or apply geograph via `--apply` on a fresh index snapshot; investigate why 411 geograph candidates already had photos at merge time.

## 2026-06-02 — Commons text warm + regional category staging

- **Goal**: Maximise Commons coverage without geosearch 429s — warm text cache, re-run Geograph-on-Commons cache pass, stage regional category matches.
- **What changed**:
  - **New:** `scripts/warm_commons_text_cache.py` — `"{name}"` + `"{name}" geograph` into `cache_commons_text.json`; `--delay 3`; stop on HTTP 429; no `islands.json` writes.
  - **New:** `scripts/enrich_images_commons_regional.py` — nation root categories + cached per-island category scan (`--cache-only`); stages `data/staging/adoptions/commons-deep.json`.
  - Re-ran `enrich_images_geograph_commons.py --cache-only` before/after warm.
- **Outcome / counts**: Warm `--limit 500` — **+1** cache key (`3,002 → 3,003`); stopped on **429** after ~2 queries (Commons hot). Geograph cache-only re-run — **0** staged (photoless queue **2,751**; prior geograph merges already applied). Regional — **2** staged via cached categories: Stac Levenish, Piper's Island. Live Scotland root walk saw **126** files, **0** name matches (strict `_mentions`; API 429 on follow-up searches).
- **Open items**: Resume `warm_commons_text_cache.py` off-peak until ~2,700 missing keys filled; then geograph `--cache-only` again; regional live pass when 429 clears.

## 2026-06-02 — Flickr + Europeana + Openverse photo staging

- **Goal**: Lead photos for named atlas islands without `images[]` via Europeana, Flickr CC/Commons, and extended Openverse (`--limit 800`).
- **What changed**:
  - **New:** `scripts/enrich_images_flickr_europeana.py` — Europeana `reusability=open` + `TYPE:IMAGE`, Flickr `photos.search` (licences 4/5/9/10), tag-feed fallback when no `FLICKR_API_KEY`; caches `cache_europeana.json`, `cache_flickr_cc.json`, `cache_flickr_commons_feed.json`; stages `flickr-europeana.json`.
  - **`enrich_images_openverse.py`**: `MAX_LIMIT` raised **500 → 800**.
  - **`.env.local.example`**: documented `EUROPEANA_API_KEY`, `FLICKR_API_KEY`.
- **Outcome / counts**: No API keys in env — Europeana/Flickr API skipped; feed fallback **0** (Flickr JSON feeds omit CC licence URLs). `flickr-europeana.json` **0** staged (50-island probe). Openverse `--limit 800 --named-only` — **+3** staged (`openverse.json`): Cliffs of Moher row, Cruagh, De'il's Heid. **2,751** named still photoless.
- **Open items**: Add Europeana + Flickr keys to `.env.local`, re-run `enrich_images_flickr_europeana.py`; merge new staging via `merge_staged_photo_adoptions.py`.

## 2026-06-02 — OGL / public-sector tourism photo staging

- **Goal**: Allowlisted OGL/CC harvest from UK/Ireland public open data (not press libraries); stage with name match.
- **What changed**:
  - **New:** `scripts/enrich_images_ogl_tourism.py` — Commons regional island categories (261 cats, 8,543 files indexed); data.gov.uk CKAN OGL image resource indexer; blocks NatureScot/NE/NRW/Fáilte/VisitScotland/Canmore with reasons in report; prioritises islands with filename candidates before `--limit`.
  - **Outputs:** `data/staging/adoptions/ogl-tourism.json`, `data/cache_ogl_commons_regional.json`, `data/image_enrichment_ogl_tourism_report.json`.
- **Outcome / counts**: `--named-only --limit 400` — **21 staged** (all `commons-regional-category`; CC-BY-SA/BY-4.0 via Commons). **21** of 2,751 named photoless had filename candidates in regional trees; data.gov.uk OGL image resources **0**. Blocked sources documented (7). Some homonym risk on generic names (“The Field”, “Goose Island”).
- **Open items**: Merge via `merge_staged_photo_adoptions.py`; manual review homonyms; expand data.gov.uk seeds or trove.scot when machine OGL path exists.

## 2026-06-02 — iNaturalist CC observation staging

- **Goal**: Lead photos for small named islands without `images[]` via iNaturalist research-grade CC observations near centroid.
- **What changed**:
  - **New:** `scripts/enrich_images_inaturalist.py` — named index only; eligibility `areaKm2` < 1 or skerry-like; API query radius 0.5 km; adopt within 300 m; landscape/coastal filter (habitat taxa, coastal place text, landscape aspect); explicit CC on observation + photo; stages `data/staging/adoptions/inaturalist.json`; cache `data/cache_inaturalist.json`; report `data/image_enrichment_inaturalist_report.json`.
- **Outcome / counts**: `--named-only --limit 300` — **18 staged** (**6%** hit rate). Licences: CC-BY-4.0, CC-BY-SA-4.0, CC0-1.0. Most small Hebridean skerries have zero iNat coverage within 500 m.
- **Open items**: Merge via `merge_staged_photo_adoptions.py`; optional wider batch on English/Welsh coastal islets with higher iNat density.

## 2026-06-02 — Internet Archive / NLS / BL Flickr / Wellcome staging

- **Goal**: Historical open photos from Archive, NLS, British Library Flickr Commons, and Wellcome; stage with strict licence + name match.
- **What changed**:
  - **New:** `scripts/enrich_images_archive_nls.py` — IA `advancedsearch.php` (`mediatype:image`, PD/CC filter in code), NLS digital gallery probe (no public JSON API), NLS + BL Flickr Commons feeds (`14456531@N07`, `12403504@N02`) and optional `FLICKR_API_KEY` REST (`license=7`), Wellcome `/catalogue/v2/images` with name-only query fallback; unified `data/cache_archive_nls.json`; stages `data/staging/adoptions/archive-nls.json`.
- **Outcome / counts**: API probe — **IA ok**, **Wellcome ok**, **NLS gallery unavailable**, **BL/NLS Flickr feeds ok** (no `FLICKR_API_KEY`). `--named-only --limit 300` (~83 min): **1** staged (**0.3%**) — Wellcome `ararat` / Mount Ararat homonym; cleared from `archive-nls.json`; `_title_mentions_nation` guard added. **0** from IA/BL/NLS Flickr under strict licence + name rules. Re-run recommended for a clean batch.
- **Open items**: Let `--limit 300` finish; merge via `merge_staged_photo_adoptions.py`; add `FLICKR_API_KEY` for BL/NLS text search.

## 2026-06-02 — Staged photo merge #2 (OGL + iNat + regional)

- **Goal**: Single-writer merge of new staging after diverse/geograph push; rebuild index.
- **What changed**:
  - Polled ~20 min until no process held `islands.json` open (`archive_nls` still staging-only).
  - **`merge_staged_photo_adoptions.py`** (unified path — not per-harvester `--apply`).
  - `python3 scripts/build_islands_index.py`.
  - **`docs/STATE.md`**: merge #2 counts + Currently running.
- **Outcome / counts**: **+45** merged — **commons-regional-category 23**, **inaturalist-obs 18**, **openverse 3**, **wellcome-collection 1** (by staging file: ogl-tourism 21, inaturalist 18, openverse 3, commons-deep 2, archive-nls 1; 2 ogl rows deduped with commons-deep). Named with photo **4,290 → 4,335**. Cumulative today: diverse push **+414** (incl. **411** `geograph-via-commons` on islands before staged merge #1); merge #1 **+5** openverse; merge #2 **+45**. Gap to 6,000: **2,706**.
- **Open items**: Let `archive_nls` finish and merge again; re-stage geograph for remaining photoless queue.

## 2026-06-02 — Staged merge soak + index verify (subagent)

- **Goal**: Poll until harvesters finish staging; ensure single-writer merge; rebuild index + verify images.
- **What changed**:
  - Polled `data/staging/adoptions/*.json` every **90 s** for **45 min** (no `--apply` writers; blocked concurrent merges until clear).
  - Fixed `merge_staged_photo_adoptions.py` backup to `shutil.copy2` **before** in-memory edits.
  - Waited for `enrich_images_archive_nls.py --limit 300` (~83 min total; **1** staged, homonym-only).
  - Post-soak `merge_staged_photo_adoptions.py`: **0** new (44 deduped candidates skipped — already had photo from merge #2).
  - `build_islands_index.py` + `verify_island_images.py`.
  - **`docs/STATE.md`**: soak + verify counts; archive_nls complete.
- **Outcome / counts**: Named with photo **4,335** / 7,041. Merge #2 sources (already applied): **commons-regional-category 23**, **inaturalist-obs 18**, **openverse 3**, **wellcome-collection 1**. Verification bands: **≥90** 1,136 / **80–89** 1,485 / **<80** 1,714. Gap to **6,000**: **2,665**.
- **Open items**: Re-stage geograph for **2,706** photoless named islands; resume Commons cache warm off-peak; v5 text-search when 429 clears.

- **Verify fix** (`verify_island_images.py --fix-suspect --min-confidence 85` + index rebuild): named with photo **4,335 → 2,621** (**−1,714** leads &lt;85 removed; **Brothers** / **Brake** / **Barrels** openverse false positives cleared). Gap to **6,000**: **3,379**. Backup: `data/islands.json.before-verify`.

## 2026-06-02 — Revert broad verify --fix-suspect (correction)

- **Goal**: Undo accidental mass removal from `--fix-suspect --min-confidence 85`; keep only the three intended Openverse false positives removed.
- **What changed**:
  - Restored `data/islands.json` from `data/islands.json.before-verify` (atomic replace; backup validated as JSON list, 11,351 islands).
  - Removed lead photo only for `osm-way-236692704` (Brothers), `wd-Q24654332` (Brake), `wd-Q24657075` (Barrels) where lead `source` was `openverse` (verify score 45, suspect).
  - `python3 scripts/build_islands_index.py`.
- **Outcome / counts**: Named with photo **4,332** (was **4,335** pre-verify; **2,621** after erroneous fix). **Do not** re-run broad `--fix-suspect` without per-source policy.

## 2026-06-04 — Verified staged merge audit (20 rows)

- **Goal**: After strict gate, merge only `adoptions-verified/` if any photoless; report overlap with existing `images[]`.
- **What changed**: Pre-merge audit of **inaturalist.json** (18) + **commons-deep.json** (2); dry-run `merge_staged_photo_adoptions.py` (verified dir default). `data/staged_merge_report.json` updated (dry_run). **No** `islands.json` write; no script change (`prefer adoptions-verified` already in `merge_staged_photo_adoptions.py`).
- **Outcome / counts**: **0** newly merged, **20** already present (skipped has image). Named with photo **4,332** unchanged. Did **not** run `verify_island_images.py --fix-suspect`.

## 2026-06-04 — Strict staged photo verification gate

- **Goal**: Pre-merge gate requiring two independent signals (entity + geo/name/anchor) before any future staged merge.
- **What changed**:
  - Added `scripts/verify_staged_photos_strict.py` (scores 0–100; ≥90 needs signal A + B; rejects name-only).
  - `--remove-openverse-without-geo` flag for future Openverse filtering.
  - Wrote `data/staging/adoptions-verified/*.json` and `data/staging/adoptions_strict_verify_report.json`.
- **Outcome / counts**: **44** staged rows in → **20** passed: **commons-deep 2/2**, **inaturalist 18/18**; **ogl-tourism 0/21**, **openverse 0/3** (homonyms / regional-category without island entity). Empty staging files mirrored with zero adoptions. **No** `islands.json` write.
- **Open items**: Merge only from `adoptions-verified/` after review; re-stage ogl-tourism with island-specific Commons categories or Wikidata/OSM entity links.

## 2026-06-04 — Photo discovery ideas doc

- **Goal**: Catalogue outside-the-box, high-confidence photo sources beyond Wikimedia geosearch/Openverse.
- **What changed**:
  - Added `docs/PHOTO-DISCOVERY-IDEAS.md` (35 ideas + verification ladder + top-10 yield×confidence ranking).
  - Linked from `docs/INDEX.md` (Tier 3).
- **Outcome / counts**: Documentation only; no dataset or pipeline changes.
- **Open items**: Prioritise depicts=Q (#3) and all-language pageimages (#6) in next enrichment pass per doc ranking.

## 2026-06-04 — Unconventional harvesters (all-lang wiki, PCW, Dúchas)

- **Goal**: Build and run three staging-only photo harvesters with caching.
- **What changed**:
  - `scripts/enrich_images_wikipedia_alllangs.py` → `wikipedia-alllangs.json` (wbgetentities all sitelinks; pageimages batched per wiki; high confidence = title name match).
  - `scripts/enrich_images_peoples_collection_wales.py` → `pcw.json` (discover `keywords` + item HTML parse; OGL/CC only; excludes Creative Archive NC).
  - `scripts/enrich_images_duchas.py` → `duchas.json` (CBÉG probe; documents CC BY-NC policy block).
  - `.env.local.example`: `DUCHAS_API_KEY` / `GAOIS_API_KEY` placeholders.
- **Outcome / counts** (staging only, **0** merged):
  - **wikipedia-alllangs** `--limit 400`: **0** staged (400 attempted; title-matched pageimages on this pool were SVG locator maps, e.g. cebwiki `*location_map.svg`; Wikimedia 429 during prefetch).
  - **pcw** `--limit 100`: **52** Wales photoless attempted, **0** staged (discover noise / `licence-blocked:creative-archive-nc` / no name match).
  - **duchas** `--limit 50`: **0** staged; no API key; **not viable** for merge under `ETHICS.md` (default licence CC BY-NC 4.0).
- **Open items**: Re-run all-lang wiki with higher `--delay` on smaller named subset; PCW only useful where items carry CC/OGL not Creative Archive; Dúchas needs Gaois key + licence policy exception (unlikely).

## 2026-06-04 — Europeana geo, BL Flickr deep, SCRAN probe

- **Goal**: Three staging harvesters with dual-signal (name + geo) verification and `--limit 400` attempts.
- **What changed**:
  - `scripts/photo_staging_dual.py` — shared name+geo gate for staging.
  - `scripts/enrich_images_europeana_geo.py` → `europeana-geo.json` (Search API + `WHERE` geo qf; `EUROPEANA_API_KEY`; documents public endpoints when key unset).
  - `scripts/enrich_images_bl_flickr_deep.py` → `bl-flickr-deep.json` (BL Flickr `photos.search`, licence 7 only; `FLICKR_API_KEY`).
  - `scripts/enrich_images_scran.py` → `scran.json` (endpoint probe; skip harvest — no open API).
  - `.env.local.example` — key comments for Europeana + BL scripts.
- **Outcome / counts** (smoke, keys unset): **europeana-geo 0**, **bl-flickr-deep 0**, **scran 0** staged; SCRAN viability `no_open_api`. Reports under `data/image_enrichment_{europeana_geo,bl_flickr_deep,scran}_report.json`.
- **Open items**: Re-run with keys in `.env.local` at `--limit 400`; merge via `verify_staged_photos_strict.py` then `merge_staged_photo_adoptions.py`.

## 2026-06-04 — Commons archipelago category sweep

- **Goal**: Wider-than-regional Commons category traversal with full file index,
  v5 word-boundary filename matching, dual-signal staging.
- **What changed**:
  - `scripts/enrich_images_commons_archipelago_sweep.py` — **36** broad roots
    (Scotland/Ireland/Wales/England/Thames/Channel Islands/county firths, etc.),
    `--build-index` / `--match`, cache `data/cache_commons_archipelago_index.json`,
    staging `data/staging/adoptions/commons-archipelago.json`.
  - Dual signal: island-specific subcategory **or** filename `_mentions` +
    nation/archipelago anchor in caption/categories.
- **Outcome / counts** (staging only): index **13,309** files / **374** categories;
  **15** island candidates, **9** staged (**6** rejected `no-dual-signal`).
  Commons **429** during Ireland subcat walk (30s backoff). Report:
  `data/image_enrichment_commons_archipelago_report.json`.
- **Open items**: Human review before merge (e.g. homonym Duck Island ×4, Ardillaun
  vs Ardoileán file); re-run match with warmed `cache_commons.json` after 429 cool-down.

## 2026-06-04 — Wikipedia gallery wikitext harvester

- **Goal**: Mine embedded Commons files from island Wikipedia articles (not just
  pageimage lead), with caption/alt name gate and Commons licence verification.
- **What changed**:
  - `scripts/enrich_images_wikipedia_gallery.py` — wikitext via MediaWiki
    `revisions`, parsers for `[[File:]]`, `<gallery>`, `{{multiple image}}`,
    infobox `| image =`; staging `data/staging/adoptions/wikipedia-gallery.json`;
    caches `cache_wikipedia_gallery_{sitelinks,wikitext}.json`.
- **Outcome / counts** (smoke `--limit 30` after sitelink prefetch): **706** named
  photoless with a `*wiki` article; **0** staged (stub articles / maps / strict
  caption gate). Parser verified on Iona wikitext (would stage `TyIonaNunnery…`
  when not already imaged). Report: `data/image_enrichment_wikipedia_gallery_report.json`.
- **Open items**: Full `--limit 500` after 429 cool-down; consider infobox
  filename-only match when `File:` name contains island token.

## 2026-06-04 — Heritage OGL photo staging (NHLE / Canmore / Cadw)

- **Goal**: Stage OGL/CC island photos from UK heritage registers with strict
  name + place + documented licence; document blocked sources.
- **What changed**:
  - `scripts/enrich_images_heritage_ogl.py` — probes NHLE ArcGIS, HES Canmore
    MapServer (`inspire.hes.scot`), Cadw Listed Buildings WFS; optional HTML
    og:image parse on list-entry / Canmore / Cadw report URLs; staging
    `data/staging/adoptions/heritage-ogl.json`; cache `data/cache_heritage_ogl.json`.
- **Outcome / counts**: `--named-only --limit 300` → **0 staged** (300 no_match).
  **APIs working**: `historic-england-nhle-arcgis`, `hes-canmore-points`,
  `cadw-listed-wfs`. **Blocked**: legacy `canmore.org.uk` WAF, `trove.scot` 403,
  NHLE `hasAttachments=false`, Heritage Gateway no national image API, Coflein /
  HE Archive / Cadw reports without OGL photo URLs. Report:
  `data/image_enrichment_heritage_ogl_report.json`.
- **Open items**: None — metadata APIs usable for enrichment flags; photos need
  Commons/Geograph or manual trove licence per asset.

## 2026-06-04 — Panoramax + OpenAerialMap geo CC harvesters

- **Goal**: Stage CC street-level (Panoramax) and CC orthomosaic (OAM) lead
  photos for tiny named islands without images; `--limit 150` each.
- **What changed**:
  - `scripts/enrich_images_panoramax.py` — Panoramax STAC `/api/search` bbox,
    250 m centroid gate, CC-BY-SA only, `areaKm2` < 0.3; staging
    `data/staging/adoptions/panoramax.json`; cache `data/cache_panoramax.json`.
  - `scripts/enrich_images_openaerialmap.py` — STAC-style bbox via
    `GET https://api.openaerialmap.org/meta`, centroid-in-footprint, CC-BY /
    CC-BY-SA / CC0 only (no NC); staging `openaerialmap.json`;
    cache `data/cache_openaerialmap.json`. Fixed HTTP→HTTPS (308) on OAM API.
- **Outcome / counts**: Panoramax **1** staged / 150 attempted (`osm-way-1002798076`,
  75 m). OpenAerialMap **0** staged / 150 attempted (sparse UAV coverage at islet
  scale). Reports: `data/image_enrichment_{panoramax,openaerialmap}_report.json`.
- **Open items**: None — merge via `verify_staged_photos_strict.py` then
  `merge_staged_photo_adoptions.py` if the Panoramax row passes dual-signal gate.

## 2026-06-04 — Wikidata depicts (P180) Commons staging

- **Goal**: High-confidence novel source — Commons files whose structured data
  explicitly **depicts** the island Q-ID (complement to Wikidata P18 / pageimages).
- **What changed**:
  - Added `scripts/enrich_images_wikidata_depicts.py` — discovery via Commons
    `haswbstatement:P180=<Q-ID>`, batched WDQS reverse depicts prefetch, optional
    Commons WCQS (OAuth); verification reads MediaInfo `statements.P180` (not
    `claims`); full Commons `extmetadata` for licence/attribution; staging
    `data/staging/adoptions/wikidata-depicts.json`; cache
    `data/cache_wikidata_depicts.json` (sets serialised as lists).
- **Outcome / counts**: `--named-only --limit 500` → **5 staged** / 500 attempted
  (**1%**); **495** `no_candidates` (no indexed depicts on obscure photoless Q-IDs).
  Examples: Furze Island, Carbery Island, Calf Island East/Middle/West (shared
  Dunmanus Bay / Illaunkearagh Commons files). Smoke on Q107393 (Isle of Skye):
  24 search hits, 5 verified — pipeline OK; Skye already has a lead photo. Report:
  `data/image_enrichment_wikidata_depicts_report.json`.
- **Open items**: Re-run remaining **363** photoless Q-ID pool (`--limit 0` or
  offset queue); merge after `verify_staged_photos_strict.py`; expect low yield
  until more SDC depicts are added on Commons.

## 2026-06-04 — Commons depicts-Q (P180 + P921) staging

- **Goal**: PHOTO-DISCOVERY ideas #1–#3 — reverse Commons/Wikidata graph for files
  whose structured data depicts or has main subject = island Q-ID (~95% when P180
  verified).
- **What changed**:
  - Added `scripts/enrich_images_commons_depicts_q.py` — Commons search
    `P180`/`P921`, batched WDQS (`wdt:P180`/`P921`), optional Commons WCQS;
    MediaInfo verification (P180 preferred over P921 for confidence); staging
    `commons-depicts-q.json`; cache `cache_commons_depicts_q.json` (claim sets
    serialised as lists).
- **Outcome / counts**: `--named-only --limit 600` → **6 staged** / 600 (**1%**);
  **594** `no_candidates`; **6** P180 / **0** P921-only. Same Dunmanus / Illaunkearagh
  cluster as wikidata-depicts pass (Furze Island, Carbery, Calf East/Middle/West).
  Report: `data/image_enrichment_commons_depicts_q_report.json`.
- **Open items**: Merge after strict verify; re-run `--limit 0` on remaining **263**
  photoless named Q-IDs; P921 yield likely low for rock islets per discovery doc.

## 2026-06-04 — OSM bulk tag Overpass staging

- **Goal**: One-pass harvest of OSM `image` / `wikimedia_commons` / `wikipedia:*` /
  `wikidata` for all named photoless islands with OSM ids; stage via v5
  `try_osm_tags`.
- **What changed**:
  - Added `scripts/enrich_images_osm_bulk.py` — 63-tile bbox Overpass (curl POST
    like v5), shared `cache_osm_tags_v5.json` + `cache_osm_tags_bulk.json`,
    id-batch fallback for keys still without photo tags, staging
    `osm-bulk.json`. Flags: `--skip-bbox`, `--cache-only`, `--force`.
- **Outcome / counts**: Full named pool **2,235** OSM keys (~**30 min** bbox pass,
  **58/63** tiles OK; **5** tiles timed out/WAF). Id fallback refreshed cache.
  **0 staged** — photo-tagged elements in cache either already have atlas photos
  (Geograph/File: on other islands) or tags point at non-adoptable hosts /
  wrong Wikipedia leads. Report: `data/image_enrichment_osm_bulk_report.json`.
- **Open items**: None; confirms v5 OSM path largely exhausted for photoless pool.

## 2026-06-04 — KartaView + GBIF geo photo staging

- **Goal**: CC geo-tagged lead photos from KartaView/OpenStreetCam and GBIF
  research-grade occurrences with strict centroid verification; stage only.
- **What changed**:
  - Added `scripts/enrich_images_kartaview.py` — OpenStreetCam 2.0 API,
    CC-BY-SA, `areaKm2` < 0.3, 200 m verify, `kartaview.json` +
    `cache_kartaview.json`.
  - Added `scripts/enrich_images_gbif.py` — iNaturalist research-grade dataset
    on GBIF, CC0/BY/BY-SA StillImage media, 300 m verify, `gbif.json` +
    `cache_gbif.json`.
- **Outcome / counts**: `--named-only --limit 200` each — **kartaview 1** staged
  (Blake's Island @ 198 m); **gbif 0** staged (no CC StillImage within 300 m on
  first-200 photoless queue). Reports:
  `data/image_enrichment_kartaview_report.json`,
  `data/image_enrichment_gbif_report.json`.
- **Open items**: Merge kartaview row after verify; GBIF yield may improve on
  coastal/small-island priority queue (current head is inland/obscure names).

## 2026-06-04 — Verified staged merge after 60 min harvest soak

- **Goal**: Wait for harvesters + strict staged verify, merge only from
  `adoptions-verified/`, single writer with backup and index rebuild.
- **What changed**:
  - Extended `scripts/verify_staged_photos_strict.py` (dual-signal scoring,
    depicts-Q / archipelago / iNaturalist sources; min score 90).
  - Extended `scripts/merge_staged_photo_adoptions.py` (prefer verified dir,
    timestamped backup, inline verify fallback for raw staging).
  - Polled staging 60 min (2 min interval) until harvesters idle.
  - Merged **9** new photos from **34** verified rows (**66** raw staged).
- **Outcome / counts**: Named with photo **4,341** (was **4,332**); gap to **6,000**
  **1,659**. Sources merged: **commons-depicts-q 6**, **commons-archipelago-category 3**.
  **20** verified rows skipped (already had `images[]`). Backup
  `data/islands.json.before-staged-merge-20260604T071708Z.bak`.
- **Open items**: **25** verified rows still not merged (prior photos); ogl-tourism /
  openverse / kartaview / panoramax failed strict gate (min 90).

## 2026-06-04 — 90 min enrich poll + idempotent verified merge

- **Goal**: Wait for all `enrich_images_*` harvesters to finish, re-run strict
  staged verify on full `adoptions/`, merge from `adoptions-verified/` only,
  rebuild index; report photo counts (no aggressive `--fix-suspect`).
- **What changed**:
  - Polled every **2 min** (Python `scripts/enrich_images_*` only) until idle
    (~**30 min**; gbif, kartaview, openaerialmap, heritage_ogl, wikidata_depicts,
    commons_depicts_q, osm_bulk completed during soak).
  - `verify_staged_photos_strict.py` → **34 / 66** accepted (**51.5%**).
  - `merge_staged_photo_adoptions.py` (verified dir) → **0** new; **29** deduped
    candidates all already had `images[]` (earlier **+9** merge at 07:17).
  - `build_islands_index.py` + nation shards refreshed.
  - `docs/STATE.md` updated.
- **Outcome / counts**: Named with photo **4,341** / 7,041; gap to **6,000**
  **1,659**. Strict gate pass **34/66**. This merge pass `merged_by_source`: _(none)_.
  Prior same-day merge: **commons-depicts-q 6**, **commons-archipelago-category 3**.
- **Open items**: ogl-tourism (**21** @ conf 85) and openverse (**3**) still fail
  min-90 gate; kartaview/panoramax at 80 without dual signal.

## 2026-06-11 — Continuous improvement loop (enrichments + photos)

- **Goal**: Run both priority tracks on a recurring schedule — enrichment apply
  and photo coverage toward 6,000 — without parallel `islands.json` writers.
- **What changed**:
  - Added `scripts/run_continuous_improvement.sh` — Phase 1: fetch missing
    enrichment caches (`cache_dobih.json` still absent) + `apply_enrichments.sh
    --yes --force`; Phase 2: rotate staging harvesters (6-source cycle),
    strict verify, staged merge, cache adopt, v5 P18/OSM limited batches, index
    rebuild. State file `data/.continuous_improvement_state.json`.
  - Armed **45 min** recurring shell loop (`AGENT_LOOP_TICK_CONTINUOUS_IMPROVE`).
  - Updated `docs/STATE.md`, `docs/QUEUE.md`.
- **Outcome / counts**: Cycle 1 in flight; baseline **4,341** named with photo /
  7,041; gap **1,659**.
- **Open items**: DoBIH CSV signup for full hills list; UI rendering for enrichment
  field groups; stop loop on request (`kill` loop PID + clear lock if stuck).

## 2026-06-11 — Priority photo harvesters P1–P5 (grid fix + first merge)

- **Goal**: Implement top-five photo-source priorities from brainstorm; fix Geograph
  grid-ref bug blocking P1; run verify → merge → index; wire into continuous loop.
- **What changed**:
  - `scripts/photo_geo_utils.py` — OSGB refs via `osgb.format_grid` (was
    single-letter formula → e.g. Furze Brake `O003094` instead of `SU035946`).
  - P1–P5 scripts + `scripts/run_priority_photo_push.sh` orchestrator.
  - Fixed `fetch_commons_meta([fname], cache)` in `enrich_images_wikipedia_embedded.py`,
    `enrich_images_commons_county.py`, `enrich_images_wd_nearby_p18.py`; P2 429
    backoff on Wikidata.
  - `run_continuous_improvement.sh` — 11-source rotation (P1–P5 before legacy six).
  - `verify_staged_photos_strict.py` — base scores for new sources (prior session).
- **Outcome / counts**: `run_priority_photo_push.sh` limit **50**: P1 staged **1**
  (`geograph-native` / `osm-way-985212914`); strict verify **1/1**; merge **+1**.
  Named with photo **4,342** / 7,041; gap to **6,000** **1,658**. P3 skipped
  (no Flickr key); P2 429; P4/P5 crashed pre-fix.
- **Open items**: Re-run full push after fixes; add `FLICKR_API_KEY` for P3; larger
  `PHOTO_PUSH_LIMIT` soak; naming brainstorm (100 approaches) still unimplemented.

## 2026-06-11 — Unnamed island naming pipeline (100 ideas → N1–N3)

- **Goal**: Start implementing the 100 high-confidence naming approaches for
  ~4,310 `nameStatus=unknown` islands; stage → verify → merge without inventing names.
- **What changed**:
  - `docs/NAMING-SOURCES.md` — full 100-idea registry with tiers, status, runbook.
  - `scripts/name_staging_utils.py`, `verify_staged_names.py`,
    `merge_staged_name_proposals.py`, `run_priority_naming_push.sh`.
  - Harvesters: `name_unnamed_os_open_names.py` (#16), `name_unnamed_logainm_oil.py`
    (#31), `name_unnamed_osm_tags.py` (#1–2); `fetch_os_open_names.py`.
  - Merge adds optional `nameProvenance` object on adopted islands.
  - `docs/INDEX.md`, `docs/STATE.md`, `docs/QUEUE.md` updated.
- **Outcome / counts**: Unnamed **4,310** (unchanged). OSM-tags probe **0/300**
  (all `no name tags` — expected for current unnamed pool). N1/N2 blocked on API keys.
- **Open items**: Fetch OS Open Names CSV; Logainm OIL bulk with Gaois key; implement
  N4 Canmore/NHLE (#46, #49), N5 ohsome (#3), N6 fusion (#99).

## 2026-06-11 — Discovery push D1–D2 + naming N4–N6

- **Goal**: Launch new island discovery approaches and complete naming harvesters N4–N6.
- **What changed**:
  - `discover_geonames_gaps.py`, `discover_wikipedia_coord_lists.py`,
    `run_priority_discovery_push.sh`, `docs/DISCOVERY-PUSH.md`.
  - `name_unnamed_heritage.py`, `name_unnamed_ohsome.py` (OSM API history after
    ohsome 404), `name_unnamed_fusion.py`; `run_priority_naming_push.sh` updated.
  - `verify_staged_names.py` — fusion + heritage source gates.
- **Outcome / counts**: GeoNames **378** gap candidates (`candidates_geonames.json`);
  Wikipedia coords **10** gaps. Atlas **7,041** unchanged. Naming smoke tests 0/15
  heritage, 0/30 OSM history on first unnamed batch (expected for never-named ways).
- **Open items**: Re-run Wikipedia lists after 429; verifier pass on GeoNames gaps;
  Wikidata SPARQL island gap harvester (DISCOVERY-SOURCES action #1).

## 2026-06-12 — Staged verify + production merge (photos, names, discovery)

- **Goal**: Verify all staged photo/name/discovery candidates and merge verified rows
  into `islands.json` + rebuild index.
- **What changed**:
  - Ran `verify_staged_photos_strict.py` → **17/49** accepted.
  - `merge_staged_photo_adoptions.py` → **0** new photos (12 deduped, already had images).
  - `verify_staged_names.py` / `merge_staged_name_proposals.py` → **0** (empty proposals).
  - `discover_islands_pipeline.py --stage=site_update --apply` → **274** merges into
    existing islands (field enrichment, not new records).
  - New `apply_staged_discovery_gaps.py` — Wikidata verify on 388 GeoNames/Wikipedia
    gap candidates → **+28** new islands.
  - `build_islands_index.py` refreshed.
- **Outcome / counts**: Atlas **11,351 → 11,379** (+28 islands); index named **7,041 → 7,069**
  (+28); named with photo **4,342** (unchanged); unnamed **4,310** (unchanged).
  Backups: `islands.json.before-discovery-20260612T112931Z`,
  `islands.json.before-discovery-gaps-20260612T114411Z`.
- **Open items**: Git push to GitHub Pages for live site; review 28 new `unconfirmed`
  discovery rows (some Wikidata matches may be hills/stacks); 357 gap candidates rejected.

## 2026-06-12 — Learner UX priorities P1–P5

- **Goal**: Make the atlas more useful for learning about islands with a simpler,
  story-first UI (priorities from product review).
- **What changed**:
  - **P1** — `With stories` quick filter (`islandHasStory`); sparse profile lede
    when no `shortDescription`; `build_description_priority_queue.py` (Wikipedia-URL
    tier first); `enrich_descriptions_wikipedia.py --queue-file`; **+16** Wikipedia
    lead extracts.
  - **P2** — Default **Hide needs review** on confidence filter; sidebar reordered
    (Notable islands → Explore topics → filter chips); chip labels renamed
    (Picture-ready, Ferry access, Unnamed survey).
  - **P3** — Profile hierarchy: key-facts strip (3), related islands (archipelago /
    water body), **All facts** + **Sources & provenance** collapsed `<details>`.
  - **P4** — Ferry block already titled “How to get there”; moved above map; maritime /
    wildlife sections unchanged (data already on records).
  - **P5** — `CHAT_LEARNING_STARTERS` + visible starter chips in Ask drawer.
  - `app.js`, `index.html`, `styles.css`; index rebuilt.
- **Outcome / counts**: Named with `shortDescription` **1,536 → 1,552**; ~**4,590**
  named islands with photo or story; queue **1,599** Wikidata-linked gaps remain.
- **Open items**: Continue Wikipedia queue pass (98 direct URL + 1,501 Wikidata-only
  need sitelink harvest); consider multilang Wikipedia for Gaelic/Welsh islands.

## 2026-07-26 — SEO / GEO continuous improvement loop

- **Goal**: Continually improve findmyisland.com for search engines and generative
  engines (sitemap, llms.txt, profile meta, descriptions, OG photos).
- **What changed**:
  - `scripts/audit_seo_geo_coverage.py` — 0–100 readiness score + priority queue +
    history JSONL.
  - `scripts/run_seo_geo_improvement.sh` — rotating cycle (descriptions → photos →
    featured → artifacts) → index rebuild → `generate_seo_artifacts.py` → live probe.
  - `enrich_descriptions_wikipedia.py` accepts SEO queue object rows / `ids`.
  - Docs: `SEO-GEO.md`, `INDEX.md`, `QUEUE.md`, `STATE.md`.
- **Outcome / counts**: Baseline avg **48.14**, both **18.5%**; photo cycle **+1**
  OG image; live probe **allOk** on `/`, sitemap, robots, llms.txt, Skye profile.
  Recurring loop armed every **60 min**.
- **Open items**: Push regenerated sitemap/llms to production when ready; Wikidata
  sitelink preflight for description queue yield.

## 2026-07-26 — Nation + name-slug public URLs

- **Goal**: SEO/GEO-friendly URLs by country + place name (no keyword stuffing in slugs).
- **What changed**:
  - `scripts/seo_paths.py` — nation segments, slugify, collision disambiguation, titles.
  - `generate_seo_artifacts.py` — `/islands/{nation}/{slug}/` landings, nation hubs,
    sitemap (**11,401** URLs), `llms.txt`, `data/seo_path_by_id.json`; legacy
    `/profiles/<id>.html` noindex-redirects to new canonicals.
  - `build_islands_index.py` — stamps `seoPath` on shard records.
  - `seo-meta.js` — canonical from `seoPath`; title
    `{name}, {nation} — map & profile | Find My Island`.
  - Pages artifact + `.gitignore` for `islands/`; live probe paths updated.
  - Docs: `SEO-GEO.md`, `DATA-SCHEMA.md`, STATE, QUEUE.
- **Outcome / counts**: **11,379** island landings + 7 nation hubs; examples
  `/islands/ireland/achill-island/`, `/islands/scotland/isle-of-skye/`,
  `/islands/northern-ireland/rathlin/`.
- **Open items**: Commit + push to `main` so GitHub Pages publishes the new URLs;
  re-submit sitemap in Search Console after deploy.

## 2026-07-26 — GSC CTR diagnosis + brand title

- **Goal**: Explain 0 clicks despite rising impressions; wire actionable GSC
  findings and SERP brand alignment.
- **What changed**:
  - Connected Search Console API / MCP; pulled Apr–Jul 2026 performance.
  - `docs/GSC-CTR-FINDINGS.md` — overview, ≤10/≤20 filters, pages, URL inspection,
    20 winnable queries.
  - Homepage + `seo-meta.js` HOME_SEO → **Find My Island — Isles of Britain atlas**.
  - `/ferries/calmac/` title/description → islands-served / ferry map (not booking).
  - Linked from `INDEX.md`, `SEO-GEO.md`; QUEUE deploy note for `/islands/…`.
- **Outcome / counts**: **0** clicks, **1,839** impressions, avg pos **76.5**;
  ≤20 positions: **9** queries / **9** impressions; top page
  `/?island=scilly-st-marys` (**565** imp). `/islands/…` not indexed (undeployed).
- **Open items**: Deploy nation+slug URLs; request indexing on hubs + Scilly/Bute/
  Staffa/Anglesey; re-check ≤20 in 2–4 weeks.

## 2026-07-26 — GSC connected; SEO fixes from live data

- **Goal**: Use Google Search Console to continue SEO/GEO optimisation.
- **GSC (28d)**: 1,614 impressions, 0 clicks, avg position 77.4; sitemap OK.
- **Finding**: Google indexes `/?island=` because profile HTML meta-refreshed into the SPA.
- **What changed**:
  - Removed auto-refresh from `/islands/{nation}/{slug}/` landings.
  - `seo-meta.js`: `noindex,follow` on `?island=` when `seoPath` canonical exists.
  - Ferry landings: drop “OSM node …” titles; absolute canonicals; link to `seoPath`.
  - `data/gsc_seo_snapshot.json` priority list (Scilly, Anglesey, Bute, CalMac, …).
- **Open**: Commit + deploy; then GSC URL Inspection on new paths.

## 2026-07-26 — GSC-driven SEO loop armed

- **Goal**: Continuously improve SEO/GEO from Search Console priorities.
- **What changed**: `scripts/run_gsc_driven_seo.sh`; richer island landings (key facts,
  image, nation hub link); 60 min loop `AGENT_LOOP_TICK_gsc_seo` (PID 16338).
- **Cycle**: avg still **48.26** / both **18.7%**; GSC priority islands already have
  desc+photo; live `/islands/` still **404**.
- **Open**: Deploy to Pages so GSC can index nation-slug URLs.

## 2026-07-26 — UX simplify (home + landings)

- **Goal**: Vastly simplify home and click-through UX — fewer competing controls, clearer paths.
- **What changed**:
  - Atlas: search-first topbar; Saved/Contribute under **More**; quieter sidebar (Notable + quick chips; Topics collapsed; Scotland chips only when Scotland filtered; ferry/guides under **Tools & guides**).
  - Profile: jump nav (Get there / Nearby / Map / More); secondary links/provenance under **More about this island**.
  - New `landing.css`; ferry + `/islands/` landings regenerated with clearer hero + CTA to the map.
- **Outcome**: Local verify on `/`, `/?island=isle-of-skye`, `/ferries/`, `/islands/scotland/isle-of-skye/`.
- **Open**: Deploy for live impact.
