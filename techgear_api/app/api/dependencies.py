"""Dependencias HTTP para recuperar la base y exigir identidad o rol."""

from typing import Annotated, Any

import jwt
from bson import ObjectId
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import get_settings
from app.schemas.user import UserRole

bearer_scheme = HTTPBearer(auto_error=False)


def get_database(request: Request) -> AsyncDatabase[dict[str, Any]]:
    """Recupera la conexión que el ciclo de vida de FastAPI abrió al arrancar."""
    return request.app.state.database


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    database: Annotated[AsyncDatabase[dict[str, Any]], Depends(get_database)],
) -> dict[str, Any]:
    """Valida el token y vuelve a leer el usuario para respetar cambios de rol."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas o sesión vencida.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        claims = jwt.decode(
            credentials.credentials,
            get_settings().jwt_secret_key.get_secret_value(),
            algorithms=["HS256"],
        )
        subject = claims.get("sub")
        user_id = ObjectId(subject) if isinstance(subject, str) else None
    except InvalidTokenError, TypeError, ValueError:
        raise unauthorized from None
    user = await database.users.find_one({"_id": user_id}) if user_id else None
    if user is None or user.get("disabled", False):
        raise unauthorized
    return user


def require_admin(user: Annotated[dict[str, Any], Depends(get_current_user)]) -> dict[str, Any]:
    """Limita operaciones administrativas a cuentas creadas con rol de administrador."""
    if user.get("role") != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Se requiere rol de administrador."
        )
    return user
