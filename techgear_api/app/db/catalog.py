"""Carga inicial explícita de componentes verificados, sin sobrescribir productos."""

import json
from pathlib import Path

from app.api.responses import bson_decimal
from app.schemas.product import ProductCreate

CATALOG_PATH = Path(__file__).resolve().parents[2] / "data" / "pc_components.json"


def load_reference_products(stock=5):
    """Valida el archivo completo antes de comenzar cualquier escritura en MongoDB."""
    if type(stock) is not int or stock < 0:
        raise ValueError("El inventario inicial debe ser un entero no negativo.")
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    products = [
        ProductCreate.model_validate({**entry["product"], "stock": stock})
        for entry in data["items"]
    ]
    if len({product.sku for product in products}) != len(products):
        raise ValueError("El catálogo contiene SKU duplicados.")
    return products


async def insert_missing_products(database, products):
    """setOnInsert evita reponer stock o modificar precios de productos ya existentes."""
    inserted = 0
    for product in products:
        document = product.model_dump(mode="python")
        document["price"] = bson_decimal(product.price)
        document["image_url"] = str(product.image_url)
        result = await database.products.update_one(
            {"sku": product.sku}, {"$setOnInsert": document}, upsert=True
        )
        inserted += result.upserted_id is not None
    return inserted
