import type { DocumentInfo } from './api/documents'


export function isDocumentJobActive(item: DocumentInfo): boolean {
  return (
    ['uploaded', 'processing', 'deleting'].includes(item.status) ||
    ['pending', 'queued', 'processing'].includes(item.graph_status)
  )
}

export function documentStatusLabel(item: DocumentInfo): string {
  if (item.status === 'ready') {
    if (item.graph_status === 'ready') return '可检索 · 图谱完成'
    if (item.graph_status === 'failed') return '文本可检索 · 图谱失败'
    if (item.graph_status === 'processing') return '文本可检索 · 图谱处理中'
    if (item.graph_status === 'queued' || item.graph_status === 'pending') {
      return '文本可检索 · 图谱排队中'
    }
    if (item.graph_status === 'disabled') return '文本可检索 · 图谱未启用'
    if (item.graph_status === 'skipped') return '文本可检索 · 已跳过图谱'
    if (item.graph_status === 'unavailable') return '文本可检索 · 图谱服务不可用'
    return '文本可检索 · 图谱状态未知'
  }
  if (item.status === 'failed') {
    if (item.processing_phase === 'delete_failed') return '删除失败 · 可重试'
    return '处理失败 · 可重试'
  }
  const phases: Record<string, string> = {
    uploaded: '等待处理',
    parsing: '解析中',
    chunking: '分块中',
    embedding: '向量化中',
    indexing: '建立索引中',
    deleting: '等待删除',
    deleting_vectors: '删除中 · 清理向量',
    deleting_graph: '删除中 · 清理图谱',
    deleting_file: '删除中 · 清理文件',
  }
  return phases[item.processing_phase] || '处理中'
}
