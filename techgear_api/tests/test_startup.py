"""Pruebas de arranque con clientes simulados y peticiones HTTP en memoria."""

import unittest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

from app.core.config import Settings
from app.db.mongodb import mongo_connection
from app.main import app
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError


class StartupTests(unittest.IsolatedAsyncioTestCase):
    """Comprueba cierre de recursos y protección de valores de configuración."""

    async def test_connection_closes_even_if_ping_fails(self):
        from pymongo.errors import ServerSelectionTimeoutError

        client = AsyncMock()
        client.admin.command.side_effect = ServerSelectionTimeoutError("unavailable")
        settings = Settings(
            mongo_uri="mongodb://localhost", jwt_secret_key="s" * 64, _env_file=None
        )
        with patch("app.db.mongodb.AsyncMongoClient", return_value=client):
            with self.assertRaisesRegex(RuntimeError, "MongoDB"):
                async with mongo_connection(settings):
                    self.fail("Should not open when ping fails")
        client.close.assert_awaited_once()

    async def test_settings_errors_do_not_disclose_credentials(self):
        with self.assertRaises(ValidationError) as caught:
            Settings(mongo_uri="bad-secret-value", jwt_secret_key="s" * 64, _env_file=None)
        self.assertNotIn("bad-secret-value", str(caught.exception))


class AppTests(unittest.IsolatedAsyncioTestCase):
    """Comprueba las rutas iniciales sin usar Atlas ni abrir un servidor de red."""

    async def test_root_and_docs_without_live_database(self):
        @asynccontextmanager
        async def fake_connection(settings):
            yield object()

        with (
            patch("app.main.get_settings", return_value=object()),
            patch("app.main.mongo_connection", fake_connection),
        ):
            # ASGITransport no ejecuta lifespan; la prueba lo abre explícitamente.
            async with app.router.lifespan_context(app):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    self.assertEqual((await client.get("/")).json()["status"], "ok")
                    self.assertEqual((await client.get("/docs")).status_code, 200)
                    self.assertEqual((await client.get("/openapi.json")).status_code, 200)
                    self.assertTrue(hasattr(app.state, "database"))
        self.assertFalse(hasattr(app.state, "database"))


class SessionContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_transaction_helper_uses_real_pymongo_session_without_awaiting_creation(self):
        from types import SimpleNamespace

        from app.services.cart import in_transaction
        from pymongo import AsyncMongoClient
        from pymongo.asynchronous.client_session import AsyncClientSession

        client = AsyncMongoClient("mongodb://127.0.0.1:1", connect=False)
        database = SimpleNamespace(client=client)
        callback = AsyncMock(return_value="transaction-result")
        try:
            with patch.object(
                AsyncClientSession, "with_transaction", new=AsyncMock()
            ) as transaction:
                transaction.return_value = "transaction-result"
                result = await in_transaction(database, callback)
                self.assertEqual(result, "transaction-result")
                transaction.assert_awaited_once_with(callback)
        finally:
            await client.close()


if __name__ == "__main__":
    unittest.main()
