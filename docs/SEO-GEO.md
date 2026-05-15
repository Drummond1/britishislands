# SEO and GEO for island profiles

This project is a **static SPA** (`index.html` + `app.js`). Deep links use
`/?island=<id>` (stable slug from `data/islands.json`).

## What runs in the browser (no visible UI change)

`seo-meta.js` (imported from `app.js`) updates the document head whenever an
island detail panel opens, and restores the homepage defaults when it closes:

- `<title>`, `meta name=description`
- `link rel=canonical` (uses `window.IOB_SITE_ORIGIN` when set, else `location.origin`)
- Open Graph (`og:*`) and Twitter Card tags
- JSON-LD `@type: Island` with `geo`, `addressCountry`, `sameAs` (Wikipedia /
  Wikidata), optional `containedInPlace` for lake/river parents, optional
  `population` via `additionalProperty`

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
| `sitemap.xml`, `robots.txt` | When `--site-origin` or env `IOB_SITE_ORIGIN` is set |

```bash
# Minimal check-in (no absolute URLs):
python3 scripts/generate_seo_artifacts.py

# Production (replace with your live origin):
IOB_SITE_ORIGIN=https://example.com python3 scripts/generate_seo_artifacts.py
```

**Sitemap size:** one URL per island plus the home page (~7k+ URLs). Within
search-engine sitemap limits; split later if the dataset grows massively.

### Optional thin landing pages

Thousands of tiny static files can help hosts that don’t execute JS for bots, or
for share URLs that resolve without query strings:

```bash
python3 scripts/generate_seo_artifacts.py \
  --site-origin https://example.com \
  --landing-dir profiles
```

Each `profiles/<id>.html` includes basic meta tags, `canonical` to
`/?island=<id>`, and an immediate redirect to the live atlas. **Do not commit**
that directory unless your repo is OK with ~7k new files; many teams generate
this only in CI before deploy.

## ETHICS

Descriptions and structured data come from the same `islands.json` fields as the
UI. Do not invent facts for SEO; follow `docs/ETHICS.md` and dataset provenance.

## Related

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — frontend data flow
- [`DATA-SCHEMA.md`](DATA-SCHEMA.md) — island field definitions
