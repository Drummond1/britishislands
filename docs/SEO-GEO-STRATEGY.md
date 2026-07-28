# Find My Island: SEO + GEO Strategy

> Repo copy of the strategy brief (source: Desktop `find-my-island-seo-geo-strategy.md`,
> 28 July 2026). Operational loop: `scripts/run_continuous_seo_geo.sh`.
>
> **Project override:** Tier C pages stay **indexable** for now (do not noindex /
> remove from sitemaps) unless the maintainer explicitly reverses that decision.
> The continuous loop still executes every other strategy workstream: brand,
> trust pages, Landform schema, segmented sitemaps, flagship depth, hubs, CWV,
> GEO benchmark, and coverage enrichment.

Research and live-site audit completed on 28 July 2026.

## Executive verdict

Find My Island’s best opportunity is to become **the definitive data-led atlas of British and Irish islands**—not another general travel blog.

The map and underlying data are genuinely differentiated. The present SEO risk is that search engines see thousands of very thin, automated pages before they see that value. The strategy should therefore be:

> Keep every island shareable on the map, but make indexability an editorial privilege.

Start with roughly 100 exceptional, authoritative pages, then expand only when each new profile clears a documented quality threshold.

## What the live audit found

| Finding | Impact |
|---|---|
| The [sitemap](https://www.findmyisland.com/sitemap.xml) contains 11,402 URLs, including 11,380 island profiles. | Search engines are being asked to evaluate a very large site immediately. |
| The live data contains 4,310 records sourced as `osm-unnamed`; 5,011 sitemap URLs contain machine identifiers. | High risk of index bloat, duplicate entities and low-value results. |
| Only 1,621 records have a short description, and just 27 have all four editorial sections: history, geography, transport and accommodation. | Most profiles cannot currently compete with Wikipedia, official tourism organisations or specialist guides. |
| Direct canonical pages such as [Fair Isle](https://www.findmyisland.com/islands/scotland/fair-isle/) expose one sentence and a fact list, while the interactive application contains substantially richer data. | The best content is missing from the page search engines and visitors land on. |
| An [unnamed profile](https://www.findmyisland.com/islands/ireland/osm-way-827589756/) is indexable with generic text. | This is precisely the kind of page that should remain usable in the atlas but stay out of search. |
| JSON-LD uses `@type: "Island"`, but Schema.org has no `Island` type. | The central entity markup is invalid. Use [`Landform`](https://schema.org/Landform) or `Place`. |
| Every sitemap URL currently has the same `lastmod` date plus `priority` and `changefreq`. | Google ignores priority/changefreq and only trusts consistently accurate, per-page significant modification dates. [Google sitemap guidance](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap) |
| The visible brand, page title, publisher and web-app name alternate between “Find My Island” and “Isles of Britain.” | Weakens brand/entity consolidation. |
| There are no public About, methodology, editorial, corrections, licensing or contact pages. | Search engines, journalists and AI systems cannot easily establish provenance or responsibility. |
| [`llms.txt`](https://www.findmyisland.com/llms.txt) references two 404 resources and recommends a legacy query-parameter URL. | Update it, but do not treat it as a ranking lever. |
| A mobile Lighthouse lab run scored the homepage 60 for performance, with 10.0s LCP. Fair Isle scored 77, with 3.0s LCP and 0.208 CLS. | Both exceed Google’s recommended LCP ≤2.5s and CLS <0.1 targets. [Core Web Vitals guidance](https://developers.google.com/search/docs/appearance/core-web-vitals) |
| The [Hebrides ferry page](https://www.findmyisland.com/ferries/hebrides/) exposes raw codes and some same-terminal route pairs. | Ferry queries are valuable but volatile; clean and verify this dataset before targeting them aggressively. |

The presence of many automated records is not automatically a penalty. The danger is asking Google to index large amounts of unoriginal or minimally useful content. Google explicitly recommends excluding scaled pages that add little user value. [Google’s spam policy](https://developers.google.com/search/docs/essentials/spam-policies)

## 1. Rebuild the indexing model

Create three quality tiers.

### Tier A: definitive editorial profiles

Initially 40–60 major islands: Skye, Mull, Islay, Lewis and Harris, Arran, Iona, Fair Isle, St Kilda, Anglesey, Isle of Wight, Lundy, Brownsea, Rathlin, Achill, the Aran Islands, Jersey, Guernsey and similar.

Each should contain original synthesis, full provenance, useful planning information and a complete entity record.

### Tier B: authoritative data profiles

Eventually 200–500 named islands with enough verified material to answer a real query: unambiguous identity, map, image, multiple meaningful facts, source dates, related islands and at least two or three trustworthy sources.

### Tier C: raw atlas records

All unnamed, ambiguous, duplicate and minimally documented map features:

- Preserve their unique shareable links.
- Set `noindex,follow`.
- Remove them from XML sitemaps.
- Do not block them in `robots.txt` until search engines have seen the `noindex`.
- Merge duplicates and redirect retired URLs to the correct entity.
- Return 404/410 where a feature proves not to be a real island.

This will not make the atlas smaller. It will make the searchable part credible.

Split the sitemap into diagnostic groups:

- `sitemap-core.xml`
- `sitemap-islands-editorial.xml`
- `sitemap-collections.xml`
- `sitemap-ferries-verified.xml`
- `sitemap-images.xml`

Include only URLs you actually want indexed. Record significant `lastmod` dates per page.

## 2. Unify the profile and interactive experience

A canonical island URL should return the complete page directly:

`/islands/scotland/lewis-and-harris/`

It should include all useful content already present in the application—names, population year, source confidence, geology, lighthouses, history and transport—then progressively enhance into the interactive map.

Do not maintain one thin “crawler page” and a richer JavaScript experience. Users and crawlers should receive the same substantive information.

Legacy URLs such as `/?island=lewis-and-harris` and `/profiles/*.html` should issue genuine HTTP 301 redirects to the canonical path. GitHub Pages cannot perform all dynamic redirects cleanly, so use an edge layer such as Cloudflare or migrate the deployment to hosting with redirect rules.

Also remove the visible sentence:

> “Canonical profile for search engines and AI crawlers.”

It is written for machines, not visitors, and conflicts with Google’s people-first guidance. [Google’s content guidance](https://developers.google.com/search/docs/fundamentals/creating-helpful-content)

## 3. Use this island-page blueprint

Every Tier A profile should contain:

1. **Breadcrumb:** Home → Scotland → Shetland → Fair Isle
2. **H1:** Fair Isle
3. **Answer-first summary:** 40–70 words explaining where it is, what type of island it is and why it is notable.
4. **Key facts table:** nation, archipelago/water body, area, population and year, highest point, access type and coordinates.
5. **Interactive map plus static fallback:** so the geography remains understandable without JavaScript.
6. **Names and etymology:** English, Gaelic, Irish, Manx, Welsh, Scots or Norse forms where verified.
7. **Geography and geology.**
8. **History and heritage.**
9. **Wildlife and conservation.**
10. **How to reach it:** with official links and “last verified” date.
11. **Nearby and similar islands.**
12. **Sources:** inline citations, not merely a general attribution at the bottom.
13. **Authorship and review:** author/editor, methodology link, date reviewed and meaningful date modified.
14. **Correction mechanism:** “Report an error or contribute local knowledge.”

Use exact years and units: “population 55, 2022 NRS figure,” rather than an undated “population 55.” This is substantially easier for both humans and answer engines to quote correctly.

### Structured-data graph

Use:

- `WebPage` or `Article`
- `mainEntity` → `Landform` or `Place`
- `BreadcrumbList`
- `ImageObject`
- `Person`/`Organization` for author, reviewer and publisher
- `sameAs` for the correct Wikidata, Wikipedia and official-community identity
- `identifier` for OSM and Wikidata IDs
- `containedInPlace`, `geo`, `alternateName`, `hasMap` and sourced `additionalProperty` values

Use `TouristDestination` only on substantial visitor-oriented pages. There is no special “GEO schema”: Google explicitly says AI features require ordinary SEO eligibility, textual content and accurate structured data—not AI-specific markup. [Google AI-search guidance](https://developers.google.com/search/docs/appearance/ai-features)

Create a separate dataset landing page using `Dataset`, `DataCatalog` and `DataDownload`, with version, licence, provenance, variables, coverage and downloadable formats. [Google’s Dataset guidance](https://developers.google.com/search/docs/appearance/structured-data/dataset)

## 4. Build query-led information architecture

The broad entity SERPs are dominated by Wikipedia, official tourism bodies, National Trust, Wikivoyage and established travel publishers. Find My Island should first target combinations where its structured dataset is uniquely useful.

| Cluster | Example queries | Target page |
|---|---|---|
| Atlas/maps | “Scottish islands map”, “British and Irish islands map” | Homepage and nation hubs |
| Counts and definitions | “how many islands are in the UK?”, “what counts as an island?” | Methodology-led research pages |
| Lists and rankings | “largest Scottish islands”, “inhabited Irish islands” | Data table + map collections |
| Archipelagos | “Outer Hebrides islands map”, “islands of Loch Lomond” | Archipelago/water-body hubs |
| Entity facts | “Fair Isle population”, “Anglesey area”, “Islay Gaelic name” | Island profiles |
| Access | “Scottish islands without a car”, “islands accessible by bridge” | Editorial comparison guides |
| Specialist data | “Scottish islands with lighthouses”, “Gaelic island names” | Original data visualisations |
| Ferries | “how to get to Mull”, “Hebrides ferry map” | Verified route hubs and profiles |

The missing middle layer is particularly important. Add hubs for:

- Inner Hebrides
- Outer Hebrides
- Orkney
- Shetland
- Isles of Scilly
- Channel Islands
- Aran Islands
- Loch Lomond
- Lough Corrib
- Thames islands

Nation hubs should contain explanation, statistics, maps, tables and links—not only a list of 50 names.

Do not allow every map filter to become indexable. Hand-select canonical collections with demonstrable search intent and unique explanatory content.

## 5. Turn the dataset into an authority moat

The most linkable asset is not another “10 best islands” article. It is the reproducible dataset.

Publish:

- A clear definition of island, islet, tidal island, river island, crannog and rock.
- Inclusion/exclusion criteria.
- Source and licence matrix for OSM, Wikidata, Wikimedia, NRS, BGS and ferry data.
- Confidence methodology.
- Versioned changelog.
- CSV/GeoJSON downloads or a documented API.
- A citable release on GitHub or Zenodo with a DOI, if licensing permits.

Strong digital-PR projects could include:

- “How many islands do Britain and Ireland actually have?”
- “Every inhabited Scottish island ranked by population and ferry access.”
- “The Gaelic, Irish, Welsh and Manx names of the islands.”
- “Britain and Ireland’s lighthouse islands.”
- “The unnamed islands still missing from public records.”

Pitch the resulting research to island community organisations, local newspapers, geography departments, map publications, outdoor media and national tourism bodies. Offer embeddable maps with a restrained branded attribution link.

This also helps GEO: the foundational GEO paper found that relevant citations, quotations and quantitative evidence can improve visibility within a generative response, although its reported gains were experimental—not a promise of organic discovery. [Original KDD research](https://arxiv.org/abs/2311.09735) A recent critical review found no stable cross-platform technique that guarantees long-term organic discovery, so traditional retrieval, authority and measurement remain essential. [2026 critical survey](https://arxiv.org/abs/2607.14035)

## 6. Clarify the brand and establish trust

Use one identity everywhere:

**Find My Island**  
*The British & Irish Islands Atlas*

Update the H1, `<title>`, `og:site_name`, WebSite schema, Organization schema, application name, footer and `llms.txt`. Treat “Isles of Britain” as an old descriptor, not the publisher.

This matters because Google derives site names from structured data, titles, headings and visible homepage references and recommends consistent naming. [Google site-name guidance](https://developers.google.com/search/docs/appearance/site-names)

Add:

- About Find My Island
- Founder/editor profiles
- Editorial and review policy
- Data methodology
- Sources and licensing
- Corrections and contributions
- Contact
- Privacy/cookie information
- Dataset changelog

Add a crawlable, stable favicon and a homepage social-sharing image.

## 7. GEO discovery and measurement

Your wildcard `robots.txt` currently allows OAI-SearchBot, so no special change is necessary. OpenAI says inclusion in ChatGPT summaries and snippets requires that OAI-SearchBot not be blocked. [OpenAI publisher guidance](https://help.openai.com/en/articles/12627856-publishers-and-developers-faq)

Update `llms.txt` because its data and ethics links currently return 404, but keep its priority low. Google states that it does not require or use special AI files to appear in its generative search features.

Set up:

- Google Search Console, including the 2026 generative-AI performance reporting.
- Bing Webmaster Tools and its **AI Performance** report: citations, cited URLs, grounding queries, topics, intents and citation share. [Bing AI Performance](https://www.bing.com/webmasters/help/ai-performance-9f8e7d6c)
- IndexNow for genuinely added, changed or removed indexable URLs. [IndexNow documentation](https://www.indexnow.org/documentation)
- Analytics segments for `chatgpt.com`, Copilot, Gemini and Perplexity referrals.
- Events for “open map,” “save island,” “view ferry,” “contribute,” and meaningful outbound clicks.
- Server-log monitoring for Googlebot, Bingbot and OAI-SearchBot.
- A repeated 50-prompt benchmark covering maps, facts, comparisons and itinerary questions. Record cited domains and factual accuracy, not merely whether the brand is mentioned.

## 90-day execution roadmap

### Weeks 1–2: stop dilution

- Noindex and remove low-quality profiles from sitemaps.
- Fix the invalid `Island` schema.
- Unify the brand.
- Repair or remove broken `llms.txt` references.
- Add trust and methodology pages.
- Establish Search Console, Bing and analytics baselines.
- Fix legacy canonical/redirect handling.

### Weeks 3–6: create the winning template

- Make canonical profiles full-content, progressively enhanced pages.
- Build 25–30 flagship island profiles.
- Add breadcrumbs and related-island links.
- Fix image dimensions, CLS and homepage loading behaviour.
- Normalize ferry data and mark verification dates.
- Build the first archipelago hubs.

### Weeks 7–12: earn authority

- Expand to 50–75 flagship profiles.
- Publish three to five original data collections.
- Launch the dataset/methodology page and downloadable release.
- Conduct outreach around one major data story.
- Enable IndexNow.
- Review indexation and AI citation data before expanding further.

## Success metrics

Do not judge success by the number of indexed pages.

Track:

- Percentage of curated sitemap URLs indexed.
- Zero unnamed pages indexed.
- Non-branded impressions and clicks by page cluster.
- Queries entering the top 20 and top 10.
- Passing field Core Web Vitals.
- Relevant referring domains and community citations.
- Bing AI citations, grounding topics and unique cited pages.
- Google generative-search visibility.
- ChatGPT and other AI referral sessions.
- Factual accuracy in the prompt benchmark.
- Map opens, saved islands, contributions and verified transport clicks.

The central strategic move is simple: **surface the exceptional data already in the application, index far fewer pages initially, and make every indexed page the best structured answer on the web for that island.**
