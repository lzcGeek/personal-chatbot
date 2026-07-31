<script setup lang="ts">
import { onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useConversationStore } from '../stores/conversations'
import { useChatStore } from '../stores/chat'
import { notify } from '../notifications'


const convStore = useConversationStore()
const chatStore = useChatStore()
const { conversations, currentId, loading } = storeToRefs(convStore)

onMounted(async () => {
  await convStore.load()
  if (!convStore.currentId && convStore.conversations.length) {
    convStore.setCurrent(convStore.conversations[0].id)
  }
})

function switchTo(id: string): void {
  if (id === convStore.currentId) return
  convStore.setCurrent(id)
  chatStore.loadInitial()
}

async function handleCreate(): Promise<void> {
  if (!await convStore.create()) {
    notify(convStore.error || '会话创建失败', 'error')
    return
  }
  chatStore.clearMessages()
  chatStore.loadInitial()
  notify('新会话已创建')
}

async function handleDelete(id: string): Promise<void> {
  const conversation = convStore.conversations.find(item => item.id === id)
  if (!window.confirm(`删除会话“${conversation?.title || '未命名会话'}”？其中的聊天记录也会删除，且无法撤销。`)) {
    notify('已取消删除会话', 'info')
    return
  }
  if (!await convStore.remove(id)) {
    notify(convStore.error || '会话删除失败', 'error')
    return
  }
  chatStore.dropConversation(id)
  if (convStore.currentId) {
    chatStore.loadInitial()
  }
  notify('会话已删除')
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
        <small v-if="chatStore.isGeneratingConversation(conv.id)" class="conv-generating">生成中</small>
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
