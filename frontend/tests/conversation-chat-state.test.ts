import assert from 'node:assert/strict'
import test from 'node:test'

import { createConversationChatState } from '../src/conversation-chat-state.ts'


test('conversation chat states keep generation and temporary messages isolated', () => {
  const first = createConversationChatState()
  const second = createConversationChatState()

  first.generating = true
  first.messages.push({
    id: 'assistant-streaming',
    role: 'assistant',
    content: '',
    status: 'streaming',
    created_at: 'now',
  })

  assert.equal(first.generating, true)
  assert.equal(first.messages.length, 1)
  assert.equal(second.generating, false)
  assert.deepEqual(second.messages, [])
})

test('new conversation state starts with independent history pagination', () => {
  const first = createConversationChatState()
  first.hasMore = false
  first.nextBeforeId = 42
  first.historyLoaded = true

  const second = createConversationChatState()
  assert.equal(second.hasMore, true)
  assert.equal(second.nextBeforeId, undefined)
  assert.equal(second.historyLoaded, false)
})
