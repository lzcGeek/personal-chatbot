<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { getSkills, type SkillInfo } from '../api/skills'


const props = defineProps<{ disabled: boolean }>()
const emit = defineEmits<{ send: [message: string] }>()
const value = ref('')
const textarea = ref<HTMLTextAreaElement>()
const skills = ref<SkillInfo[]>([])
const showCompletions = ref(false)
const selectedIndex = ref(0)

const slashMode = computed(() => value.value.trimStart().startsWith('/') && !value.value.includes(' '))
const filteredSkills = computed(() => {
  if (!slashMode.value) return []
  const prefix = value.value.trimStart().slice(1).toLowerCase()
  return skills.value.filter(item => item.enabled && item.name.toLowerCase().startsWith(prefix))
})

onMounted(async () => {
  try { skills.value = await getSkills() } catch { /* ignore */ }
})

function submit(): void {
  const message = value.value.trim()
  if (!message || props.disabled) return
  showCompletions.value = false
  emit('send', message)
  value.value = ''
  nextTick(() => resize())
}

function selectSkill(name: string): void {
  value.value = `/${name} `
  showCompletions.value = false
  textarea.value?.focus()
  nextTick(() => resize())
}

function onKeydown(event: KeyboardEvent): void {
  if (showCompletions.value && filteredSkills.value.length) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      selectedIndex.value = Math.min(selectedIndex.value + 1, filteredSkills.value.length - 1)
      return
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      selectedIndex.value = Math.max(selectedIndex.value - 1, 0)
      return
    }
    if (event.key === 'Tab' || event.key === 'Enter') {
      event.preventDefault()
      selectSkill(filteredSkills.value[selectedIndex.value].name)
      return
    }
    if (event.key === 'Escape') {
      showCompletions.value = false
      return
    }
  }
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    submit()
  }
}

function onInput(): void {
  showCompletions.value = slashMode.value && filteredSkills.value.length > 0
  selectedIndex.value = 0
  resize()
}

function resize(): void {
  if (!textarea.value) return
  textarea.value.style.height = 'auto'
  textarea.value.style.height = `${Math.min(textarea.value.scrollHeight, 180)}px`
}
</script>

<template>
  <div class="chat-input-wrapper">
    <ul v-if="showCompletions && filteredSkills.length" class="skill-completions">
      <li
        v-for="(skill, index) in filteredSkills"
        :key="skill.name"
        :class="{ active: index === selectedIndex }"
        @click="selectSkill(skill.name)"
        @mouseenter="selectedIndex = index"
      >
        <strong>/{{ skill.name }}</strong>
        <span>{{ skill.description }}</span>
      </li>
    </ul>
    <form class="chat-input" @submit.prevent="submit">
      <textarea
        ref="textarea"
        v-model="value"
        rows="1"
        :disabled="disabled"
        aria-label="聊天消息"
        placeholder="输入消息，输入 / 调用 Skill，Enter 发送"
        @keydown="onKeydown"
        @input="onInput"
      />
      <button type="submit" :disabled="disabled || !value.trim()">
        {{ disabled ? '生成中' : '发送' }}
      </button>
    </form>
  </div>
</template>
