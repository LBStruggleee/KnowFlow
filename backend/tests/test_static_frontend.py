"""Same-origin SPA hosting (evaluation R-04).

When ``frontend/dist`` exists the API process mounts it as the SPA origin, so
API and UI share one origin without CORS. Registered last, API routes keep
precedence over the static fallback.
"""

from pathlib import Path

import pytest
from app.main import create_app
from fastapi.testclient import TestClient

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@pytest.mark.skipif(not FRONTEND_DIST.is_dir(), reason="frontend/dist has not been built")
def test_root_serves_spa_index_when_dist_exists(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_root_returns_api_welcome_without_dist(monkeypatch, tmp_path, db_session):
    monkeypatch.setattr("app.main.BASE_DIR", tmp_path)
    test_engine = db_session.get_bind()
    monkeypatch.setattr("app.main.engine", test_engine)

    from sqlalchemy.orm import sessionmaker

    monkeypatch.setattr("app.main.SessionLocal", sessionmaker(bind=test_engine))

    application = create_app()
    with TestClient(application) as test_client:
        response = test_client.get("/")

    assert response.status_code == 200
    assert response.json()["health"] == "/api/health"


def test_api_routes_take_precedence_over_static_mount(client: TestClient):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
