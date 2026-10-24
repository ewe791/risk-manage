<script setup lang="ts">
import { computed } from 'vue'
import { CASE_STATUS_LABEL, EVENT_TYPE_LABEL, LEVEL_LABEL, formatTime } from '@/utils/format'

const props = withDefaults(defineProps<{ data: any; compact?: boolean }>(), { compact: false })

const events = computed<any[]>(() => (props.data?.recent_risk_events || []).slice(0, 5))
const cases = computed<any[]>(() => (props.data?.related_cases || []).slice(0, 4))
const tiles = computed(() => [
  { label: '30天订单', value: props.data?.order_count_30d ?? 0 },
  { label: '退款', value: props.data?.refund_count ?? 0 },
  { label: '投诉', value: props.data?.complaint_count ?? 0 },
  { label: '地址', value: props.data?.address_count ?? 0 }
])
</script>

<template>
  <div class="profile">
    <div class="head">
      <div class="avatar">{{ (data?.user_id || 'U').slice(0, 1) }}</div>
      <div class="who">
        <strong>{{ data?.user_id }} <span class="nick">{{ data?.nickname }}</span></strong>
        <span class="sub">注册 {{ data?.reg_days ?? '—' }} 天 · 累计订单 {{ data?.order_count ?? 0 }} 笔</span>
      </div>
    </div>

    <div class="tiles">
      <div v-for="tile in tiles" :key="tile.label" class="tile">
        <span class="v">{{ tile.value }}</span>
        <span class="l">{{ tile.label }}</span>
      </div>
    </div>

    <div v-if="events.length && !compact" class="block">
      <div class="title">最近风险事件</div>
      <ul class="timeline">
        <li v-for="event in events" :key="event.event_id">
          <span class="dot" :class="`lv-${event.risk_level || 'none'}`" />
          <div class="event-body">
            <div class="line1">
              <span class="etype">{{ EVENT_TYPE_LABEL[event.event_type] || event.event_type }}</span>
              <span v-if="event.order_id" class="mono muted">{{ event.order_id }}</span>
              <span v-if="event.risk_score !== null" class="score">{{ event.risk_score }} 分</span>
              <span v-if="event.risk_level" class="pill" :class="`tag-${event.risk_level}`">
                {{ LEVEL_LABEL[event.risk_level] }}
              </span>
            </div>
            <div class="line2">{{ formatTime(event.created_at) }}</div>
          </div>
        </li>
      </ul>
    </div>

    <div v-if="cases.length && !compact" class="block">
      <div class="title">关联案件</div>
      <ul class="cases">
        <li v-for="item in cases" :key="item.case_id">
          <span class="mono">{{ item.case_id }}</span>
          <span class="st">{{ CASE_STATUS_LABEL[item.case_status] || item.case_status }}</span>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.profile {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 14px;
  box-shadow: var(--shadow-sm);
}
.head {
  display: flex;
  align-items: center;
  gap: 10px;
}
.avatar {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: var(--primary-soft);
  color: var(--primary);
  display: grid;
  place-items: center;
  font-weight: 700;
}
.who {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.who strong {
  font-size: 13.5px;
}
.nick {
  font-weight: 400;
  color: var(--text-dim);
  font-size: 12px;
  margin-left: 4px;
}
.sub {
  font-size: 11.5px;
  color: var(--text-dim);
}

.tiles {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
  margin-top: 11px;
}
.tile {
  background: var(--panel-soft);
  border: 1px solid var(--border);
  border-radius: 9px;
  padding: 7px 6px;
  text-align: center;
}
.tile .v {
  display: block;
  font-size: 17px;
  font-weight: 700;
}
.tile .l {
  font-size: 10.5px;
  color: var(--text-dim);
}

.block {
  margin-top: 12px;
}
.title {
  font-size: 12px;
  font-weight: 650;
  color: var(--text-sub);
  margin-bottom: 7px;
}

.timeline {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.timeline li {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  margin-top: 5px;
  background: #cbd5e1;
  flex: 0 0 7px;
}
.dot.lv-high {
  background: var(--high);
}
.dot.lv-medium {
  background: var(--medium);
}
.dot.lv-low {
  background: var(--low);
}
.event-body {
  flex: 1;
  min-width: 0;
}
.line1 {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
  font-size: 12.5px;
}
.etype {
  font-weight: 600;
}
.score {
  color: var(--high);
  font-weight: 650;
}
.line2 {
  font-size: 11px;
  color: var(--text-dim);
  margin-top: 1px;
}

.cases {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
}
.cases li {
  display: flex;
  justify-content: space-between;
  border-bottom: 1px dotted #eef1f7;
  padding-bottom: 3px;
}
.st {
  color: var(--text-sub);
}
</style>
