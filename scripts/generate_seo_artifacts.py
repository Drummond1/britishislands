#!/usr/bin/env python3
"""
Generate crawlers / GEO-friendly artifacts for the static atlas.

Outputs (by default, when --site-origin is set):
  - sitemap.xml — index URL + one entry per island (?island=<id>)
  - robots.txt — allows all, points to sitemap

Always written (no origin required):
  - llms.txt — project summary for AI crawlers (relative URLs)

Optional thin HTML stubs (shareable, crawler-friendly; redirect to atlas):
  - --landing-dir DIR — writes DIR/<island-id>.html

Examples:
  IOB_SITE_ORIGIN=https://example.com python3 scripts/generate_seo_artifacts.py
  python3 scripts/generate_seo_artifacts.py --site-origin https://example.com --landing-dir profiles
"""

from __future__ import annotations

import argparse
import html
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"


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
        help="If set, write one minimal HTML file per island that redirects to ?island=",
    )
    args = ap.parse_args()

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    llms = f"""# Isles of Britain
> Visual atlas of islands in and around the United Kingdom, Ireland, and Crown Dependencies (sea, lake, and river), with maps, photos, and transport context.

## Entry points
- Main app: /
- Island profile (deep link): /?island=<id>   (example: ?island=isle-of-skye)
- Ferry guides: /ferries/

## For machines
- Prefer linking to /?island=<id> for a specific island. Island ids are stable slugs in `data/islands.json`.
- Data licensing: follow `docs/ETHICS.md` and per-field provenance in the dataset.

## Generated
- sitemap.xml (if site origin configured)
- This file (llms.txt)
"""
    (ROOT / "llms.txt").write_text(llms, encoding="utf-8")
    print(f"Wrote {ROOT / 'llms.txt'}")

    origin = (args.site_origin or "").rstrip("/")
    if not origin:
        print(
            "Skip sitemap.xml / robots.txt (set --site-origin or IOB_SITE_ORIGIN to your public HTTPS URL).",
            flush=True,
        )
    else:
        urls = [f"{origin}/"]
        for isl in islands:
            iid = isl.get("id")
            if not iid:
                continue
            urls.append(f"{origin}/?island={iid}")

        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        ]
        for u in urls:
            lines.append("  <url>")
            lines.append(f"    <loc>{xml_escape(u)}</loc>")
            lines.append(f"    <lastmod>{today}</lastmod>")
            lines.append("    <changefreq>monthly</changefreq>")
            lines.append(
                "    <priority>0.5</priority>" if u.endswith("/") else "    <priority>0.4</priority>"
            )
            lines.append("  </url>")
        lines.append("</urlset>")
        sitemap_path = ROOT / "sitemap.xml"
        sitemap_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Wrote {sitemap_path} ({len(urls)} URLs)")

        robots = f"""User-agent: *
Allow: /

Sitemap: {origin}/sitemap.xml
"""
        (ROOT / "robots.txt").write_text(robots, encoding="utf-8")
        print(f"Wrote {ROOT / 'robots.txt'}")

    if args.landing_dir:
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
            name = html.escape(str(isl.get("name") or iid), quote=True)
            desc = isl.get("shortDescription") or (
                f"{isl.get('name', '')} — island in {isl.get('nation', 'the British Isles')}."
            )
            desc = html.escape(str(desc).replace("\n", " ").strip()[:300], quote=True)
            canon = f"{origin}/?island={iid}" if origin else f"{atlas_href}?island={iid}"
            redir = f"{atlas_href}?island={html.escape(iid, quote=True)}"
            page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{name} — Isles of Britain</title>
  <meta name="description" content="{desc}"/>
  <link rel="canonical" href="{html.escape(canon, quote=True)}"/>
  <meta property="og:title" content="{name} — Isles of Britain"/>
  <meta property="og:description" content="{desc}"/>
  <meta property="og:url" content="{html.escape(canon, quote=True)}"/>
  <meta name="robots" content="index,follow"/>
  <meta http-equiv="refresh" content="0; url={redir}"/>
</head>
<body>
  <p><a href="{redir}">Open {name} in the Isles of Britain atlas →</a></p>
  <noscript><p><a href="{redir}">Continue to the atlas</a></p></noscript>
</body>
</html>
"""
            (landing / f"{iid}.html").write_text(page, encoding="utf-8")
            n += 1
        print(f"Wrote {n} landing pages under {landing}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
