<template>
  <div class="audit-view">
    <el-card>
      <template #header>
        <div class="card-header">
          <div class="title">
            <span>{{ t('audit.title') }}</span>
            <el-tag size="small" type="info" effect="plain">{{ t('audit.totalCount', { count: total }) }}</el-tag>
            <span class="muted" v-if="retentionDays > 0">{{ t('audit.retentionDaysValue', { days: retentionDays }) }}</span>
            <span class="muted" v-else>{{ t('audit.retentionForever') }}</span>
          </div>
          <div class="actions">
            <el-button size="small" @click="loadLogs" :loading="loading">
              <el-icon><Refresh /></el-icon>{{ t('common.refresh') }}
            </el-button>
            <el-dropdown @command="handleExport" :disabled="!can('audit:edit')">
              <el-button size="small" :disabled="!can('audit:edit')">
                <el-icon><Download /></el-icon>{{ t('audit.export') }}
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="csv">{{ t('audit.exportCsv') }}</el-dropdown-item>
                  <el-dropdown-item command="json">{{ t('audit.exportJson') }}</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button
              v-if="isSuperuser"
              size="small"
              type="danger"
              plain
              @click="handleCleanup"
            >
              <el-icon><Delete /></el-icon>{{ t('audit.cleanup') }}
            </el-button>
          </div>
        </div>
      </template>

      <div class="filters">
        <el-select v-model="filters.module" :placeholder="t('audit.allModules')" clearable style="width: 150px">
          <el-option
            v-for="item in modules"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
        <el-select v-model="filters.action" :placeholder="t('audit.allActions')" clearable style="width: 140px">
          <el-option
            v-for="item in actions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
        <el-select v-model="filters.status" :placeholder="t('audit.allStatus')" clearable style="width: 120px" @change="handleSearch">
          <el-option :label="t('audit.success')" value="success" />
          <el-option :label="t('audit.failed')" value="failed" />
        </el-select>
        <el-input
          v-if="isSuperuser"
          v-model="filters.operator"
          :placeholder="t('audit.operator')"
          clearable
          style="width: 150px"
          @keyup.enter="handleSearch"
        />
        <el-tag v-else type="info" effect="plain" size="small">仅显示我的操作</el-tag>
        <el-input
          v-model="filters.keyword"
          :placeholder="t('audit.keywordPlaceholder')"
          clearable
          style="width: 200px"
          @keyup.enter="handleSearch"
        />
        <el-date-picker
          v-model="dateRange"
          type="datetimerange"
          :range-separator="t('audit.rangeSeparator')"
          :start-placeholder="t('audit.startTime')"
          :end-placeholder="t('audit.endTime')"
          value-format="YYYY-MM-DD HH:mm:ss"
          style="width: 340px"
        />
        <el-button type="primary" @click="handleSearch">
          <el-icon><Search /></el-icon>{{ t('audit.query') }}
        </el-button>
        <el-button @click="handleReset">{{ t('audit.reset') }}</el-button>
      </div>

      <el-table :data="logs" stripe v-loading="loading" style="width: 100%">
        <el-table-column :label="t('audit.time')" width="160">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column :label="t('audit.module')" width="110">
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="moduleTagType(row.module)"
              effect="plain"
              class="tag-filter"
              :title="`点击按模块「${moduleLabel(row)}」筛选`"
              @click.stop="applyTagFilter('module', row.module)"
            >
              {{ moduleLabel(row) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('audit.action')" width="90">
          <template #default="{ row }">
            <span
              :class="actionClass(row.action)"
              class="tag-filter action-filter"
              role="button"
              tabindex="0"
              :title="`点击按动作「${actionLabel(row)}」筛选`"
              @click.stop="applyTagFilter('action', row.action)"
              @keyup.enter="applyTagFilter('action', row.action)"
            >{{ actionLabel(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="target_name" :label="t('audit.target')" min-width="170" show-overflow-tooltip>
          <template #default="{ row }">{{ row.target_name || row.target_id || '-' }}</template>
        </el-table-column>
        <el-table-column v-if="!isCompact" prop="operator" :label="t('audit.operator')" width="110" />
        <el-table-column v-if="!isCompact" prop="ip" label="IP" width="120">
          <template #default="{ row }">{{ row.ip || '-' }}</template>
        </el-table-column>
        <el-table-column :label="t('audit.status')" width="90">
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="row.status === 'success' ? 'success' : 'danger'"
              class="tag-filter"
              :title="`点击按状态「${row.status === 'success' ? t('audit.success') : t('audit.failed')}」筛选`"
              @click.stop="applyTagFilter('status', row.status)"
            >
              {{ row.status === 'success' ? t('audit.success') : t('audit.failed') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="!isTablet" :label="t('audit.changedFields')" width="120">
          <template #default="{ row }">
            <el-tag v-if="row.changed && row.changed.length" size="small" type="warning" effect="plain">
              {{ t('audit.changedCount', { count: row.changed.length }) }}
            </el-tag>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('audit.actions')" width="85" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="openDetail(row)">
              {{ t('audit.detail') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!loading && logs.length === 0" :description="t('audit.noLogs')" />

      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="size"
          :page-sizes="[20, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          @current-change="loadLogs"
          @size-change="handleSearch"
        />
      </div>
    </el-card>

    <el-dialog v-model="detailVisible" :title="t('audit.detailTitle')" width="860px" top="6vh">
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item :label="t('audit.time')">{{ formatDateTime(detail?.created_at) }}</el-descriptions-item>
        <el-descriptions-item :label="t('audit.module')">{{ detail?.module_label }}</el-descriptions-item>
        <el-descriptions-item :label="t('audit.action')">{{ detail?.action_label }}</el-descriptions-item>
        <el-descriptions-item :label="t('audit.target')">{{ detail?.target_name || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="t('audit.operator')">{{ detail?.operator }}</el-descriptions-item>
        <el-descriptions-item label="IP">{{ detail?.ip || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="t('audit.message')" :span="2">{{ detail?.message || '-' }}</el-descriptions-item>
      </el-descriptions>

      <div class="diff-title">{{ t('audit.changedFields') }}</div>
      <el-tag
        v-for="key in detail?.changed || []"
        :key="key"
        size="small"
        type="warning"
        effect="plain"
        class="diff-tag"
      >
        {{ key }}
      </el-tag>
      <span v-if="!detail?.changed?.length" class="muted">{{ t('audit.noDiff') }}</span>

      <div class="json-grid">
        <div>
          <div class="json-title">{{ t('audit.before') }}</div>
          <pre class="json-body">{{ pretty(detail?.before) }}</pre>
        </div>
        <div>
          <div class="json-title">{{ t('audit.after') }}</div>
          <pre class="json-body">{{ pretty(detail?.after) }}</pre>
        </div>
      </div>

      <template #footer>
        <el-button @click="detailVisible = false">{{ t('audit.close') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { t } from '@/i18n'
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { auditApi } from '@/api'
import { can, currentUser, downloadWithAuth } from '@/store/auth'
import { formatDateTime } from '@/utils/time'
import { useResponsiveViewport } from '@/composables/useResponsiveViewport'

const { isTablet, isCompact } = useResponsiveViewport()

const isSuperuser = computed(() => currentUser.value?.is_superuser === true)

const loading = ref(false)
const logs = ref([])
const total = ref(0)
const page = ref(1)
const size = ref(20)
const modules = ref([])
const actions = ref([])
const retentionDays = ref(180)
const dateRange = ref([])

const filters = reactive({
  module: '',
  action: '',
  status: '',
  operator: '',
  keyword: '',
})

const detailVisible = ref(false)
const detail = ref(null)

function params() {
  const result = {
    page: page.value,
    size: size.value,
  }
  if (filters.module) result.module = filters.module
  if (filters.action) result.action = filters.action
  if (filters.status) result.status = filters.status
  if (filters.operator) result.operator = filters.operator
  if (filters.keyword) result.keyword = filters.keyword
  if (dateRange.value?.length === 2) {
    result.start = dateRange.value[0]
    result.end = dateRange.value[1]
  }
  return result
}

async function loadMeta() {
  try {
    const res = await auditApi.meta()
    modules.value = (res.data.modules || []).map((item) => ({
      value: item.value,
      label: t(`audit.module.${item.value}`) || item.label,
    }))
    actions.value = (res.data.actions || []).map((item) => ({
      value: item.value,
      label: t(`audit.action.${item.value}`) || item.label,
    }))
    retentionDays.value = res.data.retention_days ?? 0
  } catch {
    /* 忽略 */
  }
}

async function loadLogs() {
  loading.value = true
  try {
    const res = await auditApi.logs(params())
    logs.value = res.data.items || []
    total.value = res.data.total || 0
  } catch (e) {
    ElMessage.error(e.message || t('audit.loadFailed'))
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  page.value = 1
  loadLogs()
}

function handleReset() {
  filters.module = ''
  filters.action = ''
  filters.status = ''
  filters.operator = ''
  filters.keyword = ''
  dateRange.value = []
  handleSearch()
}

function applyTagFilter(kind, value) {
  if (!value) return
  filters[kind] = filters[kind] === value ? '' : value
  page.value = 1
  loadLogs()
}

function openDetail(row) {
  detail.value = row
  detailVisible.value = true
}

function pretty(value) {
  try {
    return JSON.stringify(value || {}, null, 2)
  } catch {
    return String(value)
  }
}

function moduleLabel(row) {
  if (!row) return '-'
  return t(`audit.module.${row.module}`) || row.module_label || row.module
}

function actionLabel(row) {
  if (!row) return '-'
  return t(`audit.action.${row.action}`) || row.action_label || row.action
}

function moduleTagType(module) {
  return {
    settings: 'primary',
    users: 'success',
    roles: 'success',
    groups: 'success',
    notifications: 'warning',
    config: 'info',
    security: 'danger',
    audit: 'info',
  }[module] || 'info'
}

function actionClass(action) {
  return {
    create: 'act-create',
    update: 'act-update',
    delete: 'act-delete',
    import: 'act-import',
    export: 'act-export',
    login: 'act-login',
    cleanup: 'act-delete',
  }[action] || ''
}

function handleExport(format) {
  const query = new URLSearchParams({ format })
  const p = params()
  Object.entries(p).forEach(([key, value]) => {
    if (key !== 'page' && key !== 'size' && value !== undefined && value !== '') {
      query.append(key, value)
    }
  })
  downloadWithAuth(`/api/audit/export?${query.toString()}`)
}

async function handleCleanup() {
  try {
    const { value } = await ElMessageBox.prompt(
      t('audit.cleanupPrompt'),
      t('audit.cleanupTitle'),
      {
        confirmButtonText: t('audit.cleanupConfirm'),
        cancelButtonText: t('common.cancel'),
        inputPattern: /^[1-9]\d{0,3}$/,
        inputErrorMessage: t('audit.cleanupInputError'),
        inputValue: String(retentionDays.value || 180),
      }
    )
    const days = Number(value)
    const res = await auditApi.cleanup(days)
    ElMessage.success(t('audit.cleanedCount', { count: res.data.deleted }))
    loadLogs()
  } catch {
    /* 取消 */
  }
}

onMounted(() => {
  loadMeta()
  loadLogs()
})
</script>

<style scoped>
.audit-view {
  height: 100%;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 600;
}

.actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.muted {
  color: #909399;
  font-size: 12px;
  font-weight: 400;
}

.filters {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}

.tag-filter {
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease, opacity 0.15s ease;
}

.tag-filter:hover {
  transform: translateY(-1px);
  box-shadow: 0 3px 8px rgba(64, 158, 255, 0.18);
  opacity: 0.88;
}

.action-filter {
  display: inline-block;
  border-radius: 3px;
  outline: none;
}

.action-filter:focus-visible {
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.3);
}

.act-create {
  color: #22c55e;
  font-weight: 600;
}

.act-update {
  color: #409eff;
  font-weight: 600;
}

.act-delete {
  color: #ef4444;
  font-weight: 600;
}

.act-import {
  color: #e6a23c;
  font-weight: 600;
}

.act-export {
  color: #8b5cf6;
  font-weight: 600;
}

.act-login {
  color: #06b6d4;
  font-weight: 600;
}

.diff-title {
  margin: 16px 0 8px;
  font-weight: 600;
  font-size: 13px;
}

.diff-tag {
  margin: 0 6px 6px 0;
}

.json-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 10px;
}

.json-title {
  font-size: 12px;
  color: #909399;
  margin-bottom: 6px;
}

.json-body {
  margin: 0;
  padding: 10px;
  background: #f8fafc;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  max-height: 320px;
  overflow: auto;
  font-size: 12px;
  line-height: 1.5;
}
</style>
