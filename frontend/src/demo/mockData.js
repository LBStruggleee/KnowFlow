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
