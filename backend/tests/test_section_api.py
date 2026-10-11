from pathlib import Path
from typing import Any

from app.api import documents as documents_api
from app.api import knowledge_bases as knowledge_bases_api
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_section import DocumentSection
from app.services import document_processing_service
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session


def _create_kb(client: TestClient, name: str = "TreeKB") -> dict[str, Any]:
    response = client.post("/api/kbs", json={"name": name, "description": "", "category": "大数据"})
    assert response.status_code == 201
    return response.json()


def _enable_sync_processing(client, db_session, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(documents_api, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(
        document_processing_service.vector_store_service, "add_chunks", lambda *args: None
    )
    monkeypatch.setattr(
        document_processing_service.vector_store_service,
        "delete_chunks",
        lambda _chunk_ids: None,
    )
    monkeypatch.setattr(
        documents_api,
        "process_document",
        lambda document_id: document_processing_service.process_document_record(
            db_session, document_id
        ),
    )


def _upload_md(client: TestClient, kb_id: int, name: str, text: str) -> dict[str, Any]:
    response = client.post(
        f"/api/kbs/{kb_id}/documents/upload",
        files={"file": (name, text, "text/markdown")},
    )
    assert response.status_code == 202
    return response.json()


def test_sections_endpoint_returns_nested_tree(
    client: TestClient, db_session: Session, monkeypatch, tmp_path: Path
) -> None:
    kb = _create_kb(client)
    _enable_sync_processing(client, db_session, monkeypatch, tmp_path)
    uploaded = _upload_md(client, kb["id"], "tree.md", "# 第一章\n\n导读\n\n## 1.1 背景\n\n正文\n")

    response = client.get(f"/api/documents/{uploaded['id']}/sections")

    assert response.status_code == 200
    (root,) = response.json()
    assert root["title"] == "tree"
    assert root["section_path"] == "tree"
    (chapter,) = root["children"]
    assert chapter["title"] == "第一章"
    assert chapter["section_path"] == "tree / 第一章"
    (background,) = chapter["children"]
    assert background["chunk_count"] == 1


def test_sections_endpoint_returns_404_for_missing_document(client: TestClient) -> None:
    assert client.get("/api/documents/9999/sections").status_code == 404


def test_chunks_response_carries_section_path(
    client: TestClient, db_session: Session, monkeypatch, tmp_path: Path
) -> None:
    kb = _create_kb(client)
    _enable_sync_processing(client, db_session, monkeypatch, tmp_path)
    uploaded = _upload_md(client, kb["id"], "paths.md", "# 第一章\n\n正文\n")

    chunks = client.get(f"/api/documents/{uploaded['id']}/chunks").json()

    assert chunks[0]["section_id"] is not None
    assert chunks[0]["section_path"] == "paths / 第一章"


def test_chunks_response_tolerates_legacy_null_section(
    client: TestClient, db_session: Session, monkeypatch, tmp_path: Path
) -> None:
    kb = _create_kb(client)
    _enable_sync_processing(client, db_session, monkeypatch, tmp_path)
    uploaded = _upload_md(client, kb["id"], "legacy.md", "纯正文无标题\n")
    document_id = uploaded["id"]
    chunk = db_session.scalars(
        select(DocumentChunk).where(DocumentChunk.document_id == document_id)
    ).one()
    chunk.section_id = None
    db_session.commit()

    chunks = client.get(f"/api/documents/{document_id}/chunks").json()

    assert chunks[0]["section_id"] is None
    assert chunks[0]["section_path"] == ""


def test_delete_document_removes_sections(
    client: TestClient, db_session: Session, monkeypatch, tmp_path: Path
) -> None:
    kb = _create_kb(client)
    _enable_sync_processing(client, db_session, monkeypatch, tmp_path)
    uploaded = _upload_md(client, kb["id"], "gone.md", "# 第一章\n\n正文\n")

    assert client.delete(f"/api/documents/{uploaded['id']}").status_code == 204
    assert db_session.scalars(select(DocumentSection)).all() == []


def test_rebuild_rejects_when_documents_are_processing(
    client: TestClient, db_session: Session, monkeypatch, tmp_path: Path
) -> None:
    kb = _create_kb(client)
    _enable_sync_processing(client, db_session, monkeypatch, tmp_path)
    uploaded = _upload_md(client, kb["id"], "busy.md", "# 第一章\n\n正文\n")
    document = db_session.get(Document, uploaded["id"])
    document.status = "processing"
    db_session.commit()

    response = client.post(f"/api/kbs/{kb['id']}/rebuild-index")

    assert response.status_code == 409


def test_rebuild_rejects_concurrent_rebuild_for_same_kb(
    client: TestClient, db_session: Session, monkeypatch, tmp_path: Path
) -> None:
    kb = _create_kb(client)
    _enable_sync_processing(client, db_session, monkeypatch, tmp_path)
    _upload_md(client, kb["id"], "guard.md", "# 第一章\n\n正文\n")
    knowledge_bases_api._rebuilding_kbs.add(kb["id"])
    try:
        response = client.post(f"/api/kbs/{kb['id']}/rebuild-index")
    finally:
        knowledge_bases_api._rebuilding_kbs.clear()

    assert response.status_code == 409


def test_rebuild_guard_is_released_after_failure(
    client: TestClient, db_session: Session, monkeypatch, tmp_path: Path
) -> None:
    kb = _create_kb(client)
    _enable_sync_processing(client, db_session, monkeypatch, tmp_path)
    _upload_md(client, kb["id"], "boom.md", "# 第一章\n\n正文\n")

    def exploding_process(_db, _document_id):
        raise RuntimeError("parse exploded")

    monkeypatch.setattr(knowledge_bases_api, "process_document_record", exploding_process)

    response = client.post(f"/api/kbs/{kb['id']}/rebuild-index")

    assert response.status_code == 502
    assert kb["id"] not in knowledge_bases_api._rebuilding_kbs


def test_rebuild_compensates_vectors_after_failed_reindex(
    client: TestClient, db_session: Session, monkeypatch, tmp_path: Path
) -> None:
    kb = _create_kb(client)
    _enable_sync_processing(client, db_session, monkeypatch, tmp_path)
    uploaded = _upload_md(client, kb["id"], "lost.md", "# 第一章\n\n正文\n")
    document = db_session.get(Document, uploaded["id"])
    Path(document.file_path).unlink()

    add_calls: list[int] = []

    def flaky_add(chunks, _paths=None):
        add_calls.append(len(chunks))
        if len(add_calls) == 1:
            raise RuntimeError("embedding api down")

    monkeypatch.setattr(knowledge_bases_api.vector_store_service, "add_chunks", flaky_add)
    monkeypatch.setattr(
        knowledge_bases_api.vector_store_service, "delete_chunks", lambda _ids: None
    )

    response = client.post(f"/api/kbs/{kb['id']}/rebuild-index")

    assert response.status_code == 200
    assert add_calls == [1, 1], "compensation must re-run the failed upsert"
    assert response.json()["indexed_chunks"] == 1


def test_rebuild_returns_502_when_compensation_also_fails(
    client: TestClient, db_session: Session, monkeypatch, tmp_path: Path
) -> None:
    kb = _create_kb(client)
    _enable_sync_processing(client, db_session, monkeypatch, tmp_path)
    uploaded = _upload_md(client, kb["id"], "gone.md", "# 第一章\n\n正文\n")
    document = db_session.get(Document, uploaded["id"])
    Path(document.file_path).unlink()

    def always_failing_add(_chunks, _paths=None):
        raise RuntimeError("embedding api still down")

    monkeypatch.setattr(knowledge_bases_api.vector_store_service, "add_chunks", always_failing_add)
    monkeypatch.setattr(
        knowledge_bases_api.vector_store_service, "delete_chunks", lambda _ids: None
    )

    response = client.post(f"/api/kbs/{kb['id']}/rebuild-index")

    assert response.status_code == 502
    assert "rebuild" in response.json()["detail"].lower()
    assert kb["id"] not in knowledge_bases_api._rebuilding_kbs


def test_rebuild_reparses_finished_documents(
    client: TestClient, db_session: Session, monkeypatch, tmp_path: Path
) -> None:
    kb = _create_kb(client)
    _enable_sync_processing(client, db_session, monkeypatch, tmp_path)
    uploaded = _upload_md(client, kb["id"], "rebuild.md", "# 第一章\n\n正文\n")
    document_id = uploaded["id"]
    db_session.query(DocumentSection).filter(DocumentSection.document_id == document_id).delete()
    db_session.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()
    db_session.commit()

    response = client.post(f"/api/kbs/{kb['id']}/rebuild-index")

    assert response.status_code == 200
    assert response.json()["indexed_chunks"] == 1
    assert (
        db_session.scalar(
            select(DocumentSection.id).where(DocumentSection.document_id == document_id)
        )
        is not None
    )


def test_rebuild_keeps_chunks_when_source_file_missing(
    client: TestClient, db_session: Session, monkeypatch, tmp_path: Path
) -> None:
    kb = _create_kb(client)
    _enable_sync_processing(client, db_session, monkeypatch, tmp_path)
    uploaded = _upload_md(client, kb["id"], "lost.md", "# 第一章\n\n正文\n")
    document_id = uploaded["id"]
    stored = db_session.get(Document, document_id)
    Path(stored.file_path).unlink()
    monkeypatch.setattr(
        knowledge_bases_api.vector_store_service, "delete_knowledge_base", lambda _kb: None
    )

    response = client.post(f"/api/kbs/{kb['id']}/rebuild-index")

    assert response.status_code == 200
    assert response.json()["indexed_chunks"] == 1
    assert (
        db_session.scalar(select(DocumentChunk.id).where(DocumentChunk.document_id == document_id))
        is not None
    )


def test_chat_sources_carry_section_path(
    client: TestClient, db_session: Session, monkeypatch, tmp_path: Path
) -> None:
    from app.api import chat as chat_api

    kb = _create_kb(client, "ChatKB")
    _enable_sync_processing(client, db_session, monkeypatch, tmp_path)
    _upload_md(client, kb["id"], "chat.md", "# 第一章\n\n正文\n")

    def fake_answer(**kwargs):
        return {
            "answer": "测试回答",
            "sources": [
                {
                    "chunk_id": 1,
                    "document_id": 999,
                    "kb_id": kb["id"],
                    "chunk_index": 0,
                    "content": "正文",
                    "score": 0.9,
                    "section_path": "chat / 第一章",
                }
            ],
            "usage": None,
            "retrieval_trace": None,
        }

    monkeypatch.setattr(chat_api.rag_service, "answer", fake_answer)
    response = client.post("/api/chat", json={"kb_id": kb["id"], "question": "讲了什么"})

    assert response.status_code == 200
    (source,) = response.json()["sources"]
    assert source["section_path"] == "chat / 第一章"
    assert source["document_title"] == "已删除资料"


def test_vector_search_results_carry_section_path(client: TestClient, monkeypatch) -> None:
    from app.services import vector_store_service as vector_store_module

    kb = _create_kb(client, "SearchKB")
    monkeypatch.setattr(
        vector_store_module.vector_store_service,
        "search",
        lambda kb_id, query, top_k=5: [
            {
                "chunk_id": 1,
                "document_id": 1,
                "kb_id": kb_id,
                "chunk_index": 0,
                "content": "正文",
                "score": 0.9,
                "section_path": "chat / 第一章",
            }
        ],
    )

    response = client.post(f"/api/kbs/{kb['id']}/search", json={"query": "正文"})

    assert response.status_code == 200
    (result,) = response.json()["results"]
    assert result["section_path"] == "chat / 第一章"


def _upload_term_doc(
    client: TestClient, db_session, monkeypatch, tmp_path: Path, kb_id: int
) -> None:
    from app.api import documents as documents_api
    from app.services import document_processing_service

    monkeypatch.setattr(documents_api, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(
        document_processing_service.vector_store_service, "add_chunks", lambda *args: None
    )
    monkeypatch.setattr(
        documents_api,
        "process_document",
        lambda document_id: document_processing_service.process_document_record(
            db_session, document_id
        ),
    )
    response = client.post(
        f"/api/kbs/{kb_id}/documents/upload",
        files={"file": ("term.md", "# 指南\n\nNameNode 是主节点\n", "text/markdown")},
    )
    assert response.status_code == 202


def test_chat_lexical_channel_hits_term(
    client: TestClient, db_session: Session, monkeypatch, tmp_path: Path
) -> None:
    kb = _create_kb(client, "LexicalChatKB")
    _upload_term_doc(client, db_session, monkeypatch, tmp_path, kb["id"])
    settings_response = client.patch("/api/admin/settings", json={"retrieval_channels": "lexical"})
    assert settings_response.status_code == 200

    response = client.post("/api/chat", json={"kb_id": kb["id"], "question": "NameNode是什么"})

    assert response.status_code == 200
    body = response.json()
    assert body["sources"], "lexical channel should hit the term document"
    assert body["retrieval_trace"]["channels"]["mode"] == "lexical"
    assert body["retrieval_trace"]["channels"]["lexical"]["returned"] >= 1
    client.patch("/api/admin/settings", json={"retrieval_channels": "hybrid"})


def test_vector_search_uses_hybrid_by_default(
    client: TestClient, db_session: Session, monkeypatch, tmp_path: Path
) -> None:
    kb = _create_kb(client, "HybridSearchKB")
    _upload_term_doc(client, db_session, monkeypatch, tmp_path, kb["id"])

    response = client.post(f"/api/kbs/{kb['id']}/search", json={"query": "NameNode"})

    assert response.status_code == 200
    results = response.json()["results"]
    assert results, "hybrid search should hit the term document"
    assert results[0]["section_path"] == "term / 指南"
