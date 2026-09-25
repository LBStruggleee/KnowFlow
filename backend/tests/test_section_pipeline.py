from pathlib import Path

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_section import DocumentSection
from app.models.knowledge_base import KnowledgeBase
from app.services import document_processing_service
from app.services.document_processing_service import (
    clear_document_sections,
    process_document_record,
)
from sqlalchemy import select
from sqlalchemy.orm import Session


def _create_finished_document(
    db_session: Session, tmp_path: Path, name: str, text: str
) -> Document:
    knowledge_base = KnowledgeBase(name=f"KB-{name}", description="", category="大数据")
    db_session.add(knowledge_base)
    db_session.flush()
    file_path = tmp_path / f"{name}.md"
    file_path.write_text(text, encoding="utf-8")
    document = Document(
        kb_id=knowledge_base.id,
        title=name,
        file_name=f"{name}.md",
        file_path=str(file_path),
        file_type="md",
        status="processing",
    )
    db_session.add(document)
    db_session.commit()
    return document


def test_process_builds_section_tree_and_chunk_links(
    db_session: Session, monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        document_processing_service.vector_store_service,
        "add_chunks",
        lambda _chunks, _paths=None: None,
    )
    document = _create_finished_document(
        db_session,
        tmp_path,
        "大数据导论",
        "卷首语\n\n# 第一章\n\n章导读\n\n## 1.1 背景\n\n背景正文\n",
    )

    process_document_record(db_session, document.id)

    sections = db_session.scalars(
        select(DocumentSection).order_by(DocumentSection.section_order)
    ).all()
    assert [section.section_path for section in sections] == [
        "大数据导论",
        "大数据导论 / 第一章",
        "大数据导论 / 第一章 / 1.1 背景",
    ]
    assert sections[1].parent_section_id == sections[0].id
    assert sections[2].parent_section_id == sections[1].id
    chunks = db_session.scalars(select(DocumentChunk).order_by(DocumentChunk.chunk_index)).all()
    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2]
    by_title = {section.title: section for section in sections}
    assert chunks[0].section_id == by_title["大数据导论"].id
    assert chunks[1].section_id == by_title["第一章"].id
    assert [section.chunk_count for section in sections] == [1, 1, 1]
    assert db_session.get(Document, document.id).status == "finished"


def test_process_cleans_sections_on_vector_failure(
    db_session: Session, monkeypatch, tmp_path: Path
) -> None:
    def _boom(_chunks):
        raise RuntimeError("chroma down")

    monkeypatch.setattr(document_processing_service.vector_store_service, "add_chunks", _boom)
    document = _create_finished_document(db_session, tmp_path, "失败文档", "# 第一章\n\n正文\n")

    process_document_record(db_session, document.id)

    assert db_session.scalars(select(DocumentSection)).all() == []
    assert db_session.scalars(select(DocumentChunk)).all() == []
    assert db_session.get(Document, document.id).status == "failed"


def test_clear_document_sections_is_idempotent(db_session: Session, tmp_path: Path) -> None:
    document = _create_finished_document(db_session, tmp_path, "幂等", "# 第一章\n\n正文\n")

    clear_document_sections(db_session, document.id)
    clear_document_sections(db_session, document.id)

    assert db_session.scalars(select(DocumentSection)).all() == []


def test_failed_processing_compensates_indexed_vectors(
    db_session: Session, monkeypatch, tmp_path: Path
) -> None:
    deleted: list[list[int]] = []

    def _boom(_chunks, _paths=None):
        raise RuntimeError("chroma down")

    monkeypatch.setattr(document_processing_service.vector_store_service, "add_chunks", _boom)
    monkeypatch.setattr(
        document_processing_service.vector_store_service,
        "delete_chunks",
        lambda _ids: deleted.append(list(_ids)),
    )
    document = _create_finished_document(db_session, tmp_path, "补偿", "# 第一章\n\n正文\n")

    process_document_record(db_session, document.id)

    assert db_session.get(Document, document.id).status == "failed"
    assert len(deleted) == 1
    assert len(deleted[0]) == 1
    assert isinstance(deleted[0][0], int)
