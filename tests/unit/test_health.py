"""Tests Phase 0 : healthcheck."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok() -> None:
    """L'endpoint /health doit répondre 200 OK avec status=ok."""
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "env" in payload
    assert "version" in payload
