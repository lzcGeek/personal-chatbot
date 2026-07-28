<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import {
  confirmMemory,
  deleteMemory,
  deleteSummary,
  getConversationSummaries,
  getMemories,
  invalidateMemory,
  regenerateSummary,
  restoreMemory,
  type ConversationSummaryInfo,
  type MemoryInfo,
} from '../api/memories'
import { memoryActions, memoryScopeLabel, memoryValidityLabel } from '../memory-options'
import { useConversationStore } from '../stores/conversations'

const conversations = useConversationStore()
const memories = ref<MemoryInfo[]>([])
const summaries = ref<ConversationSummaryInfo[]>([])
const loading = ref(false)
const busyId = ref('')
const error = ref('')
const conversationId = computed(() => conversations.currentId)

async function load(): Promise<void> {
  const id = conversationId.value
  memories.value = []
  summaries.value = []
  error.value = ''
  if (!id) return
  loading.value = true
  try {
    ;[memories.value, summaries.value] = await Promise.all([
      getMemories(id),
      getConversationSummaries(id),
    ])
  } catch (reason: unknown) {
    error.value = reason instanceof Error ? reason.message : '加载记忆失败'
  } finally {
    loading.value = false
  }
}

async function mutateMemory(item: MemoryInfo, action: string): Promise<void> {
  busyId.value = item.id
  error.value = ''
  try {
    if (action === 'confirm') await confirmMemory(item.id)
    if (action === 'invalidate') await invalidateMemory(item.id)
    if (action === 'restore') await restoreMemory(item.id)
    if (action === 'delete') {
      if (!window.confirm('删除这条记忆？原始聊天消息不会被删除。')) return
      await deleteMemory(item.id)
    }
    await load()
  } catch (reason: unknown) {
    error.value = reason instanceof Error ? reason.message : '更新记忆失败'
  } finally {
    busyId.value = ''
  }
}

async function rebuild(summary: ConversationSummaryInfo): Promise<void> {
  const id = conversationId.value
  if (!id) return
  busyId.value = summary.id
  try {
    await regenerateSummary(id, summary.id)
    await load()
  } catch (reason: unknown) {
    error.value = reason instanceof Error ? reason.message : '摘要重建失败'
  } finally {
    busyId.value = ''
  }
}

async function removeSummary(summary: ConversationSummaryInfo): Promise<void> {
  const id = conversationId.value
  if (!id || !window.confirm('删除这个摘要检查点？原始聊天消息仍会保留。')) return
  busyId.value = summary.id
  try {
    await deleteSummary(id, summary.id)
    await load()
  } catch (reason: unknown) {
    error.value = reason instanceof Error ? reason.message : '删除摘要失败'
  } finally {
    busyId.value = ''
  }
}

watch(conversationId, () => void load(), { immediate: true })
</script>

<template>
  <div class="memory-tab">
    <div class="knowledge-intro">
      <strong>当前会话的分层记忆</strong>
      <p>原始聊天消息始终保留。你可以纠正自动提取的事实，或重建覆盖较早消息的滚动摘要。</p>
    </div>
    <div class="tab-actions">
      <button class="btn-secondary" :disabled="loading || !conversationId" @click="load">刷新</button>
    </div>
    <p v-if="error" class="inline-error">{{ error }}</p>
    <div v-if="!conversationId" class="empty-note">请先选择一个会话。</div>
    <div v-else-if="loading" class="empty-note">正在读取记忆…</div>
    <template v-else>
      <h3 class="memory-heading">结构化记忆</h3>
      <div v-if="!memories.length" class="empty-note">这个会话还没有结构化记忆。</div>
      <ul v-else class="memory-list">
        <li v-for="item in memories" :key="item.id" class="memory-card">
          <div class="memory-card-head">
            <span :class="['status-badge', item.validity]">{{ memoryValidityLabel(item.validity) }}</span>
            <span>{{ memoryScopeLabel(item.scope) }}</span>
            <span v-if="item.character_id">角色 {{ item.character_id.slice(0, 8) }}</span>
          </div>
          <p>{{ item.content }}</p>
          <small>来源消息：{{ item.source_message_ids.length ? item.source_message_ids.join(', ') : '未知' }}</small>
          <small v-if="item.conflict_reason">冲突说明：{{ item.conflict_reason }}</small>
          <div class="memory-actions">
            <button
              v-for="action in memoryActions(item.validity, item.superseded_by_id)"
              :key="action"
              :class="action === 'delete' ? 'btn-danger' : 'btn-secondary'"
              :disabled="busyId === item.id"
              @click="mutateMemory(item, action)"
            >{{ { confirm: '确认', invalidate: '标记失效', restore: '恢复', delete: '删除' }[action] }}</button>
          </div>
        </li>
      </ul>

      <h3 class="memory-heading">滚动摘要</h3>
      <div v-if="!summaries.length" class="empty-note">尚未达到摘要压缩阈值。</div>
      <ul v-else class="memory-list">
        <li v-for="item in summaries" :key="item.id" class="memory-card">
          <div class="memory-card-head">
            <span :class="['status-badge', item.status]">{{ item.status === 'complete' ? '可用' : '失败' }}</span>
            <span>消息 {{ item.start_message_id }}–{{ item.end_message_id }}</span>
            <span>版本 {{ item.version }}</span>
          </div>
          <p v-if="item.content">{{ item.content }}</p>
          <small v-if="item.error_message" class="document-error">{{ item.error_message }}</small>
          <div class="memory-actions">
            <button class="btn-secondary" :disabled="busyId === item.id" @click="rebuild(item)">重新生成</button>
            <button class="btn-danger" :disabled="busyId === item.id" @click="removeSummary(item)">删除</button>
          </div>
        </li>
      </ul>
    </template>
  </div>
</template>
