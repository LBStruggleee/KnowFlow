import re
from pathlib import Path
from typing import NamedTuple

from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from pptx import Presentation
from pydantic import BaseModel, Field
from pypdf import PdfReader

SUPPORTED_FILE_TYPES = {".txt", ".md", ".pdf", ".docx", ".pptx"}


def normalize_text(text: str) -> str:
    lines = [line.strip() for line in text.replace("\r\n", "\n").split("\n")]
    cleaned_lines: list[str] = []
    previous_blank = False

    for line in lines:
        is_blank = not line
        if is_blank and previous_blank:
            continue
        cleaned_lines.append(line)
        previous_blank = is_blank

    return "\n".join(cleaned_lines).strip()


def parse_document_text(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix not in SUPPORTED_FILE_TYPES:
        supported = ", ".join(sorted(SUPPORTED_FILE_TYPES))
        raise ValueError(f"Unsupported file type: {suffix}. Supported: {supported}")

    if suffix in {".txt", ".md"}:
        return normalize_text(file_path.read_text(encoding="utf-8"))

    if suffix == ".pdf":
        return normalize_text(_parse_pdf(file_path))

    if suffix == ".docx":
        return normalize_text(_parse_docx(file_path))

    return normalize_text(_parse_pptx(file_path))


def _parse_pdf(file_path: Path) -> str:
    reader = PdfReader(str(file_path))
    page_texts: list[str] = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        if page_text.strip():
            page_texts.append(page_text)
    return "\n\n".join(page_texts)


def _table_row_texts(table: Table) -> list[str]:
    rows: list[str] = []
    for row in table.rows:
        cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
        if cells:
            rows.append(" | ".join(cells))
    return rows


def _iter_docx_body_items(document: DocxDocument):
    """Yield top-level paragraphs and tables in true document order.

    ``document.paragraphs`` and ``document.tables`` are separate lists that
    lose the interleaving; iterating the body element keeps every table at its
    original position between paragraphs. Cell paragraphs live inside the
    table element, so they are never yielded (nor double-counted) here.
    """
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def _parse_docx(file_path: Path) -> str:
    document = Document(str(file_path))
    parts: list[str] = []

    for item in _iter_docx_body_items(document):
        if isinstance(item, Paragraph):
            text = item.text.strip()
            if text:
                parts.append(text)
        else:
            parts.extend(_table_row_texts(item))

    return "\n\n".join(parts)


def _parse_pptx(file_path: Path) -> str:
    presentation = Presentation(str(file_path))
    parts: list[str] = []

    for slide_index, slide in enumerate(presentation.slides, start=1):
        slide_parts: list[str] = []
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False):
                text = shape.text.strip()
                if text:
                    slide_parts.append(text)
            if getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                    if cells:
                        slide_parts.append(" | ".join(cells))

        if slide_parts:
            parts.append(f"Slide {slide_index}\n" + "\n".join(slide_parts))

    return "\n\n".join(parts)


class ParsedSection(BaseModel):
    title: str
    level: int = Field(ge=1, le=9)
    order: int = Field(ge=0)
    parent_order: int | None = None
    content: str = ""


class ParsedDocument(BaseModel):
    sections: list[ParsedSection] = []
    lead_content: str = ""
    # Where the heading tree came from. "none" means the document was parsed as
    # flat text, which keeps the pre-structure behaviour inspectable in logs.
    structure_source: str = "none"


def assign_parent_orders(items: list[tuple[str, int, str]]) -> list[ParsedSection]:
    """Fill order/parent_order for (title, level, content) triples in document order."""
    sections: list[ParsedSection] = []
    stack: list[tuple[int, int]] = []
    for order, (title, level, content) in enumerate(items):
        while stack and stack[-1][0] >= level:
            stack.pop()
        parent_order = stack[-1][1] if stack else None
        sections.append(
            ParsedSection(
                title=title,
                level=level,
                order=order,
                parent_order=parent_order,
                content=content,
            )
        )
        stack.append((level, order))
    return sections


def _match_atx_heading(line: str) -> tuple[int, str]:
    stripped = line.lstrip()
    if not stripped.startswith("#"):
        return 0, ""
    hashes = len(stripped) - len(stripped.lstrip("#"))
    rest = stripped[hashes:]
    if not 1 <= hashes <= 6 or not rest or rest.startswith("#"):
        return 0, ""
    title = re.sub(r"\s+#+\s*$", "", rest.strip())
    if not title:
        return 0, ""
    return hashes, title


def _parse_markdown_structure(text: str) -> ParsedDocument:
    items: list[tuple[str, int, str]] = []
    lead_lines: list[str] = []
    current: list[str] | None = None
    current_title = ""
    current_level = 0
    in_fence = False
    lines = text.split("\n")
    index = 0

    def target() -> list[str]:
        return current if current is not None else lead_lines

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            target().append(line)
            index += 1
            continue
        if not in_fence:
            atx_level, atx_title = _match_atx_heading(line)
            if atx_level:
                if current is not None:
                    items.append((current_title, current_level, normalize_text("\n".join(current))))
                current, current_title, current_level = [], atx_title, atx_level
                index += 1
                continue
            if stripped and index + 1 < len(lines):
                underline = lines[index + 1].strip()
                if re.fullmatch(r"=+", underline) or re.fullmatch(r"-+", underline):
                    if current is not None:
                        items.append(
                            (current_title, current_level, normalize_text("\n".join(current)))
                        )
                    current, current_title = [], stripped
                    current_level = 1 if underline.startswith("=") else 2
                    index += 2
                    continue
        target().append(line)
        index += 1

    if current is not None:
        items.append((current_title, current_level, normalize_text("\n".join(current))))
    return ParsedDocument(
        sections=assign_parent_orders(items),
        lead_content=normalize_text("\n".join(lead_lines)),
    )


HEADING_STYLE_RE = re.compile(r"^(?:Heading|标题)\s*([1-9])$")
HEURISTIC_HEADING_MIN_PT = 14
HEURISTIC_HEADING_MAX_CHARS = 40


def match_heading_style(style_name: str | None) -> int | None:
    if not style_name:
        return None
    if style_name == "Title":
        return 1
    match = HEADING_STYLE_RE.match(style_name.strip())
    return int(match.group(1)) if match else None


def _paragraph_in_table(paragraph) -> bool:
    parent = paragraph._p.getparent()
    while parent is not None:
        if parent.tag.endswith("}tbl"):
            return True
        parent = parent.getparent()
    return False


def _is_heuristic_heading(paragraph) -> bool:
    text = paragraph.text.strip()
    if not text or len(text) > HEURISTIC_HEADING_MAX_CHARS:
        return False
    if _paragraph_in_table(paragraph):
        return False
    runs = [run for run in paragraph.runs if run.text.strip()]
    if not runs or not all(run.bold for run in runs):
        return False
    return all(
        run.font.size is None or run.font.size.pt >= HEURISTIC_HEADING_MIN_PT for run in runs
    )


def _parse_docx_structure(file_path: Path) -> ParsedDocument:
    document = Document(str(file_path))
    items: list[tuple[str, int, str]] = []
    lead_lines: list[str] = []
    current: list[str] | None = None
    current_title = ""
    current_level = 0

    def target() -> list[str]:
        return current if current is not None else lead_lines

    for item in _iter_docx_body_items(document):
        if isinstance(item, Table):
            # Tables are inserted at their original position: rows land in the
            # section that is currently open instead of being appended after
            # every paragraph.
            target().extend(_table_row_texts(item))
            continue
        text = item.text.strip()
        if not text:
            continue
        try:
            style = item.style
            style_name = style.name if style is not None else None
        except (AttributeError, KeyError):
            style_name = None
        level = match_heading_style(style_name)
        if level is None and _is_heuristic_heading(item):
            level = 2
        if level is not None:
            if current is not None:
                items.append((current_title, current_level, normalize_text("\n\n".join(current))))
            current, current_title, current_level = [], text, level
            continue
        target().append(text)

    if current is not None:
        items.append((current_title, current_level, normalize_text("\n\n".join(current))))
    return ParsedDocument(
        sections=assign_parent_orders(items),
        lead_content=normalize_text("\n\n".join(lead_lines)),
    )


def _parse_pptx_structure(file_path: Path) -> ParsedDocument:
    presentation = Presentation(str(file_path))
    items: list[tuple[str, int, str]] = []
    for slide_index, slide in enumerate(presentation.slides, start=1):
        title_shape = slide.shapes.title
        title_text = title_shape.text.strip() if title_shape is not None else ""
        title = title_text or f"Slide {slide_index}"
        parts: list[str] = []
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False):
                text = shape.text.strip()
                if text:
                    parts.append(text)
            if getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                    if cells:
                        parts.append(" | ".join(cells))
        items.append((title, 1, normalize_text("\n".join(parts))))
    return ParsedDocument(sections=assign_parent_orders(items))


# --- PDF structure ------------------------------------------------------
# pypdf exposes per-fragment font metrics through extract_text(visitor_text=...),
# which is what makes heading detection possible without swapping the parser for
# a heavier dependency: no new runtime requirement, and the licence stays MIT.
PDF_HEADING_MAX_CHARS = 80
PDF_HEADING_SIZE_RATIO = 1.15
PDF_HEADING_SIZE_TOLERANCE = 0.05
PDF_MAX_HEADING_RATIO = 0.5


class PdfLine(NamedTuple):
    text: str
    size: float
    page_index: int


def _pdf_page_lines(page, page_index: int) -> list[PdfLine]:
    """Rebuild the visual lines of one page together with each line's font size.

    pypdf already inserts newlines where it decides a line ends, so splitting
    the visitor text on newlines yields reading-order lines while keeping the
    font size that produced them.
    """
    lines: list[PdfLine] = []
    parts: list[str] = []
    sizes: list[float] = []

    def flush() -> None:
        text = " ".join(part for part in parts if part).strip()
        if text:
            lines.append(PdfLine(text=text, size=max(sizes, default=0.0), page_index=page_index))
        parts.clear()
        sizes.clear()

    def visitor(text, cm, tm, font_dict, font_size) -> None:
        if not text:
            return
        for index, chunk in enumerate(text.split("\n")):
            if index:
                flush()
            chunk = chunk.strip()
            if chunk:
                parts.append(chunk)
                sizes.append(float(font_size or 0.0))

    page_text = page.extract_text(visitor_text=visitor)
    flush()
    if not lines and page_text and page_text.strip():
        # No visitor callbacks happened (unusual layout): keep the page as one
        # size-less block so the caller can still fall back to flat text.
        lines.append(PdfLine(text=page_text.strip(), size=0.0, page_index=page_index))
    return lines


def _normalize_line(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _body_font_size(lines: list[PdfLine]) -> float:
    """Char-weighted mode of the font sizes: body text dominates headings."""
    weights: dict[float, int] = {}
    for line in lines:
        if line.size > 0:
            rounded = round(line.size, 1)
            weights[rounded] = weights.get(rounded, 0) + len(line.text)
    if not weights:
        return 0.0
    return max(weights, key=lambda size: (weights[size], size))


def _repeated_line_keys(lines: list[PdfLine]) -> set[str]:
    """Lines that appear on several pages are headers/footers, not headings."""
    pages: dict[str, set[int]] = {}
    for line in lines:
        key = _normalize_line(line.text)
        if 0 < len(key) <= PDF_HEADING_MAX_CHARS:
            pages.setdefault(key, set()).add(line.page_index)
    return {key for key, page_numbers in pages.items() if len(page_numbers) > 1}


def _looks_like_heading(line: PdfLine, body_size: float, repeated: set[str]) -> bool:
    text = line.text.strip()
    if not text or len(text) > PDF_HEADING_MAX_CHARS:
        return False
    if body_size <= 0 or line.size < body_size * PDF_HEADING_SIZE_RATIO:
        return False
    if _normalize_line(text) in repeated or text.isdigit():
        return False
    return bool(re.search(r"[A-Za-z0-9\u4e00-\u9fff]", text))


def _cluster_sizes(sizes: list[float]) -> list[float]:
    """Collapse font sizes within tolerance so one size class means one level."""
    representatives: list[float] = []
    for size in sorted(set(sizes), reverse=True):
        if (
            not representatives
            or abs(size - representatives[-1]) / representatives[-1] > PDF_HEADING_SIZE_TOLERANCE
        ):
            representatives.append(size)
    return representatives


def _level_for_size(size: float, representatives: list[float]) -> int:
    for level, representative in enumerate(representatives, start=1):
        if abs(size - representative) / representative <= PDF_HEADING_SIZE_TOLERANCE:
            return min(level, 6)
    return min(len(representatives) + 1, 6)


def _pdf_font_structure(lines: list[PdfLine]) -> ParsedDocument:
    """Derive a heading tree from font sizes when no usable outline exists."""
    full_text = normalize_text("\n".join(line.text for line in lines))
    body_size = _body_font_size(lines)
    if body_size <= 0:
        return ParsedDocument(lead_content=full_text)

    repeated = _repeated_line_keys(lines)
    heading_sizes = [line.size for line in lines if _looks_like_heading(line, body_size, repeated)]
    if not heading_sizes or len(heading_sizes) > len(lines) * PDF_MAX_HEADING_RATIO:
        return ParsedDocument(lead_content=full_text)

    representatives = _cluster_sizes(heading_sizes)
    items: list[tuple[str, int, str]] = []
    lead_lines: list[str] = []
    current: list[str] | None = None
    current_title = ""
    current_level = 0
    for line in lines:
        if _looks_like_heading(line, body_size, repeated):
            if current is not None:
                items.append((current_title, current_level, normalize_text("\n".join(current))))
            current = []
            current_title = line.text.strip()
            current_level = _level_for_size(line.size, representatives)
            continue
        (current if current is not None else lead_lines).append(line.text)
    if current is not None:
        items.append((current_title, current_level, normalize_text("\n".join(current))))
    if not items:
        return ParsedDocument(lead_content=full_text)
    return ParsedDocument(
        sections=assign_parent_orders(items),
        lead_content=normalize_text("\n".join(lead_lines)),
        structure_source="font",
    )


def _pdf_outline_entries(reader: PdfReader) -> list[tuple[str, int, int]] | None:
    """Return ``(title, page_index, depth)`` for usable bookmarks, else ``None``."""
    try:
        outline = reader.outline
    except Exception:
        return None
    if not outline:
        return None

    entries: list[tuple[str, int, int]] = []

    def walk(items, depth: int) -> None:
        for item in items:
            if isinstance(item, list):
                walk(item, depth + 1)
                continue
            title = str(getattr(item, "title", "") or "").strip()
            page_index = None
            try:
                page = item.page
                if page is not None:
                    page_index = reader.get_page_number(page)
            except Exception:
                page_index = None
            if title and page_index is not None:
                entries.append((title, page_index, depth))

    walk(outline, 0)
    if len(entries) < 2:
        return None
    if any(not re.search(r"[A-Za-z0-9\u4e00-\u9fff]", title) for title, _, _ in entries):
        # Chinese PDFs often produce "?????" here when the outline uses a
        # non-Unicode encoding; font-size detection is the better fallback.
        return None
    return entries


def _pdf_outline_structure(reader: PdfReader, lines: list[PdfLine]) -> ParsedDocument | None:
    """Build sections from bookmarks, anchoring each title to its text line."""
    entries = _pdf_outline_entries(reader)
    if entries is None or not lines:
        return None

    normalized = [_normalize_line(line.text) for line in lines]
    positions: list[tuple[int, str, int]] = []
    search_from = 0
    for title, page_index, depth in entries:
        key = _normalize_line(title)
        found: int | None = None
        for index in range(search_from, len(lines)):
            candidate = normalized[index]
            if len(candidate) < 3:
                continue
            if candidate.startswith(key) or key.startswith(candidate):
                found = index
                break
        if found is None and 0 <= page_index < len(reader.pages):
            for index in range(search_from, len(lines)):
                if lines[index].page_index == page_index:
                    found = index
                    break
        if found is None:
            return None
        positions.append((found, title, min(depth + 1, 6)))
        search_from = found

    positions.sort(key=lambda item: item[0])
    items: list[tuple[str, int, str]] = []
    lead_lines = [line.text for line in lines[: positions[0][0]]]
    for index, (start, title, level) in enumerate(positions):
        end = positions[index + 1][0] if index + 1 < len(positions) else len(lines)
        body = "\n".join(line.text for line in lines[start + 1 : end])
        items.append((title, level, normalize_text(body)))
    return ParsedDocument(
        sections=assign_parent_orders(items),
        lead_content=normalize_text("\n".join(lead_lines)),
        structure_source="outline",
    )


def _parse_pdf_structure(file_path: Path) -> ParsedDocument:
    reader = PdfReader(str(file_path))
    lines: list[PdfLine] = []
    for page_index, page in enumerate(reader.pages):
        lines.extend(_pdf_page_lines(page, page_index))
    if not lines:
        return ParsedDocument()

    parsed = _pdf_outline_structure(reader, lines)
    if parsed is not None and parsed.sections:
        return parsed
    return _pdf_font_structure(lines)


def parse_document_structure(file_path: Path) -> ParsedDocument:
    suffix = file_path.suffix.lower()
    if suffix not in SUPPORTED_FILE_TYPES:
        supported = ", ".join(sorted(SUPPORTED_FILE_TYPES))
        raise ValueError(f"Unsupported file type: {suffix}. Supported: {supported}")

    if suffix == ".md":
        return _parse_markdown_structure(file_path.read_text(encoding="utf-8"))
    if suffix == ".pdf":
        return _parse_pdf_structure(file_path)
    if suffix == ".docx":
        return _parse_docx_structure(file_path)
    if suffix == ".pptx":
        return _parse_pptx_structure(file_path)
    return ParsedDocument(lead_content=parse_document_text(file_path))
