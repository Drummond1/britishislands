#!/usr/bin/env python3
"""Build SEO landing pages stitched from ``data/ferries.json``.

For each meaningful slice of the ferry network we emit a self-contained
HTML page at ``ferries/<slug>/index.html``. The pages live alongside the
main static site and link back to the relevant island detail panels (via
``/?island=<id>``).

Each page emits:
  • Standard ``<title>``, ``<meta name="description">`` for SEO.
  • Open Graph + Twitter Card meta for social previews.
  • A Schema.org ``TouristTrip`` JSON-LD block per ferry route.
  • A short editorial intro + a card list of all matching routes.

Run::

    python3 scripts/generate_ferry_landing_pages.py
"""

from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FERRIES_PATH = ROOT / "data" / "ferries.json"
TERMINALS_PATH = ROOT / "data" / "ferry_terminals.json"
OPERATORS_PATH = ROOT / "data" / "operators.json"
ISLANDS_PATH = ROOT / "data" / "islands.json"
OUT_DIR = ROOT / "ferries"

GTM_HEAD = """  <!-- Google Tag Manager -->
  <script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':
  new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],
  j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
  'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
  })(window,document,'script','dataLayer','GTM-M2T6LN5J');</script>
  <!-- End Google Tag Manager -->"""

GTM_BODY_NOSCRIPT = """  <!-- Google Tag Manager (noscript) -->
  <noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-M2T6LN5J"
  height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>
  <!-- End Google Tag Manager (noscript) -->"""


# (slug, title, description, filter_fn(route, term_lookup, island_lookup) -> bool)
def build_landing_specs():
    return [
        ("hebrides",
         "Ferries to the Hebrides",
         "Every published ferry route to the Outer Hebrides, Inner Hebrides and the Small Isles - operators, sailing times, vessels and journey lengths.",
         lambda r, T, I: _route_touches_archipelago(r, T, I, {"Outer Hebrides", "Inner Hebrides", "Small Isles"})),
        ("orkney",
         "Ferries to Orkney",
         "Every published ferry route to the Orkney Islands - NorthLink, Pentland, John o' Groats, Orkney Ferries inter-island service.",
         lambda r, T, I: _route_touches_archipelago(r, T, I, {"Orkney"})),
        ("shetland",
         "Ferries to Shetland",
         "Every published ferry route to and within Shetland - NorthLink Aberdeen-Lerwick + the Shetland inter-island council network.",
         lambda r, T, I: _route_touches_archipelago(r, T, I, {"Shetland"})),
        ("isle-of-wight",
         "Ferries to the Isle of Wight",
         "All Solent ferries to the Isle of Wight - Wightlink, Red Funnel, Hovertravel - with route times, vessel types and seasonality.",
         lambda r, T, I: _route_touches_island_name(r, T, I, "isle of wight")),
        ("isles-of-scilly",
         "Ferries & boats to the Isles of Scilly",
         "Scillonian III and inter-island launches connecting the Isles of Scilly with Penzance and each other.",
         lambda r, T, I: _route_touches_island_name(r, T, I, "scilly")),
        ("isle-of-man",
         "Ferries to the Isle of Man",
         "Isle of Man Steam Packet sailings from Heysham, Liverpool, Belfast and Dublin to Douglas.",
         lambda r, T, I: r.get("operatorId") == "iom-steam-packet"),
        ("channel-islands",
         "Ferries to the Channel Islands",
         "Condor Ferries, Manche Iles Express, Sark Shipping and Alderney sea links to Jersey, Guernsey, Sark, Alderney and Herm.",
         lambda r, T, I: r.get("operatorId") in {"condor-ferries", "manche-iles", "sark-shipping", "alderney-bailiwick"}),
        ("scottish",
         "Scottish island ferries",
         "Every ferry route to a Scottish island - CalMac, NorthLink, Pentland, Western Ferries, Highland Council, Orkney Ferries, Shetland Inter-Island.",
         lambda r, T, I: _route_touches_nation(r, T, I, "Scotland")),
        ("welsh",
         "Welsh island ferries",
         "Ferry and boat services to Welsh islands - Caldey, Bardsey, Skomer, Skokholm and Grassholm.",
         lambda r, T, I: _route_touches_nation(r, T, I, "Wales")),
        ("ireland",
         "Irish island ferries",
         "Every published ferry route to a Republic of Ireland island - Aran, Cape Clear, Tory, Inishbofin, Inishturk, Clare, Bere, Sherkin, Spike, Skellig Michael.",
         lambda r, T, I: _route_touches_nation(r, T, I, "Ireland")),
        ("northern-ireland",
         "Northern Irish island ferries",
         "Rathlin Island Ferry from Ballycastle and the Strangford-Portaferry car ferry.",
         lambda r, T, I: _route_touches_nation(r, T, I, "Northern Ireland")),
        ("calmac",
         "CalMac ferry routes",
         "Every Caledonian MacBrayne route - sailing times, vessels and seasonality across the west coast of Scotland and the Hebrides.",
         lambda r, T, I: r.get("operatorId") == "calmac"),
    ]


# ---------------------------------------------------------------------------

def _term_island(t):
    return (t.get("islandId") or "") if t else ""

def _island_lookup_archipelago(I, ipath):
    if not ipath:
        return ""
    isl = I.get(ipath)
    if not isl:
        return ""
    return isl.get("archipelago") or ""

def _island_lookup_nation(I, ipath):
    if not ipath:
        return ""
    isl = I.get(ipath)
    if not isl:
        return ""
    return isl.get("nation") or ""

def _route_touches_archipelago(route, term_lookup, island_lookup, want):
    for side in ("from", "to"):
        t = term_lookup.get(route["terminals"][side]["terminalId"])
        arch = _island_lookup_archipelago(island_lookup, _term_island(t) or route["terminals"][side].get("islandId"))
        if arch and any(a in arch for a in want):
            return True
    return False

def _route_touches_island_name(route, term_lookup, island_lookup, name_substr):
    name_substr = name_substr.lower()
    for side in ("from", "to"):
        t = term_lookup.get(route["terminals"][side]["terminalId"])
        ipath = _term_island(t) or route["terminals"][side].get("islandId")
        isl = island_lookup.get(ipath)
        if isl and name_substr in (isl.get("name", "") or "").lower():
            return True
        if t and name_substr in (t.get("name", "") or "").lower():
            return True
    return False

def _route_touches_nation(route, term_lookup, island_lookup, nation):
    for side in ("from", "to"):
        t = term_lookup.get(route["terminals"][side]["terminalId"])
        ipath = _term_island(t) or route["terminals"][side].get("islandId")
        n = _island_lookup_nation(island_lookup, ipath)
        if n == nation:
            return True
        if t and t.get("country") == nation:
            return True
    return False


# ---------------------------------------------------------------------------

def _operator_label(op):
    if not op:
        return "Unknown operator"
    return op.get("shortName") or op.get("name") or "Unknown operator"


def _terminal_name(t, island_lookup=None):
    """Human label; avoid publishing raw 'OSM node …' placeholders."""
    if not t:
        return "—"
    name = (t.get("names") or {}).get("en") or t.get("name") or ""
    if name and not str(name).startswith("OSM "):
        return name
    iid = t.get("islandId")
    if island_lookup and iid and iid in island_lookup:
        iname = island_lookup[iid].get("name") or iid
        return f"{iname} terminal"
    return "Ferry terminal"


def _route_card(route, term_lookup, operator_lookup, island_lookup):
    op = operator_lookup.get(route.get("operatorId"))
    op_label = _operator_label(op)
    t_from = term_lookup.get(route["terminals"]["from"]["terminalId"])
    t_to = term_lookup.get(route["terminals"]["to"]["terminalId"])
    dur = route.get("durationMinutes")
    dur_str = ""
    if dur:
        h, m = divmod(int(dur), 60)
        dur_str = f"{h}h {m}m" if h else f"{m} min"

    # Detect island endpoint (to link back to the main app)
    island_link = ""
    for side, term in (("from", t_from), ("to", t_to)):
        ipath = _term_island(term) or route["terminals"][side].get("islandId")
        if ipath and ipath in island_lookup:
            isl = island_lookup[ipath]
            seo = isl.get("seoPath") or f"/?island={ipath}"
            label = isl.get("name") or "island"
            island_link = (
                f'<a href="{html.escape(seo)}" class="lp-card__island-link">'
                f"Open {html.escape(label)} ↗</a>"
            )
            break

    return f"""
    <article class="lp-card">
      <header class="lp-card__head">
        <span class="lp-card__op">{html.escape(op_label)}</span>
        <h3 class="lp-card__title">{html.escape(_terminal_name(t_from, island_lookup))} → {html.escape(_terminal_name(t_to, island_lookup))}</h3>
      </header>
      <ul class="lp-card__meta">
        <li>{html.escape(route.get("type") or "—")}</li>
        <li>{html.escape(route.get("seasonality") or "—")}</li>
        <li>{html.escape(route.get("frequencyBand") or "—")}</li>
        {f"<li>{html.escape(dur_str)}</li>" if dur_str else ""}
      </ul>
      {f'<p class="lp-card__notes">{html.escape(route["timetable"]["notes"])}</p>' if route.get("timetable", {}).get("notes") else ""}
      <div class="lp-card__actions">
        {f'<a class="lp-card__book" href="{html.escape(route["bookingUrl"])}" target="_blank" rel="noopener">Book / timetable ↗</a>' if route.get("bookingUrl") else ""}
        {island_link}
      </div>
    </article>
    """


def _route_jsonld(route, term_lookup, operator_lookup, island_lookup=None):
    op = operator_lookup.get(route.get("operatorId"))
    t_from = term_lookup.get(route["terminals"]["from"]["terminalId"]) or {}
    t_to = term_lookup.get(route["terminals"]["to"]["terminalId"]) or {}
    obj = {
        "@context": "https://schema.org",
        "@type": "TouristTrip",
        "name": route.get("name")
        or f"{_terminal_name(t_from, island_lookup)} to {_terminal_name(t_to, island_lookup)} ferry",
        "description": (route.get("timetable") or {}).get("notes", "") or "Published ferry route.",
        "provider": ({
            "@type": "Organization",
            "name": op.get("name"),
            "url": op.get("homepage"),
        } if op else None),
        "departureLocation": ({
            "@type": "Place",
            "name": _terminal_name(t_from, island_lookup),
            "geo": {"@type": "GeoCoordinates", "latitude": t_from.get("lat"), "longitude": t_from.get("lon")},
        } if t_from else None),
        "arrivalLocation": ({
            "@type": "Place",
            "name": _terminal_name(t_to, island_lookup),
            "geo": {"@type": "GeoCoordinates", "latitude": t_to.get("lat"), "longitude": t_to.get("lon")},
        } if t_to else None),
        "url": route.get("bookingUrl"),
    }
    # Drop empty fields.
    return {k: v for k, v in obj.items() if v}


def _render_page(spec, routes, term_lookup, operator_lookup, island_lookup):
    slug, title, desc, _ = spec
    body_intro = f"<p class=\"lp-intro\">{html.escape(desc)}</p>"
    cards = "\n".join(_route_card(r, term_lookup, operator_lookup, island_lookup) for r in routes)
    jsonlds = "\n".join(
        f'<script type="application/ld+json">{json.dumps(_route_jsonld(r, term_lookup, operator_lookup, island_lookup), ensure_ascii=False)}</script>'
        for r in routes
    )
    canonical = f"https://www.findmyisland.com/ferries/{slug}/"
    today = date.today().isoformat()
    page_title = f"{title} — ferry map | Find My Island"
    return f"""<!doctype html>
<html lang="en">
<head>
{GTM_HEAD}
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(page_title)}</title>
  <meta name="description" content="{html.escape(desc)}" />
  <link rel="canonical" href="{html.escape(canonical)}" />
  <meta property="og:title" content="{html.escape(page_title)}" />
  <meta property="og:description" content="{html.escape(desc)}" />
  <meta property="og:type" content="website" />
  <meta property="og:url" content="{html.escape(canonical)}" />
  <meta name="twitter:card" content="summary_large_image" />
  <link rel="stylesheet" href="../../styles.css" />
  <style>
    body {{ padding: 24px; max-width: 960px; margin: 0 auto; }}
    .lp-back {{ display: inline-block; margin-bottom: 16px; color: var(--accent); text-decoration: none; }}
    .lp-back:hover {{ text-decoration: underline; }}
    h1 {{ margin: 8px 0 12px; font-size: 28px; }}
    .lp-intro {{ color: var(--text-soft); font-size: 16px; max-width: 720px; }}
    .lp-cards {{ display: grid; gap: 14px; margin-top: 18px; }}
    .lp-card {{
      background: var(--bg-soft);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 12px 14px;
    }}
    .lp-card__head {{ display: flex; flex-direction: column; gap: 2px; margin-bottom: 6px; }}
    .lp-card__op {{ font-size: 12px; color: var(--text-soft); text-transform: uppercase; letter-spacing: 0.04em; font-weight: 600; }}
    .lp-card__title {{ margin: 0; font-size: 17px; color: var(--text); }}
    .lp-card__meta {{ list-style: none; padding: 0; margin: 4px 0 6px; display: flex; flex-wrap: wrap; gap: 6px; }}
    .lp-card__meta li {{ background: var(--bg-elev); border: 1px solid var(--border); border-radius: 999px; padding: 3px 10px; font-size: 11px; color: var(--text-soft); }}
    .lp-card__notes {{ font-size: 13px; color: var(--text-soft); margin: 4px 0; }}
    .lp-card__actions {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 6px; }}
    .lp-card__book {{ background: var(--accent); color: #0a1320; font-weight: 600; padding: 6px 12px; border-radius: 6px; text-decoration: none; font-size: 13px; }}
    .lp-card__book:hover {{ background: #7ec4ff; }}
    .lp-card__island-link {{ color: var(--accent); font-size: 13px; padding: 6px 0; }}
    footer {{ margin-top: 32px; color: var(--text-muted); font-size: 12px; }}
  </style>
</head>
<body>
{GTM_BODY_NOSCRIPT}
  <a class="lp-back" href="../../">← Back to the atlas</a>
  <h1>{html.escape(title)}</h1>
  {body_intro}
  <section class="lp-cards">{cards}</section>
  <footer>
    {len(routes)} routes shown · last regenerated {today}.
    Data merged from CalMac & Traveline Scotland GTFS, OpenStreetMap, operator timetables and hand-curated entries.
  </footer>
  {jsonlds}
</body>
</html>
"""


def main() -> int:
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from seo_paths import assign_seo_paths

    ferries_doc = json.loads(FERRIES_PATH.read_text(encoding="utf-8"))
    terms_doc = json.loads(TERMINALS_PATH.read_text(encoding="utf-8"))
    ops_doc = json.loads(OPERATORS_PATH.read_text(encoding="utf-8"))
    islands = json.loads(ISLANDS_PATH.read_text(encoding="utf-8"))
    paths = assign_seo_paths(islands)
    for isl in islands:
        sp = paths.get(str(isl.get("id") or ""))
        if sp:
            isl["seoPath"] = sp.path

    routes = ferries_doc.get("routes", [])
    term_lookup = {t["id"]: t for t in terms_doc.get("terminals", [])}
    operator_lookup = {o["id"]: o for o in ops_doc.get("operators", [])}
    island_lookup = {i["id"]: i for i in islands}

    OUT_DIR.mkdir(exist_ok=True)
    index_links = []

    for spec in build_landing_specs():
        slug, title, desc, fn = spec
        sub_routes = [r for r in routes if fn(r, term_lookup, island_lookup)]
        if not sub_routes:
            continue
        d = OUT_DIR / slug
        d.mkdir(exist_ok=True)
        html_str = _render_page(spec, sub_routes, term_lookup, operator_lookup, island_lookup)
        (d / "index.html").write_text(html_str, encoding="utf-8")
        index_links.append((slug, title, len(sub_routes), desc))
        print(f"  + /ferries/{slug}/  ({len(sub_routes)} routes)")

    # Build top-level /ferries/index.html
    today = date.today().isoformat()
    cards = "\n".join(
        f'<a class="lp-card lp-card--link" href="{html.escape(slug)}/"><h3>{html.escape(title)}</h3>'
        f'<p>{html.escape(desc)}</p>'
        f'<p class="lp-card__count">{n} routes</p></a>'
        for slug, title, n, desc in index_links
    )
    index_html = f"""<!doctype html>
<html lang="en">
<head>
{GTM_HEAD}
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Ferries to the islands of Britain &amp; Ireland | Isles of Britain</title>
  <meta name="description" content="A hand-curated catalogue of every published ferry route to islands in the British Isles, the Crown Dependencies and the Republic of Ireland." />
  <link rel="canonical" href="/ferries/" />
  <link rel="stylesheet" href="../styles.css" />
  <style>
    body {{ padding: 24px; max-width: 1080px; margin: 0 auto; }}
    .lp-back {{ display: inline-block; margin-bottom: 16px; color: var(--accent); text-decoration: none; }}
    h1 {{ font-size: 30px; margin: 8px 0 12px; }}
    .lp-cards {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 14px; margin-top: 18px; }}
    .lp-card {{ background: var(--bg-soft); border: 1px solid var(--border); border-radius: 10px; padding: 14px; color: var(--text); text-decoration: none; }}
    .lp-card h3 {{ margin: 0 0 6px; font-size: 17px; color: var(--accent); }}
    .lp-card p {{ margin: 0; font-size: 13px; color: var(--text-soft); }}
    .lp-card__count {{ margin-top: 8px; font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }}
    .lp-card:hover {{ border-color: var(--accent); }}
  </style>
</head>
<body>
{GTM_BODY_NOSCRIPT}
  <a class="lp-back" href="../">← Back to the atlas</a>
  <h1>Ferries to the islands of Britain and Ireland</h1>
  <p>Browse every published ferry route by region or by operator. Each page is rebuilt from <code>data/ferries.json</code> and emits Schema.org structured data per route.</p>
  <section class="lp-cards">{cards}</section>
  <footer style="margin-top:32px;color:var(--text-muted);font-size:12px;">Last regenerated {today}.</footer>
</body>
</html>
"""
    (OUT_DIR / "index.html").write_text(index_html, encoding="utf-8")
    print(f"  + /ferries/  (index, {len(index_links)} pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
