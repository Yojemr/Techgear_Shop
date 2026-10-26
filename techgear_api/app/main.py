"""Punto de entrada ASGI, conexión MongoDB y rutas versionadas de la tienda."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import auth, orders, products, users
from app.core.config import get_settings
from app.db.mongodb import mongo_connection


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Comparte la base MongoDB durante la vida de esta instancia de la API."""
    # FastAPI ejecuta lo anterior a yield al arrancar y lo posterior al detenerse.
    async with mongo_connection(get_settings()) as database:
        app.state.database = database
        try:
            yield
        finally:
            del app.state.database


app = FastAPI(
    title="Techgear Shop API",
    description="API de catálogo, autenticación y pedidos de Techgear Shop.",
    version="0.2.0",
    lifespan=lifespan,
)

# Swagger organiza operaciones por área y permite probar la API desde /docs.
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(products.router)
app.include_router(orders.router)


@app.get("/", tags=["Sistema"])
def root() -> dict[str, str]:
    """Identifica el servicio; esta ruta no realiza un ping adicional a MongoDB."""
    return {"name": "Techgear Shop API", "status": "ok"}
