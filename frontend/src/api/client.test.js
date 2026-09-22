import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockApi = vi.hoisted(() => ({
  defaults: { baseURL: 'http://127.0.0.1:8000' },
  get: vi.fn().mockResolvedValue({ data: {} }),
  post: vi.fn().mockResolvedValue({ data: {} }),
  patch: vi.fn().mockResolvedValue({ data: {} }),
  delete: vi.fn().mockResolvedValue({ data: {} }),
}))

vi.mock('axios', () => ({
  default: { create: vi.fn(() => mockApi) },
}))

import {
  listConversations,
  listLearningRecords,
  clearAllData,
  askQuestion,
  uploadDocument,
  getDocumentFileUrl,
} from './client'

describe('api/client', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('listConversations 有 kbId 时透传 kb_id 查询参数', async () => {
    await listConversations(3)
    expect(mockApi.get).toHaveBeenCalledWith('/api/conversations', { params: { kb_id: 3 } })
  })

  it('listLearningRecords 同时透传 kb_id 与 record_type', async () => {
    await listLearningRecords(2, 'mistake')
    expect(mockApi.get).toHaveBeenCalledWith('/api/learning-records', {
      params: { kb_id: 2, record_type: 'mistake' },
    })
  })

  it('clearAllData 必须携带 confirmation=DELETE（二次确认契约）', async () => {
    await clearAllData()
    expect(mockApi.delete).toHaveBeenCalledWith('/api/admin/data', {
      params: { confirmation: 'DELETE' },
    })
  })

  it('askQuestion 提交到 /api/chat', async () => {
    await askQuestion({ kb_id: 1, question: '什么是 HDFS', mode: 'question' })
    expect(mockApi.post).toHaveBeenCalledWith('/api/chat', {
      kb_id: 1,
      question: '什么是 HDFS',
      mode: 'question',
    })
  })

  it('uploadDocument 以 multipart/form-data 上传文件', async () => {
    await uploadDocument(1, 'course.md')
    const [url, formData, config] = mockApi.post.mock.calls[0]
    expect(url).toBe('/api/kbs/1/documents/upload')
    expect(formData).toBeInstanceOf(FormData)
    expect(formData.get('file')).toBe('course.md')
    expect(config.headers['Content-Type']).toBe('multipart/form-data')
  })

  it('getDocumentFileUrl 拼出可下载原始文件地址', () => {
    expect(getDocumentFileUrl(7)).toBe('http://127.0.0.1:8000/api/documents/7/file')
  })
})
