"""Tests unitaires du module refus_office (cf ADR-017)."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.core.refus_office import build_refus_office_email, check_refus_office
from app.models.opportunity import OpportunityPayload


def make_opp(concession: str = "Fiat Mulhouse", **overrides) -> OpportunityPayload:
    """Helper pour construire une opportunité valide rapidement."""
    base = {
        "opportunity_id": "006Tn00000ABC123IAF",
        "opportunity_name": "Test Client - 01-01-2026",
        "marque": "fiat",
        "concession": concession,
        "files": [],
        "vendeur_email": "vendeur@hessautomobile.com",
        "vendeur_nom": "Jean Vendeur",
    }
    base.update(overrides)
    return OpportunityPayload(**base)


# ============================================================================
# check_refus_office
# ============================================================================


class TestCheckRefusOffice:
    def test_concession_siege_matche_R001(self):
        opp = make_opp(concession="Siège")
        result = check_refus_office(opp)
        assert result is not None
        assert result.regle == "R001_siege"
        assert result.indice_confiance == 100
        assert "point de vente" in result.message_vendeur.lower()

    def test_concession_normale_ne_matche_pas(self):
        opp = make_opp(concession="Fiat Mulhouse")
        assert check_refus_office(opp) is None

    def test_concession_renault_ne_matche_pas(self):
        opp = make_opp(concession="Renault Strasbourg Illkirch", marque="renault")
        assert check_refus_office(opp) is None

    def test_siege_case_sensitive_strict(self):
        """La règle compare exactement 'Siège' (avec accent) — pas 'siege' ou 'SIEGE'."""
        assert check_refus_office(make_opp(concession="siege")) is None
        assert check_refus_office(make_opp(concession="SIEGE")) is None
        assert check_refus_office(make_opp(concession="Siege")) is None

    def test_concession_vide_ne_matche_pas(self):
        opp = make_opp(concession="")
        assert check_refus_office(opp) is None


# ============================================================================
# build_refus_office_email
# ============================================================================


@pytest.fixture
def test_settings():
    """Settings forcés en mode TEST pour les tests unitaires."""
    return Settings(
        mail_mode="test",
        mail_recipient_override="tiffanydellmann@hessautomobile.com",
        mail_comptable="axelsaphir@hessautomobile.com",
        smtp_password="dummy",
    )


@pytest.fixture
def prod_settings():
    return Settings(
        mail_mode="prod",
        mail_recipient_override="tiffanydellmann@hessautomobile.com",
        mail_comptable="axelsaphir@hessautomobile.com",
        smtp_password="dummy",
    )


class TestBuildRefusOfficeEmailModeTest:
    def test_envoie_vers_override_en_test(self, test_settings):
        opp = make_opp(concession="Siège", vendeur_email="vendeur@concession.fr")
        refus = check_refus_office(opp)
        _subject, _html, _text, recipients = build_refus_office_email(opp, refus, test_settings)

        assert recipients.to == "tiffanydellmann@hessautomobile.com"
        assert recipients.cc == []
        assert recipients.subject_prefix == "[TEST] "
        assert recipients.original_recipients == {
            "to": ["vendeur@concession.fr"],
            "cc": [],
        }

    def test_sujet_contient_le_nom_dossier(self, test_settings):
        opp = make_opp(concession="Siège", opportunity_name="DUPONT MARIE - 14-05-2026")
        refus = check_refus_office(opp)
        subject, _, _, _ = build_refus_office_email(opp, refus, test_settings)
        assert "DUPONT MARIE - 14-05-2026" in subject


class TestBuildRefusOfficeEmailModeProd:
    def test_envoie_au_vendeur_seul_sans_cc(self, prod_settings):
        """Axel suit via le dashboard, donc pas de CC sur le mail vendeur."""
        opp = make_opp(concession="Siège", vendeur_email="vendeur@concession.fr")
        refus = check_refus_office(opp)
        _, _, _, recipients = build_refus_office_email(opp, refus, prod_settings)

        assert recipients.to == "vendeur@concession.fr"
        assert recipients.cc == []
        assert recipients.subject_prefix == ""
        assert recipients.original_recipients is None

    def test_fallback_vers_comptable_si_pas_vendeur_email(self, prod_settings):
        """Si le payload n'a pas d'email vendeur (cas dégénéré), on envoie au comptable seul."""
        opp = make_opp(concession="Siège", vendeur_email=None)
        refus = check_refus_office(opp)
        _, _, _, recipients = build_refus_office_email(opp, refus, prod_settings)
        assert recipients.to == "axelsaphir@hessautomobile.com"
        assert recipients.cc == []


class TestBuildRefusOfficeEmailContent:
    def test_html_contient_le_message_vendeur(self, test_settings):
        opp = make_opp(concession="Siège")
        refus = check_refus_office(opp)
        _, html, _, _ = build_refus_office_email(opp, refus, test_settings)
        assert refus.message_vendeur in html
        assert refus.libelle in html
        assert refus.regle in html

    def test_text_body_contient_le_message_vendeur(self, test_settings):
        opp = make_opp(concession="Siège")
        refus = check_refus_office(opp)
        _, _, text, _ = build_refus_office_email(opp, refus, test_settings)
        assert refus.message_vendeur in text
        assert refus.libelle in text
        assert "HESS Automobile" in text

    def test_html_inclus_le_nom_vendeur(self, test_settings):
        opp = make_opp(concession="Siège", vendeur_nom="Marc DUPOND")
        refus = check_refus_office(opp)
        _, html, _, _ = build_refus_office_email(opp, refus, test_settings)
        assert "Marc DUPOND" in html
