"""Selecciones de visitantes en la sesión Django, sin reservar existencias."""

import secrets
from decimal import Decimal

from .models import Cart
from .services.api import PRODUCT_ID, ApiError

SELECTION_KEY = "guest_cart"
TRANSFER_KEY = "guest_cart_transfer"


def selection(session):
    """Conserva únicamente identificadores y cantidades válidos, nunca precios del formulario."""
    values = session.get(SELECTION_KEY, {})
    if not isinstance(values, dict):
        return {}
    return {
        key: quantity
        for key, quantity in values.items()
        if isinstance(key, str)
        and PRODUCT_ID.fullmatch(key)
        and type(quantity) is int
        and 1 <= quantity <= 99
    }


def count(session):
    return sum(selection(session).values())


def clear(session):
    session.pop(SELECTION_KEY, None)
    session.pop(TRANSFER_KEY, None)


def snapshot(session, client):
    values = selection(session)
    if not values:
        return Cart(None, [], Decimal("0.00"))
    products = {product.id: product for product in client.products()}
    items = []
    for identifier, quantity in values.items():
        product = products.get(identifier)
        price = product.price if product else Decimal("0.00")
        items.append(
            {
                "product_id": identifier,
                "quantity": quantity,
                "sku": product.sku if product else "Retirado",
                "name": product.name if product else "Producto no disponible",
                "unit_price": price,
                "subtotal": price * quantity,
                "image_url": product.image_url if product else "",
                "active": bool(product and product.active),
                "available_stock": product.stock if product else 0,
            }
        )
    return Cart(None, items, sum((line["subtotal"] for line in items), Decimal("0.00")))


def change(session, client, identifier, quantity, *, add=False):
    if not PRODUCT_ID.fullmatch(identifier):
        raise ApiError(404, "No encontramos ese componente.")
    values = selection(session)
    desired = values.get(identifier, 0) + quantity if add else quantity
    if desired > 99 or (len(values) >= 100 and identifier not in values and desired):
        raise ApiError(422, "El carrito admite 100 productos y hasta 99 unidades por referencia.")
    if desired:
        # Lee el producto sin reservarlo; el precio del formulario nunca se utiliza.
        client.product(identifier)
        values[identifier] = desired
    else:
        values.pop(identifier, None)
    session[SELECTION_KEY] = values
    session[TRANSFER_KEY] = secrets.token_hex(12)


def reserve(session, client, token):
    """No borrar la selección hasta que la API confirme su reserva atómica."""
    values = selection(session)
    if not values:
        return None
    transfer = session.get(TRANSFER_KEY)
    if not isinstance(transfer, str) or not PRODUCT_ID.fullmatch(transfer):
        transfer = secrets.token_hex(12)
        session[TRANSFER_KEY] = transfer
    cart = client.import_cart(values, transfer, token)
    clear(session)
    return cart
