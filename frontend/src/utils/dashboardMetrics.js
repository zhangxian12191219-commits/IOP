import { temperatureDisplayName } from './serverComponentLabels'

export const DASHBOARD_CONFIG_KEY = 'nms_hex_dashboard_v1'

export function readDashboardMetricsConfig() {
  try {
    const raw = localStorage.getItem(DASHBOARD_CONFIG_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

const BASE_METRICS = {
  cpu_usage: { label: 'CPU 使用率', unit: '%' },
  memory_usage: { label: '内存使用率', unit: '%' },
  temperature: { label: '最高部件温度', unit: '°C' },
  disk_usage: { label: '磁盘使用率', unit: '%' },
  power_status: { label: '电源状态', unit: '' },
  alert_count: { label: '未处理告警', unit: '条' },
  warranty_days_left: { label: '维保剩余天数', unit: '天', direction: 'lower' },
}

function componentAt(device, kind, index) {
  const components = device?.metric?.components || device?.metric?.custom?.server_components || {}
  return (components[kind] || [])[Number(index)] || null
}

function metricMeta(item, device) {
  const key = String(item.metric || '')
  if (BASE_METRICS[key]) return BASE_METRICS[key]
  const temp = key.match(/^srv_component_temp_(\d+)$/)
  if (temp) {
    const component = componentAt(device, 'temperatures', temp[1])
    return { label: component ? temperatureDisplayName(component.name) : '温度', unit: '°C' }
  }
  const fan = key.match(/^srv_component_fan_(\d+)$/)
  if (fan) {
    const component = componentAt(device, 'fans', fan[1])
    return { label: component ? `风扇 · ${component.name || `#${Number(fan[1]) + 1}`}` : '风扇转速', unit: 'RPM' }
  }
  const psuWatts = key.match(/^srv_component_psu_watts_(\d+)$/)
  if (psuWatts) {
    const component = componentAt(device, 'power_supplies', psuWatts[1])
    return { label: component ? `电源功率 · ${component.name || '电源'}` : '电源功率', unit: 'W' }
  }
  const psuVoltage = key.match(/^srv_component_psu_voltage_(\d+)$/)
  if (psuVoltage) {
    const component = componentAt(device, 'power_supplies', psuVoltage[1])
    return { label: component ? `电源电压 · ${component.name || '电源'}` : '电源电压', unit: 'V' }
  }
  const disk = key.match(/^srv_component_disk_(\d+)$/)
  if (disk) {
    const component = componentAt(device, 'disks', disk[1])
    return { label: component ? `硬盘容量 · ${component.name || '硬盘'}` : '硬盘容量', unit: 'GB' }
  }
  const sensorLabels = {
    srv_cpu_temp: ['CPU 温度', '°C'],
    srv_inlet_temp: ['系统板入口温度', '°C'],
    srv_exhaust_temp: ['系统板排气温度', '°C'],
    srv_fan_speed: ['风扇转速', 'RPM'],
    srv_power_watts: ['电源功率', 'W'],
    srv_power_voltage: ['电源电压', 'V'],
    srv_disk_usage: ['硬盘使用率', '%'],
  }
  if (sensorLabels[key]) return { label: sensorLabels[key][0], unit: sensorLabels[key][1] }
  const custom = (device?.custom_metrics || []).find((entry) => String(entry.key) === key)
    || (device?.server_sensors || []).find((entry) => String(entry.key) === key)
  return { label: custom?.name || key, unit: custom?.unit || '' }
}

function metricValue(item, device) {
  const key = String(item.metric || '')
  const metric = device?.metric || {}
  if (key === 'alert_count') return Number(device?.alert_count) || 0
  if (['cpu_usage', 'memory_usage', 'temperature', 'disk_usage', 'power_status'].includes(key)) return metric[key]
  if (key === 'warranty_days_left') return device?.warranty_days_left
  if (key === 'srv_inlet_temp' || key === 'srv_exhaust_temp' || key === 'srv_cpu_temp') {
    const temps = (metric.components || metric.custom?.server_components || {}).temperatures || []
    const pattern = key === 'srv_inlet_temp' ? /inlet|进气|进风/i : key === 'srv_exhaust_temp' ? /exhaust|排气|排风/i : /cpu|处理器/i
    return temps.find((entry) => pattern.test(String(entry.name || '')))?.value
  }
  if (key === 'srv_fan_speed') {
    const values = (metric.components?.fans || metric.custom?.server_components?.fans || []).map((entry) => Number(entry.value)).filter(Number.isFinite)
    return values.length ? Math.max(...values) : metric.custom?.[key]
  }
  if (key === 'srv_power_watts') {
    const values = (metric.components?.power_supplies || metric.custom?.server_components?.power_supplies || []).map((entry) => Number(entry.watts)).filter(Number.isFinite)
    return values.length ? values.reduce((a, b) => a + b, 0) : metric.custom?.[key]
  }
  const temp = key.match(/^srv_component_temp_(\d+)$/)
  if (temp) return componentAt(device, 'temperatures', temp[1])?.value
  const fan = key.match(/^srv_component_fan_(\d+)$/)
  if (fan) return componentAt(device, 'fans', fan[1])?.value
  const psuWatts = key.match(/^srv_component_psu_watts_(\d+)$/)
  if (psuWatts) return componentAt(device, 'power_supplies', psuWatts[1])?.watts
  const psuVoltage = key.match(/^srv_component_psu_voltage_(\d+)$/)
  if (psuVoltage) return componentAt(device, 'power_supplies', psuVoltage[1])?.voltage
  const disk = key.match(/^srv_component_disk_(\d+)$/)
  if (disk) return componentAt(device, 'disks', disk[1])?.size_gb
  return metric.custom?.[key]
}

function metricSeverity(item, value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return ''
  const warning = Number(item.warning)
  const critical = Number(item.critical)
  const direction = BASE_METRICS[item.metric]?.direction || 'higher'
  if (Number.isFinite(critical) && (direction === 'lower' ? number <= critical : number >= critical)) return 'critical'
  if (Number.isFinite(warning) && (direction === 'lower' ? number <= warning : number >= warning)) return 'warning'
  return ''
}

export function formatMetricValue(metric, value = metric.value) {
  if (value === null || value === undefined || value === '') return '--'
  return `${value}${metric.unit || ''}`
}

function hasBoundaryComponent(device, kind) {
  const components = device?.metric?.components || device?.metric?.custom?.server_components || {}
  const pattern = kind === 'inlet' ? /inlet|进气|进风/i : /exhaust|排气|排风/i
  return (components.temperatures || []).some((item) => pattern.test(String(item.name || '')))
}

export function buildDeviceDashboardMetrics(config, device) {
  if (!device) return []
  const seenMetrics = new Set()
  return (Array.isArray(config) ? config : [])
    .filter((item) => String(item.deviceId) === String(device.id))
    .filter((item) => {
      if (seenMetrics.has(item.metric)) return false
      seenMetrics.add(item.metric)
      return true
    })
    .filter((item) => {
      // 采集到独立入口/排气探头时，不再重复显示汇总指标。
      if (item.metric === 'srv_inlet_temp' && hasBoundaryComponent(device, 'inlet')) return false
      if (item.metric === 'srv_exhaust_temp' && hasBoundaryComponent(device, 'exhaust')) return false
      return true
    })
    .map((item) => {
      const meta = metricMeta(item, device)
      const value = metricValue(item, device)
      let severity = metricSeverity(item, value)
      let status = severity === 'critical' ? '告警' : severity === 'warning' ? '预警' : (value === null || value === undefined ? '无数据' : '正常')
      const diskMatch = String(item.metric || '').match(/^srv_component_disk_(\d+)$/)
      if (diskMatch) {
        const disk = componentAt(device, 'disks', diskMatch[1])
        const diskText = `${disk?.status || ''} ${disk?.status_label || ''}`.toLowerCase()
        if (diskText.includes('standby') || diskText.includes('spun down') || diskText.includes('休眠')) {
          status = '休眠'
        } else if (/(fault|fail|degraded|warning|critical|offline|missing|predictive|error|bad|unknown|未知|降级|故障|离线|缺位)/.test(diskText)) {
          severity = 'emergency'
          status = '故障'
        }
      }
      return {
        key: item.metric,
        label: meta.label,
        unit: meta.unit,
        value,
        warning: item.warning,
        critical: item.critical,
        severity,
        status,
      }
    })
}
