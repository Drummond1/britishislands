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
    {
        "island_id": "osm-relation-15708714",
        "title": "Whisky from the wreck",
        "source_url": "https://www.bbc.co.uk/news/uk-scotland-12363591",
        "source_title": "BBC News",
        "commons_file": "File:Eriskay - geograph.org.uk - 200811.jpg",
        "image_note": "Eriskay, where the SS Politician went aground",
        "summary": (
            "On 5 February 1941 the cargo ship SS Politician ran aground off Eriskay "
            "with about 250,000 bottles of whisky in the hold. "
            "The BBC's account says islanders rowed out and took cases ashore, "
            "and that Customs and Excise pursued them because no duty had been paid on the spirits."
        ),
        "evidence": "BBC News, 4 February 2011, places the 1941 wreck of the SS Politician off Eriskay.",
    },
    {
        "island_id": "osm-relation-380646",
        "title": "The beach is the runway",
        "source_url": "https://www.bbc.com/news/uk-scotland-highlands-islands-65960707",
        "source_title": "BBC News",
        "commons_file": "File:Cockleshell beach, Isle of Barra - geograph.org.uk - 7036092.jpg",
        "image_note": "The cockle strand on Barra, used as the runway",
        "summary": (
            "Scheduled flights to Barra land on Tràigh Mhòr, a cockle beach at the north of the island, "
            "and the timetable follows the tide. "
            "The BBC describes it as the only beach runway in the world used for scheduled airline services. "
            "When the windsocks are down, the sand is a public beach again."
        ),
        "evidence": "BBC News, 20 June 2023, describes scheduled landings on the beach at Barra.",
    },
    {
        "island_id": "st-kilda",
        "title": "The last boats",
        "source_url": "https://www.nts.org.uk/stories/st-kilda-the-evacuation-of-a-community",
        "source_title": "National Trust for Scotland",
        "commons_file": "File:Saint Kilda 20090611 Hirta - Village Bay overview.jpg",
        "image_note": "Village Bay on Hirta, St Kilda",
        "summary": (
            "On the morning of 29 August 1930 the last 36 people living on St Kilda left Hirta aboard HMS Harebell. "
            "The National Trust for Scotland records that they had asked the government that May to help them leave, "
            "because too few remained to keep the island through another winter."
        ),
        "evidence": "The National Trust for Scotland places the 29 August 1930 evacuation on Hirta, St Kilda.",
    },
    {
        "island_id": "osm-relation-3148465",
        "title": "Scotland's earliest face",
        "source_url": "http://news.bbc.co.uk/2/hi/uk_news/scotland/north_east/8212074.stm",
        "source_title": "BBC News",
        "commons_file": "File:Westray_Wife_20110529.jpg",
        "image_note": "The sandstone figurine found on Westray",
        "summary": (
            "In 2009 archaeologists at the Links of Noltland on Westray lifted a sandstone figurine "
            "a few centimetres tall from the mud of a Neolithic house. "
            "The BBC reported it as the earliest human face known from Scotland. "
            "It has come to be called the Westray Wife."
        ),
        "evidence": "BBC News reported the 2009 find of the figurine at the Links of Noltland on Westray.",
    },
    {
        "island_id": "osm-way-4569530",
        "title": "Two minutes in the air",
        "source_url": "https://www.bbc.co.uk/news/uk-scotland-north-east-orkney-shetland-22668150",
        "source_title": "BBC News",
        "commons_file": "File:Papa Westray airport - geograph.org.uk - 8291554.jpg",
        "image_note": "The airstrip on Papa Westray",
        "summary": (
            "The scheduled flight between Westray and Papa Westray covers 1.7 miles. "
            "The BBC reported that the hop takes about two minutes, including taxiing, "
            "and that the fastest recorded time was 53 seconds."
        ),
        "evidence": "BBC News places the two-minute scheduled flight between Westray and Papa Westray.",
    },
    {
        "island_id": "osm-relation-12597195",
        "title": "The beast on the rocks",
        "source_url": "http://news.bbc.co.uk/2/hi/uk_news/scotland/highlands_and_islands/7074696.stm",
        "source_title": "BBC News",
        "commons_file": "File:PicVat.jpg",
        "image_note": "Stronsay",
        "summary": (
            "In September 1808 a carcass the islanders did not recognise washed onto the rocks "
            "at Rothiesholm Head on Stronsay. Witnesses put it at about 55 feet. "
            "The BBC, reporting later research, said some experts took it for a dead basking shark, "
            "while the drawings were compared with descriptions of the Loch Ness monster."
        ),
        "evidence": "BBC News, 3 November 2007, places the 1808 Stronsay Beast at Rothiesholm Head.",
    },
    {
        "island_id": "osm-relation-2797155",
        "title": "The raiders",
        "source_url": "http://news.bbc.co.uk/2/hi/uk_news/scotland/highlands_and_islands/6653709.stm",
        "source_title": "BBC News",
        "commons_file": "File:Vatersay_Fae057.jpg",
        "image_note": "Vatersay",
        "summary": (
            "In July 1906 landless men from Barra, who the BBC says were not allowed to build a proper house there, "
            "took land on Vatersay. "
            "By 1909 the Congested Districts Board had bought the island and divided it into 58 crofts."
        ),
        "evidence": "BBC News places the 1906 land raid, and the 1909 crofting division, on Vatersay.",
    },
    {
        "island_id": "osm-way-495525351",
        "title": "Stones for the Olympics",
        "source_url": "https://www.bbc.com/news/uk-scotland-68713338",
        "source_title": "BBC News",
        "commons_file": "File:Ailsa_Craig_2017-05-17.jpg",
        "image_note": "Ailsa Craig",
        "summary": (
            "The granite for the curling stones used at the Olympics is taken from Ailsa Craig, "
            "an uninhabited island in the Firth of Clyde. "
            "The BBC reported that one Ayrshire workshop has made them for more than 170 years, "
            "and that the rock is cut from the island about once a decade."
        ),
        "evidence": "BBC News places the granite for Olympic curling stones on Ailsa Craig.",
    },
    {
        "island_id": "osm-relation-4619204",
        "title": "Caught in the whirlpool",
        "source_url": "https://www.bbc.co.uk/news/uk-scotland-43821334",
        "source_title": "BBC News",
        "commons_file": "File:The Corryvreckan from Eilean Beag - geograph.org.uk - 39359.jpg",
        "image_note": "The Corryvreckan, off the north of Jura",
        "summary": (
            "In 1947, while he was on Jura writing his last novel, George Orwell's boat was caught "
            "in the Corryvreckan whirlpool between Jura and Scarba. "
            "The BBC records that the outboard motor was torn off, the boat capsized, "
            "and Orwell got his young son onto the rocks of Eilean Mòr before a passing fisherman took them off."
        ),
        "evidence": "BBC News, 29 April 2018, places Orwell's 1947 capsize in the Corryvreckan off Jura.",
    },
    {
        "island_id": "osm-relation-8609288",
        "title": "The car over the sound",
        "source_url": "https://www.rte.ie/news/2023/0609/1388240-cable-car-dursey-island/",
        "source_title": "RTÉ News",
        "commons_file": "File:Oileán Baoi (Dursey Island), Cable car - geograph.org.uk - 262128.jpg",
        "image_note": "The cable car to Dursey Island",
        "summary": (
            "Ireland's only cable car runs from the Beara peninsula across open water to Dursey Island. "
            "RTÉ reported that it first opened on 5 December 1969, "
            "and that it reopened in June 2023 after the towers and ropes were replaced. "
            "The car carries six people."
        ),
        "evidence": "RTÉ News, 9 June 2023, places Ireland's only cable car on the crossing to Dursey Island.",
    },
    {
        "island_id": "osm-relation-6045406",
        "title": "The furnished bus shelter",
        "source_url": "https://www.shetlandtimes.co.uk/news/website-for-unst-bus-shelter-is-essential-reading-for-future-generations-407981/",
        "source_title": "The Shetland Times",
        "commons_file": "File:Burra Stack, Unst - geograph.org.uk - 116634.jpg",
        "image_note": "Unst",
        "summary": (
            "After the bus shelter past Baltasound was taken away, a child wrote to the paper in 1996 asking for it back. "
            "The Shetland Times later described a sofa, a television, a heater and a carpet inside the replacement, "
            "and a website the British Library chose to archive. The shelter stands on Unst."
        ),
        "evidence": "The Shetland Times, 3 April 2013, places the furnished bus shelter at Baltasound on Unst.",
    },
    {
        "island_id": "osm-relation-12597195",
        "title": "A walrus under the ramp",
        "source_url": "https://orcadian.co.uk/walrus-spotted-at-stronsay-pier/",
        "source_title": "The Orcadian",
        "commons_file": "File:PicVat.jpg",
        "image_note": "Stronsay",
        "summary": (
            "In April 2026 the pier master on Stronsay saw a walrus as the ferry came in, and it settled under the linkspan. "
            "The Orcadian called it the third walrus to turn up in Orkney in recent years."
        ),
        "evidence": "The Orcadian, 16 April 2026, places a walrus under the linkspan at Stronsay pier.",
    },
    {
        "island_id": "osm-relation-3148464",
        "title": "Two huts became a chapel",
        "source_url": "https://orcadian.co.uk/appeal-for-italian-chapel-prisoner-of-war-stories-letters-and-artefacts/",
        "source_title": "The Orcadian",
        "commons_file": "File:Italian Chapel on Lamb Holm - geograph.org.uk - 931903.jpg",
        "image_note": "The Italian Chapel on Lamb Holm",
        "summary": (
            "Italian prisoners of war, held while they built the Churchill Barriers, made a chapel on Lamb Holm out of two Nissen huts. "
            "The Orcadian records Camp 60 on Lamb Holm as the place that chapel was built."
        ),
        "evidence": "The Orcadian places the Italian Chapel, built from two huts, on Lamb Holm.",
    },
    {
        "island_id": "osm-relation-6045499",
        "title": "A Viking hilt from the hill",
        "source_url": "https://www.shetlandtimes.co.uk/news/viking-sword-pommel-from-fetlar-finds-a-home-in-shetland-museum-394056/",
        "source_title": "The Shetland Times",
        "commons_file": "File:The Clett and Busta Pund, Fetlar - geograph.org.uk - 4970744.jpg",
        "image_note": "Fetlar",
        "summary": (
            "Shetland Museum took in a five-lobed sword pommel dated to about 900 to 1100, found on Fetlar. "
            "The Shetland Times reported the curator calling that kind of Viking find rare, and likely a status piece rather than a weapon that had been used."
        ),
        "evidence": "The Shetland Times, 28 January 2025, places the Viking sword pommel find on Fetlar.",
    },
    {
        "island_id": "osm-relation-380684",
        "title": "A funeral for a mermaid",
        "source_url": "https://www.stornowaygazette.co.uk/news/myth-of-the-mermaid-remains-an-enduring-fishy-tale-2129315",
        "source_title": "Stornoway Gazette",
        "commons_file": "File:Benbecula Beach.jpg",
        "image_note": "A beach on Benbecula",
        "summary": (
            "The Stornoway Gazette retells an 1830 account from the west of Benbecula: a small body, described as human above and fish below, "
            "washed ashore near Nunton and was buried as a mermaid. The paper says no grave has been found."
        ),
        "evidence": "The Stornoway Gazette, 3 October 2016, places the reported mermaid burial on Benbecula.",
    },
    {
        "island_id": "osm-relation-6045516",
        "title": "Three bears on the beach",
        "source_url": "https://www.pressandjournal.co.uk/fp/news/highlands-islands/1084514/islanders-left-baffled-mysterious-polar-bears-washed-scots-beach/",
        "source_title": "The Press and Journal",
        "commons_file": "File:Kiloran Bay from Carnan Eoin - geograph.org.uk - 24801.jpg",
        "image_note": "The west side of Colonsay",
        "summary": (
            "In 2016 three hairy carcasses washed up at different points on the west coast of Colonsay, and people on the island took them for polar bears. "
            "The Press and Journal reported that the Royal Zoological Society of Scotland called a polar bear highly unlikely."
        ),
        "evidence": "The Press and Journal, 15 November 2016, places the three carcasses on the west coast of Colonsay.",
    },
    {
        "island_id": "osm-relation-1663893",
        "title": "A road built by one man",
        "source_url": "https://www.pressandjournal.co.uk/fp/news/highlands-islands/6596318/story-of-calums-road-raasay-skye-lochalsh-portree-high/",
        "source_title": "The Press and Journal",
        "commons_file": "File:RaasayIsland2.JPG",
        "image_note": "Raasay",
        "summary": (
            "In 1964, after the council would not build a road in the north of Raasay, Calum MacLeod started the stretch from Brochel to Arnish himself. "
            "The Press and Journal says he worked into the mid-1970s with a shovel, a pick and a wheelbarrow."
        ),
        "evidence": "The Press and Journal, 14 December 2024, places Calum's Road in the north of Raasay.",
    },
    {
        "island_id": "osm-relation-1663615",
        "title": "A jog over a stegosaur",
        "source_url": "https://www.pressandjournal.co.uk/fp/entertainment/whats-on/2438533/dinosaur-fossil-dating-back-166-million-years-discovered-on-isle-of-eigg/",
        "source_title": "The Press and Journal",
        "commons_file": "File:View of Galmisdale and An Sgurr - geograph.org.uk - 823602.jpg",
        "image_note": "Eigg",
        "summary": (
            "A researcher jogging the foreshore of Eigg ran over a bone set in a boulder, the first dinosaur fossil found on the island. "
            "The Press and Journal reported a piece about a foot long, about 166 million years old, from the hind limb of a stegosaur."
        ),
        "evidence": "The Press and Journal, 26 August 2020, places the stegosaur bone on the foreshore of Eigg.",
    },
    {
        "island_id": "lewis-and-harris",
        "title": "Chessmen in a sand dune",
        "source_url": "https://www.stornowaygazette.co.uk/news/chessmen-among-top-historical-items-2078482",
        "source_title": "Stornoway Gazette",
        "commons_file": "File:Lewis chessmen.jpg",
        "image_note": "The Lewis chessmen",
        "summary": (
            "The Stornoway Gazette records that the Lewis chessmen were found in 1831 in a small stone cist in a sand dune at Uig. "
            "Most of the pieces are carved from walrus tusk."
        ),
        "evidence": "The Stornoway Gazette, 28 February 2019, places the 1831 find of the chessmen at Uig on Lewis.",
    },
    {
        "island_id": "isle-of-skye",
        "title": "Plaster in the footprints",
        "source_url": "https://www.pressandjournal.co.uk/fp/news/highlands-islands/1127355/vandal-damages-skye-tourism-gems/",
        "source_title": "The Press and Journal",
        "commons_file": "File:An Corran beach and Staffin Island - geograph.org.uk - 6533675.jpg",
        "image_note": "An Corran beach at Staffin, Skye",
        "summary": (
            "Police on Skye investigated damage to dinosaur footprints at Staffin that are about 165 million years old. "
            "The Press and Journal reported that plaster had been poured into two of the prints."
        ),
        "evidence": "The Press and Journal, 30 December 2016, places the damaged dinosaur prints at Staffin on Skye.",
    },
    {
        "island_id": "osm-relation-1240445",
        "title": "The last post on Tanera",
        "source_url": "https://www.pressandjournal.co.uk/fp/news/highlands-islands/406577/undefined-headline-580/",
        "source_title": "The Press and Journal",
        "commons_file": "File:Approaching Tanera More - geograph.org.uk - 3994876.jpg",
        "image_note": "Tanera Mòr",
        "summary": (
            "The Press and Journal reported that the last permanent residents had left Tanera Mòr, the last inhabited of the Summer Isles. "
            "The sale included a private postal service and a licence to design the island's own stamps, and 2014 was the first year in more than fifteen with no new issue."
        ),
        "evidence": "The Press and Journal, 20 November 2014, places the end of the private post on Tanera Mòr.",
    },
    {
        "island_id": "osm-relation-6045364",
        "title": "A henge built over a weekend",
        "source_url": "https://www.mayonews.ie/news/achill-henge-still-standing-two-years-on-7525579",
        "source_title": "The Mayo News",
        "commons_file": "File:Beautiful Achill Islands in County Mayo of Ireland.jpg",
        "image_note": "Achill",
        "summary": (
            "On 25 November 2011 more than thirty lorries arrived on Achill with concrete, and by Sunday a circle about 30 metres across stood on a hillside above Pollagh. "
            "The Mayo News reported that two years later the circle was still there, after the courts had ordered it taken down."
        ),
        "evidence": "The Mayo News, 26 November 2013, places the concrete circle above Pollagh on Achill.",
    },
    {
        "island_id": "osm-way-329053691",
        "title": "Wallabies that were meant to fade",
        "source_url": "https://www.newstalk.com/news/from-tasmania-to-malahide-meet-the-500-wallabies-off-the-coast-of-dublin-1747424",
        "source_title": "Newstalk",
        "commons_file": "File:Lambay Island Wallaby.jpg",
        "image_note": "A wallaby on Lambay",
        "summary": (
            "Red-necked wallabies have lived on Lambay, off Dublin, for more than fifty years, starting with a small group brought in the 1950s. "
            "Newstalk reported that the hope had been they would die out quietly, and that the estimate was now more than 500."
        ),
        "evidence": "Newstalk, 21 July 2024, places the wallaby colony on Lambay Island.",
    },
    {
        "island_id": "osm-way-128067375",
        "title": "Tunnels under the fort",
        "source_url": "https://www.irishexaminer.com/news/arid-30789225.html",
        "source_title": "Irish Examiner",
        "commons_file": "File:Entrance to Fort Mitchel on Spike Island - geograph.org.uk - 7686095.jpg",
        "image_note": "The entrance to Fort Mitchel on Spike Island",
        "summary": (
            "The Irish Examiner reported hundreds of metres of tunnels under the old punishment block on Spike Island, with storerooms the managers had not expected. "
            "A 16th-century smugglers' tunnel on the island is known as well, and its entrance has been covered until it can be surveyed."
        ),
        "evidence": "The Irish Examiner, 11 May 2017, places the newly found tunnels on Spike Island in Cork Harbour.",
    },
    {
        "island_id": "osm-relation-3235264",
        "title": "The crew came ashore in a buoy",
        "source_url": "https://www.irishtimes.com/life-and-style/travel/ireland/there-s-nothing-like-sleeping-in-your-car-to-experience-the-atlantic-coast-s-soothing-charms-1.4685789",
        "source_title": "The Irish Times",
        "commons_file": "File:Inisheer Ruins.jpg",
        "image_note": "Inis Oírr",
        "summary": (
            "On Inis Oírr, the wreck of the Plassey sits on the shore as a landmark. "
            "The Irish Times records that in 1960 a breeches buoy brought the whole crew off the ship and onto the island."
        ),
        "evidence": "The Irish Times, 1 October 2021, places the 1960 rescue of the Plassey's crew on Inis Oírr.",
    },
    {
        "island_id": "osm-relation-7230308",
        "title": "A wire under the Atlantic",
        "source_url": "https://www.irishexaminer.com/news/arid-30995445.html",
        "source_title": "Irish Examiner",
        "commons_file": "File:Valentia Island Cable Station and residences - geograph.org.uk - 386249.jpg",
        "image_note": "The cable station on Valentia",
        "summary": (
            "The first telegraph cable under the Atlantic ran from Valentia Island to Newfoundland. "
            "The Irish Examiner records that a cable laid in 1858 failed within a month, and that a new one was laid in July 1866, with a station on the island."
        ),
        "evidence": "The Irish Examiner, 22 April 2020, places the transatlantic cable station on Valentia Island.",
    },
    {
        "island_id": "rathlin",
        "title": "The lamp at the bottom",
        "source_url": "https://www.irishnews.com/news/northernirelandnews/2019/03/11/news/rathlin-lighthouse-celebrates-100-years-since-it-was-first-illuminated-1569314/",
        "source_title": "The Irish News",
        "commons_file": "File:Cliff scenery south of West Lighthouse, Rathlin Island - geograph.org.uk - 646842.jpg",
        "image_note": "The cliff by Rathlin West Light",
        "summary": (
            "Rathlin West Light was built into the cliff and first lit on 10 March 1919. "
            "The Irish News calls it Ireland's only upside-down lighthouse, because the lamp sits at the bottom so the beam can shine under the low fog."
        ),
        "evidence": "The Irish News, 11 March 2019, places the upside-down light on the cliff of Rathlin.",
    },
    {
        "island_id": "osm-way-1493515027",
        "title": "Carcasses with legs",
        "source_url": "https://www.essexlive.news/news/history/essex-island-terrifying-sea-monsters-6341779",
        "source_title": "Essex Live",
        "commons_file": "File:Canvey 060309 1.jpg",
        "image_note": "Canvey Island",
        "summary": (
            "In November 1953 a carcass more than two feet long, with leg-like fins, washed up on Canvey Island. "
            "Essex Live records a second, larger one on the same shore in August 1954, and says the likely identification now is an angler fish."
        ),
        "evidence": "Essex Live, 28 December 2022, places the 1953 and 1954 carcasses on the shore of Canvey Island.",
    },
    {
        "island_id": "osm-way-1493746453",
        "title": "The monkeys came down to the beach",
        "source_url": "https://www.walesonline.co.uk/news/wales-news/escaped-island-dwelling-monkeys-tenby-18618507",
        "source_title": "Wales Online",
        "commons_file": "File:Castle Beach and St Catherine's Fort, Tenby - geograph.org.uk - 6593683.jpg",
        "image_note": "St Catherine's Island and its fort, Tenby",
        "summary": (
            "In 1968 a zoo was opened in the fort on St Catherine's Island, the tidal rock off Tenby. "
            "Wales Online reported that the monkeys later got out, climbed down to the beach, and made off with hats and bags."
        ),
        "evidence": "Wales Online, 19 July 2020, places the zoo and the escaped monkeys on St Catherine's Island.",
    },
    {
        "island_id": "scilly-st-marys",
        "title": "The containers came ashore",
        "source_url": "https://www.cornwalllive.com/news/history/wrecked-cargo-ship-gave-scilly-6850592",
        "source_title": "Cornwall Live",
        "commons_file": "File:Hugh Town Rooftops - geograph.org.uk - 2308903.jpg",
        "image_note": "St Mary's, Isles of Scilly",
        "summary": (
            "At 3am on 26 March 1997 the container ship Cita ran aground off St Mary's and the containers broke open along the south shore. "
            "Cornwall Live reported that people on the island carried off tyres, trainers, toys and blank gravestones."
        ),
        "evidence": "Cornwall Live, 29 March 2022, places the 1997 wreck of the Cita on the south shore of St Mary's.",
    },
    {
        "island_id": "osm-way-462551174",
        "title": "Two tropical birds on one rock",
        "source_url": "https://www.cornwalllive.com/news/cornwall-news/twitchers-flock-isles-scilly-extraordinary-8711118",
        "source_title": "Cornwall Live",
        "commons_file": "File:Bishop Rock Lighthouse - Isles of Scilly.jpg",
        "image_note": "Bishop Rock lighthouse",
        "summary": (
            "In August 2023 a red-footed booby, only the second recorded in Britain, was seen on Bishop Rock lighthouse. "
            "Cornwall Live reported that a brown booby was then found at the foot of the same light, and that having both tropical species there together was called extraordinary."
        ),
        "evidence": "Cornwall Live, 2 September 2023, places both boobies on Bishop Rock.",
    },
    {
        "island_id": "osm-way-1493651984",
        "title": "The wreck that left its rats",
        "source_url": "https://www.walesonline.co.uk/news/local-news/storm-1934-changed-cardigan-island-1882751",
        "source_title": "Wales Online",
        "commons_file": "File:Cardigan Island - geograph.org.uk - 27332.jpg",
        "image_note": "Cardigan Island",
        "summary": (
            "On 15 March 1934 the steamship Herefordshire, under tow to a breaker's yard, broke her ropes and came ashore on Cardigan Island. "
            "Wales Online reported that rats from the wreck then wiped out the island's puffins, and that the rats were not cleared for more than forty-five years."
        ),
        "evidence": "Wales Online, 22 March 2013, places the 1934 wreck and the rats on Cardigan Island.",
    },
    {
        "island_id": "osm-relation-6046655",
        "title": "A king crowned on a chair",
        "source_url": "https://www.dailypost.co.uk/news/north-wales-news/mysterious-kings-bardsey-island-what-23321330",
        "source_title": "North Wales Live",
        "commons_file": "File:Bardsey Island - geograph.org.uk - 6234351.jpg",
        "image_note": "Bardsey",
        "summary": (
            "Bardsey had its own kings from about 1796 until the last died in 1926. "
            "North Wales Live describes a crowning held outdoors on the island, the new king stood on a chair, with boats lying offshore."
        ),
        "evidence": "North Wales Live, 13 March 2022, places the kingship on Bardsey.",
    },
    {
        "island_id": "osm-way-126546636",
        "title": "A cholera ward in the channel",
        "source_url": "https://www.walesonline.co.uk/news/wales-news/flat-holm-island-cardiff-hospital-20011858",
        "source_title": "Wales Online",
        "commons_file": "File:Disused buildings on Flat Holm - geograph.org.uk - 3078781.jpg",
        "image_note": "Disused buildings on Flat Holm",
        "summary": (
            "From 1883 Flat Holm was used as an isolation hospital for cholera brought in by ships. "
            "Wales Online records a permanent hospital built there in 1896, and that the Ministry of Health condemned the building in 1935."
        ),
        "evidence": "Wales Online, 9 March 2021, places the cholera isolation hospital on Flat Holm.",
    },
    {
        "island_id": "brownsea",
        "title": "Leprosy in the squirrels",
        "source_url": "https://www.bournemouthecho.co.uk/news/14479448.update-brownsea-island-squirrels-suffering-from-leprosy/",
        "source_title": "Bournemouth Echo",
        "commons_file": "File:Brownsea Island, southern shore - geograph.org.uk - 1446017.jpg",
        "image_note": "Brownsea Island",
        "summary": (
            "Post-mortem examinations found leprosy in red squirrels on Brownsea Island, and a study was set up there to learn how it spreads. "
            "The Bournemouth Echo reported that only a few of the island's squirrels were ill, and that the risk to people was described as very small."
        ),
        "evidence": "The Bournemouth Echo places the leprosy findings in the red squirrels on Brownsea Island.",
    },
    {
        "island_id": "osm-relation-12913146",
        "title": "A blonde mole on the runway",
        "source_url": "https://jerseyeveningpost.com/uncategorised/2017/11/19/rare-blonde-mole-surfaces/",
        "source_title": "Jersey Evening Post",
        "commons_file": "File:Le Braye Alderney.jpg",
        "image_note": "Alderney",
        "summary": (
            "A blonde mole, about one in ten thousand, turned up while moles were being cleared from Alderney's grass runway. "
            "The Jersey Evening Post reported that the animal was leucistic, with brown eyes, rather than an albino."
        ),
        "evidence": "The Jersey Evening Post, 19 November 2017, places the blonde mole on Alderney's grass runway.",
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
