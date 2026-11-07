<template>
  <div class="license-view">
    <div class="license-head">
      <div>
        <div class="license-title"><el-icon><Key /></el-icon>授权信息</div>
        <div class="license-sub">商业授权、机器绑定与授权签发平台 v{{ platformVersion }}</div>
      </div>
      <div class="license-head-actions">
        <el-button :loading="loading" @click="loadLicense">
          <el-icon><Refresh /></el-icon>刷新
        </el-button>
      </div>
    </div>

    <el-alert
      v-if="status.status === 'licensed'"
      type="success"
      :closable="false"
      show-icon
      :title="`商业版授权有效：${status.licensee}`"
      :description="`授权资产上限 ${status.max_assets} 台，集群节点上限 ${status.max_nodes ?? 1} 个，当前已使用 ${status.assets_used} 台。`"
      class="license-alert"
    />
    <el-alert
      v-else-if="status.status === 'opensource'"
      type="info"
      :closable="false"
      show-icon
      title="开源版 · 永久使用"
      :description="`资产上限 ${status.max_assets} 台；永久使用，全部功能可用。`"
      class="license-alert"
    />
    <el-alert
      v-else
      type="error"
      :closable="false"
      show-icon
      :title="status.status === 'expired' ? '授权已到期' : (status.status === 'invalid' ? '授权无效' : '授权不可用')"
      :description="status.message"
      class="license-alert"
    />
    <el-alert
      v-if="licenseExpiringSoon"
      type="warning"
      :closable="false"
      show-icon
      :title="`授权将在 ${status.days_left} 天后到期`"
      description="到期后系统将禁止登录和管理界面访问；后台采集和历史数据保留，请提前续期并更新授权文件。"
      class="license-alert"
    />

    <el-card class="license-card restriction-card">
      <div class="restriction-head">
        <div class="card-title">
          <span>授权到期后的功能限制</span>
          <el-tag :type="restrictionInfo.type" effect="plain">{{ restrictionInfo.label }}</el-tag>
        </div>
        <p>{{ restrictionInfo.intro }}</p>
      </div>
      <div class="restriction-columns">
        <div class="restriction-group blocked">
          <div class="restriction-title"><el-icon><CircleCloseFilled /></el-icon>到期后受限</div>
          <div class="restriction-row">
            <strong>登录系统</strong>
            <span>账号密码登录直接拒绝，已有会话也失效</span>
          </div>
          <div class="restriction-row">
            <strong>管理界面访问</strong>
            <span>除授权续期接口外，所有已登录 API 返回到期提示</span>
          </div>
          <div class="restriction-row">
            <strong>新增资产</strong>
            <span>单台新增、批量导入、自动发现入库均被拦截</span>
          </div>
        </div>
        <div class="restriction-group allowed">
          <div class="restriction-title"><el-icon><CircleCheckFilled /></el-icon>不受影响</div>
          <div class="restriction-row">
            <strong>后台采集任务</strong>
            <span>采集与告警任务继续运行，数据保留在数据库中</span>
          </div>
          <div class="restriction-row">
            <strong>历史数据保留</strong>
            <span>资产、告警、拓扑和历史记录不会被删除</span>
          </div>
          <div class="restriction-row">
            <strong>服务器侧续期</strong>
            <span>替换 data/license.key 后即可恢复登录和使用</span>
          </div>
        </div>
      </div>
      <div class="restriction-note">
        授权到期后管理界面整体不可用，但不会删除已有资产或停止后台采集；替换有效授权文件后立即恢复登录。
      </div>
    </el-card>

    <div class="license-grid">
      <el-card class="license-card">
        <template #header>
          <div class="card-title"><span>授权概览</span><el-tag :type="statusType" effect="plain">{{ statusLabel }}</el-tag></div>
        </template>
        <div class="license-status-line">
          <div class="license-mark" :class="status.status">
            <el-icon><CircleCheckFilled v-if="['licensed','opensource'].includes(status.status)" /><WarningFilled v-else /></el-icon>
          </div>
          <div>
            <strong>{{ ['licensed','opensource'].includes(status.status) ? status.licensee : '授权不可用' }}</strong>
            <span>{{ ['licensed','opensource'].includes(status.status) ? `${status.edition_label || status.edition || '商业版'} · ${status.edition || 'commercial'}` : status.message }}</span>
          </div>
        </div>
        <div class="license-facts">
          <div><span>资产使用</span><b>{{ status.assets_used }} / {{ status.max_assets || 0 }} 台</b></div>
          <div><span>集群节点上限</span><b>{{ status.max_nodes ?? 1 }} 个</b></div>
          <div><span>剩余额度</span><b>{{ status.assets_remaining ?? 0 }} 台</b></div>
          <div><span>授权客户</span><b>{{ status.licensee || '-' }}</b></div>
          <div><span>授权版本</span><b>{{ status.edition_label || status.edition || '-' }}</b></div>
          <div><span>授权费用</span><b>{{ priceLabel }}</b></div>
          <div><span>授权周期</span><b>{{ status.expires_at ? '按授权有效期' : '永久' }}</b></div>
          <div><span>授权产品版本</span><b>{{ status.product_version || '-' }}</b></div>
          <div><span>系统版本</span><b>{{ versionInfo?.effective?.display_version || '-' }}</b></div>
          <div><span>构建号</span><b>{{ versionInfo?.effective?.build || '-' }}</b></div>
          <div><span>签发时间</span><b>{{ formatDate(status.issued_at) }}</b></div>
          <div><span>到期时间</span><b>{{ status.expires_at ? formatDate(status.expires_at) : '永久' }}</b></div>
          <div><span>授权签发平台</span><b>{{ status.issued_by || '智能运维服务平台授权签发平台' }}</b></div>
          <div><span>签发平台版本</span><b>v{{ platformVersion }}</b></div>
        </div>
        <div class="license-progress-label">
          <span>资产额度使用</span>
          <span :class="{ danger: status.assets_used >= status.max_assets }">{{ usagePercent }}%</span>
        </div>
        <el-progress :percentage="usagePercent" :status="status.assets_used >= status.max_assets ? 'exception' : undefined" :stroke-width="8" />
        <div v-if="status.features_detail?.length" class="license-features">
          <div class="license-features-title">授权功能模块（{{ status.features_detail.length }} 项）</div>
          <div class="license-feature-tags">
            <el-tag v-for="feature in status.features_detail" :key="feature.key" size="small" effect="plain">
              {{ feature.name }}
            </el-tag>
          </div>
          <div class="license-features-note">系统更新不纳入授权功能模块管控范围。</div>
        </div>
        <div v-if="status.over_limit" class="license-over">当前资产已超过授权数量，新增资产会被拦截，请升级授权或删除无用资产。</div>
      </el-card>

      <el-card class="license-card">
        <template #header>
          <div class="card-title"><span>机器码与有效期</span><el-tag type="info" effect="plain">机器绑定</el-tag></div>
        </template>
        <div class="machine-label">本机机器码</div>
        <div class="machine-code">
          <span>{{ status.machine_code || '-' }}</span>
          <el-button link :disabled="!status.machine_code" @click="copyMachineCode">
            <el-icon><CopyDocument /></el-icon>复制
          </el-button>
        </div>
        <div class="machine-tip">授权文件绑定此机器码，复制到其他机器、修改授权内容或伪造签名都会导致授权无效。</div>
        <div class="license-renew">
          <span>到期时间</span>
          <b>{{ status.expires_at ? formatDate(status.expires_at) : '永久有效' }}</b>
        </div>
        <div v-if="status.expires_at" class="license-renew">
          <span>剩余有效期</span>
          <b>{{ status.days_left ?? 0 }} 天</b>
        </div>
        <div class="license-renew">
          <span>授权文件</span>
          <b>{{ status.status === 'opensource' ? '开源版（永久）' : (status.status === 'licensed' ? '商业版（永久/已加载）' : '校验失败') }}</b>
        </div>
        <el-button
          v-if="status.status === 'licensed' && canActivate"
          class="license-remove"
          type="danger"
          plain
          size="small"
          @click="removeLicense"
        >移除授权</el-button>
      </el-card>
    </div>

    <el-card class="license-card license-activate-card">
      <template #header>
        <div class="card-title"><span>激活 / 更换授权</span><el-tag type="warning" effect="plain">需管理员权限</el-tag></div>
      </template>
      <div class="activate-tip">
        将销售方提供的授权码粘贴到下方，或导入授权文件。授权码使用 Ed25519 数字签名校验，无法通过修改页面或本地文件绕过资产限制。
      </div>
      <el-input
        v-model="licenseToken"
        type="textarea"
        :rows="5"
        resize="none"
        placeholder="粘贴授权码，例如：eyJ2ZXJzaW9uIjoxLC...（完整一行）"
        :disabled="!canActivate || activating"
      />
      <div class="activate-actions">
        <input ref="fileRef" type="file" accept=".key,.lic,.txt" class="license-file" @change="readLicenseFile" />
        <el-button :disabled="!canActivate || activating" @click="fileRef?.click()">
          <el-icon><Upload /></el-icon>导入授权文件
        </el-button>
        <el-button type="primary" :loading="activating" :disabled="!canActivate || !licenseToken.trim()" @click="activate">
          <el-icon><Key /></el-icon>激活授权
        </el-button>
        <span class="activate-note">重新激活会覆盖当前授权文件</span>
      </div>
    </el-card>

    <div class="license-security">
      <el-icon><Lock /></el-icon>
      <div>
        <strong>授权安全说明</strong>
        <p>系统只内置 Ed25519 公钥，私钥由销售方离线保存；资产上限在新增资产、批量导入、自动发现写库时由后端统一校验，不依赖前端显示。纯 Python 应用无法做到绝对防反编译，正式销售建议配合 Nuitka/PyArmor 编译保护及离线私钥保管。</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { licenseApi, settingsApi } from '@/api'
import { currentUser } from '@/store/auth'

const status = ref({
  status: 'opensource',
  licensed: false,
  trial: false,
  max_assets: 0,
  assets_used: 0,
  assets_remaining: 0,
  licensee: '',
  edition: '',
  expires_at: null,
  days_left: null,
  machine_code: '',
  message: '',
  over_limit: false,
})
const loading = ref(false)
const activating = ref(false)
const licenseToken = ref('')
const fileRef = ref(null)
const versionInfo = ref(null)
const canActivate = computed(() => currentUser.value?.is_superuser === true)
const statusLabel = computed(() => ({ licensed: '已授权', opensource: '开源版', invalid: '授权无效', expired: '已过期' }[status.value.status] || '未授权'))
const statusType = computed(() => ({ licensed: 'success', opensource: 'info', invalid: 'danger', expired: 'danger' }[status.value.status] || 'info'))
const priceLabel = computed(() => {
  if (status.value.price_text) return status.value.price_text
  if (status.value.status === 'opensource') return '免费'
  return status.value.price === null || status.value.price === undefined ? '-' : `¥${status.value.price}`
})
const usagePercent = computed(() => {
  const limit = Number(status.value.max_assets) || 0
  if (!limit) return 100
  return Math.min(100, Math.round((Number(status.value.assets_used) || 0) / limit * 100))
})
const platformVersion = computed(() => status.value.platform_version || '2.6.0')
const licenseExpiringSoon = computed(() => (
  status.value.status === 'licensed'
  && status.value.days_left !== null
  && status.value.days_left <= 30
))
const restrictionInfo = computed(() => {
  if (status.value.status === 'licensed') {
    return {
      label: '当前有效',
      type: 'success',
      intro: '当前授权有效，以下限制仅在授权到期后生效。到期后将禁止登录和管理界面访问。',
    }
  }
  if (status.value.status === 'opensource') {
    return {
      label: '开源版',
      type: 'info',
      intro: `当前为开源版，永久使用，资产上限 ${status.value.max_assets} 台；全部功能可用。`,
    }
  }
  if (status.value.status === 'expired') {
    return {
      label: '已到期',
      type: 'danger',
      intro: '授权已到期，系统已禁止登录和管理界面访问；后台采集与历史数据保留，替换授权文件后恢复。',
    }
  }
  return {
    label: '授权无效',
    type: 'danger',
    intro: '授权校验失败，新增资产类操作会被限制；请检查机器码或联系销售方重新签发授权。',
  }
})

async function loadLicense() {
  loading.value = true
  try {
    const [{ data }, versionResult] = await Promise.all([
      licenseApi.info(),
      settingsApi.version().catch(() => ({ data: null })),
    ])
    status.value = data
    versionInfo.value = versionResult.data
  } catch (error) {
    ElMessage.error(error.message || '加载授权信息失败')
  } finally {
    loading.value = false
  }
}

function formatDate(value) {
  if (!value) return '-'
  const text = String(value)
  if (/^\d{4}-\d{2}-\d{2}/.test(text)) return text.slice(0, 10).replace(/-/g, '/')
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString('zh-CN')
}

async function copyMachineCode() {
  const text = String(status.value.machine_code || '').trim()
  if (!text) return
  let copied = false
  // Clipboard API 只在 HTTPS 或 localhost 安全上下文可用；
  // 通过局域网 HTTP 访问时主动走 textarea + execCommand 兼容方案。
  if (window.isSecureContext && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text)
      copied = true
    } catch {
      copied = false
    }
  }
  if (!copied) copied = fallbackCopyText(text)
  if (copied) {
    ElMessage.success('机器码已复制')
  } else {
    ElMessage.warning('复制失败，请手动选择机器码')
  }
}

function fallbackCopyText(text) {
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.cssText = 'position:fixed;top:0;left:0;width:1px;height:1px;padding:0;border:0;opacity:0;'
  document.body.appendChild(textarea)
  textarea.focus()
  textarea.select()
  textarea.setSelectionRange(0, text.length)
  let copied = false
  try {
    copied = document.execCommand('copy')
  } catch {
    copied = false
  }
  document.body.removeChild(textarea)
  return copied
}

function readLicenseFile(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  if (file.size > 256 * 1024) {
    ElMessage.warning('授权文件过大')
    return
  }
  const reader = new FileReader()
  reader.onload = () => {
    licenseToken.value = String(reader.result || '').trim()
    ElMessage.success('授权文件已读取，请点击「激活授权」')
  }
  reader.readAsText(file)
}

async function activate() {
  if (!licenseToken.value.trim()) return
  try {
    await ElMessageBox.confirm(
      '激活后会覆盖当前授权文件，并以新授权的资产数量与有效期为准。是否继续？',
      '确认激活授权',
      { type: 'warning', confirmButtonText: '确认激活', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  activating.value = true
  try {
    const { data } = await licenseApi.activate(licenseToken.value.trim())
    status.value = data
    licenseToken.value = ''
    ElMessage.success('授权激活成功，正在刷新授权功能菜单')
    setTimeout(() => window.location.reload(), 900)
  } catch (error) {
    ElMessage.error(error.message || '授权激活失败')
  } finally {
    activating.value = false
  }
}

async function removeLicense() {
  try {
    await ElMessageBox.confirm(
      '移除授权后将恢复开源版，资产上限 50 台，全部功能可用。是否继续？',
      '移除商业授权',
      { type: 'warning', confirmButtonText: '确认移除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    const { data } = await licenseApi.deactivate()
    status.value = data
    ElMessage.success('授权已移除，已恢复开源版，正在刷新授权功能菜单')
    setTimeout(() => window.location.reload(), 900)
  } catch (error) {
    ElMessage.error(error.message || '移除授权失败')
  }
}

onMounted(loadLicense)
</script>

<style scoped>
.license-view { display: flex; flex-direction: column; gap: 14px; min-height: calc(100vh - 155px); }
.license-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.license-title { display: flex; align-items: center; gap: 8px; color: #1f3a50; font-size: 19px; font-weight: 700; }
.license-title .el-icon { color: #0ea5e9; }
.license-sub { margin-top: 5px; color: #8aa0b1; font-size: 12px; }
.license-head-actions .el-button { min-height: 34px; }
.license-alert { border-radius: 9px; }
.restriction-card :deep(.el-card__body) { padding: 16px 18px; }
.restriction-head .card-title { margin-bottom: 5px; }
.restriction-head p { margin: 0 0 13px; color: #7d96a8; font-size: 11px; line-height: 1.6; }
.restriction-columns { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.restriction-group { padding: 12px 13px; border-radius: 8px; }
.restriction-group.blocked { border: 1px solid #fee2e2; background: #fff8f8; }
.restriction-group.allowed { border: 1px solid #d1fae5; background: #f7fdfa; }
.restriction-title { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; font-size: 12px; font-weight: 600; }
.restriction-group.blocked .restriction-title { color: #b91c1c; }
.restriction-group.allowed .restriction-title { color: #047857; }
.restriction-row { display: flex; align-items: baseline; gap: 7px; padding: 4px 0; }
.restriction-row strong { width: 82px; flex-shrink: 0; color: #38566b; font-size: 11px; font-weight: 600; }
.restriction-row span { color: #8095a6; font-size: 10px; line-height: 1.5; }
.restriction-note { margin-top: 10px; padding-top: 9px; border-top: 1px solid #eef4f8; color: #8ca0af; font-size: 10px; line-height: 1.5; }
.license-grid { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(320px, 0.85fr); gap: 14px; }
.license-card { border-radius: 11px; }
.license-card :deep(.el-card__header) { padding: 13px 17px; }
.license-card :deep(.el-card__body) { padding: 17px; }
.card-title { display: flex; align-items: center; justify-content: space-between; color: #24425b; font-size: 14px; font-weight: 600; }
.license-status-line { display: flex; align-items: center; gap: 11px; padding: 4px 0 15px; border-bottom: 1px solid #eef4f8; }
.license-mark { width: 42px; height: 42px; display: flex; align-items: center; justify-content: center; border-radius: 11px; font-size: 22px; }
.license-mark.licensed { color: #059669; background: #ecfdf5; }
.license-mark.trial { color: #d97706; background: #fffbeb; }
.license-mark.invalid, .license-mark.expired { color: #dc2626; background: #fef2f2; }
.license-status-line strong { display: block; color: #24425b; font-size: 15px; }
.license-status-line span { display: block; margin-top: 3px; color: #8aa0b1; font-size: 11px; }
.license-facts { display: grid; grid-template-columns: 1fr 1fr; gap: 12px 18px; padding: 15px 0 5px; }
.license-facts span { display: block; color: #92a6b5; font-size: 10px; }
.license-facts b { display: block; margin-top: 4px; color: #2d4a60; font-family: Consolas, 'Microsoft YaHei', sans-serif; font-size: 13px; }
.license-features { margin-top: 12px; padding-top: 12px; border-top: 1px dashed #e2ebf3; }
.license-features-title { margin-bottom: 8px; color: #49657a; font-size: 11px; font-weight: 600; }
.license-feature-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.license-features-note { margin-top: 8px; color: #90a5b5; font-size: 10px; line-height: 1.5; }
.license-progress-label { display: flex; justify-content: space-between; margin: 8px 0 6px; color: #8198aa; font-size: 10px; }
.license-progress-label .danger { color: #dc2626; font-weight: 600; }
.license-over { margin-top: 9px; color: #dc2626; font-size: 10px; line-height: 1.5; }
.machine-label { color: #92a6b5; font-size: 10px; }
.machine-code { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 6px; padding: 10px 11px; border: 1px dashed #bcdbea; border-radius: 7px; background: #f6fbfe; }
.machine-code span { color: #17617f; font-family: Consolas, monospace; font-size: 12px; font-weight: 600; letter-spacing: .4px; word-break: break-all; }
.machine-code .el-button { flex-shrink: 0; font-size: 11px; }
.machine-tip { margin-top: 8px; color: #8da2b2; font-size: 10px; line-height: 1.6; }
.license-renew { display: flex; justify-content: space-between; gap: 10px; margin-top: 11px; padding-top: 10px; border-top: 1px solid #eef4f8; color: #8da2b2; font-size: 11px; }
.license-renew b { color: #38566b; font-weight: 500; }
.license-remove { margin-top: 14px; }
.license-activate-card :deep(.el-textarea__inner) { min-height: 98px !important; font-family: Consolas, monospace; font-size: 11px; line-height: 1.6; }
.activate-tip { margin-bottom: 12px; color: #718b9d; font-size: 11px; line-height: 1.7; }
.activate-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.activate-note { color: #a0b1be; font-size: 10px; }
.license-file { display: none; }
.license-security { display: flex; gap: 10px; padding: 14px 16px; border: 1px solid #dbe9f3; border-radius: 10px; background: #f7fbfd; color: #8299aa; }
.license-security > .el-icon { flex-shrink: 0; margin-top: 2px; color: #0ea5e9; font-size: 18px; }
.license-security strong { color: #45657b; font-size: 12px; }
.license-security p { margin: 5px 0 0; font-size: 10px; line-height: 1.7; }
@media (max-width: 1000px) {
  .license-grid { grid-template-columns: 1fr; }
  .restriction-columns { grid-template-columns: 1fr; }
}
</style>
