"""Tests unitaires du service email_routing (mode TEST/PROD)."""

from __future__ import annotations

from app.config import Settings
from app.services.email_routing import route_recipients


def make_settings(mode: str = "test", **overrides) -> Settings:
    base = {
        "mail_mode": mode,
        "mail_recipient_override": "tiffanydellmann@hessautomobile.com",
        "mail_comptable": "axelsaphir@hessautomobile.com",
        "smtp_password": "dummy",
    }
    base.update(overrides)
    return Settings(**base)


class TestRouteRecipientsTestMode:
    def test_mode_test_redirige_to_vers_override(self):
        settings = make_settings(mode="test")
        r = route_recipients(
            to_prod="vendeur@concession.fr",
            cc_prod=["axelsaphir@hessautomobile.com"],
            settings=settings,
        )
        assert r.to == "tiffanydellmann@hessautomobile.com"

    def test_mode_test_vide_les_cc(self):
        settings = make_settings(mode="test")
        r = route_recipients(
            to_prod="vendeur@concession.fr",
            cc_prod=["axelsaphir@hessautomobile.com", "autre@truc.fr"],
            settings=settings,
        )
        assert r.cc == []

    def test_mode_test_ajoute_prefix_sujet(self):
        settings = make_settings(mode="test")
        r = route_recipients(to_prod="x@y.fr", settings=settings)
        assert r.subject_prefix == "[TEST] "

    def test_mode_test_garde_la_trace_des_destinataires_prod(self):
        settings = make_settings(mode="test")
        r = route_recipients(
            to_prod="vendeur@concession.fr",
            cc_prod=["axelsaphir@hessautomobile.com"],
            settings=settings,
        )
        assert r.original_recipients == {
            "to": ["vendeur@concession.fr"],
            "cc": ["axelsaphir@hessautomobile.com"],
        }


class TestRouteRecipientsProdMode:
    def test_mode_prod_envoie_au_vendeur(self):
        settings = make_settings(mode="prod")
        r = route_recipients(
            to_prod="vendeur@concession.fr",
            cc_prod=["axelsaphir@hessautomobile.com"],
            settings=settings,
        )
        assert r.to == "vendeur@concession.fr"

    def test_mode_prod_conserve_les_cc(self):
        settings = make_settings(mode="prod")
        r = route_recipients(
            to_prod="x@y.fr",
            cc_prod=["a@b.fr", "c@d.fr"],
            settings=settings,
        )
        assert r.cc == ["a@b.fr", "c@d.fr"]

    def test_mode_prod_pas_de_prefix_sujet(self):
        settings = make_settings(mode="prod")
        r = route_recipients(to_prod="x@y.fr", settings=settings)
        assert r.subject_prefix == ""

    def test_mode_prod_pas_de_trace_originale(self):
        settings = make_settings(mode="prod")
        r = route_recipients(to_prod="x@y.fr", cc_prod=["z@w.fr"], settings=settings)
        assert r.original_recipients is None

    def test_mode_prod_cc_vide_si_non_fourni(self):
        settings = make_settings(mode="prod")
        r = route_recipients(to_prod="x@y.fr", settings=settings)
        assert r.cc == []
