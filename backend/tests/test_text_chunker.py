import pytest
from app.services.document_parser import ParsedSection
from app.services.text_chunker import (
    estimate_token_count,
    split_text,
    split_text_structured,
)


def test_split_text_returns_empty_for_blank_input() -> None:
    assert split_text("  \n\n ") == []


def test_split_text_splits_long_text_with_overlap() -> None:
    chunks = split_text("abcdefghij", chunk_size=6, chunk_overlap=2)

    assert chunks == ["abcdef", "efghij"]


@pytest.mark.parametrize(
    ("chunk_size", "chunk_overlap"),
    [(0, 0), (10, -1), (10, 10), (10, 11)],
)
def test_split_text_rejects_invalid_limits(
    chunk_size: int,
    chunk_overlap: int,
) -> None:
    with pytest.raises(ValueError):
        split_text("content", chunk_size=chunk_size, chunk_overlap=chunk_overlap)


def test_estimate_token_count_handles_chinese_and_ascii() -> None:
    assert estimate_token_count("中文abcd") == 3


def _section(title: str, level: int, order: int, content: str) -> ParsedSection:
    parent_order = order - 1 if level > 1 else None
    return ParsedSection(
        title=title, level=level, order=order, parent_order=parent_order, content=content
    )


def test_structured_split_keeps_chunks_within_sections() -> None:
    sections = [
        _section("第一章", 1, 0, "第一段\n\n第二段"),
        _section("第二章", 1, 1, "第三段"),
    ]

    results = split_text_structured(sections, root_content="卷首语")

    assert [(result.content, result.section_order) for result in results] == [
        ("卷首语", -1),
        ("第一段\n\n第二段", 0),
        ("第三段", 1),
    ]
    assert results[0].section_level == 0
    assert results[1].section_level == 1


def test_structured_split_falls_back_to_title_for_empty_content() -> None:
    sections = [_section("纯标题幻灯片", 1, 0, "")]

    results = split_text_structured(sections)

    assert [result.content for result in results] == ["纯标题幻灯片"]
    assert results[0].section_order == 0


def test_structured_split_returns_empty_for_blank_document() -> None:
    assert split_text_structured([], root_content="  \n ") == []


def test_structured_split_rejects_invalid_limits() -> None:
    with pytest.raises(ValueError):
        split_text_structured([], root_content="正文", chunk_size=10, chunk_overlap=10)
