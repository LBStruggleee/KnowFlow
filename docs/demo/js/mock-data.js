// Mock Data for KnowFlow Demo
const MockData = {
    knowledgeBases: [
        { id: 1, name: '大数据课程', category: '大数据', description: 'Spark, Hadoop, Flink 等大数据课程资料', docCount: 24, chunkCount: 312 },
        { id: 2, name: '机器学习', category: 'AI', description: 'SVM, 决策树, 聚类等机器学习资料', docCount: 18, chunkCount: 256 },
        { id: 3, name: '深度学习', category: 'AI', description: 'CNN, RNN, Transformer 等深度学习资料', docCount: 12, chunkCount: 189 },
    ],

    documents: [
        { id: 1, title: 'Spark编程指南.pdf', type: 'PDF', status: 'finished', time: '3 分钟前', chunks: 48 },
        { id: 2, title: 'HDFS架构详解.md', type: 'Markdown', status: 'finished', time: '1 小时前', chunks: 36 },
        { id: 3, title: '大数据技术栈.pptx', type: 'PPTX', status: 'processing', time: '处理中...', chunks: null },
        { id: 4, title: 'Flink流式计算.docx', type: 'DOCX', status: 'failed', time: '失败', chunks: null },
        { id: 5, title: 'Hadoop实战手册.pdf', type: 'PDF', status: 'finished', time: '2 天前', chunks: 62 },
        { id: 6, title: 'Kafka消息队列.md', type: 'Markdown', status: 'finished', time: '3 天前', chunks: 28 },
    ],

    conversations: [
        { id: 1, title: 'Spark RDD 特点讨论', active: true },
        { id: 2, title: 'HDFS 存储原理', active: false },
        { id: 3, title: 'MapReduce 工作流程', active: false },
        { id: 4, title: 'Flink 与 Spark Streaming', active: false },
        { id: 5, title: '大数据技术选型', active: false },
    ],

    chunks: [
        { id: 1, index: 1, tokenCount: 156, content: 'Apache Spark 是一个快速、通用的集群计算系统。它提供了高级 API，支持 Java、Scala、Python 和 R 语言，同时支持高级工具包包括 Spark SQL、Spark Streaming、MLlib 和 GraphX。' },
        { id: 2, index: 2, tokenCount: 142, content: 'RDD（Resilient Distributed Dataset）是 Spark 的核心数据抽象，代表一个不可变、分区的元素集合，可以并行操作。RDD 具有容错机制，能够自动恢复丢失的分区。' },
        { id: 3, index: 3, tokenCount: 138, content: 'Spark 的主要特点包括：1）速度：比 MapReduce 快 10-100 倍；2）易用：支持多种语言 API；3）通用：支持批处理、流处理、机器学习和图计算；4）兼容性：可以在多种集群管理器上运行。' },
        { id: 4, index: 4, tokenCount: 165, content: 'Spark 的架构包括 Driver Program、Cluster Manager 和 Worker Node。Driver 负责将用户程序转换为任务，Cluster Manager 负责资源分配，Worker Node 负责执行具体的计算任务。' },
        { id: 5, index: 5, tokenCount: 148, content: 'DataFrame 和 Dataset 是 Spark SQL 提供的结构化 API。DataFrame 本质上是 Dataset[Row]，提供了关系型操作接口，支持 Catalyst 优化器和 Tungsten 执行引擎。' },
    ],

    settings: {
        topK: 5,
        threshold: 0.0,
        model: 'qwen-plus',
        temperature: 0.2,
        maxMessages: 20,
        maxChars: 16000,
    },

    systemStatus: {
        knowledgeBases: 3,
        documents: 54,
        chunks: 892,
        conversations: 12,
        messages: 156,
        tokenUsage: '45.2K',
    },

    // Simulated Q&A responses
    qaResponses: {
        '什么是 Spark RDD？': {
            answer: ## Spark RDD（弹性分布式数据集）

**RDD（Resilient Distributed Dataset）** 是 Apache Spark 的核心数据抽象，代表一个**不可变、分区**的元素集合，可以并行操作。

### 核心特性

1. **弹性（Resilient）**
   - 具有容错机制，能够自动恢复丢失的分区
   - 通过血统（Lineage）信息重新计算丢失数据

2. **分布式（Distributed）**
   - 数据自动分布到集群的多个节点
   - 支持并行计算

3. **不可变（Immutable）**
   - RDD 一旦创建就不能修改
   - 转换操作会生成新的 RDD

### 创建方式

\\\python
# 从集合创建
rdd = sc.parallelize([1, 2, 3, 4, 5])

# 从外部数据源创建
rdd = sc.textFile("hdfs://path/to/file")
\\\

### 常用操作

| 操作类型 | 示例 | 说明 |
|---------|------|------|
| 转换 | map(), filter(), flatMap() | 惰性求值，返回新 RDD |
| 行动 | count(), collect(), take() | 触发实际计算 |,
            sources: [
                { chunkId: 2, docId: 1, docTitle: 'Spark编程指南.pdf', score: 0.92, content: 'RDD（Resilient Distributed Dataset）是 Spark 的核心数据抽象，代表一个不可变、分区的元素集合，可以并行操作。' },
                { chunkId: 3, docId: 1, docTitle: 'Spark编程指南.pdf', score: 0.85, content: 'Spark 的主要特点包括：1）速度：比 MapReduce 快 10-100 倍；2）易用：支持多种语言 API...' },
            ],
            retrievalTrace: {
                requestedTopK: 5,
                returnedCount: 4,
                bestScore: 0.92,
                passedThreshold: true,
            }
        },
        'HDFS 的存储原理是什么？': {
            answer: ## HDFS 存储原理

**HDFS（Hadoop Distributed File System）** 是 Hadoop 的分布式文件系统，设计用于在廉价硬件上存储超大规模数据。

### 核心架构

1. **NameNode（名称节点）**
   - 管理文件系统命名空间
   - 存储元数据（文件目录树、块位置信息）
   - 单点故障（可通过 HA 方案解决）

2. **DataNode（数据节点）**
   - 存储实际数据块
   - 定期向 NameNode 发送心跳和块报告
   - 执行数据的读写操作

### 存储机制

- **块（Block）**：默认 128MB，文件被切分成多个块存储
- **副本（Replication）**：默认 3 份，分布在不同机架
- **写入流程**：客户端 → NameNode 获取块位置 → 写入 DataNode 管道
- **读取流程**：客户端 → NameNode 获取块位置 → 从最近的 DataNode 读取,
            sources: [
                { chunkId: 1, docId: 2, docTitle: 'HDFS架构详解.md', score: 0.89, content: 'HDFS 采用主从架构，由 NameNode 和 DataNode 组成...' },
                { chunkId: 2, docId: 2, docTitle: 'HDFS架构详解.md', score: 0.81, content: '数据块默认大小为 128MB，每个块会有多个副本分布在不同节点...' },
            ],
            retrievalTrace: {
                requestedTopK: 5,
                returnedCount: 3,
                bestScore: 0.89,
                passedThreshold: true,
            }
        },
        'MapReduce 和 Spark 有什么区别？': {
            answer: ## MapReduce vs Spark 对比

### 性能对比

| 维度 | MapReduce | Spark |
|------|-----------|-------|
| **计算模型** | 磁盘迭代 | 内存迭代 |
| **速度** | 基准 | 快 10-100 倍 |
| **延迟** | 高（分钟级） | 低（秒级） |
| **内存使用** | 低 | 高 |

### 核心差异

1. **计算方式**
   - MapReduce：每一步计算都需读写磁盘
   - Spark：支持内存中间结果复用

2. **编程模型**
   - MapReduce：仅支持 Map 和 Reduce 两种操作
   - Spark：支持丰富的转换和行动操作

3. **适用场景**
   - MapReduce：离线批处理、日志分析
   - Spark：迭代计算、流处理、机器学习

### 代码对比

\\\java
// MapReduce 实现 WordCount
map(String key, String value):
    for each word w in value:
        emit(w, 1)

reduce(String key, Iterator values):
    int sum = 0
    for each v in values:
        sum += v
    emit(key, sum)
\\\

\\\python
# Spark 实现 WordCount
rdd = sc.textFile("input")
counts = rdd.flatMap(lambda line: line.split()) \\
            .map(lambda word: (word, 1)) \\
            .reduceByKey(lambda a, b: a + b)
\\\`,
            sources: [
                { chunkId: 3, docId: 1, docTitle: 'Spark编程指南.pdf', score: 0.94, content: 'Spark 的主要特点包括：1）速度：比 MapReduce 快 10-100 倍...' },
                { chunkId: 1, docId: 5, docTitle: 'Hadoop实战手册.pdf', score: 0.78, content: 'MapReduce 是 Hadoop 的分布式计算框架，采用分而治之的思想...' },
            ],
            retrievalTrace: {
                requestedTopK: 5,
                returnedCount: 5,
                bestScore: 0.94,
                passedThreshold: true,
            }
        }
    },

    // Default response for unknown questions
    defaultResponse: {
        answer: 根据知识库中的资料，我找到了以下相关信息：

这是一个很好的问题！根据课程资料，这个主题涉及多个方面。

### 核心要点

1. **基础概念**：需要理解其基本原理和定义
2. **实际应用**：在大数据场景中的典型用法
3. **最佳实践**：行业内的推荐做法

### 建议

如果您需要更详细的解答，可以：
- 尝试更具体的问题描述
- 查看相关文档的详细内容
- 参考课程资料中的相关章节,
        sources: [
            { chunkId: 1, docId: 1, docTitle: 'Spark编程指南.pdf', score: 0.65, content: '相关内容片段...' },
        ],
        retrievalTrace: {
            requestedTopK: 5,
            returnedCount: 2,
            bestScore: 0.65,
            passedThreshold: true,
        }
    }
};

// Simulate API delay
function simulateDelay(ms = 800) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// Mock API
const MockAPI = {
    async askQuestion(question) {
        await simulateDelay(1000 + Math.random() * 500);
        const response = MockData.qaResponses[question] || MockData.defaultResponse;
        return {
            answer: response.answer,
            sources: response.sources,
            retrievalTrace: response.retrievalTrace,
            usage: {
                promptTokens: 1250,
                completionTokens: 380,
                totalTokens: 1630,
            }
        };
    },

    async uploadFile(file) {
        await simulateDelay(1500);
        return { success: true, documentId: Date.now() };
    },

    async retryDocument(docId) {
        await simulateDelay(800);
        return { success: true };
    },

    async deleteDocument(docId) {
        await simulateDelay(500);
        return { success: true };
    },

    async saveSettings(settings) {
        await simulateDelay(600);
        return { success: true };
    },

    async rebuildIndex(kbId) {
        await simulateDelay(2000);
        return { success: true, indexedChunks: 312 };
    }
};
