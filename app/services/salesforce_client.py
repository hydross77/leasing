"""Client Salesforce haut niveau pour Leasing Social v2.

Wrapper autour de `simple_salesforce` qui expose les opérations métier dont
l'API et le dashboard comptable ont besoin :

- Lecture : list des opps à traiter, détail d'une opp + fichiers + owner
- Écriture : Conformite_du_dossier__c, StageName (back-office Axel),
  Tech_Dossier_verifier__c

Principe : Streamlit (dashboard) n'appelle JAMAIS SF directement.
Toute opération SF passe par l'API FastAPI qui passe par ce client (cf ADR-016).

Mapping verdict interne → valeur SF Conformite_du_dossier__c :
- refus_office       → 'Client inéligible'
- non_conforme       → 'Document absent ou à corriger'
- conforme           → 'Bon pour livraison'
- erreur_technique   → inchangé
"""

from __future__ import annotations

from typing import Any, Literal

from simple_salesforce import Salesforce
from simple_salesforce.exceptions import SalesforceError

from app.config import Settings, get_settings
from app.models.opportunity import FileRef, OpportunityPayload
from app.utils.logging import get_logger

log = get_logger("app.services.salesforce")


# ============================================================================
# Valeurs autorisées sur les picklists SF (mapping verdict → SF)
# ============================================================================

ConformiteValue = Literal[
    "- Aucun -",
    "Client inéligible",
    "Document absent ou à corriger",
    "Bon pour livraison",
    "Dossier conforme après la livraison",
]

StageValue = Literal[
    "- Aucun -",
    "1- Nouveau",
    "2- Découverte des besoins",
    "3- Offre en cours",
    "4- Gagné",
    "4- Gagné / Facturé",
    "4- Gagné / Livré",
    "4- Gagné / Facturé / Livré",
    "5- Perdu",
]


# ============================================================================
# SOQL
# ============================================================================

# Détail d'une opp + Owner (vendeur) pour construire OpportunityPayload
SOQL_OPPORTUNITY_DETAIL = """
SELECT
    Id, Name, StageName, CloseDate, LastModifiedDate,
    Concession_du_proprietaire__c, Leasing_electrique__c,
    Conformite_du_dossier__c, Description,
    OwnerId, Owner.Email, Owner.FirstName, Owner.LastName, Owner.Name
FROM Opportunity
WHERE Id = '{opp_id}'
LIMIT 1
"""

# Opps à traiter en prod — cf ADR-015 révisé (champs SF existants)
SOQL_OPPORTUNITIES_A_TRAITER = """
SELECT
    Id, Name, StageName, CloseDate,
    Concession_du_proprietaire__c, Conformite_du_dossier__c,
    OwnerId, Owner.Email, Owner.Name
FROM Opportunity
WHERE Leasing_electrique__c = TRUE
  AND Tech_Dossier_verifier__c = FALSE
  AND StageName = '4- Gagné'
  AND Concession_du_proprietaire__c != 'Siège'
  AND (Conformite_du_dossier__c = NULL
       OR Conformite_du_dossier__c = '- Aucun -'
       OR Conformite_du_dossier__c = 'Document absent ou à corriger')
ORDER BY LastModifiedDate ASC
LIMIT {limit}
"""

# Fichiers NEILON__File__c d'une opp
SOQL_FILES = """
SELECT
    Id, Name, CreatedDate,
    NEILON__Opportunity__c, NEILON__File_Presigned_URL__c
FROM NEILON__File__c
WHERE NEILON__Opportunity__c = '{opp_id}'
ORDER BY CreatedDate DESC
"""


# ============================================================================
# Client
# ============================================================================


class SalesforceClient:
    """Client Salesforce haut niveau.

    Instancier une fois par process. L'API FastAPI le tient en singleton via
    `get_salesforce_client()` (injection de dépendance).
    """

    def __init__(
        self, settings: Settings | None = None, sf: Salesforce | None = None
    ) -> None:
        self._settings = settings or get_settings()
        if sf is not None:
            # Pour les tests : on injecte un mock
            self._sf = sf
            return
        if not all(
            [
                self._settings.salesforce_username,
                self._settings.salesforce_password,
                self._settings.salesforce_token,
            ]
        ):
            raise ValueError("Credentials Salesforce manquants dans .env")
        self._sf = Salesforce(
            username=self._settings.salesforce_username,
            password=self._settings.salesforce_password,
            security_token=self._settings.salesforce_token,
            domain=self._settings.salesforce_domain,
        )
        log.info(
            "salesforce_client_connected", domain=self._settings.salesforce_domain
        )

    # ---- Lecture ------------------------------------------------------------

    def get_opportunity(self, opp_id: str) -> OpportunityPayload | None:
        """Charge une opp + ses fichiers + son owner. None si introuvable."""
        result = self._sf.query(SOQL_OPPORTUNITY_DETAIL.format(opp_id=opp_id))
        records = result.get("records", [])
        if not records:
            log.warning("salesforce_opp_not_found", opportunity_id=opp_id)
            return None
        files = self.get_files(opp_id)
        return _record_to_payload(records[0], files)

    def list_a_traiter(self, limit: int = 20) -> list[OpportunityPayload]:
        """Liste les opps à (re-)analyser selon la SOQL de prod (ADR-015 révisé).

        Pour chaque opp, charge aussi ses fichiers — appel séparé par opp donc
        attention au quota SF si limit est grand.
        """
        result = self._sf.query(SOQL_OPPORTUNITIES_A_TRAITER.format(limit=limit))
        records = result.get("records", [])
        payloads: list[OpportunityPayload] = []
        for rec in records:
            files = self.get_files(rec["Id"])
            payloads.append(_record_to_payload(rec, files))
        log.info("salesforce_list_a_traiter", count=len(payloads), limit=limit)
        return payloads

    def get_files(self, opp_id: str) -> list[FileRef]:
        """Liste des NEILON__File__c d'une opp, plus récents d'abord."""
        try:
            result = self._sf.query(SOQL_FILES.format(opp_id=opp_id))
        except SalesforceError as exc:
            log.warning("salesforce_files_query_failed", opportunity_id=opp_id, error=str(exc))
            return []
        return [
            FileRef(
                id=r["Id"],
                name=r.get("Name") or r["Id"],
                url=r.get("NEILON__File_Presigned_URL__c", "") or "",
                created_date=r.get("CreatedDate"),
            )
            for r in result.get("records", [])
        ]

    # ---- Écriture -----------------------------------------------------------

    def update_conformite(self, opp_id: str, valeur: ConformiteValue) -> None:
        """Met à jour Conformite_du_dossier__c sur une opp.

        Appelé par :
        - L'API après refus d'office (valeur='Client inéligible')
        - L'API après validation comptable
        - Le dashboard si Axel override manuellement
        """
        self._sf.Opportunity.update(opp_id, {"Conformite_du_dossier__c": valeur})
        log.info(
            "salesforce_update_conformite",
            opportunity_id=opp_id,
            valeur=valeur,
        )

    def update_stage(self, opp_id: str, stage: StageValue) -> None:
        """Met à jour StageName — réservé au dashboard Axel (back-office)."""
        self._sf.Opportunity.update(opp_id, {"StageName": stage})
        log.info("salesforce_update_stage", opportunity_id=opp_id, stage=stage)

    def mark_dossier_verifier(self, opp_id: str, value: bool) -> None:
        """Met à jour Tech_Dossier_verifier__c.

        - value=True : analyse + validation terminées, ne pas re-traiter
        - value=False : forcer une (re-)analyse au prochain cycle n8n

        N.B. : SF décoche automatiquement ce champ à chaque modif de fichier
        sur l'opp, donc on n'a généralement pas besoin de passer False
        manuellement — sauf forcer une ré-analyse depuis le dashboard.
        """
        self._sf.Opportunity.update(opp_id, {"Tech_Dossier_verifier__c": value})
        log.info("salesforce_mark_verifier", opportunity_id=opp_id, value=value)


# ============================================================================
# Helpers
# ============================================================================


def _record_to_payload(rec: dict[str, Any], files: list[FileRef]) -> OpportunityPayload:
    """Convertit un record SF en OpportunityPayload Pydantic."""
    owner = rec.get("Owner") or {}
    concession = rec.get("Concession_du_proprietaire__c") or "inconnu"
    marque = concession.strip().split(" ")[0].lower() if concession.strip() else "inconnu"
    return OpportunityPayload(
        opportunity_id=rec["Id"],
        opportunity_name=rec.get("Name", ""),
        marque=marque,
        concession=concession,
        files=files,
        vendeur_email=owner.get("Email"),
        vendeur_nom=owner.get("Name"),
        close_date=rec.get("CloseDate"),
        stage_name=rec.get("StageName"),
        statut_dossier=rec.get("Conformite_du_dossier__c"),
    )
