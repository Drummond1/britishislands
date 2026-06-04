# Deployment — GitHub Pages (findmyisland.com)

How the live static site is built and what ships to production.

## Overview

| Item | Detail |
|------|--------|
| Host | GitHub Pages + custom domain `www.findmyisland.com` |
| Workflow | `.github/workflows/pages.yml` on every push to `main` |
| Artifact | `_site/` directory (not repo root) |
| Builder | `scripts/prepare_pages_artifact.py` |

## CI pipeline (order matters)

1. **Checkout** repo
2. **`prepare_crowd_config.py`** — optional `CROWD_FORM_EMAIL` secret → `data/crowd_suggest_config.json`
3. **`generate_seo_artifacts.py --landing-dir profiles`** — `sitemap.xml`, `robots.txt`, `llms.txt`, ~11k `profiles/<id>.html`
4. **`build_islands_index.py`** — `islands_index.json`, `islands_unnamed_index.json`, `data/shards/*.json`
5. **`prepare_pages_artifact.py`** — copies repo → `_site/`, force-includes gitignored outputs, **drops monolith**
6. **`upload-pages-artifact`** + **`deploy-pages`**

## What ships in `_site/`

| Included (forced if gitignored) | Excluded |
|----------------------------------|----------|
| `data/shards/` | `data/islands.json` (~27 MB monolith) |
| `data/terrain/` | `scripts/`, `docs/`, `.github/` |
| `profiles/` | `data/osm_raw.json`, caches, logs, `data/discovery/*.json` audits |
| `islands_index.json`, `islands_unnamed_index.json` | Most `*.py`, `*.md` |
| `app.js`, `index.html`, `styles.css`, ferries JSON, etc. | `data/mlx_lora/` |

Regenerate locally:

```bash
python3 scripts/build_islands_index.py
python3 scripts/prepare_pages_artifact.py
# Inspect _site/ — confirm no _site/data/islands.json
```

## Git push notes

- **Workflow file changes** (`.github/workflows/*.yml`) require git push with **`workflow` OAuth scope** or **SSH** remote.
- Recommended remote: `git@github.com:Drummond1/britishislands.git`
- After deploy (~60–90 s), verify:
  - `curl -sI https://www.findmyisland.com/data/islands_index.json` → 200, ~948 KB
  - `curl -sI https://www.findmyisland.com/data/shards/manifest.json` → 200
  - `curl -sI https://www.findmyisland.com/data/terrain/manifest.json` → 200

## GitHub Pages settings

**Settings → Pages → Build and deployment** should be **GitHub Actions** (not “Deploy from branch”). If both branch deploy and Actions run, stale blobs (e.g. old `islands.json`) can remain on the CDN.

## Local preview

```bash
python3 -m http.server 8765
# open http://localhost:8765
```

Use HTTP, not `file://`. After index edits, run `build_islands_index.py` first.

## Environment / secrets

| Secret / config | Purpose |
|-----------------|--------|
| `CROWD_FORM_EMAIL` (GitHub secret) | FormSubmit inbox for native crowd suggest |
| `window.OS_MAPS_API_KEY` / `localStorage.osMapsApiKey` | OS Outdoor / Leisure basemaps (client-side) |
| `.env.local` (gitignored) | Local OS key for dev — never commit |

## Related

- SEO landings: [`SEO-GEO.md`](SEO-GEO.md)
- Index build: [`FRONTEND-PERFORMANCE.md`](FRONTEND-PERFORMANCE.md)
- Property weekly workflow: [`GITHUB-WORKFLOW-WEEKLY-PROPERTY.md`](GITHUB-WORKFLOW-WEEKLY-PROPERTY.md) — separate from Pages deploy
