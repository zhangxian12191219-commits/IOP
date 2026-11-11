<template>
  <div class="ai-page">
    <div class="ai-hero">
      <div>
        <div class="ai-eyebrow">AI OPERATIONS</div>
        <h1>{{ aiStatus.name || '玄武' }} · AI 智能运维</h1>
        <p>全系统工具调用 · 告警研判 · MIB 配置辅助 · 确认式操作</p>
      </div>
      <div class="ai-hero-actions">
        <el-tag :type="aiStatus.configured ? 'success' : 'info'" effect="plain">
          {{ aiStatus.configured ? `${aiStatus.model} 已接入` : '本地统计模式' }}
        </el-tag>
        <el-button size="small" @click="openAiScreen"><el-icon><Monitor /></el-icon>AI运维大屏</el-button>
        <el-button size="small" type="primary" :loading="reportLoading" @click="generateReport">
          <el-icon><DocumentAdd /></el-icon>AI生成报告
        </el-button>
        <el-button v-if="canConfigure" size="small" @click="openConfig"><el-icon><Setting /></el-icon>模型配置</el-button>
      </div>
    </div>

    <div class="ai-stat-grid">
      <div><span>资产设备</span><b>{{ overview?.assets?.total ?? '-' }}</b><small>启用 {{ overview?.assets?.enabled ?? '-' }}</small></div>
      <div class="ai-stat-clickable" title="点击查看活动告警" @click="$router.push('/alerts?view=active')">
        <span>未恢复告警</span>
        <b class="danger">{{ overview?.alerts?.active ?? '-' }}</b>
        <small>未确认 {{ overview?.alerts?.unacknowledged ?? '-' }} · 设备 {{ overview?.alerts?.device_active ?? '-' }} / 网站 {{ overview?.alerts?.website_active ?? '-' }} / 虚拟化 {{ overview?.alerts?.virtual_active ?? '-' }}</small>
      </div>
      <div><span>MIB 对象</span><b>{{ overview?.mibs?.objects ?? '-' }}</b><small>{{ overview?.mibs?.files ?? '-' }} 个文件</small></div>
      <div><span>虚拟化资源</span><b>{{ overview?.virtualization?.vms ?? '-' }}</b><small>{{ overview?.virtualization?.platforms ?? '-' }} 个平台</small></div>
    </div>

    <el-alert
      v-if="!aiStatus.configured"
      class="ai-model-alert"
      type="warning"
      :closable="false"
      show-icon
      title="当前未接入大模型，智能体正在使用本地工具模式"
      description="本地工具模式仍可查询全系统数据、分析告警并生成 MIB 配置建议；配置 OpenAI 兼容模型后可获得更强的多轮推理和工具规划能力。"
    >
      <template #default>
        <el-button v-if="canConfigure" size="small" type="primary" plain @click="openConfig">现在配置模型</el-button>
      </template>
    </el-alert>

    <div class="ai-layout">
      <section class="ai-chat-card">
        <div class="ai-card-head">
          <div><strong>{{ aiStatus.name || 'AI' }}智能体</strong><small>工具调用 · 全模块辅助 · 写操作需人工确认</small></div>
          <div class="ai-chat-head-actions">
            <el-tag size="small" :type="['agent', 'model'].includes(chatMode) ? 'success' : 'info'" effect="plain">
              {{ chatMode === 'agent' ? '智能体' : chatMode === 'model' ? '模型' : '本地工具' }}
            </el-tag>
            <el-button size="small" type="primary" plain @click="startNewSession">新对话</el-button>
          </div>
        </div>
        <div ref="messagesRef" class="ai-messages">
          <div v-for="(item, index) in messages" :key="index" class="ai-message" :class="item.role">
            <div class="ai-avatar">{{ item.role === 'user' ? '我' : '玄' }}</div>
            <div class="ai-bubble" :class="{ 'agent-bubble': item.steps?.length || item.cards?.length }">
              <div class="ai-bubble-text">{{ item.content }}</div>
              <div v-if="item.steps?.length" class="ai-agent-steps">
                <span v-for="(step, si) in item.steps" :key="si" :class="{ failed: !step.ok }">
                  <i></i>{{ step.label }}
                </span>
              </div>
              <div v-for="(card, ci) in item.cards || []" :key="ci" class="ai-agent-card">
                <div class="ai-agent-card-head"><strong>{{ card.title }}</strong><span>{{ card.type }}</span></div>
                <div v-if="card.type === 'stats'" class="ai-agent-stats">
                  <div v-for="row in card.items || []" :key="row.label"><span>{{ row.label }}</span><b>{{ row.value }}</b><small>{{ row.note || '' }}</small></div>
                </div>
                <div v-else-if="card.type === 'alerts'" class="ai-agent-list">
                  <div v-for="row in (card.items || []).slice(0, 8)" :key="`${row.source}-${row.id}`" class="ai-agent-alert-row">
                    <span class="ai-agent-level" :class="row.level">{{ row.level_label || row.level }}</span>
                    <div><b>{{ row.device_name || row.device_ip || '对象' }}</b><small>{{ row.message || row.reason || '-' }}</small></div>
                  </div>
                  <span v-if="!card.items?.length" class="ai-muted">暂无数据</span>
                </div>
                <div v-else-if="card.type === 'devices'" class="ai-agent-list">
                  <div v-for="row in (card.items || []).slice(0, 8)" :key="row.id" class="ai-agent-device-row">
                    <b>{{ row.name }}</b><span>{{ row.ip_address }}</span>
                    <small>{{ row.vendor || '-' }} {{ row.model || '' }} · 告警 {{ row.active_alerts || 0 }}</small>
                  </div>
                  <span v-if="!card.items?.length" class="ai-muted">暂无匹配设备</span>
                </div>
                <div v-else-if="card.type === 'device'" class="ai-agent-fields">
                  <div v-for="(value, key) in (card.items || {})" :key="key">
                    <template v-if="!['active_alerts', 'interfaces', 'custom_metrics', 'mib'].includes(key)">
                      <span>{{ key }}</span><b>{{ formatAgentValue(value) }}</b>
                    </template>
                  </div>
                </div>
                <div v-else-if="card.type === 'mib'" class="ai-agent-list">
                  <div v-for="row in (card.items || []).slice(0, 3)" :key="row.mib_id" class="ai-agent-mib-row">
                    <b>{{ row.module_name || row.filename || `MIB #${row.mib_id}` }}</b>
                    <span>置信度 {{ row.confidence ?? '-' }} · 有效 OID {{ row.valid_count ?? 0 }}/{{ row.tested_count ?? 0 }}</span>
                    <small>{{ row.reason || '-' }}</small>
                  </div>
                  <div v-if="card.snmp" class="ai-agent-mib-snmp">
                    SNMP：{{ card.snmp.reachable ? '可达' : '不可达' }} · {{ card.snmp.sys_descr || card.snmp.error || '-' }}
                  </div>
                  <span v-if="!card.items?.length" class="ai-muted">暂无候选 MIB，请确认 MIB 库和设备 SNMP</span>
                </div>
                <div v-else-if="card.type === 'mib_library'" class="ai-agent-list">
                  <div v-for="row in (card.items || []).slice(0, 10)" :key="row.id" class="ai-agent-mib-row">
                    <b>{{ row.module_name || row.filename }}</b>
                    <span>{{ row.vendor || '-' }} · {{ row.object_count }} 对象 · {{ (row.categories || []).slice(0, 4).join(' / ') }}</span>
                  </div>
                  <span v-if="!card.items?.length" class="ai-muted">MIB 库为空</span>
                </div>
                <div v-else class="ai-agent-fields">
                  <div v-for="(value, key) in (card.items?.[0] || {})" :key="key">
                    <span>{{ key }}</span><b>{{ formatAgentValue(value) }}</b>
                  </div>
                </div>
              </div>
              <div v-if="item.actions?.length" class="ai-agent-actions">
                <el-button v-for="(action, ai) in item.actions" :key="ai" size="small"
                           :type="action.type === 'mib_apply' ? 'primary' : 'default'"
                           :loading="actionLoading === `${item.id || index}-${ai}`"
                           @click="runAgentAction(action, item, index, ai)">
                  {{ action.label }}
                </el-button>
              </div>
              <div v-if="item.suggestions?.length" class="ai-agent-suggestions">
                <span v-for="s in item.suggestions" :key="s" @click="ask(s)">{{ s }}</span>
              </div>
            </div>
          </div>
          <div v-if="sending" class="ai-message assistant">
            <div class="ai-avatar">玄</div>
            <div class="ai-bubble thinking"><i></i><i></i><i></i></div>
          </div>
        </div>
        <div class="ai-quick">
          <button v-for="q in quickQuestions" :key="q" type="button" @click="ask(q)">{{ q }}</button>
        </div>
        <div class="ai-composer">
          <el-input v-model="input" type="textarea" :rows="2" placeholder="问我资产、告警、MIB 配置、备份、拓扑、机房、虚拟化、证书、巡检、用户审计…" @keydown.enter.exact.prevent="ask()" />
          <el-button type="primary" :loading="sending" :disabled="!input.trim()" @click="ask()">发送</el-button>
        </div>
      </section>

      <aside class="ai-side">
        <section class="ai-side-card">
          <div class="ai-card-head"><strong>告警研判</strong><small>{{ alertAnalysis?.summary || '等待分析' }}</small></div>
          <div v-if="alertAnalysis?.causes?.length" class="ai-cause-list">
            <div v-for="item in alertAnalysis.causes.slice(0, 5)" :key="item.type">
              <b>{{ item.label }}</b><span>{{ item.cause }}</span>
            </div>
          </div>
          <el-empty v-else description="当前没有未恢复告警" :image-size="48" />
        </section>
        <section class="ai-side-card">
          <div class="ai-card-head"><strong>MIB 指标分类</strong><small>可调用 MIB 工具</small></div>
          <div class="ai-tag-cloud">
            <el-tag v-for="item in overview?.mibs?.categories || []" :key="item.category" effect="plain" size="small">{{ item.category }} {{ item.count }}</el-tag>
            <span v-if="!overview?.mibs?.categories?.length" class="ai-muted">暂无分类数据</span>
          </div>
        </section>
        <section class="ai-side-card">
          <div class="ai-card-head"><strong>智能体工具</strong><small>{{ agentCapabilities.length }} 个可调用工具</small></div>
          <div class="ai-function-list">
            <span v-for="item in agentCapabilities" :key="item.key">{{ item.name }}</span>
            <span v-if="!agentCapabilities.length">工具加载中…</span>
          </div>
        </section>
        <section class="ai-side-card">
          <div class="ai-card-head"><strong>覆盖模块</strong><small>全功能辅助</small></div>
          <div class="ai-function-list">
            <span v-for="item in (overview?.functions || []).slice(0, 16)" :key="item">{{ item }}</span>
          </div>
        </section>
      </aside>
    </div>

    <el-dialog v-model="configVisible" title="AI 模型配置" width="min(720px, 94vw)">
      <el-alert type="info" :closable="false" show-icon title="支持 OpenAI 兼容接口（OpenAI、DeepSeek、Ollama 等）。API Key 加密保存。" class="ins-alert" />
      <el-form label-width="130px" class="ai-config-form">
        <el-form-item label="启用外部模型"><el-switch v-model="configForm.enabled" /></el-form-item>
        <el-form-item label="模型地址"><el-input v-model="configForm.base_url" placeholder="https://api.openai.com/v1" /></el-form-item>
        <el-form-item label="模型名称"><el-input v-model="configForm.model" placeholder="例如 gpt-4o-mini / deepseek-chat" /></el-form-item>
        <el-form-item label="API Key"><el-input v-model="configForm.api_key" type="password" show-password :placeholder="configForm.has_key ? '已配置，留空保持不变' : '输入 API Key'" /></el-form-item>
        <el-form-item label="温度">
          <el-input v-model="configForm.temperature" placeholder="0.2" style="width: 180px" />
          <span class="form-help">0.2–0.4 更稳定、工具调用更准确；0.7 更发散，但不会让模型“更聪明”。运维智能体建议 0.2–0.3。</span>
        </el-form-item>
        <el-form-item label="最大 Token">
          <el-input-number v-model="configForm.max_tokens" :min="100" :max="8000" controls-position="right" />
          <span class="form-help">建议 1200–2000：日常问答更稳定；生成详细报告时可设为 3000–4000。</span>
        </el-form-item>
        <el-form-item label="AI 名称"><el-input v-model="configForm.name" maxlength="20" placeholder="默认：玄武" /></el-form-item>
        <el-form-item label="语音音色">
          <el-select v-model="configForm.voice_name" clearable filterable style="width: 360px" placeholder="自动选择系统中文音色">
            <el-option label="自动选择音色" value="" />
            <el-option v-for="voice in voiceOptions" :key="voice.name" :label="`${voice.name} (${voice.lang})`" :value="voice.name" />
          </el-select>
          <el-button style="margin-left: 8px" @click="previewVoice">试听</el-button>
        </el-form-item>
        <el-divider content-position="left">TTS 语音模型</el-divider>
        <el-alert type="info" :closable="false" show-icon class="ins-alert"
          title="支持 OpenAI 兼容 /audio/speech（OpenAI TTS、通义千问 TTS、火山/本地兼容服务）。启用后优先播放 TTS 模型音频，失败自动回退浏览器语音。" />
        <el-form-item label="启用 TTS 模型"><el-switch v-model="configForm.tts_enabled" /></el-form-item>
        <el-form-item label="TTS 地址">
          <el-input v-model="configForm.tts_base_url" placeholder="留空继承对话模型地址，例如 https://api.openai.com/v1" />
        </el-form-item>
        <el-form-item label="TTS 模型">
          <el-input v-model="configForm.tts_model" placeholder="例如 tts-1 / qwen-tts / CosyVoice" />
        </el-form-item>
        <el-form-item label="TTS 音色">
          <el-input v-model="configForm.tts_voice" placeholder="例如 alloy / Cherry / 芊悦" />
        </el-form-item>
        <el-form-item label="TTS API Key">
          <el-input v-model="configForm.tts_api_key" type="password" show-password autocomplete="new-password"
            :placeholder="configForm.tts_has_key ? '已配置，留空保持不变' : '留空继承对话模型 API Key'" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="testModel" :loading="testing">测试连接</el-button>
        <el-button @click="configVisible = false">取消</el-button>
        <el-button type="primary" @click="saveConfig" :loading="savingConfig">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="reportVisible" title="AI 运维报告" width="min(900px, 96vw)" top="5vh">
      <div v-if="reportPreview" class="ai-report-preview">
        <h3>{{ reportPreview.title }}</h3>
        <div class="ai-report-meta">模型：{{ reportPreview.model || '本地统计' }} · 生成时间：{{ reportPreview.created_at || '-' }}</div>
        <div class="ai-report-content" v-html="reportHtml"></div>
      </div>
      <template #footer>
        <el-button @click="reportVisible = false">关闭</el-button>
        <el-button type="primary" :disabled="!reportPreview" @click="downloadReport">下载报告</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { aiApi } from '@/api'
import { can, currentUser, downloadWithAuth, getToken, handoffToken } from '@/store/auth'

const aiStatus = ref({
  configured: false, model: '', name: '玄武', voice_name: '',
  tts_enabled: false, tts_base_url: '', tts_model: 'tts-1', tts_voice: 'alloy', tts_has_key: false,
})
const overview = ref(null)
const alertAnalysis = ref(null)
function escapeReportHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[ch]))
}

function renderReportInline(value) {
  return escapeReportHtml(value)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
}

function splitReportTableRow(line) {
  return String(line || '').trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((cell) => cell.trim())
}

function renderReportHtml(value) {
  const source = String(value || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  if (!source.trim()) return '<p class="report-empty">暂无报告内容</p>'
  const lines = source.split('\n')
  const output = []
  let inCode = false
  let inList = false
  const closeList = () => {
    if (inList) {
      output.push('</ul>')
      inList = false
    }
  }
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index]
    if (line.trim().startsWith('```')) {
      closeList()
      output.push(inCode ? '</code></pre>' : '<pre><code>')
      inCode = !inCode
      continue
    }
    if (inCode) {
      output.push(`${escapeReportHtml(line)}\n`)
      continue
    }
    const heading = line.match(/^(#{1,4})\s+(.+)$/)
    const item = line.match(/^\s*[-*]\s+(.+)$/)
    if (heading) {
      closeList()
      const level = Math.min(4, heading[1].length + 1)
      output.push(`<h${level}>${renderReportInline(heading[2])}</h${level}>`)
      continue
    }
    if (item) {
      if (!inList) {
        output.push('<ul>')
        inList = true
      }
      output.push(`<li>${renderReportInline(item[1])}</li>`)
      continue
    }
    // Markdown 表格：当前行含 |，下一行是分隔行
    if (line.includes('|') && index + 1 < lines.length
      && /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[index + 1])) {
      closeList()
      const headers = splitReportTableRow(line)
      output.push('<table><thead><tr>')
      headers.forEach((cell) => output.push(`<th>${renderReportInline(cell)}</th>`))
      output.push('</tr></thead><tbody>')
      index += 1
      while (index + 1 < lines.length && lines[index + 1].includes('|')) {
        index += 1
        const cells = splitReportTableRow(lines[index])
        output.push('<tr>')
        cells.forEach((cell) => output.push(`<td>${renderReportInline(cell)}</td>`))
        output.push('</tr>')
      }
      output.push('</tbody></table>')
      continue
    }
    if (!line.trim()) {
      closeList()
      continue
    }
    closeList()
    output.push(`<p>${renderReportInline(line)}</p>`)
  }
  closeList()
  if (inCode) output.push('</code></pre>')
  return output.join('')
}

const reportHtml = computed(() => renderReportHtml(reportPreview.value?.content || ''))
const messages = ref([{ role: 'assistant', content: 'AI 运维智能体已就绪，有什么问题请说。' }])
const input = ref('')
const sending = ref(false)
const router = useRouter()
const chatMode = ref('local')
const actionLoading = ref('')
const agentCapabilities = ref([])
const messagesRef = ref(null)
// 会话上下文：服务端按 session_id 保存最近消息，前端同时持久化，刷新后仍可继续。
const SESSION_KEY = 'ai_ops_session_id'
const MESSAGES_KEY = 'ai_ops_messages'
const sessionId = ref('')
const reportLoading = ref(false)
const reportVisible = ref(false)
const reportPreview = ref(null)
const configVisible = ref(false)
const savingConfig = ref(false)
const testing = ref(false)
const canConfigure = computed(() => can('ai:config'))
const quickQuestions = [
  '当前有哪些严重告警？按影响排序',
  '帮我检查一台设备的 MIB 配置并给出建议',
  '哪些设备没有配置凭据或自动备份？',
  '分析机房 U 位和功率容量风险',
  '虚拟化平台最近有哪些活动告警？',
  '生成一份运维报告',
]
const voiceOptions = ref([])

const configForm = reactive({
  enabled: false, base_url: '', model: '', api_key: '', has_key: false, temperature: '0.2', max_tokens: 1200,
  name: '玄武', voice_name: '',
  tts_enabled: false, tts_base_url: '', tts_model: 'tts-1', tts_voice: 'alloy', tts_api_key: '', tts_has_key: false,
})

async function load() {
  try {
    const [statusRes, overviewRes, analysisRes, capsRes] = await Promise.all([
      aiApi.status(), aiApi.overview(), aiApi.alertAnalysis(), aiApi.agentCapabilities(),
    ])
    agentCapabilities.value = capsRes.data?.tools || []
    aiStatus.value = statusRes.data
    const name = String(aiStatus.value.name || '玄武').trim() || '玄武'
    document.title = `${name} · AI 智能运维`
    if (messages.value.length <= 1 && messages.value[0]?.role === 'assistant') {
      messages.value[0].content = `我是${name} AI 运维智能体，可以调用工具查询全系统数据、分析告警和辅助 MIB 配置。有什么问题请说。`
    }
    persistConversation()
    overview.value = overviewRes.data
    alertAnalysis.value = analysisRes.data?.analysis || null
  } catch (e) {
    ElMessage.error(e.message || 'AI 运维数据加载失败')
  }
}

function scrollBottom() {
  nextTick(() => {
    const el = messagesRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

function generateSessionId() {
  try {
    if (window.crypto?.randomUUID) return window.crypto.randomUUID()
  } catch { /* ignore */ }
  return `ai-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
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

function openAiScreen() {
  handoffToken(getToken())
  window.open('/bigscreen/ai', '_blank')
}

function startNewSession() {
  const previous = sessionId.value
  // 先本地立即切换，避免 reset 接口慢或被浏览器阻塞时按钮看起来没反应。
  sessionId.value = generateSessionId()
  messages.value = [{ role: 'assistant', content: `我是${assistantName.value}，有什么问题请说。` }]
  input.value = ''
  chatMode.value = 'local'
  persistConversation()
  scrollBottom()
  ElMessage.success('已开启新对话')
  if (previous) {
    aiApi.resetChat({ session_id: previous }).catch(() => { /* 服务端会话可能已过期 */ })
  }
}

async function ask(text = '') {
  const question = String(text || input.value || '').trim()
  if (!question || sending.value) return
  input.value = ''
  messages.value.push({ role: 'user', content: question })
  scrollBottom()
  sending.value = true
  try {
    const res = await aiApi.agentChat({
      message: question,
      history: messages.value.slice(0, -1).slice(-12),
      session_id: sessionId.value,
      channel: 'text',
    })
    const data = res.data || {}
    if (data.session_id) sessionId.value = data.session_id
    chatMode.value = data.mode || 'local'
    messages.value.push({
      role: 'assistant',
      content: data.reply || '暂无分析结果',
      steps: data.steps || [],
      cards: data.cards || [],
      actions: data.actions || [],
      suggestions: data.suggestions || [],
    })
    persistConversation()
  } catch (e) {
    messages.value.push({ role: 'assistant', content: e.message || 'AI 分析失败，请稍后再试。' })
    persistConversation()
  } finally {
    sending.value = false
    scrollBottom()
  }
}

function formatAgentValue(value) {
  if (value === null || value === undefined || value === '') return '-'
  if (Array.isArray(value)) {
    return value.slice(0, 4).map((item) => (typeof item === 'object' ? JSON.stringify(item).slice(0, 120) : item)).join(' / ') || '-'
  }
  if (typeof value === 'object') return JSON.stringify(value).slice(0, 240)
  return String(value)
}

function runAgentAction(action) {
  if (!action) return
  if (action.type === 'navigate' && action.path) {
    router.push(action.path)
    return
  }
  ElMessage.info('AI 仅提供只读分析和人工入口，写操作请在对应业务页面确认执行')
}

async function generateReport() {
  reportLoading.value = true
  try {
    const res = await aiApi.generateReport({ topic: '智能运维分析报告' })
    reportPreview.value = res.data
    reportVisible.value = true
    ElMessage.success(res.data?.mode === 'model' ? 'AI 报告已生成' : '本地统计报告已生成')
  } catch (e) {
    ElMessage.error(e.message || '报告生成失败')
  } finally {
    reportLoading.value = false
  }
}

function downloadReport() {
  if (reportPreview.value?.id) downloadWithAuth(aiApi.downloadUrl(reportPreview.value.id))
}

function openConfig() {
  Object.assign(configForm, {
    enabled: !!aiStatus.value.enabled,
    base_url: aiStatus.value.base_url || 'https://api.openai.com/v1',
    model: aiStatus.value.model || 'gpt-4o-mini',
    api_key: '',
    has_key: !!aiStatus.value.has_key,
    temperature: String(aiStatus.value.temperature || '0.2'),
    max_tokens: Number(aiStatus.value.max_tokens || 1200),
    name: aiStatus.value.name || '玄武',
    voice_name: aiStatus.value.voice_name || '',
    tts_enabled: !!aiStatus.value.tts_enabled,
    tts_base_url: aiStatus.value.tts_base_url || '',
    tts_model: aiStatus.value.tts_model || 'tts-1',
    tts_voice: aiStatus.value.tts_voice || 'alloy',
    tts_api_key: '',
    tts_has_key: !!aiStatus.value.tts_has_key,
  })
  loadVoices()
  configVisible.value = true
}

function loadVoices() {
  const voices = window.speechSynthesis?.getVoices?.() || []
  voiceOptions.value = voices.filter((voice) => /^zh/i.test(voice.lang || '') || /Chinese|中文/i.test(voice.name || ''))
}

function pickConfigVoice() {
  const voices = voiceOptions.value.length ? voiceOptions.value : (window.speechSynthesis?.getVoices?.() || [])
  const preferred = String(configForm.voice_name || '').trim().toLowerCase()
  if (preferred) {
    const exact = voices.find((voice) => String(voice.name || '').toLowerCase() === preferred)
    if (exact) return exact
  }
  return voices.find((voice) => /^zh/i.test(voice.lang || '')) || voices[0] || null
}

function previewVoice() {
  const synth = window.speechSynthesis
  if (!synth) {
    ElMessage.warning('当前浏览器不支持语音合成')
    return
  }
  synth.cancel()
  const utterance = new SpeechSynthesisUtterance(`我是${configForm.name || '玄武'}，有什么问题请说。`)
  utterance.lang = 'zh-CN'
  utterance.rate = 0.95
  utterance.pitch = 1.0
  utterance.volume = 0.96
  const voice = pickConfigVoice()
  if (voice) utterance.voice = voice
  synth.speak(utterance)
}

async function saveConfig() {
  savingConfig.value = true
  try {
    const res = await aiApi.saveConfig(configForm)
    aiStatus.value = res.data
    document.title = `${String(res.data?.name || 'AI').trim() || 'AI'} · AI 智能运维`
    configVisible.value = false
    ElMessage.success('AI 配置已保存')
  } catch (e) {
    ElMessage.error(e.message || 'AI 配置保存失败')
  } finally {
    savingConfig.value = false
  }
}

async function testModel() {
  testing.value = true
  try {
    const res = await aiApi.testConfig(configForm)
    const used = res.data?.using_saved_key ? '（使用已保存的 API Key）' : '（使用当前填写的 API Key）'
    ElMessage.success(`连接成功：${res.data?.message || ''} ${used}`)
  } catch (e) {
    ElMessage.error(e.message || '模型连接失败')
  } finally {
    testing.value = false
  }
}

watch(messages, () => {
  nextTick(() => {
    scrollBottom()
    window.requestAnimationFrame(scrollBottom)
  })
}, { deep: true })

watch(sending, (value) => {
  if (value) scrollBottom()
})

onMounted(() => {
  restoreConversation()
  load()
  loadVoices()
  window.speechSynthesis?.addEventListener?.('voiceschanged', loadVoices)
})
</script>

<style scoped>
.ai-stat-clickable { cursor: pointer; transition: transform .15s ease, border-color .15s ease; }
.ai-stat-clickable:hover { transform: translateY(-1px); border-color: rgba(239,68,68,.45); }
.ai-stat-clickable small { line-height: 1.5; }
.ai-page { padding: 16px; background: #f5f7fa; min-height: 100%; box-sizing: border-box; }
.ai-hero { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; flex-wrap: wrap; padding: 20px; border-radius: 14px; background: linear-gradient(120deg, #0f2a43, #133f5c 55%, #0d766e); color: #fff; box-shadow: 0 10px 24px rgba(15, 42, 67, .12); }
.ai-eyebrow { color: #73d9d0; font-size: 10px; letter-spacing: .18em; }
.ai-hero h1 { margin: 5px 0; font-size: 24px; }
.ai-hero p { margin: 0; color: #b8d8e5; font-size: 12px; }
.ai-hero-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ai-stat-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 14px 0; }
.ai-stat-grid > div { padding: 13px 16px; border: 1px solid #e0e9f2; border-radius: 10px; background: #fff; }
.ai-stat-grid span { display: block; color: #7790a3; font-size: 10px; }
.ai-stat-grid b { display: block; margin-top: 3px; color: #15364c; font-size: 23px; }
.ai-stat-grid b.danger { color: #dc2626; }
.ai-stat-grid small { color: #9aacbb; font-size: 10px; }
.ai-layout { display: grid; grid-template-columns: minmax(0, 1.8fr) minmax(300px, .8fr); align-items: stretch; gap: 12px; }
.ai-model-alert { margin: 14px 0; }
.ai-chat-card, .ai-side-card { border: 1px solid #e0e9f2; border-radius: 12px; background: #fff; }
.ai-chat-card { display: flex; flex-direction: column; height: clamp(560px, calc(100dvh - 300px), 900px); min-height: 0; overflow: hidden; }
.ai-card-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; padding: 12px 14px; border-bottom: 1px solid #edf3f7; }
.ai-card-head strong { display: block; color: #1e3a4f; font-size: 13px; }
.ai-card-head small { color: #8da0b0; font-size: 10px; }
.ai-chat-head-actions { display: flex; align-items: center; gap: 6px; }
.ai-messages { flex: 1; min-height: 0; max-height: none; overflow-y: auto; padding: 14px; background: #fbfdff; scroll-behavior: smooth; }
.ai-message { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 12px; }
.ai-message.user { flex-direction: row-reverse; }
.ai-avatar { flex: 0 0 28px; width: 28px; height: 28px; display: grid; place-items: center; border-radius: 50%; background: #0f766e; color: #fff; font-size: 11px; font-weight: 700; }
.ai-message.user .ai-avatar { background: #2563eb; }
.ai-bubble { max-width: 88%; overflow-wrap: anywhere; word-break: break-word; padding: 9px 12px; border-radius: 10px; background: #fff; border: 1px solid #e3edf4; color: #334e63; font-size: 12px; line-height: 1.75; white-space: pre-wrap; }
.ai-message.user .ai-bubble { background: #eff6ff; border-color: #bfdbfe; }
.ai-bubble.thinking { display: flex; gap: 4px; padding: 13px; }
.ai-bubble.thinking i { width: 5px; height: 5px; border-radius: 50%; background: #0f766e; animation: ai-blink 1s infinite; }
.ai-bubble.thinking i:nth-child(2) { animation-delay: .15s; }
.ai-bubble.thinking i:nth-child(3) { animation-delay: .3s; }
@keyframes ai-blink { 0%, 60%, 100% { opacity: .25; transform: translateY(0); } 30% { opacity: 1; transform: translateY(-3px); } }
.ai-quick { display: flex; gap: 6px; flex-wrap: wrap; padding: 8px 14px; border-top: 1px solid #edf3f7; }
.ai-quick button { border: 1px solid #dce9f2; border-radius: 20px; background: #f8fbff; color: #507088; padding: 4px 9px; font-size: 10px; cursor: pointer; }
.ai-quick button:hover { color: #0f766e; border-color: #9edbd2; }
.ai-composer { display: flex; gap: 8px; padding: 12px 14px; border-top: 1px solid #edf3f7; }
.ai-side { display: flex; flex-direction: column; gap: 12px; min-height: 0; max-height: clamp(560px, calc(100dvh - 300px), 900px); overflow-y: auto; }
.ai-side-card { padding-bottom: 10px; }
.ai-cause-list { display: flex; flex-direction: column; gap: 8px; padding: 10px 14px; }
.ai-cause-list > div { padding: 8px; border-radius: 7px; background: #fbfdff; border: 1px solid #edf3f7; }
.ai-cause-list b { display: block; color: #334e63; font-size: 11px; }
.ai-cause-list span { color: #8498a8; font-size: 10px; line-height: 1.6; }
.ai-tag-cloud { display: flex; gap: 6px; flex-wrap: wrap; padding: 12px 14px; }
.ai-muted { color: #9aacbb; font-size: 11px; }
.ai-function-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 5px; padding: 10px 14px; color: #5e778a; font-size: 10px; }
.ai-function-list span { padding: 4px 6px; border-radius: 5px; background: #f8fbfd; }
.ai-report-preview { max-height: 65vh; overflow: auto; }
.ai-report-preview h3 { color: #1e3a4f; }
.ai-report-preview pre { white-space: pre-wrap; font-family: inherit; font-size: 12px; line-height: 1.8; color: #334e63; }
@media (max-width: 1100px) { .ai-layout { grid-template-columns: 1fr; } .ai-side { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 760px) { .ai-page { padding: 8px; } .ai-stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .ai-side { grid-template-columns: 1fr; } }
.agent-bubble { width: 94%; max-width: 94%; white-space: normal; }
.ai-agent-steps { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; padding-top: 7px; border-top: 1px dashed #e2edf5; }
.ai-agent-steps span { display: inline-flex; align-items: center; gap: 4px; padding: 2px 6px; border-radius: 4px; background: #ecfdf5; color: #0f766e; font-size: 9px; }
.ai-agent-steps span i { width: 5px; height: 5px; border-radius: 50%; background: #10b981; }
.ai-agent-steps span.failed { background: #fef2f2; color: #b91c1c; }
.ai-agent-steps span.failed i { background: #ef4444; }
.ai-agent-card { margin-top: 9px; border: 1px solid #e1edf5; border-radius: 8px; background: #fbfdff; overflow: hidden; }
.ai-agent-card-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 6px 9px; background: #f1f8fc; }
.ai-agent-card-head strong { color: #24475e; font-size: 11px; }
.ai-agent-card-head span { color: #91a7b8; font-family: monospace; font-size: 8px; }
.ai-agent-stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 5px; padding: 8px; }
.ai-agent-stats > div { padding: 6px 7px; border: 1px solid #e6eff5; border-radius: 6px; background: #fff; }
.ai-agent-stats span { display: block; color: #8298aa; font-size: 9px; }
.ai-agent-stats b { display: block; color: #0f766e; font-size: 17px; }
.ai-agent-stats small { color: #9aacba; font-size: 8px; }
.ai-agent-list { display: flex; flex-direction: column; gap: 4px; padding: 7px 9px; }
.ai-agent-alert-row { display: flex; align-items: flex-start; gap: 6px; padding: 5px 0; border-bottom: 1px dashed #edf3f7; }
.ai-agent-alert-row:last-child { border-bottom: 0; }
.ai-agent-alert-row div { min-width: 0; display: flex; flex-direction: column; }
.ai-agent-alert-row b { color: #29475b; font-size: 10px; }
.ai-agent-alert-row small { overflow: hidden; color: #73899b; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.ai-agent-level { flex: 0 0 auto; padding: 1px 5px; border-radius: 3px; background: #fff7e6; color: #b45309; font-size: 8px; }
.ai-agent-level.critical, .ai-agent-level.emergency { background: #fef2f2; color: #b91c1c; }
.ai-agent-device-row, .ai-agent-mib-row { display: flex; flex-direction: column; gap: 2px; padding: 5px 0; border-bottom: 1px dashed #edf3f7; }
.ai-agent-device-row b, .ai-agent-mib-row b { color: #1c435a; font-size: 10px; }
.ai-agent-device-row span, .ai-agent-mib-row span { color: #54748a; font-size: 9px; }
.ai-agent-device-row small, .ai-agent-mib-row small { color: #8ba0b0; font-size: 9px; }
.ai-agent-mib-snmp { padding: 5px 0; color: #7d93a4; font-size: 9px; line-height: 1.5; }
.ai-agent-fields { display: flex; flex-direction: column; gap: 3px; padding: 8px; }
.ai-agent-fields > div { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; font-size: 9px; }
.ai-agent-fields span { color: #8398a9; }
.ai-agent-fields b { color: #2b5068; font-weight: 500; text-align: right; word-break: break-all; }
.ai-agent-actions { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
.ai-agent-suggestions { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
.ai-agent-suggestions span { padding: 3px 7px; border: 1px solid #dceaf4; border-radius: 10px; background: #f7fbfe; color: #52758b; font-size: 9px; cursor: pointer; }
.ai-agent-suggestions span:hover { border-color: #7dd3fc; color: #0369a1; }
.ai-muted { color: #9aacbb; font-size: 10px; }
@media (max-width: 760px) { .ai-agent-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); } .agent-bubble { width: 100%; max-width: 100%; } }
.ai-report-meta { margin: -8px 0 12px; color: #8ba0b0; font-size: 10px; }
.ai-report-content { max-height: 64vh; overflow: auto; padding: 4px 16px 18px 4px; color: #334e63; font-size: 12px; line-height: 1.8; }
.ai-report-content h2 { margin: 6px 0 12px; color: #15364c; font-size: 20px; }
.ai-report-content h3 { margin: 18px 0 8px; padding-left: 8px; border-left: 3px solid #14b8a6; color: #155e75; font-size: 15px; }
.ai-report-content h4 { margin: 13px 0 6px; color: #315a70; font-size: 13px; }
.ai-report-content p { margin: 5px 0; }
.ai-report-content ul { margin: 5px 0 9px; padding-left: 20px; }
.ai-report-content table { width: 100%; margin: 8px 0 14px; border-collapse: collapse; font-size: 11px; }
.ai-report-content th, .ai-report-content td { padding: 5px 7px; border: 1px solid #dce8f0; text-align: left; vertical-align: top; }
.ai-report-content th { background: #f1f8fc; color: #1e4b63; }
.ai-report-content hr { margin: 16px 0; border: 0; border-top: 1px dashed #dce8f0; }
.ai-report-content .report-number { color: #2b5068; }
.ai-config-form :deep(.el-form-item__content) { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: flex-start; text-align: left; }
.ai-config-form :deep(.el-input-number) { text-align: left; }
.ai-config-form :deep(.el-input-number .el-input__inner) { padding-left: 8px; text-align: left; }
.ai-config-form :deep(.el-input-number .el-input__wrapper) { justify-content: flex-start; }
.ai-config-form .form-help { display: block; flex: 0 0 100%; width: 100%; margin: 4px 0 0; color: #8b9bab; font-size: 11px; line-height: 1.65; text-align: left; white-space: normal; }
</style>
