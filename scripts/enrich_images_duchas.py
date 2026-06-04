#!/usr/bin/env python3
"""Probe / stage National Folklore Collection photos via Dúchas.ie API (CBÉG).

Requires ``DUCHAS_API_KEY`` (or ``GAOIS_API_KEY``) in ``.env.local`` — register at
https://www.gaois.ie/en/technology/data. Uses Logainm place lookup + ``/api/v0.6/cbeg``
filtered by ``PlaceID``.

**Licence note:** Dúchas open data is published under **CC BY-NC 4.0**, which this
project does not redistribute (see ``docs/ETHICS.md``). The harvester therefore
records viability and probe results but does **not** stage adoptions unless a
permissive licence is returned (none expected).

Run::

    python3 scripts/enrich_images_duchas.py --limit 50
    python3 scripts/enrich_images_duchas.py --probe-only

Outputs::

    data/staging/adoptions/duchas.json          (empty unless licence policy changes)
    data/cache_duchas.json
    data/image_enrichment_duchas_report.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
STAGING = DATA / "staging" / "adoptions" / "duchas.json"
CACHE = DATA / "cache_duchas.json"
REPORT = DATA / "image_enrichment_duchas_report.json"
ENV_LOCAL = ROOT / ".env.local"

LOGAINM_API = "https://www.logainm.ie/api/v1.0"
DUCHAS_API = "https://www.duchas.ie/api/v0.6"
USER_AGENT = "isles-of-britain/0.1 duchas-enrichment"
DELAY_S = 1.2

ALLOWED_LICENCE_MARKERS = (
    "cc-by-4.0",
    "cc by 4.0",
    "cc0",
    "open government",
    "ogl",
    "public domain",
)
BLOCKED_LICENCE_MARKERS = (
    "by-nc",
    "non-commercial",
    "non commercial",
    "creative archive",
)

sys.path.insert(0, str(ROOT / "scripts"))
from enrich_images_v5 import (  # noqa: E402
    _haversine_km,
    _load,
    _load_named_index_ids,
    _mentions,
    _name_variants,
    _save,
)


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = val


def _api_key() -> str:
    return (
        os.environ.get("DUCHAS_API_KEY", "").strip()
        or os.environ.get("GAOIS_API_KEY", "").strip()
    )


def _get_json(url: str, params: dict[str, Any], api_key: str) -> dict:
    qs = urllib.parse.urlencode(params, doseq=True)
    full = f"{url}?{qs}" if qs else url
    req = urllib.request.Request(
        full,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "X-Api-Key": api_key,
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def _licence_allowed(text: str) -> bool:
    low = (text or "").lower()
    if any(b in low for b in BLOCKED_LICENCE_MARKERS):
        return False
    return any(a in low for a in ALLOWED_LICENCE_MARKERS)


def _island_lat(island: dict) -> float | None:
    lat = island.get("lat")
    return float(lat) if isinstance(lat, (int, float)) else None


def _island_lon(island: dict) -> float | None:
    lng = island.get("lng")
    if lng is None:
        lng = island.get("lon")
    return float(lng) if isinstance(lng, (int, float)) else None


def logainm_search_place(
    island: dict,
    cache: dict,
    api_key: str,
) -> dict | None:
    bucket = cache.setdefault("logainm", {})
    iid = island.get("id") or ""
    if iid in bucket:
        return bucket[iid]

    name = (island.get("name") or "").strip()
    params = {"query": name, "category": "GF", "maxResults": 8}
    try:
        payload = _get_json(f"{LOGAINM_API}/places", params, api_key)
    except Exception as exc:
        bucket[iid] = {"error": repr(exc)}
        _save(CACHE, cache)
        return None

    lat_i, lon_i = _island_lat(island), _island_lon(island)
    best: dict | None = None
    best_km = 999.0
    for row in payload if isinstance(payload, list) else payload.get("places", []):
        if not isinstance(row, dict):
            continue
        place_id = row.get("id") or row.get("placeID")
        geo = row.get("geography") or row.get("geo") or {}
        lat = geo.get("latitude") or geo.get("lat")
        lon = geo.get("longitude") or geo.get("lon") or geo.get("lng")
        if lat_i is not None and lon_i is not None and lat is not None and lon is not None:
            km = _haversine_km(lat_i, lon_i, float(lat), float(lon))
        else:
            km = 999.0
        label = (row.get("placename") or row.get("name") or "").strip()
        if label and not _mentions(label, _name_variants(island)):
            continue
        if km < best_km:
            best_km = km
            best = {"placeId": place_id, "name": label, "km": km}

    bucket[iid] = best or {}
    _save(CACHE, cache)
    time.sleep(DELAY_S)
    return best


def fetch_cbeg_for_place(
    place_id: int | str,
    cache: dict,
    api_key: str,
) -> list[dict]:
    bucket = cache.setdefault("cbeg", {})
    key = str(place_id)
    if key in bucket:
        return bucket[key].get("photos", [])

    params = {"PlaceID": place_id, "Digitized": "true"}
    try:
        payload = _get_json(f"{DUCHAS_API}/cbeg", params, api_key)
    except Exception as exc:
        bucket[key] = {"error": repr(exc), "photos": []}
        _save(CACHE, cache)
        return []

    photos = payload if isinstance(payload, list) else payload.get("photos", payload)
    if not isinstance(photos, list):
        photos = []
    bucket[key] = {
        "fetched": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "count": len(photos),
        "photos": photos[:40],
        "licenceNote": "Dúchas default CC BY-NC 4.0 — not staged by policy",
    }
    _save(CACHE, cache)
    time.sleep(DELAY_S)
    return photos


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--test", metavar="ID")
    p.add_argument("--probe-only", action="store_true", help="API probe; never stage.")
    p.add_argument(
        "--include-unnamed",
        action="store_true",
        help="Include islands not in islands_index.json (default: named only).",
    )
    args = p.parse_args()

    _load_dotenv(ENV_LOCAL)
    api_key = _api_key()

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    pending = [
        i for i in islands
        if not (i.get("images") or [])
        and (i.get("nation") or "").strip().lower() in ("ireland", "northern ireland")
    ]
    if not args.include_unnamed:
        named_ids = _load_named_index_ids()
        if named_ids:
            pending = [i for i in pending if i.get("id") in named_ids]
    if args.test:
        pending = [i for i in islands if i.get("id") == args.test]
    if args.limit:
        pending = pending[: args.limit]

    report: dict[str, Any] = {
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "args": vars(args),
        "pending": len(pending),
        "api_key_present": bool(api_key),
        "viability": {
            "api_exists": True,
            "endpoint": f"{DUCHAS_API}/cbeg",
            "default_licence": "CC BY-NC 4.0",
            "staged_under_project_policy": False,
            "reason": "ETHICS.md excludes non-commercial licences",
        },
        "probes": [],
        "adopted": [],
        "rejected": [],
    }

    if not api_key:
        report["viability"]["blocked"] = "missing DUCHAS_API_KEY / GAOIS_API_KEY"
        print("No DUCHAS_API_KEY — API probe skipped (register at gaois.ie).", flush=True)
        staged: list[dict[str, Any]] = []
        n_adopted = 0
    else:
        cache = _load(CACHE)
        staged = []
        n_adopted = 0
        photos_seen = 0
        for isl in pending:
            place = logainm_search_place(isl, cache, api_key)
            probe: dict[str, Any] = {
                "id": isl["id"],
                "name": isl.get("name"),
                "logainm": place,
            }
            if not place or not place.get("placeId"):
                report["rejected"].append({**probe, "reason": "no-logainm-place"})
                report["probes"].append(probe)
                continue
            photos = fetch_cbeg_for_place(place["placeId"], cache, api_key)
            photos_seen += len(photos)
            probe["cbeg_count"] = len(photos)
            report["probes"].append(probe)
            if args.probe_only:
                continue
            for photo in photos:
                if not isinstance(photo, dict):
                    continue
                lic = (
                    photo.get("licence")
                    or photo.get("license")
                    or "CC BY-NC 4.0"
                )
                if not _licence_allowed(str(lic)):
                    report["rejected"].append({
                        "id": isl["id"],
                        "reason": f"licence-blocked:{lic}",
                        "photoId": photo.get("id"),
                    })
                    continue
                # No known permissive licence on CBÉG — keep for future policy change.
                url = photo.get("imageUrl") or photo.get("url") or ""
                if not url:
                    continue
                rec = {
                    "url": url,
                    "source": "duchas-cbeg",
                    "sourceRef": f"duchas:cbeg:{photo.get('id')}",
                    "sourcePageUrl": photo.get("pageUrl")
                    or f"https://www.duchas.ie/en/cbeg/{photo.get('id')}",
                    "license": lic,
                    "attribution": "National Folklore Collection / Dúchas",
                    "imageConfidence": "medium",
                }
                entry = {
                    "id": isl["id"],
                    "name": isl.get("name", ""),
                    "image": rec,
                }
                staged.append(entry)
                report["adopted"].append(entry)
                n_adopted += 1
                break

        report["photos_seen"] = photos_seen
        report["viability"]["photos_seen_sample"] = photos_seen

    STAGING.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pipeline": "enrich_images_duchas",
        "attempted": len(pending),
        "staged_count": n_adopted,
        "viable": False,
        "viability": report["viability"],
        "adoptions": staged,
    }
    STAGING.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    report["staged_total"] = n_adopted
    _save(REPORT, report)

    print(f"Staging → {STAGING.relative_to(ROOT)} ({n_adopted:,})")
    print(f"Report  → {REPORT.relative_to(ROOT)}")
    print(f"Viable for merge: {report['viability'].get('staged_under_project_policy', False)}")
    return n_adopted


if __name__ == "__main__":
    count = main()
    print(f"adoption_count={count}")
    raise SystemExit(0)
