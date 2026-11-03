# Search Console baseline and SEO implementation

Observed 2 November 2026 in the authenticated `sc-domain:findmyisland.com` property. Search performance is complete through 31 October; the indexing report was last updated 23 October. The raw CSV exports and a machine-readable summary are retained under [reports/gsc-2026-11-02](reports/gsc-2026-11-02/baseline.json). These figures supersede the July baseline for current prioritisation.

## Search visibility

| Metric | 1 August to 31 October | 4 to 31 October |
| --- | ---: | ---: |
| Web clicks | 0 | 0 |
| Web impressions | 2,272 | 192 |
| CTR | 0% | 0% |
| Average position displayed in Search Console | 75.6 | 66.8 |

The previous equal-length period, 6 September to 3 October, had 491 impressions and no clicks. The most recent period therefore has 60.9% fewer impressions. This is an observed change, not evidence that a particular release caused it. Seasonality, query mix and Google's indexing decisions can all affect the comparison. Rounded daily position values in the exports produce approximate aggregate positions; use the displayed report for the official aggregate.

Most pages have little visibility near the first page of results. Improving their usefulness and discovery remains a stronger general priority than rewriting snippets indiscriminately.

## Pages to prioritise

| Page | Last 28 day impressions | Average position | Action |
| --- | ---: | ---: | --- |
| Eel Pie Island canonical profile | 33 | 10.82 | First profile to improve and measure. Add the existing sourced music/history material, credits, relevant facts and useful internal links to its static HTML. |
| St Mary's in the Isles of Scilly canonical profile | 40 | 80.38 | Improve the map/profile answer and distinguish it from other places called St Mary's. |
| Bute canonical profile | 34 | 85.35 | Strengthen the canonical profile using existing sourced material. |
| Staffa canonical profile | 18 | 84.89 | Improve distinctive, source-backed content; do not promise transport detail from frozen ferry data. |
| Anglesey query view | 18 | 81.61 | Continue canonical consolidation towards the existing island URL; do not change slugs or issue blanket deindex directives. |
| St Kilda query view | 13 | 60.08 | Inspect Google's canonical choice before any URL handling change. |

These are small samples. Eel Pie Island is the clearest current signal, not a statistically established winner. The property guide and new interest guides have not yet demonstrated significant performance in this export.

## AI search visibility

The separate Google Search generative AI report shows **30 impressions** from 4 to 31 October:

- Eel Pie Island canonical profile: **28**.
- CalMac ferry guide: **2**.

These are impressions within Google's AI features. They are not referral sessions, clicks, ChatGPT citations or an independent assistant benchmark. Do not add them to Web impressions as if the two reports represent disjoint audiences. The existing ferry freeze still governs promotion, even where a frozen guide has impressions.

Eel Pie Island URL Inspection reports:

- URL is on Google; page is indexed.
- Last crawl: **24 October 2026, 10:18:22**, as displayed by Search Console.
- Googlebot smartphone; successful fetch; crawling and indexing allowed.
- User-declared canonical is the inspected canonical profile; Google-selected canonical is “Inspected URL”.
- The URL-level sitemap section says “Temporary processing error”. This does not invalidate the successful fetch or the separately successful sitemap report.

No indexing request, validation request, removal or Search Console setting was submitted in this session.

## Indexing and sitemaps

The indexing report shows **32 indexed** and **1,728 not indexed** pages as of its 23 October update:

| Reason | Pages |
| --- | ---: |
| Discovered, currently not indexed | 1,643 |
| Crawled, currently not indexed | 66 |
| Alternative page with proper canonical | 11 |
| Page with redirect | 6 |
| Excluded by noindex | 1 |
| Not found, 404 | 1 |

The discovered/crawled categories dominate. Their presence does not establish a crawl block or technical failure. Alternative canonicals, redirects and an intentional error page can be expected states; do not attempt to make every exclusion disappear.

The submitted sitemap index shows **Success**, last read **29 October 2026**, with **1,683 discovered pages**. It does not need duplicate submission. Core Web Vitals has insufficient field data in the overview; no passing score is inferred.

## Straightforward implementation

The work accompanying this report preserves island records, URLs, atlas indexability and existing crawler permissions. It improves the generators and their validation:

- Rebuilds no longer claim an editorial review or a page modification date. Optional sitemap dates are omitted until trustworthy per-page edit dates are recorded.
- The ferry sitemap and core sitemap respect the existing ferry promotion freeze.
- Canonical profiles expose existing population years, source attribution, image credit/licence and cited interest summaries. Unrecorded years remain explicit; no new facts or classifications are inferred.
- Profile JSON-LD has stable entity and page IDs, breadcrumbs, safe embedded JSON and valid coordinates. Alternate map links are escaped once.
- Guide HTML contains every included record, with expandable sections, honest source-link counts, complete structured lists and questions that match the recorded evidence.
- Public trust pages contain working links to policy, field definitions and corrections.
- The benchmark runner distinguishes measured, failed and unrun answers, uses the correct denominators and preserves archives. The continuous loop no longer overwrites measured results with unrun templates.

Implementation and preview validation are local. Production still requires a subsequent deployment. The generator changes apply to all profiles, but they do not mean every island's facts have been editorially reviewed.

## Remaining work requiring evidence or a product decision

- Correct Fair Isle's stale observatory accommodation sentence through the governed data-update process, with a dated primary source.
- Review Pennsylvania Castle: its stored description says Gothic Revival mansion while the castle collection excludes country houses. Do not silently redefine the collection to accommodate the record.
- Nine property records lack broker URLs. Verify their sources before treating them as cited listings or current sale opportunities.
- Verify current production and property-sale scope before creating active-whisky or whole-island counts.
- Complete a real cross-product assistant benchmark. The historical unscored template remains unmeasured.
- Keep hosting/DNS redirects, new analytics integrations, outreach and policy changes as separately scoped actions.
