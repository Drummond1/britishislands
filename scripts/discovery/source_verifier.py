"""Source Verification Agent — confirm candidates against external sources."""

from __future__ import annotations

import sys
import time
import urllib.parse
from typing import Any

from . import common as c


def _wb_search(name: str, language: str = "en") -> list[dict]:
    params = {
        "action": "wbsearchentities",
        "search": name,
        "language": language,
        "format": "json",
        "limit": 8,
    }
    url = "https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(params)
    payload = c.get_json(url)
    return list(payload.get("search") or [])


def _wb_claims(qid: str) -> dict:
    cache = c.load_json(c.CACHE_WD, {})
    if qid in cache:
        return cache[qid]
    params = {
        "action": "wbgetentities",
        "ids": qid,
        "props": "claims|labels|sitelinks",
        "languages": "en|ga|gd|cy",
        "format": "json",
    }
    url = "https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(params)
    payload = c.get_json(url)
    entity = (payload.get("entities") or {}).get(qid) or {}
    cache[qid] = entity
    c.save_json(c.CACHE_WD, cache)
    time.sleep(c.DELAY_S)
    return entity


def _coord_from_claims(entity: dict) -> tuple[float, float] | None:
    coord = ((entity.get("claims") or {}).get("P625") or [{}])[0]
    value = (coord.get("mainsnak") or {}).get("datavalue", {}).get("value") or {}
    lat = value.get("latitude")
    lng = value.get("longitude")
    if lat is None or lng is None:
        return None
    return float(lat), float(lng)


def _wikipedia_from_entity(entity: dict) -> str:
    for site, link in (entity.get("sitelinks") or {}).items():
        if site.endswith("wiki") and not site.startswith("commons"):
            title = link.get("title") or ""
            lang = site.replace("wiki", "")
            if lang and title:
                return f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
    return ""


def _verify_one(candidate: dict) -> dict:
    sources: list[dict] = list(candidate.get("sourceHints") or [])
    aliases = list(candidate.get("aliases") or [])
    wikidata = candidate.get("wikidata") or ""
    wikipedia = candidate.get("wikipedia") or ""
    confidence = candidate.get("scanConfidence", "low")
    notes: list[str] = []
    verified = False

    if wikidata:
        entity = _wb_claims(wikidata)
        if entity and entity.get("id"):
            verified = True
            confidence = "high"
            wikipedia = wikipedia or _wikipedia_from_entity(entity)
            coord = _coord_from_claims(entity)
            if coord:
                d = c.haversine_km(candidate["lat"], candidate["lng"], coord[0], coord[1])
                if d > 5:
                    notes.append(f"wikidata_coord_delta_km={round(d, 2)}")
                    confidence = "medium"
            sources.append(
                {
                    "name": "wikidata",
                    "ref": wikidata,
                    "url": f"https://www.wikidata.org/wiki/{wikidata}",
                    "license": "CC0",
                }
            )
            for lang in ("en", "ga", "gd", "cy"):
                label = ((entity.get("labels") or {}).get(lang) or {}).get("value")
                if label and label not in aliases and label != candidate["name"]:
                    aliases.append(label)

    if not verified:
        hits = _wb_search(candidate["name"])
        time.sleep(c.DELAY_S)
        for hit in hits:
            qid = hit.get("id")
            if not qid:
                continue
            entity = _wb_claims(qid)
            coord = _coord_from_claims(entity)
            if not coord:
                continue
            if c.haversine_km(candidate["lat"], candidate["lng"], coord[0], coord[1]) > 3:
                continue
            wikidata = qid
            wikipedia = wikipedia or _wikipedia_from_entity(entity)
            verified = True
            confidence = "medium"
            sources.append(
                {
                    "name": "wikidata",
                    "ref": qid,
                    "url": f"https://www.wikidata.org/wiki/{qid}",
                    "license": "CC0",
                }
            )
            break

    if wikipedia and not any(s.get("name") == "wikipedia" for s in sources):
        sources.append(
            {
                "name": "wikipedia",
                "url": wikipedia,
                "license": "CC-BY-SA-4.0",
            }
        )
        if not verified:
            verified = True
            confidence = "medium"

    if candidate.get("osmType") and candidate.get("osmId") is not None:
        verified = True
        if confidence == "low":
            confidence = "medium"

    if not verified:
        return {
            **candidate,
            "verified": False,
            "verificationConfidence": "rejected",
            "sources": sources,
            "aliases": aliases,
            "wikidata": wikidata,
            "wikipedia": wikipedia,
            "notes": notes + ["no_reliable_named_source"],
        }

    return {
        **candidate,
        "verified": True,
        "verificationConfidence": confidence,
        "sources": sources,
        "aliases": aliases,
        "wikidata": wikidata,
        "wikipedia": wikipedia,
        "notes": notes,
    }


def run(*, limit: int | None = None) -> dict[str, Any]:
    scan = c.load_json(c.SCAN_PATH, {})
    candidates = list(scan.get("candidates") or [])
    if limit:
        candidates = candidates[:limit]

    verified_rows: list[dict] = []
    rejected = 0
    for idx, candidate in enumerate(candidates, start=1):
        row = _verify_one(candidate)
        verified_rows.append(row)
        if not row.get("verified"):
            rejected += 1
        if idx % 25 == 0:
            print(f"Source Verification: {idx}/{len(candidates)}", file=sys.stderr)

    report = {
        "agent": "source_verifier",
        "inputCandidates": len(candidates),
        "verified": sum(1 for row in verified_rows if row.get("verified")),
        "rejected": rejected,
        "records": verified_rows,
    }
    c.save_json(c.VERIFY_PATH, report)
    print(
        f"Source Verification: {report['verified']} verified, {rejected} rejected",
        file=sys.stderr,
    )
    return report
