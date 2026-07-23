import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'

import { getHistory, isChatMessage, streamChat } from '../api/chat'
import type { ChatMessage } from '../types/chat'
import { useConversationStore } from './conversations'


export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>([])
  const loadingHistory = ref(false)
  const generating = ref(false)
  const hasMore = ref(true)
  const error = ref('')
  let nextBeforeId: number | undefined

  const empty = computed(() => messages.value.length === 0)

  async function loadInitial(): Promise<void> {
    if (messages.value.length) return
    await loadOlder()
  }

  async function loadOlder(): Promise<void> {
    if (loadingHistory.value || !hasMore.value) return
    loadingHistory.value = true
    try {
      const convStore = useConversationStore()
      const history = await getHistory(nextBeforeId, convStore.currentId ?? undefined)
      messages.value = [...history.messages, ...messages.value]
      hasMore.value = history.has_more
      nextBeforeId = history.next_before_id ?? undefined
    } catch (reason) {
      error.value = errorMessage(reason)
    } finally {
      loadingHistory.value = false
    }
  }

  async function send(content: string): Promise<void> {
    const normalized = content.trim()
    if (!normalized || generating.value) return
    error.value = ''
    generating.value = true

    const now = new Date().toISOString()
    let triggeredSkill: string | undefined
    if (normalized.startsWith('/')) {
      const space = normalized.indexOf(' ')
      triggeredSkill = normalized.slice(1, space === -1 ? undefined : space)
    }
    messages.value.push({
      id: `user-${Date.now()}`,
      role: 'user',
      content: normalized,
      status: 'complete',
      created_at: now,
      triggeredSkill,
    })
    const assistant: ChatMessage = {
      id: `assistant-${Date.now()}`,
      role: 'assistant',
      content: '',
      status: 'streaming',
      created_at: now,
    }
    messages.value.push(assistant)
    const activeAssistant = messages.value[messages.value.length - 1]

    let completed = false
    try {
      const convStore = useConversationStore()
      await streamChat(
        normalized,
        ({ event, data }) => {
        if (event === 'token' && typeof data.content === 'string') {
          activeAssistant.content += data.content
        } else if (event === 'done' && isChatMessage(data.message)) {
          Object.assign(activeAssistant, data.message, { status: 'complete' })
          completed = true
        } else if (event === 'error') {
          throw new Error(typeof data.message === 'string' ? data.message : '生成失败')
        }
      },
      undefined,
      convStore.currentId ?? undefined,
      )
      if (!completed) throw new Error('响应流意外结束')
    } catch (reason) {
      activeAssistant.status = activeAssistant.content ? 'interrupted' : 'error'
      error.value = errorMessage(reason)
    } finally {
      generating.value = false
    }
  }

  function clearMessages(): void {
    messages.value = []
    hasMore.value = true
    nextBeforeId = undefined
  }

  function clearError(): void {
    error.value = ''
  }

  return {
    messages,
    loadingHistory,
    generating,
    hasMore,
    error,
    empty,
    loadInitial,
    loadOlder,
    send,
    clearMessages,
    clearError,
  }
})

function errorMessage(reason: unknown): string {
  return reason instanceof Error ? reason.message : '发生未知错误'
}
