"""Filesystem helpers shared by the API layer."""

import logging
from pathlib import Path

from app.core.database import BASE_DIR

logger = logging.getLogger(__name__)

UPLOAD_ROOT = BASE_DIR / "storage" / "uploads"


def is_under_upload_root(file_path: Path) -> bool:
    """Return True when ``file_path`` resolves inside the upload root."""
    try:
        file_path.resolve().relative_to(UPLOAD_ROOT.resolve())
    except ValueError:
        return False
    return True


def safe_unlink(file_path: Path) -> None:
    """Delete an uploaded file, refusing paths outside the upload root."""
    if not is_under_upload_root(file_path):
        logger.error("Refusing to delete path outside upload directory: %s", file_path)
        return
    try:
        file_path.unlink(missing_ok=True)
    except OSError:
        logger.exception("Could not delete uploaded file: %s", file_path)
