"""Contratos del carrito reservado y de su confirmación sin pago."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Money, MongoId
from app.schemas.order import OrderItemCreate, OrderItemRead

CartQuantity = Annotated[int, Field(ge=0, le=99, strict=True)]


class CartQuantityUpdate(BaseModel):
    """Una cantidad cero retira la línea y devuelve todas sus unidades."""

    model_config = ConfigDict(extra="forbid")
    quantity: CartQuantity


class CartItemRead(OrderItemRead):
    image_url: str
    available_stock: int
    active: bool


class CartRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: MongoId | None = None
    items: list[CartItemRead]
    total: Money
    currency: Literal["COP"] = "COP"


class CartCheckout(BaseModel):
    """La versión evita repetir un pedido y el total detecta cambios de precio."""

    model_config = ConfigDict(extra="forbid")
    version: MongoId
    expected_total: Money


class CartImport(BaseModel):
    """Selección anónima: la API vuelve a comprobar cantidades, stock y precios."""

    model_config = ConfigDict(extra="forbid")
    transfer_id: MongoId
    items: list[OrderItemCreate] = Field(min_length=1, max_length=100)
