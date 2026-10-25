# Discovery push — new island gap harvesters

Complements [`DISCOVERY-SOURCES.md`](DISCOVERY-SOURCES.md) (catalogue) and
[`DISCOVERY-PIPELINE.md`](DISCOVERY-PIPELINE.md) (six-stage review-first merge).

These scripts find **named features not yet in `islands.json`** and write
reviewable candidate JSON under `data/discovery/` — they do **not** auto-merge
into the atlas.

Orchestrator: `scripts/run_priority_discovery_push.sh`

---

## Implemented harvesters

| ID | # | Source | Script | Output |
|----|---|--------|--------|--------|
| **D1** | 11 | GeoNames ISL/ISLT spatial gaps | `discover_geonames_gaps.py` | `candidates_geonames.json` |
| **D2** | 76 | Wikipedia list `{{coord}}` gaps | `discover_wikipedia_coord_lists.py` | `candidates_wikipedia_coords.json` |
| **D3** | — | OSM map scanner (named islands / seamark rocks) | `discover_islands_pipeline.py --stage=map_scanner` | `candidates_scan.json` |
| **D4** | — | Catalog scanner (Wikidata lists, DoBIH, Open Names) | `discover_islands_pipeline.py --stage=catalog_scanner` | `candidates_catalog.json` |
| **D5** | — | OSM free-text / lexicon sweep | `discover_osm_freetext.py` | `candidates_osm_freetext.json` |
| **D6** | — | SSI 2014/185 seal haul-out schedule | `discover_seal_haulouts.py` | `candidates_seal_haulouts.json` |
| **D7** | 5 | Wikidata SPARQL island gap (by country statement) | `discover_wikidata_gaps.py` | `candidates_wikidata.json` |

Overnight loop: `scripts/run_overnight_discovery_naming.sh --loop` (8 h default).

### D1 — GeoNames

- Downloads `GB.zip` + `IE.zip` into `data/raw/geonames_{GB,IE}.txt` on first run.
- Feature class `T`, codes `ISL` / `ISLT`.
- Gap = no atlas island within **1 km** and no fuzzy name match.
- **First run (2026-06-11):** 3,656 GeoNames island points → **378** gap candidates (after name-key dedupe).

### D2 — Wikipedia coordinates

- Parses `[[Name]] … {{coord|…}}` on 21 curated list articles.
- Respects Wikipedia rate limits (cache: `cache_discovery_wiki_coords.json`).
- **First run:** 95 coord hits (Ireland list); **10** gap candidates (429 on later lists — re-run with delay).

### D7 — Wikidata SPARQL

- Country-statement (`wdt:P17`) query over the island class tree
  (`wdt:P31/wdt:P279*` island, covers islet/skerry/tidal island/holm
  subclasses) for UK, Ireland, Isle of Man, Jersey, Guernsey.
- Gap = no Q-ID / name+proximity / loose ≤1 km match against the atlas.
- **First run (2026-07-27):** 2,644 in-remit Wikidata island items → **0**
  gap candidates — this specific query was already fully harvested via
  `scripts/ingest_sources.py --only=wikidata` in an earlier session.
- A whole-bbox variant without the country-statement requirement (to catch
  items lacking `P17`) is dominated by non-island noise (reef/shoal/crannog
  bulk imports) and 502s WDQS when combined with a class allowlist — a
  tiled, class-restricted v2 is the real remaining opportunity here (see
  SESSION-LOG 2026-07-27).

---

## Runbook

```bash
# Full discovery pass (candidates only)
bash scripts/run_priority_discovery_push.sh

# Individual harvesters
python3 scripts/discover_geonames_gaps.py
python3 scripts/discover_wikipedia_coord_lists.py
python3 scripts/discover_islands_pipeline.py --stage=map_scanner
python3 scripts/discover_islands_pipeline.py --stage=catalog_scanner

# Review → merge (existing pipeline)
python3 scripts/discover_islands_pipeline.py --stage=source_verifier
python3 scripts/discover_islands_pipeline.py --stage=enricher
python3 scripts/discover_islands_pipeline.py --stage=site_update --apply
```

---

## Next discovery harvesters (planned)

| # | Source | Notes |
|---|--------|-------|
| 13 | Natural Earth minor islands | Polygon overlap |
| 10 | OpenSeaMap `seamark:name` | Extend map_scanner filter |
| 22–23 | Tailte Éireann WFS / 1m islands | Ireland authoritative polygons |
| 91–93 | SSSI / NPWS site names | OGL / CC-BY designation layers |
| 5 | Wikidata SPARQL island gap | Highest yield per DISCOVERY-SOURCES action plan |
