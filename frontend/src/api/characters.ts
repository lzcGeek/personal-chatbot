import { api } from './chat'


export interface CharacterWrite {
  name: string
  description: string
  personality: string
  scenario: string
  greeting: string
  example_dialogue: string
  generation_settings: Record<string, unknown>
  permissions: Record<string, boolean>
  image_profile_id: string | null
  tts_profile_id: string | null
}

export interface CharacterInfo extends CharacterWrite {
  id: string
  archived: boolean
  has_avatar: boolean
  created_at: string
  updated_at: string
}

export async function getCharacters(includeArchived = false): Promise<CharacterInfo[]> {
  const response = await api.get<CharacterInfo[]>('/characters', {
    params: { include_archived: includeArchived },
  })
  return response.data
}

export async function createCharacter(payload: CharacterWrite): Promise<CharacterInfo> {
  const response = await api.post<CharacterInfo>('/characters', payload)
  return response.data
}

export async function updateCharacter(
  id: string,
  payload: CharacterWrite & { archived: boolean },
): Promise<CharacterInfo> {
  const response = await api.put<CharacterInfo>(`/characters/${id}`, payload)
  return response.data
}

export async function duplicateCharacter(id: string): Promise<CharacterInfo> {
  const response = await api.post<CharacterInfo>(`/characters/${id}/duplicate`)
  return response.data
}

export async function deleteCharacter(id: string): Promise<void> {
  await api.delete(`/characters/${id}`)
}

export async function uploadCharacterAvatar(id: string, file: File): Promise<CharacterInfo> {
  const body = new FormData()
  body.append('file', file)
  const response = await api.post<CharacterInfo>(`/characters/${id}/avatar`, body)
  return response.data
}

export function characterAvatarUrl(id: string): string {
  return `/api/characters/${id}/avatar`
}
