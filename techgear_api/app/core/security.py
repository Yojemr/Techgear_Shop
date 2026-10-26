"""Hash de contraseñas y emisión de tokens de acceso firmados."""

from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.core.config import Settings

# Argon2 es la función de derivación recomendada para almacenar contraseñas.
password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Guarda solo el hash irreversible de la contraseña recibida."""
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Compara una contraseña con su hash sin exponer el valor almacenado."""
    return password_hash.verify(password, hashed_password)


def create_access_token(subject: str, role: str, settings: Settings) -> str:
    """Firma un JWT breve; su contenido no está cifrado y no debe llevar secretos."""
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.jwt_access_token_minutes)
    return jwt.encode(
        {"sub": subject, "role": role, "exp": expires_at},
        settings.jwt_secret_key.get_secret_value(),
        algorithm="HS256",
    )
