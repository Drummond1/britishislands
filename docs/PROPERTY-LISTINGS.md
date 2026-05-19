# Property listings (for sale)

Outbound links from atlas islands to **third-party** estate agents and brokers.
We do **not** scrape Rightmove, Zoopla, or OnTheMarket (see `data/discovery/property_sources.json`).

## Sources (priority)

| Tier | Source | Status |
|------|--------|--------|
| MVP | [`data/curated_property_listings.json`](../data/curated_property_listings.json) | **Active** — maintainer-edited links |
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
