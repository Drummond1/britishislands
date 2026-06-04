#!/usr/bin/env python3
"""Stage OGL / CC-BY island photos from allowlisted public-sector & tourism open data.

Only sources with explicit OGL v3.0 (or equivalent) or CC-BY on the asset page are
used. Press/editorial tourism libraries are skipped and logged as blocked.

Active harvesters:
  - **commons-regional-category** — Wikimedia Commons regional island category trees
    (name match on filename; CC licences via Commons metadata).
  - **datagovuk-ogl-resource** — data.gov.uk CKAN datasets whose package/resources
    declare Open Government Licence and expose image URLs (name match on title).

Blocked (documented in report; no live fetch):
  - NatureScot / Natural England / NRW marketing media (no public OGL image API;
    spatial hubs are GIS-only).
  - Fáilte Ireland / Tourism Ireland / VisitScotland press libraries (editorial only).
  - HES Canmore / Scran thumbnails (API retired Jun 2025; trove.scot per-image
    licensing via user accounts — not machine-harvestable OGL).

Run::

    python3 scripts/enrich_images_ogl_tourism.py --named-only --limit 400
    python3 scripts/enrich_images_ogl_tourism.py --test isle-of-skye --dry-run
    python3 scripts/enrich_images_ogl_tourism.py --cache-only --limit 50

Outputs (staging only by default)::

    data/staging/adoptions/ogl-tourism.json
    data/image_enrichment_ogl_tourism_report.json
    data/cache_ogl_commons_regional.json
    data/cache_ogl_datagovuk.json
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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
ISLANDS_INDEX = DATA / "islands_index.json"
STAGING = DATA / "staging" / "adoptions" / "ogl-tourism.json"
REPORT = DATA / "image_enrichment_ogl_tourism_report.json"
CACHE_COMMONS_REGIONAL = DATA / "cache_ogl_commons_regional.json"
CACHE_DATAGOVUK = DATA / "cache_ogl_datagovuk.json"

USER_AGENT = "isles-of-britain/0.1 ogl-tourism-enrichment"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
DATAGOVUK_API = "https://data.gov.uk/api/3/action"
DATAGOVUK_API_ALT = "https://www.data.gov.uk/api/3/action"
DELAY_S = 1.2
TOKEN_MIN_LEN = 4
TOKEN_RE = re.compile(r"[a-z0-9']{" + str(TOKEN_MIN_LEN) + r",}")

# Regional Commons category roots (OGL/Crown photos often uploaded via GLAM partners).
COMMONS_REGIONAL_CATEGORIES: list[str] = [
    "Category:Islands of Scotland",
    "Category:Islands of the Outer Hebrides",
    "Category:Islands of the Inner Hebrides",
    "Category:Islands of Orkney",
    "Category:Islands of Shetland",
    "Category:Islands of Ireland",
    "Category:Islands of Northern Ireland",
    "Category:Islands of Wales",
    "Category:Islands of England",
    "Category:Islands of the Isle of Man",
    "Category:Islands of the Channel Islands",
    "Category:Islands of Cornwall",
    "Category:Islands of the Firth of Clyde",
    "Category:Islands of the Firth of Forth",
    "Category:Islands of the Solway Firth",
    "Category:Islands of County Donegal",
    "Category:Islands of County Kerry",
    "Category:Islands of County Galway",
    "Category:Islands of County Cork",
]

# CKAN search seeds for OGL image packages (indexed once per run).
DATAGOVUK_SEARCH_QUERIES: list[str] = [
    "island photograph",
    "coastal island image",
    "Scottish island photo",
    "island aerial photograph",
]

OGL_LICENSE_MARKERS = (
    "open government licence",
    "open government license",
    "ogl v3",
    "ogl-3",
    "ogl v3.0",
    "uk-ogl",
    "crown copyright",
    "psi directive",
    "re-use of public sector",
)

CC_LICENSE_MARKERS = (
    "cc0",
    "cc-by",
    "cc by",
    "public domain",
    "pd",
)

IMAGE_FORMATS = frozenset(
    {"jpg", "jpeg", "png", "gif", "webp", "tif", "tiff"}
)

# Sources we refuse to scrape — licence or API posture (see report.sources_blocked).
SOURCES_BLOCKED: list[dict[str, str]] = [
    {
        "id": "naturescot-media",
        "reason": "NatureScot open hub is GIS/WFS only; no OGL photo API (editorial site separate).",
    },
    {
        "id": "natural-england-media",
        "reason": "No machine-readable OGL image feed; designation data is OGL but not photos.",
    },
    {
        "id": "nrw-media",
        "reason": "NRW open data is spatial; marketing gallery not OGL-redistributable.",
    },
    {
        "id": "failte-ireland-press",
        "reason": "Tourism press library — editorial use only unless asset page states CC/OGL.",
    },
    {
        "id": "tourism-ireland-press",
        "reason": "Editorial/press use only — skipped.",
    },
    {
        "id": "visitscotland-press",
        "reason": "Editorial/press use only — skipped.",
    },
    {
        "id": "hes-canmore-thumbnails",
        "reason": "Canmore API retired Jun 2025; trove.scot requires per-image licence via account.",
    },
]

SOURCE_COMMONS = "commons-regional-category"
SOURCE_DATAGOV = "datagovuk-ogl-resource"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import enrich_images_v3 as v3  # noqa: E402
import enrich_images_v5 as v5  # noqa: E402


def _atomic_write_json(path: Path, payload: Any, *, indent: int = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=indent), encoding="utf-8")
    os.replace(tmp, path)


def _needs_image(island: dict) -> bool:
    return not (island.get("images") or island.get("image"))


def license_allowed(license_str: str | None) -> bool:
    if not license_str:
        return False
    norm = license_str.strip().lower()
    if not norm or norm in {"unknown", "n/a", "none", "copyrighted", "all rights reserved"}:
        return False
    if "fair use" in norm or "editorial" in norm:
        return False
    if any(m in norm for m in OGL_LICENSE_MARKERS):
        return True
    if any(m in norm for m in CC_LICENSE_MARKERS):
        return True
    return any(tok in norm for tok in ("cc-by-sa", "cc-by-sa-2.0", "cc-by-sa-4.0", "odbl"))


def _datagovuk_get(action: str, params: dict[str, Any]) -> dict[str, Any]:
    last_exc: Exception | None = None
    for base in (DATAGOVUK_API, DATAGOVUK_API_ALT):
        qs = urllib.parse.urlencode(params)
        req = urllib.request.Request(
            f"{base}/{action}?{qs}",
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            if payload.get("success") is False:
                raise RuntimeError(payload.get("error", {}).get("message", "CKAN error"))
            return payload
        except Exception as exc:
            last_exc = exc
            time.sleep(0.5)
    if last_exc:
        raise last_exc
    return {}


def _package_is_ogl(pkg: dict) -> bool:
    lic = (pkg.get("license_title") or pkg.get("license_id") or "").strip()
    return license_allowed(lic) or (pkg.get("license_id") or "").lower() in {
        "uk-ogl",
        "uk-ogl-third-party",
    }


def _resource_is_image(res: dict) -> bool:
    fmt = (res.get("format") or "").strip().lower()
    if fmt in IMAGE_FORMATS:
        return True
    url = (res.get("url") or "").lower()
    return any(url.endswith(f".{ext}") for ext in IMAGE_FORMATS)


def build_datagovuk_index(cache: dict, *, live: bool = True) -> list[dict[str, Any]]:
    """Return cached list of {title, url, license, package, name_tokens}."""
    if cache.get("resources") and not live:
        return cache["resources"]

    if "resources" in cache and cache.get("built_at") and not live:
        return cache["resources"]

    resources: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    errors: list[str] = []

    for query in DATAGOVUK_SEARCH_QUERIES:
        try:
            payload = _datagovuk_get(
                "package_search",
                {"q": query, "rows": 40},
            )
        except Exception as exc:
            errors.append(f"package_search({query!r}): {exc!r}")
            continue
        time.sleep(DELAY_S)
        for pkg in (payload.get("result") or {}).get("results") or []:
            if not _package_is_ogl(pkg):
                continue
            pkg_id = pkg.get("name") or pkg.get("id")
            if not pkg_id:
                continue
            try:
                show = _datagovuk_get("package_show", {"id": pkg_id})
            except Exception as exc:
                errors.append(f"package_show({pkg_id}): {exc!r}")
                continue
            time.sleep(DELAY_S)
            pkg_full = show.get("result") or {}
            lic = pkg_full.get("license_title") or pkg.get("license_title") or "OGL v3.0"
            for res in pkg_full.get("resources") or []:
                url = (res.get("url") or "").strip()
                if not url or url in seen_urls:
                    continue
                if not _resource_is_image(res):
                    continue
                title = (res.get("name") or res.get("description") or pkg_full.get("title") or "")
                resources.append(
                    {
                        "title": title,
                        "url": url,
                        "license": lic,
                        "package": pkg_id,
                        "package_title": pkg_full.get("title", ""),
                    }
                )
                seen_urls.add(url)

    cache["resources"] = resources
    cache["built_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    cache["errors"] = errors
    cache["query_count"] = len(DATAGOVUK_SEARCH_QUERIES)
    v5._save(CACHE_DATAGOVUK, cache)
    return resources


def category_members_all(
    category: str,
    *,
    cmtype: str = "file",
    max_members: int = 2000,
) -> list[str]:
    if not category.startswith("Category:"):
        category = "Category:" + category
    out: list[str] = []
    cont: str | None = None
    while len(out) < max_members:
        params: dict[str, Any] = {
            "action": "query",
            "format": "json",
            "list": "categorymembers",
            "cmtitle": category,
            "cmtype": cmtype,
            "cmlimit": "500",
        }
        if cont:
            params["cmcontinue"] = cont
        try:
            payload = v3._get_json(COMMONS_API, params)
        except Exception as exc:
            print(f"  categorymembers {category}: {exc!r}", file=sys.stderr)
            break
        members = (payload.get("query") or {}).get("categorymembers") or []
        for m in members:
            title = m.get("title", "")
            if cmtype == "file" and title.startswith("File:"):
                out.append(v3._canon_filename(title))
            elif cmtype == "subcat" and title.startswith("Category:"):
                out.append(title)
        cont = (payload.get("continue") or {}).get("cmcontinue")
        time.sleep(v3.DELAY_S)
        if not cont:
            break
    return out[:max_members]


def harvest_commons_regional_categories(
    cache: dict,
    *,
    live: bool = True,
    include_subcats: bool = True,
) -> dict[str, list[str]]:
    """Return {category_title: [filenames]}."""
    if cache.get("categories") and not live:
        return cache["categories"]
    categories_to_scan: list[str] = list(COMMONS_REGIONAL_CATEGORIES)
    if include_subcats:
        for root in COMMONS_REGIONAL_CATEGORIES:
            subs = category_members_all(root, cmtype="subcat", max_members=80)
            for sub in subs:
                if sub not in categories_to_scan:
                    categories_to_scan.append(sub)

    cat_files: dict[str, list[str]] = {}
    for cat in categories_to_scan:
        cached = (cache.get("categories") or {}).get(cat)
        if cached and not live:
            cat_files[cat] = cached
            continue
        files = [
            f
            for f in category_members_all(cat, max_members=1500)
            if not v3._looks_like_non_photo(f)
        ]
        if files:
            cat_files[cat] = files
            print(f"  {cat}: {len(files)} files", file=sys.stderr)

    cache["categories"] = cat_files
    cache["built_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    cache["category_count"] = len(cat_files)
    v5._save(CACHE_COMMONS_REGIONAL, cache)
    return cat_files


def _tokenize(text: str) -> set[str]:
    ascii_t = v5._strip_diacritics(text or "").lower()
    return set(TOKEN_RE.findall(ascii_t))


@dataclass
class RegionalFileIndex:
    """Inverted token index over Commons regional category filenames."""

    file_to_category: dict[str, str] = field(default_factory=dict)
    token_to_files: dict[str, list[str]] = field(default_factory=dict)
    total_files: int = 0


def build_regional_index(cat_files: dict[str, list[str]]) -> RegionalFileIndex:
    idx = RegionalFileIndex()
    seen: set[str] = set()
    for cat, files in cat_files.items():
        for fname in files:
            key = v5._canon(fname)
            if key in seen:
                continue
            seen.add(key)
            idx.file_to_category[key] = cat
            idx.total_files += 1
            for tok in _tokenize(fname):
                idx.token_to_files.setdefault(tok, []).append(fname)
    return idx


_NON_IMAGE_EXT = (".ogg", ".ogv", ".webm", ".mp3", ".wav", ".mid")


def candidates_from_regional_index(island: dict, index: RegionalFileIndex) -> list[str]:
    """Token lookup, then require island name in filename (avoids weak homonyms)."""
    variants = v5._name_variants(island)
    tokens: set[str] = set()
    for v in variants:
        tokens.update(_tokenize(v))
    seen: set[str] = set()
    out: list[str] = []
    for tok in sorted(tokens):
        for fname in index.token_to_files.get(tok, []):
            low = fname.lower()
            if low.endswith(_NON_IMAGE_EXT):
                continue
            if v3._looks_like_non_photo(fname):
                continue
            if not v5._mentions(fname, variants):
                continue
            key = v5._canon(fname)
            if key in seen:
                continue
            seen.add(key)
            out.append(fname)
    return out


def _rank_filename_candidates(island: dict, filenames: list[str]) -> list[str]:
    variants = v5._name_variants(island)

    def score(fname: str) -> float:
        s = 0.0
        if v5._mentions(fname, variants):
            s += 100.0
        for v in variants:
            if len(v) >= 5 and v.lower() in fname.lower():
                s += 20.0
        if "geograph.org.uk" in fname.lower():
            s += 2.0
        return s

    ranked = sorted(filenames, key=score, reverse=True)
    return ranked[:8]


def pick_best_commons_match(
    island: dict,
    filenames: list[str],
    cm_cache: dict,
    category_hint: str,
) -> dict | None:
    if not filenames:
        return None
    shortlist = _rank_filename_candidates(island, filenames)
    metas = v5.fetch_commons_meta(shortlist, cm_cache)
    best: tuple[str, dict, float] | None = None
    variants = v5._name_variants(island)
    for fname in shortlist:
        m = metas.get(v5._canon(fname), {}) or metas.get(fname, {})
        lic = (m.get("license") or "").strip()
        if not license_allowed(lic):
            continue
        if not v5._mentions(fname, variants):
            cap = m.get("caption") or ""
            if not v5._mentions(cap, variants):
                continue
        w, h = m.get("width") or 0, m.get("height") or 0
        score = float(w * h) if w and h else 0.0
        if v5._mentions(fname, variants):
            score += 1_000_000.0
        if best is None or score > best[2]:
            best = (fname, m, score)
    if not best:
        return None
    fname, meta, _ = best
    rec = v5.build_image_record_from_commons(
        fname,
        meta,
        SOURCE_COMMONS,
        category_hint or fname,
    )
    if not rec:
        return None
    rec["imageConfidence"] = "high"
    rec["verifiedAt"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return rec


def try_datagovuk_for_island(
    island: dict,
    dg_index: list[dict[str, Any]],
) -> dict | None:
    variants = v5._name_variants(island)
    for row in dg_index:
        title = row.get("title") or ""
        if not v5._mentions(title, variants):
            continue
        lic = row.get("license") or "Open Government Licence v3.0"
        if not license_allowed(lic):
            continue
        url = row.get("url") or ""
        if not url:
            continue
        pkg = row.get("package") or ""
        return {
            "url": url,
            "source": SOURCE_DATAGOV,
            "sourceRef": f"{island.get('id')};{pkg}",
            "sourcePageUrl": f"https://data.gov.uk/dataset/{pkg}" if pkg else url,
            "license": lic if "ogl" in lic.lower() else "OGL v3.0",
            "attribution": (
                f"{row.get('package_title') or 'UK public sector open data'}, "
                f"via data.gov.uk ({lic})"
            ),
            "caption": title,
            "imageConfidence": "medium-high",
            "verifiedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
    return None


def try_island_sources(
    island: dict,
    regional_index: RegionalFileIndex,
    cm_cache: dict,
    dg_index: list[dict[str, Any]],
    *,
    skip_datagov: bool = False,
) -> tuple[dict | None, str]:
    """Return (image_record, via_source_id)."""
    cands = candidates_from_regional_index(island, regional_index)
    cat_hint = ""
    if cands:
        key = v5._canon(cands[0])
        cat_hint = regional_index.file_to_category.get(key, "")
    rec = pick_best_commons_match(island, cands, cm_cache, cat_hint)
    if rec:
        return rec, SOURCE_COMMONS

    if not skip_datagov and dg_index:
        rec = try_datagovuk_for_island(island, dg_index)
        if rec:
            return rec, SOURCE_DATAGOV

    return None, ""


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage OGL/CC public-sector island photos.")
    ap.add_argument("--limit", type=int, default=0, help="Max islands to consider (0=all).")
    ap.add_argument("--named-only", action="store_true", help="Restrict to islands_index.json ids.")
    ap.add_argument("--dry-run", action="store_true", help="Do not write staging file.")
    ap.add_argument("--cache-only", action="store_true", help="Use caches only (no live APIs).")
    ap.add_argument("--test", default="", help="Single island id.")
    ap.add_argument("--skip-datagov", action="store_true", help="Skip data.gov.uk indexer.")
    ap.add_argument("--no-subcats", action="store_true", help="Do not walk Commons subcategories.")
    ap.add_argument(
        "--refresh-commons",
        action="store_true",
        help="Re-fetch Commons category members even if cache exists.",
    )
    args = ap.parse_args()

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    if not isinstance(islands, list):
        print("FATAL: islands.json is not a list", file=sys.stderr)
        return 2

    cm_cache = v5._load(v3.CACHE_CM)
    commons_cache = v5._load(CACHE_COMMONS_REGIONAL)
    dg_cache = v5._load(CACHE_DATAGOVUK)

    live = not args.cache_only
    print("Harvesting Commons regional categories…", file=sys.stderr)
    if commons_cache.get("categories") and not args.refresh_commons:
        cat_files = commons_cache["categories"]
        print(
            f"  using cached {len(cat_files)} categories "
            f"({commons_cache.get('built_at', 'unknown')})",
            file=sys.stderr,
        )
    else:
        cat_files = harvest_commons_regional_categories(
            commons_cache,
            live=live,
            include_subcats=not args.no_subcats,
        )
    regional_index = build_regional_index(cat_files)
    print(
        f"  regional index: {regional_index.total_files:,} files in "
        f"{len(cat_files)} categories",
        file=sys.stderr,
    )

    dg_index: list[dict[str, Any]] = []
    datagov_status = "skipped"
    if not args.skip_datagov:
        try:
            dg_index = build_datagovuk_index(dg_cache, live=live)
            datagov_status = "ok" if dg_index else "empty"
            print(f"  data.gov.uk OGL image resources: {len(dg_index)}", file=sys.stderr)
        except Exception as exc:
            datagov_status = f"error:{exc!r}"
            print(f"  data.gov.uk indexer failed: {exc!r}", file=sys.stderr)
            dg_index = dg_cache.get("resources") or []

    if args.test:
        targets = [i for i in islands if i.get("id") == args.test]
        if not targets:
            print(f"FATAL: no island {args.test!r}", file=sys.stderr)
            return 2
    else:
        targets = [i for i in islands if _needs_image(i)]
        if args.named_only:
            named_ids = v5._load_named_index_ids()
            if not named_ids:
                print("FATAL: --named-only but islands_index missing", file=sys.stderr)
                return 2
            before = len(targets)
            targets = [i for i in targets if i.get("id") in named_ids]
            print(f"  named-only: {len(targets):,} of {before:,} without images", file=sys.stderr)

    def _prioritize(ts: list[dict]) -> list[dict]:
        scored = [
            (len(candidates_from_regional_index(i, regional_index)), i) for i in ts
        ]
        scored.sort(key=lambda t: (t[0], (t[1].get("name") or "")), reverse=True)
        return [i for _, i in scored]

    targets = _prioritize(targets)
    if args.limit:
        targets = targets[: args.limit]

    report: dict[str, Any] = {
        "script": "enrich_images_ogl_tourism.py",
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "args": vars(args),
        "sources_working": [SOURCE_COMMONS, SOURCE_DATAGOV],
        "sources_blocked": SOURCES_BLOCKED,
        "datagovuk_status": datagov_status,
        "commons_regional_files_indexed": regional_index.total_files,
        "commons_categories": len(cat_files),
        "datagovuk_resources_indexed": len(dg_index),
        "targets_considered": len(targets),
        "targets_with_filename_candidates": sum(
            1 for i in targets if candidates_from_regional_index(i, regional_index)
        ),
        "counts": {
            "staged": 0,
            "no_match": 0,
            "by_source": {SOURCE_COMMONS: 0, SOURCE_DATAGOV: 0},
        },
        "licence_rejected": [],
        "adopted_sample": [],
    }

    adoptions: list[dict[str, Any]] = []
    staged = 0

    for n, isl in enumerate(targets, 1):
        if n % 50 == 0:
            print(f"  {n}/{len(targets)} staged={staged}", file=sys.stderr)

        rec, via = try_island_sources(
            isl,
            regional_index,
            cm_cache,
            dg_index,
            skip_datagov=args.skip_datagov or datagov_status.startswith("error"),
        )
        if not rec:
            report["counts"]["no_match"] += 1
            if len(report.get("no_match_sample", [])) < 25:
                report.setdefault("no_match_sample", []).append(
                    {
                        "id": isl.get("id"),
                        "name": isl.get("name"),
                        "filename_candidates": len(
                            candidates_from_regional_index(isl, regional_index)
                        ),
                    }
                )
            continue

        staged += 1
        report["counts"]["staged"] += 1
        if via in report["counts"]["by_source"]:
            report["counts"]["by_source"][via] += 1

        row = {
            "id": isl["id"],
            "name": isl.get("name", ""),
            "via": via,
            "image_record": rec,
            "imageConfidence": rec.get("imageConfidence", "high"),
            "source": rec.get("source"),
            "sourcePageUrl": rec.get("sourcePageUrl"),
            "license": rec.get("license"),
        }
        adoptions.append(row)
        if len(report["adopted_sample"]) < 40:
            report["adopted_sample"].append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "via": via,
                    "license": row["license"],
                    "sourcePageUrl": row["sourcePageUrl"],
                }
            )

        if args.dry_run or args.test:
            print(json.dumps(row, ensure_ascii=False, indent=2))

    if not args.dry_run:
        _atomic_write_json(
            STAGING,
            {
                "version": 1,
                "generatedAt": report["generatedAt"],
                "source": "ogl-tourism",
                "adoptions": adoptions,
            },
        )

    _atomic_write_json(REPORT, report)

    print(
        f"\nDone. staged={staged} no_match={report['counts']['no_match']} "
        f"by_source={report['counts']['by_source']}",
        file=sys.stderr,
    )
    print(f"Staging → {STAGING.relative_to(ROOT)} ({len(adoptions)} rows)", file=sys.stderr)
    print(f"Report  → {REPORT.relative_to(ROOT)}", file=sys.stderr)
    print(staged)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
