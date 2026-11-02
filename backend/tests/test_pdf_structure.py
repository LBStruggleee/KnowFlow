from pathlib import Path

import pytest
from app.services.document_parser import (
    parse_document_structure,
    parse_document_text,
)
from pdf_builder import build_pdf


def _two_chapter_pdf(tmp_path: Path, outline: list[tuple[str, int, int | None]] | None) -> Path:
    return build_pdf(
        tmp_path / "guide.pdf",
        [
            [
                (20.0, "Chapter One"),
                (10.0, "Body of chapter one."),
                (14.0, "1.1 Section A"),
                (10.0, "Body of section A."),
            ],
            [
                (20.0, "Chapter Two"),
                (10.0, "Body of chapter two."),
            ],
        ],
        outline=outline,
    )


def test_pdf_outline_builds_nested_sections(tmp_path: Path) -> None:
    pdf_path = _two_chapter_pdf(
        tmp_path,
        outline=[
            ("Chapter One", 0, None),
            ("1.1 Section A", 0, 0),
            ("Chapter Two", 1, None),
        ],
    )

    parsed = parse_document_structure(pdf_path)

    assert parsed.structure_source == "outline"
    assert [section.title for section in parsed.sections] == [
        "Chapter One",
        "1.1 Section A",
        "Chapter Two",
    ]
    assert [section.level for section in parsed.sections] == [1, 2, 1]
    assert [section.parent_order for section in parsed.sections] == [None, 0, None]
    assert parsed.sections[0].content == "Body of chapter one."
    assert parsed.sections[1].content == "Body of section A."
    assert parsed.sections[2].content == "Body of chapter two."
    assert parsed.lead_content == ""


def test_pdf_font_sizes_produce_heading_levels_without_outline(tmp_path: Path) -> None:
    pdf_path = _two_chapter_pdf(tmp_path, outline=None)

    parsed = parse_document_structure(pdf_path)

    assert parsed.structure_source == "font"
    assert [section.title for section in parsed.sections] == [
        "Chapter One",
        "1.1 Section A",
        "Chapter Two",
    ]
    # 20pt is the largest size class and 14pt the second one.
    assert [section.level for section in parsed.sections] == [1, 2, 1]
    assert parsed.sections[0].content == "Body of chapter one."


def test_pdf_uniform_font_falls_back_to_flat_text(tmp_path: Path) -> None:
    pdf_path = build_pdf(
        tmp_path / "flat.pdf",
        [[(10.0, "First body line."), (10.0, "Second body line.")]],
    )

    parsed = parse_document_structure(pdf_path)

    assert parsed.structure_source == "none"
    assert parsed.sections == []
    assert "First body line." in parsed.lead_content
    assert "Second body line." in parsed.lead_content


def test_pdf_repeated_header_line_is_not_treated_as_heading(tmp_path: Path) -> None:
    pdf_path = build_pdf(
        tmp_path / "headers.pdf",
        [
            [(12.0, "Course Notes Header"), (10.0, "Page one body text.")],
            [(12.0, "Course Notes Header"), (10.0, "Page two body text.")],
        ],
    )

    parsed = parse_document_structure(pdf_path)

    # The 12pt line clears the size ratio, but repeating on every page marks it
    # as a running header, so the document must stay flat.
    assert parsed.structure_source == "none"
    assert parsed.sections == []


def test_pdf_unusable_chinese_outline_falls_back_to_fonts(tmp_path: Path) -> None:
    # Chinese PDFs often surface undecodable bookmarks as "?????"; the parser
    # must not build sections from those titles.
    pdf_path = _two_chapter_pdf(
        tmp_path,
        outline=[("?????", 0, None), ("?????", 1, None)],
    )

    parsed = parse_document_structure(pdf_path)

    assert parsed.structure_source == "font"
    assert [section.title for section in parsed.sections][0] == "Chapter One"


def test_pdf_single_short_page_has_no_structure(tmp_path: Path) -> None:
    # Certificate-style documents: one large line, one smaller line, no body
    # text large enough to establish a body size class.
    pdf_path = build_pdf(
        tmp_path / "certificate.pdf",
        [[(18.0, "Certificate of Completion"), (14.0, "Awarded to Alice.")]],
    )

    parsed = parse_document_structure(pdf_path)

    assert parsed.structure_source == "none"
    assert parsed.sections == []


def test_pdf_without_extractable_text_returns_empty_document(tmp_path: Path) -> None:
    pdf_path = build_pdf(tmp_path / "empty.pdf", [[]])

    parsed = parse_document_structure(pdf_path)

    assert parsed.sections == []
    assert parsed.lead_content == ""
    assert parsed.structure_source == "none"


def test_flat_text_parser_still_reads_pdf_pages(tmp_path: Path) -> None:
    pdf_path = _two_chapter_pdf(tmp_path, outline=None)

    text = parse_document_text(pdf_path)

    assert "Chapter One" in text
    assert "Body of chapter two." in text


def test_unsupported_file_type_is_rejected_before_parsing(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsupported file type"):
        parse_document_structure(tmp_path / "file.xyz")
