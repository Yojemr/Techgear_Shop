from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.schemas.product import Money, MongoId, NonEmptyText

Quantity = Annotated[int, Field(gt=0, strict=True)]


class OrderStatus(StrEnum):
    CONFIRMED = "confirmed"
    PREPARING = "preparing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class OrderItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: MongoId
    quantity: Quantity


class OrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[OrderItemCreate] = Field(min_length=1)


class OrderItemRead(OrderItemCreate):
    sku: NonEmptyText
    name: NonEmptyText
    unit_price: Money
    subtotal: Money

    @model_validator(mode="after")
    def validate_subtotal(self) -> Self:
        if self.subtotal != self.unit_price * self.quantity:
            raise ValueError("El subtotal no coincide con precio por cantidad")
        return self


class OrderRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: MongoId
    customer_id: NonEmptyText
    items: list[OrderItemRead] = Field(min_length=1)
    total: Money
    currency: Literal["COP"] = "COP"
    created_at: AwareDatetime
    status: OrderStatus = OrderStatus.CONFIRMED

    @model_validator(mode="after")
    def validate_total(self) -> Self:
        if self.total != sum(item.subtotal for item in self.items):
            raise ValueError("El total no coincide con la suma de subtotales")
        return self
