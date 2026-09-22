<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Delete,
  Document,
  FolderOpened,
  MoreFilled,
  Plus,
  Refresh,
  RefreshRight,
  Search,
  Upload,
  View,
} from '@element-plus/icons-vue'
import {
  deleteDocument,
  getDocumentFileUrl,
  listDocuments,
  rebuildKnowledgeBaseIndex,
  retryDocument,
  uploadDocument,
} from '../../api/client'
import { formatDate, getApiErrorMessage, mapDocument } from '../productState'

const props = defineProps({ course: { type: Object, required: true } })
const emit = defineEmits(['documents-updated'])

const documents = ref([])
const activeTab = ref('documents')
const activeFilter = ref('all')
const query = ref('')
const selectedDocumentId = ref(null)
const uploadProgress = ref(0)
const uploadStage = ref('正在上传')
const isUploading = ref(false)
const isRebuilding = ref(false)
const fileInput = ref(null)
let pollTimer = null

const filters = [
  { id: 'all', label: '全部' },
  { id: 'ready', label: '已入库' },
  { id: 'processing', label: '处理中' },
  { id: 'failed', label: '失败' },
]
const filteredDocuments = computed(() => {
  const normalized = query.value.trim().toLowerCase()
  return documents.value.filter((document) => {
    const matchesStatus = activeFilter.value === 'all' || document.status === activeFilter.value
    const matchesQuery = !normalized || `${document.name} ${document.type}`.toLowerCase().includes(normalized)
    return matchesStatus && matchesQuery
  })
})
const selectedDocument = computed(() =>
  documents.value.find((document) => document.id === selectedDocumentId.value),
)
const processingDocuments = computed(() =>
  documents.value.filter((document) => document.status === 'processing' || document.status === 'pending'),
)
const failedDocuments = computed(() => documents.value.filter((document) => document.status === 'failed'))

function statusLabel(status) {
  return { ready: '已入库', processing: '处理中', pending: '等待处理', failed: '失败' }[status] || status
}

function schedulePoll() {
  if (pollTimer) window.clearTimeout(pollTimer)
  if (!processingDocuments.value.length) return
  pollTimer = window.setTimeout(loadDocuments, 1600)
}

async function loadDocuments() {
  if (!props.course.id) return
  try {
    const { data } = await listDocuments(props.course.id)
    documents.value = data.map(mapDocument)
    if (!documents.value.some((item) => item.id === selectedDocumentId.value)) {
      selectedDocumentId.value = documents.value[0]?.id ?? null
    }
    emit('documents-updated', data)
    schedulePoll()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '无法读取课程资料。'))
  }
}

async function handleFileSelected(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  isUploading.value = true
  uploadProgress.value = 0
  uploadStage.value = '正在上传'
  try {
    await uploadDocument(props.course.id, file, (progressEvent) => {
      if (progressEvent.total) uploadProgress.value = Math.round((progressEvent.loaded / progressEvent.total) * 100)
    })
    uploadProgress.value = 100
    uploadStage.value = '已提交解析'
    await loadDocuments()
    ElMessage.success(`${file.name} 已加入处理队列`)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '资料上传失败。'))
  } finally {
    window.setTimeout(() => {
      isUploading.value = false
    }, 500)
  }
}

async function retryItem(document) {
  try {
    await retryDocument(document.id)
    ElMessage.success('已重新提交解析')
    await loadDocuments()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '重试失败。'))
  }
}

async function removeItem(document) {
  try {
    await ElMessageBox.confirm(`删除“${document.name}”及其全部索引片段？`, '删除资料', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
    await deleteDocument(document.id)
    await loadDocuments()
    ElMessage.success('资料已删除')
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(getApiErrorMessage(error, '删除资料失败。'))
  }
}

async function rebuildIndex() {
  isRebuilding.value = true
  try {
    const { data } = await rebuildKnowledgeBaseIndex(props.course.id)
    ElMessage.success(`索引已重建，共 ${data.indexed_chunks} 个片段`)
    await loadDocuments()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '索引重建失败。'))
  } finally {
    isRebuilding.value = false
  }
}

function openOriginal(document) {
  window.open(getDocumentFileUrl(document.id), '_blank', 'noopener,noreferrer')
}

watch(() => props.course.id, loadDocuments, { immediate: true })
watch(filteredDocuments, (items) => {
  if (!items.some((item) => item.id === selectedDocumentId.value)) selectedDocumentId.value = items[0]?.id ?? null
})
onBeforeUnmount(() => {
  if (pollTimer) window.clearTimeout(pollTimer)
})
</script>

<template>
  <section class="product-view knowledge-view">
    <input ref="fileInput" class="visually-hidden" type="file" accept=".txt,.md,.pdf,.docx,.pptx" @change="handleFileSelected" />
    <header class="view-header">
      <div><span class="eyebrow">Course Library</span><h1>课程知识库</h1><p>管理 {{ course.name }} 的原始资料、解析状态和可检索片段。</p></div>
      <button class="primary-action glass-control" type="button" :aria-label="isUploading ? uploadStage : '导入资料'" :disabled="isUploading" @click="fileInput?.click()"><el-icon><Upload /></el-icon><span>{{ isUploading ? `${uploadStage} ${uploadProgress}%` : '导入资料' }}</span></button>
    </header>

    <div class="library-overview glass-surface">
      <div><span class="eyebrow">当前课程</span><strong>{{ course.name }}</strong><p>{{ course.description || '围绕课程资料建立可追溯的问答与学习记录。' }}</p></div>
      <div class="library-stats"><span><strong>{{ documents.length }}</strong><em>份资料</em></span><span><strong>{{ documents.reduce((sum, item) => sum + item.chunks, 0) }}</strong><em>个片段</em></span><span><strong>{{ failedDocuments.length }}</strong><em>项待处理</em></span></div>
      <button class="secondary-action glass-control" type="button" :disabled="isRebuilding || !documents.length" @click="rebuildIndex"><el-icon><Refresh /></el-icon>{{ isRebuilding ? '重建中' : '重建索引' }}</button>
    </div>

    <div class="knowledge-tabs segmented-control"><button type="button" :class="{ active: activeTab === 'documents' }" @click="activeTab = 'documents'">资料</button><button type="button" :class="{ active: activeTab === 'jobs' }" @click="activeTab = 'jobs'">处理任务 <span v-if="processingDocuments.length">{{ processingDocuments.length }}</span></button></div>

    <div v-if="activeTab === 'documents'" class="library-layout">
      <section class="content-panel documents-panel">
        <header class="panel-toolbar"><div class="segmented-control compact-segments"><button v-for="filter in filters" :key="filter.id" type="button" :class="{ active: activeFilter === filter.id }" @click="activeFilter = filter.id">{{ filter.label }}</button></div><label class="compact-search"><el-icon><Search /></el-icon><input v-model="query" type="search" placeholder="搜索资料" /></label></header>
        <div class="document-table-head"><span>资料</span><span>状态</span><span>片段</span><span>更新</span><span></span></div>
        <button v-for="document in filteredDocuments" :key="document.id" type="button" :class="['document-row', { active: selectedDocumentId === document.id }]" @click="selectedDocumentId = document.id">
          <span class="document-name"><i :class="`file-${document.type.toLowerCase()}`">{{ document.type.slice(0, 1) }}</i><span><strong>{{ document.name }}</strong><em>{{ document.type }} · {{ document.size }}</em></span></span>
          <span :class="['document-status', `status-${document.status}`]"><i></i>{{ statusLabel(document.status) }}</span><span>{{ document.chunks || '-' }}</span><span>{{ document.updatedAt }}</span>
          <span class="row-actions"><button v-if="document.status === 'failed'" type="button" aria-label="重试解析" title="重试解析" @click.stop="retryItem(document)"><el-icon><RefreshRight /></el-icon></button><button type="button" aria-label="更多操作" title="更多操作"><el-icon><MoreFilled /></el-icon></button></span>
        </button>
        <div v-if="!filteredDocuments.length" class="inline-empty"><el-icon><FolderOpened /></el-icon><strong>{{ documents.length ? '没有匹配的资料' : '课程还没有资料' }}</strong><span>{{ documents.length ? '修改筛选条件后再试。' : '导入课程材料后即可检索和问答。' }}</span><button v-if="!documents.length" type="button" @click="fileInput?.click()"><el-icon><Plus /></el-icon>导入第一份资料</button></div>
      </section>

      <aside v-if="selectedDocument" class="document-inspector glass-surface">
        <header><div><span class="eyebrow">Document</span><h2>资料详情</h2></div><button class="icon-button glass-control" type="button" aria-label="打开原始资料" title="打开原始资料" @click="openOriginal(selectedDocument)"><el-icon><View /></el-icon></button></header>
        <span class="inspector-file-icon"><el-icon><Document /></el-icon></span><h3>{{ selectedDocument.name }}</h3><p>{{ selectedDocument.type }} · {{ selectedDocument.size }} · {{ selectedDocument.chunks }} 个片段</p>
        <dl><div><dt>处理状态</dt><dd>{{ statusLabel(selectedDocument.status) }}</dd></div><div><dt>内容长度</dt><dd>{{ selectedDocument.content_length || 0 }} 字符</dd></div><div><dt>最近更新</dt><dd>{{ formatDate(selectedDocument.updated_at) }}</dd></div></dl>
        <div v-if="selectedDocument.outline.length" class="outline-list"><span class="section-label">内容预览</span><p v-for="(line, index) in selectedDocument.outline" :key="index">{{ line }}</p></div>
        <div v-if="selectedDocument.error_message" class="document-error"><strong>处理失败</strong><p>{{ selectedDocument.error_message }}</p></div>
        <div class="inspector-actions"><button v-if="selectedDocument.status === 'failed'" class="secondary-action glass-control" type="button" @click="retryItem(selectedDocument)"><el-icon><RefreshRight /></el-icon>重新解析</button><button class="danger-icon-button" type="button" aria-label="删除资料" title="删除资料" @click="removeItem(selectedDocument)"><el-icon><Delete /></el-icon></button></div>
      </aside>
    </div>

    <section v-else class="content-panel jobs-panel">
      <header class="panel-toolbar"><div><span class="eyebrow">Processing</span><h2>资料处理任务</h2></div><button class="icon-button glass-control" type="button" aria-label="刷新任务" title="刷新任务" @click="loadDocuments"><el-icon><Refresh /></el-icon></button></header>
      <div v-for="document in [...processingDocuments, ...failedDocuments]" :key="document.id" class="job-row"><span :class="['job-state', document.status]"><el-icon><component :is="document.status === 'failed' ? RefreshRight : Upload" /></el-icon></span><span><strong>{{ document.name }}</strong><em>{{ document.error_message || (document.status === 'pending' ? '等待解析任务开始' : '正在提取文本并建立索引') }}</em></span><strong>{{ statusLabel(document.status) }}</strong><button v-if="document.status === 'failed'" type="button" @click="retryItem(document)">重试</button></div>
      <div v-if="!processingDocuments.length && !failedDocuments.length" class="inline-empty"><el-icon><Refresh /></el-icon><strong>没有待处理任务</strong><span>所有资料均已处理完成。</span></div>
    </section>
  </section>
</template>
