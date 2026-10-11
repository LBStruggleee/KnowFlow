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


def test_typed_settings_normalizes_hand_edited_value(db_session: Session) -> None:
    from app.models.system_setting import SystemSetting

    db_session.add(
        SystemSetting(key="retrieval_channels", value="VECTOR", description="hand-edited")
    )
    db_session.commit()

    assert typed_settings(db_session)["retrieval_channels"] == "vector"


def test_patch_unknown_setting_key_returns_422(client: TestClient) -> None:
    response = client.patch("/api/admin/settings", json={"unknown_key": "x"})

    assert response.status_code == 422


def test_typed_settings_falls_back_to_defaults_for_corrupted_values(db_session: Session) -> None:
    from app.models.system_setting import SystemSetting

    db_session.add(SystemSetting(key="top_k", value="abc", description="corrupted"))
    db_session.add(SystemSetting(key="score_threshold", value="oops", description="corrupted"))
    db_session.add(SystemSetting(key="temperature", value="hot", description="corrupted"))
    db_session.commit()

    values = typed_settings(db_session)

    assert values["top_k"] == 5
    assert values["score_threshold"] == 0.0
    assert values["temperature"] == 0.2
