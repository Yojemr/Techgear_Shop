"""Esquemas para credenciales de acceso y respuesta de token."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints


class LoginRequest(BaseModel):
    """Credenciales JSON usadas por Swagger y por el cliente Django."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class TokenRead(BaseModel):
    """Token Bearer firmado y duración expresada en segundos."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(gt=0)
