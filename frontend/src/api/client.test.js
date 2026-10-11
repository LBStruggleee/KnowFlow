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
  listKnowledgeBases,
  listDocuments,
  listDocumentChunks,
  listLearningRecords,
  getConversation,
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

  it('listConversations 可同时透传 kb_id 与分页参数', async () => {
    await listConversations(3, { limit: 50, offset: 100 })
    expect(mockApi.get).toHaveBeenCalledWith('/api/conversations', {
      params: { kb_id: 3, limit: 50, offset: 100 },
    })
  })

  it('listKnowledgeBases 不传分页参数时发送空查询串（向后兼容）', async () => {
    await listKnowledgeBases()
    expect(mockApi.get).toHaveBeenCalledWith('/api/kbs', { params: {} })
  })

  it('listKnowledgeBases 透传 limit/offset 分页参数', async () => {
    await listKnowledgeBases({ limit: 25 })
    expect(mockApi.get).toHaveBeenCalledWith('/api/kbs', { params: { limit: 25 } })
  })

  it('listDocuments 与 listDocumentChunks 透传分页参数', async () => {
    await listDocuments(3, { limit: 10, offset: 20 })
    expect(mockApi.get).toHaveBeenCalledWith('/api/kbs/3/documents', {
      params: { limit: 10, offset: 20 },
    })
    await listDocumentChunks(7, { offset: 5 })
    expect(mockApi.get).toHaveBeenCalledWith('/api/documents/7/chunks', { params: { offset: 5 } })
  })

  it('getConversation 透传消息分页参数', async () => {
    await getConversation(9, { limit: 20, offset: 40 })
    expect(mockApi.get).toHaveBeenCalledWith('/api/conversations/9', {
      params: { limit: 20, offset: 40 },
    })
  })

  it('listLearningRecords 同时透传 kb_id 与 record_type', async () => {
    await listLearningRecords(2, 'mistake')
    expect(mockApi.get).toHaveBeenCalledWith('/api/learning-records', {
      params: { kb_id: 2, record_type: 'mistake' },
    })
  })

  it('listLearningRecords 第三参透传分页参数', async () => {
    await listLearningRecords(2, 'note', { limit: 25 })
    expect(mockApi.get).toHaveBeenCalledWith('/api/learning-records', {
      params: { kb_id: 2, record_type: 'note', limit: 25 },
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
