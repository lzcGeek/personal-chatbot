import assert from 'node:assert/strict'
import test from 'node:test'

import {
  canRetryMessage,
  createChatRetryRequest,
  loadNetworkPreference,
} from '../src/chat-options.ts'


test('network preference defaults off and restores an explicit enabled value', () => {
  assert.equal(loadNetworkPreference({ getItem: () => null }), false)
  assert.equal(loadNetworkPreference({ getItem: () => 'false' }), false)
  assert.equal(loadNetworkPreference({ getItem: () => 'true' }), true)
})

test('retry request captures trimmed content, network state, and stable client id', () => {
  const request = createChatRetryRequest('  latest news  ', true, () => 'request-1')
  assert.deepEqual(request, {
    content: 'latest news',
    allowNetwork: true,
    clientRequestId: 'request-1',
  })
})

test('only recoverable messages with a captured request can retry', () => {
  const base = {
    id: 'assistant-1',
    role: 'assistant' as const,
    content: '',
    status: 'error' as const,
    created_at: 'now',
  }
  assert.equal(canRetryMessage({ ...base, recoverable: true }), false)
  assert.equal(
    canRetryMessage({
      ...base,
      recoverable: true,
      retryRequest: {
        content: 'question',
        allowNetwork: false,
        clientRequestId: 'request-1',
      },
    }),
    true,
  )
  assert.equal(
    canRetryMessage({
      ...base,
      recoverable: false,
      retryRequest: {
        content: 'question',
        allowNetwork: false,
        clientRequestId: 'request-1',
      },
    }),
    false,
  )
})

test('group retry keeps the target and bounded speaker count', () => {
  const request = createChatRetryRequest(
    '  defend the gate  ',
    false,
    () => 'group-request',
    'character-1',
    2,
  )
  assert.deepEqual(request, {
    content: 'defend the gate',
    allowNetwork: false,
    clientRequestId: 'group-request',
    targetCharacterId: 'character-1',
    maxSpeakers: 2,
  })
})
