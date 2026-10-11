import sqlite3
from pathlib import Path

from app.core import files as files_module
from app.core.database import configure_sqlite_connection
from app.core.db_utils import load_json_column
from app.core.files import safe_unlink


def test_configure_sqlite_connection_enables_wal_busy_timeout_and_foreign_keys(
    tmp_path: Path,
) -> None:
    connection = sqlite3.connect(tmp_path / "pragma.db")

    configure_sqlite_connection(connection)

    assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    connection.close()


def test_safe_unlink_deletes_files_inside_upload_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(files_module, "UPLOAD_ROOT", tmp_path)
    target = tmp_path / "kb-1" / "doc.md"
    target.parent.mkdir(parents=True)
    target.write_text("content", encoding="utf-8")

    safe_unlink(target)

    assert not target.exists()


def test_safe_unlink_refuses_paths_outside_upload_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(files_module, "UPLOAD_ROOT", tmp_path / "upload-root")
    outside = tmp_path / "outside.md"
    outside.write_text("keep me", encoding="utf-8")

    safe_unlink(outside)

    assert outside.exists()


def test_load_json_column_parses_valid_json() -> None:
    assert load_json_column('["a", "b"]', []) == ["a", "b"]
    assert load_json_column('{"k": 1}', {}) == {"k": 1}


def test_load_json_column_falls_back_on_malformed_or_mismatched_values() -> None:
    assert load_json_column("not json", []) == []
    assert load_json_column(None, []) == []
    assert load_json_column("", []) == []
    assert load_json_column('{"k": 1}', []) == []
    assert load_json_column("[1, 2]", {}) == {}
