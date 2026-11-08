<template>
  <div
    v-if="imState.preferences.enabled !== false"
    class="fb-root"
    :class="{ 'edge-hidden': edgeHidden, [`edge-${edgeSide}`]: edgeHidden }"
    :style="{ left: `${position.x}px`, top: `${position.y}px` }"
  >
    <transition name="fb-pop">
      <div v-if="open" class="fb-panel" :style="panelStyle" @pointerdown.stop>
        <div class="fb-panel-head">
          <div>
            <strong>{{ showContacts ? '选择通话联系人' : '快捷入口' }}</strong>
            <small>{{ showContacts ? '选择在线用户发起通话' : '当前用户个性化悬浮球' }}</small>
          </div>
          <div class="fb-head-actions">
            <button type="button" title="返回上一页" @click="goBack"><el-icon><Back /></el-icon></button>
            <button type="button" title="隐藏悬浮球" @click="hideBall"><el-icon><Hide /></el-icon></button>
            <button type="button" title="关闭" @click="open = false"><el-icon><Close /></el-icon></button>
          </div>
        </div>

        <template v-if="showContacts">
          <button type="button" class="fb-back-row" @click="showContacts = false">
            <el-icon><ArrowLeft /></el-icon>返回快捷入口
          </button>
          <div v-if="onlineUsers.length" class="fb-contact-list">
            <div v-for="user in onlineUsers" :key="user.id" class="fb-contact-row">
              <span class="fb-contact-avatar">{{ (user.real_name || user.username || 'U').slice(0, 1) }}</span>
              <span class="fb-contact-name">
                <strong>{{ user.real_name || user.username }}</strong>
                <small><i></i>在线</small>
              </span>
              <button type="button" title="语音通话" @click="call(user, 'audio')"><el-icon><PhoneFilled /></el-icon></button>
              <button type="button" title="视频通话" @click="call(user, 'video')"><el-icon><VideoCameraFilled /></el-icon></button>
            </div>
          </div>
          <div v-else class="fb-empty">
            <el-icon :size="24"><User /></el-icon>
            <span>暂无其他在线用户</span>
          </div>
        </template>

        <template v-else>
          <div class="fb-shortcuts">
            <button
              v-for="item in visibleShortcuts"
              :key="item.id"
              type="button"
              class="fb-shortcut"
              @click="runShortcut(item)"
            >
              <span class="fb-shortcut-icon"><el-icon><component :is="item.icon" /></el-icon></span>
              <span>{{ item.label }}</span>
            </button>
          </div>
          <div class="fb-recent">
            <div class="fb-section-title"><span>最近浏览</span><small>最多 3 条</small></div>
            <button
              v-for="item in imState.preferences.recent"
              :key="item.path"
              type="button"
              class="fb-recent-row"
              @click="goRecent(item)"
            >
              <el-icon><Clock /></el-icon>
              <span>{{ item.title || item.path }}</span>
              <small>{{ item.path }}</small>
            </button>
            <div v-if="!imState.preferences.recent?.length" class="fb-empty small">访问页面后自动记录</div>
          </div>
          <button type="button" class="fb-settings-link" @click="openSettings">
            <el-icon><Setting /></el-icon>自定义悬浮球功能
          </button>
        </template>
      </div>
    </transition>

    <button
      type="button"
      class="fb-ball"
      :class="{ dragging, active: open, 'has-unread': unreadTotal > 0 }"
      title="快捷入口 · 拖动可移动"
      @pointerdown="startDrag"
      @click="onBallClick"
    >
      <span class="fb-aurora"></span>
      <span class="fb-satellite sat-one"></span>
      <span class="fb-satellite sat-two"></span>
      <span class="fb-satellite sat-three"></span>
      <span class="fb-core"><el-icon :size="25"><Menu /></el-icon></span>
      <span v-if="unreadTotal" class="fb-badge">{{ unreadTotal > 99 ? '99+' : unreadTotal }}</span>
    </button>

    <el-dialog v-model="settingsVisible" title="悬浮球设置" width="min(860px, 94vw)" append-to-body>
      <FloatingBallSettings />
    </el-dialog>
  </div>
  <button v-else class="fb-restore" type="button" title="显示悬浮球" @click="restoreBall">
    <el-icon><Grid /></el-icon>
    <span>悬浮球</span>
  </button>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  floatingShortcutItems, imState, onlineUsers, recordRecentRoute, savePreferences, startCall,
  unreadTotal,
} from '@/store/im'
import FloatingBallSettings from '@/components/FloatingBallSettings.vue'

const route = useRoute()
const router = useRouter()
const open = ref(false)
const showContacts = ref(false)
const settingsVisible = ref(false)
const dragging = ref(false)
const draggingRef = ref(false)
const edgeHidden = ref(false)
const edgeSide = ref('right')
const position = ref({
  x: Math.max(8, window.innerWidth - 88),
  y: Math.max(8, window.innerHeight - 160),
})
let dragState = null

const visibleShortcuts = computed(() => {
  const selected = imState.preferences.shortcuts || []
  return floatingShortcutItems().filter((item) => selected.includes(item.id))
})

const panelStyle = computed(() => {
  const panelWidth = 286
  const panelHeight = showContacts.value ? 390 : 390
  const gap = 14
  const vw = window.innerWidth
  const vh = window.innerHeight
  let left = position.value.x + 68
  let top = position.value.y - 300
  if (left + panelWidth > vw - 10) left = Math.max(10, position.value.x - panelWidth - gap)
  if (position.value.x + panelWidth + gap < vw && position.value.x < 32) left = position.value.x + 68
  if (top < 10) top = Math.max(10, position.value.y - 310)
  if (top + panelHeight > vh - 10) top = Math.max(10, position.value.y - panelHeight - gap)
  return { left: `${Math.round(left)}px`, top: `${Math.round(top)}px` }
})

function clampPosition(x, y) {
  const size = 64
  return {
    x: Math.max(8, Math.min(window.innerWidth - size - 8, x)),
    y: Math.max(8, Math.min(window.innerHeight - size - 8, y)),
  }
}

function applyPosition() {
  const saved = imState.preferences.position
  if (saved && Number.isFinite(Number(saved.x)) && Number.isFinite(Number(saved.y))) {
    position.value = clampPosition(Number(saved.x), Number(saved.y))
  } else {
    position.value = clampPosition(window.innerWidth - 88, window.innerHeight - 160)
  }
}

function startDrag(event) {
  if (event.button !== 0) return
  event.preventDefault()
  draggingRef.value = false
  dragState = {
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    originX: position.value.x,
    originY: position.value.y,
  }
  window.addEventListener('pointermove', onDragMove, { passive: false })
  window.addEventListener('pointerup', onDragEnd)
  window.addEventListener('pointercancel', onDragEnd)
}

function onDragMove(event) {
  if (!dragState) return
  const dx = event.clientX - dragState.startX
  const dy = event.clientY - dragState.startY
  if (!draggingRef.value && Math.hypot(dx, dy) < 5) return
  event.preventDefault()
  draggingRef.value = true
  dragging.value = true
  position.value = clampPosition(dragState.originX + dx, dragState.originY + dy)
}

function onDragEnd() {
  window.removeEventListener('pointermove', onDragMove)
  window.removeEventListener('pointerup', onDragEnd)
  window.removeEventListener('pointercancel', onDragEnd)
  if (!dragState) return
  const moved = draggingRef.value
  dragState = null
  if (!moved) return
  dragging.value = false
  savePreferences({ position: { ...position.value } })
  window.setTimeout(() => { draggingRef.value = false }, 0)
}

function onBallClick() {
  if (draggingRef.value) {
    draggingRef.value = false
    return
  }
  open.value = !open.value
  if (!open.value) showContacts.value = false
}

function runShortcut(item) {
  if (!item) return
  if (item.type === 'call') {
    if (!onlineUsers.value.length) {
      ElMessage.warning('当前没有其他在线用户')
      return
    }
    showContacts.value = true
    return
  }
  if (item.path) {
    open.value = false
    showContacts.value = false
    if (/^https?:\/\//i.test(item.path)) window.open(item.path, '_blank', 'noopener,noreferrer')
    else router.push(item.path)
  }
}

async function call(user, type) {
  const ok = await startCall(user, type)
  if (ok) {
    open.value = false
    showContacts.value = false
  }
}

function goRecent(item) {
  if (!item?.path) return
  open.value = false
  showContacts.value = false
  router.push(item.path)
}

function goBack() {
  open.value = false
  router.back()
}

function openSettings() {
  open.value = false
  settingsVisible.value = true
}

async function hideBall() {
  open.value = false
  showContacts.value = false
  await savePreferences({ enabled: false }, true)
}

async function restoreBall() {
  await savePreferences({ enabled: true }, true)
  open.value = false
}

function onWindowResize() {
  position.value = clampPosition(position.value.x, position.value.y)
  edgeHidden.value = false
}

function onDocumentPointerMove(event) {
  if (open.value || dragging.value || dragState) {
    edgeHidden.value = false
    return
  }
  const vw = window.innerWidth
  const vh = window.innerHeight
  const edge = 10
  if (event.clientX <= edge) {
    edgeHidden.value = true
    edgeSide.value = 'left'
  } else if (event.clientX >= vw - edge) {
    edgeHidden.value = true
    edgeSide.value = 'right'
  } else if (event.clientY <= edge) {
    edgeHidden.value = true
    edgeSide.value = 'top'
  } else if (event.clientY >= vh - edge) {
    edgeHidden.value = true
    edgeSide.value = 'bottom'
  } else {
    edgeHidden.value = false
  }
}

watch(() => route.fullPath, () => {
  if (!imState.preferencesLoaded) return
  recordRecentRoute(route)
})

watch(() => imState.preferences.position, (value) => {
  if (!value || draggingRef.value) return
  const next = clampPosition(Number(value.x), Number(value.y))
  if (Number.isFinite(next.x) && Number.isFinite(next.y)) position.value = next
})

watch(() => imState.preferencesLoaded, (loaded) => {
  if (loaded) recordRecentRoute(route)
})

onMounted(() => {
  applyPosition()
  window.addEventListener('resize', onWindowResize)
  document.addEventListener('pointermove', onDocumentPointerMove, { passive: true })
  if (imState.preferencesLoaded) recordRecentRoute(route)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onWindowResize)
  document.removeEventListener('pointermove', onDocumentPointerMove)
  window.removeEventListener('pointermove', onDragMove)
  window.removeEventListener('pointerup', onDragEnd)
  window.removeEventListener('pointercancel', onDragEnd)
})
</script>

<style scoped>
.fb-root { position: fixed; z-index: 4500; width: 64px; height: 64px; transition: transform .26s ease, opacity .26s ease; }
.fb-root.edge-hidden { opacity: .16; pointer-events: none; }
.fb-root.edge-hidden.edge-right { transform: translateX(54px); }
.fb-root.edge-hidden.edge-left { transform: translateX(-54px); }
.fb-root.edge-hidden.edge-top { transform: translateY(-54px); }
.fb-root.edge-hidden.edge-bottom { transform: translateY(54px); }
.fb-ball { position: relative; width: 64px; height: 64px; border-radius: 50%; border: 1px solid rgba(103, 232, 249, .82); background: radial-gradient(circle at 34% 24%, rgba(186, 252, 255, .36) 0, rgba(21, 133, 165, .5) 18%, rgba(7, 58, 89, .9) 48%, #041927 100%); color: #e5fbff; display: grid; place-items: center; cursor: grab; box-shadow: 0 8px 26px rgba(0, 0, 0, .48), 0 0 0 6px rgba(34, 211, 238, .055), 0 0 30px rgba(34, 211, 238, .32), inset 0 0 20px rgba(186, 252, 255, .2); touch-action: none; transition: transform .16s ease, box-shadow .16s ease; }
.fb-aurora { position: absolute; inset: -1px; border-radius: 50%; z-index: 0; background: conic-gradient(from 0deg, #22d3ee, #818cf8, #f472b6, #fbbf24, #34d399, #22d3ee); filter: blur(5px) saturate(1.25); opacity: .82; animation: fb-aurora 10s linear infinite; pointer-events: none; }
.fb-ball::before { content: ''; position: absolute; inset: -10px; border-radius: 50%; border: 1px solid rgba(72, 211, 241, .5); animation: fb-pulse-ring 2.8s ease-out infinite; pointer-events: none; }
.fb-ball::after { content: ''; position: absolute; inset: -4px; border-radius: 50%; border: 1px dashed rgba(125, 211, 252, .56); animation: fb-spin 9s linear infinite; pointer-events: none; }
.fb-ball:hover, .fb-ball.active { transform: translateY(-2px) scale(1.05); box-shadow: 0 12px 32px rgba(0, 0, 0, .5), 0 0 0 8px rgba(34, 211, 238, .07), 0 0 42px rgba(34, 211, 238, .45), inset 0 0 22px rgba(186, 252, 255, .3); }
.fb-ball:active, .fb-ball.dragging { cursor: grabbing; transform: scale(.95); }
.fb-ball.has-unread { border-color: rgba(251, 113, 133, .95); box-shadow: 0 8px 26px rgba(0, 0, 0, .48), 0 0 0 7px rgba(251, 113, 133, .1), 0 0 38px rgba(244, 63, 94, .48), inset 0 0 20px rgba(255, 202, 212, .25); }
.fb-ball.has-unread::before { border-color: rgba(251, 113, 133, .82); animation-duration: 1.6s; }
.fb-core { position: relative; z-index: 2; width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center; color: #e7fdff; background: radial-gradient(circle at 35% 30%, rgba(155, 251, 255, .34), rgba(4, 33, 49, .75) 68%); border: 1px solid rgba(167, 243, 255, .5); box-shadow: inset 0 0 12px rgba(125, 211, 252, .26), 0 0 12px rgba(34, 211, 238, .2); animation: fb-core-breathe 3s ease-in-out infinite; }
.fb-satellite { position: absolute; left: 50%; top: 50%; width: 5px; height: 5px; margin: -2.5px 0 0 -2.5px; border-radius: 50%; background: #a5f3fc; box-shadow: 0 0 9px #67e8f9; pointer-events: none; z-index: 3; }
.fb-satellite.sat-one { --orbit: 36px; animation: fb-satellite 5.2s linear infinite; }
.fb-satellite.sat-two { --orbit: 29px; width: 4px; height: 4px; background: #c4b5fd; box-shadow: 0 0 8px #a78bfa; animation: fb-satellite 7.4s linear infinite; animation-delay: -2.6s; }
.fb-satellite.sat-three { --orbit: 43px; width: 3px; height: 3px; background: #bae6fd; box-shadow: 0 0 7px #7dd3fc; animation: fb-satellite 9.5s linear infinite; animation-delay: -5s; }
.fb-badge { position: absolute; right: -4px; top: -6px; z-index: 5; min-width: 19px; height: 19px; padding: 0 5px; border-radius: 10px; background: linear-gradient(135deg, #fb7185, #e11d48); color: #fff; font-size: 10px; font-weight: 800; display: grid; place-items: center; border: 2px solid #061b28; box-shadow: 0 0 12px rgba(244, 63, 94, .65); animation: fb-badge-pulse 1.8s ease-in-out infinite; }
.fb-restore { position: fixed; right: 0; top: 50%; transform: translateY(-50%); z-index: 4490; width: 24px; min-height: 90px; border-radius: 9px 0 0 9px; border: 1px solid rgba(56, 189, 248, .35); border-right: 0; background: rgba(6, 35, 50, .78); color: #6ec9dc; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 5px; cursor: pointer; opacity: .55; transition: width .16s ease, opacity .16s ease, background .16s ease; }
.fb-restore span { writing-mode: vertical-rl; font-size: 10px; letter-spacing: .08em; }
.fb-restore:hover { width: 30px; opacity: 1; background: rgba(8, 55, 74, .95); }
.fb-restore .el-icon { font-size: 13px; }
.fb-panel { position: fixed; width: 286px; max-height: min(480px, calc(100vh - 24px)); overflow-y: auto; border-radius: 13px; border: 1px solid #245b72; background: linear-gradient(160deg, rgba(9, 34, 51, .98), rgba(5, 21, 34, .99)); box-shadow: 0 20px 55px rgba(0, 0, 0, .55); color: #e2f6ff; padding: 13px; }
.fb-panel-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; padding-bottom: 10px; border-bottom: 1px solid #18475d; }
.fb-panel-head > div:first-child { display: flex; flex-direction: column; gap: 3px; }
.fb-panel-head strong { font-size: 14px; }
.fb-panel-head small { color: #7ca4b9; font-size: 10px; }
.fb-head-actions { display: flex; gap: 5px; }
.fb-head-actions button { border: 0; background: rgba(255, 255, 255, .07); color: #b9dbe9; width: 24px; height: 24px; border-radius: 6px; display: grid; place-items: center; cursor: pointer; }
.fb-shortcuts { display: grid; grid-template-columns: repeat(3, 1fr); gap: 7px; padding: 11px 0; }
.fb-shortcut { border: 1px solid #1d4a60; background: rgba(18, 55, 74, .7); border-radius: 8px; color: #d3edf7; min-height: 64px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 5px; font-size: 11px; cursor: pointer; }
.fb-shortcut:hover { border-color: #3cb9d2; background: rgba(26, 83, 105, .7); }
.fb-shortcut-icon { width: 24px; height: 24px; display: grid; place-items: center; border-radius: 7px; background: rgba(56, 189, 248, .14); color: #7dd3fc; }
.fb-recent { border-top: 1px solid #18475d; padding-top: 9px; }
.fb-section-title { display: flex; justify-content: space-between; color: #a9cfdf; font-size: 11px; margin-bottom: 5px; }
.fb-section-title small { color: #66879a; }
.fb-recent-row { width: 100%; display: flex; align-items: center; gap: 7px; padding: 6px 5px; border: 0; background: transparent; color: #c3e2ee; text-align: left; border-radius: 5px; cursor: pointer; font-size: 11px; }
.fb-recent-row:hover { background: rgba(56, 189, 248, .1); }
.fb-recent-row span { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fb-recent-row small { max-width: 100px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #6e93a7; font-size: 9px; }
.fb-empty { display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 20px 4px; color: #6f93a6; font-size: 11px; }
.fb-empty.small { padding: 11px 4px; }
.fb-settings-link { border: 0; background: transparent; color: #6dc6dc; font-size: 11px; display: inline-flex; align-items: center; gap: 5px; padding: 10px 0 0; cursor: pointer; }
.fb-contact-list { display: flex; flex-direction: column; gap: 4px; padding: 9px 0; max-height: 280px; overflow-y: auto; }
.fb-contact-row { display: flex; align-items: center; gap: 7px; padding: 6px; border-radius: 7px; background: rgba(18, 55, 74, .52); }
.fb-contact-avatar { width: 28px; height: 28px; flex: 0 0 28px; border-radius: 8px; display: grid; place-items: center; color: #e4fbff; background: #15627c; font-size: 12px; font-weight: 700; }
.fb-contact-name { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
.fb-contact-name strong { font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fb-contact-name small { color: #34d399; font-size: 9px; display: inline-flex; align-items: center; gap: 3px; }
.fb-contact-name small i { width: 5px; height: 5px; border-radius: 50%; background: #22c55e; }
.fb-contact-row > button { width: 25px; height: 25px; border: 1px solid #23647a; border-radius: 6px; background: #0b3c50; color: #75dced; display: grid; place-items: center; cursor: pointer; }
.fb-contact-row > button:hover { background: #12627d; }
.fb-back-row { border: 0; background: transparent; color: #7dd3fc; font-size: 11px; display: inline-flex; align-items: center; gap: 4px; padding: 9px 0 2px; cursor: pointer; }
.fb-pop-enter-active, .fb-pop-leave-active { transition: opacity .16s ease, transform .16s ease; }
.fb-pop-enter-from, .fb-pop-leave-to { opacity: 0; transform: translateY(7px) scale(.98); }
@keyframes fb-pulse-ring { 0% { transform: scale(.92); opacity: .8; } 75%, 100% { transform: scale(1.4); opacity: 0; } }
@keyframes fb-spin { to { transform: rotate(360deg); } }
@keyframes fb-core-breathe { 0%, 100% { transform: scale(.96); box-shadow: inset 0 0 10px rgba(125, 211, 252, .22), 0 0 9px rgba(34, 211, 238, .18); } 50% { transform: scale(1.05); box-shadow: inset 0 0 14px rgba(186, 252, 255, .4), 0 0 17px rgba(34, 211, 238, .4); } }
@keyframes fb-satellite { from { transform: rotate(0deg) translateX(var(--orbit)) rotate(0deg); } to { transform: rotate(360deg) translateX(var(--orbit)) rotate(-360deg); } }
@keyframes fb-badge-pulse { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.12); } }
@keyframes fb-aurora { from { transform: rotate(0deg) scale(1); } to { transform: rotate(360deg) scale(1.08); } }

/* 快捷入口面板与悬浮球统一的多彩极光风格 */
.fb-panel {
  position: fixed;
  border: 1px solid rgba(167, 139, 250, .38);
  background:
    radial-gradient(circle at 100% 0%, rgba(244, 114, 182, .16), transparent 38%),
    radial-gradient(circle at 0% 100%, rgba(34, 211, 238, .15), transparent 42%),
    linear-gradient(160deg, rgba(9, 18, 31, .985), rgba(5, 10, 20, .99));
  box-shadow: 0 22px 58px rgba(0, 0, 0, .58), 0 0 0 1px rgba(56, 189, 248, .08), 0 0 34px rgba(129, 140, 248, .16);
}
.fb-panel::before {
  content: '';
  position: absolute;
  inset: 0 0 auto;
  height: 2px;
  border-radius: 13px 13px 0 0;
  background: linear-gradient(90deg, #22d3ee, #818cf8, #f472b6, #fbbf24, #34d399, #22d3ee);
  opacity: .85;
  pointer-events: none;
}
.fb-panel-head { border-bottom-color: rgba(167, 139, 250, .24); }
.fb-panel-head strong { color: #f0fbff; }
.fb-panel-head small { color: #8aa7c1; }
.fb-head-actions button { background: rgba(255, 255, 255, .075); color: #c5e7f4; border: 1px solid transparent; transition: background .16s, border-color .16s, color .16s; }
.fb-head-actions button:hover { background: rgba(129, 140, 248, .2); border-color: rgba(167, 139, 250, .38); color: #fff; }
.fb-shortcut {
  --fb-accent: #38bdf8;
  position: relative;
  overflow: hidden;
  border-color: color-mix(in srgb, var(--fb-accent) 28%, rgba(255, 255, 255, .08));
  background: linear-gradient(145deg, rgba(255, 255, 255, .075), rgba(255, 255, 255, .025));
  transition: transform .16s ease, border-color .16s ease, background .16s ease, box-shadow .16s ease;
}
.fb-shortcut::before {
  content: '';
  position: absolute;
  inset: 0 0 auto;
  height: 2px;
  background: linear-gradient(90deg, transparent, var(--fb-accent), transparent);
  opacity: .82;
  pointer-events: none;
}
.fb-shortcut:nth-child(6n+1) { --fb-accent: #38bdf8; }
.fb-shortcut:nth-child(6n+2) { --fb-accent: #a78bfa; }
.fb-shortcut:nth-child(6n+3) { --fb-accent: #f472b6; }
.fb-shortcut:nth-child(6n+4) { --fb-accent: #fbbf24; }
.fb-shortcut:nth-child(6n+5) { --fb-accent: #34d399; }
.fb-shortcut:nth-child(6n+6) { --fb-accent: #818cf8; }
.fb-shortcut:hover {
  transform: translateY(-1px);
  border-color: color-mix(in srgb, var(--fb-accent) 62%, transparent);
  background: color-mix(in srgb, var(--fb-accent) 10%, rgba(7, 18, 31, .9));
  box-shadow: 0 7px 20px color-mix(in srgb, var(--fb-accent) 16%, transparent);
}
.fb-shortcut-icon {
  background: color-mix(in srgb, var(--fb-accent) 17%, transparent);
  color: var(--fb-accent);
  box-shadow: 0 0 12px color-mix(in srgb, var(--fb-accent) 14%, transparent);
  transition: transform .16s ease, background .16s ease;
}
.fb-shortcut:hover .fb-shortcut-icon { transform: scale(1.08); background: color-mix(in srgb, var(--fb-accent) 26%, transparent); }
.fb-recent { border-top-color: rgba(167, 139, 250, .22); }
.fb-section-title { color: #b7d8e8; }
.fb-section-title small { color: #7596b0; }
.fb-recent-row { color: #c9e9f5; }
.fb-recent-row:hover { background: linear-gradient(90deg, rgba(34, 211, 238, .12), rgba(167, 139, 250, .12)); }
.fb-recent-row .el-icon { color: #67e8f9; }
.fb-settings-link { color: #67e8f9; transition: color .16s, transform .16s; }
.fb-settings-link:hover { color: #c4b5fd; transform: translateX(2px); }
.fb-contact-row { background: linear-gradient(145deg, rgba(255, 255, 255, .06), rgba(255, 255, 255, .02)); }
.fb-contact-row:nth-child(6n+1) .fb-contact-avatar { background: linear-gradient(145deg, #22d3ee, #2563eb); }
.fb-contact-row:nth-child(6n+2) .fb-contact-avatar { background: linear-gradient(145deg, #a78bfa, #6d28d9); }
.fb-contact-row:nth-child(6n+3) .fb-contact-avatar { background: linear-gradient(145deg, #f472b6, #be185d); }
.fb-contact-row:nth-child(6n+4) .fb-contact-avatar { background: linear-gradient(145deg, #fbbf24, #b45309); }
.fb-contact-row:nth-child(6n+5) .fb-contact-avatar { background: linear-gradient(145deg, #34d399, #047857); }
.fb-contact-row:nth-child(6n+6) .fb-contact-avatar { background: linear-gradient(145deg, #818cf8, #4338ca); }
.fb-contact-row > button { border-color: rgba(103, 232, 249, .28); background: rgba(56, 189, 248, .12); color: #8be9fb; }
.fb-contact-row > button:hover { background: rgba(167, 139, 250, .24); color: #fff; }
.fb-panel::-webkit-scrollbar { width: 5px; }
.fb-panel::-webkit-scrollbar-thumb { border-radius: 5px; background: linear-gradient(180deg, #22d3ee, #818cf8, #f472b6); }

/* 快捷入口使用白色卡片，保留悬浮球的多彩边框与图标 */
.fb-shortcut {
  color: #263f52;
  border-color: color-mix(in srgb, var(--fb-accent) 36%, #ffffff);
  background: linear-gradient(145deg, #ffffff, #f7fbfe);
  box-shadow: 0 3px 10px rgba(1, 12, 22, .16);
}
.fb-shortcut::before { height: 3px; opacity: .92; }
.fb-shortcut:hover {
  color: #152d3f;
  border-color: color-mix(in srgb, var(--fb-accent) 72%, #ffffff);
  background: color-mix(in srgb, var(--fb-accent) 7%, #ffffff);
  box-shadow: 0 7px 18px color-mix(in srgb, var(--fb-accent) 22%, transparent);
}
.fb-shortcut-icon {
  background: color-mix(in srgb, var(--fb-accent) 13%, #ffffff);
  color: color-mix(in srgb, var(--fb-accent) 78%, #16465c);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--fb-accent) 18%, #ffffff) inset;
}
.fb-shortcut:hover .fb-shortcut-icon {
  background: color-mix(in srgb, var(--fb-accent) 22%, #ffffff);
  color: color-mix(in srgb, var(--fb-accent) 72%, #12384a);
}
</style>
