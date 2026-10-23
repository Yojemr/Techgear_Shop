from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=API_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    mongo_uri: SecretStr
    mongo_db_name: str = Field(default="techgear_shop", min_length=1)

    @field_validator("mongo_uri")
    @classmethod
    def validate_uri(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith(("mongodb://", "mongodb+srv://")):
            raise ValueError("MONGO_URI debe ser una URI de MongoDB")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
