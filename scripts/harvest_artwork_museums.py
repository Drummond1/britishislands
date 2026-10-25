#!/usr/bin/env python3
"""Harvest cited artworks from museum open-access APIs.

Sources (metadata, and public-domain images, checked at runtime):

- The Met Collection API. /public/collection/v1/search was retired on
  2026-10-01. This script uses the documented replacement
  /public/collection/v1.1/search with the same hasImages and q filters,
  then GET /public/collection/v1/objects/{id}.
- Cleveland Museum of Art Open Access API.
- Art Institute of Chicago public API.

Writes data/interest/candidates/artwork-museums.json. Does not publish
and does not modify the island catalogue.
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
import urllib.parse
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from artwork_harvest_common import (  # noqa: E402
    AMBIGUOUS_KEYS,
    NATION_PHRASES,
    artwork_row,
    existing_artwork_keys,
    match_island_phrase,
    phrase_in_text,
    search_phrases,
)
from ingest_sources import name_key  # noqa: E402
from interest_categories import (  # noqa: E402
    Atlas,
    fold,
    http_json,
    load_json,
    save_json,
    utc_now,
)

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache_artwork_museums"
OUT = ROOT / "data" / "interest" / "candidates" / "artwork-museums.json"

SLEEP = 0.35
MAX_ROWS = 600
PER_ISLAND = 40
PER_QUERY = 30
CC0_URL = "https://creativecommons.org/publicdomain/zero/1.0/"
UA = "isles-of-britain/0.1 (artwork-museums; research)"

BARE_SKIP = {
    "harris",
    "lewis",
    "man",
    "jersey",
    "guernsey",
    "orkney",
    "shetland",
    "wight",
    "scilly",
}
ARCHIPELAGO_KEYS = {"orkney", "shetland", "scilly"}

LANDMARKS = [
    "Fingal's Cave",
    "Staffa",
    "Iona",
    "Lindisfarne",
    "Holy Island",
    "St Michael's Mount",
    "St Michael’s Mount",
    "Anglesey",
    "Isle of Skye",
    "Isle of Mull",
    "Isle of Arran",
    "Isle of Jura",
    "Islay",
    "St Kilda",
    "Skellig Michael",
    "Inishmore",
    "Achill Island",
    "Lundy",
    "Isle of Wight",
    "Ailsa Craig",
    "Bass Rock",
    "Burgh Island",
    "Tresco",
    "Caldey",
    "Bardsey",
    "Skomer",
    "Brownsea",
    "Fair Isle",
    "Isle of May",
]

PHOTO_RE = re.compile(
    r"\b(photographs?|photographic|albumen|daguerreotypes?|calotypes?|"
    r"gelatin silver|photogravures?|photomechanical|cyanotypes?|"
    r"salted paper|collodion|snapshots?|polaroids?|carte de visite|"
    r"platinum print|silver print|carbon print|woodburytype)\b",
    re.I,
)
SKIP_RE = re.compile(
    r"\b(costumes?|furniture|ceramics?|porcelain|jewell?ery|jewelry|jewelery)\b",
    re.I,
)
TYPE_PATTERNS = (
    ("watercolour", re.compile(r"\b(watercolou?rs?|gouache|bodycolou?r)\b", re.I)),
    ("painting", re.compile(r"\b(paintings?|oil on|tempera|fresco(?:es)?)\b", re.I)),
    ("etching", re.compile(r"\betchings?\b", re.I)),
    ("engraving", re.compile(r"\bengravings?\b", re.I)),
    ("drawing", re.compile(r"\b(drawings?|pastels?|charcoal|graphite|chalks?)\b|\bink\b", re.I)),
    (
        "print",
        re.compile(
            r"\b(prints?|lithographs?|woodcuts?|mezzotints?|aquatints?|drypoints?|linocuts?)\b",
            re.I,
        ),
    ),
    ("statue", re.compile(r"\bstatues?\b", re.I)),
    ("mural", re.compile(r"\bmurals?\b", re.I)),
    ("sculpture", re.compile(r"\bsculptures?\b", re.I)),
)


def norm(text: str) -> str:
    text = text or ""
    text = (
        text.replace("’", "'")
        .replace("‘", "'")
        .replace("`", "'")
        .replace("–", "-")
        .replace("—", "-")
    )
    text = re.sub(r"\bSt\.", "St", text)
    return text


def plain(text) -> str:
    if text is None:
        return ""
    if not isinstance(text, str):
        text = " ".join(str(part) for part in text) if isinstance(text, (list, tuple)) else str(text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_query(phrase: str) -> str:
    return re.sub(r"\s+", " ", norm(phrase)).strip()


class AliasIndex:
    """Island-name phrases that match_island_phrase can resolve."""

    def __init__(self, atlas: Atlas):
        self.atlas = atlas
        self._resolved: dict[str, dict | None] = {}
        singles: dict[str, str] = {}
        multis: list[str] = []
        seen: set[str] = set()
        for island in atlas.islands:
            area = island.get("area") or 0
            if area <= 0 or area > 8000:
                continue
            if name_key(island["name"]) in ARCHIPELAGO_KEYS:
                continue
            for alias in self._aliases_for(island["name"]):
                key = fold(alias)
                if not key or key in seen or key in NATION_PHRASES or key in BARE_SKIP:
                    continue
                if name_key(alias) in ARCHIPELAGO_KEYS:
                    continue
                token = key
                if " " not in key:
                    if len(token) < 3:
                        continue
                    if name_key(alias) in AMBIGUOUS_KEYS and token == name_key(alias):
                        continue
                    singles.setdefault(token, alias)
                else:
                    if len(token) < 6:
                        continue
                    multis.append(alias)
                seen.add(key)
        self.singles = singles
        self.multis = [
            (alias, re.compile(r"\b" + re.escape(fold(alias)) + r"\b"))
            for alias in sorted(multis, key=len, reverse=True)
        ]

    @staticmethod
    def _aliases_for(name: str) -> list[str]:
        aliases = [name]
        base = re.sub(r"\s*\([^)]*\)", "", name).strip()
        if base:
            aliases.append(base)
        inner = re.search(r"\(([^)]+)\)", name)
        if inner:
            aliases.append(inner.group(1).strip())
        short = re.sub(r"(?i)^(isle|island) of\s+", "", name).strip()
        if short:
            aliases.append(short)
        for alias in list(aliases):
            if re.search(r"(?i)\bSaint\b", alias):
                aliases.append(re.sub(r"(?i)\bSaint\b", "St", alias))
        return [clean_query(alias) for alias in aliases if alias]

    def resolve(self, phrase: str) -> dict | None:
        cleaned = clean_query(phrase)
        if not cleaned:
            return None
        key = fold(cleaned)
        if key in self._resolved:
            return self._resolved[key]
        island = match_island_phrase(self.atlas, cleaned)
        if island is None and re.search(r"(?i)\bSt\b", cleaned):
            expanded = re.sub(r"(?i)\bSt\b", "Saint", cleaned)
            island = match_island_phrase(self.atlas, expanded)
        if island and name_key(island["name"]) in ARCHIPELAGO_KEYS:
            island = None
        if island and ((island.get("area") or 0) > 8000):
            island = None
        self._resolved[key] = island
        return island

    def find(self, text: str) -> list[str]:
        folded = fold(norm(text))
        if not folded:
            return []
        words: set[str] = set()
        for token in re.findall(r"[a-z0-9']+", folded):
            words.add(token)
            if "'" in token:
                words.add(token.split("'", 1)[0])
        found: list[str] = []
        for token, alias in self.singles.items():
            if token in words:
                found.append(alias)
        for alias, pattern in self.multis:
            if pattern.search(folded):
                found.append(alias)
        return found


def holy_target(text: str, atlas: Atlas) -> dict | None:
    """Pick which Holy Island the museum text is naming."""
    folded = fold(norm(text))
    if "holy island" not in folded:
        return None
    if any(
        hint in folded
        for hint in (
            "lindisfarne",
            "northumberland",
            "durham",
            "holy island castle",
            "holy island cathedral",
        )
    ):
        return match_island_phrase(atlas, "Lindisfarne")
    if "arran" in folded or "lamlash" in folded:
        return next(
            (
                island
                for island in atlas.islands
                if island["name"] == "Holy Island" and (island.get("lat") or 0) > 55
            ),
            None,
        )
    if any(hint in folded for hint in ("anglesey", "holyhead", "caergybi", "ynys gybi")):
        return match_island_phrase(atlas, "Holy Island")
    return None


def disambiguate_holy(pairs: list[tuple[str, dict]], text: str, atlas: Atlas) -> list[tuple[str, dict]]:
    """Holy Island is three atlas places. Prefer a more specific name in the text."""
    folded = fold(norm(text))
    if "holy island" not in folded and not any(fold(alias) == "holy island" for alias, _ in pairs):
        return pairs
    replacement = holy_target(text, atlas)
    needle = "Holy Island"
    if replacement and replacement.get("id") == "lindisfarne":
        needle = "Lindisfarne"
    if not replacement:
        return pairs
    kept = [
        (alias, island)
        for alias, island in pairs
        if island["id"] != replacement["id"] and fold(island["name"]) != "holy island"
    ]
    kept.append((needle, replacement))
    return kept


def choose_island(
    aliases: list[str],
    query: str,
    title: str,
    cite: str,
    index: AliasIndex,
) -> tuple[dict | None, str]:
    pairs: list[tuple[str, dict]] = []
    seen: set[str] = set()
    for alias in aliases:
        island = index.resolve(alias)
        if not island or island["id"] in seen:
            continue
        seen.add(island["id"])
        pairs.append((alias, island))
    pairs = disambiguate_holy(pairs, cite, index.atlas)
    if not pairs:
        resolved = index.resolve(query)
        if resolved and phrase_in_text(query, cite):
            return resolved, query
        return None, ""
    scored = []
    for alias, island in pairs:
        score = len(fold(alias))
        if phrase_in_text(alias, title) or phrase_in_text(island["name"], title):
            score += 100
        scored.append((score, island, alias))
    scored.sort(key=lambda item: item[0], reverse=True)
    if len(scored) == 1 or scored[0][0] > scored[1][0]:
        return scored[0][1], scored[0][2]
    query_island = index.resolve(query)
    tied = [item for item in scored if item[0] == scored[0][0]]
    if query_island and any(item[1]["id"] == query_island["id"] for item in tied):
        return query_island, query
    return None, ""


def artwork_kind(type_text: str, title: str, index: AliasIndex) -> str | None:
    if PHOTO_RE.search(type_text) or SKIP_RE.search(type_text):
        if re.search(r"\bpainting\b", title or "", re.I) and index.find(title or ""):
            return "painting"
        return None
    for label, pattern in TYPE_PATTERNS:
        if pattern.search(type_text):
            return label
    return None


def phrase_ok(phrase: str, text: str) -> bool:
    """phrase_in_text, plus the original spelling so Tirée does not match Tiree."""
    if not phrase_in_text(phrase, text):
        return False
    raw = norm(text).lower()
    needle = norm(phrase).lower()
    return re.search(r"\b" + re.escape(needle) + r"\b", raw) is not None


def false_place(island: dict, cite: str) -> bool:
    """Reject surname, mountain, and New Jersey collisions."""
    folded = fold(norm(cite))
    key = name_key(island["name"])
    name = fold(island["name"])
    if key == "jura" or name == "jura":
        if re.search(r"\bjura mountains?\b|\bfrom the jura\b|\bthe jura\b", folded):
            if not re.search(r"\b(isle|island) of jura\b", folded):
                return True
    if key in {"harris", "lewis"} or name in {"harris", "lewis"}:
        if not re.search(r"\b(isle|island) of (harris|lewis)\b", folded):
            return True
    if key == "jersey" or name == "jersey":
        if not re.search(r"\b(isle|island) of jersey\b", folded):
            return True
    if key == "yell" or name == "yell":
        if not re.search(r"\b(isle|island) of yell\b|\byell, shetland\b", folded):
            return True
    return False


def island_needles(query: str, island: dict, index: AliasIndex) -> list[str]:
    """Phrases that count as this island for the query that found the hit."""
    needles = [query, island["name"]]
    short = re.sub(r"(?i)^(isle|island) of\s+", "", island["name"]).strip()
    if short:
        resolved = index.resolve(short)
        if resolved and resolved["id"] == island["id"]:
            needles.append(short)
    if re.search(r"(?i)\bSaint\b", island["name"]):
        needles.append(re.sub(r"(?i)\bSaint\b", "St", island["name"]))
    seen = set()
    unique = []
    for needle in needles:
        key = fold(norm(needle))
        if needle and key not in seen:
            seen.add(key)
            unique.append(needle)
    return unique


def match_hit(
    query: str,
    paired: dict | None,
    parts: dict,
    index: AliasIndex,
) -> tuple[dict | None, str]:
    title = parts.get("title") or ""
    cite = " ".join(parts.get(key) or "" for key in ("title", "description", "credit", "medium", "place"))
    if not plain(title) or not cite.strip():
        return None, ""
    target = paired or index.resolve(query)
    if phrase_in_text("Holy Island", cite):
        better = holy_target(cite, index.atlas)
        if better and (target is None or target["name"] == "Holy Island" or fold(query) == "holy island"):
            target = better
    if target is not None:
        needles = island_needles(query, target, index)
        needle = next((item for item in needles if phrase_ok(item, cite)), "")
        if not needle or false_place(target, cite):
            return None, ""
        if name_key(target["name"]) in ARCHIPELAGO_KEYS:
            return None, ""
        return target, needle
    # "Fingal's Cave" is not itself an island. The query and an island name
    # both have to be in the museum text.
    if not phrase_ok(query, cite):
        return None, ""
    island, needle = choose_island(index.find(cite), query, title, cite, index)
    if not island or name_key(island["name"]) in ARCHIPELAGO_KEYS:
        return None, ""
    if not phrase_ok(needle, cite) or fold(needle) == fold(query) or false_place(island, cite):
        return None, ""
    return island, needle


def evidence_for(museum_name: str, parts: dict, needles: list[str]) -> str:
    for key in ("title", "description", "credit", "place", "medium"):
        text = plain(parts.get(key) or "")
        if not text:
            continue
        for needle in needles:
            if needle and phrase_ok(needle, text):
                folded = fold(norm(text))
                needle_f = fold(norm(needle))
                idx = folded.find(needle_f)
                if idx < 0:
                    idx = 0
                start = max(0, idx - 50)
                end = min(len(text), idx + len(needle) + 80)
                frag = text[start:end].strip()
                if start:
                    frag = "…" + frag
                if end < len(text):
                    frag = frag + "…"
                return f"{museum_name}: “{frag}”"
    return f"{museum_name}: “{plain(parts.get('title') or '')[:160]}”"


def build_queries(atlas: Atlas) -> list[tuple[str, dict | None]]:
    paired: list[tuple[str, dict]] = []
    seen: set[str] = set()
    for phrase, island in search_phrases(atlas):
        if (island.get("area") or 0) < 8:
            continue
        if name_key(island["name"]) in ARCHIPELAGO_KEYS:
            continue
        phrase = clean_query(phrase)
        key = fold(phrase)
        if not phrase or key in BARE_SKIP or key in seen:
            continue
        seen.add(key)
        paired.append((phrase, island))
        if len(paired) >= 120:
            break
    queries: list[tuple[str, dict | None]] = []
    seen.clear()
    for phrase in LANDMARKS:
        phrase = clean_query(phrase)
        key = fold(phrase)
        if not phrase or key in seen:
            continue
        seen.add(key)
        queries.append((phrase, None))
    for phrase, island in paired:
        key = fold(phrase)
        if key in seen:
            continue
        seen.add(key)
        queries.append((phrase, island))
    return queries


def cache_slug(query: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", fold(norm(query))).strip("-")
    return slug[:90] or "query"


def safe_load(path: Path):
    try:
        return load_json(path, None)
    except Exception:
        return None


def http_status(url: str) -> str:
    proc = subprocess.run(
        [
            "curl",
            "-sS",
            "-o",
            "/dev/null",
            "--max-time",
            "30",
            "-A",
            UA,
            "-w",
            "%{http_code}",
            url,
        ],
        capture_output=True,
        text=True,
    )
    return (proc.stdout or "").strip()


def fetch_json(url: str):
    """GET JSON via http_json. 404/410 are not retried; 429 and 5xx back off."""
    delay = 1.0
    for attempt in range(4):
        time.sleep(SLEEP)
        try:
            return http_json(url, timeout=60, user_agent=UA)
        except Exception as exc:  # noqa: BLE001 — keep harvesting after HTTP failures
            status = http_status(url)
            if status in {"400", "401", "403", "404", "410"}:
                print(f"  http {status} {url[:160]}", flush=True)
                return None
            print(
                f"  http error {attempt + 1}/4 status={status or '?'} {exc.__class__.__name__} :: {url[:160]}",
                flush=True,
            )
            time.sleep(delay)
            delay *= 2
    print(f"  gave up {url[:160]}", flush=True)
    return None


def curl_text(url: str) -> tuple[str, str]:
    """Return (body, error). Body is empty when curl fails."""
    delay = 1.0
    last = ""
    for attempt in range(3):
        time.sleep(SLEEP)
        proc = subprocess.run(
            ["curl", "-fsS", "--max-time", "40", "-A", UA, url],
            capture_output=True,
        )
        if proc.returncode == 0:
            return proc.stdout.decode("utf-8", "replace"), ""
        last = proc.stderr.decode("utf-8", "replace").strip()[:300]
        print(f"  terms fetch {attempt + 1}/3 failed {url} {last}", flush=True)
        time.sleep(delay)
        delay *= 2
    return "", last


def html_text(raw: str) -> str:
    text = re.sub(r"(?is)<script[\s\S]*?</script>", " ", raw)
    text = re.sub(r"(?is)<style[\s\S]*?</style>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def confirm_terms(url: str, needles: list[str]) -> dict:
    raw, error = curl_text(url)
    text = html_text(raw) if raw.lstrip().startswith("<") or "<html" in raw[:200].lower() else raw
    text = re.sub(r"\s+", " ", text)
    folded = text.lower()
    found = {needle: needle.lower() in folded for needle in needles}
    quotes = []
    for needle in needles:
        idx = folded.find(needle.lower())
        if idx >= 0:
            quotes.append(text[max(0, idx - 90) : idx + 220].strip())
    return {
        "url": url,
        "confirmed": all(found.values()) and bool(text),
        "needles": found,
        "quote": quotes[0] if quotes else "",
        "error": error,
    }


def confirm_licences() -> dict:
    """Fetch API docs / open-access terms with curl before any harvest call."""
    met_docs = confirm_terms(
        "https://metmuseum.github.io/",
        ["creative commons zero", "public domain"],
    )
    met_readme = confirm_terms(
        "https://raw.githubusercontent.com/metmuseum/openaccess/master/README.md",
        ["creative commons zero", "cc0"],
    )
    cleveland = confirm_terms(
        "https://www.clevelandart.org/open-access",
        ["creative commons zero", "cc0"],
    )
    aic_docs = confirm_terms(
        "https://api.artic.edu/docs/",
        ["creative commons zero (cc0)"],
    )
    aic_images = confirm_terms(
        "https://www.artic.edu/open-access/open-access-images",
        ["creative commons zero (cc0)"],
    )
    # v1 search was retired; record the live status and use v1.1.
    time.sleep(SLEEP)
    probe = subprocess.run(
        [
            "curl",
            "-sS",
            "--max-time",
            "30",
            "-A",
            UA,
            "-H",
            "Accept: application/json",
            "-w",
            "\n%{http_code}",
            "https://collectionapi.metmuseum.org/public/collection/v1/search?hasImages=true&q=Staffa",
        ],
        capture_output=True,
        text=True,
    )
    probe_lines = (probe.stdout or "").strip().splitlines()
    probe_code = probe_lines[-1] if probe_lines else ""
    probe_body = "\n".join(probe_lines[:-1])[:400]
    met_ok = met_docs["confirmed"] and met_readme["confirmed"]
    aic_ok = aic_docs["confirmed"] and aic_images["confirmed"]
    return {
        "met": {
            "confirmed": met_ok,
            "metadata": "CC0" if met_ok else "",
            "images": "CC0 when isPublicDomain is true" if met_ok else "",
            "docs": met_docs,
            "readme": met_readme,
            "v1_search_status": probe_code,
            "v1_search_body": probe_body,
            "search": "https://collectionapi.metmuseum.org/public/collection/v1.1/search",
            "note": (
                "Metadata is CC0 on metmuseum.github.io and the Open Access README. "
                "README: companion images of works covered by the policy carry the CC0 icon; "
                "the API serves public-domain JPEGs when isPublicDomain is true. "
                "/public/collection/v1/search was retired on 2026-10-01; harvest uses "
                "/public/collection/v1.1/search with hasImages, q, and limit, then "
                "GET /public/collection/v1/objects/{id}."
            ),
        },
        "cleveland": {
            "confirmed": cleveland["confirmed"],
            "metadata": "CC0" if cleveland["confirmed"] else "",
            "images": "CC0 for works with share_license_status CC0" if cleveland["confirmed"] else "",
            "terms": cleveland,
            "note": (
                "Cleveland open-access page: images of public-domain works and metadata "
                "are Creative Commons Zero (CC0). Rows require share_license_status CC0."
            ),
        },
        "aic": {
            "confirmed": aic_ok,
            "metadata": "CC0 (description field is CC BY 4.0)" if aic_ok else "",
            "images": "CC0 when is_public_domain is true" if aic_ok else "",
            "docs": aic_docs,
            "images_page": aic_images,
            "note": (
                "API docs: artwork data other than description is CC0; the description "
                "field is CC BY 4.0. Open-access images page: public-domain images are CC0. "
                "Only is_public_domain works are kept. Evidence prefers title, place, and medium."
            ),
        },
    }


def cached_search(museum: str, query: str, url: str):
    path = CACHE / museum / "search" / f"{cache_slug(query)}.json"
    cached = safe_load(path) if path.exists() else None
    if isinstance(cached, dict) and cached.get("empty") is True:
        return "empty", cached
    if isinstance(cached, dict) and cached.get("payload"):
        return "hit", cached["payload"]
    payload = fetch_json(url)
    if payload is None:
        return "error", None
    empty = False
    if museum == "met":
        empty = not payload.get("objectIDs")
    else:
        empty = not payload.get("data")
    if empty:
        save_json(path, {"empty": True, "query": query, "fetchedAt": utc_now(), "url": url})
        return "empty", payload
    save_json(path, {"empty": False, "query": query, "fetchedAt": utc_now(), "url": url, "payload": payload})
    return "hit", payload


def met_object(object_id: int):
    path = CACHE / "met" / "objects" / f"{object_id}.json"
    cached = safe_load(path) if path.exists() else None
    if isinstance(cached, dict) and cached.get("missing"):
        return None
    if isinstance(cached, dict) and "isPublicDomain" in cached:
        return cached
    payload = fetch_json(
        f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{object_id}"
    )
    if isinstance(payload, dict) and "isPublicDomain" in payload:
        save_json(path, payload)
        return payload
    save_json(path, {"missing": True, "objectID": object_id, "fetchedAt": utc_now()})
    return None


def tag_text(tags) -> str:
    terms = []
    for tag in tags or []:
        if isinstance(tag, dict) and tag.get("term"):
            terms.append(str(tag["term"]))
        elif isinstance(tag, str):
            terms.append(tag)
    return " ".join(terms)


def consider(state: dict, museum: str, query: str, paired, parts: dict, index: AliasIndex) -> str:
    if len(state["rows"]) >= MAX_ROWS:
        return "cap"
    if not plain(parts.get("title")) or not plain(parts.get("source_url")):
        state["skipped_phrase"] += 1
        return "phrase"
    kind = artwork_kind(parts.get("type_text") or "", parts.get("title") or "", index)
    if not kind:
        state["skipped_type"] += 1
        return "type"
    island, needle = match_hit(query, paired, parts, index)
    if not island:
        state["skipped_phrase"] += 1
        return "phrase"
    cap_key = (museum, island["id"])
    if state["per_island"][cap_key] >= PER_ISLAND:
        state["skipped_cap"] += 1
        return "island-cap"
    object_key = f"{museum}:{parts['object_id']}"
    if object_key in state["objects"]:
        return "dup-object"
    state["objects"].add(object_key)
    needles = [needle, island["name"], query]
    evidence = evidence_for(parts["museum_name"], parts, needles)
    museum_name = parts["museum_name"]
    collection = museum_name[4:] if museum_name.lower().startswith("the ") else museum_name
    summary = (
        f"{parts['title']} is a {kind} in the {collection} collection, "
        f"connected with {island['name']}."
    )
    image = None
    if parts.get("image_ok") and parts.get("thumb"):
        image = {
            "thumbUrl": parts["thumb"],
            "pageUrl": parts["source_url"],
            "attribution": parts["museum_name"],
            "licence": "CC0",
            "licenceUrl": CC0_URL,
        }
    row = artwork_row(
        island=island,
        title=parts["title"],
        source_url=parts["source_url"],
        source_title=parts["museum_name"],
        licence="CC0",
        evidence=evidence,
        summary=summary,
        external_id=object_key,
        open_image=image,
        seen=state["seen"],
    )
    if not row:
        state["skipped_dup"] += 1
        return "dup"
    state["rows"].append(row)
    state["per_island"][cap_key] += 1
    state["accepted"][museum] += 1
    return "accepted"


def harvest_met(state, query, paired, index: AliasIndex):
    url = "https://collectionapi.metmuseum.org/public/collection/v1.1/search?" + urllib.parse.urlencode(
        {"hasImages": "true", "q": query, "limit": str(PER_QUERY), "offset": "0"}
    )
    status, payload = cached_search("met", query, url)
    if status != "hit":
        return status, 0
    accepted = 0
    examined = 0
    for object_id in (payload.get("objectIDs") or [])[:PER_QUERY]:
        if len(state["rows"]) >= MAX_ROWS:
            break
        examined += 1
        obj = met_object(object_id)
        if not obj:
            state["http_skips"] += 1
            continue
        if not obj.get("isPublicDomain"):
            state["skipped_pd"] += 1
            continue
        title = plain(obj.get("title"))
        medium = " ".join(
            plain(obj.get(key))
            for key in ("objectName", "medium", "classification")
            if obj.get(key)
        )
        place = " ".join(
            plain(obj.get(key))
            for key in ("city", "state", "country", "region", "subregion", "locale", "locus")
            if obj.get(key)
        )
        place = plain(f"{place} {tag_text(obj.get('tags'))}")
        thumb = plain(obj.get("primaryImageSmall")) or plain(obj.get("primaryImage"))
        image_ok = bool(obj.get("isPublicDomain") and thumb.startswith("https://"))
        outcome = consider(
            state,
            "met",
            query,
            paired,
            {
                "museum_name": "The Metropolitan Museum of Art",
                "object_id": obj.get("objectID"),
                "title": title,
                "description": "",
                "credit": plain(obj.get("creditLine")),
                "medium": medium,
                "place": place,
                "type_text": medium,
                "source_url": f"https://www.metmuseum.org/art/collection/search/{obj.get('objectID')}",
                "thumb": thumb,
                "image_ok": image_ok,
            },
            index,
        )
        if outcome == "accepted":
            accepted += 1
        if outcome == "cap":
            break
    return "hit", examined


def harvest_cleveland(state, query, paired, index: AliasIndex):
    url = "https://openaccess-api.clevelandart.org/api/artworks/?" + urllib.parse.urlencode(
        {"q": query, "has_image": "1", "cc0": "1", "limit": "20"}
    )
    status, payload = cached_search("cleveland", query, url)
    if status != "hit":
        return status, 0
    accepted = 0
    examined = 0
    for item in (payload.get("data") or [])[:PER_QUERY]:
        if len(state["rows"]) >= MAX_ROWS:
            break
        examined += 1
        licence = plain(item.get("share_license_status"))
        if "cc0" not in licence.lower():
            state["skipped_pd"] += 1
            continue
        title = plain(item.get("title"))
        technique = plain(item.get("technique"))
        kind_text = " ".join(
            part
            for part in (plain(item.get("type")), technique, plain(item.get("department")))
            if part
        )
        # Department names such as "Prints" are broad; type + technique decide.
        type_text = " ".join(part for part in (plain(item.get("type")), technique) if part)
        images = item.get("images") or {}
        thumb = ""
        if isinstance(images, dict):
            for size in ("web", "print", "full"):
                url_value = (images.get(size) or {}).get("url") if isinstance(images.get(size), dict) else ""
                if url_value:
                    thumb = plain(url_value)
                    break
        description = " ".join(
            plain(item.get(key))
            for key in ("description", "did_you_know", "artlens_description")
            if item.get(key)
        )
        culture = item.get("culture") or []
        if isinstance(culture, list):
            culture_text = " ".join(str(part) for part in culture)
        else:
            culture_text = plain(culture)
        outcome = consider(
            state,
            "cleveland",
            query,
            paired,
            {
                "museum_name": "Cleveland Museum of Art",
                "object_id": item.get("id"),
                "title": title,
                "description": description,
                "credit": plain(item.get("creditline")),
                "medium": type_text or kind_text,
                "place": plain(f"{item.get('find_spot') or ''} {culture_text}"),
                "type_text": type_text or kind_text,
                "source_url": plain(item.get("url")),
                "thumb": thumb if thumb.startswith("https://") else "",
                "image_ok": thumb.startswith("https://"),
            },
            index,
        )
        if outcome == "accepted":
            accepted += 1
        if outcome == "cap":
            break
    return "hit", examined


def harvest_aic(state, query, paired, index: AliasIndex, iiif_holder: dict):
    params = [
        ("q", query),
        ("limit", str(PER_QUERY)),
        (
            "fields",
            "id,title,artist_display,date_display,medium_display,thumbnail,description,"
            "place_of_origin,artwork_type_title,is_public_domain,api_link,image_id",
        ),
        ("query[term][is_public_domain]", "true"),
    ]
    url = "https://api.artic.edu/api/v1/artworks/search?" + urllib.parse.urlencode(params)
    status, payload = cached_search("aic", query, url)
    if status != "hit":
        return status, 0
    config = payload.get("config") or {}
    if config.get("iiif_url"):
        iiif_holder["url"] = config["iiif_url"].rstrip("/")
    iiif = iiif_holder.get("url") or "https://www.artic.edu/iiif/2"
    accepted = 0
    examined = 0
    for item in (payload.get("data") or [])[:PER_QUERY]:
        if len(state["rows"]) >= MAX_ROWS:
            break
        examined += 1
        if not item.get("is_public_domain"):
            state["skipped_pd"] += 1
            continue
        image_id = plain(item.get("image_id"))
        thumb = f"{iiif}/{image_id}/full/843,/0/default.jpg" if image_id else ""
        type_text = " ".join(
            part
            for part in (plain(item.get("artwork_type_title")), plain(item.get("medium_display")))
            if part
        )
        outcome = consider(
            state,
            "aic",
            query,
            paired,
            {
                "museum_name": "Art Institute of Chicago",
                "object_id": item.get("id"),
                "title": plain(item.get("title")),
                "description": plain(item.get("description")),
                "credit": "",
                "medium": plain(item.get("medium_display")),
                "place": plain(item.get("place_of_origin")),
                "type_text": type_text,
                "source_url": f"https://www.artic.edu/artworks/{item.get('id')}",
                "thumb": thumb,
                "image_ok": bool(image_id),
            },
            index,
        )
        if outcome == "accepted":
            accepted += 1
        if outcome == "cap":
            break
    return "hit", examined


def write_output(state: dict, licences: dict, queries: list, completed: bool) -> None:
    by_museum = defaultdict(lambda: defaultdict(int))
    for row in state["rows"]:
        museum = (row.get("external_id") or "").split(":", 1)[0]
        by_museum[museum][row.get("island_name") or row.get("island_id")] += 1
    museum_islands = {
        museum: sorted(counts, key=lambda name: (-counts[name], name))
        for museum, counts in by_museum.items()
    }
    top = defaultdict(int)
    for row in state["rows"]:
        top[row.get("island_name") or ""] += 1
    payload = {
        "slug": "artwork-museums",
        "generatedAt": utc_now(),
        "meta": {
            "licences": licences,
            "completed": completed,
            "queries": len(queries),
            "accepted": dict(state["accepted"]),
            "islands": museum_islands,
            "topIslands": sorted(top, key=lambda name: (-top[name], name))[:15],
            "skipped": {
                "type": state["skipped_type"],
                "phrase": state["skipped_phrase"],
                "not_public_domain_or_not_cc0": state["skipped_pd"],
                "per_island_cap": state["skipped_cap"],
                "duplicate": state["skipped_dup"],
                "http": state["http_skips"],
            },
            "caps": {"perQuery": PER_QUERY, "perIslandPerMuseum": PER_ISLAND, "overall": MAX_ROWS},
        },
        "rows": state["rows"],
    }
    save_json(OUT, payload)


def self_check(atlas: Atlas, index: AliasIndex) -> None:
    staffa = index.resolve("Staffa")
    assert staffa and staffa["name"] == "Staffa", staffa
    skye = index.resolve("Isle of Skye")
    assert skye and "Skye" in skye["name"], skye
    mount = index.resolve("St Michael's Mount")
    assert mount and "Michael" in mount["name"], mount
    assert match_island_phrase(atlas, "Orkney") is None
    assert match_island_phrase(atlas, "Shetland") is None
    assert not phrase_in_text("Staffa", "Head of Staff")
    assert artwork_kind("Watercolor and gouache over graphite", "The Cuillin Hills", index) == "watercolour"
    assert artwork_kind("Albumen print from calotype", "Lindisfarne", index) is None
    assert artwork_kind("Etching and mezzotint", "Holy Island Cathedral", index) == "etching"
    assert artwork_kind("Gelatin silver print", "The Needle, Isle of Skye", index) is None
    island, _needle = match_hit(
        "Fingal's Cave",
        None,
        {
            "title": "Fingal's Cave, Staffa",
            "description": "Oil sketch of the cave.",
            "credit": "",
            "medium": "Oil on canvas",
            "place": "",
        },
        index,
    )
    assert island and island["name"] == "Staffa", island
    missing, _needle = match_hit(
        "Fingal's Cave",
        None,
        {
            "title": "View of Fingal's Cave",
            "description": "A cave interior.",
            "credit": "",
            "medium": "Pen and ink",
            "place": "",
        },
        index,
    )
    assert missing is None
    wight, _needle = match_hit(
        "Isle of Skye",
        None,
        {
            "title": "Culver Cliff, Isle of Wight",
            "description": "",
            "credit": "",
            "medium": "Watercolor",
            "place": "",
        },
        index,
    )
    assert wight is None
    cuillin, _needle = match_hit(
        "Isle of Skye",
        None,
        {
            "title": "The Cuillin Hills, Isle of Skye",
            "description": "",
            "credit": "",
            "medium": "Watercolor",
            "place": "",
        },
        index,
    )
    assert cuillin and cuillin["id"] == "isle-of-skye"
    loch, _needle = match_hit(
        "Isle of Skye",
        None,
        {
            "title": "Loch Coruisk, Skye",
            "description": "",
            "credit": "",
            "medium": "Oil on canvas",
            "place": "",
        },
        index,
    )
    assert loch and loch["id"] == "isle-of-skye"
    durham, _needle = match_hit(
        "Holy Island",
        None,
        {
            "title": "Holy Island Castle, Durham",
            "description": "",
            "credit": "",
            "medium": "Graphite on paper",
            "place": "",
        },
        index,
    )
    assert durham and durham["id"] == "lindisfarne", durham
    family, _needle = match_hit(
        "Holy Island",
        None,
        {
            "title": "Holy Family",
            "description": "The Virgin and Child.",
            "credit": "",
            "medium": "Oil on panel",
            "place": "",
        },
        index,
    )
    assert family is None
    mountains, _needle = match_hit(
        "Jura",
        None,
        {
            "title": "View of Jura Mountains",
            "description": "",
            "credit": "",
            "medium": "Oil on canvas",
            "place": "",
        },
        index,
    )
    assert mountains is None
    yell, _needle = match_hit(
        "Yell",
        None,
        {
            "title": "Yell as much as you like",
            "description": "",
            "credit": "",
            "medium": "Lithograph",
            "place": "",
        },
        index,
    )
    assert yell is None
    new_jersey, _needle = match_hit(
        "Isle of Jersey",
        None,
        {
            "title": "Harvest, Montclair, New Jersey",
            "description": "",
            "credit": "",
            "medium": "Oil on canvas",
            "place": "United States",
        },
        index,
    )
    assert new_jersey is None
    jersey, _needle = match_hit(
        "Isle of Jersey",
        None,
        {
            "title": "Henri de Bourbon Visits an Old Man on the Isle of Jersey",
            "description": "",
            "credit": "",
            "medium": "Engraving",
            "place": "",
        },
        index,
    )
    assert jersey and "jersey" in jersey["name"].lower()
    tiree, _needle = match_hit(
        "Tiree",
        None,
        {
            "title": "Suite des Vases Tirée du Cabinet de Monsieur Du Tillot",
            "description": "",
            "credit": "",
            "medium": "Etching",
            "place": "",
        },
        index,
    )
    assert tiree is None
    holy, _needle = match_hit(
        "Holy Island",
        None,
        {
            "title": "Lindisfarne Castle, Holy Island, Northumberland",
            "description": "",
            "credit": "",
            "medium": "Watercolor",
            "place": "",
        },
        index,
    )
    assert holy and holy["id"] == "lindisfarne", holy
    print(
        f"self-check ok; alias singles={len(index.singles)} multis={len(index.multis)}",
        flush=True,
    )


def main() -> None:
    atlas = Atlas()
    index = AliasIndex(atlas)
    queries = build_queries(atlas)
    self_check(atlas, index)
    print(f"queries={len(queries)} (landmarks plus up to 120 large-island phrases)", flush=True)
    print("confirming museum open-access terms", flush=True)
    licences = confirm_licences()
    for museum, info in licences.items():
        print(
            f"  {museum}: confirmed={info['confirmed']} metadata={info.get('metadata')} images={info.get('images')}",
            flush=True,
        )
    state = {
        "rows": [],
        "seen": existing_artwork_keys(),
        "per_island": defaultdict(int),
        "accepted": defaultdict(int),
        "objects": set(),
        "skipped_type": 0,
        "skipped_phrase": 0,
        "skipped_pd": 0,
        "skipped_cap": 0,
        "skipped_dup": 0,
        "http_skips": 0,
    }
    harvesters = {
        "met": harvest_met,
        "cleveland": harvest_cleveland,
        "aic": harvest_aic,
    }
    iiif_holder = {"url": "https://www.artic.edu/iiif/2"}
    completed = False
    try:
        for query, paired in queries:
            if len(state["rows"]) >= MAX_ROWS:
                break
            for museum in ("met", "cleveland", "aic"):
                if len(state["rows"]) >= MAX_ROWS:
                    break
                if not licences[museum]["confirmed"]:
                    continue
                before = state["accepted"][museum]
                if museum == "aic":
                    status, examined = harvest_aic(state, query, paired, index, iiif_holder)
                else:
                    status, examined = harvesters[museum](state, query, paired, index)
                gained = state["accepted"][museum] - before
                print(
                    f"[{museum}] {query!r} {status} examined={examined} "
                    f"new={gained} museum_total={state['accepted'][museum]} overall={len(state['rows'])}",
                    flush=True,
                )
        completed = True
    finally:
        write_output(state, licences, queries, completed)
        print(
            f"wrote {OUT} rows={len(state['rows'])} "
            f"met={state['accepted']['met']} cleveland={state['accepted']['cleveland']} "
            f"aic={state['accepted']['aic']} completed={completed}",
            flush=True,
        )


if __name__ == "__main__":
    main()
