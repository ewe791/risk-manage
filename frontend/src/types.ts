export type RiskLevel = 'high' | 'medium' | 'low'
export type Decision = 'reject' | 'manual_review' | 'pass'

export interface RuleHit {
  rule_id?: string
  rule_code?: string
  rule_name?: string
  hit_score: number
  hit_message: string
}

export interface RiskResult {
  assessment_id: string
  event_id?: string
  risk_score: number
  risk_level: RiskLevel
  decision: Decision
  hit_count?: number
  rule_hits: RuleHit[]
  feature_snapshot: Record<string, any>
  case_id?: string | null
  case_status?: string | null
  user_id?: string
  order_id?: string
  event_type?: string
  created_at?: string
}

export interface RiskCase {
  case_id: string
  assessment_id: string
  user_id: string
  order_id?: string
  case_status: 'pending' | 'reviewing' | 'approved' | 'rejected' | 'resolved'
  review_result?: string | null
  reviewer_id?: string | null
  risk_score?: number | null
  risk_level?: RiskLevel | null
  decision?: string | null
  created_at?: string
  updated_at?: string
  review_logs?: ReviewLog[]
  rule_hits?: RuleHit[]
  feature_snapshot?: Record<string, any>
  event_id?: string | null
  resolved_at?: string | null
}

export interface ReviewLog {
  log_id: string
  operator_id: string
  action_type: string
  action_remark: string
  created_at: string
}

export interface RiskRule {
  rule_id: string
  rule_code: string
  rule_name: string
  rule_status: 'enabled' | 'disabled'
  priority: number
  score: number
  condition_json: any
  description?: string
  updated_at?: string
  hit_count?: number
  last_hit_at?: string | null
}

export interface BlacklistItem {
  blacklist_id: string
  blacklist_type: 'user' | 'address' | 'ip' | 'device'
  blacklist_value: string
  remark?: string
  status: string
  created_at?: string
}

export interface Card {
  type: 'risk_score' | 'case_list' | 'case_review' | 'dashboard' | 'profile' | 'rule_list' | 'blacklist'
  data: any
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'tool' | 'system'
  content: string
  tool_calls?: Array<{ id: string; type: string; function: { name: string; arguments: string } }>
  tool_call_id?: string
  name?: string
  args?: Record<string, any>
  ok?: boolean
  card?: Card | null
  ts?: string
  type?: string
}

export interface Conversation {
  conversation_id: string
  title: string
  message_count: number
  updated_at?: string
}

export interface Paged<T> {
  items: T[]
  total: number
  page?: number
  page_size?: number
}
