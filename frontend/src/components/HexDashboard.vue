<template>
  <section ref="dashboardRef" class="hex-dashboard mx-dash">
    <header class="mx-head">
      <div class="mx-title">
        <span class="mx-kicker">DEVICE METRIC WORKBENCH</span>
        <h1>设备指标工作台</h1>
        <p>按设备聚合全部指标 · 阈值状态实时着色 · 支持批量配置与分页查看</p>
      </div>
      <div class="mx-head-actions">
        <div class="mx-health">
          <span class="normal"><i></i>正常 {{ normalCount }}</span>
          <span class="info"><i></i>提示 {{ infoCount }}</span>
          <span class="warning"><i></i>警告 {{ warningCount }}</span>
          <span class="critical"><i></i>严重 {{ criticalCount }}</span>
          <span class="emergency"><i></i>紧急 {{ emergencyCount }}</span>
        </div>
        <el-button size="small" :disabled="sharedReadOnly" @click="openConfig">
          <el-icon><Setting /></el-icon>指标配置
        </el-button>
        <el-button size="small" @click="refresh">
          <el-icon><Refresh /></el-icon>刷新
        </el-button>
        <el-button size="small" @click="toggleFullscreen">
          <el-icon><FullScreen /></el-icon>全屏
        </el-button>
      </div>
    </header>

    <section class="mx-attention" v-if="attentionItems.length">
      <div class="mx-attention-title"><span>!</span>需关注指标</div>
      <button
        v-for="item in attentionItems.slice(0, 10)"
        :key="item.id"
        type="button"
        class="mx-attention-chip"
        :class="item.severity"
        @click="goDevice(item.deviceId)"
      >
        <b>{{ item.deviceName }}</b>
        <span>{{ item.metricLabel }}</span>
        <em>{{ item.displayValue }}{{ item.unit }}</em>
      </button>
    </section>

    <section class="mx-toolbar">
      <div class="mx-toolbar-copy">
        本页 <strong>{{ pagedGroups.length }}</strong> 张卡片
        <span> / 共 {{ displayGroups.length }} 张</span>
      </div>
      <div class="mx-group-mode">
        <span class="mx-page-label">分组</span>
        <el-radio-group v-model="displayGroupMode" size="small">
          <el-radio-button label="device">按设备</el-radio-button>
          <el-radio-button label="metric">按指标</el-radio-button>
        </el-radio-group>
      </div>
      <div class="mx-live-controls">
        <span class="mx-page-label">刷新</span>
        <el-select v-model="refreshSeconds" size="small" style="width: 82px">
          <el-option :value="5" label="5 秒" />
          <el-option :value="10" label="10 秒" />
          <el-option :value="15" label="15 秒" />
          <el-option :value="30" label="30 秒" />
          <el-option :value="60" label="60 秒" />
          <el-option :value="300" label="5 分钟" />
        </el-select>
        <el-switch v-model="autoCarousel" size="small" active-text="自动滚屏轮播" />
        <div class="mx-unit-control">
          <el-input-number
            v-model="carouselSeconds"
            size="small"
            :min="3"
            :max="600"
            :step="1"
            controls-position="right"
            style="width: 108px"
          />
          <span class="mx-input-unit">秒/页</span>
        </div>
      </div>
      <div class="mx-pager">
        <span class="mx-page-label">每页卡片</span>
        <el-select v-model="pageSize" size="small" style="width: 76px">
          <el-option :value="3" label="3" />
          <el-option :value="4" label="4" />
          <el-option :value="6" label="6" />
          <el-option :value="8" label="8" />
          <el-option :value="9" label="9" />
          <el-option :value="12" label="12" />
        </el-select>
        <span class="mx-input-unit">张/页</span>
        <el-button size="small" circle :disabled="currentPage <= 1" @click="prevPage">
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
        <b>第 {{ currentPage }} / {{ pageCount }} 页</b>
        <el-button size="small" circle :disabled="currentPage >= pageCount" @click="nextPage">
          <el-icon><ArrowRight /></el-icon>
        </el-button>
      </div>
    </section>

    <div v-if="pagedGroups.length" ref="gridScrollRef" class="mx-grid-scroll">
    <div class="mx-grid" :class="`mx-cols-${Math.min(3, pagedGroups.length || 1)}`">
      <article
        v-for="group in pagedGroups"
        :key="group.groupKey || group.deviceId"
        class="mx-device-card"
      >
        <header class="mx-device-head">
          <div class="mx-device-name">
            <span class="mx-device-dot" :class="group.severity"></span>
            <template v-if="displayGroupMode === 'metric'">
              <strong class="mx-metric-group-title">{{ group.metricLabel }}</strong>
              <small>{{ group.deviceCount }} 台设备</small>
            </template>
            <template v-else>
              <button type="button" class="mx-link" @click="goDevice(group.deviceId)">{{ group.deviceName }}</button>
              <small>{{ group.deviceIp || '—' }}</small>
            </template>
          </div>
          <div class="mx-device-meta">
            <span class="mx-type">{{ displayGroupMode === 'metric' ? '指标类型' : (group.deviceTypeText || '设备') }}</span>
            <span class="mx-count">{{ group.items.length }} 指标</span>
            <span v-if="group.emergency" class="mx-badge emergency">紧急 {{ group.emergency }}</span>
            <span v-else-if="group.critical" class="mx-badge critical">严重 {{ group.critical }}</span>
            <span v-else-if="group.warning" class="mx-badge warning">警告 {{ group.warning }}</span>
            <span v-else-if="group.info" class="mx-badge info">提示 {{ group.info }}</span>
            <span v-else class="mx-badge normal">正常</span>
          </div>
        </header>

        <div class="mx-metrics">
          <button
            v-for="item in group.items"
            :key="item.id"
            type="button"
            class="mx-metric"
            :class="[item.severity, { 'no-threshold': !hasThresholds(item.metric, item.deviceId) }]"
            :style="{ '--mx-color': item.color, '--mx-warning': item.warningColor, '--mx-critical': item.criticalColor }"
            @click="goDevice(item.deviceId)"
          >
            <div v-if="displayGroupMode === 'metric'" class="mx-metric-device">
              {{ item.deviceName }}<small>{{ item.deviceIp || '' }}</small>
            </div>
            <div class="mx-metric-top">
              <span class="mx-metric-label">{{ item.metricLabel }}</span>
              <span class="mx-status"><i></i>{{ item.statusText }}</span>
            </div>
            <div class="mx-value">{{ item.displayValue }}<small>{{ item.unit }}</small></div>
            <div class="mx-track"><i :style="{ width: `${Math.min(100, Number(item.percent) || 0)}%` }"></i></div>
            <div class="mx-metric-foot">
              <span v-if="hasThresholds(item.metric, item.deviceId)">预警 {{ item.warning }}{{ item.unit }} · 严重 {{ item.critical }}{{ item.unit }}</span>
              <span v-else>状态指标</span>
            </div>
          </button>
        </div>
      </article>
    </div>
    </div>
    <div v-else class="mx-empty">
      <span>还没有配置任何设备指标</span>
      <el-button type="primary" plain size="small" :disabled="sharedReadOnly" @click="openConfig">去配置指标</el-button>
    </div>
  </section>

    <el-dialog v-model="configVisible" :title="t('dashboard.hexConfigTitle')" width="1080px" top="4vh" class="hex-config-dialog">
      <div v-if="!configReady" class="hex-config-opening">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>正在准备指标配置…</span>
      </div>
      <div v-else class="hex-config-ready">
      <div class="hex-config-picker">
        <aside class="hex-device-tree">
          <div class="hex-picker-head">
            <strong>{{ t('dashboard.hexDeviceTree') }}</strong>
            <span>{{ selectedDraftDevices.length }} / {{ devices.length }} 已选</span>
          </div>
          <el-input
            v-model="pickerKeyword"
            size="small"
            clearable
            :placeholder="t('dashboard.hexSearchDevice')"
            class="hex-device-search"
          >
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
          <div class="hex-device-batch-tools">
            <span>已选 {{ selectedDraftDevices.length }} 台</span>
            <small class="hex-select-hint">单击单选 · Ctrl/Shift 多选 · 勾选多选</small>
            <el-button type="success" plain size="small" class="hex-batch-select-all" @click="selectVisibleDraftDevices">全选可见</el-button>
            <el-button type="warning" plain size="small" class="hex-batch-keep-current" @click="clearDraftDeviceSelection">仅保留当前</el-button>
          </div>
          <div class="hex-device-tree-list">
            <div v-for="group in deviceSelectionGroups" :key="group.key" class="hex-device-type-group">
              <div class="hex-device-type-title">
                <span>{{ group.label }}</span>
                <small>{{ group.devices.length }}</small>
                <span class="hex-group-actions">
                  <el-button link type="primary" size="small" @click.stop="selectGroupDraftDevices(group)">全选本组</el-button>
                  <el-button link type="danger" size="small" @click.stop="deselectGroupDraftDevices(group)">取消本组</el-button>
                </span>
              </div>
              <button
                v-for="device in group.devices"
                :key="device.id"
                type="button"
                class="hex-device-option"
                :class="{ active: draftDeviceId === device.id, selected: isDraftDeviceSelected(device.id) }"
                @click="focusConfiguredDevice(device.id)"
              >
                <span class="hex-device-check" @click.stop="toggleDraftDevice(device.id)">
                  <el-icon v-if="isDraftDeviceSelected(device.id)"><Check /></el-icon>
                </span>
                <span class="hex-device-option-name">{{ device.name }}</span>
                <small>{{ device.ip_address }}</small>
                <span v-if="draftCountFor(device.id)" class="hex-device-option-count">
                  {{ draftCountFor(device.id) }}
                </span>
              </button>
            </div>
            <el-empty v-if="!deviceSelectionGroups.length" :description="t('dashboard.hexNoDeviceMatch')" :image-size="44" />
          </div>
        </aside>

        <section class="hex-metric-picker">
          <template v-if="pickerDevice">
            <div class="hex-metric-picker-head">
              <div>
                <strong>{{ pickerDevice.name }}</strong>
                <small>{{ pickerDevice.ip_address }}</small>
              </div>
              <el-tag size="small" :type="deviceTypeTagType(pickerDevice.device_type)" effect="plain">
                {{ deviceTypeLabel(pickerDevice.device_type) }}
              </el-tag>
            </div>
            <div v-if="selectedDraftDevices.length > 1" class="hex-batch-hint">
              批量模式：指标将同时应用到已选 {{ selectedDraftDevices.length }} 台设备
            </div>
            <div class="hex-metric-picker-hint">
              <span>{{ t('dashboard.hexClickMetricHint') }}</span>
              <span class="hex-picker-selected">
                {{ hexText('selected') }} <b>{{ deviceDraftCount }}</b>
                <em>· {{ hexText('total') }} {{ draft.length }}</em>
              </span>
            </div>
            <div class="hex-picker-toolbar">
              <el-input
                v-model="metricKeyword"
                size="small"
                clearable
                :placeholder="hexText('searchMetric')"
                class="hex-metric-search"
              >
                <template #prefix><el-icon><Search /></el-icon></template>
              </el-input>
              <div class="hex-picker-toolbar-actions">
                <el-button size="small" plain :disabled="!hasUnselectedMetric" @click="selectAllMetrics">
                  {{ hexText('selectAll') }}
                </el-button>
                <el-button size="small" plain :disabled="!deviceDraftCount" @click="clearDeviceMetrics">
                  {{ hexText('clearDevice') }}
                </el-button>
              </div>
            </div>
            <div v-if="pickerDevice?.device_type === 'server'" class="hex-server-hint">
              {{ t('dashboard.hexServerSensorHint') }}
            </div>
            <div class="hex-metric-groups">
              <section v-for="group in metricOptionGroups" :key="group.key" class="hex-metric-group">
                <div class="hex-metric-group-head">
                  <span class="hex-metric-group-name">{{ group.label }}</span>
                  <span class="hex-metric-group-count">
                    {{ group.addedCount }} / {{ group.items.length }}
                  </span>
                  <div class="hex-metric-group-actions">
                    <el-button
                      link
                      type="primary"
                      size="small"
                      :disabled="!groupHasUnselected(group)"
                      @click="selectGroupMetrics(group)"
                    >
                      {{ hexText('selectGroup') }}
                    </el-button>
                    <el-button
                      link
                      type="danger"
                      size="small"
                      :disabled="!group.addedCount"
                      @click="deselectGroupMetrics(group)"
                    >
                      {{ hexText('deselectGroup') }}
                    </el-button>
                  </div>
                </div>
                <div class="hex-metric-grid">
                  <button
                    v-for="metric in group.items"
                    :key="metric.key"
                    type="button"
                    class="hex-metric-option"
                    :class="{ added: isMetricAddedForTargets(metric.key) }"
                    @click="toggleMetric(metric.key)"
                  >
                    <span>{{ metric.label }}</span>
                    <small>{{ metric.unit || t('dashboard.hexStatusMetric') }}</small>
                    <span class="hex-metric-state" :class="{ added: isMetricAddedForTargets(metric.key) }">
                      {{ isMetricAddedForTargets(metric.key) ? '已选' : '未选' }}
                    </span>
                    <el-icon v-if="isMetricAddedForTargets(metric.key)"><Check /></el-icon>
                  </button>
                </div>
              </section>
              <el-empty
                v-if="!metricOptionGroups.length"
                :description="hexText('noMetricMatch')"
                :image-size="44"
              />
            </div>
          </template>
          <el-empty v-else :description="t('dashboard.hexSelectDeviceFirst')" :image-size="54" />
        </section>
      </div>

      <div class="hex-configured-head">
        <div class="hex-configured-title">
          <strong>{{ t('dashboard.hexConfiguredMetrics') }}</strong>
          <span class="hex-configured-count">{{ draft.length }} {{ t('dashboard.hexMetricCount') }}</span>
          <span class="hex-configured-devices">{{ configuredGroups.length }} {{ hexText('devices') }}</span>
        </div>
        <div class="hex-configured-actions">
          <el-select
            v-model="configuredDeviceId"
            class="hex-configured-device-select"
            size="small"
            filterable
            clearable
            :placeholder="'搜索并选择已添加设备'"
            @change="onConfiguredDeviceChange"
          >
            <el-option
              v-for="group in draftGroups"
              :key="group.deviceId"
              :value="group.deviceId"
              :label="`${group.deviceName} · ${group.deviceIp || '无 IP'}`"
            >
              <span>{{ group.deviceName }}</span>
              <small>{{ group.deviceIp || '无 IP' }} · {{ group.items.length }} 项</small>
            </el-option>
          </el-select>
          <small>{{ t('dashboard.hexConfiguredHint') }}</small>
          <el-button v-if="collapsedDraftGroups.length" link type="primary" size="small" @click="expandAllDraftGroups">
            展开全部
          </el-button>
          <el-button size="small" type="primary" plain :disabled="!selectedDraftDevices.length" @click="openBatchPanel">
            批量设置阈值
          </el-button>
          <el-button link type="danger" size="small" :disabled="!draft.length" @click="clearAllMetrics">
            {{ hexText('clearAll') }}
          </el-button>
        </div>
      </div>

      <section v-if="batchPanelVisible" class="hex-batch-panel">
        <div class="hex-batch-panel-head">
          <strong>单一指标批量设置</strong>
          <span>同一指标应用到已选 {{ selectedDraftDevices.length }} 台设备</span>
          <el-button link size="small" @click="batchPanelVisible = false">收起</el-button>
        </div>
        <div class="hex-batch-panel-grid">
          <label>
            <span>监控指标</span>
            <el-select v-model="batchMetricKey" size="small" filterable placeholder="选择指标" style="width: 100%" @change="syncBatchFromMetric">
              <el-option v-for="item in batchMetricOptions" :key="item.key" :label="item.label" :value="item.key" />
            </el-select>
          </label>
          <label>
            <span>预警值</span>
            <el-input-number v-model="batchWarning" :min="0" :step="1" size="small" controls-position="right" style="width: 100%" />
          </label>
          <label>
            <span>预警颜色</span>
            <el-color-picker v-model="batchWarningColor" size="small" :predefine="PRESET_COLORS" />
          </label>
          <label>
            <span>告警值</span>
            <el-input-number v-model="batchCritical" :min="0" :step="1" size="small" controls-position="right" style="width: 100%" />
          </label>
          <label>
            <span>告警颜色</span>
            <el-color-picker v-model="batchCriticalColor" size="small" :predefine="PRESET_COLORS" />
          </label>
          <el-button type="primary" :disabled="!batchMetricKey || !selectedDraftDevices.length" @click="applyBatchThreshold">
            应用到已选设备
          </el-button>
        </div>
      </section>

      <div v-if="configuredGroups.length" class="hex-config-groups">
        <section v-for="group in configuredGroups" :key="group.deviceId" :id="`hex-config-group-${group.deviceId}`" class="hex-config-group">
          <div class="hex-config-group-head" @click="toggleDraftGroup(group.deviceId)">
            <el-icon class="hex-group-caret" :class="{ collapsed: isDraftGroupCollapsed(group.deviceId) }">
              <ArrowDown />
            </el-icon>
            <span class="hex-config-group-name">{{ group.deviceName }}</span>
            <el-tag size="small" :type="group.tagType" effect="plain">{{ group.typeLabel }}</el-tag>
            <span class="hex-config-group-count">{{ group.items.length }} {{ t('dashboard.hexMetricCount') }}</span>
            <el-button link type="danger" size="small" @click.stop="removeDraftGroup(group)">
              {{ hexText('removeGroup') }}
            </el-button>
          </div>
          <div v-if="!isDraftGroupCollapsed(group.deviceId)" class="hex-config-list">
            <div v-for="(item, index) in group.items" :key="item.id" class="hex-config-row" :id="`hex-config-item-${item.id}`" :class="{ invalid: invalidItemId === item.id }">
              <div v-if="invalidItemId === item.id" class="hex-config-invalid-tip">
                <span>⚠</span>{{ invalidReason }}
              </div>
              <div class="hex-config-main">
                <span class="hex-config-index">{{ String(index + 1).padStart(2, '0') }}</span>
                <span class="hex-config-metric-name">{{ metricLabel(item.metric, item.deviceId) }}</span>
                <div class="hex-config-actions">
                  <el-button link type="primary" size="small" @click="startBatchFromItem(item)">批量</el-button>
                  <el-button link :disabled="index === 0" @click="moveGroupItem(group, index, -1)">↑</el-button>
                  <el-button link :disabled="index === group.items.length - 1" @click="moveGroupItem(group, index, 1)">↓</el-button>
                  <el-button link type="danger" @click="removeDraftItem(item)">{{ t('common.delete') }}</el-button>
                </div>
              </div>

              <div v-if="hasThresholds(item.metric, item.deviceId)" class="hex-config-thresholds">
                <span class="hex-threshold-label">{{ thresholdDirection(item) === 'lower' ? t('dashboard.hexWarningAtLower') : t('dashboard.hexWarningAt') }}</span>
                <el-input-number
                  v-model="item.warning"
                  :min="0"
                  :max="metricMax(item.metric, item.deviceId)"
                  :step="1"
                  size="small"
                  controls-position="right"
                  style="width: 92px"
                />
                <el-color-picker v-model="item.warningColor" size="small" :predefine="PRESET_COLORS" />
                <span class="hex-threshold-label">{{ thresholdDirection(item) === 'lower' ? t('dashboard.hexCriticalAtLower') : t('dashboard.hexCriticalAt') }}</span>
                <el-input-number
                  v-model="item.critical"
                  :min="0"
                  :max="metricMax(item.metric, item.deviceId)"
                  :step="1"
                  size="small"
                  controls-position="right"
                  style="width: 92px"
                />
                <el-color-picker v-model="item.criticalColor" size="small" :predefine="PRESET_COLORS" />
                <span v-if="assetRuleLock(item).warning !== null || assetRuleLock(item).critical !== null" class="hex-threshold-hint">与自定义告警规则同步</span>
              </div>
              <div v-else class="hex-config-thresholds">
                <span class="hex-threshold-label">{{ t('dashboard.hexAbnormalColor') }}</span>
                <el-color-picker v-model="item.criticalColor" size="small" :predefine="PRESET_COLORS" />
                <span class="hex-threshold-hint">{{ t('dashboard.hexStatusHint') }}</span>
              </div>
            </div>
          </div>
        </section>
      </div>
      <el-empty v-else :description="configuredEmptyText" :image-size="60" />
      </div>

      <template #footer>
        <el-button @click="configVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" @click="saveConfig">{{ t('dashboard.hexSave') }}</el-button>
      </template>
    </el-dialog>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { GridLayout, GridItem } from 'grid-layout-plus'
import { alertRuleApi, assetApi, monitorApi } from '@/api'
import { DEVICE_TYPES, deviceTypeLabel, deviceTypeTagType } from '@/constants/device'
import { t, locale } from '@/i18n'
import { refreshMs } from '@/store/settings'
import HexGauge from '@/components/HexGauge.vue'
import { temperatureDisplayName } from '@/utils/serverComponentLabels'

const HEX_CONFIG_KEY = 'nms_hex_dashboard_v1'
const HEX_LAYOUT_KEY = 'nms_hex_dashboard_positions_v1'
const HEX_MODE_KEY = 'nms_hex_dashboard_mode_v1'
const HEX_ROW_SIZE = 6
const PRESET_COLORS = ['#34d399', '#38bdf8', '#a78bfa', '#fbbf24', '#fb7185', '#f97316', '#ef4444']

// 配置弹窗内的补充文案（沿用 i18n 语言设置，避免改动全局词条文件）
const HEX_LOCAL_TEXT = {
  'zh-CN': {
    searchMetric: '搜索指标（名称 / 标识 / 单位）',
    selectAll: '全选指标',
    clearDevice: '清空指标',
    clearAll: '清空全部指标',
    removeGroup: '移除本设备',
    selectGroup: '全选本组',
    deselectGroup: '取消本组',
    selected: '已选',
    total: '全部',
    devices: '台设备',
    groupBase: '基础指标',
    groupInterface: '网络接口指标',
    groupSensor: '服务器传感器指标',
    groupCustom: '自定义 / MIB 指标',
    noMetricMatch: '没有匹配的指标',
  },
  'en-US': {
    searchMetric: 'Search metrics (name / key / unit)',
    selectAll: 'Select metrics',
    clearDevice: 'Clear metrics',
    clearAll: 'Clear all metrics',
    removeGroup: 'Remove device',
    selectGroup: 'Select group',
    deselectGroup: 'Deselect group',
    selected: 'Selected',
    total: 'All',
    devices: 'devices',
    groupBase: 'Base metrics',
    groupInterface: 'Interface metrics',
    groupSensor: 'Server sensors',
    groupCustom: 'Custom / MIB metrics',
    noMetricMatch: 'No matching metric',
  },
}

function hexText(key) {
  const text = HEX_LOCAL_TEXT[locale.value] || HEX_LOCAL_TEXT['zh-CN']
  return text[key] ?? HEX_LOCAL_TEXT['zh-CN'][key] ?? key
}

// 指标选项分组顺序：基础 → 接口 → 服务器传感器 → 自定义 / MIB
const METRIC_GROUP_ORDER = ['base', 'interface', 'sensor', 'custom']

function metricGroupLabel(group) {
  if (group === 'base') return hexText('groupBase')
  if (group === 'interface') return hexText('groupInterface')
  if (group === 'sensor') return hexText('groupSensor')
  return hexText('groupCustom')
}

// 多指标面板栅格：超过 8 个指标时使用自适应列 + 内部滚动，避免被裁切
function metricGridClass(count) {
  const total = Number(count) || 0
  return total > 8 ? 'metrics-many' : `metrics-${Math.min(total, 8)}`
}

const router = useRouter()
const props = defineProps({
  sharedConfig: { type: Object, default: null },
  sharedReadOnly: { type: Boolean, default: false },
})
const emit = defineEmits(['shared-change'])
const metricThresholds = ref({
  cpu_usage: 80, memory_usage: 85, temperature: 80,
  temperature_critical: 90, disk_usage: 90,
})

function defaultsFor(metric, device = null) {
  const meta = metricMeta(metric, device)
  return {
    warning: meta.warning,
    critical: meta.critical,
    warningColor: '#fbbf24',
    criticalColor: '#fb7185',
  }
}

function ruleMatchesMetric(rule, metric) {
  if (!rule || rule.enabled === false) return false
  if (String(rule.metric || '') === String(metric || '')) return true
  if (rule.metric === 'custom' && String(rule.custom_key || '') === String(metric || '')) return true
  if (rule.metric === 'fan_speed' && metric === 'srv_fan_speed') return true
  return false
}

// 自定义告警规则是阈值唯一来源：仪表盘不再单独维护一套数值。
function assetRuleThresholds(metric, device = null) {
  const rules = (device?.alert_rules || []).filter((rule) => ruleMatchesMetric(rule, metric))
  if (!rules.length) return { warning: null, critical: null }
  const direction = metricMeta(metric, device).direction || 'higher'
  const severity = (rule) => ['critical', 'emergency'].includes(String(rule.level || '').toLowerCase())
    ? 'critical' : 'warning'
  const pick = (items) => {
    const values = items.map((rule) => Number(rule.threshold)).filter((value) => Number.isFinite(value))
    if (!values.length) return null
    // 同一级别多条规则时，取先触发的阈值；严重级别取更靠后的阈值。
    return direction === 'lower' ? Math.max(...values) : Math.min(...values)
  }
  const warnings = rules.filter((rule) => severity(rule) === 'warning')
  const criticals = rules.filter((rule) => severity(rule) === 'critical')
  let warning = pick(warnings)
  let critical = pick(criticals)
  if (warning !== null && critical !== null) {
    if (direction === 'lower' ? critical >= warning : critical <= warning) {
      ;[warning, critical] = [critical, warning]
    }
  }
  return { warning, critical }
}

function assetRuleLock(item) {
  const device = devices.value.find((row) => String(row.id) === String(item.deviceId))
  return assetRuleThresholds(item.metric, device)
}

function normalizeItem(item, device = null) {
  const defaults = defaultsFor(item.metric, device)
  const rule = assetRuleThresholds(item.metric, device)
  return {
    ...item,
    warning: rule.warning !== null ? rule.warning : (item.warning === null || item.warning === undefined ? defaults.warning : Number(item.warning)),
    critical: rule.critical !== null ? rule.critical : (item.critical === null || item.critical === undefined ? defaults.critical : Number(item.critical)),
    warningColor: item.warningColor || defaults.warningColor,
    criticalColor: item.criticalColor || defaults.criticalColor,
  }
}

function metricMax(metric, device = null) {
  return metricMeta(metric, device).max
}

const HEX_METRICS = computed(() => {
  const thresholds = metricThresholds.value
  return [
    { key: 'cpu_usage', label: t('dashboard.cpuUsage'), unit: '%', max: 100, color: '#38bdf8', kind: 'base', warning: thresholds.cpu_usage, critical: Math.min(100, thresholds.cpu_usage + 10) },
    { key: 'memory_usage', label: t('dashboard.memoryUsage'), unit: '%', max: 100, color: '#a78bfa', kind: 'base', warning: thresholds.memory_usage, critical: Math.min(100, thresholds.memory_usage + 10) },
    { key: 'disk_usage', label: '磁盘使用率', unit: '%', max: 100, color: '#f59e0b', kind: 'base', warning: thresholds.disk_usage, critical: Math.min(100, thresholds.disk_usage + 5) },
    { key: 'temperature', label: t('dashboard.maxTemperature'), unit: '°C', max: 150, color: '#fb7185', kind: 'base', warning: thresholds.temperature, critical: thresholds.temperature_critical },
    { key: 'power_status', label: t('dashboard.powerStatus'), unit: '', max: 100, color: '#34d399', kind: 'power', warning: null, critical: null },
    { key: 'warranty_days_left', label: '维保剩余天数', unit: '天', max: 365, color: '#fbbf24', kind: 'base', warning: 30, critical: 5, direction: 'lower' },
    { key: 'alert_count', label: '未处理告警', unit: '条', max: 100, color: '#fb7185', kind: 'base', warning: 1, critical: 5 },
  ]
})

// 网络设备接口类指标：接口数量、可用率、流量、错误与峰值利用率
const NETWORK_IF_METRICS = computed(() => [
  { key: 'if_available', label: t('dashboard.ifAvailable'), unit: '%', max: 100, color: '#22c55e', kind: 'interface', precision: 1, warning: 90, critical: 70, direction: 'lower' },
  { key: 'if_up', label: t('dashboard.ifUp'), unit: '个', max: 1, color: '#38bdf8', kind: 'interface', precision: 0, warning: null, critical: null, noThreshold: true },
  { key: 'if_down', label: t('dashboard.ifDown'), unit: '个', max: 1, color: '#fb7185', kind: 'interface', precision: 0, warning: null, critical: null, noThreshold: true },
  { key: 'if_total_bps', label: t('dashboard.ifTotalBps'), unit: 'bps', max: 1, color: '#22d3ee', kind: 'bps', precision: 1, warning: null, critical: null, noThreshold: true },
  { key: 'if_in_bps', label: t('dashboard.ifInBps'), unit: 'bps', max: 1, color: '#38bdf8', kind: 'bps', precision: 1, warning: null, critical: null, noThreshold: true },
  { key: 'if_out_bps', label: t('dashboard.ifOutBps'), unit: 'bps', max: 1, color: '#a78bfa', kind: 'bps', precision: 1, warning: null, critical: null, noThreshold: true },
  { key: 'if_errors', label: t('dashboard.ifErrors'), unit: '个', max: 1000, color: '#f59e0b', kind: 'interface', precision: 0, warning: 1, critical: 100 },
  { key: 'if_max_util', label: t('dashboard.ifMaxUtil'), unit: '%', max: 100, color: '#fb7185', kind: 'interface', precision: 1, warning: 70, critical: 90 },
])

const SERVER_KIND_META = {
  temperature: { color: '#fb7185', max: 150, warning: 80, critical: 90, precision: 1 },
  voltage: { color: '#38bdf8', max: 300, warning: 240, critical: 260, precision: 1 },
  current: { color: '#a78bfa', max: 30, warning: 10, critical: 15, precision: 2 },
  watts: { color: '#f59e0b', max: 3000, warning: 900, critical: 1500, precision: 0 },
  percent: { color: '#22d3ee', max: 100, warning: 80, critical: 90, precision: 1 },
  fault: { color: '#34d399', max: 2, warning: null, critical: 2, precision: 0 },
  value: { color: '#22d3ee', max: 10000, warning: null, critical: null, precision: 1 },
}

// 服务器设备即使还没保存传感器 OID，也先展示这些可选指标，便于统一配置球体
const SERVER_SENSOR_DEFS = [
  { key: 'srv_cpu_temp', name: 'CPU 温度', unit: '°C', kind: 'temperature' },
  { key: 'srv_mem_fault', name: '内存物理状态', unit: '', kind: 'fault' },
  { key: 'srv_power_voltage', name: '电源电压', unit: 'V', kind: 'voltage' },
  { key: 'srv_power_current', name: '电源电流', unit: 'A', kind: 'current' },
  { key: 'srv_power_watts', name: '电源功率', unit: 'W', kind: 'watts' },
  { key: 'srv_disk_fault', name: '硬盘状态', unit: '', kind: 'fault' },
  { key: 'srv_disk_usage', name: '硬盘使用率', unit: '%', kind: 'percent' },
  { key: 'srv_inlet_temp', name: '进气温度', unit: '°C', kind: 'temperature' },
  { key: 'srv_exhaust_temp', name: '排气温度', unit: '°C', kind: 'temperature' },
  { key: 'srv_fan_speed', name: '风扇转速', unit: 'RPM', kind: 'value' },
  { key: 'srv_fan_fault', name: '风扇状态', unit: '', kind: 'fault' },
]
const SERVER_SENSOR_BY_KEY = new Map(SERVER_SENSOR_DEFS.map((item) => [item.key, item]))
const LEGACY_SERVER_SENSOR_LABELS = {
  srv_mem_fault: '内存故障',
  srv_disk_fault: '物理硬盘故障',
  srv_inlet_temp: '进风温度',
  srv_exhaust_temp: '排风温度',
}

function serverSensorLabel(sensor) {
  const def = SERVER_SENSOR_BY_KEY.get(sensor.key)
  const legacy = LEGACY_SERVER_SENSOR_LABELS[sensor.key]
  if (def && (!sensor.name || sensor.name === legacy)) return def.name
  return sensor.name || sensor.key
}

function inferServerKind(key) {
  if (key.includes('fault')) return 'fault'
  if (key.includes('watt')) return 'watts'
  if (key.includes('disk_usage')) return 'percent'
  if (key.includes('temp')) return 'temperature'
  if (key.includes('voltage')) return 'voltage'
  if (key.includes('current')) return 'current'
  return 'value'
}

function hasBoundaryTempComponent(device, kind) {
  const components = device?.metric?.components || device?.metric?.custom?.server_components || {}
  const pattern = kind === 'inlet' ? /inlet|进气|进风/i : /exhaust|排气|排风/i
  return (components.temperatures || []).some((item) => pattern.test(String(item.name || '')))
}

function serverMetricDefs(device) {
  const configured = (device?.server_sensors || []).filter((sensor) => sensor?.key)
  const known = new Set(configured.map((sensor) => sensor.key))
  const components = device?.metric?.components || device?.metric?.custom?.server_components || {}
  const hasPsuComponents = (components.power_supplies || []).length > 0
  const hasFanComponents = (components.fans || []).length > 0
  const hasInletComponent = hasBoundaryTempComponent(device, 'inlet')
  const hasExhaustComponent = hasBoundaryTempComponent(device, 'exhaust')
  const presetSensors = SERVER_SENSOR_DEFS.filter((sensor) => {
    if (hasPsuComponents && ['srv_power_watts', 'srv_power_voltage', 'srv_power_current'].includes(sensor.key)) return false
    if (hasFanComponents && ['srv_fan_speed', 'srv_fan_fault'].includes(sensor.key)) return false
    if (hasInletComponent && sensor.key === 'srv_inlet_temp') return false
    if (hasExhaustComponent && sensor.key === 'srv_exhaust_temp') return false
    return !known.has(sensor.key)
  })
  const sensors = device?.device_type === 'server'
    ? [...configured, ...presetSensors]
    : configured
  return sensors.map((sensor) => {
    const kind = sensor.kind || inferServerKind(sensor.key || '')
    const meta = SERVER_KIND_META[kind] || SERVER_KIND_META.value
    return {
      key: sensor.key,
      label: serverSensorLabel(sensor),
      unit: sensor.unit || '',
      max: meta.max,
      color: meta.color,
      kind,
      warning: meta.warning,
      critical: meta.critical,
      precision: meta.precision,
      group: 'sensor',
    }
  })
}

// 服务器组件级指标：每个温度探头、风扇、电源和硬盘都能单独上球
function componentMetricDefs(device) {
  const components = device?.metric?.components || device?.metric?.custom?.server_components || {}
  if (!components || !Object.keys(components).length) return []
  const defs = []
  const add = (kind, items, labelKey, unit, config) => {
    (items || []).forEach((item, index) => {
      defs.push({
        key: `srv_component_${kind}_${index}`,
        label: labelKey ? `${labelKey} · ${item.name || `#${index + 1}`}` : (item.name || `#${index + 1}`),
        unit,
        max: config.max,
        color: config.color,
        kind: config.kind,
        warning: config.warning,
        critical: config.critical,
        precision: config.precision,
        group: 'sensor',
      })
    })
  }
  add('temp', components.temperatures.map((item) => ({ ...item, name: temperatureDisplayName(item.name) })), '', '°C', { max: 150, color: '#fb7185', kind: 'temperature', warning: 80, critical: 90, precision: 1 })
  add('fan', components.fans, '风扇', 'RPM', { max: 15000, color: '#38bdf8', kind: 'value', warning: null, critical: null, precision: 0 })
  // 每个实际电源分别展示功率和电压，名称使用采集到的 PS1/PS2 等
  ;(components.power_supplies || []).forEach((item, index) => {
    const psuName = item.name || `PS${index + 1}`
    defs.push({ key: `srv_component_psu_watts_${index}`, label: `电源功率 · ${psuName}`, unit: 'W', max: 3000, color: '#f59e0b', kind: 'watts', warning: 900, critical: 1500, precision: 0, group: 'sensor' })
    defs.push({ key: `srv_component_psu_voltage_${index}`, label: `电源电压 · ${psuName}`, unit: 'V', max: 300, color: '#38bdf8', kind: 'voltage', warning: 240, critical: 260, precision: 1, group: 'sensor' })
  })
  add('disk', components.disks, '硬盘容量', 'GB', { max: 10000, color: '#22d3ee', kind: 'value', warning: null, critical: null, precision: 2 })
  return defs
}

// 自定义 / MIB 指标：设备已声明的 custom_metrics 以及采集值里实际出现的 key
function customMetricDefs(device) {
  const defs = []
  const known = new Set()
  const push = (raw, fallbackKey = '') => {
    const key = String(raw?.key || fallbackKey || '')
    if (!key || known.has(key)) return
    known.add(key)
    const kind = raw?.kind || inferServerKind(key)
    const meta = SERVER_KIND_META[kind] || SERVER_KIND_META.value
    defs.push({
      key,
      label: raw?.name || key,
      unit: raw?.unit || '',
      max: meta.max,
      color: meta.color,
      kind,
      warning: meta.warning,
      critical: meta.critical,
      precision: meta.precision,
      group: 'custom',
    })
  }
  ;(device?.custom_metrics || []).forEach((item) => push(item))
  Object.keys(device?.metric?.custom || {}).forEach((key) => push({ key, name: key }))
  return defs
}

function metricMeta(key, device) {
  const base = HEX_METRICS.value.find((item) => item.key === key)
  if (base) return base
  const interfaceMeta = NETWORK_IF_METRICS.value.find((item) => item.key === key)
  if (interfaceMeta) {
    const summary = device ? interfaceSummaries.value[device.id] : null
    const meta = { ...interfaceMeta }
    if (key === 'if_up' || key === 'if_down') {
      meta.max = Math.max(1, Number(summary?.total) || 1)
    } else if (key === 'if_total_bps' || key === 'if_in_bps' || key === 'if_out_bps') {
      meta.max = Math.max(1, Number(summary?.capacity_bps) || 1)
    }
    return meta
  }
  const sensor = serverMetricDefs(device).find((item) => item.key === key)
  if (sensor) return sensor
  const component = componentMetricDefs(device).find((item) => item.key === key)
  if (component) return component
  const customSensor = customMetricDefs(device).find((item) => item.key === key)
  if (customSensor) return customSensor
  const kind = inferServerKind(key)
  const meta = SERVER_KIND_META[kind] || SERVER_KIND_META.value
  return {
    key,
    label: key,
    unit: '',
    max: meta.max,
    color: meta.color,
    kind,
    warning: meta.warning,
    critical: meta.critical,
    precision: meta.precision,
  }
}

function metricVisual(key, kind = '', label = '') {
  const value = String(key || '').toLowerCase()
  if (value.startsWith('if_') || /(network|interface|ethernet|port|wan|lan)/.test(value)) return 'network'
  if (value.includes('fan')) return 'fan'
  if (/(disk|storage|hdd|ssd)/.test(value)) return 'disk'
  if (value.includes('cpu') && !value.includes('temp')) return 'cpu'
  if (/(memory|mem_|ram)/.test(value)) return 'memory'
  if (value.includes('temp') || kind === 'temperature') return 'temperature'
  if (/(power|voltage|current|watt|ups)/.test(value)
    || ['voltage', 'current', 'watts', 'power'].includes(kind)) return 'power'
  // 自定义传感器 key 可能是任意标识，补充按中文名称识别
  const text = String(label || '')
  if (/风扇/.test(text)) return 'fan'
  if (/硬盘|磁盘|存储/.test(text)) return 'disk'
  if (/内存/.test(text)) return 'memory'
  if (/CPU|处理器/i.test(text)) return 'cpu'
  if (/温度|热量/.test(text)) return 'temperature'
  if (/电源|电压|电流|功率/.test(text)) return 'power'
  if (/接口|网卡|流量|端口/.test(text)) return 'network'
  return ''
}

const devices = ref([])
const assetGroups = ref([])
const interfaceSummaries = ref({})
const metricAlertLevels = ref({})
const SEVERITY_RANK = { muted: 0, normal: 1, info: 2, warning: 3, critical: 4, emergency: 5 }
const ALERT_METRIC_ALIASES = {
  cpu: 'cpu_usage',
  memory: 'memory_usage',
  temperature: 'temperature',
  disk: 'disk_usage',
  power: 'power_status',
  power_status: 'power_status',
  storage_disk_fault: 'disk_usage',
  srv_disk_fault: 'disk_usage',
  srv_fan_fault: 'fan_speed',
  srv_mem_fault: 'memory_usage',
  warranty: 'warranty_days_left',
}

function worseSeverity(a, b) {
  return (SEVERITY_RANK[b] || 0) > (SEVERITY_RANK[a] || 0) ? b : (a || b || 'normal')
}
const configVisible = ref(false)
const configReady = ref(false)
const draft = ref([])
const draftDeviceId = ref(null)
const draftDeviceIds = ref([])
const lastSelectedDeviceId = ref(null)
const batchPanelVisible = ref(false)
const batchMetricKey = ref('')
const batchWarning = ref(80)
const batchCritical = ref(90)
const batchWarningColor = ref('#fbbf24')
const batchCriticalColor = ref('#fb7185')
const invalidItemId = ref(null)
const invalidReason = ref('')
const pickerKeyword = ref('')
const metricKeyword = ref('')
const configuredDeviceId = ref(null)
const collapsedDraftGroups = ref([])
let draftSeq = 0
let refreshTimer = null

function readConfig() {
  if (props.sharedConfig && Array.isArray(props.sharedConfig.config)) {
    return props.sharedConfig.config
  }
  try {
    const raw = localStorage.getItem(HEX_CONFIG_KEY)
    if (raw === null) return null
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : null
  } catch {
    return null
  }
}

const savedConfig = readConfig()
const config = ref(Array.isArray(savedConfig) ? savedConfig.map(normalizeItem) : [])
const seeded = ref(Array.isArray(savedConfig))

function sharedSnapshot() {
  return {
    config: JSON.parse(JSON.stringify(config.value || [])),
    mode: layoutMode.value,
    fontScale: fontScale.value,
    layout: {
      ...readPositions(),
      [layoutMode.value]: gridLayout.value.map(({ i, x, y, w, h }) => ({ i, x, y, w, h })),
      mode: layoutMode.value,
    },
  }
}

function persistConfig() {
  if (!props.sharedReadOnly) {
    try {
      localStorage.setItem(HEX_CONFIG_KEY, JSON.stringify(config.value))
    } catch {
      /* 忽略存储异常 */
    }
  }
  emit('shared-change', sharedSnapshot())
}

function diskComponentState(device, key) {
  const match = String(key || '').match(/^srv_component_disk_(\d+)$/)
  if (!match || !device?.metric) return null
  const components = device.metric.components || device.metric.custom?.server_components || {}
  const disk = (components.disks || [])[Number(match[1])]
  if (!disk) return null
  const text = `${disk.status || ''} ${disk.status_label || ''}`.toLowerCase()
  if (text.includes('standby') || text.includes('spun down') || text.includes('休眠')) return 'standby'
  if (/(fault|fail|degraded|warning|critical|offline|missing|predictive|error|bad|unknown|未知|降级|故障|离线|缺位)/.test(text)) return 'fault'
  return 'ok'
}

function metricRawValue(device, key) {
  if (key.startsWith('if_')) {
    const summary = interfaceSummaries.value[device?.id]
    if (!summary || !summary.total) return null
    const map = {
      if_available: 'available',
      if_up: 'up',
      if_down: 'down',
      if_total_bps: 'total_bps',
      if_in_bps: 'in_bps',
      if_out_bps: 'out_bps',
      if_errors: 'errors',
      if_max_util: 'max_util',
    }
    const value = summary[map[key]]
    return value === null || value === undefined ? null : Number(value)
  }
  if (!device?.metric) return null
  if (key === 'power_status') return device.metric.power_status || null
  if (['cpu_usage', 'memory_usage', 'temperature', 'disk_usage', 'alert_count'].includes(key)) {
    const value = device.metric[key]
    return value === null || value === undefined ? null : Number(value)
  }
  if (key === 'warranty_days_left') {
    const value = device.warranty_days_left
    return value === null || value === undefined ? null : Number(value)
  }
  if (key.startsWith('srv_component_')) {
    const parts = key.split('_')
    const kind = parts[2]
    const components = device.metric.components || device.metric.custom?.server_components || {}
    const arrays = { temp: 'temperatures', fan: 'fans', psu: 'power_supplies', disk: 'disks' }
    if (kind === 'psu') {
      const subtype = parts[3]
      const legacy = /^\d+$/.test(subtype)
      const index = Number(legacy ? subtype : parts[4])
      const item = (components.power_supplies || [])[index]
      if (!item) return null
      if (!legacy && subtype === 'voltage') return item.voltage === null || item.voltage === undefined ? null : Number(item.voltage)
      if (legacy || subtype === 'watts') return item.watts === null || item.watts === undefined ? null : Number(item.watts)
      return null
    }
    const index = Number(parts[3])
    const item = (components[arrays[kind]] || [])[index]
    if (!item) return null
    if (kind === 'temp') return Number(item.value)
    if (kind === 'fan') return Number(item.value)
    if (kind === 'disk') return item.size_gb === null || item.size_gb === undefined ? null : Number(item.size_gb)
    return null
  }
  const custom = device.metric.custom || {}
  if (key.startsWith('srv_')) {
    const components = device.metric.components || custom.server_components || {}
    const temps = components.temperatures || []
    const fans = components.fans || []
    const psus = components.power_supplies || []
    const named = (pattern) => temps.find((item) => pattern.test(String(item.name || '')))
    if (key === 'srv_power_watts') {
      const vals = psus.map((item) => Number(item.watts)).filter((v) => Number.isFinite(v))
      return vals.length ? vals.reduce((a, b) => a + b, 0) : (custom[key] ?? null)
    }
    if (key === 'srv_power_voltage') {
      const vals = psus.map((item) => Number(item.voltage)).filter((v) => Number.isFinite(v))
      return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : (custom[key] ?? null)
    }
    if (key === 'srv_fan_speed') {
      const vals = fans.map((item) => Number(item.value)).filter((v) => Number.isFinite(v))
      return vals.length ? Math.max(...vals) : (custom[key] ?? null)
    }
    if (key === 'srv_cpu_temp') {
      const item = named(/cpu|处理器/i) || temps[0]
      return item ? Number(item.value) : (custom[key] ?? null)
    }
    if (key === 'srv_inlet_temp') {
      const item = named(/inlet|进气|进风/i)
      return item ? Number(item.value) : (custom[key] ?? null)
    }
    if (key === 'srv_exhaust_temp') {
      const item = named(/exhaust|排气|排风/i)
      return item ? Number(item.value) : (custom[key] ?? null)
    }
  }
  const value = custom[key]
  return value === null || value === undefined ? null : Number(value)
}

function formatBpsParts(value) {
  const number = Number(value) || 0
  if (number >= 1_000_000_000) return { value: (number / 1_000_000_000).toFixed(2), unit: 'Gbps' }
  if (number >= 1_000_000) return { value: (number / 1_000_000).toFixed(2), unit: 'Mbps' }
  if (number >= 1_000) return { value: (number / 1_000).toFixed(1), unit: 'Kbps' }
  return { value: number.toFixed(0), unit: 'bps' }
}

const hexItems = computed(() =>
  config.value.map((item) => {
    const device = devices.value.find((row) => row.id === item.deviceId)
    const meta = metricMeta(item.metric, device)
    const raw = device ? metricRawValue(device, item.metric) : null
    const defaults = defaultsFor(item.metric, device)
    const warning = item.warning === null || item.warning === undefined ? defaults.warning : Number(item.warning)
    const critical = item.critical === null || item.critical === undefined ? defaults.critical : Number(item.critical)
    let displayValue = '--'
    let percent = 0
    let statusText = t('dashboard.hexNoData')
    let severity = 'muted'
    let color = meta.color
    let unit = meta.unit

    if (!device) {
      statusText = t('dashboard.hexMissingDevice')
    } else if (raw !== null) {
      const diskState = diskComponentState(device, item.metric)
      if (diskState === 'fault') {
        displayValue = '故障'
        percent = 0
        statusText = '故障'
        severity = 'emergency'
        color = item.criticalColor || '#fb7185'
        unit = ''
      } else if (diskState === 'standby') {
        displayValue = '休眠'
        percent = 0
        statusText = '休眠'
        severity = 'normal'
        color = meta.color
        unit = ''
      } else if (item.metric === 'power_status') {
        const normal = raw === 'normal'
        displayValue = normal ? t('dashboard.normal') : t('dashboard.abnormal')
        percent = normal ? 100 : 0
        statusText = normal ? t('dashboard.hexNormal') : t('dashboard.hexAbnormal')
        severity = normal ? 'normal' : 'critical'
        color = normal ? '#34d399' : (item.criticalColor || '#fb7185')
        unit = ''
      } else if (meta.kind === 'fault') {
        const normal = Number(raw) <= 1
        displayValue = normal ? t('dashboard.hexNormal') : t('dashboard.hexAbnormal')
        percent = normal ? 100 : 0
        statusText = normal ? t('dashboard.hexNormal') : t('dashboard.hexAbnormal')
        severity = normal ? 'normal' : 'critical'
        color = normal ? '#34d399' : (item.criticalColor || '#fb7185')
        unit = ''
      } else {
        const precision = meta.precision ?? 1
        if (meta.kind === 'bps') {
          const formatted = formatBpsParts(raw)
          displayValue = formatted.value
          unit = formatted.unit
        } else {
          displayValue = Number(raw).toFixed(precision)
        }
        percent = Math.max(0, Math.min(100, (Number(raw) / Math.max(1, meta.max)) * 100))
        if (item.metric === 'if_down') {
          if (Number(raw) > 0) {
            severity = 'critical'
            statusText = t('dashboard.hexAbnormal')
            color = item.criticalColor || '#fb7185'
          } else {
            severity = 'normal'
            statusText = t('dashboard.hexNormal')
            color = meta.color
          }
        } else if (meta.direction === 'lower') {
          if (critical !== null && Number(raw) <= critical) {
            severity = 'critical'
            statusText = t('dashboard.hexCritical')
            color = item.criticalColor || '#fb7185'
          } else if (warning !== null && Number(raw) <= warning) {
            severity = 'warning'
            statusText = t('dashboard.hexWarning')
            color = item.warningColor || '#fbbf24'
          } else {
            severity = 'normal'
            statusText = t('dashboard.hexNormal')
            color = meta.color
          }
        } else if (critical !== null && Number(raw) >= critical) {
          severity = 'critical'
          statusText = t('dashboard.hexCritical')
          color = item.criticalColor || '#fb7185'
        } else if (warning !== null && Number(raw) >= warning) {
          severity = 'warning'
          statusText = t('dashboard.hexWarning')
          color = item.warningColor || '#fbbf24'
        } else {
          severity = 'normal'
          statusText = t('dashboard.hexNormal')
          color = meta.color
        }
      }
    }

    const alertLevel = metricAlertLevels.value[`${item.deviceId}|${item.metric}`] || ''
    const effectiveSeverity = alertLevel
      ? worseSeverity(severity, alertLevel)
      : severity

    return {
      id: `${item.deviceId}-${item.metric}`,
      deviceName: device?.name || t('dashboard.hexMissingDevice'),
      deviceIp: device?.ip_address || '',
      metricLabel: meta.label,
      displayValue,
      unit,
      percent,
      color,
      statusText,
      statusAlert: ['info', 'warning', 'critical', 'emergency'].includes(effectiveSeverity),
      severity: effectiveSeverity,
      metricSeverity: severity,
      alertLevel,
      metric: item.metric,
      visual: metricVisual(item.metric, meta.kind, meta.label),
      deviceId: item.deviceId,
      warning,
      critical,
    }
  })
)

const normalCount = computed(() => hexItems.value.filter((item) => item.severity === 'normal').length)
const infoCount = computed(() => hexItems.value.filter((item) => item.severity === 'info').length)
const warningCount = computed(() => hexItems.value.filter((item) => item.severity === 'warning').length)
const criticalCount = computed(() => hexItems.value.filter((item) => item.severity === 'critical').length)
const emergencyCount = computed(() => hexItems.value.filter((item) => item.severity === 'emergency').length)
const attentionItems = computed(() => hexItems.value
  .filter((item) => ['info', 'warning', 'critical', 'emergency'].includes(item.severity))
  .sort((a, b) => (SEVERITY_RANK[b.severity] || 0) - (SEVERITY_RANK[a.severity] || 0))
  .slice(0, 8))

const layoutMode = ref(
  props.sharedConfig?.mode === 'free' || localStorage.getItem(HEX_MODE_KEY) === 'free' ? 'free' : 'device'
)
const magnetic = ref(localStorage.getItem('nms_hex_magnetic') !== '0')
const gridLayout = ref([])
const dashboardRef = ref(null)
const canvasWrapRef = ref(null)
const canvasAvailableHeight = ref(0)
let canvasObserver = null
const isFullscreen = ref(false)

// 行高随当前画布可用高度收缩，避免小屏必须纵向滚动
const gridMargin = computed(() => (Number(canvasAvailableHeight.value) || 480) < 420 ? 8 : 14)

const gridRowHeight = computed(() => {
  const rows = Math.max(1, ...gridLayout.value.map((item) => Number(item.y) + Number(item.h)))
  const available = Number(canvasAvailableHeight.value) || 480
  const margin = gridMargin.value
  const raw = Math.floor((available - margin * (rows + 1)) / rows)
  // 行高不再无限压缩：指标很多时画布纵向滚动，而不是把球体挤到不可读
  const minRowHeight = layoutMode.value === 'free' ? 38 : 22
  return Math.max(minRowHeight, Math.min(54, raw))
})

function observeCanvas() {
  if (canvasObserver) canvasObserver.disconnect()
  const el = canvasWrapRef.value
  if (!el) return
  canvasObserver = new ResizeObserver((entries) => {
    canvasAvailableHeight.value = entries[0]?.contentRect?.height || 0
  })
  canvasObserver.observe(el)
}
const paged = ref(localStorage.getItem('nms_hex_paged') === '1')
const displayGroupMode = ref(localStorage.getItem('nms_hex_group_mode') === 'metric' ? 'metric' : 'device')
const pageSize = ref(Number(localStorage.getItem('nms_hex_page_size')) || 6)
const defaultRefreshSeconds = Math.max(3, Math.round((Number(refreshMs()) || 10000) / 1000))
const refreshSeconds = ref(Math.max(3, Number(localStorage.getItem('nms_hex_refresh_seconds')) || defaultRefreshSeconds))
const fontScale = ref(Math.max(0.1, Math.min(1.5, Number(props.sharedConfig?.fontScale) || Number(localStorage.getItem('nms_hex_font_scale')) || 1)))
const currentPage = ref(Number(localStorage.getItem('nms_hex_page_current')) || 1)
const autoCarousel = ref(localStorage.getItem('nms_hex_auto_carousel') === '1')
const carouselSeconds = ref(Math.max(3, Math.min(600, Number(localStorage.getItem('nms_hex_carousel_seconds')) || 8)))
const gridScrollRef = ref(null)
let carouselFrame = null
let carouselHoldTimer = null
let carouselRunId = 0

const deviceGroups = computed(() => {
  const groups = new Map()
  hexItems.value.forEach((item) => {
    if (!groups.has(item.deviceId)) {
      const device = devices.value.find((row) => row.id === item.deviceId)
      groups.set(item.deviceId, {
        deviceId: item.deviceId,
        deviceName: item.deviceName,
        deviceIp: device?.ip_address || '',
        deviceTypeText: deviceTypeLabel(device?.device_type) || '',
        items: [],
        severity: 'normal',
        info: 0,
        warning: 0,
        critical: 0,
        emergency: 0,
      })
    }
    const group = groups.get(item.deviceId)
    group.items.push(item)
    if (item.severity === 'emergency') {
      group.severity = 'emergency'
      group.emergency += 1
    } else if (item.severity === 'critical') {
      if (group.severity !== 'emergency') group.severity = 'critical'
      group.critical += 1
    } else if (item.severity === 'warning') {
      if (!['emergency', 'critical'].includes(group.severity)) group.severity = 'warning'
      group.warning += 1
    } else if (item.severity === 'info') {
      if (!['emergency', 'critical', 'warning'].includes(group.severity)) group.severity = 'info'
      group.info += 1
    }
  })
  return [...groups.values()]
})

function groupOf(layoutItem) {
  return deviceGroups.value.find((group) => `g-${group.deviceId}` === layoutItem.i)
}

const metricGroups = computed(() => {
  const groups = new Map()
  hexItems.value.forEach((item) => {
    const key = item.metric || item.metricLabel
    if (!groups.has(key)) {
      groups.set(key, {
        groupKey: `metric:${key}`,
        metricKey: key,
        metricLabel: item.metricLabel,
        deviceCount: 0,
        items: [],
        severity: 'normal',
        info: 0,
        warning: 0,
        critical: 0,
        emergency: 0,
      })
    }
    const group = groups.get(key)
    group.items.push(item)
    if (item.severity === 'emergency') {
      group.severity = 'emergency'
      group.emergency += 1
    } else if (item.severity === 'critical') {
      if (group.severity !== 'emergency') group.severity = 'critical'
      group.critical += 1
    } else if (item.severity === 'warning') {
      if (!['emergency', 'critical'].includes(group.severity)) group.severity = 'warning'
      group.warning += 1
    } else if (item.severity === 'info') {
      if (!['emergency', 'critical', 'warning'].includes(group.severity)) group.severity = 'info'
      group.info += 1
    }
  })
  groups.forEach((group) => {
    group.deviceCount = new Set(group.items.map((item) => item.deviceId)).size
  })
  return [...groups.values()]
})

const displayGroups = computed(() => displayGroupMode.value === 'metric' ? metricGroups.value : deviceGroups.value)
const pageCount = computed(() => Math.max(1, Math.ceil(displayGroups.value.length / Math.max(1, Number(pageSize.value) || 6))))
const pagedGroups = computed(() => {
  const start = (currentPage.value - 1) * Math.max(1, Number(pageSize.value) || 6)
  return displayGroups.value.slice(start, start + Math.max(1, Number(pageSize.value) || 6))
})

function clampPage() {
  currentPage.value = Math.max(1, Math.min(pageCount.value, Number(currentPage.value) || 1))
}

function goPage(page) {
  clampPage()
  currentPage.value = Math.max(1, Math.min(pageCount.value, page))
  try {
    localStorage.setItem('nms_hex_page_current', String(currentPage.value))
  } catch {
    /* 忽略存储异常 */
  }
  nextTick(() => {
    if (gridScrollRef.value) gridScrollRef.value.scrollTop = 0
  })
  setupCarousel()
}

function nextPage() {
  goPage(currentPage.value >= pageCount.value ? 1 : currentPage.value + 1)
}

function prevPage() {
  goPage(currentPage.value <= 1 ? pageCount.value : currentPage.value - 1)
}

function persistPagerSetting(key, value) {
  try {
    localStorage.setItem(key, String(value))
  } catch {
    /* 忽略存储异常 */
  }
}

function clearCarousel() {
  carouselRunId += 1
  if (carouselFrame) cancelAnimationFrame(carouselFrame)
  carouselFrame = null
  if (carouselHoldTimer) clearTimeout(carouselHoldTimer)
  carouselHoldTimer = null
}

function scheduleNextPage(delay) {
  if (carouselHoldTimer) clearTimeout(carouselHoldTimer)
  carouselHoldTimer = setTimeout(() => {
    carouselHoldTimer = null
    if (!document.hidden) nextPage()
  }, Math.max(800, delay))
}

function setupCarousel() {
  clearCarousel()
  if (!autoCarousel.value) return
  const runId = carouselRunId
  const totalMs = Math.max(3, Number(carouselSeconds.value) || 8) * 1000
  nextTick(() => {
    if (runId !== carouselRunId) return
    const el = gridScrollRef.value
    if (!el) {
      scheduleNextPage(totalMs)
      return
    }
    el.scrollTop = 0
    const maxScroll = Math.max(0, el.scrollHeight - el.clientHeight)
    if (maxScroll <= 2) {
      scheduleNextPage(totalMs)
      return
    }
    // 每页用约 65% 的时间平滑滚到底部，再停留剩余时间后翻页。
    const duration = Math.max(1600, totalMs * 0.65)
    const start = performance.now()
    const step = (now) => {
      if (runId !== carouselRunId) return
      const ratio = Math.min(1, (now - start) / duration)
      el.scrollTop = maxScroll * (1 - Math.pow(1 - ratio, 3))
      if (ratio < 1) {
        carouselFrame = requestAnimationFrame(step)
      } else {
        el.scrollTop = maxScroll
        carouselFrame = null
        scheduleNextPage(totalMs * 0.35)
      }
    }
    carouselFrame = requestAnimationFrame(step)
  })
}

function onCarouselVisibility() {
  if (document.hidden) clearCarousel()
  else setupCarousel()
}

async function toggleFullscreen() {
  try {
    if (!document.fullscreenElement) {
      await dashboardRef.value?.requestFullscreen()
    } else {
      await document.exitFullscreen()
    }
  } catch {
    /* 浏览器不允许时忽略 */
  }
}

function onFullscreenChange() {
  isFullscreen.value = !!document.fullscreenElement
  nextTick(setupCarousel)
}

watch([paged, autoCarousel, carouselSeconds, pageCount, () => layoutMode.value], () => {
  clampPage()
  setupCarousel()
})

const fontPercent = computed({
  get() {
    return Math.round(fontScale.value * 100)
  },
  set(value) {
    const percent = Number.isFinite(Number(value)) ? Number(value) : 100
    const clamped = Math.max(10, Math.min(150, percent))
    fontScale.value = clamped / 100
    if (!props.sharedReadOnly) {
      try {
        localStorage.setItem('nms_hex_font_scale', String(fontScale.value))
      } catch {
        /* 忽略存储异常 */
      }
    }
    emit('shared-change', sharedSnapshot())
  },
})

watch(displayGroupMode, (value) => {
  persistPagerSetting('nms_hex_group_mode', value)
  currentPage.value = 1
  goPage(1)
})

watch(pageSize, (value) => {
  persistPagerSetting('nms_hex_page_size', value)
  clampPage()
  setupCarousel()
})

watch(paged, (value) => persistPagerSetting('nms_hex_paged', value ? '1' : '0'))
watch(refreshSeconds, (value) => {
  persistPagerSetting('nms_hex_refresh_seconds', String(Math.max(3, Number(value) || 10)))
  setupRefreshTimer()
})
watch(autoCarousel, (value) => persistPagerSetting('nms_hex_auto_carousel', value ? '1' : '0'))
watch(carouselSeconds, (value) => {
  const seconds = Math.max(3, Math.min(600, Number(value) || 8))
  if (seconds !== Number(value)) carouselSeconds.value = seconds
  persistPagerSetting('nms_hex_carousel_seconds', seconds)
  setupCarousel()
})

function metricOf(layoutItem) {
  return hexItems.value.find((item) => `m-${item.id}` === layoutItem.i)
}

let sharedLayoutSeeded = false
function readPositions() {
  if (props.sharedConfig?.layout && typeof props.sharedConfig.layout === 'object') {
    if (props.sharedReadOnly || !sharedLayoutSeeded) {
      sharedLayoutSeeded = true
      return JSON.parse(JSON.stringify(props.sharedConfig.layout))
    }
  }
  try {
    const parsed = JSON.parse(localStorage.getItem(HEX_LAYOUT_KEY) || '{}')
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

function buildDeviceLayout() {
  const groups = deviceGroups.value
  if (!groups.length) return []
  if (groups.length === 1) {
    const count = groups[0].items.length
    const height = count <= 2 ? 6 : Math.min(24, 7 + Math.ceil((count - 4) / 6) * 2)
    return [{ i: `g-${groups[0].deviceId}`, x: 0, y: 0, w: 12, h: Math.max(6, height), minW: 6, minH: 5 }]
  }
  // 多设备统一等宽等高，避免一个大一个小；按设备数量选择 2 列或 3 列
  const columns = groups.length <= 4 ? 2 : 3
  const width = Math.floor(12 / columns)
  const maxItems = Math.max(...groups.map((group) => group.items.length))
  const height = Math.max(7, Math.min(24, 7 + Math.ceil(Math.max(0, maxItems - 4) / 4) * 2))
  return groups.map((group, index) => ({
    i: `g-${group.deviceId}`,
    x: (index % columns) * width,
    y: Math.floor(index / columns) * height,
    w: width,
    h: height,
    minW: Math.max(3, width - 1),
    minH: 5,
  }))
}

function buildFreeLayout() {
  return hexItems.value.map((item, index) => ({
    i: `m-${item.id}`,
    x: (index % 6) * 2,
    y: Math.floor(index / 6) * 4,
    w: 2,
    h: 4,
    minW: 2,
    minH: 3,
  }))
}

function syncLayout() {
  const defaults = layoutMode.value === 'device' ? buildDeviceLayout() : buildFreeLayout()
  const saved = readPositions()[layoutMode.value] || []
  const byId = new Map(saved.map((item) => [item.i, item]))
  gridLayout.value = defaults.map((item) => {
    const previous = byId.get(item.i)
    if (!previous) return item
    const savedHeight = Number(previous.h ?? item.h)
    return {
      ...item,
      x: Number(previous.x ?? item.x),
      y: Number(previous.y ?? item.y),
      w: Math.max(item.minW, Number(previous.w ?? item.w)),
      // 设备模式：新增指标后默认高度只增不减，避免旧布局把球体挤在一起
      h: layoutMode.value === 'device'
        ? Math.max(item.minH, item.h, savedHeight)
        : Math.max(item.minH, savedHeight),
    }
  })
}

function persistPositions() {
  if (!props.sharedReadOnly) {
    try {
      const stored = readPositions()
      stored[layoutMode.value] = gridLayout.value.map(({ i, x, y, w, h }) => ({ i, x, y, w, h }))
      stored.mode = layoutMode.value
      localStorage.setItem(HEX_LAYOUT_KEY, JSON.stringify(stored))
      localStorage.setItem(HEX_MODE_KEY, layoutMode.value)
    } catch {
      /* 忽略存储异常 */
    }
  }
  emit('shared-change', sharedSnapshot())
}

function onLayoutUpdated() {
  persistPositions()
}

function onLayoutModeChange() {
  if (!props.sharedReadOnly) {
    localStorage.setItem(HEX_MODE_KEY, layoutMode.value)
  }
  syncLayout()
  emit('shared-change', sharedSnapshot())
}

function balanceLayout() {
  const next = layoutMode.value === 'device' ? buildDeviceLayout() : buildFreeLayout()
  gridLayout.value = next.map((item) => ({ ...item }))
  if (!props.sharedReadOnly) {
    try {
      const stored = readPositions()
      stored[layoutMode.value] = gridLayout.value.map(({ i, x, y, w, h }) => ({ i, x, y, w, h }))
      stored.mode = layoutMode.value
      localStorage.setItem(HEX_LAYOUT_KEY, JSON.stringify(stored))
      localStorage.setItem('nms_hex_magnetic', '1')
    } catch {
      /* 忽略存储异常 */
    }
  }
  magnetic.value = true
  emit('shared-change', sharedSnapshot())
  ElMessage.success('已均衡面板尺寸并开启磁吸对齐')
}

watch(magnetic, (value) => {
  if (props.sharedReadOnly) return
  try {
    localStorage.setItem('nms_hex_magnetic', value ? '1' : '0')
  } catch {
    /* 忽略存储异常 */
  }
})

function resetPositions() {
  const stored = readPositions()
  delete stored[layoutMode.value]
  try {
    localStorage.setItem(HEX_LAYOUT_KEY, JSON.stringify(stored))
  } catch {
    /* 忽略存储异常 */
  }
  syncLayout()
  ElMessage.success(t('dashboard.hexLayoutReset'))
}

watch(
  () => hexItems.value.map((item) => item.id).join('|'),
  () => syncLayout()
)

syncLayout()

watch(
  devices,
  (rows) => {
    if (seeded.value || !rows.length) return
    config.value = rows.slice(0, 6).map((device) => normalizeItem({
      id: `${device.id}-cpu_usage`,
      deviceId: device.id,
      metric: 'cpu_usage',
    }))
    seeded.value = true
    persistConfig()
  },
  { immediate: true }
)

// 一次性迁移：给已配置的服务器补充实际风扇/电源/温度组件指标，避免采集到但卡片不显示
watch(devices, (rows) => {
  if (!rows.length || props.sharedReadOnly) return
  try {
    if (localStorage.getItem('nms_hex_server_components_v1') === '1') return
    const configuredServerIds = new Set(config.value
      .map((item) => item.deviceId)
      .filter((id) => rows.find((device) => device.id === id)?.device_type === 'server'))
    if (!configuredServerIds.size) return
    const added = []
    // 有实际组件的服务器，移除旧的汇总电源/风扇指标和旧式电源键，避免重复显示
    config.value = config.value.filter((item) => {
      if (!configuredServerIds.has(item.deviceId)) return true
      const device = rows.find((row) => row.id === item.deviceId)
      const comps = device?.metric?.components || device?.metric?.custom?.server_components || {}
      const hasPsu = (comps.power_supplies || []).length > 0
      const hasFan = (comps.fans || []).length > 0
      if (hasPsu && ['srv_power_watts', 'srv_power_voltage', 'srv_power_current'].includes(item.metric)) return false
      if (hasFan && ['srv_fan_speed', 'srv_fan_fault'].includes(item.metric)) return false
      if (/^srv_component_psu_\d+$/.test(item.metric)) return false
      return true
    })
    configuredServerIds.forEach((deviceId) => {
      const device = rows.find((row) => row.id === deviceId)
      componentMetricDefs(device)
        .filter((def) => /fan|psu|temp/i.test(def.key))
        .forEach((def) => {
          if (config.value.some((item) => item.deviceId === deviceId && item.metric === def.key)) return
          draftSeq += 1
          added.push(normalizeItem({
            id: `${deviceId}-${def.key}-${Date.now()}-${draftSeq}`,
            deviceId,
            metric: def.key,
          }, device))
        })
    })
    if (added.length) {
      config.value = [...config.value, ...added]
      persistConfig()
      ElMessage.success(`已自动补全服务器风扇/电源/温度指标 ${added.length} 项`)
    }
    localStorage.setItem('nms_hex_server_components_v1', '1')
  } catch { /* 忽略迁移异常 */ }
}, { immediate: false })

const configMetricDefs = computed(() => configMetricDefsFor(draftDeviceId.value))
const pickerDevice = computed(() => devices.value.find((device) => device.id === draftDeviceId.value) || null)
const selectedDraftDevices = computed(() => devices.value.filter((device) => draftDeviceIds.value.includes(device.id)))
const targetDeviceIds = computed(() => {
  const selected = selectedDraftDevices.value.map((device) => device.id)
  return selected.length ? selected : (draftDeviceId.value ? [draftDeviceId.value] : [])
})

// 当前设备实际可选的指标，按分组筛选 / 搜索后展示；数量不再有上限
const metricOptionGroups = computed(() => {
  const keyword = metricKeyword.value.trim().toLowerCase()
  const matches = (def) => !keyword
    || String(def.label || '').toLowerCase().includes(keyword)
    || String(def.key || '').toLowerCase().includes(keyword)
    || String(def.unit || '').toLowerCase().includes(keyword)
  const groups = new Map()
  configMetricDefs.value.forEach((def) => {
    if (!def?.key || !matches(def)) return
    const groupKey = def.group || 'custom'
    if (!groups.has(groupKey)) {
      groups.set(groupKey, { key: groupKey, label: metricGroupLabel(groupKey), items: [], addedCount: 0 })
    }
    const group = groups.get(groupKey)
    group.items.push(def)
    if (isMetricAdded(def.key)) group.addedCount += 1
  })
  const order = new Map(METRIC_GROUP_ORDER.map((key, index) => [key, index]))
  return [...groups.values()].sort((a, b) => (order.get(a.key) ?? 99) - (order.get(b.key) ?? 99))
})

const deviceDraftCount = computed(() => draftCountFor(draftDeviceId.value))
const hasUnselectedMetric = computed(() => targetDeviceIds.value.some((deviceId) =>
  configMetricDefsFor(deviceId).some((def) => !draft.value.some((item) => item.deviceId === deviceId && item.metric === def.key))
))
function groupHasUnselected(group) {
  if (!group?.items?.length) return false
  return targetDeviceIds.value.some((deviceId) =>
    group.items.some((def) => !draft.value.some((item) => item.deviceId === deviceId && item.metric === def.key))
  )
}

function draftCountFor(deviceId) {
  if (!deviceId) return 0
  return draft.value.filter((item) => item.deviceId === deviceId).length
}

const deviceSelectionGroups = computed(() => {
  const keyword = pickerKeyword.value.trim().toLowerCase()
  const matches = (device) => !keyword
    || String(device.name || '').toLowerCase().includes(keyword)
    || String(device.ip_address || '').toLowerCase().includes(keyword)
    || String(device.group_name || '').toLowerCase().includes(keyword)
  const order = new Map(assetGroups.value.map((group, index) => [String(group.id), index]))
  const groups = new Map()
  devices.value.filter(matches).forEach((device) => {
    const groupId = device.group_id == null ? '' : String(device.group_id)
    if (!groups.has(groupId)) {
      const known = assetGroups.value.find((group) => String(group.id) === groupId)
      groups.set(groupId, {
        key: groupId || 'ungrouped',
        label: known?.name || device.group_name || (groupId ? `分组 #${groupId}` : '未分组'),
        order: groupId ? (order.get(groupId) ?? 9999) : 10000,
        devices: [],
      })
    }
    groups.get(groupId).devices.push(device)
  })
  return [...groups.values()].sort((a, b) => a.order - b.order || a.label.localeCompare(b.label, 'zh-CN'))
})
const draftGroups = computed(() => {
  const groups = new Map()
  draft.value.forEach((item) => {
    if (!groups.has(item.deviceId)) {
      const device = devices.value.find((row) => row.id === item.deviceId)
      groups.set(item.deviceId, {
        deviceId: item.deviceId,
        deviceName: device?.name || `#${item.deviceId}`,
        deviceIp: device?.ip_address || '',
        typeLabel: deviceTypeLabel(device?.device_type || 'other'),
        tagType: deviceTypeTagType(device?.device_type || 'other'),
        items: [],
      })
    }
    groups.get(item.deviceId).items.push(item)
  })
  return [...groups.values()]
})

const configuredGroups = computed(() => {
  if (!configuredDeviceId.value) return draftGroups.value
  return draftGroups.value.filter((group) => group.deviceId === configuredDeviceId.value)
})

const configuredEmptyText = computed(() => (
  draft.value.length && configuredDeviceId.value
    ? '没有匹配的已添加设备'
    : t('dashboard.hexEmpty')
))

watch(draftGroups, (groups) => {
  if (configuredDeviceId.value && !groups.some((group) => group.deviceId === configuredDeviceId.value)) {
    configuredDeviceId.value = null
  }
})

function onConfiguredDeviceChange(deviceId) {
  if (!deviceId) return
  collapsedDraftGroups.value = collapsedDraftGroups.value.filter((id) => id !== deviceId)
  nextTick(() => {
    document.getElementById(`hex-config-group-${deviceId}`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  })
}

const batchMetricOptions = computed(() => {
  const map = new Map()
  targetDeviceIds.value.forEach((deviceId) => {
    configMetricDefsFor(deviceId).forEach((def) => {
      if (!hasThresholds(def.key, deviceId)) return
      if (!map.has(def.key)) {
        map.set(def.key, { key: def.key, label: def.label, unit: def.unit || '' })
      }
    })
  })
  return [...map.values()].sort((a, b) => a.label.localeCompare(b.label, 'zh-CN'))
})

function syncBatchFromMetric() {
  if (!batchMetricKey.value) return
  const current = draft.value.find((item) => item.metric === batchMetricKey.value)
  const defs = targetDeviceIds.value
    .map((deviceId) => configMetricDefsFor(deviceId).find((def) => def.key === batchMetricKey.value))
    .filter(Boolean)
  const meta = defs[0] || {}
  const defaults = defaultsFor(batchMetricKey.value, devices.value.find((row) => row.id === draftDeviceId.value))
  batchWarning.value = current?.warning ?? meta.warning ?? defaults.warning ?? 80
  batchCritical.value = current?.critical ?? meta.critical ?? defaults.critical ?? 90
  batchWarningColor.value = current?.warningColor || '#fbbf24'
  batchCriticalColor.value = current?.criticalColor || '#fb7185'
}

function openBatchPanel() {
  if (!selectedDraftDevices.value.length) {
    ElMessage.warning('请先选择设备')
    return
  }
  batchPanelVisible.value = true
  if (!batchMetricKey.value || !batchMetricOptions.value.some((item) => item.key === batchMetricKey.value)) {
    batchMetricKey.value = draft.value.find((item) => targetDeviceIds.value.includes(item.deviceId))?.metric
      || batchMetricOptions.value[0]?.key
      || ''
  }
  syncBatchFromMetric()
}

function startBatchFromItem(item) {
  if (!item) return
  batchPanelVisible.value = true
  batchMetricKey.value = item.metric
  batchWarning.value = item.warning
  batchCritical.value = item.critical
  batchWarningColor.value = item.warningColor || '#fbbf24'
  batchCriticalColor.value = item.criticalColor || '#fb7185'
}

function applyBatchThreshold() {
  const metricKey = batchMetricKey.value
  if (!metricKey) return
  let applied = 0
  targetDeviceIds.value.forEach((deviceId) => {
    if (!configMetricDefsFor(deviceId).some((def) => def.key === metricKey)) return
    if (!hasThresholds(metricKey, deviceId)) return
    const existing = draft.value.find((item) => item.deviceId === deviceId && item.metric === metricKey)
    const patch = {
      warning: Number(batchWarning.value),
      critical: Number(batchCritical.value),
      warningColor: batchWarningColor.value,
      criticalColor: batchCriticalColor.value,
    }
    if (existing) {
      Object.assign(existing, patch)
    } else {
      draftSeq += 1
      draft.value.push(normalizeItem({
        id: `${deviceId}-${metricKey}-${Date.now()}-${draftSeq}`,
        deviceId,
        metric: metricKey,
        ...patch,
      }))
    }
    applied += 1
  })
  if (applied) ElMessage.success(`已将 ${metricKey} 阈值应用到 ${applied} 台设备`)
  else ElMessage.warning('已选设备没有该指标或不支持阈值')
}


function openConfig() {
  if (props.sharedReadOnly) return
  invalidItemId.value = null
  invalidReason.value = ''
  draft.value = config.value
    .filter((item) => {
      const device = devices.value.find((row) => String(row.id) === String(item.deviceId))
      if (item.metric === 'srv_inlet_temp' && hasBoundaryTempComponent(device, 'inlet')) return false
      if (item.metric === 'srv_exhaust_temp' && hasBoundaryTempComponent(device, 'exhaust')) return false
      return true
    })
    .map((item) => normalizeItem(
      { ...item },
      devices.value.find((device) => String(device.id) === String(item.deviceId)),
    ))
  draftDeviceId.value = config.value[0]?.deviceId || devices.value[0]?.id || null
  const configuredIds = [...new Set(config.value.map((item) => item.deviceId).filter(Boolean))]
  draftDeviceIds.value = configuredIds.length ? configuredIds : (draftDeviceId.value ? [draftDeviceId.value] : [])
  pickerKeyword.value = ''
  metricKeyword.value = ''
  // 配置项较多时先收起明细，避免一次性挂载大量输入控件导致弹窗卡顿
  collapsedDraftGroups.value = draft.value.length > 18 ? configuredIds : []
  batchPanelVisible.value = false
  batchMetricKey.value = ''
  lastSelectedDeviceId.value = draftDeviceId.value
  configReady.value = false
  configVisible.value = true
  window.setTimeout(() => { configReady.value = true }, 20)
}

function expandAllDraftGroups() {
  collapsedDraftGroups.value = []
}

function refresh() {
  loadDevices()
}

function goDevice(deviceId) {
  if (deviceId) router.push(`/devices/${deviceId}`)
}

function deviceName(deviceId) {
  return devices.value.find((device) => device.id === deviceId)?.name || `#${deviceId}`
}

function metricLabel(key, deviceId) {
  const device = devices.value.find((item) => item.id === deviceId)
  return metricMeta(key, device).label
}

function hasThresholds(key, deviceId) {
  const device = devices.value.find((item) => item.id === deviceId)
  const meta = metricMeta(key, device)
  if (meta.kind === 'power' || meta.kind === 'fault' || meta.noThreshold) return false
  // 自定义 / MIB 指标可能没有固定阈值，此时只按状态与容量显示，不参与阈值校验
  return (meta.warning !== null && meta.warning !== undefined)
    || (meta.critical !== null && meta.critical !== undefined)
}

function thresholdDirection(item) {
  const device = devices.value.find((row) => row.id === item.deviceId)
  return metricMeta(item.metric, device).direction || 'higher'
}

// 网络设备类型统一判断；服务器、存储、终端和打印机不作为网络接口监控对象
const NETWORK_DEVICE_TYPES = new Set(['router', 'switch', 'firewall', 'security', 'wireless', 'loadbalancer', 'other'])
function isNetworkDevice(device) {
  return !!device && NETWORK_DEVICE_TYPES.has(device.device_type || 'other')
}

function configMetricDefsFor(deviceId) {
  const device = devices.value.find((item) => item.id === deviceId)
  const defs = []
  const seen = new Set()
  const push = (def, group) => {
    if (!def?.key || seen.has(def.key)) return
    seen.add(def.key)
    defs.push({ ...def, group })
  }
  HEX_METRICS.value.forEach((def) => push(def, 'base'))
  serverMetricDefs(device).forEach((def) => push(def, 'sensor'))
  componentMetricDefs(device).forEach((def) => push(def, 'sensor'))
  customMetricDefs(device).forEach((def) => push(def, 'custom'))
  if (isNetworkDevice(device)) NETWORK_IF_METRICS.value.forEach((def) => push(def, 'interface'))
  return defs
}

function isMetricAdded(metricKey) {
  return draft.value.some((item) => String(item.deviceId) === String(draftDeviceId.value) && item.metric === metricKey)
}

function isDraftDeviceSelected(deviceId) {
  return draftDeviceIds.value.includes(deviceId)
}

const visibleDeviceIds = computed(() =>
  deviceSelectionGroups.value.flatMap((group) => group.devices.map((device) => device.id))
)

function scrollToDeviceMetrics(deviceId) {
  if (!deviceId || !draftCountFor(deviceId)) return
  collapsedDraftGroups.value = collapsedDraftGroups.value.filter((id) => id !== deviceId)
  nextTick(() => {
    document.getElementById(`hex-config-group-${deviceId}`)?.scrollIntoView({
      behavior: 'smooth',
      block: 'nearest',
    })
  })
}

function metricTargetDeviceIds(metricKey) {
  return targetDeviceIds.value.filter((deviceId) =>
    configMetricDefsFor(deviceId).some((def) => def.key === metricKey)
  )
}

function isMetricAddedForTargets(metricKey) {
  const targets = metricTargetDeviceIds(metricKey)
  return targets.length > 0 && targets.every((deviceId) =>
    draft.value.some((item) => String(item.deviceId) === String(deviceId) && item.metric === metricKey)
  )
}

function focusConfiguredDevice(deviceId) {
  if (!deviceId) return
  // 切换当前查看设备，但不改变复选框的批量选择状态。
  draftDeviceId.value = deviceId
  configuredDeviceId.value = deviceId
  if (draftCountFor(deviceId)) {
    scrollToDeviceMetrics(deviceId)
    return
  }
  ElMessage.info('该设备还没有已添加指标，请在右侧指标中勾选')
}

function selectDraftDevice(deviceId, event = {}) {
  if (!deviceId) return
  const ids = visibleDeviceIds.value
  if (event.shiftKey && lastSelectedDeviceId.value) {
    const from = ids.indexOf(lastSelectedDeviceId.value)
    const to = ids.indexOf(deviceId)
    if (from >= 0 && to >= 0) {
      const start = Math.min(from, to)
      const end = Math.max(from, to)
      draftDeviceIds.value = ids.slice(start, end + 1)
    } else {
      draftDeviceIds.value = [deviceId]
    }
  } else if (event.ctrlKey || event.metaKey) {
    if (isDraftDeviceSelected(deviceId)) {
      if (draftDeviceIds.value.length > 1) {
        draftDeviceIds.value = draftDeviceIds.value.filter((id) => id !== deviceId)
      }
    } else {
      draftDeviceIds.value = [...draftDeviceIds.value, deviceId]
    }
    lastSelectedDeviceId.value = deviceId
  } else {
    draftDeviceIds.value = [deviceId]
    lastSelectedDeviceId.value = deviceId
  }
  draftDeviceId.value = deviceId
  if (!event.shiftKey) lastSelectedDeviceId.value = deviceId
  scrollToDeviceMetrics(deviceId)
}

function toggleDraftDevice(deviceId) {
  if (!deviceId) return
  if (isDraftDeviceSelected(deviceId)) {
    draftDeviceIds.value = draftDeviceIds.value.filter((id) => id !== deviceId)
    if (draftDeviceId.value === deviceId) {
      draftDeviceId.value = draftDeviceIds.value[0] || null
    }
    return
  }
  draftDeviceIds.value = [...draftDeviceIds.value, deviceId]
  draftDeviceId.value = deviceId
  lastSelectedDeviceId.value = deviceId
  scrollToDeviceMetrics(deviceId)
}

function selectVisibleDraftDevices() {
  const ids = deviceSelectionGroups.value.flatMap((group) => group.devices.map((device) => device.id))
  if (!ids.length) return
  draftDeviceIds.value = [...new Set([...draftDeviceIds.value, ...ids])]
  if (!draftDeviceId.value) draftDeviceId.value = ids[0]
}

function selectGroupDraftDevices(group) {
  const ids = (group?.devices || []).map((device) => device.id)
  if (!ids.length) return
  draftDeviceIds.value = [...new Set([...draftDeviceIds.value, ...ids])]
  if (!draftDeviceId.value) draftDeviceId.value = ids[0]
  lastSelectedDeviceId.value = ids[0]
}

function deselectGroupDraftDevices(group) {
  const ids = new Set((group?.devices || []).map((device) => device.id))
  const remaining = draftDeviceIds.value.filter((id) => !ids.has(id))
  draftDeviceIds.value = remaining
  if (draftDeviceId.value && ids.has(draftDeviceId.value)) {
    draftDeviceId.value = remaining[0] || null
  }
}

function clearDraftDeviceSelection() {
  draftDeviceIds.value = draftDeviceId.value ? [draftDeviceId.value] : []
}

function pushDraftMetricFor(deviceId, metricKey) {
  if (!deviceId || !metricKey) return false
  if (draft.value.some((item) => item.deviceId === deviceId && item.metric === metricKey)) return false
  const supported = configMetricDefsFor(deviceId).some((def) => def.key === metricKey)
  if (!supported) return false
  draftSeq += 1
  draft.value.push(normalizeItem({
    id: `${deviceId}-${metricKey}-${Date.now()}-${draftSeq}`,
    deviceId,
    metric: metricKey,
  }, devices.value.find((device) => String(device.id) === String(deviceId))))
  return true
}

function pushDraftMetric(metricKey) {
  if (!draftDeviceId.value || !metricKey) return false
  return pushDraftMetricFor(draftDeviceId.value, metricKey)
}

function addMetric(metricKey) {
  if (!draftDeviceId.value) {
    ElMessage.warning(t('dashboard.hexSelectDevice'))
    return
  }
  let added = 0
  targetDeviceIds.value.forEach((deviceId) => {
    if (pushDraftMetricFor(deviceId, metricKey)) added += 1
  })
  if (!added) ElMessage.info(t('dashboard.hexDuplicate'))
}

function removeMetric(metricKey) {
  if (!draftDeviceId.value || !metricKey) return
  const targets = new Set(targetDeviceIds.value)
  draft.value = draft.value.filter(
    (item) => !(targets.has(item.deviceId) && item.metric === metricKey)
  )
}

function toggleMetric(metricKey) {
  const targets = metricTargetDeviceIds(metricKey)
  if (!targets.length) return
  const missing = targets.some((deviceId) =>
    !draft.value.some((item) => String(item.deviceId) === String(deviceId) && item.metric === metricKey)
  )
  if (missing) addMetric(metricKey)
  else removeMetric(metricKey)
}

function deselectGroupMetrics(group) {
  if (!draftDeviceId.value || !group?.items?.length) return
  const keys = new Set(group.items.map((item) => item.key))
  const targets = new Set(targetDeviceIds.value)
  draft.value = draft.value.filter(
    (item) => !(targets.has(item.deviceId) && keys.has(item.metric))
  )
}

function selectGroupMetrics(group) {
  if (!draftDeviceId.value || !group?.items?.length) return
  let added = 0
  targetDeviceIds.value.forEach((deviceId) => {
    group.items.forEach((def) => {
      if (pushDraftMetricFor(deviceId, def.key)) added += 1
    })
  })
  if (!added) ElMessage.info(t('dashboard.hexDuplicate'))
}

function selectAllMetrics() {
  if (!draftDeviceId.value) {
    ElMessage.warning(t('dashboard.hexSelectDevice'))
    return
  }
  let added = 0
  targetDeviceIds.value.forEach((deviceId) => {
    configMetricDefsFor(deviceId).forEach((def) => {
      if (pushDraftMetricFor(deviceId, def.key)) added += 1
    })
  })
  if (!added) ElMessage.info(t('dashboard.hexDuplicate'))
}

function clearDeviceMetrics() {
  if (!draftDeviceId.value) return
  const targets = new Set(targetDeviceIds.value)
  draft.value = draft.value.filter((item) => !targets.has(item.deviceId))
}

function clearAllMetrics() {
  draft.value = []
}

function removeDraftGroup(group) {
  if (!group) return
  draft.value = draft.value.filter((item) => item.deviceId !== group.deviceId)
}

function isDraftGroupCollapsed(deviceId) {
  return collapsedDraftGroups.value.includes(deviceId)
}

function toggleDraftGroup(deviceId) {
  if (!deviceId) return
  collapsedDraftGroups.value = isDraftGroupCollapsed(deviceId)
    ? collapsedDraftGroups.value.filter((id) => id !== deviceId)
    : [...collapsedDraftGroups.value, deviceId]
}

function removeDraftItem(item) {
  const index = draft.value.indexOf(item)
  if (index >= 0) draft.value.splice(index, 1)
}

function moveGroupItem(group, index, delta) {
  const target = index + delta
  if (target < 0 || target >= group.items.length) return
  const rows = [...draft.value]
  const current = rows.indexOf(group.items[index])
  const next = rows.indexOf(group.items[target])
  if (current < 0 || next < 0) return
  ;[rows[current], rows[next]] = [rows[next], rows[current]]
  draft.value = rows
}

function focusInvalidMetric(item, reason) {
  const device = devices.value.find((row) => row.id === item.deviceId)
  const deviceText = device?.name || deviceName(item.deviceId)
  const metricText = metricLabel(item.metric, item.deviceId)
  invalidItemId.value = item.id
  invalidReason.value = reason
  // 自动展开所在设备分组并滚动到具体指标
  if (isDraftGroupCollapsed(item.deviceId)) {
    collapsedDraftGroups.value = collapsedDraftGroups.value.filter((id) => id !== item.deviceId)
  }
  nextTick(() => {
    const el = document.getElementById(`hex-config-item-${item.id}`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  })
  ElMessage.warning(`配置错误：${deviceText} · ${metricText}，${reason}`)
}

async function saveConfig() {
  invalidItemId.value = null
  invalidReason.value = ''
  for (const item of draft.value) {
    if (!hasThresholds(item.metric, item.deviceId)) continue
    const warning = Number(item.warning)
    const critical = Number(item.critical)
    const device = devices.value.find((row) => row.id === item.deviceId)
    const direction = metricMeta(item.metric, device).direction || 'higher'
    let reason = ''
    if (!Number.isFinite(warning) || !Number.isFinite(critical)) {
      reason = '预警阈值或严重阈值不是有效数字'
    } else if (warning < 0) {
      reason = '预警阈值不能小于 0'
    } else if (direction === 'lower' ? critical >= warning : critical <= warning) {
      reason = direction === 'lower'
        ? `严重阈值（${critical}）必须低于预警阈值（${warning}）`
        : `严重阈值（${critical}）必须高于预警阈值（${warning}）`
    }
    if (reason) {
      focusInvalidMetric(item, reason)
      return
    }
  }
  const previousItems = config.value.map((item) => ({ ...item }))
  config.value = draft.value.map((item) => {
    const defaults = defaultsFor(item.metric, devices.value.find((device) => device.id === item.deviceId))
    const threshold = hasThresholds(item.metric, item.deviceId)
    return {
      id: `${item.deviceId}-${item.metric}`,
      deviceId: item.deviceId,
      metric: item.metric,
      warning: threshold ? Number(item.warning) : null,
      critical: threshold ? Number(item.critical) : null,
      warningColor: item.warningColor || defaults.warningColor,
      criticalColor: item.criticalColor || defaults.criticalColor,
    }
  })
  seeded.value = true
  persistConfig()
  syncLayout()
  configVisible.value = false
  try {
    await syncDashboardAlertRules(config.value, { silent: true })
    await deleteRemovedDashboardRules(previousItems, config.value)
  } catch {
    /* 本地仪表盘配置已保存；无规则编辑权限时不影响显示 */
  }
  ElMessage.success(t('dashboard.hexSaved'))
}

async function deleteRemovedDashboardRules(previousItems, currentItems) {
  const keyOf = (item) => `${item.deviceId}|${item.metric}`
  const after = new Set((currentItems || []).filter((item) => dashboardRuleSpec(item)).map(keyOf))
  const removed = (previousItems || []).filter((item) => dashboardRuleSpec(item) && !after.has(keyOf(item)))
  const byDevice = new Map()
  removed.forEach((item) => {
    if (!byDevice.has(item.deviceId)) byDevice.set(item.deviceId, [])
    byDevice.get(item.deviceId).push(item)
  })
  for (const [deviceId, items] of byDevice) {
    let existing = []
    try {
      const res = await alertRuleApi.list(deviceId)
      existing = Array.isArray(res?.data) ? res.data : []
    } catch {
      continue
    }
    for (const item of items) {
      const spec = dashboardRuleSpec(item)
      if (!spec) continue
      const matches = existing.filter((rule) => (
        rule.metric === spec.metric
        && String(rule.custom_key || '') === String(spec.custom_key || '')
      ))
      for (const rule of matches) {
        try {
          await alertRuleApi.remove(rule.id)
        } catch {
          /* 单条删除失败不阻塞保存 */
        }
      }
    }
  }
}

// 仪表盘阈值是外发告警的来源：保存时同步为设备自定义告警规则。
function dashboardRuleSpec(item) {
  const key = String(item.metric || '')
  if (!key) return null
  // 这些是仪表盘展示型/网络接口型指标，采集器没有单设备告警值
  if (key.startsWith('if_') || ['alert_count', 'warranty_days_left', 'power_status'].includes(key)) {
    return null
  }
  if (['cpu_usage', 'memory_usage', 'temperature', 'disk_usage', 'power'].includes(key)) {
    return { metric: key, custom_key: null }
  }
  if (key === 'srv_fan_speed') return { metric: 'fan_speed', custom_key: null }
  // 组件温度和自定义/MIB 指标统一按 custom + key 交给采集器取值
  return { metric: 'custom', custom_key: key }
}

async function syncDashboardAlertRules(items, { silent = false } = {}) {
  const candidates = (Array.isArray(items) ? items : []).filter((item) => {
    const spec = dashboardRuleSpec(item)
    return spec && (item.warning !== null && item.warning !== undefined || item.critical !== null && item.critical !== undefined)
  })
  if (!candidates.length) return
  let channels = []
  try {
    const res = await alertRuleApi.channels()
    channels = (res?.data || []).filter((channel) => channel.enabled).map((channel) => channel.id)
  } catch {
    channels = []
  }
  const byDevice = new Map()
  candidates.forEach((item) => {
    if (!byDevice.has(item.deviceId)) byDevice.set(item.deviceId, [])
    byDevice.get(item.deviceId).push(item)
  })
  let created = 0
  let updated = 0
  for (const [deviceId, deviceItems] of byDevice) {
    let existing = []
    try {
      const res = await alertRuleApi.list(deviceId)
      existing = Array.isArray(res?.data) ? res.data : []
    } catch {
      continue
    }
    for (const item of deviceItems) {
      const spec = dashboardRuleSpec(item)
      if (!spec) continue
      const device = devices.value.find((row) => String(row.id) === String(deviceId))
      const direction = metricMeta(item.metric, device).direction || 'higher'
      const operator = direction === 'lower' ? 'lte' : 'gte'
      const label = metricLabel(item.metric, deviceId)
      for (const [level, thresholdKey, levelLabel] of [
        ['warning', 'warning', '预警'],
        ['critical', 'critical', '告警'],
      ]) {
        const raw = item[thresholdKey]
        const threshold = Number(raw)
        if (raw === null || raw === undefined || !Number.isFinite(threshold)) continue
        const match = existing.find((rule) => (
          rule.metric === spec.metric
          && String(rule.custom_key || '') === String(spec.custom_key || '')
          && String(rule.level || '') === level
        ))
        if (match) {
          if (Number(match.threshold) === threshold && match.operator === operator && match.enabled !== false) continue
          await alertRuleApi.update(match.id, {
            device_id: Number(deviceId),
            name: match.name,
            metric: match.metric,
            custom_key: match.custom_key || null,
            operator,
            threshold,
            level,
            level_label: match.level_label || null,
            notify_channel_ids: match.notify_channel_ids || [],
            enabled: true,
          })
          updated += 1
        } else {
          await alertRuleApi.create({
            device_id: Number(deviceId),
            name: `仪表盘同步 · ${label} ${levelLabel}`,
            metric: spec.metric,
            custom_key: spec.custom_key,
            operator,
            threshold,
            level,
            level_label: levelLabel,
            notify_channel_ids: channels,
            enabled: true,
          })
          created += 1
        }
      }
    }
  }
  if (!silent && (created || updated)) {
    ElMessage.success(`已同步告警阈值：新增 ${created} 条，更新 ${updated} 条`)
  }
}

let dashboardRuleSyncAttempted = false

async function syncExistingDashboardRules() {
  if (dashboardRuleSyncAttempted || !config.value.length) return
  dashboardRuleSyncAttempted = true
  try {
    await syncDashboardAlertRules(config.value, { silent: true })
  } catch {
    /* 无权限或离线时忽略，保存时仍会再次尝试 */
  }
}

async function loadDevices() {
  try {
    const [deviceRes, groupRes] = await Promise.allSettled([
      assetApi.getList({ size: 100 }),
      assetApi.groups(),
    ])
    devices.value = deviceRes.status === 'fulfilled' ? (deviceRes.value.data.items || []) : []
    assetGroups.value = groupRes.status === 'fulfilled' ? (groupRes.value.data.items || []) : []
  } catch {
    devices.value = []
    assetGroups.value = []
  }
  if (!configVisible.value) {
    syncConfigAssetThresholds()
  }
  await Promise.all([loadInterfaceSummaries(), loadDeviceAlertLevels()])
}

function syncConfigAssetThresholds() {
  let changed = false
  const beforeCount = config.value.length
  config.value = config.value.filter((item) => {
    const device = devices.value.find((row) => String(row.id) === String(item.deviceId))
    if (item.metric === 'srv_inlet_temp' && hasBoundaryTempComponent(device, 'inlet')) return false
    if (item.metric === 'srv_exhaust_temp' && hasBoundaryTempComponent(device, 'exhaust')) return false
    return true
  })
  if (config.value.length !== beforeCount) changed = true
  config.value = config.value.map((item) => {
    const device = devices.value.find((row) => String(row.id) === String(item.deviceId))
    const rule = assetRuleThresholds(item.metric, device)
    if (rule.warning === null && rule.critical === null) return item
    const next = {
      ...item,
      warning: rule.warning !== null ? rule.warning : item.warning,
      critical: rule.critical !== null ? rule.critical : item.critical,
    }
    if (next.warning !== item.warning || next.critical !== item.critical) changed = true
    return next
  })
  if (changed) {
    persistConfig()
    emit('shared-change', sharedSnapshot())
  }
}

async function loadDeviceAlertLevels() {
  try {
    const res = await monitorApi.getActiveAlerts()
    const levels = {}
    for (const alert of Array.isArray(res.data) ? res.data : []) {
      if (!alert.device_id || !SEVERITY_RANK[alert.alert_level]) continue
      const rawKey = String(alert.metric_key || alert.alert_type || '').toLowerCase()
      if (!rawKey || ['offline', 'interface'].includes(rawKey)) continue
      const metric = ALERT_METRIC_ALIASES[rawKey] || rawKey
      if (!metric || metric.startsWith('rule_')) continue
      const id = `${alert.device_id}|${metric}`
      levels[id] = levels[id] ? worseSeverity(levels[id], alert.alert_level) : alert.alert_level
    }
    metricAlertLevels.value = levels
  } catch {
    metricAlertLevels.value = {}
  }
}

async function loadInterfaceSummaries() {
  const networkIds = devices.value
    .filter((device) => isNetworkDevice(device))
    .map((device) => device.id)
  if (!networkIds.length) {
    interfaceSummaries.value = {}
    return
  }
  try {
    const res = await monitorApi.getInterfaceSummaries(networkIds)
    const summaries = {}
    ;(res.data.items || []).forEach((item) => {
      summaries[item.device_id] = item
    })
    interfaceSummaries.value = summaries
  } catch {
    interfaceSummaries.value = {}
  }
}

function setupRefreshTimer() {
  if (refreshTimer) clearInterval(refreshTimer)
  const seconds = Math.max(3, Number(refreshSeconds.value) || 10)
  refreshTimer = setInterval(() => {
    if (!document.hidden) loadDevices()
  }, seconds * 1000)
}

async function loadMetricThresholds() {
  try {
    const res = await monitorApi.getDashboard()
    if (res.data?.metric_thresholds) metricThresholds.value = { ...metricThresholds.value, ...res.data.metric_thresholds }
  } catch {
    /* keep local defaults */
  }
}

onMounted(async () => {
  loadMetricThresholds()
  loadDevices()
  setupCarousel()
  document.addEventListener('visibilitychange', onCarouselVisibility)
  document.addEventListener('fullscreenchange', onFullscreenChange)
  await nextTick()
  observeCanvas()
  setupRefreshTimer()
})

watch([paged, layoutMode, () => hexItems.value.length], () => {
  nextTick(observeCanvas)
})

onBeforeUnmount(() => {
  if (refreshTimer) clearInterval(refreshTimer)
  clearCarousel()
  document.removeEventListener('visibilitychange', onCarouselVisibility)
  if (canvasObserver) canvasObserver.disconnect()
  document.removeEventListener('fullscreenchange', onFullscreenChange)
})
</script>

<style scoped>
.hex-dashboard {
  position: relative;
  overflow: hidden;
  padding: 22px 24px 24px;
  border: 1px solid rgba(56, 189, 248, 0.22);
  border-radius: 14px;
  background:
    radial-gradient(ellipse at 12% 0%, rgba(14, 165, 233, 0.16), transparent 38%),
    radial-gradient(ellipse at 92% 100%, rgba(124, 58, 237, 0.14), transparent 42%),
    linear-gradient(135deg, #071525 0%, #081c32 55%, #06111f 100%);
  box-shadow: 0 12px 34px rgba(7, 21, 37, 0.2);
}

.hex-dashboard::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0.7;
  background-image:
    linear-gradient(rgba(56, 189, 248, 0.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(56, 189, 248, 0.045) 1px, transparent 1px);
  background-size: 32px 32px;
  mask-image: radial-gradient(ellipse at 50% 50%, #000 15%, transparent 78%);
}

.hex-dashboard::after {
  content: '';
  position: absolute;
  left: 22px;
  right: 22px;
  top: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(56, 189, 248, 0.7), transparent);
}

.hex-dashboard-head {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 18px;
}

.hex-kicker {
  display: block;
  margin-bottom: 5px;
  color: #38bdf8;
  font-family: Consolas, monospace;
  font-size: 9px;
  letter-spacing: 2px;
}

.hex-head-copy h2 {
  margin: 0;
  color: #f0f9ff;
  font-size: 20px;
  letter-spacing: 2px;
  font-weight: 600;
}

.hex-head-copy p {
  margin: 4px 0 0;
  color: #64748b;
  font-size: 11px;
}

.hex-head-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.hex-font-control {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #94a3b8;
  font-size: 11px;
  white-space: nowrap;
}

.hex-font-number {
  width: 96px;
}

.hex-font-number :deep(.el-input__wrapper) {
  background: rgba(8, 28, 50, 0.72);
  box-shadow: 0 0 0 1px rgba(56, 189, 248, 0.28) inset;
}

.hex-font-unit {
  color: #64748b;
}

.hex-health {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 9px;
  border: 1px solid rgba(56, 189, 248, 0.12);
  border-radius: 4px;
  background: rgba(4, 15, 30, 0.45);
}

.hex-health-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #94a3b8;
  font-family: Consolas, monospace;
  font-size: 10px;
}

.hex-health-item i {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #34d399;
}

.hex-health-item.warning i {
  background: #fbbf24;
  box-shadow: 0 0 6px rgba(251, 191, 36, 0.7);
}

.hex-health-item.critical i {
  background: #fb7185;
  box-shadow: 0 0 6px rgba(251, 113, 133, 0.8);
  animation: hex-health-blink 1.5s ease-in-out infinite;
}

@keyframes hex-health-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.hex-head-actions :deep(.el-button) {
  border-color: rgba(56, 189, 248, 0.28);
  background: rgba(8, 28, 50, 0.72);
  color: #7dd3fc;
}

.hex-head-actions :deep(.el-button:hover) {
  border-color: rgba(56, 189, 248, 0.65);
  background: rgba(14, 165, 233, 0.14);
}

.hex-grid {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0;
  padding: 2px 0 4px;
}

.hex-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.hex-row + .hex-row {
  margin-top: -24px;
}

.hex-row.offset {
  padding-left: 82px;
}

.hex-empty {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 30px 0;
  color: #64748b;
  font-size: 12px;
}

.hex-config-picker {
  display: grid;
  grid-template-columns: 252px minmax(0, 1fr);
  gap: 14px;
  height: clamp(330px, 46vh, 540px);
  min-height: 0;
}

.hex-device-tree,
.hex-metric-picker {
  min-height: 0;
  border: 1px solid #e2e8f0;
  border-radius: 9px;
  background: #fbfdff;
}

.hex-device-tree {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.hex-picker-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 9px 11px;
  border-bottom: 1px solid #eef2f7;
  color: #334155;
  font-size: 12px;
}

.hex-picker-head span {
  color: #94a3b8;
  font-family: Consolas, monospace;
  font-size: 10px;
}

.hex-device-search {
  margin: 8px 9px;
  width: calc(100% - 18px);
}

.hex-device-tree-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 0 7px 8px;
}

.hex-device-batch-tools {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
  padding: 5px 8px;
  color: #64748b;
  font-size: 10px;
}

.hex-device-batch-tools span {
  margin-right: auto;
  color: #2563eb;
}

.hex-device-batch-tools :deep(.el-button) {
  height: 22px;
  padding: 0 8px;
  font-size: 10px;
}

.hex-device-batch-tools :deep(.hex-batch-select-all) {
  border-color: #86efac;
  color: #15803d;
  background: #ecfdf3;
  font-weight: 600;
}

.hex-device-batch-tools :deep(.hex-batch-keep-current) {
  border-color: #fcd34d;
  color: #b45309;
  background: #fffbeb;
  font-weight: 600;
}

.hex-batch-hint {
  margin: 6px 0 0;
  padding: 6px 8px;
  border: 1px solid #bfdbfe;
  border-radius: 5px;
  color: #1d4ed8;
  background: #eff6ff;
  font-size: 10px;
}

.hex-device-type-group {
  margin-bottom: 7px;
}

.hex-group-actions { display: inline-flex; align-items: center; gap: 2px; margin-left: auto; }
.hex-device-type-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 5px;
  color: #94a3b8;
  font-size: 10px;
}

.hex-device-type-title small {
  font-family: Consolas, monospace;
}

.hex-device-option {
  position: relative;
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 6px 8px 6px 26px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: #334155;
  text-align: left;
  cursor: pointer;
}

.hex-device-option-count {
  position: absolute;
  top: 6px;
  right: 7px;
  min-width: 17px;
  padding: 0 5px;
  border-radius: 9px;
  background: #dbeafe;
  color: #1d4ed8;
  font-family: Consolas, monospace;
  font-size: 9px;
  line-height: 15px;
  text-align: center;
}

.hex-device-option:hover {
  background: #f1f5f9;
}

.hex-device-check {
  position: absolute;
  left: 8px;
  top: 50%;
  display: grid;
  place-items: center;
  width: 13px;
  height: 13px;
  border: 1px solid #cbd5e1;
  border-radius: 3px;
  color: #fff;
  background: #fff;
  transform: translateY(-50%);
}

.hex-device-option.selected .hex-device-check {
  border-color: #2563eb;
  background: #2563eb;
}

.hex-device-option.selected {
  border-color: #dbeafe;
}

.hex-device-option.active {
  border-color: #60a5fa;
  background: #dbeafe;
  color: #1e40af;
  font-weight: 600;
  box-shadow: inset 3px 0 0 #2563eb;
}
.hex-device-option.active .hex-device-option-name {
  color: #1e40af;
}

.hex-device-option-name {
  width: 100%;
  overflow: hidden;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hex-device-option small {
  width: 100%;
  overflow: hidden;
  color: #94a3b8;
  font-family: Consolas, monospace;
  font-size: 9px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hex-metric-picker {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: 11px;
  overflow: hidden;
}

.hex-metric-picker-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex: 0 0 auto;
}

.hex-metric-picker-head strong {
  color: #1e293b;
  font-size: 13px;
}

.hex-metric-picker-head small {
  margin-left: 8px;
  color: #94a3b8;
  font-family: Consolas, monospace;
  font-size: 9px;
}

.hex-metric-picker-hint {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex: 0 0 auto;
  margin: 5px 0 8px;
  color: #94a3b8;
  font-size: 10px;
}

.hex-picker-selected {
  flex-shrink: 0;
  padding: 1px 8px;
  border: 1px solid #bfdbfe;
  border-radius: 10px;
  background: #eff6ff;
  color: #1d4ed8;
  font-family: Consolas, monospace;
}

.hex-picker-selected b {
  font-size: 11px;
}

.hex-picker-selected em {
  margin-left: 5px;
  font-style: normal;
  opacity: 0.75;
}

.hex-picker-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 0 0 auto;
  margin-bottom: 8px;
}

.hex-metric-search {
  flex: 1;
  min-width: 0;
}

.hex-picker-toolbar-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.hex-metric-groups {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 9px;
  overflow: auto;
  padding-right: 2px;
}

.hex-metric-group {
  flex-shrink: 0;
}

.hex-metric-group-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 5px;
  padding: 3px 2px;
  border-bottom: 1px dashed #e2e8f0;
}

.hex-metric-group-name {
  color: #475569;
  font-size: 11px;
  font-weight: 500;
}

.hex-metric-group-count {
  color: #94a3b8;
  font-family: Consolas, monospace;
  font-size: 9px;
}

.hex-metric-group-head :deep(.el-button) {
  padding: 0;
  font-size: 10px;
}

.hex-metric-group-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
  flex-shrink: 0;
}

.hex-metric-group-actions :deep(.el-button + .el-button) {
  margin-left: 0;
}

.hex-server-hint {
  margin: -3px 0 9px;
  padding: 6px 8px;
  border: 1px solid #bae6fd;
  border-radius: 6px;
  background: #f0f9ff;
  color: #0369a1;
  font-size: 10px;
  line-height: 1.5;
}

.hex-metric-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(132px, 1fr));
  gap: 7px;
}

.hex-metric-option {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 7px 9px;
  border: 1px solid #e2e8f0;
  border-radius: 7px;
  background: #fff;
  color: #334155;
  text-align: left;
  cursor: pointer;
}

.hex-metric-option:hover:not(:disabled) {
  border-color: #93c5fd;
  background: #f8fbff;
}

.hex-metric-option span {
  font-size: 11px;
}

.hex-metric-option small {
  color: #94a3b8;
  font-size: 9px;
}

.hex-metric-option .el-icon {
  position: absolute;
  top: 7px;
  right: 7px;
  color: #16a34a;
}

.hex-metric-option.added {
  border-color: #bbf7d0;
  background: #f0fdf4;
  color: #15803d;
}

.hex-metric-state {
  color: #94a3b8;
  font-size: 9px;
  line-height: 1.2;
}
.hex-metric-state.added {
  color: #15803d;
  font-weight: 700;
}

.hex-metric-option:disabled {
  cursor: default;
}

.hex-config-opening {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 260px;
  color: #7b91a3;
  font-size: 12px;
}

.hex-config-opening .el-icon {
  font-size: 18px;
}

.hex-configured-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  margin: 16px 0 8px;
}

.hex-configured-title {
  display: flex;
  align-items: baseline;
  gap: 7px;
  flex-wrap: wrap;
}

.hex-configured-head strong {
  color: #1e293b;
  font-size: 12px;
}

.hex-configured-head span {
  color: #94a3b8;
  font-size: 10px;
}

.hex-configured-count {
  color: #1d4ed8;
  font-family: Consolas, monospace;
}

.hex-configured-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.hex-configured-actions :deep(.el-button) {
  padding: 0;
}

.hex-configured-device-select {
  width: 230px;
}

.hex-configured-device-select :deep(.el-select__wrapper) {
  min-height: 26px;
  border-radius: 6px;
}

.hex-configured-device-select :deep(.el-select__placeholder),
.hex-configured-device-select :deep(.el-select__selected-item) {
  font-size: 10px;
}

.hex-configured-head small {
  color: #94a3b8;
  font-size: 10px;
}

.hex-config-groups {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: clamp(220px, 34vh, 460px);
  overflow: auto;
  padding-right: 2px;
}

.hex-config-group {
  flex-shrink: 0;
  overflow: hidden;
  border: 1px solid #e2e8f0;
  border-radius: 9px;
  background: #fff;
}

.hex-config-group-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-bottom: 1px solid #eef2f7;
  background: #f8fafc;
  cursor: pointer;
  user-select: none;
}

.hex-config-group-head:hover {
  background: #f1f5f9;
}

.hex-group-caret {
  flex-shrink: 0;
  color: #94a3b8;
  font-size: 11px;
  transition: transform 0.18s ease;
}

.hex-group-caret.collapsed {
  transform: rotate(-90deg);
}

.hex-config-group-name {
  color: #1e293b;
  font-size: 12px;
  font-weight: 500;
}

.hex-config-group-count {
  margin-left: auto;
  color: #94a3b8;
  font-size: 10px;
}

.hex-config-group .hex-config-list {
  max-height: none;
  padding: 7px;
  gap: 6px;
}

.hex-config-metric-name {
  flex: 1;
  min-width: 0;
  color: #334155;
  font-size: 12px;
}

.hex-config-add {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}

.hex-config-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 360px;
  overflow: auto;
}

.hex-config-row {
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding: 9px 10px;
  border: 1px solid #ebeef5;
  border-radius: 7px;
  background: #fafcff;
}

.hex-config-row.invalid {
  border-color: #fb7185;
  background: #fff1f2;
  box-shadow: 0 0 0 2px rgba(251, 113, 133, 0.14);
}

.hex-config-invalid-tip {
  display: flex;
  align-items: center;
  gap: 5px;
  color: #dc2626;
  font-size: 10px;
}

.hex-config-main {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.hex-config-thresholds {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 7px;
  padding-left: 28px;
}

.hex-threshold-label {
  color: #64748b;
  font-size: 11px;
  white-space: nowrap;
}

.hex-threshold-hint {
  color: #94a3b8;
  font-size: 10px;
}

.hex-config-index {
  color: #94a3b8;
  font-family: Consolas, monospace;
  font-size: 10px;
}

.hex-config-device {
  flex: 1;
  min-width: 0;
  color: #303133;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hex-config-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}

.hex-config-actions :deep(.el-button) {
  padding: 2px 5px;
}

@media (max-width: 900px) {
  .hex-dashboard {
    padding: 14px;
  }

  .hex-dashboard-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .hex-row {
    flex-wrap: wrap;
  }

  .hex-row.offset {
    padding-left: 0;
  }

  .hex-row + .hex-row {
    margin-top: 8px;
  }

  .hex-config-add {
    flex-wrap: wrap;
  }
}

/* ---------- 自适应可拖拽画布 ---------- */
.hex-dashboard {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.hex-dashboard-head {
  flex-wrap: wrap;
  align-items: flex-start;
}

.hex-head-actions {
  flex-wrap: wrap;
  justify-content: flex-end;
}

.hex-mode-switch :deep(.el-radio-button__inner) {
  border-color: rgba(56, 189, 248, 0.22);
  background: rgba(8, 28, 50, 0.72);
  color: #7dd3fc;
  padding: 7px 12px;
  font-size: 11px;
}

.hex-mode-switch :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  border-color: rgba(56, 189, 248, 0.65);
  background: rgba(14, 165, 233, 0.22);
  color: #e0f2fe;
  box-shadow: none;
}

.hex-layout-hint {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 6px;
  margin: -4px 0 8px;
  color: #64748b;
  font-size: 10px;
}

.hex-magnetic-switch {
  flex-shrink: 0;
}

.hex-magnetic-switch :deep(.el-switch__label) {
  color: #7dd3fc;
  font-size: 10px;
}

.hex-attention-bar {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
  min-width: 0;
  margin: -2px 0 8px;
  overflow-x: auto;
  scrollbar-width: none;
}

.hex-attention-bar::-webkit-scrollbar {
  display: none;
}

.hex-attention-label {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  flex: 0 0 auto;
  color: #fbbf24;
  font-size: 10px;
  white-space: nowrap;
}

.hex-attention-label i {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #fbbf24;
  box-shadow: 0 0 7px rgba(251, 191, 36, 0.85);
  animation: hex-health-blink 1.5s ease-in-out infinite;
}

.hex-attention-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  flex: 0 0 auto;
  max-width: 250px;
  padding: 4px 8px;
  border: 1px solid rgba(251, 191, 36, 0.24);
  border-radius: 4px;
  color: #94a3b8;
  background: rgba(120, 73, 20, 0.16);
  font-size: 9px;
  cursor: pointer;
}

.hex-attention-chip.critical {
  border-color: rgba(251, 113, 133, 0.38);
  color: #fecdd3;
  background: rgba(127, 29, 29, 0.2);
}

.hex-attention-chip.warning {
  color: #fde68a;
}

.hex-attention-chip b {
  overflow: hidden;
  color: #e2e8f0;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hex-attention-chip em {
  color: #fbbf24;
  font-family: Consolas, monospace;
  font-style: normal;
  font-weight: 700;
}

.hex-attention-chip.critical em {
  color: #fb7185;
}

.hex-pager-bar {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
  padding: 7px 10px;
  border: 1px solid rgba(56, 189, 248, 0.12);
  border-radius: 8px;
  background: rgba(4, 15, 30, 0.45);
}

.hex-pager-bar :deep(.el-switch__label) {
  color: #94a3b8;
  font-size: 10px;
}

.pager-label,
.pager-index,
.pager-hint {
  color: #64748b;
  font-size: 10px;
}

.pager-index {
  min-width: 36px;
  color: #7dd3fc;
  font-family: Consolas, monospace;
  text-align: center;
}

.pager-sep {
  width: 1px;
  height: 14px;
  background: rgba(148, 163, 184, 0.2);
}

.hex-pager-bar :deep(.el-button) {
  border-color: rgba(56, 189, 248, 0.2);
  background: rgba(8, 28, 50, 0.72);
  color: #7dd3fc;
}

.hex-canvas-wrap {
  position: relative;
  z-index: 1;
  flex: 1;
  height: auto;
  min-height: 0;
  overflow: auto;
  border: 1px dashed rgba(56, 189, 248, 0.14);
  border-radius: 12px;
  padding: 2px;
  scrollbar-gutter: stable;
}

.hex-paged-wrap {
  position: relative;
  z-index: 1;
  flex: 1;
  height: auto;
  min-height: 0;
  overflow: hidden;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  grid-auto-rows: minmax(0, 1fr);
  align-content: stretch;
  gap: 10px;
  padding: 2px;
  scrollbar-gutter: stable;
}

.hex-paged-wrap .paged-panel {
  min-height: 0;
  height: 100%;
}

.hex-paged-wrap .hex-fluid-cell {
  flex-basis: 128px;
  max-width: 240px;
}

.hex-paged-wrap .device-panel-body {
  min-height: 230px;
}

.hex-canvas {
  min-height: 100%;
}

.hex-grid-item {
  overflow: visible;
}

.device-panel {
  position: relative;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  container-type: inline-size;
  border: 1px solid rgba(56, 189, 248, 0.18);
  border-radius: 15px;
  background:
    radial-gradient(ellipse at 18% 0%, rgba(14, 165, 233, 0.1), transparent 42%),
    rgba(6, 20, 36, 0.82);
  box-shadow: 0 10px 26px rgba(2, 8, 20, 0.25);
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.device-panel::before {
  content: '';
  position: absolute;
  top: 0;
  left: 16px;
  right: 16px;
  height: 1px;
  z-index: 2;
  background: linear-gradient(90deg, transparent, rgba(125, 211, 252, 0.55), transparent);
  pointer-events: none;
}

.device-panel:hover {
  border-color: rgba(56, 189, 248, 0.45);  box-shadow: 0 12px 32px rgba(2, 8, 20, 0.38);
}

.device-panel.severity-warning {
  border-color: rgba(251, 191, 36, 0.45);
  box-shadow: 0 10px 28px rgba(251, 191, 36, 0.1);
}

.device-panel.severity-critical {
  border-color: rgba(251, 113, 133, 0.55);
  box-shadow: 0 10px 30px rgba(251, 113, 133, 0.14);
}

.device-panel-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  padding: 10px 12px;
  border-bottom: 1px solid rgba(56, 189, 248, 0.1);
  background: linear-gradient(90deg, rgba(14, 165, 233, 0.07), transparent);
  cursor: grab;
}

.device-panel-head:active {
  cursor: grabbing;
}

.hex-drag-handle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 5px;
  color: #64748b;
  font-size: 13px;
  cursor: grab;
  transition: color 0.18s ease, background 0.18s ease;
}

.hex-drag-handle:hover {
  color: #7dd3fc;
  background: rgba(56, 189, 248, 0.12);
}

.hex-drag-handle:active {
  cursor: grabbing;
}

.device-panel-title {
  display: flex;
  flex: 1;
  align-items: baseline;
  gap: 7px;
  min-width: 0;
}

.device-panel-title :deep(.el-link) {
  max-width: 70%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 500;
}

.device-panel-title small {
  flex-shrink: 0;
  color: #64748b;
  font-size: 9px;
}

.device-panel-health {
  display: flex;
  align-items: center;
  gap: 5px;
  flex-shrink: 0;
}

.group-dot {
  min-width: 18px;
  padding: 2px 5px;
  border-radius: 9px;
  font-family: Consolas, monospace;
  font-size: 9px;
  text-align: center;
  color: #34d399;
  background: rgba(52, 211, 153, 0.12);
}

.group-dot.warning {
  color: #fbbf24;
  background: rgba(251, 191, 36, 0.14);
}

.group-dot.critical {
  color: #fb7185;
  background: rgba(251, 113, 133, 0.16);
  animation: group-dot-pulse 1.8s ease-in-out infinite;
}

@keyframes group-dot-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.55; }
}

.device-panel-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-wrap: wrap;
  align-content: center;
  justify-content: center;
  gap: 6px;
  padding: 10px 12px 14px;
  scrollbar-gutter: stable;
}

.multi-metric-body {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(84px, 1fr));
  grid-auto-rows: minmax(0, 1fr);
  align-content: stretch;
  justify-content: stretch;
  gap: 4px;
  overflow: hidden;
}

.multi-metric-body.metrics-2 {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.multi-metric-body.metrics-3 {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.multi-metric-body.metrics-4 {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.multi-metric-body.metrics-5,
.multi-metric-body.metrics-6 {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.multi-metric-body.metrics-7,
.multi-metric-body.metrics-8 {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

/* 超过 8 个指标：自适应列数 + 面板内部滚动，保证每个球体都能看到 */
.multi-metric-body.metrics-many {
  grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
  grid-auto-rows: minmax(92px, 1fr);
  align-content: start;
  overflow: auto;
  padding: 8px 10px 12px;
}

.multi-metric-body.metrics-many .hex-fluid-cell {
  min-height: 92px;
}

@container (min-width: 300px) {
  .multi-metric-body.metrics-4 {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

@container (min-width: 620px) {
  .multi-metric-body.metrics-5,
  .multi-metric-body.metrics-6 {
    grid-template-columns: repeat(5, minmax(0, 1fr));
  }
}

@container (min-width: 820px) {
  .multi-metric-body.metrics-7,
  .multi-metric-body.metrics-8 {
    grid-template-columns: repeat(7, minmax(0, 1fr));
  }
}

.multi-metric-body .hex-fluid-cell {
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  max-width: none;
  container-type: size;
}

.multi-metric-body .hex-fluid-cell :deep(.hex-cell.fluid) {
  width: min(100cqw, 100cqh);
  height: min(100cqw, 100cqh);
  max-width: 100%;
  max-height: 100%;
}

.single-metric-body {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  justify-content: flex-start;
  gap: 18px;
  padding: 12px 18px 16px;
  overflow: hidden;
  container-type: size;
}

.single-metric-hex {
  flex: 0 0 auto;
  width: min(190px, 100cqh);
  height: min(190px, 100cqh);
  min-width: 0;
  max-width: 100%;
  container-type: inline-size;
}

.single-metric-hex :deep(.hex-cell.fluid) {
  width: 100%;
  height: 100%;
}

@container (max-width: 330px) {
  .single-metric-body {
    justify-content: center;
    gap: 0;
    padding: 6px 8px 8px;
  }

  .single-metric-side {
    display: none !important;
  }

  .single-metric-hex {
    width: min(100cqw, 100cqh);
    height: min(100cqw, 100cqh);
  }
}

.single-metric-side {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.single-side-kicker {
  color: #48697f;
  font-family: Consolas, monospace;
  font-size: 8px;
  letter-spacing: 1.2px;
}

.single-side-value {
  color: #f0f9ff;
  font-family: Rajdhani, 'DIN Alternate', Consolas, monospace;
  font-size: clamp(22px, 3vw, 31px);
  font-weight: 700;
  line-height: 1;
  letter-spacing: 0.5px;
}

.single-side-value small {
  margin-left: 4px;
  color: #7dd3fc;
  font-family: Consolas, monospace;
  font-size: 10px;
  font-weight: 400;
}

.single-side-label {
  color: #7d9bb0;
  font-size: 10px;
  line-height: 1.3;
}

.single-thresholds {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 2px;
  color: #5b7b8f;
  font-size: 9px;
}

.single-thresholds b {
  margin-left: 3px;
  color: #a7c7d8;
  font-family: Consolas, monospace;
  font-weight: 500;
}

.single-progress {
  height: 4px;
  margin: 3px 0;
  overflow: hidden;
  border-radius: 3px;
  background: rgba(56, 189, 248, 0.12);
}

.single-progress i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--metric-color, #38bdf8), color-mix(in srgb, var(--metric-color, #38bdf8) 55%, #fff));
  box-shadow: 0 0 8px color-mix(in srgb, var(--metric-color, #38bdf8) 50%, transparent);
  transition: width 0.6s ease;
}

.single-meta {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  color: #58768a;
  font-size: 9px;
}

.single-meta span {
  flex-shrink: 0;
}

.single-meta b {
  min-width: 0;
  color: #a7c7d8;
  font-family: Consolas, monospace;
  font-size: 9px;
  font-weight: 400;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.single-side-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 4px;
  padding-top: 7px;
  border-top: 1px solid rgba(56, 189, 248, 0.1);
}

.single-side-foot :deep(.el-button) {
  padding: 0;
  font-size: 9px;
}

.single-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 7px;
  border: 1px solid rgba(52, 211, 153, 0.22);
  border-radius: 10px;
  color: #5ee6b5;
  background: rgba(16, 185, 129, 0.08);
  font-size: 9px;
}

.single-status i {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: currentColor;
  box-shadow: 0 0 6px currentColor;
}

.single-status.warning {
  border-color: rgba(251, 191, 36, 0.28);
  color: #fbbf24;
  background: rgba(251, 191, 36, 0.08);
}

.single-status.critical {
  border-color: rgba(251, 113, 133, 0.3);
  color: #fb7185;
  background: rgba(251, 113, 133, 0.08);
}

.single-status.muted {
  border-color: rgba(148, 163, 184, 0.2);
  color: #94a3b8;
  background: rgba(148, 163, 184, 0.06);
}

.hex-fluid-cell {
  flex: 1 1 104px;
  max-width: 178px;
  min-width: 78px;
  display: flex;
  align-items: center;
  justify-content: center;
  container-type: inline-size;
}

.hex-fluid-cell :deep(.hex-cell) {
  margin: 0;
}

.panel-resize-note {
  position: absolute;
  right: 12px;
  bottom: 5px;
  color: #334155;
  font-size: 8px;
  pointer-events: none;
}

.free-hex-wrap {
  position: relative;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(56, 189, 248, 0.14);
  border-radius: 12px;
  background: rgba(6, 20, 36, 0.64);
}

.free-hex-wrap:hover {
  border-color: rgba(56, 189, 248, 0.38);
}

.free-hex-wrap > .hex-drag-handle {
  position: absolute;
  top: 5px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 2;
}

.free-hex-wrap :deep(.hex-cell) {
  --hex-width: 138px;
}

.hex-grid-item :deep(.vgl-item__resizer) {
  border-color: rgba(56, 189, 248, 0.55);
}

@media (max-width: 1100px) {
  .hex-dashboard {
    min-height: 0;
  }

  .hex-head-actions {
    justify-content: flex-start;
  }

  .hex-canvas-wrap,
  .hex-paged-wrap {
    height: auto;
    min-height: 0;
  }

  .hex-paged-wrap {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 700px) {
  .hex-canvas-wrap,
  .hex-paged-wrap {
    min-height: 0;
  }

  .hex-paged-wrap {
    grid-template-columns: 1fr;
  }

  .hex-pager-bar {
    gap: 6px;
  }
}

@media (max-height: 780px) {
  .hex-dashboard {
    padding: 12px 16px 10px;
  }

  .hex-dashboard-head {
    margin-bottom: 8px;
  }

  .hex-head-copy p,
  .hex-layout-hint {
    display: none;
  }

  .hex-pager-bar {
    margin-bottom: 6px;
    padding: 5px 8px;
  }
}

/* 全屏模式：只显示仪表盘本体，画布占满屏幕 */
.hex-dashboard:fullscreen {
  width: 100vw;
  height: 100vh;
  min-height: 100vh;
  max-height: 100vh;
  border: none;
  border-radius: 0;
  padding: 18px 22px;
  overflow: hidden;
  background:
    radial-gradient(ellipse at 12% 0%, rgba(14, 165, 233, 0.18), transparent 38%),
    radial-gradient(ellipse at 92% 100%, rgba(124, 58, 237, 0.16), transparent 42%),
    linear-gradient(135deg, #071525 0%, #081c32 55%, #06111f 100%);
}

@media (max-width: 900px) {
  .hex-config-picker {
    grid-template-columns: 1fr;
    height: auto;
  }

  .hex-device-tree {
    height: 220px;
    max-height: 220px;
  }

  .hex-metric-picker {
    height: clamp(320px, 50vh, 500px);
  }
}

@media (max-width: 640px) {
  .hex-picker-toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .hex-picker-toolbar-actions {
    justify-content: flex-end;
  }

  .hex-metric-grid {
    grid-template-columns: repeat(auto-fill, minmax(118px, 1fr));
  }

  .hex-configured-head {
    flex-direction: column;
    align-items: flex-start;
    gap: 6px;
  }

  .hex-configured-actions {
    justify-content: flex-start;
  }

  .hex-config-group-head {
    flex-wrap: wrap;
  }
}

.hex-dashboard:fullscreen .hex-canvas-wrap,
.hex-dashboard:fullscreen .hex-paged-wrap {
  height: auto;
  min-height: 0;
}

.hex-dashboard:fullscreen .hex-dashboard-head {
  margin-bottom: 12px;
}

.hex-dashboard:fullscreen .hex-layout-hint {
  margin-bottom: 6px;
}
</style>

<style>
.hex-config-dialog {
  max-width: 96vw;
}

.hex-config-dialog .el-dialog__body {
  max-height: calc(100vh - 180px);
  overflow-y: auto;
  padding-top: 10px;
}

@media (max-width: 760px) {
  .hex-config-dialog .el-dialog__body {
    padding: 8px 12px;
  }
}


/* ---------- 分页模式：卡片自适应、无内部滚动条、放大球体 ---------- */
.hex-paged-wrap.paged-cols-1 { grid-template-columns: minmax(0, 1fr); }
.hex-paged-wrap.paged-cols-2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.hex-paged-wrap.paged-cols-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }

.hex-paged-wrap .paged-panel {
  min-height: 0;
  height: 100%;
}

.hex-paged-wrap .device-panel-body {
  min-height: 0;
  overflow: hidden;
}

.hex-paged-wrap .multi-metric-body,
.hex-paged-wrap .multi-metric-body.metrics-many {
  overflow: hidden;
  padding: 6px 8px 10px;
}

.hex-paged-wrap .multi-metric-body.metrics-many {
  grid-template-columns: repeat(auto-fit, minmax(72px, 1fr));
  grid-auto-rows: minmax(0, 1fr);
  align-content: stretch;
}

.hex-paged-wrap .multi-metric-body.metrics-many .hex-fluid-cell {
  min-height: 0;
}

.hex-paged-wrap .hex-fluid-cell {
  flex: 1 1 0;
  min-width: 0;
  max-width: none;
}

.hex-paged-wrap .single-metric-hex {
  flex: 1 1 auto;
  width: min(320px, 56cqw, 100cqh);
  height: min(320px, 56cqw, 100cqh);
  min-width: 0;
  max-width: 100%;
}

.hex-paged-wrap .single-metric-body {
  padding: 8px 12px 12px;
}

.hex-paged-wrap .single-metric-body .hex-cell.fluid {
  max-width: none;
  max-height: none;
}



/* ============================================================
   极光玻璃主题（Aurora Glass）— 设备指标仪表盘视觉重设计
   ============================================================ */
.hex-dashboard-aurora {
  padding: 24px 26px 26px;
  border: 1px solid rgba(148, 197, 234, 0.16);
  border-radius: 24px;
  background:
    radial-gradient(ellipse at 8% -4%, rgba(34, 211, 238, 0.19), transparent 34%),
    radial-gradient(ellipse at 96% 8%, rgba(167, 139, 250, 0.13), transparent 30%),
    radial-gradient(ellipse at 50% 110%, rgba(14, 116, 144, 0.1), transparent 42%),
    linear-gradient(142deg, #061321 0%, #0a1b2d 48%, #06101e 100%);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.05),
    0 28px 70px rgba(2, 8, 18, 0.38);
}

.hex-dashboard-aurora::before {
  opacity: 0.32;
  background-image: radial-gradient(circle, rgba(148, 226, 255, 0.2) 1px, transparent 1px);
  background-size: 24px 24px;
  -webkit-mask-image: linear-gradient(to bottom, #000 0%, rgba(0, 0, 0, 0.55) 52%, transparent 96%);
  mask-image: linear-gradient(to bottom, #000 0%, rgba(0, 0, 0, 0.55) 52%, transparent 96%);
}

.hex-dashboard-aurora::after {
  left: 26px;
  right: 26px;
  height: 2px;
  background: linear-gradient(90deg, transparent 0%, #22d3ee 22%, #a78bfa 62%, transparent 100%);
  opacity: 0.9;
}

.hex-dashboard-aurora .hex-dashboard-head {
  align-items: flex-end;
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid rgba(148, 197, 234, 0.12);
}

.hex-dashboard-aurora .hex-kicker {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  margin-bottom: 8px;
  padding: 3px 9px;
  border: 1px solid rgba(103, 232, 249, 0.24);
  border-radius: 999px;
  color: #a5f3fc;
  background: rgba(8, 47, 73, 0.38);
  font-size: 8px;
  letter-spacing: 1.7px;
}

.hex-dashboard-aurora .hex-head-copy h2 {
  margin: 0;
  color: #f2fbff;
  font-size: 27px;
  font-weight: 700;
  letter-spacing: 0.6px;
  line-height: 1.2;
  text-shadow: 0 0 28px rgba(34, 211, 238, 0.18);
}

.hex-dashboard-aurora .hex-head-copy p {
  margin: 6px 0 0;
  color: #7897ad;
  font-size: 10px;
  letter-spacing: 0.2px;
}

.hex-dashboard-aurora .hex-head-actions {
  gap: 8px;
  max-width: 68%;
}

.hex-dashboard-aurora .hex-health {
  gap: 9px;
  padding: 6px 12px;
  border: 1px solid rgba(148, 197, 234, 0.16);
  border-radius: 999px;
  background: rgba(7, 24, 40, 0.72);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(14px);
}

.hex-dashboard-aurora .hex-health-item {
  color: #9fb6c8;
  font-size: 10px;
}

.hex-dashboard-aurora .hex-health-item.normal i {
  box-shadow: 0 0 8px rgba(52, 211, 153, 0.8);
}

.hex-dashboard-aurora .hex-head-actions :deep(.el-button) {
  height: 30px;
  padding: 0 12px;
  border-color: rgba(125, 211, 252, 0.2);
  border-radius: 999px;
  background: rgba(8, 29, 48, 0.7);
  color: #b8e8ff;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.hex-dashboard-aurora .hex-head-actions :deep(.el-button:hover) {
  border-color: rgba(103, 232, 249, 0.55);
  background: rgba(14, 116, 144, 0.24);
  color: #ecfeff;
  transform: translateY(-1px);
}

.hex-dashboard-aurora .hex-mode-switch {
  padding: 3px;
  border: 1px solid rgba(148, 197, 234, 0.12);
  border-radius: 999px;
  background: rgba(5, 18, 32, 0.62);
}

.hex-dashboard-aurora .hex-mode-switch :deep(.el-radio-button__inner) {
  border: none;
  border-radius: 999px;
  background: transparent;
  color: #8aa9be;
  padding: 6px 13px;
  font-size: 10px;
  box-shadow: none;
}

.hex-dashboard-aurora .hex-mode-switch :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background: linear-gradient(135deg, rgba(14, 165, 233, 0.32), rgba(167, 139, 250, 0.28));
  color: #f0fdff;
  box-shadow: 0 4px 14px rgba(8, 47, 73, 0.5);
}

.hex-dashboard-aurora .hex-font-control {
  min-height: 30px;
  padding: 3px 10px;
  border: 1px solid rgba(148, 197, 234, 0.12);
  border-radius: 999px;
  background: rgba(7, 24, 40, 0.62);
}

.hex-dashboard-aurora .hex-font-label,
.hex-dashboard-aurora .hex-font-unit {
  color: #7c9bb1;
  font-size: 9px;
}

.hex-dashboard-aurora .hex-attention-bar {
  margin: 0 0 10px;
  padding: 6px 8px;
  border: 1px solid rgba(251, 191, 36, 0.12);
  border-radius: 10px;
  background: rgba(39, 28, 9, 0.2);
}

.hex-dashboard-aurora .hex-attention-chip {
  padding: 4px 10px;
  border-radius: 999px;
  backdrop-filter: blur(8px);
}

.hex-dashboard-aurora .hex-pager-bar {
  gap: 9px;
  margin-bottom: 12px;
  padding: 8px 12px;
  border: 1px solid rgba(148, 197, 234, 0.14);
  border-radius: 14px;
  background: rgba(7, 24, 40, 0.58);
  backdrop-filter: blur(14px);
}

.hex-dashboard-aurora .hex-pager-bar :deep(.el-button) {
  border-radius: 50%;
  background: rgba(8, 29, 48, 0.75);
}

.hex-dashboard-aurora .hex-pager-bar :deep(.el-select .el-select__wrapper) {
  border-radius: 999px;
  background: rgba(8, 29, 48, 0.75);
  box-shadow: 0 0 0 1px rgba(148, 197, 234, 0.14) inset;
}

.hex-dashboard-aurora .hex-canvas-wrap {
  padding: 10px;
  border: 1px solid rgba(148, 197, 234, 0.11);
  border-radius: 18px;
  background: rgba(4, 15, 27, 0.38);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
}

.hex-dashboard-aurora .hex-paged-wrap {
  gap: 12px;
  padding: 2px;
}

.hex-dashboard-aurora .device-panel {
  border: 1px solid rgba(148, 197, 234, 0.18);
  border-radius: 20px;
  background:
    radial-gradient(ellipse at 12% 0%, rgba(34, 211, 238, 0.1), transparent 35%),
    linear-gradient(155deg, rgba(12, 35, 56, 0.86), rgba(5, 17, 30, 0.94));
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.055),
    0 14px 34px rgba(1, 7, 16, 0.34);
  backdrop-filter: blur(16px);
  transition: border-color 0.22s ease, box-shadow 0.22s ease, transform 0.22s ease;
}

.hex-dashboard-aurora .device-panel:hover {
  border-color: rgba(103, 232, 249, 0.34);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.07),
    0 18px 42px rgba(1, 7, 16, 0.42),
    0 0 0 1px rgba(34, 211, 238, 0.05);
  transform: translateY(-2px);
}

.hex-dashboard-aurora .device-panel::before {
  left: 22px;
  right: 22px;
  height: 2px;
  background: linear-gradient(90deg, transparent, rgba(103, 232, 249, 0.72), rgba(167, 139, 250, 0.55), transparent);
}

.hex-dashboard-aurora .device-panel-head {
  padding: 12px 15px;
  border-bottom: 1px solid rgba(148, 197, 234, 0.1);
  background: linear-gradient(90deg, rgba(22, 78, 105, 0.22), rgba(8, 29, 48, 0.04));
}

.hex-dashboard-aurora .device-panel-title .el-link {
  color: #e7f9ff;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.2px;
}

.hex-dashboard-aurora .device-panel-title .el-link:hover {
  color: #67e8f9;
}

.hex-dashboard-aurora .device-panel-title small {
  margin-left: 8px;
  padding: 2px 7px;
  border: 1px solid rgba(148, 197, 234, 0.12);
  border-radius: 999px;
  color: #7f9eb3;
  background: rgba(3, 14, 25, 0.34);
  font-size: 8px;
}

.hex-dashboard-aurora .hex-drag-handle {
  color: #6f91a8;
}

.hex-dashboard-aurora .hex-drag-handle:hover {
  color: #67e8f9;
  background: rgba(34, 211, 238, 0.08);
}

.hex-dashboard-aurora .group-dot {
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.hex-dashboard-aurora .single-metric-side {
  padding-left: 16px;
  border-left: 1px solid rgba(148, 197, 234, 0.1);
}

.hex-dashboard-aurora .single-side-kicker {
  color: #67e8f9;
  font-size: 7px;
  letter-spacing: 1.5px;
}

.hex-dashboard-aurora .single-side-value {
  color: #f1fcff;
  text-shadow: 0 0 20px rgba(34, 211, 238, 0.18);
}

.hex-dashboard-aurora .single-side-label {
  color: #8fb0c4;
}

.hex-dashboard-aurora .multi-metric-body {
  gap: 8px;
  padding: 12px 14px 16px;
}

.hex-dashboard-aurora .hex-empty {
  margin: 10px;
  padding: 46px 20px;
  border: 1px dashed rgba(148, 197, 234, 0.16);
  border-radius: 18px;
  background: rgba(4, 15, 27, 0.35);
  color: #718da2;
}

.hex-dashboard-aurora .panel-resize-note {
  color: #526f84;
}

.hex-dashboard-aurora :deep(.metric-graphic-shell) {
  border-width: 1.5px;
  box-shadow:
    inset 0 0 34px rgba(1, 10, 20, 0.94),
    inset 0 1px 1px rgba(255, 255, 255, 0.13),
    0 14px 34px rgba(1, 10, 20, 0.42),
    0 0 30px color-mix(in srgb, var(--hex-color) 22%, transparent);
}

.hex-dashboard-aurora :deep(.sphere-shell) {
  box-shadow:
    inset 0 0 26px rgba(1, 10, 20, 0.9),
    0 14px 30px rgba(1, 8, 17, 0.4),
    0 0 26px color-mix(in srgb, var(--hex-color) 18%, transparent);
}

@media (max-width: 1200px) {
  .hex-dashboard-aurora { padding: 18px; border-radius: 18px; }
  .hex-dashboard-aurora .hex-head-actions { max-width: 100%; }
  .hex-dashboard-aurora .hex-head-copy h2 { font-size: 22px; }
}

@media (max-width: 760px) {
  .hex-dashboard-aurora { padding: 14px; border-radius: 14px; }
  .hex-dashboard-aurora .hex-dashboard-head { align-items: flex-start; }
  .hex-dashboard-aurora .hex-head-copy h2 { font-size: 19px; }
}



/* ============================================================
   设备指标工作台（Metric Workbench）— 全新页面设计
   ============================================================ */
.mx-dash {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  padding: 24px;
  border: 1px solid #dfe8f2;
  border-radius: 22px;
  background: #f4f8fc !important;
  color: #172b3d !important;
  box-shadow: 0 16px 44px rgba(25, 55, 85, 0.07);
  scrollbar-width: thin;
  scrollbar-color: #cbd9e7 transparent;
}

.mx-dash::before,
.mx-dash::after { display: none; }

.mx-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  padding-bottom: 18px;
  border-bottom: 1px solid #e1eaf3;
}

.mx-kicker {
  color: #0f8f8a;
  font-family: Consolas, monospace;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 2.2px;
}

.mx-title h1 {
  margin: 7px 0 0;
  color: #122b42 !important;
  font-size: 27px;
  font-weight: 700;
  letter-spacing: 0.4px;
}

.mx-title p {
  margin: 6px 0 0;
  color: #7b8fa3;
  font-size: 11px;
}

.mx-head-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
}

.mx-health {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 5px;
  border: 1px solid #e2ebf4;
  border-radius: 10px;
  background: #fff;
}

.mx-health span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 8px;
  border-radius: 7px;
  color: #64788b;
  font-size: 10px;
  white-space: nowrap;
}

.mx-health span i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #10b981;
}

.mx-health .info i { background: #3b82f6; }
.mx-health .warning i { background: #f59e0b; }
.mx-health .critical i { background: #ef4444; }
.mx-health .emergency i { background: #991b1b; }
.mx-health .info { background: #eff6ff; color: #1d4ed8; }
.mx-health .warning { background: #fff9ed; color: #a16207; }
.mx-health .critical { background: #fff2f2; color: #b91c1c; }
.mx-health .emergency { background: #7f1d1d; color: #fee2e2; }

.mx-dash .mx-head-actions :deep(.el-button) {
  height: 32px;
  padding: 0 13px;
  border-color: #dfe9f2;
  border-radius: 9px;
  background: #fff;
  color: #466176;
  font-size: 11px;
}

.mx-dash .mx-head-actions :deep(.el-button:hover) {
  border-color: #9bd7d3;
  background: #f1fbfa;
  color: #087f7a;
}

.mx-attention {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 14px;
  padding: 9px 11px;
  overflow-x: auto;
  border: 1px solid #f5e4c2;
  border-radius: 11px;
  background: #fffcf5;
  scrollbar-width: none;
}

.mx-attention::-webkit-scrollbar { display: none; }

.mx-attention-title {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
  color: #9a6a1c;
  font-size: 10px;
  font-weight: 600;
  white-space: nowrap;
}

.mx-attention-title span {
  display: grid;
  place-items: center;
  width: 15px;
  height: 15px;
  border-radius: 50%;
  background: #f59e0b;
  color: #fff;
  font-size: 10px;
  font-weight: 800;
}

.mx-attention-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
  padding: 5px 9px;
  border: 1px solid #efdcb8;
  border-radius: 7px;
  background: #fff;
  color: #8a6b35;
  font-size: 9px;
  cursor: pointer;
}

.mx-attention-chip b { color: #6b4a16; font-weight: 600; }
.mx-attention-chip em { color: #b45309; font-family: monospace; font-style: normal; font-weight: 700; }
.mx-attention-chip.info { border-color: #bfdbfe; background: #eff6ff; color: #1d4ed8; }
.mx-attention-chip.info em { color: #2563eb; }
.mx-attention-chip.critical { border-color: #fecaca; background: #fff5f5; color: #a94442; }
.mx-attention-chip.critical em { color: #dc2626; }
.mx-attention-chip.emergency { border-color: #991b1b; background: #fef2f2; color: #7f1d1d; }
.mx-attention-chip.emergency em { color: #991b1b; }

.mx-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 14px 0 12px;
}

.mx-toolbar-copy {
  color: #8095a7;
  font-size: 10px;
}

.mx-toolbar-copy strong {
  color: #143a52;
  font-family: "Cascadia Mono", monospace;
  font-size: 15px;
}

.mx-live-controls {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-left: auto;
}

.mx-live-controls :deep(.el-switch__label) {
  color: #6c8193;
  font-size: 9px;
}

.mx-unit-control { display: inline-flex; align-items: center; gap: 5px; }
.mx-input-unit { flex: 0 0 auto; color: #38566b; font-size: 11px; font-weight: 600; white-space: nowrap; }
.mx-pager {
  display: flex;
  align-items: center;
  gap: 7px;
}

.mx-page-label {
  color: #7c91a3;
  font-size: 10px;
}

.mx-pager b {
  min-width: 40px;
  color: #264b63;
  font-family: "Cascadia Mono", monospace;
  font-size: 11px;
  text-align: center;
}

.mx-pager :deep(.el-button) {
  border-color: #dce8f2;
  background: #fff;
  color: #4d6b80;
}

.mx-pager :deep(.el-select__wrapper) {
  border-radius: 7px;
  box-shadow: 0 0 0 1px #dce8f2 inset;
}

.mx-grid-scroll {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 2px 4px 20px 0;
  scrollbar-gutter: stable;
}
.mx-head,
.mx-attention,
.mx-toolbar { flex: 0 0 auto; }
.mx-empty { flex: 1 1 auto; overflow-y: auto; }
.mx-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  align-items: start;
  gap: 14px;
}

.mx-grid.mx-cols-1 { grid-template-columns: minmax(0, 1fr); }
.mx-grid.mx-cols-2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }

.mx-device-card {
  min-width: 0;
  overflow: hidden;
  border: 1px solid #e0e9f2;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 5px 18px rgba(27, 57, 83, 0.045);
  transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
}

.mx-device-card:hover {
  box-shadow: 0 12px 26px rgba(27, 57, 83, 0.12);
  transform: translateY(-2px);
}

.mx-device-card {
  border-color: #e0e9f2;
}

.mx-metric.info { border-color: #3b82f6; background: #eff6ff; }
.mx-metric.info .mx-status,
.mx-metric.info .mx-value { color: #1d4ed8; }
.mx-metric.info .mx-track i { background: #3b82f6; }

.mx-metric.warning { border-color: #f59e0b; background: #fffcf5; }
.mx-metric.critical { border-color: #ef4444; background: #fff8f8; }
.mx-metric.normal { border-color: #10b981; background: #f0fdf4; }
.mx-metric.emergency {
  border-color: #991b1b;
  background: #fef2f2;
  animation: mx-emergency-flash 1.05s ease-in-out infinite;
}

@keyframes mx-emergency-flash {
  0%, 100% { border-color: #991b1b; box-shadow: 0 0 0 1px rgba(153, 27, 27, 0.35), 0 4px 12px rgba(127, 29, 29, 0.22); }
  50% { border-color: #ef4444; box-shadow: 0 0 0 4px rgba(153, 27, 27, 0.38), 0 8px 18px rgba(127, 29, 29, 0.32); }
}

@media (prefers-reduced-motion: reduce) {
  .mx-metric.emergency { animation: none; }
}

.mx-device-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 12px 14px;
  border-bottom: 1px solid #eef4f8;
  background: linear-gradient(180deg, #fbfdff, #fff);
}

.mx-device-name {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 7px;
}

.mx-device-dot {
  flex: 0 0 auto;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #10b981;
}

.mx-device-dot.info { background: #3b82f6; }
.mx-device-dot.warning { background: #f59e0b; }
.mx-device-dot.critical { background: #ef4444; }
.mx-device-dot.emergency { background: #991b1b; box-shadow: 0 0 0 3px rgba(153, 27, 27, 0.18); }

.mx-link {
  max-width: 190px;
  overflow: hidden;
  padding: 0;
  border: 0;
  background: transparent;
  color: #173c55;
  font-size: 13px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
}

.mx-link:hover { color: #0f8f8a; }

.mx-device-name small {
  overflow: hidden;
  color: #8ca0b2;
  font-family: Consolas, monospace;
  font-size: 9px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mx-device-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
}

.mx-type,
.mx-count {
  padding: 3px 7px;
  border-radius: 5px;
  color: #688094;
  background: #f2f7fb;
  font-size: 8px;
  white-space: nowrap;
}

.mx-badge {
  min-width: 20px;
  padding: 3px 6px;
  border-radius: 5px;
  font-family: monospace;
  font-size: 8px;
  text-align: center;
}

.mx-badge.normal { background: #e9fbf5; color: #0b8f68; }
.mx-badge.info { background: #eff6ff; color: #1d4ed8; }
.mx-badge.warning { background: #fff7e6; color: #b45309; }
.mx-badge.critical { background: #fff0f0; color: #dc2626; }
.mx-badge.emergency { background: #7f1d1d; color: #fee2e2; }

.mx-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(132px, 1fr));
  gap: 8px;
  padding: 12px;
}

.mx-metric {
  --mx-color: #0ea5e9;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 5px;
  min-width: 0;
  padding: 10px;
  border: 1px solid #edf2f7;
  border-radius: 9px;
  background: #fbfdff;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.16s ease, background 0.16s ease;
}

.mx-metric:hover {
  border-color: color-mix(in srgb, var(--mx-color) 36%, #dbe7f1);
  background: #fff;
}

.mx-metric.warning { border-color: #f59e0b; background: #fffcf5; }
.mx-metric.critical { border-color: #ef4444; background: #fff8f8; }
.mx-metric.normal { border-color: #10b981; background: #f0fdf4; }
.mx-metric.info { border-color: #3b82f6; background: #eff6ff; }
.mx-metric.emergency { border-color: #991b1b; background: #fef2f2; }

.mx-metric-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.mx-metric-label {
  overflow: hidden;
  color: #6c8193;
  font-size: 9px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mx-status {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  flex: 0 0 auto;
  color: #0b8f68;
  font-size: 8px;
}

.mx-status i {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: currentColor;
}

.mx-metric.info .mx-status { color: #1d4ed8; }
.mx-metric.warning .mx-status { color: #b45309; }
.mx-metric.critical .mx-status { color: #dc2626; }
.mx-metric.emergency .mx-status { color: #991b1b; }

.mx-value {
  overflow: hidden;
  color: #15364c;
  font-family: "Cascadia Mono", "DIN Alternate", monospace;
  font-size: 25px;
  font-weight: 700;
  line-height: 1.05;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mx-value small {
  margin-left: 2px;
  color: #8ca0b2;
  font-size: 9px;
  font-weight: 400;
}

.mx-track {
  height: 3px;
  overflow: hidden;
  border-radius: 3px;
  background: #edf3f8;
}

.mx-track i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--mx-color);
}

.mx-metric.info .mx-track i { background: #3b82f6; }
.mx-metric.warning .mx-track i { background: #f59e0b; }
.mx-metric.critical .mx-track i { background: #ef4444; }
.mx-metric.emergency .mx-track i { background: #991b1b; }

.mx-metric-foot {
  overflow: hidden;
  color: #9aacbb;
  font-size: 8px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mx-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 70px 20px;
  border: 1px dashed #d8e5ef;
  border-radius: 14px;
  color: #8ba0b2;
  background: #fbfdff;
  font-size: 11px;
}

.mx-dash:fullscreen {
  padding: 24px;
  border-radius: 0;
  background: #f4f8fc;
}

@media (max-width: 1180px) {
  .mx-head { align-items: flex-start; flex-direction: column; }
  .mx-head-actions { justify-content: flex-start; }
  .mx-grid, .mx-grid.mx-cols-2, .mx-grid.mx-cols-3 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 760px) {
  .mx-dash { padding: 15px; border-radius: 14px; }
  .mx-title h1 { font-size: 21px; }
  .mx-grid, .mx-grid.mx-cols-2, .mx-grid.mx-cols-3 { grid-template-columns: minmax(0, 1fr); }
  .mx-toolbar { align-items: flex-start; flex-direction: column; }
  .mx-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}



/* 指标工作台：分组、卡片数值颜色与批量阈值 */
.mx-group-mode {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
}
.mx-metric-group-title {
  color: #214667;
  font-size: 14px;
  font-weight: 700;
}
.mx-metric-device {
  overflow: hidden;
  margin-bottom: 1px;
  color: #0f766e;
  font-size: 9px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mx-metric-device small {
  margin-left: 4px;
  color: #94a3b8;
  font-size: 8px;
  font-weight: 400;
}
.mx-metric.normal .mx-value { color: #0f766e; }
.mx-metric.info .mx-value { color: #1d4ed8; }
.mx-metric.warning .mx-value { color: var(--mx-warning, #f59e0b); }
.mx-metric.critical .mx-value { color: var(--mx-critical, #ef4444); }
.mx-metric.emergency .mx-value { color: #991b1b; }
.mx-metric.muted .mx-value { color: #94a3b8; }
.mx-metric.warning .mx-value small,
.mx-metric.critical .mx-value small { color: currentColor; opacity: .72; }
.hex-select-hint {
  color: #94a3b8;
  font-size: 9px;
  white-space: nowrap;
}
.hex-batch-panel {
  margin: 0 0 12px;
  padding: 12px 14px;
  border: 1px solid #bfdbfe;
  border-radius: 10px;
  background: #f8fbff;
}
.hex-batch-panel-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 10px;
}
.hex-batch-panel-head strong { color: #1e3a5f; font-size: 12px; }
.hex-batch-panel-head span { color: #7b91a5; font-size: 10px; }
.hex-batch-panel-head .el-button { margin-left: auto; }
.hex-batch-panel-grid {
  display: grid;
  grid-template-columns: minmax(150px, 1.3fr) repeat(4, minmax(80px, .7fr)) auto;
  align-items: end;
  gap: 8px;
}
.hex-batch-panel-grid label { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.hex-batch-panel-grid label > span { color: #7b91a5; font-size: 9px; }
@media (max-width: 900px) {
  .hex-batch-panel-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .hex-batch-panel-grid > .el-button { width: 100%; }
}

</style>