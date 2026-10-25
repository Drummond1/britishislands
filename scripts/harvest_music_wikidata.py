#!/usr/bin/env python3
"""Harvest cited bands, works, and musicians from Wikidata.

Writes data/interest/candidates/music-wikidata.json and caches SPARQL
responses at data/cache_wikidata_music_extra.json. Does not publish the
interest index and does not edit islands.json.

A row is kept only when a Wikidata statement ties that group, work, or
person to an atlas island. People need an English Wikipedia article or a
MusicBrainz artist id. Towns, Great Britain, and Ireland are not places.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import urllib.parse
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from interest_categories import (  # noqa: E402
    WIKIDATA_ENDPOINT,
    Atlas,
    _atlas_qids,
    fetch_island_place_qids,
    fold,
    http_json,
    load_json,
    save_json,
    utc_now,
)
from artwork_harvest_common import (  # noqa: E402
    existing_music_keys,
    music_row,
)

CACHE_PATH = ROOT / "data" / "cache_wikidata_music_extra.json"
OUTPUT_PATH = ROOT / "data" / "interest" / "candidates" / "music-wikidata.json"
USER_AGENT = "isles-of-britain/0.1 (music-wikidata-harvest; research)"
CACHE_VERSION = 1
BATCH_SIZE = 20
PER_ISLAND_CAP = 70

# Candidate classes. The label query drops any QID whose English label is
# not a music class. Q870 is kept only when the label is "folk song".
# Q1062404 is kept only when it is a performing ensemble. Q105543609 is
# kept only when the label names a musical work.
CLASS_CANDIDATES = [
    ("Q215380", "group", "musical group"),
    ("Q5741069", "group", "rock band"),
    ("Q2088357", "group", "musical ensemble"),
    ("Q1062404", "group", "choir"),
    ("Q42998", "group", "orchestra"),
    ("Q7366", "work", "song"),
    ("Q482994", "work", "album"),
    ("Q134556", "work", "single"),
    ("Q34627", "work", "extended play"),
    ("Q207628", "work", "musical composition"),
    ("Q870", "work", "folk song"),
    ("Q1344", "work", "opera"),
    ("Q105543609", "work", "musical work"),
    ("Q639669", "person", "musician"),
    ("Q177220", "person", "singer"),
    ("Q36834", "person", "composer"),
    ("Q488205", "person", "singer-songwriter"),
]

GROUP_LABELS = {
    "musical group",
    "rock band",
    "musical ensemble",
    "choir",
    "orchestra",
}
WORK_LABELS = {
    "song",
    "album",
    "single",
    "extended play",
    "musical composition",
    "composed musical work",
    "folk song",
    "opera",
    "musical work",
    "musical work/composition",
}
PERSON_LABELS = {
    "musician",
    "singer",
    "composer",
    "singer-songwriter",
    "singer songwriter",
}
RELEASE_LABELS = {"song", "album", "single", "extended play", "folk song", "opera"}
COMPOSITION_LABELS = {
    "musical composition",
    "composed musical work",
    "musical work",
    "musical work/composition",
}

GROUP_PROPS = ("P740", "P159", "P2541", "P937")
WORK_PROPS = ("P921", "P840", "P180", "P138", "P1071", "P276")
PERSON_PROPS = ("P19", "P937")

PROP_NAMES = {
    "P740": "location of formation",
    "P159": "headquarters location",
    "P2541": "operating area",
    "P937": "work location",
    "P921": "main subject",
    "P840": "narrative location",
    "P180": "depicts",
    "P138": "named after",
    "P1071": "location of creation",
    "P276": "location",
    "P19": "place of birth",
}
PROP_ORDER = list(PROP_NAMES)

KIND_PRIORITY = [
    "rock band",
    "orchestra",
    "choir",
    "musical ensemble",
    "musical group",
    "opera",
    "single",
    "extended play",
    "album",
    "folk song",
    "song",
    "composed musical work",
    "musical composition",
    "musical work/composition",
    "musical work",
    "singer songwriter",
    "composer",
    "singer",
    "musician",
]

FAMILY_PROPS = {
    "group": set(GROUP_PROPS),
    "work": set(WORK_PROPS),
    "person": set(PERSON_PROPS),
}

NATION_NAMES = {
    "great britain",
    "britain",
    "united kingdom",
    "uk",
    "ireland",
    "northern ireland",
    "republic of ireland",
    "england",
    "scotland",
    "wales",
}
BLOCKED_PLACE_QIDS = {
    "Q145",
    "Q21",
    "Q22",
    "Q25",
    "Q26",
    "Q27",
    "Q236",
    "Q22890",
}


def log(message: str) -> None:
    print(message, flush=True)


def norm_label(text: str) -> str:
    text = fold(text).replace("-", " ")
    return re.sub(r"\s+", " ", text).strip()


def qid_of(value: str) -> str:
    return (value or "").rstrip("/").rsplit("/", 1)[-1]


def is_q_number(label: str) -> bool:
    return bool(re.fullmatch(r"Q\d+", (label or "").strip()))


def commons_file(url: str) -> str:
    if not url:
        return ""
    name = urllib.parse.unquote(url.rstrip("/").rsplit("/", 1)[-1]).replace("_", " ")
    name = name.split("?", 1)[0].strip()
    if not name or name.lower() in {"special:filepath", "wiki"}:
        return ""
    return name if name.startswith("File:") else f"File:{name}"


def wiki_title(url: str) -> str:
    if not url:
        return ""
    return urllib.parse.unquote(url.rstrip("/").rsplit("/", 1)[-1]).replace("_", " ")


def article_word(kind: str) -> str:
    return "an" if fold(kind)[:1] in "aeiou" else "a"


def good_label(label: str) -> bool:
    label = (label or "").strip()
    if not label or is_q_number(label):
        return False
    if re.search(r"\bpossibly\b", label, re.I):
        return False
    return True


def is_nation_name(label: str) -> bool:
    return fold(label) in NATION_NAMES


def values_clause(qids: list[str], prefix: str = "wd:") -> str:
    return " ".join(f"{prefix}{qid}" for qid in qids)


def wikidata_sparql(query: str, attempts: int = 4) -> dict:
    """POST a SPARQL query. Retry with backoff, then raise so the caller can split."""
    body = urllib.parse.urlencode({"format": "json", "query": query}).encode("utf-8")
    last_error = None
    for attempt in range(attempts):
        try:
            return http_json(
                WIKIDATA_ENDPOINT,
                data=body,
                headers={
                    "Accept": "application/sparql-results+json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                timeout=60,
                user_agent=USER_AGENT,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            last_error = exc
            code = getattr(exc, "returncode", "error")
            log(f"wikidata attempt {attempt + 1} failed: {code}")
            time.sleep(15 * (attempt + 1))
    raise RuntimeError(f"Wikidata request failed: {last_error}")


def parse_binding(binding: dict) -> dict:
    direct = binding.get("direct", {}).get("value") or ""
    return {
        "work": qid_of(binding.get("work", {}).get("value") or ""),
        "label": (binding.get("workLabel", {}).get("value") or "").strip(),
        "place": qid_of(binding.get("place", {}).get("value") or ""),
        "type": qid_of(binding.get("type", {}).get("value") or ""),
        "typeLabel": (binding.get("typeLabel", {}).get("value") or "").strip(),
        "root": qid_of(binding.get("root", {}).get("value") or ""),
        "article": binding.get("article", {}).get("value") or "",
        "mb": binding.get("mbArtist", {}).get("value") or "",
        "image": binding.get("image", {}).get("value") or "",
        "prop": direct.rsplit("/", 1)[-1],
    }


def query_subclasses(qids: list[str], roots: list[str], props: tuple[str, ...]) -> str:
    """Groups and works, including subclasses such as musical duo, punk band, and choir.

    Direct P31 misses bands typed only as a narrower class. Choir's real class
    is a subclass of musical group; the candidate choir QID is not that class.
    """
    return f"""
SELECT DISTINCT ?work ?workLabel ?place ?type ?typeLabel ?root ?article ?mbArtist ?image ?direct WHERE {{
  VALUES ?place {{ {values_clause(qids)} }}
  VALUES ?direct {{ {values_clause(list(props), "wdt:")} }}
  ?work ?direct ?place .
  FILTER(?work != ?place)
  ?work wdt:P31 ?type .
  ?type wdt:P279* ?root .
  VALUES ?root {{ {values_clause(roots)} }}
  FILTER NOT EXISTS {{ ?work wdt:P31 wd:Q6619719 }}
  OPTIONAL {{ ?article schema:about ?work ; schema:isPartOf <https://en.wikipedia.org/> . }}
  OPTIONAL {{ ?work wdt:P434 ?mbArtist }}
  OPTIONAL {{ ?work wdt:P18 ?image }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
"""


def query_classes() -> str:
    values = values_clause([qid for qid, _group, _expect in CLASS_CANDIDATES])
    return f"""
SELECT ?item ?itemLabel WHERE {{
  VALUES ?item {{ {values} }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
"""


def query_items(qids: list[str], types: list[str], props: tuple[str, ...], mode: str) -> str:
    """One SPARQL query for groups, works, or people on a batch of islands."""
    if mode == "person":
        typed = f"""
  ?work wdt:P31 wd:Q5 .
  ?work wdt:P106 ?type .
  VALUES ?type {{ {values_clause(types)} }}"""
        cited = "FILTER(BOUND(?article) || BOUND(?mbArtist))"
    else:
        typed = f"""
  ?work wdt:P31 ?type .
  VALUES ?type {{ {values_clause(types)} }}"""
        cited = ""
    return f"""
SELECT DISTINCT ?work ?workLabel ?place ?type ?article ?mbArtist ?image ?direct WHERE {{
  VALUES ?place {{ {values_clause(qids)} }}
  VALUES ?direct {{ {values_clause(list(props), "wdt:")} }}
  ?work ?direct ?place .
  FILTER(?work != ?place)
  {typed}
  OPTIONAL {{ ?article schema:about ?work ; schema:isPartOf <https://en.wikipedia.org/> . }}
  OPTIONAL {{ ?work wdt:P434 ?mbArtist }}
  OPTIONAL {{ ?work wdt:P18 ?image }}
  {cited}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
"""


def load_cache() -> dict:
    cache = load_json(CACHE_PATH, {})
    if not isinstance(cache, dict) or cache.get("version") != CACHE_VERSION:
        cache = {"version": CACHE_VERSION}
    cache.setdefault("classLabels", {})
    cache.setdefault("batches", {})
    cache.setdefault("failed", [])
    return cache


def class_is_music(qid: str, group: str, label: str) -> bool:
    folded = norm_label(label)
    if not label or is_q_number(label):
        return False
    if qid == "Q870":
        return folded == "folk song"
    if qid == "Q1062404":
        return folded in GROUP_LABELS
    if qid == "Q105543609":
        return "musical work" in folded
    if group == "group":
        return folded in GROUP_LABELS
    if group == "work":
        return folded in WORK_LABELS
    if group == "person":
        return folded in PERSON_LABELS
    return False


def verify_classes(cache: dict) -> dict[str, dict]:
    """Return kept classes: QID -> {label, group}. Drop the rest."""
    labels = cache.setdefault("classLabels", {})
    missing = [qid for qid, _group, _expect in CLASS_CANDIDATES if qid not in labels]
    if missing:
        payload = wikidata_sparql(query_classes())
        for binding in payload.get("results", {}).get("bindings", []):
            qid = qid_of(binding.get("item", {}).get("value") or "")
            label = (binding.get("itemLabel", {}).get("value") or "").strip()
            if qid:
                labels[qid] = label
        for qid, _group, _expect in CLASS_CANDIDATES:
            labels.setdefault(qid, "")
        save_json(CACHE_PATH, cache)
        time.sleep(1.2)
    kept = {}
    dropped = []
    for qid, group, expected in CLASS_CANDIDATES:
        label = (labels.get(qid) or "").strip()
        if not class_is_music(qid, group, label):
            dropped.append((qid, expected, label or "(no English label)"))
            continue
        kept[qid] = {"label": label, "group": group}
        log(f"class keep {qid} {label} ({group})")
    for qid, expected, label in dropped:
        log(f"class drop {qid} expected {expected!r} got {label!r}")
    cache["droppedClasses"] = [
        {"qid": qid, "expected": expected, "label": label} for qid, expected, label in dropped
    ]
    cache["keptClasses"] = {qid: meta["label"] for qid, meta in kept.items()}
    save_json(CACHE_PATH, cache)
    return kept


def island_qids(atlas: Atlas) -> dict[str, dict]:
    by_qid = _atlas_qids(atlas)
    accepted = None
    last_error = None
    for attempt in range(6):
        try:
            accepted = fetch_island_place_qids(list(by_qid))
            break
        except json.JSONDecodeError as exc:
            last_error = exc
            log(f"place cache busy ({exc}); retry {attempt + 1}")
            time.sleep(3)
    if accepted is None:
        raise RuntimeError(f"could not read island place classes: {last_error}")
    usable = {}
    for qid, island in by_qid.items():
        if qid not in accepted or qid in BLOCKED_PLACE_QIDS:
            continue
        name = island.get("name") or ""
        if is_nation_name(name):
            continue
        usable[qid] = island
    log(f"islands: {len(by_qid)} atlas QIDs, {len(accepted)} place-checked, {len(usable)} usable")
    return usable


def run_batches(cache: dict, kind: str, qids: list[str], query_fn) -> list[dict]:
    batches = cache.setdefault("batches", {})
    failed = cache.setdefault("failed", [])
    ordered = sorted(set(qids))
    pending = [ordered[start : start + BATCH_SIZE] for start in range(0, len(ordered), BATCH_SIZE)]
    log(f"{kind}: {len(ordered)} islands, {len(pending)} batches")
    for index, batch in enumerate(pending, start=1):
        key = kind + ":" + ",".join(batch)
        if key in batches:
            log(f"{kind} batch {index}/{len(pending)} cached ({len(batches[key])} rows)")
            continue
        rows: list[dict] = []
        chunks = [batch]
        while chunks:
            chunk = chunks.pop(0)
            subkey = kind + ":" + ",".join(chunk)
            if subkey in batches and subkey != key:
                rows.extend(batches[subkey])
                continue
            attempts = 4 if len(chunk) <= 3 else 2
            try:
                payload = wikidata_sparql(query_fn(chunk), attempts=attempts)
            except RuntimeError:
                if len(chunk) > 1:
                    mid = len(chunk) // 2
                    chunks.insert(0, chunk[mid:])
                    chunks.insert(0, chunk[:mid])
                    log(f"splitting a Wikidata batch of {len(chunk)}")
                    continue
                log(f"skipping Wikidata batch of {len(chunk)} after repeated failures")
                if subkey not in failed:
                    failed.append(subkey)
                payload = {"results": {"bindings": []}}
            parsed = [
                parse_binding(binding)
                for binding in payload.get("results", {}).get("bindings", [])
            ]
            if subkey != key:
                batches[subkey] = parsed
            rows.extend(parsed)
            save_json(CACHE_PATH, cache)
            time.sleep(1.2)
        batches[key] = rows
        save_json(CACHE_PATH, cache)
        log(f"{kind} batch {index}/{len(pending)}: {len(rows)} links")
    found = []
    for batch in pending:
        found.extend(batches.get(kind + ":" + ",".join(batch)) or [])
    return found


def banned_type(label: str) -> bool:
    folded = norm_label(label)
    if not folded or is_q_number(label):
        return True
    if "fictional" in folded or "tribute" in folded:
        return True
    return False


def choose_kind(options: list[tuple[str, str, str, bool]]) -> tuple[str, str]:
    """Pick a kind from (normalised label, label, family, specific) options."""
    if not options:
        return "", ""
    specific = [item for item in options if item[3]]
    pool = specific or options
    by_norm = {}
    for norm, raw, family, _specific in pool:
        by_norm.setdefault(norm, (raw, family))
    for kind in KIND_PRIORITY:
        if kind in by_norm:
            raw, family = by_norm[kind]
            return raw, family
    _norm, raw, family, _specific = sorted(pool, key=lambda item: (len(item[1]), item[0]))[0]
    return raw, family


def copied_music_keys() -> set[tuple[str, str]]:
    last_error = None
    for attempt in range(8):
        try:
            return set(existing_music_keys())
        except (json.JSONDecodeError, OSError) as exc:
            last_error = exc
            log(f"candidate file busy ({exc}); retry {attempt + 1}")
            time.sleep(2)
    raise RuntimeError(f"could not read existing music keys: {last_error}")


def source_for(family: str, work: str, article: str, mb: str, title: str) -> tuple[str, str, str]:
    if article:
        return article, "CC BY-SA 4.0", wiki_title(article) or title
    if family in {"person", "group"} and mb:
        return f"https://musicbrainz.org/artist/{mb}", "CC0", title
    return f"https://www.wikidata.org/wiki/{work}", "CC0", title


def build_rows(raw: list[dict], by_qid: dict[str, dict], kept: dict[str, dict]) -> tuple[list[dict], dict[str, int]]:
    grouped: dict[tuple[str, str], dict] = {}
    for item in raw:
        place = item.get("place") or ""
        work = item.get("work") or ""
        island = by_qid.get(place)
        if not island or place in BLOCKED_PLACE_QIDS or is_nation_name(island.get("name") or ""):
            continue
        if not work or work == place:
            continue
        type_id = item.get("type") or ""
        root = item.get("root") or ""
        type_label = item.get("typeLabel") or ""
        option = None
        if type_id in kept:
            meta = kept[type_id]
            option = (norm_label(meta["label"]), meta["label"], meta["group"], False)
        elif root in kept and good_label(type_label) and not banned_type(type_label):
            meta = kept[root]
            specific = norm_label(type_label) != norm_label(meta["label"])
            option = (norm_label(type_label), type_label, meta["group"], specific)
        if option is None:
            continue
        prop = item.get("prop") or ""
        if prop not in PROP_NAMES:
            continue
        bucket = grouped.setdefault(
            (work, place),
            {
                "work": work,
                "place": place,
                "island": island,
                "label": "",
                "article": "",
                "mb": "",
                "image": "",
                "options": [],
                "props": [],
            },
        )
        label = item.get("label") or ""
        if good_label(label) and (not bucket["label"] or is_q_number(bucket["label"])):
            bucket["label"] = label
        if item.get("article") and not bucket["article"]:
            bucket["article"] = item["article"]
        if item.get("mb") and not bucket["mb"]:
            bucket["mb"] = item["mb"]
        if item.get("image") and not bucket["image"]:
            bucket["image"] = item["image"]
        if option not in bucket["options"]:
            bucket["options"].append(option)
        if prop not in bucket["props"]:
            bucket["props"].append(prop)

    per_island: dict[str, list[dict]] = defaultdict(list)
    for bucket in grouped.values():
        label = bucket["label"]
        if not good_label(label):
            continue
        kind, family = choose_kind(bucket["options"])
        if not kind or family not in FAMILY_PROPS:
            continue
        allowed = [prop for prop in PROP_ORDER if prop in bucket["props"] and prop in FAMILY_PROPS[family]]
        if not allowed:
            continue
        if family == "person" and not bucket["article"] and not bucket["mb"]:
            continue
        bucket["kind"] = kind
        bucket["family"] = family
        bucket["allowed"] = allowed
        per_island[bucket["island"]["id"]].append(bucket)

    seen = copied_music_keys()
    rows = []
    counts = {"group": 0, "work": 0, "person": 0}
    for candidates in per_island.values():
        candidates.sort(
            key=lambda cand: (
                0 if (cand["article"] or cand["mb"]) else 1,
                0 if cand["article"] else 1,
                0 if good_label(cand["label"]) else 1,
                fold(cand["label"]),
                cand["work"],
            )
        )
        accepted = 0
        seen_works = set()
        for cand in candidates:
            if accepted >= PER_ISLAND_CAP:
                break
            if cand["work"] in seen_works:
                continue
            island = cand["island"]
            title = cand["label"]
            kind = cand["kind"]
            family = cand["family"]
            props = " and ".join(PROP_NAMES[prop] for prop in cand["allowed"])
            island_name = island["name"]
            source_url, licence, source_title = source_for(
                family, cand["work"], cand["article"], cand["mb"], title
            )
            summary = f"{title} is {article_word(kind)} {kind} linked to '{island_name}' ({props})."
            evidence = f"Wikidata {cand['work']}: {kind}; {props} '{island_name}'."
            built = music_row(
                island=island,
                title=title,
                source_url=source_url,
                source_title=source_title,
                licence=licence,
                evidence=evidence,
                summary=summary,
                external_id=cand["work"],
                commons_file=commons_file(cand["image"]),
                seen=seen,
            )
            if not built:
                continue
            rows.append(built)
            counts[family] = counts.get(family, 0) + 1
            accepted += 1
            seen_works.add(cand["work"])
    rows.sort(key=lambda item: (fold(item.get("island_name") or ""), fold(item.get("title") or "")))
    return rows, counts


def types_for(kept: dict[str, dict], group: str, labels: set[str] | None = None) -> list[str]:
    found = []
    for qid, meta in kept.items():
        if meta["group"] != group:
            continue
        if labels is not None and norm_label(meta["label"]) not in labels:
            continue
        found.append(qid)
    return found


def main() -> None:
    cache = load_cache()
    kept = verify_classes(cache)
    if not kept:
        raise SystemExit("No music classes survived the label check")

    by_qid = island_qids(Atlas())
    qids = sorted(by_qid)
    raw: list[dict] = []

    groups = types_for(kept, "group")
    releases = types_for(kept, "work", RELEASE_LABELS)
    compositions = types_for(kept, "work", COMPOSITION_LABELS)
    people = types_for(kept, "person")
    log(
        "query classes: groups "
        + (", ".join(groups) or "(none)")
        + "; releases "
        + (", ".join(releases) or "(none)")
        + "; compositions "
        + (", ".join(compositions) or "(none)")
        + "; people "
        + (", ".join(people) or "(none)")
    )
    if groups:
        raw.extend(
            run_batches(
                cache,
                "group",
                qids,
                lambda batch: query_items(batch, groups, GROUP_PROPS, "group"),
            )
        )
    if releases:
        raw.extend(
            run_batches(
                cache,
                "release",
                qids,
                lambda batch: query_items(batch, releases, WORK_PROPS, "work"),
            )
        )
    if compositions:
        raw.extend(
            run_batches(
                cache,
                "composition",
                qids,
                lambda batch: query_items(batch, compositions, WORK_PROPS, "work"),
            )
        )
    if people:
        raw.extend(
            run_batches(
                cache,
                "person",
                qids,
                lambda batch: query_items(batch, people, PERSON_PROPS, "person"),
            )
        )
    # Subclasses of the kept classes: musical duo, punk band, choir, hymn, and
    # the rest. Direct P31 only repeats rows the culture query already kept.
    work_roots = releases + compositions
    if groups:
        raw.extend(
            run_batches(
                cache,
                "group-sub",
                qids,
                lambda batch: query_subclasses(batch, groups, GROUP_PROPS),
            )
        )
    if work_roots:
        raw.extend(
            run_batches(
                cache,
                "work-sub",
                qids,
                lambda batch: query_subclasses(batch, work_roots, WORK_PROPS),
            )
        )

    rows, counts = build_rows(raw, by_qid, kept)
    save_json(
        OUTPUT_PATH,
        {
            "slug": "music-wikidata",
            "generatedAt": utc_now(),
            "sources": ["wikidata"],
            "rows": rows,
        },
    )
    islands: dict[str, int] = {}
    for item in rows:
        islands[item["island_name"]] = islands.get(item["island_name"], 0) + 1
    top = sorted(islands.items(), key=lambda item: (-item[1], item[0]))[:12]
    failed = cache.get("failed") or []
    dropped = cache.get("droppedClasses") or []
    log(
        f"SUMMARY accepted={len(rows)} groups={counts.get('group', 0)} "
        f"works={counts.get('work', 0)} people={counts.get('person', 0)} "
        f"islands={len(islands)} failed={len(failed)}"
    )
    log("DROPPED " + "; ".join(f"{item['qid']} {item['label']}" for item in dropped))
    log("TOP " + "; ".join(f"{name} {count}" for name, count in top))
    if failed:
        log("FAILED " + "; ".join(failed))
    samples = []
    seen_islands = set()
    for item in rows:
        if item["island_name"] in seen_islands:
            continue
        samples.append(item)
        seen_islands.add(item["island_name"])
        if len(samples) == 8:
            break
    for item in rows:
        if len(samples) >= 8:
            break
        if item in samples:
            continue
        samples.append(item)
    for item in samples:
        log(f"SAMPLE {item['island_name']} | {item['title']} | {item['source_url']}")
    log(f"WROTE {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
