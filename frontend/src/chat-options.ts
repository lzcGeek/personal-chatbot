import type { ChatMessage, ChatRetryRequest } from './types/chat'


export interface PreferenceStorage {
  getItem(key: string): string | null
}

export function loadNetworkPreference(storage: PreferenceStorage): boolean {
  return storage.getItem('chat-allow-network') === 'true'
}

export function createChatRetryRequest(
  content: string,
  allowNetwork: boolean,
  idFactory: () => string = () => crypto.randomUUID(),
  targetCharacterId?: string,
  maxSpeakers?: number,
): ChatRetryRequest {
  const request: ChatRetryRequest = {
    content: content.trim(),
    allowNetwork,
    clientRequestId: idFactory(),
  }
  if (targetCharacterId) request.targetCharacterId = targetCharacterId
  if (maxSpeakers) request.maxSpeakers = maxSpeakers
  return request
}

export function canRetryMessage(message: ChatMessage): boolean {
  return message.recoverable === true && message.retryRequest !== undefined
}
