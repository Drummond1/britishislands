#!/usr/bin/env python3
"""Lead-photo enrichment via the Openverse API (CC0 / PDM / BY / BY-SA only).

Targets named atlas islands (``islands_index.json`` ids) that still lack
``images[]``. Reuses name-matching helpers from ``enrich_images_v5``.

Run::

    python3 scripts/enrich_images_openverse.py --limit 100 --named-only
    python3 scripts/enrich_images_openverse.py --dry-run --limit 20
    python3 scripts/enrich_images_openverse.py --no-named-only --limit 50

Outputs (default: staging only — does not mutate islands.json)::

    data/staging/adoptions/openverse.json          [{id, image_record, confidence, reason}]
    data/cache_openverse.json
    data/image_enrichment_openverse_report.json

Optional ``--apply`` writes adopted images into ``data/islands.json`` (with backup).
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
BACKUP = DATA / "islands.json.before-openverse"
STAGING = DATA / "staging" / "adoptions" / "openverse.json"
CACHE = DATA / "cache_openverse.json"
REPORT = DATA / "image_enrichment_openverse_report.json"
MAX_LIMIT = 800
CONFIDENCE = "medium"

OPENVERSE_API = "https://api.openverse.org/v1/images/"
USER_AGENT = "isles-of-britain/0.1 openverse-enrichment"
DEFAULT_DELAY_S = 1.5
ALLOWED_LICENSES = frozenset({"cc0", "pdm", "by", "by-sa"})
LICENSE_PARAM = "cc0,pdm,by,by-sa"
GEO_MAX_KM = 15.0
GEO_MAX_KM_GENERIC = 5.0
PAGE_SIZE = 20

sys.path.insert(0, str(Path(__file__).resolve().parent))
from enrich_images_v5 import (  # noqa: E402
    DELAY_S,
    _atomic_write_islands,
    _get_json,
    _haversine_km,
    _load,
    _load_named_index_ids,
    _mentions,
    _name_variants,
    _save,
)

# Generic English island names need a tighter geo gate (homonym risk).
_GENERIC_NAME_RE = re.compile(
    r"^(?:the\s+)?"
    r"(?:green|black|white|red|blue|brown|grey|gray|great|little|big|small|"
    r"north|south|east|west|middle|inner|outer|high|low|long|short|round|flat|"
    r"rock|stone|sand|shell|reef|holm|skerry|inch|eilean|ynys|inis|holy|saint|"
    r"st\.?)\s+"
    r"(?:island|isle|islets?|islet)$",
    re.IGNORECASE,
)
_NON_PHOTO_TITLE_RE = re.compile(
    r"(?:^|[_ \-\(\[])"
    r"(?:flag|coat[_ \-]of[_ \-]arms|logo|map|diagram|chart|icon|badge|"
    r"illustration|drawing|cartoon|clipart|vector|svg|portrait|selfie|"
    r"cosplay|wedding|party|concert|festival)"
    r"(?:$|[_ \-\)\]])",
    re.IGNORECASE,
)


def _is_generic_island_name(name: str) -> bool:
    raw = (name or "").strip()
    if not raw:
        return True
    low = raw.lower()
    if _GENERIC_NAME_RE.match(low):
        return True
    tokens = re.sub(r"[^\w\s'-]", " ", low).split()
    if len(tokens) == 2 and tokens[-1] in ("island", "isle", "islets", "islet"):
        return True
    if len(low) <= 8 and " " not in low:
        return True
    return False


def _island_lon(island: dict) -> float | None:
    lng = island.get("lng")
    if lng is None:
        lng = island.get("lon")
    if isinstance(lng, (int, float)):
        return float(lng)
    return None


def _search_query(island: dict) -> str:
    name = (island.get("name") or "").strip()
    nation = (island.get("nation") or "").strip()
    if nation:
        return f"{name} {nation}"
    return name


def _format_license(code: str, version: str | None) -> str:
    code = (code or "").strip().lower()
    ver = (version or "").strip()
    if code == "cc0":
        return "CC0-1.0"
    if code == "pdm":
        return "PDM"
    if code == "by":
        return f"CC-BY-{ver}" if ver else "CC-BY-2.0"
    if code == "by-sa":
        return f"CC-BY-SA-{ver}" if ver else "CC-BY-SA-2.0"
    return ""


def _result_description(result: dict) -> str:
    parts: list[str] = []
    attr = (result.get("attribution") or "").strip()
    if attr:
        parts.append(attr)
    for tag in result.get("tags") or []:
        if isinstance(tag, dict):
            nm = (tag.get("name") or "").strip()
            if nm:
                parts.append(nm)
    return " ".join(parts)


def _looks_like_non_photo_result(result: dict) -> bool:
    title = (result.get("title") or "").strip()
    if not title:
        return True
    if _NON_PHOTO_TITLE_RE.search(title):
        return True
    url = (result.get("url") or "").lower()
    if url.endswith((".svg", ".gif", ".pdf")):
        return True
    return False


def _build_attribution(result: dict, license_label: str) -> str:
    upstream = (result.get("attribution") or "").strip()
    if upstream:
        return upstream
    creator = (result.get("creator") or "").strip() or "Unknown"
    provider = (result.get("provider") or result.get("source") or "Openverse").strip()
    return f"\"{(result.get('title') or '').strip()}\" by {creator} via {provider} ({license_label})"


def build_image_record_from_openverse(result: dict) -> dict | None:
    lic_code = (result.get("license") or "").strip().lower()
    if lic_code not in ALLOWED_LICENSES:
        return None
    license_label = _format_license(lic_code, result.get("license_version"))
    if not license_label:
        return None
    url = (result.get("url") or "").strip()
    if not url:
        return None
    page = (
        (result.get("foreign_landing_url") or "").strip()
        or (result.get("detail_url") or "").strip()
    )
    if not page:
        return None
    ref = str(result.get("id") or "").strip() or page
    return {
        "url": url,
        "source": "openverse",
        "sourceRef": ref,
        "sourcePageUrl": page,
        "license": license_label,
        "attribution": _build_attribution(result, license_label),
        "caption": (result.get("title") or "").strip(),
    }


def _save_cache(cache: dict) -> None:
    """Atomic cache write with one retry (avoids concurrent tmp races)."""
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(cache, ensure_ascii=False, separators=(",", ":"))
    for attempt in range(2):
        tmp = CACHE.with_suffix(CACHE.suffix + ".tmp")
        try:
            tmp.write_text(payload, encoding="utf-8")
            os.replace(tmp, CACHE)
            return
        except OSError as exc:
            if attempt:
                print(f"WARN: cache save failed: {exc!r}", file=sys.stderr)
                return
            time.sleep(0.05)


def fetch_openverse_search(
    island: dict,
    cache: dict,
    delay_s: float,
) -> list[dict]:
    key = island.get("id") or _search_query(island)
    if key in cache:
        cached = cache[key]
        if isinstance(cached, dict) and isinstance(cached.get("results"), list):
            return cached["results"]
        if isinstance(cached, list):
            return cached

    q = _search_query(island)
    params: dict[str, Any] = {
        "q": q,
        "license": LICENSE_PARAM,
        "page_size": PAGE_SIZE,
        "page": 1,
    }
    lat = island.get("lat")
    lon = _island_lon(island)
    if isinstance(lat, (int, float)) and lon is not None:
        params["lat"] = lat
        params["lon"] = lon

    try:
        payload = _get_json(OPENVERSE_API, params)
    except Exception as exc:
        print(f"  openverse search failed for {key}: {exc!r}", file=sys.stderr)
        cache[key] = {"q": q, "params": params, "error": repr(exc), "results": []}
        _save_cache(cache)
        time.sleep(delay_s)
        return []

    results = payload.get("results") or []
    cache[key] = {
        "q": q,
        "params": {k: v for k, v in params.items() if k != "page"},
        "fetched": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "result_count": payload.get("result_count"),
        "results": results,
    }
    _save_cache(cache)
    time.sleep(delay_s)
    return results


def _adoption_reason(island: dict, rec: dict, score: float) -> str:
    name = (island.get("name") or "").strip()
    generic = _is_generic_island_name(name)
    max_km = GEO_MAX_KM_GENERIC if generic else GEO_MAX_KM
    return (
        f"name match in title/description; geo {score:.1f} km "
        f"(max {max_km:.0f} km)"
        + ("; generic name" if generic else "")
    )


def pick_openverse_candidate(
    island: dict,
    results: list[dict],
    rejected: list[dict],
) -> tuple[dict, float] | None:
    variants = _name_variants(island)
    if not variants:
        rejected.append({
            "id": island.get("id"),
            "reason": "no name variants >= 5 chars",
        })
        return None

    generic = _is_generic_island_name(island.get("name") or "")
    max_km = GEO_MAX_KM_GENERIC if generic else GEO_MAX_KM
    isl_lat = island.get("lat")
    isl_lon = _island_lon(island)
    island_has_geo = (
        isinstance(isl_lat, (int, float)) and isl_lon is not None
    )

    best: tuple[float, dict] | None = None

    for result in results:
        if _looks_like_non_photo_result(result):
            continue
        lic = (result.get("license") or "").strip().lower()
        if lic not in ALLOWED_LICENSES:
            continue

        title = (result.get("title") or "").strip()
        desc = _result_description(result)
        if not (_mentions(title, variants) or _mentions(desc, variants)):
            rejected.append({
                "id": island.get("id"),
                "openverse_id": result.get("id"),
                "reason": "name-not-in-title-or-description",
                "title": title[:120],
            })
            continue

        rlat = result.get("lat")
        rlon = result.get("lon")
        result_has_geo = (
            isinstance(rlat, (int, float)) and isinstance(rlon, (int, float))
        )

        if island_has_geo and not result_has_geo:
            rejected.append({
                "id": island.get("id"),
                "openverse_id": result.get("id"),
                "reason": "result-missing-geo (island has lat/lon)",
                "title": title[:120],
            })
            continue

        if generic and not result_has_geo:
            rejected.append({
                "id": island.get("id"),
                "openverse_id": result.get("id"),
                "reason": "generic-name-requires-result-geo",
                "title": title[:120],
            })
            continue

        if result_has_geo and island_has_geo:
            try:
                dist = _haversine_km(
                    float(isl_lat), float(isl_lon), float(rlat), float(rlon),
                )
            except Exception:
                dist = 1e9
            if dist > max_km:
                rejected.append({
                    "id": island.get("id"),
                    "openverse_id": result.get("id"),
                    "reason": f"geo {dist:.1f} km > {max_km:.0f} km",
                    "title": title[:120],
                })
                continue
            score = dist
        elif not island_has_geo and not generic:
            # Name-only match only when the island has no centroid to verify.
            score = 50.0
        else:
            rejected.append({
                "id": island.get("id"),
                "openverse_id": result.get("id"),
                "reason": "no-island-geo-and-no-result-geo",
                "title": title[:120],
            })
            continue

        if best is None or score < best[0]:
            rec = build_image_record_from_openverse(result)
            if rec:
                best = (score, rec)

    if best is None:
        return None
    score, rec = best
    return rec, score


def _save_staging(adoptions: list[dict]) -> None:
    STAGING.parent.mkdir(parents=True, exist_ok=True)
    tmp = STAGING.with_suffix(STAGING.suffix + ".tmp")
    tmp.write_text(
        json.dumps(adoptions, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, STAGING)


def main() -> int:
    global DELAY_S
    p = argparse.ArgumentParser(
        description="Adopt lead photos from Openverse for named islands without images.",
    )
    p.add_argument(
        "--named-only",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Only islands in islands_index.json (default: true).",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Stop after considering N pending islands (0 = all).",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Write adopted images into islands.json (default: staging only).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Evaluate and report without writing staging or islands.json.",
    )
    p.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY_S,
        metavar="SECONDS",
        help=f"Seconds between Openverse API calls (default {DEFAULT_DELAY_S}).",
    )
    p.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip writing islands.json.before-openverse.",
    )
    p.add_argument(
        "--test",
        default="",
        help="Process only the island with this id.",
    )
    args = p.parse_args()
    if args.limit > MAX_LIMIT:
        print(
            f"FATAL: --limit {args.limit} exceeds max {MAX_LIMIT}",
            file=sys.stderr,
        )
        return 2
    delay_s = max(0.0, float(args.delay))
    DELAY_S = delay_s
    use_staging = not args.apply

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    if not isinstance(islands, list):
        print("FATAL: islands.json is not a list", file=sys.stderr)
        return 2

    if (
        args.apply
        and not args.dry_run
        and not args.no_backup
        and not BACKUP.exists()
    ):
        BACKUP.write_text(
            json.dumps(islands, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Backup → {BACKUP.relative_to(ROOT)}")

    cache = _load(CACHE)
    adoptions: list[dict] = []
    report: dict[str, Any] = {
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "args": {
            "named_only": args.named_only,
            "limit": args.limit,
            "dry_run": args.dry_run,
            "apply": args.apply,
            "staging": use_staging,
            "delay": delay_s,
        },
        "geo_max_km": GEO_MAX_KM,
        "geo_max_km_generic": GEO_MAX_KM_GENERIC,
        "allowed_licenses": sorted(ALLOWED_LICENSES),
        "input_total": len(islands),
        "pending_considered": 0,
        "adopted": [],
        "rejected": [],
    }

    pending = [i for i in islands if not (i.get("images") or [])]
    if args.named_only:
        named_ids = _load_named_index_ids()
        if named_ids:
            before = len(pending)
            pending = [i for i in pending if i.get("id") in named_ids]
            print(
                f"  named-only: {len(pending):,} of {before:,} without images",
                flush=True,
            )
    if args.test:
        pending = [i for i in islands if i.get("id") == args.test]
    if args.limit:
        pending = pending[: args.limit]
    report["pending_considered"] = len(pending)
    print(f"Pending (Openverse): {len(pending):,}", flush=True)

    pending_set = {i.get("id") for i in pending}
    n_attempted = 0
    n_adopted = 0
    n_checkpoint = 25
    last_checkpoint = 0
    started_at = time.time()

    for isl in islands:
        if isl.get("id") not in pending_set:
            continue
        n_attempted += 1
        results = fetch_openverse_search(isl, cache, delay_s)
        picked = pick_openverse_candidate(isl, results, report["rejected"])
        if picked:
            rec, score = picked
            reason = _adoption_reason(isl, rec, score)
            adoption = {
                "id": isl["id"],
                "image_record": rec,
                "confidence": CONFIDENCE,
                "reason": reason,
            }
            adoptions.append(adoption)
            if args.apply and not args.dry_run:
                isl.setdefault("images", []).append(rec)
            report["adopted"].append({
                "id": isl["id"],
                "name": isl.get("name", ""),
                "source": rec.get("source"),
                "license": rec.get("license"),
                "sourcePageUrl": rec.get("sourcePageUrl"),
                "sourceRef": rec.get("sourceRef"),
                "url": rec.get("url"),
                "caption": rec.get("caption"),
                "confidence": CONFIDENCE,
                "reason": reason,
            })
            n_adopted += 1
            print(
                f"  ✓ [{n_attempted:4d}/{len(pending):4d}] {isl['id']:45s} "
                f"→ {rec.get('license')} {rec.get('caption', '')[:50]}",
                flush=True,
            )
        else:
            report["rejected"].append({
                "id": isl["id"],
                "name": isl.get("name", ""),
                "reason": "no qualifying openverse result",
            })

        if not args.dry_run and n_attempted - last_checkpoint >= n_checkpoint:
            if use_staging:
                _save_staging(adoptions)
            elif args.apply:
                _atomic_write_islands(islands)
            _save(REPORT, report)
            last_checkpoint = n_attempted
            rate = n_attempted / max(1.0, time.time() - started_at)
            print(
                f"  …checkpoint {n_attempted}/{len(pending)}, "
                f"{n_adopted} adopted ({rate:.2f}/s)",
                flush=True,
            )

    if not args.dry_run:
        if use_staging:
            _save_staging(adoptions)
        elif args.apply:
            _atomic_write_islands(islands)

    api_errors = [
        v for v in cache.values()
        if isinstance(v, dict) and v.get("error")
    ]
    report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    report["attempted"] = n_attempted
    report["adopted_total"] = n_adopted
    report["staged_total"] = len(adoptions)
    report["dry_run"] = args.dry_run
    report["staging_path"] = str(STAGING.relative_to(ROOT)) if use_staging else None
    report["api_errors"] = len(api_errors)
    report["api_error_samples"] = [
        {"key": k, "error": v.get("error")}
        for k, v in list(cache.items())[:20]
        if isinstance(v, dict) and v.get("error")
    ][:5]
    _save(REPORT, report)

    print()
    print(f"Attempted: {n_attempted:,}")
    print(f"Adopted:   {n_adopted:,}")
    if use_staging and not args.dry_run:
        print(f"Staging  → {STAGING.relative_to(ROOT)} ({len(adoptions):,} records)")
    print(f"Report   → {REPORT.relative_to(ROOT)}")
    if api_errors:
        print(f"API errors in cache: {len(api_errors):,}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
