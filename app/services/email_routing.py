"""Service de routage et d'envoi email pour le système Leasing Social.

Applique le mode TEST/PROD global (cf .env MAIL_MODE) :

- mail_mode = "test" :
    - TOUS les mails partent vers `mail_recipient_override` (Tiffany par défaut)
    - CC vidées
    - Sujet préfixé "[TEST] "
    - Les destinataires originaux (prod) sont tracés dans le corps du mail
      en début, pour visibilité humaine

- mail_mode = "prod" :
    - Routage normal : `to`/`cc` honorés tels quels
    - Envoi via SMTP Gmail (compte copilote@hessautomobile.com)

L'envoi se fait dans tous les cas via SMTP Gmail. Le mode TEST ne désactive PAS
l'envoi — il change juste le destinataire pour que Tiffany puisse vérifier les
mails sans risquer d'envoyer aux concessions.
"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from app.config import Settings, get_settings
from app.models.email import EmailRecipients
from app.utils.logging import get_logger

log = get_logger("app.services.email_routing")


def route_recipients(
    to_prod: str,
    cc_prod: list[str] | None = None,
    settings: Settings | None = None,
) -> EmailRecipients:
    """Applique le mode TEST/PROD aux destinataires d'un mail.

    Args:
        to_prod: destinataire principal en mode prod (ex: email vendeur)
        cc_prod: liste de CC en mode prod (ex: comptable + concession)
        settings: injecté pour faciliter les tests

    Returns:
        EmailRecipients avec destinataires effectifs après application du mode.
    """
    settings = settings or get_settings()
    cc_prod = cc_prod or []

    if settings.mail_mode == "test":
        return EmailRecipients(
            to=settings.mail_recipient_override,
            cc=[],
            subject_prefix="[TEST] ",
            original_recipients={"to": [to_prod], "cc": cc_prod},
        )

    return EmailRecipients(
        to=to_prod,
        cc=cc_prod,
        subject_prefix="",
        original_recipients=None,
    )


def _build_test_banner(original: dict[str, list[str]] | None) -> str:
    """Construit un bandeau visible affichant les destinataires originaux en mode TEST."""
    if not original:
        return ""
    to = ", ".join(original.get("to", []))
    cc = ", ".join(original.get("cc", []))
    return (
        '<div style="background:#FFF3CD;border:1px solid #FFE69C;padding:12px;'
        'margin-bottom:16px;font-family:Arial,sans-serif;font-size:13px;color:#664D03;">'
        "<strong>⚠️ MODE TEST</strong> — En production ce mail serait envoyé à :<br>"
        f"<strong>TO :</strong> {to or '(aucun)'}<br>"
        f"<strong>CC :</strong> {cc or '(aucun)'}"
        "</div>"
    )


def send_email(
    subject: str,
    html_body: str,
    recipients: EmailRecipients,
    text_body: str | None = None,
    settings: Settings | None = None,
) -> None:
    """Envoie un mail via SMTP Gmail (compte copilote@hessautomobile.com).

    En mode TEST, ajoute automatiquement un bandeau visible avec les destinataires
    qui auraient reçu le mail en prod.
    """
    settings = settings or get_settings()

    if not settings.smtp_password:
        raise ValueError("SMTP_PASSWORD manquant dans .env — envoi mail impossible")

    msg = EmailMessage()
    msg["Subject"] = recipients.subject_prefix + subject
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from}>"
    msg["To"] = recipients.to
    if recipients.cc:
        msg["Cc"] = ", ".join(recipients.cc)

    # Bandeau TEST en haut du corps HTML
    banner = _build_test_banner(recipients.original_recipients)
    final_html = banner + html_body

    if text_body:
        msg.set_content(text_body)
        msg.add_alternative(final_html, subtype="html")
    else:
        msg.set_content(final_html, subtype="html")

    all_recipients = [recipients.to, *recipients.cc]

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context) as smtp:
        smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg, to_addrs=all_recipients)

    log.info(
        "email_sent",
        mode=settings.mail_mode,
        subject=subject,
        to=recipients.to,
        cc_count=len(recipients.cc),
        original_to=(recipients.original_recipients or {}).get("to"),
    )
