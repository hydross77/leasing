"""Modèle Pydantic pour le routage email — applique le mode TEST/PROD global."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class EmailRecipients(BaseModel):
    """Destinataires finaux d'un mail après application du mode TEST/PROD.

    En mode test :
        - `to` = override (tiffanydellmann@hessautomobile.com)
        - `cc` = []
        - `subject_prefix` = "[TEST] "
        - `original_recipients` conserve la trace de ce qui aurait été envoyé en prod

    En mode prod :
        - `to` = vendeur (depuis SF)
        - `cc` = comptable HESS + concession
        - `subject_prefix` = ""
    """

    to: EmailStr
    cc: list[EmailStr] = Field(default_factory=list)
    subject_prefix: str = ""
    original_recipients: dict[str, list[str]] | None = Field(
        default=None,
        description="Trace des destinataires originaux quand MAIL_MODE=test (audit + visibilité)",
    )
