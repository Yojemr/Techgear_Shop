"""Pruebas de stock y cancelación usando sesiones MongoDB simuladas."""

import unittest
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.api.orders import create_order, update_order_status
from app.schemas.order import OrderCreate, OrderStatus, OrderStatusUpdate
from bson import Decimal128, ObjectId
from fastapi import HTTPException


class FakeSession:
    """Ejecuta el callback transaccional una vez en la base simulada."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def with_transaction(self, callback):
        return await callback(self)


class OrderOperationTests(unittest.IsolatedAsyncioTestCase):
    """Protege el inventario y la devolución al cancelar antes del envío."""

    def setUp(self):
        self.customer_id = ObjectId()
        self.product_id = ObjectId()
        self.order_id = ObjectId()
        self.product = {
            "_id": self.product_id,
            "sku": "DEMO-001",
            "name": "Producto ficticio",
            "price": Decimal128("0.10"),
            "stock": 5,
            "active": True,
        }
        self.products = SimpleNamespace(
            find_one=AsyncMock(return_value=self.product),
            update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1)),
        )
        self.orders = SimpleNamespace(
            insert_one=AsyncMock(),
            find_one=AsyncMock(),
            replace_one=AsyncMock(return_value=SimpleNamespace(matched_count=1)),
        )
        self.database = SimpleNamespace(
            products=self.products,
            orders=self.orders,
            client=SimpleNamespace(start_session=AsyncMock(return_value=FakeSession())),
        )
        self.customer = {"_id": self.customer_id, "role": "customer"}

    async def test_confirmed_order_uses_server_price_and_decrements_stock(self):
        result = await create_order(
            OrderCreate(items=[{"product_id": str(self.product_id), "quantity": 3}]),
            self.database,
            self.customer,
        )
        self.assertEqual(result["total"], Decimal("0.30"))
        self.assertEqual(result["items"][0]["unit_price"], Decimal("0.10"))
        self.assertEqual(result["customer_id"], str(self.customer_id))
        self.assertEqual(result["status"], OrderStatus.CONFIRMED)
        self.products.update_one.assert_awaited_once()
        self.orders.insert_one.assert_awaited_once()

    async def test_insufficient_stock_does_not_write_order_or_stock(self):
        self.product["stock"] = 1
        with self.assertRaises(HTTPException) as caught:
            await create_order(
                OrderCreate(items=[{"product_id": str(self.product_id), "quantity": 2}]),
                self.database,
                self.customer,
            )
        self.assertEqual(caught.exception.status_code, 409)
        self.products.update_one.assert_not_awaited()
        self.orders.insert_one.assert_not_awaited()

    async def test_cancel_restores_inventory_and_updates_status(self):
        self.orders.find_one.return_value = {
            "_id": self.order_id,
            "customer_id": self.customer_id,
            "items": [{"product_id": self.product_id, "quantity": 2}],
            "total": Decimal128("0.20"),
            "currency": "COP",
            "created_at": datetime.now(UTC),
            "status": OrderStatus.PREPARING,
        }
        result = await update_order_status(
            str(self.order_id),
            OrderStatusUpdate(status=OrderStatus.CANCELLED),
            self.database,
            {"_id": ObjectId(), "role": "admin"},
        )
        self.assertEqual(result["status"], OrderStatus.CANCELLED)
        self.products.update_one.assert_awaited_once()
        self.orders.replace_one.assert_awaited_once()

    async def test_shipped_order_cannot_be_cancelled_or_restocked(self):
        self.orders.find_one.return_value = {
            "_id": self.order_id,
            "customer_id": self.customer_id,
            "items": [{"product_id": self.product_id, "quantity": 2}],
            "total": Decimal128("0.20"),
            "currency": "COP",
            "created_at": datetime.now(UTC),
            "status": OrderStatus.SHIPPED,
        }
        with self.assertRaises(HTTPException) as caught:
            await update_order_status(
                str(self.order_id),
                OrderStatusUpdate(status=OrderStatus.CANCELLED),
                self.database,
                {"_id": ObjectId(), "role": "admin"},
            )
        self.assertEqual(caught.exception.status_code, 409)
        self.products.update_one.assert_not_awaited()
        self.orders.replace_one.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
