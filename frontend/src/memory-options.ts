export type MemoryValidity = 'active' | 'invalid' | 'historical' | 'superseded' | 'pending_confirmation' | string

export function memoryScopeLabel(scope: string): string {
  if (scope === 'character_private') return '角色私有'
  if (scope === 'conversation_shared') return '会话共享'
  if (scope === 'user') return '用户长期'
  return scope
}

export function memoryValidityLabel(validity: MemoryValidity): string {
  const labels: Record<string, string> = {
    active: '当前有效',
    invalid: '已失效',
    historical: '历史版本',
    superseded: '已被替代',
    pending_confirmation: '待确认',
  }
  return labels[validity] ?? validity
}

export function memoryActions(validity: MemoryValidity, supersededById: string | null): string[] {
  if (validity === 'pending_confirmation') return ['confirm', 'invalidate', 'delete']
  if (validity === 'invalid' && !supersededById) return ['restore', 'delete']
  if (validity === 'active') return ['invalidate', 'delete']
  return ['delete']
}
