# Image sources — brainstorm and registry

This document does two jobs:

1. **Brainstorm**: catalogue every plausible upstream source for a representative
   island photo, with licensing and ethical posture.
2. **Registry**: define the canonical `images[i].source` codes used in
   `data/islands.json`, so any photo can be cross-referenced back to the page
   that supplied it.

See also: [`ETHICS.md`](ETHICS.md), [`DATA-SCHEMA.md`](DATA-SCHEMA.md) (the
`images[]` field), [`PIPELINE.md`](PIPELINE.md) (enrichment runs).

---

## A. Brainstorm — universe of candidate sources

Status legend: ✅ in use · 🟡 plausible, not yet integrated · 🛑 ethically off-limits or licence-incompatible.

### Open / Wikimedia ecosystem

| # | Source | Licence | Access | Status | Notes |
|---|---|---|---|---|---|
| 1 | **Wikimedia Commons via Wikidata P18** | CC-BY-SA, CC-BY, CC0, PD | SPARQL `wikidata.org/sparql` + Commons API | ✅ | Highest confidence: image is attached to the Q-ID itself. |
| 2 | **MediaWiki `pageimages`** (Wikipedia lead) | inherits Commons file licence | `en.wikipedia.org/w/api.php?action=query&prop=pageimages` | ✅ | Used as P18 fallback for entries with a Wikipedia article but no P18. |
| 3 | **Commons category traversal by Q-ID** | CC-BY-SA, CC-BY, CC0, PD | Commons API `categorymembers` (the Commons sitelink on a Q-ID points at a Commons category) | 🟡 | Untapped. Many Q-IDs have a Commons *category* but no P18; the category often contains 10+ photos. Pick the highest-scored (`Quality image` / `Featured picture`). |
| 4 | **Commons radial geo-search** | CC-BY-SA, CC-BY, CC0, PD | Commons API `list=geosearch&gscoord=lat\|lng&gsradius=500` | 🟡 | Powerful but **mismatch-prone**. Photos of the same loch shore can read as "on the island". Use only with a strict name-match filter and a `suspect` flag in the report. |
| 5 | **Commons "Category:Islands of <X>" tree** | CC-BY-SA, CC-BY, CC0, PD | Commons API category traversal | 🟡 | Country/region category trees curated by Wikimedians. Good for sanity-checking other sources. |
| 6 | **Wikivoyage** | CC-BY-SA 4.0 (text); images via Commons | API similar to Wikipedia | 🟡 | Travel-oriented articles often have *different* lead images than Wikipedia; useful as a tiebreaker. |

### UK & Ireland geophoto projects

| # | Source | Licence | Access | Status | Notes |
|---|---|---|---|---|---|
| 7 | **Geograph Britain and Ireland** | **CC-BY-SA 2.0** (every photo) | XML/JSON API at `geograph.org.uk/api/` + `syndicator.php` | 🛑 (direct) / ✅ (indirect via Commons) | The public API now returns 451 ("Unavailable For Legal Reasons") for unauthenticated requests — appears to be a UK regulatory block. **However**, a very large fraction of Geograph photos have been re-uploaded to Wikimedia Commons (you can spot them by the `_-_geograph.org.uk_-_NNN.jpg` filename suffix), so we surface them transparently via #3 and #4 below. |
| 8 | **Geograph Ireland** | **CC-BY-SA 2.0** | Same API family at `geograph.ie` | 🛑 / ✅ via Commons | Same status as #7. |
| 9 | **GeoHack catalogue** | (links only) | `tools.wmflabs.org/geohack` | — | Not a photo source, but used to surface other sources for a given coordinate. |

### Other open photo libraries

| # | Source | Licence | Access | Status | Notes |
|---|---|---|---|---|---|
| 10 | **Flickr Commons** | "no known copyright restrictions" / PD | Flickr API `flickr.commons.getInstitutions` etc. | 🟡 | Institutional historical photos (National Library of Scotland, Library of Congress, etc.). Modest island coverage but high quality. |
| 11 | **Flickr CC-BY / CC-BY-SA pool** | CC-BY 2.0, CC-BY-SA 2.0 | Flickr API `photos.search` with `license=4,5` | 🟡 | Requires API key. Large pool but high mismatch risk; needs strict filters. |
| 12 | **OpenStreetMap `image=*` tag** | Tag is ODbL; image rights inherit from URL | We already have `osmType`+`osmId`; one Overpass call gets `tags.image` | 🟡 | Small but high-confidence: the photo URL is on the island element itself. Some are Flickr/Commons; some are personal websites. We must inspect the host & licence before adopting. |
| 13 | **National Library of Scotland Maps & Images** | OGL / NLS Open Licence (varies) | NLS API / Iframe embeds | 🟡 | Historic maps, not photos; useful for the "history" prose, not the image field. |

### Statutory bodies (OGL or equivalent)

| # | Source | Licence | Status | Notes |
|---|---|---|---|---|
| 14 | **NatureScot** (formerly SNH) | OGL v3.0 | 🟡 | Photo library of NNRs, SSSIs. Need to navigate site to extract individual file URLs. |
| 15 | **Natural England** | OGL v3.0 | 🟡 | Same model for English NNRs/SSSIs. |
| 16 | **Natural Resources Wales** | OGL v3.0 | 🟡 | Welsh statutory equivalent. |
| 17 | **NIEA (NI Environment Agency)** | OGL v3.0 | 🟡 | NI sites. |
| 18 | **NPWS (Ireland)** | OGL Ireland-equivalent? | 🟡 | Check; not all NPWS material is open. |
| 19 | **Historic Environment Scotland** | OGL v3.0 (for many) | 🟡 | Built heritage on islands (brochs, castles, abbeys). |
| 20 | **Historic England / Cadw / HED NI** | OGL v3.0 (for many) | 🟡 | Built heritage equivalents. |
| 21 | **Britain From Above** (RCAHMS / HE) | Varies; some PD, some all-rights | 🟡 | Historic aerial photos. Per-photo licence check required. |

### Trusts and NGOs (case-by-case)

| # | Source | Licence | Status | Notes |
|---|---|---|---|---|
| 22 | **National Trust for Scotland press library** | Editorial use; **not redistribution** | 🛑 | Off-limits without per-photo permission. |
| 23 | **National Trust press library** | Editorial use only | 🛑 | Same. |
| 24 | **RSPB image library** | Editorial use only | 🛑 | Same. |
| 25 | **John Muir Trust photos** | All-rights-reserved | 🛑 | Same. |
| 26 | **Highland Council / island development trusts** | Varies | 🟡 | Some publish under OGL or CC; treat per case. |

### Tourism boards

| # | Source | Licence | Status | Notes |
|---|---|---|---|---|
| 27 | VisitScotland / VisitWales / Discover Northern Ireland / Fáilte Ireland / Visit Isle of Man / Visit Guernsey / Visit Jersey | Editorial / press use only | 🛑 | Photos are licensed for tourism marketing, not for general redistribution. Skip unless an individual asset is explicitly CC. |

### Photo-sharing platforms

| # | Source | Status | Notes |
|---|---|---|---|
| 28 | Unsplash / Pexels / Pixabay | 🛑 | Licences are permissive but the *provenance chain* is opaque — we can't always verify the uploader was the photographer. Skip to avoid laundering. |
| 29 | Instagram / Facebook / Twitter / TikTok | 🛑 | No consent chain. Off-limits as a matter of policy (see `ETHICS.md` §5). |
| 30 | Reddit r/europe etc. | 🛑 | Same. |

### AI generation

| # | Source | Status | Notes |
|---|---|---|---|
| 31 | Stable Diffusion / DALL-E / Midjourney for "an island that looks like X" | 🛑 | **Strictly forbidden.** Misrepresentation. We only show photographs of the actual island. |

---

## B. Registry — canonical `images[i].source` codes

Every photo in `data/islands.json` carries a `source` field. This table tells
you how to cross-reference it.

| `source` code | What `sourceRef` contains | Cross-reference URL pattern | Licence default | Cache file |
|---|---|---|---|---|
| `curated` | `images[i].sourcePageUrl` (full URL) | The `sourcePageUrl` itself | varies — must be set explicitly | n/a (hard-coded in `data/curated.json`) |
| `wikidata` | Q-ID, e.g. `Q80967` | `https://www.wikidata.org/wiki/Q80967` (find P18 there) | inherited from Commons file | `data/cache_wikidata.json` |
| `wikipedia` | Wikipedia page title, e.g. `Isle_of_Skye` | `https://en.wikipedia.org/wiki/Isle_of_Skye` | inherited from Commons file | `data/cache_pageimages.json` |
| `commons` *(reserved)* | Commons filename, e.g. `Skye_001.jpg` | `https://commons.wikimedia.org/wiki/File:Skye_001.jpg` | per file | `data/cache_commons.json` |
| `commons-category` | Commons category name, e.g. `Category:Isle_of_Skye` | `https://commons.wikimedia.org/wiki/<sourceRef>` | per file | `data/cache_commons_category.json` (v3) |
| `commons-geosearch` | `"lat,lng;radius_m"` of the query, e.g. `57.273,-6.215;500` | (no canonical page; the per-image `sourcePageUrl` is the Commons file page) | per file (often CC-BY-SA 2.0 — many are Geograph carries) | `data/cache_commons_geo.json` (v3) |
| `geograph` | Geograph photo id (numeric, e.g. `1234567`) | `https://www.geograph.org.uk/photo/<sourceRef>` | **CC-BY-SA 2.0** | `data/cache_geograph.json` (v3) |
| `geograph-ie` | Geograph IE photo id | `https://www.geograph.ie/photo/<sourceRef>` | **CC-BY-SA 2.0** | `data/cache_geograph_ie.json` (v3) |
| `osm-image-tag` | `osmType/osmId`, e.g. `relation/544726` | `https://www.openstreetmap.org/<osmType>/<osmId>` (tag `image` in the body) | inherited from the URL | `data/cache_osm_image_tag.json` (v3) |
| `flickr-cc` | Flickr photo id | `https://www.flickr.com/photo.gne?id=<sourceRef>` | CC-BY 2.0 or CC-BY-SA 2.0 (record `images[i].license` exactly) | `data/cache_flickr.json` (v3) |
| `flickr-commons` | Flickr photo id | Same URL pattern | "no known copyright restrictions" | `data/cache_flickr_commons.json` (v3) |
| `ogl-natureScot` | Page URL on nature.scot | The URL | OGL v3.0 | `data/cache_natureScot.json` (v3+) |
| `ogl-naturalEngland` | Page URL on naturalengland.org.uk | The URL | OGL v3.0 | `data/cache_naturalEngland.json` (v3+) |
| `ogl-nrw` | Page URL on naturalresources.wales | The URL | OGL v3.0 | `data/cache_nrw.json` (v3+) |
| `ogl-nieaorni` | Page URL on daera-ni.gov.uk | The URL | OGL v3.0 | `data/cache_niea.json` (v3+) |
| `ogl-hes` | Page URL on historicenvironment.scot | The URL | OGL v3.0 | `data/cache_hes.json` (v3+) |
| `ogl-historicEngland` | Page URL on historicengland.org.uk | The URL | OGL v3.0 | `data/cache_he.json` (v3+) |

### Hard rules for adding a new image to `images[]`

Every entry **must** include all of:

- `url` — displayable thumbnail URL (HTTPS).
- `source` — one of the codes above.
- `sourceRef` — the upstream identifier (see column 2). Stable, queryable.
- `sourcePageUrl` — direct URL to the page where the photo was found.
- `license` — SPDX-ish: `CC-BY-SA-2.0`, `CC-BY-SA-4.0`, `CC-BY-4.0`, `CC0`,
  `PD`, `OGL-3.0`, …
- `attribution` — human-readable display string, format:
  `"Photo by <Author> (<License>) via <Source>"`.

Missing any of these = bug. The image must not ship.

### Cross-referencing from the running app

Each `images[i]` on an island has `sourcePageUrl`. The frontend
(`renderDetails()` in `app.js`) will surface this as a small link under the
photo, e.g.:

> Photo by Jane Doe (CC-BY-SA 2.0) — [source ↗](https://geograph.org.uk/photo/1234567)

That is the cross-reference: clicking it lands you on the upstream page where
the image lives, with full licence terms and the photographer's name.

---

## C. Ranking for v3 enrichment (post-v2)

v3 (in flight as of 12:23) works through the remaining 5,662 unphotographed
islands in this order:

1. **Commons category by Q-ID** (#3). Pool: ~1,626 islands with a Q-ID but
   no P18. Smoke-tested on `osm-way-209273242` (A' Chleit) → adopted in 3.3s.
2. **OSM `image=*` tag** (#12). Pool: ~4,917 OSM elements. Only adopts if
   the URL host is in `HOST_ALLOW` (Commons, Wikipedia, Geograph) so licence
   is inferable.
3. **Commons radial geosearch** (#4). Fallback for everything left. Pool: any
   island with a `lat`/`lng`. Smoke-tested on `llyn-y-fan-fach-w23147971` →
   adopted a Geograph-via-Commons photo within 106 m, full attribution, in
   3.5s.

Acceptance rules (spot-check):
- Source #1 (Commons category): no extra check — the category is keyed to the
  Q-ID itself.
- Source #2 (OSM tag): host must be allow-listed (`commons.wikimedia.org`,
  `upload.wikimedia.org`, `geograph.org.uk`, …).
- Source #3 (geosearch): adopt if filename or caption **mentions the island
  name**, OR distance ≤ 200 m AND filename passes the
  `_looks_like_non_photo` filter. Photos that match only on distance are
  flagged `_suspect: true` in the report.

Direct Geograph (#7, #8) and Flickr CC (#11) are deferred (auth required).
Statutory bodies (#14–20) deferred (slow per-photo; better as a curated
workstream).

**Stopping criteria for v3**: continue down the ranking until either:

- the island has a `primary` image with `images[0].license` set, or
- all listed sources have been tried and returned no candidate. The island
  remains without an image and is recorded in
  `image_enrichment_report.json → without_image[]` with the reasons.

---

## D. Spot-check & "suspect" handling

Carried over from v1 (`enrich_images.py`) and extended for v3:

For every candidate photo before commit:

1. **Name proximity**: does the filename / title / caption contain the
   island's name (or any cultural-language name)? If yes → OK. If no →
   continue.
2. **Geo proximity**: is the photo's geo-tag within `r` metres of the island
   centroid? Threshold:
   - Commons P18: skip check (we trust Wikidata).
   - Commons category: 1500 m (categories can include neighbouring shores).
   - Geograph: 500 m default, 1000 m for islands < 0.1 km².
   - Commons geosearch: must be ≤ 200 m AND name proximity must pass.
3. **Negative-cache**: if either check fails, write the candidate to
   `cache_suspects.json` rather than dropping silently. Surface in the report.

The frontend never renders an image flagged `suspect: true` as `primary`.
It can still appear in a "Other photos" gallery once we have one.

---

## E. Per-source attribution templates

When constructing `images[i].attribution`:

| Source | Template |
|---|---|
| Wikimedia Commons (P18 / pageimages / categories / geosearch) | `Photo by <Author>, via Wikimedia Commons (<License>)` |
| Geograph BI / IE | `<Photographer> via Geograph project (CC-BY-SA 2.0)` |
| Flickr CC | `<Author> on Flickr (<License>)` |
| Flickr Commons | `<Holding Institution> via Flickr Commons (no known copyright restrictions)` |
| OSM `image` tag | `<Domain of URL> via OpenStreetMap` |
| OGL statutory body | `Contains public-sector information licensed under OGL v3.0 (<Body>)` |
| Curated | `<Hand-set in curated.json>` |

`<Author>` is whatever the upstream API returns. If empty, use `Unknown`.
Never invent a photographer name.

---

## F. What ships in the front-end

Every photo in `app.js → renderDetails()` will be rendered with:

```html
<figure class="island-photo">
  <img src="{images[0].url}" alt="{images[0].caption or island.name}">
  <figcaption>
    {images[0].attribution}
    · <a href="{images[0].sourcePageUrl}" target="_blank" rel="noopener">source ↗</a>
  </figcaption>
</figure>
```

A photo without an attribution string OR without a sourcePageUrl is a bug and
must not ship.

---

## G. Updating this document

- New code values (when a new source is integrated) → add to the registry
  table in §B with cache file and licence default.
- New brainstormed sources → §A.
- Yield results after a run → §C.
- Per-source attribution templates → §E.

---

## H. Per-entity photos (post 2026-05-13 schema enrichments)

Photos enriched alongside the 2026-05-13 enrichment workstream (hills,
lighthouses, RSPB reserves) live under the same `images[]` array on the
island record, but each entry carries an extra `subject:` key so the UI
can group them. See
[`SCHEMA-ENRICHMENTS-2026-05-13.md`](SCHEMA-ENRICHMENTS-2026-05-13.md)
§6 for the full schema.

```jsonc
{
  "subject": "island" | "lighthouse" | "hill" | "wildlife",
  "subjectRef": "neist-point-lighthouse",   // loose ID matching an entry in lighthouses[]/hillsOn[]/wildlifeColonies[]
}
```

`subject: "island"` is the implicit default for every existing photo;
no migration is required. Photos for **wildlife colonies** are
deliberately **not** ingested at this stage — per ETHICS §5 we don't
want to compose a "best photo-spotting locations" page that could
drive disturbance.

Per-entity quota (enforced in the ingestion scripts):

- **Hills:** 1 photo per hill, attached to the parent island's
  `images[]` with `subject: "hill"`.
- **Lighthouses:** 1–2 photos per lighthouse (exterior + close-up if
  both available), with `subject: "lighthouse"`.
- **RSPB reserves:** 1 photo per reserve (the reserve itself, never a
  species photo), with `subject: "wildlife"`.
- **Wildlife colonies:** 0 photos (presence is text-only).

The lookup chain for each entity is identical to §C above:

1. Wikidata P18 if a Q-ID is in the entity's source data.
2. Otherwise `prop=pageimages` from the matching Wikipedia article.
3. Otherwise Commons `list=geosearch` within 200 m of the entity's
   coordinates, with strict name-anchor filtering.

In all cases the full attribution chain (`url`, `source`, `sourceRef`,
`sourcePageUrl`, `license`, `attribution`) is mandatory. Missing any
field is a bug; the photo must not ship.
