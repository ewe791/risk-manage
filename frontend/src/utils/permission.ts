/** 角色与权限（文档 2.3.2）：admin 全权，reviewer 审核/检查，viewer 只读 */
export type Role = 'admin' | 'reviewer' | 'viewer'
export type Action = 'read' | 'check' | 'rule_write' | 'case_review' | 'blacklist_write'

export const ROLE_LABEL: Record<string, string> = {
  admin: '风控管理员',
  reviewer: '风控审核员',
  viewer: '数据查看人'
}

const MATRIX: Record<Action, Role[]> = {
  read: ['admin', 'reviewer', 'viewer'],
  check: ['admin', 'reviewer'],
  rule_write: ['admin'],
  case_review: ['admin', 'reviewer'],
  blacklist_write: ['admin']
}

export function can(role: string | undefined | null, action: Action): boolean {
  if (!role) return false
  return MATRIX[action].includes(role as Role)
}
