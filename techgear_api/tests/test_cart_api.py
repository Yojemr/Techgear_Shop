"""Pruebas HTTP de reservas, aislamiento y transacciones con almacenamiento en memoria."""

import asyncio
import copy
import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from app.api.dependencies import get_database
from app.core.config import Settings
from app.core.security import create_access_token
from app.main import app
from bson import Decimal128, ObjectId
from httpx import ASGITransport, AsyncClient
from pymongo.errors import OperationFailure


def matches(row, criteria):
    for key, value in criteria.items():
        current = bool(row.get("items")) if key == "items.0" else row.get(key)
        if isinstance(value, dict):
            for operator, expected in value.items():
                if operator == "$exists" and bool(current) != expected:
                    return False
                if operator in ("$lte", "$gt", "$gte"):
                    if current is None:
                        return False
                    if operator == "$lte" and not current <= expected:
                        return False
                    if operator == "$gt" and not current > expected:
                        return False
                    if operator == "$gte" and not current >= expected:
                        return False
        elif current != value:
            return False
    return True


class Cursor:
    def __init__(self, rows):
        self.rows = copy.deepcopy(rows)

    def sort(self, key, direction):
        self.rows.sort(key=lambda row: row[key], reverse=direction < 0)
        return self

    def skip(self, offset):
        self.rows = self.rows[offset:]
        return self

    def limit(self, limit):
        self.rows = self.rows[:limit]
        return self

    def __aiter__(self):
        async def iterate():
            for row in self.rows:
                yield row

        return iterate()


class Collection:
    def __init__(self):
        self.rows = {}
        self.fail_replace = False

    def find(self, criteria):
        return Cursor([row for row in self.rows.values() if matches(row, criteria)])

    async def find_one(self, criteria, **kwargs):
        return next(
            (copy.deepcopy(row) for row in self.rows.values() if matches(row, criteria)), None
        )

    async def update_one(self, criteria, update, **kwargs):
        row = next((row for row in self.rows.values() if matches(row, criteria)), None)
        if row is None:
            return SimpleNamespace(matched_count=0, modified_count=0)
        for key, value in update.get("$inc", {}).items():
            row[key] += value
        row.update(update.get("$set", {}))
        return SimpleNamespace(matched_count=1, modified_count=1)

    async def find_one_and_update(self, criteria, update, **kwargs):
        row = await self.find_one(criteria)
        if row is None:
            return None
        await self.update_one(criteria, update)
        return await self.find_one({"_id": row["_id"]})

    async def replace_one(self, criteria, document, *, upsert=False, **kwargs):
        if self.fail_replace:
            raise OperationFailure("simulated transaction failure")
        identifier = criteria["_id"]
        found = identifier in self.rows and matches(self.rows[identifier], criteria)
        if found or upsert:
            self.rows[identifier] = copy.deepcopy(document)
        return SimpleNamespace(matched_count=int(found))

    async def insert_one(self, document, **kwargs):
        identifier = document.get("_id", ObjectId())
        self.rows[identifier] = copy.deepcopy(document) | {"_id": identifier}
        return SimpleNamespace(inserted_id=identifier)


class Session:
    def __init__(self, database):
        self.database = database

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def with_transaction(self, callback):
        # Serializa las carreras y revierte todos los documentos cuando aborta el callback.
        async with self.database.lock:
            before = {
                name: copy.deepcopy(getattr(self.database, name).rows)
                for name in ("products", "carts", "orders", "users")
            }
            try:
                return await callback(self)
            except Exception:
                for name, rows in before.items():
                    getattr(self.database, name).rows = rows
                raise


class Database:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.products = Collection()
        self.carts = Collection()
        self.orders = Collection()
        self.users = Collection()
        self.client = self

    def start_session(self):
        return Session(self)


class CartApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = Database()
        self.product_id = ObjectId()
        self.db.products.rows[self.product_id] = {
            "_id": self.product_id,
            "sku": "TEST-CPU",
            "name": "Procesador de prueba",
            "brand": "Prueba",
            "category": "Procesadores",
            "description": "Solo pruebas",
            "specifications": {"Socket": "Prueba"},
            "price": Decimal128("100.25"),
            "stock": 5,
            "active": True,
            "currency": "COP",
            "image_url": "https://example.test/product.png",
        }
        settings = Settings(
            mongo_uri="mongodb://localhost", jwt_secret_key="s" * 64, _env_file=None
        )
        self.users = [ObjectId(), ObjectId()]
        self.headers = []
        for identifier in self.users:
            self.db.users.rows[identifier] = {"_id": identifier, "role": "customer"}
            token = create_access_token(str(identifier), "customer", settings)
            self.headers.append({"Authorization": "Bearer " + token})
        app.dependency_overrides[get_database] = lambda: self.db
        self.addCleanup(app.dependency_overrides.clear)
        patch("app.api.dependencies.get_settings", return_value=settings).start()
        self.addCleanup(patch.stopall)
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        self.addAsyncCleanup(self.client.aclose)

    async def add(self, quantity=3, user=0):
        return await self.client.post(
            f"/cart/items/{self.product_id}",
            json={"quantity": quantity},
            headers=self.headers[user],
        )

    @property
    def stock(self):
        return self.db.products.rows[self.product_id]["stock"]

    async def test_two_users_cannot_reserve_the_same_three_units(self):
        responses = await asyncio.gather(self.add(3, 0), self.add(3, 1))
        self.assertEqual(sorted(response.status_code for response in responses), [200, 409])
        self.assertEqual(self.stock, 2)
        self.assertEqual(sum(len(cart["items"]) for cart in self.db.carts.rows.values()), 1)

    async def test_change_remove_and_repeated_clear_restore_exact_inventory(self):
        self.assertEqual((await self.add()).json()["total"], "300.75")
        response = await self.client.put(
            f"/cart/items/{self.product_id}", json={"quantity": 1}, headers=self.headers[0]
        )
        self.assertEqual(response.json()["items"][0]["quantity"], 1)
        self.assertEqual(self.stock, 4)
        for _ in range(2):
            self.assertEqual(
                (await self.client.delete("/cart/", headers=self.headers[0])).status_code, 200
            )
        self.assertEqual(self.stock, 5)

    async def test_cart_is_private_and_rejects_price_and_owner_injection(self):
        await self.add()
        own = await self.client.get("/cart/", headers=self.headers[0])
        other = await self.client.get("/cart/", headers=self.headers[1])
        self.assertEqual(len(own.json()["items"]), 1)
        self.assertEqual(other.json()["items"], [])
        self.assertEqual((await self.client.get("/cart/")).status_code, 401)
        for quantity in (-1, 100, True, "3"):
            response = await self.client.post(
                f"/cart/items/{self.product_id}",
                json={"quantity": quantity},
                headers=self.headers[1],
            )
            self.assertEqual(response.status_code, 422)
        injected = await self.client.post(
            f"/cart/items/{self.product_id}",
            json={"quantity": 1, "customer_id": str(self.users[0]), "price": "0"},
            headers=self.headers[1],
        )
        self.assertEqual(injected.status_code, 422)
        self.assertEqual(self.stock, 2)

    async def test_checkout_is_idempotent_keeps_snapshots_and_does_not_discount_twice(self):
        cart = (await self.add()).json()
        payload = {"version": cart["version"], "expected_total": cart["total"]}
        responses = await asyncio.gather(
            *[
                self.client.post("/cart/checkout", json=payload, headers=self.headers[0])
                for _ in range(2)
            ]
        )
        self.assertEqual([response.status_code for response in responses], [200, 200])
        self.assertEqual(responses[0].json()["id"], responses[1].json()["id"])
        self.assertEqual(len(self.db.orders.rows), 1)
        self.assertEqual(self.stock, 2)
        self.assertNotIn("payment", responses[0].json())
        self.assertEqual(responses[0].json()["items"][0]["unit_price"], "100.25")
        self.assertEqual(
            (await self.client.get("/cart/", headers=self.headers[0])).json()["items"], []
        )
        denied = await self.client.get("/orders/" + cart["version"], headers=self.headers[1])
        self.assertEqual(denied.status_code, 404)
        await self.client.delete("/cart/", headers=self.headers[0])
        self.assertEqual(self.stock, 2)

    async def test_changed_version_or_price_cannot_be_silently_confirmed(self):
        cart = (await self.add()).json()
        self.db.products.rows[self.product_id]["price"] = Decimal128("200.25")
        response = await self.client.post(
            "/cart/checkout",
            headers=self.headers[0],
            json={"version": cart["version"], "expected_total": cart["total"]},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.stock, 2)
        self.assertEqual(len(self.db.orders.rows), 0)
        await self.add(1)
        response = await self.client.post(
            "/cart/checkout",
            headers=self.headers[0],
            json={"version": cart["version"], "expected_total": "801.00"},
        )
        self.assertEqual(response.status_code, 409)

    async def test_closed_browser_reservation_is_released_before_next_catalog_read(self):
        await self.add()
        self.db.carts.rows[self.users[0]]["expires_at"] = datetime.now(UTC) - timedelta(seconds=1)
        response = await self.client.get("/products/")
        self.assertEqual(response.json()[0]["stock"], 5)
        self.assertEqual(self.stock, 5)
        response = await self.client.post("/cart/heartbeat", headers=self.headers[0])
        self.assertEqual(response.json()["count"], 0)
        self.assertEqual(self.stock, 5)

    async def test_presence_renews_and_transaction_failure_rolls_back_reservation(self):
        await self.add()
        self.db.carts.rows[self.users[0]]["expires_at"] = datetime.now(UTC) + timedelta(seconds=10)
        response = await self.client.post("/cart/heartbeat", headers=self.headers[0])
        self.assertEqual(response.json()["count"], 3)
        self.assertGreater(
            self.db.carts.rows[self.users[0]]["expires_at"],
            datetime.now(UTC) + timedelta(seconds=100),
        )
        self.db.carts.fail_replace = True
        response = await self.add(1)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.stock, 2)
        self.assertEqual(self.db.carts.rows[self.users[0]]["items"][0]["quantity"], 3)

    async def test_inactive_item_can_be_returned_but_cannot_be_confirmed(self):
        cart = (await self.add()).json()
        self.db.products.rows[self.product_id]["active"] = False
        response = await self.client.post(
            "/cart/checkout",
            headers=self.headers[0],
            json={"version": cart["version"], "expected_total": cart["total"]},
        )
        self.assertEqual(response.status_code, 409)
        await self.client.delete("/cart/", headers=self.headers[0])
        self.assertEqual(self.stock, 5)

    async def test_expired_cart_cannot_be_confirmed_and_is_not_restocked_twice(self):
        cart = (await self.add()).json()
        self.db.carts.rows[self.users[0]]["expires_at"] = datetime.now(UTC) - timedelta(seconds=1)
        response = await self.client.post(
            "/cart/checkout",
            headers=self.headers[0],
            json={"version": cart["version"], "expected_total": cart["total"]},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.stock, 5)
        await self.client.delete("/cart/", headers=self.headers[0])
        self.assertEqual(self.stock, 5)
        self.assertEqual(len(self.db.orders.rows), 0)

    async def test_money_overflow_aborts_reservation(self):
        self.db.products.rows[self.product_id]["price"] = Decimal128("99999999999999.99")
        response = await self.add(3)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.stock, 5)
        self.assertEqual(len(self.db.carts.rows), 0)

    async def test_guest_import_is_atomic_authenticated_and_safe_to_retry(self):
        payload = {
            "transfer_id": "a" * 24,
            "items": [{"product_id": str(self.product_id), "quantity": 3}],
        }
        self.assertEqual((await self.client.post("/cart/import", json=payload)).status_code, 401)
        self.assertEqual(self.stock, 5)
        for _ in range(2):
            response = await self.client.post("/cart/import", json=payload, headers=self.headers[0])
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["items"][0]["quantity"], 3)
        self.assertEqual(self.stock, 2)

    async def test_import_failure_rolls_back_every_product(self):
        other_id = ObjectId()
        self.db.products.rows[other_id] = self.db.products.rows[self.product_id].copy() | {
            "_id": other_id,
            "stock": 1,
            "sku": "OTRO",
        }
        payload = {
            "transfer_id": "c" * 24,
            "items": [
                {"product_id": str(self.product_id), "quantity": 3},
                {"product_id": str(other_id), "quantity": 2},
            ],
        }
        response = await self.client.post("/cart/import", json=payload, headers=self.headers[0])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.stock, 5)
        self.assertEqual(self.db.products.rows[other_id]["stock"], 1)
        self.assertEqual(len(self.db.carts.rows), 0)

    async def test_order_can_be_read_after_bson_round_trip_with_database_codec(self):
        import app.db.mongodb as mongodb
        from bson import BSON
        from bson.codec_options import CodecOptions
        from pymongo import AsyncMongoClient

        cart = (await self.add()).json()
        response = await self.client.post(
            "/cart/checkout",
            headers=self.headers[0],
            json={"version": cart["version"], "expected_total": cart["total"]},
        )
        self.assertEqual(response.status_code, 200)
        identifier = ObjectId(response.json()["id"])

        # Usa el códec configurado por la conexión real, sin abrir ninguna red.
        def offline_client(*args, **kwargs):
            kwargs.pop("appname", None)
            return AsyncMongoClient("mongodb://127.0.0.1:1", connect=False, **kwargs)

        settings = Settings(
            mongo_uri="mongodb://localhost", jwt_secret_key="s" * 64, _env_file=None
        )
        with (
            patch.object(mongodb, "AsyncMongoClient", side_effect=offline_client),
            patch("pymongo.asynchronous.database.AsyncDatabase.command", return_value={"ok": 1}),
        ):
            async with mongodb.mongo_connection(settings) as database:
                codec = database.codec_options
                self.assertTrue(codec.tz_aware)
                self.db.orders.rows[identifier] = BSON(
                    BSON.encode(self.db.orders.rows[identifier])
                ).decode(codec_options=CodecOptions(tz_aware=codec.tz_aware))
        receipt = await self.client.get("/orders/" + str(identifier), headers=self.headers[0])
        self.assertEqual(receipt.status_code, 200)
        self.assertEqual(receipt.json()["items"][0]["quantity"], 3)
        self.assertEqual(receipt.json()["total"], "300.75")
        history = await self.client.get("/orders/", headers=self.headers[0])
        self.assertEqual(history.status_code, 200)
        self.assertEqual(len(history.json()), 1)

    async def test_stock_is_conserved_through_two_carts_checkout_and_rejection(self):
        """Disponible + reservado + vendido debe sumar las cinco unidades iniciales."""
        admin_id = ObjectId()
        self.db.users.rows[admin_id] = {"_id": admin_id, "role": "admin"}
        settings = Settings(
            mongo_uri="mongodb://localhost", jwt_secret_key="s" * 64, _env_file=None
        )
        admin = {"Authorization": "Bearer " + create_access_token(str(admin_id), "admin", settings)}
        self.assertEqual((await self.add(3, 0)).status_code, 200)
        self.assertEqual((await self.add(2, 1)).status_code, 200)
        self.assertEqual(self.stock, 0)
        self.assertEqual((await self.add(1, 1)).status_code, 409)
        cart = (await self.client.get("/cart/", headers=self.headers[0])).json()
        response = await self.client.post(
            "/cart/checkout",
            headers=self.headers[0],
            json={"version": cart["version"], "expected_total": cart["total"]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.stock, 0)
        self.assertEqual(
            (await self.client.delete("/cart/", headers=self.headers[1])).status_code, 200
        )
        self.assertEqual(self.stock, 2)
        response = await self.client.patch(
            "/orders/" + response.json()["id"] + "/status",
            headers=admin,
            json={"status": "cancelled"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.stock, 5)
        for header in self.headers:
            await self.client.delete("/cart/", headers=header)
        self.assertEqual(self.stock, 5)

    async def test_stale_product_edit_cannot_undo_a_customer_reservation(self):
        """Una ficha abierta con cinco unidades no puede sobreescribir una reserva posterior."""
        self.db.users.rows[self.users[1]]["role"] = "admin"
        product = (await self.client.get(f"/products/{self.product_id}")).json()
        product.pop("id")
        product["expected_stock"] = product["stock"]
        self.assertEqual((await self.add(3)).status_code, 200)
        response = await self.client.put(
            f"/products/{self.product_id}", headers=self.headers[1], json=product
        )
        self.assertEqual(response.status_code, 412)
        self.assertEqual(self.stock, 2)
        without_snapshot = {key: value for key, value in product.items() if key != "expected_stock"}
        response = await self.client.put(
            f"/products/{self.product_id}", headers=self.headers[1], json=without_snapshot
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.stock, 2)
        # Después de releer el stock, sí puede modificar nombre u otras características.
        product.update({"stock": 2, "expected_stock": 2, "name": "Nombre actualizado"})
        response = await self.client.put(
            f"/products/{self.product_id}", headers=self.headers[1], json=product
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("expected_stock", response.json())
        await self.client.delete("/cart/", headers=self.headers[0])
        self.assertEqual(self.stock, 5)

    async def test_checkout_storage_failure_keeps_reservation_and_never_duplicates_sale(self):
        cart = (await self.add(3)).json()
        payload = {"version": cart["version"], "expected_total": cart["total"]}
        self.db.carts.fail_replace = True
        response = await self.client.post("/cart/checkout", headers=self.headers[0], json=payload)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.stock, 2)
        self.assertEqual(len(self.db.orders.rows), 0)
        self.assertEqual(self.db.carts.rows[self.users[0]]["items"][0]["quantity"], 3)
        self.db.carts.fail_replace = False
        response = await self.client.post("/cart/checkout", headers=self.headers[0], json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.stock, 2)
        self.assertEqual(len(self.db.orders.rows), 1)
