/** 自定义大屏：配置存储、默认值与指标工具 */
import { assetApi } from '@/api'

export const BIGSCREEN_STORAGE_KEY = 'nms_bigscreens_v1'
export const BIGSCREEN_VERSION_KEY = 'nms_bigscreens_version'
const BIGSCREEN_VERSION = '2'

export const WIDGET_FONT_SIZES = [10, 12, 14, 16, 18, 20, 24, 28, 32, 36]

export const WIDGET_TYPES = [
  { value: 'kpi', label: '指标卡' },
  { value: 'gauge', label: '单设备仪表' },
  { value: 'bar', label: '指标排行' },
  { value: 'table', label: '设备表格' },
  { value: 'server', label: '服务器硬件' },
  { value: 'alerts', label: '实时告警' },
  { value: 'trend', label: '告警趋势' },
  { value: 'website', label: '网站监控' },
  { value: 'text', label: '文本 / 标题' },
  { value: 'topology', label: '网络拓扑' },
  { value: 'virtualization', label: '虚拟化资源监控' },
  { value: 'zabbix', label: 'Zabbix 指标' },
]

export const KPI_OPTIONS = [
  { value: 'total_devices', label: '设备总数' },
  { value: 'enabled_devices', label: '监控中设备' },
  { value: 'online_devices', label: '在线设备' },
  { value: 'offline_devices', label: '离线设备' },
  { value: 'server_devices', label: '服务器数量' },
  { value: 'unack_alerts', label: '未处理告警' },
  { value: 'recent_alerts_24h', label: '24h 告警数' },
  { value: 'avg_cpu', label: '平均 CPU' },
  { value: 'avg_memory', label: '平均内存' },
]

export const METRIC_OPTIONS = [
  { value: 'cpu_usage', label: 'CPU 使用率', unit: '%' },
  { value: 'memory_usage', label: '内存使用率', unit: '%' },
  { value: 'temperature', label: '温度', unit: '°C' },
  { value: 'power_status', label: '电源状态', unit: '' },
  { value: 'srv_cpu_temp', label: 'CPU 温度', unit: '°C' },
  { value: 'srv_mem_fault', label: '内存故障', unit: '' },
  { value: 'srv_power_voltage', label: '电源电压', unit: 'V' },
  { value: 'srv_power_current', label: '电源电流', unit: 'A' },
  { value: 'srv_disk_fault', label: '物理硬盘故障', unit: '' },
  { value: 'srv_inlet_temp', label: '进风温度', unit: '°C' },
  { value: 'srv_exhaust_temp', label: '排风温度', unit: '°C' },
  { value: 'srv_fan_speed', label: '风扇转速', unit: 'RPM' },
]

export const TIMEZONE_OPTIONS = [
  { value: 'local', label: '跟随浏览器' },
  { value: 'Asia/Shanghai', label: 'Asia/Shanghai (中国标准时间)' },
  { value: 'Asia/Tokyo', label: 'Asia/Tokyo (日本标准时间)' },
  { value: 'Asia/Singapore', label: 'Asia/Singapore (新加坡时间)' },
  { value: 'UTC', label: 'UTC (协调世界时)' },
  { value: 'Europe/London', label: 'Europe/London (伦敦)' },
  { value: 'Europe/Berlin', label: 'Europe/Berlin (柏林)' },
  { value: 'America/New_York', label: 'America/New_York (纽约)' },
  { value: 'America/Los_Angeles', label: 'America/Los_Angeles (洛杉矶)' },
  { value: 'Australia/Sydney', label: 'Australia/Sydney (悉尼)' },
]

export const CLOCK_FONT_OPTIONS = [
  { value: "Bahnschrift, 'DIN Alternate', 'Microsoft YaHei', sans-serif", label: '科技数字（Bahnschrift / DIN）' },
  { value: "'Microsoft YaHei', sans-serif", label: '微软雅黑' },
  { value: "'Source Han Sans SC', 'Noto Sans SC', sans-serif", label: '思源黑体 / Noto Sans' },
  { value: "Consolas, 'SFMono-Regular', monospace", label: '等宽数字（Consolas）' },
  { value: "'Arial Black', 'Microsoft YaHei', sans-serif", label: '粗体无衬线（Arial Black）' },
  { value: "Georgia, 'Times New Roman', serif", label: '衬线字体（Georgia）' },
]

export function defaultClock() {
  return {
    fontSize: 20,
    showYear: true,
    showMonth: true,
    showDay: true,
    showWeekday: true,
    hour12: false,
    timezone: 'local',
    fontFamily: CLOCK_FONT_OPTIONS[0].value,
    bold: true,
  }
}

export function defaultDisplay() {
  return {
    fontFamily: defaultClock().fontFamily,
    fontSize: 14,
  }
}

export function normalizeScreen(screen) {
  const base = screen && typeof screen === 'object' ? screen : {}
  const clock = { ...defaultClock(), ...(base.clock || {}) }
  if (!clock.timezone) clock.timezone = 'local'
  delete clock.dateFontSize
  return {
    ...base,
    widgets: Array.isArray(base.widgets)
      ? base.widgets.map((widget) => ({
        ...widget,
        fontSize: Number(widget?.fontSize) > 0 ? Number(widget.fontSize) : 0,
      }))
      : [],
    display: {
      ...defaultDisplay(),
      ...(base.display || {}),
    },
    clock,
    zabbix: {
      url: '',
      token: '',
      username: '',
      password: '',
      verify_tls: true,
      ...(base.zabbix || {}),
    },
  }
}

export function makeId(prefix = 's') {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return `${prefix}-${crypto.randomUUID()}`
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`
}

export function defaultWidget(type = 'kpi') {
  const base = {
    id: makeId('w'),
    type,
    title: '新指标',
    span: 3,
    fontSize: 0,
    fontFamily: '',
    content: '输入自定义文本',
    align: 'left',
    color: '#e2f8ff',
    metric: 'cpu_usage',
    kpiKey: 'total_devices',
    deviceId: '',
    limit: 5,
    websiteLimit: 6,
    level: '',
    host: '',
    item: '',
    aggregation: 'last',
    minutes: 60,
    unit: '',
    precision: 1,
  }
  if (type === 'kpi') return { ...base, title: '设备总数', kpiKey: 'total_devices', span: 3 }
  if (type === 'gauge') return { ...base, title: '设备 CPU', span: 3 }
  if (type === 'bar') return { ...base, title: 'CPU 使用率 TOP5', span: 6, limit: 5 }
  if (type === 'table') return { ...base, title: '设备运行状态', span: 6, limit: 8 }
  if (type === 'server') return { ...base, title: '服务器硬件状态', span: 6 }
  if (type === 'alerts') return { ...base, title: '实时告警', span: 6, limit: 6 }
  if (type === 'trend') return { ...base, title: '24 小时告警趋势', span: 12 }
  if (type === 'website') return { ...base, title: '网站健康态势', span: 6, websiteLimit: 6 }
  if (type === 'text') return { ...base, title: '自定义标题', span: 6, content: '在这里输入自定义标题或说明文字', fontSize: 18 }
  if (type === 'topology') return { ...base, title: '网络拓扑', span: 12 }
  if (type === 'virtualization') return { ...base, title: '虚拟化资源监控', span: 12, limit: 8 }
  if (type === 'zabbix') return { ...base, title: 'Zabbix 指标', span: 3, precision: 1 }
  return base
}

export function readScreens() {
  try {
    const parsed = JSON.parse(localStorage.getItem(BIGSCREEN_STORAGE_KEY) || 'null')
    if (Array.isArray(parsed)) return parsed.map(normalizeScreen)
  } catch {
    /* 忽略损坏配置 */
  }
  return []
}

export function writeScreens(screens) {
  try {
    localStorage.setItem(BIGSCREEN_STORAGE_KEY, JSON.stringify(screens))
  } catch {
    /* 忽略存储异常 */
  }
}

export function createScreen(name = '新增大屏') {
  return {
    id: makeId('screen'),
    name,
    description: '',
    refresh: 10,
    display: defaultDisplay(),
    clock: defaultClock(),
    zabbix: { url: '', token: '', username: '', password: '', verify_tls: true },
    widgets: [
      { ...defaultWidget('kpi'), id: makeId('w'), title: '设备总数', kpiKey: 'total_devices', span: 3 },
      { ...defaultWidget('kpi'), id: makeId('w'), title: '未处理告警', kpiKey: 'unack_alerts', span: 3 },
      { ...defaultWidget('bar'), id: makeId('w'), title: 'CPU 使用率 TOP5', metric: 'cpu_usage', span: 6, limit: 5 },
    ],
  }
}

export function cloneScreen(screen) {
  return normalizeScreen(JSON.parse(JSON.stringify(screen)))
}

export function metricMeta(key) {
  return METRIC_OPTIONS.find((item) => item.value === key) || METRIC_OPTIONS[0]
}

export function deviceMetricValue(device, key) {
  if (!device) return null
  const metric = device.metric || {}
  if (key === 'power_status') return metric.power_status || null
  if (['cpu_usage', 'memory_usage', 'temperature'].includes(key)) {
    const value = metric[key]
    return value === null || value === undefined ? null : Number(value)
  }
  const value = (metric.custom || {})[key]
  return value === null || value === undefined ? null : Number(value)
}

export function metricText(device, key) {
  const value = deviceMetricValue(device, key)
  if (value === null || value === undefined || Number.isNaN(value)) return '--'
  if (key === 'power_status') return value === 'normal' ? '正常' : '异常'
  if (key === 'srv_mem_fault' || key === 'srv_disk_fault') return Number(value) <= 1 ? '正常' : '故障'
  const meta = metricMeta(key)
  const precision = key === 'srv_power_current' ? 2 : 1
  return `${Number(value).toFixed(precision)}${meta.unit || ''}`
}

export async function fetchAllDevices() {
  const items = []
  let page = 1
  while (page <= 20) {
    const res = await assetApi.getList({ page, size: 100 })
    const batch = res.data.items || []
    items.push(...batch)
    const total = Number(res.data.total || 0)
    if (!batch.length || items.length >= total) break
    page += 1
  }
  return items
}
