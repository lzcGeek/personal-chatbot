import axios from 'axios'

import type { ChatMessage, HistoryResponse, StreamEvent } from '../types/chat'


export const api = axios.create({ baseURL: '/api', withCredentials: true })

api.interceptors.request.use((config) => {
  const method = (config.method || 'get').toLowerCase()
  if (!['get', 'head', 'options'].includes(method)) {
    const csrf = readCookie('newagent_csrf')
    if (csrf) config.headers.set('X-CSRF-Token', csrf)
  }
  return config
})

api.interceptors.response.use(
  response => response,
  (error) => {
    if (error?.response?.status === 401) {
      window.dispatchEvent(new Event('auth:unauthorized'))
    }
    return Promise.reject(error)
  },
)

export async function getHistory(beforeId?: number, conversationId?: string): Promise<HistoryResponse> {
  const params: Record<string, string> = { limit: '30' }
  if (beforeId) params.before_id = String(beforeId)
  if (conversationId) params.conversation_id = String(conversationId)
  const response = await api.get<HistoryResponse>('/chat/history', { params })
  return response.data
}

export async function streamChat(
  message: string,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
  conversationId?: string,
  allowNetwork = false,
  clientRequestId?: string,
  targetCharacterId?: string,
  maxSpeakers?: number,
): Promise<void> {
  const csrf = readCookie('newagent_csrf')
  const response = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...(csrf ? { 'X-CSRF-Token': csrf } : {}),
    },
    credentials: 'same-origin',
    body: JSON.stringify({
      message,
      conversation_id: conversationId ?? null,
      allow_network: allowNetwork,
      client_request_id: clientRequestId ?? null,
      target_character_id: targetCharacterId ?? null,
      max_speakers: maxSpeakers ?? null,
    }),
    signal,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail || `请求失败 (${response.status})`)
  }
  if (!response.body) throw new Error('浏览器未提供响应流')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, '\n')
    let boundary = buffer.indexOf('\n\n')
    while (boundary !== -1) {
      const block = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      const parsed = parseSseBlock(block)
      if (parsed) onEvent(parsed)
      boundary = buffer.indexOf('\n\n')
    }
    if (done) break
  }
  if (buffer.trim()) {
    const parsed = parseSseBlock(buffer)
    if (parsed) onEvent(parsed)
  }
}

function readCookie(name: string): string | null {
  const prefix = `${encodeURIComponent(name)}=`
  const item = document.cookie.split('; ').find(value => value.startsWith(prefix))
  return item ? decodeURIComponent(item.slice(prefix.length)) : null
}

function parseSseBlock(block: string): StreamEvent | null {
  let event: StreamEvent['event'] | null = null
  const data: string[] = []
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim() as StreamEvent['event']
    if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
  }
  if (!event || data.length === 0) return null
  return { event, data: JSON.parse(data.join('\n')) as Record<string, unknown> }
}

export function isChatMessage(value: unknown): value is ChatMessage {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<ChatMessage>
  return (
    (candidate.role === 'user' || candidate.role === 'assistant') &&
    typeof candidate.content === 'string' &&
    typeof candidate.created_at === 'string'
  )
}
