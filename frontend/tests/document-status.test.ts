import assert from 'node:assert/strict'
import test from 'node:test'

import type { DocumentInfo } from '../src/api/documents.ts'
import { documentStatusLabel, isDocumentJobActive } from '../src/document-status.ts'


function document(overrides: Partial<DocumentInfo>): DocumentInfo {
  return {
    id: 'document-1',
    filename: 'notes.md',
    media_type: 'text/markdown',
    byte_size: 10,
    status: 'ready',
    processing_phase: 'ready',
    graph_mode: 'inherit',
    graph_status: 'ready',
    error_message: null,
    created_at: '2026-07-27T00:00:00Z',
    updated_at: '2026-07-27T00:00:00Z',
    ...overrides,
  }
}

test('keeps polling after text becomes searchable while graph work is active', () => {
  const queued = document({ graph_status: 'queued' })
  const processing = document({ graph_status: 'processing' })

  assert.equal(isDocumentJobActive(queued), true)
  assert.equal(isDocumentJobActive(processing), true)
  assert.equal(documentStatusLabel(queued), '文本可检索 · 图谱排队中')
  assert.equal(documentStatusLabel(processing), '文本可检索 · 图谱处理中')
})

test('shows each persisted deletion phase', () => {
  assert.equal(
    documentStatusLabel(document({ status: 'deleting', processing_phase: 'deleting' })),
    '等待删除',
  )
  assert.equal(
    documentStatusLabel(document({ status: 'deleting', processing_phase: 'deleting_vectors' })),
    '删除中 · 清理向量',
  )
  assert.equal(
    documentStatusLabel(document({ status: 'deleting', processing_phase: 'deleting_graph' })),
    '删除中 · 清理图谱',
  )
  assert.equal(
    documentStatusLabel(document({ status: 'deleting', processing_phase: 'deleting_file' })),
    '删除中 · 清理文件',
  )
})

test('stops polling for terminal graph states and exposes retryable deletion failure', () => {
  assert.equal(isDocumentJobActive(document({ graph_status: 'ready' })), false)
  assert.equal(isDocumentJobActive(document({ graph_status: 'failed' })), false)
  assert.equal(
    documentStatusLabel(document({ status: 'failed', processing_phase: 'delete_failed' })),
    '删除失败 · 可重试',
  )
})

test('distinguishes skipped and unavailable graph enhancement from text readiness', () => {
  assert.equal(
    documentStatusLabel(document({ graph_mode: 'disabled', graph_status: 'skipped' })),
    '文本可检索 · 已跳过图谱',
  )
  assert.equal(
    documentStatusLabel(document({ graph_mode: 'enabled', graph_status: 'unavailable' })),
    '文本可检索 · 图谱服务不可用',
  )
  assert.equal(isDocumentJobActive(document({ graph_status: 'skipped' })), false)
  assert.equal(isDocumentJobActive(document({ graph_status: 'unavailable' })), false)
})
