"""Contratos de pedidos y comprobaciones de sus importes históricos."""

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import Money, MongoId, NonEmptyText

Quantity = Annotated[int, Field(gt=0, strict=True)]


class OrderStatus(StrEnum):
    """Estados del pedido; los cambios permitidos se validan en el endpoint."""

    CONFIRMED = "confirmed"
    PREPARING = "preparing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class OrderItemCreate(BaseModel):
    """Producto y cantidad que el cliente solicita comprar."""

    model_config = ConfigDict(extra="forbid")

    product_id: MongoId
    quantity: Quantity


class OrderCreate(BaseModel):
    """Solicitud de compra; servidor determina cliente, precios y existencias."""

    model_config = ConfigDict(extra="forbid")

    items: list[OrderItemCreate] = Field(min_length=1)


class OrderItemRead(OrderItemCreate):
    """Copia histórica del SKU, nombre y precio usados en el momento de compra."""

    sku: NonEmptyText
    name: NonEmptyText
    unit_price: Money
    subtotal: Money

    @model_validator(mode="after")
    def validate_subtotal(self) -> Self:
        """Comprueba el subtotal con Decimal, sin redondeos mediante float."""
        if self.subtotal != self.unit_price * self.quantity:
            raise ValueError("El subtotal no coincide con precio por cantidad")
        return self


class OrderRead(BaseModel):
    """Pedido persistido con fecha zonificada, cliente y total consistente."""

    model_config = ConfigDict(extra="forbid")

    id: MongoId
    customer_id: MongoId
    items: list[OrderItemRead] = Field(min_length=1)
    total: Money
    currency: Literal["COP"] = "COP"
    created_at: AwareDatetime
    status: OrderStatus = OrderStatus.CONFIRMED

    @model_validator(mode="after")
    def validate_total(self) -> Self:
        """Comprueba que el total coincida con la suma exacta de las líneas."""
        if self.total != sum(item.subtotal for item in self.items):
            raise ValueError("El total no coincide con la suma de subtotales")
        return self


class OrderStatusUpdate(BaseModel):
    """Estado solicitado por un administrador; el endpoint controla transiciones."""

    model_config = ConfigDict(extra="forbid")

    status: OrderStatus
