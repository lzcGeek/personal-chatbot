<script setup lang="ts">
import { ref } from 'vue'
import { storeToRefs } from 'pinia'

import { useAuthStore } from '../stores/auth'


const authStore = useAuthStore()
const { loading, error } = storeToRefs(authStore)
const username = ref('')
const password = ref('')
const registering = ref(false)

async function submit(): Promise<void> {
  if (registering.value) {
    await authStore.register(username.value, password.value).catch(() => undefined)
  } else {
    await authStore.login(username.value, password.value).catch(() => undefined)
  }
}
</script>

<template>
  <main class="auth-page">
    <form class="auth-card" @submit.prevent="submit">
      <div class="auth-brand">Memory Agent</div>
      <h1>{{ registering ? '创建账号' : '登录' }}</h1>
      <p>登录后，你的会话、记忆和 MCP 服务将与其他用户隔离。</p>
      <label>
        用户名
        <input v-model.trim="username" autocomplete="username" minlength="3" maxlength="128" placeholder="示例：player01（至少 3 个字符）" required />
      </label>
      <label>
        密码
        <input
          v-model="password"
          :autocomplete="registering ? 'new-password' : 'current-password'"
          type="password"
          minlength="8"
          maxlength="1024"
          placeholder="请输入密码（至少 8 个字符）"
          required
        />
      </label>
      <p v-if="error" class="auth-error">{{ error }}</p>
      <button class="auth-submit" type="submit" :disabled="loading">
        {{ loading ? '请稍候…' : registering ? '注册并登录' : '登录' }}
      </button>
      <button class="auth-switch" type="button" @click="registering = !registering">
        {{ registering ? '已有账号？返回登录' : '没有账号？创建一个' }}
      </button>
    </form>
  </main>
</template>
