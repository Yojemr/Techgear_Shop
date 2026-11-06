"""Modelos de presentación; los documentos de negocio pertenecen a FastAPI."""

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

IDENTIFIER = re.compile(r"^[0-9a-f]{24}$")
ORDER_STATES = {
    "confirmed": "Confirmado",
    "preparing": "En preparación",
    "shipped": "Enviado",
    "delivered": "Entregado",
    "cancelled": "Rechazado / cancelado",
    "returned": "Devuelto",
}


@dataclass(frozen=True)
class Cart:
    version: str | None
    items: list[dict]
    total: Decimal

    @property
    def count(self):
        return sum(line["quantity"] for line in self.items)

    @classmethod
    def from_payload(cls, payload):
        version = payload.get("version")
        if version is not None and not IDENTIFIER.fullmatch(version):
            raise ValueError("Invalid cart version")
        return cls(version, checked_items(payload), checked_total(payload))


def checked_items(payload):
    """Comprueba importes con Decimal antes de usarlos en la interfaz."""
    if not isinstance(payload.get("items"), list):
        raise ValueError("Invalid items")
    result = []
    for original in payload["items"]:
        line = original.copy()
        if (
            not IDENTIFIER.fullmatch(line["product_id"])
            or type(line["quantity"]) is not int
            or line["quantity"] <= 0
            or not isinstance(line["name"], str)
            or not isinstance(line["sku"], str)
        ):
            raise ValueError("Invalid item")
        for key in ("unit_price", "subtotal"):
            line[key] = Decimal(str(line[key]))
            if not line[key].is_finite() or line[key] < 0:
                raise ValueError("Invalid money")
        if line["subtotal"] != line["unit_price"] * line["quantity"]:
            raise ValueError("Invalid subtotal")
        result.append(line)
    return result


def checked_total(payload):
    total = Decimal(str(payload["total"]))
    if (
        not total.is_finite()
        or total < 0
        or payload.get("currency") != "COP"
        or total != sum((line["subtotal"] for line in checked_items(payload)), Decimal(0))
    ):
        raise InvalidOperation
    return total


@dataclass(frozen=True)
class Order:
    id: str
    items: list[dict]
    total: Decimal
    status: str
    created_at: str
    customer_id: str = ""
    customer: dict | None = None
    updates: list[dict] = field(default_factory=list)

    @property
    def status_label(self):
        return ORDER_STATES[self.status]

    @classmethod
    def from_payload(cls, payload):
        if not IDENTIFIER.fullmatch(payload["id"]) or payload["status"] not in ORDER_STATES:
            raise ValueError("Invalid order")
        updates = payload.get("updates", [])
        if not isinstance(updates, list) or any(
            not isinstance(item, dict)
            or not isinstance(item.get("message"), str)
            or not isinstance(item.get("created_at"), str)
            for item in updates
        ):
            raise ValueError("Invalid order updates")
        customer = payload.get("customer")
        if customer is not None and (
            not isinstance(customer, dict)
            or any(not isinstance(customer.get(key), str) for key in ("full_name", "email"))
        ):
            raise ValueError("Invalid customer")
        return cls(
            payload["id"],
            checked_items(payload),
            checked_total(payload),
            payload["status"],
            payload["created_at"],
            payload.get("customer_id", ""),
            customer,
            updates,
        )
