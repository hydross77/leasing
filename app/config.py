"""Settings applicatifs chargés depuis l'environnement.

Validation stricte au démarrage via pydantic-settings.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings de l'application — instancié une seule fois via get_settings()."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Environnement
    env: Literal["dev", "staging", "prod"] = "dev"
    log_level: str = "INFO"

    # Mail override (PHASE DE TEST)
    # Si défini, tous les mails (concession + interne) sont redirigés vers cette adresse.
    # En prod : vide. En dev/test : tiffanydellmann@hessautomobile.com.
    mail_recipient_override: str | None = None

    # Auth API (token partagé avec n8n)
    api_token: str = "changeme"

    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""

    # IA
    gemini_api_key: str = ""
    openai_api_key: str = ""

    # Sentry (optionnel)
    sentry_dsn: str | None = None

    # Salesforce (Phase 1)
    salesforce_username: str = ""
    salesforce_password: str = ""
    salesforce_token: str = ""
    salesforce_domain: str = "login"

    # Phase 1 — chiffrement local des PDFs (RGPD)
    dataset_encryption_key: str = Field(default="", description="Fernet key base64")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retourne l'instance unique de Settings (cachée)."""
    return Settings()
