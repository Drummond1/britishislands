# Data schema — island record

Canonical structure of one entry in `data/islands.json`. **Update this file
whenever the schema changes**, in the same diff as the code change.

## At a glance

`data/islands.json` is a JSON array of island records:

```json
[
  { /* one island */ },
  { /* another */ }
]
```

There is no top-level metadata wrapper. Total size is in
[`STATE.md`](STATE.md).

## Full record (example)

```json
{
  "id": "isle-of-skye",
  "name": "Isle of Skye",
  "nation": "Scotland",
  "type": "sea",
  "subtype": null,
  "tidal": null,
  "archipelago": "Inner Hebrides",
  "lat": 57.273,
  "lng": -6.215,
  "areaKm2": 1656,
  "population": 10008,
  "highestPointM": 992,
  "highestPointName": "Sgùrr Alasdair",

  "shortDescription": "The largest island of the Inner Hebrides …",
  "history": "Settled since the Mesolithic …",
  "geography": "Dominated by the Cuillin and Trotternish ridges …",
  "transport": "Skye Bridge from Kyle of Lochalsh; CalMac ferries from Mallaig …",
  "accommodation": "Hotels in Portree; many B&Bs island-wide …",

  "wikipedia": "https://en.wikipedia.org/wiki/Isle_of_Skye",
  "wikidata": "Q80967",

  "image": "https://upload.wikimedia.org/.../640px-Skye.jpg",
  "images": [
    {
      "url": "https://upload.wikimedia.org/.../640px-Skye.jpg",
      "fullUrl": "https://upload.wikimedia.org/.../1600px-Skye.jpg",
      "caption": "Cuillin from Elgol",
      "source": "wikidata",
      "sourceRef": "Q80967",
      "sourcePageUrl": "https://commons.wikimedia.org/wiki/File:Skye.jpg",
      "license": "CC-BY-SA-4.0",
      "attribution": "Photo by … via Wikimedia Commons",
      "primary": true
    }
  ],

  "tags": ["mountains", "ferry", "bridge"],

  "source": "curated",
  "osmType": "relation",
  "osmId": 544726,
  "osmPlace": "island",

  "parentWaterBody": null,
  "classification": {
    "source": "manual",
    "confidence": "high"
  }
}
```

## Field reference

### Identity

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | yes | Stable, lowercase-hyphenated, ASCII-folded name. Disambiguated by parent body or island group on collision. **Never regenerated** for an existing island. |
| `name` | string | yes | Canonical English display name. Diacritics allowed (e.g. `Sgùrr na h-Iolaire`). For landmasses without any published name, use the placeholder **`Unnamed island`** and set `nameStatus` to `unknown` — never invent a proper name. |
| `nameStatus` | enum / null | no | `unknown` when the landmass is mapped (usually via OSM) but no reliable name exists yet; omit or `null` when `name` is a real identifier. Crowdsourcing target for Contribute flows. |
| `nation` | enum | yes (after classification) | One of `Scotland`, `England`, `Wales`, `Northern Ireland`, `Ireland`, `Crown Dependency`. `null` for unclassified outliers (which are then filtered out before shipping). |

### Geometry / location

| Field | Type | Required | Notes |
|---|---|---|---|
| `lat` | number | yes | WGS84 degrees. |
| `lng` | number | yes | WGS84 degrees (negative = west). |
| `areaKm2` | number | no | Polygon area, if known. Computed from OSM geometry or curated. |
| `osmType` | enum | no | `relation`, `way`, or `node`. |
| `osmId` | integer | no | OSM element id paired with `osmType`. |
| `osmPlace` | string | no | The OSM `place=` tag value, e.g. `island`, `islet`. |

### Type / water-body context

| Field | Type | Required | Notes |
|---|---|---|---|
| `type` | enum | yes | `sea`, `lake`, or `river`. |
| `subtype` | enum / null | no | `estuary`, `tidal`, `canal`, `reservoir`, `crannog`, `oxbow`, or `null`. |
| `tidal` | boolean / null | no | Currently unset for most entries; reserved for future use. |
| `archipelago` | string / null | no | Hand-curated grouping (e.g. "Inner Hebrides", "Scilly"). |
| `parentWaterBody` | object / null | no (required if `type` ≠ `sea`) | See sub-schema below. |

`parentWaterBody`:

```json
{
  "name": "Lough Neagh",
  "type": "lake",
  "osmType": "relation",
  "osmId": 12345,
  "wikidata": "Q57301"
}
```

### Stats (mostly optional)

| Field | Type | Notes |
|---|---|---|
| `population` | integer | Only ~141 entries have this; most small islands are unpopulated or undocumented. |
| `highestPointM` | integer | Metres. |
| `highestPointName` | string | E.g. "Sgùrr Alasdair". |

### Prose (curated)

| Field | Type | Notes |
|---|---|---|
| `shortDescription` | string | One-paragraph summary shown at the top of the detail pane. |
| `history` | string | Multi-paragraph; supports plain text only (no HTML). |
| `geography` | string | |
| `transport` | string | |
| `accommodation` | string | Must be neutral, factual, no affiliate links. |
| `tags` | string[] | Free-form tag list (e.g. `["castle","ferry","unesco"]`). |

### External references

| Field | Type | Notes |
|---|---|---|
| `wikipedia` | URL string | Article URL. Used by `enrich_images.py` as a fallback image source. |
| `wikidata` | string | Q-ID, e.g. `Q80967`. Primary key for image enrichment. |

### Images

`image` (string, optional) is a back-compat mirror of `images[0].url`. Always
set when `images[]` is non-empty.

`images` (array, optional). Each entry **must** have all of `url`, `source`,
`license`, `sourcePageUrl`, `attribution`. The full schema:

```jsonc
{
  "url": "https://upload.wikimedia.org/.../640px-Foo.jpg",  // displayable thumbnail
  "fullUrl": "https://upload.wikimedia.org/.../1600px-Foo.jpg", // optional larger
  "caption": "Optional human-written caption",
  "source": "wikidata" | "wikipedia" | "commons" | "curated",
  "sourceRef": "Q12345 or Page_Title or null",
  "sourcePageUrl": "https://commons.wikimedia.org/wiki/File:Foo.jpg",
  "license": "CC-BY-SA-4.0" | "CC-BY-4.0" | "CC0" | "PD" | "OGL-3.0" | …,
  "attribution": "Photo by Author Name (CC-BY-SA-4.0) via Wikimedia Commons",
  "primary": true
}
```

**Hard rules** (see also `ETHICS.md`):

- Never add an image without `license` + `attribution` + `sourcePageUrl`.
- Never derive an image from a free-text search (e.g. "google for Foo Island").
- Only one image may have `primary: true` per record.

### Property listings (for sale — outbound links)

Optional field group. **Link-out only** — no scraped portal HTML, photos, or
full addresses (see `docs/PROPERTY-LISTINGS.md` and `ETHICS.md` §3).

| Field | Type | Notes |
|---|---|---|
| `propertyListings` | array | Zero or more active listing stubs. |
| `propertyListingsSource` | string | e.g. `curated`, `homedata`, `curated+homedata`. |
| `propertyListingsConfidence` | enum | `high`, `medium`, `low` — worst-case across matches on the island. |
| `propertyListingsAttribution` | string | Human-readable source / disclaimer. |
| `propertyListingsFetchedAt` | ISO-8601 | Last ingest run. |

Each `propertyListings[]` entry:

```json
{
  "id": "a1b2c3d4e5f67890",
  "listingType": "whole_island",
  "status": "for_sale",
  "title": "Tanera Mòr — whole island estate",
  "url": "https://example.com/listing",
  "source": "curated",
  "sourceListingId": "curated-tanera-mor-1",
  "priceGBP": null,
  "priceDisplay": "POA",
  "matchedMethod": "curated",
  "matchedConfidence": "high",
  "offshore": false
}
```

| `listingType` | `whole_island`, `residential`, `land` |
| `matchedMethod` | `curated`, `polygon`, `proximity`, `name` |
| `matchedConfidence` | `high`, `medium`, `low` |

Staged in `data/cache_property_listings.json`; applied via `apply_enrichments.py`.

### Provenance / classification

| Field | Type | Notes |
|---|---|---|
| `source` | enum | `curated`, `osm`, `osm-inland`, `wikidata-discovery`, `csv-import`, … one per ingestion path. |
| `classification.source` | enum | `manual`, `tier-a`, `tier-b`, `tier-c`, `tier-d`, `discovery-pipeline`. See `METHODOLOGY-INLAND.md` for tier labels. |
| `classification.confidence` | enum | `high`, `medium`, `low`, **`unconfirmed`**. The last marks a row shown on the map for exploration that **did not** pass the discovery pipeline’s automatic review gate (e.g. missing licence-safe hero image, medium/low verification). It is **not** a claim that the feature is a recognised island. |
| `classification.reviewHint` | string / null | Optional short machine-oriented note (e.g. why `unconfirmed` was applied). Shown in the UI for transparency. |

## Adding a new field

1. Pick a name and type. Prefer extending an existing object (e.g.
   `parentWaterBody`) over flattening if it's structured.
2. Update this file with the field, type, example, and rules.
3. Update the relevant pipeline script(s) to write it.
4. Update `app.js → renderDetails()` to render it (or `renderList()` if it
   affects the sidebar).
5. Add a SESSION-LOG entry mentioning the new field.

## Adding a new island manually

You almost never should — use a pipeline. But if you must (curated additions
only):

1. Add to `data/curated.json` with at least `id`, `name`, `nation`, `lat`,
   `lng`, `type`, `source: "curated"`, `classification: { source: "manual",
   confidence: "high" }`.
2. Rerun `python3 scripts/fetch_islands.py --cache` (the merge step will pick
   it up and try to attach `osmId`).
3. Verify it appears in the UI; add a SESSION-LOG entry.
