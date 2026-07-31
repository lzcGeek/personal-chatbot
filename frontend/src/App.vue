<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import { storeToRefs } from 'pinia'

import ChatWindow from './components/ChatWindow.vue'
import LoginView from './components/LoginView.vue'
import ToastHost from './components/ToastHost.vue'
import { useAuthStore } from './stores/auth'


const authStore = useAuthStore()
const { user, initialized } = storeToRefs(authStore)

function handleUnauthorized(): void {
  authStore.clear()
}

onMounted(() => {
  window.addEventListener('auth:unauthorized', handleUnauthorized)
  authStore.initialize()
})

onBeforeUnmount(() => window.removeEventListener('auth:unauthorized', handleUnauthorized))
</script>

<template>
  <div v-if="!initialized" class="app-loading">正在检查登录状态…</div>
  <ChatWindow v-else-if="user" />
  <LoginView v-else />
  <ToastHost />
</template>
