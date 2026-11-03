# Find My Island SEO and GEO strategy

Updated 2 November 2026. Scope: **https://www.findmyisland.com**. This replaces the July strategy with a plan based on the current site and repository. SEO means discovery in conventional search; GEO means discovery and citation in generative search and AI answers.

**Recommendation:** concentrate the next 90 days on a small set of excellent island guides and comparisons, supported by reliable facts, clear sources and measurable routes into the interactive atlas. The catalogue supplies breadth; reviewed pages supply the reasons to visit and cite it.

**Primary outcome:** engaged island discovery. Count visits that lead to a map interaction, another island profile, a saved island or a useful outbound visit. Treat property referrals and dataset citations as secondary outcomes until their value is measured.

**Project policy:** retain the existing no-deindex override for atlas records. Preserve shareable records and current sitemap eligibility; do not introduce bulk `noindex`, remove atlas records or launch enrichment/publishing loops as part of this strategy. Existing query-view handling remains separate. Ferry promotion stays subject to the freeze in [QUEUE.md](QUEUE.md). [ETHICS.md](ETHICS.md) governs every workstream.

## 1 What has changed since the previous strategy

The foundations already exist: canonical `/islands/{nation}/{slug}/` pages, nation and collection hubs, `Landform` markup, segmented sitemaps, trust pages and explicit permission for OAI-SearchBot. The task is to improve their usefulness and accuracy, rather than recreate those features.

The following observations were checked on 2 November 2026. Live pages were retrieved through Firecrawl; source code and local reports supplied implementation evidence. These are a bounded sample, not a complete crawl or a current Search Console report.

| Evidence | Strategic consequence |
| --- | --- |
| Local `data/islands.json` contains 11,212 records; 1,620 have `shortDescription`, and 2,799 have an `image` or non-empty `images`. These are corpus counts, not indexed-page counts. | Improving every record equally would spread effort too thinly. Select pages with clear intent and enough reliable material. |
| [Scottish islands map](https://www.findmyisland.com/islands/scotland/) is principally a short introduction and links. [Shetland](https://www.findmyisland.com/collections/shetland/) is principally a one-sentence introduction and 51 links. | Existing hubs need useful maps, comparisons and explanations to fulfil their titles. |
| [Fair Isle](https://www.findmyisland.com/islands/scotland/fair-isle/) has undated population, very short sections, guide links but little of the underlying story content, and just one listed source. | Bring verified facts and useful summaries into the canonical HTML itself. |
| Fair Isle says the observatory is being rebuilt, while the [observatory's booking page](https://www.fairislebirdobs.co.uk/booking.html) describes accommodation and bookings for 2026 and 2027. The island page nevertheless says “Last reviewed: 2026-10-28”. | Fix factual freshness and the meaning of review dates before expanding this template. |
| `generate_seo_artifacts.py` prints the build date as “Last reviewed”. Several sitemap dates also use the current date or a shared file timestamp. | Separate generation, content modification and actual review. |
| [Whisky islands](https://www.findmyisland.com/collections/whisky-distilleries/) combines distillery entries, silent stills, stories and planned stills. Its first question asks which Scottish islands make whisky without naming the qualifying islands in the answer. | Lead with a direct, verified answer; clearly distinguish production status and historical connections. |
| [Islands for sale](https://www.findmyisland.com/collections/for-sale/) includes whole islands, portions, homes and a houseboat. Some listed broker names have no clickable source. | Distinguish the thing being sold and its verification status before targeting purchase-intent searches. |
| [About](https://www.findmyisland.com/about/), [methodology](https://www.findmyisland.com/methodology/) and [dataset](https://www.findmyisland.com/dataset/) exist but contain little detail. Methodology refers readers to repository docs without linking them. | Expand the existing pages into usable evidence of responsibility and method. |
| [The ferry sitemap](https://www.findmyisland.com/sitemap-ferries-verified.xml) still promotes 13 ferry URLs; the generator still has those paths despite the queue's ferry freeze. | Align generated discovery surfaces with the existing freeze. A filename containing “verified” does not establish verification. |
| `data/geo_prompt_benchmark_latest.json` is dated 2 August and contains 50 prompts with zero scored results. The runner creates templates; it does not query assistants. | Run and score a real benchmark before reporting any GEO improvement. |

The July Search Console findings are historical. A fresh authenticated baseline was subsequently captured on 2 November: **192 Web impressions, zero clicks and average position 66.8** for 4–31 October, plus **30 Google AI-feature impressions**, 28 for Eel Pie Island. Eel Pie Island's Web average position was **10.82** on 33 impressions. Prioritise that page first while recognising the small sample. See [the current baseline and exports](GSC-BASELINE-2026-11-02.md). Bing and visitor-conversion baselines remain unverified; Core Web Vitals has insufficient field data in the GSC overview.

## 2 Choose searches the atlas can answer well

The strongest positioning is a visual, source-backed atlas of the islands of Britain and Ireland. Its distinctive contribution is connecting geography with culture, names, stories and interests across many islands.

Start with the following hypotheses. These are proposed query clusters, not measured search volumes or promised ranking opportunities. Reorder them using current GSC impressions, positions, indexed status and visitor behaviour in week one.

| Priority | Search intent and examples | Page to improve |
| --- | --- | --- |
| 1 | Interest discovery: islands with castles; Scottish islands with whisky distilleries; books set on British and Irish islands. | Existing castle, whisky and book guides. Match each answer to precisely defined inclusion rules. |
| 2 | Regional orientation: Scottish islands map; Shetland islands map; islands of Loch Lomond; Thames islands map. | Existing nation and regional hubs with visible maps and useful comparison tables. |
| 3 | Individual islands: Bute map; Staffa island; St Mary's Scilly map; where is Eel Pie Island. | A first group of 10 strong island profiles. July impressions provide leads only; verify current demand. |
| 4 | Facts and comparisons: Fair Isle population; Gaelic island names; largest islands in a defined region. | Island profiles and a few sourced data collections. Include years, definitions and missing-data notes. |
| 5 | Purchase intent: whole islands for sale in Scotland or Ireland; houses for sale on islands. | The property guide, after scope and current listing status are separated. |

Keep each query family attached to one principal page. A regional hub answers a regional question; a profile answers an island question; the interactive filter supports exploration. Avoid creating separate pages for every filter combination.

Defer ferry timetables, live crossing advice, generic accommodation guides and mass “best islands” articles. The ferry freeze and ethics charter already limit those subjects, and the atlas has more defensible opportunities.

## 3 Make the best pages complete answers

### Island profiles

Upgrade 10 profiles first, then expand to 25 only after the template and review process work. The initial selection should include Fair Isle, Bute, Staffa, St Mary's in Scilly, Anglesey, Lewis and Harris, Lundy, Brownsea, Eel Pie Island and Iona, subject to current demand and source availability.

Each profile should provide:

- A concise opening explaining location, identity and distinctive interest.
- A readable map in the returned HTML, with a lightweight fallback and a clear route into the interactive atlas.
- A fact table with units, population year, source and measurement confidence. Unknown population must not become zero or “uninhabited”.
- Two or three useful sections drawn from verified island material: geography, history, names, culture or publicly documented access context. No filler to reach a word count.
- Short, original summaries of the relevant interest stories, with citations beside the claims. Link to deeper guides without making readers open several pages to learn the essential facts.
- The island's verified local-language names and cultural authority where available.
- Proper photograph credit and licence, meaningful alt text and reserved image dimensions.
- A real editor/reviewer credit, correction route and honest modification/review dates.
- Relevant internal links. Distinguish geographical neighbours from islands with similar interests; do not describe a same-country list as nearby.

A profile clears editorial review when its essential claims are traceable, its dated facts are current for the stated reference year, its map and image identify the correct island, and its canonical HTML stands on its own. Three copied summaries do not become independent corroboration.

### Interest guides

Improve the existing guides before building more. The first paragraph and comparison table should directly answer the page's question. Follow with examples, inclusion rules, evidence and a useful map action.

For whisky, show active whisky production, closed distilleries, planned production and cultural stories as separate groups. Gin production or a shipwreck story must not qualify an island for an answer about current whisky production. Verify current status against official producers; retain historical stories in their appropriate section.

For property, show **whole island**, **part of island**, **home on an island** and **other property**. A whole-island count must exclude the other groups. Display broker, source link, last status check and whether availability is confirmed or unknown. Keep asking prices on broker pages under the existing policy. Any future property schema must describe the actual offer, rather than imply the whole island is for sale.

For castles, distinguish islands containing a castle from small castle islets and from places a visitor can enter. For tidal islands, describe the connection and link to official access information without publishing crossing times or implying safe access. For wildlife, keep information at the permitted island level and honour the sensitive-species exclusions.

Retain complete relevant rows in crawlable HTML, using accessible expandable sections where needed. The current whisky page sends readers to the application for some remaining entries; the search landing page should contain the evidence needed to support its stated totals.

### Regional hubs

Start with Scotland, Shetland, Loch Lomond and the Thames. Give each a map, an explanation of scope, a comparison table, a few distinct starting points and links to its islands and interest guides. Use an actual region-specific map view where the interface supports it.

Label catalogue totals as atlas coverage. Do not present the atlas's record count as an official answer to “How many islands does Scotland have?” without reconciling definitions, geographic extent and inclusion of inland or unnamed features.

## 4 Strengthen technical discovery

Keep the static site and current URL scheme. A platform migration is unnecessary for the content work.

1. **Audit a representative URL sample.** Test the homepage, four hubs, five guides, ten profiles, a legacy profile, a query view and a nonexistent slug. Confirm HTTP status, canonical, robots directive, useful initial HTML, image loading and internal links. Inspect Google's selected canonical for the priority pages.
2. **Fix dates.** Store or derive genuine per-page content modification dates; persist review dates only when a review occurs. Build dates belong in release metadata. Source retrieval is not automatically editorial review. Google recommends accurate `lastmod` values reflecting significant page changes. [Google sitemap guidance](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap)
3. **Keep sitemap policy explicit.** Retain existing canonical, named/prose eligibility and the no-deindex override. Add priority pages to the correct segment when eligible. Reconcile ferry URLs in the core and ferry sitemaps with the documented freeze. Do not regenerate every URL's freshness on routine builds.
4. **Consolidate legacy URLs.** `/profiles/fair-isle.html` still returns a complete 200 page. Maintain canonical signals while preparing a one-hop 301/308 redirect plan for an edge layer that supports it. Audit old nation paths and merged IDs as well. Query-aware rules must preserve unrelated atlas parameters. JavaScript address changes do not provide HTTP redirects. A DNS or hosting cutover is a separate deployment decision.
5. **Improve structured data already present.** Retain `Landform` and correct entity identifiers. Add stable entity IDs, `WebPage`, breadcrumbs, publisher and licensed `ImageObject` information where supported by visible content. Validate vocabulary and factual correspondence. Use `Dataset` only with real metadata, access and licensing. No schema type guarantees a rich result or AI citation.
6. **Measure mobile performance before prescribing fixes.** Baseline the homepage, one guide and one profile in PageSpeed/Lighthouse and field data where available. Aim for field p75 LCP at most 2.5 seconds, INP at most 200 ms and CLS at most 0.1. Reserve image space, use appropriate thumbnails, and defer map/3D work without hiding the main answer. Retain clustering, virtualisation and lazy loading. July Lighthouse figures are not today's baseline. [Google Core Web Vitals guidance](https://developers.google.com/search/docs/appearance/core-web-vitals)

## 5 Make the site useful as an AI source

Google's guidance prioritises useful original content and ordinary search eligibility for its generative features. Important answers should be available as text with supporting images and matching structured data; it requires no special AI file or schema. [Google AI guidance](https://developers.google.com/search/docs/appearance/ai-features), [Google generative search guide](https://developers.google.com/search/docs/fundamentals/ai-optimization-guide)

Apply that to every priority page:

- Put the direct answer immediately below the relevant heading. For a list question, name the qualifying islands.
- Keep each important claim with its island identity, source, reference year and qualification. Avoid floating numbers or vague “currently” language.
- Provide compact comparison tables and explicit definitions. Clearly distinguish verified absence, missing data and unreviewed visitor contributions.
- Keep displayed facts, JSON-LD, downloadable data and the site's own Ask answers consistent.
- Publish original comparisons or analysis that add something beyond the upstream source. AI systems can otherwise cite that source directly.
- Keep access open to search crawlers. The live robots file already explicitly allows OAI-SearchBot, so changing that is not an early growth task. OpenAI distinguishes its search crawler from GPTBot training access; training permission is a separate choice. [OpenAI crawler guidance](https://developers.openai.com/api/docs/bots)
- Maintain `llms.txt` as a small navigation aid with working canonical links and accurate counts. Treat it as housekeeping, not the main discovery channel.

Do not use hidden AI instructions, invented reviews, unsupported superlatives or bulk rewritten source pages. Do not add FAQ markup in expectation of automatic search enhancements; visible questions must earn their place by helping readers.

## 6 Earn references through distinctive evidence

Expand the existing About, methodology, sources and dataset pages. Name the responsible editor; explain inclusion, water-body classification, measurements, language handling, corrections and limits. Make their links work on the public site.

Build one carefully scoped, reproducible data story first: **a map of castle islands across Britain and Ireland**, with a downloadable table, explicit definition, cited entries and a dated release. A second candidate is the geography of island names, once cultural-authority validation is sufficient. Choose the topic using the first month of demand data.

Offer a lightweight map embed or a source-backed table to relevant island organisations, heritage groups, local publications and geography educators. Link back to the relevant collection and methodology. Prepare a shortlist of 10 appropriate recipients and a useful pitch for each. Contacting them is a separate action requiring explicit sending authority.

Provide a public versioned release only for material the project can redistribute. Preserve OSM, Wikimedia and other upstream attribution and licence obligations; do not label the combined corpus CC0. Prefer a real download and clear field documentation over a metadata-only dataset page. Register a DOI only when there is a maintained release worth citing.

## 7 Measure discovery and useful visits

Establish a fresh 28-day baseline and an equal-length comparison, with the previous year where available because island interest is seasonal. Segment UK and Ireland visitors, devices, branded searches, page families and priority pages.

**Search Console:** reconnect the property, export queries/pages and inspect priority URLs. Track non-brand clicks, impressions, queries moving into the top 20/10, selected canonicals and priority-page indexation. Google now documents separate generative AI performance reports; record the visibility data actually exposed in this property and retain ordinary Web reporting for the overall trend. Do not infer a separate AI click total from an impressions-only view. [Google reporting announcement](https://developers.google.com/search/blog/2026/06/gen-ai-performance-reports?hl=en)

**Bing Webmaster Tools:** use AI Performance for citations, grounding queries and cited pages. Topics Portfolio, introduced in October, may supply opportunity queries when the site has enough activity. Its estimates are directional and apply to Bing's supported AI surfaces, not every assistant. [Bing AI Performance](https://blogs.bing.com/webmaster/2026/2/Introducing-AI-Performance-in-Bing-Webmaster-Tools-Public-Preview/), [Topics Portfolio](https://blogs.bing.com/webmaster/2026/10/introducing-topics-portfolio-beta-in-ai-performance/)

**Visitor outcomes:** GTM is installed; verify what it actually records. Track map opens from landing pages, subsequent island views, saves, relevant broker/official-source clicks and accepted contributions. Measure sessions with at least one useful action as well as action rates. Segment identifiable AI referrals, recognising that missing referrers prevent a complete AI-traffic count. Keep contribution text and private email addresses out of analytics events.

**Analytics setup check, 2 November:** the existing GTM container has no tags.
A shared, opt-in loader and six controlled events are now implemented and
tested locally; five data-layer fields are saved as unpublished GTM drafts.
The account and sharing choices are approved; separate action-time legal-terms
confirmation is pending after automatic approval review blocked Next. An
allowlisted event trigger is also saved as an unpublished draft. There is no
measurement ID or verified live collection yet. See [the installation record](ANALYTICS.md).

**Independent AI benchmark:** reuse the 50 existing prompts, fixing misleading ferry or live-property prompts before freezing a version. Complete a first scored run on ChatGPT Search, Copilot and Perplexity, with date, product/model, search mode, country/language and fresh-chat conditions. Retain answer evidence and cited URLs. Repeat 10 priority prompts weekly and the full set monthly; use repeated runs where results fluctuate.

Report citation rate as prompts citing the site divided by completed prompts, separately for each product. Report canonical URL share among site-citing results and factual accuracy among completed answers. Unrun or failed prompts are unscored, not false. Brand mentions without links are not citations. The current runner needs denominator and incomplete-run handling before it can be trusted for partial scores.

Use these operational targets, not traffic forecasts:

| By day 90 | Acceptance measure |
| --- | --- |
| Reliable measurement | Fresh GSC/Bing/visitor baselines and one completed, scored cross-product benchmark. |
| Stronger entry points | 25 reviewed profiles, 4 substantive regional hubs and 3 improved existing guides. |
| Trustworthy facts | All priority pages have claim-level sources, dated population/measurements where relevant, correct images and honest review dates. |
| Technical clarity | Priority URLs return 200 with consistent canonical and schema; invalid URLs return genuine errors; legacy handling is documented and verified where deployed. |
| Evidence of growth | Compare non-brand clicks, engaged discovery sessions and citation rate with baseline; report absolute numbers and denominators. Set numerical growth goals after the baseline. |

## 8 The 90 day sequence

Suggested capacity is 6–8 hours a week for 12 weeks. Allocate roughly half to research and editing, a quarter to implementation, and the remainder to measurement and useful distribution. Reduce the page count if review quality requires more time.

| Period | Work | Exit condition |
| --- | --- | --- |
| Days 1–14 | Restore reporting; audit priority URLs; repair review-date semantics; resolve ferry promotion drift; specify whisky/property categories; review Fair Isle; baseline performance and 10 AI prompts. | A usable baseline, explicit page/query map and a working reviewed-page template. |
| Days 15–45 | Upgrade the first 10 profiles, 3 guides and 4 regional hubs. Expand trust pages. Make essential facts available in canonical HTML and test the path into the map. | Pages pass factual, source, image, mobile and canonical checks. First full AI benchmark completed. |
| Days 46–90 | Expand to 25 profiles; publish one reproducible data story; prepare targeted distribution; add change-only IndexNow notifications if Bing discovery is slow. Repeat measurements and prioritise the next cohort. | A repeatable process with measured discovery, visitor actions and citation outcomes. |

The coding agent can prepare implementation, conduct bounded research, assemble comparisons and produce distribution drafts. Drummond supplies account reconnection where necessary, first-hand observations and explicit authority for external outreach. Do not imply first-hand experience where none exists.

At day 30, prioritise indexability and canonical problems if priority pages remain undiscovered. If pages are indexed but receive few impressions, improve query relevance, distinctiveness and references. Work on title/snippet click-through when pages already have meaningful visibility near the first page. If clicks arrive without map use or further exploration, improve the landing-page journey. Expand content only when the evidence identifies a useful next group.

## 9 First implementation backlog

| Order | Concrete task | Main implementation area | Done when |
| --- | --- | --- | --- |
| 1 | Establish fresh reporting and a priority URL/query sheet. | GSC, Bing, existing analytics and benchmark files | Dates, filters and baseline values are recorded; unknowns remain explicit. |
| 2 | Separate build, modification and review dates. | `scripts/generate_seo_artifacts.py`, `scripts/seo_interest_guides.py` and review metadata | Rebuilding an unchanged page cannot claim a new editorial review. |
| 3 | Align ferry sitemap and discovery links with the freeze. | Generator and deployed sitemap segments | Every promoted route passes the existing policy, or promotion is removed without a blanket atlas deindex change. |
| 4 | Make whisky and property answers match their qualifying rows. | Guide generator and attributed interest/property records | Active production and whole-island claims exclude non-qualifying items. |
| 5 | Upgrade the profile template and first 10 profiles. | Generator, existing detail records and editorial content | Useful content is present without opening the application; facts and credits pass review. |
| 6 | Improve regional hubs, contextual links and public trust pages. | Generator and public landing assets | Each target page fulfils its title, connects to useful islands and offers a relevant map action. |
| 7 | Replace benchmark templates with valid scored evidence. | Existing prompt set and runner | Completed/failed/unrun states and KPI denominators are correct. |

Implementation should be reviewed in small diffs, retaining the canonical dataset schema and curated regression spine. Changes to generated pages must be made in their generators or source records so the next Pages build preserves them.

**Implementation status, 2–3 November:** current GSC exports and an Eel Pie Island URL inspection are complete. Reviewed generator changes remove false review/modification dates, respect the ferry promotion freeze, expose existing sourced stories and credits, improve entity markup, fix map-link escaping and add public trust links. Guide rows and source counts are complete and explicit. Benchmark scoring distinguishes unrun/failed answers and the continuous script preserves measured results. Desktop/mobile verification also corrected landing-page backgrounds and card colours that made text hard to read below the first screen. **33 focused tests pass** and all **11,212** canonical plus **11,212** legacy profiles passed isolated rendering checks. Canonical data and running schedules are unchanged. The SEO integrity batch is isolated in local release commit `35e1c5a`; automatic approval review requires explicit user permission before publishing this exact release. Separately, the consent layer deployed in `97f72466`, the dedicated Analytics property was created, and all six site event names reached it in Preview. The release also includes the tested withdrawal correction; GTM remains unpublished pending deployment and a live retest. See [ANALYTICS.md](ANALYTICS.md) for exact verification and approval state. This is a verified first implementation batch, not completion of the 90-day editorial programme.

## 10 Project references

- [SEO and GEO implementation](SEO-GEO.md)
- [Historical Search Console findings](GSC-CTR-FINDINGS.md)
- [GEO benchmark procedure](GEO-BENCHMARK.md)
- [Deployment](DEPLOYMENT.md)
- [Current queue and ferry freeze](QUEUE.md)
- [Ethics](ETHICS.md)
- [Validation](VALIDATION.md)
