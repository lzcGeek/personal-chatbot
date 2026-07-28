import { api } from './chat'

export interface MediaCapabilities {
  image: { enabled: boolean; profiles: string[] }
  tts: { enabled: boolean; profiles: string[] }
  limits: { max_response_bytes: number; max_tasks_per_message: number }
}

export interface MediaTaskInfo {
  id: string
  message_id: number
  kind: 'image' | 'tts'
  profile_id: string
  status: 'pending' | 'processing' | 'complete' | 'failed'
  attempts: number
  error_code: string | null
  error_message: string | null
}

export interface MessageAttachment {
  id: string
  message_id: number
  task_id: string
  kind: 'image' | 'tts'
  mime_type: string
  byte_size: number
  provider_id: string
  profile_id: string
  download_url: string
  created_at: string
}

let capabilityPromise: Promise<MediaCapabilities> | null = null

export function getMediaCapabilities(): Promise<MediaCapabilities> {
  if (!capabilityPromise) {
    capabilityPromise = api.get<MediaCapabilities>('/media/capabilities').then(response => response.data)
  }
  return capabilityPromise
}

export async function createMediaTask(messageId: number, kind: 'image' | 'tts'): Promise<MediaTaskInfo> {
  const response = await api.post<MediaTaskInfo>(`/media/messages/${messageId}/${kind}`, {
    idempotency_key: crypto.randomUUID(),
  })
  return response.data
}

export async function getMediaTask(id: string): Promise<MediaTaskInfo> {
  const response = await api.get<MediaTaskInfo>(`/media/tasks/${id}`)
  return response.data
}

export async function retryMediaTask(id: string): Promise<MediaTaskInfo> {
  const response = await api.post<MediaTaskInfo>(`/media/tasks/${id}/retry`)
  return response.data
}

export async function getMessageAttachments(messageId: number): Promise<MessageAttachment[]> {
  const response = await api.get<{ attachments: MessageAttachment[] }>(
    `/media/messages/${messageId}/attachments`,
  )
  return response.data.attachments
}

export async function waitForMediaTask(id: string): Promise<MediaTaskInfo> {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    const task = await getMediaTask(id)
    if (task.status === 'complete' || task.status === 'failed') return task
    await new Promise(resolve => window.setTimeout(resolve, 500))
  }
  throw new Error('媒体生成超时，请稍后刷新')
}
