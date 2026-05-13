"""Tests unitaires du client Salesforce — tous les appels SF sont mockés."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.config import Settings
from app.services.salesforce_client import SalesforceClient, _record_to_payload


def make_settings() -> Settings:
    return Settings(
        salesforce_username="dummy@example.com",
        salesforce_password="dummy",
        salesforce_token="dummy",
        salesforce_domain="login",
        smtp_password="dummy",
    )


@pytest.fixture
def mock_sf():
    """Mock complet de l'objet simple_salesforce.Salesforce."""
    sf = MagicMock()
    # Sub-objet pour les CRUD : sf.Opportunity.update(...)
    sf.Opportunity = MagicMock()
    return sf


@pytest.fixture
def client(mock_sf):
    return SalesforceClient(settings=make_settings(), sf=mock_sf)


# ============================================================================
# _record_to_payload — parsing des records SF
# ============================================================================


class TestRecordToPayload:
    def test_record_complet_avec_owner(self):
        rec = {
            "Id": "006Tn00000ABC123IAF",
            "Name": "DUPONT Marie - 12-05-2026",
            "StageName": "4- Gagné",
            "CloseDate": "2026-05-12",
            "Concession_du_proprietaire__c": "Fiat Mulhouse",
            "Conformite_du_dossier__c": "- Aucun -",
            "Owner": {
                "Email": "jean.vendeur@fiatmulhouse.fr",
                "Name": "Jean Vendeur",
                "FirstName": "Jean",
                "LastName": "Vendeur",
            },
        }
        payload = _record_to_payload(rec, files=[])
        assert payload.opportunity_id == "006Tn00000ABC123IAF"
        assert payload.opportunity_name == "DUPONT Marie - 12-05-2026"
        assert payload.marque == "fiat"
        assert payload.concession == "Fiat Mulhouse"
        assert payload.vendeur_email == "jean.vendeur@fiatmulhouse.fr"
        assert payload.vendeur_nom == "Jean Vendeur"
        assert payload.stage_name == "4- Gagné"
        assert payload.statut_dossier == "- Aucun -"

    def test_record_sans_owner_pas_de_plantage(self):
        rec = {
            "Id": "006Tn00000ABC123IAF",
            "Name": "Sans owner",
            "Concession_du_proprietaire__c": "Renault Mulhouse",
            "Owner": None,
        }
        payload = _record_to_payload(rec, files=[])
        assert payload.vendeur_email is None
        assert payload.vendeur_nom is None
        assert payload.marque == "renault"

    def test_concession_vide_marque_inconnu(self):
        rec = {
            "Id": "006Tn00000XYZIAF",
            "Name": "Concession vide",
            "Concession_du_proprietaire__c": "",
            "Owner": {},
        }
        payload = _record_to_payload(rec, files=[])
        assert payload.concession == "inconnu"
        assert payload.marque == "inconnu"

    def test_marque_extraite_premier_mot(self):
        rec = {
            "Id": "006Tn00000XYZIAF",
            "Name": "x",
            "Concession_du_proprietaire__c": "Renault Strasbourg Hautepierre",
            "Owner": {},
        }
        payload = _record_to_payload(rec, files=[])
        assert payload.marque == "renault"


# ============================================================================
# Méthodes du client
# ============================================================================


class TestGetOpportunity:
    def test_opp_trouvee(self, client, mock_sf):
        mock_sf.query.side_effect = [
            # Premier appel : opp detail
            {
                "records": [
                    {
                        "Id": "006Tn0001",
                        "Name": "Test - 01-01-2026",
                        "Concession_du_proprietaire__c": "Fiat Mulhouse",
                        "Conformite_du_dossier__c": "- Aucun -",
                        "StageName": "4- Gagné",
                        "Owner": {"Email": "v@x.fr", "Name": "Vendeur X"},
                    }
                ]
            },
            # Deuxième appel : get_files
            {"records": []},
        ]
        payload = client.get_opportunity("006Tn0001")
        assert payload is not None
        assert payload.opportunity_id == "006Tn0001"
        assert payload.marque == "fiat"
        assert payload.files == []

    def test_opp_non_trouvee(self, client, mock_sf):
        mock_sf.query.return_value = {"records": []}
        assert client.get_opportunity("006Tn_inexistant") is None


class TestListATraiter:
    def test_pas_de_resultat(self, client, mock_sf):
        mock_sf.query.return_value = {"records": []}
        result = client.list_a_traiter(limit=20)
        assert result == []

    def test_avec_resultats(self, client, mock_sf):
        # 1er query = opps, ensuite 1 query par opp pour les fichiers
        mock_sf.query.side_effect = [
            {
                "records": [
                    {
                        "Id": "006Tn001",
                        "Name": "A",
                        "Concession_du_proprietaire__c": "Fiat Mulhouse",
                        "Owner": {"Email": "a@b.fr", "Name": "A B"},
                    },
                    {
                        "Id": "006Tn002",
                        "Name": "B",
                        "Concession_du_proprietaire__c": "Renault Colmar",
                        "Owner": {"Email": "c@d.fr", "Name": "C D"},
                    },
                ]
            },
            {"records": []},  # files pour Tn001
            {"records": []},  # files pour Tn002
        ]
        result = client.list_a_traiter(limit=20)
        assert len(result) == 2
        assert {p.marque for p in result} == {"fiat", "renault"}


class TestGetFiles:
    def test_files_renvoies_dans_l_ordre(self, client, mock_sf):
        mock_sf.query.return_value = {
            "records": [
                {
                    "Id": "f1",
                    "Name": "BDC.pdf",
                    "CreatedDate": "2026-05-01T10:00:00Z",
                    "NEILON__File_Presigned_URL__c": "https://s3/bdc",
                },
                {
                    "Id": "f2",
                    "Name": "CNI.pdf",
                    "CreatedDate": "2026-04-30T10:00:00Z",
                    "NEILON__File_Presigned_URL__c": "https://s3/cni",
                },
            ]
        }
        files = client.get_files("006Tn001")
        assert len(files) == 2
        assert files[0].name == "BDC.pdf"
        assert files[1].name == "CNI.pdf"

    def test_url_absente_renvoie_string_vide(self, client, mock_sf):
        mock_sf.query.return_value = {
            "records": [
                {"Id": "f1", "Name": "x.pdf", "NEILON__File_Presigned_URL__c": None}
            ]
        }
        files = client.get_files("006Tn001")
        assert files[0].url == ""


class TestUpdateMethods:
    def test_update_conformite_appelle_bonne_valeur(self, client, mock_sf):
        client.update_conformite("006Tn001", "Bon pour livraison")
        mock_sf.Opportunity.update.assert_called_once_with(
            "006Tn001", {"Conformite_du_dossier__c": "Bon pour livraison"}
        )

    def test_update_conformite_client_ineligible(self, client, mock_sf):
        client.update_conformite("006Tn001", "Client inéligible")
        mock_sf.Opportunity.update.assert_called_once_with(
            "006Tn001", {"Conformite_du_dossier__c": "Client inéligible"}
        )

    def test_update_stage(self, client, mock_sf):
        client.update_stage("006Tn001", "5- Perdu")
        mock_sf.Opportunity.update.assert_called_once_with(
            "006Tn001", {"StageName": "5- Perdu"}
        )

    def test_mark_dossier_verifier_true(self, client, mock_sf):
        client.mark_dossier_verifier("006Tn001", True)
        mock_sf.Opportunity.update.assert_called_once_with(
            "006Tn001", {"Tech_Dossier_verifier__c": True}
        )

    def test_mark_dossier_verifier_false_force_re_analyse(self, client, mock_sf):
        """Cas du dashboard : Axel force une ré-analyse en décochant le flag."""
        client.mark_dossier_verifier("006Tn001", False)
        mock_sf.Opportunity.update.assert_called_once_with(
            "006Tn001", {"Tech_Dossier_verifier__c": False}
        )


# ============================================================================
# Configuration / init
# ============================================================================


class TestClientInit:
    def test_credentials_manquants_leve_erreur(self):
        bad_settings = Settings(
            salesforce_username="",
            salesforce_password="",
            salesforce_token="",
            smtp_password="dummy",
        )
        with pytest.raises(ValueError, match="Credentials Salesforce"):
            SalesforceClient(settings=bad_settings)

    def test_avec_sf_inject_pas_de_connexion_reelle(self, mock_sf):
        """Si on injecte un mock sf, pas de check credentials (utilisé en tests)."""
        # Pas de raise même avec credentials vides
        settings = Settings(smtp_password="dummy")
        client = SalesforceClient(settings=settings, sf=mock_sf)
        assert client is not None
