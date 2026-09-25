from app.services.settings_service import (
    get_settings,
    normalize_retrieval_channels,
    typed_settings,
)
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_normalize_retrieval_channels() -> None:
    assert normalize_retrieval_channels("lexical") == "lexical"
    assert normalize_retrieval_channels("VECTOR") == "vector"
    assert normalize_retrieval_channels("bogus") == "hybrid"
    assert normalize_retrieval_channels(None) == "hybrid"
    assert normalize_retrieval_channels("") == "hybrid"


def test_default_settings_include_hybrid_channels(db_session: Session) -> None:
    assert get_settings(db_session)["retrieval_channels"] == "hybrid"
    assert typed_settings(db_session)["retrieval_channels"] == "hybrid"


def test_patch_channels_roundtrip(client: TestClient) -> None:
    response = client.patch("/api/admin/settings", json={"retrieval_channels": "lexical"})

    assert response.status_code == 200
    assert response.json()["retrieval_channels"] == "lexical"
    assert client.get("/api/admin/settings").json()["retrieval_channels"] == "lexical"


def test_patch_invalid_channels_normalizes_to_hybrid(client: TestClient) -> None:
    response = client.patch("/api/admin/settings", json={"retrieval_channels": "bogus"})

    assert response.status_code == 200
    assert response.json()["retrieval_channels"] == "hybrid"
