"""Reservas en MongoDB: carrito e inventario siempre cambian en una transacción."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from bson import ObjectId
from fastapi import HTTPException
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.api.responses import bson_decimal, json_document
from app.schemas.cart import CartRead
from app.schemas.order import OrderStatus


async def in_transaction(database, callback):
    """MongoDB puede repetir el callback; no se ejecutan efectos externos dentro de él."""
    try:
        # start_session no realiza E/S y es síncrono; las operaciones de la sesión sí se esperan.
        async with database.client.start_session() as session:
            return await session.with_transaction(callback)
    except HTTPException:
        raise
    except DuplicateKeyError:
        raise HTTPException(409, "El carrito cambió. Actualízalo e intenta de nuevo.") from None
    except PyMongoError:
        raise HTTPException(503, "No fue posible completar la operación del carrito.") from None


async def cart_snapshot(database, cart, session):
    """Precios, imágenes y disponibilidad proceden de productos, nunca del navegador."""
    items = []
    total = Decimal("0.00")
    for line in cart.get("items", []):
        product = await database.products.find_one({"_id": line["product_id"]}, session=session)
        if product is None:
            raise HTTPException(409, "Un componente del carrito ya no está disponible.")
        price = product["price"].to_decimal()
        subtotal = price * line["quantity"]
        total += subtotal
        items.append(
            {
                "product_id": str(product["_id"]),
                "sku": product["sku"],
                "name": product["name"],
                "quantity": line["quantity"],
                "unit_price": price,
                "subtotal": subtotal,
                "image_url": product["image_url"],
                "active": product["active"],
                "available_stock": product["stock"],
            }
        )
    snapshot = {
        "version": str(cart["version"]) if cart.get("version") else None,
        "items": items,
        "total": total,
        "currency": "COP",
    }
    try:
        # Validar antes del commit evita reservar stock para una respuesta monetaria inválida.
        CartRead.model_validate(snapshot)
    except ValidationError:
        raise HTTPException(422, "El importe del carrito supera el límite permitido.") from None
    return snapshot


async def release_expired_carts(database):
    """La limpieza es diferida; nunca se borra una reserva mediante un índice TTL."""
    now = datetime.now(UTC)
    try:
        cursor = database.carts.find({"expires_at": {"$lte": now}, "items.0": {"$exists": True}})
        async for expired in cursor:

            async def release(session, identifier=expired["_id"]):
                cart = await database.carts.find_one(
                    {"_id": identifier, "expires_at": {"$lte": now}}, session=session
                )
                if cart and cart["items"]:
                    for line in cart["items"]:
                        result = await database.products.update_one(
                            {"_id": line["product_id"]},
                            {"$inc": {"stock": line["quantity"]}},
                            session=session,
                        )
                        if result.matched_count != 1:
                            raise HTTPException(409, "No fue posible liberar una reserva vencida.")
                    cart.update({"items": [], "version": ObjectId(), "expires_at": None})
                    await database.carts.replace_one({"_id": identifier}, cart, session=session)

            await in_transaction(database, release)
    except PyMongoError:
        raise HTTPException(503, "No fue posible verificar las reservas del inventario.") from None


async def heartbeat(database, customer_id):
    """Solo renueva reservas vigentes; una pestaña antigua no puede resucitar existencias."""
    await release_expired_carts(database)
    now = datetime.now(UTC)

    async def transaction(session):
        await database.carts.update_one(
            {"_id": customer_id, "expires_at": {"$gt": now}},
            {"$set": {"expires_at": now + timedelta(seconds=120)}},
            session=session,
        )
        cart = await database.carts.find_one({"_id": customer_id}, session=session)
        return {"count": sum(line["quantity"] for line in (cart or {}).get("items", []))}

    return await in_transaction(database, transaction)


async def read_cart(database, customer_id):
    await release_expired_carts(database)

    async def transaction(session):
        cart = await database.carts.find_one({"_id": customer_id}, session=session)
        return await cart_snapshot(database, cart or {}, session)

    return await in_transaction(database, transaction)


async def change_quantity(database, customer_id, product_id, quantity, *, add=False):
    """Reserva solo la diferencia; el filtro de stock impide vender las mismas unidades."""
    await release_expired_carts(database)
    version = ObjectId()

    async def transaction(session):
        cart = await database.carts.find_one({"_id": customer_id}, session=session)
        cart = cart or {"_id": customer_id, "items": []}
        lines = {line["product_id"]: line["quantity"] for line in cart["items"]}
        identifier = ObjectId(product_id)
        previous = lines.get(identifier, 0)
        desired = previous + quantity if add else quantity
        if desired > 99 or (len(lines) >= 100 and identifier not in lines and desired):
            raise HTTPException(
                422, "El carrito admite hasta 100 productos y 99 unidades por línea."
            )
        difference = desired - previous
        if difference:
            criteria = {"_id": identifier}
            if difference > 0:
                criteria.update({"active": True, "stock": {"$gte": difference}})
            result = await database.products.update_one(
                criteria, {"$inc": {"stock": -difference}}, session=session
            )
            if result.matched_count != 1:
                raise HTTPException(409, "No hay suficientes unidades disponibles de ese producto.")
        if desired:
            lines[identifier] = desired
        else:
            lines.pop(identifier, None)
        cart.update(
            {
                "items": [{"product_id": key, "quantity": value} for key, value in lines.items()],
                "version": version,
                "expires_at": datetime.now(UTC) + timedelta(seconds=120) if lines else None,
            }
        )
        await database.carts.replace_one({"_id": customer_id}, cart, upsert=True, session=session)
        return await cart_snapshot(database, cart, session)

    return await in_transaction(database, transaction)


async def empty_cart(database, customer_id):
    """Vaciar dos veces es seguro: la primera transacción retira las líneas reservadas."""

    async def transaction(session):
        cart = await database.carts.find_one({"_id": customer_id}, session=session)
        if cart and cart["items"]:
            for line in cart["items"]:
                result = await database.products.update_one(
                    {"_id": line["product_id"]},
                    {"$inc": {"stock": line["quantity"]}},
                    session=session,
                )
                if result.matched_count != 1:
                    raise HTTPException(409, "No fue posible devolver un producto al inventario.")
            cart.update({"items": [], "version": ObjectId(), "expires_at": None})
            await database.carts.replace_one({"_id": customer_id}, cart, session=session)
        return {"version": None, "items": [], "total": Decimal("0.00"), "currency": "COP"}

    return await in_transaction(database, transaction)


async def checkout_cart(database, customer_id, payload):
    """Convierte la reserva en pedido; repetir la misma versión devuelve el mismo pedido."""
    await release_expired_carts(database)
    identifier = ObjectId(payload.version)
    created_at = datetime.now(UTC)

    async def transaction(session):
        existing = await database.orders.find_one(
            {"_id": identifier, "customer_id": customer_id}, session=session
        )
        if existing:
            return json_document(existing)
        cart = await database.carts.find_one({"_id": customer_id}, session=session)
        if not cart or not cart["items"] or cart["version"] != identifier:
            raise HTTPException(409, "El carrito cambió. Revísalo antes de confirmar.")
        snapshot = await cart_snapshot(database, cart, session)
        if any(not line["active"] for line in snapshot["items"]):
            raise HTTPException(409, "Retira los productos que ya no están disponibles.")
        if snapshot["total"] != payload.expected_total:
            raise HTTPException(409, "Los precios cambiaron. Revisa el total actualizado.")
        order_items = []
        for line in snapshot["items"]:
            order_items.append(
                {
                    "product_id": ObjectId(line["product_id"]),
                    "quantity": line["quantity"],
                    "sku": line["sku"],
                    "name": line["name"],
                    "unit_price": bson_decimal(line["unit_price"]),
                    "subtotal": bson_decimal(line["subtotal"]),
                }
            )
        order = {
            "_id": identifier,
            "customer_id": customer_id,
            "items": order_items,
            "total": bson_decimal(snapshot["total"]),
            "currency": "COP",
            "created_at": created_at,
            "status": OrderStatus.CONFIRMED,
        }
        await database.orders.insert_one(order, session=session)
        # El stock ya se descontó al reservar: confirmar no lo vuelve a descontar.
        cart.update({"items": [], "version": ObjectId(), "expires_at": None})
        await database.carts.replace_one({"_id": customer_id}, cart, session=session)
        return json_document(order)

    return await in_transaction(database, transaction)


async def import_cart(database, customer_id, payload):
    """Reserva toda la selección o ninguna línea; una transferencia repetida no suma dos veces."""
    await release_expired_carts(database)
    version = ObjectId()
    additions = {}
    for item in payload.items:
        identifier = ObjectId(item.product_id)
        additions[identifier] = additions.get(identifier, 0) + item.quantity

    async def transaction(session):
        cart = await database.carts.find_one({"_id": customer_id}, session=session)
        cart = cart or {"_id": customer_id, "items": []}
        transfers = cart.get("transfers", [])
        if payload.transfer_id in transfers:
            return await cart_snapshot(database, cart, session)
        lines = {line["product_id"]: line["quantity"] for line in cart["items"]}
        if len(set(lines) | set(additions)) > 100:
            raise HTTPException(422, "El carrito admite hasta 100 productos.")
        for identifier, quantity in additions.items():
            if lines.get(identifier, 0) + quantity > 99:
                raise HTTPException(422, "El carrito admite hasta 99 unidades por producto.")
            result = await database.products.update_one(
                {"_id": identifier, "active": True, "stock": {"$gte": quantity}},
                {"$inc": {"stock": -quantity}},
                session=session,
            )
            if result.matched_count != 1:
                raise HTTPException(409, "No hay existencias para reservar toda la selección.")
            lines[identifier] = lines.get(identifier, 0) + quantity
        cart.update(
            {
                "items": [{"product_id": key, "quantity": value} for key, value in lines.items()],
                "version": version,
                "expires_at": datetime.now(UTC) + timedelta(seconds=120),
                "transfers": transfers + [payload.transfer_id],
            }
        )
        await database.carts.replace_one({"_id": customer_id}, cart, upsert=True, session=session)
        return await cart_snapshot(database, cart, session)

    return await in_transaction(database, transaction)
