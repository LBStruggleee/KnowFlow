from pathlib import Path

import pytest
from app.services.document_parser import normalize_text, parse_document_text


def test_normalize_text_trims_lines_and_collapses_blank_lines() -> None:
    assert normalize_text(" first  \r\n\r\n\r\n second ") == "first\n\nsecond"


def test_parse_document_text_reads_utf8_markdown(tmp_path: Path) -> None:
    document = tmp_path / "sample.md"
    document.write_text("# 标题\n\n内容", encoding="utf-8")

    assert parse_document_text(document) == "# 标题\n\n内容"


def test_parse_document_text_rejects_unsupported_extension(tmp_path: Path) -> None:
    document = tmp_path / "sample.csv"
    document.write_text("value", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported file type"):
        parse_document_text(document)
