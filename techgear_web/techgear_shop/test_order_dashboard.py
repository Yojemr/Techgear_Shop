"""Panel de pedidos con API simulada, sin credenciales ni escrituras en Atlas."""

import time
from dataclasses import replace
from unittest.mock import patch

from django.test import Client, SimpleTestCase, override_settings

from .services.api import ApiClient, ApiError
from .test_cart import ORDER
from .tests import FAKE_PROFILE


@override_settings(
    SESSION_ENGINE="django.contrib.sessions.backends.cache",
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "orders-tests",
        }
    },
    ALLOWED_HOSTS=["testserver"],
)
class OrderDashboardTests(SimpleTestCase):
    def setUp(self):
        self.api = patch("techgear_shop.order_dashboard.ApiClient").start().return_value
        self.auth = patch("techgear_shop.middleware.ApiClient").start().return_value
        self.cart = patch("techgear_shop.cart.ApiClient").start().return_value
        self.addCleanup(patch.stopall)
        self.auth.profile.return_value = FAKE_PROFILE | {"role": "admin"}
        self.order = replace(
            ORDER,
            customer_id=FAKE_PROFILE["id"],
            customer={"full_name": "Cliente ficticio", "email": "cliente@example.test"},
            updates=[{"message": "<script>test</script>", "created_at": "2026-11-05T12:00:00Z"}],
        )
        self.api.order.return_value = self.order
        self.api.managed_orders.return_value = [self.order]
        self.cart.order.return_value = self.order
        self.path = "/gestion/pedidos/" + ORDER.id + "/"

    def login(self, client=None):
        session = (client or self.client).session
        session["access_token"] = "test-private-token"
        session["auth_expires_at"] = int(time.time()) + 1800
        session.save()

    def post(self, action="preparing", **extra):
        return self.client.post(
            self.path,
            {
                "action": action,
                "expected_status": "confirmed",
                "request_id": "a" * 24,
                "message": "",
                **extra,
            },
        )

    def test_admin_can_read_other_users_orders_and_follow_pagination(self):
        self.login()
        self.api.managed_orders.return_value = [self.order] * 21
        response = self.client.get("/gestion/pedidos/", {"state": "confirmed", "page": 2})
        self.assertContains(response, "Pedidos de clientes")
        self.assertContains(response, "Siguiente")
        self.assertEqual(len(response.context["orders"]), 20)
        self.api.managed_orders.assert_called_once_with(
            "test-private-token", state="confirmed", page=2
        )
        self.assertNotContains(response, "test-private-token")

    def test_customer_and_guest_cannot_enter_administration(self):
        self.assertEqual(self.client.get(self.path).status_code, 302)
        self.login()
        self.auth.profile.return_value = FAKE_PROFILE
        self.assertEqual(self.client.get(self.path).status_code, 403)
        self.assertEqual(self.post().status_code, 403)
        self.api.order.assert_not_called()
        self.api.update_order.assert_not_called()

    def test_actions_contact_and_notifications_are_escaped_and_render_by_state(self):
        self.login()
        response = self.client.get(self.path)
        self.assertContains(response, "Aceptar y preparar")
        self.assertContains(response, "cliente@example.test")
        self.assertContains(response, "&lt;script&gt;test&lt;/script&gt;")
        self.assertNotContains(response, "Registrar devolución")
        self.api.order.return_value = replace(self.order, status="delivered")
        response = self.client.get(self.path)
        self.assertContains(response, "Registrar devolución")
        self.assertNotContains(response, "Rechazar pedido")

    def test_update_and_notify_use_api_and_redirect_after_success(self):
        self.login()
        self.assertEqual(self.post().status_code, 302)
        self.api.update_order.assert_called_once_with(
            ORDER.id, "preparing", "confirmed", "", "test-private-token"
        )
        self.assertEqual(self.post("notify", message="Listo para despacho").status_code, 302)
        self.api.notify_order.assert_called_once_with(
            ORDER.id, "Listo para despacho", "a" * 24, "test-private-token"
        )

    def test_empty_message_and_csrf_rejected_without_mutation(self):
        self.login()
        self.assertEqual(self.post("notify").status_code, 400)
        self.api.notify_order.assert_not_called()
        protected = Client(enforce_csrf_checks=True)
        self.login(protected)
        self.assertEqual(protected.post(self.path, {"action": "preparing"}).status_code, 403)
        self.api.update_order.assert_not_called()

    def test_stale_action_keeps_message_and_token_private(self):
        self.login()
        self.api.update_order.side_effect = ApiError(409, "El pedido cambió.")
        response = self.post(message="Nota que debe conservarse")
        self.assertContains(response, "El pedido cambió.", status_code=409)
        self.assertContains(response, "Nota que debe conservarse", status_code=409)
        self.assertNotContains(response, "test-private-token", status_code=409)

    def test_customer_can_see_internal_messages_on_receipt(self):
        self.login()
        self.auth.profile.return_value = FAKE_PROFILE
        response = self.client.get("/pedidos/" + ORDER.id + "/")
        self.assertContains(response, "Novedades del pedido")
        self.assertContains(response, "&lt;script&gt;test&lt;/script&gt;")

    def test_client_admin_pagination_and_safe_order_conflicts(self):
        with patch.object(ApiClient, "_request", return_value=[]) as request:
            self.assertEqual(ApiClient().managed_orders("token", state="returned", page=3), [])
            self.assertEqual(
                request.call_args.kwargs["params"],
                {"mine": False, "limit": 21, "offset": 40, "order_status": "returned"},
            )
