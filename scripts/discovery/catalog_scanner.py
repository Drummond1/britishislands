"""Catalog Scanner — harvest island candidates from open gazetteers."""

from __future__ import annotations

import csv
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from . import common as c
from . import marine_regions_gazetteer as mrg

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import ingest_sources as ing  # noqa: E402

WIKI_LIST_TITLES = [
    "List of islands of Scotland",
    "List of islands of England",
    "List of islands of Wales",
    "List of islands of Ireland",
    "List of islands of the British Isles",
    "List of islands of the Inner Hebrides",
    "List of islands of the Outer Hebrides",
    "List of islands of Orkney",
    "List of islands of Shetland",
    "List of islands of the Channel Islands",
    "List of islands of the Isle of Man",
    "List of islands of Northern Ireland",
    "List of islands of the Firth of Clyde",
    "List of islands of the Clyde",
    "List of islands of Cornwall",
    "List of islands of Dorset",
]

SKIP_LINK_PREFIXES = (
    "Category:",
    "File:",
    "Image:",
    "List of",
    "User:",
    "Wikipedia:",
    "Template:",
    "Help:",
    "Portal:",
)

ISLANDISH = re.compile(
    r"\b(island|islet|holm|holme|eyot|ait|skerry|stack|rock|inch|inis|eilean|ynys|oileán|oiléan)\b",
    re.I,
)

DOBIH_ISLANDS_QUERY = """
SELECT ?item ?itemLabel ?coord ?dobihId
WHERE {
  ?item wdt:P31/wdt:P279* wd:Q23442 .
  ?item wdt:P625 ?coord .
  OPTIONAL { ?item wdt:P5283 ?dobihId . }
  FILTER(
    EXISTS { ?item wdt:P17 wd:Q145 . }
    || EXISTS { ?item wdt:P17 wd:Q27 . }
    || EXISTS { ?item wdt:P17 wd:Q9676 . }
    || EXISTS { ?item wdt:P17 wd:Q785 . }
    || EXISTS { ?item wdt:P17 wd:Q3311985 . }
  )
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
"""


def _source_hint(name: str, url: str, license_name: str) -> dict[str, str]:
    return {"name": name, "url": url, "license": license_name}


def _from_ingest(
    record: dict,
    *,
    feature_kind: str,
    scan_confidence: str,
    source_name: str,
    source_url: str,
    license_name: str,
) -> dict[str, Any]:
    lat, lng = record["lat"], record["lng"]
    wikidata = record.get("wikidata") or ""
    candidate_id = record.get("id") or (f"wd-{wikidata}" if wikidata else c.slugify(record["name"], "catalog-"))
    sources = record.get("sources") or []
    hints = [
        _source_hint(
            (src.get("name") or source_name),
            (src.get("url") or source_url),
            (src.get("licence") or src.get("license") or license_name),
        )
        for src in sources
    ] or [_source_hint(source_name, source_url, license_name)]
    return {
        "candidateId": candidate_id,
        "name": record["name"],
        "lat": round(float(lat), 5),
        "lng": round(float(lng), 5),
        "nation": record.get("nation") or c.nation_for(lat, lng),
        "featureKind": feature_kind,
        "osmType": record.get("osmType"),
        "osmId": record.get("osmId"),
        "osmPlace": record.get("osmPlace") or feature_kind,
        "wikidata": wikidata,
        "wikipedia": record.get("wikipedia") or "",
        "aliases": list(record.get("aliases") or []),
        "tags": sorted(set(record.get("tags") or ["island"])),
        "scanConfidence": scan_confidence,
        "sourceHints": hints,
    }


def _from_wikipedia_page(
    title: str,
    *,
    lat: float,
    lng: float,
    wikidata: str,
    list_page: str,
) -> dict[str, Any]:
    wiki_url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
    return {
        "candidateId": f"wp-{wikidata or c.slugify(title, 'wp-')}",
        "name": title,
        "lat": round(lat, 5),
        "lng": round(lng, 5),
        "nation": c.nation_for(lat, lng),
        "featureKind": "island",
        "osmType": None,
        "osmId": None,
        "osmPlace": "island",
        "wikidata": wikidata,
        "wikipedia": wiki_url,
        "aliases": [],
        "tags": ["island", "wikipedia-list"],
        "scanConfidence": "high" if wikidata else "medium",
        "sourceHints": [
            _source_hint(
                "Wikipedia island list",
                f"https://en.wikipedia.org/wiki/{list_page.replace(' ', '_')}",
                "CC-BY-SA-4.0",
            ),
            _source_hint("Wikipedia article", wiki_url, "CC-BY-SA-4.0"),
        ],
    }


def _from_open_names(row: dict[str, str]) -> dict[str, Any] | None:
    name = (row.get("NAME1") or row.get("name") or row.get("Name") or "").strip()
    if not name:
        return None
    try:
        lat = float(row.get("LATITUDE") or row.get("lat") or row.get("Latitude") or "")
        lng = float(row.get("LONGITUDE") or row.get("lng") or row.get("Longitude") or "")
    except ValueError:
        return None
    if not c.in_remit(lat, lng):
        return None
    feature = (row.get("LOCAL_TYPE") or row.get("FEATURE_TYPE") or row.get("type") or "").lower()
    if feature and "island" not in feature and "islet" not in feature:
        return None
    return {
        "candidateId": f"os-opennames-{c.slugify(name)}",
        "name": name,
        "lat": round(lat, 5),
        "lng": round(lng, 5),
        "nation": c.nation_for(lat, lng),
        "featureKind": "islet" if "islet" in feature else "island",
        "osmType": None,
        "osmId": None,
        "osmPlace": "island",
        "wikidata": "",
        "wikipedia": "",
        "aliases": [v for k, v in row.items() if k.upper().startswith("NAME") and v and k.upper() != "NAME1"],
        "tags": ["island", "os-opennames"],
        "scanConfidence": "medium",
        "sourceHints": [
            _source_hint(
                "OS Open Names",
                "https://osdatahub.os.uk/downloads/open/OpenNames",
                "OGL v3.0",
            )
        ],
    }


def _from_dobih_row(row: dict[str, Any]) -> dict[str, Any] | None:
    wkt = (row.get("coord") or {}).get("value", "")
    latlng = ing.parse_point_wkt(wkt) if wkt else None
    if not latlng:
        return None
    lat, lng = latlng
    if not c.in_remit(lat, lng):
        return None
    qid = row["item"]["value"].rsplit("/", 1)[-1]
    label = (row.get("itemLabel") or {}).get("value", "")
    if not label or label == qid:
        return None
    dobih = (row.get("dobihId") or {}).get("value", "")
    hints = [
        _source_hint(
            "Database of British and Irish Hills",
            "https://www.hills-database.co.uk/",
            "CC-BY-4.0",
        ),
        _source_hint("Wikidata", f"https://www.wikidata.org/wiki/{qid}", "CC0"),
    ]
    return {
        "candidateId": f"dobih-{qid}",
        "name": label,
        "lat": round(lat, 5),
        "lng": round(lng, 5),
        "nation": c.nation_for(lat, lng),
        "featureKind": "island",
        "osmType": None,
        "osmId": None,
        "osmPlace": "island",
        "wikidata": qid,
        "wikipedia": "",
        "aliases": [],
        "tags": ["island", "dobih"],
        "scanConfidence": "high" if dobih else "medium",
        "sourceHints": hints,
    }


def _link_title_ok(title: str) -> bool:
    if not title or title.startswith(SKIP_LINK_PREFIXES):
        return False
    if title.endswith("(disambiguation)"):
        return False
    return bool(ISLANDISH.search(title))


def _wiki_links_for_page(page_title: str, cache: dict[str, Any]) -> list[str]:
    if page_title in cache and cache[page_title].get("links"):
        return list(cache[page_title]["links"])
    titles: list[str] = []
    cont: str | None = None
    while True:
        params: dict[str, Any] = {
            "action": "query",
            "format": "json",
            "prop": "links",
            "titles": page_title,
            "plnamespace": 0,
            "pllimit": 500,
        }
        if cont:
            params["plcontinue"] = cont
        payload = c.get_json("https://en.wikipedia.org/w/api.php", params)
        pages = (payload.get("query") or {}).get("pages") or {}
        for page in pages.values():
            for link in page.get("links") or []:
                title = (link.get("title") or "").strip()
                if _link_title_ok(title):
                    titles.append(title)
        cont = (payload.get("continue") or {}).get("plcontinue")
        if not cont:
            break
        time.sleep(c.DELAY_S)
    cache[page_title] = {"links": titles, "fetched": time.time()}
    c.save_json(c.CACHE_WP_LISTS, cache)
    return titles


def _resolve_wikipedia_titles(titles: list[str], list_page: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    batch = 50
    for i in range(0, len(titles), batch):
        chunk = titles[i : i + batch]
        params = {
            "action": "query",
            "format": "json",
            "prop": "coordinates|pageprops",
            "ppprop": "wikibase_item",
            "titles": "|".join(chunk),
            "redirects": 1,
            "coprop": "primary",
        }
        try:
            payload = c.get_json("https://en.wikipedia.org/w/api.php", params)
        except Exception as exc:
            print(f"Wikipedia batch {i}: {exc!r}", file=sys.stderr)
            continue
        normalized: dict[str, str] = {}
        for item in (payload.get("query") or {}).get("normalized") or []:
            normalized[item["to"]] = item["from"]
        for redir in (payload.get("query") or {}).get("redirects") or []:
            normalized.setdefault(redir["to"], redir["from"])
        for page in (payload.get("query") or {}).get("pages", {}).values():
            if page.get("missing"):
                continue
            coords = page.get("coordinates") or []
            if not coords:
                continue
            lat, lng = coords[0].get("lat"), coords[0].get("lon")
            if lat is None or lng is None or not c.in_remit(float(lat), float(lng)):
                continue
            title = page.get("title") or normalized.get(page.get("title", ""), "")
            if not title:
                continue
            qid = (page.get("pageprops") or {}).get("wikibase_item", "")
            out.append(
                _from_wikipedia_page(
                    title,
                    lat=float(lat),
                    lng=float(lng),
                    wikidata=qid,
                    list_page=list_page,
                )
            )
        time.sleep(c.DELAY_S)
    return out


def _collect_wikipedia_lists() -> list[dict[str, Any]]:
    cache = c.load_json(c.CACHE_WP_LISTS, {})
    candidates: list[dict[str, Any]] = []
    for page in WIKI_LIST_TITLES:
        print(f"→ Wikipedia list: {page}", file=sys.stderr)
        links = _wiki_links_for_page(page, cache)
        resolved = _resolve_wikipedia_titles(links, page)
        print(f"  {len(resolved)} located links", file=sys.stderr)
        candidates.extend(resolved)
    return candidates


def _collect_open_names() -> list[dict[str, Any]]:
    if not c.OPEN_NAMES_PATH.exists():
        return []
    print(f"→ OS Open Names: {c.OPEN_NAMES_PATH.name}", file=sys.stderr)
    out: list[dict[str, Any]] = []
    with c.OPEN_NAMES_PATH.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            candidate = _from_open_names(row)
            if candidate:
                out.append(candidate)
    print(f"  {len(out)} island features", file=sys.stderr)
    return out


def _collect_dobih_islands() -> list[dict[str, Any]]:
    cache_path = c.DATA / "cache_discovery_dobih_islands.json"
    cache = c.load_json(cache_path, {})
    if cache.get("rows"):
        rows = cache["rows"]
        print(f"→ DoBIH island crosswalk: cached ({len(rows)} rows)", file=sys.stderr)
    else:
        print("→ DoBIH island crosswalk: Wikidata SPARQL", file=sys.stderr)
        try:
            payload = c.post_sparql(DOBIH_ISLANDS_QUERY)
            rows = payload.get("results", {}).get("bindings", [])
            cache = {"rows": rows, "fetched": time.time()}
            c.save_json(cache_path, cache)
        except Exception as exc:
            print(f"  DoBIH SPARQL failed: {exc!r}", file=sys.stderr)
            return []
    out: list[dict[str, Any]] = []
    for row in rows:
        candidate = _from_dobih_row(row)
        if candidate:
            out.append(candidate)
    print(f"  {len(out)} island rows", file=sys.stderr)
    return out


def _collect_ingest_sources() -> tuple[list[dict[str, Any]], dict[str, int]]:
    counts: dict[str, int] = {}
    collected: list[dict[str, Any]] = []

    actions = (
        ("wikidata", ing.action_wikidata, "island", "high", "Wikidata", "https://www.wikidata.org/", "CC0"),
        (
            "wikipedia_thames",
            ing.action_thames,
            "river",
            "high",
            "Wikipedia",
            ing.THAMES_URL,
            "CC-BY-SA-4.0",
        ),
        (
            "crannogs",
            ing.action_crannogs,
            "island",
            "medium",
            "heritage-register",
            "https://www.historicenvironment.scot/",
            "OGL v3.0",
        ),
        (
            "designations",
            ing.action_designations,
            "island",
            "medium",
            "designation-boundary",
            "https://www.nature.scot/",
            "OGL v3.0",
        ),
    )
    for key, fn, feature_kind, confidence, source_name, source_url, license_name in actions:
        try:
            rows = fn()
        except Exception as exc:
            print(f"  {key} failed: {exc!r}", file=sys.stderr)
            counts[key] = 0
            continue
        counts[key] = len(rows)
        collected.extend(
            _from_ingest(
                row,
                feature_kind=feature_kind,
                scan_confidence=confidence,
                source_name=source_name,
                source_url=source_url,
                license_name=license_name,
            )
            for row in rows
        )
    return collected, counts


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        key = candidate.get("wikidata") or candidate.get("candidateId") or c.slugify(candidate.get("name", ""))
        existing = by_key.get(key)
        if not existing:
            by_key[key] = candidate
            continue
        hints = {(h.get("name"), h.get("url")) for h in existing.get("sourceHints") or []}
        for hint in candidate.get("sourceHints") or []:
            token = (hint.get("name"), hint.get("url"))
            if token not in hints:
                existing.setdefault("sourceHints", []).append(hint)
                hints.add(token)
        if not existing.get("wikidata") and candidate.get("wikidata"):
            existing["wikidata"] = candidate["wikidata"]
        if not existing.get("wikipedia") and candidate.get("wikipedia"):
            existing["wikipedia"] = candidate["wikipedia"]
    return list(by_key.values())


def run(*, limit: int | None = None) -> dict[str, Any]:
    islands = c.load_islands()
    index = c.build_island_index(islands)
    scan = c.load_json(c.SCAN_PATH, {})
    existing_candidates = list(scan.get("candidates") or [])

    source_counts: dict[str, int] = {}
    collected: list[dict[str, Any]] = []

    ingest_rows, ingest_counts = _collect_ingest_sources()
    source_counts.update(ingest_counts)
    collected.extend(ingest_rows)

    wiki_rows = _collect_wikipedia_lists()
    source_counts["wikipedia_lists"] = len(wiki_rows)
    collected.extend(wiki_rows)

    open_rows = _collect_open_names()
    source_counts["os_opennames"] = len(open_rows)
    collected.extend(open_rows)

    dobih_rows = _collect_dobih_islands()
    source_counts["dobih"] = len(dobih_rows)
    collected.extend(dobih_rows)

    try:
        if os.environ.get("DISCOVERY_SKIP_MARINE") == "1":
            mr_rows = []
            print("→ Marine Regions: skipped (DISCOVERY_SKIP_MARINE=1)", file=sys.stderr)
        else:
            mr_refresh = os.environ.get("DISCOVERY_REFRESH_MARINE") == "1"
            mr_rows = mrg.collect_candidates(refresh=mr_refresh)
    except Exception as exc:
        print(f"  marine_regions failed: {exc!r}", file=sys.stderr)
        mr_rows = []
    source_counts["marine_regions"] = len(mr_rows)
    collected.extend(mr_rows)

    collected = _dedupe_candidates(collected)

    missing: list[dict[str, Any]] = []
    matched = 0
    out_of_remit = 0
    for candidate in collected:
        if candidate.get("nation") == "British Isles":
            out_of_remit += 1
            continue
        if c.find_existing_match(candidate, index):
            matched += 1
            continue
        missing.append(candidate)
        if limit and len(missing) >= limit:
            break

    merged = _dedupe_candidates(existing_candidates + missing)
    report = {
        "agent": "catalog_scanner",
        "bbox": c.UK_BBOX,
        "islandsInDatabase": len(islands),
        "sourceCounts": source_counts,
        "referenceOnlySources": [
            {
                "name": "Haswell-Smith, The Scottish Islands",
                "status": "reference-only",
                "reason": "Copyrighted book; cross-validation only.",
            },
            {
                "name": "Vision of Britain historical gazetteer",
                "status": "reference-only",
                "reason": "No bulk open-licence redistribution path.",
            },
            {
                "name": "OS MasterMap",
                "status": "reference-only",
                "reason": "Commercial product; use OS Open Names / Boundary-Line instead.",
            },
            {
                "name": "NBN Atlas / GBIF / JNCC marine layers",
                "status": "enrichment-not-gazetteer",
                "reason": "Biodiversity and MPA context — use for tags/enrichment, not bulk island discovery.",
            },
            {
                "name": "NRS / ONS inhabited-island tables",
                "status": "deferred",
                "reason": "Population enrichment via staged census CSVs; not a discovery feed without boundary geometry.",
            },
        ],
        "catalogCandidates": len(collected),
        "alreadyInDatabase": matched,
        "outOfRemit": out_of_remit,
        "missingCandidates": len(missing),
        "candidates": missing,
        "mergedScanCandidates": len(merged),
    }
    c.save_json(c.CATALOG_PATH, report)

    scan.update(
        {
            "catalogMergedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "catalogMissingCandidates": len(missing),
            "missingCandidates": len(merged),
            "candidates": merged,
        }
    )
    c.save_json(c.SCAN_PATH, scan)

    print(
        f"Catalog Scanner: {len(missing)} new catalog candidates "
        f"({matched} already in DB); scan file now {len(merged)} total",
        file=sys.stderr,
    )
    return report
