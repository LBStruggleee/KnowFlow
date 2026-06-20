import axios from 'axios'

const api = axios.create({
  baseURL: 'http://127.0.0.1:8000',
  timeout: 60000,
})

export function listKnowledgeBases() {
  return api.get('/api/kbs')
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

export function listDocuments(kbId) {
  return api.get(`/api/kbs/${kbId}/documents`)
}

export function deleteDocument(documentId) {
  return api.delete(`/api/documents/${documentId}`)
}

export function uploadDocument(kbId, file) {
  const formData = new FormData()
  formData.append('file', file)
  return api.post(`/api/kbs/${kbId}/documents/upload`, formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
}

export function listDocumentChunks(documentId) {
  return api.get(`/api/documents/${documentId}/chunks`)
}

export function askQuestion(payload) {
  return api.post('/api/chat', payload)
}

export function searchKnowledgeBase(kbId, payload) {
  return api.post(`/api/kbs/${kbId}/search`, payload)
}

export function listConversations(kbId) {
  const params = kbId ? { kb_id: kbId } : {}
  return api.get('/api/conversations', { params })
}

export function getConversation(conversationId) {
  return api.get(`/api/conversations/${conversationId}`)
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
