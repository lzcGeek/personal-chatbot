<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'

import { useChatStore } from '../stores/chat'
import ChatInput from './ChatInput.vue'
import ConversationSidebar from './ConversationSidebar.vue'
import MessageBubble from './MessageBubble.vue'
import SettingsPanel from './SettingsPanel.vue'


const store = useChatStore()
const { messages, loadingHistory, generating, hasMore, error, empty } = storeToRefs(store)
const scroller = ref<HTMLElement>()
const showSettings = ref(false)
const sidebarCollapsed = ref(false)

onMounted(async () => {
  await store.loadInitial()
  await nextTick()
  scrollToBottom()
})

watch(
  () => {
    const last = messages.value.at(-1)
    return last ? `${last.id}:${last.content.length}` : ''
  },
  async () => {
    await nextTick()
    scrollToBottom()
  },
)

async function onScroll(): Promise<void> {
  const element = scroller.value
  if (!element || element.scrollTop > 80 || loadingHistory.value || !hasMore.value) return
  const previousHeight = element.scrollHeight
  await store.loadOlder()
  await nextTick()
  element.scrollTop = element.scrollHeight - previousHeight
}

function scrollToBottom(): void {
  const element = scroller.value
  if (element) element.scrollTop = element.scrollHeight
}
</script>

<template>
  <main class="chat-shell" :class="{ 'sidebar-collapsed': sidebarCollapsed }">
    <ConversationSidebar />
    <button
      class="sidebar-collapse-btn"
      :title="sidebarCollapsed ? '展开侧栏' : '收起侧栏'"
      @click="sidebarCollapsed = !sidebarCollapsed"
    >
      {{ sidebarCollapsed ? '▶' : '◀' }}
    </button>
    <div class="chat-main-area">
    <header class="chat-header">
      <div>
        <p class="eyebrow">MEMORY · MCP · SKILLS</p>
        <h1>智能聊天助手</h1>
      </div>
      <span class="status-dot"><i /> 本地会话</span>
      <button class="settings-toggle" aria-label="打开设置" @click="showSettings = !showSettings">⚙</button>
    </header>

    <section ref="scroller" class="messages" aria-live="polite" @scroll="onScroll">
      <div v-if="loadingHistory" class="history-state">正在加载历史消息…</div>
      <button v-else-if="hasMore && !empty" class="history-button" @click="store.loadOlder()">
        加载更早消息
      </button>
      <div v-if="empty && !loadingHistory" class="empty-state">
        <div class="empty-mark">AI</div>
        <h2>从一个问题开始</h2>
        <p>对话会保存在本机，并在后续交流中检索相关长期记忆。</p>
      </div>
      <MessageBubble v-for="message in messages" :key="message.id" :message="message" />
    </section>

    <div v-if="error" class="error-toast" role="alert">
      <span>{{ error }}</span>
      <button aria-label="关闭错误提示" @click="store.clearError()">关闭</button>
    </div>

    <footer class="composer">
      <ChatInput :disabled="generating" @send="store.send" />
      <p>AI 可能会出错，请核验重要信息。</p>
    </footer>
    </div>
    <SettingsPanel v-if="showSettings" @close="showSettings = false" />
  </main>
</template>
