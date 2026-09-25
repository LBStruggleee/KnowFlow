from pathlib import Path

import pytest
from pydantic import ValidationError
from app.services.document_parser import (
    ParsedDocument,
    ParsedSection,
    _parse_markdown_structure,
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


def test_markdown_structure_parses_nested_headings() -> None:
    text = "# 第一章\n\n导读\n\n## 1.1 背景\n\n背景正文\n\n### 细节\n\n细则\n\n## 1.2 方法\n\n方法正文\n"

    parsed = _parse_markdown_structure(text)

    assert [section.title for section in parsed.sections] == ["第一章", "1.1 背景", "细节", "1.2 方法"]
    assert [section.level for section in parsed.sections] == [1, 2, 3, 2]
    assert [section.parent_order for section in parsed.sections] == [None, 0, 1, 0]
    assert parsed.sections[0].content == "导读"
    assert parsed.lead_content == ""


def test_markdown_structure_ignores_fenced_code() -> None:
    parsed = _parse_markdown_structure("# 真标题\n\n```python\n# 不是标题\n```\n\n正文\n")

    assert [section.title for section in parsed.sections] == ["真标题"]
    assert "不是标题" in parsed.sections[0].content


def test_markdown_structure_supports_setext_and_nospace_atx() -> None:
    parsed = _parse_markdown_structure("总览\n===\n\n#紧凑标题\n\n内容\n")

    assert [(section.title, section.level) for section in parsed.sections] == [
        ("总览", 1),
        ("紧凑标题", 1),
    ]


def test_markdown_structure_collects_lead_content() -> None:
    parsed = _parse_markdown_structure("前言第一段。\n\n# 第一章\n\n正文\n")

    assert parsed.lead_content == "前言第一段。"
    assert parsed.sections[0].content == "正文"


def test_markdown_structure_without_headings_returns_empty_sections() -> None:
    parsed = _parse_markdown_structure("只有正文，没有标题。\n\n第二段。\n")

    assert parsed.sections == []
    assert parsed.lead_content == "只有正文，没有标题。\n\n第二段。"
