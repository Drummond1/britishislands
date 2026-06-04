#!/usr/bin/env python3
"""Wider Commons archipelago category sweep → staged photo adoptions.

Traverses broad nation/archipelago Commons category trees (e.g.
``Category:Islands of Scotland``, ``Category:Islands of the Outer Hebrides``,
``Category:Islands in the River Thames``), indexes **all** file members, and
matches photoless named islands using strict v5 word-boundary filename rules.

Dual-signal gate (at least one required):
  - **Island-specific category** — member of a per-island subcategory whose
    title mentions the island (not a broad archipelago root), or
  - **Filename + nation anchor** — ``_mentions`` on filename **and** nation /
    archipelago anchor in Commons caption or categories metadata.

Default: build index cache, then match. No writes to ``islands.json``.

Run::

    python3 scripts/enrich_images_commons_archipelago_sweep.py --build-index
    python3 scripts/enrich_images_commons_archipelago_sweep.py --match --cache-only
    python3 scripts/enrich_images_commons_archipelago_sweep.py --named-only --delay 2
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
STAGING = DATA / "staging" / "adoptions" / "commons-archipelago.json"
REPORT = DATA / "image_enrichment_commons_archipelago_report.json"
CACHE_INDEX = DATA / "cache_commons_archipelago_index.json"
CACHE_CM = DATA / "cache_commons_categorymembers.json"
CACHE_COMMONS = DATA / "cache_commons.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import enrich_images_v3 as v3  # noqa: E402
from enrich_images_v5 import (  # noqa: E402
    DELAY_S,
    _canon,
    _geo_anchors,
    _load,
    _load_named_index_ids,
    _looks_like_non_photo,
    _mentions,
    _name_variants,
    _save,
    _strip_diacritics,
    build_image_record_from_commons,
    fetch_commons_meta,
)

SOURCE = "commons-archipelago-category"

# Broad roots — wider than ``enrich_images_commons_regional.py`` nation lists.
# Sourced from PHOTO-DISCOVERY-IDEAS / OGL-tourism / regional harvesters.
ARCHIPELAGO_ROOTS: tuple[str, ...] = (
    "Category:Islands of Scotland",
    "Category:Islands of the Outer Hebrides",
    "Category:Islands of the Inner Hebrides",
    "Category:Islands of Orkney",
    "Category:Islands of Shetland",
    "Category:Islands of the Firth of Clyde",
    "Category:Islands of the Firth of Forth",
    "Category:Islands of Argyll and Bute",
    "Category:Islands of the Hebrides",
    "Category:Islands of the Clyde",
    "Category:Islands of the Forth",
    "Category:Islands of the Solway Firth",
    "Category:River islands of Scotland",
    "Category:Uninhabited islands of Scotland",
    "Category:Tidal islands of Scotland",
    "Category:Islands of England",
    "Category:Islands in England",
    "Category:Islands of the River Thames",
    "Category:River islands of England",
    "Category:Tidal islands of England",
    "Category:Islands of Cornwall",
    "Category:Islands of Wales",
    "Category:River islands of Wales",
    "Category:Tidal islands of Wales",
    "Category:Islands of Northern Ireland",
    "Category:River islands of Northern Ireland",
    "Category:Islands of Ireland",
    "Category:River islands of Ireland",
    "Category:Islands of County Donegal",
    "Category:Islands of County Galway",
    "Category:Islands of County Kerry",
    "Category:Islands of County Cork",
    "Category:Islands of the Isle of Man",
    "Category:Islands of the Channel Islands",
    "Category:Islands of Jersey",
    "Category:Islands of Guernsey",
)

BROAD_ROOTS: frozenset[str] = frozenset(ARCHIPELAGO_ROOTS)

_SUBCAT_SKIP_RE = re.compile(
    r"(?:maps?|chart|diagram|coat|flag|logo|people|visitors|aerial\s+views|"
    r"satellite|locator|svg|video|audio)",
    re.IGNORECASE,
)

_GROUPING_CAT_RE = re.compile(
    r"(?:islands?\s+of|river\s+islands|tidal\s+islands|uninhabited|archipelago|"
    r"county|firth|hebrides|orkney|shetland|channel|england|scotland|wales|ireland)",
    re.IGNORECASE,
)

_TOKEN_RE = re.compile(r"[a-z0-9']{4,}")


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
    limit: int = 0,
    cache_cm: dict[str, Any],
    cache_only: bool,
) -> list[str]:
    """Return member titles; ``limit=0`` means paginate until exhausted."""
    category = _normalize_category(category)
    cache_key = f"arch|{category}|{cmtype}|{limit or 'all'}"
    if cache_key in cache_cm:
        return list(cache_cm[cache_key])

    if cache_only:
        return []

    out: list[str] = []
    cmcontinue: str | None = None
    while limit <= 0 or len(out) < limit:
        batch = 500 if limit <= 0 else min(500, limit - len(out))
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

    cache_cm[cache_key] = out
    _save(CACHE_CM, cache_cm)
    return out


def _category_label(category: str) -> str:
    if category.startswith("Category:"):
        return category[len("Category:") :].split("(", 1)[0].strip()
    return category


def is_island_specific_category(category: str, island: dict) -> bool:
    """True when ``category`` names this island (not a broad archipelago root)."""
    cat = _normalize_category(category)
    if cat in BROAD_ROOTS:
        return False
    if _GROUPING_CAT_RE.search(_category_label(cat)) and not _mentions(
        _category_label(cat), _name_variants(island)
    ):
        return False
    variants = _name_variants(island)
    if not variants:
        return False
    label = _category_label(cat)
    return _mentions(label, variants) or _mentions(cat, variants)


def _nation_anchor_in_meta(meta: dict, island: dict) -> bool:
    hay = " ".join([
        meta.get("caption") or "",
        meta.get("categories") or "",
    ]).lower()
    if not hay.strip():
        return False
    for anchor in _geo_anchors(island):
        if anchor.lower() in hay:
            return True
    return False


def passes_dual_signal(
    island: dict,
    fname: str,
    categories: list[str],
    meta: dict,
) -> tuple[bool, str]:
    variants = _name_variants(island)
    for cat in categories:
        if is_island_specific_category(cat, island):
            return True, f"island-category:{cat}"
    if variants and _mentions(fname, variants) and _nation_anchor_in_meta(meta, island):
        return True, "filename+nation-anchor"
    return False, "no-dual-signal"


def _add_file_to_index(
    index: dict[str, Any],
    fname: str,
    category: str,
) -> None:
    key = _canon(fname)
    if not key or _looks_like_non_photo(key):
        return
    files = index.setdefault("files", {})
    entry = files.setdefault(key, {"categories": []})
    cats: list[str] = entry["categories"]
    cat = _normalize_category(category)
    if cat and cat not in cats:
        cats.append(cat)
    by_cat = index.setdefault("by_category", {})
    by_cat.setdefault(cat, []).append(key)


def build_archipelago_index(
    *,
    cache_cm: dict[str, Any],
    cache_only: bool,
    member_limit: int,
    subcat_limit: int,
    include_subcats: bool,
) -> dict[str, Any]:
    """Walk roots (+ optional subcats) and index every file member."""
    index: dict[str, Any] = {
        "version": 1,
        "builtAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "roots": list(ARCHIPELAGO_ROOTS),
        "files": {},
        "by_category": {},
        "counts": {
            "roots_walked": 0,
            "subcats_walked": 0,
            "files_indexed": 0,
            "categories_with_files": 0,
        },
    }
    seen_cats: set[str] = set()

    for root in ARCHIPELAGO_ROOTS:
        root = _normalize_category(root)
        index["counts"]["roots_walked"] += 1
        print(f"  root {root}", flush=True)

        file_titles = category_members_paged(
            root,
            cmtype="file",
            limit=member_limit,
            cache_cm=cache_cm,
            cache_only=cache_only,
        )
        for t in file_titles:
            if t.startswith("File:"):
                _add_file_to_index(index, t[len("File:") :], root)

        subcats: list[str] = []
        if include_subcats:
            subcats = category_members_paged(
                root,
                cmtype="subcat",
                limit=subcat_limit,
                cache_cm=cache_cm,
                cache_only=cache_only,
            )
            subcats = [s for s in subcats if s.startswith("Category:")]

        for sub in subcats:
            if _SUBCAT_SKIP_RE.search(sub):
                continue
            if sub in seen_cats:
                continue
            seen_cats.add(sub)
            index["counts"]["subcats_walked"] += 1
            sub_files = category_members_paged(
                sub,
                cmtype="file",
                limit=member_limit,
                cache_cm=cache_cm,
                cache_only=cache_only,
            )
            for t in sub_files:
                if t.startswith("File:"):
                    _add_file_to_index(index, t[len("File:") :], sub)

    index["counts"]["files_indexed"] = len(index.get("files") or {})
    index["counts"]["categories_with_files"] = len(index.get("by_category") or {})
    index["tokenIndex"] = _token_index_for_files(index.get("files") or {})
    return index


def _build_name_index(
    islands: list[dict],
    pending_ids: set[str],
) -> dict[str, list[dict]]:
    """Lowered full-name key → pending islands (variants ≥5 chars)."""
    out: dict[str, list[dict]] = {}
    for isl in islands:
        if isl.get("id") not in pending_ids:
            continue
        for v in _name_variants(isl):
            key = v.strip().lower()
            if len(key) < 5:
                continue
            out.setdefault(key, []).append(isl)
    return out


def _islands_for_category(cat: str, name_index: dict[str, list[dict]]) -> list[dict]:
    """Return pending islands that this category specifically names."""
    if cat in BROAD_ROOTS:
        return []
    label = _category_label(cat).lower()
    best: list[dict] = []
    best_len = 0
    for key, group in name_index.items():
        if len(key) < 5:
            continue
        if key in label and len(key) > best_len:
            best_len = len(key)
            best = group
    if best:
        return best
    for key, group in name_index.items():
        if _mentions(label, [key]) or _mentions(cat, [key]):
            if len(key) > best_len:
                best_len = len(key)
                best = group
    return best


def _build_island_category_matches(
    islands: list[dict],
    index: dict[str, Any],
    pending_ids: set[str],
) -> dict[str, list[str]]:
    """island_id → [filenames] from island-specific categories in the index."""
    by_cat = index.get("by_category") or {}
    name_index = _build_name_index(islands, pending_ids)
    out: dict[str, list[str]] = {}
    for cat, fnames in by_cat.items():
        if cat in BROAD_ROOTS:
            continue
        for isl in _islands_for_category(cat, name_index):
            if not is_island_specific_category(cat, isl):
                continue
            bucket = out.setdefault(isl["id"], [])
            for f in fnames:
                if f not in bucket:
                    bucket.append(f)
    return out


def _token_index_for_files(files: dict[str, Any]) -> dict[str, list[str]]:
    """Lowercase token → [canonical filenames]."""
    idx: dict[str, list[str]] = {}
    for key in files:
        for tok in _TOKEN_RE.findall(_strip_diacritics(key).lower()):
            idx.setdefault(tok, []).append(key)
    return idx


def _build_filename_matches(
    islands: list[dict],
    index: dict[str, Any],
    pending_ids: set[str],
) -> dict[str, list[str]]:
    """island_id → [filenames] where filename mentions island (word boundary)."""
    out: dict[str, list[str]] = {}
    files = index.get("files") or {}
    if not files:
        return out
    token_idx = index.get("tokenIndex")
    if not isinstance(token_idx, dict):
        token_idx = _token_index_for_files(files)
    for isl in islands:
        iid = isl.get("id")
        if iid not in pending_ids:
            continue
        variants = _name_variants(isl)
        if not variants:
            continue
        tokens: set[str] = set()
        for v in variants:
            tokens.update(_TOKEN_RE.findall(_strip_diacritics(v).lower()))
        seen: set[str] = set()
        for tok in tokens:
            for key in token_idx.get(tok, []):
                if key in seen:
                    continue
                if _mentions(key, variants):
                    seen.add(key)
                    out.setdefault(iid, []).append(key)
    return out


def _pick_best_file(
    fnames: list[str],
    island: dict,
    cache_commons: dict[str, Any],
) -> str | None:
    variants = _name_variants(island)
    best = ""
    best_score = -1
    for fname in fnames:
        if _looks_like_non_photo(fname):
            continue
        m = cache_commons.get(_canon(fname)) or {}
        lic = (m.get("license") or "").strip()
        if not lic or "fair use" in lic.lower():
            score = -5
        else:
            score = 0
        w, h = m.get("width") or 0, m.get("height") or 0
        if w and h:
            score += min(5, int((w * h) / 500_000))
        if _mentions(fname, variants):
            score += 10
        if score > best_score:
            best_score = score
            best = fname
    return best or None


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


def match_from_index(
    index: dict[str, Any],
    islands: list[dict],
    *,
    pending_ids: set[str],
    cache_commons: dict[str, Any],
    cache_only: bool,
    limit: int,
    dry_run: bool,
) -> tuple[list[dict], dict[str, Any]]:
    pending = [i for i in islands if i.get("id") in pending_ids]
    report: dict[str, Any] = {
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source": SOURCE,
        "indexBuiltAt": index.get("builtAt"),
        "filesInIndex": len(index.get("files") or {}),
        "matches": [],
        "rejected": [],
        "counts": {
            "candidates": 0,
            "dual_signal_ok": 0,
            "staged": 0,
            "meta_fetched": 0,
        },
    }

    by_cat = _build_island_category_matches(pending, index, pending_ids)
    by_name = _build_filename_matches(pending, index, pending_ids)

    island_by_id = {i["id"]: i for i in pending}
    staged_ids: set[str] = set()
    adoptions: list[dict] = []

    for iid, island in island_by_id.items():
        if iid in staged_ids:
            continue
        fnames = list(dict.fromkeys((by_cat.get(iid) or []) + (by_name.get(iid) or [])))
        if not fnames:
            continue
        report["counts"]["candidates"] += 1

        need_meta = [f for f in fnames[:12] if _canon(f) not in cache_commons]
        if need_meta and not cache_only:
            fetch_commons_meta(need_meta, cache_commons)
            report["counts"]["meta_fetched"] += len(need_meta)

        best = _pick_best_file(fnames, island, cache_commons)
        if not best:
            report["rejected"].append({"id": iid, "reason": "no-licensed-file"})
            continue

        m = cache_commons.get(_canon(best)) or {}
        cats = (index.get("files") or {}).get(_canon(best), {}).get("categories") or []
        ok, signal = passes_dual_signal(island, best, cats, m)
        if not ok:
            report["rejected"].append({
                "id": iid,
                "name": island.get("name"),
                "file": best,
                "reason": signal,
                "categories": cats[:5],
            })
            continue

        report["counts"]["dual_signal_ok"] += 1
        source_ref = cats[0] if cats else best
        rec = build_image_record_from_commons(best, m, SOURCE, source_ref)
        if not rec:
            report["rejected"].append({"id": iid, "reason": "build-record-failed"})
            continue

        exact = _mentions(best, _name_variants(island))
        rec["imageConfidence"] = "high" if exact or signal.startswith("island-category") else "medium"
        rec["verifiedAt"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

        row = {
            "id": iid,
            "name": island.get("name", ""),
            "via": SOURCE,
            "dualSignal": signal,
            "category": source_ref,
            "categories": cats,
            "image_record": rec,
            "imageConfidence": rec.get("imageConfidence"),
            "source": rec.get("source"),
            "sourcePageUrl": rec.get("sourcePageUrl"),
        }
        adoptions.append(row)
        staged_ids.add(iid)
        report["counts"]["staged"] += 1
        report["matches"].append({
            "id": iid,
            "name": island.get("name"),
            "file": best,
            "signal": signal,
            "category": source_ref,
        })
        print(f"  ✓ {iid:40s} {signal}", flush=True)
        if limit and len(adoptions) >= limit:
            break

    if not dry_run:
        _save_staging(adoptions, report)
        _save(REPORT, report)

    return adoptions, report


def main() -> int:
    p = argparse.ArgumentParser(
        description="Commons archipelago category sweep (wide roots → staged adoptions).",
    )
    p.add_argument(
        "--build-index",
        action="store_true",
        help="Only build/update data/cache_commons_archipelago_index.json.",
    )
    p.add_argument(
        "--match",
        action="store_true",
        help="Only match islands from existing archipelago index cache.",
    )
    p.add_argument("--cache-only", action="store_true", help="No live Commons API calls.")
    p.add_argument("--named-only", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--dry-run", action="store_true", help="Do not write staging/report.")
    p.add_argument("--limit", type=int, default=0, help="Max adoptions to stage (0=all).")
    p.add_argument(
        "--member-limit",
        type=int,
        default=0,
        help="Max file members per category (0=unlimited).",
    )
    p.add_argument(
        "--subcat-limit",
        type=int,
        default=400,
        help="Max subcategories to walk per root.",
    )
    p.add_argument(
        "--no-subcats",
        action="store_true",
        help="Index root file members only (skip subcategory walk).",
    )
    p.add_argument("--delay", type=float, default=None, help="Override v3 DELAY_S.")
    args = p.parse_args()

    do_build = args.build_index or (not args.build_index and not args.match)
    do_match = args.match or (not args.build_index and not args.match)

    if args.delay is not None:
        v3.DELAY_S = max(0.0, float(args.delay))
        print(f"  API delay: {v3.DELAY_S}s", flush=True)

    cache_cm = _load(CACHE_CM)
    cache_commons = _load(CACHE_COMMONS)

    index = _load(CACHE_INDEX) if CACHE_INDEX.exists() else {}

    if do_build:
        print(f"Building archipelago index ({len(ARCHIPELAGO_ROOTS)} roots)…", flush=True)
        index = build_archipelago_index(
            cache_cm=cache_cm,
            cache_only=args.cache_only,
            member_limit=args.member_limit,
            subcat_limit=args.subcat_limit,
            include_subcats=not args.no_subcats,
        )
        if not args.dry_run:
            to_save = {k: v for k, v in index.items() if k != "tokenIndex"}
            _save(CACHE_INDEX, to_save)
            print(
                f"  indexed {index['counts']['files_indexed']:,} files "
                f"across {index['counts']['categories_with_files']:,} categories",
                flush=True,
            )
            print(f"  cache → {CACHE_INDEX.relative_to(ROOT)}", flush=True)
        if args.cache_only and index["counts"]["files_indexed"] == 0:
            print("WARN: cache-only build produced empty index", file=sys.stderr)
            return 1

    if do_match:
        if not (index.get("files")):
            if CACHE_INDEX.exists():
                index = _load(CACHE_INDEX)
            if not (index.get("files")):
                print("FATAL: no archipelago index — run --build-index first", file=sys.stderr)
                return 2
        if "tokenIndex" not in index and index.get("files"):
            index["tokenIndex"] = _token_index_for_files(index["files"])

        islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
        pending = [i for i in islands if not (i.get("images") or [])]
        if args.named_only:
            named_ids = _load_named_index_ids()
            if named_ids:
                pending = [i for i in pending if i.get("id") in named_ids]
        pending_ids = {i.get("id") for i in pending}
        print(
            f"Matching {len(pending_ids):,} photoless islands against "
            f"{len(index.get('files') or {}):,} indexed files…",
            flush=True,
        )
        adoptions, report = match_from_index(
            index,
            islands,
            pending_ids=pending_ids,
            cache_commons=cache_commons,
            cache_only=args.cache_only,
            limit=args.limit,
            dry_run=args.dry_run,
        )
        print()
        print(f"Candidates:        {report['counts']['candidates']:,}")
        print(f"Dual signal OK:    {report['counts']['dual_signal_ok']:,}")
        print(f"Staged:            {report['counts']['staged']:,}")
        if not args.dry_run:
            print(f"Staging → {STAGING.relative_to(ROOT)}")
            print(f"Report  → {REPORT.relative_to(ROOT)}")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
