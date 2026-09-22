import { describe, expect, it } from 'vitest'
import {
  combineLearningRecords,
  formatBytes,
  getApiErrorMessage,
  getCourseMeta,
  mapDocument,
  TASK_MODES,
} from './productState'

describe('product state mapping', () => {
  it('maps backend document state to the product vocabulary', () => {
    const mapped = mapDocument({
      id: 1,
      title: 'Spark',
      file_type: 'pdf',
      file_size: 1536,
      chunk_count: 4,
      status: 'finished',
      content_preview: '第一章\n第二章',
    })
    expect(mapped.status).toBe('ready')
    expect(mapped.type).toBe('PDF')
    expect(mapped.size).toBe('1.5 KB')
    expect(mapped.outline).toEqual(['第一章', '第二章'])
  })

  it('combines conversations and persisted learning records by time', () => {
    const result = combineLearningRecords(
      [{ id: 1, title: '旧对话', updated_at: '2026-01-01T00:00:00Z' }],
      [
        {
          id: 2,
          record_type: 'note',
          title: '新笔记',
          content: '内容',
          tags: ['RDD'],
          metadata: {},
          updated_at: '2026-01-02T00:00:00Z',
        },
      ],
      'Spark',
    )
    expect(result.map((item) => item.key)).toEqual(['record-2', 'conversation-1'])
  })

  it('normalizes errors and course statistics', () => {
    expect(getApiErrorMessage({ response: { data: { detail: '资料不存在' } } })).toBe('资料不存在')
    expect(getApiErrorMessage({})).toContain('无法连接')
    expect(getCourseMeta([{ status: 'finished', chunk_count: 3 }, { status: 'failed' }])).toBe(
      '1/2 份已入库 · 3 个片段',
    )
    expect(formatBytes(0)).toBe('0 B')
    expect(TASK_MODES).toHaveLength(5)
  })
})
