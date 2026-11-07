/**
 * 告警声音提醒
 *
 * - 内置中文女声播报（提示/警告/严重/紧急），也支持系统配置上传的自定义声音文件
 * - 开关状态保存在 localStorage（按浏览器/用户记忆）
 * - 有未处理告警时播放；新告警或每 60 秒重复提醒（由 App 轮询逻辑控制）
 */
import { ref, watch } from 'vue'
import api from '@/api'

const STORAGE_KEY = 'nms_alert_sound_enabled'
const BUILTIN_SOUND_URLS = {
  info: '/sounds/alert-info.wav',
  warning: '/sounds/alert-warning.wav',
  critical: '/sounds/alert-critical.wav',
  emergency: '/sounds/alert-emergency.wav',
}
const TOGGLE_SOUND_URLS = {
  on: '/sounds/alert-sound-on.wav',
  off: '/sounds/alert-sound-off.wav',
}

export const alertSoundEnabled = ref(localStorage.getItem(STORAGE_KEY) !== '0')

// 自定义声音（系统配置按严重级别上传）
export const customSoundUrls = ref({ info: '', warning: '', critical: '', emergency: '' })
export const customSoundUrl = ref('')
export const customSoundName = ref('')
export const customSoundUpdatedAt = ref('')

let audioContext = null
const customAudioCache = new Map()
const builtinAudioCache = new Map()
const toggleAudioCache = new Map()
const alertToneOscillators = new Set()

watch(alertSoundEnabled, (value) => {
  try {
    localStorage.setItem(STORAGE_KEY, value ? '1' : '0')
  } catch {
    /* 忽略存储异常 */
  }
  // 总开关关闭时，立即停止正在播放的分级音、详细语音和待播报定时器
  if (!value) stopAllAlertAudio()
})

/** 读取各严重级别的告警声音配置（自定义文件 / 内置提示音） */
export async function loadAlertSoundInfo() {
  try {
    const res = await api.get('/settings/alert-sound')
    const data = res.data || {}
    const levels = data.levels || {
      info: { custom: false, url: '' },
      warning: { custom: false, url: '' },
      critical: { custom: false, url: '' },
      emergency: { custom: data.custom, url: data.url, filename: data.filename, updated_at: data.updated_at },
    }
    customSoundUrls.value = Object.fromEntries(
      ['info', 'warning', 'critical', 'emergency'].map((level) => [
        level,
        levels[level]?.custom ? levels[level].url : '',
      ]),
    )
    const emergency = levels.emergency || {}
    customSoundUrl.value = emergency.custom ? emergency.url : ''
    customSoundName.value = emergency.custom ? emergency.filename : ''
    customSoundUpdatedAt.value = emergency.custom ? emergency.updated_at : ''
    for (const level of customAudioCache.keys()) {
      if (!customSoundUrls.value[level]) customAudioCache.delete(level)
    }
    return { ...data, levels }
  } catch {
    return null
  }
}

function ensureAudioContext() {
  const Ctor = window.AudioContext || window.webkitAudioContext
  if (!Ctor) return null
  if (!audioContext) audioContext = new Ctor()
  if (audioContext.state === 'suspended') {
    audioContext.resume().catch(() => {})
  }
  return audioContext
}

/** 内置中文女声播报（每个级别独立 WAV） */
async function playBuiltinSound(level) {
  const url = BUILTIN_SOUND_URLS[level] || BUILTIN_SOUND_URLS.warning
  try {
    let audio = builtinAudioCache.get(level)
    if (!audio || audio.dataset.url !== url) {
      audio = new Audio(url)
      audio.preload = 'auto'
      audio.dataset.url = url
      builtinAudioCache.set(level, audio)
    }
    audio.volume = 1
    audio.currentTime = 0
    await audio.play()
    return true
  } catch {
    return false
  }
}

/** 开关小喇叭时单独播报「告警打开 / 告警关闭」 */
async function playTogglePrompt(enabled) {
  const key = enabled ? 'on' : 'off'
  const url = TOGGLE_SOUND_URLS[key]
  try {
    let audio = toggleAudioCache.get(key)
    if (!audio || audio.dataset.url !== url) {
      audio = new Audio(url)
      audio.preload = 'auto'
      audio.dataset.url = url
      toggleAudioCache.set(key, audio)
    }
    audio.volume = 1
    audio.currentTime = 0
    await audio.play()
    return true
  } catch {
    return false
  }
}

/** 文件无法播放时的合成三声设备提示音兜底 */
function playToneFallback() {
  playToneSequence([
    [0.00, 880.00], [0.18, 1108.73], [0.36, 1318.51],
    [0.78, 880.00], [0.96, 1108.73], [1.14, 1318.51],
  ], 0.32, true)
}

function playToneSequence(notes, volume = 0.3, alertTone = false) {
  const ctx = ensureAudioContext()
  if (!ctx) return false
  try {
    const start = ctx.currentTime + 0.02
    notes.forEach(([offset, frequency, duration = 0.16]) => {
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.type = 'sine'
      osc.frequency.value = frequency
      const at = start + offset
      gain.gain.setValueAtTime(0.0001, at)
      gain.gain.exponentialRampToValueAtTime(volume, at + 0.015)
      gain.gain.exponentialRampToValueAtTime(0.0001, at + duration)
      osc.connect(gain)
      gain.connect(ctx.destination)
      osc.start(at)
      osc.stop(at + duration + 0.01)
      if (alertTone) {
        alertToneOscillators.add(osc)
        osc.onended = () => alertToneOscillators.delete(osc)
      }
    })
    return true
  } catch {
    return false
  }
}

/** 不同严重级别使用明显不同的节奏与音高 */
export const LEVEL_SOUNDS = {
  info: { label: '女声：提示告警', notes: [[0, 660, 0.18]] },
  warning: { label: '女声：警告报警', notes: [[0, 880, 0.16], [0.22, 988, 0.16]] },
  critical: { label: '女声：严重告警', notes: [[0, 880, 0.16], [0.2, 1108, 0.16], [0.4, 1318, 0.16], [0.82, 880, 0.16], [1.02, 1108, 0.16], [1.22, 1318, 0.16]] },
  emergency: { label: '女声：紧急告警', notes: [[0, 1200, 0.12], [0.15, 780, 0.12], [0.3, 1200, 0.12], [0.45, 780, 0.12], [0.6, 1200, 0.12], [0.75, 780, 0.12], [0.9, 1200, 0.12]] },
}

function playLevelTone(level) {
  const sound = LEVEL_SOUNDS[level] || LEVEL_SOUNDS.warning
  return playToneSequence(sound.notes, level === 'emergency' ? 0.4 : 0.3, true)
}

async function playCustomSound(level) {
  const url = customSoundUrls.value[level]
  if (!url) return false
  try {
    let audio = customAudioCache.get(level)
    if (!audio || audio.dataset.url !== url) {
      audio = new Audio(url)
      audio.preload = 'auto'
      audio.dataset.url = url
      customAudioCache.set(level, audio)
    }
    audio.currentTime = 0
    audio.volume = level === 'emergency' ? 0.9 : 0.8
    await audio.play()
    return true
  } catch {
    return false
  }
}

/** 即时通信新消息提示音：与告警音区分开的短促双音。 */
export function playMessageSound() {
  return playToneSequence([[0, 1046.5, 0.11], [0.14, 1318.51, 0.15]], 0.24)
}

let callRingAudio = null
let callRingFallbackTimer = null

function stopCallToneFallback() {
  if (callRingFallbackTimer) {
    window.clearInterval(callRingFallbackTimer)
    callRingFallbackTimer = null
  }
}

function startCallToneFallback(kind = 'incoming') {
  const ring = () => {
    // 柔和三音提示；去电只用低音量双音回拨
    const notes = kind === 'outgoing'
      ? [[0, 392, 0.30], [0.32, 523.25, 0.30]]
      : [[0, 523.25, 0.38], [0.24, 659.25, 0.42], [0.48, 783.99, 0.52]]
    playToneSequence(notes, kind === 'outgoing' ? 0.10 : 0.17)
  }
  ring()
  stopCallToneFallback()
  callRingFallbackTimer = window.setInterval(ring, kind === 'outgoing' ? 1900 : 2600)
}

/** 播放来电/去电铃声；来电循环，直到接听、拒绝或挂断时停止。 */
export function playCallRingtone(kind = 'incoming') {
  stopCallRingtone()
  try {
    if (typeof Audio !== 'undefined') {
      callRingAudio = new Audio(kind === 'outgoing' ? '/sounds/call-dial.wav' : '/sounds/call-ring.wav')
      callRingAudio.loop = true
      callRingAudio.preload = 'auto'
      callRingAudio.volume = kind === 'outgoing' ? 0.28 : 0.55
      const promise = callRingAudio.play()
      if (promise?.catch) {
        promise.catch(() => {
          callRingAudio = null
          startCallToneFallback(kind)
        })
      }
      return true
    }
  } catch {
    /* 自动播放被拦截时使用 Web Audio 兜底 */
  }
  startCallToneFallback(kind)
  return true
}

export function stopCallRingtone() {
  stopCallToneFallback()
  if (callRingAudio) {
    try {
      callRingAudio.pause()
      callRingAudio.currentTime = 0
    } catch {
      /* 忽略音频停止异常 */
    }
    callRingAudio = null
  }
}

/** 在用户首次点击/按键时解锁浏览器音频上下文，保证后续消息提示音可播放。 */
export function unlockAlertAudio() {
  try {
    window.speechSynthesis?.getVoices?.()
  } catch {
    /* 部分浏览器不支持语音合成 */
  }
  return ensureAudioContext()
}

const BROADCAST_LEVELS = [
  { value: 'info', label: '提示' },
  { value: 'warning', label: '警告' },
  { value: 'critical', label: '严重' },
  { value: 'emergency', label: '紧急' },
]

function normalizeBroadcastLevels(value) {
  const source = Array.isArray(value)
    ? value
    : String(value || '').split(',')
  const selected = new Set(source.map((item) => String(item).trim()).filter(Boolean))
  return BROADCAST_LEVELS.filter((item) => selected.has(item.value))
}

function broadcastUnit(unit = '') {
  const value = String(unit || '').trim()
  // 浏览器中文语音会把 "ms" 读成英文字母，播报时统一换成中文。
  if (value.toLowerCase() === 'ms') return '毫秒'
  return value
}

function formatBroadcastValue(value, unit = '') {
  if (value === null || value === undefined || value === '') return ''
  const number = Number(value)
  if (Number.isNaN(number)) return String(value)
  const text = Number.isInteger(number) ? String(number) : String(Math.round(number * 10) / 10)
  return `${text}${broadcastUnit(unit)}`
}

function formatBroadcastNumber(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return ''
  return Number.isInteger(number) ? String(number) : String(Math.round(number * 10) / 10)
}

function broadcastComparison(alert) {
  const value = Number(alert.value)
  const threshold = Number(alert.threshold)
  if (!Number.isFinite(value) || !Number.isFinite(threshold)) return ''
  const unit = alert.metric_unit || ''
  const unitText = unit === '%' ? '个百分点' : broadcastUnit(unit)
  const valueText = formatBroadcastValue(value, unit)
  const thresholdText = formatBroadcastValue(threshold, unit)
  const operator = alert.operator || 'gt'
  const diff = Math.abs(value - threshold)
  const diffText = `${formatBroadcastNumber(diff)}${unitText}`
  if (operator === 'lt' || operator === 'lte') {
    return value < threshold
      ? `，当前值 ${valueText}，阈值 ${thresholdText}，低于阈值 ${diffText}`
      : `，当前值 ${valueText}，阈值 ${thresholdText}，当前未低于阈值`
  }
  if (operator === 'gt' || operator === 'gte') {
    return value > threshold
      ? `，当前值 ${valueText}，阈值 ${thresholdText}，超出阈值 ${diffText}`
      : `，当前值 ${valueText}，阈值 ${thresholdText}，当前未超出阈值`
  }
  if (operator === 'eq') {
    return `，当前值 ${valueText}，阈值 ${thresholdText}，${value === threshold ? '达到阈值' : `与阈值相差 ${diffText}`}`
  }
  return `，当前值 ${valueText}，阈值 ${thresholdText}`
}

/** 根据未处理告警生成中文播报文案；数量和内容均可单独开关。 */
export function buildAlertBroadcastText(alerts, options = {}) {
  const list = Array.isArray(alerts) ? alerts.filter(Boolean) : []
  if (!list.length) return ''
  const levels = normalizeBroadcastLevels(
    options.levels ?? 'info,warning,critical,emergency',
  )
  if (!levels.length) return ''
  const counts = options.counts !== false
  const details = options.details !== false
  const requestedLimit = Number(options.maxItems)
  const maxItems = Number.isFinite(requestedLimit) && requestedLimit > 0
    ? Math.min(1000, Math.floor(requestedLimit))
    : 0
  const grouped = Object.fromEntries(levels.map((item) => [item.value, []]))
  list.forEach((alert) => {
    const level = String(alert.alert_level || '').toLowerCase()
    if (grouped[level]) grouped[level].push(alert)
  })

  const parts = [`当前共有 ${list.length} 条未处理告警`]
  if (counts) {
    levels.forEach((level) => {
      parts.push(`${level.label}告警 ${grouped[level.value].length} 条`)
    })
  }
  if (details) {
    levels.forEach((level) => {
      const items = grouped[level.value]
      if (!items.length) return
      const shownItems = maxItems > 0 ? items.slice(0, maxItems) : items
      const contents = shownItems.map((alert) => {
        const device = alert.device_name || alert.ip_address || '设备'
        const type = alert.alert_type_text || alert.metric_label || alert.alert_type || '告警'
        const comparison = broadcastComparison(alert)
        if (comparison) return `${device}，${type}${comparison}`
        const value = formatBroadcastValue(alert.value, alert.metric_unit || '')
        return `${device}，${type}${value ? `，当前值 ${value}` : ''}`
      })
      const overflow = maxItems > 0 && items.length > maxItems ? `，其余 ${items.length - maxItems} 条` : ''
      parts.push(`${level.label}告警内容：${contents.join('；')}${overflow}`)
    })
  }
  return `${parts.filter(Boolean).join('。')}。`
}

let broadcastTimer = null
let broadcastSpeaking = false

export function isAlertBroadcastSpeaking() {
  return broadcastSpeaking || Boolean(broadcastTimer)
}

function stopCachedAudios(cache) {
  for (const audio of cache.values()) {
    try {
      audio.pause()
      audio.currentTime = 0
    } catch {
      /* 忽略音频停止异常 */
    }
  }
}

/** 总开关关闭时彻底停止告警相关声音、语音播报和待播报任务。 */
export function stopAllAlertAudio() {
  stopAlertBroadcast()
  stopCachedAudios(customAudioCache)
  stopCachedAudios(builtinAudioCache)
  stopCachedAudios(toggleAudioCache)
  for (const oscillator of alertToneOscillators) {
    try {
      oscillator.stop()
    } catch {
      /* 已停止 */
    }
  }
  alertToneOscillators.clear()
}

/** 停止上一轮详细播报，避免新告警播报与旧播报重叠。 */
export function stopAlertBroadcast() {
  if (broadcastTimer) {
    window.clearTimeout(broadcastTimer)
    broadcastTimer = null
  }
  broadcastSpeaking = false
  try {
    window.speechSynthesis?.cancel?.()
  } catch {
    /* 忽略浏览器语音异常 */
  }
}

/** 使用浏览器中文语音播报详细告警；force=true 仅在总开关开启时用于设置页试听。 */
export function speakAlertBroadcast(alerts, options = {}, force = false) {
  if (!alertSoundEnabled.value) return false
  if (!force && !options.enabled) return false
  if (!force && isAlertBroadcastSpeaking()) return false
  const text = buildAlertBroadcastText(alerts, options)
  if (!text) return false
  const synth = window.speechSynthesis
  const Utterance = window.SpeechSynthesisUtterance
  if (!synth || !Utterance) return false
  try {
    // 试听时允许替换正在播放的内容；实际告警播报在上方已经拒绝重复触发
    stopAlertBroadcast()
    const utterance = new Utterance(text)
    utterance.lang = 'zh-CN'
    utterance.rate = 1
    utterance.pitch = 1
    utterance.volume = 1
    const voices = synth.getVoices?.() || []
    const chineseVoice = voices.find((voice) => /^zh(-|_)/i.test(voice.lang || ''))
    if (chineseVoice) utterance.voice = chineseVoice
    const finish = () => {
      if (!broadcastSpeaking) return
      broadcastSpeaking = false
      if (typeof options.onEnd === 'function') options.onEnd()
    }
    utterance.onend = finish
    utterance.onerror = finish
    broadcastSpeaking = true
    synth.speak(utterance)
    return true
  } catch {
    broadcastSpeaking = false
    return false
  }
}

/** 声音播放后稍作停顿再播报详情，避免与分级告警音重叠。 */
export function scheduleAlertBroadcast(alerts, options = {}, delay = 1400) {
  if (!alertSoundEnabled.value || !options.enabled) return false
  if (isAlertBroadcastSpeaking()) return false
  stopAlertBroadcast()
  broadcastTimer = window.setTimeout(() => {
    broadcastTimer = null
    speakAlertBroadcast(alerts, options, true)
  }, Math.max(0, Number(delay) || 0))
  return true
}

/** 播放告警音：优先播放该级别自定义文件，否则播放该级别中文女声播报 */
export async function playAlertSound(level = 'warning', force = false) {
  // 总开关关闭时，即使内部 force 调用也不允许再发出告警声音
  if (!alertSoundEnabled.value) return
  const normalized = LEVEL_SOUNDS[level] ? level : 'warning'
  const custom = await playCustomSound(normalized)
  if (custom) return
  const builtin = await playBuiltinSound(normalized)
  if (!builtin) {
    if (!playLevelTone(normalized)) playToneFallback()
  }
}

export function toggleAlertSound() {
  const enabled = !alertSoundEnabled.value
  alertSoundEnabled.value = enabled
  if (enabled) {
    // 开启时播放“告警已开启”；关闭时不再播放任何提示音，并立即停止已有声音
    playTogglePrompt(true)
  } else {
    stopAllAlertAudio()
  }
  return enabled
}

export function useAlertSound() {
  return {
    alertSoundEnabled,
    customSoundUrl,
    customSoundUrls,
    customSoundName,
    customSoundUpdatedAt,
    loadAlertSoundInfo,
    toggleAlertSound,
    playAlertSound,
    levelSounds: LEVEL_SOUNDS,
  }
}
