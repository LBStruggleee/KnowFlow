<script setup>
import MarkdownIt from 'markdown-it'

defineProps({
  messages: {
    type: Array,
    required: true,
  },
})

const markdown = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
})

function renderMessage(content) {
  return markdown.render(content || '')
}
</script>

<template>
  <section v-if="messages.length" class="message-stream" aria-label="会话消息">
    <article
      v-for="(message, index) in messages"
      :key="message.id || `${message.role}-${index}`"
      :class="['message-bubble', `message-${message.role}`]"
    >
      <header>
        <span v-if="message.role === 'assistant'" class="ai-dot"></span>
        <strong>{{ message.role === 'assistant' ? 'AI 回答' : '你' }}</strong>
      </header>
      <div
        v-if="message.role === 'assistant'"
        class="markdown-body"
        v-html="renderMessage(message.content)"
      ></div>
      <p v-else>{{ message.content }}</p>
    </article>
  </section>
</template>

<style scoped>
.message-stream {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin: 18px;
}

.message-bubble {
  max-width: min(820px, 88%);
  padding: 14px 16px;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  color: var(--color-text);
  line-height: 1.7;
}

.message-bubble header {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-bottom: 8px;
}

.message-bubble p {
  margin: 0;
  white-space: pre-wrap;
}

.message-user {
  align-self: flex-end;
  background: rgba(0, 71, 171, 0.08);
}

.message-assistant {
  align-self: flex-start;
  background: #fff;
}

.ai-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: var(--color-accent);
  box-shadow: 0 0 0 4px rgba(0, 71, 171, 0.12);
}
</style>
