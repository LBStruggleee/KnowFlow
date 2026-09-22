<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ChatDotRound,
  Check,
  CollectionTag,
  Delete,
  EditPen,
  Notebook,
  RefreshRight,
  Search,
  Tickets,
  Warning,
} from '@element-plus/icons-vue'
import {
  deleteConversation,
  deleteLearningRecord,
  listConversations,
  listLearningRecords,
} from '../../api/client'
import { combineLearningRecords, getApiErrorMessage } from '../productState'

const props = defineProps({ course: { type: Object, required: true } })
const emit = defineEmits(['open-assistant'])

const activeType = ref('all')
const query = ref('')
const records = ref([])
const selectedRecordKey = ref(null)
const loading = ref(true)

const typeMeta = {
  conversation: { label: '对话', icon: ChatDotRound },
  note: { label: '笔记', icon: Notebook },
  exercise: { label: '练习', icon: Tickets },
  mistake: { label: '错题', icon: Warning },
}
const filteredRecords = computed(() => {
  const normalized = query.value.trim().toLowerCase()
  return records.value.filter((record) => {
    const matchesType = activeType.value === 'all' || record.type === activeType.value
    const searchable = `${record.title} ${record.summary} ${record.tags.join(' ')}`.toLowerCase()
    return matchesType && (!normalized || searchable.includes(normalized))
  })
})
const selectedRecord = computed(() =>
  records.value.find((record) => record.key === selectedRecordKey.value),
)
const counts = computed(() => ({
  conversation: records.value.filter((item) => item.type === 'conversation').length,
  note: records.value.filter((item) => item.type === 'note').length,
  exercise: records.value.filter((item) => item.type === 'exercise').length,
  mistake: records.value.filter((item) => item.type === 'mistake').length,
}))

async function loadRecords() {
  loading.value = true
  try {
    const [conversationResponse, recordResponse] = await Promise.all([
      listConversations(props.course.id),
      listLearningRecords(props.course.id),
    ])
    records.value = combineLearningRecords(conversationResponse.data, recordResponse.data, props.course.name)
    if (!records.value.some((item) => item.key === selectedRecordKey.value)) {
      selectedRecordKey.value = records.value[0]?.key ?? null
    }
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '无法读取学习记录。'))
  } finally {
    loading.value = false
  }
}

function continueRecord(record = selectedRecord.value) {
  if (!record) return
  const conversationId = record.type === 'conversation' ? record.id : record.conversationId
  if (conversationId) emit('open-assistant', conversationId)
  else emit('open-assistant')
}

async function removeRecord(record) {
  try {
    await ElMessageBox.confirm(`删除“${record.title}”？`, '删除学习记录', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
    if (record.type === 'conversation') await deleteConversation(record.id)
    else await deleteLearningRecord(record.id)
    await loadRecords()
    ElMessage.success('学习记录已删除')
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(getApiErrorMessage(error, '删除学习记录失败。'))
  }
}

watch(() => props.course.id, loadRecords, { immediate: true })
watch(filteredRecords, (matches) => {
  if (!matches.some((item) => item.key === selectedRecordKey.value)) selectedRecordKey.value = matches[0]?.key ?? null
})
</script>

<template>
  <section class="product-view records-view">
    <header class="view-header">
      <div><span class="eyebrow">Learning Memory</span><h1>学习记录</h1><p>把 {{ course.name }} 的对话、笔记、练习和错题留在同一条课程脉络中。</p></div>
      <button class="primary-action glass-control" type="button" @click="emit('open-assistant')"><el-icon><EditPen /></el-icon><span>开始新学习</span></button>
    </header>

    <div class="record-overview glass-surface">
      <div class="review-ring"><strong>{{ records.length }}</strong><span>学习产物</span></div>
      <div class="review-copy"><span class="eyebrow">本地学习记忆</span><strong>{{ records.length ? '学习上下文已持续积累' : '从一次课程问答开始' }}</strong><p>{{ records.length ? '对话与主动保存的产物均可回到原学习上下文。' : '回答后可保存为笔记、练习或错题。' }}</p></div>
      <div class="review-stats"><span><strong>{{ counts.conversation }}</strong><em>次对话</em></span><span><strong>{{ counts.note }}</strong><em>篇笔记</em></span><span><strong>{{ counts.exercise + counts.mistake }}</strong><em>项练习</em></span></div>
      <button class="secondary-action glass-control" type="button" :disabled="!counts.mistake" @click="activeType = 'mistake'">查看待复习</button>
    </div>

    <div class="records-layout">
      <section class="content-panel records-panel">
        <header class="panel-toolbar"><div class="segmented-control records-tabs"><button v-for="tab in [{ id: 'all', label: '全部' }, { id: 'conversation', label: '对话' }, { id: 'note', label: '笔记' }, { id: 'exercise', label: '练习' }, { id: 'mistake', label: '错题' }]" :key="tab.id" type="button" :class="{ active: activeType === tab.id }" @click="activeType = tab.id">{{ tab.label }}</button></div><label class="compact-search"><el-icon><Search /></el-icon><input v-model="query" type="search" placeholder="搜索学习记录" /></label></header>
        <div class="record-list">
          <button v-for="record in filteredRecords" :key="record.key" type="button" :class="['record-row', { active: selectedRecordKey === record.key }]" @click="selectedRecordKey = record.key"><span :class="['record-icon', `record-${record.type}`]"><el-icon><component :is="typeMeta[record.type].icon" /></el-icon></span><span class="record-main"><strong>{{ record.title }}</strong><p>{{ record.summary }}</p><em>{{ record.course }} · {{ record.meta }}</em></span><span class="record-time">{{ record.time }}</span></button>
          <div v-if="loading" class="inline-empty"><el-icon><RefreshRight /></el-icon><strong>正在读取学习记录</strong></div>
          <div v-else-if="!filteredRecords.length" class="inline-empty"><el-icon><Search /></el-icon><strong>{{ records.length ? '没有匹配的学习记录' : '还没有学习记录' }}</strong><span>{{ records.length ? '修改分类或搜索关键词后再试。' : '开始课程问答，并把有价值的回答保存下来。' }}</span></div>
        </div>
      </section>

      <aside v-if="selectedRecord" class="record-preview glass-surface">
        <header><span :class="['record-icon', `record-${selectedRecord.type}`]"><el-icon><component :is="typeMeta[selectedRecord.type].icon" /></el-icon></span><div><span class="eyebrow">{{ typeMeta[selectedRecord.type].label }}</span><em>{{ selectedRecord.time }}</em></div></header>
        <h2>{{ selectedRecord.title }}</h2><p>{{ selectedRecord.summary }}</p>
        <div class="preview-tags"><span v-for="tag in selectedRecord.tags" :key="tag">{{ tag }}</span></div>
        <div class="preview-evidence"><span class="section-label">关联内容</span><div><el-icon><CollectionTag /></el-icon><span><strong>{{ selectedRecord.course }}</strong><em>课程知识库</em></span></div><div><el-icon><Check /></el-icon><span><strong>保存在本地</strong><em>{{ selectedRecord.meta }}</em></span></div></div>
        <blockquote v-if="selectedRecord.content">{{ selectedRecord.content }}</blockquote>
        <div class="preview-actions"><button class="primary-action glass-control" type="button" @click="continueRecord()"><el-icon><RefreshRight /></el-icon>继续学习</button><button class="danger-icon-button" type="button" aria-label="删除记录" title="删除记录" @click="removeRecord(selectedRecord)"><el-icon><Delete /></el-icon></button></div>
      </aside>
    </div>
  </section>
</template>
