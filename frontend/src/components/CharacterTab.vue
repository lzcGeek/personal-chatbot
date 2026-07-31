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
import { errorText, notify } from '../notifications'


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
const error = ref('')
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
  error.value = ''
  try {
    const saved = await store.save(normalizedCharacterDraft(draft), selectedId.value ?? undefined)
    edit(saved)
    notify(`角色“${saved.name}”已保存`)
  } catch (reason: unknown) {
    error.value = errorText(reason, '角色保存失败')
    notify(error.value, 'error')
  }
}

async function remove(character: CharacterInfo): Promise<void> {
  if (!window.confirm(`删除角色“${character.name}”？历史消息仍会保留角色名。`)) {
    notify('已取消删除角色', 'info')
    return
  }
  try {
    await store.remove(character.id)
    if (selectedId.value === character.id) edit()
    notify(`角色“${character.name}”已删除`)
  } catch (reason: unknown) {
    error.value = errorText(reason, '角色删除失败')
    notify(error.value, 'error')
  }
}

async function duplicateSelected(): Promise<void> {
  if (!selectedId.value) return
  try {
    await store.duplicate(selectedId.value)
    notify('角色副本已创建')
  } catch (reason: unknown) {
    error.value = errorText(reason, '角色复制失败')
    notify(error.value, 'error')
  }
}

async function archiveSelected(): Promise<void> {
  const character = store.characters.find(item => item.id === selectedId.value)
  if (!character) return
  if (!window.confirm(`归档角色“${character.name}”？归档后不会出现在可选角色列表中。`)) {
    notify('已取消归档角色', 'info')
    return
  }
  try {
    await store.archive(character)
    edit()
    notify(`角色“${character.name}”已归档`)
  } catch (reason: unknown) {
    error.value = errorText(reason, '角色归档失败')
    notify(error.value, 'error')
  }
}

function cancelEdit(): void {
  const character = store.characters.find(item => item.id === selectedId.value)
  edit(character)
  notify('已取消编辑，本次修改未保存', 'info')
}

async function uploadAvatar(event: Event): Promise<void> {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file || !selectedId.value) return
  try {
    await store.uploadAvatar(selectedId.value, file)
    notify('角色头像已更新')
  } catch (reason: unknown) {
    error.value = errorText(reason, '头像上传失败')
    notify(error.value, 'error')
  } finally {
    target.value = ''
  }
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
  if (validation) { notice.value = validation; notify(validation, 'error'); return }
  error.value = ''
  try {
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
    notice.value = ''
    notify('当前会话的角色设置已保存')
  } catch (reason: unknown) {
    error.value = errorText(reason, '会话角色设置保存失败')
    notify(error.value, 'error')
  }
}

onMounted(async () => {
  await Promise.all([store.load(), conversations.load()])
  await loadRuntime()
})
</script>

<template>
  <div class="character-tab">
    <p v-if="error || store.error" class="inline-error">{{ error || store.error }}</p>
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
          <small class="field-help">手动：发送前指定角色；@ 提及：按消息中的角色名选择；轮询：依次发言；自动：由系统选择。</small>
        </label>
      </div>
      <label>场景描述<textarea v-model="scene" rows="2" placeholder="示例：雨夜的旧港口酒馆；用于告诉所有角色当前共同环境" /></label>
      <div class="character-grid" v-if="mode === 'group'">
        <label>每轮最多角色数<input v-model.number="maxSpeakers" type="number" min="1" max="8" placeholder="示例：2；限制一轮参与回复的角色数" /></label>
        <label>连续生成上限<input v-model.number="maxGenerations" type="number" min="1" max="12" placeholder="示例：3；防止角色无限接力回复" /></label>
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
        <label>名称<input v-model="draft.name" maxlength="120" placeholder="示例：艾琳（聊天中显示的角色名）" required /></label>
        <label>角色描述<textarea v-model="draft.description" rows="3" placeholder="示例：银月城的药剂师，熟悉草药与古代传说；用于定义身份和背景" /></label>
        <label>性格<textarea v-model="draft.personality" rows="3" placeholder="示例：温柔谨慎、偶尔毒舌；用于约束角色说话和处事风格" /></label>
        <label>默认场景<textarea v-model="draft.scenario" rows="2" placeholder="示例：玩家第一次走进她的药剂铺；用于没有会话场景时提供背景" /></label>
        <label>开场白<textarea v-model="draft.greeting" rows="2" placeholder="示例：欢迎光临，需要我为你调配什么？；用于角色首次出场" /></label>
        <label>示例对话<textarea v-model="draft.example_dialogue" rows="3" placeholder="示例：\n玩家：这里有治疗药水吗？\n艾琳：有，但请先告诉我伤势。\n用于模仿角色语气" /></label>
        <div class="character-grid">
          <label>Temperature<input type="number" min="0" max="2" step="0.1" placeholder="示例：0.8；越高越有创造性" :value="draft.generation_settings.temperature ?? ''" @input="setGeneration('temperature', $event)" /></label>
          <label>Top P<input type="number" min="0" max="1" step="0.05" placeholder="示例：0.9；控制候选词范围" :value="draft.generation_settings.top_p ?? ''" @input="setGeneration('top_p', $event)" /></label>
          <label>最大输出 Token<input type="number" min="1" max="32768" placeholder="示例：1024；限制单次回复长度" :value="draft.generation_settings.max_tokens ?? ''" @input="setGeneration('max_tokens', $event)" /></label>
        </div>
        <div class="character-grid">
          <label>图片配置 ID<input v-model="draft.image_profile_id" placeholder="示例：default-image；指定该角色的图片生成配置（可选）" /></label>
          <label>TTS 音色 ID<input v-model="draft.tts_profile_id" placeholder="示例：zh_female_01；指定该角色的语音音色（可选）" /></label>
        </div>
        <div class="character-permissions">
          <label><input v-model="draft.permissions.knowledge" type="checkbox" />知识库</label>
          <label><input v-model="draft.permissions.tools" type="checkbox" />工具</label>
          <label><input v-model="draft.permissions.network" type="checkbox" />联网</label>
          <label><input v-model="draft.permissions.image" type="checkbox" />图片生成</label>
          <label><input v-model="draft.permissions.tts" type="checkbox" />语音合成</label>
        </div>
        <small class="field-help">权限决定这个角色在回复时可以使用哪些可选能力；仍需系统已配置对应服务。</small>
        <label v-if="selectedId">头像<input type="file" accept="image/png,image/jpeg,image/webp,image/gif" @change="uploadAvatar" /><small class="field-help">支持 PNG、JPEG、WebP 或 GIF，用于消息头像。</small></label>
        <div class="tab-actions">
          <button class="btn-primary" type="submit">保存角色</button>
          <button class="btn-secondary" type="button" @click="cancelEdit">取消编辑</button>
          <button v-if="selectedId" class="btn-secondary" type="button" @click="duplicateSelected">复制</button>
          <button v-if="selectedId" class="btn-secondary" type="button" @click="archiveSelected">归档</button>
          <button v-if="selectedId" class="btn-danger" type="button" @click="remove(store.characters.find(item => item.id === selectedId)!)">删除</button>
        </div>
      </form>
    </div>
  </div>
</template>
