"""Configuración de la API obtenida del entorno o del archivo .env local."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# La ruta absoluta permite arrancar la API desde distintos directorios de trabajo.
API_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Valida la configuración; las variables del proceso prevalecen sobre .env."""

    model_config = SettingsConfigDict(
        env_file=API_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    # SecretStr enmascara credenciales en representaciones y mensajes de validación.
    mongo_uri: SecretStr
    mongo_db_name: str = Field(default="techgear_shop", min_length=1)
    jwt_secret_key: SecretStr
    jwt_access_token_minutes: int = Field(default=30, ge=5, le=1440)

    @field_validator("mongo_uri")
    @classmethod
    def validate_uri(cls, value: SecretStr) -> SecretStr:
        """Rechaza protocolos ajenos a MongoDB sin mostrar credenciales."""
        if not value.get_secret_value().startswith(("mongodb://", "mongodb+srv://")):
            raise ValueError("MONGO_URI debe ser una URI de MongoDB")
        return value

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret(cls, value: SecretStr) -> SecretStr:
        """Exige una clave de firma con entropía suficiente para HMAC-SHA256."""
        if len(value.get_secret_value().encode("utf-8")) < 32:
            raise ValueError("JWT_SECRET_KEY debe tener al menos 32 bytes")
        return value


@lru_cache
def get_settings() -> Settings:
    """Carga la configuración una vez por proceso y reutiliza la instancia."""
    return Settings()
