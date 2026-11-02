# KnowFlow 检索升级工作流（承接 2026-11 三篇 RAG 论文判断报告）

> **状态：已确认（2026-11-02 定稿），待放行执行**。本文件只定义"怎么做、按什么顺序做、每步怎么验收"，不含实现代码。
> 依据：`KnowFlow检索升级判断报告.md`（2026-11-02，对照 commit `bb4d559`）+ 仓库现状复核。
> 确认后按"任务卡"逐条执行，每条任务独立 commit。

**Goal:** 在不改变本地单用户、零额外基础设施部署边界的前提下，把报告判定"值得动手"的三件事落地：① 可量化的检索评测基线；② PDF 结构解析进入现有章节树与混合检索；③ 摄入侧提示注入规则筛查。报告判定"暂不处理"的两条路线（两阶段层级检索、LLM 上下文前置）**明确不做**。

**Architecture:** 沿用现状——SQLite 是事实源，Chroma 是可重建索引；解析层 `parse_document_structure()` 产出 `ParsedDocument`，分块层 `split_text_structured()` 产出带 `section_order/level` 的 chunk，检索层 `search_hybrid()` 做 RRF 融合。本次只在这三层上增量改造，不新增外部服务、不新增必须联网的依赖。

**Tech Stack:** Python 3.13 / FastAPI / SQLAlchemy 2.0 / SQLite FTS5 / Chroma / pypdf 6.19 / pytest / Ruff / mypy / Vue 3 + Vitest。

---

## 0. 环境前置状态（已完成，仅记录）

| 项 | 状态 |
|---|---|
| GitHub 仓库 | `LBStruggleee/KnowFlow`（public，默认分支 `main`），`gh` 已登录 |
| remote | 已由 SSH 改为 HTTPS：`https://github.com/LBStruggleee/KnowFlow.git`（原 SSH 22 端口在本机被中间设备阻断） |
| 同步状态 | `main` 与 `origin/main` 完全一致（`bb4d559`），工作区干净 |
| 本地测试基线 | 后端 `176 passed`（`pytest tests -q`） |
| 技术探针 | pypdf 6.19 的 `PageObject.extract_text(visitor_text=...)` 实测可拿到 `font_size` 与 `/BaseFont`；`PdfReader.outline` 可读真实书签 → **PDF 结构解析首版不需要新增依赖** |

---

## 1. 工作流（执行模型）

### 1.1 分支与提交

```
main ──┬─ feat/retrieval-eval-baseline   (T1) ──┐
       ├─ feat/pdf-structure             (T2) ──┼─> PR: feat/retrieval-upgrade-2026-11 → main
       └─ feat/injection-screening      (T3) ──┘
```

- 一个集成分支 `feat/retrieval-upgrade-2026-11`，按阶段切子分支；每张任务卡 = 1 个（必要时 2 个）commit。
- commit 前缀遵循仓库习惯：`feat:` / `fix:` / `test:` / `docs:` / `refactor:`。
- 每张任务卡完成即 commit；阶段完成即推送分支。**最终一次性开 PR**，不逐卡开 PR。
- 允许回滚粒度：单卡 revert 不影响同阶段其他卡。

### 1.2 每张任务卡的定义（Definition of Done）

一张卡只有同时满足以下 6 条才算完成：

1. **实现**：改动局限在卡上列出的文件范围；跨范围改动需在 commit message 里说明原因。
2. **测试**：新增/更新对应 pytest（或 Vitest）用例；覆盖卡的"验收"条目，且包含至少 1 条负向用例。
3. **门禁**：`ruff format --check backend`、`ruff check backend`、`mypy`（backend 目录）、`pytest backend/tests` 全绿。
4. **兼容**：现有 API 响应字段不删不改名，只新增；旧数据库可自动迁移（`ALTER TABLE ... ADD COLUMN` 路径）。
5. **文档**：涉及行为/配置/接口的卡，同步更新对应文档（见各卡"文档"行）。
6. **提交**：1 个语义完整的 commit，message 说明"做了什么 + 为什么"。

### 1.3 验收门禁分层

| 层级 | 内容 | 触发时机 |
|---|---|---|
| 单卡 | 该卡 pytest 子集 + ruff + mypy | 每卡 |
| 阶段 | 全量 `pytest backend/tests`、`ruff`、`mypy`、`npm run lint && npm test && npm run build` | 每阶段末 |
| 交付 | 上述全量 + 本地端到端 smoke（上传 PDF → 检索 → 问答 trace）+ 评测报告归档 | PR 前 |

### 1.4 质量硬约束（来自 AGENTS.md 与既有方案）

1. 每次改动必须 commit，可回滚。
2. 每次改动必须有对应测试，交付前全部通过。
3. 不引入 Redis/PostgreSQL/Celery/对象存储；不新增必须联网的运行时依赖。
4. 无 `DASHSCOPE_API_KEY` 时所有新功能必须可离线跑（hashing embedding + 规则筛查 + 本地评测）。

---

## 2. 阶段总览

```text
T0 基线确认（已完成）
      │
      ▼
T1 评测基线 + embedding 模式可见性   ← 其余改动的验收前提
      │
      ├──────────────┐
      ▼              ▼
T2 PDF 结构解析    T3 摄入侧注入筛查（规则版，可并行）
      │              │
      └──────┬───────┘
             ▼
T4 文档收尾 + PR 交付
```

| 阶段 | 主题 | 工作量 | 依赖 | 判定依据 |
|---|---|---|---|---|
| T1 | 检索评测基线 + embedding 模式明示 | M（约 1.5 天） | 无 | 报告行动项 1 + 末段风险 |
| T2 | PDF 结构解析（outline + 字号启发式） | L（约 3 天） | T1（验收需要基线） | 报告论文 1"部分动手" |
| T3 | 摄入侧注入筛查·规则版（**本轮不做，下一轮入口**） | S（约 1 天） | 无（建议排在 T2 后） | 报告论文 2"轻量版" |
| T4 | 文档收尾 + 全量门禁 + PR | S（约 0.5 天） | T1/T2/T3 | — |

---

## 3. 任务卡

### T1 检索评测基线 + embedding 模式可见性

**为什么第一**：报告结论——没有基线，后面任何检索改动都无法证明有效。同时，未配 key 时向量通道会静默降级为哈希词袋，若不先明示，评测结果本身会被污染。

| 卡 | 内容 | 文件范围 | 验收 |
|---|---|---|---|
| **T1.1** 指标纯函数 | `Recall@k`、`MRR`、`nDCG@k`、拒答准确率、同义改写一致性 | 新增 `backend/app/services/eval/metrics.py`、`backend/tests/test_eval_metrics.py` | 边界用例：空结果、k>命中数、并列分、单条命中；指标值与手算一致 |
| **T1.2** 黄金集 | JSONL 格式 + 加载校验器 + 首批 30 条（术语/结构定位/同义改写/无答案 四类） | 新增 `backend/tests/fixtures/eval_corpus/`、`backend/app/services/eval/corpus.py`、`test_eval_corpus.py` | 坏行给出可读错误；每条样例带 `expected_section_path` 或 `expected_keywords` |
| **T1.3** 评测 CLI | 临时 KB 建索引 → 跑 `vector/lexical/hybrid` × `真标题路径/打乱标题路径(placebo)` → 输出 JSON + Markdown | 新增 `backend/scripts/eval_retrieval.py`；复用 `document_processing_service` | `--smoke` 秒级可跑；报告注明 embedding 模式与 chunk 参数；placebo 对比表可读 |
| **T1.4** embedding 模式明示 | `/api/health` 增 `embedding_mode`（`semantic`/`hashing`）与 `degraded`；chat `retrieval_trace` 增同名字段；前端 Settings 对降级态加说明文案 | `app/api/health.py`、`app/api/admin.py`、`app/services/rag_service.py`、`frontend/src/demo/views/SettingsView.vue`、`test_api.py`/`test_rag_service.py` | 未配 key 时 `degraded=true` 且文案明确"当前为词袋匹配，非语义检索"；字段只增不删 |
| **T1.5** 基线报告 | 首次基线结果归档 | 新增 `docs/检索评测基线-2026-11.md` | 含各通道 × k 的指标表、结论、复现命令、embedding 模式 |

**测试补充要求**：T1.4 必须覆盖"有 key / 无 key"两条分支（用 monkeypatch 改 settings，不改真实 .env）。

---

### T2 PDF 结构解析

**为什么第二**：报告认定这是"现状与论文结论之间最大的落差"，且方向已被对照实验背书。

| 卡 | 内容 | 文件范围 | 验收 |
|---|---|---|---|
| **T2.1** 样本与探针 | 收集 4–6 个真实 PDF（有书签 / 仅字号 / 扫描件 / 双栏 / 中文标题），先写探针脚本量化"字号可得率、outline 可得率" | 新增 `backend/tests/fixtures/pdf/`（小体积）、临时探针脚本（不合并） | 每个样本给出 `outline_present / font_size_coverage / 页数` 结论；据此确认启发式参数 |
| **T2.2** 书签路径 | `reader.outline` → 标题树；处理 pypdf 6 返回的 `Destination`/嵌套 list；页码定位到"该标题起始页" | `app/services/document_parser.py` | 层级归一（缺失层级补齐/跳级压缩）；中文书签正确解码；空标题跳过 |
| **T2.3** 字号启发式 | `visitor_text` 收集 `(text, size, font)`，正文字号取加权众数，≥阈值倍率 + 短行 + 独立成行 → 标题；按字号分档映射 level | 同上 | 对"仅字号"样本产出 ≥2 级标题；页眉页脚/页码不被误判；正文不丢字 |
| **T2.4** 接入与回退 | `parse_document_structure` 对 `.pdf` 走结构化；无结构时平铺（保持现行为）；新增 `structure_source`（`outline`/`font`/`none`）随解析结果返回并写入处理日志 | 同上 + `app/services/document_processing_service.py` | 扫描件/无字号 PDF 不报错、退回平铺；旧 `.txt` 行为不变 |
| **T2.5** 流水线兼容 | 重试（`reset_document_for_retry`）、重建索引、section 树落盘、`search_text` 拼 `section_path` 全链路 | `document_processing_service.py`、`lexical_search.py`（如需） | 重试后 section/chunk 不重复不残留；`section_path` 参与词法索引 |
| **T2.6** 测试 | 解析单测（书签/字号/混合/扫描件/空页/单页）+ 流水线集成（memory DB + 临时 Chroma 目录） | `test_document_parser.py`、`test_section_pipeline.py` | 至少 8 个新用例，含"一个字都提不出来"的失败路径 |
| **T2.7** 基线对照验收 | 用 T1 的 CLI 跑"真标题路径 vs 打乱标题路径"placebo，比较 PDF 语料在改造前后 | `docs/检索评测基线-2026-11.md` 追加 | 结论必须写清"有增益/无增益/噪声范围内"，不允许只写通过 |
| **T2.8** 文档 | README 能力说明、`docs/技术方案.md` 解析链路 | 上述文档 | 描述与实现一致，含限制（扫描件不支持结构） |

**风险与对策**：字号在不同 PDF 里可能被 `tm/cm` 缩放（探针里已见 124.2/173.9 这类值），因此**只做相对比较，不用绝对值**；双栏/旋转页先降级为平铺并记 `structure_source=font` 的置信度，不硬切。

---

### T3 摄入侧注入筛查（规则版）

**为什么第三**：成本最低、堵最明显的洞；报告要求同时做防泄漏的小测试集。

| 卡 | 内容 | 文件范围 | 验收 |
|---|---|---|---|
| **T3.1** 规则引擎 | 中英文模式库：忽略指令类、角色劫持类、伪造引用标记（`[资料 N]`、`</source>`）、零宽/不可见字符、超长重复噪声；输出 `score` + 命中规则名 | 新增 `app/services/injection_guard.py`、`backend/tests/test_injection_guard.py` | 每条规则有正例；正常技术文档（含"忽略"等日常词）不误报（负例覆盖） |
| **T3.2** 数据模型 | `document_chunk` 增 `injection_flag`（bool/bool 语义 int）与 `injection_rules`（text）；迁移走 `ensure_chunk_columns` 的 `ADD COLUMN` 路径 | `app/models/document_chunk.py`、`app/services/lexical_search.py`（迁移）、`test_migrations.py` | 旧库自动加列；新文档落标；`rebuild-index` 后标记可重建 |
| **T3.3** 检索处置 | 命中块在 hybrid 融合后降权（默认 ×0.5）或按设置排除；`retrieval_trace` 记录 `injection_filtered` 数量 | `app/services/hybrid_search.py`、`app/services/settings_service.py`、`app/api/admin.py`、`test_hybrid_search.py` | 降权策略可配置且默认不破坏现有排序断言（新用例显式打开） |
| **T3.4** 小测试集 | 8–12 条风格匹配的注入样本 + 同风格正常样本；记录"捷径审计"结论（是否靠固定短语就能区分） | `backend/tests/fixtures/injection/`、`test_injection_guard.py` | 报告写明规则版召回/误报的实测数字，不引用论文 0.896 |
| **T3.5** 可见性（可选） | chunk 预览接口返回标记；前端展示"疑似注入"徽标 | `app/schemas/document.py`、前端 chunk 预览 | 字段只增不删；无标记时为 `false` 而非缺字段 |

**明确不做**：DistilBERT 类小模型检测器（报告列为第二期，需中文样本另行验证）。

---

### T4 收尾与交付

| 卡 | 内容 | 验收 |
|---|---|---|
| **T4.1** 文档同步 | README 路线图勾选、`docs/技术方案.md`、`docs/检索评测基线-2026-11.md` 定稿、本文件状态改为"已完成" | 文档与代码一致，无过期命令 |
| **T4.2** 全量门禁 | backend：`ruff format --check`、`ruff check`、`mypy`、`pytest --cov`；frontend：`lint`、`test`、`build` | 全绿；覆盖率不低于改造前 |
| **T4.3** 端到端 smoke | 本地起后端，上传 1 个 PDF + 1 个 md，检索/问答/重试各跑一次 | trace 中可见 `structure_source`、`embedding_mode`、`injection_filtered` |
| **T4.4** PR | 汇总 commit 列表、评测对比表、遗留项 | PR 描述含"改了什么/为什么/怎么验证/没做什么" |

---

## 4. 全局验收标准

1. `python scripts/eval_retrieval.py --smoke` 可在无 API key 环境跑通并产出报告。
2. 上传含书签 PDF 后，`/api/documents/{id}/sections` 出现 ≥2 级树；`section_path` 进入 `search_text`。
3. 扫描件/无字号 PDF 不报错，退回平铺，`structure_source=none`。
4. 注入样本 chunk 被标记，检索 trace 里有过滤计数；正常文档零误报。
5. `/api/health` 与 chat trace 能明确回答"当前向量通道是不是语义的"。
6. 后端测试数从 176 只增不减；Ruff/mypy/前端构建全绿。

---

## 5. 明确不做（本次范围外）

- 两阶段层级检索（论文实测 −0.033/−0.015）。
- LLM 生成块上下文 / Contextual Retrieval（真实 token 预算下有害，且成本不可控）。
- Bounded Provisional Visibility（场景不匹配；触发条件：共享 KB / URL 抓取 / 第三方内容源）。
- 重排模型（rerank）、jieba 分词替换、跨语言优化。
- 小模型注入检测器（第二期）。
- 多用户/认证/Alembic（与单用户定位冲突，维持现状）。

---

## 6. 风险登记

| 风险 | 影响 | 对策 |
|---|---|---|
| 评测集与索引语料同源，指标虚高 | 基线不可信 | 黄金集问题人工撰写，命中标准用 section_path 而非"我造的 chunk 恰好命中" |
| PDF 字号启发式在真实文档上不稳 | 标题误判/漏判 | T2.1 先用真实样本量化，再定阈值；不可靠即退回平铺并记录 |
| 中文注入样本少 | 规则覆盖率虚高 | T3.4 风格匹配 + 捷径审计，报告只报自测数字 |
| 评测脚本污染真实数据目录 | 用户数据受损 | 一律用临时目录（tmp path）+ 内存 SQLite，禁止写 `backend/storage/chroma` |
| 前端改动引入构建风险 | CI 失败 | 前端改动仅限文案/徽标，改动后必跑 `lint/test/build` |

---

## 7. 已确认决策（2026-11-02）

| # | 决策项 | 结论 | 对方案的影响 |
|---|---|---|---|
| 1 | 放行范围 | **先做 T1 + T2**，T3 随后单开一轮 | T3 的任务卡保留在本文件，作为下一轮入口；本轮 PR 只含 T1/T2 |
| 2 | 评测语料 | **先用仓库内合成语料（30 条四类问题）**，格式固定为 JSONL，接口留给你替换真实课程资料 | T1.2 交付"可替换的加载器 + 合成集"，不阻塞 T1.3/T2.7 |
| 3 | PDF 依赖 | **零新增依赖**：pypdf `reader.outline` + `visitor_text` 字号 | T2 不新增 requirements；复杂版式（双栏/旋转/扫描件）降级为平铺并记 `structure_source` |
| 4 | 交付方式 | **feature 分支 + PR**：`feat/retrieval-upgrade-2026-11`，每卡 1 commit，末尾一次 PR 到 `main` | 全程不直接推 `main`；PR 描述含 commit 清单、评测对比表、遗留项 |

**执行顺序（锁定）**：T1.1 → T1.2 → T1.4 → T1.3 → T1.5 → T2.1 → T2.2 → T2.3 → T2.4 → T2.5 → T2.6 → T2.7 → T2.8 → T4.2 → T4.3 → T4.4。

> T1.4（embedding 模式明示）排在 T1.3 之前：先让评测报告能记录"当前向量通道是不是语义的"，否则 T1.5 的基线数字本身带歧义。
> T2.1 是**门禁式任务**：若真实 PDF 的字号/书签可得率不足以支撑启发式，先在 T2.1 汇报并停在 T2.1，不硬写 T2.2/T2.3。
