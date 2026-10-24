import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { agentApi } from '@/api'
import type { Card, ChatMessage, Conversation } from '@/types'

export const useChatStore = defineStore('chat', () => {
  const conversations = ref<Conversation[]>([])
  const messages = ref<ChatMessage[]>([])
  const activeId = ref<string>('')
  const loading = ref(false)
  const backend = ref('memory')
  const loadingConversation = ref(false)

  /** 右侧结果卡片区：按评估/案件去重，最新的排前面 */
  const cards = computed<Card[]>(() => {
    const seen = new Set<string>()
    const result: Card[] = []
    for (let i = messages.value.length - 1; i >= 0; i -= 1) {
      const card = messages.value[i].card
      if (!card) continue
      const data = card.data || {}
      // 评分卡按评估去重（93 与 63 是两次评估，都要留）；
      // 列表类卡片按类型去重，只保留最新一份，避免右侧面板越堆越多
      const key =
        card.type === 'risk_score'
          ? data.assessment_id || `risk-${i}`
          : card.type === 'case_review'
            ? data.case_id || `review-${i}`
            : card.type
      if (seen.has(key)) continue
      seen.add(key)
      result.push(card)
    }
    return result.slice(0, 8)
  })

  async function loadConversations() {
    try {
      const data = await agentApi.conversations()
      conversations.value = data.items || []
      backend.value = data.backend || 'memory'
    } catch {
      conversations.value = []
    }
  }

  function newConversation() {
    activeId.value = ''
    messages.value = []
  }

  async function openConversation(id: string) {
    if (!id || id === activeId.value) return
    loadingConversation.value = true
    try {
      const data = await agentApi.messages(id)
      activeId.value = id
      messages.value = data.messages || []
    } finally {
      loadingConversation.value = false
    }
  }

  async function send(text: string) {
    const content = text.trim()
    if (!content || loading.value) return
    const now = new Date().toISOString()
    messages.value.push({ role: 'user', content, ts: now })
    loading.value = true
    try {
      const data = await agentApi.chat(content, activeId.value || null)
      activeId.value = data.conversation_id
      // 服务端返回的首条是刚提交的用户消息，避免重复渲染
      const incoming = (data.messages || []).filter(
        (m, idx) => !(idx === 0 && m.role === 'user' && m.content === content)
      )
      messages.value.push(...incoming)
      await loadConversations()
    } catch (error: any) {
      messages.value.push({
        role: 'assistant',
        content: `⚠️ 请求失败：${error?.message || '未知错误'}`,
        type: 'error',
        ts: new Date().toISOString()
      })
    } finally {
      loading.value = false
    }
  }

  return {
    conversations,
    messages,
    activeId,
    loading,
    backend,
    loadingConversation,
    cards,
    loadConversations,
    newConversation,
    openConversation,
    send
  }
})
