"""Deterministic PDF fixtures for the parser tests.

Binary PDFs in git are opaque and hard to review, so the tests build their own:
this module emits uncompressed single-font (Helvetica) PDFs with controlled font
sizes, and can optionally attach an outline through pypdf. That keeps heading
detection assertions exact (a 18pt line really is 18pt) without adding a
runtime dependency or committing opaque blobs.

Only ASCII text is supported: a base-14 font cannot render CJK glyphs, and the
PDF parser's heading heuristics are language-agnostic (they look at size and
line length), so ASCII fixtures test the same code paths.
"""

from pathlib import Path

from pypdf import PdfReader, PdfWriter

PAGE_WIDTH = 595
PAGE_HEIGHT = 842
MARGIN_X = 72
TOP_Y = 770
LEADING_RATIO = 1.4


def build_pdf(
    path: Path,
    pages: list[list[tuple[float, str]]],
    outline: list[tuple[str, int, int | None]] | None = None,
) -> Path:
    """Write a PDF where ``pages[i]`` is a list of ``(font_size, text)`` lines.

    ``outline`` entries are ``(title, page_index, parent_index)`` where
    ``parent_index`` indexes into the same list (``None`` for a top-level item).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_render_pdf(pages))
    if outline:
        _attach_outline(path, outline)
    return path


def _render_pdf(pages: list[list[tuple[float, str]]]) -> bytes:
    page_count = len(pages)
    font_number = 3 + 2 * page_count
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: (
            f"<< /Type /Pages /Kids [{' '.join(f'{3 + 2 * i} 0 R' for i in range(page_count))}] "
            f"/Count {page_count} >>"
        ).encode(),
        font_number: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for index, lines in enumerate(pages):
        content = _page_content(lines)
        objects[3 + 2 * index] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 {font_number} 0 R >> >> /Contents {4 + 2 * index} 0 R >>"
        ).encode()
        objects[4 + 2 * index] = (
            f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream"
        )
    return _serialize(objects, font_number)


def _page_content(lines: list[tuple[float, str]]) -> bytes:
    parts = ["BT"]
    y = TOP_Y
    for size, text in lines:
        y -= size * LEADING_RATIO
        parts.append(f"/F1 {size:.2f} Tf 1 0 0 1 {MARGIN_X} {y:.2f} Tm ({_escape(text)}) Tj")
    parts.append("ET")
    return "\n".join(parts).encode("latin-1")


def _escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _serialize(objects: dict[int, bytes], last_number: int) -> bytes:
    out = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for number in range(1, last_number + 1):
        offsets[number] = len(out)
        out += f"{number} 0 obj\n".encode() + objects[number] + b"\nendobj\n"
    xref_position = len(out)
    out += f"xref\n0 {last_number + 1}\n".encode() + b"0000000000 65535 f \n"
    for number in range(1, last_number + 1):
        out += f"{offsets[number]:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {last_number + 1} /Root 1 0 R >>\nstartxref\n{xref_position}\n%%EOF\n"
    ).encode()
    return bytes(out)


def _attach_outline(path: Path, outline: list[tuple[str, int, int | None]]) -> None:
    reader = PdfReader(str(path))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    parents: dict[int, object] = {}
    for index, (title, page_index, parent_index) in enumerate(outline):
        parent = parents.get(parent_index) if parent_index is not None else None
        parents[index] = writer.add_outline_item(title, page_index, parent=parent)
    with path.open("wb") as handle:
        writer.write(handle)
