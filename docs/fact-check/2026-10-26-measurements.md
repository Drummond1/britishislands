# Measurement fact-check — 2026-10-26

Read-only check of the figures a visitor sees on an island profile:
`areaKm2`, `highestPointM`, `highestPointName`, and `population`.
Nothing in `data/islands.json` was edited, and `area_audit.json` was not
recomputed.

Visitor-facing values are the `data/islands.json` records. `data/curated.json`
was compared where both exist; disagreements are noted. The profile prints
`populationYear` as “census {year}” (`app.js`). A stored number can therefore
be a real census total and still be wrong on the page if the year label is
wrong.

## Rules used

- Area: a difference under 5% of the cited figure is not an error.
  Hectares or acres stored as km², or a 10× / 100× slip, is an error.
- Summit: under 5 metres against a surveyed height is not an error.
- Wikidata is a lead, not a verdict. Several P2044 values point at the
  wrong feature. Wikipedia infoboxes and hill-database pages were used to
  decide.
- Population: curated islands, plus any population over 100,000.
  Island totals only.

## Counts

| Bucket | Count |
| --- | --- |
| Confirmed errors (field-level) | 18 |
| Confirmed islands | 14 |
| Of which unit bugs | 0 |
| Plausible, not confirmed | 6 |
| Named islands with `areaKm2` > 20 | 53 (top 40 listed below) |
| `areaKm2` > 5000 other than Great Britain and Ireland | 0 |
| OSM-vs-Wikidata summit mismatches in `highpoint_audit.json` | 9 (7 confirmed wrong on the page, 2 held) |

The old Cardigan Island case (about 40 km² stored for an island of about
0.15 km²) is **not** still in the data. See checked-and-held.

---

## Confirmed errors

None are unit bugs.

### Area

**`osm-relation-3970260` Hayling Island — `areaKm2` — 16.2385 → 30 — not a unit bug**

Wikipedia infobox: 30 km² (12 sq mi), about 6.5 km by 6.5 km.
[Hayling Island](https://en.wikipedia.org/wiki/Hayling_Island).
The [list of British Isles by area](https://en.wikipedia.org/wiki/List_of_the_British_Isles_by_area)
gives 27 km². Stored 16.2 km² is about 46% below 30 and about 40% below 27.
`area_audit.json` already flags an 85% Wikidata gap and `areaConfidence` is
`medium`. This is the incomplete-polygon / boundary case in `QUEUE.md`, not
a hectare tagged as km².

**`mainland-orkney` Mainland (Orkney) — `areaKm2` — 580.604 → 523.25 — not a unit bug**

Wikipedia infobox: 52,325 ha (202 sq mi) = 523.25 km².
[Mainland, Orkney](https://en.wikipedia.org/wiki/Mainland,_Orkney).
Stored 580.6 km² is 11% high. The same article describes the Churchill
Barriers linking Mainland to Lamb Holm, Glimps Holm, Burray and South
Ronaldsay. Those islands are also separate records (South Ronaldsay 49.7 km²,
Burray 9.7 km², Lamb Holm 0.4 km²). Adding them to 523 km² lands on about
583 km², which is the stored Mainland figure. The profile is counting
barrier-linked islands inside Mainland. `curated.json` still has 523.
Summit is held: Mid Hill 275 m versus Wikipedia 271 m (4 m).

### Summits

**`osm-relation-8156739` Arranmore — `highestPointM` — 281 → 227 — not a unit bug**

Stored name Cnoc an Iolair. [MountainViews](https://mountainviews.ie/lists/islandfeature/)
lists the island high point as Cluidaniller West Top, 227 m.
The island’s own places page calls Cnoc an Iolair the highest point at
750 ft (229 m): [Arranmore places of interest](https://arranmoreisland.ie/2020/07/07/places-of-interest/).
Wikidata P2044 is 16 m, which is not a summit either. The metres on the
profile are wrong; the local name Cnoc an Iolair can stay. Wikipedia’s
Arranmore article does not give a height.

**`osm-relation-8495304` Cape Clear Island — `highestPointM` — 212.8 → 160 — not a unit bug**

Same name, Cnoicín an tSeabhaic. Wikipedia infobox: 160 m.
[Cape Clear Island](https://en.wikipedia.org/wiki/Cape_Clear_Island).
MountainViews agrees (160 m). Wikidata 160 m is right here; the OSM `ele`
is about 53 m high. Area 6.50 km² versus Wikipedia 6.7 km² is 3% and is held.

**`osm-relation-3699362` Bere Island — `highestPointM` — 320.1 → 270 — not a unit bug**

Name Knockanallig is right. Wikipedia: 270 m.
[Bere Island](https://en.wikipedia.org/wiki/Bere_Island).
[High Point Ireland](https://www.highpointireland.com/knockanallig-267m.html)
and MountainViews give 267 m, which is within 5 m of 270 and is not a
separate error. Stored 320.1 m is about 50 m high. Wikidata 270 m matches
the infobox. Area 18.1 km² versus 17.68 km² is 2% and is held.

**`osm-relation-6045552` Inishmore — `highestPointM` — 71 → 123 — not a unit bug**

**`osm-relation-6045552` Inishmore — `highestPointName` — An Charcair → An Droim Rua — not a unit bug**

This is the Aran island (stored area 32.2 km²). Wikipedia infobox: An Droim
Rua, 123 m. [Inishmore](https://en.wikipedia.org/wiki/Inishmore).
MountainViews: An Droim Rua, 123 m, Oileáin Árann. An Charcair at 71 m is a
lower feature. Wikidata 123 m is right. Area versus the stated 31 km²
(7,636 acres) is about 4% and is held. There is a second, much smaller
Inishmore in the atlas; this error is the Galway one.

**`osm-relation-3214114` Tresco — `highestPointM` — 34 → 44 — not a unit bug**

**`osm-relation-3214114` Tresco — `highestPointName` — Gun Hill → Castle Down — not a unit bug**

Gun Hill is a real 34 m OSM peak and is not the summit. Castle Down (Tresco)
is 44.0 m in the hill database
([graupel hill 17889](https://www.graupel.org.uk/hill_details.php?searchHill=17889);
[Geograph](https://www.geograph.org.uk/photo/3445151)).
Wikidata 44 m is right. Wikipedia’s Tresco article gives the area as 297 ha,
which matches stored 2.99 km², and does not name the summit.

**`osm-way-219575236` Scarriff Island — `highestPointM` — 305.3 → 252 — not a unit bug**

Wikipedia infobox and the hill note: 252 m, citing MountainViews.
[Scarriff Island](https://en.wikipedia.org/wiki/Scarriff_Island).
Stored 305.3 m is about 53 m high. The audit name on the peak is “Scarriff
Island”; the error confirmed here is the metres.

**`lundy` Lundy — `highestPointM` — 138 → 143 — not a unit bug**

**`lundy` Lundy — `highestPointName` — Tibbett's Hill → Beacon Hill — not a unit bug**

Wikipedia: Beacon Hill, 469 ft (143 m).
[Lundy](https://en.wikipedia.org/wiki/Lundy).
Tibbetts is a building “on the second highest point of the island”
([Landmark Trust](https://www.landmarktrust.org.uk/properties/tibbetts/)).
The OSM peak at 138 m is that lower hill. The 5 m gap is not under the
5-metre allowance, and the name is a different place. Area 4.24 km² versus
Wikipedia’s 4.45 km² / 450 ha is 4.7% and is held. Population 28 matches the
2007 figure in that article.

### Population

The profile shows “census 2022” wherever `populationYear` is 2022.
Those four Scottish numbers were loaded from `data/census2022_nrs.csv`,
whose own header says it is a sample and not the official NRS table.
Skye’s 10,008 is the **2011 island total**, not a civil-parish stand-in
and not the 2022 census.

**`isle-of-skye` Isle of Skye — `population` — 10008 (labelled census 2022) → 10496 (2022) — not a unit bug**

Wikipedia infobox: 10,496. The history table runs … 9,232 (2001), 10,008
(2011), 10,496 (2022). Citation [6] is the Scottish Islands Data Dashboard
(RESAS, 2025). [Isle of Skye](https://en.wikipedia.org/wiki/Isle_of_Skye).
NRS’s 2011 island table is the source of 10,008
([2011 island residents PDF](https://www.nrscotland.gov.uk/files/geography/2011-census/geog-2011-cen-supp-info-islands.pdf)).
Area 1,636 km² versus 1,656 km² is 1.2% and is held. Sgùrr Alasdair 992 m
versus the infobox 993 m is 1 m and is held.

**`lewis-and-harris` Lewis and Harris — `population` — 21031 (labelled census 2022) → 19680 (2022) — not a unit bug**

Wikipedia: 19,680 in 2022, and 21,031 in 2011.
[Lewis and Harris](https://en.wikipedia.org/wiki/Lewis_and_Harris).
The stored number is the 2011 island total with a 2022 label. Area 2,149 km²
versus the usual 2,179 km² is 1.4% and is held. An Cliseam 799 m is the
Gaelic name of Clisham at the same height and is held.

**`islay` Islay — `population` — 3498 (labelled census 2022) → 3180 (2022) — not a unit bug**

Wikipedia infobox: 3,180, Scottish Islands Data Dashboard.
[Islay](https://en.wikipedia.org/wiki/Islay).
3,498 matches neither that 2022 figure nor the 2011 island total of 3,228.
Area 617.6 km² versus 619.6 km² is 0.3%. Beinn Bheigeir 491 m matches the
infobox (curated spelling Beinn Bheigier).

**`arran` Isle of Arran — `population` — 4679 (labelled census 2022) → 4618 (2022) — not a unit bug**

Wikipedia: “In the 2022 census it had a resident population of 4,618.”
2011 was 4,629. [Isle of Arran](https://en.wikipedia.org/wiki/Isle_of_Arran).
4,679 matches neither year. Area 429.6 km² versus 43,201 ha (432.0 km²) is
0.6%. Goat Fell 874 m versus 875 m is 1 m.

**`fair-isle` Fair Isle — `population` — 55 → 44 (2022 census) — not a unit bug**

No year is printed. Wikipedia: 44 permanent residents at the 2022 census;
Ward Hill 217 m; area 768 ha.
[Fair Isle](https://en.wikipedia.org/wiki/Fair_Isle).
55 matches neither the 2022 census (44) nor the 2011 island total (68, in
the NRS PDF above). Summit Ward Hill 217 m is held: Wikidata’s 271 m is the
wrong Ward Hill (Orkney Mainland’s is 271 m). Area 8.10 km² versus 7.68 km²
is 5.4% and is listed under plausible, not confirmed.

**`osm-relation-3969458` Portsea Island — `population` — 150000 → 165248 (2021) — not a unit bug**

Wikipedia infobox: 165,248 (2021). Area in the same infobox is 24.542 km²,
which matches stored 24.52 km².
[Portsea Island](https://en.wikipedia.org/wiki/Portsea_Island).
150,000 is an unlabelled round number, about 9% below the 2021 island
census. Portsmouth local authority is larger (ONS 2021: 208,003) because it
includes mainland wards; the island figure is 165,248, not the city total.
Over the 100,000 flag line.

---

## The nine audit summit mismatches

`highpoint_audit.json` has nine OSM-versus-Wikidata gaps over 5 m. `QUEUE.md`
names seven of them and says most Wikidata values point at the wrong feature.
That is true for two of the nine. For five Irish islands and for Tresco,
Wikidata or the hill page is the better summit and the OSM `ele` or the
chosen peak is what the visitor sees.

| Island | Stored | Wikidata | Verdict |
| --- | --- | --- | --- |
| Arranmore | 281 m Cnoc an Iolair | 16 m | Confirmed. Both wrong. Better 227 m. |
| Fair Isle | 217 m Ward Hill | 271 m | Held. Wikipedia 217 m. Wikidata is the wrong hill. |
| Cape Clear Island | 212.8 m Cnoicín an tSeabhaic | 160 m | Confirmed. Better 160 m. Same name. |
| Bere Island | 320.1 m Knockanallig | 270 m | Confirmed. Better 270 m. Same name. |
| Inishmore (Aran) | 71 m An Charcair | 123 m | Confirmed. Better An Droim Rua, 123 m. |
| Sùla Sgeir | 70 m, no name | 108 m | Held. Wikipedia: near Sròn na Lice, **over 70 m**. 108 m is not supported. The light’s focal height is 74 m, which is not the ground. |
| Tresco | 34 m Gun Hill | 44 m | Confirmed. Better Castle Down, 44 m. |
| Puffin Island (Kerry), `osm-way-4564233` | 212.5 m Oileán na gCánóg | 159 m | Held. [Wikipedia](https://en.wikipedia.org/wiki/Puffin_Island_(County_Kerry)) says 213 m. Stored 212.5 m is within 1 m. MountainViews’ 159 m disagrees with Wikipedia; the page follows Wikipedia. |
| Scarriff Island | 305.3 m | 252 m | Confirmed. Better 252 m. |

---

## Plausible, not confirmed

Not unit bugs. Left alone because the published figure and the coastline
polygon can both be defended, or the only conflicting number is a round
gazetteer figure.

- **Fair Isle area** (`fair-isle`): 8.0965 km² versus Wikipedia 768 ha
  (7.68 km²), 5.4%. Just past the 5% bar. Cliffed-island tide line, not a
  10× error. `curated.json` has 7.68.
- **Sùla Sgeir area** (`osm-way-20594001`): 0.1009 km² versus
  [Wikipedia](https://en.wikipedia.org/wiki/Sula_Sgeir) 15 ha (0.15 km²),
  about 33%. `areaConfidence` is already `medium`. Height held, as above.
- **Holy Island, Anglesey** (`osm-relation-6045346`): area 34.83 km² versus
  [Wikipedia](https://en.wikipedia.org/wiki/Holy_Island,_Anglesey) 39.4 km²,
  about 12%. Summit is already right: Mynydd Twr 220 m (Holyhead Mountain).
  Not “too big for the name”.
- **Lindisfarne** (`lindisfarne`): geodesic 4.92 km² versus Wikidata 4 km²
  in the area audit (19%). Tidal island; not confirmed as a bad polygon.
- **Harris** (`osm-relation-9603390`): 447 km² versus Wikidata 401 km²
  (10%). This is the southern part of the single island of Lewis and Harris,
  which itself is held at 2,149 km². A district boundary, not a Cardigan-class
  blow-up.
- **Shetland** (`osm-relation-376677`): the record is **named** Shetland but
  the area is 953.4 km², the same polygon as `mainland-shetland`, and
  Wikidata P2046 in the audit is 968.8 km² (Mainland). The archipelago is
  much larger. The area matches Mainland; the display name does not. Not
  scored as an `areaKm2` error.

Arranmore’s Wikipedia area of 22 km² against a geodesic 18.3 km² was not
confirmed. The infobox pair is the round “8.5 sq mi”. No surveyed area was
found to overturn the polygon.

---

## Checked and held

### Cardigan Island, the queue example

`osm-way-1493651984` Cardigan Island is **0.154 km²**, height **52 m**,
population 0. [Wikipedia](https://en.wikipedia.org/wiki/Cardigan_Island):
38 acres (15 ha) and 52 m. The Wildlife Trust handbook: 15.6 ha.
0.154 km² is 15.4 ha. The “stored as 40 km², real ~0.24” note in `QUEUE.md`
does not describe the current record. ~0.24 km² is not the Wikipedia figure.

### Anglesey split

`anglesey` area 679.8 km² matches [Wikipedia’s main island](https://en.wikipedia.org/wiki/Anglesey)
of 676 km² (0.6%). The county, including Holy Island, is 712 km², which is
what `curated.json` still says (711). Mynydd Bodafon at 178 m is the highest
point **of the main island**; Wikipedia says Holyhead Mountain, 220 m, is
higher and stands on Holy Island, and it explicitly gives Bodafon as 178 m
on the main island. Holy Island’s own record has Mynydd Twr at 220 m.
Population 68,900 is the rounded 2021 local-authority census (ONS table:
68,878). Not an error.

### Hoy split

`osm-relation-12597159` Hoy is 133.0 km² with Ward Hill 481 m. South Walls
is a separate record at 10.7 km². Together they are about 144 km², against
the area list’s 143 km² for Hoy-with-South-Walls. Held as a clean split,
same pattern as Anglesey / Holy Island.

### Other large named islands (`areaKm2` > 20)

53 named islands are over 20 km². Nothing over 5,000 km² except:

- `osm-relation-6038068` Great Britain, 218,685.6 km². The usual island
  figure is 209,331 km² ([area list](https://en.wikipedia.org/wiki/List_of_the_British_Isles_by_area)).
  Difference 4.5%, under the 5% bar. Not confirmed. Ben Nevis 1,345 m held.
- `osm-relation-7681896` Ireland, 83,553.1 km². Against about 84,421 km²
  that is about 1%; against the area list’s 81,638 km² it is about 2%.
  Held. Carrauntoohil 1,038.6 m is within 5 m of 1,039 m.

Top 40 named islands by stored area. Rows marked “known large” are the
exclusion list in the brief. “Held” means the figure was compared and is
inside 5%, or it is a known large island whose polygon matches a published
figure in the area audit.

| km² | id | Name | Note |
| --- | --- | --- | --- |
| 218685.6 | osm-relation-6038068 | Great Britain | Held, 4.5% above 209,331 |
| 83553.1 | osm-relation-7681896 | Ireland | Held |
| 2149.4 | osm-relation-7220346 | Lewis and Harris | Duplicate of the curated id, same area |
| 2149.2 | lewis-and-harris | Lewis and Harris | Known large. Held |
| 1636.1 | isle-of-skye | Isle of Skye | Known large. Held |
| 953.4 | mainland-shetland | Mainland (Shetland) | Known large. Held vs ~969 |
| 953.4 | osm-relation-376677 | Shetland | Plausible name scope, area is Mainland |
| 884.7 | mull | Isle of Mull | Known large. 1.1% above the list’s 875 |
| 679.8 | anglesey | Anglesey (Ynys Môn) | Held as the main island, 676 km² |
| 617.6 | islay | Islay | Known large. Held |
| 580.6 | mainland-orkney | Mainland (Orkney) | **Confirmed** (should be 523) |
| 570.5 | isle-of-man | Isle of Man | Known large. 0.3% under 572 |
| 447.4 | osm-relation-9603390 | Harris | Plausible district boundary |
| 429.6 | arran | Isle of Arran | Known large. Held |
| 381.6 | isle-of-wight | Isle of Wight | Known large. Held vs 381 |
| 364.8 | osm-relation-4619204 | Jura | Known large. List 367; under 1% |
| 306.8 | osm-relation-380670 | South Uist | Known large. List 320; 4.1% |
| 299.4 | osm-relation-380685 | North Uist | Known large. List 303; 1.2% |
| 211.6 | osm-relation-8684336 | Yell | List 212 |
| 148.3 | osm-relation-6045364 | Achill Island | Known large. List 147 |
| 133.0 | osm-relation-12597159 | Hoy | Held; South Walls is separate |
| 121.3 | bute | Isle of Bute | List 122 |
| 120.1 | jersey | Jersey | Held |
| 119.9 | osm-relation-6045406 | Unst | List 121 |
| 107.1 | osm-relation-929839 | Isle of Rum | List 105; 2.0% |
| 89.6 | osm-relation-2273838 | Isle of Sheppey | List 94; 4.7%, under the bar |
| 79.0 | osm-relation-6045455 | Tiree | List 78 |
| 76.1 | osm-relation-380684 | Benbecula | List 82; 7% low, not “too big” |
| 74.3 | osm-relation-5420246 | Coll | List 77; 3.6% |
| 63.6 | guernsey | Guernsey | Held |
| 62.4 | osm-relation-1663893 | Raasay | List 64; 2.5% |
| 58.2 | osm-relation-380646 | Barra | List 59 |
| 49.7 | osm-relation-3075243 | Sanday | List 50 |
| 49.7 | osm-relation-3601567 | South Ronaldsay | List 50 |
| 48.6 | osm-relation-3148465 | Westray | List 47 |
| 47.2 | osm-relation-13008771 | Rousay | List 49; 3.8% |
| 41.0 | osm-relation-6045516 | Colonsay | List 41 |
| 40.5 | osm-relation-6045499 | Fetlar | List 41 |
| 34.8 | osm-relation-6045346 | Holy Island | Plausible vs 39.4; not too big |
| 33.9 | osm-relation-12597195 | Stronsay | List 33 |

Also checked and not “too big for the name”: Inishmore 32.2 (list 31),
Eigg 29.7 (list 30), Foulness 29.1, Eday 27.7 (list 27), Bressay 27.6
(list 28), Shapinsay 27.4 (list 30), Valentia 26.3, Great Island
(`osm-relation-8158173`) 25.3 versus Wikidata 25.0 in the audit (the area
list’s 61 km² does **not** match Wikidata; the polygon was held), Gorumna
24.9, Scalpay (`osm-way-1169080225`) 24.7 versus Wikidata 24.8 (this is the
Skye Scalpay, not the Harris one of about 6.5 km²), Portsea area held,
Lismore 21.8, Great Bernera 20.4 (list about 21).

`Eilean Mhealasta` (`osm-way-233105297`) is the queue’s other area example:
geodesic 1.33 km², Wikidata 124. The audit already treats that as hectares
mis-tagged as km² (124 ha = 1.24 km²). Our figure is the sane one. Not our
unit bug.

`st-kilda` is named St Kilda (Hirta). Stored 6.28 km² and Conachair 430 m.
[Hirta](https://en.wikipedia.org/wiki/Hirta) says 628.5 ha and 430 m. The
area audit’s 36% Wikidata gap (8.546 km²) is the whole archipelago, not
Hirta. Population 0 matches the 1930 evacuation. Held.
`curated.json` area 8.5 km² is the archipelago, not the Hirta polygon.

### Populations held or not confirmed

| id | Stored | What it matches | Why it is not confirmed |
| --- | --- | --- | --- |
| mainland-orkney | 17162, no year | 2011 island census | [Wikipedia](https://en.wikipedia.org/wiki/Mainland,_Orkney) gives 17,779 for 2022 and states 17,162 for 2011. The page does not claim 2022. |
| mainland-shetland | 18765, no year | 2011 (18,765) | 2022 table is 18,763. Two people. |
| bute | 6498, no year | 2011 NRS island total | 2022 table is 6,047. Year is not printed, so the number is a real census total, not a mislabel. |
| mull | 3049, labelled census 2022 | close to 2022 | Populated-islands table: 3,063 in 2022. Difference 14 people (0.5%). |
| iona | 177, labelled census 2022 | 2011 exactly | 2022 table: 178. One person. |
| isle-of-wight | 140794, no year | near 2021 | ONS Census 2021 local authority: 140,459. Difference 335 (0.24%). St Boniface Down 242 m versus curated 241 m. |
| jersey | 103267, no year | Census 2021, 21 March | [Statistics Jersey](https://stats.je/statistic/total-population-census-2021/). Les Platons 143 m. Area 120.1 versus 119.5. |
| guernsey | 63950, no year | Published 2022 figure 63,950 | [Demographics of Guernsey](https://en.wikipedia.org/wiki/Demographics_of_Guernsey). That sentence is the bailiwick; almost all of it is the island, and the Channel Islands list tags the same 63,950 on Guernsey. Hautnez 110 m. Area 63.6 versus 63.4 km². |
| isle-of-man | 84069, no year | 2021 census total 84,069 | Matches the published census figure. Snaefell 621 m. Area 570.5 versus 572. |
| anglesey | 68900, no year | 2021 county census | ONS 68,878, stored rounded to 68,900. |
| osm-relation-6038068 Great Britain | 65121000 | Great Britain, not the UK | Order of magnitude is England + Wales + Scotland (UK minus Northern Ireland is about 65.1 million). Not Ireland, not a 10× error. Justified as the island. |
| osm-relation-7681896 Ireland | 7185600 | Island of Ireland, not the Republic alone | [List of islands by population](https://en.wikipedia.org/wiki/List_of_islands_by_population) gives 7,026,636 (2022) for the island. Stored 7,185,600 is about 2% higher and has no year. Right island, not confirmed as a false total. |
| staffa | summit Meall nan Gamhna 42 m | hill database and Wikipedia height | [graupel 10527](https://www.graupel.org.uk/hill_details.php?searchHill=10527) and [Staffa](https://en.wikipedia.org/wiki/Staffa) (42 m, uninhabited since 1800). `curated.json` name An Cròcan is the disagreement; the profile shows the hill-database name. Area 0.30 km² versus 33 ha is 9%; 33 ha / 82 acres is a rounded gazetteer pair, so the area was not confirmed as wrong. |
| lundy population | 28 | Wikipedia, 2007 | Held. Summit is the confirmed error above. |
| st-kilda population | 0 | evacuated 1930 | Held. |

`mainland-shetland` summit name **Rønnies Hill** at 450 m was not confirmed
as wrong. [Ronas Hill](https://en.wikipedia.org/wiki/Ronas_Hill) gives Ronas
Hill and the alias Rönies Hill, both 450 m. The stored spelling is that alias.

### Curated records not re-opened against a live page

These `islands.json` values were read and compared with `curated.json`.
No external page was opened in this pass, so they are not in confirmed or
held:

- `scilly-st-marys`: area 6.42 km² (audit: Wikidata 6.29, 2%), height 51 m
  with **no name** (curated still says Telegraph Hill), population 1,723.
- `rathlin`: area 14.45 versus curated 14.6, Slieveard 134 m, population 150.
- `iona` area 8.53 versus curated 8.77 (2.7%) and Dùn Ì 101 m. Population
  was checked (above).
- `brownsea`: area 2.08 versus curated 2.0, height 25 m unnamed, population 0.
- `lindisfarne` population 180 and Beblowe Crag 30 m. Area is under plausible.
- `inchcailloch`: area 0.53 versus curated 0.43, Tom na Nigheanan 85 m,
  population 0. No external area was found.
- `belle-isle-windermere`: area 0.154 versus Wikidata 0.154 in the audit,
  height 60 m unnamed, population 0.
- `eel-pie-island`: area 0.0378 versus curated 0.039, height 5 m, population 120.
- `isle-of-dogs`: area is null on the profile (`areaConfidence` n/a;
  curated still has 2.6). Height 10 m unnamed, a manual placeholder.
  Population 26,000 has no year and was not matched to a census table here.
- `burgh-island`: area 0.105, height 33 m unnamed, population 0. Matches curated.

### Same sample file, outside the population flag set

`census2022_nrs.csv` also stamped year 2022 onto Tiree (653), Coll (210),
Eigg (108), Rum (40), Canna (11) and Muck (32). Those are not curated and
are under 100,000, so they were not fact-checked one by one. The file header
says to replace it with the official NRS table before trusting it.
