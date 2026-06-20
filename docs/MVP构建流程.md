# KnowFlow（知汇）MVP 构建流程文档

## 1. 项目定位

KnowFlow，中文名“知汇”，是一个面向大数据学习场景的多知识库 RAG 问答平台。

MVP 阶段的目标不是一次性做完整平台，而是先跑通最核心的 RAG 闭环：

```text
创建知识库 -> 上传资料 -> 文档解析 -> 文本分块 -> 向量化入库 -> 用户提问 -> 检索相关片段 -> LLM 生成回答 -> 展示答案与来源
```

只要这条链路稳定跑通，后续的网页爬取、历史会话、多知识库高级管理、系统监控、权限控制都可以逐步叠加。

## 2. MVP 边界

### 2.1 MVP 要做的功能

MVP 只保留最小但完整的可用能力：

1. 创建知识库
2. 查看知识库列表
3. 上传文档到指定知识库
4. 解析文档文本
5. 对文本进行分块
6. 调用 Embedding 模型生成向量
7. 将文本片段和向量写入存储
8. 用户选择知识库并提问
9. 检索相关文本片段
10. 调用 LLM 生成回答
11. 展示回答和引用来源

### 2.2 MVP 暂不做的功能

这些功能后续再扩展：

1. 用户注册和复杂权限
2. 网页爬虫自动入库
3. 多轮历史会话
4. 文档删除后的向量同步清理
5. Reranker 重排序
6. Token 统计和系统监控
7. 模型可视化配置页面
8. Docker Compose 部署

MVP 阶段可以先使用一个默认管理员身份，不做完整登录系统。

## 3. 推荐技术栈

为了兼顾工程实践和实现难度，MVP 推荐如下技术栈：

```text
前端：Vue3 + Element Plus
后端：FastAPI
关系数据库：SQLite 或 MySQL
向量数据库：Chroma
文档解析：pypdf / python-docx / markdown
Embedding 模型：bge-small-zh / bge-large-zh / 阿里云百炼 Embedding
LLM：通义千问 API（阿里云百炼 / DashScope）
```

MVP 建议优先使用：

```text
FastAPI + SQLite + Chroma + Vue3 + 通义千问 API
```

原因：

1. SQLite 免安装，适合快速跑通业务表。
2. Chroma 上手快，适合 MVP 阶段做向量检索。
3. FastAPI 自带 Swagger 文档，方便调试接口。
4. Vue3 + Element Plus 适合快速搭建后台管理页面。

后续工程增强时，可以把 SQLite 替换成 MySQL，把 Chroma 替换成 Milvus。

## 4. 千问模型 API 接入方案

KnowFlow 的底层大语言模型默认调用通义千问 API。MVP 阶段建议使用阿里云百炼 DashScope 的 OpenAI 兼容接口，这样后端可以继续使用 OpenAI SDK 风格的调用方式，只需要配置 API Key、BASE_URL 和模型名称。

### 4.1 环境变量

后端不要把 API Key 写死在代码中，统一从环境变量读取：

```text
DASHSCOPE_API_KEY=你的千问 API Key
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-plus
```

说明：

```text
DASHSCOPE_API_KEY：阿里云百炼 API Key
QWEN_BASE_URL：千问 OpenAI 兼容接口地址
QWEN_MODEL：默认调用的千问模型
```

MVP 阶段可以先用 `qwen-plus`，后续根据成本和效果再切换为其他千问模型。

### 4.2 后端封装原则

不要在 RAG 业务代码里直接调用千问 API，建议单独封装一个 `llm_service.py`：

```text
rag_service.py
  ↓
llm_service.py
  ↓
通义千问 API
```

这样做的好处：

1. RAG 流程和模型调用解耦。
2. 后续可以在系统设置中切换模型。
3. 面试时可以讲清楚模型适配层设计。
4. 如果千问调用参数变化，只需要改 `llm_service.py`。

### 4.3 MVP 调用流程

```text
RAG 检索得到 context
  ↓
拼接 Prompt
  ↓
llm_service 调用通义千问 Chat Completions 接口
  ↓
解析回答文本和 token usage
  ↓
返回给 rag_service
```

### 4.4 千问调用伪代码

```python
from openai import OpenAI


class QwenLLMService:
    def __init__(self, api_key: str, base_url: str, model: str):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def chat(self, system_prompt: str, user_prompt: str) -> dict:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )

        return {
            "content": response.choices[0].message.content,
            "usage": response.usage.model_dump() if response.usage else None,
        }
```

### 4.5 Embedding 模型选择

注意：RAG 系统中有两类模型：

```text
LLM：负责根据检索上下文生成回答
Embedding：负责把文档 chunk 和用户问题转成向量
```

MVP 可以有两种选择：

1. LLM 使用千问，Embedding 使用本地中文向量模型，例如 `bge-small-zh`。
2. LLM 和 Embedding 都使用阿里云百炼提供的模型服务。

为了降低初期复杂度，推荐 MVP 先采用：

```text
LLM：通义千问 API
Embedding：bge-small-zh 本地模型
```

这样可以减少每次文档入库时的 API 调用成本。后续如果想进一步贴近云服务架构，再把 Embedding 也切换到百炼模型。

## 5. MVP 系统架构

```text
前端 Vue3
  |
  | HTTP API
  v
后端 FastAPI
  |
  |-- 知识库管理模块
  |-- 文档上传模块
  |-- 文档解析与分块模块
  |-- Embedding 向量化模块
  |-- 向量检索模块
  |-- RAG 问答模块
  |
  |-- SQLite：业务数据
  |-- Chroma：向量数据
```

业务数据和向量数据分开存储：

```text
SQLite 存：知识库、文档、文本片段、来源信息
Chroma 存：文本片段向量、chunk_id、kb_id、document_id 等 metadata
```

## 6. 核心数据流

### 5.1 文档入库流程

```text
用户选择知识库
  ↓
上传 PDF / TXT / Markdown
  ↓
后端保存原始文件
  ↓
解析文档正文
  ↓
清洗文本
  ↓
按 chunk_size 和 overlap 分块
  ↓
保存 document 和 document_chunk 记录
  ↓
调用 Embedding 模型生成向量
  ↓
写入 Chroma
  ↓
返回文档处理成功
```

### 5.2 问答流程

```text
用户选择知识库并输入问题
  ↓
后端生成问题向量
  ↓
在 Chroma 中按 kb_id 过滤检索 Top-K chunk
  ↓
读取相关 chunk 的正文和来源信息
  ↓
构造 RAG Prompt
  ↓
调用 LLM
  ↓
返回回答、引用来源和相似度分数
```

## 7. MVP 页面设计

MVP 前端只需要 4 个页面。

### 6.1 首页 / 工作台

展示系统的基本信息：

```text
知识库数量
文档数量
文本片段数量
最近上传文档
```

### 6.2 知识库管理页

功能：

```text
创建知识库
查看知识库列表
进入某个知识库
```

字段：

```text
知识库名称
知识库描述
知识库分类
创建时间
文档数量
```

### 6.3 文档管理页

功能：

```text
选择知识库
上传文档
查看文档列表
查看处理状态
```

MVP 支持的文档格式：

```text
.txt
.md
.pdf
```

### 6.4 问答页

推荐布局：

```text
左侧：知识库选择
中间：问题输入区 + 回答展示区
右侧：引用来源列表
```

问答页是 MVP 最重要的展示页面，必须清晰展示：

```text
用户问题
AI 回答
引用文档标题
引用片段内容
相似度分数
来源位置
```

## 8. 数据库表设计

### 7.1 knowledge_base

```text
id             主键
name           知识库名称
description    知识库描述
category       分类，例如 Hadoop / Spark / Hive
created_at     创建时间
updated_at     更新时间
```

### 7.2 document

```text
id             主键
kb_id          所属知识库 ID
title          文档标题
file_name      原始文件名
file_path      文件保存路径
file_type      文件类型
status         状态：pending / processing / finished / failed
error_message  失败原因
created_at     创建时间
updated_at     更新时间
```

### 7.3 document_chunk

```text
id             主键
kb_id          知识库 ID
document_id    文档 ID
chunk_index    分块序号
content        分块正文
token_count    估算 token 数
metadata       JSON 元数据
created_at     创建时间
```

### 7.4 chat_record

MVP 可以简单保存问答记录，后续再升级为 conversation + message。

```text
id             主键
kb_id          知识库 ID
question       用户问题
answer         模型回答
sources        JSON 引用来源
created_at     创建时间
```

## 9. API 设计

### 8.1 知识库接口

```text
GET  /api/kbs
POST /api/kbs
GET  /api/kbs/{kb_id}
```

创建知识库请求：

```json
{
  "name": "Spark 知识库",
  "description": "用于学习 Spark 核心概念、Spark SQL、性能优化等内容",
  "category": "Spark"
}
```

### 8.2 文档接口

```text
POST /api/kbs/{kb_id}/documents/upload
GET  /api/kbs/{kb_id}/documents
GET  /api/documents/{document_id}
```

上传文档使用 `multipart/form-data`：

```text
file: spark_intro.pdf
```

### 8.3 问答接口

```text
POST /api/chat
```

请求：

```json
{
  "kb_id": 1,
  "question": "Spark RDD 和 DataFrame 有什么区别？"
}
```

响应：

```json
{
  "answer": "RDD 是 Spark 的底层弹性分布式数据集抽象，DataFrame 是带有结构化 schema 的分布式数据集合...",
  "sources": [
    {
      "document_id": 3,
      "document_title": "Spark 基础教程.pdf",
      "chunk_id": 18,
      "chunk_index": 4,
      "content": "DataFrame 是以命名列组织的分布式数据集合...",
      "score": 0.86
    }
  ]
}
```

## 10. RAG 核心实现细节

### 9.1 文本清洗

MVP 阶段先做基础清洗：

```text
去除首尾空白
合并连续空行
去除过短片段
统一换行符
过滤明显乱码
```

### 9.2 文本分块

推荐参数：

```text
chunk_size = 800
chunk_overlap = 150
```

分块策略：

```text
优先按段落切分
段落过长时再按字符长度切分
相邻 chunk 保留一定 overlap
```

### 9.3 向量检索

推荐参数：

```text
top_k = 5
score_threshold = 0.3
```

检索时必须带上 `kb_id` 过滤条件：

```text
只在用户当前选择的知识库中检索
```

这是多知识库系统的关键。

### 9.4 Prompt 模板

```text
你是 KnowFlow（知汇）中的大数据课程学习助手。
请严格基于下面的参考资料回答用户问题。
如果参考资料中没有足够信息，请明确说明“知识库中未找到足够依据”。
回答要适合大数据专业学生理解，尽量分点说明。
不要编造不存在的文档、链接或来源。

参考资料：
{context}

用户问题：
{question}
```

### 9.5 来源引用

每个被检索出来的 chunk 都要带 metadata：

```text
kb_id
document_id
document_title
chunk_id
chunk_index
score
```

前端展示时至少显示：

```text
文档标题
相关片段
相似度
```

## 11. 推荐目录结构

```text
KnowFlow/
  docs/
    MVP构建流程.md
  backend/
    app/
      main.py
      api/
      core/
      models/
      schemas/
      services/
        document_service.py
        chunk_service.py
        embedding_service.py
        vector_store_service.py
        rag_service.py
        llm_service.py
      repositories/
      utils/
    storage/
      uploads/
      chroma/
    requirements.txt
  frontend/
    src/
      api/
      views/
      components/
      router/
      stores/
    package.json
  README.md
```

## 12. 开发顺序

### 阶段 1：后端基础框架

目标：FastAPI 服务能启动，数据库能连接。

任务：

```text
创建 backend 目录
初始化 FastAPI
配置 SQLite
定义数据库模型
实现健康检查接口
```

验收标准：

```text
访问 /docs 可以看到 Swagger
访问 /api/health 返回 ok
数据库表能正常创建
```

### 阶段 2：知识库管理

目标：可以创建和查看知识库。

任务：

```text
实现 knowledge_base 表
实现 POST /api/kbs
实现 GET /api/kbs
实现 GET /api/kbs/{kb_id}
```

验收标准：

```text
可以创建 Spark、Hadoop 等知识库
可以在列表中看到已创建知识库
```

### 阶段 3：文档上传与解析

目标：可以上传文档并提取文本。

任务：

```text
实现 document 表
实现文件上传接口
保存原始文件
解析 txt / md / pdf
保存文档状态
```

验收标准：

```text
上传文档后状态为 finished
能在后端日志或接口中看到解析出的正文
```

### 阶段 4：文本分块

目标：文档能被拆成多个 chunk。

任务：

```text
实现 document_chunk 表
实现 chunk 切分函数
保存 chunk 内容
记录 chunk_index
```

验收标准：

```text
上传一个文档后，document_chunk 表中出现多条片段记录
每个 chunk 长度基本稳定
```

当前实现状态：

```text
已实现 document_chunk 表
已实现 split_text 文本分块函数
已实现 token_count 估算
已实现 GET /api/documents/{document_id}/chunks
上传文档成功后会自动生成 chunk
```

### 阶段 5：向量化入库

目标：chunk 能生成向量并写入 Chroma。

任务：

```text
封装 embedding_service
封装 vector_store_service
为每个 chunk 生成 embedding
写入 Chroma collection
metadata 中保存 kb_id / document_id / chunk_id
```

验收标准：

```text
上传文档后，Chroma 中能查到对应向量
可以用一个问题检索出相关 chunk
```

当前实现状态：

```text
已接入 Chroma PersistentClient
已实现 embedding_service 本地向量生成
已实现 vector_store_service 向量写入与查询
已实现 POST /api/kbs/{kb_id}/search
上传文档成功后会自动将 chunk 向量化并写入 Chroma
```

说明：

```text
当前 embedding_service 使用轻量本地 hashing embedding，方便 MVP 阶段离线验证完整链路。
后续可以在不改变业务接口的前提下替换为 bge-small-zh、bge-large-zh 或阿里云百炼 Embedding。
```

### 阶段 6：RAG 问答接口

目标：用户可以提问，并得到基于知识库的回答。

任务：

```text
实现 POST /api/chat
根据 question 做向量检索
构造 context
拼接 prompt
通过 llm_service 调用通义千问 API
返回 answer + sources
保存 chat_record
```

验收标准：

```text
选择 Spark 知识库提问，答案来自 Spark 文档
返回结果中包含引用来源
资料不足时能提示知识库中未找到足够依据
```

当前实现状态：

```text
已实现 llm_service 调用通义千问 OpenAI 兼容接口
已实现 rag_service：检索 chunk -> 构造 Prompt -> 调用千问
已实现 POST /api/chat
已通过 .env 管理 DASHSCOPE_API_KEY、QWEN_BASE_URL、QWEN_MODEL
已实现缺少 API Key 和千问上游异常的结构化错误提示
```

### 阶段 7：前端 MVP

目标：通过页面完成完整流程。

任务：

```text
创建 Vue3 项目
实现知识库列表页
实现文档上传页
实现问答页
展示答案和引用来源
```

验收标准：

```text
不用 Swagger，仅通过前端页面即可完成：
创建知识库 -> 上传文档 -> 提问 -> 查看答案和来源
```

## 13. MVP 测试样例

建议先准备一个小型 Spark 文档作为测试资料。

测试问题：

```text
Spark RDD 是什么？
RDD 和 DataFrame 有什么区别？
Spark 为什么需要 DAG 调度？
Spark SQL 的 Catalyst 优化器有什么作用？
```

预期效果：

```text
系统能够从 Spark 知识库检索相关片段
回答内容和上传文档一致
右侧或下方能看到引用来源
```

再准备一个 Hadoop 文档，用来测试多知识库隔离。

测试问题：

```text
HDFS 的 NameNode 有什么作用？
```

预期效果：

```text
选择 Hadoop 知识库时可以回答
选择 Spark 知识库时不应该强行回答 Hadoop 内容
```

## 14. 后续增强路线

MVP 完成后，可以按下面顺序升级。

### 13.0 已完成的作业增强

针对课程作业 1.1 RAG 系统基础用例图，KnowFlow 已在 MVP 基础上补充：

```text
历史会话
token 用量统计
系统状态面板
检索参数和 LLM 参数设置
检索过程可视化
```

新增后端接口：

```text
GET    /api/conversations
GET    /api/conversations/{conversation_id}
DELETE /api/conversations/{conversation_id}
GET    /api/admin/status
GET    /api/admin/settings
PATCH  /api/admin/settings
```

这些增强使系统从“能完成 RAG 问答”升级为“能追踪、能配置、能解释、能统计”的 RAG 原型。

### 13.1 增强一：网页资料采集

```text
输入 URL
抓取网页正文
清洗导航、页脚、广告
自动分块
自动向量化
写入指定知识库
```

### 13.2 增强二：历史会话

```text
保存 conversation
保存 message
支持继续追问
支持查看历史记录
```

### 13.3 增强三：问题改写

```text
根据历史对话将追问改写成完整问题
再进行向量检索
```

示例：

```text
第一轮：Spark RDD 是什么？
第二轮：它和 DataFrame 有什么区别？
改写后：Spark RDD 和 DataFrame 有什么区别？
```

### 13.4 增强四：检索优化

```text
向量检索 Top 20
Reranker 重排序
取 Top 5 作为上下文
设置相似度阈值
低相关度拒答
```

### 13.5 增强五：系统监控

```text
统计知识库数量
统计文档数量
统计 chunk 数量
统计提问次数
统计 token 用量
统计检索耗时
统计 LLM 生成耗时
```

### 13.6 增强六：工程部署

```text
Dockerfile
Docker Compose
MySQL
Redis
Milvus
Nginx
```

## 15. 简历表述方向

MVP 完成后可以这样写：

```text
KnowFlow（知汇）：面向大数据学习场景的多知识库 RAG 问答平台

基于 FastAPI、Vue3、SQLite/Chroma 和通义千问 API 构建课程知识库问答系统，
支持知识库创建、文档上传、文本解析、分块向量化、语义检索、RAG 问答和来源引用。
设计并实现文档处理管道和向量检索链路，通过知识库过滤、Top-K 召回、Prompt 约束和来源追踪降低模型幻觉。
```

增强版完成后可以补充：

```text
扩展实现网页资料采集、历史会话、问题改写、Token 用量统计和系统监控模块，
提升系统在真实学习场景下的可用性和工程完整度。
```

## 16. MVP 完成标准

当系统满足下面条件，就可以认为 MVP 完成：

1. 可以创建至少两个知识库，例如 Spark 和 Hadoop。
2. 每个知识库可以上传至少一个文档。
3. 文档能够被成功解析、分块和向量化。
4. 用户可以选择某个知识库提问。
5. 系统回答时只基于当前知识库检索。
6. 回答结果包含引用来源。
7. 当知识库中没有相关内容时，系统不会胡编。
8. 前端可以完整演示主流程。

MVP 的核心价值是证明 KnowFlow 的 RAG 主链路可用。后续所有增强功能，都应该围绕这条主链路继续加深。
