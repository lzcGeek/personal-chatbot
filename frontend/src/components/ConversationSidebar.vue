<script setup lang="ts">
import { onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useConversationStore } from '../stores/conversations'
import { useChatStore } from '../stores/chat'


const convStore = useConversationStore()
const chatStore = useChatStore()
const { conversations, currentId, loading } = storeToRefs(convStore)

onMounted(async () => {
  await convStore.load()
  if (!convStore.currentId && convStore.conversations.length) {
    convStore.setCurrent(convStore.conversations[0].id)
  }
})

function switchTo(id: number): void {
  chatStore.clearMessages()
  convStore.setCurrent(id)
  chatStore.loadInitial()
}

async function handleCreate(): Promise<void> {
  await convStore.create()
  chatStore.clearMessages()
  chatStore.loadInitial()
}

async function handleDelete(id: number): Promise<void> {
  await convStore.remove(id)
  chatStore.clearMessages()
  if (convStore.currentId) {
    chatStore.loadInitial()
  }
}
</script>

<template>
  <aside class="conv-sidebar">
    <header class="conv-header">
      <span>会话</span>
      <button class="btn-new-conv" title="新建会话" @click="handleCreate">+</button>
    </header>
    <ul class="conv-list">
      <li
        v-for="conv in conversations"
        :key="conv.id"
        :class="{ active: conv.id === currentId }"
        class="conv-item"
        @click="switchTo(conv.id)"
      >
        <span class="conv-title">{{ conv.title }}</span>
        <button
          class="conv-delete"
          title="删除会话"
          :disabled="loading"
          @click.stop="handleDelete(conv.id)"
        >
          &times;
        </button>
      </li>
      <li v-if="!conversations.length && !loading" class="conv-empty">暂无会话</li>
    </ul>
  </aside>
</template>
