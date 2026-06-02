"""Главный модуль FastAPI."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import (
    acts,
    anomalies,
    auth,
    contractors,
    dashboard,
    objects,
    orders,
    telemetry,
    works,
)
from app.core.config import settings
from app.core.logging import get_logger, setup_logging

setup_logging()
log = get_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("startup", app=settings.app_name, env=settings.app_env)
    yield
    log.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="АСКК Татнефть-Добыча — API",
        version="0.1.0",
        description=(
            "Прототип системы контроля качества работ подрядчиков. "
            "Документация OpenAPI: /docs, /redoc"
        ),
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "app": settings.app_name}

    prefix = settings.api_prefix
    app.include_router(auth.router, prefix=prefix)
    app.include_router(contractors.router, prefix=prefix)
    app.include_router(objects.router, prefix=prefix)
    app.include_router(works.router, prefix=prefix)
    app.include_router(orders.router, prefix=prefix)
    app.include_router(acts.router, prefix=prefix)
    app.include_router(telemetry.router, prefix=prefix)
    app.include_router(anomalies.router, prefix=prefix)
    app.include_router(dashboard.router, prefix=prefix)

    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
    )
