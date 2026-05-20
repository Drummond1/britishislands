---
name: weekly-island-property-discovery
description: >-
  Runs the Isles of Britain weekly for-sale island discovery pass across obscure
  broker sites, merges verified listings, updates the registry and FOR-SALE-ISLANDS
  full list. Use when the user asks for property listing updates, weekly for-sale
  crawl, new islands on the market, or maintaining property_listings_verified.json.
---

# Weekly island property discovery

## When to run

- **At least once per week** (Monday morning recommended).
- After any manual broker research session.
- Before reporting for-sale counts to the user.

## Hard rules

1. Read `docs/STATE.md` — do not run if another write-pipeline is active.
2. **No Rightmove / Zoopla / OnTheMarket scrape** (`docs/ETHICS.md`).
3. Only broker pages that **name a specific island** in the listing.
4. Never invent URLs or atlas islands.
5. Append `docs/SESSION-LOG.md` when counts change.

## Full list (show the user every time)

| What | Path |
|------|------|
| **Human table (start here)** | [`docs/FOR-SALE-ISLANDS.md`](../../../docs/FOR-SALE-ISLANDS.md) |
| Machine registry + run history | `data/discovery/property_listings_registry.json` |
| Research manifest | `data/discovery/property_listings_verified.json` |
| Obscure broker catalogue | `data/discovery/property_obscure_sources.json` |
| Map filter | **For sale** on [findmyisland.com](https://www.findmyisland.com) |

## Weekly workflow

Copy and track:

```
- [ ] 1. Obscure broker research (4 parallel sub-agents)
- [ ] 2. Merge JSON → data/discovery/property_tier4_obscure_raw.json
- [ ] 3. Orchestrator + sync + registry
- [ ] 4. Update STATE.md counts + SESSION-LOG.md
- [ ] 5. Report: total islands, +N this run, link to FOR-SALE-ISLANDS.md
```

### Step 1 — Sub-agent research (parallel)

Launch **four** `generalPurpose` agents with `property_obscure_sources.json` regions:

1. **Scotland** — sites under `regions.scotland`
2. **Ireland + NI** — `regions.ireland_ni`
3. **England + Wales** — `regions.england_wales`
4. **Global specialists** — `regions.global_specialists`

Each agent returns a JSON array:

```json
{
  "islandName": "",
  "nation": "",
  "broker": "",
  "url": "https://...",
  "listingType": "whole_island|land|residential",
  "priceDisplay": "",
  "status": "for_sale",
  "notes": "",
  "pageNamesIsland": true
}
```

Exclude: sold/withdrawn, duplicate URLs already in `property_listings_verified.json`, homes on large inhabited islands without island name, islands not in atlas (note in `pendingAtlasIngest`).

### Step 2 — Consolidate raw file

Append new rows to `data/discovery/property_tier4_obscure_raw.json` (dedupe by URL).

### Step 3 — Apply pipeline

```bash
python3 scripts/run_property_discovery_weekly.py --apply-tier4
```

Or registry-only refresh:

```bash
python3 scripts/run_property_discovery_weekly.py --registry-only
```

### Step 4 — Docs

Update `docs/STATE.md` for-sale count. Append one `SESSION-LOG.md` block with `+N` new island names.

### Step 5 — User report template

```markdown
**For-sale islands:** {total} (was {previous})
**Added this run:** {names or "none"}
**Full list:** docs/FOR-SALE-ISLANDS.md
```

## GitHub Actions

Scheduled workflow `.github/workflows/main.yml` runs registry sync weekly.
Research still requires this skill in Cursor (sub-agents); CI refreshes counts/docs from committed data.

**If the workflow is not on GitHub yet** (Cursor push lacks `workflow` scope), follow
[`docs/GITHUB-WORKFLOW-WEEKLY-PROPERTY.md`](../../../docs/GITHUB-WORKFLOW-WEEKLY-PROPERTY.md)
— paste the YAML in **Actions → New workflow** once.

## Troubleshooting

| Issue | Action |
|-------|--------|
| URL check false negative (Strutt) | Desk-verify; keep apex URL; note in manifest |
| Low match confidence | Add alias in `scripts/match_property_listing_islands.py` |
| Island not in atlas | Add to `pendingAtlasIngest` in verified manifest; OSM discovery first |
| Stale listing | Remove row from verified manifest; re-run sync |

See [reference.md](reference.md) for tier definitions and prior counts.
