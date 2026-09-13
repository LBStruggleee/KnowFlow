from pathlib import Path
from typing import Any

from app.api import admin as admin_api
from app.api import chat as chat_api
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.embedding_service import HashingEmbeddingService, ResilientEmbeddingService
from app.services.rag_service import RagService
from app.services.startup_recovery import recover_interrupted_documents
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _create_kb(client: TestClient, name: str = "Spark") -> dict[str, Any]:
    response = client.post("/api/kbs", json={"name": name, "category": "大数据"})
    assert response.status_code == 201
    return response.json()


class _FailingEmbeddingProvider:
    index_name = "unavailable_remote"

    def embed_texts(self, _texts: list[str]) -> list[list[float]]:
        raise HTTPException(status_code=502, detail="remote unavailable")


def test_embedding_provider_falls_back_to_local_after_runtime_failure() -> None:
    service = ResilientEmbeddingService(
        _FailingEmbeddingProvider(),
        HashingEmbeddingService(),
    )

    vectors = service.embed_texts(["Spark RDD lineage"])

    assert service.index_name == "hashing_v1"
    assert len(vectors) == 1
    assert len(vectors[0]) == 384


def test_learning_record_crud_and_link_validation(client: TestClient) -> None:
    kb = _create_kb(client)
    created = client.post(
        "/api/learning-records",
        json={
            "kb_id": kb["id"],
            "record_type": "note",
            "title": "  RDD 复习  ",
            "content": "  Lineage 用于故障恢复。  ",
            "tags": ["RDD", "RDD", "  容错  "],
        },
    )
    assert created.status_code == 201
    record = created.json()
    assert record["title"] == "RDD 复习"
    assert record["tags"] == ["RDD", "容错"]

    listed = client.get(f"/api/learning-records?kb_id={kb['id']}")
    assert [item["id"] for item in listed.json()] == [record["id"]]

    updated = client.patch(
        f"/api/learning-records/{record['id']}",
        json={"record_type": "mistake", "metadata": {"reviewed": False}},
    )
    assert updated.status_code == 200
    assert updated.json()["record_type"] == "mistake"

    assert client.delete(f"/api/learning-records/{record['id']}").status_code == 204
    assert client.get(f"/api/learning-records/{record['id']}").status_code == 404
    assert (
        client.post(
            "/api/learning-records",
            json={
                "kb_id": 999,
                "record_type": "note",
                "title": "无效",
                "content": "无效课程",
            },
        ).status_code
        == 404
    )


def test_local_rag_answer_does_not_call_cloud(monkeypatch) -> None:
    service = RagService()
    sources = [
        {
            "chunk_id": 1,
            "document_id": 2,
            "kb_id": 3,
            "chunk_index": 0,
            "content": "RDD 通过 Lineage 记录转换关系。",
            "score": 0.92,
        }
    ]
    monkeypatch.setattr(
        "app.services.rag_service.vector_store_service.search",
        lambda **_kwargs: sources,
    )
    monkeypatch.setattr(
        "app.services.rag_service.llm_service.chat",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("cloud called")),
    )

    result = service.answer(3, "RDD 如何容错？", privacy_mode="local", mode="explain")

    assert result["answer_mode"] == "local"
    assert result["insufficient_evidence"] is False
    assert "Lineage" in result["answer"]
    assert "[资料 1]" in result["answer"]


def test_chat_enriches_source_and_exposes_answer_mode(
    client: TestClient,
    db_session: Session,
    monkeypatch,
    tmp_path: Path,
) -> None:
    kb = _create_kb(client)
    file_path = tmp_path / "spark.md"
    file_path.write_text("RDD 通过 Lineage 恢复。", encoding="utf-8")
    document = Document(
        kb_id=kb["id"],
        title="Spark 指南",
        file_name="spark.md",
        file_path=str(file_path),
        file_type="md",
        status="finished",
    )
    db_session.add(document)
    db_session.flush()
    chunk = DocumentChunk(
        kb_id=kb["id"],
        document_id=document.id,
        chunk_index=2,
        content="RDD 通过 Lineage 恢复。",
        token_count=8,
    )
    db_session.add(chunk)
    db_session.commit()
    monkeypatch.setattr(
        chat_api.rag_service,
        "answer",
        lambda **_kwargs: {
            "answer": "可恢复 [资料 1]",
            "sources": [
                {
                    "chunk_id": chunk.id,
                    "document_id": document.id,
                    "kb_id": kb["id"],
                    "chunk_index": 2,
                    "content": chunk.content,
                    "score": 0.9,
                }
            ],
            "usage": None,
            "retrieval_trace": None,
            "answer_mode": "local",
            "provider": "local-extractive",
            "insufficient_evidence": False,
        },
    )

    response = client.post(
        "/api/chat",
        json={"kb_id": kb["id"], "question": "如何恢复？", "mode": "explain"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["assistant_message_id"] is not None
    assert payload["answer_mode"] == "local"
    assert payload["sources"][0]["document_title"] == "Spark 指南"
    assert payload["sources"][0]["location"] == "第 3 个片段"


def test_settings_provider_export_and_confirmed_clear(
    client: TestClient,
    monkeypatch,
) -> None:
    kb = _create_kb(client)
    client.post(
        "/api/learning-records",
        json={
            "kb_id": kb["id"],
            "record_type": "note",
            "title": "笔记",
            "content": "正文",
        },
    )
    updated = client.patch(
        "/api/admin/settings",
        json={"privacy_mode": "local", "glass_variant": "contrast"},
    )
    assert updated.status_code == 200
    assert updated.json()["privacy_mode"] == "local"
    assert updated.json()["glass_variant"] == "contrast"

    providers = client.get("/api/admin/providers")
    assert providers.status_code == 200
    assert providers.json()["privacy_mode"] == "local"
    assert providers.json()["embedding_provider"]

    exported = client.get("/api/admin/export")
    assert exported.status_code == 200
    assert exported.json()["knowledge_bases"][0]["name"] == "Spark"
    assert exported.json()["learning_records"][0]["title"] == "笔记"

    assert client.delete("/api/admin/data?confirmation=NO").status_code == 400
    monkeypatch.setattr(
        admin_api.vector_store_service,
        "delete_knowledge_base",
        lambda _kb_id: None,
    )
    cleared = client.delete("/api/admin/data?confirmation=DELETE")
    assert cleared.status_code == 200
    assert cleared.json()["knowledge_bases"] == 1
    assert client.get("/api/kbs").json() == []
    assert client.get("/api/admin/settings").json()["privacy_mode"] == "local"


def test_interrupted_document_becomes_retryable(
    db_session: Session,
    tmp_path: Path,
) -> None:
    from app.models.knowledge_base import KnowledgeBase

    kb = KnowledgeBase(name="Interrupted")
    db_session.add(kb)
    db_session.flush()
    document = Document(
        kb_id=kb.id,
        title="stuck",
        file_name="stuck.md",
        file_path=str(tmp_path / "stuck.md"),
        file_type="md",
        status="processing",
    )
    db_session.add(document)
    db_session.commit()

    assert recover_interrupted_documents(db_session) == 1
    db_session.refresh(document)
    assert document.status == "failed"
    assert "重试" in document.error_message


def test_document_file_endpoint_rejects_paths_outside_upload_root(
    client: TestClient,
    db_session: Session,
    tmp_path: Path,
) -> None:
    from app.models.knowledge_base import KnowledgeBase

    kb = KnowledgeBase(name="Unsafe path")
    db_session.add(kb)
    db_session.flush()
    outside = tmp_path / "outside.md"
    outside.write_text("private", encoding="utf-8")
    document = Document(
        kb_id=kb.id,
        title="outside",
        file_name="outside.md",
        file_path=str(outside),
        file_type="md",
        status="finished",
    )
    db_session.add(document)
    db_session.commit()

    response = client.get(f"/api/documents/{document.id}/file")

    assert response.status_code == 404
