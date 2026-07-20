from pathlib import Path
from typing import Any

from app.api import chat as chat_api
from app.api import documents as documents_api
from app.api import knowledge_bases as knowledge_bases_api
from app.core.config import settings
from app.models.conversation import ChatMessage, Conversation
from app.models.document import Document
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session


def _create_kb(client: TestClient, name: str = "Spark") -> dict[str, Any]:
    response = client.post(
        "/api/kbs",
        json={"name": name, "description": "课程资料", "category": "大数据"},
    )
    assert response.status_code == 201
    return response.json()


def test_knowledge_base_names_are_trimmed_and_unique(client: TestClient) -> None:
    created = _create_kb(client, "  Spark  ")
    assert created["name"] == "Spark"

    duplicate = client.post("/api/kbs", json={"name": "Spark"})
    assert duplicate.status_code == 409


def test_conversation_requires_existing_knowledge_base(client: TestClient) -> None:
    response = client.post(
        "/api/conversations",
        json={"kb_id": 999, "title": "不存在"},
    )
    assert response.status_code == 404


def test_chat_uses_configured_top_k_and_passes_history(
    client: TestClient,
    monkeypatch,
) -> None:
    kb = _create_kb(client)
    client.patch("/api/admin/settings", json={"top_k": 7})
    calls: list[dict[str, Any]] = []

    def fake_answer(**kwargs):
        calls.append(kwargs)
        return {
            "answer": "测试回答",
            "sources": [],
            "usage": None,
            "retrieval_trace": None,
        }

    monkeypatch.setattr(chat_api.rag_service, "answer", fake_answer)
    first = client.post("/api/chat", json={"kb_id": kb["id"], "question": "第一问"})
    assert first.status_code == 200
    conversation_id = first.json()["conversation_id"]

    second = client.post(
        "/api/chat",
        json={
            "kb_id": kb["id"],
            "question": "它有什么特点？",
            "conversation_id": conversation_id,
        },
    )
    assert second.status_code == 200
    assert calls[0]["top_k"] == 7
    assert calls[0]["history"] == []
    assert [message["role"] for message in calls[1]["history"]] == [
        "user",
        "assistant",
    ]


def test_delete_knowledge_base_removes_conversations(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    kb = _create_kb(client)
    conversation = Conversation(kb_id=kb["id"], title="测试")
    db_session.add(conversation)
    db_session.flush()
    db_session.add(
        ChatMessage(
            conversation_id=conversation.id,
            kb_id=kb["id"],
            role="user",
            content="问题",
        )
    )
    db_session.commit()
    monkeypatch.setattr(
        knowledge_bases_api.vector_store_service,
        "delete_knowledge_base",
        lambda _kb_id: None,
    )

    response = client.delete(f"/api/kbs/{kb['id']}")
    assert response.status_code == 204
    assert db_session.scalars(select(Conversation)).all() == []
    assert db_session.scalars(select(ChatMessage)).all() == []


def test_upload_streams_content_and_returns_real_chunk_count(
    client: TestClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    kb = _create_kb(client)
    monkeypatch.setattr(documents_api, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(
        documents_api.vector_store_service,
        "add_chunks",
        lambda _chunks: None,
    )

    response = client.post(
        f"/api/kbs/{kb['id']}/documents/upload",
        files={"file": ("lesson.md", "第一段\n\n第二段", "text/markdown")},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "finished"
    assert response.json()["chunk_count"] == 1


def test_upload_limit_rejects_file_without_creating_document(
    client: TestClient,
    db_session: Session,
    monkeypatch,
    tmp_path: Path,
) -> None:
    kb = _create_kb(client)
    monkeypatch.setattr(documents_api, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(settings, "upload_max_bytes", 4)

    response = client.post(
        f"/api/kbs/{kb['id']}/documents/upload",
        files={"file": ("large.md", b"12345", "text/markdown")},
    )
    assert response.status_code == 413
    assert db_session.scalars(select(Document)).all() == []
