# KnowFlow（知汇）系统 UML 图

> 最后更新：2026-10-12（与 v0.3.0 代码同步：层级化 Section 模型、三通道混合检索、学习记录与 admin API）

本文档基于当前 KnowFlow 后端实现绘制，覆盖知识库管理、文档上传解析、层级化分块、向量化入库、三通道混合检索（FTS5 词面 + 语义向量 + RRF 融合）和 RAG 问答流程。

## 1. 用例图

```mermaid
flowchart LR
    User["用户"]
    Admin["管理员"]

    subgraph System["KnowFlow（知汇）RAG 问答系统"]
        UC1(("查看知识库列表"))
        UC2(("创建知识库"))
        UC3(("上传文档"))
        UC4(("查看文档列表"))
        UC5(("查看文档详情"))
        UC6(("查看文档分块与章节树"))
        UC7(("混合检索"))
        UC8(("RAG 提问"))
        UC9(("查看回答来源"))
        UC10(("解析文档为章节树"))
        UC11(("文本分块"))
        UC12(("生成 Embedding"))
        UC13(("写入 Chroma 与 FTS"))
        UC14(("调用千问 API"))
        UC15(("管理学习记录"))
        UC16(("系统设置与数据管理"))
    end

    User --> UC1
    User --> UC7
    User --> UC8
    User --> UC9
    User --> UC15

    Admin --> UC1
    Admin --> UC2
    Admin --> UC3
    Admin --> UC4
    Admin --> UC5
    Admin --> UC6
    Admin --> UC7
    Admin --> UC8
    Admin --> UC16

    UC3 -.include.-> UC10
    UC10 -.include.-> UC11
    UC11 -.include.-> UC12
    UC11 -.include.-> UC13

    UC8 -.include.-> UC7
    UC8 -.include.-> UC14
    UC8 -.include.-> UC9
```

### 用例说明

| 参与者 | 主要用例 | 说明 |
| --- | --- | --- |
| 用户 | 查看知识库、混合检索、RAG 提问、查看回答来源、管理学习记录 | 面向学习者与资料使用者，核心行为是选择知识库并提问 |
| 管理员 | 创建知识库、上传文档、查看分块与章节、系统设置与数据管理 | 负责维护知识库和资料入库 |
| 系统内部 | 解析文档、文本分块、生成 Embedding、写入 Chroma 与 FTS、调用千问 API | 属于自动执行的内部流程 |

## 2. 类图

```mermaid
classDiagram
    direction LR

    class KnowledgeBase {
        +int id
        +str name
        +str description
        +str category
        +datetime created_at
        +datetime updated_at
    }

    class Document {
        +int id
        +int kb_id
        +str title
        +str file_name
        +str file_path
        +str file_type
        +str status
        +int content_length
        +str content_preview
        +str error_message
        +datetime created_at
        +datetime updated_at
    }

    class DocumentSection {
        +int id
        +int document_id
        +int parent_section_id
        +str title
        +str section_path
        +int section_level
        +int section_order
        +int chunk_count
    }

    class DocumentChunk {
        +int id
        +int kb_id
        +int document_id
        +int section_id
        +int chunk_index
        +str content
        +str search_text
        +int token_count
        +datetime created_at
    }

    class Conversation {
        +int id
        +int kb_id
        +str title
        +datetime created_at
        +datetime updated_at
    }

    class ChatMessage {
        +int id
        +int conversation_id
        +int kb_id
        +str role
        +str content
        +str sources_json
        +int prompt_tokens
        +int completion_tokens
        +int total_tokens
    }

    class LearningRecord {
        +int id
        +int kb_id
        +int conversation_id
        +int source_message_id
        +str record_type
        +str title
        +str content
        +str tags_json
        +str metadata_json
    }

    class SystemSetting {
        +str key
        +str value
        +str description
        +datetime updated_at
    }

    class DocumentParser {
        +parse_document_text(file_path) str
        +parse_structure(file_path) ParsedDocument
        +assign_parent_orders(sections) list
    }

    class TextChunker {
        +split_text(text, chunk_size, chunk_overlap) list
        +estimate_token_count(text) int
    }

    class EmbeddingService {
        +embed_text(text) list
        +embed_texts(texts) list
    }

    class LexicalSearch {
        +to_search_text(text) str
        +search_lexical(db, kb_id, query, limit) tuple
    }

    class HybridSearch {
        +search_hybrid(db, kb_id, query, top_k, channels) HybridResult
        +normalize_channels(channels) str
    }

    class VectorStoreService {
        +add_chunks(chunks) None
        +search(kb_id, query, top_k) list
        +delete_chunks(chunk_ids) None
    }

    class QwenLLMService {
        +chat(system_prompt, user_prompt) dict
    }

    class RagService {
        +answer(kb_id, question, top_k, mode, privacy_mode, channels) dict
    }

    class KnowledgeBaseAPI {
        +create_knowledge_base()
        +list_knowledge_bases()
        +rebuild_index()
    }

    class DocumentAPI {
        +upload_document()
        +list_documents()
        +get_document()
        +list_document_chunks()
        +list_document_sections()
        +retry_document()
    }

    class VectorSearchAPI {
        +search_knowledge_base()
    }

    class ChatAPI {
        +chat()
    }

    class ConversationAPI {
        +create_conversation()
        +list_conversations()
        +get_conversation()
        +delete_conversation()
    }

    class LearningRecordAPI {
        +create_learning_record()
        +list_learning_records()
        +update_learning_record()
        +delete_learning_record()
    }

    class AdminAPI {
        +get_settings()
        +patch_settings()
        +get_provider_status()
        +get_system_status()
        +export_all_data()
        +clear_all_data()
    }

    KnowledgeBase "1" --> "0..*" Document : contains
    Document "1" --> "0..*" DocumentSection : parsed into
    DocumentSection "1" --> "0..*" DocumentSection : parent of
    Document "1" --> "0..*" DocumentChunk : splits into
    DocumentSection "1" --> "0..*" DocumentChunk : groups
    KnowledgeBase "1" --> "0..*" Conversation : hosts
    Conversation "1" --> "0..*" ChatMessage : contains
    KnowledgeBase "1" --> "0..*" LearningRecord : collects
    ChatMessage "0..1" --> "0..*" LearningRecord : saved as

    DocumentAPI --> DocumentParser : uses
    DocumentAPI --> TextChunker : uses
    DocumentAPI --> VectorStoreService : writes vectors
    VectorStoreService --> EmbeddingService : generates embedding
    VectorSearchAPI --> HybridSearch : searches
    HybridSearch --> LexicalSearch : lexical channel
    HybridSearch --> VectorStoreService : vector channel
    ChatAPI --> RagService : calls
    RagService --> HybridSearch : retrieves context
    RagService --> QwenLLMService : generates answer

    KnowledgeBaseAPI --> KnowledgeBase : manages
    DocumentAPI --> Document : manages
    ConversationAPI --> Conversation : manages
    LearningRecordAPI --> LearningRecord : manages
    AdminAPI --> SystemSetting : manages
```

### 类图说明

| 类/模块 | 作用 |
| --- | --- |
| `KnowledgeBase` | 知识库实体，统一纳管企业文档、团队沉淀或个人资料 |
| `Document` | 文档实体，记录上传文件、解析状态和内容预览 |
| `DocumentSection` | 层级化章节实体，构成文档章节树，`section_path` 用于引用回查 |
| `DocumentChunk` | 文档分块实体，是检索的基本单位；`search_text` 为双字化检索列，供 FTS 使用 |
| `Conversation` / `ChatMessage` | 多轮会话与消息，`sources_json` 持久化引用快照，token 用量入库 |
| `LearningRecord` | 学习记录（note / exercise / mistake），可关联来源会话与消息 |
| `SystemSetting` | 键值系统设置（检索通道、Top K、阈值、模型、隐私模式等） |
| `DocumentParser` | 文档解析服务，支持 `.txt`、`.md`、`.pdf`、`.docx`、`.pptx`，并输出结构化章节树 |
| `TextChunker` | 文本分块服务，按 section 独立切分 chunk 并估算 token |
| `EmbeddingService` | 向量生成服务：DashScope `text-embedding-v3` 语义 embedding；无有效 API Key 时降级为本地 deterministic hashing embedding（离线开发与测试用），降级路径不影响在线语义检索的默认行为 |
| `LexicalSearch` | 词面检索通道：中文重叠双字分词 + SQLite FTS5（bm25），FTS 不可用时降级 LIKE |
| `HybridSearch` | 混合检索编排：向量 + 词面双通道 RRF（k=60）融合，通道可配、过程可 trace |
| `VectorStoreService` | Chroma 向量库服务，负责向量写入和相似度检索 |
| `QwenLLMService` | 千问模型调用服务，封装 DashScope OpenAI 兼容接口 |
| `RagService` | RAG 编排服务：混合检索、构造 Prompt（含任务模式与历史）、调用 LLM、拒答与本地降级 |

## 3. 文档入库顺序图

```mermaid
sequenceDiagram
    autonumber
    actor Admin as 管理员
    participant DocAPI as DocumentAPI
    participant DB as SQLite
    participant Parser as DocumentParser
    participant Chunker as TextChunker
    participant Embed as EmbeddingService
    participant Chroma as Chroma

    Admin->>DocAPI: 上传文档到指定知识库
    DocAPI->>DB: 查询知识库是否存在
    DB-->>DocAPI: 返回知识库
    DocAPI->>DocAPI: 校验扩展名/大小/空文件，随机文件名落盘 storage/uploads
    DocAPI->>DB: 创建 Document，状态 processing，立即返回 202

    Note over DocAPI,Chroma: 以下在进程内后台任务中执行

    DocAPI->>Parser: parse_structure(file_path)
    Parser-->>DocAPI: 返回结构化章节树（DocumentSection 列表）
    DocAPI->>DB: 写入 document_section

    DocAPI->>Chunker: 按 section 切分 chunk
    Chunker-->>DocAPI: 返回 chunk 列表（含 section_id、search_text）
    DocAPI->>DB: 写入 document_chunk（触发器同步 FTS 索引）

    DocAPI->>Embed: embed_texts(chunks)
    Embed-->>DocAPI: 返回 embedding 列表
    DocAPI->>Chroma: upsert(chunk_id, embedding, metadata 含 section_path)

    DocAPI->>DB: 更新 Document 状态 finished
    DocAPI-->>Admin: 前端轮询获得文档状态与内容预览
```

### 文档入库流程说明

该流程对应接口：

```text
POST /api/kbs/{kb_id}/documents/upload
```

核心结果：

```text
文档被保存到本地 storage/uploads
解析结果构建为 document_section 章节树
正文按 section 切分为 document_chunk（携带 section_path 与 search_text）
每个 chunk 被生成 embedding，向量与 metadata 写入 Chroma
FTS 索引由 SQLite 触发器自动同步
Document 状态变为 finished；失败时回滚并标记 failed，可重试
```

## 4. RAG 问答顺序图（混合检索）

```mermaid
sequenceDiagram
    autonumber
    actor User as 用户
    participant ChatAPI as ChatAPI
    participant DB as SQLite
    participant Rag as RagService
    participant Hybrid as HybridSearch
    participant Lexical as LexicalSearch (FTS5)
    participant Vector as VectorStoreService
    participant Embed as EmbeddingService
    participant Qwen as 通义千问 API

    User->>ChatAPI: 提交问题 kb_id + question + mode + conversation_id
    ChatAPI->>DB: 读取设置（top_k、阈值、通道、模型、隐私模式）
    ChatAPI->>DB: 获取/创建会话，落库用户消息

    ChatAPI->>Rag: answer(...)
    Rag->>Rag: 指代消解（最近用户问题）生成检索 query
    Rag->>Hybrid: search_hybrid(query, top_k, channels)

    par 词面通道（lexical/hybrid）
        Hybrid->>Lexical: search_lexical(db, kb_id, query)
        Lexical-->>Hybrid: FTS bm25 命中（FTS 不可用时 LIKE 降级）
    and 向量通道（vector/hybrid）
        Hybrid->>Vector: search(kb_id, query, pool)
        Vector->>Embed: embed_text(query)
        Embed-->>Vector: 返回 query embedding
        Vector-->>Hybrid: 按 kb_id 过滤的 Top-K chunk
    end

    Hybrid-->>Rag: RRF 融合结果 + trace（通道、降级、分数语义）

    alt 阈值未通过
        Rag-->>ChatAPI: 返回“知识库中未找到足够依据”（不调用 LLM）
        ChatAPI-->>User: 返回拒答结果
    else 隐私模式 local 或 LLM 不可用
        Rag-->>ChatAPI: 本地抽取式回答（answer_mode=local）
    else 正常生成
        Rag->>Qwen: Chat Completions（任务模式约束 + 历史 + 参考资料）
        Qwen-->>Rag: 返回 answer 和 token usage
        Rag-->>ChatAPI: answer + sources（含 section_path） + trace + usage
        ChatAPI-->>User: 展示回答与引用来源
    end
```

### RAG 问答流程说明

该流程对应接口：

```text
POST /api/chat
```

请求示例：

```json
{
  "kb_id": 1,
  "question": "文本分块有什么作用？",
  "top_k": 5,
  "mode": "question",
  "conversation_id": null
}
```

返回结果包含：

```text
answer：千问基于检索上下文生成的回答（或本地抽取式回答）
answer_mode：local / cloud；provider：实际使用的模型或本地实现
sources：被检索到的 chunk 来源（含 section_path 章节路径）
retrieval_trace：混合检索通道、RRF 融合、Top K、阈值与最高分
usage：LLM API 返回的 token 使用量
```

## 5. 混合检索顺序图

```mermaid
sequenceDiagram
    autonumber
    actor User as 用户
    participant SearchAPI as VectorSearchAPI
    participant DB as SQLite
    participant Hybrid as HybridSearch
    participant Lexical as LexicalSearch (FTS5)
    participant Vector as VectorStoreService
    participant Embed as EmbeddingService

    User->>SearchAPI: 输入 kb_id、query、top_k
    SearchAPI->>DB: 查询知识库是否存在
    SearchAPI->>Hybrid: search_hybrid(db, kb_id, query, top_k, channels)

    par 词面通道
        Hybrid->>Lexical: search_lexical(db, kb_id, query, pool)
        Lexical-->>Hybrid: 双字分词 MATCH bm25（或 LIKE 降级）
    and 向量通道
        Hybrid->>Vector: search(kb_id, query, pool)
        Vector->>Embed: embed_text(query)
        Vector-->>Hybrid: Top-K chunk、metadata、distance
    end

    Hybrid-->>SearchAPI: RRF 融合取前 Top K + trace
    SearchAPI-->>User: 返回检索结果（chunk_id、content、score、section_path）
```

该流程对应接口：

```text
POST /api/kbs/{kb_id}/search
```

通道由系统设置 `retrieval_channels`（`vector` / `lexical` / `hybrid`，默认 `hybrid`）决定；该接口主要用于验证索引入库是否成功，也可以作为 RAG 问答前的调试工具。

## 6. 管理与学习沉淀 API

当前实现已覆盖以下管理与学习沉淀端点：

```text
GET/PATCH /api/admin/settings        检索通道、Top K、阈值、模型与隐私设置
GET /api/admin/providers             LLM/embedding Provider 与索引状态
GET /api/admin/status                系统统计与 token 用量
GET /api/admin/export                流式导出全部事实数据
DELETE /api/admin/data               二次确认后清理事实数据与索引
GET/POST /api/conversations          会话列表/创建
GET/DELETE /api/conversations/{id}   会话详情/删除
GET/POST /api/learning-records       学习记录列表/创建（note/exercise/mistake）
GET/PATCH/DELETE /api/learning-records/{id}  学习记录详情/更新/删除
```
