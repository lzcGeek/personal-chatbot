<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import {
  getConversationMembers,
  replaceConversationMembers,
  type ConversationMode,
  type RoutingStrategy,
} from '../api/conversations'
import type { CharacterInfo, CharacterWrite } from '../api/characters'
import {
  normalizeConversationMode,
  normalizedCharacterDraft,
  validateMemberSelection,
} from '../character-options'
import { useCharacterStore } from '../stores/characters'
import { useConversationStore } from '../stores/conversations'


const store = useCharacterStore()
const conversations = useConversationStore()
const selectedId = ref<string | null>(null)
const memberIds = ref<string[]>([])
const mode = ref<ConversationMode>('assistant')
const routing = ref<RoutingStrategy>('manual')
const scene = ref('')
const maxSpeakers = ref(1)
const maxGenerations = ref(3)
const notice = ref('')
const draft = reactive<CharacterWrite>(emptyCharacter())
const currentConversation = computed(() =>
  conversations.conversations.find(item => item.id === conversations.currentId),
)

function emptyCharacter(): CharacterWrite {
  return {
    name: '', description: '', personality: '', scenario: '', greeting: '',
    example_dialogue: '', generation_settings: {}, permissions: {},
    image_profile_id: null, tts_profile_id: null,
  }
}

function edit(character?: CharacterInfo): void {
  selectedId.value = character?.id ?? null
  Object.assign(draft, character ?? emptyCharacter())
}

async function save(): Promise<void> {
  const saved = await store.save(normalizedCharacterDraft(draft), selectedId.value ?? undefined)
  edit(saved)
  notice.value = '角色已保存'
}

async function remove(character: CharacterInfo): Promise<void> {
  if (!window.confirm(`删除角色“${character.name}”？历史消息仍会保留角色名。`)) return
  await store.remove(character.id)
  if (selectedId.value === character.id) edit()
}

async function uploadAvatar(event: Event): Promise<void> {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file && selectedId.value) await store.uploadAvatar(selectedId.value, file)
}

function setGeneration(key: 'temperature' | 'top_p' | 'max_tokens', event: Event): void {
  const raw = (event.target as HTMLInputElement).value
  const next = { ...draft.generation_settings }
  if (raw === '') delete next[key]
  else next[key] = Number(raw)
  draft.generation_settings = next
}

async function loadRuntime(): Promise<void> {
  const conversation = currentConversation.value
  if (!conversation) return
  mode.value = normalizeConversationMode(conversation.mode)
  routing.value = conversation.routing_strategy
  scene.value = conversation.scene_description
  maxSpeakers.value = conversation.max_speakers_per_turn ?? 1
  maxGenerations.value = conversation.max_group_generations ?? 3
  memberIds.value = (await getConversationMembers(conversation.id))
    .filter(item => item.enabled)
    .map(item => item.character_id)
}

async function saveRuntime(): Promise<void> {
  const conversation = currentConversation.value
  if (!conversation) return
  const validation = validateMemberSelection(mode.value, memberIds.value)
  if (validation) { notice.value = validation; return }
  if (conversation.mode !== 'assistant') {
    await conversations.updateSettings(conversation.id, { mode: 'assistant' })
  }
  await replaceConversationMembers(
    conversation.id,
    memberIds.value.map((characterId, position) => ({
      character_id: characterId, position, enabled: true, overrides: {},
    })),
  )
  await conversations.updateSettings(conversation.id, {
    mode: mode.value,
    routing_strategy: routing.value,
    scene_description: scene.value,
    max_speakers_per_turn: maxSpeakers.value,
    max_group_generations: maxGenerations.value,
  })
  notice.value = '当前会话的角色设置已保存'
}

onMounted(async () => {
  await Promise.all([store.load(), conversations.load()])
  await loadRuntime()
})
</script>

<template>
  <div class="character-tab">
    <p v-if="store.error" class="inline-error">{{ store.error }}</p>
    <p v-if="notice" class="empty-note">{{ notice }}</p>

    <section class="character-runtime">
      <strong>当前会话</strong>
      <div class="character-grid">
        <label>模式
          <select v-model="mode">
            <option value="assistant">普通助手（兼容模式）</option>
            <option value="single_character">单角色 NPC</option>
            <option value="group">多角色群聊</option>
          </select>
        </label>
        <label>发言路由
          <select v-model="routing" :disabled="mode === 'assistant'">
            <option value="manual">手动</option><option value="mention">@ 提及</option>
            <option value="round_robin">轮询</option><option value="auto">自动</option>
          </select>
        </label>
      </div>
      <label>场景描述<textarea v-model="scene" rows="2" /></label>
      <div class="character-grid" v-if="mode === 'group'">
        <label>每轮最多角色数<input v-model.number="maxSpeakers" type="number" min="1" max="8" /></label>
        <label>连续生成上限<input v-model.number="maxGenerations" type="number" min="1" max="12" /></label>
      </div>
      <div class="character-members">
        <label v-for="character in store.characters" :key="character.id">
          <input v-model="memberIds" type="checkbox" :value="character.id" /> {{ character.name }}
        </label>
      </div>
      <button class="btn-primary" @click="saveRuntime">保存会话角色设置</button>
    </section>

    <div class="character-layout">
      <aside class="character-list">
        <button class="btn-primary" @click="edit()">新建角色</button>
        <button v-for="character in store.characters" :key="character.id" class="character-item" @click="edit(character)">
          <img v-if="character.has_avatar" :src="`/api/characters/${character.id}/avatar`" alt="" />
          <span>{{ character.name }}</span>
        </button>
      </aside>
      <form class="character-form" @submit.prevent="save">
        <label>名称<input v-model="draft.name" maxlength="120" required /></label>
        <label>角色描述<textarea v-model="draft.description" rows="3" /></label>
        <label>性格<textarea v-model="draft.personality" rows="3" /></label>
        <label>默认场景<textarea v-model="draft.scenario" rows="2" /></label>
        <label>开场白<textarea v-model="draft.greeting" rows="2" /></label>
        <label>示例对话<textarea v-model="draft.example_dialogue" rows="3" /></label>
        <div class="character-grid">
          <label>Temperature<input type="number" min="0" max="2" step="0.1" :value="draft.generation_settings.temperature ?? ''" @input="setGeneration('temperature', $event)" /></label>
          <label>Top P<input type="number" min="0" max="1" step="0.05" :value="draft.generation_settings.top_p ?? ''" @input="setGeneration('top_p', $event)" /></label>
          <label>最大输出 Token<input type="number" min="1" max="32768" :value="draft.generation_settings.max_tokens ?? ''" @input="setGeneration('max_tokens', $event)" /></label>
        </div>
        <div class="character-grid">
          <label>图片配置 ID<input v-model="draft.image_profile_id" placeholder="可选，Provider 启用后生效" /></label>
          <label>TTS 音色 ID<input v-model="draft.tts_profile_id" placeholder="可选，Provider 启用后生效" /></label>
        </div>
        <div class="character-permissions">
          <label><input v-model="draft.permissions.knowledge" type="checkbox" />知识库</label>
          <label><input v-model="draft.permissions.tools" type="checkbox" />工具</label>
          <label><input v-model="draft.permissions.network" type="checkbox" />联网</label>
          <label><input v-model="draft.permissions.image" type="checkbox" />图片生成</label>
          <label><input v-model="draft.permissions.tts" type="checkbox" />语音合成</label>
        </div>
        <label v-if="selectedId">头像<input type="file" accept="image/png,image/jpeg,image/webp,image/gif" @change="uploadAvatar" /></label>
        <div class="tab-actions">
          <button class="btn-primary" type="submit">保存角色</button>
          <button v-if="selectedId" class="btn-secondary" type="button" @click="store.duplicate(selectedId)">复制</button>
          <button v-if="selectedId" class="btn-secondary" type="button" @click="store.archive(store.characters.find(item => item.id === selectedId)!)">归档</button>
          <button v-if="selectedId" class="btn-danger" type="button" @click="remove(store.characters.find(item => item.id === selectedId)!)">删除</button>
        </div>
      </form>
    </div>
  </div>
</template>
