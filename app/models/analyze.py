"""Modèle de réponse de l'endpoint POST /analyze."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.verdict import Verdict


class AnalyzeResponse(BaseModel):
    """Réponse retournée à n8n après analyse d'une opportunité."""

    verdict: Verdict
    analyse_id: str | None = Field(
        default=None,
        description="UUID Supabase de l'analyse persistée (null si erreur d'écriture)",
    )
    salesforce_updated: bool = Field(
        default=False,
        description="True si l'API a déjà patché SF (cas refus d'office uniquement)",
    )
    mail_sent: bool = Field(
        default=False,
        description="True si le mail vendeur a été envoyé (cas refus d'office uniquement)",
    )
    duree_ms: int = Field(description="Durée totale de l'analyse en ms")
