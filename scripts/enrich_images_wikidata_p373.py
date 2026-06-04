#!/usr/bin/env python3
"""
Harvest Wikidata P373 (Commons category) for named islands with Q-IDs but no photo.

v3 source A used the **commonswiki sitelink**, which many islands lack even when
P373 is populated (and vice versa). This pass reads P373 via ``wbgetentities``,
falls back to the commonswiki sitelink, and walks category members on Commons.

For each category, pick the best photo (quality / featured / name match) like
``enrich_images_v3.try_commons_category``, but also accept any member whose
**filename** mentions the island name even when it has no quality score.

Run::

    python3 scripts/enrich_images_wikidata_p373.py --named-only --limit 500
    python3 scripts/enrich_images_wikidata_p373.py --named-only --limit 300 --refresh
    python3 scripts/enrich_images_wikidata_p373.py --test isle-of-skye --dry-run
    python3 scripts/enrich_images_wikidata_p373.py --apply   # write islands.json (opt-in)

Outputs (default: stage only, never mutates islands.json)::

    data/staging/adoptions/p373-commons.json
    data/cache_wikidata_p373.json
    data/cache_commons_category.json              (shared sitelink cache)
    data/cache_commons.json                       (shared metadata cache)
    data/image_enrichment_wikidata_p373_report.json
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
BACKUP = DATA / "islands.json.before-p373"
CACHE_P373 = DATA / "cache_wikidata_p373.json"
REPORT = DATA / "image_enrichment_wikidata_p373_report.json"
STAGING = DATA / "staging" / "adoptions" / "p373-commons.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import enrich_images_v3 as v3  # noqa: E402
import enrich_images_v5 as v5  # noqa: E402

SOURCE = "commons-category-p373"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
CHECKPOINT_EVERY = 100


def atomic_write_json(path: Path, payload: Any, *, indent: int = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=indent), encoding="utf-8")
    os.replace(tmp, path)


def _needs_image(island: dict) -> bool:
    return not (island.get("images") or island.get("image"))


def _has_qid(island: dict) -> bool:
    qid = (island.get("wikidata") or "").strip()
    return bool(re.match(r"^Q\d+$", qid))


def p373_for_qids(qids: list[str], cache: dict, refresh: bool = False) -> dict[str, str]:
    """Return {Q-ID: 'Category:Foo' or ''} from Wikidata P373 claims."""
    out: dict[str, str] = {}
    missing = [q for q in qids if refresh or q not in cache]
    batch_size = 50
    for i in range(0, len(missing), batch_size):
        batch = missing[i : i + batch_size]
        params = {
            "action": "wbgetentities",
            "format": "json",
            "ids": "|".join(batch),
            "props": "claims",
        }
        try:
            payload = v3._get_json(WIKIDATA_API, params)
        except Exception as exc:
            print(f"  wbgetentities P373 batch failed: {exc!r}", file=sys.stderr)
            continue
        entities = payload.get("entities") or {}
        for qid in batch:
            ent = entities.get(qid) or {}
            claims = ent.get("claims") or {}
            cat = ""
            for claim in claims.get("P373") or []:
                ds = (claim.get("mainsnak") or {}).get("datavalue") or {}
                val = ds.get("value")
                if isinstance(val, str) and val.strip():
                    cat = val.strip()
                    break
            if cat and not cat.startswith("Category:"):
                cat = "Category:" + cat
            cache[qid] = cat
        v3._save_cache(CACHE_P373, cache)
        time.sleep(v3.DELAY_S)
    for q in qids:
        out[q] = cache.get(q, "")
    return out


def _normalize_category(title: str) -> str:
    t = (title or "").strip()
    if not t:
        return ""
    if not t.startswith("Category:"):
        return "Category:" + t
    return t


def resolve_commons_category(
    qid: str,
    p373_cache: dict,
    cc_cache: dict,
) -> tuple[str, str]:
    """Return (category title, 'p373' | 'sitelink' | '')."""
    cat = _normalize_category(p373_cache.get(qid, ""))
    if cat:
        return cat, "p373"
    sl = (cc_cache.get(qid) or "").strip()
    if sl:
        return _normalize_category(sl), "sitelink"
    return "", ""


def _score_photo(fname: str, meta: dict, island: dict) -> float:
    """Quality / featured / resolution / name scoring (v3 parity)."""
    score = 0.0
    cats = (meta.get("categories") or "").lower()
    if "quality images" in cats:
        score += 5
    if "featured pictures" in cats:
        score += 10
    if "valued images" in cats:
        score += 3
    w, h = meta.get("width") or 0, meta.get("height") or 0
    if w and h and w * h > 1_000_000:
        score += 1
    if v3._mentions_island(fname, island) or v3._mentions_island(meta.get("caption", ""), island):
        score += 4
    return score


def try_commons_category_p373(
    island: dict,
    category: str,
    cm_cache: dict,
) -> dict | None:
    if not category:
        return None
    members = v3.category_members(category, limit=50)
    photos = [f for f in members if not v3._looks_like_non_photo(f)]
    if not photos:
        return None

    metas = v3.fetch_commons_meta(photos, cm_cache)

    name_matches: list[tuple[str, dict, float]] = []
    for fname in photos:
        m = metas.get(fname, {})
        lic = (m.get("license") or "").strip()
        if not lic or "fair use" in lic.lower():
            continue
        if v3._mentions_island(fname, island):
            w, h = m.get("width") or 0, m.get("height") or 0
            tie = float(w * h) if w and h else 0.0
            name_matches.append((fname, m, tie))
    if name_matches:
        name_matches.sort(key=lambda t: t[2], reverse=True)
        best_fname, m, _ = name_matches[0]
        return _build_record(best_fname, m, category)

    best_fname = ""
    best_score = -1.0
    for fname in photos:
        m = metas.get(fname, {})
        lic = (m.get("license") or "").strip()
        if not lic or "fair use" in lic.lower():
            continue
        score = _score_photo(fname, m, island)
        if score > best_score:
            best_score = score
            best_fname = fname
    if not best_fname:
        return None
    m = metas.get(best_fname, {})
    if not m.get("license"):
        return None
    return _build_record(best_fname, m, category)


def _build_record(fname: str, meta: dict, category: str) -> dict:
    return {
        "url": v3.commons_thumb_url(fname, 640),
        "fullUrl": v3.commons_thumb_url(fname, 1600),
        "caption": meta.get("caption", ""),
        "source": SOURCE,
        "sourceRef": category,
        "sourcePageUrl": meta.get("descriptionUrl") or v3.commons_page_url(fname),
        "license": meta.get("license"),
        "licenseUrl": meta.get("licenseUrl", ""),
        "attribution": v3._format_attribution(
            meta.get("attribution"), meta.get("license"), "Wikimedia Commons (P373)"
        ),
        "primary": True,
    }


def compare_sitelink_vs_p373(qids: list[str], p373_cache: dict, cc_cache: dict) -> dict:
    """Diagnostic: how many Q-IDs have P373 vs commonswiki sitelink."""
    p373_map = {q: _normalize_category(p373_cache.get(q, "")) for q in qids}
    sitelink_map = {
        q: _normalize_category((cc_cache.get(q) or "").strip()) for q in qids
    }
    only_p373 = 0
    only_sitelink = 0
    both = 0
    neither = 0
    resolvable = 0
    for q in qids:
        has_p = bool(p373_map.get(q))
        has_s = bool(sitelink_map.get(q))
        if has_p or has_s:
            resolvable += 1
        if has_p and has_s:
            both += 1
        elif has_p:
            only_p373 += 1
        elif has_s:
            only_sitelink += 1
        else:
            neither += 1
    return {
        "qids_checked": len(qids),
        "resolvable_p373_or_sitelink": resolvable,
        "both_p373_and_sitelink": both,
        "p373_only": only_p373,
        "sitelink_only": only_sitelink,
        "neither": neither,
        "note": (
            "v3 commons-category used commonswiki sitelink only (no P373); "
            "most photoless Q-ID islands lack both sitelink and P373, "
            "which explains commons-category: 0 in image_enrichment_v3_report.json."
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Stage Commons photos via Wikidata P373 (+ sitelink fallback).",
    )
    ap.add_argument("--limit", type=int, default=0, help="Process at most N pending islands (0 = all).")
    ap.add_argument(
        "--named-only",
        action="store_true",
        help="Only islands whose id appears in data/islands_index.json.",
    )
    ap.add_argument("--dry-run", action="store_true", help="Print candidates; still writes staging unless --no-stage.")
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Also mutate data/islands.json (default: stage to p373-commons.json only).",
    )
    ap.add_argument("--no-backup", action="store_true", help="Skip islands.json.before-p373 backup when --apply.")
    ap.add_argument("--test", default="", help="Dry-run one island id.")
    ap.add_argument("--refresh", action="store_true", help="Bypass P373 + sitelink caches for target Q-IDs.")
    ap.add_argument("--no-stage", action="store_true", help="Skip writing data/staging/adoptions/p373-commons.json.")
    args = ap.parse_args()

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    if not isinstance(islands, list):
        print("FATAL: islands.json is not a list", file=sys.stderr)
        return 2

    p373_cache = v3._load_cache(CACHE_P373)
    cm_cache = v3._load_cache(v3.CACHE_CM)
    cc_cache = v3._load_cache(v3.CACHE_CC)

    if args.test:
        targets = [i for i in islands if i.get("id") == args.test]
        if not targets:
            print(f"FATAL: no island with id {args.test!r}", file=sys.stderr)
            return 2
    else:
        targets = [i for i in islands if _needs_image(i) and _has_qid(i)]
        if args.named_only:
            named_ids = v5._load_named_index_ids()
            if not named_ids:
                print("FATAL: --named-only but islands_index.json missing/empty", file=sys.stderr)
                return 2
            before = len(targets)
            targets = [i for i in targets if i.get("id") in named_ids]
            print(
                f"  named-only: {len(targets):,} of {before:,} Q-ID islands without images",
                file=sys.stderr,
            )

    if args.limit:
        targets = targets[: args.limit]

    qids = sorted({i["wikidata"] for i in targets if _has_qid(i)})
    print(f"Targets: {len(targets):,} islands; {len(qids):,} unique Q-IDs", file=sys.stderr)

    if args.refresh:
        for q in qids:
            p373_cache.pop(q, None)
            cc_cache.pop(q, None)

    # Cache-first: only missing Q-IDs hit the live Wikidata API.
    p373_for_qids(qids, p373_cache, refresh=args.refresh)
    v3.commons_category_for_qid(qids, cc_cache, refresh=args.refresh)

    coverage = compare_sitelink_vs_p373(qids, p373_cache, cc_cache)
    print(
        f"  P373 vs sitelink: resolvable={coverage['resolvable_p373_or_sitelink']} "
        f"both={coverage['both_p373_and_sitelink']} "
        f"p373_only={coverage['p373_only']} sitelink_only={coverage['sitelink_only']} "
        f"neither={coverage['neither']}",
        file=sys.stderr,
    )

    report: dict[str, Any] = {
        "script": "enrich_images_wikidata_p373.py",
        "source": SOURCE,
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "args": vars(args),
        "coverage_p373_vs_sitelink": coverage,
        "targets": len(targets),
        "counts": {
            "staged": 0,
            "no_category": 0,
            "no_photo": 0,
            "no_qid": 0,
            "by_category_source": {"p373": 0, "sitelink": 0},
        },
        "adopted": [],
        "dry_run": bool(args.dry_run or args.test),
        "staging_path": str(STAGING.relative_to(ROOT)),
    }

    staging_adoptions: list[dict[str, Any]] = []
    adopted_n = 0
    last_checkpoint = 0

    if args.apply and not args.dry_run and not args.test and not args.no_backup and not BACKUP.exists():
        BACKUP.write_text(json.dumps(islands, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Backup → {BACKUP.relative_to(ROOT)}", file=sys.stderr)

    for n, isl in enumerate(targets, 1):
        if n % 50 == 0:
            print(f"  {n}/{len(targets)} processed; staged={adopted_n}", file=sys.stderr)

        qid = (isl.get("wikidata") or "").strip()
        if not _has_qid(isl):
            report["counts"]["no_qid"] += 1
            continue

        category, cat_src = resolve_commons_category(qid, p373_cache, cc_cache)
        if not category:
            report["counts"]["no_category"] += 1
            continue

        candidate = try_commons_category_p373(isl, category, cm_cache)
        if not candidate:
            report["counts"]["no_photo"] += 1
            continue

        adopted_n += 1
        report["counts"]["staged"] += 1
        if cat_src in report["counts"]["by_category_source"]:
            report["counts"]["by_category_source"][cat_src] += 1

        row = {
            "id": isl["id"],
            "name": isl.get("name", ""),
            "wikidata": qid,
            "categorySource": cat_src,
            "category": category,
            "image": candidate,
            "sourcePageUrl": candidate.get("sourcePageUrl"),
            "license": candidate.get("license"),
        }
        report["adopted"].append({
            "id": row["id"],
            "name": row["name"],
            "wikidata": qid,
            "categorySource": cat_src,
            "p373": category,
            "sourcePageUrl": row["sourcePageUrl"],
            "license": row["license"],
        })
        staging_adoptions.append(row)

        if args.dry_run or args.test:
            print(json.dumps(candidate, indent=2, ensure_ascii=False))
            continue

        if args.apply:
            imgs = isl.get("images") or []
            imgs.append(candidate)
            for k, img in enumerate(imgs):
                img["primary"] = (k == 0)
            isl["images"] = imgs
            if not isl.get("image"):
                isl["image"] = candidate["url"]

        if adopted_n - last_checkpoint >= CHECKPOINT_EVERY:
            last_checkpoint = adopted_n
            if not args.no_stage and not args.dry_run and not args.test:
                atomic_write_json(
                    STAGING,
                    {
                        "version": 1,
                        "generatedAt": report["generatedAt"],
                        "source": SOURCE,
                        "adoptions": staging_adoptions,
                        "report": report,
                    },
                )
            atomic_write_json(REPORT, report)
            if args.apply:
                atomic_write_json(ISLANDS, islands)
            print(f"    [checkpoint] {adopted_n} adoptions", file=sys.stderr)

    if not args.no_stage and not args.dry_run and not args.test:
        atomic_write_json(
            STAGING,
            {
                "version": 1,
                "generatedAt": report["generatedAt"],
                "source": SOURCE,
                "adoptions": staging_adoptions,
                "report": report,
            },
        )

    atomic_write_json(REPORT, report)
    if args.apply and not args.dry_run and not args.test and adopted_n:
        atomic_write_json(ISLANDS, islands)

    print(
        f"\nDone. staged={report['counts']['staged']} "
        f"no_category={report['counts']['no_category']} "
        f"no_photo={report['counts']['no_photo']} "
        f"by_source={report['counts']['by_category_source']}",
        file=sys.stderr,
    )
    if not args.no_stage:
        print(f"Staging → {STAGING.relative_to(ROOT)} ({len(staging_adoptions)} rows)", file=sys.stderr)
    print(report["counts"]["staged"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
