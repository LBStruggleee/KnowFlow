export const TASK_MODES = [
  { id: 'question', label: '自由提问' },
  { id: 'explain', label: '概念讲解' },
  { id: 'compare', label: '知识对比' },
  { id: 'summarize', label: '章节总结' },
  { id: 'exercise', label: '练习生成' },
]

export function formatBytes(bytes) {
  const size = Number(bytes)
  if (!Number.isFinite(size) || size <= 0) return '0 B'
  if (size < 1024) return `${size} B`
  if (size < 1024 ** 2) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 ** 2).toFixed(1)} MB`
}

// Must stay aligned with the backend upload limit (UPLOAD_MAX_BYTES,
// backend/app/core/config.py defaults to 50 MB) and SUPPORTED_FILE_TYPES
// (backend/app/services/document_parser.py) so rejected uploads never make
// a doomed round trip (evaluation I-21).
export const UPLOAD_MAX_BYTES = 50 * 1024 * 1024
export const SUPPORTED_UPLOAD_EXTENSIONS = ['.txt', '.md', '.pdf', '.docx', '.pptx']

export function validateUploadFile(
  file,
  { maxBytes = UPLOAD_MAX_BYTES, allowedExtensions = SUPPORTED_UPLOAD_EXTENSIONS } = {},
) {
  const name = file?.name || ''
  const extension = name.slice(name.lastIndexOf('.')).toLowerCase()
  if (!allowedExtensions.includes(extension)) {
    return { ok: false, reason: `暂不支持该文件类型，仅支持 ${allowedExtensions.join('、')}` }
  }
  if ((file?.size || 0) <= 0) return { ok: false, reason: '文件内容为空，无法解析。' }
  if (file.size > maxBytes) {
    return { ok: false, reason: `文件超过大小上限（最大 ${formatBytes(maxBytes)}），请压缩后再上传。` }
  }
  return { ok: true, reason: '' }
}

// Cloud answers carry token usage (ChatResponse.usage); local extractive
// answers have none, in which case the label stays empty and is hidden.
export function formatTokenUsage(usage) {
  const total = Number(usage?.total_tokens)
  if (!Number.isFinite(total) || total <= 0) return ''
  const prompt = Number(usage?.prompt_tokens) || 0
  const completion = Number(usage?.completion_tokens) || 0
  return `输入 ${prompt} · 输出 ${completion} · 共 ${total} tokens`
}

// Inspector surfaces show truncated chunk bodies; full text stays available
// through the original file.
export function truncatePreview(text, max = 260) {
  const value = String(text || '')
  return value.length > max ? `${value.slice(0, max)}…` : value
}

export function formatDate(value) {
  if (!value) return '刚刚'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '时间未知'
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

export function mapDocument(document) {
  return {
    ...document,
    name: document.title || document.file_name,
    type: (document.file_type || 'FILE').toUpperCase(),
    size: formatBytes(document.file_size),
    chunks: Number(document.chunk_count) || 0,
    status: document.status === 'finished' ? 'ready' : document.status,
    updatedAt: formatDate(document.updated_at),
    tags: [],
    outline: document.content_preview
      ? document.content_preview.split(/\n+/).filter(Boolean).slice(0, 5)
      : [],
  }
}

export function combineLearningRecords(conversations, records, courseName) {
  const conversationItems = conversations.map((conversation) => ({
    key: `conversation-${conversation.id}`,
    id: conversation.id,
    type: 'conversation',
    title: conversation.title,
    summary: '打开这段对话并继续追问。',
    course: courseName,
    time: formatDate(conversation.updated_at),
    meta: '已保存会话',
    tags: ['对话'],
    updatedAt: new Date(conversation.updated_at || 0).getTime(),
  }))
  const learningItems = records.map((record) => ({
    key: `record-${record.id}`,
    id: record.id,
    type: record.record_type,
    title: record.title,
    summary: record.content,
    content: record.content,
    course: courseName,
    time: formatDate(record.updated_at),
    meta: record.metadata?.reviewed ? '已复习' : '学习产物',
    tags: record.tags || [],
    metadata: record.metadata || {},
    conversationId: record.conversation_id,
    updatedAt: new Date(record.updated_at || 0).getTime(),
  }))
  return [...conversationItems, ...learningItems].sort((a, b) => b.updatedAt - a.updatedAt)
}

export function getDocumentPollDelay(attempt) {
  const step = Number.isFinite(attempt) ? Math.max(0, Math.floor(attempt)) : 0
  return Math.min(1600 * 2 ** step, 10000)
}

export function getApiErrorMessage(error, fallback = '操作失败，请稍后重试。') {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) return detail.map((item) => item.msg).filter(Boolean).join('；') || fallback
  if (error?.code === 'ECONNABORTED') return '请求超时，请检查模型服务或网络连接。'
  if (!error?.response) return '无法连接 KnowFlow 后端，请确认 API 已启动。'
  return fallback
}

export function getCourseMeta(documents) {
  const ready = documents.filter((document) => document.status === 'finished').length
  const chunks = documents.reduce((sum, document) => sum + (Number(document.chunk_count) || 0), 0)
  return `${ready}/${documents.length} 份已入库 · ${chunks} 个片段`
}
