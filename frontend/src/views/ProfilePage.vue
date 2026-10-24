<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { riskApi } from '@/api'
import ProfileCard from '@/components/ProfileCard.vue'
import { CASE_STATUS_LABEL, EVENT_TYPE_LABEL, LEVEL_LABEL, formatTime } from '@/utils/format'

const ORDER_STATUS_LABEL: Record<string, string> = {
  paid: '已支付',
  delivered: '已签收',
  refunded: '已退款',
  created: '已创建',
  closed: '已关闭'
}

const userId = ref('U1001')
const loading = ref(false)
const profile = ref<any>(null)

async function load() {
  if (!userId.value.trim()) return
  loading.value = true
  try {
    profile.value = await riskApi.profile(userId.value.trim())
  } catch (error: any) {
    ElMessage.error(error?.message || '加载画像失败')
  } finally {
    loading.value = false
  }
}

load()
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">用户画像</h1>
        <p class="page-desc">订单历史、退款投诉、收货地址、最近风险事件与关联案件一屏聚合</p>
      </div>
      <div class="search">
        <el-input v-model="userId" placeholder="输入用户 ID，如 U1001" style="width: 200px" @keyup.enter="load" />
        <el-button type="primary" :loading="loading" @click="load">查询</el-button>
      </div>
    </div>

    <div v-if="profile" class="grid">
      <div class="left">
        <ProfileCard :data="profile" compact />

        <div class="card panel">
          <div class="panel-title">收货地址（{{ profile.address_count }}）</div>
          <div class="addr" v-for="addr in profile.addresses" :key="addr.address_id">
            <span class="mono id">{{ addr.address_id }}</span>
            <span class="city">{{ addr.city }}</span>
            <span class="detail">{{ addr.detail }}</span>
            <span class="shared">共用 {{ addr.shared_user_count }} 账号</span>
          </div>
        </div>
      </div>

      <div class="right">
        <div class="card panel">
          <div class="panel-title">订单历史（{{ profile.order_history.length }}）</div>
          <el-table :data="profile.order_history" size="small" style="width: 100%">
            <el-table-column label="订单" width="100">
              <template #default="{ row }"><span class="mono">{{ row.order_id }}</span></template>
            </el-table-column>
            <el-table-column label="金额" width="96">
              <template #default="{ row }">¥{{ Number(row.amount).toFixed(2) }}</template>
            </el-table-column>
            <el-table-column prop="category" label="品类" width="110" />
            <el-table-column label="状态" width="96">
              <template #default="{ row }">
                <span class="pill" :class="row.refund_status ? 'tag-high' : 'tag-low'">
                  {{ row.refund_status ? '已退款' : ORDER_STATUS_LABEL[row.status] || row.status }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="投诉" width="70">
              <template #default="{ row }">{{ row.has_complaint ? '是' : '否' }}</template>
            </el-table-column>
            <el-table-column label="下单时间" min-width="140">
              <template #default="{ row }"><span class="muted">{{ formatTime(row.created_at) }}</span></template>
            </el-table-column>
          </el-table>
        </div>

        <div class="card panel">
          <div class="panel-title">最近风险事件（{{ profile.recent_risk_events.length }}）</div>
          <div v-for="event in profile.recent_risk_events" :key="event.event_id" class="event-row">
            <span class="etype">{{ EVENT_TYPE_LABEL[event.event_type] || event.event_type }}</span>
            <span class="mono muted">{{ event.order_id }}</span>
            <span class="score">{{ event.risk_score ?? '—' }} 分</span>
            <span v-if="event.risk_level" class="pill" :class="`tag-${event.risk_level}`">
              {{ LEVEL_LABEL[event.risk_level] }}
            </span>
            <span class="muted time">{{ formatTime(event.created_at) }}</span>
          </div>
        </div>

        <div class="card panel">
          <div class="panel-title">关联案件（{{ profile.related_cases.length }}）</div>
          <div v-for="item in profile.related_cases" :key="item.case_id" class="event-row">
            <span class="mono">{{ item.case_id }}</span>
            <span class="mono muted">{{ item.order_id }}</span>
            <span class="pill" :class="item.case_status === 'pending' ? 'tag-medium' : 'tag-low'">
              {{ CASE_STATUS_LABEL[item.case_status] || item.case_status }}
            </span>
            <span class="muted time">{{ formatTime(item.created_at) }}</span>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="card empty-state">
      <p>输入用户 ID 后查询画像，演示数据可用 U1001 / U1002 / U1003。</p>
    </div>
  </div>
</template>

<style scoped>
.search {
  display: flex;
  gap: 8px;
}
.grid {
  display: grid;
  grid-template-columns: 330px minmax(0, 1fr);
  gap: 14px;
  align-items: start;
}
.left,
.right {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.panel {
  padding: 14px;
}
.panel-title {
  font-size: 12.5px;
  font-weight: 650;
  color: var(--text-sub);
  margin-bottom: 10px;
}
.addr {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  padding: 6px 0;
  border-bottom: 1px dotted #eef1f7;
  flex-wrap: wrap;
}
.addr .id {
  color: var(--primary);
  background: var(--primary-soft);
  padding: 0 5px;
  border-radius: 4px;
}
.addr .detail {
  color: var(--text-sub);
  flex: 1;
}
.addr .shared {
  color: var(--text-dim);
  font-size: 11px;
}
.event-row {
  display: flex;
  align-items: center;
  gap: 9px;
  font-size: 12.5px;
  padding: 6px 0;
  border-bottom: 1px dotted #eef1f7;
}
.etype {
  font-weight: 600;
  min-width: 62px;
}
.score {
  color: var(--high);
  font-weight: 650;
}
.time {
  margin-left: auto;
  font-size: 11.5px;
}
.empty-state {
  padding: 40px;
  text-align: center;
  color: var(--text-dim);
  font-size: 13px;
}
@media (max-width: 1100px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
