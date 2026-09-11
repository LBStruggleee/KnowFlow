<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Check,
  CircleClose,
  Clock,
  Document,
  FolderAdd,
  MoreFilled,
  Refresh,
  Search,
  UploadFilled,
} from '@element-plus/icons-vue'
import { documents as initialDocuments } from '../mockData'

defineProps({
  course: { type: Object, required: true },
})

const documents = ref(initialDocuments.map((document) => ({ ...document })))
const activeTab = ref('documents')
const statusFilter = ref('all')
const searchQuery = ref('')
const selectedDocumentId = ref(1)
const uploadProgress = ref(0)
const uploadStage = ref('等待上传')
const isUploading = ref(false)
let uploadTimer = null
let completionTimer = null

const filteredDocuments = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()
  return documents.value.filter((document) => {
    const matchesStatus = statusFilter.value === 'all' || document.status === statusFilter.value
    const matchesQuery = !query || `${document.name} ${document.tags.join(' ')}`.toLowerCase().includes(query)
    return matchesStatus && matchesQuery
  })
})

const selectedDocument = computed(() =>
  documents.value.find((document) => document.id === selectedDocumentId.value),
)

watch(filteredDocuments, (matches) => {
  if (!matches.some((document) => document.id === selectedDocumentId.value)) {
    selectedDocumentId.value = matches[0]?.id ?? null
  }
})

const readyCount = computed(() => documents.value.filter((document) => document.status === 'ready').length)
const totalChunks = computed(() => documents.value.reduce((total, document) => total + document.chunks, 0))

const statusMeta = {
  ready: { label: '已入库', icon: Check },
  processing: { label: '处理中', icon: Clock },
  failed: { label: '失败', icon: CircleClose },
}

function retryDocument(document) {
  document.status = 'processing'
  document.updatedAt = '刚刚'
  ElMessage.success(`已重新提交「${document.name}」`)
}

function simulateUpload() {
  if (isUploading.value) return
  isUploading.value = true
  uploadProgress.value = 8
  uploadStage.value = '校验文件'
  const stages = [
    [24, '解析章节与页码'],
    [48, '生成结构化分块'],
    [72, '计算语义向量'],
    [92, '写入课程索引'],
    [100, '入库完成'],
  ]
  let index = 0
  uploadTimer = window.setInterval(() => {
    const [progress, stage] = stages[index]
    uploadProgress.value = progress
    uploadStage.value = stage
    index += 1
    if (index === stages.length) {
      window.clearInterval(uploadTimer)
      uploadTimer = null
      completionTimer = window.setTimeout(() => {
        documents.value.unshift({
          id: Date.now(),
          name: 'Spark 性能调优补充资料.pdf',
          type: 'PDF',
          size: '2.4 MB',
          pages: 42,
          chunks: 68,
          status: 'ready',
          updatedAt: '刚刚',
          tags: ['性能调优'],
          outline: ['内存管理', '数据倾斜', 'Shuffle 优化'],
        })
        selectedDocumentId.value = documents.value[0].id
        isUploading.value = false
        completionTimer = null
        ElMessage.success('模拟资料已完成入库')
      }, 450)
    }
  }, 520)
}

onBeforeUnmount(() => {
  if (uploadTimer !== null) window.clearInterval(uploadTimer)
  if (completionTimer !== null) window.clearTimeout(completionTimer)
})
</script>

<template>
  <section class="product-view knowledge-view">
    <header class="view-header">
      <div>
        <span class="eyebrow">Course Library</span>
        <h1>课程知识库</h1>
        <p>组织 {{ course.name }} 的资料，检查解析结构与入库状态。</p>
      </div>
      <button class="primary-action glass-control" type="button" :disabled="isUploading" @click="simulateUpload">
        <el-icon><UploadFilled /></el-icon>
        <span>{{ isUploading ? '正在入库' : '模拟上传资料' }}</span>
      </button>
    </header>

    <div class="metric-band glass-surface">
      <div><span>课程资料</span><strong>{{ documents.length }}</strong><em>5 种格式</em></div>
      <div><span>已完成</span><strong>{{ readyCount }}</strong><em>可用于问答</em></div>
      <div><span>知识片段</span><strong>{{ totalChunks }}</strong><em>结构化索引</em></div>
      <div><span>索引版本</span><strong>v12</strong><em>BGE-M3 · 混合检索</em></div>
    </div>

    <div v-if="isUploading" class="upload-progress glass-surface" aria-live="polite">
      <div class="upload-file-icon"><el-icon><FolderAdd /></el-icon></div>
      <div>
        <strong>Spark 性能调优补充资料.pdf</strong>
        <span>{{ uploadStage }}</span>
      </div>
      <div class="progress-track"><i :style="{ width: `${uploadProgress}%` }"></i></div>
      <em>{{ uploadProgress }}%</em>
    </div>

    <div class="knowledge-layout">
      <section class="content-panel document-panel">
        <header class="panel-toolbar">
          <div class="segmented-control">
            <button type="button" :class="{ active: activeTab === 'documents' }" @click="activeTab = 'documents'">资料</button>
            <button type="button" :class="{ active: activeTab === 'jobs' }" @click="activeTab = 'jobs'">入库任务</button>
          </div>
          <label class="compact-search">
            <el-icon><Search /></el-icon>
            <input v-model="searchQuery" type="search" placeholder="搜索资料或标签" />
          </label>
        </header>

        <div class="filter-row">
          <button v-for="filter in [{ id: 'all', label: '全部' }, { id: 'ready', label: '已入库' }, { id: 'processing', label: '处理中' }, { id: 'failed', label: '失败' }]" :key="filter.id" type="button" :class="{ active: statusFilter === filter.id }" @click="statusFilter = filter.id">
            {{ filter.label }}
          </button>
        </div>

        <div v-if="activeTab === 'documents'" class="document-list">
          <article
            v-for="document in filteredDocuments"
            :key="document.id"
            :class="['document-row', { active: selectedDocumentId === document.id }]"
            role="button"
            tabindex="0"
            @click="selectedDocumentId = document.id"
            @keydown.enter="selectedDocumentId = document.id"
          >
            <span class="file-type-icon"><el-icon><Document /></el-icon></span>
            <span class="document-name"><strong>{{ document.name }}</strong><em>{{ document.type }} · {{ document.size }} · {{ document.pages }} 页</em></span>
            <span :class="['document-status', `status-${document.status}`]"><el-icon><component :is="statusMeta[document.status].icon" /></el-icon>{{ statusMeta[document.status].label }}</span>
            <span class="chunk-count">{{ document.chunks }} chunks</span>
            <span class="updated-at">{{ document.updatedAt }}</span>
            <span class="row-actions">
              <button v-if="document.status === 'failed'" type="button" title="重试" aria-label="重试" @click.stop="retryDocument(document)"><el-icon><Refresh /></el-icon></button>
              <button type="button" title="更多" aria-label="更多"><el-icon><MoreFilled /></el-icon></button>
            </span>
          </article>
          <div v-if="!filteredDocuments.length" class="inline-empty"><el-icon><Search /></el-icon><strong>没有匹配的资料</strong><span>尝试修改关键词或状态筛选。</span></div>
        </div>

        <div v-else class="job-list">
          <article><span class="job-state finished"><el-icon><Check /></el-icon></span><div><strong>Spark 编程指南.pdf</strong><em>解析 126 页 · 生成 184 个片段 · 索引 v12</em></div><time>4.2 秒</time></article>
          <article><span class="job-state running"><el-icon><Clock /></el-icon></span><div><strong>Spark SQL 课堂笔记.md</strong><em>正在计算语义向量 · 24 / 34</em></div><time>72%</time></article>
          <article><span class="job-state failed"><el-icon><CircleClose /></el-icon></span><div><strong>旧版课程提纲.pdf</strong><em>PDF 页面对象损坏，未生成索引</em></div><button type="button" @click="activeTab = 'documents'; statusFilter = 'failed'">处理</button></article>
        </div>
      </section>

      <aside class="document-inspector glass-surface">
        <template v-if="selectedDocument">
          <header>
            <span class="file-type-large">{{ selectedDocument.type }}</span>
            <div><strong>{{ selectedDocument.name }}</strong><em>{{ selectedDocument.size }} · {{ selectedDocument.pages }} 页</em></div>
          </header>
          <div class="inspector-status"><span :class="`status-${selectedDocument.status}`"><i></i>{{ statusMeta[selectedDocument.status].label }}</span><em>{{ selectedDocument.updatedAt }}</em></div>
          <section>
            <span class="section-label">文档结构</span>
            <ol v-if="selectedDocument.outline.length" class="outline-list">
              <li v-for="(item, index) in selectedDocument.outline" :key="item"><span>{{ String(index + 1).padStart(2, '0') }}</span>{{ item }}</li>
            </ol>
            <div v-else class="inspector-empty">解析失败，暂无可用结构。</div>
          </section>
          <section>
            <span class="section-label">标签</span>
            <div class="tag-list"><span v-for="tag in selectedDocument.tags" :key="tag">{{ tag }}</span><button type="button"><span>+</span></button></div>
          </section>
          <dl>
            <div><dt>解析器</dt><dd>Structured Parser v2</dd></div>
            <div><dt>Embedding</dt><dd>BGE-M3 · local</dd></div>
            <div><dt>索引</dt><dd>{{ selectedDocument.status === 'ready' ? 'course-1-v12' : '尚未生效' }}</dd></div>
          </dl>
          <button class="secondary-action glass-control" type="button" :disabled="selectedDocument.status !== 'ready'">预览并检查分块</button>
        </template>
        <div v-else class="inline-empty"><el-icon><Search /></el-icon><strong>暂无文档详情</strong><span>调整筛选条件后选择一份资料。</span></div>
      </aside>
    </div>
  </section>
</template>
