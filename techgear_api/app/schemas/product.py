"""Contratos de entrada y salida para los productos del catálogo."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.schemas.common import Money, MongoId, NonEmptyText


class ProductCreate(BaseModel):
    """Datos editables de un producto; su identificador se asigna en el servidor."""

    # Los campos desconocidos se rechazan para detectar errores en las solicitudes.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    sku: NonEmptyText
    name: NonEmptyText
    brand: NonEmptyText
    category: NonEmptyText
    description: NonEmptyText
    specifications: dict[NonEmptyText, NonEmptyText] = Field(min_length=1)
    price: Money
    currency: Literal["COP"] = "COP"
    # strict=True impide aceptar decimales, booleanos o números enviados como texto.
    stock: Annotated[int, Field(ge=0, strict=True)]
    image_url: HttpUrl
    active: bool = True


class ProductRead(ProductCreate):
    """Producto devuelto por la API, con el ObjectId serializado como texto."""

    id: MongoId
