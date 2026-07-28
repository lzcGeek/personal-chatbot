import assert from 'node:assert/strict'
import test from 'node:test'

import {
  normalizeConversationMode,
  normalizedCharacterDraft,
  validateMemberSelection,
  characterErrorMessage,
} from '../src/character-options.ts'


test('legacy or unknown conversation mode falls back to assistant', () => {
  assert.equal(normalizeConversationMode(undefined), 'assistant')
  assert.equal(normalizeConversationMode('legacy'), 'assistant')
  assert.equal(normalizeConversationMode('group'), 'group')
})

test('member selection enforces single and group NPC modes', () => {
  assert.equal(validateMemberSelection('assistant', []), '')
  assert.equal(validateMemberSelection('single_character', []), 'NPC 模式至少选择一个角色')
  assert.equal(validateMemberSelection('single_character', ['a', 'b']), '单角色模式必须只选择一个角色')
  assert.equal(validateMemberSelection('single_character', ['a']), '')
  assert.equal(validateMemberSelection('group', ['a', 'b']), '')
})

test('character form trims the required name without changing persona fields', () => {
  const result = normalizedCharacterDraft({
    name: '  守卫  ', description: ' desc ', personality: '', scenario: '', greeting: '',
    example_dialogue: '', generation_settings: {}, permissions: {},
    image_profile_id: null, tts_profile_id: null,
  })
  assert.equal(result.name, '守卫')
  assert.equal(result.description, ' desc ')
})

test('character errors expose only the server detail or safe fallback', () => {
  assert.equal(
    characterErrorMessage({ response: { data: { detail: 'Character not found' } } }, '失败'),
    'Character not found',
  )
  assert.equal(characterErrorMessage({ secret: 'hidden' }, '失败'), '失败')
})
