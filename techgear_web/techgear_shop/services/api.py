"""Cliente HTTP de FastAPI: limita tiempos de espera y oculta detalles internos."""

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

import httpx
from django.conf import settings
from django.utils.text import slugify

from ..models import Cart, Order

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

    @property
    def slug(self):
        """URL comercial legible; el ObjectId permanece en las llamadas internas a la API."""
        return slugify(f"{self.name}-{self.sku}")

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
            raise ApiError(404, "No encontramos el recurso solicitado.")
        if response.status_code >= 500 or 300 <= response.status_code < 400:
            raise ApiError(503, "La tienda no está disponible en este momento.")
        if response.status_code == 412 and path.startswith("products/"):
            raise ApiError(
                412,
                "El inventario cambió mientras editabas. Abre de nuevo la edición "
                "y revisa las existencias antes de guardar.",
            )
        if response.status_code == 409:
            if path.startswith("cart/"):
                message = (
                    "El carrito cambió o no hay existencias suficientes. "
                    "Revisa las cantidades y los precios antes de confirmar."
                )
            elif path.startswith("orders/"):
                message = (
                    "El pedido cambió o la acción no está disponible. Revisa su estado actual."
                )
            elif path == "auth/register":
                message = "Ya existe una cuenta con ese correo. Puedes iniciar sesión."
            else:
                message = "Ya existe un producto con ese SKU."
            raise ApiError(409, message)
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

    def product_by_slug(self, slug):
        matches = [product for product in self.products() if product.slug == slug]
        if len(matches) != 1:
            raise ApiError(404, "No encontramos ese componente.")
        return matches[0]

    def register(self, full_name, email, password):
        payload = self._request(
            "POST",
            "auth/register",
            payload={
                "full_name": full_name,
                "email": email,
                "password": password,
            },
        )
        if not isinstance(payload, dict) or payload.get("role") != "customer":
            raise ApiError(502, "No fue posible verificar el registro.")
        return payload

    def _read_model(self, model, payload):
        try:
            return model.from_payload(payload)
        except KeyError, TypeError, ValueError, AttributeError, InvalidOperation:
            raise ApiError(
                502, "La tienda devolvió datos incompletos del carrito o pedido."
            ) from None

    def cart(self, token):
        return self._read_model(Cart, self._request("GET", "cart/", token=token))

    def change_cart(self, identifier, quantity, token, *, add=False):
        if not PRODUCT_ID.fullmatch(identifier):
            raise ApiError(404, "No encontramos ese componente.")
        return self._read_model(
            Cart,
            self._request(
                "POST" if add else "PUT",
                f"cart/items/{identifier}",
                token=token,
                payload={"quantity": quantity},
            ),
        )

    def clear_cart(self, token):
        return self._read_model(Cart, self._request("DELETE", "cart/", token=token))

    def heartbeat(self, token):
        payload = self._request("POST", "cart/heartbeat", token=token)
        if not isinstance(payload, dict) or type(payload.get("count")) is not int:
            raise ApiError(502, "No pudimos verificar la reserva.")
        return payload

    def checkout(self, version, total, token):
        return self._read_model(
            Order,
            self._request(
                "POST",
                "cart/checkout",
                token=token,
                payload={"version": version, "expected_total": str(total)},
            ),
        )

    def orders(self, token):
        payload = self._request("GET", "orders/", token=token, params={"mine": True})
        if not isinstance(payload, list):
            raise ApiError(502, "No pudimos leer tus pedidos.")
        return [self._read_model(Order, item) for item in payload]

    def order(self, identifier, token):
        if not PRODUCT_ID.fullmatch(identifier):
            raise ApiError(404, "Pedido no encontrado.")
        return self._read_model(Order, self._request("GET", f"orders/{identifier}", token=token))

    def import_cart(self, selection, transfer_id, token):
        return self._read_model(
            Cart,
            self._request(
                "POST",
                "cart/import",
                token=token,
                payload={
                    "transfer_id": transfer_id,
                    "items": [
                        {"product_id": key, "quantity": value} for key, value in selection.items()
                    ],
                },
            ),
        )

    def managed_orders(self, token, *, state="", page=1):
        """La API aplica rol, estado y paginación; no filtra solo una página en memoria."""
        params = {"mine": False, "limit": 21, "offset": (page - 1) * 20}
        if state:
            params["order_status"] = state
        payload = self._request("GET", "orders/", token=token, params=params)
        if not isinstance(payload, list):
            raise ApiError(502, "No pudimos leer los pedidos.")
        return [self._read_model(Order, item) for item in payload]

    def update_order(self, identifier, state, expected_status, message, token):
        if not PRODUCT_ID.fullmatch(identifier):
            raise ApiError(404, "Pedido no encontrado.")
        return self._read_model(
            Order,
            self._request(
                "PATCH",
                f"orders/{identifier}/status",
                token=token,
                payload={"status": state, "expected_status": expected_status, "message": message},
            ),
        )

    def notify_order(self, identifier, message, request_id, token):
        if not PRODUCT_ID.fullmatch(identifier):
            raise ApiError(404, "Pedido no encontrado.")
        return self._read_model(
            Order,
            self._request(
                "POST",
                f"orders/{identifier}/notifications",
                token=token,
                payload={"message": message, "request_id": request_id},
            ),
        )
