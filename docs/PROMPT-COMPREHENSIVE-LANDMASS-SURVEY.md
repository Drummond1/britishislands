# Comprehensive landmass survey — multi-agent operational prompt

Use this as the **single briefing** when orchestrating parallel agents (human or Cursor) on a full remit pass. It aligns with **AGENTS.md** (~50 miles of UK + Ireland, sea + inland) and **`scripts/discovery/common.py`** (`UK_BBOX`, `in_remit`).

---

## Succinct prompt (copy/paste)

```
MISSION — Isles of Britain landmass sweep

GEOGRAPHY: Within project remit only — bounding box 49.0–61.5°N, 10.5°W–2.5°E,
excluding points that fail `in_remit()` (non UK/IE/Crown-Dependency boxes).
This matches “~50 miles of UK & Ireland” + inland islands; do not expand scope
without updating AGENTS.md and STATE.md.

DETECTION TARGET: Catalogue every landmass ≥ 3 m × 3 m that we can SOURCE
from open / licensed pipelines — see REALITY CHECK below. Do not promise
wall-to-wall 3 m resolution from one global dataset; use OSM + official
gazetteers + grid-assisted discovery to approach completeness within API limits.

AGENT TEAM (run in parallel where safe; one writer for islands.json):
1) Grid cartographer — tile the bbox; ensure full coverage; output tile manifest.
2) OSM harvester — Overpass per tile: natural=coastline/island/islet, place=island|islet,
   maritime rocks where tagged; merge with map_scanner diff vs islands.json.
3) Inland extension — run / extend classify_inland tier logic for inner rings + PiP.
4) Gazetteer linker — OS Open Names (if staged), Wikidata SPARQL, Wikipedia lists,
   Marine Regions (where island-type features exist), DoBIH crosswalk, Tailte/NRS
   only where bulk paths exist and licence is clear.
5) Name resolver — for each candidate without name: Nominatim reverse (rate-limited),
   nearest named OSM feature, Wikidata by coordinates; require provenance per ETHICS.
6) Merger / QA — dedupe by osm id / wikidata / name+1km; never delete curated rows;
   apply via discover_islands_pipeline site_update or fetch_islands merge;
   unconfirmed → classification.confidence "unconfirmed" + reviewHint.

ARTIFACTS: Regenerate data/survey/landmass_ledger.json via
scripts/survey_landmass_ledger.py (reads islands.json + verification.json +
optional discovery reports). Columns align with: candidate_id, lat, lng,
source_layer, named (y/n), proposed_name, name_confidence (high|medium|low|none),
name_sources[], merged_to_islands_json (y/n), island_id, outstanding_reason.
See data/survey/README.md.

CLOSURE REPORT: Counts — added_to_atlas, merged_enrichment_only, rejected_duplicate,
outstanding_named_low_confidence, outstanding_unnamed, outstanding_offline_review.
Append one block to SESSION-LOG.md; update STATE.md counts.

HARD RULES: ETHICS.md + DATA-SCHEMA.md; no island without source + osmId|wikidata|
curated ref; no images without licence in images[]; coordinate writes via STATE
“Currently running”.
```

---

## Reality check — “3 m × 3 m”

| Intent | What the project can actually do |
|--------|----------------------------------|
| **Policy minimum** | Treat **≥ ~3 m extent** as “in scope” for *inclusion* if a source records the feature. |
| **National wall-to-wall detection at 3 m** | **Not feasible** from public APIs alone: no single open layer lists every sub-metre rock around GB+IE without commercial hydrographic or aerial contracts. |
| **Practical proxy** | **OpenStreetMap** geometry + tags; **official gazetteers** (points/polygons where open); optional **dense grid** only to *discover* OSM gaps (new surveys), not to invent unnamed polygons. |

Phrase outcomes honestly in the report: **“all sourced landmasses at ≥3 m meeting inclusion rules”**, not “every rock in the sea.”

---

## Agent responsibilities (expanded)

| Agent | Inputs | Outputs |
|-------|--------|---------|
| **Grid cartographer** | `UK_BBOX`, tile size (e.g. 0.25°–0.5°) | `survey/tiles_manifest.json`, coverage % |
| **OSM harvester** | Tiles, Overpass cache (`--cache`) | `candidates_scan.json` delta, audit log |
| **Inland extension** | Water multipolygons, existing classifier | Inland candidates + `parentWaterBody` |
| **Gazetteer linker** | Wikidata, lists, optional CSV | `candidates_catalog.json` rows |
| **Name resolver** | Candidates missing `name` | Ledger rows with `name_confidence` + URLs |
| **Merger / QA** | Ledger + `VALIDATION.md` spot checks | `islands.json` via pipeline; `review_report.json` |

---

## Naming certainty → schema

| Level | Criteria | `islands.json` |
|-------|----------|----------------|
| **high** | Matches OSM `name` or Wikidata label + same geometry ref | Normal `classification.confidence` |
| **medium** | Gazetteer or reverse-geocode agrees; minor spelling variants | `medium` + source list |
| **low** | One weak source or proximity-only name | `low` or `unconfirmed` + `reviewHint` |
| **none** | No name; keep for map as unnamed feature if policy allows | placeholder name policy OR exclude until named — **recommend** `unconfirmed` + `reviewHint: "unnamed feature; needs survey"` |

Follow **`docs/DATA-SCHEMA.md`**; use existing **`unconfirmed`** for “come back later.”

---

## End-of-run report (template)

```text
LANDMASS SURVEY — closure YYYY-MM-DD
Remit: UK_BBOX + in_remit
Detection sources: [OSM tiles … | inland tier … | gazetteers …]
Added to islands.json: N
Merged into existing (sources only): M
Outstanding — low confidence name: A
Outstanding — unnamed: B
Outstanding — manual review: C
Validation spot-check: [pass / issues]
Next: [e.g. OS Open Names CSV, marine chart cross-check]
```

---

## Related repo paths

- Survey ledger (local, no network): `scripts/survey_landmass_ledger.py` → `data/survey/landmass_ledger.json`, `survey_summary.json`
- Orchestrator: `scripts/discover_islands_pipeline.py`
- Bbox / remit: `scripts/discovery/common.py` (`UK_BBOX`, `in_remit`)
- Inland methodology: `docs/METHODOLOGY-INLAND.md`
- Ethics: `docs/ETHICS.md`

---

## Document control

| | |
|--|--|
| **Created** | 2026-05-15 |
| **Purpose** | Reusable multi-agent briefing for full remit sweeps |
