"""Modèle Pydantic d'une anomalie détectée par le vérificateur ASP 2025."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Anomalie(BaseModel):
    """Une anomalie détectée sur un dossier par les règles `verification.py`.

    Code court (`A001_rfr_part`) pour suivi/monitoring, libellé en français pour
    affichage humain (mail vendeur, dashboard comptable), détail facultatif avec
    les valeurs constatées vs seuils ASP.
    """

    code: str = Field(
        description="Code court de la règle, ex: 'A001_rfr_part', 'A005_aide_27_ttc'"
    )
    libelle: str = Field(
        description="Description en français, prête à afficher dans un mail"
    )
    detail: str | None = Field(
        default=None,
        description="Détail avec valeurs constatées vs seuils (ex: '18 624 € / 2 parts = 9 312 €/part, seuil 16 300 €')",
    )
    severite: Literal["bloquante", "alerte"] = Field(
        default="bloquante",
        description="bloquante = dossier non conforme. alerte = à surveiller mais ne bloque pas.",
    )
    document_concerne: str | None = Field(
        default=None,
        description="Type de document à corriger (ex: 'bon_de_commande', 'avis_imposition')",
    )
