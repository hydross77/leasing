"""Client Supabase pour Leasing Social v2.

Repositories exposés :
- `PromptsRepository` — lecture cascade des prompts actifs (cf ADR-005)
- `AnalysesRepository` — historique des verdicts produits par l'API
- `ValidationsRepository` — décisions comptable depuis le dashboard
- `ConcessionsRepository` — lookup email diffusion par concession SF

Le client Supabase utilise le SDK officiel `supabase-py`. Les opérations sont
synchrones (l'API FastAPI wrap en `asyncio.to_thread` si besoin).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from supabase import Client, create_client

from app.config import Settings, get_settings
from app.models.verdict import Verdict
from app.utils.logging import get_logger

log = get_logger("app.services.supabase")


class SupabaseClient:
    """Client Supabase haut niveau, expose des repositories par table."""

    def __init__(
        self, settings: Settings | None = None, client: Client | None = None
    ) -> None:
        self._settings = settings or get_settings()
        if client is not None:
            # Injection pour les tests
            self._client = client
            return
        if not self._settings.supabase_url or not self._settings.supabase_key:
            raise ValueError("Credentials Supabase manquants dans .env")
        self._client = create_client(
            self._settings.supabase_url, self._settings.supabase_key
        )
        log.info("supabase_client_connected")

    @property
    def client(self) -> Client:
        return self._client

    # ========================================================================
    # PROMPTS — cascade (marque, concession) → (marque, NULL) → ('default', NULL)
    # ========================================================================

    def get_prompt_actif(
        self,
        marque: str,
        concession: str | None,
        type_prompt: str,
    ) -> dict[str, Any] | None:
        """Récupère le prompt actif selon la cascade ADR-005.

        Ordre :
        1. `(marque, concession, type_prompt, actif=true)` — surcharge concession
        2. `(marque, NULL, type_prompt, actif=true)` — fallback marque
        3. `('default', NULL, type_prompt, actif=true)` — fallback global

        Returns:
            Le record prompt complet, ou None si aucun ne matche (cas anormal).
        """
        # 1. Surcharge concession
        if concession:
            r = (
                self._client.table("prompts")
                .select("*")
                .eq("marque", marque)
                .eq("concession", concession)
                .eq("type_prompt", type_prompt)
                .eq("actif", True)
                .limit(1)
                .execute()
            )
            if r.data:
                log.debug(
                    "prompt_match_concession",
                    marque=marque,
                    concession=concession,
                    type_prompt=type_prompt,
                )
                return r.data[0]

        # 2. Fallback marque
        r = (
            self._client.table("prompts")
            .select("*")
            .eq("marque", marque)
            .is_("concession", "null")
            .eq("type_prompt", type_prompt)
            .eq("actif", True)
            .limit(1)
            .execute()
        )
        if r.data:
            log.debug("prompt_match_marque", marque=marque, type_prompt=type_prompt)
            return r.data[0]

        # 3. Fallback global
        r = (
            self._client.table("prompts")
            .select("*")
            .eq("marque", "default")
            .is_("concession", "null")
            .eq("type_prompt", type_prompt)
            .eq("actif", True)
            .limit(1)
            .execute()
        )
        if r.data:
            log.debug("prompt_match_default", type_prompt=type_prompt)
            return r.data[0]

        log.error(
            "prompt_not_found",
            marque=marque,
            concession=concession,
            type_prompt=type_prompt,
        )
        return None

    # ========================================================================
    # ANALYSES — historique des verdicts (rétention 90 j)
    # ========================================================================

    def create_analyse(
        self,
        opportunity_id: str,
        opportunity_name: str | None,
        marque: str | None,
        concession: str | None,
        verdict: Verdict,
        prompts_utilises: dict[str, str] | None = None,
        duree_ms: int | None = None,
        cout_estime_eur: float | None = None,
    ) -> dict[str, Any]:
        """Insert une analyse dans la table `analyses` après le passage Gemini."""
        row = {
            "opportunity_id": opportunity_id,
            "opportunity_name": opportunity_name,
            "marque": marque,
            "concession": concession,
            "statut": verdict.statut,
            "indice_confiance": verdict.indice_confiance,
            "nb_documents": len(verdict.documents_valides),
            "documents_manquants": verdict.documents_manquants,
            "anomalies": [a.model_dump() for a in verdict.anomalies],
            "prompts_utilises": prompts_utilises,
            "duree_ms": duree_ms,
            "cout_estime_eur": cout_estime_eur,
            "erreur": verdict.erreur,
        }
        r = self._client.table("analyses").insert(row).execute()
        analyse = r.data[0]
        log.info(
            "analyse_created",
            analyse_id=analyse["id"],
            opportunity_id=opportunity_id,
            statut=verdict.statut,
            indice_confiance=verdict.indice_confiance,
        )
        return analyse

    def get_analyse(self, analyse_id: str) -> dict[str, Any] | None:
        r = (
            self._client.table("analyses")
            .select("*")
            .eq("id", analyse_id)
            .limit(1)
            .execute()
        )
        return r.data[0] if r.data else None

    def list_analyses_en_attente(
        self, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Liste les analyses sans validation comptable encore (pour dashboard)."""
        # Approche simple : sous-requête NOT IN
        validations_existantes = (
            self._client.table("validations").select("analyse_id").execute()
        )
        ids_valides = {v["analyse_id"] for v in validations_existantes.data}
        r = (
            self._client.table("analyses")
            .select("*")
            .in_("statut", ["conforme", "non_conforme"])
            .order("cree_le", desc=True)
            .limit(limit * 2)  # marge car on filtre côté Python
            .execute()
        )
        en_attente = [a for a in r.data if a["id"] not in ids_valides]
        return en_attente[:limit]

    # ========================================================================
    # VALIDATIONS — décisions comptable depuis le dashboard
    # ========================================================================

    def create_validation(
        self,
        analyse_id: str,
        opportunity_id: str,
        statut: str,
        decision_comptable: str,
        anomalies_finales: list[dict[str, Any]],
        comptable_email: str,
        anomalies_ajoutees: list[dict[str, Any]] | None = None,
        anomalies_retirees: list[dict[str, Any]] | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Insert une validation comptable.

        Args:
            statut: 'validee_conforme' | 'validee_non_conforme' | 'refus_office'
            decision_comptable: 'confirme_ia' | 'inverse_ia' | 'modifie' | 'refus_office_auto'
        """
        row = {
            "analyse_id": analyse_id,
            "opportunity_id": opportunity_id,
            "statut": statut,
            "decision_comptable": decision_comptable,
            "anomalies_finales": anomalies_finales,
            "anomalies_ajoutees": anomalies_ajoutees or [],
            "anomalies_retirees": anomalies_retirees or [],
            "comptable_email": comptable_email,
            "notes": notes,
            "valide_le": datetime.now(UTC).isoformat(),
        }
        r = self._client.table("validations").insert(row).execute()
        validation = r.data[0]
        log.info(
            "validation_created",
            validation_id=validation["id"],
            analyse_id=analyse_id,
            opportunity_id=opportunity_id,
            statut=statut,
            comptable=comptable_email,
        )
        return validation

    # ========================================================================
    # CONCESSIONS — lookup email diffusion
    # ========================================================================

    def get_concession_email(self, nom_salesforce: str) -> str | None:
        """Retourne l'email de diffusion d'une concession ou None si absente."""
        r = (
            self._client.table("concessions")
            .select("email_conformite")
            .eq("nom_salesforce", nom_salesforce)
            .eq("actif", True)
            .limit(1)
            .execute()
        )
        return r.data[0]["email_conformite"] if r.data else None
