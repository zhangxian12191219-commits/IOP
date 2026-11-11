<template>
  <el-config-provider :locale="epLocale" :direction="locale === 'ar-SA' ? 'rtl' : 'ltr'">
  <!-- 大屏模式：全屏无侧边栏 -->
  <router-view v-if="isFullscreen" />

  <!-- 常规管理界面 -->
  <el-container v-else class="app-container">
    <!-- 侧边栏 -->
    <el-aside :width="isCollapse ? '64px' : '220px'" class="sidebar" :class="{ 'is-collapse': isCollapse }">
      <div class="logo">
        <img
          v-if="settings.system_logo"
          :src="settings.system_logo"
          alt=""
          class="logo-image"
        />
        <img v-else src="/logo-default.svg" alt="" class="logo-image" />
        <span v-if="!isCollapse" class="logo-text">{{ systemName }}</span>
      </div>

      <el-menu
        :default-active="activeMenu"
        :collapse="isCollapse"
        :collapse-transition="false"
        background-color="#001529"
        text-color="#ffffffa6"
        active-text-color="#1890ff"
        @select="handleMenuSelect"
      >
        <el-menu-item
          v-for="item in mainMenus"
          :key="item.key"
          :index="item.index"
          :data-menu-key="item.key"
          class="sidebar-menu-item"
          :class="{
            'is-menu-dragging': draggingMenuKey === item.key,
            'is-drag-origin': draggingMenuKey === item.key,
          }"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <template #title>{{ item.label || t(item.labelKey) }}</template>
          <span
            v-if="item.badge && alertCount > 0 && !isCollapse"
            class="alert-count-badge"
          >
            {{ alertCount > 99 ? '99+' : alertCount }}
          </span>
          <span
            v-if="item.key === 'im' && imUnread > 0"
            class="alert-count-badge im-message-badge"
          >
            {{ imUnread > 99 ? '99+' : imUnread }}
          </span>
          <span
            v-if="!isCollapse && !isBottomMenuItem(item.key)"
            class="menu-drag-handle"
            :title="t('menu.dragSortHint')"
            @pointerdown.stop.prevent="startMenuDrag($event, item)"
            @click.stop.prevent
          >
            <el-icon :size="13"><Rank /></el-icon>
          </span>
        </el-menu-item>
      </el-menu>

      <el-menu
        v-if="bottomMenus.length"
        :default-active="activeMenu"
        :collapse="isCollapse"
        :collapse-transition="false"
        background-color="#001529"
        text-color="#ffffffa6"
        active-text-color="#1890ff"
        class="sidebar-bottom-menu"
        @select="handleMenuSelect"
      >
        <el-menu-item
          v-for="item in bottomMenus"
          :key="item.key"
          :index="item.index"
          :data-menu-key="item.key"
          class="sidebar-menu-item is-pinned-bottom"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <template #title>{{ item.label || t(item.labelKey) }}</template>
          <span
            v-if="item.badge && alertCount > 0 && !isCollapse"
            class="alert-count-badge"
          >
            {{ alertCount > 99 ? '99+' : alertCount }}
          </span>
          <span
            v-if="item.key === 'im' && imUnread > 0"
            class="alert-count-badge im-message-badge"
          >
            {{ imUnread > 99 ? '99+' : imUnread }}
          </span>
        </el-menu-item>
      </el-menu>

      <div class="sidebar-footer">
        <el-tooltip v-if="versionText" :content="versionTooltip" placement="right">
          <div class="sidebar-version" :class="{ 'is-collapse': isCollapse }">
            <div class="sidebar-version-main">
              <span class="version-dot" :class="versionSource"></span>
              <strong>{{ isCollapse ? versionShort : versionText }}</strong>
            </div>
            <div v-if="!isCollapse" class="sidebar-version-meta">
              <span class="version-source-inline">{{ versionSourceLabel }}</span>
              <span v-if="versionBuildId">ID {{ versionBuildId }}</span>
            </div>
          </div>
        </el-tooltip>
        <el-tooltip
          :content="`${isCollapse ? t('header.expandSidebar') : t('header.collapseSidebar')} · Ctrl+B`"
          placement="right"
        >
          <button
            type="button"
            class="sidebar-bottom-toggle"
            :aria-label="isCollapse ? t('header.expandSidebar') : t('header.collapseSidebar')"
            @click="toggleCollapse"
          >
            <el-icon :size="16">
              <ArrowRightBold v-if="isCollapse" />
              <ArrowLeftBold v-else />
            </el-icon>
            <span v-if="!isCollapse">{{ t('header.collapseSidebar') }}</span>
          </button>
        </el-tooltip>
      </div>
    </el-aside>

    <!-- 主内容区 -->
    <el-container>
      <el-header class="header">
        <div class="header-left">
          <el-breadcrumb separator="/">
            <el-breadcrumb-item :to="{ path: '/dashboard' }">{{ t('header.home') }}</el-breadcrumb-item>
            <el-breadcrumb-item>{{ currentTitle }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="header-right">
          <el-tooltip
            :content="alertSoundEnabled ? t('header.soundOn') : t('header.soundOff')"
            placement="bottom"
          >
            <el-button text class="sound-toggle" @click="handleToggleAlertSound">
              <el-icon :size="18">
                <svg v-if="alertSoundEnabled" class="sound-svg" viewBox="0 0 24 24" aria-hidden="true">
                  <path fill="currentColor" d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z" />
                </svg>
                <svg v-else class="sound-svg" viewBox="0 0 24 24" aria-hidden="true">
                  <path fill="currentColor" d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3 3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4 9.91 6.09 12 8.18V4z" />
                </svg>
              </el-icon>
            </el-button>
          </el-tooltip>
          <el-tag type="success" effect="plain" size="small">
            {{ t('header.collecting') }}
          </el-tag>
          <span class="tz-tip">{{ timezoneLabel }}</span>
          <el-dropdown trigger="click">
            <span class="user-info">
              <el-icon><User /></el-icon>
              <span>{{ displayName }}</span>
              <el-tag v-if="currentUser.is_superuser" type="danger" size="small" effect="plain">
                {{ t('header.superuser') }}
              </el-tag>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item disabled>
                  {{ currentUser.username || '-' }}
                </el-dropdown-item>
                <el-dropdown-item divided @click="$router.push('/profile')">
                  {{ t('menu.profile') }}
                </el-dropdown-item>
                <el-dropdown-item v-if="currentUser?.is_superuser" @click="$router.push('/system/settings')">
                  {{ t('menu.settings') }}
                </el-dropdown-item>
                <el-dropdown-item divided @click="openChangePassword">
                  {{ t('header.changePassword') }}
                </el-dropdown-item>
                <el-dropdown-item @click="openApiDocs">{{ t('header.apiDocs') }}</el-dropdown-item>
                <el-dropdown-item divided @click="handleLogout">{{ t('header.logout') }}</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>

  <!-- 全局即时通信 / 后台通话与悬浮球（路由切换不销毁） -->
  <ImCallOverlay v-if="canIm" />
  <FloatingBall v-if="canIm && !isFullscreen" />

  <!-- 修改密码 -->
  <el-dialog
    v-model="passwordDialog"
    :title="passwordDialogTitle"
    width="520px"
    class="password-dialog"
    :close-on-click-modal="!passwordRequired"
    :close-on-press-escape="!passwordRequired"
    :show-close="!passwordRequired"
  >
    <el-alert
      v-if="passwordRequired"
      type="warning"
      :closable="false"
      show-icon
      :title="passwordForceHint"
      class="password-alert"
    />
    <el-form :model="passwordForm" label-width="110px" class="password-form">
      <el-form-item :label="t('header.oldPassword')" required>
        <el-input v-model="passwordForm.old_password" type="password" show-password />
      </el-form-item>
      <el-form-item :label="t('header.newPassword')" required>
        <el-input
          v-model="passwordForm.new_password"
          type="password"
          show-password
          :placeholder="t('header.newPasswordPlaceholder')"
        />
        <div class="password-policy-hint">{{ passwordPolicyHint }}</div>
      </el-form-item>
      <el-form-item :label="t('header.confirmPassword')" required>
        <el-input v-model="passwordForm.confirm" type="password" show-password />
      </el-form-item>
    </el-form>
    <template #footer>
      <div class="password-dialog-footer">
        <el-button v-if="!passwordRequired" @click="passwordDialog = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="passwordSaving" @click="submitChangePassword">
          {{ t('common.confirm') }}
        </el-button>
      </div>
    </template>
  </el-dialog>
  </el-config-provider>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { authApi, monitorApi, settingsApi, licenseApi } from '@/api'
import {
  can, currentUser, logout, refreshMe, refreshToken,
} from '@/store/auth'
import { settings, loadPublicSettings, refreshMs } from '@/store/settings'
import { alertSoundEnabled, toggleAlertSound, playAlertSound, loadAlertSoundInfo, unlockAlertAudio, scheduleAlertBroadcast, isAlertBroadcastSpeaking } from '@/utils/alertSound'
import { syncDashboardRulesFromStorage } from '@/utils/dashboardRuleSync'
import { t, locale } from '@/i18n'
import ImCallOverlay from '@/components/ImCallOverlay.vue'
import FloatingBall from '@/components/FloatingBall.vue'
import { connectIM, disconnectIM, unreadTotal } from '@/store/im'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import zhTw from 'element-plus/es/locale/lang/zh-tw'
import enUs from 'element-plus/es/locale/lang/en'
import ja from 'element-plus/es/locale/lang/ja'
import ko from 'element-plus/es/locale/lang/ko'
import de from 'element-plus/es/locale/lang/de'
import fr from 'element-plus/es/locale/lang/fr'
import es from 'element-plus/es/locale/lang/es'
import ptBr from 'element-plus/es/locale/lang/pt-br'
import ru from 'element-plus/es/locale/lang/ru'
import ar from 'element-plus/es/locale/lang/ar'
import hi from 'element-plus/es/locale/lang/hi'

const route = useRoute()
const router = useRouter()
const imUnread = computed(() => Number(unreadTotal.value || 0))
const canIm = computed(() => Boolean(currentUser.value?.id && can('im:view')))
let imAudioUnlocked = false
function unlockImAudio() {
  if (imAudioUnlocked) return
  imAudioUnlocked = true
  unlockAlertAudio()
  window.removeEventListener('pointerdown', unlockImAudio)
  window.removeEventListener('keydown', unlockImAudio)
}

watch([() => currentUser.value?.id, canIm], ([userId, imEnabled]) => {
  if (userId && imEnabled) {
    connectIM()
  } else {
    disconnectIM()
  }
  if (userId) {
    if (!imAudioUnlocked) {
      window.addEventListener('pointerdown', unlockImAudio, { once: true })
      window.addEventListener('keydown', unlockImAudio, { once: true })
    }
  }
}, { immediate: true })
const ELEMENT_LOCALES = {
  'zh-CN': zhCn, 'zh-TW': zhTw, 'en-US': enUs, 'ja-JP': ja, 'ko-KR': ko,
  'de-DE': de, 'fr-FR': fr, 'es-ES': es, 'pt-BR': ptBr, 'ru-RU': ru,
  'ar-SA': ar, 'hi-IN': hi,
}
const epLocale = computed(() => ELEMENT_LOCALES[locale.value] || zhCn)
// 左侧菜单收缩状态（记住用户选择）
const isCollapse = ref(localStorage.getItem('nms_sidebar_collapsed') === '1')
const alertCount = ref(0)
const lastAlertCount = ref(null)
const lastSoundAt = ref(0)
let alertTimer = null
let idleTimer = null
let displayKeepAliveTimer = null
let permissionTimer = null

// 大屏页面已移除，菜单统一使用路由跳转
function handleMenuSelect(index) {
  if (route.path !== index) router.push(index)
}

const isFullscreen = computed(
  () => route.meta?.layout === 'immersive' || route.meta?.layout === 'blank'
)

// 大屏/机房数字孪生是长期展示页签：不受空闲注销影响，并定时静默续期。
function isDisplayPage() {
  return route.meta?.layout === 'immersive'
    || String(route.path || '').startsWith('/bigscreen')
    || /^\/rooms\/[^/]+\/showcase/.test(String(route.path || ''))
}

function syncDisplayKeepAlive() {
  if (displayKeepAliveTimer) {
    clearInterval(displayKeepAliveTimer)
    displayKeepAliveTimer = null
  }
  if (!isDisplayPage()) return
  refreshToken(true).catch(() => {})
  displayKeepAliveTimer = setInterval(() => {
    if (isDisplayPage()) refreshToken(true).catch(() => {})
  }, 30 * 60 * 1000)
}

const systemName = computed(() => settings.system_name || t('header.defaultSystemName'))
const timezoneLabel = computed(() => settings.timezone || '')

// 侧边栏版本信息：全部由构建时自动生成
const versionInfo = ref(null)
const licenseFeatures = ref(null)
const versionData = computed(() => versionInfo.value?.effective || null)
const versionText = computed(() => {
  const value = String(versionData.value?.display_version || versionData.value?.version || '').trim()
  if (!value) return ''
  return value.startsWith('v') ? value : `v${value}`
})
const versionShort = computed(() => {
  const value = String(versionData.value?.version || '').trim()
  if (!value) return versionText.value
  return value.startsWith('v') ? value : `v${value}`
})
const versionBuild = computed(() => String(versionData.value?.build || '').trim())
const versionBuildId = computed(() => String(versionData.value?.build_id || '').trim())
const versionSource = computed(() => versionData.value?.source || 'fallback')
const versionSourceLabel = computed(() => {
  const key = `version.source.${versionSource.value}`
  return t(key)
})
const versionBuiltAt = computed(() => {
  const raw = versionData.value?.built_at
  if (!raw) return ''
  const date = new Date(raw)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString(locale.value || 'zh-CN', { hour12: false })
})
const versionTooltip = computed(() => {
  if (!versionData.value) return ''
  const parts = [`${versionText.value} · ${versionSourceLabel.value}`]
  if (versionBuild.value) parts.push(`${t('version.build')} ${versionBuild.value}`)
  if (versionBuildId.value) parts.push(`ID ${versionBuildId.value}`)
  if (versionBuiltAt.value) parts.push(versionBuiltAt.value)
  return parts.join(' · ')
})

async function loadVersionInfo() {
  try {
    const res = await settingsApi.version()
    versionInfo.value = res.data || null
  } catch {
    versionInfo.value = null
  }
}

async function ensureLicenseUsable() {
  try {
    const res = await licenseApi.publicStatus()
    licenseFeatures.value = Array.isArray(res.data?.features) ? res.data.features : null
    if (res.data?.status === 'expired') {
      logout()
      return false
    }
  } catch {
    /* 授权状态接口异常时交由后端 API 拦截 */
  }
  return true
}

const displayName = computed(
  () => currentUser.value?.real_name || currentUser.value?.username || t('header.notLoggedIn')
)

// 修改密码
const passwordDialog = ref(false)
const passwordForm = ref({ old_password: '', new_password: '', confirm: '' })
const passwordSaving = ref(false)
const passwordRequired = computed(() => !!currentUser.value?.password_change_required)
const passwordChangeReason = computed(() => currentUser.value?.password_change_reason || '')
const passwordDialogTitle = computed(() => {
  if (!passwordRequired.value) return t('header.changePassword')
  return passwordChangeReason.value === 'first_login'
    ? t('header.passwordFirstLoginTitle')
    : t('header.passwordExpiredTitle')
})
const passwordForceHint = computed(() => (
  passwordChangeReason.value === 'first_login'
    ? t('header.passwordFirstLoginHint')
    : t('header.passwordExpiredHint')
))
const passwordPolicyHint = computed(() => {
  const min = Number(settings.password_min_length) || 8
  const parts = [t('settings.passwordMinDynamic', { min })]
  if (settings.password_require_uppercase) parts.push(t('settings.passwordUppercase'))
  if (settings.password_require_lowercase) parts.push(t('settings.passwordLowercase'))
  if (settings.password_require_digit) parts.push(t('settings.passwordDigit'))
  if (settings.password_require_special) parts.push(t('settings.passwordSpecial'))
  return parts.join(' · ')
})

watch(passwordRequired, (required) => {
  if (!required) return
  passwordForm.value = { old_password: '', new_password: '', confirm: '' }
  passwordDialog.value = true
}, { immediate: true })

// 左侧菜单定义：顺序可由用户拖拽调整并记住
const MENU_ORDER_KEY = 'nms_menu_order_v1'
const MENU_DEFS = [
  { key: 'instrument', index: '/instrument', permission: 'monitor:view', icon: 'Odometer', labelKey: 'menu.instrumentDashboard' },
  { key: 'dashboard', index: '/dashboard', permission: 'monitor:view', icon: 'DataAnalysis', labelKey: 'menu.dashboard' },
  { key: 'bigscreen', index: '/bigscreen', permission: 'bigscreen:view', icon: 'DataBoard', labelKey: 'menu.bigscreen' },
  { key: 'ai', index: '/ai', permission: 'ai:view', icon: 'MagicStick', labelKey: 'menu.aiOps', feature: 'ai' },
  { key: 'cascade', index: '/cascade', permission: 'cascade:view', icon: 'Connection', labelKey: 'menu.cascade', superuserOnly: true, feature: 'cascade' },
  { key: 'devices', index: '/devices', permission: 'assets:view', icon: 'Monitor', labelKey: 'menu.assets' },
  { key: 'mibs', index: '/mibs', permission: 'mib:view', icon: 'Document', labelKey: 'menu.mibs' },
  { key: 'rooms', index: '/rooms', permission: 'rooms:view', icon: 'OfficeBuilding', labelKey: 'menu.rooms' },
  { key: 'topology', index: '/topology', permission: 'topology:view', icon: 'Connection', labelKey: 'menu.topology' },
  { key: 'virtualization', index: '/virtualization', permission: 'virtualization:view', icon: 'Cpu', labelKey: 'menu.virtualization' },
  { key: 'website', index: '/website', permission: 'website:view', icon: 'ChromeFilled', labelKey: 'menu.website' },
  { key: 'alerts', index: '/alerts', permission: 'monitor:view', icon: 'Bell', labelKey: 'menu.alerts', badge: true },
  { key: 'notifications', index: '/notifications', permission: 'notifications:view', icon: 'Message', labelKey: 'menu.notifications', superuserOnly: true },
  { key: 'discovery', index: '/discovery', permission: 'discovery:view', icon: 'Aim', labelKey: 'menu.discovery' },
  { key: 'im', index: '/im', permission: 'im:view', icon: 'ChatDotRound', labelKey: 'menu.im' },
  { key: 'inspection', index: '/inspection', permission: 'inspection:view', icon: 'DocumentChecked', label: '设备巡检', labelKey: 'menu.inspection' },
  { key: 'configBackups', index: '/config-backups', permission: 'config_backup:view', icon: 'FolderOpened', labelKey: 'menu.configBackups' },
  { key: 'credentials', index: '/credentials', permission: 'credentials:view', icon: 'Key', label: '设备凭据' },
  { key: 'audit', index: '/system/audit', permission: 'audit:view', icon: 'Document', labelKey: 'menu.audit' },
  { key: 'tools', index: '/tools', permission: 'tools:view', icon: 'Tools', labelKey: 'menu.tools' },
  { key: 'profile', index: '/profile', permission: null, icon: 'User', labelKey: 'menu.profile' },
  { key: 'settings', index: '/system/settings', permission: 'settings:view', icon: 'Setting', labelKey: 'menu.settings', pinnedBottom: true, superuserOnly: true },
  { key: 'license', index: '/system/license', permission: 'license:view', icon: 'Key', labelKey: 'menu.license', pinnedBottom: true, superuserOnly: true },
]

const BOTTOM_MENU_KEYS = ['settings', 'license']
const BOTTOM_MENU_SET = new Set(BOTTOM_MENU_KEYS)
const PINNED_BOTTOM_KEYS = new Set(MENU_DEFS.filter((item) => item.pinnedBottom).map((item) => item.key))

function isPinnedBottom(key) {
  return PINNED_BOTTOM_KEYS.has(key)
}

function isBottomMenuItem(key) {
  return BOTTOM_MENU_SET.has(key)
}

function normalizeMenuOrder() {
  const defaults = MENU_DEFS.map((item) => item.key)
  const draggableDefaults = defaults.filter((key) => !isBottomMenuItem(key))
  let saved = []
  try {
    const parsed = JSON.parse(localStorage.getItem(MENU_ORDER_KEY) || '[]')
    if (Array.isArray(parsed)) saved = parsed
  } catch {
    saved = []
  }
  const valid = [...new Set(saved.filter((key) => draggableDefaults.includes(key)))]
  const result = [...valid]
  draggableDefaults.forEach((key, index) => {
    if (result.includes(key)) return
    let insertAt = result.length
    for (let prev = index - 1; prev >= 0; prev -= 1) {
      const pos = result.indexOf(draggableDefaults[prev])
      if (pos >= 0) {
        insertAt = pos + 1
        break
      }
    }
    result.splice(insertAt, 0, key)
  })
  return [...result, ...BOTTOM_MENU_KEYS]
}

const menuOrder = ref(normalizeMenuOrder())
const draggingMenuKey = ref(null)
let menuDragGhost = null
let menuDragOrigin = null
let menuDragOffsetX = 0
let menuDragOffsetY = 0
let menuDragLastTarget = ''
const visibleMenus = computed(() => {
  const menus = menuOrder.value
    .map((key) => MENU_DEFS.find((item) => item.key === key))
    .filter((item) => item && (!item.permission || can(item.permission)) && (!item.superuserOnly || currentUser.value?.is_superuser) && (!item.feature || !licenseFeatures.value || licenseFeatures.value.includes(item.feature)))
  const base = menus.filter((item) => !isBottomMenuItem(item.key))
  const bottom = BOTTOM_MENU_KEYS
    .map((key) => menus.find((item) => item.key === key))
    .filter(Boolean)
  return [...base, ...bottom]
})

const mainMenus = computed(() => visibleMenus.value.filter((item) => !isBottomMenuItem(item.key)))
const bottomMenus = computed(() => visibleMenus.value.filter((item) => isBottomMenuItem(item.key)))

function captureMenuRects() {
  const rects = new Map()
  document.querySelectorAll('.sidebar-menu-item').forEach((node) => {
    rects.set(node.dataset.menuKey, node.getBoundingClientRect())
  })
  return rects
}

function animateMenuReorder(beforeRects) {
  document.querySelectorAll('.sidebar-menu-item').forEach((node) => {
    const before = beforeRects.get(node.dataset.menuKey)
    if (!before) return
    const after = node.getBoundingClientRect()
    const deltaY = before.top - after.top
    if (Math.abs(deltaY) < 1) return
    node.style.transition = 'none'
    node.style.transform = `translateY(${deltaY}px)`
    node.style.zIndex = '1'
    requestAnimationFrame(() => {
      node.style.transition = 'transform 0.2s cubic-bezier(0.22, 1, 0.36, 1)'
      node.style.transform = 'translateY(0)'
      window.setTimeout(() => {
        node.style.transition = ''
        node.style.transform = ''
        node.style.zIndex = ''
      }, 230)
    })
  })
}

function createMenuDragGhost(element, event) {
  const rect = element.getBoundingClientRect()
  const ghost = element.cloneNode(true)
  ghost.classList.add('menu-drag-ghost')
  ghost.classList.remove('sidebar-menu-item', 'is-active', 'is-menu-dragging', 'is-drag-origin')
  ghost.querySelectorAll('.menu-drag-handle').forEach((node) => node.remove())
  ghost.style.width = `${Math.max(150, rect.width - 16)}px`
  ghost.style.height = `${rect.height}px`
  ghost.style.left = '0'
  ghost.style.top = '0'
  ghost.style.transform = `translate3d(8px, ${rect.top}px, 0)`
  document.body.appendChild(ghost)
  menuDragOffsetX = 0
  menuDragOffsetY = event.clientY - rect.top
  menuDragGhost = ghost
  menuDragOrigin = element
}

function moveMenuGhost(event) {
  if (!menuDragGhost) return
  menuDragGhost.style.transform = `translate3d(8px, ${event.clientY - menuDragOffsetY}px, 0)`
}

function startMenuDrag(event, item) {
  if (isCollapse.value || isBottomMenuItem(item.key)) return
  draggingMenuKey.value = item.key
  menuDragLastTarget = ''
  const origin = document.querySelector(`.sidebar-menu-item[data-menu-key="${item.key}"]`)
  if (origin) createMenuDragGhost(origin, event)
  document.body.classList.add('menu-sorting')
  document.addEventListener('pointermove', onMenuDragMove)
  document.addEventListener('pointerup', stopMenuDrag)
  document.addEventListener('pointercancel', stopMenuDrag)
}

function onMenuDragMove(event) {
  if (!draggingMenuKey.value) return
  moveMenuGhost(event)
  const element = document.elementFromPoint(event.clientX, event.clientY)
  const targetItem = element?.closest('.sidebar-menu-item')
  if (!targetItem || targetItem.classList.contains('is-drag-origin')) return
  const targetKey = targetItem.dataset.menuKey
  if (!targetKey || targetKey === draggingMenuKey.value) return
  if (isBottomMenuItem(targetKey)) return
  const rect = targetItem.getBoundingClientRect()
  const after = event.clientY > rect.top + rect.height / 2
  const directionKey = `${targetKey}:${after ? 'after' : 'before'}`
  if (directionKey === menuDragLastTarget) return
  menuDragLastTarget = directionKey
  const bottomKeys = menuOrder.value.filter((key) => isBottomMenuItem(key))
  const order = menuOrder.value.filter((key) => !isBottomMenuItem(key))
  const from = order.indexOf(draggingMenuKey.value)
  if (from < 0) return
  const beforeRects = captureMenuRects()
  order.splice(from, 1)
  let insertAt = order.indexOf(targetKey)
  if (insertAt < 0) return
  if (after) insertAt += 1
  order.splice(insertAt, 0, draggingMenuKey.value)
  menuOrder.value = [...order, ...bottomKeys]
  nextTick(() => animateMenuReorder(beforeRects))
}

function stopMenuDrag() {
  if (draggingMenuKey.value) {
    try {
      localStorage.setItem(MENU_ORDER_KEY, JSON.stringify(menuOrder.value))
    } catch {
      /* 忽略存储异常 */
    }
  }
  if (menuDragGhost) {
    const ghost = menuDragGhost
    const finalItem = document.querySelector(`.sidebar-menu-item[data-menu-key="${draggingMenuKey.value}"]`)
    if (finalItem) {
      const rect = finalItem.getBoundingClientRect()
      ghost.style.transition = 'transform 0.18s ease, opacity 0.18s ease'
      ghost.style.transform = `translate3d(${rect.left}px, ${rect.top}px, 0)`
      ghost.style.opacity = '0'
    } else {
      ghost.style.opacity = '0'
    }
    window.setTimeout(() => ghost.remove(), 190)
    menuDragGhost = null
  }
  if (menuDragOrigin) {
    menuDragOrigin = null
  }
  draggingMenuKey.value = null
  menuDragLastTarget = ''
  document.body.classList.remove('menu-sorting')
  document.removeEventListener('pointermove', onMenuDragMove)
  document.removeEventListener('pointerup', stopMenuDrag)
  document.removeEventListener('pointercancel', stopMenuDrag)
}

const activeMenu = computed(() => {
  // 子页面高亮父级菜单
  const path = route.path
  if (path.startsWith('/devices') || path.startsWith('/assets')) return '/devices'
  if (path.startsWith('/bigscreen')) return '/bigscreen'
  if (path.startsWith('/website')) return '/website'
  if (path.startsWith('/system/users')) return '/system/users'
  if (path.startsWith('/system/settings')) return '/system/settings'
  return path
})

const currentTitle = computed(() => {
  const titles = {
    '/instrument': t('menu.instrumentDashboard'),
    '/dashboard': t('menu.dashboard'),
    '/bigscreen': t('menu.bigscreen'),
  '/ai': t('menu.aiOps'),
  '/cascade': t('menu.cascade'),
  '/ai-screen': t('menu.aiOpsScreen'),
    '/devices': t('menu.assets'),
    '/templates': t('menu.templates'),
    '/discovery': t('menu.discovery'),
    '/inspection': '设备巡检',
    '/config-backups': t('menu.configBackups'),
    '/credentials': '设备凭据',
    '/tools': t('menu.tools'),
    '/im': t('menu.im'),
    '/mibs': t('menu.mibs'),
    '/devices/add': t('asset.form.addDevice'),
    '/topology': t('menu.topology'),
    '/virtualization': t('menu.virtualization'),
    '/rooms': t('menu.rooms'),
    '/alerts': t('menu.alerts'),
    '/notifications': t('menu.notifications'),
    '/website': t('menu.website'),
    '/website/add': t('website.addWebsite'),
    '/system/users': t('menu.users'),
    '/profile': t('menu.profile'),
    '/system/settings': t('menu.settings'),
    '/system/license': t('menu.license'),
    '/system/audit': t('menu.audit'),
  }
  const path = route.path
  if (path.startsWith('/devices/edit') || path.startsWith('/assets/edit')) return t('asset.form.editDevice')
  if (path.startsWith('/devices/copy')) return t('asset.form.copyDevice')
  if (path === '/website/certificates') return '证书管理'
  if (path.startsWith('/website/edit')) return t('website.editWebsite')
  if (/^\/(devices|assets)\/[^/]+$/.test(path)) return t('device.detailTitle')
  if (path.startsWith('/website/')) return t('website.detailTitle')
  return titles[path] || ''
})

function toggleCollapse() {
  isCollapse.value = !isCollapse.value
  try {
    localStorage.setItem('nms_sidebar_collapsed', isCollapse.value ? '1' : '0')
  } catch {
    /* 忽略存储异常 */
  }
}

function handleToggleAlertSound() {
  const enabled = toggleAlertSound()
  if (enabled) {
    ElMessage.success(t('header.soundOnToast'))
  } else {
    ElMessage.info(t('header.soundOffToast'))
  }
}

function handleSidebarShortcut(event) {
  if (!(event.ctrlKey || event.metaKey) || event.altKey) return
  if (String(event.key).toLowerCase() !== 'b') return
  const tag = event.target?.tagName
  if (['INPUT', 'TEXTAREA', 'SELECT'].includes(tag) || event.target?.isContentEditable) return
  event.preventDefault()
  toggleCollapse()
}

async function fetchAlertCount() {
  if (!can('monitor:view')) return
  try {
    const res = await monitorApi.getBroadcastAlerts()
    const alerts = res.data || []
    const count = alerts.length
    const levelRank = { info: 0, warning: 1, critical: 2, emergency: 3 }
    const highestLevel = alerts.reduce(
      (level, alert) => ((levelRank[alert.alert_level] ?? 1) > (levelRank[level] ?? 1) ? alert.alert_level : level),
      'info',
    )
    const now = Date.now()
    const repeatMs = Math.max(10, Number(settings.alert_sound_interval) || 60) * 1000
    if (count > 0) {
      // 有未处理告警时：首次加载、新增告警、或距上次响铃达到配置间隔后提醒
      const firstLoad = lastAlertCount.value === null
      const increased = lastAlertCount.value !== null && count > lastAlertCount.value
      const repeat = !lastSoundAt.value || now - lastSoundAt.value >= repeatMs
      const broadcasting = isAlertBroadcastSpeaking()
      if (!broadcasting && (firstLoad || increased || repeat) && alertSoundEnabled.value) {
        playAlertSound(highestLevel)
        scheduleAlertBroadcast(alerts, {
          enabled: settings.alert_broadcast_enabled,
          counts: settings.alert_broadcast_counts,
          details: settings.alert_broadcast_details,
          levels: settings.alert_broadcast_levels,
          maxItems: 0,
          onEnd: () => {
            // 详细播报结束的时间作为下一次声音提醒的起点，避免长播报被间隔打断/重复
            lastSoundAt.value = Date.now()
          },
        })
        lastSoundAt.value = now
      }
    } else {
      lastSoundAt.value = 0
    }
    lastAlertCount.value = count
    alertCount.value = count
  } catch {
    /* 忽略 */
  }
}

function openApiDocs() {
  window.open('/docs', '_blank')
}

function openChangePassword() {
  passwordForm.value = { old_password: '', new_password: '', confirm: '' }
  passwordDialog.value = true
}

async function submitChangePassword() {
  const { old_password, new_password, confirm } = passwordForm.value
  if (!old_password || !new_password) {
    ElMessage.warning(t('header.passwordRequired'))
    return
  }
  if (new_password.length < 6) {
    ElMessage.warning(t('header.passwordMin6'))
    return
  }
  if (new_password !== confirm) {
    ElMessage.warning(t('header.passwordMismatch'))
    return
  }
  passwordSaving.value = true
  const forced = passwordRequired.value
  try {
    await authApi.changePassword({ old_password, new_password })
    passwordDialog.value = false
    if (forced) {
      await refreshMe()
      ElMessage.success(t('header.passwordChanged'))
      return
    }
    ElMessage.success(t('header.passwordChanged'))
    setTimeout(() => logout(), 800)
  } catch (e) {
    ElMessage.error(e.message || t('header.changeFailed'))
  } finally {
    passwordSaving.value = false
  }
}

function handleLogout() {
  logout()
}

// ==================== 自动注销（无操作超时） ====================
function resetIdleTimer() {
  if (idleTimer) {
    clearTimeout(idleTimer)
    idleTimer = null
  }
  if (isDisplayPage()) return
  const minutes = Number(settings.auto_logout_minutes) || 0
  if (minutes <= 0 || route.meta?.public) return
  idleTimer = setTimeout(() => {
    ElMessage.warning(t('idle.logout'))
    setTimeout(() => logout(), 800)
  }, minutes * 60 * 1000)
}

const ACTIVE_EVENTS = ['mousemove', 'mousedown', 'keydown', 'wheel', 'touchstart']
function bindIdleEvents() {
  ACTIVE_EVENTS.forEach((evt) => window.addEventListener(evt, resetIdleTimer, { passive: true }))
}
function unbindIdleEvents() {
  ACTIVE_EVENTS.forEach((evt) => window.removeEventListener(evt, resetIdleTimer))
}

// ==================== 定时器 ====================
function startAlertTimer() {
  if (alertTimer) clearInterval(alertTimer)
  // 角标最多 10 秒刷新一次；告警中心页面还会触发即时刷新事件
  alertTimer = setInterval(fetchAlertCount, Math.min(refreshMs(), 10000))
}

let alertsUpdatedTimer = null
function onAlertsUpdated() {
  if (alertsUpdatedTimer) clearTimeout(alertsUpdatedTimer)
  alertsUpdatedTimer = setTimeout(() => {
    if (!route.meta?.public) fetchAlertCount()
  }, 120)
}

watch(
  () => settings.refresh_interval,
  () => {
    if (!route.meta?.public) startAlertTimer()
  }
)
watch(
  () => settings.auto_logout_minutes,
  () => resetIdleTimer()
)

// 浏览器标签标题：沉浸式页面与页面名称一致，其它页面为「页面名 - 系统名」
const pageTitle = computed(() => {
  if (route.meta?.public) return ''
  return route.meta?.title || ''
})
const documentTitle = computed(() => {
  if (!pageTitle.value) return systemName.value
  if (route.meta?.layout === 'immersive') return pageTitle.value
  return `${pageTitle.value} - ${systemName.value}`
})
watch(documentTitle, (title) => {
  document.title = title
}, { immediate: true })

// 登录后加载自定义告警声音配置
watch(
  () => currentUser.username,
  (username) => {
    if (username) loadAlertSoundInfo()
  },
  { immediate: true }
)

// 从登录页等公开页面进入管理页面后，启动告警轮询/空闲注销
watch(
  () => route.meta?.public,
  (isPublic) => {
    if (!isPublic) {
      loadVersionInfo()
      fetchAlertCount()
      startAlertTimer()
      bindIdleEvents()
      resetIdleTimer()
      syncDisplayKeepAlive()
    }
  }
)

watch(
  () => route.fullPath,
  () => {
    resetIdleTimer()
    syncDisplayKeepAlive()
  }
)

function onAiFunctionFocus(event) {
  if (event.key !== 'nms_ai_function_focus' || !event.newValue) return
  try {
    const data = JSON.parse(event.newValue)
    if (!data?.path || Date.now() - Number(data.at || 0) > 12000) return
    if (String(route.path || '').startsWith('/ai-screen')) return
    localStorage.setItem('nms_ai_function_focus_ack', String(data.at))
    router.push(data.path).then(() => {
      nextTick(() => {
        const target = document.querySelector(`[data-ai-focus="${data.tool || ''}"]`)
        target?.scrollIntoView({ behavior: 'smooth', block: 'center' })
        try { window.focus() } catch { /* browser may ignore */ }
      })
    }).catch(() => { /* duplicate route */ })
  } catch { /* ignore malformed focus event */ }
}

async function refreshPermissions() {
  if (route.meta?.public) return
  await refreshMe()
  const need = route.meta?.permission
  if (need && !can(need)) {
    ElMessage.warning('当前账号的功能权限已变更，请重新登录或联系管理员')
    router.replace('/profile').catch(() => {})
  }
}

function onPermissionVisibilityChange() {
  if (!document.hidden) refreshPermissions()
}

onMounted(async () => {
  if (route.meta?.public) return
  await loadPublicSettings()
  if (!(await ensureLicenseUsable())) return
  await loadVersionInfo()
  await refreshMe()
  permissionTimer = setInterval(refreshPermissions, 10000)
  document.addEventListener('visibilitychange', onPermissionVisibilityChange)
  window.addEventListener('focus', refreshPermissions)
  if (currentUser.value?.id) syncDashboardRulesFromStorage().catch(() => {})
  fetchAlertCount()
  startAlertTimer()
  bindIdleEvents()
  resetIdleTimer()
  syncDisplayKeepAlive()
  window.addEventListener('nms:alerts-updated', onAlertsUpdated)
  window.addEventListener('keydown', handleSidebarShortcut)
  window.addEventListener('storage', onAiFunctionFocus)
})

onBeforeUnmount(() => {
  if (alertTimer) clearInterval(alertTimer)
  if (idleTimer) clearTimeout(idleTimer)
  if (displayKeepAliveTimer) clearInterval(displayKeepAliveTimer)
  if (permissionTimer) clearInterval(permissionTimer)
  document.removeEventListener('visibilitychange', onPermissionVisibilityChange)
  window.removeEventListener('focus', refreshPermissions)
  unbindIdleEvents()
  window.removeEventListener('nms:alerts-updated', onAlertsUpdated)
  if (alertsUpdatedTimer) clearTimeout(alertsUpdatedTimer)
  stopMenuDrag()
  disconnectIM()
  window.removeEventListener('keydown', handleSidebarShortcut)
  window.removeEventListener('storage', onAiFunctionFocus)
})
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html, body, #app {
  height: 100%;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Microsoft YaHei', Arial, sans-serif;
}

/* 全站表格表头标签统一居中，不影响单元格内容与列宽拖拽 */
.el-table th.el-table__cell > .cell {
  text-align: center !important;
}

/* 表头对应列的正文内容同步居中 */
.el-table td.el-table__cell > .cell {
  text-align: center !important;
}

/* 正文文字按当前列宽自动换行，列宽拖拽后自适应 */
.el-table td.el-table__cell > .cell {
  white-space: normal !important;
  word-break: break-word;
  overflow-wrap: anywhere;
  text-overflow: clip;
  line-height: 1.45;
}

.app-container {
  height: 100vh;
}

.sidebar {
  background-color: #001529;
  transition: width 0.3s;
  display: flex;
  flex-direction: column;
  overflow-x: hidden;
}

.logo {
  position: relative;
  min-height: 64px;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 10px;
  padding: 9px 14px;
  color: #fff;
  font-size: 15px;
  font-weight: bold;
  line-height: 1.25;
  border-bottom: 1px solid #ffffff1a;
  overflow: hidden;
}

.logo > .el-icon {
  flex-shrink: 0;
}

.logo-image {
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  object-fit: contain;
  border-radius: 7px;
}

.logo-text {
  flex: 1;
  min-width: 0;
  white-space: normal;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.sidebar .el-menu {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, 0.38) transparent;
}

.sidebar .el-menu::-webkit-scrollbar {
  width: 4px;
  height: 4px;
}

.sidebar .el-menu::-webkit-scrollbar-track {
  background: transparent;
}

.sidebar .el-menu::-webkit-scrollbar-thumb {
  min-height: 32px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.32);
  transition: background 0.2s ease;
}

.sidebar .el-menu:hover::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.56);
}

.sidebar .el-menu::-webkit-scrollbar-button {
  display: none;
  width: 0;
  height: 0;
}

.sidebar .el-menu::-webkit-scrollbar-corner {
  background: transparent;
}

.sidebar .el-menu-item {
  height: 48px;
  line-height: 48px;
}

.sidebar .sidebar-bottom-menu {
  flex: 0 0 auto;
  min-height: 0;
  overflow: visible;
  border-top: 1px solid rgba(148, 163, 184, 0.12);
}

.sidebar.is-collapse .logo {
  justify-content: center;
  padding: 9px 0;
}

/* 收起时隐藏菜单分组标题，避免文字挤压换行 */
.sidebar.is-collapse .el-menu-item-group__title {
  display: none;
}

.menu-badge {
  margin-left: 8px;
}

/* 告警数量徽标：固定在菜单项右侧，垂直居中 */
.alerts-menu-item {
  position: relative;
}

.sidebar-menu-item {
  position: relative;
  padding-right: 38px !important;
}

.sidebar-menu-item.is-pinned-bottom {
  margin-top: 8px;
  padding-right: 20px !important;
  border-top: 1px solid rgba(148, 163, 184, 0.16);
}

.sidebar-menu-item:hover {
  background: #ffffff0d;
}

.sidebar-menu-item.is-menu-dragging {
  background: rgba(56, 189, 248, 0.18);
}

.menu-drag-handle {
  position: absolute;
  right: 6px;
  top: 50%;
  z-index: 2;
  width: 24px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transform: translateY(-50%);
  border-radius: 5px;
  color: #94a3b8;
  opacity: 0;
  pointer-events: none;
  cursor: grab;
  touch-action: none;
  transition: opacity 0.15s ease, color 0.15s ease, background 0.15s ease;
}

.sidebar-menu-item:hover .menu-drag-handle,
.sidebar-menu-item.is-menu-dragging .menu-drag-handle {
  opacity: 1;
  pointer-events: auto;
}

.menu-drag-handle:hover {
  color: #7dd3fc;
  background: rgba(56, 189, 248, 0.16);
}

.menu-drag-handle:active {
  cursor: grabbing;
}

.sidebar-menu-item.is-drag-origin {
  opacity: 0.28;
}

.menu-drag-ghost {
  position: fixed;
  top: 0;
  left: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0;
  padding: 0 16px !important;
  border: 1px solid rgba(56, 189, 248, 0.75);
  border-radius: 7px;
  background: linear-gradient(90deg, #0b2a45, #0c2238) !important;
  color: #e0f2fe !important;
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.42), 0 0 0 1px rgba(56, 189, 248, 0.15);
  pointer-events: none;
  list-style: none;
  white-space: nowrap;
  overflow: hidden;
  opacity: 0.96;
}

.menu-drag-ghost .menu-drag-handle {
  display: none;
}

.menu-drag-ghost .el-icon {
  color: #7dd3fc;
}

.sidebar.is-collapse .sidebar-menu-item {
  padding-right: 0 !important;
}

.sidebar.is-collapse .menu-drag-handle {
  display: none;
}

body.menu-sorting {
  cursor: grabbing;
  user-select: none;
}

.alert-count-badge {
  position: absolute;
  right: 38px;
  top: 50%;
  transform: translateY(-50%);
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 9px;
  background: #f56c6c;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  line-height: 18px;
  text-align: center;
  box-sizing: border-box;
  pointer-events: none;
}

.im-message-badge {
  background: linear-gradient(135deg, #0ea5e9, #0891b2);
  box-shadow: 0 0 8px rgba(14, 165, 233, .5);
}

.sidebar.is-collapse .im-message-badge {
  right: 3px;
  top: 6px;
  transform: none;
  min-width: 15px;
  height: 15px;
  line-height: 15px;
  font-size: 9px;
  padding: 0 3px;
}

@media (hover: none) {
  .sidebar-menu-item .menu-drag-handle {
    opacity: 0.6;
    pointer-events: auto;
  }
}

.header {
  background: #fff;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  z-index: 10;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.tz-tip {
  margin-right: 12px;
  color: #94a3b8;
  font-size: 12px;
}

/* 侧边栏底部：常驻的收起/展开入口 */
.sidebar-footer {
  flex-shrink: 0;
  padding: 10px;
  border-top: 1px solid #ffffff1a;
  background: rgba(0, 21, 41, 0.72);
}

.sidebar-version {
  margin-bottom: 8px;
  padding: 8px 9px;
  border: 1px solid rgba(56, 189, 248, 0.13);
  border-radius: 8px;
  background: linear-gradient(135deg, rgba(14, 165, 233, 0.08), rgba(2, 20, 40, 0.25));
  cursor: default;
  transition: border-color 0.2s ease, background 0.2s ease;
}

.sidebar-version:hover {
  border-color: rgba(56, 189, 248, 0.32);
  background: linear-gradient(135deg, rgba(14, 165, 233, 0.12), rgba(2, 20, 40, 0.3));
}

.sidebar-version.is-collapse {
  display: flex;
  justify-content: center;
  padding: 7px 4px;
}

.sidebar-version-main {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
}

.sidebar-version-main strong {
  min-width: 0;
  overflow: hidden;
  color: #d8f3ff;
  font-family: Consolas, monospace;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.1px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.version-dot {
  width: 5px;
  height: 5px;
  flex-shrink: 0;
  border-radius: 50%;
  background: #38bdf8;
  box-shadow: 0 0 7px rgba(56, 189, 248, 0.75);
}

.version-dot.auto {
  background: #34d399;
  box-shadow: 0 0 7px rgba(52, 211, 153, 0.75);
}

.sidebar-version-meta {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-top: 4px;
  padding-left: 11px;
  overflow: hidden;
  color: #607f93;
  font-family: Consolas, monospace;
  font-size: 8px;
  line-height: 1.3;
  white-space: nowrap;
}

.sidebar-version-meta span {
  overflow: hidden;
  text-overflow: ellipsis;
}

.version-source-inline {
  flex-shrink: 0;
  color: #5fae95;
}

.sidebar.is-collapse .sidebar-version-main strong {
  font-size: 9px;
}

.sidebar.is-collapse .sidebar-version {
  margin-bottom: 6px;
}

.sidebar-bottom-toggle {
  width: 100%;
  height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 7px;
  background: rgba(148, 163, 184, 0.08);
  color: #cbd5e1;
  font-size: 11px;
  cursor: pointer;
  transition: color 0.18s ease, border-color 0.18s ease, background 0.18s ease;
}

.sidebar-bottom-toggle:hover {
  color: #fff;
  border-color: rgba(125, 211, 252, 0.6);
  background: rgba(56, 189, 248, 0.18);
}

.sidebar-bottom-toggle:focus-visible {
  outline: 2px solid #7dd3fc;
  outline-offset: 2px;
}

.sidebar.is-collapse .sidebar-footer {
  padding: 10px 6px;
}

.sidebar.is-collapse .sidebar-bottom-toggle {
  width: 100%;
  padding: 0;
}

@media (max-width: 900px) {
  .sidebar-footer {
    padding: 8px 6px;
  }
}

.sidebar.is-collapse .el-menu-item-group__title {
  display: none;
}

.sound-toggle {
  color: #606266;
  padding: 4px;
}

.sound-toggle:hover {
  color: #e6a23c;
}

.sound-svg {
  width: 18px;
  height: 18px;
  display: block;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  color: #333;
}

.main-content {
  background: #f0f2f5;
  padding: 20px;
  overflow-y: auto;
}

/* 修改密码弹窗 */
.password-dialog {
  border-radius: 14px;
  overflow: hidden;
}
.password-dialog .el-dialog__header {
  margin: 0;
  padding: 20px 24px 10px;
}
.password-dialog .el-dialog__body {
  padding: 6px 24px 4px;
}
.password-dialog .el-dialog__footer {
  padding: 14px 24px 20px;
  border-top: 1px solid #eef2f6;
}
.password-alert {
  margin-bottom: 18px;
  border-radius: 9px;
}
.password-form .el-form-item {
  margin-bottom: 20px;
}
.password-form .el-form-item__label {
  padding-right: 14px;
  color: #48606f;
  font-weight: 500;
  line-height: 1.4;
}
.password-form .el-form-item__content {
  min-width: 0;
}
.password-form .el-input__wrapper {
  min-height: 40px;
}
.password-policy-hint {
  margin-top: 7px;
  color: #8a9cac;
  font-size: 11px;
  line-height: 1.5;
}
.password-dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
.password-dialog-footer .el-button {
  min-width: 82px;
  margin-left: 0;
}
@media (max-width: 600px) {
  .password-dialog {
    width: calc(100vw - 28px) !important;
    margin-top: 8vh !important;
  }
  .password-dialog .el-dialog__header {
    padding: 16px 18px 8px;
  }
  .password-dialog .el-dialog__body {
    padding: 6px 18px 4px;
  }
  .password-dialog .el-dialog__footer {
    padding: 12px 18px 16px;
  }
  .password-form .el-form-item__label {
    width: 104px !important;
    padding-right: 8px;
  }
}

/* 全局表格与表单内容居中标准 */
.el-table th.el-table__cell,
.el-table td.el-table__cell {
  text-align: center;
}

.el-form-item__content {
  justify-content: center;
  text-align: center;
}

</style>
