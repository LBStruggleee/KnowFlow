<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import MarkdownIt from 'markdown-it'
import {
  ArrowRight,
  ChatDotRound,
  Coin,
  Collection,
  Delete,
  DocumentAdd,
  Setting,
  Refresh,
  Search,
  UploadFilled,
} from '@element-plus/icons-vue'
import {
  askQuestion,
  createKnowledgeBase,
  deleteDocument,
  deleteConversation,
  getConversation,
  getSystemSettings,
  getSystemStatus,
  deleteKnowledgeBase,
  listDocumentChunks,
  listConversations,
  listDocuments,
  listKnowledgeBases,
  updateSystemSettings,
  updateKnowledgeBase,
  uploadDocument,
} from './api/client'

const markdown = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
})

const activeView = ref('chat')
const knowledgeBases = ref([])
const documents = ref([])
const chunks = ref([])
const selectedKbId = ref(null)
const selectedDocumentId = ref(null)
const loadingKbs = ref(false)
const loadingDocuments = ref(false)
const uploading = ref(false)
const asking = ref(false)
const commandQuery = ref('')
const commandInputRef = ref(null)
const kbPanelTab = ref('documents')
const chatCollapse = ref(['trace', 'sources'])
const historyExpanded = ref(false)
const conversations = ref([])
const activeConversationId = ref(null)
const systemStatus = ref(null)
const systemSettings = ref({
  top_k: 5,
  score_threshold: 0,
  qwen_model: 'qwen-plus',
  temperature: 0.2,
})
const settingsSaving = ref(false)

const kbForm = ref({
  name: '',
  category: '',
  description: '',
})

const renameForm = ref({
  name: '',
})

const categoryForm = ref({
  category: '',
})

const question = ref('')
const answer = ref('')
const sources = ref([])
const usage = ref(null)
const retrievalTrace = ref(null)

const selectedKb = computed(() =>
  knowledgeBases.value.find((item) => item.id === selectedKbId.value),
)

const renderedAnswer = computed(() => markdown.render(answer.value || ''))

const normalizedQuery = computed(() => commandQuery.value.trim().toLowerCase())

const filteredKnowledgeBases = computed(() => {
  if (!normalizedQuery.value) return knowledgeBases.value
  return knowledgeBases.value.filter((kb) =>
    [kb.name, kb.category, kb.description]
      .join(' ')
      .toLowerCase()
      .includes(normalizedQuery.value),
  )
})

const filteredDocuments = computed(() => {
  if (!normalizedQuery.value) return documents.value
  return documents.value.filter((doc) =>
    [doc.title, doc.file_name, doc.file_type, doc.status]
      .join(' ')
      .toLowerCase()
      .includes(normalizedQuery.value),
  )
})

const currentDocument = computed(() =>
  documents.value.find((item) => item.id === selectedDocumentId.value),
)

const activeConversation = computed(() =>
  conversations.value.find((item) => item.id === activeConversationId.value),
)

const totalChunks = computed(() =>
  documents.value.reduce((total, item) => total + (item.chunk_count || 0), chunks.value.length),
)

const finishedDocuments = computed(() =>
  documents.value.filter((item) => item.status === 'finished').length,
)

const recentDocuments = computed(() => filteredDocuments.value.slice(0, 4))

function syncMaintenanceForms() {
  renameForm.value.name = selectedKb.value?.name || ''
  categoryForm.value.category = selectedKb.value?.category || ''
}

async function loadKnowledgeBases() {
  loadingKbs.value = true
  try {
    const { data } = await listKnowledgeBases()
    knowledgeBases.value = data
    if (!selectedKbId.value && data.length > 0) {
      selectedKbId.value = data[0].id
      syncMaintenanceForms()
      await loadDocuments()
      await loadConversations()
    } else {
      syncMaintenanceForms()
    }
    await loadSystemStatus()
  } catch (error) {
    showError(error, '知识库加载失败')
  } finally {
    loadingKbs.value = false
  }
}

async function handleCreateKb() {
  if (!kbForm.value.name.trim()) {
    ElMessage.warning('请输入知识库名称')
    return
  }

  try {
    const { data } = await createKnowledgeBase({
      name: kbForm.value.name.trim(),
      category: kbForm.value.category.trim(),
      description: kbForm.value.description.trim(),
    })
    ElMessage.success('知识库创建成功')
    kbForm.value = { name: '', category: '', description: '' }
    await loadKnowledgeBases()
    selectedKbId.value = data.id
    await loadDocuments()
  } catch (error) {
    showError(error, '知识库创建失败')
  }
}

async function handleDeleteKb() {
  if (!selectedKb.value) {
    ElMessage.warning('请先选择知识库')
    return
  }

  try {
    await ElMessageBox.confirm(
      `确定删除知识库「${selectedKb.value.name}」吗？该操作会删除其文档、分块和向量数据。`,
      '删除知识库',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
    await deleteKnowledgeBase(selectedKb.value.id)
    ElMessage.success('知识库已删除')
    selectedKbId.value = null
    selectedDocumentId.value = null
    documents.value = []
    chunks.value = []
    answer.value = ''
    sources.value = []
    usage.value = null
    await loadKnowledgeBases()
  } catch (error) {
    if (error !== 'cancel') {
      showError(error, '删除知识库失败')
    }
  }
}

async function handleRenameKb() {
  if (!selectedKb.value) {
    ElMessage.warning('请先选择知识库')
    return
  }
  const name = renameForm.value.name.trim()
  if (!name) {
    ElMessage.warning('请输入新的知识库名称')
    return
  }

  try {
    const { data } = await updateKnowledgeBase(selectedKb.value.id, { name })
    ElMessage.success('知识库已重命名')
    await loadKnowledgeBases()
    selectedKbId.value = data.id
    syncMaintenanceForms()
  } catch (error) {
    showError(error, '重命名失败')
  }
}

async function handleUpdateKbCategory() {
  if (!selectedKb.value) {
    ElMessage.warning('请先选择知识库')
    return
  }

  try {
    const { data } = await updateKnowledgeBase(selectedKb.value.id, {
      category: categoryForm.value.category.trim(),
    })
    ElMessage.success('分类已更新')
    await loadKnowledgeBases()
    selectedKbId.value = data.id
    syncMaintenanceForms()
  } catch (error) {
    showError(error, '修改分类失败')
  }
}

async function handleKbChange() {
  selectedDocumentId.value = null
  activeConversationId.value = null
  chunks.value = []
  answer.value = ''
  sources.value = []
  usage.value = null
  retrievalTrace.value = null
  syncMaintenanceForms()
  await loadDocuments()
  await loadConversations()
}

async function loadDocuments() {
  if (!selectedKbId.value) {
    documents.value = []
    return
  }

  loadingDocuments.value = true
  try {
    const { data } = await listDocuments(selectedKbId.value)
    documents.value = data
  } catch (error) {
    showError(error, '文档加载失败')
  } finally {
    loadingDocuments.value = false
  }
}

async function loadConversations() {
  if (!selectedKbId.value) {
    conversations.value = []
    return
  }
  try {
    const { data } = await listConversations(selectedKbId.value)
    conversations.value = data
  } catch (error) {
    showError(error, '历史会话加载失败')
  }
}

async function loadConversation(conversationId) {
  try {
    const { data } = await getConversation(conversationId)
    activeConversationId.value = data.id
    const assistantMessages = data.messages.filter((message) => message.role === 'assistant')
    const lastAssistant = assistantMessages[assistantMessages.length - 1]
    if (lastAssistant) {
      answer.value = lastAssistant.content
      sources.value = lastAssistant.sources || []
      usage.value = {
        prompt_tokens: lastAssistant.prompt_tokens,
        completion_tokens: lastAssistant.completion_tokens,
        total_tokens: lastAssistant.total_tokens,
      }
      retrievalTrace.value = null
    }
  } catch (error) {
    showError(error, '会话详情加载失败')
  }
}

async function handleDeleteConversation(conversation) {
  try {
    await deleteConversation(conversation.id)
    ElMessage.success('历史会话已删除')
    if (activeConversationId.value === conversation.id) {
      activeConversationId.value = null
      answer.value = ''
      sources.value = []
      usage.value = null
      retrievalTrace.value = null
    }
    await loadConversations()
    await loadSystemStatus()
  } catch (error) {
    showError(error, '删除历史会话失败')
  }
}

async function loadSystemStatus() {
  try {
    const { data } = await getSystemStatus()
    systemStatus.value = data
  } catch (error) {
    showError(error, '系统状态加载失败')
  }
}

async function loadSystemSettings() {
  try {
    const { data } = await getSystemSettings()
    systemSettings.value = data
  } catch (error) {
    showError(error, '系统设置加载失败')
  }
}

async function handleSaveSettings() {
  settingsSaving.value = true
  try {
    const { data } = await updateSystemSettings(systemSettings.value)
    systemSettings.value = data
    ElMessage.success('系统设置已保存')
  } catch (error) {
    showError(error, '系统设置保存失败')
  } finally {
    settingsSaving.value = false
  }
}

async function handleUpload(uploadRequest) {
  if (!selectedKbId.value) {
    ElMessage.warning('请先选择知识库')
    return
  }

  uploading.value = true
  try {
    const { data } = await uploadDocument(selectedKbId.value, uploadRequest.file)
    ElMessage.success('文档上传并入库成功')
    selectedDocumentId.value = data.id
    await loadDocuments()
    await loadChunks(data.id)
  } catch (error) {
    showError(error, '文档上传失败')
  } finally {
    uploading.value = false
  }
}

async function handleDeleteDocument(document) {
  try {
    await ElMessageBox.confirm(
      `确定删除文件「${document.title}」吗？该操作会同步删除分块和向量数据。`,
      '删除文件',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
    await deleteDocument(document.id)
    ElMessage.success('文件已删除')
    if (selectedDocumentId.value === document.id) {
      selectedDocumentId.value = null
      chunks.value = []
    }
    await loadDocuments()
  } catch (error) {
    if (error !== 'cancel') {
      showError(error, '删除文件失败')
    }
  }
}

async function loadChunks(documentId = selectedDocumentId.value) {
  if (!documentId) {
    chunks.value = []
    return
  }

  selectedDocumentId.value = documentId
  try {
    const { data } = await listDocumentChunks(documentId)
    chunks.value = data
  } catch (error) {
    showError(error, '分块加载失败')
  }
}

async function handleAsk() {
  if (!selectedKbId.value) {
    ElMessage.warning('请先选择知识库')
    return
  }
  if (!documents.value.length) {
    ElMessage.warning('当前知识库还没有文档，请先上传资料或切换知识库')
    return
  }
  if (!question.value.trim()) {
    ElMessage.warning('请输入问题')
    return
  }

  asking.value = true
  answer.value = ''
  sources.value = []
  usage.value = null
  retrievalTrace.value = null
  try {
    const { data } = await askQuestion({
      kb_id: selectedKbId.value,
      question: question.value.trim(),
      top_k: systemSettings.value.top_k,
      conversation_id: activeConversationId.value,
    })
    answer.value = data.answer
    sources.value = data.sources || []
    usage.value = data.usage
    retrievalTrace.value = data.retrieval_trace
    activeConversationId.value = data.conversation_id
    await loadConversations()
    await loadSystemStatus()
  } catch (error) {
    showError(error, '问答请求失败')
  } finally {
    asking.value = false
  }
}

function startNewConversation() {
  activeConversationId.value = null
  question.value = ''
  answer.value = ''
  sources.value = []
  usage.value = null
  retrievalTrace.value = null
}

function handleViewSelect(view) {
  activeView.value = view
  if (view === 'chat') {
    loadConversations()
  }
}

function focusCommandSearch() {
  nextTick(() => {
    commandInputRef.value?.focus?.()
  })
}

function handleGlobalKeydown(event) {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    focusCommandSearch()
  }
}

function showError(error, fallback) {
  const detail = error?.response?.data?.detail
  ElMessage.error(detail || fallback)
}

onMounted(() => {
  loadKnowledgeBases()
  loadSystemSettings()
  loadSystemStatus()
  window.addEventListener('keydown', handleGlobalKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleGlobalKeydown)
})
</script>

<template>
  <el-container class="app-shell">
    <el-aside width="320px" class="sidebar">
      <div class="brand">
        <div class="brand-mark">KF</div>
        <div>
          <h1>KnowFlow</h1>
          <p>知汇 · RAG Console</p>
        </div>
      </div>

      <el-menu
        :default-active="activeView"
        :active-text-color="'#E0E6ED'"
        class="nav"
        @select="handleViewSelect"
      >
        <el-menu-item index="chat">
          <el-icon><ChatDotRound /></el-icon>
          <span>RAG 问答</span>
        </el-menu-item>
        <el-menu-item index="kb">
          <el-icon><Collection /></el-icon>
          <span>知识库管理</span>
        </el-menu-item>
      </el-menu>

      <div class="sidebar-panel">
        <span class="panel-label">当前知识库</span>
        <strong>{{ selectedKb?.name || '未选择' }}</strong>
        <p>{{ selectedKb?.category || '未分类' }}</p>
      </div>

      <section class="sidebar-metrics" aria-label="Knowledge base overview">
        <div class="sidebar-metric">
          <span>知识库</span>
          <strong>{{ knowledgeBases.length }}</strong>
          <em>workspaces</em>
        </div>
        <div class="sidebar-metric">
          <span>当前文档</span>
          <strong>{{ documents.length }}</strong>
          <em>{{ finishedDocuments }} finished</em>
        </div>
        <div class="sidebar-metric">
          <span>当前分块</span>
          <strong>{{ totalChunks }}</strong>
          <em>chunks</em>
        </div>
      </section>

      <section v-if="activeView === 'chat'" class="sidebar-history">
        <button class="sidebar-history-head" type="button" @click="historyExpanded = !historyExpanded">
          <span class="panel-label">History</span>
          <strong>历史会话</strong>
          <em>{{ conversations.length }} sessions</em>
        </button>
        <div v-if="historyExpanded" class="sidebar-history-body">
          <div v-if="conversations.length" class="sidebar-conversation-list">
            <button
              v-for="conversation in conversations"
              :key="conversation.id"
              :class="{ active: activeConversationId === conversation.id }"
              type="button"
              @click="loadConversation(conversation.id)"
            >
              <span>
                <strong>{{ conversation.title }}</strong>
                <em>#{{ conversation.id }}</em>
              </span>
              <el-button
                class="danger-text"
                link
                :icon="Delete"
                @click.stop="handleDeleteConversation(conversation)"
              />
            </button>
          </div>
          <el-empty v-else description="暂无历史会话" />
        </div>
      </section>
    </el-aside>

    <el-container>
      <el-header class="topbar">
        <div class="command-search">
          <el-icon><Search /></el-icon>
          <input
            ref="commandInputRef"
            v-model="commandQuery"
            type="search"
            placeholder="搜索知识库、文档或问题"
          />
          <kbd>⌘K</kbd>
        </div>

        <nav class="topbar-nav" aria-label="Primary">
          <button type="button" :class="{ active: activeView === 'chat' }" @click="handleViewSelect('chat')">
            RAG 问答
          </button>
          <button type="button" :class="{ active: activeView === 'kb' }" @click="handleViewSelect('kb')">
            知识库管理
          </button>
          <button type="button" @click="kbPanelTab = 'settings'; handleViewSelect('kb')">Settings</button>
          <button type="button" @click="focusCommandSearch">Search</button>
        </nav>

        <div class="topbar-actions">
          <el-button
            class="ghost-button icon-button"
            :icon="Refresh"
            aria-label="刷新"
            title="刷新"
            @click="loadKnowledgeBases"
          />
          <el-button class="upgrade-button" @click="loadSystemStatus">System</el-button>
        </div>
      </el-header>

      <el-main class="workspace">
        <section class="workspace-header">
          <div class="workspace-title">
            <span class="home-chip">
              <el-icon>
                <ChatDotRound v-if="activeView === 'chat'" />
                <Collection v-else />
              </el-icon>
            </span>
            <div>
              <h2>{{ activeView === 'chat' ? 'RAG 问答首页' : '知识库管理' }}</h2>
              <p>
                {{
                  activeView === 'chat'
                    ? '基于选定知识库检索来源，并调用千问生成回答'
                    : '组织资料、上传文档、检查分块与入库状态'
                }}
              </p>
            </div>
          </div>

          <div class="workspace-actions">
            <el-upload
              v-if="activeView === 'kb'"
              :http-request="handleUpload"
              :show-file-list="false"
              :disabled="uploading || !selectedKbId"
            >
              <el-button class="black-button" :icon="UploadFilled" :loading="uploading">
                Add Document
              </el-button>
            </el-upload>
            <el-button v-else class="black-button" @click="startNewConversation">New Chat</el-button>
          </div>
        </section>

        <section v-if="activeView === 'kb'" class="dashboard-view">
          <div class="dashboard-main">
            <section class="dashboard-hero">
              <div class="kb-copy">
                <span class="eyebrow">Knowledge Base</span>
                <h3>{{ selectedKb?.name || '选择一个知识库' }}</h3>
                <p>{{ selectedKb?.description || '选择知识库后上传资料，系统会自动解析、分块并写入向量库。' }}</p>
              </div>

              <div class="hero-actions">
                <el-select
                  v-model="selectedKbId"
                  filterable
                  class="kb-selector"
                  placeholder="选择知识库"
                  :loading="loadingKbs"
                  @change="handleKbChange"
                >
                  <el-option
                    v-for="kb in filteredKnowledgeBases"
                    :key="kb.id"
                    :label="`${kb.name} · ${kb.category || '未分类'}`"
                    :value="kb.id"
                  />
                </el-select>
                <el-upload
                  :http-request="handleUpload"
                  :show-file-list="false"
                  :disabled="uploading || !selectedKbId"
                  class="compact-upload"
                >
                  <el-button type="primary" :icon="UploadFilled" :loading="uploading">
                    上传文档
                  </el-button>
                </el-upload>
              </div>
            </section>

            <div class="panel management-panel">
              <header class="panel-heading">
                <div>
                  <span class="eyebrow">Library Console</span>
                  <h3>资料与分块</h3>
                  <p>查看文档、检查分块，并维护当前知识库的元信息。</p>
                </div>
              </header>

            <div class="management-tabs" role="tablist" aria-label="知识库管理功能">
              <button
                :class="{ active: kbPanelTab === 'documents' }"
                type="button"
                @click="kbPanelTab = 'documents'"
              >
                文档
                <span>{{ filteredDocuments.length }}</span>
              </button>
              <button
                :class="{ active: kbPanelTab === 'chunks' }"
                type="button"
                @click="kbPanelTab = 'chunks'"
              >
                分块
                <span>{{ chunks.length }}</span>
              </button>
              <button
                :class="{ active: kbPanelTab === 'maintenance' }"
                type="button"
                @click="kbPanelTab = 'maintenance'"
              >
                维护
              </button>
              <button
                :class="{ active: kbPanelTab === 'create' }"
                type="button"
                @click="kbPanelTab = 'create'"
              >
                创建
              </button>
            </div>

            <div class="management-body">
              <section v-if="kbPanelTab === 'documents'" class="management-section">
                <div class="section-heading">
                  <div>
                    <h4>文档列表</h4>
                    <p>点击任意文档可以查看解析后的分块；删除会同步清理向量数据。</p>
                  </div>
                  <el-tag size="small" effect="plain">{{ filteredDocuments.length }} docs</el-tag>
                </div>
                <el-table
                  class="document-table dark-table"
                  :data="filteredDocuments"
                  height="330"
                  v-loading="loadingDocuments"
                  empty-text="暂无文档"
                  @row-click="(row) => loadChunks(row.id)"
                >
                  <el-table-column prop="title" label="文档" min-width="220" />
                  <el-table-column prop="file_type" label="类型" width="90" />
                  <el-table-column prop="content_length" label="长度" width="110" />
                  <el-table-column prop="status" label="状态" width="120">
                    <template #default="{ row }">
                      <el-tag :type="row.status === 'finished' ? 'success' : 'warning'" effect="dark">
                        {{ row.status }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column label="操作" width="90" fixed="right">
                    <template #default="{ row }">
                      <el-button
                        class="danger-text"
                        link
                        :icon="Delete"
                        @click.stop="handleDeleteDocument(row)"
                      >
                        删除
                      </el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </section>

              <section v-else-if="kbPanelTab === 'chunks'" class="management-section">
                <div class="section-heading">
                  <div>
                    <h4>{{ currentDocument?.title || '分块预览' }}</h4>
                    <p>用于检查解析质量、分块长度和后续检索命中的上下文。</p>
                  </div>
                  <el-tag size="small" effect="plain">{{ chunks.length }} chunks</el-tag>
                </div>
                <el-empty v-if="!chunks.length" description="先在文档列表中选择一个文档" />
                <el-scrollbar v-else height="340px">
                  <article v-for="chunk in chunks" :key="chunk.id" class="chunk">
                    <header>
                      <span>#{{ chunk.chunk_index }}</span>
                      <el-tag size="small" effect="plain">{{ chunk.token_count }} tokens</el-tag>
                    </header>
                    <pre><code>{{ chunk.content }}</code></pre>
                  </article>
                </el-scrollbar>
              </section>

              <section v-else-if="kbPanelTab === 'maintenance'" class="management-section">
                <div class="section-heading">
                  <div>
                    <h4>知识库维护</h4>
                    <p>修改当前知识库的名称、分类，或执行危险删除操作。</p>
                  </div>
                  <el-tag size="small" effect="plain">{{ selectedKb?.name || '未选择' }}</el-tag>
                </div>

                <div class="maintenance-grid">
                  <article class="maintenance-card">
                    <span class="eyebrow">Rename</span>
                    <strong>重命名</strong>
                    <div class="maintenance-row stacked">
                      <el-input
                        v-model="renameForm.name"
                        :disabled="!selectedKbId"
                        placeholder="新的知识库名称"
                      />
                      <el-button type="primary" :disabled="!selectedKbId" @click="handleRenameKb">
                        保存名称
                      </el-button>
                    </div>
                  </article>

                  <article class="maintenance-card">
                    <span class="eyebrow">Category</span>
                    <strong>修改分类</strong>
                    <div class="maintenance-row stacked">
                      <el-input
                        v-model="categoryForm.category"
                        :disabled="!selectedKbId"
                        placeholder="例如：Spark / RAG / FastAPI"
                      />
                      <el-button
                        type="primary"
                        :disabled="!selectedKbId"
                        @click="handleUpdateKbCategory"
                      >
                        保存分类
                      </el-button>
                    </div>
                  </article>

                  <article class="maintenance-card danger-card">
                    <span class="eyebrow">Danger</span>
                    <strong>删除知识库</strong>
                    <p>会同步删除文档、分块、本地文件和 Chroma 向量数据。</p>
                    <el-button
                      class="danger-button"
                      :icon="Delete"
                      :disabled="!selectedKbId"
                      @click="handleDeleteKb"
                    >
                      删除知识库
                    </el-button>
                  </article>
                </div>
              </section>

              <section v-else class="management-section">
                <div class="section-heading">
                  <div>
                    <h4>创建新知识库</h4>
                    <p>为新的资料主题建立独立空间，后续上传内容会写入对应向量集合。</p>
                  </div>
                </div>
                <el-form label-position="top" class="compact-form">
                  <div class="form-grid">
                    <el-form-item label="名称">
                      <el-input v-model="kbForm.name" placeholder="例如：Spark 知识库" />
                    </el-form-item>
                    <el-form-item label="分类">
                      <el-input v-model="kbForm.category" placeholder="例如：Spark" />
                    </el-form-item>
                  </div>
                  <el-form-item label="描述">
                    <el-input
                      v-model="kbForm.description"
                      type="textarea"
                      :rows="3"
                      placeholder="说明这个知识库收录的资料范围"
                    />
                  </el-form-item>
                  <el-button type="primary" :icon="DocumentAdd" @click="handleCreateKb">
                    创建知识库
                  </el-button>
                </el-form>
              </section>
            </div>
            </div>
          </div>

          <aside class="dashboard-side">
            <section class="side-card selected-card">
              <span class="eyebrow">Current</span>
              <h4>{{ selectedKb?.name || '未选择知识库' }}</h4>
              <p>{{ selectedKb?.category || '未分类' }}</p>
              <div class="side-divider"></div>
              <div class="side-stat">
                <span>文档完成率</span>
                <strong>{{ documents.length ? Math.round((finishedDocuments / documents.length) * 100) : 0 }}%</strong>
              </div>
              <div class="progress-track">
                <span :style="{ width: `${documents.length ? Math.round((finishedDocuments / documents.length) * 100) : 0}%` }"></span>
              </div>
            </section>

            <section class="side-card status-card">
              <div class="side-header">
                <span class="eyebrow">System</span>
                <el-button
                  class="ghost-button mini-icon"
                  :icon="Refresh"
                  aria-label="刷新系统状态"
                  title="刷新系统状态"
                  @click="loadSystemStatus"
                />
              </div>
              <div class="status-grid">
                <div>
                  <span>会话</span>
                  <strong>{{ systemStatus?.conversations ?? 0 }}</strong>
                </div>
                <div>
                  <span>消息</span>
                  <strong>{{ systemStatus?.messages ?? 0 }}</strong>
                </div>
                <div>
                  <span>Token</span>
                  <strong>{{ systemStatus?.token_usage?.total_tokens ?? 0 }}</strong>
                </div>
                <div>
                  <span>失败文档</span>
                  <strong>{{ systemStatus?.failed_documents ?? 0 }}</strong>
                </div>
              </div>
            </section>

            <section class="side-card settings-card">
              <span class="eyebrow">Settings</span>
              <h4>检索与模型参数</h4>
              <div class="settings-grid">
                <label>
                  <span>Top K</span>
                  <el-input-number v-model="systemSettings.top_k" :min="1" :max="20" size="small" />
                </label>
                <label>
                  <span>阈值</span>
                  <el-input-number
                    v-model="systemSettings.score_threshold"
                    :min="0"
                    :max="1"
                    :step="0.05"
                    size="small"
                  />
                </label>
                <label class="wide-setting">
                  <span>模型</span>
                  <el-input v-model="systemSettings.qwen_model" size="small" />
                </label>
                <label>
                  <span>温度</span>
                  <el-input-number
                    v-model="systemSettings.temperature"
                    :min="0"
                    :max="2"
                    :step="0.1"
                    size="small"
                  />
                </label>
              </div>
              <el-button
                class="settings-save"
                type="primary"
                :icon="Setting"
                :loading="settingsSaving"
                @click="handleSaveSettings"
              >
                保存设置
              </el-button>
            </section>

            <section class="side-card ingest-card">
              <span class="eyebrow">Ingest</span>
              <h4>上传资料并自动入库</h4>
              <p>支持 txt、md、pdf、docx、pptx，上传后自动完成解析、分块、向量化和 Chroma 写入。</p>
              <el-upload
                :http-request="handleUpload"
                :show-file-list="false"
                :disabled="uploading || !selectedKbId"
                class="compact-upload"
              >
                <el-button type="primary" :icon="UploadFilled" :loading="uploading">
                  上传文档
                </el-button>
              </el-upload>
            </section>

            <section class="side-card">
              <div class="side-header">
                <span class="eyebrow">Recent</span>
                <el-tag size="small" effect="plain">{{ recentDocuments.length }}</el-tag>
              </div>
              <div v-if="recentDocuments.length" class="recent-list">
                <button
                  v-for="doc in recentDocuments"
                  :key="doc.id"
                  type="button"
                  @click="loadChunks(doc.id); kbPanelTab = 'chunks'"
                >
                  <strong>{{ doc.title }}</strong>
                  <span>{{ doc.file_type }} · {{ doc.chunk_count || 0 }} chunks</span>
                </button>
              </div>
              <el-empty v-else description="暂无文档" />
            </section>
          </aside>
        </section>

        <section v-else class="clean-view">
          <div class="panel focus-panel chat-focus">
            <header class="focus-header">
              <div>
                <span class="eyebrow">Ask KnowFlow</span>
                <h3>向知识库提问</h3>
                <p>回答会严格基于选定知识库的检索片段生成，引用源可在下方展开查看。</p>
              </div>
              <div class="active-database-card">
                <span>当前数据库</span>
                <strong>{{ selectedKb?.name || '未选择知识库' }}</strong>
                <em>{{ documents.length }} docs · {{ totalChunks }} chunks</em>
              </div>
            </header>

            <div class="question-composer">
              <div class="ai-prompt-shell">
                <el-input
                  v-model="question"
                  class="prompt-textarea"
                  type="textarea"
                  :rows="4"
                  placeholder="What can I ask from this knowledge base?"
                  @keydown.enter.exact.prevent="handleAsk"
                />
                <div class="prompt-toolbar">
                  <div class="prompt-tools">
                    <el-select
                      v-model="selectedKbId"
                      filterable
                      class="database-model-select"
                      placeholder="选择知识库数据库"
                      @change="handleKbChange"
                    >
                      <template #prefix>
                        <el-icon><Coin /></el-icon>
                      </template>
                      <template #label="{ label }">
                        <span class="database-selected-label">{{ label }}</span>
                      </template>
                      <el-option
                        v-for="kb in knowledgeBases"
                        :key="kb.id"
                        :label="kb.name"
                        :value="kb.id"
                      >
                        <div class="database-option">
                          <span class="database-option-icon">
                            <el-icon><Coin /></el-icon>
                          </span>
                          <span>
                            <strong>{{ kb.name }}</strong>
                            <em>{{ kb.category || '未分类' }}</em>
                          </span>
                        </div>
                      </el-option>
                    </el-select>

                    <span class="prompt-divider"></span>

                    <el-upload
                      :http-request="handleUpload"
                      :show-file-list="false"
                      :disabled="uploading || !selectedKbId"
                    >
                      <el-button
                        class="prompt-icon-button"
                        :icon="UploadFilled"
                        :loading="uploading"
                        aria-label="上传文档"
                        title="上传文档"
                      />
                    </el-upload>
                  </div>

                  <div class="prompt-submit-group">
                    <span>Top K {{ systemSettings.top_k }} · 阈值 {{ systemSettings.score_threshold }}</span>
                    <el-button
                      class="prompt-send-button"
                      :loading="asking"
                      :icon="ArrowRight"
                      :disabled="!question.trim()"
                      aria-label="发送问题"
                      title="发送问题"
                      @click="handleAsk"
                    />
                  </div>
                </div>
              </div>
            </div>

            <section v-if="answer" class="answer">
              <header>
                <span class="ai-dot"></span>
                <h3>AI 回答</h3>
                <el-tag v-if="usage" effect="plain">Token {{ usage.total_tokens ?? '-' }}</el-tag>
              </header>
              <div class="answer-body markdown-body" v-html="renderedAnswer"></div>
            </section>

            <el-collapse v-model="chatCollapse" class="dark-collapse compact-collapse">
              <el-collapse-item name="trace">
                <template #title>
                  <span class="collapse-title">检索过程</span>
                  <el-tag size="small" effect="plain">
                    best {{ retrievalTrace?.best_score?.toFixed?.(3) ?? '-' }}
                  </el-tag>
                </template>
                <el-empty v-if="!retrievalTrace" description="提问后显示检索过程" />
                <div v-else class="trace-panel">
                  <div class="trace-summary">
                    <span>Top K: {{ retrievalTrace.top_k }}</span>
                    <span>阈值: {{ retrievalTrace.score_threshold }}</span>
                    <span>最高分: {{ retrievalTrace.best_score.toFixed(3) }}</span>
                    <el-tag
                      size="small"
                      :type="retrievalTrace.passed_threshold ? 'success' : 'warning'"
                      effect="dark"
                    >
                      {{ retrievalTrace.passed_threshold ? '通过阈值' : '触发拒答' }}
                    </el-tag>
                  </div>
                  <article
                    v-for="match in retrievalTrace.matches"
                    :key="match.chunk_id"
                    class="source"
                  >
                    <div class="source-tags">
                      <el-tag size="small" effect="dark">score {{ match.score.toFixed(3) }}</el-tag>
                      <el-tag size="small" effect="plain">chunk {{ match.chunk_index }}</el-tag>
                      <el-tag size="small" effect="plain">doc {{ match.document_id }}</el-tag>
                    </div>
                    <pre><code>{{ match.content }}</code></pre>
                  </article>
                </div>
              </el-collapse-item>

              <el-collapse-item name="sources">
                <template #title>
                  <span class="collapse-title">引用源</span>
                  <el-tag size="small" effect="plain">{{ sources.length }}</el-tag>
                </template>
                <el-empty v-if="!sources.length" description="提问后显示引用来源" />
                <el-scrollbar v-else height="360px">
                  <article v-for="source in sources" :key="source.chunk_id" class="source">
                    <div class="source-tags">
                      <el-tag size="small" effect="dark">chunk {{ source.chunk_index }}</el-tag>
                      <el-tag size="small" effect="plain">score {{ source.score.toFixed(3) }}</el-tag>
                      <el-tag size="small" effect="plain">doc {{ source.document_id }}</el-tag>
                    </div>
                    <pre><code>{{ source.content }}</code></pre>
                  </article>
                </el-scrollbar>
              </el-collapse-item>

              <el-collapse-item name="docs">
                <template #title>
                  <span class="collapse-title">当前知识库文档</span>
                  <el-tag size="small" effect="plain">{{ filteredDocuments.length }}</el-tag>
                </template>
                <el-table
                  class="document-table dark-table"
                  :data="filteredDocuments"
                  height="260"
                  v-loading="loadingDocuments"
                  empty-text="暂无文档"
                  @row-click="(row) => loadChunks(row.id)"
                >
                  <el-table-column prop="title" label="文档" min-width="220" />
                  <el-table-column prop="file_type" label="类型" width="90" />
                  <el-table-column prop="status" label="状态" width="110" />
                  <el-table-column label="操作" width="90">
                    <template #default="{ row }">
                      <el-button
                        class="danger-text"
                        link
                        :icon="Delete"
                        @click.stop="handleDeleteDocument(row)"
                      >
                        删除
                      </el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </el-collapse-item>
            </el-collapse>
          </div>
        </section>
      </el-main>
    </el-container>
  </el-container>
</template>
