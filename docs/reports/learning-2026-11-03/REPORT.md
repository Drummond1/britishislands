# Learning/discovery pilot — local verification, 3 November 2026

**Result:** 20-island pilot implemented and verified locally. No commit, push, production deployment or Supabase mutation. [Context, manifest and next priorities](../../LEARNING-DISCOVERY.md).

## Delivered

- Story-first hooks in default/search cards, featured cards and profile openings, using substantive cited stories outside the pilot where available.
- 20 original/adapted introductory profiles, 60 source-linked facts, 47 timeline entries and 60 explained onward links.
- Three eight-stop reading journeys covering all 20 profiles, shareable atlas URLs, eight-island map view and four static `/learn/` pages.
- Browser-local saved islands without email, recent exploration (12 IDs), Surprise and a weekly choice.
- Source-aware Ask payloads, direct authored pilot story/timeline answers, separate factual/background and photograph links, valid bounded JSON tool output.
- Unknown geographic labels no longer group unrelated islands. Detail-map generation tokens prevent duplicate/stale Leaflet initialisation during asynchronous profile refreshes.

## Automated checks

Full commands, outputs and geographic regression: [checks.json](checks.json).

| Check | Result |
|---|---|
| Syntax: `app.js`, `chat-agent.js`, `learning.js` | Pass |
| `node --experimental-default-type=module scripts/test_learning.mjs` | 11 checks pass; 20 profiles/60 facts/47 events/60 connections/3 journeys; unresolved Llanddwyn ID withheld |
| `node --experimental-default-type=module scripts/test_detail_map_lifecycle.mjs` | Repeated render, rapid island switch and profile close during projection setup pass |
| `node --experimental-default-type=module scripts/test_chat_agent.mjs` | Existing query/tool checks pass |
| `scripts/test_analytics_consent.mjs` and `scripts/test_app_analytics.mjs` | Existing consent, withdrawal, clean fields and app-hook checks pass; fixture adds inert learning dependencies |
| `python3 -m unittest discover -s scripts -p 'test_seo*.py'` | 21 tests pass, including four new learning tests |
| `python3 -m unittest discover -s scripts -p 'test_geo_prompt_benchmark.py'` | 16 tests pass |
| `git diff --check` | Pass |
| Canonical geographic checklist | 18/19 pass; existing Wallasea parent-water mismatch remains, also recorded before this session |
| Curated regression spine | All 27 IDs present; atlas remains 11,212 records |

## Isolated full generation

[static-generation.json](static-generation.json) records hashes and counts. The actual generator ran with source inputs read from the checkout and **all output paths redirected** to `/private/tmp/fmi-learning-static-20261103/`. Generated **11,212** canonical island pages and **11,212** legacy redirects, plus `/learn/` and three journeys. Every pilot profile contains its hook, story, source-check date, timeline and explained connections. All three journeys occur in the core sitemap; collections hub links `/learn/`. Hub assets use one parent directory and journey assets use two. Canonical islands, curated spine, compact index, interest index and galleries have identical before/after SHA-256 hashes.

`prepare_pages_artifact.py` was inspected: these new `.js`, `.css`, JSON and generated `/learn/` assets are copied by its normal tree traversal. No local `_site/` packaging was run over the shared checkout's unrelated untracked files. Existing CI generation builds the new pages at release time.

## Browser checks

Checked the app in the in-app browser on desktop and at **390 × 844**, and generated reading pages on desktop and phone. This is a focused functional/layout check, not a complete assistive-technology or cross-browser audit.

| Scenario | Observed result |
|---|---|
| Homepage, cards and profiles | Hook visible before bounded picture; source-linked facts/timeline/credits and three explained links present |
| Mobile journey URL/reload | Intro and first stops near the top; no horizontal page overflow |
| Journey → island → Back | Correct profile opens and returns to the same journey URL/list |
| Show journey on map | Explicit **8 islands shown on map**; mobile Map/Explore navigation works |
| All islands/home reset | Journey removed and normal browsing restored |
| Saved list | Previously saved Lundy survives reload and appears as the only saved result; no email modal; local-storage limitation visible |
| Continue / weekly / Surprise | Continue retains the last viewed island, weekly Lundy link works, Surprise opens substantive Anglesey profile |
| Ask: `Tell me about Lundy` / timeline | Authored coin story and dates appear with Wikipedia reading source; photograph credit separate |
| Ask: `What kind of rock is Lundy made from?` | Smart answer reads atlas record and shows **Island background read for this answer**; uncited museum/artwork references and internal result metadata omitted |
| Direct profile load with late learning refresh | Detail map builds cleanly after generation-token fix; no new `learning-4` map-init error observed; earlier console entries were from pre-fix versions |
| Static journey/profile/hub | Eight island/source links present; headings, facts, timeline and source credits readable without the interactive app |

## Evidence

- [Desktop home](01-home.jpg)
- [Desktop profile](02-profile.jpg)
- [Ask authored answer and separate photo credit](03-ask.jpg)
- [Phone home](04-phone-home.jpg)
- [Phone journey](05-phone-journey.jpg)
- [Phone profile](06-phone-profile.jpg)
- [Ask background-source label](07-ask-background.jpg)
- [Static phone journey](08-static-phone-journey.jpg)
- [Desktop journey and map](09-journey-map.jpg)

## Limits and handover

The pilot's initial content uses attributed Wikipedia summaries checked 2026-11-03, under CC BY-SA 4.0. This does not certify every legacy profile field or broader generated AI sentence. Model paragraph citations are requested but not guaranteed; background read is labelled honestly. Authoritative-source enrichment, the remaining 80 profiles, pronunciation/audio and broader Ask evaluation are queued.

The Ynys y Clochydd/Llanddwyn entity mismatch is recorded, withheld from the pilot and queued for canonical correction. Legacy access guarantees need a separate evidence review. No new images or canonical island fields were edited. Pre-existing SEO/analytics/photo work remains in the shared checkout; its release authority is separate. Do not stage/push the whole tree. Production verification remains pending for this learning implementation.
