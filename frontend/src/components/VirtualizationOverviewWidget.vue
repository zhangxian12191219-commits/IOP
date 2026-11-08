<template>
  <div class="vz-stage">
    <div v-if="editable" class="vz-editbar">
      <span>拖拽标题移动 · 右下角缩放</span>
      <el-dropdown trigger="click" @command="openAddPanel">
        <el-button size="small" type="primary" plain>＋ 添加面板</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item v-for="item in panelTypeOptions" :key="item.value" :command="item.value">{{ item.label }}</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-button size="small" @click="resetPanels">重置布局</el-button>
    </div>

    <div ref="boardRef" class="vz-board">
      <article
        v-for="panel in localPanels"
        :key="panel.id"
        class="vz-panel"
        :class="[`vz-panel--${panel.type}`, { 'is-editing': editable }]"
        :style="panelStyle(panel)"
      >
        <header class="vz-panel-head" @pointerdown="startDrag($event, panel)">
          <div class="vz-panel-heading">
            <span>{{ panelKicker(panel) }}</span>
            <b>{{ panel.title }}</b>
          </div>
          <div v-if="editable" class="vz-panel-tools" @pointerdown.stop>
            <button type="button" title="设置" @click="openConfig(panel)">⚙</button>
            <button type="button" title="删除" @click="removePanel(panel)">×</button>
          </div>
        </header>

        <div class="vz-panel-body">
          <div class="vz-panel-content" :style="panelContentStyle(panel)">
          <template v-if="panel.type === 'scene3d'">
            <VirtualizationScene3D :platforms="platforms" :hosts="hosts" :vms="vms" :summary="summary" />
          </template>

          <template v-else-if="panel.type === 'kpi'">
            <div class="vz-kpi-live" :class="kpiData(panel).tone">
              <div class="vz-kpi-chart">
                <VzMetricChart :value="kpiChartValue(panel)" :tone="kpiData(panel).tone" :seed="panel.metric?.length || 1" />
              </div>
              <strong class="vz-kpi-value">{{ kpiData(panel).value }}</strong>
              <small class="vz-kpi-hint">{{ kpiData(panel).hint }}</small>
              <i class="vz-kpi-scan"></i>
            </div>
          </template>

          <template v-else-if="panel.type === 'gauge'">
            <div class="vz-gauge-live">
              <div class="vz-gauge-ring" :style="{ '--pct': `${gaugeData(panel).percent}%`, '--ring-color': gaugeData(panel).color }">
                <div class="vz-gauge-inner">
                  <strong>{{ gaugeData(panel).percent.toFixed(1) }}<small>%</small></strong>
                  <span>{{ gaugeData(panel).short }}</span>
                </div>
              </div>
              <small>{{ gaugeData(panel).foot }}</small>
            </div>
          </template>

          <template v-else-if="panel.type === 'platform'">
            <div v-if="platformRows.length" class="vz-dynamic-list">
              <div v-for="platform in platformRows" :key="platform.id" class="vz-platform-live">
                <div class="vz-platform-top">
                  <b>{{ platform.name }}</b>
                  <small>{{ platform.hostCount }}H / {{ platform.vmCount }}V</small>
                </div>
                <div v-for="bar in platform.bars" :key="bar.key" class="vz-bar-row">
                  <span>{{ bar.label }}</span>
                  <i><em :style="{ width: `${bar.percent}%`, background: bar.color }"></em></i>
                  <b>{{ bar.percent.toFixed(0) }}%</b>
                </div>
              </div>
            </div>
            <div v-else class="vz-no-data">暂未纳管虚拟化平台</div>
          </template>

          <template v-else-if="panel.type === 'host'">
            <div v-if="hostRows.length" class="vz-dynamic-list">
              <div v-for="host in hostRows" :key="host.id" class="vz-host-live">
                <div class="vz-host-title"><b>{{ host.name }}</b><small>{{ host.ip }}</small></div>
                <div class="vz-host-bars">
                  <div v-for="bar in host.bars" :key="bar.key" class="vz-bar-row">
                    <span>{{ bar.label }}</span>
                    <i><em :style="{ width: `${bar.percent}%`, background: bar.color }"></em></i>
                    <b>{{ bar.percent.toFixed(0) }}%</b>
                  </div>
                </div>
              </div>
            </div>
            <div v-else class="vz-no-data">暂无宿主机数据</div>
          </template>

          <template v-else-if="panel.type === 'vm'">
            <div v-if="vmRows.length" class="vz-dynamic-list">
              <div v-for="(vm, index) in vmRows" :key="vm.id" class="vz-vm-live">
                <span class="vz-vm-rank">{{ String(index + 1).padStart(2, '0') }}</span>
                <div class="vz-vm-info">
                  <b>{{ vm.name }}</b>
                  <div class="vz-vm-triple">
                    <i :style="{ width: `${vm.cpu}%`, background: '#38bdf8' }"></i>
                    <i :style="{ width: `${vm.memory}%`, background: '#a78bfa' }"></i>
                    <i :style="{ width: `${vm.disk}%`, background: '#fbbf24' }"></i>
                  </div>
                </div>
                <div class="vz-vm-value"><b>{{ vm.cpu.toFixed(0) }}%</b><small>{{ vm.memory.toFixed(0) }}% / {{ vm.disk.toFixed(0) }}%</small></div>
              </div>
            </div>
            <div v-else class="vz-no-data">暂无虚拟机数据</div>
          </template>

          <template v-else-if="panel.type === 'alerts'">
            <div v-if="alertRows.length" class="vz-dynamic-list">
              <div v-for="alert in alertRows" :key="alert.id" class="vz-alert-live" :class="alert.level">
                <span class="vz-alert-dot"></span>
                <div><b>{{ alert.vm_name || alert.platform_name || '虚拟化平台' }}</b><small>{{ alert.message || alert.alert_type_text }}</small></div>
                <time>{{ alert.time }}</time>
              </div>
            </div>
            <div v-else class="vz-no-data">当前没有虚拟机告警</div>
          </template>
          </div>
        </div>

        <span v-if="editable" class="vz-resize-handle" @pointerdown.stop.prevent="startResize($event, panel)"></span>
      </article>
    </div>

    <el-dialog v-model="configVisible" :title="editingNew ? '添加指标面板' : '面板设置'" width="430px" append-to-body>
      <el-form label-width="78px">
        <el-form-item label="面板类型">
          <el-select v-model="draft.type" style="width: 100%" :disabled="!editingNew" @change="onDraftTypeChange">
            <el-option v-for="item in panelTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="标题">
          <el-input v-model="draft.title" maxlength="24" placeholder="面板标题" />
        </el-form-item>
        <el-form-item v-if="draft.type === 'kpi'" label="指标">
          <el-select v-model="draft.metric" style="width: 100%">
            <el-option v-for="item in kpiMetricOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="draft.type === 'gauge'" label="指标">
          <el-select v-model="draft.metric" style="width: 100%">
            <el-option v-for="item in gaugeMetricOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="字号">
          <el-select v-model="draft.fontSize" style="width: 100%">
            <el-option label="自动适配" :value="0" />
            <el-option v-for="size in [10, 11, 12, 13, 14, 16, 18, 20, 22, 24]" :key="size" :label="`${size} px`" :value="size" />
          </el-select>
          <div class="vz-config-tip">会按面板实际大小自动收敛，避免溢出</div>
        </el-form-item>
        <el-form-item label="布局">
          <span class="vz-config-tip">添加后可拖拽标题移动，拖拽右下角调整大小</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="configVisible = false">取消</el-button>
        <el-button type="primary" @click="saveConfig">应用</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import VirtualizationScene3D from '@/components/VirtualizationScene3D.vue'
import VzMetricChart from '@/components/VirtualizationMetricChart.vue'

const props = defineProps({
  data: { type: Object, default: () => ({}) },
  panels: { type: Array, default: () => [] },
  editable: { type: Boolean, default: false },
})
const emit = defineEmits(['update:panels'])

const COLS = 12
const ROWS = 10
const boardRef = ref(null)
const configVisible = ref(false)
const editingNew = ref(false)
const editingId = ref('')
const draft = reactive({ type: 'kpi', title: '新指标', metric: 'total', fontSize: 0 })
let drag = null

const panelTypeOptions = [
  { value: 'kpi', label: '指标数值卡' },
  { value: 'gauge', label: '资源仪表盘' },
  { value: 'platform', label: '平台资源列表' },
  { value: 'host', label: '宿主机 TOP' },
  { value: 'vm', label: '虚拟机 TOP' },
  { value: 'alerts', label: '告警动态' },
  { value: 'scene3d', label: '3D 态势场景' },
]
const kpiMetricOptions = [
  { value: 'total', label: '虚拟机总数' },
  { value: 'running', label: '运行中虚拟机' },
  { value: 'hosts', label: '宿主机数量' },
  { value: 'platforms', label: '平台数量' },
  { value: 'stopped', label: '已关机虚拟机' },
  { value: 'vcpu', label: 'vCPU 分配' },
  { value: 'memoryAllocated', label: '内存分配' },
  { value: 'storageAllocated', label: '磁盘分配' },
  { value: 'alerts', label: '未恢复告警' },
]
const gaugeMetricOptions = [
  { value: 'cpu', label: 'CPU 平均负载' },
  { value: 'memory', label: '内存平均负载' },
  { value: 'disk', label: '存储平均负载' },
]

const defaultPanels = () => [
  { id: 'vz-kpi-vms', type: 'kpi', metric: 'total', title: '虚拟机总数', x: 0, y: 0, w: 3, h: 2 },
  { id: 'vz-kpi-hosts', type: 'kpi', metric: 'hosts', title: '宿主机', x: 0, y: 2, w: 3, h: 2 },
  { id: 'vz-gauge-cpu', type: 'gauge', metric: 'cpu', title: 'CPU 负载', x: 0, y: 4, w: 3, h: 2 },
  { id: 'vz-gauge-memory', type: 'gauge', metric: 'memory', title: '内存负载', x: 0, y: 6, w: 3, h: 2 },
  { id: 'vz-scene', type: 'scene3d', metric: '', title: '资源态势', x: 3, y: 0, w: 6, h: 10 },
  { id: 'vz-platform', type: 'platform', metric: '', title: '平台资源', x: 9, y: 0, w: 3, h: 3 },
  { id: 'vz-host', type: 'host', metric: '', title: '宿主机 TOP', x: 9, y: 3, w: 3, h: 3 },
  { id: 'vz-vm', type: 'vm', metric: '', title: '虚拟机 TOP', x: 9, y: 6, w: 3, h: 2 },
  { id: 'vz-alerts', type: 'alerts', metric: '', title: '告警动态', x: 9, y: 8, w: 3, h: 2 },
]
const localPanels = ref(defaultPanels())

const overview = computed(() => props.data?.overview || {})
const platforms = computed(() => props.data?.platforms || [])
const hosts = computed(() => props.data?.hosts || [])
const vms = computed(() => props.data?.vms || [])
const alerts = computed(() => props.data?.alerts || [])
const summary = computed(() => ({
  cpu: avg(hosts.value, 'cpu_usage'),
  memory: avg(hosts.value, 'memory_usage'),
  disk: avg(hosts.value, 'storage_usage'),
  vcpu: vms.value.reduce((sum, vm) => sum + number(vm.vcpu), 0),
  memoryAllocated: vms.value.reduce((sum, vm) => sum + number(vm.memory_mb), 0),
  storageAllocated: vms.value.reduce((sum, vm) => sum + number(vm.disk_total_gb), 0),
}))

function number(value) {
  const n = Number(value)
  return Number.isFinite(n) ? n : 0
}

function avg(items, key) {
  const values = (items || []).map((item) => Number(item?.[key])).filter((value) => Number.isFinite(value))
  if (!values.length) return 0
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

function colorFor(value) {
  if (value >= 90) return '#fb7185'
  if (value >= 75) return '#fbbf24'
  return '#38bdf8'
}

function kpiData(panel) {
  const o = overview.value
  const map = {
    total: { label: '虚拟机总数', value: number(o.total) || vms.value.length, hint: `运行中 ${number(o.running)} 台`, tone: 'cyan' },
    running: { label: '运行中虚拟机', value: number(o.running), hint: `共 ${number(o.total) || vms.value.length} 台`, tone: 'emerald' },
    hosts: { label: '宿主机', value: number(o.hosts) || hosts.value.length, hint: `平台 ${number(o.platforms) || platforms.value.length} 个`, tone: 'blue' },
    platforms: { label: '虚拟化平台', value: number(o.platforms) || platforms.value.length, hint: '已纳管平台', tone: 'violet' },
    stopped: { label: '已关机', value: number(o.stopped), hint: 'Powered Off / Shutoff', tone: 'slate' },
    vcpu: { label: 'vCPU 分配', value: summary.value.vcpu, hint: '已分配虚拟核心', tone: 'violet' },
    memoryAllocated: { label: '内存分配', value: `${(summary.value.memoryAllocated / 1024).toFixed(0)} GB`, hint: '虚拟机内存总量', tone: 'emerald' },
    storageAllocated: { label: '磁盘分配', value: `${summary.value.storageAllocated.toFixed(0)} GB`, hint: '虚拟机磁盘总量', tone: 'amber' },
    alerts: { label: '未恢复告警', value: number(o.vm_alerts_active) || alerts.value.length, hint: `未确认 ${number(o.vm_alerts_unack)} 条`, tone: 'rose' },
  }
  return map[panel.metric] || map.total
}

function gaugeData(panel) {
  const value = summary.value[panel.metric] || 0
  const labels = { cpu: 'CPU', memory: 'MEM', disk: 'DISK' }
  const feet = {
    cpu: `${hosts.value.length} 台宿主机`,
    memory: `分配 ${(summary.value.memoryAllocated / 1024).toFixed(0)} GB`,
    disk: `分配 ${summary.value.storageAllocated.toFixed(0)} GB`,
  }
  return {
    percent: Math.max(0, Math.min(100, value)),
    short: labels[panel.metric] || 'LOAD',
    foot: feet[panel.metric] || '',
    color: colorFor(value),
  }
}

function kpiChartValue(panel) {
  const raw = String(kpiData(panel).value ?? '')
  const parsed = Number(raw.replace(/[^\d.]/g, ''))
  return Number.isFinite(parsed) ? Math.max(8, Math.min(100, parsed)) : 24
}

function autoPanelFont(panel) {
  const byHeight = 9 + Math.min(panel.h, 6) * 2
  const byWidth = 9 + Math.min(panel.w, 6) * 2
  return Math.max(10, Math.min(20, Math.min(byHeight, byWidth)))
}

function panelContentStyle(panel) {
  if (panel.type === 'scene3d') return {}
  const requested = Number(panel.fontSize) || 0
  const maxByPanel = Math.min(24, 10 + panel.h * 4, 10 + panel.w * 4)
  const size = Math.max(9, Math.min(requested > 0 ? requested : autoPanelFont(panel), maxByPanel))
  const scale = size / 12
  return {
    zoom: scale,
    width: `${100 / scale}%`,
    height: `${100 / scale}%`,
  }
}

const hostRows = computed(() => [...hosts.value]
  .map((host) => ({
    id: host.id,
    name: host.name,
    ip: host.ip_address || host.name,
    bars: [
      { key: 'cpu', label: 'CPU', percent: number(host.cpu_usage), color: colorFor(number(host.cpu_usage)) },
      { key: 'mem', label: 'MEM', percent: number(host.memory_usage), color: colorFor(number(host.memory_usage)) },
      { key: 'disk', label: 'DISK', percent: number(host.storage_usage), color: colorFor(number(host.storage_usage)) },
    ],
    load: Math.max(number(host.cpu_usage), number(host.memory_usage), number(host.storage_usage)),
  }))
  .sort((a, b) => b.load - a.load)
  .slice(0, 5))

const platformRows = computed(() => platforms.value.map((platform) => {
  const platformHosts = hosts.value.filter((host) => host.platform_id === platform.id)
  const platformVms = vms.value.filter((vm) => vm.platform_id === platform.id)
  return {
    id: platform.id,
    name: platform.name,
    hostCount: number(platform.host_count) || platformHosts.length,
    vmCount: number(platform.vm_count) || platformVms.length,
    bars: [
      { key: 'cpu', label: 'CPU', percent: avg(platformHosts, 'cpu_usage'), color: '#38bdf8' },
      { key: 'mem', label: 'MEM', percent: avg(platformHosts, 'memory_usage'), color: '#a78bfa' },
      { key: 'disk', label: 'DISK', percent: avg(platformHosts, 'storage_usage'), color: '#fbbf24' },
    ],
  }
}).slice(0, 4))

const vmRows = computed(() => [...vms.value]
  .sort((a, b) => number(b.cpu_usage) - number(a.cpu_usage))
  .slice(0, 5)
  .map((vm) => ({
    id: vm.id,
    name: vm.name,
    cpu: number(vm.cpu_usage),
    memory: number(vm.memory_usage),
    disk: number(vm.disk_usage),
  })))

const alertRows = computed(() => alerts.value.slice(0, 5).map((alert) => ({
  id: alert.id,
  vm_name: alert.vm_name || '虚拟机',
  alert_type_text: alert.alert_type_text || '资源告警',
  message: alert.message || '',
  level: alert.alert_level === 'critical' ? 'critical' : 'warning',
  time: alert.created_at ? new Date(alert.created_at).toLocaleTimeString('zh-CN', { hour12: false }).slice(0, 5) : '--:--',
})))

function clonePanels(list) {
  return (list && list.length ? list : defaultPanels()).map((item) => ({ ...item }))
}

watch(() => props.panels, (value) => {
  if (value?.length) {
    const next = clonePanels(value)
    if (JSON.stringify(next) !== JSON.stringify(localPanels.value)) localPanels.value = next
  }
}, { deep: true })

function panelStyle(panel) {
  return {
    left: `calc(${(panel.x / COLS) * 100}% + 3px)`,
    top: `calc(${(panel.y / ROWS) * 100}% + 3px)`,
    width: `calc(${(panel.w / COLS) * 100}% - 6px)`,
    height: `calc(${(panel.h / ROWS) * 100}% - 6px)`,
  }
}

function panelKicker(panel) {
  const map = {
    kpi: 'LIVE METRIC',
    gauge: 'RESOURCE LOAD',
    platform: 'PLATFORM',
    host: 'HOST RANK',
    vm: 'VM RANK',
    alerts: 'VM ALERT',
    scene3d: '3D SITUATION',
  }
  return map[panel.type] || 'PANEL'
}

function syncPanels() {
  emit('update:panels', localPanels.value.map((item) => ({ ...item })))
}

function findSlot(w, h) {
  for (let y = 0; y <= ROWS - h; y += 1) {
    for (let x = 0; x <= COLS - w; x += 1) {
      const overlaps = localPanels.value.some((panel) => (
        x < panel.x + panel.w && x + w > panel.x && y < panel.y + panel.h && y + h > panel.y
      ))
      if (!overlaps) return { x, y }
    }
  }
  return null
}

function openAddPanel(type) {
  editingNew.value = true
  editingId.value = ''
  const title = panelTypeOptions.find((item) => item.value === type)?.label || '新指标'
  Object.assign(draft, {
    type,
    title,
    metric: type === 'gauge' ? 'cpu' : type === 'kpi' ? 'total' : '',
    fontSize: 0,
  })
  configVisible.value = true
}

function openConfig(panel) {
  editingNew.value = false
  editingId.value = panel.id
  Object.assign(draft, {
    type: panel.type,
    title: panel.title,
    metric: panel.metric || (panel.type === 'gauge' ? 'cpu' : 'total'),
    fontSize: Number(panel.fontSize) || 0,
  })
  configVisible.value = true
}

function onDraftTypeChange() {
  draft.metric = draft.type === 'gauge' ? 'cpu' : draft.type === 'kpi' ? 'total' : ''
}

function saveConfig() {
  if (!draft.title.trim()) {
    ElMessage.warning('请填写面板标题')
    return
  }
  if (editingNew.value) {
    const isScene = draft.type === 'scene3d'
    const w = isScene ? 6 : 3
    const h = isScene ? 6 : 2
    const slot = findSlot(w, h)
    if (!slot) {
      ElMessage.warning('当前布局已满，请先移动或删除一个面板后再添加')
      return
    }
    localPanels.value = [...localPanels.value, {
      id: `vz-${Date.now()}`,
      type: draft.type,
      title: draft.title.trim(),
      metric: draft.metric,
      fontSize: Number(draft.fontSize) || 0,
      x: slot.x,
      y: slot.y,
      w,
      h,
    }]
  } else {
    localPanels.value = localPanels.value.map((panel) => (
      panel.id === editingId.value
        ? { ...panel, title: draft.title.trim(), metric: draft.metric, fontSize: Number(draft.fontSize) || 0 }
        : panel
    ))
  }
  configVisible.value = false
  syncPanels()
}

function removePanel(panel) {
  localPanels.value = localPanels.value.filter((item) => item.id !== panel.id)
  syncPanels()
}

function resetPanels() {
  localPanels.value = defaultPanels()
  syncPanels()
}

function beginPointer(event, panel, mode) {
  if (!props.editable || event.button !== 0 || !boardRef.value) return
  const rect = boardRef.value.getBoundingClientRect()
  const col = rect.width / COLS
  const row = rect.height / ROWS
  drag = {
    mode,
    panel,
    col,
    row,
    startX: event.clientX,
    startY: event.clientY,
    original: { x: panel.x, y: panel.y, w: panel.w, h: panel.h },
  }
  document.body.style.userSelect = 'none'
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', endPointer, { once: true })
}

function startDrag(event, panel) {
  beginPointer(event, panel, 'move')
}

function startResize(event, panel) {
  beginPointer(event, panel, 'resize')
}

function onPointerMove(event) {
  if (!drag) return
  const { panel, col, row, original } = drag
  const dx = (event.clientX - drag.startX) / col
  const dy = (event.clientY - drag.startY) / row
  if (drag.mode === 'move') {
    panel.x = Math.max(0, Math.min(COLS - panel.w, Math.round(original.x + dx)))
    panel.y = Math.max(0, Math.min(ROWS - panel.h, Math.round(original.y + dy)))
  } else {
    panel.w = Math.max(2, Math.min(COLS - panel.x, Math.round(original.w + dx)))
    panel.h = Math.max(1, Math.min(ROWS - panel.y, Math.round(original.h + dy)))
  }
}

function endPointer() {
  window.removeEventListener('pointermove', onPointerMove)
  document.body.style.userSelect = ''
  drag = null
  syncPanels()
}
</script>

<style scoped>
.vz-stage {
  position: relative;
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  color: #dbeafe;
  container-type: size;
}

.vz-board {
  position: relative;
  flex: 1;
  width: 100%;
  height: auto;
  min-height: 0;
  overflow: hidden;
}

.vz-editbar {
  position: static;
  z-index: 8;
  display: flex;
  align-items: center;
  align-self: flex-end;
  flex-shrink: 0;
  gap: 7px;
  margin: 0 6px 4px;
  padding: 3px 5px;
  border: 1px solid rgba(56, 189, 248, 0.22);
  border-radius: 6px;
  background: rgba(3, 16, 30, 0.92);
}

.vz-editbar > span { color: #64748b; font-size: 9px; }

.vz-panel {
  position: absolute;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  border: 1px solid rgba(56, 189, 248, 0.2);
  border-radius: 8px;
  background: linear-gradient(150deg, rgba(6, 25, 44, 0.9), rgba(3, 12, 24, 0.76));
  box-shadow: inset 0 0 26px rgba(14, 165, 233, 0.045);
  transition: border-color 0.2s, box-shadow 0.2s;
  animation: vz-panel-in 0.45s ease both;
}

.vz-panel::after {
  position: absolute;
  top: 0;
  left: -35%;
  width: 35%;
  height: 1px;
  background: linear-gradient(90deg, transparent, #38bdf8, transparent);
  content: '';
  animation: vz-panel-scan 5.5s linear infinite;
  pointer-events: none;
}

.vz-panel.is-editing {
  border-color: rgba(56, 189, 248, 0.4);
  box-shadow: 0 0 0 1px rgba(56, 189, 248, 0.08), inset 0 0 25px rgba(14, 165, 233, 0.06);
}

.vz-panel.is-editing .vz-panel-head { cursor: move; }

.vz-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-shrink: 0;
  padding: calc(3px * var(--vz-card-scale, 1)) calc(7px * var(--vz-card-scale, 1));
  border-bottom: 1px solid rgba(56, 189, 248, 0.1);
  touch-action: none;
}

.vz-panel-heading { min-width: 0; }
.vz-panel-heading span { display: block; overflow: hidden; color: #38bdf8; font-family: Consolas, monospace; font-size: 7px; letter-spacing: 1.2px; text-overflow: ellipsis; white-space: nowrap; }
.vz-panel-heading b { display: block; overflow: hidden; margin-top: 1px; color: #e0f2fe; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }

.vz-panel-tools { display: flex; gap: 1px; flex-shrink: 0; }
.vz-panel-tools button { width: 18px; height: 18px; padding: 0; border: 1px solid rgba(56, 189, 248, 0.18); border-radius: 3px; color: #7dd3fc; background: rgba(14, 165, 233, 0.08); font-size: 11px; line-height: 1; cursor: pointer; }
.vz-panel-tools button:hover { background: rgba(14, 165, 233, 0.2); }

.vz-panel-body { flex: 1; min-height: 0; padding: calc(4px * var(--vz-card-scale, 1)) calc(7px * var(--vz-card-scale, 1)); overflow: hidden; }
.vz-panel-content { width: 100%; height: 100%; min-height: 0; overflow: hidden; }
.vz-panel--scene3d .vz-panel-body { padding: 3px; }
.vz-panel--scene3d .vz-panel-head { border-bottom: 0; padding-bottom: 1px; }

.vz-resize-handle {
  position: absolute;
  right: 1px;
  bottom: 1px;
  z-index: 9;
  width: 12px;
  height: 12px;
  border-right: 2px solid #38bdf8;
  border-bottom: 2px solid #38bdf8;
  cursor: nwse-resize;
  opacity: 0.8;
  touch-action: none;
}

.vz-kpi-live { position: relative; display: flex; flex-direction: column; justify-content: center; height: 100%; min-height: 0; overflow: hidden; }
.vz-kpi-chart { position: absolute; right: 0; bottom: 0; left: 0; height: 62%; opacity: 0.58; pointer-events: none; }
.vz-kpi-value { position: relative; z-index: 1; margin: 0 0 2px; color: #f0f9ff; font-family: Bahnschrift, Consolas, sans-serif; font-size: clamp(15px, 4.5cqh, 24px); line-height: 1; text-shadow: 0 0 16px rgba(56, 189, 248, 0.38); }
.vz-kpi-hint { position: relative; z-index: 1; overflow: hidden; color: #64748b; font-size: 8px; text-overflow: ellipsis; white-space: nowrap; }
.vz-kpi-live.violet .vz-kpi-value { color: #c4b5fd; }
.vz-kpi-live.emerald .vz-kpi-value { color: #6ee7b7; }
.vz-kpi-live.rose .vz-kpi-value { color: #fda4af; }
.vz-kpi-live.amber .vz-kpi-value { color: #fbbf24; }
.vz-kpi-scan { position: absolute; right: -20px; bottom: -26px; width: 62px; height: 62px; border: 1px solid rgba(56, 189, 248, 0.2); border-radius: 50%; animation: vz-pulse 3.2s ease-in-out infinite; }

.vz-gauge-live { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 3px; height: 100%; min-height: 0; overflow: hidden; }
.vz-gauge-ring { display: grid; place-items: center; width: min(22cqh, calc(64px * var(--vz-card-scale, 1))); height: min(22cqh, calc(64px * var(--vz-card-scale, 1))); border-radius: 50%; background: conic-gradient(var(--ring-color) var(--pct), rgba(56, 189, 248, 0.1) 0); box-shadow: 0 0 20px rgba(56, 189, 248, 0.14); animation: vz-ring-breathe 3.5s ease-in-out infinite; }
.vz-gauge-inner { display: flex; flex-direction: column; align-items: center; justify-content: center; width: 77%; height: 77%; border-radius: 50%; background: #061629; }
.vz-gauge-inner strong { color: #f0f9ff; font-family: Consolas, monospace; font-size: clamp(12px, 3.8cqh, 18px); line-height: 1; }
.vz-gauge-inner strong small { font-size: 7px; }
.vz-gauge-inner span { margin-top: 1px; color: #7dd3fc; font-size: 7px; }
.vz-gauge-live > small { max-width: 100%; overflow: hidden; color: #64748b; font-size: 7px; text-overflow: ellipsis; white-space: nowrap; }

.vz-dynamic-list { height: 100%; min-height: 0; overflow: hidden; scrollbar-width: none; }
.vz-dynamic-list::-webkit-scrollbar { display: none; }
.vz-platform-live { padding: 3px 0; border-bottom: 1px solid rgba(148, 163, 184, 0.08); }
.vz-platform-top { display: flex; align-items: baseline; justify-content: space-between; gap: 6px; }
.vz-platform-top b { overflow: hidden; color: #e0f2fe; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.vz-platform-top small { flex-shrink: 0; color: #64748b; font-size: 7px; }
.vz-bar-row { display: flex; align-items: center; gap: 4px; margin-top: 3px; }
.vz-bar-row > span { width: 28px; flex-shrink: 0; color: #64748b; font-family: Consolas, monospace; font-size: 7px; }
.vz-bar-row > i { flex: 1; height: 3px; overflow: hidden; border-radius: 3px; background: rgba(148, 163, 184, 0.12); }
.vz-bar-row > i em { display: block; height: 100%; border-radius: 3px; box-shadow: 0 0 7px currentColor; transition: width 0.8s ease; }
.vz-bar-row > b { width: 28px; flex-shrink: 0; color: #cbd5e1; font-family: Consolas, monospace; font-size: 7px; text-align: right; }

.vz-host-live { display: flex; gap: 6px; padding: 4px 0; border-bottom: 1px solid rgba(148, 163, 184, 0.08); }
.vz-host-title { width: 70px; min-width: 0; }
.vz-host-title b { display: block; overflow: hidden; color: #e0f2fe; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.vz-host-title small { display: block; overflow: hidden; margin-top: 2px; color: #64748b; font-family: Consolas, monospace; font-size: 7px; text-overflow: ellipsis; white-space: nowrap; }
.vz-host-bars { flex: 1; min-width: 0; }

.vz-vm-live { display: flex; align-items: center; gap: 5px; padding: 4px 0; border-bottom: 1px solid rgba(148, 163, 184, 0.08); }
.vz-vm-rank { width: 14px; flex-shrink: 0; color: #38bdf8; font-family: Consolas, monospace; font-size: 8px; }
.vz-vm-info { flex: 1; min-width: 0; }
.vz-vm-info b { display: block; overflow: hidden; color: #e0f2fe; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.vz-vm-triple { display: flex; gap: 2px; height: 3px; margin-top: 3px; overflow: hidden; border-radius: 3px; background: rgba(148, 163, 184, 0.1); }
.vz-vm-triple i { height: 100%; border-radius: 3px; transition: width 0.8s ease; }
.vz-vm-value { width: 55px; flex-shrink: 0; text-align: right; }
.vz-vm-value b { display: block; color: #7dd3fc; font-family: Consolas, monospace; font-size: 9px; }
.vz-vm-value small { color: #64748b; font-family: Consolas, monospace; font-size: 7px; }

.vz-alert-live { display: flex; align-items: flex-start; gap: 5px; padding: 4px 0; border-bottom: 1px solid rgba(148, 163, 184, 0.08); }
.vz-alert-dot { width: 4px; height: 4px; flex-shrink: 0; margin-top: 4px; border-radius: 50%; background: #fbbf24; box-shadow: 0 0 6px #fbbf24; }
.vz-alert-live.critical .vz-alert-dot { background: #fb7185; box-shadow: 0 0 6px #fb7185; }
.vz-alert-live > div { flex: 1; min-width: 0; }
.vz-alert-live b { display: block; overflow: hidden; color: #e0f2fe; font-size: 8px; text-overflow: ellipsis; white-space: nowrap; }
.vz-alert-live small { display: block; overflow: hidden; color: #94a3b8; font-size: 7px; text-overflow: ellipsis; white-space: nowrap; }
.vz-alert-live time { flex-shrink: 0; color: #64748b; font-family: Consolas, monospace; font-size: 7px; }

.vz-no-data { display: grid; place-items: center; height: 100%; min-height: 24px; color: #475569; font-size: 9px; }
.vz-config-tip { color: #94a3b8; font-size: 12px; }
@keyframes vz-panel-in {
  from { opacity: 0; transform: translateY(5px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes vz-panel-scan {
  0% { left: -35%; opacity: 0; }
  18% { opacity: 1; }
  70% { opacity: 0.5; }
  100% { left: 100%; opacity: 0; }
}

@keyframes vz-pulse {
  0%, 100% { transform: scale(0.9); opacity: 0.3; }
  50% { transform: scale(1.1); opacity: 0.7; }
}

@keyframes vz-ring-breathe {
  0%, 100% { filter: drop-shadow(0 0 4px rgba(56, 189, 248, 0.2)); }
  50% { filter: drop-shadow(0 0 13px rgba(56, 189, 248, 0.5)); }
}

@media (max-width: 900px) {
  .vz-editbar > span { display: none; }
  .vz-panel-heading b { font-size: 10px; }
}
</style>
