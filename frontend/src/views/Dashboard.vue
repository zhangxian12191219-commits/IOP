<template>
  <div class="ops-page">
    <header class="ops-header">
      <div class="ops-title">
        <span class="ops-kicker">OPERATIONS SIGNAL DECK</span>
        <h1>监控总览</h1>
        <p>资产在线、告警处置、资源使用率与设备状态集中指挥</p>
      </div>
      <div class="ops-actions">
        <span v-if="sharedResource" class="ops-shared">
          共享自 {{ sharedResource.owner?.real_name || sharedResource.owner?.username }}
          <el-tag size="small" :type="sharedResource.can_edit ? 'success' : 'info'" effect="plain">
            {{ sharedResource.can_edit ? '可编辑' : '只读' }}
          </el-tag>
        </span>
        <el-button v-if="sharedResource && !sharedResource.can_edit" size="small" type="primary" plain @click="requestSharedEdit">
          申请编辑
        </el-button>
        <el-button v-if="!sharedResource || sharedResource.is_owner" size="small" @click="shareVisible = true">分享</el-button>
        <el-button size="small" @click="sharedWithMeVisible = true">共享给我</el-button>
      </div>
    </header>

    <section class="ops-kpis">
      <button
        v-for="item in commandKpis"
        :key="item.key"
        type="button"
        class="ops-kpi"
        :class="`tone-${item.tone}`"
        @click="goKpi(item)"
      >
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}<small>{{ item.unit }}</small></strong>
        <em>{{ item.note }}</em>
      </button>
    </section>

    <section class="ops-grid">
      <article class="ops-card ops-alerts">
        <header class="ops-card-head">
          <div><span>ALERT QUEUE</span><h2>未处理告警</h2></div>
          <el-tag type="danger" effect="dark" round>{{ unackAlerts.length }} 条</el-tag>
        </header>
        <div class="ops-alert-body">
          <el-table v-if="unackAlerts.length" :data="unackPreview" size="small" height="100%" style="width: 100%">
            <el-table-column :label="t('dashboard.level')" width="58">
              <template #default="{ row }">
                <el-tag :type="row.alert_level === 'critical' ? 'danger' : 'warning'" size="small">
                  {{ row.alert_level === 'critical' ? t('dashboard.levelCritical') : t('dashboard.levelWarning') }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="t('alerts.source')" width="48">
              <template #default="{ row }">
                <span class="ops-source">{{ row.source === 'website' ? '网站' : '设备' }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="device_name" :label="t('dashboard.deviceName')" width="105" show-overflow-tooltip>
              <template #default="{ row }">{{ row.device_name || row.device?.name || '—' }}</template>
            </el-table-column>
            <el-table-column prop="message" label="告警内容" min-width="140" show-overflow-tooltip />
            <el-table-column :label="t('dashboard.time')" width="108">
              <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column :label="t('dashboard.actions')" width="56" fixed="right">
              <template #default="{ row }">
                <el-button type="primary" link size="small" @click="confirmAlert(row)">确认</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-else :description="t('dashboard.noUnackAlerts')" :image-size="60" />
        </div>
      </article>

      <article class="ops-card ops-type">
        <header class="ops-card-head">
          <div><span>ASSET MIX</span><h2>{{ t('dashboard.deviceTypeDistribution') }}</h2></div>
          <b class="ops-total">{{ stats.total_devices || rankingDevices.length }}</b>
        </header>
        <div ref="typeChartRef" class="ops-chart ops-chart-pie"></div>
      </article>

      <article class="ops-card ops-top">
        <header class="ops-card-head">
          <div><span>RESOURCE PRESSURE</span><h2>{{ t('dashboard.topUsage') }}</h2></div>
          <el-button type="primary" link @click="$router.push('/devices')">{{ t('dashboard.viewAll') }}</el-button>
        </header>
        <div v-if="topTripleDevices.length" class="ops-top-list">
          <div v-for="(row, index) in topTripleDevices" :key="row.id" class="ops-top-row ops-top-triple" @click="$router.push(`/devices/${row.id}`)">
            <span class="ops-rank" :class="`rank-${index + 1}`">{{ String(index + 1).padStart(2, '0') }}</span>
            <div class="ops-top-main">
              <div class="ops-top-name"><b>{{ row.name }}</b><span>{{ getTypeName(row.device_type) }}</span></div>
              <div class="ops-triple">
                <div class="ops-triple-line">
                  <span>CPU</span>
                  <i><em :style="{ width: `${clampPercent(row.cpu)}%`, background: getProgressColor(row.cpu, 'cpu_usage') }"></em></i>
                  <b>{{ row.cpu.toFixed(1) }}%</b>
                </div>
                <div class="ops-triple-line">
                  <span>内存</span>
                  <i><em :style="{ width: `${clampPercent(row.memory)}%`, background: getProgressColor(row.memory, 'memory_usage') }"></em></i>
                  <b>{{ row.memory.toFixed(1) }}%</b>
                </div>
                <div class="ops-triple-line">
                  <span>最高温度</span>
                  <i><em :style="{ width: `${clampPercent(row.temperature)}%`, background: getTempColor(row.temperature) }"></em></i>
                  <b>{{ row.temperature === null ? '—' : `${row.temperature.toFixed(1)}°C` }}</b>
                </div>
              </div>
            </div>
          </div>
        </div>
        <el-empty v-else :description="t('dashboard.noUsageData')" :image-size="60" />
      </article>

      <article class="ops-card ops-trend">
        <header class="ops-card-head">
          <div><span>ALERT SIGNAL</span><h2>{{ t('dashboard.alertTrend') }}</h2></div>
          <span class="ops-legend"><i></i>告警数量</span>
        </header>
        <div ref="alertChartRef" class="ops-chart"></div>
      </article>

      <article v-if="serverHardware.length" class="ops-card ops-server">
        <header class="ops-card-head">
          <div><span>SERVER HARDWARE</span><h2>{{ t('dashboard.serverHardware') }}</h2></div>
          <b class="ops-total">{{ serverHardware.length }}</b>
        </header>
        <div class="ops-server-grid">
          <div v-for="server in serverHardware" :key="server.id" class="ops-server-item">
            <button type="button" class="ops-server-name" @click="$router.push(`/devices/${server.id}`)">{{ server.name }}</button>
            <span>{{ server.ip_address }}</span>
            <div class="ops-sensors">
              <span v-for="sensor in server.sensors.slice(0, 8)" :key="sensor.key" :class="`level-${serverSensorLevel(sensor)}`">
                {{ sensor.name }}<b>{{ serverSensorText(sensor) }}</b>
              </span>
            </div>
          </div>
        </div>
      </article>

      <article class="ops-card ops-devices">
        <header class="ops-card-head">
          <div><span>DEVICE FLEET</span><h2>{{ t('dashboard.deviceStatusOverview') }}</h2></div>
          <div class="ops-device-tools">
            <el-checkbox v-model="layout.groupByType" :disabled="sharedReadOnly" @change="onGroupByTypeChange">按类型分组</el-checkbox>
            <el-popover placement="bottom-end" :width="210" trigger="click">
              <template #reference>
                <el-button type="primary" link :disabled="sharedReadOnly">指标选择</el-button>
              </template>
              <div class="ops-column-picker">
                <el-checkbox-group v-model="layout.columns" @change="onColumnsChange">
                  <el-checkbox v-for="col in COLUMN_DEFS" :key="col.key" :label="col.key">
                    {{ t(col.labelKey) }}
                  </el-checkbox>
                </el-checkbox-group>
              </div>
            </el-popover>
            <el-button type="primary" link @click="$router.push('/devices')">{{ t('dashboard.viewAll') }}</el-button>
          </div>
        </header>
        <div class="ops-device-body">
          <div class="ops-device-table">
            <el-table
              :data="tableRows"
              stripe
              height="420"
              style="width: 100%"
              :span-method="deviceSpanMethod"
              :row-class-name="deviceRowClassName"
            >
              <el-table-column :label="t('dashboard.deviceName')" width="190">
                <template #default="{ row }">
                  <div v-if="row.__group" class="ops-device-group">
                    <span class="ops-device-group-label">{{ deviceTypeLabel(row.device_type) }}</span>
                    <span class="ops-device-group-count">{{ row.count }} 台</span>
                  </div>
                  <span v-else>{{ row.name }}</span>
                </template>
              </el-table-column>
              <el-table-column v-for="col in activeColumns" :key="col.key" :label="t(col.labelKey)" :min-width="col.width">
                <template #default="{ row }">
                  <template v-if="col.key === 'ip'"><span class="mono">{{ row.ip_address }}</span></template>
                  <el-tag v-else-if="col.key === 'type'" :type="getTypeTagColor(row.device_type)" size="small">{{ getTypeName(row.device_type) }}</el-tag>
                  <el-progress v-else-if="col.key === 'cpu'" :percentage="row.metric?.cpu_usage || 0" :color="getProgressColor(row.metric?.cpu_usage, 'cpu_usage')" :format="formatPercent" :stroke-width="14" />
                  <el-progress v-else-if="col.key === 'memory'" :percentage="row.metric?.memory_usage || 0" :color="getProgressColor(row.metric?.memory_usage, 'memory_usage')" :format="formatPercent" :stroke-width="14" />
                  <span v-else-if="col.key === 'temperature'" :class="getTempClass(row.metric?.temperature)"
                    :title="row.metric?.temperature_info?.name ? `传感器：${row.metric.temperature_info.name}` : '设备最高温度'">
                    {{ row.metric?.temperature ? row.metric.temperature + '°C' : '-' }}
                  </span>
                  <el-tag v-else-if="col.key === 'power'" :type="row.metric?.power_status === 'normal' ? 'success' : 'danger'" size="small">{{ row.metric?.power_status === 'normal' ? t('dashboard.normal') : t('dashboard.abnormal') }}</el-tag>
                  <span v-else-if="col.key === 'uptime'">{{ formatUptime(row.metric?.uptime) }}</span>
                  <el-tag v-else-if="col.key === 'status'" :type="getStatusType(row)" size="small">{{ getStatusText(row) }}</el-tag>
                  <el-button v-else-if="col.key === 'actions'" type="primary" link size="small" @click="$router.push(`/devices/${row.id}`)">{{ t('dashboard.detail') }}</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <aside class="ops-fleet-side">
            <div class="ops-fleet-title">
              <span>FLEET HEALTH</span>
              <b>资产健康</b>
            </div>
            <div class="ops-fleet-kpis">
              <div><b>{{ onlineCount }}</b><span>在线</span></div>
              <div class="warning"><b>{{ alertDevices }}</b><span>告警设备</span></div>
              <div class="danger"><b>{{ offlineCount }}</b><span>离线</span></div>
              <div class="amber"><b>{{ warrantyExpiring }}</b><span>维保临期</span></div>
            </div>

            <div class="ops-fleet-block">
              <div class="ops-fleet-block-head"><b>设备类型分布</b><span>{{ rankingDevices.length }} 台</span></div>
              <div v-for="row in fleetTypeRows" :key="row.key" class="ops-fleet-type">
                <span>{{ row.label }}</span>
                <i><em :style="{ width: `${row.percent}%`, background: row.color }"></em></i>
                <b>{{ row.count }}</b>
              </div>
              <div v-if="!fleetTypeRows.length" class="ops-fleet-empty">暂无设备数据</div>
            </div>

            <div class="ops-fleet-block">
              <div class="ops-fleet-block-head"><b>告警设备 TOP</b><span>未处理</span></div>
              <button
                v-for="row in fleetAlertDevices"
                :key="row.id"
                type="button"
                class="ops-fleet-alert"
                @click="$router.push(`/devices/${row.id}`)"
              >
                <span>{{ row.name }}</span>
                <b>{{ row.alert_count }} 条</b>
              </button>
              <div v-if="!fleetAlertDevices.length" class="ops-fleet-empty">暂无告警设备</div>
            </div>
          </aside>
        </div>
      </article>
    </section>

    <ResourceShareDialog
      v-model="shareVisible"
      resource-type="dashboard"
      resource-key="default"
      title="监控总览仪表盘"
      :config="{ groupByType: layout.groupByType, cards: layout.cards, columns: layout.columns, items: layout.items }"
    />
    <SharedWithMeDialog v-model="sharedWithMeVisible" resource-type="dashboard" />
  </div>
</template>

<script setup>
import { t } from '@/i18n'
import { ref, reactive, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import * as echarts from 'echarts'
import { ElMessage, ElMessageBox } from 'element-plus'
import { GridLayout, GridItem } from 'grid-layout-plus'
import { monitorApi, assetApi, sharingApi } from '@/api'
import ResourceShareDialog from '@/components/ResourceShareDialog.vue'
import SharedWithMeDialog from '@/components/SharedWithMeDialog.vue'
import { refreshMs } from '@/store/settings'
import { settings } from '@/store/settings'
import { ageSeconds, formatDateTime } from '@/utils/time'
import {
  DEVICE_TYPES, deviceTypeLabel, deviceTypeTagType, deviceTypeColor,
} from '@/constants/device'

const router = useRouter()
const route = useRoute()

const stats = ref({
  total_devices: 0,
  enabled_devices: 0,
  unack_alerts: 0,
  metric_thresholds: {},
})

const metricThresholds = computed(() => ({
  cpu_usage: Number(stats.value.metric_thresholds?.cpu_usage) || 80,
  memory_usage: Number(stats.value.metric_thresholds?.memory_usage) || 85,
  temperature: Number(stats.value.metric_thresholds?.temperature) || 80,
  temperature_critical: Number(stats.value.metric_thresholds?.temperature_critical) || 90,
  disk_usage: Number(stats.value.metric_thresholds?.disk_usage) || 90,
}))

function goStat(path) {
  router.push(path)
}

function goKpi(item) {
  if (item.key === 'asset-alert') {
    const target = fleetAlertDevices.value[0]
    if (target?.id) {
      router.push(`/devices/${target.id}?tab=alerts`)
    } else {
      router.push('/alerts')
    }
    return
  }
  goStat(item.path)
}

const deviceList = ref([])
const rankingDevices = ref([])
const unackAlerts = ref([])
const alertTrend = ref([])
const typeChartRef = ref(null)
const alertChartRef = ref(null)

const serverHardware = computed(() =>
  rankingDevices.value
    .filter((device) => device.device_type === 'server' && (device.server_sensors || []).length)
    .map((device) => ({
      ...device,
      sensors: (device.server_sensors || [])
        .filter((sensor) => sensor.oid)
        .map((sensor) => ({
          ...sensor,
          value: sensor.kind === 'fault'
            ? device.metric?.custom?.[sensor.key]
            : Number(device.metric?.custom?.[sensor.key]),
        })),
    }))
)

function deviceOnline(device) {
  const collected = device?.metric?.collected_at
  if (!collected) return false
  const text = /[zZ]|[+-]\d{2}:\d{2}$/.test(collected) ? collected : `${collected}Z`
  const time = new Date(text).getTime()
  return Number.isFinite(time) && Date.now() - time < 10 * 60 * 1000
}
const clamp = (value) => Math.max(0, Math.min(100, Number(value) || 0))
const onlineCount = computed(() => rankingDevices.value.filter(deviceOnline).length)
const offlineCount = computed(() => Math.max(0, rankingDevices.value.length - onlineCount.value))
const onlineRate = computed(() => rankingDevices.value.length ? (onlineCount.value / rankingDevices.value.length * 100).toFixed(1) : '0.0')
const serverCount = computed(() => rankingDevices.value.filter((device) => device.device_type === 'server').length)
const criticalAlerts = computed(() => unackAlerts.value.filter((alert) => alert.alert_level === 'critical').length)
const emergencyAlerts = computed(() => unackAlerts.value.filter((alert) => alert.alert_level === 'emergency').length)
const warningAlerts = computed(() => unackAlerts.value.filter((alert) => alert.alert_level === 'warning').length)
const warrantyExpiring = computed(() => rankingDevices.value.filter((device) => device.warranty_days_left !== null && device.warranty_days_left !== undefined && device.warranty_days_left <= 30).length)
const alertDevices = computed(() => rankingDevices.value.filter((device) => Number(device.alert_count || 0) > 0).length)
const fleetTypeRows = computed(() => {
  const counts = {}
  rankingDevices.value.forEach((device) => {
    const key = device.device_type || 'other'
    counts[key] = (counts[key] || 0) + 1
  })
  const max = Math.max(1, ...Object.values(counts))
  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .map(([key, count]) => ({
      key,
      count,
      label: deviceTypeLabel(key),
      percent: (count / max) * 100,
      color: deviceTypeColor(key),
    }))
})
const fleetAlertDevices = computed(() => rankingDevices.value
  .filter((device) => Number(device.alert_count || 0) > 0)
  .sort((a, b) => Number(b.alert_count) - Number(a.alert_count))
  .slice(0, 4))
const avgCpu = computed(() => {
  const values = rankingDevices.value.filter(deviceOnline).map((device) => Number(device.metric?.cpu_usage)).filter((value) => Number.isFinite(value) && value > 0)
  return values.length ? (values.reduce((a, b) => a + b, 0) / values.length).toFixed(1) : '0'
})
const avgMemory = computed(() => {
  const values = rankingDevices.value.filter(deviceOnline).map((device) => Number(device.metric?.memory_usage)).filter((value) => Number.isFinite(value) && value > 0)
  return values.length ? (values.reduce((a, b) => a + b, 0) / values.length).toFixed(1) : '0'
})
const maxTemp = computed(() => {
  const values = rankingDevices.value.map((device) => Number(device.metric?.temperature)).filter((value) => Number.isFinite(value))
  return values.length ? Math.max(...values) : null
})
const maxTempText = computed(() => maxTemp.value === null ? '未采集' : `${maxTemp.value.toFixed(1)}℃`)
const powerFailures = computed(() => rankingDevices.value.filter((device) => device.metric?.power_status === 'failure').length)
const commandKpis = computed(() => [
  { key: 'total', label: '资产总数', value: rankingDevices.value.length || stats.value.total_devices || 0, unit: '台', note: '已纳管资产', tone: 'blue', path: '/devices' },
  { key: 'enabled', label: '监控中', value: stats.value.enabled_devices || rankingDevices.value.filter((device) => device.is_enabled !== false).length, unit: '台', note: '启用监控', tone: 'cyan', path: '/devices' },
  { key: 'online', label: '在线资产', value: onlineCount.value, unit: '台', note: `${onlineRate.value}% 在线率`, tone: 'green', path: '/devices' },
  { key: 'offline', label: '离线资产', value: offlineCount.value, unit: '台', note: offlineCount.value ? '需要立即排查' : '全部在线', tone: 'red', path: '/devices' },
  { key: 'unack', label: '未处理告警', value: unackAlerts.value.length, unit: '条', note: `严重 ${criticalAlerts.value} · 紧急 ${emergencyAlerts.value} · 预警 ${warningAlerts.value}`, tone: 'amber', path: '/alerts' },
  { key: 'asset-alert', label: '资产告警数量', value: alertDevices.value, unit: '台', note: `${unackAlerts.value.length} 条活动告警 · 点击打开告警最多资产`, tone: 'red', path: '/alerts' },
  { key: 'server', label: '服务器', value: serverCount.value, unit: '台', note: '服务器资产', tone: 'violet', path: '/devices' },
  { key: 'warranty', label: '维保临期', value: warrantyExpiring.value, unit: '台', note: '30 天内到期', tone: 'amber', path: '/devices' },
])

function serverSensorText(sensor) {
  if (sensor.value === null || sensor.value === undefined || Number.isNaN(sensor.value)) return '--'
  if (sensor.kind === 'fault') return Number(sensor.value) <= 1 ? t('dashboard.normal') : t('dashboard.abnormal')
  const value = Number(sensor.value)
  const precision = sensor.kind === 'current' ? 2 : 1
  return `${value.toFixed(precision)}${sensor.unit || ''}`
}

function serverSensorLevel(sensor) {
  if (sensor.value === null || sensor.value === undefined || Number.isNaN(sensor.value)) return 'muted'
  if (sensor.kind === 'fault') return Number(sensor.value) <= 1 ? 'normal' : 'critical'
  if (sensor.kind === 'temperature') {
    if (Number(sensor.value) >= 90) return 'critical'
    if (Number(sensor.value) >= 80) return 'warning'
  }
  return 'normal'
}

// ---------- 总览布局自定义（可自由拖动/缩放，自动吸附网格）----------
const LAYOUT_KEY = 'nms_dashboard_layout_v2'
const CARD_DEFS = [
  { key: 'unack', labelKey: 'dashboard.cardUnack' },
  { key: 'top', labelKey: 'dashboard.cardTop' },
  { key: 'type', labelKey: 'dashboard.cardType' },
  { key: 'trend', labelKey: 'dashboard.cardTrend' },
  { key: 'server', labelKey: 'dashboard.cardServer' },
]
const COLUMN_DEFS = [
  { key: 'ip', labelKey: 'dashboard.ipAddress', width: 160 },
  { key: 'type', labelKey: 'dashboard.type', width: 110 },
  { key: 'cpu', labelKey: 'dashboard.cpuUsage', width: 140 },
  { key: 'memory', labelKey: 'dashboard.memoryUsage', width: 140 },
  { key: 'temperature', labelKey: 'dashboard.maxTemperature', width: 110 },
  { key: 'power', labelKey: 'dashboard.powerStatus', width: 110 },
  { key: 'uptime', labelKey: 'dashboard.uptime', width: 120 },
  { key: 'status', labelKey: 'dashboard.status', width: 100 },
  { key: 'actions', labelKey: 'dashboard.actions', width: 90, fixed: 'right' },
]
const DEFAULT_LAYOUT = {
  groupByType: true,
  cards: { unack: true, top: true, type: true, trend: true, server: false },
  columns: ['ip', 'type', 'cpu', 'memory', 'temperature', 'status', 'actions'],
  items: {
    // 按内容体量排布：饼图小卡片、告警列表高卡片、TOP5/趋势中等卡片
    type: { x: 0, y: 0, w: 3, h: 4 },
    unack: { x: 3, y: 0, w: 5, h: 11 },
    top: { x: 8, y: 0, w: 4, h: 5 },
    trend: { x: 8, y: 5, w: 4, h: 6 },
    server: { x: 0, y: 4, w: 3, h: 6 },
    table: { x: 0, y: 11, w: 12, h: 8 },
  },
}
const ITEM_KEYS = ['unack', 'top', 'type', 'trend', 'server', 'table']
const ITEM_LIMITS = {
  unack: { minW: 4, minH: 3 },
  top: { minW: 4, minH: 3 },
  type: { minW: 3, minH: 4 },
  trend: { minW: 4, minH: 4 },
  server: { minW: 6, minH: 4 },
  table: { minW: 6, minH: 4 },
}
const ITEM_DEFAULT_POS = DEFAULT_LAYOUT.items

function cloneItems(items) {
  const result = {}
  ITEM_KEYS.forEach((key) => {
    result[key] = { ...(items?.[key] || ITEM_DEFAULT_POS[key]) }
  })
  return result
}

function readSavedLayout() {
  try {
    const saved = JSON.parse(localStorage.getItem(LAYOUT_KEY) || '{}')
    const cards = { ...DEFAULT_LAYOUT.cards, ...(saved.cards || {}) }
    const columns = Array.isArray(saved.columns)
      ? COLUMN_DEFS.map((col) => col.key).filter((key) => saved.columns.includes(key))
      : [...DEFAULT_LAYOUT.columns]
    const items = cloneItems(saved.items)
    ITEM_KEYS.forEach((key) => {
      const limits = ITEM_LIMITS[key]
      items[key].w = Math.max(limits.minW, Math.min(12, Number(items[key].w) || ITEM_DEFAULT_POS[key].w))
      items[key].h = Math.max(limits.minH, Number(items[key].h) || ITEM_DEFAULT_POS[key].h)
      items[key].x = Math.max(0, Math.min(12 - items[key].w, Number(items[key].x) || 0))
      items[key].y = Math.max(0, Number(items[key].y) || 0)
    })
    return {
      groupByType: saved.groupByType !== false,
      cards,
      columns,
      items,
    }
  } catch {
    return {
      groupByType: true,
      cards: { ...DEFAULT_LAYOUT.cards },
      columns: [...DEFAULT_LAYOUT.columns],
      items: cloneItems(DEFAULT_LAYOUT.items),
    }
  }
}

const layout = reactive(readSavedLayout())
const layoutDialog = ref(false)
const shareVisible = ref(false)
const sharedWithMeVisible = ref(false)
const sharedResource = ref(null)
const sharedReadOnly = computed(() => Boolean(sharedResource.value && !sharedResource.value.can_edit))
const draft = reactive({
  cards: { ...layout.cards },
  columns: [...layout.columns],
  items: cloneItems(layout.items),
})
const widgetLayout = ref([])


const activeColumns = computed(() =>
  COLUMN_DEFS.filter((col) => layout.columns.includes(col.key))
)

const tableRows = computed(() => {
  if (!layout.groupByType) return deviceList.value
  const groups = new Map()
  rankingDevices.value.forEach((device) => {
    const type = device.device_type || 'other'
    if (!groups.has(type)) groups.set(type, [])
    groups.get(type).push(device)
  })
  const order = DEVICE_TYPES.map((item) => item.value)
  const sortedTypes = [...groups.keys()].sort((a, b) => {
    const ai = order.indexOf(a)
    const bi = order.indexOf(b)
    return (ai < 0 ? 999 : ai) - (bi < 0 ? 999 : bi)
  })
  const rows = []
  sortedTypes.forEach((type) => {
    const items = groups.get(type) || []
    if (!items.length) return
    rows.push({ __group: true, device_type: type, count: items.length })
    rows.push(...items)
  })
  return rows
})

function deviceSpanMethod({ row, columnIndex }) {
  if (!row.__group) return undefined
  if (columnIndex === 0) return [1, 1 + activeColumns.value.length]
  return [0, 0]
}

function deviceRowClassName({ row }) {
  return row.__group ? 'ops-device-group-row' : ''
}

function onGroupByTypeChange() {
  persistLayout()
}

function onColumnsChange(columns) {
  if (!Array.isArray(columns) || !columns.length) {
    layout.columns = ['status']
  }
  persistLayout()
}

function activeGridItems() {
  return ITEM_KEYS.filter((key) => key === 'table' || layout.cards[key]).map((key) => ({
    ...layout.items[key],
    i: key,
    ...ITEM_LIMITS[key],
  }))
}

function widgetItem(key) {
  return widgetLayout.value.find((item) => item.i === key) || layout.items[key]
}

function syncGridLayout() {
  widgetLayout.value = activeGridItems()
}

syncGridLayout()

function persistLayout() {
  if (sharedReadOnly.value) return
  try {
    if (sharedResource.value?.id) {
      sharingApi.updateResource(sharedResource.value.id, {
        config: {
          groupByType: layout.groupByType,
          cards: { ...layout.cards },
          columns: [...layout.columns],
          items: cloneItems(layout.items),
        },
      }).catch(() => {})
      return
    }
    localStorage.setItem(LAYOUT_KEY, JSON.stringify({
      groupByType: layout.groupByType,
      cards: { ...layout.cards },
      columns: [...layout.columns],
      items: cloneItems(layout.items),
    }))
  } catch {
    /* 忽略存储异常 */
  }
}

function onLayoutUpdated(updated) {
  if (sharedReadOnly.value) return
  ;(updated || []).forEach((item) => {
    const key = item.i
    if (!layout.items[key]) return
    layout.items[key] = {
      x: item.x, y: item.y, w: item.w, h: item.h,
    }
  })
  persistLayout()
  nextTick(() => resizeCharts())
}

function openLayoutConfig() {
  if (sharedReadOnly.value) {
    ElMessage.info('共享仪表盘当前为只读，请点击“申请编辑”')
    return
  }
  draft.cards = { ...layout.cards }
  draft.columns = [...layout.columns]
  draft.items = cloneItems(layout.items)
  layoutDialog.value = true
}

function applyLayoutConfig() {
  const typeVisible = layout.cards.type
  const trendVisible = layout.cards.trend
  layout.cards = { ...draft.cards }
  layout.columns = [...draft.columns]
  if (!layout.columns.length) layout.columns = ['status']
  layout.items = cloneItems(draft.items)
  persistLayout()
  syncGridLayout()
  layoutDialog.value = false
  ElMessage.success(t('dashboard.layoutSaved'))
  if (typeVisible && !layout.cards.type && typeChart) {
    typeChart.dispose()
    typeChart = null
  }
  if (trendVisible && !layout.cards.trend && alertChart) {
    alertChart.dispose()
    alertChart = null
  }
  nextTick(() => {
    initCharts()
    resizeCharts()
  })
}

function resetLayoutConfig() {
  draft.cards = { ...DEFAULT_LAYOUT.cards }
  draft.columns = [...DEFAULT_LAYOUT.columns]
  draft.items = cloneItems(DEFAULT_LAYOUT.items)
}

function resizeCharts() {
  typeChart?.resize()
  alertChart?.resize()
}

function onItemMoved(i, x, y) {
  if (sharedReadOnly.value) return
  if (!layout.items[i]) return
  layout.items[i] = { ...layout.items[i], x, y }
  persistLayout()
  nextTick(() => resizeCharts())
}

function onItemResized(i, h, w) {
  if (sharedReadOnly.value) return
  if (!layout.items[i]) return
  layout.items[i] = { ...layout.items[i], w, h }
  persistLayout()
  nextTick(() => resizeCharts())
}

async function loadSharedDashboard() {
  const sharedId = Number(route.query.shared)
  if (!sharedId) return
  try {
    const res = await sharingApi.resource(sharedId)
    const item = res.data?.resource
    if (!item || item.resource_type !== 'dashboard') {
      ElMessage.error('该共享资源不是仪表盘')
      return
    }
    const config = item.config || {}
    layout.cards = { ...DEFAULT_LAYOUT.cards, ...(config.cards || {}) }
    const allowedColumns = COLUMN_DEFS.map((col) => col.key)
    layout.groupByType = config.groupByType !== false
    layout.columns = Array.isArray(config.columns)
      ? allowedColumns.filter((key) => config.columns.includes(key))
      : [...DEFAULT_LAYOUT.columns]
    if (!layout.columns.length) layout.columns = ['status']
    layout.items = cloneItems(config.items)
    sharedResource.value = item
    syncGridLayout()
    await nextTick()
    resizeCharts()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '共享仪表盘加载失败')
  }
}

async function requestSharedEdit() {
  if (!sharedResource.value) return
  try {
    await sharingApi.requestEdit(sharedResource.value.id)
    sharedResource.value = {
      ...sharedResource.value,
      pending_request: { status: 'pending' },
    }
    ElMessage.success('编辑申请已提交，等待共享者审批')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '提交编辑申请失败')
  }
}

watch(() => route.query.shared, async (value) => {
  if (value) {
    await loadSharedDashboard()
    return
  }
  sharedResource.value = null
  const local = readSavedLayout()
  layout.cards = local.cards
  layout.columns = local.columns
  layout.items = cloneItems(local.items)
  syncGridLayout()
  await nextTick()
  resizeCharts()
})

const unackPreview = computed(() => unackAlerts.value)

// TOP5 指标选择（CPU / 内存 / 温度 / 功率）
const TOP_METRICS = [
  { key: 'cpu', labelKey: 'dashboard.cpuUsage', shortLabel: 'CPU' },
  { key: 'memory', labelKey: 'dashboard.memoryUsage', shortLabel: 'MEM' },
  { key: 'temperature', labelKey: 'dashboard.maxTemperature', shortLabel: '最高温度' },
  { key: 'power', labelKey: 'dashboard.powerUsage', shortLabel: '功率' },
]
const TOP_METRIC_KEY = 'nms_dashboard_top_metric'
const savedTopMetric = localStorage.getItem(TOP_METRIC_KEY)
const topMetric = ref(
  TOP_METRICS.some((item) => item.key === savedTopMetric) ? savedTopMetric : 'cpu'
)
const topMetricMeta = computed(
  () => TOP_METRICS.find((item) => item.key === topMetric.value) || TOP_METRICS[0]
)

function onTopMetricChange(value) {
  try {
    localStorage.setItem(TOP_METRIC_KEY, value)
  } catch {
    /* 忽略存储异常 */
  }
}

function topMetricRawValue(device) {
  if (topMetric.value === 'cpu') return Number(device.metric?.cpu_usage) || 0
  if (topMetric.value === 'memory') return Number(device.metric?.memory_usage) || 0
  if (topMetric.value === 'temperature') {
    const value = device.metric?.temperature
    return value === null || value === undefined ? null : Number(value)
  }
  // 功率：使用设备额定功率（W），无对应数值时跳过
  const watts = device.power_watts
  return watts === null || watts === undefined ? null : Number(watts)
}

const topUsageDevices = computed(() => {
  const rows = rankingDevices.value
    .map((device) => ({
      ...device,
      metricValue: topMetricRawValue(device),
      temperature: device.metric?.temperature,
      cpu: Number(device.metric?.cpu_usage) || 0,
      memory: Number(device.metric?.memory_usage) || 0,
    }))
    .filter((device) => device.metricValue !== null && !Number.isNaN(device.metricValue))

  const maxValue = Math.max(1, ...rows.map((device) => device.metricValue))
  return rows
    .sort((a, b) => b.metricValue - a.metricValue)
    .slice(0, 5)
    .map((device) => ({ ...device, maxValue }))
})

const topTripleDevices = computed(() => rankingDevices.value
  .map((device) => {
    const temp = device.metric?.temperature
    return {
      ...device,
      cpu: Number(device.metric?.cpu_usage) || 0,
      memory: Number(device.metric?.memory_usage) || 0,
      temperature: temp === null || temp === undefined || !Number.isFinite(Number(temp)) ? null : Number(temp),
    }
  })
  .sort((a, b) => b.cpu - a.cpu)
  .slice(0, 5))

function topUsagePercent(row) {
  if (['cpu', 'memory', 'temperature'].includes(topMetric.value)) {
    return clampPercent(row.metricValue)
  }
  return clampPercent(row.maxValue ? (row.metricValue / row.maxValue) * 100 : 0)
}

function topUsageColor(row) {
  if (topMetric.value === 'temperature') {
    if (row.metricValue >= metricThresholds.value.temperature_critical) return '#f56c6c'
    if (row.metricValue >= metricThresholds.value.temperature) return '#e6a23c'
    return '#409eff'
  }
  if (topMetric.value === 'power') {
    return row.metric?.power_status === 'normal' ? '#409eff' : '#f56c6c'
  }
  return getProgressColor(row.metricValue, `${topMetric.value}_usage`)
}

function topUsageText(row) {
  const value = Number(row.metricValue)
  if (topMetric.value === 'cpu' || topMetric.value === 'memory') return `${value.toFixed(1)}%`
  if (topMetric.value === 'temperature') return `${value.toFixed(1)}°C`
  return `${Math.round(value)} W`
}

function clampPercent(value) {
  return Math.max(0, Math.min(100, Number(value) || 0))
}

function formatUptime(seconds) {
  const total = Number(seconds)
  if (!total || total <= 0) return '-'
  const days = Math.floor(total / 86400)
  const hours = Math.floor((total % 86400) / 3600)
  return t('dashboard.uptimeFormat', { days, hours })
}

async function confirmAlert(row) {
  try {
    await ElMessageBox.confirm(
      `${t('dashboard.confirmAlert')}\n${row.message || ''}`,
      t('dashboard.confirm'),
      { type: 'warning' }
    )
    await monitorApi.acknowledgeAlert(row.id, row.source || 'device')
    ElMessage.success(t('dashboard.alertConfirmed'))
    await Promise.all([loadDashboard(), loadUnackAlerts()])
  } catch {
    /* 取消 */
  }
}

let typeChart = null
let alertChart = null
let refreshTimer = null

// 设备类型（统一映射，避免各页面/图表颜色不一致）
const getTypeTagColor = (type) => deviceTypeTagType(type)
const getTypeName = (type) => deviceTypeLabel(type)

// 使用率进度条：只改变颜色，不替换数值（避免 ✕/! 图标盖住百分比）
const getProgressColor = (value, metricKey = 'cpu_usage') => {
  const threshold = Number(metricThresholds.value[metricKey]) || 80
  if (!value || value < threshold) return '#409eff'
  if (value < threshold + 10) return '#e6a23c'
  return '#f56c6c'
}

const formatPercent = (value) => `${Math.round(value || 0)}%`

const getTempColor = (temp) => {
  if (temp === null || temp === undefined) return '#0ea5e9'
  if (Number(temp) >= metricThresholds.value.temperature_critical) return '#ef4444'
  if (Number(temp) >= metricThresholds.value.temperature) return '#f59e0b'
  return '#0ea5e9'
}

const getTempClass = (temp) => {
  if (temp === null || temp === undefined) return ''
  if (Number(temp) >= metricThresholds.value.temperature_critical) return 'temp-high'
  if (Number(temp) >= metricThresholds.value.temperature) return 'temp-warn'
  return ''
}

const getStatusType = (row) => {
  if (!row.metric) return 'info'
  if (ageSeconds(row.metric.collected_at) > 300) return 'danger'
  if (row.alert_count > 0) return 'warning'
  return 'success'
}

const getStatusText = (row) => {
  const type = getStatusType(row)
  return { success: t('dashboard.online'), warning: t('dashboard.alert'), danger: t('dashboard.offline'), info: t('dashboard.unknown') }[type]
}

// 加载仪表盘数据
async function loadDashboard() {
  try {
    const res = await monitorApi.getDashboard()
    stats.value = res.data
    updateTypeChart()
  } catch (e) {
    console.error('加载仪表盘数据失败', e)
  }
}

// 加载设备列表（表格展示前 10 台，TOP5 使用率基于全部设备）
async function loadDevices() {
  try {
    const res = await assetApi.getList({ size: 100 })
    const items = res.data.items || []
    rankingDevices.value = items
    deviceList.value = items.slice(0, 10)
  } catch (e) {
    console.error('加载设备列表失败', e)
  }
}

// 加载未处理告警列表
async function loadUnackAlerts() {
  try {
    const res = await monitorApi.getUnackAlerts()
    unackAlerts.value = res.data || []
  } catch (e) {
    console.error('加载未处理告警失败', e)
  }
}

// 加载 24 小时告警趋势（真实数据）
async function loadAlertTrend() {
  try {
    const res = await monitorApi.getAlertTrend()
    alertTrend.value = res.data.alert_trend || []
    updateAlertChart()
  } catch (e) {
    console.error('加载告警趋势失败', e)
  }
}

// 初始化图表
function initCharts() {
  if (typeChartRef.value && !typeChart) {
    typeChart = echarts.init(typeChartRef.value)
  }
  if (alertChartRef.value && !alertChart) {
    alertChart = echarts.init(alertChartRef.value)
  }
  updateTypeChart()
  updateAlertChart()
}

function updateTypeChart() {
  if (!typeChart) return
  const distribution = stats.value.device_type_distribution || {}
  const total = Object.values(distribution).reduce(
    (sum, count) => sum + (Number(count) || 0), 0
  )

  // 按固定顺序输出，颜色与列表标签、大屏保持一致
  const data = []
  const known = new Set()
  DEVICE_TYPES.forEach((type) => {
    const count = Number(distribution[type.value] || 0)
    if (count > 0) {
      known.add(type.value)
      data.push({ name: type.label, value: count, itemStyle: { color: type.color } })
    }
  })
  // 兼容历史数据里未预置的类型（如手工导入的其它取值）
  Object.entries(distribution).forEach(([key, count]) => {
    const value = Number(count) || 0
    if (known.has(key) || value <= 0) return
    data.push({
      name: deviceTypeLabel(key),
      value,
      itemStyle: { color: deviceTypeColor(key) },
    })
  })

  const graphic = data.length
    ? [
        {
          type: 'text', left: 'center', top: '36%',
          style: {
            text: String(total), fontSize: 26, fontWeight: 'bold',
            fill: '#303133', textAlign: 'center',
          },
        },
        {
          type: 'text', left: 'center', top: '46%',
          style: { text: t('dashboard.totalDevices'), fontSize: 12, fill: '#909399', textAlign: 'center' },
        },
      ]
    : [{
        type: 'text', left: 'center', top: 'middle',
        style: { text: t('dashboard.noDeviceData'), fontSize: 14, fill: '#909399' },
      }]

  typeChart.setOption({
    tooltip: {
      trigger: 'item',
      formatter: (params) =>
        `${params.marker}${params.name}<br/>${t('dashboard.typeTooltip', { count: params.value, percent: params.percent })}`,
    },
    legend: {
      bottom: 0,
      left: 'center',
      icon: 'circle',
      itemWidth: 8,
      itemHeight: 8,
      textStyle: { color: '#606266', fontSize: 12 },
    },
    graphic,
    series: [{
      name: t('dashboard.deviceType'),
      type: 'pie',
      radius: ['45%', '68%'],
      center: ['50%', '45%'],
      avoidLabelOverlap: true,
      itemStyle: { borderRadius: 8, borderColor: '#fff', borderWidth: 2 },
      label: { show: false },
      emphasis: {
        scale: true,
        scaleSize: 6,
        label: { show: true, fontWeight: 'bold' },
      },
      data,
    }],
  }, true) // notMerge：类型变化时整体替换，避免残留旧扇区
}

function updateAlertChart() {
  if (!alertChart) return
  const trend = alertTrend.value || []
  alertChart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: '3%', right: '4%', bottom: '3%', top: '12%', containLabel: true },
    xAxis: {
      type: 'category',
      data: trend.map((t) => t.time),
      axisLabel: { fontSize: 10, interval: 2 },
    },
    yAxis: { type: 'value', minInterval: 1 },
    series: [{
      name: t('dashboard.alertCount'),
      type: 'bar',
      data: trend.map((t) => t.count),
      barMaxWidth: 18,
      itemStyle: { color: '#f5222d', borderRadius: [3, 3, 0, 0] },
    }],
  })
}

function startRefreshTimer() {
  if (refreshTimer) clearInterval(refreshTimer)
  refreshTimer = setInterval(() => {
    loadDashboard()
    loadDevices()
    loadUnackAlerts()
    loadAlertTrend()
  }, refreshMs())
}

// 系统配置里修改刷新间隔后，实时应用（设置加载完成时也会触发一次）
watch(() => settings.refresh_interval, () => startRefreshTimer())

function handleResize() {
  typeChart?.resize()
  alertChart?.resize()
}

onMounted(async () => {
  await loadSharedDashboard()
  loadDashboard()
  loadDevices()
  loadUnackAlerts()
  loadAlertTrend()
  setTimeout(initCharts, 100)
  startRefreshTimer()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  if (refreshTimer) clearInterval(refreshTimer)
  window.removeEventListener('resize', handleResize)
  typeChart?.dispose()
  alertChart?.dispose()
})
</script>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.command-overview {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background:
    radial-gradient(circle at 0% 0%, rgba(14, 165, 233, 0.09), transparent 40%),
    linear-gradient(135deg, #f8fbff, #ffffff);
}

.command-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.command-kicker {
  color: #0284c7;
  font-size: 8px;
  font-weight: 600;
  letter-spacing: 1.8px;
}

.command-head h2 {
  margin: 3px 0 0;
  color: #0f172a;
  font-size: 18px;
}

.command-head p {
  margin: 4px 0 0;
  color: #64748b;
  font-size: 11px;
}

.command-live {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  color: #64748b;
  font-size: 10px;
}

.command-live i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #10b981;
  box-shadow: 0 0 7px rgba(16, 185, 129, 0.75);
}

.command-live span {
  padding-left: 8px;
  border-left: 1px solid #e2e8f0;
}

.command-kpis {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 9px;
}

.command-kpi {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  min-width: 0;
  padding: 10px 12px;
  overflow: hidden;
  border: 1px solid #e5edf5;
  border-radius: 8px;
  background: #fff;
  text-align: left;
  cursor: pointer;
  transition: transform 0.16s ease, box-shadow 0.16s ease, border-color 0.16s ease;
}

.command-kpi:hover {
  border-color: #bae6fd;
  box-shadow: 0 8px 20px rgba(14, 116, 144, 0.1);
  transform: translateY(-2px);
}

.command-kpi-label {
  color: #64748b;
  font-size: 10px;
}

.command-kpi strong {
  color: #0f172a;
  font-family: "Cascadia Mono", "DIN Alternate", monospace;
  font-size: 24px;
  line-height: 1.1;
}

.command-kpi strong small {
  margin-left: 2px;
  color: #94a3b8;
  font-size: 10px;
  font-weight: 400;
}

.command-kpi em {
  overflow: hidden;
  max-width: 100%;
  color: #94a3b8;
  font-size: 9px;
  font-style: normal;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.command-kpi-mark {
  position: absolute;
  right: -16px;
  bottom: -22px;
  width: 62px;
  height: 62px;
  border: 1px solid currentColor;
  border-radius: 50%;
  opacity: 0.1;
}

.command-kpi.tone-blue { color: #2563eb; }
.command-kpi.tone-cyan { color: #0891b2; }
.command-kpi.tone-green { color: #059669; }
.command-kpi.tone-red { color: #dc2626; }
.command-kpi.tone-amber { color: #d97706; }
.command-kpi.tone-violet { color: #7c3aed; }
.command-kpi.tone-red strong { color: #dc2626; }
.command-kpi.tone-amber strong { color: #b45309; }

.command-health {
  padding: 11px 13px;
  border: 1px solid #e5edf5;
  border-radius: 9px;
  background: #fff;
}

.command-health-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}

.command-health-head span {
  color: #334155;
  font-size: 12px;
  font-weight: 600;
}

.command-health-head b {
  color: #0891b2;
  font-family: monospace;
  font-size: 11px;
}

.command-health-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.command-health-item > div {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 6px;
}

.command-health-item span {
  color: #64748b;
  font-size: 9px;
}

.command-health-item b {
  color: #0f172a;
  font-family: monospace;
  font-size: 11px;
}

.command-health-item b.danger {
  color: #dc2626;
}

.command-health-item > i {
  display: block;
  height: 4px;
  margin-top: 5px;
  overflow: hidden;
  border-radius: 3px;
  background: #eef2f7;
}

.command-health-item > i > em {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #0ea5e9, #22d3ee);
}

.command-health-item > i > em.temperature {
  background: linear-gradient(90deg, #f59e0b, #fb7185);
}

.command-health-item > i > em.danger {
  background: linear-gradient(90deg, #ef4444, #fb7185);
}

.command-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 9px;
  padding-top: 8px;
  border-top: 1px dashed #e2e8f0;
  color: #94a3b8;
  font-size: 9px;
}

@media (max-width: 1200px) {
  .command-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .command-health-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

.dashboard-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 30px;
}

.dashboard-toolbar-title,
.dashboard-toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.dashboard-toolbar-title strong {
  color: #1e293b;
  font-size: 14px;
  font-weight: 600;
}

.shared-mode-tip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #64748b;
  font-size: 11px;
}

.stats-row {
  margin-bottom: 0;
}

/* 自由拖动/缩放的网格布局 */
:deep(.vgl-layout) {
  position: relative;
  width: 100%;
  min-height: 420px;
}

:deep(.vgl-item) {
  position: absolute;
  touch-action: none;
}

:deep(.vgl-item__resizer) {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 20px;
  height: 20px;
  z-index: 20;
  cursor: se-resize;
  opacity: 0.6;
  border-radius: 3px;
  background:
    linear-gradient(135deg, transparent 44%, #94a3b8 45%, #94a3b8 55%, transparent 56%),
    linear-gradient(135deg, transparent 62%, #cbd5e1 63%, #cbd5e1 73%, transparent 74%);
}

:deep(.vgl-item__resizer:hover) {
  opacity: 1;
  background-color: #f1f5f9;
}

:deep(.vgl-item--placeholder) {
  background: #e6f4ff;
  border: 1px dashed #409eff;
  border-radius: 10px;
  opacity: 0.9;
}

.widget-card {
  height: 100%;
  display: flex;
  flex-direction: column;
  border-radius: 10px;
  overflow: hidden;
}

.widget-card :deep(.el-card__header) {
  padding-left: 38px;
  flex-shrink: 0;
}

.widget-card :deep(.el-card__body) {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.chart-box {
  height: 100%;
  min-height: 160px;
}

.widget-drag {
  position: absolute;
  left: 8px;
  top: 12px;
  z-index: 10;
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #909399;
  cursor: grab;
  border-radius: 4px;
  opacity: 0.45;
}

.widget-drag:hover {
  opacity: 1;
  background: #f1f5f9;
}

.widget-drag:active {
  cursor: grabbing;
}

.layout-tip {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
}

.stat-card {
  border: none;
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
  position: relative;
  overflow: hidden;
}

.stat-card--link {
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease, filter 0.2s ease;
}

.stat-card--link:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.18);
  filter: brightness(1.03);
}

.stat-card--link:focus-visible {
  outline: 3px solid rgba(24, 144, 255, 0.65);
  outline-offset: 2px;
}

.stat-arrow {
  margin-left: auto;
  color: rgba(255, 255, 255, 0.62);
  transition: transform 0.2s ease, color 0.2s ease;
}

.stat-card--link:hover .stat-arrow {
  color: #fff;
  transform: translateX(3px);
}

.stat-card--primary { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
.stat-card--success { background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); }
.stat-card--warning { background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); }
.stat-card--danger { background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); }

.stat-content {
  display: flex;
  align-items: center;
  gap: 20px;
  color: #fff;
}

.stat-icon {
  opacity: 0.8;
}

.stat-info {
  color: #fff;
}

.stat-value {
  font-size: 28px;
  font-weight: bold;
  color: #fff;
}

.stat-label {
  font-size: 14px;
  opacity: 0.85;
  color: #fff;
}

.chart-row {
  margin-bottom: 0;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.mono {
  font-family: Consolas, Monaco, monospace;
  font-size: 13px;
}

.unack-card .card-header > span {
  display: flex;
  align-items: center;
  gap: 6px;
}

/* 使用率 TOP5 */
.top-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.top-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 10px;
  border: 1px solid #f0f2f5;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
}

.top-row:hover {
  background: #f5f7fa;
}

.top-rank {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #eef2f7;
  color: #606266;
  font-size: 12px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

.top-rank.rank-1 { background: #f56c6c; color: #fff; }
.top-rank.rank-2 { background: #e6a23c; color: #fff; }
.top-rank.rank-3 { background: #409eff; color: #fff; }

.top-main {
  flex: 1;
  min-width: 0;
}

.top-name {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 5px;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.top-name > span {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.top-bars {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.top-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: #909399;
}

.top-bar .el-progress {
  flex: 1;
}

.top-bar b {
  width: 46px;
  text-align: right;
  color: #606266;
}

.top-bar .bar-label {
  width: 44px;
  flex-shrink: 0;
  white-space: nowrap;
}

.top-temp {
  flex-shrink: 0;
  font-size: 12px;
  color: #909399;
}

.layout-section-title {
  margin-bottom: 10px;
  font-weight: 600;
  color: #303133;
}

.layout-checks {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 18px;
}

.layout-checks .el-checkbox {
  margin-right: 0;
}

.temp-high { color: #f5222d; font-weight: bold; }
.temp-warn { color: #fa8c16; font-weight: bold; }

.server-hw-list {
  height: 100%;
  overflow: auto;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 10px;
}

.server-hw-device {
  min-width: 0;
  padding: 10px 11px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fafcff;
}

.server-hw-head {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.server-hw-ip {
  color: #94a3b8;
  font-family: Consolas, monospace;
  font-size: 10px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.server-sensor-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.server-sensor-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 7px;
  border: 1px solid #e2e8f0;
  border-radius: 5px;
  background: #fff;
}

.server-sensor-chip small {
  color: #94a3b8;
  font-size: 10px;
}

.server-sensor-chip b {
  color: #475569;
  font-family: Consolas, monospace;
  font-size: 11px;
  font-weight: 500;
}

.server-sensor-chip.level-warning {
  border-color: #fcd34d;
  background: #fffbeb;
}

.server-sensor-chip.level-warning b {
  color: #d97706;
}

.server-sensor-chip.level-critical {
  border-color: #fda4af;
  background: #fff1f2;
}

.server-sensor-chip.level-critical b {
  color: #e11d48;
}

.server-sensor-chip.level-muted b {
  color: #cbd5e1;
}


/* ============================================================
   监控总览 · Operations Signal Deck 全新页面设计
   ============================================================ */
.ops-page {
  display: flex;
  flex-direction: column;
  gap: 14px;
  color: #1f3040;
}

.ops-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  padding: 4px 2px 16px;
  border-bottom: 1px solid #e4e9ee;
}

.ops-kicker {
  color: #b45309;
  font-family: Consolas, monospace;
  font-size: 8px;
  font-weight: 700;
  letter-spacing: 2.2px;
}

.ops-title h1 {
  margin: 6px 0 0;
  color: #142a3b;
  font-size: 28px;
  font-weight: 700;
  letter-spacing: 0.3px;
}

.ops-title p {
  margin: 6px 0 0;
  color: #7d8f9f;
  font-size: 11px;
}

.ops-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
}

.ops-shared {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #64748b;
  font-size: 11px;
}

.ops-actions :deep(.el-button) {
  border-color: #dde6ee;
  border-radius: 8px;
  background: #fff;
  color: #4b6478;
}

.ops-kpis {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 9px;
}

.ops-kpi {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  min-width: 0;
  padding: 12px 14px 11px;
  overflow: hidden;
  border: 1px solid #e2e9f0;
  border-radius: 10px;
  background: #fff;
  text-align: left;
  cursor: pointer;
  transition: transform 0.16s ease, box-shadow 0.16s ease;
}

.ops-kpi::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: var(--ops-kpi-color, #0ea5e9);
}

.ops-kpi:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(31, 64, 92, 0.08);
}

.ops-kpi > span {
  color: #7b8d9e;
  font-size: 10px;
}

.ops-kpi strong {
  color: #172f43;
  font-family: "Cascadia Mono", monospace;
  font-size: 24px;
  line-height: 1.1;
}

.ops-kpi strong small {
  margin-left: 2px;
  color: #97a8b6;
  font-size: 9px;
  font-weight: 400;
}

.ops-kpi em {
  overflow: hidden;
  max-width: 100%;
  color: #9aaab8;
  font-size: 8px;
  font-style: normal;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ops-kpi.tone-blue { --ops-kpi-color: #3b82f6; }
.ops-kpi.tone-cyan { --ops-kpi-color: #0891b2; }
.ops-kpi.tone-green { --ops-kpi-color: #10b981; }
.ops-kpi.tone-red { --ops-kpi-color: #ef4444; }
.ops-kpi.tone-amber { --ops-kpi-color: #f59e0b; }
.ops-kpi.tone-violet { --ops-kpi-color: #8b5cf6; }
.ops-kpi.tone-red strong { color: #c24141; }

.ops-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(280px, 0.72fr) minmax(310px, 0.9fr);
  grid-template-areas:
    "devices devices devices"
    "alerts type top"
    "alerts trend top"
    "server server server";
  gap: 12px;
  align-items: stretch;
}

.ops-card {
  min-width: 0;
  overflow: hidden;
  border: 1px solid #e1e9f0;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 4px 16px rgba(30, 58, 82, 0.04);
}

.ops-alerts { grid-area: alerts; display: flex; flex-direction: column; min-height: 620px; }
.ops-type { grid-area: type; }
.ops-top { grid-area: top; display: flex; flex-direction: column; }
.ops-trend { grid-area: trend; }
.ops-server { grid-area: server; }
.ops-devices { grid-area: devices; }

.ops-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex: 0 0 auto;
  padding: 12px 14px;
  border-bottom: 1px solid #edf2f6;
  background: #fbfdff;
}

.ops-card-head > div > span {
  display: block;
  color: #b8a58e;
  font-family: Consolas, monospace;
  font-size: 7px;
  letter-spacing: 1.4px;
}

.ops-card-head h2 {
  margin: 3px 0 0;
  color: #263d50;
  font-size: 13px;
  font-weight: 600;
}

.ops-total {
  color: #263d50;
  font-family: "Cascadia Mono", monospace;
  font-size: 18px;
}

.ops-legend {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: #879baa;
  font-size: 9px;
}

.ops-legend i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #f59e0b;
}

.ops-alert-body {
  flex: 1;
  min-height: 0;
  padding: 4px 8px 10px;
}

.ops-source {
  color: #7a8f9e;
  font-size: 10px;
}

.ops-type .ops-chart {
  height: 220px;
}

.ops-trend .ops-chart {
  height: 230px;
}

.ops-chart {
  width: 100%;
  min-height: 180px;
}

.ops-top-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
}

.ops-top-row {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 9px 10px;
  border: 1px solid #eef3f7;
  border-radius: 9px;
  background: #fbfdff;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.ops-top-row:hover {
  border-color: #cfe2e6;
  background: #fff;
}

.ops-rank {
  flex: 0 0 auto;
  color: #b5c1ca;
  font-family: monospace;
  font-size: 10px;
}

.ops-rank.rank-1 { color: #dc2626; }
.ops-rank.rank-2 { color: #d97706; }
.ops-rank.rank-3 { color: #0284c7; }

.ops-top-main {
  flex: 1;
  min-width: 0;
}

.ops-top-name {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}

.ops-top-name b {
  overflow: hidden;
  color: #31485a;
  font-size: 11px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ops-top-name span {
  flex: 0 0 auto;
  color: #93a5b3;
  font-size: 9px;
}

.ops-top-track {
  height: 5px;
  overflow: hidden;
  border-radius: 4px;
  background: #eef3f7;
}

.ops-top-track i {
  display: block;
  height: 100%;
  border-radius: inherit;
}

.ops-top-row > strong {
  flex: 0 0 auto;
  min-width: 48px;
  color: #263d50;
  font-family: "Cascadia Mono", monospace;
  font-size: 11px;
  text-align: right;
}

.ops-top-triple {
  align-items: flex-start;
}

.ops-triple {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ops-triple-line {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr) 52px;
  align-items: center;
  gap: 6px;
}

.ops-triple-line > span {
  color: #8a9dab;
  font-size: 8px;
}

.ops-triple-line > i {
  display: block;
  height: 3px;
  overflow: hidden;
  border-radius: 3px;
  background: #eef3f7;
}

.ops-triple-line > i > em {
  display: block;
  height: 100%;
  border-radius: inherit;
}

.ops-triple-line > b {
  color: #4c6577;
  font-family: "Cascadia Mono", monospace;
  font-size: 9px;
  font-weight: 500;
  text-align: right;
}

.ops-device-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  min-width: 0;
}

.ops-device-table {
  min-width: 0;
  overflow: hidden;
}

.ops-device-tools {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.ops-device-tools :deep(.el-checkbox__label) {
  padding-left: 4px;
  font-size: 10px;
}

.ops-column-picker {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ops-column-picker :deep(.el-checkbox) {
  height: 25px;
  margin-right: 0;
}

.ops-device-table :deep(.ops-device-group-row > td) {
  padding: 7px 10px;
  background: #f3f9fc;
  border-bottom: 1px solid #e3eef5;
}

.ops-device-group {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 18px;
}

.ops-device-group-label {
  color: #314e61;
  font-size: 10px;
  font-weight: 700;
}

.ops-device-group-count {
  padding: 2px 6px;
  border-radius: 4px;
  background: #e5f2f8;
  color: #5b7d90;
  font-family: Consolas, monospace;
  font-size: 8px;
}

.ops-fleet-side {
  display: flex;
  flex-direction: column;
  gap: 13px;
  padding: 14px;
  border-left: 1px solid #edf2f6;
  background: #fbfdff;
}

.ops-fleet-title span {
  display: block;
  color: #b8a58e;
  font-family: Consolas, monospace;
  font-size: 7px;
  letter-spacing: 1.4px;
}

.ops-fleet-title b {
  display: block;
  margin-top: 3px;
  color: #263d50;
  font-size: 13px;
}

.ops-fleet-kpis {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
}

.ops-fleet-kpis > div {
  padding: 8px 9px;
  border: 1px solid #e8eff5;
  border-radius: 7px;
  background: #fff;
}

.ops-fleet-kpis b {
  display: block;
  color: #1c465e;
  font-family: "Cascadia Mono", monospace;
  font-size: 19px;
  line-height: 1.05;
}

.ops-fleet-kpis span {
  color: #8b9eac;
  font-size: 8px;
}

.ops-fleet-kpis .warning b { color: #b45309; }
.ops-fleet-kpis .danger b { color: #dc2626; }
.ops-fleet-kpis .amber b { color: #b45309; }

.ops-fleet-block {
  padding-top: 10px;
  border-top: 1px solid #edf2f6;
}

.ops-fleet-block-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.ops-fleet-block-head b {
  color: #506a7c;
  font-size: 10px;
  font-weight: 600;
}

.ops-fleet-block-head span {
  color: #9aabb8;
  font-size: 8px;
}

.ops-fleet-type {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr) 22px;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}

.ops-fleet-type > span {
  overflow: hidden;
  color: #7a909f;
  font-size: 8px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ops-fleet-type > i {
  height: 4px;
  overflow: hidden;
  border-radius: 3px;
  background: #edf3f7;
}

.ops-fleet-type > i > em {
  display: block;
  height: 100%;
  border-radius: inherit;
}

.ops-fleet-type > b {
  color: #5c7587;
  font-family: monospace;
  font-size: 9px;
  text-align: right;
}

.ops-fleet-alert {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  padding: 6px 7px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: #718898;
  font-size: 9px;
  text-align: left;
  cursor: pointer;
}

.ops-fleet-alert:hover {
  background: #fff;
  color: #b45309;
}

.ops-fleet-alert span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ops-fleet-alert b {
  flex: 0 0 auto;
  color: #c2410c;
  font-family: monospace;
  font-size: 9px;
}

.ops-fleet-empty {
  padding: 8px 0;
  color: #a8b6c1;
  font-size: 9px;
}

.ops-server-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 10px;
  padding: 12px;
}

.ops-server-item {
  padding: 10px;
  border: 1px solid #edf2f6;
  border-radius: 9px;
  background: #fbfdff;
}

.ops-server-name {
  padding: 0;
  border: 0;
  background: transparent;
  color: #176c78;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}

.ops-server-item > span {
  margin-left: 8px;
  color: #98a9b7;
  font-family: monospace;
  font-size: 9px;
}

.ops-sensors {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 7px;
}

.ops-sensors span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 6px;
  border: 1px solid #e8eff5;
  border-radius: 5px;
  color: #8095a5;
  background: #fff;
  font-size: 8px;
}

.ops-sensors b {
  color: #506b7d;
  font-family: monospace;
  font-size: 9px;
}

.ops-sensors .level-warning { border-color: #f5dfb7; background: #fffcf5; }
.ops-sensors .level-critical { border-color: #fecaca; background: #fff7f7; }

.ops-devices :deep(.el-card__body) { padding: 0; }
.ops-devices :deep(.el-table) { --el-table-border-color: #edf2f6; font-size: 11px; }
.ops-devices :deep(.el-table th.el-table__cell) { background: #fbfdff; color: #758a9b; font-weight: 500; }

@media (max-width: 1400px) {
  .ops-device-body { grid-template-columns: minmax(0, 1fr) 260px; }
}

@media (max-width: 1000px) {
  .ops-device-body { grid-template-columns: minmax(0, 1fr); }
  .ops-fleet-side { border-top: 1px solid #edf2f6; border-left: 0; }
}

@media (max-width: 1200px) {
  .ops-grid {
    grid-template-columns: minmax(0, 1fr) minmax(280px, .8fr);
    grid-template-areas:
      "devices devices"
      "alerts type"
      "alerts trend"
      "top top"
      "server server";
  }
  .ops-alerts { min-height: 540px; }
}

@media (max-width: 820px) {
  .ops-header { align-items: flex-start; flex-direction: column; }
  .ops-actions { justify-content: flex-start; }
  .ops-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .ops-grid { display: flex; flex-direction: column; }
  .ops-devices { order: -1; }
  .ops-alerts { min-height: 460px; }
}

</style>
