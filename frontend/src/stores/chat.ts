import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { getHistory, isChatMessage, streamChat } from '../api/chat'
import { canRetryMessage, createChatRetryRequest } from '../chat-options'
import {
  createConversationChatState,
  type ConversationChatState,
} from '../conversation-chat-state'
import type { ChatMessage, ChatRetryRequest } from '../types/chat'
import { useConversationStore } from './conversations'


export const useChatStore = defineStore('chat', () => {
  const convStore = useConversationStore()
  const states = ref<Record<string, ConversationChatState>>({})
  const emptyState = createConversationChatState()

  function stateFor(conversationId: string): ConversationChatState {
    return states.value[conversationId]
      ?? (states.value[conversationId] = createConversationChatState())
  }

  const currentState = computed(() => (
    convStore.currentId ? stateFor(convStore.currentId) : emptyState
  ))
  const messages = computed(() => currentState.value.messages)
  const loadingHistory = computed(() => currentState.value.loadingHistory)
  const generating = computed(() => currentState.value.generating)
  const hasMore = computed(() => currentState.value.hasMore)
  const error = computed(() => currentState.value.error)
  const activeSpeaker = computed(() => currentState.value.activeSpeaker)

  const empty = computed(() => messages.value.length === 0)

  async function loadInitial(): Promise<void> {
    await convStore.load()
    if (!convStore.currentId) {
      emptyState.hasMore = false
      return
    }
    const state = stateFor(convStore.currentId)
    if (state.historyLoaded) return
    await loadOlderFor(convStore.currentId)
  }

  async function loadOlder(): Promise<void> {
    if (!convStore.currentId) return
    await loadOlderFor(convStore.currentId)
  }

  async function loadOlderFor(conversationId: string): Promise<void> {
    const state = stateFor(conversationId)
    if (state.loadingHistory || !state.hasMore) return
    state.loadingHistory = true
    try {
      const history = await getHistory(state.nextBeforeId, conversationId)
      const persistedIds = new Set(
        state.messages
          .filter(message => typeof message.id === 'number')
          .map(message => message.id),
      )
      state.messages.unshift(
        ...history.messages.filter(message => !persistedIds.has(message.id)),
      )
      state.hasMore = history.has_more
      state.nextBeforeId = history.next_before_id ?? undefined
      state.historyLoaded = true
    } catch (reason) {
      state.error = errorMessage(reason)
    } finally {
      state.loadingHistory = false
    }
  }

  async function send(
    content: string,
    allowNetwork = false,
    targetCharacterId?: string,
    maxSpeakers?: number,
  ): Promise<void> {
    await sendRequest(
      createChatRetryRequest(content, allowNetwork, () => crypto.randomUUID(), targetCharacterId, maxSpeakers),
      true,
    )
  }

  async function sendRequest(request: ChatRetryRequest, appendUser: boolean): Promise<void> {
    const content = request.content
    const normalized = content.trim()
    if (!normalized) return

    if (!convStore.currentId) await convStore.load()
    if (!convStore.currentId) {
      emptyState.error = '请先创建一个会话'
      return
    }
    const conversationId = convStore.currentId
    const state = stateFor(conversationId)
    if (state.generating) return
    state.error = ''

    state.generating = true

    const now = new Date().toISOString()
    let triggeredSkill: string | undefined
    if (normalized.startsWith('/')) {
      const space = normalized.indexOf(' ')
      triggeredSkill = normalized.slice(1, space === -1 ? undefined : space)
    }
    if (appendUser) {
      state.messages.push({
        id: `user-${Date.now()}`,
        role: 'user',
        content: normalized,
        status: 'complete',
        created_at: now,
        triggeredSkill,
        allow_network: request.allowNetwork,
        client_request_id: request.clientRequestId,
      })
    }
    const assistant: ChatMessage = {
      id: `assistant-${Date.now()}`,
      role: 'assistant',
      content: '',
      status: 'streaming',
      created_at: now,
      retryRequest: request,
    }
    state.messages.push(assistant)
    let activeAssistant = state.messages[state.messages.length - 1]

    function appendAssistant(): ChatMessage {
      const next: ChatMessage = {
        id: `assistant-${Date.now()}-${state.messages.length}`,
        role: 'assistant',
        content: '',
        status: 'streaming',
        created_at: new Date().toISOString(),
        retryRequest: request,
      }
      state.messages.push(next)
      return next
    }

    let completed = false
    try {
      await streamChat(
        normalized,
        ({ event, data }) => {
        if (event === 'routing') {
          // Routing metadata is intentionally machine-readable; the active speaker is shown separately.
        } else if (event === 'speaker_start') {
          if (activeAssistant.status === 'complete') activeAssistant = appendAssistant()
          if (typeof data.character_id === 'string') activeAssistant.character_id = data.character_id
          if (typeof data.speaker_name === 'string') {
            activeAssistant.speaker_name = data.speaker_name
            state.activeSpeaker = data.speaker_name
          }
        } else if (event === 'token' && typeof data.content === 'string') {
          if (typeof data.character_id === 'string') activeAssistant.character_id = data.character_id
          if (typeof data.speaker_name === 'string') activeAssistant.speaker_name = data.speaker_name
          activeAssistant.content += data.content
        } else if (event === 'speaker_done' && isChatMessage(data.message)) {
          Object.assign(activeAssistant, data.message, { status: 'complete', retryRequest: undefined })
          state.activeSpeaker = ''
        } else if (event === 'done' && isChatMessage(data.message)) {
          const groupMessages = Array.isArray(data.messages)
            ? data.messages.filter(isChatMessage)
            : []
          if (groupMessages.length) {
            if (typeof activeAssistant.id === 'string' && !activeAssistant.content) {
              const emptyIndex = state.messages.indexOf(activeAssistant)
              if (emptyIndex !== -1) state.messages.splice(emptyIndex, 1)
            }
            for (const groupMessage of groupMessages) {
              const existing = state.messages.find(item => item.id === groupMessage.id)
              if (existing) Object.assign(existing, groupMessage, { status: 'complete', retryRequest: undefined })
              else state.messages.push(groupMessage)
            }
          } else {
            Object.assign(activeAssistant, data.message, {
              status: 'complete',
              degraded: data.degraded === true,
              degradations: Array.isArray(data.degradations)
                ? data.degradations.filter((item): item is string => typeof item === 'string')
                : [],
              retryRequest: undefined,
            })
          }
          state.activeSpeaker = ''
          completed = true
        } else if (event === 'error') {
          activeAssistant.recoverable = data.recoverable === true
          activeAssistant.errorCode = typeof data.code === 'string' ? data.code : 'generation_failed'
          throw new Error(typeof data.message === 'string' ? data.message : '生成失败')
        }
      },
      undefined,
      conversationId,
      request.allowNetwork,
      request.clientRequestId,
      request.targetCharacterId,
      request.maxSpeakers,
      )
      if (!completed) throw new Error('响应流意外结束')
    } catch (reason) {
      activeAssistant.status = activeAssistant.content ? 'interrupted' : 'error'
      state.error = errorMessage(reason)
    } finally {
      state.generating = false
      state.activeSpeaker = ''
    }
  }

  async function retry(message: ChatMessage): Promise<void> {
    if (!convStore.currentId) return
    const state = stateFor(convStore.currentId)
    if (!canRetryMessage(message) || !message.retryRequest || state.generating) return
    const index = state.messages.findIndex(item => item.id === message.id)
    if (index !== -1) state.messages.splice(index, 1)
    await sendRequest(message.retryRequest, false)
  }

  function clearMessages(): void {
    if (!convStore.currentId) return
    states.value[convStore.currentId] = createConversationChatState()
  }

  function dropConversation(conversationId: string): void {
    delete states.value[conversationId]
  }

  function isGeneratingConversation(conversationId: string): boolean {
    return states.value[conversationId]?.generating === true
  }

  function clearError(): void {
    currentState.value.error = ''
  }

  return {
    messages,
    loadingHistory,
    generating,
    hasMore,
    error,
    activeSpeaker,
    empty,
    loadInitial,
    loadOlder,
    send,
    retry,
    clearMessages,
    dropConversation,
    isGeneratingConversation,
    clearError,
  }
})

function errorMessage(reason: unknown): string {
  if (reason && typeof reason === 'object' && 'response' in reason) {
    const response = (reason as {
      response?: { data?: { detail?: string | Array<{ loc?: unknown[]; msg?: string }> } }
    }).response
    const detail = response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return detail
        .map(item => `${item.loc?.at(-1) ?? '请求参数'}: ${item.msg ?? '校验失败'}`)
        .join('；')
    }
  }
  return reason instanceof Error ? reason.message : '发生未知错误'
}
