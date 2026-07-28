export interface DocumentCitation {
  index: number
  document_id: string
  chunk_id: string
  filename: string
  page_number: number | null
  section: string | null
  score: number
  excerpt: string
}

export interface ChatMessage {
  id: number | string
  role: 'user' | 'assistant'
  content: string
  status: 'complete' | 'streaming' | 'interrupted' | 'error'
  created_at: string
  triggeredSkill?: string
  citations?: DocumentCitation[]
  allow_network?: boolean
  client_request_id?: string | null
  character_id?: string
  speaker_name?: string
  speaker_plan_id?: string
  speaker_plan_index?: number
  degraded?: boolean
  degradations?: string[]
  recoverable?: boolean
  errorCode?: string
  retryRequest?: ChatRetryRequest
}

export interface ChatRetryRequest {
  content: string
  allowNetwork: boolean
  clientRequestId: string
  targetCharacterId?: string
  maxSpeakers?: number
}

export interface HistoryResponse {
  messages: ChatMessage[]
  has_more: boolean
  next_before_id: number | null
}

export interface StreamEvent {
  event: 'routing' | 'speaker_start' | 'token' | 'speaker_done' | 'media_status' | 'done' | 'error'
  data: Record<string, unknown>
}
