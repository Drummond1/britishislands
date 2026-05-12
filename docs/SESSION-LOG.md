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

## 2026-05-10 — Initial prototype

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
