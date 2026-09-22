<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import MarkdownIt from 'markdown-it'
import { ElMessage } from 'element-plus'
import {
  ArrowUp,
  Collection,
  Document,
  EditPen,
  Expand,
  Files,
  Fold,
  MagicStick,
  Notebook,
  Tickets,
} from '@element-plus/icons-vue'
import {
  askQuestion,
  createLearningRecord,
  getConversation,
  getDocumentFileUrl,
  listConversations,
} from '../../api/client'
import { getEvidencePanelState } from '../evidencePanelState'
import { getApiErrorMessage, TASK_MODES } from '../productState'

const props = defineProps({
  course: { type: Object, required: true },
  documentCount: { type: Number, default: 0 },
  resumeConversationId: { type: Number, default: null },
})
const emit = defineEmits(['conversation-resumed'])

const markdown = new MarkdownIt({ html: false, linkify: true, breaks: true })
const activeMode = ref('question')
const question = ref('')
const messages = ref([])
const conversations = ref([])
const conversationId = ref(null)
const sources = ref([])
const retrievalTrace = ref(null)
const sourcePanelOpen = ref(true)
const selectedSourceId = ref(null)
const sending = ref(false)
const conversationScroll = ref(null)

const evidencePanelState = computed(() =>
  getEvidencePanelState(sourcePanelOpen.value, sources.value.length),
)
const bestScore = computed(() => {
  const value = retrievalTrace.value?.best_score
  return Number.isFinite(value) ? Math.round(value * 100) + '%' : '-'
})
const lastAssistantMessage = computed(() =>
  [...messages.value].reverse().find((message) => message.role === 'assistant'),
)
const composerPlaceholder = computed(() => '继续询问 ' + props.course.name + '…')

function renderMarkdown(content) {
  return markdown.render(content || '')
}

function assistantMeta(message) {
  if (message.error) return '生成失败'
  const mode = message.answer_mode === 'cloud' ? '云端增强' : '本地回答'
  return mode + ' · ' + (message.sources?.length || 0) + ' 个来源'
}

async function loadConversation(id) {
  if (!id) return
  try {
    const { data } = await getConversation(id)
    if (data.kb_id !== props.course.id) return
    conversationId.value = data.id
    messages.value = data.messages
    const assistant = [...data.messages].reverse().find((message) => message.role === 'assistant')
    sources.value = assistant?.sources || []
    selectedSourceId.value = sources.value[0]?.chunk_id ?? null
    retrievalTrace.value = null
    emit('conversation-resumed')
    await scrollToBottom()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '无法恢复这段会话。'))
  }
}

async function loadConversationList() {
  try {
    conversations.value = (await listConversations(props.course.id)).data
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '无法读取历史会话。'))
  }
}

function newChat() {
  conversationId.value = null
  messages.value = []
  sources.value = []
  retrievalTrace.value = null
  question.value = ''
}

async function submitQuestion() {
  const content = question.value.trim()
  if (!content || sending.value) return
  messages.value.push({ id: 'local-' + Date.now(), role: 'user', content })
  question.value = ''
  sending.value = true
  await scrollToBottom()
  try {
    const { data } = await askQuestion({
      kb_id: props.course.id,
      question: content,
      conversation_id: conversationId.value,
      mode: activeMode.value,
    })
    conversationId.value = data.conversation_id
    messages.value.push({
      id: data.assistant_message_id,
      role: 'assistant',
      content: data.answer,
      sources: data.sources,
      answer_mode: data.answer_mode,
      provider: data.provider,
      insufficient_evidence: data.insufficient_evidence,
    })
    sources.value = data.sources || []
    selectedSourceId.value = sources.value[0]?.chunk_id ?? null
    retrievalTrace.value = data.retrieval_trace
    await loadConversationList()
  } catch (error) {
    messages.value.push({
      id: 'error-' + Date.now(),
      role: 'assistant',
      content: getApiErrorMessage(error, '回答生成失败，请稍后重试。'),
      error: true,
    })
  } finally {
    sending.value = false
    await scrollToBottom()
  }
}

async function saveLearningRecord(type) {
  const message = lastAssistantMessage.value
  if (!message || message.error) return
  try {
    await createLearningRecord({
      kb_id: props.course.id,
      conversation_id: conversationId.value,
      source_message_id: Number.isInteger(message.id) ? message.id : null,
      record_type: type,
      title:
        type === 'exercise'
          ? '资料练习'
          : messages.value.find((item) => item.role === 'user')?.content?.slice(0, 80) ||
            '学习笔记',
      content: message.content,
      tags: [TASK_MODES.find((mode) => mode.id === activeMode.value)?.label || '学习'],
      metadata: { answer_mode: message.answer_mode || 'unknown' },
    })
    ElMessage.success(type === 'exercise' ? '练习已保存' : '回答已保存为笔记')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '保存学习记录失败。'))
  }
}

function prepareExercise() {
  activeMode.value = 'exercise'
  question.value = '根据当前课程资料生成 3 道练习题，并提供参考答案。'
}

function openSelectedSource() {
  const source = sources.value.find((item) => item.chunk_id === selectedSourceId.value)
  if (source) window.open(getDocumentFileUrl(source.document_id), '_blank', 'noopener,noreferrer')
}

async function scrollToBottom() {
  await nextTick()
  if (conversationScroll.value) {
    conversationScroll.value.scrollTop = conversationScroll.value.scrollHeight
  }
}

watch(
  () => props.course.id,
  async () => {
    newChat()
    await loadConversationList()
  },
  { immediate: true },
)

watch(
  () => props.resumeConversationId,
  (id) => loadConversation(id),
  { immediate: true },
)
</script>

<template>
  <div :class="['assistant-layout', { 'evidence-collapsed': !sourcePanelOpen }]">
    <section class="conversation-pane">
      <header class="conversation-header">
        <div>
          <span class="eyebrow">当前课程</span>
          <h1>{{ course.name }}</h1>
          <p>基于 {{ documentCount }} 份课程资料回答，关键结论将标注原文引用。</p>
        </div>
        <button class="new-chat-button glass-control" type="button" @click="newChat">
          <el-icon><EditPen /></el-icon><span>新对话</span>
        </button>
      </header>

      <div class="mode-strip" role="tablist" aria-label="学习任务类型">
        <button v-for="mode in TASK_MODES" :key="mode.id" type="button" :class="{ active: activeMode === mode.id }" @click="activeMode = mode.id">
          {{ mode.label }}
        </button>
      </div>

      <div ref="conversationScroll" class="conversation-scroll">
        <div v-if="!messages.length" class="assistant-empty">
          <span class="assistant-mark"><el-icon><MagicStick /></el-icon></span>
          <strong>从课程资料开始学习</strong>
          <p>提问一个概念，或选择上方任务模式生成总结、对比和练习。</p>
        </div>

        <article v-for="message in messages" :key="message.id" :class="['message', message.role === 'user' ? 'user-message' : 'assistant-message', { 'message-error': message.error }]">
          <template v-if="message.role === 'user'">
            <span class="message-author">你</span><p>{{ message.content }}</p>
          </template>
          <template v-else>
            <header class="assistant-author">
              <span class="assistant-mark"><el-icon><MagicStick /></el-icon></span>
              <span><strong>KnowFlow</strong><em>{{ assistantMeta(message) }}</em></span>
            </header>
            <div class="answer-content markdown-answer" v-html="renderMarkdown(message.content)"></div>
            <footer v-if="!message.error && message === lastAssistantMessage" class="answer-actions">
              <button type="button" @click="saveLearningRecord('note')"><el-icon><Notebook /></el-icon>存为笔记</button>
              <button type="button" @click="saveLearningRecord('exercise')"><el-icon><Tickets /></el-icon>保存练习</button>
              <button type="button" @click="sourcePanelOpen = true"><el-icon><Document /></el-icon>查看检索依据</button>
            </footer>
          </template>
        </article>

        <article v-if="sending" class="message assistant-message answer-loading" aria-live="polite">
          <header class="assistant-author"><span class="assistant-mark"><el-icon><MagicStick /></el-icon></span><span><strong>KnowFlow</strong><em>正在检索课程资料</em></span></header>
          <span></span><span></span><span></span>
        </article>
      </div>

      <section class="composer glass-surface">
        <textarea v-model="question" rows="2" :placeholder="composerPlaceholder" :disabled="sending" @keydown.ctrl.enter.prevent="submitQuestion"></textarea>
        <div class="composer-footer">
          <div class="composer-context"><button type="button"><el-icon><Collection /></el-icon>全部资料</button><span>{{ sources.length || '尚未' }} 个命中片段</span></div>
          <button class="send-button" type="button" :disabled="!question.trim() || sending" aria-label="发送问题" @click="submitQuestion"><el-icon><ArrowUp /></el-icon></button>
        </div>
      </section>

      <div class="suggestion-row">
        <span>继续探索</span>
        <button type="button" @click="question = '窄依赖和宽依赖如何影响故障恢复？'">比较窄依赖与宽依赖</button>
        <button type="button" @click="prepareExercise">生成 3 道练习题</button>
      </div>
    </section>

    <aside :class="['evidence-panel', 'glass-surface', evidencePanelState.stateClass]" :aria-label="evidencePanelState.toggleLabel">
      <header v-if="sourcePanelOpen" class="evidence-header">
        <div><span class="eyebrow">Evidence</span><h2>回答依据</h2></div>
        <button class="icon-button glass-control" type="button" :aria-label="evidencePanelState.toggleLabel" :title="evidencePanelState.toggleLabel" :aria-expanded="sourcePanelOpen" @click="sourcePanelOpen = false"><el-icon><Fold /></el-icon></button>
      </header>

      <template v-if="sourcePanelOpen">
        <div class="evidence-summary">
          <span><i class="status-dot"></i>{{ sources.length ? '依据可查' : '等待提问' }}</span>
          <strong>{{ sources.length }} 个来源</strong>
          <em>最高匹配 {{ bestScore }}</em>
        </div>
        <div v-if="sources.length" class="source-list">
          <button v-for="(source, index) in sources" :key="source.chunk_id" type="button" :class="['source-item', { active: selectedSourceId === source.chunk_id }]" @click="selectedSourceId = source.chunk_id">
            <span class="source-index">{{ index + 1 }}</span>
            <span class="source-copy"><strong>{{ source.document_title || source.file_name || '课程资料' }}</strong><em>{{ source.location }}</em></span>
            <span class="source-score">{{ Math.round(source.score * 100) }}%</span>
            <p>{{ source.content }}</p>
          </button>
        </div>
        <div v-else class="inline-empty compact-empty"><el-icon><Files /></el-icon><strong>暂无回答依据</strong><span>发送问题后，这里会展示真实命中片段。</span></div>
        <button class="open-source-button glass-control" type="button" :disabled="!selectedSourceId" @click="openSelectedSource"><el-icon><Document /></el-icon><span>打开原始资料</span></button>
      </template>

      <button v-else class="evidence-capsule-trigger" type="button" :aria-label="evidencePanelState.toggleLabel" :title="evidencePanelState.toggleLabel" :aria-expanded="sourcePanelOpen" @click="sourcePanelOpen = true">
        <span class="evidence-capsule-icon"><el-icon><Files /></el-icon></span>
        <span class="evidence-capsule-desktop"><strong>依据</strong><em>{{ sources.length }}</em></span>
        <span class="evidence-capsule-mobile"><strong>回答依据</strong><em>{{ evidencePanelState.sourceSummary }}</em></span>
        <el-icon class="evidence-capsule-arrow"><Expand /></el-icon>
      </button>
    </aside>
  </div>
</template>

