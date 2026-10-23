from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Money = Annotated[Decimal, Field(ge=0, max_digits=16, decimal_places=2, allow_inf_nan=False)]
MongoId = Annotated[str, Field(pattern=r"^[0-9a-f]{24}$")]


class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    sku: NonEmptyText
    name: NonEmptyText
    brand: NonEmptyText
    category: NonEmptyText
    description: NonEmptyText
    specifications: dict[NonEmptyText, NonEmptyText] = Field(min_length=1)
    price: Money
    currency: Literal["COP"] = "COP"
    stock: Annotated[int, Field(ge=0, strict=True)]
    image_url: HttpUrl
    active: bool = True


class ProductRead(ProductCreate):
    id: MongoId
