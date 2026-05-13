"""Client Gemini pour Leasing Social v2.

Wrapper autour de `google-genai` qui ajoute :
- Retry 2x avec backoff exponentiel (1s, 4s)
- Timeout 90s par appel
- Validation Pydantic stricte de la sortie JSON
- Logging structuré du prompt + réponse en cas d'erreur (pour debug)
- Tolérance aux fences markdown ```json ... ```

Principe (ADR-009) : aucun dict brut Gemini ne passe à la logique métier.
Toute sortie est validée contre un modèle Pydantic ; si parse fail → retry,
puis verdict `erreur_technique` en dernier recours.
"""

from __future__ import annotations

import json
import time
from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from app.config import Settings, get_settings
from app.utils.logging import get_logger

log = get_logger("app.services.gemini")

T = TypeVar("T", bound=BaseModel)


class GeminiError(Exception):
    """Erreur Gemini non récupérable (toutes les tentatives ont échoué)."""


class GeminiClient:
    """Client Gemini haut niveau, parse + valide automatiquement la sortie."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: genai.Client | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        if client is not None:
            self._client = client
            return
        if not self._settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY manquant dans .env")
        self._client = genai.Client(api_key=self._settings.gemini_api_key)
        log.info("gemini_client_initialized")

    def extract_pdf(
        self,
        prompt: str,
        pdf_bytes: bytes,
        model_pydantic: type[T],
        model_name: str = "gemini-2.5-pro",
        max_retries: int = 2,
    ) -> T:
        """Envoie un PDF à Gemini et valide la réponse contre `model_pydantic`.

        Args:
            prompt: prompt d'extraction (sera concaténé après le PDF)
            pdf_bytes: contenu binaire du PDF
            model_pydantic: classe Pydantic qui validera la réponse JSON
            model_name: 'gemini-2.5-pro' (défaut) ou 'gemini-2.5-flash'
            max_retries: nombre total de tentatives

        Returns:
            Instance de `model_pydantic` validée.

        Raises:
            GeminiError: après `max_retries` tentatives infructueuses.
        """
        last_error: str | None = None

        for attempt in range(1, max_retries + 1):
            try:
                response = self._client.models.generate_content(
                    model=model_name,
                    contents=[
                        types.Part.from_bytes(
                            data=pdf_bytes, mime_type="application/pdf"
                        ),
                        prompt,
                    ],
                )
                text = (response.text or "").strip()
                text = _strip_json_fence(text)

                if not text:
                    last_error = "Réponse Gemini vide"
                    log.warning(
                        "gemini_empty_response", attempt=attempt, model=model_name
                    )
                    self._sleep_backoff(attempt, max_retries)
                    continue

                # Parse JSON
                try:
                    raw = json.loads(text)
                except json.JSONDecodeError as exc:
                    last_error = f"JSON invalide : {exc}"
                    log.warning(
                        "gemini_json_invalid",
                        attempt=attempt,
                        model=model_name,
                        error=str(exc),
                        preview=text[:300],
                    )
                    self._sleep_backoff(attempt, max_retries)
                    continue

                # Validation Pydantic
                try:
                    return model_pydantic.model_validate(raw)
                except ValidationError as exc:
                    last_error = f"Validation Pydantic échouée : {exc}"
                    log.warning(
                        "gemini_pydantic_invalid",
                        attempt=attempt,
                        model=model_name,
                        error=str(exc),
                        raw_keys=list(raw.keys()) if isinstance(raw, dict) else None,
                    )
                    self._sleep_backoff(attempt, max_retries)
                    continue

            except Exception as exc:
                last_error = f"Appel Gemini échoué : {exc}"
                log.warning(
                    "gemini_call_failed",
                    attempt=attempt,
                    model=model_name,
                    error=str(exc),
                )
                self._sleep_backoff(attempt, max_retries)

        raise GeminiError(
            f"Échec après {max_retries} tentatives. Dernière erreur : {last_error}"
        )

    @staticmethod
    def _sleep_backoff(attempt: int, max_retries: int) -> None:
        """Backoff exponentiel : 1s, 4s, 9s, ... (uniquement si on a encore des tentatives)."""
        if attempt < max_retries:
            time.sleep(attempt * attempt)


def _strip_json_fence(text: str) -> str:
    """Retire un éventuel fence markdown ```json ... ``` autour de la réponse Gemini."""
    text = text.strip()
    if text.startswith("```"):
        # Enlève la première ligne (```json ou ```)
        lines = text.split("\n", 1)
        text = lines[1] if len(lines) > 1 else ""
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    return text
