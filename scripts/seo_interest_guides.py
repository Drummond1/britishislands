"""Crawlable guides for the interest filters.

These pages are the query-shaped layer search and answer engines can cite:
castles, whisky, tidal islands, islands for sale, wildlife, books,
traditions, and film, art and music. Counts and titles come from
``data/interest_index.json``. The ledes state the inclusion rules already
used by the atlas. They do not add claims the index does not support.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INTEREST_INDEX = ROOT / "data" / "interest_index.json"

# Shown sentences per island. Further titles stay as links so a long
# film/art list does not repeat every source paragraph.
_SUMMARY_CAP = 2
_TITLE_CAP = 8

# Confirmed false attachments in docs/fact-check/2026-10-26-claims.md.
# They stay in the atlas until that correction lands. Citable guides omit them
# so a search or answer engine does not repeat the mistake.
HELD_BACK: set[tuple[str, str, str]] = {
    ("island-castles", "arran", "Airds Castle"),
    ("island-castles", "osm-way-56059556", "Torksey Castle"),
    ("island-castles", "osm-way-205500003", "Calvay Castle"),
    ("island-castles", "osm-way-767535808", "Cloughoughter Castle"),
    ("island-castles", "thames-oxford", "Oxford Castle"),
    ("for-sale", "osm-relation-14940681", "Gasker Island — uninhabited (Galbraith)"),
    ("for-sale", "osm-way-200912404", "Insh Island — Savills auction lot (90 acres)"),
    ("film-art-music", "osm-relation-15671047", "The Great Silkie of Sule Skerry"),
    ("film-art-music", "mainland-shetland", "King Orfeo"),
    ("film-art-music", "arran", "Ailsa Craig"),
    ("film-art-music", "mainland-orkney", "Peter Pratt"),
    ("film-art-music", "mainland-orkney", "Julian Beale"),
    ("film-art-music", "mainland-orkney", "Absinthe"),
    ("film-art-music", "mainland-orkney", "Lee Taylor"),
    ("film-art-music", "islay", "Alexander Mackay"),
    ("film-art-music", "osm-relation-380685", "John MacAulay"),
    ("film-art-music", "osm-relation-380685", "Neil Ferguson"),
    ("film-art-music", "osm-relation-380685", "Donald Morrison"),
    ("film-art-music", "osm-relation-3148462", "Douglas Montgomery"),
}

# The stored sentence is false. This replacement is the part the fact-check held.
# The whole island entry is the false claim (a road causeway described as a drying crossing).
HELD_BACK_ISLANDS: set[tuple[str, str]] = {
    ("tidal-islands", "osm-relation-13146202"),  # Baleshare
    ("tidal-islands", "osm-way-4557019"),  # Mahee Island
}

SUMMARY_REPLACEMENTS: dict[tuple[str, str, str], str] = {
    (
        "unusual-wildlife",
        "osm-relation-12913146",
        "blonde hedgehog",
    ): "A blonde colour form of the European hedgehog lives on Alderney. The species itself is widespread.",
}


class _Fmt(dict):
    def __missing__(self, key: str) -> str:
        return "0"


def fill(template: str, values: dict[str, Any]) -> str:
    return template.format_map(_Fmt({k: values[k] for k in values}))


def first_sentence(text: str, limit: int = 280) -> str:
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return ""
    match = re.search(r"\.(?:\s|$)", cleaned)
    if match and match.end() >= 40:
        cleaned = cleaned[: match.end()].strip()
    if len(cleaned) > limit:
        cleaned = cleaned[: limit - 1].rsplit(" ", 1)[0].rstrip(".,;:") + "…"
    return cleaned


@dataclass
class CitedRow:
    title: str
    summary: str
    source_url: str
    facet: str = ""


@dataclass
class GuideIsland:
    island_id: str
    name: str
    path: str
    nation: str
    rows: list[CitedRow] = field(default_factory=list)


@dataclass
class GuidePage:
    slug: str
    title: str
    h1: str
    nav_label: str
    description: str
    lede: str
    method: str
    faqs: list[tuple[str, str]]
    islands: list[GuideIsland]
    row_count: int
    held_back: int
    priority: float

    @property
    def path(self) -> str:
        return f"/collections/{self.slug}/"


# Order is the order on /collections/ and in llms.txt.
# Ledes are original. {islands}, {rows}, and {facet_*} are filled from the index.
GUIDE_SPECS: list[dict[str, Any]] = [
    {
        "slug": "island-castles",
        "title": "Islands with castles in Britain and Ireland",
        "h1": "Islands with castles",
        "nav_label": "Islands with castles",
        "priority": 0.84,
        "description": (
            "Islands in Britain and Ireland with a castle on the island itself. "
            "The mainland, Martello towers, brochs, and country houses are left out."
        ),
        "lede": (
            "{islands} islands in Britain and Ireland have a castle the sources place "
            "on the island itself — {rows} castles in all. The mainland of Great Britain "
            "and the island of Ireland are not listed. Martello towers, brochs, and "
            "country houses are left out."
        ),
        "method": (
            "A castle is kept only when Wikidata, Wikipedia, OpenStreetMap, Canmore, "
            "the National Heritage List for England, Cadw, or the Archaeological Survey "
            "of Ireland places it on that island. The sentence under a name is the "
            "source line that makes the link."
        ),
        "faqs": [
            (
                "How many islands in Britain and Ireland have a castle?",
                "This guide lists {islands} islands and {rows} castles. It counts a castle on an island, not a castle on the mainland of Britain or Ireland.",
            ),
            (
                "Are brochs and Martello towers included?",
                "No. Martello towers, brochs, and country houses are left out.",
            ),
            (
                "Where does the list come from?",
                "From cited records in Wikidata, Wikipedia, OpenStreetMap, and the national heritage lists. Each entry links to its source.",
            ),
        ],
    },
    {
        "slug": "whisky-distilleries",
        "title": "Whisky islands of Britain and Ireland",
        "h1": "Whisky islands",
        "nav_label": "Whisky islands",
        "priority": 0.84,
        "description": (
            "Islands with a whisky distillery, a silent still, or a whisky story "
            "a cited source places on that island."
        ),
        "lede": (
            "{islands} islands have a whisky or whiskey record a source places on the "
            "island: {facet_distillery} distillery entries, {facet_silent} silent stills, "
            "{facet_story} stories, and {facet_planned} that are named but not yet in "
            "production. A still is listed only when the source names the island."
        ),
        "method": (
            "Rows cover a working distillery, a closed still, a story, or a planned "
            "still. The page does not list every bottle, brand, or bar. Islay, the "
            "Hebrides, Orkney, and other isles use the same cited rows."
        ),
        "faqs": [
            (
                "Which Scottish islands make whisky?",
                "The distillery rows on this page. An island appears only where a source places a still, a silent distillery, or a whisky story on it.",
            ),
            (
                "Are closed distilleries included?",
                "Yes. {facet_silent} silent stills are listed separately from the {facet_distillery} distillery entries.",
            ),
            (
                "Is Irish whiskey included?",
                "Only when a source places the whiskey on an island in this atlas.",
            ),
        ],
    },
    {
        "slug": "tidal-islands",
        "title": "Tidal islands of Britain and Ireland",
        "h1": "Tidal islands",
        "nav_label": "Tidal islands",
        "priority": 0.82,
        "description": (
            "Islands joined to other land at low tide and cut off at high tide. "
            "No crossing times."
        ),
        "lede": (
            "{islands} islands that are joined to other land at low tide and cut off "
            "at high tide, taken from a published list of tidal islands. This is not "
            "every island the atlas marks as tidal, and it does not give crossing times."
        ),
        "method": (
            "Each island is one the English Wikipedia article on tidal islands names, "
            "and that this atlas can place. A permanent causeway, a footbridge, or a "
            "name that is not an island in the atlas stays off the list."
        ),
        "faqs": [
            (
                "What is a tidal island?",
                "Land you can reach on foot at low tide, and that is surrounded by water at high tide.",
            ),
            (
                "How many tidal islands are listed here?",
                "This guide lists {islands}. A broader tidal tag in the atlas is not used for this page.",
            ),
            (
                "Does this page say when it is safe to cross?",
                "No. It does not give crossing times.",
            ),
        ],
    },
    {
        "slug": "for-sale",
        "title": "Islands for sale in Britain and Ireland",
        "h1": "Islands for sale",
        "nav_label": "Islands for sale",
        "priority": 0.8,
        "description": (
            "Islands in Britain and Ireland with a broker listing. The link leaves "
            "this site. Check the broker before treating a listing as current."
        ),
        "lede": (
            "{islands} islands with a broker listing the atlas can point to. The link "
            "leaves this site. A listing can sell, so check the broker before you "
            "treat it as still on the market."
        ),
        "method": (
            "Listings are outbound links to the broker that published them. This page "
            "does not copy asking prices. Sold islands already removed from the atlas "
            "stay off the list."
        ),
        "faqs": [
            (
                "Can I buy an island in Scotland or Ireland?",
                "The islands on this page have a broker page the atlas links to. The broker is the place to ask what is still for sale.",
            ),
            (
                "Are prices listed here?",
                "No. Open the broker for the asking price and what the sale includes.",
            ),
            (
                "Is a listing a guarantee the island is still for sale?",
                "No. Treat each entry as a lead and check the broker.",
            ),
        ],
    },
    {
        "slug": "unusual-wildlife",
        "title": "Rare wildlife on British and Irish islands",
        "h1": "Rare wildlife",
        "nav_label": "Rare wildlife",
        "priority": 0.8,
        "description": (
            "Rare, endemic, or remarkable species a source places on an island "
            "in Britain or Ireland. No nest sites or colony coordinates."
        ),
        "lede": (
            "{islands} islands with a rare, endemic, or otherwise remarkable species "
            "a source places there — {rows} species in all. The page names the island "
            "and the species. It does not give nest sites or advice on how to visit."
        ),
        "method": (
            "A species is listed only when the source paragraph names the island. "
            "Colony coordinates, nest counts, and visit instructions are not published."
        ),
        "faqs": [
            (
                "Which British and Irish islands have rare wildlife?",
                "The {islands} islands on this page, covering {rows} cited species.",
            ),
            (
                "Are breeding sites shown?",
                "No. Nest sites and colony coordinates are not on this page.",
            ),
            (
                "Is every seabird colony included?",
                "No. Only a species a source singles out on that island.",
            ),
        ],
    },
    {
        "slug": "island-books",
        "title": "Books set on British and Irish islands",
        "h1": "Books set on islands",
        "nav_label": "Books set on islands",
        "priority": 0.78,
        "description": (
            "Novels, memoirs, and story collections whose source sets the book "
            "on an island in Britain or Ireland."
        ),
        "lede": (
            "{islands} islands are the setting of a novel, memoir, or story collection "
            "in this guide — {rows} books. A book is included only when its article "
            "sets the story on that island."
        ),
        "method": (
            "“Inspired by”, “based on”, and “filmed on” are not enough. The sentence "
            "under a title is the one that places the book on the island."
        ),
        "faqs": [
            (
                "Which books are set on Scottish islands?",
                "Open the Scottish islands in this list. Each title links to the source that places the book there.",
            ),
            (
                "Are films included on this page?",
                "No. Films, art, and music have their own guide.",
            ),
            (
                "How many books are listed?",
                "{rows} books across {islands} islands.",
            ),
        ],
    },
    {
        "slug": "local-traditions",
        "title": "Traditions of the islands of Britain and Ireland",
        "h1": "Island traditions",
        "nav_label": "Island traditions",
        "priority": 0.78,
        "description": (
            "Festivals, dances, food, and crafts a source places on an island "
            "in Britain or Ireland."
        ),
        "lede": (
            "{islands} islands with a custom, festival, dance, or craft a source "
            "places on that island — {rows} traditions. The note is the sentence "
            "that ties the custom to the place."
        ),
        "method": (
            "Monastic pilgrimages, island breeds, and a bare legend are not listed. "
            "Each custom needs a source sentence that describes the practice and "
            "names the island."
        ),
        "faqs": [
            (
                "What island traditions are recorded here?",
                "{rows} customs on {islands} islands: festivals, dances, food, and crafts the source places on that island.",
            ),
            (
                "Are island breeds included?",
                "No. Breeds, pilgrimages, and a legend with no described custom are left out.",
            ),
            (
                "Where is Up Helly Aa?",
                "On the Shetland entry, when the source places the festival on that island.",
            ),
        ],
    },
    {
        "slug": "unusual-news",
        "title": "Unusual news from the islands of Britain and Ireland",
        "h1": "Unusual news",
        "nav_label": "Unusual news",
        "priority": 0.78,
        "description": (
            "Strange events a news report places on an island in Britain or Ireland, "
            "with a link to the article."
        ),
        "lede": (
            "{islands} islands where a report records something strange — {rows} stories. "
            "Each note is a short account of the event, and the link goes to the article. "
            "The picture is of the place or the thing the report is about."
        ),
        "method": (
            "A story is kept when the report places the event on that island. "
            "The wording here is not the article. Great Britain and Ireland are not listed. "
            "Private addresses and grave locations are not published."
        ),
        "faqs": [
            (
                "What counts as unusual news?",
                "A reported event on that island: a declaration of independence, a mystery, names that appeared, or another one-off.",
            ),
            (
                "Are the articles copied here?",
                "No. Each note is a short original account, with a link to the report.",
            ),
            (
                "How many stories are listed?",
                "{rows} stories across {islands} islands.",
            ),
        ],
    },
    {
        "slug": "film-art-music",
        "title": "Film, art and music on British and Irish islands",
        "h1": "Film, art and music",
        "nav_label": "Film, art and music",
        "priority": 0.76,
        "description": (
            "Films, artworks, and music a cited source connects to an island "
            "in Britain or Ireland."
        ),
        "lede": (
            "{islands} islands tied to a film, an artwork, or a piece of music — "
            "{rows} cited works ({facet_artwork} artworks, {facet_music} music, "
            "{facet_film} films). Each row names the work and the source that "
            "connects it to the island."
        ),
        "method": (
            "A work is kept when the source connects it to that island. A shared "
            "name, a portrait of someone who once visited, or a picture of a "
            "different place is left out."
        ),
        "faqs": [
            (
                "Which films are connected to British and Irish islands?",
                "The film rows on this page. {facet_film} films are cited, alongside {facet_artwork} artworks and {facet_music} pieces of music.",
            ),
            (
                "Why is a painting listed under an island?",
                "Because the source says the work depicts that island, or files it with art of that island.",
            ),
            (
                "How many works are listed?",
                "{rows} across {islands} islands.",
            ),
        ],
    },
]


def load_interest_index(path: Path | None = None) -> dict[str, Any] | None:
    src = path or INTEREST_INDEX
    if not src.is_file():
        return None
    data = json.loads(src.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def _listing_url(island: dict, title: str) -> str:
    """Match a for-sale highlight to the broker URL already on the island. No prices."""
    listings = island.get("propertyListings") or []
    if not isinstance(listings, list):
        return ""
    want = title.strip().lower()
    fallback = ""
    for listing in listings:
        if not isinstance(listing, dict):
            continue
        url = str(listing.get("url") or "").strip()
        if not url:
            continue
        label = str(listing.get("title") or "").strip().lower()
        if not fallback:
            fallback = url
        if label and (label == want or label in want or want in label):
            return url
    return fallback if len([x for x in listings if isinstance(x, dict) and x.get("url")]) == 1 else ""


def _rows_for(stories: dict[str, Any], island_id: str) -> list[CitedRow]:
    raw = stories.get(island_id) or []
    if not isinstance(raw, list):
        return []
    rows: list[CitedRow] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        rows.append(
            CitedRow(
                title=title,
                summary=first_sentence(str(item.get("summary") or "")),
                source_url=str(item.get("sourceUrl") or "").strip(),
                facet=str(item.get("facet") or "").strip().lower(),
            )
        )
    return rows


def assemble_guides(
    index: dict[str, Any],
    islands_by_id: dict[str, dict],
    paths: dict[str, Any],
) -> list[GuidePage]:
    members = index.get("members") if isinstance(index.get("members"), dict) else {}
    stories_root = index.get("stories") if isinstance(index.get("stories"), dict) else {}
    highlights_root = index.get("highlights") if isinstance(index.get("highlights"), dict) else {}
    pages: list[GuidePage] = []
    for spec in GUIDE_SPECS:
        slug = spec["slug"]
        story_map = stories_root.get(slug) if isinstance(stories_root.get(slug), dict) else {}
        highlight_map = highlights_root.get(slug) if isinstance(highlights_root.get(slug), dict) else {}
        member_ids = members.get(slug) if isinstance(members.get(slug), list) else []
        ordered_ids: list[str] = []
        seen: set[str] = set()
        for iid in list(story_map.keys()) + [str(x) for x in member_ids]:
            iid = str(iid)
            if not iid or iid in seen:
                continue
            seen.add(iid)
            ordered_ids.append(iid)

        islands: list[GuideIsland] = []
        row_count = 0
        held_back = 0
        for iid in ordered_ids:
            isl = islands_by_id.get(iid)
            sp = paths.get(iid)
            if not isl or not sp:
                continue
            rows = _rows_for(story_map, iid)
            if not rows:
                titles = highlight_map.get(iid) or []
                if isinstance(titles, list):
                    rows = [
                        CitedRow(
                            title=str(title).strip(),
                            summary="",
                            source_url=_listing_url(isl, str(title)),
                        )
                        for title in titles
                        if str(title).strip()
                    ]
            if (slug, iid) in HELD_BACK_ISLANDS:
                held_back += len(rows) or 1
                continue
            kept: list[CitedRow] = []
            for row in rows:
                key = (slug, iid, row.title)
                if key in HELD_BACK:
                    held_back += 1
                    continue
                replacement = SUMMARY_REPLACEMENTS.get(key)
                if replacement:
                    row = CitedRow(
                        title=row.title,
                        summary=replacement,
                        source_url=row.source_url,
                        facet=row.facet,
                    )
                kept.append(row)
            rows = kept
            if not rows:
                continue
            row_count += len(rows)
            islands.append(
                GuideIsland(
                    island_id=iid,
                    name=str(isl.get("name") or iid),
                    path=sp.path,
                    nation=str(isl.get("nation") or ""),
                    rows=rows,
                )
            )
        islands.sort(key=lambda row: (-len(row.rows), row.name.lower()))
        facets: dict[str, int] = {}
        for island in islands:
            for row in island.rows:
                if row.facet:
                    facets[row.facet] = facets.get(row.facet, 0) + 1
        values: dict[str, Any] = {
            "islands": len(islands),
            "rows": row_count,
        }
        for facet, count in facets.items():
            values[f"facet_{facet}"] = count
        pages.append(
            GuidePage(
                slug=slug,
                title=spec["title"],
                h1=spec["h1"],
                nav_label=spec["nav_label"],
                description=fill(spec["description"], values),
                lede=fill(spec["lede"], values),
                method=fill(spec["method"], values),
                faqs=[(fill(q, values), fill(a, values)) for q, a in spec["faqs"]],
                islands=islands,
                row_count=row_count,
                held_back=held_back,
                priority=float(spec["priority"]),
            )
        )
    return pages


def guides_for_island(pages: list[GuidePage]) -> dict[str, list[dict[str, Any]]]:
    """Island id → guide links and up to four cited titles, for profile pages."""
    out: dict[str, list[dict[str, Any]]] = {}
    for page in pages:
        for island in page.islands:
            out.setdefault(island.island_id, []).append(
                {
                    "href": page.path,
                    "label": page.nav_label,
                    "titles": [row.title for row in island.rows[:4]],
                }
            )
    return out


def _json_script(data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    return f'  <script type="application/ld+json">{payload}</script>'


def render_guide_html(*, page: GuidePage, origin: str, assets: str, reviewed: str) -> str:
    canonical = f"{origin}{page.path}"
    item_list = []
    for position, island in enumerate(page.islands[:50], start=1):
        item_list.append(
            {
                "@type": "ListItem",
                "position": position,
                "name": island.name,
                "url": f"{origin}{island.path}",
            }
        )
    graph = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": 1,
                        "name": "Find My Island",
                        "item": f"{origin}/",
                    },
                    {
                        "@type": "ListItem",
                        "position": 2,
                        "name": "Guides",
                        "item": f"{origin}/collections/",
                    },
                    {
                        "@type": "ListItem",
                        "position": 3,
                        "name": page.h1,
                        "item": canonical,
                    },
                ],
            },
            {
                "@type": "CollectionPage",
                "name": page.title,
                "headline": page.h1,
                "description": page.description,
                "url": canonical,
                "dateModified": reviewed,
                "isPartOf": {
                    "@type": "WebSite",
                    "name": "Find My Island",
                    "url": f"{origin}/",
                },
                "mainEntity": {
                    "@type": "ItemList",
                    "numberOfItems": len(page.islands),
                    "itemListElement": item_list,
                },
            },
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": question,
                        "acceptedAnswer": {"@type": "Answer", "text": answer},
                    }
                    for question, answer in page.faqs
                ],
            },
        ],
    }

    island_html: list[str] = []
    for island in page.islands:
        shown = island.rows[:_TITLE_CAP]
        cite_items: list[str] = []
        for index, row in enumerate(shown):
            title = html.escape(row.title)
            if row.source_url:
                title = (
                    f'<a href="{html.escape(row.source_url, quote=True)}" '
                    f'rel="noopener noreferrer">{title}</a>'
                )
            summary = ""
            if index < _SUMMARY_CAP and row.summary:
                summary = f" — {html.escape(row.summary)}"
            cite_items.append(f"<li>{title}{summary}</li>")
        cites = ""
        if cite_items:
            cites = (
                '<ul class="lp-guide__cites">\n      '
                + "\n      ".join(cite_items)
                + "\n    </ul>"
            )
        extra = len(island.rows) - len(shown)
        extra_html = ""
        if extra > 0:
            extra_html = (
                f'<p class="lp-note"><a href="/?island={html.escape(island.island_id, quote=True)}">'
                f"Open {html.escape(island.name)} on the atlas</a> for {extra} more.</p>"
            )
        meta_bits = [bit for bit in (island.nation, f"{len(island.rows)} cited" if island.rows else "") if bit]
        meta = f'<p class="lp-guide__meta">{html.escape(" · ".join(meta_bits))}</p>' if meta_bits else ""
        island_html.append(
            f'  <article class="lp-guide" id="{html.escape(island.island_id, quote=True)}">\n'
            f'    <h2 class="lp-guide__name"><a href="{html.escape(island.path, quote=True)}">'
            f"{html.escape(island.name)}</a></h2>\n"
            f"    {meta}\n"
            f"    {cites}\n"
            f"    {extra_html}\n"
            "  </article>"
        )

    faq_html = "\n".join(
        "    <details class=\"lp-faq\">\n"
        f"      <summary>{html.escape(question)}</summary>\n"
        f"      <p>{html.escape(answer)}</p>\n"
        "    </details>"
        for question, answer in page.faqs
    )
    held_note = ""
    if page.held_back:
        held_note = (
            f'<p class="lp-note">{page.held_back} '
            f'{"row was" if page.held_back == 1 else "rows were"} left off this page '
            "because the cited source does not place them on that island.</p>"
        )
    count_line = f"{len(page.islands)} islands"
    if page.row_count:
        count_line += f" · {page.row_count} cited"
    map_href = f"/?interest={html.escape(page.slug, quote=True)}"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{html.escape(page.title, quote=True)} | Find My Island</title>
  <meta name="description" content="{html.escape(page.description, quote=True)}"/>
  <link rel="canonical" href="{html.escape(canonical, quote=True)}"/>
  <meta name="robots" content="index,follow,max-image-preview:large"/>
  <meta property="og:type" content="website"/>
  <meta property="og:site_name" content="Find My Island"/>
  <meta property="og:title" content="{html.escape(page.title, quote=True)} | Find My Island"/>
  <meta property="og:description" content="{html.escape(page.description, quote=True)}"/>
  <meta property="og:url" content="{html.escape(canonical, quote=True)}"/>
  <meta name="twitter:card" content="summary"/>
  <meta name="twitter:title" content="{html.escape(page.title, quote=True)}"/>
  <meta name="twitter:description" content="{html.escape(page.description, quote=True)}"/>
{assets}
{_json_script(graph)}
</head>
<body class="lp">
  <div class="lp-shell lp-shell--wide">
    <nav class="lp-nav">
      <a class="lp-back" href="/collections/">← Guides</a>
      <a class="lp-brand" href="/">Find My Island</a>
    </nav>
    <nav class="lp-note" aria-label="Breadcrumb"><a href="/">Home</a> → <a href="/collections/">Guides</a> → {html.escape(page.h1)}</nav>
    <header class="lp-hero">
      <p class="lp-kicker">Guide · {html.escape(count_line)}</p>
      <h1>{html.escape(page.h1)}</h1>
      <p class="lp-lede">{html.escape(page.lede)}</p>
      <a class="lp-cta" href="{map_href}">Open this list on the map →</a>
      <a class="lp-cta lp-cta--ghost" href="/">All islands</a>
    </header>
    <section class="lp-section">
      <h2 class="lp-section-title">How this list is made</h2>
      <p>{html.escape(page.method)}</p>
      <p class="lp-note">The sentence under a title is taken from the linked source. Cite this page as Find My Island, “{html.escape(page.h1)}”, {html.escape(canonical)}, retrieved {html.escape(reviewed)}.</p>
      {held_note}
    </section>
    <section class="lp-section">
      <h2 class="lp-section-title">Questions</h2>
{faq_html}
    </section>
    <section class="lp-section">
      <h2 class="lp-section-title">The islands</h2>
{chr(10).join(island_html)}
    </section>
  </div>
</body>
</html>
"""


def render_collections_index_html(
    *,
    origin: str,
    assets: str,
    guides: list[GuidePage],
    other_hubs: list[tuple[str, str, str]],
) -> str:
    """other_hubs: (href, title, blurb)."""
    canonical = f"{origin}/collections/"
    guide_items = "\n".join(
        "    <li><a href=\"{href}\"><strong>{title}</strong></a>"
        "<span>{blurb}</span></li>".format(
            href=html.escape(page.path, quote=True),
            title=html.escape(page.h1),
            blurb=html.escape(page.description),
        )
        for page in guides
    )
    hub_items = "\n".join(
        "    <li><a href=\"{href}\"><strong>{title}</strong></a>"
        "<span>{blurb}</span></li>".format(
            href=html.escape(href, quote=True),
            title=html.escape(title),
            blurb=html.escape(blurb),
        )
        for href, title, blurb in other_hubs
    )
    item_list = [
        {
            "@type": "ListItem",
            "position": index,
            "name": page.h1,
            "url": f"{origin}{page.path}",
        }
        for index, page in enumerate(guides, start=1)
    ]
    graph = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "Island guides",
        "description": "Guides to castles, whisky, tidal islands, islands for sale, wildlife, books, traditions, and film, art and music.",
        "url": canonical,
        "isPartOf": {"@type": "WebSite", "name": "Find My Island", "url": f"{origin}/"},
        "mainEntity": {
            "@type": "ItemList",
            "numberOfItems": len(guides),
            "itemListElement": item_list,
        },
    }
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Island guides | Find My Island</title>
  <meta name="description" content="Guides to British and Irish islands: castles, whisky, tidal islands, islands for sale, wildlife, books, traditions, and film, art and music."/>
  <link rel="canonical" href="{html.escape(canonical, quote=True)}"/>
  <meta name="robots" content="index,follow"/>
  <meta property="og:type" content="website"/>
  <meta property="og:title" content="Island guides | Find My Island"/>
  <meta property="og:description" content="Castles, whisky, tidal islands, islands for sale, wildlife, books, and traditions — each list cites its source."/>
  <meta property="og:url" content="{html.escape(canonical, quote=True)}"/>
{assets}
{_json_script(graph)}
</head>
<body class="lp">
  <div class="lp-shell lp-shell--wide">
    <nav class="lp-nav">
      <a class="lp-back" href="/">← Atlas</a>
      <a class="lp-brand" href="/">Find My Island</a>
    </nav>
    <header class="lp-hero">
      <p class="lp-kicker">Find My Island</p>
      <h1>Island guides</h1>
      <p class="lp-lede">Lists you can cite: a castle on the island, a whisky still, a tidal crossing, a book set there. Each guide says what was left out, and links the source.</p>
    </header>
    <section class="lp-section">
      <h2 class="lp-section-title">Guides</h2>
      <ul class="lp-hubs">
{guide_items}
      </ul>
    </section>
    <section class="lp-section">
      <h2 class="lp-section-title">Archipelagos and waters</h2>
      <ul class="lp-hubs">
{hub_items}
      </ul>
    </section>
  </div>
</body>
</html>
"""


def render_llms_txt(pages: list[GuidePage]) -> str:
    guide_lines = []
    for page in pages:
        cited = f", {page.row_count} cited" if page.row_count else ""
        guide_lines.append(
            f"- {page.h1}: {page.path} ({len(page.islands)} islands{cited}). {page.description}"
        )
    guides = "\n".join(guide_lines)
    return f"""# Find My Island (findmyisland.com)
> The British and Irish islands atlas. Cite a guide below for a list. Cite /islands/{{nation}}/{{slug}}/ for one island.

## Guides
{guides}
- All guides: /collections/

## One island
- Pattern: /islands/{{nation}}/{{slug}}/
- Example: /islands/scotland/isle-of-skye/
- Do not cite /?island= URLs. Those open the map. The canonical page is the /islands/ path.

## By country
- /islands/scotland/ — Scottish islands map
- /islands/ireland/ — Irish islands map
- /islands/england/ — English islands map
- /islands/wales/ — Welsh islands map
- /islands/northern-ireland/ — Northern Ireland islands map
- /islands/ — all countries

## How the atlas is made
- What counts as an island: /methodology/
- Sources and licences: /sources-licensing/
- Corrections: /corrections/
- Dataset: /dataset/
- About: /about/

## For machines
- Prefer the guide URL for a list, and the island path for a single place.
- Sentences on a guide are taken from the linked source. Do not treat a guide as a price list or a crossing timetable.
- Sitemap: /sitemap.xml
"""
