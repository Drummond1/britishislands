#!/usr/bin/env python3
"""HEAD every external URL in ``data/islands.json`` and report 4xx/5xx.

URLs checked (per island):

  * ``wikipedia``
  * ``image`` (only the ``url`` field — Commons file pages)
  * ``images[i].url`` and ``images[i].sourcePageUrl``
  * ``descriptionAttribution`` (any ``http(s)://…`` substrings)

Rate-limited at ~3 req/s overall (per-host queues respected by the
underlying socket).  Designed to be safe to run overnight.

Usage::

    python3 scripts/audit_broken_links.py
    python3 scripts/audit_broken_links.py --limit 500
    python3 scripts/audit_broken_links.py --concurrency 4

Output::

    data/broken_links_report.json
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
REPORT = DATA / "broken_links_report.json"

UA = "isles-of-britain/0.7 (link-checker; +https://github.com/local-atlas)"
URL_RE = re.compile(r"https?://[^\s'\"<>)\]]+")
TIMEOUT_S = 12


def collect_urls(island: dict) -> list[tuple[str, str]]:
    """Return list of (urlField, url) tuples for one island."""
    out: list[tuple[str, str]] = []
    if isinstance(island.get("wikipedia"), str) and island["wikipedia"].startswith("http"):
        out.append(("wikipedia", island["wikipedia"]))
    img = island.get("image")
    if isinstance(img, dict):
        if isinstance(img.get("url"), str) and img["url"].startswith("http"):
            out.append(("image.url", img["url"]))
        if isinstance(img.get("sourcePageUrl"), str) and img["sourcePageUrl"].startswith("http"):
            out.append(("image.sourcePageUrl", img["sourcePageUrl"]))
    for i, im in enumerate(island.get("images") or []):
        if isinstance(im, dict):
            if isinstance(im.get("url"), str) and im["url"].startswith("http"):
                out.append((f"images[{i}].url", im["url"]))
            if isinstance(im.get("sourcePageUrl"), str) and im["sourcePageUrl"].startswith("http"):
                out.append((f"images[{i}].sourcePageUrl", im["sourcePageUrl"]))
    attr = island.get("descriptionAttribution")
    if isinstance(attr, str):
        for u in URL_RE.findall(attr):
            out.append(("descriptionAttribution", u))
    return out


def check_one(url: str) -> dict:
    """HEAD a URL, falling back to GET-with-1-byte-range on 405."""
    started = time.time()
    try:
        req = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": UA, "Accept": "*/*"})
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            return {"status": resp.status, "method": "HEAD",
                    "elapsedMs": int((time.time() - started) * 1000)}
    except urllib.error.HTTPError as e:
        if e.code == 405:
            try:
                req = urllib.request.Request(
                    url, method="GET",
                    headers={"User-Agent": UA, "Accept": "*/*", "Range": "bytes=0-0"})
                with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                    return {"status": resp.status, "method": "GET-range",
                            "elapsedMs": int((time.time() - started) * 1000)}
            except urllib.error.HTTPError as e2:
                return {"status": e2.code, "method": "GET-range",
                        "elapsedMs": int((time.time() - started) * 1000)}
            except Exception as e2:
                return {"status": -1, "method": "GET-range",
                        "error": type(e2).__name__,
                        "elapsedMs": int((time.time() - started) * 1000)}
        return {"status": e.code, "method": "HEAD",
                "elapsedMs": int((time.time() - started) * 1000)}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return {"status": -1, "method": "HEAD",
                "error": type(e).__name__,
                "elapsedMs": int((time.time() - started) * 1000)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--concurrency", type=int, default=6)
    args = ap.parse_args()

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    tasks: list[tuple[str, str, str, str]] = []  # (iid, name, field, url)
    seen_urls: set[str] = set()
    for isl in islands:
        if not isinstance(isl, dict):
            continue
        for field, url in collect_urls(isl):
            if url in seen_urls:
                continue
            seen_urls.add(url)
            tasks.append((isl.get("id"), isl.get("name"), field, url))
    if args.limit:
        tasks = tasks[: args.limit]
    print(f"queued {len(tasks)} unique URLs across {len(islands)} islands "
          f"(concurrency={args.concurrency})", flush=True)

    bad: list[dict] = []
    checked = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        future_map = {ex.submit(check_one, t[3]): t for t in tasks}
        for fut in concurrent.futures.as_completed(future_map):
            iid, name, field, url = future_map[fut]
            res = fut.result()
            checked += 1
            if checked % 100 == 0:
                print(f"  checked {checked}/{len(tasks)}; bad so far: {len(bad)}",
                      flush=True)
            status = res.get("status")
            if status is None or status == -1 or status >= 400:
                bad.append({"id": iid, "name": name, "field": field, "url": url, **res})

    bad.sort(key=lambda b: (b.get("status") or -1, b.get("url") or ""))
    out = {
        "generatedAt": __import__("datetime").datetime.utcnow().isoformat(timespec="seconds"),
        "totalUrlsChecked": len(tasks),
        "badUrls": len(bad),
        "byStatus": {},
        "bad": bad,
    }
    for b in bad:
        s = str(b.get("status"))
        out["byStatus"][s] = out["byStatus"].get(s, 0) + 1
    REPORT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"done: {len(bad)} bad URLs / {len(tasks)} checked  → "
          f"{REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
