<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

import type { DocumentInfo, GraphMode } from '../api/documents'
import type { RetrievalMode } from '../api/conversations'
import { documentStatusLabel } from '../document-status'
import { useConversationStore } from '../stores/conversations'
import { useDocumentStore } from '../stores/documents'
import { errorText, notify } from '../notifications'


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
  if (file) {
    const succeeded = await store.upload(file, graphMode.value)
    notify(succeeded ? `文档“${file.name}”已上传，正在后台处理` : (store.error || '文档上传失败'), succeeded ? 'success' : 'error')
  }
  target.value = ''
}

async function handleRetrievalMode(event: Event): Promise<void> {
  const id = conversationStore.currentId
  if (!id) return
  const mode = (event.target as HTMLSelectElement).value as RetrievalMode
  try {
    await conversationStore.setRetrievalMode(id, mode)
    notify('当前会话的知识检索模式已保存')
  } catch (reason: unknown) {
    notify(errorText(reason, '知识检索模式保存失败'), 'error')
  }
}

async function remove(item: DocumentInfo): Promise<void> {
  if (window.confirm(`删除“${item.filename}”及其全部索引和图谱知识？`)) {
    const succeeded = await store.remove(item.id)
    notify(succeeded ? `文档“${item.filename}”已进入删除流程` : (store.error || '文档删除失败'), succeeded ? 'success' : 'error')
  } else {
    notify('已取消删除文档', 'info')
  }
}

async function refresh(): Promise<void> {
  await store.load()
  notify(store.error || '知识库状态已刷新', store.error ? 'error' : 'success')
}

async function retry(item: DocumentInfo): Promise<void> {
  const succeeded = await store.retry(item.id)
  notify(succeeded ? `已重新处理“${item.filename}”` : (store.error || '重试失败'), succeeded ? 'success' : 'error')
}

async function buildGraph(item: DocumentInfo, rebuild = false): Promise<void> {
  if (rebuild && !window.confirm(`重新构建“${item.filename}”的图谱？现有图谱数据将被替换。`)) {
    notify('已取消重建图谱', 'info')
    return
  }
  const succeeded = await store.buildGraph(item.id, rebuild)
  notify(
    succeeded ? `${rebuild ? '重建' : '构建'}图谱任务已开始` : (store.error || `${rebuild ? '重建' : '构建'}图谱失败`),
    succeeded ? 'success' : 'error',
  )
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
      <button class="btn-secondary" :disabled="store.loading" @click="refresh">刷新状态</button>
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
          <button v-if="item.status === 'failed' || item.graph_status === 'failed'" class="btn-secondary" @click="retry(item)">重试</button>
          <button
            v-if="item.status === 'ready' && ['skipped', 'disabled', 'unavailable', 'failed'].includes(item.graph_status)"
            class="btn-secondary"
            @click="buildGraph(item)"
          >构建图谱</button>
          <button
            v-if="item.status === 'ready' && item.graph_status === 'ready'"
            class="btn-secondary"
            @click="buildGraph(item, true)"
          >重建图谱</button>
          <button class="btn-danger" :disabled="item.status === 'deleting'" @click="remove(item)">删除</button>
        </div>
      </li>
    </ul>
  </div>
</template>
