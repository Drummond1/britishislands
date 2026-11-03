"""Static learning pages match the overlay and expose their evidence without JavaScript."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
import generate_seo_artifacts as seo
from seo_learning import load_learning, learning_profile_html, reading_links_for, journey_page_html, write_learning_pages
from seo_paths import assign_seo_paths

ROOT = Path(__file__).resolve().parents[1]

class LearningPagesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = load_learning(ROOT/'data/learning_profiles.json')
        cls.rows = json.loads((ROOT/'data/islands.json').read_text())
        cls.islands = {r['id']: r for r in cls.rows}
        cls.paths = assign_seo_paths(cls.rows)

    def test_all_twenty_profiles_expose_facts_sources_timeline_and_connections(self):
        for iid, profile in self.doc['profiles'].items():
            links = reading_links_for(profile, self.islands, self.paths)
            output = seo.profile_page_html(self.islands[iid], origin='https://www.findmyisland.com', atlas_href='/', profile_path=self.paths[iid].path, title=self.islands[iid]['name'], learning=profile, learning_links=links)
            self.assertIn('The island’s story', output)
            self.assertIn('A short timeline', output)
            self.assertIn('Follow the story', output)
            self.assertIn('Source checked 2026-11-03', output)
            self.assertEqual(len(links), 3)
            self.assertNotIn('Last reviewed', output)

    def test_journeys_and_hub_are_written_and_all_stops_survive(self):
        with tempfile.TemporaryDirectory() as directory:
            write_learning_pages(Path(directory), self.doc, self.islands, self.paths, 'https://www.findmyisland.com', seo.landing_head_assets(2), seo.landing_head_assets(1))
            self.assertEqual(len(list(Path(directory).rglob('index.html'))), 4)
            self.assertIn('../learning.css?', (Path(directory)/'learn/index.html').read_text())
            for journey in self.doc['journeys']:
                output = (Path(directory)/'learn'/journey['slug']/'index.html').read_text()
                self.assertIn('../../learning.css?', output)
                for stop in journey['stops']:
                    self.assertIn(self.paths[stop['id']].path, output)
                self.assertIn('Wikipedia', output)
                self.assertNotIn('/ferries/', output)

    def test_source_markup_is_escaped_and_unsafe_links_are_absent(self):
        profile = copy.deepcopy(self.doc['profiles']['lundy'])
        profile['overview'] = '<script>alert(1)</script>'
        profile['sources'][0]['url'] = 'javascript:alert(1)'
        output = learning_profile_html(profile)
        self.assertNotIn('<script>', output)
        self.assertNotIn('href="javascript:', output)

    def test_missing_journey_target_fails_instead_of_silently_dropping_a_stop(self):
        journey = copy.deepcopy(self.doc['journeys'][0]); journey['stops'][0]['id'] = 'missing'
        with self.assertRaises(ValueError):
            journey_page_html(journey, self.doc, self.islands, self.paths, '', '')

if __name__ == '__main__': unittest.main()
