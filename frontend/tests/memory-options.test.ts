import assert from 'node:assert/strict'
import test from 'node:test'

import { memoryActions, memoryScopeLabel, memoryValidityLabel } from '../src/memory-options.ts'

test('memory labels explain scope and hybrid validity', () => {
  assert.equal(memoryScopeLabel('conversation_shared'), '会话共享')
  assert.equal(memoryScopeLabel('character_private'), '角色私有')
  assert.equal(memoryValidityLabel('pending_confirmation'), '待确认')
  assert.equal(memoryValidityLabel('historical'), '历史版本')
})

test('memory actions do not restore superseded history', () => {
  assert.deepEqual(memoryActions('active', null), ['invalidate', 'delete'])
  assert.deepEqual(memoryActions('pending_confirmation', null), ['confirm', 'invalidate', 'delete'])
  assert.deepEqual(memoryActions('invalid', null), ['restore', 'delete'])
  assert.deepEqual(memoryActions('superseded', 'new-id'), ['delete'])
})
