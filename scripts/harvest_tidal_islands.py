#!/usr/bin/env python3
"""Cite tidal islands from the English Wikipedia article Tidal island.

The article is the source. A row is kept only when that page names the
island for Britain, Ireland, Guernsey, or Jersey, the atlas already has
that island, and the page's definition says the link is exposed at low
tide and submerged at high tide. A permanent causeway named on the page,
or a permanent bridge named on the island's own article, is left out.

No crossing times, safe windows, or private tracks. Does not edit
islands.json. The atlas subtype `tidal` is not a source.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from ingest_sources import haversine_km  # noqa: E402
from interest_categories import fold, row, write_candidates  # noqa: E402

SOURCE = "https://en.wikipedia.org/wiki/Tidal_island"
SOURCE_TITLE = "Tidal island"
LICENCE = "CC BY-SA 4.0"
TIDE = "The link is exposed at low tide and covered at high tide."
BANNED = re.compile(
    r"\b(hours?|safe window|tide times|crossing time|do not|private track)\b",
    re.I,
)

# Hand count from the 25 October 2026 text of the article.
# id, atlas name, lat, lng, card title, where it joins, list bullet.
KEPT = [
    ("osm-way-3404368", "Lihou", 49.461, -2.668, "Joined to Guernsey", "It is joined to Guernsey.", "Lihou in Guernsey, one of the Channel Islands."),
    ("osm-way-87357581", "Coney Island", 54.296, -8.588, "Near Rosses Point", "It is joined to the coast near Rosses Point, County Sligo.", "Coney Island near Rosses Point, County Sligo."),
    ("osm-relation-3414078", "Omey Island", 53.531, -10.167, "Joined to Connemara", "It is joined to the Connemara coast in County Galway.", "Omey Island in Connemara, County Galway."),
    ("osm-way-4559719", "Inishkeel", 54.848, -8.457, "Joined to the Donegal coast", "It is joined to the County Donegal coast.", "Inishkeel, County Donegal."),
    ("osm-way-2957543", "La Motte", 49.161, -2.077, "Joined to Jersey", "It is joined to Jersey, where it is also called Green Island.", "La Motte, Jersey, alias Green Island."),
    ("wd-Q129167797", "L'Avarison", 49.158, -2.008, "Joined to Jersey", "It is joined to Jersey and hosts Seymour Tower.", "L'Avarison, which hosts Seymour Tower."),
    ("osm-way-2957548", "Icho", 49.148, -2.048, "Joined to Jersey", "It is the islet of Icho Tower, joined to Jersey.", "Icho Tower."),
    ("osm-way-409793711", "Asparagus Island", 49.974, -5.233, "Mount's Bay, Cornwall", "It is joined to the shore of Mount's Bay, Cornwall.", "Asparagus Island, Mount's Bay, Cornwall."),
    ("burgh-island", "Burgh Island", 50.279, -3.900, "Joined to the Devon coast", "It is joined to the Devon coast.", "Burgh Island, Devon."),
    ("osm-way-2943262", "Burrow Island", 50.803, -1.121, "Portsmouth Harbour", "It is joined to the shore of Portsmouth Harbour.", "Burrow Island, Portsmouth Harbour."),
    ("osm-way-3099261", "Chapel Island", 54.174, -3.041, "Joined to the Cumbrian coast", "It is joined to the Cumbrian coast.", "Chapel Island, Cumbria."),
    ("wd-Q1074858", "Chiswick Eyot", 51.487, -0.246, "Joined to the Thames bank", "It stands in the River Thames in London, joined to the bank.", "Chiswick Eyot in the River Thames in London."),
    ("osm-way-250415714", "Dova Haw", 54.096, -3.235, "Off the Cumbrian coast", "It is one of the Islands of Furness, off the coast of Cumbria.", "Dova Haw, one of the Islands of Furness, off the coast of Cumbria."),
    ("osm-way-237654372", "Gugh", 49.894, -6.333, "Joined to St Agnes", "It is joined to St Agnes.", "Gugh in the Isles of Scilly (joined to St Agnes at low tide)."),
    ("wd-Q5689613", "Headin Haw", 54.097, -3.203, "Off the Cumbrian coast", "It is one of the Islands of Furness, off the coast of Cumbria.", "Headin Haw, one of the Islands of Furness, off the coast of Cumbria."),
    ("osm-way-250292715", "Hilbre Island", 53.382, -3.226, "Dee estuary, the Wirral", "It stands in the River Dee estuary, between North Wales and the English Wirral.", "Hilbre Island, Middle Eye and Little Eye in the River Dee estuary, between North Wales and the English Wirral, but administratively in England."),
    ("osm-node-252820858", "Middle Eye (Little Hilbre)", 53.378, -3.221, "Dee estuary, the Wirral", "It stands in the River Dee estuary, between North Wales and the English Wirral.", "Hilbre Island, Middle Eye and Little Eye in the River Dee estuary, between North Wales and the English Wirral, but administratively in England."),
    ("osm-node-252820875", "Little Eye", 53.371, -3.205, "Dee estuary, the Wirral", "It stands in the River Dee estuary, between North Wales and the English Wirral.", "Hilbre Island, Middle Eye and Little Eye in the River Dee estuary, between North Wales and the English Wirral, but administratively in England."),
    ("osm-relation-965365", "Horsey Island", 51.876, 1.243, "Joined to the Essex coast", "It is joined to the Essex coast.", "Horsey Island, Essex."),
    ("lindisfarne", "Lindisfarne (Holy Island)", 55.681, -1.802, "Joined to the Northumberland coast", "It is joined to the Northumberland coast, and is also called Holy Island.", "Lindisfarne, Northumberland, also known as Holy Island."),
    ("osm-relation-6046587", "Mersea Island", 51.791, 0.951, "Joined by the Strood", "It is joined to the Essex mainland by the Strood.", "Mersea Island, Essex (accessible to road traffic via the Strood)."),
    ("osm-relation-9873586", "Northey Island", 51.724, 0.719, "Joined to the Essex coast", "It is joined to the Essex coast.", "Northey Island, Essex."),
    ("osm-way-109926387", "Osea Island", 51.723, 0.770, "Joined to the Essex coast", "It is joined to the Essex coast.", "Osea Island, Essex."),
    ("osm-way-3099422", "Piel Island", 54.064, -3.175, "Joined to the Cumbrian coast", "It is joined to the Cumbrian coast.", "Piel Island, Cumbria."),
    ("osm-relation-9795458", "Scolt Head Island", 52.983, 0.704, "Joined to the Norfolk coast", "It is joined to the Norfolk coast.", "Scolt Head Island, Norfolk."),
    ("osm-way-3099419", "Sheep Island", 54.065, -3.202, "Joined to Piel and Walney", "It is joined to Piel Island and to Walney Island.", "Sheep Island, Cumbria (joined at low tide to Piel Island and to Walney Island)."),
    ("wd-Q7594502", "St Mary's Island", 55.072, -1.450, "Joined to the North Tyneside coast", "It is joined to the North Tyneside coast.", "St Mary's Island, North Tyneside."),
    ("osm-way-147209474", "Saint Michael's Mount", 50.118, -5.478, "Joined to the Cornish coast", "It is joined to the Cornish coast, and stands clear of that shore at high tide.", "St Michael's Mount, Cornwall."),
    ("osm-relation-3212246", "White Island", 49.977, -6.292, "Joined to St Martin's", "It is joined to St Martin's in the Isles of Scilly.", "White Island, Isles of Scilly and St Martin's, Isles of Scilly."),
    ("osm-way-4557019", "Mahee Island", 54.502, -5.635, "Strangford Lough", "It is joined to the shore of Strangford Lough.", "Nendrum Monastery on Mahee Island, Strangford Lough."),
    ("osm-way-4557268", "Guns Island", 54.294, -5.547, "Joined to Ballyhornan Bay", "It is connected to Ballyhornan Bay.", "Guns Island, near Ballyhornan. The page's picture note says Gunns Island is connected to Ballyhornan Bay at low tide."),
    ("osm-relation-18138346", "Isle of Muck", 54.848, -5.719, "Joined at Portmuck", "It is joined to the coast at Portmuck.", "Isle of Muck, Portmuck."),
    ("osm-way-4556956", "Rough Island", 54.546, -5.690, "Near Comber, Strangford Lough", "It is joined to the shore of Strangford Lough near Comber.", "Rough Island, near Comber, Strangford Lough."),
    ("osm-relation-13146202", "Baleshare", 57.524, -7.375, "Joined to North Uist", "It is joined to North Uist.", "Baleshare in the Outer Hebrides, joined to North Uist."),
    ("osm-way-205084046", "Bernera Island", 56.494, -5.585, "Joined to Lismore", "It is joined to Lismore.", "Bernera Island, joined to Lismore."),
    ("osm-way-4569428", "Brough of Birsay", 59.136, -3.335, "Joined to Orkney Mainland", "It is joined to Orkney Mainland.", "Brough of Birsay in Orkney, joined to Orkney Mainland."),
    ("osm-way-205108325", "Stalker Island", 56.571, -5.386, "Loch Laich, Argyll", "Castle Stalker stands on it, in Loch Laich in Argyll, joined to the loch shore.", "Castle Stalker on Loch Laich in Argyll."),
    ("osm-relation-1658182", "Cramond Island", 55.993, -3.290, "Causeway in the Firth of Forth", "It lies in the Firth of Forth, and its causeway is submerged at high tide.", "Cramond Island in the Firth of Forth."),
    ("osm-relation-10323151", "Davaar Island", 55.425, -5.545, "Joined to Kintyre", "It lies near Campbeltown, joined to the Kintyre peninsula.", "Island Davaar near Campbeltown, off the Kintyre peninsula."),
    ("osm-relation-13987269", "Eilean Fladday", 57.486, -6.026, "Joined to Raasay", "It is joined to the Isle of Raasay.", "Eilean Fladday and Eilean Tigh off the Isle of Raasay."),
    ("osm-relation-13736431", "Eilean Tigh", 57.512, -6.003, "Joined to Raasay", "It is joined to the Isle of Raasay.", "Eilean Fladday and Eilean Tigh off the Isle of Raasay."),
    ("osm-relation-9395600", "Eilean Shona", 56.798, -5.848, "Loch Moidart", "It is joined to the shore of Loch Moidart.", "Eilean Shona in Loch Moidart, Lochaber, Highland."),
    ("osm-way-4009288", "Eilean Tioram", 56.784, -5.828, "Loch Moidart", "It is joined to the shore of Loch Moidart.", "Eilean Tioram, in Loch Moidart."),
    ("osm-relation-9620215", "Erraid", 56.292, -6.370, "Joined to Mull", "It is joined to the Isle of Mull.", "Erraid off the Isle of Mull."),
    ("osm-way-3098808", "Hestan Island", 54.836, -3.810, "Auchencairn Bay", "It lies near Rough Island in Auchencairn Bay, joined to that shore.", "Hestan Island near Rough Island in Auchencairn Bay."),
    ("osm-relation-15750034", "Ardwall Isle", 54.819, -4.225, "Islands of Fleet", "It is one of the Islands of Fleet in Galloway, joined to that shore.", "Islands of Fleet: Ardwall Isle and Barlocco Isle in Galloway."),
    ("osm-relation-15750033", "Barlocco Isle", 54.809, -4.214, "Islands of Fleet", "It is one of the Islands of Fleet in Galloway, joined to that shore.", "Islands of Fleet: Ardwall Isle and Barlocco Isle in Galloway."),
    ("osm-way-3619210", "Isle Ristol", 58.046, -5.437, "Innermost of the Summer Isles", "It is the innermost of the Summer Isles, joined to that shore.", "Isle Ristol, the innermost of the Summer Isles."),
    ("osm-way-4569230", "Kili Holm", 59.176, -2.919, "Joined to Egilsay", "It is joined to Egilsay.", "Kili Holm in Orkney, joined to Egilsay."),
    ("osm-way-23275012", "Oronsay", 56.014, -6.240, "Joined to Colonsay", "It is joined to Colonsay.", "Oronsay in the Inner Hebrides, joined to Colonsay."),
    ("osm-way-1218371162", "Oronsay", 57.335, -6.464, "Joined to Skye", "It is joined to Skye, in Loch Bracadale.", "Oronsay in Loch Bracadale, joined to Skye."),
    ("osm-way-216812403", "Orosay", 57.029, -7.418, "Joined to Barra", "It is joined to Barra.", "Orosay in the Outer Hebrides, joined to Barra."),
    ("osm-way-3098796", "Rough Island", 54.860, -3.803, "Opposite Rockcliffe", "It is joined to the shore opposite Rockcliffe, Dumfries and Galloway.", "Rough Island opposite Rockcliffe, Dumfries & Galloway."),
    ("osm-relation-9319278", "Uyea", 60.618, -1.427, "Joined to Northmavine", "It is joined to the Northmavine peninsula in Shetland.", "Uyea, Northmavine, off the Northmavine peninsula, Shetland."),
    ("osm-way-4010657", "Vallay", 57.662, -7.408, "Joined to North Uist", "It is joined to North Uist.", "Vallay (Bhàlaigh), joined to North Uist in the Outer Hebrides."),
    ("osm-way-96327659", "Burry Holms", 51.609, -4.313, "Joined to the Gower", "It is joined to the Gower.", "Burry Holms off the Gower."),
    ("osm-way-4000577", "Cribinau", 53.185, -4.492, "Joined to Anglesey", "It is joined to Anglesey.", "Cribinau off Anglesey."),
    ("osm-way-1493746527", "Gateholm", 51.719, -5.230, "Joined to the Pembrokeshire coast", "It is joined to the south-west coast of Pembrokeshire.", "Gateholm off the south west coast of Pembrokeshire."),
    ("osm-way-1493746453", "St Catherine's Island", 51.671, -4.692, "Joined to the Pembrokeshire coast", "It is joined to the Pembrokeshire coast.", "St Catherine's Island in Pembrokeshire."),
    ("osm-way-491160982", "Sully Island", 51.396, -3.198, "Joined to the Glamorgan coast", "It is joined to the coast of the Vale of Glamorgan.", "Sully Island in the Vale of Glamorgan."),
    ("osm-way-1493808602", "Worms Head", 51.564, -4.324, "Joined to the Gower", "It is joined to the end of the Gower.", "Worm's Head at the end of the Gower."),
    ("osm-way-1493746577", "Ynys Cantwr", 51.853, -5.333, "Joined to Ramsey Island", "It is joined to Ramsey Island.", "Ynys Cantwr off Ramsey Island, Pembrokeshire."),
    ("osm-relation-17552908", "Ynys Feurig", 53.231, -4.543, "Joined to Anglesey", "It is joined to Anglesey.", "Ynys Feurig off Anglesey."),
    ("osm-way-300065283", "Ynys Gifftan", 52.912, -4.082, "Joined to the Gwynedd coast", "It is joined to the Gwynedd coast.", "Ynys Gifftan in Gwynedd."),
    ("osm-way-1493746496", "Ynys Gwelltog", 51.854, -5.336, "Joined to Ramsey Island", "It is joined to Ramsey Island.", "Ynys Gwelltog off Ramsey Island, Pembrokeshire."),
    ("osm-way-4041382", "Ynys Lochtyn", 52.173, -4.466, "Cardigan Bay coast", "It is joined to the coast of Cardigan Bay.", "Ynys Lochtyn on the coast of Cardigan Bay."),
]

# Named on the page, and not published.
HELD = [
    ("osm-way-201511514", "Eilean Donan", "The tidal-island bullet does not say the crossing floods. Eilean Donan's own article says a footbridge, put in early in the 20th century, joins it to the mainland."),
    ("", "Archirondel Tower", "The same article says it is now connected via a permanent causeway."),
    ("", "Elizabeth Castle", "Listed for Jersey as reachable on foot at low tide, but it is not an island in the atlas."),
    ("", "Saint Aubin's Fort", "Listed under Jersey, but it is not an island in the atlas."),
    ("", "La Corbière Lighthouse", "Listed under Jersey, but it is not an island in the atlas."),
    ("", "Portelet Tower", "Listed under Jersey, but it is not an island in the atlas."),
    ("", "Marsden Rock", "Listed under England, but it is not an island in the atlas."),
    ("", "Eilean Arnoil", "Listed as joined to Lewis, but that name is not an island in the atlas."),
    ("", "Ynys Llanddwyn", "Listed off Anglesey, but it is not an island in the atlas."),
    ("", "Mumbles Lighthouse", "Listed near Swansea, but it is not an island in the atlas."),
    ("osm-relation-3210701", "St Martin's", "The bullet pairs it with White Island. White Island is the land joined to St Martin's. The page does not say St Martin's itself is cut off from a further shore."),
]


def _summary(label: str, where: str) -> str:
    text = f"{label} is a tidal island. {where} {TIDE}"
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _label(atlas_name: str) -> str:
    if atlas_name == "Lindisfarne (Holy Island)":
        return "Lindisfarne"
    if atlas_name == "Middle Eye (Little Hilbre)":
        return "Middle Eye"
    if atlas_name == "Saint Michael's Mount":
        return "St Michael's Mount"
    if atlas_name == "Worms Head":
        return "Worm's Head"
    return atlas_name


def populate_tidal(atlas) -> list[dict]:
    rows = []
    seen = set()
    for island_id, atlas_name, lat, lng, title, where, bullet in KEPT:
        island = atlas.by_id.get(island_id)
        label = _label(atlas_name)
        summary = _summary(label, where)
        evidence = f"Wikipedia '{SOURCE_TITLE}' lists: {bullet} A tidal island's link is exposed at low tide and submerged at high tide."
        reason = ""
        status = "accepted"
        if island is None:
            status = "rejected"
            reason = "atlas id missing"
        elif fold(island["name"]) != fold(atlas_name):
            status = "rejected"
            reason = f"atlas name is {island['name']!r}, expected {atlas_name!r}"
        elif haversine_km(lat, lng, island["lat"], island["lng"]) > 3:
            status = "rejected"
            reason = "atlas point has moved away from the counted island"
        elif island_id in seen:
            status = "rejected"
            reason = "duplicate island"
        elif BANNED.search(summary) or BANNED.search(title):
            status = "rejected"
            reason = "summary included a crossing time or a private track"
        elif "low tide" not in summary.lower() or "high tide" not in summary.lower():
            status = "rejected"
            reason = "summary does not say the link floods"
        if status == "accepted":
            seen.add(island_id)
        rows.append(
            row(
                category="tidal-islands",
                island_id=island_id if status == "accepted" else (island_id if island else ""),
                island_name=island["name"] if island else atlas_name,
                facet="tidal",
                title=title,
                source_url=SOURCE,
                source_title=SOURCE_TITLE,
                licence=LICENCE,
                evidence=evidence,
                external_id="Tidal_island",
                status=status,
                confidence="high" if status == "accepted" else "medium",
                reject_reason=reason,
            )
        )
        if status == "accepted":
            rows[-1]["summary"] = summary

    for island_id, atlas_name, reason in HELD:
        island = atlas.by_id.get(island_id) if island_id else None
        rows.append(
            row(
                category="tidal-islands",
                island_id=island_id if island else "",
                island_name=island["name"] if island else atlas_name,
                facet="tidal",
                title=atlas_name,
                source_url=SOURCE,
                source_title=SOURCE_TITLE,
                licence=LICENCE,
                evidence=reason,
                external_id="Tidal_island",
                status="rejected",
                confidence="high",
                reject_reason=reason,
            )
        )

    write_candidates(
        "tidal-islands",
        rows,
        {
            "source": SOURCE,
            "licence": LICENCE,
            "counted": "2026-10-25",
            "note": "Britain, Ireland, Guernsey, and Jersey names on the Tidal island article. The atlas subtype tidal was not used. No crossing times.",
        },
    )
    return rows
