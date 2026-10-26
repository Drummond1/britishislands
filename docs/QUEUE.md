# QUEUE — pending follow-ups

> Append at the bottom. Mark items `[in flight]`, `[blocked]`, or move to
> `SESSION-LOG.md` once complete.
> Order is **priority top to bottom**. Reorder freely as priorities shift.

## P1 — fact-check fixes (2026-10-26)

Read-only pass: [`fact-check/2026-10-26.md`](fact-check/2026-10-26.md).
Nothing in `islands.json` or `interest_index.json` was corrected.

- **Nation labels.** 156 islands carry the wrong nation because
  `nation_for()` in `scripts/fetch_islands.py` uses overlapping boxes.
  England’s Farnes and Northumberland coast are Scotland; Donegal and
  several Irish loughs are Northern Ireland; Davaar and the Sanda group
  are Ireland or Northern Ireland; Knightstone, Birnbeck, Steep Holm, and
  Langford Grounds are Wales. Do **not** bulk-apply
  `recompute_nation_admin1.py` until the boundary order is fixed. Then
  correct these 156 from the location report.
- **Not islands.** Greenisland (County Antrim town, filed as sea / England)
  and Island Magee (peninsula, filed as sea). Oxford is a city-centre pin
  filed as a river island, with Oxford Castle attached.
- **Photos.** Remove the confirmed wrong leads in the photo report,
  starting with La Boue (Palmarin, Senegal) and the Dunmanus / Illaunkearagh
  / Tanera mismatches. Drop film-art images that are flags, maps, museum
  logos, or a different subject.
- **Claims.** Unhook Airds Castle from Arran, Torksey Castle from Torksey
  Island, Calvay Castle from Calbhaigh, Cloughoughter from Stony Island,
  and Oxford Castle. Rewrite the Highland Park and Scapa “northernmost”
  lines. Fix the Alderney hedgehog sentence. Stop calling Baleshare and
  Mahee drying crossings. Remove sold listings for Insh Island and Gasker.
- **Measurements.** Hayling area 16.2 km² (about 27–30). Orkney Mainland
  581 km² includes the Churchill Barrier isles; curated still has 523.
  Summit corrections: Arranmore, Cape Clear, Bere, Inishmore, Tresco,
  Sùla Sgeir, Lundy. Census year on Skye, Lewis and Harris, Islay, and
  Arran says 2022 and stores the 2011 total.

## P1 — ferries stay hidden

Ferry guides, the ferry filter, the crossing planner, and ferry cards are off
the atlas until the routes are reliable enough to show. Do not link `/ferries/`
or render `renderFerries` route cards. A tidal causeway note can stay. The
generator in `scripts/generate_seo_artifacts.py` no longer emits ferry links.

## P1 — next interest category

Tidal islands is published locally (2026-10-25): **66** islands from the
Wikipedia [Tidal island](https://en.wikipedia.org/wiki/Tidal_island) article,
each with a note on where it joins and that the link floods. Not the 256-row
`tidal` subtype. No crossing times. Eleven names on that page were left out.
Supabase still needs `data/interest/memberships_sync.sql` and the tidal facet
migration `supabase/migrations/20261025190000_tidal_islands.sql` before the
remote memberships match this index.

Rare wildlife is published locally (2026-10-25, renamed 2026-10-26): **30** species on **23**
islands, **22** with a species photo. Eight have a paragraph and no usable
photo: Fair Isle wren, Guernsey vole, Skomer vole, Islay shrew, Lundy cabbage
flea beetle, Catacol whitebeam, *Salvelinus gracillimus*, and the extinct
Orkney charr. Do not add a picture that is not of the species. The wildlife
facet migration is also still unapplied.

The empty draft `uninhabited-stay` stays drafted and unstaffed until a cited
public place to stay exists (population not known to be above zero, no street
address, no owner name). It is not the next build.

Islands with Castles is published locally (2026-10-26): **89** islands, **113**
cited castles, **80** with a castle photo. Any atlas island with a castle on it,
including Mull, Skye, Anglesey, and Wight. Not the under-1 km² rule in
[`INTEREST-FILTER-IDEAS.md`](INTEREST-FILTER-IDEAS.md). Martello towers, brochs,
and country houses stay out. Supabase still needs
`data/interest/memberships_sync.sql` and
`supabase/migrations/20261026044000_island_castles.sql`.

Local traditions is published locally (2026-10-26): **23** islands, **35** cited
customs, each with a picture and a Wikipedia sentence that places the custom on
the island. Monastic pilgrimages, island breeds, and a bare legend stayed out.
Supabase still needs `data/interest/memberships_sync.sql` and
`supabase/migrations/20261026071000_local_traditions.sql`.

Unusual news is published locally (2026-10-26): **78** islands, **86** cited
stories, each with an original summary, a link to the report, and an
open-licence picture of the subject. Later batches came from local papers and from smaller Forth, Clyde, and loch islands. Supabase still needs
`data/interest/memberships_sync.sql` and
`supabase/migrations/20261026140000_unusual_news.sql`.

The next chip is lighthouses that have their own Wikipedia article. Do not build
the lighthouse chip from the 16 May 2026 OSM join (297 islands, 19,425 light
rows, including 603 lights on Great Britain). Follow
`.cursor/skills/interest-category-populate/SKILL.md`.

Published locally 2026-10-26: Film, art and music (111 islands, 916 cited
rows: 546 artworks, 297 music, 73 film). Whisky (**18** islands, **57** rows: 30 working stills,
13 silent stills, 12 stories, 2 planned), including Anglesey Môn distillery, Nun's Island in Galway, and the Loch Shiel wreck on Thorne Island. Subdivisions: Islay,
Hebrides, Orkney, Other isles, Silent stills, Stories, Planned. For sale
(42), Rare wildlife (23 islands, 30 species), Tidal islands (66),
Islands with Castles (89 islands, 113 castles),
Local traditions (23 islands, 35 customs), Unusual news (78 islands, 86 stories).
Artwork, whisky, and wildlife lead the list and the profile with one cited
picture and a short connection. Whisky also groups the rest of the profile
under those subdivisions. The chip row is one filter at a time (2026-10-26):
All islands, Islands with Castles, Rare wildlife, Whisky, then the rest.
Whisky regions and Film / Artwork / Music are not on the chip until more of
those islands have a picture. The profile still groups whisky by subdivision. Tidal islands lead with where the link goes, and
that it floods. This index is local. Supabase still has the earlier
memberships until `data/interest/memberships_sync.sql` is loaded, and the
whisky facet migration `supabase/migrations/20261025200000_whisky_subdivisions.sql`
is not applied.

## P1 — calm atlas UI deploy (2026-10-25)

- ~~**Deploy**~~ ✅ pushed to `main` (`atlas-redesign.css?v=calm-4`,
  `app.js?v=calm-4`, vendored Leaflet). Schema unchanged. Confirm the Pages
  workflow goes green.

## P0 — LLM counsel UX / reliability sprint (2026-08-16)

Counsel canvas: open beside chat from session “LLM Counsel — Broken areas & UX”.

- ~~**Day 1 — Trust**~~ ✅
- ~~**Day 2 — Correctness**~~ ✅
- ~~**Days 3–5 — Mobile + share**~~ ✅
- ~~**Later — history Back**~~ ✅ `pushState` on island open + `popstate` /
  toolbar Back uses `history.back()`.
- ~~**Later — per-island detail**~~ ✅ `data/details/{id}.json` from
  `build_islands_index.py` (11,351 files); `ensureIslandDetailLoaded` with
  nation-shard fallback; Pages stages `data/details/` + `vendor/` + `404.html`.
- ~~**UX polish**~~ ✅ default list cap 24 + Show all; verified-records orient
  line; hide Ask FAB on mobile (Ask tab only); map view paints list for sheet.

## P0 — continuous SEO/GEO (armed)

- **[in flight]** `bash scripts/arm_continuous_seo_geo.sh` →
  `run_continuous_seo_geo.sh --loop` (screen `iob-seo-geo`) — continuous
  strategy-aligned cycles (descriptions → photos → flagship → authority → GSC).
  Does **not** stop after 8 h. Stop: `touch data/.continuous_seo_geo.stop`.
  Lock: `data/.continuous_seo_geo.lock`. Strategy: `docs/SEO-GEO-STRATEGY.md`
  (no deindex). See `docs/SEO-GEO.md`.

## P0 — atlas redesign deploy (2026-07-28)

- ~~Product redesign~~ ✅ shipped `15eb7d24` to Pages (2026-07-30). Optional
  follow-up: true mobile draggable results bottom sheet.

## P0 — GSC indexing after `/islands/` deploy (2026-07-30)

- ~~**Deploy** smaller sitemap~~ ✅ live `2720d940` (2026-08-13): **1,622** island
  URLs in sitemap; `/profiles/` `index,follow`; geology prose.
- ~~GSC **Request indexing**~~ ✅ 2026-08-13: hubs (Scotland, England, Wales,
  Ireland) + Scilly St Mary's, Bute, Staffa, Anglesey. Hubs + Anglesey were
  **unknown to Google**; Scilly/Bute/Staffa were already indexed (requested
  again). Optional next: collections + Lewis & Harris / Lundy / St Kilda /
  Brownsea (`docs/GSC-INDEXING-REQUESTS.md`). Re-check Inspection in 3–7 days.
- **[blocked]** Cloudflare 301s — `data/legacy_redirects.csv` ready, but
  findmyisland.com is GitHub Pages (not proxied through Cloudflare). Needs CF
  zone + Global API Key/email, or DNS cutover first.

## P0 — overnight SEO/GEO (superseded by continuous)

- ~~`bash scripts/run_overnight_seo_geo.sh --loop`~~ ✅ finished 2026-07-28;
  replaced by continuous loop above. Overnight remains for time-boxed runs.

## P0 — GSC-driven SEO loop (armed 2026-07-26)

- **[in flight]** `scripts/run_gsc_driven_seo.sh` every **60 min** (sentinel
  `AGENT_LOOP_TICK_gsc_seo`). Uses `data/gsc_seo_snapshot.json` + GSC MCP on ticks.
  Deploy blocker cleared (hubs live); MCP still needs reconnect for inspect API.

## P0 — GSC + deploy (2026-07-26)

- ~~**blocked on deploy**~~ ✅ `/islands/…` live. Request indexing ✅ 2026-08-13
  (hubs + Scilly / Bute / Staffa / Anglesey; see GSC indexing P0 above).
- ~~GSC snapshot + meta-refresh fix + SPA noindex + CalMac title cleanup~~ ✅

## P0 — nation + name-slug URLs (2026-07-26)

- ~~**Canonical `/islands/{nation}/{slug}/` URLs**~~ ✅ Implemented and live.
  See `docs/GSC-CTR-FINDINGS.md` + `docs/GSC-INDEXING-REQUESTS.md`.

## P0 — SEO / GEO continuous loop (armed 2026-07-26)

- **[in flight] SEO/GEO improvement loop** — `scripts/run_seo_geo_improvement.sh`
  every **60 min**. Audit → rotate descriptions/photos/featured/artifacts →
  regenerate sitemap/`llms.txt`/profiles → live probe. Baseline avg score
  **~48**, both (desc+photo) **~18.5%**; target **50% both / avg ≥70**.
  Lock: `data/.seo_geo_improvement.lock`. See `docs/SEO-GEO.md`.

## P0 — learner UX (shipped 2026-06-12)

- ~~**Story-first browse** — `With stories` chip, sparse profile lede, default hide
  unconfirmed, Notable/Explore above list, profile key facts + related islands,
  chat starters.~~ ✅ See SESSION-LOG 2026-06-12 learner UX.
- **Description queue pass** — `python3 scripts/build_description_priority_queue.py`
  then `enrich_descriptions_wikipedia.py --queue-file data/description_priority_queue.json
  --limit 200` (first batch **+16**; **1,599** Wikidata-linked candidates remain).

## P0 — currently in flight

- **[in flight] Overnight discovery + naming (2026-07-26)** —
  `bash scripts/run_overnight_discovery_naming.sh --loop` (8 h). N7 GeoNames
  reverse already **−140** unnamed (4310→4170). Cycles: D5/D6 + N7–N10 + N3–N5
  rotate → verify → merge → apply gaps → index. Check morning:
  `data/.overnight_discovery_naming_state.json` + `logs/overnight-discovery-naming-*.log`.
- **[in flight] Priority naming push N1–N6** — `docs/NAMING-SOURCES.md`;
  `run_priority_naming_push.sh`. **N1–N10 implemented**; N1/N2 need API keys +
  data files. Baseline now **~4,170** unnamed after N7 confirm.
- **[in flight] Priority discovery push D1–D6** — `docs/DISCOVERY-PUSH.md`;
  `run_priority_discovery_push.sh` + overnight. **D6 seal haul-outs: 16** gap
  candidates; apply pass verified-but-matched (0 new entities this batch).
  Review via `discover_islands_pipeline.py` verifier → `site_update --apply`.
- **Priority photo push P1–P5** — `scripts/run_priority_photo_push.sh` (grid fix
  applied **2026-06-11**; first merge **+1**). Re-run with `PHOTO_PUSH_LIMIT=200`;
  add `FLICKR_API_KEY` to `.env.local` for P3. Continuous loop now includes P1–P5
  in 11-source rotation (`run_continuous_improvement.sh`); re-arm 45 min loop when ready.

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

## P1 — photo coverage (priority queue + v5)

- **Priority queue** — `python3 scripts/build_image_priority_queue.py` →
  `data/image_priority_queue.json` (curated → ferry → large area → Wikidata).
- **Lead images (v5)** — polite run with caches (DELAY_S=1.2s in script):
  `python3 scripts/enrich_images_v5.py --queue-file data/image_priority_queue.json`
  Resume with `--limit N` for batches; then `python3 scripts/build_islands_index.py`.
- **Gallery extras (v4)** — after leads exist:
  `python3 scripts/enrich_images_v4.py --limit 500` (Commons 429: reuse caches).
- **Featured strip** — `python3 scripts/build_featured_islands.py` →
  `data/featured_islands.json` (sidebar **Notable islands**; regenerate after atlas edits).

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
  boundaries (Natural Earth admin-1). **`scripts/recompute_nation_admin1.py`**
  is a **dry-run prototype** — current polygon order mis-tags NI/ROI and
  Scotland/England; do **not** bulk `--apply` until boundary / ordering rules
  are fixed (overrides list, Lough Neagh handling, etc.).
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

5. **Initial-payload performance**: ~~pre-cluster server-side at low zoom~~ **partial
   (2026-05-30)** — nation shards + deferred merge shipped; index carries `thumbUrl`.
   Remaining: zoom ≤6 grid cluster summaries if index stays >10 MiB.

## P2 — backlog (in rough order)

- **Gallery v4 / v5 photo enrichment resume** — UI **Has photo** filter is live
  (~3,345 / 7,041 on index `image` stub). Re-run `enrich_images_v4.py` /
  `enrich_images_v5.py` with `--cache` when Commons rate limits clear (see
  STATE overnight stall note) to raise atlas coverage; then rebuild index.

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
  - ~~LLM-augmented mode (opt-in).~~ Shipped 2026-10-26. Smart answers
    searches the atlas and reads full records (`chat-agent.js`). Local
    finder remains the default and the fallback.
  - ~~Add `near "London"` / `near "Glasgow"` proximity parsing.~~
    Shipped 2026-05-11 — 30-city UK/IE/Crown gazetteer + `within N km of …`
    explicit radii. See SESSION-LOG.
  - ~~Surface chatbot under a permalink (`?ask=…`).~~ Shipped 2026-05-11.
  - ~~Suggest didn't-resolve fallback.~~ Shipped 2026-10-26. An unknown
    place is named back, with a gazetteer suggestion (`obn` → Oban).
  - ~~Extend the gazetteer.~~ Shipped 2026-10-26. Tobermory, Portree,
    Stromness, Rothesay, Tarbert, Fishguard, Pembroke, Tralee, Larne,
    and the west-coast ferry piers (Kyle of Lochalsh, Scrabster, Doolin,
    Caernarfon, and the Islay, Mull, and Skye piers) are in `CHAT_PLACES`.
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
  already supports it. ~~Follow-up: optional lightbox / full-screen
  viewer for the hero image.~~ Shipped 2026-05-30.
- **Accommodation booking links**: ethical-only sources (B&B listings on
  visitscotland / visitwales / discoverni / failteireland with attribution);
  never affiliate or harvested without consent.
- **A11y audit**: ~~keyboard navigation through the virtualised list~~ (partial 2026-05-30:
  ↑/↓ + Enter on list); ~~Escape closes detail/filters~~; ~~`/` focuses search~~;
  ~~map live region + richer tooltips~~; remaining: full keyboard path to individual markers.

## P3 — open questions

- Should we treat the **Channel Islands** as their own nation rather than
  lumping under "Crown Dependency"? Currently 162 entries are grouped.
- Should we expose the **classification confidence** in the UI (e.g. a small
  badge for `tier-d`) or keep it hidden?
- Privacy: should we suppress islands with a single named resident? See
  `ETHICS.md` §5.

## P2 — Wikidata bbox v2 (2026-07-27)

- `discover_wikidata_gaps.py`'s country-statement scope is exhausted (0 gaps,
  see SESSION-LOG). Real remaining yield is Wikidata items **without** a
  `P17` country statement (bot-imported islet/skerry/tidal-island/lake-island
  stubs). A v2 needs: (a) explicit class allowlist (exclude reef/shoal/
  crannog/energy-island — confirmed noise), (b) per-`NATION_BOXES` tiled
  queries to stay under WDQS's cost limit (whole-bbox + class filter 502'd
  twice), (c) a spatial index (e.g. simple lat/lng grid bucket) for the match
  pass since candidate counts could be in the tens of thousands.

---

## How to use this file

- Add new items at the bottom of the relevant priority section.
- When you pick something up, prefix it with `[in flight]` and add your agent
  ID.
- When you finish, **move the item** (cut, not copy) to `SESSION-LOG.md` with
  a brief outcome line.
- If something is blocked, prefix `[blocked]` and add the blocker beneath it.

## P0 — SEO/GEO 90-day execution (rolling)

- ~~Batch 2: expand flagship editorial sections and improve CWV (LCP/CLS) on homepage + canonical island landings.~~ ✅ See SESSION-LOG 2026-07-28 batch 2.
- ~~Wire weekly GEO prompt benchmark run into reporting snapshots.~~ ✅ `scripts/run_geo_prompt_benchmark.py` + 50-prompt set.
- **[pending]** Deploy the eight `/collections/` interest guides (local, 2026-10-26) and request indexing for `/collections/` plus those guides. Search Console refresh token is expired (`mcp-google-search-console auth`). Do not put the fact-check’s false rows back onto the guides.
- **[pending]** Batch 3: request GSC indexing on hubs + top flagship `/islands/` URLs; fill first scored GEO benchmark run; deepen ferry hub last-verified dates.
- **[pending]** Homepage LCP follow-up: measure field CWV after font change; consider self-hosting DM Serif / Source Sans if third-party fonts remain a bottleneck.
