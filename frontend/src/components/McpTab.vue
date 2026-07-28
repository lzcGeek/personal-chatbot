<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { addMcpServer, deleteMcpServer, disableMcpServer, enableMcpServer, getMcpServers, updateMcpNetworkPolicy, type McpServerInfo } from '../api/mcp'


const servers = ref<McpServerInfo[]>([])
const loading = ref(false)
const error = ref('')
const showForm = ref(false)
const deletingId = ref<number | null>(null)

const form = reactive({
  name: '',
  transport: 'stdio' as 'stdio' | 'sse' | 'http',
  command: '',
  args: '',
  env: '',
  url: '',
  requiresNetwork: false,
})

watch(() => form.transport, transport => {
  form.requiresNetwork = transport !== 'stdio'
})

async function refresh(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    servers.value = await getMcpServers()
  } catch (reason: unknown) {
    error.value = reason instanceof Error ? reason.message : '加载失败'
  } finally {
    loading.value = false
  }
}

async function submitAdd(): Promise<void> {
  if (!form.name.trim()) return
  loading.value = true
  error.value = ''
  try {
    const args = form.transport === 'stdio' && form.args.trim()
      ? form.args.split(',').map(item => item.trim()).filter(Boolean)
      : []
    const env: Record<string, string> = {}
    if (form.transport === 'stdio' && form.env.trim()) {
      form.env.split('\n').forEach(line => {
        const [key, ...rest] = line.split('=')
        if (key.trim() && rest.length) env[key.trim()] = rest.join('=').trim()
      })
    }
    const added = await addMcpServer({
      name: form.name.trim(),
      transport: form.transport,
      command: form.transport === 'stdio' ? form.command.trim() : undefined,
      args: form.transport === 'stdio' ? args : undefined,
      env: form.transport === 'stdio' && Object.keys(env).length ? env : undefined,
      url: form.transport !== 'stdio' ? form.url.trim() : undefined,
      requires_network: form.requiresNetwork,
    })
    servers.value.unshift(added)
    showForm.value = false
    Object.assign(form, { name: '', command: '', args: '', env: '', url: '', requiresNetwork: false })
  } catch (reason: unknown) {
    if (reason && typeof reason === 'object' && 'response' in reason) {
      const axiosErr = reason as { response?: { status?: number; data?: { detail?: string } } }
      if (axiosErr.response?.status === 422) {
        error.value = axiosErr.response.data?.detail || '服务器连接失败，请检查 URL 和传输类型'
      } else {
        error.value = axiosErr.response?.data?.detail || '添加失败'
      }
    } else {
      error.value = reason instanceof Error ? reason.message : '添加失败'
    }
  } finally {
    loading.value = false
  }
}

async function toggleServer(server: McpServerInfo): Promise<void> {
  loading.value = true
  try {
    if (server.enabled) {
      await disableMcpServer(server.id)
    } else {
      await enableMcpServer(server.id)
    }
    server.enabled = !server.enabled
  } catch (reason: unknown) {
    error.value = reason instanceof Error ? reason.message : '操作失败'
  } finally {
    loading.value = false
  }
}

async function remove(id: number): Promise<void> {
  deletingId.value = id
  try {
    await deleteMcpServer(id)
    servers.value = servers.value.filter(item => item.id !== id)
  } catch (reason: unknown) {
    error.value = reason instanceof Error ? reason.message : '删除失败'
  } finally {
    deletingId.value = null
  }
}

async function toggleNetworkPolicy(server: McpServerInfo): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const updated = await updateMcpNetworkPolicy(server.id, !server.requires_network)
    Object.assign(server, updated)
  } catch (reason: unknown) {
    error.value = reason instanceof Error ? reason.message : '联网分类更新失败'
  } finally {
    loading.value = false
  }
}

const transportIcon: Record<string, string> = { stdio: '⬡', sse: '⬢', http: '⬓' }

onMounted(refresh)
</script>

<template>
  <div class="mcp-tab">
    <div class="tab-actions">
      <button class="btn-secondary" @click="refresh" :disabled="loading">刷新</button>
      <button class="btn-primary" @click="showForm = !showForm">{{ showForm ? '取消' : '添加服务' }}</button>
    </div>

    <form v-if="showForm" class="mcp-form" @submit.prevent="submitAdd">
      <label>
        名称
        <input v-model="form.name" placeholder="我的 MCP 服务" required />
      </label>
      <label>
        传输类型
        <select v-model="form.transport">
          <option value="stdio">stdio</option>
          <option value="sse">SSE</option>
          <option value="http">HTTP</option>
        </select>
      </label>
      <template v-if="form.transport === 'stdio'">
        <label>
          命令
          <input v-model="form.command" placeholder="npx" required />
        </label>
        <label>
          参数（逗号分隔）
          <input v-model="form.args" placeholder="-y, @mcp/server" />
        </label>
        <label>
          环境变量（每行 KEY=VALUE）
          <textarea v-model="form.env" rows="2" />
        </label>
      </template>
      <label v-else>
        URL
        <input v-model="form.url" placeholder="https://..." required />
      </label>
      <label class="mcp-network-option">
        <input v-model="form.requiresNetwork" type="checkbox" />
        此服务需要“联网”许可
        <small>stdio 工具也可能访问互联网，请按工具实际行为选择。</small>
      </label>
      <button type="submit" class="btn-primary" :disabled="loading">确认添加</button>
    </form>

    <p v-if="error" class="inline-error">{{ error }}</p>

    <div v-if="loading && !servers.length" class="empty-note">加载中…</div>
    <div v-else-if="!servers.length" class="empty-note">暂无 MCP 服务，点击"添加服务"开始。</div>

    <ul v-else class="server-list">
      <li v-for="server in servers" :key="server.id" class="server-card">
        <div class="server-info">
          <span class="server-icon">{{ transportIcon[server.transport] }}</span>
          <div>
            <strong>{{ server.name }}</strong>
            <span class="server-meta">
              {{ server.transport }}
              <span :class="['status-badge', server.status]">{{ server.status }}</span>
              · {{ server.tools.length }} 个工具
              · {{ server.requires_network ? '需要联网许可' : '本地工具' }}
            </span>
          </div>
        </div>
        <button class="btn-secondary" @click="toggleNetworkPolicy(server)" :disabled="loading">
          {{ server.requires_network ? '设为本地' : '设为联网' }}
        </button>
        <label class="toggle-switch">
          <input type="checkbox" :checked="server.enabled" @change="toggleServer(server)" />
          <span class="toggle-slider"></span>
        </label>
        <button class="btn-danger" @click="remove(server.id)" :disabled="deletingId === server.id">
          {{ deletingId === server.id ? '删除中…' : '删除' }}
        </button>
      </li>
    </ul>
  </div>
</template>
