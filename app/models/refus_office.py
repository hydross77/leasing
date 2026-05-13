"""Modèle Pydantic pour les verdicts de refus d'office (cf ADR-017).

Un refus d'office court-circuite le pipeline IA + comptable : règle binaire claire,
mail vendeur direct, update SF immédiat.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RefusOffice(BaseModel):
    """Résultat d'une règle de refus d'office matchée sur une opportunité."""

    regle: str = Field(description="Code court de la règle (ex: 'R001_siege')")
    libelle: str = Field(description="Nom humain de la règle (ex: 'Concession Siège non éligible')")
    message_vendeur: str = Field(
        description="Texte à inclure dans le mail vendeur, en français, sans variables"
    )
    indice_confiance: int = Field(
        default=100,
        ge=0,
        le=100,
        description="Toujours 100 pour une règle binaire (certitude déterministe)",
    )
