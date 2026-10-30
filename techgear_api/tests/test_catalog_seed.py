"""Comprueba la carga idempotente con una colección simulada."""

from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase

from app.db.catalog import insert_missing_products, load_reference_products


class FakeProducts:
    def __init__(self):
        self.documents = {}

    async def update_one(self, criteria, update, upsert=False):
        sku = criteria["sku"]
        self.last_update = update
        if sku in self.documents:
            return SimpleNamespace(upserted_id=None)
        self.documents[sku] = dict(update["$setOnInsert"])
        return SimpleNamespace(upserted_id="fake-" + sku)


class CatalogSeedTests(IsolatedAsyncioTestCase):
    async def test_repeat_does_not_reset_stock_or_overwrite_existing_price(self):
        products = load_reference_products(stock=5)
        fake = FakeProducts()
        database = SimpleNamespace(products=fake)
        self.assertEqual(await insert_missing_products(database, products), len(products))
        sku = products[0].sku
        fake.documents[sku]["stock"] = 3
        fake.documents[sku]["price"] = "edited-price"
        self.assertEqual(await insert_missing_products(database, products), 0)
        self.assertEqual(fake.documents[sku]["stock"], 3)
        self.assertEqual(fake.documents[sku]["price"], "edited-price")
        self.assertEqual(set(fake.last_update), {"$setOnInsert"})

    def test_initial_stock_is_explicit_and_can_be_zero(self):
        self.assertTrue(all(product.stock == 0 for product in load_reference_products(stock=0)))
        with self.assertRaises(ValueError):
            load_reference_products(stock=-1)
