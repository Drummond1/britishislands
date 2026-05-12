# QUEUE — pending follow-ups

> Append at the bottom. Mark items `[in flight]`, `[blocked]`, or move to
> `SESSION-LOG.md` once complete.
> Order is **priority top to bottom**. Reorder freely as priorities shift.

## P0 — currently in flight

- `scripts/enrich_images_v4.py` (PID 63436) — galleries pass, ETA ~90 min.
- `scripts/geocode_csv_skips.py` (PID 64221) — CSV-skip recovery, ETA ~30 min.
- ~~`scripts/compute_drive_times.py`~~ ✅ done 2026-05-11 20:25 — populated
  drive-times for **535 of 538 mainland terminals** (3 unreachable in
  OSRM's road graph). Now uses `curl` via `subprocess` (Python's bundled
  SSL stack failed on the OSRM demo server's TLS).

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
