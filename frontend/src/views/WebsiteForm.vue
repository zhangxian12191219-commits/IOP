<template>
  <div class="website-form-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>{{ isEdit ? t('website.editWebsite') : t('website.addWebsite') }}</span>
          <el-button @click="returnToWebsite">{{ t('website.back') }}</el-button>
        </div>
      </template>

      <el-form ref="formRef" :model="form" :rules="rules" label-width="120px" style="max-width: 820px">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="t('website.monitorName')" prop="name">
              <el-input v-model="form.name" :placeholder="t('website.monitorNamePlaceholder')" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('website.monitorType')" prop="monitor_type">
              <el-select v-model="form.monitor_type" style="width: 100%" @change="onTypeChange">
                <el-option :label="t('website.httpProbe')" value="http" />
                <el-option label="HTTPS" value="https" />
                <el-option :label="t('website.tcpProbe')" value="tcp" />
                <el-option label="ICMP Ping" value="ping" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item v-if="form.monitor_type === 'http' || form.monitor_type === 'https'" label="URL" prop="url">
          <el-input v-model="form.url" placeholder="https://www.example.com 或 10.20.0.10" />
          <div class="form-hint">支持域名、IPv4/IPv6 和带端口地址；不填写协议时默认使用 http://</div>
        </el-form-item>

        <template v-else>
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item :label="t('website.hostDomain')" prop="host">
                <el-input v-model="form.host" :placeholder="t('website.hostPlaceholder')" />
              </el-form-item>
            </el-col>
            <el-col v-if="form.monitor_type === 'tcp'" :span="12">
              <el-form-item :label="t('website.port')" prop="port">
                <el-input-number v-model="form.port" :min="1" :max="65535" />
              </el-form-item>
            </el-col>
          </el-row>
        </template>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="t('website.timeoutSeconds')">
              <el-input-number v-model="form.timeout" :min="1" :max="60" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('website.intervalSeconds')">
              <el-input-number v-model="form.check_interval" :min="10" :max="3600" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider content-position="left">告警阈值与级别</el-divider>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="慢响应阈值">
              <el-input-number v-model="form.slow_threshold_ms" :min="100" :max="600000" :step="500" controls-position="right" />
              <span class="field-unit">毫秒</span>
              <div class="form-hint">响应时间超过该值触发「响应缓慢」告警</div>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="检测超时">
              <span class="readonly-value">{{ form.timeout }} 秒</span>
              <div class="form-hint">请求超过超时时间判定为检测失败</div>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="检测失败级别">
              <el-select v-model="form.down_level" style="width: 100%">
                <el-option v-for="item in alertLevels" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="响应缓慢级别">
              <el-select v-model="form.slow_level" style="width: 100%">
                <el-option v-for="item in alertLevels" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="失败级别名称">
              <el-input v-model="form.down_level_label" maxlength="50" placeholder="留空使用标准级别名称" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="缓慢级别名称">
              <el-input v-model="form.slow_level_label" maxlength="50" placeholder="例如：业务延迟" />
            </el-form-item>
          </el-col>
        </el-row>
        <div class="alert-level-hint">
          告警声音会根据最终级别播放：提示单音、警告双音、严重三连音、紧急急促交替音。
        </div>

        <template v-if="form.monitor_type === 'http' || form.monitor_type === 'https'">
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item :label="t('website.httpMethod')">
                <el-select v-model="form.method" style="width: 100%">
                  <el-option label="GET" value="GET" />
                  <el-option label="HEAD" value="HEAD" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="t('website.expectedStatusCode')">
                <el-input-number v-model="form.expected_status" :min="100" :max="599" />
              </el-form-item>
            </el-col>
          </el-row>

          <el-form-item :label="t('website.expectedKeyword')">
            <el-input v-model="form.expected_keywords" :placeholder="t('website.keywordsPlaceholder')" />
          </el-form-item>

          <el-divider content-position="left">状态码、HTTPS 与缓存</el-divider>
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item label="允许状态码">
                <el-input v-model="form.expected_statuses" placeholder="例如 200,301-399；留空使用单个状态码" />
                <div class="form-hint">支持逗号分隔和区间；填写后优先于上方单个期望状态码</div>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="忽略 HTTPS 安全提示">
                <el-switch v-model="form.ignore_https_errors" />
                <div class="form-hint">开启后忽略证书过期、自签名或主机名不匹配提示</div>
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item label="缓存更换间隔">
                <el-input-number v-model="form.cache_bust_seconds" :min="0" :max="86400" :step="30" controls-position="right" />
                <span class="field-unit">秒</span>
                <div class="form-hint">0 为关闭；非 0 时按时间桶追加缓存参数，降低安全设备缓存/拦截影响</div>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="自定义排序号">
                <el-input-number v-model="form.sort_order" :min="0" :max="999999" controls-position="right" />
                <div class="form-hint">数字越小越靠前，相同序号按创建顺序排列</div>
              </el-form-item>
            </el-col>
          </el-row>

          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item label="根域名证书">
                <el-input v-model="form.cert_root_domain" placeholder="example.com（可选）" />
                <div class="form-hint">监控子域名时，可额外检查根域名证书</div>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="额外子域名证书">
                <el-input v-model="form.cert_subdomains" placeholder="www.example.com,api.example.com" />
                <div class="form-hint">多个域名用逗号分隔，最多 20 个</div>
              </el-form-item>
            </el-col>
          </el-row>

          <el-divider content-position="left">自动/手动归类</el-divider>
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item label="归类方式">
                <el-radio-group v-model="form.category_mode">
                  <el-radio-button value="auto">自动归类</el-radio-button>
                  <el-radio-button value="manual">手动归类</el-radio-button>
                </el-radio-group>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="分类名称">
                <el-input v-model="form.category" :disabled="form.category_mode === 'auto'" placeholder="自动归类或手动填写" maxlength="100" />
                <div class="form-hint">自动归类：根域名、子域名、主站、IP 地址、API 服务、管理平台等</div>
              </el-form-item>
            </el-col>
          </el-row>

          <el-divider content-position="left">{{ t('website.certSection') }}</el-divider>
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item :label="t('website.certMonitorEnabled')">
                <el-switch v-model="form.cert_monitor_enabled" />
                <div class="form-hint">{{ t('website.certOnlyHttps') }}</div>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="t('website.certExpiryDays')">
                <el-input-number
                  v-model="form.cert_expiry_days"
                  :min="1"
                  :max="3650"
                  :disabled="!form.cert_monitor_enabled"
                />
                <span class="field-unit">{{ t('website.days') }}</span>
                <div class="form-hint">{{ t('website.certExpiryHint') }}</div>
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item :label="t('website.certAlertLevel')">
                <el-select v-model="form.cert_alert_level" style="width: 100%" :disabled="!form.cert_monitor_enabled">
                  <el-option v-for="item in alertLevels" :key="item.value" :label="item.label" :value="item.value" />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
        </template>

        <el-form-item :label="t('website.description')">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="submit">
            {{ isEdit ? t('common.save') : t('website.create') }}
          </el-button>
          <el-button @click="returnToWebsite">{{ t('common.cancel') }}</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { t } from '@/i18n'
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { websiteApi } from '@/api'

const router = useRouter()
const route = useRoute()

function returnQuery() {
  const query = {}
  for (const key of ['page', 'size', 'search', 'category', 'enabled', 'start', 'end', 'sort_by', 'sort_order']) {
    const value = route.query[key]
    if (typeof value === 'string' && value) query[key] = value
  }
  return query
}

function returnToWebsite() {
  router.push({ path: '/website', query: returnQuery() })
}
const formRef = ref(null)
const submitting = ref(false)

const isEdit = computed(() => !!route.params.id)

const alertLevels = [
  { value: 'info', label: '提示' },
  { value: 'warning', label: '警告' },
  { value: 'critical', label: '严重' },
  { value: 'emergency', label: '紧急' },
]

const form = reactive({
  name: '',
  monitor_type: 'http',
  url: '',
  host: '',
  port: 443,
  method: 'GET',
  expected_status: 200,
  expected_statuses: '',
  expected_keywords: '',
  timeout: 10,
  check_interval: 60,
  slow_threshold_ms: 5000,
  ignore_https_errors: true,
  cache_bust_seconds: 0,
  category: '',
  category_mode: 'auto',
  sort_order: 0,
  cert_root_domain: '',
  cert_subdomains: '',
  cert_monitor_enabled: true,
  cert_expiry_days: 30,
  cert_alert_level: 'warning',
  down_level: 'critical',
  slow_level: 'warning',
  down_level_label: '',
  slow_level_label: '',
  description: '',
})

const rules = computed(() => ({
  name: [{ required: true, message: t('website.monitorNameRequired'), trigger: 'blur' }],
  monitor_type: [{ required: true, message: t('website.monitorTypeRequired'), trigger: 'change' }],
  url: form.monitor_type === 'http' || form.monitor_type === 'https'
    ? [{ required: true, message: t('website.urlRequired'), trigger: 'blur' }]
    : [],
  host: form.monitor_type !== 'http' && form.monitor_type !== 'https'
    ? [{ required: true, message: t('website.hostRequired'), trigger: 'blur' }]
    : [],
  port: form.monitor_type === 'tcp'
    ? [{ required: true, message: t('website.portRequired'), trigger: 'change' }]
    : [],
}))

function onTypeChange(type) {
  if (type === 'http' || type === 'https') form.port = 443
  if (type === 'tcp' && !form.port) form.port = 80
}

function buildPayload() {
  const payload = {
    name: form.name,
    monitor_type: form.monitor_type,
    method: form.method,
    expected_status: form.expected_status,
    expected_statuses: form.expected_statuses || null,
    expected_keywords: form.expected_keywords || null,
    timeout: form.timeout,
    check_interval: form.check_interval,
    slow_threshold_ms: form.slow_threshold_ms,
    ignore_https_errors: form.ignore_https_errors,
    cache_bust_seconds: form.cache_bust_seconds,
    category: form.category || null,
    category_mode: form.category_mode,
    sort_order: form.sort_order,
    cert_root_domain: form.cert_root_domain || null,
    cert_subdomains: form.cert_subdomains || null,
    cert_monitor_enabled: form.cert_monitor_enabled,
    cert_expiry_days: form.cert_expiry_days,
    cert_alert_level: form.cert_alert_level,
    down_level: form.down_level,
    slow_level: form.slow_level,
    down_level_label: form.down_level_label || null,
    slow_level_label: form.slow_level_label || null,
    description: form.description || null,
    is_enabled: true,
  }

  if (form.monitor_type === 'http' || form.monitor_type === 'https') {
    payload.url = form.url
    payload.port = null
    payload.domain = null
  } else if (form.monitor_type === 'tcp') {
    payload.url = `tcp://${form.host}:${form.port}`
    payload.domain = form.host
    payload.ip_address = null
    payload.port = form.port
  } else {
    payload.url = `icmp://${form.host}`
    payload.domain = form.host
    payload.port = null
  }
  return payload
}

async function submit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    submitting.value = true
    try {
      const payload = buildPayload()
      if (isEdit.value) {
        await websiteApi.update(route.params.id, payload)
        ElMessage.success(t('website.updateSuccess'))
      } else {
        await websiteApi.create(payload)
        ElMessage.success(t('website.createSuccess'))
      }
      returnToWebsite()
    } catch (e) {
      ElMessage.error(e.message || t('website.operationFailed'))
    } finally {
      submitting.value = false
    }
  })
}

onMounted(async () => {
  if (!isEdit.value) return
  try {
    const res = await websiteApi.getOne(route.params.id)
    const data = res.data
    Object.assign(form, {
      name: data.name,
      monitor_type: data.monitor_type,
      url: data.url,
      host: data.domain || '',
      port: data.port || 443,
      method: data.method || 'GET',
      expected_status: data.expected_status || 200,
      expected_statuses: data.expected_statuses || '',
      expected_keywords: data.expected_keywords || '',
      timeout: data.timeout || 10,
      check_interval: data.check_interval || 60,
      slow_threshold_ms: data.slow_threshold_ms || 5000,
      ignore_https_errors: data.ignore_https_errors !== false,
      cache_bust_seconds: Number(data.cache_bust_seconds || 0),
      category: data.category || '',
      category_mode: data.category_mode || 'auto',
      sort_order: Number(data.sort_order || 0),
      cert_root_domain: data.cert_root_domain || '',
      cert_subdomains: data.cert_subdomains || '',
      cert_monitor_enabled: data.cert_monitor_enabled !== false,
      cert_expiry_days: data.cert_expiry_days || 30,
      cert_alert_level: data.cert_alert_level || 'warning',
      down_level: data.down_level || 'critical',
      slow_level: data.slow_level || 'warning',
      down_level_label: data.down_level_label || '',
      slow_level_label: data.slow_level_label || '',
      description: data.description || '',
    })
  } catch (e) {
    ElMessage.error(e.message || t('website.loadFailed'))
  }
})
</script>

<style scoped>
.website-form-page {
  height: 100%;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.field-unit {
  margin-left: 6px;
  color: #8ca0af;
  font-size: 11px;
}

.readonly-value {
  color: #38566b;
  font-family: Consolas, monospace;
  font-size: 12px;
}

.form-hint {
  margin-top: 3px;
  color: #91a5b4;
  font-size: 9px;
  line-height: 1.5;
}

.alert-level-hint {
  margin: 2px 0 14px 120px;
  padding: 7px 9px;
  border-radius: 6px;
  color: #7891a5;
  background: #f5faff;
  font-size: 10px;
  line-height: 1.5;
}
</style>
