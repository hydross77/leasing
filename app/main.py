"""Entrée FastAPI — Leasing Social.

Phase 0 : healthcheck uniquement.
Les endpoints métier (/analyze, /validation/...) seront ajoutés en Phase 3+.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.responses import Response
from sentry_sdk.integrations.fastapi import FastApiIntegration

from app import __version__
from app.api.routes import health
from app.config import get_settings
from app.utils.logging import get_logger, setup_logging


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Initialisation au démarrage de l'application."""
    settings = get_settings()
    setup_logging(settings.log_level)

    log = get_logger("app.startup")

    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.env,
            release=__version__,
            traces_sample_rate=0.1 if settings.env == "prod" else 1.0,
            integrations=[FastApiIntegration()],
        )
        log.info("sentry_initialized", env=settings.env)

    log.info("app_started", env=settings.env, version=__version__)
    yield
    log.info("app_stopped")


app = FastAPI(
    title="Leasing Social — Conformité ASP 2025",
    description="API d'analyse automatique des dossiers Leasing Social pour HESS Automobile.",
    version=__version__,
    lifespan=lifespan,
)


@app.middleware("http")
async def log_requests(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Log structuré de chaque requête HTTP (méthode, path, durée, status)."""
    log = get_logger("app.http")
    start = time.perf_counter()
    response: Response = await call_next(request)
    duree_ms = int((time.perf_counter() - start) * 1000)
    log.info(
        "http_request",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duree_ms=duree_ms,
    )
    return response


app.include_router(health.router)
