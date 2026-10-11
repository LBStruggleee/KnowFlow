"""Versioned migration runner: fresh-database and legacy-upgrade paths."""

from app.core.database import Base
from app.core.migrations import MIGRATIONS, applied_versions, run_migrations
from app.models.document_chunk import DocumentChunk
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


def _memory_engine() -> Engine:
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def test_migrations_are_ordered_and_uniquely_versioned() -> None:
    versions = [version for version, _, _ in MIGRATIONS]

    assert versions == sorted(versions)
    assert len(set(versions)) == len(versions)
    assert all(name for _, name, _ in MIGRATIONS)


def test_run_migrations_on_fresh_database_records_all_versions_and_backfills() -> None:
    engine = _memory_engine()
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        # A chunk written before any migration ran, still carrying an empty
        # search_text like rows created by pre-FTS versions.
        connection.execute(
            text(
                "INSERT INTO document_chunk (kb_id, document_id, chunk_index, content, "
                "token_count, search_text) VALUES (1, 1, 0, '混合检索', 4, '')"
            )
        )

    applied = run_migrations(engine)

    assert applied == [version for version, _, _ in MIGRATIONS]
    assert applied_versions(engine) == set(applied)
    with Session(bind=engine) as db:
        chunk = db.get(DocumentChunk, 1)
        assert chunk is not None
        assert "混合" in chunk.search_text
    with engine.connect() as connection:
        indexed = connection.execute(
            text("SELECT rowid FROM chunk_fts WHERE chunk_fts MATCH :q"), {"q": "混合"}
        ).fetchall()
    assert [row[0] for row in indexed] == [1]


def test_run_migrations_on_fresh_database_is_idempotent() -> None:
    engine = _memory_engine()
    Base.metadata.create_all(engine)

    assert run_migrations(engine) == [version for version, _, _ in MIGRATIONS]
    assert run_migrations(engine) == []
    assert applied_versions(engine) == {version for version, _, _ in MIGRATIONS}


LEGACY_CHUNK_DDL = """
CREATE TABLE document_chunk (
    id INTEGER PRIMARY KEY,
    kb_id INTEGER NOT NULL,
    document_id INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""".strip()


def _seed_legacy_database(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text(LEGACY_CHUNK_DDL))
        connection.execute(
            text(
                "INSERT INTO document_chunk (kb_id, document_id, chunk_index, content) "
                "VALUES (1, 1, 0, '机器学习基础')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO document_chunk (kb_id, document_id, chunk_index, content) "
                "VALUES (1, 1, 1, '深度学习进阶')"
            )
        )


def test_run_migrations_upgrades_legacy_database_without_columns_or_fts() -> None:
    engine = _memory_engine()
    _seed_legacy_database(engine)
    with engine.connect() as connection:
        columns = {
            row[1] for row in connection.exec_driver_sql("PRAGMA table_info(document_chunk)")
        }
    assert "section_id" not in columns
    assert "search_text" not in columns

    applied = run_migrations(engine)

    assert applied == [version for version, _, _ in MIGRATIONS]
    with engine.connect() as connection:
        columns = {
            row[1] for row in connection.exec_driver_sql("PRAGMA table_info(document_chunk)")
        }
        assert {"section_id", "search_text"} <= columns
        backfilled = connection.execute(
            text("SELECT id, search_text FROM document_chunk ORDER BY id")
        ).fetchall()
        indexed = connection.execute(
            text("SELECT rowid FROM chunk_fts WHERE chunk_fts MATCH :q"), {"q": "学习"}
        ).fetchall()
    assert [text_value for _, text_value in backfilled] and all(
        text_value for _, text_value in backfilled
    )
    assert [row[0] for row in indexed] == [1, 2]


def test_run_migrations_on_upgraded_legacy_database_is_idempotent() -> None:
    engine = _memory_engine()
    _seed_legacy_database(engine)

    run_migrations(engine)
    second_pass = run_migrations(engine)

    assert second_pass == []
    with Session(bind=engine) as db:
        assert db.query(DocumentChunk).count() == 2


def test_migration_registry_keeps_the_historical_startup_order() -> None:
    assert [name for _, name, _ in MIGRATIONS] == [
        "ensure_chunk_columns",
        "ensure_lexical_index",
        "backfill_search_text",
    ]
