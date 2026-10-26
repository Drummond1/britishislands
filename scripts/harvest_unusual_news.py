#!/usr/bin/env python3
"""Cite unusual news that happened on an atlas island.

Each row is a real report that places a strange event on that island:
a declaration of independence, names appearing, a mystery, or another
one-off. The summary is original. The picture is an open-licence
photograph of the thing the report is about. News photographs are not
copied. Does not edit islands.json.

Great Britain and Ireland do not count. No private address, no photograph
of a person, no grave coordinates, and no method for a weapons test.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from interest_categories import Atlas, row, write_candidates  # noqa: E402

SLUG = "unusual-news"

# island_id must already be in the atlas. commons_file is the subject.
SEEDS = [
    {
        "island_id": "osm-way-4004501",
        "title": "Boat names on the cliff",
        "source_url": "https://coast.scot/stories/the-canna-grafitti/",
        "source_title": "Coast that Shaped the World",
        "commons_file": "File:Graffiti, Canna Harbour - geograph.org.uk - 6177257.jpg",
        "image_note": "Names painted on the cliff at Canna harbour",
        "summary": (
            "As boats come into Canna harbour, names appear painted up the cliff behind the pier: "
            "fishing boats, their numbers, and home ports, refreshed by crews who call often. "
            "A published account of the cliff says the names are a visitors' book the boats keep themselves. "
            "One family has repainted their launch, Patrice, on visits since the 1950s."
        ),
        "evidence": "Coast that Shaped the World places the painted boat names on the cliff at Canna pier.",
    },
    {
        "island_id": "osm-way-172479890",
        "title": "Forvik declared independent",
        "source_url": "https://www.reuters.com/article/lifestyle/tiny-shetland-island-declares-independence-idUSL21226656/",
        "source_title": "Reuters",
        "commons_file": "File:Forewick Holm (aka Forvik Island) - geograph.org.uk - 1780521.jpg",
        "image_note": "Forvik, the Shetland islet in the declaration",
        "summary": (
            "In June 2008 Stuart Hill declared the Shetland islet of Forvik a crown dependency "
            "and said it owed no allegiance to any United Kingdom government. "
            "Reuters reported the declaration the day it was made. Britain does not recognise the claim."
        ),
        "evidence": "Reuters reported the independence declaration for the Shetland island of Forvik.",
    },
    {
        "island_id": "wd-Q13706",
        "title": "Principality of Sealand",
        "source_url": "https://www.bbc.co.uk/news/uk-england-suffolk-41135081",
        "source_title": "BBC News",
        "commons_file": "File:HM Fort Roughs a.k.a. Principality Of Sealand - geograph.org.uk - 1325728.jpg",
        "image_note": "HM Fort Roughs, the fort called Sealand",
        "summary": (
            "In 1967 Roy Bates declared the abandoned wartime fort HM Fort Roughs, about seven miles off Suffolk, "
            "the Principality of Sealand. Marking fifty years of the claim, the BBC described a flag, a constitution, "
            "and passports. Britain does not recognise the principality."
        ),
        "evidence": "BBC News places the 1967 declaration on HM Fort Roughs off Suffolk.",
    },
    {
        "island_id": "lundy",
        "title": "The puffin coins",
        "source_url": "https://time.com/archive/6766900/foreign-news-puffin-into-nuffin/",
        "source_title": "Time",
        "commons_file": "File:The Jetty, Lundy.jpg",
        "image_note": "Photograph of Lundy",
        "summary": (
            "Martin Coles Harman, who bought Lundy in 1925, told the High Court in 1931 that he was sovereign "
            "of the island and entitled to issue puffin coins with his own head on them. "
            "Time reported that the court kept a fine under the Coinage Act and treated Lundy as part of the United Kingdom."
        ),
        "evidence": "Time reported the 1931 coinage case in which Harman called himself sovereign of Lundy.",
    },
    {
        "island_id": "osm-relation-2324897",
        "title": "Declared free of anthrax",
        "source_url": "https://www.heraldscotland.com/news/11938940.outcast-island-finally-returns-to-real-world/",
        "source_title": "The Herald",
        "commons_file": "File:Gruinard Island.jpg",
        "image_note": "Photograph of Gruinard Island",
        "summary": (
            "Wartime anthrax tests left Gruinard Island closed for 48 years. "
            "On 24 April 1990 a defence minister crossed from the mainland, took down the red warning sign, "
            "and declared the island safe. The Herald reported the day."
        ),
        "evidence": "The Herald reported the 24 April 1990 declaration that Gruinard Island was safe.",
    },
    {
        "island_id": "osm-relation-2324897",
        "title": "Fire on the anthrax island",
        "source_url": "https://www.bbc.co.uk/news/uk-scotland-highlands-islands-60892350",
        "source_title": "BBC News",
        "commons_file": "File:Gruinard Island.jpg",
        "image_note": "Photograph of Gruinard Island",
        "summary": (
            "In March 2022 a fire burned from one end of Gruinard Island to the other. "
            "The BBC reported the blaze on the uninhabited island, used for anthrax tests in the Second World War "
            "and declared clear in April 1990. The fire service said the empty island was outside its remit."
        ),
        "evidence": "BBC News, 27 March 2022, reported the fire on Gruinard Island.",
    },
    {
        "island_id": "flannan-isles-eilean-mor-6-others",
        "title": "The keepers vanished",
        "source_url": "https://www.bbc.co.uk/news/articles/c7942e4gdnpo",
        "source_title": "BBC News",
        "commons_file": "File:Flannan Isles, the lighthouse - geograph.org.uk - 3201947.jpg",
        "image_note": "The Flannan Isles lighthouse",
        "summary": (
            "On 15 December 1900 the three keepers of the Flannan Isles lighthouse vanished from Eilean Mòr. "
            "A relief crew landed on 26 December and found the light ready, the beds empty, and the last notes from that morning. "
            "In June 2026 the BBC reported that the letter the first keeper ashore wrote would go on public display."
        ),
        "evidence": "BBC News places the 1900 disappearance at the Flannan Isles lighthouse on Eilean Mòr.",
    },
    {
        "island_id": "osm-way-4569195",
        "title": "A new breed of cattle",
        "source_url": "http://news.bbc.co.uk/2/hi/uk_news/scotland/480237.stm",
        "source_title": "BBC News",
        "commons_file": "File:Swona cattle - geograph.org.uk - 2221842.jpg",
        "image_note": "The cattle on Swona",
        "summary": (
            "The last residents left Swona in 1974 and the cattle stayed. "
            "In 1999 the BBC reported that the herd had bred without people for long enough to be entered as its own breed, "
            "the first new British cattle breed recognised in more than a century."
        ),
        "evidence": "BBC News, 20 October 1999, places the feral herd on Swona.",
    },
    {
        "island_id": "osm-way-4569195",
        "title": "Trainers in the post",
        "source_url": "https://www.bbc.co.uk/news/articles/c864pgw4d27o",
        "source_title": "BBC News",
        "commons_file": "File:Swona cattle - geograph.org.uk - 2221842.jpg",
        "image_note": "The cattle that live on Swona",
        "summary": (
            "In September 2025 a parcel addressed to Swona arrived in the post: a pair of trainers, "
            "for an island whose only inhabitants are feral cattle. "
            "The BBC reported that the people who look after Swona from South Ronaldsay did not know the name on the label, "
            "and that the island has no internet from which anyone there could have ordered them."
        ),
        "evidence": "BBC News, 12 September 2025, reported a parcel posted to Swona.",
    },
    {
        "island_id": "osm-way-128077107",
        "title": "Prince of the Saltees",
        "source_url": "https://www.irishtimes.com/opinion/an-irishman-s-diary-1.1068914",
        "source_title": "The Irish Times",
        "commons_file": "File:The Great Saltee.JPG",
        "image_note": "Photograph of Great Saltee",
        "summary": (
            "Michael Neale bought Great Saltee in 1943 and styled himself Prince of the Saltees. "
            "The Irish Times records that he set a throne and an obelisk on the island, and that his coronation was held there in 1953. "
            "As a boy he had told his mother he would one day own the island and be its prince."
        ),
        "evidence": "The Irish Times places the throne, the obelisk, and the 1953 coronation on Great Saltee.",
    },
    {
        "island_id": "osm-relation-1663615",
        "title": "The People's Republic of Eigg",
        "source_url": "http://news.bbc.co.uk/2/hi/uk_news/scotland/highlands_and_islands/8298816.stm",
        "source_title": "BBC News",
        "commons_file": "File:View of Galmisdale and An Sgurr - geograph.org.uk - 823602.jpg",
        "image_note": "Galmisdale and An Sgùrr on Eigg",
        "summary": (
            "In 1997 the residents of Eigg bought their island after years of dispute with absentee landlords. "
            "A BBC account of that purchase calls it the moment a People's Republic of Eigg declared independence."
        ),
        "evidence": "BBC News describes the 1997 community purchase of Eigg as a declaration of a people's republic.",
    },
    {
        "island_id": "mull",
        "title": "The night flight",
        "source_url": "https://www.bbc.com/news/articles/cgqz4pj1x9po",
        "source_title": "BBC News",
        "commons_file": "File:Glenforsa Airfield - Mull - geograph.org.uk - 2423728.jpg",
        "image_note": "Glenforsa airfield on Mull",
        "summary": (
            "On Christmas Eve 1975 Peter Gibbs took off alone, at night, from Glenforsa airfield on Mull and did not return. "
            "The BBC records that his body was found four months later on a hillside about a mile from the hotel, "
            "with no seawater on his clothes, and that the light aircraft was not with him."
        ),
        "evidence": "BBC News places the 1975 disappearance on a night flight from Glenforsa on Mull.",
    },
    {
        "island_id": "osm-relation-14940656",
        "title": "Castaway",
        "source_url": "http://news.bbc.co.uk/2/hi/entertainment/1079949.stm",
        "source_title": "BBC News",
        "commons_file": "File:Taransay Beach - geograph.org.uk - 883059.jpg",
        "image_note": "A beach on Taransay",
        "summary": (
            "In 2000 the BBC put 36 strangers on Taransay for a year and filmed them trying to build a community from scratch. "
            "By New Year seven had left, after gales that wrecked shelters they had built, a meningitis scare, and rows in public."
        ),
        "evidence": "BBC News reported the year-long Castaway settlement on Taransay.",
    },
    {
        "island_id": "rockall",
        "title": "Forty days on the rock",
        "source_url": "https://www.bbc.co.uk/news/uk-scotland-48582267",
        "source_title": "BBC News",
        "commons_file": "File:Rockall - geograph.org.uk - 1048822.jpg",
        "image_note": "Rockall",
        "summary": (
            "In 1985 Tom McClean spent 40 days and nights on Rockall, living in a wooden box bolted to the rock. "
            "He told the BBC he raised a Union flag when he landed and that he was the first person to reside there. "
            "Britain had annexed the rock in 1955."
        ),
        "evidence": "BBC News reports Tom McClean's 40 days living on Rockall in 1985.",
    },
    {
        "island_id": "fair-isle",
        "title": "The observatory burned",
        "source_url": "https://www.bbc.com/news/uk-scotland-north-east-orkney-shetland-47515175",
        "source_title": "BBC News",
        "commons_file": "File:Fair Isle Bird Observatory reopened June 2010 - geograph.org.uk - 1999001.jpg",
        "image_note": "The Fair Isle observatory before the 2019 fire",
        "summary": (
            "On 10 March 2019 a fire destroyed the Fair Isle Bird Observatory. "
            "The BBC reported that extra crews had to be flown from Sumburgh and brought by boat, "
            "and that the smoke could be seen from the Shetland mainland. A family in the adjoining flat got out unhurt."
        ),
        "evidence": "BBC News, 11 March 2019, reported the fire at the Fair Isle Bird Observatory.",
    },
    {
        "island_id": "osm-way-3099422",
        "title": "Crowned with beer",
        "source_url": "https://www.bbc.com/news/articles/c9vde23x3mgo",
        "source_title": "BBC News",
        "commons_file": "File:Piel Island and Castle, Barrow-in-Furness.jpg",
        "image_note": "Piel Island and its castle",
        "summary": (
            "Whoever takes the Ship Inn on Piel Island is crowned king or queen, and the ceremony pours a jug of beer over their head. "
            "In 2025 the BBC met the landlord, Aaron Sanderson, who said he was crowned at 33 when he took the pub. "
            "He is recorded as the island's 24th king."
        ),
        "evidence": "BBC News, 8 August 2025, reports the kingship attached to the Ship Inn on Piel Island.",
    },
    {
        "island_id": "wd-Q38252228",
        "title": "Graves in the mud",
        "source_url": "https://www.bbc.co.uk/news/uk-england-kent-38797543",
        "source_title": "BBC News",
        "commons_file": "File:Dead Man's Island and Channel Marker - geograph.org.uk - 997245.jpg",
        "image_note": "Deadman's Island in the Swale. Not a photograph of the graves.",
        "summary": (
            "Deadman's Island, a closed mudbank in the Swale opposite Queenborough, holds unmarked graves of people who died on prison hulks more than 200 years ago. "
            "In 2017 the BBC reported that erosion was washing those coffins out of the mud. The public are not allowed on the island."
        ),
        "evidence": "BBC News, 2017, places the exposed prison-hulk graves on Deadman's Island opposite Queenborough.",
    },
    {
        "island_id": "osm-way-2956937",
        "title": "The last feudal election",
        "source_url": "https://www.theguardian.com/uk/2008/dec/13/sark-channelislands",
        "source_title": "The Guardian",
        "commons_file": "File:Sark La Coupee 20160907.jpg",
        "image_note": "La Coupée on Sark",
        "summary": (
            "On 10 December 2008 Sark held its first fully democratic election in nearly 450 years and ended a feudal parliament. "
            "After candidates backed by the Barclay brothers lost, the Guardian reported that the brothers closed the shops, hotels, and building work they ran on the island, "
            "and that about 140 people lost their jobs."
        ),
        "evidence": "The Guardian, 13 December 2008, reported the election aftermath on Sark.",
    },
]


def populate_news(atlas: Atlas | None = None) -> list[dict]:
    atlas = atlas or Atlas()
    rows = []
    for seed in SEEDS:
        island = atlas.by_id.get(seed["island_id"])
        if not island:
            rows.append(
                row(
                    category=SLUG,
                    island_id=seed["island_id"],
                    facet="news",
                    title=seed["title"],
                    source_url=seed["source_url"],
                    source_title=seed["source_title"],
                    status="rejected",
                    confidence="high",
                    reject_reason="island id is not in the atlas index",
                    evidence=seed["evidence"],
                    summary=seed["summary"],
                )
            )
            continue
        item = row(
            category=SLUG,
            island_id=seed["island_id"],
            facet="news",
            title=seed["title"],
            source_url=seed["source_url"],
            source_title=seed["source_title"],
            status="accepted",
            confidence="high",
            licence="Summary original. Photograph via Wikimedia Commons.",
            evidence=seed["evidence"],
            summary=seed["summary"],
            island_name=island["name"],
        )
        item["commons_file"] = seed["commons_file"]
        item["image_note"] = seed["image_note"]
        item["image_alt"] = seed["image_note"]
        rows.append(item)
    write_candidates(SLUG, rows, {"source": "cited news reports", "seeds": len(SEEDS)})
    return rows


if __name__ == "__main__":
    populate_news()
