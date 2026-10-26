# Location fact-check — 26 October 2026

Read-only check of where islands are placed: coordinates, nation, water type (sea / lake / river), and parent water body. Nothing in `data/islands.json` was edited.

Republic of Ireland is **Ireland** in this atlas. It is never rolled into the UK. Northern Ireland stays Northern Ireland.

## Counts

| | |
|---|---|
| Islands whose coordinates were compared with a cached Wikidata point | **2,559** named islands that have both a pin and a Wikidata id present in `data/cache_wd_islands.json` |
| Of those, within 5 km | **2,549** |
| Of those, over 5 km, each opened | **10** (none is a confirmed wrong pin; see below) |
| Curated islands reviewed | **27 / 27**, matched on id in `data/islands.json` |
| Validation-set rows (`docs/VALIDATION.md`) | **19**. **18** match type, nation, and parent. **1** parent mismatch (Wallasea) is not a wrong place |
| **Confirmed errors** | **156 islands** |
| **Suspicions** (not confirmed) | **18** |

The 156 are one bug in several places, not 156 bad pins. `nation_for()` in `scripts/fetch_islands.py` uses overlapping bounding boxes, checked in order. Scotland's box starts at 54.6°N and takes the Northumberland and Cumbrian coast. Wales's box runs to 2.65°W and takes the Somerset shore. Northern Ireland's box (54.0–55.4°N, 8.2–5.4°W) takes County Donegal, lakes in Leitrim, Cavan and Roscommon, and the Sanda group off Kintyre. Where a Wikidata coordinate was compared, the atlas pin was on the feature (usually under 0.5 km). The nation label is what is wrong.

## Confirmed errors

### 1. Northumberland and Tyne & Wear, tagged Scotland — 67

Every named feature below sits south of the Anglo-Scottish border. The border meets the North Sea at Marshall Meadows Bay, north of Berwick-upon-Tweed ([Anglo-Scottish border](https://en.wikipedia.org/wiki/Anglo-Scottish_border)). The southernmost pin in this set is 55.01°N (Tynemouth). The northernmost is Spittal, Berwick, at 55.77°N. Nothing in the 55.80–55.90°N band on this longitude was in the atlas, so the border itself is not in the list.

Sampled Wikidata administrations, all in England: Northumberland (Spittal Hirst), North Sunderland (the Farne Islands parish: Staple Island, Longstone, Big Harcar, Knivestone), Tyne and Wear (St Mary's Island, Whitley Bay), Ashington (Castle Island in the River Wansbeck). Coquet Island's article places it off Amble and in the parish of Hauxley, which covers the five Hauxley Nature Reserve lake islets. St Cuthbert's Isle and Old Law sit on Holy Island sands beside Lindisfarne. Lindisfarne itself is already England, because it is curated.

Field: `nation`. Site value: `Scotland`. Correct value: `England`. Distance: not a bad pin.

| id | name | lat, lng | source |
|---|---|---|---|
| `wd-Q24637553` | Spittal Hirst | 55.76667, -1.85000 | https://www.wikidata.org/wiki/Q24637553 |
| `wd-Q24641671` | Inner Hirst | 55.75000, -1.86667 | https://en.wikipedia.org/wiki/Anglo-Scottish_border |
| `wd-Q24638971` | Outer Tours | 55.73333, -1.83333 | https://en.wikipedia.org/wiki/Anglo-Scottish_border |
| `wd-Q24639860` | Park Dyke | 55.71667, -1.81667 | https://en.wikipedia.org/wiki/Anglo-Scottish_border |
| `wd-Q24636775` | Wingate Reef | 55.71667, -1.83333 | https://en.wikipedia.org/wiki/Anglo-Scottish_border |
| `riding-stone` | Riding Stone | 55.66874, -1.78990 | https://en.wikipedia.org/wiki/Lindisfarne |
| `willy-potts-rock` | Willy Pott's Rock | 55.66852, -1.79359 | https://en.wikipedia.org/wiki/Lindisfarne |
| `osm-way-26723926` | St. Cuthbert's Isle | 55.66786, -1.80595 | https://en.wikipedia.org/wiki/Lindisfarne |
| `wd-Q24641355` | Guzzard | 55.66667, -1.71667 | https://en.wikipedia.org/wiki/Lindisfarne |
| `wd-Q3881514` | Old Law | 55.65000, -1.78750 | https://en.wikipedia.org/wiki/Lindisfarne |
| `wd-Q24638006` | Tree o' the House | 55.65000, -1.71667 | https://en.wikipedia.org/wiki/Lindisfarne |
| `wd-Q24640149` | Knivestone | 55.64975, -1.60177 | https://en.wikipedia.org/wiki/Farne_Islands |
| `osm-way-61921338` | Northern Hares | 55.64606, -1.61112 | https://en.wikipedia.org/wiki/Farne_Islands |
| `osm-way-61921346` | Humber Rock | 55.64436, -1.61159 | https://en.wikipedia.org/wiki/Farne_Islands |
| `osm-way-61921366` | Longstone | 55.64393, -1.60844 | https://en.wikipedia.org/wiki/Farne_Islands |
| `osm-way-61921362` | Little Harcar | 55.64023, -1.61732 | https://en.wikipedia.org/wiki/Farne_Islands |
| `osm-way-61921352` | Blue Caps | 55.64014, -1.61157 | https://en.wikipedia.org/wiki/Farne_Islands |
| `osm-way-61921337` | Big Harcar | 55.63945, -1.62104 | https://en.wikipedia.org/wiki/Farne_Islands |
| `osm-way-61921367` | North Wamses | 55.63942, -1.62953 | https://en.wikipedia.org/wiki/Farne_Islands |
| `osm-way-61921365` | The Sandbags | 55.63905, -1.62575 | https://en.wikipedia.org/wiki/Farne_Islands |
| `osm-way-61921369` | South Wamses | 55.63742, -1.62797 | https://en.wikipedia.org/wiki/Farne_Islands |
| `osm-way-61921361` | Roddam and Green | 55.63664, -1.62467 | https://en.wikipedia.org/wiki/Farne_Islands |
| `osm-way-3121406` | Brownsman | 55.63384, -1.62373 | https://en.wikipedia.org/wiki/Farne_Islands |
| `wd-Q33171886` | Elbow | 55.63333, -1.66667 | https://en.wikipedia.org/wiki/Farne_Islands |
| `wd-Q24637813` | Swedman | 55.63333, -1.68333 | https://en.wikipedia.org/wiki/Farne_Islands |
| `osm-relation-3077274` | Staple Island | 55.63063, -1.62398 | https://en.wikipedia.org/wiki/Farne_Islands |
| `osm-relation-3077273` | Megstone | 55.62929, -1.67467 | https://en.wikipedia.org/wiki/Farne_Islands |
| `osm-way-61921802` | Crumstone | 55.62737, -1.59842 | https://en.wikipedia.org/wiki/Farne_Islands |
| `osm-way-61921371` | Solan Rock | 55.62005, -1.65465 | https://en.wikipedia.org/wiki/Farne_Islands |
| `osm-way-61921344` | Little Scarcar | 55.61800, -1.63994 | https://en.wikipedia.org/wiki/Farne_Islands |
| `osm-way-61921339` | Big Scarcar | 55.61716, -1.63974 | https://en.wikipedia.org/wiki/Farne_Islands |
| `osm-way-61921353` | West Wideopen | 55.61695, -1.64786 | https://en.wikipedia.org/wiki/Farne_Islands |
| `osm-relation-3077272` | Inner Farne | 55.61670, -1.65540 | https://en.wikipedia.org/wiki/Farne_Islands |
| `osm-way-61921350` | East Wideopen | 55.61652, -1.64359 | https://en.wikipedia.org/wiki/Farne_Islands |
| `wd-Q24641716` | Islestone | 55.60000, -1.68333 | https://en.wikipedia.org/wiki/Farne_Islands |
| `wd-Q24649313` | Dicky Shad | 55.56667, -1.56667 | https://en.wikipedia.org/wiki/Farne_Islands |
| `wd-Q24638796` | Newton Skere | 55.56667, -1.48333 | https://en.wikipedia.org/wiki/Farne_Islands |
| `wd-Q24656421` | Barnyard Reef | 55.53333, -1.60000 | https://en.wikipedia.org/wiki/Farne_Islands |
| `wd-Q24652070` | Craster Skeres | 55.48333, -1.43333 | https://en.wikipedia.org/wiki/Farne_Islands |
| `wd-Q24654295` | Boulmer Bush | 55.41667, -1.56667 | https://en.wikipedia.org/wiki/Farne_Islands |
| `wd-Q24654297` | Boulmer Stile | 55.40000, -1.56667 | https://en.wikipedia.org/wiki/Farne_Islands |
| `wd-Q24656798` | Birling Carrs | 55.36400, -1.60000 | https://en.wikipedia.org/wiki/Farne_Islands |
| `wd-Q24639018` | Pan Rocks | 55.33700, -1.56888 | https://en.wikipedia.org/wiki/Farne_Islands |
| `wd-Q2755722` | Coquet Island | 55.33500, -1.53900 | https://en.wikipedia.org/wiki/Coquet_Island |
| `wd-Q24656915` | Bondicarr Bush | 55.31667, -1.51667 | https://en.wikipedia.org/wiki/Farne_Islands |
| `osm-way-145174776` | Island 1 | 55.31372, -1.55515 | https://en.wikipedia.org/wiki/Coquet_Island |
| `osm-way-145174780` | Island 2 | 55.31300, -1.55414 | https://en.wikipedia.org/wiki/Coquet_Island |
| `osm-way-145174778` | Island 3 | 55.31209, -1.55378 | https://en.wikipedia.org/wiki/Coquet_Island |
| `osm-way-145174779` | Island 4 | 55.31162, -1.55524 | https://en.wikipedia.org/wiki/Coquet_Island |
| `osm-way-145174777` | Island 5 | 55.31139, -1.55594 | https://en.wikipedia.org/wiki/Coquet_Island |
| `wd-Q24645889` | Elm Bush | 55.30780, -1.55102 | https://en.wikipedia.org/wiki/Farne_Islands |
| `wd-Q24638828` | Northern Hill | 55.30000, -1.53333 | https://en.wikipedia.org/wiki/Farne_Islands |
| `wd-Q24652091` | Cresswell Skeres | 55.25000, -1.51667 | https://en.wikipedia.org/wiki/Farne_Islands |
| `wd-Q24657174` | Blackdyke | 55.20000, -1.48333 | https://en.wikipedia.org/wiki/Farne_Islands |
| `wd-Q137756430` | Castle Island | 55.16350, -1.55900 | https://en.wikipedia.org/wiki/Castle_Island,_England |
| `osm-way-3121034` | Castle Island | 55.16334, -1.55752 | https://en.wikipedia.org/wiki/Castle_Island,_England |
| `wd-Q24637522` | South Spit | 55.13333, -1.48333 | https://en.wikipedia.org/wiki/Farne_Islands |
| `wd-Q24638857` | North Spit | 55.13306, -1.49944 | https://en.wikipedia.org/wiki/Farne_Islands |
| `wd-Q24638503` | Seaton Sea Rocks | 55.11667, -1.46667 | https://en.wikipedia.org/wiki/Farne_Islands |
| `wd-Q24651800` | Colville Rock | 55.08333, -1.46667 | https://en.wikipedia.org/wiki/Farne_Islands |
| `wd-Q24641666` | Inner Bell Rock | 55.08333, -1.45000 | https://en.wikipedia.org/wiki/Farne_Islands |
| `old-hartley-standing-stone` | Old Hartley Standing Stone | 55.07288, -1.46748 | https://en.wikipedia.org/wiki/Farne_Islands |
| `wd-Q7594502` | St Mary's Island | 55.07167, -1.44972 | https://en.wikipedia.org/wiki/St_Mary%27s_Island_(Tyne_and_Wear) |
| `wd-Q24658754` | Brierdean Bushes | 55.05806, -1.44083 | https://en.wikipedia.org/wiki/Farne_Islands |
| `wd-Q24636755` | Whitley Shad | 55.04611, -1.41083 | https://en.wikipedia.org/wiki/Farne_Islands |
| `wd-Q24656498` | Bellhues Rocks | 55.03667, -1.41250 | https://en.wikipedia.org/wiki/Farne_Islands |
| `wd-Q27627601` | Black Middens | 55.01230, -1.42170 | https://en.wikipedia.org/wiki/Farne_Islands |

### 2. Cumbrian Solway and the River Eden, tagged Scotland — 5

Field: `nation`. Site value: `Scotland`. Correct value: `England`. Hestan Island, Rough Island at Kippford, and Little Ross stay Scotland; they were checked and are right.

| id | name | correction | source |
|---|---|---|---|
| `wd-Q24657162` | Beckfoot | Reef or shore at Beckfoot, parish of Holme St Cuthbert, Cumbria, on the English Solway. Not Scotland. | https://en.wikipedia.org/wiki/Beckfoot |
| `osm-way-527570894` | Buckholme Island | River island in the River Eden, which flows through Cumbria to the Solway. Parent water River Eden is right. | https://en.wikipedia.org/wiki/River_Eden,_Cumbria |
| `osm-way-1260658988` | Little Corby Island | River island at Little Corby, a village in Cumbria beside the Eden, east of Carlisle. Parent water River Eden is right. | https://en.wikipedia.org/wiki/Little_Corby |
| `big-island-w29471565` | Big Island | Lake islet at 54.634°N, 2.655°W, in the Eden valley south of Carlisle. The border does not come this far south. | https://en.wikipedia.org/wiki/Anglo-Scottish_border |
| `little-island-w31028733` | Little Island | Same lake as Big Island, a few tens of metres away. England. | https://en.wikipedia.org/wiki/Anglo-Scottish_border |

### 3. Somerset shore of the Bristol Channel, tagged Wales — 4

This is the Knightstone bug in the queue. Field: `nation`. Site value: `Wales`. Correct value: `England`.

Do not 'correct' the Welsh islands in the same channel. Flat Holm (Butetown, Cardiff), Sully Island (Vale of Glamorgan), Barry Island, and Denny Island (Monmouthshire above high water; the southern foreshore is the boundary) are Wales and are right.

| id | name | correction | source |
|---|---|---|---|
| `wd-Q125365707` | Knightstone Island | England (Weston-super-Mare). Wikidata admin is Weston-Super-Mare. | https://www.wikidata.org/wiki/Q125365707 |
| `wd-Q125365684` | Birnbeck Island | England (Weston-super-Mare, North Somerset). | https://en.wikipedia.org/wiki/Birnbeck_Pier |
| `osm-way-30782387` | Steep Holm | England (North Somerset). Flat Holm, nearby, is the Welsh one. | https://en.wikipedia.org/wiki/Steep_Holm |
| `wd-Q24658725` | Langford Grounds | England. Shoal on the Somerset shore, about 6 km north of Birnbeck. Wikidata has no county, but the point is on that shore. | https://www.wikidata.org/wiki/Q24658725 |

Knightstone's parent text 'Weston-super-Mare seafront' matches the place. Steep Holm's water is the Bristol Channel. Type `sea` is right for all four.

### 4. Kintyre, tagged Northern Ireland or Ireland — 5

Field: `nation`. Correct value: `Scotland`.

| id | name | site | correction | source |
|---|---|---|---|---|
| `osm-relation-10323151` | Davaar Island | Ireland | Scotland (Argyll and Bute), mouth of Campbeltown Loch. Site says Ireland. | https://en.wikipedia.org/wiki/Island_Davaar |
| `osm-way-376949973` | Sanda | Northern Ireland | Scotland (Argyll and Bute), off Southend, Kintyre. Site says Northern Ireland. | https://en.wikipedia.org/wiki/Sanda_Island |
| `osm-way-376949974` | Sheep Island | Northern Ireland | Scotland, beside Sanda. Site says Northern Ireland. Wikidata admin is Argyll and Bute. | https://en.wikipedia.org/wiki/Glunimore_Island |
| `osm-way-4006840` | Glunimore Island | Northern Ireland | Scotland, beside Sanda. Site says Northern Ireland. | https://en.wikipedia.org/wiki/Glunimore_Island |
| `osm-node-530980959` | Paterson's Rock | Northern Ireland | Scotland. Rock beside Sanda (about 2.5 km east). No Wikidata id. Site says Northern Ireland. | https://en.wikipedia.org/wiki/Sanda_Island |

### 5. Pembrokeshire, tagged Ireland — 5

Field: `nation`. Site value: `Ireland`. Correct value: `Wales`. These are west of 5.4°W, so they miss the Wales box and fall in the Ireland box. They are not in Ireland.

| id | name | correction | source |
|---|---|---|---|
| `osm-way-27013704` | Grassholm | Wales (Pembrokeshire). Site says Ireland. Pin matches Wikidata (0.04 km). | https://en.wikipedia.org/wiki/Grassholm |
| `osm-way-1493746561` | West Tump | Wales. Unnamed in Wikidata; the pin is 0.2 km from Grassholm. | https://en.wikipedia.org/wiki/Grassholm |
| `osm-relation-3009841` | South Bishop | Wales (Pembrokeshire), west of Ramsey. Sister rocks Daufraich and Moelyn are already Wales. | https://en.wikipedia.org/wiki/Bishops_and_Clerks |
| `wd-Q24657075` | Barrels | Wales. Reef southwest of Grassholm, not an Irish island. Pin matches Wikidata. | https://en.wikipedia.org/wiki/Grassholm |
| `wd-Q24641433` | Hats | Wales. Reef west of Grassholm. Pin matches Wikidata. | https://en.wikipedia.org/wiki/Grassholm |

### 6. County Donegal coast and Lough Swilly, tagged Northern Ireland — 13

Field: `nation`. Site value: `Northern Ireland`. Correct value: `Ireland`. Pins match the Wikidata points. Inishtrahull, Tory Island, Arranmore, and Cruit Island are already Ireland and were left alone.

| id | name | correction | source |
|---|---|---|---|
| `osm-way-4558730` | Glashedy Island | Ireland (County Donegal), off Malin Head. | https://en.wikipedia.org/wiki/Glashedy |
| `osm-relation-5497270` | Inch | Ireland (County Donegal). Also set parent water to Lough Swilly; it is empty. Type sea is fair for the sea lough. | https://en.wikipedia.org/wiki/Inch_Island |
| `osm-way-4558430` | Inishbofin | Ireland (County Donegal), off Magheraroarty. The Galway Inishbofin is a different record and is already Ireland. | https://en.wikipedia.org/wiki/Inishbofin,_County_Donegal |
| `osm-relation-11619444` | Inishdooey | Ireland (County Donegal), just north of Inishbofin. | https://en.wikipedia.org/wiki/Inishdooey |
| `osm-way-4559909` | Ballyboyle Island | Ireland. Wikidata country Ireland, admin County Donegal. Pin within 0.2 km. | https://www.wikidata.org/wiki/Q26718245 |
| `wd-Q26717163` | Croaghan Island | Ireland. Wikidata country Ireland, admin County Donegal. | https://www.wikidata.org/wiki/Q26717163 |
| `wd-Q26717191` | Duncap Isle | Ireland. Wikidata country Ireland, admin County Donegal. | https://www.wikidata.org/wiki/Q26717191 |
| `osm-way-4558951` | Inishbeg | Ireland. Wikidata country Ireland, admin County Donegal. | https://www.wikidata.org/wiki/Q26715850 |
| `osm-way-4559046` | Island Roy | Ireland. Wikidata country Ireland (Oileán Ruaidh), Atlantic. Pin on the Donegal shore. | https://www.wikidata.org/wiki/Q7081481 |
| `osm-way-4558415` | Clonmass Island | Ireland. Same coordinates as Wikidata 'Little Island', country Ireland. Admin 'Ards' is Ards Forest Park, County Donegal, not the Ards in County Down. Display name may not match the Wikidata label. | https://en.wikipedia.org/wiki/Ards_Forest_Park |
| `osm-way-835031691` | Rabbit Island | Ireland. Wikidata calls the same point Inishyweel, country Ireland, admin Cranford (Donegal). Display name is Rabbit Island. | https://www.wikidata.org/wiki/Q104350678 |
| `osm-way-4559198` | Rough Island | Ireland. Wikidata calls the same point Long Island, country Ireland, admin Milford (Donegal). Display name is Rough Island. | https://www.wikidata.org/wiki/Q104350716 |
| `osm-way-4559951` | Rooney's Island | Ireland. Wikidata country Ireland. Pin within 0.1 km, Donegal Bay. | https://www.wikidata.org/wiki/Q26718248 |

### 7. Lough Allen, tagged Northern Ireland — 16

The whole lake is in County Leitrim and County Roscommon ([Lough Allen](https://en.wikipedia.org/wiki/Lough_Allen)). Field: `nation`. Site value: `Northern Ireland`. Correct value: `Ireland`. Parent water Lough Allen is right. Type `lake` is right. Live Wikidata checks: Corry Island and Drummans Island and Inishmagrath (County Leitrim), O'Reilly's Island (County Roscommon).

| id | name |
|---|---|
| `osm-way-814326891` | "Jenny's Island" |
| `osm-way-207529521` | Corry Island |
| `osm-way-1327471955` | Corry Shoal |
| `osm-way-322267458` | Drummans Island |
| `osm-way-1106942090` | Fahy Island |
| `osm-way-1106942089` | Fahy Rock |
| `osm-way-816432968` | Gull Island |
| `osm-way-816432969` | Gull Rock |
| `osm-way-1327471956` | Holy island |
| `osm-relation-7169522` | Inishmacgrath |
| `osm-way-231229702` | Inishmagrath |
| `osm-way-1081419180` | Long Island |
| `wd-Q26717915` | O'Reilly's Island |
| `osm-way-1105379439` | Round Island |
| `osm-way-1094318119` | Spiranthes Islands |
| `osm-way-1081419179` | The Spit |

### 8. Garadice Lough, County Leitrim, tagged Northern Ireland — 3

The lake is in County Leitrim ([Garadice Lough](https://en.wikipedia.org/wiki/Garadice_Lough)). Field: `nation`. Correct value: `Ireland`. Cherry Island and Church Island were checked live (County Leitrim, pins within 0.1 km). Crane Island is the same lake.

| id | name |
|---|---|
| `osm-way-186289752` | Cherry Island |
| `osm-way-6957984` | Church Island |
| `osm-way-186289751` | Crane Island |

### 9. Lough Oughter, County Cavan, tagged Northern Ireland — 4

The lakes are in County Cavan ([Lough Oughter](https://en.wikipedia.org/wiki/Lough_Oughter)). Field: `nation`. Correct value: `Ireland`. Eonish and the Inch Island in this lake were checked live (County Cavan).

| id | name |
|---|---|
| `osm-way-1102225963` | Buck Island |
| `wd-Q26717992` | Eonish |
| `osm-way-182626259` | Inch Island |
| `osm-way-767535808` | Stony Island |

### 10. Lough Eske, County Donegal, tagged Northern Ireland — 6

The lake is northeast of Donegal Town ([Lough Eske](https://en.wikipedia.org/wiki/Lough_Eske)). Field: `nation`. Correct value: `Ireland`. O'Donnell's Island was checked live (Wikidata country Ireland).

| id | name |
|---|---|
| `osm-way-1033855557` | Grania's Island |
| `osm-way-1033855559` | Moylederg Island |
| `osm-way-1033855558` | Pigeon's Island |
| `osm-way-467589924` | Roshin Island |
| `osm-way-1033855560` | Round Island |
| `osm-way-467586333` | Ò' Donnell's Island |

### 11. Lough Derg, County Donegal, tagged Northern Ireland — 16

This is the pilgrimage lough at about 54.61°N, 7.87°W, not the Shannon lake of the same name. Station Island is St Patrick's Purgatory, County Donegal ([St Patrick's Purgatory](https://en.wikipedia.org/wiki/St_Patrick%27s_Purgatory)). Wikidata country for Station Island, Boat Island, Derg Beg, Derg More, Inishgoosk, and Saints Island is Ireland. Admins Pettigo and Templecarn are the Donegal side. The Shannon Lough Derg islands further south are already `Ireland` and are not in this list.

Field: `nation`. Site value: `Northern Ireland`. Correct value: `Ireland`. Parent water Lough Derg is the right lake. Allingham's Island carries a Wikidata id whose label is Station Island; the pin is 0.5 km from that point, and a separate Station Island record is also here. Both nations are wrong. The display name was not treated as a confirmed error.

| id | name |
|---|---|
| `osm-way-112156376` | Allingham's Island |
| `osm-way-112156370` | Ash Island |
| `osm-way-306303592` | Ash Islands |
| `osm-relation-4087461` | Boat Island |
| `osm-way-112156369` | Bulls Island |
| `osm-relation-4087462` | Derg Beg Island |
| `osm-relation-4087463` | Derg More Island |
| `osm-way-112156375` | Derry Beg Island |
| `osm-way-112156371` | Derry More Island |
| `osm-way-109722657` | Friar's Island |
| `osm-relation-4087466` | Inishgoosk |
| `osm-way-109728511` | Kelly's Isles |
| `osm-way-112156380` | Philipboy Island |
| `osm-relation-4087468` | Saints Island |
| `osm-way-106592833` | Station Island |
| `osm-way-112156377` | Trough Island |

Ranaghmore Island (`wd-Q104348087`) is the one Lough Swilly record whose parent is already set. Nation on the site is Northern Ireland. Wikidata country is Ireland. Correct nation: Ireland. Source: https://www.wikidata.org/wiki/Q104348087

### 12. Two Lough Melvin islands on the Leitrim side — 2

Lough Melvin is split between County Leitrim and County Fermanagh ([Lough Melvin](https://en.wikipedia.org/wiki/Lough_Melvin)). Only the islands Wikidata places in Ireland are confirmed. Inishmean and Inisheher are already Ireland.

| id | name | site | correct | source |
|---|---|---|---|---|
| `osm-way-127628516` | Inishkeen | Northern Ireland | Ireland (County Leitrim). Parent Lough Melvin is right. | https://www.wikidata.org/wiki/Q26717851 |
| `osm-way-127628517` | Inishtemple | Northern Ireland | Ireland (County Leitrim). Parent Lough Melvin is right. | https://www.wikidata.org/wiki/Q26717852 |

### 13. MacNean, Inishmuck, and Inishnagon — 4

| id | name | site | correct | source |
|---|---|---|---|---|
| `osm-way-274965315` | Trawnish Island | Northern Ireland | Ireland. Upper Lough MacNean. Wikidata country Ireland. Parent lake is right. Inishteige, in the same lake, is Fermanagh and is correctly Northern Ireland. | https://www.wikidata.org/wiki/Q104326846 |
| `osm-way-179021429` | Tuam Island | Northern Ireland | Ireland (County Cavan). Upper Lough MacNean. | https://www.wikidata.org/wiki/Q26717849 |
| `osm-way-367724521` | Inishmuck | Northern Ireland | Ireland (County Cavan). Parent Inishmuck Lough is right. | https://www.wikidata.org/wiki/Q26717994 |
| `osm-way-369604216` | Inishnagon | Northern Ireland | Ireland (County Leitrim). | https://www.wikidata.org/wiki/Q104326253 |

### 14. Not an English sea island: Greenisland — 1

| id | name | wrong fields | site | correct | source |
|---|---|---|---|---|---|
| `csv-geocoded-Q1375188` | Greenisland | `nation`, `type` | England, sea, parent Belfast Lough | The pin is the town of Greenisland, County Antrim, on the shore of Belfast Lough. Nation Northern Ireland. It is not a sea island. The town is named after a separate tiny islet. | https://en.wikipedia.org/wiki/Greenisland |

### 15. Peninsula typed as a sea island: Island Magee — 1

| id | name | field | site | correct | source |
|---|---|---|---|---|---|
| `wd-Q24639396` | Island Magee | `type` | sea (nation Northern Ireland is right) | Peninsula between Larne Lough and the North Channel, County Antrim. Not a sea island. | https://en.wikipedia.org/wiki/Islandmagee |

### 16. Curated lake and river islands with no parent water — 3

Coordinates, nation, and water type are right. The parent field is empty. Belle Isle is not in this list: the validation set expects a null parent, and the water body is in the name.

| id | name | field | site | correct | distance to Wikidata | source |
|---|---|---|---|---|---|---|
| `inchcailloch` | Inchcailloch | `parentWaterBody` | null (type lake, nation Scotland) | Loch Lomond | 1.5 km, still the south end of the loch, under the 5 km bar | https://en.wikipedia.org/wiki/Inchcailloch |
| `eel-pie-island` | Eel Pie Island | `parentWaterBody` | null (type river, nation England) | River Thames, Twickenham | 0.3 km | https://en.wikipedia.org/wiki/Eel_Pie_Island |
| `isle-of-dogs` | Isle of Dogs | `parentWaterBody` | null (type river, nation England) | River Thames | 0.5 km | https://en.wikipedia.org/wiki/Isle_of_Dogs |

Isle of Dogs is a peninsula in a Thames meander, not a sea island. The atlas already has it as `river`, not `sea`. That part of the check is clean. The missing parent is the gap.

### Recount

67 + 5 + 4 + 5 + 5 + 13 + 16 + 3 + 4 + 6 + 16 + 1 (Ranaghmore) + 2 + 2 + 2 (Inishmuck, Inishnagon) + 1 + 1 + 3 = **156**.

## Suspicions

Not confirmed. Do not treat these as fixes.

1. **Corn Holm in Shetland** (`osm-way-183405659`, 60.275°N, 1.132°W) shares Wikidata Q1747849 with the real Corn Holm in Orkney. The points are 176 km apart. The Orkney record `osm-way-1306666573` matches [Corn Holm](https://en.wikipedia.org/wiki/Corn_Holm) within 0.2 km. The Shetland pin may be a different holm with the wrong id, not the Orkney island drawn in the wrong place.
2. **Uyea, Unst** (`osm-way-8603690`, 60.670°N, 0.898°W) is linked to [Uyea, Northmavine](https://en.wikipedia.org/wiki/Uyea,_Northmavine) (Q7904154), 29 km away. The Northmavine record `osm-relation-9319278` is 0.6 km from that point. A third record, `csv-geocoded-Q282210`, is [Uyea, Unst](https://www.wikidata.org/wiki/Q282210) and sits on the Unst island. The Unst OSM way is in the right place with the wrong Wikidata id.
3. **Oronsay** (`osm-way-1063002533`, 57.668°N, 7.414°W) is 7.4 km from [Oronsay, Outer Hebrides](https://en.wikipedia.org/wiki/Oronsay,_Outer_Hebrides) (Q3139569). The OSM islet is only 0.06 km², so this is a different Oronsay, not a 7 km slip of one pin.
4. **Lewis and Harris is in twice.** `lewis-and-harris` and `osm-relation-7220346` share Q363778 and the same area (about 2,149 km²). The pins are 11.5 km apart, both on the island. Wikidata's point is 7.9 km and 14.4 km from them. That spread is normal on an island this size.
5. **Mainland Shetland is in twice.** `mainland-shetland` ('Mainland (Shetland)', 60.30°N, 1.30°W) and `osm-relation-376677` (named 'Shetland', 60.245°N, 1.377°W) share Q738734 and the same area (about 953 km²). Both pins are on Mainland. The second name is the archipelago's name on the main island's geometry.
6. **Inner Farne's Wikidata label is House Island.** `osm-relation-3077272` is 80 m from Q62130277, which is labelled House Island. The nation error (Scotland → England) is already in the confirmed list. The name was not confirmed as wrong.
7. **Welsh Hook** (`wd-Q24636643`, 51.50°N, 2.92°W), nation Wales, Wikidata instance shoal, no county. It sits in the Bristol Channel between the Somerset shore and the Welsh shore. Not assigned.
8. **Black Rock** (`osm-way-457907632`, 51.311°N, 2.997°W), nation Wales, type river, parent Severn Estuary. The point is just south of Brean Down, on the English side of the channel. Likely England. Not confirmed without a source that names this rock.
9. **Upper Severn rocks**, nation Wales: Goblin Ledge (`goblin-ledge`), Old Man's Head (`old-mans-head`), Red Ledge (`red-ledge`), The Bull (`the-bull`), around 51.57°N, 2.67°W. The boundary here is the channel. Not assigned.
10. **The Wolves** (`wd-Q2100283`), nation Wales, beside Flat Holm. Probably Wales. Wikidata has no county, and the article was not opened. Left unverified rather than confirmed.
11. **Rabbit Island** (`rabbit-island-w134156897`, 55.011°N, 3.262°W), nation Scotland, type river. This is the Annan side of the inner Solway, not Beckfoot. Probably Scotland. Not confirmed as an error.
12. **Rough Island, Lough Foyle** (`osm-way-813176103`, 55.021°N, 7.263°W), nation Northern Ireland, parent Lough Foyle. The lough is disputed water. No nation was assigned.
13. **Other Lough Melvin islands still tagged Northern Ireland**, including Gorminish (`osm-way-179073597`). The lake is on the border. Only Inishkeen and Inishtemple were confirmed as Leitrim.
14. **Other Upper and Lower Lough MacNean islands** still tagged Northern Ireland, apart from Trawnish and Tuam (confirmed Ireland) and Inishteige (confirmed Northern Ireland, Fermanagh and Omagh).
15. **Cormorant Rock** (`osm-way-529190905`, 54.079°N, 10.159°W), nation Ireland, off Achill. The coordinates are in Mayo. Its Wikidata id Q5171004 was in the UK slice of the local island cache. The nation may be right and the link wrong. Not opened live.
16. **Thorney Island, Chichester Harbour** (`wd-Q4575689`, 50.817°N, 0.920°W), type sea, parent Chichester Harbour, nation England. This is the West Sussex peninsula, not the removed school. Whether `sea` is fair for a peninsula was not settled from a source this session.
17. **Great Britain** (`osm-relation-6038068`) and **Ireland** (`osm-relation-7681896`) are the two mainlands, typed `sea`. Their pins (54.9 km and 7.5 km from the Wikidata points) sit on the landmasses. Not a mis-pin. Whether they belong in an island atlas is a scope question.
18. **Peel Castle** (`csv-geocoded-Q31118312`, 54.227°N, 4.699°W) uses nation `Isle of Man` rather than `Crown Dependency`. The place is Peel, on the Isle of Man. That is not a wrong country. It may be the castle rather than St Patrick's Isle. Not confirmed as a location error.

Display names that disagree with a Wikidata label, on islands whose **nation** is already confirmed: Clonmass Island vs Little Island, Rabbit Island vs Inishyweel, Rough Island vs Long Island, Allingham's Island vs a Station Island id. The pins are on the Donegal features. The names were not confirmed as wrong.

## Checked and found correct

### Curated 27

All 27 ids in `data/curated.json` are the same ids in `data/islands.json`. Name, nation, type, and coordinates match the curated file. Five were not in the coordinate cache and were checked live against Wikidata P625.

| id | nation | type | vs Wikidata | note |
|---|---|---|---|---|
| `isle-of-skye` | Scotland | sea | 7.4 km | Both points are on Skye (1,636 km²). Not an error. |
| `lewis-and-harris` | Scotland | sea | 7.9 km | Both points are on Lewis and Harris. A second pin exists; see suspicions. |
| `mainland-orkney` | Scotland | sea | 3.8 km | On Mainland, Orkney. |
| `mainland-shetland` | Scotland | sea | 0.0 km | Matches the Wikidata point. A duplicate pin exists; see suspicions. |
| `mull` | Scotland | sea | 3.1 km | On Mull. |
| `islay` | Scotland | sea | 4.0 km | On Islay. |
| `arran` | Scotland | sea | 1.8 km | On Arran. |
| `bute` | Scotland | sea | 3.4 km | On Bute. |
| `iona` | Scotland | sea | 0.0 km | |
| `staffa` | Scotland | sea | 0.7 km | |
| `isle-of-man` | Crown Dependency | sea | 1.5 km | Live. Country is the Isle of Man, not the UK. Schema value Crown Dependency is right. |
| `anglesey` | Wales | sea | 3.2 km | On Anglesey. |
| `isle-of-wight` | England | sea | 1.6 km | |
| `scilly-st-marys` | England | sea | 0.6 km | St Mary's. |
| `lundy` | England | sea | 0.2 km | England, not the Wales box. |
| `rathlin` | Northern Ireland | sea | 0.03 km | County Antrim. [Rathlin Island](https://en.wikipedia.org/wiki/Rathlin_Island). |
| `jersey` | Crown Dependency | sea | 3.1 km | Live. Bailiwick of Jersey. Not England and not UK. [Jersey](https://en.wikipedia.org/wiki/Jersey). |
| `guernsey` | Crown Dependency | sea | 1.2 km | Live. [Guernsey](https://en.wikipedia.org/wiki/Guernsey). |
| `brownsea` | England | sea | 0.8 km | Poole Harbour. |
| `lindisfarne` | England | sea | 0.1 km | The curated override held. Neighbours in section 1 did not. |
| `fair-isle` | Scotland | sea | 0.6 km | Between Shetland and Orkney. [Fair Isle](https://en.wikipedia.org/wiki/Fair_Isle). |
| `st-kilda` | Scotland | sea | 0.6 km | Live. Display name St Kilda (Hirta). Wikidata is the archipelago at the same point. [St Kilda, Scotland](https://en.wikipedia.org/wiki/St_Kilda,_Scotland) was requested; the coordinate and admin (Harris, Outer Hebrides) are the check. |
| `inchcailloch` | Scotland | lake | 1.5 km | Right loch. Parent empty: confirmed above. |
| `belle-isle-windermere` | England | lake | 0.7 km | Windermere. Parent is null, which is what the validation set requires. The water body is in the name. [Belle Isle (Windermere)](https://en.wikipedia.org/wiki/Belle_Isle_(Windermere)). |
| `eel-pie-island` | England | river | 0.3 km | Thames ait. Parent empty: confirmed above. Not a sea island. |
| `isle-of-dogs` | England | river | 0.5 km | Peninsula, and the atlas does not call it a sea island. Parent empty: confirmed above. [Isle of Dogs](https://en.wikipedia.org/wiki/Isle_of_Dogs). |
| `burgh-island` | England | sea | 0.04 km | Tidal island, South Devon. [Burgh Island](https://en.wikipedia.org/wiki/Burgh_Island). |

### Validation set

Programmatic check of type, nation, and parent against `docs/VALIDATION.md`:

- Match: Isle of Skye, Isle of Wight, Isle of Man, Lundy, Anglesey, Mull, Rathlin, Lewis and Harris, Belle Isle (Windermere), Barra (`osm-relation-380646`), South Uist (`osm-relation-380670`), North Uist (`osm-relation-380685`), Jura (`osm-relation-4619204`), Tiree (`osm-relation-6045455`), Achill (`osm-relation-6045364`, nation Ireland), Devenish (`osm-relation-3998376`, Lower Lough Erne), Boa (`osm-relation-3512150`, Lower Lough Erne), Innisfallen (`osm-way-26526918`, Lough Leane, Ireland).
- Wallasea (`osm-way-403472785`): type `sea` and nation `England` match. Parent is `Crouch / Roach Estuaries`; the script expects null. The pin is 1.2 km from Wikidata. The estuary parent is the real water. Not counted as a location error. [Wallasea Island](https://en.wikipedia.org/wiki/Wallasea_Island) was requested for the name; the coordinate check is Wikidata Q7962983.

### Removed stowaways, and the Severn pair

- `csv-geocoded-Q26272407` (Great Arthur House, Barbican) is **not** in `data/islands.json`.
- `csv-geocoded-Q66227635` (Thorney Island Community Primary School) is **not** in `data/islands.json`.
- A Scilly islet whose other name is Great Arthur remains. That is not the Barbican building.
- Two real Thorney Islands remain, both England: `wd-Q2453024` in the Thames at Westminster (type river, parent River Thames) and `wd-Q4575689` at Chichester Harbour (see suspicions).
- **Flat Holm** (`osm-way-126546636`) is Wales. [Flat Holm](https://en.wikipedia.org/wiki/Flat_Holm).
- **Steep Holm** is England and is in the confirmed list. Do not swap the pair.
- **Denny Island** (`osm-way-38867846`) is Wales: Monmouthshire above high water, Severn Estuary. [Denny Island](https://en.wikipedia.org/wiki/Denny_Island).
- **Sully Island** and **Barry Island** are Wales. Barry is also described as a peninsula; nation and pin are right, and it was not called an error.

### Solway, Foyle, and the Donegal islands that are already right

- Hestan Island (`osm-way-3098808`) and Little Ross (`osm-way-17506071`) are Scotland, Dumfries and Galloway, Solway Firth. Pins within 2 km. [Hestan Island](https://en.wikipedia.org/wiki/Hestan_Island).
- Rough Island at Kippford (`osm-way-3098796`) is the Scottish Solway island, not the Donegal one and not the Foyle one.
- Inishtrahull (`osm-way-4558676`) is Ireland, off Malin Head. [Inishtrahull](https://en.wikipedia.org/wiki/Inishtrahull).
- Tory Island, Arranmore, and Cruit Island are Ireland.
- The Galway Inishbofin (`osm-relation-8158207`) is Ireland. Only the Donegal one was wrong.
- Inishmean and Inisheher on Lough Melvin are already Ireland (County Leitrim).
- Inishteige (`osm-relation-3999307`) on Lough MacNean is Northern Ireland (Fermanagh and Omagh). That one is right.

### The 5 km sweep

`data/cache_wd_islands.json` has a coordinate for 3,487 Wikidata islands (SPARQL `coord`, the same fact as P625). Of 2,792 named atlas islands with a pin and a Wikidata id, 2,559 were in that cache.

| Distance | Islands |
|---|---|
| under 1 km | 2,492 |
| 1–2 km | 42 |
| 2–5 km | 15 |
| over 5 km | 10 |

The ten over 5 km:

| km | id | name | verdict |
|---|---|---|---|
| 176.5 | `osm-way-183405659` | Corn Holm | Suspicion 1. The Orkney Corn Holm is a different record and is right. |
| 54.9 | `osm-relation-6038068` | Great Britain | On the landmass. Suspicion 17. |
| 28.9 | `osm-way-8603690` | Uyea | Suspicion 2. Pin is Uyea, Unst. |
| 15.3 | `osm-relation-4619204` | Jura | On Jura (365 km²). Validation row. Not an error. |
| 14.4 | `osm-relation-7220346` | Lewis and Harris | On the island. Suspicion 4. |
| 7.9 | `lewis-and-harris` | Lewis and Harris | On the island. |
| 7.5 | `osm-relation-7681896` | Ireland | On the landmass. Suspicion 17. |
| 7.4 | `osm-relation-376677` | Shetland | On Mainland Shetland. Suspicion 5. |
| 7.4 | `isle-of-skye` | Isle of Skye | On Skye. |
| 7.4 | `osm-way-1063002533` | Oronsay | Suspicion 3. |

No confirmed coordinate error came out of the 5 km sweep.

There is no `type: unknown` and no null `nation` in the current file. One record uses nation `Isle of Man` (Peel Castle, suspicion 18). Every other nation is Scotland, England, Wales, Northern Ireland, Ireland, or Crown Dependency.

## Method

- Curated file read in full and joined to `data/islands.json` on id.
- Validation tuples run in Python against type, nation, and `parentWaterBody.name`.
- Queue items searched by name and by Wikidata id: Knightstone, Severn / Solway / Foyle boxes, Great Arthur House, Thorney Island school.
- Cached Wikidata coordinates compared with the haversine distance. Threshold 5 km, as asked.
- Live Wikidata `wbgetentities` for coordinates (P625), country (P17), admin (P131), and water (P206), in four batches, plus label lookups. English Wikipedia intro sentences for the places named above, in three queries. One request was rejected for listing more than 50 ids and was split. About a dozen HTTP calls. Responses were left in `/tmp`, not in the repo.
- No script was run with `--apply`, `--fix`, or `--commit`. `data/islands.json`, the interest index, and the shards were not edited.

Island-level only. No private addresses, owner names, or colony coordinates.

