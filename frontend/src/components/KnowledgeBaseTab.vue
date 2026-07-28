<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

import type { DocumentInfo, GraphMode } from '../api/documents'
import type { RetrievalMode } from '../api/conversations'
import { documentStatusLabel } from '../document-status'
import { useConversationStore } from '../stores/conversations'
import { useDocumentStore } from '../stores/documents'


const store = useDocumentStore()
const conversationStore = useConversationStore()
const input = ref<HTMLInputElement | null>(null)
const graphMode = ref<GraphMode>('inherit')
const currentConversation = computed(() =>
  conversationStore.conversations.find(item => item.id === conversationStore.currentId),
)
let pollTimer: number | undefined

function chooseFile(): void {
  input.value?.click()
}

async function handleFile(event: Event): Promise<void> {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (file) await store.upload(file, graphMode.value)
  target.value = ''
}

async function handleRetrievalMode(event: Event): Promise<void> {
  const id = conversationStore.currentId
  if (!id) return
  const mode = (event.target as HTMLSelectElement).value as RetrievalMode
  await conversationStore.setRetrievalMode(id, mode)
}

async function remove(item: DocumentInfo): Promise<void> {
  if (window.confirm(`删除“${item.filename}”及其全部索引和图谱知识？`)) {
    await store.remove(item.id)
  }
}

function sizeLabel(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

onMounted(async () => {
  await store.load()
  pollTimer = window.setInterval(() => {
    if (store.hasActiveJobs) void store.load(true)
  }, 3000)
})

onUnmounted(() => {
  if (pollTimer) window.clearInterval(pollTimer)
})
</script>

<template>
  <div class="knowledge-tab">
    <div class="knowledge-intro">
      <strong>个人知识库</strong>
      <p>上传 PDF、Word、TXT 或 Markdown。处理完成后，聊天会自动检索相关内容并显示来源。</p>
    </div>

    <div class="knowledge-controls">
      <label>
        当前会话检索
        <select :value="currentConversation?.retrieval_mode ?? 'auto'" @change="handleRetrievalMode">
          <option value="auto">自动（保持原行为）</option>
          <option value="off">关闭知识库</option>
          <option value="vector">仅向量文本</option>
          <option value="hybrid">向量 + 图谱</option>
        </select>
      </label>
      <label>
        新文档图谱
        <select v-model="graphMode">
          <option value="inherit">跟随系统默认</option>
          <option value="enabled">构建图谱</option>
          <option value="disabled">不构建图谱</option>
        </select>
      </label>
    </div>

    <div class="tab-actions">
      <input ref="input" class="visually-hidden" type="file" accept=".pdf,.docx,.txt,.md,text/plain,application/pdf" @change="handleFile" />
      <button class="btn-primary" :disabled="store.uploading" @click="chooseFile">
        {{ store.uploading ? '上传中…' : '上传文档' }}
      </button>
      <button class="btn-secondary" :disabled="store.loading" @click="store.load()">刷新状态</button>
    </div>

    <p v-if="store.error" class="inline-error">{{ store.error }}</p>
    <div v-if="store.loading && !store.documents.length" class="empty-note">正在读取知识库…</div>
    <div v-else-if="!store.documents.length" class="empty-note">还没有文档，上传一份资料开始构建个人知识库。</div>

    <ul v-else class="document-list">
      <li v-for="item in store.documents" :key="item.id" class="document-card">
        <div class="document-icon" aria-hidden="true">文</div>
        <div class="document-info">
          <strong :title="item.filename">{{ item.filename }}</strong>
          <span>{{ sizeLabel(item.byte_size) }} · {{ new Date(item.created_at).toLocaleString() }}</span>
          <span :class="['document-status', item.status]">{{ documentStatusLabel(item) }}</span>
          <small v-if="item.error_message" class="document-error">{{ item.error_message }}</small>
        </div>
        <div class="document-actions">
          <button v-if="item.status === 'failed' || item.graph_status === 'failed'" class="btn-secondary" @click="store.retry(item.id)">重试</button>
          <button
            v-if="item.status === 'ready' && ['skipped', 'disabled', 'unavailable', 'failed'].includes(item.graph_status)"
            class="btn-secondary"
            @click="store.buildGraph(item.id)"
          >构建图谱</button>
          <button
            v-if="item.status === 'ready' && item.graph_status === 'ready'"
            class="btn-secondary"
            @click="store.buildGraph(item.id, true)"
          >重建图谱</button>
          <button class="btn-danger" :disabled="item.status === 'deleting'" @click="remove(item)">删除</button>
        </div>
      </li>
    </ul>
  </div>
</template>
