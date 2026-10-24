<script setup lang="ts">
import { computed } from 'vue'
import RiskScoreCard from './RiskScoreCard.vue'
import CaseCard from './CaseCard.vue'
import DashboardCard from './DashboardCard.vue'
import ProfileCard from './ProfileCard.vue'
import type { Card } from '@/types'
import { BLACKLIST_TYPE_LABEL, CASE_STATUS_LABEL } from '@/utils/format'

const props = withDefaults(defineProps<{ card: Card; dense?: boolean; actionable?: boolean }>(), {
  dense: false,
  actionable: true
})
const emit = defineEmits<{ (e: 'reviewed', payload: any): void }>()

const type = computed(() => props.card?.type)
const data = computed<any>(() => props.card?.data || {})

const cases = computed<any[]>(() => data.value.items || [])
const rules = computed<any[]>(() => data.value.items || [])
const blacklists = computed<any[]>(() => data.value.items || [])
const isToggleResult = computed(() => type.value === 'rule_list' && !!data.value.rule_code && !data.value.items)
const isBlacklistAdd = computed(() => type.value === 'blacklist' && !!data.value.blacklist_id)
const deletedBlacklist = computed(() => data.value.deleted)
</script>

<template>
  <RiskScoreCard v-if="type === 'risk_score'" :data="data" :dense="dense" />

  <div v-else-if="type === 'case_list'" class="box">
    <div class="box-head">
      <span>案件列表</span>
      <span class="muted">共 {{ data.total ?? cases.length }} 件</span>
    </div>
    <div v-if="cases.length" class="list">
      <CaseCard
        v-for="item in cases.slice(0, 5)"
        :key="item.case_id"
        :item="item"
        :actionable="actionable"
        @reviewed="(payload) => emit('reviewed', payload)"
      />
    </div>
    <div v-else class="empty">没有符合条件的案件</div>
  </div>

  <div v-else-if="type === 'case_review'" class="box done">
    <div class="done-head">
      <span class="check">✓</span>
      审核已提交
    </div>
    <div class="done-body">
      <div>案件 <b class="mono">{{ data.case_id }}</b></div>
      <div>结论：{{ CASE_STATUS_LABEL[data.case_status] || data.case_status }}</div>
      <div>操作员：<span class="mono">{{ data.reviewer_id }}</span></div>
      <div class="remark">备注：{{ data.review_remark }}</div>
    </div>
  </div>

  <DashboardCard v-else-if="type === 'dashboard'" :data="data" :dense="dense" />

  <ProfileCard v-else-if="type === 'profile'" :data="data" />

  <div v-else-if="type === 'rule_list'" class="box">
    <div class="box-head">
      <span>{{ isToggleResult ? '规则状态变更' : '规则列表' }}</span>
      <span v-if="!isToggleResult" class="muted">共 {{ data.total ?? rules.length }} 条</span>
    </div>

    <div v-if="isToggleResult" class="toggle-result">
      <span class="mono">{{ data.rule_code }}</span>
      <span class="name">{{ data.rule_name }}</span>
      <span class="pill" :class="data.rule_status === 'enabled' ? 'tag-low' : 'tag-high'">
        {{ data.rule_status === 'enabled' ? '已启用' : '已停用' }}
      </span>
    </div>

    <ul v-else class="rules">
      <li v-for="rule in rules.slice(0, 8)" :key="rule.rule_id">
        <div class="rule-head">
          <span class="code mono">{{ rule.rule_code }}</span>
          <span class="name">{{ rule.rule_name }}</span>
          <span class="status" :class="{ off: rule.rule_status !== 'enabled' }">
            {{ rule.rule_status === 'enabled' ? '启用' : '停用' }}
          </span>
          <span class="score">+{{ rule.score }}</span>
        </div>
        <div v-if="rule.description" class="desc">{{ rule.description }}</div>
      </li>
    </ul>
  </div>

  <div v-else-if="type === 'blacklist'" class="box">
    <div class="box-head">
      <span>黑名单</span>
      <span class="muted">{{ isBlacklistAdd ? '已新增' : deletedBlacklist ? '已删除' : `共 ${data.total ?? blacklists.length} 条` }}</span>
    </div>

    <div v-if="isBlacklistAdd" class="toggle-result">
      <span class="pill tag-high">{{ BLACKLIST_TYPE_LABEL[data.blacklist_type] || data.blacklist_type }}</span>
      <span class="mono">{{ data.blacklist_value }}</span>
      <span class="muted">{{ data.remark }}</span>
    </div>

    <div v-else-if="deletedBlacklist" class="toggle-result">
      <span class="pill tag-high">{{ BLACKLIST_TYPE_LABEL[deletedBlacklist.blacklist_type] }}</span>
      <span class="mono">{{ deletedBlacklist.blacklist_value }}</span>
      <span class="muted">已删除</span>
    </div>

    <ul v-else class="rules">
      <li v-for="item in blacklists.slice(0, 8)" :key="item.blacklist_id">
        <div class="rule-head">
          <span class="code mono">{{ BLACKLIST_TYPE_LABEL[item.blacklist_type] || item.blacklist_type }}</span>
          <span class="name mono">{{ item.blacklist_value }}</span>
          <span class="status" :class="{ off: item.status !== 'active' }">{{ item.status === 'active' ? '生效' : '失效' }}</span>
        </div>
        <div v-if="item.remark" class="desc">{{ item.remark }}</div>
      </li>
    </ul>
  </div>

  <div v-else class="box">
    <div class="box-head"><span>工具结果</span></div>
    <pre class="raw">{{ JSON.stringify(data, null, 2) }}</pre>
  </div>
</template>

<style scoped>
.box {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 13px;
  box-shadow: var(--shadow-sm);
}
.box-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12.5px;
  font-weight: 650;
  color: var(--text-sub);
  margin-bottom: 9px;
}

.list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.empty {
  font-size: 12px;
  color: var(--text-dim);
  padding: 10px 0;
  text-align: center;
}

.done {
  border-color: #bbf7d0;
  background: #f7fef9;
}
.done-head {
  display: flex;
  align-items: center;
  gap: 7px;
  font-weight: 650;
  color: #166534;
  font-size: 13px;
}
.check {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #16a34a;
  color: #fff;
  display: grid;
  place-items: center;
  font-size: 11px;
}
.done-body {
  margin-top: 8px;
  font-size: 12.5px;
  color: var(--text-sub);
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.remark {
  margin-top: 3px;
  padding: 6px 8px;
  background: #fff;
  border: 1px dashed #d7e9dc;
  border-radius: 7px;
  color: var(--text);
}

.toggle-result {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12.5px;
}
.toggle-result .name {
  font-weight: 600;
}

.rules {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.rules li {
  border-bottom: 1px dotted #eef1f7;
  padding-bottom: 6px;
}
.rules li:last-child {
  border-bottom: none;
}
.rule-head {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12.5px;
}
.rule-head .code {
  color: var(--primary);
  background: var(--primary-soft);
  padding: 0 5px;
  border-radius: 4px;
}
.rule-head .name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rule-head .status {
  font-size: 11px;
  color: var(--low);
  background: var(--low-soft);
  padding: 0 6px;
  border-radius: 999px;
}
.rule-head .status.off {
  color: var(--high);
  background: var(--high-soft);
}
.rule-head .score {
  color: var(--text-sub);
  font-weight: 600;
}
.desc {
  font-size: 11.5px;
  color: var(--text-dim);
  margin-top: 2px;
  line-height: 1.5;
}

.raw {
  margin: 0;
  font-size: 11px;
  max-height: 220px;
  overflow: auto;
  background: #f6f8fc;
  padding: 8px;
  border-radius: 8px;
  white-space: pre-wrap;
}
</style>
