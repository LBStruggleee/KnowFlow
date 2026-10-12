"""Database utility functions for consistent exception handling."""

import json
import logging
from typing import Any

from app.models.knowledge_base import KnowledgeBase
from fastapi import HTTPException, status
from sqlalchemy import Select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class CommitConflictError(Exception):
    """Raised when a commit fails due to a constraint violation."""


def safe_commit(db) -> None:
    """Commit the current transaction, rolling back on any error.

    This provides a single, consistent commit/rollback pattern for all
    endpoints. Callers that need to convert ``IntegrityError`` into a
    domain-specific response should catch :class:`CommitConflictError`
    and inspect ``.cause`` instead of importing ``IntegrityError``
    directly.
    """
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise CommitConflictError("Constraint violation") from exc
    except SQLAlchemyError:
        db.rollback()
        raise


def commit_or_conflict(db) -> None:
    """Commit, converting ``IntegrityError`` into an HTTP 409 response.

    Use this helper when a unique-constraint violation should surface as
    a user-facing conflict rather than a 500 error.
    """
    try:
        safe_commit(db)
    except CommitConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail="Resource already exists.",
        ) from exc


def load_json_column(value: str | None, default: Any) -> Any:
    """Parse a JSON column value, falling back to ``default`` when malformed.

    The parsed value must match the type of ``default`` so callers always
    receive the shape they declared.
    """
    try:
        loaded = json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        logger.warning("Ignoring malformed JSON column value")
        return default
    return loaded if isinstance(loaded, type(default)) else default


def get_knowledge_base_or_404(db: Session, kb_id: int) -> KnowledgeBase:
    """Fetch a knowledge base or raise the shared 404 response."""
    knowledge_base = db.get(KnowledgeBase, kb_id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found.",
        )
    return knowledge_base


def id_to_text_map(db: Session, statement: Select[tuple[int, str]]) -> dict[int, str]:
    """Run a two-column ``(id, text)`` select and build an id-to-text dict.

    The query must return at most one text row per id; duplicates keep the
    last row, mirroring the ``dict(...)`` idiom this replaces.
    """
    return {int(row[0]): str(row[1]) for row in db.execute(statement)}
