import type { CharacterWrite } from './api/characters'
import type { ConversationMode } from './api/conversations'


export function validateMemberSelection(mode: ConversationMode, characterIds: string[]): string {
  if (mode !== 'assistant' && characterIds.length === 0) return 'NPC 模式至少选择一个角色'
  if (mode === 'single_character' && characterIds.length !== 1) {
    return '单角色模式必须只选择一个角色'
  }
  return ''
}

export function normalizeConversationMode(mode: string | undefined): ConversationMode {
  return mode === 'single_character' || mode === 'group' ? mode : 'assistant'
}

export function normalizedCharacterDraft(draft: CharacterWrite): CharacterWrite {
  return { ...draft, name: draft.name.trim() }
}

export function characterErrorMessage(reason: unknown, fallback: string): string {
  if (reason && typeof reason === 'object' && 'response' in reason) {
    const response = (reason as { response?: { data?: { detail?: string } } }).response
    if (typeof response?.data?.detail === 'string') return response.data.detail
  }
  return reason instanceof Error ? reason.message : fallback
}
