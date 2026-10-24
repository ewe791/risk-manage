<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useChatStore } from '@/stores/chat'
import ToolCallBlock from '@/components/ToolCallBlock.vue'
import CardRenderer from '@/components/CardRenderer.vue'
import SvgIcon from '@/components/SvgIcon.vue'
import { CASE_STATUS_LABEL, renderMarkdown } from '@/utils/format'

const chat = useChatStore()
const input = ref('')
const scrollEl = ref<HTMLElement | null>(null)

const EXAMPLES = [
  { title: '高风险订单检查', text: '支付环节做一次风控检查：用户 U1001，订单 O2001' },
  { title: '停规则看差异', text: 'R05 这条规则先停掉，然后把刚才那个订单重新查一遍，告诉我分数变化' },
  { title: '看板与待审案件', text: '看一下风控看板，再把待审核的案件列出来' },
  { title: '用户画像', text: '查一下这个用户的画像和最近的风险事件' }
]

const visibleMessages = computed(() =>
  chat.messages.filter((m) => {
    if (m.role === 'system') return false
    if (m.role === 'assistant' && m.tool_calls && !m.content) return false
    return true
  })
)

const canSend = computed(() => input.value.trim().length > 0 && !chat.loading)

function scrollToBottom() {
  nextTick(() => {
    if (scrollEl.value) scrollEl.value.scrollTop = scrollEl.value.scrollHeight
  })
}

watch(() => [chat.messages.length, chat.loading], scrollToBottom)

onMounted(async () => {
  await chat.loadConversations()
  scrollToBottom()
})

async function submit(text?: string) {
  const payload = (text ?? input.value).trim()
  if (!payload || chat.loading) return
  input.value = ''
  await chat.send(payload)
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    submit()
  }
}

function patchReviewed(payload: any) {
  chat.messages.forEach((message) => {
    const items = message.card?.data?.items
    if (!Array.isArray(items)) return
    items.forEach((item: any) => {
      if (item.case_id === payload.case_id) {
        item.case_status = payload.case_status
        item.review_result = payload.review_result
        item.reviewer_id = payload.reviewer_id
      }
    })
  })
  ElMessage.success(`案件已${CASE_STATUS_LABEL[payload.case_status] || '更新'}`)
}

function timeLabel(ts?: string) {
  if (!ts) return ''
  const date = new Date(ts)
  if (Number.isNaN(date.getTime())) return ''
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}
</script>

<template>
  <div class="wb">
    <!-- 左：会话列表 -->
    <aside class="convs">
      <button class="new-btn" type="button" @click="chat.newConversation()">
        <SvgIcon name="plus" :size="15" /> 新建会话
      </button>

      <div class="conv-label">最近会话</div>
      <div class="conv-list">
        <button
          v-for="conv in chat.conversations"
          :key="conv.conversation_id"
          type="button"
          class="conv"
          :class="{ on: conv.conversation_id === chat.activeId }"
          @click="chat.openConversation(conv.conversation_id)"
        >
          <span class="conv-title">{{ conv.title || '新会话' }}</span>
          <span class="conv-meta">{{ conv.message_count }} 条</span>
        </button>
        <p v-if="!chat.conversations.length" class="conv-empty">还没有会话记录，右侧直接开始提问即可。</p>
      </div>

      <div class="conv-foot">
        会话存储：{{ chat.backend === 'redis' ? 'Redis' : '进程内缓存' }}
      </div>
    </aside>

    <!-- 中：消息流 -->
    <section class="stream">
      <header class="stream-head">
        <div>
          <h2>对话工作台</h2>
          <p>用自然语言完成 查风险 / 停规则 / 审案件 / 看画像，所有结论来自工具调用</p>
        </div>
        <div class="head-right">
          <span class="model mono">deepseek-flash</span>
        </div>
      </header>

      <div ref="scrollEl" class="messages">
        <div v-if="!visibleMessages.length && !chat.loading" class="welcome">
          <div class="welcome-mark"><SvgIcon name="spark" :size="22" /></div>
          <h3>今天想核查哪一笔交易？</h3>
          <p>可以直接说「支付环节查一下 U1001 的 O2001」，也可以让我先列规则再停用某条后重查对比。</p>
          <div class="examples">
            <button
              v-for="example in EXAMPLES"
              :key="example.title"
              type="button"
              class="example"
              @click="submit(example.text)"
            >
              <strong>{{ example.title }}</strong>
              <span>{{ example.text }}</span>
            </button>
          </div>
        </div>

        <template v-for="(message, index) in visibleMessages" :key="index">
          <!-- 用户 -->
          <div v-if="message.role === 'user'" class="msg user">
            <div class="bubble user-bubble">{{ message.content }}</div>
            <span class="stamp">{{ timeLabel(message.ts) }}</span>
          </div>

          <!-- 工具调用 -->
          <div v-else-if="message.role === 'tool'" class="msg tool-msg">
            <ToolCallBlock :message="message" />
            <CardRenderer
              v-if="message.card"
              :card="message.card"
              dense
              @reviewed="patchReviewed"
            />
          </div>

          <!-- 助手文本 -->
          <div v-else class="msg assistant">
            <div class="avatar"><SvgIcon name="shield" :size="14" /></div>
            <div class="bubble-wrap">
              <div v-if="message.type === 'error'" class="bubble error-bubble">{{ message.content }}</div>
              <div v-else class="bubble md-body" v-html="renderMarkdown(message.content)" />
              <span class="stamp">{{ timeLabel(message.ts) }}</span>
            </div>
          </div>
        </template>

        <div v-if="chat.loading" class="msg assistant">
          <div class="avatar"><SvgIcon name="shield" :size="14" /></div>
          <div class="bubble thinking">
            <span class="dot" /><span class="dot" /><span class="dot" />
            <em>模型思考中：解析诉求 → 调用工具 → 汇总结论</em>
          </div>
        </div>
      </div>

      <footer class="composer">
        <textarea
          v-model="input"
          rows="1"
          placeholder="描述你的诉求，例如：支付环节查一下用户 U1001 的订单 O2001"
          @keydown="onKeydown"
        />
        <button class="send" :disabled="!canSend" type="button" @click="submit()">
          <SvgIcon name="send" :size="16" />
        </button>
        <div class="tip">Enter 发送 / Shift + Enter 换行 · 工具调用与参数全程留痕</div>
      </footer>
    </section>

    <!-- 右：结果卡片区 -->
    <aside class="cards">
      <div class="cards-head">
        <span>结果卡片</span>
        <span class="muted">{{ chat.cards.length }} 张</span>
      </div>
      <div class="cards-body">
        <template v-if="chat.cards.length">
          <CardRenderer
            v-for="(card, index) in chat.cards"
            :key="index"
            :card="card"
            dense
            @reviewed="patchReviewed"
          />
        </template>
        <div v-else class="cards-empty">
          <SvgIcon name="chart" :size="22" />
          <p>发起一次风险检查后，评分环、命中规则、特征快照会固定在这里，方便对照。</p>
        </div>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.wb {
  display: grid;
  grid-template-columns: 232px minmax(0, 1fr) 348px;
  height: 100vh;
  overflow: hidden;
}

/* ---------- 左 ---------- */
.convs {
  border-right: 1px solid var(--border);
  background: #fbfcfe;
  display: flex;
  flex-direction: column;
  padding: 14px 12px;
  min-height: 0;
}
.new-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 34px;
  border-radius: 9px;
  border: 1px solid var(--border);
  background: #fff;
  color: var(--text);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.new-btn:hover {
  border-color: #c3d2f5;
  color: var(--primary);
  background: #f8faff;
}
.conv-label {
  font-size: 11px;
  color: var(--text-dim);
  margin: 16px 4px 8px;
  letter-spacing: 0.4px;
}
.conv-list {
  flex: 1;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.conv {
  text-align: left;
  border: none;
  background: none;
  border-radius: 8px;
  padding: 8px 9px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.conv:hover {
  background: #f1f5fb;
}
.conv.on {
  background: var(--primary-soft);
}
.conv-title {
  font-size: 12.5px;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 190px;
}
.conv-meta {
  font-size: 10.5px;
  color: var(--text-dim);
}
.conv-empty {
  font-size: 11.5px;
  color: var(--text-dim);
  line-height: 1.6;
  padding: 0 4px;
}
.conv-foot {
  border-top: 1px solid var(--border);
  padding-top: 9px;
  font-size: 10.5px;
  color: var(--text-dim);
}

/* ---------- 中 ---------- */
.stream {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  background: var(--bg);
}
.stream-head {
  padding: 15px 24px 12px;
  border-bottom: 1px solid var(--border);
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.stream-head h2 {
  margin: 0;
  font-size: 16px;
  letter-spacing: -0.2px;
}
.stream-head p {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-dim);
}
.model {
  font-size: 11px;
  color: var(--primary);
  background: var(--primary-soft);
  padding: 3px 9px;
  border-radius: 999px;
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 18px 24px 8px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
}

.msg {
  display: flex;
  gap: 8px;
  max-width: 100%;
}
.msg.user {
  justify-content: flex-end;
  align-items: flex-end;
}

.bubble {
  border-radius: 12px;
  padding: 9px 12px;
  font-size: 13.5px;
  line-height: 1.68;
  max-width: 680px;
}
.user-bubble {
  background: linear-gradient(135deg, #2563eb, #3b5bdb);
  color: #fff;
  border-bottom-right-radius: 4px;
  box-shadow: 0 6px 16px rgba(37, 99, 235, 0.18);
}
.assistant .bubble,
.thinking {
  background: #fff;
  border: 1px solid var(--border);
  border-bottom-left-radius: 4px;
  box-shadow: var(--shadow-sm);
  color: var(--text);
}
.error-bubble {
  background: var(--high-soft);
  border: 1px solid #f5c2c2;
  color: #b91c1c;
}
.avatar {
  width: 26px;
  height: 26px;
  border-radius: 8px;
  background: linear-gradient(135deg, #2563eb, #4f46e5);
  color: #fff;
  display: grid;
  place-items: center;
  flex: 0 0 26px;
  margin-top: 2px;
}
.bubble-wrap {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.stamp {
  font-size: 10px;
  color: var(--text-dim);
  padding: 0 2px;
}
.msg.user .stamp {
  padding-bottom: 2px;
}

.tool-msg {
  flex-direction: column;
  gap: 8px;
  margin-left: 34px;
  max-width: 680px;
}

.thinking {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12.5px;
  color: var(--text-sub);
}
.thinking em {
  font-style: normal;
  margin-left: 4px;
}
.dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #94a3b8;
  animation: bounce 1.1s infinite;
}
.dot:nth-child(2) {
  animation-delay: 0.15s;
}
.dot:nth-child(3) {
  animation-delay: 0.3s;
}
@keyframes bounce {
  0%,
  60%,
  100% {
    transform: translateY(0);
    opacity: 0.45;
  }
  30% {
    transform: translateY(-3px);
    opacity: 1;
  }
}

.welcome {
  margin: 28px auto 0;
  max-width: 620px;
  text-align: center;
  padding: 0 10px;
}
.welcome-mark {
  width: 44px;
  height: 44px;
  border-radius: 13px;
  background: #fff;
  border: 1px solid var(--border);
  color: var(--primary);
  display: grid;
  place-items: center;
  margin: 0 auto 14px;
  box-shadow: var(--shadow-sm);
}
.welcome h3 {
  margin: 0 0 6px;
  font-size: 18px;
  letter-spacing: -0.3px;
}
.welcome p {
  margin: 0 0 18px;
  font-size: 12.5px;
  color: var(--text-sub);
  line-height: 1.7;
}
.examples {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 9px;
  text-align: left;
}
.example {
  border: 1px solid var(--border);
  background: #fff;
  border-radius: 11px;
  padding: 10px 12px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 3px;
  transition: all 0.15s;
}
.example strong {
  font-size: 12.5px;
}
.example span {
  font-size: 11.5px;
  color: var(--text-dim);
  line-height: 1.55;
}
.example:hover {
  border-color: #c3d2f5;
  transform: translateY(-1px);
  box-shadow: var(--shadow);
}

.composer {
  border-top: 1px solid var(--border);
  background: #fff;
  padding: 11px 24px 12px;
  display: grid;
  grid-template-columns: 1fr 40px;
  grid-template-areas: 'input send' 'tip tip';
  gap: 8px;
  align-items: end;
}
.composer textarea {
  grid-area: input;
  resize: none;
  min-height: 42px;
  max-height: 120px;
  border-radius: 11px;
  border: 1px solid var(--border);
  padding: 11px 13px;
  font-size: 13.5px;
  font-family: inherit;
  line-height: 1.5;
  outline: none;
  color: var(--text);
  background: #fbfcfe;
}
.composer textarea:focus {
  border-color: var(--primary);
  background: #fff;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
}
.send {
  grid-area: send;
  width: 40px;
  height: 40px;
  border-radius: 11px;
  border: none;
  background: linear-gradient(135deg, #2563eb, #4f46e5);
  color: #fff;
  cursor: pointer;
  display: grid;
  place-items: center;
  box-shadow: 0 6px 14px rgba(37, 99, 235, 0.25);
}
.send:disabled {
  opacity: 0.45;
  cursor: not-allowed;
  box-shadow: none;
}
.tip {
  grid-area: tip;
  font-size: 10.5px;
  color: var(--text-dim);
}

/* ---------- 右 ---------- */
.cards {
  border-left: 1px solid var(--border);
  background: #fbfcfe;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.cards-head {
  padding: 15px 16px 10px;
  display: flex;
  justify-content: space-between;
  font-size: 12.5px;
  font-weight: 650;
  color: var(--text-sub);
  border-bottom: 1px solid var(--border);
}
.cards-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.cards-empty {
  margin-top: 40px;
  text-align: center;
  color: var(--text-dim);
  padding: 0 18px;
}
.cards-empty p {
  font-size: 11.5px;
  line-height: 1.7;
}

@media (max-width: 1360px) {
  .wb {
    grid-template-columns: 210px minmax(0, 1fr) 320px;
  }
}
@media (max-width: 1180px) {
  .wb {
    grid-template-columns: 200px minmax(0, 1fr);
  }
  .cards {
    display: none;
  }
}
</style>
