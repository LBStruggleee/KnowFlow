"""Database utility functions for consistent exception handling."""

import logging

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

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
        from fastapi import HTTPException
        raise HTTPException(
            status_code=409,
            detail="Resource already exists.",
        ) from exc