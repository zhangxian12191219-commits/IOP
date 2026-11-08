<template>
  <div class="login-page">
    <!-- 动态科技背景 -->
    <canvas ref="particleCanvas" class="particle-canvas"></canvas>
    <div class="tech-grid"></div>
    <div class="scanline"></div>
    <div class="glow-orb orb-cyan"></div>
    <div class="glow-orb orb-violet"></div>
    <div class="glow-orb orb-amber"></div>

    <!-- HUD 状态栏 -->
    <header class="hud hud-top-left">
      <span class="hud-bracket"></span>
      <span class="hud-label">SNMP // NETWORK OPERATIONS</span>
    </header>
    <div class="hud hud-top-right">
      <span class="status-dot"></span>
      <span class="hud-label">SECURE ACCESS</span>
      <span class="hud-time">{{ clock }}</span>
    </div>

    <main class="login-shell">
      <!-- 左侧品牌/科技信息 -->
      <section class="login-hero">
        <div class="hero-orbit">
          <span class="orbit orbit-a"></span>
          <span class="orbit orbit-b"></span>
          <span class="orbit orbit-c"></span>
          <span class="orbit-core"></span>
          <div class="hero-logo">
            <img v-if="settings.system_logo" :src="settings.system_logo" alt="" class="hero-logo-image" />
            <img v-else src="/logo-default.svg" alt="" class="hero-logo-image" />
          </div>
        </div>

        <p class="hero-kicker">INTELLIGENT NETWORK OPERATIONS</p>
        <h1>{{ systemName }}</h1>
        <p class="hero-desc">{{ loginSubtitle }}</p>

        <div class="hero-tags">
          <span><i class="tag-dot cyan"></i>SNMP v1 / v2c / v3</span>
          <span><i class="tag-dot green"></i>REAL-TIME MONITOR</span>
          <span><i class="tag-dot amber"></i>ENCRYPTED ACCESS</span>
        </div>

        <div class="hero-terminal">
          <div><span class="prompt">$</span> monitor --status <b>ONLINE</b></div>
          <div><span class="prompt">$</span> assets --sync <b>READY</b></div>
          <div class="terminal-cursor"><span class="prompt">$</span> <span class="cursor"></span></div>
        </div>
      </section>

      <!-- 登录卡片 -->
      <section class="login-card">
        <span class="corner corner-tl"></span>
        <span class="corner corner-tr"></span>
        <span class="corner corner-bl"></span>
        <span class="corner corner-br"></span>

        <div class="card-topline">
          <span><i class="live-dot"></i>IDENTITY VERIFICATION</span>
          <span class="card-code">AUTH / 01</span>
        </div>

        <div class="mobile-brand">
          <div class="mobile-logo">
            <img v-if="settings.system_logo" :src="settings.system_logo" alt="" class="mobile-logo-image" />
            <img v-else src="/logo-default.svg" alt="" class="mobile-logo-image" />
          </div>
          <div>
            <strong>{{ systemName }}</strong>
            <span>{{ loginSubtitle }}</span>
          </div>
        </div>

        <div class="card-title">
          <h2>{{ t('login.submit') }}</h2>
          <p>ACCESS CONTROL SYSTEM</p>
        </div>

        <el-alert
          v-if="licenseExpired"
          type="error"
          :closable="false"
          show-icon
          class="license-expired-alert"
        >
          <template #title>商业授权已到期，系统已禁止登录和使用</template>
          <div class="license-expired-detail">
            到期时间：{{ formatLicenseDate(licenseStatus?.expires_at) }}
            <template v-if="licenseStatus?.licensee"> · 授权客户：{{ licenseStatus.licensee }}</template>
          </div>
          <div class="license-expired-detail">
            已有登录会话也将失效。可在下方直接上传新授权文件恢复，或联系管理员处理。
          </div>
        </el-alert>

        <div v-if="licenseExpired" class="license-renewal-card">
          <div class="license-renewal-head">
            <div>
              <strong>{{ t('login.licenseRenewTitle') }}</strong>
              <span>{{ t('login.licenseRenewDesc') }}</span>
            </div>
            <el-tag size="small" type="warning" effect="plain">{{ t('login.licenseRenewTag') }}</el-tag>
          </div>

          <div v-if="licenseStatus?.machine_code" class="license-machine-row">
            <span>{{ t('login.licenseMachineCode') }}</span>
            <code>{{ licenseStatus.machine_code }}</code>
            <el-button link type="primary" @click="copyMachineCode">{{ t('login.licenseCopy') }}</el-button>
          </div>

          <el-input
            v-model="renewToken"
            type="textarea"
            :rows="3"
            resize="none"
            :placeholder="t('login.licenseTokenPlaceholder')"
            class="license-token-input"
          />
          <div class="license-renewal-actions">
            <input
              ref="licenseFileRef"
              type="file"
              accept=".key,.txt,.lic"
              style="display: none"
              @change="onLicenseFileChange"
            />
            <el-button size="small" @click="licenseFileRef?.click()">{{ t('login.licenseChooseFile') }}</el-button>
            <el-button type="primary" size="small" :loading="renewLoading" @click="renewLicense">
              {{ renewLoading ? t('login.licenseActivating') : t('login.licenseActivate') }}
            </el-button>
          </div>
          <div class="license-renewal-hint">{{ t('login.licenseRenewHint') }}</div>
          <el-alert v-if="renewError" :title="renewError" type="error" :closable="false" show-icon />
        </div>

        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          size="large"
          class="login-form"
          :validate-on-rule-change="false"
          @submit.prevent="submit"
        >
          <el-form-item prop="username">
            <el-input v-model="form.username" :placeholder="t('login.username')" autocomplete="username" :disabled="licenseExpired">
              <template #prefix><el-icon><User /></el-icon></template>
            </el-input>
          </el-form-item>
          <el-form-item prop="password">
            <el-input
              v-model="form.password"
              type="password"
              :placeholder="t('login.password')"
              show-password
              autocomplete="current-password"
              :disabled="licenseExpired"
              @keyup.enter="submit"
            >
              <template #prefix><el-icon><Lock /></el-icon></template>
            </el-input>
          </el-form-item>

          <!-- 二次身份验证：密码校验通过后自动出现 -->
          <el-form-item v-if="totpRequired" prop="totpCode" class="totp-item">
            <el-input
              ref="totpInputRef"
              v-model="form.totpCode"
              maxlength="6"
              inputmode="numeric"
              autocomplete="one-time-code"
              placeholder="请输入身份验证器中的 6 位动态验证码"
              :disabled="licenseExpired"
              @keyup.enter="submit"
            >
              <template #prefix><el-icon><Unlock /></el-icon></template>
            </el-input>
            <div class="totp-tip">
              <span class="totp-badge"><i></i>二次身份验证</span>
              支持 Google Authenticator / 腾讯身份验证器，验证码每 30 秒刷新一次。
              <template v-if="captchaEnabled">验证码已刷新，请重新输入下方图片验证码。</template>
            </div>
          </el-form-item>

          <el-form-item v-if="captchaEnabled" prop="captchaCode" class="captcha-item">
            <div class="captcha-row">
              <el-input
                v-model="form.captchaCode"
                :placeholder="t('login.captchaPlaceholder')"
                maxlength="4"
                autocomplete="off"
                :disabled="licenseExpired"
                @keyup.enter="submit"
              >
                <template #prefix><el-icon><Key /></el-icon></template>
              </el-input>
              <div class="captcha-img" :title="t('login.captchaRefresh')" @click="loadCaptcha">
                <img v-if="captchaImage" :src="captchaImage" alt="captcha" />
                <el-icon v-else :class="{ 'is-loading': captchaLoading }">
                  <Loading v-if="captchaLoading" />
                  <Refresh v-else />
                </el-icon>
              </div>
            </div>
            <div v-if="captchaError" class="captcha-error">
              <el-icon><WarningFilled /></el-icon>
              <span>{{ captchaError }}</span>
              <button type="button" @click="loadCaptcha">{{ t('login.captchaReload') }}</button>
            </div>
          </el-form-item>

          <div class="login-options">
            <el-checkbox v-model="form.remember" :disabled="licenseExpired">{{ t('login.remember') }}</el-checkbox>
            <button type="button" class="forgot-link" @click="forgotVisible = true">
              {{ t('login.forgotPassword') }}
            </button>
          </div>

          <el-alert
            v-if="errorMsg"
            :title="errorMsg"
            type="error"
            :closable="false"
            show-icon
            class="login-error"
          />

          <el-button type="primary" class="login-btn" :loading="loading" :disabled="licenseExpired" @click="submit">
            <span>{{ t('login.submit') }}</span>
            <el-icon class="btn-arrow"><Right /></el-icon>
          </el-button>
        </el-form>

        <div class="login-footer">
          {{ t('login.footer') }}
        </div>
      </section>
    </main>

    <div v-if="showCopyright" class="copyright-note" :style="{ color: copyrightColor }">
      {{ copyrightText }}
    </div>

    <div v-if="!showCopyright" class="hud hud-bottom">
      <span>NODE 01</span>
      <span class="hud-line"></span>
      <span>UPTIME 99.99%</span>
      <span class="hud-line"></span>
      <span>AES-256</span>
    </div>

    <el-dialog v-model="forgotVisible" :title="t('login.forgotTitle')" width="640px" append-to-body class="forgot-dialog">
      <p class="forgot-intro">{{ t('login.forgotIntro') }}</p>
      <div class="forgot-grid">
        <div class="forgot-card">
          <div class="forgot-card-title"><el-icon><User /></el-icon>{{ t('login.forgotUserTitle') }}</div>
          <p>{{ t('login.forgotUserDesc') }}</p>
          <div class="forgot-path">{{ t('login.forgotUserPath') }}</div>
        </div>
        <div class="forgot-card admin">
          <div class="forgot-card-title"><el-icon><Key /></el-icon>{{ t('login.forgotAdminTitle') }}</div>
          <p>{{ t('login.forgotAdminDesc') }}</p>
          <div class="forgot-command">
            <code>{{ recoveryCommand }}</code>
            <el-button link type="primary" @click="copyRecoveryCommand">{{ t('login.forgotCopy') }}</el-button>
          </div>
          <div class="forgot-command secondary">
            <code>python tools/reset_password.py --list-admins</code>
          </div>
          <div class="forgot-hint">{{ t('login.forgotCommandHint') }}</div>
        </div>
      </div>
      <el-alert :title="t('login.forgotNote')" type="warning" :closable="false" show-icon />
      <template #footer>
        <el-button @click="forgotVisible = false">{{ t('login.forgotClose') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { isLoggedIn, setToken, setUser } from '@/store/auth'
import { settings, loadPublicSettings } from '@/store/settings'
import { settingsApi, licenseApi, authApi } from '@/api'
import { t } from '@/i18n'

const router = useRouter()
const route = useRoute()
const formRef = ref(null)
const loading = ref(false)
const errorMsg = ref('')
const licenseStatus = ref(null)
const licenseExpired = computed(() => licenseStatus.value?.status === 'expired')

function formatLicenseDate(value) {
  if (!value) return '未知'
  return String(value).replace('T', ' ').slice(0, 19)
}

async function loadLicenseStatus() {
  try {
    const res = await licenseApi.publicStatus()
    licenseStatus.value = res.data
    if (res.data?.status === 'expired') {
      errorMsg.value = ''
    }
  } catch {
    licenseStatus.value = null
  }
}

const licenseFileRef = ref(null)
const renewToken = ref('')
const renewLoading = ref(false)
const renewError = ref('')

async function copyMachineCode() {
  const code = licenseStatus.value?.machine_code
  if (!code) return
  try {
    await navigator.clipboard.writeText(code)
    ElMessage.success(t('login.licenseCopied'))
  } catch {
    ElMessage.error(t('login.licenseCopyFailed'))
  }
}

async function onLicenseFileChange(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  if (file.size > 64 * 1024) {
    renewError.value = t('login.licenseFileTooLarge')
    return
  }
  try {
    renewToken.value = (await file.text()).replace(/^\uFEFF/, '').trim()
    renewError.value = ''
  } catch {
    renewError.value = t('login.licenseFileReadFailed')
  }
}

async function renewLicense() {
  if (renewLoading.value) return
  const token = renewToken.value.trim()
  if (!token) {
    renewError.value = t('login.licenseTokenRequired')
    return
  }
  renewLoading.value = true
  renewError.value = ''
  try {
    const res = await licenseApi.activatePublic(token)
    licenseStatus.value = res.data
    if (res.data?.status !== 'licensed') {
      throw new Error(res.data?.message || t('login.licenseRenewFailed'))
    }
    renewToken.value = ''
    ElMessage.success(t('login.licenseActivated'))
    await loadCaptcha()
  } catch (error) {
    renewError.value = error?.response?.data?.detail || error?.message || t('login.licenseRenewFailed')
  } finally {
    renewLoading.value = false
  }
}

const captchaEnabled = ref(!!settings.captcha_enabled)
const captchaId = ref('')
const captchaImage = ref('')
const captchaLoading = ref(false)
const captchaError = ref('')
const captchaReady = ref(false)
const forgotVisible = ref(false)
const recoveryCommand = 'python tools/reset_password.py --username admin'

async function copyRecoveryCommand() {
  try {
    await navigator.clipboard.writeText(recoveryCommand)
    ElMessage.success(t('login.forgotCopied'))
  } catch {
    ElMessage.error(t('login.forgotCopyFailed'))
  }
}

function clearCaptcha() {
  captchaId.value = ''
  captchaImage.value = ''
  form.captchaCode = ''
}

const systemName = computed(() => settings.system_name || t('header.defaultSystemName'))
const loginSubtitle = computed(() => String(settings.login_subtitle || '').trim() || t('login.subtitle'))
const copyrightText = computed(() => String(settings.copyright_text || '').trim())
const copyrightColor = computed(() => (
  /^#[0-9a-fA-F]{6}$/.test(settings.copyright_color || '') ? settings.copyright_color : '#94a3b8'
))
const showCopyright = computed(() => !!settings.copyright_enabled && !!copyrightText.value)

const form = reactive({
  username: '',
  password: '',
  totpCode: '',
  captchaCode: '',
  remember: false,
})

// 二次身份验证（TOTP）：密码校验通过后由后端返回 totp_required，前端显示动态验证码输入框
const totpRequired = ref(false)
const totpInputRef = ref(null)

watch(
  () => form.username,
  () => {
    // 切换账号后清空二次验证状态，避免沿用上一个账号的输入
    totpRequired.value = false
    form.totpCode = ''
  }
)

const rules = computed(() => ({
  username: [{ required: true, message: t('login.username'), trigger: 'blur' }],
  password: [{ required: true, message: t('login.password'), trigger: 'blur' }],
  totpCode: totpRequired.value
    ? [
        { required: true, message: '请输入 6 位动态验证码', trigger: 'blur' },
        { pattern: /^\s*\d{6}\s*$/, message: '动态验证码为 6 位数字', trigger: 'blur' },
      ]
    : [],
  captchaCode: captchaEnabled.value
    ? [{ required: true, message: t('login.captchaPlaceholder'), trigger: 'blur' }]
    : [],
}))

async function loadCaptcha(retry = true) {
  captchaLoading.value = true
  captchaError.value = ''
  try {
    const res = await settingsApi.getCaptcha()
    if (res.data?.enabled === false) {
      // 公开配置与验证码接口可能因缓存短暂不一致，先刷新配置再重试一次
      if (retry) {
        await loadPublicSettings()
        if (settings.captcha_enabled) return loadCaptcha(false)
      }
      if (!settings.captcha_enabled) {
        captchaEnabled.value = false
        clearCaptcha()
        return
      }
      // 配置要求验证码但接口未返回时，保留验证码区域并提示，避免“验证码消失”
      captchaEnabled.value = true
      clearCaptcha()
      captchaError.value = t('login.captchaLoadFailed')
      return
    }
    if (!res.data?.captcha_id || !res.data?.image) {
      throw new Error('验证码数据不完整')
    }
    captchaEnabled.value = true
    captchaId.value = res.data.captcha_id
    captchaImage.value = res.data.image
    form.captchaCode = ''
  } catch {
    // 接口异常时保留验证码区域，避免用户误以为系统关闭了验证码
    if (retry) return loadCaptcha(false)
    captchaEnabled.value = true
    clearCaptcha()
    captchaError.value = t('login.captchaLoadFailed')
  } finally {
    captchaLoading.value = false
    captchaReady.value = true
  }
}

async function submit() {
  if (loading.value) return
  if (licenseExpired.value) {
    errorMsg.value = '商业授权已到期，系统禁止登录。请联系管理员更新授权文件。'
    return
  }
  if (!formRef.value) return

  // 首次进入页面必须等待验证码配置检查完成，避免配置尚未加载时直接登录
  if (!captchaReady.value || captchaLoading.value) {
    errorMsg.value = t('login.captchaChecking')
    return
  }

  // 验证码已启用时必须拿到本次有效的验证码，禁止在验证码未加载时提交
  if (captchaEnabled.value && (!captchaId.value || !captchaImage.value)) {
    errorMsg.value = t('login.captchaNotReady')
    await loadCaptcha()
    return
  }

  await formRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    errorMsg.value = ''
    try {
      const res = await authApi.login({
        username: form.username.trim(),
        password: form.password,
        captcha_id: captchaId.value,
        captcha_code: form.captchaCode,
        // 已启用二次身份验证时，第二次提交才携带动态验证码
        totp_code: totpRequired.value ? form.totpCode.replace(/\s/g, '') : undefined,
      })
      const { token, user } = res.data || {}
      if (!token || !user) throw new Error(t('login.failed'))
      setToken(token, form.remember !== false)
      setUser(user)
      ElMessage.success(`${t('login.welcome')}，${user.real_name || user.username}`)
      if (user.totp_required && !user.totp_enabled) {
        ElMessage.warning('管理员已要求该账号开启二次验证，请在个人账户完成绑定')
        router.replace('/profile')
        return
      }
      const redirect = (route.query.redirect || '/dashboard').toString()
      router.replace(redirect)
    } catch (e) {
      const data = e?.response?.data || {}
      const code = data.code
      if (code === 'totp_required' || code === 'totp_invalid') {
        // 该账号已启用二次身份验证：显示动态验证码输入框，等待用户补充后再次提交
        totpRequired.value = true
        errorMsg.value = code === 'totp_invalid'
          ? (data.detail || '动态验证码不正确或已过期，请重新输入')
          : ''
        await loadCaptcha()
        loading.value = false
        await nextTick()
        totpInputRef.value?.focus?.()
        return
      }
      errorMsg.value = data.detail || e.message || t('login.failed')
      // 验证码一次性使用，失败后刷新
      await loadCaptcha()
    } finally {
      loading.value = false
    }
  })
}

// ==================== 科技背景动效 ====================
const particleCanvas = ref(null)
const clock = ref('')

let ctx = null
let particles = []
let animationId = 0
let clockTimer = null
let resizeHandler = null
let reducedMotion = false

function updateClock() {
  const now = new Date()
  const pad = (value) => String(value).padStart(2, '0')
  clock.value = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`
}

function setupParticles() {
  const canvas = particleCanvas.value
  if (!canvas) return
  ctx = canvas.getContext('2d')
  if (!ctx) return

  reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  let width = 0
  let height = 0

  const resize = () => {
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    width = window.innerWidth
    height = window.innerHeight
    canvas.width = width * dpr
    canvas.height = height * dpr
    canvas.style.width = `${width}px`
    canvas.style.height = `${height}px`
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

    const count = Math.min(90, Math.max(30, Math.floor(width / 22)))
    particles = Array.from({ length: count }, () => ({
      x: Math.random() * width,
      y: Math.random() * height,
      vx: (Math.random() - 0.5) * 0.28,
      vy: (Math.random() - 0.5) * 0.28,
      radius: Math.random() * 1.4 + 0.5,
      hue: Math.random() > 0.82 ? 262 : Math.random() > 0.7 ? 38 : 196,
      alpha: Math.random() * 0.45 + 0.2,
    }))
  }

  const draw = () => {
    if (!ctx) return
    ctx.clearRect(0, 0, width, height)

    for (let i = 0; i < particles.length; i += 1) {
      const p = particles[i]
      if (!reducedMotion) {
        p.x += p.vx
        p.y += p.vy
      }
      if (p.x < -20) p.x = width + 20
      if (p.x > width + 20) p.x = -20
      if (p.y < -20) p.y = height + 20
      if (p.y > height + 20) p.y = -20

      ctx.beginPath()
      ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2)
      ctx.fillStyle = `hsla(${p.hue}, 90%, 65%, ${p.alpha})`
      ctx.fill()

      for (let j = i + 1; j < particles.length; j += 1) {
        const q = particles[j]
        const dx = p.x - q.x
        const dy = p.y - q.y
        const distance = Math.hypot(dx, dy)
        if (distance < 135) {
          ctx.beginPath()
          ctx.moveTo(p.x, p.y)
          ctx.lineTo(q.x, q.y)
          ctx.strokeStyle = `hsla(196, 90%, 60%, ${(1 - distance / 135) * 0.12})`
          ctx.lineWidth = 0.6
          ctx.stroke()
        }
      }
    }

    if (!reducedMotion) animationId = requestAnimationFrame(draw)
  }

  resize()
  resizeHandler = resize
  window.addEventListener('resize', resize)
  draw()
}

onMounted(async () => {
  if (isLoggedIn.value) {
    router.replace('/dashboard')
    return
  }
  updateClock()
  clockTimer = setInterval(updateClock, 1000)
  setupParticles()

  await loadPublicSettings()
  await loadLicenseStatus()
  captchaEnabled.value = !!settings.captcha_enabled
  form.remember = !!settings.auto_login
  await loadCaptcha()
})

onBeforeUnmount(() => {
  if (animationId) cancelAnimationFrame(animationId)
  if (clockTimer) clearInterval(clockTimer)
  if (resizeHandler) window.removeEventListener('resize', resizeHandler)
  ctx = null
  particles = []
})
</script>

<style scoped>
.login-page {
  position: relative;
  height: 100vh;
  min-height: 620px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px;
  overflow: hidden;
  background: #040912;
  color: #e2e8f0;
  isolation: isolate;
}

.particle-canvas {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
}

.tech-grid {
  position: absolute;
  inset: -20%;
  z-index: 0;
  pointer-events: none;
  background-image:
    linear-gradient(rgba(56, 189, 248, 0.08) 1px, transparent 1px),
    linear-gradient(90deg, rgba(56, 189, 248, 0.08) 1px, transparent 1px);
  background-size: 52px 52px;
  transform: perspective(680px) rotateX(56deg) translateY(8%);
  transform-origin: center 65%;
  animation: grid-flow 18s linear infinite;
  mask-image: radial-gradient(ellipse at 50% 55%, #000 10%, rgba(0, 0, 0, 0.72) 48%, transparent 78%);
}

@keyframes grid-flow {
  from { background-position: 0 0, 0 0; }
  to { background-position: 0 52px, 52px 0; }
}

.login-page::after {
  content: '';
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
  background:
    radial-gradient(circle at 50% 120%, rgba(14, 165, 233, 0.2), transparent 46%),
    linear-gradient(180deg, rgba(2, 6, 23, 0.2), rgba(2, 6, 23, 0.78));
}

.scanline {
  position: absolute;
  left: 0;
  right: 0;
  top: -18%;
  height: 18%;
  z-index: 2;
  pointer-events: none;
  background: linear-gradient(180deg, transparent, rgba(56, 189, 248, 0.055), transparent);
  animation: scan 7s linear infinite;
}

@keyframes scan {
  0% { transform: translateY(-20vh); }
  100% { transform: translateY(130vh); }
}

.glow-orb {
  position: absolute;
  z-index: 0;
  border-radius: 50%;
  filter: blur(80px);
  pointer-events: none;
  opacity: 0.55;
}

.orb-cyan {
  width: 460px;
  height: 460px;
  left: -140px;
  top: -120px;
  background: rgba(14, 165, 233, 0.32);
  animation: pulse-orb 9s ease-in-out infinite;
}

.orb-violet {
  width: 420px;
  height: 420px;
  right: -120px;
  bottom: -120px;
  background: rgba(129, 92, 246, 0.3);
  animation: pulse-orb 11s ease-in-out infinite reverse;
}

.orb-amber {
  width: 240px;
  height: 240px;
  right: 18%;
  top: 10%;
  background: rgba(245, 158, 11, 0.12);
  animation: pulse-orb 13s ease-in-out infinite;
}

@keyframes pulse-orb {
  0%, 100% { transform: scale(1); opacity: 0.42; }
  50% { transform: scale(1.15); opacity: 0.62; }
}

/* HUD */
.hud {
  position: absolute;
  z-index: 5;
  display: flex;
  align-items: center;
  gap: 10px;
  color: #7dd3fc;
  font-family: 'Consolas', 'SFMono-Regular', monospace;
  font-size: 10px;
  letter-spacing: 2px;
  text-transform: uppercase;
  pointer-events: none;
}

.hud-top-left {
  top: 26px;
  left: 32px;
}

.hud-top-right {
  top: 26px;
  right: 32px;
}

.hud-bracket {
  width: 18px;
  height: 18px;
  border-left: 1px solid rgba(56, 189, 248, 0.85);
  border-top: 1px solid rgba(56, 189, 248, 0.85);
  box-shadow: -2px -2px 12px rgba(56, 189, 248, 0.25);
}

.hud-label {
  opacity: 0.8;
}

.status-dot,
.live-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #22c55e;
  box-shadow: 0 0 10px rgba(34, 197, 94, 0.9);
  animation: blink 2.2s ease-in-out infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}

.hud-time {
  color: #e2e8f0;
  letter-spacing: 1px;
  font-variant-numeric: tabular-nums;
}

.hud-bottom {
  left: 50%;
  bottom: 24px;
  transform: translateX(-50%);
  color: #64748b;
  letter-spacing: 3px;
  font-size: 9px;
}

.copyright-note {
  position: fixed;
  left: 50%;
  bottom: 20px;
  z-index: 40;
  max-width: min(92vw, 900px);
  transform: translateX(-50%);
  color: #94a3b8;
  font-size: 12px;
  line-height: 1.6;
  letter-spacing: 0.5px;
  text-align: center;
  overflow-wrap: anywhere;
  pointer-events: none;
}

.hud-line {
  width: 48px;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(56, 189, 248, 0.5), transparent);
}

/* 主体 */
.login-shell {
  position: relative;
  z-index: 10;
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(360px, 420px);
  align-items: center;
  gap: clamp(40px, 7vw, 100px);
  width: min(1120px, 100%);
}

/* 左侧品牌 */
.login-hero {
  min-width: 0;
  padding-left: 6px;
}

.hero-orbit {
  position: relative;
  width: 148px;
  height: 148px;
  margin-bottom: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.orbit {
  position: absolute;
  border-radius: 50%;
  border: 1px solid rgba(56, 189, 248, 0.24);
}

.orbit::before {
  content: '';
  position: absolute;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #38bdf8;
  top: -2px;
  left: 50%;
  box-shadow: 0 0 10px rgba(56, 189, 248, 0.95);
}

.orbit-a {
  inset: 0;
  animation: spin 14s linear infinite;
}

.orbit-b {
  inset: 17px;
  border-color: rgba(129, 140, 248, 0.22);
  animation: spin 10s linear infinite reverse;
}

.orbit-b::before {
  background: #a78bfa;
  box-shadow: 0 0 10px rgba(167, 139, 250, 0.95);
}

.orbit-c {
  inset: 33px;
  border-color: rgba(245, 158, 11, 0.16);
  animation: spin 18s linear infinite;
}

.orbit-c::before {
  background: #fbbf24;
  box-shadow: 0 0 8px rgba(245, 158, 11, 0.85);
}

.orbit-core {
  position: absolute;
  inset: 42px;
  border-radius: 50%;
  border: 1px solid rgba(56, 189, 248, 0.15);
  background: radial-gradient(circle, rgba(56, 189, 248, 0.14), transparent 68%);
  animation: core-pulse 3.6s ease-in-out infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@keyframes core-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(56, 189, 248, 0.12); }
  50% { box-shadow: 0 0 34px 6px rgba(56, 189, 248, 0.12); }
}

.hero-logo {
  position: relative;
  z-index: 1;
  width: 78px;
  height: 78px;
  border-radius: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #06111f;
  background: linear-gradient(145deg, #7dd3fc, #38bdf8 45%, #818cf8);
  border: 1px solid rgba(186, 230, 253, 0.7);
  box-shadow:
    0 0 0 6px rgba(56, 189, 248, 0.08),
    0 0 44px rgba(56, 189, 248, 0.42),
    inset 0 1px 0 rgba(255, 255, 255, 0.5);
}

.hero-logo-image {
  width: 100%;
  height: 100%;
  object-fit: contain;
  border-radius: 21px;
}

.hero-kicker {
  margin: 0 0 12px;
  color: #38bdf8;
  font-family: 'Consolas', 'SFMono-Regular', monospace;
  font-size: 10px;
  letter-spacing: 3px;
}

.login-hero h1 {
  margin: 0 0 12px;
  font-size: clamp(30px, 3.2vw, 48px);
  line-height: 1.15;
  letter-spacing: 2px;
  font-weight: 700;
  color: #f0f9ff;
  text-shadow: 0 0 26px rgba(56, 189, 248, 0.18);
}

.hero-desc {
  max-width: 460px;
  margin: 0 0 24px;
  color: #94a3b8;
  font-size: 13px;
  line-height: 1.8;
}

.hero-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 26px;
}

.hero-tags span {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 6px 10px;
  border: 1px solid rgba(56, 189, 248, 0.16);
  border-radius: 4px;
  background: rgba(8, 20, 38, 0.55);
  color: #94a3b8;
  font-family: 'Consolas', monospace;
  font-size: 9px;
  letter-spacing: 1px;
}

.tag-dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
}

.tag-dot.cyan { background: #38bdf8; box-shadow: 0 0 8px #38bdf8; }
.tag-dot.green { background: #22c55e; box-shadow: 0 0 8px #22c55e; }
.tag-dot.amber { background: #f59e0b; box-shadow: 0 0 8px #f59e0b; }

.hero-terminal {
  width: min(420px, 100%);
  padding: 13px 16px;
  border: 1px solid rgba(56, 189, 248, 0.13);
  border-left: 2px solid rgba(56, 189, 248, 0.55);
  border-radius: 6px;
  background: rgba(4, 12, 24, 0.58);
  color: #64748b;
  font-family: 'Consolas', 'SFMono-Regular', monospace;
  font-size: 10px;
  line-height: 1.9;
  letter-spacing: 0.5px;
  backdrop-filter: blur(6px);
}

.hero-terminal b {
  color: #22c55e;
  font-weight: 500;
}

.prompt {
  color: #38bdf8;
  margin-right: 8px;
}

.cursor {
  display: inline-block;
  width: 7px;
  height: 11px;
  vertical-align: -1px;
  background: #38bdf8;
  animation: cursor-blink 1s steps(1) infinite;
}

@keyframes cursor-blink {
  0%, 49% { opacity: 1; }
  50%, 100% { opacity: 0; }
}

/* 登录卡片 */
.login-card {
  position: relative;
  width: 100%;
  padding: 26px 30px 22px;
  border: 1px solid rgba(56, 189, 248, 0.24);
  border-radius: 8px;
  background:
    linear-gradient(160deg, rgba(10, 24, 43, 0.94), rgba(5, 13, 26, 0.92));
  box-shadow:
    0 0 0 1px rgba(2, 6, 23, 0.6),
    0 28px 80px rgba(0, 0, 0, 0.65),
    0 0 46px rgba(14, 165, 233, 0.1) inset;
  backdrop-filter: blur(16px);
}

.login-card::before {
  content: '';
  position: absolute;
  inset: -1px;
  border-radius: 8px;
  padding: 1px;
  background: linear-gradient(120deg, rgba(56, 189, 248, 0.7), transparent 30%, transparent 70%, rgba(129, 92, 246, 0.55));
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  pointer-events: none;
}

.login-card::after {
  content: '';
  position: absolute;
  left: 12%;
  right: 12%;
  top: -1px;
  height: 1px;
  background: linear-gradient(90deg, transparent, #38bdf8, transparent);
  box-shadow: 0 0 14px rgba(56, 189, 248, 0.85);
  animation: card-line 4.5s ease-in-out infinite;
}

@keyframes card-line {
  0%, 100% { opacity: 0.35; transform: scaleX(0.55); }
  50% { opacity: 1; transform: scaleX(1); }
}

.corner {
  position: absolute;
  width: 12px;
  height: 12px;
  pointer-events: none;
}

.corner-tl { top: 7px; left: 7px; border-left: 1px solid #38bdf8; border-top: 1px solid #38bdf8; }
.corner-tr { top: 7px; right: 7px; border-right: 1px solid #38bdf8; border-top: 1px solid #38bdf8; }
.corner-bl { bottom: 7px; left: 7px; border-left: 1px solid rgba(56, 189, 248, 0.55); border-bottom: 1px solid rgba(56, 189, 248, 0.55); }
.corner-br { bottom: 7px; right: 7px; border-right: 1px solid rgba(56, 189, 248, 0.55); border-bottom: 1px solid rgba(56, 189, 248, 0.55); }

.card-topline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 22px;
  color: #7dd3fc;
  font-family: 'Consolas', monospace;
  font-size: 9px;
  letter-spacing: 2px;
}

.card-topline > span:first-child {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}

.card-code {
  color: #475569;
}

.live-dot {
  width: 5px;
  height: 5px;
}

.mobile-brand {
  display: none;
}

.card-title {
  margin-bottom: 22px;
}

.card-title h2 {
  margin: 0 0 5px;
  font-size: 24px;
  letter-spacing: 4px;
  color: #f0f9ff;
  font-weight: 600;
}

.card-title p {
  margin: 0;
  color: #475569;
  font-family: 'Consolas', monospace;
  font-size: 9px;
  letter-spacing: 2.4px;
}

.login-form {
  margin-top: 4px;
}

.login-form :deep(.el-form-item) {
  margin-bottom: 18px;
}

.captcha-item :deep(.el-form-item__content) {
  display: block;
}

.captcha-row {
  display: flex;
  gap: 10px;
  width: 100%;
}

.captcha-row :deep(.el-input) {
  flex: 1;
}

.captcha-img {
  width: 116px;
  height: 40px;
  border-radius: 5px;
  overflow: hidden;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f7fa;
  border: 1px solid rgba(56, 189, 248, 0.3);
  box-shadow: 0 0 14px rgba(56, 189, 248, 0.12);
  flex-shrink: 0;
}

.captcha-img img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.captcha-error {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  color: #fca5a5;
  font-size: 10px;
  line-height: 1.4;
}

.captcha-error button {
  padding: 0;
  border: 0;
  color: #7dd3fc;
  background: transparent;
  font-size: 10px;
  cursor: pointer;
  text-decoration: underline;
}

/* 二次身份验证动态验证码 */
.totp-item :deep(.el-form-item__content) {
  display: block;
}

.totp-item :deep(.el-input__inner) {
  letter-spacing: 6px;
  font-family: 'Consolas', 'SFMono-Regular', monospace;
  font-size: 16px;
}

.totp-tip {
  margin-top: 7px;
  color: #7f9eb2;
  font-size: 10px;
  line-height: 1.6;
}

.totp-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-right: 6px;
  padding: 2px 7px;
  border: 1px solid rgba(56, 189, 248, 0.35);
  border-radius: 10px;
  color: #7dd3fc;
  font-size: 9px;
  letter-spacing: 1px;
}

.totp-badge i {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #22c55e;
  box-shadow: 0 0 8px rgba(34, 197, 94, 0.85);
}

.login-options {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: -4px 0 14px;
}

.forgot-link {
  padding: 0;
  border: 0;
  color: #7dd3fc;
  background: transparent;
  font-size: 11px;
  cursor: pointer;
  transition: color 0.18s ease;
}

.forgot-link:hover {
  color: #e0f2fe;
  text-decoration: underline;
}

.forgot-intro {
  margin: 0 0 14px;
  color: #546e82;
  font-size: 12px;
  line-height: 1.6;
}

.forgot-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 12px;
}

.forgot-card {
  padding: 12px 13px;
  border: 1px solid #e2edf6;
  border-radius: 9px;
  background: #f8fbfe;
}

.forgot-card.admin {
  border-color: #d8e9f3;
  background: linear-gradient(135deg, #f3faff, #fbfdff);
}

.forgot-card-title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 7px;
  color: #24485f;
  font-size: 13px;
  font-weight: 600;
}

.forgot-card p {
  margin: 0;
  color: #637b8d;
  font-size: 11px;
  line-height: 1.6;
}

.forgot-path {
  margin-top: 8px;
  padding: 7px 9px;
  border-radius: 6px;
  color: #2c647f;
  background: #eaf5fc;
  font-size: 10px;
}

.forgot-command {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 8px;
  padding: 6px 8px;
  overflow: hidden;
  border: 1px solid #dcebf5;
  border-radius: 6px;
  background: #fff;
}

.forgot-command code {
  min-width: 0;
  overflow: hidden;
  color: #235b74;
  font-family: Consolas, monospace;
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.forgot-command.secondary code {
  color: #6b8495;
}

.forgot-command :deep(.el-button) {
  flex-shrink: 0;
  padding: 0;
  font-size: 10px;
}

.forgot-hint {
  margin-top: 7px;
  color: #8a9eac;
  font-size: 10px;
  line-height: 1.5;
}

:global(.forgot-dialog .el-dialog__body) {
  padding-top: 8px;
}

:global(.forgot-dialog .el-alert) {
  margin-top: 2px;
}

@media (max-width: 700px) {
  .forgot-grid {
    grid-template-columns: 1fr;
  }
}

.login-options :deep(.el-checkbox__label) {
  color: #94a3b8;
  font-size: 12px;
}

.login-options :deep(.el-checkbox__inner) {
  background: rgba(2, 6, 23, 0.5);
  border-color: rgba(56, 189, 248, 0.35);
}

.login-options :deep(.el-checkbox__input.is-checked .el-checkbox__inner) {
  background: #0ea5e9;
  border-color: #38bdf8;
}

.secure-hint {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #475569;
  font-family: 'Consolas', monospace;
  font-size: 9px;
  letter-spacing: 1px;
}

.secure-hint i {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #22c55e;
  box-shadow: 0 0 8px rgba(34, 197, 94, 0.8);
}

.license-expired-alert {
  margin-bottom: 14px;
  border-radius: 6px;
}

.license-expired-detail {
  margin-top: 4px;
  color: #7f1d1d;
  font-size: 11px;
  line-height: 1.55;
}

.license-renewal-card {
  margin-bottom: 14px;
  padding: 11px 12px;
  border: 1px solid rgba(56, 189, 248, 0.28);
  border-radius: 8px;
  background: rgba(8, 30, 52, 0.78);
}

.license-renewal-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 9px;
}

.license-renewal-head strong {
  display: block;
  color: #d8f3ff;
  font-size: 12px;
  line-height: 1.4;
}

.license-renewal-head span:not(.el-tag__content) {
  display: block;
  margin-top: 2px;
  color: #7f9eb2;
  font-size: 10px;
  line-height: 1.5;
}

.license-machine-row {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 8px;
  color: #64889e;
  font-size: 10px;
}

.license-machine-row code {
  min-width: 0;
  overflow: hidden;
  color: #9ed9ef;
  font-family: Consolas, monospace;
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.license-token-input {
  margin-bottom: 8px;
}

.license-token-input :deep(.el-textarea__inner) {
  background: rgba(2, 15, 29, 0.7);
  color: #d8f3ff;
  font-family: Consolas, monospace;
  font-size: 10px;
  line-height: 1.5;
}

.license-token-input :deep(.el-textarea__inner::placeholder) {
  color: #557389;
}

.license-renewal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 7px;
}

.license-renewal-hint {
  margin-top: 8px;
  color: #5b7d91;
  font-size: 9px;
  line-height: 1.5;
}

.license-renewal-card :deep(.el-alert) {
  margin-top: 8px;
}

.login-error {
  margin-bottom: 14px;
  border-radius: 5px;
}

.login-btn {
  position: relative;
  width: 100%;
  height: 44px;
  margin-top: 2px;
  border: 1px solid rgba(125, 211, 252, 0.7);
  border-radius: 5px;
  font-size: 14px;
  letter-spacing: 3px;
  color: #04111f;
  background: linear-gradient(100deg, #7dd3fc, #38bdf8 55%, #818cf8);
  box-shadow: 0 0 24px rgba(56, 189, 248, 0.28);
  transition: box-shadow 0.25s, transform 0.25s;
}

.login-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 0 34px rgba(56, 189, 248, 0.5);
}

.btn-arrow {
  margin-left: 8px;
  transition: transform 0.25s;
}

.login-btn:hover .btn-arrow {
  transform: translateX(4px);
}

.login-footer {
  margin-top: 18px;
  text-align: center;
  font-size: 10px;
  color: #475569;
  line-height: 1.6;
  font-family: 'Consolas', monospace;
  letter-spacing: 0.5px;
}

:deep(.el-input__wrapper) {
  background: rgba(2, 8, 18, 0.72);
  border-radius: 5px;
  box-shadow: 0 0 0 1px rgba(56, 189, 248, 0.18) inset;
  transition: box-shadow 0.22s;
}

:deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px rgba(56, 189, 248, 0.35) inset;
}

:deep(.el-input__wrapper.is-focus) {
  box-shadow:
    0 0 0 1px rgba(56, 189, 248, 0.8) inset,
    0 0 18px rgba(56, 189, 248, 0.12);
}

:deep(.el-input__inner) {
  color: #e2e8f0;
  font-size: 13px;
}

:deep(.el-input__inner::placeholder) {
  color: #475569;
}

:deep(.el-input__prefix) {
  color: #38bdf8;
}

:deep(.el-form-item__error) {
  color: #fb7185;
  font-size: 11px;
}

/* 响应式 */
@media (max-width: 920px) {
  .login-page {
    padding: 24px;
    min-height: 100vh;
  }

  .login-shell {
    grid-template-columns: 1fr;
    width: min(440px, 100%);
  }

  .login-hero {
    display: none;
  }

  .mobile-brand {
    display: flex;
    align-items: center;
    gap: 12px;
    padding-bottom: 18px;
    margin-bottom: 18px;
    border-bottom: 1px solid rgba(56, 189, 248, 0.12);
  }

  .mobile-logo {
    width: 42px;
    height: 42px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #06111f;
    background: linear-gradient(145deg, #7dd3fc, #38bdf8 55%, #818cf8);
    box-shadow: 0 0 22px rgba(56, 189, 248, 0.35);
  }

  .mobile-logo-image {
    width: 100%;
    height: 100%;
    object-fit: contain;
    border-radius: 11px;
  }

  .mobile-brand strong {
    display: block;
    color: #f0f9ff;
    font-size: 15px;
    letter-spacing: 1px;
    word-break: break-all;
  }

  .mobile-brand span {
    display: block;
    margin-top: 3px;
    color: #64748b;
    font-size: 10px;
  }

  .hud-top-left {
    top: 16px;
    left: 16px;
  }

  .hud-top-right {
    top: 16px;
    right: 16px;
  }

  .hud-bottom {
    display: none;
  }

  .hud-label:first-of-type {
    display: none;
  }

  .hud-top-left .hud-label {
    display: none;
  }
}

@media (max-width: 520px) {
  .login-page {
    padding: 14px;
  }

  .login-card {
    padding: 22px 18px 18px;
  }

  .card-title h2 {
    font-size: 21px;
  }

  .hud-time {
    font-size: 9px;
  }

  .hud-top-left .hud-label {
    font-size: 8px;
    letter-spacing: 1px;
  }

  .secure-hint {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .tech-grid,
  .scanline,
  .glow-orb,
  .orbit,
  .orbit-core,
  .status-dot,
  .live-dot,
  .cursor,
  .login-card::after {
    animation: none !important;
  }
}
</style>
