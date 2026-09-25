# Phase 1：层级化 Section 模型 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 解析器输出结构化文档树并落盘 `document_section` 表，每个 chunk 归属一个 section 且检索/问答结果携带 `section_path`。

**Architecture:** 解析层输出 `ParsedDocument`（sections 自带 `parent_order`，解析器内层级栈算法填充）；落盘层只做持久化与 `section_path` 拼接；chunker 按 section 独立切分（空正文回退用标题）；Chroma metadata 追加 `section_path`；API 只加字段不删字段。

**Tech Stack:** Python 3.13、FastAPI、SQLAlchemy 2.0、Pydantic v2（经由 fastapi 依赖）、python-docx、pypdf、python-pptx、pytest、Vitest。零新增依赖。

**Spec:** `docs/superpowers/specs/2026-09-24-phase1-section-model-design.md`（已含 `lead_content` 与标题回退两处修订）

## Global Constraints

1. 后端默认监听 `127.0.0.1`，不引入 Redis / PostgreSQL / 对象存储 / Celery。
2. SQLite 是事实源，Chroma 是可重建索引；任何改动不能让 Chroma 成为单点事实来源。
3. API Key 只在 `backend/.env`，不提交 Git；新代码不得硬编码密钥或模型名。
4. `/api/chat`、`/api/kbs/{kb_id}/search`、`/api/documents/{id}/chunks` 的现有响应字段不能删除或改名，只能新增字段。
5. 每任务自带测试；后端 pytest、Ruff 检查、`ruff format`、`python -m compileall` 必须通过；前端改动追加 Vitest 与 `npm run build`。
6. 每个 Task 一个 Git commit，message 用 `feat:`/`refactor:`/`test:`/`docs:` 前缀。
7. 无有效 `DASHSCOPE_API_KEY` 时所有新功能必须可降级，离线开发与测试不能被云端 API 阻塞。
8. 保留 `parse_document_text()` 与 `split_text()` 原函数不变（降级路径与旧测试继续用）。
9. 测试命令一律从仓库根目录执行：后端 `$env:PYTHONPATH="backend"; pytest backend/tests/<file> -v`（PowerShell）。

## Review Focus

1. 中文 docx 模板样式名为"标题 1"而非"Heading 1" → 双重正则，Task 3 的 `test_match_heading_style_handles_chinese_and_english_names` 锁定。
2. 加粗的表格说明/重点提示被误判为标题 → 四条护栏，Task 3 的 `test_docx_structure_rejects_bold_non_headings`（表格内/超长/非加粗三反例）锁定。
3. md 代码围栏内的 `#` 行 → fence 跟踪，Task 2 的 `test_markdown_structure_ignores_fenced_code` 锁定。
4. 无标题文档（txt/PDF/纯正文 md）→ 单 Root 回退，Task 4 的 `test_parse_structure_falls_back_to_single_root` 锁定。
5. 处理失败或 retry 时 section 残留/重复建树 → 幂等清理，Task 7 的 `test_process_cleans_sections_on_vector_failure` 与 Task 9 的重建/删除断言锁定。

---

### Task 1: 结构模型与层级栈纯函数

**Files:**
- Modify: `backend/app/services/document_parser.py`（文件顶部追加 `from pydantic import BaseModel, Field`；文件末尾追加模型与 `assign_parent_orders`；现有 91 行不动）
- Test: `backend/tests/test_document_parser.py`（末尾追加）

**Interfaces:**
- Consumes: 无（首个任务；复用现有 `normalize_text` 的行为约定）。
- Produces: `ParsedSection(title, level, order, parent_order, content)`（`level` 限 1–9，`order` ≥ 0）；`ParsedTable(headers, rows, source_section_order)`；`ParsedDocument(sections, tables, lead_content)`；`assign_parent_orders(items: list[tuple[str, int, str]]) -> list[ParsedSection]`（输入为文档顺序的 `(title, level, content)` 三元组；用 `(level, order)` 栈填充 `order` 与 `parent_order`，栈空则 `parent_order=None`，跳级直接挂栈顶）。

- [ ] **Step 1: Write the failing tests**

```python
from pydantic import ValidationError
from app.services.document_parser import (
    ParsedDocument,
    ParsedSection,
    assign_parent_orders,
)


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH="backend"; pytest backend/tests/test_document_parser.py -v`
Expected: FAIL with "cannot import name 'ParsedDocument'"（5 个新测试全部因导入失败而 error）。

- [ ] **Step 3: Write minimal implementation**

文件顶部 import 区追加一行（放在现有 `from pathlib import Path` 之后）：

```python
from pydantic import BaseModel, Field
```

文件末尾追加：

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONPATH="backend"; pytest backend/tests/test_document_parser.py -v`
Expected: PASS（8 个测试：3 个旧测试 + 5 个新测试）。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/document_parser.py backend/tests/test_document_parser.py
git commit -m "feat: add ParsedDocument models and hierarchy stack helper"
```

---

### Task 2: Markdown 结构解析

**Files:**
- Modify: `backend/app/services/document_parser.py`（顶部追加 `import re`；末尾追加 `_match_atx_heading` 与 `_parse_markdown_structure`）
- Test: `backend/tests/test_document_parser.py`（末尾追加）

**Interfaces:**
- Consumes: Task 1 的 `assign_parent_orders`、`ParsedDocument`、`normalize_text`（已存在）。
- Produces: `_parse_markdown_structure(text: str) -> ParsedDocument`；`_match_atx_heading(line: str) -> tuple[int, str]`（返回 `(level, title)`，非标题行返回 `(0, "")`）。

约定（测试锁定的行为）：ATX 允许 `#` 后有或无空格（中文讲义常写 `#标题`），但 `#` 独占一行或 `#######`（7 个以上）不是标题；行尾 `##` 闭合符要剥掉；setext `===`→level 1、`---`→level 2（仅当前行非空且紧邻下一行是下划线时）；围栏内（``` / ~~~ 配对翻转）所有行都是正文。

- [ ] **Step 1: Write the failing tests**

```python
from app.services.document_parser import _parse_markdown_structure


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH="backend"; pytest backend/tests/test_document_parser.py -v -k markdown_structure`
Expected: FAIL with "cannot import name '_parse_markdown_structure'"。

- [ ] **Step 3: Write minimal implementation**

文件顶部追加 `import re`（放在 `from pathlib import Path` 之前，按 stdlib 字母序）。文件末尾追加：

```python
def _match_atx_heading(line: str) -> tuple[int, str]:
    stripped = line.lstrip()
    if not stripped.startswith("#"):
        return 0, ""
    hashes = len(stripped) - len(stripped.lstrip("#"))
    rest = stripped[hashes:]
    if not 1 <= hashes <= 6 or not rest or rest.startswith("#"):
        return 0, ""
    if rest[0] not in (" ", "\t"):
        title = rest.strip()
    else:
        title = rest.strip()
    title = re.sub(r"\s+#+\s*$", "", title)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONPATH="backend"; pytest backend/tests/test_document_parser.py -v`
Expected: PASS（全部 13 个测试）。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/document_parser.py backend/tests/test_document_parser.py
git commit -m "feat: parse markdown heading structure with fence awareness"
```

---

### Task 3: docx 结构解析（含中文样式名与加粗启发式）

**Files:**
- Modify: `backend/app/services/document_parser.py`（末尾追加 `HEADING_STYLE_RE`、`HEURISTIC_HEADING_MIN_PT`、`HEURISTIC_HEADING_MAX_CHARS`、`match_heading_style`、`_paragraph_in_table`、`_is_heuristic_heading`、`_parse_docx_structure`）
- Test: `backend/tests/test_document_parser.py`（末尾追加；用 python-docx 现场生成测试文档，不提交二进制 fixture）

**Interfaces:**
- Consumes: Task 1 的 `assign_parent_orders`、`ParsedDocument`；现有 `_parse_docx` 保持不动。
- Produces: `match_heading_style(style_name: str | None) -> int | None`（`"Heading N"`/`"标题 N"`→N，`"Title"`→1，其余/空/None→None）；`_parse_docx_structure(path: Path) -> ParsedDocument`（正文段落按标题切分；表格沿用 V1 拍平 `" | "` 行为追加到当前 section；样式读取异常按无标题处理）。

加粗启发式四条护栏（必须同时满足，level 固定为 2）：无标题样式；全部非空 run 加粗；字号缺失或 ≥14pt；文本 ≤40 字；不在表格内。

- [ ] **Step 1: Write the failing tests**

```python
from docx import Document as DocxDocument
from docx.enum.style import WD_STYLE_TYPE
from docx.shared import Pt
from app.services.document_parser import _parse_docx_structure, match_heading_style


def test_match_heading_style_handles_chinese_and_english_names() -> None:
    assert match_heading_style("Heading 1") == 1
    assert match_heading_style("标题 2") == 2
    assert match_heading_style("标题9") == 9
    assert match_heading_style("Title") == 1
    assert match_heading_style("Normal") is None
    assert match_heading_style("Heading 10") is None
    assert match_heading_style(None) is None
    assert match_heading_style("") is None


def test_docx_structure_parses_mixed_styles(tmp_path: Path) -> None:
    path = tmp_path / "lesson.docx"
    document = DocxDocument()
    document.add_paragraph("课程导读")
    document.add_paragraph("第一章", style="Heading 1")
    document.add_paragraph("章导读")
    document.add_paragraph("1.1 背景", style="Heading 2")
    document.add_paragraph("背景正文")
    document.save(path)

    parsed = _parse_docx_structure(path)

    assert [section.title for section in parsed.sections] == ["第一章", "1.1 背景"]
    assert [section.parent_order for section in parsed.sections] == [None, 0]
    assert parsed.lead_content == "课程导读"
    assert parsed.sections[0].content == "章导读"


def test_docx_structure_matches_chinese_style_name(tmp_path: Path) -> None:
    path = tmp_path / "chinese.docx"
    document = DocxDocument()
    style = document.styles.add_style("标题 1", WD_STYLE_TYPE.PARAGRAPH)
    document.add_paragraph("第一章", style=style)
    document.add_paragraph("正文")
    document.save(path)

    parsed = _parse_docx_structure(path)

    assert [(section.title, section.level) for section in parsed.sections] == [("第一章", 1)]


def test_docx_structure_detects_bold_heuristic_heading(tmp_path: Path) -> None:
    path = tmp_path / "heuristic.docx"
    document = DocxDocument()
    document.add_paragraph("第一章", style="Heading 1")
    paragraph = document.add_paragraph()
    run = paragraph.add_run("加粗小节")
    run.bold = True
    run.font.size = Pt(16)
    document.add_paragraph("小节正文")
    document.save(path)

    parsed = _parse_docx_structure(path)

    assert [(section.title, section.level) for section in parsed.sections] == [
        ("第一章", 1),
        ("加粗小节", 2),
    ]
    assert parsed.sections[1].parent_order == 0


def test_docx_structure_rejects_bold_non_headings(tmp_path: Path) -> None:
    path = tmp_path / "bold-noise.docx"
    document = DocxDocument()
    long_bold = document.add_paragraph()
    long_run = long_bold.add_run("这是一段很长的加粗文字，超过四十个字符，不应被识别为标题内容填充")
    long_run.bold = True
    plain = document.add_paragraph()
    plain_run = plain.add_run("未加粗的大字号文字")
    plain_run.font.size = Pt(18)
    table = document.add_table(rows=1, cols=1)
    caption = table.cell(0, 0).paragraphs[0]
    caption_run = caption.add_run("表格内的加粗说明")
    caption_run.bold = True
    caption_run.font.size = Pt(16)
    document.save(path)

    parsed = _parse_docx_structure(path)

    assert parsed.sections == []
    assert "表格内的加粗说明" in parsed.lead_content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH="backend"; pytest backend/tests/test_document_parser.py -v -k "docx_structure or match_heading"`
Expected: FAIL with "cannot import name 'match_heading_style'"。

- [ ] **Step 3: Write minimal implementation**

文件末尾追加：

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONPATH="backend"; pytest backend/tests/test_document_parser.py -v`
Expected: PASS（全部测试，含 5 个 docx 新测试）。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/document_parser.py backend/tests/test_document_parser.py
git commit -m "feat: parse docx heading structure with bold heuristic"
```

---

### Task 4: pptx 结构解析与 parse_document_structure 总装

**Files:**
- Modify: `backend/app/services/document_parser.py`（末尾追加 `_parse_pptx_structure` 与 `parse_document_structure`）
- Test: `backend/tests/test_document_parser.py`（末尾追加）

**Interfaces:**
- Consumes: Task 2/3 的各格式解析函数；现有 `parse_document_text`（txt/pdf 回退复用它，保证文本提取单一来源）。
- Produces: `parse_document_structure(file_path: Path) -> ParsedDocument`（`.md`→markdown 结构；`.docx`→docx 结构；`.pptx`→每 slide 一个 level-1 section，title 取标题占位符否则 `Slide N`；`.txt`/`.pdf`→`sections=[]` 且全文进 `lead_content`；不支持后缀→与 `parse_document_text` 相同的 ValueError 文案）。

- [ ] **Step 1: Write the failing tests**

```python
from pptx import Presentation
from pypdf import PdfWriter
from app.services.document_parser import parse_document_structure


def test_pptx_structure_creates_one_section_per_slide(tmp_path: Path) -> None:
    path = tmp_path / "deck.pptx"
    presentation = Presentation()
    blank_layout = presentation.slide_layouts[6]
    first = presentation.slides.add_slide(blank_layout)
    first.shapes.title.text = "课程目标"
    first.placeholders[1].text = "掌握 RAG 原理"
    second = presentation.slides.add_slide(blank_layout)
    second.placeholders[1].text = "只有正文没有标题"
    presentation.save(path)

    parsed = parse_document_structure(path)

    assert [(section.title, section.level) for section in parsed.sections] == [
        ("课程目标", 1),
        ("Slide 2", 1),
    ]
    assert parsed.sections[0].content == "课程目标\n掌握 RAG 原理"
    assert parsed.lead_content == ""


def test_parse_structure_dispatches_markdown(tmp_path: Path) -> None:
    document = tmp_path / "note.md"
    document.write_text("# 第一章\n\n正文\n", encoding="utf-8")

    parsed = parse_document_structure(document)

    assert [section.title for section in parsed.sections] == ["第一章"]


def test_parse_structure_falls_back_to_single_root(tmp_path: Path) -> None:
    text_file = tmp_path / "plain.txt"
    text_file.write_text("第一段\n\n第二段", encoding="utf-8")
    pdf_file = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with pdf_file.open("wb") as handle:
        writer.write(handle)

    text_parsed = parse_document_structure(text_file)
    pdf_parsed = parse_document_structure(pdf_file)

    assert text_parsed.sections == []
    assert text_parsed.lead_content == "第一段\n\n第二段"
    assert pdf_parsed.sections == []
    assert pdf_parsed.lead_content == ""


def test_parse_structure_rejects_unsupported_extension(tmp_path: Path) -> None:
    document = tmp_path / "sample.csv"
    document.write_text("value", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported file type"):
        parse_document_structure(document)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH="backend"; pytest backend/tests/test_document_parser.py -v -k "parse_structure or pptx_structure"`
Expected: FAIL with "cannot import name 'parse_document_structure'"。

- [ ] **Step 3: Write minimal implementation**

文件末尾追加：

```python
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


def parse_document_structure(file_path: Path) -> ParsedDocument:
    suffix = file_path.suffix.lower()
    if suffix not in SUPPORTED_FILE_TYPES:
        supported = ", ".join(sorted(SUPPORTED_FILE_TYPES))
        raise ValueError(f"Unsupported file type: {suffix}. Supported: {supported}")

    if suffix == ".md":
        return _parse_markdown_structure(file_path.read_text(encoding="utf-8"))
    if suffix == ".docx":
        return _parse_docx_structure(file_path)
    if suffix == ".pptx":
        return _parse_pptx_structure(file_path)
    return ParsedDocument(lead_content=parse_document_text(file_path))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONPATH="backend"; pytest backend/tests/test_document_parser.py -v`
Expected: PASS（全部测试）。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/document_parser.py backend/tests/test_document_parser.py
git commit -m "feat: add parse_document_structure dispatch with pptx and text fallback"
```

---

### Task 5: 数据模型（DocumentSection + chunk.section_id）

**Files:**
- Create: `backend/app/models/document_section.py`
- Modify: `backend/app/models/document_chunk.py`（追加 `section_id` 列）、`backend/app/models/__init__.py`（注册导出）
- Test: Create `backend/tests/test_document_section.py`

**Interfaces:**
- Consumes: 无（独立建模；`document.id` 外键目标已存在）。
- Produces: `DocumentSection`（`document_id` FK CASCADE；`parent_section_id` 自引用 FK CASCADE nullable；`title` String(500)；`section_path` Text；`section_level/section_order/chunk_count` Integer；`summary` Text 恒空预留；`created_at`）；`DocumentChunk.section_id`（FK→document_section nullable index CASCADE）；`main.py:30` 的 `create_all` 自动建表，无需迁移代码。

- [ ] **Step 1: Write the failing tests**

```python
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_section import DocumentSection
from app.models.knowledge_base import KnowledgeBase
from sqlalchemy import select
from sqlalchemy.orm import Session


def _create_document(db_session: Session) -> Document:
    knowledge_base = KnowledgeBase(name="结构化课程", description="", category="大数据")
    db_session.add(knowledge_base)
    db_session.flush()
    document = Document(
        kb_id=knowledge_base.id,
        title="大数据导论",
        file_name="大数据导论.md",
        file_path="/tmp/大数据导论.md",
        file_type="md",
        status="finished",
    )
    db_session.add(document)
    db_session.flush()
    return document


def test_section_tree_persists_with_parent_links(db_session: Session) -> None:
    document = _create_document(db_session)
    root = DocumentSection(
        document_id=document.id,
        parent_section_id=None,
        title="大数据导论",
        section_path="大数据导论",
        section_level=0,
        section_order=0,
    )
    db_session.add(root)
    db_session.flush()
    child = DocumentSection(
        document_id=document.id,
        parent_section_id=root.id,
        title="第一章",
        section_path="大数据导论 / 第一章",
        section_level=1,
        section_order=1,
    )
    db_session.add(child)
    db_session.commit()

    rows = db_session.scalars(
        select(DocumentSection).order_by(DocumentSection.section_order)
    ).all()
    assert [row.title for row in rows] == ["大数据导论", "第一章"]
    assert rows[1].parent_section_id == rows[0].id


def test_chunk_allows_null_section_id_for_legacy_data(db_session: Session) -> None:
    document = _create_document(db_session)
    chunk = DocumentChunk(
        kb_id=document.kb_id,
        document_id=document.id,
        chunk_index=0,
        content="老数据正文",
        token_count=6,
        section_id=None,
    )
    db_session.add(chunk)
    db_session.commit()

    assert chunk.id is not None
    assert chunk.section_id is None


def test_section_cascade_on_document_delete(db_session: Session) -> None:
    document = _create_document(db_session)
    root = DocumentSection(
        document_id=document.id,
        title="大数据导论",
        section_path="大数据导论",
        section_level=0,
        section_order=0,
    )
    db_session.add(root)
    db_session.flush()
    db_session.add(
        DocumentChunk(
            kb_id=document.kb_id,
            document_id=document.id,
            chunk_index=0,
            content="正文",
            token_count=2,
            section_id=root.id,
        )
    )
    db_session.commit()

    db_session.delete(document)
    db_session.commit()

    assert db_session.scalars(select(DocumentSection)).all() == []
    assert db_session.scalars(select(DocumentChunk)).all() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH="backend"; pytest backend/tests/test_document_section.py -v`
Expected: FAIL with "No module named 'app.models.document_section'"（conftest 收集即报错）。

- [ ] **Step 3: Write minimal implementation**

新建 `backend/app/models/document_section.py`：

```python
from datetime import datetime

from app.core.database import Base
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column


class DocumentSection(Base):
    __tablename__ = "document_section"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), index=True
    )
    parent_section_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_section.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500))
    section_path: Mapped[str] = mapped_column(Text, default="")
    section_level: Mapped[int] = mapped_column(Integer, default=0)
    section_order: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
```

`backend/app/models/document_chunk.py` 在 `token_count` 行后追加：

```python
    section_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_section.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
```

`backend/app/models/__init__.py` 追加 `from app.models.document_section import DocumentSection` 与 `__all__` 中的 `"DocumentSection"`（按字母序放在 `DocumentChunk` 之后、`KnowledgeBase` 之前）。

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONPATH="backend"; pytest backend/tests/test_document_section.py -v`
Expected: PASS（3 个测试；内存库 `create_all` 自动建表，级联删除依赖外键 PRAGMA，conftest 已启用）。

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/document_section.py backend/app/models/document_chunk.py backend/app/models/__init__.py backend/tests/test_document_section.py
git commit -m "feat: add DocumentSection model and chunk section link"
```

---

### Task 6: split_text_structured（按 section 独立切分）

**Files:**
- Modify: `backend/app/services/text_chunker.py`（顶部追加 `from pydantic import BaseModel` 与 `from app.services.document_parser import ParsedSection`；末尾追加 `ChunkResult` 与 `split_text_structured`）
- Test: `backend/tests/test_text_chunker.py`（末尾追加）

**Interfaces:**
- Consumes: Task 1 的 `ParsedSection`；现有 `split_text`（含 800/150 默认与参数校验）。
- Produces: `ChunkResult(content, section_order=-1, section_level=0)`；`split_text_structured(sections, root_content="", chunk_size, chunk_overlap) -> list[ChunkResult]`（Root 内容先输出；每个 section 独立切分不跨界合并；`section.content` 为空回退用标题；空 section 列表且空 root 返回 `[]`；非法 limits 透传 `split_text` 的 ValueError）。

- [ ] **Step 1: Write the failing tests**

```python
from app.services.document_parser import ParsedSection
from app.services.text_chunker import ChunkResult, split_text_structured


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH="backend"; pytest backend/tests/test_text_chunker.py -v -k structured_split`
Expected: FAIL with "cannot import name 'ChunkResult'"。

- [ ] **Step 3: Write minimal implementation**

文件顶部追加（放在 `DEFAULT_CHUNK_OVERLAP` 定义之前）：

```python
from pydantic import BaseModel

from app.services.document_parser import ParsedSection
```

文件末尾追加：

```python
class ChunkResult(BaseModel):
    content: str
    section_order: int = -1
    section_level: int = 0


def split_text_structured(
    sections: list[ParsedSection],
    root_content: str = "",
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[ChunkResult]:
    results: list[ChunkResult] = []
    for content in split_text(root_content, chunk_size=chunk_size, chunk_overlap=chunk_overlap):
        results.append(ChunkResult(content=content, section_order=-1, section_level=0))
    for section in sections:
        body = section.content if section.content.strip() else section.title
        for content in split_text(body, chunk_size=chunk_size, chunk_overlap=chunk_overlap):
            results.append(
                ChunkResult(
                    content=content,
                    section_order=section.order,
                    section_level=section.level,
                )
            )
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONPATH="backend"; pytest backend/tests/test_text_chunker.py -v`
Expected: PASS（全部测试，含 4 个新测试）。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/text_chunker.py backend/tests/test_text_chunker.py
git commit -m "feat: split text per section with title fallback"
```

---

### Task 7: 落盘流程改造（建树 + 归属 + 清理）

**Files:**
- Modify: `backend/app/services/document_processing_service.py`（import 区追加 `ParsedDocument`、`DocumentSection`、`split_text_structured`；追加 `clear_document_sections` 与 `_persist_section_tree`；重写 `process_document_record` 主流程与异常补偿；`reset_document_for_retry` 追加 section 清理）
- Modify: `backend/tests/test_api.py`（`test_failed_document_can_be_retried` 的 monkeypatch 从 `parse_document_text` 改为 `parse_document_structure`，见 Step 3）
- Test: Create `backend/tests/test_section_pipeline.py`（落盘端到端）

**Interfaces:**
- Consumes: Task 4 的 `parse_document_structure`；Task 5 的 `DocumentSection`；Task 6 的 `split_text_structured`；现有 `vector_store_service.add_chunks(document_chunks)`（单参数调用保持不变，Task 8 再扩展）。
- Produces: `clear_document_sections(db: Session, document_id: int) -> None`（按 document_id 批量删除 section 行，幂等）；`_persist_section_tree(db, document, root_title, parsed: ParsedDocument) -> dict[int, DocumentSection]`（建 Root + 子树，返回 `ParsedSection.order → DocumentSection` 映射，键 `-1` 为 Root；`parent_order=None` 或查不到时挂 Root）；改造后的 `process_document_record`（无可读文本仍抛 `ValueError("No readable text was extracted from the document.")`；`content_length` 为全部 chunk 字符数之和；`content_preview` 取首个 chunk 前 500 字；失败时补偿删除向量 + chunk 行 + section 行）。

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_section import DocumentSection
from app.models.knowledge_base import KnowledgeBase
from app.services import document_processing_service
from app.services.document_processing_service import (
    clear_document_sections,
    process_document_record,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def _create_finished_document(
    db_session: Session, tmp_path: Path, name: str, text: str
) -> Document:
    knowledge_base = KnowledgeBase(name=f"KB-{name}", description="", category="大数据")
    db_session.add(knowledge_base)
    db_session.flush()
    file_path = tmp_path / f"{name}.md"
    file_path.write_text(text, encoding="utf-8")
    document = Document(
        kb_id=knowledge_base.id,
        title=name,
        file_name=f"{name}.md",
        file_path=str(file_path),
        file_type="md",
        status="processing",
    )
    db_session.add(document)
    db_session.commit()
    return document


def test_process_builds_section_tree_and_chunk_links(
    db_session: Session, monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        document_processing_service.vector_store_service, "add_chunks", lambda _chunks: None
    )
    document = _create_finished_document(
        db_session, tmp_path, "大数据导论", "卷首语\n\n# 第一章\n\n章导读\n\n## 1.1 背景\n\n背景正文\n"
    )

    process_document_record(db_session, document.id)

    sections = db_session.scalars(
        select(DocumentSection).order_by(DocumentSection.section_order)
    ).all()
    assert [section.section_path for section in sections] == [
        "大数据导论",
        "大数据导论 / 第一章",
        "大数据导论 / 第一章 / 1.1 背景",
    ]
    assert sections[1].parent_section_id == sections[0].id
    assert sections[2].parent_section_id == sections[1].id
    chunks = db_session.scalars(
        select(DocumentChunk).order_by(DocumentChunk.chunk_index)
    ).all()
    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2, 3]
    by_title = {section.title: section for section in sections}
    assert chunks[0].section_id == by_title["大数据导论"].id
    assert chunks[1].section_id == by_title["第一章"].id
    assert [section.chunk_count for section in sections] == [1, 1, 2]
    assert db_session.get(Document, document.id).status == "finished"


def test_process_cleans_sections_on_vector_failure(
    db_session: Session, monkeypatch, tmp_path: Path
) -> None:
    def _boom(_chunks):
        raise RuntimeError("chroma down")

    monkeypatch.setattr(
        document_processing_service.vector_store_service, "add_chunks", _boom
    )
    document = _create_finished_document(db_session, tmp_path, "失败文档", "# 第一章\n\n正文\n")

    process_document_record(db_session, document.id)

    assert db_session.scalars(select(DocumentSection)).all() == []
    assert db_session.scalars(select(DocumentChunk)).all() == []
    assert db_session.get(Document, document.id).status == "failed"


def test_clear_document_sections_is_idempotent(db_session: Session, tmp_path: Path) -> None:
    document = _create_finished_document(db_session, tmp_path, "幂等", "# 第一章\n\n正文\n")

    clear_document_sections(db_session, document.id)
    clear_document_sections(db_session, document.id)

    assert db_session.scalars(select(DocumentSection)).all() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH="backend"; pytest backend/tests/test_section_pipeline.py -v`
Expected: FAIL with "No module named '...test_section_pipeline'"？不——文件新建后收集成功，但 `cannot import name 'clear_document_sections'"`（3 个测试全部 error）。

- [ ] **Step 3: Write minimal implementation**

`document_processing_service.py` import 区追加（按字母序插入现有 import 之后）：

```python
from app.models.document_section import DocumentSection
from app.services.document_parser import ParsedDocument, parse_document_structure
from app.services.text_chunker import estimate_token_count, split_text_structured
```

原 `from app.services.text_chunker import estimate_token_count, split_text` 改为上述行（`split_text` 不再被本文件使用）。

追加新函数（放在 `process_document_record` 之前）：

```python
def clear_document_sections(db: Session, document_id: int) -> None:
    """Delete all section rows of one document. Idempotent."""
    db.query(DocumentSection).filter(DocumentSection.document_id == document_id).delete()


def _persist_section_tree(
    db: Session,
    document: Document,
    root_title: str,
    parsed: ParsedDocument,
) -> dict[int, DocumentSection]:
    by_order: dict[int, DocumentSection] = {}
    root = DocumentSection(
        document_id=document.id,
        parent_section_id=None,
        title=root_title,
        section_path=root_title,
        section_level=0,
        section_order=0,
        chunk_count=0,
        summary="",
    )
    db.add(root)
    db.flush()
    by_order[-1] = root
    order_counter = 1
    for section in parsed.sections:
        if section.parent_order is None:
            parent = root
        else:
            parent = by_order.get(section.parent_order, root)
        node = DocumentSection(
            document_id=document.id,
            parent_section_id=parent.id,
            title=section.title,
            section_path=f"{parent.section_path} / {section.title}",
            section_level=section.level,
            section_order=order_counter,
            chunk_count=0,
            summary="",
        )
        db.add(node)
        db.flush()
        by_order[section.order] = node
        order_counter += 1
    return by_order
```

重写 `process_document_record` 的 try 块主体（guards 不变）：

```python
    document_chunks: list[DocumentChunk] = []
    try:
        logger.info("Processing document id=%s name=%s", document.id, document.file_name)
        parsed = parse_document_structure(Path(document.file_path))
        if not parsed.sections and not parsed.lead_content.strip():
            raise ValueError("No readable text was extracted from the document.")

        root_title = document.title or Path(document.file_path).stem
        owners = _persist_section_tree(db, document, root_title, parsed)
        chunk_index = 0
        for result in split_text_structured(parsed.sections, root_content=parsed.lead_content):
            owner = owners.get(result.section_order, owners[-1])
            document_chunk = DocumentChunk(
                kb_id=document.kb_id,
                document_id=document.id,
                chunk_index=chunk_index,
                content=result.content,
                token_count=estimate_token_count(result.content),
                section_id=owner.id,
            )
            db.add(document_chunk)
            document_chunks.append(document_chunk)
            owner.chunk_count += 1
            chunk_index += 1

        db.flush()
        vector_store_service.add_chunks(document_chunks)

        document.status = "finished"
        document.content_length = sum(len(chunk.content) for chunk in document_chunks)
        document.content_preview = document_chunks[0].content[:500] if document_chunks else ""
        document.error_message = ""
        db.commit()
        logger.info("Document processing finished id=%s chunks=%s", document.id, len(document_chunks))
    except Exception as exc:
        ...原有 except 块，在 `db.query(DocumentChunk)...delete()` 之后追加一行：
        clear_document_sections(db, document_id)
        ...其余不变...
```

`reset_document_for_retry` 在 chunk 删除行之后追加：

```python
    clear_document_sections(db, document.id)
```

同步更新 `backend/tests/test_api.py` 中 `test_failed_document_can_be_retried` 的 monkeypatch（第 178–182 行），因为处理入口已从 `parse_document_text` 改为 `parse_document_structure`：

```python
    monkeypatch.setattr(
        document_processing_service,
        "parse_document_structure",
        lambda _path: ParsedDocument(
            sections=[
                ParsedSection(
                    title="正文",
                    level=1,
                    order=0,
                    parent_order=None,
                    content="重试后成功解析的内容",
                )
            ]
        ),
    )
```

并在 `test_api.py` 顶部 import 区追加 `from app.services.document_parser import ParsedDocument, ParsedSection`。

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONPATH="backend"; pytest backend/tests/test_section_pipeline.py backend/tests/test_api.py -v`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/document_processing_service.py backend/tests/test_api.py backend/tests/test_section_pipeline.py
git commit -m "feat: persist section tree during document processing"
```

---

### Task 8: Chroma metadata、检索返回与 RAG 上下文

**Files:**
- Modify: `backend/app/services/vector_store_service.py`（`add_chunks` 加 `section_paths` 可选参数并写入 metadata；`search` 的 match 追加 `section_path`）
- Modify: `backend/app/services/document_processing_service.py`（`process_document_record` 在 flush 后组装 `section_paths` 并传入 `add_chunks`）
- Modify: `backend/app/services/rag_service.py`（`_build_context` 追加 `section_path` 行，用 `source.get("section_path", "")` 兼容老数据）
- Test: Create `backend/tests/test_section_search.py`

**Interfaces:**
- Consumes: Task 7 落盘产出的 chunk 行（`chunk.id` 已 flush 可用）。
- Produces: `add_chunks(chunks, section_paths: dict[int, str] | None = None)`（缺省 None 时行为与旧签名完全一致，已有 `lambda _chunks: None` 的 monkeypatch 不受影响）；`search()` 的每个 match 追加 `"section_path": str`（旧向量缺字段时为空字符串）；`_build_context` 的每个资料块追加 `section_path:` 行。

- [ ] **Step 1: Write the failing tests**

```python
import pytest
from app.services import vector_store_service as vector_store_module
from app.models.document_chunk import DocumentChunk
from app.services.embedding_service import embedding_service
from app.services.rag_service import _build_context
from app.services.vector_store_service import vector_store_service


class _FakeCollection:
    name = "fake"

    def __init__(self) -> None:
        self.upsert_kwargs: dict = {}
        self.query_result: dict = {
            "documents": [["正文"]],
            "metadatas": [
                [
                    {
                        "chunk_id": 5,
                        "document_id": 2,
                        "kb_id": 1,
                        "chunk_index": 0,
                        "section_path": "课程 / 第一章",
                    }
                ]
            ],
            "distances": [[0.2]],
        }

    def count(self) -> int:
        return 1

    def upsert(self, **kwargs) -> None:
        self.upsert_kwargs = kwargs

    def query(self, **kwargs):
        return self.query_result


def test_add_chunks_stores_section_path_metadata(monkeypatch) -> None:
    fake = _FakeCollection()
    monkeypatch.setattr(vector_store_service, "_collection_for", lambda _name: fake)
    monkeypatch.setattr(embedding_service, "embed_texts", lambda _docs: [[0.1, 0.2]])
    chunk = DocumentChunk(
        id=7, kb_id=1, document_id=2, chunk_index=0, content="正文", token_count=2
    )

    vector_store_service.add_chunks([chunk], {7: "课程 / 第一章"})

    assert fake.upsert_kwargs["metadatas"] == [
        {
            "chunk_id": 7,
            "document_id": 2,
            "kb_id": 1,
            "chunk_index": 0,
            "section_path": "课程 / 第一章",
        }
    ]


def test_add_chunks_defaults_section_path_to_empty(monkeypatch) -> None:
    fake = _FakeCollection()
    monkeypatch.setattr(vector_store_service, "_collection_for", lambda _name: fake)
    monkeypatch.setattr(embedding_service, "embed_texts", lambda _docs: [[0.1, 0.2]])
    chunk = DocumentChunk(
        id=8, kb_id=1, document_id=2, chunk_index=0, content="正文", token_count=2
    )

    vector_store_service.add_chunks([chunk])

    assert fake.upsert_kwargs["metadatas"][0]["section_path"] == ""


def test_search_returns_section_path_from_metadata(monkeypatch) -> None:
    fake = _FakeCollection()
    monkeypatch.setattr(vector_store_service, "_collection_for", lambda _name: fake)
    monkeypatch.setattr(embedding_service, "embed_text", lambda _query: [0.1])

    matches = vector_store_service.search(kb_id=1, query="正文", top_k=3)

    assert matches[0]["section_path"] == "课程 / 第一章"
    assert matches[0]["score"] == pytest.approx(0.8)


def test_search_tolerates_legacy_metadata_without_section_path(monkeypatch) -> None:
    fake = _FakeCollection()
    fake.query_result["metadatas"] = [
        [{"chunk_id": 5, "document_id": 2, "kb_id": 1, "chunk_index": 0}]
    ]
    monkeypatch.setattr(vector_store_service, "_collection_for", lambda _name: fake)
    monkeypatch.setattr(embedding_service, "embed_text", lambda _query: [0.1])

    matches = vector_store_service.search(kb_id=1, query="正文", top_k=3)

    assert matches[0]["section_path"] == ""


def test_build_context_includes_section_path() -> None:
    context = _build_context(
        [
            {
                "chunk_id": 1,
                "document_id": 2,
                "chunk_index": 0,
                "score": 0.9,
                "content": "正文",
                "section_path": "课程 / 第一章",
            }
        ]
    )

    assert "section_path: 课程 / 第一章" in context


def test_build_context_tolerates_missing_section_path() -> None:
    context = _build_context(
        [
            {
                "chunk_id": 1,
                "document_id": 2,
                "chunk_index": 0,
                "score": 0.9,
                "content": "正文",
            }
        ]
    )

    assert "section_path: " in context
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH="backend"; pytest backend/tests/test_section_search.py -v`
Expected: FAIL（`add_chunks() got an unexpected keyword argument` 类错误；`section_path` 断言失败）。

- [ ] **Step 3: Write minimal implementation**

`vector_store_service.py` 的 `add_chunks` 改为：

```python
    def add_chunks(
        self,
        chunks: list[DocumentChunk],
        section_paths: dict[int, str] | None = None,
    ) -> None:
        if not chunks:
            return

        documents = [chunk.content for chunk in chunks]
        embeddings = embedding_service.embed_texts(documents)
        collection = self.collection
        ids = [_chunk_vector_id(chunk.id) for chunk in chunks]
        paths = section_paths or {}
        metadatas = [
            {
                "chunk_id": chunk.id,
                "document_id": chunk.document_id,
                "kb_id": chunk.kb_id,
                "chunk_index": chunk.chunk_index,
                "section_path": paths.get(chunk.id, ""),
            }
            for chunk in chunks
        ]
        ...其余不变...
```

`search` 的 match 组装追加一行：

```python
                    "content": document,
                    "score": max(0.0, 1.0 - float(distance)),
                    "section_path": str(metadata.get("section_path") or ""),
```

`document_processing_service.py` 的 `db.flush()` 与 `add_chunks` 之间插入路径组装（注意 `owner` 变量在循环结束后的值不可用，改为用 owners 映射反查；最直接的是在建 chunk 时同步记录）：

将建 chunk 循环改为同步记录路径：

```python
        chunk_index = 0
        section_paths: dict[int, str] = {}
        for result in split_text_structured(parsed.sections, root_content=parsed.lead_content):
            owner = owners.get(result.section_order, owners[-1])
            document_chunk = DocumentChunk(...)
            db.add(document_chunk)
            document_chunks.append(document_chunk)
            owner.chunk_count += 1
            chunk_index += 1
```
flush 之后、add 之前追加：

```python
        db.flush()
        section_paths = {
            chunk.id: owners_by_chunk... 
        }
```
 Owners 映射是 order→section，而 chunk→order 的对应关系在循环里。最干净的办法：在循环内用临时属性记录——不允许。改为循环内记录 `(chunk, owner)` 对：

```python
        chunk_owners: list[tuple[DocumentChunk, DocumentSection]] = []
        chunk_index = 0
        for result in ...:
            ...
            chunk_owners.append((document_chunk, owner))
            chunk_index += 1

        db.flush()
        section_paths = {chunk.id: owner.section_path for chunk, owner in chunk_owners}
        vector_store_service.add_chunks(document_chunks, section_paths)
```

需要 import DocumentSection（Task 7 已加）。把这段替换 Task 7 的对应循环与调用行。

`rag_service.py` 的 `_build_context` blocks 追加一行（放在 `score` 行之后）：

```python
                    f"score: {source['score']:.4f}",
                    f"section_path: {source.get('section_path', '')}",
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONPATH="backend"; pytest backend/tests/test_section_search.py backend/tests/test_section_pipeline.py backend/tests/test_rag_service.py -v`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/vector_store_service.py backend/app/services/document_processing_service.py backend/app/services/rag_service.py backend/tests/test_section_search.py
git commit -m "feat: carry section_path through vector index and RAG context"
```

---

### Task 9: Schema、Sections 树接口与清理/重建路径

**Files:**
- Create: `backend/app/schemas/document_section.py`
- Modify: `backend/app/schemas/document_chunk.py`（`DocumentChunkRead` 追加 `section_id: int | None = None`、`section_path: str = ""`）
- Modify: `backend/app/api/documents.py`（import DocumentSection 与 section schema；`list_document_chunks` 改显式构造响应；新增 `GET /documents/{document_id}/sections` 与 `_build_section_forest`；`delete_document` 追加 section 清理）
- Modify: `backend/app/api/knowledge_bases.py`（import DocumentSection/func/clear_document_sections/process_document_record；`delete_knowledge_base` 追加 section 清理；`rebuild_knowledge_base_index` 改为 finished 文档重解析 + 缺文件文档仅重嵌）
- Modify: `README.md`（rebuild-index 说明行更新为重解析语义）
- Test: Create `backend/tests/test_section_api.py`

**Interfaces:**
- Consumes: Task 5 的 `DocumentSection`；Task 7 的 `clear_document_sections`、`process_document_record`、`reset_document_for_retry`。
- Produces: `DocumentSectionRead`（from_attributes，含全部 9 个字段）；`DocumentSectionTree(DocumentSectionRead + children)`（模块末尾调用 `model_rebuild()`）；`GET /api/documents/{document_id}/sections -> list[DocumentSectionTree]`（文档不存在 404；按 `section_order` 排序后组森林，`parent_section_id` 找不到父时视为根）；`_build_section_forest(sections) -> list[DocumentSectionTree]`；`_chunk_section_paths(db, chunks) -> dict[int, str]`（knowledge_bases 内私有 helper，老数据返回空串）。

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path
from typing import Any

from app.api import documents as documents_api
from app.api import knowledge_bases as knowledge_bases_api
from app.models.document_chunk import DocumentChunk
from app.models.document_section import DocumentSection
from app.services import document_processing_service
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session


def _create_kb(client: TestClient, name: str = "TreeKB") -> dict[str, Any]:
    response = client.post(
        "/api/kbs", json={"name": name, "description": "", "category": "大数据"}
    )
    assert response.status_code == 201
    return response.json()


def _enable_sync_processing(client, db_session, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(documents_api, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(
        document_processing_service.vector_store_service, "add_chunks", lambda *args: None
    )
    monkeypatch.setattr(
        document_processing_service.vector_store_service,
        "delete_chunks",
        lambda _chunk_ids: None,
    )
    monkeypatch.setattr(
        documents_api,
        "process_document",
        lambda document_id: document_processing_service.process_document_record(
            db_session, document_id
        ),
    )


def _upload_md(client: TestClient, kb_id: int, name: str, text: str) -> dict[str, Any]:
    response = client.post(
        f"/api/kbs/{kb_id}/documents/upload",
        files={"file": (name, text, "text/markdown")},
    )
    assert response.status_code == 202
    return response.json()


def test_sections_endpoint_returns_nested_tree(
    client: TestClient, db_session: Session, monkeypatch, tmp_path: Path
) -> None:
    kb = _create_kb(client)
    _enable_sync_processing(client, db_session, monkeypatch, tmp_path)
    uploaded = _upload_md(
        client, kb["id"], "tree.md", "# 第一章\n\n导读\n\n## 1.1 背景\n\n正文\n"
    )

    response = client.get(f"/api/documents/{uploaded['id']}/sections")

    assert response.status_code == 200
    (root,) = response.json()
    assert root["title"] == "tree"
    assert root["section_path"] == "tree"
    (chapter,) = root["children"]
    assert chapter["title"] == "第一章"
    assert chapter["section_path"] == "tree / 第一章"
    (background,) = chapter["children"]
    assert background["chunk_count"] == 1


def test_sections_endpoint_returns_404_for_missing_document(client: TestClient) -> None:
    assert client.get("/api/documents/9999/sections").status_code == 404


def test_chunks_response_carries_section_path(
    client: TestClient, db_session: Session, monkeypatch, tmp_path: Path
) -> None:
    kb = _create_kb(client)
    _enable_sync_processing(client, db_session, monkeypatch, tmp_path)
    uploaded = _upload_md(client, kb["id"], "paths.md", "# 第一章\n\n正文\n")

    chunks = client.get(f"/api/documents/{uploaded['id']}/chunks").json()

    assert chunks[0]["section_id"] is not None
    assert chunks[0]["section_path"] == "paths / 第一章"


def test_chunks_response_tolerates_legacy_null_section(
    client: TestClient, db_session: Session, monkeypatch, tmp_path: Path
) -> None:
    kb = _create_kb(client)
    _enable_sync_processing(client, db_session, monkeypatch, tmp_path)
    uploaded = _upload_md(client, kb["id"], "legacy.md", "纯正文无标题\n")
    document_id = uploaded["id"]
    chunk = db_session.scalars(
        select(DocumentChunk).where(DocumentChunk.document_id == document_id)
    ).one()
    chunk.section_id = None
    db_session.commit()

    chunks = client.get(f"/api/documents/{document_id}/chunks").json()

    assert chunks[0]["section_id"] is None
    assert chunks[0]["section_path"] == ""


def test_delete_document_removes_sections(
    client: TestClient, db_session: Session, monkeypatch, tmp_path: Path
) -> None:
    kb = _create_kb(client)
    _enable_sync_processing(client, db_session, monkeypatch, tmp_path)
    uploaded = _upload_md(client, kb["id"], "gone.md", "# 第一章\n\n正文\n")

    assert client.delete(f"/api/documents/{uploaded['id']}").status_code == 204
    assert db_session.scalars(select(DocumentSection)).all() == []


def test_rebuild_reparses_finished_documents(
    client: TestClient, db_session: Session, monkeypatch, tmp_path: Path
) -> None:
    kb = _create_kb(client)
    _enable_sync_processing(client, db_session, monkeypatch, tmp_path)
    uploaded = _upload_md(client, kb["id"], "rebuild.md", "# 第一章\n\n正文\n")
    document_id = uploaded["id"]
    db_session.query(DocumentSection).filter(
        DocumentSection.document_id == document_id
    ).delete()
    db_session.query(DocumentChunk).filter(
        DocumentChunk.document_id == document_id
    ).delete()
    db_session.commit()

    response = client.post(f"/api/kbs/{kb['id']}/rebuild-index")

    assert response.status_code == 200
    assert response.json()["indexed_chunks"] == 1
    assert (
        db_session.scalar(
            select(DocumentSection.id).where(DocumentSection.document_id == document_id)
        )
        is not None
    )


def test_rebuild_keeps_chunks_when_source_file_missing(
    client: TestClient, db_session: Session, monkeypatch, tmp_path: Path
) -> None:
    kb = _create_kb(client)
    _enable_sync_processing(client, db_session, monkeypatch, tmp_path)
    uploaded = _upload_md(client, kb["id"], "lost.md", "# 第一章\n\n正文\n")
    document_id = uploaded["id"]
    stored = db_session.get(
        __import__("app.models.document", fromlist=["Document"]).Document, document_id
    )
    Path(stored.file_path).unlink()
    monkeypatch.setattr(
        knowledge_bases_api.vector_store_service, "delete_knowledge_base", lambda _kb: None
    )

    response = client.post(f"/api/kbs/{kb['id']}/rebuild-index")

    assert response.status_code == 200
    assert response.json()["indexed_chunks"] == 1
    assert (
        db_session.scalar(
            select(DocumentChunk.id).where(DocumentChunk.document_id == document_id)
        )
        is not None
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH="backend"; pytest backend/tests/test_section_api.py -v`
Expected: FAIL with 404 on `/sections`（路由不存在）及其余断言失败。

- [ ] **Step 3: Write minimal implementation**

新建 `backend/app/schemas/document_section.py`：

```python
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentSectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    parent_section_id: int | None
    title: str
    section_path: str
    section_level: int
    section_order: int
    chunk_count: int
    created_at: datetime


class DocumentSectionTree(DocumentSectionRead):
    children: list["DocumentSectionTree"] = []


DocumentSectionTree.model_rebuild()
```

`backend/app/schemas/document_chunk.py` 追加两行：

```python
    section_id: int | None = None
    section_path: str = ""
```

`backend/app/api/documents.py` 改动：
1. import 区追加 `from app.models.document_section import DocumentSection` 与 `from app.schemas.document_section import DocumentSectionRead, DocumentSectionTree`。
2. `delete_document` 在 chunk 删除行后追加：

```python
    db.query(DocumentSection).filter(DocumentSection.document_id == document_id).delete()
```

3. `list_document_chunks` 改写为显式构造（替换原函数体 return 部分，签名返回改为 `list[DocumentChunkRead]`）：

```python
@router.get(
    "/documents/{document_id}/chunks",
    response_model=list[DocumentChunkRead],
)
def list_document_chunks(
    document_id: int,
    db: Session = Depends(get_db),
) -> list[DocumentChunkRead]:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    chunks = list(
        db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index.asc())
        )
    )
    section_ids = {chunk.section_id for chunk in chunks if chunk.section_id is not None}
    paths: dict[int, str] = {}
    if section_ids:
        paths = dict(
            db.execute(
                select(DocumentSection.id, DocumentSection.section_path).where(
                    DocumentSection.id.in_(section_ids)
                )
            )
        )
    return [
        DocumentChunkRead(
            id=chunk.id,
            kb_id=chunk.kb_id,
            document_id=chunk.document_id,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            token_count=chunk.token_count,
            created_at=chunk.created_at,
            section_id=chunk.section_id,
            section_path=paths.get(chunk.section_id, "") if chunk.section_id else "",
        )
        for chunk in chunks
    ]
```

4. 在 `list_document_chunks` 之后追加新端点与 helper：

```python
@router.get(
    "/documents/{document_id}/sections",
    response_model=list[DocumentSectionTree],
)
def list_document_sections(
    document_id: int,
    db: Session = Depends(get_db),
) -> list[DocumentSectionTree]:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    sections = list(
        db.scalars(
            select(DocumentSection)
            .where(DocumentSection.document_id == document_id)
            .order_by(DocumentSection.section_order.asc())
        )
    )
    return _build_section_forest(sections)


def _build_section_forest(sections: list[DocumentSection]) -> list[DocumentSectionTree]:
    nodes = {section.id: DocumentSectionTree.model_validate(section) for section in sections}
    roots: list[DocumentSectionTree] = []
    for section in sections:
        node = nodes[section.id]
        parent = (
            nodes.get(section.parent_section_id)
            if section.parent_section_id is not None
            else None
        )
        if parent is None:
            roots.append(node)
        else:
            parent.children.append(node)
    return roots
```

`backend/app/api/knowledge_bases.py` 改动：
1. import 区追加 `from app.models.document_section import DocumentSection`、`from app.services.document_processing_service import clear_document_sections, process_document_record, reset_document_for_retry`，并把 `from sqlalchemy import select` 改为 `from sqlalchemy import func, select`。
2. `delete_knowledge_base` 在 chunk 删除行后追加：

```python
    db.query(DocumentSection).filter(
        DocumentSection.document_id.in_(
            select(Document.id).where(Document.kb_id == kb_id)
        )
    ).delete(synchronize_session=False)
```

3. `rebuild_knowledge_base_index` 整体替换为：

```python
@router.post("/{kb_id}/rebuild-index", response_model=IndexRebuildRead)
def rebuild_knowledge_base_index(
    kb_id: int,
    db: Session = Depends(get_db),
) -> IndexRebuildRead:
    _get_knowledge_base_or_404(db, kb_id)
    documents = list(
        db.scalars(
            select(Document)
            .where(Document.kb_id == kb_id, Document.status == "finished")
            .order_by(Document.id)
        )
    )
    try:
        indexed_chunks = 0
        for document in documents:
            if Path(document.file_path).is_file():
                reset_document_for_retry(db, document)
                process_document_record(db, document.id)
                finished = db.get(Document, document.id)
                if finished is not None and finished.status == "finished":
                    indexed_chunks += (
                        db.scalar(
                            select(func.count(DocumentChunk.id)).where(
                                DocumentChunk.document_id == document.id
                            )
                        )
                        or 0
                    )
            else:
                stale = list(
                    db.scalars(
                        select(DocumentChunk).where(
                            DocumentChunk.document_id == document.id
                        )
                    )
                )
                vector_store_service.delete_chunks([chunk.id for chunk in stale])
                vector_store_service.add_chunks(stale, _chunk_section_paths(db, stale))
                indexed_chunks += len(stale)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Index rebuild failed for knowledge base id=%s", kb_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not rebuild the vector index.",
        ) from exc
    return IndexRebuildRead(
        kb_id=kb_id,
        indexed_chunks=indexed_chunks,
        collection=vector_store_service.collection_name,
        embedding_provider=vector_store_service.embedding_provider,
    )


def _chunk_section_paths(db: Session, chunks: list[DocumentChunk]) -> dict[int, str]:
    section_ids = {chunk.section_id for chunk in chunks if chunk.section_id is not None}
    if not section_ids:
        return {}
    by_section = dict(
        db.execute(
            select(DocumentSection.id, DocumentSection.section_path).where(
                DocumentSection.id.in_(section_ids)
            )
        )
    )
    return {
        chunk.id: by_section.get(chunk.section_id, "")
        for chunk in chunks
        if chunk.id is not None and chunk.section_id is not None
    }
```

注意：`reset_document_for_retry` 要求文档状态为 processing 吗？检查 Task 7 的实现——`reset_document_for_retry(db, document)` 直接清理并置 processing，不校验原状态（原代码无状态校验，重试路由层校验）。重建循环里 finished 文档可直接调用。`reset` 内含 commit；`process_document_record` 内含 commit。循环内 db 会话复用可行。

`README.md` 的 rebuild-index 表格行 `| POST | /api/kbs/{kb_id}/rebuild-index | 从 SQLite chunk 重建 Chroma 索引 |` 改为 `| POST | /api/kbs/{kb_id}/rebuild-index | 重新解析 finished 文档并重建 section 与 Chroma 索引（源文件缺失则仅重嵌） |`。

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONPATH="backend"; pytest backend/tests/test_section_api.py backend/tests/test_api.py -v`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/document_section.py backend/app/schemas/document_chunk.py backend/app/api/documents.py backend/app/api/knowledge_bases.py backend/tests/test_section_api.py README.md
git commit -m "feat: expose section tree API and rebuild sections on reindex"
```

---

### Task 10: 问答与检索响应的 section_path 透出

**Files:**
- Modify: `backend/app/schemas/chat.py`（`ChatSource` 追加 `section_path: str = ""`）
- Modify: `backend/app/schemas/vector_search.py`（`VectorSearchResult` 追加 `section_path: str = ""`）
- Modify: `backend/app/api/chat.py`（`_enrich_sources` 追加 `section_path` 透出，老数据兜底空串）
- Test: `backend/tests/test_section_api.py`（末尾追加两个测试；vector_search 端点无需改代码，search 结果字典已在 Task 8 带出）

**Interfaces:**
- Consumes: Task 8 的 `search()` match（含 `section_path`）；Task 9 的上传/处理测试脚手架。
- Produces: 响应契约新增可选字段（带默认值，旧客户端不受影响）。

- [ ] **Step 1: Write the failing tests**

```python
def test_chat_sources_carry_section_path(
    client: TestClient, db_session: Session, monkeypatch, tmp_path: Path
) -> None:
    from app.api import chat as chat_api

    kb = _create_kb(client, "ChatKB")
    _enable_sync_processing(client, db_session, monkeypatch, tmp_path)
    _upload_md(client, kb["id"], "chat.md", "# 第一章\n\n正文\n")

    def fake_answer(**kwargs):
        return {
            "answer": "测试回答",
            "sources": [
                {
                    "chunk_id": 1,
                    "document_id": 999,
                    "kb_id": kb["id"],
                    "chunk_index": 0,
                    "content": "正文",
                    "score": 0.9,
                    "section_path": "chat / 第一章",
                }
            ],
            "usage": None,
            "retrieval_trace": None,
        }

    monkeypatch.setattr(chat_api.rag_service, "answer", fake_answer)
    response = client.post("/api/chat", json={"kb_id": kb["id"], "question": "讲了什么"})

    assert response.status_code == 200
    (source,) = response.json()["sources"]
    assert source["section_path"] == "chat / 第一章"
    assert source["document_title"] == "已删除资料"


def test_vector_search_results_carry_section_path(
    client: TestClient, monkeypatch
) -> None:
    from app.services import vector_store_service as vector_store_module

    kb = _create_kb(client, "SearchKB")
    monkeypatch.setattr(
        vector_store_module.vector_store_service,
        "search",
        lambda kb_id, query, top_k=5: [
            {
                "chunk_id": 1,
                "document_id": 1,
                "kb_id": kb_id,
                "chunk_index": 0,
                "content": "正文",
                "score": 0.9,
                "section_path": "chat / 第一章",
            }
        ],
    )

    response = client.post(f"/api/kbs/{kb['id']}/search", json={"query": "正文"})

    assert response.status_code == 200
    (result,) = response.json()["results"]
    assert result["section_path"] == "chat / 第一章"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH="backend"; pytest backend/tests/test_section_api.py -v -k "carry_section_path"`
Expected: FAIL（响应体被 Pydantic 丢弃 `section_path` 字段或 `_enrich_sources` KeyError——实际是 response_model 过滤掉多余字段导致断言失败）。

- [ ] **Step 3: Write minimal implementation**

`schemas/chat.py` 的 `ChatSource` 追加：

```python
    location: str = ""
    section_path: str = ""
```

`schemas/vector_search.py` 的 `VectorSearchResult` 追加：

```python
    score: float
    section_path: str = ""
```

`api/chat.py` 的 `_enrich_sources` 循环内追加：

```python
        item["section_path"] = str(source.get("section_path") or "")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONPATH="backend"; pytest backend/tests/test_section_api.py -v`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/chat.py backend/app/schemas/vector_search.py backend/app/api/chat.py backend/tests/test_section_api.py
git commit -m "feat: expose section_path in chat and search responses"
```

---

### Task 11: 前端来源展示与全量质量门

**Files:**
- Create: `frontend/src/demo/sourceFormat.js`
- Create: `frontend/src/demo/sourceFormat.test.js`
- Modify: `frontend/src/demo/views/AssistantView.vue`（第 283 行来源副标题改用 helper；`<script setup>` import 区追加引入）
- Docs: 无（本任务只跑全量门禁，不写新文档）

**Interfaces:**
- Consumes: Task 10 的 `section_path` 响应字段。
- Produces: `formatSourceSubtitle(source) -> string`（`${section_path || '未分类'} · ${location}`，location 为空时只返回前半）。

- [ ] **Step 1: Write the failing tests**

```js
import { describe, expect, it } from 'vitest'
import { formatSourceSubtitle } from './sourceFormat'

describe('formatSourceSubtitle', () => {
  it('combines section path and location', () => {
    expect(formatSourceSubtitle({ section_path: '大数据导论 / 第一章', location: '第 2 个片段' })).toBe(
      '大数据导论 / 第一章 · 第 2 个片段',
    )
  })

  it('falls back to 未分类 when section path is missing', () => {
    expect(formatSourceSubtitle({ location: '第 1 个片段' })).toBe('未分类 · 第 1 个片段')
    expect(formatSourceSubtitle({ section_path: '  ', location: '第 1 个片段' })).toBe(
      '未分类 · 第 1 个片段',
    )
  })

  it('omits the separator when location is missing', () => {
    expect(formatSourceSubtitle({ section_path: '大数据导论 / 第一章' })).toBe('大数据导论 / 第一章')
    expect(formatSourceSubtitle({})).toBe('未分类')
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend; npm test -- sourceFormat`
Expected: FAIL with "Failed to resolve import './sourceFormat'"。

- [ ] **Step 3: Write minimal implementation**

新建 `frontend/src/demo/sourceFormat.js`：

```js
export function formatSourceSubtitle(source) {
  const section = (source?.section_path || '').trim() || '未分类'
  const location = (source?.location || '').trim()
  return location ? `${section} · ${location}` : section
}
```

`AssistantView.vue` 改动两处：
1. `<script setup>` 的 import 区追加（与其它相对引入放一起）：`import { formatSourceSubtitle } from '../sourceFormat'`
2. 第 283 行：

```html
<span class="source-copy"><strong>{{ source.document_title || source.file_name || '课程资料' }}</strong><em>{{ formatSourceSubtitle(source) }}</em></span>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend; npm test -- sourceFormat`
Expected: PASS（3 个测试）。随后跑全量门禁：
- `$env:PYTHONPATH="backend"; pytest backend/tests -q`（从仓库根目录）
- `ruff check backend`
- `ruff format --check backend`
- `python -m compileall -q backend/app`
- `cd frontend; npm test`
- `cd frontend; npm run build`

Expected: 全部通过；后端测试数 ≥ 19 + 本阶段新增（ Task 1:5、Task 2:5、Task 3:5、Task 4:4、Task 5:3、Task 6:4、Task 7:3、Task 8:6、Task 9:7、Task 10:2 = 44 个新测试）。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/demo/sourceFormat.js frontend/src/demo/sourceFormat.test.js frontend/src/demo/views/AssistantView.vue
git commit -m "feat: show section path in evidence panel"
```

---

## Self-Review

**1. Spec coverage:** Spec §1（模型/Root/归属）→Task 5/7；§2（解析器四格式+边界）→Task 1–4；§3（chunker/落盘/Chroma）→Task 6–8；§4（API/schema/前端）→Task 9–11；§6 不做事项均未排入。覆盖完整。两处有意的 spec 修订已同步回 spec 文件：`ParsedDocument.lead_content` 字段；空正文 section 回退用标题（替代"chunk_count=0 合法"）。

**2. Placeholder scan:** 无 TBD/TODO/"类似 Task N"；每步含真实代码与确切命令；唯一的动态点是 Task 9 重建测试里用 `__import__` 取 Document 模型——已写成可运行代码而非占位，但风格差，执行时可改为顶部常规 import（`from app.models.document import Document`）。此处显式允许该替换。

**3. Type consistency:** `ParsedSection.order/parent_order`（Task 1）→ `_persist_section_tree` 的 `by_order` 键含 `-1→Root`（Task 7）→ `ChunkResult.section_order` 对齐同一键空间（Task 6）→ `section_paths: dict[int, str]` 以 `chunk.id` 为键（Task 8/9 的 `_chunk_section_paths` 一致）；`section_path` 全链路 `str`，缺失时 `""`。一致。

**4. Review Focus:** 5 项全部 pin 到具体测试（见顶部 Review Focus 与各 Task）。Task 2 的无空格 ATX（`#标题`）与 Task 9 的缺文件重建是额外覆盖，不在 5 项内但各有测试。
