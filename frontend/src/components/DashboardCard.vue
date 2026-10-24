<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{ data: any; dense?: boolean }>(), { dense: false })

const trend = computed<Array<{ date: string; events: number; high_risk: number }>>(() => props.data?.trend || [])
const ranking = computed<any[]>(() => props.data?.rule_hit_ranking || [])
const eff = computed<any>(() => props.data?.case_efficiency || {})

const maxEvents = computed(() => Math.max(1, ...trend.value.map((t) => t.events)))
const maxHit = computed(() => Math.max(1, ...ranking.value.map((r) => r.hit_count)))

const W = 300
const H = 72
const pad = 4

function points(key: 'events' | 'high_risk') {
  const n = trend.value.length
  if (n === 0) return ''
  const step = n > 1 ? (W - pad * 2) / (n - 1) : 0
  return trend.value
    .map((item, i) => {
      const x = pad + i * step
      const ratio = Number(item[key] || 0) / maxEvents.value
      const y = H - pad - ratio * (H - pad * 2)
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
}

const tiles = computed(() => [
  { label: '事件总量', value: props.data?.total_events ?? 0, unit: '次', accent: '#2563eb' },
  {
    label: '高风险占比',
    value: `${Math.round((props.data?.high_risk_ratio ?? 0) * 100)}`,
    unit: '%',
    accent: '#dc2626'
  },
  { label: '待审案件', value: eff.value.pending_cases ?? 0, unit: '件', accent: '#d97706' },
  { label: '黑名单命中', value: props.data?.blacklist_hit_count ?? 0, unit: '次', accent: '#7c3aed' }
])
</script>

<template>
  <div class="dash" :class="{ dense }">
    <div class="tiles">
      <div v-for="tile in tiles" :key="tile.label" class="tile">
        <span class="tile-label">{{ tile.label }}</span>
        <span class="tile-value" :style="{ color: tile.accent }">
          {{ tile.value }}<em>{{ tile.unit }}</em>
        </span>
      </div>
    </div>

    <div class="block">
      <div class="block-head">
        <span>近 {{ trend.length || 7 }} 天事件趋势</span>
        <span class="legend">
          <i class="dot-a" />事件 <i class="dot-b" />高风险
        </span>
      </div>
      <svg :viewBox="`0 0 ${W} ${H}`" class="spark" preserveAspectRatio="none">
        <line :x1="0" :y1="H - 4" :x2="W" :y2="H - 4" stroke="#eef1f7" stroke-width="1" />
        <path :d="points('events')" fill="none" stroke="#2563eb" stroke-width="2" stroke-linejoin="round" />
        <path
          :d="points('high_risk')"
          fill="none"
          stroke="#dc2626"
          stroke-width="1.8"
          stroke-dasharray="4 3"
          stroke-linejoin="round"
        />
      </svg>
      <div class="axis">
        <span v-for="(item, i) in trend" :key="i">{{ item.date }}</span>
      </div>
    </div>

    <div class="block">
      <div class="block-head"><span>规则命中排行</span><span class="muted">Top {{ ranking.length }}</span></div>
      <ul class="rank">
        <li v-for="row in ranking.slice(0, 5)" :key="row.rule_code">
          <div class="rank-head">
            <span class="code mono">{{ row.rule_code }}</span>
            <span class="name">{{ row.rule_name }}</span>
            <span class="count">{{ row.hit_count }} 次</span>
          </div>
          <div class="bar"><i :style="{ width: `${Math.max(6, (row.hit_count / maxHit) * 100)}%` }" /></div>
        </li>
      </ul>
    </div>

    <div class="eff">
      案件处理：共 {{ eff.total_cases ?? 0 }} 件 · 已审 {{ eff.reviewed_cases ?? 0 }} 件 · 处理率
      {{ Math.round((eff.review_rate ?? 0) * 100) }}% · 平均 {{ eff.avg_handle_hours ?? 0 }} 小时
    </div>
  </div>
</template>

<style scoped>
.dash {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 15px;
  box-shadow: var(--shadow-sm);
}

.tiles {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}
.tile {
  background: var(--panel-soft);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 9px 11px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.tile-label {
  font-size: 11.5px;
  color: var(--text-dim);
}
.tile-value {
  font-size: 21px;
  font-weight: 700;
  letter-spacing: -0.6px;
}
.tile-value em {
  font-style: normal;
  font-size: 11px;
  font-weight: 500;
  color: var(--text-dim);
  margin-left: 2px;
}

.block {
  margin-top: 13px;
}
.block-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  font-weight: 650;
  color: var(--text-sub);
  margin-bottom: 7px;
}

.legend {
  display: flex;
  align-items: center;
  gap: 5px;
  font-weight: 500;
  font-size: 11px;
  color: var(--text-dim);
}
.legend i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  display: inline-block;
}
.dot-a {
  background: #2563eb;
}
.dot-b {
  background: #dc2626;
  margin-left: 6px;
}

.spark {
  width: 100%;
  height: 72px;
  display: block;
}
.axis {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  color: var(--text-dim);
  margin-top: 2px;
}

.rank {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.rank-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}
.rank-head .code {
  color: var(--primary);
  background: var(--primary-soft);
  padding: 0 5px;
  border-radius: 4px;
}
.rank-head .name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rank-head .count {
  color: var(--text-sub);
  font-weight: 600;
}
.bar {
  height: 5px;
  background: #f1f4f9;
  border-radius: 4px;
  overflow: hidden;
  margin-top: 3px;
}
.bar i {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #93b4fb, #2563eb);
  border-radius: 4px;
}

.eff {
  margin-top: 13px;
  padding-top: 10px;
  border-top: 1px dashed var(--border);
  font-size: 11.5px;
  color: var(--text-sub);
  line-height: 1.6;
}
</style>
