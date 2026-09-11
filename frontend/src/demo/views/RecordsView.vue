<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  ChatDotRound,
  Check,
  CollectionTag,
  EditPen,
  Notebook,
  RefreshRight,
  Search,
  Tickets,
  Warning,
} from '@element-plus/icons-vue'
import { learningRecords } from '../mockData'

const emit = defineEmits(['open-assistant'])

const activeType = ref('all')
const query = ref('')
const selectedRecordId = ref(1)

const typeMeta = {
  conversation: { label: '对话', icon: ChatDotRound },
  note: { label: '笔记', icon: Notebook },
  exercise: { label: '练习', icon: Tickets },
  mistake: { label: '错题', icon: Warning },
}

const filteredRecords = computed(() => {
  const normalized = query.value.trim().toLowerCase()
  return learningRecords.filter((record) => {
    const matchesType = activeType.value === 'all' || record.type === activeType.value
    const matchesQuery = !normalized || `${record.title} ${record.summary} ${record.tags.join(' ')}`.toLowerCase().includes(normalized)
    return matchesType && matchesQuery
  })
})

const selectedRecord = computed(() =>
  learningRecords.find((record) => record.id === selectedRecordId.value),
)

watch(filteredRecords, (matches) => {
  if (!matches.some((record) => record.id === selectedRecordId.value)) {
    selectedRecordId.value = matches[0]?.id ?? null
  }
})

function continueRecord() {
  ElMessage.success('已恢复该学习上下文')
  emit('open-assistant')
}
</script>

<template>
  <section class="product-view records-view">
    <header class="view-header">
      <div>
        <span class="eyebrow">Learning Memory</span>
        <h1>学习记录</h1>
        <p>把对话、笔记、练习和错题留在同一条课程脉络中。</p>
      </div>
      <button class="primary-action glass-control" type="button" @click="emit('open-assistant')">
        <el-icon><EditPen /></el-icon><span>开始新学习</span>
      </button>
    </header>

    <div class="record-overview glass-surface">
      <div class="review-ring"><strong>78%</strong><span>本周完成</span></div>
      <div class="review-copy"><span class="eyebrow">本周学习节奏</span><strong>你已经连续学习 4 天</strong><p>还有 2 道 Spark 错题建议在今天复习。</p></div>
      <div class="review-stats"><span><strong>11</strong><em>次对话</em></span><span><strong>6</strong><em>篇笔记</em></span><span><strong>83%</strong><em>练习正确率</em></span></div>
      <button class="secondary-action glass-control" type="button" @click="activeType = 'mistake'">查看待复习</button>
    </div>

    <div class="records-layout">
      <section class="content-panel records-panel">
        <header class="panel-toolbar">
          <div class="segmented-control records-tabs">
            <button v-for="tab in [{ id: 'all', label: '全部' }, { id: 'conversation', label: '对话' }, { id: 'note', label: '笔记' }, { id: 'exercise', label: '练习' }, { id: 'mistake', label: '错题' }]" :key="tab.id" type="button" :class="{ active: activeType === tab.id }" @click="activeType = tab.id">{{ tab.label }}</button>
          </div>
          <label class="compact-search"><el-icon><Search /></el-icon><input v-model="query" type="search" placeholder="搜索学习记录" /></label>
        </header>

        <div class="record-list">
          <button v-for="record in filteredRecords" :key="record.id" type="button" :class="['record-row', { active: selectedRecordId === record.id }]" @click="selectedRecordId = record.id">
            <span :class="['record-icon', `record-${record.type}`]"><el-icon><component :is="typeMeta[record.type].icon" /></el-icon></span>
            <span class="record-main"><strong>{{ record.title }}</strong><p>{{ record.summary }}</p><em>{{ record.course }} · {{ record.meta }}</em></span>
            <span class="record-time">{{ record.time }}</span>
          </button>
          <div v-if="!filteredRecords.length" class="inline-empty"><el-icon><Search /></el-icon><strong>没有匹配的学习记录</strong><span>修改分类或搜索关键词后再试。</span></div>
        </div>
      </section>

      <aside class="record-preview glass-surface" v-if="selectedRecord">
        <header><span :class="['record-icon', `record-${selectedRecord.type}`]"><el-icon><component :is="typeMeta[selectedRecord.type].icon" /></el-icon></span><div><span class="eyebrow">{{ typeMeta[selectedRecord.type].label }}</span><em>{{ selectedRecord.time }}</em></div></header>
        <h2>{{ selectedRecord.title }}</h2>
        <p>{{ selectedRecord.summary }}</p>
        <div class="preview-tags"><span v-for="tag in selectedRecord.tags" :key="tag">{{ tag }}</span></div>
        <div class="preview-evidence">
          <span class="section-label">关联内容</span>
          <div><el-icon><CollectionTag /></el-icon><span><strong>{{ selectedRecord.course }}</strong><em>课程知识库</em></span></div>
          <div><el-icon><Check /></el-icon><span><strong>来源已验证</strong><em>{{ selectedRecord.meta }}</em></span></div>
        </div>
        <blockquote>“Lineage 决定能否恢复，缓存决定是否需要频繁重算。”</blockquote>
        <div class="preview-actions">
          <button class="primary-action glass-control" type="button" @click="continueRecord"><el-icon><RefreshRight /></el-icon>继续学习</button>
          <button class="icon-button glass-control" type="button" aria-label="编辑记录" title="编辑记录"><el-icon><EditPen /></el-icon></button>
        </div>
      </aside>
    </div>
  </section>
</template>
