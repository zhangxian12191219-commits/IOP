<template>
  <div ref="pageRef" class="bs3-page">
    <div class="bs3-bg"></div>
    <header class="bs3-header">
      <div class="bs3-brand">
        <div class="bs3-mark"><el-icon :size="23"><Monitor /></el-icon></div>
        <div>
          <span class="bs3-kicker">ASSET DIGITAL TWIN · LIVE NOC</span>
          <h1>资产全景 · 数字孪生大屏</h1>
        </div>
      </div>
      <div class="bs3-head-center">
        <span class="bs3-live"><i></i>LIVE TELEMETRY</span>
        <span class="bs3-date">{{ dateText }}</span>
        <strong class="bs3-clock">{{ clockText }}</strong>
      </div>
      <div class="bs3-actions">
        <span class="bs3-last">更新于 {{ lastUpdatedText }}</span>
        <el-button size="small" @click="loadData"><el-icon><Refresh /></el-icon>刷新</el-button>
        <el-button size="small" @click="toggleFullscreen"><el-icon><FullScreen /></el-icon>{{ isFullscreen ? '退出全屏' : '全屏' }}</el-button>
        <el-button size="small" @click="$router.push('/bigscreen')"><el-icon><Back /></el-icon>返回</el-button>
      </div>
    </header>

    <main class="bs3-main">
      <section class="bs3-kpis">
        <div v-for="item in kpis" :key="item.key" class="bs3-kpi" :class="`bs3-${item.tone}`">
          <div class="bs3-kpi-icon"><el-icon :size="17"><component :is="item.icon" /></el-icon></div>
          <div class="bs3-kpi-copy"><span>{{ item.label }}</span><strong>{{ item.value }}<small>{{ item.unit }}</small></strong></div>
          <em>{{ item.note }}</em><i class="beam"></i>
        </div>
      </section>

      <section class="bs3-workspace">
        <aside class="bs3-col asset-left">
          <article class="bs3-panel bs3-flex-panel">
            <header class="bs3-panel-head"><div><span class="bs3-eyebrow">01 / ASSET MIX</span><h2>资产类型分布</h2></div><span class="bs3-badge">{{ totalCount }} 台</span></header>
            <div class="bs3-panel-body">
              <div class="bs3-dist">
                <div v-for="item in typeRows" :key="item.key" class="bs3-dist-row">
                  <span class="bs3-dist-name">{{ item.label }}</span>
                  <span class="bs3-dist-bar"><i :style="{ width: `${item.percent}%` }"></i></span>
                  <span class="bs3-dist-value">{{ item.value }}</span>
                </div>
                <div v-if="!typeRows.length" class="bs3-empty">暂无资产数据</div>
              </div>
              <div class="bs3-mini-note">厂商 TOP 5：{{ vendorText }}</div>
            </div>
          </article>

          <article class="bs3-panel bs3-flex-panel">
            <header class="bs3-panel-head"><div><span class="bs3-eyebrow">02 / RESOURCE HEALTH</span><h2>资源健康</h2></div><span class="bs3-badge">实时</span></header>
            <div class="bs3-panel-body">
              <div class="bs3-health-grid">
                <div class="bs3-health-cell"><span>在线率</span><b>{{ onlineRate }}%</b><i><em :style="{ width: `${onlineRate}%` }"></em></i></div>
                <div class="bs3-health-cell"><span>平均 CPU</span><b>{{ avgCpu }}%</b><i><em :style="{ width: `${clamp(avgCpu)}%` }"></em></i></div>
                <div class="bs3-health-cell"><span>平均内存</span><b>{{ avgMemory }}%</b><i><em :style="{ width: `${clamp(avgMemory)}%` }"></em></i></div>
                <div class="bs3-health-cell"><span>平均磁盘</span><b>{{ avgDisk }}%</b><i><em :style="{ width: `${clamp(avgDisk)}%` }"></em></i></div>
              </div>
              <div class="bs3-facts">
                <span>最高温度<b>{{ maxTempText }}</b></span>
                <span>电源异常<b class="bad">{{ powerFailureCount }}</b></span>
                <span>维保到期<b class="warn">{{ warrantyRows.length }}</b></span>
              </div>
              <div class="bs3-facts">
                <span>网络设备<b>{{ networkDeviceCount }}</b></span>
                <span>接口 UP/DOWN<b>{{ interfaceStats.up }} / {{ interfaceStats.down }}</b></span>
                <span>接口错误<b class="warn">{{ interfaceStats.errors }}</b></span>
              </div>
            </div>
          </article>

          <article class="bs3-panel bs3-flex-panel">
            <header class="bs3-panel-head"><div><span class="bs3-eyebrow">03 / SERVER INVENTORY</span><h2>服务器组件</h2></div><span class="bs3-badge">{{ componentTotals.servers }} 台</span></header>
            <div class="bs3-panel-body">
              <div class="bs3-facts bs3-facts-tight">
                <span>CPU<b>{{ componentTotals.cpus }}</b></span>
                <span>内存条<b>{{ componentTotals.memoryModules }}</b></span>
                <span>风扇<b>{{ componentTotals.fans }}</b></span>
                <span>电源<b>{{ componentTotals.powerSupplies }}</b></span>
                <span>硬盘<b>{{ componentTotals.disks }}</b></span>
                <span>温度探头<b>{{ componentTotals.temperatures }}</b></span>
              </div>
              <div v-if="!componentTotals.servers" class="bs3-empty">服务器组件暂未采集</div>
            </div>
          </article>
        </aside>

        <section class="bs3-col asset-center">
          <article class="bs3-panel bs3-3d-panel">
            <header class="bs3-panel-head"><div><span class="bs3-eyebrow">04 / DIGITAL TWIN</span><h2>资产数字孪生</h2></div><span class="bs3-badge">3D 实时</span></header>
            <div class="bs3-3d-wrap">
              <BigScreen3D mode="asset" :items="threeItems" :alerts="alerts" />
              <div v-if="assetsLoaded && !assets.length" class="bs3-data-empty">
                <strong>当前账号没有可见资产</strong>
                <span>请检查用户所属资产群组，或让管理员在「用户权限 → 群组」中分配可见设备。</span>
              </div>
              <div v-if="visible3dAlerts.length" class="bs3-3d-alert-layer">
                <div class="bs3-3d-alert-head">
                  <span><i></i>LIVE ALERTS</span>
                  <b>{{ sorted3dAlerts.length }} 条</b>
                  <em v-if="emergency3dCount">紧急 {{ emergency3dCount }} 条</em>
                </div>
                <TransitionGroup name="bs3-alert-float">
                  <div
                    v-for="(alert, index) in visible3dAlerts"
                    :key="alert.id"
                    class="bs3-3d-alert-float"
                    :class="alert.alert_level || 'warning'"
                    :style="alertFloatStyle(alert, index)"
                  >
                    <div class="bs3-3d-alert-float-head">
                      <span class="bs3-3d-alert-level">{{ alertLevelText(alert.alert_level) }}</span>
                      <time>{{ alertTimeText(alert) }}</time>
                    </div>
                    <b>{{ alert.device_name || alert.device?.name || '告警对象' }}</b>
                    <p>{{ alert.message || '需要处理' }}</p>
                  </div>
                </TransitionGroup>
              </div>
              <div class="bs3-3d-stats">
                <span>在线资产<b>{{ onlineCount }}</b></span>
                <span>离线资产<b>{{ offlineCount }}</b></span>
                <span>平均 CPU<b>{{ avgCpu }}%</b></span>
              </div>
            </div>
          </article>
        </section>

        <aside class="bs3-col right asset-right">
          <article class="bs3-panel bs3-flex-panel">
            <header class="bs3-panel-head"><div><span class="bs3-eyebrow">05 / RESOURCE HOTSPOTS</span><h2>资源使用 Top</h2></div><span class="bs3-badge">CPU</span></header>
            <div class="bs3-panel-body">
              <BigScreenAutoScroll class="bs3-list-scroll" :speed="8">
              <div class="bs3-side-list">
                <div v-for="(row, index) in topCpu" :key="row.id" class="bs3-side-row">
                  <span class="bs3-rank">{{ String(index + 1).padStart(2, '0') }}</span>
                  <div class="bs3-side-main"><b>{{ row.name }}</b><small>{{ row.typeLabel }} · {{ row.ip_address }} · 内存 {{ row.memory }}</small></div>
                  <strong>{{ row.cpu }}</strong>
                </div>
                <div v-if="!topCpu.length" class="bs3-empty">暂无监控指标</div>
              </div>
              </BigScreenAutoScroll>
            </div>
          </article>

          <article class="bs3-panel bs3-flex-panel">
            <header class="bs3-panel-head"><div><span class="bs3-eyebrow">06 / ATTENTION</span><h2>未处理告警</h2></div><span class="bs3-badge rose">{{ alerts.length }} 条</span></header>
            <div class="bs3-panel-body">
              <BigScreenAutoScroll class="bs3-list-scroll" :speed="8">
              <div v-for="item in alerts.slice(0, 6)" :key="item.id" class="bs3-alert-row" :class="item.alert_level || 'warning'">
                <i></i><div><b>{{ item.device_name || item.device?.name || '设备告警' }}</b><small>{{ item.message || item.metric_name || '需要处理' }}</small></div>
              </div>
              <div v-if="!alerts.length" class="bs3-empty">当前没有未处理告警</div>
              </BigScreenAutoScroll>
            </div>
          </article>

          <article class="bs3-panel bs3-flex-panel">
            <header class="bs3-panel-head"><div><span class="bs3-eyebrow">07 / WARRANTY</span><h2>维保到期</h2></div><span class="bs3-badge warn">{{ warrantyRows.length }} 台</span></header>
            <div class="bs3-panel-body">
              <BigScreenAutoScroll class="bs3-list-scroll" :speed="8">
              <div v-for="item in warrantyRows.slice(0, 6)" :key="item.id" class="bs3-side-row">
                <div class="bs3-side-main"><b>{{ item.name }}</b><small>{{ item.warranty_until || '未填写日期' }} · {{ item.vendor || '未标注厂商' }}</small></div>
                <strong :class="item.warranty_days_left <= 3 ? 'bad' : 'warn'">{{ warrantyText(item) }}</strong>
              </div>
              <div v-if="!warrantyRows.length" class="bs3-empty">暂无临近维保资产</div>
              </BigScreenAutoScroll>
            </div>
          </article>
        </aside>

        <article class="bs3-panel bs3-table-panel">
          <header class="bs3-panel-head"><div><span class="bs3-eyebrow">08 / ASSET PULSE</span><h2>资产实时明细</h2></div><span class="bs3-badge">{{ assetRows.length }} / {{ assets.length }} 台 · 在线优先排序</span></header>
          <div class="bs3-panel-body bs3-table-body">
            <BigScreenAutoScroll class="bs3-table-scroll" :speed="14">
            <table class="bs3-table bs3-table-wide">
              <thead><tr><th style="width:15%">资产</th><th>类型</th><th>厂商 / 型号</th><th>IP / 位置</th><th>状态</th><th>CPU</th><th>内存</th><th>磁盘</th><th>温度</th><th>电源</th><th>维保</th><th>告警</th></tr></thead>
              <tbody>
                <tr v-for="row in assetRows" :key="row.id">
                  <td class="name">{{ row.name }}</td>
                  <td>{{ row.typeLabel }}</td>
                  <td>{{ row.vendorModel }}</td>
                  <td class="mono">{{ row.ip_address }}<small class="bs3-cell-sub">{{ row.location || '未标注位置' }}</small></td>
                  <td :class="row.online ? 'ok' : 'bad'">{{ row.online ? '在线' : '离线' }}</td>
                  <td class="mono">{{ row.cpu }}</td>
                  <td class="mono">{{ row.memory }}</td>
                  <td class="mono">{{ row.disk }}</td>
                  <td class="mono">{{ row.temperature }}</td>
                  <td :class="row.powerClass">{{ row.power }}</td>
                  <td :class="row.warrantyClass">{{ row.warranty }}</td>
                  <td :class="row.alertCount ? 'warn' : 'ok'">{{ row.alertCount }}</td>
                </tr>
                <tr v-if="!assetRows.length"><td colspan="12"><div class="bs3-empty">暂无资产数据</div></td></tr>
              </tbody>
            </table>
            </BigScreenAutoScroll>
          </div>
        </article>
      </section>

      <footer class="bs3-footer">
        <span>LIVE FEED</span>
        <div class="bs3-ticker"><div class="bs3-ticker-track"><span>{{ tickerText }}</span><span>{{ tickerText }}</span></div></div>
        <span>资产数字孪生 · 3D ADAPTIVE</span>
      </footer>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Back, Bell, CircleCheck, CircleClose, FullScreen, Monitor, Refresh, Timer, TrendCharts, Warning } from '@element-plus/icons-vue'
import { monitorApi } from '@/api'
import { fetchAllDevices } from '@/utils/bigscreen'
import { deviceTypeLabel } from '@/constants/device'
import BigScreen3D from '@/components/BigScreen3D.vue'
import BigScreenAutoScroll from '@/components/BigScreenAutoScroll.vue'
import '@/styles/bigscreen-3d-pages.css'

const pageRef = ref(null)
const assets = ref([])
const assetsLoaded = ref(false)
const stats = ref({})
const alerts = ref([])
const interfaces = ref([])
const now = ref(new Date())
const lastUpdated = ref(null)
const isFullscreen = ref(false)
let timer = null
let refresh = null
let alertTimer = null

const pad = (v) => String(v).padStart(2, '0')
const dateText = computed(() => `${now.value.getFullYear()}-${pad(now.value.getMonth() + 1)}-${pad(now.value.getDate())}`)
const clockText = computed(() => `${pad(now.value.getHours())}:${pad(now.value.getMinutes())}:${pad(now.value.getSeconds())}`)
const lastUpdatedText = computed(() => lastUpdated.value ? lastUpdated.value.toLocaleTimeString('zh-CN', { hour12: false }) : '--:--:--')
const clamp = (value) => Math.max(0, Math.min(100, Number(value) || 0))
const pct = (value) => value !== null && value !== undefined && Number.isFinite(Number(value)) ? `${Number(value).toFixed(1)}%` : '—'
const num = (value) => Number.isFinite(Number(value)) ? Number(value) : null

function onlineOf(asset) {
  if (typeof asset?.is_online === 'boolean') return asset.is_online
  const collected = asset?.metric?.collected_at
  if (!collected) return false
  const text = /[zZ]|[+-]\d{2}:\d{2}$/.test(collected) ? collected : `${collected}Z`
  const time = new Date(text).getTime()
  return Number.isFinite(time) && Date.now() - time < 10 * 60 * 1000
}
function cpuOf(asset) { return num(asset?.metric?.cpu_usage) || 0 }
function memOf(asset) { return num(asset?.metric?.memory_usage) || 0 }
function diskOf(asset) { return num(asset?.metric?.disk_usage) }
function tempOf(asset) { return num(asset?.metric?.temperature) }
function componentsOf(asset) { return asset?.metric?.components || asset?.metric?.custom?.server_components || {} }
function warrantyText(asset) {
  const days = asset?.warranty_days_left
  if (days === null || days === undefined) return '未填写'
  if (days < 0) return `过期 ${Math.abs(days)} 天`
  return `剩余 ${days} 天`
}

const totalCount = computed(() => (
  assetsLoaded.value ? assets.value.length : Number(stats.value.total_devices || 0)
))
const enabledCount = computed(() => assets.value.filter((item) => item.is_enabled !== false).length)
const onlineCount = computed(() => assets.value.filter(onlineOf).length)
const offlineCount = computed(() => Math.max(0, totalCount.value - onlineCount.value))
const serverCount = computed(() => assets.value.filter((item) => item.device_type === 'server').length)
const onlineRate = computed(() => totalCount.value ? (onlineCount.value / totalCount.value * 100).toFixed(1) : '0.0')
const avgCpu = computed(() => {
  const values = assets.value.filter(onlineOf).map(cpuOf).filter((value) => value > 0)
  return values.length ? (values.reduce((a, b) => a + b, 0) / values.length).toFixed(1) : '0'
})
const avgMemory = computed(() => {
  const values = assets.value.filter(onlineOf).map(memOf).filter((value) => value > 0)
  return values.length ? (values.reduce((a, b) => a + b, 0) / values.length).toFixed(1) : '0'
})
const avgDisk = computed(() => {
  const values = assets.value.map(diskOf).filter((value) => Number.isFinite(value))
  return values.length ? (values.reduce((a, b) => a + b, 0) / values.length).toFixed(1) : '0'
})
const maxTemp = computed(() => {
  const values = assets.value.map(tempOf).filter((value) => Number.isFinite(value))
  return values.length ? Math.max(...values) : null
})
const maxTempText = computed(() => maxTemp.value === null ? '未采集' : `${maxTemp.value.toFixed(1)}℃`)
const powerFailureCount = computed(() => assets.value.filter((item) => item.metric?.power_status === 'failure').length)
const networkDeviceCount = computed(() => assets.value.filter((item) => ['switch', 'router', 'firewall', 'security'].includes(item.device_type)).length)
const unackCount = computed(() => alerts.value.length)

const typeRows = computed(() => {
  const counts = {}
  assets.value.forEach((item) => { const key = item.device_type || 'other'; counts[key] = (counts[key] || 0) + 1 })
  const max = Math.max(1, ...Object.values(counts))
  return Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([key, value]) => ({
    key, value, label: deviceTypeLabel(key), percent: (value / max) * 100,
  }))
})
const vendorText = computed(() => {
  const counts = {}
  assets.value.forEach((item) => { const key = item.vendor || '未标注'; counts[key] = (counts[key] || 0) + 1 })
  return Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 5).map(([name, value]) => `${name} ${value}`).join(' · ') || '暂无'
})
const interfaceById = computed(() => Object.fromEntries(interfaces.value.map((item) => [item.device_id, item])))
const interfaceStats = computed(() => ({
  up: interfaces.value.reduce((sum, item) => sum + Number(item.up || 0), 0),
  down: interfaces.value.reduce((sum, item) => sum + Number(item.down || 0), 0),
  errors: interfaces.value.reduce((sum, item) => sum + Number(item.errors || 0), 0),
}))
const componentTotals = computed(() => {
  const totals = { servers: 0, cpus: 0, memoryModules: 0, fans: 0, powerSupplies: 0, disks: 0, temperatures: 0 }
  assets.value.forEach((asset) => {
    const components = componentsOf(asset)
    if (!components || !Object.keys(components).length) return
    totals.servers += 1
    totals.cpus += components.cpus?.length || 0
    totals.memoryModules += components.memory_modules?.length || 0
    totals.fans += components.fans?.length || 0
    totals.powerSupplies += components.power_supplies?.length || 0
    totals.disks += components.disks?.length || 0
    totals.temperatures += components.temperatures?.length || 0
  })
  return totals
})
const warrantyRows = computed(() => assets.value
  .filter((item) => item.warranty_days_left !== null && item.warranty_days_left !== undefined && item.warranty_days_left <= 30)
  .sort((a, b) => Number(a.warranty_days_left) - Number(b.warranty_days_left)))
const threeItems = computed(() => assets.value.slice(0, 56).map((item) => ({
  deviceId: item.id, name: item.name, value: cpuOf(item), online: onlineOf(item),
  color: onlineOf(item) ? (cpuOf(item) > 80 ? '#fbbf24' : '#34d399') : '#fb7185',
})))
const topCpu = computed(() => assets.value.filter(onlineOf).sort((a, b) => cpuOf(b) - cpuOf(a)).slice(0, 6).map((item) => ({
  ...item, typeLabel: deviceTypeLabel(item.device_type), cpu: pct(cpuOf(item)), memory: pct(memOf(item)),
})))
const assetRows = computed(() => [...assets.value]
  .sort((a, b) => Number(onlineOf(b)) - Number(onlineOf(a)) || cpuOf(b) - cpuOf(a))
  .slice(0, 12)
  .map((item) => {
    const days = item.warranty_days_left
    return {
      ...item,
      typeLabel: deviceTypeLabel(item.device_type),
      online: onlineOf(item),
      vendorModel: [item.vendor, item.model].filter(Boolean).join(' / ') || '—',
      cpu: pct(cpuOf(item)),
      memory: pct(memOf(item)),
      disk: diskOf(item) === null ? '未采集' : pct(diskOf(item)),
      temperature: tempOf(item) === null ? '未采集' : `${tempOf(item).toFixed(1)}℃`,
      power: item.metric?.power_status === 'failure' ? '异常' : item.metric?.power_status === 'normal' ? '正常' : '未知',
      powerClass: item.metric?.power_status === 'failure' ? 'bad' : item.metric?.power_status === 'normal' ? 'ok' : 'warn',
      warranty: days === null || days === undefined ? '未填写' : days < 0 ? `过期${Math.abs(days)}天` : `${days}天`,
      warrantyClass: days !== null && days !== undefined && days <= 3 ? 'bad' : days !== null && days !== undefined && days <= 30 ? 'warn' : '',
      alertCount: Number(item.alert_count || 0),
    }
  }))
const kpis = computed(() => [
  { key: 'total', label: '资产总数', value: totalCount.value, unit: '台', note: `${enabledCount.value} 台启用`, tone: 'cyan', icon: Monitor },
  { key: 'online', label: '在线资产', value: onlineCount.value, unit: '台', note: `${onlineRate.value}% 在线率`, tone: 'mint', icon: CircleCheck },
  { key: 'offline', label: '离线资产', value: offlineCount.value, unit: '台', note: offlineCount.value ? '需要关注' : '全部正常', tone: 'rose', icon: CircleClose },
  { key: 'server', label: '服务器', value: serverCount.value, unit: '台', note: `${componentTotals.value.cpus} 颗 CPU`, tone: 'violet', icon: TrendCharts },
  { key: 'cpu', label: '平均 CPU', value: `${avgCpu.value}%`, unit: '', note: '在线资产', tone: 'cyan', icon: Timer },
  { key: 'memory', label: '平均内存', value: `${avgMemory.value}%`, unit: '', note: '在线资产', tone: 'mint', icon: Timer },
  { key: 'disk', label: '平均磁盘', value: `${avgDisk.value}%`, unit: '', note: '已采集资产', tone: 'amber', icon: Warning },
  { key: 'alert', label: '未处理告警', value: unackCount.value, unit: '条', note: `${warrantyRows.value.length} 台维保到期`, tone: 'rose', icon: Bell },
])
const tickerText = computed(() => {
  if (!assets.value.length) return '资产监控数据接入中，等待采集...'
  return [`资产 ${totalCount.value} 台`, `在线 ${onlineCount.value}`, `离线 ${offlineCount.value}`, `平均 CPU ${avgCpu.value}%`, `平均内存 ${avgMemory.value}%`, `维保到期 ${warrantyRows.value.length} 台`].join('　◆　')
})

const ALERT_LEVEL_RANK = { info: 1, warning: 2, critical: 3, emergency: 4 }
const alertIndex = ref(0)
const sorted3dAlerts = computed(() => [...(alerts.value || [])].sort((a, b) => {
  const rank = (ALERT_LEVEL_RANK[b.alert_level] || 0) - (ALERT_LEVEL_RANK[a.alert_level] || 0)
  if (rank) return rank
  return String(b.created_at || '').localeCompare(String(a.created_at || ''))
}))
const visible3dAlerts = computed(() => {
  const rows = sorted3dAlerts.value
  if (rows.length <= 3) return rows
  const start = (alertIndex.value * 3) % rows.length
  return Array.from({ length: 3 }, (_, offset) => rows[(start + offset) % rows.length])
})
const alertSlotOrder = computed(() => {
  const order = [0, 1, 2, 3]
  let seed = (alertIndex.value + 1) * 17
  for (let i = order.length - 1; i > 0; i -= 1) {
    seed = (seed * 9301 + 49297) % 233280
    const j = seed % (i + 1)
    ;[order[i], order[j]] = [order[j], order[i]]
  }
  return order
})
const emergency3dCount = computed(() => alerts.value.filter((item) => item.alert_level === 'emergency').length)
function alertLevelText(level) {
  return { info: '提示', warning: '警告', critical: '严重', emergency: '紧急' }[level] || '告警'
}
const ALERT_FLOAT_SLOTS = [
  { left: '3%', top: '17%' },
  { left: '53%', top: '17%' },
  { left: '3%', top: '55%' },
  { left: '53%', top: '55%' },
]
function alertFloatStyle(_alert, index) {
  const slot = ALERT_FLOAT_SLOTS[alertSlotOrder.value[index % alertSlotOrder.value.length]]
  return { left: slot.left, top: slot.top }
}

function alertTimeText(alert) {
  const raw = alert?.created_at
  if (!raw) return '--'
  const text = /[zZ]|[+-]\d{2}:?\d{2}$/.test(raw) ? raw : `${raw}Z`
  const date = new Date(text)
  if (Number.isNaN(date.getTime())) return '--'
  const pad = (value) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

async function loadData() {
  try {
    const [assetRes, statsRes, alertRes, interfaceRes] = await Promise.allSettled([
      fetchAllDevices(),
      monitorApi.getDashboard(),
      monitorApi.getUnackAlerts(),
      monitorApi.getInterfaceSummaries(),
    ])
    if (assetRes.status === 'fulfilled') {
      assets.value = assetRes.value || []
      assetsLoaded.value = true
    }
    if (statsRes.status === 'fulfilled') stats.value = statsRes.value?.data || {}
    if (alertRes.status === 'fulfilled') alerts.value = alertRes.value?.data || []
    if (interfaceRes.status === 'fulfilled') interfaces.value = interfaceRes.value?.data?.items || []
    lastUpdated.value = new Date()
  } finally {
    /* 保持上一轮数据，避免大屏刷新时闪空 */
  }
}
async function toggleFullscreen() {
  try {
    if (!document.fullscreenElement) { await pageRef.value?.requestFullscreen(); isFullscreen.value = true }
    else { await document.exitFullscreen(); isFullscreen.value = false }
  } catch { /* ignore */ }
}
function onFullscreen() { isFullscreen.value = Boolean(document.fullscreenElement) }
onMounted(() => {
  loadData()
  timer = setInterval(() => { now.value = new Date() }, 1000)
  refresh = setInterval(() => { if (!document.hidden) loadData() }, 10000)
  alertTimer = setInterval(() => {
    if (visible3dAlerts.value.length) alertIndex.value += 1
  }, 3800)
  document.addEventListener('fullscreenchange', onFullscreen)
})
onBeforeUnmount(() => {
  clearInterval(timer)
  clearInterval(refresh)
  clearInterval(alertTimer)
  document.removeEventListener('fullscreenchange', onFullscreen)
})
</script>

<style scoped>
.bs3-data-empty {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 30px;
  z-index: 5;
  text-align: center;
  background: radial-gradient(ellipse at center, rgba(8, 25, 43, 0.82), rgba(8, 25, 43, 0.42));
  pointer-events: none;
}
.bs3-data-empty strong { color: #e2f3ff; font-size: 16px; }
.bs3-data-empty span { max-width: 360px; color: #8fb2c9; font-size: 12px; line-height: 1.7; }
</style>
