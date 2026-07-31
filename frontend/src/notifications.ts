import { readonly, ref } from 'vue'

export type NotificationKind = 'success' | 'error' | 'info'

export interface AppNotification {
  id: number
  kind: NotificationKind
  message: string
}

const items = ref<AppNotification[]>([])
let nextId = 1

export const notifications = readonly(items)

export function notify(message: string, kind: NotificationKind = 'success', duration = 3200): number {
  const id = nextId++
  items.value.push({ id, kind, message })
  if (duration > 0) window.setTimeout(() => dismissNotification(id), duration)
  return id
}

export function dismissNotification(id: number): void {
  items.value = items.value.filter(item => item.id !== id)
}

export function clearNotifications(): void {
  items.value = []
}

export function errorText(reason: unknown, fallback: string): string {
  if (reason && typeof reason === 'object' && 'response' in reason) {
    const response = (reason as { response?: { data?: { detail?: string } } }).response
    if (typeof response?.data?.detail === 'string') return response.data.detail
  }
  return reason instanceof Error ? reason.message : fallback
}
