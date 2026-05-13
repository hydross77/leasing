"""Dépendances FastAPI : auth + clients singleton.

Les clients (SF, Supabase, Gemini) sont instanciés une fois au premier appel
via @lru_cache. C'est correct car ils n'ont pas d'état mutable côté Python.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import Header, HTTPException, status

from app.config import get_settings
from app.services.gemini_client import GeminiClient
from app.services.salesforce_client import SalesforceClient
from app.services.supabase_client import SupabaseClient


@lru_cache(maxsize=1)
def get_salesforce_client() -> SalesforceClient:
    return SalesforceClient()


@lru_cache(maxsize=1)
def get_supabase_client() -> SupabaseClient:
    return SupabaseClient()


@lru_cache(maxsize=1)
def get_gemini_client() -> GeminiClient:
    return GeminiClient()


def verify_api_token(authorization: str = Header(default="")) -> None:
    """Vérifie le Bearer token API_TOKEN (partagé avec n8n et le dashboard)."""
    settings = get_settings()
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token requis dans le header Authorization",
        )
    token = authorization[len("Bearer ") :].strip()
    if not token or token != settings.api_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token invalide",
        )
