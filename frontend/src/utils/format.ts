import { marked } from 'marked'
import DOMPurify from 'dompurify'

marked.setOptions({ breaks: true, gfm: true })

/** 渲染 LLM 的 Markdown 输出（先 sanitize，避免模型输出注入 HTML） */
export function renderMarkdown(text: string): string {
  if (!text) return ''
  const html = marked.parse(text, { async: false }) as string
  return DOMPurify.sanitize(html, { ADD_ATTR: ['target'] })
}

export const LEVEL_LABEL: Record<string, string> = {
  high: '高风险',
  medium: '中风险',
  low: '低风险'
}

export const DECISION_LABEL: Record<string, string> = {
  reject: '拒绝交易',
  manual_review: '人工复核',
  pass: '建议放行'
}

export const CASE_STATUS_LABEL: Record<string, string> = {
  pending: '待审核',
  reviewing: '复核中',
  approved: '已通过',
  rejected: '已驳回',
  resolved: '已结案'
}

export const EVENT_TYPE_LABEL: Record<string, string> = {
  order_create: '下单',
  order_pay: '支付',
  after_sale_apply: '售后申请',
  logistics_complaint: '物流投诉'
}

export const BLACKLIST_TYPE_LABEL: Record<string, string> = {
  user: '用户',
  address: '地址',
  ip: 'IP',
  device: '设备'
}

/** 25 个特征的中文名与分组（顺序与后端 FEATURE_NAMES 一致） */
export const FEATURE_META: Array<{ key: string; label: string; group: string }> = [
  { key: 'user_order_count_30d', label: '30天订单数', group: '用户维度' },
  { key: 'user_refund_count_30d', label: '30天退款数', group: '用户维度' },
  { key: 'user_complaint_count_30d', label: '30天投诉数', group: '用户维度' },
  { key: 'user_reg_days', label: '注册天数', group: '用户维度' },
  { key: 'user_address_count', label: '地址数', group: '用户维度' },
  { key: 'user_risk_event_count_30d', label: '30天风险事件数', group: '用户维度' },
  { key: 'user_blacklist_hit', label: '用户命中黑名单', group: '用户维度' },
  { key: 'user_avg_order_amount', label: '平均订单金额', group: '用户维度' },
  { key: 'user_refund_rate', label: '退款率', group: '用户维度' },
  { key: 'user_case_count', label: '历史案件数', group: '用户维度' },
  { key: 'order_amount', label: '订单金额', group: '订单维度' },
  { key: 'order_category_risk_score', label: '品类风险分', group: '订单维度' },
  { key: 'order_pay_method', label: '支付方式', group: '订单维度' },
  { key: 'order_hour', label: '下单小时', group: '订单维度' },
  { key: 'order_is_weekend', label: '周末下单', group: '订单维度' },
  { key: 'order_item_count', label: '商品件数', group: '订单维度' },
  { key: 'order_discount_rate', label: '折扣率', group: '订单维度' },
  { key: 'order_is_new_user', label: '是否新用户', group: '订单维度' },
  { key: 'order_device_risk', label: '设备风险分', group: '订单维度' },
  { key: 'order_ip_risk', label: 'IP 风险分', group: '订单维度' },
  { key: 'address_change_count_90d', label: '90天地址变更数', group: '地址维度' },
  { key: 'address_user_count', label: '地址共用账号数', group: '地址维度' },
  { key: 'address_in_blacklist', label: '地址在黑名单', group: '地址维度' },
  { key: 'address_ip_consistency', label: '地址IP一致性', group: '地址维度' },
  { key: 'address_distance_from_history', label: '距历史地址(km)', group: '地址维度' }
]

export function formatValue(value: any): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(4).replace(/0+$/, '').replace(/\.$/, '')
  return String(value)
}

export function formatTime(value?: string): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(
    date.getMinutes()
  )}`
}

export function scoreColor(score: number): string {
  if (score >= 70) return '#dc2626'
  if (score >= 40) return '#d97706'
  return '#15803d'
}
