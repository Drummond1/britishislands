#!/usr/bin/env python3
"""
Generate crawlers / GEO-friendly artifacts for the static atlas.

Outputs (when --site-origin is set):
  - sitemap.xml — home, nation hubs, ferry guides, /islands/{nation}/{slug}/
  - robots.txt — allows all, points to sitemap

Always written:
  - llms.txt — project summary for AI crawlers
  - data/seo_path_by_id.json — id → public path (for tooling / probes)

Optional:
  - --landing-dir DIR — also write legacy /profiles/<id>.html redirects
  - /islands/.../index.html canonical landings + nation hubs
  - Patches index.html crawl-link block between IOB_CRAWL_LINKS markers

Examples:
  IOB_SITE_ORIGIN=https://www.findmyisland.com python3 scripts/generate_seo_artifacts.py \\
    --landing-dir profiles
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from seo_paths import (  # noqa: E402
    NATION_HUB_BLURB,
    NATION_HUB_TITLE,
    NATION_SEGMENT,
    assign_seo_paths,
    nation_segment,
    page_title,
)

DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
CURATED = DATA / "curated.json"
FEATURED = DATA / "featured_islands.json"
SEO_PATH_MAP = DATA / "seo_path_by_id.json"
INDEX_HTML = ROOT / "index.html"
ISLANDS_DIR = ROOT / "islands"

FERRY_LABELS: dict[str, str] = {
    "/ferries/": "All ferry guides",
    "/ferries/hebrides/": "Hebrides",
    "/ferries/orkney/": "Orkney",
    "/ferries/shetland/": "Shetland",
    "/ferries/isle-of-wight/": "Isle of Wight",
    "/ferries/isles-of-scilly/": "Isles of Scilly",
    "/ferries/isle-of-man/": "Isle of Man",
    "/ferries/channel-islands/": "Channel Islands",
    "/ferries/scottish/": "Scottish islands",
    "/ferries/welsh/": "Wales",
    "/ferries/ireland/": "Ireland",
    "/ferries/northern-ireland/": "Northern Ireland",
    "/ferries/calmac/": "CalMac",
}

FERRY_PATHS = (
    "/ferries/",
    "/ferries/hebrides/",
    "/ferries/orkney/",
    "/ferries/shetland/",
    "/ferries/isle-of-wight/",
    "/ferries/isles-of-scilly/",
    "/ferries/isle-of-man/",
    "/ferries/channel-islands/",
    "/ferries/scottish/",
    "/ferries/welsh/",
    "/ferries/ireland/",
    "/ferries/northern-ireland/",
    "/ferries/calmac/",
)

CRAWL_LINKS_MARKER_START = "<!-- IOB_CRAWL_LINKS_START -->"
CRAWL_LINKS_MARKER_END = "<!-- IOB_CRAWL_LINKS_END -->"

TRUST_PAGES: dict[str, str] = {
    "/about/": "About Find My Island",
    "/methodology/": "Methodology",
    "/editorial-policy/": "Editorial policy",
    "/corrections/": "Corrections",
    "/sources-licensing/": "Sources and licensing",
    "/contact/": "Contact",
    "/dataset/": "Dataset",
}


def load_id_set(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {str(x.get("id")) for x in data if x.get("id")}
    if isinstance(data, dict) and isinstance(data.get("islands"), list):
        return {str(x.get("id")) for x in data["islands"] if x.get("id")}
    return set()


def island_image_url(isl: dict) -> str:
    images = isl.get("images") or []
    if images:
        img = images[0]
        for key in ("fullUrl", "url", "thumbUrl"):
            u = str(img.get(key) or "").strip()
            if u:
                return u
    return str(isl.get("image") or "").strip()


def island_priority(iid: str, isl: dict, curated: set[str], featured: set[str]) -> float:
    if iid in curated:
        return 0.85
    if iid in featured:
        return 0.75
    if isl.get("images") or isl.get("image"):
        return 0.55
    return 0.45


def sort_islands_for_sitemap(
    islands: list[dict], curated: set[str], featured: set[str]
) -> list[dict]:
    def key(isl: dict) -> tuple:
        iid = str(isl.get("id") or "")
        if iid in curated:
            tier = 0
        elif iid in featured:
            tier = 1
        elif isl.get("images") or isl.get("image"):
            tier = 2
        else:
            tier = 3
        return (tier, str(isl.get("name") or iid).lower())

    return sorted(islands, key=key)


def _ymd_from_iso(s: str) -> str | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except Exception:
        return None


def _mtime_ymd(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _island_lastmod(isl: dict, default_ymd: str) -> str:
    # Prefer explicit record timestamps when available; otherwise file mtime.
    candidates = [
        _ymd_from_iso(str(isl.get("propertyListingsFetchedAt") or "")),
        _ymd_from_iso(str(isl.get("imageEnrichmentFetchedAt") or "")),
        _ymd_from_iso(str(isl.get("nameEnrichmentFetchedAt") or "")),
    ]
    for src in isl.get("sources") or []:
        if isinstance(src, dict):
            candidates.append(_ymd_from_iso(str(src.get("retrieved") or "")))
    vals = [c for c in candidates if c]
    return max(vals) if vals else default_ymd


def write_urlset(path: Path, entries: list[tuple[str, float, str]]) -> None:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for loc, priority, lastmod in entries:
        lines.append("  <url>")
        lines.append(f"    <loc>{xml_escape(loc)}</loc>")
        lines.append(f"    <lastmod>{lastmod}</lastmod>")
        lines.append(f"    <priority>{priority:.2f}</priority>")
        lines.append("  </url>")
    lines.append("</urlset>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_sitemap_index(path: Path, files: list[tuple[str, str]]) -> None:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for loc, lastmod in files:
        lines.append("  <sitemap>")
        lines.append(f"    <loc>{xml_escape(loc)}</loc>")
        lines.append(f"    <lastmod>{lastmod}</lastmod>")
        lines.append("  </sitemap>")
    lines.append("</sitemapindex>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def profile_page_html(
    isl: dict,
    *,
    origin: str,
    atlas_href: str,
    profile_path: str,
    title: str,
    related_links: list[tuple[str, str]] | None = None,
    depth: int = 3,
) -> str:
    iid = isl["id"]
    name = html.escape(str(isl.get("name") or iid), quote=True)
    nation = html.escape(str(isl.get("nation") or ""), quote=True)
    title_esc = html.escape(title, quote=True)
    desc_raw = isl.get("shortDescription") or (
        f"{isl.get('name', '')} — island in {isl.get('nation', 'the British Isles')}. "
        f"Map, location, and profile on Find My Island."
    )
    desc = html.escape(str(desc_raw).replace("\n", " ").strip()[:300], quote=True)
    profile_url = f"{origin}{profile_path}" if origin else profile_path
    atlas_url = f"{atlas_href}?island={html.escape(iid, quote=True)}"
    img = island_image_url(isl)
    og_img = ""
    if img:
        og_img = f'  <meta property="og:image" content="{html.escape(img, quote=True)}"/>\n'

    lat = isl.get("lat")
    lng = isl.get("lng")
    address = ""
    if isl.get("nation"):
        address = f',\n    "address": {{"@type": "PostalAddress", "addressCountry": {json.dumps(str(isl.get("nation")))}}}'

    geo_block = ""
    if lat is not None and lng is not None:
        identifiers: list[dict[str, Any]] = []
        if isl.get("osmType") and isl.get("osmId") is not None:
            identifiers.append(
                {
                    "@type": "PropertyValue",
                    "propertyID": "OpenStreetMap",
                    "value": f"{isl.get('osmType')}/{isl.get('osmId')}",
                }
            )
        if isl.get("wikidata"):
            identifiers.append(
                {
                    "@type": "PropertyValue",
                    "propertyID": "Wikidata",
                    "value": str(isl.get("wikidata")),
                }
            )
        same_as: list[str] = []
        if isl.get("wikipedia"):
            same_as.append(str(isl["wikipedia"]))
        if isl.get("wikidata"):
            same_as.append(f"https://www.wikidata.org/wiki/{isl['wikidata']}")
        geo_block = f"""
  <script type="application/ld+json">{{
    "@context": "https://schema.org",
    "@type": "Landform",
    "name": {json.dumps(str(isl.get("name") or iid))},
    "description": {json.dumps(str(desc_raw)[:500])},
    "url": {json.dumps(profile_url)},
    "identifier": {json.dumps(identifiers[0] if len(identifiers) == 1 else identifiers) if identifiers else "null"},
    "sameAs": {json.dumps(same_as) if same_as else "null"},
    "geo": {{"@type": "GeoCoordinates", "latitude": {lat}, "longitude": {lng}}}{address}
  }}</script>"""

    nation_line = (
        f'<p class="lp-kicker">{nation}</p>' if nation else ""
    )

    facts: list[str] = []
    if isl.get("type"):
        facts.append(
            f"<li><strong>Type</strong>{html.escape(str(isl['type']))} island</li>"
        )
    if isl.get("archipelago"):
        facts.append(
            f"<li><strong>Group</strong>{html.escape(str(isl['archipelago']))}</li>"
        )
    if isl.get("areaKm2"):
        facts.append(
            f"<li><strong>Area</strong>{html.escape(str(isl['areaKm2']))} km²</li>"
        )
    if isl.get("population") is not None and isl.get("population") != "":
        facts.append(
            f"<li><strong>Population</strong>{html.escape(str(isl['population']))}</li>"
        )
    if lat is not None and lng is not None:
        facts.append(
            f"<li><strong>Location</strong>{lat}, {lng}</li>"
        )
    facts_block = ""
    if facts:
        facts_block = (
            '  <ul class="lp-facts">\n    '
            + "\n    ".join(facts)
            + "\n  </ul>\n"
        )

    section_chunks: list[str] = []
    section_map = [
        ("Names", "namesSummary"),
        ("Geography", "geography"),
        ("History", "history"),
        ("Wildlife and conservation", "wildlife"),
        ("How to reach it", "transport"),
        ("Accommodation", "accommodation"),
    ]
    for label, key in section_map:
        value = str(isl.get(key) or "").strip()
        if not value:
            continue
        section_chunks.append(
            f'  <section class="lp-section"><h2 class="lp-section-title">{html.escape(label)}</h2><p>{html.escape(value)}</p></section>'
        )
    sections_block = "\n".join(section_chunks)

    sources_block = ""
    src_rows = []
    for src in isl.get("sources") or []:
        if not isinstance(src, dict):
            continue
        src_name = html.escape(str(src.get("name") or "Source"))
        src_url = html.escape(str(src.get("url") or ""), quote=True)
        src_ref = html.escape(str(src.get("ref") or ""))
        src_lic = html.escape(str(src.get("licence") or ""))
        if src_url:
            src_rows.append(
                f'<li><a href="{src_url}" rel="noopener" target="_blank">{src_name}</a>'
                f'{f" · {src_ref}" if src_ref else ""}{f" · {src_lic}" if src_lic else ""}</li>'
            )
    if src_rows:
        sources_block = (
            '  <section class="lp-section"><h2 class="lp-section-title">Sources</h2><ul class="lp-list">\n    '
            + "\n    ".join(src_rows)
            + "\n  </ul></section>\n"
        )

    hub = ""
    seg = nation_segment(isl.get("nation"))
    if seg:
        hub = (
            f'  <p class="lp-note">Part of the '
            f'<a href="/islands/{html.escape(seg, quote=True)}/">'
            f"{nation or seg} islands map</a>.</p>\n"
        )

    img_block = ""
    if img:
        img_block = (
            f'  <figure class="lp-media"><img src="{html.escape(img, quote=True)}" '
            f'alt="{name}" width="960" height="540" loading="lazy" decoding="async"/></figure>\n'
        )

    assets = landing_head_assets(depth)

    breadcrumb = ""
    if seg:
        breadcrumb = (
            '<nav class="lp-note" aria-label="Breadcrumb">'
            f'<a href="{html.escape(atlas_href, quote=True)}">Home</a> → '
            f'<a href="/islands/{html.escape(seg, quote=True)}/">{nation or seg}</a> → '
            f"{name}</nav>"
        )

    related_block = ""
    if related_links:
        related_items = "\n".join(
            f'    <li><a href="{html.escape(path, quote=True)}">{html.escape(label)}</a></li>'
            for path, label in related_links[:8]
        )
        related_block = (
            '  <section class="lp-section"><h2 class="lp-section-title">Nearby and related islands</h2>'
            f'<ul class="lp-list">\n{related_items}\n  </ul></section>\n'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{title_esc}</title>
  <meta name="description" content="{desc}"/>
  <link rel="canonical" href="{html.escape(profile_url, quote=True)}"/>
  <meta name="robots" content="index,follow,max-image-preview:large"/>
  <meta property="og:type" content="article"/>
  <meta property="og:title" content="{title_esc}"/>
  <meta property="og:description" content="{desc}"/>
  <meta property="og:url" content="{html.escape(profile_url, quote=True)}"/>
{og_img}  <meta name="twitter:card" content="summary_large_image"/>
  <meta name="twitter:title" content="{title_esc}"/>
  <meta name="twitter:description" content="{desc}"/>
  <link rel="alternate" href="{html.escape(atlas_url, quote=True)}"/>
{assets}
{geo_block}
</head>
<body class="lp">
  <div class="lp-shell">
    <nav class="lp-nav">
      <a class="lp-back" href="{html.escape(atlas_href, quote=True)}">← Atlas</a>
      <a class="lp-brand" href="{html.escape(atlas_href, quote=True)}">Find My Island</a>
    </nav>
    {breadcrumb}
    <header class="lp-hero">
      {nation_line}
      <h1>{name}</h1>
      <p class="lp-lede">{desc}</p>
      <a class="lp-cta" href="{atlas_url}">Open on the map →</a>
    </header>
{img_block}{facts_block}{hub}
{sections_block}
{related_block}
{sources_block}    <p class="lp-note">Last reviewed: {datetime.now(timezone.utc).strftime("%Y-%m-%d")}.</p>
  </div>
</body>
</html>
"""


def legacy_redirect_html(*, new_url: str, atlas_url: str, name: str) -> str:
    new_esc = html.escape(new_url, quote=True)
    atlas_esc = html.escape(atlas_url, quote=True)
    name_esc = html.escape(name, quote=True)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>{name_esc} (moved)</title>
  <link rel="canonical" href="{new_esc}"/>
  <meta name="robots" content="noindex,follow"/>
  <meta http-equiv="refresh" content="0; url={new_esc}"/>
</head>
<body>
  <p>This profile has moved to <a href="{new_esc}">{new_esc}</a>.</p>
  <p><a href="{atlas_esc}">Open in atlas</a></p>
</body>
</html>
"""


# Nation hub → related ferry guide paths (internal links for SEO/GEO).
NATION_FERRY_LINKS: dict[str, list[tuple[str, str]]] = {
    "scotland": [
        ("/ferries/scottish/", "Scottish island ferries"),
        ("/ferries/calmac/", "CalMac ferry map"),
        ("/ferries/hebrides/", "Hebrides ferries"),
        ("/ferries/orkney/", "Orkney ferries"),
        ("/ferries/shetland/", "Shetland ferries"),
    ],
    "ireland": [("/ferries/ireland/", "Ireland island ferries")],
    "northern-ireland": [("/ferries/northern-ireland/", "Northern Ireland ferries")],
    "wales": [("/ferries/welsh/", "Wales ferries")],
    "england": [
        ("/ferries/isle-of-wight/", "Isle of Wight ferries"),
        ("/ferries/isles-of-scilly/", "Isles of Scilly boats"),
    ],
    "crown-dependencies": [
        ("/ferries/isle-of-man/", "Isle of Man ferries"),
        ("/ferries/channel-islands/", "Channel Islands ferries"),
    ],
    "isle-of-man": [("/ferries/isle-of-man/", "Isle of Man ferries")],
}


def nation_hub_html(
    *,
    segment: str,
    origin: str,
    atlas_href: str,
    featured_links: list[tuple[str, str]],
    depth: int = 2,
) -> str:
    title = NATION_HUB_TITLE.get(segment, f"{segment} islands map")
    blurb = NATION_HUB_BLURB.get(
        segment, "Explore islands on the Find My Island interactive atlas."
    )
    hub_path = f"/islands/{segment}/"
    hub_url = f"{origin}{hub_path}"
    title_esc = html.escape(title, quote=True)
    blurb_esc = html.escape(blurb, quote=True)
    items = "\n".join(
        f'    <li><a href="{html.escape(path, quote=True)}">{html.escape(label)}</a></li>'
        for path, label in featured_links
    )
    ferry_rows = NATION_FERRY_LINKS.get(segment) or [("/ferries/", "All ferry guides")]
    ferry_items = "\n".join(
        f'    <li><a href="{html.escape(path, quote=True)}">{html.escape(label)}</a></li>'
        for path, label in ferry_rows
    )
    other_nations = "\n".join(
        f'    <li><a href="/islands/{seg}/">{html.escape(NATION_HUB_TITLE.get(seg, seg))}</a></li>'
        for seg in (
            "scotland",
            "ireland",
            "england",
            "wales",
            "northern-ireland",
            "crown-dependencies",
            "isle-of-man",
        )
        if seg != segment
    )
    jsonld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": title,
        "description": blurb,
        "url": hub_url,
        "isPartOf": {"@type": "WebSite", "name": "Find My Island", "url": origin + "/"},
    }
    assets = landing_head_assets(depth)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{title_esc} | Find My Island</title>
  <meta name="description" content="{blurb_esc}"/>
  <link rel="canonical" href="{html.escape(hub_url, quote=True)}"/>
  <meta name="robots" content="index,follow"/>
  <meta property="og:type" content="website"/>
  <meta property="og:title" content="{title_esc}"/>
  <meta property="og:description" content="{blurb_esc}"/>
  <meta property="og:url" content="{html.escape(hub_url, quote=True)}"/>
  <script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>
{assets}
</head>
<body class="lp">
  <div class="lp-shell">
    <nav class="lp-nav">
      <a class="lp-back" href="{html.escape(atlas_href, quote=True)}">← Atlas</a>
      <a class="lp-brand" href="{html.escape(atlas_href, quote=True)}">Find My Island</a>
    </nav>
    <header class="lp-hero">
      <p class="lp-kicker">Islands by country</p>
      <h1>{title_esc}</h1>
      <p class="lp-lede">{blurb_esc}</p>
      <a class="lp-cta" href="{html.escape(atlas_href, quote=True)}">Open the map →</a>
    </header>
    <h2 class="lp-section-title">Notable islands</h2>
    <ul class="lp-list">
{items}
    </ul>
    <h2 class="lp-section-title">Ferry guides</h2>
    <ul class="lp-list">
{ferry_items}
    </ul>
    <h2 class="lp-section-title">Other countries</h2>
    <ul class="lp-list">
{other_nations}
    </ul>
  </div>
</body>
</html>
"""


def islands_root_html(*, origin: str, atlas_href: str, depth: int = 1) -> str:
    links = "\n".join(
        f'    <li><a href="/islands/{seg}/">{html.escape(NATION_HUB_TITLE.get(seg, seg))}</a></li>'
        for seg in sorted(set(NATION_SEGMENT.values()))
    )
    url = f"{origin}/islands/"
    assets = landing_head_assets(depth)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Islands by country — map | Find My Island</title>
  <meta name="description" content="Browse islands of Scotland, Ireland, England, Wales, Northern Ireland, and the Crown Dependencies on an interactive map."/>
  <link rel="canonical" href="{html.escape(url, quote=True)}"/>
  <meta name="robots" content="index,follow"/>
{assets}
</head>
<body class="lp">
  <div class="lp-shell">
    <nav class="lp-nav">
      <a class="lp-back" href="{html.escape(atlas_href, quote=True)}">← Atlas</a>
      <a class="lp-brand" href="{html.escape(atlas_href, quote=True)}">Find My Island</a>
    </nav>
    <header class="lp-hero">
      <p class="lp-kicker">Browse</p>
      <h1>Islands by country</h1>
      <p class="lp-lede">Choose a nation map hub, then open any island profile.</p>
      <a class="lp-cta" href="{html.escape(atlas_href, quote=True)}">Open the map →</a>
    </header>
    <ul class="lp-list">
{links}
    </ul>
  </div>
</body>
</html>
"""


def trust_page_html(*, title: str, lede: str, body: list[str], canonical: str, depth: int = 1) -> str:
    assets = landing_head_assets(depth)
    paras = "\n".join(f"    <p>{html.escape(p)}</p>" for p in body)
    title_esc = html.escape(title, quote=True)
    lede_esc = html.escape(lede, quote=True)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{title_esc} | Find My Island</title>
  <meta name="description" content="{lede_esc}"/>
  <link rel="canonical" href="{html.escape(canonical, quote=True)}"/>
  <meta name="robots" content="index,follow"/>
  <meta property="og:type" content="article"/>
  <meta property="og:title" content="{title_esc} | Find My Island"/>
  <meta property="og:description" content="{lede_esc}"/>
  <meta property="og:url" content="{html.escape(canonical, quote=True)}"/>
{assets}
</head>
<body class="lp">
  <div class="lp-shell">
    <nav class="lp-nav">
      <a class="lp-back" href="/">← Atlas</a>
      <a class="lp-brand" href="/">Find My Island</a>
    </nav>
    <header class="lp-hero">
      <h1>{title_esc}</h1>
      <p class="lp-lede">{lede_esc}</p>
    </header>
{paras}
  </div>
</body>
</html>
"""


def collection_specs() -> list[dict[str, str]]:
    return [
        {"slug": "inner-hebrides", "title": "Inner Hebrides islands", "match_archipelago": "Inner Hebrides"},
        {"slug": "outer-hebrides", "title": "Outer Hebrides islands", "match_archipelago": "Outer Hebrides"},
        {"slug": "orkney", "title": "Orkney islands", "match_archipelago": "Orkney"},
        {"slug": "shetland", "title": "Shetland islands", "match_archipelago": "Shetland"},
        {"slug": "isles-of-scilly", "title": "Isles of Scilly", "match_archipelago": "Scilly"},
        {"slug": "channel-islands", "title": "Channel Islands", "match_archipelago": "Channel Islands"},
        {"slug": "aran-islands", "title": "Aran Islands", "match_archipelago": "Aran"},
        {"slug": "loch-lomond", "title": "Islands of Loch Lomond", "match_parent": "Loch Lomond"},
        {"slug": "lough-corrib", "title": "Islands of Lough Corrib", "match_parent": "Lough Corrib"},
        {"slug": "thames-islands", "title": "Islands of the River Thames", "match_parent": "Thames"},
    ]


def _collection_members(islands: list[dict], spec: dict[str, str], paths: dict[str, Any]) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    want_arch = str(spec.get("match_archipelago") or "").lower()
    want_parent = str(spec.get("match_parent") or "").lower()
    for isl in islands:
        iid = str(isl.get("id") or "")
        if not iid:
            continue
        sp = paths.get(iid)
        if not sp:
            continue
        arch = str(isl.get("archipelago") or "").lower()
        parent = str((isl.get("parentWaterBody") or {}).get("name") or "").lower()
        ok = False
        if want_arch and want_arch in arch:
            ok = True
        if want_parent and want_parent in parent:
            ok = True
        if ok:
            rows.append((sp.path, str(isl.get("name") or iid)))
    rows.sort(key=lambda r: r[1].lower())
    return rows


def collection_hub_html(*, title: str, canonical_url: str, items: list[tuple[str, str]], depth: int = 2) -> str:
    assets = landing_head_assets(depth)
    li = "\n".join(
        f'    <li><a href="{html.escape(path, quote=True)}">{html.escape(name)}</a></li>'
        for path, name in items[:250]
    )
    desc = f"Browse mapped islands in this collection on Find My Island."
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{html.escape(title, quote=True)} | Find My Island</title>
  <meta name="description" content="{html.escape(desc, quote=True)}"/>
  <link rel="canonical" href="{html.escape(canonical_url, quote=True)}"/>
  <meta name="robots" content="index,follow"/>
  <meta property="og:type" content="website"/>
  <meta property="og:title" content="{html.escape(title, quote=True)} | Find My Island"/>
  <meta property="og:description" content="{html.escape(desc, quote=True)}"/>
  <meta property="og:url" content="{html.escape(canonical_url, quote=True)}"/>
{assets}
</head>
<body class="lp">
  <div class="lp-shell">
    <nav class="lp-nav">
      <a class="lp-back" href="/">← Atlas</a>
      <a class="lp-brand" href="/">Find My Island</a>
    </nav>
    <header class="lp-hero">
      <h1>{html.escape(title)}</h1>
      <p class="lp-lede">{html.escape(desc)}</p>
      <a class="lp-cta" href="/">Open the map →</a>
    </header>
    <ul class="lp-list">
{li}
    </ul>
  </div>
</body>
</html>
"""

def build_crawl_links_html(
    islands_by_id: dict[str, dict],
    curated: set[str],
    paths: dict,
) -> str:
    ferry_items = "\n".join(
        f'        <li><a href="{p}">{html.escape(FERRY_LABELS.get(p, p))}</a></li>'
        for p in FERRY_PATHS
    )
    nation_items = "\n".join(
        f'        <li><a href="/islands/{seg}/">{html.escape(NATION_HUB_TITLE.get(seg, seg))}</a></li>'
        for seg in (
            "scotland",
            "ireland",
            "england",
            "wales",
            "northern-ireland",
            "crown-dependencies",
            "isle-of-man",
        )
    )
    curated_ids = [iid for iid in islands_by_id if iid in curated]
    curated_ids.sort(key=lambda i: str(islands_by_id[i].get("name") or i).lower())
    island_items = []
    for iid in curated_ids[:40]:
        sp = paths.get(iid)
        href = sp.path if sp else f"/profiles/{iid}.html"
        label = str(islands_by_id[iid].get("name") or iid)
        island_items.append(
            f'        <li><a href="{html.escape(href, quote=True)}">'
            f"{html.escape(label)}</a></li>"
        )
    island_block = "\n".join(island_items)
    trust_items = "\n".join(
        f'        <li><a href="{path}">{html.escape(label)}</a></li>'
        for path, label in TRUST_PAGES.items()
    )
    return f"""{CRAWL_LINKS_MARKER_START}
        <footer class="crawl-links" aria-label="Guides and notable islands">
          <p class="crawl-links__heading">Guides &amp; notable islands</p>
          <div class="crawl-links__grid">
            <section>
              <h3 class="crawl-links__sub">Ferry guides</h3>
              <ul class="crawl-links__list">
{ferry_items}
              </ul>
            </section>
            <section>
              <h3 class="crawl-links__sub">Islands by country</h3>
              <ul class="crawl-links__list">
{nation_items}
              </ul>
            </section>
            <section>
              <h3 class="crawl-links__sub">Notable islands</h3>
              <ul class="crawl-links__list">
{island_block}
              </ul>
            </section>
            <section>
              <h3 class="crawl-links__sub">About this atlas</h3>
              <ul class="crawl-links__list">
{trust_items}
              </ul>
            </section>
          </div>
        </footer>
{CRAWL_LINKS_MARKER_END}"""


def patch_index_crawl_links(fragment: str) -> bool:
    if not INDEX_HTML.is_file():
        print("Skip index crawl links (index.html missing)", flush=True)
        return False
    text = INDEX_HTML.read_text(encoding="utf-8")
    pattern = re.compile(
        re.escape(CRAWL_LINKS_MARKER_START) + r".*?" + re.escape(CRAWL_LINKS_MARKER_END),
        re.DOTALL,
    )
    if not pattern.search(text):
        print(
            "Skip index crawl links (markers not found — add IOB_CRAWL_LINKS_START/END to index.html)",
            flush=True,
        )
        return False
    INDEX_HTML.write_text(pattern.sub(fragment, text, count=1), encoding="utf-8")
    print("Patched index.html crawl links", flush=True)
    return True


def atlas_href_for_depth(depth: int) -> str:
    prefix = "/".join([".."] * depth) if depth else "."
    return f"{prefix}/" if prefix != "." else "./"


def asset_href_for_depth(depth: int, filename: str) -> str:
    prefix = "/".join([".."] * depth) if depth else "."
    return f"{prefix}/{filename}" if prefix != "." else f"./{filename}"


def landing_head_assets(depth: int) -> str:
    styles = html.escape(asset_href_for_depth(depth, "styles.css"), quote=True)
    landing = html.escape(asset_href_for_depth(depth, "landing.css"), quote=True)
    return (
        f'  <link rel="stylesheet" href="{styles}"/>\n'
        f'  <link rel="stylesheet" href="{landing}"/>'
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--site-origin",
        default=os.environ.get("IOB_SITE_ORIGIN", "").rstrip("/"),
        help="Canonical HTTPS origin (no trailing slash). Env: IOB_SITE_ORIGIN.",
    )
    ap.add_argument(
        "--landing-dir",
        type=Path,
        default=None,
        help="Also write legacy profiles/<id>.html redirects (deploy-time; gitignored).",
    )
    ap.add_argument(
        "--skip-index-patch",
        action="store_true",
        help="Do not patch index.html crawl-link block.",
    )
    ap.add_argument(
        "--skip-islands-dir",
        action="store_true",
        help="Do not write /islands/ HTML landings (sitemap/llms only).",
    )
    args = ap.parse_args()

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    islands_by_id = {str(x["id"]): x for x in islands if x.get("id")}
    curated = load_id_set(CURATED)
    featured = load_id_set(FEATURED)
    paths = assign_seo_paths(islands)

    # Persist id → path for frontend tooling / probes
    SEO_PATH_MAP.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "paths": {iid: sp.path for iid, sp in paths.items()},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {SEO_PATH_MAP} ({len(paths)} paths)")

    origin = (args.site_origin or "").rstrip("/")
    write_landings = bool(origin) and not args.skip_islands_dir

    llms = f"""# Find My Island (findmyisland.com)
> The British & Irish Islands Atlas: visual, data-led island profiles with maps, photos, transport context, and provenance.

## Entry points
- Main app: /
- Islands by country: /islands/
- Nation hubs: /islands/scotland/ · /islands/ireland/ · /islands/england/ · /islands/wales/ · /islands/northern-ireland/ · /islands/crown-dependencies/
- Island profile: /islands/{{nation}}/{{slug}}/   (example: /islands/scotland/isle-of-skye/)
- Legacy deep link: /?island=<id> (supported for map state; canonical stays on /islands/…)
- Legacy redirects: /profiles/<id>.html → canonical /islands/… path
- Ferry guides: /ferries/
- Collections: /collections/
- Sitemap: /sitemap.xml

## For machines
- Prefer /islands/{{nation}}/{{slug}}/ in citations and indexing.
- Internal ids remain stable in `data/islands.json` and legacy `?island=` query params.
- Data licensing: follow `docs/ETHICS.md` and per-field provenance in the dataset.

## Generated
- sitemap.xml (when site origin configured)
- This file (llms.txt)
"""
    (ROOT / "llms.txt").write_text(llms, encoding="utf-8")
    print(f"Wrote {ROOT / 'llms.txt'}")

    if not origin:
        print(
            "Skip sitemap.xml / robots.txt (set --site-origin or IOB_SITE_ORIGIN).",
            flush=True,
        )
    else:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        islands_mtime = _mtime_ymd(ISLANDS)
        core_entries: list[tuple[str, float, str]] = [(f"{origin}/", 1.0, _mtime_ymd(INDEX_HTML))]
        core_entries.append((f"{origin}/islands/", 0.9, today))
        for seg in sorted(set(NATION_SEGMENT.values())):
            core_entries.append((f"{origin}/islands/{seg}/", 0.88, today))
        for path in TRUST_PAGES:
            core_entries.append((f"{origin}{path}", 0.75, today))
        core_entries.append((f"{origin}/collections/", 0.78, today))
        for path in FERRY_PATHS:
            core_entries.append((f"{origin}{path}", 0.72, _mtime_ymd(ROOT / path.strip("/") / "index.html")))

        sorted_islands = sort_islands_for_sitemap(islands, curated, featured)
        island_editorial: list[tuple[str, float, str]] = []
        island_bulk: list[tuple[str, float, str]] = []
        for isl in sorted_islands:
            iid = isl.get("id")
            if not iid:
                continue
            pri = island_priority(str(iid), isl, curated, featured)
            sp = paths.get(str(iid))
            loc = f"{origin}{sp.path}" if sp else f"{origin}/?island={iid}"
            row = (loc, pri, _island_lastmod(isl, islands_mtime))
            if str(iid) in curated or str(iid) in featured:
                island_editorial.append(row)
            else:
                island_bulk.append(row)

        ferry_entries: list[tuple[str, float, str]] = [
            (f"{origin}{path}", 0.72, _mtime_ymd(ROOT / path.strip("/") / "index.html"))
            for path in FERRY_PATHS
        ]

        collection_entries: list[tuple[str, float, str]] = []
        for spec in collection_specs():
            collection_entries.append((f"{origin}/collections/{spec['slug']}/", 0.68, today))
        collection_entries.append((f"{origin}/collections/flagship-islands/", 0.82, today))

        write_urlset(ROOT / "sitemap-core.xml", core_entries)
        write_urlset(ROOT / "sitemap-islands-editorial.xml", island_editorial)
        write_urlset(ROOT / "sitemap-islands.xml", island_bulk)
        write_urlset(ROOT / "sitemap-ferries-verified.xml", ferry_entries)
        write_urlset(ROOT / "sitemap-collections.xml", collection_entries)
        write_sitemap_index(
            ROOT / "sitemap.xml",
            [
                (f"{origin}/sitemap-core.xml", today),
                (f"{origin}/sitemap-islands-editorial.xml", islands_mtime),
                (f"{origin}/sitemap-islands.xml", islands_mtime),
                (f"{origin}/sitemap-ferries-verified.xml", today),
                (f"{origin}/sitemap-collections.xml", today),
            ],
        )
        print(
            "Wrote sitemap index + segmented sitemaps "
            f"(core={len(core_entries)}, editorial={len(island_editorial)}, islands={len(island_bulk)})"
        )

        robots = f"""User-agent: *
Allow: /

# Nation hubs and name-slug island profiles
Allow: /islands/

# Legacy profile redirects (noindex; keep for old links)
Allow: /profiles/

Sitemap: {origin}/sitemap.xml
"""
        (ROOT / "robots.txt").write_text(robots, encoding="utf-8")
        print("Wrote robots.txt")

    if write_landings:
        # Clear previous generated tree under islands/ (keep safe)
        if ISLANDS_DIR.exists():
            import shutil

            shutil.rmtree(ISLANDS_DIR)
        ISLANDS_DIR.mkdir(parents=True, exist_ok=True)

        (ISLANDS_DIR / "index.html").write_text(
            islands_root_html(origin=origin, atlas_href="/"),
            encoding="utf-8",
        )
        # Trust and governance pages.
        trust_page_payloads: dict[str, tuple[str, str, list[str]]] = {
            "/about/": (
                "About Find My Island",
                "Find My Island is a data-led atlas of the British and Irish islands.",
                [
                    "We map sea, loch, lake, and river islands across the UK, Ireland, and Crown Dependencies.",
                    "The project combines curated editorial records with open geographic datasets and transparent provenance.",
                    "Our goal is to make island geography easier to explore, verify, and cite.",
                ],
            ),
            "/methodology/": (
                "Methodology",
                "How islands are defined, included, and verified in the atlas.",
                [
                    "Inclusion criteria, confidence labels, and source provenance are documented and versioned.",
                    "Every island record links back to public references such as OpenStreetMap, Wikidata, or curated research.",
                    "See docs/ETHICS.md and docs/DATA-SCHEMA.md for full policy and field-level definitions.",
                ],
            ),
            "/editorial-policy/": (
                "Editorial policy",
                "How we maintain quality, updates, and attribution.",
                [
                    "We prioritize verifiable facts, clear attribution, and respectful naming across languages.",
                    "Machine-generated enrichments are reviewed before being treated as canonical editorial content.",
                    "When uncertain, records are marked with confidence and preserved transparently.",
                ],
            ),
            "/corrections/": (
                "Corrections",
                "How to report a mistake or suggest an improvement.",
                [
                    "If you spot an error in naming, geography, transport, or imagery, please send a correction.",
                    "Include source links whenever possible so updates can be verified quickly.",
                    "Significant changes are logged in the public session and state documentation.",
                ],
            ),
            "/sources-licensing/": (
                "Sources and licensing",
                "Licences, provenance, and data attribution policy.",
                [
                    "We only ingest and redistribute data with clear open licensing and required attribution.",
                    "Each record stores source metadata such as licence, URL, and retrieval date.",
                    "Licensing and ethics guardrails are documented in docs/ETHICS.md.",
                ],
            ),
            "/contact/": (
                "Contact",
                "Get in touch about corrections, partnerships, or data questions.",
                [
                    "Use the atlas contribution flow for island fixes and community updates.",
                    "For editorial, licensing, or research requests, contact the Find My Island team via repository issues.",
                ],
            ),
            "/dataset/": (
                "Dataset",
                "Versioned atlas dataset metadata, definitions, and reuse guidance.",
                [
                    "The dataset includes island geometry references, metadata, and provenance fields.",
                    "Machine-readable outputs include islands.json, islands_index.json, nation shards, and SEO path maps.",
                    "Use source citations and licence obligations when reusing derived outputs.",
                ],
            ),
        }
        for rel_path, (title, lede, body) in trust_page_payloads.items():
            out_dir = ROOT / rel_path.strip("/")
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "index.html").write_text(
                trust_page_html(
                    title=title,
                    lede=lede,
                    body=body,
                    canonical=f"{origin}{rel_path}",
                ),
                encoding="utf-8",
            )

        # Group curated/featured per nation for hub lists
        by_seg: dict[str, list[tuple[str, str, str, float]]] = {}
        for iid, sp in paths.items():
            isl = islands_by_id.get(iid)
            if not isl:
                continue
            score = island_priority(iid, isl, curated, featured)
            by_seg.setdefault(sp.nation_segment, []).append(
                (iid, sp.path, str(isl.get("name") or iid), score)
            )

        for seg, items in by_seg.items():
            items.sort(key=lambda t: (-t[3], t[2].lower()))
            featured_links = [(p, n) for _, p, n, _ in items[:48]]
            hub_dir = ISLANDS_DIR / seg
            hub_dir.mkdir(parents=True, exist_ok=True)
            (hub_dir / "index.html").write_text(
                nation_hub_html(
                    segment=seg,
                    origin=origin,
                    atlas_href="/",
                    featured_links=featured_links,
                ),
                encoding="utf-8",
            )

        collections_root = ROOT / "collections"
        collections_root.mkdir(parents=True, exist_ok=True)
        (collections_root / "index.html").write_text(
            trust_page_html(
                title="Island collections",
                lede="Curated collection pages for major archipelagos and water-body groups.",
                body=["Browse collection hubs such as the Hebrides, Orkney, Shetland, Aran Islands, and Thames islands."],
                canonical=f"{origin}/collections/",
                depth=1,
            ),
            encoding="utf-8",
        )
        for spec in collection_specs():
            members = _collection_members(islands, spec, paths)
            out_dir = collections_root / spec["slug"]
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "index.html").write_text(
                collection_hub_html(
                    title=spec["title"],
                    canonical_url=f"{origin}/collections/{spec['slug']}/",
                    items=members,
                ),
                encoding="utf-8",
            )
        flagship_rows: list[tuple[str, str, float]] = []
        for iid, sp in paths.items():
            isl = islands_by_id.get(iid)
            if not isl:
                continue
            score = island_priority(iid, isl, curated, featured)
            if iid in curated or iid in featured:
                flagship_rows.append((sp.path, str(isl.get("name") or iid), score))
        flagship_rows.sort(key=lambda r: (-r[2], r[1].lower()))
        flagship_links = [(path, name) for path, name, _ in flagship_rows[:30]]
        (collections_root / "flagship-islands").mkdir(parents=True, exist_ok=True)
        (collections_root / "flagship-islands" / "index.html").write_text(
            collection_hub_html(
                title="Flagship island profiles",
                canonical_url=f"{origin}/collections/flagship-islands/",
                items=flagship_links,
            ),
            encoding="utf-8",
        )

        n = 0
        for isl in islands:
            iid = isl.get("id")
            if not iid:
                continue
            sp = paths.get(str(iid))
            if not sp:
                continue
            out = ROOT / sp.index_rel
            out.parent.mkdir(parents=True, exist_ok=True)
            # Depth: islands/nation/slug/index.html → ../../../
            page = profile_page_html(
                isl,
                origin=origin,
                atlas_href=atlas_href_for_depth(3),
                profile_path=sp.path,
                title=page_title(isl),
                related_links=[
                    (path, label)
                    for rid, path, label, _ in by_seg.get(sp.nation_segment, [])
                    if rid != str(iid)
                ][:8],
                depth=3,
            )
            out.write_text(page, encoding="utf-8")
            n += 1
        print(f"Wrote {n} island landings under islands/ + nation hubs")

    if args.landing_dir and origin:
        landing = Path(args.landing_dir)
        if not landing.is_absolute():
            landing = ROOT / landing
        landing.mkdir(parents=True, exist_ok=True)
        depth = len(landing.relative_to(ROOT).parts)
        atlas = atlas_href_for_depth(depth)
        n = 0
        for isl in islands:
            iid = isl.get("id")
            if not iid:
                continue
            sp = paths.get(str(iid))
            new_url = f"{origin}{sp.path}" if sp else f"{atlas}?island={iid}"
            atlas_url = f"{atlas}?island={html.escape(str(iid), quote=True)}"
            page = legacy_redirect_html(
                new_url=new_url,
                atlas_url=atlas_url,
                name=str(isl.get("name") or iid),
            )
            (landing / f"{iid}.html").write_text(page, encoding="utf-8")
            n += 1
        print(f"Wrote {n} legacy redirect pages under {landing}/")

    if origin and not args.skip_index_patch:
        patch_index_crawl_links(
            build_crawl_links_html(islands_by_id, curated, paths)
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
