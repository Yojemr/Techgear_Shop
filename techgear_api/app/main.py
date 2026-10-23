from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.db.mongodb import mongo_connection


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with mongo_connection(get_settings()) as database:
        app.state.database = database
        try:
            yield
        finally:
            del app.state.database


app = FastAPI(
    title="Techgear Shop API",
    description="API de catálogo y pedidos de Techgear Shop.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/", tags=["Sistema"])
def root() -> dict[str, str]:
    return {"name": "Techgear Shop API", "status": "ok"}
