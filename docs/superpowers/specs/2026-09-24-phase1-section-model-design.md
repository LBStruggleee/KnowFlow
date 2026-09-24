# Phase 1：层级化 Section 模型 — 设计 Spec

> 状态：设计评审中。批准后由 `superpowers:writing-plans` 生成逐任务 TDD 实施计划。
> 总体方案：`docs/superpowers/plans/2026-09-24-knowflow-retrieval-upgrade.md`（Phase 1）

**Goal:** 解析器输出结构化文档树（`ParsedDocument`），落盘 `document_section` 表，每个 chunk 归属一个 section 并携带 `section_path`，检索与问答结果展示来源路径。

**Architecture:** 解析层做"纯文本结构提取 + 层级栈建 parent 关系"（输出扁平 sections，`parent_order` 已填好），落盘层（processing service）只做持久化与 `section_path` 拼接。chunker 消费结构化输入、按 section 独立切分。SQLite 仍是事实源，Chroma metadata 只追加 `section_path` 可重建字段。

**Tech Stack:** 现有依赖即可（python-docx / pypdf / python-pptx / SQLAlchemy / Pydantic），零新增依赖。

**已确认决策：**
- D1: PDF 采用单 Root 回退（不做字号启发式）。
- D2: docx 采用标准标题样式 + 保守加粗启发式。
- D3: 老数据不自动回填（`section_id` nullable，老 chunk 为 NULL，前端显示"未分类"）。
- D4: 实现取方案 A（结构化中间模型）+ 方案 C 的层级栈算法（在落盘层执行）。
- D5: 每个文档恒有一个合成 Root section，title = 文档标题（文件名词干）。

---

## 1. 数据模型

### 1.1 新增 `document_section` 表

```python
class DocumentSection(Base):
    __tablename__ = "document_section"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), index=True
    )
    parent_section_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_section.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    title: Mapped[str] = mapped_column(String(500))
    section_path: Mapped[str] = mapped_column(Text, default="")
    section_level: Mapped[int] = mapped_column(Integer, default=0)  # Root=0
    section_order: Mapped[int] = mapped_column(Integer, default=0)  # 文档内全局顺序
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)    # 直属 chunk 数
    summary: Mapped[str] = mapped_column(Text, default="")          # 预留，P1 恒为空
    created_at: Mapped[datetime] = ...
```

说明：
- `parent_section_id` 自引用 + CASCADE，随文档删除级联清理。
- `section_path` 用 `" / "` 连接，含文档根（例：`大数据导论 / 第3章 / 3.2 MapReduce`）。
- `section_path` 不要求唯一；身份标识是 `section.id`。
- `summary` 为 Phase 6 预留字段，P1 恒为空字符串，不做 LLM 调用。
- 建表靠 `main.py:30` 现有 `create_all` 自动完成；测试内存库同样自动建表。

### 1.2 `document_chunk` 增量改动

新增一列：`section_id: Mapped[int | None]`（FK → document_section，nullable，ondelete=CASCADE，index=True）。
- `chunk_index` 保持文档级全局编号，`(document_id, chunk_index)` 唯一约束不动。
- 老数据 `section_id = NULL`，所有读路径用 `.get()` / `is None` 容忍。

### 1.3 Root 与归属语义（约定，测试必须覆盖）

- 每个文档恒有一个合成 Root section：`level=0`，`parent=None`，`title` = 文档标题（文件名词干），`section_path` = 文档标题本身。
- 首个标题之前的正文（摘要、前言）归属 Root；无标题文档（txt / PDF）退化为「Root + 全部正文」。
- 一个 section 拥有其直属标题下、子标题之前的正文切出的全部 chunk；只有子标题、无直属正文的 section `chunk_count = 0`（合法，不报错）。
- 每个 chunk 必属一个 section，无孤儿 chunk。

---

## 2. 解析器（`document_parser.py`）

### 2.1 新契约（与旧函数并存）

```python
class ParsedSection(BaseModel):
    title: str
    level: int   # >= 1
    order: int   # 文档内顺序，0 起
    parent_order: int | None  # 父 section 的 order；None 表示挂 Root。
    # 由解析器内的层级栈算法填充：维护 (level, order) 栈，新 section
    # 到来时 pop 至栈顶 level < 新 level，栈顶即父（空栈则为 None）。
    # 跳级（如 L0 后直接 L3）容忍，直接挂栈顶。
    content: str # 直属正文（不含子标题内容），可为空字符串

class ParsedTable(BaseModel):  # P1 只定义类型，解析器返回空列表；P3 填充
    headers: list[str]
    rows: list[list[str]]
    source_section_order: int

class ParsedDocument(BaseModel):
    sections: list[ParsedSection]
    tables: list[ParsedTable] = []

def parse_document_structure(file_path: Path) -> ParsedDocument: ...
```

- 保留 `parse_document_text()` 原函数不变（降级路径与旧测试继续用）。
- `normalize_text()` 复用。

### 2.2 各格式策略

**txt / md 以外 / pdf**：`sections = []`（单 Root 回退，由落盘层统一建 Root）。D1 决策：不做字号启发式。

**txt**：`sections = []`。整篇正文归 Root。

**md**：
- ATX 标题：行首 1–6 个 `#` + 空格 → `level` = 井号数。
- Setext 标题：`===` 下划线 → level 1，`---` 下划线 → level 2。
- 代码围栏（``` / ~~~）内的 `#` 行不是标题（逐行扫描跟踪 fence 状态）。
- 无标题 md → `sections = []`。

**docx**：
- 标准样式：`paragraph.style.name` 匹配 `^(Heading|标题)\s*([1-9])$` → level 为数字；`^Title$` → level 1。
- 样式名读取失败（模板损坏）时按无标题处理，不抛异常。
- 加粗启发式（D2，保守护栏，四个条件**同时满足**才认作标题）：
  1. 段落无标题样式；
  2. 段落全部非空 run 的 `bold` 为 True；
  3. 无显式字号或字号 ≥ 14pt（`run.font.size` 为 None 时视为满足）；
  4. 文本长度 ≤ 40 字符，且段落不在表格内。
  满足 → `level` **固定为 2**。理由：讲义最常见结构是"章（H1）+ 加粗小节"，固定 level 2 行为可预测、可测试；出现在 H2 之下的加粗小标题会与其同级（语义略偏但结构不乱套，spec 明确接受此偏差）。
- 表格段落（`paragraph._p` 在 `tbl` 内）在 P1 阶段：保持现有行为（表格文本拍平追加到当前 section content），P3 再结构化。

**pptx**：每张 slide 一个 `level=1` section；`title` = 标题占位符文本（若有）否则 `Slide N`；`content` = 该 slide 全部文本（含表格拍平文本，保持现有行为）。

### 2.3 边界行为（必须有单测）

- 空文档 / 全空白文档 → `sections = []`（落盘层后续按"无可读文本"报错，行为与现在一致）。
- 只有标题、零正文的 section → `content = ""`，合法。
- 标题层级跳级（如 H1 后直接 H3）→ 原样保留 level，落盘层层级栈容忍（见 §3）。
- 连续同级标题、文档以正文开头（无前置标题）、超长单段落（> chunk_size）→ 均合法输入。

---

## 3. 落盘层（`document_processing_service.py` + `text_chunker.py`）

### 3.1 chunker 新契约（与旧函数并存）

```python
class ChunkResult(BaseModel):
    content: str
    section_order: int  # 对应 ParsedSection.order；Root 内容为 -1
    section_level: int  # Root 内容为 0

def split_text_structured(
    sections: list[ParsedSection],
    root_content: str = "",   # 首标题前正文 + 无标题文档全文
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[ChunkResult]: ...
```

- 每个 section 的 content **独立切分**（复用现有 800/150 段落逻辑），不跨 section 合并，保证归属清晰。
- `content` 为空的 section 产出 0 个 chunk。
- 保留 `split_text()` 原纯函数不变。

### 3.2 落盘流程（`process_document_record` 改造）

```
parse_document_structure(file)          # 新；sections 自带 parent_order
  → 建 Root section（title=文件名词干）
  → 按 order 建子 section：
      parent_id = order_map[sec.parent_order] if sec.parent_order is not None else root_id
      path = parent.path + " / " + sec.title
      insert section；order_map[sec.order] = new_id
  → split_text_structured(...) → 建 DocumentChunk(section_id=order_map[...] 或 root_id)
  → flush → Chroma add_chunks（含 metadata.section_path）
  → 更新各 section.chunk_count → 现有 commit / 异常补偿流程不变
```

- 跳级容忍：level 0 → level 3 直接挂 Root（while 循环自然处理）。
- Root 内容（首标题前正文）：`section_order=-1` → 归属 root_id。
- 异常补偿：现有 `delete_chunks` + 删除 `DocumentChunk` 流程**扩展为同时删除本批次 `DocumentSection`**（按 document_id），否则 section 残留。
- `reset_document_for_retry`：扩展为同时删除该文档的 `DocumentSection` 行（否则 retry 会重复建树）。
- 空解析结果（无可读文本）→ 保持现有 `ValueError("No readable text...")` 行为。

### 3.3 Chroma metadata

`add_chunks` 的 metadata 新增 `section_path: str`（空字符串兜底）。旧向量无此字段：所有读 metadata 处用 `metadata.get("section_path", "")`。本阶段不迁移旧向量（D3）。

---

## 4. API / Schema / 前端

### 4.1 Schema

- 新增 `backend/app/schemas/document_section.py`：`DocumentSectionRead{id, document_id, parent_section_id, title, section_path, section_level, section_order, chunk_count, created_at}`（`summary` 不暴露，P1 恒空）。
- 新增 `DocumentSectionTree`（嵌套 children，供大纲接口）。
- `DocumentChunkRead` 新增 `section_id: int | None`、`section_path: str = ""`（老数据/旧向量兜底为空）。
- chat source（`schemas/chat.py` 的 source 模型）与 vector search hit（`schemas/vector_search.py`）新增 `section_path: str = ""`（带默认值 = 向后兼容）。

### 4.2 API

- 新增 `GET /api/documents/{document_id}/sections`：返回该文档的 section 树（嵌套结构，Root 为根）。文档不存在 → 404（与现有 chunks 接口一致）。
- `GET /api/documents/{document_id}/chunks`：响应项追加新字段（不删旧字段）。
- `/api/kbs/{kb_id}/search` 与 `/api/chat`：source/hit 追加 `section_path`。
- `POST /api/kbs/{kb_id}/rebuild-index`：重建时删除并重建该文档 section（复用与 retry 相同的清理函数，抽成 `clear_document_sections(db, document_id)` 共用）。

### 4.3 前端

- chunk 预览项显示 `section_path` 面包屑；为空时显示"未分类"（覆盖 D3 老数据）。
- 不改整体布局，只动 chunk 预览组件 + 对应 Vitest。

---

## 5. 测试策略

后端 pytest（内存 SQLite，现成 fixture 直接可用）：
1. `test_document_parser.py`（现有文件扩展）：md ATX/setext/fence、docx 中英文样式名（需构造含 `Heading 1` 与 `标题 1` 的 docx fixture——用 python-docx 在测试里现场生成，不提交二进制）、加粗启发式四条护栏的正反用例、pptx 无标题 slide、pdf/txt 回退、`parse_document_text` 旧行为不变。
2. 新增 `test_section_tree.py`：层级栈建树（正常嵌套 / 跳级 / 连续同级 / 首段正文归 Root / 空 sections 只建 Root）。
3. `test_text_chunker.py`（现有文件扩展）：`split_text_structured` 按 section 独立切分、不跨 section 合并、空 section 产 0 chunk；`split_text` 旧行为不变。
4. `process_document_record` 落盘端到端（用 `db_session` fixture + 真实小文件）：section 树形状断言、chunk.section_id 外键正确、chunk_count 正确、失败时 section 无残留、retry 清理 section。
5. API 契约：`GET sections` 树形状、`chunks` 新字段、`chat`/`search` source 带 `section_path`、老数据（section_id NULL）响应不 500。

前端 Vitest：section_path 面包屑渲染 + "未分类"兜底。

质量门：pytest 全过、Ruff、format、compileall、前端 `npm test` + `npm run build`。

---

## 6. 不做事项（重申，防止范围蔓延）

1. 不做 section 摘要 LLM 生成（`summary` 恒空）。
2. 不做跨文档图 / 文档关系。
3. 不改检索算法（仍单路向量，只多带路径元数据）。
4. 不做 `query_table`、不做表格结构化（Phase 3）。
5. 不做 Alembic（`create_all` 足够；多用户确定后再立项）。
6. 不自动回填老数据（D3）。

---

## Review Focus（本阶段最易踩坑的五类输入，测试必须覆盖）

1. 中文 docx 模板样式名为"标题 1"而非"Heading 1" → 双重正则，单测覆盖。
2. 加粗的表格说明/重点提示被误判为标题 → 四条护栏（尤其"不在表格内"与"≤40 字"），正反用例。
3. md 代码围栏内的 `#` 行 → fence 跟踪，单测覆盖。
4. 无标题文档（txt/PDF/纯正文 md）→ 单 Root 回退，不抛异常，不断言空。
5. 处理中删除文档 / retry 重复建树 → 清理函数幂等，失败无 section 残留。
