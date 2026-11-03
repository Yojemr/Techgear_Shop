"""Comprueba el entorno publicado y los archivos estáticos sin consultar Atlas."""

import importlib.util
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import DisallowedHost, ImproperlyConfigured
from django.core.management import call_command
from django.http import HttpResponse
from django.middleware.csrf import CsrfViewMiddleware, get_token
from django.test import RequestFactory, SimpleTestCase, override_settings


def deployment_settings(**overrides):
    """Carga ajustes con variables ficticias; no lee los archivos .env privados."""
    environment = {
        "DJANGO_SECRET_KEY": "deployment-test-key-with-no-production-use",
        "DJANGO_DEBUG": "True",
        "MONGO_URI": "mongodb://127.0.0.1:27017/",
        "TECHGEAR_API_URL": "https://api.example.test",
    } | overrides
    source = Path(__file__).with_name("settings.py")
    spec = importlib.util.spec_from_file_location("isolated_deployment_settings", source)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(os.environ, environment, clear=True), patch("dotenv.load_dotenv"):
        spec.loader.exec_module(module)
    return module


class DeploymentTests(SimpleTestCase):
    def test_vercel_disables_debug_and_accepts_only_configured_domains(self):
        config = deployment_settings(
            VERCEL="1",
            VERCEL_URL="preview.example.test",
            VERCEL_PROJECT_PRODUCTION_URL="shop.example.test",
            DJANGO_ALLOWED_HOSTS="custom.example.test",
            DJANGO_CSRF_TRUSTED_ORIGINS="https://custom.example.test/",
        )
        self.assertFalse(config.DEBUG)
        self.assertTrue(config.SESSION_COOKIE_SECURE)
        self.assertTrue(config.CSRF_COOKIE_SECURE)
        self.assertIn("https://custom.example.test", config.CSRF_TRUSTED_ORIGINS)
        with override_settings(ALLOWED_HOSTS=config.ALLOWED_HOSTS):
            for host in ("preview.example.test", "shop.example.test", "custom.example.test"):
                self.assertEqual(RequestFactory().get("/", HTTP_HOST=host).get_host(), host)
            with self.assertRaises(DisallowedHost):
                RequestFactory().get("/", HTTP_HOST="other.vercel.app").get_host()

    def test_vercel_defaults_reject_other_platform_projects(self):
        config = deployment_settings(VERCEL="1", VERCEL_URL="shop.example.test")
        with override_settings(ALLOWED_HOSTS=config.ALLOWED_HOSTS):
            for host in ("other.vercel.app", "other.onrender.com", "localhost"):
                with self.subTest(host=host), self.assertRaises(DisallowedHost):
                    RequestFactory().get("/", HTTP_HOST=host).get_host()
            self.assertEqual(
                RequestFactory().get("/", HTTP_HOST="shop.example.test").get_host(),
                "shop.example.test",
            )

    def test_development_can_keep_debug_and_local_api(self):
        config = deployment_settings(TECHGEAR_API_URL="http://127.0.0.1:8001")
        self.assertTrue(config.DEBUG)
        self.assertFalse(config.SESSION_COOKIE_SECURE)
        self.assertFalse(config.CSRF_COOKIE_SECURE)
        self.assertFalse(hasattr(config, "SECURE_PROXY_SSL_HEADER"))

    def test_vercel_rejects_local_or_unencrypted_api(self):
        for url in ("http://127.0.0.1:8001", "https://localhost", "http://api.example.test"):
            with self.subTest(url=url), self.assertRaises(ImproperlyConfigured):
                deployment_settings(VERCEL="1", TECHGEAR_API_URL=url)

    def test_https_proxy_and_same_origin_post_preserve_csrf_validation(self):
        config = deployment_settings(VERCEL="1", VERCEL_URL="shop.example.test")
        with override_settings(
            ALLOWED_HOSTS=config.ALLOWED_HOSTS,
            CSRF_TRUSTED_ORIGINS=config.CSRF_TRUSTED_ORIGINS,
            SECURE_PROXY_SSL_HEADER=config.SECURE_PROXY_SSL_HEADER,
        ):
            factory = RequestFactory()
            seed = factory.get("/")
            token = get_token(seed)
            middleware = CsrfViewMiddleware(lambda request: HttpResponse("ok"))
            for origin, expected in (
                ("https://shop.example.test", None),
                ("https://other.example.test", 403),
            ):
                with self.subTest(origin=origin):
                    request = factory.post(
                        "/ingresar/",
                        {"csrfmiddlewaretoken": token},
                        HTTP_HOST="shop.example.test",
                        HTTP_ORIGIN=origin,
                        HTTP_X_FORWARDED_PROTO="https",
                    )
                    request.COOKIES[settings.CSRF_COOKIE_NAME] = seed.META["CSRF_COOKIE"]
                    self.assertTrue(request.is_secure())
                    middleware.process_request(request)
                    result = middleware.process_view(
                        request, lambda request: HttpResponse("ok"), (), {}
                    )
                    self.assertEqual(None if result is None else result.status_code, expected)

    def test_collectstatic_copies_store_assets_with_debug_disabled(self):
        # El build prepara recursos; no necesita una conexión de base de datos.
        local = settings.BASE_DIR.parent / ".local"
        local.mkdir(exist_ok=True)
        with TemporaryDirectory(dir=local, prefix="static-test-") as directory:
            with override_settings(DEBUG=False, STATIC_ROOT=directory, STATIC_URL="/static/"):
                call_command("collectstatic", interactive=False, verbosity=0)
            for asset in ("css/store.css", "js/store.js", "banners.svg", "icons.svg"):
                self.assertTrue((Path(directory) / "techgear_shop" / asset).stat().st_size)
