"""Route POST /analyze — analyse complète d'un dossier Leasing Social.

Appelée par n8n après avoir détecté une opp avec Tech_Dossier_verifier__c = FALSE.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import (
    get_gemini_client,
    get_salesforce_client,
    get_supabase_client,
    verify_api_token,
)
from app.core.analyze import orchestrate_analyze
from app.models.analyze import AnalyzeResponse
from app.models.opportunity import OpportunityPayload
from app.services.gemini_client import GeminiClient
from app.services.salesforce_client import SalesforceClient
from app.services.supabase_client import SupabaseClient

router = APIRouter(
    prefix="/analyze",
    tags=["analyze"],
    dependencies=[Depends(verify_api_token)],
)


@router.post("", response_model=AnalyzeResponse)
def analyze(
    payload: OpportunityPayload,
    sf: SalesforceClient = Depends(get_salesforce_client),
    sb: SupabaseClient = Depends(get_supabase_client),
    gemini: GeminiClient = Depends(get_gemini_client),
) -> AnalyzeResponse:
    """Analyse complète d'une opportunité Leasing Social.

    Flux selon ADR-013, ADR-015, ADR-017 :
    - Refus d'office (Siège, etc.) → mail vendeur direct + update SF + retour
    - Sinon : extraction Gemini → vérification ASP → persist Supabase → retour
      (pas de mail/SF tant que le comptable n'a pas validé via le dashboard)
    """
    return orchestrate_analyze(payload=payload, sf=sf, sb=sb, gemini=gemini)
