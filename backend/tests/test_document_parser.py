from pathlib import Path

import pytest
from pydantic import ValidationError
from app.services.document_parser import (
    ParsedDocument,
    ParsedSection,
    assign_parent_orders,
    normalize_text,
    parse_document_text,
)


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


def test_assign_parent_orders_builds_nested_tree() -> None:
    sections = assign_parent_orders(
        [
            ("第一章", 1, "章导读"),
            ("1.1 背景", 2, "背景正文"),
            ("1.1.1 定义", 3, "定义正文"),
            ("1.2 方法", 2, "方法正文"),
            ("第二章", 1, ""),
        ]
    )

    assert [section.order for section in sections] == [0, 1, 2, 3, 4]
    assert [section.parent_order for section in sections] == [None, 0, 1, 0, None]
    assert sections[2].content == "定义正文"


def test_assign_parent_orders_tolerates_skipped_levels() -> None:
    sections = assign_parent_orders([("第一章", 1, ""), ("1.1.1 细节", 3, "x")])

    assert sections[1].parent_order == 0


def test_assign_parent_orders_empty_input() -> None:
    assert assign_parent_orders([]) == []


def test_parsed_document_defaults_to_empty() -> None:
    parsed = ParsedDocument()

    assert parsed.sections == []
    assert parsed.tables == []
    assert parsed.lead_content == ""


def test_parsed_section_rejects_level_zero() -> None:
    with pytest.raises(ValidationError):
        ParsedSection(title="x", level=0, order=0, content="")
