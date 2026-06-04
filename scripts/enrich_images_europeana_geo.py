#!/usr/bin/env python3
"""Europeana lead-photo staging with geo filter + island name (dual-signal).

Targets named atlas islands without ``images[]``. Uses the Europeana Search API
when ``EUROPEANA_API_KEY`` (or ``EUROPEANA_WSKEY``) is set in ``.env.local``.

Without a key, the Search API returns 401. Public endpoints that work without a
key are documented in the run report but are **not** used for per-island harvest
(SPARQL text search times out; OAI-PMH has no geo+name search; Thumbnail API needs
known media URLs). Register a free key at https://pro.europeana.eu.

Run::

    python3 scripts/enrich_images_europeana_geo.py --named-only --limit 400
    python3 scripts/enrich_images_europeana_geo.py --dry-run --test iona

Outputs (staging only)::

    data/staging/adoptions/europeana-geo.json
    data/cache_europeana_geo.json
    data/image_enrichment_europeana_geo_report.json
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
STAGING = DATA / "staging" / "adoptions" / "europeana-geo.json"
CACHE = DATA / "cache_europeana_geo.json"
REPORT = DATA / "image_enrichment_europeana_geo_report.json"
ENV_LOCAL = ROOT / ".env.local"

EUROPEANA_SEARCH = "https://api.europeana.eu/record/v2/search.json"
USER_AGENT = "isles-of-britain/0.1 europeana-geo-enrichment"
DEFAULT_DELAY_S = 1.5
DEFAULT_LIMIT = 400
EUROPEANA_ROWS = 20
SOURCE = "europeana-geo"

PUBLIC_ENDPOINTS_NO_KEY = [
    {
        "name": "Search API",
        "url": EUROPEANA_SEARCH,
        "note": "Requires wskey / x-api-key (401 without). Primary harvest path.",
    },
    {
        "name": "SPARQL",
        "url": "https://sparql.europeana.eu/sparql",
        "note": "Anonymous access; broad text queries timeout; not used per-island.",
    },
    {
        "name": "OAI-PMH",
        "url": "https://oaipmh.europeana.eu/oaipmh",
        "note": "Public metadata; no geo+name island search.",
    },
    {
        "name": "Thumbnail API",
        "url": "https://api.europeana.eu/thumbnail/v3/",
        "note": "No key required; needs known media URL (not discovery).",
    },
]

_CC_URL_RE = re.compile(
    r"creativecommons\.org/licenses/([a-z\-]+)/(\d+\.?\d*)",
    re.IGNORECASE,
)
_CC0_URL_RE = re.compile(r"creativecommons\.org/publicdomain/zero", re.IGNORECASE)
_PDM_URL_RE = re.compile(r"creativecommons\.org/publicdomain/mark", re.IGNORECASE)
_EXCLUDED_RIGHTS_RE = re.compile(
    r"(?:by-nc|by-nd|nc-nd|noncommercial|non-commercial|all-rights-reserved|"
    r"copyrighted|in-copyright|permission)",
    re.IGNORECASE,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from enrich_images_v5 import (  # noqa: E402
    _get_json,
    _haversine_km,
    _load,
    _load_named_index_ids,
    _mentions,
    _name_variants,
    _save,
)
from photo_staging_dual import (  # noqa: E402
    dual_signal_ok,
    island_lon,
    load_dotenv,
    looks_like_non_photo,
    make_adoption,
    save_staging,
)


def _europeana_key() -> str:
    return (
        os.environ.get("EUROPEANA_API_KEY", "").strip()
        or os.environ.get("EUROPEANA_WSKEY", "").strip()
    )


def _search_query(island: dict) -> str:
    name = (island.get("name") or "").strip()
    nation = (island.get("nation") or "").strip()
    if nation:
        return f'"{name}" {nation}'
    return f'"{name}"'


def _license_from_rights_urls(urls: list[str]) -> tuple[str, str] | None:
    if not urls:
        return None
    joined = " ".join(urls)
    if _EXCLUDED_RIGHTS_RE.search(joined):
        return None
    for u in urls:
        low = u.lower()
        if _CC0_URL_RE.search(low):
            return "CC0-1.0", "https://creativecommons.org/publicdomain/zero/1.0/"
        if _PDM_URL_RE.search(low):
            return "PDM", "http://creativecommons.org/publicdomain/mark/1.0/"
        m = _CC_URL_RE.search(u)
        if m:
            kind, ver = m.group(1).lower(), m.group(2)
            if "nc" in kind or "nd" in kind:
                continue
            if kind == "by":
                return f"CC-BY-{ver}", u
            if kind == "by-sa":
                return f"CC-BY-SA-{ver}", u
    return None


def _save_cache(cache: dict) -> None:
    payload = json.dumps(cache, ensure_ascii=False, separators=(",", ":"))
    tmp = CACHE.with_suffix(CACHE.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, CACHE)


def fetch_europeana(
    island: dict,
    api_key: str,
    cache: dict,
    delay_s: float,
) -> list[dict]:
    iid = island.get("id") or ""
    if iid in cache:
        entry = cache[iid]
        if isinstance(entry, dict) and isinstance(entry.get("items"), list):
            return entry["items"]

    q = _search_query(island)
    lat = island.get("lat")
    lon = island_lon(island)
    qf: list[str] = ["TYPE:IMAGE"]
    if isinstance(lat, (int, float)) and lon is not None:
        qf.append(f"WHERE:{lat},{lon},25")

    params: dict[str, Any] = {
        "wskey": api_key,
        "query": q,
        "reusability": "open",
        "qf": qf,
        "profile": "rich",
        "rows": EUROPEANA_ROWS,
        "start": 1,
    }
    try:
        payload = _get_json(EUROPEANA_SEARCH, params)
    except Exception as exc:
        print(f"  europeana failed for {iid}: {exc!r}", file=sys.stderr)
        cache[iid] = {"query": q, "error": repr(exc), "items": []}
        _save_cache(cache)
        time.sleep(delay_s)
        return []

    items = payload.get("items") or []
    cache[iid] = {
        "query": q,
        "qf": qf,
        "fetched": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "itemsCount": payload.get("itemsCount"),
        "items": items,
    }
    _save_cache(cache)
    time.sleep(delay_s)
    return items


def _europeana_coords(item: dict) -> tuple[float, float] | None:
    def _first_float(vals: Any) -> float | None:
        if isinstance(vals, list):
            for v in vals:
                try:
                    return float(str(v).strip())
                except (TypeError, ValueError):
                    continue
        elif vals is not None:
            try:
                return float(str(vals).strip())
            except (TypeError, ValueError):
                return None
        return None

    lat = _first_float(item.get("edmPlaceLatitude"))
    lon = _first_float(item.get("edmPlaceLongitude"))
    if lat is not None and lon is not None:
        return lat, lon
    return None


def build_image_record(item: dict) -> dict | None:
    rights = item.get("rights") or []
    if isinstance(rights, str):
        rights = [rights]
    lic = _license_from_rights_urls([str(r) for r in rights])
    if not lic:
        return None
    license_label, license_url = lic

    url = (item.get("edmPreview") or "").strip()
    if not url:
        shown = item.get("isShownBy")
        if isinstance(shown, list):
            url = (shown[0] if shown else "").strip()
        elif shown:
            url = str(shown).strip()
    if not url.startswith("http"):
        return None

    titles = item.get("title") or []
    if isinstance(titles, str):
        titles = [titles]
    title = (titles[0] if titles else "").strip()
    if looks_like_non_photo(title):
        return None

    page = (item.get("guid") or item.get("link") or "").strip()
    rec_id = (item.get("id") or "").strip() or page
    creators = item.get("dcCreator") or []
    if isinstance(creators, str):
        creators = [creators]
    creator = (creators[0] if creators else "").strip() or "Unknown"
    provider = item.get("dataProvider") or item.get("provider") or "Europeana"
    if isinstance(provider, list):
        provider = (provider[0] if provider else "Europeana")
    provider = str(provider).strip()

    return {
        "url": url,
        "source": SOURCE,
        "sourceRef": rec_id,
        "sourcePageUrl": page or url,
        "license": license_label,
        "licenseUrl": license_url,
        "attribution": f"\"{title}\" by {creator} via {provider} ({license_label})",
        "caption": title,
    }


def pick_candidate(
    island: dict,
    items: list[dict],
    rejected: list[dict],
) -> tuple[dict, dict[str, Any]] | None:
    best: tuple[float, dict, dict[str, Any]] | None = None

    for item in items:
        titles = item.get("title") or []
        if isinstance(titles, str):
            titles = [titles]
        title = (titles[0] if titles else "").strip()
        desc_parts = item.get("dcDescription") or []
        if isinstance(desc_parts, str):
            desc_parts = [desc_parts]
        desc = " ".join(str(d) for d in desc_parts)
        spatial = item.get("dctermsSpatial") or []
        if isinstance(spatial, str):
            spatial = [spatial]
        blob = " ".join([desc, " ".join(str(s) for s in spatial)])

        coords = _europeana_coords(item)
        rlat, rlon = (coords[0], coords[1]) if coords else (None, None)
        ok, verification = dual_signal_ok(
            island,
            title=title,
            blob=blob,
            result_lat=rlat,
            result_lon=rlon,
            mentions_fn=_mentions,
            name_variants_fn=_name_variants,
            haversine_km_fn=_haversine_km,
        )
        if not ok:
            rejected.append({
                "id": island.get("id"),
                "europeana_id": item.get("id"),
                "reason": verification.get("reason"),
                "title": title[:120],
            })
            continue

        rec = build_image_record(item)
        if not rec:
            rejected.append({
                "id": island.get("id"),
                "europeana_id": item.get("id"),
                "reason": "license-or-url-blocked",
                "title": title[:120],
            })
            continue

        dist = float(verification.get("distance_km") or 999)
        if best is None or dist < best[0]:
            best = (dist, rec, verification)

    if best is None:
        return None
    _, rec, verification = best
    return rec, verification


def main() -> int:
    load_dotenv(ENV_LOCAL)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--named-only", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Max islands to attempt (default {DEFAULT_LIMIT}).",
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--delay", type=float, default=DEFAULT_DELAY_S)
    p.add_argument("--test", default="", help="Single island id.")
    args = p.parse_args()
    delay_s = max(0.0, float(args.delay))

    api_key = _europeana_key()
    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    pending = [i for i in islands if not (i.get("images") or [])]
    if args.named_only:
        named_ids = _load_named_index_ids()
        if named_ids:
            before = len(pending)
            pending = [i for i in pending if i.get("id") in named_ids]
            print(f"  named-only: {len(pending):,} of {before:,} without images", flush=True)
    if args.test:
        pending = [i for i in islands if i.get("id") == args.test]
    if args.limit:
        pending = pending[: args.limit]

    cache = _load(CACHE)
    adoptions: list[dict] = []
    report: dict[str, Any] = {
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "script": "enrich_images_europeana_geo.py",
        "source": SOURCE,
        "args": vars(args),
        "api_key_set": bool(api_key),
        "public_endpoints_without_key": PUBLIC_ENDPOINTS_NO_KEY,
        "dual_signal": "name_match AND geo_match required",
        "attempts": len(pending),
        "staged_by_source": {SOURCE: 0},
        "adopted": [],
        "rejected": [],
        "skipped": [],
    }

    if not api_key:
        report["skipped"].append(
            "EUROPEANA_API_KEY unset — Search API unavailable; "
            "see public_endpoints_without_key in this report."
        )
        print(
            "WARN: EUROPEANA_API_KEY unset — no harvest (register at https://pro.europeana.eu)",
            file=sys.stderr,
        )
        report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        report["staged_count"] = 0
        report["staged_by_source"][SOURCE] = 0
        if not args.dry_run:
            save_staging(STAGING, [])
        _save(REPORT, report)
        print(f"Attempts: {len(pending):,}")
        print(f"Staged ({SOURCE}): 0")
        print(report["staged_by_source"][SOURCE])
        return 0

    n_staged = 0
    for n, isl in enumerate(pending, 1):
        items = fetch_europeana(isl, api_key, cache, delay_s)
        picked = pick_candidate(isl, items, report["rejected"])
        if picked:
            rec, verification = picked
            adoption = make_adoption(isl, rec, verification, source_label=SOURCE)
            adoptions.append(adoption)
            n_staged += 1
            report["adopted"].append({
                "id": isl["id"],
                "name": isl.get("name", ""),
                "license": rec.get("license"),
                "distance_km": verification.get("distance_km"),
                "url": rec.get("url"),
            })
            print(
                f"  ✓ {isl['id']:40s} {rec.get('license')} "
                f"{verification.get('distance_km')} km",
                flush=True,
            )
        if n % 50 == 0:
            print(f"  … {n}/{len(pending)} attempts; staged={n_staged}", flush=True)

    if not args.dry_run:
        save_staging(STAGING, adoptions)

    report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    report["staged_count"] = n_staged
    report["staged_by_source"][SOURCE] = n_staged
    _save(REPORT, report)

    print()
    print(f"Attempts: {len(pending):,}")
    print(f"Staged ({SOURCE}): {n_staged:,}")
    print(n_staged)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
