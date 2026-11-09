/**
 * 认证状态管理（轻量，无需 Pinia）
 * - token / 用户信息持久化：自动登录开启时存 localStorage，关闭时存 sessionStorage
 * - 提供登录、登出、权限判断、带 token 下载
 */
import { reactive, computed } from 'vue'
import axios from 'axios'

const TOKEN_KEY = 'nms_token'
const USER_KEY = 'nms_user'
const REMEMBER_KEY = 'nms_remember'
const HANDOFF_KEY = 'nms_token_handoff'
const HANDOFF_TTL = 5 * 60 * 1000

const state = reactive({
  token: readToken(),
  user: JSON.parse(localStorage.getItem(USER_KEY) || sessionStorage.getItem(USER_KEY) || 'null'),
})

/**
 * 新标签页令牌交接
 * 默认「自动登录」关闭时 token 存在 sessionStorage（不跨标签页），
 * 打开大屏等新页签前写入一次性 handoff（60 秒内有效），新页签加载后取出并立即删除。
 */
export function handoffToken(token) {
  if (!token) return
  try {
    const user = state.user
      || JSON.parse(localStorage.getItem(USER_KEY) || sessionStorage.getItem(USER_KEY) || 'null')
    localStorage.setItem(
      HANDOFF_KEY,
      JSON.stringify({ token, user, ts: Date.now() })
    )
  } catch {
    /* 忽略存储异常 */
  }
}

export function consumeHandoff() {
  try {
    const raw = localStorage.getItem(HANDOFF_KEY)
    if (!raw) return
    localStorage.removeItem(HANDOFF_KEY)
    const data = JSON.parse(raw)
    if (!data?.token) return
    if (Date.now() - Number(data.ts || 0) > HANDOFF_TTL) return
    if (getToken()) return
    state.token = data.token
    sessionStorage.setItem(TOKEN_KEY, data.token)
    // 路由守卫从 storage 读取用户权限；交接时同步恢复用户信息
    if (data.user && typeof data.user === 'object') {
      state.user = data.user
      sessionStorage.setItem(USER_KEY, JSON.stringify(data.user))
    }
  } catch {
    /* 忽略 */
  }
}

consumeHandoff()

export const authState = state

export const isLoggedIn = computed(() => !!state.token)

export const currentUser = computed(() => state.user || {})

/** 读取 token（localStorage 优先，其次 sessionStorage） */
export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || sessionStorage.getItem(TOKEN_KEY) || ''
}

function readToken() {
  return getToken()
}

/** 是否勾选了自动登录 */
export function isRemembered() {
  return localStorage.getItem(REMEMBER_KEY) === '1'
}

/** 权限判断（超级管理员或拥有该权限点） */
export function can(permission) {
  const user = state.user
  if (!user) return false
  if (user.is_superuser) return true
  return Array.isArray(user.permissions) && user.permissions.includes(permission)
}

export function setToken(token, remember = true) {
  state.token = token || ''
  localStorage.removeItem(TOKEN_KEY)
  sessionStorage.removeItem(TOKEN_KEY)
  if (!token) {
    localStorage.removeItem(REMEMBER_KEY)
    return
  }
  if (remember) {
    localStorage.setItem(TOKEN_KEY, token)
    localStorage.setItem(REMEMBER_KEY, '1')
  } else {
    sessionStorage.setItem(TOKEN_KEY, token)
    localStorage.removeItem(REMEMBER_KEY)
  }
}

export function setUser(user) {
  state.user = user || null
  localStorage.removeItem(USER_KEY)
  sessionStorage.removeItem(USER_KEY)
  if (user) {
    const storage = isRemembered() ? localStorage : sessionStorage
    storage.setItem(USER_KEY, JSON.stringify(user))
  }
}

export function clearAuth() {
  setToken('')
  setUser(null)
}

export async function login(username, password, options = {}) {
  const payload = { username, password }
  if (options.captchaId) payload.captcha_id = options.captchaId
  if (options.captchaCode) payload.captcha_code = options.captchaCode

  const res = await axios.post('/api/auth/login', payload)
  const { token, user } = res.data
  setToken(token, options.remember !== false)
  setUser(user)
  return user
}

export async function refreshMe() {
  const token = getToken()
  if (!token) return null
  try {
    const res = await axios.get('/api/auth/me', {
      headers: { Authorization: `Bearer ${token}` },
    })
    setUser(res.data)
    return res.data
  } catch {
    return null
  }
}

export function logout(redirect = true) {
  clearAuth()
  if (redirect && window.location.pathname !== '/login') {
    window.location.href = '/login'
  }
}

/**
 * 带登录令牌的下载（导出 Excel/CSV 等）
 * 浏览器直接跳转无法携带 Authorization 头，因此用 ?token= 传递
 */
export function downloadWithAuth(url) {
  const token = getToken()
  if (!token) {
    window.location.href = '/login'
    return
  }
  const sep = url.includes('?') ? '&' : '?'
  window.location.href = `${url}${sep}token=${encodeURIComponent(token)}`
}
