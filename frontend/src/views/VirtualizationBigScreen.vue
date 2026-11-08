<template>
  <div ref="pageRef" class="bs3-page">
    <div class="bs3-bg"></div>
    <header class="bs3-header">
      <div class="bs3-brand">
        <div class="bs3-mark"><el-icon :size="23"><Cpu /></el-icon></div>
        <div>
          <span class="bs3-kicker">VIRTUALIZATION ORBIT · LIVE NOC</span>
          <h1>虚拟化资源 · 立体态势大屏</h1>
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
        <aside class="bs3-col virt-left">
          <article class="bs3-panel bs3-flex-panel">
            <header class="bs3-panel-head"><div><span class="bs3-eyebrow">01 / PLATFORMS</span><h2>虚拟化平台</h2></div><span class="bs3-badge">{{ platforms.length }} 个</span></header>
            <div class="bs3-panel-body">
              <BigScreenAutoScroll class="bs3-list-scroll" :speed="8">
              <div class="bs3-side-list">
                <div v-for="item in platforms.slice(0, 6)" :key="item.id" class="bs3-side-row">
                  <div class="bs3-side-main"><b>{{ item.name }}</b><small>{{ item.platform_type }} · {{ item.host_count || 0 }} 宿主 / {{ item.vm_count || 0 }} VM</small></div>
                  <span :class="item.last_sync_status === 'success' ? 'ok' : 'warn'" class="mono">{{ item.last_sync_status === 'success' ? '同步正常' : item.last_sync_status === 'failed' ? '同步失败' : '待同步' }}</span>
                </div>
                <div v-if="!platforms.length" class="bs3-empty">暂无虚拟化平台</div>
              </div>
              </BigScreenAutoScroll>
            </div>
          </article>

          <article class="bs3-panel bs3-flex-panel">
            <header class="bs3-panel-head"><div><span class="bs3-eyebrow">02 / CAPACITY</span><h2>资源容量</h2></div><span class="bs3-badge">{{ hosts.length }} 宿主</span></header>
            <div class="bs3-panel-body">
              <div class="bs3-capacity-row">
                <div><span>宿主机内存</span><b>{{ formatMemory(capacity.memoryUsed) }} / {{ formatMemory(capacity.memoryTotal) }}</b></div>
                <div class="bs3-capacity-bar"><i :style="{ width: `${capacity.memoryPercent}%` }"></i></div>
                <strong>{{ capacity.memoryPercent.toFixed(1) }}%</strong>
              </div>
              <div class="bs3-capacity-row">
                <div><span>存储容量</span><b>{{ formatCapacity(capacity.storageUsed) }} / {{ formatCapacity(capacity.storageTotal) }}</b></div>
                <div class="bs3-capacity-bar"><i :style="{ width: `${capacity.storagePercent}%` }"></i></div>
                <strong>{{ capacity.storagePercent.toFixed(1) }}%</strong>
              </div>
              <div class="bs3-facts">
                <span>网络入向<b>{{ bpsText(capacity.rx) }}</b></span>
                <span>网络出向<b>{{ bpsText(capacity.tx) }}</b></span>
                <span>宿主机离线<b class="bad">{{ offlineHosts }}</b></span>
              </div>
              <div class="bs3-facts">
                <span>vCPU 总量<b>{{ capacity.vcpu }}</b></span>
                <span>VM 分配内存<b>{{ formatMemory(capacity.vmMemory) }}</b></span>
                <span>VM 分配磁盘<b>{{ formatCapacity(capacity.vmDisk) }}</b></span>
              </div>
            </div>
          </article>

          <article class="bs3-panel bs3-flex-panel">
            <header class="bs3-panel-head"><div><span class="bs3-eyebrow">03 / VM STATE</span><h2>虚拟机状态</h2></div><span class="bs3-badge">{{ overview.total || vms.length }} VM</span></header>
            <div class="bs3-panel-body">
              <div class="bs3-dist">
                <div class="bs3-dist-row"><span class="bs3-dist-name">运行中</span><span class="bs3-dist-bar"><i :style="{ width: `${rate(overview.running, overview.total)}%` }"></i></span><span class="bs3-dist-value">{{ overview.running || 0 }}</span></div>
                <div class="bs3-dist-row"><span class="bs3-dist-name">已停止</span><span class="bs3-dist-bar"><i :style="{ width: `${rate(overview.stopped, overview.total)}%`, background: 'linear-gradient(90deg,#fb7185,#fda4af)' }"></i></span><span class="bs3-dist-value">{{ overview.stopped || 0 }}</span></div>
                <div class="bs3-dist-row"><span class="bs3-dist-name">暂停/未知</span><span class="bs3-dist-bar"><i :style="{ width: `${rate((overview.paused || 0) + (overview.unknown || 0), overview.total)}%`, background: 'linear-gradient(90deg,#f59e0b,#fbbf24)' }"></i></span><span class="bs3-dist-value">{{ (overview.paused || 0) + (overview.unknown || 0) }}</span></div>
              </div>
            </div>
          </article>
        </aside>

        <section class="bs3-col virt-center">
          <article class="bs3-panel bs3-3d-panel">
            <header class="bs3-panel-head"><div><span class="bs3-eyebrow">04 / RESOURCE ORBIT</span><h2>虚拟化资源轨道</h2></div><span class="bs3-badge">3D 实时</span></header>
            <div class="bs3-3d-wrap">
              <BigScreen3D mode="virtual" :items="threeItems" :alerts="alerts" />
              <div class="bs3-3d-stats">
                <span>运行中 VM<b>{{ overview.running || 0 }}</b></span>
                <span>宿主机<b>{{ overview.hosts || hosts.length }}</b></span>
                <span>平均 CPU<b>{{ avgCpu }}%</b></span>
              </div>
            </div>
          </article>
        </section>

        <aside class="bs3-col right virt-right">
          <article class="bs3-panel bs3-flex-panel">
            <header class="bs3-panel-head"><div><span class="bs3-eyebrow">05 / HOST PRESSURE</span><h2>宿主机负载 Top</h2></div><span class="bs3-badge">CPU</span></header>
            <div class="bs3-panel-body">
              <BigScreenAutoScroll class="bs3-list-scroll" :speed="8">
              <div class="bs3-side-list">
                <div v-for="(row, index) in hostRows" :key="row.id" class="bs3-side-row">
                  <span class="bs3-rank">{{ String(index + 1).padStart(2, '0') }}</span>
                  <div class="bs3-side-main"><b>{{ row.name }}</b><small>{{ row.vm_count || 0 }} VM · {{ row.cluster_name || '默认集群' }} · 内存 {{ pct(row.memory_usage) }} · 磁盘 {{ pct(row.storage_usage) }}</small></div>
                  <strong>{{ pct(row.cpu_usage) }}</strong>
                </div>
                <div v-if="!hostRows.length" class="bs3-empty">暂无宿主机指标</div>
              </div>
              </BigScreenAutoScroll>
            </div>
          </article>

          <article class="bs3-panel bs3-flex-panel">
            <header class="bs3-panel-head"><div><span class="bs3-eyebrow">06 / VM ALERTS</span><h2>虚拟化告警</h2></div><span class="bs3-badge rose">{{ alerts.length }} 条</span></header>
            <div class="bs3-panel-body">
              <BigScreenAutoScroll class="bs3-list-scroll" :speed="8">
              <div v-for="item in alerts.slice(0, 6)" :key="item.id" class="bs3-alert-row" :class="item.alert_level || 'warning'">
                <i></i><div><b>{{ item.vm_name || item.platform_name || item.name || '虚拟化平台告警' }}</b><small>{{ item.message || item.metric_name || '需要处理' }}</small></div>
              </div>
              <div v-if="!alerts.length" class="bs3-empty">当前没有虚拟化告警</div>
              </BigScreenAutoScroll>
            </div>
          </article>
        </aside>

        <article class="bs3-panel bs3-table-panel">
          <header class="bs3-panel-head"><div><span class="bs3-eyebrow">07 / VM DETAILS</span><h2>虚拟机实时明细</h2></div><span class="bs3-badge">{{ vmRows.length }} / {{ vms.length }} 台 · CPU 排序</span></header>
          <div class="bs3-panel-body bs3-table-body">
            <BigScreenAutoScroll class="bs3-table-scroll" :speed="14">
            <table class="bs3-table bs3-table-wide">
              <thead><tr><th style="width:15%">虚拟机</th><th>宿主机 / 集群</th><th>状态</th><th>vCPU</th><th>内存</th><th>磁盘</th><th>CPU</th><th>内存%</th><th>磁盘%</th><th>IP 地址</th></tr></thead>
              <tbody>
                <tr v-for="row in vmRows" :key="row.id">
                  <td class="name">{{ row.name }}</td>
                  <td>{{ row.host_name || '—' }}<small class="bs3-cell-sub">{{ row.cluster_name || '默认集群' }}</small></td>
                  <td :class="row.power_state === 'running' ? 'ok' : row.power_state === 'stopped' ? 'bad' : 'warn'">{{ stateLabel(row.power_state) }}</td>
                  <td class="mono">{{ row.vcpu || '—' }}</td>
                  <td class="mono">{{ formatMemory(row.memory_mb) }}</td>
                  <td class="mono">{{ formatCapacity(row.disk_total_gb) }}</td>
                  <td class="mono">{{ pct(row.cpu_usage) }}</td>
                  <td class="mono">{{ pct(row.memory_usage) }}</td>
                  <td class="mono">{{ pct(row.disk_usage) }}</td>
                  <td class="mono">{{ row.primary_ip || (row.ip_addresses || []).join(', ') || '—' }}</td>
                </tr>
                <tr v-if="!vmRows.length"><td colspan="10"><div class="bs3-empty">暂无虚拟机数据</div></td></tr>
              </tbody>
            </table>
            </BigScreenAutoScroll>
          </div>
        </article>
      </section>

      <footer class="bs3-footer">
        <span>LIVE FEED</span>
        <div class="bs3-ticker"><div class="bs3-ticker-track"><span>{{ tickerText }}</span><span>{{ tickerText }}</span></div></div>
        <span>虚拟化资源 · 3D ADAPTIVE</span>
      </footer>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Back, Cpu, FullScreen, Refresh, Timer, Warning } from '@element-plus/icons-vue'
import { virtualizationApi } from '@/api'
import BigScreen3D from '@/components/BigScreen3D.vue'
import BigScreenAutoScroll from '@/components/BigScreenAutoScroll.vue'
import '@/styles/bigscreen-3d-pages.css'

const pageRef = ref(null)
const overview = ref({})
const platforms = ref([])
const hosts = ref([])
const vms = ref([])
const alerts = ref([])
const now = ref(new Date())
const lastUpdated = ref(null)
const isFullscreen = ref(false)
let timer = null
let refresh = null

const pad = (v) => String(v).padStart(2, '0')
const dateText = computed(() => `${now.value.getFullYear()}-${pad(now.value.getMonth() + 1)}-${pad(now.value.getDate())}`)
const clockText = computed(() => `${pad(now.value.getHours())}:${pad(now.value.getMinutes())}:${pad(now.value.getSeconds())}`)
const lastUpdatedText = computed(() => lastUpdated.value ? lastUpdated.value.toLocaleTimeString('zh-CN', { hour12: false }) : '--:--:--')
const point = (value) => value === null || value === undefined ? NaN : Number(value)
const pct = (value) => Number.isFinite(point(value)) ? `${point(value).toFixed(1)}%` : '—'
const rate = (value, total) => Math.max(0, Math.min(100, Number(value || 0) / Math.max(1, Number(total || 0)) * 100))
const stateLabel = (value) => ({ running: '运行中', stopped: '已停止', paused: '暂停', unknown: '未知' }[value] || value || '未知')
const formatMemory = (value) => {
  const number = Number(value || 0)
  if (!number) return '0 GB'
  return number >= 1024 * 1024 ? `${(number / 1024 / 1024).toFixed(1)} TB` : `${(number / 1024).toFixed(number >= 10240 ? 0 : 1)} GB`
}
const formatCapacity = (value) => {
  const number = Number(value || 0)
  if (!number) return '—'
  return number >= 1024 ? `${(number / 1024).toFixed(1)} TB` : `${number.toFixed(1)} GB`
}
const bpsText = (value) => {
  const number = Number(value || 0)
  if (!number) return '0 bps'
  if (number >= 1_000_000_000) return `${(number / 1_000_000_000).toFixed(2)} Gbps`
  if (number >= 1_000_000) return `${(number / 1_000_000).toFixed(2)} Mbps`
  if (number >= 1_000) return `${(number / 1_000).toFixed(1)} Kbps`
  return `${number.toFixed(0)} bps`
}

const threeItems = computed(() => hosts.value.slice(0, 24).map((host) => ({
  name: host.name, value: point(host.cpu_usage) || 0, online: host.status !== 'offline',
  vms: host.vm_count || 0, color: host.status === 'offline' ? '#fb7185' : (point(host.cpu_usage) > 80 ? '#fbbf24' : '#a78bfa'),
})))
const avgCpu = computed(() => {
  const values = hosts.value.map((host) => point(host.cpu_usage)).filter(Number.isFinite)
  return values.length ? (values.reduce((a, b) => a + b, 0) / values.length).toFixed(1) : '0'
})
const avgMemory = computed(() => {
  const values = hosts.value.map((host) => point(host.memory_usage)).filter(Number.isFinite)
  return values.length ? (values.reduce((a, b) => a + b, 0) / values.length).toFixed(1) : '0'
})
const avgStorage = computed(() => {
  const values = hosts.value.map((host) => point(host.storage_usage)).filter(Number.isFinite)
  return values.length ? (values.reduce((a, b) => a + b, 0) / values.length).toFixed(1) : '0'
})
const offlineHosts = computed(() => hosts.value.filter((host) => host.status === 'offline').length)
const capacity = computed(() => {
  const memoryTotal = hosts.value.reduce((sum, host) => sum + Number(host.memory_total_mb || 0), 0)
  const memoryUsed = hosts.value.reduce((sum, host) => sum + Number(host.memory_used_mb || 0), 0)
  const storageTotal = hosts.value.reduce((sum, host) => sum + Number(host.storage_total_gb || 0), 0)
  const storageUsed = hosts.value.reduce((sum, host) => sum + Number(host.storage_used_gb || 0), 0)
  return {
    memoryTotal, memoryUsed,
    memoryPercent: memoryTotal ? memoryUsed / memoryTotal * 100 : 0,
    storageTotal, storageUsed,
    storagePercent: storageTotal ? storageUsed / storageTotal * 100 : 0,
    rx: hosts.value.reduce((sum, host) => sum + Number(host.net_rx_bps || 0), 0),
    tx: hosts.value.reduce((sum, host) => sum + Number(host.net_tx_bps || 0), 0),
    vcpu: vms.value.reduce((sum, vm) => sum + Number(vm.vcpu || 0), 0),
    vmMemory: vms.value.reduce((sum, vm) => sum + Number(vm.memory_mb || 0), 0),
    vmDisk: vms.value.reduce((sum, vm) => sum + Number(vm.disk_total_gb || 0), 0),
  }
})
const hostRows = computed(() => [...hosts.value].sort((a, b) => (point(b.cpu_usage) || 0) - (point(a.cpu_usage) || 0)).slice(0, 7))
const vmRows = computed(() => [...vms.value].sort((a, b) => (point(b.cpu_usage) || 0) - (point(a.cpu_usage) || 0)).slice(0, 12))
const kpis = computed(() => [
  { key: 'vm', label: '虚拟机总数', value: overview.value.total || vms.value.length, unit: '台', note: '已纳管', tone: 'cyan', icon: Cpu },
  { key: 'running', label: '运行中', value: overview.value.running || 0, unit: '台', note: '运行状态', tone: 'mint', icon: Timer },
  { key: 'stopped', label: '已停止', value: overview.value.stopped || 0, unit: '台', note: '需要确认', tone: 'rose', icon: Warning },
  { key: 'hosts', label: '宿主机', value: overview.value.hosts || hosts.value.length, unit: '台', note: `${offlineHosts.value} 台离线`, tone: 'violet', icon: Cpu },
  { key: 'platforms', label: '虚拟化平台', value: overview.value.platforms || platforms.value.length, unit: '个', note: '多平台纳管', tone: 'cyan', icon: Cpu },
  { key: 'cpu', label: '平均 CPU', value: `${avgCpu.value}%`, unit: '', note: '宿主机', tone: 'amber', icon: Timer },
  { key: 'memory', label: '平均内存', value: `${avgMemory.value}%`, unit: '', note: '宿主机', tone: 'mint', icon: Timer },
  { key: 'alerts', label: '活动告警', value: overview.value.vm_alerts_unack || alerts.value.length, unit: '条', note: '未处理', tone: 'rose', icon: Warning },
])
const tickerText = computed(() => {
  if (!vms.value.length && !hosts.value.length) return '虚拟化数据接入中，等待平台同步...'
  return [`平台 ${platforms.value.length} 个`, `宿主机 ${overview.value.hosts || hosts.value.length}`, `虚拟机 ${overview.value.total || vms.value.length}`, `运行 ${overview.value.running || 0}`, `停止 ${overview.value.stopped || 0}`, `存储 ${capacity.value.storagePercent.toFixed(1)}%`, `告警 ${alerts.value.length}`].join('　◆　')
})

async function loadData() {
  const [overviewRes, platformRes, hostRes, vmRes, alertRes] = await Promise.allSettled([
    virtualizationApi.overview(),
    virtualizationApi.platforms(),
    fetchAllPaged((page) => virtualizationApi.hosts({ page, page_size: 200 })),
    fetchAllPaged((page) => virtualizationApi.vms({ page, page_size: 200 })),
    virtualizationApi.vmAlerts({ status: 'active', page: 1, size: 50 }),
  ])
  if (overviewRes.status === 'fulfilled') overview.value = overviewRes.value?.data || {}
  if (platformRes.status === 'fulfilled') platforms.value = platformRes.value?.data?.items || []
  if (hostRes.status === 'fulfilled') hosts.value = hostRes.value || []
  if (vmRes.status === 'fulfilled') vms.value = vmRes.value || []
  if (alertRes.status === 'fulfilled') alerts.value = alertRes.value?.data?.items || []
  lastUpdated.value = new Date()
}

async function fetchAllPaged(loader) {
  const items = []
  let page = 1
  while (page <= 50) {
    const res = await loader(page)
    const batch = res.data?.items || []
    items.push(...batch)
    const total = Number(res.data?.total || 0)
    if (!batch.length || (total > 0 && items.length >= total)) break
    page += 1
  }
  return items
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
  document.addEventListener('fullscreenchange', onFullscreen)
})
onBeforeUnmount(() => {
  clearInterval(timer)
  clearInterval(refresh)
  document.removeEventListener('fullscreenchange', onFullscreen)
})
</script>
