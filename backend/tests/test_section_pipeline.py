from pathlib import Path

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_section import DocumentSection
from app.models.knowledge_base import KnowledgeBase
from app.services import document_processing_service
from app.services.document_processing_service import (
    clear_document_sections,
    process_document_record,
    reset_document_for_retry,
)
from pdf_builder import build_pdf
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


def test_document_defaults_to_processing_status(db_session: Session) -> None:
    knowledge_base = KnowledgeBase(name="KB-default-status")
    db_session.add(knowledge_base)
    db_session.flush()
    document = Document(
        kb_id=knowledge_base.id,
        title="default",
        file_name="default.md",
        file_path="storage/uploads/1/default.md",
        file_type="md",
    )

    db_session.add(document)
    db_session.flush()

    assert document.status == "processing"


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


def test_process_writes_bigram_search_text(
    db_session: Session, monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        document_processing_service.vector_store_service,
        "add_chunks",
        lambda _chunks, _paths=None: None,
    )
    document = _create_finished_document(db_session, tmp_path, "分词", "# 第一章\n\n背景正文\n")

    process_document_record(db_session, document.id)

    chunks = db_session.scalars(select(DocumentChunk).order_by(DocumentChunk.chunk_index)).all()
    assert chunks[0].search_text == "背景 景正 正文 分词 第一 一章"


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


def test_process_builds_pdf_section_tree_and_retry_is_idempotent(
    db_session: Session, monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        document_processing_service.vector_store_service,
        "add_chunks",
        lambda _chunks, _paths=None: None,
    )
    monkeypatch.setattr(
        document_processing_service.vector_store_service,
        "delete_chunks",
        lambda _ids: None,
    )
    pdf_path = build_pdf(
        tmp_path / "guide.pdf",
        [
            [
                (20.0, "Chapter One"),
                (10.0, "Body of chapter one."),
                (14.0, "1.1 Section A"),
                (10.0, "Body of section A."),
            ],
            [(20.0, "Chapter Two"), (10.0, "Body of chapter two.")],
        ],
        outline=[("Chapter One", 0, None), ("1.1 Section A", 0, 0), ("Chapter Two", 1, None)],
    )
    knowledge_base = KnowledgeBase(name="KB-pdf", description="", category="大数据")
    db_session.add(knowledge_base)
    db_session.flush()
    document = Document(
        kb_id=knowledge_base.id,
        title="PDF 指南",
        file_name="guide.pdf",
        file_path=str(pdf_path),
        file_type="pdf",
        status="processing",
    )
    db_session.add(document)
    db_session.commit()

    process_document_record(db_session, document.id)

    sections = db_session.scalars(
        select(DocumentSection).order_by(DocumentSection.section_order)
    ).all()
    assert [section.section_path for section in sections] == [
        "PDF 指南",
        "PDF 指南 / Chapter One",
        "PDF 指南 / Chapter One / 1.1 Section A",
        "PDF 指南 / Chapter Two",
    ]
    chunks = db_session.scalars(select(DocumentChunk).order_by(DocumentChunk.chunk_index)).all()
    assert chunks, "PDF text must still produce chunks"
    # section_path is part of the lexical index for every chunk.
    assert all(chunk.search_text for chunk in chunks)
    first_chunk_count = len(chunks)
    first_section_count = len(sections)

    # The rebuild/retry path re-parses the same PDF: no duplicated rows.
    reset_document_for_retry(db_session, db_session.get(Document, document.id))
    process_document_record(db_session, document.id)

    assert len(db_session.scalars(select(DocumentSection)).all()) == first_section_count
    assert len(db_session.scalars(select(DocumentChunk)).all()) == first_chunk_count
    assert db_session.get(Document, document.id).status == "finished"
