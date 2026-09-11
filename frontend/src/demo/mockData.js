export const navItems = [
  { id: 'assistant', label: '学习助手' },
  { id: 'knowledge', label: '课程知识库' },
  { id: 'records', label: '学习记录' },
  { id: 'settings', label: '设置' },
]

export const taskModes = ['自由提问', '概念讲解', '知识对比', '章节总结', '练习生成']

export const courses = [
  { id: 1, name: 'Spark 核心原理', meta: '12 份资料 · 428 个知识片段', tone: 'green' },
  { id: 2, name: 'Flink 实时计算', meta: '8 份资料 · 261 个知识片段', tone: 'blue' },
  { id: 3, name: 'Hadoop 基础', meta: '6 份资料 · 174 个知识片段', tone: 'amber' },
]

export const sources = [
  {
    id: 1,
    badge: '1',
    title: 'Spark 编程指南.pdf',
    location: '第 3 章 · 第 24 页',
    score: '96%',
    excerpt: 'RDD 是只读的分布式对象集合，可被划分到集群多个节点并行处理。RDD 通过 lineage 记录转换关系，在分区丢失时重新计算。',
  },
  {
    id: 2,
    badge: '2',
    title: '大数据计算框架课件.pptx',
    location: '弹性分布式数据集 · 第 18 页',
    score: '91%',
    excerpt: 'RDD 的容错不依赖完整数据副本，而是依靠转换操作构成的依赖关系重新构建丢失分区。',
  },
  {
    id: 3,
    badge: '3',
    title: 'Spark 实验手册.docx',
    location: '实验二 · 缓存策略',
    score: '84%',
    excerpt: '对需要重复使用的数据集执行 persist 或 cache，可以避免沿 lineage 重复计算，但需要考虑存储级别与内存容量。',
  },
]

export const documents = [
  {
    id: 1,
    name: 'Spark 编程指南.pdf',
    type: 'PDF',
    size: '4.8 MB',
    pages: 126,
    chunks: 184,
    status: 'ready',
    updatedAt: '今天 09:42',
    tags: ['核心教材', 'RDD'],
    outline: ['Spark 概述', 'RDD 编程指南', '共享变量', 'Spark SQL'],
  },
  {
    id: 2,
    name: '大数据计算框架课件.pptx',
    type: 'PPTX',
    size: '8.2 MB',
    pages: 64,
    chunks: 97,
    status: 'ready',
    updatedAt: '昨天 16:20',
    tags: ['课堂课件', '架构'],
    outline: ['计算模型演进', 'Spark 运行架构', '弹性分布式数据集', 'Shuffle'],
  },
  {
    id: 3,
    name: 'Spark 实验手册.docx',
    type: 'DOCX',
    size: '1.6 MB',
    pages: 38,
    chunks: 82,
    status: 'ready',
    updatedAt: '9 月 10 日',
    tags: ['实验', '操作步骤'],
    outline: ['环境准备', 'RDD 基础操作', '缓存策略', '性能观察'],
  },
  {
    id: 4,
    name: 'Spark SQL 课堂笔记.md',
    type: 'MD',
    size: '86 KB',
    pages: 12,
    chunks: 34,
    status: 'processing',
    updatedAt: '刚刚',
    tags: ['个人笔记'],
    outline: ['DataFrame', 'Catalyst', '执行计划'],
  },
  {
    id: 5,
    name: '旧版课程提纲.pdf',
    type: 'PDF',
    size: '640 KB',
    pages: 18,
    chunks: 0,
    status: 'failed',
    updatedAt: '9 月 8 日',
    tags: ['课程提纲'],
    outline: [],
  },
]

export const learningRecords = [
  {
    id: 1,
    type: 'conversation',
    title: 'RDD 容错机制与缓存的关系',
    summary: '讨论 Lineage、窄依赖与宽依赖，以及缓存对重复计算的影响。',
    course: 'Spark 核心原理',
    time: '今天 10:18',
    meta: '6 条消息 · 3 个引用',
    tags: ['RDD', '容错'],
  },
  {
    id: 2,
    type: 'note',
    title: 'Spark 作业执行流程速记',
    summary: 'Application、Job、Stage、Task 的层级，以及 DAG Scheduler 划分 Stage 的依据。',
    course: 'Spark 核心原理',
    time: '昨天 21:06',
    meta: '来自 2 次对话',
    tags: ['调度', '复习'],
  },
  {
    id: 3,
    type: 'exercise',
    title: 'RDD 与 DataFrame 对比练习',
    summary: '5 道选择题、2 道简答题，覆盖类型信息、执行优化和适用场景。',
    course: 'Spark 核心原理',
    time: '昨天 19:34',
    meta: '已完成 · 6/7 正确',
    tags: ['练习', 'DataFrame'],
  },
  {
    id: 4,
    type: 'mistake',
    title: 'Shuffle 分区器选择',
    summary: '误把 HashPartitioner 的分区数量理解为由 Executor 数量决定。',
    course: 'Spark 核心原理',
    time: '9 月 9 日',
    meta: '待复习 · 第 1 次',
    tags: ['错题', 'Shuffle'],
  },
  {
    id: 5,
    type: 'conversation',
    title: 'Checkpoint 与 Savepoint 的区别',
    summary: '从一致性、用途、生命周期三个角度比较 Flink 的两种状态快照。',
    course: 'Flink 实时计算',
    time: '9 月 8 日',
    meta: '8 条消息 · 4 个引用',
    tags: ['状态管理'],
  },
]

export const providerOptions = [
  { id: 'qwen', name: 'Qwen Plus', role: '回答模型', location: '云端', status: '可用' },
  { id: 'bge', name: 'BGE-M3', role: 'Embedding', location: '本地', status: '可用' },
  { id: 'reranker', name: 'BGE Reranker v2', role: '相关性重排', location: '本地', status: '可用' },
]
