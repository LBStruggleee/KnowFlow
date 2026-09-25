# Phase 2：混合检索（BM25 词面 + 向量 RRF）— 设计 Spec

> 状态：设计评审中。批准后由 `superpowers:writing-plans` 生成逐任务 TDD 实施计划。
> 总体方案：`docs/superpowers/plans/2026-09-24-knowflow-retrieval-upgrade.md`（Phase 2）

**Goal:** 检索从单路向量 Top-K 升级为"向量 + 词面"双通道 RRF 融合，中文课程术语可被词面命中，通道可配、过程可 trace、可离线降级。

**Architecture:** 新增 `lexical_search.py`（双字分词 + FTS5 通道 + DDL/回填）与 `hybrid_search.py`（RRF 融合编排），均为无状态函数模块；`rag_service.answer` 与 `/search` 改调 `search_hybrid`；SQLite 触发器保证 FTS 与 chunk 行自动同步；Chroma 与向量通道原样复用。

**Tech Stack:** 现有依赖即可（SQLite FTS5 为标准库自带，无编译选项缺失时才降级）。零新增依赖。

**已确认决策：**
- D1: 中文分词用重叠双字（ASCII 整词保留），已用真实语料探针验证 8/8 命中；不用 jieba，不用 trigram。
- D2: FTS 用 external-content 表 + insert/delete/update 三触发器同步；在 chunk 表加 `search_text` 预处理列（应用层写入），触发器只做列拷贝（不调自定义函数）。
- D3: 单列索引（双字化 content + 空格 + 双字化 section_path 拼合），不做列加权（YAGNI，加权等 Phase 4 评测数据再定）。
- D4: channels 只读 settings（`retrieval_channels`，默认 `hybrid`），不做单请求覆盖。
- D5: 探针证伪 `unicode61` 直查中文（连续中文被当整个词，MATCH 永不命中）——任何时候不得用原文直建 FTS 索引。

---

## 1. 分词与索引结构

### 1.1 `to_search_text(text: str) -> str`（纯函数）

```python
ASCII_WORD = re.compile(r"[A-Za-z0-9_]+")

def _is_cjk(char: str) -> bool:
    return "\u4e00" <= char <= "\u9fff"

def to_search_text(text: str) -> str:
    tokens: list[str] = []
    for match in re.finditer(r"[A-Za-z0-9_]+|[^\x00-\x7f\s]+", text):
        token = match.group(0)
        if ASCII_WORD.fullmatch(token):
            tokens.append(token)
        else:
            chars = [c for c in token if _is_cjk(c)]
            tokens.extend(chars[i] + chars[i + 1] for i in range(len(chars) - 1))
    return " ".join(tokens)
```

- ASCII（含数字下划线）连续串保留整词；CJK 连续串切重叠双字（仅相邻对，末单字丢弃，保证索引/查询同构）；标点、空白、emoji 等其余字符丢弃。
- 空输入返回 `""`；调用方（查询侧）空结果回退原文直查或返回空集（见 §2）。
- 大小写：不做归一化（unicode61 在 ASCII 侧已做 fold，CJK 无大小写）。

### 1.2 `DocumentChunk.search_text` 列

- `search_text: Mapped[str] = mapped_column(Text, default="")`。
- 内容 = `to_search_text(content) + " " + to_search_text(section_path)`（section_path 为空时只剩 content 部分；首尾 strip）。
- 写入点：`process_document_record` 建 chunk 时、`rebuild` 重解析时（复用同一构造 helper `_build_search_text(content, section_path)`，与落盘逻辑放同一模块以便复用——归属 `lexical_search.py`，processing service 导入）。
- 老数据该列为空；启动回填补写（见 §4）。

### 1.3 FTS 表与触发器（`lexical_search.py` 内 DDL）

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(
  text,
  content='document_chunk', content_rowid='id', tokenize='unicode61'
);
```
（单列：存 `search_text` 拼合文本。D3 决策：不做列加权。）

触发器（标准 external-content 三件套，`IF NOT EXISTS`）：

```sql
CREATE TRIGGER IF NOT EXISTS chunk_fts_ai AFTER INSERT ON document_chunk BEGIN
  INSERT INTO chunk_fts(rowid, text) VALUES (new.id, new.search_text);
END;
CREATE TRIGGER IF NOT EXISTS chunk_fts_ad AFTER DELETE ON document_chunk BEGIN
  INSERT INTO chunk_fts(chunk_fts, rowid, text) VALUES ('delete', old.id, old.search_text);
END;
CREATE TRIGGER IF NOT EXISTS chunk_fts_au AFTER UPDATE ON document_chunk BEGIN
  INSERT INTO chunk_fts(chunk_fts, rowid, text) VALUES ('delete', old.id, old.search_text);
  INSERT INTO chunk_fts(rowid, text) VALUES (new.id, new.search_text);
END;
```

- DDL 执行点：`ensure_lexical_index(dbapi_connection_or_engine)`，在 `main.py` lifespan（`create_all` 之后）执行一次；测试 `conftest.db_session` fixture 在 `create_all` 后执行一次；函数内幂等（全 `IF NOT EXISTS`），重复调用无害。
- FTS 可用性探测：`lexical_available(connection) -> bool`（查 `pragma_compile_options` 含 FTS5）。不可用 → 通道走 LIKE 降级（见 §4），不建表、不报错。

### 1.4 LIKE 降级

触发条件：FTS5 未编译进 SQLite，或 `chunk_fts` 表不存在（探测失败）。行为：`WHERE document_chunk.content LIKE '%q%' OR section IN ...`——用**原文 query**（非双字化）直查 `content` 与关联 section 的 `section_path`，按 `chunk_index` 排序，无 bm25 分数（`channel_score` 记为 `1.0/(rank+1)` 与 RRF 共用排名逻辑），trace 标记 `"fallback": "like"`。目标：功能不断，只是无相关性排序。

---

## 2. 检索编排

### 2.1 通道函数

```python
class ChannelHit(TypedDict):  # 与现有 match 字典同形，复用即可
    chunk_id: int; document_id: int; kb_id: int; chunk_index: int
    content: str; score: float; section_path: str

def search_lexical(db: Session, kb_id: int, query: str, top_k: int) -> list[ChannelHit]: ...
```

- 查询双字化为空（如纯标点）→ 返回 `[]`。
- FTS 查询：`SELECT c.*, bm25(chunk_fts) AS rank FROM chunk_fts JOIN document_chunk c ON c.id = chunk_fts.rowid WHERE chunk_fts MATCH :q AND c.kb_id = :kb ORDER BY rank LIMIT :n`。`channel_score` = 结果集内 min-max 归一化 bm25（best=1.0，单命中=1.0）。
- `n = max(top_k * 2, 10)`（融合池深度）。
- 向量通道：复用 `vector_store_service.search(kb_id, query, top_k=n)`，其 `score`（余弦）即 `channel_score`。

### 2.2 RRF 融合（`hybrid_search.py` 纯函数 + 编排）

```python
RRF_K = 60

def fuse_rrf(ranked_lists: list[list[int]], k: int = RRF_K) -> dict[int, float]: ...
# 返回 {chunk_id: raw_rrf}，raw = sum(1/(k+rank))，rank 从 1 起

def search_hybrid(db: Session | None, kb_id: int, query: str, top_k: int,
                  channels: str = "hybrid") -> HybridResult: ...

class HybridResult(BaseModel):
    hits: list[ChannelHit]          # 最终 top_k，score 为归一化融合分
    trace: dict[str, Any]           # {"vector": {"returned": n, "best": s}, "lexical": {...}, "fused_by": "rrf_k60", "fallback"?: "like", "lexical_skipped"?: "no_db"}
```

- 归一化：`score = raw / (n_active_channels * 1/(RRF_K+1))`，双通道第一名=1.0，保证现有 `score_threshold` 语义可用（默认 0.0 不启用，无行为变化）。
- 单通道模式（`vector`/`lexical`）：直接返回该通道 hits（score=channel_score），trace 标另一通道 `"skipped"`。
- `db=None` 且需要 lexical → 回退纯向量 + trace `"lexical_skipped": "no_db"`；若 `channels="lexical"` 且 `db=None` → hits 为空 + 同样标记（调用方 chat/search 恒传 db，此分支只防御直调）。
- hits 内容字段（content/section_path）来源：lexical 通道从 DB 行组装；向量通道从 Chroma（如 Phase 1）；融合后以任一通道的完整 hit 为准（两通道同 chunk_id 去重）。

### 2.3 接入点

- `rag_service.answer(..., db: Session | None = None)`：`retrieval_query` 构造不变；`vector_store_service.search` 调用替换为 `search_hybrid(db, kb_id, retrieval_query, top_k, channels)`；`channels` 取自调用方传入或默认 `"hybrid"`——**设置读取放在 chat.py / vector_search.py**（它们持有 db 与 typed_settings），`answer` 只收 `channels: str = "hybrid"` 参数，保持 service 层纯粹。trace 追加 `result["retrieval_trace"]["channels"] = hybrid.trace`。
- `chat.py`：`config["retrieval_channels"]` 传入 `answer(channels=...)`，同时把 `db` 传入。
- `vector_search.py`：同样读设置并传入 `db` + `channels`。

---

## 3. 设置与 trace

- `DEFAULT_SETTINGS` 加 `"retrieval_channels": ("hybrid", "检索通道：vector、lexical 或 hybrid")`；`typed_settings` 加字符串透传；`SystemSettingsRead`/`SystemSettingsUpdate` 加字段（读 schema 必填、写 schema 可选——看齐现有 `top_k` 等字段风格，执行时读 `schemas/admin.py` 确认）；`admin.py` `patch_system_settings` 显式构造追加该字段。
- 非法值（如 `"foo"`）→ 视为 `"hybrid"`（防御，不 500；`search_hybrid` 内归一化未知值）。
- `retrieval_trace["channels"]` 形如 `{"vector": {"returned": 6, "best": 0.82}, "lexical": {"returned": 6, "best": 1.0}, "fused_by": "rrf_k60"}`。
- 前端：`SettingsView.vue` 检索策略区加三段选择器（语义检索/词面检索/混合检索）绑定新设置；`AssistantView.vue` 依据汇总行展示通道标识（如"混合检索 · 6 个来源"，缺省显示兼容旧 trace）。

---

## 4. 兼容、回填与降级

- **老数据回填**：`ensure_lexical_index` 之后执行 `backfill_search_text(db)`——`UPDATE document_chunk SET search_text = ... WHERE search_text = ""` 需逐行双字化（Python 侧分批 read→compute→update→commit，日志记录行数）。触发器只管 FTS 行，不管回填。`rebuild-index` 重解析路径自然重写 search_text。
- **导出**：`/admin/export` 的 `_model_dict` 自动带 `search_text`，无需改动。
- **删库/清库**：触发器自动清理 FTS 行；`clear_all_data` 与 KB/文档删除路径无需改动（测试锁定：删除后 FTS 查不到）。
- **离线**：lexical 全本地；vector 走 hashing fallback；hybrid 照常工作。
- **阈值语义**：归一化融合分 best=1.0 仅当某 chunk 双通道第一；纯词面命中时融合分偏低是预期行为，文档说明。

---

## 5. 测试策略

- `to_search_text` 纯函数单测：中英混排、标点丢弃、末单字丢弃、空输入、纯 ASCII。
- DDL/触发器集成测试（conftest 内存库 + ensure）：insert→FTS 可查；delete→查不到；update→新文本可查旧文本查不到。
- `search_lexical`：术语命中（NameNode 类）、section_path 命中、无结果、LIKE 降级（删表模拟）。
- `fuse_rrf` 纯函数：双通道第一融合分为 1.0、单通道、空通道。
- `search_hybrid`：三模式、未知 channels 归一化、db=None 回退。
- API：settings 分页 roundtrip、`channels` trace 字段、chat/search 在 lexical-only 下可用。
- 前端：设置三段选择器绑定、依据面板通道标识兜底（纯函数或既有模式）。
- 质量门与 Phase 1 相同。

---

## 6. 不做事项

1. 不做 rerank/重排模型。
2. 不做 FTS 列加权调优（等 Phase 4 评测数据）。
3. 不做单请求 channels 覆盖（只读 settings）。
4. 不做 jieba / trigram（D1 已否决）。
5. 不做跨语言分词优化。
6. 不做 Alembic（`create_all` + `IF NOT EXISTS` DDL 足够）。

---

## Review Focus

1. 纯符号/纯标点查询（双字化为空）→ 返回空集不崩溃，trace 如实记录。
2. 中英混排长词（如 `HDFS的NameNode节点`）→ ASCII 词与双字共存，AND 语义下都能命中。
3. FTS 表缺失/FTS5 未编译 → LIKE 降级不断服务（删表模拟测试）。
4. 老数据 search_text 为空 → 启动回填后可查；回填前 hybrid 不报错（lexical 只是少命中）。
5. 非法 channels 值 → 归一化为 hybrid，不 500。
