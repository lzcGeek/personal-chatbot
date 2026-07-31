<script setup lang="ts">
import { ref } from 'vue'
import McpTab from './McpTab.vue'
import SkillTab from './SkillTab.vue'
import KnowledgeBaseTab from './KnowledgeBaseTab.vue'
import CharacterTab from './CharacterTab.vue'
import MemoryTab from './MemoryTab.vue'
import { useAuthStore } from '../stores/auth'
import { notify } from '../notifications'


const activeTab = ref<'characters' | 'memory' | 'knowledge' | 'mcp' | 'skills'>('characters')
const authStore = useAuthStore()
const emit = defineEmits<{ close: [] }>()

async function handleLogout(): Promise<void> {
  if (!window.confirm('确定退出登录？当前未发送的输入内容可能会丢失。')) {
    notify('已取消退出登录', 'info')
    return
  }
  emit('close')
  await authStore.logout()
  notify('已退出登录', 'info')
}
</script>

<template>
  <Teleport to="body">
    <aside class="settings-overlay" @click.self="$emit('close')">
      <div class="settings-panel">
        <header class="settings-header">
          <h2>设置</h2>
          <button class="settings-logout" @click="handleLogout">退出登录</button>
          <button class="settings-close" aria-label="关闭设置" @click="$emit('close')">&times;</button>
        </header>
        <nav class="settings-tabs">
          <button :class="{ active: activeTab === 'characters' }" @click="activeTab = 'characters'">角色</button>
          <button :class="{ active: activeTab === 'memory' }" @click="activeTab = 'memory'">记忆</button>
          <button :class="{ active: activeTab === 'knowledge' }" @click="activeTab = 'knowledge'">知识库</button>
          <button :class="{ active: activeTab === 'mcp' }" @click="activeTab = 'mcp'">MCP 服务</button>
          <button :class="{ active: activeTab === 'skills' }" @click="activeTab = 'skills'">Skills</button>
        </nav>
        <section class="settings-body">
          <CharacterTab v-if="activeTab === 'characters'" />
          <MemoryTab v-else-if="activeTab === 'memory'" />
          <KnowledgeBaseTab v-else-if="activeTab === 'knowledge'" />
          <McpTab v-else-if="activeTab === 'mcp'" />
          <SkillTab v-else />
        </section>
      </div>
    </aside>
  </Teleport>
</template>
