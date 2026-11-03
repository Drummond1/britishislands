#!/usr/bin/env python3
"""Regression checks for complete, accurately labelled crawlable guide content."""

from __future__ import annotations

import json
import re
import unittest
from types import SimpleNamespace

from seo_interest_guides import (
    CitedRow,
    GuideIsland,
    GuidePage,
    assemble_guides,
    guides_for_island,
    render_guide_html,
    render_llms_txt,
)


def render(page: GuidePage, reviewed: str | None = None) -> str:
    return render_guide_html(
        page=page, origin="https://www.findmyisland.com", assets="", reviewed=reviewed
    )


def guide(islands: list[GuideIsland], slug: str = "island-books") -> GuidePage:
    return GuidePage(
        slug=slug,
        title="Test island guide",
        h1="Test island guide",
        nav_label="Test guide",
        description="Recorded island connections.",
        lede="Recorded island connections.",
        method="Records from the atlas.",
        faqs=[],
        islands=islands,
        row_count=sum(len(island.rows) for island in islands),
        held_back=0,
        priority=0.8,
    )


def assemble(slug: str, stories: dict, records: dict) -> GuidePage:
    pages = assemble_guides(
        {"stories": {slug: stories}},
        records,
        {iid: SimpleNamespace(path=f"/islands/test/{iid}/") for iid in records},
    )
    return next(page for page in pages if page.slug == slug)


class GuideIntegrityTests(unittest.TestCase):
    def test_profile_links_retain_preview_and_propagate_complete_rows(self) -> None:
        rows = [
            CitedRow(f"Title {n}", f"Recorded summary {n}.", f"https://example.org/{n}")
            for n in range(6)
        ]
        page = guide([GuideIsland("one", "One", "/islands/test/one/", "Scotland", rows)])
        links = guides_for_island([page])["one"]
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["href"], page.path)
        self.assertEqual(links[0]["label"], page.nav_label)
        self.assertEqual(links[0]["titles"], [f"Title {n}" for n in range(4)])
        self.assertEqual(len(links[0]["rows"]), 6)
        self.assertEqual(links[0]["rows"][-1], {
            "title": "Title 5",
            "summary": "Recorded summary 5.",
            "sourceUrl": "https://example.org/5",
        })

    def test_all_rows_and_summaries_remain_in_html(self) -> None:
        rows = [
            CitedRow(
                title=f"Unique title {n}",
                summary=f"Unique evidence sentence {n}.",
                source_url=f"https://example.org/source/{n}",
            )
            for n in range(12)
        ]
        page = guide([GuideIsland("one", "One", "/islands/test/one/", "Scotland", rows)])
        output = render(page)
        self.assertEqual(output.count("<li>"), 12)
        for n in range(12):
            self.assertIn(f'Unique title {n}</a>', output)
            self.assertIn(f"Unique evidence sentence {n}.", output)
            self.assertIn(f'href="https://example.org/source/{n}"', output)
        self.assertIn("<summary>10 more entries for One</summary>", output)
        self.assertNotIn("Open One on the atlas</a> for", output)

    def test_missing_source_is_retained_but_never_counted_as_cited(self) -> None:
        rows = [
            CitedRow("Linked record", "One summary.", "https://example.org/one"),
            CitedRow("Unlinked record", "Another summary.", ""),
        ]
        page = guide([GuideIsland("one", "One", "/islands/test/one/", "Scotland", rows)])
        output = render(page)
        self.assertEqual(page.row_count, 2)
        self.assertEqual(page.source_count, 1)
        self.assertIn("2 entries · 1 with source links", output)
        self.assertIn("Unlinked record", output)
        self.assertIn("(source link not recorded)", output)
        self.assertNotIn("2 cited", output)
        self.assertIn("2 entries, 1 with source links", render_llms_txt([page]))

    def test_build_date_cannot_become_review_or_modified_date(self) -> None:
        page = guide([])
        first = render(page, reviewed="2026-11-02")
        second = render(page, reviewed="2026-11-03")
        self.assertEqual(first, second)
        self.assertNotIn("dateModified", first)
        self.assertNotIn("Last reviewed", first)
        self.assertNotIn("retrieved 2026", first)
        self.assertIn("with the date you accessed it", first)

    def test_structured_list_matches_every_visible_island(self) -> None:
        islands = [
            GuideIsland(str(n), f"Island {n}", f"/islands/test/{n}/", "Scotland", [])
            for n in range(60)
        ]
        output = render(guide(islands))
        payload = re.search(r'application/ld\+json">(.*?)</script>', output, re.S)
        self.assertIsNotNone(payload)
        graph = json.loads(payload.group(1))["@graph"]
        collection = next(node for node in graph if node["@type"] == "CollectionPage")
        listing = collection["mainEntity"]
        self.assertEqual(listing["numberOfItems"], 60)
        self.assertEqual(len(listing["itemListElement"]), 60)
        self.assertEqual(output.count('<article class="lp-guide"'), 60)
        self.assertEqual(listing["itemListElement"][-1]["position"], 60)

    def test_whisky_answer_names_scottish_connections_without_production_claim(self) -> None:
        records = {
            "skye": {"name": "Skye", "nation": "Scotland"},
            "arran": {"name": "Arran", "nation": "Scotland"},
            "irish": {"name": "Irish Isle", "nation": "Ireland"},
        }
        stories = {
            "skye": [{"title": "A whisky story", "facet": "story", "sourceUrl": "https://example.org/story"}],
            "arran": [{"title": "Recorded distillery", "facet": "distillery", "sourceUrl": "https://example.org/still"}],
            "irish": [{"title": "Irish connection", "facet": "silent", "sourceUrl": "https://example.org/closed"}],
        }
        page = assemble("whisky-distilleries", stories, records)
        question, answer = page.faqs[0]
        self.assertIn("recorded whisky connections", question)
        self.assertIn("Arran, Skye", answer)
        self.assertNotIn("Irish Isle", answer)
        self.assertIn("do not establish current whisky production", answer)
        output = render(page)
        self.assertIn("(distillery record)", output)
        self.assertIn("(silent still record)", output)
        self.assertIn("(story)", output)

    def test_repeated_books_are_counted_as_connections_with_direct_answer(self) -> None:
        records = {
            "one": {"name": "One", "nation": "Scotland"},
            "two": {"name": "Two", "nation": "Scotland"},
        }
        stories = {
            iid: [{"title": "Shared book", "facet": "book", "sourceUrl": "https://example.org/book"}]
            for iid in records
        }
        page = assemble("island-books", stories, records)
        self.assertEqual(page.row_count, 2)
        self.assertIn("2 book–island connections", page.lede)
        self.assertIn("Shared book (One)", page.faqs[0][1])
        self.assertIn("Shared book (Two)", page.faqs[0][1])

    def test_known_false_rows_stay_held_back(self) -> None:
        page = assemble(
            "island-castles",
            {"arran": [
                {"title": "Airds Castle", "sourceUrl": "https://example.org/false"},
                {"title": "Brodick Castle", "sourceUrl": "https://example.org/kept"},
            ]},
            {"arran": {"name": "Arran", "nation": "Scotland"}},
        )
        self.assertEqual(page.held_back, 1)
        self.assertEqual(page.row_count, 1)
        self.assertEqual(page.islands[0].rows[0].title, "Brodick Castle")
        self.assertNotIn("Airds Castle", render(page))

    def test_uncited_property_fallback_is_explicit(self) -> None:
        records = {"one": {"name": "One", "nation": "Scotland"}}
        pages = assemble_guides(
            {"members": {"for-sale": ["one"]}, "highlights": {"for-sale": {"one": ["Property lead"]}}},
            records,
            {"one": SimpleNamespace(path="/islands/scotland/one/")},
        )
        page = next(page for page in pages if page.slug == "for-sale")
        self.assertEqual(page.row_count, 1)
        self.assertEqual(page.source_count, 0)
        self.assertIn("source link not recorded", render(page))
        self.assertNotIn("1 cited", render_llms_txt([page]))


if __name__ == "__main__":
    unittest.main()
