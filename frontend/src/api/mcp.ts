import { api } from './chat'

export interface McpServerInfo {
  id: number
  name: string
  transport: 'stdio' | 'sse' | 'http'
  command: string | null
  args: string[]
  url: string | null
  header_keys: string[]
  env_keys: string[]
  status: 'connected' | 'disconnected'
  enabled: boolean
  requires_network: boolean
  last_error: string | null
  tools: Array<{ name: string; description?: string }>
  created_at: string
  updated_at: string
}

export interface McpServerCreate {
  name: string
  transport: 'stdio' | 'sse' | 'http'
  command?: string
  args?: string[]
  url?: string
  headers?: Record<string, string>
  env?: Record<string, string>
  requires_network?: boolean
}

export async function getMcpServers(): Promise<McpServerInfo[]> {
  const response = await api.get<{ servers: McpServerInfo[] }>('/mcp/servers')
  return response.data.servers
}

export async function addMcpServer(data: McpServerCreate): Promise<McpServerInfo> {
  const response = await api.post<McpServerInfo>('/mcp/servers', data)
  return response.data
}

export async function deleteMcpServer(id: number): Promise<void> {
  await api.delete(`/mcp/servers/${id}`)
}

export async function enableMcpServer(id: number): Promise<void> {
  await api.post(`/mcp/servers/${id}/enable`)
}

export async function disableMcpServer(id: number): Promise<void> {
  await api.post(`/mcp/servers/${id}/disable`)
}

export async function updateMcpNetworkPolicy(
  id: number,
  requiresNetwork: boolean,
): Promise<McpServerInfo> {
  const response = await api.patch<McpServerInfo>(`/mcp/servers/${id}`, {
    requires_network: requiresNetwork,
  })
  return response.data
}
