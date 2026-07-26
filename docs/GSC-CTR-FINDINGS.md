# GSC CTR findings — findmyisland.com

**Date:** 2026-07-26  
**Property:** `sc-domain:findmyisland.com`  
**Period:** 2026-04-26 → 2026-07-25 (≈ last 3 months)  
**Source:** Search Console API via MCP (`gsc_performance_overview`, `gsc_query`, `gsc_inspect_url`, `gsc_sitemaps`)

## Overview

| Metric | Value |
|--------|-------|
| Clicks | **0** |
| Impressions | **1,839** |
| CTR | **0%** |
| Average position | **76.5** |

**Verdict:** Zero clicks are expected. Almost all visibility is deep in results (page 7–8). Sitemap is healthy (0 errors). Ranking, not snippet CTR, is the bottleneck.

## Position ≤10 / ≤20 filter

| Filter | Queries | Total impressions |
|--------|---------|-------------------|
| Position ≤10 | **1** | 1 |
| Position ≤20 | **9** | 9 |

Nearly **no page-1 / page-2 presence**. The ≤20 set is one-impression noise (e.g. `benbecula ferry` pos 11, `calmac ferry map` pos 20, `isle of lundy` pos 19). **Title/snippet CTR work will not move the 3-month aggregate** until more queries crack the top 20.

## Top queries by impressions (all 0 clicks)

| Imp | Pos | Query | Notes |
|-----|-----|-------|--------|
| 36 | 80.9 | welsh for anglesey | Language intent — skip |
| 33 | 35.7 | calmac ferries | Booking intent — skip as primary |
| 32 | 95.5 | st mary's scilly map | **Winnable atlas** |
| 27 | 89.3 | isle of bute | **Winnable** |
| 24 | 88.9 | st mary's isles of scilly | **Winnable** |
| 23 | 60.7 | calmac timetables | Booking — skip |
| 22 | 90.0 | map of st mary's scilly isles | **Winnable** |
| 16 | 90.8 | staffa | **Winnable** |

607 distinct queries in period; ferry/CalMac variants dominate volume but are hard to win vs operators.

## Top pages by impressions

| Imp | Pos | Page |
|-----|-----|------|
| 565 | 88.0 | `/?island=scilly-st-marys` |
| 290 | 50.6 | `/ferries/calmac/` |
| 132 | 78.8 | `/?island=anglesey` |
| 108 | 73.7 | `/ferries/scottish/` |
| 107 | 71.7 | `/ferries/shetland/` |
| 100 | 83.5 | `/?island=bute` |
| 91 | 67.8 | `/` (homepage) |
| 70 | 83.0 | `/?island=lewis-and-harris` |

Google is ranking **SPA query URLs** (`/?island=…`) more than `/profiles/…`. New `/islands/{nation}/{slug}/` paths are **not indexed yet**.

## URL Inspection

| URL | Status |
|-----|--------|
| `https://www.findmyisland.com/` | **Submitted and indexed** (crawled 2026-07-09) |
| `https://www.findmyisland.com/ferries/calmac/` | **Submitted and indexed** |
| `https://www.findmyisland.com/profiles/anglesey.html` | **Redirect** → `/?island=anglesey` |
| `https://www.findmyisland.com/islands/scotland/` | **Unknown to Google** (404 live — not deployed) |
| `https://www.findmyisland.com/islands/wales/anglesey/` | **Unknown to Google** (404 live — not deployed) |

Sitemap `https://www.findmyisland.com/sitemap.xml`: last downloaded 2026-07-26, **0 errors / 0 warnings**.

## Winnable query priorities (10–20)

Prioritise after `/islands/…` deploy + indexing. Do **not** chase CalMac booking or Welsh-dictionary head terms.

1. st mary's scilly map / isles of scilly st mary's variants  
2. isle of bute / bute island scotland  
3. staffa  
4. anglesey island map (not “welsh for anglesey”)  
5. lewis and harris / harris island map  
6. lundy island / where is lundy  
7. st kilda / hirta  
8. brownsea island  
9. eel pie island  
10. inchcailloch  
11. isle of wight (atlas/map, not ferry booking)  
12. british islands map / britain's islands  
13. islands of scotland map (nation hub)  
14. calmac ferry **map** / which islands CalMac serves (secondary to atlas)  
15. isle of man (profile, not Steam Packet booking)  
16. mainland orkney / orkney islands map  
17. rathlin island  
18. iona  
19. lindisfarne / holy island  
20. arran / mull (thin in current top-imp list — still curated spine)

## Next actions

1. **Deploy** nation+slug `/islands/…` + sitemap + ferry landings (QUEUE P0) — still blocked.
2. **Request indexing** on hubs + top GSC islands once live.
3. Strengthen **Scilly St Mary's**, **Bute**, **Staffa**, **Anglesey** content/titles for map intent.
4. Homepage brand: lead with **Find My Island** in title/OG (done in-repo when shipped).
5. Re-check position ≤20 in 2–4 weeks.

## Follow-up fixes (same day)

- Removed **meta-refresh** from island landings (was why Google canonicalised `/?island=`).
- SPA: `noindex,follow` when `?island=` is open and `seoPath` canonical exists.
- Ferry pages: no more “OSM node …” card titles; absolute canonicals; links to `seoPath`.
- Snapshot: `data/gsc_seo_snapshot.json`.
