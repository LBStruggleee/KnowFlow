<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Bell,
  FolderOpened,
  Lock,
  Menu,
  MoreFilled,
  Notebook,
  Plus,
  Reading,
  Search,
  Setting,
} from '@element-plus/icons-vue'
import {
  createKnowledgeBase,
  getProviderStatus,
  getSystemSettings,
  listDocuments,
  listKnowledgeBases,
} from '../api/client'
import { getApiErrorMessage, getCourseMeta } from './productState'
import AssistantView from './views/AssistantView.vue'
import KnowledgeView from './views/KnowledgeView.vue'
import RecordsView from './views/RecordsView.vue'
import SettingsView from './views/SettingsView.vue'

const navItems = [
  { id: 'assistant', label: '课程助手', icon: Reading },
  { id: 'knowledge', label: '课程知识库', icon: FolderOpened },
  { id: 'records', label: '学习记录', icon: Notebook },
  { id: 'settings', label: '设置', icon: Setting },
]
const validViews = new Set(navItems.map((item) => item.id))
const initialView = window.location.hash.slice(1)

const activeView = ref(validViews.has(initialView) ? initialView : 'assistant')
const knowledgeBases = ref([])
const documents = ref([])
const selectedKbId = ref(null)
const providerStatus = ref(null)
const settings = ref(null)
const resumeConversationId = ref(null)
const mobileNavOpen = ref(false)
const loading = ref(true)

const glassVariant = computed({
  get: () => settings.value?.glass_variant || 'balanced',
  set: (value) => {
    settings.value = { ...(settings.value || {}), glass_variant: value }
  },
})
const selectedCourse = computed(() => {
  const course = knowledgeBases.value.find((item) => item.id === selectedKbId.value)
  if (!course) return null
  return {
    ...course,
    meta: getCourseMeta(documents.value),
    tone: ['green', 'blue', 'amber'][course.id % 3],
  }
})
const activeNavItem = computed(() => navItems.find((item) => item.id === activeView.value))
const privacyLabel = computed(() => {
  const labels = { local: '完全本地', hybrid: '本地优先', cloud: '云端增强' }
  return labels[settings.value?.privacy_mode] || '本地优先'
})

async function loadDocuments() {
  if (!selectedKbId.value) {
    documents.value = []
    return
  }
  try {
    documents.value = (await listDocuments(selectedKbId.value)).data
  } catch (error) {
    documents.value = []
    ElMessage.error(getApiErrorMessage(error, '无法读取课程资料。'))
  }
}

async function selectCourse(id) {
  selectedKbId.value = id
  resumeConversationId.value = null
  await loadDocuments()
  mobileNavOpen.value = false
}

async function loadApplication() {
  loading.value = true
  try {
    const [kbResponse, settingsResponse, providerResponse] = await Promise.all([
      listKnowledgeBases(),
      getSystemSettings(),
      getProviderStatus(),
    ])
    knowledgeBases.value = kbResponse.data
    settings.value = settingsResponse.data
    providerStatus.value = providerResponse.data
    const preferredId = selectedKbId.value
    selectedKbId.value =
      knowledgeBases.value.find((item) => item.id === preferredId)?.id ||
      knowledgeBases.value[0]?.id ||
      null
    await loadDocuments()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, 'KnowFlow 初始化失败。'))
  } finally {
    loading.value = false
  }
}

async function createCourse() {
  try {
    const { value } = await ElMessageBox.prompt('为课程知识库命名，例如“大数据原理”。', '新建课程', {
      confirmButtonText: '创建',
      cancelButtonText: '取消',
      inputPlaceholder: '课程名称',
      inputPattern: /\S+/,
      inputErrorMessage: '请输入课程名称',
    })
    const { data } = await createKnowledgeBase({ name: value.trim(), description: '', category: '课程' })
    await loadApplication()
    await selectCourse(data.id)
    activeView.value = 'knowledge'
    syncHash()
    ElMessage.success('课程已创建，现在可以导入资料。')
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(getApiErrorMessage(error, '创建课程失败。'))
  }
}

function selectView(view) {
  activeView.value = view
  mobileNavOpen.value = false
  syncHash()
}

function openAssistant(conversationId = null) {
  resumeConversationId.value = conversationId
  selectView('assistant')
}

function syncHash() {
  window.history.replaceState(null, '', `#${activeView.value}`)
}

function syncViewFromHash() {
  const view = window.location.hash.slice(1)
  if (validViews.has(view)) activeView.value = view
}

function handleSettingsSaved(value) {
  settings.value = value
  providerStatus.value = { ...(providerStatus.value || {}), privacy_mode: value.privacy_mode }
}

onMounted(() => {
  window.addEventListener('hashchange', syncViewFromHash)
  loadApplication()
})
onBeforeUnmount(() => window.removeEventListener('hashchange', syncViewFromHash))
</script>

<template>
  <main :class="['demo-canvas', `glass-${glassVariant}`]">
    <div class="ambient-grid" aria-hidden="true">
      <span class="ambient-block block-green"></span>
      <span class="ambient-block block-blue"></span>
      <span class="ambient-block block-amber"></span>
    </div>

    <header class="mobile-header glass-surface">
      <button class="icon-button glass-control" type="button" aria-label="打开导航" @click="mobileNavOpen = !mobileNavOpen">
        <el-icon><Menu /></el-icon>
      </button>
      <div class="mobile-brand"><span>K</span><strong>KnowFlow</strong></div>
      <button class="icon-button glass-control" type="button" aria-label="新建课程" @click="createCourse"><el-icon><Plus /></el-icon></button>
    </header>

    <button v-if="mobileNavOpen" class="mobile-scrim" type="button" aria-label="关闭导航" @click="mobileNavOpen = false"></button>

    <aside :class="['sidebar', 'glass-surface', { 'is-open': mobileNavOpen }]">
      <div class="brand-lockup"><div class="brand-symbol">K</div><div><strong>KnowFlow</strong><span>课程知识工作台</span></div></div>

      <nav class="primary-nav" aria-label="主导航">
        <button v-for="item in navItems" :key="item.id" type="button" :class="['nav-item', { active: activeView === item.id }]" @click="selectView(item.id)">
          <el-icon><component :is="item.icon" /></el-icon><span>{{ item.label }}</span>
        </button>
      </nav>

      <section class="course-switcher">
        <div class="section-label-row"><span class="section-label">我的课程</span><button class="tiny-action" type="button" aria-label="新建课程" title="新建课程" @click="createCourse"><el-icon><Plus /></el-icon></button></div>
        <button v-for="course in knowledgeBases" :key="course.id" type="button" :class="['course-item', { active: selectedKbId === course.id }]" @click="selectCourse(course.id)">
          <span :class="['course-mark', `tone-${['green', 'blue', 'amber'][course.id % 3]}`]"></span>
          <span><strong>{{ course.name }}</strong><em>{{ selectedKbId === course.id ? getCourseMeta(documents) : course.category || '课程知识库' }}</em></span>
        </button>
        <button v-if="!knowledgeBases.length && !loading" class="empty-course-action" type="button" @click="createCourse"><el-icon><Plus /></el-icon><span>创建第一门课程</span></button>
      </section>

      <footer class="sidebar-footer">
        <div class="privacy-status"><span class="privacy-icon"><el-icon><Lock /></el-icon></span><span><strong>{{ privacyLabel }}</strong><em>{{ providerStatus?.llm_available ? '回答模型已就绪' : '当前使用本地提取式回答' }}</em></span></div>
        <button class="avatar-button" type="button" aria-label="本地用户">BL</button>
      </footer>
    </aside>

    <section class="workspace">
      <header class="workspace-toolbar glass-surface">
        <div class="breadcrumb"><span>{{ selectedCourse?.name || 'KnowFlow' }}</span><span class="slash">/</span><strong>{{ activeNavItem?.label }}</strong></div>
        <div class="toolbar-actions">
          <button class="search-trigger glass-control" type="button" @click="selectView('knowledge')"><el-icon><Search /></el-icon><span>搜索资料</span></button>
          <button class="icon-button glass-control" type="button" aria-label="新建课程" title="新建课程" @click="createCourse"><el-icon><Plus /></el-icon></button>
          <button class="icon-button glass-control" type="button" aria-label="设置" title="设置" @click="selectView('settings')"><el-icon><MoreFilled /></el-icon></button>
        </div>
      </header>

      <div v-if="loading" class="app-loading"><span></span><strong>正在载入本地学习空间</strong></div>
      <section v-else-if="!selectedCourse" class="app-empty">
        <span class="brand-symbol">K</span><h1>建立你的第一门课程</h1><p>先创建课程，再导入 PDF、PPTX、DOCX、Markdown 或文本资料。</p>
        <button class="primary-action glass-control" type="button" @click="createCourse"><el-icon><Plus /></el-icon>新建课程</button>
      </section>
      <template v-else>
        <AssistantView v-if="activeView === 'assistant'" :course="selectedCourse" :document-count="documents.length" :resume-conversation-id="resumeConversationId" @conversation-resumed="resumeConversationId = null" />
        <KnowledgeView v-else-if="activeView === 'knowledge'" :course="selectedCourse" @documents-updated="documents = $event" />
        <RecordsView v-else-if="activeView === 'records'" :course="selectedCourse" @open-assistant="openAssistant" />
        <SettingsView v-else :initial-settings="settings" :provider-status="providerStatus" :glass-variant="glassVariant" @saved="handleSettingsSaved" @update:glass-variant="glassVariant = $event" @data-cleared="loadApplication" />
      </template>
    </section>
  </main>
</template>
