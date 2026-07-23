export interface ChatMessage {
  id: number | string
  role: 'user' | 'assistant'
  content: string
  status: 'complete' | 'streaming' | 'interrupted' | 'error'
  created_at: string
  triggeredSkill?: string
}

export interface HistoryResponse {
  messages: ChatMessage[]
  has_more: boolean
  next_before_id: number | null
}

export interface StreamEvent {
  event: 'token' | 'done' | 'error'
  data: Record<string, unknown>
}
