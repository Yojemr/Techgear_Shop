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
from app.schemas.order import (
    OrderCreate,
    OrderNotification,
    OrderRead,
    OrderStatus,
    OrderStatusUpdate,
)
from app.services.cart import release_expired_carts

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
    await release_expired_carts(database)
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
        async with database.client.start_session() as session:
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
    mine: bool = Query(default=False),
    order_status: OrderStatus | None = None,
) -> list[dict[str, Any]]:
    """Devuelve los pedidos propios o todos los pedidos al rol administrativo."""
    criteria = {} if user.get("role") == "admin" and not mine else {"customer_id": user["_id"]}
    if order_status is not None:
        criteria["status"] = order_status.value
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
    response = json_document(order)
    if user.get("role") == "admin":
        customer = await database.users.find_one({"_id": order["customer_id"]})
        if customer is not None:
            # Lista explícita: nunca serializar el documento de cuenta completo.
            response["customer"] = {"full_name": customer["full_name"], "email": customer["email"]}
    return response


@router.patch("/{order_id}/status", response_model=OrderRead)
async def update_order_status(
    order_id: MongoId,
    payload: OrderStatusUpdate,
    database: Annotated[AsyncDatabase[dict[str, Any]], Depends(get_database)],
    _: Annotated[dict[str, Any], Depends(require_admin)],
) -> dict[str, Any]:
    """Aplica estados secuenciales y repone stock al rechazar o registrar devolución."""
    transitions = {
        OrderStatus.CONFIRMED: {OrderStatus.PREPARING, OrderStatus.CANCELLED},
        OrderStatus.PREPARING: {OrderStatus.SHIPPED, OrderStatus.CANCELLED},
        OrderStatus.SHIPPED: {OrderStatus.DELIVERED},
        OrderStatus.DELIVERED: {OrderStatus.RETURNED},
        OrderStatus.RETURNED: set(),
        OrderStatus.CANCELLED: set(),
    }
    try:
        async with database.client.start_session() as session:

            async def transaction(active_session: Any) -> dict[str, Any]:
                order = await database.orders.find_one(
                    {"_id": ObjectId(order_id)}, session=active_session
                )
                if order is None:
                    raise HTTPException(status_code=404, detail="Pedido no encontrado.")
                current = OrderStatus(order["status"])
                if payload.expected_status is not None and payload.expected_status != current:
                    raise HTTPException(
                        status_code=409, detail="El pedido cambió; actualiza su estado."
                    )
                if payload.status not in transitions[current]:
                    raise HTTPException(
                        status_code=409,
                        detail=f"No se permite pasar de {current.value} a {payload.status.value}.",
                    )
                if payload.status in (OrderStatus.CANCELLED, OrderStatus.RETURNED):
                    for item in order["items"]:
                        restored = await database.products.update_one(
                            {"_id": item["product_id"]},
                            {"$inc": {"stock": item["quantity"]}},
                            session=active_session,
                        )
                        if restored.matched_count != 1:
                            raise HTTPException(
                                status_code=409, detail="No se pudo reponer una pieza."
                            )
                labels = {
                    OrderStatus.PREPARING: "Pedido aceptado y en preparación.",
                    OrderStatus.SHIPPED: "Pedido enviado.",
                    OrderStatus.DELIVERED: "Pedido entregado.",
                    OrderStatus.CANCELLED: "Pedido rechazado. Se devolvieron las existencias.",
                    OrderStatus.RETURNED: "Devolución registrada. Se repusieron las existencias.",
                }
                _append_update(
                    order,
                    labels[payload.status]
                    + (" " + payload.message.strip() if payload.message.strip() else ""),
                    status=payload.status,
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


def _append_update(order, message, *, status=None, identifier=None):
    """Acota el historial para evitar documentos sin límite de tamaño."""
    updates = order.setdefault("updates", [])
    # Reserva espacio para estados finales: las novedades no bloquean una devolución.
    if status is None and len(updates) >= 190:
        raise HTTPException(status_code=409, detail="El historial del pedido alcanzó su límite.")
    updates.append(
        {
            "id": identifier or str(ObjectId()),
            "message": message,
            "created_at": datetime.now(UTC),
            "status": status,
        }
    )


@router.post("/{order_id}/notifications", response_model=OrderRead)
async def notify_order(
    order_id: MongoId,
    payload: OrderNotification,
    database: Annotated[AsyncDatabase[dict[str, Any]], Depends(get_database)],
    _: Annotated[dict[str, Any], Depends(require_admin)],
) -> dict[str, Any]:
    """Publica una novedad interna; no envía correos ni modifica existencias."""

    async def transaction(session):
        order = await database.orders.find_one({"_id": ObjectId(order_id)}, session=session)
        if order is None:
            raise HTTPException(status_code=404, detail="Pedido no encontrado.")
        if any(item["id"] == payload.request_id for item in order.get("updates", [])):
            return order
        _append_update(order, payload.message, identifier=payload.request_id)
        result = await database.orders.replace_one({"_id": order["_id"]}, order, session=session)
        if result.matched_count != 1:
            raise HTTPException(status_code=409, detail="El pedido cambió; vuelve a consultar.")
        return order

    try:
        async with database.client.start_session() as session:
            updated = await session.with_transaction(transaction)
    except HTTPException:
        raise
    except PyMongoError:
        raise HTTPException(status_code=503, detail="No fue posible guardar la novedad.") from None
    return json_document(updated)
