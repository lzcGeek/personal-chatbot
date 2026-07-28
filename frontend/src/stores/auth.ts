import { ref } from 'vue'
import { defineStore } from 'pinia'

import {
  getCurrentUser,
  login as loginRequest,
  logout as logoutRequest,
  register as registerRequest,
  type AuthUser,
} from '../api/auth'


export const useAuthStore = defineStore('auth', () => {
  const user = ref<AuthUser | null>(null)
  const initialized = ref(false)
  const loading = ref(false)
  const error = ref('')

  async function initialize(): Promise<void> {
    try {
      user.value = await getCurrentUser()
    } catch {
      user.value = null
    } finally {
      initialized.value = true
    }
  }

  async function login(username: string, password: string): Promise<void> {
    loading.value = true
    error.value = ''
    try {
      user.value = await loginRequest(username, password)
    } catch (reason) {
      error.value = apiError(reason)
      throw reason
    } finally {
      loading.value = false
    }
  }

  async function register(username: string, password: string): Promise<void> {
    loading.value = true
    error.value = ''
    try {
      await registerRequest(username, password)
      user.value = await loginRequest(username, password)
    } catch (reason) {
      error.value = apiError(reason)
      throw reason
    } finally {
      loading.value = false
    }
  }

  async function logout(): Promise<void> {
    try {
      await logoutRequest()
    } finally {
      clear()
    }
  }

  function clear(): void {
    user.value = null
  }

  return { user, initialized, loading, error, initialize, login, register, logout, clear }
})

function apiError(reason: unknown): string {
  if (reason && typeof reason === 'object' && 'response' in reason) {
    const response = (reason as { response?: { data?: { detail?: string } } }).response
    if (response?.data?.detail) return response.data.detail
  }
  return reason instanceof Error ? reason.message : '请求失败'
}
