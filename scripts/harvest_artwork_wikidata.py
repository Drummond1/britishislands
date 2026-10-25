#!/usr/bin/env python3
"""Harvest cited artworks from Wikidata for the atlas interest filter.

Writes data/interest/candidates/artwork-wikidata.json and caches SPARQL
responses at data/cache_wikidata_artwork_extra.json. Does not publish the
interest index and does not edit islands.json.

A row is kept only when a Wikidata statement ties that work to an atlas
island, or to a landmark Wikidata places on that island.
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
    artwork_row,
    existing_artwork_keys,
    phrase_in_text,
)

CACHE_PATH = ROOT / "data" / "cache_wikidata_artwork_extra.json"
OUTPUT_PATH = ROOT / "data" / "interest" / "candidates" / "artwork-wikidata.json"
USER_AGENT = "isles-of-britain/0.1 (artwork-wikidata-harvest; research)"
BATCH_SIZE = 25
PER_ISLAND_CAP = 80

# Starting list from the brief. The label query below drops any QID whose
# English label is not an artwork class.
CLASS_CANDIDATES = {
    "Q3305213": "painting",
    "Q18761202": "oil painting",
    "Q174219": "watercolor painting",
    "Q93184": "drawing",
    "Q11060274": "print",
    "Q18219090": "etching",
    "Q174740": "engraving",
    "Q187850": "fresco",
    "Q26904132": "acrylic painting",
    "Q860861": "sculpture",
    "Q179700": "statue",
    "Q4989906": "public art",
    "Q219423": "mural",
    "Q1473346": "stained-glass window",
    "Q184296": "tapestry",
}

# Labels that name a work. Materials, people, facilities, techniques, and
# commemorative structures are not artwork classes.
ARTWORK_CLASS_LABELS = {
    "painting",
    "oil painting",
    "watercolor painting",
    "watercolour painting",
    "drawing",
    "print",
    "etching",
    "engraving",
    "fresco",
    "acrylic painting",
    "woodcut print",
    "sculpture",
    "statue",
    "public art",
    "mural",
    "stained-glass window",
    "stained glass window",
    "tapestry",
}

# Sculptures, statues, public art, murals, and stained glass may use P276.
# Flat works must not: on a painting, P276 is the museum.
LOCATED_LABELS = {
    "sculpture",
    "statue",
    "public art",
    "mural",
    "stained-glass window",
    "stained glass window",
}

KIND_PRIORITY = [
    "watercolor painting",
    "watercolour painting",
    "woodcut print",
    "oil painting",
    "acrylic painting",
    "etching",
    "engraving",
    "fresco",
    "stained-glass window",
    "stained glass window",
    "tapestry",
    "print",
    "drawing",
    "mural",
    "statue",
    "public art",
    "sculpture",
    "painting",
]

FLAT_PROPS = ("P180", "P921", "P1071")
LOCATED_PROPS = ("P180", "P921", "P1071", "P276")
# P276 location and P361 part of, plus P706 located on a physical feature.
# Fingal's Cave is on Staffa by P706, not by P276 or P361.
LANDMARK_VIAS = ("P276", "P361", "P706")

PROP_NAMES = {
    "P180": "depicts",
    "P921": "main subject",
    "P1071": "location of creation",
    "P276": "location",
    "P361": "part of",
    "P706": "located on physical feature",
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

# Countries and the two main islands. Never attach a work to these QIDs.
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
    text = fold(text).replace("watercolour", "watercolor").replace("-", " ")
    return re.sub(r"\s+", " ", text).strip()


def qid_of(value: str) -> str:
    return (value or "").rstrip("/").rsplit("/", 1)[-1]


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


def is_q_number(label: str) -> bool:
    return bool(re.fullmatch(r"Q\d+", (label or "").strip()))


def is_nation_name(label: str) -> bool:
    """True when the whole label is a country or Great Britain / Ireland."""
    folded = fold(label)
    if folded in NATION_NAMES:
        return True
    return any(
        phrase_in_text(phrase, label) and folded == fold(phrase)
        for phrase in ("great britain", "united kingdom", "ireland")
    )


def is_photograph_title(label: str) -> bool:
    return phrase_in_text("photograph", label) or phrase_in_text("photographs", label)


def good_work_label(label: str) -> bool:
    label = (label or "").strip()
    if not label or is_q_number(label):
        return False
    if phrase_in_text("possibly", label):
        return False
    if is_photograph_title(label):
        return False
    return True


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
    via = binding.get("via", {}).get("value") or ""
    return {
        "work": qid_of(binding.get("work", {}).get("value") or ""),
        "label": (binding.get("workLabel", {}).get("value") or "").strip(),
        "place": qid_of(binding.get("place", {}).get("value") or ""),
        "type": qid_of(binding.get("type", {}).get("value") or ""),
        "article": binding.get("article", {}).get("value") or "",
        "image": binding.get("image", {}).get("value") or "",
        "prop": direct.rsplit("/", 1)[-1],
        "landmark": qid_of(binding.get("landmark", {}).get("value") or ""),
        "landmarkLabel": (binding.get("landmarkLabel", {}).get("value") or "").strip(),
        "via": via.rsplit("/", 1)[-1],
    }


def values_clause(qids: list[str], prefix: str = "wd:") -> str:
    return " ".join(f"{prefix}{qid}" for qid in qids)


def query_classes() -> str:
    values = values_clause(list(CLASS_CANDIDATES))
    return f"""
SELECT ?item ?itemLabel WHERE {{
  VALUES ?item {{ {values} }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
"""


def query_direct(qids: list[str], types: list[str], props: tuple[str, ...]) -> str:
    return f"""
SELECT DISTINCT ?work ?workLabel ?place ?type ?article ?image ?direct WHERE {{
  VALUES ?place {{ {values_clause(qids)} }}
  VALUES ?direct {{ {values_clause(list(props), "wdt:")} }}
  ?work ?direct ?place .
  ?work wdt:P31 ?type .
  VALUES ?type {{ {values_clause(types)} }}
  FILTER(?work != ?place)
  OPTIONAL {{ ?article schema:about ?work ; schema:isPartOf <https://en.wikipedia.org/> . }}
  OPTIONAL {{ ?work wdt:P18 ?image }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
"""


def query_landmark(qids: list[str], types: list[str], props: tuple[str, ...]) -> str:
    return f"""
SELECT DISTINCT ?work ?workLabel ?place ?landmark ?landmarkLabel ?type ?article ?image ?direct ?via WHERE {{
  VALUES ?place {{ {values_clause(qids)} }}
  ?landmark ?via ?place .
  VALUES ?via {{ {values_clause(list(LANDMARK_VIAS), "wdt:")} }}
  FILTER(?landmark != ?place)
  VALUES ?direct {{ {values_clause(list(props), "wdt:")} }}
  ?work ?direct ?landmark .
  ?work wdt:P31 ?type .
  VALUES ?type {{ {values_clause(types)} }}
  FILTER(?work != ?landmark && ?work != ?place)
  OPTIONAL {{ ?article schema:about ?work ; schema:isPartOf <https://en.wikipedia.org/> . }}
  OPTIONAL {{ ?work wdt:P18 ?image }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
"""


def load_cache() -> dict:
    cache = load_json(CACHE_PATH, {})
    if not isinstance(cache, dict):
        cache = {}
    cache.setdefault("classLabels", {})
    cache.setdefault("batches", {})
    cache.setdefault("failed", [])
    return cache


def verify_classes(cache: dict) -> dict[str, dict]:
    """Return kept classes: QID -> {label, group}. Drop the rest."""
    labels = cache.setdefault("classLabels", {})
    missing = [qid for qid in CLASS_CANDIDATES if qid not in labels]
    if missing:
        payload = wikidata_sparql(query_classes())
        for binding in payload.get("results", {}).get("bindings", []):
            qid = qid_of(binding.get("item", {}).get("value") or "")
            label = (binding.get("itemLabel", {}).get("value") or "").strip()
            if qid:
                labels[qid] = label
        for qid in CLASS_CANDIDATES:
            labels.setdefault(qid, "")
        save_json(CACHE_PATH, cache)
        time.sleep(1.2)
    kept = {}
    dropped = []
    for qid, expected in CLASS_CANDIDATES.items():
        label = (labels.get(qid) or "").strip()
        folded = norm_label(label)
        # Stained glass is kept only when the English label is the window class.
        if qid == "Q1473346" and folded not in {"stained glass window"}:
            dropped.append((qid, expected, label or "(no English label)"))
            continue
        if not label or is_q_number(label) or folded not in ARTWORK_CLASS_LABELS:
            dropped.append((qid, expected, label or "(no English label)"))
            continue
        group = "located" if folded in LOCATED_LABELS else "flat"
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
    accepted = fetch_island_place_qids(list(by_qid))
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


def choose_kind(type_ids: list[str], kept: dict[str, dict]) -> str:
    labels = [norm_label(kept[type_id]["label"]) for type_id in type_ids if type_id in kept]
    for kind in KIND_PRIORITY:
        if norm_label(kind) in labels:
            return kind
    return labels[0] if labels else ""


def article_word(kind: str) -> str:
    return "an" if fold(kind)[:1] in "aeiou" else "a"


def build_rows(raw: list[dict], by_qid: dict[str, dict], kept: dict[str, dict]) -> list[dict]:
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
        if type_id not in kept:
            continue
        prop = item.get("prop") or ""
        if prop not in PROP_NAMES:
            continue
        landmark = item.get("landmark") or ""
        # The work item is not a depiction of itself, and a landmark QID is
        # not the island item. Landmark ids are Q-numbers; the label check
        # below rejects a landmark whose English name is missing.
        if landmark and (landmark == work or landmark == place):
            continue
        bucket = grouped.setdefault(
            (work, place),
            {
                "work": work,
                "place": place,
                "island": island,
                "label": "",
                "article": "",
                "image": "",
                "types": [],
                "direct_props": [],
                "landmark_props": [],
                "landmarks": {},
            },
        )
        label = item.get("label") or ""
        if good_work_label(label) and not bucket["label"]:
            bucket["label"] = label
        elif good_work_label(label) and is_q_number(bucket["label"]):
            bucket["label"] = label
        if item.get("article") and not bucket["article"]:
            bucket["article"] = item["article"]
        if item.get("image") and not bucket["image"]:
            bucket["image"] = item["image"]
        if type_id not in bucket["types"]:
            bucket["types"].append(type_id)
        if landmark:
            landmark_label = item.get("landmarkLabel") or ""
            via = item.get("via") or ""
            if (
                via in LANDMARK_VIAS
                and good_work_label(landmark_label)
                and not is_nation_name(landmark_label)
                and not is_q_number(landmark_label)
            ):
                slot = bucket["landmarks"].setdefault(
                    landmark,
                    {"qid": landmark, "label": landmark_label, "vias": []},
                )
                if via not in slot["vias"]:
                    slot["vias"].append(via)
                if prop not in bucket["landmark_props"]:
                    bucket["landmark_props"].append(prop)
        elif prop not in bucket["direct_props"]:
            bucket["direct_props"].append(prop)

    per_island: dict[str, list[dict]] = defaultdict(list)
    for bucket in grouped.values():
        if not bucket["direct_props"] and not bucket["landmarks"]:
            continue
        label = bucket["label"]
        if not good_work_label(label):
            continue
        kind = choose_kind(bucket["types"], kept)
        if not kind:
            continue
        bucket["kind"] = kind
        per_island[bucket["island"]["id"]].append(bucket)

    seen = set(existing_artwork_keys())
    # A rerun must replace this file, not treat its own previous rows as
    # foreign duplicates. Keys that also appear in another candidate file stay.
    own_keys = set()
    for item in load_json(OUTPUT_PATH, {}).get("rows") or []:
        if item.get("island_id") and item.get("title"):
            own_keys.add((item["island_id"], fold(item["title"])))
    elsewhere = set()
    for path in OUTPUT_PATH.parent.glob("*.json"):
        if path.name == OUTPUT_PATH.name:
            continue
        for item in load_json(path, {}).get("rows") or []:
            if item.get("status") != "accepted":
                continue
            if item.get("facet") not in (None, "", "artwork"):
                continue
            if item.get("island_id") and item.get("title"):
                elsewhere.add((item["island_id"], fold(item["title"])))
    seen = (seen - own_keys) | elsewhere

    rows = []
    for island_id, candidates in per_island.items():
        candidates.sort(
            key=lambda cand: (
                0 if (cand["article"] or cand["image"]) else 1,
                0 if cand["article"] else 1,
                0 if cand["image"] else 1,
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
            landmarks = list(cand["landmarks"].values())
            if not cand["direct_props"] and not landmarks:
                continue
            title = cand["label"]
            kind = cand["kind"]
            article = cand["article"]
            if article:
                source_url = article
                licence = "CC BY-SA 4.0"
                source_title = wiki_title(article) or title
            else:
                source_url = f"https://www.wikidata.org/wiki/{cand['work']}"
                licence = "CC0"
                source_title = title
            landmark_name = landmarks[0]["label"] if landmarks else ""
            if landmark_name:
                summary = f"{title} is {article_word(kind)} {kind} of {landmark_name} on {island['name']}."
            else:
                summary = f"{title} is {article_word(kind)} {kind} linked to {island['name']}."
            evidence = evidence_text(cand, kind, island["name"], landmarks)
            built = artwork_row(
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
            accepted += 1
            seen_works.add(cand["work"])
    rows.sort(key=lambda item: (fold(item.get("island_name") or ""), fold(item.get("title") or "")))
    return rows


def evidence_text(cand: dict, kind: str, island_name: str, landmarks: list[dict]) -> str:
    parts = []
    if cand["direct_props"]:
        props = " and ".join(PROP_NAMES[prop] for prop in cand["direct_props"] if prop in PROP_NAMES)
        parts.append(f"{props} '{island_name}'")
    if landmarks:
        bits = []
        for landmark in landmarks[:3]:
            via_bits = " and ".join(
                f"{via} {PROP_NAMES.get(via, via)}" for via in landmark["vias"] if via
            )
            link = " and ".join(
                PROP_NAMES[prop] for prop in cand["landmark_props"] if prop in PROP_NAMES
            )
            bits.append(f"{link} '{landmark['label']}' ({via_bits}) on '{island_name}'")
        parts.append("landmark " + "; ".join(bits))
    detail = "; ".join(parts)
    return f"Wikidata {cand['work']}: {kind}; {detail}."


def main() -> None:
    cache = load_cache()
    kept = verify_classes(cache)
    if not kept:
        raise SystemExit("No artwork classes survived the label check")
    flat_types = [qid for qid, meta in kept.items() if meta["group"] == "flat"]
    located_types = [qid for qid, meta in kept.items() if meta["group"] == "located"]
    log(f"flat classes: {', '.join(flat_types) or '(none)'}")
    log(f"located classes: {', '.join(located_types) or '(none)'}")

    by_qid = island_qids(Atlas())
    qids = sorted(by_qid)
    raw: list[dict] = []
    if flat_types:
        raw.extend(run_batches(cache, "A-flat", qids, lambda batch: query_direct(batch, flat_types, FLAT_PROPS)))
    if located_types:
        raw.extend(
            run_batches(cache, "A-located", qids, lambda batch: query_direct(batch, located_types, LOCATED_PROPS))
        )
    if flat_types:
        raw.extend(
            run_batches(cache, "B-flat", qids, lambda batch: query_landmark(batch, flat_types, FLAT_PROPS))
        )
    if located_types:
        raw.extend(
            run_batches(
                cache, "B-located", qids, lambda batch: query_landmark(batch, located_types, LOCATED_PROPS)
            )
        )

    rows = build_rows(raw, by_qid, kept)
    save_json(
        OUTPUT_PATH,
        {
            "slug": "artwork-wikidata",
            "generatedAt": utc_now(),
            "sources": ["wikidata"],
            "rows": rows,
        },
    )
    islands = {}
    for row in rows:
        islands.setdefault(row["island_name"], 0)
        islands[row["island_name"]] += 1
    top = sorted(islands.items(), key=lambda item: (-item[1], item[0]))[:15]
    failed = cache.get("failed") or []
    log(f"accepted {len(rows)} rows on {len(islands)} islands")
    log(f"failed batches {len(failed)}")
    log("top islands: " + "; ".join(f"{name} {count}" for name, count in top))
    for row in rows[:8]:
        log(f"sample {row['island_name']} | {row['title']} | {row['source_url']}")
    log(f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
