#!/usr/bin/env python3
"""Mine Geograph photos already on Wikimedia Commons (no live geosearch).

Uses ``cache_commons.json`` (~27k file metadata entries) and
``cache_commons_text.json`` — no Commons geosearch API.

Strategy (per pending named island):

  1. **Local index** — one scan of all ``cache_commons`` keys builds a
     token → filename map for Geograph uploads
     (``*_-_geograph.org.uk_-_*.jpg`` / spaced equivalents).
  2. **Cache text** — filenames from prior ``"{name}"`` text-search rows
     plus ``"{name}" geograph`` keys when present.
  3. **Live text search** (unless ``--cache-only``) —
     ``"{island name}" geograph`` via Commons ``list=search`` (cached).

Matching: island name must appear in the title prefix (before the Geograph
suffix) using v5 ``_mentions`` word-boundary rules. Optional: when
``cache_commons`` stores ``lat``/``lon``, reject candidates > 10 km away.

Sources: ``geograph-via-commons`` (index/local) or ``commons-text-search``
with ``sourceRef`` ``{island_id};geograph``. High confidence when the
filename prefix contains an exact island name match.

Run::

    python3 scripts/enrich_images_geograph_commons.py --cache-only
    python3 scripts/enrich_images_geograph_commons.py --limit 50
    python3 scripts/enrich_images_geograph_commons.py --dry-run --cache-only

Outputs (default: staging only — does not mutate islands.json)::

    data/staging/adoptions/geograph-commons.json
    data/image_enrichment_geograph_commons_report.json

Optional ``--apply`` writes adopted images into ``data/islands.json`` (with backup).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
BACKUP = DATA / "islands.json.before-geograph-commons"
STAGING = DATA / "staging" / "adoptions" / "geograph-commons.json"
REPORT = DATA / "image_enrichment_geograph_commons_report.json"

CACHE_COMMONS = DATA / "cache_commons.json"
CACHE_COMMONS_TEXT = DATA / "cache_commons_text.json"

GEO_MAX_KM = 10.0
TOKEN_MIN_LEN = 4

sys.path.insert(0, str(Path(__file__).resolve().parent))
from enrich_images_v5 import (  # noqa: E402
    DELAY_S,
    _canon,
    _haversine_km,
    _load,
    _load_named_index_ids,
    _looks_like_non_photo,
    _mentions,
    _name_variants,
    _save,
    _strip_diacritics,
    build_image_record_from_commons,
    commons_text_search,
    fetch_commons_meta,
)

# Commons title: "Place name - geograph.org.uk - 1234567.jpg" or underscore form.
_GEOGRAPH_FILE_RE = re.compile(
    r"geograph\.org\.uk",
    re.IGNORECASE,
)
_GEOGRAPH_SUFFIX_SPLIT = re.compile(
    r"\s*[-_]+\s*geograph\.org\.uk\s*[-_]+\s*",
    re.IGNORECASE,
)
_TOKEN_RE = re.compile(r"[a-z0-9']{" + str(TOKEN_MIN_LEN) + r",}")


def is_geograph_commons_file(fname: str) -> bool:
    if not fname:
        return False
    low = fname.lower()
    if not low.endswith(".jpg") and not low.endswith(".jpeg"):
        return False
    return bool(_GEOGRAPH_FILE_RE.search(fname))


def geograph_title_prefix(fname: str) -> str:
    """Text before the ``geograph.org.uk`` segment (canonical spaces)."""
    canon = _canon(fname)
    parts = _GEOGRAPH_SUFFIX_SPLIT.split(canon, maxsplit=1)
    return (parts[0] if parts else canon).strip()


def _tokenize_for_index(text: str) -> set[str]:
    ascii_t = _strip_diacritics(text or "").lower()
    return set(_TOKEN_RE.findall(ascii_t))


def _filename_has_exact_name(prefix: str, variants: list[str]) -> bool:
    """Strong match: full variant appears in the Geograph title prefix."""
    if not prefix:
        return False
    ascii_prefix = _strip_diacritics(prefix)
    for v in variants:
        v_ascii = _strip_diacritics(v)
        if len(v_ascii) < 4:
            continue
        if v_ascii.lower() in ascii_prefix.lower():
            # Require word-boundary style match (same spirit as _mentions).
            escaped = re.escape(v_ascii)
            escaped = escaped.replace(r"\'", "[']?")
            if re.search(
                rf"(?:^|[^a-z0-9]){escaped}(?:[^a-z0-9]|$)",
                ascii_prefix,
                re.IGNORECASE,
            ):
                return True
    return False


@dataclass
class GeographIndex:
    """Inverted token index over Geograph filenames in cache_commons."""

    files: list[str] = field(default_factory=list)
    token_to_files: dict[str, list[str]] = field(default_factory=dict)
    scanned: int = 0


def build_geograph_token_index(cache_commons: dict[str, Any]) -> GeographIndex:
    """Scan all cache_commons keys once; index by normalized title tokens."""
    idx = GeographIndex()
    idx.scanned = len(cache_commons)
    for fname in cache_commons:
        if not is_geograph_commons_file(fname):
            continue
        idx.files.append(fname)
        prefix = geograph_title_prefix(fname)
        for tok in _tokenize_for_index(prefix):
            idx.token_to_files.setdefault(tok, []).append(fname)
    return idx


def candidates_from_index(island: dict, index: GeographIndex) -> list[str]:
    variants = _name_variants(island)
    tokens: set[str] = set()
    for v in variants:
        tokens.update(_tokenize_for_index(v))
    seen: set[str] = set()
    out: list[str] = []
    for tok in sorted(tokens):
        for fname in index.token_to_files.get(tok, []):
            key = _canon(fname)
            if key in seen:
                continue
            seen.add(key)
            out.append(fname)
    return out


def _text_cache_keys(island: dict) -> list[str]:
    name = (island.get("name") or "").strip()
    arch = (island.get("archipelago") or "").strip()
    keys = [
        f"{name}|{arch}",
        f"{name}|",
        f'"{name}" geograph|{arch}',
        f'"{name}" geograph|',
    ]
    if arch and arch.lower() != name.lower():
        keys.append(f'"{name}" {arch}|geograph')
    return keys


def candidates_from_text_cache(
    island: dict,
    cache_text: dict[str, Any],
) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for key in _text_cache_keys(island):
        files = cache_text.get(key)
        if not isinstance(files, list):
            continue
        for f in files:
            if not is_geograph_commons_file(f):
                continue
            c = _canon(f)
            if c in seen:
                continue
            seen.add(c)
            out.append(f)
    return out


def _file_coords_from_cache(fname: str, cache_commons: dict) -> tuple[float, float] | None:
    m = cache_commons.get(_canon(fname)) or {}
    if not isinstance(m, dict):
        return None
    lat, lon = m.get("lat"), m.get("lon")
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        return float(lat), float(lon)
    coords = m.get("coords")
    if isinstance(coords, (list, tuple)) and len(coords) >= 2:
        try:
            return float(coords[0]), float(coords[1])
        except (TypeError, ValueError):
            pass
    return None


def _passes_optional_geo(
    island: dict,
    fname: str,
    cache_commons: dict,
    max_km: float = GEO_MAX_KM,
) -> tuple[bool, str]:
    coords = _file_coords_from_cache(fname, cache_commons)
    if coords is None:
        return True, "no-file-coords"
    lat = island.get("lat")
    lon = island.get("lng") if island.get("lng") is not None else island.get("lon")
    if lat is None or lon is None:
        return True, "island-no-coords"
    try:
        d_km = _haversine_km(float(lat), float(lon), coords[0], coords[1])
    except Exception:
        return False, "coord-error"
    if d_km <= max_km:
        return True, f"in-range ({d_km:.1f} km)"
    return False, f"out-of-range ({d_km:.1f} km > {max_km} km)"


def _score_candidate(
    fname: str,
    island: dict,
    variants: list[str],
    cache_commons: dict,
) -> tuple[int, str]:
    """Higher is better. Returns (score, reject_reason)."""
    if _looks_like_non_photo(fname):
        return -1, "non-photo"
    prefix = geograph_title_prefix(fname)
    if not (_mentions(prefix, variants) or _mentions(fname, variants)):
        return -1, "no-name-match"
    ok, reason = _passes_optional_geo(island, fname, cache_commons)
    if not ok:
        return -1, reason
    score = 0
    if _filename_has_exact_name(prefix, variants):
        score += 20
    elif _mentions(prefix, variants):
        score += 8
    m = cache_commons.get(_canon(fname)) or {}
    w, h = m.get("width") or 0, m.get("height") or 0
    if w and h:
        score += min(5, int((w * h) / 500_000))
    if "no-file-coords" not in reason and reason.startswith("in-range"):
        score += 3
    return score, ""


def _pick_best(
    filenames: list[str],
    island: dict,
    cache_commons: dict,
    report_rejected: list[dict[str, Any]],
    match_source: str,
) -> tuple[str | None, bool]:
    """Return (best_filename, exact_name_match)."""
    variants = _name_variants(island)
    best_fname = ""
    best_score = -1
    exact = False
    for fname in filenames:
        score, reason = _score_candidate(fname, island, variants, cache_commons)
        if score < 0:
            if reason:
                report_rejected.append({
                    "id": island.get("id"),
                    "source": match_source,
                    "file": fname,
                    "reason": reason,
                })
            continue
        prefix = geograph_title_prefix(fname)
        is_exact = _filename_has_exact_name(prefix, variants)
        if score > best_score or (score == best_score and is_exact and not exact):
            best_score = score
            best_fname = fname
            exact = is_exact
    if not best_fname:
        return None, False
    return best_fname, exact


def _stamp_high(rec: dict, exact: bool) -> dict:
    out = dict(rec)
    if exact:
        out["imageConfidence"] = "high"
        out["verifiedAt"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return out


def try_geograph_from_caches(
    island: dict,
    index: GeographIndex,
    cache_commons: dict,
    cache_text: dict,
    report_rejected: list[dict[str, Any]],
) -> dict | None:
    cands: list[str] = []
    seen: set[str] = set()
    for f in candidates_from_index(island, index) + candidates_from_text_cache(
        island, cache_text
    ):
        c = _canon(f)
        if c in seen:
            continue
        seen.add(c)
        cands.append(f)
    if not cands:
        return None
    best, exact = _pick_best(
        cands, island, cache_commons, report_rejected, "geograph-via-commons"
    )
    if not best:
        return None
    m = cache_commons.get(_canon(best)) or {}
    rec = build_image_record_from_commons(
        best, m, "geograph-via-commons", island.get("id", "")
    )
    if rec:
        return _stamp_high(rec, exact)
    return None


def geograph_text_cache_key(island: dict) -> str:
    name = (island.get("name") or "").strip()
    arch = (island.get("archipelago") or "").strip()
    return f'"{name}" geograph|{arch}'


def try_geograph_text_search(
    island: dict,
    cache_commons: dict,
    cache_text: dict,
    report_rejected: list[dict[str, Any]],
    *,
    cache_only: bool,
) -> dict | None:
    name = (island.get("name") or "").strip()
    if len(name) < 4:
        return None
    key = geograph_text_cache_key(island)
    if key in cache_text:
        files = cache_text[key]
    elif cache_only:
        return None
    else:
        q = f'"{name}" geograph'
        files = commons_text_search(q, limit=12)
        files = [f for f in files if is_geograph_commons_file(f)]
        cache_text[key] = files
        _save(CACHE_COMMONS_TEXT, cache_text)
        time.sleep(DELAY_S)
    if not files:
        return None
    missing_meta = [f for f in files[:8] if not cache_commons.get(_canon(f))]
    if missing_meta and not cache_only:
        fetch_commons_meta(missing_meta, cache_commons)
    best, exact = _pick_best(
        files, island, cache_commons, report_rejected, "commons-text-search"
    )
    if not best:
        return None
    m = cache_commons.get(_canon(best)) or {}
    rec = build_image_record_from_commons(
        best,
        m,
        "commons-text-search",
        f"{island.get('id', '')};geograph",
    )
    if rec:
        return _stamp_high(rec, exact)
    return None


def _atomic_write_islands(payload: list) -> None:
    tmp = ISLANDS.with_suffix(ISLANDS.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, ISLANDS)


def _save_staging(adoptions: list[dict]) -> None:
    STAGING.parent.mkdir(parents=True, exist_ok=True)
    tmp = STAGING.with_suffix(STAGING.suffix + ".tmp")
    tmp.write_text(
        json.dumps(adoptions, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, STAGING)


def main() -> int:
    p = argparse.ArgumentParser(
        description="Adopt Geograph-on-Commons photos from caches (optional live text search).",
    )
    p.add_argument(
        "--cache-only",
        action="store_true",
        help="Only local cache_commons index + cache_commons_text (no API).",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Write adopted images into islands.json (default: staging only).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Report adoptions without writing staging or islands.json.",
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
        "--test",
        default="",
        help="Process only this island id.",
    )
    p.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip backup of islands.json.",
    )
    p.add_argument(
        "--delay",
        type=float,
        default=None,
        metavar="SECONDS",
        help=f"Seconds between live API calls (default {DELAY_S}).",
    )
    args = p.parse_args()
    use_staging = not args.apply

    if args.delay is not None:
        import enrich_images_v5 as v5_mod  # noqa: E402

        v5_mod.DELAY_S = max(0.0, float(args.delay))
        print(f"  API delay: {v5_mod.DELAY_S}s", flush=True)

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

    cache_commons = _load(CACHE_COMMONS)
    cache_text = _load(CACHE_COMMONS_TEXT)

    print("Building Geograph token index from cache_commons…", flush=True)
    t0 = time.time()
    index = build_geograph_token_index(cache_commons)
    print(
        f"  indexed {len(index.files):,} Geograph files from "
        f"{index.scanned:,} cache keys ({time.time() - t0:.1f}s)",
        flush=True,
    )

    adoptions: list[dict] = []
    report: dict[str, Any] = {
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mode": "cache-only" if args.cache_only else "cache+live-text",
        "args": {**vars(args), "staging": use_staging},
        "staging_path": str(STAGING.relative_to(ROOT)),
        "index_geograph_files": len(index.files),
        "index_cache_keys_scanned": index.scanned,
        "geo_max_km": GEO_MAX_KM,
        "adopted": [],
        "rejected": [],
    }

    pending = [i for i in islands if not (i.get("images") or [])]
    if args.named_only:
        named_ids = _load_named_index_ids()
        if named_ids:
            before = len(pending)
            pending = [i for i in pending if i.get("id") in named_ids]
            print(f"  named-only: {len(pending):,} of {before:,} without images",
                  flush=True)
    if args.test:
        pending = [i for i in islands if i.get("id") == args.test]
    if args.limit:
        pending = pending[: args.limit]
    report["pending_considered"] = len(pending)
    print(f"Pending: {len(pending):,}", flush=True)

    pending_set = {i.get("id") for i in pending}
    n_attempted = 0
    n_adopted = 0
    n_cache_adopted = 0

    for isl in islands:
        if isl.get("id") not in pending_set:
            continue
        n_attempted += 1
        rec = try_geograph_from_caches(
            isl, index, cache_commons, cache_text, report["rejected"]
        )
        via = "geograph-via-commons"
        if not rec and not args.cache_only:
            rec = try_geograph_text_search(
                isl,
                cache_commons,
                cache_text,
                report["rejected"],
                cache_only=False,
            )
            via = "commons-text-search"
        if rec:
            if via == "geograph-via-commons":
                n_cache_adopted += 1
            entry = {
                "id": isl.get("id"),
                "name": isl.get("name"),
                "via": via,
                "image_record": rec,
                "imageConfidence": rec.get("imageConfidence"),
                "source": rec.get("source"),
                "sourcePageUrl": rec.get("sourcePageUrl"),
            }
            adoptions.append(entry)
            if args.apply and not args.dry_run:
                isl.setdefault("images", []).append(rec)
            n_adopted += 1
            conf = rec.get("imageConfidence", "")
            tag = f" [{conf}]" if conf else ""
            print(
                f"  ✓ {isl.get('id', ''):45s} via {via:24s} "
                f"{rec.get('sourcePageUrl', '')[:70]}{tag}",
                flush=True,
            )
            report["adopted"].append({
                "id": isl.get("id"),
                "name": isl.get("name"),
                "source": rec.get("source"),
                "via": via,
                "imageConfidence": rec.get("imageConfidence"),
                "sourcePageUrl": rec.get("sourcePageUrl"),
            })
        if args.test and rec:
            print(json.dumps(rec, ensure_ascii=False, indent=2), flush=True)

    if not args.dry_run:
        if use_staging:
            _save_staging(adoptions)
        if args.apply:
            _atomic_write_islands(islands)

    report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    report["attempted"] = n_attempted
    report["adopted_total"] = n_adopted
    report["staged_total"] = n_adopted if use_staging else 0
    report["adopted_from_cache_index"] = n_cache_adopted
    report["dry_run"] = args.dry_run
    _save(REPORT, report)

    print()
    print(f"Attempted:              {n_attempted:,}")
    print(f"Adopted (total):        {n_adopted:,}")
    print(f"Adopted (cache index):  {n_cache_adopted:,}")
    if use_staging and not args.dry_run:
        print(f"Staging  → {STAGING.relative_to(ROOT)} ({len(adoptions):,} rows)")
    print(f"Report   → {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
