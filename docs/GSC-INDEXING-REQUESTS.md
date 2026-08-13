# GSC indexing requests — post `/islands/` deploy

**Date:** 2026-07-30  
**Property:** `sc-domain:findmyisland.com`  
**Machine list:** `data/gsc_index_request_urls.json` (36 URLs)

## Why

Google was ranking SPA `/?island=` URLs. Canonical nation+slug landings are now
live (HTTP 200). Requesting indexing on hubs and high-impression islands is the
fastest way to shift crawl attention.

## Status (this session)

- [x] Confirmed live HTTP 200 for nation hubs + priority island landings
- [x] Warm-crawled all 36 priority URLs with bot UA
- [x] Built `data/gsc_index_request_urls.json`
- [ ] Search Console MCP unavailable this session (server discovery error) —
      **manual Request indexing still required**
- [ ] Sitemap ping endpoints returned non-success (Google 404 / Bing 400);
      rely on GSC sitemap + URL Inspection instead

## Manual steps (highest impact first)

1. **Deploy** this branch so the smaller sitemap and richer landings go live.
2. Open [Google Search Console](https://search.google.com/search-console) →
   URL Inspection.
3. Request indexing in this order:

### Hubs (do first)

- `https://www.findmyisland.com/islands/scotland/`
- `https://www.findmyisland.com/islands/england/`
- `https://www.findmyisland.com/islands/wales/`
- `https://www.findmyisland.com/islands/ireland/`
- `https://www.findmyisland.com/collections/`
- `https://www.findmyisland.com/collections/flagship-islands/`
- `https://www.findmyisland.com/sitemap.xml`

### Top GSC islands (winnable map intent)

- `https://www.findmyisland.com/islands/england/scilly-st-marys/`
- `https://www.findmyisland.com/islands/scotland/bute/`
- `https://www.findmyisland.com/islands/scotland/staffa/`
- `https://www.findmyisland.com/islands/wales/anglesey/`
- `https://www.findmyisland.com/islands/scotland/lewis-and-harris/`
- `https://www.findmyisland.com/islands/england/lundy/`
- `https://www.findmyisland.com/islands/scotland/st-kilda/`
- `https://www.findmyisland.com/islands/england/brownsea/`

### Next wave

- Eel Pie, Inchcailloch, Isle of Wight, Iona, Rathlin, Arran, Mull,
  Lindisfarne, Isle of Man, Mainland Orkney, Fair Isle, Isle of Dogs
- Ferry hubs: `/ferries/`, `/ferries/calmac/`, `/ferries/scottish/`

3. Re-check URL Inspection in 3–7 days for “Indexed” vs “Discovered / crawled”.
4. Re-run CTR snapshot when position ≤20 starts to appear.

## 301 redirects (optional edge)

GitHub Pages cannot 301. `data/legacy_redirects.csv` is a Cloudflare Bulk Redirect
list (`/profiles/<id>.html` and `/?island=<id>` → canonical `/islands/…`) for
named islands with descriptions. Import it only after pointing DNS through
Cloudflare (or another edge that supports bulk 301s). Until then, rely on
canonical tags + Request indexing.

## Notes

Quota for “Request indexing” is limited — prioritize hubs + the eight winnable
islands above before the long tail. The sitemap now omits unnamed/thin atlas
records so Google spends crawl budget on pages that can rank.
