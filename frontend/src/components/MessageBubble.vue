<script setup lang="ts">
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import { computed, onMounted, ref } from 'vue'

import type { ChatMessage } from '../types/chat'
import {
  createMediaTask,
  getMediaCapabilities,
  getMessageAttachments,
  retryMediaTask,
  waitForMediaTask,
  type MediaCapabilities,
  type MediaTaskInfo,
  type MessageAttachment,
} from '../api/media'


const props = defineProps<{ message: ChatMessage }>()
const emit = defineEmits<{ retry: [] }>()

const degradationLabels: Record<string, string> = {
  memory_retrieval_failed: '长期记忆暂不可用',
  document_retrieval_failed: '个人知识库暂不可用',
  network_tool_unavailable: '未找到可用网络工具',
  network_tool_failed: '联网检索失败，已基于本地信息回答',
  tool_round_limit_reached: '工具调用达到上限，已降级收尾',
}

const degradationText = computed(() =>
  (props.message.degradations ?? [])
    .map(code => degradationLabels[code] ?? code)
    .join('；'),
)

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
const capabilities = ref<MediaCapabilities | null>(null)
const attachments = ref<MessageAttachment[]>([])
const mediaTask = ref<MediaTaskInfo | null>(null)
const mediaError = ref('')

async function loadAttachments(): Promise<void> {
  if (typeof props.message.id === 'number') {
    attachments.value = await getMessageAttachments(props.message.id)
  }
}

async function generate(kind: 'image' | 'tts'): Promise<void> {
  if (typeof props.message.id !== 'number') return
  mediaError.value = ''
  try {
    mediaTask.value = await createMediaTask(props.message.id, kind)
    mediaTask.value = await waitForMediaTask(mediaTask.value.id)
    if (mediaTask.value.status === 'failed') {
      mediaError.value = mediaTask.value.error_message || '媒体生成失败'
    } else {
      await loadAttachments()
    }
  } catch (reason: unknown) {
    mediaError.value = reason instanceof Error ? reason.message : '媒体生成失败'
  }
}

async function retryMedia(): Promise<void> {
  if (!mediaTask.value || mediaTask.value.status !== 'failed') return
  mediaError.value = ''
  try {
    mediaTask.value = await retryMediaTask(mediaTask.value.id)
    mediaTask.value = await waitForMediaTask(mediaTask.value.id)
    if (mediaTask.value.status === 'complete') await loadAttachments()
    else mediaError.value = mediaTask.value.error_message || '媒体生成失败'
  } catch (reason: unknown) {
    mediaError.value = reason instanceof Error ? reason.message : '媒体重试失败'
  }
}

onMounted(async () => {
  if (props.message.role !== 'assistant' || typeof props.message.id !== 'number') return
  try {
    ;[capabilities.value] = await Promise.all([getMediaCapabilities(), loadAttachments()])
  } catch { /* text chat remains usable */ }
})
</script>

<template>
  <article class="message" :class="message.role">
    <div class="avatar" aria-hidden="true">
      <span v-if="message.character_id">{{ message.speaker_name?.slice(0, 1) || '角' }}</span>
      <img v-if="message.character_id" :src="`/api/characters/${message.character_id}/avatar`" alt="" />
      <template v-else>{{ message.role === 'user' ? '你' : 'AI' }}</template>
    </div>
    <div class="message-body">
      <strong v-if="message.speaker_name" class="speaker-name">{{ message.speaker_name }}</strong>
      <div v-if="message.role === 'assistant'" class="markdown" v-html="rendered" />
      <div v-else>
        <span v-if="message.triggeredSkill" class="skill-tag">/{{ message.triggeredSkill }}</span>
        <p class="user-text">{{ message.content }}</p>
      </div>
      <p v-if="message.status === 'streaming' && !message.content" class="typing">正在思考…</p>
      <details v-if="message.role === 'assistant' && message.citations?.length" class="citations">
        <summary>参考了 {{ message.citations.length }} 处个人资料</summary>
        <ol>
          <li v-for="citation in message.citations" :key="citation.chunk_id">
            <strong>[来源 {{ citation.index }}] {{ citation.filename }}</strong>
            <span v-if="citation.page_number">第 {{ citation.page_number }} 页</span>
            <span v-else-if="citation.section">{{ citation.section }}</span>
            <p>{{ citation.excerpt }}</p>
          </li>
        </ol>
      </details>
      <p v-if="message.status === 'interrupted'" class="message-status">响应已中断，以上内容可能不完整。</p>
      <p v-if="message.status === 'error'" class="message-status">未能生成回复。</p>
      <p v-if="message.degraded" class="message-degradation">{{ degradationText }}</p>
      <div v-if="attachments.length" class="message-media">
        <template v-for="item in attachments" :key="item.id">
          <img v-if="item.kind === 'image'" :src="item.download_url" alt="AI 生成的场景图片" />
          <audio v-else controls preload="none" :src="item.download_url" />
        </template>
      </div>
      <div v-if="message.role === 'assistant' && message.status === 'complete' && capabilities" class="media-actions">
        <button v-if="capabilities.image.enabled" :disabled="!!mediaTask && !['complete', 'failed'].includes(mediaTask.status)" @click="generate('image')">生成图片</button>
        <button v-if="capabilities.tts.enabled" :disabled="!!mediaTask && !['complete', 'failed'].includes(mediaTask.status)" @click="generate('tts')">播放语音</button>
        <small v-if="!capabilities.image.enabled && !capabilities.tts.enabled">未配置图片或语音 Provider</small>
        <small v-if="mediaTask && !['complete', 'failed'].includes(mediaTask.status)">媒体生成中…</small>
        <button v-if="mediaTask?.status === 'failed'" @click="retryMedia">重试媒体</button>
      </div>
      <p v-if="mediaError" class="message-status">{{ mediaError }}</p>
      <button
        v-if="(message.status === 'interrupted' || message.status === 'error') && message.recoverable"
        class="message-retry"
        @click="emit('retry')"
      >
        重试
      </button>
    </div>
  </article>
</template>
