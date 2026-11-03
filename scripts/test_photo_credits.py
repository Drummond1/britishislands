"""Regression checks for visible standalone photo attribution."""
import unittest

from generate_seo_artifacts import image_credit_html


class PhotoCreditTests(unittest.TestCase):
    def setUp(self):
        self.image = dict(url='https://images.example/photo.jpg', fullUrl='https://images.example/full.jpg', attribution='<a href="https://example.org/person">A &amp; B</a>', license='CC BY-SA 2.0', sourcePageUrl='https://example.org/photo?id=1&lang=en')

    def test_visible_author_licence_and_source_for_selected_photo(self):
        credit = image_credit_html({'images': [self.image]}, self.image['fullUrl'])
        self.assertIn('A &amp; B', credit)
        self.assertIn('CC BY-SA 2.0', credit)
        self.assertIn('https://example.org/photo?id=1&amp;lang=en', credit)
        self.assertNotIn('href="https://example.org/person"', credit)

    def test_never_credits_a_different_photo(self):
        self.assertEqual(image_credit_html({'images': [self.image]}, 'https://images.example/other.jpg'), '')

    def test_unsafe_source_url_is_not_linked(self):
        self.image['sourcePageUrl'] = 'javascript:alert(1)'
        credit = image_credit_html({'images': [self.image]}, self.image['url'])
        self.assertNotIn('href=', credit)
        self.assertIn('A &amp; B', credit)

    def test_metadata_cannot_inject_html(self):
        self.image['attribution'] = '<img src=x onerror=alert(1)>Author'
        self.image['license'] = '<script>alert(1)</script>CC BY'
        credit = image_credit_html({'images': [self.image]}, self.image['url'])
        self.assertNotIn('<img', credit)
        self.assertNotIn('<script', credit)
        self.assertIn('Author', credit)

    def test_missing_images_are_safe(self):
        self.assertEqual(image_credit_html({}, 'https://images.example/photo.jpg'), '')


if __name__ == '__main__':
    unittest.main()
