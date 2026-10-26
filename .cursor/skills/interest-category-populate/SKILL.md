---
name: interest-category-populate
description: >-
  Add or refresh an Isles of Britain interest filter (film, whisky, for sale,
  or a new category). Use when asked to populate an interest category, publish
  a new atlas filter chip, or fill interest_memberships with cited islands.
---

# Populate an interest category

Interest filters are an overlay. The island catalogue stays in `data/islands.json`.
Supabase holds the category spec and the cited memberships. The public map
reads `data/interest_index.json` and does not call the database.

## Hard rules

1. Read `docs/STATE.md` and `docs/ETHICS.md` first. Do not run a write-pipeline while another agent is writing `islands.json`.
2. Never invent an island. `island_id` must already exist in `data/islands_index.json`.
3. Every candidate row needs a `source_url`. Film, art, and music may use Wikipedia, Wikidata, Wikimedia Commons, and MusicBrainz (CC0). No IMDb, lyric sites, Spotify, Discogs, or other terms-restricted scrapes. A cited page still has to tie a specific work, band, or artist to that island.
4. For sale copies `data/discovery/property_listings_registry.json`. Do not scrape Rightmove, Zoopla, or OnTheMarket.
5. No private addresses, owner names, or street-level dwellings (`docs/ETHICS.md`).
6. Do not commit `.env.local`, `config.local.js`, or a service-role key.
7. A new published category appears as a chip from the index. Do not hard-code a new checkbox unless the populator needs a new source the verifier cannot check.

## Contract

1. Insert a `draft` category row (slug, label, blurb, populator name, acceptance rules).
2. Run or write that populator into `data/interest/candidates/{slug}.json` with a source URL on every row.
3. Run the shared verifier. Only `accepted` rows are eligible.
4. Set the category to `published` and rerun the export.
5. The chip appears on the next page load. No filter code change unless the populator needs a new source.

The draft example already in the table is `uninhabited-stay`. Its acceptance rule: population is not known to be above zero, and a public island-level place to stay is cited. No street addresses.

## Commands

From the repo root:

```bash
python3 scripts/interest_categories.py for-sale
python3 scripts/interest_categories.py whisky
python3 scripts/interest_categories.py culture
python3 scripts/interest_categories.py culture-open
python3 scripts/interest_categories.py wildlife
python3 scripts/interest_categories.py tidal
python3 scripts/interest_categories.py castles
python3 scripts/interest_categories.py books
python3 scripts/interest_categories.py publish
```

`publish` writes `data/interest_index.json` from accepted candidate rows and, when `SUPABASE_SERVICE_ROLE_KEY` is in the environment, upserts those rows. Without that key it writes `data/interest/memberships_sync.sql` for a service-role load. Anonymous clients can read published categories and accepted memberships only.

## Candidate row

```json
{
  "category_slug": "film-art-music",
  "island_id": "staffa",
  "facet": "artwork",
  "title": "Staffa, Fingal's Cave",
  "source_url": "https://en.wikipedia.org/wiki/Staffa,_Fingal%27s_Cave",
  "licence": "CC BY-SA 4.0",
  "evidence": "Wikipedia page names the work and the island.",
  "confidence": "high",
  "status": "accepted"
}
```

Facets in use: `film`, `artwork`, `music`, `distillery`, `silent`, `story`, `planned`, `listing`, `wildlife`, `tidal`, `castle`, `book`. Whisky stories also carry `subdivision` (`islay`, `hebrides`, `orkney`, `other`, `silent`, `story`, `planned`). Unique key is category + island + facet + title, so one island can carry several works or distilleries.

## Matching

- Resolve names with `name_key` in `scripts/ingest_sources.py`, plus coordinates when the source has them.
- Reject a point that only falls on Great Britain or Ireland, or on a skerry whose centroid happens to be nearer than the real island.
- For film, art, and music, fetch the source page and require both the work title and the island name. “Inspired by the region” is not enough.
- For whisky, the still has to be on the island. A working distillery, a silent still the source page places on the island, a still the page says is not yet producing, or a whisky story (a named wreck, film, novel, festival, or illicit stills the page places on the island) whose page names the island. Gin, a stalled plan, a brand whose still is somewhere else, and a closed site the page cannot locate are out. A non-English Wikipedia article is fine when it names the island and the still. A caption that merely mentions whisky is not evidence. Subdivisions are `islay`, `hebrides`, `orkney`, `other` for working stills, and the facets `silent`, `story`, and `planned`.
- For unusual wildlife, a Wikipedia, Wikidata, or Open Government Licence page must name the species and the island. The species is endemic, named for the island, or a principal stronghold. The picture is of the species. Do not store colony coordinates, nest counts, or advice on when to visit. Do not use the Seabird Monitoring Programme, RSPB reserve maps, iNaturalist, or GBIF occurrences.
- For books, the English Wikipedia article must set the book on that atlas island (a novel, memoir, autobiography, or story collection). "Inspired by", "based on", and "filmed on" do not count. The picture is an open-licence cover, title page, or illustration. A fair-use cover is left out. When the article has no open picture, use the island's own open-licence photograph and say it is a photograph of the island. The summary is the article's own sentences.

## After a publish

Append `docs/SESSION-LOG.md`. Note counts in `docs/STATE.md`. Leave draft categories out of the index until their status is `published`.
