# Ethics — Isles of Britain project

This is a permanent project artefact, not a session note. Every data
ingestion, every UI change, and every external API call must be consistent
with the principles below. When a guideline conflicts with a feature, the
guideline wins.

## 1. Licensing rigour

We redistribute only data covered by an unambiguous open licence:

- **OGL v3.0** (UK Crown), **OGL (Isle of Man)**, **OGL (NI)**
- **CC0** (Wikidata, public-domain dedications)
- **CC-BY 4.0** with required attribution carried forward to the per-island
  `provenance` field
- **CC-BY-SA 4.0** with share-alike honoured on derivative datasets
- **ODbL** (OpenStreetMap) — share-alike obligations honoured
- **PSI Directive / Re-use of Public Sector Information Regulations**
  (Ireland) — substantively equivalent to OGL

Every other class is excluded, even if technically reachable:

- IUCN WDPA / Protected Planet (non-commercial-only)
- RSPB IBA current polygons (non-commercial bespoke licence)
- Seabird Monitoring Programme colony coordinates (gated, Schedule 1
  species rules)
- Maxar / WorldView / GeoEye (commercial; surveillance risk)
- Reed's Nautical Almanac, Imray Charts (commercial)
- States of Jersey GIS, Digimap Guernsey (partner-only; no clear open
  licence)
- ToS-restricted scrapes (RNLI UK hub is "Open Data" branded but uses a
  revocable, no-modification licence)

Every ingested record carries a provenance entry recording the source URL,
licence identifier, retrieval date, and the licence's required attribution
string. The `not_for_navigation: true` flag is mandatory for any record
derived from hydrographic / lighthouse / AtoN data.

## 2. Cultural and linguistic respect

The British Isles are home to multiple living languages whose place-name
authorities pre-date OpenStreetMap's English-default rendering. Where a
recognised cultural authority publishes a name, that name is **canonical**
in its territory and is preserved verbatim — diacritics, orthography, and
all.

| Language | Authority | Coverage |
| --- | --- | --- |
| Gàidhlig (Scottish Gaelic) | Ainmean-Àite na h-Alba (AÀA), Comhairle nan Eilean Siar | Scottish islands |
| Gaeilge (Irish) | Logainm.ie (An Brainse Logainmneacha, statutory) | Ireland (RoI + NI) |
| Cymraeg (Welsh) | Welsh Language Commissioner (statutory) | Welsh islands |
| Gaelg (Manx) | Yn Çheshaght Ghailckagh, Manx National Heritage, Broderick *Place-Names of the Isle of Man* | Isle of Man |
| Kernewek (Cornish) | Akademi Kernewek (Standard Written Form) | Cornish + Scilly islands |
| Jèrriais, Guernésiais, Sercquiais, Auregnais | local government cultural registries | Channel Islands |

The dataset schema accommodates this with parallel name fields
(`name:ga`, `name:gd`, `name:cy`, `name:gv`, `name:kw`, plus
language-specific aliases). The English form may be displayed by default,
but the cultural-authority form is never silently dropped or anglicised.

The Republic of Ireland is a sovereign nation. Its islands are tagged
`nation: "Ireland"` and are **never** rolled up into a "UK" or "British
Isles" aggregation, even though the wider geographic term is in our project
title for historical reasons.

## 3. Privacy on inhabited islands

Inhabited islands are home to identifiable communities. The dataset records
**island-level** information only:

- Island name, geography, history, transport, public-facing accommodation.
- We **do not** ingest per-dwelling addresses, owner names, building
  footprints, or any data that could be aggregated to identify a private
  resident.
- We **do not** record telephone numbers, postal addresses, or email
  addresses of named individuals.
- Heritage registers (NHLE, Cadw, Canmore, NMS Ireland) often contain
  per-building entries on inhabited islands. We summarise these as counts
  ("N listed buildings", "N scheduled monuments") without per-building
  geometry, unless the listed feature is itself the island's defining
  public landmark (e.g. an abbey ruin, a lighthouse).

## 4. Sacred and sensitive sites

Several islands are continuously sacred or contain unmarked burial places.
For these, the project displays only what is already public on Wikipedia
and OSM, and avoids generating any new disclosure:

- **Iona** — Reilig Odhráin burial ground. Island-level entry with public
  history; no new feature-level coordinates for individual graves.
- **Skellig Michael** — UNESCO monastic site with seasonal access
  restrictions and fragile archaeology. Public access advisories
  propagated; no new sub-feature geometry beyond what NMS Ireland publishes.
- **Lough Derg Station Island** — active pilgrimage site. Public-facing
  description only.
- **Inishmurray** — early-Christian monastic remains including leachta
  "cursing stones". Public-facing description only.
- **Boa Island (Lough Erne) Caldragh figures**, **White Island carved
  figures** — public archaeology, but no exact unmarked-grave coordinates.
- **Hebridean "burying isles"** (e.g. Inchcailloch, Eilean Munde, Eilean
  Fhianain) — recorded as historic burial isles without precise burial
  coordinates.
- **Crannogs and scheduled monuments** — we adopt the granularity already
  published by Canmore / NPWS / NISMR (typically 10–100 m rounded NGRs)
  and never disclose finer.

Where a heritage authority flags a site as **at risk** or **access
restricted**, that flag is carried forward on the public record so users
respect it.

## 5. Sensitive species

UK and Irish law protects certain breeding species' nesting locations:

- **UK Wildlife & Countryside Act 1981 Schedule 1** — Leach's storm petrel,
  Manx shearwater (some colonies), roseate tern, little tern,
  Mediterranean gull, white-tailed eagle, sea eagle, peregrine, hen harrier,
  many others.
- **Irish Wildlife Acts** — equivalent protections including storm petrel,
  Leach's storm petrel.

For any dataset that flags such species (RSPB, JNCC, NatureScot, NIEA,
NPWS, BWI, SMP):

- We ingest **only the island name and approximate position** (≥1 km grid).
- We do **not** ingest precise colony coordinates, per-nest data, or counts
  that could indicate productive sub-sites.
- We do **not** publish "best time to visit" or similar guidance that could
  drive disturbance.

The Seabird Monitoring Programme would be the highest-name-yield source
(~150–300 stacks/holms) but the licence is gated and the species rules
strict. We do not ingest its data without explicit BTO/JNCC written
sign-off, and even then only the site-name list — never counts or per-site
species annotations.

## 6. Imagery

- **No biometric or personally-identifying imagery.** When a Wikimedia
  Commons image of an island prominently shows identifiable individuals,
  prefer the next image in the gallery via the existing fallback chain.
- **No high-resolution aerial / satellite zoom showing private property.**
  Our base map allows users to zoom; we do not enrich the imagery beyond
  what the underlying open tile providers serve.
- **No drone / aerial footage from sources without commercial-reuse
  rights.** The image enrichment pipeline (`scripts/enrich_images.py`)
  already restricts to Wikidata P18 + Commons-licensed Wikipedia lead
  images.
- **Filter out non-photographic representations** (flags, coats of arms,
  maps drawn in SVG). The existing `_looks_like_non_photo` filter handles
  this; do not regress it.

## 7. Indigenous and community knowledge

Where a community register, council, or place-names body publishes a form
or interpretation of an island, that source is canonical for its territory.
Examples:

- Comhairle nan Eilean Siar's signage policy is binding for Eilean Siar
  islands (Lewis, Harris, the Uists, Benbecula, Barra, Vatersay, Eriskay,
  Scalpay, Taransay).
- Logainm.ie's Irish form is co-canonical with the English form in
  Ireland; in Gaeltacht territory the Irish form is primary.
- Akademi Kernewek's Standard Written Form is the recognised Cornish form
  for the Scilly archipelago and Cornish coast.

When OSM, Wikipedia, or the academic literature disagrees with a cultural
authority's preferred form, the cultural authority wins.

## 8. Remote sensing — no fabrication

If a future ingestion uses remote-sensing data (Sentinel, Landsat, EMODnet
satellite coastlines, lidar), it must respect:

- **No auto-promoted detections.** Any feature surfaced by RS pipelines
  must be flagged `candidate: true` with a `year_of_detection` field and
  must not be displayed as a confirmed named island until corroborated by
  OS / UKHO / OSM / Wikipedia.
- **No naming from imagery alone.** Coordinates are not names. Defer to
  local-name authorities (workstream 7) for naming.
- **No surveillance overreach.** Stick to coastline and topography; do not
  derive building footprints, vehicle counts, vessel tracks, or person
  detections, even from open imagery.
- **Temporal honesty.** When climate-change-driven accretion or erosion has
  produced a new or vanished feature, record both states with a temporal
  qualifier rather than overwriting history.

## 9. Attribution and provenance

Every ingested entry carries:

```jsonc
{
  // ...
  "sources": [
    {
      "name": "Wikidata",
      "ref": "Q47921",
      "url": "https://www.wikidata.org/wiki/Q47921",
      "licence": "CC0",
      "retrieved": "2026-05-11",
      "attribution": "Wikidata contributors"
    },
    {
      "name": "Logainm.ie",
      "ref": "logainm:1411993",
      "url": "https://www.logainm.ie/en/1411993",
      "licence": "CC-BY-4.0",
      "retrieved": "2026-05-11",
      "attribution": "© Government of Ireland — Logainm contributors"
    }
  ]
}
```

The front-end displays the licence and attribution for every island in its
details panel, and a global "Sources" page lists every cited dataset.

## 10. Out of scope

This project does **not** publish:

- Sailing directions, pilotage notes, or any guidance presented in a form
  that could be mistaken for navigation advice. (Even where source data is
  open, we add `not_for_navigation: true` to derivative records and a
  visible disclaimer in any nautical-flavoured UI.)
- Tide tables, weather forecasts, or live SAR / coastguard / RNLI status.
- Personal contact information for residents, business owners, or
  monastic / pilgrimage communities.

## 11. Geographic and political scope

The project covers the British Isles within ~50 statute miles of the UK
coast: Great Britain, Northern Ireland, the Republic of Ireland, the Isle
of Man, and the Bailiwicks of Jersey and Guernsey (including Sark,
Alderney, Herm, Lihou, Brecqhou, Burhou, and the Casquets). It does **not**
cover the Faroe Islands, Iceland, mainland Europe, or French islands.
Faroese and French islands within incidental Overpass bounding-box pulls
are filtered out at ingest.

## 12. Review and updates

This document is reviewed when:

- A new source category is added to `DISCOVERY-SOURCES.md`.
- A licence change at a source is detected during refresh.
- A community authority issues new naming or sensitivity guidance.
- A user report flags a privacy, cultural, or accuracy concern.

Reports go to the project issue tracker. Anyone may propose changes.

---

*Adopted 2026-05-11. The principles above are non-negotiable; specific
implementation choices may evolve.*
