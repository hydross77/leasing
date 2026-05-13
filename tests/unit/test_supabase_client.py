"""Tests unitaires du client Supabase — appels mockés."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.config import Settings
from app.models.anomalie import Anomalie
from app.models.verdict import Verdict
from app.services.supabase_client import SupabaseClient


def make_settings() -> Settings:
    return Settings(
        supabase_url="https://example.supabase.co",
        supabase_key="dummy_key",
        smtp_password="dummy",
    )


@pytest.fixture
def mock_supabase():
    """Mock du client supabase-py — la chaîne fluent .table().select()...execute()."""
    return MagicMock()


@pytest.fixture
def client(mock_supabase):
    return SupabaseClient(settings=make_settings(), client=mock_supabase)


def _setup_query_chain(mock_supabase, return_data: list[dict]):
    """Helper qui configure la chaîne fluent pour retourner `return_data`.

    La chaîne attendue : table().select().eq().eq().eq().eq().limit().execute()
                       ou table().select().eq().is_().eq().eq().limit().execute()
                       etc.
    Comme chaque méthode retourne le même MagicMock dans la pratique de supabase-py,
    on mock pour que toute la chaîne retourne un objet avec `.data = return_data`.
    """
    chain = MagicMock()
    chain.data = return_data
    # Toute méthode appelée sur le chain retourne le chain lui-même, sauf execute()
    chain.execute.return_value = chain
    chain.select.return_value = chain
    chain.insert.return_value = chain
    chain.update.return_value = chain
    chain.eq.return_value = chain
    chain.is_.return_value = chain
    chain.in_.return_value = chain
    chain.limit.return_value = chain
    chain.order.return_value = chain
    mock_supabase.table.return_value = chain
    return chain


# ============================================================================
# PROMPTS — cascade lookup
# ============================================================================


class TestGetPromptActif:
    def test_match_niveau_concession(self, client, mock_supabase):
        """Cas 1 : surcharge concession trouvée."""
        prompt = {
            "id": "uuid1",
            "marque": "fiat",
            "concession": "Fiat Mulhouse",
            "type_prompt": "extraction_bdc",
            "contenu": "prompt v3 mulhouse",
            "actif": True,
        }
        _setup_query_chain(mock_supabase, [prompt])
        result = client.get_prompt_actif("fiat", "Fiat Mulhouse", "extraction_bdc")
        assert result == prompt

    def test_fallback_niveau_marque(self, client, mock_supabase):
        """Cas 2 : pas de surcharge concession, on tombe sur (marque, NULL)."""
        prompt_marque = {
            "id": "uuid2",
            "marque": "fiat",
            "concession": None,
            "type_prompt": "extraction_bdc",
            "contenu": "prompt fiat default",
            "actif": True,
        }
        # 1er appel (surcharge concession) : vide
        # 2ème appel (fallback marque) : trouvé
        chains = [MagicMock(data=[]), MagicMock(data=[prompt_marque])]
        for c in chains:
            c.execute.return_value = c
            c.select.return_value = c
            c.eq.return_value = c
            c.is_.return_value = c
            c.limit.return_value = c
        mock_supabase.table.side_effect = chains
        result = client.get_prompt_actif("fiat", "Fiat Bischheim", "extraction_bdc")
        assert result == prompt_marque

    def test_fallback_global_default(self, client, mock_supabase):
        """Cas 3 : aucune surcharge, on tombe sur ('default', NULL)."""
        prompt_default = {
            "id": "uuid3",
            "marque": "default",
            "concession": None,
            "type_prompt": "extraction_bdc",
            "contenu": "prompt fallback global",
            "actif": True,
        }
        chains = [
            MagicMock(data=[]),  # surcharge concession
            MagicMock(data=[]),  # fallback marque
            MagicMock(data=[prompt_default]),  # fallback default
        ]
        for c in chains:
            c.execute.return_value = c
            c.select.return_value = c
            c.eq.return_value = c
            c.is_.return_value = c
            c.limit.return_value = c
        mock_supabase.table.side_effect = chains
        result = client.get_prompt_actif(
            "marque_inconnue", "Concession Inconnue", "extraction_bdc"
        )
        assert result == prompt_default

    def test_aucun_prompt_trouve(self, client, mock_supabase):
        """Cas anormal : même le default est absent → None."""
        chains = [MagicMock(data=[]) for _ in range(3)]
        for c in chains:
            c.execute.return_value = c
            c.select.return_value = c
            c.eq.return_value = c
            c.is_.return_value = c
            c.limit.return_value = c
        mock_supabase.table.side_effect = chains
        result = client.get_prompt_actif("fiat", None, "extraction_bdc")
        assert result is None

    def test_concession_none_skip_etape_1(self, client, mock_supabase):
        """Si concession=None, on passe directement au fallback marque (étape 2)."""
        prompt_marque = {
            "id": "uuid2",
            "marque": "fiat",
            "concession": None,
            "type_prompt": "extraction_bdc",
            "actif": True,
        }
        chains = [MagicMock(data=[prompt_marque])]
        for c in chains:
            c.execute.return_value = c
            c.select.return_value = c
            c.eq.return_value = c
            c.is_.return_value = c
            c.limit.return_value = c
        mock_supabase.table.side_effect = chains
        result = client.get_prompt_actif("fiat", None, "extraction_bdc")
        assert result == prompt_marque


# ============================================================================
# ANALYSES
# ============================================================================


class TestCreateAnalyse:
    def test_create_avec_verdict_conforme(self, client, mock_supabase):
        verdict = Verdict(statut="conforme", indice_confiance=95, anomalies=[])
        chain = _setup_query_chain(
            mock_supabase, [{"id": "analyse-uuid-1", "statut": "conforme"}]
        )
        result = client.create_analyse(
            opportunity_id="006Tn0001",
            opportunity_name="Test - 01-01-2026",
            marque="fiat",
            concession="Fiat Mulhouse",
            verdict=verdict,
            duree_ms=2500,
        )
        assert result["id"] == "analyse-uuid-1"
        # Vérifie que insert a été appelé avec les bons champs
        chain.insert.assert_called_once()
        inserted_row = chain.insert.call_args[0][0]
        assert inserted_row["statut"] == "conforme"
        assert inserted_row["indice_confiance"] == 95
        assert inserted_row["duree_ms"] == 2500
        assert inserted_row["anomalies"] == []

    def test_create_avec_anomalies_serialise_pydantic(self, client, mock_supabase):
        anomalie = Anomalie(
            code="A005_aide_27_ttc",
            libelle="Aide trop élevée",
            severite="bloquante",
        )
        verdict = Verdict(
            statut="non_conforme",
            indice_confiance=40,
            anomalies=[anomalie],
            documents_manquants=["photos_vehicule"],
        )
        chain = _setup_query_chain(mock_supabase, [{"id": "u2"}])
        client.create_analyse(
            opportunity_id="006Tn0002",
            opportunity_name="X",
            marque="renault",
            concession="Renault Mulhouse",
            verdict=verdict,
        )
        inserted_row = chain.insert.call_args[0][0]
        assert isinstance(inserted_row["anomalies"], list)
        assert inserted_row["anomalies"][0]["code"] == "A005_aide_27_ttc"
        assert inserted_row["anomalies"][0]["libelle"] == "Aide trop élevée"
        assert inserted_row["documents_manquants"] == ["photos_vehicule"]


# ============================================================================
# VALIDATIONS
# ============================================================================


class TestCreateValidation:
    def test_create_validation_conforme(self, client, mock_supabase):
        chain = _setup_query_chain(
            mock_supabase, [{"id": "validation-uuid-1", "statut": "validee_conforme"}]
        )
        result = client.create_validation(
            analyse_id="analyse-1",
            opportunity_id="006Tn0001",
            statut="validee_conforme",
            decision_comptable="confirme_ia",
            anomalies_finales=[],
            comptable_email="axelsaphir@hessautomobile.com",
        )
        assert result["id"] == "validation-uuid-1"
        inserted = chain.insert.call_args[0][0]
        assert inserted["statut"] == "validee_conforme"
        assert inserted["comptable_email"] == "axelsaphir@hessautomobile.com"
        assert inserted["anomalies_finales"] == []
        assert inserted["valide_le"] is not None

    def test_create_validation_inverse_avec_ajouts(self, client, mock_supabase):
        """Comptable inverse le verdict IA en ajoutant des anomalies non détectées."""
        chain = _setup_query_chain(mock_supabase, [{"id": "v1"}])
        client.create_validation(
            analyse_id="analyse-1",
            opportunity_id="006Tn0001",
            statut="validee_non_conforme",
            decision_comptable="inverse_ia",
            anomalies_finales=[{"code": "A_manuel", "libelle": "Détecté par humain"}],
            comptable_email="axelsaphir@hessautomobile.com",
            anomalies_ajoutees=[{"code": "A_manuel", "libelle": "Détecté par humain"}],
            anomalies_retirees=[],
            notes="L'IA a manqué une anomalie sur le contrat",
        )
        inserted = chain.insert.call_args[0][0]
        assert inserted["decision_comptable"] == "inverse_ia"
        assert len(inserted["anomalies_ajoutees"]) == 1
        assert inserted["notes"] == "L'IA a manqué une anomalie sur le contrat"


# ============================================================================
# CONCESSIONS
# ============================================================================


class TestConcessions:
    def test_concession_trouvee(self, client, mock_supabase):
        _setup_query_chain(
            mock_supabase, [{"email_conformite": "fiatmulhouseconformite@hessautomobile.com"}]
        )
        result = client.get_concession_email("Fiat Mulhouse")
        assert result == "fiatmulhouseconformite@hessautomobile.com"

    def test_concession_inconnue(self, client, mock_supabase):
        _setup_query_chain(mock_supabase, [])
        result = client.get_concession_email("Concession Fantôme")
        assert result is None


# ============================================================================
# Init
# ============================================================================


class TestClientInit:
    def test_credentials_manquants_leve_erreur(self):
        bad_settings = Settings(supabase_url="", supabase_key="", smtp_password="dummy")
        with pytest.raises(ValueError, match="Credentials Supabase"):
            SupabaseClient(settings=bad_settings)

    def test_injection_client_skip_creation(self, mock_supabase):
        """Si on injecte un client, on ne tente pas de créer une vraie connexion."""
        settings = Settings(smtp_password="dummy")
        client = SupabaseClient(settings=settings, client=mock_supabase)
        assert client.client is mock_supabase
