"""Consulta de perfil y alta administrativa de cuentas de cliente."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.api.dependencies import get_current_user, get_database, require_admin
from app.api.responses import user_response
from app.core.security import hash_password
from app.schemas.user import UserCreate, UserRead, UserRole

router = APIRouter(prefix="/users", tags=["Usuarios"])


@router.get("/me", response_model=UserRead)
async def read_profile(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, Any]:
    """Devuelve solo los datos públicos de la cuenta autenticada."""
    return user_response(user)


@router.post("/", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user_by_admin(
    payload: UserCreate,
    database: Annotated[AsyncDatabase[dict[str, Any]], Depends(get_database)],
    _: Annotated[dict[str, Any], Depends(require_admin)],
) -> dict[str, Any]:
    """Permite al administrador crear clientes sin recibir campos de rol."""
    document = payload.model_dump(exclude={"password"})
    document.update(
        {
            "email": payload.email.lower(),
            "password_hash": hash_password(payload.password),
            "role": UserRole.CUSTOMER,
            "disabled": False,
        }
    )
    try:
        result = await database.users.insert_one(document)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=409, detail="Ya existe una cuenta con ese correo."
        ) from None
    except PyMongoError:
        raise HTTPException(status_code=503, detail="No fue posible registrar la cuenta.") from None
    document["_id"] = result.inserted_id
    return user_response(document)
