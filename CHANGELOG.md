# Changelog

所有对 KnowFlow 的显著变更都会记录在本文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [0.3.0] - 2026-10-12

### Added

- 三通道混合检索：SQLite FTS5 词面通道（中文重叠双字分词，FTS 不可用时 LIKE 降级）与语义向量通道经 RRF（k=60）融合；`retrieval_channels` 设置（`vector`/`lexical`/`hybrid`）可配，检索过程可 trace。
- 层级化 Section 模型：文档解析输出结构化章节树并落盘 `document_section`，chunk 归属 section 并携带 `section_path`，新增 `GET /api/documents/{id}/sections` 章节树接口。
- 学习沉淀：学习记录（note/exercise/mistake）API（`/api/learning-records` CRUD），可关联来源会话与消息。
- 学习任务模式：`/api/chat` 支持 question/explain/compare/summarize/exercise 五种模式与隐私模式（local/hybrid/cloud）。
- 系统管理：Provider 状态、系统统计、流式数据导出（`GET /api/admin/export`）与二次确认数据清理（`DELETE /api/admin/data?confirmation=DELETE`）。
- 后端同源托管前端：构建 `frontend/dist` 后由 FastAPI 挂载，API 与 UI 共一来源，免 CORS。
- Vite dev/preview 代理默认同源转发 `/api`。
- 工程配套：`backend/pyproject.toml`（项目元数据与 pytest 配置）、`.pre-commit-config.yaml`、`Dockerfile` 与 `docker-compose.yml`（本地部署）、`CHANGELOG.md`。

### Changed

- 文档、README、技术方案、UML 图与代码同步（v0.3.0 口径）；产品定位更新为通用知识库。
- `frontend/package.json` 与后端 FastAPI version 统一为 `0.3.0`。
- 检索阈值分数语义明确为归一化 [0,1]，纯词面命中集在阈值比较前打折。

### Fixed

- 后端可靠性与并发修复：SQLite 写锁不再跨 LLM 调用持有，会话与用户消息先落库再调用上游；FTS 索引由触发器同步并回填遗留数据；上传/重试/删除的向量补偿清理与文档状态恢复。
- 前端修复：证据面板、检索通道展示、文档轮询退避、移动端布局与错误映射。

## [0.2.0] - 2026-10

### Added

- 后台文档处理：上传立即返回 `202 processing`，解析/分块/embedding/Chroma 写入在进程内后台任务完成；失败文档一键重试（`POST /api/documents/{id}/retry`）。
- 多轮会话：历史窗口（消息数 + 字符数）与指代消解；会话 API（`/api/conversations`）。
- 系统设置与统计：`/api/admin/settings`、`/api/admin/status`（token 用量）。
- CI（GitHub Actions）：后端 pytest、Ruff、pip-audit；前端 Vitest、build、npm audit。
- 依赖审计与安全基线（pip-audit、npm audit、SECURITY.md）。

### Changed

- README 重写为当前项目状态；Embedding 切换模型后 collection 命名隔离与索引重建（`POST /api/kbs/{kb_id}/rebuild-index`）。

## [0.1.0] - 2026-09

### Added

- 首个可运行版本：文档上传（.txt/.md/.pdf/.docx/.pptx）、解析、分块、语义 embedding（DashScope `text-embedding-v3`，无 Key 时本地 hashing fallback）、Chroma 向量检索、通义千问 RAG 问答、引用与 trace 展示。
- 知识库 CRUD、文档状态轮询与索引重建。
- Vue 3 + Vite 前端控制台。
