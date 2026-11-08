/**
 * 系统配置（前端侧）
 * - 公开配置登录页即可读取
 * - 全局生效：系统名称（标题）、语言、时区、刷新间隔、自动注销
 */
import { reactive } from 'vue'
import axios from 'axios'
import { setLocale, t } from '@/i18n'

const state = reactive({
  loaded: false,
  system_name: t('header.defaultSystemName'),
  login_subtitle: '设备监测 · 机房与网站监测 · 即时通信 · 设备备份 · 虚拟化纳管 · 智能运维',
  system_logo: '',
  copyright_enabled: true,
  copyright_name: '智能运维服务平台',
  copyright_text: `© ${new Date().getFullYear()} 智能运维服务平台 版权所有`,
  copyright_color: '#94a3b8',
  language: 'zh-CN',
  timezone: 'Asia/Shanghai',
  captcha_enabled: true,
  auto_login: false,
  refresh_interval: 30,
  auto_logout_minutes: 30,
  alert_sound_interval: 60,
  alert_broadcast_enabled: false,
  alert_broadcast_counts: true,
  alert_broadcast_details: true,
  alert_broadcast_levels: 'info,warning,critical,emergency',
  alert_broadcast_max_items: 3,
})

export const settings = state

/** 常用时区选项（与后端白名单一致） */
export const TIMEZONE_OPTIONS = [
  'Asia/Shanghai', 'Asia/Hong_Kong', 'Asia/Taipei', 'Asia/Tokyo',
  'Asia/Seoul', 'Asia/Singapore', 'Asia/Bangkok', 'Asia/Kolkata',
  'Asia/Dubai', 'Europe/London', 'Europe/Paris', 'Europe/Berlin',
  'Europe/Moscow', 'America/New_York', 'America/Chicago',
  'America/Denver', 'America/Los_Angeles', 'America/Sao_Paulo',
  'Australia/Sydney', 'UTC',
].map((value) => ({ value, label: value.replace('_', ' ') }))

/** 读取公开系统配置（登录页 / 外壳） */
export async function loadPublicSettings() {
  try {
    const res = await axios.get('/api/settings/public', {
      params: { _t: Date.now() },
      headers: { 'Cache-Control': 'no-cache', Pragma: 'no-cache' },
    })
    Object.assign(state, res.data)
    state.loaded = true
    applyGlobal()
    return state
  } catch {
    state.loaded = false
    return state
  }
}

/** 应用全局效果：语言、html lang、浏览器图标 */
export function applyGlobal() {
  setLocale(state.language || 'zh-CN')
  applyFavicon()
}

function applyFavicon() {
  try {
    let link = document.querySelector('link[rel="icon"]')
    if (!link) {
      link = document.createElement('link')
      link.rel = 'icon'
      document.head.appendChild(link)
    }
    const logo = state.system_logo || '/logo-default.svg'
    link.href = logo
    const clean = logo.split('?')[0].toLowerCase()
    if (clean.endsWith('.svg')) link.type = 'image/svg+xml'
    else if (clean.endsWith('.ico')) link.type = 'image/x-icon'
    else if (clean.endsWith('.webp')) link.type = 'image/webp'
    else if (clean.endsWith('.gif')) link.type = 'image/gif'
    else if (clean.endsWith('.jpg') || clean.endsWith('.jpeg')) link.type = 'image/jpeg'
    else link.type = 'image/png'
  } catch {
    /* 忽略 DOM 异常 */
  }
}

/** 前端自动刷新间隔（毫秒） */
export function refreshMs() {
  const seconds = Number(state.refresh_interval) || 30
  return Math.max(5, Math.min(600, seconds)) * 1000
}
