#!/usr/bin/env python3
"""
Tier 3 property listing discovery: merge broker research, verify URLs, match atlas.

Reads:
  - data/discovery/property_tier3_raw.json  (array of desk-research rows)
  - data/discovery/property_listings_verified.json (existing verified, for dedupe)

Writes:
  - data/discovery/property_tier3_report.json
  - Updates property_listings_verified.json verified[] when run with --apply

Ethics: HEAD/GET check on broker URLs only; no Rightmove/Zoopla scrape.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "discovery"
DEFAULT_RAW = DATA / "property_tier3_raw.json"
VERIFIED = DATA / "property_listings_verified.json"
DEFAULT_REPORT = DATA / "property_tier3_report.json"
USER_AGENT = "isles-of-britain/0.9 (discover_property_tier3; link-check)"

SOLD_RE = re.compile(
    r"\b(sold\s+stc|sale\s+agreed|sold\s+subject|no\s+longer\s+available|"
    r"withdrawn|removed\s+from\s+market|this\s+property\s+has\s+been\s+sold)\b",
    re.I,
)
LIVE_RE = re.compile(
    r"\b(for\s+sale|offers\s+(?:over|in\s+excess)|guide\s+price|fixed\s+price|"
    r"auction|under\s+offer|available|price\s+on\s+application|poa)\b",
    re.I,
)

LISTING_TYPE_MAP = {
    "whole_island": "whole_island",
    "whole_island_listing": "whole_island",
    "private_island": "whole_island",
    "private_island_listing": "whole_island",
    "land": "land",
    "island_land": "land",
    "island_land_sale": "land",
    "residential": "residential",
    "home_on_island": "residential",
    "home-on-island": "residential",
    "residential_sale_on_island": "residential",
    "auction": "land",
    "unconditional_online_auction": "land",
}


def slug_id(url: str, broker: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (broker or "broker").lower())[:20]
    tail = re.sub(r"[^a-z0-9]+", "-", url.lower())[-40:].strip("-")
    return f"tier3-{base}-{tail}"[:64]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _fetch_page(url: str, timeout: float, *, allow_redirect: bool = True) -> tuple[int, str]:
    ctx = ssl.create_default_context()
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"},
        method="GET",
    )
    handlers: list = [urllib.request.HTTPSHandler(context=ctx)]
    if not allow_redirect:
        handlers.insert(0, _NoRedirect())
    opener = urllib.request.build_opener(*handlers)
    with opener.open(req, timeout=timeout) as resp:
        return resp.getcode(), resp.read(120_000).decode("utf-8", errors="replace")


def check_url(url: str, timeout: float = 20.0) -> dict:
    if not url or not url.startswith("http"):
        return {"ok": False, "reason": "bad_url"}
    try:
        code, body = _fetch_page(url, timeout)
    except urllib.error.HTTPError as exc:
        code = exc.code
        try:
            body = exc.read(80_000).decode("utf-8", errors="replace")
        except Exception:
            body = ""
        if code in (404, 410, 451) and "struttandparker.com" in url:
            try:
                code, body = _fetch_page(url.replace("://www.", "://"), timeout, allow_redirect=False)
            except urllib.error.HTTPError as exc2:
                if exc2.code in (404, 410, 451):
                    return {"ok": False, "http": exc2.code, "reason": "gone"}
                code = exc2.code
                body = exc2.read(80_000).decode("utf-8", errors="replace") if exc2.fp else ""
            except Exception as exc2:
                return {"ok": False, "reason": str(exc2)[:120]}
        elif code in (404, 410, 451):
            return {"ok": False, "http": code, "reason": "gone"}
    except Exception as exc:
        return {"ok": False, "reason": str(exc)[:120]}
    else:
        if code >= 400:
            return {"ok": False, "http": code, "reason": "http_error"}
    if SOLD_RE.search(body) and not LIVE_RE.search(body):
        return {"ok": False, "http": code, "reason": "sold_markers"}
    if not LIVE_RE.search(body) and len(body) < 500:
        return {"ok": False, "http": code, "reason": "no_live_markers"}
    return {"ok": True, "http": code, "reason": "live"}


def to_verified_row(m: dict, *, tier_label: str = "Tier 3") -> dict:
    ltype = LISTING_TYPE_MAP.get((m.get("listingType") or "").lower(), "residential")
    if m.get("listingType") in ("whole_island", "land", "residential"):
        ltype = m["listingType"]
    title = m.get("title") or f"{m.get('matchedName', m.get('islandName'))} — {m.get('broker', 'listing')}"
    notes = (
        f"{tier_label} desk research ({m.get('matchMethod', '?')}, {m.get('matchConfidence', '?')}). "
        f"{m.get('notes', '')}"
    ).strip()
    return {
        "islandId": m["islandId"],
        "title": title[:200],
        "url": m["url"],
        "listingType": ltype,
        "source": "curated",
        "sourceListingId": slug_id(m["url"], m.get("broker", "")),
        "priceDisplay": (m.get("priceDisplay") or "")[:80],
        "notes": notes[:400],
        "tier3": True,
        "matchConfidence": m.get("matchConfidence"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="Merge new rows into verified manifest")
    ap.add_argument("--skip-fetch", action="store_true", help="Skip URL checks (match only)")
    ap.add_argument("--delay", type=float, default=1.0, help="Seconds between URL checks")
    ap.add_argument("--raw", type=Path, default=DEFAULT_RAW, help="Research JSON array input")
    ap.add_argument("--report", type=Path, default=None, help="Report output path")
    ap.add_argument("--tier-label", default="Tier 3", help="Label for notes field")
    args = ap.parse_args()

    raw_path = args.raw
    report_path = args.report or DATA / f"{raw_path.stem}_report.json"
    if not raw_path.is_file():
        sys.exit(f"Missing {raw_path}")
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        sys.exit("property_tier3_raw.json must be a JSON array")

    import subprocess

    matched_path = DATA / "property_tier3_matched.json"
    subprocess.check_call(
        [sys.executable, str(ROOT / "scripts" / "match_property_listing_islands.py"),
         str(raw_path), "-o", str(matched_path)],
        cwd=ROOT,
    )
    matched = json.loads(matched_path.read_text(encoding="utf-8"))

    existing = json.loads(VERIFIED.read_text(encoding="utf-8"))
    existing_ids = {r["islandId"] for r in existing.get("verified") or []}
    existing_urls = {r["url"].rstrip("/").lower() for r in existing.get("verified") or []}

    report = {
        "runAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "rawCount": len(raw),
        "matchedCount": len(matched),
        "accepted": [],
        "rejected": [],
    }

    # Best row per island: prefer whole_island, then high confidence
    by_island: dict[str, dict] = {}
    type_rank = {"whole_island": 0, "land": 1, "residential": 2}
    conf_rank = {"high": 0, "medium": 1, "low": 2}

    for m in matched:
        if m.get("matchConfidence") == "low":
            report["rejected"].append({**m, "reason": "low_match_confidence"})
            continue
        iid = m["islandId"]
        url = (m.get("url") or "").strip()
        if not url:
            report["rejected"].append({**m, "reason": "no_url"})
            continue
        url_key = url.rstrip("/").lower()
        if url_key in existing_urls:
            report["rejected"].append({**m, "reason": "duplicate_url"})
            continue
        ltype = LISTING_TYPE_MAP.get((m.get("listingType") or "").lower(), "residential")
        score = (type_rank.get(ltype, 9), conf_rank.get(m.get("matchConfidence", "low"), 9))
        prev = by_island.get(iid)
        if prev is None or score < prev["_score"]:
            m = {**m, "_score": score}
            by_island[iid] = m

    candidates = list(by_island.values())
    print(f"candidates after island dedupe: {len(candidates)}", flush=True)

    new_rows = []
    for m in candidates:
        iid = m["islandId"]
        url = m["url"]
        if args.skip_fetch:
            check = {"ok": True, "reason": "skipped"}
        else:
            check = check_url(url)
            time.sleep(args.delay)
        if not check.get("ok"):
            report["rejected"].append({**m, "reason": f"url_check:{check.get('reason')}"})
            print(f"  reject {m.get('islandName')}: {check.get('reason')}", flush=True)
            continue
        row = to_verified_row(m, tier_label=args.tier_label)
        if iid in existing_ids:
            report["rejected"].append({**row, "reason": "island_already_listed"})
            continue
        new_rows.append(row)
        report["accepted"].append(row)
        print(f"  + {row['title'][:60]}", flush=True)

    report["newIslandCount"] = len(new_rows)
    report["previousVerifiedCount"] = len(existing.get("verified") or [])
    report["proposedTotal"] = report["previousVerifiedCount"] + len(new_rows)

    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nReport → {report_path}")
    print(f"New islands: {len(new_rows)}")

    if args.apply and new_rows:
        merged = list(existing.get("verified") or []) + new_rows
        existing["verified"] = merged
        existing["tier3AppliedAt"] = report["runAt"]
        existing["tier3NewCount"] = len(new_rows)
        VERIFIED.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Updated {VERIFIED} ({len(merged)} verified)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
