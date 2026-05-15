# QUEUE — pending follow-ups

> Append at the bottom. Mark items `[in flight]`, `[blocked]`, or move to
> `SESSION-LOG.md` once complete.
> Order is **priority top to bottom**. Reorder freely as priorities shift.

## P0 — currently in flight

- _(none verified 2026-05-15)_ — prior `overnight_runner` / `enrich_images_v5`
  entries are **stale** (autonomous run stalled on Commons 429 per STATE).
  Re-check PIDs before trusting old queue rows.

## P0b — staged but not yet applied (enrichment caches missing locally)

Five enrichment ingest scripts are documented; **cache files are not present**
in this workspace yet (`data/cache_dobih.json`, etc.). Run each
`ingest_*.py --fetch --commit` before `bash scripts/apply_enrichments.sh`.

- **Hills** (DoBIH classifications) — `scripts/ingest_hills_dobih.py`
  → `data/cache_dobih.json`. Wikidata SPARQL covers ~854 hills with
  DoBIH IDs; full DoBIH CSV available at hills-database.co.uk under
  CC-BY 4.0 with email registration.
- **Lighthouses + beacons** — `scripts/ingest_lighthouses.py` →
  `data/cache_lighthouses.json`. OSM `man_made=lighthouse|beacon` over
  the UK/IE bbox, Wikidata cross-check for characteristic / built
  year / operator. `notForNavigation: true` mandatory.
- **RSPB reserves + wildlife colonies** — `scripts/ingest_wildlife_
  colonies.py` → `data/cache_wildlife.json`. Strictly island-level
  presence only (ETHICS §5).  25 curated overrides + Wikipedia text
  scan as low-confidence backup.
- **Geology** (BGS DigMapGB-625) — `scripts/ingest_geology_bgs.py`
  → `data/cache_bgs.json`. WMS GetFeatureInfo per centroid; GB only.
- **Census 2022** — `scripts/ingest_census_2022.py` → `data/
  cache_census2022.json`. Reads one CSV per nation; honours "don't
  overwrite newer with older". Sample NRS CSV staged with 12 islands.

Apply step (single atomic merge):

```
# After overnight finishes:
bash scripts/apply_enrichments.sh        # interactive
bash scripts/apply_enrichments.sh --yes  # unattended
```

The apply step takes one timestamped backup, re-reads after writing,
and runs smoke checks (Skye / Devenish / Achill / IoW / Eel Pie).
Rolls back automatically on any failure.

See [`docs/SCHEMA-ENRICHMENTS-2026-05-13.md`](SCHEMA-ENRICHMENTS-2026-05-13.md)
for the full schema proposal and [`docs/DATA-SOURCES.md`](DATA-SOURCES.md)
for source / licence / refresh-cadence detail.

## P0c — follow-ups after the staged enrichment lands

- **DoBIH CSV ingestion** — when the user signs up at
  hills-database.co.uk and drops the CSV at `data/dobih_v17_3.csv`,
  rerun `ingest_hills_dobih.py --dobih-csv … --commit` for the
  canonical hill list (12,000+ hills vs Wikidata's 854).
- **Census CSV completion** — NRS sample provided; add ONS, NISRA,
  CSO Ireland, IoM, and Channel Islands CSVs (per nation).
- **GSNI / GSI geology** — Northern Ireland (GSNI) and Republic of
  Ireland (GSI) publish equivalent open WMS; current BGS ingest only
  covers GB.  A follow-up `ingest_geology_gsni.py` /
  `ingest_geology_gsi.py` can mirror the BGS script.
- **Lighthouse photos** — once the lighthouses[] field group is
  applied, run an `enrich_images_lighthouses.py` pass (extension of
  `enrich_images_v5.py`) to attach 1–2 photos per lighthouse with
  `subject: "lighthouse"`.
- **UI rendering for the new field groups** — not shipped this
  session.  `docs/SCHEMA-ENRICHMENTS-2026-05-13.md` §7 documents
  where each new section would go and what CSS classes to introduce.

- (nothing else — all prior P0 jobs from earlier sessions have completed.)

## P0a — recently completed

- ~~Highest-point elevations (OSM peaks + Wikidata P2044)~~ ✅ applied
  2026-05-12 15:45 — `scripts/compute_island_highpoints.py` bulk-
  fetched 18,525 surveyed `natural=peak` nodes across the UK / Ireland
  bbox, spatial-indexed them, and assigned the highest peak inside
  each island's polygon. Wikidata P2044 cross-validates and falls back
  where no OSM peak is tagged. **Outcome**: 293 islands now have an
  elevation (up from 27); 239 at high confidence, 54 marked
  `estimate`. New schema fields: `highestPointM`, `highestPointName`,
  `highestPointSource`, `highestPointConfidence`. UI renders the
  source / confidence next to the figure. Audit at
  `data/highpoint_audit.json`.
- ~~Polygon-based island areas (≤ 2 % method, or N/A)~~ ✅ applied
  2026-05-12 15:10 — `scripts/compute_island_areas.py` resolves a
  polygon for each island (Step B: own OSM way / relation; Step C:
  Wikidata→OSM; Step A: hand-curated coastline lookup), then runs
  `pyproj.Geod.polygon_area_perimeter` for sub-0.01 % geodesic area.
  Wikidata P2046 cross-check with unit-error detection.
  **Outcome**: 5,581 high · 236 medium · 959 N/A on 6,776 islands
  (85.8 % coverage). New schema fields: `areaKm2`,
  `areaSource`, `areaConfidence`. UI updated to render confidence
  + source on the details panel. Audit at `data/area_audit.json`.
- ~~`scripts/enrich_images_v4.py`~~ ✅ done — galleries pass complete.
- ~~`scripts/geocode_csv_skips.py`~~ ✅ done — CSV-skip recovery complete.
- ~~`scripts/compute_drive_times.py`~~ ✅ done — drive-times for 535 of
  538 mainland terminals (3 unreachable in OSRM).
- ~~Phase 1 island reclassification~~ ✅ applied 2026-05-12 12:46 — 213
  islands re-typed (157 sea→lake, 56 sea→river).
- ~~Phase 1.5 positive-sea verification + `unknown` UI pill~~ ✅
  applied 2026-05-12 13:15 — 210 islands flipped `sea → unknown`;
  mainland test built offline by `scripts/build_land_polygons.py`.
- ~~Drain the 210 `unknown` queue~~ ✅ applied 2026-05-12 13:55 —
  Tier 4 proximity (76) + 134 manual overrides resolved 209 of 210.
  Final: `sea 5,049 · lake 1,329 · river 397 · unknown 1` (the last
  is a misclassified Barbican Estate building).

## P0b — categorisation hardening (next layers)

- **Subtype badges in the details panel.** We now have populated
  `subtype` for ~250 islands (`tidal-loch`, `estuary`, `reservoir`,
  `canal`, `pond`, `lagoon`, `oxbow`, `stream`, `crannog`). The UI
  shows it inside the type label string (`Crannog (lake)`) but
  doesn't render it as a distinct chip yet. Tiny visual job; promotes
  earlier work without any new pipeline.
- **Coastal-island nation audit.** The manual overrides flagged
  Knightstone Island (Weston-super-Mare) as wrongly tagged "Wales"
  when it's England; the underlying bbox-based `nation_for()` in
  `fetch_islands.py` is sloppy near the Severn / Solway / Foyle
  boundaries. Replace with a point-in-polygon test against admin
  boundaries (Natural Earth or OS Boundary-Line).
- **Drop dataset stowaways.** Two CSV-geocoded entries that aren't
  geographic islands (`csv-geocoded-Q26272407` Great Arthur House and
  `csv-geocoded-Q66227635` Thorney Island Community Primary School)
  should be excluded at the ingestion stage rather than carried in
  `islands.json`. Add a "is-this-actually-an-island?" sanity check
  to `geocode_csv_skips.py`.
- **OS NGD Features API integration (Phase 2).** Hit
  `https://api.os.uk/features/ngd/ofa/v1/collections/wat-fts-water-1`
  for each medium-confidence Phase-1 island and cross-check against the
  OS authoritative water polygon. Requires the user to enable "OS NGD
  Features API" on their existing OS DataHub project.
- **EA / NRW / SEPA / EPA WFD overlays (Phase 3).** For the residual
  estuary / transitional water disambiguation (Thames, Severn, Solway,
  Clyde, Foyle).

## P1 — next session

1. **Robust `areaKm2` fix at the source.** The one-shot patch at 15:25
   re-scaled 67 entries (`> 200 km²` and not curated / GB / IE). A handful
   of small entries in the 1–200 km² band are still wrong (e.g. Cardigan
   Island stored as 40 km², real ~0.24). Proper fix: rewrite the SPARQL
   in `scripts/ingest_sources.py` so it fetches the **unit Q-ID** alongside
   `wdt:P2046` and converts hectares (Q35852) / square metres (Q11573) to
   km² explicitly. Then re-run ingestion.

2. ~~**Geocode the 235 skipped CSV rows.**~~ **In flight 2026-05-11
   18:25** via `scripts/geocode_csv_skips.py` — Wikidata
   `wbsearchentities` + bbox filtering + P31-island-class tie-break.
   Successful adoptions tagged `source: csv-geocoded`. Ambiguous / no-hit
   cases logged for follow-up.

3. **CSV → discovery delta sweep**. Rerun `scripts/classify_inland.py
   --cache` to re-classify the 7 (now ≥7) new CSV-imported entries (most
   are sea groupings, but Rockall and possibly others should be re-
   classified). Re-run **after** `geocode_csv_skips.py` finishes adopting
   so the new `csv-geocoded` rows go through the classifier too.

4. **Northern Ireland / Ireland detail-view basemaps.** OS Leisure is GB
   only. Add OSNI (Northern Ireland) and OSi Discovery (Republic of
   Ireland) tile sources as fourth/fifth basemaps in the switcher when
   the island's nation matches. See `docs/OS-MAPS.md` future-work.

5. **Initial-payload performance**: pre-cluster server-side at low zoom
   levels so the initial network response is <1 MB instead of the 8 MB
   we currently ship. Two cheap approaches:
   - bucket islands into a 0.5°×0.5° grid at zoom ≤ 6 and ship cluster
     summaries; load detail rows on-demand by viewport; or
   - emit per-nation JSON files plus a tiny index, so the marker layer
     fetches only what's visible.

## P2 — backlog (in rough order)

- **Elevation follow-ups** (highest points shipped 2026-05-12):
  - 95.7 % of islands are `n/a` because they have no OSM-tagged peak.
    Phase 2: sample SRTM 1-arc-sec or OS Terrain 50 inside each
    polygon to derive a DEM-based highest-elevation cell. Would
    require fetching DEM tiles (large bundle, ~200 MB compressed for
    the British Isles).
  - 9 OSM-vs-WD mismatches > 5 m flagged in `highpoint_audit.json`
    for manual review (Arranmore Δ 265 m, Fair Isle Δ 54, Cape Clear
    Δ 53, Bere Island Δ 50, Inishmore Δ 52, Sùla Sgeir Δ 38, Tresco
    Δ 10). Most look like Wikidata pointing at a non-summit feature.
- **Area follow-ups** (polygon-based areas shipped 2026-05-12):
  - Review the 236 `medium`-confidence entries from
    `data/area_audit.json` and either confirm OSM, hand-curate, or
    set N/A. Top candidates: Hayling Island (Δ 85 % — boundary
    definition issue), Bryher (Δ 11 % — tide line), Eilean Mhealasta
    (Δ 9194 % — likely a WD hectare-tag bug just outside our
    detection window).
  - Re-run `compute_island_areas.py --fetch-wd` later: two batches
    were rate-limited (~166 Q-IDs missed) so the
    Wikidata-cross-validated set is 340 instead of ~500.
  - For the 959 N/A entries, consider a Step E: `place=island`
    within 100 m for csv-geocoded entries (might unlock ~25 more).
- **Ferry-routes follow-ups** (core feature shipped 2026-05-11 — see
  [`FERRIES.md`](FERRIES.md) and SESSION-LOG):
  - Surface a per-operator "data freshness" page that links to the
    stale report and the `lastVerified` date per route, with a one-
    click "kick the refresh job" button (when running with GitHub
    Actions).
  - Light per-operator scrapers for the ten biggest `manual` operators
    (Wightlink, Red Funnel, Hovertravel, IoM Steam Packet, Condor,
    Aran, Cape Clear, Tory, Scillonian, Lundy) so monthly refreshes
    pick up timetable changes without a human in the loop. Each
    operator needs its own ToS read-through first; document any
    decisions in `data/operators.json -> disclosure`.
  - Vessel-Q-ID enrichment via Wikidata `wbsearchentities` (we left
    `vesselWikidata: []` empty for the GTFS routes — a one-off pass
    can fill these and unlock "typically operated by MV …" hover cards).
  - Itinerary builder UI: today it's permalink-only (`?trip=startId,endId`);
    add a proper two-field form ("From island", "To island") that
    builds the permalink and surfaces total travel time / operator
    handovers.
  - Accommodation linkage: when the target island has no on-island
    accommodation, recommend stays near the **mainland terminal**.
    Requires the future `data/accommodation.json`.
- **Chatbot improvements**:
  - LLM-augmented mode (opt-in): use a local API key to refine parsing and
    compose richer responses for free-form queries. Keep local fallback.
  - ~~Add `near "London"` / `near "Glasgow"` proximity parsing.~~
    Shipped 2026-05-11 — 30-city UK/IE/Crown gazetteer + `within N km of …`
    explicit radii. See SESSION-LOG.
  - ~~Surface chatbot under a permalink (`?ask=…`).~~ Shipped 2026-05-11.
  - **Suggest didn't-resolve fallback**: when `near nowhereville` is typed,
    the bot currently just ignores the proximity intent silently. Better:
    surface a "Couldn't find that place — try Oban / Mallaig / …" hint.
  - **Extend the gazetteer**: 30 entries today; add Tobermory, Portree,
    Stromness, Rothesay, Tarbert, Fishguard, Pembroke Dock, Tralee,
    Larne, etc. for finer-grained proximity.
- ~~**Cultural-names workstream** (Gaelic / Welsh / Irish / Manx / Cornish /
  Scots)~~. Shipped 2026-05-11 via `scripts/enrich_names.py` (Wikidata
  `wbgetentities labels`, 8 target languages, 184 islands enriched on
  first run). Long-tail follow-ups: small islets without Q-IDs (use OSM
  `name:gd` / `name:cy` / `name:ga` tags via Overpass); also harvest
  **Norse / Scots-place-name** etymology summaries for a future
  "etymology" badge on the details panel.
- **Statutory designations** (NNRs, SSSIs, RAMSAR, etc.) — Natural England,
  NatureScot, NRW, NIEA, NPWS feeds. Adds a `designations[]` array.
- **River pipeline expansion** beyond the Thames cache — Tay, Severn, Bann,
  Shannon, etc.
- **Crannog deep-dive** — historic record IDs from Canmore + NMS for proper
  attribution; current 2 KB cache is a stub.
- ~~**Search**: fuzzy/typeahead search in the sidebar.~~ Shipped
  2026-05-11. Scored matcher (`_scoreIsland`) with diacritic-insensitive
  prefix / word-start / substring / subsequence scoring. Now sorts by
  score when a query is active; alphabetic when empty.
- ~~**Per-island additional images**: extend `images[]` beyond the lead
  photo using Commons category traversal; UI gallery in the details
  panel.~~ Shipped 2026-05-11. Extras live in `data/galleries.json`
  (separate file, lazy-fetched on first island click); UI thumb-strip
  already supports it. Follow-up: optional lightbox / full-screen
  viewer for the hero image.
- **Accommodation booking links**: ethical-only sources (B&B listings on
  visitscotland / visitwales / discoverni / failteireland with attribution);
  never affiliate or harvested without consent.
- **A11y audit**: keyboard navigation through the virtualised list, ARIA labels
  on the map.

## P3 — open questions

- Should we treat the **Channel Islands** as their own nation rather than
  lumping under "Crown Dependency"? Currently 162 entries are grouped.
- Should we expose the **classification confidence** in the UI (e.g. a small
  badge for `tier-d`) or keep it hidden?
- Privacy: should we suppress islands with a single named resident? See
  `ETHICS.md` §5.

---

## How to use this file

- Add new items at the bottom of the relevant priority section.
- When you pick something up, prefix it with `[in flight]` and add your agent
  ID.
- When you finish, **move the item** (cut, not copy) to `SESSION-LOG.md` with
  a brief outcome line.
- If something is blocked, prefix `[blocked]` and add the blocker beneath it.
