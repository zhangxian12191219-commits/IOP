<template>
  <div class="cascade-page">
    <div class="cascade-hero">
      <div>
        <div class="cascade-eyebrow">HQ · BRANCH FEDERATION</div>
        <h1>级联管理</h1>
        <p>分支主动出站连接总部，加密隧道同步资产、告警和运行数据</p>
      </div>
      <div class="cascade-hero-right">
        <el-tag :type="roleTag" effect="dark">{{ roleLabel }}</el-tag>
        <el-tag :type="tunnel.online ? 'success' : 'info'" effect="plain">
          {{ tunnel.online ? '隧道已连接' : '隧道未连接' }}
        </el-tag>
        <el-button size="small" @click="loadAll" :loading="loading"><el-icon><Refresh /></el-icon>刷新</el-button>
      </div>
    </div>

    <div class="cascade-stat-grid">
      <div><span>分支节点</span><b>{{ summary.total || 0 }}</b><small>在线 {{ summary.online || 0 }} / 离线 {{ summary.offline || 0 }}</small></div>
      <div><span>分支资产</span><b>{{ summary.assets || 0 }}</b><small>来自全部已同步分支</small></div>
      <div><span>分支告警</span><b class="danger">{{ summary.alerts || 0 }}</b><small>未恢复告警汇总</small></div>
      <div><span>最近同步</span><b class="time">{{ latestSyncText }}</b><small>{{ role === 'branch' ? '本分支上报状态' : '总部接收状态' }}</small></div>
    </div>

    <el-tabs v-model="activeTab" class="cascade-tabs">
      <el-tab-pane label="分支视图" name="nodes">
        <div class="cascade-toolbar">
          <span class="muted">{{ role === 'branch' ? '本系统作为分支运行，数据会主动同步到总部。' : '总部节点可登记多个分支，在线状态按隧道心跳实时更新。' }}</span>
          <el-button v-if="role !== 'branch'" type="primary" size="small" @click="openCreate"><el-icon><Plus /></el-icon>登记分支</el-button>
        </div>
        <el-empty v-if="!nodes.length" description="暂无已登记分支" :image-size="60" />
        <div v-else class="cascade-node-grid">
          <div v-for="node in nodes" :key="node.id" class="cascade-node-card" :class="{ online: node.online }">
            <div class="cascade-node-head">
              <div><strong>{{ node.name }}</strong><span class="cascade-node-version">{{ node.version || '-' }}</span></div>
              <span class="cascade-status"><i></i>{{ node.online ? '在线' : '离线' }}</span>
            </div>
            <div class="cascade-node-address">{{ node.address || '未上报地址' }}</div>
            <div class="cascade-node-stats">
              <div><b>{{ node.stats?.assets || 0 }}</b><span>资产</span></div>
              <div><b class="danger">{{ node.stats?.alerts || 0 }}</b><span>告警</span></div>
              <div><b>{{ node.stats?.virtual_vms || 0 }}</b><span>虚拟机/容器</span></div>
            </div>
            <div class="cascade-node-foot">
              <span>同步：{{ formatTime(node.last_sync) || '从未' }}</span>
              <div class="cascade-node-actions">
                <el-button link type="primary" size="small" @click="openDetail(node)">查看数据</el-button>
                <el-button link type="danger" size="small" @click="removeNode(node)">删除</el-button>
              </div>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="级联通信" name="chat">
        <div class="cascade-chat-layout">
          <div class="cascade-chat-side">
            <div class="cascade-chat-side-title">会话节点</div>
            <button v-for="node in nodes" :key="node.id" class="cascade-chat-node" :class="{ active: chatNodeId === node.id }" @click="selectChatNode(node)">
              <span><i :class="{ online: node.online }"></i>{{ node.name }}</span>
              <small>{{ node.online ? '在线' : '离线待投递' }}</small>
            </button>
            <div v-if="role === 'branch'" class="cascade-chat-node active"><span><i class="online"></i>总部</span><small>级联频道</small></div>
          </div>
          <div class="cascade-chat-main">
            <div class="cascade-chat-head">
              <strong>{{ role === 'branch' ? '总部级联频道' : (chatNode?.name || '选择分支节点') }}</strong>
              <small>消息通过加密隧道传输</small>
            </div>
            <div ref="chatRef" class="cascade-messages">
              <div v-for="message in messages" :key="message.id" class="cascade-message" :class="message.direction === 'hq_to_branch' ? 'from-hq' : 'from-branch'">
                <div class="cascade-message-meta">{{ message.sender || (message.direction === 'hq_to_branch' ? '总部' : '分支') }} · {{ formatTime(message.created_at) }}</div>
                <div class="cascade-message-body">{{ message.content }}</div>
              </div>
              <el-empty v-if="!messages.length" description="暂无级联消息" :image-size="50" />
            </div>
            <div class="cascade-composer">
              <el-input v-model="chatInput" type="textarea" :rows="2" placeholder="向分支发送运维消息…" @keydown.enter.exact.prevent="sendChat" />
              <el-button type="primary" :loading="sending" :disabled="!chatInput.trim() || (role !== 'branch' && !chatNodeId)" @click="sendChat">发送</el-button>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="连接配置" name="config">
        <el-form label-width="145px" class="cascade-config-form">
          <el-alert type="info" :closable="false" show-icon title="分支只需要主动访问总部 HTTPS 地址，不需要在分支防火墙开放入站端口。业务帧在 WSS 隧道内再次使用令牌派生密钥加密。" />
          <el-form-item label="启用级联"><el-switch v-model="configForm.enabled" /></el-form-item>
          <el-form-item label="本机角色">
            <el-radio-group v-model="configForm.role" @change="onRoleChange">
              <el-radio-button value="standalone">独立运行</el-radio-button>
              <el-radio-button value="hq">总部</el-radio-button>
              <el-radio-button value="branch">分支</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item v-if="configForm.role !== 'standalone'" label="隧道专用端口">
            <el-input-number v-model="configForm.tunnel_port" :min="1" :max="65535" controls-position="right" />
            <span class="form-hint">默认 9527；总部需监听并放行该端口，分支将用此端口建立隧道</span>
          </el-form-item>
          <template v-if="configForm.role === 'branch'">
            <el-form-item label="节点名称"><el-input v-model="configForm.node_name" maxlength="160" placeholder="例如：上海分支" /></el-form-item>
            <el-form-item label="总部地址"><el-input v-model="configForm.hq_url" placeholder="https://总部地址" /></el-form-item>
            <el-form-item label="接入令牌"><el-input v-model="configForm.token" type="password" show-password :placeholder="configForm.has_token ? '已配置，留空表示不修改' : '总部登记分支时生成的一次性令牌'" /></el-form-item>
            <el-form-item label="同步间隔"><el-input-number v-model="configForm.sync_interval" :min="30" :max="3600" controls-position="right" /><span class="form-hint">秒</span></el-form-item>
            <el-form-item label="校验总部 TLS"><el-switch v-model="configForm.verify_tls" /><span class="form-hint">生产环境建议开启；仅自签名测试环境可关闭</span></el-form-item>
          </template>
          <el-form-item>
            <el-button type="primary" :loading="configSaving" @click="saveConfig">保存并重连隧道</el-button>
          </el-form-item>
        </el-form>
        <div v-if="configForm.role === 'hq'" class="cascade-hq-tip">
          总部登记分支后，将生成的一次性接入令牌填入分支系统的「连接配置」，分支即可主动上线。
        </div>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="createVisible" title="登记级联分支" width="560px">
      <el-form label-width="90px">
        <el-form-item label="分支名称"><el-input v-model="createName" maxlength="160" placeholder="例如：上海分支" /></el-form-item>
      </el-form>
      <div v-if="createdToken" class="cascade-token-box">
        <div>接入令牌只显示一次，请立即复制到分支系统：</div>
        <code>{{ createdToken }}</code>
        <el-button size="small" type="primary" plain @click="copyToken">复制令牌</el-button>
      </div>
      <template #footer>
        <el-button @click="createVisible = false">关闭</el-button>
        <el-button v-if="!createdToken" type="primary" :loading="creating" @click="createNode">生成接入令牌</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="detailVisible" :title="detailNode?.name || '分支数据'" size="78%">
      <div v-if="detailNode" class="cascade-detail">
        <div class="cascade-detail-meta">
          <el-tag :type="detailNode.online ? 'success' : 'info'">{{ detailNode.online ? '在线' : '离线' }}</el-tag>
          <span>{{ detailNode.address || '-' }}</span>
          <span>版本 {{ detailNode.version || '-' }}</span>
          <span>同步 {{ formatTime(detailNode.last_sync) || '-' }}</span>
        </div>
        <el-tabs v-model="detailTab">
          <el-tab-pane label="资产" name="assets">
            <el-table :data="detailSnapshot.assets || []" size="small" border max-height="520">
              <el-table-column prop="name" label="设备名称" min-width="160" show-overflow-tooltip />
              <el-table-column prop="ip_address" label="IP" width="130" />
              <el-table-column prop="device_type" label="类型" width="95" />
              <el-table-column prop="vendor" label="厂商" width="110" />
              <el-table-column prop="model" label="型号" min-width="130" show-overflow-tooltip />
              <el-table-column label="CPU" width="80"><template #default="{ row }">{{ percent(row.cpu_usage) }}</template></el-table-column>
              <el-table-column label="内存" width="80"><template #default="{ row }">{{ percent(row.memory_usage) }}</template></el-table-column>
              <el-table-column label="状态" width="90"><template #default="{ row }"><el-tag size="small" :type="row.status === 'online' ? 'success' : 'info'">{{ row.status === 'online' ? '在线' : '未知' }}</el-tag></template></el-table-column>
            </el-table>
          </el-tab-pane>
          <el-tab-pane :label="`告警 ${detailSnapshot.alerts?.length || 0}`" name="alerts">
            <el-table :data="detailSnapshot.alerts || []" size="small" border max-height="520">
              <el-table-column label="级别" width="80"><template #default="{ row }"><el-tag size="small" :type="alertType(row.level)">{{ row.level_label || row.level }}</el-tag></template></el-table-column>
              <el-table-column prop="device_name" label="设备" min-width="150" />
              <el-table-column prop="type_label" label="类型" width="120" />
              <el-table-column prop="message" label="告警原因" min-width="300" show-overflow-tooltip />
              <el-table-column label="时间" width="160"><template #default="{ row }">{{ formatTime(row.created_at) }}</template></el-table-column>
            </el-table>
          </el-tab-pane>
          <el-tab-pane label="虚拟化 / 巡检" name="other">
            <el-descriptions :column="3" border class="cascade-descriptions">
              <el-descriptions-item label="虚拟化平台">{{ detailSnapshot.virtualization?.platforms || 0 }}</el-descriptions-item>
              <el-descriptions-item label="虚拟机/容器">{{ detailSnapshot.virtualization?.vms || 0 }}</el-descriptions-item>
              <el-descriptions-item label="虚拟化告警">{{ detailSnapshot.virtualization?.alerts || 0 }}</el-descriptions-item>
              <el-descriptions-item label="巡检任务">{{ detailSnapshot.inspection?.tasks || 0 }}</el-descriptions-item>
              <el-descriptions-item label="巡检报告">{{ detailSnapshot.inspection?.reports || 0 }}</el-descriptions-item>
              <el-descriptions-item label="站点">{{ detailSnapshot.websites?.length || 0 }}</el-descriptions-item>
            </el-descriptions>
          </el-tab-pane>
        </el-tabs>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { cascadeApi } from '@/api'
import { formatDateTime } from '@/utils/time'

const loading = ref(false)
const role = ref('standalone')
const nodes = ref([])
const summary = ref({})
const tunnel = reactive({ online: false, connected: false, last_error: '' })
const route = useRoute()
const activeTab = ref(route.query.tab === 'chat' ? 'chat' : 'nodes')
const configForm = reactive({ enabled: false, role: 'standalone', node_name: '', hq_url: '', token: '', has_token: false, sync_interval: 60, verify_tls: true, tunnel_port: 9527 })
const configDirty = ref(false)
const configSaving = ref(false)
const createVisible = ref(false)
const createName = ref('')
const creating = ref(false)
const createdToken = ref('')
const detailVisible = ref(false)
const detailNode = ref(null)
const detailSnapshot = ref({})
const detailTab = ref('assets')
const chatNodeId = ref(null)
const messages = ref([])
const chatInput = ref('')
const sending = ref(false)
const chatRef = ref(null)
let timer = null

const roleLabel = computed(() => ({ hq: '总部节点', branch: '分支节点', standalone: '独立运行' }[role.value] || role.value))
const roleTag = computed(() => ({ hq: 'warning', branch: 'success', standalone: 'info' }[role.value] || 'info'))
const latestSyncText = computed(() => {
  const times = nodes.value.map(n => n.last_sync).filter(Boolean).sort().reverse()
  return times.length ? formatDateTime(times[0]) : '-'
})
const chatNode = computed(() => nodes.value.find(n => n.id === chatNodeId.value) || null)

function percent(value) {
  return value === null || value === undefined ? '-' : `${Number(value).toFixed(1)}%`
}
function formatTime(value) { return value ? formatDateTime(value) : '' }
function alertType(level) { return ({ info: 'info', warning: 'warning', critical: 'danger', emergency: 'danger' }[level] || 'info') }

async function loadAll() {
  loading.value = true
  try {
    const [statusRes, configRes] = await Promise.all([cascadeApi.status(), cascadeApi.getConfig()])
    const data = statusRes.data || {}
    role.value = configDirty.value ? configForm.role : (data.config?.role || 'standalone')
    nodes.value = data.nodes || []
    summary.value = data.summary || {}
    Object.assign(tunnel, data.tunnel || {}, { online: !!data.tunnel?.connected })
    const config = configRes.data?.config || data.config || {}
    if (!configDirty.value) {
      Object.assign(configForm, {
        enabled: !!config.enabled, role: config.role || 'standalone', node_name: config.node_name || '',
        hq_url: config.hq_url || '', token: '', has_token: !!config.has_token,
        sync_interval: Number(config.sync_interval || 60), verify_tls: config.verify_tls !== false,
        tunnel_port: Number(config.tunnel_port || 9527),
      })
    }
    if (!chatNodeId.value && nodes.value.length) chatNodeId.value = nodes.value[0].id
  } catch (e) {
    ElMessage.error(e.message || '级联状态加载失败')
  } finally {
    loading.value = false
  }
}

async function saveConfig() {
  configSaving.value = true
  try {
    const payload = { ...configForm }
    if (!payload.token) delete payload.token
    const res = await cascadeApi.saveConfig(payload)
    Object.assign(configForm, { token: '', has_token: !!res.data?.config?.has_token })
    configDirty.value = false
    ElMessage.success('级联配置已保存，隧道正在重连')
    await loadAll()
  } catch (e) {
    ElMessage.error(e.message || '级联配置保存失败')
  } finally {
    configSaving.value = false
  }
}

function onRoleChange(value) {
  role.value = value
  configDirty.value = true
}

async function removeNode(node) {
  try {
    await ElMessageBox.confirm(
      `确定删除分支“${node.name}”吗？删除后该分支接入令牌立即失效，历史级联消息也会清理。`,
      '删除分支节点',
      { type: 'warning' },
    )
    await cascadeApi.deleteNode(node.id)
    if (chatNodeId.value === node.id) {
      chatNodeId.value = null
      messages.value = []
    }
    if (detailNode.value?.id === node.id) {
      detailVisible.value = false
      detailNode.value = null
    }
    ElMessage.success('分支节点已删除')
    await loadAll()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || '删除分支失败')
  }
}

function openCreate() {
  createVisible.value = true
  createName.value = ''
  createdToken.value = ''
}

async function createNode() {
  if (!createName.value.trim()) return ElMessage.warning('请填写分支名称')
  creating.value = true
  try {
    const res = await cascadeApi.createNode({ name: createName.value.trim() })
    createdToken.value = res.data.token
    await loadAll()
  } catch (e) {
    ElMessage.error(e.message || '登记分支失败')
  } finally {
    creating.value = false
  }
}

async function copyToken() {
  try {
    await navigator.clipboard.writeText(createdToken.value)
    ElMessage.success('接入令牌已复制')
  } catch {
    ElMessage.warning('复制失败，请手动选择令牌')
  }
}

async function openDetail(node) {
  try {
    const res = await cascadeApi.getNode(node.id)
    detailNode.value = res.data
    detailSnapshot.value = res.data.snapshot || {}
    detailTab.value = 'assets'
    detailVisible.value = true
  } catch (e) {
    ElMessage.error(e.message || '加载分支数据失败')
  }
}

function selectChatNode(node) {
  chatNodeId.value = node.id
  loadMessages()
}

async function loadMessages() {
  if (role.value !== 'branch' && !chatNodeId.value) return
  try {
    const params = role.value === 'branch' ? {} : { node_id: chatNodeId.value }
    const res = await cascadeApi.messages(params)
    messages.value = res.data?.items || []
    await nextTick()
    if (chatRef.value) chatRef.value.scrollTop = chatRef.value.scrollHeight
  } catch {
    messages.value = []
  }
}

async function sendChat() {
  const content = chatInput.value.trim()
  if (!content || (role.value !== 'branch' && !chatNodeId.value)) return
  sending.value = true
  try {
    const payload = { content }
    if (role.value !== 'branch') payload.node_id = chatNodeId.value
    const res = await cascadeApi.sendMessage(payload)
    chatInput.value = ''
    ElMessage.success(res.data?.message || '消息已发送')
    await loadMessages()
  } catch (e) {
    ElMessage.error(e.message || '级联消息发送失败')
  } finally {
    sending.value = false
  }
}

onMounted(async () => {
  await loadAll()
  await loadMessages()
  timer = window.setInterval(async () => {
    await loadAll()
    if (activeTab.value === 'chat') await loadMessages()
  }, 10000)
})
onBeforeUnmount(() => { if (timer) window.clearInterval(timer) })
</script>

<style scoped>
.cascade-page { padding: 16px; background: #f5f7fa; min-height: 100%; box-sizing: border-box; }
.cascade-hero { display: flex; justify-content: space-between; align-items: flex-start; gap: 14px; flex-wrap: wrap; padding: 20px; border-radius: 14px; background: linear-gradient(120deg, #102a43, #174a63 55%, #155e75); color: #fff; }
.cascade-eyebrow { color: #8be9e1; font-size: 10px; letter-spacing: .2em; }
.cascade-hero h1 { margin: 5px 0; font-size: 24px; }
.cascade-hero p { margin: 0; color: #b9d8e5; font-size: 12px; }
.cascade-hero-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.cascade-stat-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 14px 0; }
.cascade-stat-grid > div { padding: 14px 16px; background: #fff; border: 1px solid #e2eaf2; border-radius: 10px; }
.cascade-stat-grid span { display: block; color: #7c91a3; font-size: 10px; }
.cascade-stat-grid b { display: block; margin: 3px 0; color: #15364c; font-size: 25px; }
.cascade-stat-grid b.danger { color: #dc2626; }
.cascade-stat-grid b.time { font-size: 14px; line-height: 1.8; }
.cascade-stat-grid small { color: #9aabba; font-size: 10px; }
.cascade-tabs { padding: 14px; background: #fff; border: 1px solid #e2eaf2; border-radius: 12px; }
.cascade-toolbar { display: flex; justify-content: space-between; gap: 10px; align-items: center; margin-bottom: 14px; }
.muted { color: #8b9bab; font-size: 11px; }
.cascade-node-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; }
.cascade-node-card { padding: 14px; border: 1px solid #e6edf4; border-radius: 10px; background: #fbfdff; }
.cascade-node-card.online { border-color: #9de6d8; box-shadow: 0 0 0 2px rgba(15, 118, 110, .06); }
.cascade-node-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }
.cascade-node-head strong { color: #1e3a4f; font-size: 14px; }
.cascade-node-version { margin-left: 6px; color: #8b9bab; font-size: 10px; }
.cascade-status { display: inline-flex; align-items: center; gap: 4px; color: #8b9bab; font-size: 10px; }
.cascade-status i { width: 7px; height: 7px; border-radius: 50%; background: #9ca3af; }
.cascade-node-card.online .cascade-status { color: #0f766e; }
.cascade-node-card.online .cascade-status i { background: #10b981; box-shadow: 0 0 7px #10b981; }
.cascade-node-address { margin: 5px 0 10px; color: #8b9bab; font-size: 10px; }
.cascade-node-stats { display: flex; gap: 20px; padding: 8px 0; border-top: 1px solid #eef3f7; border-bottom: 1px solid #eef3f7; }
.cascade-node-stats b { color: #1e3a4f; font-size: 18px; }
.cascade-node-stats b.danger { color: #dc2626; }
.cascade-node-stats span { display: block; color: #9aabba; font-size: 9px; }
.cascade-node-foot { display: flex; justify-content: space-between; align-items: center; margin-top: 8px; color: #99a9b6; font-size: 9px; }
.cascade-node-actions { display: flex; align-items: center; gap: 2px; }
.cascade-chat-layout { display: grid; grid-template-columns: 220px minmax(0, 1fr); min-height: 480px; border: 1px solid #e7eef5; border-radius: 10px; overflow: hidden; }
.cascade-chat-side { padding: 10px; background: #fbfdff; border-right: 1px solid #e7eef5; }
.cascade-chat-side-title { margin: 3px 5px 8px; color: #8b9bab; font-size: 10px; }
.cascade-chat-node { width: 100%; display: flex; justify-content: space-between; gap: 6px; padding: 9px 8px; margin-bottom: 3px; border: 0; border-radius: 6px; background: transparent; color: #334e63; font-size: 11px; text-align: left; cursor: pointer; }
.cascade-chat-node:hover, .cascade-chat-node.active { background: #e9f8f5; color: #0f766e; }
.cascade-chat-node i { display: inline-block; width: 6px; height: 6px; margin-right: 5px; border-radius: 50%; background: #9ca3af; }
.cascade-chat-node i.online { background: #10b981; }
.cascade-chat-node small { color: #9aabba; font-size: 9px; }
.cascade-chat-main { display: flex; flex-direction: column; min-width: 0; }
.cascade-chat-head { display: flex; justify-content: space-between; align-items: baseline; padding: 12px 14px; border-bottom: 1px solid #eef3f7; }
.cascade-chat-head strong { color: #1e3a4f; font-size: 13px; }
.cascade-chat-head small { color: #9aabba; font-size: 9px; }
.cascade-messages { flex: 1; min-height: 320px; max-height: 500px; overflow: auto; padding: 14px; background: #fbfdff; }
.cascade-message { margin-bottom: 10px; }
.cascade-message.from-hq { text-align: right; }
.cascade-message-meta { color: #99a9b6; font-size: 9px; }
.cascade-message-body { display: inline-block; max-width: 80%; margin-top: 3px; padding: 8px 10px; border-radius: 8px; background: #fff; border: 1px solid #e5edf4; color: #334e63; font-size: 11px; line-height: 1.7; text-align: left; white-space: pre-wrap; }
.cascade-message.from-hq .cascade-message-body { background: #eefaf7; border-color: #bceee6; }
.cascade-composer { display: flex; gap: 8px; padding: 10px 12px; border-top: 1px solid #eef3f7; }
.cascade-config-form { max-width: 780px; }
.cascade-config-form .el-alert { margin-bottom: 18px; }
.form-hint { margin-left: 10px; color: #8b9bab; font-size: 10px; }
.cascade-hq-tip { margin-top: 6px; padding: 12px; border-radius: 8px; background: #f5fbfa; color: #507a75; font-size: 11px; }
.cascade-token-box { margin-top: 12px; padding: 12px; border: 1px solid #bceee6; border-radius: 8px; background: #f2fcf9; color: #0f766e; font-size: 11px; }
.cascade-token-box code { display: block; margin: 8px 0; padding: 8px; word-break: break-all; background: #fff; border-radius: 5px; color: #1e3a4f; font-size: 11px; }
.cascade-detail-meta { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; padding-bottom: 12px; color: #70879a; font-size: 11px; }
.cascade-descriptions { margin-top: 10px; }
@media (max-width: 900px) { .cascade-page { padding: 8px; } .cascade-stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .cascade-chat-layout { grid-template-columns: 1fr; } .cascade-chat-side { display: flex; gap: 5px; overflow: auto; border-right: 0; border-bottom: 1px solid #e7eef5; } .cascade-chat-side-title { display: none; } .cascade-chat-node { min-width: 130px; } }
</style>
