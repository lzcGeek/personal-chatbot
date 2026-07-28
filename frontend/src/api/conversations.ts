import { api } from './chat'

export interface ConversationInfo {
  id: string
  title: string
  retrieval_mode: RetrievalMode
  mode: ConversationMode
  routing_strategy: RoutingStrategy
  scene_description: string
  max_speakers_per_turn: number
  max_group_generations: number
  created_at: string
  updated_at: string
}

export type RetrievalMode = 'auto' | 'off' | 'vector' | 'hybrid'
export type ConversationMode = 'assistant' | 'single_character' | 'group'
export type RoutingStrategy = 'manual' | 'mention' | 'round_robin' | 'auto'

export interface ConversationMember {
  id: string
  character_id: string
  name: string
  position: number
  enabled: boolean
  overrides: Record<string, unknown>
}

export async function getConversations(): Promise<ConversationInfo[]> {
  const response = await api.get<{ conversations: ConversationInfo[] }>('/conversations')
  return response.data.conversations
}

export async function createConversation(): Promise<ConversationInfo> {
  const response = await api.post<ConversationInfo>('/conversations')
  return response.data
}

export async function deleteConversation(id: string): Promise<void> {
  await api.delete(`/conversations/${id}`)
}

export async function renameConversation(id: string, title: string): Promise<ConversationInfo> {
  const response = await api.patch<ConversationInfo>(`/conversations/${id}`, { title })
  return response.data
}

export async function updateConversationSettings(
  id: string,
  settings: Partial<Pick<ConversationInfo, 'retrieval_mode' | 'mode' | 'routing_strategy' | 'scene_description' | 'max_speakers_per_turn' | 'max_group_generations'>>,
): Promise<ConversationInfo> {
  const response = await api.patch<ConversationInfo>(`/conversations/${id}/settings`, settings)
  return response.data
}

export async function getConversationMembers(id: string): Promise<ConversationMember[]> {
  const response = await api.get<ConversationMember[]>(`/conversations/${id}/members`)
  return response.data
}

export async function replaceConversationMembers(
  id: string,
  members: Array<Omit<ConversationMember, 'id' | 'name'>>,
): Promise<ConversationMember[]> {
  const response = await api.put<ConversationMember[]>(`/conversations/${id}/members`, { members })
  return response.data
}
