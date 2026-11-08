<template>
  <div class="website-monitor">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>{{ t('website.title') }}</span>
          <div class="actions">
            <el-button size="small" @click="$router.push('/bigscreen/website')">
              <el-icon><Monitor /></el-icon>网站大屏
            </el-button>
            <el-button size="small" @click="$router.push('/website/certificates')">
              <el-icon><Key /></el-icon>证书管理
            </el-button>
            <el-button size="small" @click="importVisible = true">
              <el-icon><Upload /></el-icon>批量导入
            </el-button>
            <el-button size="small" @click="exportTargets">
              <el-icon><Download /></el-icon>导出 CSV
            </el-button>
            <el-button type="primary" size="small" @click="addTarget">
              <el-icon><Plus /></el-icon>{{ t('website.addMonitor') }}
            </el-button>
          </div>
        </div>
      </template>

      <div class="website-toolbar">
        <el-input v-model="search" size="small" clearable placeholder="名称 / URL / 域名 / IP" class="toolbar-search" @keyup.enter="applyFilters">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-select v-model="category" size="small" clearable placeholder="分类" class="toolbar-select" @change="applyFilters">
          <el-option v-for="item in categoryOptions" :key="item" :label="item" :value="item" />
        </el-select>
        <el-select v-model="enabledFilter" size="small" class="toolbar-select" @change="applyFilters">
          <el-option label="全部状态" value="all" />
          <el-option label="仅启用" value="true" />
          <el-option label="仅停用" value="false" />
        </el-select>
        <el-date-picker
          v-model="dateRange"
          size="small"
          type="daterange"
          value-format="YYYY-MM-DD"
          start-placeholder="创建开始"
          end-placeholder="创建结束"
          class="toolbar-date"
          @change="applyFilters"
        />
        <el-button size="small" type="primary" @click="applyFilters">查询</el-button>
        <el-button size="small" @click="resetFilters">重置</el-button>
        <span class="batch-order-divider"></span>
        <span class="batch-order-tip">当前页已选 {{ selectedIds.length }} 项</span>
        <el-button size="small" :disabled="!selectedIds.length" @click="moveSelected(-1)">
          <el-icon><ArrowUp /></el-icon>批量上移
        </el-button>
        <el-button size="small" :disabled="!selectedIds.length" @click="moveSelected(1)">
          <el-icon><ArrowDown /></el-icon>批量下移
        </el-button>
      </div>

      <el-table
        ref="websiteTableRef"
        :data="targets"
        row-key="id"
        stripe
        v-loading="loading"
        @header-dragend="onHeaderDragEnd"
        @sort-change="onSortChange"
        @selection-change="onSelectionChange"
      >
        <el-table-column type="selection" width="42" />
        <el-table-column prop="name" :label="t('website.monitorName')" width="130" sortable="custom" />
        <el-table-column
          prop="url"
          label="URL"
          :width="urlColumnWidth || undefined"
          :min-width="urlColumnWidth ? undefined : 170"
          sortable="custom"
          show-overflow-tooltip
        />
        <el-table-column
          :label="t('website.monitorTrend')"
          min-width="110"
          header-align="center"
          align="center"
          class-name="trend-column"
        >
          <template #default="{ row }">
            <div v-if="sparkline(row).hasData" class="sparkline-wrap" :title="sparkline(row).title">
              <svg
                class="sparkline"
                viewBox="0 0 120 30"
                preserveAspectRatio="none"
                role="img"
                :aria-label="t('website.monitorTrend')"
              >
                <defs>
                  <linearGradient :id="sparkline(row).gradientId" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" :stop-color="sparkline(row).color" stop-opacity="0.34" />
                    <stop offset="100%" :stop-color="sparkline(row).color" stop-opacity="0.02" />
                  </linearGradient>
                </defs>
                <path :d="sparkline(row).area" :fill="`url(#${sparkline(row).gradientId})`" />
                <path
                  :d="sparkline(row).line"
                  fill="none"
                  :stroke="sparkline(row).color"
                  stroke-width="1.6"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  vector-effect="non-scaling-stroke"
                  class="spark-line"
                />
                <circle
                  :cx="sparkline(row).last.x"
                  :cy="sparkline(row).last.y"
                  r="2.1"
                  :fill="sparkline(row).color"
                  class="spark-latest"
                />
              </svg>
              <span class="spark-value" :style="{ color: sparkline(row).color }">
                {{ sparkline(row).latestLabel }}
              </span>
            </div>
            <span v-else class="spark-empty">{{ t('website.noTrendData') }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('website.type')" width="70">
          <template #default="{ row }">
            <el-tag :type="getTypeColor(row.monitor_type)" size="small">
              {{ getTypeName(row.monitor_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="category" label="分类" width="105" sortable="custom">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" type="info">{{ row.category || '未分类' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('website.certIssuerColumn')" width="145">
          <template #default="{ row }">
            <span
              v-if="certInfo(row)"
              class="cert-issuer"
              :title="`${t('website.certOwner')}: ${certInfo(row).owner || t('website.certOrgUnknown')}`"
            >
              {{ certInfo(row).issuer || certInfo(row).issuer_organization || '-' }}
            </span>
            <span v-else class="cert-empty">-</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('website.certValidTo')" width="135">
          <template #default="{ row }">
            <div v-if="certInfo(row)" class="cert-expiry" :title="certInfo(row).valid_to || ''">
              <span class="cert-date">{{ certExpiryDate(certInfo(row)) }}</span>
              <el-tag :type="certTagType(certInfo(row))" size="small">
                {{ certDaysText(certInfo(row)) }}
              </el-tag>
            </div>
            <span v-else class="cert-empty">-</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('website.aliveStatus')" width="70">
          <template #default="{ row }">
            <el-tag :type="row.latest_status?.is_alive ? 'success' : 'danger'" size="small">
              {{ row.latest_status?.is_alive ? t('website.normal') : t('website.abnormal') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态码" width="78" sortable="custom" prop="expected_status">
          <template #default="{ row }">
            <span :class="statusCodeClass(row)">{{ row.latest_status?.status_code ?? '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('website.responseTime')" width="85">
          <template #default="{ row }">
            <span :class="{ slow: row.latest_status?.response_time > 5000 }">
              {{ formatLatency(row.latest_status?.response_time) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column :label="t('website.lastCheck')" width="130">
          <template #default="{ row }">
            {{ row.latest_status?.checked_at ? formatTime(row.latest_status.checked_at) : '-' }}
          </template>
        </el-table-column>
        <el-table-column :label="t('website.enable')" width="60">
          <template #default="{ row }">
            <el-switch v-model="row.is_enabled" @change="toggleTarget(row)" />
          </template>
        </el-table-column>
        <el-table-column :label="t('website.actions')" width="230" fixed="right">
          <template #default="{ row, $index }">
            <el-button type="primary" link size="small" @click="openTarget(row)">
              {{ t('website.detail') }}
            </el-button>
            <el-button type="primary" link size="small" @click="editTarget(row)">
              {{ t('website.edit') }}
            </el-button>
            <el-button
              type="primary"
              link
              size="small"
              title="上移"
              :disabled="$index === 0"
              @click="moveTarget(row, -1)"
            >
              <el-icon><ArrowUp /></el-icon>
            </el-button>
            <el-button
              type="primary"
              link
              size="small"
              title="下移"
              :disabled="$index === targets.length - 1"
              @click="moveTarget(row, 1)"
            >
              <el-icon><ArrowDown /></el-icon>
            </el-button>
            <el-button type="danger" link size="small" @click="removeTarget(row)">{{ t('website.delete') }}</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="website-pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          background
          layout="total, prev, pager, next"
          :total="total"
          @current-change="onWebsitePageChange"
          @size-change="onWebsiteSizeChange"
        />
      </div>

      <el-dialog v-model="importVisible" title="批量导入网站监控" width="560px" :close-on-click-modal="false">
        <el-alert type="info" :closable="false" show-icon title="支持 CSV，UTF-8 / GBK 编码均可。列名见模板；URL 支持域名和 IP，重复 URL 默认跳过。" />
        <div class="import-actions">
          <el-button link type="primary" @click="downloadTemplate">下载导入模板</el-button>
        </div>
        <el-upload
          drag
          :auto-upload="false"
          :limit="1"
          accept=".csv,text/csv"
          :on-change="onImportFileChange"
          :on-remove="() => { importFile = null }"
        >
          <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
          <div class="el-upload__text">拖拽 CSV 到此处，或<em>点击选择</em></div>
        </el-upload>
        <div class="import-mode">
          <span>重复 URL 处理：</span>
          <el-radio-group v-model="importMode" size="small">
            <el-radio-button value="skip">跳过</el-radio-button>
            <el-radio-button value="update">更新已有</el-radio-button>
          </el-radio-group>
        </div>
        <template #footer>
          <el-button @click="importVisible = false">取消</el-button>
          <el-button type="primary" :loading="importing" :disabled="!importFile" @click="submitImport">开始导入</el-button>
        </template>
      </el-dialog>

      <el-empty v-if="!loading && targets.length === 0" :description="t('website.noTargets')" />
    </el-card>
  </div>
</template>

<script setup>
import { t } from '@/i18n'
import { ref, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { websiteApi } from '@/api'
import { downloadWithAuth } from '@/store/auth'
import { formatDateTime } from '@/utils/time'
import { formatLatency } from '@/utils/latency'
import { useRouter, useRoute } from 'vue-router'

const COLUMN_WIDTH_STORAGE_KEY = 'nms_website_table_widths_v1'
const router = useRouter()
const route = useRoute()
const targets = ref([])
const loading = ref(false)
const websiteTableRef = ref(null)
const search = ref('')
const category = ref('')
const enabledFilter = ref('all')
const dateRange = ref([])
const categoryOptions = ref([])
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const sortBy = ref('sort_order')
const sortOrder = ref('asc')
const importVisible = ref(false)
const importFile = ref(null)
const importMode = ref('skip')
const importing = ref(false)
const selectedIds = ref([])
let refreshTimer = null
const viewportWidth = ref(typeof window === 'undefined' ? 1600 : window.innerWidth)
// 超宽屏时限制 URL 列，避免它无限拉伸把“监控趋势”列推到页面右侧
const urlColumnWidth = computed(() => (
  viewportWidth.value >= 2400
    ? Math.min(420, Math.max(320, Math.round(viewportWidth.value * 0.113)))
    : null
))

function onViewportResize() {
  viewportWidth.value = window.innerWidth
}

function getTypeColor(type) {
  const colors = { http: '', https: 'success', tcp: 'warning', ping: 'info' }
  return colors[type] || 'info'
}

function getTypeName(type) {
  const names = { http: 'HTTP', https: 'HTTPS', tcp: 'TCP', ping: 'PING' }
  return names[type] || type
}

function formatTime(iso) {
  return formatDateTime(iso)
}

function certInfo(row) {
  const info = row?.latest_status?.cert_info
  return info && !info.error && info.valid_to ? info : null
}

function certTagType(info) {
  if (!info) return 'info'
  const days = Number(info.days_left)
  if (days < 0) return 'danger'
  if (days <= 30) return 'warning'
  return 'success'
}

function certDaysText(info) {
  if (!info) return '-'
  const days = Number(info.days_left)
  if (Number.isNaN(days)) return '-'
  if (days < 0) return t('website.certExpired')
  return t('website.certDayUnit', { days })
}

function certExpiryDate(info) {
  if (!info?.valid_to) return '-'
  return String(info.valid_to).slice(0, 10)
}

function sparkline(row) {
  const checks = Array.isArray(row.recent_checks) ? row.recent_checks : []
  const latest = row.latest_status || {}
  const values = checks.length
    ? checks.map((check) => (check.is_alive ? Math.max(0, Number(check.response_time) || 0) : 0))
    : (latest.response_time ? [Math.max(0, Number(latest.response_time) || 0)] : [])
  if (!values.length) {
    return { hasData: false }
  }
  const width = 120
  const height = 30
  const pad = 3
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = Math.max(1, max - min)
  const step = values.length > 1 ? (width - pad * 2) / (values.length - 1) : 0
  let points = values.map((value, index) => ({
    x: pad + index * step,
    y: height - pad - ((value - min) / span) * (height - pad * 2),
  }))
  if (points.length === 1) {
    points = [points[0], { ...points[0], x: width - pad }]
  }
  const line = points.map((point, index) => `${index === 0 ? 'M' : 'L'}${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(' ')
  const area = `${line} L${points[points.length - 1].x.toFixed(2)},${height} L${points[0].x.toFixed(2)},${height} Z`
  const lastCheck = checks.length ? checks[checks.length - 1] : latest
  const latestValue = Number(lastCheck?.response_time || 0)
  const isDown = lastCheck?.is_alive === false
  const isSlow = !isDown && latestValue > Math.max(1000, Number(row.slow_threshold_ms || 5000))
  const color = isDown ? '#f87171' : (isSlow ? '#fbbf24' : '#38bdf8')
  const latestLabel = isDown ? t('website.abnormal') : formatLatency(latestValue)
  return {
    hasData: true,
    line,
    area,
    last: points[points.length - 1],
    color,
    latestLabel,
    gradientId: `wspark-${row.id}`,
    title: `最近 ${values.length} 次检查 · 最低 ${formatLatency(min)} · 最高 ${formatLatency(max)}`,
  }
}

function tableColumns() {
  return websiteTableRef.value?.store?.states?.columns?.value || []
}

function persistTableWidths() {
  const columns = tableColumns()
  if (!columns.length) return
  const widths = columns.map((column) => Math.round(Number(column.realWidth || column.width || 0))).filter((width) => width > 0)
  try {
    localStorage.setItem(COLUMN_WIDTH_STORAGE_KEY, JSON.stringify(widths))
  } catch {
    /* 忽略存储异常 */
  }
}

async function restoreTableWidths() {
  await nextTick()
  const table = websiteTableRef.value
  const columns = tableColumns()
  if (!table || !columns.length) return
  let widths = []
  try {
    widths = JSON.parse(localStorage.getItem(COLUMN_WIDTH_STORAGE_KEY) || '[]')
  } catch {
    widths = []
  }
  if (!Array.isArray(widths) || widths.length !== columns.length) return
  let changed = false
  columns.forEach((column, index) => {
    const width = Number(widths[index])
    if (Number.isFinite(width) && width >= 80) {
      column.width = width
      changed = true
    }
  })
  if (changed) {
    await nextTick()
    table.doLayout?.()
  }
}

function onHeaderDragEnd(newWidth, oldWidth, column) {
  const table = websiteTableRef.value
  const columns = table?.store?.states?.columns?.value || []
  if (!table) return
  if (column?.property === 'url') {
    const trend = columns.find((item) => String(item.label || '').includes('监控趋势'))
    if (trend) {
      const oldTrendWidth = Number(trend.realWidth || trend.width || 0)
      const delta = Math.round(Number(newWidth) - Number(oldWidth))
      if (oldTrendWidth && Number.isFinite(delta)) {
        // URL 变宽多少，监控趋势就收窄多少；反之亦然，后续列位置保持不变
        const minTrendWidth = 140
        const maxGrow = Math.max(0, oldTrendWidth - minTrendWidth)
        const adjustedDelta = delta > maxGrow ? maxGrow : delta
        if (adjustedDelta !== delta) {
          const url = columns.find((item) => item.property === 'url')
          if (url) url.width = Number(oldWidth) + adjustedDelta
        }
        trend.width = Math.max(minTrendWidth, oldTrendWidth - adjustedDelta)
      }
    }
  }
  requestAnimationFrame(() => {
    table.doLayout?.()
    persistTableWidths()
  })
}

function websiteQuery() {
  const query = {}
  if (page.value > 1) query.page = String(page.value)
  if (pageSize.value !== 20) query.size = String(pageSize.value)
  if (search.value.trim()) query.search = search.value.trim()
  if (category.value) query.category = category.value
  if (enabledFilter.value !== 'all') query.enabled = String(enabledFilter.value)
  if (dateRange.value?.[0]) query.start = dateRange.value[0]
  if (dateRange.value?.[1]) query.end = dateRange.value[1]
  if (sortBy.value !== 'sort_order') query.sort_by = sortBy.value
  if (sortOrder.value !== 'asc') query.sort_order = sortOrder.value
  return query
}

function restoreWebsiteContext() {
  const q = route.query
  const qPage = Number(q.page)
  const qSize = Number(q.size)
  if (Number.isFinite(qPage) && qPage > 0) page.value = Math.floor(qPage)
  if (Number.isFinite(qSize) && [10, 20, 50, 100].includes(Math.floor(qSize))) pageSize.value = Math.floor(qSize)
  if (typeof q.search === 'string') search.value = q.search
  if (typeof q.category === 'string') category.value = q.category
  if (typeof q.enabled === 'string' && ['true', 'false'].includes(q.enabled)) enabledFilter.value = q.enabled
  if (typeof q.start === 'string') dateRange.value = [q.start, typeof q.end === 'string' ? q.end : '']
  if (typeof q.sort_by === 'string') sortBy.value = q.sort_by
  if (typeof q.sort_order === 'string') sortOrder.value = q.sort_order
}

function addTarget() {
  router.push({ path: '/website/add', query: websiteQuery() })
}

function openTarget(row) {
  router.push({ path: `/website/${row.id}`, query: websiteQuery() })
}

function editTarget(row) {
  router.push({ path: `/website/edit/${row.id}`, query: websiteQuery() })
}

async function loadTargets(silent = false) {
  if (!silent) loading.value = true
  try {
    const params = {
      page: page.value,
      size: pageSize.value,
      search: search.value.trim() || undefined,
      category: category.value || undefined,
      is_enabled: enabledFilter.value === 'all' ? undefined : enabledFilter.value === 'true',
      start_time: dateRange.value?.[0] || undefined,
      end_time: dateRange.value?.[1] || undefined,
      sort_by: sortBy.value,
      sort_order: sortOrder.value,
    }
    const res = await websiteApi.getList(params)
    targets.value = res.data.items
    total.value = Number(res.data.total || 0)
    if (!silent) await loadCategories()
  } catch (e) {
    if (!silent) ElMessage.error(e.message || t('website.loadTargetsFailed'))
  } finally {
    if (!silent) loading.value = false
  }
}

async function loadCategories() {
  try {
    const res = await websiteApi.categories()
    categoryOptions.value = res.data.items || []
  } catch {
    categoryOptions.value = []
  }
}

function syncWebsiteQuery() {
  router.replace({ path: '/website', query: websiteQuery() })
}

function onWebsitePageChange() {
  syncWebsiteQuery()
  loadTargets()
}

function onWebsiteSizeChange() {
  page.value = 1
  syncWebsiteQuery()
  loadTargets()
}

function applyFilters() {
  page.value = 1
  syncWebsiteQuery()
  loadTargets()
}

function resetFilters() {
  search.value = ''
  category.value = ''
  enabledFilter.value = 'all'
  dateRange.value = []
  sortBy.value = 'sort_order'
  sortOrder.value = 'asc'
  page.value = 1
  syncWebsiteQuery()
  loadTargets()
}

function onSortChange({ prop, order }) {
  if (!order) {
    sortBy.value = 'sort_order'
    sortOrder.value = 'asc'
  } else {
    sortBy.value = prop || 'sort_order'
    sortOrder.value = order === 'descending' ? 'desc' : 'asc'
  }
  page.value = 1
  syncWebsiteQuery()
  loadTargets()
}

function statusCodeClass(row) {
  const code = Number(row?.latest_status?.status_code)
  if (!code) return 'status-code-empty'
  if (row?.latest_status?.is_alive) return 'status-code-ok'
  return 'status-code-bad'
}

async function moveTarget(row, direction) {
  const index = targets.value.findIndex((item) => item.id === row.id)
  if (index < 0) return
  await moveRows([row.id], direction)
}

async function moveSelected(direction) {
  if (!selectedIds.value.length) return
  await moveRows(selectedIds.value, direction)
}

async function moveRows(ids, direction) {
  const idSet = new Set(ids.map((id) => Number(id)))
  const current = [...targets.value]
  const selected = current.filter((item) => idSet.has(Number(item.id)))
  if (!selected.length) return
  const firstIndex = current.findIndex((item) => idSet.has(Number(item.id)))
  const lastIndex = current.length - 1 - [...current].reverse().findIndex((item) => idSet.has(Number(item.id)))
  if (direction < 0 && firstIndex <= 0) return
  if (direction > 0 && lastIndex >= current.length - 1) return
  const remaining = current.filter((item) => !idSet.has(Number(item.id)))
  const anchor = direction < 0
    ? current[firstIndex - 1]
    : current[lastIndex + 1]
  const anchorIndex = remaining.findIndex((item) => item.id === anchor.id)
  if (anchorIndex < 0) return
  const insertAt = direction < 0 ? anchorIndex : anchorIndex + 1
  const ordered = [...remaining]
  ordered.splice(insertAt, 0, ...selected)
  try {
    await websiteApi.reorder(ordered.map((item) => item.id))
    sortBy.value = 'sort_order'
    sortOrder.value = 'asc'
    selectedIds.value = []
    await loadTargets()
    websiteTableRef.value?.clearSelection?.()
    ElMessage.success('排序已保存')
  } catch (e) {
    ElMessage.error(e.message || '排序失败')
  }
}

function onSelectionChange(rows) {
  selectedIds.value = (rows || []).map((row) => row.id)
}

function exportTargets() {
  downloadWithAuth(websiteApi.exportUrl())
}

function onImportFileChange(uploadFile) {
  importFile.value = uploadFile.raw || null
}

function downloadTemplate() {
  const headers = [
    'name', 'url', 'monitor_type', 'domain', 'ip_address', 'port', 'method',
    'expected_status', 'expected_statuses', 'expected_keywords', 'timeout',
    'check_interval', 'slow_threshold_ms', 'ignore_https_errors',
    'cache_bust_seconds', 'cert_monitor_enabled', 'cert_expiry_days',
    'cert_alert_level', 'cert_root_domain', 'cert_subdomains', 'category',
    'category_mode', 'sort_order', 'is_enabled', 'description',
  ]
  const blob = new Blob([`\ufeff${headers.join(',')}\n`], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'website-monitor-import-template.csv'
  link.click()
  URL.revokeObjectURL(url)
}

async function submitImport() {
  if (!importFile.value) return
  importing.value = true
  try {
    const res = await websiteApi.importTargets(importFile.value, importMode.value)
    const data = res.data
    const errors = data.errors || []
    ElMessage.success(`导入完成：新增 ${data.created}，更新 ${data.updated}，跳过 ${data.skipped}${errors.length ? `，失败 ${errors.length}` : ''}`)
    if (errors.length) {
      ElMessage.warning(`前 ${Math.min(errors.length, 5)} 条失败：${errors.slice(0, 5).map((item) => `第${item.row}行 ${item.message}`).join('；')}`)
    }
    importVisible.value = false
    importFile.value = null
    page.value = 1
    await loadTargets()
  } catch (e) {
    ElMessage.error(e.message || '导入失败')
  } finally {
    importing.value = false
  }
}

async function toggleTarget(row) {
  try {
    await websiteApi.toggle(row.id)
    ElMessage.success(row.is_enabled ? t('website.enabled') : t('website.disabled'))
  } catch (e) {
    row.is_enabled = !row.is_enabled
    ElMessage.error(e.message || t('website.operationFailed'))
  }
}

async function removeTarget(row) {
  try {
    await ElMessageBox.confirm(t('website.confirmDeleteTarget', { name: row.name }), t('website.confirmDelete'), { type: 'warning' })
    await websiteApi.remove(row.id)
    ElMessage.success(t('website.deleted'))
    if (targets.value.length === 1 && page.value > 1) page.value -= 1
    syncWebsiteQuery()
    loadTargets()
  } catch {
    /* 取消或失败 */
  }
}

onMounted(async () => {
  restoreWebsiteContext()
  await loadTargets()
  await restoreTableWidths()
  window.addEventListener('resize', onViewportResize)
  refreshTimer = setInterval(() => {
    if (!document.hidden) loadTargets(true)
  }, 15000)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onViewportResize)
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<style scoped>
.website-monitor {
  height: 100%;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.actions {
  display: flex;
  gap: 8px;
}

.website-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
  padding: 10px 12px;
  border: 1px solid #e4edf4;
  border-radius: 7px;
  background: #f8fbfd;
}
.toolbar-search { width: 220px; }
.toolbar-select { width: 118px; }
.toolbar-date { width: 235px; }
.batch-order-divider { width: 1px; height: 20px; background: #dbe7ef; margin: 0 3px; }
.batch-order-tip { color: #6d8494; font-size: 11px; white-space: nowrap; }

.website-pager {
  display: flex;
  justify-content: flex-end;
  padding-top: 12px;
}

.status-code-ok { color: #15803d; font-weight: 700; font-variant-numeric: tabular-nums; }
.status-code-bad { color: #dc2626; font-weight: 700; font-variant-numeric: tabular-nums; }
.status-code-empty { color: #94a3b8; }

.import-actions { margin: 8px 0; }
.import-mode { display: flex; align-items: center; gap: 8px; padding-top: 12px; color: #5f7383; font-size: 12px; }

@media (max-width: 1200px) {
  .toolbar-search { width: 180px; }
  .toolbar-date { width: 210px; }
}
@media (max-width: 760px) {
  .website-toolbar { align-items: stretch; }
  .toolbar-search, .toolbar-select, .toolbar-date { width: 100%; }
}

.slow {
  color: #f5222d;
  font-weight: bold;
}

.sparkline-wrap {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  justify-content: center;
  gap: 1px;
  width: 100%;
  max-width: 900px;
  min-height: 44px;
  margin: 0 auto;
}

.sparkline {
  display: block;
  width: 100%;
  height: 32px;
  min-width: 0;
  margin: 0 auto;
  overflow: visible;
}

.spark-line {
  filter: drop-shadow(0 0 3px rgba(56, 189, 248, 0.35));
  transform-origin: center;
  animation: spark-fade 0.55s ease-out;
}

.spark-latest {
  animation: spark-pulse 1.8s ease-in-out infinite;
}

.spark-value {
  flex-shrink: 0;
  text-align: center;
  margin: 0 auto;
  font-size: 11px;
  font-weight: 700;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}

:deep(.trend-column .cell) {
  width: 100%;
  display: flex;
  justify-content: center;
  text-align: center;
}

.spark-empty {
  color: #94a3b8;
  font-size: 12px;
}

.cert-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  line-height: 1.35;
}

.cert-issuer {
  display: block;
  color: #334155;
  font-size: 12px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.cert-expiry {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  line-height: 1.25;
}

.cert-date {
  color: #334155;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.cert-empty {
  color: #94a3b8;
}

@keyframes spark-fade {
  from {
    opacity: 0.25;
  }
  to {
    opacity: 1;
  }
}

@keyframes spark-pulse {
  0%, 100% {
    opacity: 1;
    r: 2.1;
  }
  50% {
    opacity: 0.55;
    r: 3.1;
  }
}
</style>
