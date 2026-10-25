# Interest filter ideas — 25 October 2026

Recommendation for the next atlas chips, after the ones already live.
Tidal islands was counted from the Wikipedia article and published locally
on 25 October 2026 (66 islands). The notes below are the brief that produced
that chip. Castle islets and lighthouses are still not populators.

Nothing else here is a populator, and nothing else here is published.

Live chips: Film, art and music; Whisky distilleries; For sale.
Already in harvest: unusual wildlife. Do not redesign it.
Already drafted and empty: `uninhabited-stay`. Leave it drafted. Do not
staff it in this round. A public place to stay, with no street address and
no owner name, is still missing.

A chip is one cited fact, with a source URL, on an island that already
exists. Open licences only. About 8 to 80 islands. No private addresses,
no owner names, no nest coordinates, no "when to visit".

## Build these three, one at a time

Finish publishing unusual wildlife first. Then:

### 1. Tidal walks

The English Wikipedia article [Tidal island](https://en.wikipedia.org/wiki/Tidal_island)
names the island as joined to other land at low tide and cut off at high tide.
That article is the source. There is no page called "List of tidal islands".

Do not use the atlas subtype `tidal`. That tag is on **256** islands and is
a classification, not a walk. Do not publish crossing times, a safe window,
or a private track. If the same article says a link is now a permanent
causeway, that island is out.

First action, before any populator: take the Britain, Ireland, Guernsey and
Jersey names on that page, match them to atlas ids, and keep a row only when
the sentence says the crossing floods. Stop if the keepers fall outside 8 to 80.
A book footnote on that page ("43 unbridged tidal islands") is Peter Caton,
*No Boat Required* (Troubador, 2011). Do not use the book, and do not treat
43 as our count.

### 2. Castle in the sea

The atlas area is under 1 km², and a Wikipedia article states that a castle
stands on that island. A castle on Skye or Mull does not qualify. A Martello
tower, a broch, and a fort do not qualify. Store the castle and the island,
not a living owner, a lease, or how to approach a private house.

`scripts/interest_categories.py` skips landmasses over 8,000 km² when it maps
Wikidata ids. It does not drop small islands. The artwork harvester does skip
areas under 1 km². Do not reuse that harvester for this chip.

Eight cited rows have not been counted yet. If the hand count falls under 8,
park the chip. Do not loosen the size rule to fill it.

### 3. Lighthouses

The lighthouse has its own English Wikipedia article, and that article places
the tower on the atlas island. Mark the row `not_for_navigation`. Do not store
a keeper's cottage or a light characteristic as if it were a pilot book.

Do not build this from the 16 May 2026 OSM join.

- `data/lighthouses_ingestion_report.json` (started 2026-05-16T09:35:58Z)
  records **238** islands with lights.
- The same morning's apply left a `lighthouses` array on **297** islands in
  `data/islands.json`, totalling **19,425** light rows.
- **19** of those islands each carry **603** lights, including Great Britain.
  **50 Peaks View** in Wales carries **602**. The first of those is a marker
  at 50.76068, 0.12183, which is the Beachy Head coast, not the Welsh island.
- **182** islands have exactly one light in that array. One light is still
  not a Wikipedia article. Recount from the articles before publishing.

## Parked

Worth a later chip. Not in this round.

| Chip | Why it waits |
| --- | --- |
| No visitor cars | The search notes already name "Scottish islands without a car". A half-true line (Iona has some vehicles) makes the chip a lie. Needs a dated page. |
| Iron-age brochs | Mousa and Dun Carloway are a clean Wikipedia test. The tap is specialist, and the Mousa article's storm-petrel counts must not be copied. |
| Island airfields | Barra and Papa Westray are real. It is a way of arriving, and ferry routes are still hidden for that reason. |
| Martello towers | Cork's fortification table and the Dalkey article can clear eight islands. Some towers are private houses. A weaker tap than a castle islet. |
| Monastic islands | Iona Abbey is a real citation. Graves, postcodes, and new access notes for Skellig Michael, Station Island and Inishmurray are too easy to copy in by mistake. |
| Books set here | Wikidata narrative location (P840), or the work's own article. "Inspired by" fails. A filmed novel stays on Film, art and music. The island count was not run. |

`uninhabited-stay` stays in the queue as an empty draft. It is not cancelled.
Nobody works it until a cited public stay exists.

## Do not build

| Idea | Why not |
| --- | --- |
| Bird observatories | About a dozen named sites. It becomes a second wildlife chip as soon as a species is added. Do not store warden contacts. |
| Island breeds | Soay, Boreray and Eriskay are real. Feral sheep belong on the wildlife chip, and a strict one-island origin rule may never clear eight. |
| Crannogs | Charming, and the source fails. Subtype `crannog` is **21** islands. **60** island names contain "crannog". Many recorded sites are no longer islands. Canmore grids are finer than this atlas should republish. |
| Had a railway | Alderney is the surprise. Wight, Man, Anglesey and Sheppey turn the chip into "large islands with a train". |
| Has a pub, or only one pub | OpenStreetMap lags closures. A pub on Wight swamps the small-island tap. No landlord, phone, or street. |
| Last residents left | The empty-island story already queued as `uninhabited-stay`. |
| Gaeltacht, or a Gaelic census share | Whole-island Gaeltacht status may fall under eight once Achill is excluded (only part of Achill is included). Census language cells for a small island can identify a person. |
| Reached by bridge | `docs/SEO-GEO-STRATEGY.md` names this as an editorial guide, not a filter. Thames footbridges blow the count. |
| Joined by causeway | Too easy to confuse with tidal walks and with bridges. |
| Standing stones | The loose heritage set blows past 80, and cairns drift into graves. |
| National Trust islands | Often a building or a length of coast, not the island. Lundy is the Landmark Trust. Owner rows are out. |
| Named for a saint | "St" is not a saint. St Kilda is the worked example. Fuzzy Irish names will attach the wrong person. |
| Own postage stamps | Lundy's puffin issues are real. The catalogues that list the rest are commercial. |
| Island Games | Archipelago teams, and only about seven single islands in range. |
| Puffin islands | The wildlife chip, narrowed to one species, which pushes the row toward colony counts. |
| Wild camp islands | The access right is not the same in each nation, and the chip reads as permission to land. |
| Prison islands, cruise calls, dark-sky islands, wrecks | Too few, no stable open list, or the wrong thing to map. |

## Ideas the team also brought

Kept here so a later session does not invent them again. They are not a
build queue.

Walk at low tide and castle islets and lighthouses are the three above.
The same passes also offered burial isles (Wikipedia already calls the island
a burial place; no grave coordinates; Iona, Inchcailloch, Eilean Munde),
volcanic islands (Staffa's article names Staffa, Ulva, and the Ardmeanach
basalt on Mull; lower quirk, and Staffa is already an artwork island),
and island quarries (Easdale's article names the slate workings; do not store
the current owner's name).

## How the five agents split

Three agents invented. Two judged.

- The editorial pass wanted, in order: tidal walks, castle in the sea, no
  visitor cars, island breeds, island airstrips.
- The source pass wanted: tidal walks, Martello towers, brochs, airfields.
  It rejected stamps, crannogs, Island Games, census Gaelic, wrecks, and
  ownership lists.
- The search pass wanted: tidal islands, lighthouses, castle islands,
  car-free islands. It said not to build puffin islands or wild-camp islands.
  Search Console was not readable in that pass (expired token). Every demand
  grade from that pass is an assumption. The strategy doc does name
  car-free islands, islands by bridge, and lighthouse islands. It mentions
  tidal island and crannog only inside a definitions sentence.

The red team said freeze every new chip until wildlife is published and the
stay draft is either filled or dropped. The focus coach said pause the stay
draft and ship tidal walks, then castle islets, then lighthouses, and that
the decision was already made.

This note follows the focus coach's order and the red team's gate on
wildlife, the hand count, and the lighthouse cache. It does not treat the
empty stay draft as a blocker, and it does not treat the order as something
that no longer needs a nod. The stay draft remains the harder chip. Tidal
walks is the one that can be counted from a single open page.
