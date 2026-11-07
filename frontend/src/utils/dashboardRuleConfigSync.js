import { DASHBOARD_CONFIG_KEY, readDashboardMetricsConfig } from '@/utils/dashboardMetrics'

function dashboardMetricKey(rule) {
  if (!rule) return ''
  if (rule.metric === 'custom') return String(rule.custom_key || '')
  if (rule.metric === 'fan_speed') return 'srv_fan_speed'
  return String(rule.metric || '')
}

/**
 * 自定义告警规则优先：规则保存/启停后把阈值写回仪表盘指标配置。
 * 仪表盘配置只作为展示与规则缺失时的初始来源，不反向覆盖已有规则。
 */
export function syncRuleToDashboardConfig(deviceId, rule) {
  if (!deviceId || !rule) return
  const metric = dashboardMetricKey(rule)
  const threshold = Number(rule.threshold)
  if (!metric || !Number.isFinite(threshold)) return
  const config = readDashboardMetricsConfig()
  let item = config.find((row) => String(row.deviceId) === String(deviceId) && String(row.metric) === metric)
  if (!item) {
    item = {
      id: `${deviceId}-${metric}`,
      deviceId: Number(deviceId),
      metric,
      warning: null,
      critical: null,
      warningColor: '#fbbf24',
      criticalColor: '#fb7185',
    }
    config.push(item)
  }
  if (['critical', 'emergency'].includes(String(rule.level || '').toLowerCase())) {
    item.critical = threshold
  } else {
    item.warning = threshold
  }
  try {
    localStorage.setItem(DASHBOARD_CONFIG_KEY, JSON.stringify(config))
    window.dispatchEvent(new CustomEvent('nms:dashboard-config-updated'))
  } catch {
    /* 本地存储不可用时忽略，规则本身仍已保存 */
  }
}


export function removeRuleFromDashboardConfig(deviceId, removedRule, remainingRules = []) {
  if (!deviceId || !removedRule) return
  const metric = dashboardMetricKey(removedRule)
  if (!metric) return
  const sameMetric = (remainingRules || []).filter((rule) => dashboardMetricKey(rule) === metric)
  const config = readDashboardMetricsConfig()
  const index = config.findIndex((row) => String(row.deviceId) === String(deviceId) && String(row.metric) === metric)
  if (index < 0) return
  if (sameMetric.length) {
    const levels = new Set(sameMetric.map((rule) => ['critical', 'emergency'].includes(String(rule.level || '').toLowerCase()) ? 'critical' : 'warning'))
    if (!levels.has('warning')) config[index].warning = null
    if (!levels.has('critical')) config[index].critical = null
    for (const rule of sameMetric) {
      const threshold = Number(rule.threshold)
      if (!Number.isFinite(threshold)) continue
      if (['critical', 'emergency'].includes(String(rule.level || '').toLowerCase())) config[index].critical = threshold
      else config[index].warning = threshold
    }
  } else {
    config.splice(index, 1)
  }
  try {
    localStorage.setItem(DASHBOARD_CONFIG_KEY, JSON.stringify(config))
    window.dispatchEvent(new CustomEvent('nms:dashboard-config-updated'))
  } catch {
    /* ignore */
  }
}
