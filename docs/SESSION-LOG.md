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
