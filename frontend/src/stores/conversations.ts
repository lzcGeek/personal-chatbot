import { ref } from 'vue'
import { defineStore } from 'pinia'
import { createConversation, deleteConversation, getConversations, type ConversationInfo } from '../api/conversations'


export const useConversationStore = defineStore('conversations', () => {
  const conversations = ref<ConversationInfo[]>([])
  const currentId = ref<number | null>(null)
  const loading = ref(false)
  const error = ref('')

  async function load(): Promise<void> {
    loading.value = true
    try {
      conversations.value = await getConversations()
    } catch (reason: unknown) {
      error.value = reason instanceof Error ? reason.message : '加载失败'
    } finally {
      loading.value = false
    }
  }

  function setCurrent(id: number | null): void {
    currentId.value = id
  }

  async function create(): Promise<void> {
    loading.value = true
    try {
      const conv = await createConversation()
      conversations.value.unshift(conv)
      currentId.value = conv.id
    } catch (reason: unknown) {
      error.value = reason instanceof Error ? reason.message : '创建失败'
    } finally {
      loading.value = false
    }
  }

  async function remove(id: number): Promise<void> {
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
    } catch (reason: unknown) {
      error.value = reason instanceof Error ? reason.message : '删除失败'
    } finally {
      loading.value = false
    }
  }

  return { conversations, currentId, loading, error, load, setCurrent, create, remove }
})
