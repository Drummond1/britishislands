# Property discovery reference

## Tiers

| Tier | Source file | Script |
|------|-------------|--------|
| MVP | `curated_property_listings.json` | manual |
| 3 | `property_tier3_raw.json` | `discover_property_tier3.py` |
| 4+ | `property_tier4_obscure_raw.json` | `discover_property_tier3.py --raw … --tier-label Tier 4` |

## Count milestones

| Date | Islands with listings |
|------|----------------------:|
| 2026-05-19 (Tier 3) | 29 |
| 2026-05-19 (Tier 4 + registry) | 37 |

## Pending atlas ingest (examples)

Live broker pages for islands **not yet** in `islands.json`:

- Inishskehan Island (Vladi)
- Annaghavane Island (Lisney Connemara Isles)
- Inis Saimer (PIO)
- Harbour Island / Eilean dá Mhéinn (Savills Crinan)
- Cameron Island (Lough Derg)
- Dumsey Eyot (Thames)

Add via OSM discovery, then re-run weekly apply.
