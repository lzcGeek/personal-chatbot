import { ref } from 'vue'
import { defineStore } from 'pinia'

import {
  createCharacter,
  deleteCharacter,
  duplicateCharacter,
  getCharacters,
  updateCharacter,
  uploadCharacterAvatar,
  type CharacterInfo,
  type CharacterWrite,
} from '../api/characters'
import { characterErrorMessage } from '../character-options'


export const useCharacterStore = defineStore('characters', () => {
  const characters = ref<CharacterInfo[]>([])
  const loading = ref(false)
  const error = ref('')

  async function load(): Promise<void> {
    loading.value = true
    try {
      characters.value = await getCharacters()
      error.value = ''
    } catch (reason) {
      error.value = characterErrorMessage(reason, '角色加载失败')
    } finally {
      loading.value = false
    }
  }

  async function save(payload: CharacterWrite, id?: string): Promise<CharacterInfo> {
    const result = id
      ? await updateCharacter(id, { ...payload, archived: false })
      : await createCharacter(payload)
    replace(result)
    return result
  }

  async function duplicate(id: string): Promise<void> {
    replace(await duplicateCharacter(id))
  }

  async function remove(id: string): Promise<void> {
    await deleteCharacter(id)
    characters.value = characters.value.filter(item => item.id !== id)
  }

  async function archive(character: CharacterInfo): Promise<void> {
    await updateCharacter(character.id, { ...character, archived: true })
    characters.value = characters.value.filter(item => item.id !== character.id)
  }

  async function uploadAvatar(id: string, file: File): Promise<void> {
    replace(await uploadCharacterAvatar(id, file))
  }

  function replace(item: CharacterInfo): void {
    const index = characters.value.findIndex(current => current.id === item.id)
    if (index === -1) characters.value.unshift(item)
    else characters.value[index] = item
  }

  return { characters, loading, error, load, save, duplicate, archive, remove, uploadAvatar }
})

