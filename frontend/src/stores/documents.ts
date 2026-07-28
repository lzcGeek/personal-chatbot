import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { isDocumentJobActive } from '../document-status'

import {
  buildDocumentGraph,
  deleteDocument,
  getDocuments,
  rebuildDocumentGraph,
  retryDocument,
  uploadDocument,
  type DocumentInfo,
  type GraphMode,
} from '../api/documents'


export const useDocumentStore = defineStore('documents', () => {
  const documents = ref<DocumentInfo[]>([])
  const loading = ref(false)
  const uploading = ref(false)
  const error = ref('')
  const hasActiveJobs = computed(() =>
    documents.value.some(isDocumentJobActive),
  )

  async function load(silent = false): Promise<void> {
    if (!silent) loading.value = true
    try {
      documents.value = await getDocuments()
      error.value = ''
    } catch (reason) {
      error.value = errorMessage(reason, '知识库加载失败')
    } finally {
      if (!silent) loading.value = false
    }
  }

  async function upload(file: File, graphMode: GraphMode = 'inherit'): Promise<void> {
    uploading.value = true
    error.value = ''
    try {
      const item = await uploadDocument(file, graphMode)
      documents.value.unshift(item)
    } catch (reason) {
      error.value = errorMessage(reason, '上传失败')
    } finally {
      uploading.value = false
    }
  }

  async function buildGraph(id: string, rebuild = false): Promise<void> {
    try {
      const updated = rebuild
        ? await rebuildDocumentGraph(id)
        : await buildDocumentGraph(id)
      replace(updated)
      error.value = ''
    } catch (reason) {
      error.value = errorMessage(reason, rebuild ? '重建图谱失败' : '构建图谱失败')
    }
  }

  async function retry(id: string): Promise<void> {
    try {
      const updated = await retryDocument(id)
      replace(updated)
      error.value = ''
    } catch (reason) {
      error.value = errorMessage(reason, '重试失败')
    }
  }

  async function remove(id: string): Promise<void> {
    try {
      await deleteDocument(id)
      const item = documents.value.find(document => document.id === id)
      if (item) item.status = 'deleting'
      error.value = ''
    } catch (reason) {
      error.value = errorMessage(reason, '删除失败')
    }
  }

  function replace(updated: DocumentInfo): void {
    const index = documents.value.findIndex(item => item.id === updated.id)
    if (index === -1) documents.value.unshift(updated)
    else documents.value[index] = updated
  }

  return {
    documents,
    loading,
    uploading,
    error,
    hasActiveJobs,
    load,
    upload,
    retry,
    buildGraph,
    remove,
  }
})


function errorMessage(reason: unknown, fallback: string): string {
  if (reason && typeof reason === 'object' && 'response' in reason) {
    const response = (reason as { response?: { data?: { detail?: string } } }).response
    if (typeof response?.data?.detail === 'string') return response.data.detail
  }
  return reason instanceof Error ? reason.message : fallback
}
