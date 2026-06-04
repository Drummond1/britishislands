#!/usr/bin/env python3
"""Discover licensed island photos from open-web links (no social scraping).

Sources (ETHICS-safe):
  1. Wikidata P973 (described at URL) and P856 (official website) via wbgetentities
  2. English Wikipedia ``prop=extlinks`` and External links section URLs
  3. DuckDuckGo HTML search biased to .gov.uk, .scot, geograph, wikimedia
  4. Polite page fetch: ``og:image`` / ``twitter:image`` only when the page states
     OGL/CC licence markers or the host is a government / allowlisted asset site

Blocked: facebook, instagram, twitter/x, tiktok, pinterest, etc.
Allowlisted hosts: Commons, Geograph, Flickr /photos/ with on-page CC, UK gov, gov.scot.

Default: stage only (never mutates islands.json).

Run::

    python3 scripts/discover_island_photo_urls.py --limit 200
    python3 scripts/discover_island_photo_urls.py --test isle-of-skye --dry-run
    python3 scripts/discover_island_photo_urls.py --refresh

Outputs::

    data/staging/adoptions/web-discovery.json
    data/cache_web_photo_discovery.json
    data/image_enrichment_web_discovery_report.json
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
from collections import Counter
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
CURATED = DATA / "curated.json"
FERRIES = DATA / "ferries.json"
STAGING = DATA / "staging" / "adoptions" / "web-discovery.json"
CACHE = DATA / "cache_web_photo_discovery.json"
REPORT = DATA / "image_enrichment_web_discovery_report.json"

USER_AGENT = "isles-of-britain/0.1 (web-photo-discovery; static-site)"
DEFAULT_DELAY_S = 1.2
MAX_LIMIT = 500
MAX_FETCH_PER_ISLAND = 8
MAX_LINKS_PER_ISLAND = 24
HTML_MAX = 140_000

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
DDG_HTML = "https://html.duckduckgo.com/html/"
DDG_LITE = "https://lite.duckduckgo.com/lite/"
RL_BACKOFF = (5, 15, 45, 90, 120)

# Social / UGC platforms — never adopt.
BLOCKED_HOST_RE = re.compile(
    r"(?:^|\.)"
    r"(?:facebook\.com|fb\.com|instagram\.com|twitter\.com|x\.com|"
    r"tiktok\.com|pinterest\.(?:com|co\.uk)|linkedin\.com|"
    r"youtube\.com|youtu\.be|threads\.net)"
    r"(?:$|/)",
    re.I,
)

GOV_HOST_RE = re.compile(
    r"(?:^|\.)"
    r"(?:gov\.uk|gov\.scot|gov\.wales|wales\.gov\.uk|"
    r"nationalarchives\.gov\.uk|parliament\.uk|"
    r"infrastructure-ni\.gov\.uk|gov\.ie|"
    r"council|borough|county)"
    r"(?:$|/)",
    re.I,
)

ALLOWLIST_HOSTS = frozenset(
    {
        "commons.wikimedia.org",
        "upload.wikimedia.org",
        "www.geograph.org.uk",
        "geograph.org.uk",
        "s0.geograph.org.uk",
        "s1.geograph.org.uk",
        "s2.geograph.org.uk",
        "www.flickr.com",
        "flickr.com",
        "live.staticflickr.com",
        "farm1.staticflickr.com",
        "farm2.staticflickr.com",
        "farm3.staticflickr.com",
        "farm4.staticflickr.com",
        "farm5.staticflickr.com",
        "farm6.staticflickr.com",
        "farm7.staticflickr.com",
        "farm8.staticflickr.com",
        "farm9.staticflickr.com",
    }
)

LICENSE_PAGE_RE = re.compile(
    r"(?:open\s+government\s+licen[sc]e|ogl\s+v?3|ogl\s+\(|\bogl\b|"
    r"creative\s+commons|cc[\s\-]?by(?:[\s\-]?sa)?|cc0|"
    r"open\s+licence|open\s+license|psi\s+directive|"
    r"re[\s\-]?use\s+of\s+public\s+sector)",
    re.I,
)

CC_ON_PAGE_RE = re.compile(
    r"creativecommons\.org/licenses|"
    r"licensed?\s+under\s+(?:the\s+)?cc[\s\-]?by",
    re.I,
)

OG_IMAGE_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\']'
    r'(?:og:image|twitter:image(?::src)?)["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)
OG_IMAGE_RE2 = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']'
    r'(?:og:image|twitter:image(?::src)?)["\']',
    re.I,
)

HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)
IMAGE_EXT_RE = re.compile(r"\.(?:jpe?g|png|webp|gif)(?:\?|$)", re.I)

TRUSTED_LINK_RE = re.compile(
    r"(?:geograph\.org\.uk|wikimedia\.org|commons\.wikimedia|"
    r"upload\.wikimedia|\.gov\.uk|gov\.scot|gov\.wales|"
    r"flickr\.com/photos/)",
    re.I,
)

CONFIDENCE_RANK = {"high": 4, "medium-high": 3, "medium": 2, "low": 1}


def _load(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        print(f"WARN: corrupt cache {path.name}; starting fresh", file=sys.stderr)
        return {}


def _save(path: Path, data: Any, *, indent: int | None = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    if indent is None:
        text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    else:
        text = json.dumps(data, ensure_ascii=False, indent=indent) + "\n"
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _open(req: urllib.request.Request, timeout: int = 45) -> bytes:
    last: Exception | None = None
    for attempt in range(len(RL_BACKOFF) + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code in (429, 403, 502, 503, 504) and attempt < len(RL_BACKOFF):
                sleep = RL_BACKOFF[attempt]
                print(f"  HTTP {exc.code}; sleep {sleep}s", file=sys.stderr, flush=True)
                time.sleep(sleep)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            if attempt < len(RL_BACKOFF):
                time.sleep(RL_BACKOFF[attempt])
                continue
            raise
    if last:
        raise last  # type: ignore[misc]
    raise RuntimeError("max retries exceeded")


def _get_json(url: str, params: dict[str, Any], delay_s: float) -> dict:
    qs = urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(
        f"{url}?{qs}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    raw = _open(req)
    time.sleep(delay_s)
    return json.loads(raw.decode("utf-8"))


def _post_form(url: str, fields: dict[str, str], delay_s: float) -> str:
    body = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,*/*",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "https://duckduckgo.com/",
        },
        method="POST",
    )
    raw = _open(req)
    time.sleep(delay_s)
    return raw.decode("utf-8", errors="replace")


def _fetch_html(url: str, cache: dict, delay_s: float, *, refresh: bool = False) -> str:
    key = f"html:{url}"
    if not refresh and key in cache and isinstance(cache[key], dict) and "body" in cache[key]:
        return cache[key]["body"]
    if BLOCKED_HOST_RE.search(urlparse(url).netloc):
        cache[key] = {"error": "blocked_host", "url": url}
        return ""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"},
    )
    try:
        raw = _open(req)
        text = raw[:HTML_MAX].decode("utf-8", errors="replace")
        cache[key] = {"body": text, "fetched": time.strftime("%Y-%m-%dT%H:%M:%S")}
    except Exception as exc:
        cache[key] = {"error": str(exc)[:200], "url": url}
        text = ""
    time.sleep(delay_s)
    return text


def has_image(island: dict) -> bool:
    return bool(island.get("images") or island.get("image"))


def curated_ids() -> set[str]:
    if not CURATED.is_file():
        return set()
    rows = json.loads(CURATED.read_text(encoding="utf-8"))
    return {r["id"] for r in rows if isinstance(r, dict) and r.get("id")}


def ferry_island_ids(by_id: dict[str, dict]) -> set[str]:
    if not FERRIES.is_file():
        return set()
    data = json.loads(FERRIES.read_text(encoding="utf-8"))
    ids: set[str] = set()
    for route in data.get("routes") or []:
        terminals = route.get("terminals") or {}
        for key in ("from", "to"):
            iid = (terminals.get(key) or {}).get("islandId")
            if iid and iid in by_id:
                ids.add(iid)
    return ids


def island_tier(island: dict, curated: set[str], ferry: set[str]) -> int:
    iid = island.get("id") or ""
    if iid in curated:
        return 0
    if iid in ferry:
        return 1
    area = island.get("areaKm2")
    if isinstance(area, (int, float)) and area >= 1.0:
        return 2
    wd = (island.get("wikidata") or "").strip()
    if re.match(r"^Q\d+$", wd):
        return 3
    return 4


def sort_key(island: dict, curated: set[str], ferry: set[str]) -> tuple:
    t = island_tier(island, curated, ferry)
    area = island.get("areaKm2")
    area_sort = -(float(area) if isinstance(area, (int, float)) else 0.0)
    return (t, area_sort, (island.get("name") or "").lower())


def has_wiki_signal(island: dict) -> bool:
    if re.match(r"^Q\d+$", (island.get("wikidata") or "").strip()):
        return True
    wp = (island.get("wikipedia") or "").strip()
    return "wikipedia.org/wiki/" in wp


def enwiki_title(island: dict, cache: dict | None = None) -> str | None:
    wp = (island.get("wikipedia") or "").strip()
    m = re.search(r"en\.wikipedia\.org/wiki/([^#?]+)", wp, re.I)
    if m:
        return urllib.parse.unquote(m.group(1).replace(" ", "_"))
    qid = (island.get("wikidata") or "").strip()
    if cache and re.match(r"^Q\d+$", qid):
        row = cache.get(f"wd:{qid}")
        if isinstance(row, dict) and row.get("enwiki"):
            return row["enwiki"]
    return None


def prefetch_wikidata_batch(
    qids: list[str],
    cache: dict,
    delay_s: float,
    *,
    refresh: bool,
) -> None:
    """Batch-fetch P973/P856 and enwiki sitelink via wbgetentities."""
    missing = [q for q in qids if refresh or f"wd:{q}" not in cache]
    if not missing:
        return
    batch_size = 50
    for i in range(0, len(missing), batch_size):
        chunk = missing[i : i + batch_size]
        try:
            payload = _get_json(
                WIKIDATA_API,
                {
                    "action": "wbgetentities",
                    "format": "json",
                    "ids": "|".join(chunk),
                    "props": "claims|sitelinks",
                },
                delay_s,
            )
        except Exception as exc:
            print(f"  wbgetentities batch failed: {exc!r}", file=sys.stderr)
            for qid in chunk:
                wikidata_link_urls(qid, cache, delay_s, refresh=True)
            continue
        entities = payload.get("entities") or {}
        for qid in chunk:
            ent = entities.get(qid) or {}
            urls: list[str] = []
            claims = ent.get("claims") or {}
            for prop in ("P973", "P856"):
                for claim in claims.get(prop) or []:
                    ds = (claim.get("mainsnak") or {}).get("datavalue") or {}
                    val = ds.get("value")
                    if isinstance(val, str) and val.startswith("http"):
                        urls.append(val)
            enwiki = None
            en = (ent.get("sitelinks") or {}).get("enwiki") or {}
            if isinstance(en, dict) and en.get("title"):
                enwiki = en["title"]
            cache[f"wd:{qid}"] = {
                "urls": urls,
                "enwiki": enwiki,
                "fetched": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }


def _normalize_url(url: str, base: str | None = None) -> str | None:
    u = (url or "").strip()
    if not u or u.startswith("#") or u.lower().startswith("javascript:"):
        return None
    if u.startswith("//"):
        u = "https:" + u
    elif base and u.startswith("/"):
        p = urlparse(base)
        u = f"{p.scheme}://{p.netloc}{u}"
    if not u.startswith("http"):
        return None
    try:
        parsed = urlparse(u)
    except Exception:
        return None
    if BLOCKED_HOST_RE.search(parsed.netloc):
        return None
    return u.split("#")[0].rstrip("/")


def host_allowed(netloc: str) -> bool:
    host = (netloc or "").lower().lstrip("www.")
    if host in ALLOWLIST_HOSTS or host.endswith(".wikimedia.org"):
        return True
    if GOV_HOST_RE.search(host) or host.endswith(".gov.uk") or host.endswith(".gov.scot"):
        return True
    if host.endswith(".gov.wales") or host == "gov.wales":
        return True
    return False


def page_license_ok(html: str, url: str) -> tuple[bool, str]:
    host = urlparse(url).netloc.lower()
    if GOV_HOST_RE.search(host) or host.endswith(".gov.uk") or host.endswith(".gov.scot"):
        return True, "government host (OGL assumed)"
    if host_allowed(host) and "geograph.org.uk" in host:
        return True, "geograph allowlist"
    if "commons.wikimedia.org" in host or "upload.wikimedia.org" in host:
        return True, "wikimedia allowlist"
    if LICENSE_PAGE_RE.search(html):
        return True, "page states open/CC licence"
    if "flickr.com" in host and CC_ON_PAGE_RE.search(html):
        return True, "flickr page states Creative Commons"
    return False, "no licence signal on page"


def extract_og_images(html: str) -> list[str]:
    found: list[str] = []
    for pat in (OG_IMAGE_RE, OG_IMAGE_RE2):
        for m in pat.finditer(html):
            u = unescape(m.group(1).strip())
            if u and u not in found:
                found.append(u)
    return found


def commons_file_path_url(page_url: str) -> str | None:
    if "commons.wikimedia.org/wiki/File:" not in page_url:
        return None
    name = page_url.split("/wiki/File:", 1)[-1].split("?")[0]
    if not name:
        return None
    enc = urllib.parse.quote(name.replace(" ", "_"), safe="/()%")
    return (
        f"https://commons.wikimedia.org/wiki/Special:FilePath/{enc}?width=800"
    )


def geograph_image_from_page(html: str, page_url: str) -> str | None:
    for img in extract_og_images(html):
        if "geograph.org.uk" in img or IMAGE_EXT_RE.search(img):
            return img
    m = re.search(r'(https?://s\d\.geograph\.org\.uk/[^"\']+\.(?:jpg|png))', html, re.I)
    if m:
        return m.group(1)
    return None


def flickr_cc_license(html: str) -> str | None:
    m = re.search(
        r"creativecommons\.org/licenses/([a-z\-]+)/(\d+\.?\d*)",
        html,
        re.I,
    )
    if not m:
        return None
    code = m.group(1).upper().replace("BY", "BY").replace("SA", "SA")
    ver = m.group(2)
    return f"CC-{code}-{ver}"


def direct_image_candidate(url: str) -> dict[str, Any] | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if not host_allowed(host) and not GOV_HOST_RE.search(host):
        return None
    if "commons.wikimedia.org/wiki/File:" in url:
        img = commons_file_path_url(url)
        if img:
            return {
                "url": img,
                "sourcePageUrl": url,
                "license": "CC-BY-SA or CC-BY (Commons)",
                "attribution": "Via Wikimedia Commons — see file page for author and licence.",
                "confidence": "high",
                "reason": "direct Commons File: link",
                "via": "commons-file-link",
            }
    if "geograph.org.uk" in host or "geograph.org.uk" in url:
        if IMAGE_EXT_RE.search(url):
            return {
                "url": url,
                "sourcePageUrl": url,
                "license": "CC-BY-SA-2.0",
                "attribution": "© contributor, via Geograph Britain and Ireland (CC BY-SA 2.0)",
                "confidence": "high",
                "reason": "geograph image URL",
                "via": "geograph-link",
            }
    if IMAGE_EXT_RE.search(url) and host_allowed(host):
        lic = "OGL v3.0" if GOV_HOST_RE.search(host) else "CC (host allowlist)"
        return {
            "url": url,
            "sourcePageUrl": url,
            "license": lic,
            "attribution": "See source page.",
            "confidence": "medium-high" if GOV_HOST_RE.search(host) else "medium",
            "reason": "direct image URL on allowlisted host",
            "via": "direct-image",
        }
    return None


def candidate_from_page(url: str, html: str) -> dict[str, Any] | None:
    ok, lic_reason = page_license_ok(html, url)
    if not ok:
        return None
    host = urlparse(url).netloc.lower()
    via = "og-image"
    if "geograph.org.uk" in url:
        img = geograph_image_from_page(html, url)
        if img:
            return {
                "url": img,
                "sourcePageUrl": url,
                "license": "CC-BY-SA-2.0",
                "attribution": "© contributor, via Geograph Britain and Ireland (CC BY-SA 2.0)",
                "confidence": "high",
                "reason": f"geograph page; {lic_reason}",
                "via": "geograph-page",
            }
    if "flickr.com/photos/" in url:
        lic = flickr_cc_license(html)
        if not lic:
            return None
        imgs = extract_og_images(html)
        if not imgs:
            return None
        return {
            "url": imgs[0],
            "sourcePageUrl": url,
            "license": lic,
            "attribution": f"See Flickr page ({lic}).",
            "confidence": "medium",
            "reason": f"flickr CC on page; {lic_reason}",
            "via": "flickr-og",
        }
    imgs = extract_og_images(html)
    if not imgs:
        return None
    conf = "medium-high" if GOV_HOST_RE.search(host) else "medium"
    lic = "OGL v3.0" if GOV_HOST_RE.search(host) else "Open/CC (page text)"
    return {
        "url": imgs[0],
        "sourcePageUrl": url,
        "license": lic,
        "attribution": "See source page for attribution.",
        "confidence": conf,
        "reason": f"{via}; {lic_reason}",
        "via": via,
    }


def wikidata_link_urls(qid: str, cache: dict, delay_s: float, refresh: bool) -> list[str]:
    key = f"wd:{qid}"
    if not refresh and key in cache and not cache[key].get("error"):
        return list(cache[key].get("urls") or [])
    urls: list[str] = []
    enwiki: str | None = None
    try:
        payload = _get_json(
            WIKIDATA_API,
            {
                "action": "wbgetentities",
                "format": "json",
                "ids": qid,
                "props": "claims|sitelinks",
            },
            delay_s,
        )
    except Exception as exc:
        cache[key] = {"error": str(exc)[:120], "urls": [], "enwiki": None}
        return []
    ent = (payload.get("entities") or {}).get(qid) or {}
    claims = ent.get("claims") or {}
    for prop in ("P973", "P856"):
        for claim in claims.get(prop) or []:
            ds = (claim.get("mainsnak") or {}).get("datavalue") or {}
            val = ds.get("value")
            if isinstance(val, str) and val.startswith("http"):
                urls.append(val)
    sitelinks = ent.get("sitelinks") or {}
    en = sitelinks.get("enwiki") or {}
    if isinstance(en, dict) and en.get("title"):
        enwiki = en["title"]
    cache[key] = {
        "urls": urls,
        "enwiki": enwiki,
        "fetched": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    return urls


def wikipedia_extlinks(title: str, cache: dict, delay_s: float, refresh: bool) -> list[str]:
    key = f"wp:{title}"
    if not refresh and key in cache and not cache[key].get("error"):
        return list(cache[key].get("urls") or [])
    urls: list[str] = []
    try:
        payload = _get_json(
            WIKIPEDIA_API,
            {
                "action": "query",
                "format": "json",
                "prop": "extlinks",
                "titles": title,
                "ellimit": "max",
            },
            delay_s,
        )
        pages = (payload.get("query") or {}).get("pages") or {}
        for page in pages.values():
            for row in page.get("extlinks") or []:
                u = row.get("*") or row.get("url")
                if isinstance(u, str):
                    urls.append(u)
    except Exception as exc:
        cache[key] = {"error": str(exc)[:120], "urls": []}
        return []
    cache[key] = {"urls": urls, "fetched": time.strftime("%Y-%m-%dT%H:%M:%S")}
    return urls


def parse_external_links_html(html: str) -> list[str]:
    """Extract hrefs from External links section (fallback parse)."""
    urls: list[str] = []
    low = html.lower()
    start = low.find('id="external-links"')
    if start < 0:
        start = low.find(">external links<")
    if start < 0:
        return urls
    chunk = html[start : start + 25_000]
    for m in HREF_RE.finditer(chunk):
        u = _normalize_url(m.group(1))
        if u and link_candidate_ok(u):
            urls.append(u)
    return urls


def link_candidate_ok(url: str) -> bool:
    if not url:
        return False
    if BLOCKED_HOST_RE.search(urlparse(url).netloc):
        return False
    return bool(TRUSTED_LINK_RE.search(url) or host_allowed(urlparse(url).netloc))


def _parse_ddg_html(html: str) -> list[str]:
    urls: list[str] = []
    for m in re.finditer(r"uddg=([^&\"'>]+)", html):
        try:
            u = urllib.parse.unquote(m.group(1))
        except Exception:
            continue
        u = _normalize_url(u)
        if u and link_candidate_ok(u) and u not in urls:
            urls.append(u)
    for m in re.finditer(
        r'href="(https?://[^"]+(?:geograph|wikimedia|gov\.uk|gov\.scot)[^"]*)"',
        html,
        re.I,
    ):
        u = _normalize_url(m.group(1))
        if u and link_candidate_ok(u) and u not in urls:
            urls.append(u)
    return urls


def duckduckgo_urls(query: str, cache: dict, delay_s: float, refresh: bool) -> list[str]:
    key = f"ddg:{query}"
    if not refresh and key in cache:
        return list(cache[key].get("urls") or [])
    urls: list[str] = []
    last_err = ""
    for endpoint in (DDG_LITE, DDG_HTML):
        try:
            html = _post_form(endpoint, {"q": query, "s": "0"}, delay_s)
            urls = _parse_ddg_html(html)
            if urls:
                break
        except Exception as exc:
            last_err = str(exc)[:120]
    cache[key] = {
        "urls": urls,
        "error": last_err or None,
        "fetched": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    return urls


def collect_link_candidates(island: dict, cache: dict, delay_s: float, refresh: bool) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []

    def add(raw: str | None, base: str | None = None, *, from_trusted_source: bool = False) -> None:
        u = _normalize_url(raw or "", base)
        if not u or u in seen:
            return
        if from_trusted_source:
            if BLOCKED_HOST_RE.search(urlparse(u).netloc):
                return
        elif not link_candidate_ok(u):
            return
        seen.add(u)
        out.append(u)

    qid = (island.get("wikidata") or "").strip()
    if re.match(r"^Q\d+$", qid):
        for u in wikidata_link_urls(qid, cache, delay_s, refresh):
            add(u, from_trusted_source=True)

    title = enwiki_title(island, cache)
    if title:
        for u in wikipedia_extlinks(title, cache, delay_s, refresh):
            add(u, from_trusted_source=True)
        wp_html_key = f"wphtml:{title}"
        if refresh or wp_html_key not in cache:
            try:
                parse = _get_json(
                    WIKIPEDIA_API,
                    {
                        "action": "parse",
                        "format": "json",
                        "page": title,
                        "prop": "text",
                    },
                    delay_s,
                )
                text = (parse.get("parse") or {}).get("text") or {}
                body = text.get("*") if isinstance(text, dict) else ""
                if isinstance(body, str):
                    cache[wp_html_key] = {"body": body[:120_000]}
                    for u in parse_external_links_html(body):
                        add(u, from_trusted_source=True)
            except Exception:
                pass
        elif isinstance(cache.get(wp_html_key), dict):
            for u in parse_external_links_html(cache[wp_html_key].get("body") or ""):
                add(u, from_trusted_source=True)

    name = (island.get("name") or "").strip()
    nation = (island.get("nation") or "").strip()
    if name and len(out) < 3:
        q = f'{name} {nation} site:geograph.org.uk OR site:gov.uk OR site:wikimedia.org'
        for u in duckduckgo_urls(q, cache, delay_s, refresh):
            add(u)

    return out[:MAX_LINKS_PER_ISLAND]


def verify_url(url: str, cache: dict, delay_s: float, refresh: bool) -> dict[str, Any] | None:
    direct = direct_image_candidate(url)
    if direct:
        return direct
    if not host_allowed(urlparse(url).netloc) and not GOV_HOST_RE.search(
        urlparse(url).netloc
    ):
        return None
    html = _fetch_html(url, cache, delay_s, refresh=refresh)
    if not html:
        return None
    return candidate_from_page(url, html)


def pick_best(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda c: (
            CONFIDENCE_RANK.get(c.get("confidence", "low"), 0),
            1 if "commons" in (c.get("via") or "") else 0,
            1 if "geograph" in (c.get("via") or "") else 0,
        ),
    )


def build_image_record(island: dict, cand: dict[str, Any]) -> dict[str, Any]:
    name = (island.get("name") or "").strip()
    return {
        "url": cand["url"],
        "source": "web-discovery",
        "sourceRef": island.get("id") or "",
        "sourcePageUrl": cand.get("sourcePageUrl") or cand["url"],
        "license": cand.get("license") or "See source page",
        "attribution": cand.get("attribution") or "See source page.",
        "caption": name,
        "imageConfidence": cand.get("confidence"),
        "verifiedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }


def priority_targets(
    islands: list[dict],
    *,
    limit: int,
    test_id: str | None,
) -> list[dict]:
    by_id = {i["id"]: i for i in islands if i.get("id")}
    curated = curated_ids()
    ferry = ferry_island_ids(by_id)
    if test_id:
        return [i for i in islands if i.get("id") == test_id]
    pending = [
        i
        for i in islands
        if not has_image(i) and has_wiki_signal(i)
    ]
    pending.sort(key=lambda i: sort_key(i, curated, ferry))
    if limit:
        pending = pending[:limit]
    return pending


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=200, help="Max islands (default 200).")
    ap.add_argument("--test", metavar="ID", help="Single island id.")
    ap.add_argument("--dry-run", action="store_true", help="Do not write staging/cache.")
    ap.add_argument("--refresh", action="store_true", help="Ignore cached HTTP/API rows.")
    ap.add_argument("--delay", type=float, default=DEFAULT_DELAY_S, help="Seconds between requests.")
    args = ap.parse_args()

    if args.limit > MAX_LIMIT:
        print(f"FATAL: --limit {args.limit} > {MAX_LIMIT}", file=sys.stderr)
        return 2

    delay_s = max(0.5, float(args.delay))
    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    if not isinstance(islands, list):
        print("FATAL: islands.json is not a list", file=sys.stderr)
        return 2

    cache = _load(CACHE)
    targets = priority_targets(
        islands,
        limit=0 if args.test else args.limit,
        test_id=args.test,
    )
    print(f"Targets: {len(targets):,} (wiki/wikidata, no image, priority order)")

    qids = [
        (t.get("wikidata") or "").strip()
        for t in targets
        if re.match(r"^Q\d+$", (t.get("wikidata") or "").strip())
    ]
    if qids and not args.dry_run:
        print(f"Prefetch Wikidata ({len(qids):,} Q-IDs)…", flush=True)
        prefetch_wikidata_batch(qids, cache, delay_s, refresh=args.refresh)
        if not args.dry_run:
            _save(CACHE, cache, indent=None)

    adoptions: list[dict] = []
    source_counter: Counter[str] = Counter()
    via_counter: Counter[str] = Counter()
    report: dict[str, Any] = {
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "args": {
            "limit": args.limit,
            "test": args.test,
            "dry_run": args.dry_run,
            "refresh": args.refresh,
            "delay": delay_s,
        },
        "targets": len(targets),
        "staged": [],
        "skipped": [],
    }

    for n, isl in enumerate(targets, 1):
        iid = isl.get("id") or ""
        name = isl.get("name") or ""
        links = collect_link_candidates(isl, cache, delay_s, args.refresh)
        verified: list[dict[str, Any]] = []
        fetches = 0
        for url in links:
            if fetches >= MAX_FETCH_PER_ISLAND:
                break
            fetches += 1
            cand = verify_url(url, cache, delay_s, args.refresh)
            if cand:
                verified.append(cand)
        best = pick_best(verified)
        if best:
            rec = build_image_record(isl, best)
            row = {
                "id": iid,
                "name": name,
                "image_record": rec,
                "confidence": best.get("confidence"),
                "reason": best.get("reason"),
                "via": best.get("via"),
                "discovery_url": best.get("sourcePageUrl"),
            }
            adoptions.append(row)
            via_counter[best.get("via") or "unknown"] += 1
            host = urlparse(best.get("sourcePageUrl") or "").netloc.lower()
            if "geograph" in host:
                source_counter["geograph.org.uk"] += 1
            elif "wikimedia" in host or "commons" in host:
                source_counter["wikimedia.org"] += 1
            elif "gov" in host:
                source_counter["gov.uk / gov.scot"] += 1
            elif "flickr" in host:
                source_counter["flickr.com"] += 1
            else:
                source_counter[host or "other"] += 1
            report["staged"].append(
                {
                    "id": iid,
                    "name": name,
                    "via": best.get("via"),
                    "confidence": best.get("confidence"),
                    "url": rec.get("url"),
                    "sourcePageUrl": rec.get("sourcePageUrl"),
                }
            )
            print(
                f"  ✓ [{n:3d}/{len(targets)}] {iid[:40]:40s} "
                f"{best.get('confidence')} {best.get('via')}",
                flush=True,
            )
        else:
            report["skipped"].append({"id": iid, "name": name, "links_tried": len(links)})
            print(f"  · [{n:3d}/{len(targets)}] {iid[:40]:40s} (no verified image)", flush=True)

        if not args.dry_run and n % 20 == 0:
            _save(CACHE, cache, indent=None)
            STAGING.parent.mkdir(parents=True, exist_ok=True)
            _save(STAGING, adoptions)

    report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    report["staged_count"] = len(adoptions)
    report["top_sources"] = dict(source_counter.most_common(15))
    report["top_via"] = dict(via_counter.most_common(15))

    if not args.dry_run:
        _save(CACHE, cache, indent=None)
        STAGING.parent.mkdir(parents=True, exist_ok=True)
        _save(STAGING, adoptions)
        _save(REPORT, report)

    print()
    print(f"Staged: {len(adoptions):,} → {STAGING.relative_to(ROOT)}")
    print(f"Cache:  {CACHE.relative_to(ROOT)}")
    print("Top sources:")
    for src, cnt in source_counter.most_common(10):
        print(f"  {cnt:4d}  {src}")
    print("Top via:")
    for via, cnt in via_counter.most_common(8):
        print(f"  {cnt:4d}  {via}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
