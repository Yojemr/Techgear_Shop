"""Pruebas del CRUD web, permisos y transporte HTTP con datos aislados."""

import time
from dataclasses import replace
from decimal import Decimal
from unittest.mock import patch

import httpx
from django.test import Client, SimpleTestCase, override_settings

from .forms import ProductForm
from .services.api import ApiClient, ApiError, Product
from .tests import FAKE_PRODUCT, FAKE_PROFILE

PRODUCT = Product.from_payload(FAKE_PRODUCT)
DATA = {
    **FAKE_PRODUCT,
    "specifications": "Socket: AM5\nNúcleos: 6",
    "price": "100.25",
    "stock": "5",
    "active": "on",
}
DATA.pop("id")


@override_settings(
    SESSION_ENGINE="django.contrib.sessions.backends.cache",
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "dashboard-tests",
        }
    },
    ALLOWED_HOSTS=["testserver"],
)
class DashboardTests(SimpleTestCase):
    """La sesión y la API son ficticias; ninguna escritura llega a Atlas."""

    def setUp(self):
        self.api = patch("techgear_shop.dashboard.ApiClient").start().return_value
        self.profile = patch("techgear_shop.middleware.ApiClient").start().return_value
        self.addCleanup(patch.stopall)
        self.profile.profile.return_value = FAKE_PROFILE | {"role": "admin"}
        self.api.products.return_value = [PRODUCT, replace(PRODUCT, id="f" * 24, active=False)]
        self.api.managed_product.return_value = PRODUCT
        self.api.save_product.return_value = PRODUCT
        self.authenticate()

    def authenticate(self, client=None):
        client = client or self.client
        session = client.session
        session["access_token"] = "test-only-token"
        session["auth_expires_at"] = int(time.time()) + 1800
        session.save()

    def test_anonymous_and_customer_cannot_use_any_admin_view(self):
        self.client = Client()
        urls = [
            "/gestion/productos/",
            "/gestion/productos/nuevo/",
            f"/gestion/productos/{PRODUCT.id}/editar/",
            f"/gestion/productos/{PRODUCT.id}/desactivar/",
        ]
        for url in urls:
            for method in ("get", "post"):
                with self.subTest(url=url, method=method):
                    response = getattr(self.client, method)(url)
                    self.assertEqual(
                        response.status_code, 405 if method == "post" and url == urls[0] else 302
                    )
        self.authenticate()
        self.profile.profile.return_value = FAKE_PROFILE
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 403)
            if url != urls[0]:
                self.assertEqual(self.client.post(url, DATA).status_code, 403)
        self.api.products.assert_not_called()
        self.api.save_product.assert_not_called()
        self.api.deactivate_product.assert_not_called()

    def test_table_reads_all_states_and_filters_without_writing(self):
        response = self.client.get("/gestion/productos/", {"state": "inactive", "q": "CPU"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["products"]), 1)
        self.assertContains(response, "Inactivo")
        self.assertContains(response, "Administración")
        self.assertNotContains(response, "test-only-token")
        self.api.products.assert_called_once_with(
            token="test-only-token", search="CPU", category=""
        )
        self.api.save_product.assert_not_called()

    def test_create_and_update_use_only_validated_server_payload(self):
        for url, identifier in [
            ("/gestion/productos/nuevo/", None),
            (f"/gestion/productos/{PRODUCT.id}/editar/", PRODUCT.id),
        ]:
            with self.subTest(url=url):
                response = self.client.post(url, DATA | {"role": "admin", "customer_id": "forged"})
                self.assertRedirects(response, "/gestion/productos/", fetch_redirect_response=False)
                args, kwargs = self.api.save_product.call_args
                self.assertEqual(args[0]["price"], "100.25")
                self.assertEqual(args[0]["stock"], 5)
                self.assertEqual(args[0]["specifications"], {"Socket": "AM5", "Núcleos": "6"})
                self.assertNotIn("role", args[0])
                self.assertNotIn("customer_id", args[0])
                self.assertEqual(kwargs["identifier"], identifier)

    def test_invalid_form_does_not_write_and_keeps_entered_data(self):
        response = self.client.post("/gestion/productos/nuevo/", DATA | {"stock": "-1"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("stock", response.context["form"].errors)
        self.assertContains(response, "Procesador de prueba")
        self.api.save_product.assert_not_called()

    def test_duplicate_sku_and_api_validation_keep_form(self):
        for status in (409, 422):
            self.api.save_product.side_effect = ApiError(status, "Conflicto controlado")
            response = self.client.post("/gestion/productos/nuevo/", DATA)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["form"].errors)

    def test_edit_can_reactivate_an_inactive_product(self):
        self.api.managed_product.return_value = replace(PRODUCT, active=False)
        response = self.client.get(f"/gestion/productos/{PRODUCT.id}/editar/")
        self.assertFalse(response.context["form"].initial["active"])
        response = self.client.post(f"/gestion/productos/{PRODUCT.id}/editar/", DATA)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.api.save_product.call_args.args[0]["active"])

    def test_delete_requires_confirmation_and_post(self):
        url = f"/gestion/productos/{PRODUCT.id}/desactivar/"
        self.assertEqual(self.client.get(url).status_code, 200)
        self.api.deactivate_product.assert_not_called()
        self.assertEqual(self.client.post(url).status_code, 302)
        self.api.deactivate_product.assert_called_once_with(PRODUCT.id, "test-only-token")
        self.assertEqual(self.client.delete(url).status_code, 405)

    def test_repeated_deactivation_does_not_send_another_delete(self):
        self.api.managed_product.return_value = replace(PRODUCT, active=False)
        self.assertEqual(
            self.client.post(f"/gestion/productos/{PRODUCT.id}/desactivar/").status_code, 302
        )
        self.api.deactivate_product.assert_not_called()

    def test_post_requires_csrf_for_all_writes(self):
        client = Client(enforce_csrf_checks=True)
        self.authenticate(client)
        for url in (
            "/gestion/productos/nuevo/",
            f"/gestion/productos/{PRODUCT.id}/editar/",
            f"/gestion/productos/{PRODUCT.id}/desactivar/",
        ):
            self.assertEqual(client.post(url, DATA).status_code, 403)
        self.api.save_product.assert_not_called()
        self.api.deactivate_product.assert_not_called()

    def test_expired_token_and_outage_never_allow_admin_operations(self):
        self.profile.profile.side_effect = ApiError(503, "No disponible")
        self.assertEqual(self.client.get("/gestion/productos/").status_code, 503)
        self.api.products.assert_not_called()
        self.profile.profile.side_effect = None
        self.api.products.side_effect = ApiError(401, "Vencida")
        response = self.client.get("/gestion/productos/")
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("access_token", self.client.session)

    def test_not_found_and_outage_return_controlled_pages(self):
        for code in (404, 503):
            self.api.managed_product.side_effect = ApiError(code, "Error controlado")
            response = self.client.get(f"/gestion/productos/{PRODUCT.id}/editar/")
            self.assertEqual(response.status_code, code)

    def test_new_and_edit_forms_render_with_csrf_and_current_data(self):
        response = self.client.get("/gestion/productos/nuevo/")
        self.assertContains(response, "csrfmiddlewaretoken")
        response = self.client.get(f"/gestion/productos/{PRODUCT.id}/editar/")
        self.assertContains(response, "TEST-CPU")
        self.assertContains(response, "Guardar cambios")

    def test_modal_loads_prefixed_form_without_exposing_token(self):
        response = self.client.get(f"/gestion/productos/{PRODUCT.id}/editar/?modal=1")
        self.assertEqual(response.status_code, 200)
        html = response.json()["html"]
        self.assertIn('name="product-stock"', html)
        self.assertIn('name="product-specifications"', html)
        self.assertIn("csrfmiddlewaretoken", html)
        self.assertNotIn("test-only-token", html)
        self.api.save_product.assert_not_called()

    def test_modal_validation_keeps_data_and_success_returns_json(self):
        url = f"/gestion/productos/{PRODUCT.id}/editar/?modal=1"
        payload = {f"product-{key}": value for key, value in DATA.items()}
        response = self.client.post(url, payload | {"product-stock": "-1"})
        self.assertEqual(response.status_code, 422)
        self.assertIn('value="-1"', response.json()["html"])
        self.api.save_product.assert_not_called()
        response = self.client.post(url, payload | {"product-stock": "7"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["saved"])
        self.assertEqual(self.api.save_product.call_args.args[0]["stock"], 7)

    def test_modal_duplicate_sku_and_csrf_are_enforced(self):
        url = f"/gestion/productos/{PRODUCT.id}/editar/?modal=1"
        payload = {f"product-{key}": value for key, value in DATA.items()}
        self.api.save_product.side_effect = ApiError(409, "SKU existente")
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 422)
        self.assertIn("SKU existente", response.json()["html"])
        client = Client(enforce_csrf_checks=True)
        self.authenticate(client)
        self.assertEqual(client.post(url, payload).status_code, 403)

    def test_customer_cannot_read_or_save_modal(self):
        self.profile.profile.return_value = FAKE_PROFILE
        url = f"/gestion/productos/{PRODUCT.id}/editar/?modal=1"
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {}).status_code, 403)
        self.api.managed_product.assert_not_called()
        self.api.save_product.assert_not_called()


class ProductFormTests(SimpleTestCase):
    def test_money_integer_stock_and_specification_validation(self):
        form = ProductForm(DATA)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["price"], Decimal("100.25"))
        for fields in (
            {"stock": "1.5"},
            {"stock": "-1"},
            {"price": "0.001"},
            {"price": "-1"},
            {"specifications": "Socket: AM5\nsocket: AM4"},
            {"specifications": "Sin separador"},
            {"specifications": "Clave:"},
            {"image_url": "javascript:alert(1)"},
        ):
            with self.subTest(fields=fields):
                self.assertFalse(ProductForm(DATA | fields).is_valid())


class DashboardHttpTests(SimpleTestCase):
    def test_authenticated_read_post_put_and_empty_delete(self):
        calls = []

        def handle(request):
            calls.append(request)
            if request.method == "DELETE":
                return httpx.Response(204)
            if request.url.path.endswith("/manage/"):
                return httpx.Response(200, json=[FAKE_PRODUCT | {"active": False}])
            return httpx.Response(200, json=FAKE_PRODUCT)

        factory = httpx.Client
        with patch(
            "techgear_shop.services.api.httpx.Client",
            side_effect=lambda **kw: factory(transport=httpx.MockTransport(handle), **kw),
        ):
            client = ApiClient()
            self.assertFalse(client.products(token="test-token")[0].active)
            client.managed_product(PRODUCT.id, "test-token")
            form = ProductForm(DATA)
            self.assertTrue(form.is_valid())
            client.save_product(form.payload(), "test-token")
            client.save_product(form.payload(), "test-token", identifier=PRODUCT.id)
            client.deactivate_product(PRODUCT.id, "test-token")
        self.assertEqual([c.method for c in calls], ["GET", "GET", "POST", "PUT", "DELETE"])
        self.assertTrue(all(c.headers["Authorization"] == "Bearer test-token" for c in calls))
        self.assertIn("/products/manage/", str(calls[0].url))
