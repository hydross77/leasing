"""Règles de refus d'office (cf ADR-017).

Une règle de refus d'office est binaire, claire, incontestable. Quand elle matche,
on court-circuite tout le pipeline IA + comptable :

- Pas d'appel Gemini (économie de tokens)
- Pas de validation comptable (économie de temps)
- Mail vendeur direct (avec CC comptable pour audit)
- Update SF Statut_dossier__c = en_anomalie_a_corriger

Toute règle ajoutée ici DOIT être :
1. Déterministe (pas d'IA)
2. Sans ambiguïté possible
3. Testée unitairement (cas positif ET cas négatif)
4. Documentée dans ADR-017 (table des règles)
"""

from __future__ import annotations

from app.config import Settings, get_settings
from app.models.email import EmailRecipients
from app.models.opportunity import OpportunityPayload
from app.models.refus_office import RefusOffice
from app.services.email_routing import route_recipients
from app.utils.logging import get_logger

log = get_logger("app.core.refus_office")


# ============================================================================
# Catalogue des règles — ajouts conservatistes uniquement (cf ADR-017)
# ============================================================================


def _regle_siege(opportunity: OpportunityPayload) -> RefusOffice | None:
    """R001 — Concession 'Siège' : dossier à rattacher à un point de vente."""
    if opportunity.concession == "Siège":
        return RefusOffice(
            regle="R001_siege",
            libelle="Concession Siège non éligible",
            message_vendeur=(
                "Le dossier est rattaché au Siège HESS, qui n'est pas un point de vente. "
                "Merci de modifier la concession dans Salesforce vers le point de vente "
                "concerné et de redéposer le dossier."
            ),
        )
    return None


# Liste des règles évaluées dans l'ordre. Première qui matche emporte.
REGLES: list[callable[[OpportunityPayload], RefusOffice | None]] = [
    _regle_siege,
    # Futures règles à ajouter ici, dans l'ordre de priorité.
    # Toute nouvelle règle doit être ajoutée dans ADR-017 ET testée unitairement.
]


# ============================================================================
# API publique
# ============================================================================


def check_refus_office(opportunity: OpportunityPayload) -> RefusOffice | None:
    """Vérifie si un dossier doit être refusé d'office.

    Returns:
        RefusOffice si une règle matche, None sinon (le dossier continue le pipeline normal).
    """
    for regle in REGLES:
        result = regle(opportunity)
        if result is not None:
            log.info(
                "refus_office_match",
                opportunity_id=opportunity.opportunity_id,
                regle=result.regle,
                concession=opportunity.concession,
            )
            return result
    return None


def build_refus_office_email(
    opportunity: OpportunityPayload,
    refus: RefusOffice,
    settings: Settings | None = None,
) -> tuple[str, str, str, EmailRecipients]:
    """Construit le mail à envoyer au vendeur en cas de refus d'office.

    Returns:
        (subject, html_body, text_body, recipients)
    """
    settings = settings or get_settings()

    subject = f"LEASING SOCIAL — Dossier à corriger : {opportunity.opportunity_name}"

    # Mail vendeur uniquement — Axel suit via le dashboard, pas de CC
    vendeur_to = opportunity.vendeur_email or settings.mail_comptable
    recipients = route_recipients(to_prod=vendeur_to, cc_prod=[], settings=settings)

    nom_vendeur = opportunity.vendeur_nom or "Bonjour"
    accent = "#C9A978"
    header_blue = "#2E3152"

    html_body = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{subject}</title></head>
<body style="margin:0;background:#F5F6F7;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" bgcolor="#F5F6F7"><tr><td align="center" style="padding:28px 12px;">
    <table width="640" style="max-width:100%;border-radius:14px;overflow:hidden;background:#FFFFFF;">
      <tr><td style="height:6px;background:{accent};"></td></tr>
      <tr><td bgcolor="{header_blue}" style="padding:28px;color:#FFFFFF;">
        <div style="font-size:22px;font-weight:700;">HESS Automobile</div>
        <div style="font-size:18px;font-weight:700;margin-top:6px;">Dossier non éligible</div>
        <div style="margin-top:10px;">
          <span style="display:inline-block;background:#FFFFFF;color:{header_blue};padding:2px 10px;border-radius:999px;font-size:12px;font-weight:700;">{refus.regle}</span>
        </div>
      </td></tr>
      <tr><td style="padding:24px;color:#111;font-size:14px;line-height:1.7;">
        <p>{nom_vendeur},</p>
        <p>Le dossier <strong>{opportunity.opportunity_name}</strong> (concession : {opportunity.concession})
           n'est pas éligible au dispositif Leasing Social pour la raison suivante :</p>
        <div style="background:#FFFDF8;border:1px solid #F1E8D7;border-radius:12px;padding:16px;margin:16px 0;">
          <div style="font-weight:700;color:{header_blue};margin-bottom:6px;">{refus.libelle}</div>
          <div>{refus.message_vendeur}</div>
        </div>
        <p>Aucune analyse complémentaire n'a été effectuée sur ce dossier — il s'agit d'une règle
           administrative directe. Merci de corriger et redéposer.</p>
      </td></tr>
      <tr><td style="padding:18px 24px 26px 24px;border-top:1px solid #ECEDEF;font-size:12px;color:#6B7280;">
        Cordialement, l'équipe Conformité HESS Automobile<br>
        <span style="color:#9AA1AA;">Message automatique — ne pas répondre</span>
      </td></tr>
    </table>
  </td></tr></table>
</body></html>"""

    text_body = (
        f"{nom_vendeur},\n\n"
        f"Le dossier {opportunity.opportunity_name} (concession : {opportunity.concession}) "
        f"n'est pas éligible au dispositif Leasing Social pour la raison suivante :\n\n"
        f"  {refus.libelle}\n"
        f"  {refus.message_vendeur}\n\n"
        f"Aucune analyse complémentaire n'a été effectuée sur ce dossier — il s'agit d'une règle "
        f"administrative directe. Merci de corriger et redéposer.\n\n"
        f"Cordialement,\nL'équipe Conformité HESS Automobile\n"
        f"(Message automatique — ne pas répondre)"
    )

    return subject, html_body, text_body, recipients
