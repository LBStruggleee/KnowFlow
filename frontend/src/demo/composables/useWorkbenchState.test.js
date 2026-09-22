import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), success: vi.fn() },
  ElMessageBox: { prompt: vi.fn(), confirm: vi.fn() },
}))

vi.mock('../../api/client', () => ({
  listKnowledgeBases: vi.fn(),
  getSystemSettings: vi.fn(),
  getProviderStatus: vi.fn(),
  listDocuments: vi.fn(),
  createKnowledgeBase: vi.fn(),
}))

import { useWorkbenchState } from './useWorkbenchState'
import {
  listKnowledgeBases,
  getSystemSettings,
  getProviderStatus,
  listDocuments,
} from '../../api/client'

describe('useWorkbenchState', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listKnowledgeBases.mockResolvedValue({
      data: [{ id: 1, name: '大数据原理', category: '课程' }],
    })
    getSystemSettings.mockResolvedValue({
      data: { privacy_mode: 'hybrid', top_k: 5, glass_variant: 'balanced' },
    })
    getProviderStatus.mockResolvedValue({ data: { llm_available: false } })
    listDocuments.mockResolvedValue({ data: [] })
  })

  it('loadApplication 填充课程、设置与 Provider 状态并选中第一门课程', async () => {
    const state = useWorkbenchState()
    await state.loadApplication()
    expect(state.knowledgeBases.value).toHaveLength(1)
    expect(state.selectedKbId.value).toBe(1)
    expect(state.settings.value.privacy_mode).toBe('hybrid')
    expect(state.providerStatus.value.llm_available).toBe(false)
    expect(state.loading.value).toBe(false)
  })

  it('selectedCourse 附加 meta 与 tone（id 取模 3）', async () => {
    const state = useWorkbenchState()
    await state.loadApplication()
    // getCourseMeta 返回的是聚合字符串（已入库份数/总份数 · 片段数），而非对象字段。
    expect(state.selectedCourse.value.meta).toBe('0/0 份已入库 · 0 个片段')
    expect(state.selectedCourse.value.tone).toBe('blue') // id 1 % 3 === 1 -> 'blue'
  })

  it('privacyLabel 按设置映射中文，缺省为本地优先', async () => {
    const state = useWorkbenchState()
    await state.loadApplication()
    expect(state.privacyLabel.value).toBe('本地优先')
  })

  it('API 失败时 documents 置空且 loading 复位', async () => {
    listDocuments.mockRejectedValue(new Error('boom'))
    const state = useWorkbenchState()
    await state.loadApplication()
    expect(state.documents.value).toEqual([])
    expect(state.loading.value).toBe(false)
  })
})
