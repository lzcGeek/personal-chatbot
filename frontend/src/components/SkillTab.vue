<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { createSkill, disableSkill, enableSkill, getSkills, reloadSkills, uploadSkill, type SkillInfo } from '../api/skills'


const skills = ref<SkillInfo[]>([])
const loading = ref(false)
const error = ref('')
const showEditor = ref(false)
const uploadInput = ref<HTMLInputElement>()

const editor = reactive({
  name: '',
  description: '',
  content: '',
})

onMounted(refresh)

async function refresh(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    skills.value = await getSkills()
  } catch (reason: unknown) {
    error.value = reason instanceof Error ? reason.message : '加载失败'
  } finally {
    loading.value = false
  }
}

async function handleReload(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    skills.value = await reloadSkills()
  } catch (reason: unknown) {
    error.value = reason instanceof Error ? reason.message : '重载失败'
  } finally {
    loading.value = false
  }
}

function openEditor(): void {
  editor.name = ''
  editor.description = ''
  editor.content = '在这里编写 Skill 的指令内容。\n\n例如：\n- 当用户询问代码时，解释思路再给出示例\n- 使用中文回复，保持简洁'
  showEditor.value = true
}

function pickFile(): void {
  uploadInput.value?.click()
}

async function handleUpload(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  loading.value = true
  error.value = ''
  try {
    await uploadSkill(file)
    input.value = ''
    await refresh()
  } catch (reason: unknown) {
    const msg = reason instanceof Error ? reason.message : '上传失败'
    if (reason && typeof reason === 'object' && 'response' in reason) {
      const axiosErr = reason as { response?: { data?: { detail?: string } } }
      error.value = axiosErr.response?.data?.detail || msg
    } else {
      error.value = msg
    }
  } finally {
    loading.value = false
  }
}

async function toggleSkill(skill: SkillInfo): Promise<void> {
  loading.value = true
  try {
    if (skill.enabled) {
      await disableSkill(skill.name)
    } else {
      await enableSkill(skill.name)
    }
    skill.enabled = !skill.enabled
  } catch (reason: unknown) {
    error.value = reason instanceof Error ? reason.message : '操作失败'
  } finally {
    loading.value = false
  }
}

async function handleCreate(): Promise<void> {
  if (!editor.name.trim() || !editor.description.trim() || !editor.content.trim()) return
  loading.value = true
  error.value = ''
  try {
    await createSkill({
      name: editor.name.trim(),
      description: editor.description.trim(),
      content: editor.content.trim(),
    })
    showEditor.value = false
    Object.assign(editor, { name: '', description: '', content: '' })
    await refresh()
  } catch (reason: unknown) {
    error.value = reason instanceof Error ? reason.message : '创建失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="skill-tab">
    <div class="tab-actions">
      <button class="btn-secondary" @click="handleReload" :disabled="loading">重载 Skills</button>
      <button class="btn-secondary" @click="pickFile" :disabled="loading">上传 Skill 文件</button>
      <button class="btn-primary" @click="showEditor ? (showEditor = false) : openEditor()">
        {{ showEditor ? '取消' : '新建 Skill' }}
      </button>
    </div>
    <input ref="uploadInput" type="file" accept=".md" style="display:none" @change="handleUpload" />

    <form v-if="showEditor" class="skill-form" @submit.prevent="handleCreate">
      <label>
        名称
        <input v-model="editor.name" placeholder="my-skill" required />
      </label>
      <label>
        描述
        <input v-model="editor.description" placeholder="这个 Skill 的用途" required />
      </label>
      <label>
        内容
        <textarea
          v-model="editor.content"
          rows="8"
          placeholder="Skill 的指令内容（将作为 Markdown 正文）"
          required
        />
      </label>
      <button type="submit" class="btn-primary" :disabled="loading">保存 Skill</button>
    </form>

    <p v-if="error" class="inline-error">{{ error }}</p>

    <div v-if="loading && !skills.length" class="empty-note">加载中…</div>
    <div v-else-if="!skills.length" class="empty-note">暂无 Skill，点击"新建 Skill"创建或"重载 Skills"从磁盘加载。</div>

    <ul v-else class="server-list">
      <li v-for="skill in skills" :key="skill.name" class="server-card">
        <div class="server-info">
          <span class="status-badge" :class="skill.enabled ? 'loaded' : ''">{{ skill.enabled ? '已启用' : '已禁用' }}</span>
          <div>
            <strong>{{ skill.name }}</strong>
            <span class="server-meta">{{ skill.description }}</span>
          </div>
        </div>
        <label class="toggle-switch">
          <input type="checkbox" :checked="skill.enabled" @change="toggleSkill(skill)" />
          <span class="toggle-slider"></span>
        </label>
      </li>
    </ul>
  </div>
</template>
