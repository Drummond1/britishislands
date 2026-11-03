#!/usr/bin/env python3
"""Offline integrity checks for public profile and sitemap generation."""
from __future__ import annotations

import contextlib
import io
import json
import re
import tempfile
import unittest
from html import unescape
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from xml.etree import ElementTree

import generate_seo_artifacts as seo

ORIGIN = 'https://www.findmyisland.com'
PROFILE = '/islands/scotland/test-island/'


def island(**extra):
    row = {'id': 'test-island', 'name': 'Test Island', 'nation': 'Scotland',
           'lat': 56.1, 'lng': -5.1, 'type': 'sea', 'shortDescription': 'A sourced island.',
           'population': 0, 'populationYear': 2022,
           'sources': [{'name': 'Reference', 'url': 'https://example.org/reference',
                        'licence': 'OGL', 'attribution': 'Original contributors',
                        'retrieved': '2026-01-03'}],
           'images': [{'url': 'https://example.org/island.jpg',
                       'attribution': '<a href="https://example.org/author">A Photographer</a>',
                       'license': 'CC BY 4.0', 'sourcePageUrl': 'https://example.org/photo'}]}
    row.update(extra)
    return row


def render(row=None, **extra):
    return seo.profile_page_html(row or island(), origin=ORIGIN,
        atlas_href='../../../', profile_path=PROFILE, title='Test Island', **extra)


class ArtifactIntegrityTests(unittest.TestCase):
    def test_existing_fact_years_and_attribution_survive_rendering(self):
        output = render(island(populationAttribution='Population contributors',
                               highestPointM=12, highestPointConfidence='estimate'))
        for text in ['0 (2022)', 'A Photographer', 'CC BY 4.0', 'Image source',
                     'Original contributors', 'Population contributors', 'retrieved 2026-01-03', '12 m (estimate)']:
            self.assertIn(text, output)
        self.assertNotIn('&lt;a href=', output)
        self.assertNotIn('Last reviewed', output)
        self.assertIn('<figcaption>', output)

    def test_unknown_population_year_is_not_invented(self):
        row = island()
        row.pop('populationYear')
        self.assertIn('reference year not recorded', render(row))
        row['population'] = None
        self.assertNotIn('<strong>Population</strong>', render(row))

    def test_alternate_and_cta_urls_are_escaped_once(self):
        output = render()
        alternate = re.search(r'rel="alternate" href="([^"]+)"', output).group(1)
        self.assertNotIn('&amp;amp;', alternate)
        self.assertEqual(parse_qs(urlsplit(unescape(alternate)).query),
                         {'island': ['test-island'], 'map': ['1']})
        self.assertIn(f'class="lp-cta" href="{alternate}"', output)

    def test_schema_preserves_entity_identity_and_cannot_close_script(self):
        malicious = '</script><script>alert(1)</script>'
        output = render(island(name=malicious, shortDescription=malicious))
        payloads = re.findall(r'<script type="application/ld\+json">(.*?)</script>', output, re.S)
        self.assertEqual(len(payloads), 1)
        payload = json.loads(payloads[0])
        graph = payload['@graph']
        entity = next(node for node in graph if node['@type'] == 'Landform')
        page = next(node for node in graph if node['@type'] == 'WebPage')
        self.assertEqual(entity['name'], malicious)
        self.assertEqual(page['mainEntity']['@id'], entity['@id'])
        self.assertEqual(entity['address']['addressCountry'], 'GB')
        self.assertNotIn('<script>alert(1)', output)
        invalid_geo = render(island(lat=float('nan'), lng=float('inf')))
        invalid_graph = json.loads(re.search(r'application/ld\+json">(.*?)</script>', invalid_geo, re.S).group(1))['@graph']
        self.assertNotIn('geo', invalid_graph[0])

    def test_all_profile_stories_have_their_evidence_available(self):
        rows = [{'title': f'Entry {n}', 'summary': f'Evidence {n}.',
                 'sourceUrl': f'https://example.org/{n}'} for n in range(5)]
        output = render(guide_links=[{'href': '/collections/island-books/',
                                     'label': 'Books', 'rows': rows}])
        for n in range(5):
            self.assertIn(f'Entry {n}</a>', output)
            self.assertIn(f'Evidence {n}.', output)
        self.assertIn('<details>', output)
        self.assertIn('Report a correction', output)
        self.assertNotIn('Nearby and related', output)

    def test_executable_source_urls_are_not_links(self):
        row = island(sources=[{'name': 'Bad source', 'url': 'javascript:alert(1)'}])
        output = render(row)
        self.assertNotIn('href="javascript:', output)

    def test_sitemap_dates_are_optional_and_only_valid_dates_are_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'sitemap.xml'
            seo.write_urlset(path, [(ORIGIN+'/', 1.0, None),
                                   (ORIGIN+'/known/', 0.8, '2026-02-03'),
                                   (ORIGIN+'/unknown/', 0.8, 'not-a-date')])
            root = ElementTree.fromstring(path.read_text())
            ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
            self.assertEqual([node.text for node in root.findall('.//s:lastmod', ns)], ['2026-02-03'])
            self.assertEqual(len(root.findall('s:url', ns)), 3)

    def test_full_generator_keeps_ferry_freeze_and_atlas_indexability(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / 'data'
            data.mkdir()
            rows = [island(), island(id='unnamed-test', name='Unnamed island', shortDescription='')]
            (data/'islands.json').write_text(json.dumps(rows))
            (data/'curated.json').write_text(json.dumps([rows[0]]))
            (root/'index.html').write_text(seo.CRAWL_LINKS_MARKER_START + seo.CRAWL_LINKS_MARKER_END)
            constants = {'ROOT': root, 'DATA': data, 'ISLANDS': data/'islands.json',
                         'CURATED': data/'curated.json', 'FEATURED': data/'featured.json',
                         'SEO_PATH_MAP': data/'seo_path_by_id.json', 'LEGACY_REDIRECTS': data/'legacy_redirects.csv',
                         'INDEX_HTML': root/'index.html', 'ISLANDS_DIR': root/'islands'}
            before = (data/'islands.json').read_bytes()
            with patch.multiple(seo, **constants), patch.object(seo, 'load_interest_index', return_value={}), \
                 patch('sys.argv', ['generate_seo_artifacts.py', '--site-origin', ORIGIN]), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(seo.main(), 0)
            self.assertEqual((data/'islands.json').read_bytes(), before)
            self.assertEqual(seo.FERRY_PATHS, ())
            for path in root.glob('sitemap*.xml'):
                xml = path.read_text()
                ElementTree.fromstring(xml)
                self.assertNotIn('/ferries/', xml)
                self.assertNotIn('<lastmod>', xml)
            paths = json.loads((data/'seo_path_by_id.json').read_text())['paths']
            unnamed = (root / paths['unnamed-test'].strip('/') / 'index.html').read_text()
            self.assertIn('index,follow', unnamed)
            self.assertNotIn('noindex', unnamed)
            trust = (root/'methodology/index.html').read_text()
            self.assertIn(seo.REPOSITORY_URL+'/blob/main/docs/ETHICS.md', trust)
            self.assertIn(seo.REPOSITORY_URL+'/issues', trust)


if __name__ == '__main__':
    unittest.main()
