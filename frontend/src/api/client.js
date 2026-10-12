import axios from 'axios'

// Same-origin by default: the dev server proxies '/api' to the backend
// (vite.config.js server.proxy) and production serves the SPA from the
// backend itself. VITE_API_BASE still overrides it with a full origin such
// as 'http://127.0.0.1:8000' for direct backend connections.
const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '',
  timeout: 60000,
})

export function getApiBaseUrl() {
  return api.defaults.baseURL
}

// Pagination is optional everywhere: omitting it keeps the server defaults
// (limit 100, offset 0), so existing callers stay unchanged.
function paginationParams({ limit, offset } = {}) {
  const params = {}
  if (limit !== undefined) params.limit = limit
  if (offset !== undefined) params.offset = offset
  return params
}

export function getKnowledgeBase(kbId) {
  return api.get(`/api/kbs/${kbId}`)
}

export function listKnowledgeBases(page = {}) {
  return api.get('/api/kbs', { params: paginationParams(page) })
}

export function createKnowledgeBase(payload) {
  return api.post('/api/kbs', payload)
}

export function deleteKnowledgeBase(kbId) {
  return api.delete(`/api/kbs/${kbId}`)
}

export function updateKnowledgeBase(kbId, payload) {
  return api.patch(`/api/kbs/${kbId}`, payload)
}

export function listDocuments(kbId, page = {}) {
  return api.get(`/api/kbs/${kbId}/documents`, { params: paginationParams(page) })
}

export function deleteDocument(documentId) {
  return api.delete(`/api/documents/${documentId}`)
}

export function retryDocument(documentId) {
  return api.post(`/api/documents/${documentId}/retry`)
}

export function uploadDocument(kbId, file, onProgress) {
  const formData = new FormData()
  formData.append('file', file)
  return api.post(`/api/kbs/${kbId}/documents/upload`, formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    onUploadProgress: onProgress,
  })
}

export function getDocumentFileUrl(documentId) {
  return `${getApiBaseUrl()}/api/documents/${documentId}/file`
}

export function rebuildKnowledgeBaseIndex(kbId) {
  return api.post(`/api/kbs/${kbId}/rebuild-index`)
}

export function listDocumentChunks(documentId, page = {}) {
  return api.get(`/api/documents/${documentId}/chunks`, { params: paginationParams(page) })
}

export function listDocumentSections(documentId, page = {}) {
  return api.get(`/api/documents/${documentId}/sections`, { params: paginationParams(page) })
}

export function askQuestion(payload) {
  return api.post('/api/chat', payload)
}

export function searchKnowledgeBase(kbId, payload) {
  return api.post(`/api/kbs/${kbId}/search`, payload)
}

export function listConversations(kbId, page = {}) {
  const params = paginationParams(page)
  if (kbId) params.kb_id = kbId
  return api.get('/api/conversations', { params })
}

export function getConversation(conversationId, page = {}) {
  return api.get(`/api/conversations/${conversationId}`, { params: paginationParams(page) })
}

export function deleteConversation(conversationId) {
  return api.delete(`/api/conversations/${conversationId}`)
}

export function getSystemStatus() {
  return api.get('/api/admin/status')
}

export function getSystemSettings() {
  return api.get('/api/admin/settings')
}

export function updateSystemSettings(payload) {
  return api.patch('/api/admin/settings', payload)
}

export function getProviderStatus() {
  return api.get('/api/admin/providers')
}

export function getLearningRecord(recordId) {
  return api.get(`/api/learning-records/${recordId}`)
}

export function listLearningRecords(kbId, recordType, page = {}) {
  const params = paginationParams(page)
  if (kbId) params.kb_id = kbId
  if (recordType) params.record_type = recordType
  return api.get('/api/learning-records', { params })
}

export function createLearningRecord(payload) {
  return api.post('/api/learning-records', payload)
}

export function updateLearningRecord(recordId, payload) {
  return api.patch(`/api/learning-records/${recordId}`, payload)
}

export function deleteLearningRecord(recordId) {
  return api.delete(`/api/learning-records/${recordId}`)
}

export function exportAllData() {
  return api.get('/api/admin/export')
}

export function clearAllData() {
  return api.delete('/api/admin/data', { params: { confirmation: 'DELETE' } })
}
