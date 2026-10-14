from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router
from .config import get_settings
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

# 同源部署（前端由本服务一起托管，或走 Vite 代理）不需要 CORS。
# 只有前端从别的域名直连本 API 时才需要，于是由 AIR_OBSERVATORY_CORS_ORIGINS 显式开启。
if get_settings().cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origin_list,
        allow_methods=["GET"],
        allow_headers=["*"],
    )


@app.get("/api/health")
def health() -> dict[str, bool]:
    return {"ok": True}
