# Property listings (for sale)

Outbound links from atlas islands to **third-party** estate agents and brokers.
We do **not** scrape Rightmove, Zoopla, or OnTheMarket (see `data/discovery/property_sources.json`).

## Sources (priority)

| Tier | Source | Status |
|------|--------|--------|
| MVP | [`data/curated_property_listings.json`](../data/curated_property_listings.json) | **Active** — maintainer-edited links |
| **Tier 3** | Multi-broker desk research + URL verify | **Active** — see below |
| Evaluate | [Homedata](https://homedata.co.uk/docs) live-listings API | Behind `HOMEDATA_API_KEY`; confirm Terms before baking into `islands.json` |
| Reject | Rightmove / Zoopla / OTM scrape | Blocked by [`ETHICS.md`](ETHICS.md) |

## Pipeline

```bash
# Research catalogue (no network)
python3 scripts/discover_property_apis.py

# Ingest curated (+ optional homedata cache) → staged cache
python3 scripts/ingest_property_listings.py --source all --commit

# Or curated only
python3 scripts/import_curated_property_listings.py

# Merge into islands.json
python3 scripts/apply_enrichments.py --apply --only property --force

# Slim index for filter chip
python3 scripts/build_islands_index.py
```

Artifacts:

- `data/cache_property_listings.json` — staged per-island payloads (gitignored when regenerated locally; commit after deliberate apply)
- `data/property_listings_ingestion_report.json` — match stats + unmatched audit
- `data/cache_homedata_listings.json` — raw Homedata responses (gitignored)

## Matching rules

1. **Curated** — explicit `islandId` → confidence `high`.
2. **Geometry** — listing lat/lng inside island polygon → `high`; within 200 m → `medium` + `offshore`.
3. **Name** — island name in title + island keyword → `medium` / `low` (flagged in report).

No full street addresses or owner names in shipped JSON ([`ETHICS.md`](ETHICS.md) §3).

## UI

- Topbar **For sale** filter (`hasPropertyListing` on index stub).
- Detail panel **On the market** — outbound links only.
- Chat synonyms: “for sale”, “on the market”, “property”, etc.

## Maintaining curated links

1. Add rows to `data/discovery/property_listings_verified.json` (research manifest) **or** edit `data/curated_property_listings.json` directly.
2. Each row must include a **broker URL that names the island** — no generic search pages.
3. Run:

```bash
python3 scripts/sync_curated_property_listings.py
```

That copies the verified manifest → curated file → ingest → `apply_enrichments` → `build_islands_index.py`.

The property cache is **authoritative**: any island that previously had `propertyListings[]` but is absent from the latest curated ingest will have those fields removed on apply.

Islands named on broker sites but **missing from** `islands.json` (e.g. some Vladi-only spellings) must be ingested via normal OSM discovery first — do not invent atlas rows.

Replace URLs when listings expire or sell; remove rows when pages go offline.

### Listing tiers (research manifest)

| Tier | Meaning | Examples |
|------|---------|----------|
| `whole_island` | Broker markets the island title or whole island estate | Shuna, Inchmarnock, Eilean Mòr (Loch Sunart), Vladi Ireland |
| `land` | Named island parcel / auction lot | Insh Island, Gasker, Creaghawaddy portion |
| `residential` | Named island but house/plot on an island (not whole island) | Soay croft, Boa Island cottage, Thames Ditton |

Rows in `pendingAtlasIngest` in the verified manifest are live broker pages for islands **not yet** in `islands.json` — ingest via OSM discovery first, then add to `verified`.

### Tier 3 — broker desk research (2026-05-19)

Systematic pass across specialist broker sites (Scotland, Ireland/NI, England/Wales
sub-agents): Galbraith, Strutt & Parker, Savills auctions, Bell Ingram, UKLAF, Vladi,
Private Islands Online, MyHome agent brochures (not aggregator scrape), Sibleys/Scilly
agents, Absolute Homes Thames eyots, Lisney, etc. No Rightmove/Zoopla.

```bash
# 1. Consolidate research → data/discovery/property_tier3_raw.json (array)
# 2. Match + verify + merge into verified manifest
python3 scripts/discover_property_tier3.py --apply
# 3. One-shot sync to map
python3 scripts/sync_curated_property_listings.py
```

Supporting scripts:

- `scripts/match_property_listing_islands.py` — name/alias/hint matching to `islands.json`
- `data/discovery/property_tier3_report.json` — accept/reject audit per run

**Counts (2026-05-19):** verified manifest **37** islands; **full list:**
[`docs/FOR-SALE-ISLANDS.md`](FOR-SALE-ISLANDS.md) (auto-generated).

### Tier 4+ — obscure brokers + weekly skill

Broader catalogue: `data/discovery/property_obscure_sources.json`.

```bash
# Weekly orchestrator (after sub-agent research → property_tier4_obscure_raw.json)
python3 scripts/run_property_discovery_weekly.py --apply-tier4

# Registry / human list only
python3 scripts/property_listings_registry.py --update --print
```

**Cursor skill:** `.cursor/skills/weekly-island-property-discovery/SKILL.md` — run at least
once per week; launches four regional sub-agents, then the scripts above.

**Tracking:**

| File | Purpose |
|------|---------|
| [`docs/FOR-SALE-ISLANDS.md`](FOR-SALE-ISLANDS.md) | **Full list** (table, counts, links) |
| `data/discovery/property_listings_registry.json` | Machine registry + run history |
| `data/for_sale_islands_summary.json` | Slim counts stub |

GitHub Actions: `.github/workflows/property-discovery-weekly.yml` (Mondays 06:00 UTC,
registry refresh; research still via Cursor skill). **Setup (paste workflow on GitHub):**
[`GITHUB-WORKFLOW-WEEKLY-PROPERTY.md`](GITHUB-WORKFLOW-WEEKLY-PROPERTY.md).
