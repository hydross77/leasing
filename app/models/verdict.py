"""Modèle Pydantic du verdict global produit par `verification.py`.

Le verdict est le résultat de l'analyse d'un dossier : statut, indice de confiance,
liste d'anomalies, documents manquants/valides. C'est ce qui alimente :
- la base Supabase (table `analyses`)
- le dashboard comptable (qui peut éditer anomalies avant validation)
- les mails vendeur (après validation comptable)
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.models.anomalie import Anomalie

Statut = Literal[
    "conforme",
    "non_conforme",
    "refus_office",
    "erreur_technique",
    "aucun_doc",
]


class Verdict(BaseModel):
    """Verdict final d'analyse d'un dossier."""

    statut: Statut = Field(description="Statut global du dossier")
    indice_confiance: int = Field(ge=0, le=100, description="0-100, plafonné à 50 si anomalie critique")
    anomalies: list[Anomalie] = Field(default_factory=list)
    documents_manquants: list[str] = Field(
        default_factory=list,
        description="Types de documents attendus mais non détectés (ex: 'photo_arriere_vehicule')",
    )
    documents_valides: list[str] = Field(
        default_factory=list,
        description="Types de documents détectés et conformes",
    )
    duree_ms: int | None = Field(default=None, description="Temps total d'analyse en ms")
    erreur: str | None = Field(
        default=None,
        description="Détail technique si statut = 'erreur_technique'",
    )
