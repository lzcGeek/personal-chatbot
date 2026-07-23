<script setup lang="ts">
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import { computed } from 'vue'

import type { ChatMessage } from '../types/chat'


const props = defineProps<{ message: ChatMessage }>()

const markdown = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
  highlight(code: string, language: string): string {
    if (language && hljs.getLanguage(language)) {
      return hljs.highlight(code, { language }).value
    }
    return MarkdownIt().utils.escapeHtml(code)
  },
})

const rendered = computed(() => markdown.render(props.message.content))
</script>

<template>
  <article class="message" :class="message.role">
    <div class="avatar" aria-hidden="true">{{ message.role === 'user' ? '你' : 'AI' }}</div>
    <div class="message-body">
      <div v-if="message.role === 'assistant'" class="markdown" v-html="rendered" />
      <div v-else>
        <span v-if="message.triggeredSkill" class="skill-tag">/{{ message.triggeredSkill }}</span>
        <p class="user-text">{{ message.content }}</p>
      </div>
      <p v-if="message.status === 'streaming' && !message.content" class="typing">正在思考…</p>
      <p v-if="message.status === 'interrupted'" class="message-status">响应已中断，以上内容可能不完整。</p>
      <p v-if="message.status === 'error'" class="message-status">未能生成回复。</p>
    </div>
  </article>
</template>
