from types import SimpleNamespace

from app.services import vector_store_service as vector_store_module
from fastapi.testclient import TestClient


class _FakeCollection:
    def __init__(self, count: int) -> None:
        self._count = count

    def count(self) -> int:
        return self._count


class _FakeEmbeddingService:
    """Only the names and the active backend matter for index_status."""

    def __init__(self, active: str, primary: str, fallback: str) -> None:
        self.index_name = active
        self.primary = SimpleNamespace(index_name=primary)
        self.fallback = SimpleNamespace(index_name=fallback)


def _service_with_counts(monkeypatch, counts: dict[str, int], active: str):
    service = object.__new__(vector_store_module.VectorStoreService)
    monkeypatch.setattr(
        vector_store_module,
        "embedding_service",
        _FakeEmbeddingService(
            active,
            primary="dashscope_text_embedding_v3",
            fallback="hashing_v1",
        ),
    )
    monkeypatch.setattr(
        service, "_collection_for", lambda name: _FakeCollection(counts.get(name, 0))
    )
    return service


def test_index_status_is_clean_when_only_active_collection_holds_chunks(monkeypatch) -> None:
    service = _service_with_counts(
        monkeypatch,
        {"dashscope_text_embedding_v3": 12, "hashing_v1": 0},
        active="dashscope_text_embedding_v3",
    )

    status = service.index_status()

    assert status["index_stale"] is False
    assert status["stale_chunks"] == 0
    assert status["stale_collections"] == []
    assert status["active_chunks"] == 12
    assert status["active_collection"] == "knowflow_chunks_dashscope_text_embedding_v3"


def test_index_status_flags_chunks_left_in_the_inactive_collection(monkeypatch) -> None:
    # Degraded-period uploads landed in the hashing collection; the semantic
    # provider is active again, so those chunks are invisible to vector search.
    service = _service_with_counts(
        monkeypatch,
        {"dashscope_text_embedding_v3": 40, "hashing_v1": 7},
        active="dashscope_text_embedding_v3",
    )

    status = service.index_status()

    assert status["index_stale"] is True
    assert status["stale_chunks"] == 7
    assert status["stale_collections"] == [
        {"index_name": "hashing_v1", "collection": "knowflow_chunks", "chunks": 7}
    ]
    assert status["active_chunks"] == 40


def test_index_status_flags_the_reverse_split(monkeypatch) -> None:
    # Primary is down: hashing is active, semantic vectors from the healthy
    # period are the stale side.
    service = _service_with_counts(
        monkeypatch, {"dashscope_text_embedding_v3": 3, "hashing_v1": 0}, active="hashing_v1"
    )

    status = service.index_status()

    assert status["index_stale"] is True
    assert status["stale_collections"][0]["collection"] == (
        "knowflow_chunks_dashscope_text_embedding_v3"
    )
    assert status["active_collection"] == "knowflow_chunks"


def test_provider_status_exposes_vector_index_breakdown(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        vector_store_module.vector_store_service,
        "index_status",
        lambda: {
            "active_index_name": "dashscope_text_embedding_v3",
            "active_collection": "knowflow_chunks_dashscope_text_embedding_v3",
            "active_chunks": 40,
            "stale_collections": [
                {"index_name": "hashing_v1", "collection": "knowflow_chunks", "chunks": 7}
            ],
            "stale_chunks": 7,
            "index_stale": True,
        },
    )

    payload = client.get("/api/admin/providers").json()

    assert payload["vector_index"]["index_stale"] is True
    assert payload["vector_index"]["stale_chunks"] == 7
    assert payload["vector_index"]["active_chunks"] == 40
    assert payload["vector_index"]["stale_collections"][0]["chunks"] == 7


def test_health_exposes_stale_index_flat_fields(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        vector_store_module.vector_store_service,
        "index_status",
        lambda: {
            "active_index_name": "hashing_v1",
            "active_collection": "knowflow_chunks",
            "active_chunks": 5,
            "stale_collections": [
                {
                    "index_name": "dashscope_x",
                    "collection": "knowflow_chunks_dashscope_x",
                    "chunks": 2,
                }
            ],
            "stale_chunks": 2,
            "index_stale": True,
        },
    )

    payload = client.get("/api/health").json()

    assert payload["vector_index_stale"] is True
    assert payload["vector_index_stale_chunks"] == 2
    assert payload["vector_index_active_chunks"] == 5
    # Existing fields must stay intact.
    assert payload["embedding_mode"] in {"semantic", "hashing"}
    assert payload["vector_collection"]
