<template>
  <div ref="showcaseRef" class="room-showcase">
    <div class="rs-bg"></div>
    <header class="rs-header">
      <div class="rs-header-left">
        <el-button text class="rs-back" @click="$router.push('/rooms')">
          <el-icon><Back /></el-icon>机房管理
        </el-button>
        <div class="rs-room-switch">
          <el-select v-model="currentRoomId" size="small" filterable @change="switchRoom">
            <el-option v-for="item in rooms" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </div>
      </div>
      <div class="rs-title">
        <span class="rs-title-mark">◆</span>
        <h1>{{ room?.name || '机房数字孪生' }}</h1>
        <span class="rs-title-mark">◆</span>
      </div>
      <div class="rs-header-right">
        <span class="rs-clock">{{ clockText }}</span>
        <span class="rs-live"><i></i>LIVE</span>
        <el-button size="small" @click="refresh" :loading="loading">
          <el-icon><Refresh /></el-icon>刷新
        </el-button>
        <el-button size="small" @click="toggleFullscreen">
          <el-icon><FullScreen /></el-icon>{{ isFullscreen ? '退出全屏' : '全屏' }}
        </el-button>
      </div>
    </header>

    <section class="rs-metrics">
      <div v-for="metric in metrics" :key="metric.label" class="rs-metric" :class="metric.level">
        <div class="rs-metric-icon"><el-icon><component :is="metric.icon" /></el-icon></div>
        <div>
          <span>{{ metric.label }}</span>
          <strong>{{ metric.value }}</strong>
        </div>
        <small>{{ metric.hint }}</small>
      </div>
    </section>

    <main class="rs-main">
      <aside class="rs-side rs-left">
        <div class="rs-panel">
          <div class="rs-panel-head"><span>设备负载</span><small>AVERAGE</small></div>
          <div class="rs-gauges">
            <div class="rs-gauge-ring" :style="gaugeStyle(avgCpu, '#38bdf8')">
              <div><strong>{{ avgCpu ?? '--' }}</strong><small>%</small><span>CPU</span></div>
            </div>
            <div class="rs-gauge-ring" :style="gaugeStyle(avgMemory, '#a78bfa')">
              <div><strong>{{ avgMemory ?? '--' }}</strong><small>%</small><span>内存</span></div>
            </div>
          </div>
          <div class="rs-mini-metrics">
            <div><span>在线设备</span><b>{{ onlineCount }}</b></div>
            <div><span>告警设备</span><b class="warning">{{ warningCount }}</b></div>
            <div><span>离线设备</span><b class="danger">{{ offlineCount }}</b></div>
          </div>
        </div>

        <div class="rs-panel rs-panel-grow">
          <div class="rs-panel-head"><span>环境监测</span><small>ENV</small></div>
          <div class="rs-env">
            <div class="rs-env-item temperature">
              <el-icon><Sunny /></el-icon>
              <div><small>平均温度</small><strong>{{ sensorSummary.temperature_avg ?? avgTemperature ?? '--' }}<i>°C</i></strong></div>
            </div>
            <div class="rs-env-item humidity">
              <el-icon><Cloudy /></el-icon>
              <div><small>平均湿度</small><strong>{{ sensorSummary.humidity_avg ?? '--' }}<i>%</i></strong></div>
            </div>
          </div>
          <div class="rs-sensor-list">
            <div v-for="sensor in sensorSummary.sensors" :key="sensor.id" class="rs-sensor-row">
              <span :class="sensor.status"></span>
              <b>{{ sensor.name }}</b>
              <small>{{ sensor.last_temperature ?? '--' }}°C / {{ sensor.last_humidity ?? '--' }}%</small>
            </div>
            <div v-if="!sensorSummary.sensors.length" class="rs-empty-mini">未配置温湿度传感器</div>
          </div>
        </div>
      </aside>

      <section class="rs-scene-panel">
        <div class="rs-scene-head">
          <div>
            <span class="rs-scene-kicker">DIGITAL TWIN / REAL-TIME</span>
            <h2>机房机柜数字孪生</h2>
          </div>
          <div class="rs-scene-legend">
            <span><i class="online"></i>在线</span>
            <span><i class="warning"></i>告警</span>
            <span><i class="offline"></i>离线</span>
            <span><i class="unknown"></i>空闲</span>
          </div>
        </div>

        <div class="rs-scene">
          <div ref="threeRef" class="rs-three-canvas"></div>
          <div class="rs-scene-topline">
            <div class="rs-room-label">
              <b>{{ room?.name }}</b>
              <span>{{ room?.building || '' }} {{ room?.floor || '' }} · {{ room?.length_m }}×{{ room?.width_m }}m</span>
            </div>
            <div class="rs-three-controls">
              <el-switch v-model="manualAdjust" size="small" inline-prompt active-text="拖动定位" inactive-text="锁定视角" title="拖动定位后位置会保留；点击重置视角恢复居中" />
              <el-switch v-model="autoRotate" size="small" inline-prompt active-text="自动旋转" inactive-text="静止" />
              <el-dropdown trigger="click" @command="applyThreePreset">
                <el-button size="small">预置视角</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="overview">全景视角</el-dropdown-item>
                    <el-dropdown-item command="top">俯视视角</el-dropdown-item>
                    <el-dropdown-item command="front">正面视角</el-dropdown-item>
                    <el-dropdown-item command="side">侧面视角</el-dropdown-item>
                    <el-dropdown-item command="back">背面视角</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <el-button size="small" @click="resetThreeView">重置视角</el-button>
            </div>
          </div>
          <div v-if="manualAdjust" class="rs-drag-hint">
            <el-icon><Rank /></el-icon>左键平移 · 右键旋转 · 滚轮缩放 · 关闭后保留当前位置
          </div>

          <div
            v-if="hoverDevice"
            class="rs-device-tooltip"
            :style="{ left: `${hoverPosition.x}px`, top: `${hoverPosition.y}px` }"
          >
            <div class="rs-tip-head">
              <i :class="hoverDevice.status"></i>
              <strong>{{ hoverDevice.name }}</strong>
              <el-tag :type="hoverDevice.status === 'online' ? 'success' : hoverDevice.status === 'warning' ? 'warning' : 'info'" size="small">
                {{ statusText(hoverDevice.status) }}
              </el-tag>
            </div>
            <div class="rs-tip-line"><span>IP 地址</span><b>{{ hoverDevice.ip_address || '-' }}</b></div>
            <div class="rs-tip-line"><span>设备类型</span><b>{{ hoverDevice.device_type || '-' }}</b></div>
            <div class="rs-tip-line"><span>所在机柜</span><b>{{ hoverDevice.cabinetName }} · {{ formatURange(hoverDevice.u_position, hoverDevice.u_height) }}</b></div>
            <div class="rs-tip-line"><span>CPU / 内存</span><b>{{ hoverDevice.cpu_usage ?? '-' }}% / {{ hoverDevice.memory_usage ?? '-' }}%</b></div>
            <div class="rs-tip-action">点击查看设备详情</div>
          </div>

          <div class="rs-scene-footer">
            <span><small>机柜</small><b>{{ cabinets.length }}</b></span>
            <span><small>设备</small><b>{{ devices.length }}</b></span>
            <span><small>在线率</small><b>{{ devices.length ? Math.round(onlineCount / devices.length * 100) : 0 }}%</b></span>
            <span><small>告警</small><b class="warning">{{ warningCount }}</b></span>
          </div>

          <el-empty v-if="!cabinets.length" description="该机房尚未添加机柜" :image-size="60" class="rs-three-empty" />

          <div v-if="selectedCabinet" class="rs-rack-detail">
            <div class="rs-detail-head">
              <div>
                <strong>{{ selectedCabinet.name }}</strong>
                <span>{{ Number(selectedCabinet.row_index || 0) + 1 }} 排 {{ Number(selectedCabinet.col_index || 0) + 1 }} 列</span>
              </div>
              <el-button link @click="selectedCabinetId = null"><el-icon><Close /></el-icon></el-button>
            </div>
            <div class="rs-detail-grid">
              <div><span>状态</span><b :class="cabinetStatus(selectedCabinet)">{{ statusText(cabinetStatus(selectedCabinet)) }}</b></div>
              <div><span>设备</span><b>{{ selectedCabinet.usage?.device_count || 0 }} 台</b></div>
              <div><span>U 位</span><b>{{ selectedCabinet.usage?.used_u || 0 }} / {{ selectedCabinet.u_capacity || 0 }}U</b></div>
              <div><span>功耗</span><b>{{ ((selectedCabinet.usage?.used_power_w || 0) / 1000).toFixed(2) }} kW</b></div>
              <div><span>柜门</span><b :class="selectedCabinet.door_state === 'open' ? 'online' : ''">{{ selectedCabinet.door_state === 'open' ? '已打开' : '已关闭' }}</b></div>
            </div>
            <div class="rs-detail-bar"><i :style="{ width: `${Math.min(selectedCabinet.usage?.u_percent || 0, 100)}%` }"></i></div>
            <div v-if="canEditRoom" class="rs-door-actions">
              <el-button size="small" type="primary" plain :loading="doorBusy" @click="toggleSelectedDoor">
                <el-icon><SwitchButton /></el-icon>{{ selectedCabinet.door_state === 'open' ? '关闭机柜门' : '打开机柜门' }}
              </el-button>
              <span>{{ selectedCabinet.door_state === 'open' ? '当前门板已向外打开，可点击柜内设备' : '点击柜门或按钮打开机柜门' }}</span>
            </div>
            <div class="rs-detail-devices">
              <div v-for="device in selectedCabinet.devices || []" :key="device.id" class="rs-device-row rs-device-row-clickable" @click="openDeviceDetail(device.id)">
                <span :class="device.status"></span>
                <b>{{ device.name }}</b>
                <small>{{ formatURange(device.u_position, device.u_height) }} · {{ device.cpu_usage ?? '-' }}%</small>
              </div>
              <div v-if="!(selectedCabinet.devices || []).length" class="rs-empty-mini">机柜内暂无设备</div>
            </div>
            <el-button
              v-if="canEditRoom"
              type="primary"
              size="small"
              plain
              class="rs-place-device"
              @click="openDevicePlacement"
            >
              <el-icon><Plus /></el-icon>添加 / 调整设备
            </el-button>
          </div>
        </div>
      </section>

      <aside class="rs-side rs-right">
        <div class="rs-panel">
          <div class="rs-panel-head"><span>功耗容量</span><small>POWER</small></div>
          <div class="rs-power-value">{{ (totalPower / 1000).toFixed(1) }} <small>kW</small></div>
          <div class="rs-progress"><i :style="{ width: `${powerPercent}%` }"></i></div>
          <div class="rs-meta-row"><span>已用 / 总容量</span><b>{{ (totalPower / 1000).toFixed(1) }} / {{ (powerCapacity / 1000).toFixed(1) }} kW</b></div>
          <div class="rs-meta-row"><span>U 位使用</span><b>{{ uPercent }}%</b></div>
        </div>

        <div class="rs-panel rs-panel-grow">
          <div class="rs-panel-head"><span>机柜负载 TOP</span><small>LOAD</small></div>
          <div class="rs-load-list">
            <div v-for="cab in topCabinets" :key="cab.id" class="rs-load-row">
              <span>{{ cab.name }}</span>
              <div><i :style="{ width: `${Math.min(cab.usage?.u_percent || 0, 100)}%` }"></i></div>
              <b>{{ Math.round(cab.usage?.u_percent || 0) }}%</b>
            </div>
          </div>
        </div>

        <div class="rs-panel">
          <div class="rs-panel-head"><span>机房温湿度</span><small>SENSOR</small></div>
          <div class="rs-env-line">
            <span>温度 <b>{{ sensorSummary.temperature_avg ?? '--' }}°C</b></span>
            <span>湿度 <b>{{ sensorSummary.humidity_avg ?? '--' }}%</b></span>
            <el-tag v-if="sensorSummary.alarm_count" type="danger" size="small">{{ sensorSummary.alarm_count }} 超限</el-tag>
          </div>
        </div>
      </aside>
    </main>

    <footer class="rs-alerts">
      <div class="rs-alert-title"><i></i>实时告警 <span>{{ roomAlerts.length }}</span></div>
      <div class="rs-alert-track" :class="{ empty: !roomAlerts.length }">
        <template v-if="roomAlerts.length">
          <span v-for="alert in tickerAlerts" :key="`${alert.id}-${alert._copy}`" class="rs-alert-item" :class="alert.alert_level">
            <time>{{ formatTime(alert.created_at) }}</time>
            <b>{{ alert.device_name || alert.source_name || '系统' }}</b>
            <span>{{ alert.message }}</span>
          </span>
        </template>
        <span v-else class="rs-no-alert">当前机房暂无未处理告警</span>
      </div>
    </footer>

    <el-dialog v-model="placementVisible" title="机柜设备上架 / U 位设置" width="520px" :close-on-click-modal="false">
      <el-form :model="placementForm" label-width="92px">
        <el-form-item label="机柜">
          <el-input :model-value="selectedCabinet?.name || ''" disabled />
        </el-form-item>
        <el-form-item label="上架方式">
          <el-radio-group v-model="placementForm.mode" size="small">
            <el-radio-button value="existing">从资产选择</el-radio-button>
            <el-radio-button value="new">新建设备</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <template v-if="placementForm.mode === 'existing'">
          <el-form-item label="设备" required>
            <el-select v-model="placementForm.device_id" filterable style="width:100%" placeholder="选择未上架设备或本机柜设备" @change="onPlacementDeviceChange">
              <el-option
                v-for="device in availableDevices"
                :key="device.id"
                :label="`${device.name} · ${device.ip_address}${device.cabinet_id ? '（当前机柜）' : ''}`"
                :value="device.id"
              />
            </el-select>
            <div class="rs-place-hint">仅显示未上架设备，以及当前机柜已有设备</div>
          </el-form-item>
        </template>
        <template v-else>
          <el-row :gutter="12">
            <el-col :span="12">
              <el-form-item label="设备名称" required>
                <el-input v-model="placementForm.name" placeholder="新设备名称" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="IP 地址" required>
                <el-input v-model="placementForm.ip_address" placeholder="192.168.1.1" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="设备类型" required>
                <el-select v-model="placementForm.device_type" style="width:100%">
                  <el-option v-for="item in DEVICE_TYPE_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="厂商">
                <el-input v-model="placementForm.vendor" />
              </el-form-item>
            </el-col>
          </el-row>
        </template>
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="起始 U 位">
              <div class="rs-u-auto-row">
                <el-input-number v-model="placementForm.u_position" :min="1" :max="selectedCabinet?.u_capacity || 42" controls-position="right" placeholder="自动分配" style="width:100%" />
                <el-button link type="primary" @click="placementForm.u_position = null">自动分配</el-button>
              </div>
              <div class="rs-place-hint">不填写时自动选择最低的连续空闲 U 位；选择已有设备时会带出当前 U 位，可清空后重新自动分配。</div>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="占用 U 数">
              <el-input-number v-model="placementForm.u_height" :min="1" :max="selectedCabinet?.u_capacity || 42" controls-position="right" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="额定功率">
              <el-input-number v-model="placementForm.power_watts" :min="0" :max="100000" :step="50" controls-position="right" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <div class="rs-place-hint">系统会校验 U 位是否越界、重叠以及机柜功率是否超限。</div>
      </el-form>
      <template #footer>
        <el-button @click="placementVisible = false">取消</el-button>
        <el-button type="primary" :loading="placementSaving" @click="savePlacement">保存上架</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js'
import { ElMessage } from 'element-plus'
import { roomApi, monitorApi, assetApi } from '@/api'
import { refreshMs } from '@/store/settings'
import { formatHM } from '@/utils/time'
import { can } from '@/store/auth'
import { DEVICE_TYPES as DEVICE_TYPE_OPTIONS } from '@/constants/device'

const route = useRoute()
const router = useRouter()
const showcaseRef = ref(null)
const rooms = ref([])
const room = ref(null)
const cabinets = ref([])
const alerts = ref([])
const now = ref(new Date())
const loading = ref(false)
const isFullscreen = ref(false)
const selectedCabinetId = ref(null)
const sensorSummary = ref({ sensors: [], temperature_avg: null, humidity_avg: null, alarm_count: 0 })
const autoRotate = ref(true)
const manualAdjust = ref(false)
const hoverDevice = ref(null)
const hoverPosition = ref({ x: 0, y: 0 })
let lastHoverAt = 0
const threeRef = ref(null)
const canEditRoom = computed(() => can('rooms:edit'))
const doorBusy = ref(false)
const placementVisible = ref(false)
const placementSaving = ref(false)
const availableDevices = ref([])
const placementForm = ref({
  mode: 'existing',
  device_id: null,
  name: '',
  ip_address: '',
  device_type: 'server',
  vendor: '',
  u_position: null,
  u_height: 1,
  power_watts: 0,
})
let refreshTimer = null
let clockTimer = null

let threeRenderer = null
let threeScene = null
let threeCamera = null
let threeControls = null
let threeAnimation = null
let threeResizeObserver = null
let threeFitTimer = null
let viewCustomized = false
let threeFitDistance = 20
let cabinetGroup3d = null
let cabinetObjectMap = new Map()
let cabinetDoorMap = new Map()
let raycaster = null
let pointer = null
let threeSignature = ''
const threeCenter = new THREE.Vector3()
const THREE_VIEW_STORAGE_PREFIX = 'nms_room_three_view_'

function threeViewStorageKey() {
  return `${THREE_VIEW_STORAGE_PREFIX}${currentRoomId.value || route.params.id || ''}`
}

function saveThreeView() {
  if (!threeCamera || !threeControls || !viewCustomized) return
  try {
    sessionStorage.setItem(threeViewStorageKey(), JSON.stringify({
      position: threeCamera.position.toArray(),
      target: threeControls.target.toArray(),
    }))
  } catch {
    /* 忽略浏览器存储限制 */
  }
}

function restoreThreeView() {
  if (!threeCamera || !threeControls) return false
  try {
    const raw = sessionStorage.getItem(threeViewStorageKey())
    if (!raw) return false
    const saved = JSON.parse(raw)
    if (!Array.isArray(saved?.position) || !Array.isArray(saved?.target)) return false
    threeCamera.position.fromArray(saved.position)
    threeControls.target.fromArray(saved.target)
    threeCamera.lookAt(threeControls.target)
    threeControls.update()
    viewCustomized = true
    return true
  } catch {
    return false
  }
}

function clearThreeView() {
  try {
    sessionStorage.removeItem(threeViewStorageKey())
  } catch {
    /* 忽略浏览器存储限制 */
  }
}

const currentRoomId = ref(Number(route.params.id))

const devices = computed(() => cabinets.value.flatMap((cab) => (cab.devices || []).map((device) => ({
  ...device,
  cabinetName: cab.name,
}))))
const onlineCount = computed(() => devices.value.filter((d) => d.status === 'online').length)
const warningCount = computed(() => devices.value.filter((d) => d.status === 'warning').length)
const offlineCount = computed(() => devices.value.filter((d) => d.status === 'offline').length)
const totalPower = computed(() => cabinets.value.reduce((sum, cab) => sum + Number(cab.usage?.used_power_w || 0), 0))
const powerCapacity = computed(() => cabinets.value.reduce((sum, cab) => sum + Number(cab.power_capacity_w || 0), 0))
const powerPercent = computed(() => powerCapacity.value ? Math.min(100, totalPower.value / powerCapacity.value * 100) : 0)
const totalU = computed(() => cabinets.value.reduce((sum, cab) => sum + Number(cab.u_capacity || 0), 0))
const usedU = computed(() => cabinets.value.reduce((sum, cab) => sum + Number(cab.usage?.used_u || 0), 0))
const uPercent = computed(() => totalU.value ? Math.round(usedU.value / totalU.value * 100) : 0)
const avgCpu = computed(() => average(devices.value.map((d) => d.cpu_usage)))
const avgMemory = computed(() => average(devices.value.map((d) => d.memory_usage)))
const avgTemperature = computed(() => average(devices.value.map((d) => d.temperature)))
const selectedCabinet = computed(() => cabinets.value.find((cab) => cab.id === selectedCabinetId.value) || null)
const topCabinets = computed(() => [...cabinets.value]
  .sort((a, b) => (b.usage?.u_percent || 0) - (a.usage?.u_percent || 0))
  .slice(0, 8))
const cabinetRows = computed(() => {
  const groups = new Map()
  cabinets.value.forEach((cab) => {
    const row = Number(cab.row_index || 1)
    if (!groups.has(row)) groups.set(row, [])
    groups.get(row).push(cab)
  })
  return [...groups.entries()].sort((a, b) => a[0] - b[0]).map(([rowIndex, items]) => ({
    rowIndex,
    label: `${String.fromCharCode(64 + Math.min(rowIndex, 26))} 排`,
    items: items.sort((a, b) => Number(a.col_index || 0) - Number(b.col_index || 0)),
  }))
})

const roomAlerts = computed(() => {
  const ids = new Set(devices.value.map((d) => d.id))
  return alerts.value.filter((alert) => ids.has(alert.device_id)).slice(0, 8)
})
const tickerAlerts = computed(() => {
  if (!roomAlerts.value.length) return []
  return [...roomAlerts.value, ...roomAlerts.value.map((alert) => ({ ...alert, _copy: 1 }))]
})

const metrics = computed(() => [
  { label: '机柜总数', value: cabinets.value.length, hint: 'RACKS', icon: 'OfficeBuilding', level: '' },
  { label: '设备总数', value: devices.value.length, hint: 'DEVICES', icon: 'Cpu', level: '' },
  { label: '在线设备', value: onlineCount.value, hint: 'ONLINE', icon: 'CircleCheckFilled', level: 'success' },
  { label: '告警设备', value: warningCount.value, hint: 'WARNING', icon: 'WarningFilled', level: 'warning' },
  { label: '离线设备', value: offlineCount.value, hint: 'OFFLINE', icon: 'CircleCloseFilled', level: 'danger' },
  { label: 'U 位使用', value: `${uPercent.value}%`, hint: `${usedU.value} / ${totalU.value}U`, icon: 'Grid', level: uPercent.value >= 85 ? 'warning' : '' },
  { label: '总功耗', value: `${(totalPower.value / 1000).toFixed(1)}kW`, hint: 'POWER', icon: 'Lightning', level: '' },
  { label: '平均温度', value: `${sensorSummary.value.temperature_avg ?? avgTemperature.value ?? '--'}°C`, hint: 'TEMP', icon: 'Sunny', level: '' },
])

function average(values) {
  const valid = values.filter((value) => value !== null && value !== undefined && !Number.isNaN(Number(value)))
  if (!valid.length) return '--'
  return (valid.reduce((sum, value) => sum + Number(value), 0) / valid.length).toFixed(1)
}

function gaugeStyle(value, color) {
  const percent = value === '--' || value === null ? 0 : Math.min(100, Number(value) || 0)
  return { '--gauge': `${percent}%`, '--gauge-color': color }
}

function cabinetStatus(cab) {
  if ((cab.devices || []).some((device) => device.status === 'offline')) return 'offline'
  if ((cab.devices || []).some((device) => device.status === 'warning')) return 'warning'
  if ((cab.devices || []).length) return 'online'
  return 'unknown'
}

function statusText(status) {
  return { online: '正常', warning: '告警', offline: '离线', unknown: '空闲' }[status] || status
}

const CABINET_W = 1.02
const CABINET_H = 2.2
const CABINET_D = 0.96
const DOOR_OPEN_ANGLE = -Math.PI * 0.58
let worldGroup = null
let selectionRing = null

function disposeObject(object) {
  object?.traverse?.((child) => {
    child.geometry?.dispose?.()
    if (Array.isArray(child.material)) child.material.forEach((material) => material.dispose?.())
    else child.material?.dispose?.()
    if (child.material?.map) child.material.map.dispose?.()
  })
}

function initThree() {
  if (!threeRef.value || threeRenderer) return
  threeScene = new THREE.Scene()
  threeCamera = new THREE.PerspectiveCamera(42, 1, 0.1, 300)
  threeRenderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
  threeRenderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  threeRenderer.setClearColor(0x000000, 0)
  threeRenderer.toneMapping = THREE.ACESFilmicToneMapping
  threeRenderer.toneMappingExposure = 1.12
  threeRenderer.outputColorSpace = THREE.SRGBColorSpace
  threeRenderer.domElement.className = 'rs-three-dom'
  threeRef.value.appendChild(threeRenderer.domElement)
  const pmrem = new THREE.PMREMGenerator(threeRenderer)
  threeScene.environment = pmrem.fromScene(new RoomEnvironment(), 0.035).texture
  pmrem.dispose()

  threeControls = new OrbitControls(threeCamera, threeRenderer.domElement)
  threeControls.enableDamping = true
  threeControls.dampingFactor = 0.065
  threeControls.enablePan = false
  threeControls.screenSpacePanning = true
  threeControls.mouseButtons.LEFT = THREE.MOUSE.ROTATE
  threeControls.mouseButtons.MIDDLE = THREE.MOUSE.DOLLY
  threeControls.mouseButtons.RIGHT = THREE.MOUSE.PAN
  threeControls.autoRotate = autoRotate.value
  threeControls.autoRotateSpeed = 0.65
  threeControls.minDistance = 2
  threeControls.maxDistance = 200
  threeControls.maxPolarAngle = Math.PI / 2.08
  threeControls.target.set(0, 1, 0)
  // 默认支持鼠标旋转和滚轮缩放；平移仅在「拖动定位」开启后启用
  threeControls.enableRotate = true
  threeControls.enablePan = false
  threeControls.enableZoom = true

  threeScene.add(new THREE.AmbientLight(0xffffff, 0.52))
  threeScene.add(new THREE.HemisphereLight(0xc9d6df, 0x030405, 0.82))
  const key = new THREE.DirectionalLight(0xffffff, 1.5)
  key.position.set(5, 10, 7)
  threeScene.add(key)
  const rim = new THREE.DirectionalLight(0x38bdf8, 0.4)
  rim.position.set(-7, 4, -6)
  threeScene.add(rim)
  const warm = new THREE.PointLight(0xffd0a0, 4.5, 15, 2)
  warm.position.set(0, 4.5, 3)
  threeScene.add(warm)

  raycaster = new THREE.Raycaster()
  pointer = new THREE.Vector2()
  selectionRing = new THREE.Mesh(
    new THREE.RingGeometry(0.72, 0.8, 48),
    new THREE.MeshBasicMaterial({ color: 0x38bdf8, transparent: true, opacity: 0, side: THREE.DoubleSide }),
  )
  selectionRing.rotation.x = -Math.PI / 2
  selectionRing.position.y = 0.035
  threeScene.add(selectionRing)

  threeRenderer.domElement.addEventListener('click', onThreeClick)
  threeRenderer.domElement.addEventListener('pointermove', onThreePointerMove)
  threeRenderer.domElement.addEventListener('pointerleave', onThreePointerLeave)
  threeControls.addEventListener('start', () => {
    // 鼠标旋转、滚轮缩放或拖动定位后都保留用户当前视角
    viewCustomized = true
  })
  threeControls.addEventListener('end', () => {
    // 松开鼠标后保存当前相机位置，刷新数据或关闭拖动定位时不再回弹
    saveThreeView()
  })
  threeRenderer.domElement.style.cursor = manualAdjust.value ? 'grab' : 'default'
  threeResizeObserver = new ResizeObserver(resizeThreeViewport)
  threeResizeObserver.observe(threeRef.value)
  window.addEventListener('resize', resizeThreeViewport)
  animateThree()
}

function resizeThreeViewport() {
  if (!threeRenderer || !threeCamera || !threeRef.value) return
  const width = threeRef.value.clientWidth
  const height = threeRef.value.clientHeight
  if (!width || !height) return
  threeRenderer.setSize(width, height, false)
  const aspect = width / height
  if (Math.abs(threeCamera.aspect - aspect) > 0.001) {
    threeCamera.aspect = aspect
    threeCamera.updateProjectionMatrix()
  }
  if (worldGroup && !manualAdjust.value && !viewCustomized) fitThreeView()
}

function formatCabinetPower(watts) {
  const value = Number(watts) || 0
  if (value >= 1000) return `${(value / 1000).toFixed(value >= 10000 ? 0 : 1)} kW`
  return `${Math.round(value)} W`
}

function makeCabinetLabel(name, color, cab) {
  const canvas = document.createElement('canvas')
  canvas.width = 340
  canvas.height = 108
  const ctx = canvas.getContext('2d')
  ctx.clearRect(0, 0, 340, 108)
  ctx.fillStyle = 'rgba(6, 18, 30, 0.88)'
  ctx.strokeStyle = `${color}99`
  ctx.lineWidth = 2
  ctx.beginPath()
  ctx.roundRect?.(4, 4, 332, 98, 10)
  if (!ctx.roundRect) ctx.rect(4, 4, 332, 98)
  ctx.fill()
  ctx.stroke()

  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.font = '700 18px "Microsoft YaHei", sans-serif'
  ctx.fillStyle = '#bfe9f8'
  ctx.fillText(String(name || '').slice(0, 24), 170, 28)

  const usedU = Number(cab?.usage?.used_u || 0)
  const capacity = Number(cab?.u_capacity || 42)
  const deviceCount = Number(cab?.usage?.device_count || (cab?.devices || []).length)
  ctx.font = '600 13px "Microsoft YaHei", sans-serif'
  ctx.fillStyle = '#7dd3fc'
  ctx.fillText(`占用 ${usedU}U / ${capacity}U · ${deviceCount} 台设备`, 170, 56)

  const powerW = Number(cab?.usage?.used_power_w || 0)
  const powerCapacity = Number(cab?.usage?.power_capacity_w || cab?.power_capacity_w || 0)
  const powerPercent = powerCapacity > 0 ? (powerW / powerCapacity) * 100 : 0
  const powerColor = powerPercent >= 90 ? '#fb7185' : powerPercent >= 70 ? '#fbbf24' : '#6ee7b7'
  const powerText = powerCapacity > 0
    ? `使用功率 ${formatCabinetPower(powerW)} / ${formatCabinetPower(powerCapacity)}`
    : `使用功率 ${formatCabinetPower(powerW)}`
  ctx.font = '700 13px "Microsoft YaHei", sans-serif'
  ctx.fillStyle = powerColor
  ctx.fillText(powerText, 170, 82)

  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  const material = new THREE.SpriteMaterial({ map: texture, transparent: true, depthWrite: false })
  const sprite = new THREE.Sprite(material)
  sprite.scale.set(1.8, 0.57, 1)
  return sprite
}

function makeURuler(cab) {
  const capacity = Math.max(1, Number(cab.u_capacity) || 42)
  const canvas = document.createElement('canvas')
  canvas.width = 240
  canvas.height = 2048
  const ctx = canvas.getContext('2d')
  const top = 18
  const bottom = 2030
  const fontSize = capacity > 48 ? 30 : 34
  const occupied = {}
  ;(cab.devices || []).forEach((device) => {
    const start = Math.max(1, Number(device.u_position) || 1)
    const height = Math.max(1, Number(device.u_height) || 1)
    for (let u = start; u < start + height && u <= capacity; u += 1) occupied[u] = device.status
  })
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  ctx.strokeStyle = 'rgba(125, 211, 252, 0.9)'
  ctx.lineWidth = 3
  ctx.beginPath()
  ctx.moveTo(212, top)
  ctx.lineTo(212, bottom)
  ctx.stroke()
  for (let u = 1; u <= capacity; u += 1) {
    const y = bottom - ((u - 1) / Math.max(capacity - 1, 1)) * (bottom - top)
    const status = occupied[u]
    const color = status === 'online' ? '#34d399' : status === 'warning' ? '#fbbf24' : status === 'offline' ? '#fb7185' : null
    // 占用状态仍逐 U 标注，便于观察设备分布
    if (color) {
      ctx.strokeStyle = color
      ctx.lineWidth = 6
      ctx.beginPath()
      ctx.moveTo(220, y)
      ctx.lineTo(236, y)
      ctx.stroke()
    }
    // 只给 1U、5U 整数倍和顶部容量画文字刻度，避免 1U 间隔文字重叠
    const isTextTick = u === 1 || u === capacity || u % 5 === 0
    ctx.strokeStyle = isTextTick ? 'rgba(125, 211, 252, 0.95)' : 'rgba(125, 211, 252, 0.38)'
    ctx.lineWidth = isTextTick ? 4 : 2
    ctx.beginPath()
    ctx.moveTo(isTextTick ? 192 : 202, y)
    ctx.lineTo(212, y)
    ctx.stroke()
    if (!isTextTick) continue
    ctx.fillStyle = color || '#d5f3ff'
    ctx.font = `${u === 1 || u === capacity ? 700 : 600} ${fontSize}px "Microsoft YaHei", sans-serif`
    ctx.textAlign = 'right'
    ctx.textBaseline = 'middle'
    ctx.fillText(`${u}U`, 184, y)
  }
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  const material = new THREE.MeshBasicMaterial({
    map: texture,
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
  })
  const ruler = new THREE.Mesh(new THREE.PlaneGeometry(0.46, CABINET_H * 0.96), material)
  ruler.position.set(-CABINET_W * 0.68, CABINET_H / 2, CABINET_D / 2 + 0.12)
  ruler.renderOrder = 5
  return ruler
}

// U 位标签统一使用“数字+U”格式：22U / 22U-24U
function formatURange(start, height = 1) {
  const from = Math.max(1, Math.round(Number(start) || 1))
  const heightU = Math.max(1, Math.round(Number(height) || 1))
  return heightU > 1 ? `${from}U-${from + heightU - 1}U` : `${from}U`
}

function makeDeviceTag(device, start, heightU, y, unitHeight = CABINET_H / 42) {
  const canvas = document.createElement('canvas')
  canvas.width = 256
  canvas.height = 64
  const ctx = canvas.getContext('2d')
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  ctx.fillStyle = 'rgba(5, 20, 32, 0.9)'
  ctx.strokeStyle = 'rgba(125, 211, 252, 0.8)'
  ctx.lineWidth = 2
  ctx.beginPath()
  ctx.roundRect?.(2, 2, 252, 60, 9)
  if (!ctx.roundRect) ctx.rect(2, 2, 252, 60)
  ctx.fill()
  ctx.stroke()
  ctx.font = '700 34px "Microsoft YaHei", sans-serif'
  ctx.fillStyle = '#d9f6ff'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(formatURange(start, heightU), 128, 32)
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    depthWrite: false,
  }))
  // 标签高度压在 1U 以内（≤ 0.84U），避免上下相邻设备标签互相覆盖
  const unit = Math.max(0.01, Number(unitHeight) || CABINET_H / 42)
  const tagHeight = Math.min(unit * 0.84, 0.062)
  const tagWidth = tagHeight * (canvas.width / canvas.height)
  sprite.scale.set(tagWidth, tagHeight, 1)
  sprite.position.set(-CABINET_W * 0.22, y, CABINET_D / 2 + 0.1)
  sprite.renderOrder = 6
  return sprite
}

function makeRackDoorPatternTexture() {
  const canvas = document.createElement('canvas')
  canvas.width = 256
  canvas.height = 512
  const ctx = canvas.getContext('2d')
  ctx.fillStyle = '#050708'
  ctx.fillRect(0, 0, canvas.width, canvas.height)
  // 黑色冲孔网门：深灰孔点 + 轻微横向加强筋，不反光成银色
  const stepX = 11
  const stepY = 9
  ctx.fillStyle = '#24282d'
  for (let row = 0, y = 7; y < canvas.height - 5; row += 1, y += stepY) {
    for (let x = 7 + (row % 2) * (stepX / 2); x < canvas.width - 5; x += stepX) {
      ctx.beginPath()
      ctx.arc(x, y, 2.15, 0, Math.PI * 2)
      ctx.fill()
    }
  }
  ctx.fillStyle = '#171b1f'
  for (let y = 76; y < canvas.height; y += 112) ctx.fillRect(0, y, canvas.width, 2)
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.anisotropy = 4
  return texture
}

function makeRackDoorAlphaTexture() {
  const canvas = document.createElement('canvas')
  canvas.width = 256
  canvas.height = 512
  const ctx = canvas.getContext('2d')
  ctx.fillStyle = '#ffffff'
  ctx.fillRect(0, 0, canvas.width, canvas.height)
  ctx.fillStyle = '#000000'
  const stepX = 11
  const stepY = 9
  for (let row = 0, y = 7; y < canvas.height - 5; row += 1, y += stepY) {
    for (let x = 7 + (row % 2) * (stepX / 2); x < canvas.width - 5; x += stepX) {
      ctx.beginPath()
      ctx.arc(x, y, 2.35, 0, Math.PI * 2)
      ctx.fill()
    }
  }
  const texture = new THREE.CanvasTexture(canvas)
  texture.anisotropy = 4
  return texture
}

function makeRackDoorTexture() {
  const canvas = document.createElement('canvas')
  canvas.width = 256
  canvas.height = 512
  const ctx = canvas.getContext('2d')
  ctx.fillStyle = '#050708'
  ctx.fillRect(0, 0, canvas.width, canvas.height)
  // 细密圆形冲孔网：孔位透明，能看到柜内设备与 LED
  ctx.globalCompositeOperation = 'destination-out'
  const stepX = 11
  const stepY = 9
  for (let row = 0, y = 7; y < canvas.height - 5; row += 1, y += stepY) {
    for (let x = 7 + (row % 2) * (stepX / 2); x < canvas.width - 5; x += stepX) {
      ctx.beginPath()
      ctx.arc(x, y, 2.35, 0, Math.PI * 2)
      ctx.fill()
    }
  }
  ctx.globalCompositeOperation = 'source-over'
  const sheen = ctx.createLinearGradient(0, 0, canvas.width, 0)
  sheen.addColorStop(0, 'rgba(255,255,255,0.035)')
  sheen.addColorStop(0.18, 'rgba(255,255,255,0.006)')
  sheen.addColorStop(0.48, 'rgba(255,255,255,0.02)')
  sheen.addColorStop(0.72, 'rgba(255,255,255,0.004)')
  sheen.addColorStop(1, 'rgba(255,255,255,0.028)')
  ctx.fillStyle = sheen
  ctx.fillRect(0, 0, canvas.width, canvas.height)
  // 网孔门横向加强筋，增加黑色金属机柜的真实层次
  ctx.fillStyle = 'rgba(255,255,255,0.028)'
  for (let y = 70; y < canvas.height; y += 110) ctx.fillRect(0, y, canvas.width, 2)
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.anisotropy = 4
  return texture
}

function rackMetalMaterial(color, metalness = 0.86, roughness = 0.36, emissive = 0x000000, emissiveIntensity = 0) {
  const material = new THREE.MeshStandardMaterial({
    color,
    metalness,
    roughness,
    emissive,
    emissiveIntensity,
  })
  material.envMapIntensity = 0.16
  return material
}

function addRackBox(group, width, height, depth, material, x, y, z) {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(width, height, depth), material)
  mesh.position.set(x, y, z)
  group.add(mesh)
  return mesh
}

function buildCabinet(cab, x, z) {
  const group = new THREE.Group()
  group.position.set(x, 0.05, z)
  group.userData.cabinetId = cab.id

  const status = cabinetStatus(cab)
  const color = { online: 0x22c55e, warning: 0xf59e0b, offline: 0xef4444, unknown: 0x64748b }[status]
  const frameMaterial = rackMetalMaterial(0x0b0e11, 0.36, 0.52, color, 0.018)
  group.userData.frameMaterial = frameMaterial
  const shellMaterial = rackMetalMaterial(0x06080a, 0.28, 0.62)
  const railMaterial = rackMetalMaterial(0x171b20, 0.4, 0.48)
  const interiorMaterial = rackMetalMaterial(0x030405, 0.22, 0.88)
  const handleMaterial = rackMetalMaterial(0x252b31, 0.5, 0.38)
  const doorFrameMaterial = rackMetalMaterial(0x242a30, 0.45, 0.4)
  const doorOpen = cab.door_state === 'open'

  // 机柜内部：后板、侧板、顶/底板，正面保持开放，形成真实机柜的黑色金属腔体
  addRackBox(group, CABINET_W * 0.9, CABINET_H * 0.92, 0.025, interiorMaterial, 0, CABINET_H / 2, -CABINET_D / 2 + 0.018)
  addRackBox(group, 0.025, CABINET_H * 0.92, CABINET_D * 0.88, shellMaterial, -CABINET_W / 2 + 0.015, CABINET_H / 2, 0)
  addRackBox(group, 0.025, CABINET_H * 0.92, CABINET_D * 0.88, shellMaterial, CABINET_W / 2 - 0.015, CABINET_H / 2, 0)
  addRackBox(group, CABINET_W * 0.92, 0.025, CABINET_D * 0.88, shellMaterial, 0, CABINET_H - 0.02, 0)
  addRackBox(group, CABINET_W * 0.92, 0.025, CABINET_D * 0.88, shellMaterial, 0, 0.025, 0)

  // 四根黑色金属立柱与前后横梁
  const post = new THREE.BoxGeometry(0.055, CABINET_H, 0.055)
  ;[-1, 1].forEach((sx) => {
    ;[-1, 1].forEach((sz) => {
      const mesh = new THREE.Mesh(post, frameMaterial)
      mesh.position.set(sx * (CABINET_W / 2 - 0.028), CABINET_H / 2, sz * (CABINET_D / 2 - 0.028))
      group.add(mesh)
    })
  })
  addRackBox(group, CABINET_W, 0.045, 0.045, railMaterial, 0, CABINET_H - 0.045, CABINET_D / 2 - 0.025)
  addRackBox(group, CABINET_W, 0.045, 0.045, railMaterial, 0, 0.045, CABINET_D / 2 - 0.025)
  addRackBox(group, CABINET_W, 0.045, 0.045, railMaterial, 0, CABINET_H - 0.045, -CABINET_D / 2 + 0.025)
  addRackBox(group, CABINET_W, 0.045, 0.045, railMaterial, 0, 0.045, -CABINET_D / 2 + 0.025)

  // 底座、调平脚与顶部承重框
  addRackBox(group, CABINET_W * 0.94, 0.06, CABINET_D * 0.9, railMaterial, 0, 0.06, 0)
  const footGeometry = new THREE.CylinderGeometry(0.042, 0.05, 0.08, 12)
  ;[-1, 1].forEach((sx) => {
    ;[-1, 1].forEach((sz) => {
      const foot = new THREE.Mesh(footGeometry, handleMaterial)
      foot.position.set(sx * (CABINET_W * 0.33), 0.04, sz * (CABINET_D * 0.33))
      group.add(foot)
    })
  })

  // 前门：深色冲孔网孔门 + 金属门框，替代原来的透明蓝色玻璃
  const doorPivot = new THREE.Group()
  doorPivot.position.set(-CABINET_W / 2 + 0.052, 0.02, CABINET_D / 2 + 0.035)
  doorPivot.rotation.y = doorOpen ? DOOR_OPEN_ANGLE : 0
  const doorWidth = CABINET_W * 0.89
  const doorHeight = CABINET_H * 0.87
  const doorPanel = new THREE.Mesh(
    new THREE.PlaneGeometry(doorWidth, doorHeight),
    new THREE.MeshStandardMaterial({
      map: makeRackDoorPatternTexture(),
      color: 0xffffff,
      metalness: 0.06,
      roughness: 0.82,
      transparent: false,
      side: THREE.DoubleSide,
    }),
  )
  doorPanel.material.envMapIntensity = 0.02
  doorPanel.position.set(doorWidth / 2, CABINET_H * 0.49, 0.006)
  doorPanel.userData.cabinetDoorId = cab.id
  doorPivot.add(doorPanel)

  addRackBox(doorPivot, 0.045, doorHeight + 0.06, 0.045, doorFrameMaterial, 0.02, CABINET_H * 0.49, 0.016)
  addRackBox(doorPivot, 0.045, doorHeight + 0.06, 0.045, doorFrameMaterial, doorWidth - 0.02, CABINET_H * 0.49, 0.016)
  addRackBox(doorPivot, doorWidth, 0.045, 0.045, doorFrameMaterial, doorWidth / 2, CABINET_H * 0.49 + doorHeight / 2 + 0.022, 0.016)
  addRackBox(doorPivot, doorWidth, 0.045, 0.045, doorFrameMaterial, doorWidth / 2, CABINET_H * 0.49 - doorHeight / 2 - 0.022, 0.016)
  addRackBox(doorPivot, 0.042, 0.36, 0.042, handleMaterial, doorWidth - 0.1, CABINET_H * 0.5, 0.055)
  addRackBox(doorPivot, 0.13, 0.042, 0.042, handleMaterial, doorWidth - 0.16, CABINET_H * 0.61, 0.055)
  addRackBox(doorPivot, doorWidth * 0.94, 0.012, 0.018, doorFrameMaterial, doorWidth / 2, CABINET_H * 0.3, 0.02)
  addRackBox(doorPivot, doorWidth * 0.94, 0.012, 0.018, doorFrameMaterial, doorWidth / 2, CABINET_H * 0.68, 0.02)
  const lock = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.025, 0.018, 16), handleMaterial)
  lock.rotation.x = Math.PI / 2
  lock.position.set(doorWidth - 0.1, CABINET_H * 0.43, 0.037)
  doorPivot.add(lock)
  doorPivot.traverse((node) => {
    if (node.isMesh) node.userData.cabinetDoorId = cab.id
  })

  group.add(doorPivot)
  group.userData.doorPivot = doorPivot
  group.userData.doorOpen = doorOpen

  // 机柜左侧状态灯带，只在金属框架上露出一条很细的彩色光
  const statusStrip = new THREE.Mesh(
    new THREE.BoxGeometry(0.012, CABINET_H * 0.66, 0.018),
    new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.9 }),
  )
  statusStrip.position.set(-CABINET_W / 2 + 0.045, CABINET_H * 0.5, CABINET_D / 2 + 0.08)
  group.add(statusStrip)
  group.userData.statusMaterial = statusStrip.material

  // 顶部风扇、后部走线槽与两侧散热孔，补足真实机柜的机械细节
  for (const sx of [-1, 1]) {
    const fan = new THREE.Mesh(
      new THREE.CylinderGeometry(0.15, 0.15, 0.022, 28),
      railMaterial,
    )
    fan.position.set(sx * CABINET_W * 0.22, CABINET_H + 0.022, -CABINET_D * 0.12)
    group.add(fan)
    const fanRing = new THREE.Mesh(
      new THREE.TorusGeometry(0.155, 0.012, 8, 32),
      handleMaterial,
    )
    fanRing.rotation.x = Math.PI / 2
    fanRing.position.copy(fan.position)
    group.add(fanRing)
    for (const sz of [-1, 1]) {
      for (let index = 0; index < 4; index += 1) {
        addRackBox(
          group,
          0.008,
          0.014,
          CABINET_D * 0.46,
          interiorMaterial,
          sx * (CABINET_W / 2 + 0.018),
          CABINET_H * 0.26 + index * 0.19,
          sz * CABINET_D * 0.16,
        )
      }
    }
  }
  addRackBox(group, CABINET_W * 0.82, 0.04, 0.16, railMaterial, 0, CABINET_H + 0.052, -CABINET_D * 0.33)

  // 前部 19 英寸安装立柱
  ;[-1, 1].forEach((side) => {
    addRackBox(group, 0.045, CABINET_H * 0.78, 0.035, railMaterial, side * CABINET_W * 0.36, CABINET_H * 0.5, CABINET_D / 2 - 0.115)
    for (let index = 0; index < 12; index += 1) {
      const hole = new THREE.Mesh(
        new THREE.BoxGeometry(0.018, 0.018, 0.014),
        interiorMaterial,
      )
      hole.position.set(side * CABINET_W * 0.36, 0.28 + index * 0.15, CABINET_D / 2 - 0.132)
      group.add(hole)
    }
  })

  const topLed = new THREE.Mesh(
    new THREE.BoxGeometry(CABINET_W * 0.58, 0.022, 0.018),
    new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.8 }),
  )
  topLed.position.set(0, CABINET_H + 0.012, CABINET_D / 2 - 0.04)
  group.add(topLed)

  const deviceMetal = rackMetalMaterial(0x181d22, 0.36, 0.48)
  const ventMetal = rackMetalMaterial(0x050607, 0.3, 0.76)
  const unit = CABINET_H / Math.max(Number(cab.u_capacity) || 42, 1)
  ;(cab.devices || []).forEach((device) => {
    const start = Math.max(1, Number(device.u_position) || 1)
    const heightU = Math.max(1, Number(device.u_height) || 1)
    const deviceHeight = Math.min(CABINET_H * 0.82, heightU * unit * 0.86)
    const centerY = (start - 1 + heightU / 2) * unit
    const deviceColor = { online: 0x22c55e, warning: 0xf59e0b, offline: 0xef4444, unknown: 0x64748b }[device.status] || 0x64748b
    const deviceInfo = { ...device, cabinetName: cab.name }
    const panelZ = CABINET_D / 2 - 0.13
    const face = new THREE.Mesh(
      new THREE.BoxGeometry(CABINET_W * 0.76, deviceHeight, 0.04),
      deviceMetal,
    )
    face.position.set(0, centerY, panelZ)
    face.userData.deviceId = device.id
    face.userData.device = deviceInfo
    group.add(face)

    ;[-1, 1].forEach((side) => {
      const ear = new THREE.Mesh(
        new THREE.BoxGeometry(0.035, deviceHeight, 0.055),
        handleMaterial,
      )
      ear.position.set(side * (CABINET_W * 0.395), centerY, panelZ + 0.018)
      group.add(ear)
    })
    const ventCount = deviceHeight > 0.24 ? 4 : 2
    for (let index = 0; index < ventCount; index += 1) {
      const vent = new THREE.Mesh(
        new THREE.BoxGeometry(CABINET_W * 0.55, 0.007, 0.008),
        ventMetal,
      )
      vent.position.set(-CABINET_W * 0.04, centerY - deviceHeight * 0.28 + index * (deviceHeight * 0.16), panelZ + 0.024)
      group.add(vent)
    }
    const led = new THREE.Mesh(
      new THREE.BoxGeometry(0.022, 0.014, 0.012),
      new THREE.MeshBasicMaterial({ color: deviceColor }),
    )
    led.position.set(CABINET_W * 0.32, centerY + deviceHeight * 0.26, panelZ + 0.028)
    group.add(led)
    const ledStrip = new THREE.Mesh(
      new THREE.BoxGeometry(CABINET_W * 0.6, 0.009, 0.008),
      new THREE.MeshBasicMaterial({ color: deviceColor, transparent: true, opacity: 0.72 }),
    )
    ledStrip.position.set(0, centerY - deviceHeight * 0.39, panelZ + 0.027)
    group.add(ledStrip)

    const tag = makeDeviceTag(device, start, heightU, centerY, unit)
    tag.userData.deviceId = device.id
    tag.userData.device = deviceInfo
    group.add(tag)
  })

  group.add(makeURuler(cab))

  const label = makeCabinetLabel(cab.name, `#${color.toString(16).padStart(6, '0')}`, cab)
  label.position.set(0, CABINET_H + 0.38, 0)
  group.add(label)
  return group
}

function buildThreeScene() {
  if (!threeRef.value) return
  if (!threeRenderer) initThree()
  if (!threeScene) return
  if (worldGroup) {
    threeScene.remove(worldGroup)
    disposeObject(worldGroup)
  }
  worldGroup = new THREE.Group()
  threeScene.add(worldGroup)
  cabinetObjectMap.clear()
  cabinetDoorMap.clear()

  const rowData = cabinetRows.value
  const maxCols = Math.max(...rowData.map((row) => row.items.length), 1)
  const spacingX = 1.75
  const spacingZ = 2.45
  const roomWidth = Math.max(Number(room.value?.width_m) || 9, 7, (maxCols - 1) * spacingX + 2.4)
  const roomDepth = Math.max(Number(room.value?.length_m) || 12, 8, (rowData.length - 1) * spacingZ + 2.4)
  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(roomWidth, roomDepth),
    new THREE.MeshStandardMaterial({ color: 0x0d1014, roughness: 0.86, metalness: 0.18 }),
  )
  floor.rotation.x = -Math.PI / 2
  worldGroup.add(floor)
  const grid = new THREE.GridHelper(Math.max(roomWidth, roomDepth), 28, 0x3a4854, 0x1e272e)
  grid.position.y = 0.012
  worldGroup.add(grid)
  const border = new THREE.LineSegments(
    new THREE.EdgesGeometry(new THREE.BoxGeometry(roomWidth, 0.06, roomDepth)),
    new THREE.LineBasicMaterial({ color: 0x4b5b66, transparent: true, opacity: 0.62 }),
  )
  border.position.y = 0.035
  worldGroup.add(border)

  const rows = rowData
  rows.forEach((row, rowIndex) => {
    row.items.forEach((cab, colIndex) => {
      const x = (colIndex - (row.items.length - 1) / 2) * spacingX
      const z = (rowIndex - (rows.length - 1) / 2) * spacingZ
      const cabinet = buildCabinet(cab, x, z)
      worldGroup.add(cabinet)
      cabinetObjectMap.set(cab.id, cabinet)
      cabinetDoorMap.set(cab.id, {
        pivot: cabinet.userData.doorPivot,
        target: cab.door_state === 'open' ? DOOR_OPEN_ANGLE : 0,
      })
    })
  })

  for (let i = 0; i < Math.max(rows.length - 1, 1); i += 1) {
    const z = (i - (rows.length - 2) / 2) * spacingZ
    const strip = new THREE.Mesh(
      new THREE.BoxGeometry(Math.max(roomWidth * 0.55, 4), 0.018, 0.035),
      new THREE.MeshBasicMaterial({ color: 0x9ec7d6, transparent: true, opacity: 0.18 }),
    )
    strip.position.set(0, 0.025, z)
    worldGroup.add(strip)
  }

  const restoredView = restoreThreeView()
  if (!restoredView && !manualAdjust.value && !viewCustomized) {
    fitThreeView()
    // 首屏画布尺寸/标签布局稳定后再校准一次，避免初始机柜阵列偏左或偏低
    requestAnimationFrame(() => {
      if (!manualAdjust.value && !viewCustomized) fitThreeView()
    })
    if (threeFitTimer) clearTimeout(threeFitTimer)
    threeFitTimer = setTimeout(() => {
      if (!manualAdjust.value && !viewCustomized) fitThreeView()
    }, 360)
  }
  updateCabinetSelection()
}

function fitThreeView() {
  if (!threeCamera || !threeControls || !worldGroup) return
  // 只以机柜/设备实体取景，排除悬浮标签和规则线，确保视口中心是机柜阵列本身
  const cabinetBox = new THREE.Box3()
  const displayBox = new THREE.Box3()
  cabinetObjectMap.forEach((group) => {
    displayBox.expandByObject(group)
    // 用柜体本身的尺寸和位置取景，不把打开的门板、悬浮标签算进中心
    const p = group.position
    cabinetBox.expandByPoint(new THREE.Vector3(
      p.x - CABINET_W / 2,
      0,
      p.z - CABINET_D / 2,
    ))
    cabinetBox.expandByPoint(new THREE.Vector3(
      p.x + CABINET_W / 2,
      CABINET_H,
      p.z + CABINET_D / 2,
    ))
  })
  const box = cabinetBox.isEmpty() ? displayBox : cabinetBox
  const center = box.getCenter(new THREE.Vector3())
  const contentBox = displayBox.isEmpty() ? cabinetBox.clone() : displayBox.clone().union(cabinetBox)
  const corners = [
    new THREE.Vector3(contentBox.min.x, contentBox.min.y, contentBox.min.z),
    new THREE.Vector3(contentBox.min.x, contentBox.min.y, contentBox.max.z),
    new THREE.Vector3(contentBox.min.x, contentBox.max.y, contentBox.min.z),
    new THREE.Vector3(contentBox.min.x, contentBox.max.y, contentBox.max.z),
    new THREE.Vector3(contentBox.max.x, contentBox.min.y, contentBox.min.z),
    new THREE.Vector3(contentBox.max.x, contentBox.min.y, contentBox.max.z),
    new THREE.Vector3(contentBox.max.x, contentBox.max.y, contentBox.min.z),
    new THREE.Vector3(contentBox.max.x, contentBox.max.y, contentBox.max.z),
  ]
  const radius = Math.max(
    ...corners.map((corner) => center.distanceTo(corner)),
    3.6,
  )
  const aspect = Math.max(threeCamera.aspect || 1, 0.6)
  const verticalFov = THREE.MathUtils.degToRad(threeCamera.fov)
  const horizontalFov = 2 * Math.atan(Math.tan(verticalFov / 2) * aspect)
  // 视锥内接包围球所需距离；留少量安全边距，尽量让机柜阵列铺满可视区域
  const distance = Math.max(
    radius / Math.sin(verticalFov / 2),
    radius / Math.sin(horizontalFov / 2),
  ) * 1.0
  threeFitDistance = distance
  const direction = new THREE.Vector3(0.22, 0.3, 1).normalize()
  threeCamera.position.copy(center).addScaledVector(direction, distance)
  threeCamera.near = Math.max(0.05, distance / 100)
  threeCamera.far = Math.max(200, distance * 2.5)
  threeCamera.updateProjectionMatrix()
  threeCenter.copy(center)
  threeControls.target.copy(center)
  threeCamera.lookAt(center)
  threeControls.update()
  viewCustomized = false
}

function resetThreeView() {
  manualAdjust.value = false
  viewCustomized = false
  clearThreeView()
  fitThreeView()
}

const THREE_VIEW_DIRECTIONS = {
  overview: [0.22, 0.3, 1],
  top: [0, 1, 0.08],
  front: [0, 0.16, 1],
  side: [1, 0.16, 0],
  back: [-1, 0.16, 0],
}

function applyThreePreset(name) {
  if (!threeCamera || !threeControls) return
  const direction = THREE_VIEW_DIRECTIONS[name]
  if (!direction) return
  const target = threeControls.target.clone()
  const currentDistance = threeCamera.position.distanceTo(target)
  const distance = Number.isFinite(currentDistance) && currentDistance > 1 ? currentDistance : threeFitDistance
  threeCamera.position.copy(target).addScaledVector(
    new THREE.Vector3(...direction).normalize(),
    distance,
  )
  threeControls.target.copy(target)
  threeCamera.lookAt(target)
  threeControls.update()
  viewCustomized = true
}

function applyManualAdjust(enabled) {
  if (!threeControls) return
  threeControls.enablePan = enabled
  threeControls.enableRotate = true
  threeControls.enableZoom = true
  threeControls.mouseButtons.LEFT = enabled ? THREE.MOUSE.PAN : THREE.MOUSE.ROTATE
  threeControls.mouseButtons.RIGHT = enabled ? THREE.MOUSE.ROTATE : THREE.MOUSE.PAN
  if (threeRenderer) threeRenderer.domElement.style.cursor = enabled ? 'grab' : 'default'
  if (!enabled) {
    // 关闭拖动定位时只保存当前相机位置，不再自动 fit 回初始视角
    saveThreeView()
  }
}

function updateCabinetSelection() {
  if (!selectionRing) return
  cabinetObjectMap.forEach((group, id) => {
    const selected = id === selectedCabinetId.value
    group.scale.setScalar(selected ? 1.025 : 1)
    if (group.userData.frameMaterial) {
      group.userData.frameMaterial.emissiveIntensity = selected ? 0.55 : 0.018
    }
  })
  const selectedGroup = cabinetObjectMap.get(selectedCabinetId.value)
  if (selectedGroup) {
    selectionRing.position.x = selectedGroup.position.x
    selectionRing.position.z = selectedGroup.position.z
    selectionRing.material.opacity = 0.9
  } else {
    selectionRing.material.opacity = 0
  }
}

function findCabinetDoorNode(object) {
  let node = object
  while (node && node !== worldGroup) {
    if (node.userData?.cabinetDoorId) return node
    node = node.parent
  }
  return null
}

function findDeviceNode(object) {
  let node = object
  while (node && node !== worldGroup) {
    if (node.userData?.deviceId) return node
    node = node.parent
  }
  return null
}

function openDeviceDetail(deviceId) {
  if (!deviceId) return
  hoverDevice.value = null
  router.push(`/devices/${deviceId}`)
}

function onThreePointerMove(event) {
  if (!threeRenderer || !threeCamera || !worldGroup) return
  const now = performance.now()
  if (now - lastHoverAt < 45) return
  lastHoverAt = now
  const rect = threeRenderer.domElement.getBoundingClientRect()
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
  raycaster.setFromCamera(pointer, threeCamera)
  const hits = raycaster.intersectObjects(worldGroup.children, true)
  let deviceNode = null
  for (const hit of hits) {
    if (findCabinetDoorNode(hit.object)) {
      hoverDevice.value = null
      threeRenderer.domElement.style.cursor = 'pointer'
      return
    }
    deviceNode = findDeviceNode(hit.object)
    if (deviceNode) break
  }
  if (!deviceNode) {
    hoverDevice.value = null
    threeRenderer.domElement.style.cursor = manualAdjust.value ? 'grab' : 'default'
    return
  }
  hoverDevice.value = deviceNode.userData.device
  const sceneRect = threeRef.value?.getBoundingClientRect() || rect
  hoverPosition.value = {
    x: Math.max(12, Math.min(sceneRect.width - 286, event.clientX - sceneRect.left + 18)),
    y: Math.max(12, Math.min(sceneRect.height - 190, event.clientY - sceneRect.top + 18)),
  }
  threeRenderer.domElement.style.cursor = 'pointer'
}

function onThreePointerLeave() {
  hoverDevice.value = null
  if (threeRenderer) threeRenderer.domElement.style.cursor = manualAdjust.value ? 'grab' : 'default'
}

function onThreeClick(event) {
  if (!threeRenderer || !threeCamera || !worldGroup) return
  const rect = threeRenderer.domElement.getBoundingClientRect()
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
  raycaster.setFromCamera(pointer, threeCamera)
  const hits = raycaster.intersectObjects(worldGroup.children, true)
  for (const hit of hits) {
    const doorNode = findCabinetDoorNode(hit.object)
    if (doorNode) {
      const cabinet = cabinets.value.find((item) => item.id === doorNode.userData.cabinetDoorId)
      if (!cabinet) return
      selectedCabinetId.value = cabinet.id
      if (canEditRoom.value && !doorBusy.value) toggleCabinetDoor(cabinet)
      return
    }
    const deviceNode = findDeviceNode(hit.object)
    if (deviceNode) {
      openDeviceDetail(deviceNode.userData.deviceId)
      return
    }
  }
  for (const hit of hits) {
    let node = hit.object
    while (node && !node.userData?.cabinetId) node = node.parent
    if (node?.userData?.cabinetId) {
      selectedCabinetId.value = node.userData.cabinetId
      break
    }
  }
}

function animateThree() {
  threeAnimation = requestAnimationFrame(animateThree)
  if (!threeRenderer || !threeScene || !threeCamera) return
  if (threeControls) {
    // 自动旋转默认围绕机柜阵列中心；用户已手动定位时保留其 target，避免关闭拖动后跳回
    if (autoRotate.value && !manualAdjust.value && !viewCustomized) {
      threeControls.target.copy(threeCenter)
    }
    threeControls.autoRotate = autoRotate.value
    threeControls.update()
    if (autoRotate.value && !manualAdjust.value && !viewCustomized) {
      threeCamera.lookAt(threeCenter)
    }
  }
  cabinetDoorMap.forEach((entry) => {
    if (!entry.pivot) return
    const delta = entry.target - entry.pivot.rotation.y
    if (Math.abs(delta) > 0.001) entry.pivot.rotation.y += delta * 0.14
    else entry.pivot.rotation.y = entry.target
  })
  threeRenderer.render(threeScene, threeCamera)
}

async function toggleCabinetDoor(cabinet) {
  if (!cabinet || !canEditRoom.value || doorBusy.value) return
  const nextState = cabinet.door_state === 'open' ? 'closed' : 'open'
  doorBusy.value = true
  try {
    const { data } = await roomApi.setDoor(cabinet.id, nextState)
    cabinet.door_state = data.door_state || nextState
    const entry = cabinetDoorMap.get(cabinet.id)
    if (entry) entry.target = cabinet.door_state === 'open' ? DOOR_OPEN_ANGLE : 0
    ElMessage.success(cabinet.door_state === 'open' ? '机柜门已打开' : '机柜门已关闭')
  } catch (error) {
    ElMessage.error(error.message || '机柜门操作失败')
  } finally {
    doorBusy.value = false
  }
}

function toggleSelectedDoor() {
  return toggleCabinetDoor(selectedCabinet.value)
}

async function openDevicePlacement() {
  if (!selectedCabinet.value) return
  placementForm.value = {
    mode: 'existing',
    device_id: null,
    name: '',
    ip_address: '',
    device_type: 'server',
    vendor: '',
    u_position: null,
    u_height: 1,
    power_watts: 0,
  }
  try {
    const { data } = await assetApi.getList({ page: 1, size: 100 })
    const items = data.items || []
    availableDevices.value = items.filter((device) => (
      !device.cabinet_id || device.cabinet_id === selectedCabinet.value.id
    ))
  } catch (error) {
    availableDevices.value = []
    ElMessage.error(error.message || '加载设备列表失败')
    return
  }
  placementVisible.value = true
}

function onPlacementDeviceChange(deviceId) {
  const device = availableDevices.value.find((item) => item.id === deviceId)
  if (!device) return
  placementForm.value.u_position = device.u_position || null
  placementForm.value.u_height = device.u_height || 1
  placementForm.value.power_watts = device.power_watts || 0
}

async function savePlacement() {
  if (!selectedCabinet.value) return
  if (placementForm.value.mode === 'existing' && !placementForm.value.device_id) {
    ElMessage.warning('请选择设备')
    return
  }
  if (placementForm.value.mode === 'new') {
    if (!placementForm.value.name.trim() || !placementForm.value.ip_address.trim()) {
      ElMessage.warning('请填写设备名称和 IP 地址')
      return
    }
    if (!/^(\d{1,3}\.){3}\d{1,3}$/.test(placementForm.value.ip_address.trim())) {
      ElMessage.warning('请输入合法的 IPv4 地址')
      return
    }
  }
  placementSaving.value = true
  try {
    if (placementForm.value.mode === 'new') {
      await assetApi.create({
        name: placementForm.value.name.trim(),
        ip_address: placementForm.value.ip_address.trim(),
        device_type: placementForm.value.device_type,
        vendor: placementForm.value.vendor.trim(),
        cabinet_id: selectedCabinet.value.id,
        u_position: placementForm.value.u_position,
        u_height: placementForm.value.u_height,
        power_watts: placementForm.value.power_watts,
        snmp_version: 'v2c',
        community: 'public',
        port: 161,
        is_enabled: true,
      })
    } else {
      await assetApi.update(placementForm.value.device_id, {
        cabinet_id: selectedCabinet.value.id,
        u_position: placementForm.value.u_position,
        u_height: placementForm.value.u_height,
        power_watts: placementForm.value.power_watts,
      })
    }
    placementVisible.value = false
    ElMessage.success('设备上架信息已保存')
    await refresh()
  } catch (error) {
    ElMessage.error(error.message || '保存上架信息失败')
  } finally {
    placementSaving.value = false
  }
}

function formatTime(value) {
  return formatHM(value)
}

const clockText = computed(() => now.value.toLocaleString('zh-CN', {
  hour12: false,
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
}))

async function refresh() {
  loading.value = true
  try {
    const id = Number(route.params.id)
    const [layoutRes, sensorRes, alertRes, roomsRes] = await Promise.allSettled([
      roomApi.layout(id),
      roomApi.sensorSummary(id),
      monitorApi.getUnackAlerts(),
      roomApi.list(),
    ])
    if (layoutRes.status === 'fulfilled') {
      room.value = layoutRes.value.data.room
      cabinets.value = layoutRes.value.data.cabinets || []
      if (!cabinets.value.some((cab) => cab.id === selectedCabinetId.value)) selectedCabinetId.value = null
    }
    if (sensorRes.status === 'fulfilled') {
      const data = sensorRes.value.data || {}
      sensorSummary.value = {
        sensors: data.sensors || [],
        temperature_avg: data.temperature_avg,
        humidity_avg: data.humidity_avg,
        alarm_count: data.alarm_count || 0,
      }
    }
    if (alertRes.status === 'fulfilled') alerts.value = alertRes.value.data || []
    if (roomsRes.status === 'fulfilled') {
      const data = roomsRes.value.data
      rooms.value = Array.isArray(data) ? data : (data?.items || [])
    }
  } finally {
    loading.value = false
  }
  await nextTick()
  const signature = JSON.stringify({
    room: room.value?.id,
    cabinets: cabinets.value.map((cab) => ({
      id: cab.id,
      name: cab.name,
      status: cabinetStatus(cab),
      row: cab.row_index,
      col: cab.col_index,
      u: cab.u_capacity,
      usedU: cab.usage?.used_u,
      powerW: cab.usage?.used_power_w,
      powerCapacity: cab.usage?.power_capacity_w,
      devices: (cab.devices || []).map((device) => ({
        id: device.id,
        name: device.name,
        status: device.status,
        u: device.u_position,
        h: device.u_height,
        power: device.power_watts,
      })),
    })),
  })
  if (!worldGroup || signature !== threeSignature) {
    threeSignature = signature
    buildThreeScene()
  }
}

function switchRoom(id) {
  router.replace(`/rooms/${id}/showcase`)
}

async function toggleFullscreen() {
  try {
    if (!document.fullscreenElement) await showcaseRef.value?.requestFullscreen()
    else await document.exitFullscreen()
  } catch {
    /* 忽略 */
  }
}

function handleFullscreenChange() {
  isFullscreen.value = !!document.fullscreenElement
  setTimeout(resizeThreeViewport, 180)
}

onMounted(async () => {
  await nextTick()
  initThree()
  refresh()
  clockTimer = setInterval(() => { now.value = new Date() }, 1000)
  refreshTimer = setInterval(refresh, refreshMs())
  document.addEventListener('fullscreenchange', handleFullscreenChange)
})

onBeforeUnmount(() => {
  saveThreeView()
  if (refreshTimer) clearInterval(refreshTimer)
  if (clockTimer) clearInterval(clockTimer)
  if (threeFitTimer) clearTimeout(threeFitTimer)
  document.removeEventListener('fullscreenchange', handleFullscreenChange)
  if (threeAnimation) cancelAnimationFrame(threeAnimation)
  threeResizeObserver?.disconnect()
  window.removeEventListener('resize', resizeThreeViewport)
  threeRenderer?.domElement?.removeEventListener('click', onThreeClick)
  threeRenderer?.domElement?.removeEventListener('pointermove', onThreePointerMove)
  threeRenderer?.domElement?.removeEventListener('pointerleave', onThreePointerLeave)
  if (worldGroup && threeScene) {
    threeScene.remove(worldGroup)
    disposeObject(worldGroup)
  }
  threeRenderer?.dispose()
  threeRenderer?.domElement?.remove()
  threeRenderer = null
  threeScene = null
  threeCamera = null
  threeControls = null
})

watch(() => route.params.id, (id) => {
  saveThreeView()
  currentRoomId.value = Number(id)
  selectedCabinetId.value = null
  manualAdjust.value = false
  viewCustomized = false
  refresh()
})

watch(selectedCabinetId, () => {
  updateCabinetSelection()
})

watch(autoRotate, (value) => {
  if (threeControls) threeControls.autoRotate = value
})

watch(manualAdjust, applyManualAdjust)
</script>

<style scoped>
.room-showcase {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  color: #dceaf5;
  background:
    radial-gradient(ellipse at 20% 30%, rgba(0, 140, 255, 0.08), transparent 55%),
    radial-gradient(ellipse at 85% 10%, rgba(123, 97, 255, 0.06), transparent 45%),
    #050a13;
  font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
}

.rs-bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0.45;
  background-image:
    linear-gradient(rgba(0, 245, 255, 0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 245, 255, 0.035) 1px, transparent 1px);
  background-size: 34px 34px;
  mask-image: radial-gradient(ellipse at 50% 45%, #000 10%, transparent 82%);
}

.rs-header {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex-shrink: 0;
  min-height: 60px;
  padding: 8px 18px;
  border-bottom: 1px solid rgba(0, 245, 255, 0.14);
  background: rgba(4, 12, 23, 0.82);
}

.rs-header-left,
.rs-header-right,
.rs-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.rs-back {
  color: #8ca6bb;
}

.rs-room-switch {
  width: 170px;
}

.rs-room-switch :deep(.el-select__wrapper) {
  background: rgba(8, 27, 47, 0.8);
  box-shadow: 0 0 0 1px rgba(56, 189, 248, 0.18) inset;
}

.rs-title h1 {
  margin: 0;
  color: #e3f7ff;
  font-size: 20px;
  font-weight: 600;
  letter-spacing: 4px;
  text-shadow: 0 0 20px rgba(0, 245, 255, 0.35);
}

.rs-title-mark {
  color: #00e5ff;
  font-size: 10px;
  opacity: 0.8;
}

.rs-clock {
  color: #8ca6bb;
  font-family: Consolas, monospace;
  font-size: 11px;
}

.rs-live {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: #00ffb3;
  font-family: Consolas, monospace;
  font-size: 10px;
}

.rs-live i {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #00ffb3;
  box-shadow: 0 0 8px #00ffb3;
}

.rs-header-right :deep(.el-button) {
  border-color: rgba(0, 245, 255, 0.18);
  background: rgba(8, 27, 47, 0.72);
  color: #7dd3fc;
}

.rs-metrics {
  position: relative;
  z-index: 2;
  display: grid;
  grid-template-columns: repeat(8, minmax(0, 1fr));
  gap: 8px;
  padding: 9px 16px;
  flex-shrink: 0;
}

.rs-metric {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 8px 10px;
  border: 1px solid rgba(56, 189, 248, 0.12);
  border-radius: 10px;
  background: rgba(7, 22, 39, 0.72);
  overflow: hidden;
}

.rs-metric::after {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  width: 2px;
  height: 100%;
  background: #38bdf8;
  opacity: 0.55;
}

.rs-metric.success::after { background: #00e0a1; }
.rs-metric.warning::after { background: #fbbf24; }
.rs-metric.danger::after { background: #fb7185; }

.rs-metric-icon {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(56, 189, 248, 0.14);
  border-radius: 7px;
  color: #38bdf8;
  background: rgba(14, 165, 233, 0.1);
}

.rs-metric span {
  display: block;
  color: #637f96;
  font-size: 9px;
  white-space: nowrap;
}

.rs-metric strong {
  display: block;
  margin-top: 1px;
  color: #dff8ff;
  font-family: Consolas, monospace;
  font-size: 17px;
  line-height: 1.1;
  white-space: nowrap;
}

.rs-metric small {
  position: absolute;
  right: 6px;
  bottom: 4px;
  color: #314b60;
  font-family: Consolas, monospace;
  font-size: 7px;
  letter-spacing: 0.5px;
}

.rs-main {
  position: relative;
  z-index: 1;
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(210px, 18%) minmax(0, 1fr) minmax(210px, 18%);
  gap: 10px;
  padding: 0 16px 10px;
  overflow: hidden;
}

.rs-side {
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow-y: auto;
}

.rs-panel {
  min-height: 0;
  overflow: hidden;
  flex-shrink: 0;
  border: 1px solid rgba(56, 189, 248, 0.13);
  border-radius: 12px;
  background: rgba(7, 20, 36, 0.78);
  box-shadow: 0 8px 26px rgba(0, 0, 0, 0.2);
}

.rs-panel-grow {
  flex: 1;
}

.rs-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 11px;
  border-bottom: 1px solid rgba(56, 189, 248, 0.1);
  background: linear-gradient(90deg, rgba(0, 245, 255, 0.06), transparent);
}

.rs-panel-head span {
  color: #bce9f8;
  font-size: 11px;
  letter-spacing: 0.5px;
}

.rs-panel-head small {
  color: #345c75;
  font-family: Consolas, monospace;
  font-size: 8px;
  letter-spacing: 1px;
}

.rs-gauges {
  display: flex;
  justify-content: center;
  gap: 12px;
  padding: 12px 8px 8px;
}

.rs-gauge-ring {
  position: relative;
  width: 82px;
  height: 82px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: conic-gradient(var(--gauge-color) var(--gauge), rgba(31, 59, 79, 0.5) 0);
  box-shadow: 0 0 18px rgba(56, 189, 248, 0.12);
}

.rs-gauge-ring::before {
  content: '';
  position: absolute;
  inset: 6px;
  border-radius: 50%;
  background: #071525;
}

.rs-gauge-ring > div {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: baseline;
  justify-content: center;
  flex-wrap: wrap;
  width: 60px;
  text-align: center;
}

.rs-gauge-ring strong {
  color: #e5fbff;
  font-family: Consolas, monospace;
  font-size: 18px;
}

.rs-gauge-ring small {
  color: #7dd3fc;
  font-size: 8px;
}

.rs-gauge-ring span {
  flex-basis: 100%;
  color: #55748a;
  font-size: 8px;
}

.rs-mini-metrics {
  display: flex;
  border-top: 1px solid rgba(56, 189, 248, 0.08);
}

.rs-mini-metrics div {
  flex: 1;
  padding: 7px 4px;
  text-align: center;
  border-right: 1px solid rgba(56, 189, 248, 0.08);
}

.rs-mini-metrics div:last-child { border-right: none; }
.rs-mini-metrics span { display: block; color: #536e82; font-size: 8px; }
.rs-mini-metrics b { display: block; margin-top: 2px; color: #dff8ff; font-family: Consolas, monospace; font-size: 13px; }
.rs-mini-metrics b.warning { color: #fbbf24; }
.rs-mini-metrics b.danger { color: #fb7185; }

.rs-env {
  display: flex;
  gap: 8px;
  padding: 10px;
}

.rs-env-item {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 8px;
  border-radius: 7px;
  background: rgba(15, 37, 56, 0.65);
}

.rs-env-item .el-icon { color: #ffab4a; font-size: 18px; }
.rs-env-item.humidity .el-icon { color: #38bdf8; }
.rs-env-item small { display: block; color: #55748a; font-size: 8px; }
.rs-env-item strong { display: block; color: #e0f9ff; font-family: Consolas, monospace; font-size: 16px; }
.rs-env-item i { margin-left: 2px; color: #6f93a9; font-size: 8px; font-style: normal; }

.rs-sensor-list {
  padding: 0 10px 10px;
  overflow: auto;
}

.rs-sensor-row {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 2px;
  border-bottom: 1px solid rgba(56, 189, 248, 0.06);
}

.rs-sensor-row > span,
.rs-device-row > span {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #00e0a1;
}

.rs-sensor-row > span.warning,
.rs-device-row > span.warning { background: #fbbf24; }
.rs-sensor-row > span.danger,
.rs-device-row > span.offline { background: #fb7185; }
.rs-sensor-row b { color: #a7c7d8; font-size: 9px; font-weight: 400; }
.rs-sensor-row small { margin-left: auto; color: #5b7b8f; font-family: Consolas, monospace; font-size: 8px; }

.rs-scene-panel {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid rgba(56, 189, 248, 0.16);
  border-radius: 13px;
  background: rgba(4, 15, 27, 0.5);
}

.rs-scene-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 9px 14px;
  flex-shrink: 0;
  border-bottom: 1px solid rgba(56, 189, 248, 0.1);
}

.rs-scene-kicker {
  color: #00c8e8;
  font-family: Consolas, monospace;
  font-size: 7px;
  letter-spacing: 1.5px;
}

.rs-scene-head h2 {
  margin: 2px 0 0;
  color: #dff8ff;
  font-size: 13px;
  font-weight: 500;
  letter-spacing: 1px;
}

.rs-scene-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 9px;
  color: #607f93;
  font-size: 8px;
}

.rs-scene-legend span { display: inline-flex; align-items: center; gap: 3px; }
.rs-scene-legend i { width: 5px; height: 5px; border-radius: 50%; background: #00e0a1; }
.rs-scene-legend i.warning { background: #fbbf24; }
.rs-scene-legend i.offline { background: #fb7185; }
.rs-scene-legend i.unknown { background: #4f6b7d; }

.rs-scene {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  background:
    radial-gradient(ellipse at 50% 45%, rgba(14, 94, 130, 0.2), transparent 60%),
    #050d18;
}

.rs-three-canvas {
  position: absolute;
  inset: 0;
  z-index: 1;
}

.rs-three-dom {
  display: block;
  width: 100%;
  height: 100%;
}

.rs-scene-topline {
  position: absolute;
  left: 14px;
  right: 14px;
  top: 10px;
  z-index: 4;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  pointer-events: none;
}

.rs-room-label {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 5px 9px;
  border: 1px solid rgba(56, 189, 248, 0.14);
  border-radius: 7px;
  background: rgba(5, 16, 28, 0.72);
  backdrop-filter: blur(6px);
}

.rs-room-label b { color: #b9e9f8; font-size: 10px; }
.rs-room-label span { color: #4f7188; font-size: 8px; }

.rs-three-controls {
  display: flex;
  align-items: center;
  gap: 7px;
  pointer-events: auto;
  padding: 5px 8px;
  border: 1px solid rgba(56, 189, 248, 0.14);
  border-radius: 7px;
  background: rgba(5, 16, 28, 0.78);
  backdrop-filter: blur(6px);
}

.rs-three-controls :deep(.el-switch__label) {
  color: #8db3c5;
  font-size: 9px;
}

.rs-three-controls .el-button {
  margin: 0;
  border-color: rgba(56, 189, 248, 0.18);
  background: rgba(10, 31, 49, 0.82);
  color: #8fc7dd;
  font-size: 10px;
}

.rs-device-tooltip {
  position: absolute;
  z-index: 8;
  width: 268px;
  padding: 10px 12px;
  border: 1px solid rgba(56, 189, 248, 0.6);
  border-radius: 8px;
  background: rgba(4, 16, 28, 0.96);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45), 0 0 20px rgba(14, 165, 233, 0.12);
  pointer-events: none;
  backdrop-filter: blur(8px);
}

.rs-tip-head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding-bottom: 7px;
  margin-bottom: 6px;
  border-bottom: 1px solid rgba(56, 189, 248, 0.16);
}

.rs-tip-head > i {
  width: 6px;
  height: 6px;
  flex-shrink: 0;
  border-radius: 50%;
  background: #64748b;
}

.rs-tip-head > i.online { background: #00e0a1; box-shadow: 0 0 6px #00e0a1; }
.rs-tip-head > i.warning { background: #fbbf24; box-shadow: 0 0 6px #fbbf24; }
.rs-tip-head > i.offline { background: #fb7185; box-shadow: 0 0 6px #fb7185; }
.rs-tip-head strong { flex: 1; color: #e0f7ff; font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.rs-tip-line {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 2px 0;
  font-size: 9px;
}

.rs-tip-line span { color: #5b7b8f; flex-shrink: 0; }
.rs-tip-line b { color: #a7c7d8; font-weight: 400; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rs-tip-action { margin-top: 6px; padding-top: 6px; border-top: 1px solid rgba(56, 189, 248, 0.12); color: #38bdf8; font-size: 9px; text-align: right; }

.rs-device-row-clickable { cursor: pointer; border-radius: 3px; }
.rs-device-row-clickable:hover { background: rgba(56, 189, 248, 0.08); }

.rs-drag-hint {
  position: absolute;
  top: 54px;
  left: 50%;
  z-index: 4;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 9px;
  border: 1px solid rgba(45, 212, 191, 0.22);
  border-radius: 6px;
  color: #87e8dc;
  background: rgba(4, 22, 32, 0.78);
  font-size: 9px;
  white-space: nowrap;
  pointer-events: none;
}

.rs-scene-footer {
  position: absolute;
  bottom: 10px;
  left: 50%;
  z-index: 4;
  transform: translateX(-50%);
  display: flex;
  justify-content: center;
  gap: 26px;
  padding: 6px 13px;
  border: 1px solid rgba(56, 189, 248, 0.13);
  border-radius: 7px;
  background: rgba(5, 16, 28, 0.8);
  backdrop-filter: blur(6px);
  white-space: nowrap;
}

.rs-scene-footer span {
  display: flex;
  align-items: baseline;
  gap: 5px;
}

.rs-scene-footer small { color: #4d6e82; font-size: 8px; }
.rs-scene-footer b { color: #bce9f8; font-family: Consolas, monospace; font-size: 12px; }
.rs-scene-footer b.warning { color: #fbbf24; }

.rs-three-empty {
  position: absolute;
  inset: 0;
  z-index: 3;
  background: rgba(5, 13, 24, 0.55);
}

.rs-place-device {
  width: 100%;
  margin-top: 9px;
}

.rs-place-hint {
  margin-top: 3px;
  color: #6d8b9e;
  font-size: 9px;
  line-height: 1.5;
}

.rs-u-auto-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.rs-u-auto-row .el-button {
  flex-shrink: 0;
  font-size: 11px;
}

.rs-racks {
  position: relative;
  z-index: 1;
  min-width: max-content;
  min-height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 28px;
  margin: 0 auto;
  padding: 9px 0;
}

.rs-rack-row {
  display: flex;
  align-items: flex-end;
  gap: 10px;
}

.rs-row-label {
  width: 30px;
  color: #47738c;
  font-family: Consolas, monospace;
  font-size: 8px;
  writing-mode: vertical-rl;
}

.rs-rack-list {
  display: flex;
  align-items: flex-end;
  gap: 10px;
}

.rs-rack {
  position: relative;
  width: 64px;
  height: 162px;
  padding: 0;
  border: 0;
  background: transparent;
  cursor: pointer;
  transition: transform 0.2s ease, filter 0.2s ease;
}

.rs-rack:hover,
.rs-rack.selected {
  transform: translateY(-5px);
  filter: brightness(1.2);
}

.rs-rack-top {
  position: absolute;
  left: 5px;
  right: 5px;
  top: 0;
  height: 9px;
  border-radius: 2px 2px 0 0;
  background: #1a3d55;
  clip-path: polygon(15% 0, 100% 0, 85% 100%, 0 100%);
}

.rs-rack-body {
  position: absolute;
  left: 5px;
  right: 5px;
  top: 8px;
  bottom: 9px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-top: 6px;
  border: 1px solid rgba(56, 189, 248, 0.25);
  border-radius: 2px;
  background: linear-gradient(180deg, #0b253b, #071827);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.35);
}

.rs-rack.online .rs-rack-body { border-color: rgba(0, 224, 161, 0.36); }
.rs-rack.warning .rs-rack-body { border-color: rgba(251, 191, 36, 0.58); box-shadow: 0 0 15px rgba(251, 191, 36, 0.16); }
.rs-rack.offline .rs-rack-body { border-color: rgba(251, 113, 133, 0.58); }

.rs-rack-led {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #00e0a1;
  box-shadow: 0 0 6px #00e0a1;
}

.rs-rack.warning .rs-rack-led { background: #fbbf24; box-shadow: 0 0 6px #fbbf24; }
.rs-rack.offline .rs-rack-led { background: #fb7185; box-shadow: 0 0 6px #fb7185; }
.rs-rack.unknown .rs-rack-led { background: #526b7b; box-shadow: none; }

.rs-rack-name {
  position: relative;
  z-index: 2;
  margin-top: 6px;
  color: #c9edf7;
  font-family: Consolas, monospace;
  font-size: 7px;
  white-space: nowrap;
}

.rs-rack-fill {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(180deg, rgba(56, 189, 248, 0.06), rgba(56, 189, 248, 0.23));
  border-top: 1px solid rgba(56, 189, 248, 0.3);
}

.rs-rack.warning .rs-rack-fill { background: linear-gradient(180deg, rgba(251, 191, 36, 0.06), rgba(251, 191, 36, 0.26)); }
.rs-rack.offline .rs-rack-fill { background: linear-gradient(180deg, rgba(251, 113, 133, 0.06), rgba(251, 113, 133, 0.23)); }

.rs-rack-u {
  position: absolute;
  bottom: 4px;
  left: 0;
  right: 0;
  z-index: 2;
  color: #6e9ab3;
  font-family: Consolas, monospace;
  font-size: 6px;
  text-align: center;
}

.rs-rack-base {
  position: absolute;
  left: 2px;
  right: 2px;
  bottom: 2px;
  height: 8px;
  border-radius: 1px;
  background: rgba(14, 38, 56, 0.9);
  box-shadow: 0 3px 9px rgba(0, 0, 0, 0.6);
}

.rs-aisle {
  align-self: flex-end;
  margin: 0 0 3px 8px;
  color: #234a60;
  font-family: Consolas, monospace;
  font-size: 7px;
  writing-mode: vertical-rl;
}

.rs-rack-detail {
  position: absolute;
  right: 14px;
  top: 38px;
  z-index: 3;
  width: 228px;
  max-height: calc(100% - 54px);
  overflow: auto;
  padding: 10px;
  border: 1px solid rgba(0, 245, 255, 0.28);
  border-radius: 10px;
  background: rgba(5, 20, 34, 0.94);
  box-shadow: 0 12px 30px rgba(0, 0, 0, 0.42);
}

.rs-detail-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: flex-start;
  padding-bottom: 7px;
  border-bottom: 1px solid rgba(56, 189, 248, 0.12);
}

.rs-detail-head strong { display: block; color: #dff8ff; font-size: 12px; }
.rs-detail-head span { display: block; margin-top: 2px; color: #5d7b8d; font-size: 8px; }
.rs-detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 7px 10px; margin-top: 9px; }
.rs-detail-grid span { display: block; color: #557286; font-size: 8px; }
.rs-detail-grid b { display: block; margin-top: 2px; color: #c7e7f4; font-family: Consolas, monospace; font-size: 10px; }
.rs-detail-grid b.warning { color: #fbbf24; }
.rs-detail-grid b.offline { color: #fb7185; }
.rs-detail-grid b.online { color: #00e0a1; }
.rs-detail-bar { height: 4px; margin-top: 9px; overflow: hidden; border-radius: 2px; background: rgba(31, 59, 79, 0.7); }
.rs-detail-bar i { display: block; height: 100%; background: #38bdf8; }
.rs-door-actions { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
.rs-door-actions .el-button { height: 25px; padding: 0 9px; border-color: rgba(56, 189, 248, 0.3); background: rgba(14, 165, 233, 0.12); color: #7dd3fc; font-size: 9px; }
.rs-door-actions > span { color: #527286; font-size: 8px; line-height: 1.4; }
.rs-detail-devices { margin-top: 8px; }
.rs-device-row { display: flex; align-items: center; gap: 5px; padding: 4px 0; border-bottom: 1px solid rgba(56, 189, 248, 0.05); }
.rs-device-row b { color: #a7c7d8; font-size: 8px; font-weight: 400; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rs-device-row small { margin-left: auto; color: #527286; font-family: Consolas, monospace; font-size: 7px; white-space: nowrap; }

.rs-power-value {
  padding: 10px 11px 2px;
  color: #e5fbff;
  font-family: Consolas, monospace;
  font-size: 27px;
  font-weight: 600;
}

.rs-power-value small { color: #61869c; font-size: 10px; }

.rs-progress { height: 5px; margin: 6px 11px 9px; overflow: hidden; border-radius: 3px; background: rgba(31, 59, 79, 0.7); }
.rs-progress i { display: block; height: 100%; background: linear-gradient(90deg, #00c8e8, #00ffb3); }
.rs-meta-row { display: flex; justify-content: space-between; gap: 8px; padding: 4px 11px; color: #58778a; font-size: 8px; }
.rs-meta-row b { color: #9fc9d9; font-family: Consolas, monospace; font-size: 8px; }

.rs-load-list { padding: 5px 10px 9px; }
.rs-load-row { display: flex; align-items: center; gap: 5px; padding: 4px 0; }
.rs-load-row span { width: 34px; color: #6b8da0; font-family: Consolas, monospace; font-size: 8px; overflow: hidden; text-overflow: ellipsis; }
.rs-load-row div { flex: 1; height: 4px; overflow: hidden; border-radius: 2px; background: rgba(31, 59, 79, 0.65); }
.rs-load-row i { display: block; height: 100%; background: #38bdf8; }
.rs-load-row b { width: 27px; color: #8fb8c9; font-family: Consolas, monospace; font-size: 7px; text-align: right; }

.rs-env-line { display: flex; align-items: center; gap: 12px; padding: 10px 11px; color: #5c7b8e; font-size: 9px; }
.rs-env-line b { color: #d6f4ff; font-family: Consolas, monospace; font-size: 11px; }
.rs-empty-mini { padding: 10px 2px; color: #3e5d70; font-size: 8px; }

.rs-alerts {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
  min-height: 34px;
  padding: 0 17px;
  border-top: 1px solid rgba(56, 189, 248, 0.12);
  background: rgba(4, 13, 24, 0.9);
  overflow: hidden;
}

.rs-alert-title { display: inline-flex; align-items: center; gap: 5px; flex-shrink: 0; color: #7dd3fc; font-size: 9px; }
.rs-alert-title i { width: 5px; height: 5px; border-radius: 50%; background: #fbbf24; box-shadow: 0 0 6px #fbbf24; }
.rs-alert-title span { color: #fbbf24; font-family: Consolas, monospace; }
.rs-alert-track { display: flex; align-items: center; gap: 24px; min-width: max-content; animation: rs-ticker 24s linear infinite; }
.rs-alert-track.empty { animation: none; }
.rs-alert-item { display: inline-flex; align-items: center; gap: 7px; color: #7296a8; font-size: 8px; white-space: nowrap; }
.rs-alert-item time { color: #355b70; font-family: Consolas, monospace; }
.rs-alert-item b { color: #9ac6d4; font-weight: 400; }
.rs-alert-item.critical b { color: #fb7185; }
.rs-alert-item.warning b { color: #fbbf24; }
.rs-no-alert { color: #3e5d70; font-size: 8px; }

@keyframes rs-ticker {
  0% { transform: translateX(0); }
  100% { transform: translateX(-50%); }
}

@media (max-width: 1100px) {
  .rs-metrics { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  .rs-main { grid-template-columns: 190px minmax(0, 1fr) 190px; }
}

@media (max-width: 820px) {
  .rs-header { flex-wrap: wrap; }
  .rs-title { order: -1; width: 100%; justify-content: center; }
  .rs-main { display: flex; flex-direction: column; overflow: auto; }
  .rs-side { overflow: visible; }
  .rs-scene-panel { min-height: 500px; }
  .rs-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
