from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_section import DocumentSection
from app.models.knowledge_base import KnowledgeBase
from app.services.lexical_search import (
    _build_search_text,
    backfill_search_text,
    ensure_chunk_columns,
    ensure_lexical_index,
    fts5_available,
    to_search_text,
)
from sqlalchemy import text
from sqlalchemy.orm import Session


def test_to_search_text_bigrams_chinese() -> None:
    assert to_search_text("混合检索") == "混合 合检 检索"


def test_to_search_text_handles_mixed_chinese_ascii() -> None:
    assert to_search_text("HDFS的NameNode节点") == "HDFS NameNode 节点"


def test_to_search_text_drops_punctuation_and_single_chars() -> None:
    assert to_search_text("你好，世界！") == "你好 世界"
    assert to_search_text("是的") == "是的"


def test_to_search_text_returns_empty_for_blank_or_symbol_input() -> None:
    assert to_search_text("") == ""
    assert to_search_text("  !!!???  ") == ""


def test_to_search_text_keeps_ascii_words_whole() -> None:
    assert to_search_text("MapReduce Shuffle") == "MapReduce Shuffle"


def test_build_search_text_combines_content_and_section_path() -> None:
    assert _build_search_text("背景正文", "课程 / 第一章") == "背景 景正 正文 课程 第一 一章"
    assert _build_search_text("背景正文") == "背景 景正 正文"


def _create_chunk(db_session: Session, content: str, search_text: str = "") -> DocumentChunk:
    knowledge_base = KnowledgeBase(name=f"KB-{content[:6]}", description="", category="")
    db_session.add(knowledge_base)
    db_session.flush()
    document = Document(
        kb_id=knowledge_base.id,
        title="词面",
        file_name="词面.md",
        file_path="/tmp/词面.md",
        file_type="md",
        status="finished",
    )
    db_session.add(document)
    db_session.flush()
    section = DocumentSection(
        document_id=document.id,
        title="词面",
        section_path="词面",
        section_level=0,
        section_order=0,
    )
    db_session.add(section)
    db_session.flush()
    chunk = DocumentChunk(
        kb_id=knowledge_base.id,
        document_id=document.id,
        chunk_index=0,
        content=content,
        token_count=1,
        section_id=section.id,
        search_text=search_text,
    )
    db_session.add(chunk)
    db_session.commit()
    return chunk


def test_triggers_sync_fts_on_insert_update_delete(db_session: Session) -> None:
    chunk = _create_chunk(db_session, "混合检索提升召回", _build_search_text("混合检索提升召回"))

    hits = db_session.execute(
        text("SELECT rowid FROM chunk_fts WHERE chunk_fts MATCH '混合'")
    ).all()
    assert [row[0] for row in hits] == [chunk.id]

    chunk.search_text = _build_search_text("向量数据库原理")
    db_session.commit()
    assert (
        db_session.execute(text("SELECT rowid FROM chunk_fts WHERE chunk_fts MATCH '混合'")).all()
        == []
    )
    assert (
        db_session.execute(text("SELECT rowid FROM chunk_fts WHERE chunk_fts MATCH '向量'")).all()
        != []
    )

    db_session.delete(chunk)
    db_session.commit()
    assert (
        db_session.execute(text("SELECT rowid FROM chunk_fts WHERE chunk_fts MATCH '向量'")).all()
        == []
    )


def test_backfill_search_text_fills_legacy_rows(db_session: Session) -> None:
    chunk = _create_chunk(db_session, "窄依赖影响恢复")

    filled = backfill_search_text(db_session)

    assert filled == 1
    db_session.refresh(chunk)
    assert chunk.search_text == _build_search_text("窄依赖影响恢复", "词面")
    hits = db_session.execute(
        text("SELECT rowid FROM chunk_fts WHERE chunk_fts MATCH '窄依'")
    ).all()
    assert [row[0] for row in hits] == [chunk.id]


def test_ensure_lexical_index_is_idempotent(db_session: Session) -> None:
    assert ensure_lexical_index(db_session.get_bind()) is True
    assert ensure_lexical_index(db_session.get_bind()) is True
    tables = db_session.execute(
        text("SELECT name FROM sqlite_master WHERE name='chunk_fts'")
    ).all()
    assert tables != []


def test_fts5_available_on_supported_sqlite(db_session: Session) -> None:
    assert fts5_available(db_session.get_bind()) is True


def test_ensure_chunk_columns_repairs_legacy_table(db_session: Session) -> None:
    # Legacy tables predate both the column and the triggers; drop triggers first
    # because SQLite refuses DROP COLUMN while a trigger references it.
    db_session.execute(text("DROP TRIGGER chunk_fts_ai"))
    db_session.execute(text("DROP TRIGGER chunk_fts_ad"))
    db_session.execute(text("DROP TRIGGER chunk_fts_au"))
    db_session.execute(text("ALTER TABLE document_chunk DROP COLUMN search_text"))
    db_session.commit()

    ensure_chunk_columns(db_session.get_bind())

    columns = db_session.execute(text("PRAGMA table_info(document_chunk)")).all()
    assert "search_text" in [row[1] for row in columns]
