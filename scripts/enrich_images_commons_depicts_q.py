#!/usr/bin/env python3
"""
Stage Commons photos linked to island Wikidata Q-IDs via structured depicts / subject.

Discovery per named island without ``images[]`` and with ``wikidata=Q…``:

  1. **Commons search** — ``haswbstatement:P180=<Q-ID>`` and ``P921=<Q-ID>``
  2. **Wikidata SPARQL** — media/items with ``wdt:P180`` or ``wdt:P921`` → Commons files
  3. **Commons SPARQL** (when available) — ``?file wdt:P180|P921 wd:<Q-ID>``

Only files that **verify** on Commons MediaInfo with P180 or P921 pointing at the exact
Q-ID are staged (~95% when P180 depicts exists; ~90% when P921 main subject only).

Run::

    python3 scripts/enrich_images_commons_depicts_q.py --named-only --limit 600
    python3 scripts/enrich_images_commons_depicts_q.py --test isle-of-mull --dry-run
    python3 scripts/enrich_images_commons_depicts_q.py --refresh --delay 1.5

Outputs (default: stage only — does not mutate islands.json)::

    data/staging/adoptions/commons-depicts-q.json
    data/cache_commons_depicts_q.json
    data/image_enrichment_commons_depicts_q_report.json

See ``docs/PHOTO-DISCOVERY-IDEAS.md`` (#1–#3 reverse Commons depicts graph).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
BACKUP = DATA / "islands.json.before-commons-depicts-q"
DEFAULT_CACHE = DATA / "cache_commons_depicts_q.json"
REPORT = DATA / "image_enrichment_commons_depicts_q_report.json"
STAGING = DATA / "staging" / "adoptions" / "commons-depicts-q.json"

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
COMMONS_SPARQL = "https://commons-query.wikimedia.org/sparql"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"

USER_AGENT = (
    "isles-of-britain/0.1 (commons depicts-q image enrichment; "
    "https://www.findmyisland.com; static-site)"
)
DEFAULT_DELAY_S = 1.0
SEARCH_LIMIT = 25
CHECKPOINT_EVERY = 50

SOURCE = "commons-depicts-q"
CONFIDENCE_P180 = ("high", 95)
CONFIDENCE_P921 = ("medium-high", 90)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import enrich_images_v3 as v3  # noqa: E402
import enrich_images_v5 as v5  # noqa: E402

QID_RE = re.compile(r"^Q\d+$")
LinkKind = Literal["P180", "P921"]


def atomic_write_json(path: Path, payload: Any, *, indent: int = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=indent), encoding="utf-8")
    os.replace(tmp, path)


def _claim_cache_for_json(claim_cache: dict[str, Any]) -> dict[str, Any]:
    """Sets in _claim_cache are not JSON-serialisable; store as sorted lists."""
    out: dict[str, Any] = {}
    for fn, props in claim_cache.items():
        if isinstance(props, dict):
            out[fn] = {
                k: sorted(list(v)) if isinstance(v, set) else v for k, v in props.items()
            }
        elif isinstance(props, set):
            out[fn] = sorted(props)
        else:
            out[fn] = props
    return out


def _claim_cache_from_json(raw: Any) -> dict[str, dict[str, set[str]]]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, set[str]]] = {}
    for fn, props in raw.items():
        if isinstance(props, dict):
            out[fn] = {
                k: set(v) if isinstance(v, list) else set() for k, v in props.items()
            }
        elif isinstance(props, list):
            out[fn] = {"P180": set(props), "P921": set()}
    return out


def _load_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        cache = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        print(f"WARN: corrupt cache {path}, starting fresh", file=sys.stderr)
        return {}
    raw_cc = cache.pop("_claim_cache", None)
    if raw_cc is not None:
        cache["_claim_cache"] = _claim_cache_from_json(raw_cc)
    return cache


def _save_cache(path: Path, cache: dict[str, Any]) -> None:
    payload = dict(cache)
    cc = payload.get("_claim_cache")
    if isinstance(cc, dict):
        payload["_claim_cache"] = _claim_cache_for_json(cc)
    atomic_write_json(path, payload, indent=None)


def _needs_image(island: dict) -> bool:
    return not (island.get("images") or island.get("image"))


def _has_qid(island: dict) -> bool:
    return bool(QID_RE.match((island.get("wikidata") or "").strip()))


class RateLimitError(RuntimeError):
    pass


def _http_json(
    url: str,
    params: dict[str, Any] | None = None,
    *,
    data: bytes | None = None,
    delay_s: float,
) -> dict:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if data:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        req = urllib.request.Request(url, data=data, headers=headers)
    else:
        qs = urllib.parse.urlencode(params or {}, doseq=True)
        req = urllib.request.Request(f"{url}?{qs}" if qs else url, headers=headers)
    last: Exception | None = None
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            time.sleep(delay_s)
            return payload
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code == 429:
                wait = min(120.0, delay_s * (4 ** attempt))
                print(f"  rate limited; sleeping {wait:.0f}s", file=sys.stderr)
                time.sleep(wait)
                if attempt >= 5:
                    raise RateLimitError(f"HTTP 429 from {url}") from exc
                continue
            if exc.code in (500, 502, 503, 504):
                time.sleep(delay_s * (2 + attempt))
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            time.sleep(delay_s * (1 + attempt))
    raise last  # type: ignore[misc]


def _claim_qids_from_entity(ent: dict, prop: str) -> set[str]:
    depicted: set[str] = set()
    for bucket in (ent.get("statements") or {}, ent.get("claims") or {}):
        if not isinstance(bucket, dict):
            continue
        for claim in bucket.get(prop) or []:
            sn = claim.get("mainsnak") or {}
            if sn.get("snaktype") != "value":
                continue
            val = (sn.get("datavalue") or {}).get("value") or {}
            if isinstance(val, dict) and val.get("id"):
                depicted.add(str(val["id"]))
    return depicted


def commons_search_statement(qid: str, prop: str, delay_s: float, limit: int = SEARCH_LIMIT) -> list[str]:
    params = {
        "action": "query",
        "format": "json",
        "list": "search",
        "srsearch": f"haswbstatement:{prop}={qid}",
        "srnamespace": "6",
        "srlimit": str(limit),
    }
    try:
        payload = _http_json(COMMONS_API, params, delay_s=delay_s)
    except RateLimitError:
        raise
    except Exception as exc:
        print(f"  commons search {prop}={qid} failed: {exc!r}", file=sys.stderr)
        return []
    out: list[str] = []
    for hit in (payload.get("query") or {}).get("search") or []:
        title = (hit.get("title") or "").strip()
        if title.startswith("File:"):
            out.append(v3._canon_filename(title))
    return list(dict.fromkeys(out))


def mediainfo_to_filenames(mids: list[str], delay_s: float) -> list[str]:
    if not mids:
        return []
    out: list[str] = []
    for i in range(0, len(mids), 50):
        batch = mids[i : i + 50]
        params = {
            "action": "wbgetentities",
            "format": "json",
            "ids": "|".join(batch),
            "props": "sitelinks",
        }
        try:
            payload = _http_json(COMMONS_API, params, delay_s=delay_s)
        except Exception as exc:
            print(f"  mediainfo sitelinks failed: {exc!r}", file=sys.stderr)
            continue
        for mid, ent in (payload.get("entities") or {}).items():
            if mid.startswith("-"):
                continue
            title = (ent.get("title") or "").strip()
            if title.startswith("File:"):
                out.append(v3._canon_filename(title))
    return list(dict.fromkeys(out))


def commons_sparql_linked(qid: str, delay_s: float, limit: int = 25) -> list[str]:
    query = f"""
SELECT ?file ?url WHERE {{
  {{
    ?file wdt:P180 wd:{qid} .
    ?file schema:url ?url .
  }} UNION {{
    ?file wdt:P921 wd:{qid} .
    ?file schema:url ?url .
  }}
}}
LIMIT {limit}
""".strip()
    body = urllib.parse.urlencode({"query": query}).encode()
    try:
        payload = _http_json(COMMONS_SPARQL, data=body, delay_s=delay_s)
    except urllib.error.HTTPError as exc:
        if exc.code in (307, 401, 403):
            return []
        raise
    except Exception:
        return []
    out: list[str] = []
    for row in (payload.get("results") or {}).get("bindings") or []:
        url = (row.get("url") or {}).get("value", "")
        if "/wiki/File:" in url:
            part = url.split("/wiki/File:", 1)[-1]
            out.append(v3._canon_filename(urllib.parse.unquote(part)))
            continue
        file_uri = (row.get("file") or {}).get("value", "")
        if "/entity/M" in file_uri:
            mid = "M" + file_uri.rsplit("/entity/M", 1)[-1].split("?")[0]
            out.extend(mediainfo_to_filenames([mid], delay_s))
    return list(dict.fromkeys(out))


def verify_sdc_batch(
    filenames: list[str],
    qid: str,
    delay_s: float,
    claim_cache: dict[str, dict[str, set[str]]],
) -> dict[str, LinkKind | None]:
    """Return {filename: 'P180' | 'P921' | None} — P180 wins when both match."""
    result: dict[str, LinkKind | None] = {}
    pending: list[str] = []
    for fn in filenames:
        if not fn:
            continue
        cached = claim_cache.get(fn)
        if cached is not None:
            if qid in cached.get("P180", set()):
                result[fn] = "P180"
            elif qid in cached.get("P921", set()):
                result[fn] = "P921"
            else:
                result[fn] = None
            continue
        pending.append(fn)

    batch_size = 40
    for i in range(0, len(pending), batch_size):
        batch = pending[i : i + batch_size]
        titles = "|".join("File:" + n for n in batch)
        q_params = {
            "action": "query",
            "format": "json",
            "titles": titles,
            "prop": "info",
        }
        try:
            q_payload = _http_json(COMMONS_API, q_params, delay_s=delay_s)
        except Exception as exc:
            print(f"  verify pageinfo batch failed: {exc!r}", file=sys.stderr)
            for fn in batch:
                result[fn] = None
            continue
        pages = (q_payload.get("query") or {}).get("pages") or {}
        mid_for_fn: dict[str, str] = {}
        for page in pages.values():
            if page.get("missing"):
                continue
            title = (page.get("title") or "").strip()
            fname = v3._canon_filename(title)
            if fname and page.get("pageid"):
                mid_for_fn[fname] = "M" + str(page["pageid"])

        mids = list(dict.fromkeys(mid_for_fn.values()))
        if not mids:
            for fn in batch:
                claim_cache.setdefault(fn, {"P180": set(), "P921": set()})
                result[fn] = None
            continue

        params = {
            "action": "wbgetentities",
            "format": "json",
            "ids": "|".join(mids),
            "props": "claims",
        }
        try:
            payload = _http_json(COMMONS_API, params, delay_s=delay_s)
        except Exception as exc:
            print(f"  verify mediainfo batch failed: {exc!r}", file=sys.stderr)
            for fn in batch:
                result[fn] = None
            continue
        mid_props: dict[str, dict[str, set[str]]] = {}
        for mid, ent in (payload.get("entities") or {}).items():
            if mid.startswith("-"):
                continue
            mid_props[mid] = {
                "P180": _claim_qids_from_entity(ent, "P180"),
                "P921": _claim_qids_from_entity(ent, "P921"),
            }
        for fn in batch:
            mid = mid_for_fn.get(fn)
            if not mid:
                claim_cache.setdefault(fn, {"P180": set(), "P921": set()})
                result[fn] = None
                continue
            props = mid_props.get(mid, {"P180": set(), "P921": set()})
            claim_cache[fn] = props
            if qid in props["P180"]:
                result[fn] = "P180"
            elif qid in props["P921"]:
                result[fn] = "P921"
            else:
                result[fn] = None
    return result


def prefetch_wikidata_linked_batch(
    qids: list[str],
    cache: dict[str, Any],
    delay_s: float,
    *,
    refresh: bool,
) -> None:
    missing = [q for q in qids if refresh or not (cache.get(q, {}).get("wikidata_sparql_files"))]
    if not missing:
        return
    batch_size = 25
    for i in range(0, len(missing), batch_size):
        batch = missing[i : i + batch_size]
        values = " ".join(f"wd:{q}" for q in batch)
        query = f"""
SELECT ?item ?media ?image WHERE {{
  VALUES ?item {{ {values} }}
  {{
    ?media wdt:P180 ?item .
  }} UNION {{
    ?media wdt:P921 ?item .
  }}
  OPTIONAL {{ ?media wdt:P18 ?image . }}
}}
LIMIT 500
""".strip()
        body = urllib.parse.urlencode({"query": query}).encode()
        try:
            payload = _http_json(WIKIDATA_SPARQL, data=body, delay_s=delay_s)
        except Exception as exc:
            print(f"  WDQS batch failed: {exc!r}", file=sys.stderr)
            continue
        per_qid: dict[str, list[str]] = {q: [] for q in batch}
        media_by_qid: dict[str, list[str]] = {q: [] for q in batch}
        for row in (payload.get("results") or {}).get("bindings") or []:
            item_uri = (row.get("item") or {}).get("value", "")
            qid = ""
            if "/entity/Q" in item_uri:
                qid = "Q" + item_uri.rsplit("/Q", 1)[-1]
            if qid not in per_qid:
                continue
            image_uri = (row.get("image") or {}).get("value", "")
            if image_uri and "Special:FilePath/" in image_uri:
                part = image_uri.split("Special:FilePath/", 1)[-1].split("?")[0]
                per_qid[qid].append(v3._canon_filename(urllib.parse.unquote(part)))
            media_uri = (row.get("media") or {}).get("value", "")
            if "/entity/Q" in media_uri:
                media_by_qid[qid].append("Q" + media_uri.rsplit("/Q", 1)[-1])
        all_media = list(dict.fromkeys(m for mids in media_by_qid.values() for m in mids))
        media_to_file: dict[str, list[str]] = {}
        for j in range(0, len(all_media), 50):
            chunk = all_media[j : j + 50]
            if not chunk:
                continue
            params = {
                "action": "wbgetentities",
                "format": "json",
                "ids": "|".join(chunk),
                "props": "claims|sitelinks",
            }
            try:
                wd = _http_json(WIKIDATA_API, params, delay_s=delay_s)
            except Exception as exc:
                print(f"  WD media resolve batch failed: {exc!r}", file=sys.stderr)
                continue
            for mid, ent in (wd.get("entities") or {}).items():
                if mid.startswith("-"):
                    continue
                names: list[str] = []
                sl = (ent.get("sitelinks") or {}).get("commonswiki") or {}
                title = (sl.get("title") or "").strip()
                if title.startswith("File:"):
                    names.append(v3._canon_filename(title))
                for claim in (ent.get("claims") or {}).get("P18") or []:
                    sn = claim.get("mainsnak") or {}
                    if sn.get("snaktype") != "value":
                        continue
                    val = (sn.get("datavalue") or {}).get("value")
                    if isinstance(val, str) and val.strip():
                        names.append(v3._canon_filename(val))
                media_to_file[mid] = names
        for qid, mids in media_by_qid.items():
            for mid in mids:
                per_qid[qid].extend(media_to_file.get(mid, []))
        for qid in batch:
            row = cache.setdefault(qid, {})
            row["wikidata_sparql_files"] = list(dict.fromkeys(per_qid.get(qid, [])))


def discover_candidates(
    qid: str,
    delay_s: float,
    cache_row: dict[str, Any],
    *,
    refresh: bool,
    sparql_enabled: bool,
) -> tuple[list[str], dict[str, int], bool]:
    counts = {
        "search_p180": 0,
        "search_p921": 0,
        "wikidata_sparql": 0,
        "commons_sparql": 0,
    }
    rate_limited = False
    if refresh or "candidates" not in cache_row:
        files: list[str] = []
        try:
            p180_hits = commons_search_statement(qid, "P180", delay_s)
            p921_hits = commons_search_statement(qid, "P921", delay_s)
        except RateLimitError:
            rate_limited = True
            p180_hits, p921_hits = [], []
        counts["search_p180"] = len(p180_hits)
        counts["search_p921"] = len(p921_hits)
        files.extend(p180_hits)
        files.extend(p921_hits)

        wd_files = list(cache_row.get("wikidata_sparql_files") or [])
        counts["wikidata_sparql"] = len(wd_files)
        files.extend(wd_files)

        if sparql_enabled:
            sparql_files = commons_sparql_linked(qid, delay_s)
            counts["commons_sparql"] = len(sparql_files)
            files.extend(sparql_files)

        files = list(dict.fromkeys(f for f in files if f))
        if not rate_limited:
            cache_row["candidates"] = files
            cache_row["discovery"] = counts
            cache_row["fetchedAt"] = datetime.now(timezone.utc).replace(
                microsecond=0
            ).isoformat()
        else:
            cache_row["rate_limited_at"] = datetime.now(timezone.utc).replace(
                microsecond=0
            ).isoformat()
    else:
        files = list(cache_row.get("candidates") or [])
        for k in counts:
            counts[k] = int((cache_row.get("discovery") or {}).get(k, 0))
    return files, counts, rate_limited


def _score_photo(fname: str, meta: dict, island: dict, link: LinkKind) -> float:
    score = 10.0 if link == "P180" else 6.0
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


def pick_best_verified(
    island: dict,
    verified: dict[str, LinkKind],
    cm_cache: dict,
) -> tuple[dict | None, str, LinkKind | None]:
    photos = [f for f, lk in verified.items() if lk and not v3._looks_like_non_photo(f)]
    if not photos:
        return None, "all_non_photo", None

    metas = v3.fetch_commons_meta(photos[:30], cm_cache)
    best_fname = ""
    best_score = -1.0
    best_link: LinkKind | None = None
    for fname in photos:
        m = metas.get(fname, {})
        lic = (m.get("license") or "").strip()
        if not lic or "fair use" in lic.lower():
            continue
        link = verified[fname]
        if not link:
            continue
        score = _score_photo(fname, m, island, link)
        if score > best_score:
            best_score = score
            best_fname = fname
            best_link = link
    if not best_fname or not best_link:
        return None, "no_license", None

    label, pct = CONFIDENCE_P180 if best_link == "P180" else CONFIDENCE_P921
    m = metas.get(best_fname, {})
    qid = island.get("wikidata", "")
    record = {
        "url": v3.commons_thumb_url(best_fname, 640),
        "fullUrl": v3.commons_thumb_url(best_fname, 1600),
        "caption": m.get("caption", ""),
        "source": SOURCE,
        "sourceRef": f"{best_link}:{qid}",
        "sourcePageUrl": m.get("descriptionUrl") or v3.commons_page_url(best_fname),
        "license": m.get("license"),
        "licenseUrl": m.get("licenseUrl", ""),
        "attribution": v3._format_attribution(
            m.get("attribution"), m.get("license"), "Wikimedia Commons (depicts/subject)"
        ),
        "primary": True,
        "imageConfidence": label,
        "confidencePct": pct,
    }
    return record, best_fname, best_link


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Stage Commons photos with verified P180/P921 links to island Q-IDs.",
    )
    ap.add_argument("--limit", type=int, default=0, help="Max islands to process (0 = all).")
    ap.add_argument("--named-only", action="store_true", help="Only ids in islands_index.json.")
    ap.add_argument("--dry-run", action="store_true", help="Print candidates; still writes staging.")
    ap.add_argument("--apply", action="store_true", help="Also write islands.json.")
    ap.add_argument("--no-backup", action="store_true", help="Skip backup when --apply.")
    ap.add_argument("--test", default="", help="Single island id.")
    ap.add_argument("--refresh", action="store_true", help="Bypass per-Q-ID discovery cache.")
    ap.add_argument("--no-stage", action="store_true", help="Skip staging JSON.")
    ap.add_argument("--no-sparql", action="store_true", help="Skip Commons SPARQL (often OAuth).")
    ap.add_argument("--delay", type=float, default=DEFAULT_DELAY_S, help="Seconds between API calls.")
    ap.add_argument(
        "--cache",
        default=str(DEFAULT_CACHE),
        help=f"Cache JSON path (default: {DEFAULT_CACHE.name}).",
    )
    args = ap.parse_args()
    cache_path = Path(args.cache)
    if not cache_path.is_absolute():
        cache_path = ROOT / cache_path

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    if not isinstance(islands, list):
        print("FATAL: islands.json is not a list", file=sys.stderr)
        return 2

    cache = _load_cache(cache_path)
    claim_cache: dict[str, dict[str, set[str]]] = cache.setdefault("_claim_cache", {})
    cm_cache = v3._load_cache(v3.CACHE_CM)
    sparql_enabled = not args.no_sparql
    sparql_blocked = bool(cache.get("_sparql_blocked"))

    if args.test:
        targets = [i for i in islands if i.get("id") == args.test]
        if not targets:
            print(f"FATAL: no island id {args.test!r}", file=sys.stderr)
            return 2
    else:
        targets = [i for i in islands if _needs_image(i) and _has_qid(i)]
        if args.named_only:
            named_ids = v5._load_named_index_ids()
            if not named_ids:
                print("FATAL: --named-only but islands_index.json missing", file=sys.stderr)
                return 2
            before = len(targets)
            targets = [i for i in targets if i.get("id") in named_ids]
            print(
                f"  named-only: {len(targets):,} of {before:,} Q-ID islands without images",
                file=sys.stderr,
            )

    if args.limit:
        targets = targets[: args.limit]

    def _qid_sort_key(island: dict) -> int:
        q = (island.get("wikidata") or "").strip()
        if QID_RE.match(q):
            try:
                return int(q[1:])
            except ValueError:
                pass
        return 10**12

    targets.sort(key=_qid_sort_key)

    print(f"Targets: {len(targets):,}", file=sys.stderr)

    qids_all = sorted({(i.get("wikidata") or "").strip() for i in targets if _has_qid(i)})
    if qids_all:
        print(f"  WDQS prefetch for {len(qids_all):,} Q-IDs…", file=sys.stderr)
        prefetch_wikidata_linked_batch(qids_all, cache, args.delay, refresh=args.refresh)
        _save_cache(cache_path, cache)

    report: dict[str, Any] = {
        "script": "enrich_images_commons_depicts_q.py",
        "source": SOURCE,
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "args": vars(args),
        "targets": len(targets),
        "sparql_blocked": sparql_blocked,
        "counts": {
            "staged": 0,
            "no_candidates": 0,
            "no_verified": 0,
            "no_license_or_photo": 0,
            "no_qid": 0,
            "by_link": {"P180": 0, "P921": 0},
            "by_discovery": {
                "search_p180": 0,
                "search_p921": 0,
                "wikidata_sparql": 0,
                "commons_sparql": 0,
            },
        },
        "adopted": [],
        "dry_run": bool(args.dry_run or args.test),
        "staging_path": str(STAGING.relative_to(ROOT)),
        "cache_path": str(cache_path.relative_to(ROOT)),
    }

    staging_adoptions: list[dict[str, Any]] = []
    adopted_n = 0
    last_checkpoint = 0

    if args.apply and not args.dry_run and not args.test and not args.no_backup and not BACKUP.exists():
        BACKUP.write_text(json.dumps(islands, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Backup → {BACKUP.relative_to(ROOT)}", file=sys.stderr)

    for n, isl in enumerate(targets, 1):
        if n % 25 == 0:
            print(f"  {n}/{len(targets)} processed; staged={adopted_n}", file=sys.stderr)

        qid = (isl.get("wikidata") or "").strip()
        if not _has_qid(isl):
            report["counts"]["no_qid"] += 1
            continue

        row = cache.setdefault(qid, {})
        if args.refresh:
            row.pop("candidates", None)
            row.pop("verified", None)

        use_sparql = sparql_enabled and not sparql_blocked
        candidates, disc, rate_limited = discover_candidates(
            qid, args.delay, row, refresh=args.refresh, sparql_enabled=use_sparql
        )
        if rate_limited:
            print(f"  {isl.get('id')}: rate limited, skipping cache", file=sys.stderr)
            _save_cache(cache_path, cache)
            continue
        if use_sparql and disc.get("commons_sparql", 0) == 0 and not row.get("commons_sparql_attempted"):
            row["commons_sparql_attempted"] = True
            test = commons_sparql_linked(qid, args.delay, limit=1)
            if not test:
                cache["_sparql_blocked"] = True
                sparql_blocked = True
                report["sparql_blocked"] = True

        for k, v in disc.items():
            if v and k in report["counts"]["by_discovery"]:
                report["counts"]["by_discovery"][k] += 1

        if not candidates:
            report["counts"]["no_candidates"] += 1
            _save_cache(cache_path, cache)
            continue

        verified_map = verify_sdc_batch(candidates, qid, args.delay, claim_cache)
        verified = {f: lk for f, lk in verified_map.items() if lk}
        row["verified"] = list(verified.keys())
        row["verified_links"] = {f: lk for f, lk in verified.items()}
        _save_cache(cache_path, cache)

        if not verified:
            report["counts"]["no_verified"] += 1
            continue

        candidate, chosen, link = pick_best_verified(isl, verified, cm_cache)
        if not candidate or not link:
            report["counts"]["no_license_or_photo"] += 1
            continue

        adopted_n += 1
        report["counts"]["staged"] += 1
        report["counts"]["by_link"][link] += 1
        row["chosen"] = chosen
        row["chosenLink"] = link

        label, pct = CONFIDENCE_P180 if link == "P180" else CONFIDENCE_P921
        staging_row = {
            "id": isl["id"],
            "name": isl.get("name", ""),
            "wikidata": qid,
            "imageConfidence": label,
            "confidencePct": pct,
            "wikidataLink": link,
            "depictsVerified": link == "P180",
            "subjectVerified": link == "P921",
            "chosenFile": chosen,
            "candidateCount": len(candidates),
            "verifiedCount": len(verified),
            "discovery": disc,
            "image": candidate,
            "sourcePageUrl": candidate.get("sourcePageUrl"),
            "license": candidate.get("license"),
        }
        report["adopted"].append({
            "id": staging_row["id"],
            "name": staging_row["name"],
            "wikidata": qid,
            "file": chosen,
            "link": link,
            "verifiedCount": len(verified),
            "sourcePageUrl": staging_row["sourcePageUrl"],
            "license": staging_row["license"],
        })
        staging_adoptions.append(staging_row)

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

    _save_cache(cache_path, cache)

    print(
        f"\nDone. staged={report['counts']['staged']} "
        f"no_candidates={report['counts']['no_candidates']} "
        f"no_verified={report['counts']['no_verified']} "
        f"no_license={report['counts']['no_license_or_photo']} "
        f"P180={report['counts']['by_link']['P180']} P921={report['counts']['by_link']['P921']}",
        file=sys.stderr,
    )
    if not args.no_stage:
        print(f"Staging → {STAGING.relative_to(ROOT)} ({len(staging_adoptions)} rows)", file=sys.stderr)
    print(report["counts"]["staged"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
