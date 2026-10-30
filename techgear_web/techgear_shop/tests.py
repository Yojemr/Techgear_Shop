"""Pruebas del frontend con API simulada y sesiones aisladas, sin consultar Atlas."""

import time
from decimal import Decimal
from unittest.mock import patch

import httpx
from django.test import Client, SimpleTestCase, override_settings

from .services.api import ApiClient, ApiError, Product, TokenGrant
from .templatetags.shop_tags import cop

FAKE_PRODUCT = {
    "id": "0123456789abcdef01234567",
    "sku": "TEST-CPU",
    "name": "Procesador de prueba",
    "brand": "Marca de prueba",
    "category": "Procesadores",
    "description": "Componente ficticio utilizado solo en pruebas.",
    "specifications": {"Socket": "Prueba", "Nucleos": "6"},
    "price": "100.25",
    "stock": 5,
    "image_url": "https://images.example.test/cpu.png",
}
FAKE_PROFILE = {
    "id": "abcdef0123456789abcdef01",
    "full_name": "Cliente de prueba",
    "email": "cliente@example.test",
    "role": "customer",
}


@override_settings(
    SESSION_ENGINE="django.contrib.sessions.backends.cache",
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "storefront-isolated-tests",
        }
    },
    ALLOWED_HOSTS=["testserver"],
)
class StorefrontTests(SimpleTestCase):
    """La caché de sesión existe únicamente dentro de estas pruebas."""

    def setUp(self):
        self.client_api = patch("techgear_shop.views.ApiClient").start().return_value
        self.session_api = patch("techgear_shop.middleware.ApiClient").start().return_value
        self.addCleanup(patch.stopall)
        self.client_api.products.return_value = [Product.from_payload(FAKE_PRODUCT)]
        self.client_api.product.return_value = Product.from_payload(FAKE_PRODUCT)
        self.client_api.login.return_value = TokenGrant("jwt-only-for-tests", 1800)
        self.client_api.profile.return_value = FAKE_PROFILE
        self.session_api.profile.return_value = FAKE_PROFILE

    def _open_session(self, *, expires_in=1800):
        session = self.client.session
        session["access_token"] = "jwt-only-for-tests"
        session["auth_expires_at"] = int(time.time()) + expires_in
        session.save()

    def test_catalog_consumes_api_filters_and_displays_stock_without_writes(self):
        response = self.client.get("/", {"q": "procesador", "category": "Procesadores"})
        self.assertEqual(response.status_code, 200)
        self.client_api.products.assert_called_once_with(
            search="procesador", category="Procesadores"
        )
        self.assertContains(response, "Procesador de prueba")
        self.assertContains(response, "$100,25")
        self.assertContains(response, "5 disponibles")

    def test_decimal_sorting_and_html_escaping(self):
        first = Product.from_payload(
            {**FAKE_PRODUCT, "price": "500.10", "name": "<script>x</script>"}
        )
        second = Product.from_payload({**FAKE_PRODUCT, "price": "99.99", "name": "Segundo"})
        self.client_api.products.return_value = [first, second]
        response = self.client.get("/", {"sort": "price_asc"})
        self.assertEqual(response.context["products"], [second, first])
        self.assertContains(response, "&lt;script&gt;x&lt;/script&gt;")
        self.assertNotContains(response, "<script>x</script>")

    def test_invalid_category_never_reaches_api(self):
        response = self.client.get("/", {"category": "desconocida"})
        self.assertEqual(response.status_code, 400)
        self.client_api.products.assert_not_called()

    def test_empty_catalog_and_api_failure_have_useful_states(self):
        self.client_api.products.return_value = []
        self.assertContains(self.client.get("/"), "El catálogo está por comenzar")
        self.client_api.products.side_effect = ApiError(503, "Intenta de nuevo.")
        response = self.client.get("/")
        self.assertEqual(response.status_code, 503)
        self.assertContains(response, "Volver a intentar", status_code=503)

    def test_detail_renders_specs_and_missing_product(self):
        response = self.client.get("/componentes/" + FAKE_PRODUCT["id"] + "/")
        self.assertContains(response, "Especificaciones técnicas")
        self.client_api.product.side_effect = ApiError(404, "Componente no encontrado.")
        self.assertEqual(
            self.client.get("/componentes/" + FAKE_PRODUCT["id"] + "/").status_code, 404
        )

    def test_login_keeps_jwt_on_server_and_rejects_external_next(self):
        response = self.client.post(
            "/ingresar/",
            {
                "email": "cliente@example.test",
                "password": "password ficticio",
                "next": "https://untrusted.example/",
            },
        )
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertEqual(self.client.session["access_token"], "jwt-only-for-tests")
        self.assertGreater(self.client.session["auth_expires_at"], time.time())
        cookie = response.cookies["techgear_session"]
        self.assertTrue(cookie["httponly"])
        self.assertNotIn("jwt-only-for-tests", cookie.value)
        self.client_api.profile.assert_called_once_with("jwt-only-for-tests")

    def test_login_accepts_relative_next_and_preserves_password_spaces(self):
        response = self.client.post(
            "/ingresar/",
            {
                "email": "cliente@example.test",
                "password": " con espacios ",
                "next": "/?category=RAM",
            },
        )
        self.assertEqual(response["Location"], "/?category=RAM")
        self.client_api.login.assert_called_once_with("cliente@example.test", " con espacios ")

    def test_invalid_credentials_do_not_open_session_or_echo_password(self):
        self.client_api.login.side_effect = ApiError(401, "Correo o contraseña incorrectos.")
        response = self.client.post(
            "/ingresar/",
            {
                "email": "cliente@example.test",
                "password": "never-echo-this-value",
            },
        )
        self.assertContains(response, "Correo o contraseña incorrectos.")
        self.assertNotContains(response, "never-echo-this-value")
        self.assertNotIn("access_token", self.client.session)
        self.assertIn("no-store", response["Cache-Control"])

    def test_expired_session_is_removed_before_profile_request(self):
        self._open_session(expires_in=-1)
        response = self.client.get("/")
        self.assertContains(response, "Tu sesión venció.")
        self.assertNotIn("access_token", self.client.session)
        self.session_api.profile.assert_not_called()

    def test_disabled_account_removes_session_and_role_comes_from_api(self):
        self._open_session()
        self.session_api.profile.return_value = {**FAKE_PROFILE, "role": "admin"}
        response = self.client.get("/")
        self.assertContains(response, "Administrador")
        self.assertNotContains(response, "jwt-only-for-tests")
        self.session_api.profile.side_effect = ApiError(401, "Credenciales inválidas.")
        response = self.client.get("/")
        self.assertNotIn("access_token", self.client.session)
        self.assertContains(response, "Iniciar sesión")

    def test_temporary_api_outage_preserves_session_but_not_unverified_identity(self):
        self._open_session()
        self.session_api.profile.side_effect = ApiError(503, "Servicio no disponible.")
        response = self.client.get("/")
        self.assertIn("access_token", self.client.session)
        self.assertIsNone(response.context["shop_account"])
        self.assertContains(response, "No pudimos verificar tu sesión.")

    def test_logout_requires_post_and_clears_session(self):
        self._open_session()
        self.assertEqual(self.client.get("/salir/").status_code, 405)
        response = self.client.post("/salir/")
        self.assertRedirects(response, "/ingresar/", fetch_redirect_response=False)
        self.assertNotIn("access_token", self.client.session)

    def test_login_and_logout_require_csrf(self):
        guarded = Client(enforce_csrf_checks=True)
        self.assertEqual(guarded.post("/ingresar/", {}).status_code, 403)
        self.assertEqual(guarded.post("/salir/", {}).status_code, 403)


class ApiClientTests(SimpleTestCase):
    def _transport(self, handler):
        original = httpx.Client
        return patch(
            "techgear_shop.services.api.httpx.Client",
            side_effect=lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)),
        )

    def test_pagination_and_profile_authorization_header(self):
        requests = []

        def handler(request):
            requests.append(request)
            if request.url.path.endswith("/users/me"):
                return httpx.Response(200, json=FAKE_PROFILE)
            if request.url.params["offset"] == "0":
                return httpx.Response(200, json=[FAKE_PRODUCT] * 100)
            return httpx.Response(200, json=[])

        with self._transport(handler):
            self.assertEqual(len(ApiClient().products()), 100)
            ApiClient().profile("secret-test-token")
        self.assertEqual(requests[1].url.params["offset"], "100")
        self.assertEqual(requests[2].headers["Authorization"], "Bearer secret-test-token")

    def test_http_errors_do_not_echo_private_response_details(self):
        def handler(request):
            return httpx.Response(401, json={"detail": "do-not-expose"})

        with self._transport(handler), self.assertRaises(ApiError) as captured:
            ApiClient().login("fake@example.test", "fake-password")
        self.assertEqual(captured.exception.status_code, 401)
        self.assertNotIn("do-not-expose", str(captured.exception))

    def test_redirect_is_not_followed_and_timeout_is_sanitized(self):
        def redirect_handler(request):
            return httpx.Response(307, headers={"Location": "https://untrusted.example/"})

        with self._transport(redirect_handler), self.assertRaises(ApiError):
            ApiClient().profile("never-redirect-this-token")

        def timeout_handler(request):
            raise httpx.ReadTimeout("private-network-detail", request=request)

        with self._transport(timeout_handler), self.assertRaises(ApiError) as captured:
            ApiClient().products()
        self.assertNotIn("private-network-detail", str(captured.exception))

    def test_invalid_json_product_and_login_payload_are_rejected(self):
        with self._transport(lambda request: httpx.Response(200, text="not-json")):
            with self.assertRaises(ApiError):
                ApiClient().products()
        with self.assertRaises(ApiError):
            Product.from_payload({**FAKE_PRODUCT, "price": "NaN"})
        with self._transport(lambda request: httpx.Response(200, json={"access_token": "bad"})):
            with self.assertRaises(ApiError):
                ApiClient().login("fake@example.test", "fake-password")

    def test_money_formatting_keeps_decimal_precision_and_token_repr_is_redacted(self):
        self.assertEqual(cop(Decimal("1079000.00")), "$1.079.000")
        self.assertEqual(cop(Decimal("99.95")), "$99,95")
        self.assertNotIn("private-token", repr(TokenGrant("private-token", 100)))
