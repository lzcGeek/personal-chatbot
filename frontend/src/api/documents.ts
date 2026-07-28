import { api } from './chat'


export interface DocumentInfo {
  id: string
  filename: string
  media_type: string
  byte_size: number
  status: 'uploaded' | 'processing' | 'ready' | 'failed' | 'deleting' | string
  processing_phase: string
  graph_mode: GraphMode
  graph_status: string
  error_message: string | null
  created_at: string
  updated_at: string
}

export type GraphMode = 'inherit' | 'enabled' | 'disabled'

export async function getDocuments(): Promise<DocumentInfo[]> {
  const response = await api.get<DocumentInfo[]>('/documents')
  return response.data
}

export async function uploadDocument(file: File, graphMode: GraphMode = 'inherit'): Promise<DocumentInfo> {
  const body = new FormData()
  body.append('file', file)
  body.append('graph_mode', graphMode)
  const response = await api.post<DocumentInfo>('/documents', body)
  return response.data
}

export async function buildDocumentGraph(id: string): Promise<DocumentInfo> {
  const response = await api.post<DocumentInfo>(`/documents/${id}/graph/build`)
  return response.data
}

export async function rebuildDocumentGraph(id: string): Promise<DocumentInfo> {
  const response = await api.post<DocumentInfo>(`/documents/${id}/graph/rebuild`)
  return response.data
}

export async function retryDocument(id: string): Promise<DocumentInfo> {
  const response = await api.post<DocumentInfo>(`/documents/${id}/retry`)
  return response.data
}

export async function deleteDocument(id: string): Promise<void> {
  await api.delete(`/documents/${id}`)
}
