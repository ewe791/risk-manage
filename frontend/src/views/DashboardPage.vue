<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { riskApi } from '@/api'

const data = ref<any>(null)
const loading = ref(false)

const days = 7
const W = 640
const H = 220
const PAD_X = 28
const PAD_Y = 18

const trend = computed<Array<{ date: string; events: number; high_risk: number }>>(() => data.value?.trend || [])
const ranking = computed<any[]>(() => data.value?.rule_hit_ranking || [])
const eff = computed<any>(() => data.value?.case_efficiency || {})

const maxValue = computed(() => Math.max(1, ...trend.value.map((t) => t.events)))

const tiles = computed(() => [
  { label: '风险事件总量', value: data.value?.total_events ?? 0, unit: '次', accent: '#2563eb', hint: `近 ${days} 天趋势见右` },
  {
    label: '高风险占比',
    value: Math.round((data.value?.high_risk_ratio ?? 0) * 100),
    unit: '%',
    accent: '#dc2626',
    hint: '高风险评估 / 全部评估'
  },
  { label: '待处理案件', value: eff.value.pending_cases ?? 0, unit: '件', accent: '#d97706', hint: `处理率 ${Math.round((eff.value.review_rate ?? 0) * 100)}%` },
  { label: '黑名单命中', value: data.value?.blacklist_hit_count ?? 0, unit: '次', accent: '#7c3aed', hint: '用户/地址类名单命中' }
])

function x(index: number) {
  const n = trend.value.length
  if (n <= 1) return PAD_X
  return PAD_X + (index * (W - PAD_X * 2)) / (n - 1)
}

function y(value: number) {
  return H - PAD_Y - (value / maxValue.value) * (H - PAD_Y * 2)
}

function line(key: 'events' | 'high_risk') {
  return trend.value.map((item, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(Number(item[key] || 0)).toFixed(1)}`).join(' ')
}

function area() {
  if (!trend.value.length) return ''
  const base = H - PAD_Y
  return `${line('events')} L${x(trend.value.length - 1).toFixed(1)},${base} L${PAD_X},${base} Z`
}

function gridLines() {
  return [0, 0.25, 0.5, 0.75, 1].map((ratio) => ({
    y: H - PAD_Y - ratio * (H - PAD_Y * 2),
    value: Math.round(maxValue.value * ratio)
  }))
}

async function load() {
  loading.value = true
  try {
    data.value = await riskApi.dashboard(days)
  } catch (error: any) {
    ElMessage.error(error?.message || '加载看板失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page" v-loading="loading">
    <div class="page-head">
      <div>
        <h1 class="page-title">风险看板</h1>
        <p class="page-desc">事件总量、高风险占比、规则命中排行与案件处理效率（近 {{ days }} 天）</p>
      </div>
      <el-button @click="load">刷新</el-button>
    </div>

    <template v-if="data">
      <div class="tiles">
        <div v-for="tile in tiles" :key="tile.label" class="card tile">
          <span class="tile-label">{{ tile.label }}</span>
          <div class="tile-value" :style="{ color: tile.accent }">
            {{ tile.value }}<em>{{ tile.unit }}</em>
          </div>
          <span class="tile-hint">{{ tile.hint }}</span>
        </div>
      </div>

      <div class="grid">
        <div class="card panel chart-panel">
          <div class="panel-head">
            <span class="panel-title">事件趋势</span>
            <span class="legend"><i class="dot-a" />事件量<i class="dot-b" />高风险</span>
          </div>
          <svg :viewBox="`0 0 ${W} ${H}`" class="chart">
            <g class="grid">
              <line
                v-for="(g, i) in gridLines()"
                :key="i"
                :x1="PAD_X"
                :x2="W - PAD_X"
                :y1="g.y"
                :y2="g.y"
              />
            </g>
            <path :d="area()" fill="url(#grad)" opacity="0.5" />
            <defs>
              <linearGradient id="grad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#2563eb" stop-opacity="0.28" />
                <stop offset="100%" stop-color="#2563eb" stop-opacity="0" />
              </linearGradient>
            </defs>
            <path :d="line('events')" class="line-a" />
            <path :d="line('high_risk')" class="line-b" />
            <g>
              <circle
                v-for="(item, i) in trend"
                :key="i"
                :cx="x(i)"
                :cy="y(item.events)"
                r="3.2"
                class="pt"
              >
                <title>{{ item.date }}：{{ item.events }} 个事件，其中高风险 {{ item.high_risk }}</title>
              </circle>
            </g>
          </svg>
          <div class="axis">
            <span v-for="(item, i) in trend" :key="i">{{ item.date }}</span>
          </div>
        </div>

        <div class="card panel">
          <div class="panel-head"><span class="panel-title">案件处理效率</span></div>
          <div class="eff-list">
            <div class="eff-row">
              <span>案件总数</span><b>{{ eff.total_cases ?? 0 }}</b>
            </div>
            <div class="eff-row">
              <span>待处理</span><b style="color: var(--medium)">{{ eff.pending_cases ?? 0 }}</b>
            </div>
            <div class="eff-row">
              <span>已审核</span><b style="color: var(--low)">{{ eff.reviewed_cases ?? 0 }}</b>
            </div>
            <div class="eff-row">
              <span>平均处理时长</span><b>{{ eff.avg_handle_hours ?? 0 }} h</b>
            </div>
          </div>
          <div class="ratio">
            <div class="ratio-bar"><i :style="{ width: `${Math.min(100, (eff.review_rate ?? 0) * 100)}%` }" /></div>
            <span>{{ Math.round((eff.review_rate ?? 0) * 100) }}%</span>
          </div>
          <p class="ratio-hint">处理率 = 已审核案件 / 全部案件；平均时长为建案到审核完成的时间差。</p>
        </div>
      </div>

      <div class="card panel table-panel">
        <div class="panel-head">
          <span class="panel-title">规则命中排行（全量）</span>
          <span class="muted">Top {{ ranking.length }}</span>
        </div>
        <el-table :data="ranking" size="small" style="width: 100%">
          <el-table-column label="#" width="56">
            <template #default="{ $index }">{{ $index + 1 }}</template>
          </el-table-column>
          <el-table-column label="规则" width="110">
            <template #default="{ row }"><span class="mono code">{{ row.rule_code }}</span></template>
          </el-table-column>
          <el-table-column prop="rule_name" label="规则名" min-width="180" />
          <el-table-column label="命中占比" min-width="220">
            <template #default="{ row }">
              <div class="bar-wrap">
                <div class="bar">
                  <i :style="{ width: `${Math.max(4, (row.hit_count / (ranking[0]?.hit_count || 1)) * 100)}%` }" />
                </div>
                <span>{{ row.hit_count }} 次</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="hit_score_sum" label="累计分值" width="110" align="right" />
        </el-table>
        <div v-if="!ranking.length" class="empty">暂无命中记录，先在工作台发起一次风险检查</div>
      </div>
    </template>

    <div v-else class="card empty-state">加载中…</div>
  </div>
</template>

<style scoped>
.tiles {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 14px;
}
.tile {
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.tile-label {
  font-size: 12px;
  color: var(--text-sub);
}
.tile-value {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.8px;
}
.tile-value em {
  font-style: normal;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-dim);
  margin-left: 3px;
}
.tile-hint {
  font-size: 11px;
  color: var(--text-dim);
}

.grid {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr);
  gap: 14px;
  margin-bottom: 14px;
  align-items: stretch;
}
.panel {
  padding: 15px 16px;
}
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.panel-title {
  font-size: 13px;
  font-weight: 650;
}

.chart {
  width: 100%;
  height: 220px;
  display: block;
}
.grid line {
  stroke: #eef1f7;
  stroke-width: 1;
}
.line-a {
  fill: none;
  stroke: #2563eb;
  stroke-width: 2.2;
  stroke-linejoin: round;
}
.line-b {
  fill: none;
  stroke: #dc2626;
  stroke-width: 1.8;
  stroke-dasharray: 5 4;
  stroke-linejoin: round;
}
.pt {
  fill: #fff;
  stroke: #2563eb;
  stroke-width: 1.8;
}
.axis {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--text-dim);
  padding: 0 6px;
}
.legend {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11.5px;
  color: var(--text-dim);
}
.legend i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.dot-a {
  background: #2563eb;
}
.dot-b {
  background: #dc2626;
  margin-left: 8px;
}

.eff-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.eff-row {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  color: var(--text-sub);
  border-bottom: 1px dotted #eef1f7;
  padding-bottom: 6px;
}
.eff-row b {
  color: var(--text);
  font-size: 14px;
}
.ratio {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
  font-size: 13px;
  font-weight: 600;
  color: var(--low);
}
.ratio-bar {
  flex: 1;
  height: 8px;
  background: #f1f4f9;
  border-radius: 999px;
  overflow: hidden;
}
.ratio-bar i {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #86efac, #16a34a);
}
.ratio-hint {
  margin: 9px 0 0;
  font-size: 11.5px;
  color: var(--text-dim);
  line-height: 1.7;
}

.table-panel {
  padding: 15px 16px 8px;
}
.code {
  color: var(--primary);
  background: var(--primary-soft);
  padding: 1px 6px;
  border-radius: 5px;
  font-weight: 600;
}
.bar-wrap {
  display: flex;
  align-items: center;
  gap: 9px;
  font-size: 12px;
  color: var(--text-sub);
}
.bar {
  flex: 1;
  height: 6px;
  background: #f1f4f9;
  border-radius: 4px;
  overflow: hidden;
}
.bar i {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #93b4fb, #2563eb);
  border-radius: 4px;
}
.empty {
  font-size: 12px;
  color: var(--text-dim);
  padding: 14px 0;
  text-align: center;
}
.empty-state {
  padding: 50px;
  text-align: center;
  color: var(--text-dim);
}
@media (max-width: 1200px) {
  .tiles {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
