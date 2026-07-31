import { ref } from 'vue'
import { defineStore } from 'pinia'
import {
  createConversation,
  deleteConversation,
  getConversations,
  updateConversationSettings,
  type ConversationInfo,
  type RetrievalMode,
} from '../api/conversations'


export const useConversationStore = defineStore('conversations', () => {
  const conversations = ref<ConversationInfo[]>([])
  const currentId = ref<string | null>(null)
  const loading = ref(false)
  const error = ref('')
  let loadPromise: Promise<void> | null = null

  async function load(): Promise<void> {
    if (loadPromise) return loadPromise
    loading.value = true
    error.value = ''
    loadPromise = (async () => {
      try {
        conversations.value = await getConversations()
        const currentExists = conversations.value.some(conv => conv.id === currentId.value)
        if (!currentExists) {
          currentId.value = conversations.value[0]?.id ?? null
        }
      } catch (reason: unknown) {
        error.value = reason instanceof Error ? reason.message : '加载失败'
      } finally {
        loading.value = false
        loadPromise = null
      }
    })()
    return loadPromise
  }

  function setCurrent(id: string | null): void {
    currentId.value = id
  }

  async function create(): Promise<boolean> {
    loading.value = true
    try {
      const conv = await createConversation()
      conversations.value.unshift(conv)
      currentId.value = conv.id
      error.value = ''
      return true
    } catch (reason: unknown) {
      error.value = reason instanceof Error ? reason.message : '创建失败'
      return false
    } finally {
      loading.value = false
    }
  }

  async function remove(id: string): Promise<boolean> {
    loading.value = true
    try {
      await deleteConversation(id)
      conversations.value = conversations.value.filter(c => c.id !== id)
      if (currentId.value === id) {
        currentId.value = conversations.value[0]?.id ?? null
      }
      if (!conversations.value.length) {
        await load()
        if (conversations.value.length) {
          currentId.value = conversations.value[0].id
        }
      }
      error.value = ''
      return true
    } catch (reason: unknown) {
      error.value = reason instanceof Error ? reason.message : '删除失败'
      return false
    } finally {
      loading.value = false
    }
  }

  async function setRetrievalMode(id: string, mode: RetrievalMode): Promise<void> {
    try {
      const updated = await updateConversationSettings(id, { retrieval_mode: mode })
      const index = conversations.value.findIndex(conversation => conversation.id === id)
      if (index !== -1) conversations.value[index] = updated
      error.value = ''
    } catch (reason: unknown) {
      error.value = reason instanceof Error ? reason.message : '更新知识检索模式失败'
      throw reason
    }
  }

  async function updateSettings(
    id: string,
    settings: Parameters<typeof updateConversationSettings>[1],
  ): Promise<void> {
    const updated = await updateConversationSettings(id, settings)
    const index = conversations.value.findIndex(conversation => conversation.id === id)
    if (index !== -1) conversations.value[index] = updated
  }

  return {
    conversations,
    currentId,
    loading,
    error,
    load,
    setCurrent,
    create,
    remove,
    setRetrievalMode,
    updateSettings,
  }
})
