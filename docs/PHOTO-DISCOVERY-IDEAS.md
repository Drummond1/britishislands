# Photo discovery ideas — high-confidence verification

Brainstorm of **outside-the-box** ways to attach a representative photograph to an
island record with **~90% confidence** that the image actually depicts *that*
island (not a nearby headland, the wrong archipelago, or a generic “Scottish
coast”). Complements [`IMAGE-SOURCES.md`](IMAGE-SOURCES.md) (registry + sources
already in use) and [`ETHICS.md`](ETHICS.md) (licence allowlist).

**Not in scope here:** implementation, new `images[i].source` codes, or scripts.
Use this doc to prioritise the next enrichment passes.

---

## Shared verification ladder (target ~90%)

Most ideas below assume one or more of these checks. Combining **two independent
signals** (structured link + geo, or Q-ID + licence) is the default path to ~90%.

| Tier | Signal | Typical confidence boost |
|------|--------|----------------------------|
| A | Wikidata Q-ID on the **file** or **category** (`depicts`, `P180`, `main subject`) | +40% |
| B | OSM `wikidata=Q…` on the island polygon + file/category points at same Q | +35% |
| C | Commons/Wikipedia **title or caption** matches canonical island name (incl. `name:gd` / Logainm form) | +25% |
| D | Geo: media coordinates inside island polygon (or ≤50 m for tiny islets) | +20% |
| E | Human-readable **source page** states the place name (archive caption, planning doc title) | +15% |
| F | **Second source** agrees (e.g. P18 + depicts=Q; or OSM `wikimedia_commons` + category member) | caps mismatch risk |

Reject or flag `suspect` when only **D** (geo alone) or only **C** (name substring on
a 500 m geosearch hit) is present — those plateau around 60–70% on obscure islets.

---

## Idea catalogue (28 sources + 1 meta-pattern)

Yield and difficulty are scored for **UK/Ireland obscure islets** (unnamed OSM
islands, <5 ha, no enwiki, often no Wikidata). Yield: **Low** / **Med** / **High**.
Difficulty: **Easy** (API + cache) / **Med** (multi-step or regional portals) /
 **Hard** (scraping, PDFs, manual licence per asset).

### Wikimedia & Wikidata graph

| # | Source | Licence posture | Verification method (~90%) | Yield (obscure) | Difficulty |
|---|--------|-----------------|------------------------------|-----------------|------------|
| 1 | **Wikidata P180 on island item** (“depicts” incoming: files/items that depict this place) | ✅ CC-BY-SA / CC-BY / CC0 / PD via Commons | SPARQL: `?file wdt:P180 wd:Q<island>`; require Commons file page + `extmetadata.LicenseShortName`; optional **Tier F** if P18 also exists | **Med** — strong for Q-ID’d islands, weak without Q | **Med** |
| 2 | **Commons structured data `depicts` (P180) on File:** | ✅ same | Query Commons EntitySearch / SD API for `depicts=Q<island>`; reject files whose `depicts` is broader (e.g. “Scotland”) unless island is only place in caption | **Med** | **Med** |
| 3 | **Reverse Commons depicts** (all files depicting Q-ID, not just P18 on item) | ✅ same | Same as #2 but indexed as primary harvest; rank by `Quality image`, date, and **Tier C** caption match | **Med–High** among islands with Q | **Med** |
| 4 | **Wikidata “subject of” (P921) on media-adjacent items** | ✅ when media is Commons | Works for notable islets with dedicated books/films; traverse P921 → linked items → P18/P180; weak for rock islets | **Low** | **Hard** |
| 5 | **Commons category from P373** (not only sitelink category) | ✅ same | `wdt:P373` on Q-ID → category members; require **Tier C** (filename/caption contains island name or AÀA/Logainm alias) + **Tier D** (coord on file inside polygon) | **Med** | **Easy** (extends v3) |
| 6 | **Wikipedia all-languages `pageimages`** | ✅ inherits Commons licence | `wbgetentities` sitelinks → each wiki `pageimages`; match **Tier C** via wgTitle vs island names; **Tier F** if two wikis share same lead file | **High** for named islands with any wiki article; **Low** for pure OSM rocks | **Easy** |
| 7 | **Wikivoyage multi-language lead images** | ✅ CC-BY-SA text; images via Commons | Same as #6 but often different lead photo; still require **Tier C** name match on file page | **Low–Med** | **Easy** |
| 8 | **DBpedia / Wikipedia infobox `image` property** | ✅ when URI is Commons | Parse infobox resource → Commons file; **Tier A** if `dbo:wikiPageWikiLink` equals island Q | **Med** for wikidata-linked articles | **Med** |

### OpenStreetMap & linked catalogues

| # | Source | Licence posture | Verification method (~90%) | Yield (obscure) | Difficulty |
|---|--------|-----------------|------------------------------|-----------------|------------|
| 9 | **OSM `wikimedia_commons=File:…` on island** | ✅ file licence; OSM tag ODbL | Direct tag on `place=island`/`islet` element; **Tier B** if `wikidata=` matches; no geosearch | **Low** globally, **Very high confidence** when present | **Easy** |
| 10 | **OSM `wikidata=Q…` + Wikipedia/Commons sitelink harvest** | ✅ | Overpass `wikidata` → wbgetentities P18/P373; **Tier B** OSM geometry vs Commons coord | **Med** for tagged islets | **Easy** |
| 11 | **OSM `image=*` / `image:0=*` on island or ferry terminal** | ⚠️ per-URL licence audit | Fetch URL; allowlist host (Commons, Flickr CC, gov OGL); **Tier E** caption on landing page; **Tier D** if EXIF coords | **Low** | **Med** |
| 12 | **Ferry terminal / `amenity=ferry_terminal` + KartaView / OpenStreetCam** | ✅ KartaView CC-BY-SA; Mapillary has separate terms — check before use | Buffer 80 m around terminal on **known routes** to islet; pick frames facing channel; **Tier D** + route table in [`FERRIES.md`](FERRIES.md); island must be only landmass in view cone | **Low** for rock islets; **Med** for served islands | **Hard** |
| 13 | **OSM `tourism=viewpoint` + `image` near islet** | ⚠️ per-URL | Viewpoint within 200 m of islet centroid, name tag matches **Tier C** | **Low** | **Med** |

### Citizen science & biodiversity media

| # | Source | Licence posture | Verification method (~90%) | Yield (obscure) | Difficulty |
|---|--------|-----------------|------------------------------|-----------------|------------|
| 14 | **GBIF occurrence media** (filtered CC licences) | ✅ CC-BY / CC-BY-SA / CC0 only; exclude NC | Occurrences with `media` inside island polygon; prefer habitat/plant shots where **recordedBy** + **locality** string matches island name; still **Tier D** only → flag `suspect` unless name match | **Low** for tiny rocks; **Med** for vegetated islets | **Med** |
| 15 | **eBird checklists with photos** (Macaulay) | ⚠️ **often not redistribution-safe** — Macaulay Library terms are **not** equivalent to CC-BY for bulk reuse; treat as **discovery lead** only unless licence explicitly CC | Use only to find Commons/Wikipedia cross-posts; **do not ingest** without counsel — mark **not ETHICS-compliant** for direct embed | **Med** sightings, **Low** legal yield | **Hard** |
| 16 | **iNaturalist Research-Grade CC observations** | ✅ CC-BY / CC-BY-SA / CC0 via API | `place_id` or polygon filter + taxon; require coords inside island + observer comment mentions island; **Tier F** with second signal | **Low–Med** | **Med** (script exists) |

### UK/Ireland cultural heritage & memory institutions

| # | Source | Licence posture | Verification method (~90%) | Yield (obscure) | Difficulty |
|---|--------|-----------------|------------------------------|-----------------|------------|
| 17 | **People’s Collection Wales (PCW)** | ✅ many items CC-BY; verify per item | API/search by place name + map browse; **Tier E** catalogue fields + **Tier C** Welsh/English name; georeference when available | **Med** (Wales); **Low** elsewhere | **Med** |
| 18 | **SCRAN (Historic Environment Scotland)** | ⚠️ mixed — many **educational use**; only ingest where item page states **OGL** or CC | Institution filter + manual licence field; **Tier E** caption “Island of X” | **Low–Med** (Scotland) | **Hard** |
| 19 | **Dúchas.ie / National Folklore Collection photos** | ⚠️ per-item; not all CC — many **© NFCI** with limited reuse | Only items explicitly licensed CC-BY or OGL-equivalent; **Tier E** folklore district + place name in metadata | **Low** (Ireland, place-linked stories) | **Hard** |
| 20 | **National Library of Scotland (NLS) digital gallery** | ✅ OGL / NLS open licence on many sets | Search place name + “island”; **Tier E** catalogue description; georeferenced scans → **Tier D** | **Low–Med** | **Med** |
| 21 | **Britain from Above (HES/RCAHMS)** | ⚠️ per-image | Only frames with explicit OGL/PD on asset page; **Tier D** georeferenced footprint intersects island polygon | **Med** for larger islets; **Low** for rocks | **Hard** |
| 22 | **Museum Wales / Manx National Heritage open collections** | ✅ when marked OGL/CC | Collection API + place name; same as #17 | **Low** (regional) | **Med** |

### Government, planning & marine OGL

| # | Source | Licence posture | Verification method (~90%) | Yield (obscure) | Difficulty |
|---|--------|-----------------|------------------------------|-----------------|------------|
| 23 | **Planning portal OGL aerials** (LPA sites, Environmental Statement appendices) | ✅ OGL v3.0 when stated on document | PDF/image extraction from applications naming island + grid ref; **Tier E** + **Tier D** grid inside polygon; archive URL in provenance | **Med** for islands with recent development; **Low** overall | **Hard** |
| 24 | **Marine conservation / HPMA / MCZ photo libraries** (JNCC, Natural England, NRW, DAERA) | ✅ OGL on many gov.uk assets; verify each | Site search by site name (= official MCZ label); **Tier C** statutory site name must equal island or include islet in site boundary dataset | **Low** (site-scale, not islet-scale) | **Med** |
| 25 | **Council tourism / heritage OGL press galleries** | ✅ when page footer says OGL | Allowlist domains; **Tier E** title “Isle of …” | **Low** | **Med** |
| 26 | **data.gov.uk dataset attachments** (Coastal surveys, Seabed mapping outreach) | ✅ often OGL | Metadata title + bounding box; **Tier D** only with **Tier C** name in attachment filename | **Low** | **Hard** |

### Street-level & panoramic open imagery

| # | Source | Licence posture | Verification method (~90%) | Yield (obscure) | Difficulty |
|---|--------|-----------------|------------------------------|-----------------|------------|
| 27 | **Panoramax** (French public-sector street imagery, growing UK coverage) | ✅ open licence (check collection policy per provider) | Sequence near causeway/ferry; **Tier D** + bearing toward islet; use only where licence confirmed CC-BY-SA or equivalent | **Low** UK today; rising | **Med** |
| 28 | **Mapillary** (CC-BY-SA subset via API) | ⚠️ Mapillary **license changed** — confirm current API terms against [`ETHICS.md`](ETHICS.md); may be ✅ for CC-BY-SA flagged images only | Same geometry as #12; filter `license=CC-BY-SA` | **Low** | **Med** |

### Aggregators & archives (beyond Openverse)

| # | Source | Licence posture | Verification method (~90%) | Yield (obscure) | Difficulty |
|---|--------|-----------------|------------------------------|-----------------|------------|
| 29 | **Europeana** (query place + “island”, licence filter) | ✅ CC0 / CC-BY / CC-BY-SA filter | Require `edm:isShownBy` licence URI in allowlist; **Tier C** + **Tier E** subject fields | **Low–Med** | **Med** |
| 30 | **British Library Flickr Commons** | ✅ “no known copyright restrictions” / PD | Institution search + manual **Tier C** place in title | **Low** | **Easy** |
| 31 | **Flickr geotagged CC** (API `license=4,5,6,9,10`) | ✅ CC-BY / CC-BY-SA | Strict: coords inside polygon + title/description contains island name + **Tier F** match to Logainm/AÀA alias | **Low** (noisy) | **Med** |

### Cross-source & “boring but lethal” patterns

| # | Source | Licence posture | Verification method (~90%) | Yield (obscure) | Difficulty |
|---|--------|-----------------|------------------------------|-----------------|------------|
| 32 | **Structured peer verification (meta)** | ✅ (inherits child sources) | Adopt image only if **two** of: {Q-ID link, OSM wikidata match, name authority match, coord-in-polygon, independent catalogue page} | **High** precision; reduces false positives from geosearch | **Easy** as policy layer |
| 33 | **Geograph via Commons filename suffix** (`_-_geograph.org.uk_-_`) | ✅ CC-BY-SA 2.0 | Reverse lookup: Commons search `incategory:"Geograph"` + coord in polygon + **Tier C** Geograph title | **Med** where Geograph coverage exists | **Med** |
| 34 | **Openverse with mandatory dual filter** | ✅ CC0/CC-BY/CC-BY-SA | Not standalone: require **Tier C** + **Tier D** + exclude stock keywords (“landscape”, “aerial view”) | **Low** for obscure | **Easy** |
| 35 | **Wikidata P973 / P856 external URLs** (discovery only) | ⚠️ per landing page | Already used in web-discovery staging; human/allowlist licence check before merge | **Low–Med** | **Med** |

### Explicitly out-of-band (documented to avoid rework)

| Source | Why skip or lead-only |
|--------|----------------------|
| eBird / Macaulay direct embed | Licence not aligned with [`ETHICS.md`](ETHICS.md) redistribution list |
| Unsplash / Pexels / Instagram | Provenance opacity or no consent chain |
| Maxar / commercial satellite | Commercial + surveillance ethics |
| RSPB / NT press libraries | Editorial-only |

---

## Top 10 ranked by yield × confidence

Scoring: **Yield** (obscure islets) Low=1, Med=2, High=3. **Confidence** at
verification ceiling Low=1, Med=2, High=3. **Product** = Yield × Confidence
(higher = prioritise).

| Rank | Idea # | Source | Yield | Conf. | Product | Rationale |
|------|--------|--------|-------|-------|---------|-----------|
| 1 | 32 | **Structured peer verification (2+ signals)** | 3 | 3 | **9** | Meta-layer; upgrades every pipeline without new API |
| 2 | 3 | **Reverse Commons `depicts=Q`** | 2 | 3 | **6** | Strongest semantic link short of P18 on the island item |
| 3 | 6 | **All-language Wikipedia pageimages** | 3 | 2 | **6** | Broad coverage for any island with *any* wiki article |
| 4 | 9 | **OSM `wikimedia_commons=File:`** | 1 | 3 | **3** | Rare but near-certain when mappers attached a file |
| 5 | 10 | **OSM `wikidata` + P18/P373 harvest** | 2 | 3 | **6** | Tight coupling of geometry and Wikidata graph |
| 6 | 1 | **Wikidata P180 incoming** | 2 | 3 | **6** | Same graph as #3; sometimes richer than P18 alone |
| 7 | 5 | **P373 category + name + coord gate** | 2 | 2 | **4** | Catches “category but no P18” cases safely |
| 8 | 33 | **Geograph-on-Commons reverse** | 2 | 2 | **4** | UK/Ireland coastal coverage without Geograph API 451 |
| 9 | 17 | **People’s Collection Wales** | 2 | 2 | **4** | Regional but strong place metadata for Welsh islands |
| 10 | 23 | **Planning portal OGL aerials** | 2 | 2 | **4** | Surprising yield for small islets in active LPAs |

**Honourable mentions** (product 3–4): #2 Commons SD depicts; #11 OSM `image=*`
with allowlist; #14 GBIF media (strict licence filter); #27 Panoramax as UK
coverage grows; #31 Flickr geo+name with **Tier F**.

**Deprioritise for obscure islets** despite hype: raw Commons geosearch, Openverse
alone, eBird/Macaulay direct, street-view at scale without ferry/name gates.

---

## Suggested pass order (no code)

1. Turn on **#32** everywhere (reject single-signal geosearch adoptions).
2. Batch **#3 / #1 / #2** depicts graph for all islands with Wikidata Q.
3. Expand **#6** to full sitelink set (cy, ga, gd, gv, kw, fr, …).
4. Overpass sweep **#9–#11** once per OSM island refresh.
5. Regional OGL tranches: **#17–#19**, then **#23–#24** for gaps.
6. Street imagery **#12 / #27** only for ferry-served islands in validation set.

---

## Related docs

- [`IMAGE-SOURCES.md`](IMAGE-SOURCES.md) — registry and in-use sources
- [`ETHICS.md`](ETHICS.md) — licence allowlist
- [`PIPELINE.md`](PIPELINE.md) — how enrichment runs are chained
- [`VALIDATION.md`](VALIDATION.md) — regression islands to test new passes
