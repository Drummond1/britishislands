# Discovery pipeline — six-agent workflow

This document describes the review-first island discovery pipeline that
finds UK / Ireland remit landmasses missing from `data/islands.json`,
verifies them against open sources, attaches licence-safe photos, and
merges only after human review.

## Agents

| Agent | Module | Purpose |
| --- | --- | --- |
| Map Scanner | `scripts/discovery/map_scanner.py` | Scan OSM for named islands, islets, rocks, and seamarks inside the project bbox; diff against the canonical dataset. |
| Catalog Scanner | `scripts/discovery/catalog_scanner.py` | Merge map-scan candidates with Wikidata/Wikipedia list harvest, DoBIH island crosswalk, **Marine Regions gazetteer** (CC-BY; lat/long grid often yields zero strict `Island` rows in the UK bbox — see cache), optional `data/raw/os_opennames.csv`. Env: `DISCOVERY_SKIP_MARINE`, `DISCOVERY_REFRESH_MARINE`. |
| Source Verification | `scripts/discovery/source_verifier.py` | Confirm each candidate is a real named feature using OSM, Wikidata, and Wikipedia links. Reject entries without a reliable source. |
| Photo Finder | `scripts/discovery/photo_finder.py` | Attach Wikidata P18 or Wikipedia pageimage photos with Commons licence metadata. Skip unclear licences. |
| Data Enrichment | `scripts/discovery/enricher.py` | Build schema-shaped records, aliases, provenance, and `discovery.needsReview` flags. |
| Site Update | `scripts/discovery/site_update.py` | Dry-run by default; gated merge with fuzzy name + coordinate dedup. Never overwrites curated rows without a review note. |

Orchestrator: `scripts/discover_islands_pipeline.py`.

## Artifacts

| Stage | Output |
| --- | --- |
| Map Scanner | `data/discovery/candidates_scan.json`, cache `data/cache_discovery_osm.json` |
| Catalog Scanner | `data/discovery/candidates_catalog.json`; caches `data/cache_discovery_wikipedia_lists.json`, `data/cache_discovery_dobih_islands.json`, `data/cache_discovery_marine_regions.json`; optional `data/raw/os_opennames.csv` |
| Source Verification | `data/discovery/verification.json`, cache `data/cache_discovery_wikidata.json` |
| Photo Finder | `data/discovery/photos.json`, cache `data/cache_discovery_commons.json` |
| Data Enrichment | `data/discovery/enrichment.json` |
| Site Update | `data/discovery/review_report.json` (+ timestamped `data/islands.json.before-discovery-*` backup on `--apply`) |

## How to run

Full pipeline (dry-run merge at the end):

```bash
python3 scripts/discover_islands_pipeline.py
```

Single stage:

```bash
python3 scripts/discover_islands_pipeline.py --stage=map_scanner
python3 scripts/discover_islands_pipeline.py --stage=catalog_scanner
python3 scripts/discover_islands_pipeline.py --stage=source_verifier
python3 scripts/discover_islands_pipeline.py --stage=photo_finder
python3 scripts/discover_islands_pipeline.py --stage=enricher
python3 scripts/discover_islands_pipeline.py --stage=site_update
```

Useful flags:

- `--limit=N` — cap records per stage while testing.
- `--no-cache` — refresh the Overpass response for map scanning.
- `--include-uncertain` — **site_update only:** merge every candidate into an existing island when OSM/Wikidata/name+proximity matches; then insert remaining review-flagged rows as **new** islands with `classification.confidence: "unconfirmed"` (see `DATA-SCHEMA.md`). Without this flag, those rows stay in `enrichment.json` only.
- `--apply` — write new islands into `data/islands.json` (only on `site_update`).
- **Catalog / Marine Regions:** `DISCOVERY_SKIP_MARINE=1` skips the ~55-cell Marine Regions gazetteer fetch (useful for CI). `DISCOVERY_REFRESH_MARINE=1` ignores `data/cache_discovery_marine_regions.json` and re-downloads.

Before any `--apply` run, read `docs/STATE.md` **Currently running** and
do not mutate `islands.json` while another write-pipeline is active.

## Ethics and accuracy rules

- Never invent names or photos.
- Every surviving candidate keeps at least one open-licence source URL.
- Photos require a recognised Commons / Wikipedia licence string.
- Curated islands are never replaced; cross-references may be merged only.
- Uncertain rows stay in the enrichment artifact until a human approves them.

## Related docs

- [`DISCOVERY-SOURCES.md`](DISCOVERY-SOURCES.md) — evaluated external catalogues.
- [`ETHICS.md`](ETHICS.md) — licensing and attribution guardrails.
- [`DATA-SCHEMA.md`](DATA-SCHEMA.md) — island record shape.
- [`PIPELINE.md`](PIPELINE.md) — canonical rebuild path for `islands.json`.
