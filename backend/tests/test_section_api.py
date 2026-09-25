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
    response = client.post(
        "/api/kbs", json={"name": name, "description": "", "category": "大数据"}
    )
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
    uploaded = _upload_md(
        client, kb["id"], "tree.md", "# 第一章\n\n导读\n\n## 1.1 背景\n\n正文\n"
    )

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


def test_rebuild_reparses_finished_documents(
    client: TestClient, db_session: Session, monkeypatch, tmp_path: Path
) -> None:
    kb = _create_kb(client)
    _enable_sync_processing(client, db_session, monkeypatch, tmp_path)
    uploaded = _upload_md(client, kb["id"], "rebuild.md", "# 第一章\n\n正文\n")
    document_id = uploaded["id"]
    db_session.query(DocumentSection).filter(
        DocumentSection.document_id == document_id
    ).delete()
    db_session.query(DocumentChunk).filter(
        DocumentChunk.document_id == document_id
    ).delete()
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
        db_session.scalar(
            select(DocumentChunk.id).where(DocumentChunk.document_id == document_id)
        )
        is not None
    )
