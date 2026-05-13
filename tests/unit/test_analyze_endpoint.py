"""Tests d'intégration de l'endpoint POST /analyze."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_gemini_client,
    get_salesforce_client,
    get_supabase_client,
)
from app.config import Settings, get_settings
from app.main import app


@pytest.fixture(autouse=True)
def override_settings():
    """Force des settings de test pour tous les tests de ce module."""

    def _settings():
        return Settings(
            api_token="test-token",
            mail_mode="test",
            mail_recipient_override="tiffanydellmann@hessautomobile.com",
            mail_comptable="axelsaphir@hessautomobile.com",
            smtp_password="dummy",
        )

    app.dependency_overrides[get_settings] = _settings
    get_settings.cache_clear()
    yield
    app.dependency_overrides.clear()
    get_settings.cache_clear()


@pytest.fixture
def mock_sf():
    return MagicMock()


@pytest.fixture
def mock_sb():
    sb = MagicMock()
    sb.create_analyse.return_value = {"id": "analyse-uuid-test"}
    return sb


@pytest.fixture
def mock_gemini():
    return MagicMock()


@pytest.fixture
def client(mock_sf, mock_sb, mock_gemini):
    """Client TestClient avec tous les services mockés."""
    app.dependency_overrides[get_salesforce_client] = lambda: mock_sf
    app.dependency_overrides[get_supabase_client] = lambda: mock_sb
    app.dependency_overrides[get_gemini_client] = lambda: mock_gemini
    # On force aussi le settings via env hack pour verify_api_token
    with patch("app.api.dependencies.get_settings") as gs:
        gs.return_value = Settings(api_token="test-token", smtp_password="dummy")
        yield TestClient(app)


VALID_PAYLOAD = {
    "opportunity_id": "006Tn00000ABC123IAF",
    "opportunity_name": "DUPONT Marie - 12-05-2026",
    "marque": "fiat",
    "concession": "Fiat Mulhouse",
    "files": [],
    "vendeur_email": "vendeur@fiatmulhouse.fr",
    "vendeur_nom": "Jean Vendeur",
}


# ============================================================================
# Auth
# ============================================================================


class TestAuth:
    def test_pas_de_token_refuse(self, client):
        response = client.post("/analyze", json=VALID_PAYLOAD)
        assert response.status_code == 401

    def test_token_invalide_refuse(self, client):
        response = client.post(
            "/analyze",
            json=VALID_PAYLOAD,
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert response.status_code == 403

    def test_token_valide_accepte(self, client, mock_sb):
        response = client.post(
            "/analyze",
            json=VALID_PAYLOAD,
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 200


# ============================================================================
# Validation du payload
# ============================================================================


class TestPayloadValidation:
    def test_opportunity_id_manquant_refuse(self, client):
        bad = VALID_PAYLOAD.copy()
        del bad["opportunity_id"]
        response = client.post(
            "/analyze",
            json=bad,
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 422

    def test_email_vendeur_invalide_refuse(self, client):
        bad = VALID_PAYLOAD.copy()
        bad["vendeur_email"] = "pas-un-email"
        response = client.post(
            "/analyze",
            json=bad,
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 422


# ============================================================================
# Flux refus d'office (concession Siège)
# ============================================================================


class TestRefusOffice:
    def test_siege_declenche_refus_office(self, client, mock_sf, mock_sb):
        payload = VALID_PAYLOAD | {"concession": "Siège", "marque": "inconnu"}
        with patch("app.core.analyze.send_email") as mock_send:
            response = client.post(
                "/analyze",
                json=payload,
                headers={"Authorization": "Bearer test-token"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["verdict"]["statut"] == "refus_office"
        assert data["verdict"]["indice_confiance"] == 100
        assert data["mail_sent"] is True
        assert data["salesforce_updated"] is True
        # Update SF appelé avec "Client inéligible"
        mock_sf.update_conformite.assert_called_once_with(
            "006Tn00000ABC123IAF", "Client inéligible"
        )
        mock_sf.mark_dossier_verifier.assert_called_once_with(
            "006Tn00000ABC123IAF", True
        )
        # Mail envoyé
        mock_send.assert_called_once()
        # Analyse persistée
        mock_sb.create_analyse.assert_called_once()


# ============================================================================
# Flux normal (pas de refus d'office)
# ============================================================================


class TestFluxNormal:
    def test_dossier_normal_ne_touche_pas_sf(self, client, mock_sf, mock_sb):
        """Pour les verdicts conforme/non_conforme, l'API ne patche pas SF
        (c'est Axel qui valide depuis le dashboard, cf ADR-013)."""
        with patch("app.core.analyze.send_email") as mock_send:
            response = client.post(
                "/analyze",
                json=VALID_PAYLOAD,
                headers={"Authorization": "Bearer test-token"},
            )
        assert response.status_code == 200
        data = response.json()
        # En Phase 3 skeleton, dossier vide → non_conforme (documents manquants)
        assert data["verdict"]["statut"] == "non_conforme"
        assert data["salesforce_updated"] is False
        assert data["mail_sent"] is False
        # SF NON touchée
        mock_sf.update_conformite.assert_not_called()
        mock_sf.mark_dossier_verifier.assert_not_called()
        # Pas de mail
        mock_send.assert_not_called()
        # Analyse persistée
        mock_sb.create_analyse.assert_called_once()

    def test_response_contient_analyse_id(self, client):
        response = client.post(
            "/analyze",
            json=VALID_PAYLOAD,
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 200
        assert response.json()["analyse_id"] == "analyse-uuid-test"

    def test_response_contient_duree_ms(self, client):
        response = client.post(
            "/analyze",
            json=VALID_PAYLOAD,
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.json()["duree_ms"] >= 0
