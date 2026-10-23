import unittest
from decimal import Decimal

from app.schemas.order import OrderCreate, OrderItemRead, OrderRead
from app.schemas.product import ProductCreate
from pydantic import ValidationError

PRODUCT_ID = "0123456789abcdef01234567"


def product_payload():
    return {
        "sku": "TEST-001",
        "name": "Producto de prueba",
        "brand": "Marca de prueba",
        "category": "Memoria",
        "description": "Datos ficticios para validación",
        "specifications": {"Capacidad": "16 GB"},
        "price": "125000.50",
        "stock": 4,
        "image_url": "https://example.com/product.png",
    }


class SchemaTests(unittest.TestCase):
    def test_price_keeps_decimal_precision_and_json_roundtrip(self):
        product = ProductCreate(**product_payload())
        self.assertEqual(product.price, Decimal("125000.50"))
        self.assertEqual(ProductCreate.model_validate_json(product.model_dump_json()), product)

    def test_invalid_products_are_rejected(self):
        cases = [
            {"price": "-1"},
            {"price": "1.001"},
            {"price": "NaN"},
            {"stock": -1},
            {"stock": 1.5},
            {"stock": True},
            {"specifications": {}},
            {"specifications": {"RAM": " "}},
            {"sku": " "},
            {"image_url": "not-a-url"},
            {"currency": "USD"},
        ]
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                ProductCreate(**(product_payload() | changes))

    def test_order_input_cannot_supply_prices_total_or_customer_identity(self):
        payload = {"items": [{"product_id": PRODUCT_ID, "quantity": 2}]}
        self.assertEqual(OrderCreate(**payload).items[0].quantity, 2)
        for injected in ({"total": "1"}, {"customer_id": "another-user"}):
            with self.subTest(injected=injected), self.assertRaises(ValidationError):
                OrderCreate(**(payload | injected))
        with self.assertRaises(ValidationError):
            OrderCreate(items=[{"product_id": PRODUCT_ID, "quantity": 1, "unit_price": "1"}])

    def test_empty_order_bad_ids_and_invalid_quantities_are_rejected(self):
        for items in (
            [],
            [{"product_id": "bad", "quantity": 1}],
            [{"product_id": PRODUCT_ID, "quantity": 0}],
            [{"product_id": PRODUCT_ID, "quantity": 1.5}],
        ):
            with self.subTest(items=items), self.assertRaises(ValidationError):
                OrderCreate(items=items)

    def test_order_snapshot_requires_consistent_amounts_and_aware_date(self):
        item = {
            "product_id": PRODUCT_ID,
            "quantity": 3,
            "sku": "TEST-001",
            "name": "Producto de prueba",
            "unit_price": "0.10",
            "subtotal": "0.30",
        }
        order = {
            "id": PRODUCT_ID,
            "customer_id": "customer-test",
            "items": [item],
            "total": "0.30",
            "created_at": "2026-10-23T12:00:00Z",
        }
        self.assertEqual(OrderRead(**order).total, Decimal("0.30"))
        with self.assertRaises(ValidationError):
            OrderItemRead(**(item | {"subtotal": "0.29"}))
        with self.assertRaises(ValidationError):
            OrderRead(**(order | {"total": "0.29"}))
        with self.assertRaises(ValidationError):
            OrderRead(**(order | {"created_at": "2026-10-23T12:00:00"}))


if __name__ == "__main__":
    unittest.main()
