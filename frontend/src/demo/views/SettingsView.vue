<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Check,
  Connection,
  DataLine,
  Delete,
  Download,
  Lock,
  MagicStick,
  Refresh,
  Setting,
} from '@element-plus/icons-vue'
import {
  clearAllData,
  exportAllData,
  getProviderStatus,
  updateSystemSettings,
} from '../../api/client'
import { getApiErrorMessage } from '../productState'

const props = defineProps({
  initialSettings: { type: Object, default: null },
  providerStatus: { type: Object, default: null },
  glassVariant: { type: String, default: 'balanced' },
})
const emit = defineEmits(['saved', 'update:glass-variant', 'data-cleared'])

const privacyMode = ref('hybrid')
const topK = ref(8)
const threshold = ref(0.62)
const qwenModel = ref('qwen-plus')
const temperature = ref(0.2)
const currentProviders = ref(props.providerStatus)
const saving = ref(false)
const saved = ref(false)

const privacyDescription = computed(() => ({
  local: '资料、向量和回答全部在本机处理，不产生外部回答模型请求。',
  hybrid: '原始资料保留在本机，仅将命中的少量片段发送给已配置的回答模型。',
  cloud: '允许使用云端回答模型；原始文件仍保存在本地。',
}[privacyMode.value]))
const providers = computed(() => [
  {
    id: 'llm',
    name: currentProviders.value?.llm_provider || qwenModel.value,
    role: '回答模型',
    location: currentProviders.value?.llm_available ? '云端' : '本地回退',
    status: currentProviders.value?.llm_available ? '可用' : '未配置',
    healthy: Boolean(currentProviders.value?.llm_available),
  },
  {
    id: 'embedding',
    name: currentProviders.value?.embedding_provider || '本地向量模型',
    role: '文本向量化',
    location: '本地',
    status: '可用',
    healthy: true,
  },
  {
    id: 'index',
    name: currentProviders.value?.vector_collection || 'knowflow_chunks',
    role: '向量索引',
    location: '本地',
    status: '可用',
    healthy: true,
  },
])

watch(
  () => props.initialSettings,
  (value) => {
    if (!value) return
    privacyMode.value = value.privacy_mode
    topK.value = value.top_k
    threshold.value = value.score_threshold
    qwenModel.value = value.qwen_model
    temperature.value = value.temperature
  },
  { immediate: true },
)
watch(() => props.providerStatus, (value) => { currentProviders.value = value })

async function saveSettings() {
  saving.value = true
  saved.value = false
  try {
    const { data } = await updateSystemSettings({
      privacy_mode: privacyMode.value,
      top_k: topK.value,
      score_threshold: threshold.value,
      qwen_model: qwenModel.value,
      temperature: temperature.value,
      glass_variant: props.glassVariant,
    })
    emit('saved', data)
    saved.value = true
    ElMessage.success('设置已保存')
    await refreshProviders(false)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '设置保存失败。'))
  } finally {
    saving.value = false
  }
}

async function refreshProviders(notify = true) {
  try {
    currentProviders.value = (await getProviderStatus()).data
    if (notify) ElMessage.success('服务状态已刷新')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '服务状态检查失败。'))
  }
}

function updateAppearance(value) {
  saved.value = false
  emit('update:glass-variant', value)
}

function jumpToSetting(id) {
  const section = document.getElementById(id)
  const container = section?.closest('.product-view')
  if (!section || !container) return
  container.scrollTop = Math.max(0, section.offsetTop - 20)
  section.focus({ preventScroll: true })
}

async function exportData() {
  try {
    const { data } = await exportAllData()
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `knowflow-export-${new Date().toISOString().slice(0, 10)}.json`
    link.click()
    URL.revokeObjectURL(url)
    ElMessage.success('数据导出已开始')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '数据导出失败。'))
  }
}

async function clearData() {
  try {
    await ElMessageBox.confirm('将永久删除全部课程、资料、索引、会话和学习记录。此操作不可撤销。', '清理全部本地数据', {
      confirmButtonText: '永久删除', cancelButtonText: '取消', type: 'warning',
    })
    const { data } = await clearAllData()
    emit('data-cleared')
    ElMessage.success(`已删除 ${data.knowledge_bases} 个课程和 ${data.documents} 份资料`)
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(getApiErrorMessage(error, '本地数据清理失败。'))
  }
}
</script>

<template>
  <section class="product-view settings-view">
    <header class="view-header"><div><span class="eyebrow">Preferences</span><h1>设置</h1><p>控制资料如何处理、模型如何回答，以及界面的玻璃表现。</p></div><div class="save-group"><span v-if="saved"><el-icon><Check /></el-icon>已保存</span><button class="primary-action glass-control" type="button" :disabled="saving" @click="saveSettings"><el-icon><Setting /></el-icon>{{ saving ? '保存中' : '保存设置' }}</button></div></header>

    <div class="settings-layout">
      <nav class="settings-nav glass-surface" aria-label="设置分类"><button type="button" @click="jumpToSetting('privacy')"><el-icon><Lock /></el-icon><span>隐私与处理</span></button><button type="button" @click="jumpToSetting('models')"><el-icon><Connection /></el-icon><span>模型服务</span></button><button type="button" @click="jumpToSetting('retrieval')"><el-icon><DataLine /></el-icon><span>检索策略</span></button><button type="button" @click="jumpToSetting('appearance')"><el-icon><MagicStick /></el-icon><span>界面外观</span></button><button type="button" @click="jumpToSetting('data')"><el-icon><Download /></el-icon><span>数据管理</span></button></nav>

      <div class="settings-content">
        <section id="privacy" class="settings-section content-panel" tabindex="-1"><header><div><span class="eyebrow">Privacy</span><h2>资料处理模式</h2><p>明确选择课程资料离开本机的边界。</p></div><span class="health-badge"><i></i>保护已启用</span></header><div class="privacy-options"><button v-for="mode in [{ id: 'local', title: '完全本地', meta: '不调用外部回答模型' }, { id: 'hybrid', title: '本地优先', meta: '仅发送命中片段' }, { id: 'cloud', title: '云端增强', meta: '使用云端回答能力' }]" :key="mode.id" type="button" :class="{ active: privacyMode === mode.id }" @click="privacyMode = mode.id; saved = false"><span class="radio-dot"></span><strong>{{ mode.title }}</strong><em>{{ mode.meta }}</em></button></div><div class="setting-note"><el-icon><Lock /></el-icon><p><strong>当前模式说明</strong>{{ privacyDescription }}</p></div></section>

        <section id="models" class="settings-section content-panel" tabindex="-1"><header><div><span class="eyebrow">Providers</span><h2>模型服务</h2><p>显示回答、向量化和索引实际使用的服务。</p></div><button class="icon-button glass-control" type="button" aria-label="检查连接" title="检查连接" @click="refreshProviders()"><el-icon><Refresh /></el-icon></button></header><div class="provider-list"><div v-for="provider in providers" :key="provider.id"><span class="provider-mark">{{ provider.name.slice(0, 1).toUpperCase() }}</span><span><strong>{{ provider.name }}</strong><em>{{ provider.role }}</em></span><span class="provider-location">{{ provider.location }}</span><span :class="['provider-status', { unavailable: !provider.healthy }]"><i></i>{{ provider.status }}</span></div></div></section>

        <section id="retrieval" class="settings-section content-panel" tabindex="-1"><header><div><span class="eyebrow">Retrieval</span><h2>检索策略</h2><p>控制候选片段数量和依据不足时的拒答边界。</p></div><span class="strategy-badge">语义检索</span></header><div class="slider-setting"><label><strong>候选片段数</strong><span>检索后提供给回答模块的片段上限</span></label><el-slider v-model="topK" :min="1" :max="20" :show-tooltip="false" @change="saved = false" /><output>{{ topK }}</output></div><div class="slider-setting"><label><strong>拒答阈值</strong><span>低于阈值时明确说明资料依据不足</span></label><el-slider v-model="threshold" :min="0" :max="1" :step="0.01" :show-tooltip="false" @change="saved = false" /><output>{{ threshold.toFixed(2) }}</output></div><div class="slider-setting"><label><strong>回答温度</strong><span>数值越低，回答越稳定和保守</span></label><el-slider v-model="temperature" :min="0" :max="2" :step="0.05" :show-tooltip="false" @change="saved = false" /><output>{{ temperature.toFixed(2) }}</output></div></section>

        <section id="appearance" class="settings-section content-panel" tabindex="-1"><header><div><span class="eyebrow">Appearance</span><h2>Liquid Glass 强度</h2><p>切换材质表现，内容和信息层级保持不变。</p></div></header><div class="appearance-options"><button v-for="variant in [{ id: 'clear', title: '清透', meta: '更强背景折射' }, { id: 'balanced', title: '平衡', meta: '默认阅读体验' }, { id: 'contrast', title: '高对比', meta: '降低透明效果' }]" :key="variant.id" type="button" :class="{ active: props.glassVariant === variant.id }" @click="updateAppearance(variant.id)"><span :class="['glass-swatch', `swatch-${variant.id}`]"></span><strong>{{ variant.title }}</strong><em>{{ variant.meta }}</em></button></div></section>

        <section id="data" class="settings-section content-panel data-section" tabindex="-1"><header><div><span class="eyebrow">Data</span><h2>数据管理</h2><p>导出可迁移的 JSON 备份，或清理全部本地学习数据。</p></div></header><div class="data-actions"><button type="button" @click="exportData"><el-icon><Download /></el-icon><span><strong>导出全部数据</strong><em>课程、对话、学习产物和设置</em></span></button><button type="button" class="danger-action" @click="clearData"><el-icon><Delete /></el-icon><span><strong>清理本地数据</strong><em>永久删除，需再次确认</em></span></button></div></section>
      </div>
    </div>
  </section>
</template>
