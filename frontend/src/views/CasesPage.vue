<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { riskApi } from '@/api'
import type { RiskCase } from '@/types'
import { CASE_STATUS_LABEL, FEATURE_META, LEVEL_LABEL, formatTime, formatValue } from '@/utils/format'
import { useAuthStore } from '@/stores/auth'
import { can } from '@/utils/permission'

const rows = ref<RiskCase[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)
const status = ref('pending')

const drawer = ref(false)
const detail = ref<RiskCase | null>(null)
const dialog = ref(false)
const current = ref<RiskCase | null>(null)
const submitting = ref(false)
const form = reactive({ review_result: 'approve', review_remark: '' })
const auth = useAuthStore()
const canReview = computed(() => can(auth.operator?.role, 'case_review'))

const resolveDialog = ref(false)
const resolving = ref(false)
const resolveForm = reactive({ resolve_remark: '' })

/** 特征快照按维度分组展示（文档 2.3.3 案件详情页） */
const featureGroups = computed(() => {
  const snapshot = detail.value?.feature_snapshot || {}
  return ['用户维度', '订单维度', '地址维度'].map((name) => ({
    name,
    items: FEATURE_META.filter((m) => m.group === name).map((m) => ({
      label: m.label,
      value: formatValue(snapshot[m.key])
    }))
  }))
})
const snapshotCount = computed(() => Object.keys(detail.value?.feature_snapshot || {}).length)

function openResolve(row: RiskCase) {
  current.value = row
  resolveForm.resolve_remark = ''
  resolveDialog.value = true
}

async function submitResolve() {
  if (!current.value) return
  if (!resolveForm.resolve_remark.trim()) {
    ElMessage.warning('请填写处理说明')
    return
  }
  resolving.value = true
  try {
    await riskApi.resolveCase({ case_id: current.value.case_id, resolve_remark: resolveForm.resolve_remark.trim() })
    ElMessage.success('已标记处理完成（resolved）')
    resolveDialog.value = false
    await load()
    if (drawer.value && detail.value?.case_id === current.value.case_id) {
      detail.value = await riskApi.getCase(current.value.case_id)
    }
  } catch (error: any) {
    ElMessage.error(error?.message || '操作失败')
  } finally {
    resolving.value = false
  }
}

async function load() {
  loading.value = true
  try {
    const data = await riskApi.listCases({
      page: page.value,
      page_size: pageSize.value,
      case_status: status.value || undefined
    })
    rows.value = data.items
    total.value = data.total
  } catch (error: any) {
    ElMessage.error(error?.message || '加载案件失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function openDetail(row: RiskCase) {
  try {
    detail.value = await riskApi.getCase(row.case_id)
    drawer.value = true
  } catch (error: any) {
    ElMessage.error(error?.message || '加载详情失败')
  }
}

function openReview(row: RiskCase) {
  current.value = row
  form.review_result = 'approve'
  form.review_remark = ''
  dialog.value = true
}

async function submitReview() {
  if (!current.value) return
  if (!form.review_remark.trim()) {
    ElMessage.warning('请填写审核备注')
    return
  }
  submitting.value = true
  try {
    await riskApi.reviewCase({
      case_id: current.value.case_id,
      review_result: form.review_result,
      review_remark: form.review_remark.trim()
    })
    ElMessage.success('审核已提交，已写入 review_logs')
    dialog.value = false
    await load()
    if (drawer.value && detail.value?.case_id === current.value.case_id) {
      detail.value = await riskApi.getCase(current.value.case_id)
    }
  } catch (error: any) {
    ElMessage.error(error?.message || '提交失败')
  } finally {
    submitting.value = false
  }
}

function statusType(value: string) {
  return value === 'pending' ? 'warning' : value === 'approved' ? 'success' : value === 'rejected' ? 'danger' : 'primary'
}
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">案件审核</h1>
        <p class="page-desc">高风险或需人工介入的评估会自动建案；审核结论与备注全程留痕</p>
      </div>
      <el-radio-group v-model="status" @change="page = 1; load()">
        <el-radio-button value="">全部</el-radio-button>
        <el-radio-button value="pending">待审核</el-radio-button>
        <el-radio-button value="approved">已通过</el-radio-button>
        <el-radio-button value="rejected">已驳回</el-radio-button>
        <el-radio-button value="resolved">已结案</el-radio-button>
      </el-radio-group>
    </div>

    <div class="card table-card">
      <el-table v-loading="loading" :data="rows" style="width: 100%">
        <el-table-column label="案件编号" width="160">
          <template #default="{ row }"><span class="mono code">{{ row.case_id }}</span></template>
        </el-table-column>
        <el-table-column prop="user_id" label="用户" width="110" />
        <el-table-column prop="order_id" label="订单" width="110" />
        <el-table-column label="评分 / 等级" width="150">
          <template #default="{ row }">
            <b :style="{ color: row.risk_level === 'high' ? 'var(--high)' : row.risk_level === 'medium' ? 'var(--medium)' : 'var(--low)' }">
              {{ row.risk_score ?? '—' }}
            </b>
            <span v-if="row.risk_level" class="pill" :class="`tag-${row.risk_level}`" style="margin-left: 6px">
              {{ LEVEL_LABEL[row.risk_level] }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusType(row.case_status)" effect="light" size="small">
              {{ CASE_STATUS_LABEL[row.case_status] || row.case_status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="reviewer_id" label="审核人" width="120">
          <template #default="{ row }"><span class="mono">{{ row.reviewer_id || '—' }}</span></template>
        </el-table-column>
        <el-table-column label="创建时间" width="150">
          <template #default="{ row }"><span class="muted">{{ formatTime(row.created_at) }}</span></template>
        </el-table-column>
        <el-table-column label="操作" min-width="150" align="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">详情</el-button>
            <el-button
              v-if="canReview && ['pending', 'reviewing'].includes(row.case_status)"
              link
              type="warning"
              @click="openReview(row)"
            >
              审核
            </el-button>
            <el-button
              v-if="canReview && ['approved', 'rejected'].includes(row.case_status)"
              link
              type="success"
              @click="openResolve(row)"
            >
              结案
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @current-change="load"
          @size-change="load"
        />
      </div>
    </div>

    <el-drawer v-model="drawer" title="案件详情" size="480px">
      <div v-if="detail" class="detail">
        <div class="d-row">
          <span class="k">案件编号</span><span class="mono">{{ detail.case_id }}</span>
        </div>
        <div class="d-row"><span class="k">评估</span><span class="mono">{{ detail.assessment_id }}</span></div>
        <div class="d-row"><span class="k">用户 / 订单</span><span>{{ detail.user_id }} / {{ detail.order_id || '—' }}</span></div>
        <div class="d-row">
          <span class="k">评分</span>
          <span>{{ detail.risk_score ?? '—' }} 分 · {{ LEVEL_LABEL[detail.risk_level || 'low'] }}</span>
        </div>
        <div class="d-row">
          <span class="k">状态</span>
          <el-tag :type="statusType(detail.case_status)" size="small" effect="light">
            {{ CASE_STATUS_LABEL[detail.case_status] }}
          </el-tag>
        </div>

        <div class="d-title">命中规则</div>
        <ul class="hits">
          <li v-for="hit in detail.rule_hits || []" :key="hit.rule_code">
            <span class="mono code">{{ hit.rule_code }}</span>
            <span class="name">{{ hit.rule_name }}</span>
            <b>+{{ hit.hit_score }}</b>
          </li>
          <li v-if="!(detail.rule_hits || []).length" class="empty">无命中记录</li>
        </ul>

        <div class="d-title">特征快照（{{ snapshotCount }} 项）</div>
        <div v-if="snapshotCount" class="feat-groups">
          <div v-for="group in featureGroups" :key="group.name" class="feat-group">
            <div class="fg-name">{{ group.name }}</div>
            <div class="fg-grid">
              <div v-for="item in group.items" :key="item.label" class="fg-item">
                <span class="k">{{ item.label }}</span>
                <span class="v">{{ item.value }}</span>
              </div>
            </div>
          </div>
        </div>
        <div v-else class="empty">该评估未保存特征快照</div>

        <div class="d-title">审核日志（review_logs）</div>
        <ul class="logs">
          <li v-for="log in detail.review_logs || []" :key="log.log_id">
            <div class="log-head">
              <span class="mono">{{ log.operator_id }}</span>
              <span class="action">{{ log.action_type }}</span>
              <span class="muted">{{ formatTime(log.created_at) }}</span>
            </div>
            <div class="log-body">{{ log.action_remark }}</div>
          </li>
          <li v-if="!(detail.review_logs || []).length" class="empty">暂无审核记录</li>
        </ul>

        <el-button
          v-if="canReview && ['pending', 'reviewing'].includes(detail.case_status)"
          type="primary"
          style="margin-top: 16px; width: 100%"
          @click="openReview(detail)"
        >
          审核该案件
        </el-button>
        <el-button
          v-if="canReview && ['approved', 'rejected'].includes(detail.case_status)"
          type="success"
          style="margin-top: 16px; width: 100%"
          @click="openResolve(detail)"
        >
          标记处理完成（结案）
        </el-button>
        <div v-if="detail.resolved_at" class="resolved-tip">
          已于 {{ formatTime(detail.resolved_at) }} 结案归档
        </div>
      </div>
    </el-drawer>

    <el-dialog v-model="resolveDialog" title="标记处理完成" width="440px">
      <div class="dlg">
        <div class="mono muted">{{ current?.case_id }} · {{ current?.user_id }}</div>
        <div class="resolve-hint">结案后案件状态变为 <b>resolved</b>，并写入 review_logs，不可再变更。</div>
        <el-input
          v-model="resolveForm.resolve_remark"
          type="textarea"
          :rows="4"
          maxlength="500"
          show-word-limit
          placeholder="处置说明（必填），如：已冻结账号并追回款项"
        />
      </div>
      <template #footer>
        <el-button @click="resolveDialog = false">取消</el-button>
        <el-button type="primary" :loading="resolving" @click="submitResolve">确认结案</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="dialog" title="案件审核" width="440px">
      <div class="dlg">
        <div class="mono muted">{{ current?.case_id }} · {{ current?.user_id }}</div>
        <el-radio-group v-model="form.review_result">
          <el-radio value="approve">通过（风险成立）</el-radio>
          <el-radio value="reject">驳回（风险不成立）</el-radio>
          <el-radio value="escalate">升级复核</el-radio>
        </el-radio-group>
        <el-input
          v-model="form.review_remark"
          type="textarea"
          :rows="4"
          maxlength="500"
          show-word-limit
          placeholder="审核依据（必填，写入 review_logs）"
        />
      </div>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitReview">提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.table-card {
  padding: 6px 6px 12px;
}
.code {
  color: var(--primary);
  background: var(--primary-soft);
  padding: 1px 6px;
  border-radius: 5px;
  font-weight: 600;
}
.pager {
  display: flex;
  justify-content: flex-end;
  padding: 12px 10px 0;
}
.detail {
  display: flex;
  flex-direction: column;
  gap: 9px;
}
.d-row {
  display: flex;
  gap: 12px;
  font-size: 13px;
}
.d-row .k {
  width: 84px;
  color: var(--text-dim);
  flex: 0 0 84px;
}
.d-title {
  margin-top: 12px;
  font-size: 12.5px;
  font-weight: 650;
  color: var(--text-sub);
  border-top: 1px dashed var(--border);
  padding-top: 12px;
}
.hits,
.logs {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.hits li {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
}
.hits .name {
  flex: 1;
}
.hits b {
  color: var(--high);
}
.logs li {
  background: var(--panel-soft);
  border: 1px solid var(--border);
  border-radius: 9px;
  padding: 8px 10px;
}
.log-head {
  display: flex;
  gap: 10px;
  font-size: 11.5px;
  color: var(--text-sub);
  align-items: center;
}
.action {
  color: var(--primary);
  font-weight: 600;
}
.log-body {
  font-size: 12.5px;
  margin-top: 4px;
  line-height: 1.6;
}
.empty {
  color: var(--text-dim);
  font-size: 12px;
}
.dlg {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.feat-groups {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.fg-name {
  font-size: 11px;
  color: var(--text-dim);
  margin-bottom: 4px;
}
.fg-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 3px 12px;
}
.fg-item {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 11.5px;
  padding: 2px 0;
  border-bottom: 1px dotted #eef1f7;
}
.fg-item .k {
  color: var(--text-sub);
}
.fg-item .v {
  font-weight: 600;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11px;
}
.resolve-hint {
  font-size: 12px;
  color: var(--text-sub);
  background: var(--panel-soft);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 7px 10px;
  line-height: 1.6;
}
.resolved-tip {
  margin-top: 10px;
  font-size: 11.5px;
  color: var(--low);
  background: var(--low-soft);
  border-radius: 8px;
  padding: 7px 10px;
  text-align: center;
}
</style>
