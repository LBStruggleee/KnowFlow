# Liquid Glass 正式入口切换 + 端到端验收 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把已完成的 Liquid Glass 工作台切换为正式入口（`index.html`/`src/main.js`），抽取根级 composable，清理遗留代码，并完成 V1 端到端验收。

**Architecture:** 后端已 100% 满足《技术方案》§7 API 契约，无需改动。前端正式入口当前是旧版 Element Plus 控制台（`src/App.vue`），而 Liquid Glass 工作台（`src/demo/DemoApp.vue` + 4 个 views）已完整连接真实 API 但只挂在 `demo.html`。本计划让两个 HTML 入口复用同一个 `DemoApp` 组件，把 `DemoApp.vue` 中的跨视图状态抽取为根级 composable（方案 §8.1），删除死代码，最后跑完整验收。

**Tech Stack:** FastAPI + SQLAlchemy + Chroma（后端，已完成）；Vue 3 `<script setup>` + Vite 8 + vitest 4 + Element Plus（前端）。

**Spec:** `docs/技术方案.md`（§7 API 契约、§8 前端实现、§9 测试策略、§10 交付阶段、§11 V1 验收）+ `docs/产品设计改进方案.md`（§9 成功标准）。

## Global Constraints

- 每个任务独立 Git commit；任何阶段测试失败不得进入下一阶段（方案 §10）。
- 每次改动后必须更新/新增测试并保证全部通过（AGENTS.md）。
- 后端默认仅监听 `127.0.0.1`；不新增后端依赖。
- 保留 `demo.html` 第二入口，两个入口必须复用同一组件（方案 §8）。
- 触控目标至少 44px；移动端 390px 无页面级横向溢出（方案 §8.3）。
- 证据面板桌面折叠为竖向胶囊、移动端横向胶囊（方案 §8.3，已实现，不得回退）。
- 不在浏览器保存 API Key（方案 §8.3）。
- 数据清理必须二次确认（方案 §6.4，`confirmation=DELETE` 参数）。

## Review Focus

1. **无 API Key 的本地闭环**：`/api/admin/providers` 返回 `llm_available: false` 时界面必须正常展示"本地提取式回答"，不得报错 → Task 4 浏览器检查 + Task 2 composable 测试断言 provider 状态透传。
2. **刷新持久性**：会话/笔记/练习/错题刷新后仍存在（SQLite 事实源）→ Task 4 浏览器重载检查。
3. **清理数据二次确认**：`clearAllData()` 必须带 `confirmation=DELETE` → Task 3 单元测试。
4. **390px 横向溢出**：正式入口切换后移动端不得出现页面级横向滚动 → Task 4 浏览器 390px 检查。
5. **hash 视图路由**：`#knowledge` 等 hash 恢复对应视图，composable 抽取后不得破坏 → Task 2 composable 测试 + Task 4 浏览器检查。
6. **后端契约零回归**：本计划不改后端，Task 4 全量 pytest 必须通过以证明。

---

### Task 0: 提交工作区中未完成的 Stage-3 改动（基线）

**Files:**
- Modify: `.gitignore`（追加 `generated/`）
- Commit: 工作区现有的 7 个修改文件 + 3 个未跟踪前端文件

**Interfaces:**
- Consumes: 无
- Produces: 干净的工作区基线（后续任务基于已提交的 demo 视图改动）

- [ ] **Step 1: 运行前端测试确认基线可用**

Run: `cd frontend && npm test`
Expected: 全部 PASS（若失败，先修复失败再继续，不得带病提交）

- [ ] **Step 2: 把 `generated/` 加入 .gitignore**

在 `.gitignore` 末尾追加一行：

```
generated/
```

- [ ] **Step 3: 提交 Stage-3 前端改动（不包含 `generated/` 和 `instructions.md`）**

```bash
git add .gitignore frontend/src/api/client.js frontend/src/demo/DemoApp.vue frontend/src/demo/pages.css frontend/src/demo/views/KnowledgeView.vue frontend/src/demo/views/RecordsView.vue frontend/src/demo/views/SettingsView.vue frontend/src/demo/productState.js frontend/src/demo/productState.test.js frontend/src/demo/views/AssistantView.vue
git commit -m "feat: wire liquid glass demo views to real api"
```

注意：`instructions.md`（内容为杂散文本"You are a helpful AI coding assistant."）与 `generated/` 是非项目产物，不提交；`instructions.md` 保留在磁盘上待用户决定。

---

### Task 1: 正式入口切换为 Liquid Glass 工作台

**Files:**
- Modify: `frontend/src/main.js`（整文件替换，7 行 → 11 行）
- Modify: `frontend/index.html`（meta/title 对齐 demo.html）
- Create: 无
- Delete: `frontend/src/App.vue`、`frontend/src/style.css`、`frontend/src/components/ChatMessageStream.vue`（仅被旧 App.vue 引用，切换后均为死代码）

**Interfaces:**
- Consumes: `src/demo/DemoApp.vue`（默认导出组件，无需修改）
- Produces: `index.html` 入口挂载与 `demo.html` 完全相同的 `DemoApp` 组件（方案 §8"复用同一应用组件"）；后续任务的浏览器验收基于此入口

- [ ] **Step 1: 替换 `frontend/src/main.js`**

```js
import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './demo/demo.css'
import './demo/evidence-panel.css'
import './demo/pages.css'
import './demo/settings.css'
import './demo/responsive.css'
import DemoApp from './demo/DemoApp.vue'

createApp(DemoApp).use(ElementPlus).mount('#app')
```

- [ ] **Step 2: 更新 `frontend/index.html`（对齐 demo.html 的 meta）**

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="theme-color" content="#dfe8e3" />
    <meta name="description" content="KnowFlow 私有课程知识库 Agent" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <title>KnowFlow 学习助手</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.js"></script>
  </body>
</html>
```

- [ ] **Step 3: 确认删除目标无其他引用**

Run: `grep -r "App.vue\|style.css\|ChatMessageStream" frontend/src --include="*.vue" --include="*.js" --include="*.html" -l`（排除将被删除的文件本身）
Expected: 无输出（若 `demo.html`/`index.html` 之外的文件引用了它们，先处理引用）

- [ ] **Step 4: 删除死代码**

```bash
git rm frontend/src/App.vue frontend/src/style.css frontend/src/components/ChatMessageStream.vue
```

- [ ] **Step 5: 构建验证两个入口均可产出**

Run: `cd frontend && npm run build`
Expected: 构建成功，输出包含 `app` 与 `demo` 两个 HTML 入口，无 "Rollup failed to resolve" 错误

- [ ] **Step 6: 运行前端测试**

Run: `cd frontend && npm test`
Expected: 全部 PASS

- [ ] **Step 7: Commit**

```bash
git add frontend/src/main.js frontend/index.html
git commit -m "feat: switch main entry to liquid glass workbench"
```

---

### Task 2: 抽取根级 composable（方案 §8.1）

**Files:**
- Create: `frontend/src/demo/composables/useWorkbenchState.js`
- Create: `frontend/src/demo/composables/useWorkbenchState.test.js`
- Modify: `frontend/src/demo/DemoApp.vue`（改为消费 composable，仅保留视图/导航状态）

**Interfaces:**
- Consumes: `../api/client` 的 `listKnowledgeBases`、`getSystemSettings`、`getProviderStatus`、`listDocuments`、`createKnowledgeBase`；`./productState` 的 `getApiErrorMessage`、`getCourseMeta`
- Produces: `useWorkbenchState()` 返回 `{ knowledgeBases, documents, selectedKbId, providerStatus, settings, loading, glassVariant, selectedCourse, privacyLabel, loadDocuments, selectCourse, loadApplication, handleSettingsSaved }`（ref/computed 语义与原 DemoApp.vue 中同名成员完全一致；`selectCourse(id)`、`handleSettingsSaved(value)` 为 async 函数）

- [ ] **Step 1: 编写失败的 composable 测试**

创建 `frontend/src/demo/composables/useWorkbenchState.test.js`：

```js
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), success: vi.fn() },
  ElMessageBox: { prompt: vi.fn(), confirm: vi.fn() },
}))

vi.mock('../api/client', () => ({
  listKnowledgeBases: vi.fn(),
  getSystemSettings: vi.fn(),
  getProviderStatus: vi.fn(),
  listDocuments: vi.fn(),
  createKnowledgeBase: vi.fn(),
}))

import {
  useWorkbenchState,
} from './useWorkbenchState'
import {
  listKnowledgeBases,
  getSystemSettings,
  getProviderStatus,
  listDocuments,
} from '../api/client'

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
    expect(state.selectedCourse.value.meta.finishedCount).toBe(0)
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
```

注意：`selectedCourse.value.meta` 的具体字段以 `src/demo/productState.js` 的 `getCourseMeta` 返回为准（当前返回含 `finishedCount`，执行时先读该函数确认字段名，若不同则按实际字段断言）。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/demo/composables/useWorkbenchState.test.js`
Expected: FAIL，报错"Cannot find module './useWorkbenchState'"

- [ ] **Step 3: 实现 composable**

创建 `frontend/src/demo/composables/useWorkbenchState.js`（代码从 `DemoApp.vue` 第 39–157 行原样搬移，不改变行为）：

```js
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getProviderStatus,
  getSystemSettings,
  listDocuments,
  listKnowledgeBases,
} from '../api/client'
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend && npx vitest run src/demo/composables/useWorkbenchState.test.js`
Expected: 4 个测试全部 PASS

- [ ] **Step 5: 改造 `DemoApp.vue` 消费 composable**

在 `<script setup>` 中：

1. 删除已搬走的状态与函数（`knowledgeBases`、`documents`、`selectedKbId`、`providerStatus`、`settings`、`loading`、`glassVariant`、`selectedCourse`、`privacyLabel`、`loadDocuments`、`selectCourse` 中的文档加载部分、`loadApplication`、`handleSettingsSaved`）。
2. 加入：

```js
import { useWorkbenchState } from './composables/useWorkbenchState'

const {
  knowledgeBases,
  documents,
  selectedKbId,
  providerStatus,
  settings,
  loading,
  glassVariant,
  selectedCourse,
  privacyLabel,
  selectCourse,
  loadApplication,
  handleSettingsSaved,
} = useWorkbenchState()
```

3. `DemoApp.vue` 自有的 `selectCourse(id)` 保留为薄包装（先调 composable 的 `selectCourse`，再清空 `resumeConversationId.value = null`、关闭 `mobileNavOpen`）：

```js
async function selectCourseAndCloseNav(id) {
  await selectCourse(id)
  resumeConversationId.value = null
  mobileNavOpen.value = false
}
```

模板中所有 `@click="selectCourse(course.id)"` 改为 `@click="selectCourseAndCloseNav(course.id)"`。
4. `createCourse` 中原 `await selectCourse(data.id)` 改为 `await selectCourseAndCloseNav(data.id)`；其余（`activeView`、`resumeConversationId`、`mobileNavOpen`、hash 逻辑、`openAssistant`、`syncHash`、`syncViewFromHash`）保持不变。

- [ ] **Step 6: 运行全部前端测试 + 构建**

Run: `cd frontend && npm test && npm run build`
Expected: 全部 PASS，构建成功

- [ ] **Step 7: Commit**

```bash
git add frontend/src/demo/composables frontend/src/demo/DemoApp.vue
git commit -m "refactor: extract root workbench state composable"
```

---

### Task 3: 清理遗留 mockData + API client 单元测试（方案 §9.2）

**Files:**
- Delete: `frontend/src/demo/mockData.js`、`frontend/src/demo/mockData.test.js`
- Create: `frontend/src/api/client.test.js`

**Interfaces:**
- Consumes: `src/api/client.js` 的既有导出
- Produces: `client.test.js` 固化 API client 的关键契约（参数透传、FormData、确认参数）

- [ ] **Step 1: 确认 mockData 无引用**

Run: `grep -r "mockData" frontend/src --include="*.vue" --include="*.js" -l`
Expected: 仅 `frontend/src/demo/mockData.js` 与 `frontend/src/demo/mockData.test.js` 自身（若有其他引用，先迁移再删）

- [ ] **Step 2: 编写失败的 client 测试**

创建 `frontend/src/api/client.test.js`：

```js
import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockApi = {
  defaults: { baseURL: 'http://127.0.0.1:8000' },
  get: vi.fn().mockResolvedValue({ data: {} }),
  post: vi.fn().mockResolvedValue({ data: {} }),
  patch: vi.fn().mockResolvedValue({ data: {} }),
  delete: vi.fn().mockResolvedValue({ data: {} }),
}

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
```

- [ ] **Step 3: 运行测试确认通过（新测试应直接 PASS，mock 层不依赖网络）**

Run: `cd frontend && npx vitest run src/api/client.test.js`
Expected: 6 个测试全部 PASS

- [ ] **Step 4: 删除遗留 mockData**

```bash
git rm frontend/src/demo/mockData.js frontend/src/demo/mockData.test.js
```

- [ ] **Step 5: 运行全部前端测试 + 构建**

Run: `cd frontend && npm test && npm run build`
Expected: 全部 PASS（mockData.test.js 已随文件删除），构建成功

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/client.test.js
git commit -m "test: cover api client contract and drop legacy mock data"
```

---

### Task 4: 端到端验收（方案 §11）

**Files:**
- Modify: `frontend/README.md`（更新启动与入口说明）
- 无新增测试文件；验收 = 全量自动化测试 + 浏览器行为检查

**Interfaces:**
- Consumes: Task 0–3 的全部产出
- Produces: 通过 V1 验收清单的主分支

- [ ] **Step 1: 全量后端测试**

Run: `cd backend && python -m pytest -v`
Expected: 全部 PASS（若环境缺依赖，先 `pip install -r requirements.txt -r requirements-dev.txt`）

- [ ] **Step 2: 全量前端测试 + 构建 + 静态检查**

Run: `cd frontend && npm test && npm run build`
Expected: 全部 PASS，构建成功

- [ ] **Step 3: 启动本地服务**

后端：`cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`（后台运行）
前端：`cd frontend && npm run dev`（后台运行，记下端口，默认 5173）

- [ ] **Step 4: 浏览器验收核心路径（390 / 768 / 1440 三档视口）**

对每档视口检查：
1. 打开正式入口（如 `http://127.0.0.1:5173/`），无页面级横向溢出、无控制台错误；
2. 创建课程 → 上传一个 `.md` 资料 → 等待状态变为"已入库"；
3. 提问（五种模式至少各试一次"自由提问"与"练习生成"）→ 回答展示引用数量与最高匹配度，引用含文档名与位置；
4. 保存笔记 / 保存练习 → 刷新页面 → 学习记录中仍存在；
5. 打开 `#records`、`#knowledge`、`#settings` hash 均恢复对应视图；
6. 设置页 Provider 状态展示正常（无 Key 时显示"当前使用本地提取式回答"）；
7. 数据清理入口有二次确认弹窗，点取消不删除。

- [ ] **Step 5: 修复验收中发现的问题**

每个问题：先写失败测试（可固化的部分进 vitest/pytest），修复后测试转绿，随本任务一起提交。若无可固化行为则直接修复。

- [ ] **Step 6: 更新 `frontend/README.md`**

说明两处改动：正式入口 `index.html` 即 Liquid Glass 工作台（与 `demo.html` 复用同一组件）；`npm run dev` 后访问 `/` 即正式界面、`/demo.html` 为同一应用的第二入口。

- [ ] **Step 7: 最终提交并推送**

```bash
git add frontend/README.md docs/superpowers/plans/2026-09-22-liquid-glass-main-entry.md
git commit -m "docs: verify v1 end-to-end and update frontend readme"
git push origin main
```

- [ ] **Step 8: 勾选本计划所有已完成 checkbox，标记计划完成**

---

## Self-Review 记录

1. **Spec 覆盖**：方案 §8（正式入口/复用组件/composable）→ Task 1、2；§9.2（client 测试、清理 mock）→ Task 3；§10 阶段 4 + §11 验收 → Task 4；§10 阶段 1–2 已在历史 commit 完成（`test_docs_contract.py`、`6ad38b5`），Task 4 Step 1 回归确认。方案 §3 模块图中 `composables/` 目录 → Task 2 建立。无缺口。
2. **占位符扫描**：无 TBD/TODO；所有代码步骤含完整代码。
3. **类型一致性**：composable 返回成员名与 `DemoApp.vue` 现有成员逐一对应（`loadDocuments/selectCourse/loadApplication/handleSettingsSaved` 签名不变）；测试中 mock 的函数名与 `api/client.js` 实际导出一致。
4. **Review Focus**：6 条均有归属任务与测试/检查步骤（见各条标注）。
