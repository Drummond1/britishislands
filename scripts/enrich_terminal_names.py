#!/usr/bin/env python3
"""Add regional-language names (Gàidhlig / Cymraeg / Gaeilge / Gaelg /
Kernewek / Français) to ``data/ferry_terminals.json`` for the major
mainland and island ferry ports.

The set is hand-curated rather than fetched from Wikidata: it avoids the
rate-limit pain that hit ``scripts/enrich_names.py`` and gives accurate
names for the ports that matter most (every CalMac mainland port, every
Orkney/Shetland port, every Aran/Cork/Cornish port we care about). The
manual seeds in ``scripts/seed_ferries_manual.py`` already cover Welsh,
Irish, and Manx terminals; this script supplements OSM- and GTFS-sourced
terminals that we didn't seed by hand.

Run::

    python3 scripts/enrich_terminal_names.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TERMINALS_PATH = ROOT / "data" / "ferry_terminals.json"

# Stable substring → {lang: localised_name} mapping. We match the
# terminal's English name (case-insensitive substring) to keep this
# resilient against the slight naming differences between OSM, GTFS,
# manual and Wikipedia sources.
NAME_MAP: list[tuple[str, dict[str, str]]] = [
    # CalMac mainland
    ("oban",         {"gd": "An t-Òban"}),
    ("mallaig",      {"gd": "Malaig"}),
    ("ullapool",     {"gd": "Ullapul"}),
    ("uig",          {"gd": "Ùige"}),
    ("kennacraig",   {"gd": "Ceann a' Charraig"}),
    ("ardrossan",    {"gd": "Àird Rosain"}),
    ("largs",        {"gd": "An Leargaidh Ghallta"}),
    ("wemyss bay",   {"gd": "Bàgh Uaimh"}),
    ("gourock",      {"gd": "Guireag"}),
    ("tarbert",      {"gd": "An Tairbeart"}),
    ("portavadie",   {"gd": "Port Bhàdaidh"}),
    ("colintraive",  {"gd": "Caol an t-Snàimh"}),
    ("rhubodach",    {"gd": "Rubha Bodach"}),
    ("claonaig",     {"gd": "Claonaig"}),
    ("lochranza",    {"gd": "Loch Raonasa"}),
    ("brodick",      {"gd": "Breadhaig"}),
    ("craignure",    {"gd": "Creag an Iubhair"}),
    ("tobermory",    {"gd": "Tobar Mhoire"}),
    ("fionnphort",   {"gd": "Fionnphort"}),
    ("iona",         {"gd": "Eilean Ì"}),
    ("lochaline",    {"gd": "Loch Àlainn"}),
    ("fishnish",     {"gd": "Fionnais"}),
    ("colonsay",     {"gd": "Colbhasa"}),
    ("port askaig",  {"gd": "Port Asgaig"}),
    ("port ellen",   {"gd": "Port Eilein"}),
    ("scalasaig",    {"gd": "Sgalasaig"}),
    ("kerrera",      {"gd": "Cearrara"}),
    ("lismore",      {"gd": "Lios Mòr"}),
    ("achnacroish",  {"gd": "Achadh na Croise"}),
    ("rum",          {"gd": "Rùm"}),
    ("eigg",         {"gd": "Eige"}),
    ("muck",         {"gd": "Eilean nam Muc"}),
    ("canna",        {"gd": "Canaigh"}),
    ("armadale",     {"gd": "Àrmadal"}),
    ("kyle of lochalsh", {"gd": "Caol Loch Aillse"}),
    ("kyleakin",     {"gd": "Caol Acain"}),
    ("portree",      {"gd": "Port Rìgh"}),
    ("staffin",      {"gd": "Stafainn"}),
    ("lochmaddy",    {"gd": "Loch nam Madadh"}),
    ("lochboisdale", {"gd": "Loch Baghasdail"}),
    ("eriskay",      {"gd": "Èirisgeigh"}),
    ("leverburgh",   {"gd": "An t-Òb"}),
    ("berneray",     {"gd": "Beàrnaraigh"}),
    ("stornoway",    {"gd": "Steòrnabhagh"}),
    ("tarbert (harris)", {"gd": "An Tairbeart"}),
    ("castlebay",    {"gd": "Bàgh a' Chaisteil"}),
    ("ardmhor",      {"gd": "Àird Mhór"}),

    # NorthLink + Pentland + Orkney + Shetland
    ("aberdeen",     {"gd": "Obar Dheathain"}),
    ("kirkwall",     {}),                          # Scots/Norse, no canonical gd
    ("scrabster",    {"gd": "Sgrabstair"}),
    ("stromness",    {}),
    ("gills bay",    {"gd": "Bàgh Ghills"}),
    ("st margaret's hope", {}),
    ("lerwick",      {}),
    ("yell",         {}),
    ("unst",         {}),
    ("fetlar",       {}),

    # Wales
    ("holyhead",     {"cy": "Caergybi"}),
    ("fishguard",    {"cy": "Abergwaun"}),
    ("pembroke",     {"cy": "Penfro"}),
    ("tenby",        {"cy": "Dinbych-y-pysgod"}),
    ("aberdaron",    {"cy": "Aberdaron"}),
    ("caldey",       {"cy": "Ynys Bŷr"}),
    ("bardsey",      {"cy": "Ynys Enlli"}),
    ("skomer",       {"cy": "Sgomer"}),
    ("skokholm",     {"cy": "Sgogwm"}),
    ("grassholm",    {"cy": "Gwales"}),

    # Northern Ireland
    ("ballycastle",  {"ga": "Baile an Chaistil"}),
    ("rathlin",      {"ga": "Reachlainn"}),
    ("strangford",   {"ga": "Baile Loch Cuan"}),
    ("portaferry",   {"ga": "Port an Pheire"}),
    ("larne",        {"ga": "Latharna"}),
    ("belfast",      {"ga": "Béal Feirste"}),

    # Republic of Ireland
    ("rossaveal",    {"ga": "Ros a' Mhíl"}),
    ("ros a' mhíl",  {"ga": "Ros a' Mhíl"}),
    ("doolin",       {"ga": "Dúlainn"}),
    ("cleggan",      {"ga": "Cloigeann"}),
    ("inishbofin",   {"ga": "Inis Bó Finne"}),
    ("inishmore",    {"ga": "Inis Mór"}),
    ("inishmaan",    {"ga": "Inis Meáin"}),
    ("inisheer",     {"ga": "Inis Oírr"}),
    ("roonagh",      {"ga": "Cuan Ruanaí"}),
    ("clare island", {"ga": "Cliara"}),
    ("inishturk",    {"ga": "Inis Toirc"}),
    ("magheroarty",  {"ga": "Machaire Rabhartaigh"}),
    ("tory",         {"ga": "Toraigh"}),
    ("baltimore",    {"ga": "Baile an Tí Mhóir"}),
    ("cape clear",   {"ga": "Cléire"}),
    ("sherkin",      {"ga": "Inis Arcáin"}),
    ("castletownbere", {"ga": "Baile Chaisleáin Bhéarra"}),
    ("bere island",  {"ga": "Béarra"}),
    ("cobh",         {"ga": "An Cóbh"}),
    ("spike",        {"ga": "Inis Píc"}),
    ("portmagee",    {"ga": "An Caladh"}),
    ("skellig michael", {"ga": "Sceilg Mhichíl"}),
    ("dublin port",  {"ga": "Calafort Bhaile Átha Cliath"}),

    # IoM
    ("douglas",      {"gv": "Doolish"}),
    ("ramsey",       {"gv": "Rhumsaa"}),
    ("peel",         {"gv": "Purt ny h-Inshey"}),
    ("port erin",    {"gv": "Purt Çhiarn"}),

    # Channel Islands
    ("st helier",    {"fr": "St Hélier"}),
    ("st peter port", {"fr": "Saint-Pierre-Port"}),
    ("st malo",      {"fr": "Saint-Malo"}),
    ("granville",    {"fr": "Granville"}),
    ("diélette",     {"fr": "Diélette"}),
    ("dielette",     {"fr": "Diélette"}),
    ("carteret",     {"fr": "Carteret"}),
    ("sark",         {"fr": "Sercq", "nrf": "Sèr"}),
    ("alderney",     {"fr": "Aurigny", "nrf": "Aoeur'gny"}),
    ("braye",        {"fr": "La Braye"}),
    ("chausey",      {"fr": "Chausey"}),

    # Cornwall
    ("penzance",     {"kw": "Pennsans"}),
    ("st mary's",    {"kw": "Ennor"}),
    ("scilly",       {"kw": "Syllan"}),
]


def main() -> int:
    doc = json.loads(TERMINALS_PATH.read_text(encoding="utf-8"))
    terminals = doc.get("terminals", [])
    enriched = 0
    for t in terminals:
        name = (t.get("name") or "").lower()
        if not name:
            continue
        existing = t.setdefault("names", {})
        # Always set English label if missing.
        if not existing.get("en"):
            existing["en"] = t["name"]
        for substr, mapping in NAME_MAP:
            if substr in name:
                for lang, val in mapping.items():
                    if val and not existing.get(lang):
                        existing[lang] = val
                        enriched += 1
    tmp = TERMINALS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(TERMINALS_PATH)
    print(f"Enriched {enriched} terminal-name fields across {len(terminals)} terminals.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
