import axios from 'axios'

import type { ChatMessage, HistoryResponse, StreamEvent } from '../types/chat'


export const api = axios.create({ baseURL: '/api' })

export async function getHistory(beforeId?: number, conversationId?: number): Promise<HistoryResponse> {
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
  conversationId?: number,
): Promise<void> {
  const response = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ message, conversation_id: conversationId ?? null }),
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
