<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { createSkill, disableSkill, enableSkill, getSkills, reloadSkills, uploadSkill, type SkillInfo } from '../api/skills'
import { errorText, notify } from '../notifications'


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
    notify(`Skills 已重载，共发现 ${skills.value.length} 个`)
  } catch (reason: unknown) {
    error.value = errorText(reason, '重载失败')
    notify(error.value, 'error')
  } finally {
    loading.value = false
  }
}

function toggleEditor(): void {
  if (showEditor.value) {
    showEditor.value = false
    notify('已取消新建，表单内容未保存', 'info')
  } else {
    openEditor()
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
    notify(`Skill 文件“${file.name}”已上传`)
  } catch (reason: unknown) {
    const msg = reason instanceof Error ? reason.message : '上传失败'
    if (reason && typeof reason === 'object' && 'response' in reason) {
      const axiosErr = reason as { response?: { data?: { detail?: string } } }
      error.value = axiosErr.response?.data?.detail || msg
    } else {
      error.value = msg
    }
    notify(error.value, 'error')
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
    notify(`Skill“${skill.name}”已${skill.enabled ? '启用' : '停用'}`)
  } catch (reason: unknown) {
    error.value = errorText(reason, '操作失败')
    notify(error.value, 'error')
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
    notify('Skill 已保存')
  } catch (reason: unknown) {
    error.value = errorText(reason, '创建失败')
    notify(error.value, 'error')
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
      <button class="btn-primary" @click="toggleEditor">
        {{ showEditor ? '取消' : '新建 Skill' }}
      </button>
    </div>
    <input ref="uploadInput" type="file" accept=".md" style="display:none" @change="handleUpload" />

    <form v-if="showEditor" class="skill-form" @submit.prevent="handleCreate">
      <label>
        名称
        <input v-model="editor.name" placeholder="示例：code-review（调用 Skill 时使用的唯一名称）" required />
      </label>
      <label>
        描述
        <input v-model="editor.description" placeholder="示例：检查代码缺陷并给出修改建议（用于说明适用场景）" required />
      </label>
      <label>
        内容
        <textarea
          v-model="editor.content"
          rows="8"
          placeholder="示例：当用户要求审查代码时，先检查正确性和安全性，再按优先级列出问题。此处内容将作为 Skill 的 Markdown 指令。"
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
