# STATE — live snapshot

> Update this file whenever counts, schema, or running processes change.
> Stamp the date at the top of each section so we can spot drift.
## Last updated

**2026-10-26 (shipped to main)** — More cited islands in the thinner interest filters. Film, art and music **139**, whisky **21**, for sale **48**, rare wildlife **33**, tidal islands **104**, castles **96**, books **32**, local traditions **30**, unusual news **50**. Stories **1,488**, **901** with an open-licence picture. Supabase was not reloaded. `islands.json` was not edited.

**2026-10-26 (shipped to main)** — Island profiles open with the island. Each collection is a closed row with a count; the first two cited pieces are inside it. The island’s own-language name sits under the title, and a repeated name in another language is not listed again. Counts unchanged. Supabase was not reloaded. `islands.json` was not edited.

**2026-10-26 (shipped to main)** — The expanded interest index is on `main` for GitHub Pages. Film, art and music **139**, whisky **20**, for sale **48**, rare wildlife **30**, tidal islands **104**, castles **94**, books **32**, local traditions **30**, unusual news **50**. Stories **1,475**, **891** with an open-licence picture. Supabase was not reloaded. `islands.json` was not edited.

**2026-10-26 (interest expansion published)** — Eight filters gained cited islands. Film, art and music **139**, whisky **20**, for sale **48**, rare wildlife **30**, tidal islands **104**, castles **94**, books **32**, local traditions **30**. Unusual news stays **50**. Stories **1,475**, **891** with an open-licence picture. Local index only. Supabase was not reloaded. `islands.json` was not edited.

**2026-10-26 (rare wildlife)** — The interest chip, profile heading, and collection guide now read Rare wildlife. The slug stays `unusual-wildlife`. Counts unchanged. Supabase was not reloaded. The unapplied migration `supabase/migrations/20261025170000_unusual_wildlife.sql` uses the new label.

**2026-10-26 (unusual news, local papers)** — Twenty-six more reports from local and regional papers. **50** islands, **54** cited stories, every one with an open-licence picture. Shetland Times, the Orcadian, Stornoway Gazette, the Press and Journal, the Mayo News, the Irish Examiner, the Irish News, Essex Live, Wales Online, Cornwall Live, North Wales Live, the Bournemouth Echo, and the Jersey Evening Post. Stories **1,271**, **734** with a picture. Other chips unchanged. Did not edit `islands.json`. Supabase was not reloaded.

**2026-10-26 (unusual news, continued)** — Ten more reports. **26** islands, **28** cited stories, every one with an open-licence picture. Added the whisky wreck off Eriskay, the beach runway on Barra, the St Kilda evacuation, the Westray Wife, the two-minute flight to Papa Westray, the Stronsay beast, the Vatersay raiders, the Ailsa Craig curling stones, Orwell in the Corryvreckan, and the Dursey cable car. Stories **1,245**, **708** with a picture. Other chips unchanged. Did not edit `islands.json`. Supabase was not reloaded.

**2026-10-26 (shipped to main)** — Photo frames, naming an unnamed island, and the collection guides are on `main` for GitHub Pages. Counts unchanged. Supabase migrations in the repo stay unapplied from this push.

**2026-10-26 (photo frames)** — Collection cards and the opening photographs use a 3:2 frame. A tall or square picture is shown whole. Counts unchanged.

**2026-10-26 (name an island)** — An unnamed island opens one form: what it is called, your name, your email, and an optional source. Saving writes the private log `island_name_log` and shows the name on the map, the list, and the profile. The email is not readable from the browser. `islands.json` is unchanged.

**2026-10-26 (interest expansion)** — Eight researchers are adding cited rows for the published interest filters. Each writes only its own candidate file under `data/interest/candidates/zz-expansion-*.json`, or, for sale, the broker registry. They are not publishing the index and they are not editing `islands.json`. Counts unchanged until that publish.

**2026-10-26 (homepage cover)** — The opening photograph carries its name, *somewhere* is chalk and *else.* is the only gold in the headline, and the map clusters stay ink until a pointer reaches them. A gold seam joins the column to the map. No new request. Counts unchanged. Shipped to main.

**2026-10-26 (unusual news)** — New interest chip. **16** islands, **18** cited stories, every one with an open-licence picture of the subject. Each note is an original summary, and the link goes to the report. Forvik's declaration, Sealand, Lundy's puffin coins, the names painted at Canna harbour, the Flannan keepers, Gruinard's anthrax closure and the 2022 fire, Swona's cattle and the trainers in the post, the Prince of the Saltees, Eigg's community purchase, the Mull night flight, Castaway on Taransay, forty days on Rockall, the Fair Isle observatory fire, the king of Piel, the graves on Deadman's Island, and Sark's last feudal election. Stories **1,235**, **698** with a picture. Film/art/music stays **111**, whisky **18**, for sale **42**, unusual wildlife **23**, tidal islands **66**, castles **89**, local traditions **23**. The books harvest stays unpublished. Did not edit `islands.json`. Supabase was not reloaded. Migration `supabase/migrations/20261026140000_unusual_news.sql` is written and not applied.

**2026-10-26 (homepage plate)** — The first screen is a printed chart: a gold north on the rose, a coastline drawn once under the headline, interest chips on two whole lines, a gold rule on a photograph and on a name, and registration marks with a gold ring on the map clusters. Nothing new is fetched. The rose stays still and the lamp stays a fixed pool. Counts unchanged. Shipped to main.

**2026-10-26 (veil timeout)** — A stalled first fetch of the island index no longer holds the loading veil. The preload uses the same credentials as the fetch, a fetch that has not finished after 3.5 seconds is retried, and the veil hides without waiting for animation frames. Opening cards, the rose, lamp, needle, chip rule, search glow, bearing, and one-off arrivals are unchanged. Counts unchanged. Shipped to main. A cold load of findmyisland.com hid the veil inside two seconds.

**2026-10-26 (five-second boot)** — The atlas was stuck on “Loading the atlas…” because the page script imported an export the live metadata file did not have. That export is published, the icon library no longer blocks the first script, and the opening cards start downloading with the island index. The rose, lamp, needle, chip rule, search glow, bearing, and one-off arrivals are unchanged. Counts unchanged. Shipped to main.

**2026-10-26 (still passage)** — The chart rose stays behind the headline and no longer turns. The lamp is a fixed warm pool there and no longer follows the cursor. The needle rests, without the soft shadow. The chip rule, the search glow, the bearing, and the one-off arrivals remain. Counts unchanged. Shipped to main.

**2026-10-26 (homepage passage)** — The atlas first screen is a chart-room instrument: a drifting rose whose needle follows the pointer, a lamp that tracks the cursor, a bearing that names St Kilda, Iona, Staffa, Lindisfarne, and Skellig Michael, and a gold rule that travels the interest chips. Counts unchanged. Shipped to main.

**2026-10-26 (SEO/GEO guides)** — Eight crawlable guides under `/collections/` (castles, whisky, tidal, for sale, wildlife, books, traditions, film/art/music), plus `llms.txt` and the collections sitemap. Counts on the pages omit the rows the 26 October fact-check found false. Atlas totals are unchanged. Not deployed. Search Console token is expired.

**2026-10-26 (local traditions)** — New interest chip. **23** islands, **35** cited customs, every one with a picture (**13** of the custom, **22** a photograph of the island when the article had no open photo). Each summary is the Wikipedia sentence that places the custom on that island. Up Helly Aa, the Kirkwall Ba, Hop-tu-Naa, Hunt the Wren, Tynwald Day, Yn Chruinnaght, the Papa Stour sword dance, Foula's Old Christmas, Fair Isle knitting, the South Ronaldsay Boys' Ploughing Match, the North Ronaldsay dyke, the King of Tory, Jersey's Battle of Flowers, black butter, Jersey wonders, and the Clameur de Haro, Guernsey's Viaer Marchi, bean jar, and gansey, the World Pilot Gig Championships, Easdale stone skimming, the Aran jumper, Harris Tweed, the guga hunt, the St Kilda parliament and mailboat, Fèis Ìle, Fèis Bharraigh, the Omey races, the Davaar cave painting, and Tigh an Truish. Stories **1,217**, **680** with a picture. Film/art/music stays **111**, whisky **18**, for sale **42**, unusual wildlife **23**, tidal islands **66**, castles **89**. The unfinished books harvest was not published. Shipped to main. Supabase was not reloaded. Migration `supabase/migrations/20261026071000_local_traditions.sql` is written and not applied.

**2026-10-26 (one filter at a time)** — The chip row is single-select. Order: All islands, Islands with Castles, Unusual wildlife, Whisky, then Film, art and music, For sale, Tidal islands, Remote. Whisky regions and Film / Artwork / Music chips are hidden until more of those islands have a picture. Counts unchanged. Local only.

**2026-10-26 (Islands with Castles)** — New interest chip. **89** islands, **113** cited castles, **80** with an open-licence castle photo (**58** islands have at least one). Sources: Wikidata, English Wikipedia, OpenStreetMap `historic=castle`, Canmore, the National Heritage List for England, Cadw, and the Archaeological Survey of Ireland. Great Britain and Ireland are excluded. Martello towers, brochs, and country houses are excluded. Stories **1,182**, **645** with a picture. Rebuilding the index also picked up candidate rows already on disk: film/art/music **111** islands and **916** rows (546 artworks, 297 music, 73 film). Whisky stays **18** / **57**, for sale **42**, unusual wildlife **23**, tidal islands **66**. Local index only. Supabase was not reloaded. Migration `supabase/migrations/20261026044000_island_castles.sql` is written and not applied.

**2026-10-26 (shipped to main)** — This push publishes the current interest index (film/art/music, whisky with subdivisions, for sale, unusual wildlife, tidal islands, island castles), the atlas UI, and Ask. Smart answers can search the atlas and read full records. `data/chat_corpus.json` is 3,073 rows. Island counts unchanged. Supabase migrations are in the repo and not applied remotely.

**2026-10-26 (Anglesey and Nun's Island)** — Two stills the source places on the island. Anglesey Môn distillery, near Pentraeth, is listed as a working Welsh whisky distillery in 2018. Nun's Island Distillery made Irish whiskey on the Galway river island until about 1908. Whisky is **18** islands and **57** rows: **30** working, **13** silent, **12** stories, **2** planned. Achill, Lambay, the Isle of Wight, Scilly, and Saxa Vord stay out. Stories **1,180**, **640** with a picture. Local index only. Supabase was not reloaded.

**2026-10-26 (Loch Shiel)** — The Thorne Island article places the 1894 wreck of the Loch Shiel, carrying Scotch whisky, on that Pembrokeshire islet. Whisky is now **16** islands and **55** rows: **29** working, **12** silent, **12** stories, **2** planned. The novel rows were already in. The 2016 film stays out: it was shot at Portsoy. Stories **988**, **507** with a picture. Local index only. Supabase was not reloaded.

**2026-10-26 (more whisky)** — Nine further cited rows, still **15** islands and now **54** rows: **29** working stills, **12** silent, **11** stories, **2** planned. New: Laggan Bay on Islay (Ukrainian Wikipedia, opened 2 April 2026, between Bowmore and Port Ellen), the closed 1837 Lagg still and Arran's illicit stills, Islay's illicit stills, the village of Bunnahabhain, Ledaig as the old name of the Mull still, illegal distillation at the Highland Park site in 1798, and the novel Whisky Galore on Eriskay and on Barra. Achill still left out. Stories **966**, **492** with a picture. Local index only. Supabase was not reloaded.

**2026-10-26 (two songbook pages)** — Wikisource’s *Book of Scottish Song* added Arran Maid and the Song of Death, an Isle of Skye tune also called Oran an Aoig. Film/art/music is **106** islands and **817** cited rows (**465** artworks, **292** music, **60** film). Stories **957**, **492** with a picture. The other harvests lost their connection before they wrote a file. Local index only. Supabase was not reloaded.

**2026-10-25 (Shetland engraving and a Raasay reel)** — Openverse returned mostly false name matches (a steamship called Jura, Rebel Yell, an engraver named van Hoy). One CC BY engraving of Shetland was kept. The Internet Archive added the public-domain reel Mrs McLeod of Raasay. Film/art/music is **106** islands and **815** cited rows (**465** artworks, **290** music, **60** film). Stories **955**, **492** with a picture. Whisky stays **15** islands / **45** rows. Local index only. Supabase was not reloaded.

**2026-10-25 (whisky subdivisions)** — The Whisky chip is no longer only working distilleries. **15** islands and **45** cited rows: **28** working stills, **11** silent Islay stills, **4** stories (Islay's protected region, Fèis Ìle, Whisky Galore! on Barra, SS Politician off Eriskay), and **2** planned stills (Portintruan on Islay, the Barra whisky still that is not in production yet). Subdivisions on the chip: Islay, Hebrides, Orkney, Other isles, Silent stills, Stories, Planned. Achill was left out: no Wikipedia sentence places that still on the island. Barra's gin distillery is filed under Planned, not as a working whisky still. Shetland's Lerwick Distillery and the Isle of Man's Manx Whiskey Company are in Other isles, each from a sentence that names the island. Film/art/music stays **104**, for sale **42**, unusual wildlife **23**, tidal islands **66**. Stories **953**, **491** with a picture. Local index only. Supabase was not reloaded. Migration `supabase/migrations/20261025200000_whisky_subdivisions.sql` is written and not applied.

**2026-10-25 (tidal islands)** — New interest chip, Tidal islands. **66** islands from the English Wikipedia article Tidal island, each with a short note on where the link goes and that it is exposed at low tide and covered at high tide. Eleven names on that page were left out (not in the atlas, a permanent causeway, Eilean Donan's footbridge, or St Martin's as the land White Island joins). The atlas subtype `tidal` (256 islands) was not used. No crossing times. Film/art/music stays **104**, whisky **12**, for sale **42**, unusual wildlife **23**. Stories **934**, **491** with a picture. Shipped to `main` for GitHub Pages. Supabase was not reloaded. Migration `supabase/migrations/20261025190000_tidal_islands.sql` is written and not applied.

**2026-10-25 (MusicBrainz songs and albums)** — MusicBrainz release groups and works added **121** cited rows after **59** mismatches were rejected (Lundy surnames, Cutty Sark, the Melbourne St Kilda joke, Valentia the game, baroque giga movements, and Lindisfarne compilation piles). Film/art/music is **104** islands and **813** cited rows (**464** artworks on **51** islands, **289** music on **63** islands, **60** film). Stories **868**, **491** with an open-licence picture. Whisky **12**, for sale **42**, unusual wildlife **23** islands / **30** species. Local index only. Supabase was not reloaded.

**2026-10-25 (unusual wildlife)** — New interest chip, Unusual wildlife. **30** cited species on **23** islands, **22** with an open-licence photo of the species. Paragraphs come from the source page and name the island. No colony coordinates, nest counts, or visit advice. Film/art/music stays **95** islands, whisky **12**, for sale **42**. Local index only. Supabase was not reloaded. Migration `supabase/migrations/20261025170000_unusual_wildlife.sql` is written and not applied.

**2026-10-25 (Yale, Wellcome, and Là Luain)** — Yale LUX and the Wellcome Collection added **78** artworks after 10 mismatches were rejected (portraits, specimen plates, a mainland castle, and a print of an island near Staffa). Wikidata added the Skye punk band Là Luain. Film/art/music is **95** islands and **692** cited rows (**464** artworks on **51** islands, **168** music, **60** film). Stories **718**, **459** with an open-licence picture. Whisky **12** / for sale **42**. Local index only. Supabase was not reloaded.

**2026-10-25 (Commons artworks)** — Wikimedia Commons categories added **172** paintings, prints, and named sculptures after **37** snapshot filenames, souvenir objects, and a fantasy stamp were rejected. Film/art/music was then **95** islands and **613** cited rows.

**2026-10-25 (museum art and Wikipedia bands)** — Met, Cleveland, and Art Institute of Chicago CC0 records added **19** artworks (two sitter portraits were rejected). English Wikipedia music categories added **16** bands and musicians, mostly from the Isle of Wight, including Wet Leg and Coach Party. Film/art/music was then **95** islands and **441** cited rows.

**2026-10-25 (Wikidata artworks)** — Wikidata landmark and depicts statements added **79** artworks after four mismatches were rejected. Film/art/music was then **94** islands and **406** cited rows.

**2026-10-25 (night-light atlas)** — Homepage shell is a dark passage with an amber mark; the map stays bright and full-bleed; island profiles stay paper. Figma frames in file `kgEdP0EphgKDLlpAwJLQn2`. Pushed to `main` for GitHub Pages.

**2026-10-25 (chart-room aesthetic, local)** — Atlas and reading pages move from sage-on-cool-paper to chalk, Atlantic ink, and one vermilion mark. Fraunces + Outfit. Map tiles keep their colour. Files: `atlas-redesign.css`, `editorial-profile.css`, `landing.css`, `index.html`, `about/index.html`. Not pushed.

**2026-10-25 (gallery artworks)** — National Gallery of Art (Washington) CC0 metadata and one National Gallery, London title added **12** artworks on islands already in the atlas (Wight, Man, Ailsa Craig, Bass Rock, Sheppey). Film/art/music is **85** islands and **327** cited rows (**116** artworks, **151** music, **60** film). Stories **353**, **178** with an open-licence picture. Whisky **12** / for sale **42**. Local index only. Supabase was not reloaded. V&A skipped (non-commercial API terms). Other artwork and music harvests are still running.

**2026-10-25 (simpler atlas, ferries paused)** — Ferry guides, the ferry filter, the crossing planner, and ferry cards are hidden. Island profiles lead with the story, a few plain facts, and wildlife or lighthouses when we have them. Sources, bedrock, and mapping notes are no longer on the profile. Schema and counts unchanged. Local only.


**2026-10-25 (interest categories, expanded)** — Overlay filters.
Supabase `interest_categories` + `interest_memberships` (project
`oqqfuddgclotoohekmop`). Static export `data/interest_index.json`.
Published: film/art/music **85** islands (**315** cited rows), whisky
distilleries **12** islands (**26** rows), for sale **42**. Draft and empty:
`uninhabited-stay`. The static index is local. Supabase still has the
previous **171** memberships until the new SQL is loaded. The first batch
(13 / 10 / 37) is what production still serves until this index is pushed.
Island profiles include a picture and a short summary for distilleries and
for film, art, and music. The Artwork chip and the Whisky distilleries chip
lead with that picture under the island name. Music and artwork now also come
from Wikidata and MusicBrainz, not only Wikipedia. Skill:
`.cursor/skills/interest-category-populate/SKILL.md`.

**2026-10-25 (editorial UI preview — LOCAL ONLY)** — Warm paper/evergreen discovery
column, framed map, simplified search/quick filters and updated profiles/mobile UI.
Changed `index.html`, `app.js`, `atlas-redesign.css`; added `editorial-profile.css`.
No commit, push or deploy. Data/schema/counts unchanged. See SESSION-LOG entry.

**2026-10-25 (calm atlas UI)** — Map-first desktop layout: floating list, quieter
header, photographic cards, shorter browse chips. Schema and counts unchanged.
Shipped to `main` for the Pages deploy.

**2026-08-16 (counsel follow-through)** — Per-island `data/details/{id}.json`
(**11,351**), history Back (`pushState`/`popstate`), browse list cap 24, mobile
Ask FAB hidden. Nation shards remain as fallback. Deploy needed for production.

**2026-08-16 (LLM counsel UX ship)** — Shipped counsel Day 1–5: honest access
labels, Filters Done, boot/shard error UI, deferred seo_path hydrate, ferry
token match, local Save, mobile bottom sheet, vendor Leaflet, Share/`map=1`
landing handoff, `404.html`, shard prefetch. Schema unchanged. Deploy needed
for production.

**2026-08-13 (GSC Request indexing)** — Submitted indexing for nation hubs
(`/islands/scotland|england|wales|ireland/`) plus Scilly St Mary's, Bute, Staffa,
and Anglesey. Hubs and Anglesey: **URL is unknown to Google**. Scilly, Bute, Staffa:
**Page is indexed** (requested recrawl). Cloudflare 301s still blocked: no CF zone
in front of GitHub Pages; API needs Global API Key + account email.

**2026-08-13 (SEO deploy live)** — Pushed `2720d940`; Pages deploy succeeded.
Live sitemap is **1,622** island URLs (120 editorial + 1,502 named-with-description).
`/profiles/anglesey.html` is `index,follow` with geology prose.

**2026-08-13 (SEO next actions)** — Sitemap now asks Google for **1,622** island
URLs (120 editorial + 1,502 named-with-description), omitting **9,758** unnamed/thin
records. Landing geology is prose (not a Python dict dump). Cloudflare-ready
`data/legacy_redirects.csv` (**3,244** rows) maps `/profiles/` and `/?island=` →
`/islands/…` for those eligible islands. GitHub Pages still cannot 301 until an
edge layer is added. Needs deploy + GSC Request indexing.

**2026-08-13 (indexable /profiles/ aliases)** — Stopped emitting `noindex` on
legacy `/profiles/<id>.html`. Those pages are now full landings (`index,follow`,
JSON-LD, OG) with canonical still `/islands/{nation}/{slug}/`, so search and GEO
crawlers that already know the old URLs get real content. SPA `?island=` stays
`noindex,follow`. Generator: `scripts/generate_seo_artifacts.py --landing-dir profiles`.

**2026-07-30 (GSC indexing + coverage pass)** — Cleared stale `.gsc_seo_improvement.lock` so continuous SEO loop could resume. Confirmed `/islands/…` hubs+priority landings **HTTP 200**. Built indexing pack `docs/GSC-INDEXING-REQUESTS.md` + `data/gsc_index_request_urls.json` (36 URLs). Coverage pass: **+2** multilang descriptions; photos flat **4,356**. Scores **avg 47.81→47.82**, both **18.8%→18.9%**, desc **1,621→1,623**. Regenerated `seo_path_by_id.json` (**11,380** paths) + sitemaps/landings. GSC MCP unhealthy — manual Request indexing required. Continuous loop still armed.


**2026-07-28 (atlas product redesign)** — Map-led discover UX: compact header,
intent chips, richer cards, filter drawer groups, visitor-first profile +
grouped ferries, contextual Ask, Search this area. Files: `index.html`,
`app.js`, `atlas-redesign.css`. Schema unchanged. Not yet pushed to Pages.

**2026-07-28 (visual polish)** — Richer night-sea atmosphere, glass topbar, branded mark pulse, elevated featured/list cards with hover motion, stronger search/Ask CTAs; landing hero/CTA polish. Deployed with UX navigate pass.

**2026-07-28 (UX navigate simplify)** — Clearer atlas chrome: Collections + Filter topbar; Browse/Start here/Show me chips; mobile Map/List/Ask; profile Share/Save + no Atlas badge; unnamed survey under More filters. Continuous SEO loop still armed.

**2026-07-28 (continuous SEO/GEO loop armed)** — Replaced time-boxed overnight with `scripts/run_continuous_seo_geo.sh --loop` (strategy-aligned 5-phase rotation; no deindex). Strategy doc in-repo: `docs/SEO-GEO-STRATEGY.md`. Stop via `data/.continuous_seo_geo.stop`.

**2026-07-28 (batch 2 CWV + GEO + flagship depth)** — Non-blocking homepage/landing fonts; landing hero `fetchpriority=high` + reserved aspect-ratio; Names/Geology sections + collection cross-links on island landings; richer collection hub blurbs; GEO prompt set expanded to **50** + `scripts/run_geo_prompt_benchmark.py`. Production deploy `9c8afb78` live (`/about/`, `/collections/`, sitemap index).

**2026-07-28 (SEO/GEO phase 1-3 foundations)** — Reworked SEO artifacts for people-first indexation without deindexing: JSON-LD `Landform` + identifiers; segmented sitemap index (`core`, `islands-editorial`, `islands`, `ferries-verified`, `collections`); trust pages (`/about/`, `/methodology/`, `/editorial-policy/`, `/corrections/`, `/sources-licensing/`, `/contact/`, `/dataset/`); new collection hubs (`/collections/*`) including `flagship-islands` (30 profiles); richer canonical island landing template (breadcrumbs, section blocks, sources, related links).

**2026-07-28 (overnight SEO/GEO done)** — Loop finished after **11** cycles (~8 h). Scores: avg **47.78→47.81**, desc **1,617→1,621**, photos **4,356** (flat). Auto-push on cycle 1 failed (commit `e6d8bf3a` still local, `main` ahead 1).

**2026-07-27 (visible name URLs)** — Atlas `history.replaceState` now shows `/islands/{nation}/{slug}/` on island open (not `?island=`). Index stubs carry `sp`; `<base href="/">` keeps fetches rooted. Index rebuilt 7,237+4,143 with `sp`.

**2026-07-27 (overnight SEO/GEO autonomous)** — Armed `scripts/run_overnight_seo_geo.sh --loop` (**8 h**, **45 min** cycles). Self-contained: rotates `run_seo_geo_improvement.sh` + multilang descriptions + photo-gap harvest; rebuilds `/islands/` artifacts; auto-pushes on score gains (`SEO_GEO_OVERNIGHT_PUSH=1`). Lock `data/.overnight_seo_geo.lock`. Replaces agent-wake hourly loop (PID 19423 stopped).

**2026-07-27 (SEO/GEO sitelink+multilang desc)** — Batch Wikidata sitelink
preflight (`wdsl:`) + gd/cy/ga/en Wikipedia lead extracts: **+45**
shortDescriptions after QA (57 raw − 12 wrong sitelink/hill/loch). Scores
**avg 47.5→47.75**, both% **18.3→18.7**, desc **1,566→1,611**, photo **4,356**.
Hourly loop PID **19423** still alive.

**2026-07-27 (discovery unlock)** — Agents found overnight +1 was a **verifier
bottleneck** (GeoNames needed Wikidata). Fixed `name_key`, refined gaps,
accepted OSM/GeoNames provenance, OpenSeaMap + Wikidata harvesters. Applied
**+187** then scrubbed **13** false positives → atlas **11,380 → 11,554 (+174)**.

**2026-07-27 (SEO/GEO continue)** — Hourly loop PID **19423** (`AGENT_LOOP_TICK_seo_geo`). Geograph **+2** photos (4,354→4,356); avg **47.5**. Nation hubs now include ferry cross-links + CollectionPage JSON-LD + 48 notable links. Desc Wikipedia mostly exhausted (no enwiki).

**2026-07-27 (SEO/GEO include-exhausted + photo gaps)** — Continuing SEO/GEO loop
after GSC-only saturation. Description `--include-exhausted` + photo-gap queue
(P18/osm-tags/wiki-embedded): **+0 desc / +0 photos** this pass; scores flat
**avg 47.49 / both 18.3%** (desc **1,566**, photo **4,354**). Live
`/islands/scotland/` **200**. Hourly `AGENT_LOOP_TICK_seo_geo` re-armed; state
`lastAction=descriptions+photos-gap` cycle **17**.


**2026-07-26 (overnight discovery+naming)** — Implemented N7–N10 + D5–D6;
first confirm pass named **140** islands (4310→4170 unnamed; mostly GeoNames
≤150 m). Seal haul-outs: **59** sites parsed, **16** gap candidates staged.
Overnight loop armed: `run_overnight_discovery_naming.sh --loop` (**8 h**,
45 min cycles; PID in Currently running). Lock
`data/.overnight_discovery_naming.lock`.

**2026-07-26 (UX simplify)** — Search-first atlas chrome; quieter sidebar;
profile jump nav + collapsed secondary facts; shared `landing.css` for ferry +
`/islands/` click-through pages. Regenerated landings. Local only until deploy.

**2026-07-26 (GSC-driven loop)** — `scripts/run_gsc_driven_seo.sh` + richer `/islands/` landings (key facts). Loop every **60 min**. Live `/islands/` still **404** until deploy.

**2026-07-26 (GSC CTR diagnosis)** — Live Search Console API: **0 clicks / 1,839
impressions / avg pos 76.5** (Apr–Jul). Position ≤20 ≈ **9** one-imp queries.
`/islands/…` unknown to Google (not deployed). Full write-up:
`docs/GSC-CTR-FINDINGS.md`. Homepage title → **Find My Island — Isles of Britain
atlas**; CalMac guide retitled toward map/islands-served intent.
**Follow-up this session:** removed profile meta-refresh (was feeding `/?island=`
indexation); SPA `noindex` on `?island=`; ferry “OSM node” titles cleaned;
`data/gsc_seo_snapshot.json`. **Deploy still required.**

**2026-07-26 (nation + name-slug URLs)** — Canonical public paths are now
`/islands/{nation}/{slug}/` (e.g. `/islands/ireland/achill-island/`). Nation hubs
at `/islands/scotland/` … `/islands/ireland/` etc. Legacy `/profiles/<id>.html`
become noindex redirects. `seoPath` stamped on shards; `data/seo_path_by_id.json`
map; titles `{name}, {nation} — map & profile | Find My Island`. Sitemap **11,401**
URLs. See `docs/SEO-GEO.md` + `scripts/seo_paths.py`.

**2026-07-26 (SEO/GEO continuous loop)** — Added `scripts/audit_seo_geo_coverage.py`
and `scripts/run_seo_geo_improvement.sh` (rotate photos/descriptions/featured;
rebuild index + sitemap/robots/llms.txt/profiles; live probe). Looser description
name-match + staging photo harvesters in photos phase. Through cycle **13**:
avg **48.14→48.26**, desc **1,552→1,566** (+14), photo **4,343→4,354** earlier then
stable **4,354**, both **18.7%**. Live probe allOk. Recurring every **60 min**
(PID armed).

**2026-06-12 (learner UX P1–P5)** — Learning-first UI pass: **With stories**
browse chip (`islandHasStory`), default **hide needs review**, sidebar reordered
(Notable → Explore topics → filters), profile hierarchy (key facts strip, sparse
lede, related islands, collapsed facts/provenance), chat learning starters.
Description queue `build_description_priority_queue.py` + Wikipedia pass **+16**
shortDescriptions (**1,552** named with prose, **~4,590** with photo or story).
Index rebuilt.

**2026-06-12 (staged verify + production merge)** — Full staged pass:
photos strict verify **17/49** accepted; merge **+0** new photos (12 already had images).
Names verify **0** proposals. Discovery `site_update --apply`: **274** field merges on
existing islands. GeoNames/Wikipedia gaps: **31** verified, **+28** new islands
(`apply_staged_discovery_gaps.py`). Atlas **11,351 → 11,379**; index rebuilt.

**2026-06-11 (discovery + naming N4–N6)** — New-island gap harvesters:
`discover_geonames_gaps.py` (**378** gap candidates after name dedupe), `discover_wikipedia_coord_lists.py`
(**10** candidates); orchestrator `run_priority_discovery_push.sh`. Naming N4–N6:
`name_unnamed_heritage.py`, `name_unnamed_ohsome.py` (OSM API history),
`name_unnamed_fusion.py`; wired into `run_priority_naming_push.sh`. GeoNames raw:
`data/raw/geonames_{GB,IE}.txt`.

**2026-06-11 (naming pipeline — 100 ideas scaffold)** — Registry
`docs/NAMING-SOURCES.md`; staging harvesters N1–N3:
`name_unnamed_os_open_names.py`, `name_unnamed_logainm_oil.py`,
`name_unnamed_osm_tags.py`; verify/merge via `verify_staged_names.py` +
`merge_staged_name_proposals.py`; orchestrator `run_priority_naming_push.sh`.
**4,310** unnamed islands unchanged (OSM-tags probe 0/300 — expected: no tags on
unnamed ways). Blocked on `OS_DATAHUB_API_KEY` (Open Names CSV) and
`LOGAINM_API_KEY` (OIL bulk).

**2026-06-11 (priority photo push P1–P5 + grid fix)** — Fixed OSGB grid refs in
`scripts/photo_geo_utils.py` (now uses `osgb` package; was single-letter bug →
wrong Geograph locations). Added P1–P5 harvesters + `run_priority_photo_push.sh`;
fixed `fetch_commons_meta()` calls in P2/P4/P5. First end-to-end push (limit 50):
**4,341 → 4,342** (+1 `geograph-native`, island `osm-way-985212914`). P2 hit WD
429; P3 skipped (no `FLICKR_API_KEY`); P4/P5 had commons-meta bug (fixed, not
re-run). Continuous loop now rotates **11** harvesters (P1–P5 + legacy six). Gap
to **6,000**: **1,658**.

**2026-06-11 (continuous improvement loop armed)** — New orchestrator
`scripts/run_continuous_improvement.sh`: **Phase 1** refresh missing enrichment
caches + `apply_enrichments.sh --yes --force`; **Phase 2** rotate staging
harvesters → strict verify → staged merge → cache adopt → v5 P18/OSM batches →
index rebuild. Recurring loop every **45 min** (lock:
`data/.continuous_improvement.lock`). Baseline before cycle 1: **4,341** named
with photo / 7,041; gap to **6,000**: **1,659**. Missing cache:
`cache_dobih.json` (hills Wikidata fetch attempted each cycle).

**2026-06-04 (90 min enrich poll + strict merge re-pass)** — Polled every **2 min**
until no `Python scripts/enrich_images_*` (~**30 min**, poll **16/45**,
`ALL_IDLE` 08:17). Re-ran `verify_staged_photos_strict.py` on all
`data/staging/adoptions/*.json`: **34 / 66** passed (**51.5%** strict gate; min
**90** dual-signal). By file: **inaturalist 18/18**, **commons-depicts-q 6/6**,
**wikidata-depicts 5/5**, **commons-deep 2/2**, **commons-archipelago 3/9**;
**0** from ogl-tourism (**21**), openverse (**3**), kartaview/panoramax.
`merge_staged_photo_adoptions.py` from `adoptions-verified/` → **0** new (**29**
deduped; all already had `images[]`; prior pass **+9** at 07:17). Index rebuilt.
**4,341** named with photo / 7,041. Gap to **6,000**: **1,659**. Reports:
`data/staged_verify_strict_report.json`, `data/staged_merge_report.json`.
Did **not** run `verify_island_images.py --fix-suspect`.

**2026-06-04 (verified staged merge — first post-harvest soak)** — Polled staging **60 min**
(2 min) while harvesters finished (**66** raw rows / **26** files). Re-ran
`verify_staged_photos_strict.py` (dual-signal, min **90**) → **34** accepted in
`data/staging/adoptions-verified/`. Single-writer merge from verified dir only:
**+9** lead photos (**6** `commons-depicts-q`, **3** `commons-archipelago-category`;
**20** skipped — already had `images[]`). Backup
`data/islands.json.before-staged-merge-20260604T071708Z.bak`; index rebuilt.
**4,341** named with photo / 7,041. Gap to **6,000**: **1,659**.
`verify_island_images.py`: **≥90** 1,136 / **80–89** 1,485 / **<80** 1,720.
Report: `data/staged_merge_report.json`, `data/staged_verify_strict_report.json`.

**2026-06-04 (KartaView + GBIF staging)** —
`scripts/enrich_images_kartaview.py` → `data/staging/adoptions/kartaview.json`
(CC-BY-SA OpenStreetCam; `areaKm2` < 0.3; 200 m centroid verify).
`scripts/enrich_images_gbif.py` → `data/staging/adoptions/gbif.json` (GBIF
iNaturalist research-grade dataset; CC StillImage; 300 m verify). Each
`--named-only --limit 200`: **kartaview 1** staged (**0.5%**); **gbif 0** staged.
Caches: `cache_kartaview.json`, `cache_gbif.json`. Reports:
`image_enrichment_kartaview_report.json`, `image_enrichment_gbif_report.json`.
**No** `islands.json` write.

**2026-06-04 (OSM bulk tag staging)** —
`scripts/enrich_images_osm_bulk.py` → `data/staging/adoptions/osm-bulk.json`
(tiled bbox Overpass + v5 `try_osm_tags`; id fallback for keys without photo
tags). Full named photoless pool with OSM id: **2,235** keys; bbox **58/63**
tiles; **0 staged** (OSM photo tags on remaining pool are non-adoptable or
already covered). Caches: `cache_osm_tags_bulk.json`, `cache_osm_tags_v5.json`.
Report: `data/image_enrichment_osm_bulk_report.json`. **No** `islands.json` write.

**2026-06-04 (Commons depicts-Q P180/P921 staging)** —
`scripts/enrich_images_commons_depicts_q.py` →
`data/staging/adoptions/commons-depicts-q.json` (Commons search
`haswbstatement:P180|P921`, WDQS reverse links, optional Commons WCQS; MediaInfo
verify). `--named-only --limit 600` (**~18 min**): **6 staged** / 600 (**1%**);
**594** no candidates; all **P180** (no P921-only). Cache:
`data/cache_commons_depicts_q.json`. Report:
`data/image_enrichment_commons_depicts_q_report.json`. **No** `islands.json` write.

**2026-06-04 (Wikidata depicts / P180 staging)** —
`scripts/enrich_images_wikidata_depicts.py` →
`data/staging/adoptions/wikidata-depicts.json` (Commons
`haswbstatement:P180=<Q-ID>` + MediaInfo `statements.P180` verify; batched WDQS
prefetch). `--named-only --limit 500` (**~17 min**, `--delay 2.5`): **5 staged**
/ 500 attempted (**1%**); **495** no Commons depicts index hit. Staged: Furze
Island, Carbery Island, Calf Island East/Middle/West (Dunmanus / Illaunkearagh
files). Cache: `data/cache_wikidata_depicts.json`. Report:
`data/image_enrichment_wikidata_depicts_report.json`. Commons WCQS requires OAuth
(use `--no-sparql` for unattended runs). **No** `islands.json` write.

**2026-06-04 (Panoramax + OpenAerialMap geo CC)** —
`enrich_images_panoramax.py` / `enrich_images_openaerialmap.py` each
`--named-only --limit 150` (tiny islands, `areaKm2` < 0.3). **Panoramax: 1**
staged → `data/staging/adoptions/panoramax.json` (CC-BY-SA, 250 m gate).
**OpenAerialMap: 0** staged → `openaerialmap.json` (HTTPS meta bbox; sparse UAV).
Reports `data/image_enrichment_{panoramax,openaerialmap}_report.json`. **No**
`islands.json` write.

**2026-06-04 (heritage OGL photo staging)** —
`scripts/enrich_images_heritage_ogl.py` → `data/staging/adoptions/heritage-ogl.json`.
`--named-only --limit 300`: **0** staged (strict name+place+OGL image URL gate).
**APIs working**: NHLE ArcGIS, HES Canmore_Points (`inspire.hes.scot`), Cadw WFS.
**Blocked** (report): legacy Canmore WAF, trove.scot 403, no NHLE attachments,
Heritage Gateway / Coflein / HE Archive / Cadw report photos. Report:
`data/image_enrichment_heritage_ogl_report.json`; cache `data/cache_heritage_ogl.json`.

**2026-06-04 (Commons archipelago sweep)** —
`enrich_images_commons_archipelago_sweep.py`: **13,309** files indexed (**374**
categories, **36** roots); **9** staged → `commons-archipelago.json` (dual-signal).
Cache `data/cache_commons_archipelago_index.json`; report
`data/image_enrichment_commons_archipelago_report.json`. **No** `islands.json` write.

**2026-06-04 (Europeana geo + BL Flickr deep + SCRAN probe)** —
New staging scripts: `enrich_images_europeana_geo.py` → `europeana-geo.json`
(needs `EUROPEANA_API_KEY`), `enrich_images_bl_flickr_deep.py` → `bl-flickr-deep.json`
(needs `FLICKR_API_KEY`, licence 7 / PD only), `enrich_images_scran.py` → `scran.json`
(probe-only skip — no open API). Shared dual-signal gate in `photo_staging_dual.py`.
Smoke without keys: **0** staged each. Reports:
`data/image_enrichment_{europeana_geo,bl_flickr_deep,scran}_report.json`.

**2026-06-04 (unconventional photo harvesters — all-lang wiki, PCW, Dúchas)** —
Three new staging scripts run; **0** adoptions each. **wikipedia-alllangs**
`--limit 400`: **0** staged (title-matched leads were SVG locator maps on small
wikis; 429 during pageimage prefetch). **pcw** `--limit 100`: **52** Wales
photoless tried, **0** staged (Creative Archive NC / discover mismatch).
**duchas**: no `DUCHAS_API_KEY`; API exists but **CC BY-NC** blocks project merge.
Files: `data/staging/adoptions/{wikipedia-alllangs,pcw,duchas}.json`, reports
`data/image_enrichment_{wikipedia_alllangs,peoples_collection_wales,duchas}_report.json`.
Caches: `cache_wikipedia_alllangs_*.json`, `cache_peoples_collection_wales.json`.

**2026-06-04 (verified staged merge audit)** — Audited **20** rows in
`data/staging/adoptions-verified/` (**inaturalist 18**, **commons-deep 2**): all **20**
already had `images[]` in `islands.json` (prior merge #2 / harvest). Dry-run
`merge_staged_photo_adoptions.py` → **0** new, **20** skipped (has image); uses
`adoptions-verified` by default. Named with photo **4,332** / 7,041. **No**
`islands.json` write. Report: `data/staged_merge_report.json` (dry_run).

**2026-06-04 (strict staged photo gate)** — `python3 scripts/verify_staged_photos_strict.py`
on all `data/staging/adoptions/*.json` (**44** input rows). **20** passed (≥90, dual
signal): **commons-deep 2/2**, **inaturalist 18/18**. **0** from **ogl-tourism 21**,
**openverse 3** (name-only /
no entity). Output: `data/staging/adoptions-verified/`; report:
`data/staging/adoptions_strict_verify_report.json`. **No** `islands.json` merge.

**2026-06-02 (staged merge soak + verify)** — Subagent polled staging **45 min**
(90 s interval) while harvesters wrote `data/staging/adoptions/*.json`; no
`--apply` writers. Merge #2 **+45** applied earlier; post-soak merge **0** new
(all 44 candidates already had `images[]`). `archive_nls` finished (**1** staged,
**0.3%** yield). Index rebuilt; `verify_island_images.py`: **4,335** named with
lead photo (**≥90** 1,136 / **80–89** 1,485 / **<80** 1,714). Gap to **6,000**:
**2,665**.

**2026-06-02 (staged photo merge #2)** — `python3 scripts/merge_staged_photo_adoptions.py`
after ~20 min soak (no `islands.json` writers; `enrich_images_archive_nls.py` still
staging-only). **+45** merged (**45** deduped candidates from 10 staging files). By
source: **commons-regional-category 23**, **inaturalist-obs 18**, **openverse 3**,
**wellcome-collection 1**. Index rebuilt. Named atlas with photo **4,335** / 7,041
(**2,706** photoless). Report: `data/staged_merge_report.json`. Geograph **411** applied
earlier via `run_diverse_photo_sources.sh`; first merge skipped them (already had photo).

**2026-06-02 (web photo URL discovery staging)** —
`scripts/discover_island_photo_urls.py` → `data/staging/adoptions/web-discovery.json`
(Wikidata P973/P856, Wikipedia extlinks, DuckDuckGo lite, og:image on OGL/CC/gov).
`--limit 200`: **0 staged** (priority tier = obscure Hebridean islets; Wikimedia 429
during run). Cache: `data/cache_web_photo_discovery.json`. Report:
`data/image_enrichment_web_discovery_report.json`. Re-run with `--refresh --delay 3`.

**2026-06-02 (OGL / tourism open-data staging)** —
`scripts/enrich_images_ogl_tourism.py` → `data/staging/adoptions/ogl-tourism.json`
(Commons regional island categories + data.gov.uk OGL indexer; press libraries blocked).
`--named-only --limit 400`: **21 staged** (21/2751 named photoless had category filename
matches). Report: `data/image_enrichment_ogl_tourism_report.json`; cache:
`data/cache_ogl_commons_regional.json`.

**2026-06-02 (iNaturalist CC observation staging)** —
`scripts/enrich_images_inaturalist.py` → `data/staging/adoptions/inaturalist.json`
(default staging; research-grade + explicit CC-BY/BY-SA/CC0 only; 300 m centroid
verify). `--named-only --limit 300`: **18 staged** / 300 attempted (**6%** hit rate).
Cache: `data/cache_inaturalist.json`. Report: `data/image_enrichment_inaturalist_report.json`.

**2026-06-02 (Commons text warm + regional staging)** —
`scripts/warm_commons_text_cache.py` (cache only; stop on 429),
`scripts/enrich_images_commons_regional.py` → `data/staging/adoptions/commons-deep.json`.
Warm `--limit 500`: **+1** `cache_commons_text` key (**3,003** total; 429 after 2 queries).
Geograph `--cache-only`: **0** new staged (**2,751** named photoless). Regional cache scan:
**2** staged (Stac Levenish, Piper's Island). Reports:
`data/warm_commons_text_cache_report.json`, `data/image_enrichment_commons_regional_report.json`.

**2026-06-02 (Flickr + Europeana + Openverse photo staging)** —
`scripts/enrich_images_flickr_europeana.py` → `data/staging/adoptions/flickr-europeana.json`
(requires `EUROPEANA_API_KEY` / `FLICKR_API_KEY` in `.env.local` for API paths; tag-feed
fallback rarely yields licence metadata). Openverse pass `--limit 800` in flight →
`openverse.json`. Keys documented in `.env.local.example`.

**2026-06-02 (P373 Commons category harvester)** — `scripts/enrich_images_wikidata_p373.py`
stages to `data/staging/adoptions/p373-commons.json` (default; `--apply` for
`islands.json`). P373 + commonswiki sitelink fallback. Full named photoless Q-ID
pool **876** (was ~963 pre-index): **0 staged** — 867 lack P373 and sitelink; 9
have both but Commons categories contain only maps/charts (filtered). v3
`commons-category: 0` root cause: v3 used sitelink only; same 9 Q-IDs, no
licensed photos in members. Cache: `data/cache_wikidata_p373.json` (9 with P373);
report: `data/image_enrichment_wikidata_p373_report.json`.

**2026-05-31 (homepage load v3 — sub-7s interactive target)** — Index prefetch at module init;
boot skips marker rebuild + 7k sort; loader dismisses after list paints; markers build in
**350-row rAF chunks** after idle; lazy tooltips at zoom ≤7; **proj4** + **island-3d** load on
demand only; `index.html` preloads index JSON. Push via SSH to `main`.

**2026-05-31 (atlas load fix v2 — compact index, lazy shards, _site deploy)** —
First paint from v2 **`islands_index.json`** (~**0.9 MiB**, short-key stubs; was ~12 MiB).
Unnamed overlay lazy (~**0.8 MiB**). Nation shards merge **on demand** when opening a
profile (`ensureNationShardLoaded`) — no startup preload of all ~19 MiB shards. Pages CI
stages **`_site/`** via `prepare_pages_artifact.py` (omits monolithic `islands.json`).
Regenerate: `python3 scripts/build_islands_index.py`.

**2026-05-30 (Google indexing — profile sitemap + static homepage SEO)** — Sitemap
now lists **7,055** URLs: home, 13 ferry guides, **7,041** `/profiles/<id>.html`
static pages (not `?island=` query strings). Homepage ships canonical, OG/Twitter,
`WebSite` JSON-LD, crawl-link footer; `seo-head.js` for Search Console verification.
Regenerate: `IOB_SITE_ORIGIN=https://www.findmyisland.com python3 scripts/generate_seo_artifacts.py --landing-dir profiles`.
See `docs/SEO-GEO.md`.

**2026-05-30 (usability pass — deferred load, placeholders, lightbox, discoverability, a11y)** —
Frontend paints from `islands_index.json` + `thumbUrl` stubs, then merges **7 nation shards**
(`data/shards/*.json`) in parallel instead of blocking on monolithic `islands.json`.
**Browse quick filters** (Has photo / Ferry / For sale + top explore topics) promoted above
the list; trip planner demoted. Type-tinted **photo placeholders** in list + detail hero.
**Gallery lightbox** on hero click. **Keyboard** ↑/↓ through virtualised list; filter drawer
focus trap on mobile. Chat gazetteer extended (+12 ferry hubs). v5 photo batch (**80** attempts,
**0** adoptions — Commons **429**). Regenerate index + shards:
`python3 scripts/build_islands_index.py` (Pages workflow runs this on deploy).

**2026-05-19 (property listings — Tier 4 obscure + weekly system)** — **37** islands
with `propertyListings[]` (**+8** vs 29 after Tier 3). Tier 4 obscure brokers;
**full list:** `docs/FOR-SALE-ISLANDS.md`; registry:
`data/discovery/property_listings_registry.json`; skill:
`.cursor/skills/weekly-island-property-discovery/`; workflow:
`.github/workflows/main.yml`.

**2026-05-19 (property listings — Tier 3 broker crawl)** — **29** islands with
`propertyListings[]` (**+12** new vs prior **17**). Tier 3 desk research across
Scotland / Ireland / England-Wales broker sites; `scripts/discover_property_tier3.py`
+ `scripts/match_property_listing_islands.py`. New islands include Eilean Righ,
Thorne Island, High Island, Whiddy, Heir, Kerrera, Turbot, Inishmicatreer, Arranmore,
Horse Island (Loop Head), St Agnes (Scilly), Taggs Island. Manifest:
`data/discovery/property_listings_verified.json`. Refresh:
`python3 scripts/sync_curated_property_listings.py`.

**2026-05-19 (property listings — deep broker pass)** — First verified manifest (**17**
islands): Inchmarnock, Eilean Mòr (Loch Sunart), Inishturk (ULE), Inis Barna, Boa
Island, Thames Ditton, Pharaoh's Island, etc.

**2026-05-19 (property listings — for sale UI)** — Gold **£** map markers, filter,
detail **On the market** section; `hasPropertyListing` on index. See
`docs/PROPERTY-LISTINGS.md`.

**2026-05-17 (SEO discoverability)** — Committed **`sitemap.xml`** (7,042 URLs) and
**`robots.txt`** for `https://www.findmyisland.com`. **`index.html`** sets
`window.IOB_SITE_ORIGIN` for canonical/OG URLs. **Pages workflow** runs
`generate_seo_artifacts.py` on deploy (refreshes sitemap/robots + **`profiles/`**
thin HTML stubs, gitignored locally). Island meta in-browser remains **`seo-meta.js`**
(client-side); crawlers get sitemap + optional static landings.

**2026-05-17 (deploy: map UX, trip planner, index stubs)** — **Map:** larger touch
targets (`tapTolerance` 22, min radius 7, invisible hit halo), viewport-culled markers
at zoom ≤7. **Ferries:** “Plan crossing” sidebar form restores `?trip=` Dijkstra
itinerary banner; per-island **freshness** note from `lastVerified`. **Index:**
`islands_index.json` carries `hasImage` stub (images still merged from full JSON).
**Blocked:** v5 photos (Commons 429, 0 adoptions / 280 attempts); hills (Wikidata 429,
no `cache_dobih.json`; DoBIH CSV absent). **Discovery:** bounded `catalog_scanner`
`--limit=15` (cache only, 0 new candidates).

**2026-05-16 (contribute config + Scotland explore + UX deploy)** — **Contribute:**
GitHub Pages workflow `.github/workflows/pages.yml` injects `CROWD_FORM_EMAIL` secret
into `data/crowd_suggest_config.json`; `scripts/prepare_crowd_config.py`;
`crowd-config.js` + optional `config.local.js`; mailto fallback in modal.
**Scotland explore:** five new topics in `discovery_topics.json` (classics, Inner/
Outer Hebrides, Orkney & Shetland, ferry hops) via `build_discovery_topics.py`.
**UX:** Scotland quick-filter chips, filter tiers, list thumbnails, mobile map peek
(commit `1ae828a` + follow-ups). **P0b geology done (2026-05-16):** BGS ingest finished
(~2.3 h); `cache_bgs.json` (3,647 islands; 2,086 bedrock, 723 superficial); applied to
`islands.json` + index rebuilt. Hills ingest still **blocked** (Wikidata 429) — use
`--dobih-csv` or retry off-peak.

**2026-05-16 (deploy: explore topics + P0b partial apply)** — **Explore** chips:
`data/discovery_topics.json` (notable, island-hopping, thames-eyots, high-summits);
`?explore=<id>` deep links; `scripts/build_discovery_topics.py`. **P0b applied**
(lighthouses **297**, wildlife **38**, census **10** islands) — detail UI for
hills/lighthouses/wildlife/bedrock/census breakdown in `app.js`. **Notable strip**
`featured_islands.json` (120). `islands_index.json` rebuilt (~10.2 MB). Hills/geology
caches still pending. OS key: `config.local.example.js` (copy → `config.local.js`).

**2026-05-16 (featured strip + image priority queue)** — Sidebar **Notable islands**
(`data/featured_islands.json`, 120 rows). Priority queue for v5:
`data/image_priority_queue.json` (3,444 without lead image). Regenerate via
`scripts/build_featured_islands.py` / `build_image_priority_queue.py`; run
`enrich_images_v5.py --queue-file data/image_priority_queue.json` for backfill.

**2026-05-16 (discovery filters + trip planner removed)** — Topbar discovery
filters: **Has photo**, **Ferry** (enabled after `loadFerries()`), **Summit**,
area band (≥1 / ≥10 km²), subtype, curated / hide unconfirmed. Photo filter
sorts with-photo islands first. Ferry trip planner overlay + mobile **Trip** tab
removed; list **⛴** icon and detail **How to get there** unchanged. Chat
synonyms extended (ferry, photo, large, summit, curated).

**2026-05-16 (saved islands email gate)** — Hearts + **Saved** list require a one-time email
(`iobFavoritesEmail` in localStorage); island ids stay in `iobFavoriteIslandIds` on-device only.

**2026-05-16 (native crowd submit)** — In-app **Submit suggestion** for crowd pins
(FormSubmit / Formspree / Web3Forms / webhook via `data/crowd_suggest_config.json` or
`window.IOB_SUGGEST_CONFIG`). GitHub issue remains optional fallback. See
`docs/CROWD-PINS.md`.

**2026-05-16 (Wikidata→OSM backfill)** — `compute_island_areas.py --fetch-osm` (39 new
Wikidata→OSM cache lookups). **`scripts/backfill_osm_from_wikidata.py --apply`**: **83**
rows gained `osmType`/`osmId` (**6,193** / 7,041 now have OSM ids; **848** still without).
Report `data/osm_wikidata_backfill_report.json`. Regenerated `islands_index.json`.
Discovery dry-run: **1** merge candidate; survey ledger **0** strict outstanding.
Backup `data/islands.json.before-osm-backfill-*`.

**2026-05-16 (map first paint + data hygiene)** — **`islands.json` → 7,041** rows
(removed **2** bogus csv-geocoded non-islands: Q26272407 Great Arthur House,
Q66227635 Thorney Island school). **`data/islands_index.json`** slim payload
(~4.5 MB) + two-phase fetch/merge in `app.js` (`loadIslands`). Details panel
**subtype chip** (green pill). **`scripts/build_islands_index.py`** — run after
any `islands.json` edit; see `docs/PIPELINE.md` §5b. **`scripts/recompute_nation_admin1.py`**
(dry-run / experimental): Natural Earth admin-1 **must not** be bulk-applied
— mis-tags NI/ROI and GB border; cache `data/cache_ne10m_admin1_uk_ie.geojson`.

**2026-05-15 (crowd pins v1)** — **Community suggestion layer:** `data/crowd_pins.json`
(maintainer-curated) + map overlay (gold markers), **Suggest island** modal →
pre-filled GitHub issue, **Crowd pins** toggle. Implementation: `crowd-pins.js`,
`app.js`, styles for modal/popup/legend. Workflow: `docs/CROWD-PINS.md`.

**2026-05-15 (SEO + GEO)** — Runtime head tags in `seo-meta.js` (canonical, OG,
Twitter, JSON-LD `Island`); `scripts/generate_seo_artifacts.py` for `llms.txt` +
optional `sitemap.xml` / `robots.txt` / thin `--landing-dir` stubs. See
`docs/SEO-GEO.md`.

**2026-05-15 (terrestrial rock prune)** — Removed **266** non-curated atlas rows:
`osmPlace: rock` + `type: sea` points on **dry land** (well inland of the
simplified UK+IE outline — see `TERRESTRIAL_ROCK_MIN_INLAND_DEG` in
`scripts/discovery/common.py`). Coastal / intertidal stacks (e.g. offshore
sea stacks) **kept**. Script: `scripts/prune_terrestrial_rocks.py --apply`;
audit `data/terrestrial_rocks_prune_report.json`; backup
`data/islands.json.before-terrestrial-rock-prune-20260515T231858Z.bak`.
`map_scanner` now skips the same pattern (`skippedTerrestrialRocks` in
`data/discovery/candidates_scan.json`). **`islands.json` → 7,043** rows.
Discovery **`verification.json` / survey strict “outstanding”** are now **stale**
for former rock OSM ids until you re-run the verifier / ledger pass you trust.

**2026-05-15 (survey ledger runner)** — **`scripts/survey_landmass_ledger.py`**
reconciles `data/islands.json` + `data/discovery/verification.json` (strict
`find_existing_match`, loose=False) into `data/survey/landmass_ledger.json` and
`survey_summary.json`. Latest run after rock prune: atlas **7,043** rows; note
verification bundle still lists many **off-atlas** rock OSM rows that were
**intentionally pruned** — re-run discovery merge or regenerate verification before
trusting **outstanding** counts.

**2026-05-15 (survey prompt)** — **`docs/PROMPT-COMPREHENSIVE-LANDMASS-SURVEY.md`**
— multi-agent copy/paste briefing for full remit landmass + naming sweep, survey
ledger + closure report template; 3 m × 3 m stated as **policy minimum** with
OSM/open-data reality check (not literal wall-to-wall 3 m enumeration).

**2026-05-15 (corrections v1)** — **Suggest a correction** on every island detail
panel: pre-filled GitHub issue (`Drummond1/britishislands`) with island id,
coordinates, OSM/Wikidata links, and required evidence section. Template at
`.github/ISSUE_TEMPLATE/island-data-correction.md`. No on-site accounts;
maintainer review only. Override repo via `window.IOB_CORRECTION_REPO`.

**2026-05-15 (provisional discovery)** — **Unconfirmed classification + site merge.**
`site_update --include-uncertain --apply`: **549** discovery rows merged into
existing atlas records (strict OSM / Wikidata / name match; no global 0.5 km
glue for review-flagged rows). **1** new row: **Wolf Rock Lighthouse** with
`classification.confidence: "unconfirmed"` + `reviewHint` (see
`DATA-SCHEMA.md`). `islands.json` **7,309** (+1). Backup
`data/islands.json.before-discovery-20260515T051857Z`.

**2026-05-15 (trip planner)** — **Ferry trip planner race fix.** `loadFerries()`
could resolve before `islands.json` finished, so `buildFerryIslandRefIndex()`
ran on an empty `byId` and cached an empty ferry graph; Plan route then always
failed until hard refresh. Ferries now wait on `_islandsIndexReady`; islands
load settles that promise; stale empty graphs are invalidated on island load.
Itinerary banner `z-index` raised above the top bar; status line shows a
text summary of the route.

**2026-05-15 05:00 UTC+1** — **Marine Regions discovery cache + site_update fix.**
First full `getGazetteerRecordsByLatLong` grid cached at
`data/cache_discovery_marine_regions.json` (54 cells). Under strict
`placeType=Island` + project bbox, the gazetteer returned **no** usable island
points (only macro / off-remit centroids); the hook remains for transparency
and future filter tuning. **`site_update --apply`** now writes
`islands.json` when there are **merge-only** updates (wikidata/osm/sources on
existing rows), not only new inserts — fixed regression where 5 merges would
stay in-memory. Applied merge pass: **5** enriched existing islands (count
still **7,308**); backup `data/islands.json.before-discovery-20260515T044747Z`.

**2026-05-14 22:45 UTC+1** — **Multi-source catalog discovery applied.**
`scripts/discovery/catalog_scanner.py` harvests Wikidata, Wikipedia island
lists, Thames eyots, crannogs, DoBIH crosswalk, and optional OS Open Names
(`data/raw/os_opennames.csv`). Haswell-Smith, Vision of Britain, and OS
MasterMap stay reference-only. `islands.json` **7,308** (+10 from catalog
merge; backup `data/islands.json.before-discovery-20260514T214253Z`).

**2026-05-14 06:45 UTC+1** — **Autonomous run in progress.** Full
discovery pipeline (`discover_islands_pipeline.py --include-uncertain
--apply`) then overnight enrichment + LLM (≤ $30). Check
`logs/discovery-*.log` and `logs/overnight-*-summary.log`.

**2026-05-13 22:05 UTC+1** — **Five-agent discovery pipeline staged
(`islands.json` untouched).** Orchestrator at
`scripts/discover_islands_pipeline.py` with modules under
`scripts/discovery/` (map scanner, source verifier, photo finder,
enricher, site update). Workflow doc at
[`DISCOVERY-PIPELINE.md`](DISCOVERY-PIPELINE.md). Review-first artifacts
under `data/discovery/` (`candidates_scan.json`, `verification.json`,
`photos.json`, `enrichment.json`, `review_report.json`) plus caches
`data/cache_discovery_*.json`. Dry-run smoke test on 5 candidates:
5 verified, 0 merge-ready without manual review (no licence-safe photos in
the sample). Apply merge only via `--stage=site_update --apply` after
checking **Currently running**.

**2026-05-12 21:45 UTC+1** — **Five-source enrichment scaffold staged
(islands.json untouched).** New ingestion scripts for DoBIH hills,
lighthouses + beacons, RSPB reserves + wildlife colonies, BGS
geology, and Census 2022 population.  Per-source caches at
`data/cache_dobih.json`, `data/cache_lighthouses.json`,
`data/cache_wildlife.json`, `data/cache_bgs.json`,
`data/cache_census2022.json`.  All scripts compile clean, follow the
`<thing>Source` / `<thing>Confidence` / `<thing>Attribution` /
`<thing>FetchedAt` quad, and write atomically with idempotent /
checkpointed / audited behaviour.  Schema proposal at
[`SCHEMA-ENRICHMENTS-2026-05-13.md`](SCHEMA-ENRICHMENTS-2026-05-13.md);
source registry at [`DATA-SOURCES.md`](DATA-SOURCES.md).  The merge
into `islands.json` is gated behind `scripts/apply_enrichments.sh`,
which waits for `scripts/overnight_runner.sh` (PID 71005) to finish.

Dry-run coverage estimates:
* **DoBIH hills** — Wikidata SPARQL fallback covers ~854 hills with
  DoBIH IDs (full DoBIH CSV path also supported).  Expected coverage
  after PIP join: ~250–400 islands have ≥1 classified hill.
* **Lighthouses** — first --fetch run will pull every
  `man_made=lighthouse|beacon` in the UK + Ireland bbox (~600–900
  elements expected from past Overpass runs).
* **RSPB reserves + wildlife** — 25 curated stacks + Wikipedia
  text-scan; first dry-run staged 30 islands (22 curated + 8
  text-scan).
* **BGS geology** — every GB island will resolve a bedrock unit;
  ~2,200 GB islands × ~2 WMS calls each ≈ 4,400 calls at 0.5 s
  polite throttle ≈ 40 minutes.  Dry-run probed 8 large islands
  (Skye, Mull, Anglesey, IoW, Arran, Orkney, Shetland, Lewis) with
  factually-correct bedrock matches.
* **Census 2022** — first 10 islands matched against NRS 2022 sample
  CSV (Skye 10,008; Lewis & Harris 21,031; Mull 3,049; Islay 3,498;
  Arran 4,679; Tiree 653; Iona 177; Eigg 108; Rum 40; Canna 11).
  61 inhabited Scottish islands total once the full NRS table is
  staged.

**2026-05-12 15:45 UTC+1** — **Highest-point elevations published
(293 islands, 4.3 %; up from 27).** New
`scripts/compute_island_highpoints.py` bulk-fetches every
`natural=peak` node with an `ele=*` tag from the UK / Ireland bbox
(18,525 peaks in 42 Overpass tiles), spatial-indexes them, then for
each island polygon finds peaks inside and takes the highest. OSM
`ele` is typically Ordnance-Survey-derived and accurate to ±1 m — well
inside 2 % for any summit ≥ 50 m.

Cross-validated against Wikidata P2044 where both signals exist:

| Conf       | Count | When                                                       |
| ---------- | ----- | ---------------------------------------------------------- |
| `high`     |  239  | OSM-surveyed peak (cross-validated by WD when available)   |
| `estimate` |   54  | Wikidata P2044 only, OR OSM/WD disagree by > 5 m or > 5 %  |
| `n/a`      | 6,483 | No peak inside polygon and no Wikidata elevation           |

Top 30 by computed elevation reads as a who's-who of British / Irish
summits: Ben Nevis (1,345 m) · Carrauntoohil (1,039) · Sgùrr Alasdair
on Skye (992) · Ben More on Mull (966) · Goat Fell on Arran (874) ·
Askival on Rum (812) · An Cliseam on Lewis-and-Harris (799) · Beinn an
Òir on Jura (785) · Croaghaun on Achill (688) · Snaefell on the Isle
of Man (621) — all matching canonical references to the metre.

New fields on each island:
`highestPointM: number | null`,
`highestPointName: string | null`,
`highestPointSource: "osm-peak" | "wikidata-p2044" | "manual" | null`,
`highestPointConfidence: "high" | "estimate" | "n/a"`.

Detail-panel UI updated (`app.js` → `formatHighPointRow`):
high-confidence values render with their source ("· OSM surveyed
peak"); estimate values render with "· estimate · …" so users
immediately see that the figure is unverified.

Backup at `data/islands.json.before-highpoints-20260512T154541Z`.
Full evidence in `data/highpoint_audit.json`.

The 95.7 % `n/a` rate reflects reality: most islands in the dataset
are small islets without OSM-tagged peaks. Future work could sample
SRTM 1-arc-sec or OS Terrain 50 inside each polygon to derive an
elevation; that would be a Phase 2 enhancement.

---

**2026-05-12 15:10 UTC+1** — **Polygon-based island areas published
(85.8 % coverage; 82.4 % at high confidence; the rest N/A).** New
`scripts/compute_island_areas.py` measures each island by geodesic
integration on the WGS84 ellipsoid (`pyproj.Geod.polygon_area_perimeter`),
which is sub-0.01 %-accurate as a *method* — meaning the published
number's uncertainty is entirely the accuracy of the underlying
polygon, not the maths.

Polygons are resolved in priority order:

1. **Step B** — the island's own `osm-way-…` or `osm-relation-…` ID
   (or the `…-w<digits>` suffix embedded in hand-curated IDs) is the
   canonical geometry; fetched in batches from Overpass and cached in
   `data/cache_osm_geometries.json`.
2. **Step C** — for `wd-Q…` IDs we look up the OSM element tagged
   `wikidata=Q…` over Overpass; covers ~60 additional islands where
   the dataset entry doesn't store a way ID directly.
3. **Step A** — only for *hand-curated* IDs (no `osm-`/`wd-`/`csv-`
   prefix and no `-w…` suffix). For these we find the smallest non-
   mainland OSM coastline polygon containing the centroid. The
   allowlist behaviour was a deliberate fix for *islet inheritance*:
   a `wd-Q*` skerry whose centroid happens to fall inside Mull's
   coastline would otherwise be assigned 884 km².

Cross-validation against Wikidata P2046 is treated as a *sanity check*,
not a gate, because the field has many unit-tagging errors (hectares
marked as km², m² marked as km², etc.) — when the OSM/WD ratio matches
a known unit confusion (≈100×, ≈1000×, ≈300×) we keep our number with
a "WD unit mis-tagged" note. Disagreements > 25 % with no unit
explanation downgrade to medium confidence.

Outcome on `islands.json` (6,776 entries):

* **5,581 (82.4 %) — `areaConfidence: "high"`** — polygon-backed
  geodesic, where applicable cross-checked by Wikidata.
* **236 (3.5 %) — `areaConfidence: "medium"`** — small islets with
  minimal polygons, or significant WD disagreement.
* **959 (14.2 %) — `areaConfidence: "n/a"`** — point-only OSM nodes,
  `wd-Q*` islets with no resolvable polygon, csv-geocoded entries
  without an OSM linkage. We honour the spec: "accurate to within
  2 % or N/A".

Spot-checks (computed vs canonical reference, Δ):
GB 218,686 (Δ −4.5 % vs commonly-cited 228,938 which *includes
inhabited adjacent isles*) · Ireland 83,553 (−1.0 %) · L&H 2,149
(−1.4 %) · Skye 1,636 (−1.2 %) · Mull 884.7 (+1.1 %) · Anglesey 679.8
(−4.9 % vs 715 figure that includes Holy Island) · IoM 570.5 (−0.3 %) ·
Arran 429.6 (−0.6 %) · IoW 381.6 (+0.4 %) · Islay 617.6 (−0.2 %) ·
Achill 148.3 (+1.6 %).

New fields on each island:
`areaKm2: number | null`,
`areaSource: "osm-way" | "osm-relation" | "osm-coastline-polygon" | "osm-via-wikidata-…"  | null`,
`areaConfidence: "high" | "medium" | "n/a"`.

Detail-panel UI updated (`app.js` → `formatAreaRow`): high-confidence
areas now render with their source ("· high confidence · OSM way"),
N/A entries show a hoverable tooltip explaining the spec.

Full per-island evidence in `data/area_audit.json` (write-only,
ignored by `.gitignore` if needed); islands backup at
`data/islands.json.before-areas-20260512T151008Z`.

---

**2026-05-12 13:55 UTC+1** — **`unknown` queue drained (210 → 1).** Two
follow-up passes:

1. **Tier 4 added to `scripts/reclassify_islands.py`** — nearest non-tidal
   OSM water polygon ≤200 m = medium-confidence proposal, 200-500 m = low.
   Gated on the mainland test so it can't false-positive a marine islet
   against a coastal freshwater stream. The classifier re-ran in
   ~10 min and proposed 94 transitions (`unknown→river` 38, `unknown→lake`
   56). Applied 76 medium-confidence ones via the existing apply script;
   the 18 low-confidence ones were rolled into the manual sweep instead.
2. **Hand-curated `data/manual_overrides.json`** — 134 entries covering
   the residual unknowns plus the 18 mixed low-confidence Tier-4 ones
   plus a few Tier-4 errors that needed flipping (Cobholm river not
   lake; Eilean na h-Aibhne river not lake; Foaty Island sea not lake;
   Holy-Island-Surrey river not lake; Thorney-Island-Westminster river
   not lake; Great Arthur House kept as unknown). New script
   `scripts/apply_manual_overrides.py` reads the JSON, writes a
   timestamped backup, and supports the same atomic-write + read-back
   safety the auto-apply uses. Persists `classificationNote` so the
   reasoning is preserved in `islands.json` itself.

Final state: `sea: 5,049 · lake: 1,329 · river: 397 · unknown: 1`. The
single remaining unknown is "Great Arthur House Including Boiler House"
(an architectural feature inside the Barbican Estate; needs upstream
CSV cleanup, not a classification fix). Classification-source
distribution: 1,080 tier-a · 249 tier-b · 134 manual-override · 133
osm-water-pip · 80 wikidata-p206 · 76 osm-water-near · 22 thames-list ·
4 wp-category · 3 crannog-subtype-override · 4,995 default-sea-
confirmed.

**2026-05-12 13:15 UTC+1** — **Island categorisation Phase 1.5 applied.**
New Tier 2 added to the reclassification pipeline: every centroid is now
tested against the **GB + Ireland mainland polygons** (built offline by
`scripts/build_land_polygons.py`, pickled to `data/mainland_polygons.pickle`).
An island that sits **inside** the mainland polygon but has **no
positive water-body match** is now flagged `type: unknown` with
classification `{source: "land-in-no-water", confidence: "low"}` rather
than left as the default `sea`. 210 such islands were re-typed in this
pass (`sea → unknown`). Catches: Magurk's Island (Lough MacNean), Bank
Island (Yorkshire Derwent floodplain RSPB reserve), Bingley's Island
(Pegwell Bay marshland), various small Irish lough islets, several
crannogs, plus a handful of tidal/causeway islets (Inchydoney, Corkbeg,
Calbha Mor) that genuinely sit on the line. The UI now ships a fourth
type pill `unknown` (lilac, hatch-textured) labelled **"Unverified
(needs review)"** in legend, type filter, and the details panel.
`islands.json` backup at `data/islands.json.before-reclass-20260512T131152Z`.
Mainland test pickle was built from the cached OSM coastline (40 MB
on disk; 23,354 land polygons, 2 mainland components: GB at 218k km²
and Ireland at 83k km²; clean 39× area gap to next-largest). Type
breakdown now: `sea: 4,991 | lake: 1,257 | river: 318 | unknown: 210`.

**2026-05-12 12:46 UTC+1** — **Island categorisation Phase 1 applied.** 213
islands re-typed from the default `sea` to their correct inland body:
**157 → lake**, **56 → river**. New pipeline at
`scripts/reclassify_islands.py` (Wikidata P206 → P31 + P279 climb, plus
widened OSM water polygon containment). Headline fixes: Kate's Island
(small Yorkshire pond) and Bodinbo Island (River Clyde) both now show
the correct pill. Sea-loch trap solved by cross-referencing each OSM
water body's `wikidata=Q…` tag against the Wikidata cache (Loch Ewe
caught and excluded). Proposal kept at
`data/reclassification_proposal.json` for audit; `islands.json` backup
at `data/islands.json.before-reclass-20260512T124618Z`.

**2026-05-11 20:00 UTC+1** — **Ferry-routes feature complete.** Three new
JSONs: `data/ferries.json` (**347 routes**: 156 OSM + 141 GTFS + 50
manual), `data/operators.json` (**54 operators**), `data/ferry_terminals.json`
(**903 terminals**, 366 matched to islands). Plus `data/ferries_manual.json`
(50 hand-curated routes / 73 hand-curated terminals) and
`data/causeways.json` (11 tidal/bridge entries). UI ships the "How to get
there" block on every island details panel, dashed-polyline ferry layer
on the detail map, `⛴` icons in the sidebar, ferry-aware chatbot intent,
verified/stale badges, drive-time pills (London / Glasgow / Edinburgh /
Belfast / Dublin), Trainline + Discover Cars affiliates with
`rel="sponsored"`, 12 SEO landing pages with `TouristTrip` JSON-LD per
route, and a Dijkstra-backed multi-island itinerary builder triggered
via `?trip=startId,endId`. Orchestrator `scripts/refresh_ferries.py`
runs the full pipeline monthly and emits
`data/ferries_stale_report.json`. Full operator-by-operator notes in
[`FERRIES.md`](FERRIES.md).

**2026-05-11 18:30 UTC+1** — Tier A/B priority shipping. **Per-island
image galleries** (lazy-loaded `data/galleries.json`, harvested by
`scripts/enrich_images_v4.py`, hooked into the existing thumb-strip);
**fuzzy/typeahead sidebar search** (diacritic-insensitive, subsequence-
tolerant, scored not alphabetical); **cultural-names enrichment**
(`scripts/enrich_names.py`) → 184 new label fills across `fr / ga / sco /
cy / gd / kw / gv`; **CSV-skip geocoder** (`scripts/geocode_csv_skips.py`)
launched to recover the 235 unmatched rows via Wikidata
`wbsearchentities` + bbox filtering.

**2026-05-11 17:55 UTC+1** — Big session. **v3 enrichment complete**
(2,263 adoptions; 3,342 / 6,748 islands now have photos, 49.5 %).
**OS Leisure** detail view shipped (EPSG:27700, paper-map detail) with
Leisure/Outdoor/OSM basemap switcher. **User CSV merged**: 399 existing
entries enriched, 7 new entries added (6 archipelago groupings +
Rockall), 7 duplicates auto-deduped via a follow-up pass when the matcher
was patched to handle "Isle of"/"Sanda Island" name variants.

---

## 1. Dataset at a glance (`data/islands.json`)

| Metric | Value |
|---|---|
| **Total islands** | **7,308** |
| File size | 8.0 MB |
| Total lines | ~283,000 (post v3 + CSV + reclass) |

### By type (post `unknown`-queue drain, 2026-05-12)

| Type | Count | Source mix |
|---|---:|---|
| `sea` | **5,049** | tier-a/b/default-confirmed + manual-override 57 + Tier-4 misclassifications corrected |
| `lake` | **1,329** | tier-a 878 · tier-b 213 · wd-p206 24 · osm-water-pip 133 · osm-water-near 44 · wp-category 4 · crannog 3 · manual-override 30 |
| `river` | **397** | tier-a 202 · tier-b 36 · thames-list 22 · wd-p206 56 · osm-water-near 32 · manual-override 47 |
| `unknown` | **1** | Great Arthur House (Barbican Estate building, awaiting upstream CSV cleanup) |

### By nation

| Nation | Count |
|---|---|
| Scotland | 3,128 |
| Ireland | 1,852 |
| England | 953 |
| Northern Ireland | 469 |
| Wales | 187 |
| Crown Dependency (IoM, Channel Is., etc.) | 162 |

### By type

| Type | Count |
|---|---|
| Sea | 5,382 |
| Lake | 1,097 |
| River | 262 |

### Field coverage

| Field | Coverage |
|---|---|
| `osmId` | 5,853 (87%) |
| `wikidata` Q-ID | 2,698 (40%) |
| `wikipedia` URL | 1,043 (15%) |
| `parentWaterBody` (inland) | 1,351 (20%) |
| `images[]` (>=1 image) | **3,342 / 6,748 = 49.5 %** (v3 complete) |
| `galleries.json` (extra images, lazy-loaded) | growing — v4 in flight, target ~3 extras × 3,342 = ~10 k extras |
| `names.{gd,cy,ga,gv,kw,sco,fr,nrf}` (non-English) | **961** islands with ≥1 non-English label (777 pre-existing + 184 new) |
| `population` | 141 (curated mostly) |

---

## 1b. Ferry corpus (`data/ferries.json`)

| Metric | Value |
|---|---|
| Routes | **347** |
| Operators | **54** |
| Terminals | **903** |
| Terminals matched to an islandId | **366** |
| Manually curated routes | 50 |
| Causeways | 11 |

Route sources: `osm-relation` 156 · `gtfs` 141 · `operator-page` (manual) 50.

Operators by country: Scotland 14 · Ireland 13 · England 12 · Wales 3 · Northern Ireland 3 · International 3 · Isle of Man 1 · Channel Is. 4 · France 1.

Harvest methods: `gtfs` 7 · `scrape` 25 · `manual` 22.

See [`FERRIES.md`](FERRIES.md) for the full operator inventory, ToS notes, and refresh cadence.

---

## 2. Currently running

| Process | Started | ETA | Owner | Notes |
|---|---|---|---|---|
| ~~Interest expansion, second pass~~ ✅ 2026-10-26 19:54 UTC | 2026-10-26 19:27 UTC | — | cursor agent | Published `data/interest_index.json`. Film **139**, whisky **21**, for sale **48**, rare wildlife **33**, tidal **104**, castles **96**, books **32**, traditions **30**, unusual news **50**. Stories **1,488** / **901** with a picture. Wrote `data/interest/memberships_sync.sql`. Did not call Supabase. Did not edit `islands.json`. |
| ~~Interest index publish~~ ✅ 2026-10-26 15:59 UTC | 2026-10-26 15:50 UTC | — | cursor agent | Published `data/interest_index.json`. Film **139**, whisky **20**, for sale **48**, rare wildlife **30**, tidal **104**, castles **94**, books **32**, traditions **30**, unusual news **50**. Stories **1,475** / **891** with a picture. Wrote `data/interest/memberships_sync.sql`. Did not call Supabase. Did not edit `islands.json`. |
| ~~Unusual news harvest~~ ✅ published 2026-10-26 | 2026-10-26 14:07 UTC | — | cursor agent | **50** islands, **54** stories in `data/interest_index.json`. Did not edit `islands.json`. |
| ~~Local traditions harvest~~ ✅ published 2026-10-26 | 2026-10-26 07:10 UTC | — | cursor agent | **23** islands, **35** customs in `data/interest_index.json`. Cache `data/cache_local_traditions/`. Did not edit `islands.json`. |
| ~~Books set on the island~~ ✅ published 2026-10-26 | 2026-10-26 06:20 UTC | — | cursor agent | **22** islands, **39** books in `data/interest_index.json`. Cache `data/cache_island_books/`. Did not edit `islands.json`. Supabase not reloaded. |
| ~~Island castles interest harvest~~ ✅ published 2026-10-26 | 2026-10-26 04:40 UTC | — | cursor agent | **89** islands, **113** castles in `data/interest_index.json`. Cache `data/cache_island_castles/`. Did not edit `islands.json`. |
| Film, music, artwork, and photo harvests for the film/art/music filter | 2026-10-25 19:23 UTC | this session | cursor agent | Four passes write only `data/interest/candidates/film-open.json`, `music-further.json`, `artwork-further.json`, and `data/interest/culture_photo_backfill.json`. They do not edit `islands.json` or publish the index. |
| `run_continuous_seo_geo.sh --loop` (PID **848**, screen `iob-seo-geo`) | 2026-07-28 18:10 BST | ongoing | autonomous bash | Strategy-aligned continuous SEO/GEO. Lock `data/.continuous_seo_geo.lock`. Stop: `touch data/.continuous_seo_geo.stop` or `screen -S iob-seo-geo -X quit`. Policy: **no deindex**. Log: `logs/continuous-seo-geo-20260728T171002Z.log` / `logs/continuous-seo-geo.out`. Re-arm: `bash scripts/arm_continuous_seo_geo.sh`. |
| ~~`run_overnight_seo_geo.sh --loop`~~ ✅ finished 2026-07-28 05:05 UTC | 2026-07-27 | — | autonomous bash | **11** cycles; avg **47.78→47.81**, desc **1,617→1,621**, photos flat **4,356**. Superseded by continuous loop. |
| ~~`AGENT_LOOP_TICK_seo_geo` (hourly)~~ stopped | — | — | — | Replaced by autonomous overnight bash, then continuous. |
| ~~`enrich_descriptions_wikipedia.py` sitelink+multilang~~ ✅ | 2026-07-27 ~06:25 BST | — | cursor subagent | Prefetch + multilang pass; **+45** desc after QA. |
| ~~`run_overnight_discovery_naming.sh --loop`~~ ✅ finished 2026-07-27 04:27 UTC | — | — | cursor agent | 8 cycles; +1 island overnight; naming −27. Superseded by discovery unlock (+174). |
| _(idle photo continuous)_ | — | — | — | Priority push **2026-06-11**: **4,341→4,342**. Re-arm `run_continuous_improvement.sh` on request. |
| _(prior — islands.json idle since 2026-06-04)_ | — | — | — | Baseline **4,341** / 7,041 named with photo; gap to 6k **1,659**. |
| ~~`enrich_images_openverse.py --limit 800`~~ ✅ | 2026-06-02 | — | cursor subagent | **+3** staged → `openverse.json` (800 considered; cache-heavy). |
| ~~`enrich_images_archive_nls.py --limit 300`~~ ✅ | 2026-06-02 | ~83 min | cursor subagent | **1** staged (Wellcome `ararat` homonym); **0.3%** yield. |
| ~~`enrich_images_commons_archipelago_sweep.py --named-only --delay 2`~~ ✅ | 2026-06-04 | ~5 min | cursor subagent | Index **13,309** files / **374** cats; **9** staged → `commons-archipelago.json` (429 backoff). |
| ~~`enrich_images_commons_depicts_q.py --named-only --limit 600`~~ ✅ | 2026-06-04 | ~18 min | cursor subagent | **6** staged → `commons-depicts-q.json` (P180 only). |
| ~~`scripts/merge_staged_photo_adoptions.py` (#2)~~ ✅ | 2026-06-02 | — | cursor subagent | **+45** (ogl/regional 23, iNat 18, openverse 3, Wellcome 1). Prior merge: **+5** openverse; **411** geograph skipped (photos already on island). |
| ~~`scripts/run_diverse_photo_sources.sh`~~ ✅ | 2026-06-02 | — | — | 3,871→4,285; orchestrator at `scripts/run_diverse_photo_sources.sh`. |
| ~~`scripts/enrich_names.py` → …~~ | 2026-05-14 20:30 UTC+1 | — | — | Superseded / not running. |
| ~~`scripts/autonomous_run.sh`~~ | 2026-05-14 06:45 UTC | — | — | Stalled on Commons 429 during image v5. |
| ~~`scripts/overnight_runner.sh` (PID 71005)~~ | 2026-05-12 20:30 | — | — | Superseded; see QUEUE.md. |
| ~~`python3 scripts/compute_drive_times.py` (PID 70453)~~ ✅ done 2026-05-11 20:25 | 2026-05-11 19:55 | ~30 min | main agent | OSRM batch drive-time bands from London / Glasgow / Edinburgh / Belfast / Dublin to each mainland terminal. Now uses `curl` via `subprocess` after diagnosing a Python TLS handshake failure against the public OSRM demo server. **Result**: 535 of 538 mainland terminals populated; 3 unreachable in OSRM's road graph. |

### Completed today (2026-05-11)
- **Gallery v4 phase 1** — wired `data/galleries.json` lazy-fetch on first
  island click; merge with `island.images[]` is idempotent and cached on
  the island object. Existing thumb-strip + hero-swap UI picks up the
  extras automatically. Tracking-UTM params stripped from Commons URLs.
- **Fuzzy/typeahead search** in the sidebar (`applyFilters` rewrite,
  `_scoreIsland`) — exact > prefix > word-start > substring > subsequence.
  Diacritic-insensitive ("Eilean Mor" → "Eilean Mòr"). Cache normalised
  search strings on the island record so 6,748× per keystroke is cheap.
- **Cultural-names enrichment** — `scripts/enrich_names.py` populated
  `names.{lang}` for 184 islands via Wikidata `wbgetentities labels`.
  Largest wins: 135 fr (Channel Islands), 47 ga, 15 sco. UI already
  rendered these via `renderAltNames`; just needed data.
- **v2** (`scripts/enrich_images.py`, Wikidata P18 + Wikipedia pageimages)
  finished at 12:17 — added 290 photos (789 → 1,079).
- **v3 first attempt** (PID 39072, no checkpointing) was killed at 12:48 with
  800/5,662 processed; all in-memory work lost. Caches survived → fast replay.
- **v3 second run** (PID 56783, checkpointed) finished at 17:13 after ~1 h 45 m.
  Adopted: 172 from Commons category, 5 from OSM `image` tag, 2,086 from
  Commons radial geosearch (the workhorse). Final coverage: 3,342 / 6,748.
- **`areaKm2` mis-scaling fix** applied at ~15:25. 67 entries had their stored
  area divided by 100 (Wikidata returned hectares stored as km² by
  `ingest_sources.py`). Backup at `data/islands.json.before-area-fix`.
- **OS Leisure detail view** shipped at 17:13 via proj4leaflet (EPSG:27700).
- **User CSV merge** (`scripts/merge_csv.py`) at 17:30. 665 rows → 399 enriched,
  16 added → after auto + manual dedup → 7 kept as new entries.

---

## 3. File inventory (data/)

| File | Size | Last write | Purpose |
|---|---|---|---|
| `islands.json` | 5.9 MB | 11:33 | Canonical dataset. |
| `islands_index.json` | ~4.5 MB | 2026-05-16 | Slim map/list/search scaffold; regenerate with `scripts/build_islands_index.py`. |
| `islands.json.before-ingest` | 4.5 MB | 11:33 | Pre-discovery-ingest backup. |
| `curated.json` | 34 KB | 2026-05-10 22:05 | Hand-curated 27-island spine. Do **not** delete entries. |
| `crowd_pins.json` | small | 2026-05-15 | Maintainer-curated community pins (separate from `islands.json`). See `docs/CROWD-PINS.md`. |
| `osm_raw.json` | 1.2 MB | 2026-05-10 22:26 | Cached Overpass island response. |
| `water_raw.json` | 274 MB | 2026-05-11 07:16 | Cached Overpass water-body response (large). |
| `inland_classification_report.json` | 159 KB | 11:33 | Audit trail for Tier A + B classifier. |
| `discovery_ingestion_report.json` | 8 KB | 11:33 | What each discovery source added. |
| `image_enrichment_report.json` | 57 KB | (v1 = 10:28; v2 in flight) | Image provenance + spot-checks. |
| `cache_wd_islands.json` | 2.4 MB | 11:20 | Wikidata SPARQL islands cache. |
| `cache_wikidata.json` | 227 KB | 11:45 | Wikidata P18 image lookups (live-updated). |
| `cache_commons.json` | 435 KB | 10:14 | Commons file-info cache. |
| `cache_pageimages.json` | 10 KB | 10:03 | Wikipedia pageimages cache. |
| `cache_pageprops.json` | 1 KB | 10:13 | Wikipedia pageprops cache. |
| `cache_thames.json` | 27 KB | 11:20 | River Thames discovery cache. |
| `cache_crannogs.json` | 2 KB | 11:32 | Crannog discovery cache. |
| `cache_designations.json` | 107 B | 11:21 | Statutory designations cache (empty, source still pending). |
| `candidates_*.json` | varies | 11:20–11:32 | Pre-merge candidate sets from each discovery source. |
| `ferries.json` | ~ 400 KB | 2026-05-11 | 347 ferry routes (156 OSM + 141 GTFS + 50 manual). |
| `operators.json` | ~ 60 KB | 2026-05-11 | 54 ferry operators with Wikidata IDs, ToS disclosures, harvest methods. |
| `ferry_terminals.json` | ~ 320 KB | 2026-05-11 | 903 canonical terminals incl. drive-times + cultural names. |
| `ferries_manual.json` | ~ 80 KB | 2026-05-11 | 50 hand-curated routes / 73 terminals (input to `merge_ferries.py`). |
| `causeways.json` | ~ 10 KB | 2026-05-11 | 11 tidal / bridge access points (Lindisfarne, St Michael's Mount, Davaar, etc.). |
| `ferries_stale_report.json` | < 1 KB | 2026-05-11 | Auto-generated by `refresh_ferries.py`; routes with `lastVerified` ≥ 180 days. |

---

## 4. Frontend state

- **Two-phase island load**: v2 compact **`data/islands_index.json`** (~0.9 MiB; `version` +
  short keys expanded in `app.js`) paints map + list first. Full records merge **on demand**
  from nation shards when a profile opens (`ensureNationShardLoaded`); monolithic
  `data/islands.json` is omitted from production `_site/` artifact and only used as local
  dev fallback if index missing. Regenerate via `scripts/build_islands_index.py` (Pages
  workflow runs this + `prepare_pages_artifact.py`). At zoom ≤7, only markers inside the
  viewport are painted (pan/zoom refreshes the layer).
- **Plan crossing**: sidebar form builds `?trip=startId,endId` and shows an
  itinerary banner under the header (ferry graph from `loadFerries()`).
- Static app served by `python3 -m http.server` (currently port 8767).
- Marker clustering: **on** by default (`#cluster-toggle`).
- List virtualisation: **active** (renders only visible items, ~30 at a time).
- **OS Maps detail view: full Leisure shipped (17:13).** The details panel
  has a three-button basemap switcher: **OS Leisure** (EPSG:27700,
  paper-style 1:25k/1:50k via proj4leaflet — default in GB), **OS
  Outdoor** (EPSG:3857), and **OSM** (universal fallback). Disabled
  buttons indicate what would unlock with a key or inside GB. Selection
  persists across island switches via `localStorage.detailBasemap`.
  proj4 + proj4leaflet load from unpkg (≈98 KB combined). API key from
  `window.OS_MAPS_API_KEY` or `localStorage.osMapsApiKey`. See
  [`OS-MAPS.md`](OS-MAPS.md).
- Polygon overlays: lazy-fetched from Overpass on island click for islands
  with `osmId`.
- **Per-island image galleries**: `data/galleries.json` (separate file,
  lazy-fetched on first island click) supplies up to 3 extra photos per
  island. The merge into `island.images[]` is done once and cached on the
  island object so re-renders are O(1). The existing thumb-strip below the
  hero now shows the full set; clicking a thumb swaps the hero (already
  wired up). See `loadGalleries` / `ensureGalleryMerged` /
  `refreshGalleryInPlace` in `app.js`.
- **Sidebar search is fuzzy/typeahead** as of 2026-05-11: the search box
  scores islands per keystroke with prefix / word-start / substring /
  subsequence matching, diacritic-insensitive. Sort is by score when a query
  is active; alphabetic when the box is empty (with-photo first when **Has
  photo** is on).
- **Discovery filters** (2026-05-16): topbar toggles/selects for photo,
  ferry-accessible, summit/elevation, minimum area, subtype, and
  curated / hide-unconfirmed. Ferries preload after islands load so the
  ferry filter enables without opening an island first.
- **Crowd pins**: optional gold markers from `data/crowd_pins.json`; **Suggest
  island** opens a map pick + GitHub issue (no on-site accounts). Toggle
  **Crowd pins** in filters. See `docs/CROWD-PINS.md` and `crowd-pins.js`.
- **Name an unnamed island**: Filters → Unnamed places only → click one. The
  profile is a four-field form. The suggested name shows at once. The email
  stays in Supabase `island_name_log`. See `name-island.js`.
- **Chatbot ("Island finder")**: floating "Ask" button bottom-right opens a
  chat panel. **Local mode** (default) parses nation, type, subtype,
  archipelago, feature, size, sort, and proximity, and nothing leaves the
  browser. **Smart answers** (visitor's own OpenAI or Anthropic key, stored
  only in this browser) lets the model call `search_islands`, `count_islands`,
  `list_collections`, and `read_islands` against the loaded atlas, then write
  from those records. Loch names and short snippets live in
  `data/chat_corpus.json`, fetched when Ask opens. Each query is reflected
  as `?ask=…`. See `chat-agent.js`, `app.js → CHAT_*`, and `.chat-*` styles.
- **Ferry layer**: lazy-loaded on first island click via `loadFerries()` +
  `loadCauseways()`. The details panel ships a "How to get there" block
  with operator-branded ferry cards (route label, duration, frequency /
  seasonality / type pills, verified/stale badge, drive-time pills,
  Trainline + Discover Cars affiliate links, "Book ↗" CTA) and a
  separate "Causeway access" block for tidal-causeway islands. The detail
  map renders dashed-polyline ferry routes + terminal markers; the
  sidebar shows a `⛴` icon next to ferry-accessible islands. SEO landing
  pages (12 of them) ship under `ferries/` with `TouristTrip` JSON-LD per
  route. (Trip-planner overlay removed 2026-05-16.) See [`FERRIES.md`](FERRIES.md).

---

## 5. Known good (smoke checks)

After any data run, the following must remain correct (see `VALIDATION.md` for
the full set):

- `Isle of Skye` → sea, Scotland, large polygon, image present.
- `Devenish Island` → **lake** (Lower Lough Erne), Northern Ireland.
- `Eilean a' Bhuidhe` (Loch Lomond) → lake, Scotland.
- `Isle of Wight` → sea, England.
- `Achill Island` → sea, Ireland.

---

## 6. Known issues / debt

- ~5,400 unnamed inner-ring inland features were intentionally **excluded**
  during Tier A. Some of these may be genuine, named-but-unmapped islands. See
  `METHODOLOGY-INLAND.md` §6.
- `population` is only set for ~141 curated/Wikidata-enriched entries — most
  small islands lack population data anywhere upstream.
- **848** entries still lack an `osmId` (mostly Wikidata-only; OSM has no
  `wikidata=` tag on a way/relation for **841** cached misses). Polygon overlay
  needs `osmType`+`osmId` (way/relation). Re-run `backfill_osm_from_wikidata.py`
  after refreshing cache.
- Belle Isle (Windermere) has no Wikidata Q-ID, so no image source — should
  resolve in v3 via Commons geosearch.
- **`areaKm2` mis-scaling (mostly fixed at 15:25).** Root cause: not
  `fetch_islands.py` but `scripts/ingest_sources.py` line 290 — Wikidata's
  `wdt:P2046` was read raw, which is in **hectares** for individual islands
  but in **km²** for whole-country entries (Great Britain, Ireland). 67
  entries patched. A handful of small islands in the 1–200 km² band may
  still be off (e.g. Cardigan Island shown as 40 km², real ~0.24 km²) — the
  fix's threshold is conservative. **Long-term fix**: rerun the SPARQL
  query with proper unit normalisation in `ingest_sources.py` (extract the
  unit Q-ID alongside the value).
- 235 CSV rows skipped during merge: 71 had ambiguous names (multiple
  matching candidates without DMS coords to disambiguate, e.g. multiple
  "Pabbay"/"Flodday"); 164 are genuinely missing from our OSM data
  (small Hebridean / Irish / French islets). See
  `data/csv_import_report.json` → `skipped_no_coords_no_match`. A future
  pass could geocode them via Wikipedia/Wikidata lookups.
- Geograph direct API now returns 451 ("Unavailable For Legal Reasons") for
  unauthenticated callers. We route around it via Commons geosearch (which
  surfaces Geograph uploads that landed on Commons).
