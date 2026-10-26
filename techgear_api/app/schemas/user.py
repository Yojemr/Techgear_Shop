"""Esquemas públicos para registro, roles y respuesta de usuarios."""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, StringConstraints

from app.schemas.common import MongoId, NonEmptyText

Password = Annotated[str, StringConstraints(min_length=8, max_length=128)]


class UserRole(StrEnum):
    """Permisos generales de las cuentas persistidas en MongoDB."""

    CUSTOMER = "customer"
    ADMIN = "admin"


class UserCreate(BaseModel):
    """Datos de registro; el endpoint público asigna siempre rol de cliente."""

    model_config = ConfigDict(extra="forbid")

    full_name: NonEmptyText
    email: EmailStr
    password: Password


class UserRead(BaseModel):
    """Campos de perfil permitidos; nunca incluye hash ni contraseña."""

    model_config = ConfigDict(extra="forbid")

    id: MongoId
    full_name: NonEmptyText
    email: EmailStr
    role: UserRole
    disabled: bool = False
