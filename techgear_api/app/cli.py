"""Comandos administrativos explícitos para inicializar una cuenta de administrador."""

import argparse
import asyncio
from getpass import getpass

from pymongo.errors import DuplicateKeyError

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.catalog import insert_missing_products, load_reference_products
from app.db.mongodb import initialize_database, mongo_connection
from app.schemas.user import UserCreate, UserRole


async def create_admin() -> None:
    """Crea un administrador inicial solicitando credenciales sin mostrarlas."""
    full_name = input("Nombre del administrador: ").strip()
    email = input("Correo del administrador: ").strip().lower()
    password = getpass("Contraseña (mínimo 8 caracteres): ")
    repeated = getpass("Repite la contraseña: ")
    if password != repeated:
        raise SystemExit("Las contraseñas no coinciden.")
    # El mismo esquema valida correo, nombre y longitud antes de abrir una conexión.
    account = UserCreate(full_name=full_name, email=email, password=password)
    async with mongo_connection(get_settings()) as database:
        document = {
            "full_name": account.full_name,
            "email": str(account.email).lower(),
            "password_hash": hash_password(account.password),
            "role": UserRole.ADMIN,
            "disabled": False,
        }
        try:
            await database.users.insert_one(document)
        except DuplicateKeyError:
            raise SystemExit("Ya existe una cuenta con ese correo.") from None
    print("Cuenta administrativa creada.")


async def seed_catalog(stock: int) -> None:
    """Carga el catalogo investigado una sola vez por SKU; no se ejecuta al arrancar."""
    products = load_reference_products(stock)
    async with mongo_connection(get_settings()) as database:
        await initialize_database(database)
        inserted = await insert_missing_products(database, products)
    print(f"Catalogo: {inserted} insertados; {len(products) - inserted} conservados.")


def main() -> None:
    """Selecciona una acción manual para que el arranque no cree cuentas."""
    parser = argparse.ArgumentParser(description="Administración inicial de Techgear Shop.")
    parser.add_argument("command", choices=("create-admin", "seed-catalog"))
    parser.add_argument("--stock", type=int, default=5, help="Existencias de productos nuevos.")
    arguments = parser.parse_args()
    if arguments.stock < 0:
        parser.error("--stock debe ser un entero no negativo.")
    if arguments.command == "create-admin":
        asyncio.run(create_admin())
    elif arguments.command == "seed-catalog":
        asyncio.run(seed_catalog(arguments.stock))


if __name__ == "__main__":
    main()
