#!/usr/bin/env python3
"""Match Commons regional island categories to atlas islands by name.

Walks nation-scoped Commons categories (e.g. ``Category:Islands of the Outer
Hebrides``, ``Category:River islands of England``), lists file members (and
optional one-level subcategories), and stages adoptions for photoless named
islands when a member filename mentions the island name.

No geosearch. Default: staging only → ``data/staging/adoptions/commons-deep.json``.

Run::

    python3 scripts/enrich_images_commons_regional.py --cache-only
    python3 scripts/enrich_images_commons_regional.py --nation Scotland --delay 2
    python3 scripts/enrich_images_commons_regional.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
STAGING = DATA / "staging" / "adoptions" / "commons-deep.json"
REPORT = DATA / "image_enrichment_commons_regional_report.json"
CACHE_CM = DATA / "cache_commons_categorymembers.json"
CACHE_COMMONS = DATA / "cache_commons.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import enrich_images_v3 as v3  # noqa: E402
from enrich_images_v5 import (  # noqa: E402
    DELAY_S,
    _canon,
    _load,
    _load_named_index_ids,
    _looks_like_non_photo,
    _mentions,
    _name_variants,
    _save,
    build_image_record_from_commons,
    fetch_commons_meta,
)

SOURCE = "commons-regional-category"

# Nation → root Commons categories (files + subcats at depth 1).
REGIONAL_CATEGORIES: dict[str, list[str]] = {
    "Scotland": [
        "Category:Islands of the Outer Hebrides",
        "Category:Islands of the Inner Hebrides",
        "Category:Islands of Orkney",
        "Category:Islands of Shetland",
        "Category:Islands of the Firth of Clyde",
        "Category:Islands of the Firth of Forth",
        "Category:Islands of Argyll and Bute",
        "Category:River islands of Scotland",
        "Category:Uninhabited islands of Scotland",
        "Category:Tidal islands of Scotland",
    ],
    "England": [
        "Category:River islands of England",
        "Category:Islands of England",
        "Category:Islands of the River Thames",
        "Category:Islands in England",
        "Category:Tidal islands of England",
    ],
    "Wales": [
        "Category:Islands of Wales",
        "Category:River islands of Wales",
        "Category:Tidal islands of Wales",
    ],
    "Northern Ireland": [
        "Category:Islands of Northern Ireland",
        "Category:River islands of Northern Ireland",
    ],
    "Ireland": [
        "Category:Islands of Ireland",
        "Category:River islands of Ireland",
        "Category:Islands of County Donegal",
        "Category:Islands of County Galway",
        "Category:Islands of County Kerry",
        "Category:Islands of County Cork",
    ],
    "Isle of Man": [
        "Category:Islands of the Isle of Man",
    ],
    "Crown Dependency": [
        "Category:Islands of Jersey",
        "Category:Islands of Guernsey",
    ],
}

_SUBCAT_SKIP_RE = re.compile(
    r"(?:maps?|chart|diagram|coat|flag|logo|people|visitors|aerial\s+views)",
    re.IGNORECASE,
)


def _normalize_category(title: str) -> str:
    t = (title or "").strip()
    if not t:
        return ""
    if not t.startswith("Category:"):
        return "Category:" + t
    return t


def category_members_paged(
    category: str,
    *,
    cmtype: str = "file",
    limit: int = 500,
    cache: dict[str, Any],
    cache_only: bool,
) -> list[str]:
    """Return member titles (File:… or Category:…) up to ``limit``."""
    category = _normalize_category(category)
    cache_key = f"{category}|{cmtype}|{limit}"
    if cache_key in cache:
        return list(cache[cache_key])
    # Legacy v3/v4 entries keyed by category title only (files).
    if cmtype == "file" and category in cache:
        legacy = cache[category]
        if isinstance(legacy, list):
            return [
                t if t.startswith("File:") else f"File:{t}"
                for t in legacy[:limit]
            ]

    if cache_only:
        return []

    out: list[str] = []
    cmcontinue: str | None = None
    while len(out) < limit:
        batch = min(50, limit - len(out))
        params: dict[str, Any] = {
            "action": "query",
            "format": "json",
            "list": "categorymembers",
            "cmtitle": category,
            "cmtype": cmtype,
            "cmlimit": str(batch),
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue
        try:
            payload = v3._get_json(v3.COMMONS_API, params)
        except Exception as exc:
            print(f"  categorymembers failed {category}: {exc!r}", file=sys.stderr)
            break
        members = (payload.get("query") or {}).get("categorymembers") or []
        for m in members:
            title = (m.get("title") or "").strip()
            if title:
                out.append(title)
        cont = payload.get("continue") or {}
        cmcontinue = cont.get("cmcontinue")
        if not cmcontinue or not members:
            break
        time.sleep(DELAY_S)

    cache[cache_key] = out
    _save(CACHE_CM, cache)
    return out


def _category_island_name(title: str) -> str:
    """Extract island-ish name from ``Category:Foo (bar)``."""
    if not title.startswith("Category:"):
        return ""
    name = title[len("Category:") :].strip()
    # Drop trailing disambiguation in parentheses when present.
    if "(" in name:
        name = name.split("(", 1)[0].strip()
    return name


def _build_nation_name_index(
    islands: list[dict],
    pending_ids: set[str],
) -> dict[str, dict[str, list[dict]]]:
    """nation → canonical lowered name → islands."""
    out: dict[str, dict[str, list[dict]]] = {}
    for isl in islands:
        if isl.get("id") not in pending_ids:
            continue
        nation = (isl.get("nation") or "").strip()
        if not nation:
            continue
        bucket = out.setdefault(nation, {})
        for v in _name_variants(isl):
            if len(v) < 3:
                continue
            key = v.strip().lower()
            bucket.setdefault(key, []).append(isl)
    return out


def _match_island_for_file(
    fname: str,
    nation_index: dict[str, list[dict]],
) -> dict | None:
    canon = _canon(fname)
    best: dict | None = None
    best_len = 0
    for key, group in nation_index.items():
        if len(key) < 4:
            continue
        if not (_mentions(canon, [key]) or _mentions(fname, [key])):
            continue
        if len(key) > best_len:
            best_len = len(key)
            best = group[0]
    return best


def _match_island_for_subcat(
    subcat: str,
    nation_index: dict[str, list[dict]],
) -> dict | None:
    name = _category_island_name(subcat)
    if len(name) < 3:
        return None
    key = name.lower()
    group = nation_index.get(key)
    if group:
        return group[0]
    # Fuzzy: longest variant contained in category title.
    low = subcat.lower()
    best: dict | None = None
    best_len = 0
    for vkey, group in nation_index.items():
        if len(vkey) < 4:
            continue
        if vkey in low and len(vkey) > best_len:
            best_len = len(vkey)
            best = group[0]
    return best


def _pick_best_file(
    files: list[str],
    island: dict,
    cache_commons: dict,
) -> str | None:
    variants = _name_variants(island)
    best = ""
    best_score = -1
    for fname in files:
        if _looks_like_non_photo(fname):
            continue
        if not (_mentions(fname, variants)):
            continue
        score = 0
        m = cache_commons.get(_canon(fname)) or {}
        lic = (m.get("license") or "").strip()
        if not lic or "fair use" in lic.lower():
            score -= 5
        w, h = m.get("width") or 0, m.get("height") or 0
        if w and h:
            score += min(5, int((w * h) / 500_000))
        if score > best_score:
            best_score = score
            best = fname
    return best or None


def _stamp_confidence(rec: dict, exact: bool) -> dict:
    out = dict(rec)
    out["imageConfidence"] = "high" if exact else "medium"
    out["verifiedAt"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return out


def _save_staging(adoptions: list[dict], report: dict[str, Any]) -> None:
    STAGING.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "generatedAt": report.get("generatedAt", ""),
        "source": SOURCE,
        "adoptions": adoptions,
        "report": report,
    }
    tmp = STAGING.with_suffix(STAGING.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, STAGING)


def _stage_from_cached_categories(
    cache_cm: dict[str, Any],
    nation_index_by_nation: dict[str, dict[str, list[dict]]],
    cache_commons: dict[str, Any],
    pending: list[dict],
    report: dict[str, Any],
    staged_ids: set[str],
    *,
    limit: int,
) -> list[dict]:
    """When ``--cache-only``, match islands to any cached per-island Commons category."""
    adoptions: list[dict] = []
    pending_by_id = {i["id"]: i for i in pending}

    for nation, nation_index in nation_index_by_nation.items():
        if not nation_index:
            continue
        for cache_key, members in cache_cm.items():
            if not cache_key.startswith("Category:"):
                continue
            if "|" in cache_key:
                continue
            if not isinstance(members, list) or not members:
                continue
            isl = _match_island_for_subcat(cache_key, nation_index)
            if not isl or isl.get("id") in staged_ids:
                continue
            files = [
                _canon(t[len("File:") :]) if str(t).startswith("File:") else _canon(str(t))
                for t in members
                if str(t).startswith("File:") or str(t).lower().endswith((".jpg", ".jpeg", ".png"))
            ]
            if not files:
                continue
            best = _pick_best_file(files, isl, cache_commons)
            if not best:
                continue
            m = cache_commons.get(_canon(best)) or {}
            rec = build_image_record_from_commons(best, m, SOURCE, cache_key)
            if not rec:
                continue
            exact = _mentions(best, _name_variants(isl))
            rec = _stamp_confidence(rec, exact)
            row = {
                "id": isl["id"],
                "name": isl.get("name", ""),
                "via": SOURCE,
                "category": cache_key,
                "image_record": rec,
                "imageConfidence": rec.get("imageConfidence"),
                "source": rec.get("source"),
                "sourcePageUrl": rec.get("sourcePageUrl"),
            }
            adoptions.append(row)
            staged_ids.add(isl["id"])
            report["counts"]["staged"] += 1
            report["counts"]["islands_matched"] += 1
            report["category_matches"].append({
                "id": isl["id"],
                "name": isl.get("name"),
                "category": cache_key,
                "file": best,
                "from": "cached-category-scan",
            })
            print(f"  ✓ {isl['id']:40s} {cache_key}", flush=True)
            if limit and len(adoptions) >= limit:
                return adoptions
    return adoptions


def main() -> int:
    p = argparse.ArgumentParser(description="Regional Commons category → island name match.")
    p.add_argument("--cache-only", action="store_true", help="Only use cached category members.")
    p.add_argument("--named-only", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--nation", default="", help="Limit to one nation key.")
    p.add_argument("--delay", type=float, default=None, help="Override v3 DELAY_S.")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=0, help="Max adoptions to stage (0 = all).")
    p.add_argument("--member-limit", type=int, default=500, help="Max members per category.")
    args = p.parse_args()

    if args.delay is not None:
        v3.DELAY_S = max(0.0, float(args.delay))
        print(f"  API delay: {v3.DELAY_S}s", flush=True)

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    pending = [i for i in islands if not (i.get("images") or [])]
    if args.named_only:
        named_ids = _load_named_index_ids()
        if named_ids:
            pending = [i for i in pending if i.get("id") in named_ids]
    pending_ids = {i.get("id") for i in pending}
    nation_index_by_nation = _build_nation_name_index(islands, pending_ids)

    cache_cm = _load(CACHE_CM)
    cache_commons = _load(CACHE_COMMONS)

    report: dict[str, Any] = {
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source": SOURCE,
        "args": vars(args),
        "category_matches": [],
        "counts": {
            "categories_walked": 0,
            "files_seen": 0,
            "subcats_seen": 0,
            "islands_matched": 0,
            "staged": 0,
        },
    }

    adoptions: list[dict] = []
    staged_ids: set[str] = set()

    if args.cache_only:
        print("Cache-only: scanning cached per-island categories…", flush=True)
        adoptions = _stage_from_cached_categories(
            cache_cm,
            nation_index_by_nation,
            cache_commons,
            pending,
            report,
            staged_ids,
            limit=args.limit,
        )
        if not args.dry_run:
            _save_staging(adoptions, report)
            _save(REPORT, report)
        print()
        print(f"Regional matches:  {report['counts']['islands_matched']:,}")
        print(f"Staged:            {report['counts']['staged']:,}")
        if not args.dry_run:
            print(f"Staging → {STAGING.relative_to(ROOT)}")
        return 0

    nations = sorted(REGIONAL_CATEGORIES.keys())
    if args.nation:
        if args.nation not in REGIONAL_CATEGORIES:
            print(f"Unknown nation: {args.nation}", file=sys.stderr)
            return 2
        nations = [args.nation]

    for nation in nations:
        cats = REGIONAL_CATEGORIES.get(nation, [])
        nation_index = nation_index_by_nation.get(nation, {})
        if not nation_index:
            continue
        print(f"\n{nation}: {len(cats)} categories, {len(nation_index)} name keys", flush=True)

        for cat in cats:
            report["counts"]["categories_walked"] += 1
            files_raw = category_members_paged(
                cat,
                cmtype="file",
                limit=args.member_limit,
                cache=cache_cm,
                cache_only=args.cache_only,
            )
            file_names = [
                _canon(t[len("File:") :]) if t.startswith("File:") else _canon(t)
                for t in files_raw
                if t.startswith("File:")
            ]
            report["counts"]["files_seen"] += len(file_names)

            subcats = category_members_paged(
                cat,
                cmtype="subcat",
                limit=min(200, args.member_limit),
                cache=cache_cm,
                cache_only=args.cache_only,
            )
            report["counts"]["subcats_seen"] += len(subcats)

            # Subcategory → island: walk file members of matching subcats.
            for sub in subcats:
                if not sub.startswith("Category:"):
                    continue
                if _SUBCAT_SKIP_RE.search(sub):
                    continue
                isl = _match_island_for_subcat(sub, nation_index)
                if not isl or isl.get("id") in staged_ids:
                    continue
                sub_files_raw = category_members_paged(
                    sub,
                    cmtype="file",
                    limit=50,
                    cache=cache_cm,
                    cache_only=args.cache_only,
                )
                sub_files = [
                    _canon(t[len("File:") :])
                    for t in sub_files_raw
                    if t.startswith("File:")
                ]
                if not sub_files:
                    continue
                if not args.cache_only:
                    fetch_commons_meta(sub_files[:10], cache_commons)
                best = _pick_best_file(sub_files, isl, cache_commons)
                if not best:
                    continue
                m = cache_commons.get(_canon(best)) or {}
                rec = build_image_record_from_commons(
                    best, m, SOURCE, sub
                )
                if not rec:
                    continue
                exact = _mentions(best, _name_variants(isl))
                rec = _stamp_confidence(rec, exact)
                row = {
                    "id": isl["id"],
                    "name": isl.get("name", ""),
                    "via": SOURCE,
                    "category": sub,
                    "parentCategory": cat,
                    "image_record": rec,
                    "imageConfidence": rec.get("imageConfidence"),
                    "source": rec.get("source"),
                    "sourcePageUrl": rec.get("sourcePageUrl"),
                }
                adoptions.append(row)
                staged_ids.add(isl["id"])
                report["counts"]["staged"] += 1
                report["counts"]["islands_matched"] += 1
                report["category_matches"].append({
                    "id": isl["id"],
                    "name": isl.get("name"),
                    "category": sub,
                    "parent": cat,
                    "file": best,
                })
                print(f"  ✓ {isl['id']:40s} {sub}", flush=True)
                if args.limit and len(adoptions) >= args.limit:
                    break

            if args.limit and len(adoptions) >= args.limit:
                break

            # Direct file members in regional category.
            island_to_files: dict[str, list[str]] = {}
            for fname in file_names:
                isl = _match_island_for_file(fname, nation_index)
                if not isl:
                    continue
                island_to_files.setdefault(isl["id"], []).append(fname)

            need_meta: list[str] = []
            for fnames in island_to_files.values():
                need_meta.extend(fnames[:5])
            if need_meta and not args.cache_only:
                fetch_commons_meta(list(dict.fromkeys(need_meta))[:40], cache_commons)

            for iid, fnames in island_to_files.items():
                if iid in staged_ids:
                    continue
                isl = next(i for i in pending if i.get("id") == iid)
                best = _pick_best_file(fnames, isl, cache_commons)
                if not best:
                    continue
                m = cache_commons.get(_canon(best)) or {}
                rec = build_image_record_from_commons(best, m, SOURCE, cat)
                if not rec:
                    continue
                exact = _mentions(best, _name_variants(isl))
                rec = _stamp_confidence(rec, exact)
                row = {
                    "id": iid,
                    "name": isl.get("name", ""),
                    "via": SOURCE,
                    "category": cat,
                    "image_record": rec,
                    "imageConfidence": rec.get("imageConfidence"),
                    "source": rec.get("source"),
                    "sourcePageUrl": rec.get("sourcePageUrl"),
                }
                adoptions.append(row)
                staged_ids.add(iid)
                report["counts"]["staged"] += 1
                report["counts"]["islands_matched"] += 1
                report["category_matches"].append({
                    "id": iid,
                    "name": isl.get("name"),
                    "category": cat,
                    "file": best,
                })
                print(f"  ✓ {iid:40s} {cat}", flush=True)
                if args.limit and len(adoptions) >= args.limit:
                    break

            if args.limit and len(adoptions) >= args.limit:
                break
        if args.limit and len(adoptions) >= args.limit:
            break

    if not args.dry_run:
        if adoptions or not STAGING.exists():
            _save_staging(adoptions, report)
        else:
            print("No new matches; keeping existing staging file.", flush=True)
        _save(REPORT, report)

    print()
    print(f"Categories walked: {report['counts']['categories_walked']}")
    print(f"Files seen:        {report['counts']['files_seen']:,}")
    print(f"Regional matches:  {report['counts']['islands_matched']:,}")
    print(f"Staged:            {report['counts']['staged']:,}")
    if not args.dry_run:
        print(f"Staging → {STAGING.relative_to(ROOT)}")
        print(f"Report  → {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
