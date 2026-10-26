"""Consulta pública del catálogo y mantenimiento de productos para administradores."""

from typing import Annotated, Any

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.api.dependencies import get_database, require_admin
from app.api.responses import bson_decimal, json_document
from app.schemas.common import MongoId
from app.schemas.product import ProductCreate, ProductRead

router = APIRouter(prefix="/products", tags=["Productos"])


@router.get("/", response_model=list[ProductRead])
async def list_products(
    database: Annotated[AsyncDatabase[dict[str, Any]], Depends(get_database)],
    category: str | None = None,
    search: str | None = Query(default=None, min_length=1, max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    """Lista solo productos activos y permite filtrar por categoría o texto."""
    criteria: dict[str, Any] = {"active": True}
    if category:
        criteria["category"] = category
    if search:
        # La expresión escapa los caracteres para que el texto no se interprete como regex.
        import re

        criteria["$or"] = [
            {field: {"$regex": re.escape(search), "$options": "i"}}
            for field in ("name", "brand", "sku")
        ]
    try:
        cursor = database.products.find(criteria).sort("name", 1).skip(offset).limit(limit)
        return [json_document(item) async for item in cursor]
    except PyMongoError:
        raise HTTPException(
            status_code=503, detail="No fue posible consultar el catálogo."
        ) from None


@router.get("/{product_id}", response_model=ProductRead)
async def get_product(
    product_id: MongoId, database: Annotated[AsyncDatabase[dict[str, Any]], Depends(get_database)]
) -> dict[str, Any]:
    """Recupera un producto activo por su identificador MongoDB."""
    product = await database.products.find_one({"_id": ObjectId(product_id), "active": True})
    if product is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")
    return json_document(product)


@router.post("/", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    database: Annotated[AsyncDatabase[dict[str, Any]], Depends(get_database)],
    _: Annotated[dict[str, Any], Depends(require_admin)],
) -> dict[str, Any]:
    """Crea un producto; el índice de MongoDB evita SKU duplicados concurrentes."""
    document = payload.model_dump(mode="python")
    document["image_url"] = str(payload.image_url)
    document["price"] = bson_decimal(payload.price)
    try:
        result = await database.products.insert_one(document)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Ya existe un producto con ese SKU.") from None
    except PyMongoError:
        raise HTTPException(status_code=503, detail="No fue posible crear el producto.") from None
    document["_id"] = result.inserted_id
    return json_document(document)


@router.put("/{product_id}", response_model=ProductRead)
async def replace_product(
    product_id: MongoId,
    payload: ProductCreate,
    database: Annotated[AsyncDatabase[dict[str, Any]], Depends(get_database)],
    _: Annotated[dict[str, Any], Depends(require_admin)],
) -> dict[str, Any]:
    """Reemplaza los datos editables del producto sin cambiar su identidad."""
    document = payload.model_dump(mode="python")
    document["image_url"] = str(payload.image_url)
    document["price"] = bson_decimal(payload.price)
    try:
        result = await database.products.find_one_and_update(
            {"_id": ObjectId(product_id)}, {"$set": document}, return_document=True
        )
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Ya existe un producto con ese SKU.") from None
    except PyMongoError:
        raise HTTPException(
            status_code=503, detail="No fue posible actualizar el producto."
        ) from None
    if result is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")
    return json_document(result)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def deactivate_product(
    product_id: MongoId,
    database: Annotated[AsyncDatabase[dict[str, Any]], Depends(get_database)],
    _: Annotated[dict[str, Any], Depends(require_admin)],
) -> Response:
    """Retira un producto del catálogo sin borrar referencias en pedidos históricos."""
    result = await database.products.update_one(
        {"_id": ObjectId(product_id), "active": True}, {"$set": {"active": False}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
