"""Recorridos web con API simulada; ninguna prueba escribe en Atlas."""

import time
from decimal import Decimal
from unittest.mock import patch

from django.test import Client, SimpleTestCase, override_settings

from .models import Cart, Order
from .services.api import ApiClient, ApiError, Product, TokenGrant
from .tests import FAKE_PRODUCT, FAKE_PROFILE

LINE = {
    "product_id": FAKE_PRODUCT["id"],
    "sku": "TEST-CPU",
    "name": "Procesador de prueba",
    "quantity": 3,
    "unit_price": Decimal("100.25"),
    "subtotal": Decimal("300.75"),
    "image_url": FAKE_PRODUCT["image_url"],
    "active": True,
    "available_stock": 2,
}
CART = Cart("a" * 24, [LINE], Decimal("300.75"))
ORDER = Order("b" * 24, [LINE], Decimal("300.75"), "confirmed", "2026-11-05T12:00:00Z")


@override_settings(
    SESSION_ENGINE="django.contrib.sessions.backends.cache",
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "cart-isolated-tests",
        }
    },
    ALLOWED_HOSTS=["testserver"],
)
class CartWebTests(SimpleTestCase):
    def setUp(self):
        self.api = patch("techgear_shop.cart.ApiClient").start().return_value
        self.views_api = patch("techgear_shop.views.ApiClient").start().return_value
        self.auth = patch("techgear_shop.middleware.ApiClient").start().return_value
        self.addCleanup(patch.stopall)
        self.auth.profile.return_value = FAKE_PROFILE
        self.api.cart.return_value = CART
        self.api.change_cart.return_value = CART
        self.api.clear_cart.return_value = Cart(None, [], Decimal(0))
        self.api.checkout.return_value = ORDER
        self.api.orders.return_value = [ORDER]
        self.api.order.return_value = ORDER
        self.api.heartbeat.return_value = {"count": 3}
        self.views_api.register.return_value = FAKE_PROFILE
        self.views_api.clear_cart.return_value = Cart(None, [], Decimal(0))
        self.api.products.return_value = [Product.from_payload(FAKE_PRODUCT)]
        self.api.product.return_value = Product.from_payload(FAKE_PRODUCT)
        self.views_api.login.return_value = TokenGrant("private-test-token", 1800)
        self.views_api.profile.return_value = FAKE_PROFILE
        self.views_api.import_cart.return_value = CART
        self.api.import_cart.return_value = CART

    def login(self):
        session = self.client.session
        session["access_token"] = "private-test-token"
        session["auth_expires_at"] = int(time.time()) + 1800
        session.save()

    def test_public_registration_reaches_api_without_role_and_never_echoes_password(self):
        response = self.client.post(
            "/registro/",
            {
                "full_name": "Nuevo Cliente",
                "email": "nuevo@example.com",
                "password": " clave con espacios ",
                "password_confirm": " clave con espacios ",
                "role": "admin",
                "next": "/carrito/",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/ingresar/", response["Location"])
        self.views_api.register.assert_called_once_with(
            "Nuevo Cliente", "nuevo@example.com", " clave con espacios "
        )
        self.assertNotIn("access_token", self.client.session)
        self.views_api.register.side_effect = ApiError(409, "Ya existe una cuenta con ese correo.")
        response = self.client.post(
            "/registro/",
            {
                "full_name": "Nuevo Cliente",
                "email": "nuevo@example.com",
                "password": "never-echo-me",
                "password_confirm": "never-echo-me",
            },
        )
        self.assertContains(response, "Ya existe una cuenta")
        self.assertNotContains(response, "never-echo-me")

    def test_invalid_or_mismatched_registration_does_not_call_api(self):
        for values in (
            {"password": "short", "password_confirm": "short"},
            {"password": "password1", "password_confirm": "password2"},
        ):
            response = self.client.post(
                "/registro/", {"full_name": "Cliente", "email": "ok@example.com"} | values
            )
            self.assertEqual(response.status_code, 200)
        self.views_api.register.assert_not_called()

    def test_registration_rejects_external_next(self):
        response = self.client.get("/registro/", {"next": "https://outside.example/"})
        self.assertEqual(response.context["next"], "/")

    def test_guest_can_view_cart_but_cannot_reserve_or_confirm(self):
        response = self.client.get("/carrito/", HTTP_ACCEPT="application/json")
        self.assertIn("Crear una cuenta", response.json()["html"])
        self.assertEqual(response.json()["count"], 0)
        response = self.client.post(
            "/carrito/agregar/" + FAKE_PRODUCT["id"] + "/",
            {"quantity": 3},
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session["guest_cart"][FAKE_PRODUCT["id"]], 3)
        self.api.change_cart.assert_not_called()
        self.api.checkout.assert_not_called()
        self.api.import_cart.assert_not_called()
        self.assertContains(self.client.get("/carrito/"), "Confirmar pedido")
        response = self.client.post("/carrito/confirmar/", {"expected_total": "0"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/ingresar/", response["Location"])
        self.api.checkout.assert_not_called()

    def test_authenticated_cart_renders_totals_forms_and_drawer_without_token(self):
        self.login()
        response = self.client.get("/carrito/")
        self.assertContains(response, "$300,75")
        self.assertContains(response, 'value="300.75"')
        self.assertContains(response, "Confirmar pedido")
        self.assertContains(response, 'id="cart-drawer"')
        self.assertNotContains(response, "private-test-token")
        self.assertIn("no-store", response["Cache-Control"])

    def test_add_update_remove_and_clear_use_only_server_token(self):
        self.login()
        for action, quantity in (("agregar", 3), ("cantidad", 2), ("cantidad", 0)):
            response = self.client.post(
                f"/carrito/{action}/{FAKE_PRODUCT['id']}/",
                {"quantity": quantity, "customer_id": "ignored", "price": "0"},
                HTTP_ACCEPT="application/json",
            )
            self.assertEqual(response.status_code, 200)
            self.api.change_cart.assert_called_with(
                FAKE_PRODUCT["id"], quantity, "private-test-token", add=action == "agregar"
            )
        response = self.client.post("/carrito/vaciar/", HTTP_ACCEPT="application/json")
        self.assertEqual(response.json()["count"], 0)
        self.api.clear_cart.assert_called_once_with("private-test-token")

    def test_bad_quantity_and_api_conflict_do_not_claim_success(self):
        self.login()
        path = f"/carrito/agregar/{FAKE_PRODUCT['id']}/"
        response = self.client.post(path, {"quantity": -1}, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 422)
        self.api.change_cart.assert_not_called()
        self.api.change_cart.side_effect = ApiError(409, "No hay suficientes unidades.")
        response = self.client.post(path, {"quantity": 3}, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 409)
        self.assertIn("No hay suficientes", response.json()["error"])

    def test_confirmation_redirects_to_receipt_and_hides_payment_language(self):
        self.login()
        response = self.client.post(
            "/carrito/confirmar/", {"version": CART.version, "expected_total": "300.75"}
        )
        self.api.checkout.assert_called_once_with(
            CART.version, Decimal("300.75"), "private-test-token"
        )
        self.assertEqual(response["Location"], "/pedidos/" + ORDER.id + "/")
        self.assertEqual(self.client.session["cart_count"], 0)
        receipt = self.client.get(response["Location"])
        self.assertContains(receipt, "No se ha realizado ningún cobro")
        self.assertContains(receipt, "$300,75")
        self.assertNotContains(receipt, "Pagado")

    def test_order_failure_does_not_clear_cart_or_retry_confirmation(self):
        self.login()
        self.api.checkout.side_effect = ApiError(503, "No pudimos confirmar.")
        response = self.client.post(
            "/carrito/confirmar/", {"version": CART.version, "expected_total": "300.75"}
        )
        self.assertEqual(response["Location"], "/carrito/")
        self.api.checkout.assert_called_once()
        self.api.clear_cart.assert_not_called()

    def test_logout_releases_inventory_before_forgetting_token_and_blocks_on_failure(self):
        self.login()
        self.views_api.clear_cart.side_effect = ApiError(503, "No disponible.")
        self.assertEqual(self.client.post("/salir/").status_code, 503)
        self.assertIn("access_token", self.client.session)
        self.views_api.clear_cart.side_effect = None
        self.assertEqual(self.client.post("/salir/").status_code, 302)
        self.assertNotIn("access_token", self.client.session)

    def test_presence_refreshes_reservations_without_extending_authentication(self):
        self.login()
        before = self.client.session["auth_expires_at"]
        response = self.client.post("/carrito/presencia/", HTTP_ACCEPT="application/json")
        self.assertEqual(response.json(), {"count": 3})
        self.assertEqual(self.client.session["auth_expires_at"], before)

    def test_csrf_and_post_are_required_for_all_writes(self):
        guarded = Client(enforce_csrf_checks=True)
        for path in (
            "/registro/",
            "/carrito/vaciar/",
            "/carrito/confirmar/",
            "/carrito/presencia/",
            f"/carrito/agregar/{FAKE_PRODUCT['id']}/",
        ):
            self.assertEqual(guarded.post(path).status_code, 403)
        for path in ("/carrito/vaciar/", "/carrito/confirmar/", "/carrito/presencia/"):
            self.assertEqual(self.client.get(path).status_code, 405)

    def test_readable_product_urls_and_related_products(self):
        product = Product.from_payload(FAKE_PRODUCT)
        other = Product.from_payload(
            FAKE_PRODUCT | {"id": "c" * 24, "sku": "OTRO", "name": "Otra pieza"}
        )
        self.views_api.product_by_slug.return_value = product
        self.views_api.products.return_value = [product, other]
        response = self.client.get("/componentes/" + product.slug + "/")
        self.assertContains(response, "Agregar al carrito")
        self.assertContains(response, "Otras piezas que pueden interesarte")
        self.assertEqual(response.context["related_products"], [other])
        self.assertNotIn(product.id, product.slug)
        with patch.object(ApiClient, "products", return_value=[product, other]):
            self.assertEqual(ApiClient().product_by_slug(product.slug), product)
            with self.assertRaises(ApiError):
                ApiClient().product_by_slug(product.id)

    def test_cart_models_reject_inconsistent_api_totals(self):
        payload = {"version": CART.version, "items": [LINE], "total": "0", "currency": "COP"}
        with self.assertRaises(ApiError):
            ApiClient()._read_model(Cart, payload)
        payload["total"] = "300.75"
        self.assertEqual(ApiClient()._read_model(Cart, payload).total, Decimal("300.75"))

    def test_api_outage_does_not_loop_cart_redirects_or_forget_session_on_logout(self):
        self.login()
        self.auth.profile.side_effect = ApiError(503, "Servicio no disponible.")
        response = self.client.get("/carrito/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.client.post("/salir/").status_code, 503)
        self.assertIn("access_token", self.client.session)

    def test_stock_updates_are_returned_for_reserved_and_removed_products(self):
        self.login()
        self.api.products.return_value = [Product.from_payload(FAKE_PRODUCT | {"stock": 2})]
        response = self.client.post(
            f"/carrito/agregar/{FAKE_PRODUCT['id']}/",
            {"quantity": 3},
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.json()["stocks"][FAKE_PRODUCT["id"]], 2)
        self.assertIn("-panel", response.json()["html"])
        self.api.products.side_effect = ApiError(503, "No disponible.")
        response = self.client.post("/carrito/vaciar/", HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 0)

    def test_guest_can_update_and_clear_selection_without_inventory_calls(self):
        path = f"/carrito/agregar/{FAKE_PRODUCT['id']}/"
        self.client.post(path, {"quantity": 2, "price": "0"})
        self.client.post(path, {"quantity": 1})
        response = self.client.get("/carrito/")
        self.assertContains(response, "$300,75")
        self.assertContains(response, "Tu selección aún no reserva inventario")
        self.client.post(f"/carrito/cantidad/{FAKE_PRODUCT['id']}/", {"quantity": 1})
        self.assertEqual(self.client.session["guest_cart"][FAKE_PRODUCT["id"]], 1)
        self.client.post("/carrito/vaciar/")
        self.assertNotIn("guest_cart", self.client.session)
        self.api.change_cart.assert_not_called()
        self.api.clear_cart.assert_not_called()
        self.api.import_cart.assert_not_called()

    def test_login_preserves_guest_selection_rotates_session_and_reserves_once(self):
        self.client.post(f"/carrito/agregar/{FAKE_PRODUCT['id']}/", {"quantity": 3})
        previous_session = self.client.session.session_key
        transfer = self.client.session["guest_cart_transfer"]
        response = self.client.post(
            "/ingresar/",
            {"email": "cliente@example.com", "password": "ficticia-123", "next": "/carrito/"},
        )
        self.assertEqual(response["Location"], "/carrito/")
        self.assertNotEqual(self.client.session.session_key, previous_session)
        self.views_api.import_cart.assert_called_once_with(
            {FAKE_PRODUCT["id"]: 3}, transfer, "private-test-token"
        )
        self.assertNotIn("guest_cart", self.client.session)
        self.assertEqual(self.client.session["cart_count"], 3)
        self.assertIn("access_token", self.client.session)

    def test_login_stock_conflict_keeps_pending_editable_and_does_not_confirm(self):
        self.client.post(f"/carrito/agregar/{FAKE_PRODUCT['id']}/", {"quantity": 3})
        self.views_api.import_cart.side_effect = ApiError(409, "No hay unidades suficientes.")
        response = self.client.post(
            "/ingresar/",
            {"email": "cliente@example.com", "password": "ficticia-123", "next": "/carrito/"},
        )
        self.assertEqual(response["Location"], "/carrito/")
        self.assertIn("access_token", self.client.session)
        self.assertEqual(self.client.session["guest_cart"][FAKE_PRODUCT["id"]], 3)
        response = self.client.get("/carrito/")
        self.assertContains(response, "Selección pendiente de reservar")
        self.assertContains(response, "Reservar selección")
        self.client.post(
            f"/carrito/cantidad/{FAKE_PRODUCT['id']}/", {"quantity": 1, "bucket": "pending"}
        )
        self.api.change_cart.assert_not_called()
        self.assertEqual(self.client.session["guest_cart"][FAKE_PRODUCT["id"]], 1)
        self.client.post("/carrito/reservar/")
        self.assertNotIn("guest_cart", self.client.session)
        self.api.import_cart.assert_called_once()
        self.api.checkout.assert_not_called()

    def test_receipt_load_error_has_order_recovery_link_instead_of_product_error(self):
        self.login()
        self.api.order.side_effect = ApiError(503, "No pudimos cargar el pedido.")
        response = self.client.get("/pedidos/" + ORDER.id + "/")
        self.assertContains(response, "Ir a Mis pedidos", status_code=503)
        self.assertNotContains(response, "NO ENCONTRAMOS LA PIEZA", status_code=503)
