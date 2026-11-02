# Analytics — installation and verification

Status checked through the signed-in browser on **2 November 2026**.

## Current state

The existing Find My Island Tag Manager container is **GTM-M2T6LN5J**:
account `6355174033`, container `252364207`, default workspace `2`.
It had no tags at the initial inspection. The production homepage includes that
container, but an installed empty container does not establish Analytics
collection. Generated island, guide and trust pages previously lacked the loader.

The user explicitly approved the dedicated account with optional Google data
sharing off, then separately approved Google Analytics Terms of Service and
the associated Data Processing Terms. The UK terms were accepted and the
following resources were created on 2 November 2026:

| Resource | Actual value |
|----------|--------------|
| Analytics account | **Find My Island**, `414499788` |
| GA4 property | **Find My Island**, `562073794` |
| Web stream | **Find My Island website**, `16258560202` |
| Stream address | `https://www.findmyisland.com` |
| Measurement ID | **`G-GGXR2KHHCZ`** |
| Reporting settings | UK Time, daylight-saving aware; GBP |
| Business settings | Travel; Small (1–10); traffic and engagement goals |

Enhanced Measurement, Google Signals and user-provided data collection are
**off**. Advertising personalisation is disabled in all **307** listed regions,
verified in the property settings. Optional account data sharing is off.

**Rollout is in progress.** The site integration remains local and unpublished;
no site deployment or Tag Manager publication has occurred for this setup.
Live receipt of visits and events in the new property is **unverified**. Saved
account settings and tag drafts are preparation, not proof of collection.

Saved draft variables (all Data Layer Variable version 2):

| Variable | Data layer key | GTM variable ID |
|----------|----------------|-----------------|
| DLV - FMI Page Location | `page_location` | `3` |
| DLV - FMI Page Referrer | `page_referrer` | `4` |
| DLV - FMI Island ID | `island_id` | `5` |
| DLV - FMI Category | `category` | `6` |
| DLV - FMI Outbound Host | `outbound_host` | `7` |

These drafts are in the existing default workspace. The unpublished custom
event trigger **FMI - Allowed Analytics Events** (trigger ID `8`) matches only
`^(page_view|map_open|island_view|island_save|interest_select|broker_click)$`
with regex matching enabled.

The saved, unpublished base tag **FMI - Google tag** (tag ID `9`) is a Google Tag
for `G-GGXR2KHHCZ`, triggered on **Initialization — All Pages**. Its settings are
`send_page_view=false`, `allow_google_signals=false`,
`allow_ad_personalization_signals=false` and `ads_data_redaction=true`.
`page_location` and `page_referrer` use the sanitised Data Layer Variables above;
the tag additionally requires `analytics_storage` consent.

The saved, unpublished GA4 event-forwarder **FMI - Analytics events** (tag ID
`10`) uses measurement ID `G-GGXR2KHHCZ` and event name `{{Event}}`. It maps
exactly `page_location`, `page_referrer`, `island_id`, `category` and
`outbound_host` to the five Data Layer Variables above. It requires
`analytics_storage` consent and uses only the anchored six-event allowlist
trigger `8`. The workspace has **8 unpublished changes**, including exactly
**2 tags**. Nothing in this workspace has been published.

Browser proof images are retained locally under `docs/reports/analytics-2026-11-02/`; they are not included in the source release.

## Shared site integration

`analytics.js` and `analytics.css` load on the homepage and every generated
landing through `landing_head_assets()`. The immediate homepage GTM snippet and
the noscript iframe are replaced by one consent-gated loader. The assets and
both `app.js` references use version `analytics-20261102a`.

The visitor gets equal Accept analytics and Decline choices, with a persistent
Privacy settings button. No container, event queue or analytics request starts
before an affirmative choice. Earlier actions are discarded. Localhost and
other non-production hosts never load the container.

Withdrawal clears GA cookies and unloads already loaded tags. A denial is
saved locally, with removal of an old grant and a tab-level denial as fallbacks.
If all browser storage operations fail, navigation to the clean public path
with `?fmi_analytics=off` prevents an immediate restart. Storage events propagate
withdrawal to other tabs where shared storage works. No durable preference can
be promised when the browser refuses all storage. Mobile controls sit above
the atlas navigation.

The frozen ferry pages are currently redirect stubs. Removed the unconditional
GTM snippets from their dormant generator so future use cannot silently bypass
consent; no ferry content was regenerated or promoted.

The loader sends only these explicit interaction names:

| Event | Meaning | Optional public fields |
|-------|---------|------------------------|
| `page_view` | Initial page, island detail or return to atlas; consecutive identical canonical pages deduplicated | `island_id` |
| `map_open` | A generated landing's map link is activated | `island_id`, `category` |
| `island_view` | A known island detail successfully renders | `island_id` |
| `island_save` | A known island is added to favourites | `island_id` |
| `interest_select` | A published interest filter is selected | `category` |
| `broker_click` | A broker link for a known island is activated | `island_id`, `outbound_host` |

Every event also has sanitised `page_location` and `page_referrer`. Addresses
exclude all query strings and fragments. Only recognised public site paths
are retained; external referrers retain their origin alone. Unused interaction
fields are explicitly cleared, preventing stale data-layer values carrying
into later events. Ask questions, contribution text, names, email addresses,
precise visitor coordinates and API keys are never event fields.

Advertising storage, advertising user data and personalisation remain denied.
The loader sets `send_page_view: false`, `allow_google_signals: false` and
`allow_ad_personalization_signals: false`. These site-side defaults must also be
preserved in the container/property configuration. Do not publish additional
automatic tags that bypass this event contract.

## Remaining rollout work

Account creation, legal-terms acceptance and both tag drafts are complete. The
remaining work is:

1. Deploy the prepared analytics-only consent integration while the live
   container is empty. Verify production visitor choices and generated asset
   paths before publishing measurement tags.
2. Preview the container and inspect emitted requests before publication.
   Decline must produce no Google measurement requests; Accept must produce
   one initial page view with clean addresses. Confirm island opening, saving,
   interest selection and broker navigation without text leakage or duplicates.
   Confirm initialisation order, `analytics_storage` requirements, sanitised
   fields and the saved property privacy settings.
3. Publish the verified container configuration after the production consent
   controls and Preview checks pass.
4. Confirm clean events reach the intended property in the Analytics
   realtime/debug report. A saved configuration or tag detector alone is not
   proof that visits reach the intended property.

## Validation

Offline privacy and app-hook regressions run with:

```bash
node scripts/test_analytics_consent.mjs
node scripts/test_app_analytics.mjs
```

Check real browser layout on the homepage and a generated landing at desktop
and mobile sizes. Consent withdrawal must stop collection and remove the
Google Analytics cookies. Cross-tab withdrawal and browser-storage failures
must be covered before shipping. Check generated assets at nesting depths
0–3. Never send real private prompts or contribution details as test data.

**Local results, 2 November:** both analytics regression scripts pass, including
storage-failure withdrawal, other-tab denial/removal, diacritic island IDs,
private-field rejection and page-view deduplication. Desktop and 390px atlas controls were exercised;
Decline persisted after reload, settings reopened, and later Accept worked.
No Google script was loaded on localhost after Accept, as intended. An isolated
Eel Pie Island landing at depth 3 loaded both shared assets, displayed working
choices and had no horizontal overflow. These tests do not verify Google
receiving events; that requires deployment, Preview, publication and live checks.

Browser screenshots and account-creation evidence are retained in the local working records. Explicit terms approval and account creation have completed.
The analytics-only patch is prepared on `codex/analytics-consent` in the attached
isolated worktree. A release clone at
`/private/tmp/findmyisland-analytics-release` starts from latest `main`,
`3db265ee`; the source patch applied cleanly and its tests pass. It excludes
concurrent photo changes and the separate, unpublished SEO improvements in the
primary checkout. No deployment has occurred. Deploy the consent integration
while the live container is empty, verify visitor choices, then publish the
verified measurement tags.

Analytics will describe the visits of people who opt in. Search Console remains
the source for search impressions, clicks and Google AI feature reporting;
those measures are distinct from Analytics sessions and recorded interactions.
