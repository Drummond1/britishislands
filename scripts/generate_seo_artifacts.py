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
    title: str,
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
        geo_block = f"""
  <script type="application/ld+json">{{
    "@context": "https://schema.org",
    "@type": "Island",
    "name": {json.dumps(str(isl.get("name") or iid))},
    "description": {json.dumps(str(desc_raw)[:500])},
    "url": {json.dumps(profile_url)},
    "geo": {{"@type": "GeoCoordinates", "latitude": {lat}, "longitude": {lng}}}{address}
  }}</script>"""

    nation_line = f"<p>{nation}</p>" if nation else ""

    facts: list[str] = []
    if isl.get("type"):
        facts.append(f"<li><strong>Type:</strong> {html.escape(str(isl['type']))} island</li>")
    if isl.get("archipelago"):
        facts.append(
            f"<li><strong>Group:</strong> {html.escape(str(isl['archipelago']))}</li>"
        )
    if isl.get("areaKm2"):
        facts.append(
            f"<li><strong>Area:</strong> {html.escape(str(isl['areaKm2']))} km²</li>"
        )
    if isl.get("population") is not None and isl.get("population") != "":
        facts.append(
            f"<li><strong>Population:</strong> {html.escape(str(isl['population']))}</li>"
        )
    if lat is not None and lng is not None:
        facts.append(
            f"<li><strong>Location:</strong> {lat}, {lng} "
            f"(open on the interactive map)</li>"
        )
    facts_block = ""
    if facts:
        facts_block = (
            "  <h2>Key facts</h2>\n  <ul>\n    "
            + "\n    ".join(facts)
            + "\n  </ul>\n"
        )

    hub = ""
    seg = nation_segment(isl.get("nation"))
    if seg:
        hub = (
            f'  <p>Part of the <a href="/islands/{html.escape(seg, quote=True)}/">'
            f"{nation or seg} islands map</a>.</p>\n"
        )

    img_block = ""
    if img:
        img_block = (
            f'  <p><img src="{html.escape(img, quote=True)}" alt="{name}" '
            f'width="640" loading="lazy"/></p>\n'
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
{geo_block}
</head>
<body>
  <header>
    <p><a href="{html.escape(atlas_href, quote=True)}">← Isles of Britain atlas</a></p>
    <h1>{name}</h1>
    {nation_line}
    <p>{desc}</p>
  </header>
{img_block}{facts_block}{hub}  <p><a href="{atlas_url}">Open interactive map profile →</a></p>
  <p><small>Canonical profile for search engines and AI crawlers. Map opens on demand — no auto-redirect.</small></p>
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


def nation_hub_html(
    *,
    segment: str,
    origin: str,
    atlas_href: str,
    featured_links: list[tuple[str, str]],
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
</head>
<body>
  <header>
    <p><a href="{html.escape(atlas_href, quote=True)}">← Isles of Britain atlas</a></p>
    <h1>{title_esc}</h1>
    <p>{blurb_esc}</p>
  </header>
  <p><a href="{html.escape(atlas_href, quote=True)}">Open the interactive map →</a></p>
  <h2>Notable islands</h2>
  <ul>
{items}
  </ul>
</body>
</html>
"""


def islands_root_html(*, origin: str, atlas_href: str) -> str:
    links = "\n".join(
        f'    <li><a href="/islands/{seg}/">{html.escape(NATION_HUB_TITLE.get(seg, seg))}</a></li>'
        for seg in sorted(set(NATION_SEGMENT.values()))
    )
    url = f"{origin}/islands/"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Islands by country — map | Find My Island</title>
  <meta name="description" content="Browse islands of Scotland, Ireland, England, Wales, Northern Ireland, and the Crown Dependencies on an interactive map."/>
  <link rel="canonical" href="{html.escape(url, quote=True)}"/>
  <meta name="robots" content="index,follow"/>
</head>
<body>
  <header>
    <p><a href="{html.escape(atlas_href, quote=True)}">← Isles of Britain atlas</a></p>
    <h1>Islands by country</h1>
    <p>Choose a nation map hub, then open any island profile.</p>
  </header>
  <ul>
{links}
  </ul>
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

    llms = f"""# Isles of Britain (findmyisland.com)
> Visual atlas of islands in and around the United Kingdom, Ireland, and Crown Dependencies (sea, lake, and river), with maps, photos, and transport context.

## Entry points
- Main app: /
- Islands by country: /islands/
- Nation hubs: /islands/scotland/ · /islands/ireland/ · /islands/england/ · /islands/wales/ · /islands/northern-ireland/ · /islands/crown-dependencies/
- Island profile (static HTML for crawlers): /islands/{{nation}}/{{slug}}/   (example: /islands/scotland/isle-of-skye/)
- Island profile (interactive): /?island=<id>   (example: ?island=isle-of-skye)
- Legacy redirects: /profiles/<id>.html → canonical /islands/… path
- Ferry guides: /ferries/
- Sitemap: /sitemap.xml

## For machines
- Prefer /islands/{{nation}}/{{slug}}/ in sitemaps and citations; it links to the live atlas.
- Internal ids remain stable in `data/islands.json` and `?island=` query params.
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
        entries: list[tuple[str, float]] = [(f"{origin}/", 1.0)]
        entries.append((f"{origin}/islands/", 0.9))
        for seg in sorted(set(NATION_SEGMENT.values())):
            entries.append((f"{origin}/islands/{seg}/", 0.88))
        for path in FERRY_PATHS:
            entries.append((f"{origin}{path}", 0.72))

        sorted_islands = sort_islands_for_sitemap(islands, curated, featured)
        for isl in sorted_islands:
            iid = isl.get("id")
            if not iid:
                continue
            pri = island_priority(str(iid), isl, curated, featured)
            sp = paths.get(str(iid))
            if sp:
                entries.append((f"{origin}{sp.path}", pri))
            else:
                entries.append((f"{origin}/?island={iid}", pri))

        write_urlset(ROOT / "sitemap.xml", entries)
        print(f"Wrote sitemap.xml ({len(entries)} URLs; nation-slug paths)")

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

        # Group curated/featured per nation for hub lists
        by_seg: dict[str, list[tuple[str, str, float]]] = {}
        for iid, sp in paths.items():
            isl = islands_by_id.get(iid)
            if not isl:
                continue
            score = island_priority(iid, isl, curated, featured)
            by_seg.setdefault(sp.nation_segment, []).append(
                (sp.path, str(isl.get("name") or iid), score)
            )

        for seg, items in by_seg.items():
            items.sort(key=lambda t: (-t[2], t[1].lower()))
            featured_links = [(p, n) for p, n, _ in items[:24]]
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
