"""Regresiones de caché al actualizar recursos de la interfaz."""

from unittest.mock import patch

from django.template import Context, Template
from django.test import SimpleTestCase

from .templatetags.asset_tags import asset_url


class AssetVersionTests(SimpleTestCase):
    def test_same_asset_is_cached_but_changed_contents_receive_a_new_url(self):
        with (
            patch("techgear_shop.templatetags.asset_tags.finders.find", return_value="store.css"),
            patch("techgear_shop.templatetags.asset_tags.Path.read_bytes") as read,
        ):
            read.return_value = b".main-links { display: block; }"
            original = asset_url("techgear_shop/css/store.css")
            self.assertEqual(original, asset_url("techgear_shop/css/store.css"))
            read.return_value = b".main-links { display: flex; gap: 8px; }"
            updated = asset_url("techgear_shop/css/store.css")
        self.assertNotEqual(original, updated)
        self.assertIn("store.css?v=", updated)

    def test_rendered_svg_fragment_follows_version_without_changing_navigation_links(self):
        html = Template(
            "{% load asset_tags %}"
            '<use href="{% asset_url "techgear_shop/icons.svg" %}#home"></use>'
            '<a href="/#catalogo">Catálogo</a>'
        ).render(Context())
        self.assertRegex(html, r"icons\.svg\?v=[0-9a-f]{12}#home")
        self.assertIn('href="/#catalogo"', html)
