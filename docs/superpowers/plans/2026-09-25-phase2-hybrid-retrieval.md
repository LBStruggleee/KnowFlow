# Phase 2：混合检索 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 检索从单路向量升级为"向量 + 词面（FTS5 双字索引）"双通道 RRF 融合，中文术语可命中，通道可配、过程可 trace。

**Architecture:** 新模块 `lexical_search.py`（双字分词 + FTS 通道 + DDL/回填）与 `hybrid_search.py`（RRF 融合编排）均为无状态函数；`rag_service.answer` 与 `/search` 改调 `search_hybrid`；SQLite 触发器保证 FTS 与 chunk 行自动同步；向量通道与 Chroma 原样复用。

**Tech Stack:** Python 3.13（实测 venv 为 3.12.8，命令一律用 `backend\.venv\Scripts\python.exe`）、FastAPI、SQLAlchemy 2.0、SQLite FTS5（标准库自带）、pytest、Vitest。零新增依赖。

**Spec:** `docs/superpowers/specs/2026-09-25-phase2-hybrid-retrieval-design.md`

## Global Constraints

1. 后端默认监听 `127.0.0.1`，不引入 Redis / PostgreSQL / 对象存储 / Celery。
2. SQLite 是事实源，Chroma 是可重建索引；`search_text` 与 FTS 行都是可重建派生数据，损坏时回填/重建恢复。
3. API Key 只在 `backend/.env`，不提交 Git。
4. `/api/chat`、`/api/kbs/{kb_id}/search`、`/api/admin/settings` 现有响应字段不删不改名，只新增字段。
5. 每任务自带测试；后端 pytest、Ruff 检查、`ruff format`、`python -m compileall` 必须通过；前端改动追加 Vitest 与 `npm run build`。
6. 每个 Task 一个 Git commit，`feat:`/`fix:`/`test:`/`docs:` 前缀。
7. 无有效 `DASHSCOPE_API_KEY` 时所有新功能必须可降级；lexical 通道纯本地，任何情况下可用。
8. 零新增依赖；测试命令一律从仓库根目录执行，后端用 `$env:PYTHONPATH="backend"; backend\.venv\Scripts\python.exe -m pytest backend/tests/<file> -v`（PowerShell）。
9. 不得用原文直建 FTS 索引（spec D5：`unicode61` 对中文无效，已被探针证伪）。

## Review Focus

1. 纯符号/纯标点查询（双字化为空）→ 返回空集不崩溃，trace 如实记录 → Task 4 的 `test_search_lexical_returns_empty_for_blank_terms`。
2. 中英混排长词（如 `HDFS的NameNode节点`）→ ASCII 词与双字共存命中 → Task 1 的 `test_to_search_text_handles_mixed_chinese_ascii` + Task 4 的术语命中测试。
3. FTS 表缺失/FTS5 未编译 → LIKE 降级不断服务 → Task 4 的 `test_search_lexical_falls_back_to_like_without_fts_table`。
4. 老数据 `search_text` 为空 → 启动回填后可查，回填前 hybrid 不报错 → Task 3 的 `test_backfill_search_text_fills_legacy_rows`。
5. 非法 channels 值 → 归一化为 hybrid，不 500 → Task 5 的 `test_search_hybrid_normalizes_unknown_channels`。

---

### Task 1: 双字分词纯函数

**Files:**
- Create: `backend/app/services/lexical_search.py`（本任务只含分词函数与构造 helper；DDL 与查询函数由 Task 3/4 追加）
- Test: Create `backend/tests/test_lexical_search.py`

**Interfaces:**
- Consumes: 无（首个任务；`re` 标准库）。
- Produces: `to_search_text(text: str) -> str`（ASCII `[A-Za-z0-9_]+` 整词保留；CJK 连续串切重叠双字，仅相邻对，末单字丢弃；其余字符丢弃；空/纯符号输入返回 `""`）；`_build_search_text(content: str, section_path: str = "") -> str`（两部分分别双字化后空格拼合 strip）。

- [ ] **Step 1: Write the failing tests**

```python
from app.services.lexical_search import _build_search_text, to_search_text


def test_to_search_text_bigrams_chinese() -> None:
    assert to_search_text("混合检索") == "混合 合检 检索"


def test_to_search_text_handles_mixed_chinese_ascii() -> None:
    assert to_search_text("HDFS的NameNode节点") == "HDFS NameNode 节点"


def test_to_search_text_drops_punctuation_and_single_chars() -> None:
    assert to_search_text("你好，世界！") == "你好 世界"
    assert to_search_text("是的") == "是的"


def test_to_search_text_returns_empty_for_blank_or_symbol_input() -> None:
    assert to_search_text("") == ""
    assert to_search_text("  !!!???  ") == ""


def test_to_search_text_keeps_ascii_words_whole() -> None:
    assert to_search_text("MapReduce Shuffle") == "MapReduce Shuffle"


def test_build_search_text_combines_content_and_section_path() -> None:
    assert _build_search_text("背景正文", "课程 / 第一章") == "背景 正文 课程 程第 第一 一章"
    assert _build_search_text("背景正文") == "背景 正文"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH="backend"; backend\.venv\Scripts\python.exe -m pytest backend/tests/test_lexical_search.py -v`
Expected: FAIL with "No module named 'app.services.lexical_search'"（收集即报错）。

- [ ] **Step 3: Write minimal implementation**

新建 `backend/app/services/lexical_search.py`：

```python
import re

ASCII_WORD_RE = re.compile(r"[A-Za-z0-9_]+")
TOKEN_SCAN_RE = re.compile(r"[A-Za-z0-9_]+|[^\x00-\x7f\s]+")


def _is_cjk(char: str) -> bool:
    return "\u4e00" <= char <= "\u9fff"


def to_search_text(text: str) -> str:
    tokens: list[str] = []
    for match in TOKEN_SCAN_RE.finditer(text or ""):
        token = match.group(0)
        if ASCII_WORD_RE.fullmatch(token):
            tokens.append(token)
        else:
            chars = [char for char in token if _is_cjk(char)]
            tokens.extend(chars[index] + chars[index + 1] for index in range(len(chars) - 1))
    return " ".join(tokens)


def _build_search_text(content: str, section_path: str = "") -> str:
    return f"{to_search_text(content)} {to_search_text(section_path or '')}".strip()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONPATH="backend"; backend\.venv\Scripts\python.exe -m pytest backend/tests/test_lexical_search.py -v`
Expected: PASS（6/6）。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/lexical_search.py backend/tests/test_lexical_search.py
git commit -m "feat: add bigram Chinese tokenizer for lexical search"
```

---

### Task 2: search_text 列与入库写入

**Files:**
- Modify: `backend/app/models/document_chunk.py`（追加 `search_text` 列）
- Modify: `backend/app/services/document_processing_service.py`（import `_build_search_text`；建 chunk 时写入 `search_text`）
- Test: `backend/tests/test_section_pipeline.py`（末尾追加 1 个测试）

**Interfaces:**
- Consumes: Task 1 的 `_build_search_text`；Task 1（Phase 1）的落盘流程（`owners` 映射含 `DocumentSection.section_path`）。
- Produces: `DocumentChunk.search_text`（Text，默认 `""`）；落盘/retry/rebuild 自动携带（均走 `process_document_record`）。

- [ ] **Step 1: Write the failing test**

```python
def test_process_writes_bigram_search_text(
    db_session: Session, monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        document_processing_service.vector_store_service,
        "add_chunks",
        lambda _chunks, _paths=None: None,
    )
    document = _create_finished_document(db_session, tmp_path, "分词", "# 第一章\n\n背景正文\n")

    process_document_record(db_session, document.id)

    chunks = db_session.scalars(
        select(DocumentChunk).order_by(DocumentChunk.chunk_index)
    ).all()
    assert chunks[0].search_text == "背景 正文 分词 第一 一章"
```

（期望推导：内容"背景正文"→`背景 正文`；section_path"分词 / 第一章"→`分词 第一 一章`；拼合 strip。）

- [ ] **Step 2: Run test to verify it fails**

Run: `$env:PYTHONPATH="backend"; backend\.venv\Scripts\python.exe -m pytest backend/tests/test_section_pipeline.py -v -k writes_bigram`
Expected: FAIL with `AttributeError`/`OperationalError: no such column: search_text`（模型缺列）。

- [ ] **Step 3: Write minimal implementation**

`document_chunk.py` 在 `section_id` 列后追加：

```python
    search_text: Mapped[str] = mapped_column(Text, default="")
```

`document_processing_service.py` import 行追加 `from app.services.lexical_search import _build_search_text`（按字母序放在 `llm` 相关之后——本文件现有 imports：database、models、document_parser、text_chunker、vector_store；`lexical_search` 按序插在 `document_parser` 之后、`text_chunker` 之前）。建 chunk 处：

```python
            document_chunk = DocumentChunk(
                kb_id=document.kb_id,
                document_id=document.id,
                chunk_index=chunk_index,
                content=result.content,
                token_count=estimate_token_count(result.content),
                section_id=owner.id,
                search_text=_build_search_text(result.content, owner.section_path),
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONPATH="backend"; backend\.venv\Scripts\python.exe -m pytest backend/tests/test_section_pipeline.py backend/tests/test_api.py -q`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/document_chunk.py backend/app/services/document_processing_service.py backend/tests/test_section_pipeline.py
git commit -m "feat: store bigram search text on chunk insert"
```

---

### Task 3: FTS DDL、触发器、回填与启动接入

**Files:**
- Modify: `backend/app/services/lexical_search.py`（追加 DDL 常量、`fts5_available`、`ensure_lexical_index`、`ensure_chunk_columns`、`backfill_search_text`）
- Modify: `backend/app/main.py`（`create_all` 后依次调用三者；回填放在 `SessionLocal` 块内 recovery 之前）
- Modify: `backend/tests/conftest.py`（`db_session` fixture 在 `create_all` 后调用 `ensure_lexical_index(engine)`）
- Test: `backend/tests/test_lexical_search.py`（末尾追加）

**Interfaces:**
- Consumes: Task 1 的 `to_search_text`、`_build_search_text`；Phase 1 的 conftest `db_session`（内存库）。
- Produces: `fts5_available(engine) -> bool`；`ensure_lexical_index(engine) -> bool`（建表+三触发器，幂等；返回可用性）；`ensure_chunk_columns(engine) -> None`（`PRAGMA table_info` 查缺补 `section_id INTEGER` / `search_text TEXT DEFAULT ''`，幂等；修复 Phase 1 遗留的老库缺列问题）；`backfill_search_text(db: Session, batch_size: int = 500) -> int`（逐批补写空 `search_text` 并 commit，返回行数；触发器自动同步 FTS）。

- [ ] **Step 1: Write the failing tests**

```python
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_section import DocumentSection
from app.models.knowledge_base import KnowledgeBase
from app.services.lexical_search import (
    _build_search_text,
    backfill_search_text,
    ensure_chunk_columns,
    ensure_lexical_index,
    fts5_available,
)
from sqlalchemy import text
from sqlalchemy.orm import Session


def _create_chunk(db_session: Session, content: str, search_text: str = "") -> DocumentChunk:
    knowledge_base = KnowledgeBase(name=f"KB-{content[:6]}", description="", category="")
    db_session.add(knowledge_base)
    db_session.flush()
    document = Document(
        kb_id=knowledge_base.id,
        title="词面",
        file_name="词面.md",
        file_path="/tmp/词面.md",
        file_type="md",
        status="finished",
    )
    db_session.add(document)
    db_session.flush()
    section = DocumentSection(
        document_id=document.id,
        title="词面",
        section_path="词面",
        section_level=0,
        section_order=0,
    )
    db_session.add(section)
    db_session.flush()
    chunk = DocumentChunk(
        kb_id=knowledge_base.id,
        document_id=document.id,
        chunk_index=0,
        content=content,
        token_count=1,
        section_id=section.id,
        search_text=search_text,
    )
    db_session.add(chunk)
    db_session.commit()
    return chunk


def test_triggers_sync_fts_on_insert_update_delete(db_session: Session) -> None:
    chunk = _create_chunk(db_session, "混合检索提升召回", _build_search_text("混合检索提升召回"))

    hits = db_session.execute(
        text("SELECT rowid FROM chunk_fts WHERE chunk_fts MATCH '混合'")
    ).all()
    assert [row[0] for row in hits] == [chunk.id]

    chunk.search_text = _build_search_text("向量数据库原理")
    db_session.commit()
    assert (
        db_session.execute(text("SELECT rowid FROM chunk_fts WHERE chunk_fts MATCH '混合'")).all()
        == []
    )
    assert (
        db_session.execute(text("SELECT rowid FROM chunk_fts WHERE chunk_fts MATCH '向量'")).all()
        != []
    )

    db_session.delete(chunk)
    db_session.commit()
    assert (
        db_session.execute(text("SELECT rowid FROM chunk_fts WHERE chunk_fts MATCH '向量'")).all()
        == []
    )


def test_backfill_search_text_fills_legacy_rows(db_session: Session) -> None:
    chunk = _create_chunk(db_session, "窄依赖影响恢复")

    filled = backfill_search_text(db_session)

    assert filled == 1
    db_session.refresh(chunk)
    assert chunk.search_text == _build_search_text("窄依赖影响恢复")
    hits = db_session.execute(
        text("SELECT rowid FROM chunk_fts WHERE chunk_fts MATCH '窄依'")
    ).all()
    assert [row[0] for row in hits] == [chunk.id]


def test_ensure_lexical_index_is_idempotent(db_session: Session) -> None:
    assert ensure_lexical_index(db_session.get_bind()) is True
    assert ensure_lexical_index(db_session.get_bind()) is True
    tables = db_session.execute(
        text("SELECT name FROM sqlite_master WHERE name='chunk_fts'")
    ).all()
    assert tables != []


def test_fts5_available_on_supported_sqlite(db_session: Session) -> None:
    assert fts5_available(db_session.get_bind()) is True


def test_ensure_chunk_columns_repairs_legacy_table(db_session: Session) -> None:
    db_session.execute(text("ALTER TABLE document_chunk DROP COLUMN search_text"))
    db_session.commit()

    ensure_chunk_columns(db_session.get_bind())

    columns = db_session.execute(text("PRAGMA table_info(document_chunk)")).all()
    assert "search_text" in [row[1] for row in columns]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH="backend"; backend\.venv\Scripts\python.exe -m pytest backend/tests/test_lexical_search.py -v -k "triggers or backfill or ensure or fts5_available"`
Expected: FAIL with "cannot import name 'backfill_search_text'"（收集即报错）。

- [ ] **Step 3: Write minimal implementation**

`lexical_search.py` 末尾追加（imports 区追加 `logging`、`from sqlalchemy import text`、`from sqlalchemy.engine import Engine`、`from sqlalchemy.orm import Session`——注意循环导入：`backfill_search_text` 需 `DocumentChunk/DocumentSection`，models 不依赖 services，无循环，放顶部 import）：

```python
import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models.document_chunk import DocumentChunk
from app.models.document_section import DocumentSection

logger = logging.getLogger(__name__)

FTS_TABLE_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(
    text,
    content='document_chunk',
    content_rowid='id',
    tokenize='unicode61'
)
""".strip()

FTS_TRIGGER_DDLS = [
    """
    CREATE TRIGGER IF NOT EXISTS chunk_fts_ai AFTER INSERT ON document_chunk BEGIN
      INSERT INTO chunk_fts(rowid, text) VALUES (new.id, new.search_text);
    END
    """.strip(),
    """
    CREATE TRIGGER IF NOT EXISTS chunk_fts_ad AFTER DELETE ON document_chunk BEGIN
      INSERT INTO chunk_fts(chunk_fts, rowid, text) VALUES ('delete', old.id, old.search_text);
    END
    """.strip(),
    """
    CREATE TRIGGER IF NOT EXISTS chunk_fts_au AFTER UPDATE ON document_chunk BEGIN
      INSERT INTO chunk_fts(chunk_fts, rowid, text) VALUES ('delete', old.id, old.search_text);
      INSERT INTO chunk_fts(rowid, text) VALUES (new.id, new.search_text);
    END
    """.strip(),
]

BACKFILL_BATCH_SIZE = 500


def fts5_available(engine: Engine) -> bool:
    with engine.connect() as connection:
        rows = connection.exec_driver_sql(
            "SELECT compile_options FROM pragma_compile_options"
        ).fetchall()
    return any("FTS5" in str(row[0]) for row in rows)


def ensure_lexical_index(engine: Engine) -> bool:
    if not fts5_available(engine):
        logger.warning("SQLite FTS5 is unavailable; lexical channel will use LIKE fallback.")
        return False
    with engine.begin() as connection:
        connection.exec_driver_sql(FTS_TABLE_DDL)
        for trigger_ddl in FTS_TRIGGER_DDLS:
            connection.exec_driver_sql(trigger_ddl)
    return True


def ensure_chunk_columns(engine: Engine) -> None:
    expected = {"section_id": "INTEGER", "search_text": "TEXT DEFAULT ''"}
    with engine.begin() as connection:
        existing = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(document_chunk)").fetchall()
        }
        for column, ddl in expected.items():
            if column not in existing:
                connection.exec_driver_sql(f"ALTER TABLE document_chunk ADD COLUMN {column} {ddl}")
                logger.info("Added missing column document_chunk.%s", column)


def backfill_search_text(db: Session, batch_size: int = BACKFILL_BATCH_SIZE) -> int:
    total = 0
    while True:
        ids = list(
            db.scalars(
                select(DocumentChunk.id)
                .where(DocumentChunk.search_text == "")
                .limit(batch_size)
            )
        )
        if not ids:
            break
        chunks = list(db.scalars(select(DocumentChunk).where(DocumentChunk.id.in_(ids))))
        section_ids = {c.section_id for c in chunks if c.section_id is not None}
        paths: dict[int, str] = {}
        if section_ids:
            paths = dict(
                db.execute(
                    select(DocumentSection.id, DocumentSection.section_path).where(
                        DocumentSection.id.in_(section_ids)
                    )
                ).all()
            )
        for chunk in chunks:
            path = paths.get(chunk.section_id, "") if chunk.section_id else ""
            chunk.search_text = _build_search_text(chunk.content, path)
        db.commit()
        total += len(chunks)
    if total:
        logger.info("Backfilled search_text for %s chunks", total)
    return total
```

`main.py` 改动（import 区追加 `from app.services.lexical_search import backfill_search_text, ensure_chunk_columns, ensure_lexical_index`；`create_app` 内）：

```python
    Base.metadata.create_all(bind=engine)
    ensure_chunk_columns(engine)
    ensure_lexical_index(engine)
    with SessionLocal() as db:
        backfill_search_text(db)
        recover_interrupted_documents(db)
```

`conftest.py` 改动（`db_session` fixture，`create_all` 后追加）：

```python
    from app.services.lexical_search import ensure_lexical_index

    Base.metadata.create_all(engine)
    ensure_lexical_index(engine)
```

（import 放函数内，避免模块 import 时序问题；注释说明原因。）

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONPATH="backend"; backend\.venv\Scripts\python.exe -m pytest backend/tests/test_lexical_search.py -q`
Expected: PASS（11/11：6 个 Task 1 + 5 个 Task 3）。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/lexical_search.py backend/app/main.py backend/tests/conftest.py backend/tests/test_lexical_search.py
git commit -m "feat: sync FTS index with triggers and backfill legacy rows"
```

---

### Task 4: 词面检索通道（含 LIKE 降级）

**Files:**
- Modify: `backend/app/services/lexical_search.py`（追加 `search_lexical` 与 `_search_like`、`_escape_like`）
- Test: `backend/tests/test_lexical_search.py`（末尾追加）

**Interfaces:**
- Consumes: Task 1 的 `to_search_text`；Task 3 的 FTS 表/触发器（conftest 已 ensure）；`DocumentChunk`/`DocumentSection`。
- Produces: `search_lexical(db: Session, kb_id: int, query: str, top_k: int) -> tuple[list[dict[str, Any]], dict[str, Any]]`（返回 `(hits, info)`；hit 与现有 vector match 同形 `chunk_id/document_id/kb_id/chunk_index/content/score/section_path`，`score` 为结果集内 min-max 归一化 bm25（best=1.0，单命中=1.0）；`info = {"returned": int, "best": float, "fallback": None | "like"}`；双字化为空返回 `([], {"returned": 0, "best": 0.0, "fallback": None})`；FTS `OperationalError`（表缺失等）自动转 LIKE 降级；融合池 `n = max(top_k*2, 10)` 由调用方决定——本函数内直接 `limit = max(top_k * 2, 10)`）。

- [ ] **Step 1: Write the failing tests**

首先把 Task 3 已写入的 import 块扩展一行（追加 `search_lexical`）：

```python
from app.services.lexical_search import (
    _build_search_text,
    backfill_search_text,
    ensure_chunk_columns,
    ensure_lexical_index,
    fts5_available,
    search_lexical,
)
```

然后在文件末尾追加测试：

```python
def _create_kb_chunks(db_session: Session) -> int:
    knowledge_base = KnowledgeBase(name="词面KB", description="", category="")
    db_session.add(knowledge_base)
    db_session.flush()
    document = Document(
        kb_id=knowledge_base.id,
        title="课程",
        file_name="课程.md",
        file_path="/tmp/课程.md",
        file_type="md",
        status="finished",
    )
    db_session.add(document)
    db_session.flush()
    section = DocumentSection(
        document_id=document.id, title="第一章", section_path="课程 / 第一章",
        section_level=1, section_order=1,
    )
    db_session.add(section)
    db_session.flush()
    for index, content in enumerate(["NameNode 是主节点", "Shuffle 原理讲解", "无关的向量内容"]):
        db_session.add(
            DocumentChunk(
                kb_id=knowledge_base.id,
                document_id=document.id,
                chunk_index=index,
                content=content,
                token_count=1,
                section_id=section.id,
                search_text=_build_search_text(content, "课程 / 第一章"),
            )
        )
    db_session.commit()
    return knowledge_base.id


def test_search_lexical_hits_chinese_term(db_session: Session) -> None:
    kb_id = _create_kb_chunks(db_session)

    hits, info = search_lexical(db_session, kb_id, "NameNode", top_k=5)

    assert [hit["content"] for hit in hits] == ["NameNode 是主节点"]
    assert hits[0]["section_path"] == "课程 / 第一章"
    assert hits[0]["score"] == 1.0
    assert info == {"returned": 1, "best": 1.0, "fallback": None}


def test_search_lexical_matches_section_path_terms(db_session: Session) -> None:
    kb_id = _create_kb_chunks(db_session)

    hits, _ = search_lexical(db_session, kb_id, "第一章", top_k=5)

    assert len(hits) == 3


def test_search_lexical_returns_empty_for_blank_terms(db_session: Session) -> None:
    kb_id = _create_kb_chunks(db_session)

    hits, info = search_lexical(db_session, kb_id, "！！！", top_k=5)

    assert hits == []
    assert info["returned"] == 0


def test_search_lexical_isolated_by_knowledge_base(db_session: Session) -> None:
    kb_id = _create_kb_chunks(db_session)
    other = KnowledgeBase(name="他库", description="", category="")
    db_session.add(other)
    db_session.commit()

    hits, _ = search_lexical(db_session, other.id, "NameNode", top_k=5)

    assert hits == []


def test_search_lexical_falls_back_to_like_without_fts_table(db_session: Session) -> None:
    kb_id = _create_kb_chunks(db_session)
    db_session.execute(text("DROP TABLE chunk_fts"))
    db_session.commit()

    hits, info = search_lexical(db_session, kb_id, "Shuffle", top_k=5)

    assert [hit["content"] for hit in hits] == ["Shuffle 原理讲解"]
    assert info["fallback"] == "like"


def test_search_like_escapes_wildcards(db_session: Session) -> None:
    kb_id = _create_kb_chunks(db_session)
    db_session.execute(text("DROP TABLE chunk_fts"))
    db_session.commit()

    hits, _ = search_lexical(db_session, kb_id, "100%", top_k=5)

    assert hits == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH="backend"; backend\.venv\Scripts\python.exe -m pytest backend/tests/test_lexical_search.py -v -k "search_lexical or search_like"`
Expected: FAIL with "cannot import name 'search_lexical'"。

- [ ] **Step 3: Write minimal implementation**

`lexical_search.py` 追加（imports 追加 `from typing import Any`、`from sqlalchemy import or_、select` 已有 select、`from sqlalchemy.exc import OperationalError`）：

```python
FTS_SEARCH_SQL = """
SELECT c.id AS chunk_id, c.kb_id AS kb_id, c.document_id AS document_id,
       c.chunk_index AS chunk_index, c.content AS content, c.section_id AS section_id,
       bm25(chunk_fts) AS rank_value
FROM chunk_fts JOIN document_chunk AS c ON c.id = chunk_fts.rowid
WHERE chunk_fts MATCH :terms AND c.kb_id = :kb_id
ORDER BY rank_value LIMIT :limit
""".strip()


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_lexical(
    db: Session, kb_id: int, query: str, top_k: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    terms = to_search_text(query)
    if not terms:
        return [], {"returned": 0, "best": 0.0, "fallback": None}
    limit = max(top_k * 2, 10)
    try:
        rows = (
            db.execute(text(FTS_SEARCH_SQL), {"terms": terms, "kb_id": kb_id, "limit": limit})
            .mappings()
            .all()
        )
    except OperationalError:
        logger.warning("chunk_fts unavailable; lexical channel uses LIKE fallback.")
        return _search_like(db, kb_id, query, limit)
    if not rows:
        return [], {"returned": 0, "best": 0.0, "fallback": None}
    ranks = [float(row["rank_value"]) for row in rows]
    lowest, highest = min(ranks), max(ranks)
    section_ids = {row["section_id"] for row in rows if row["section_id"] is not None}
    paths: dict[int, str] = {}
    if section_ids:
        paths = dict(
            db.execute(
                select(DocumentSection.id, DocumentSection.section_path).where(
                    DocumentSection.id.in_(section_ids)
                )
            ).all()
        )
    hits = [
        {
            "chunk_id": int(row["chunk_id"]),
            "document_id": int(row["document_id"]),
            "kb_id": int(row["kb_id"]),
            "chunk_index": int(row["chunk_index"]),
            "content": str(row["content"]),
            "score": 1.0 if highest == lowest else (highest - float(row["rank_value"])) / (highest - lowest),
            "section_path": paths.get(row["section_id"], "") if row["section_id"] else "",
        }
        for row in rows
    ]
    return hits, {"returned": len(hits), "best": hits[0]["score"], "fallback": None}


def _search_like(
    db: Session, kb_id: int, query: str, limit: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pattern = f"%{_escape_like(query)}%"
    rows = (
        db.execute(
            select(DocumentChunk, DocumentSection.section_path)
            .outerjoin(DocumentSection, DocumentSection.id == DocumentChunk.section_id)
            .where(DocumentChunk.kb_id == kb_id)
            .where(
                or_(
                    DocumentChunk.content.like(pattern, escape="\\"),
                    DocumentSection.section_path.like(pattern, escape="\\"),
                )
            )
            .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
            .limit(limit)
        )
        .all()
    )
    hits = [
        {
            "chunk_id": chunk.id,
            "document_id": chunk.document_id,
            "kb_id": chunk.kb_id,
            "chunk_index": chunk.chunk_index,
            "content": chunk.content,
            "score": 1.0 / (rank + 1),
            "section_path": section_path or "",
        }
        for rank, (chunk, section_path) in enumerate(rows)
    ]
    return hits, {"returned": len(hits), "best": hits[0]["score"] if hits else 0.0, "fallback": "like"}
```

注意：`select(DocumentChunk, DocumentSection.section_path)` 返回 Row 元组 `(chunk, path)`，解包 `for rank, (chunk, section_path)` 正确。

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONPATH="backend"; backend\.venv\Scripts\python.exe -m pytest backend/tests/test_lexical_search.py -q`
Expected: PASS（17/17）。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/lexical_search.py backend/tests/test_lexical_search.py
git commit -m "feat: add lexical retrieval channel with LIKE fallback"
```

---

### Task 5: RRF 融合与 hybrid 编排

**Files:**
- Create: `backend/app/services/hybrid_search.py`
- Test: Create `backend/tests/test_hybrid_search.py`

**Interfaces:**
- Consumes: Task 4 的 `search_lexical`；现有 `vector_store_service.search(kb_id, query, top_k)`。
- Produces: `RRF_K = 60`；`VALID_CHANNELS = ("vector", "lexical", "hybrid")`；`normalize_channels(channels: str) -> str`（未知值→`"hybrid"`）；`fusion_pool_size(top_k: int) -> int`（`max(top_k*2, 10)`）；`fuse_rrf(ranked: list[list[int]], k: int = RRF_K) -> dict[int, float]`（`sum(1/(k+rank))`，rank 从 1 起）；`HybridResult(BaseModel: hits: list[dict[str, Any]], trace: dict[str, Any])`；`search_hybrid(db: Session | None, kb_id: int, query: str, top_k: int = 5, channels: str = "hybrid") -> HybridResult`（单通道直接返回该通道 hits；hybrid 按排名融合后 score 归一化 `raw / (n_nonempty * 1/(RRF_K+1))`，内容优先取 lexical 版；`db=None` 且需 lexical 时纯向量 + trace `"lexical_skipped": "no_db"`，且 `channels="lexical"`+`db=None` 时 hits 为空；trace 恒含 `mode/vector/lexical/fused_by`，单通道时另一方为 `{"returned": 0, "best": 0.0, "skipped": True}`）。

- [ ] **Step 1: Write the failing tests**

```python
import pytest
from app.services import hybrid_search as hybrid_module
from app.services.hybrid_search import (
    HybridResult,
    fuse_rrf,
    fusion_pool_size,
    normalize_channels,
    search_hybrid,
)


def test_normalize_channels_defaults_unknown_to_hybrid() -> None:
    assert normalize_channels("foo") == "hybrid"
    assert normalize_channels("vector") == "vector"


def test_fusion_pool_size_doubles_with_floor() -> None:
    assert fusion_pool_size(5) == 10
    assert fusion_pool_size(8) == 16


def test_fuse_rrf_scores_shared_hits_highest() -> None:
    fused = fuse_rrf([[1, 2, 3], [2, 1, 4]])

    assert fused[2] > fused[1] > fused[3]
    assert fused[2] == pytest.approx(1 / 61 + 1 / 61)


def test_fuse_rrf_empty_channels() -> None:
    assert fuse_rrf([]) == {}
    assert fuse_rrf([[], []]) == {}


def _hit(chunk_id: int, score: float) -> dict:
    return {
        "chunk_id": chunk_id,
        "document_id": 1,
        "kb_id": 1,
        "chunk_index": chunk_id,
        "content": f"内容{chunk_id}",
        "score": score,
        "section_path": "课程",
    }


def test_search_hybrid_fuses_both_channels(monkeypatch) -> None:
    monkeypatch.setattr(
        hybrid_module.vector_store_service, "search", lambda kb_id, query, top_k: [
            _hit(1, 0.9), _hit(2, 0.8),
        ]
    )
    monkeypatch.setattr(
        hybrid_module, "search_lexical",
        lambda db, kb_id, query, top_k: ([_hit(2, 1.0), _hit(3, 0.5)], {"returned": 2, "best": 1.0, "fallback": None}),
    )

    result = search_hybrid(object(), kb_id=1, query="测试", top_k=2, channels="hybrid")

    assert isinstance(result, HybridResult)
    assert [hit["chunk_id"] for hit in result.hits] == [2, 1]
    assert result.hits[0]["score"] == pytest.approx(1.0)
    assert result.trace["mode"] == "hybrid"
    assert result.trace["fused_by"] == "rrf_k60"
    assert result.trace["vector"]["returned"] == 2
    assert result.trace["lexical"]["returned"] == 2


def test_search_hybrid_single_channel_modes(monkeypatch) -> None:
    monkeypatch.setattr(
        hybrid_module.vector_store_service, "search", lambda kb_id, query, top_k: [_hit(1, 0.9)]
    )

    vector_only = search_hybrid(None, kb_id=1, query="测试", top_k=5, channels="vector")

    assert [hit["chunk_id"] for hit in vector_only.hits] == [1]
    assert vector_only.hits[0]["score"] == 0.9
    assert vector_only.trace["lexical"]["skipped"] is True


def test_search_hybrid_normalizes_unknown_channels(monkeypatch) -> None:
    monkeypatch.setattr(
        hybrid_module.vector_store_service, "search", lambda kb_id, query, top_k: [_hit(1, 0.9)]
    )
    monkeypatch.setattr(
        hybrid_module, "search_lexical",
        lambda db, kb_id, query, top_k: ([], {"returned": 0, "best": 0.0, "fallback": None}),
    )

    result = search_hybrid(object(), kb_id=1, query="测试", top_k=5, channels="bogus")

    assert result.trace["mode"] == "hybrid"


def test_search_hybrid_skips_lexical_without_db(monkeypatch) -> None:
    monkeypatch.setattr(
        hybrid_module.vector_store_service, "search", lambda kb_id, query, top_k: [_hit(1, 0.9)]
    )

    result = search_hybrid(None, kb_id=1, query="测试", top_k=5, channels="hybrid")

    assert [hit["chunk_id"] for hit in result.hits] == [1]
    assert result.trace["lexical_skipped"] == "no_db"
```

（期望推导 `test_search_hybrid_fuses_both_channels`：vector 排名 [1,2]，lexical 排名 [2,3]；chunk2 raw=1/61+1/61，chunk1 raw=1/61，chunk3 raw=1/62；n_nonempty=2，除数=2/61；chunk2 得 1.0；排序 [2,1]，top 2。内容取 lexical 版：chunk2 content 为 lexical 的"内容2"（两边相同，无差）。）

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH="backend"; backend\.venv\Scripts\python.exe -m pytest backend/tests/test_hybrid_search.py -v`
Expected: FAIL with "No module named 'app.services.hybrid_search'"。

- [ ] **Step 3: Write minimal implementation**

新建 `backend/app/services/hybrid_search.py`：

```python
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.services.lexical_search import search_lexical
from app.services.vector_store_service import vector_store_service

RRF_K = 60
VALID_CHANNELS = ("vector", "lexical", "hybrid")


class HybridResult(BaseModel):
    hits: list[dict[str, Any]]
    trace: dict[str, Any]


def normalize_channels(channels: str) -> str:
    return channels if channels in VALID_CHANNELS else "hybrid"


def fusion_pool_size(top_k: int) -> int:
    return max(top_k * 2, 10)


def fuse_rrf(ranked: list[list[int]], k: int = RRF_K) -> dict[int, float]:
    fused: dict[int, float] = {}
    for ranking in ranked:
        for rank, chunk_id in enumerate(ranking, start=1):
            fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return fused


def _empty_channel(skipped: Any = True) -> dict[str, Any]:
    return {"returned": 0, "best": 0.0, "skipped": skipped}


def search_hybrid(
    db: Session | None,
    kb_id: int,
    query: str,
    top_k: int = 5,
    channels: str = "hybrid",
) -> HybridResult:
    mode = normalize_channels(channels)
    pool = fusion_pool_size(top_k)
    vector_hits: list[dict[str, Any]] = []
    lexical_hits: list[dict[str, Any]] = []
    lexical_info: dict[str, Any] = {"returned": 0, "best": 0.0}
    trace: dict[str, Any] = {"mode": mode, "fused_by": "rrf_k60"}

    want_lexical = mode in ("lexical", "hybrid")
    if mode in ("vector", "hybrid"):
        vector_hits = vector_store_service.search(kb_id=kb_id, query=query, top_k=pool)
    if want_lexical and db is not None:
        lexical_hits, lexical_info = search_lexical(db, kb_id, query, pool)
    if want_lexical and db is None:
        trace["lexical_skipped"] = "no_db"

    vector_best = max((hit["score"] for hit in vector_hits), default=0.0)
    trace["vector"] = (
        {"returned": len(vector_hits), "best": vector_best}
        if mode in ("vector", "hybrid")
        else _empty_channel()
    )
    trace["lexical"] = (
        {
            "returned": lexical_info["returned"],
            "best": lexical_info["best"],
            **({"fallback": lexical_info["fallback"]} if lexical_info.get("fallback") else {}),
        }
        if want_lexical and db is not None
        else _empty_channel("no_db" if (want_lexical and db is None) else True)
    )

    if mode == "vector" or (mode == "hybrid" and not lexical_hits):
        return HybridResult(hits=vector_hits[:top_k], trace=trace)
    if mode == "lexical" or (mode == "hybrid" and not vector_hits):
        return HybridResult(hits=lexical_hits[:top_k], trace=trace)

    by_id: dict[int, dict[str, Any]] = {}
    for hit in vector_hits:
        by_id[int(hit["chunk_id"])] = hit
    for hit in lexical_hits:
        by_id[int(hit["chunk_id"])] = hit
    rankings = [
        [int(hit["chunk_id"]) for hit in vector_hits],
        [int(hit["chunk_id"]) for hit in lexical_hits],
    ]
    fused = fuse_rrf(rankings)
    ordered = sorted(fused, key=lambda chunk_id: fused[chunk_id], reverse=True)
    divisor = 2.0 * (1.0 / (RRF_K + 1))
    hits = [
        {**by_id[chunk_id], "score": fused[chunk_id] / divisor} for chunk_id in ordered[:top_k]
    ]
    return HybridResult(hits=hits, trace=trace)
```

（hybrid 双空分支：`not lexical_hits` 且 `not vector_hits` 时第一分支返回空 vector_hits，分母逻辑不触发；trace 两通道 returned 均为实际值。内容优先取 lexical 版：后写入覆盖先生效。）

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONPATH="backend"; backend\.venv\Scripts\python.exe -m pytest backend/tests/test_hybrid_search.py -v`
Expected: PASS（8/8）。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/hybrid_search.py backend/tests/test_hybrid_search.py
git commit -m "feat: fuse vector and lexical channels with RRF"
```

---

### Task 6: retrieval_channels 设置项

**Files:**
- Modify: `backend/app/services/settings_service.py`（DEFAULT_SETTINGS、`typed_settings`、`normalize_retrieval_channels`、`update_settings` 内归一化）
- Modify: `backend/app/schemas/admin.py`（Read 加 Literal 字段；Update 加 `str | None` 字段）
- Modify: `backend/app/api/admin.py`（`patch_system_settings` 显式构造追加字段）
- Test: Create `backend/tests/test_retrieval_settings.py`

**Interfaces:**
- Consumes: 无（独立设置项；`get_settings` 的 setdefault 机制自动补默认值）。
- Produces: `normalize_retrieval_channels(value: object) -> str`；`typed_settings(db)["retrieval_channels"]` 恒为三者之一；PATCH 非法值存 `"hybrid"`。

- [ ] **Step 1: Write the failing tests**

```python
from app.services.settings_service import (
    get_settings,
    normalize_retrieval_channels,
    typed_settings,
)
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_normalize_retrieval_channels() -> None:
    assert normalize_retrieval_channels("lexical") == "lexical"
    assert normalize_retrieval_channels("VECTOR") == "vector"
    assert normalize_retrieval_channels("bogus") == "hybrid"
    assert normalize_retrieval_channels(None) == "hybrid"
    assert normalize_retrieval_channels("") == "hybrid"


def test_default_settings_include_hybrid_channels(db_session: Session) -> None:
    assert get_settings(db_session)["retrieval_channels"] == "hybrid"
    assert typed_settings(db_session)["retrieval_channels"] == "hybrid"


def test_patch_channels_roundtrip(client: TestClient) -> None:
    response = client.patch("/api/admin/settings", json={"retrieval_channels": "lexical"})

    assert response.status_code == 200
    assert response.json()["retrieval_channels"] == "lexical"
    assert client.get("/api/admin/settings").json()["retrieval_channels"] == "lexical"


def test_patch_invalid_channels_normalizes_to_hybrid(client: TestClient) -> None:
    response = client.patch("/api/admin/settings", json={"retrieval_channels": "bogus"})

    assert response.status_code == 200
    assert response.json()["retrieval_channels"] == "hybrid"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH="backend"; backend\.venv\Scripts\python.exe -m pytest backend/tests/test_retrieval_settings.py -v`
Expected: FAIL with "cannot import name 'normalize_retrieval_channels'"。

- [ ] **Step 3: Write minimal implementation**

`settings_service.py`：DEFAULT_SETTINGS 追加 `"retrieval_channels": ("hybrid", "检索通道：vector、lexical 或 hybrid")`；模块追加：

```python
RETRIEVAL_CHANNELS = ("vector", "lexical", "hybrid")


def normalize_retrieval_channels(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if text in RETRIEVAL_CHANNELS else "hybrid"
```

`update_settings` 循环内首行追加：

```python
    for key, value in payload.items():
        if value is None or key not in DEFAULT_SETTINGS:
            continue
        if key == "retrieval_channels":
            value = normalize_retrieval_channels(value)
```

`typed_settings` 返回追加 `"retrieval_channels": str(values["retrieval_channels"])`。

`schemas/admin.py`：Read 追加 `retrieval_channels: Literal["vector", "lexical", "hybrid"]`；Update 追加 `retrieval_channels: str | None = Field(default=None)`（plain str 以便接受后归一化，见 spec §3 讨论；注释说明）。

`admin.py` `patch_system_settings` 构造追加 `retrieval_channels=values["retrieval_channels"]`。

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONPATH="backend"; backend\.venv\Scripts\python.exe -m pytest backend/tests/test_retrieval_settings.py -v`
Expected: PASS（4/4）。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/settings_service.py backend/app/schemas/admin.py backend/app/api/admin.py backend/tests/test_retrieval_settings.py
git commit -m "feat: add retrieval_channels setting with normalization"
```

---

### Task 7: RAG 与端点接入 hybrid

**Files:**
- Modify: `backend/app/services/rag_service.py`（`answer` 加 `db`/`channels` 参数；检索换 `search_hybrid`；trace 追加 `channels`）
- Modify: `backend/app/api/chat.py`（传 `db` 与 `config["retrieval_channels"]`）
- Modify: `backend/app/api/vector_search.py`（读设置，改调 `search_hybrid`）
- Test: `backend/tests/test_section_api.py`（末尾追加 2 个端到端测试；沿用 Task 9（Phase 1）的脚手架风格，新建本阶段脚手架）

**Interfaces:**
- Consumes: Task 5 的 `search_hybrid`；Task 6 的 `typed_settings(db)["retrieval_channels"]`。
- Produces: `answer(..., db: Session | None = None, channels: str = "hybrid")`；`retrieval_trace["channels"]`；chat/search 按设置走通道。

- [ ] **Step 1: Write the failing tests**

```python
def _upload_term_doc(client: TestClient, db_session, monkeypatch, tmp_path: Path, kb_id: int) -> None:
    from app.api import documents as documents_api
    from app.services import document_processing_service

    monkeypatch.setattr(documents_api, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(
        document_processing_service.vector_store_service, "add_chunks", lambda *args: None
    )
    monkeypatch.setattr(
        documents_api,
        "process_document",
        lambda document_id: document_processing_service.process_document_record(
            db_session, document_id
        ),
    )
    response = client.post(
        f"/api/kbs/{kb_id}/documents/upload",
        files={"file": ("term.md", "# 指南\n\nNameNode 是主节点\n", "text/markdown")},
    )
    assert response.status_code == 202


def test_chat_lexical_channel_hits_term(
    client: TestClient, db_session: Session, monkeypatch, tmp_path: Path
) -> None:
    kb = _create_kb(client, "LexicalChatKB")
    _upload_term_doc(client, db_session, monkeypatch, tmp_path, kb["id"])
    assert client.patch("/api/admin/settings", json={"retrieval_channels": "lexical"}).status_code == 200

    response = client.post("/api/chat", json={"kb_id": kb["id"], "question": "NameNode是什么"})

    assert response.status_code == 200
    body = response.json()
    assert body["sources"], "lexical channel should hit the term document"
    assert body["retrieval_trace"]["channels"]["mode"] == "lexical"
    assert body["retrieval_trace"]["channels"]["lexical"]["returned"] >= 1
    client.patch("/api/admin/settings", json={"retrieval_channels": "hybrid"})


def test_vector_search_uses_hybrid_by_default(
    client: TestClient, db_session: Session, monkeypatch, tmp_path: Path
) -> None:
    kb = _create_kb(client, "HybridSearchKB")
    _upload_term_doc(client, db_session, monkeypatch, tmp_path, kb["id"])

    response = client.post(f"/api/kbs/{kb['id']}/search", json={"query": "NameNode"})

    assert response.status_code == 200
    results = response.json()["results"]
    assert results, "hybrid search should hit the term document"
    assert results[0]["section_path"] == "term / 指南"
```

（注意：`_create_kb` 已在 `test_section_api.py` 顶部定义，直接复用。chat 测试依赖 `llm_service.available` 为 False 走本地回答——测试环境无 Key，恒成立。lexical 的 `NameNode是什么` 双字化含 NameNode 整词，命中。测试末尾把设置改回 hybrid，避免污染其他测试——conftest 的 db 是单测隔离的（内存库每测重建），此行实为防御，保留无害。）

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH="backend"; backend\.venv\Scripts\python.exe -m pytest backend/tests/test_section_api.py -v -k "lexical_channel or hybrid_by_default"`
Expected: FAIL（`retrieval_trace["channels"]` KeyError；search 未走 hybrid 但结果可能仍命中——以 trace 断言为 RED 依据；若两者都意外通过，说明实现已存在，检查后按 TDD 删除重来）。

- [ ] **Step 3: Write minimal implementation**

`rag_service.py`：import 区追加 `from sqlalchemy.orm import Session` 与 `from app.services.hybrid_search import search_hybrid`；`answer` 签名追加 `db: Session | None = None, channels: str = "hybrid"`（放在 `privacy_mode` 之后）；检索两行替换为：

```python
        hybrid = search_hybrid(
            db, kb_id=kb_id, query=retrieval_query, top_k=top_k, channels=channels
        )
        sources = hybrid.hits
        retrieval_trace = _build_retrieval_trace(sources, top_k, score_threshold)
        retrieval_trace["channels"] = hybrid.trace
```

`chat.py` 的 `rag_service.answer(` 调用追加：

```python
            privacy_mode=str(config["privacy_mode"]),
            db=db,
            channels=str(config["retrieval_channels"]),
```

`vector_search.py` 改写：

```python
from app.core.database import get_db
from app.models.knowledge_base import KnowledgeBase
from app.schemas.vector_search import VectorSearchRequest, VectorSearchResponse
from app.services.hybrid_search import search_hybrid
from app.services.settings_service import typed_settings
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/kbs", tags=["vector search"])


@router.post("/{kb_id}/search", response_model=VectorSearchResponse)
def search_knowledge_base(
    kb_id: int,
    payload: VectorSearchRequest,
    db: Session = Depends(get_db),
) -> VectorSearchResponse:
    knowledge_base = db.get(KnowledgeBase, kb_id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found.",
        )

    config = typed_settings(db)
    hybrid = search_hybrid(
        db,
        kb_id=kb_id,
        query=payload.query,
        top_k=payload.top_k,
        channels=str(config["retrieval_channels"]),
    )
    return VectorSearchResponse(query=payload.query, results=hybrid.hits)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONPATH="backend"; backend\.venv\Scripts\python.exe -m pytest backend/tests/test_section_api.py backend/tests/test_api.py backend/tests/test_rag_service.py -q`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/rag_service.py backend/app/api/chat.py backend/app/api/vector_search.py backend/tests/test_section_api.py
git commit -m "feat: route chat and search through hybrid retrieval"
```

---

### Task 8: 前端通道展示与全量质量门

**Files:**
- Modify: `frontend/src/demo/sourceFormat.js`（追加 `formatChannelLabel`）
- Create: `frontend/src/demo/channelLabel.test.js`（与 `sourceFormat.test.js` 放同目录；命名区分被测主题）
- Modify: `frontend/src/demo/views/SettingsView.vue`（`retrievalChannels` ref + watch + save + 三段选择器 + 动态 badge）
- Modify: `frontend/src/demo/views/AssistantView.vue`（`channelLabel` computed + 依据汇总行展示）
- Docs: 无

**Interfaces:**
- Consumes: Task 6 的设置字段；Task 7 的 `trace.channels.mode`。
- Produces: `formatChannelLabel(trace) -> string`（`hybrid`→`混合检索`，`vector`→`语义检索`，`lexical`→`词面检索`，lexical 含 `fallback` 时后缀`（兼容模式）`，无 trace/无 mode 返回 `""`）。

- [ ] **Step 1: Write the failing tests**

```js
import { describe, expect, it } from 'vitest'
import { formatChannelLabel } from './sourceFormat'

describe('formatChannelLabel', () => {
  it('labels hybrid mode', () => {
    expect(formatChannelLabel({ channels: { mode: 'hybrid', fused_by: 'rrf_k60' } })).toBe('混合检索')
  })

  it('labels single-channel modes', () => {
    expect(formatChannelLabel({ channels: { mode: 'vector' } })).toBe('语义检索')
    expect(formatChannelLabel({ channels: { mode: 'lexical' } })).toBe('词面检索')
  })

  it('marks LIKE fallback', () => {
    expect(formatChannelLabel({ channels: { mode: 'lexical', lexical: { fallback: 'like' } } })).toBe(
      '词面检索（兼容模式）',
    )
  })

  it('returns empty for missing trace', () => {
    expect(formatChannelLabel(null)).toBe('')
    expect(formatChannelLabel({})).toBe('')
    expect(formatChannelLabel({ channels: { mode: 'bogus' } })).toBe('')
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend; npm test -- channelLabel`
Expected: FAIL with "formatChannelLabel is not a function"（import 成功但 undefined——若报 resolve 错误同样接受，判定标准：测试不通过）。

- [ ] **Step 3: Write minimal implementation**

`sourceFormat.js` 追加：

```js
const CHANNEL_LABELS = { hybrid: '混合检索', vector: '语义检索', lexical: '词面检索' }

export function formatChannelLabel(trace) {
  const mode = trace?.channels?.mode
  const label = CHANNEL_LABELS[mode] || ''
  if (!label) return ''
  if (mode === 'lexical' && trace.channels.lexical?.fallback) return `${label}（兼容模式）`
  return label
}
```

`SettingsView.vue` 四处改动：
1. script：`const retrievalChannels = ref('hybrid')`（放在 `temperature` 行后）；`channelOptions` 常量（script 内 `const channelOptions = [{ id: 'vector', label: '语义检索' }, { id: 'lexical', label: '词面检索' }, { id: 'hybrid', label: '混合检索' }]`）；`channelBadge` computed（`channelOptions.find(...).label || '混合检索'`）；watch 内追加 `retrievalChannels.value = value.retrieval_channels || 'hybrid'`；save payload 追加 `retrieval_channels: retrievalChannels.value`。
2. template 检索策略区：`<span class="strategy-badge">语义检索</span>` 改为 `<span class="strategy-badge">{{ channelBadge }}</span>`，并在该 header 行后插入选择器：

```html
<div class="segmented-control channel-segments"><button v-for="option in channelOptions" :key="option.id" type="button" :class="{ active: retrievalChannels === option.id }" @click="retrievalChannels = option.id; saved = false">{{ option.label }}</button></div>
```

`AssistantView.vue` 两处：import 行追加 `formatChannelLabel`（与现有 `formatSourceSubtitle` 同行引入）；`bestScore` computed 后追加 `const channelLabel = computed(() => formatChannelLabel(retrievalTrace.value))`；template 依据汇总行 `<em>最高匹配 {{ bestScore }}</em>` 后追加 `<em v-if="channelLabel">{{ channelLabel }}</em>`。

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend; npm test -- channelLabel`
Expected: PASS（4/4）。随后全量门禁：
- `$env:PYTHONPATH="backend"; pytest backend/tests -q`（仓库根目录）
- `ruff check backend` / `ruff format --check backend` / `python -m compileall -q backend/app`（用 venv python）
- `cd frontend; npm test`
- `cd frontend; npm run build`

Expected: 全部通过；后端测试数 = 73 + 本阶段新增（Task 1:6、Task 3:5、Task 4:6、Task 5:8、Task 6:4、Task 7:2 ≈ 31）。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/demo/sourceFormat.js frontend/src/demo/channelLabel.test.js frontend/src/demo/views/SettingsView.vue frontend/src/demo/views/AssistantView.vue
git commit -m "feat: show retrieval channels in settings and evidence panel"
```

---

## Self-Review

**1. Spec coverage:** §1（分词/列/FTS/降级）→Task 1–4；§2（通道/RRF/接入）→Task 4–5、Task 7；§3（设置/trace/前端）→Task 6、Task 8；§4（回填/导出/离线）→Task 3（回填+触发器覆盖删除；导出零改动）；§6 不做事项均未排入。`search_hybrid` 的 `mode` trace 键与 `normalize_channels` 为 spec 的兼容性细化（spec 要求非法值不 500，本计划落实）。

**2. Placeholder scan:** 无 TBD/TODO/"类似 Task N"；`_create_kb` 在 Task 7 复用 Phase 1 测试文件的同名 helper（同文件内，直接可用，已注明）；Task 2 期望值推导过程已写明，执行时以运行为准。

**3. Type consistency:** `to_search_text(str)->str` → `_build_search_text` → `search_text` 列/FTS 文本；`search_lexical -> tuple[hits, info]` → `search_hybrid -> HybridResult` → `answer/db+channels` → `trace["channels"]` → `formatChannelLabel`；`fusion_pool_size` 两处共用（lexical limit 与 vector top_k 均为 pool——Task 5 的 `search_hybrid` 传 pool 给两通道，Task 4 的 limit 参数接收方为 pool 值，一致）；`normalize_channels` 与 `normalize_retrieval_channels` 职责分离（前者运行时归一，后者入库归一）。

**4. Review Focus:** 5 项全部 pin 到测试（见顶部）。
