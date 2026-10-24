<script setup lang="ts">
import { computed, ref } from 'vue'
import type { RiskResult } from '@/types'
import { DECISION_LABEL, FEATURE_META, LEVEL_LABEL, formatTime, formatValue, scoreColor } from '@/utils/format'

const props = withDefaults(defineProps<{ data: RiskResult; dense?: boolean }>(), { dense: false })

const showFeatures = ref(false)

const score = computed(() => Math.max(0, Math.min(100, Number(props.data.risk_score ?? 0))))
const color = computed(() => scoreColor(score.value))
const level = computed(() => props.data.risk_level || 'low')
const decision = computed(() => DECISION_LABEL[props.data.decision] || props.data.decision || '—')
const hits = computed(() => props.data.rule_hits || [])
const snapshot = computed(() => props.data.feature_snapshot || {})

const CIRC = 2 * Math.PI * 40
const dash = computed(() => `${(score.value / 100) * CIRC} ${CIRC}`)

const groups = computed(() => {
  const names = ['用户维度', '订单维度', '地址维度']
  return names.map((name) => ({
    name,
    items: FEATURE_META.filter((meta) => meta.group === name).map((meta) => ({
      label: meta.label,
      key: meta.key,
      value: formatValue(snapshot.value[meta.key])
    }))
  }))
})
</script>

<template>
  <div class="rsc" :class="{ dense }">
    <div class="head">
      <div class="ring-wrap">
        <svg viewBox="0 0 96 96" :width="dense ? 74 : 92" :height="dense ? 74 : 92">
          <circle cx="48" cy="48" r="40" fill="none" stroke="#eef1f7" stroke-width="9" />
          <circle
            cx="48"
            cy="48"
            r="40"
            fill="none"
            :stroke="color"
            stroke-width="9"
            stroke-linecap="round"
            :stroke-dasharray="dash"
            transform="rotate(-90 48 48)"
          />
        </svg>
        <div class="ring-label">
          <span class="num" :style="{ color }">{{ score }}</span>
          <span class="unit">分</span>
        </div>
      </div>

      <div class="meta">
        <div class="tags">
          <span class="pill" :class="`tag-${level}`">{{ LEVEL_LABEL[level] }}</span>
          <span class="pill decision" :class="`dec-${data.decision}`">{{ decision }}</span>
          <span class="pill ghost">命中 {{ hits.length }} 条规则</span>
        </div>

        <div class="kv">
          <span>评估 <b class="mono">{{ data.assessment_id || '—' }}</b></span>
          <span v-if="data.user_id">用户 <b class="mono">{{ data.user_id }}</b></span>
          <span v-if="data.order_id">订单 <b class="mono">{{ data.order_id }}</b></span>
          <span v-if="data.created_at">{{ formatTime(data.created_at) }}</span>
        </div>

        <div v-if="data.case_id" class="case-banner">
          <span class="dot" />
          已自动建案 <b class="mono">{{ data.case_id }}</b>，状态：待审核
        </div>
      </div>
    </div>

    <div v-if="hits.length" class="block">
      <div class="block-title">命中规则</div>
      <ul class="hits">
        <li v-for="hit in hits" :key="hit.rule_code || hit.rule_name">
          <div class="hit-head">
            <span class="code mono">{{ hit.rule_code }}</span>
            <span class="name">{{ hit.rule_name }}</span>
            <span class="pts">+{{ hit.hit_score }}</span>
          </div>
          <div class="hit-msg">{{ hit.hit_message }}</div>
        </li>
      </ul>
    </div>

    <div class="block">
      <button class="toggle" type="button" @click="showFeatures = !showFeatures">
        <span class="block-title">特征快照（25 项）</span>
        <span class="chevron" :class="{ open: showFeatures }">›</span>
      </button>
      <div v-show="showFeatures" class="features">
        <div v-for="group in groups" :key="group.name" class="feat-group">
          <div class="feat-group-name">{{ group.name }}</div>
          <div class="feat-grid">
            <div v-for="item in group.items" :key="item.key" class="feat-item" :title="item.key">
              <span class="k">{{ item.label }}</span>
              <span class="v">{{ item.value }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.rsc {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 16px 16px 13px;
  box-shadow: var(--shadow-sm);
}
.rsc.dense {
  padding: 13px 13px 10px;
}

.head {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}

.ring-wrap {
  position: relative;
  flex: 0 0 auto;
  display: grid;
  place-items: center;
}
.ring-label {
  position: absolute;
  display: flex;
  align-items: baseline;
  gap: 1px;
}
.ring-label .num {
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -1px;
}
.dense .ring-label .num {
  font-size: 20px;
}
.ring-label .unit {
  font-size: 11px;
  color: var(--text-dim);
}

.meta {
  flex: 1;
  min-width: 0;
}

.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}
.pill.ghost {
  color: var(--text-sub);
  background: #f2f5fa;
  font-weight: 500;
}
.pill.decision.dec-reject {
  color: #b91c1c;
  background: #fee2e2;
}
.pill.decision.dec-manual_review {
  color: #b45309;
  background: #fef3c7;
}
.pill.decision.dec-pass {
  color: #166534;
  background: #dcfce7;
}

.kv {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 14px;
  font-size: 12px;
  color: var(--text-sub);
}
.kv b {
  color: var(--text);
  font-weight: 600;
}

.case-banner {
  margin-top: 9px;
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
  font-size: 12px;
  color: #92400e;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 8px;
  padding: 6px 9px;
  line-height: 1.5;
}
.case-banner b {
  font-weight: 600;
  white-space: nowrap;
}
.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #f59e0b;
}

.block {
  margin-top: 13px;
}
.block-title {
  font-size: 12px;
  font-weight: 650;
  color: var(--text-sub);
  letter-spacing: 0.2px;
}

.hits {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.hits li {
  border: 1px solid var(--border);
  border-radius: 9px;
  padding: 7px 10px;
  background: var(--panel-soft);
}
.hit-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
}
.hit-head .code {
  color: var(--primary);
  background: var(--primary-soft);
  padding: 1px 5px;
  border-radius: 4px;
  font-weight: 600;
}
.hit-head .name {
  font-weight: 600;
  flex: 1;
}
.hit-head .pts {
  color: var(--high);
  font-weight: 700;
}
.hit-msg {
  font-size: 11.5px;
  color: var(--text-dim);
  margin-top: 3px;
  line-height: 1.5;
  word-break: break-all;
}

.toggle {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
}
.chevron {
  color: var(--text-dim);
  transition: transform 0.18s;
  font-size: 16px;
  line-height: 1;
}
.chevron.open {
  transform: rotate(90deg);
}

.features {
  margin-top: 9px;
  border-top: 1px dashed var(--border);
  padding-top: 9px;
  display: flex;
  flex-direction: column;
  gap: 9px;
}
.feat-group-name {
  font-size: 11px;
  color: var(--text-dim);
  margin-bottom: 4px;
}
.feat-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 3px 12px;
}
.feat-item {
  display: flex;
  justify-content: space-between;
  gap: 6px;
  font-size: 11.5px;
  padding: 2px 0;
  border-bottom: 1px dotted #eef1f7;
}
.feat-item .k {
  color: var(--text-sub);
}
.feat-item .v {
  font-weight: 600;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11px;
}
</style>
