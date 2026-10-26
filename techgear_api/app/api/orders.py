"""Creación de pedidos, consulta por propietario y transición administrativa de estados."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from app.api.dependencies import get_current_user, get_database, require_admin
from app.api.responses import bson_decimal, json_document
from app.schemas.common import MongoId
from app.schemas.order import OrderCreate, OrderRead, OrderStatus, OrderStatusUpdate

router = APIRouter(prefix="/orders", tags=["Pedidos"])


def _order_filter(order_id: str, user: dict[str, Any], admin: bool) -> dict[str, Any]:
    """Restringe clientes a sus pedidos; administradores pueden consultar cualquiera."""
    criteria: dict[str, Any] = {"_id": ObjectId(order_id)}
    if not admin:
        criteria["customer_id"] = user["_id"]
    return criteria


@router.post("/", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: OrderCreate,
    database: Annotated[AsyncDatabase[dict[str, Any]], Depends(get_database)],
    user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, Any]:
    """Valida productos y descuenta existencias solo al confirmar el pedido."""
    quantities: dict[str, int] = {}
    for item in payload.items:
        # Consolida líneas repetidas para validar y descontar el total solicitado.
        quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity
    order_id = ObjectId()
    created_at = datetime.now(UTC)

    async def transaction(session: Any) -> dict[str, Any]:
        snapshots: list[dict[str, Any]] = []
        total = Decimal("0.00")
        for product_id, quantity in quantities.items():
            product = await database.products.find_one(
                {"_id": ObjectId(product_id), "active": True}, session=session
            )
            if product is None:
                raise HTTPException(
                    status_code=404, detail="Uno de los productos no está disponible."
                )
            if product["stock"] < quantity:
                raise HTTPException(
                    status_code=409,
                    detail=f"Existencias insuficientes para el producto {product['sku']}.",
                )
            unit_price = product["price"].to_decimal()
            subtotal = unit_price * quantity
            total += subtotal
            snapshots.append(
                {
                    "product_id": product["_id"],
                    "quantity": quantity,
                    "sku": product["sku"],
                    "name": product["name"],
                    "unit_price": bson_decimal(unit_price),
                    "subtotal": bson_decimal(subtotal),
                }
            )
        for product_id, quantity in quantities.items():
            result = await database.products.update_one(
                {"_id": ObjectId(product_id), "active": True, "stock": {"$gte": quantity}},
                {"$inc": {"stock": -quantity}},
                session=session,
            )
            if result.modified_count != 1:
                # La transacción aborta y MongoDB revierte descuentos parciales.
                raise HTTPException(
                    status_code=409,
                    detail="Las existencias cambiaron; vuelve a intentar el pedido.",
                )
        order = {
            "_id": order_id,
            "customer_id": user["_id"],
            "items": snapshots,
            "total": bson_decimal(total),
            "currency": "COP",
            "created_at": created_at,
            "status": OrderStatus.CONFIRMED,
        }
        await database.orders.insert_one(order, session=session)
        return order

    try:
        async with await database.client.start_session() as session:
            order = await session.with_transaction(transaction)
    except HTTPException:
        raise
    except PyMongoError:
        raise HTTPException(status_code=503, detail="No fue posible confirmar el pedido.") from None
    return json_document(order)


@router.get("/", response_model=list[OrderRead])
async def list_orders(
    database: Annotated[AsyncDatabase[dict[str, Any]], Depends(get_database)],
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    """Devuelve los pedidos propios o todos los pedidos al rol administrativo."""
    criteria = {} if user.get("role") == "admin" else {"customer_id": user["_id"]}
    cursor = database.orders.find(criteria).sort("created_at", -1).skip(offset).limit(limit)
    return [json_document(order) async for order in cursor]


@router.get("/{order_id}", response_model=OrderRead)
async def get_order(
    order_id: MongoId,
    database: Annotated[AsyncDatabase[dict[str, Any]], Depends(get_database)],
    user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, Any]:
    """Impide que una cuenta de cliente lea pedidos pertenecientes a otra."""
    order = await database.orders.find_one(
        _order_filter(order_id, user, user.get("role") == "admin")
    )
    if order is None:
        raise HTTPException(status_code=404, detail="Pedido no encontrado.")
    return json_document(order)


@router.patch("/{order_id}/status", response_model=OrderRead)
async def update_order_status(
    order_id: MongoId,
    payload: OrderStatusUpdate,
    database: Annotated[AsyncDatabase[dict[str, Any]], Depends(get_database)],
    _: Annotated[dict[str, Any], Depends(require_admin)],
) -> dict[str, Any]:
    """Aplica estados secuenciales y devuelve stock al cancelar antes del envío."""
    transitions = {
        OrderStatus.CONFIRMED: {OrderStatus.PREPARING, OrderStatus.CANCELLED},
        OrderStatus.PREPARING: {OrderStatus.SHIPPED, OrderStatus.CANCELLED},
        OrderStatus.SHIPPED: {OrderStatus.DELIVERED},
        OrderStatus.DELIVERED: set(),
        OrderStatus.CANCELLED: set(),
    }
    try:
        async with await database.client.start_session() as session:

            async def transaction(active_session: Any) -> dict[str, Any]:
                order = await database.orders.find_one(
                    {"_id": ObjectId(order_id)}, session=active_session
                )
                if order is None:
                    raise HTTPException(status_code=404, detail="Pedido no encontrado.")
                current = OrderStatus(order["status"])
                if payload.status not in transitions[current]:
                    raise HTTPException(
                        status_code=409,
                        detail=f"No se permite pasar de {current.value} a {payload.status.value}.",
                    )
                if payload.status == OrderStatus.CANCELLED:
                    for item in order["items"]:
                        await database.products.update_one(
                            {"_id": item["product_id"]},
                            {"$inc": {"stock": item["quantity"]}},
                            session=active_session,
                        )
                order["status"] = payload.status
                result = await database.orders.replace_one(
                    {"_id": order["_id"], "status": current.value},
                    order,
                    session=active_session,
                )
                if result.matched_count != 1:
                    # Si otro cambio ganó la carrera, se aborta también cualquier devolución.
                    raise HTTPException(
                        status_code=409,
                        detail="El pedido cambió; vuelve a consultar su estado.",
                    )
                return order

            updated = await session.with_transaction(transaction)
    except HTTPException:
        raise
    except PyMongoError:
        raise HTTPException(
            status_code=503, detail="No fue posible actualizar el estado del pedido."
        ) from None
    return json_document(updated)
