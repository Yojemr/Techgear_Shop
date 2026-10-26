"""Tipos de validación compartidos por los contratos de la API."""

from decimal import Decimal
from typing import Annotated

from pydantic import Field, StringConstraints

# Normaliza los espacios exteriores y rechaza cadenas vacías después de limpiarlas.
NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

# Decimal conserva los centavos; los importes admiten hasta dos decimales y 16 dígitos.
# El valor validado todavía debe convertirse a BSON al implementar la persistencia.
Money = Annotated[Decimal, Field(ge=0, max_digits=16, decimal_places=2, allow_inf_nan=False)]

# Representación JSON de un ObjectId; no comprueba que el documento exista en MongoDB.
MongoId = Annotated[str, Field(pattern=r"^[0-9a-f]{24}$")]
