"""Pruebas HTTP de registro y sesión con una colección de usuarios en memoria."""

import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import patch

from app.core.config import Settings
from app.core.security import hash_password
from app.main import app
from bson import ObjectId
from httpx import ASGITransport, AsyncClient


class MemoryUsers:
    """Simula las operaciones mínimas de usuarios sin abrir una conexión externa."""

    def __init__(self):
        self.documents = {}

    async def insert_one(self, document):
        email = document["email"]
        if any(existing["email"] == email for existing in self.documents.values()):
            from pymongo.errors import DuplicateKeyError

            raise DuplicateKeyError("duplicate")
        user_id = ObjectId()
        self.documents[user_id] = document.copy() | {"_id": user_id}
        return SimpleNamespace(inserted_id=user_id)

    async def find_one(self, criteria):
        return next(
            (
                document
                for document in self.documents.values()
                if all(document.get(key) == value for key, value in criteria.items())
            ),
            None,
        )


class MemoryProducts:
    """Implementa las operaciones usadas por el CRUD de productos en pruebas."""

    def __init__(self):
        self.documents = {}

    async def insert_one(self, document):
        product_id = ObjectId()
        self.documents[product_id] = document.copy() | {"_id": product_id}
        return SimpleNamespace(inserted_id=product_id)

    async def find_one(self, criteria):
        return next(
            (
                document
                for document in self.documents.values()
                if all(document.get(key) == value for key, value in criteria.items())
            ),
            None,
        )

    async def find_one_and_update(self, criteria, update, return_document=True):
        document = await self.find_one(criteria)
        if document is None:
            return None
        document.update(update["$set"])
        return document

    async def update_one(self, criteria, update):
        document = await self.find_one(criteria)
        if document is None:
            return SimpleNamespace(matched_count=0)
        document.update(update["$set"])
        return SimpleNamespace(matched_count=1)


class AuthApiTests(unittest.IsolatedAsyncioTestCase):
    """Comprueba el contrato público y que el perfil no exponga hashes."""

    async def test_register_login_and_profile(self):
        database = SimpleNamespace(users=MemoryUsers())
        settings = Settings(
            mongo_uri="mongodb://localhost",
            jwt_secret_key="s" * 64,
            _env_file=None,
        )

        @asynccontextmanager
        async def fake_connection(_settings):
            yield database

        with (
            patch("app.main.mongo_connection", fake_connection),
            patch("app.main.get_settings", return_value=settings),
            patch("app.api.auth.get_settings", return_value=settings),
            patch("app.api.dependencies.get_settings", return_value=settings),
        ):
            async with app.router.lifespan_context(app):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    registration = await client.post(
                        "/auth/register",
                        json={
                            "full_name": "Cliente Demo",
                            "email": "cliente@example.com",
                            "password": "Clave-segura-123",
                        },
                    )
                    self.assertEqual(registration.status_code, 201)
                    self.assertEqual(registration.json()["role"], "customer")
                    self.assertNotIn("password", registration.json())
                    self.assertNotIn("password_hash", registration.json())

                    login = await client.post(
                        "/auth/login",
                        json={"email": "CLIENTE@example.com", "password": "Clave-segura-123"},
                    )
                    self.assertEqual(login.status_code, 200)
                    self.assertEqual(login.json()["token_type"], "bearer")
                    token = login.json()["access_token"]

                    profile = await client.get(
                        "/users/me", headers={"Authorization": f"Bearer {token}"}
                    )
                    self.assertEqual(profile.status_code, 200)
                    self.assertEqual(profile.json()["email"], "cliente@example.com")
                    self.assertNotIn("password_hash", profile.json())

                    wrong_password = await client.post(
                        "/auth/login",
                        json={"email": "cliente@example.com", "password": "incorrecta"},
                    )
                    self.assertEqual(wrong_password.status_code, 401)
                    missing_token = await client.get("/users/me")
                    self.assertEqual(missing_token.status_code, 401)

                    role_escalation = await client.post(
                        "/auth/register",
                        json={
                            "full_name": "Admin falso",
                            "email": "falso@example.com",
                            "password": "Clave-segura-123",
                            "role": "admin",
                        },
                    )
                    self.assertEqual(role_escalation.status_code, 422)

    async def test_customer_cannot_create_products(self):
        database = SimpleNamespace(users=MemoryUsers())
        settings = Settings(
            mongo_uri="mongodb://localhost",
            jwt_secret_key="s" * 64,
            _env_file=None,
        )

        @asynccontextmanager
        async def fake_connection(_settings):
            yield database

        with (
            patch("app.main.mongo_connection", fake_connection),
            patch("app.main.get_settings", return_value=settings),
            patch("app.api.auth.get_settings", return_value=settings),
            patch("app.api.dependencies.get_settings", return_value=settings),
        ):
            async with app.router.lifespan_context(app):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    await client.post(
                        "/auth/register",
                        json={
                            "full_name": "Cliente Demo",
                            "email": "cliente@example.com",
                            "password": "Clave-segura-123",
                        },
                    )
                    login = await client.post(
                        "/auth/login",
                        json={"email": "cliente@example.com", "password": "Clave-segura-123"},
                    )
                    response = await client.post(
                        "/products/",
                        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
                        json={},
                    )
                    self.assertEqual(response.status_code, 403)

    async def test_admin_can_create_read_update_and_deactivate_product(self):
        users = MemoryUsers()
        admin_id = ObjectId()
        users.documents[admin_id] = {
            "_id": admin_id,
            "full_name": "Admin Demo",
            "email": "admin@example.com",
            "password_hash": hash_password("Clave-admin-123"),
            "role": "admin",
            "disabled": False,
        }
        database = SimpleNamespace(users=users, products=MemoryProducts())
        settings = Settings(
            mongo_uri="mongodb://localhost",
            jwt_secret_key="s" * 64,
            _env_file=None,
        )
        product = {
            "sku": "DEMO-001",
            "name": "Memoria ficticia",
            "brand": "Marca demo",
            "category": "Memoria",
            "description": "Producto ficticio para pruebas",
            "specifications": {"Capacidad": "16 GB"},
            "price": "125000.50",
            "stock": 4,
            "image_url": "https://example.com/memoria.png",
        }

        @asynccontextmanager
        async def fake_connection(_settings):
            yield database

        with (
            patch("app.main.mongo_connection", fake_connection),
            patch("app.main.get_settings", return_value=settings),
            patch("app.api.auth.get_settings", return_value=settings),
            patch("app.api.dependencies.get_settings", return_value=settings),
        ):
            async with app.router.lifespan_context(app):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    login = await client.post(
                        "/auth/login",
                        json={"email": "admin@example.com", "password": "Clave-admin-123"},
                    )
                    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
                    created = await client.post("/products/", json=product, headers=headers)
                    self.assertEqual(created.status_code, 201)
                    self.assertEqual(created.json()["sku"], "DEMO-001")
                    product_id = created.json()["id"]

                    read = await client.get(f"/products/{product_id}")
                    self.assertEqual(read.status_code, 200)
                    changed = await client.put(
                        f"/products/{product_id}",
                        json=product | {"price": "130000.00"},
                        headers=headers,
                    )
                    self.assertEqual(changed.status_code, 200)
                    self.assertEqual(changed.json()["price"], "130000.00")
                    deleted = await client.delete(f"/products/{product_id}", headers=headers)
                    self.assertEqual(deleted.status_code, 204)
                    hidden = await client.get(f"/products/{product_id}")
                    self.assertEqual(hidden.status_code, 404)


if __name__ == "__main__":
    unittest.main()
