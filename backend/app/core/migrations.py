"""Versioned, idempotent startup schema migrations.

Schema evolution used to be scattered across main.py (hand-written ALTER
TABLE calls) and lexical_search.py (FTS DDL), with no record of what had
been applied to which database. This module registers every startup
migration as an ordered, idempotent step and records applied versions in a
``schema_migrations`` table, so a fresh database and an upgraded legacy
database end up in the same state.

Run after ``Base.metadata.create_all``: create_all brings a fresh database
up to the current model schema, while the migrations below repair databases
created by older versions (missing columns, missing FTS index, legacy rows
without search_text). Every step must also be safe to run on an
already-current database, because create_all may have pre-applied it.
"""

import logging
from collections.abc import Callable

from app.services.lexical_search import (
    backfill_search_text,
    ensure_chunk_columns,
    ensure_lexical_index,
)
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

SCHEMA_MIGRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
)
""".strip()


def _migrate_backfill_search_text(engine: Engine) -> None:
    with Session(bind=engine) as db:
        backfill_search_text(db)


# Ordered, idempotent steps. The order mirrors the historical startup
# sequence: columns must exist before the FTS index is built over them, and
# the FTS UPDATE trigger keeps the index in sync while the backfill commits.
MIGRATIONS: list[tuple[int, str, Callable[[Engine], None]]] = [
    (1, "ensure_chunk_columns", ensure_chunk_columns),
    (2, "ensure_lexical_index", ensure_lexical_index),
    (3, "backfill_search_text", _migrate_backfill_search_text),
]


def applied_versions(engine: Engine) -> set[int]:
    with engine.connect() as connection:
        rows = connection.execute(text("SELECT version FROM schema_migrations")).fetchall()
    return {int(row[0]) for row in rows}


def run_migrations(engine: Engine) -> list[int]:
    """Apply pending migrations in order; return the versions applied now."""
    with engine.begin() as connection:
        connection.execute(text(SCHEMA_MIGRATIONS_DDL))
    done = applied_versions(engine)
    newly_applied: list[int] = []
    for version, name, migrate in MIGRATIONS:
        if version in done:
            continue
        migrate(engine)
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO schema_migrations (version, name) VALUES (:version, :name)"),
                {"version": version, "name": name},
            )
        newly_applied.append(version)
        logger.info("Applied migration %s: %s", version, name)
    return newly_applied
