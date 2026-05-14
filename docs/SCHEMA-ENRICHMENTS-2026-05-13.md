# Schema enrichments proposal — 2026-05-13

Five new open-data enrichments for `data/islands.json`. This document is
the **schema proposal** — read it before any ingestion script mutates
the dataset.

It follows the existing
`<thing>Source` / `<thing>Confidence` / `<thing>Attribution` /
`<thing>FetchedAt` quad pattern established by:

- `areaSource` / `areaConfidence` (`compute_island_areas.py`)
- `highestPointSource` / `highestPointConfidence` (`compute_island_highpoints.py`)
- `descriptionSource` / `descriptionConfidence` / `descriptionAttribution` /
  `descriptionFetchedAt` (`enrich_descriptions_wikipedia.py`)

Every new field-group below carries its own quad so the UI and audit
trail are uniform.

---

## 0. Coordination — do NOT mutate `islands.json` directly

`scripts/overnight_runner.sh` is still in flight as of writing. We
therefore **stage** each enrichment to a per-source cache:

| Enrichment             | Cache file                          |
| ---------------------- | ----------------------------------- |
| Hills (DoBIH)          | `data/cache_dobih.json`             |
| Lighthouses + beacons  | `data/cache_lighthouses.json`       |
| Wildlife colonies      | `data/cache_wildlife.json`          |
| Geology (BGS)          | `data/cache_bgs.json`               |
| Census 2022            | `data/cache_census2022.json`        |

The merge into `islands.json` is a separate, deferred, single atomic step
(`scripts/apply_enrichments.sh`) the user runs once the overnight chain
has finished and they've sanity-checked the staged data.

---

## 1. Hills — `hillsOn[]` + `hillsOnSource`/`hillsOnConfidence`/…

The **Database of British and Irish Hills** (DoBIH; Jackson, Dawson et
al.) is the canonical compendium of UK + Ireland hill classifications:
Munros, Corbetts, Grahams, Donalds, Murdos, Marilyns, HuMPs, TuMPs,
Hewitts, Nuttalls, Wainwrights, Birketts. Released under
**CC-BY 4.0** at <https://www.hills-database.co.uk/>. Required
attribution: "Database of British and Irish Hills (Jackson, Dawson, et
al.), CC-BY 4.0".

### Schema

```jsonc
{
  // existing fields ...
  "hillsOn": [
    {
      "name": "Sgùrr Alasdair",
      "classifications": ["Munro"],        // ordered: highest classification first
      "elevationM": 992,
      "prominenceM": 992,
      "lat": 57.2087, "lng": -6.2236,
      "dobihId": 4061,                     // null if not in DoBIH (OSM-only fallback)
      "osmNodeId": 1242503981,             // null if not in OSM
      "wikidata": "Q1369681",
      "wikipedia": "https://en.wikipedia.org/wiki/Sgùrr_Alasdair",
      "image": null                        // populated separately under island.images[] with subject:"hill"
    }
  ],
  "hillsOnSource": "dobih-v17|wikidata-p2044|osm-peak",
  "hillsOnConfidence": "high|medium|n/a",
  "hillsOnAttribution": "Database of British and Irish Hills (Jackson, Dawson, et al.), CC-BY 4.0 — https://www.hills-database.co.uk/",
  "hillsOnFetchedAt": "2026-05-13T08:00:00Z"
}
```

### Rules

- `classifications` is a list because a single hill can be a Munro **and**
  a Marilyn **and** a HuMP. Sort by "prestige" so `[0]` is the most
  commonly cited tier (Munro > Furth > Corbett > Graham > Donald >
  Murdo > Marilyn > HuMP > Hewitt > Nuttall > Wainwright > Birkett).
- `prominenceM` only set when DoBIH supplies it; never invented.
- `confidence: "high"` when the hill is in DoBIH **and** its coordinates
  fall inside the island's polygon (resolved via the existing
  `cache_osm_geometries.json` priority chain).
- `confidence: "medium"` when we have a name + elevation but PIP failed
  (e.g. OSM peak node sits ≤ 50 m outside our polygon because of tidal
  smoothing).
- `confidence: "n/a"` and `hillsOn: []` when the island has no qualifying
  hill (true for the ~6,400 small islets without a classified summit).

### UI placeholder

Render under the existing "Highest point" row in the stats table:

```html
<div class="hills-on">
  <h4>Classified hills</h4>
  <ul>
    <li>
      <span class="hill-name">Sgùrr Alasdair</span>
      <span class="hill-class hill-class-munro">Munro</span>
      <span class="hill-ele">992 m</span>
    </li>
    ...
  </ul>
  <p class="attribution">via DoBIH (CC-BY 4.0)</p>
</div>
```

New CSS classes to introduce: `.hills-on`, `.hill-name`, `.hill-class`,
`.hill-class-{munro|corbett|graham|donald|marilyn|hump|hewitt}`,
`.hill-ele`. Cap the list at 6 items + "n more" on islands like Skye
with ~12 Munros.

---

## 2. Lighthouses & beacons — `lighthouses[]` + quad

Three open authorities:

| Body                                  | Coverage                       | Licence                |
| ------------------------------------- | ------------------------------ | ---------------------- |
| Northern Lighthouse Board (NLB)       | Scotland + Isle of Man         | © NLB, factual reuse OK; attribution required. |
| Trinity House                         | England, Wales, Channel Is.    | © Trinity House; factual reuse OK. |
| Commissioners of Irish Lights (CIL)   | All Ireland (NI + ROI)         | © Commissioners of Irish Lights. |
| OpenStreetMap                         | Global cross-check             | ODbL 1.0               |
| Wikidata                              | Q-IDs + light characteristic   | CC0                    |

Source-of-truth for our pipeline is **OSM `man_made=lighthouse` / `man_made=beacon`**
(ODbL 1.0) cross-referenced with Wikidata for the `seamark:light:character`
string and established year. Per ETHICS §1, NLB/Trinity/CIL pages are
cited as *underlying* attribution but we do not scrape their websites.

### Schema

```jsonc
{
  "lighthouses": [
    {
      "name": "Neist Point Lighthouse",
      "characteristic": "Fl W 5s",                  // light pattern; null if unknown
      "rangeNm": 16,                                // visibility in nautical miles; null if unknown
      "heightM": 19,                                // tower height above mean sea level; null if unknown
      "establishedYear": 1909,                       // null if unknown
      "status": "operational",                       // "operational" | "deactivated" | "automated" | "unknown"
      "operator": "Northern Lighthouse Board",       // exact body name; or null
      "lat": 57.4225, "lng": -6.7869,
      "offshore": false,                             // true if PIP says outside island polygon but within 200 m
      "osmType": "node", "osmId": 1234567,
      "wikidata": "Q1234567",
      "wikipedia": "https://en.wikipedia.org/wiki/Neist_Point_Lighthouse",
      "notForNavigation": true                       // mandatory per ETHICS §10
    }
  ],
  "lighthousesSource": "osm-man-made-lighthouse|wikidata-q39715|nlb-vessel-list",
  "lighthousesConfidence": "high|medium|n/a",
  "lighthousesAttribution": "© OpenStreetMap contributors (ODbL 1.0); cross-checked against Northern Lighthouse Board / Trinity House / Commissioners of Irish Lights public lists.",
  "lighthousesFetchedAt": "2026-05-13T08:00:00Z"
}
```

### Rules

- `notForNavigation: true` is **mandatory** on every record (ETHICS §10).
- `offshore: true` when the coordinates fall *outside* the island
  polygon but ≤ 200 m from the coastline. These should still be
  attributed to the island as a navigation aid, but flagged so the UI
  can render them under a separate sub-heading.
- `characteristic` is the formal seamark notation
  (`seamark:light:character` + `seamark:light:colour` from OSM). We
  never compose our own characteristic string.
- A representative photo per lighthouse goes in the island's
  `images[]` with `subject: "lighthouse"` (see §6 below).

---

## 3. Wildlife colonies + reserves — `rspbReserves[]`, `wildlifeColonies[]`

This is the **most ethically-sensitive** of the five enrichments. Read
[`ETHICS.md`](ETHICS.md) §5 ("Sensitive species") before writing the
ingestion script.

### Hard constraints (from ETHICS §5)

- **Island-level presence only.** We may list species that are known
  to breed on an island; we may **NOT** include precise colony
  coordinates, per-nest data, or counts.
- **No "best time to visit"** narrative.
- **Schedule 1 species** (Leach's storm petrel, Manx shearwater, roseate
  tern, little tern, hen harrier, peregrine, white-tailed eagle, …) —
  presence may be recorded if it is *already* in public domain sources
  (Wikipedia article, SPA citation, RSPB reserve description); never
  counts.

### Schema

```jsonc
{
  "rspbReserves": [
    {
      "name": "Mingulay, Berneray and Pabbay",
      "url": "https://www.rspb.org.uk/days-out/reserves/mingulay-berneray-pabbay",
      "areaHa": 1330,                       // hectares; null if not published
      "established": null,                  // year; null if not published
      "designation": "RSPB Reserve",        // "RSPB Reserve" | "RSPB Future" | "Joint Management"
      "osmType": "way", "osmId": 12345678   // OSM nature_reserve relation, when present
    }
  ],
  "rspbReservesSource": "osm-leisure-nature-reserve|rspb-website",
  "rspbReservesConfidence": "high|medium|n/a",
  "rspbReservesAttribution": "© OpenStreetMap contributors (ODbL 1.0); reserve listing © RSPB.",
  "rspbReservesFetchedAt": "2026-05-13T08:00:00Z",

  "wildlifeColonies": [
    {
      "species": "gannet",                  // controlled vocabulary, lowercase, hyphen-joined
      "category": "seabird",                // "seabird" | "seal" | "raptor" | "cetacean"
      "season": "breeding-summer",          // free-text qualifier, optional
      "source": "spa-citation",             // see Sources below
      "sourceRef": "https://sac.jncc.gov.uk/site/UK9001041",
      "scheduleListed": true                // UK W&CA Sch.1 or IE protected — UI tones down disturbance signals
    }
  ],
  "wildlifeColoniesSource": "spa-citation|jncc-sea-area|wikipedia-mention|curated",
  "wildlifeColoniesConfidence": "high|medium|low",
  "wildlifeColoniesAttribution": "Joint Nature Conservation Committee SPA citations (OGL 3.0); RSPB Reserves (© RSPB); presence cross-checked against Wikipedia articles under CC-BY-SA 4.0.",
  "wildlifeColoniesFetchedAt": "2026-05-13T08:00:00Z"
}
```

### Controlled species vocabulary

The `species` field accepts ONLY the following identifiers. Anything
else gets rejected at ingest:

```
gannet, puffin, kittiwake, guillemot, razorbill, fulmar,
manx-shearwater, storm-petrel, leachs-petrel, arctic-tern,
common-tern, roseate-tern, sandwich-tern, little-tern,
eider, shag, cormorant, great-skua, arctic-skua, herring-gull,
black-headed-gull, lesser-black-backed-gull, great-black-backed-gull,
black-guillemot, red-throated-diver, black-throated-diver,
great-northern-diver, white-tailed-eagle, golden-eagle, peregrine,
hen-harrier, merlin, short-eared-owl, corncrake, chough,
grey-seal, common-seal,
harbour-porpoise, common-dolphin, bottlenose-dolphin, minke-whale,
basking-shark, otter
```

Adding a new species requires updating this list AND `ETHICS.md` §5 to
reflect its protected status.

### Source priority (highest → lowest)

1. **SPA / SAC citation documents** — JNCC publishes the Special
   Protection Area citations under OGL 3.0. Each citation lists
   qualifying species at SPA-level granularity (no per-nest data).
2. **RSPB reserve description** (public web page) — listed species.
3. **JNCC Seabird Monitoring Programme summary page** — *summary
   only*, never the count data which is gated.
4. **Wikipedia article body** — only when explicitly cited to a
   published source; we record `confidence: "low"` for these.
5. **Curated `data/wildlife_overrides.json`** — for well-known stacks
   (Bass Rock, St Kilda, Skellig Michael, Skomer, Rathlin, Ailsa Craig,
   Lundy, Mingulay) with hand-verified species lists.

---

## 4. Geology — `geology` object + quad

The **British Geological Survey** publishes DigMapGB-625 (1:625,000
scale) bedrock and superficial deposit maps under the **BGS Open Data
licence (OGL v3.0)**.

Download (one-off, ~50 MB SHP): <https://www.bgs.ac.uk/datasets/bgs-geology-625k-digmapgb/>.

Pipeline: point-in-polygon each island's centroid against the bedrock
polygon layer. Optionally same for the superficial layer.

### Schema

```jsonc
{
  "geology": {
    "bedrock": {
      "name": "Torridon Group",                  // BGS LEX_RCS_NAME
      "lithology": "Sandstone",                  // BGS RCS_D
      "ageStart": "Neoproterozoic",              // BGS LEX_RANK or NEO_AGE_MIN
      "ageEnd": "Neoproterozoic",
      "ageStartMa": 1000,                         // approximate megaannum
      "ageEndMa": 750
    },
    "superficial": {                              // optional, may be null
      "name": "Till, Devensian",
      "lithology": "Diamicton"
    },
    "source": "bgs-digmapgb-625",
    "confidence": "high|medium|n/a",
    "attribution": "Contains British Geological Survey materials © UKRI 2026, licensed under the BGS Open Data licence (OGL v3.0).",
    "fetchedAt": "2026-05-13T08:00:00Z"
  }
}
```

Note: this is a single nested object rather than a quad spread across
top-level keys, because all four entries logically belong together.
The four-key-quad convention is honoured *inside* the object via the
nested `source`, `confidence`, `attribution`, `fetchedAt` keys.

### Confidence

- `high`: centroid is unambiguously inside one bedrock polygon.
- `medium`: centroid sits on a polygon edge / multiple candidates within
  100 m; the script picks the largest-area candidate.
- `n/a`: outside BGS extent (e.g. far-offshore Channel Island reefs).

---

## 5. Census 2022 — `populationYear`, `populationSource`, `populationDetails`

Each nation in the British Isles released its 2022/2021 census on a
different schedule:

| Nation           | Body           | Census year | Open licence | Island-level published? |
| ---------------- | -------------- | ----------- | ------------ | ----------------------- |
| Scotland         | NRS            | 2022        | OGL 3.0      | Yes — "Scotland's Inhabited Islands" 2022 report (61 inhabited islands). |
| England + Wales  | ONS            | 2021        | OGL 3.0      | Partial — most via OA aggregation; IoW, Hayling, Canvey, Lindisfarne published. |
| Northern Ireland | NISRA          | 2021        | OGL 3.0      | Partial — Rathlin only. |
| Ireland (ROI)    | CSO Ireland    | 2022        | PSI Re-use   | Partial — Small Area level; offshore island summary report. |
| Isle of Man      | IoM Government | 2021        | OGL IoM      | Yes — single number. |
| Channel Islands  | States         | 2021/22     | Mixed        | Yes — per bailiwick. |

### Schema

We **never overwrite** an existing `population` with an older figure;
the script compares timestamps and only updates if the new figure is
more recent / more authoritative.

```jsonc
{
  "population": 137,                           // most-recent authoritative figure
  "populationYear": 2022,                       // census year, NOT the year we fetched
  "populationSource": "nrs-2022",               // nrs-2022 | ons-2021 | nisra-2021 | cso-2022 | iom-2021 | states-2021
  "populationConfidence": "high",
  "populationAttribution": "© Crown copyright, National Records of Scotland (OGL v3.0)",
  "populationFetchedAt": "2026-05-13T08:00:00Z",

  "populationDetails": {
    "households": 56,
    "ageStructure": {                           // optional; only NRS / ONS publish at island level
      "under16": 18,
      "16to64": 79,
      "65plus": 40
    },
    "gaelicSpeakers": 12,                       // Scotland only, when published
    "welshSpeakers": null,                      // Wales only
    "irishSpeakers": null                       // Ireland only
  }
}
```

### Rules

- `populationDetails` is **optional**. Don't fudge — for ROI islands
  where CSO publishes only Small Area data and not island-level, leave
  it unset and record in the audit `coverage_gaps[]` list.
- `populationConfidence` is `high` when the figure comes directly from
  a published table at island granularity, `medium` when aggregated up
  from sub-island reporting units, `low` when extrapolated.
- The `population` top-level field is the *user-facing* figure — keep
  it backwards-compatible (existing UI reads it directly).

---

## 6. Photos for new entities — `images[]` extensions

Per the existing `enrich_images_v5.py` attribution shape, plus a new
`subject:` discriminator:

```jsonc
{
  "images": [
    {
      "url": "https://commons.wikimedia.org/wiki/Special:FilePath/Foo.jpg?width=800",
      "fullUrl": "https://commons.wikimedia.org/wiki/Special:FilePath/Foo.jpg?width=1600",
      "caption": "Neist Point Lighthouse, Isle of Skye",
      "source": "wikidata|wikipedia|commons-geosearch",
      "sourceRef": "Q1234567",
      "sourcePageUrl": "https://commons.wikimedia.org/wiki/File:Foo.jpg",
      "license": "CC-BY-SA-4.0",
      "attribution": "Photo by …, via Wikimedia Commons (CC-BY-SA 4.0)",
      "subject": "lighthouse",         // "island" (existing) | "lighthouse" | "hill" | "wildlife"
      "subjectRef": "neist-point-lighthouse",  // entity ID within this island (loose match to hillsOn[].name etc.)
      "primary": false
    }
  ]
}
```

`subject: "island"` is the implicit default for every photo already in
the dataset (no migration needed; UI will treat absent `subject` as
`island`).

### Per-entity quota

- 1 photo per hill at most (the highest-prestige one).
- 1-2 photos per lighthouse (exterior + close-up if both available).
- 1 photo per RSPB reserve (the reserve itself, not a species photo —
  avoids any disturbance-driving narrative).
- 0 photos for individual `wildlifeColonies[]` entries. Birds in flight
  are public-domain enough but we don't want to compose a "best
  photo-spotting locations" page (see ETHICS §5).

---

## 7. UI render plan (this task documents only — no UI ship)

| Field group         | Where it renders                                    | CSS classes to introduce                         |
| ------------------- | --------------------------------------------------- | ------------------------------------------------ |
| `hillsOn[]`         | New row under "Highest point" in the stats table    | `.hills-on`, `.hill-name`, `.hill-class*`, `.hill-ele` |
| `lighthouses[]`     | New section "Maritime aids", below "Heritage" row   | `.lighthouses`, `.lighthouse`, `.lighthouse-meta` |
| `rspbReserves[]`    | New section "Reserves & wildlife", above "Tags"     | `.reserves`, `.reserve`                          |
| `wildlifeColonies[]`| Same section as reserves, after the reserves list   | `.wildlife-colonies`, `.colony-species*`         |
| `geology` (bedrock) | New inline row in the stats table, "Bedrock"        | (none new — reuse existing `.row`)               |
| `populationDetails` | Expand the existing "Population" cell with a `<details>` disclosure | `.population-detail`                       |

All sections must show an `attribution` paragraph at the bottom citing
the underlying source per ETHICS §9.

---

## 8. Apply order (single atomic merge)

`scripts/apply_enrichments.sh` reads from all five caches and merges
into `islands.json` in a single atomic pass:

1. Verify overnight chain finished (`logs/overnight-*-summary.log`
   contains `===== Overnight run finished`).
2. Take a single timestamped backup
   `data/islands.json.before-enrichments-<ts>`.
3. Load `islands.json`.
4. For each cache file present:
   - Skip islands the cache didn't cover (no field overwriting).
   - Merge under the per-source field, never the unrelated ones.
   - Honour the "don't overwrite newer with older" rule for `population`.
5. Validate the result is parseable JSON, the array length is
   unchanged, and a sample of curated regression islands (Skye,
   Devenish, Achill, Eel Pie, …) still passes its smoke check.
6. Atomic write via tmp + `os.replace`.
7. Write `data/enrichment_apply_report.json` summarising counts +
   diffs.

---

## 9. Out-of-scope (parked)

- **NHLE / Cadw / Canmore / NMS heritage register** — separate
  workstream, queued in `QUEUE.md` P2.
- **Tide times & live AIS** — out of scope per ETHICS §10.
- **SMP raw colony counts** — gated, off-limits per ETHICS §5.
- **WDPA / Protected Planet polygons** — non-commercial licence, off-
  limits per ETHICS §1.

---

## 10. Schema diff summary

New top-level keys on island records (all optional, defaulting to
`null` / `[]`):

```
hillsOn               array of {name, classifications[], elevationM, prominenceM, lat, lng, dobihId, osmNodeId, wikidata, wikipedia}
hillsOnSource         string enum
hillsOnConfidence     string enum
hillsOnAttribution    string
hillsOnFetchedAt      ISO timestamp string

lighthouses           array of {name, characteristic, rangeNm, heightM, establishedYear, status, operator, lat, lng, offshore, osmType, osmId, wikidata, wikipedia, notForNavigation}
lighthousesSource     string enum
lighthousesConfidence string enum
lighthousesAttribution string
lighthousesFetchedAt  ISO timestamp string

rspbReserves          array of {name, url, areaHa, established, designation, osmType, osmId}
rspbReservesSource    string enum
rspbReservesConfidence string enum
rspbReservesAttribution string
rspbReservesFetchedAt ISO timestamp string

wildlifeColonies      array of {species, category, season, source, sourceRef, scheduleListed}
wildlifeColoniesSource string enum
wildlifeColoniesConfidence string enum
wildlifeColoniesAttribution string
wildlifeColoniesFetchedAt ISO timestamp string

geology               object {bedrock, superficial, source, confidence, attribution, fetchedAt}

populationYear        integer
populationSource      string enum
populationConfidence  string enum
populationAttribution string
populationFetchedAt   ISO timestamp string
populationDetails     object {households, ageStructure, gaelicSpeakers, welshSpeakers, irishSpeakers}
```

New optional key on `images[i]`:

```
subject               string enum: "island" | "lighthouse" | "hill" | "wildlife"  (defaults to "island")
subjectRef            string (loose match into the per-entity arrays)
```

After this change, update `docs/DATA-SCHEMA.md` (same diff).
