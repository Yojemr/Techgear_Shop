"""Cliente HTTP de FastAPI: limita tiempos de espera y oculta detalles internos."""

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

import httpx
from django.conf import settings

PRODUCT_ID = re.compile(r"^[0-9a-f]{24}$")


class ApiError(Exception):
    """Error controlado que una vista puede traducir a un mensaje público."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class Product:
    """Datos de presentación; la API sigue siendo dueña del precio y las existencias."""

    id: str
    sku: str
    name: str
    brand: str
    category: str
    description: str
    specifications: dict[str, str]
    price: Decimal
    stock: int
    image_url: str
    active: bool = True

    @classmethod
    def from_payload(cls, data: dict):
        """Rechaza respuestas incompletas sin enviar detalles de la API al navegador."""
        try:
            if not isinstance(data, dict):
                raise ValueError
            active = data.get("active", True)
            identifier = data["id"]
            price = Decimal(str(data["price"]))
            stock = data["stock"]
            image_url = str(data["image_url"])
            specifications = data["specifications"]
            text_fields = ("sku", "name", "brand", "category", "description")
            if (
                not isinstance(identifier, str)
                or not PRODUCT_ID.fullmatch(identifier)
                or not price.is_finite()
                or price < 0
                or type(active) is not bool
                or type(stock) is not int
                or stock < 0
                or urlsplit(image_url).scheme not in ("http", "https")
                or not isinstance(specifications, dict)
                or not specifications
                or any(
                    not isinstance(k, str) or not isinstance(v, str)
                    for k, v in specifications.items()
                )
                or any(not isinstance(data[key], str) or not data[key] for key in text_fields)
            ):
                raise ValueError
            return cls(
                id=identifier,
                active=active,
                price=price,
                stock=stock,
                image_url=image_url,
                specifications=specifications,
                **{key: data[key] for key in text_fields},
            )
        except KeyError, TypeError, ValueError, InvalidOperation:
            raise ApiError(502, "Recibimos una respuesta incompleta del catálogo.") from None


@dataclass(frozen=True)
class TokenGrant:
    """El token no participa en repr para evitar exponerlo accidentalmente en registros."""

    access_token: str = field(repr=False)
    expires_in: int


class ApiClient:
    """Todas las rutas son internas y conocidas; ninguna URL procede del formulario."""

    def _request(self, method: str, path: str, *, token=None, payload=None, params=None):
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            # No se siguen redirecciones: una respuesta remota no debe reenviar el JWT.
            with httpx.Client(
                base_url=settings.TECHGEAR_API_URL + "/",
                timeout=httpx.Timeout(settings.TECHGEAR_API_TIMEOUT),
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = client.request(
                    method, path.lstrip("/"), headers=headers, json=payload, params=params
                )
        except httpx.RequestError:
            raise ApiError(503, "No pudimos conectar con la tienda. Intenta de nuevo.") from None
        if response.status_code == 401:
            message = (
                "Correo o contraseña incorrectos."
                if path.strip("/") == "auth/login"
                else "Tu sesión venció. Inicia sesión de nuevo."
            )
            raise ApiError(401, message)
        if response.status_code == 404:
            raise ApiError(404, "No encontramos ese componente.")
        if response.status_code >= 500 or 300 <= response.status_code < 400:
            raise ApiError(503, "La tienda no está disponible en este momento.")
        if response.status_code == 409:
            raise ApiError(409, "Ya existe un producto con ese SKU.")
        if response.status_code >= 400:
            raise ApiError(response.status_code, "No fue posible completar la solicitud.")
        # DELETE responde 204 sin cuerpo; no debe intentarse interpretar JSON.
        if response.status_code == 204:
            return None
        try:
            return response.json()
        except ValueError:
            raise ApiError(502, "La tienda devolvió una respuesta no válida.") from None

    def products(self, *, search="", category="", token=None):
        """Recupera el catálogo completo por páginas; filtros y stock pertenecen a FastAPI."""
        products = []
        offset = 0
        # Un límite total evita que una respuesta remota defectuosa genere un bucle infinito.
        for _ in range(50):
            params = {"limit": 100, "offset": offset}
            if search:
                params["search"] = search
            if category:
                params["category"] = category
            path = "products/manage/" if token else "products/"
            payload = self._request("GET", path, params=params, token=token)
            if not isinstance(payload, list):
                raise ApiError(502, "No fue posible interpretar el catálogo.")
            products.extend(Product.from_payload(item) for item in payload)
            if len(payload) < 100:
                return products
            offset += 100
        raise ApiError(502, "El catálogo es demasiado grande para esta consulta.")

    def product(self, identifier):
        if not PRODUCT_ID.fullmatch(identifier):
            raise ApiError(404, "No encontramos ese componente.")
        return Product.from_payload(self._request("GET", f"products/{identifier}"))

    def managed_product(self, identifier, token):
        """Lee la ficha administrativa sin sustituir la consulta pública."""
        if not PRODUCT_ID.fullmatch(identifier):
            raise ApiError(404, "No encontramos ese componente.")
        return Product.from_payload(
            self._request("GET", f"products/manage/{identifier}", token=token)
        )

    def save_product(self, payload, token, *, identifier=None):
        """Django envía POST para crear y PUT para editar; FastAPI valida el contrato."""
        if identifier is not None and not PRODUCT_ID.fullmatch(identifier):
            raise ApiError(404, "No encontramos ese componente.")
        path = f"products/{identifier}" if identifier else "products/"
        data = self._request("PUT" if identifier else "POST", path, token=token, payload=payload)
        return Product.from_payload(data)

    def deactivate_product(self, identifier, token):
        """Retira el producto mediante DELETE, manteniendo los pedidos históricos."""
        if not PRODUCT_ID.fullmatch(identifier):
            raise ApiError(404, "No encontramos ese componente.")
        self._request("DELETE", f"products/{identifier}", token=token)

    def login(self, email, password):
        """Las credenciales solo se envían a la dirección de API configurada en el servidor."""
        payload = self._request(
            "POST", "auth/login", payload={"email": email, "password": password}
        )
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("access_token"), str)
            or not payload["access_token"]
            or payload.get("token_type") != "bearer"
            or type(payload.get("expires_in")) is not int
            or not 0 < payload["expires_in"] <= 86400
        ):
            raise ApiError(502, "No fue posible validar el inicio de sesión.")
        return TokenGrant(payload["access_token"], payload["expires_in"])

    def profile(self, token):
        """Vuelve a consultar identidad y rol: los datos del formulario no los determinan."""
        payload = self._request("GET", "users/me", token=token)
        if (
            not isinstance(payload, dict)
            or payload.get("role") not in ("customer", "admin")
            or any(
                not isinstance(payload.get(key), str) or not payload[key]
                for key in ("id", "email", "full_name")
            )
        ):
            raise ApiError(502, "No fue posible verificar tu cuenta.")
        return {key: payload[key] for key in ("id", "full_name", "email", "role")}
