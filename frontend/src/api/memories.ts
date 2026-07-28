import { api } from './chat'
import type { MemoryValidity } from '../memory-options'

export interface MemoryInfo {
  id: string
  conversation_id: string
  character_id: string | null
  content: string
  source_message_ids: number[]
  metadata: Record<string, unknown>
  importance: number
  scope: string
  validity: MemoryValidity
  superseded_by_id: string | null
  conflict_reason: string | null
  effective_from: string | null
  effective_to: string | null
  embedding_status: string
  created_at: string
}

export interface ConversationSummaryInfo {
  id: string
  conversation_id: string
  start_message_id: number
  end_message_id: number
  version: number
  status: string
  content: string
  error_message: string | null
  created_at: string
  updated_at: string
}

export async function getMemories(conversationId?: string): Promise<MemoryInfo[]> {
  const response = await api.get<{ memories: MemoryInfo[] }>('/memories', {
    params: conversationId ? { conversation_id: conversationId } : undefined,
  })
  return response.data.memories
}

export async function invalidateMemory(id: string): Promise<void> {
  await api.post(`/memories/${id}/invalidate`)
}

export async function restoreMemory(id: string): Promise<void> {
  await api.post(`/memories/${id}/restore`)
}

export async function confirmMemory(id: string): Promise<void> {
  await api.post(`/memories/${id}/confirm`, {})
}

export async function deleteMemory(id: string): Promise<void> {
  await api.delete(`/memories/${id}`)
}

export async function getConversationSummaries(conversationId: string): Promise<ConversationSummaryInfo[]> {
  const response = await api.get<{ summaries: ConversationSummaryInfo[] }>(
    `/conversations/${conversationId}/summaries`,
  )
  return response.data.summaries
}

export async function regenerateSummary(conversationId: string, summaryId: string): Promise<void> {
  await api.post(`/conversations/${conversationId}/summaries/${summaryId}/regenerate`)
}

export async function deleteSummary(conversationId: string, summaryId: string): Promise<void> {
  await api.delete(`/conversations/${conversationId}/summaries/${summaryId}`)
}
