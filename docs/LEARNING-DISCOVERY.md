# Learning and discovery improvements

**Owner:** Codex · **Published:** 3 November 2026 · **Status:** 20-island pilot live and verified.

## Purpose and authority

Drummond asked to implement the 2 November learning/discovery recommendations in priority order and keep the work shared in project documentation. This delivers the recommended 20-island pilot and the discovery mechanisms needed to expand it. The larger 100-profile goal remains an expansion milestone. `STATE.md` holds release/process status; `QUEUE.md` holds pending work; `SESSION-LOG.md` records completion. Start here for implementation context.

## Priority and acceptance

1. [x] **Story hooks:** default/search cards and profile openings explain why an island is interesting. Pilot hooks take priority, then substantive cited thematic stories, then existing descriptions. Feature pictures follow the text; gallery attribution remains visible. Existing virtualisation and clustering remain in use.
2. [x] **Twenty richer profiles:** original overviews, 60 source-linked facts and 47 timeline entries across Britain, Ireland and the Crown Dependencies. The overlay preserves canonical records, local names and reviewed photograph decisions. No invented pronunciation or etymology.
3. [x] **Explained connections:** three authored onward choices per pilot profile (60 connections). Other profiles can use substantive cited thematic peers. Geographic group suggestions are separate; unknown/placeholder labels no longer connect unrelated islands.
4. [x] **Learning journeys:** three deliberate eight-stop sequences covering all 20 profiles, each with an introduction, a note explaining every stop, a source-linked hook, island links and an eight-island map view. Also generated as readable static HTML.
5. [x] **Ask and trust:** learning facts/timelines and source URLs reach `read_islands`; simple pilot story/timeline prompts use the authored material directly. Model answers can cite only returned source URLs. References actually cited are labelled separately from background read; photo credits have their own label. Oversized tool output remains valid JSON with explicit omissions.
6. [x] **Easy exploration and returning:** Surprise chooses substantive pilot profiles; a weekly selection rotates deterministically; Continue exploring uses recent local history; saved islands require no email. Existing saved IDs remain valid.
7. [x] **Verification and handover:** focused content/failure tests, existing Ask/analytics/SEO/GEO regressions, isolated full static generation, desktop/phone browser checks, canonical input hashes and linked schema/architecture/performance documentation. Evidence: [verification report](reports/learning-2026-11-03/REPORT.md).

## Implementation map

| File | Responsibility |
|---|---|
| `data/learning_profiles.json` | Authored, versioned source of truth for this pilot; edit through a reviewed content change, no canonical rebuild required. |
| `learning.js` | Safe source links and rendering, hooks, connections, substantive-profile selection, weekly choice and bounded local history. |
| `learning.css` | Existing atlas/paper theme, bounded pictures, visible card hooks, journey mode, reading/source/timeline styles and phone toolbar wrapping. |
| `app.js` / `index.html` | Lazy overlay loading, discovery controls, `?journey=slug`, profile integration, no-email saved UI and source-aware Ask. |
| `chat-agent.js` | Source-preserving story/learning payloads and bounded valid JSON tool results. |
| `scripts/seo_learning.py` | Static equivalents of facts, timelines, connections, `/learn/` and three journey pages. |
| `scripts/generate_seo_artifacts.py` | Overlay integration into canonical profiles, core sitemap and collections hub; existing CI generates the pages. |
| `scripts/test_learning.mjs` / `scripts/test_seo_learning.py` / `scripts/test_detail_map_lifecycle.mjs` | Content integrity, failure behaviour, source separation, unresolved identity gate, static equivalents and async map lifecycle. |

The 51,491-byte JSON sidecar is requested at idle after atlas first paint, or during Ask preparation. It is not embedded in the compact index and does not load all nation shards. Failure leaves the original atlas usable. A generation token prevents stub/full/learning refreshes, rapid island switches or closing a profile from initialising a stale detail map after projection setup. Small selectors are in the initial module graph. See [performance](FRONTEND-PERFORMANCE.md) and [sidecar schema](DATA-SCHEMA.md#learning-and-discovery-sidecar).

## Source and editorial policy

All 20 introductory profiles were checked against their linked Wikipedia articles on **2026-11-03**. Summaries are original/adapted prose attributed to Wikipedia contributors and Find My Island, under **CC BY-SA 4.0**. Every overview, fact and timeline entry names source IDs; the hook uses the overview's sources. Visible reading credits include source URL, attribution, licence and check date. Source-check dates describe research, not current access, a census or an editorial review of the whole canonical record.

This is an introductory source-linked pilot. It does **not** certify every legacy measurement, cultural story, access note, image association or generated AI claim in the existing atlas. Wikipedia is the pilot's initial source layer; authoritative open-licensed heritage, geology, conservation and cultural-language sources are the next editorial improvement. Contemporary access conditions require their own evidence. Timelines preserve approximate dates (`c.`, centuries) instead of implying exactness. No new photographs, visitor records, personal details, crossing times or wildlife coordinates were added.

Simple Ask prompts such as `Tell me about Lundy` and `Show me a timeline of Lundy` use the authored pilot directly, with reading links. Broader Smart answers still depend on a model. The prompt requests paragraph citations, but the model may omit them; in that case the UI honestly labels the returned island sources **Island background read for this answer**. It does not claim that a background link verifies every generated sentence. Resolving source contradictions and measuring broader citation accuracy remain future work. Factual references never substitute photo credits.

The recent list is browser-local (`iobRecentLearningIslands`, most recent 12); saved islands retain `iobFavoriteIslandIds`. Neither requires an account or email. Clearing browser data removes them. The old favourites email value is no longer read or written; this change does not erase unrelated browser storage. Existing consent-gated analytics is preserved; this work adds no new analytics events or remote history sync.

## Pilot manifest

| Island | Nation label | Stable atlas ID | Reading source |
|---|---|---|---|
| Erraid | Scotland | `osm-relation-9620215` | [Erraid](https://en.wikipedia.org/wiki/Erraid) |
| Staffa | Scotland | `staffa` | [Staffa](https://en.wikipedia.org/wiki/Staffa) |
| Iona | Scotland | `iona` | [Iona](https://en.wikipedia.org/wiki/Iona) |
| Eigg | Scotland | `osm-relation-1663615` | [Eigg](https://en.wikipedia.org/wiki/Eigg) |
| St Kilda (Hirta) | Scotland | `st-kilda` | [St Kilda, Scotland](https://en.wikipedia.org/wiki/St_Kilda,_Scotland) |
| Lundy | England | `lundy` | [Lundy](https://en.wikipedia.org/wiki/Lundy) |
| Lindisfarne (Holy Island) | England | `lindisfarne` | [Lindisfarne](https://en.wikipedia.org/wiki/Lindisfarne) |
| Eel Pie Island | England | `eel-pie-island` | [Eel Pie Island](https://en.wikipedia.org/wiki/Eel_Pie_Island) |
| Brownsea Island | England | `brownsea` | [Brownsea Island](https://en.wikipedia.org/wiki/Brownsea_Island) |
| Achill Island | Ireland | `osm-relation-6045364` | [Achill Island](https://en.wikipedia.org/wiki/Achill_Island) |
| Dursey Island | Ireland | `osm-relation-8609288` | [Dursey Island](https://en.wikipedia.org/wiki/Dursey_Island) |
| Inishmaan | Ireland | `osm-relation-8158177` | [Inishmaan](https://en.wikipedia.org/wiki/Inishmaan) |
| Scattery Island | Ireland | `osm-relation-319479` | [Inis Cathaigh](https://en.wikipedia.org/wiki/Inis_Cathaigh) |
| Bardsey Island | Wales | `osm-relation-6046655` | [Bardsey Island](https://en.wikipedia.org/wiki/Bardsey_Island) |
| Devenish Island | Northern Ireland | `osm-relation-3998376` | [Devenish Island](https://en.wikipedia.org/wiki/Devenish_Island) |
| Rathlin Island | Northern Ireland | `rathlin` | [Rathlin Island](https://en.wikipedia.org/wiki/Rathlin_Island) |
| Isle of Man | Crown Dependency | `isle-of-man` | [Isle of Man](https://en.wikipedia.org/wiki/Isle_of_Man) |
| Guernsey | Crown Dependency | `guernsey` | [Guernsey](https://en.wikipedia.org/wiki/Guernsey) |
| Calf of Man | Crown Dependency | `osm-way-25987471` | [Calf of Man](https://en.wikipedia.org/wiki/Calf_of_Man) |
| Anglesey (Ynys Môn) | Wales | `anglesey` | [Anglesey](https://en.wikipedia.org/wiki/Anglesey) |

## Journeys

- **Faith, stories and island communities** (`islands-and-community`): Iona, Lindisfarne, Devenish, Scattery, Bardsey, Anglesey, Erraid, Eigg.
- **How islands connect** (`islands-and-connections`): Eel Pie, Achill, Lindisfarne, Erraid, Dursey, Isle of Man, Guernsey, Inishmaan.
- **Reading island landscapes** (`reading-island-landscapes`): Staffa, Eigg, Rathlin, Inishmaan, Lundy, Brownsea, Calf of Man, Hirta.

These are reading sequences, not travel itineraries. In the atlas use `/?journey=<slug>`; generated reading pages are `/learn/<slug>/`. The collections hub and core sitemap link them. Profile connections use assigned canonical island paths; modifier/new-tab links remain normal links.

## Identity gate: Llanddwyn withheld

Research found canonical `osm-way-310149701`, **Ynys y Clochydd**, is a **0.0012 km²** islet at approximately **53.13716, -4.40933**, while its aliases/Wikipedia field point to **Ynys Llanddwyn**, a substantially larger neighbouring island (Wikipedia describes about **0.3 km²**, around **53.1375, -4.4125**). Attaching Llanddwyn history to that record would repeat an unresolved entity match. The pilot therefore uses **Anglesey** instead. Tests keep the questionable ID out of profiles and journeys.

No canonical correction was made while another chat owns photo-related data writes. The queued follow-up must establish the actual boundary/entity and correct aliases/Wikipedia through the appropriate pipeline, then inspect attached content and images. A matching article title alone is insufficient evidence. This is a recorded data issue, not a claim that the existing Llanddwyn association is fixed.

## Release and coordination

The scoped release was built from the then-current production branch, preserving the published Irish-photo data and excluding active research caches. Commit `4cef2d8` includes `learning.js`, `learning.css`, the JSON sidecar and Python helper with the app/generator changes. [Pages run 41695300995](https://github.com/Drummond1/britishislands/actions/runs/41695300995) succeeded. The public homepage, modules, sidecar, `/learn/` and one journey page matched the built artifact byte for byte. CI generated all four learning pages and 11,212 island landings. Canonical island data was not changed by this release.

Local app preview: <http://127.0.0.1:8766/>. Isolated reading-page preview: <http://127.0.0.1:8767/learn/>. These require their local preview servers to remain running.

## Next priorities

1. Resolve the Llanddwyn entity mismatch without disrupting the active photo writer; independently check any changed aliases and attached content.
2. Expand from 20 to 100 profiles in reviewed batches, using authoritative open-licensed sources and the same claim/source/identity checks. Keep regional and inland variety. Add more specific shared-event, writer and geology connections as evidence grows.
3. Improve Ask citation coverage and contradiction handling beyond the deterministic pilot. Expand evaluation with known-answer/source cases before claiming answer-wide grounding.
4. Add authoritative local-language explanations and licensed pronunciation recordings where available. Never fabricate pronunciation, etymology or audio provenance.
5. Audit existing access notes separately, including unqualified safe-crossing/bridge-opening guarantees. No new travel advice was added in this pilot.
