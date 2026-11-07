<template>
  <div class="topology-widget">
    <div class="topo-meta">
      <span><i class="dot online"></i>{{ statusCount('online') }} 在线</span>
      <span><i class="dot warning"></i>{{ statusCount('warning') }} 告警</span>
      <span><i class="dot offline"></i>{{ statusCount('offline') }} 离线</span>
      <span class="topo-total">{{ nodes.length }} 台设备 · {{ edges.length }} 条链路</span>
      <span v-if="largeMode" class="topo-scale-note">大规模模式 · 按类型聚合</span>
    </div>

    <BigScreenAutoScroll v-if="largeMode && nodes.length" class="topo-large-scroll" :speed="10">
      <div class="topo-large-grid">
        <div v-for="group in largeGroups" :key="group.key" class="topo-large-card" :style="{ '--group-color': group.color }">
          <div><i></i><strong>{{ group.label }}</strong></div>
          <b>{{ group.count }} 台</b>
          <small>
            <span class="online">{{ group.online }} 在线</span>
            <span class="warning">{{ group.warning }} 告警</span>
            <span class="offline">{{ group.offline }} 离线</span>
          </small>
        </div>
      </div>
    </BigScreenAutoScroll>

    <div v-if="loading && !nodes.length" class="topo-state">拓扑加载中…</div>
    <div v-else-if="error" class="topo-state error">{{ error }}</div>
    <div v-else-if="!nodes.length" class="topo-state">当前没有可展示的拓扑设备</div>
    <svg
      v-else-if="!largeMode"
      class="topo-svg"
      :viewBox="`0 0 ${layout.width} ${layout.height}`"
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="网络拓扑"
    >
      <defs>
        <pattern :id="gridId" width="36" height="36" patternUnits="userSpaceOnUse">
          <path d="M 36 0 L 0 0 0 36" fill="none" stroke="rgba(56,189,248,0.07)" stroke-width="1" />
        </pattern>
      </defs>
      <rect :width="layout.width" :height="layout.height" :fill="`url(#${gridId})`" />

      <g v-for="layer in layout.layers" :key="layer.key">
        <line
          :x1="layer.x"
          :x2="layer.x + 150"
          :y1="30"
          :y2="30"
          :stroke="layer.color"
          stroke-opacity="0.55"
        />
        <text :x="layer.x + 75" y="20" text-anchor="middle" class="layer-title" :fill="layer.color">
          {{ layer.label }}
        </text>
      </g>

      <g class="topo-edges">
        <path
          v-for="edge in renderedEdges"
          :key="edge.id"
          :d="edge.d"
          fill="none"
          :stroke="edge.color"
          :stroke-width="edge.width"
          :stroke-opacity="edge.opacity"
          stroke-linecap="round"
        >
          <title>{{ edge.title }}</title>
        </path>
      </g>

      <g
        v-for="node in renderedNodes"
        :key="node.id"
        class="topo-node"
        :transform="`translate(${node.x}, ${node.y})`"
      >
        <title>{{ node.label }} · {{ node.ip_address }} · {{ statusText(node.status) }}</title>
        <rect
          width="150"
          height="54"
          rx="8"
          fill="rgba(5, 17, 30, 0.92)"
          :stroke="statusColor(node.status)"
          stroke-width="1.2"
        />
        <rect width="4" height="54" rx="2" :fill="statusColor(node.status)" />
        <circle cx="16" cy="17" r="4" :fill="statusColor(node.status)" />
        <text x="27" y="21" class="node-name">{{ truncate(node.label, 14) }}</text>
        <text x="14" y="41" class="node-meta">{{ truncate(node.ip_address || '', 19) }}</text>
        <text x="138" y="41" text-anchor="end" class="node-type">{{ typeShort(node.device_type) }}</text>
      </g>
    </svg>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { topologyApi } from '@/api'
import BigScreenAutoScroll from '@/components/BigScreenAutoScroll.vue'

const NODE_W = 150
const NODE_H = 54
const gridId = `topo-grid-${Math.random().toString(36).slice(2, 8)}`
const LAYERS = [
  { key: 'router', label: '路由层', types: ['router'], color: '#38bdf8' },
  { key: 'firewall', label: '安全边界', types: ['firewall'], color: '#f87171' },
  { key: 'switch', label: '交换层', types: ['switch'], color: '#34d399' },
  { key: 'security', label: '安全设备', types: ['security'], color: '#c084fc' },
  { key: 'server', label: '服务器', types: ['server'], color: '#fbbf24' },
  { key: 'other', label: '其他设备', types: [], color: '#94a3b8' },
]

const nodes = ref([])
const edges = ref([])
const loading = ref(false)
const error = ref('')
let timer = null

const layout = ref({ width: 980, height: 520, positions: {}, layers: [] })
const largeMode = computed(() => nodes.value.length > 80)
const largeGroups = computed(() => {
  const groups = new Map()
  nodes.value.forEach((node) => {
    const type = node.device_type || 'other'
    if (!groups.has(type)) {
      groups.set(type, {
        key: type,
        label: typeShort(type),
        color: {
          router: '#38bdf8',
          switch: '#34d399',
          firewall: '#f87171',
          security: '#c084fc',
          server: '#fbbf24',
          other: '#94a3b8',
        }[type] || '#94a3b8',
        count: 0,
        online: 0,
        warning: 0,
        offline: 0,
      })
    }
    const item = groups.get(type)
    item.count += 1
    const status = node.status || 'unknown'
    if (item[status] !== undefined) item[status] += 1
  })
  return [...groups.values()].sort((a, b) => b.count - a.count)
})

const renderedNodes = computed(() => nodes.value.map((node) => ({
  ...node,
  x: layout.value.positions[node.id]?.x || 0,
  y: layout.value.positions[node.id]?.y || 0,
})))

const renderedEdges = computed(() => {
  const nodeMap = new Map(renderedNodes.value.map((node) => [node.id, node]))
  return edges.value.map((edge) => {
    const from = nodeMap.get(edge.source)
    const to = nodeMap.get(edge.target)
    if (!from || !to) return null
    const x1 = from.x + NODE_W / 2
    const y1 = from.y + NODE_H / 2
    const x2 = to.x + NODE_W / 2
    const y2 = to.y + NODE_H / 2
    const bend = Math.max(40, Math.abs(x2 - x1) * 0.45)
    const utilization = Number(edge.utilization || 0)
    const color = !edge.oper_up
      ? '#ef4444'
      : utilization >= 80
        ? '#fb7185'
        : utilization >= 60
          ? '#fbbf24'
          : 'rgba(56, 189, 248, 0.55)'
    return {
      id: edge.id,
      d: `M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`,
      color,
      width: utilization >= 60 ? 2 : 1.2,
      opacity: edge.oper_up ? 0.9 : 0.65,
      title: `${from.label} → ${to.label}${edge.oper_up ? '' : ' · 链路 DOWN'}`,
    }
  }).filter(Boolean)
})

function typeShort(type) {
  return {
    router: '路由',
    switch: '交换',
    firewall: '防火墙',
    server: '服务器',
    security: '安全',
    other: '设备',
  }[type] || '设备'
}

function truncate(value, size) {
  const text = String(value || '')
  return text.length > size ? `${text.slice(0, size - 1)}…` : text
}

function statusColor(status) {
  return {
    online: '#34d399',
    warning: '#fbbf24',
    offline: '#fb7185',
    unknown: '#64748b',
  }[status] || '#64748b'
}

function statusText(status) {
  return { online: '在线', warning: '告警', offline: '离线' }[status] || '未知'
}

function statusCount(status) {
  return nodes.value.filter((node) => (node.status || 'unknown') === status).length
}

function automaticLayout(list) {
  const groups = LAYERS.map((layer) => ({
    ...layer,
    items: list.filter((node) => (layer.types.length
      ? layer.types.includes(node.device_type)
      : !LAYERS.some((item) => item.types.includes(node.device_type)))),
  })).filter((layer) => layer.items.length)
  const maxRows = Math.max(...groups.map((layer) => layer.items.length), 1)
  const width = Math.max(720, groups.length * 196 + 76)
  const height = Math.max(420, maxRows * 82 + 88)
  const positions = {}
  const layers = []
  groups.forEach((layer, index) => {
    const x = 38 + index * 196
    const total = layer.items.length
    const top = 56 + Math.max(0, (maxRows * 82 - total * 82) / 2)
    layers.push({ key: layer.key, label: layer.label, color: layer.color, x })
    layer.items.forEach((node, row) => {
      positions[node.id] = { x, y: top + row * 82 }
    })
  })
  return { width, height, positions, layers }
}

function manualLayout(list) {
  const hasCoordinate = (value) => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value))
  const valid = list.filter((node) => hasCoordinate(node.x) && hasCoordinate(node.y))
  if (valid.length !== list.length) return automaticLayout(list)
  const minX = Math.min(...valid.map((node) => Number(node.x)))
  const minY = Math.min(...valid.map((node) => Number(node.y)))
  const maxX = Math.max(...valid.map((node) => Number(node.x) + NODE_W))
  const maxY = Math.max(...valid.map((node) => Number(node.y) + NODE_H))
  const padding = 44
  const positions = {}
  valid.forEach((node) => {
    positions[node.id] = {
      x: Number(node.x) - minX + padding,
      y: Number(node.y) - minY + padding,
    }
  })
  return {
    width: Math.max(520, maxX - minX + padding * 2),
    height: Math.max(320, maxY - minY + padding * 2),
    positions,
    layers: [],
  }
}

async function loadTopology() {
  loading.value = true
  error.value = ''
  try {
    const res = await topologyApi.getTopology()
    const data = res.data || {}
    nodes.value = Array.isArray(data.nodes) ? data.nodes : []
    edges.value = Array.isArray(data.edges) ? data.edges : []
    layout.value = manualLayout(nodes.value)
  } catch (err) {
    error.value = err?.response?.data?.detail || err?.message || '拓扑加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadTopology()
  timer = window.setInterval(loadTopology, 15000)
})

onBeforeUnmount(() => {
  if (timer) window.clearInterval(timer)
  timer = null
})
</script>

<style scoped>
.topology-widget {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  border-radius: 8px;
  background:
    radial-gradient(circle at 50% 0%, rgba(14, 165, 233, 0.1), transparent 48%),
    rgba(3, 12, 24, 0.55);
  overflow: hidden;
}

.topo-meta {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  padding: 7px 12px 0;
  color: #8ca6b8;
  font-size: 10px;
  flex-shrink: 0;
}

.topo-meta span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.topo-total {
  margin-left: auto;
  color: #5f8196;
  font-family: Consolas, monospace;
}

.dot {
  display: inline-block;
  width: 5px;
  height: 5px;
  border-radius: 50%;
}

.dot.online { background: #34d399; box-shadow: 0 0 6px #34d399; }
.dot.warning { background: #fbbf24; box-shadow: 0 0 6px #fbbf24; }
.dot.offline { background: #fb7185; box-shadow: 0 0 6px #fb7185; }

.topo-svg {
  display: block;
  width: 100%;
  height: 0;
  min-height: 0;
  flex: 1 1 auto;
}

.topo-scale-note {
  color: #fbbf24;
}

.topo-large-scroll {
  flex: 1;
  min-height: 0;
}

.topo-large-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
  padding: 10px 12px 12px;
  align-content: start;
}

.topo-large-card {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 5px 10px;
  padding: 12px 14px;
  border: 1px solid color-mix(in srgb, var(--group-color) 36%, transparent);
  border-radius: 8px;
  background: linear-gradient(135deg, color-mix(in srgb, var(--group-color) 12%, transparent), rgba(5, 17, 30, 0.9));
}

.topo-large-card div {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.topo-large-card i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--group-color);
  box-shadow: 0 0 7px var(--group-color);
}

.topo-large-card strong {
  overflow: hidden;
  color: #d9f3ff;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.topo-large-card b {
  color: var(--group-color);
  font-family: Consolas, monospace;
  font-size: 12px;
}

.topo-large-card small {
  grid-column: 1 / -1;
  display: flex;
  gap: 10px;
  font-size: 9px;
}

.topo-large-card small .online { color: #34d399; }
.topo-large-card small .warning { color: #fbbf24; }
.topo-large-card small .offline { color: #fb7185; }

.layer-title {
  font-family: 'Microsoft YaHei', sans-serif;
  font-size: 11px;
  font-weight: 600;
}

.node-name {
  fill: #d9f3ff;
  font-family: 'Microsoft YaHei', sans-serif;
  font-size: 12px;
  font-weight: 600;
}

.node-meta {
  fill: #7195aa;
  font-family: Consolas, monospace;
  font-size: 9px;
}

.node-type {
  fill: #8ba8ba;
  font-family: 'Microsoft YaHei', sans-serif;
  font-size: 8px;
}

.topo-node {
  cursor: pointer;
}

.topo-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #6b8a9e;
  font-size: 12px;
}

.topo-state.error {
  color: #fb7185;
}
</style>
