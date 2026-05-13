"""Modèle Pydantic décrivant une opportunité Salesforce telle que reçue par l'API.

Le payload est construit par n8n à partir de la SOQL puis envoyé à `/analyze`.
L'API ne fait pas elle-même la SOQL Opportunity — c'est n8n qui orchestre.
"""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class FileRef(BaseModel):
    """Référence à un fichier NEILON__File__c attaché à une opportunité."""

    id: str = Field(description="Salesforce Id du NEILON__File__c (15/18 chars)")
    name: str = Field(description="Nom du fichier tel qu'uploadé par le vendeur")
    url: str = Field(description="Presigned URL S3 pour télécharger le PDF")
    mime_type: str = "application/pdf"
    created_date: str | None = Field(
        default=None, description="ISO datetime de création SF — sert à la déduplication"
    )


class OpportunityPayload(BaseModel):
    """Payload reçu par POST /analyze depuis n8n."""

    opportunity_id: str = Field(description="Salesforce Opportunity Id (15/18 chars)")
    opportunity_name: str = Field(description="ex: 'Doungou TOURÉ - 23-01-2026'")
    marque: str = Field(description="Marque normalisée minuscule (fiat, renault, ...)")
    concession: str = Field(description="Nom SF exact (ex: 'Fiat Mulhouse')")
    files: list[FileRef] = Field(default_factory=list)

    # Coordonnées vendeur (Owner Salesforce — extrait par n8n via SOQL)
    vendeur_email: EmailStr | None = Field(
        default=None,
        description="Email du commercial qui détient l'opportunité (Opportunity.Owner.Email)",
    )
    vendeur_nom: str | None = Field(default=None, description="Nom complet du vendeur")

    # Optionnels : champs SF utiles pour les règles
    close_date: str | None = None
    stage_name: str | None = None
    statut_dossier: str | None = Field(
        default=None,
        description="Valeur de Statut_dossier__c (cf ADR-015) — nouveau/corrige_a_reverifier/...",
    )
