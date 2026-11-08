import { alertRuleApi, assetApi } from '@/api'
import { readDashboardMetricsConfig } from '@/utils/dashboardMetrics'

const BASE_LABELS = {
  cpu_usage: 'CPU 使用率',
  memory_usage: '内存使用率',
  temperature: '最高部件温度',
  disk_usage: '磁盘使用率',
  power: '电源状态',
  fan_speed: '风扇转速',
}

function ruleSpec(item) {
  const key = String(item.metric || '')
  if (!key || key.startsWith('if_') || ['alert_count', 'warranty_days_left', 'power_status'].includes(key)) return null
  if (['cpu_usage', 'memory_usage', 'temperature', 'disk_usage', 'power'].includes(key)) return { metric: key, custom_key: null }
  if (key === 'srv_fan_speed') return { metric: 'fan_speed', custom_key: null }
  return { metric: 'custom', custom_key: key }
}

function lowerDirection(key) {
  return key === 'warranty_days_left'
}

const MIGRATION_FLAG = 'nms_dashboard_rule_sync_v1'

export async function syncDashboardRulesFromStorage() {
  try {
    if (localStorage.getItem(MIGRATION_FLAG) === '1') return { created: 0, updated: 0 }
  } catch {
    /* 忽略存储异常 */
  }
  const config = readDashboardMetricsConfig()
  if (!Array.isArray(config) || !config.length) return { created: 0, updated: 0 }
  const deviceIds = [...new Set(config.map((item) => Number(item.deviceId)).filter(Boolean))]
  if (!deviceIds.length) return { created: 0, updated: 0 }
  const devices = new Map()
  for (const deviceId of deviceIds) {
    try {
      const res = await assetApi.getOne(deviceId)
      if (res?.data?.id) devices.set(Number(res.data.id), res.data)
    } catch {
      /* 无权限或设备已删除时跳过 */
    }
  }
  let channels = []
  try {
    const channelRes = await alertRuleApi.channels()
    channels = (channelRes?.data || []).filter((channel) => channel.enabled).map((channel) => channel.id)
  } catch {
    channels = []
  }
  let created = 0
  let updated = 0
  for (const deviceId of deviceIds) {
    const device = devices.get(deviceId)
    if (!device) continue
    let existing = []
    try {
      const res = await alertRuleApi.list(deviceId)
      existing = Array.isArray(res?.data) ? res.data : []
    } catch {
      continue
    }
    for (const item of config.filter((row) => Number(row.deviceId) === deviceId)) {
      const spec = ruleSpec(item)
      if (!spec) continue
      const operator = lowerDirection(item.metric) ? 'lte' : 'gte'
      const label = BASE_LABELS[spec.metric] || spec.custom_key || spec.metric
      for (const [level, thresholdKey, levelText] of [
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
          // 自定义规则优先；已有规则不被仪表盘旧值覆盖。
          continue
        } else {
          await alertRuleApi.create({
            device_id: deviceId,
            name: `仪表盘同步 · ${label} ${levelText}`,
            metric: spec.metric,
            custom_key: spec.custom_key,
            operator,
            threshold,
            level,
            level_label: levelText,
            notify_channel_ids: channels,
            enabled: true,
          })
          created += 1
        }
      }
    }
  }
  try {
    localStorage.setItem(MIGRATION_FLAG, '1')
  } catch {
    /* 忽略存储异常 */
  }
  return { created, updated }
}
