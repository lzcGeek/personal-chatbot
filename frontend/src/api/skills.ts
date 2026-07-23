import { api } from './chat'

export interface SkillInfo {
  name: string
  description: string
  content: string
  path: string
  status: string
  enabled: boolean
}

export interface SkillCreate {
  name: string
  description: string
  content: string
}

export async function getSkills(): Promise<SkillInfo[]> {
  const response = await api.get<{ skills: SkillInfo[] }>('/skills')
  return response.data.skills
}

export async function createSkill(data: SkillCreate): Promise<SkillInfo> {
  const response = await api.post<SkillInfo>('/skills', data)
  return response.data
}

export async function uploadSkill(file: File): Promise<SkillInfo> {
  const form = new FormData()
  form.append('file', file)
  const response = await api.post<SkillInfo>('/skills/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return response.data
}

export async function reloadSkills(): Promise<SkillInfo[]> {
  const response = await api.post<{ skills: SkillInfo[] }>('/skills/reload')
  return response.data.skills
}

export async function enableSkill(name: string): Promise<void> {
  await api.post(`/skills/${encodeURIComponent(name)}/enable`)
}

export async function disableSkill(name: string): Promise<void> {
  await api.post(`/skills/${encodeURIComponent(name)}/disable`)
}
