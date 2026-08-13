# SEO and GEO for island profiles

This project is a **static SPA** (`index.html` + `app.js`). **Visible atlas URLs**
(and share links) use the nation + name-slug path. Legacy `/?island=<id>` still
opens an island, then the address bar is rewritten to the name path.

```
/islands/{nation}/{slug}/
```

Examples:

- `/islands/scotland/isle-of-skye/`
- `/islands/ireland/achill-island/`
- `/islands/northern-ireland/rathlin/`

Nation hubs (where “map” intent belongs): `/islands/ireland/`, `/islands/scotland/`, …

Do **not** stuff keywords like `map` into per-island slugs. Put map intent in
hub titles and page `<title>` templates instead.

## URL rules (`scripts/seo_paths.py`)

| Piece | Rule |
|-------|------|
| Nation segment | From `nation`: `scotland`, `ireland`, `england`, `wales`, `northern-ireland`, `crown-dependencies`, `isle-of-man` |
| Slug | ASCII-folded place name; curated human `id` kept when already a clean slug; collisions get parent water / archipelago / id suffix |
| Unnamed | Slug falls back to stable `id` (often `osm-…`) |
| Internal `id` | **Never** regenerated — still used for data joins and legacy `?island=` |
| Legacy | `/profiles/<id>.html` — **indexable** full landing (JSON-LD + OG); canonical points at `/islands/…` |

`build_islands_index.py` stamps `seoPath` on shards and compact index key `sp`.
Lookup file: `data/seo_path_by_id.json` (also written by `generate_seo_artifacts.py`).
The atlas SPA uses `<base href="/">` so `history.replaceState` to `/islands/…`
does not break `data/` fetches.

## What runs in the browser (no visible UI change)

`seo-meta.js` (imported from `app.js`) updates the document head whenever an
island detail panel opens, and restores the homepage defaults when it closes:

- `<title>` — `{name}, {nation} — map & profile | Find My Island`
- `meta name=description`
- `link rel=canonical` → `seoPath` when present
- Open Graph (`og:*`) and Twitter Card tags
- JSON-LD `@type: Landform` with `geo`, `addressCountry`, `sameAs` (Wikipedia /
  Wikidata), optional `containedInPlace` for lake/river parents, optional
  `population` via `additionalProperty`, plus `identifier` for OSM/Wikidata

Optional one-liner before `app.js` in `index.html`:

```html
<script>window.IOB_SITE_ORIGIN = "https://YOUR-PRODUCTION-HOST";</script>
```

Use this when the public URL differs from `location.origin` (reverse proxy,
alternate CDN hostname).

## Crawler / generative (GEO) artifacts

`scripts/generate_seo_artifacts.py` builds deploy-time files:

| Output | When |
|--------|------|
| `llms.txt` | Always — short briefing + URL patterns for AI crawlers |
| `sitemap.xml` sitemap index + segmented sitemap files | When `--site-origin` or env `IOB_SITE_ORIGIN` is set |
| `robots.txt` | When `--site-origin` or env `IOB_SITE_ORIGIN` is set |
| `islands/` | Nation hubs + `/islands/{nation}/{slug}/index.html` |
| `collections/` | Archipelago and water-body hubs (Inner/Outer Hebrides, Orkney, Shetland, etc.) |
| Trust pages (`/about/`, `/methodology/`, `/editorial-policy/`, `/corrections/`, `/sources-licensing/`, `/contact/`, `/dataset/`) | Generated as crawlable static pages |
| `profiles/<id>.html` | With `--landing-dir profiles` — indexable aliases (canonical `/islands/…`) |
| `data/seo_path_by_id.json` | id → public path map |
| `index.html` crawl links | Patched between `IOB_CRAWL_LINKS_*` markers |

```bash
# Production (matches GitHub Pages workflow):
IOB_SITE_ORIGIN=https://www.findmyisland.com python3 scripts/generate_seo_artifacts.py \
  --landing-dir profiles
python3 scripts/build_islands_index.py   # stamps seoPath onto shards
```

**Sitemap model:** `sitemap.xml` indexes:

- `sitemap-core.xml` (home, nation hubs, trust pages, collections root)
- `sitemap-islands-editorial.xml` (curated + featured)
- `sitemap-islands.xml` (**named islands with a description only** — unnamed / thin atlas records stay shareable on `/islands/…` but are omitted so Google does not spend crawl budget on them)
- `sitemap-ferries-verified.xml`
- `sitemap-collections.xml`

Legacy `/profiles/` URLs are **not** listed in the sitemap (canonical is `/islands/…`). They are still **indexable** landings so crawlers and GEO systems that already know the old URL get full content instead of a `noindex` stub.

**301 redirects:** GitHub Pages cannot emit HTTP 301s. After each generate, `data/legacy_redirects.csv` lists `/profiles/<id>.html` and `/?island=<id>` → `/islands/{nation}/{slug}/` for sitemap-eligible islands (Cloudflare Bulk Redirects). Import that CSV on an edge layer when DNS allows; until then, canonical tags are the only consolidation signal.

## Google Search Console (connected 2026-07-26)

Property: `sc-domain:findmyisland.com`. Snapshot: `data/gsc_seo_snapshot.json`.

| Metric (28d to 2026-07-25) | Value |
|----------------------------|-------|
| Impressions | **1,614** |
| Clicks | **0** |
| Avg position | **77.4** |
| Sitemap | Submitted OK (0 errors) |

### What GSC showed

1. Google is indexing **`/?island=`** SPA URLs (e.g. Scilly **563** impressions) because
   old profile HTML used **instant meta-refresh** into the atlas — treated as a redirect.
2. New **`/islands/{nation}/{slug}/`** URLs were **unknown** until deploy.
3. Best early ranking surface: **`/ferries/calmac/`** (279 impressions, ~position 51).
4. Strong query clusters: Anglesey, Brownsea, Bute, CalMac/ferries, Scilly.

### Fixes applied from this data

- Remove meta-refresh from island landings (indexable HTML stays on `/islands/…`).
- SPA `?island=` views: `noindex,follow` + canonical → `seoPath`.
- Ferry landings: stop showing “OSM node …” titles; absolute canonicals; links to `seoPath`.
- Priority list of GSC islands in `data/gsc_seo_snapshot.json`.

### After each deploy

1. Confirm sitemap still submitted in GSC.
2. URL Inspection → Request indexing on `/islands/`, nation hubs, and top GSC islands
   (`scilly-st-marys`, `anglesey`, `bute`, `lewis-and-harris`, CalMac ferry page).
3. Re-pull GSC in ~2 weeks; expect `/?island=` impressions to fall as `/islands/` rises.

Live CTR / ranking diagnosis (2026-07-26 API pull): [`GSC-CTR-FINDINGS.md`](GSC-CTR-FINDINGS.md).

### Static homepage SEO

`index.html` ships canonical, Open Graph, Twitter Card, `WebSite` JSON-LD, and
`robots` index directives in plain HTML. Island panels still update head tags via
`seo-meta.js`.

### Profile landing pages

Each `/islands/{nation}/{slug}/` page has self-canonical URL, `Landform` JSON-LD,
OG tags, and a link to the interactive atlas. Legacy `/profiles/<id>.html` pages
are the same landing HTML with `index,follow` so search and GEO crawlers can
use them; their canonical still points at `/islands/…`. Generated on every Pages
deploy; `islands/` and `profiles/` are gitignored.

## Continuous SEO / GEO improvement loop

Orchestrator: `scripts/run_seo_geo_improvement.sh`.

Each cycle (safe to run repeatedly; single-writer lock
`data/.seo_geo_improvement.lock`):

1. **Audit** — `audit_seo_geo_coverage.py` scores named islands 0–100
   (description 40 · photo 30 · sameAs 15 · geo 10 · nation 5) and writes
   `data/seo_geo_priority_queue.json` + `data/seo_geo_coverage_report.json`.
2. **Rotate enrichment** (cycle % 4):
   - `descriptions` — Wikipedia lead extracts (description queue then SEO queue)
   - `photos` — high-confidence P18 / OSM tag images ordered by SEO queue (OG)
   - `featured` — rebuild notable strip + discovery topics + featured desc gaps
   - `artifacts` — featured refresh only
3. **Publish** — `build_islands_index.py` + `generate_seo_artifacts.py`
   (sitemap, robots, llms.txt, `/islands/` HTML, legacy profile redirects).
4. **Probe live** — GET `/`, `/sitemap.xml`, `/robots.txt`, `/llms.txt`,
   `/islands/`, nation hub, sample profile, legacy redirect →
   `data/seo_geo_live_probe.json`.

```bash
# One cycle
bash scripts/run_seo_geo_improvement.sh

# Recurring every hour
while true; do
  bash scripts/run_seo_geo_improvement.sh || true
  sleep 3600
done
```

Env knobs: `IOB_SITE_ORIGIN`, `SEO_GEO_DESC_LIMIT` (default 60),
`SEO_GEO_PHOTO_LIMIT` (default 80).

## Continuous strategy loop (preferred)

Primary autonomous runner for the 90-day strategy in
[`SEO-GEO-STRATEGY.md`](SEO-GEO-STRATEGY.md). **Does not stop after 8 hours** —
runs until a stop file, optional max cycles/hours, or process kill.

```bash
# Preferred: detach via screen (survives Cursor/agent shells)
bash scripts/arm_continuous_seo_geo.sh

# Or run directly in a long-lived terminal
nohup env SEO_GEO_CONTINUOUS_PUSH=1 SEO_GEO_SLEEP_SEC=2700 \
  bash scripts/run_continuous_seo_geo.sh --loop \
  >> logs/continuous-seo-geo.out 2>&1 &

# Stop cleanly
touch data/.continuous_seo_geo.stop
# or: screen -S iob-seo-geo -X quit
```

Phase rotation (5-cycle):

| Phase | Focus |
|-------|--------|
| descriptions | Wikipedia/multilang leads for entity/GEO answers |
| photos | OG images + named photo-gap harvest |
| featured-flagship | Featured/topics + flagship editorial audit + desc |
| authority-artifacts | Landings/hubs/trust/sitemaps + GEO benchmark stub + live probes |
| gsc-priority | GSC snapshot-driven enrichment when available |

**Policy:** improve coverage and landings; **do not noindex/deindex** Tier C
atlas pages (project override vs strategy §1). Lock:
`data/.continuous_seo_geo.lock`. State:
`data/.continuous_seo_geo_state.json`. History:
`data/seo_geo_continuous_history.jsonl`.

## Overnight autonomous loop (time-boxed)

Fixed window (default 8 h). Prefer the continuous loop above for ongoing work.
Set `SEO_GEO_USE_CONTINUOUS=1` to delegate overnight `--loop` to the continuous
runner with `SEO_GEO_MAX_HOURS=8`.

```bash
OVERNIGHT_HOURS=8 OVERNIGHT_SLEEP_SEC=2700 SEO_GEO_OVERNIGHT_PUSH=1 \
  bash scripts/run_overnight_seo_geo.sh --loop
```

Each cycle (~45 min): `run_seo_geo_improvement.sh` + multilang descriptions or
photo-gap harvest → rebuild index/`/islands/` → audit → **auto-push** when avg,
description, or photo counts rise. Lock: `data/.overnight_seo_geo.lock`. PID:
`data/.overnight_seo_geo.pid`. History: `data/seo_geo_overnight_history.jsonl`.
