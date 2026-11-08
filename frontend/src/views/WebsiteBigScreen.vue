<template>
  <div ref="pageRef" class="ws-page" :class="{ 'is-fullscreen': isFullscreen }">
    <div class="ws-bg-grid"></div>
    <div class="ws-bg-aurora aurora-a"></div>
    <div class="ws-bg-aurora aurora-b"></div>
    <div class="ws-bg-scan"></div>
    <div class="ws-bg-noise"></div>

    <header class="ws-header">
      <div class="ws-brand">
        <div class="ws-brand-mark"><el-icon :size="24"><Monitor /></el-icon></div>
        <div>
          <span class="ws-kicker">WEBSITE OBSERVABILITY · LIVE NOC</span>
          <h1>网站监控 · 全景态势大屏</h1>
        </div>
      </div>
      <div class="ws-header-center">
        <span class="ws-live"><i></i>LIVE TELEMETRY</span>
        <span class="ws-header-divider"></span>
        <span class="ws-date">{{ dateText }}</span>
        <strong class="ws-clock">{{ clockText }}</strong>
      </div>
      <div class="ws-actions">
        <span class="ws-updated">更新于 {{ lastUpdatedText }}</span>
        <span class="ws-countdown">下次刷新 {{ countdown }}s</span>
        <el-button size="small" @click="loadData(false)">
          <el-icon><Refresh /></el-icon>刷新
        </el-button>
        <el-button size="small" @click="toggleFullscreen">
          <el-icon><FullScreen /></el-icon>{{ isFullscreen ? '退出全屏' : '全屏' }}
        </el-button>
        <el-button size="small" @click="$router.push('/bigscreen')">
          <el-icon><Back /></el-icon>返回
        </el-button>
      </div>
    </header>

    <main class="ws-main">
      <div v-if="error" class="ws-error">
        <el-icon><Warning /></el-icon>
        <span>{{ error }}</span>
        <button type="button" @click="loadData(false)">重试</button>
      </div>

      <section class="ws-kpis">
        <div v-for="item in kpis" :key="item.key" class="ws-kpi" :class="`tone-${item.tone}`">
          <div class="ws-kpi-icon"><el-icon :size="19"><component :is="item.icon" /></el-icon></div>
          <div class="ws-kpi-copy">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}<small>{{ item.unit }}</small></strong>
          </div>
          <em>{{ item.note }}</em>
          <i class="ws-kpi-beam"></i>
        </div>
      </section>

      <section class="ws-content">
        <aside class="ws-side ws-side-left">
          <article class="ws-panel ws-panel-status">
            <header class="ws-panel-head">
              <div><span class="ws-eyebrow">01 / REACHABILITY</span><h2>站点在线态势</h2></div>
              <span class="ws-head-badge">{{ enabledCount }} 个启用</span>
            </header>
            <div ref="statusChartRef" class="ws-chart ws-chart-donut"></div>
            <div class="ws-status-legend">
              <span><i class="online"></i><b>{{ onlineCount }}</b>在线</span>
              <span><i class="offline"></i><b>{{ offlineCount }}</b>离线</span>
              <span><i class="unknown"></i><b>{{ unknownCount }}</b>无数据</span>
              <span><i class="paused"></i><b>{{ pausedCount }}</b>停用</span>
            </div>
          </article>

          <article class="ws-panel ws-panel-cert">
            <header class="ws-panel-head">
              <div><span class="ws-eyebrow">02 / CERTIFICATE HEALTH</span><h2>证书健康度</h2></div>
              <span class="ws-head-badge" :class="{ danger: certExpiredCount > 0 }">{{ certExpiringCount }} 个临期</span>
            </header>
            <div ref="certChartRef" class="ws-chart ws-chart-cert"></div>
            <div class="ws-cert-summary">
              <span><b>{{ certHealth.good }}</b><small>健康</small></span>
              <span><b class="amber">{{ certHealth.warning }}</b><small>30 天内</small></span>
              <span><b class="red">{{ certHealth.expired }}</b><small>已过期</small></span>
              <span><b class="muted">{{ certHealth.missing }}</b><small>无证书</small></span>
            </div>
          </article>
        </aside>

        <section class="ws-center">
          <article class="ws-panel ws-panel-trend">
            <header class="ws-panel-head">
              <div><span class="ws-eyebrow">03 / RESPONSE FLUCTUATION</span><h2>网站响应波动</h2></div>
              <span class="ws-head-badge live"><i></i>最近 {{ trend.labels.length || 0 }} 个采样</span>
            </header>
            <div ref="trendChartRef" class="ws-chart ws-chart-trend"></div>
            <div class="ws-trend-meta">
              <span>平均响应 <b>{{ formatLatency(stats.avgResponse) }}</b></span>
              <span>峰值 <b>{{ formatLatency(trend.maxResponse) }}</b></span>
              <span>慢站点 <b class="amber">{{ slowCount }}</b></span>
              <span>可用率 <b class="green">{{ stats.uptimeText }}</b></span>
            </div>
          </article>

          <article class="ws-panel ws-panel-sites">
            <header class="ws-panel-head">
              <div><span class="ws-eyebrow">04 / SITE PULSE</span><h2>站点实时态势</h2></div>
              <span class="ws-head-badge">{{ siteRows.length }} 个站点 · 自动滚动</span>
            </header>
            <div class="ws-table-head">
              <span>网站</span><span>状态</span><span>响应</span><span>状态码</span><span>可用率</span><span>证书</span><span>波动</span>
            </div>
            <BigScreenAutoScroll class="ws-table-body" :speed="12">
              <div
                v-for="row in siteRows"
                :key="row.id"
                class="ws-site-row"
                :class="`status-${row.status}`"
                :title="siteTitle(row)"
                @click="openSite(row)"
              >
                <div class="ws-site-main">
                  <i class="ws-site-dot"></i>
                  <div><b>{{ row.name }}</b><small>{{ row.typeText }} · {{ row.category }} · {{ row.host }}</small></div>
                </div>
                <span class="ws-site-status" :class="`status-${row.status}`">{{ row.statusText }}</span>
                <span class="ws-site-response" :class="{ slow: row.isSlow }">{{ row.responseText }}</span>
                <span class="ws-site-code">{{ row.statusCode }}</span>
                <span class="ws-site-uptime">{{ row.uptimeText }}</span>
                <span class="ws-site-cert" :class="`cert-${row.certTone}`">{{ row.certText }}</span>
                <svg v-if="row.spark.hasData" class="ws-spark" viewBox="0 0 90 24" preserveAspectRatio="none" aria-hidden="true">
                  <path :d="row.spark.area" :fill="row.spark.gradient"></path>
                  <path :d="row.spark.line" fill="none" :stroke="row.spark.color" stroke-width="1.5" stroke-linecap="round"></path>
                  <circle :cx="row.spark.last.x" :cy="row.spark.last.y" r="2" :fill="row.spark.color"></circle>
                </svg>
                <span v-else class="ws-spark-empty">—</span>
              </div>
              <div v-if="!siteRows.length" class="ws-empty">
                <el-icon :size="24"><Monitor /></el-icon>
                <span>暂无网站监控数据</span>
              </div>
            </BigScreenAutoScroll>
          </article>
        </section>

        <aside class="ws-side ws-side-right">
          <article class="ws-panel ws-panel-certlist">
            <header class="ws-panel-head">
              <div><span class="ws-eyebrow">05 / EXPIRY COUNTDOWN</span><h2>证书到期倒计时</h2></div>
              <span class="ws-head-badge">{{ certRows.length }} 张</span>
            </header>
            <BigScreenAutoScroll class="ws-cert-list" :speed="10">
              <div v-for="item in certRows" :key="item.id" class="ws-cert-item">
                <div class="ws-cert-line">
                  <b>{{ item.name }}</b>
                  <span :class="`cert-${item.certTone}`">{{ item.certText }}</span>
                </div>
                <div class="ws-cert-bar"><i :style="{ width: `${item.certPercent}%` }"></i></div>
              </div>
              <div v-if="!certRows.length" class="ws-empty small"><span>暂无证书数据</span></div>
            </BigScreenAutoScroll>
          </article>

          <article class="ws-panel ws-panel-slow">
            <header class="ws-panel-head">
              <div><span class="ws-eyebrow">06 / SLOWEST SITES</span><h2>响应最慢 Top</h2></div>
              <span class="ws-head-badge">实时</span>
            </header>
            <BigScreenAutoScroll class="ws-slow-list" :speed="10">
              <div v-for="(item, index) in slowRows" :key="item.id" class="ws-slow-item">
                <span class="ws-rank" :class="{ top: index === 0 }">{{ String(index + 1).padStart(2, '0') }}</span>
                <div class="ws-slow-main"><b>{{ item.name }}</b><div class="ws-slow-bar"><i :style="{ width: `${item.slowPercent}%` }"></i></div></div>
                <strong>{{ item.responseText }}</strong>
              </div>
              <div v-if="!slowRows.length" class="ws-empty small"><span>暂无响应数据</span></div>
            </BigScreenAutoScroll>
          </article>

          <article class="ws-panel ws-panel-alerts">
            <header class="ws-panel-head">
              <div><span class="ws-eyebrow">07 / ATTENTION REQUIRED</span><h2>异常与待处理</h2></div>
              <span class="ws-head-badge danger">{{ alertRows.length }} 项</span>
            </header>
            <BigScreenAutoScroll class="ws-alert-list" :speed="10">
              <div v-for="item in alertRows" :key="`${item.id}-${item.alertType}`" class="ws-alert-item" :class="item.alertTone">
                <span class="ws-alert-mark"></span>
                <div><b>{{ item.name }}</b><small>{{ item.alertText }}</small></div>
                <span>{{ item.alertTime }}</span>
              </div>
              <div v-if="!alertRows.length" class="ws-empty small"><span>当前没有异常</span></div>
            </BigScreenAutoScroll>
          </article>
        </aside>
      </section>

      <footer class="ws-footer">
        <div class="ws-ticker-label"><i></i>LIVE FEED</div>
        <div class="ws-ticker-window">
          <div class="ws-ticker-track" :style="{ animationDuration: `${Math.max(18, tickerText.length * 0.16)}s` }">
            <span>{{ tickerText }}</span><span>{{ tickerText }}</span>
          </div>
        </div>
        <span class="ws-footer-meta">REFRESH 10S · WEBSITE MONITOR · {{ enabledCount }} ACTIVE</span>
      </footer>
    </main>

    <div v-if="loading && !targets.length" class="ws-loading">
      <div class="ws-loader-ring"></div>
      <span>正在接入网站监控数据...</span>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import {
  Back,
  Bell,
  CircleCheck,
  CircleClose,
  FullScreen,
  Lock,
  Monitor,
  Refresh,
  Timer,
  TrendCharts,
  Warning,
} from '@element-plus/icons-vue'
import { websiteApi } from '@/api'
import { formatLatency } from '@/utils/latency'
import BigScreenAutoScroll from '@/components/BigScreenAutoScroll.vue'

const router = useRouter()
const pageRef = ref(null)
const statusChartRef = ref(null)
const certChartRef = ref(null)
const trendChartRef = ref(null)
const targets = ref([])
const loading = ref(true)
const error = ref('')
const now = ref(new Date())
const countdown = ref(10)
const isFullscreen = ref(false)
const lastUpdated = ref(null)
const refreshSeconds = 10
let statusChart = null
let certChart = null
let trendChart = null
let clockTimer = null
let refreshTimer = null
let resizeObserver = null

const pad = (value) => String(value).padStart(2, '0')
const dateText = computed(() => {
  const d = now.value
  const week = ['日', '一', '二', '三', '四', '五', '六'][d.getDay()]
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} 星期${week}`
})
const clockText = computed(() => `${pad(now.value.getHours())}:${pad(now.value.getMinutes())}:${pad(now.value.getSeconds())}`)
const lastUpdatedText = computed(() => {
  if (!lastUpdated.value) return '等待数据'
  return `${pad(lastUpdated.value.getHours())}:${pad(lastUpdated.value.getMinutes())}:${pad(lastUpdated.value.getSeconds())}`
})

function latest(row) {
  return row?.latest_status || {}
}

function certInfo(row) {
  const info = latest(row).cert_info
  return info && !info.error ? info : null
}

function certDays(row) {
  const info = certInfo(row)
  const days = Number(info?.days_left)
  return Number.isFinite(days) ? days : null
}

function certTone(days) {
  if (days === null) return 'missing'
  if (days < 0) return 'expired'
  if (days <= 7) return 'danger'
  if (days <= 30) return 'warning'
  return 'good'
}

function certText(days) {
  if (days === null) return '无证书'
  if (days < 0) return `已过期 ${Math.abs(days)} 天`
  return `${days} 天`
}

function statusOf(row) {
  if (!row.is_enabled) return 'paused'
  const alive = latest(row).is_alive
  if (alive === true) return 'online'
  if (alive === false) return 'offline'
  return 'unknown'
}

function statusText(status) {
  return { online: '在线', offline: '离线', unknown: '无数据', paused: '停用' }[status] || '未知'
}

function hostOf(row) {
  return row.domain || row.ip_address || (() => {
    try {
      return new URL(row.url).host
    } catch {
      return row.url || '-'
    }
  })()
}

function uptimeOf(row) {
  const checks = Array.isArray(row.recent_checks) ? row.recent_checks : []
  if (checks.length) {
    return (checks.filter((item) => item.is_alive).length / checks.length) * 100
  }
  const alive = latest(row).is_alive
  return alive === true ? 100 : alive === false ? 0 : null
}

function sparkline(row) {
  const checks = Array.isArray(row.recent_checks) ? row.recent_checks : []
  const values = checks.length
    ? checks.map((item) => (item.is_alive ? Math.max(0, Number(item.response_time) || 0) : 0))
    : (Number(latest(row).response_time) ? [Number(latest(row).response_time)] : [])
  if (!values.length) return { hasData: false }
  const width = 90
  const height = 24
  const padX = 2
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = Math.max(1, max - min)
  const step = values.length > 1 ? (width - padX * 2) / (values.length - 1) : 0
  const points = values.map((value, index) => ({
    x: padX + index * step,
    y: height - padX - ((value - min) / span) * (height - padX * 2),
  }))
  if (points.length === 1) points.push({ ...points[0], x: width - padX })
  const line = points.map((point, index) => `${index ? 'L' : 'M'}${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(' ')
  const area = `${line} L${points[points.length - 1].x.toFixed(2)},${height} L${points[0].x.toFixed(2)},${height} Z`
  const lastCheck = checks[checks.length - 1] || latest(row)
  const down = lastCheck.is_alive === false
  const slow = !down && Number(lastCheck.response_time || 0) > Math.max(1000, Number(row.slow_threshold_ms || 5000))
  const color = down ? '#fb7185' : slow ? '#fbbf24' : '#38bdf8'
  return {
    hasData: true,
    line,
    area,
    last: points[points.length - 1],
    color,
    gradient: `${color}38`,
  }
}

const enabledTargets = computed(() => targets.value.filter((item) => item.is_enabled))
const enabledCount = computed(() => enabledTargets.value.length)
const onlineCount = computed(() => enabledTargets.value.filter((item) => statusOf(item) === 'online').length)
const offlineCount = computed(() => enabledTargets.value.filter((item) => statusOf(item) === 'offline').length)
const unknownCount = computed(() => enabledTargets.value.filter((item) => statusOf(item) === 'unknown').length)
const pausedCount = computed(() => targets.value.filter((item) => !item.is_enabled).length)
const certExpiredCount = computed(() => enabledTargets.value.filter((item) => (certDays(item) ?? 99) < 0).length)
const certExpiringCount = computed(() => enabledTargets.value.filter((item) => {
  const days = certDays(item)
  return days !== null && days >= 0 && days <= 30
}).length)
const slowCount = computed(() => enabledTargets.value.filter((item) => {
  const status = statusOf(item)
  const response = Number(latest(item).response_time || 0)
  return status === 'online' && response > Number(item.slow_threshold_ms || 5000)
}).length)
const alertCount = computed(() => enabledTargets.value.reduce((sum, item) => sum + Number(item.unack_alerts || 0), 0))

const stats = computed(() => {
  const checks = enabledTargets.value.flatMap((item) => (item.recent_checks || []))
  const aliveChecks = checks.filter((item) => item.is_alive).length
  const uptime = checks.length ? (aliveChecks / checks.length) * 100 : (enabledCount.value ? (onlineCount.value / enabledCount.value) * 100 : 0)
  const responses = enabledTargets.value
    .map((item) => Number(latest(item).response_time || 0))
    .filter((value) => value > 0)
  const avgResponse = responses.length ? responses.reduce((a, b) => a + b, 0) / responses.length : 0
  return {
    uptime,
    uptimeText: `${uptime.toFixed(1)}%`,
    avgResponse,
  }
})

const certHealth = computed(() => {
  const result = { good: 0, warning: 0, expired: 0, missing: 0 }
  enabledTargets.value.forEach((item) => {
    const days = certDays(item)
    if (days === null) result.missing += 1
    else if (days < 0) result.expired += 1
    else if (days <= 30) result.warning += 1
    else result.good += 1
  })
  return result
})

function buildTrend() {
  const points = []
  enabledTargets.value.forEach((row) => {
    ;(row.recent_checks || []).forEach((check) => {
      const time = Date.parse(check.checked_at)
      if (Number.isFinite(time)) {
        points.push({ time, response: Number(check.response_time || 0), alive: check.is_alive })
      }
    })
  })
  if (!points.length) return { labels: [], avg: [], max: [], down: [], maxResponse: 0 }
  const min = Math.min(...points.map((point) => point.time))
  const max = Math.max(...points.map((point) => point.time))
  const bucketCount = Math.min(24, Math.max(6, new Set(points.map((point) => Math.floor(point.time / 60000))).size))
  const buckets = Array.from({ length: bucketCount }, () => ({ sum: 0, count: 0, max: 0, down: 0 }))
  points.forEach((point) => {
    const index = Math.min(bucketCount - 1, Math.floor(((point.time - min) / Math.max(1, max - min)) * bucketCount))
    const bucket = buckets[index]
    if (point.alive) {
      bucket.sum += point.response
      bucket.count += 1
      bucket.max = Math.max(bucket.max, point.response)
    } else {
      bucket.down += 1
    }
  })
  const labels = buckets.map((_, index) => {
    const timestamp = min + ((index + 0.5) / bucketCount) * Math.max(1, max - min)
    const date = new Date(timestamp)
    return `${pad(date.getHours())}:${pad(date.getMinutes())}`
  })
  return {
    labels,
    avg: buckets.map((bucket) => (bucket.count ? Math.round(bucket.sum / bucket.count) : 0)),
    max: buckets.map((bucket) => bucket.max),
    down: buckets.map((bucket) => bucket.down),
    maxResponse: Math.max(...buckets.map((bucket) => bucket.max), 0),
  }
}

const trend = computed(buildTrend)

const siteRows = computed(() => {
  const rank = { offline: 0, unknown: 1, online: 2, paused: 3 }
  return [...targets.value]
    .sort((a, b) => {
      const statusDiff = (rank[statusOf(a)] ?? 9) - (rank[statusOf(b)] ?? 9)
      if (statusDiff !== 0) return statusDiff
      const certDiff = (certDays(a) ?? 9999) - (certDays(b) ?? 9999)
      return certDiff || Number(latest(b).response_time || 0) - Number(latest(a).response_time || 0)
    })
    .map((row) => {
      const status = statusOf(row)
      const response = Number(latest(row).response_time || 0)
      const days = certDays(row)
      const uptime = uptimeOf(row)
      const checked = latest(row).checked_at
      return {
        ...row,
        status,
        statusText: statusText(status),
        host: hostOf(row),
        responseText: status === 'online' || status === 'offline' ? formatLatency(response) : '—',
        statusCode: latest(row).status_code ?? '—',
        uptimeText: uptime === null ? '—' : `${uptime.toFixed(1)}%`,
        typeText: ({ http: 'HTTP', https: 'HTTPS', tcp: 'TCP', ping: 'PING' }[row.monitor_type] || row.monitor_type || 'HTTP'),
        certText: certText(days),
        certTone: certTone(days),
        certPercent: days === null ? 0 : Math.max(4, Math.min(100, Math.max(0, days) / 90 * 100)),
        isSlow: status === 'online' && response > Number(row.slow_threshold_ms || 5000),
        checkedAt: checked ? String(checked).replace('T', ' ').slice(11, 19) : '—',
        spark: sparkline(row),
      }
    })
})

const certRows = computed(() => siteRows.value
  .filter((row) => row.certTone !== 'missing')
  .sort((a, b) => (certDays(a) ?? 9999) - (certDays(b) ?? 9999))
  .slice(0, 6))

const slowRows = computed(() => {
  const sorted = siteRows.value
    .filter((row) => row.status === 'online' && Number(latest(row).response_time || 0) > 0)
    .sort((a, b) => Number(latest(b).response_time || 0) - Number(latest(a).response_time || 0))
    .slice(0, 5)
  const maxResponse = Math.max(1, ...sorted.map((row) => Number(latest(row).response_time || 0)))
  return sorted.map((row) => ({
    ...row,
    slowPercent: Math.max(8, Math.min(100, Number(latest(row).response_time || 0) / maxResponse * 100)),
  }))
})

const alertRows = computed(() => {
  const list = []
  siteRows.value.forEach((row) => {
    if (row.status === 'offline') {
      list.push({ ...row, alertType: 'offline', alertTone: 'critical', alertText: `站点离线 · 状态码 ${row.statusCode}`, alertTime: row.checkedAt || '刚刚' })
    } else if (row.isSlow) {
      list.push({ ...row, alertType: 'slow', alertTone: 'warning', alertText: `响应超过阈值 ${row.responseText}`, alertTime: row.checkedAt || '刚刚' })
    } else if (row.certTone === 'expired' || row.certTone === 'danger') {
      list.push({ ...row, alertType: 'cert', alertTone: 'warning', alertText: `证书${row.certTone === 'expired' ? '已过期' : '即将到期'} · ${row.certText}`, alertTime: '证书' })
    } else if (Number(row.unack_alerts || 0) > 0) {
      list.push({ ...row, alertType: 'alert', alertTone: 'warning', alertText: `${row.unack_alerts} 条未处理告警`, alertTime: '待处理' })
    }
  })
  return list.slice(0, 6)
})

const tickerText = computed(() => {
  if (!targets.value.length) return '网站监控数据接入中，等待首个检查周期...'
  const parts = [`共 ${targets.value.length} 个监控站点`, `在线 ${onlineCount.value}`, `离线 ${offlineCount.value}`, `可用率 ${stats.value.uptimeText}`, `平均响应 ${formatLatency(stats.value.avgResponse)}`]
  if (certExpiringCount.value) parts.push(`证书临期 ${certExpiringCount.value}`)
  if (alertCount.value) parts.push(`待处理告警 ${alertCount.value}`)
  if (offlineCount.value) parts.push(`离线站点：${siteRows.value.filter((row) => row.status === 'offline').map((row) => row.name).join('、')}`)
  return parts.join('　◆　')
})

function siteTitle(row) {
  return [
    `类型 ${row.typeText}`,
    `URL ${row.url || row.host}`,
    `预期状态 ${row.expected_statuses || row.expected_status || '-'}`,
    `检查间隔 ${row.check_interval || '-'} 秒`,
    `超时 ${row.timeout || '-'} 秒`,
    `最后检查 ${row.checkedAt}`,
    `未处理告警 ${row.unack_alerts || 0} 条`,
  ].join(' · ')
}

const kpis = computed(() => [
  { key: 'total', label: '监控网站', value: targets.value.length, unit: '个', note: `${enabledCount.value} 个启用`, tone: 'cyan', icon: Monitor },
  { key: 'online', label: '在线站点', value: onlineCount.value, unit: '个', note: `${stats.value.uptimeText} 可用率`, tone: 'green', icon: CircleCheck },
  { key: 'offline', label: '离线站点', value: offlineCount.value, unit: '个', note: offlineCount.value ? '需要关注' : '全部正常', tone: 'red', icon: CircleClose },
  { key: 'uptime', label: '整体可用率', value: stats.value.uptimeText, unit: '', note: '基于最近采样', tone: 'blue', icon: TrendCharts },
  { key: 'response', label: '平均响应', value: formatLatency(stats.value.avgResponse), unit: '', note: `${slowCount.value} 个慢站点`, tone: 'violet', icon: Timer },
  { key: 'slow', label: '响应波动', value: slowCount.value, unit: '个', note: '超过慢阈值', tone: 'amber', icon: Warning },
  { key: 'cert', label: '证书临期', value: certExpiringCount.value, unit: '个', note: `${certExpiredCount.value} 个已过期`, tone: 'amber', icon: Lock },
  { key: 'alert', label: '待处理告警', value: alertCount.value, unit: '条', note: '未确认', tone: 'pink', icon: Bell },
])

function initCharts() {
  if (statusChartRef.value && !statusChart) statusChart = echarts.init(statusChartRef.value)
  if (certChartRef.value && !certChart) certChart = echarts.init(certChartRef.value)
  if (trendChartRef.value && !trendChart) trendChart = echarts.init(trendChartRef.value)
}

function updateCharts() {
  initCharts()
  if (statusChart) {
    statusChart.setOption({
      animationDuration: 800,
      tooltip: { trigger: 'item', backgroundColor: 'rgba(3,14,24,.94)', borderColor: 'rgba(56,189,248,.3)', textStyle: { color: '#d6f3ff' } },
      series: [{
        type: 'pie',
        radius: ['54%', '76%'],
        center: ['50%', '48%'],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: '#061421', borderWidth: 3 },
        label: { show: false },
        data: [
          { name: '在线', value: onlineCount.value, itemStyle: { color: '#34d399' } },
          { name: '离线', value: offlineCount.value, itemStyle: { color: '#fb7185' } },
          { name: '无数据', value: unknownCount.value, itemStyle: { color: '#64748b' } },
          { name: '停用', value: pausedCount.value, itemStyle: { color: '#475569' } },
        ],
      }],
      graphic: [{
        type: 'text', left: 'center', top: '39%',
        style: { text: String(enabledCount.value), fill: '#ecfeff', font: '600 24px "Microsoft YaHei", sans-serif' },
      }, {
        type: 'text', left: 'center', top: '53%',
        style: { text: 'ACTIVE SITES', fill: '#6fb3ca', font: '9px "Microsoft YaHei", sans-serif' },
      }],
    }, true)
  }
  if (certChart) {
    certChart.setOption({
      animationDuration: 900,
      grid: { left: 12, right: 18, top: 12, bottom: 8, containLabel: true },
      xAxis: { type: 'value', axisLabel: { show: false }, splitLine: { show: false }, axisLine: { show: false }, axisTick: { show: false } },
      yAxis: { type: 'category', inverse: true, data: ['健康', '30天内', '已过期', '无证书'], axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: '#8bb7c9', fontSize: 10 } },
      series: [{
        type: 'bar', barWidth: 9, showBackground: true,
        backgroundStyle: { color: 'rgba(56,189,248,.06)', borderRadius: 6 },
        itemStyle: { borderRadius: 6, color: (params) => ['#22d3ee', '#fbbf24', '#fb7185', '#64748b'][params.dataIndex] },
        label: { show: true, position: 'right', color: '#d9f6ff', fontSize: 10 },
        data: [certHealth.value.good, certHealth.value.warning, certHealth.value.expired, certHealth.value.missing],
      }],
    }, true)
  }
  if (trendChart) {
    trendChart.setOption({
      animationDuration: 900,
      color: ['#38bdf8', '#a78bfa', '#fbbf24'],
      tooltip: { trigger: 'axis', backgroundColor: 'rgba(3,14,24,.94)', borderColor: 'rgba(56,189,248,.3)', textStyle: { color: '#d6f3ff' } },
      legend: { right: 8, top: 0, itemWidth: 12, itemHeight: 6, textStyle: { color: '#8bb7c9', fontSize: 10 } },
      grid: { left: 12, right: 18, top: 32, bottom: 10, containLabel: true },
      xAxis: { type: 'category', boundaryGap: false, data: trend.value.labels, axisLine: { lineStyle: { color: 'rgba(56,189,248,.18)' } }, axisLabel: { color: '#6f9caf', fontSize: 9, hideOverlap: true }, axisTick: { show: false } },
      yAxis: [
        { type: 'value', name: 'ms', nameTextStyle: { color: '#6f9caf', fontSize: 9 }, axisLabel: { color: '#6f9caf', fontSize: 9 }, splitLine: { lineStyle: { color: 'rgba(56,189,248,.08)' } }, axisLine: { show: false } },
        { type: 'value', name: '离线', nameTextStyle: { color: '#fbbf24', fontSize: 9 }, axisLabel: { color: '#8a6b2d', fontSize: 9 }, splitLine: { show: false }, axisLine: { show: false } },
      ],
      series: [
        {
          name: '平均响应', type: 'line', smooth: true, symbol: 'none', data: trend.value.avg,
          lineStyle: { width: 2.5, shadowBlur: 12, shadowColor: 'rgba(56,189,248,.55)' },
          areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(56,189,248,.38)' }, { offset: 1, color: 'rgba(56,189,248,.01)' }]) },
        },
        {
          name: '峰值响应', type: 'line', smooth: true, symbol: 'none', data: trend.value.max,
          lineStyle: { width: 1.2, type: 'dashed' }, itemStyle: { color: '#a78bfa' },
          areaStyle: { color: 'rgba(167,139,250,.04)' },
        },
        { name: '离线检查', type: 'bar', yAxisIndex: 1, barWidth: 5, data: trend.value.down, itemStyle: { color: 'rgba(251,191,36,.8)', borderRadius: [3, 3, 0, 0] } },
      ],
    }, true)
  }
}

function resizeCharts() {
  statusChart?.resize()
  certChart?.resize()
  trendChart?.resize()
}

async function loadData(showLoading = true) {
  if (showLoading) loading.value = true
  try {
    const all = []
    let page = 1
    while (page <= 5) {
      const res = await websiteApi.getList({ page, size: 100, sort_by: 'sort_order', sort_order: 'asc' })
      const items = res.data?.items || []
      all.push(...items)
      if (items.length < 100 || all.length >= Number(res.data?.total || 0)) break
      page += 1
    }
    targets.value = all
    lastUpdated.value = new Date()
    error.value = ''
    await nextTick()
    updateCharts()
  } catch (e) {
    error.value = e?.response?.data?.detail || e?.message || '网站监控数据加载失败'
  } finally {
    loading.value = false
  }
}

function openSite(row) {
  router.push(`/website/${row.id}`)
}

async function toggleFullscreen() {
  try {
    if (!document.fullscreenElement) {
      await pageRef.value?.requestFullscreen()
      isFullscreen.value = true
    } else {
      await document.exitFullscreen()
      isFullscreen.value = false
    }
  } catch {
    /* 浏览器拒绝全屏时保持普通模式 */
  }
}

function onFullscreenChange() {
  isFullscreen.value = Boolean(document.fullscreenElement)
}

function startTimers() {
  clockTimer = setInterval(() => {
    now.value = new Date()
    countdown.value -= 1
    if (countdown.value <= 0) {
      countdown.value = refreshSeconds
      loadData(false)
    }
  }, 1000)
}

onMounted(async () => {
  await loadData(true)
  startTimers()
  window.addEventListener('resize', resizeCharts)
  document.addEventListener('fullscreenchange', onFullscreenChange)
  if (pageRef.value) {
    resizeObserver = new ResizeObserver(resizeCharts)
    resizeObserver.observe(pageRef.value)
  }
})

onBeforeUnmount(() => {
  clearInterval(clockTimer)
  clearInterval(refreshTimer)
  window.removeEventListener('resize', resizeCharts)
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  resizeObserver?.disconnect()
  statusChart?.dispose()
  certChart?.dispose()
  trendChart?.dispose()
})
</script>

<style scoped>
.ws-page {
  --ws-cyan: #38bdf8;
  --ws-mint: #34d399;
  --ws-amber: #fbbf24;
  --ws-rose: #fb7185;
  --ws-text: #dff7ff;
  --ws-muted: #78a6b8;
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  height: 100vh;
  overflow: hidden;
  color: var(--ws-text);
  background: #030b14;
  font-family: "DIN Alternate", "Bahnschrift", "Microsoft YaHei", sans-serif;
}

.ws-bg-grid, .ws-bg-aurora, .ws-bg-scan, .ws-bg-noise {
  position: fixed;
  inset: 0;
  pointer-events: none;
}

.ws-bg-grid {
  opacity: .62;
  background-image: linear-gradient(rgba(56,189,248,.055) 1px, transparent 1px), linear-gradient(90deg, rgba(56,189,248,.055) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: radial-gradient(circle at 50% 40%, #000 10%, transparent 80%);
}

.ws-bg-aurora {
  filter: blur(70px);
  opacity: .4;
  border-radius: 50%;
}

.aurora-a {
  width: 42vw;
  height: 38vw;
  left: 12%;
  top: 20%;
  background: rgba(14,116,144,.3);
  animation: ws-aurora 12s ease-in-out infinite alternate;
}

.aurora-b {
  width: 32vw;
  height: 32vw;
  right: 6%;
  bottom: 3%;
  background: rgba(76,29,149,.35);
  animation: ws-aurora 16s ease-in-out infinite alternate-reverse;
}

.ws-bg-scan {
  background: linear-gradient(180deg, transparent 0, rgba(56,189,248,.03) 48%, rgba(56,189,248,.08) 50%, rgba(56,189,248,.03) 52%, transparent 100%);
  background-size: 100% 18px;
  animation: ws-scan 12s linear infinite;
  opacity: .7;
}

.ws-bg-noise {
  opacity: .12;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 160 160' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.3'/%3E%3C/svg%3E");
}

.ws-header {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  flex: 0 0 74px;
  padding: 0 24px;
  border-bottom: 1px solid rgba(56,189,248,.18);
  background: linear-gradient(180deg, rgba(3,14,25,.96), rgba(3,14,25,.72));
  box-shadow: 0 8px 28px rgba(0,0,0,.22);
}

.ws-brand { display: flex; align-items: center; gap: 12px; min-width: 310px; }
.ws-brand-mark {
  display: grid; place-items: center; width: 42px; height: 42px;
  border: 1px solid rgba(56,189,248,.48); border-radius: 9px;
  color: #7dd3fc; background: rgba(8,47,73,.55);
  box-shadow: inset 0 0 16px rgba(56,189,248,.15), 0 0 18px rgba(56,189,248,.12);
}
.ws-kicker { display: block; color: #6fb3ca; font-size: 9px; letter-spacing: 2.5px; line-height: 1.2; }
.ws-brand h1 { margin: 3px 0 0; font-size: clamp(17px, 1.35vw, 24px); font-weight: 600; letter-spacing: 1px; color: #ecfeff; }
.ws-header-center { display: flex; align-items: center; gap: 12px; color: #8bb7c9; font-size: 11px; }
.ws-live { display: inline-flex; align-items: center; gap: 6px; color: #86efac; font-size: 10px; letter-spacing: 1.2px; }
.ws-live i, .ws-head-badge.live i { width: 6px; height: 6px; border-radius: 50%; background: #34d399; box-shadow: 0 0 9px #34d399; animation: ws-pulse 1.6s infinite; }
.ws-header-divider { width: 1px; height: 20px; background: rgba(56,189,248,.2); }
.ws-date { font-size: 10px; letter-spacing: .5px; }
.ws-clock { color: #e0f2fe; font-family: "DIN Alternate", "Cascadia Mono", monospace; font-size: clamp(18px, 1.6vw, 26px); font-weight: 600; letter-spacing: 2px; }
.ws-actions { display: flex; align-items: center; gap: 8px; }
.ws-updated { color: #6f9caf; font-size: 10px; white-space: nowrap; }
.ws-countdown { padding: 4px 8px; border: 1px solid rgba(56,189,248,.18); border-radius: 4px; color: #7dd3fc; font-size: 10px; white-space: nowrap; }
.ws-actions :deep(.el-button) { color: #c6ebf5; border-color: rgba(56,189,248,.24); background: rgba(8,47,73,.3); }
.ws-actions :deep(.el-button:hover) { color: #fff; border-color: rgba(56,189,248,.65); background: rgba(8,47,73,.7); }

.ws-main { position: relative; z-index: 1; display: flex; flex: 1; flex-direction: column; gap: 10px; min-height: 0; padding: 12px 18px 8px; }
.ws-error { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border: 1px solid rgba(251,113,133,.4); border-radius: 6px; background: rgba(127,29,29,.25); color: #fecdd3; font-size: 11px; }
.ws-error button { margin-left: auto; border: 0; background: transparent; color: #fda4af; cursor: pointer; text-decoration: underline; }

.ws-kpis { display: grid; grid-template-columns: repeat(8, minmax(0, 1fr)); gap: 9px; flex: 0 0 auto; }
.ws-kpi {
  position: relative; display: flex; align-items: center; gap: 9px; min-height: 78px; padding: 10px 11px; overflow: hidden;
  border: 1px solid rgba(56,189,248,.14); border-radius: 7px;
  background: linear-gradient(135deg, rgba(8,38,58,.78), rgba(5,19,33,.7));
  box-shadow: inset 0 1px 0 rgba(255,255,255,.025), 0 8px 22px rgba(0,0,0,.12);
}
.ws-kpi::after { content: ''; position: absolute; right: -12px; bottom: -20px; width: 62px; height: 62px; border: 1px solid currentColor; border-radius: 50%; opacity: .1; }
.ws-kpi-icon { display: grid; place-items: center; flex: 0 0 33px; width: 33px; height: 33px; border-radius: 7px; background: rgba(56,189,248,.1); color: #67e8f9; }
.ws-kpi-copy { display: flex; flex-direction: column; min-width: 0; }
.ws-kpi-copy > span { color: #88b3c4; font-size: 10px; white-space: nowrap; }
.ws-kpi-copy strong { color: #f0fdff; font-family: "DIN Alternate", "Cascadia Mono", monospace; font-size: clamp(20px, 1.45vw, 28px); line-height: 1.08; white-space: nowrap; }
.ws-kpi-copy small { margin-left: 3px; color: #79a9bb; font-family: "Microsoft YaHei", sans-serif; font-size: 9px; font-weight: 400; }
.ws-kpi em { align-self: flex-end; margin-left: auto; color: #5d8fa4; font-size: 9px; font-style: normal; white-space: nowrap; }
.ws-kpi-beam { position: absolute; left: 0; right: 0; bottom: 0; height: 2px; background: linear-gradient(90deg, transparent, currentColor, transparent); opacity: .55; }
.tone-cyan { color: #38bdf8; } .tone-green { color: #34d399; } .tone-red { color: #fb7185; } .tone-blue { color: #60a5fa; }
.tone-violet { color: #a78bfa; } .tone-amber { color: #fbbf24; } .tone-pink { color: #f472b6; }
.tone-green .ws-kpi-icon { color: #6ee7b7; background: rgba(52,211,153,.1); }
.tone-red .ws-kpi-icon { color: #fda4af; background: rgba(251,113,133,.1); }
.tone-amber .ws-kpi-icon { color: #fde68a; background: rgba(251,191,36,.1); }
.tone-violet .ws-kpi-icon { color: #c4b5fd; background: rgba(167,139,250,.1); }

.ws-content { display: grid; grid-template-columns: minmax(225px, .9fr) minmax(470px, 1.9fr) minmax(225px, .92fr); gap: 10px; flex: 1; min-height: 0; }
.ws-side, .ws-center { display: flex; flex-direction: column; gap: 10px; min-height: 0; }
.ws-panel {
  position: relative; display: flex; flex-direction: column; min-height: 0; overflow: hidden;
  border: 1px solid rgba(56,189,248,.16); border-radius: 7px;
  background: linear-gradient(145deg, rgba(6,29,45,.76), rgba(3,15,27,.68));
  box-shadow: inset 0 1px 0 rgba(255,255,255,.025), 0 10px 28px rgba(0,0,0,.14);
}
.ws-panel::before, .ws-panel::after { content: ''; position: absolute; width: 13px; height: 13px; pointer-events: none; border-color: rgba(56,189,248,.58); }
.ws-panel::before { left: -1px; top: -1px; border-left: 1px solid; border-top: 1px solid; border-top-left-radius: 7px; }
.ws-panel::after { right: -1px; bottom: -1px; border-right: 1px solid; border-bottom: 1px solid; border-bottom-right-radius: 7px; }
.ws-panel-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; flex: 0 0 auto; padding: 10px 12px 4px; }
.ws-eyebrow { display: block; color: #4f8298; font-size: 8px; letter-spacing: 1.5px; line-height: 1.3; }
.ws-panel-head h2 { margin: 2px 0 0; color: #d9f6ff; font-size: clamp(12px, .85vw, 15px); font-weight: 600; letter-spacing: .5px; }
.ws-head-badge { padding: 3px 6px; border: 1px solid rgba(56,189,248,.18); border-radius: 3px; color: #7dd3fc; font-size: 9px; white-space: nowrap; }
.ws-head-badge.danger { color: #fda4af; border-color: rgba(251,113,133,.3); background: rgba(127,29,29,.15); }
.ws-panel-status { flex: 1.08; }
.ws-panel-cert { flex: 1; }
.ws-panel-trend { flex: 1.12; min-height: 220px; }
.ws-panel-sites { flex: 1.5; min-height: 270px; }
.ws-panel-certlist { flex: 1.04; }
.ws-panel-slow { flex: .95; }
.ws-panel-alerts { flex: .9; }
.ws-chart { flex: 1; min-height: 0; }
.ws-chart-donut { min-height: 150px; }
.ws-chart-cert { min-height: 120px; }
.ws-chart-trend { min-height: 150px; }
.ws-status-legend { display: grid; grid-template-columns: 1fr 1fr; gap: 5px 8px; padding: 0 12px 10px; color: #86aebe; font-size: 10px; }
.ws-status-legend span { display: flex; align-items: center; gap: 5px; }
.ws-status-legend i { width: 6px; height: 6px; border-radius: 50%; }
.ws-status-legend b { color: #e0f2fe; font-family: "DIN Alternate", monospace; font-size: 12px; }
.ws-status-legend .online { background: #34d399; box-shadow: 0 0 7px #34d399; }
.ws-status-legend .offline { background: #fb7185; box-shadow: 0 0 7px #fb7185; }
.ws-status-legend .unknown { background: #64748b; }
.ws-status-legend .paused { background: #475569; }
.ws-cert-summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 3px; padding: 0 10px 10px; text-align: center; }
.ws-cert-summary span { display: flex; flex-direction: column; gap: 2px; }
.ws-cert-summary b { color: #e0f2fe; font-family: "DIN Alternate", monospace; font-size: 14px; }
.ws-cert-summary .amber { color: #fbbf24; } .ws-cert-summary .red { color: #fb7185; } .ws-cert-summary .muted { color: #64748b; }
.ws-cert-summary small { color: #6f9caf; font-size: 9px; }
.ws-trend-meta { display: flex; justify-content: space-between; gap: 6px; padding: 0 12px 9px; color: #6f9caf; font-size: 9px; white-space: nowrap; }
.ws-trend-meta b { color: #c7f5ff; font-family: "DIN Alternate", monospace; font-size: 11px; font-weight: 600; }
.ws-trend-meta .amber { color: #fbbf24; } .ws-trend-meta .green { color: #6ee7b7; }

.ws-table-head, .ws-site-row { display: grid; grid-template-columns: minmax(165px, 1.75fr) 60px 72px 52px 66px 83px 92px; align-items: center; gap: 7px; }
.ws-table-head { flex: 0 0 auto; padding: 5px 12px; margin: 1px 0 3px; color: #4f8298; font-size: 9px; letter-spacing: .3px; border-bottom: 1px solid rgba(56,189,248,.1); }
.ws-table-body { flex: 1; min-height: 0; }
.ws-site-row { position: relative; min-height: 37px; padding: 5px 12px; border-bottom: 1px solid rgba(56,189,248,.055); cursor: pointer; transition: background .2s, transform .2s; }
.ws-site-row:hover { background: rgba(56,189,248,.075); }
.ws-site-row.status-offline { background: linear-gradient(90deg, rgba(127,29,29,.28), transparent 70%); animation: ws-alert-row 3.8s ease-in-out infinite; }
.ws-site-row.status-offline:hover { transform: translateX(2px); }
.ws-site-main { display: flex; align-items: center; gap: 7px; min-width: 0; }
.ws-site-dot { flex: 0 0 6px; width: 6px; height: 6px; border-radius: 50%; background: #64748b; }
.status-online .ws-site-dot { background: #34d399; box-shadow: 0 0 7px #34d399; }
.status-offline .ws-site-dot { background: #fb7185; box-shadow: 0 0 8px #fb7185; animation: ws-pulse 1.5s infinite; }
.status-unknown .ws-site-dot { background: #64748b; }
.ws-site-main > div { min-width: 0; }
.ws-site-main b { display: block; overflow: hidden; color: #d9f6ff; font-size: 11px; font-weight: 500; text-overflow: ellipsis; white-space: nowrap; }
.ws-site-main small { display: block; overflow: hidden; color: #5f8b9f; font-size: 8px; text-overflow: ellipsis; white-space: nowrap; }
.ws-site-status { justify-self: start; padding: 2px 6px; border-radius: 3px; font-size: 9px; }
.ws-site-status.status-online { color: #86efac; background: rgba(22,101,52,.32); border: 1px solid rgba(52,211,153,.22); }
.ws-site-status.status-offline { color: #fecdd3; background: rgba(127,29,29,.4); border: 1px solid rgba(251,113,133,.35); }
.ws-site-status.status-unknown { color: #a8b7c7; background: rgba(51,65,85,.28); border: 1px solid rgba(100,116,139,.2); }
.ws-site-status.status-paused { color: #94a3b8; background: rgba(51,65,85,.18); border: 1px solid rgba(100,116,139,.16); }
.ws-site-response, .ws-site-code, .ws-site-uptime, .ws-site-cert { color: #9bc6d5; font-family: "DIN Alternate", monospace; font-size: 10px; white-space: nowrap; }
.ws-site-response.slow { color: #fbbf24; }
.ws-site-uptime { color: #9de9d5; }
.cert-good { color: #6ee7b7 !important; } .cert-warning { color: #fbbf24 !important; } .cert-danger, .cert-expired { color: #fb7185 !important; } .cert-missing { color: #64748b !important; }
.ws-spark { width: 92px; height: 24px; overflow: visible; }
.ws-spark-empty { color: #456b7c; font-size: 9px; }
.ws-empty { display: flex; align-items: center; justify-content: center; gap: 8px; min-height: 70px; color: #547b8d; font-size: 10px; }
.ws-empty.small { min-height: 42px; }
.ws-loading { position: fixed; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px; z-index: 8; background: rgba(3,11,20,.8); color: #7dd3fc; font-size: 11px; }
.ws-loader-ring { width: 34px; height: 34px; border: 2px solid rgba(56,189,248,.16); border-top-color: #38bdf8; border-radius: 50%; animation: ws-spin 1s linear infinite; }

.ws-cert-list, .ws-slow-list, .ws-alert-list { flex: 1; min-height: 0; padding: 0 11px 9px; }
.ws-cert-item { padding: 7px 0; border-bottom: 1px solid rgba(56,189,248,.06); }
.ws-cert-line { display: flex; justify-content: space-between; gap: 6px; align-items: center; }
.ws-cert-line b { overflow: hidden; color: #c9edf7; font-size: 10px; font-weight: 500; text-overflow: ellipsis; white-space: nowrap; }
.ws-cert-line span { font-family: "DIN Alternate", monospace; font-size: 9px; white-space: nowrap; }
.ws-cert-bar { height: 3px; margin-top: 5px; overflow: hidden; border-radius: 3px; background: rgba(56,189,248,.12); }
.ws-cert-bar i { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, #38bdf8, #67e8f9); }
.ws-cert-item:has(.cert-warning) .ws-cert-bar i { background: linear-gradient(90deg, #f59e0b, #fbbf24); }
.ws-cert-item:has(.cert-danger) .ws-cert-bar i, .ws-cert-item:has(.cert-expired) .ws-cert-bar i { background: linear-gradient(90deg, #f43f5e, #fb7185); }
.ws-slow-item { display: flex; align-items: center; gap: 7px; min-height: 31px; border-bottom: 1px solid rgba(56,189,248,.055); }
.ws-rank { width: 16px; color: #5c8ca0; font-family: "DIN Alternate", monospace; font-size: 10px; }
.ws-rank.top { color: #fbbf24; }
.ws-slow-main { flex: 1; min-width: 0; }
.ws-slow-main b { display: block; overflow: hidden; color: #c9edf7; font-size: 10px; font-weight: 500; text-overflow: ellipsis; white-space: nowrap; }
.ws-slow-bar { height: 3px; margin-top: 4px; border-radius: 3px; background: rgba(56,189,248,.1); }
.ws-slow-bar i { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, #0ea5e9, #67e8f9); box-shadow: 0 0 7px rgba(56,189,248,.4); }
.ws-slow-item > strong { color: #9fe8f5; font-family: "DIN Alternate", monospace; font-size: 10px; white-space: nowrap; }
.ws-alert-item { display: flex; align-items: center; gap: 7px; min-height: 32px; border-bottom: 1px solid rgba(56,189,248,.055); }
.ws-alert-mark { flex: 0 0 4px; width: 4px; height: 18px; border-radius: 2px; background: #fbbf24; }
.ws-alert-item.critical .ws-alert-mark { background: #fb7185; box-shadow: 0 0 8px #fb7185; }
.ws-alert-item > div { flex: 1; min-width: 0; }
.ws-alert-item b { display: block; overflow: hidden; color: #d9f6ff; font-size: 10px; font-weight: 500; text-overflow: ellipsis; white-space: nowrap; }
.ws-alert-item small { display: block; overflow: hidden; color: #79a8b9; font-size: 8px; text-overflow: ellipsis; white-space: nowrap; }
.ws-alert-item > span:last-child { color: #5f8b9f; font-size: 8px; white-space: nowrap; }

.ws-footer { display: flex; align-items: center; gap: 10px; flex: 0 0 25px; min-height: 25px; border-top: 1px solid rgba(56,189,248,.14); color: #5d8fa4; font-size: 8px; }
.ws-ticker-label { display: flex; align-items: center; gap: 5px; color: #7dd3fc; letter-spacing: 1px; white-space: nowrap; }
.ws-ticker-label i { width: 5px; height: 5px; border-radius: 50%; background: #38bdf8; box-shadow: 0 0 8px #38bdf8; animation: ws-pulse 1.5s infinite; }
.ws-ticker-window { flex: 1; overflow: hidden; white-space: nowrap; }
.ws-ticker-track { display: inline-block; white-space: nowrap; animation: ws-ticker 27s linear infinite; }
.ws-ticker-track span { padding-right: 60px; color: #7eafc0; }
.ws-footer-meta { white-space: nowrap; letter-spacing: .5px; }

@keyframes ws-pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: .4; transform: scale(.75); } }
@keyframes ws-scan { from { transform: translateY(-20px); } to { transform: translateY(18px); } }
@keyframes ws-aurora { from { transform: translate3d(-4%, 4%, 0) scale(.9); } to { transform: translate3d(7%, -5%, 0) scale(1.15); } }
@keyframes ws-spin { to { transform: rotate(360deg); } }
@keyframes ws-ticker { from { transform: translateX(0); } to { transform: translateX(-50%); } }
@keyframes ws-alert-row { 0%, 100% { box-shadow: inset 0 0 0 rgba(251,113,133,0); } 50% { box-shadow: inset 3px 0 0 rgba(251,113,133,.55); } }

@media (max-width: 1500px) {
  .ws-kpis { gap: 7px; }
  .ws-kpi { min-height: 70px; padding: 8px 9px; }
  .ws-kpi em { display: none; }
  .ws-content { grid-template-columns: minmax(205px, .85fr) minmax(420px, 1.9fr) minmax(205px, .9fr); }
}

@media (max-width: 1240px) {
  .ws-header { flex-wrap: wrap; flex-basis: auto; padding: 9px 14px; }
  .ws-header-center { order: 4; width: 100%; justify-content: center; }
  .ws-actions { margin-left: auto; }
  .ws-updated, .ws-countdown { display: none; }
  .ws-kpis { grid-template-columns: repeat(4, 1fr); }
  .ws-content { grid-template-columns: minmax(210px, .82fr) minmax(420px, 1.8fr); }
  .ws-side-right { grid-column: 1 / -1; flex-direction: row; height: 230px; }
  .ws-side-right .ws-panel { flex: 1; }
  .ws-page { overflow-y: auto; height: auto; min-height: 100vh; }
  .ws-main { min-height: 900px; }
}

@media (max-width: 760px) {
  .ws-brand { min-width: 0; }
  .ws-brand h1 { font-size: 15px; }
  .ws-kicker { font-size: 7px; }
  .ws-brand-mark { width: 34px; height: 34px; }
  .ws-actions :deep(.el-button) { padding: 5px 7px; font-size: 10px; }
  .ws-kpis { grid-template-columns: repeat(2, 1fr); }
  .ws-content { display: flex; flex-direction: column; }
  .ws-side, .ws-center { width: 100%; }
  .ws-side-right { flex-direction: column; height: auto; }
  .ws-panel { min-height: 210px; }
  .ws-table-head, .ws-site-row { grid-template-columns: minmax(130px, 1.6fr) 50px 60px 54px 58px 68px 65px; gap: 4px; }
  .ws-table-head { font-size: 8px; }
  .ws-site-main b { font-size: 10px; }
  .ws-spark { width: 64px; }
  .ws-footer-meta { display: none; }
  .ws-header-center { gap: 7px; }
  .ws-date { font-size: 8px; }
}
</style>
