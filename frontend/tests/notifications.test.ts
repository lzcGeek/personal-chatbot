import assert from 'node:assert/strict'
import test from 'node:test'

import {
  clearNotifications,
  dismissNotification,
  errorText,
  notifications,
  notify,
} from '../src/notifications.ts'

test('notifications expose success, error and dismiss behavior', () => {
  clearNotifications()
  const successId = notify('保存成功', 'success', 0)
  notify('保存失败', 'error', 0)

  assert.deepEqual(
    notifications.value.map(item => [item.kind, item.message]),
    [['success', '保存成功'], ['error', '保存失败']],
  )

  dismissNotification(successId)
  assert.deepEqual(notifications.value.map(item => item.message), ['保存失败'])
  clearNotifications()
})

test('error text prefers API detail and otherwise uses a safe fallback', () => {
  assert.equal(errorText({ response: { data: { detail: '名称已存在' } } }, '操作失败'), '名称已存在')
  assert.equal(errorText({ token: 'secret' }, '操作失败'), '操作失败')
})
