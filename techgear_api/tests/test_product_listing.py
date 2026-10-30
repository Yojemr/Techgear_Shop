"""Lecturas pública y administrativa de productos, sin MongoDB real."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.api.dependencies import get_database, require_admin
from app.main import app
from bson import Decimal128, ObjectId
from httpx import ASGITransport, AsyncClient


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *_):
        return self

    def skip(self, *_):
        return self

    def limit(self, *_):
        return self

    def __aiter__(self):
        async def iterate():
            for row in self.rows:
                yield row

        return iterate()


class ProductListingTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_query_excludes_inactive_while_admin_query_includes_them(self):
        document = {
            "_id": ObjectId(),
            "sku": "TEST-01",
            "name": "Componente de prueba",
            "brand": "Prueba",
            "category": "Procesadores",
            "description": "Solo pruebas",
            "specifications": {"Socket": "AM5"},
            "price": Decimal128("100.25"),
            "currency": "COP",
            "stock": 5,
            "image_url": "https://example.test/cpu.png",
            "active": False,
        }
        products = Mock()
        products.find.side_effect = lambda criteria: Cursor(
            [] if criteria.get("active") is True else [document]
        )
        database = SimpleNamespace(products=products)
        # Los overrides existen solo durante esta prueba y no abren el lifespan de Atlas.
        with patch.dict(
            app.dependency_overrides,
            {
                get_database: lambda: database,
                require_admin: lambda: {"role": "admin"},
            },
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                public = await client.get("/products/")
                managed = await client.get("/products/manage/")
        self.assertEqual(public.status_code, 200)
        self.assertEqual(public.json(), [])
        self.assertEqual(managed.status_code, 200)
        self.assertFalse(managed.json()[0]["active"])
        self.assertEqual(products.find.call_args_list[0].args[0], {"active": True})
        self.assertEqual(products.find.call_args_list[1].args[0], {})
