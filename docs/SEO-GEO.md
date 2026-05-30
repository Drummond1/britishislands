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
| `profiles/<id>.html` | With `--landing-dir profiles` (Pages deploy; gitignored locally) |
| `index.html` crawl links | Patched between `IOB_CRAWL_LINKS_*` markers |

```bash
# Production (matches GitHub Pages workflow):
IOB_SITE_ORIGIN=https://www.findmyisland.com python3 scripts/generate_seo_artifacts.py \
  --landing-dir profiles
```

**Sitemap (2026-05-30):** homepage + 13 ferry guides + 7,041 static profile URLs
(`/profiles/<id>.html`). Curated islands get higher `priority`. Query-string
`/?island=` URLs are omitted when profile pages are generated.

### Google Search Console

1. Add property `https://www.findmyisland.com`
2. Verify via HTML tag: set `window.IOB_GOOGLE_SITE_VERIFICATION` in `config.local.js`
   (see `config.local.example.js`); `seo-head.js` injects the meta tag at load.
3. Submit sitemap: `https://www.findmyisland.com/sitemap.xml`
4. Use URL Inspection → Request indexing on `/` and a few `/profiles/*.html` pages

### Static homepage SEO

`index.html` ships canonical, Open Graph, Twitter Card, `WebSite` JSON-LD, and
`robots` index directives in plain HTML. Island panels still update head tags via
`seo-meta.js`.

### Profile landing pages

Each `profiles/<id>.html` has self-canonical URL, `Island` JSON-LD, OG tags, and a
link to the interactive atlas. Generated on every Pages deploy; not committed locally.

## ETHICS

Descriptions and structured data come from the same `islands.json` fields as the
UI. Do not invent facts for SEO; follow `docs/ETHICS.md` and dataset provenance.

## Related

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — frontend data flow
- [`DATA-SCHEMA.md`](DATA-SCHEMA.md) — island field definitions
