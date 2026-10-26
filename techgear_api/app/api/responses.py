"""Conversión segura de documentos MongoDB a tipos JSON de la API."""

from decimal import Decimal
from typing import Any

from bson import Decimal128, ObjectId


def json_document(document: dict[str, Any]) -> dict[str, Any]:
    """Convierte ObjectId y Decimal128 recursivamente sin pasar por float."""

    def convert(value: Any) -> Any:
        if isinstance(value, ObjectId):
            return str(value)
        if isinstance(value, Decimal128):
            return value.to_decimal()
        if isinstance(value, dict):
            return {key: convert(item) for key, item in value.items() if key != "_id"}
        if isinstance(value, list):
            return [convert(item) for item in value]
        return value

    response = convert(document)
    if "_id" in document:
        response["id"] = str(document["_id"])
    return response


def bson_decimal(value: Decimal) -> Decimal128:
    """Usa Decimal128 para preservar con exactitud los importes en MongoDB."""
    return Decimal128(value)


def user_response(document: dict[str, Any]) -> dict[str, Any]:
    """Construye una lista permitida de campos y excluye credenciales de la cuenta."""
    return {
        "id": str(document["_id"]),
        "full_name": document["full_name"],
        "email": document["email"],
        "role": document["role"],
        "disabled": document.get("disabled", False),
    }
