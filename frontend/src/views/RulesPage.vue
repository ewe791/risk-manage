<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { riskApi } from '@/api'
import type { RiskRule } from '@/types'
import { formatTime } from '@/utils/format'
import { useAuthStore } from '@/stores/auth'
import { can } from '@/utils/permission'

const rows = ref<RiskRule[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)
const status = ref('')
const keyword = ref('')
const enabledTotal = ref(0)

const dialog = ref(false)
const editing = ref<RiskRule | null>(null)
const saving = ref(false)
const form = reactive({
  rule_code: '',
  rule_name: '',
  priority: 100,
  score: 10,
  rule_status: 'enabled',
  description: '',
  condition_text: '{\n  "op": "and",\n  "conditions": [\n    { "field": "order_amount", "op": ">", "value": 5000 }\n  ]\n}'
})

const enabledCount = computed(() => enabledTotal.value)
const auth = useAuthStore()
const canWrite = computed(() => can(auth.operator?.role, 'rule_write'))

function condToText(cond: any): string {
  if (!cond || typeof cond !== 'object') return '—'
  if (cond.op === 'and' || cond.op === 'or') {
    const parts = (cond.conditions || []).map((c: any) => condToText(c))
    return `(${parts.join(cond.op === 'and' ? ' 且 ' : ' 或 ')})`
  }
  const value = typeof cond.value === 'boolean' ? (cond.value ? 'true' : 'false') : JSON.stringify(cond.value)
  return `${cond.field} ${cond.op} ${value}`
}

async function load() {
  loading.value = true
  try {
    const data = await riskApi.listRules({
      page: page.value,
      page_size: pageSize.value,
      rule_status: status.value || undefined,
      keyword: keyword.value || undefined
    })
    rows.value = data.items
    total.value = data.total
    const enabled = await riskApi.listRules({ page: 1, page_size: 1, rule_status: 'enabled' })
    enabledTotal.value = enabled.total
  } catch (error: any) {
    ElMessage.error(error?.message || '加载规则失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)

function openCreate() {
  editing.value = null
  Object.assign(form, {
    rule_code: '',
    rule_name: '',
    priority: 100,
    score: 10,
    rule_status: 'enabled',
    description: '',
    condition_text: '{\n  "op": "and",\n  "conditions": [\n    { "field": "order_amount", "op": ">", "value": 5000 }\n  ]\n}'
  })
  dialog.value = true
}

function openEdit(row: RiskRule) {
  editing.value = row
  Object.assign(form, {
    rule_code: row.rule_code,
    rule_name: row.rule_name,
    priority: row.priority,
    score: row.score,
    rule_status: row.rule_status,
    description: row.description || '',
    condition_text: JSON.stringify(row.condition_json, null, 2)
  })
  dialog.value = true
}

async function save() {
  let condition: any
  try {
    condition = JSON.parse(form.condition_text)
  } catch {
    ElMessage.error('条件 JSON 解析失败，请检查括号与引号')
    return
  }
  saving.value = true
  try {
    if (editing.value) {
      await riskApi.updateRule({
        rule_id: editing.value.rule_id,
        rule_name: form.rule_name,
        priority: form.priority,
        score: form.score,
        rule_status: form.rule_status as 'enabled' | 'disabled',
        description: form.description,
        condition_json: condition
      })
      ElMessage.success('规则已更新')
    } else {
      await riskApi.createRule({
        rule_code: form.rule_code,
        rule_name: form.rule_name,
        priority: form.priority,
        score: form.score,
        rule_status: form.rule_status as 'enabled' | 'disabled',
        description: form.description,
        condition_json: condition
      })
      ElMessage.success('规则已创建')
    }
    dialog.value = false
    await load()
  } catch (error: any) {
    ElMessage.error(error?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function toggle(row: RiskRule) {
  const target = row.rule_status === 'enabled' ? 'disabled' : 'enabled'
  try {
    await riskApi.setRuleStatus(row.rule_id, target)
    row.rule_status = target
    ElMessage.success(`${row.rule_code} 已${target === 'enabled' ? '启用' : '停用'}`)
  } catch (error: any) {
    ElMessage.error(error?.message || '操作失败')
  }
}

async function remove(row: RiskRule) {
  try {
    await ElMessageBox.confirm(
      `删除规则 ${row.rule_code} ${row.rule_name}？其历史命中记录也会被清理，且不可恢复。`,
      '确认删除',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  try {
    await riskApi.deleteRule(row.rule_id)
    ElMessage.success('已删除')
    await load()
  } catch (error: any) {
    ElMessage.error(error?.message || '删除失败')
  }
}

function reset() {
  status.value = ''
  keyword.value = ''
  page.value = 1
  load()
}
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">规则管理</h1>
        <p class="page-desc">
          共 {{ total }} 条规则，当前启用 {{ enabledCount }} 条 · 停用后新发起的检查立即生效，历史评估不回改
        </p>
      </div>
      <el-button v-if="canWrite" type="primary" @click="openCreate">新建规则</el-button>
      <span v-else class="readonly-tip">只读角色，规则维护需管理员权限</span>
    </div>

    <div class="card filters">
      <el-input v-model="keyword" placeholder="搜索规则名或编码" clearable style="width: 220px" @keyup.enter="load" />
      <el-select v-model="status" placeholder="全部状态" clearable style="width: 140px">
        <el-option label="启用" value="enabled" />
        <el-option label="停用" value="disabled" />
      </el-select>
      <el-button @click="page = 1; load()">查询</el-button>
      <el-button text @click="reset">重置</el-button>
    </div>

    <div class="card table-card">
      <el-table v-loading="loading" :data="rows" style="width: 100%" row-key="rule_id">
        <el-table-column label="编码" width="90">
          <template #default="{ row }"><span class="mono code">{{ row.rule_code }}</span></template>
        </el-table-column>
        <el-table-column prop="rule_name" label="规则名" min-width="150" />
        <el-table-column label="条件" min-width="280">
          <template #default="{ row }">
            <span class="cond">{{ condToText(row.condition_json) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="分值" width="76" align="center">
          <template #default="{ row }"><b class="score">+{{ row.score }}</b></template>
        </el-table-column>
        <el-table-column prop="priority" label="优先级" width="82" align="center" />
        <el-table-column label="命中次数" width="96" align="center" sortable>
          <template #default="{ row }">
            <span class="hit-count" :class="{ zero: !row.hit_count }">{{ row.hit_count ?? 0 }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="86" align="center">
          <template #default="{ row }">
            <el-switch
              :model-value="row.rule_status === 'enabled'"
              :disabled="!canWrite"
              @change="toggle(row)"
            />
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="150">
          <template #default="{ row }">
            <span class="muted">{{ formatTime(row.updated_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="130" align="right">
          <template #default="{ row }">
            <template v-if="canWrite">
              <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
              <el-button link type="danger" @click="remove(row)">删除</el-button>
            </template>
            <span v-else class="muted">—</span>
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

    <el-dialog v-model="dialog" :title="editing ? '编辑规则' : '新建规则'" width="620px">
      <el-form label-width="92px" label-position="right">
        <el-form-item label="规则编码">
          <el-input v-model="form.rule_code" :disabled="!!editing" placeholder="如 R25" />
        </el-form-item>
        <el-form-item label="规则名">
          <el-input v-model="form.rule_name" placeholder="如 异常高频下单" />
        </el-form-item>
        <el-form-item label="分值 / 优先级">
          <el-input-number v-model="form.score" :min="0" :max="100" controls-position="right" />
          <el-input-number v-model="form.priority" :min="0" :max="9999" controls-position="right" style="margin-left: 12px" />
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="form.rule_status">
            <el-radio value="enabled">启用</el-radio>
            <el-radio value="disabled">停用</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="form.description" placeholder="业务含义，供审核员与 Agent 理解" />
        </el-form-item>
        <el-form-item label="条件 JSON">
          <el-input v-model="form.condition_text" type="textarea" :rows="9" class="json-input" />
          <div class="form-tip">
            支持 op：and / or / &gt; / &lt; / &gt;= / &lt;= / = / != / contains，可无限嵌套
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.filters {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  margin-bottom: 14px;
}
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
.cond {
  font-size: 12px;
  color: var(--text-sub);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.score {
  color: var(--high);
}
.hit-count {
  font-weight: 650;
  color: var(--primary);
  background: var(--primary-soft);
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 12px;
}
.hit-count.zero {
  color: var(--text-dim);
  background: #f3f5f9;
  font-weight: 500;
}
.readonly-tip {
  font-size: 12px;
  color: var(--text-dim);
}
.pager {
  display: flex;
  justify-content: flex-end;
  padding: 12px 10px 0;
}
.form-tip {
  font-size: 11.5px;
  color: var(--text-dim);
  margin-top: 5px;
}
.json-input :deep(textarea) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
}
</style>
