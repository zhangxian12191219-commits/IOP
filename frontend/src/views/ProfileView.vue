<template>
  <div class="profile-page">
    <el-card class="profile-card" shadow="never">
      <div class="profile-head">
        <div>
          <h2>{{ t('profile.title') }}</h2>
          <p>{{ t('profile.subtitle') }}</p>
        </div>
        <el-tag v-if="user?.is_superuser" type="danger" effect="plain">{{ t('header.superuser') }}</el-tag>
        <el-tag v-else type="info" effect="plain">{{ t('profile.normalUser') }}</el-tag>
      </div>

      <div class="profile-body">
        <aside class="identity-panel">
          <div class="avatar">{{ avatarText }}</div>
          <strong class="identity-name">{{ user?.real_name || user?.username || '-' }}</strong>
          <span class="identity-account">@{{ user?.username || '-' }}</span>
          <div class="identity-meta">
            <div><span>{{ t('profile.roles') }}</span><b>{{ roleNames }}</b></div>
            <div><span>{{ t('profile.groups') }}</span><b>{{ groupNames }}</b></div>
            <div><span>{{ t('profile.lastLogin') }}</span><b>{{ lastLoginText }}</b></div>
          </div>
          <el-alert
            type="info"
            :closable="false"
            show-icon
            :title="t('profile.scopeTip')"
          />
        </aside>

        <section class="account-panel">
          <el-form ref="formRef" :model="form" :rules="rules" label-width="110px" class="account-form">
            <el-divider content-position="left">{{ t('profile.accountSection') }}</el-divider>
            <el-form-item :label="t('profile.username')" prop="username">
              <el-input v-model="form.username" maxlength="64" />
              <div class="form-tip">{{ t('profile.usernameTip') }}</div>
            </el-form-item>
            <el-form-item :label="t('profile.currentPassword')" prop="old_password">
              <el-input v-model="form.old_password" type="password" show-password autocomplete="current-password" />
              <div class="form-tip">{{ t('profile.currentPasswordTip') }}</div>
            </el-form-item>

            <el-divider content-position="left">{{ t('profile.passwordSection') }}</el-divider>
            <el-form-item :label="t('profile.newPassword')" prop="new_password">
              <el-input v-model="form.new_password" type="password" show-password autocomplete="new-password" />
              <div class="form-tip">{{ t('profile.passwordTip') }}</div>
            </el-form-item>
            <el-form-item :label="t('profile.confirmPassword')" prop="confirm">
              <el-input v-model="form.confirm" type="password" show-password autocomplete="new-password" />
            </el-form-item>

            <el-form-item>
              <el-button type="primary" :loading="saving" @click="submit">{{ t('common.save') }}</el-button>
              <el-button @click="resetForm">{{ t('common.reset') }}</el-button>
            </el-form-item>
          </el-form>

          <el-divider content-position="left">二次身份验证</el-divider>
          <div class="totp-card">
            <div class="totp-card-head">
              <div class="totp-card-title">
                <strong>二次身份验证（TOTP）</strong>
                <span>兼容 Google Authenticator / 腾讯身份验证器 / Microsoft Authenticator；启用后登录需要额外输入 6 位动态验证码。</span>
              </div>
              <div class="totp-tags">
                <el-tag v-if="totpStatus?.required" type="warning" size="small">管理员要求</el-tag>
                <el-tag :type="totpStatus?.enabled ? 'success' : 'info'" size="small">
                  {{ totpStatus?.enabled ? '已启用' : '未启用' }}
                </el-tag>
              </div>
            </div>

            <el-alert
              v-if="totpStatus?.required && !totpStatus?.enabled"
              type="warning"
              :closable="false"
              show-icon
              title="管理员已要求该账号开启二次验证，请完成下方绑定后再使用。"
              class="totp-required-alert"
            />
            <el-alert
              v-if="totpStatus?.required && totpStatus?.enabled"
              type="info"
              :closable="false"
              show-icon
              title="管理员已要求该账号开启二次验证，当前账号不能自行停用。"
              class="totp-required-alert"
            />

            <div v-if="!totpStatus?.enabled" class="totp-actions">
              <el-button type="primary" :loading="totpSetupLoading" @click="startTotpSetup">
                {{ totpSetup ? '重新生成密钥' : '开始设置' }}
              </el-button>
              <span class="form-tip">点击生成密钥和二维码，用身份验证器扫码并输入动态验证码完成启用。</span>
            </div>

            <div v-if="totpSetup && !totpStatus?.enabled" class="totp-setup-grid">
              <div class="totp-qr">
                <img v-if="totpSetup.qr_code" :src="totpSetup.qr_code" alt="TOTP QR Code" />
                <el-alert v-else type="warning" :closable="false" show-icon title="二维码生成不可用，请使用下方密钥手动添加" />
                <span class="muted">扫描二维码添加到身份验证器</span>
              </div>
              <el-form label-width="100px" class="totp-setup-form">
                <el-form-item label="密钥">
                  <code class="totp-secret">{{ totpSetup.secret }}</code>
                  <el-button link type="primary" @click="copyTotpText(totpSetup.secret)">复制</el-button>
                </el-form-item>
                <el-form-item label="otpauth">
                  <el-input :model-value="totpSetup.otpauth_uri" readonly type="textarea" :rows="2" resize="none" />
                  <el-button link type="primary" @click="copyTotpText(totpSetup.otpauth_uri)">复制链接</el-button>
                </el-form-item>
                <el-form-item label="动态验证码">
                  <el-input
                    v-model="totpCode"
                    maxlength="6"
                    inputmode="numeric"
                    placeholder="输入身份验证器中的 6 位验证码"
                    style="max-width: 220px"
                  />
                  <el-button type="primary" :loading="totpEnabling" @click="enableTotp">启用</el-button>
                </el-form-item>
                <div class="form-tip">密钥仅在设置时显示，请妥善保管。</div>
              </el-form>
            </div>

            <el-form
              v-if="totpStatus?.enabled && !totpStatus?.required"
              label-width="110px"
              class="totp-setup-form"
            >
              <el-form-item label="当前密码">
                <el-input v-model="totpDisableForm.password" type="password" show-password style="max-width: 260px" />
              </el-form-item>
              <el-form-item label="动态验证码">
                <el-input
                  v-model="totpDisableForm.code"
                  maxlength="6"
                  inputmode="numeric"
                  placeholder="6 位动态验证码"
                  style="max-width: 220px"
                />
                <el-button type="danger" plain :loading="totpDisabling" @click="disableTotp">停用二次验证</el-button>
              </el-form-item>
              <div class="form-tip">停用需要当前密码 + 有效动态验证码，停用后登录只校验账号密码。</div>
            </el-form>
          </div>
        </section>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { currentUser, setUser } from '@/store/auth'
import { userApi } from '@/api'
import apiRequest from '@/api'
import { t } from '@/i18n'

const formRef = ref(null)
const loading = ref(false)
const saving = ref(false)
const user = ref(null)
const form = reactive({
  username: '',
  old_password: '',
  new_password: '',
  confirm: '',
})

const totpStatus = ref(null)
const totpSetup = ref(null)
const totpCode = ref('')
const totpSetupLoading = ref(false)
const totpEnabling = ref(false)
const totpDisabling = ref(false)
const totpDisableForm = reactive({ password: '', code: '' })

async function loadTotpStatus() {
  try {
    const res = await apiRequest.get('/auth/2fa/status')
    totpStatus.value = res.data || null
  } catch {
    totpStatus.value = null
  }
}

async function startTotpSetup() {
  totpSetupLoading.value = true
  try {
    const res = await apiRequest.post('/auth/2fa/setup')
    totpSetup.value = res.data || null
    totpStatus.value = res.data?.status || totpStatus.value
    totpCode.value = ''
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '生成二次验证密钥失败')
  } finally {
    totpSetupLoading.value = false
  }
}

async function enableTotp() {
  const code = String(totpCode.value || '').replace(/\s/g, '')
  if (code.length !== 6) {
    ElMessage.warning('请输入 6 位动态验证码')
    return
  }
  totpEnabling.value = true
  try {
    const res = await apiRequest.post('/auth/2fa/enable', { code })
    totpStatus.value = res.data?.status || { ...(totpStatus.value || {}), enabled: true }
    totpSetup.value = null
    totpCode.value = ''
    ElMessage.success('二次身份验证已启用')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '启用二次身份验证失败')
  } finally {
    totpEnabling.value = false
  }
}

async function disableTotp() {
  if (!totpDisableForm.password) {
    ElMessage.warning('请输入当前密码')
    return
  }
  const code = String(totpDisableForm.code || '').replace(/\s/g, '')
  if (code.length !== 6) {
    ElMessage.warning('请输入 6 位动态验证码')
    return
  }
  totpDisabling.value = true
  try {
    const res = await apiRequest.post('/auth/2fa/disable', {
      password: totpDisableForm.password,
      code,
    })
    totpStatus.value = res.data?.status || { ...(totpStatus.value || {}), enabled: false }
    totpDisableForm.password = ''
    totpDisableForm.code = ''
    ElMessage.success('二次身份验证已停用')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '停用二次身份验证失败')
  } finally {
    totpDisabling.value = false
  }
}

async function copyTotpText(text) {
  try {
    await navigator.clipboard.writeText(text || '')
    ElMessage.success('已复制')
  } catch {
    ElMessage.warning('复制失败，请手动选择文本')
  }
}

const avatarText = computed(() => {
  const value = String(user.value?.real_name || user.value?.username || '?').trim()
  return value.slice(0, 1).toUpperCase()
})

const roleNames = computed(() => {
  const names = (user.value?.roles || []).map((item) => item.name).filter(Boolean)
  if (user.value?.is_superuser && !names.some((name) => name.includes('超级'))) names.unshift(t('header.superuser'))
  return names.join('、') || '-'
})

const groupNames = computed(() => {
  const names = (user.value?.groups || []).map((item) => item.name).filter(Boolean)
  return names.join('、') || '-'
})

const lastLoginText = computed(() => {
  const value = user.value?.last_login
  if (!value) return '-'
  return String(value).replace('T', ' ').slice(0, 19)
})

const rules = computed(() => ({
  username: [
    { required: true, message: t('profile.usernameRequired'), trigger: 'blur' },
    { min: 2, max: 64, message: t('profile.usernameLength'), trigger: 'blur' },
  ],
  old_password: [{ required: true, message: t('profile.currentPasswordRequired'), trigger: 'blur' }],
  new_password: [
    {
      validator: (_rule, value, callback) => {
        if (value && value.length < 4) callback(new Error(t('profile.passwordTooShort')))
        else callback()
      },
      trigger: 'blur',
    },
  ],
  confirm: [
    {
      validator: (_rule, value, callback) => {
        if (form.new_password && value !== form.new_password) callback(new Error(t('profile.passwordMismatch')))
        else callback()
      },
      trigger: 'blur',
    },
  ],
}))

function fillUser(data) {
  user.value = data || currentUser.value || null
  form.username = user.value?.username || ''
}

async function loadMe() {
  loading.value = true
  try {
    const res = await userApi.me()
    fillUser(res.data)
  } catch {
    fillUser(currentUser.value)
  } finally {
    loading.value = false
  }
}

function resetForm() {
  form.old_password = ''
  form.new_password = ''
  form.confirm = ''
  form.username = user.value?.username || ''
  formRef.value?.clearValidate()
}

async function submit() {
  if (saving.value) return
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  if (!form.new_password && !form.username.trim()) {
    ElMessage.warning(t('profile.usernameRequired'))
    return
  }
  saving.value = true
  try {
    const payload = {
      username: form.username.trim(),
      old_password: form.old_password,
    }
    if (form.new_password) payload.password = form.new_password
    const res = await userApi.updateMe(payload)
    setUser(res.data)
    fillUser(res.data)
    resetForm()
    ElMessage.success(t('profile.saved'))
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || t('profile.saveFailed'))
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  await loadMe()
  await loadTotpStatus()
})
</script>

<style scoped>
.profile-page {
  height: 100%;
  padding: 18px;
  overflow: auto;
  background: #f5f7fa;
}

.profile-card {
  max-width: 1080px;
  margin: 0 auto;
  border: 1px solid #e4e9ef;
  border-radius: 10px;
}

.profile-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 14px;
  border-bottom: 1px solid #edf1f5;
}

.profile-head h2 {
  margin: 0;
  color: #17212b;
  font-size: 18px;
  font-weight: 700;
}

.profile-head p {
  margin: 5px 0 0;
  color: #7b8a98;
  font-size: 12px;
}

.profile-body {
  display: grid;
  grid-template-columns: 250px minmax(0, 1fr);
  gap: 28px;
  padding-top: 20px;
}

.identity-panel {
  padding: 18px;
  border: 1px solid #e7edf3;
  border-radius: 9px;
  background: linear-gradient(180deg, #f8fbfe, #fff);
}

.avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 64px;
  height: 64px;
  margin-bottom: 10px;
  border-radius: 50%;
  color: #fff;
  background: linear-gradient(145deg, #2a7fb8, #1b4f78);
  box-shadow: 0 8px 18px rgba(31, 96, 139, 0.22);
  font-size: 26px;
  font-weight: 700;
}

.identity-name {
  display: block;
  color: #1d2b38;
  font-size: 15px;
}

.identity-account {
  display: block;
  margin-top: 3px;
  color: #8b9aa8;
  font-family: Consolas, monospace;
  font-size: 11px;
}

.identity-meta {
  display: grid;
  gap: 8px;
  margin: 16px 0;
  padding-top: 13px;
  border-top: 1px dashed #e5ecf2;
}

.identity-meta div {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  font-size: 11px;
}

.identity-meta span {
  color: #8c9aa7;
  flex-shrink: 0;
}

.identity-meta b {
  color: #314252;
  font-weight: 500;
  text-align: right;
  word-break: break-all;
}

.account-panel {
  min-width: 0;
  padding-right: 14px;
}

.account-form {
  max-width: 620px;
}

.form-tip {
  width: 100%;
  margin-top: 4px;
  color: #8b98a5;
  font-size: 11px;
  line-height: 1.5;
}

.totp-card {
  max-width: 620px;
  padding: 14px 16px;
  border: 1px solid #e2eef6;
  border-radius: 10px;
  background: #fbfdff;
}

.totp-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.totp-card-title {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 4px;
}

.totp-card-title strong {
  color: #24425b;
  font-size: 13px;
}

.totp-card-title span {
  color: #7d95a6;
  font-size: 11px;
  line-height: 1.6;
}

.totp-tags {
  display: flex;
  flex-shrink: 0;
  gap: 6px;
}

.totp-required-alert {
  margin-top: 10px;
}

.totp-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
  flex-wrap: wrap;
}

.totp-setup-grid {
  display: grid;
  grid-template-columns: 190px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
  margin-top: 12px;
}

.totp-qr {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.totp-qr img {
  width: 170px;
  height: 170px;
  padding: 6px;
  border: 1px solid #e2eef6;
  border-radius: 8px;
  background: #fff;
}

.totp-secret {
  display: inline-block;
  max-width: 280px;
  overflow: hidden;
  padding: 3px 6px;
  border-radius: 4px;
  color: #1e4e72;
  background: #edf7ff;
  font-family: Consolas, monospace;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.totp-setup-form {
  margin-top: 12px;
}

.muted {
  color: #94a3b8;
  font-size: 10px;
}

@media (max-width: 860px) {
  .profile-page {
    padding: 10px;
  }

  .profile-body {
    grid-template-columns: 1fr;
  }

  .account-panel {
    padding-right: 0;
  }
}
</style>
