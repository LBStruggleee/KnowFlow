import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getProviderStatus,
  getSystemSettings,
  listDocuments,
  listKnowledgeBases,
} from '../../api/client'
import { getApiErrorMessage, getCourseMeta } from '../productState'

export function useWorkbenchState() {
  const knowledgeBases = ref([])
  const documents = ref([])
  const selectedKbId = ref(null)
  const providerStatus = ref(null)
  const settings = ref(null)
  const loading = ref(true)

  const glassVariant = computed({
    get: () => settings.value?.glass_variant || 'balanced',
    set: (value) => {
      settings.value = { ...(settings.value || {}), glass_variant: value }
    },
  })
  const selectedCourse = computed(() => {
    const course = knowledgeBases.value.find((item) => item.id === selectedKbId.value)
    if (!course) return null
    return {
      ...course,
      meta: getCourseMeta(documents.value),
      tone: ['green', 'blue', 'amber'][course.id % 3],
    }
  })
  const privacyLabel = computed(() => {
    const labels = { local: '完全本地', hybrid: '本地优先', cloud: '云端增强' }
    return labels[settings.value?.privacy_mode] || '本地优先'
  })

  async function loadDocuments() {
    if (!selectedKbId.value) {
      documents.value = []
      return
    }
    try {
      documents.value = (await listDocuments(selectedKbId.value)).data
    } catch (error) {
      documents.value = []
      ElMessage.error(getApiErrorMessage(error, '无法读取课程资料。'))
    }
  }

  async function selectCourse(id) {
    selectedKbId.value = id
    await loadDocuments()
  }

  async function loadApplication() {
    loading.value = true
    try {
      const [kbResponse, settingsResponse, providerResponse] = await Promise.all([
        listKnowledgeBases(),
        getSystemSettings(),
        getProviderStatus(),
      ])
      knowledgeBases.value = kbResponse.data
      settings.value = settingsResponse.data
      providerStatus.value = providerResponse.data
      const preferredId = selectedKbId.value
      selectedKbId.value =
        knowledgeBases.value.find((item) => item.id === preferredId)?.id ||
        knowledgeBases.value[0]?.id ||
        null
      await loadDocuments()
    } catch (error) {
      ElMessage.error(getApiErrorMessage(error, 'KnowFlow 初始化失败。'))
    } finally {
      loading.value = false
    }
  }

  function handleSettingsSaved(value) {
    settings.value = value
    providerStatus.value = { ...(providerStatus.value || {}), privacy_mode: value.privacy_mode }
  }

  return {
    knowledgeBases,
    documents,
    selectedKbId,
    providerStatus,
    settings,
    loading,
    glassVariant,
    selectedCourse,
    privacyLabel,
    loadDocuments,
    selectCourse,
    loadApplication,
    handleSettingsSaved,
  }
}
