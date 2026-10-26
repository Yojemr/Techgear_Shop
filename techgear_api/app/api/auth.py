"""Registro de clientes e inicio de sesión mediante token Bearer."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.api.dependencies import get_database
from app.api.responses import user_response
from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    hash_password,
    password_hash,
    verify_password,
)
from app.schemas.auth import LoginRequest, TokenRead
from app.schemas.user import UserCreate, UserRead, UserRole

router = APIRouter(prefix="/auth", tags=["Autenticación"])
# Un hash ficticio evita reducir el tiempo de respuesta cuando el correo no existe.
DUMMY_PASSWORD_HASH = password_hash.hash("un-password-ficticio-que-no-se-usa")


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    payload: UserCreate,
    database: Annotated[AsyncDatabase[dict[str, Any]], Depends(get_database)],
) -> dict[str, Any]:
    """Crea una cuenta de cliente; el rol no se recibe desde el formulario público."""
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


@router.post("/login", response_model=TokenRead)
async def login(
    payload: LoginRequest,
    database: Annotated[AsyncDatabase[dict[str, Any]], Depends(get_database)],
) -> TokenRead:
    """Verifica correo y contraseña y devuelve un token de acceso temporal."""
    try:
        user = await database.users.find_one({"email": payload.email.lower()})
    except PyMongoError:
        raise HTTPException(status_code=503, detail="No fue posible iniciar sesión.") from None
    stored_hash = user.get("password_hash", DUMMY_PASSWORD_HASH) if user else DUMMY_PASSWORD_HASH
    password_matches = verify_password(payload.password, stored_hash)
    if user is None or user.get("disabled", False) or not password_matches:
        raise HTTPException(
            status_code=401,
            detail="Correo o contraseña incorrectos.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    settings = get_settings()
    token = create_access_token(str(user["_id"]), user["role"], settings)
    return TokenRead(access_token=token, expires_in=settings.jwt_access_token_minutes * 60)
