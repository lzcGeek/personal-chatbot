import type { ChatMessage } from './types/chat'


export interface ConversationChatState {
  messages: ChatMessage[]
  loadingHistory: boolean
  generating: boolean
  hasMore: boolean
  error: string
  activeSpeaker: string
  nextBeforeId?: number
  historyLoaded: boolean
}

export function createConversationChatState(): ConversationChatState {
  return {
    messages: [],
    loadingHistory: false,
    generating: false,
    hasMore: true,
    error: '',
    activeSpeaker: '',
    historyLoaded: false,
  }
}
