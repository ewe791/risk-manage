import http from './client'
import type {
  BlacklistItem,
  ChatMessage,
  Conversation,
  Paged,
  RiskCase,
  RiskResult,
  RiskRule
} from '@/types'

export interface LoginResult {
  operator_id: string
  username: string
  role: string
  access_token: string
  expires_in: number
}

export const authApi = {
  login: (username: string, password: string) =>
    http.post<any, LoginResult>('/auth/login', { username, password }),
  me: () => http.get<any, { operator_id: string; username: string; role: string }>('/auth/me')
}

export const agentApi = {
  chat: (message: string, conversation_id?: string | null) =>
    http.post<any, { conversation_id: string; messages: ChatMessage[]; type: string; steps: number }>(
      '/agent/chat',
      { message, conversation_id: conversation_id || null }
    ),
  conversations: () => http.get<any, { items: Conversation[]; backend: string }>('/agent/conversations'),
  messages: (id: string) =>
    http.get<any, { conversation_id: string; messages: ChatMessage[]; context: any }>(
      `/agent/conversations/${id}/messages`
    ),
  toolLogs: (conversationId?: string) =>
    http.get<any, { items: any[] }>('/agent/tool-logs', { params: { conversation_id: conversationId, limit: 100 } })
}

export const riskApi = {
  check: (payload: { event_type: string; source_id?: string; user_id: string; order_id?: string }) =>
    http.post<any, RiskResult>('/risk/check', payload),
  assessment: (id: string) => http.get<any, any>(`/risk/assessments/${id}`),

  listRules: (params: Record<string, any> = {}) => http.get<any, Paged<RiskRule>>('/risk/rules', { params }),
  createRule: (payload: Partial<RiskRule>) => http.post<any, RiskRule>('/risk/rules', payload),
  updateRule: (payload: Partial<RiskRule> & { rule_id: string }) =>
    http.post<any, RiskRule>('/risk/rules/update', payload),
  setRuleStatus: (rule_id: string, target_status: 'enabled' | 'disabled') =>
    http.post<any, RiskRule>('/risk/rules/status', { rule_id, target_status }),
  deleteRule: (rule_id: string) => http.post<any, any>('/risk/rules/delete', { rule_id }),

  listCases: (params: Record<string, any> = {}) => http.get<any, Paged<RiskCase>>('/risk/cases', { params }),
  getCase: (id: string) => http.get<any, RiskCase>(`/risk/cases/${id}`),
  reviewCase: (payload: { case_id: string; review_result: string; review_remark: string }) =>
    http.post<any, any>('/risk/cases/review', payload),
  resolveCase: (payload: { case_id: string; resolve_remark: string }) =>
    http.post<any, any>('/risk/cases/resolve', payload),

  listBlacklists: (params: Record<string, any> = {}) =>
    http.get<any, Paged<BlacklistItem>>('/risk/blacklists', { params }),
  addBlacklist: (payload: Partial<BlacklistItem>) => http.post<any, BlacklistItem>('/risk/blacklists', payload),
  deleteBlacklist: (blacklist_id: string) =>
    http.post<any, any>('/risk/blacklists/delete', { blacklist_id }),
  importBlacklists: (payload: { text?: string; items?: any[] }) =>
    http.post<any, any>('/risk/blacklists/import', payload),

  profile: (userId: string) => http.get<any, any>(`/risk/users/${userId}/profile`),
  dashboard: (days = 7) => http.get<any, any>('/risk/dashboard', { params: { days } })
}
