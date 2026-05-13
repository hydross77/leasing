"""Endpoint healthcheck — utilisé par Render et n8n pour vérifier la disponibilité."""

from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Vérifie que l'API est up.

    Pas d'authentification requise — appelé toutes les 30s par Render.
    """
    settings = get_settings()
    return {
        "status": "ok",
        "env": settings.env,
        "version": __version__,
    }
