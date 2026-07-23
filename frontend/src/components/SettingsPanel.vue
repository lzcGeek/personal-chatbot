<script setup lang="ts">
import { ref } from 'vue'
import McpTab from './McpTab.vue'
import SkillTab from './SkillTab.vue'


const activeTab = ref<'mcp' | 'skills'>('mcp')
</script>

<template>
  <Teleport to="body">
    <aside class="settings-overlay" @click.self="$emit('close')">
      <div class="settings-panel">
        <header class="settings-header">
          <h2>设置</h2>
          <button class="settings-close" aria-label="关闭设置" @click="$emit('close')">&times;</button>
        </header>
        <nav class="settings-tabs">
          <button :class="{ active: activeTab === 'mcp' }" @click="activeTab = 'mcp'">MCP 服务</button>
          <button :class="{ active: activeTab === 'skills' }" @click="activeTab = 'skills'">Skills</button>
        </nav>
        <section class="settings-body">
          <McpTab v-if="activeTab === 'mcp'" />
          <SkillTab v-else />
        </section>
      </div>
    </aside>
  </Teleport>
</template>
