import pytest
from app.models.document_chunk import DocumentChunk
from app.services.embedding_service import embedding_service
from app.services.rag_service import _build_context
from app.services.vector_store_service import vector_store_service


class _FakeCollection:
    name = "fake"

    def __init__(self) -> None:
        self.upsert_kwargs: dict = {}
        self.query_result: dict = {
            "documents": [["正文"]],
            "metadatas": [
                [
                    {
                        "chunk_id": 5,
                        "document_id": 2,
                        "kb_id": 1,
                        "chunk_index": 0,
                        "section_path": "课程 / 第一章",
                    }
                ]
            ],
            "distances": [[0.2]],
        }

    def count(self) -> int:
        return 1

    def upsert(self, **kwargs) -> None:
        self.upsert_kwargs = kwargs

    def query(self, **kwargs):
        return self.query_result


def test_add_chunks_stores_section_path_metadata(monkeypatch) -> None:
    fake = _FakeCollection()
    monkeypatch.setattr(vector_store_service, "_collection_for", lambda _name: fake)
    monkeypatch.setattr(embedding_service, "embed_texts", lambda _docs: [[0.1, 0.2]])
    chunk = DocumentChunk(
        id=7, kb_id=1, document_id=2, chunk_index=0, content="正文", token_count=2
    )

    vector_store_service.add_chunks([chunk], {7: "课程 / 第一章"})

    assert fake.upsert_kwargs["metadatas"] == [
        {
            "chunk_id": 7,
            "document_id": 2,
            "kb_id": 1,
            "chunk_index": 0,
            "section_path": "课程 / 第一章",
        }
    ]


def test_add_chunks_defaults_section_path_to_empty(monkeypatch) -> None:
    fake = _FakeCollection()
    monkeypatch.setattr(vector_store_service, "_collection_for", lambda _name: fake)
    monkeypatch.setattr(embedding_service, "embed_texts", lambda _docs: [[0.1, 0.2]])
    chunk = DocumentChunk(
        id=8, kb_id=1, document_id=2, chunk_index=0, content="正文", token_count=2
    )

    vector_store_service.add_chunks([chunk])

    assert fake.upsert_kwargs["metadatas"][0]["section_path"] == ""


def test_search_returns_section_path_from_metadata(monkeypatch) -> None:
    fake = _FakeCollection()
    monkeypatch.setattr(vector_store_service, "_collection_for", lambda _name: fake)
    monkeypatch.setattr(embedding_service, "embed_text", lambda _query: [0.1])

    matches = vector_store_service.search(kb_id=1, query="正文", top_k=3)

    assert matches[0]["section_path"] == "课程 / 第一章"
    assert matches[0]["score"] == pytest.approx(0.8)


def test_search_tolerates_legacy_metadata_without_section_path(monkeypatch) -> None:
    fake = _FakeCollection()
    fake.query_result["metadatas"] = [
        [{"chunk_id": 5, "document_id": 2, "kb_id": 1, "chunk_index": 0}]
    ]
    monkeypatch.setattr(vector_store_service, "_collection_for", lambda _name: fake)
    monkeypatch.setattr(embedding_service, "embed_text", lambda _query: [0.1])

    matches = vector_store_service.search(kb_id=1, query="正文", top_k=3)

    assert matches[0]["section_path"] == ""


def test_build_context_includes_section_path() -> None:
    context = _build_context(
        [
            {
                "chunk_id": 1,
                "document_id": 2,
                "chunk_index": 0,
                "score": 0.9,
                "content": "正文",
                "section_path": "课程 / 第一章",
            }
        ]
    )

    assert "section_path: 课程 / 第一章" in context


def test_build_context_tolerates_missing_section_path() -> None:
    context = _build_context(
        [
            {
                "chunk_id": 1,
                "document_id": 2,
                "chunk_index": 0,
                "score": 0.9,
                "content": "正文",
            }
        ]
    )

    assert "section_path: " in context
