<template>
  <div class="gw-screen">
    <div class="gw-grid-bg"></div>
    <header class="gw-head">
      <div class="gw-brand">
        <div class="gw-mark"><span>AI</span></div>
        <div><b>{{ assistantName }} · AI 网关运维智脑</b><small>GATEWAY OPERATIONS INTELLIGENCE</small></div>
      </div>
      <div class="gw-head-center">
        <span class="gw-live"><i></i>LIVE GATEWAY</span>
        <span class="gw-date">{{ dateText }}</span>
        <span class="gw-clock">{{ clockText }}</span>
      </div>
      <div class="gw-head-actions">
        <span class="gw-status" :class="{ ok: aiStatus.configured }"><i></i>{{ aiStatus.configured ? aiStatus.model : 'LOCAL AGENT' }}</span>
        <el-button size="small" @click="$router.push('/bigscreen')">大屏中心</el-button>
        <el-button size="small" @click="$router.push('/ai')">AI 运维</el-button>
      </div>
    </header>

    <div class="gw-body">
      <aside class="gw-rail gw-left">
        <section class="gw-panel gw-health-panel">
          <div class="gw-panel-head"><span>GATEWAY HEALTH</span><b>网关健康</b></div>
          <BigScreenAutoScroll class="gw-scroll" :speed="5">
            <div class="gw-scroll-body">
              <div class="gw-health-ring" :style="{ '--health': `${health.asset_enabled_percent || 0}%` }">
                <div><strong>{{ health.asset_enabled_percent ?? 0 }}</strong><small>HEALTH</small></div>
              </div>
              <div class="gw-health-meta">
                <span><i class="ok"></i>AI CORE 在线</span><span>{{ onlineRate }}% 资产在线</span>
              </div>
            </div>
          </BigScreenAutoScroll>
        </section>

        <section class="gw-panel">
          <div class="gw-panel-head"><span>ACCESS MATRIX</span><b>资源接入</b></div>
          <BigScreenAutoScroll class="gw-scroll" :speed="7">
            <div class="gw-access-list">
              <div v-for="node in gatewayNodes" :key="node.key"><span>{{ node.label }}</span><b>{{ node.value }}</b><small>{{ node.sub }}</small></div>
            </div>
          </BigScreenAutoScroll>
        </section>

        <section class="gw-panel gw-panel-grow">
          <div class="gw-panel-head"><span>ASSET SPECTRUM</span><b>设备构成</b></div>
          <div ref="assetScrollEl" class="gw-scroll-native" @mouseenter="panelPausedUntil.asset = Date.now() + 60000" @mouseleave="panelPausedUntil.asset = 0" @wheel.passive="panelPausedUntil.asset = Date.now() + 2500">
            <div class="gw-bar-list">
              <div v-for="item in assetTypeRows" :key="item.type"><em>{{ item.label }}</em><i><b :style="{ width: `${item.percent}%` }"></b></i><strong>{{ item.count }}</strong></div>
              <small v-if="!assetTypeRows.length" class="gw-muted">暂无设备类型数据</small>
            </div>
          </div>
        </section>
      </aside>

      <main class="gw-stage">
        <div class="gw-stage-title">
          <div><span>GATEWAY DIGITAL TWIN</span><h1>网关链路 · 实时态势</h1></div>
          <div class="gw-stage-tags"><span>NORTHBOUND</span><span>AI CORE</span><span>SOUTHBOUND</span></div>
        </div>

        <div ref="gateway3dEl" class="gw-scene-wrap">
          <canvas ref="gatewayCanvasRef" class="gw-canvas"></canvas>
          <div class="gw-scan"></div>
          <div class="gw-positive-banner">{{ positiveText }}</div>
          <div class="gw-core-label" :class="{ alert: highAlertCount > 0 }">
            <span>AI GATEWAY</span><b>{{ highAlertCount > 0 ? 'ATTENTION' : 'HEALTHY' }}</b>
          </div>
          <div v-for="node in gatewayNodes" :key="`label-${node.key}`" class="gw-node-label" :class="node.pos">
            <span>{{ node.label }}</span><b>{{ node.value }}</b>
          </div>
          <div class="gw-scene-caption"><span>● DATA PLANE</span><span>● AI PLANE</span><span>● CONTROL PLANE</span></div>
        </div>

        <div class="gw-telemetry">
          <div><span>ACTIVE ALERTS</span><b>{{ overview?.alerts?.active ?? 0 }}</b><small>活动告警</small></div>
          <div><span>MIB OBJECTS</span><b>{{ overview?.mibs?.objects ?? 0 }}</b><small>采集对象</small></div>
          <div><span>VM RESOURCES</span><b>{{ overview?.virtualization?.vms ?? 0 }}</b><small>虚拟资源</small></div>
          <div><span>AI LATENCY</span><b>{{ sending ? 'BUSY' : 'READY' }}</b><small>智能体状态</small></div>
        </div>

        <section class="gw-voice-console">
          <div class="gw-voice-left">
            <button v-if="speaking" type="button" class="gw-barge-btn" @click="interruptSpeech">打断</button>
            <button type="button" class="gw-voice-trigger" :class="{ active: voiceActive }" @click="toggleVoice">
              <span class="gw-mic"><i></i><i></i><i></i><i></i></span>
              <b>{{ voiceActive ? '停止连续语音' : '启动连续语音' }}</b>
              <small>{{ voiceActive ? 'LISTENING' : 'VOICE READY' }}</small>
            </button>
            <div class="gw-voice-copy">
              <span>{{ voiceStatusText }}</span>
              <small>{{ voiceTranscript || (speaking ? '播报中麦克风已暂停；点击“打断”后可插话' : '直接说，AI 播报结束后自动继续聆听') }}</small>
            </div>
          </div>
          <div class="gw-voice-wave"><i v-for="n in 22" :key="n" :style="{ animationDelay: `${n * .05}s`, height: `${5 + (n * 7) % 17}px` }"></i></div>
        </section>
      </main>

      <aside class="gw-rail gw-right">
        <section class="gw-panel gw-insight-panel">
          <div class="gw-panel-head"><span>AI INSIGHT</span><b>智能研判</b></div>
          <div ref="insightScrollEl" class="gw-scroll-native" @mouseenter="panelPausedUntil.insight = Date.now() + 60000" @mouseleave="panelPausedUntil.insight = 0" @wheel.passive="panelPausedUntil.insight = Date.now() + 2500">
            <p class="gw-insight-summary">{{ alertAnalysis?.summary || '正在汇总网关态势...' }}</p>
            <div class="gw-insight-list">
              <div v-for="item in (alertAnalysis?.causes || []).slice(0, 4)" :key="item.type"><b>{{ item.label }}</b><span>{{ item.cause }}</span></div>
              <small v-if="!alertAnalysis?.causes?.length" class="gw-muted">当前没有需要研判的告警</small>
            </div>
          </div>
        </section>
      <div class="gw-chat gw-chat-rail">
        <div class="gw-chat-head">
          <div><span>COMMAND CONSOLE</span><b>{{ assistantName }} · 智能体对话</b></div>
          <div><small>{{ voiceActive ? voiceStatusText : sending ? '分析中…' : '上下文已保留' }}</small><el-button text size="small" @click="startNewSession">新对话</el-button></div>
        </div>
        <div v-if="!aiStatus.configured" class="gw-model-hint">本地工具模式 · <el-button link type="primary" size="small" @click="$router.push('/ai')">接入大模型</el-button></div>
        <div ref="messagesEl" class="gw-messages" @scroll.passive="onMessagesScroll">
          <div v-for="(item, index) in messages" :key="index" class="gw-message" :class="item.role">
            <span class="gw-avatar">{{ item.role === 'user' ? 'U' : 'AI' }}</span>
            <div class="gw-message-main">
              <p>{{ item.content }}</p>
              <div v-if="item.steps?.length" class="gw-function-links">
                <span>相关功能</span>
                <button v-for="(step, si) in item.steps" :key="si" type="button" :class="{ failed: !step.ok }" @click="openFunction(step)">{{ step.label }} ↗</button>
              </div>
            </div>
          </div>
        </div>
        <div class="gw-input">
          <el-input v-model="input" placeholder="输入指令，或启动连续语音…" @keyup.enter="ask()" />
          <el-button v-if="sending" type="danger" plain @click="stopGeneration">停止</el-button>
          <el-button v-else type="primary" @click="ask()">发送</el-button>
        </div>
      </div>

      </aside>
    </div>

    <section class="gw-bottom">
      <div class="gw-alertdeck">
        <div class="gw-chat-head"><div><span>EVENT STREAM</span><b>实时告警流</b></div><small>{{ recentAlerts.length }} 条活动</small></div>
        <div ref="alertScrollEl" class="gw-alert-scroll" @mouseenter="alertPausedUntil = Date.now() + 60000" @mouseleave="alertPausedUntil = 0" @wheel.passive="alertPausedUntil = Date.now() + 2500">
          <div v-for="item in recentAlerts.slice(0, 8)" :key="`${item.id}-${item.created_at}`" class="gw-alert-item" :class="item.level">
            <span>{{ item.level_label || item.level }}</span><div><b>{{ item.device_name || item.device_ip || '网关对象' }}</b><small>{{ item.reason || item.message }}</small></div><time>{{ (item.created_at || '').slice(11, 19) }}</time>
          </div>
          <div v-if="!recentAlerts.length" class="gw-muted">当前没有活动告警</div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { aiApi } from '@/api'
import BigScreenAutoScroll from '@/components/BigScreenAutoScroll.vue'

const router = useRouter()
const aiStatus = ref({
  configured: false, name: '玄武', voice_name: '',
  tts_enabled: false, tts_model: '', tts_voice: '',
})
const overview = ref(null)
const assistantName = computed(() => String(aiStatus.value.name || '玄武').trim() || '玄武')
const messages = ref([{ role: 'assistant', content: 'AI 网关智脑已就绪。可以直接输入，或启动连续语音对话。' }])
const input = ref('')
const sending = ref(false)
const speaking = ref(false)
let askAbortController = null
let askSequence = 0
// 语音大屏会话：文字与连续语音共用同一 session_id 与消息序列，刷新后仍可续接前文。
const SESSION_KEY = 'ai_ops_voice_session_id'
const MESSAGES_KEY = 'ai_ops_voice_messages'
const sessionId = ref('')
const voiceActive = ref(false)
const voiceTranscript = ref('')
let recognition = null
let refreshTimer = null
let restartTimer = null
let speechTimer = null
let speechGeneration = 0
let voiceSilenceTimer = null
let voiceBuffer = ''
let recognitionRunning = false
let voiceErrorShown = false
let ttsAudio = null
let currentSpeechText = ''
let suppressVoiceUntil = 0
let positiveTimer = null
let alertAutoTimer = null
let alertPausedUntil = 0
let panelAutoTimer = null
const panelPausedUntil = { asset: 0, insight: 0 }
const positivePhrases = [
  '稳如磐石 · 从容运维', '每一份专注，都让网络更稳', '保持热爱，守护每一跳流量',
  '今天也要相信，问题都有解法', '把复杂留给自己，把稳定留给业务',
  '心有秩序，网关自稳', '认真巡检的人，运气都不会差', '慢慢来，比较快',
]
const positiveText = ref(positivePhrases[0])
function rotatePositive() {
  let next = positiveText.value
  while (next === positiveText.value) next = positivePhrases[Math.floor(Math.random() * positivePhrases.length)]
  positiveText.value = next
}

function welcomeGreeting() {
  const name = aiStatus.value.name || '玄武'
  const greetings = [
    `您好，我是${name}。很高兴陪您一起守护网关，愿今天的每一次巡检都带来安心，我们一起把风险提前化解。`,
    `您好，我是${name}。今天也请放心，我会陪您把每个告警看清楚，把每个细节照顾好，让网络稳稳运行。`,
    `您好，我是${name}。保持专注，也保持从容；有我在，我们一起守住网关的每一跳流量。`,
    `您好，我是${name}。愿您今天从容不迫，愿系统稳定如初，我们一起把问题解决在发生之前。`,
  ]
  return greetings[Math.floor(Math.random() * greetings.length)]
}
const messagesEl = ref(null)
const alertScrollEl = ref(null)
const assetScrollEl = ref(null)
const insightScrollEl = ref(null)
const stickToBottom = ref(true)
const gateway3dEl = ref(null)
const gatewayCanvasRef = ref(null)
const alertAnalysis = ref(null)
const now = ref(new Date())
const clockText = computed(() => now.value.toLocaleTimeString('zh-CN', { hour12: false }))
const dateText = computed(() => {
  const d = now.value
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
})
let clockTimer = null
let gwRenderer = null
let gwScene = null
let gwCamera = null
let gwGroup = null
let gwAnimation = null
let gwResizeObserver = null
const gwParticles = []
const TYPE_LABELS = {
  router: '路由器', switch: '交换机', firewall: '防火墙', server: '服务器',
  security: '安全设备', storage: '存储', wireless: '无线', other: '其他',
}

const assetTypeRows = computed(() => {
  const rows = overview.value?.assets?.by_type || []
  const max = Math.max(...rows.map((item) => Number(item.count) || 0), 1)
  return rows.slice(0, 5).map((item) => ({
    type: item.type,
    label: TYPE_LABELS[item.type] || item.type || '其他',
    count: Number(item.count) || 0,
    percent: Math.max(4, Math.round((Number(item.count) || 0) / max * 100)),
  }))
})
const mibCategoryRows = computed(() => {
  const rows = overview.value?.mibs?.categories || []
  const max = Math.max(...rows.map((item) => Number(item.count) || 0), 1)
  return rows.slice(0, 5).map((item) => ({
    category: item.category,
    count: Number(item.count) || 0,
    percent: Math.max(4, Math.round((Number(item.count) || 0) / max * 100)),
  }))
})
const ALERT_LEVEL_LABELS = { info: '提示', warning: '警告', critical: '严重', emergency: '紧急' }
const alertLevelRows = computed(() => {
  const levels = overview.value?.alerts?.by_level || {}
  return ['critical', 'emergency', 'warning', 'info']
    .filter((key) => Number(levels[key] || 0) > 0)
    .map((key) => ({ key, label: ALERT_LEVEL_LABELS[key], count: Number(levels[key] || 0) }))
})
const highAlertCount = computed(() => {
  const levels = overview.value?.alerts?.by_level || {}
  return Number(levels.critical || 0) + Number(levels.emergency || 0)
})
const onlineRate = computed(() => {
  const total = Number(overview.value?.assets?.total || 0)
  if (!total) return 0
  return Math.round(Number(overview.value?.assets?.enabled || 0) / total * 100)
})
const moduleStats = computed(() => overview.value?.module_stats || {})
const health = computed(() => moduleStats.value.health || {})
const gatewayNodes = computed(() => {
  const data = overview.value || {}
  return [
    { key: 'assets', label: '资产接入', sub: 'ASSETS', value: data.assets?.total ?? 0, pos: 'n1' },
    { key: 'alerts', label: '活动告警', sub: 'ALERTS', value: data.alerts?.active ?? 0, pos: 'n2' },
    { key: 'mib', label: 'MIB 对象', sub: 'MIB', value: data.mibs?.objects ?? 0, pos: 'n3' },
    { key: 'backup', label: '备份设备', sub: 'BACKUP', value: backups.value.enabled_devices ?? 0, pos: 'n4' },
    { key: 'virtual', label: '虚拟资源', sub: 'VIRTUAL', value: data.virtualization?.vms ?? 0, pos: 'n5' },
    { key: 'topology', label: '拓扑链路', sub: 'TOPOLOGY', value: topologyStats.value.links ?? 0, pos: 'n6' },
  ]
})
const backups = computed(() => moduleStats.value.backups || {})
const credentials = computed(() => moduleStats.value.credentials || {})
const mibCoverage = computed(() => moduleStats.value.mib_coverage || {})
const topologyStats = computed(() => moduleStats.value.topology || {})
const rooms = computed(() => moduleStats.value.rooms || {})
const websiteStats = computed(() => moduleStats.value.website || {})

const voiceStatusText = computed(() => {
  if (!voiceActive.value) return '连续语音未启动'
  if (sending.value) return '正在分析问题'
  if (speaking.value) return '正在播报，可直接插话打断'
  return '正在聆听，直接说即可'
})

const recentAlerts = computed(() => {
  const data = overview.value
  if (!data) return []
  return [...(data.alerts?.recent || []), ...(data.alerts?.website_recent || []), ...(data.alerts?.virtual_recent || [])]
    .sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
})

async function load() {
  try {
    const [statusRes, overviewRes, analysisRes] = await Promise.all([aiApi.status(), aiApi.overview(), aiApi.alertAnalysis()])
    aiStatus.value = statusRes.data || aiStatus.value
    const name = String(aiStatus.value.name || '玄武').trim() || '玄武'
    document.title = `${name} · AI 网关智脑`
    if (messages.value.length <= 1 && messages.value[0]?.role === 'assistant') {
      messages.value[0].content = `我是${name} AI 网关智脑，可以分析网关链路、资产告警、MIB 配置和全系统运行状态。可以直接提问或启动连续语音。`
    }
    persistConversation()
    overview.value = overviewRes.data
    alertAnalysis.value = analysisRes.data?.analysis || null
  } catch {
    /* 大屏不因单次刷新失败中断 */
  }
}

function scrollBottom(force = false) {
  nextTick(() => {
    const el = messagesEl.value
    if (!el) return
    if (!force && !stickToBottom.value) return
    el.scrollTop = el.scrollHeight
    window.requestAnimationFrame(() => {
      if (!messagesEl.value) return
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight
    })
  })
}

function onMessagesScroll(event) {
  const el = event.target
  if (!el) return
  stickToBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 42
}

function generateSessionId() {
  try {
    if (window.crypto?.randomUUID) return window.crypto.randomUUID()
  } catch { /* ignore */ }
  return `voice-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

function persistConversation() {
  try {
    sessionStorage.setItem(SESSION_KEY, sessionId.value)
    sessionStorage.setItem(MESSAGES_KEY, JSON.stringify(messages.value.slice(-40)))
  } catch { /* 隐私模式可能禁用 sessionStorage */ }
}

function restoreConversation() {
  try {
    sessionId.value = sessionStorage.getItem(SESSION_KEY) || ''
  } catch { sessionId.value = '' }
  if (!sessionId.value) {
    sessionId.value = generateSessionId()
    try { sessionStorage.setItem(SESSION_KEY, sessionId.value) } catch { /* ignore */ }
  }
  try {
    const raw = sessionStorage.getItem(MESSAGES_KEY)
    if (raw) {
      const items = JSON.parse(raw)
      if (Array.isArray(items) && items.length) {
        messages.value = items
          .filter((item) => item && (item.role === 'user' || item.role === 'assistant') && item.content)
          .slice(-40)
      }
    }
  } catch { /* ignore */ }
  if (!messages.value.length) {
    messages.value = [{ role: 'assistant', content: `我是${assistantName.value}，有什么问题请说。` }]
  }
}

function startNewSession() {
  const previous = sessionId.value
  // 先立即清空当前对话；服务端 reset 在后台执行，避免接口慢时按钮看起来没反应。
  stopSpeakingOnly()
  sessionId.value = generateSessionId()
  messages.value = [{ role: 'assistant', content: `我是${assistantName.value}，有什么问题请说。` }]
  input.value = ''
  persistConversation()
  scrollBottom(true)
  ElMessage.success('已开启新对话')
  if (previous) {
    aiApi.resetChat({ session_id: previous }).catch(() => { /* 服务端会话可能已过期 */ })
  }
  if (voiceActive.value) speak(`我是${assistantName.value}，已开启新的对话。`)
}

function resumeRecognition() {
  if (!voiceActive.value || speaking.value || sending.value) return
  if (restartTimer) window.clearTimeout(restartTimer)
  restartTimer = window.setTimeout(() => {
    if (!voiceActive.value || speaking.value || sending.value || recognitionRunning) return
    try { recognition?.start() } catch { recognitionRunning = false }
  }, 120)
}

function pickSpeechVoice() {
  const synth = window.speechSynthesis
  const allVoices = synth?.getVoices?.() || []
  const voices = allVoices.filter((voice) => /^zh/i.test(voice.lang || '') || /Chinese|中文/i.test(voice.name || ''))
  if (!voices.length) return null
  const preferred = String(aiStatus.value.voice_name || '').trim().toLowerCase()
  if (preferred) {
    const exact = voices.find((voice) => String(voice.name || '').toLowerCase() === preferred)
    if (exact) return exact
  }
  return voices.find((voice) => /^zh/i.test(voice.lang || '')) || voices[0]
}

function splitSpeechSegments(text) {
  const clean = String(text || '')
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/[|#*`>_]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  if (!clean) return []
  const parts = clean.match(/[^。！？!?；;]+[。！？!?；;]?/g) || [clean]
  return parts.map((item) => item.trim()).filter(Boolean).slice(0, 18)
}

function speechTone(segment, isLast) {
  const text = String(segment || '')
  const urgent = /严重|紧急|告警|离线|失败|异常|风险|故障|中断|错误/.test(text)
  const positive = /正常|完成|成功|恢复|建议|可以|请|已/.test(text)
  const question = /[？?]$/.test(text) || /吗|呢|是否/.test(text)
  let pitch = 1.0
  let rate = 0.94
  if (urgent) { pitch -= 0.07; rate = 0.9 }
  else if (positive) { pitch += 0.04; rate = 0.97 }
  if (question) pitch += 0.05
  if (isLast) rate = Math.min(1.02, rate + 0.02)
  return { pitch: Math.max(0.65, Math.min(1.35, pitch)), rate }
}

const BARGE_PHRASES = ['停止播报', '停止', '暂停', '停一下', '别说了', '打断']

function matchBargePhrase(text) {
  const normalized = normalizeEchoText(text)
  return BARGE_PHRASES.find((phrase) => normalized.includes(normalizeEchoText(phrase))) || ''
}

function normalizeEchoText(value) {
  return String(value || '').replace(/[\s，。！？,!?；;：:、]/g, '')
}

function isEchoText(candidate, spoken) {
  const text = normalizeEchoText(candidate)
  const source = normalizeEchoText(spoken)
  if (!text) return true
  if (BARGE_PHRASES.some((phrase) => text.includes(normalizeEchoText(phrase)))) return false
  if (text.length <= 2) return true
  if (source.includes(text)) return true
  let matched = 0
  for (let i = 0; i < text.length - 1; i += 1) {
    if (source.includes(text.slice(i, i + 2))) matched += 1
  }
  return matched / Math.max(1, text.length - 1) > 0.62
}

function stopSpeakingOnly() {
  speechGeneration += 1
  if (speechTimer) window.clearTimeout(speechTimer)
  speechTimer = null
  window.speechSynthesis?.cancel?.()
  if (ttsAudio) {
    try { ttsAudio.pause() } catch { /* ignore */ }
    ttsAudio = null
  }
  speaking.value = false
  currentSpeechText = ''
}

function interruptSpeech() {
  if (!speaking.value) return
  suppressVoiceUntil = 0
  stopSpeakingOnly()
  voiceBuffer = ''
  voiceTranscript.value = '请说，我在听…'
  if (!voiceActive.value) startVoice(false)
  else resumeRecognition()
}

function playTtsAudio(blob, contentForSpeech = '') {
  const generation = ++speechGeneration
  return new Promise((resolve) => {
    let finished = false
    let url = ''
    const done = () => {
      if (finished) return
      finished = true
      if (generation !== speechGeneration) { resolve(); return }
      if (speechTimer) window.clearTimeout(speechTimer)
      speechTimer = null
      ttsAudio = null
      if (url) URL.revokeObjectURL(url)
      speaking.value = false
      suppressVoiceUntil = Date.now() + 1400
      resumeRecognition()
      resolve()
    }
    try {
      url = URL.createObjectURL(blob)
      ttsAudio = new Audio(url)
      ttsAudio.onended = done
      ttsAudio.onerror = done
      speaking.value = true
      currentSpeechText = contentForSpeech
      speechTimer = window.setTimeout(done, 120000)
      try { recognition?.stop() } catch { /* ignore */ }
      ttsAudio.play().catch(done)
    } catch {
      done()
    }
  })
}

async function speak(text) {
  const content = String(text || '').trim().slice(0, 1600)
  if (!content) return
  if (aiStatus.value.tts_enabled) {
    try {
      const res = await aiApi.tts({ text: content })
      if (res.data && res.data.size) return playTtsAudio(res.data, content)
    } catch (error) {
      console.warn('TTS 模型不可用，回退浏览器语音', error)
    }
  }
  return speakBrowser(content)
}

function speakBrowser(text) {
  const content = String(text || '').trim().slice(0, 900)
  const generation = ++speechGeneration
  return new Promise((resolve) => {
    let finished = false
    let index = 0
    let pauseTimer = null
    const segments = splitSpeechSegments(content)
    const done = () => {
      if (finished) return
      if (generation !== speechGeneration) { resolve(); return }
      finished = true
      if (speechTimer) window.clearTimeout(speechTimer)
      if (pauseTimer) window.clearTimeout(pauseTimer)
      speechTimer = null
      pauseTimer = null
      speaking.value = false
      suppressVoiceUntil = Date.now() + 1400
      resumeRecognition()
      resolve()
    }
    if (!segments.length || !window.speechSynthesis) {
      speaking.value = false
      resumeRecognition()
      resolve()
      return
    }
    window.speechSynthesis.cancel()
    speaking.value = true
    currentSpeechText = content
    try { recognition?.stop() } catch { /* ignore */ }
    const next = () => {
      if (finished || generation !== speechGeneration) { if (!finished) done(); return }
      if (index >= segments.length) { done(); return }
      const segment = segments[index]
      const isLast = index === segments.length - 1
      index += 1
      const utterance = new SpeechSynthesisUtterance(segment)
      utterance.lang = 'zh-CN'
      const tone = speechTone(segment, isLast)
      utterance.pitch = tone.pitch
      utterance.rate = tone.rate
      utterance.volume = 0.96
      try {
        const selectedVoice = pickSpeechVoice()
        if (selectedVoice) utterance.voice = selectedVoice
      } catch { /* ignore */ }
      utterance.onend = () => {
        if (finished) return
        const pause = /[。！？!?；;]$/.test(segment) ? 220 : 90
        pauseTimer = window.setTimeout(next, pause)
      }
      utterance.onerror = () => {
        if (!finished) { index += 0; pauseTimer = window.setTimeout(next, 80) }
      }
      window.speechSynthesis.speak(utterance)
    }
    next()
    speechTimer = window.setTimeout(done, Math.min(60000, Math.max(8000, segments.join('').length * 180)))
  })
}

function stopGeneration() {
  askSequence += 1
  if (askAbortController) {
    askAbortController.abort()
    askAbortController = null
  }
  if (sending.value) {
    messages.value.push({ role: 'assistant', content: '已停止本轮生成。' })
    persistConversation()
  }
  sending.value = false
  stopSpeakingOnly()
  stickToBottom.value = true
  scrollBottom(true)
  if (voiceActive.value) resumeRecognition()
}

function functionTarget(step) {
  const tool = String(step?.tool || '')
  const data = step?.data || {}
  const deviceId = data?.id || data?.device?.id || data?.device_id
  const paths = {
    get_system_overview: '/bigscreen',
    search_devices: '/devices',
    get_active_alerts: '/alerts?view=active',
    get_device_detail: deviceId ? `/devices/${deviceId}?tab=alerts` : '/devices',
    get_mib_library: '/mibs',
    get_mib_objects: '/mibs',
    get_device_mib_status: deviceId ? `/devices/${deviceId}?tab=custom` : '/mibs',
    recommend_device_mib: deviceId ? `/devices/${deviceId}?tab=custom` : '/mibs',
    get_backup_status: '/config-backups',
    get_topology_status: '/topology',
    get_room_status: '/rooms',
    get_virtualization_status: '/virtualization',
    get_website_status: '/website',
    get_inspection_status: '/inspection',
    get_security_status: '/users',
    get_license_status: '/license',
    get_system_status: '/settings',
    web_search: '',
  }
  return paths[tool] || ''
}

function openFunction(step) {
  const path = functionTarget(step)
  if (!path) {
    ElMessage.info('该功能没有可跳转的页面')
    return
  }
  const target = router.resolve(path).href
  // 大屏通常由原管理页签 window.open 打开：优先回到原页签并定位对应功能。
  if (window.opener && !window.opener.closed) {
    try {
      window.opener.location.href = target
      window.opener.focus()
      ElMessage.success(`已回到原页签并打开：${step?.label || '对应功能'}`)
      return
    } catch { /* opener 跨窗口受限时回退新页签 */ }
  }
  const opened = window.open(target, '_blank', 'noopener,noreferrer')
  if (opened) {
    try { opened.opener = null } catch { /* ignore */ }
    ElMessage.success(`已在新页签打开：${step?.label || '对应功能'}`)
  } else {
    ElMessage.warning('浏览器阻止了新页签，请允许弹出窗口')
  }
}

async function ask(text = '', fromVoice = false) {
  const question = String(text || input.value || '').trim()
  if (!question || sending.value) return
  input.value = ''
  voiceTranscript.value = ''
  messages.value.push({ role: 'user', content: question })
  stickToBottom.value = true
  scrollBottom(true)
  sending.value = true
  const sequence = ++askSequence
  askAbortController = new AbortController()
  try {
    const res = await aiApi.agentChat({
      message: question,
      // 统一携带最近消息历史：语音轮次与文字轮次共享同一上下文。
      history: messages.value.slice(0, -1).slice(-12),
      session_id: sessionId.value,
      channel: fromVoice ? 'voice' : 'text',
    }, { signal: askAbortController.signal })
    if (sequence !== askSequence) return
    const data = res.data || {}
    if (data.session_id) sessionId.value = data.session_id
    const reply = data.reply || '暂无分析结果'
    messages.value.push({
      role: 'assistant', content: reply,
      steps: data.steps || [], cards: data.cards || [],
      actions: data.actions || [], suggestions: data.suggestions || [],
    })
    persistConversation()
    stickToBottom.value = true
    scrollBottom(true)
    if (voiceActive.value) await speak(reply)
  } catch (e) {
    if (sequence !== askSequence || e?.code === 'ERR_CANCELED' || e?.name === 'CanceledError') return
    messages.value.push({ role: 'assistant', content: e.message || 'AI 分析失败' })
    persistConversation()
    stickToBottom.value = true
    scrollBottom(true)
    if (voiceActive.value) await speak('分析失败，请稍后再试')
  } finally {
    if (sequence === askSequence) {
      askAbortController = null
      sending.value = false
      stickToBottom.value = true
      scrollBottom(true)
      if (voiceActive.value) resumeRecognition()
    }
  }
}

function normalizeVoiceText(value) {
  return String(value || '')
    .replace(/\s+/g, '')
    .replace(/([，。！？,!?])\1+/g, '$1')
    .trim()
}

function bestAlternative(result) {
  let best = result?.[0] || null
  for (let i = 1; i < (result?.length || 0); i += 1) {
    if (Number(result[i].confidence || 0) > Number(best?.confidence || 0)) best = result[i]
  }
  return best
}

function appendVoiceFinal(text) {
  const cleaned = normalizeVoiceText(text)
  if (!cleaned || cleaned.length < 2) return
  if (voiceBuffer.endsWith(cleaned)) return
  const separator = voiceBuffer && !/[，。！？,!?；;]$/.test(voiceBuffer) ? '，' : ''
  voiceBuffer = `${voiceBuffer}${separator}${cleaned}`.slice(-1200)
}

function scheduleVoiceCommit(delay = 2300) {
  if (voiceSilenceTimer) window.clearTimeout(voiceSilenceTimer)
  voiceSilenceTimer = window.setTimeout(() => {
    const question = normalizeVoiceText(voiceBuffer || voiceTranscript.value || '')
    voiceBuffer = ''
    voiceTranscript.value = question
    voiceSilenceTimer = null
    if (question.length >= 2 && !speaking.value && !sending.value) handleVoiceText(question)
  }, delay)
}

function getRecognition() {
  const Ctor = window.SpeechRecognition || window.webkitSpeechRecognition
  if (!Ctor) return null
  const engine = new Ctor()
  engine.lang = 'zh-CN'
  engine.continuous = true
  engine.interimResults = true
  engine.maxAlternatives = 3
  engine.onstart = () => { recognitionRunning = true }
  engine.onresult = (event) => {
    if (sending.value) return
    let finalText = ''
    let interim = ''
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const result = event.results[i]
      const alternative = bestAlternative(result)
      if (!alternative) continue
      const text = String(alternative.transcript || '')
      if (result.isFinal) finalText += text
      else interim += text
    }
    const heard = `${finalText}${interim}`.trim()
    if (speaking.value) {
      // 播报期间麦克风识别已停止；若浏览器仍回传缓存结果，全部丢弃。
      return
    }
    if (Date.now() < suppressVoiceUntil) return
    if (interim) voiceTranscript.value = `${voiceBuffer}${interim}`.trim()
    if (finalText) {
      appendVoiceFinal(finalText)
      voiceTranscript.value = voiceBuffer
    }
    if (interim || finalText) scheduleVoiceCommit()
  }
  engine.onerror = (event) => {
    recognitionRunning = false
    if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
      ElMessage.warning('浏览器未允许麦克风权限，连续语音已停止')
      stopVoice()
      return
    }
    // no-speech / aborted 是浏览器长连接正常回收，静默重连，不打断连续对话。
    if (!['no-speech', 'aborted', 'audio-capture'].includes(event.error)) {
      if (!voiceErrorShown) {
        voiceErrorShown = true
        ElMessage.warning(`语音识别暂时不可用：${event.error || 'network'}，将自动重连`)
      }
      window.setTimeout(() => { voiceErrorShown = false }, 8000)
    }
    if (voiceActive.value && !speaking.value && !sending.value) resumeRecognition()
  }
  engine.onend = () => {
    recognitionRunning = false
    if (voiceActive.value && !speaking.value && !sending.value) resumeRecognition()
  }
  return engine
}

function handleVoiceText(text) {
  const query = normalizeVoiceText(text)
  if (query.length < 2) return
  if (!voiceActive.value) return
  ask(query, true)
}

function startVoice(auto = false) {
  if (voiceActive.value) return
  recognition = getRecognition()
  if (!recognition) {
    if (!auto) ElMessage.warning('当前浏览器不支持语音识别，请使用 Chrome/Edge，或直接文字输入')
    return
  }
  if (!window.speechSynthesis && !auto) {
    ElMessage.warning('当前浏览器不支持语音合成，仍可连续语音提问，但不会朗读回答')
  }
  voiceActive.value = true
  voiceBuffer = ''
  voiceErrorShown = false
  suppressVoiceUntil = 0
  try {
    recognition.start()
  } catch {
    recognitionRunning = false
    voiceActive.value = false
    if (auto) ElMessage.warning('浏览器限制了自动麦克风，请点击“启动连续语音”授权')
  }
  if (voiceActive.value) {
    if (!auto) ElMessage.success('连续语音已开启，停顿约 2.3 秒自动发送')
    speak(welcomeGreeting())
  }
}

function toggleVoice() {
  if (voiceActive.value) {
    stopVoice()
    return
  }
  startVoice(false)
}

function stopVoice() {
  speechGeneration += 1
  voiceActive.value = false
  if (restartTimer) window.clearTimeout(restartTimer)
  restartTimer = null
  if (speechTimer) window.clearTimeout(speechTimer)
  speechTimer = null
  if (voiceSilenceTimer) window.clearTimeout(voiceSilenceTimer)
  voiceSilenceTimer = null
  voiceBuffer = ''
  window.speechSynthesis?.cancel?.()
  if (ttsAudio) {
    try { ttsAudio.pause() } catch { /* ignore */ }
    ttsAudio = null
  }
  speaking.value = false
  try { recognition?.stop() } catch { /* ignore */ }
  recognitionRunning = false
  recognition = null
}

watch(() => messages.value.length, () => {
  stickToBottom.value = true
  scrollBottom(true)
}, { flush: 'post' })

watch(sending, (value) => {
  if (value) { stickToBottom.value = true; scrollBottom(true) }
})

function initGateway3D() {
  const host = gateway3dEl.value
  const canvas = gatewayCanvasRef.value
  if (!host || !canvas) return
  const width = Math.max(320, host.clientWidth)
  const height = Math.max(260, host.clientHeight)
  gwRenderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true })
  gwRenderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  gwRenderer.setSize(width, height, false)
  gwScene = new THREE.Scene()
  gwCamera = new THREE.PerspectiveCamera(42, width / height, 0.1, 100)
  gwCamera.position.set(0, 3.6, 8.2)
  gwCamera.lookAt(0, 0.2, 0)
  gwGroup = new THREE.Group()
  gwScene.add(gwGroup)

  gwScene.add(new THREE.AmbientLight(0x63e6da, 1.2))
  const point = new THREE.PointLight(0x46e8df, 3.2, 20)
  point.position.set(0, 4, 3)
  gwScene.add(point)
  const warning = (overview.value?.alerts?.by_level?.critical || 0) + (overview.value?.alerts?.by_level?.emergency || 0) > 0
  const coreColor = warning ? 0xff9a5a : 0x65fff0

  const core = new THREE.Mesh(
    new THREE.IcosahedronGeometry(1.3, 1),
    new THREE.MeshBasicMaterial({ color: coreColor, wireframe: true, transparent: true, opacity: 0.9 }),
  )
  gwGroup.add(core)
  const inner = new THREE.Mesh(
    new THREE.IcosahedronGeometry(0.72, 1),
    new THREE.MeshBasicMaterial({ color: coreColor, transparent: true, opacity: 0.22 }),
  )
  gwGroup.add(inner)
  const ringA = new THREE.Mesh(
    new THREE.TorusGeometry(2.05, 0.018, 8, 96),
    new THREE.MeshBasicMaterial({ color: 0x52e9df, transparent: true, opacity: 0.62 }),
  )
  ringA.rotation.x = Math.PI / 2.5
  gwGroup.add(ringA)
  const ringB = new THREE.Mesh(
    new THREE.TorusGeometry(2.7, 0.012, 8, 96),
    new THREE.MeshBasicMaterial({ color: 0x4c9dff, transparent: true, opacity: 0.42 }),
  )
  ringB.rotation.x = Math.PI / 2
  ringB.rotation.z = 0.5
  gwGroup.add(ringB)
  const ringC = new THREE.Mesh(
    new THREE.TorusGeometry(3.35, 0.01, 8, 96),
    new THREE.MeshBasicMaterial({ color: 0x9ef9e9, transparent: true, opacity: 0.22 }),
  )
  ringC.rotation.x = Math.PI / 2.2
  gwGroup.add(ringC)

  const positions = [
    [3.45, 0.4, 0], [1.75, 0.25, 2.95], [-1.75, 0.15, 2.95],
    [-3.45, 0.35, 0], [-1.75, -0.3, -2.95], [1.75, -0.25, -2.95],
  ]
  positions.forEach(([x, y, z], index) => {
    const node = new THREE.Mesh(
      new THREE.OctahedronGeometry(0.18, 0),
      new THREE.MeshBasicMaterial({ color: index === 1 && warning ? 0xff9a5a : 0x7dfff1, transparent: true, opacity: 0.95 }),
    )
    node.position.set(x, y, z)
    gwGroup.add(node)
    const line = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0, 0, 0), new THREE.Vector3(x, y, z)]),
      new THREE.LineBasicMaterial({ color: 0x3bd9cd, transparent: true, opacity: 0.28 }),
    )
    gwGroup.add(line)
    for (let p = 0; p < 2; p += 1) {
      const particle = new THREE.Mesh(
        new THREE.SphereGeometry(0.035, 8, 8),
        new THREE.MeshBasicMaterial({ color: p ? 0xffc46b : 0x7dfff1 }),
      )
      gwGroup.add(particle)
      gwParticles.push({ mesh: particle, target: new THREE.Vector3(x, y, z), offset: (index * 0.17 + p * 0.5) % 1, speed: 0.0012 + index * 0.00008 })
    }
  })

  const grid = new THREE.GridHelper(14, 28, 0x197d7d, 0x10424f)
  grid.position.y = -2.25
  grid.material.transparent = true
  grid.material.opacity = 0.3
  gwScene.add(grid)

  const render = () => {
    if (!gwRenderer || !gwScene || !gwCamera) return
    const time = performance.now()
    gwGroup.rotation.y += 0.0014
    ringA.rotation.z += 0.002
    ringB.rotation.z -= 0.0015
    ringC.rotation.z += 0.001
    core.rotation.x += 0.001
    core.rotation.y += 0.0018
    inner.rotation.y -= 0.0012
    for (const item of gwParticles) {
      const t = ((time * item.speed + item.offset) % 1)
      item.mesh.position.copy(item.target).multiplyScalar(t)
      item.mesh.position.y += Math.sin(t * Math.PI) * 0.24
    }
    gwCamera.position.x = Math.sin(time * 0.00018) * 0.34
    gwCamera.lookAt(0, 0.2, 0)
    gwRenderer.render(gwScene, gwCamera)
    gwAnimation = requestAnimationFrame(render)
  }
  render()
  gwResizeObserver = new ResizeObserver(() => {
    if (!gwRenderer || !gwCamera || !host) return
    const w = Math.max(320, host.clientWidth)
    const h = Math.max(260, host.clientHeight)
    gwRenderer.setSize(w, h, false)
    gwCamera.aspect = w / h
    gwCamera.updateProjectionMatrix()
  })
  gwResizeObserver.observe(host)
}

function startPanelAutoScroll() {
  if (panelAutoTimer) window.clearInterval(panelAutoTimer)
  panelAutoTimer = window.setInterval(() => {
    const targets = [
      [assetScrollEl.value, 'asset'],
      [insightScrollEl.value, 'insight'],
    ]
    for (const [el, key] of targets) {
      if (!el || Date.now() < panelPausedUntil[key]) continue
      const max = el.scrollHeight - el.clientHeight
      if (max <= 2) { el.scrollTop = 0; continue }
      if (el.scrollTop >= max - 1) {
        panelPausedUntil[key] = Date.now() + 1800
        window.setTimeout(() => {
          if (key === 'asset' && assetScrollEl.value) assetScrollEl.value.scrollTop = 0
          if (key === 'insight' && insightScrollEl.value) insightScrollEl.value.scrollTop = 0
          panelPausedUntil[key] = 0
        }, 1800)
      } else {
        el.scrollTop = Math.min(max, el.scrollTop + 0.45)
      }
    }
  }, 80)
}

function startAlertAutoScroll() {
  if (alertAutoTimer) window.clearInterval(alertAutoTimer)
  if (panelAutoTimer) window.clearInterval(panelAutoTimer)
  alertAutoTimer = window.setInterval(() => {
    const el = alertScrollEl.value
    if (!el || Date.now() < alertPausedUntil) return
    const max = el.scrollHeight - el.clientHeight
    if (max <= 2) { el.scrollTop = 0; return }
    if (el.scrollTop >= max - 1) {
      alertPausedUntil = Date.now() + 1800
      window.setTimeout(() => {
        if (alertScrollEl.value) alertScrollEl.value.scrollTop = 0
        alertPausedUntil = 0
      }, 1800)
      return
    }
    el.scrollTop = Math.min(max, el.scrollTop + 0.6)
  }, 80)
}

onMounted(async () => {
  restoreConversation()
  rotatePositive()
  positiveTimer = window.setInterval(rotatePositive, 12000)
  // 进入 AI 大屏即尝试自动接管麦克风；浏览器权限未放行时保留手动启动按钮。
  window.setTimeout(() => { if (!voiceActive.value) startVoice(true) }, 300)
  await load()
  initGateway3D()
  startAlertAutoScroll()
  startPanelAutoScroll()
  scrollBottom()
  refreshTimer = window.setInterval(load, 15000)
  clockTimer = window.setInterval(() => { now.value = new Date() }, 1000)
})

onBeforeUnmount(() => {
  if (refreshTimer) window.clearInterval(refreshTimer)
  if (clockTimer) window.clearInterval(clockTimer)
  if (positiveTimer) window.clearInterval(positiveTimer)
  if (alertAutoTimer) window.clearInterval(alertAutoTimer)
  if (gwAnimation) cancelAnimationFrame(gwAnimation)
  gwResizeObserver?.disconnect()
  gwScene?.traverse((object) => {
    object.geometry?.dispose?.()
    if (Array.isArray(object.material)) object.material.forEach((material) => material.dispose?.())
    else object.material?.dispose?.()
  })
  gwRenderer?.dispose?.()
  stopVoice()
  window.speechSynthesis?.cancel()
})
</script>

<style scoped>
.gw-screen { --gw-head: 70px; --gw-bottom: clamp(110px, 13vh, 150px); position: relative; width: 100vw; height: 100vh; height: 100dvh; min-height: 620px; overflow: hidden; background: radial-gradient(circle at 50% 38%, #0a2b3b 0, #061623 45%, #020a12 100%); color: #d8f5f2; }
.gw-screen * { box-sizing: border-box; }
.gw-grid-bg { pointer-events: none; position: absolute; inset: 0; opacity: .55; background-image: linear-gradient(rgba(55, 189, 184, .035) 1px, transparent 1px), linear-gradient(90deg, rgba(55, 189, 184, .035) 1px, transparent 1px); background-size: 42px 42px; mask-image: linear-gradient(to bottom, black, transparent 92%); }
.gw-head { position: relative; z-index: 4; height: var(--gw-head); display: flex; align-items: center; justify-content: space-between; padding: 12px 26px; border-bottom: 1px solid rgba(65, 207, 199, .18); background: linear-gradient(90deg, rgba(3, 24, 35, .95), rgba(4, 31, 42, .68), rgba(3, 24, 35, .95)); backdrop-filter: blur(10px); }
.gw-brand { display: flex; align-items: center; gap: 11px; }
.gw-mark { width: 38px; height: 38px; display: grid; place-items: center; border: 1px solid #4ce3d5; border-radius: 9px; background: linear-gradient(135deg, rgba(42, 205, 190, .2), rgba(8, 42, 60, .6)); box-shadow: 0 0 20px rgba(58, 230, 213, .24); }
.gw-mark span { color: #a1fff3; font-family: Consolas, monospace; font-size: 16px; font-weight: 700; letter-spacing: .06em; }
.gw-brand b { display: block; color: #e8fffc; font-size: 20px; letter-spacing: .08em; }
.gw-brand small { color: #6fb0b6; font-size: 9px; letter-spacing: .22em; }
.gw-head-center { display: flex; align-items: center; gap: 18px; color: #83c8cc; font-size: 11px; }
.gw-live { display: flex; align-items: center; gap: 6px; color: #7ff4e7; letter-spacing: .1em; }
.gw-live i { width: 6px; height: 6px; border-radius: 50%; background: #37e9c4; box-shadow: 0 0 10px #37e9c4; animation: gw-pulse 1.5s infinite; }
@keyframes gw-pulse { 50% { opacity: .35; } }
.gw-date { color: #8fd3d6; font-family: Consolas, monospace; font-size: 21px; font-weight: 500; letter-spacing: .04em; }
.gw-clock { color: #e5fffb; font-family: Consolas, monospace; font-size: 21px; font-weight: 700; letter-spacing: .08em; }
.gw-head-actions { display: flex; align-items: center; gap: 8px; }
.gw-status { display: flex; align-items: center; gap: 5px; margin-right: 5px; color: #e6b56c; font-family: Consolas, monospace; font-size: 10px; }
.gw-status i { width: 5px; height: 5px; border-radius: 50%; background: #e6b56c; }
.gw-status.ok { color: #62e6c9; }
.gw-status.ok i { background: #3ee5bd; box-shadow: 0 0 8px #3ee5bd; }
.gw-head-actions :deep(.el-button) { color: #b9eeee; border-color: rgba(70, 198, 193, .25); background: rgba(7, 44, 56, .52); }
.gw-body { position: relative; z-index: 3; height: calc(100dvh - var(--gw-head) - var(--gw-bottom)); min-height: 0; display: grid; grid-template-columns: 275px minmax(460px, 1fr) 390px; gap: 15px; padding: 14px 24px 0; }
.gw-rail { min-height: 0; display: flex; flex-direction: column; gap: 10px; overflow: hidden; }
.gw-rail::-webkit-scrollbar { display: none; }
.gw-panel { flex: 0 0 auto; display: flex; flex-direction: column; min-height: 0; overflow: hidden; padding: 14px 15px; border: 1px solid rgba(68, 193, 190, .2); border-radius: 8px; background: linear-gradient(145deg, rgba(7, 42, 56, .78), rgba(3, 23, 35, .72)); box-shadow: inset 0 0 28px rgba(20, 152, 150, .045); }
.gw-panel-grow { flex: 1 1 auto; min-height: 0; }
.gw-scroll { flex: 1 1 auto; min-height: 0; height: auto; }
.gw-scroll-native { flex: 1 1 auto; min-height: 0; overflow-y: auto; padding-right: 5px; scrollbar-width: thin; scrollbar-color: rgba(82, 216, 204, .4) transparent; }
.gw-scroll-native::-webkit-scrollbar { width: 5px; }
.gw-scroll-native::-webkit-scrollbar-thumb { border-radius: 3px; background: rgba(82, 216, 204, .4); }
.gw-scroll-native::-webkit-scrollbar-track { background: transparent; }
.gw-scroll-body { padding-right: 3px; }
.gw-panel :deep(.gw-scroll) { scrollbar-width: thin !important; scrollbar-color: rgba(82, 216, 204, .4) transparent; }
.gw-panel :deep(.gw-scroll::-webkit-scrollbar) { display: block !important; width: 4px !important; height: 4px !important; }
.gw-panel :deep(.gw-scroll::-webkit-scrollbar-thumb) { border-radius: 2px; background: rgba(82, 216, 204, .4); }
.gw-panel :deep(.gw-scroll::-webkit-scrollbar-track) { background: transparent; }
.gw-positive-banner { position: absolute; left: 50%; top: 10px; z-index: 4; max-width: 86%; transform: translateX(-50%); color: #ffe0a3; font-size: clamp(18px, 1.45vw, 27px); font-weight: 600; letter-spacing: .08em; text-align: center; text-shadow: 0 0 12px rgba(255, 192, 96, .45), 0 0 28px rgba(255, 173, 64, .18); white-space: nowrap; animation: gw-positive-in .7s ease; pointer-events: none; }
@keyframes gw-positive-in { from { opacity: 0; transform: translate(-50%, 6px); } to { opacity: 1; transform: translate(-50%, 0); } }
.gw-panel-head { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin-bottom: 9px; }
.gw-panel-head span { color: #5dacb3; font-family: Consolas, monospace; font-size: 9px; letter-spacing: .14em; }
.gw-panel-head b { color: #bdf4ef; font-size: 14px; font-weight: 500; }
.gw-health-panel { text-align: center; }
.gw-health-panel .gw-scroll { text-align: center; }
.gw-health-panel .gw-panel-head { text-align: left; }
.gw-health-ring { width: 132px; height: 132px; margin: 3px auto 7px; display: grid; place-items: center; border-radius: 50%; background: conic-gradient(#4be7cf var(--health), rgba(37, 106, 113, .22) 0); position: relative; }
.gw-health-ring::after { content: ''; position: absolute; inset: 8px; border-radius: 50%; background: #062333; box-shadow: inset 0 0 22px rgba(50, 220, 203, .12); }
.gw-health-ring > div { position: relative; z-index: 1; }
.gw-health-ring strong { display: block; color: #b6fff4; font-family: Consolas, monospace; font-size: 35px; line-height: 1; }
.gw-health-ring small { color: #71b8ba; font-family: Consolas, monospace; font-size: 9px; letter-spacing: .12em; }
.gw-health-meta { display: flex; justify-content: space-between; color: #7cb9bc; font-size: 10px; }
.gw-health-meta i { display: inline-block; width: 4px; height: 4px; margin-right: 3px; border-radius: 50%; }
.gw-health-meta i.ok { background: #38e2bf; box-shadow: 0 0 6px #38e2bf; }
.gw-access-list { display: grid; grid-template-columns: 1fr 1fr; gap: 5px; }
.gw-access-list > div { padding: 6px 7px; border: 1px solid rgba(65, 161, 168, .13); border-radius: 4px; background: rgba(3, 28, 41, .5); }
.gw-access-list span { display: block; color: #83b9bd; font-size: 10px; }
.gw-access-list b { display: inline-block; margin-top: 2px; color: #adfff3; font-family: Consolas, monospace; font-size: 22px; }
.gw-access-list small { margin-left: 4px; color: #5d909a; font-family: Consolas, monospace; font-size: 7px; }
.gw-bar-list { display: flex; flex-direction: column; gap: 7px; }
.gw-bar-list > div { display: grid; grid-template-columns: 48px 1fr 25px; align-items: center; gap: 5px; }
.gw-bar-list em { overflow: hidden; color: #95c9cb; font-size: 10px; font-style: normal; text-overflow: ellipsis; white-space: nowrap; }
.gw-bar-list i, .gw-link-list i { display: block; height: 3px; overflow: hidden; border-radius: 2px; background: rgba(46, 133, 138, .25); }
.gw-bar-list i b, .gw-link-list i b { display: block; height: 100%; border-radius: 2px; background: linear-gradient(90deg, #28c9bd, #8affdf); box-shadow: 0 0 7px rgba(82, 238, 215, .35); }
.gw-bar-list strong { color: #b6fff4; font-family: Consolas, monospace; font-size: 10px; text-align: right; }
.gw-muted { color: #6c979e; font-size: 10px; }
.gw-stage { min-width: 0; min-height: 0; display: grid; grid-template-rows: 48px minmax(220px, 1fr) 66px 72px; gap: 5px; }
.gw-stage-title { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 0 4px; }
.gw-stage-title span { color: #58aab0; font-family: Consolas, monospace; font-size: 9px; letter-spacing: .16em; }
.gw-stage-title h1 { margin: 2px 0 0; color: #e1fffb; font-size: 20px; font-weight: 500; letter-spacing: .08em; }
.gw-stage-tags { display: flex; gap: 5px; }
.gw-stage-tags span { padding: 3px 8px; border: 1px solid rgba(59, 197, 190, .22); border-radius: 3px; color: #75c9c8; font-family: Consolas, monospace; font-size: 8px; }
.gw-scene-wrap { position: relative; min-height: 0; overflow: hidden; border: 1px solid rgba(61, 188, 185, .16); border-radius: 10px; background: radial-gradient(circle at 50% 50%, rgba(16, 81, 91, .33), rgba(2, 15, 25, .08) 68%); }
.gw-canvas { position: absolute; inset: 0; width: 100%; height: 100%; }
.gw-scan { pointer-events: none; position: absolute; inset: 0; background: repeating-linear-gradient(0deg, transparent 0, transparent 3px, rgba(88, 240, 224, .025) 4px); }
.gw-core-label { position: absolute; left: 50%; top: 50%; width: 96px; margin: -28px 0 0 -48px; display: flex; flex-direction: column; align-items: center; padding: 4px 0; border: 1px solid rgba(88, 239, 222, .35); border-radius: 4px; background: rgba(2, 24, 35, .7); box-shadow: 0 0 18px rgba(53, 220, 205, .14); pointer-events: none; }
.gw-core-label span { color: #8ae4dd; font-family: Consolas, monospace; font-size: 9px; letter-spacing: .12em; }
.gw-core-label b { color: #b6fff4; font-family: Consolas, monospace; font-size: 11px; }
.gw-core-label.alert { border-color: rgba(255, 156, 93, .45); }
.gw-core-label.alert b { color: #ffb178; }
.gw-node-label { position: absolute; display: flex; align-items: baseline; gap: 4px; padding: 2px 5px; border-left: 1px solid rgba(82, 217, 207, .4); background: rgba(2, 20, 32, .42); pointer-events: none; }
.gw-node-label span { color: #80c2c5; font-size: 9px; }
.gw-node-label b { color: #c8fff8; font-family: Consolas, monospace; font-size: 14px; }
.gw-node-label.n1 { left: 8%; top: 16%; }
.gw-node-label.n2 { right: 8%; top: 12%; }
.gw-node-label.n3 { right: 7%; bottom: 22%; }
.gw-node-label.n4 { left: 10%; bottom: 18%; }
.gw-node-label.n5 { left: 2%; top: 46%; }
.gw-node-label.n6 { right: 2%; top: 47%; }
.gw-scene-caption { position: absolute; left: 10px; right: 10px; bottom: 8px; display: flex; gap: 12px; color: #609ca2; font-family: Consolas, monospace; font-size: 8px; }
.gw-scene-caption span:first-child { color: #5be6cf; }
.gw-telemetry { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 6px; }
.gw-telemetry > div { padding: 7px 9px; border: 1px solid rgba(61, 171, 173, .17); border-radius: 5px; background: rgba(4, 29, 42, .62); }
.gw-telemetry span { display: block; color: #5ca5ab; font-family: Consolas, monospace; font-size: 8px; letter-spacing: .08em; }
.gw-telemetry b { display: block; margin-top: 1px; color: #b4fff4; font-family: Consolas, monospace; font-size: 23px; line-height: 1.1; }
.gw-telemetry small { color: #6ca2a7; font-size: 10px; }
.gw-voice-console { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 8px 11px; border: 1px solid rgba(63, 202, 194, .22); border-radius: 8px; background: linear-gradient(90deg, rgba(5, 40, 50, .8), rgba(4, 27, 42, .7)); }
.gw-voice-left { display: flex; align-items: center; gap: 11px; min-width: 0; }
.gw-barge-btn { flex: 0 0 auto; height: 60px; padding: 0 10px; border: 1px solid rgba(255, 153, 90, .5); border-radius: 7px; background: rgba(114, 49, 20, .55); color: #ffc28e; font-size: 11px; cursor: pointer; }
.gw-barge-btn:hover { background: rgba(156, 67, 26, .75); color: #fff; }
.gw-voice-trigger { flex: 0 0 auto; width: 108px; height: 60px; display: flex; flex-direction: column; align-items: center; justify-content: center; border: 1px solid rgba(67, 219, 203, .3); border-radius: 7px; background: rgba(7, 51, 61, .8); color: #a6fff1; cursor: pointer; }
.gw-voice-trigger.active { border-color: #48e7c5; box-shadow: 0 0 16px rgba(57, 228, 195, .18); background: rgba(7, 72, 63, .7); }
.gw-voice-trigger b { margin-top: 3px; font-size: 11px; font-weight: 500; }
.gw-voice-trigger small { color: #6fa6ac; font-family: Consolas, monospace; font-size: 7px; letter-spacing: .08em; }
.gw-mic { display: flex; align-items: center; gap: 2px; height: 15px; }
.gw-mic i { width: 2px; height: 7px; border-radius: 2px; background: #63efd9; animation: gw-wave 1s infinite alternate; }
.gw-mic i:nth-child(2) { height: 13px; animation-delay: .12s; }
.gw-mic i:nth-child(3) { height: 9px; animation-delay: .24s; }
.gw-mic i:nth-child(4) { height: 15px; animation-delay: .36s; }
@keyframes gw-wave { to { transform: scaleY(.35); opacity: .5; } }
.gw-voice-copy { min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.gw-voice-copy span { color: #b0f7ef; font-size: 11px; }
.gw-voice-copy small { overflow: hidden; color: #78afb3; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.gw-voice-wave { flex: 0 0 auto; height: 30px; display: flex; align-items: center; gap: 2px; opacity: .55; }
.gw-voice-wave i { width: 2px; border-radius: 2px; background: #43cfc6; animation: gw-wave 1.1s ease-in-out infinite alternate; }
.gw-right .gw-insight-panel { flex: 0 0 150px; min-height: 0; }
.gw-chat-rail { flex: 1 1 auto; min-height: 0; }
.gw-insight-summary { margin: 0 0 7px; color: #c7e5e3; font-size: 11px; line-height: 1.55; }
.gw-insight-list { display: flex; flex-direction: column; gap: 5px; max-height: 145px; overflow: auto; }
.gw-insight-list > div { padding-left: 6px; border-left: 1px solid rgba(239, 140, 72, .42); }
.gw-insight-list b { display: block; color: #ffc99e; font-size: 10px; }
.gw-insight-list span { display: block; color: #87b5b7; font-size: 10px; line-height: 1.45; }
.gw-level-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 5px; }
.gw-level-grid > div { padding: 5px 7px; border: 1px solid rgba(80, 187, 185, .15); border-radius: 4px; background: rgba(3, 25, 37, .5); }
.gw-level-grid span { display: block; color: #8cb9bd; font-size: 10px; }
.gw-level-grid b { color: #effffc; font-family: Consolas, monospace; font-size: 22px; }
.gw-level-grid .critical b, .gw-level-grid .emergency b { color: #ff948f; }
.gw-level-grid .warning b { color: #f6c66c; }
.gw-level-empty { padding: 10px 0; color: #649ba0; font-family: Consolas, monospace; font-size: 10px; text-align: center; }
.gw-link-list { display: flex; flex-direction: column; gap: 10px; }
.gw-link-list > div { display: grid; grid-template-columns: 1fr auto; gap: 4px 8px; }
.gw-link-list span { color: #87bdc0; font-size: 10px; }
.gw-link-list b { color: #bcfff5; font-family: Consolas, monospace; font-size: 11px; }
.gw-link-list i { grid-column: 1 / -1; }
.gw-bottom { position: relative; z-index: 3; height: var(--gw-bottom); min-height: 0; overflow: hidden; display: grid; grid-template-columns: 1fr; gap: 0; padding: 6px 24px 12px; }
.gw-chat, .gw-alertdeck { min-width: 0; min-height: 0; overflow: hidden; display: flex; flex-direction: column; padding: 11px 13px; border: 1px solid rgba(62, 188, 185, .2); border-radius: 9px; background: linear-gradient(150deg, rgba(5, 35, 48, .82), rgba(3, 20, 32, .72)); }
.gw-chat-head { flex: 0 0 auto; display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; margin-bottom: 7px; }
.gw-chat-head span { display: block; color: #60a8ae; font-family: Consolas, monospace; font-size: 8px; letter-spacing: .12em; }
.gw-chat-head b { display: block; margin-top: 1px; color: #c8fff8; font-size: 14px; font-weight: 500; }
.gw-chat-head small { color: #72aab0; font-size: 10px; }
.gw-chat-head > div:last-child { display: flex; align-items: center; gap: 5px; }
.gw-model-hint { flex: 0 0 auto; margin: 0 0 5px; color: #dab57e; font-size: 10px; }
.gw-messages { flex: 1 1 auto; min-height: 0; max-height: 100%; overflow-y: auto; display: flex; flex-direction: column; gap: 6px; padding-right: 7px; scroll-behavior: smooth; scrollbar-width: thin; scrollbar-color: rgba(86, 220, 207, .45) rgba(4, 31, 43, .6); }
.gw-messages::-webkit-scrollbar { width: 6px; }
.gw-messages::-webkit-scrollbar-thumb { border-radius: 3px; background: rgba(86, 220, 207, .45); }
.gw-messages::-webkit-scrollbar-track { background: rgba(4, 31, 43, .6); }
.gw-message { display: flex; align-items: flex-start; gap: 6px; }
.gw-message.user { flex-direction: row-reverse; }
.gw-avatar { flex: 0 0 27px; width: 27px; height: 27px; display: grid; place-items: center; border: 1px solid rgba(69, 220, 205, .24); border-radius: 5px; background: rgba(7, 62, 66, .8); color: #8ff8e9; font-family: Consolas, monospace; font-size: 8px; }
.gw-message.user .gw-avatar { border-color: rgba(91, 165, 255, .3); background: rgba(29, 70, 132, .5); color: #b9d9ff; }
.gw-message-main { min-width: 0; max-width: 90%; }
.gw-message p { margin: 0; padding: 7px 10px; border-radius: 5px; background: rgba(8, 54, 64, .72); color: #c5e7e5; font-size: 12px; line-height: 1.65; white-space: pre-wrap; overflow-wrap: anywhere; }
.gw-message.user .gw-message-main { display: flex; flex-direction: column; align-items: flex-end; }
.gw-message.user p { background: rgba(30, 73, 134, .42); color: #d8eaff; }
.gw-steps { display: flex; flex-wrap: wrap; gap: 3px; margin-top: 3px; }
.gw-steps span { padding: 2px 6px; border-radius: 3px; background: rgba(21, 184, 146, .12); color: #84ebcf; font-size: 9px; }
.gw-steps span.failed { background: rgba(239, 68, 68, .12); color: #f8a2a2; }
.gw-function-links { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; margin-top: 5px; }
.gw-function-links > span { color: #5f9ba1; font-size: 9px; }
.gw-function-links button { padding: 2px 7px; border: 1px solid rgba(64, 199, 191, .25); border-radius: 9px; background: rgba(10, 70, 77, .35); color: #9be8df; font-size: 9px; cursor: pointer; }
.gw-function-links button:hover { border-color: #59e4d2; color: #fff; background: rgba(16, 100, 103, .55); }
.gw-function-links button.failed { opacity: .55; }
.gw-input { flex: 0 0 auto; display: flex; gap: 7px; margin-top: 7px; }
.gw-input :deep(.el-input__wrapper) { background: rgba(2, 23, 34, .8); box-shadow: 0 0 0 1px rgba(65, 190, 188, .22) inset; }
.gw-input :deep(.el-input__inner) { color: #d5f5f3; font-size: 12px; }
.gw-alert-scroll { flex: 1 1 auto; min-height: 0; height: auto; max-height: 100%; overflow-y: auto; display: flex; flex-direction: column; gap: 4px; padding-right: 5px; scrollbar-width: thin; scrollbar-color: rgba(82, 216, 204, .4) transparent; }
.gw-alert-scroll::-webkit-scrollbar { width: 5px; }
.gw-alert-scroll::-webkit-scrollbar-thumb { border-radius: 3px; background: rgba(82, 216, 204, .4); }
.gw-alert-scroll::-webkit-scrollbar-track { background: transparent; }
.gw-alert-item { display: flex; align-items: flex-start; gap: 6px; padding: 5px 6px; border-left: 2px solid #eab35a; border-radius: 3px; background: rgba(238, 169, 58, .055); }
.gw-alert-item.critical, .gw-alert-item.emergency { border-left-color: #ef7676; background: rgba(239, 103, 103, .07); }
.gw-alert-item > span { flex: 0 0 auto; color: #ffd18e; font-size: 9px; }
.gw-alert-item.critical > span, .gw-alert-item.emergency > span { color: #ff9a9a; }
.gw-alert-item div { min-width: 0; display: flex; flex-direction: column; }
.gw-alert-item b { color: #e5f3f1; font-size: 10px; font-weight: 500; }
.gw-alert-item small { overflow: hidden; color: #84acb1; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.gw-alert-item time { flex: 0 0 auto; margin-left: auto; color: #63949b; font-family: Consolas, monospace; font-size: 8px; }
@media (max-height: 800px) {
  .gw-screen { --gw-head: 60px; --gw-bottom: 110px; }
  .gw-head { padding: 8px 18px; }
  .gw-brand small { display: none; }
  .gw-head-center { gap: 10px; }
  .gw-clock, .gw-date { font-size: 16px; }
  .gw-stage { grid-template-rows: 40px minmax(170px, 1fr) 56px 62px; gap: 4px; }
  .gw-stage-title h1 { font-size: 17px; }
  .gw-health-ring { width: 104px; height: 104px; }
  .gw-health-ring strong { font-size: 28px; }
  .gw-health-meta { font-size: 9px; }
  .gw-panel { padding: 10px 12px; }
  .gw-panel-head { margin-bottom: 6px; }
  .gw-access-list > div { padding: 4px 6px; }
  .gw-telemetry > div { padding: 4px 7px; }
  .gw-voice-console { padding: 5px 9px; }
  .gw-voice-trigger { height: 44px; }
  .gw-bottom { padding: 6px 16px 10px; gap: 10px; }
  .gw-chat, .gw-alertdeck { padding: 8px 10px; }
  .gw-chat-head { margin-bottom: 4px; }
}
@media (max-height: 680px) {
  .gw-screen { height: auto; min-height: 660px; overflow-y: auto; }
  .gw-body { height: auto; min-height: 360px; }
  .gw-bottom { height: 110px; min-height: 110px; }
}
@media (max-width: 1200px) { .gw-body { grid-template-columns: 230px minmax(360px, 1fr) 340px; padding: 12px 14px 0; } .gw-bottom { padding: 6px 14px 10px; grid-template-columns: 1fr; height: 110px; min-height: 110px; } .gw-body { height: auto; min-height: 600px; } .gw-screen { overflow: auto; } }
@media (max-width: 800px) { .gw-head { padding: 10px 12px; } .gw-brand b { font-size: 13px; } .gw-head-center { display: none; } .gw-head-actions :deep(.el-button) { display: none; } .gw-body { display: flex; flex-direction: column; padding: 10px; } .gw-rail { display: grid; grid-template-columns: 1fr 1fr; overflow: visible; } .gw-left .gw-panel-grow, .gw-right .gw-panel-grow { display: none; } .gw-right { display: flex; flex-direction: column; } .gw-right .gw-insight-panel { flex: 0 0 auto; } .gw-chat-rail { min-height: 420px; } .gw-stage { grid-template-rows: 42px 360px 60px 70px; } .gw-voice-wave { display: none; } .gw-bottom { padding: 8px; } }
</style>