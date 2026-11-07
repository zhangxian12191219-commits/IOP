/**
 * 时间处理工具
 *
 * 后端返回的是 UTC 的朴素 ISO 字符串（如 "2026-10-27T12:22:46"），
 * 浏览器 new Date() 会按本地时区解析，导致偏差。这里统一补齐 'Z' 后再解析，
 * 并按「系统配置 → 时区」格式化输出。
 */
import { settings } from '@/store/settings'

/** 把后端时间字符串安全解析为 Date（UTC） */
export function parseServerDate(value) {
  if (!value) return null
  if (value instanceof Date) return value
  const str = String(value)
  const hasZone = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(str)
  const d = new Date(hasZone ? str : `${str}Z`)
  return Number.isNaN(d.getTime()) ? null : d
}

/** 距今秒数 */
export function ageSeconds(value) {
  const d = parseServerDate(value)
  if (!d) return Infinity
  return (Date.now() - d.getTime()) / 1000
}

function formatter(options) {
  const timeZone = settings.timezone || undefined
  try {
    return new Intl.DateTimeFormat('zh-CN', {
      timeZone,
      hourCycle: 'h23',
      ...options,
    })
  } catch {
    return new Intl.DateTimeFormat('zh-CN', { hourCycle: 'h23', ...options })
  }
}

function partsOf(value) {
  const d = parseServerDate(value)
  if (!d) return null
  const fmt = formatter({
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
  const map = {}
  for (const part of fmt.formatToParts(d)) {
    if (part.type !== 'literal') map[part.type] = part.value
  }
  return map
}

/** YYYY-MM-DD HH:mm:ss（按系统配置时区） */
export function formatDateTime(value) {
  const p = partsOf(value)
  if (!p) return '-'
  return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}:${p.second}`
}

/** HH:mm */
export function formatHM(value) {
  const p = partsOf(value)
  if (!p) return '-'
  return `${p.hour}:${p.minute}`
}

/** HH:mm:ss */
export function formatHMS(value) {
  const p = partsOf(value)
  if (!p) return '-'
  return `${p.hour}:${p.minute}:${p.second}`
}

/** 当前配置时区名称 */
export function currentTimezone() {
  return settings.timezone || 'Local'
}
