import { api } from './chat'

export interface ConversationInfo {
  id: number
  title: string
  created_at: string
  updated_at: string
}

export async function getConversations(): Promise<ConversationInfo[]> {
  const response = await api.get<{ conversations: ConversationInfo[] }>('/conversations')
  return response.data.conversations
}

export async function createConversation(): Promise<ConversationInfo> {
  const response = await api.post<ConversationInfo>('/conversations')
  return response.data
}

export async function deleteConversation(id: number): Promise<void> {
  await api.delete(`/conversations/${id}`)
}

export async function renameConversation(id: number, title: string): Promise<ConversationInfo> {
  const response = await api.patch<ConversationInfo>(`/conversations/${id}`, { title })
  return response.data
}
