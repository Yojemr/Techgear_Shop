"""Conexión asíncrona y preparación explícita de colecciones e índices."""

import argparse
import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import CollectionInvalid, PyMongoError

from app.core.config import Settings, get_settings


@asynccontextmanager
async def mongo_connection(settings: Settings) -> AsyncIterator[AsyncDatabase[dict[str, Any]]]:
    """Verifica la conexión, entrega la base y cierra el cliente incluso ante errores."""
    client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(
        settings.mongo_uri.get_secret_value(),
        serverSelectionTimeoutMS=10000,
        connectTimeoutMS=10000,
        appname="Techgear_Shop",
    )
    try:
        # Crear el cliente no verifica red ni credenciales; ping fuerza una operación.
        await client.admin.command("ping")
        yield client[settings.mongo_db_name]
    except PyMongoError:
        # El error público evita mostrar detalles que podrían incluir datos de conexión.
        raise RuntimeError("No se pudo completar la operación con MongoDB.") from None
    finally:
        await client.close()


async def initialize_database(database: AsyncDatabase[dict[str, Any]]) -> None:
    """Crea colecciones e índices idempotentes, sin insertar datos de negocio."""
    for name in ("users", "products", "orders"):
        try:
            await database.create_collection(name)
        except CollectionInvalid:
            # Una colección existente permite repetir la preparación sin borrarla.
            pass
    # El servidor aplica unicidad incluso cuando llegan dos registros simultáneos.
    await database.users.create_index("email", unique=True, name="unique_user_email")
    await database.products.create_index("sku", unique=True, name="unique_product_sku")
    await database.orders.create_index(
        [("customer_id", 1), ("created_at", -1)], name="orders_by_customer_date"
    )


async def check_connection(initialize: bool = False) -> None:
    """Diagnostica Atlas; solo --initialize crea colecciones e índices necesarios."""
    async with mongo_connection(get_settings()) as database:
        if initialize:
            await initialize_database(database)
        print(f"Conexión correcta. Base: {database.name}")
        if initialize:
            print("Colecciones users, products y orders; índices requeridos verificados.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verificar o preparar MongoDB para Techgear.")
    parser.add_argument("--initialize", action="store_true")
    arguments = parser.parse_args()
    asyncio.run(check_connection(arguments.initialize))
