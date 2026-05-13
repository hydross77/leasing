"""Tests unitaires du client Gemini — appels mockés (jamais d'appel réel)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel

from app.config import Settings
from app.services.gemini_client import GeminiClient, GeminiError, _strip_json_fence


# Modèle Pydantic de test
class _FakeExtraction(BaseModel):
    type_document: str
    prix_ttc: float | None = None


def make_settings() -> Settings:
    return Settings(gemini_api_key="dummy_key", smtp_password="dummy")


@pytest.fixture
def mock_genai_client():
    """Mock du google.genai.Client."""
    c = MagicMock()
    c.models = MagicMock()
    return c


@pytest.fixture
def client(mock_genai_client):
    return GeminiClient(settings=make_settings(), client=mock_genai_client)


def _fake_response(text: str) -> MagicMock:
    """Helper qui construit une réponse Gemini factice."""
    r = MagicMock()
    r.text = text
    return r


# ============================================================================
# _strip_json_fence
# ============================================================================


class TestStripJsonFence:
    def test_pas_de_fence(self):
        assert _strip_json_fence('{"a": 1}') == '{"a": 1}'

    def test_fence_json(self):
        assert _strip_json_fence('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_fence_sans_lang(self):
        assert _strip_json_fence('```\n{"a": 1}\n```') == '{"a": 1}'

    def test_espaces_autour(self):
        assert _strip_json_fence('  ```json\n{"a": 1}\n```  ') == '{"a": 1}'

    def test_fence_sans_fin(self):
        """Cas tolérance : fence ouvrant sans fence fermant."""
        # On enlève au moins la première ligne ```
        result = _strip_json_fence('```json\n{"a": 1}')
        assert '"a": 1' in result


# ============================================================================
# extract_pdf — cas nominaux
# ============================================================================


class TestExtractPdfSucces:
    def test_reponse_json_pure(self, client, mock_genai_client):
        mock_genai_client.models.generate_content.return_value = _fake_response(
            '{"type_document": "BDC", "prix_ttc": 28800}'
        )
        result = client.extract_pdf(
            prompt="extract", pdf_bytes=b"%PDF...", model_pydantic=_FakeExtraction
        )
        assert isinstance(result, _FakeExtraction)
        assert result.type_document == "BDC"
        assert result.prix_ttc == 28800

    def test_reponse_avec_fence_markdown(self, client, mock_genai_client):
        mock_genai_client.models.generate_content.return_value = _fake_response(
            '```json\n{"type_document": "Contrat"}\n```'
        )
        result = client.extract_pdf(
            prompt="extract", pdf_bytes=b"x", model_pydantic=_FakeExtraction
        )
        assert result.type_document == "Contrat"

    def test_prix_ttc_optional_a_null(self, client, mock_genai_client):
        mock_genai_client.models.generate_content.return_value = _fake_response(
            '{"type_document": "CNI"}'
        )
        result = client.extract_pdf(
            prompt="x", pdf_bytes=b"x", model_pydantic=_FakeExtraction
        )
        assert result.prix_ttc is None


# ============================================================================
# extract_pdf — gestion d'erreurs et retry
# ============================================================================


class TestExtractPdfRetry:
    def test_retry_apres_json_invalide_puis_succes(self, client, mock_genai_client):
        """1ère tentative : JSON cassé. 2e tentative : OK."""
        mock_genai_client.models.generate_content.side_effect = [
            _fake_response("ceci n'est pas du json"),
            _fake_response('{"type_document": "BDC"}'),
        ]
        result = client.extract_pdf(
            prompt="x", pdf_bytes=b"x", model_pydantic=_FakeExtraction
        )
        assert result.type_document == "BDC"
        assert mock_genai_client.models.generate_content.call_count == 2

    def test_echec_apres_max_retries(self, client, mock_genai_client):
        mock_genai_client.models.generate_content.return_value = _fake_response(
            "toujours invalide"
        )
        with pytest.raises(GeminiError, match="2 tentatives"):
            client.extract_pdf(
                prompt="x",
                pdf_bytes=b"x",
                model_pydantic=_FakeExtraction,
                max_retries=2,
            )
        assert mock_genai_client.models.generate_content.call_count == 2

    def test_validation_pydantic_echoue_apres_retry(self, client, mock_genai_client):
        """JSON valide mais ne matche pas le schéma Pydantic."""
        mock_genai_client.models.generate_content.return_value = _fake_response(
            '{"wrong_field": "x"}'
        )
        with pytest.raises(GeminiError):
            client.extract_pdf(
                prompt="x",
                pdf_bytes=b"x",
                model_pydantic=_FakeExtraction,
                max_retries=2,
            )

    def test_exception_reseau_remonte_apres_max_retries(
        self, client, mock_genai_client
    ):
        mock_genai_client.models.generate_content.side_effect = RuntimeError(
            "Connection refused"
        )
        with pytest.raises(GeminiError, match="Connection refused"):
            client.extract_pdf(
                prompt="x",
                pdf_bytes=b"x",
                model_pydantic=_FakeExtraction,
                max_retries=2,
            )

    def test_reponse_vide_compte_comme_erreur(self, client, mock_genai_client):
        mock_genai_client.models.generate_content.return_value = _fake_response("")
        with pytest.raises(GeminiError, match="vide"):
            client.extract_pdf(
                prompt="x",
                pdf_bytes=b"x",
                model_pydantic=_FakeExtraction,
                max_retries=2,
            )


# ============================================================================
# Init
# ============================================================================


class TestClientInit:
    def test_api_key_manquante_leve_erreur(self):
        bad = Settings(gemini_api_key="", smtp_password="dummy")
        with pytest.raises(ValueError, match="GEMINI_API_KEY manquant"):
            GeminiClient(settings=bad)

    def test_injection_client_skip_validation(self, mock_genai_client):
        settings = Settings(smtp_password="dummy")
        client = GeminiClient(settings=settings, client=mock_genai_client)
        assert client is not None
