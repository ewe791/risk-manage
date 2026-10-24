<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { riskApi } from '@/api'
import type { BlacklistItem } from '@/types'
import { BLACKLIST_TYPE_LABEL, formatTime } from '@/utils/format'
import { useAuthStore } from '@/stores/auth'
import { can } from '@/utils/permission'

const rows = ref<BlacklistItem[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)
const type = ref('')
const keyword = ref('')

const dialog = ref(false)
const saving = ref(false)
const auth = useAuthStore()
const canWrite = computed(() => can(auth.operator?.role, 'blacklist_write'))

const importDialog = ref(false)
const importText = ref('')
const importing = ref(false)
const importResult = ref<any>(null)
const form = reactive<{ blacklist_type: string; blacklist_value: string; remark: string }>({
  blacklist_type: 'address',
  blacklist_value: '',
  remark: ''
})

async function load() {
  loading.value = true
  try {
    const data = await riskApi.listBlacklists({
      page: page.value,
      page_size: pageSize.value,
      blacklist_type: type.value || undefined,
      keyword: keyword.value || undefined
    })
    rows.value = data.items
    total.value = data.total
  } catch (error: any) {
    ElMessage.error(error?.message || '加载黑名单失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function add() {
  if (!form.blacklist_value.trim()) {
    ElMessage.warning('请填写黑名单值')
    return
  }
  saving.value = true
  try {
    await riskApi.addBlacklist({
      blacklist_type: form.blacklist_type as any,
      blacklist_value: form.blacklist_value.trim(),
      remark: form.remark || undefined,
      status: 'active'
    })
    ElMessage.success('已加入黑名单，下一次风险检查立即生效')
    dialog.value = false
    form.blacklist_value = ''
    form.remark = ''
    await load()
  } catch (error: any) {
    ElMessage.error(error?.message || '新增失败')
  } finally {
    saving.value = false
  }
}

function openImport() {
  importText.value = ''
  importResult.value = null
  importDialog.value = true
}

function onPickFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    importText.value = String(reader.result || '')
    ElMessage.success(`已读取 ${file.name}`)
  }
  reader.readAsText(file, 'utf-8')
  input.value = ''
}

async function submitImport() {
  if (!importText.value.trim()) {
    ElMessage.warning('请粘贴数据或选择文件')
    return
  }
  importing.value = true
  try {
    importResult.value = await riskApi.importBlacklists({ text: importText.value })
    const r = importResult.value
    ElMessage.success(`导入完成：新增 ${r.created} 条，跳过 ${r.skipped} 条，失败 ${r.failed} 条`)
    await load()
  } catch (error: any) {
    ElMessage.error(error?.message || '导入失败')
  } finally {
    importing.value = false
  }
}

async function remove(row: BlacklistItem) {
  try {
    await ElMessageBox.confirm(
      `将 ${BLACKLIST_TYPE_LABEL[row.blacklist_type]} ${row.blacklist_value} 移出黑名单？`,
      '确认删除',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  try {
    await riskApi.deleteBlacklist(row.blacklist_id)
    ElMessage.success('已删除')
    await load()
  } catch (error: any) {
    ElMessage.error(error?.message || '删除失败')
  }
}
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h1 class="page-title">黑名单管理</h1>
        <p class="page-desc">用户 / 地址 / IP / 设备四类名单，命中后由 R04、R05 等规则直接加分</p>
      </div>
      <div class="head-actions">
        <el-button v-if="canWrite" @click="openImport">批量导入</el-button>
        <el-button v-if="canWrite" type="primary" @click="dialog = true">新增黑名单</el-button>
        <span v-if="!canWrite" class="readonly-tip">只读角色，维护需管理员权限</span>
      </div>
    </div>

    <div class="card filters">
      <el-input v-model="keyword" placeholder="搜索黑名单值" clearable style="width: 220px" @keyup.enter="load" />
      <el-select v-model="type" placeholder="全部类型" clearable style="width: 140px">
        <el-option v-for="(label, key) in BLACKLIST_TYPE_LABEL" :key="key" :label="label" :value="key" />
      </el-select>
      <el-button @click="page = 1; load()">查询</el-button>
      <el-button text @click="type = ''; keyword = ''; page = 1; load()">重置</el-button>
    </div>

    <div class="card table-card">
      <el-table v-loading="loading" :data="rows" style="width: 100%">
        <el-table-column label="类型" width="100">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ BLACKLIST_TYPE_LABEL[row.blacklist_type] || row.blacklist_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="黑名单值" width="180">
          <template #default="{ row }"><span class="mono value">{{ row.blacklist_value }}</span></template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="280" show-overflow-tooltip />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <span class="pill" :class="row.status === 'active' ? 'tag-high' : 'tag-low'">
              {{ row.status === 'active' ? '生效' : '失效' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="加入时间" width="150">
          <template #default="{ row }"><span class="muted">{{ formatTime(row.created_at) }}</span></template>
        </el-table-column>
        <el-table-column label="操作" width="90" align="right">
          <template #default="{ row }">
            <el-button v-if="canWrite" link type="danger" @click="remove(row)">移除</el-button>
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

    <el-dialog v-model="importDialog" title="批量导入黑名单" width="580px">
      <div class="import-wrap">
        <div class="import-tip">
          每行一条：<code>类型,名单值,备注</code>，支持逗号/制表符分隔；类型可写
          <code>user/address/ip/device</code> 或中文「用户/地址/IP/设备」，自动跳过重复项。
        </div>
        <el-input
          v-model="importText"
          type="textarea"
          :rows="8"
          placeholder="address,ADDR-2025-01,虚假地址&#10;ip,45.32.11.90,代理池&#10;用户,U-7712,骗赔惯犯"
          class="import-text"
        />
        <div class="import-foot">
          <label class="file-btn">
            选择 CSV / TXT 文件
            <input type="file" accept=".csv,.txt" @change="onPickFile" />
          </label>
          <span class="muted">示例：{{ total }} 条已有记录不会被覆盖</span>
        </div>
        <div v-if="importResult" class="import-result">
          <div class="ir-row">
            <b class="ok">新增 {{ importResult.created }}</b>
            <b class="warn">跳过 {{ importResult.skipped }}</b>
            <b class="bad">失败 {{ importResult.failed }}</b>
            <span class="muted">共 {{ importResult.total }} 行</span>
          </div>
          <ul v-if="importResult.details?.length" class="ir-detail">
            <li v-for="(d, i) in importResult.details.slice(0, 8)" :key="i">
              第 {{ d.row }} 行：{{ d.reason }}{{ d.value ? `（${d.value}）` : '' }}
            </li>
          </ul>
        </div>
      </div>
      <template #footer>
        <el-button @click="importDialog = false">关闭</el-button>
        <el-button type="primary" :loading="importing" @click="submitImport">开始导入</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="dialog" title="新增黑名单" width="460px">
      <el-form label-width="88px">
        <el-form-item label="类型">
          <el-select v-model="form.blacklist_type" style="width: 100%">
            <el-option v-for="(label, key) in BLACKLIST_TYPE_LABEL" :key="key" :label="label" :value="key" />
          </el-select>
        </el-form-item>
        <el-form-item label="名单值">
          <el-input v-model="form.blacklist_value" placeholder="用户ID / 地址ID / IP / 设备指纹" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="3" placeholder="加入原因，便于后续复核" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="add">确定</el-button>
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
.value {
  color: var(--text);
  font-weight: 600;
}
.pager {
  display: flex;
  justify-content: flex-end;
  padding: 12px 10px 0;
}
.head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.readonly-tip {
  font-size: 12px;
  color: var(--text-dim);
}
.import-wrap {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.import-tip {
  font-size: 12px;
  color: var(--text-sub);
  line-height: 1.7;
  background: var(--panel-soft);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
}
.import-tip code {
  background: #eef2f9;
  padding: 0 4px;
  border-radius: 4px;
  font-size: 11.5px;
}
.import-text :deep(textarea) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
}
.import-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 11.5px;
}
.file-btn {
  border: 1px solid var(--border);
  border-radius: 7px;
  padding: 4px 10px;
  cursor: pointer;
  font-size: 12px;
  color: var(--primary);
}
.file-btn input {
  display: none;
}
.import-result {
  border-top: 1px dashed var(--border);
  padding-top: 9px;
}
.ir-row {
  display: flex;
  gap: 14px;
  align-items: center;
  font-size: 12.5px;
}
.ir-row .ok {
  color: var(--low);
}
.ir-row .warn {
  color: var(--medium);
}
.ir-row .bad {
  color: var(--high);
}
.ir-detail {
  margin: 6px 0 0;
  padding-left: 16px;
  font-size: 11.5px;
  color: var(--text-dim);
  line-height: 1.7;
}
</style>
