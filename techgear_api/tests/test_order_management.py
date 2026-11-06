"""Gestión administrativa con transacciones simuladas y usuarios ficticios."""

import asyncio
import unittest

import test_cart_api as cart_fixture
from bson import ObjectId


class OrderManagementTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await cart_fixture.CartApiTests.asyncSetUp(self)
        self.customer = self.headers[0]
        self.admin = self.headers[1]
        self.db.users.rows[self.users[1]]["role"] = "admin"
        self.db.users.rows[self.users[0]].update(
            {
                "full_name": "Cliente ficticio",
                "email": "cliente@example.test",
                "password_hash": "never-expose-this",
            }
        )
        response = await self.client.post(
            "/orders/",
            headers=self.customer,
            json={
                "items": [{"product_id": str(self.product_id), "quantity": 2}],
            },
        )
        self.assertEqual(response.status_code, 201)
        self.path = "/orders/" + response.json()["id"]

    async def transition(self, state, expected=None):
        payload = {"status": state}
        if expected:
            payload["expected_status"] = expected
        return await self.client.patch(self.path + "/status", headers=self.admin, json=payload)

    def stock(self):
        return self.db.products.rows[self.product_id]["stock"]

    async def test_return_requires_delivery_and_repeated_return_never_adds_twice(self):
        self.assertEqual((await self.transition("returned")).status_code, 409)
        for state in ("preparing", "shipped", "delivered", "returned"):
            response = await self.transition(state)
            self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.stock(), 5)
        self.assertEqual((await self.transition("returned")).status_code, 409)
        self.assertEqual(self.stock(), 5)
        receipt = await self.client.get(self.path, headers=self.customer)
        self.assertEqual(receipt.json()["status"], "returned")
        self.assertEqual(len(receipt.json()["updates"]), 4)

    async def test_concurrent_rejections_restore_inventory_once(self):
        results = await asyncio.gather(self.transition("cancelled"), self.transition("cancelled"))
        self.assertEqual(sorted(r.status_code for r in results), [200, 409])
        self.assertEqual(self.stock(), 5)

    async def test_stale_status_cannot_reject_after_another_admin_changed_it(self):
        self.assertEqual((await self.transition("preparing")).status_code, 200)
        self.assertEqual((await self.transition("cancelled", "confirmed")).status_code, 409)
        self.assertEqual(self.stock(), 3)

    async def test_missing_product_aborts_restock_and_keeps_order_status(self):
        self.db.products.rows.clear()
        self.assertEqual((await self.transition("cancelled")).status_code, 409)
        receipt = await self.client.get(self.path, headers=self.customer)
        self.assertEqual(receipt.json()["status"], "confirmed")

    async def test_notifications_are_internal_idempotent_and_owner_only(self):
        payload = {"message": "Tus piezas están listas.", "request_id": str(ObjectId())}
        for _ in range(2):
            response = await self.client.post(
                self.path + "/notifications", headers=self.admin, json=payload
            )
            self.assertEqual(response.status_code, 200, response.text)
        receipt = await self.client.get(self.path, headers=self.customer)
        self.assertEqual(len(receipt.json()["updates"]), 1)
        self.assertEqual(receipt.json()["updates"][0]["message"], payload["message"])
        self.assertIsNone(receipt.json()["customer"])
        self.assertEqual(self.stock(), 3)
        self.db.users.rows[self.users[1]]["role"] = "customer"
        self.assertEqual((await self.client.get(self.path, headers=self.admin)).status_code, 404)
        self.assertEqual(
            (
                await self.client.post(
                    self.path + "/notifications", headers=self.admin, json=payload
                )
            ).status_code,
            403,
        )
        self.assertEqual(
            (
                await self.client.patch(
                    self.path + "/status", headers=self.customer, json={"status": "preparing"}
                )
            ).status_code,
            403,
        )

    async def test_admin_contact_allowlist_filters_and_customer_isolation(self):
        receipt = await self.client.get(self.path, headers=self.admin)
        self.assertEqual(
            receipt.json()["customer"],
            {"full_name": "Cliente ficticio", "email": "cliente@example.test"},
        )
        self.assertNotIn("never-expose-this", receipt.text)
        await self.transition("preparing")
        response = await self.client.get("/orders/?order_status=confirmed", headers=self.admin)
        self.assertEqual(response.json(), [])
        response = await self.client.get("/orders/?order_status=preparing", headers=self.admin)
        self.assertEqual(len(response.json()), 1)
        response = await self.client.get("/orders/?mine=true", headers=self.admin)
        self.assertEqual(response.json(), [])

    async def test_blank_notification_rejected_and_failure_rolls_back_inventory(self):
        response = await self.client.post(
            self.path + "/notifications",
            headers=self.admin,
            json={"request_id": str(ObjectId()), "message": "   "},
        )
        self.assertEqual(response.status_code, 422)
        self.db.orders.fail_replace = True
        self.assertEqual((await self.transition("cancelled")).status_code, 503)
        self.assertEqual(self.stock(), 3)
