from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_section import DocumentSection
from app.models.knowledge_base import KnowledgeBase
from sqlalchemy import select
from sqlalchemy.orm import Session


def _create_document(db_session: Session) -> Document:
    knowledge_base = KnowledgeBase(name="结构化课程", description="", category="大数据")
    db_session.add(knowledge_base)
    db_session.flush()
    document = Document(
        kb_id=knowledge_base.id,
        title="大数据导论",
        file_name="大数据导论.md",
        file_path="/tmp/大数据导论.md",
        file_type="md",
        status="finished",
    )
    db_session.add(document)
    db_session.flush()
    return document


def test_section_tree_persists_with_parent_links(db_session: Session) -> None:
    document = _create_document(db_session)
    root = DocumentSection(
        document_id=document.id,
        parent_section_id=None,
        title="大数据导论",
        section_path="大数据导论",
        section_level=0,
        section_order=0,
    )
    db_session.add(root)
    db_session.flush()
    child = DocumentSection(
        document_id=document.id,
        parent_section_id=root.id,
        title="第一章",
        section_path="大数据导论 / 第一章",
        section_level=1,
        section_order=1,
    )
    db_session.add(child)
    db_session.commit()

    rows = db_session.scalars(
        select(DocumentSection).order_by(DocumentSection.section_order)
    ).all()
    assert [row.title for row in rows] == ["大数据导论", "第一章"]
    assert rows[1].parent_section_id == rows[0].id


def test_chunk_allows_null_section_id_for_legacy_data(db_session: Session) -> None:
    document = _create_document(db_session)
    chunk = DocumentChunk(
        kb_id=document.kb_id,
        document_id=document.id,
        chunk_index=0,
        content="老数据正文",
        token_count=6,
        section_id=None,
    )
    db_session.add(chunk)
    db_session.commit()

    assert chunk.id is not None
    assert chunk.section_id is None


def test_section_cascade_on_document_delete(db_session: Session) -> None:
    document = _create_document(db_session)
    root = DocumentSection(
        document_id=document.id,
        title="大数据导论",
        section_path="大数据导论",
        section_level=0,
        section_order=0,
    )
    db_session.add(root)
    db_session.flush()
    db_session.add(
        DocumentChunk(
            kb_id=document.kb_id,
            document_id=document.id,
            chunk_index=0,
            content="正文",
            token_count=2,
            section_id=root.id,
        )
    )
    db_session.commit()

    db_session.delete(document)
    db_session.commit()

    assert db_session.scalars(select(DocumentSection)).all() == []
    assert db_session.scalars(select(DocumentChunk)).all() == []
