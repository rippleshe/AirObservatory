from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api import router
from .db import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Air Observatory API",
    description=(
        "Air-quality observations, atmospheric-model fields, forecasts, "
        "provenance, and model-evaluation data."
    ),
    lifespan=lifespan,
)
app.include_router(router)


@app.get("/api/health")
def health() -> dict[str, bool]:
    return {"ok": True}
