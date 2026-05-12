# Next session — ingestion action plan

This is the small, executable plan for the next session. It picks the five
highest-yield sources from `DISCOVERY-SOURCES.md` and gives each a concrete
"do this" recipe. Do not start anything else (photo re-enrichment, CSV
merge, OS-Maps detail view, frontend redesign) until the user signs off
on this plan.

## Summary of headline numbers

- Current baseline: **5,892 islands** in `data/islands.json`.
- Estimated net new islands reachable from the top 5 actions combined:
  **~3,750–6,000** (dominated by Wikidata; long-tail of crannogs and
  river eyots is the *interesting* part).
- Combined attribution / share-alike work: medium (CC0, CC-BY-4.0, OGL,
  CC BY-SA all in the mix — already handled by the existing provenance
  fields).
- Ethics risk: low across all five if the workflows below are followed.

## Action 1 — Wikidata spine (CC0; HIGHEST priority)

**Yield**: ~2,500–3,500 net new islands; canonical Q-ID join key for every
other source.

**Recipe**:

1. Run the SPARQL query against `https://query.wikidata.org/sparql`:
   ```sparql
   SELECT ?island ?islandLabel ?nativeLabel ?coord ?country ?area ?population WHERE {
     ?island wdt:P31/wdt:P279* wd:Q23442 ;
             wdt:P17 ?country ;
             wdt:P625 ?coord .
     FILTER(?country IN (wd:Q145, wd:Q27, wd:Q9676, wd:Q785, wd:Q3311985))
     OPTIONAL { ?island wdt:P1559 ?nativeLabel }
     OPTIONAL { ?island wdt:P2046 ?area }
     OPTIONAL { ?island wdt:P1082 ?population }
     SERVICE wikibase:label { bd:serviceParam wikibase:language "en,ga,gd,cy,gv,kw". }
   }
   ```
2. Paginate / split by country if timeouts occur.
3. Cache the response to `data/cache_wikidata_full.json`.
4. Join by Q-ID to our existing 1,302 entries. For every new Q-ID,
   create a candidate record and hold it for the dedup-by-proximity
   pass.
5. Dedup against existing entries by name AND <1 km proximity. Anything
   ambiguous → flag for manual review.

**Output**: ~3,000 new candidate islands; ~1,000 enrichments of existing
entries (Q-ID + native labels).

## Action 2 — River-islands pipeline structural fix (OGL; HIGH)

**Yield**: ~300–700 new English river islands + ~80–110 Thames eyots +
~100–300 Scottish loch islets + ~80–150 Shannon-system islands.

**Recipe**:

1. Download **Environment Agency Detailed River Network** (DRN) as
   GeoPackage from <https://environment.data.gov.uk/dataset/detailed-river-network>.
2. Download **EA Risk of Flooding from Rivers and Sea** (RoFRS) polygons
   for cross-validation.
3. Modify `scripts/classify_inland.py` to accept EA river *polygons* as
   parent water bodies (currently only treats OSM `natural=water`).
4. Re-run Tier A (inner-ring extraction) and Tier B (point-in-polygon
   containment) against the augmented water-body set.
5. Validate against the **Wikipedia "Islands in the River Thames"**
   ~150-row ground-truth (CC BY-SA 4.0).
6. Repeat for Scotland with **SEPA WFD water-body register** and for
   Ireland with **OPW NIFM/CFRAM**.

**Caveat**: this is engineering investment, not a flat-file ingest.
Budget 2–3 days.

## Action 3 — Crannog corpus (OGL + CC-BY-4.0; HIGH)

**Yield**: ~600–1,200 net new lake / loch islets — roughly *doubles* our
lake-island count.

**Recipe**:

1. **Historic Environment Scotland — Canmore**: use the API at
   `https://canmore.org.uk/api/` with `SITETYPE=CRANNOG` and
   `SITETYPE=ISLAND DWELLING`. Filter by `FORM=" "` to drop the
   submerged ones.
2. **NPWS / NMS Ireland**: download the Archaeological Survey from
   `https://data.gov.ie/dataset/national-monuments-service-archaeological-survey-of-ireland`,
   filter to class "Crannog" + "Lake settlement" + "Island dwelling".
3. **DfC NI NISMR**: download from
   `https://www.opendatani.gov.uk/dataset/northern-ireland-sites-and-monuments-record`,
   filter equivalently.
4. **Filter**: drop any record where the site type is recorded as
   submerged / underwater, and any record < ~5 m diameter (these are
   features, not islands).
5. **Round coordinates** to 100 m to honour Canmore/NMS publication
   granularity for sensitive sites — see `ETHICS.md` §4.
6. **Preserve names** verbatim — Gaelic forms like *Eilean Dòmhnuill*
   are canonical (see §2).
7. Schema flag: `subtype: "crannog"` + `heritage_designation: "scheduled monument"` where applicable.

## Action 4 — Cultural place-name authorities (CC-BY-4.0 + OGL; HIGH)

**Yield**: 0–30 net new entities, **but ~3,000+ authoritative non-English
name additions**. This is the cultural-integrity action.

**Recipe**:

1. **Schema migration**: add `name:ga`, `name:gd`, `name:cy`, `name:gv`,
   `name:kw` fields to `data/islands.json` entries and to the rendering
   layer (`app.js`). Display logic: show local form alongside English
   form in the details panel.
2. **Logainm.ie** (CC-BY-4.0): register for the Gaois Developer Hub at
   <https://docs.gaois.ie/en/data/logainm/v1.0/api>. Filter by category
   `OIL` (oileán / island). Pull ~2,000–3,000 records. Note: Logainm sits
   behind a Cloudflare bot-check, so use the official API, not scraping.
3. **Welsh Language Commissioner — Standard Welsh Place-names** (OGL):
   download from DataMapWales as CSV/GeoJSON.
4. **Ainmean-Àite na h-Alba**: no bulk feed. (a) Parse the Argyll & Bute
   Core Paths PDF and Highland Council Core Paths PDFs already publicly
   available. (b) Email AÀA (`info@ainmean-aite.scot`) with the list of
   Scottish islands we hold and request bulk Gàidhlig forms or a
   partnership. (c) Until then, ingest from PDFs.
5. **Akademi Kernewek — Cornish place-names**: scrape per parish from
   <https://www.akademikernewek.org.uk/place-names/> AFTER explicit
   licence confirmation by email.
6. **Comhairle nan Eilean Siar / Manx Place-Names**: hand-add canonical
   forms for the ~50 Hebridean + ~10 IoM offshore features.

## Action 5 — Statutory designation feeds (OGL + CC-BY-4.0; HIGH)

**Yield**: ~250–450 net new (small named stacks, Lough Erne + Strangford
islets, Connemara stacks, etc.)

**Recipe**:

1. **JNCC UK Protected Area Datasets** (OGL):
   <https://jncc.gov.uk/our-work/uk-protected-area-datasets-for-download>.
   Filter polygons that are wholly an island.
2. **NatureScot SSSI + NNR + SPA + SAC** (OGL): bulk downloads from
   <https://gis-downloads.nature.scot/>. The SSSI layer alone has
   ~100–200 island-named entries.
3. **NIEA / DAERA ASSI** (OGL): from
   <https://www.opendatani.gov.uk/dataset/areas-of-special-scientific-interest>.
4. **NPWS Ireland SAC/SPA/NHA/pNHA** (CC-BY-4.0): from
   <https://www.npws.ie/maps-and-data/designated-site-data/download-boundary-data>.
5. **Tailte Éireann Islands National 1m Map** (CC-BY-4.0): from
   <https://data.gov.ie/dataset/islands-national-1m-map-of-ireland1>.
6. For every polygon that is a single island, attempt name match
   against existing entries; missing → new candidate.
7. **Polygon adoption**: where these sources have *more accurate*
   geometry than our current OSM polygon, replace ours and credit them
   in `provenance`.

## Sequencing

The five actions are largely independent and could be done in any order,
but the dependency-minimising order is:

1. **Wikidata spine first** — gives every other action a Q-ID join key.
2. **Cultural-authority schema migration second** — once you have the
   Q-IDs, you have the SPARQL labels in 5+ languages for free; this
   migration just regularises that.
3. **Statutory designations third** — geometry corrections + small
   named stacks.
4. **Crannog corpus fourth** — large absolute yield, but high ethics
   filter work.
5. **River pipeline last** — engineering investment; the validation
   set (Wikipedia Thames eyots) is ready and waiting once the pipeline
   change lands.

## What NOT to do next session

- **No photo re-enrichment.** The current 793/5,892 image coverage will
  rise mechanically once Wikidata adds ~2,500 Q-IDs, but actively
  re-running `enrich_images.py` should wait for the new entries to
  arrive.
- **No OS Maps detail-view tile fetcher.** That requires a separate
  licence conversation with OS.
- **No frontend redesign.** The current UI handles the dataset growth
  via clustering + virtualisation.
- **No CSV import.** All five actions target structured / API sources.

## Ethics checklist (apply to all five actions)

Before any action ships:

- [ ] Provenance fields populated (`name`, `ref`, `url`, `licence`,
      `retrieved`, `attribution`).
- [ ] Cultural-authority spellings preserved verbatim.
- [ ] Republic of Ireland tagged `nation: "Ireland"`.
- [ ] Sensitive species data filtered out (Schedule 1 colonies → name
      only, no coordinates beyond ≥1 km grid).
- [ ] Sacred / burial sites → public-facing name + history only.
- [ ] Crannog coordinates → adopt 100 m rounding from Canmore / NMS.
- [ ] Non-photographic images filtered (`_looks_like_non_photo`
      heuristic).
- [ ] Hydrographic data → `not_for_navigation: true` flag.
- [ ] No per-dwelling addresses on inhabited islands.

If anything in this checklist fails, the merge does not land.
