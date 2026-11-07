<template>
  <div class="cert-page">
    <el-card class="cert-shell">
      <template #header>
        <div class="cert-head">
          <div>
            <div class="cert-title"><el-icon><Key /></el-icon>证书管理</div>
            <div class="cert-sub">证书监控 · 免费证书申请 · 自动生成 PEM · 证书托管 · IP 证书导入</div>
          </div>
          <div class="cert-actions">
            <el-button size="small" @click="$router.push('/website')">返回网站监控</el-button>
            <el-button size="small" :loading="refreshingAll" @click="refreshAll">
              <el-icon><Refresh /></el-icon>刷新监控
            </el-button>
            <el-button size="small" @click="openGenerate">
              <el-icon><MagicStick /></el-icon>自动生成证书
            </el-button>
            <el-button size="small" @click="openImport">
              <el-icon><Upload /></el-icon>导入/托管证书
            </el-button>
            <el-button type="primary" size="small" @click="openApply">
              <el-icon><Plus /></el-icon>申请免费证书
            </el-button>
          </div>
        </div>
      </template>

      <div v-if="!certbotAvailable" class="certbot-panel">
        <el-alert
          class="cert-notice"
          type="warning"
          :closable="false"
          show-icon
          title="服务器未安装 certbot，暂时不能在线申请 Let's Encrypt 免费证书"
          :description="certbotInstallTip"
        />
        <div class="certbot-install-actions">
          <el-button
            v-if="certbotInfo?.can_install && currentUser?.is_superuser"
            type="primary"
            size="small"
            :loading="installingCertbot"
            @click="installCertbot"
          >自动安装 certbot</el-button>
          <el-button size="small" :loading="certbotInfoLoading" @click="loadCertbotStatus">重新检测系统</el-button>
          <span v-if="certbotInfo?.install_commands?.length" class="certbot-command-hint">
            手动安装：{{ certbotInfo.install_commands.join(' && ') }}
          </span>
        </div>
        <pre v-if="certbotInstallOutput" class="certbot-install-output">{{ certbotInstallOutput }}</pre>
      </div>

      <div class="cert-stats">
        <div class="cert-stat total"><span>全部证书</span><strong>{{ summary.total || 0 }}</strong></div>
        <div class="cert-stat valid"><span>有效</span><strong>{{ summary.valid || 0 }}</strong></div>
        <div class="cert-stat expiring"><span>即将到期</span><strong>{{ summary.expiring || 0 }}</strong></div>
        <div class="cert-stat expired"><span>已过期</span><strong>{{ summary.expired || 0 }}</strong></div>
        <div class="cert-stat error"><span>读取异常</span><strong>{{ summary.error || 0 }}</strong></div>
        <div class="cert-stat auto"><span>自动续期</span><strong>{{ summary.auto_renew || 0 }}</strong></div>
      </div>

      <div class="cert-toolbar">
        <el-input
          v-model="filters.search"
          size="small"
          clearable
          placeholder="证书名称 / 域名 / IP / 颁发者"
          class="cert-search"
          @keyup.enter="load"
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-select v-model="filters.status" size="small" clearable placeholder="全部状态" class="cert-filter" @change="load">
          <el-option label="有效" value="valid" />
          <el-option label="即将到期" value="expiring" />
          <el-option label="已过期" value="expired" />
          <el-option label="读取异常" value="error" />
        </el-select>
        <el-select v-model="filters.cert_type" size="small" clearable placeholder="全部类型" class="cert-filter" @change="load">
          <el-option label="域名证书" value="domain" />
          <el-option label="IP 证书" value="ip" />
        </el-select>
        <el-select v-model="filters.source" size="small" clearable placeholder="全部来源" class="cert-filter" @change="load">
          <el-option label="免费申请" value="acme" />
          <el-option label="导入托管" value="import" />
          <el-option label="自动生成" value="generated" />
        </el-select>
        <el-button size="small" type="primary" @click="load">查询</el-button>
        <span class="cert-toolbar-tip">证书按主域名/IP 集中托管，私钥仅超级管理员可下载</span>
      </div>

      <el-table v-loading="loading" :data="items" class="cert-table" empty-text="暂无证书，请申请或导入证书">
        <el-table-column label="证书" min-width="190">
          <template #default="{ row }">
            <div class="cert-name-cell">
              <strong>{{ row.name }}</strong>
              <span>{{ row.primary_host }}<template v-if="row.san.length > 1"> 等 {{ row.san.length }} 个 SAN</template></span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="82">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" :type="row.cert_type === 'ip' ? 'warning' : 'info'">
              {{ row.cert_type === 'ip' ? 'IP' : '域名' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="94">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" :type="sourceTag(row.source)">
              {{ sourceLabel(row.source) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="issuer" label="颁发者" min-width="150" show-overflow-tooltip />
        <el-table-column label="到期时间" width="135">
          <template #default="{ row }">
            <div class="cert-date-cell">
              <span>{{ formatDate(row.valid_to) }}</span>
              <el-tag size="small" :type="statusTag(row.status)">{{ daysText(row) }}</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="96">
          <template #default="{ row }">
            <el-tag size="small" :type="statusTag(row.status)">{{ row.status_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="自动续期" width="86">
          <template #default="{ row }">
            <el-tag v-if="row.auto_renew" size="small" type="success" effect="plain">开启</el-tag>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <el-button link size="small" type="primary" @click="openDetail(row)">详情</el-button>
            <el-button link size="small" @click="refreshOne(row)">刷新</el-button>
            <el-button link size="small" @click="download(row, 'fullchain')">下载</el-button>
            <el-button v-if="row.source === 'acme'" link size="small" @click="renew(row)">续期</el-button>
            <el-button link size="small" type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 免费证书申请 -->
    <el-dialog v-model="applyVisible" title="申请免费证书" width="620px" :close-on-click-modal="false">
      <el-alert
        class="dialog-notice"
        type="info"
        :closable="false"
        show-icon
        title="通过 Let's Encrypt + certbot 申请，使用 HTTP-01 验证"
        description="域名必须解析到本机，且 80 端口可被公网访问。公网 CA 通常不签发 IP 证书；IP 证书请使用「导入/托管证书」。通配符和 DNS-01 暂不支持。"
      />
      <el-form :model="applyForm" label-width="105px">
        <el-form-item label="域名" required>
          <el-input
            v-model="applyForm.domains"
            type="textarea"
            :rows="2"
            placeholder="example.com,www.example.com"
          />
          <div class="form-tip">多个域名用逗号或换行分隔，最多 20 个，不要填 https://</div>
        </el-form-item>
        <el-form-item label="通知邮箱" required>
          <el-input v-model="applyForm.email" placeholder="ops@example.com" />
        </el-form-item>
        <el-form-item label="验证方式">
          <el-select v-model="applyForm.method" style="width:100%">
            <el-option label="Webroot（推荐，需网站目录可写）" value="webroot" />
            <el-option label="Standalone（临时占用 80 端口）" value="standalone" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="applyForm.method === 'webroot'" label="Webroot 目录" required>
          <el-input v-model="applyForm.webroot" placeholder="/var/www/html" />
          <div class="form-tip">certbot 会在该目录写入 .well-known/acme-challenge 验证文件</div>
        </el-form-item>
        <el-form-item label="测试环境">
          <el-switch v-model="applyForm.staging" />
          <span class="form-inline-tip">开启后申请 Let's Encrypt 测试证书，不用于生产</span>
        </el-form-item>
        <el-form-item label="自动续期">
          <el-switch v-model="applyForm.auto_renew" />
          <span class="form-inline-tip">记录 ACME 配置，供证书续期使用</span>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="applyForm.notes" maxlength="500" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="applyVisible = false">取消</el-button>
        <el-button type="primary" :loading="applying" @click="applyCertificate">开始申请</el-button>
      </template>
    </el-dialog>

    <!-- 自动生成自签名证书 -->
    <el-dialog v-model="generateVisible" title="自动生成 PEM 证书" width="640px" :close-on-click-modal="false">
      <el-alert
        class="dialog-notice"
        type="warning"
        :closable="false"
        show-icon
        title="将生成自签名证书和私钥，并自动进入证书托管库"
        description="自签名证书适合内网系统、设备管理、测试环境加密；公共浏览器不会默认信任。公网 HTTPS 请使用「申请免费证书」获取 Let's Encrypt 证书。支持域名和 IP SAN。"
      />
      <el-form :model="generateForm" label-width="105px">
        <el-form-item label="证书名称">
          <el-input v-model="generateForm.name" maxlength="255" placeholder="留空则使用主域名/IP 命名" />
        </el-form-item>
        <el-form-item label="主域名/IP" required>
          <el-input v-model="generateForm.common_name" placeholder="例如：nms.intra 或 192.168.1.10" />
          <div class="form-tip">证书 CN 和默认监控目标</div>
        </el-form-item>
        <el-form-item label="SAN">
          <el-input
            v-model="generateForm.san"
            type="textarea"
            :rows="2"
            placeholder="可选，多个域名/IP 用逗号或换行分隔；例如：nms.intra,192.168.1.10"
          />
          <div class="form-tip">会自动包含主域名/IP，最多 50 个 SAN</div>
        </el-form-item>
        <el-form-item label="密钥类型">
          <el-select v-model="generateForm.key_type" style="width:100%">
            <el-option label="RSA 2048（兼容性最好）" value="rsa2048" />
            <el-option label="RSA 4096" value="rsa4096" />
            <el-option label="ECDSA P-256" value="ec256" />
            <el-option label="ECDSA P-384" value="ec384" />
          </el-select>
        </el-form-item>
        <el-form-item label="有效期">
          <el-input-number v-model="generateForm.valid_days" :min="1" :max="3650" />
          <span class="form-inline-tip">天（最长 3650 天）</span>
        </el-form-item>
        <el-form-item label="组织名称">
          <el-input v-model="generateForm.organization" maxlength="128" placeholder="可选" />
        </el-form-item>
        <el-form-item label="监控主机">
          <el-input v-model="generateForm.monitor_host" placeholder="留空则使用主域名/IP" />
        </el-form-item>
        <el-form-item label="监控端口">
          <el-input-number v-model="generateForm.monitor_port" :min="1" :max="65535" />
        </el-form-item>
        <el-form-item label="提前告警">
          <el-input-number v-model="generateForm.warning_days" :min="1" :max="3650" />
          <span class="form-inline-tip">天</span>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="generateForm.notes" maxlength="500" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="generateVisible = false">取消</el-button>
        <el-button type="primary" :loading="generating" @click="generateCertificate">生成并托管</el-button>
      </template>
    </el-dialog>

    <!-- 导入/托管 -->
    <el-dialog v-model="importVisible" title="导入 / 托管证书" width="620px" :close-on-click-modal="false">
      <div class="import-mode-switch">
        <span>已有证书可在此上传；没有证书也可以自动生成自签名 PEM 证书。</span>
        <el-button link type="primary" size="small" @click="openGenerateFromImport">自动生成 PEM 证书</el-button>
      </div>
      <el-alert
        class="dialog-notice"
        type="info"
        :closable="false"
        show-icon
        title="支持 PEM 域名证书和 IP SAN 证书"
        description="证书和私钥会保存在数据目录，文件权限 600。IP 证书会自动识别 SAN 中的 IP 地址；私钥可选，不上传私钥时只能查看和下载证书。"
      />
      <el-form :model="importForm" label-width="105px">
        <el-form-item label="证书名称">
          <el-input v-model="importForm.name" maxlength="255" placeholder="留空则自动使用主域名/IP" />
        </el-form-item>
        <el-form-item label="证书 PEM" required>
          <div class="file-row">
            <input ref="certFileInput" type="file" accept=".pem,.crt,.cer" hidden @change="pickFile('cert', $event)" />
            <el-button size="small" @click="certFileInput?.click()">选择证书文件</el-button>
            <span class="file-name">{{ importForm.certFile?.name || '未选择' }}</span>
          </div>
          <div class="form-tip">可包含证书链；也可以只上传叶子证书并单独上传链文件</div>
        </el-form-item>
        <el-form-item label="私钥 PEM">
          <div class="file-row">
            <input ref="keyFileInput" type="file" accept=".pem,.key" hidden @change="pickFile('key', $event)" />
            <el-button size="small" @click="keyFileInput?.click()">选择私钥文件</el-button>
            <span class="file-name">{{ importForm.keyFile?.name || '未选择（可选）' }}</span>
          </div>
          <div class="form-tip">仅支持未加密 PEM 私钥；证书与私钥不匹配会被拒绝</div>
        </el-form-item>
        <el-form-item label="证书链">
          <div class="file-row">
            <input ref="chainFileInput" type="file" accept=".pem,.crt,.cer" hidden @change="pickFile('chain', $event)" />
            <el-button size="small" @click="chainFileInput?.click()">选择链文件</el-button>
            <span class="file-name">{{ importForm.chainFile?.name || '未选择（可选）' }}</span>
          </div>
        </el-form-item>
        <el-form-item label="监控主机">
          <el-input v-model="importForm.monitor_host" placeholder="留空则使用证书主域名/IP" />
        </el-form-item>
        <el-form-item label="监控端口">
          <el-input-number v-model="importForm.monitor_port" :min="1" :max="65535" />
        </el-form-item>
        <el-form-item label="提前告警">
          <el-input-number v-model="importForm.warning_days" :min="1" :max="3650" />
          <span class="form-inline-tip">天</span>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="importForm.notes" maxlength="500" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="importVisible = false">取消</el-button>
        <el-button type="primary" :loading="importing" @click="importCertificate">导入并托管</el-button>
      </template>
    </el-dialog>

    <!-- 详情/设置 -->
    <el-dialog v-model="detailVisible" title="证书详情" width="700px">
      <template v-if="detail">
        <div class="detail-facts">
          <div><span>证书名称</span><b>{{ detail.name }}</b></div>
          <div><span>主域名 / IP</span><b>{{ detail.primary_host }}</b></div>
          <div><span>类型</span><b>{{ detail.cert_type === 'ip' ? 'IP 证书' : '域名证书' }}</b></div>
          <div><span>来源</span><b>{{ sourceLabel(detail.source) }}</b></div>
          <div><span>颁发者</span><b>{{ detail.issuer || '-' }}</b></div>
          <div><span>序列号</span><b>{{ detail.serial_number || '-' }}</b></div>
          <div><span>有效期</span><b>{{ formatDate(detail.valid_from) }} ~ {{ formatDate(detail.valid_to) }}</b></div>
          <div><span>剩余天数</span><b>{{ daysText(detail) }}</b></div>
          <div><span>密钥类型</span><b>{{ detail.key_type || '-' }}</b></div>
          <div><span>签名算法</span><b>{{ detail.signature_algorithm || '-' }}</b></div>
        </div>
        <div class="san-line">
          <span>SAN：</span>
          <el-tag v-for="item in detail.san" :key="item" size="small" effect="plain">{{ item }}</el-tag>
          <span v-if="!detail.san?.length" class="muted">无</span>
        </div>
        <el-alert v-if="detail.last_error" type="error" :closable="false" show-icon :title="detail.last_error" class="dialog-notice" />
        <el-divider content-position="left">监控与续期设置</el-divider>
        <el-form :model="editForm" label-width="100px">
          <el-form-item label="启用监控"><el-switch v-model="editForm.monitor_enabled" /></el-form-item>
          <el-form-item label="监控主机"><el-input v-model="editForm.monitor_host" /></el-form-item>
          <el-form-item label="监控端口"><el-input-number v-model="editForm.monitor_port" :min="1" :max="65535" /></el-form-item>
          <el-form-item label="提前告警"><el-input-number v-model="editForm.warning_days" :min="1" :max="3650" /><span class="form-inline-tip">天</span></el-form-item>
          <el-form-item v-if="detail.source === 'acme'" label="自动续期"><el-switch v-model="editForm.auto_renew" /></el-form-item>
          <el-form-item label="备注"><el-input v-model="editForm.notes" maxlength="500" /></el-form-item>
        </el-form>
        <div class="detail-downloads">
          <span>下载：</span>
          <el-button link type="primary" size="small" @click="download(detail, 'fullchain')">完整证书链</el-button>
          <el-button link type="primary" size="small" @click="download(detail, 'cert')">证书</el-button>
          <el-button link type="primary" size="small" :disabled="!detail.has_chain" @click="download(detail, 'chain')">根链</el-button>
          <el-button link type="primary" size="small" @click="showTrustGuide(detail)">浏览器信任指引</el-button>
          <el-button
            v-if="detail.has_private_key && canDownloadKey"
            link
            type="danger"
            size="small"
            @click="download(detail, 'key')"
          >私钥</el-button>
        </div>
      </template>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
        <el-button type="primary" :loading="savingDetail" @click="saveDetail">保存设置</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { websiteApi } from '@/api'
import { currentUser } from '@/store/auth'

const items = ref([])
const loading = ref(false)
const summary = ref({})
const certbotAvailable = ref(true)
const certbotInfo = ref(null)
const certbotInfoLoading = ref(false)
const installingCertbot = ref(false)
const certbotInstallOutput = ref('')
const certbotInstallTip = computed(() => {
  const info = certbotInfo.value
  if (!info) return '正在检测当前系统与包管理器...'
  if (info.certbot_available) return `certbot 已安装${info.certbot_version ? `（${info.certbot_version}）` : ''}`
  if (!info.is_linux) {
    return `当前系统：${info.platform}。自动安装仅支持 Linux；请手动安装 certbot，或改用证书导入/托管功能。`
  }
  const osName = info.distro_name || info.distro_id || 'Linux'
  if (!info.install_supported) {
    return `当前系统：${osName}。未识别到受支持的包管理器，请手动安装 certbot。`
  }
  return `当前系统：${osName}；包管理器：${info.package_label || info.package_manager || '-'}。${info.message}`
})
const filters = reactive({ search: '', status: '', cert_type: '', source: '' })
const applyVisible = ref(false)
const importVisible = ref(false)
const generateVisible = ref(false)
const detailVisible = ref(false)
const canDownloadKey = computed(() => currentUser.value?.is_superuser === true)
const applying = ref(false)
const importing = ref(false)
const generating = ref(false)
const refreshingAll = ref(false)
const savingDetail = ref(false)
const detail = ref(null)
const certFileInput = ref(null)
const keyFileInput = ref(null)
const chainFileInput = ref(null)

const applyForm = reactive({
  domains: '',
  email: '',
  method: 'webroot',
  webroot: '/var/www/html',
  staging: false,
  auto_renew: true,
  notes: '',
})
const importForm = reactive({
  name: '',
  certFile: null,
  keyFile: null,
  chainFile: null,
  monitor_host: '',
  monitor_port: 443,
  warning_days: 30,
  notes: '',
})
const generateForm = reactive({
  name: '',
  common_name: '',
  san: '',
  key_type: 'rsa2048',
  valid_days: 365,
  organization: '',
  monitor_host: '',
  monitor_port: 443,
  warning_days: 30,
  notes: '',
})
const editForm = reactive({
  monitor_enabled: true,
  monitor_host: '',
  monitor_port: 443,
  warning_days: 30,
  auto_renew: false,
  notes: '',
})

const statusTag = (status) => ({ valid: 'success', expiring: 'warning', expired: 'danger', error: 'danger' }[status] || 'info')
const sourceLabel = (source) => ({ acme: '免费申请', generated: '自动生成', auto_device: '设备自动证书', import: '导入托管' }[source] || '导入托管')
const sourceTag = (source) => ({ acme: 'success', generated: 'warning', auto_device: 'success', import: 'info' }[source] || 'info')
const formatDate = (value) => (value ? String(value).replace('T', ' ').slice(0, 10) : '-')
const daysText = (row) => {
  const days = Number(row?.days_left)
  if (!Number.isFinite(days)) return '-'
  if (days < 0) return `已过期 ${Math.abs(days)} 天`
  return `${days} 天`
}

async function load() {
  loading.value = true
  try {
    const res = await websiteApi.certificates(filters)
    items.value = res.data?.items || []
    summary.value = res.data?.summary || {}
    certbotAvailable.value = res.data?.certbot_available !== false
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '加载证书失败')
  } finally {
    loading.value = false
  }
}

async function loadCertbotStatus() {
  certbotInfoLoading.value = true
  try {
    const res = await websiteApi.certbotStatus()
    certbotInfo.value = res.data || null
    certbotAvailable.value = res.data?.certbot_available === true
  } catch (error) {
    certbotInfo.value = null
  } finally {
    certbotInfoLoading.value = false
  }
}

async function installCertbot() {
  const info = certbotInfo.value
  if (!info?.can_install) return
  try {
    await ElMessageBox.confirm(
      `检测到当前系统为 ${info.distro_name || info.distro_id}，将使用 ${info.package_label || info.package_manager} 自动安装 certbot。需要 root 或免密 sudo 权限，是否继续？`,
      '自动安装 certbot',
      { type: 'warning', confirmButtonText: '开始安装', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  installingCertbot.value = true
  certbotInstallOutput.value = ''
  try {
    const res = await websiteApi.installCertbot()
    certbotInfo.value = res.data || certbotInfo.value
    certbotAvailable.value = res.data?.certbot_available === true
    certbotInstallOutput.value = res.data?.output || ''
    ElMessage.success(res.data?.message || 'certbot 安装完成')
    await load()
  } catch (error) {
    const message = error?.response?.data?.detail || error.message || 'certbot 安装失败'
    certbotInstallOutput.value = message
    ElMessage.error(message)
  } finally {
    installingCertbot.value = false
  }
}

function openApply() {
  applyVisible.value = true
}

function openImport() {
  Object.assign(importForm, {
    name: '', certFile: null, keyFile: null, chainFile: null,
    monitor_host: '', monitor_port: 443, warning_days: 30, notes: '',
  })
  importVisible.value = true
}

function openGenerate() {
  Object.assign(generateForm, {
    name: '',
    common_name: '',
    san: '',
    key_type: 'rsa2048',
    valid_days: 365,
    organization: '',
    monitor_host: '',
    monitor_port: 443,
    warning_days: 30,
    notes: '',
  })
  generateVisible.value = true
}

function openGenerateFromImport() {
  importVisible.value = false
  openGenerate()
}

async function generateCertificate() {
  const commonName = generateForm.common_name.trim()
  if (!commonName) {
    ElMessage.warning('请填写证书主域名或 IP')
    return
  }
  const san = generateForm.san
    .split(/[,\s]+/)
    .map((item) => item.trim())
    .filter(Boolean)
  generating.value = true
  try {
    const res = await websiteApi.generateCertificate({
      name: generateForm.name.trim(),
      common_name: commonName,
      san,
      key_type: generateForm.key_type,
      valid_days: generateForm.valid_days,
      organization: generateForm.organization.trim(),
      monitor_host: generateForm.monitor_host.trim(),
      monitor_port: generateForm.monitor_port,
      warning_days: generateForm.warning_days,
      notes: generateForm.notes,
    })
    ElMessage.success(res.data?.message || 'PEM 证书生成成功')
    generateVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '证书生成失败')
  } finally {
    generating.value = false
  }
}

function pickFile(kind, event) {
  const file = event.target.files?.[0] || null
  event.target.value = ''
  if (kind === 'cert') importForm.certFile = file
  else if (kind === 'key') importForm.keyFile = file
  else importForm.chainFile = file
}

async function applyCertificate() {
  const domains = applyForm.domains.split(/[,\s]+/).map((item) => item.trim()).filter(Boolean)
  if (!domains.length) {
    ElMessage.warning('请填写需要申请的域名')
    return
  }
  if (!applyForm.email.trim()) {
    ElMessage.warning('请填写通知邮箱')
    return
  }
  if (applyForm.method === 'webroot' && !applyForm.webroot.trim()) {
    ElMessage.warning('请填写 Webroot 目录')
    return
  }
  applying.value = true
  try {
    await websiteApi.applyCertificate({
      domains,
      email: applyForm.email.trim(),
      method: applyForm.method,
      webroot: applyForm.webroot.trim(),
      staging: applyForm.staging,
      auto_renew: applyForm.auto_renew,
      notes: applyForm.notes,
    })
    ElMessage.success('免费证书申请成功')
    applyVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '证书申请失败')
  } finally {
    applying.value = false
  }
}

async function importCertificate() {
  if (!importForm.certFile) {
    ElMessage.warning('请选择证书 PEM 文件')
    return
  }
  const form = new FormData()
  form.append('cert_file', importForm.certFile)
  if (importForm.keyFile) form.append('key_file', importForm.keyFile)
  if (importForm.chainFile) form.append('chain_file', importForm.chainFile)
  form.append('name', importForm.name)
  form.append('monitor_host', importForm.monitor_host)
  form.append('monitor_port', String(importForm.monitor_port))
  form.append('warning_days', String(importForm.warning_days))
  form.append('notes', importForm.notes)
  importing.value = true
  try {
    const res = await websiteApi.importCertificate(form)
    ElMessage.success(res.data?.message || '证书导入成功')
    importVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '证书导入失败')
  } finally {
    importing.value = false
  }
}

async function refreshOne(row) {
  try {
    await websiteApi.refreshCertificate(row.id)
    ElMessage.success('证书状态已刷新')
    await load()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '刷新失败')
  }
}

async function refreshAll() {
  refreshingAll.value = true
  try {
    const res = await websiteApi.refreshCertificates()
    ElMessage.success(`证书监控已刷新：成功 ${res.data?.ok ?? 0}，异常 ${res.data?.errors ?? 0}`)
    await load()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '刷新失败')
  } finally {
    refreshingAll.value = false
  }
}

async function renew(row) {
  try {
    await ElMessageBox.confirm(
      `确认续期「${row.name}」？将通过 certbot 重新签发并更新本地托管文件。`,
      '续期证书',
      { type: 'warning', confirmButtonText: '续期', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await websiteApi.renewCertificate(row.id)
    ElMessage.success('证书续期成功')
    await load()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '续期失败')
  }
}

function openDetail(row) {
  detail.value = { ...row }
  Object.assign(editForm, {
    monitor_enabled: row.monitor_enabled,
    monitor_host: row.monitor_host,
    monitor_port: row.monitor_port,
    warning_days: row.warning_days,
    auto_renew: row.auto_renew,
    notes: row.notes,
  })
  detailVisible.value = true
}

async function saveDetail() {
  if (!detail.value) return
  savingDetail.value = true
  try {
    const res = await websiteApi.updateCertificate(detail.value.id, {
      monitor_enabled: editForm.monitor_enabled,
      monitor_host: editForm.monitor_host,
      monitor_port: editForm.monitor_port,
      warning_days: editForm.warning_days,
      auto_renew: detail.value.source === 'acme' ? editForm.auto_renew : false,
      notes: editForm.notes,
    })
    detail.value = res.data?.certificate || detail.value
    ElMessage.success('证书设置已保存')
    await load()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '保存失败')
  } finally {
    savingDetail.value = false
  }
}

function download(row, kind) {
  window.open(websiteApi.certificateDownloadUrl(row.id, kind), '_blank', 'noopener')
}

function showTrustGuide(row) {
  if (!row) return
  const selfSigned = row.source === 'generated' || row.subject === row.issuer
  const lines = [
    `证书：${row.name}（${row.primary_host}）`,
    selfSigned
      ? '当前是自签名证书，浏览器默认不信任。远端/公网 HTTPS 建议改用受信任 CA 证书。'
      : '当前为 CA 签发证书，请确认客户端信任其根证书。',
    '',
    '1. 先下载证书；如果有根链，下载根链中的根证书。',
    '2. Windows：双击证书 → 安装证书 → 本地计算机 → 受信任的根证书颁发机构 → 完成，重启浏览器。',
    '3. macOS：钥匙串访问 → 系统 → 导入 → 双击 → 信任 → 始终信任。',
    '4. Linux：复制根证书到 /usr/local/share/ca-certificates/，执行 update-ca-certificates；Firefox 单独导入。',
    '5. iPhone/iPad：安装描述文件后，到“关于本机 → 证书信任设置”开启完全信任。',
    '6. Android：设置 → 安全 → 加密与凭据 → 安装 CA 证书。',
    '',
    `访问地址必须与证书 SAN 匹配：${(row.san || []).join(', ') || row.primary_host}`,
    '自签名叶子证书不一定能作为根证书被接受；如导入无效，请使用受信任 CA 或由内部 CA 签发的服务器证书。',
  ]
  ElMessageBox.alert(lines.join('\n'), '浏览器信任指引', {
    confirmButtonText: '知道了',
    customClass: 'web-diagnose-message',
  })
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(
      `删除证书「${row.name}」？托管证书和私钥文件会一并删除，且不可恢复。`,
      '删除证书',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await websiteApi.deleteCertificate(row.id)
    ElMessage.success('证书已删除')
    await load()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '删除失败')
  }
}

onMounted(() => {
  load()
  loadCertbotStatus()
})
</script>

<style scoped>
.cert-page { min-height: 100%; }
.cert-shell { border-radius: 12px; }
.cert-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; flex-wrap: wrap; }
.cert-title { display: flex; align-items: center; gap: 8px; color: #1f3b52; font-size: 17px; font-weight: 700; }
.cert-title .el-icon { color: #0ea5e9; }
.cert-sub { margin-top: 5px; color: #8a9dad; font-size: 12px; }
.cert-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.cert-notice { margin-bottom: 0; }
.certbot-panel { margin-bottom: 14px; }
.certbot-install-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 9px;
  margin-top: 8px;
}
.certbot-command-hint {
  color: #8a9dad;
  font-family: Consolas, monospace;
  font-size: 10px;
  overflow-wrap: anywhere;
}
.certbot-install-output {
  max-height: 190px;
  margin: 9px 0 0;
  padding: 9px 11px;
  overflow: auto;
  border: 1px solid #e1eaf1;
  border-radius: 7px;
  background: #f7fafc;
  color: #506778;
  font-family: Consolas, monospace;
  font-size: 10px;
  line-height: 1.5;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.cert-stats { display: grid; grid-template-columns: repeat(6, minmax(90px, 1fr)); gap: 10px; margin-bottom: 16px; }
.cert-stat { padding: 12px 14px; border: 1px solid #e6eef5; border-radius: 9px; background: #f8fbfd; }
.cert-stat span { display: block; color: #879baa; font-size: 11px; }
.cert-stat strong { display: block; margin-top: 5px; color: #24475f; font-size: 22px; line-height: 1.1; }
.cert-stat.valid strong { color: #059669; }
.cert-stat.expiring strong { color: #d97706; }
.cert-stat.expired strong, .cert-stat.error strong { color: #dc2626; }
.cert-stat.auto strong { color: #0284c7; }
.cert-toolbar { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.cert-search { width: 260px; }
.cert-filter { width: 120px; }
.cert-toolbar-tip { margin-left: auto; color: #9aabb8; font-size: 11px; }
.cert-name-cell { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.cert-name-cell strong { color: #27475d; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cert-name-cell span { color: #879eae; font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cert-date-cell { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; }
.cert-date-cell span { color: #334155; font-size: 12px; }
.muted { color: #a7b6c2; }
.dialog-notice { margin-bottom: 16px; }
.import-mode-switch {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  padding: 8px 11px;
  border-radius: 7px;
  background: #f5f9fc;
  color: #70889a;
  font-size: 11px;
}
.form-tip { margin-top: 3px; color: #96a8b6; font-size: 11px; line-height: 1.5; }
.form-inline-tip { margin-left: 8px; color: #96a8b6; font-size: 11px; }
.file-row { display: flex; align-items: center; gap: 9px; min-height: 30px; }
.file-name { max-width: 330px; overflow: hidden; color: #718a9d; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.detail-facts { display: grid; grid-template-columns: 1fr 1fr; gap: 11px 18px; padding: 4px 0 10px; }
.detail-facts span { display: block; color: #92a6b5; font-size: 10px; }
.detail-facts b { display: block; margin-top: 3px; color: #2d4a60; font-size: 12px; word-break: break-all; }
.san-line { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; padding: 10px 0; color: #607b8e; font-size: 11px; }
.detail-downloads { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; padding-top: 6px; color: #7890a2; font-size: 11px; }
@media (max-width: 1100px) {
  .cert-stats { grid-template-columns: repeat(3, 1fr); }
  .cert-toolbar-tip { display: none; }
}
@media (max-width: 700px) {
  .cert-stats { grid-template-columns: repeat(2, 1fr); }
  .cert-search, .cert-filter { width: 100%; }
  .cert-actions { width: 100%; }
}
</style>
