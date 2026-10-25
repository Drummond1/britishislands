# Naming sources — 100 high-confidence approaches for ~4,310 unnamed islands

Brainstorm and implementation registry for islands with `nameStatus=unknown`
(OSM polygons, placeholder **Unnamed island**). Complements
[`DISCOVERY-SOURCES.md`](DISCOVERY-SOURCES.md) (new-entity discovery) and
[`ETHICS.md`](ETHICS.md) (linguistic authorities, no invented names).

**Baseline:** 4,310 unnamed / 7,041 total (2026-06-11).

---

## Confidence framework (all 100)

| Tier | Rule | Auto-merge? |
|------|------|-------------|
| **A** | Statutory gazetteer or cartographic authority; centroid ≤150 m or polygon containment | Yes, with provenance |
| **B** | Two independent open-licensed sources agree (name + ≤200 m) | Yes, with `dualSource` |
| **C** | Single strong source + parent-water disambiguation | Human review queue |
| **D** | Inferred / composed / LLM | Never auto-merge |

Staging: `data/staging/name_proposals/*.json` →
`verify_staged_names.py` → `name_proposals-verified/` →
`merge_staged_name_proposals.py`.

Orchestrator: `scripts/run_priority_naming_push.sh`.

---

## Implementation status

| Priority | # | Source | Script | Status |
|----------|---|--------|--------|--------|
| **N1** | 16 | OS Open Names spatial join | `name_unnamed_os_open_names.py` | **Implemented** (needs `data/raw/os_opennames.csv`) |
| **N2** | 31 | Logainm OIL bulk | `name_unnamed_logainm_oil.py` | **Implemented** (needs `LOGAINM_API_KEY`) |
| **N3** | 1–2 | OSM `wikidata=` + name tags | `name_unnamed_osm_tags.py` | **Implemented** |
| **N4** | 46, 49 | Canmore / NHLE locality | `name_unnamed_heritage.py` | **Implemented** |
| **N5** | 3 | OSM version history (name recovery) | `name_unnamed_ohsome.py` | **Implemented** (OSM API) |
| **N6** | 99 | Triangulation fusion | `name_unnamed_fusion.py` | **Implemented** |
| **N7** | 11 | GeoNames ISL/ISLT → unnamed ≤150 m | `name_unnamed_geonames.py` | **Implemented** (first merge **+128**) |
| **N8** | 5 | OSM nearby named nodes | `name_unnamed_nearby_osm.py` | **Implemented** (overnight batches) |
| **N9** | — | For-sale listing adjacent names | `name_unnamed_property_adjacent.py` | **Implemented** |
| **N10** | — | Commons geo title consensus | `name_unnamed_photo_titles.py` | **Implemented** (strict proper-name gate) |

Overnight: `scripts/run_overnight_discovery_naming.sh --loop`.

Fetch helper: `scripts/fetch_os_open_names.py` (OGL; `OS_DATAHUB_API_KEY`).

---

## 1–15: OSM & geospatial

| # | Approach | Licence | Gate | Script |
|---|----------|---------|------|--------|
| 1 | OSM `wikidata=Q` reverse label | ODbL + CC0 | Same way ID | **N3** |
| 2 | OSM alternate name tags (`name:gd`, `alt_name`, …) | ODbL | Tag on same way | **N3** |
| 3 | OSM changeset archaeology (ohsome) | ODbL | Exact way ID match | planned |
| 4 | OSM–Wikidata mismatch detector | ODbL + CC0 | Existing `wikidata=` link | partial (N3) |
| 5 | OSM orphan named nodes inside polygon | ODbL | PIP / around | **N8** |
| 6 | OSM `note` / `fixme` / `description` mining | ODbL | Text + corroborator | planned |
| 7 | OSM archipelago relation members | ODbL | Relation membership | planned |
| 8 | OSM `ref` / `ref:admiralty` | ODbL + OGL | Ref resolves at coords | planned |
| 9 | OSM relation `site=*` membership | ODbL | Way in relation | planned |
| 10 | OpenSeaMap `seamark:name` | ODbL | ≤150 m + `notForNavigation` | planned |
| 11 | GeoNames ISL/ISLET dump | CC-BY | ≤150 m + area sanity | **N7** |
| 12 | NGA GNS maritime features | PD/USGov | ≤200 m, sea only | planned |
| 13 | Natural Earth minor islands | PD | Polygon overlap | planned |
| 14 | EMODnet Seabed Habitats names | CC-BY | Centroid in polygon | planned |
| 15 | Flickr geotag cluster consensus | CC | ≥3 photos, same title | planned |

## 16–30: Ordnance Survey & government gazetteers

| # | Approach | Licence | Gate | Script |
|---|----------|---------|------|--------|
| 16 | **OS Open Names** spatial join | OGL v3.0 | ≤100 m | **N1** |
| 17 | OS Names API (MasterMap) | Commercial | ≤75 m | blocked |
| 18 | OS Linked Identifiers API | OGL/commercial | TOID↔Q-ID | planned |
| 19 | OS OpenMap Local water polygons | OGL v3.0 | Centroid in polygon | planned |
| 20 | OS Open Rivers parent context | OGL v3.0 | PIP in river | planned |
| 21 | OS Terrain 50 waterbody labels | OGL v3.0 | ≥70% overlap | planned |
| 22 | Tailte Éireann Placenames WFS | CC-BY-4.0 | ≤150 m | planned |
| 23 | Tailte Éireann Islands 1m Map | CC-BY-4.0 | Polygon overlap | planned |
| 24 | Tailte Éireann `Inis-` townland filter | CC-BY-4.0 | Townland PIP | planned |
| 25 | LPS NI POINTER gazetteer | OGL | ≤200 m | planned |
| 26 | OSNI Largescale Boundaries | OGL | Polygon containment | planned |
| 27 | NRS Scotland inhabited-island boundaries | OGL | NRS polygon overlap | planned |
| 28 | IoM MANNGIS | OGL IoM | ≤300 m | planned |
| 29 | Channel Islands registers | mixed | Reef-group bbox | manual |
| 30 | UKHO NtM “name assigned” archive | OGL subset | ≤1 km + 2nd source | planned |

## 31–45: Cultural & linguistic authorities

| # | Approach | Authority | Gate | Script |
|---|----------|-----------|------|--------|
| 31 | **Logainm OIL** bulk spatial join | Logainm.ie CC-BY-4.0 | ≤500 m | **N2** |
| 32 | Logainm parent-water text search | Logainm | Irish form + lough | planned |
| 33 | Gaois API variant forms | CC-BY-4.0 | Linked to #31 | planned |
| 34 | AÀA online gazetteer REST | AÀA | ≤200 m | planned |
| 35 | AÀA parish PDF lists | AÀA | ≤400 m | planned |
| 36 | Comhairle nan Eilean Siar register | CnES | Inside boundary | planned |
| 37 | PlacenamesNI / PRONI | OGL/CC-BY | ≤500 m + water anchor | planned |
| 38 | Welsh Language Commissioner CSV | OGL | Bilingual match | planned |
| 39 | Archwilio Wales HER `SiteName_CY` | OGL | ≤250 m | planned |
| 40 | Coflein RCAHMW | CC-BY-4.0 | ≤400 m + PRN | planned |
| 41 | Manx Place-Names Survey | reference | ≤300 m | planned |
| 42 | Akademi Kernewek SWF | AK | AK entry + etymology | planned |
| 43 | Shetland/Orkney Norse indices | UHI/council | ≤300 m | planned |
| 44 | Channel Islands Norman-French | local | Reef containment | manual |
| 45 | Gaelic element metathesaurus | SPNS rules | Independent attestation only | tier D |

## 46–60: Heritage, archaeology & monuments

| # | Approach | Licence | Gate | Script |
|---|----------|---------|------|--------|
| 46 | Canmore `SITENAME` (ISLAND/CRANNOG) | CC-BY-4.0 | ≤300 m NGR | **N4 planned** |
| 47 | NMS Ireland RMP | OGL IE | ≤500 m | planned |
| 48 | NISMR NI | OGL | ≤400 m | planned |
| 49 | Historic England NHLE locality | OGL | ≤350 m | **N4 planned** |
| 50 | Heritage Gateway county HER | mixed OGL | ≤400 m | planned |
| 51 | NHLE scheduled monument `Name` | OGL | ≤250 m | planned |
| 52 | SCAPE/SCHARP threatened sites | CC-BY | ≤500 m Scotland coast | planned |
| 53 | SPNS historic forms | academic | ≤600 m | planned |
| 54 | Dúchas placenames (name-only) | NC — cross-ref only | Must match Logainm | reference |
| 55 | Griffith's Valuation townland crosswalk | PD/old | ≤1 island/townland | planned |
| 56 | Valuation field books (NLI) | archive | Townland uniqueness | planned |
| 57 | NRS Valuation Rolls | OGL | Parish + townland | planned |
| 58 | Coflein crannog PRNs | CC-BY-4.0 | Citation required | planned |
| 59 | Cadw scheduled monuments | OGL | ≤300 m Wales | planned |
| 60 | heritage_ogl WFS name fields | OGL/CC-BY | Reuse photo WFS infra | planned |

## 61–75: Historical maps & gazetteers

| # | Approach | Licence | Gate |
|---|----------|---------|------|
| 61 | NLS georeferenced OS 6-inch OCR | OGL/PD | ≥2 sheets agree |
| 62 | NLS Georeferencer Map Search API | OGL | RMSE ≤10 m |
| 63 | First Edition OS Ireland 6-inch | OGL/CC-BY | Logainm cross-ref |
| 64 | OSi Discovery Series WMS OCR | CC-BY | OCR ≥85% + Logainm |
| 65 | Vision of Britain GBH-GIS | CC-BY-NC ref | ≤500 m NGR |
| 66 | Lewis's Topographical Dictionary | PD | Parent-water match |
| 67 | British Newspaper Archive mining | subscription | County + dual-source |
| 68 | Roy Military Survey Scotland | NLS | Georef tile at centroid |
| 69 | Tithe map island labels | archive | Parish + single island |
| 70 | Admiralty chart open derivatives | OGL subset | Label bbox in polygon |
| 71 | Stanford/Hydrographic catalogue | PD metadata | Chart cell + seamark |
| 72 | Estate map archives | archive | Georef + 2nd source |
| 73 | Irish Historic Towns Atlas | academic | Map pin + polygon |
| 74 | Vision of Ireland 6-inch index | archive | Sheet grid + centroid |
| 75 | British Library Georeferencer | PD/OGL | Multi-sheet rule |

## 76–90: Wikimedia, open knowledge & crowdsourced

| # | Approach | Licence | Gate |
|---|----------|---------|------|
| 76 | Wikipedia list-article coord tables | CC-BY-SA | Row coord ≤500 m PIP |
| 77 | Wikipedia redlinks in island lists | CC-BY-SA | Grid ref in row |
| 78 | GeoHack URL extraction | CC-BY-SA | Category membership |
| 79 | Wikivoyage listing blocks | CC-BY-SA | Coord in polygon |
| 80 | Commons category geo-headers | CC-BY-SA | WCQS spatial |
| 81 | Wikidata P2561/P1448/P1705 official labels | CC0 | Filter generic |
| 82 | Wikidata P527 archipelago parts | CC0 | ≤200 m + area ratio |
| 83 | DBpedia `dbo:Island` SPARQL | CC-BY-SA | Bbox + PIP |
| 84 | Geograph subject-text mining | CC-BY-SA | ≥3 photo consensus |
| 85 | iNaturalist Places API | CC-BY-NC — ref only | Place polygon contains |
| 86 | GBIF locality strings | CC-BY / mixed | NLP + ≤300 m |
| 87 | Openverse/Flickr geo title clusters | CC | Licence + consensus |
| 88 | Commons depicts reverse (P180) | CC-BY-SA | Existing depicts infra |
| 89 | Wikipedia all-langs infobox coords | CC-BY-SA | Not locator SVG |
| 90 | Crowd pins triangulation | community | ≥3 submissions + corroborator |

## 91–100: Environmental, marine, inference & fusion

| # | Approach | Licence | Gate |
|---|----------|---------|------|
| 91 | NatureScot SSSI `SSSI_NAME` | OGL | ≤400 m |
| 92 | Defra MAGIC / NRW SSSI labels | OGL | ≥30% overlap |
| 93 | NPWS `SITE_NAME` / `AINM_SUIMH` | CC-BY-4.0 | ≤400 m |
| 94 | JNCC SAC citation PDF parsing | OGL | Inside SAC polygon |
| 95 | Ramsar RIS PDF island mentions | OGL | Inside Ramsar + ≥2 sections |
| 96 | JNCC Seabird Colony Register | OGL/restricted | ≤300 m |
| 97 | BSBI Distribution Database | research | 6-figure grid |
| 98 | FBA/CEH lake survey station names | academic | ≤200 m, lake ≥1 km² |
| 99 | **Triangulation fusion engine** | meta | ≥3 Tier-A/B agree ≤200 m |
| 100 | Voronoi OS Open Names disambiguation | OGL | Sole polygon in cell |

---

## Realistic yield (de-duplicated)

| Tier | Estimated recoverable |
|------|---------------------|
| A (auto) | 900–1,400 |
| B (dual) | 400–700 |
| C (review) | 300–500 |
| D (suggestions) | 200–400 |

**Total high-confidence potential: ~1,300–2,100** of 4,310 (30–49%).

---

## Runbook

```bash
# One-time data prep
python3 scripts/fetch_os_open_names.py          # OS_DATAHUB_API_KEY
# LOGAINM_API_KEY in .env.local for Ireland

# Full priority pass
bash scripts/run_priority_naming_push.sh

# Or individual harvesters
python3 scripts/name_unnamed_osm_tags.py --limit 500
python3 scripts/name_unnamed_os_open_names.py
python3 scripts/name_unnamed_logainm_oil.py --refresh

python3 scripts/verify_staged_names.py
python3 scripts/merge_staged_name_proposals.py
python3 scripts/build_islands_index.py
```
