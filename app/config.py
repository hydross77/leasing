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

    # Mode mail global — TEST = tous les mails vers mail_recipient_override
    #                   PROD = routage normal (vendeur + concession + comptable)
    mail_mode: Literal["test", "prod"] = "test"

    # Destinataire unique en mode TEST. Ignoré si mail_mode = "prod".
    mail_recipient_override: str = "tiffanydellmann@hessautomobile.com"

    # Adresse du comptable HESS (un seul destinataire interne, pas de CC additionnels)
    # En mode test, ignoré : tous les mails partent vers mail_recipient_override
    mail_comptable: str = "axelsaphir@hessautomobile.com"

    # SMTP Gmail (compte copilote@hessautomobile.com) — utilisé en mode prod ET test
    # En mode test, on envoie quand même via SMTP mais vers mail_recipient_override
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    smtp_user: str = "copilote@hessautomobile.com"
    smtp_password: str = ""
    smtp_from: str = "copilote@hessautomobile.com"
    smtp_from_name: str = "HESS Conformité Leasing"

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
