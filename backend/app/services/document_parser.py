import re
from pathlib import Path

from docx import Document
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


def _parse_docx(file_path: Path) -> str:
    document = Document(str(file_path))
    parts: list[str] = []

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if text:
            parts.append(text)

    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                parts.append(" | ".join(cells))

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


class ParsedTable(BaseModel):
    headers: list[str] = []
    rows: list[list[str]] = []
    source_section_order: int = -1


class ParsedDocument(BaseModel):
    sections: list[ParsedSection] = []
    tables: list[ParsedTable] = []
    lead_content: str = ""


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
                    items.append(
                        (current_title, current_level, normalize_text("\n".join(current)))
                    )
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

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        try:
            style = paragraph.style
            style_name = style.name if style is not None else None
        except (AttributeError, KeyError):
            style_name = None
        level = match_heading_style(style_name)
        if level is None and _is_heuristic_heading(paragraph):
            level = 2
        if level is not None:
            if current is not None:
                items.append(
                    (current_title, current_level, normalize_text("\n\n".join(current)))
                )
            current, current_title, current_level = [], text, level
            continue
        target().append(text)

    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                target().append(" | ".join(cells))

    if current is not None:
        items.append((current_title, current_level, normalize_text("\n\n".join(current))))
    return ParsedDocument(
        sections=assign_parent_orders(items),
        lead_content=normalize_text("\n\n".join(lead_lines)),
    )
