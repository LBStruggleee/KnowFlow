from app.services.embedding_service import (
    EMBEDDING_DEGRADED_NOTICE,
    HASHING_INDEX_NAME,
    HashingEmbeddingService,
    ResilientEmbeddingService,
    embedding_status,
)
from fastapi.testclient import TestClient


class _FakeSemanticProvider:
    """Stand-in for DashScope: only the index_name matters for mode reporting."""

    index_name = "dashscope_text_embedding_v3"

    def embed_text(self, text: str) -> list[float]:
        return [1.0, 0.0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


def test_hashing_only_service_reports_non_semantic_mode() -> None:
    service = ResilientEmbeddingService(HashingEmbeddingService())

    assert service.mode == "hashing"
    assert service.degraded is True
    assert service.index_name == HASHING_INDEX_NAME


def test_semantic_service_switches_to_hashing_after_fallback() -> None:
    service = ResilientEmbeddingService(_FakeSemanticProvider())

    assert service.mode == "semantic"
    assert service.degraded is False

    service.use_fallback()

    assert service.mode == "hashing"
    assert service.degraded is True


def test_embedding_status_describes_active_backend(monkeypatch) -> None:
    service = ResilientEmbeddingService(_FakeSemanticProvider())
    monkeypatch.setattr("app.services.embedding_service.embedding_service", service)

    status = embedding_status()
    assert status["embedding_mode"] == "semantic"
    assert status["embedding_degraded"] is False
    assert status["embedding_notice"] == ""

    service.use_fallback()
    degraded = embedding_status()
    assert degraded["embedding_mode"] == "hashing"
    assert degraded["embedding_degraded"] is True
    assert degraded["embedding_notice"] == EMBEDDING_DEGRADED_NOTICE


def test_health_endpoint_exposes_embedding_mode(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["embedding_mode"] in {"semantic", "hashing"}
    assert payload["embedding_degraded"] is (payload["embedding_mode"] == "hashing")
    # The legacy field stays for existing clients.
    assert payload["embedding_provider"]


def test_provider_status_exposes_embedding_mode(client: TestClient) -> None:
    response = client.get("/api/admin/providers")

    assert response.status_code == 200
    payload = response.json()
    assert payload["embedding_mode"] in {"semantic", "hashing"}
    assert payload["embedding_degraded"] is (payload["embedding_mode"] == "hashing")
    if payload["embedding_degraded"]:
        assert payload["embedding_notice"]
