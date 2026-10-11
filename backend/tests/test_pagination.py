"""Pagination contract for the 7 list endpoints and the streaming export."""

import json
from datetime import datetime
from typing import Any

import pytest
from app.models.conversation import ChatMessage, Conversation
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_section import DocumentSection
from app.models.knowledge_base import KnowledgeBase
from app.models.learning_record import LearningRecord
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _create_kb(client: TestClient, name: str) -> dict[str, Any]:
    response = client.post("/api/kbs", json={"name": name})
    assert response.status_code == 201
    return response.json()


@pytest.mark.parametrize(
    ("url", "params"),
    [
        ("/api/kbs", {"limit": 0}),
        ("/api/kbs", {"limit": 501}),
        ("/api/kbs", {"offset": -1}),
        ("/api/kbs/999/documents", {"limit": 501}),
        ("/api/documents/999/chunks", {"limit": 0}),
        ("/api/documents/999/sections", {"limit": 501}),
        ("/api/conversations", {"limit": 501}),
        ("/api/conversations/999", {"offset": -1}),
        ("/api/learning-records", {"limit": 501}),
    ],
)
def test_pagination_params_are_validated(
    client: TestClient, url: str, params: dict[str, int]
) -> None:
    response = client.get(url, params=params)
    assert response.status_code == 422


def test_knowledge_bases_pagination_slices_newest_first(client: TestClient) -> None:
    for name in ("KB-A", "KB-B", "KB-C"):
        _create_kb(client, name)

    assert len(client.get("/api/kbs").json()) == 3
    first_page = client.get("/api/kbs", params={"limit": 2}).json()
    assert [kb["name"] for kb in first_page] == ["KB-C", "KB-B"]
    second_page = client.get("/api/kbs", params={"limit": 2, "offset": 2}).json()
    assert [kb["name"] for kb in second_page] == ["KB-A"]
    assert client.get("/api/kbs", params={"offset": 10}).json() == []


def _seed_document_with_chunks(db_session: Session, kb: KnowledgeBase, chunk_count: int) -> int:
    document = Document(
        kb_id=kb.id,
        title="分页文档",
        file_name="page.md",
        file_path="page.md",
        file_type="md",
        status="finished",
    )
    db_session.add(document)
    db_session.flush()
    for index in range(chunk_count):
        db_session.add(
            DocumentChunk(
                kb_id=kb.id,
                document_id=document.id,
                chunk_index=index,
                content=f"内容{index}",
                token_count=2,
            )
        )
    db_session.commit()
    return document.id


def test_document_chunks_pagination_keeps_chunk_order(
    client: TestClient, db_session: Session
) -> None:
    kb = KnowledgeBase(name="ChunksKB")
    db_session.add(kb)
    db_session.flush()
    document_id = _seed_document_with_chunks(db_session, kb, 5)

    middle = client.get(
        f"/api/documents/{document_id}/chunks", params={"limit": 2, "offset": 1}
    ).json()
    assert [chunk["chunk_index"] for chunk in middle] == [1, 2]
    tail = client.get(f"/api/documents/{document_id}/chunks", params={"offset": 4}).json()
    assert [chunk["chunk_index"] for chunk in tail] == [4]
    assert client.get(f"/api/documents/{document_id}/chunks", params={"offset": 10}).json() == []


def test_document_sections_pagination_pages_the_flat_list(
    client: TestClient, db_session: Session
) -> None:
    kb = KnowledgeBase(name="SectionsKB")
    db_session.add(kb)
    db_session.flush()
    document = Document(
        kb_id=kb.id,
        title="结构文档",
        file_name="structure.md",
        file_path="structure.md",
        file_type="md",
        status="finished",
    )
    db_session.add(document)
    db_session.flush()
    for order in range(3):
        db_session.add(
            DocumentSection(
                document_id=document.id,
                title=f"第{order + 1}章",
                section_path=f"第{order + 1}章",
                section_level=1,
                section_order=order,
            )
        )
    db_session.commit()

    first_page = client.get(f"/api/documents/{document.id}/sections", params={"limit": 2}).json()

    assert [section["title"] for section in first_page] == ["第1章", "第2章"]
    rest = client.get(
        f"/api/documents/{document.id}/sections", params={"limit": 2, "offset": 2}
    ).json()
    assert [section["title"] for section in rest] == ["第3章"]


def test_conversations_pagination_and_message_pagination(
    client: TestClient, db_session: Session
) -> None:
    kb = KnowledgeBase(name="ConvKB")
    db_session.add(kb)
    db_session.flush()
    conversations = []
    for index, updated in enumerate(
        [datetime(2026, 1, 1), datetime(2026, 1, 2), datetime(2026, 1, 3)], start=1
    ):
        conversation = Conversation(kb_id=kb.id, title=f"会话{index}")
        conversation.updated_at = updated
        db_session.add(conversation)
        conversations.append(conversation)
    db_session.flush()
    for index in range(4):
        db_session.add(
            ChatMessage(
                conversation_id=conversations[0].id,
                kb_id=kb.id,
                role="user" if index % 2 == 0 else "assistant",
                content=f"消息{index}",
            )
        )
    db_session.commit()

    newest_first = client.get("/api/conversations", params={"limit": 2}).json()
    assert [conversation["title"] for conversation in newest_first] == ["会话3", "会话2"]

    detail = client.get(f"/api/conversations/{conversations[0].id}", params={"limit": 2}).json()
    assert [message["content"] for message in detail["messages"]] == ["消息0", "消息1"]
    detail = client.get(
        f"/api/conversations/{conversations[0].id}", params={"limit": 2, "offset": 2}
    ).json()
    assert [message["content"] for message in detail["messages"]] == ["消息2", "消息3"]


def test_learning_records_pagination(client: TestClient, db_session: Session) -> None:
    kb = KnowledgeBase(name="RecordsKB")
    db_session.add(kb)
    db_session.flush()
    for index, updated in enumerate(
        [datetime(2026, 2, 1), datetime(2026, 2, 2), datetime(2026, 2, 3)], start=1
    ):
        record = LearningRecord(
            kb_id=kb.id,
            record_type="note",
            title=f"笔记{index}",
            content=f"正文{index}",
        )
        record.updated_at = updated
        db_session.add(record)
    db_session.commit()

    first_page = client.get("/api/learning-records", params={"limit": 2}).json()
    assert [record["title"] for record in first_page] == ["笔记3", "笔记2"]
    tail = client.get("/api/learning-records", params={"limit": 2, "offset": 2}).json()
    assert [record["title"] for record in tail] == ["笔记1"]


def test_admin_export_streams_same_payload_shape(client: TestClient, db_session: Session) -> None:
    kb = KnowledgeBase(name="ExportKB")
    db_session.add(kb)
    db_session.flush()
    document = Document(
        kb_id=kb.id,
        title="导出文档",
        file_name="export.md",
        file_path="export.md",
        file_type="md",
        status="finished",
    )
    db_session.add(document)
    db_session.flush()
    # More than EXPORT_BATCH_ROWS (200) chunks forces the multi-batch path.
    for index in range(205):
        db_session.add(
            DocumentChunk(
                kb_id=kb.id,
                document_id=document.id,
                chunk_index=index,
                content=f"内容{index}",
                token_count=2,
            )
        )
    conversation = Conversation(kb_id=kb.id, title="导出会话")
    db_session.add(conversation)
    db_session.flush()
    db_session.add(
        ChatMessage(
            conversation_id=conversation.id,
            kb_id=kb.id,
            role="user",
            content="导出问题",
            sources_json=json.dumps([{"chunk_id": 1}]),
        )
    )
    db_session.add(
        LearningRecord(
            kb_id=kb.id,
            record_type="note",
            title="导出笔记",
            content="导出正文",
            tags_json=json.dumps(["重点"]),
            metadata_json=json.dumps({"reviewed": True}),
        )
    )
    db_session.commit()

    response = client.get("/api/admin/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["content-disposition"] == 'attachment; filename="knowflow-export.json"'
    payload = response.json()
    assert payload["version"] == 1
    assert set(payload) == {
        "version",
        "knowledge_bases",
        "documents",
        "chunks",
        "conversations",
        "messages",
        "learning_records",
        "settings",
    }
    assert payload["knowledge_bases"][0]["name"] == "ExportKB"
    assert payload["documents"][0]["title"] == "导出文档"
    assert "file_path" not in payload["documents"][0]
    assert len(payload["chunks"]) == 205
    assert payload["chunks"][0]["content"] == "内容0"
    assert payload["chunks"][204]["chunk_index"] == 204
    assert payload["messages"][0]["content"] == "导出问题"
    assert payload["messages"][0]["sources"] == [{"chunk_id": 1}]
    assert payload["learning_records"][0]["tags"] == ["重点"]
    assert payload["learning_records"][0]["metadata"] == {"reviewed": True}
    assert isinstance(payload["settings"], dict)


def test_admin_export_empty_database_is_valid_json(client: TestClient) -> None:
    response = client.get("/api/admin/export")

    assert response.status_code == 200
    payload = response.json()
    assert payload["knowledge_bases"] == []
    assert payload["chunks"] == []
    assert payload["settings"] == {}
