"""Tests for foundational API endpoints."""

from starlette.testclient import TestClient


def test_health_endpoint_returns_success(client: TestClient) -> None:
    """Verify that GET /health returns HTTP 200 with required health metadata."""
    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "HealthTrack Follow-Up System"
    assert data["version"] == "0.1.0"
    assert data["environment"] == "development"


def test_health_endpoint_rejects_post_method(client: TestClient) -> None:
    """Verify that POST /health is rejected with 405 Method Not Allowed."""
    response = client.post("/health", json={})
    assert response.status_code == 405


def test_nonexistent_endpoint_returns_404(client: TestClient) -> None:
    """Verify 404 response for unhandled paths."""
    response = client.get("/nonexistent-endpoint")
    assert response.status_code == 404


def test_create_app_without_lifespan_does_not_create_database_file() -> None:
    """Verify that constructing the FastAPI app does not trigger table creation or disk side-effects."""
    from pathlib import Path
    from app.main import create_app

    app_instance = create_app()
    assert app_instance.title == "HealthTrack Follow-Up System"
    assert not Path("healthtrack.db").exists()
