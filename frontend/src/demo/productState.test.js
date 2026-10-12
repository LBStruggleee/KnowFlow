import { describe, expect, it } from 'vitest'
import {
  combineLearningRecords,
  formatBytes,
  formatTokenUsage,
  getApiErrorMessage,
  getCourseMeta,
  getDocumentPollDelay,
  mapDocument,
  TASK_MODES,
  truncatePreview,
  UPLOAD_MAX_BYTES,
  validateUploadFile,
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

  it('backs off document polling delays and caps them', () => {
    expect(getDocumentPollDelay(0)).toBe(1600)
    expect(getDocumentPollDelay(1)).toBe(3200)
    expect(getDocumentPollDelay(2)).toBe(6400)
    expect(getDocumentPollDelay(3)).toBe(10000)
    expect(getDocumentPollDelay(10)).toBe(10000)
    expect(getDocumentPollDelay(-5)).toBe(1600)
    expect(getDocumentPollDelay(undefined)).toBe(1600)
    expect(getDocumentPollDelay(Number.NaN)).toBe(1600)
  })

  it('metadata.reviewed 让学习记录展示为已复习', () => {
    const result = combineLearningRecords(
      [],
      [
        {
          id: 5,
          record_type: 'note',
          title: '笔记',
          content: '内容',
          tags: [],
          metadata: { reviewed: true },
          updated_at: '2026-01-03T00:00:00Z',
        },
      ],
      '知识库',
    )
    expect(result[0].meta).toBe('已复习')
  })
})

describe('upload pre-validation (evaluation I-21)', () => {
  it('接受受支持扩展名且大小在上限内的文件', () => {
    expect(validateUploadFile({ name: 'notes.md', size: 2048 })).toEqual({ ok: true, reason: '' })
    expect(validateUploadFile({ name: '报告.PDF', size: UPLOAD_MAX_BYTES })).toEqual({
      ok: true,
      reason: '',
    })
  })

  it('拒绝不支持的扩展名、无扩展名与双扩展名伪装', () => {
    expect(validateUploadFile({ name: 'evil.exe', size: 10 }).ok).toBe(false)
    expect(validateUploadFile({ name: 'README', size: 10 }).ok).toBe(false)
    expect(validateUploadFile({ name: 'report.pdf.exe', size: 10 }).ok).toBe(false)
  })

  it('拒绝空文件', () => {
    expect(validateUploadFile({ name: 'empty.txt', size: 0 }).ok).toBe(false)
  })

  it('拒绝超过上限的文件，并提示与后端一致的上限', () => {
    const result = validateUploadFile({ name: 'big.pdf', size: UPLOAD_MAX_BYTES + 1 })
    expect(result.ok).toBe(false)
    expect(result.reason).toContain('50.0 MB')
  })

  it('允许调用方覆盖上限参数', () => {
    expect(validateUploadFile({ name: 'a.md', size: 100 }, { maxBytes: 50 }).ok).toBe(false)
  })
})

describe('token usage label (evaluation R-06)', () => {
  it('云端回答生成可读的 token 摘要', () => {
    expect(
      formatTokenUsage({ prompt_tokens: 800, completion_tokens: 434, total_tokens: 1234 }),
    ).toBe('输入 800 · 输出 434 · 共 1234 tokens')
  })

  it('本地回答无 usage 时返回空串（调用方据此隐藏）', () => {
    expect(formatTokenUsage(null)).toBe('')
    expect(formatTokenUsage(undefined)).toBe('')
    expect(formatTokenUsage({})).toBe('')
    expect(formatTokenUsage({ total_tokens: 0 })).toBe('')
  })
})

describe('chunk preview truncation', () => {
  it('超过上限时截断并追加省略号，短文本与空值原样返回', () => {
    expect(truncatePreview('短文本')).toBe('短文本')
    expect(truncatePreview('')).toBe('')
    expect(truncatePreview(null)).toBe('')
    const long = 'a'.repeat(261)
    expect(truncatePreview(long)).toBe(`${'a'.repeat(260)}…`)
    expect(truncatePreview('b'.repeat(500), 10)).toBe(`${'b'.repeat(10)}…`)
  })
})
