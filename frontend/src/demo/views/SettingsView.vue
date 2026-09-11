<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
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
import { providerOptions } from '../mockData'

const props = defineProps({
  glassVariant: { type: String, default: 'balanced' },
})
const emit = defineEmits(['update:glass-variant'])

const privacyMode = ref('hybrid')
const topK = ref(8)
const threshold = ref(0.62)
const rerankCount = ref(5)
const saving = ref(false)
const saved = ref(false)
let saveTimer = null

const privacyDescription = computed(() => ({
  local: '资料、向量和回答全部在本机处理，不产生外部模型请求。',
  hybrid: '原始资料保留在本机，仅将命中的少量片段发送给云端回答模型。',
  cloud: '使用云端 Embedding 与回答模型，适合追求效果且资料允许外发的场景。',
}[privacyMode.value]))

function saveSettings() {
  saving.value = true
  saved.value = false
  saveTimer = window.setTimeout(() => {
    saving.value = false
    saved.value = true
    saveTimer = null
    ElMessage.success('模拟设置已保存')
  }, 700)
}

function jumpToSetting(id) {
  const section = document.getElementById(id)
  const container = section?.closest('.product-view')
  if (!section || !container) return
  container.scrollTop = Math.max(0, section.offsetTop - 20)
  section.focus({ preventScroll: true })
}

async function clearData() {
  try {
    await ElMessageBox.confirm('这是交互 Demo，不会真正删除数据。是否继续模拟？', '模拟清理数据', {
      confirmButtonText: '确认模拟',
      cancelButtonText: '取消',
      type: 'warning',
    })
    ElMessage.success('已完成模拟清理，实际数据未改变')
  } catch {
    // User cancelled the simulated destructive action.
  }
}

onBeforeUnmount(() => {
  if (saveTimer !== null) window.clearTimeout(saveTimer)
})
</script>

<template>
  <section class="product-view settings-view">
    <header class="view-header">
      <div>
        <span class="eyebrow">Preferences</span>
        <h1>设置</h1>
        <p>控制资料如何处理、模型如何回答，以及界面的玻璃表现。</p>
      </div>
      <div class="save-group"><span v-if="saved"><el-icon><Check /></el-icon>已保存</span><button class="primary-action glass-control" type="button" :disabled="saving" @click="saveSettings"><el-icon><Setting /></el-icon>{{ saving ? '保存中' : '保存设置' }}</button></div>
    </header>

    <div class="settings-layout">
      <nav class="settings-nav glass-surface" aria-label="设置分类">
        <button type="button" @click="jumpToSetting('privacy')"><el-icon><Lock /></el-icon><span>隐私与处理</span></button>
        <button type="button" @click="jumpToSetting('models')"><el-icon><Connection /></el-icon><span>模型服务</span></button>
        <button type="button" @click="jumpToSetting('retrieval')"><el-icon><DataLine /></el-icon><span>检索策略</span></button>
        <button type="button" @click="jumpToSetting('appearance')"><el-icon><MagicStick /></el-icon><span>界面外观</span></button>
        <button type="button" @click="jumpToSetting('data')"><el-icon><Download /></el-icon><span>数据管理</span></button>
      </nav>

      <div class="settings-content">
        <section id="privacy" class="settings-section content-panel" tabindex="-1">
          <header><div><span class="eyebrow">Privacy</span><h2>资料处理模式</h2><p>每个课程知识库都可以单独选择处理边界。</p></div><span class="health-badge"><i></i>保护已启用</span></header>
          <div class="privacy-options">
            <button v-for="mode in [{ id: 'local', title: '完全本地', meta: '不发送外部请求' }, { id: 'hybrid', title: '本地优先', meta: '仅发送命中片段' }, { id: 'cloud', title: '云端增强', meta: '使用云端完整能力' }]" :key="mode.id" type="button" :class="{ active: privacyMode === mode.id }" @click="privacyMode = mode.id"><span class="radio-dot"></span><strong>{{ mode.title }}</strong><em>{{ mode.meta }}</em></button>
          </div>
          <div class="setting-note"><el-icon><Lock /></el-icon><p><strong>当前模式说明</strong>{{ privacyDescription }}</p></div>
        </section>

        <section id="models" class="settings-section content-panel" tabindex="-1">
          <header><div><span class="eyebrow">Providers</span><h2>模型服务</h2><p>清楚显示每一步使用的模型与运行位置。</p></div><button class="icon-button glass-control" type="button" aria-label="检查连接" title="检查连接" @click="ElMessage.success('所有模拟服务连接正常')"><el-icon><Refresh /></el-icon></button></header>
          <div class="provider-list">
            <div v-for="provider in providerOptions" :key="provider.id"><span class="provider-mark">{{ provider.name.slice(0, 1) }}</span><span><strong>{{ provider.name }}</strong><em>{{ provider.role }}</em></span><span class="provider-location">{{ provider.location }}</span><span class="provider-status"><i></i>{{ provider.status }}</span></div>
          </div>
        </section>

        <section id="retrieval" class="settings-section content-panel" tabindex="-1">
          <header><div><span class="eyebrow">Retrieval</span><h2>检索策略</h2><p>模拟 Dense + BM25 召回、重排与可靠拒答。</p></div><span class="strategy-badge">Hybrid RRF</span></header>
          <div class="slider-setting"><label><strong>候选片段数</strong><span>语义与关键词融合后保留的候选数量</span></label><el-slider v-model="topK" :min="3" :max="20" :show-tooltip="false" /><output>{{ topK }}</output></div>
          <div class="slider-setting"><label><strong>拒答阈值</strong><span>低于阈值时明确说明资料依据不足</span></label><el-slider v-model="threshold" :min="0" :max="1" :step="0.01" :show-tooltip="false" /><output>{{ threshold.toFixed(2) }}</output></div>
          <div class="slider-setting"><label><strong>最终重排数量</strong><span>送入回答模型前保留的高相关证据</span></label><el-slider v-model="rerankCount" :min="2" :max="10" :show-tooltip="false" /><output>{{ rerankCount }}</output></div>
        </section>

        <section id="appearance" class="settings-section content-panel" tabindex="-1">
          <header><div><span class="eyebrow">Appearance</span><h2>Liquid Glass 强度</h2><p>直接切换三种材质表现，内容和结构保持不变。</p></div></header>
          <div class="appearance-options">
            <button v-for="variant in [{ id: 'clear', title: '清透', meta: '更强背景折射' }, { id: 'balanced', title: '平衡', meta: '默认阅读体验' }, { id: 'contrast', title: '高对比', meta: '降低透明效果' }]" :key="variant.id" type="button" :class="{ active: props.glassVariant === variant.id }" @click="emit('update:glass-variant', variant.id)"><span :class="['glass-swatch', `swatch-${variant.id}`]"></span><strong>{{ variant.title }}</strong><em>{{ variant.meta }}</em></button>
          </div>
        </section>

        <section id="data" class="settings-section content-panel data-section" tabindex="-1">
          <header><div><span class="eyebrow">Data</span><h2>数据管理</h2><p>导出、备份或清理本地学习数据。</p></div></header>
          <div class="data-actions"><button type="button" @click="ElMessage.success('已模拟生成导出包')"><el-icon><Download /></el-icon><span><strong>导出全部数据</strong><em>知识库、笔记、练习和设置</em></span></button><button type="button" class="danger-action" @click="clearData"><el-icon><Delete /></el-icon><span><strong>清理本地数据</strong><em>需要再次确认</em></span></button></div>
        </section>
      </div>
    </div>
  </section>
</template>
