# Discovery sources — British Isles islands within 50 mi of the UK

This catalogue documents every data source we have evaluated for completing
the island coverage of the British Isles + Ireland + the Crown Dependencies.
It is the output of eight parallel research workstreams. Nothing here has
been ingested yet — the next session will act on the action plan at the end.

**Current dataset state:** `data/islands.json` = 5,892 named islands
(Scotland 2,776 / Ireland 1,747 / England 693 / Northern Ireland 447 /
Wales 139 / Crown Dependency 90; by type: sea 4,600 / lake 1,066 /
river 226). Initial Wikidata Q-ID coverage = 1,302; initial Wikipedia URL
coverage = 689.

## Reading the manifest

Each row records:

- **Licence**: only `Open Government Licence v3.0`, `CC0`, `CC-BY`,
  `CC-BY-SA` or equivalent open licences are accepted for redistribution.
  Anything else is `SKIP` or `reference-only`.
- **Yield estimate**: islands *new to our 5,892 baseline*, after de-duplication.
- **Priority**: the action plan at the foot of this file picks the top 5.
- **Ethical considerations**: per-source treatment of sacred sites, sensitive
  species, linguistic authority, and licence obligations. The cross-cutting
  guardrails live in [`ETHICS.md`](./ETHICS.md).

---

## Workstream 1 — Government & authoritative open data

| Source | Jurisdiction | Licence | Yield vs 5,892 | Priority |
| --- | --- | --- | --- | --- |
| **OS Open Names** | GB | OGL v3.0 | 200–500 new named features + bilingual GD/CY/SC name alternates | **HIGH** |
| **OS Boundary-Line** | GB | OGL v3.0 | Tens to a few hundred (offshore islands ≥0.4 ha or with buildings) | **HIGH** |
| **Tailte Éireann — Islands (National 1m Map of Ireland)** | IE | CC-BY-4.0 | 20–80 new + authoritative Irish-language primary names | **HIGH** |
| **OSNI Open Data — Largescale Boundaries (NI Outline)** | NI | OGL v3.0 | 30–100 new tiny lough islets (Strangford, Lower Erne) | **HIGH** |
| **National Records of Scotland — Island (Scotland) boundaries** | Scotland | OGL v3.0 | 0–50 new; provides authoritative "is inhabited" flag | **HIGH** |
| **NatureScot Open Data — SSSI / SPA / SAC** | Scotland | OGL v3.0 | 50–150 new tiny named skerries (Sula Sgeir, Stac an Armin, Hyskeir…) | **HIGH** |
| **UKHO ADMIRALTY Marine Data Portal — INSPIRE subset** | UK+IoM+CI | OGL v3.0 | Mostly bathymetry/maritime-limits; new-island yield small; "drying rocks" S-57 feature class stays in the **commercial ENC** product | MEDIUM (limited) |
| **JNCC UK Marine Protected Area datasets** | UK-wide | OGL v3.0 | ~10–30 new uninhabited rock/skerry names from MPA citations | MEDIUM |
| **Defra MAGIC Map** | England | OGL v3.0 | 10–30 new tiny rocky stacks named in SSSI citations | MEDIUM |
| **DataMapWales / NRW open data** | Wales | OGL v3.0 | Few new entries; high value for Welsh-language primary forms | MEDIUM |
| **Marine Scotland Maps NMPi** | Scotland | OGL v3.0 (per-layer) | Aggregator — direct upstream sources better | MEDIUM |
| **OpenDataNI catalogue** | NI | OGL v3.0 | Surfaces OSNI products + NIEA ASSI | MEDIUM |
| **Tailte Éireann — Townlands gazetteer** | IE | CC-BY-4.0 | 30–100 new small ROI islets via "Inis-"/"Oileán-" townland names | MEDIUM |
| **Isle of Man Government / MANNGIS** | IoM | OGL (IoM) | ~10–20 new tiny rocks (Kitterland, Burroo, Thousla, Chicken Rock) | MEDIUM |
| **States of Jersey GIS / Digimap Guernsey** | Jersey, Guernsey | **NOT open** — partner-only / unclear ToS | EXCLUDE from bulk ingest; manual research only |
| **Welsh Lle Geo-Portal** | Wales | (decommissioned 2023) | Superseded by DataMapWales | SKIP |
| **OS Open Map – Local, OS Open Zoomstack** | GB | OGL v3.0 | Dominated by OS Open Names + Boundary-Line | LOW / SKIP |

---

## Workstream 2 — Conservation & wildlife organisations

| Source | Jurisdiction | Licence | Yield | Priority |
| --- | --- | --- | --- | --- |
| **JNCC UK Protected Area Datasets (SAC / SPA / Ramsar)** | UK-wide | OGL v3.0 | 40–80 new (Flannan, St Kilda, Treshnish components) | **HIGH** |
| **NPWS Ireland — Designated Site Boundary Data** (SAC / SPA / NHA / pNHA) | IE | CC-BY-4.0 | 60–120 new (Connemara, Erne/Mask/Corrib lough islands, West-coast stacks) | **HIGH** |
| **NatureScot Sitelink — SSSI & NNR** | Scotland | OGL v3.0 | 80–150 new Outer Hebridean / Shetland / Orkney stacks | **HIGH** |
| **Natural England — Designated Sites via MAGIC / Defra DSP** | England | OGL v3.0 | 20–40 new (Scilly + Farne archipelago sub-features) | **HIGH** |
| **Natural Resources Wales — SSSI on DataMapWales** | Wales | OGL v3.0 | 10–20 new Pembrokeshire/Cardigan islets | **HIGH** |
| **NIEA / DAERA — Areas of Special Scientific Interest (ASSI) on OpenDataNI** | NI | OGL v3.0 | 30–60 new (Lough Erne + Strangford Lough archipelagos) | **HIGH** |
| **RSPB Reserves (open data)** | UK-wide | OGL v3.0 | 5–10 new sub-reserve features | MEDIUM |
| **National Trust + National Trust for Scotland properties** | E+W+NI / Scot | OGL / CC-BY-4.0 | 0–8 new (mostly already known: Brownsea, Farne, St Kilda, Iona) | MEDIUM |
| **The Wildlife Trusts (geoportal)** | UK-wide | mixed OGL / CC-BY (per-trust) | 5–10 new Ulster/Cornwall WT islets | MEDIUM |
| **Jersey ASP + Ramsar (gazetted instruments)** | Jersey | OGL-equivalent (Crown instruments) | 10–20 new (Écréhous, Minquiers islets) | MEDIUM |
| **Guernsey Ramsar + Sites of Special Significance** | Guernsey | gov.gg attribution | 10–20 new (Humps, Casquets, Ortac, Burhou) | MEDIUM |
| **Seabird Monitoring Programme (SMP)** | UK+IE+IoM+CI | RESTRICTIVE (gated; Schedule 1 species rules) | High *name yield* (~150–300 stacks/holms) but **incompatible with public redistribution**; site-name list only with BTO/JNCC sign-off | **SKIP unless explicit sign-off** |
| **IUCN WDPA / Protected Planet** | global | **NON-COMMERCIAL only** | Fully duplicated by upstream national sources | **SKIP** |
| **RSPB IBA (current polygons)** | UK | **NON-COMMERCIAL bespoke** | ~5–15 new in principle but licence prevents redistribution | **SKIP** |
| **Scottish Seabird Centre PDFs** | Scotland | © SSC (no spatial feed) | 0 new; use only for narrative text on existing islands | SKIP |
| **Marine Conservation Society reserve list** | UK | site-only | 0 new; JNCC covers the surface authoritatively | SKIP |
| **Hebridean Whale & Dolphin Trust datasets** | Scotland (Hebrides) | aggregated → JCDP | Out of scope (cetacean records, not island toponyms) | SKIP |

---

## Workstream 3 — Academic & scholarly inventories

| Source | Jurisdiction | Licence | Yield | Priority |
| --- | --- | --- | --- | --- |
| **Wikipedia — "List of islands of Ireland"** | RoI + NI | CC BY-SA 4.0 | 100–200 new (Strangford Lough, Clew Bay, Cork Harbour, Shannon Estuary) | **HIGH** |
| **David Walsh, *Oileáin* (free PDF + book)** | RoI + NI | Free PDF, **terms ambiguous** — verify with author | 150–200 obscure Irish islets uniquely in Oileáin (688 documented islands) | **HIGH** (with permission) |
| **The SIBs (Significant Islands of the British Isles & Ireland) — Alan Holmes / hill-bagging.co.uk** | GB+IE | private compilation; contact Alan Holmes | 30–80 stacks/holms (1,700+ SIB+SQUIB entries) | **HIGH** (contact owner first) |
| **Wikipedia — "List of islands of Scotland"** | Scotland | CC BY-SA 4.0 | 20–50 new in stacks/crannogs/former-island sections | **HIGH** |
| **Logainm.ie — Placenames Database of Ireland** | RoI + NI cross-border | CC-BY-4.0 | 100–300 new + authoritative Irish-language forms (~2,000–3,000 OIL records) | **HIGH** |
| **Haswell-Smith, *The Scottish Islands* (4th ed.)** | Scotland | © Canongate | 0 new (book in copyright); use for **cross-validation only** of area/elevation | MEDIUM |
| **Dennis & Shreeve, *Butterflies on British and Irish Offshore Islands* (1996) + CABI supp. appendix** | British Isles + IE | 1996 © + open appendix | 0 new; high yield for area + distance-to-mainland enrichment (73 islands) | MEDIUM |
| **Wikipedia — "List of islands of England"** | England | CC BY-SA 4.0 | Low offshore; medium-high for river/lake sub-pages (Thames + Lake District) | MEDIUM |
| **BGS GeoIndex (onshore + offshore)** | GB | OGL variants | 0 new entities; high yield for geology/bedrock enrichment | MEDIUM |
| **Walkhighlands island-bagging community list** | Scotland | site © | Near-full overlap with SIBs/Haswell-Smith | LOW |
| **EThOS / university thesis repositories** | UK | per-thesis | Low for bulk discovery; medium for spot-checks | LOW |
| **McCoy & Connor (1976) and similar species-area papers** | British Isles | paywalled (JSTOR) | <30 islands as data points; 0 new | LOW |
| **McNally (1978), Carradice (1997) regional books** | IE / Wales | © | 0 new; historical context only | LOW |
| **RGS-IBG / OS "Great Britain's largest islands" geovisualisation** | GB | OGL underlying data | 0 new (82 islands ≥5 km², all in baseline) | LOW |

> Six brief-listed sources could not be verified (Donald Whyte's bagging
> list; Reay Adamson *Islands at the Edge*; McGarry *Islands of Ireland*;
> "Inseanna na hÉireann" as a discrete book; Barber *The Welsh Islands*;
> an RGS "Hidden Hebrides" expedition dataset). The closest verified
> analogues are substituted above (SIBs, Carradice, McNally, Logainm.ie,
> RGS-IBG geovisualisation).

---

## Workstream 4 — Crowd-sourced data beyond OSM `place=island/islet`

| Source | Jurisdiction | Licence | Yield | Priority |
| --- | --- | --- | --- | --- |
| **Wikidata SPARQL on `P31/P279* Q23442` × UK/IE/IoM/Jersey/Guernsey** | UK+IE+IoM+CI | **CC0** | 2,500–3,500 net new (~4,000–5,500 total entities vs our 1,302 Q-IDs) | **HIGHEST** |
| **Wikipedia category-tree recursion (PetScan, depth=6)** | UK+IE+IoM+CI | CC BY-SA 4.0 | 1,000–1,500 net new (~1,800–2,500 after filtering category noise) | **HIGH** |
| **OSM Overpass — `natural=rock`, `seamark:type=rock`, `place=locality` offshore** | UK+IE | ODbL | 400–1,200 new sea stacks / skerries above MHW | **HIGH** |
| **GeoNames (feature codes ISL / ISLET / ISLS / ISLT / RK / RKS)** | UK+IE+IoM+CI | CC-BY-4.0 | 300–800 net new; high value for non-English aliases | MEDIUM |
| **OpenSeaMap (seamark layer)** | UK+IE | ODbL (OSM-derived) | Fully overlaps with Overpass `seamark:*` filter | LOW (fold into Overpass query) |
| **NHLE / Pastscape / Canmore (crowd-contributed heritage references)** | E / Scot | OGL | Low for discovery; medium for enrichment | LOW (also covered in WS7) |
| **Mapcarta / Wikimapia** | global | ODbL / CC BY-SA (OSM-derived) | Essentially duplicative; Wikimapia adds 50–150 community names of uneven quality | SKIP |

---

## Workstream 5 — Hydrographic & nautical sources

| Source | Jurisdiction | Licence | Yield | Priority |
| --- | --- | --- | --- | --- |
| **Commissioners of Irish Lights — Aids to Navigation (data.gov.ie)** | RoI + NI | CC-BY-4.0 | 15–25 new tiny Irish skerries (Fastnet, Tuskar, Rockabill, Inishtearaght, Bull Rock, Eagle Island…) | **HIGH** |
| **Northern Lighthouse Board — Lighthouse Library + marine.gov.scot** | Scotland + IoM | OGL (NMPi layer); site facts | 10–20 new Scottish/Manx islets (esp. Shetland/Orkney bound skerries) | **HIGH** |
| **EMODnet Bathymetry — satellite-derived LAT coastline** | UK + IE | EMODnet CC-BY-like | 100–500 detached LAT polygons (large; **un-named**, requires gazetteer joining) | MEDIUM-HIGH |
| **Trinity House — Lighthouses register** | E+W+CI | © site (facts extractable) | 3–8 new English/Welsh rocks (Bishop, Wolf, Smalls already in OSM) | MEDIUM |
| **Environment Agency AIMS Aids to Navigation** | England + partial Wales | OGL v3.0 | 0–5 new genuine islands; useful cross-reference | MEDIUM-LOW |
| **UKHO ADMIRALTY open subset** | UK EEZ | OGL v3.0 | Open subset = bathymetry + wrecks + limits; **does NOT contain "drying rocks" S-57 features** (those are in the licensed ENC product) | LOW (despite reputation) |
| **EMODnet Human Activities — Lighthouses layer** | pan-European | EMODnet | 0 new (ARLHS-derived; lower quality than CIL/NLB/TH) | LOW |
| **IHO DCDB Crowdsourced Bathymetry** | global | free | 0 new islands; bathymetric points only | LOW |
| **RNLI Open Data — Lifeboat stations** | UK + IE | **UK = revocable bespoke** (NOT truly open); IE mirror = CC-BY-4.0 | 0 new (all stations on already-known inhabited islands) | LOW |
| **HM Coastguard CRT station list** | UK | OGL via GOV.UK | 0 new | LOW |
| **Reed's Nautical Almanac / Imray Charts** | UK + IE + NW Europe | **commercial, all rights reserved** | Internal QA only, fair-dealing spot-checks | **EXCLUDE** from redistribution |
| **"Irish Sea Hydrographic Database"** (in brief) | — | — | **DOES NOT EXIST** as a named product. Closest analogue is INFOMAR (CC-BY-4.0), but it is bathymetry, not a named-island feature list | n/a |

---

## Workstream 6 — River & lake-specific sources

> This is the highest-yield workstream by far. Our current 226 river islands
> + 1,066 lake islands almost certainly under-represents the long tail of
> named eyots and crannogs. Realistic yield ceiling for the workstream:
> **1,500–2,500 new candidates**, dominated by crannogs in Scotland + Ireland.

| Source | Jurisdiction | Licence | Yield | Priority |
| --- | --- | --- | --- | --- |
| **Wikipedia — "Islands in the River Thames"** | England | CC BY-SA 4.0 | 80–110 new Thames eyots (verified: ~133 main-table rows + ~17 supplementary = ~150 features; we have only 142 English river islands total) | **TIER 1** |
| **Wikipedia — Lough Erne (Upper + Lower) island lists** | NI + RoI | CC BY-SA 4.0 | 80–150 new (1846 Parliamentary Gazetteer: 90 Upper + 109 Lower = 199 islands) | **TIER 1** |
| **Historic Environment Scotland — Canmore (CRANNOG site type)** | Scotland | OGL v3.0 | 300–500 new (~389 crannogs confirmed; ~570 with island duns) | **TIER 1** |
| **NPWS / NMS — Sites and Monuments Record Ireland (Crannog / Island dwelling)** | RoI | CC-BY-4.0 / open re-use | 400–800 new (~1,200 crannogs catalogued; filter for above-water "extant" condition) | **TIER 1** |
| **Environment Agency — Detailed River Network (DRN) + RoFRS** | England | OGL v3.0 | 300–700 new (structural fix for our linear-river OSM gap; re-runs Tier A/B against river POLYGONS) | **TIER 1** (engineering investment) |
| **OPW Ireland — NIFM + CFRAM** | RoI | PSI Directive (OGL-equivalent) | 80–150 new Shannon-system islands (Lough Ree alone has 50+ named islets) | **TIER 1** |
| **DfC NI — Sites and Monuments Record (Northern Ireland)** | NI | OGL v3.0 | 80–200 new (Fermanagh lake islets esp.) | **TIER 1** |
| **Logainm.ie — Placenames Database of Ireland (filtered to OIL category)** | RoI + NI | CC-BY-4.0 | 100–300 actually-new + 500–1,500 name-enrichment | **TIER 1** |
| **Wikidata SPARQL — `?island wdt:P361 ?lake/river` constrained to British Isles** | UK + IE | **CC0** | 200–500 new; best dedup spine for the whole workstream | **TIER 1** |
| **SEPA — WFD water-body register + Scotland's River Network** | Scotland | OGL v3.0 | 100–300 new loch islets (paired with EA-style polygon ingest) | **TIER 1** |
| **NRW / DataMapWales river & lake polygons** | Wales | OGL v3.0 | 20–50 new; key Welsh entries are scarce but Llangorse crannog is essential | **TIER 2** |
| **Wikipedia — Loch Lomond + Islands of Loch Lomond category** | Scotland | CC BY-SA 4.0 | 10–30 new (smaller islets + crannogs) | **TIER 2** |
| **Lake District NPA + Wikipedia per-lake articles** | England | OGL-like / CC BY-SA | 20–40 new "Holmes" (Old Norse *holmr* = islet — preserve suffix) | **TIER 2** |
| **Wikipedia — Lough Neagh / Lough Ree / Lough Derg (Shannon) islands** | NI / RoI | CC BY-SA 4.0 | 3–8 (Lough Neagh) + 40–80 (Shannon lakes) new | **TIER 1–2** |
| **Norfolk Broads Authority + EA/OS layers** | England (Norfolk/Suffolk) | OGL v3.0 | 30–100 new small unnamed islets (apply min-area + vegetation-stability filter) | **TIER 2** |
| **Inland Waterways Association (UK + IE) + Canal & River Trust + Waterways Ireland** | UK + IE | CC BY-NC / OGL | 5–20 new canal-pound eyots; low priority | **TIER 3** |

---

## Workstream 7 — Local heritage & place-name authorities

> The transformative value of this workstream is **canonical non-English
> names + heritage flags**, not net-new island entities. Realistic new-entity
> yield ~100–300; cultural-correctness yield = thousands of authoritative
> Gàidhlig / Gaeilge / Cymraeg / Gaelg / Kernewek forms.

| Source | Jurisdiction | Licence | Yield | Priority |
| --- | --- | --- | --- | --- |
| **Historic Environment Scotland — Canmore / trove.scot** | Scotland | OGL v3.0 (metadata) | 10–30 new islets; 100–300 crannog candidates; heritage flags for hundreds | **HIGH** |
| **Historic England — National Heritage List for England (NHLE)** | England | OGL v3.0 | Few new entities; main yield = listed-feature counts for existing islands | **HIGH** |
| **Cadw — Cof Cymru** | Wales | OGL (Welsh Govt) | Few new entities; complements Welsh-language names | MEDIUM-HIGH |
| **DfC Historic Environment Division NI — NISMR** | NI | OGL v3.0 | 20–80 new Lough Erne / Lough Neagh crannogs (NIEA-adjacent; overlap with WS2 + WS6) | MEDIUM |
| **National Monuments Service Ireland — Archaeological Survey (archaeology.ie)** | RoI | CC-BY-4.0 | 20–50 monastic islands strengthened with heritage flags | **HIGH** |
| **Manx National Heritage — IOMHER + Protected Buildings Register** | IoM | © Crown of IoM (non-commercial with attribution) | Small absolute yield (~3–8 new IoM features) | MEDIUM |
| **Ainmean-Àite na h-Alba (AÀA)** | Scotland | © AÀA (PDF spelling lists public; no bulk feed) | 0–10 new entities; **canonical Gàidhlig forms for ~600–800 Scottish islands** | **HIGHEST (cultural)** |
| **Welsh Language Commissioner — Standard Welsh Place-names** | Wales | OGL v3.0 | 0–5 new; canonical Welsh forms for ~30–80 islands | **HIGHEST (cultural)** |
| **Logainm.ie — Placenames Database of Ireland (Gaois API)** | RoI + NI | CC-BY-4.0 | 0–20 new entities; canonical Gaeilge forms for ~2,000–3,000 OIL records | **HIGHEST (cultural)** |
| **Akademi Kernewek — Cornish place-names** | Cornwall (incl. Scilly) | © Akademi (reasonable scholarly reuse) | 5–20 new sub-island features (Scilly rocks); canonical Kernewek forms | **HIGHEST (cultural, esp. Scilly)** |
| **Comhairle nan Eilean Siar — Gaelic place-names** | Outer Hebrides | flows through AÀA | 0 new entities; Hebridean Gàidhlig forms | HIGH (principle) |
| **RCAHMW — Coflein (National Monuments Record of Wales)** | Wales | OGL | 0–10 new entities; complements Cadw | MEDIUM |
| **Manx Place-Names — Kneen (1925) + Broderick** | IoM | Kneen public domain; Broderick © De Gruyter | 0 new entities; Manx Gaelic (Gaelg) forms | MEDIUM |
| **Saints in Scottish Place-Names (Univ. Glasgow — NOT St Andrews)** | Scotland | © Univ. Glasgow (scholarly reuse) | 0–5 new entities; saintly-dedication metadata for monastic islands | MEDIUM |
| **English Place-Name Society (EPNS) — Digital Survey + KEPN** | England (county-by-county) | © EPNS / Univ. Nottingham | 0 new entities; historical name forms (Old English / Old Norse attestations) | MEDIUM-LOW |

---

## Workstream 8 — Remote sensing as a last-resort fill (research inventory only)

> **No imagery was processed, no ML pipeline built.** This is a forward-only
> inventory. Realistic UK yield from any future RS pipeline: **0–20
> candidate features**, mostly drying rocks at LAT. Integration complexity
> is uniformly **HIGH**. Every satellite-derived candidate must be confirmed
> against OS / UKHO / OSM / Wikipedia before being given a name; never
> auto-promoted. Schema must carry `candidate=true` + `year_of_detection`.

| Source / method | Licence | Yield | Priority |
| --- | --- | --- | --- |
| **EMODnet Bathymetry — satellite-derived LAT coastlines** (also in WS5) | CC-BY-4.0 | 5–20 drying-rock candidates after gazetteer join | **MEDIUM-HIGH** (only actionable RS-derived layer) |
| **Environment Agency 1 m LIDAR composite** | OGL v3.0 | Handful of confirmations; **England only** | MEDIUM |
| **ESA WorldCover 10 m global land cover** | CC-BY-4.0 | 0–5 UK features; cheapest single RS comparison | MEDIUM |
| **Sentinel-2 MSI** | Copernicus free + open | 0–5 truly uncharted; high false-positive risk | LOW (research) |
| **Sentinel-1 SAR** | Copernicus free + open | 0 directly; useful only as S2 confirmation channel | LOW (research) |
| **Landsat 8/9 Collection 2** | US public domain | 0–2; historical (40+ year) "lost island" detection only | LOW (research) |
| **GEBCO_2024 + GMRT bathymetric synthesis** | public domain / CC-BY-4.0 | 0 directly | LOW |
| **NASA Worldview / GIBS (MODIS / VIIRS)** | US public domain | 0; pixels too coarse | LOW |
| **Defra / EA Vertical Aerial Photography** | OGL v3.0 | 0 directly; manual-verification source | LOW |
| **OS Open Zoomstack** | OGL v3.0 | Already in baseline | n/a |
| **PlanetScope (Dove / SuperDove)** | commercial | Theoretically the best small-island sensor; cost-prohibitive (~$15k/yr) | VERY LOW |
| **Maxar WorldView / GeoEye** | commercial / NGA EULA | 0 in practice; surveillance risk | **EXCLUDE** |
| **"ESA WorldCoast"** (in brief) | — | **DOES NOT EXIST** as a discrete product — closest equivalents: EMODnet World Coastline, ESA "Space for Shore", ESA CCI Coastal Erosion | n/a |
| **CoastSat (Vos et al. 2019)** | GPL-3.0 toolkit | Methodology reference | OPTIONAL TOOLKIT |
| **DeepWaterMap v2 (Isikdogan et al.)** | open toolkit (TF1) | Methodology reference; less maintained than CoastSat | REFERENCE ONLY |
| **GMW v3/v4 + Allen Coral Atlas** | CC-BY-4.0 | Methodology citations only (Bunting 2022; DOI 10.3390/rs14153657) | CITATION ONLY |
| **Pardo-Pascual 2018, Almonacid-Caballer 2016** | CC-BY (MDPI / Elsevier) | Sub-pixel coastline-extraction citations | CITATION ONLY |

---

## Action plan — top 5 sources to ingest next

Each of the following is open-licensed, has a structured access path, and
has a clear marginal yield. Numbers in parentheses are estimated *net new*
islands beyond the 5,892 baseline. They are ranked by yield ÷ complexity
× ethical-cleanness.

1. **Wikidata SPARQL on `wdt:P31/wdt:P279* wd:Q23442` × UK/IE/IoM/Jersey/Guernsey** — *CC0*, ~2,500–3,500 net new, complexity LOW. Output is also the canonical Q-ID / native-label / area / population spine to join every other source against. This is the highest-yield single action by an order of magnitude. **(WS4)**

2. **Environment Agency Detailed River Network + RoFRS polygons** — *OGL v3.0*, ~300–700 net new (England), complexity HIGH (one-time engineering: re-run our Tier A/B classifier against river *polygons* not *ways*). Pair with **Wikipedia "Islands in the River Thames"** (CC BY-SA 4.0, ~80–110 net new) as validation set, plus **SEPA WFD water-body register** (OGL, ~100–300 new Scottish loch islets) and **OPW Ireland NIFM/CFRAM** (PSI/OGL, ~80–150 new Shannon-system islands) to close the river-island gap UK-wide. **(WS6)**

3. **Crannog corpus: HES Canmore + NPWS Ireland SMR + DfC NI NISMR** — *OGL v3.0 / CC-BY-4.0*, ~600–1,200 net new combined (after filtering out submerged platforms), complexity MEDIUM. This roughly **doubles our 1,066 lake-island count**. Must apply the WS6/WS7 ethics filter: scheduled-monument granularity (10–100 m rounded), no precise burial coordinates, defer to authority on "at-risk" sites. **(WS6 + WS7)**

4. **Logainm.ie + Ainmean-Àite na h-Alba + Welsh Language Commissioner + Akademi Kernewek** — *CC-BY-4.0 / OGL v3.0 / scholarly-with-permission*, 0–30 net new entities but ~3,000+ authoritative non-English name additions (Gaeilge, Gàidhlig, Cymraeg, Kernewek). This is the cultural-integrity action: every existing entry gets its canonical native form. Schema impact: introduce `name:ga`, `name:gd`, `name:cy`, `name:gv`, `name:kw` fields alongside `name`. Email-permission step required for AÀA bulk use; Akademi Kernewek scrape needs licence confirmation. **(WS7)**

5. **Statutory designation feeds — JNCC SAC/SPA/Ramsar + NatureScot SSSI/NNR + NIEA ASSI + Tailte Éireann Islands + NPWS Ireland** — *OGL v3.0 / CC-BY-4.0*, ~250–450 net new combined (small named stacks, Lough Erne + Strangford islets, Connemara stacks, West-coast Irish stacks, plus authoritative polygons for canonical Scottish/Welsh/Irish islands). Complexity LOW–MEDIUM. **(WS2)**

These five actions together estimate **~3,750–6,000 new islands**, with the Wikidata pull dominating absolute yield and the river/crannog pipelines dominating *interesting* yield (the long-tail of named eyots and lake islets our current pipeline misses by construction).

---

## Sources by licence class (audit summary)

- **CC0** (no obligation): Wikidata.
- **CC-BY-4.0** (attribution): Tailte Éireann, NPWS Ireland, NMS Ireland, Logainm.ie, Commissioners of Irish Lights, GeoNames, EMODnet, ESA WorldCover, GMW, GMRT, EMODnet Coastlines, Coflein, Welsh Govt, RNLI Ireland mirror.
- **OGL v3.0** (attribution): All UK government sources (OS, OSNI, NatureScot, NRW, Defra, MAGIC, JNCC, NHLE, Cadw, HES Canmore, NIEA, NMRW, EA, SEPA, Trinity House facts).
- **CC BY-SA 4.0** (share-alike): Wikipedia + Wikipedia category trees.
- **ODbL** (share-alike): OSM, OpenSeaMap.
- **Non-commercial / restrictive**: WDPA, RSPB IBA (current), SMP (gated), RNLI UK hub (revocable), Mapcarta/Wikimapia user content. — **SKIP for redistribution.**
- **Copyright / commercial**: Haswell-Smith book, Reed's, Imray, Maxar, PlanetScope, McNally, Carradice, EPNS Survey, Broderick. — **REFERENCE ONLY** or **EXCLUDE**.
- **Not open / partner-only**: States of Jersey GIS, Digimap Guernsey, Manx Wildlife Trust website. — **EXCLUDE from bulk ingest; manual research only.**
- **Decommissioned / nonexistent**: Welsh Lle Geo-Portal (replaced by DataMapWales), ESA WorldCoast (not a product), Irish Sea Hydrographic Database (not a product).

---

## What this catalogue does NOT include

- **Per-source field schemas** (CSV columns, GeoJSON properties). Those are
  the next session's deliverable, after the top-5 action plan is approved.
- **Actual ingestion scripts.** No code has been written.
- **Photography enrichment.** Already done in the previous session; see
  `scripts/enrich_images.py`.

---

*Last updated: 2026-05-11. Authors: parent + 8 internal research subagents.*
