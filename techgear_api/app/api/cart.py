"""Carrito propio: la identidad siempre procede del token autenticado."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pymongo.asynchronous.database import AsyncDatabase

from app.api.dependencies import get_current_user, get_database
from app.schemas.cart import CartCheckout, CartImport, CartQuantityUpdate, CartRead
from app.schemas.common import MongoId
from app.schemas.order import OrderRead
from app.services.cart import (
    change_quantity,
    checkout_cart,
    empty_cart,
    heartbeat,
    import_cart,
    read_cart,
)

router = APIRouter(prefix="/cart", tags=["Carrito"])
Database = Annotated[AsyncDatabase[dict[str, Any]], Depends(get_database)]
User = Annotated[dict[str, Any], Depends(get_current_user)]


@router.get("/", response_model=CartRead)
async def get_cart(database: Database, user: User):
    return await read_cart(database, user["_id"])


@router.post("/items/{product_id}", response_model=CartRead)
async def add_item(
    product_id: MongoId, payload: CartQuantityUpdate, database: Database, user: User
):
    return await change_quantity(database, user["_id"], product_id, payload.quantity, add=True)


@router.put("/items/{product_id}", response_model=CartRead)
async def set_item(
    product_id: MongoId, payload: CartQuantityUpdate, database: Database, user: User
):
    return await change_quantity(database, user["_id"], product_id, payload.quantity)


@router.delete("/", response_model=CartRead)
async def clear_cart(database: Database, user: User):
    return await empty_cart(database, user["_id"])


@router.post("/checkout", response_model=OrderRead)
async def checkout(payload: CartCheckout, database: Database, user: User):
    return await checkout_cart(database, user["_id"], payload)


@router.post("/heartbeat")
async def keep_reservation(database: Database, user: User):
    return await heartbeat(database, user["_id"])


@router.post("/import", response_model=CartRead)
async def reserve_guest_selection(payload: CartImport, database: Database, user: User):
    return await import_cart(database, user["_id"], payload)
