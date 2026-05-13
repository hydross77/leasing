"""Orchestrateur principal de l'endpoint POST /analyze.

Étapes (cf ADR-013, ADR-015, ADR-017) :

1. Vérifier les règles de refus d'office (Siège, etc.)
   - Si match : update SF immédiate + mail vendeur direct + persist analyse → FIN
2. Sinon : extraction Gemini de chaque PDF
   - **À CÂBLER en Phase 2 quand les prompts seront prêts** (stub pour le MVP)
3. Agréger en `DossierExtrait`
4. Appliquer les règles ASP via `verifier_dossier()` → produit le `Verdict`
5. Persist l'analyse en base Supabase
6. **NE PAS** mettre à jour SF ici : c'est Axel qui décide depuis le dashboard
   (cf ADR-013 : validation comptable obligatoire pour conforme ET non_conforme)
7. Retourner la réponse à n8n
"""

from __future__ import annotations

import time

from app.core.refus_office import build_refus_office_email, check_refus_office
from app.core.verification import verifier_dossier
from app.models.analyze import AnalyzeResponse
from app.models.anomalie import Anomalie
from app.models.document import DossierExtrait
from app.models.opportunity import OpportunityPayload
from app.models.verdict import Verdict
from app.services.email_routing import send_email
from app.services.gemini_client import GeminiClient
from app.services.salesforce_client import SalesforceClient
from app.services.supabase_client import SupabaseClient
from app.utils.logging import get_logger

log = get_logger("app.core.analyze")


def orchestrate_analyze(
    payload: OpportunityPayload,
    sf: SalesforceClient,
    sb: SupabaseClient,
    gemini: GeminiClient,
) -> AnalyzeResponse:
    """Pipeline complet d'analyse d'une opportunité."""
    start = time.perf_counter()

    # =========================================================================
    # ÉTAPE 1 — Refus d'office (court-circuit complet : pas d'IA, pas de comptable)
    # =========================================================================
    if refus := check_refus_office(payload):
        log.info(
            "analyze_refus_office_match",
            opportunity_id=payload.opportunity_id,
            regle=refus.regle,
        )
        verdict = Verdict(
            statut="refus_office",
            indice_confiance=100,
            anomalies=[
                Anomalie(
                    code=refus.regle,
                    libelle=refus.libelle,
                    detail=refus.message_vendeur,
                    severite="bloquante",
                )
            ],
        )

        # Update SF immédiate
        salesforce_ok = _safe_update_sf_refus_office(sf, payload.opportunity_id)

        # Persist analyse en base
        analyse_id = _safe_persist_analyse(
            sb,
            payload=payload,
            verdict=verdict,
            duree_ms=_elapsed_ms(start),
        )

        # Mail vendeur direct
        mail_ok = _safe_send_refus_office_mail(payload, refus)

        return AnalyzeResponse(
            verdict=verdict,
            analyse_id=analyse_id,
            salesforce_updated=salesforce_ok,
            mail_sent=mail_ok,
            duree_ms=_elapsed_ms(start),
        )

    # =========================================================================
    # ÉTAPE 2 — Extraction Gemini par PDF (STUB Phase 3, à câbler Phase 2)
    # =========================================================================
    # TODO Phase 2/3 : pour chaque file de payload.files :
    #   - télécharger le PDF depuis l'URL presigned
    #   - récupérer le prompt cascade via sb.get_prompt_actif(marque, concession, type)
    #   - gemini.extract_pdf(prompt, pdf_bytes, ModelePydantic)
    #   - agréger dans DossierExtrait
    # Pour le MVP skeleton, on passe un DossierExtrait vide.
    dossier = DossierExtrait(
        opportunity_id=payload.opportunity_id,
        opportunity_name=payload.opportunity_name,
        marque=payload.marque,
        concession=payload.concession,
    )

    # =========================================================================
    # ÉTAPE 3 — Application des règles ASP (déterministe, Python pur)
    # =========================================================================
    verdict = verifier_dossier(dossier)
    log.info(
        "analyze_verdict",
        opportunity_id=payload.opportunity_id,
        statut=verdict.statut,
        indice_confiance=verdict.indice_confiance,
        nb_anomalies=len(verdict.anomalies),
        nb_docs_manquants=len(verdict.documents_manquants),
    )

    # =========================================================================
    # ÉTAPE 4 — Persist en base Supabase (table analyses)
    # =========================================================================
    analyse_id = _safe_persist_analyse(
        sb,
        payload=payload,
        verdict=verdict,
        duree_ms=_elapsed_ms(start),
    )

    # =========================================================================
    # ÉTAPE 5 — On NE TOUCHE PAS à SF (cf ADR-013 : validation comptable obligatoire)
    # =========================================================================
    # Le mail vendeur ne part qu'après que le comptable valide depuis le dashboard.
    # On ne change pas Conformite_du_dossier__c ni Tech_Dossier_verifier__c ici.

    return AnalyzeResponse(
        verdict=verdict,
        analyse_id=analyse_id,
        salesforce_updated=False,
        mail_sent=False,
        duree_ms=_elapsed_ms(start),
    )


# =========================================================================
# Helpers "safe" : capturent les erreurs pour ne pas casser le retour à n8n
# =========================================================================


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _safe_update_sf_refus_office(sf: SalesforceClient, opp_id: str) -> bool:
    """Patch SF en cas de refus d'office. Capture les erreurs."""
    try:
        sf.update_conformite(opp_id, "Client inéligible")
        sf.mark_dossier_verifier(opp_id, True)
        return True
    except Exception as exc:
        log.error("sf_update_refus_office_failed", opportunity_id=opp_id, error=str(exc))
        return False


def _safe_persist_analyse(
    sb: SupabaseClient,
    payload: OpportunityPayload,
    verdict: Verdict,
    duree_ms: int,
) -> str | None:
    """Écrit l'analyse en base. Retourne l'UUID ou None si échec."""
    try:
        analyse = sb.create_analyse(
            opportunity_id=payload.opportunity_id,
            opportunity_name=payload.opportunity_name,
            marque=payload.marque,
            concession=payload.concession,
            verdict=verdict,
            duree_ms=duree_ms,
        )
        return analyse.get("id")
    except Exception as exc:
        log.error(
            "supabase_persist_failed",
            opportunity_id=payload.opportunity_id,
            error=str(exc),
        )
        return None


def _safe_send_refus_office_mail(payload: OpportunityPayload, refus) -> bool:
    """Envoie le mail vendeur pour un refus d'office. Capture les erreurs."""
    try:
        subject, html, text, recipients = build_refus_office_email(payload, refus)
        send_email(
            subject=subject,
            html_body=html,
            recipients=recipients,
            text_body=text,
        )
        return True
    except Exception as exc:
        log.error(
            "refus_office_mail_send_failed",
            opportunity_id=payload.opportunity_id,
            error=str(exc),
        )
        return False
