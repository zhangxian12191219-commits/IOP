<template>
  <div class="bigscreen-view" :class="[`theme-${screen?.theme || 'tech'}`, `background-${screen?.background || 'default'}`, { 'is-virtualization-screen': isVirtualizationScreen }]">
    <VirtualizationTechBackground v-if="isVirtualizationScreen" />
    <div class="bs-bg-grid"></div>
    <div class="bs-glow"></div>

    <header class="bs-header">
      <div class="bs-brand">
        <div class="bs-brand-mark"><el-icon :size="20"><Monitor /></el-icon></div>
        <div>
          <span class="bs-kicker">NOC VISUAL CONSOLE</span>
          <h1>{{ screen?.name || '大屏展示' }}</h1>
        </div>
      </div>
      <div class="bs-header-center">
        <span class="bs-live-dot"></span>
        <span>LIVE DATA</span>
        <span class="bs-divider"></span>
        <div class="bs-clock-block" :style="clockStyle">
          <span
            v-if="showDate"
            class="bs-date"
          >{{ dateText }}</span>
          <span class="bs-time">{{ clock }}</span>        </div>
      </div>
      <div class="bs-header-actions">
        <span class="bs-updated">更新于 {{ lastUpdatedText }}</span>
        <el-tag v-if="sharedResource" size="small" :type="sharedResource.can_edit ? 'success' : 'info'" effect="plain">
          共享{{ sharedResource.can_edit ? '可编辑' : '只读' }}
        </el-tag>
        <el-button v-if="sharedResource && !sharedResource.can_edit" size="small" type="primary" plain @click="requestSharedEdit">
          <el-icon><Edit /></el-icon>申请编辑
        </el-button>
        <template v-if="layoutEditing">
          <el-button type="primary" size="small" @click="saveLayout">
            <el-icon><Check /></el-icon>保存布局
          </el-button>
          <el-button size="small" @click="cancelLayout">取消</el-button>
          <el-button size="small" @click="resetLayout">重置</el-button>
        </template>
        <el-button v-else size="small" :disabled="sharedReadOnly" @click="startLayoutEdit">
          <el-icon><Edit /></el-icon>编辑布局
        </el-button>
        <el-button size="small" @click="loadData">
          <el-icon><Refresh /></el-icon>刷新
        </el-button>
        <el-button size="small" @click="toggleFullscreen">
          <el-icon><FullScreen /></el-icon>{{ isFullscreen ? '退出全屏' : '全屏' }}
        </el-button>
        <el-button size="small" @click="$router.push('/bigscreen')">
          <el-icon><Back /></el-icon>返回配置
        </el-button>
      </div>
    </header>

    <main v-if="screen" class="bs-canvas">
      <div v-if="layoutEditing" class="bs-edit-hint">
        <el-icon><Rank /></el-icon>
        <span>拖动组件标题移动位置，拖拽右下角调整大小；字体、全局字号和组件字号均按配置页参数实时生效</span>
        <el-dropdown trigger="click" class="bs-add-widget" @command="addWidgetToScreen">
          <el-button size="small" type="primary" plain>
            <el-icon><Plus /></el-icon>添加内容组件
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item v-for="type in WIDGET_TYPES" :key="type.value" :command="type.value">
                {{ type.label }}
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
      <GridLayout
        v-model:layout="widgetLayout"
        class="bs-grid"
        :col-num="12"
        :row-height="96"
        :margin="[14, 14]"
        :is-draggable="layoutEditing"
        :is-resizable="layoutEditing"
        :vertical-compact="false"
        :use-css-transforms="true"
        @layout-updated="onLayoutUpdated"
      >
        <GridItem
          v-for="widget in screen.widgets"
          :key="widget.id"
          :i="widget.id"
          v-bind="widgetLayoutItem(widget)"
          :min-w="2"
          :min-h="1"
          drag-allow-from=".bs-widget-head"
          drag-ignore-from="button,a,input"
          class="bs-grid-item"
        >
          <section
            class="bs-widget"
            :class="[`bs-widget--${widget.type}`, { 'is-editing': layoutEditing }]"
            :style="widgetShellStyle(widget)"
          >
            <div class="bs-widget-head">
              <el-icon v-if="layoutEditing" class="bs-drag-grip"><Rank /></el-icon>
              <span class="bs-widget-title" :style="{ fontSize: `${widgetTitleFontSize(widget)}px` }">{{ widget.title }}</span>
              <span class="bs-widget-tag">{{ widgetTypeLabel(widget.type) }}</span>
              <el-button
                v-if="layoutEditing"
                text
                circle
                class="bs-widget-settings"
                title="组件设置"
                aria-label="组件设置"
                @click.stop="openWidgetSettings(widget)"
              >
                <el-icon><Setting /></el-icon>
              </el-button>
              <el-button
                v-if="layoutEditing"
                text
                circle
                class="bs-widget-delete"
                title="删除组件"
                aria-label="删除组件"
                @click.stop="removeWidget(widget)"
              >
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>

        <div class="bs-widget-body">
          <div class="bs-widget-scale" :style="widgetScaleStyle(widget)">
          <template v-if="widget.type === 'kpi'">
            <div class="bs-kpi">
              <div class="bs-kpi-value">{{ widgetData(widget).value }}</div>
              <div class="bs-kpi-label">{{ widgetData(widget).label }}</div>
            </div>
          </template>

          <template v-else-if="widget.type === 'gauge'">
            <div class="bs-gauge-wrap">
              <div class="bs-gauge" :style="{ '--gauge-percent': `${widgetData(widget).percent || 0}%`, '--gauge-color': widgetData(widget).color || '#38bdf8' }">
                <div class="bs-gauge-inner">
                  <strong>{{ widgetData(widget).value }}</strong>
                  <small>{{ widgetData(widget).unit }}</small>
                </div>
              </div>
              <div class="bs-gauge-meta">
                <b>{{ widgetData(widget).deviceName }}</b>
                <span>{{ widgetData(widget).label }} · {{ widgetData(widget).status }}</span>
              </div>
            </div>
          </template>

          <template v-else-if="widget.type === 'bar'">
            <div class="bs-bars">
              <div v-for="item in widgetData(widget).items" :key="item.name" class="bs-bar-row">
                <span class="bs-bar-name">{{ item.name }}</span>
                <span class="bs-bar-track"><i :style="{ width: `${item.percent}%`, background: item.color }"></i></span>
                <b class="bs-bar-value">{{ item.value }}</b>
              </div>
              <div v-if="!widgetData(widget).items.length" class="bs-empty">暂无指标数据</div>
            </div>
          </template>

          <template v-else-if="widget.type === 'table'">
            <div class="bs-table">
              <div class="bs-table-row bs-table-head">
                <span>设备</span><span>IP 地址</span><span>状态</span><span>{{ metricLabel(widget.metric) }}</span>
              </div>
              <BigScreenAutoScroll class="bs-table-body" :speed="14">
                <div v-for="row in widgetData(widget).rows" :key="row.id" class="bs-table-row">
                  <span class="bs-device-name">{{ row.name }}</span>
                  <span class="bs-mono">{{ row.ip }}</span>
                  <span><i class="bs-status-dot" :class="row.status"></i>{{ row.statusText }}</span>
                  <b>{{ row.value }}</b>
                </div>
                <div v-if="!widgetData(widget).rows.length" class="bs-empty">暂无设备数据</div>
              </BigScreenAutoScroll>
            </div>
          </template>

          <template v-else-if="widget.type === 'server'">
            <BigScreenAutoScroll class="bs-server-scroll" :speed="10">
              <div class="bs-server-grid">
                <div v-for="server in widgetData(widget).servers" :key="server.id" class="bs-server-card">
                  <div class="bs-server-head">
                    <b>{{ server.name }}</b>
                    <span>{{ server.ip }}</span>
                  </div>
                  <div class="bs-server-sensors">
                    <span v-for="sensor in server.sensors" :key="sensor.key" class="bs-sensor" :class="sensor.level">
                      <small>{{ sensor.name }}</small>
                      <strong>{{ sensor.text }}</strong>
                    </span>
                  </div>
                </div>
                <div v-if="!widgetData(widget).servers.length" class="bs-empty">暂无服务器硬件传感器</div>
              </div>
            </BigScreenAutoScroll>
          </template>

          <template v-else-if="widget.type === 'alerts'">
            <BigScreenAutoScroll class="bs-alert-list" :speed="10">
              <div v-for="alert in widgetData(widget).alerts" :key="alert.id" class="bs-alert-item" :class="alert.level">
                <span class="bs-alert-level">{{ alert.levelText }}</span>
                <div>
                  <b>{{ alert.device }}</b>
                  <p>{{ alert.message }}</p>
                </div>
                <time>{{ alert.time }}</time>
              </div>
              <div v-if="!widgetData(widget).alerts.length" class="bs-empty">当前没有未处理告警</div>
            </BigScreenAutoScroll>
          </template>

          <template v-else-if="widget.type === 'website'">
            <BigScreenAutoScroll class="bs-website-list" :speed="10">
              <div v-for="item in websiteTargets.slice(0, Number(widget.websiteLimit) || 6)" :key="item.id" class="bs-website-row">
                <span class="bs-website-dot" :class="item.latest_status?.is_alive ? 'online' : 'offline'"></span>
                <div class="bs-website-main">
                  <b>{{ item.name }}</b>
                  <small>{{ item.domain || item.ip_address || item.url }}</small>
                </div>
                <span class="bs-website-value">{{ item.latest_status?.response_time ? `${Math.round(item.latest_status.response_time)}ms` : '—' }}</span>
                <span class="bs-website-cert">{{ item.latest_status?.cert_info?.days_left !== undefined ? `${item.latest_status.cert_info.days_left}天` : '—' }}</span>
              </div>
              <div v-if="!websiteTargets.length" class="bs-empty">暂无网站监控数据</div>
            </BigScreenAutoScroll>
          </template>

          <template v-else-if="widget.type === 'text'">
            <div
              class="bs-text-widget"
              :style="{
                fontFamily: widget.fontFamily || displayConfig.fontFamily,
                fontSize: `${widgetFontSize(widget)}px`,
                color: widget.color || '#e2f8ff',
                textAlign: widget.align || 'left',
              }"
            >{{ widget.content || widget.title }}</div>
          </template>

          <template v-else-if="widget.type === 'topology'">
            <TopologyWidget />
          </template>

          <template v-else-if="widget.type === 'virtualization'">
            <VirtualizationOverviewWidget
              :data="virtualizationData"
              :panels="virtualizationPanels(widget)"
              :editable="layoutEditing"
              @update:panels="(panels) => updateVirtualizationPanels(widget, panels)"
            />
          </template>

          <template v-else-if="widget.type === 'trend'">
            <div class="bs-trend">
              <div v-for="point in widgetData(widget).points" :key="point.time" class="bs-trend-col">
                <span class="bs-trend-bar" :style="{ height: `${point.height}%` }"></span>
                <small>{{ point.time }}</small>
              </div>
            </div>
          </template>

          <template v-else-if="widget.type === 'zabbix'">
            <div class="bs-zabbix">
              <div class="bs-zabbix-value">
                {{ widgetData(widget).display }}
                <small>{{ widgetData(widget).unit }}</small>
              </div>
              <div class="bs-zabbix-meta">
                <b>{{ widgetData(widget).host || '未配置 Zabbix 主机' }}</b>
                <span>{{ widgetData(widget).itemName || widget.item || '未配置监控项' }}</span>
              </div>
              <div v-if="widgetData(widget).error" class="bs-zabbix-error">
                {{ widgetData(widget).error }}
              </div>
            </div>
          </template>
          </div>
        </div>
          </section>
        </GridItem>
      </GridLayout>
    </main>

    <div v-else class="bs-notfound">
      <h2>大屏不存在或已被删除</h2>
      <el-button type="primary" @click="$router.push('/bigscreen')">返回大屏管理</el-button>
    </div>

    <el-dialog
      v-model="widgetSettingsVisible"
      title="内容组件设置"
      width="520px"
      append-to-body
      class="bs-widget-settings-dialog"
    >
      <el-form v-if="widgetSettingsDraft" label-width="88px">
        <el-form-item label="组件类型">
          <el-tag size="small" effect="plain">{{ widgetTypeLabel(widgetSettingsDraft.type) }}</el-tag>
        </el-form-item>
        <el-form-item label="标题">
          <el-input v-model="widgetSettingsDraft.title" maxlength="40" placeholder="组件标题" />
        </el-form-item>
        <el-form-item label="字号">
          <el-select v-model="widgetSettingsDraft.fontSize" style="width: 100%">
            <el-option label="跟随全局" :value="0" />
            <el-option v-for="size in WIDGET_FONT_SIZES" :key="size" :label="`${size} px`" :value="size" />
          </el-select>
          <div class="bs-settings-tip">跟随全局时使用大屏配置的基础字号，选择具体字号可单独放大或缩小本组件。</div>
        </el-form-item>

        <template v-if="widgetSettingsDraft.type === 'kpi'">
          <el-form-item label="指标">
            <el-select v-model="widgetSettingsDraft.kpiKey" style="width: 100%">
              <el-option v-for="item in KPI_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-form-item>
        </template>
        <template v-else-if="widgetSettingsDraft.type === 'gauge'">
          <el-form-item label="设备">
            <el-select v-model="widgetSettingsDraft.deviceId" filterable clearable style="width: 100%" placeholder="选择设备">
              <el-option v-for="device in assets" :key="device.id" :label="`${device.name} · ${device.ip_address}`" :value="device.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="指标">
            <el-select v-model="widgetSettingsDraft.metric" style="width: 100%">
              <el-option v-for="item in METRIC_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-form-item>
        </template>
        <template v-else-if="widgetSettingsDraft.type === 'bar' || widgetSettingsDraft.type === 'table'">
          <el-form-item label="指标">
            <el-select v-model="widgetSettingsDraft.metric" style="width: 100%">
              <el-option v-for="item in METRIC_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="显示条数">
            <el-input-number v-model="widgetSettingsDraft.limit" :min="3" :max="20" controls-position="right" />
          </el-form-item>
        </template>
        <template v-else-if="widgetSettingsDraft.type === 'alerts'">
          <el-form-item label="显示条数">
            <el-input-number v-model="widgetSettingsDraft.limit" :min="3" :max="20" controls-position="right" />
          </el-form-item>
        </template>
        <template v-else-if="widgetSettingsDraft.type === 'zabbix'">
          <el-form-item label="Zabbix 主机">
            <el-input v-model="widgetSettingsDraft.host" placeholder="主机技术名" />
          </el-form-item>
          <el-form-item label="监控项 key">
            <el-input v-model="widgetSettingsDraft.item" placeholder="如 system.cpu.util" />
          </el-form-item>
          <el-form-item label="单位">
            <el-input v-model="widgetSettingsDraft.unit" placeholder="可留空" />
          </el-form-item>
        </template>
        <el-form-item v-else label="说明">
          <span class="bs-settings-tip">{{ widgetSettingsDraft.type === 'virtualization' ? '自动读取虚拟化平台、宿主机、虚拟机和告警数据' : widgetSettingsDraft.type === 'topology' ? '自动读取当前网络拓扑与链路数据' : widgetSettingsDraft.type === 'server' ? '自动汇总服务器硬件传感器' : '展示最近 24 小时告警趋势' }}</span>
        </el-form-item>

        <el-form-item label="布局宽度">
          <el-input-number v-model="widgetSettingsDraft.span" :min="2" :max="12" controls-position="right" />
          <span class="bs-settings-tip">占 12 列中的宽度，应用后可继续拖动、缩放布局</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="bs-settings-footer">
          <el-button type="danger" plain @click="deleteSettingsWidget">删除组件与布局</el-button>
          <span class="bs-settings-spacer"></span>
          <el-button @click="widgetSettingsVisible = false">取消</el-button>
          <el-button type="primary" @click="saveWidgetSettings">应用</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { GridLayout, GridItem } from 'grid-layout-plus'
import { monitorApi, bigscreenApi, virtualizationApi, sharingApi, websiteApi } from '@/api'
import TopologyWidget from '@/components/TopologyWidget.vue'
import VirtualizationOverviewWidget from '@/components/VirtualizationOverviewWidget.vue'
import VirtualizationTechBackground from '@/components/VirtualizationTechBackground.vue'
import BigScreenAutoScroll from '@/components/BigScreenAutoScroll.vue'
import {
  readScreens, writeScreens, metricMeta, deviceMetricValue, metricText, fetchAllDevices,
  defaultClock, defaultDisplay, WIDGET_TYPES, KPI_OPTIONS, METRIC_OPTIONS, WIDGET_FONT_SIZES,
  defaultWidget,
} from '@/utils/bigscreen'

const route = useRoute()
const screens = ref([])
const sharedResource = ref(null)
const sharedReadOnly = computed(() => Boolean(sharedResource.value && !sharedResource.value.can_edit))
const assets = ref([])
const stats = ref({})
const alerts = ref([])
const trend = ref([])
const zabbixResults = ref({})
const virtualizationData = ref({ overview: {}, platforms: [], hosts: [], vms: [], alerts: [] })
const websiteTargets = ref([])
const lastUpdated = ref(null)
const now = ref(new Date())
const isFullscreen = ref(false)
const layoutEditing = ref(false)
const widgetLayout = ref([])
const layoutSnapshot = ref([])
const widgetSnapshot = ref([])
const widgetSettingsVisible = ref(false)
const widgetSettingsDraft = ref(null)
let refreshTimer = null
let clockTimer = null

const screen = computed(() => screens.value.find((item) => item.id === route.params.id) || null)
const displayConfig = computed(() => ({ ...defaultDisplay(), ...(screen.value?.display || {}) }))
const DESIGN_BASE_FONT_SIZE = 14
const isVirtualizationScreen = computed(() => (
  screen.value?.kind === 'virtualization'
  || screen.value?.background === 'virtual'
  || (screen.value?.widgets || []).some((widget) => widget.type === 'virtualization')
))
const needsVirtualization = computed(() => (screen.value?.widgets || []).some((widget) => widget.type === 'virtualization'))

function virtualizationPanels(widget) {
  return Array.isArray(widget?.panels) && widget.panels.length ? widget.panels : []
}

function updateVirtualizationPanels(widget, panels) {
  if (!widget) return
  widget.panels = Array.isArray(panels) ? panels.map((item) => ({ ...item })) : []
}
const clockConfig = computed(() => ({ ...defaultClock(), ...(screen.value?.clock || {}) }))
const clockStyle = computed(() => ({
  fontSize: `${clockConfig.value.fontSize}px`,
  fontFamily: clockConfig.value.fontFamily || defaultClock().fontFamily,
  fontWeight: clockConfig.value.bold ? 700 : 400,
}))
const showDate = computed(() => ['showYear', 'showMonth', 'showDay', 'showWeekday']
  .some((key) => clockConfig.value[key]))
const dateText = computed(() => formatClock(now.value, clockConfig.value).date)
const clock = computed(() => formatClock(now.value, clockConfig.value).time)

function widgetFontSize(widget) {
  const own = Number(widget?.fontSize)
  if (Number.isFinite(own) && own > 0) return Math.max(8, Math.min(48, own))
  const globalSize = Number(displayConfig.value.fontSize)
  return Number.isFinite(globalSize) && globalSize > 0 ? Math.max(8, Math.min(48, globalSize)) : DESIGN_BASE_FONT_SIZE
}

function widgetShellStyle(widget) {
  return {
    fontFamily: widget.fontFamily || displayConfig.value.fontFamily || defaultDisplay().fontFamily,
  }
}

function widgetTitleFontSize(widget) {
  const size = widgetFontSize(widget)
  return Math.max(11, Math.min(24, Math.round(12 * (size / DESIGN_BASE_FONT_SIZE))))
}

function widgetScaleStyle(widget) {
  const fontSize = widgetFontSize(widget)
  const scale = Math.max(0.6, Math.min(3, fontSize / DESIGN_BASE_FONT_SIZE))
  return {
    fontFamily: widget.fontFamily || displayConfig.value.fontFamily || defaultDisplay().fontFamily,
    zoom: scale,
    width: `${100 / scale}%`,
    height: `${100 / scale}%`,
  }
}

function formatClock(date, config) {
  const timezone = config.timezone && config.timezone !== 'local' ? config.timezone : undefined
  const timeOptions = {
    hour12: !!config.hour12,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    timeZone: timezone,
  }
  let time = ''
  try {
    time = new Intl.DateTimeFormat('zh-CN', timeOptions).format(date)
  } catch {
    const fallback = { ...timeOptions }
    delete fallback.timeZone
    time = new Intl.DateTimeFormat('zh-CN', fallback).format(date)
  }

  const dateOptions = {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    weekday: 'long',
    timeZone: timezone,
  }
  let parts = {}
  try {
    new Intl.DateTimeFormat('zh-CN', dateOptions).formatToParts(date).forEach((part) => {
      if (part.type !== 'literal') parts[part.type] = part.value
    })
  } catch {
    const fallback = { ...dateOptions }
    delete fallback.timeZone
    new Intl.DateTimeFormat('zh-CN', fallback).formatToParts(date).forEach((part) => {
      if (part.type !== 'literal') parts[part.type] = part.value
    })
  }

  const pieces = []
  let dateMain = ''
  if (config.showYear && parts.year) dateMain += `${parts.year}年`
  if (config.showMonth && parts.month) dateMain += `${parts.month}月`
  if (config.showDay && parts.day) dateMain += `${parts.day}日`
  if (dateMain) pieces.push(dateMain)
  if (config.showWeekday && parts.weekday) pieces.push(parts.weekday)
  return { time, date: pieces.join(' ') }
}
function defaultWidgetHeight(type) {
  if (type === 'kpi') return 1
  if (type === 'server') return 3
  if (type === 'topology') return 4
  if (type === 'virtualization') return 7
  return 2
}

function buildWidgetLayout(widgets, reset = false) {
  const list = Array.isArray(widgets) ? widgets : []
  const hasSaved = !reset && list.length > 0 && list.every((widget) => (
    Number.isFinite(Number(widget.x))
    && Number.isFinite(Number(widget.y))
    && Number(widget.w) >= 2
    && Number(widget.h) >= 1
  ))
  if (hasSaved) {
    return list.map((widget) => ({
      i: widget.id,
      x: Math.max(0, Number(widget.x)),
      y: Math.max(0, Number(widget.y)),
      w: Math.max(2, Math.min(12, Number(widget.w))),
      h: Math.max(1, Number(widget.h)),
    }))
  }

  const layout = []
  let x = 0
  let y = 0
  let rowHeight = 0
  list.forEach((widget) => {
    const w = Math.max(2, Math.min(12, Number(widget.span) || 3))
    const h = defaultWidgetHeight(widget.type)
    if (x + w > 12) {
      x = 0
      y += rowHeight
      rowHeight = 0
    }
    layout.push({ i: widget.id, x, y, w, h })
    x += w
    rowHeight = Math.max(rowHeight, h)
    if (x >= 12) {
      x = 0
      y += rowHeight
      rowHeight = 0
    }
  })
  return layout
}

function initWidgetLayout() {
  if (!screen.value) {
    widgetLayout.value = []
    return
  }
  widgetLayout.value = buildWidgetLayout(screen.value.widgets)
  layoutSnapshot.value = JSON.parse(JSON.stringify(widgetLayout.value))
}

function widgetLayoutItem(widget) {
  return widgetLayout.value.find((item) => item.i === widget.id) || {
    i: widget.id,
    x: 0,
    y: 0,
    w: Math.max(2, Number(widget.span) || 3),
    h: defaultWidgetHeight(widget.type),
  }
}

function startLayoutEdit() {
  if (sharedReadOnly.value) {
    ElMessage.info('共享大屏当前为只读，请点击“申请编辑”')
    return
  }
  layoutSnapshot.value = JSON.parse(JSON.stringify(widgetLayout.value))
  widgetSnapshot.value = JSON.parse(JSON.stringify(screen.value?.widgets || []))
  layoutEditing.value = true
}

async function removeWidget(widget) {
  if (!screen.value || !layoutEditing.value) return
  try {
    await ElMessageBox.confirm(
      `确定删除组件「${widget.title || '未命名组件'}」吗？点击「保存布局」后生效。`,
      '删除组件',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  screen.value.widgets = screen.value.widgets.filter((item) => item.id !== widget.id)
  widgetLayout.value = widgetLayout.value.filter((item) => item.i !== widget.id)
  ElMessage.success('组件已删除，点击「保存布局」后持久生效')
}

function onLayoutUpdated() {
  // 布局实时写入 widgetLayout，点击保存后持久化
}

async function saveLayout() {
  if (!screen.value || sharedReadOnly.value) return
  const positions = new Map(widgetLayout.value.map((item) => [item.i, item]))
  screen.value.widgets = screen.value.widgets.map((widget) => {
    const position = positions.get(widget.id)
    if (!position) return widget
    return {
      ...widget,
      x: position.x,
      y: position.y,
      w: position.w,
      h: position.h,
      span: position.w,
    }
  })
  if (sharedResource.value?.id) {
    try {
      await sharingApi.updateResource(sharedResource.value.id, { config: screen.value })
    } catch (error) {
      ElMessage.error(error?.response?.data?.detail || error.message || '共享大屏保存失败')
      return
    }
  } else {
    writeScreens(screens.value)
  }
  layoutSnapshot.value = JSON.parse(JSON.stringify(widgetLayout.value))
  widgetSnapshot.value = []
  layoutEditing.value = false
  ElMessage.success('大屏布局已保存')
}

function cancelLayout() {
  widgetLayout.value = JSON.parse(JSON.stringify(layoutSnapshot.value))
  if (screen.value && widgetSnapshot.value.length) {
    screen.value.widgets = JSON.parse(JSON.stringify(widgetSnapshot.value))
  }
  widgetSnapshot.value = []
  layoutEditing.value = false
}

function resetLayout() {
  if (!screen.value) return
  widgetLayout.value = buildWidgetLayout(screen.value.widgets, true)
  ElMessage.info('已恢复默认排列，点击「保存布局」后生效')
}

watch(() => screen.value?.id, initWidgetLayout, { immediate: true })

const lastUpdatedText = computed(() => (lastUpdated.value
  ? lastUpdated.value.toLocaleTimeString('zh-CN', { hour12: false })
  : '--:--:--'))

const serverDevices = computed(() => assets.value.filter((device) => (device.server_sensors || []).length))

function widgetTypeLabel(type) {
  const labels = {
    kpi: 'KPI', gauge: '实时指标', bar: '指标排行', table: '设备状态',
    server: '服务器硬件', alerts: '告警', trend: '趋势', website: '网站监控', text: '文本',
    topology: '网络拓扑', virtualization: '虚拟化资源', zabbix: 'Zabbix 指标',
  }
  return labels[type] || type
}

function addWidgetToScreen(type) {
  if (!screen.value || !layoutEditing.value) return
  const widget = defaultWidget(type)
  const width = Math.max(2, Math.min(12, Number(widget.span) || 3))
  const height = defaultWidgetHeight(type)
  const bottom = widgetLayout.value.reduce(
    (max, item) => Math.max(max, Number(item.y || 0) + Number(item.h || 0)),
    0,
  )
  widget.x = 0
  widget.y = bottom
  widget.w = width
  widget.h = height
  screen.value.widgets.push(widget)
  widgetLayout.value.push({ i: widget.id, x: 0, y: bottom, w: width, h: height })
  openWidgetSettings(widget)
}

function openWidgetSettings(widget) {
  if (!widget) return
  widgetSettingsDraft.value = JSON.parse(JSON.stringify(widget))
  widgetSettingsVisible.value = true
}

function saveWidgetSettings() {
  if (!screen.value || !widgetSettingsDraft.value) return
  const draft = widgetSettingsDraft.value
  const source = screen.value.widgets.find((widget) => widget.id === draft.id)
  if (!source) return
  Object.assign(source, draft)
  const item = widgetLayout.value.find((layout) => layout.i === draft.id)
  if (item) {
    item.w = Math.max(2, Math.min(12, Number(draft.span) || item.w))
    item.x = Math.min(Number(item.x) || 0, Math.max(0, 12 - item.w))
  }
  widgetSettingsVisible.value = false
  ElMessage.success('组件设置已应用，点击「保存布局」持久化')
}

function deleteSettingsWidget() {
  if (!screen.value || !widgetSettingsDraft.value) return
  const widget = screen.value.widgets.find((item) => item.id === widgetSettingsDraft.value.id)
  widgetSettingsVisible.value = false
  if (widget) removeWidget(widget)
}

function metricLabel(key) {
  return metricMeta(key).label
}

function isOnline(device) {
  const at = device.metric?.collected_at
  if (!at) return false
  const normalized = /[zZ]|[+-]\d{2}:\d{2}$/.test(at) ? at : `${at}Z`
  const timestamp = new Date(normalized).getTime()
  return Number.isFinite(timestamp) && Date.now() - timestamp < 10 * 60 * 1000
}

function onlineCount() {
  return assets.value.filter(isOnline).length
}

function averageMetric(key) {
  const values = assets.value.map((device) => deviceMetricValue(device, key)).filter((value) => Number.isFinite(value))
  if (!values.length) return '--'
  return (values.reduce((sum, value) => sum + value, 0) / values.length).toFixed(1)
}

function kpiValue(key) {
  if (key === 'total_devices') return assets.value.length || stats.value.total_devices || 0
  if (key === 'enabled_devices') return assets.value.filter((device) => device.is_enabled !== false).length || stats.value.enabled_devices || 0
  if (key === 'online_devices') return onlineCount()
  if (key === 'offline_devices') return Math.max(0, (assets.value.length || stats.value.total_devices || 0) - onlineCount())
  if (key === 'server_devices') return serverDevices.value.length
  if (key === 'unack_alerts') return stats.value.unack_alerts ?? alerts.value.length
  if (key === 'recent_alerts_24h') return stats.value.recent_alerts_24h || 0
  if (key === 'avg_cpu') return averageMetric('cpu_usage')
  if (key === 'avg_memory') return averageMetric('memory_usage')
  return 0
}

function kpiLabel(key) {
  const labels = {
    total_devices: '设备总数', enabled_devices: '监控中设备', online_devices: '在线设备',
    offline_devices: '离线设备', server_devices: '服务器数量', unack_alerts: '未处理告警',
    recent_alerts_24h: '24h 告警数', avg_cpu: '平均 CPU', avg_memory: '平均内存',
  }
  return labels[key] || key
}

function sensorText(device, key, kind) {
  const value = deviceMetricValue(device, key)
  if (value === null || value === undefined || Number.isNaN(value)) return '--'
  if (kind === 'fault') return Number(value) <= 1 ? '正常' : '故障'
  return metricText(device, key)
}

function widgetData(widget) {
  if (widget.type === 'kpi') {
    const value = kpiValue(widget.kpiKey)
    const unit = ['avg_cpu', 'avg_memory'].includes(widget.kpiKey) ? '%' : ''
    return { value: typeof value === 'number' ? `${value}${unit}` : value, label: kpiLabel(widget.kpiKey), hint: '与实时资产数据联动' }
  }
  if (widget.type === 'gauge') {
    const device = assets.value.find((item) => item.id === widget.deviceId)
    const value = device ? deviceMetricValue(device, widget.metric) : null
    const meta = metricMeta(widget.metric)
    const isPercent = ['cpu_usage', 'memory_usage'].includes(widget.metric)
    let percent = 0
    if (Number.isFinite(value)) {
      percent = isPercent ? Math.min(100, Number(value)) : Math.min(100, Number(value) / (widget.metric === 'temperature' ? 100 : 100) * 100)
    }
    const fault = ['srv_mem_fault', 'srv_disk_fault'].includes(widget.metric)
    return {
      deviceName: device?.name || '未选择设备',
      label: meta.label,
      value: device ? (fault ? sensorText(device, widget.metric, 'fault') : metricText(device, widget.metric)) : '--',
      unit: fault ? '' : meta.unit,
      percent,
      color: percent >= 80 ? '#fb7185' : percent >= 60 ? '#fbbf24' : '#38bdf8',
      status: device ? (isOnline(device) ? '在线' : '离线/无数据') : '待配置',
    }
  }
  if (widget.type === 'bar') {
    const meta = metricMeta(widget.metric)
    const items = assets.value
      .map((device) => ({ name: device.name, value: deviceMetricValue(device, widget.metric) }))
      .filter((item) => Number.isFinite(item.value))
      .sort((a, b) => b.value - a.value)
      .slice(0, widget.limit || 5)
      .map((item) => ({
        ...item,
        value: `${Number(item.value).toFixed(1)}${meta.unit || ''}`,
        percent: Math.max(4, Math.min(100, Number(item.value))),
        color: widget.metric === 'temperature' ? '#fb7185' : widget.metric === 'memory_usage' ? '#a78bfa' : '#38bdf8',
      }))
    return { items }
  }
  if (widget.type === 'table') {
    const rows = assets.value
      .map((device) => ({
        id: device.id,
        name: device.name,
        ip: device.ip_address,
        status: isOnline(device) ? 'online' : 'offline',
        statusText: isOnline(device) ? '在线' : '离线',
        raw: deviceMetricValue(device, widget.metric),
      }))
      .filter((row) => Number.isFinite(row.raw))
      .sort((a, b) => b.raw - a.raw)
      .slice(0, widget.limit || 8)
      .map((row) => ({ ...row, value: metricText(assets.value.find((device) => device.id === row.id), widget.metric) }))
    return { rows }
  }
  if (widget.type === 'server') {
    const list = serverDevices.value.map((device) => ({
      id: device.id,
      name: device.name,
      ip: device.ip_address,
      sensors: (device.server_sensors || []).filter((sensor) => sensor.oid).map((sensor) => {
        const value = deviceMetricValue(device, sensor.key)
        const level = sensor.kind === 'fault'
          ? (Number(value) <= 1 ? 'normal' : 'critical')
          : (sensor.kind === 'temperature' && Number(value) >= 80 ? 'warning' : 'normal')
        return { key: sensor.key, name: sensor.name, text: sensorText(device, sensor.key, sensor.kind), level }
      }),
    }))
    return { servers: list }
  }
  if (widget.type === 'alerts') {
    const list = alerts.value.slice(0, widget.limit || 6).map((alert) => ({
      id: alert.id,
      level: alert.alert_level === 'critical' ? 'critical' : 'warning',
      levelText: alert.alert_level === 'critical' ? '严重' : '告警',
      device: alert.device_name || alert.source_name || '系统',
      message: alert.message || '设备异常',
      time: alert.created_at ? new Date(alert.created_at).toLocaleTimeString('zh-CN', { hour12: false }).slice(0, 5) : '-',
    }))
    return { alerts: list }
  }
  if (widget.type === 'trend') {
    const max = Math.max(1, ...trend.value.map((item) => item.count || 0))
    return {
      points: trend.value.slice(-12).map((item) => ({
        time: item.time,
        height: Math.max(4, ((item.count || 0) / max) * 100),
      })),
    }
  }
  if (widget.type === 'zabbix') {
    const source = screen.value?.zabbix || {}
    const result = zabbixResults.value[widget.id] || {}
    const numeric = Number(result.value)
    const display = result.error || result.value === null || result.value === undefined
      ? '--'
      : (Number.isFinite(numeric) ? numeric.toFixed(Number(widget.precision ?? 1)) : String(result.value))
    const configError = !source.url
      ? '未配置 Zabbix 数据源'
      : (!source.token && (!source.username || !source.password)
        ? '未配置 Zabbix API Token 或账号密码'
        : '')
    return {
      display,
      unit: widget.unit || result.unit || '',
      host: result.host_name || result.host || widget.host,
      itemName: result.item_name || widget.item,
      error: result.error || configError,
      aggregation: widget.aggregation || 'last',
    }
  }
  return {}
}

async function loadZabbixData() {
  const widgets = (screen.value?.widgets || []).filter((widget) => (
    widget.type === 'zabbix' && widget.host && widget.item
  )).slice(0, 50)
  if (!widgets.length) {
    zabbixResults.value = {}
    return
  }
  const source = screen.value?.zabbix || {}
  if (!source.url || (!source.token && (!source.username || !source.password))) {
    zabbixResults.value = Object.fromEntries(widgets.map((widget) => [widget.id, {
      id: widget.id,
      error: !source.url ? '未配置 Zabbix 数据源' : '请配置 Zabbix API Token 或用户名密码',
    }]))
    return
  }
  try {
    const res = await bigscreenApi.zabbixQuery({
      url: source.url,
      token: source.token || '',
      username: source.username || '',
      password: source.password || '',
      verify_tls: source.verify_tls !== false,
      queries: widgets.map((widget) => ({
        id: widget.id,
        host: widget.host,
        item: widget.item,
        aggregation: widget.aggregation || 'last',
        minutes: widget.minutes || 60,
        unit: widget.unit || '',
        precision: widget.precision ?? 1,
      })),
    })
    const results = res.data.results || []
    zabbixResults.value = Object.fromEntries(results.map((item) => [item.id, item]))
  } catch (error) {
    const message = error?.response?.data?.detail || error?.message || 'Zabbix 查询失败'
    zabbixResults.value = Object.fromEntries(widgets.map((widget) => [widget.id, {
      id: widget.id,
      error: message,
    }]))
  }
}

async function loadVirtualizationData() {
  const [overviewRes, platformRes, hostRes, vmRes, alertRes] = await Promise.allSettled([
    virtualizationApi.overview(),
    virtualizationApi.platforms(),
    virtualizationApi.hosts({ page: 1, page_size: 200 }),
    virtualizationApi.vms({ page: 1, page_size: 200 }),
    virtualizationApi.vmAlerts({ status: 'active', page: 1, size: 8 }),
  ])
  virtualizationData.value = {
    overview: overviewRes.status === 'fulfilled' ? (overviewRes.value.data || {}) : {},
    platforms: platformRes.status === 'fulfilled' ? (platformRes.value.data?.items || []) : [],
    hosts: hostRes.status === 'fulfilled' ? (hostRes.value.data?.items || []) : [],
    vms: vmRes.status === 'fulfilled' ? (vmRes.value.data?.items || []) : [],
    alerts: alertRes.status === 'fulfilled' ? (alertRes.value.data?.items || []) : [],
  }
}

async function loadData() {
  try {
    const [assetRes, statsRes, alertsRes, trendRes] = await Promise.allSettled([
      fetchAllDevices(),
      monitorApi.getDashboard(),
      monitorApi.getUnackAlerts(),
      monitorApi.getAlertTrend(),
    ])
    if (assetRes.status === 'fulfilled') assets.value = assetRes.value || []
    if (statsRes.status === 'fulfilled') stats.value = statsRes.value.data || {}
    if (alertsRes.status === 'fulfilled') alerts.value = alertsRes.value.data || []
    if (trendRes.status === 'fulfilled') trend.value = trendRes.value.data.alert_trend || []
    if ((screen.value?.widgets || []).some((widget) => widget.type === 'website')) {
      try {
        const websiteRes = await websiteApi.getList({ page: 1, size: 100, sort_by: 'sort_order', sort_order: 'asc' })
        websiteTargets.value = websiteRes.data?.items || []
      } catch {
        websiteTargets.value = []
      }
    }
    await loadZabbixData()
    if (needsVirtualization.value) await loadVirtualizationData()
    lastUpdated.value = new Date()
  } catch {
    lastUpdated.value = new Date()
  }
}

function scheduleRefresh() {
  if (refreshTimer) clearInterval(refreshTimer)
  const seconds = Math.max(3, Number(screen.value?.refresh || 10))
  refreshTimer = setInterval(() => {
    if (!document.hidden) loadData()
  }, seconds * 1000)
}

async function toggleFullscreen() {
  try {
    if (!document.fullscreenElement) {
      await document.documentElement.requestFullscreen()
      isFullscreen.value = true
    } else {
      await document.exitFullscreen()
      isFullscreen.value = false
    }
  } catch {
    /* 浏览器不允许时忽略 */
  }
}

function handleFullscreenChange() {
  isFullscreen.value = !!document.fullscreenElement
}

async function loadSharedScreen() {
  const shareId = Number(route.query.shared)
  if (!shareId) return false
  try {
    const res = await sharingApi.resource(shareId)
    const item = res.data?.resource
    if (!item || item.resource_type !== 'bigscreen') {
      ElMessage.error('该共享资源不是大屏')
      return false
    }
    const config = JSON.parse(JSON.stringify(item.config || {}))
    config.id = String(route.params.id)
    screens.value = [config]
    sharedResource.value = item
    await nextTick()
    initWidgetLayout()
    return true
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '共享大屏加载失败')
    return false
  }
}

async function requestSharedEdit() {
  if (!sharedResource.value) return
  try {
    await sharingApi.requestEdit(sharedResource.value.id)
    sharedResource.value = { ...sharedResource.value, pending_request: { status: 'pending' } }
    ElMessage.success('编辑申请已提交，等待共享者审批')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '提交编辑申请失败')
  }
}

onMounted(async () => {
  const isShared = await loadSharedScreen()
  if (!isShared) screens.value = readScreens()
  loadData()
  scheduleRefresh()
  clockTimer = setInterval(() => { now.value = new Date() }, 1000)
  document.addEventListener('fullscreenchange', handleFullscreenChange)
})

watch(() => route.query.shared, async (value) => {
  if (value) {
    const loaded = await loadSharedScreen()
    if (loaded) loadData()
  } else {
    sharedResource.value = null
    screens.value = readScreens()
    initWidgetLayout()
  }
})

onBeforeUnmount(() => {
  if (refreshTimer) clearInterval(refreshTimer)
  if (clockTimer) clearInterval(clockTimer)
  document.removeEventListener('fullscreenchange', handleFullscreenChange)
})
</script>

<style scoped>
.bigscreen-view {
  position: fixed;
  inset: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  color: #dbeafe;
  background: #030b16;
  font-family: -apple-system, 'Microsoft YaHei', sans-serif;
}

.bigscreen-view.background-virtual {
  background:
    radial-gradient(ellipse at 50% 0%, #06253f 0%, #020b18 48%, #01050d 100%);
}

.bigscreen-view.background-virtual .bs-bg-grid {
  opacity: .36;
  background-size: 46px 46px;
  animation: virtualGridDrift 26s linear infinite;
}

.bigscreen-view.background-virtual .bs-glow {
  animation: virtualGlowPulse 9s ease-in-out infinite alternate;
}

@keyframes virtualGridDrift {
  from { background-position: 0 0, 0 0; }
  to { background-position: 46px 46px, 46px 46px; }
}

@keyframes virtualGlowPulse {
  from { opacity: .65; transform: scale(1); }
  to { opacity: 1; transform: scale(1.04); }
}

.bs-bg-grid {
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0.5;
  background-image:
    linear-gradient(rgba(56, 189, 248, 0.055) 1px, transparent 1px),
    linear-gradient(90deg, rgba(56, 189, 248, 0.055) 1px, transparent 1px);
  background-size: 36px 36px;
  mask-image: radial-gradient(ellipse at 50% 30%, #000 10%, transparent 85%);
}

.bs-glow {
  position: absolute;
  inset: -20%;
  pointer-events: none;
  background:
    radial-gradient(ellipse at 15% 0%, rgba(14, 165, 233, 0.16), transparent 38%),
    radial-gradient(ellipse at 90% 100%, rgba(124, 58, 237, 0.14), transparent 42%);
}

.bs-header {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-shrink: 0;
  min-height: 68px;
  height: auto;
  padding: 8px 22px;
  border-bottom: 1px solid rgba(56, 189, 248, 0.16);
  background: rgba(4, 14, 27, 0.82);
  backdrop-filter: blur(8px);
}

.bs-brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.bs-brand-mark {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border: 1px solid rgba(56, 189, 248, 0.4);
  border-radius: 8px;
  color: #7dd3fc;
  background: rgba(14, 165, 233, 0.12);
  box-shadow: 0 0 20px rgba(56, 189, 248, 0.16);
}

.bs-kicker {
  display: block;
  color: #38bdf8;
  font-family: Consolas, monospace;
  font-size: 8px;
  letter-spacing: 2px;
}

.bs-header h1 {
  margin: 3px 0 0;
  color: #f0f9ff;
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 2px;
  white-space: nowrap;
}

.bs-header-center {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #64748b;
  font-family: Consolas, monospace;
  font-size: 11px;
  letter-spacing: 1px;
}

.bs-clock-block {
  display: flex;
  flex-direction: row;
  align-items: baseline;
  justify-content: center;
  gap: 16px;
  line-height: 1.08;
  white-space: nowrap;
}

.bs-date {
  color: #64748b;
  letter-spacing: 0.5px;
  white-space: nowrap;
}

.bs-time {
  color: #e0f2fe;
  font-weight: inherit;
  letter-spacing: 1.5px;
  white-space: nowrap;
  text-shadow: 0 0 16px rgba(56, 189, 248, 0.35);
}

.bs-live-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #34d399;
  box-shadow: 0 0 8px #34d399;
}

.bs-divider {
  width: 1px;
  height: 12px;
  background: rgba(148, 163, 184, 0.25);
}

.bs-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.bs-updated {
  margin-right: 4px;
  color: #64748b;
  font-size: 10px;
}

.bs-header-actions :deep(.el-button) {
  border-color: rgba(56, 189, 248, 0.22);
  background: rgba(8, 28, 50, 0.72);
  color: #7dd3fc;
}

.bs-header-actions :deep(.el-button:hover) {
  border-color: rgba(56, 189, 248, 0.55);
  background: rgba(14, 165, 233, 0.16);
}

.bs-canvas {
  position: relative;
  z-index: 1;
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
  padding: 12px 20px 24px;
}

.bs-edit-hint {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 8px;
  padding: 6px 10px;
  border: 1px solid rgba(56, 189, 248, 0.28);
  border-radius: 6px;
  background: rgba(14, 165, 233, 0.1);
  color: #7dd3fc;
  font-size: 10px;
}

.bs-add-widget {
  margin-left: auto;
}

.bs-add-widget :deep(.el-button) {
  height: 26px;
  border-color: rgba(56, 189, 248, .4);
  background: rgba(14, 165, 233, .12);
  color: #bae6fd;
}

.bs-grid {
  flex: 1;
  width: 100%;
  min-height: 100%;
}

.bs-grid-item {
  overflow: visible;
}

.bs-widget {
  height: 100%;
  min-width: 0;
  overflow: hidden;
  border: 1px solid rgba(56, 189, 248, 0.16);
  border-radius: 10px;
  background:
    linear-gradient(150deg, rgba(9, 28, 48, 0.92), rgba(5, 16, 30, 0.9));
  box-shadow: 0 6px 22px rgba(2, 8, 20, 0.2);
}

.bs-widget.is-editing {
  border-color: rgba(56, 189, 248, 0.55);
  box-shadow: 0 0 0 1px rgba(56, 189, 248, 0.18), 0 8px 26px rgba(2, 8, 20, 0.35);
}

.bs-grid-item :deep(.vgl-item__resizer) {
  border-color: rgba(56, 189, 248, 0.65);
  background: rgba(14, 165, 233, 0.35);
}

.bs-widget-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  height: 34px;
  padding: 0 12px;
  border-bottom: 1px solid rgba(56, 189, 248, 0.1);
  background: linear-gradient(90deg, rgba(14, 165, 233, 0.08), transparent);
  cursor: default;
}

.bs-widget.is-editing .bs-widget-head {
  cursor: grab;
}

.bs-widget.is-editing .bs-widget-head:active {
  cursor: grabbing;
}

.bs-drag-grip {
  flex-shrink: 0;
  color: #38bdf8;
  font-size: 12px;
}

.bs-widget-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  color: #e0f2fe;
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bs-widget-tag {
  color: #38bdf8;
  font-family: Consolas, monospace;
  font-size: 8px;
  letter-spacing: 1px;
  opacity: 0.7;
}

.bs-widget-delete {
  flex: none;
  margin-left: 2px;
  color: #fb7185;
}

.bs-widget-settings {
  flex: none;
  color: #7dd3fc;
}

.bs-widget-settings:hover {
  color: #e0f2fe;
}

.bs-settings-tip {
  margin-top: 3px;
  color: #94a3b8;
  font-size: 11px;
  line-height: 1.5;
}

.bs-settings-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.bs-settings-spacer {
  flex: 1;
}

.bs-widget-settings-dialog :deep(.el-form-item__content) {
  min-width: 0;
}

.bs-widget-delete:hover {
  color: #fecdd3;
}

.bs-widget-body {
  height: calc(100% - 34px);
  padding: 10px 12px;
  overflow: hidden;
}

.bs-widget-scale {
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.bs-widget--virtualization {
  border-color: rgba(34, 211, 238, 0.26);
  background: linear-gradient(150deg, rgba(4, 21, 38, 0.86), rgba(3, 10, 22, 0.88));
}

.bs-widget--virtualization .bs-widget-body {
  padding: 8px;
}

.bs-widget--virtualization .bs-widget-scale {
  container-type: size;
  container-name: vz;
}

.bs-kpi {
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.bs-kpi-value {
  color: #f0f9ff;
  font-family: Consolas, monospace;
  font-size: 30px;
  font-weight: 600;
  line-height: 1;
  text-shadow: 0 0 18px rgba(56, 189, 248, 0.28);
}

.bs-kpi-label {
  margin-top: 5px;
  color: #94a3b8;
  font-size: 11px;
}

.bs-kpi-hint {
  margin-top: 3px;
  color: #334155;
  font-size: 9px;
}

.bs-gauge-wrap {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 18px;
}

.bs-gauge {
  position: relative;
  width: 94px;
  height: 94px;
  flex-shrink: 0;
  border-radius: 50%;
  background: conic-gradient(var(--gauge-color) var(--gauge-percent), rgba(51, 65, 85, 0.5) 0);
  padding: 7px;
  box-shadow: 0 0 22px color-mix(in srgb, var(--gauge-color) 35%, transparent);
}

.bs-gauge::after {
  content: '';
  position: absolute;
  inset: 7px;
  border-radius: 50%;
  background: #071525;
}

.bs-gauge-inner {
  position: relative;
  z-index: 1;
  height: 100%;
  display: flex;
  align-items: baseline;
  justify-content: center;
}

.bs-gauge-inner strong {
  color: #f0f9ff;
  font-family: Consolas, monospace;
  font-size: 18px;
}

.bs-gauge-inner small {
  color: #94a3b8;
  font-size: 9px;
}

.bs-gauge-meta b {
  display: block;
  color: #e2e8f0;
  font-size: 12px;
}

.bs-gauge-meta span {
  display: block;
  margin-top: 4px;
  color: #64748b;
  font-size: 10px;
}

.bs-bars {
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 7px;
}

.bs-bar-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.bs-bar-name {
  width: 100px;
  overflow: hidden;
  color: #94a3b8;
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bs-bar-track {
  flex: 1;
  height: 7px;
  overflow: hidden;
  border-radius: 4px;
  background: rgba(51, 65, 85, 0.5);
}

.bs-bar-track i {
  display: block;
  height: 100%;
  border-radius: 4px;
  transition: width 0.4s ease;
}

.bs-bar-value {
  width: 52px;
  color: #e2e8f0;
  font-family: Consolas, monospace;
  font-size: 10px;
  text-align: right;
}

.bs-table {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.bs-table-body {
  flex: 1;
  min-height: 0;
}

.bs-table-row {
  display: grid;
  grid-template-columns: 1.2fr 1fr 0.65fr 0.8fr;
  align-items: center;
  gap: 8px;
  min-height: 27px;
  padding: 0 4px;
  border-bottom: 1px solid rgba(56, 189, 248, 0.07);
  color: #cbd5e1;
  font-size: 10px;
}

.bs-table-head {
  color: #64748b;
  font-size: 9px;
}

.bs-device-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bs-mono {
  color: #7dd3fc;
  font-family: Consolas, monospace;
  font-size: 9px;
}

.bs-status-dot {
  display: inline-block;
  width: 5px;
  height: 5px;
  margin-right: 4px;
  border-radius: 50%;
  background: #fb7185;
}

.bs-status-dot.online {
  background: #34d399;
}

.bs-table-row b {
  color: #e2e8f0;
  font-family: Consolas, monospace;
  font-size: 10px;
}

.bs-server-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 10px;
}

.bs-server-card {
  padding: 9px 10px;
  border: 1px solid rgba(56, 189, 248, 0.1);
  border-radius: 8px;
  background: rgba(8, 25, 43, 0.6);
}

.bs-server-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.bs-server-head b {
  color: #e0f2fe;
  font-size: 12px;
}

.bs-server-head span {
  color: #475569;
  font-family: Consolas, monospace;
  font-size: 9px;
}

.bs-server-sensors {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 7px;
}

.bs-sensor {
  display: inline-flex;
  align-items: baseline;
  gap: 5px;
  padding: 3px 6px;
  border: 1px solid rgba(56, 189, 248, 0.1);
  border-radius: 4px;
  background: rgba(15, 23, 42, 0.45);
}

.bs-sensor small {
  color: #64748b;
  font-size: 9px;
}

.bs-sensor strong {
  color: #cbd5e1;
  font-family: Consolas, monospace;
  font-size: 10px;
}

.bs-sensor.warning {
  border-color: rgba(251, 191, 36, 0.35);
}

.bs-sensor.warning strong {
  color: #fbbf24;
}

.bs-sensor.critical {
  border-color: rgba(251, 113, 133, 0.45);
}

.bs-sensor.critical strong {
  color: #fb7185;
}

.bs-alert-list {
  height: 100%;
}

.bs-alert-item {
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr) 34px;
  gap: 8px;
  align-items: start;
  padding: 6px 0;
  border-bottom: 1px solid rgba(56, 189, 248, 0.07);
}

.bs-alert-level {
  padding: 2px 3px;
  border-radius: 3px;
  color: #fbbf24;
  background: rgba(251, 191, 36, 0.12);
  font-size: 9px;
  text-align: center;
}

.bs-alert-item.critical .bs-alert-level {
  color: #fb7185;
  background: rgba(251, 113, 133, 0.14);
}

.bs-alert-item b {
  display: block;
  overflow: hidden;
  color: #cbd5e1;
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bs-alert-item p {
  margin: 2px 0 0;
  overflow: hidden;
  color: #64748b;
  font-size: 9px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bs-alert-item time {
  color: #475569;
  font-family: Consolas, monospace;
  font-size: 9px;
  text-align: right;
}

.bs-trend {
  height: 100%;
  display: flex;
  align-items: stretch;
  gap: 4px;
  padding-top: 8px;
}

.bs-trend-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  gap: 5px;
  min-width: 0;
}

.bs-trend-bar {
  width: 70%;
  min-height: 4px;
  border-radius: 2px 2px 0 0;
  background: linear-gradient(180deg, #38bdf8, rgba(56, 189, 248, 0.18));
}

.bs-trend-col small {
  color: #475569;
  font-family: Consolas, monospace;
  font-size: 8px;
}

.bs-empty {
  color: #475569;
  font-size: 10px;
  text-align: center;
  padding: 18px 0;
}

.bs-notfound {
  position: relative;
  z-index: 2;
  margin: auto;
  text-align: center;
}

.bs-notfound h2 {
  color: #e2e8f0;
  font-size: 20px;
  margin-bottom: 16px;
}

@media (max-width: 1400px) {
  .bs-header-center {
    display: none;
  }

  .bs-updated {
    display: none;
  }

  .bs-header {
    gap: 10px;
  }

  .bs-header-actions {
    gap: 5px;
  }
}

@media (max-width: 1100px) {
  .bs-header-center {
    display: none;
  }

  .bs-updated {
    display: none;
  }
}

@media (max-width: 720px) {
  .bs-header {
    height: auto;
    min-height: 64px;
    padding: 8px 12px;
    flex-wrap: wrap;
  }

  .bs-header-actions {
    width: 100%;
    justify-content: flex-end;
  }

  .bs-canvas {
    padding: 12px;
  }
}

.bs-widget--topology .bs-widget-body {
  height: calc(100% - 34px);
  padding: 0;
}

.bs-zabbix {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  text-align: center;
}

.bs-zabbix-value {
  color: #38bdf8;
  font-size: clamp(30px, 3.4vw, 62px);
  font-weight: 800;
  line-height: 1;
  letter-spacing: 0.02em;
  text-shadow: 0 0 20px rgba(56, 189, 248, 0.35);
}

.bs-zabbix-value small {
  margin-left: 6px;
  color: #7dd3fc;
  font-size: 0.34em;
  font-weight: 600;
}

.bs-zabbix-meta {
  display: flex;
  flex-direction: column;
  gap: 3px;
  color: #94a3b8;
  font-size: 12px;
}

.bs-zabbix-meta b {
  color: #e2e8f0;
  font-size: 13px;
}

.bs-zabbix-error {
  max-width: 90%;
  color: #fb7185;
  font-size: 11px;
  line-height: 1.5;
}

.bs-website-list {
  display: flex;
  flex-direction: column;
  gap: 1px;
  height: 100%;
}

.bs-website-row {
  display: flex;
  align-items: center;
  gap: 9px;
  min-height: 2.4em;
  padding: 0 0.3em;
  border-bottom: 1px solid rgba(56, 189, 248, 0.08);
}

.bs-website-dot {
  width: 0.5em;
  height: 0.5em;
  flex: 0 0 0.5em;
  border-radius: 50%;
  background: #64748b;
}

.bs-website-dot.online { background: #34d399; box-shadow: 0 0 0.5em #34d399; }
.bs-website-dot.offline { background: #fb7185; box-shadow: 0 0 0.5em #fb7185; }

.bs-website-main {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 0.12em;
  min-width: 0;
}

.bs-website-main b {
  overflow: hidden;
  color: #e2f8ff;
  font-size: 0.9em;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bs-website-main small {
  overflow: hidden;
  color: #7dacbd;
  font-size: 0.68em;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bs-website-value,
.bs-website-cert {
  color: #a8e7f3;
  font-family: monospace;
  font-size: 0.78em;
  white-space: nowrap;
}

.bs-text-widget {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  width: 100%;
  height: 100%;
  padding: 0.45em 0.7em;
  line-height: 1.45;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.bs-text-widget[style*="center"] { justify-content: center; }
.bs-text-widget[style*="right"] { justify-content: flex-end; }
</style>
