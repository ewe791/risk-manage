<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { riskApi } from '@/api'
import type { RiskCase } from '@/types'
import { CASE_STATUS_LABEL, LEVEL_LABEL, formatTime } from '@/utils/format'

const props = withDefaults(
  defineProps<{ item: RiskCase; actionable?: boolean; compact?: boolean }>(),
  { actionable: true, compact: false }
)
const emit = defineEmits<{ (e: 'reviewed', payload: any): void }>()

const dialog = ref(false)
const submitting = ref(false)
const form = ref({ review_result: 'approve', review_remark: '' })

const statusLabel = computed(() => CASE_STATUS_LABEL[props.item.case_status] || props.item.case_status)
const canReview = computed(
  () => props.actionable && ['pending', 'reviewing'].includes(props.item.case_status)
)
const levelClass = computed(() => `tag-${props.item.risk_level || 'low'}`)

function open() {
  form.value = { review_result: 'approve', review_remark: '' }
  dialog.value = true
}

async function submit() {
  if (!form.value.review_remark.trim()) {
    ElMessage.warning('请填写审核备注（必填，将写入 review_logs）')
    return
  }
  submitting.value = true
  try {
    const result = await riskApi.reviewCase({
      case_id: props.item.case_id,
      review_result: form.value.review_result,
      review_remark: form.value.review_remark.trim()
    })
    ElMessage.success(`审核已提交：${CASE_STATUS_LABEL[result.case_status] || result.case_status}`)
    dialog.value = false
    emit('reviewed', result)
  } catch (error: any) {
    ElMessage.error(error?.message || '提交失败')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="case">
    <div class="row1">
      <span class="code mono">{{ item.case_id }}</span>
      <span class="status" :class="`st-${item.case_status}`">{{ statusLabel }}</span>
      <span v-if="item.risk_level" class="pill" :class="levelClass">{{ LEVEL_LABEL[item.risk_level] }}</span>
    </div>

    <div class="row2">
      <span>用户 <b class="mono">{{ item.user_id }}</b></span>
      <span>订单 <b class="mono">{{ item.order_id || '—' }}</b></span>
      <span v-if="item.risk_score !== null && item.risk_score !== undefined">评分 <b>{{ item.risk_score }}</b></span>
      <span class="muted">{{ formatTime(item.created_at) }}</span>
    </div>

    <div v-if="item.review_result" class="row3">
      审核结论：{{ CASE_STATUS_LABEL[item.case_status] }} · 操作员
      <span class="mono">{{ item.reviewer_id }}</span>
    </div>

    <div v-if="canReview" class="actions">
      <button class="btn" type="button" @click="open">审核</button>
    </div>

    <el-dialog v-model="dialog" title="案件审核" width="430px" append-to-body>
      <div class="dlg">
        <div class="dlg-case">
          案件 <b class="mono">{{ item.case_id }}</b> · 用户 <b class="mono">{{ item.user_id }}</b>
        </div>
        <el-radio-group v-model="form.review_result">
          <el-radio value="approve">通过（判定风险成立）</el-radio>
          <el-radio value="reject">驳回（风险不成立）</el-radio>
          <el-radio value="escalate">升级复核</el-radio>
        </el-radio-group>
        <el-input
          v-model="form.review_remark"
          type="textarea"
          :rows="4"
          maxlength="500"
          show-word-limit
          placeholder="请填写审核依据（必填），会写入 review_logs"
        />
      </div>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">提交审核</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.case {
  border: 1px solid var(--border);
  border-radius: 11px;
  padding: 11px 12px;
  background: #fff;
  box-shadow: var(--shadow-sm);
}

.row1 {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.code {
  font-weight: 650;
  color: var(--text);
}
.status {
  font-size: 11.5px;
  padding: 1px 7px;
  border-radius: 999px;
  font-weight: 600;
}
.st-pending {
  color: #b45309;
  background: #fef3c7;
}
.st-reviewing {
  color: #1d4ed8;
  background: #dbeafe;
}
.st-approved {
  color: #166534;
  background: #dcfce7;
}
.st-rejected {
  color: #b91c1c;
  background: #fee2e2;
}

.row2 {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 14px;
  font-size: 12px;
  color: var(--text-sub);
  margin-top: 7px;
}
.row2 b {
  color: var(--text);
}
.row3 {
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-sub);
}

.actions {
  margin-top: 9px;
  display: flex;
  justify-content: flex-end;
}
.btn {
  border: 1px solid var(--primary);
  color: var(--primary);
  background: var(--primary-soft);
  border-radius: 7px;
  padding: 4px 14px;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
}
.btn:hover {
  background: var(--primary);
  color: #fff;
}

.dlg {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.dlg-case {
  font-size: 12.5px;
  color: var(--text-sub);
}
</style>
