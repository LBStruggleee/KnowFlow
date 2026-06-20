# KnowFlow（知汇）系统 UML 图

本文档基于当前 KnowFlow MVP 后端实现绘制，覆盖知识库管理、文档上传解析、文本分块、向量化入库、向量检索和 RAG 问答流程。

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
        UC6(("查看文档分块"))
        UC7(("向量检索"))
        UC8(("RAG 提问"))
        UC9(("查看回答来源"))
        UC10(("解析文档"))
        UC11(("文本分块"))
        UC12(("生成 Embedding"))
        UC13(("写入 Chroma"))
        UC14(("调用千问 API"))
    end

    User --> UC1
    User --> UC7
    User --> UC8
    User --> UC9

    Admin --> UC1
    Admin --> UC2
    Admin --> UC3
    Admin --> UC4
    Admin --> UC5
    Admin --> UC6
    Admin --> UC7
    Admin --> UC8

    UC3 -.include.-> UC10
    UC10 -.include.-> UC11
    UC11 -.include.-> UC12
    UC12 -.include.-> UC13

    UC8 -.include.-> UC7
    UC8 -.include.-> UC14
    UC8 -.include.-> UC9
```

### 用例说明

| 参与者 | 主要用例 | 说明 |
| --- | --- | --- |
| 用户 | 查看知识库、向量检索、RAG 提问、查看回答来源 | 面向学习者，核心行为是选择知识库并提问 |
| 管理员 | 创建知识库、上传文档、查看文档分块 | 负责维护知识库和资料入库 |
| 系统内部 | 解析文档、文本分块、生成 Embedding、写入 Chroma、调用千问 API | 属于自动执行的内部流程 |

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

    class DocumentChunk {
        +int id
        +int kb_id
        +int document_id
        +int chunk_index
        +str content
        +int token_count
        +datetime created_at
    }

    class DocumentParser {
        +parse_document_text(file_path) str
        +normalize_text(text) str
        -_parse_pdf(file_path) str
        -_parse_docx(file_path) str
        -_parse_pptx(file_path) str
    }

    class TextChunker {
        +split_text(text, chunk_size, chunk_overlap) list
        +estimate_token_count(text) int
    }

    class EmbeddingService {
        +embed_text(text) list
        +embed_texts(texts) list
    }

    class VectorStoreService {
        +add_chunks(chunks) None
        +search(kb_id, query, top_k) list
    }

    class QwenLLMService {
        +chat(system_prompt, user_prompt) dict
    }

    class RagService {
        +answer(kb_id, question, top_k) dict
    }

    class KnowledgeBaseAPI {
        +create_knowledge_base()
        +list_knowledge_bases()
        +get_knowledge_base()
    }

    class DocumentAPI {
        +upload_document()
        +list_documents()
        +get_document()
        +list_document_chunks()
    }

    class VectorSearchAPI {
        +search_knowledge_base()
    }

    class ChatAPI {
        +chat()
    }

    KnowledgeBase "1" --> "0..*" Document : contains
    Document "1" --> "0..*" DocumentChunk : splits into
    KnowledgeBase "1" --> "0..*" DocumentChunk : filters

    DocumentAPI --> DocumentParser : uses
    DocumentAPI --> TextChunker : uses
    DocumentAPI --> VectorStoreService : writes vectors
    VectorStoreService --> EmbeddingService : generates embedding
    VectorSearchAPI --> VectorStoreService : searches
    ChatAPI --> RagService : calls
    RagService --> VectorStoreService : retrieves context
    RagService --> QwenLLMService : generates answer

    KnowledgeBaseAPI --> KnowledgeBase : manages
    DocumentAPI --> Document : manages
    DocumentAPI --> DocumentChunk : creates
```

### 类图说明

| 类/模块 | 作用 |
| --- | --- |
| `KnowledgeBase` | 知识库实体，表示 Spark、Hadoop、Flink 等课程知识库 |
| `Document` | 文档实体，记录上传文件、解析状态和内容预览 |
| `DocumentChunk` | 文档分块实体，是后续向量检索的基本单位 |
| `DocumentParser` | 文档解析服务，支持 `.txt`、`.md`、`.pdf`、`.docx`、`.pptx` |
| `TextChunker` | 文本分块服务，负责 chunk 切分和 token 估算 |
| `EmbeddingService` | 向量生成服务，当前为本地 hashing embedding，后续可替换为 BGE 或百炼 Embedding |
| `VectorStoreService` | Chroma 向量库服务，负责向量写入和相似度检索 |
| `QwenLLMService` | 千问模型调用服务，封装阿里云百炼 OpenAI 兼容接口 |
| `RagService` | RAG 编排服务，负责检索上下文、构造 Prompt、调用 LLM |

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
    DocAPI->>DocAPI: 保存原始文件到 storage/uploads
    DocAPI->>DB: 创建 Document，状态 processing
    DB-->>DocAPI: 返回 document_id

    DocAPI->>Parser: parse_document_text(file_path)
    Parser-->>DocAPI: 返回解析后的正文

    DocAPI->>Chunker: split_text(parsed_text)
    Chunker-->>DocAPI: 返回 chunk 列表

    loop 每个 chunk
        DocAPI->>Chunker: estimate_token_count(chunk)
        Chunker-->>DocAPI: 返回 token_count
        DocAPI->>DB: 写入 DocumentChunk
    end

    DocAPI->>Embed: embed_texts(chunks)
    Embed-->>DocAPI: 返回 embedding 列表
    DocAPI->>Chroma: upsert(chunk_id, embedding, metadata)
    Chroma-->>DocAPI: 写入成功

    DocAPI->>DB: 更新 Document 状态 finished
    DB-->>DocAPI: 更新成功
    DocAPI-->>Admin: 返回文档信息、状态和内容预览
```

### 文档入库流程说明

该流程对应接口：

```text
POST /api/kbs/{kb_id}/documents/upload
```

核心结果：

```text
文档被保存到本地 storage/uploads
解析结果被切分为 document_chunk
每个 chunk 被生成 embedding
向量和 metadata 被写入 Chroma
Document 状态变为 finished
```

## 4. RAG 问答顺序图

```mermaid
sequenceDiagram
    autonumber
    actor User as 用户
    participant ChatAPI as ChatAPI
    participant DB as SQLite
    participant Rag as RagService
    participant Vector as VectorStoreService
    participant Embed as EmbeddingService
    participant Chroma as Chroma
    participant Qwen as 通义千问 API

    User->>ChatAPI: 提交问题 kb_id + question + top_k
    ChatAPI->>DB: 查询知识库是否存在
    DB-->>ChatAPI: 返回知识库

    ChatAPI->>Rag: answer(kb_id, question, top_k)
    Rag->>Vector: search(kb_id, question, top_k)
    Vector->>Embed: embed_text(question)
    Embed-->>Vector: 返回 query embedding
    Vector->>Chroma: 按 kb_id 检索相似 chunk
    Chroma-->>Vector: 返回 Top-K chunk、metadata、distance
    Vector-->>Rag: 返回 sources

    alt 检索不到相关资料
        Rag-->>ChatAPI: 返回“知识库中未找到足够依据”
        ChatAPI-->>User: 返回拒答结果
    else 检索到相关资料
        Rag->>Rag: 构造 RAG Prompt
        Rag->>Qwen: 调用千问 Chat Completions
        Qwen-->>Rag: 返回 answer 和 token usage
        Rag-->>ChatAPI: 返回 answer + sources + usage
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
  "question": "Spark DataFrame 和 RDD 有什么区别？",
  "top_k": 5
}
```

返回结果包含：

```text
answer：千问基于检索上下文生成的回答
sources：被检索到的 chunk 来源
usage：千问 API 返回的 token 使用量
```

## 5. 向量检索顺序图

```mermaid
sequenceDiagram
    autonumber
    actor User as 用户
    participant SearchAPI as VectorSearchAPI
    participant DB as SQLite
    participant Vector as VectorStoreService
    participant Embed as EmbeddingService
    participant Chroma as Chroma

    User->>SearchAPI: 输入 kb_id、query、top_k
    SearchAPI->>DB: 查询知识库是否存在
    DB-->>SearchAPI: 返回知识库
    SearchAPI->>Vector: search(kb_id, query, top_k)
    Vector->>Embed: embed_text(query)
    Embed-->>Vector: 返回 query embedding
    Vector->>Chroma: 按 kb_id 过滤并检索 Top-K
    Chroma-->>Vector: 返回 documents、metadata、distances
    Vector-->>SearchAPI: 组装 chunk_id、content、score
    SearchAPI-->>User: 返回检索结果
```

该流程对应接口：

```text
POST /api/kbs/{kb_id}/search
```

该接口主要用于验证向量化入库是否成功，也可以作为 RAG 问答前的调试工具。

## 6. 作业 1.1 RAG 系统增强说明

课程作业给出的基础 RAG 用例图包含用户与管理员两个参与者，核心用例包括：

```text
提问、查看回答与来源、管理历史会话、创建知识库、管理知识库、
上传文档、删除文档、登录、系统设置、修改检索器、修改 LLM、
查看系统状态、查看 token 用量
```

当前 KnowFlow MVP 已经覆盖 RAG 主链路，包括：

```text
创建知识库 -> 上传文档 -> 解析分块 -> 向量化入库 -> 检索 -> 调用千问 -> 返回回答与来源
```

后续为了更完整地对应作业基础用例图，并体现创新性，建议优先扩展：

```text
历史会话
系统状态面板
token 用量统计
检索参数设置
LLM 参数设置
检索过程可视化
低相关度拒答
```

详细的作业要求对照、创新定位、增强版用例图、增强版类图和增强版顺序图，见：

```text
docs/作业要求对照与创新扩展方案.md
```
