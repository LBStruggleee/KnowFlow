<script setup>
import { computed, ref } from 'vue'
import {
  ArrowUp,
  Bell,
  Collection,
  Document,
  EditPen,
  Files,
  FolderOpened,
  Lock,
  MagicStick,
  Menu,
  MoreFilled,
  Notebook,
  Plus,
  Reading,
  Search,
  Setting,
  Tickets,
} from '@element-plus/icons-vue'
import { courses, navItems as navDefinitions, sources, taskModes } from './mockData'

const navIcons = { assistant: Reading, knowledge: FolderOpened, records: Notebook, settings: Setting }
const navItems = navDefinitions.map((item) => ({ ...item, icon: navIcons[item.id] }))

const activeView = ref('assistant')
const activeMode = ref('自由提问')
const selectedCourseId = ref(1)
const question = ref('')
const sourcePanelOpen = ref(true)
const mobileNavOpen = ref(false)
const selectedSourceId = ref(1)

const selectedCourse = computed(() =>
  courses.find((course) => course.id === selectedCourseId.value),
)

function selectView(view) {
  activeView.value = view
  mobileNavOpen.value = false
}

function useSuggestion(text) {
  question.value = text
}
</script>

<template>
  <main class="demo-canvas">
    <div class="ambient-grid" aria-hidden="true">
      <span class="ambient-block block-green"></span>
      <span class="ambient-block block-blue"></span>
      <span class="ambient-block block-amber"></span>
    </div>

    <header class="mobile-header glass-surface">
      <button class="icon-button glass-control" type="button" aria-label="打开导航" @click="mobileNavOpen = !mobileNavOpen">
        <el-icon><Menu /></el-icon>
      </button>
      <div class="mobile-brand"><span>K</span><strong>KnowFlow</strong></div>
      <button class="icon-button glass-control" type="button" aria-label="通知">
        <el-icon><Bell /></el-icon>
      </button>
    </header>

    <aside :class="['sidebar', 'glass-surface', { 'is-open': mobileNavOpen }]">
      <div class="brand-lockup">
        <div class="brand-symbol">K</div>
        <div>
          <strong>KnowFlow</strong>
          <span>课程知识工作台</span>
        </div>
      </div>

      <nav class="primary-nav" aria-label="主导航">
        <button
          v-for="item in navItems"
          :key="item.id"
          type="button"
          :class="['nav-item', { active: activeView === item.id }]"
          @click="selectView(item.id)"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </button>
      </nav>

      <section class="course-switcher">
        <div class="section-label-row">
          <span class="section-label">我的课程</span>
          <button class="tiny-action" type="button" aria-label="新建课程" title="新建课程">
            <el-icon><Plus /></el-icon>
          </button>
        </div>
        <button
          v-for="course in courses"
          :key="course.id"
          type="button"
          :class="['course-item', { active: selectedCourseId === course.id }]"
          @click="selectedCourseId = course.id"
        >
          <span :class="['course-mark', `tone-${course.tone}`]"></span>
          <span>
            <strong>{{ course.name }}</strong>
            <em>{{ course.meta }}</em>
          </span>
        </button>
      </section>

      <footer class="sidebar-footer">
        <div class="privacy-status">
          <span class="privacy-icon"><el-icon><Lock /></el-icon></span>
          <span><strong>本地优先</strong><em>仅检索片段用于云端回答</em></span>
        </div>
        <button class="avatar-button" type="button" aria-label="用户菜单">BL</button>
      </footer>
    </aside>

    <section class="workspace">
      <header class="workspace-toolbar glass-surface">
        <div class="breadcrumb">
          <span>{{ selectedCourse.name }}</span>
          <span class="slash">/</span>
          <strong>学习助手</strong>
        </div>
        <div class="toolbar-actions">
          <button class="search-trigger glass-control" type="button">
            <el-icon><Search /></el-icon>
            <span>搜索资料</span>
            <kbd>⌘ K</kbd>
          </button>
          <button class="icon-button glass-control" type="button" aria-label="通知" title="通知">
            <el-icon><Bell /></el-icon>
          </button>
          <button class="icon-button glass-control" type="button" aria-label="更多" title="更多">
            <el-icon><MoreFilled /></el-icon>
          </button>
        </div>
      </header>

      <div v-if="activeView === 'assistant'" class="assistant-layout">
        <section class="conversation-pane">
          <header class="conversation-header">
            <div>
              <span class="eyebrow">当前课程</span>
              <h1>{{ selectedCourse.name }}</h1>
              <p>基于 12 份课程资料回答，关键结论将标注原文引用。</p>
            </div>
            <button class="new-chat-button glass-control" type="button">
              <el-icon><EditPen /></el-icon>
              <span>新对话</span>
            </button>
          </header>

          <div class="mode-strip" role="tablist" aria-label="学习任务类型">
            <button
              v-for="mode in taskModes"
              :key="mode"
              type="button"
              :class="{ active: activeMode === mode }"
              @click="activeMode = mode"
            >
              {{ mode }}
            </button>
          </div>

          <div class="conversation-scroll">
            <article class="message user-message">
              <span class="message-author">你</span>
              <p>RDD 为什么具有容错能力？它和缓存机制是什么关系？</p>
            </article>

            <article class="message assistant-message">
              <header class="assistant-author">
                <span class="assistant-mark"><el-icon><MagicStick /></el-icon></span>
                <span><strong>KnowFlow</strong><em>已核对 3 个来源</em></span>
              </header>
              <div class="answer-content">
                <p>RDD 的容错能力主要来自<strong>血统关系（Lineage）</strong>，而不是为每份数据保存完整副本。</p>
                <ol>
                  <li>
                    RDD 会记录从父 RDD 到当前 RDD 的一系列转换关系。当某个分区丢失时，Spark 可以根据这些依赖关系重新计算该分区。
                    <button class="citation-chip" type="button" @click="selectedSourceId = 1; sourcePanelOpen = true">1</button>
                  </li>
                  <li>
                    窄依赖通常只需要重新计算少量父分区；宽依赖可能涉及 Shuffle，因此恢复成本更高。
                    <button class="citation-chip" type="button" @click="selectedSourceId = 2; sourcePanelOpen = true">2</button>
                  </li>
                  <li>
                    缓存不是容错的前提，而是性能优化。缓存数据丢失后仍可沿 Lineage 重算；合理缓存能减少重复计算。
                    <button class="citation-chip" type="button" @click="selectedSourceId = 3; sourcePanelOpen = true">3</button>
                  </li>
                </ol>
                <div class="answer-summary">
                  <strong>一句话理解</strong>
                  <span>Lineage 决定“能不能恢复”，缓存决定“需不需要经常重算”。</span>
                </div>
              </div>
              <footer class="answer-actions">
                <button type="button"><el-icon><Notebook /></el-icon>存为笔记</button>
                <button type="button"><el-icon><Tickets /></el-icon>生成练习</button>
                <button type="button"><el-icon><Document /></el-icon>查看检索过程</button>
              </footer>
            </article>
          </div>

          <section class="composer glass-surface">
            <textarea v-model="question" rows="2" :placeholder="`继续询问 ${selectedCourse.name}…`"></textarea>
            <div class="composer-footer">
              <div class="composer-context">
                <button type="button"><el-icon><Collection /></el-icon>全部资料</button>
                <span>3 个候选片段</span>
              </div>
              <button class="send-button" type="button" :disabled="!question.trim()" aria-label="发送问题">
                <el-icon><ArrowUp /></el-icon>
              </button>
            </div>
          </section>

          <div class="suggestion-row">
            <span>继续探索</span>
            <button type="button" @click="useSuggestion('窄依赖和宽依赖如何影响故障恢复？')">比较窄依赖与宽依赖</button>
            <button type="button" @click="useSuggestion('根据这部分内容生成 3 道练习题')">生成 3 道练习题</button>
          </div>
        </section>

        <aside :class="['evidence-panel', 'glass-surface', { collapsed: !sourcePanelOpen }]">
          <header class="evidence-header">
            <div>
              <span class="eyebrow">Evidence</span>
              <h2>回答依据</h2>
            </div>
            <button class="icon-button glass-control" type="button" aria-label="收起引用" @click="sourcePanelOpen = !sourcePanelOpen">
              <el-icon><Files /></el-icon>
            </button>
          </header>

          <template v-if="sourcePanelOpen">
            <div class="evidence-summary">
              <span><i class="status-dot"></i>依据充分</span>
              <strong>3 个来源</strong>
              <em>最高匹配 96%</em>
            </div>

            <div class="source-list">
              <button
                v-for="source in sources"
                :key="source.id"
                type="button"
                :class="['source-item', { active: selectedSourceId === source.id }]"
                @click="selectedSourceId = source.id"
              >
                <span class="source-index">{{ source.badge }}</span>
                <span class="source-copy">
                  <strong>{{ source.title }}</strong>
                  <em>{{ source.location }}</em>
                </span>
                <span class="source-score">{{ source.score }}</span>
                <p>{{ source.excerpt }}</p>
              </button>
            </div>

            <button class="open-source-button glass-control" type="button">
              <el-icon><Document /></el-icon>
              <span>在原文中定位</span>
            </button>
          </template>
        </aside>
      </div>

      <section v-else class="placeholder-view">
        <div class="placeholder-icon"><el-icon><component :is="navItems.find((item) => item.id === activeView)?.icon" /></el-icon></div>
        <span class="eyebrow">V0 结构预览</span>
        <h1>{{ navItems.find((item) => item.id === activeView)?.label }}</h1>
        <p>该区域会在下一版补充完整模拟数据与操作流程。</p>
        <button class="new-chat-button glass-control" type="button" @click="selectView('assistant')">返回学习助手</button>
      </section>
    </section>
  </main>
</template>
