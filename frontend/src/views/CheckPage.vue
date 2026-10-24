<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { riskApi } from '@/api'
import RiskScoreCard from '@/components/RiskScoreCard.vue'
import SvgIcon from '@/components/SvgIcon.vue'
import type { RiskResult } from '@/types'
import { EVENT_TYPE_LABEL, LEVEL_LABEL } from '@/utils/format'
import { useAuthStore } from '@/stores/auth'
import { can } from '@/utils/permission'

const auth = useAuthStore()
const canCheck = computed(() => can(auth.operator?.role, 'check'))

const form = reactive({
  event_type: 'order_pay',
  user_id: 'U1001',
  order_id: 'O2001',
  source_id: ''
})
const loading = ref(false)
const result = ref<RiskResult | null>(null)
const history = ref<RiskResult[]>([])
const showFeatures = ref(false)

const EVENT_TYPES = [
  { value: 'order_create', label: '下单', desc: '创建订单时评估收货信息与账号风险' },
  { value: 'order_pay', label: '支付', desc: '支付环节拦截盗刷、套券与团伙欺诈' },
  { value: 'after_sale_apply', label: '售后申请', desc: '退款/退货申请的恶意套利识别' },
  { value: 'logistics_complaint', label: '物流投诉', desc: '投诉高发账号与虚假物流单识别' }
]

async function submit() {
  if (!canCheck.value) {
    ElMessage.warning('当前角色为数据查看人，无检查权限')
    return
  }
  if (!form.user_id.trim()) {
    ElMessage.warning('请填写用户编号')
    return
  }
  loading.value = true
  try {
    const data = await riskApi.check({
      event_type: form.event_type,
      user_id: form.user_id.trim(),
      order_id: form.order_id.trim() || undefined,
      source_id: form.source_id.trim() || undefined
    })
    result.value = data
    history.value = [data, ...history.value].slice(0, 6)
    ElMessage.success(`检查完成：${data.risk_score} 分 / ${LEVEL_LABEL[data.risk_level]}`)
  } catch (error: any) {
    ElMessage.error(error?.message || '检查失败')
  } finally {
    loading.value = false
  }
}

function pick(item: RiskResult) {
  result.value = item
}

onMounted(() => {
  if (auth.operator?.role === 'viewer') {
    ElMessage.info('当前为只读角色，可查看历史检查结果')
  }
})
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">风险检查</h1>
        <p class="page-desc">
          选择业务事件并输入参数，一次调用返回评分、等级、处理建议、命中规则与 25 项特征快照
        </p>
      </div>
      <span class="pill" :class="canCheck ? 'tag-low' : 'tag-medium'">
        {{ canCheck ? '可发起检查' : '只读角色' }}
      </span>
    </div>

    <div class="grid">
      <div class="col-form">
        <div class="card panel">
          <div class="panel-title">业务事件</div>
          <div class="events">
            <button
              v-for="event in EVENT_TYPES"
              :key="event.value"
              type="button"
              class="event"
              :class="{ on: form.event_type === event.value }"
              @click="form.event_type = event.value"
            >
              <strong>{{ event.label }}</strong>
              <span class="mono">{{ event.value }}</span>
              <em>{{ event.desc }}</em>
            </button>
          </div>

          <div class="fields">
            <label class="field">
              <span>用户编号 <b>*</b></span>
              <input v-model="form.user_id" placeholder="如 U1001" />
            </label>
            <label class="field">
              <span>订单编号</span>
              <input v-model="form.order_id" placeholder="如 O2001" />
            </label>
            <label class="field">
              <span>来源单号</span>
              <input v-model="form.source_id" placeholder="上游业务单号，可选" />
            </label>
          </div>

          <button class="submit" :disabled="loading || !canCheck" @click="submit">
            <SvgIcon name="search" :size="15" />
            {{ loading ? '检查中…' : '发起风险检查' }}
          </button>

          <div class="tips">
            演示数据：U1001+O2001（高风险 93）、U1002+O2002（中风险 68）、U1003+O2003（低风险 0）
          </div>
        </div>

        <div v-if="history.length" class="card panel">
          <div class="panel-title">本次会话的检查（{{ history.length }}）</div>
          <button
            v-for="(item, index) in history"
            :key="index"
            type="button"
            class="history-item"
            :class="{ on: result?.assessment_id === item.assessment_id }"
            @click="pick(item)"
          >
            <span class="mini-score" :class="`s-${item.risk_level}`">{{ item.risk_score }}</span>
            <span class="h-main">
              <b>{{ EVENT_TYPE_LABEL[item.event_type || 'order_pay'] }} · {{ item.user_id }}</b>
              <span class="mono">{{ item.order_id }}</span>
            </span>
            <span class="h-tag" :class="`tag-${item.risk_level}`">{{ item.risk_level }}</span>
          </button>
        </div>
      </div>

      <div class="col-result">
        <RiskScoreCard v-if="result" :data="result" />
        <div v-else class="card empty">
          <SvgIcon name="alert" :size="24" />
          <p>左侧填好参数后发起检查，结果卡片会显示在这里。</p>
          <p class="muted">评分 0-100，≥70 高风险、≥40 中风险；高风险自动建案。</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 420px;
  gap: 14px;
  align-items: start;
}
.col-form,
.col-result {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.panel {
  padding: 15px 16px;
}
.panel-title {
  font-size: 12.5px;
  font-weight: 650;
  color: var(--text-sub);
  margin-bottom: 10px;
}

.events {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}
.event {
  text-align: left;
  border: 1px solid var(--border);
  background: #fff;
  border-radius: 10px;
  padding: 9px 11px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 2px;
  transition: all 0.15s;
}
.event strong {
  font-size: 12.5px;
}
.event .mono {
  color: var(--text-dim);
  font-size: 10.5px;
}
.event em {
  font-style: normal;
  font-size: 11px;
  color: var(--text-dim);
  line-height: 1.5;
}
.event:hover {
  border-color: #c3d2f5;
  background: #f8faff;
}
.event.on {
  border-color: var(--primary);
  background: var(--primary-soft);
}

.fields {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin: 14px 0 12px;
}
.field span {
  display: block;
  font-size: 11.5px;
  color: var(--text-sub);
  margin-bottom: 5px;
}
.field b {
  color: var(--high);
}
.field input {
  width: 100%;
  height: 36px;
  border-radius: 8px;
  border: 1px solid var(--border);
  padding: 0 10px;
  font-size: 13px;
  outline: none;
  color: var(--text);
}
.field input:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
}

.submit {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 38px;
  padding: 0 18px;
  border: none;
  border-radius: 9px;
  background: linear-gradient(135deg, #2563eb, #4f46e5);
  color: #fff;
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 6px 16px rgba(37, 99, 235, 0.22);
}
.submit:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  box-shadow: none;
}
.tips {
  margin-top: 10px;
  font-size: 11px;
  color: var(--text-dim);
  line-height: 1.6;
}

.history-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 9px;
  border: 1px solid transparent;
  background: none;
  border-radius: 9px;
  padding: 7px 8px;
  cursor: pointer;
  text-align: left;
}
.history-item:hover {
  background: #f6f9fe;
}
.history-item.on {
  border-color: var(--primary);
  background: var(--primary-soft);
}
.mini-score {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  font-weight: 700;
  font-size: 13px;
  flex: 0 0 30px;
}
.mini-score.s-high {
  background: var(--high-soft);
  color: var(--high);
}
.mini-score.s-medium {
  background: var(--medium-soft);
  color: var(--medium);
}
.mini-score.s-low {
  background: var(--low-soft);
  color: var(--low);
}
.h-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.h-main b {
  font-size: 12.5px;
}
.h-main .mono {
  color: var(--text-dim);
  font-size: 10.5px;
}
.h-tag {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 999px;
  font-weight: 600;
}

.empty {
  padding: 46px 24px;
  text-align: center;
  color: var(--text-dim);
}
.empty p {
  font-size: 12.5px;
  line-height: 1.8;
  margin: 10px 0 0;
}

@media (max-width: 1180px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
