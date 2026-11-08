<template>
  <div class="website-detail">
    <el-card v-loading="loading">
      <template #header>
        <div class="card-header">
          <el-button link @click="backToWebsite">
            <el-icon><Back /></el-icon>{{ t('website.back') }}
          </el-button>
          <span>{{ target?.name }} · {{ target?.url }}</span>
          <div>
            <el-button type="primary" link @click="loadAll">
              <el-icon><Refresh /></el-icon>{{ t('common.refresh') }}
            </el-button>
            <el-button type="primary" link @click="editWebsite">
              {{ t('website.edit') }}
            </el-button>
          </div>
        </div>
      </template>

      <el-descriptions :column="4" border>
        <el-descriptions-item :label="t('website.monitorType')">
          <el-tag size="small">{{ getTypeName(target?.monitor_type) }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="t('website.lastStatus')">
          <el-tag :type="latest?.is_alive ? 'success' : 'danger'">
            {{ latest?.is_alive ? t('website.normal') : t('website.abnormal') }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="t('website.responseTime')">
          {{ formatLatency(latest?.response_time) }}
        </el-descriptions-item>
        <el-descriptions-item label="状态码">
          {{ latest?.status_code ?? '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('website.lastCheck')">
          {{ formatDateTime(latest?.checked_at) }}
        </el-descriptions-item>
      </el-descriptions>

      <div v-if="latest?.cert_info" class="cert-panel">
        <div class="cert-panel-title">
          <span>{{ t('website.certSection') }}</span>
          <el-tag v-if="certInfo" :type="certTagType(certInfo)" size="small">
            {{ certStatusLabel(certInfo) }}
          </el-tag>
        </div>
        <el-descriptions v-if="certInfo" :column="3" border size="small">
          <el-descriptions-item :label="t('website.certOwner')">
            <strong>{{ certInfo.owner || t('website.certOrgUnknown') }}</strong>
          </el-descriptions-item>
          <el-descriptions-item :label="t('website.certIssuer')">
            {{ certInfo.issuer || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('website.certDaysLeft')">
            <el-tag :type="certTagType(certInfo)" size="small">{{ certDaysText(certInfo) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('website.certValidFrom')">
            {{ formatDateTime(certInfo.valid_from) }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('website.certValidTo')">
            {{ formatDateTime(certInfo.valid_to) }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('website.certSerial')">
            <span class="cert-serial">{{ certInfo.serial_number || '-' }}</span>
          </el-descriptions-item>
        </el-descriptions>
        <el-collapse v-if="extraCertificates.length" class="extra-certs">
          <el-collapse-item :title="`根域名 / 额外子域名证书（${extraCertificates.length}）`">
            <el-table :data="extraCertificates" size="small" stripe>
              <el-table-column prop="host" label="证书域名" min-width="170" />
              <el-table-column prop="owner" label="所属单位" min-width="150" show-overflow-tooltip />
              <el-table-column prop="issuer" label="颁发机构" min-width="140" show-overflow-tooltip />
              <el-table-column label="剩余天数" width="110">
                <template #default="{ row }">
                  <el-tag :type="certTagType(row)" size="small">{{ certDaysText(row) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="到期时间" width="130">
                <template #default="{ row }">{{ formatDateTime(row.valid_to) }}</template>
              </el-table-column>
            </el-table>
          </el-collapse-item>
        </el-collapse>
        <el-alert
          v-if="!certInfo"
          type="warning"
          :closable="false"
          show-icon
          :title="t('website.certError')"
          :description="latest.cert_info.error || ''"
        />
      </div>

      <el-tabs v-model="activeTab" @tab-change="onTabChange">
        <el-tab-pane :label="t('website.checkHistory')" name="history">
          <div class="history-filter">
            <el-date-picker
              v-model="historyRange"
              type="daterange"
              value-format="YYYY-MM-DD"
              size="small"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              @change="applyHistoryFilter"
            />
            <el-button size="small" @click="applyHistoryFilter">查询</el-button>
            <el-button size="small" @click="resetHistoryFilter">重置</el-button>
          </div>
          <el-table :data="history" stripe style="width: 100%">
            <el-table-column :label="t('website.status')" width="80">
              <template #default="{ row }">
                <el-tag :type="row.is_alive ? 'success' : 'danger'" size="small">
                  {{ row.is_alive ? t('website.normal') : t('website.abnormal') }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="status_code" :label="t('website.statusCode')" width="80" />
            <el-table-column :label="t('website.responseTime')" width="120">
              <template #default="{ row }">
                {{ formatLatency(row.response_time) }}
              </template>
            </el-table-column>
            <el-table-column label="DNS/TCP/SSL(ms)" width="180">
              <template #default="{ row }">
                {{ fmtMs(row.dns_resolve_time) }} / {{ fmtMs(row.tcp_connect_time) }} /
                {{ fmtMs(row.ssl_time) }}
              </template>
            </el-table-column>
            <el-table-column prop="final_ip" :label="t('website.resolvedIp')" width="130" />
            <el-table-column :label="t('website.errorMessage')" min-width="200" show-overflow-tooltip>
              <template #default="{ row }">{{ row.http_error || row.error_message || '-' }}</template>
            </el-table-column>
            <el-table-column :label="t('website.checkTime')" width="170">
              <template #default="{ row }">{{ formatDateTime(row.checked_at) }}</template>
            </el-table-column>
          </el-table>

          <el-pagination
            v-model:current-page="historyPage"
            :total="historyTotal"
            :page-size="20"
            layout="total, prev, pager, next"
            class="pager"
            @current-change="loadHistory"
          />
        </el-tab-pane>

        <el-tab-pane :label="t('website.aliveStats')" name="stats">
          <div class="stats-row">
            <el-statistic :title="t('website.checkCount')" :value="stats.total_checks" />
            <el-statistic :title="t('website.aliveRatePct')" :value="stats.uptime_percent" />
            <el-statistic :title="t('website.avgResponse')" :value="stats.avg_response_time" />
            <el-statistic :title="t('website.maxResponse')" :value="stats.max_response_time" />
          </div>
          <div ref="uptimeChartRef" class="chart"></div>
        </el-tab-pane>

        <el-tab-pane :label="t('website.alert')" name="alerts">
          <el-table :data="alerts" stripe style="width: 100%">
            <el-table-column :label="t('website.type')" width="110">
              <template #default="{ row }">{{ row.alert_type }}</template>
            </el-table-column>
            <el-table-column :label="t('website.level')" width="90">
              <template #default="{ row }">
                <el-tag :type="alertLevelType(row.alert_level)" size="small" effect="dark">
                  {{ row.level_label || alertLevelText(row.alert_level) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="message" :label="t('website.info')" show-overflow-tooltip />
            <el-table-column :label="t('website.time')" width="170">
              <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column :label="t('website.status')" width="100">
              <template #default="{ row }">
                <el-tag :type="row.is_acknowledged ? 'success' : 'info'" size="small">
                  {{ row.is_acknowledged ? t('website.acknowledged') : t('website.unacknowledged') }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="t('website.actions')" width="100">
              <template #default="{ row }">
                <el-button
                  v-if="!row.is_acknowledged"
                  type="primary"
                  link
                  size="small"
                  @click="ackAlert(row.id)"
                >
                  {{ t('website.acknowledge') }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup>
import { t } from '@/i18n'
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import api from '@/api'
import { formatDateTime, formatHM } from '@/utils/time'
import { formatLatency } from '@/utils/latency'

function alertLevelText(level) {
  return { info: '提示', warning: '警告', critical: '严重', emergency: '紧急' }[level] || level || '警告'
}

function alertLevelType(level) {
  return { info: 'info', warning: 'warning', critical: 'danger', emergency: 'danger' }[level] || 'warning'
}

const route = useRoute()
const router = useRouter()

function websiteReturnQuery() {
  const query = {}
  for (const key of ['page', 'size', 'search', 'category', 'enabled', 'start', 'end', 'sort_by', 'sort_order']) {
    const value = route.query[key]
    if (typeof value === 'string' && value) query[key] = value
  }
  return query
}

function backToWebsite() {
  router.push({ path: '/website', query: websiteReturnQuery() })
}

function editWebsite() {
  router.push({ path: `/website/edit/${route.params.id}`, query: websiteReturnQuery() })
}
const loading = ref(false)
const target = ref(null)
const latest = ref(null)
const certInfo = computed(() => {
  const info = latest.value?.cert_info
  return info && !info.error && info.valid_to ? info : null
})
const extraCertificates = computed(() => (
  Array.isArray(certInfo.value?.extra_certificates)
    ? certInfo.value.extra_certificates.filter((item) => item && !item.error)
    : []
))
const history = ref([])
const historyTotal = ref(0)
const historyPage = ref(1)
const historyRange = ref([])
const alerts = ref([])
const stats = ref({
  total_checks: 0,
  uptime_percent: 0,
  avg_response_time: 0,
  max_response_time: 0,
})
const activeTab = ref('history')
const uptimeChartRef = ref(null)

let uptimeChart = null

function getTypeName(type) {
  const names = { http: 'HTTP', https: 'HTTPS', tcp: 'TCP', ping: 'PING' }
  return names[type] || type
}

function fmtMs(v) {
  return formatLatency(v)
}

function certTagType(info) {
  const days = Number(info?.days_left)
  if (days < 0) return 'danger'
  if (days <= 30) return 'warning'
  return 'success'
}

function certDaysText(info) {
  const days = Number(info?.days_left)
  if (Number.isNaN(days)) return '-'
  return days < 0 ? t('website.certExpired') : t('website.certDayUnit', { days })
}

function certStatusLabel(info) {
  const days = Number(info?.days_left)
  if (days < 0) return t('website.certExpired')
  if (days <= 30) return t('website.certExpiring')
  return t('website.certValid')
}

async function loadTarget() {
  const res = await api.get(`/website/targets/${route.params.id}`)
  target.value = res.data
  latest.value = res.data.latest_status
}

async function loadHistory() {
  const res = await api.get(`/website/targets/${route.params.id}/history`, {
    params: {
      page: historyPage.value,
      size: 20,
      start_time: historyRange.value?.[0] || undefined,
      end_time: historyRange.value?.[1] || undefined,
    },
  })
  history.value = res.data.items
  historyTotal.value = res.data.total
}

function applyHistoryFilter() {
  historyPage.value = 1
  loadHistory()
}

function resetHistoryFilter() {
  historyRange.value = []
  historyPage.value = 1
  loadHistory()
}

async function loadStats() {
  const res = await api.get(`/website/targets/${route.params.id}/stats`, {
    params: { hours: 24 },
  })
  stats.value = res.data
}

async function loadAlerts() {
  const res = await api.get(`/website/targets/${route.params.id}/alerts`, {
    params: { page: 1, size: 50 },
  })
  alerts.value = res.data.items
}

async function loadAll() {
  loading.value = true
  try {
    await loadTarget()
    await Promise.all([loadHistory(), loadStats(), loadAlerts()])
    if (activeTab.value === 'stats') renderChart()
  } catch (e) {
    ElMessage.error(e.message || t('website.loadFailed'))
  } finally {
    loading.value = false
  }
}

function renderChart() {
  if (!uptimeChartRef.value) return
  if (!uptimeChart) uptimeChart = echarts.init(uptimeChartRef.value)

  // 使用历史记录绘制存活/响应时间趋势
  const points = [...history.value].reverse()
  uptimeChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: [t('website.responseTimeMs'), t('website.alive')] },
    grid: { left: '3%', right: '4%', bottom: '6%', top: '14%', containLabel: true },
    xAxis: {
      type: 'category',
      data: points.map((h) => formatHM(h.checked_at)),
      axisLabel: { fontSize: 10 },
    },
    yAxis: [
      { type: 'value', name: 'ms' },
      { type: 'value', min: 0, max: 1, name: t('website.alive'), show: false },
    ],
    series: [
      {
        name: t('website.responseTimeMs'),
        type: 'line',
        smooth: true,
        data: points.map((h) => (h.response_time ? Number(h.response_time) : 0)),
        areaStyle: { opacity: 0.15 },
        itemStyle: { color: '#409eff' },
      },
      {
        name: t('website.alive'),
        type: 'line',
        yAxisIndex: 1,
        step: 'middle',
        data: points.map((h) => (h.is_alive ? 1 : 0)),
        itemStyle: { color: '#67c23a' },
      },
    ],
  })
  uptimeChart.resize()
}

function onTabChange(name) {
  if (name === 'stats') {
    setTimeout(renderChart, 60)
  }
}

async function ackAlert(id) {
  try {
    await api.post(`/website/alerts/${id}/ack`)
    ElMessage.success(t('website.alertAcknowledged'))
    await loadAlerts()
  } catch (e) {
    ElMessage.error(e.message || t('website.operationFailed'))
  }
}

onMounted(loadAll)
</script>

<style scoped>
.website-detail {
  height: 100%;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.pager {
  margin-top: 16px;
  justify-content: flex-end;
}

.history-filter {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 12px;
}

.chart {
  height: 340px;
}

.cert-panel {
  margin-top: 18px;
  padding: 14px 16px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #f8fafc;
}

.cert-panel-title {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 600;
  color: #334155;
}

.cert-serial {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 12px;
  overflow-wrap: anywhere;
}
</style>
