# KnowFlow 检索能力升级总体改造方案

> **For agentic workers:** 本文件是**路线图级**总体方案，按阶段（Phase）划分边界。每个 Phase 启动时，再由 `superpowers:writing-plans` 生成该阶段的逐任务 TDD 实施计划（checkbox 语法）。阶段顺序即执行顺序，除非显式标注可并行。

**Goal:** 把 KnowFlow 的检索从"扁平 chunk + 单路向量 Top-K"升级为"层级化结构记忆 + 混合检索 + 可评测、可流式、可被 Agent 自主遍历"的课程知识库检索系统，同时保持本地单用户、零额外基础设施的部署边界。

**Architecture:** 事实数据仍在 SQLite，向量索引仍是可重建的 Chroma 缓存。核心改造集中在三处：(1) 解析层输出带层级的结构化文档树而非纯文本；(2) 检索层从单路向量变为多路（向量 + 词面）RRF 融合；(3) 问答层从固定 pipeline 增加受控工具调用能力。所有阶段都不引入 Redis/PostgreSQL/Celery 等外部依赖。

**Tech Stack:** Python 3.13、FastAPI、SQLAlchemy 2.0、Pydantic、SQLite、Chroma、DashScope/Qwen、pypdf/python-docx/python-pptx、pytest、Vitest。新增依赖只在确实需要时加入（见各阶段）。

**Spec:** 本方案承接并细化既有文档：
- `docs/工程化推进计划书.md`（KnowFlow 1.0 目标架构与缺口表）
- `docs/技术方案.md`（V1 架构与数据边界）
- `README.md`（下一阶段路线图 1-6 项）

---

## 全局约束（所有阶段共同遵守）

1. **部署边界不变**：后端默认监听 `127.0.0.1`，不引入 Redis / PostgreSQL / 对象存储 / Celery；任务系统保持进程内（Phase 5 只做"持久化+恢复"增强，不换中间件）。
2. **数据边界不变**：SQLite 是事实源，Chroma 是可重建索引。任何阶段都不能让 Chroma 成为单点事实来源；索引损坏必须可从 SQLite chunk 重建。
3. **API Key 只在 `backend/.env`**，不提交 Git；新依赖不得硬编码密钥或模型名。
4. **向后兼容既有契约**：`/api/chat`、`/api/kbs/{kb_id}/search`、`/api/documents/{id}/chunks` 的现有响应字段不能删除或改名，只能新增字段，保证前端在升级窗口内不破。
5. **每阶段必须自带测试**：后端 pytest 覆盖、Ruff 检查、`ruff format`、`python -m compileall` 必须全部通过；涉及前端改动时追加 Vitest 与 `npm run build`。CI 基线（后端 19 项起步）只增不减。
6. **每个 Phase 一个 Git commit 序列**，commit message 用 `feat:`/`refactor:`/`test:`/`docs:` 前缀，遵循 `CONTRIBUTING.md`。
7. **无有效 `DASHSCOPE_API_KEY` 时所有新功能必须可降级到本地 hashing embedding / 本地抽取式回答**，离线开发与测试不能被云端 API 阻塞。

---

## 阶段总览与依赖关系

```text
Phase 1 层级化 Section 模型 ──┬──> Phase 2 混合检索(BM25+向量 RRF)
                             │         │
                             │         └──> Phase 4 检索评测集  ──┐
                             │                                   │
                             └──> Phase 3 表格结构化提取 ────────┤
                                                                 │
Phase 5 SSE 流式 + 任务持久化（独立，可与 1-3 并行）──────────────┤
                                                                 v
                                          Phase 6 受控工具调用式 Agentic 检索
                                                                 │
                                                                 v
                                                       Phase 7 Docker 部署（收尾，最后做）
```

- **Phase 1 是关键路径**：2、3、6 都依赖它产出的层级结构。
- **Phase 5 独立**：只改问答流与任务系统，可与 1-3 并行推进。
- **Phase 4 依赖 2、3**：评测集要能衡量"混合检索 vs 单路向量""结构化表格 vs 拍平文本"的差异，否则没有对照基线。
- **Phase 6 依赖 1+4**：Agent 需要层级工具（outline/read），且需要评测集证明工具调用真的比固定 pipeline 更好。
- **Phase 7 最后做**：等其他阶段接口稳定，避免 Dockerfile 和 compose 反复改。

---

## Phase 1：层级化 Section 模型（关键路径，最高优先）

**为什么排第一**：课程资料天然是"章 → 节 → 小节"结构。当前 `text_chunker.py` 只做纯段落切分，`document_parser.py` 把标题层级完全丢弃（docx 只取 `paragraph.text`，不取 `style.name`；markdown 不解析 `#`；pdf 无结构）。后续所有阶段（混合检索的 path 加权、表格归属、Agent 的 outline/read 工具）都建立在结构之上。这是 knowhere "hierarchy-native memory" 的核心思路在 KnowFlow 的最小可行落地。

**范围（本阶段做什么）**：
1. 解析器输出结构化文档树：识别标题层级（docx 用 `paragraph.style.name` 的 `Heading N`；markdown 用 `#`/`##` 前缀；pptx 用"Slide N"作一级节点；pdf/txt 无层级时回退为单 Root）。
2. 新增 `document_section` 表：`id / document_id / parent_section_id / title / section_path / section_level / chunk_count / summary`。
3. `DocumentChunk` 增加 `section_id` 外键（可空，兼容旧数据）。
4. 检索命中结果新增 `section_path` 字段，并把它写入 Chroma metadata。
5. `rebuild-index` 和 retry 流程能正确重建 section 关系。
6. 前端 chunk 预览展示所属 section 路径。

**范围（本阶段不做什么）**：
- 不做 section 摘要的 LLM 生成（Phase 6 再做，或作为可选开关）。
- 不做跨文档图（不在本阶段）。
- 不改检索算法（仍是单路向量，只多带路径元数据）。

**文件地图**：
- 改造：`backend/app/services/document_parser.py`（输出 `ParsedDocument` 结构而非裸字符串）
- 改造：`backend/app/services/text_chunker.py`（接收结构化块，输出带 `section_path` 的 chunk 列表）
- 改造：`backend/app/services/document_processing_service.py`（落盘 section + chunk）
- 改造：`backend/app/services/vector_store_service.py`（metadata 增加 `section_path`）
- 新增模型：`backend/app/models/document_section.py`
- 改模型：`backend/app/models/document_chunk.py`（加 `section_id`）
- 新增 schema：`backend/app/schemas/document_section.py`；改 `document.py` / `chat.py` / `vector_search.py` 响应
- 改 API：`backend/app/api/documents.py`（section 预览接口）、`vector_search.py`、`chat.py`
- 测试：`backend/tests/test_document_parser.py`、`test_text_chunker.py`、新增 `test_document_section.py`
- 前端：`frontend/src/components/` chunk 预览组件

**关键接口（供后续阶段使用）**：
```python
# document_parser.py 产出
class ParsedSection(BaseModel):
    title: str
    level: int              # 1 = 一级标题
    order: int              # 文档内顺序
    content: str            # 该标题下的正文（不含子标题内容）

class ParsedDocument(BaseModel):
    sections: list[ParsedSection]
    tables: list[ParsedTable]  # Phase 3 填充，本阶段返回空列表

def parse_document_structure(file_path: Path) -> ParsedDocument: ...
# 保留 parse_document_text() 供降级/兼容

# text_chunker.py 产出
class ChunkResult(BaseModel):
    content: str
    section_path: str       # "第3章 / 3.2 MapReduce / Shuffle 原理"
    section_level: int

def split_text_structured(parsed: ParsedDocument, ...) -> list[ChunkResult]: ...
# 保留 split_text() 纯函数供测试与兼容
```

**验收标准**：
- 上传一个含多级标题的 docx/markdown，`/api/documents/{id}/chunks` 每个 chunk 带 `section_path`。
- 无标题的 txt 落到 Root，`section_path` 为文件标题，不报错。
- 旧数据库（无 section 表）能自动建表并正常运行（SQLite `CREATE TABLE IF NOT EXISTS` 兼容路径）。
- `rebuild-index` 后 section 关系完整重建。
- 后端测试 ≥ 19 + 本阶段新增全部通过；Ruff/format/compileall 通过。

**风险点**：python-docx 的 `style.name` 在中文模板里可能是"标题 1"而非 `Heading 1`，需要双重匹配；markdown 的 setext 标题（`===` 下划线）要一并支持。

---

## Phase 2：混合检索（BM25 词面 + 向量，RRF 融合）

**为什么排第二**：当前 `vector_store_service.search()` 是纯语义单路。中文课程资料里大量专有名词（`HDFS`、`NameNode`、`YARN`、`CAP`）词面匹配比语义更准，且 BM25 零 API 成本。knowhere 的 `recall` 正是 `path_content`（BM25）+ `term`（子串）两路 RRF 融合，vector 反而标为预留——说明在结构化语料上词面检索价值很高。

**范围**：
1. 引入 SQLite FTS5（Python 标准库 `sqlite3` 自带，零新依赖）为 `document_chunk.content` 建全文索引；若 FTS5 不可用，降级到 `LIKE` 子串匹配。
2. 词面检索通道：对 `content`（+ Phase 1 的 `section_path`）做 BM25/子串检索，返回 chunk_id + 分数。
3. 向量检索通道：复用现有 Chroma `search`。
4. RRF 融合器：`score_rrf(rank_lists, k=60)` 标准倒数排名融合。
5. `/api/kbs/{kb_id}/search` 和 `/api/chat` 的 `retrieval_trace` 增加 `channels` 字段（`vector` / `lexical` / 各自分数），前端可展示走了哪些通道。
6. `admin/settings` 增加 `RETRIEVAL_CHANNELS` 开关（`vector` / `lexical` / `hybrid`），默认 `hybrid`。

**范围（不做什么）**：不做重排模型（rerank）——单独列未来项；不做跨语言分词器优化，用 FTS5 默认 + jieba 可选开关。

**文件地图**：
- 新增：`backend/app/services/retrieval/lexical_search.py`（FTS5/LIKE 通道）
- 新增：`backend/app/services/retrieval/rrf.py`（融合器纯函数）
- 新增：`backend/app/services/retrieval/hybrid_search.py`（编排）
- 改造：`backend/app/services/vector_store_service.py`（暴露检索接口给融合器）
- 改造：`backend/app/services/rag_service.py`（调用 hybrid_search，trace 记录通道）
- 改 API/schema：`vector_search.py`、`chat.py`、`admin.py`
- 测试：`backend/tests/test_lexical_search.py`、`test_rrf.py`、`test_hybrid_search.py`

**关键接口**：
```python
def search_lexical(db: Session, kb_id: int, query: str, top_k: int) -> list[SearchHit]: ...
def fuse_rrf(channels: dict[str, list[SearchHit]], k: int = 60) -> list[SearchHit]: ...
def search_hybrid(db: Session, kb_id: int, query: str, top_k: int,
                  channels: str = "hybrid") -> HybridResult: ...
# HybridResult.hits + HybridResult.trace（各通道原始命中与分数）
```

**验收标准**：
- 一个含专业术语的知识库，查 "NameNode"，hybrid 命中优于纯向量（人工抽检 + Phase 4 评测量化）。
- FTS5 不可用环境自动降级到 LIKE 且日志告警，不崩溃。
- `trace.channels` 正确反映实际使用的通道。
- 无 API Key 离线环境下，`vector` 通道用 hashing fallback，`lexical` 通道正常，hybrid 仍可用。

**风险点**：FTS5 与 SQLite WAL 模式的并发写；中文分词需要 `simple` tokenizer + 双字索引兜底，否则 BM25 对中文召回差。这是本阶段最大的技术不确定性，需在任务计划里先做分词可行性验证。

---

## Phase 3：表格结构化提取

**为什么排第三**：大数据课程资料里表格密度高（参数对照表、命令表、算法对比）。当前 `document_parser.py` 把表格拍平成 ` | ` 分隔的字符串塞进正文，结构信息全丢。knowhere 把表格存为独立 HTML 资产并支持 SQL 查询；KnowFlow 不必做 SQL 查询，但**至少把表格保留为结构化 block**。

**范围**：
1. 解析器输出 `ParsedTable`：`headers / rows / source_section_path / row_count / col_count`。
2. `document_chunk` 增加 `chunk_type`（`text` / `table`）；table chunk 的 `content` 存 Markdown 表格或 HTML，`content_metadata`（JSON）存结构化数据。
3. 检索时 table chunk 单独计分，命中后前端以表格组件渲染（而非纯文本）。
4. 表格归属到 Phase 1 的 section（`section_id`）。
5. 支持表格内容检索（词面 + 向量都能命中表格 chunk）。

**范围（不做什么）**：不做 `query_table` 式 SQL 查询；不做大表分页；不做图片表格 OCR。

**文件地图**：
- 改造：`document_parser.py`（docx/pptx 表格提取结构化；pdf 表格若 pypdf 拿不到则保持现状并记录限制）
- 改模型：`document_chunk.py`（`chunk_type`、`content_metadata` JSON 列）
- 改 schema：`document_chunk.py`
- 前端：chunk 预览按 `chunk_type` 渲染表格组件
- 测试：`test_document_parser.py` 扩展表格用例

**验收标准**：docx 含表格文档上传后，`/api/documents/{id}/chunks` 出现 `chunk_type: "table"` 的 chunk，前端渲染成真实表格；检索能命中表格内容。

---

## Phase 4：检索评测集（Recall@K / MRR / 拒答率）

**为什么排第四**：Phase 1-3 做完，没有评测集就无法证明"层级化""混合检索""结构化表格"真的提升了检索质量。knowhere 有专门 eval 脚本（`run_agentic_router_eval.py`）。这一阶段是把"我觉得更好"变成"数据证明更好"。

**范围**：
1. 建立离线评测语料：一份课程资料 + 20-50 条标注 query（每条标注期望命中的 chunk_id 或 section_id）。
2. 评测指标：Recall@K、MRR、拒答准确率（无依据问题应拒答）、同义改写稳定性（同一问题换三种问法，命中一致性）。
3. 评测脚本：`backend/scripts/eval_retrieval.py`，对比 `vector` / `lexical` / `hybrid` 三通道，输出 JSON 报告。
4. 评测脚本可在 CI 中以 `--smoke` 小规模模式运行（避免每条 PR 跑全量）。
5. 把评测结果写入 `docs/` 形成基线文档。

**范围（不做什么）**：不做自动化 query 生成；不做 LLM-as-judge 的回答质量评分（成本高，列未来项）。

**文件地图**：
- 新增：`backend/tests/fixtures/eval_corpus/`（资料 + 标注）
- 新增：`backend/scripts/eval_retrieval.py`
- 新增：`backend/app/services/eval/metrics.py`（Recall@K / MRR 纯函数，可单测）
- 测试：`backend/tests/test_eval_metrics.py`
- 文档：`docs/检索评测基线.md`

**验收标准**：`python scripts/eval_retrieval.py --channels hybrid,vector,lexical` 输出报告；hybrid 的 Recall@5 明显不低于 vector；指标函数有单元测试。

**依赖**：Phase 2（要能切换通道）、Phase 3（表格用例进语料）。

---

## Phase 5：SSE 流式回答 + 任务持久化（可与 1-3 并行）

**为什么排这里**：README 路线图第 1、3 项。用户等待体验差（当前整段返回），且进程被杀后 `processing` 文档卡死。knowhere 有 ADR-0005（SSE 流式检索进度）。这一阶段**不依赖** Phase 1-3，可并行。

**范围**：
1. `/api/chat` 增加 SSE 端点（`/api/chat/stream`），流式返回 token、引用片段、trace；前端 EventSource 消费。
2. 请求取消（前端断开即停止生成）与有限重试（指数退避，最多 2 次）。
3. 后台任务持久化：把文档处理任务状态写入 SQLite（`job` 表：`status / started_at / updated_at / heartbeat`），启动时 `startup_recovery.py` 扫描超时 `processing` 任务并重置为 `failed` 可重试。
4. 前端首屏优化：拆分 `App.vue` 管理视图，按需加载 Element Plus（目标 bundle < 800 KB）。

**文件地图**：
- 新增：`backend/app/api/chat_stream.py`、`backend/app/services/llm_service.py` 流式接口
- 改造：`backend/app/services/document_processing_service.py`（心跳更新）
- 新增模型：`backend/app/models/job.py`
- 改造：`backend/app/services/startup_recovery.py`
- 前端：`frontend/src/` SSE composable + 路由拆分
- 测试：`test_chat_stream.py`、`test_startup_recovery.py`、`test_job_heartbeat.py`

**验收标准**：流式回答可逐 token 显示；关闭浏览器后后端停止生成；强杀后端再启动，卡住的 `processing` 文档被标记为可重试；前端 bundle 体积下降。

---

## Phase 6：受控工具调用式 Agentic 检索

**为什么排第六**：knowhere 的核心差异化是 Retrieval 2.0——不给固定 pipeline，而给 Agent 一套 corpus 工具（`outline` / `grep` / `recall` / `read` / `neighbors`）。KnowFlow 的课程场景同样受益：学生问"第三章哪里讲了 Shuffle"，Agent 先 `outline` 定位章节再 `read` 精读，比一把 Top-K 更准。**但必须受控**（工程化计划书明确"不允许模型无限自主循环"）。

**范围**：
1. 定义工具集（先做 3 个最有价值的）：
   - `kb_outline`：列出知识库/文档的 section 树与摘要
   - `kb_recall`：混合检索（复用 Phase 2）
   - `kb_read`：按 section_path 或 chunk_id 精读正文/表格
2. 工具注册表 + JSON Schema 定义；LLM 用 Qwen function calling。
3. 受控执行循环：最大步数（如 4 步）、最大 token 预算、每步工具调用白名单、全程 trace 记录。
4. `/api/chat` 增加 `mode: "agent"` 开关，默认仍为 `rag`（固定 pipeline），保证现有行为不变。
5. 前端展示 Agent 执行轨迹（每一步调了什么工具、返回了什么）。
6. 用 Phase 4 评测集对比 `agent` 模式 vs `rag` 模式的准确率。

**范围（不做什么）**：不做 MCP Server（本地单用户用不上外部 Agent 协议）；不做有副作用的工具（不开放写操作）；不做跨知识库工具。

**文件地图**：
- 新增：`backend/app/services/agent/tools/`（每个工具一个文件 + schema）
- 新增：`backend/app/services/agent/registry.py`、`executor.py`（受控循环）、`budget.py`
- 改造：`backend/app/services/rag_service.py`（增加 agent 模式分支）
- 改 schema/API：`chat.py`
- 前端：Agent 轨迹可视化组件
- 测试：每个工具单测 + executor 步数上限/预算耗尽测试

**验收标准**：`mode: "agent"` 能多步检索后作答；执行轨迹完整展示；步数/token 超限自动降级为固定 RAG；评测集上 agent 模式的结构类问题准确率高于 rag 模式。

**依赖**：Phase 1（outline/read 需要 section 树）、Phase 4（证明 agent 更好）。

---

## Phase 7：Docker 部署（收尾）

**为什么最后做**：接口和依赖稳定后再容器化，避免 Dockerfile/compose 反复改。

**范围**：
1. 后端多阶段镜像（Python 3.13-slim + requirements 分层缓存）。
2. 前端构建产物由后端静态托管或 nginx 提供。
3. `docker-compose.yml`：backend + frontend，数据卷挂载 `storage/`。
4. `.env.example` 完整化；`docs/部署指南.md`。
5. 健康检查端点 + 容器 `HEALTHCHECK`。
6. CI 增加镜像构建冒烟测试。

**验收标准**：`docker compose up -d` 后 `http://localhost` 可用；上传、检索、问答全流程通过；数据卷持久化跨重启保留。

---

## 各阶段与既有路线图的对应关系

| 本方案阶段 | README 路线图项 | 工程化计划书缺口项 |
|---|---|---|
| Phase 1 | （新增）| 文档入库结构化 |
| Phase 2 | 5（评测集相关）| 检索：缺少关键词检索 |
| Phase 3 | （新增）| 文档入库：表格结构化 |
| Phase 4 | 5. RAG 评测集 | 质量：缺少离线评测 |
| Phase 5 | 1（SSE）+ 3（任务队列）| 对话：流式输出；入库：任务重试 |
| Phase 6 | 4（认证授权之外）+ 工程化"Agent 模式" | Agent：工具选择与多步执行 |
| Phase 7 | 6. Docker 部署 | 运维：容器化 |

**注意**：README 路线图第 2 项"拆分 App.vue + 按需加载 Element Plus"已并入 Phase 5；第 4 项"Alembic 迁移 + 用户认证授权"**本方案刻意延后**——它与"本地单用户"定位冲突，且 Phase 1 的 section 表用 SQLite `CREATE TABLE IF NOT EXISTS` 兼容路径即可。若未来确定要多用户，再单独立项（参考 knowhere 的 Stripe/RBAC 层，但对 KnowFlow 是过度设计）。

---

## Review Focus（最容易踩坑、但单测不一定覆盖的五类输入）

以下是跨阶段的易错点，各阶段任务计划里必须针对性补测试：

1. **无标题/纯正文文档**：txt 和某些 pdf 没有任何标题，Phase 1 的 section 树必须优雅回退到单 Root，不能抛异常或产出空 chunk。
2. **中文标题样式名**：python-docx 中文模板的 `style.name` 可能是 `"标题 1"` 而非 `"Heading 1"`，Phase 1 必须双重匹配，否则中文 docx 全部落到 Root，层级功能静默失效。
3. **空文档与超大文档**：0 字节文件、只有空白页的 pdf、超大单段落（超过 chunk_size 的长正文）在 Phase 1/2 的所有路径上都不能死循环或 OOM。
4. **FTS5 不可用环境**：某些 SQLite 构建不带 FTS5，Phase 2 必须自动降级到 LIKE 并记录日志，不能让检索整体不可用。
5. **并发与中断**：文档正在处理时被强杀、重建索引中途失败、删除文档与检索同时发生——这些竞态在 Phase 1（落盘 section）、Phase 5（心跳恢复）里必须有用例覆盖，而不是假设"单用户不会并发"。

---

## 执行方式

本总体方案完成后，**不立即写代码**。每启动一个 Phase 时：

1. 用 `superpowers:brainstorming` 快速对齐该阶段的取舍（尤其是 Phase 2 的中文分词方案、Phase 6 的工具集边界）。
2. 用 `superpowers:writing-plans` 生成该阶段的逐任务 TDD 计划，保存到 `docs/superpowers/plans/2026-MM-DD-phase{N}-<name>.md`。
3. 用 `superpowers:executing-plans` 或 `subagent-driven-development` 执行。
4. 完成后跑全部测试 + Ruff + 前端构建，确认通过后 commit，并更新本文件的阶段状态。

**建议的执行节奏**：Phase 1 → Phase 2 → Phase 4（先建小评测集验证 1、2 的收益）→ Phase 3 → Phase 5（并行）→ Phase 6 → Phase 7。如果 Phase 1+2 的评测显示收益不明显，应先停下来调整方向，而不是继续堆 Phase 3/6。
