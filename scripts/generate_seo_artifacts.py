#!/usr/bin/env python3
"""
Generate crawlers / GEO-friendly artifacts for the static atlas.

Outputs (when --site-origin is set):
  - sitemap.xml — home, ferry guides, static profile pages (preferred for indexing)
  - robots.txt — allows all, points to sitemap

Always written:
  - llms.txt — project summary for AI crawlers

Optional:
  - --landing-dir DIR — static HTML per island (profiles/<id>.html on deploy)
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
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
CURATED = DATA / "curated.json"
FEATURED = DATA / "featured_islands.json"
INDEX_HTML = ROOT / "index.html"

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


def write_urlset(path: Path, entries: list[tuple[str, float]]) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for loc, priority in entries:
        lines.append("  <url>")
        lines.append(f"    <loc>{xml_escape(loc)}</loc>")
        lines.append(f"    <lastmod>{today}</lastmod>")
        lines.append("    <changefreq>monthly</changefreq>")
        lines.append(f"    <priority>{priority:.2f}</priority>")
        lines.append("  </url>")
    lines.append("</urlset>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def profile_page_html(
    isl: dict,
    *,
    origin: str,
    atlas_href: str,
    profile_path: str,
) -> str:
    iid = isl["id"]
    name = html.escape(str(isl.get("name") or iid), quote=True)
    desc_raw = isl.get("shortDescription") or (
        f"{isl.get('name', '')} — island in {isl.get('nation', 'the British Isles')}."
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
    geo_block = ""
    if lat is not None and lng is not None:
        geo_block = f"""
  <script type="application/ld+json">{{
    "@context": "https://schema.org",
    "@type": "Island",
    "name": {json.dumps(str(isl.get("name") or iid))},
    "description": {json.dumps(str(desc_raw)[:500])},
    "url": {json.dumps(profile_url)},
    "geo": {{"@type": "GeoCoordinates", "latitude": {lat}, "longitude": {lng}}}
  }}</script>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{name} — Isles of Britain</title>
  <meta name="description" content="{desc}"/>
  <link rel="canonical" href="{html.escape(profile_url, quote=True)}"/>
  <meta name="robots" content="index,follow,max-image-preview:large"/>
  <meta property="og:type" content="article"/>
  <meta property="og:title" content="{name} — Isles of Britain"/>
  <meta property="og:description" content="{desc}"/>
  <meta property="og:url" content="{html.escape(profile_url, quote=True)}"/>
{og_img}  <meta name="twitter:card" content="summary_large_image"/>
  <meta name="twitter:title" content="{name} — Isles of Britain"/>
  <meta name="twitter:description" content="{desc}"/>
  <link rel="alternate" href="{html.escape(atlas_url, quote=True)}"/>
  <meta http-equiv="refresh" content="0; url={atlas_url}"/>
{geo_block}
</head>
<body>
  <header>
    <p><a href="{html.escape(atlas_href, quote=True)}">← Isles of Britain atlas</a></p>
    <h1>{name}</h1>
    <p>{desc}</p>
  </header>
  <p><a href="{atlas_url}">Open interactive map profile →</a></p>
  <noscript><p><a href="{atlas_url}">Continue to the atlas</a></p></noscript>
</body>
</html>
"""


def build_crawl_links_html(islands_by_id: dict[str, dict], curated: set[str]) -> str:
    ferry_items = "\n".join(
        f'        <li><a href="{p}">{html.escape(FERRY_LABELS.get(p, p))}</a></li>'
        for p in FERRY_PATHS
    )
    curated_ids = [iid for iid in islands_by_id if iid in curated]
    curated_ids.sort(key=lambda i: str(islands_by_id[i].get("name") or i).lower())
    island_items = "\n".join(
        f'        <li><a href="/profiles/{html.escape(iid, quote=True)}.html">'
        f'{html.escape(str(islands_by_id[iid].get("name") or iid))}</a></li>'
        for iid in curated_ids[:40]
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
              <h3 class="crawl-links__sub">Notable islands</h3>
              <ul class="crawl-links__list">
{island_items}
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
        help="Write profiles/<id>.html static pages (deploy-time; gitignored).",
    )
    ap.add_argument(
        "--skip-index-patch",
        action="store_true",
        help="Do not patch index.html crawl-link block.",
    )
    args = ap.parse_args()

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    islands_by_id = {str(x["id"]): x for x in islands if x.get("id")}
    curated = load_id_set(CURATED)
    featured = load_id_set(FEATURED)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    llms = f"""# Isles of Britain (findmyisland.com)
> Visual atlas of islands in and around the United Kingdom, Ireland, and Crown Dependencies (sea, lake, and river), with maps, photos, and transport context.

## Entry points
- Main app: /
- Island profile (interactive): /?island=<id>   (example: ?island=isle-of-skye)
- Island profile (static HTML for crawlers): /profiles/<id>.html
- Ferry guides: /ferries/
- Sitemap: /sitemap.xml

## For machines
- Prefer /profiles/<id>.html in sitemaps and citations; it links to the live atlas.
- Island ids are stable slugs in `data/islands.json`.
- Data licensing: follow `docs/ETHICS.md` and per-field provenance in the dataset.

## Generated
- sitemap.xml (when site origin configured)
- This file (llms.txt)
"""
    (ROOT / "llms.txt").write_text(llms, encoding="utf-8")
    print(f"Wrote {ROOT / 'llms.txt'}")

    origin = (args.site_origin or "").rstrip("/")
    use_profiles = bool(args.landing_dir and origin)

    if not origin:
        print(
            "Skip sitemap.xml / robots.txt (set --site-origin or IOB_SITE_ORIGIN).",
            flush=True,
        )
    else:
        entries: list[tuple[str, float]] = [(f"{origin}/", 1.0)]
        for path in FERRY_PATHS:
            entries.append((f"{origin}{path}", 0.72))

        sorted_islands = sort_islands_for_sitemap(islands, curated, featured)
        for isl in sorted_islands:
            iid = isl.get("id")
            if not iid:
                continue
            pri = island_priority(str(iid), isl, curated, featured)
            if use_profiles:
                entries.append((f"{origin}/profiles/{iid}.html", pri))
            else:
                entries.append((f"{origin}/?island={iid}", pri))

        write_urlset(ROOT / "sitemap.xml", entries)
        print(f"Wrote sitemap.xml ({len(entries)} URLs; profiles={use_profiles})")

        robots = f"""User-agent: *
Allow: /

# Static island profiles (generated on deploy)
Allow: /profiles/

Sitemap: {origin}/sitemap.xml
"""
        (ROOT / "robots.txt").write_text(robots, encoding="utf-8")
        print("Wrote robots.txt")

    if args.landing_dir and origin:
        landing = Path(args.landing_dir)
        if not landing.is_absolute():
            landing = ROOT / landing
        landing.mkdir(parents=True, exist_ok=True)
        rel = landing.relative_to(ROOT)
        depth = len(rel.parts)
        prefix = "/".join([".."] * depth) if depth else "."
        atlas_href = f"{prefix}/" if prefix != "." else "./"

        n = 0
        for isl in islands:
            iid = isl.get("id")
            if not iid:
                continue
            profile_path = f"/profiles/{iid}.html"
            page = profile_page_html(
                isl,
                origin=origin,
                atlas_href=atlas_href,
                profile_path=profile_path,
            )
            (landing / f"{iid}.html").write_text(page, encoding="utf-8")
            n += 1
        print(f"Wrote {n} profile pages under {landing}/")

    if origin and not args.skip_index_patch:
        patch_index_crawl_links(build_crawl_links_html(islands_by_id, curated))

    _ = today  # reserved for future lastmod on static index meta
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
