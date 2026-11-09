<template>
  <div v-if="hasOverlay" class="im-call-layer">
    <!-- 一对一语音/视频来电 -->
    <div v-if="imState.incoming" class="im-incoming">
      <div class="call-kicker">INCOMING {{ imState.incoming.call_type === 'video' ? 'VIDEO' : 'AUDIO' }} CALL</div>
      <div class="call-avatar ringing">
        <el-icon :size="34"><UserFilled /></el-icon>
      </div>
      <strong>{{ imState.incoming.from?.real_name || imState.incoming.from?.username || '未知用户' }}</strong>
      <span class="incoming-type">{{ imState.incoming.call_type === 'video' ? '邀请你进行视频通话' : '邀请你进行语音通话' }}</span>
      <div class="incoming-actions">
        <el-button type="danger" round class="call-action call-action-hangup" @click="rejectIncoming">
          <el-icon><CloseBold /></el-icon>拒绝
        </el-button>
        <el-button type="success" round class="call-action call-action-answer" @click="acceptIncoming">
          <el-icon><PhoneFilled /></el-icon>接听
        </el-button>
      </div>
    </div>

    <!-- 群通话来电 -->
    <div v-else-if="imState.groupIncoming" class="im-incoming im-group-incoming">
      <div class="call-kicker">INCOMING GROUP {{ imState.groupIncoming.call_type === 'video' ? 'VIDEO' : 'AUDIO' }} CALL</div>
      <div class="call-avatar ringing">
        <el-icon :size="34"><ChatLineSquare /></el-icon>
      </div>
      <strong>{{ imState.groupIncoming.group_name || '群通话' }}</strong>
      <span class="incoming-type">
        {{ imState.groupIncoming.from?.real_name || imState.groupIncoming.from?.username || '成员' }} 邀请你加入群{{ imState.groupIncoming.call_type === 'video' ? '视频' : '语音' }}通话
      </span>
      <span class="group-incoming-meta">
        {{ (imState.groupIncoming.participants || []).length }} 人正在通话
      </span>
      <div class="incoming-actions">
        <el-button type="danger" round class="call-action call-action-hangup" @click="rejectGroupIncoming">
          <el-icon><CloseBold /></el-icon>拒绝
        </el-button>
        <el-button type="success" round class="call-action call-action-answer" @click="acceptGroupIncoming">
          <el-icon><PhoneFilled /></el-icon>加入
        </el-button>
      </div>
    </div>

    <!-- 一对一 call 窗口 -->
    <div v-else-if="imState.call.active" class="im-call-window" :class="{ minimized: imState.call.minimized }">
      <div class="call-head">
        <div class="call-peer">
          <span class="call-dot" :class="{ live: imState.call.status === 'active' }"></span>
          <div>
            <strong>{{ imState.call.peer?.real_name || imState.call.peer?.username || '通话中' }}</strong>
            <small>{{ imState.call.type === 'video' ? '视频通话' : '语音通话' }} · {{ durationText }}</small>
          </div>
        </div>
        <div class="call-head-actions">
          <button v-if="imState.call.type === 'video'" type="button" class="call-icon-btn" :disabled="!remoteHasVideo" :title="remoteHasVideo ? '放大视频画面（全屏）' : '等待对方视频'" @click="toggleFullscreen(remoteVideo)">
            <el-icon><FullScreen /></el-icon>
          </button>
          <button type="button" class="call-icon-btn" :title="imState.call.minimized ? '展开通话' : '收起（后台继续）'" @click="minimizeCall(!imState.call.minimized)">
            <el-icon><Minus v-if="!imState.call.minimized" /><FullScreen v-else /></el-icon>
          </button>
          <button type="button" class="call-icon-btn danger call-hangup-pulse" title="挂断" @click="endCall()">
            <el-icon><CloseBold /></el-icon>
          </button>
        </div>
      </div>

      <div v-show="!imState.call.minimized" class="call-body">
        <div class="call-stage" :class="{ audio: imState.call.type === 'audio' }" @dblclick="toggleFullscreen(remoteVideo)">
          <div v-if="imState.call.type === 'audio'" class="call-audio-stage">
            <div class="call-avatar" :class="{ live: imState.call.status === 'active' }">
              <el-icon :size="46"><UserFilled /></el-icon>
            </div>
            <span>{{ imState.call.status === 'calling' ? '正在呼叫…' : '通话中' }}</span>
          </div>
          <video v-show="imState.call.type === 'video' && remoteHasVideo" ref="remoteVideo" class="call-remote-video" autoplay muted playsinline></video>
          <div v-if="imState.call.type === 'video' && !remoteHasVideo" class="call-video-placeholder">
            <div class="call-avatar" :class="{ live: imState.call.status === 'active' }">
              <el-icon :size="34"><UserFilled /></el-icon>
            </div>
            <span>{{ imState.call.status === 'calling' ? '等待对方接听…' : '对方未开启摄像头或视频暂不可用' }}</span>
          </div>
          <div v-if="imState.call.type === 'video' && imState.call.status === 'calling'" class="call-waiting">
            正在呼叫 {{ imState.call.peer?.real_name || imState.call.peer?.username }}…
          </div>
          <video v-show="imState.call.type === 'video' && localHasVideo && imState.call.cameraOn" ref="localVideo" class="call-local-video" autoplay muted playsinline></video>
          <div v-if="imState.call.type === 'video' && !localHasVideo" class="call-camera-off">本端无摄像头画面</div>
        </div>
        <audio ref="remoteAudio" autoplay playsinline class="call-hidden-audio"></audio>
        <button v-if="audioBlocked" type="button" class="call-audio-enable" @click="resumeRemoteAudio">
          <el-icon><Microphone /></el-icon> 点击开启声音
        </button>
        <div class="call-controls">
          <button type="button" class="call-control" :class="{ off: imState.call.muted }" @click="toggleMute">
            <el-icon><Microphone v-if="!imState.call.muted" /><Mute v-else /></el-icon>
            <span>{{ imState.call.muted ? '已静音' : '静音' }}</span>
          </button>
          <button v-if="imState.call.type === 'video'" type="button" class="call-control" :class="{ off: !imState.call.cameraOn }" @click="toggleCamera">
            <el-icon><VideoCamera v-if="imState.call.cameraOn" /><VideoCameraFilled v-else /></el-icon>
            <span>{{ imState.call.cameraOn ? '关闭摄像头' : '打开摄像头' }}</span>
          </button>
          <button type="button" class="call-control danger call-hangup-btn" @click="endCall()">
            <el-icon><CloseBold /></el-icon>
            <span>挂断</span>
          </button>
          <span class="call-bg-tip">切换页面通话继续</span>
        </div>
      </div>
    </div>

    <!-- 群通话窗口（mesh） -->
    <div v-else-if="imState.groupCall.active" class="im-group-window" :class="{ minimized: imState.groupCall.minimized }">
      <div class="call-head">
        <div class="call-peer">
          <span class="call-dot" :class="{ live: imState.groupCall.status === 'active' }"></span>
          <div>
            <strong>{{ imState.groupCall.groupName || '群通话' }}</strong>
            <small>
              {{ imState.groupCall.type === 'video' ? '群视频' : '群语音' }}
              · {{ groupTiles.length }} 人 · {{ durationText }}
            </small>
          </div>
        </div>
        <div class="call-head-actions">
          <button
            type="button"
            class="call-icon-btn"
            :title="imState.groupCall.minimized ? '展开群通话' : '收起（后台继续）'"
            @click="minimizeGroupCall(!imState.groupCall.minimized)"
          >
            <el-icon><Minus v-if="!imState.groupCall.minimized" /><FullScreen v-else /></el-icon>
          </button>
          <button type="button" class="call-icon-btn danger call-hangup-pulse" title="离开群通话" @click="leaveGroupCall">
            <el-icon><CloseBold /></el-icon>
          </button>
        </div>
      </div>

      <div v-show="!imState.groupCall.minimized" class="group-call-body">
        <div class="group-tile-grid">
          <div v-for="tile in groupTiles" :key="tile.id" class="group-tile" :class="{ videocam: hasVideoStream(tile), invited: tile.joined === false }">
            <video
              v-show="hasVideoStream(tile)"
              :ref="(el) => setTileVideo(tile.id, el)"
              class="group-tile-video"
              autoplay
              playsinline
              muted
            ></video>
            <div v-if="!hasVideoStream(tile)" class="group-tile-avatar">
              <span>{{ initialOf(tile) }}</span>
              <em v-if="imState.groupCall.type === 'video' && isCameraOff(tile)">摄像头已关闭</em>
            </div>
            <div class="group-tile-bar">
              <span class="group-tile-name">{{ tile.isSelf ? '我' : (tile.real_name || tile.username) }}</span>
              <el-icon v-if="isMuted(tile)" class="group-tile-muted"><Mute /></el-icon>
            </div>
            <span v-if="tile.joined === false" class="group-tile-tag pending">邀请中</span>
            <span v-else-if="tile.isSelf" class="group-tile-tag">本机</span>
          </div>
        </div>
        <div v-if="imState.groupCall.status === 'connecting'" class="group-call-waiting">
          正在连接群通话…
        </div>
        <div v-if="imState.groupCall.offlineMembers?.length" class="group-offline-tip">
          离线未收到邀请：{{ imState.groupCall.offlineMembers.map((item) => item.real_name || item.username).join('、') }}
        </div>
        <div class="call-controls group-controls">
          <button type="button" class="call-control" :class="{ off: imState.groupCall.muted }" @click="toggleGroupMute">
            <el-icon><Microphone v-if="!imState.groupCall.muted" /><Mute v-else /></el-icon>
            <span>{{ imState.groupCall.muted ? '已静音' : '静音' }}</span>
          </button>
          <button
            v-if="imState.groupCall.type === 'video'"
            type="button"
            class="call-control"
            :class="{ off: !imState.groupCall.cameraOn }"
            @click="toggleGroupCamera"
          >
            <el-icon><VideoCamera v-if="imState.groupCall.cameraOn" /><VideoCameraFilled v-else /></el-icon>
            <span>{{ imState.groupCall.cameraOn ? '关闭摄像头' : '打开摄像头' }}</span>
          </button>
          <button type="button" class="call-control" @click="toggleWhiteboard">
            <el-icon><EditPen /></el-icon>
            <span>群白板</span>
          </button>
          <button type="button" class="call-control danger" @click="leaveGroupCall">
            <el-icon><SwitchButton /></el-icon>
            <span>离开</span>
          </button>
          <button
            v-if="Number(imState.groupCall.hostId) === meId"
            type="button"
            class="call-control danger"
            title="结束所有成员的群通话"
            @click="endGroupCall"
          >
            <el-icon><CircleCloseFilled /></el-icon>
            <span>结束通话</span>
          </button>
          <span class="call-bg-tip">群通话使用点对点 mesh，适合小型群组</span>
        </div>
      </div>
      <audio
        v-for="tile in remoteTiles"
        :key="`audio-${tile.id}`"
        :ref="(el) => setTileAudio(tile.id, el)"
        autoplay
        class="call-hidden-audio"
      ></audio>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  acceptGroupIncoming, acceptIncoming, cleanupGroupCall, endCall, endGroupCall,
  groupStreams, imState, leaveGroupCall, localStream, minimizeCall, minimizeGroupCall,
  openWhiteboard, rejectGroupIncoming, rejectIncoming, remoteStream,
  toggleCamera, toggleGroupCamera, toggleGroupMute, toggleMute,
} from '@/store/im'
import { currentUser } from '@/store/auth'

const remoteVideo = ref(null)
const localVideo = ref(null)
const remoteAudio = ref(null)
const audioBlocked = ref(false)
const remoteHasVideo = computed(() => Boolean(remoteStream.value?.getVideoTracks?.().length))
const localHasVideo = computed(() => Boolean(localStream.value?.getVideoTracks?.().length))
const now = ref(Date.now())
let timer = null
const meId = computed(() => Number(currentUser.value?.id || 0))

const hasOverlay = computed(() => Boolean(
  imState.incoming || imState.groupIncoming || imState.call.active || imState.groupCall.active,
))

const isGroupMode = computed(() => !imState.incoming && !imState.groupIncoming && !imState.call.active
  && imState.groupCall.active)

const durationText = computed(() => {
  const startedAt = isGroupMode.value ? imState.groupCall.startedAt : imState.call.startedAt
  if (!startedAt) {
    return isGroupMode.value && imState.groupCall.status === 'connecting' ? '连接中' : '等待接听'
  }
  const seconds = Math.max(0, Math.floor((now.value - startedAt) / 1000))
  const mm = String(Math.floor(seconds / 60)).padStart(2, '0')
  const ss = String(seconds % 60).padStart(2, '0')
  return `${mm}:${ss}`
})

const groupTiles = computed(() => {
  const participants = (imState.groupCall.participants || []).map((item) => ({
    ...item,
    isSelf: Number(item.id) === meId.value,
  }))
  if (!participants.some((item) => item.isSelf)) {
    participants.unshift({
      id: meId.value,
      isSelf: true,
      real_name: currentUser.value?.real_name || currentUser.value?.username || '我',
      username: currentUser.value?.username || '',
      muted: imState.groupCall.muted,
      camera: imState.groupCall.cameraOn,
    })
  }
  return participants
})
const remoteTiles = computed(() => groupTiles.value.filter((tile) => !tile.isSelf))

const tileVideoRefs = new Map()
const tileAudioRefs = new Map()
function setTileVideo(id, el) {
  const key = Number(id)
  if (el) tileVideoRefs.set(key, el)
  else tileVideoRefs.delete(key)
}
function setTileAudio(id, el) {
  const key = Number(id)
  if (el) tileAudioRefs.set(key, el)
  else tileAudioRefs.delete(key)
}

function playMedia(el, markAudio = false) {
  if (!el?.play) return
  const promise = el.play()
  if (promise?.then) {
    promise.then(() => { if (markAudio) audioBlocked.value = false }).catch(() => {})
  }
  if (promise?.catch) {
    promise.catch(() => { if (markAudio) audioBlocked.value = true })
  }
}

function resumeRemoteAudio() {
  audioBlocked.value = false
  playMedia(remoteAudio.value, true)
}

function attachGroupStreams() {
  nextTick(() => {
    tileVideoRefs.forEach((el, id) => {
      const stream = id === meId.value ? localStream.value : groupStreams.value[id]
      if (el.srcObject !== (stream || null)) el.srcObject = stream || null
      if (stream) playMedia(el)
    })
    tileAudioRefs.forEach((el, id) => {
      const stream = groupStreams.value[id] || null
      if (el.srcObject !== stream) el.srcObject = stream
      if (stream) playMedia(el)
    })
  })
}

function hasVideoStream(tile) {
  if (imState.groupCall.type !== 'video') return false
  if (tile.isSelf ? !imState.groupCall.cameraOn : tile.camera === false) return false
  const stream = tile.isSelf ? localStream.value : groupStreams.value[Number(tile.id)]
  return Boolean(stream)
}

function isMuted(tile) {
  return tile.isSelf ? imState.groupCall.muted : tile.muted === true
}

function isCameraOff(tile) {
  return tile.isSelf ? !imState.groupCall.cameraOn : tile.camera === false
}

function initialOf(tile) {
  return String(tile.real_name || tile.username || 'U').slice(0, 1).toUpperCase()
}

function toggleFullscreen(el) {
  if (!el) return
  if (document.fullscreenElement) {
    document.exitFullscreen?.().catch?.(() => {})
  } else if (el.requestFullscreen) {
    el.requestFullscreen().catch?.(() => {})
  }
}

function toggleTileFullscreen(id) {
  const el = tileVideoRefs.get(Number(id))
  if (el) toggleFullscreen(el)
}

function toggleWhiteboard() {
  if (!imState.groupCall.active) return
  minimizeGroupCall(true)
  openWhiteboard(imState.groupCall.groupId)
}

function attachStreams() {
  nextTick(() => {
    const stream = remoteStream.value || null
    const isVideo = imState.call.type === 'video'
    // 远端视频静音，音频统一由独立的 audio 元素播放，避免浏览器对隐藏 video 的音频策略不一致。
    if (remoteVideo.value) {
      remoteVideo.value.srcObject = isVideo ? stream : null
      remoteVideo.value.muted = true
      if (stream) playMedia(remoteVideo.value)
    }
    if (remoteAudio.value) {
      remoteAudio.value.srcObject = stream
      remoteAudio.value.muted = false
      remoteAudio.value.volume = 1
      if (!stream) audioBlocked.value = false
      if (stream) playMedia(remoteAudio.value, true)
    }
    if (localVideo.value) {
      localVideo.value.srcObject = localStream.value || null
      if (localStream.value) playMedia(localVideo.value)
    }
  })
}

watch(remoteStream, attachStreams)
watch(localStream, attachStreams)
watch(() => imState.call.type, attachStreams)
watch([localStream, groupStreams], attachGroupStreams)
watch(() => groupTiles.value.map((tile) => tile.id).join(','), attachGroupStreams)
watch(() => imState.groupCall.active, (active) => {
  if (!active) {
    tileVideoRefs.clear()
    tileAudioRefs.clear()
    return
  }
  attachGroupStreams()
})

watch(() => imState.call.active, (active) => {
  if (active) attachStreams()
})
onMounted(() => {
  attachStreams()
  attachGroupStreams()
})

timer = window.setInterval(() => { now.value = Date.now() }, 1000)
onBeforeUnmount(() => {
  window.clearInterval(timer)
  cleanupGroupCall()
})
</script>

<style scoped>
.im-call-layer { position: fixed; inset: 0; z-index: 5000; pointer-events: none; }
.im-incoming { pointer-events: auto; position: fixed; right: 22px; bottom: 22px; width: 300px; padding: 20px; border-radius: 16px; background: linear-gradient(165deg, #08243a, #071a2b); border: 1px solid #2b8fa8; box-shadow: 0 20px 60px rgba(0, 0, 0, .55), 0 0 30px rgba(34, 211, 238, .15); display: flex; flex-direction: column; align-items: center; gap: 10px; color: #e8f8ff; animation: im-incoming-in .22s ease-out; }
.im-group-incoming { border-color: #3b82f6; box-shadow: 0 20px 60px rgba(0, 0, 0, .55), 0 0 30px rgba(59, 130, 246, .18); }
.call-action-answer .el-icon { animation: im-answer-pulse 1.25s ease-in-out infinite; }
.call-action-hangup .el-icon { animation: im-hangup-wiggle 1.1s ease-in-out infinite; }
.call-hangup-pulse .el-icon { animation: im-hangup-pulse 1.4s ease-in-out infinite; }
.call-hangup-btn { animation: im-hangup-pulse 1.4s ease-in-out infinite; }
@keyframes im-answer-pulse {
  0%, 100% { transform: scale(1); filter: drop-shadow(0 0 0 rgba(34, 197, 94, 0)); }
  50% { transform: scale(1.18); filter: drop-shadow(0 0 6px rgba(34, 197, 94, .85)); }
}
@keyframes im-hangup-wiggle {
  0%, 100% { transform: rotate(0deg); }
  25% { transform: rotate(-12deg); }
  75% { transform: rotate(12deg); }
}
@keyframes im-hangup-pulse {
  0%, 100% { transform: scale(1); filter: drop-shadow(0 0 0 rgba(239, 68, 68, 0)); }
  50% { transform: scale(1.12); filter: drop-shadow(0 0 6px rgba(239, 68, 68, .8)); }
}
@media (prefers-reduced-motion: reduce) {
  .call-action-answer .el-icon, .call-action-hangup .el-icon, .call-hangup-pulse .el-icon, .call-hangup-btn { animation: none; }
}
.call-kicker { font-size: 10px; letter-spacing: .16em; color: #67e8f9; text-align: center; }
.im-incoming strong { font-size: 16px; text-align: center; }
.incoming-type { color: #8eb6cc; font-size: 12px; margin-bottom: 4px; text-align: center; }
.group-incoming-meta { color: #6ba3bd; font-size: 11px; }
.incoming-actions { display: flex; gap: 12px; width: 100%; margin-top: 6px; }
.incoming-actions .el-button { flex: 1; }
.call-avatar { width: 82px; height: 82px; border-radius: 50%; display: grid; place-items: center; color: #d9f5ff; background: linear-gradient(145deg, #145b7d, #0b2d45); border: 1px solid #38bdf8; }
.call-avatar.ringing { animation: im-call-pulse 1.4s ease-in-out infinite; }
.call-avatar.live { box-shadow: 0 0 30px rgba(34, 211, 238, .35); }
.im-call-window { pointer-events: auto; position: fixed; right: 22px; bottom: 92px; width: 340px; border-radius: 15px; overflow: hidden; background: linear-gradient(165deg, #09243a, #071725); border: 1px solid #245f78; box-shadow: 0 18px 55px rgba(0, 0, 0, .55); color: #e8f8ff; animation: im-incoming-in .2s ease-out; }
.im-call-window.minimized { width: 280px; bottom: 92px; }
.call-head { display: flex; align-items: center; justify-content: space-between; padding: 11px 13px; background: rgba(12, 47, 68, .9); border-bottom: 1px solid #17485e; }
.call-peer { display: flex; align-items: center; gap: 9px; min-width: 0; }
.call-peer > div { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.call-peer strong { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.call-peer small { color: #84a9be; font-size: 11px; }
.call-dot { width: 8px; height: 8px; border-radius: 50%; background: #f59e0b; flex: 0 0 8px; }
.call-dot.live { background: #22c55e; box-shadow: 0 0 8px #22c55e; }
.call-head-actions { display: flex; gap: 5px; }
.call-icon-btn { width: 27px; height: 27px; border: 0; border-radius: 7px; background: rgba(255, 255, 255, .07); color: #c7e8f7; cursor: pointer; display: grid; place-items: center; }
.call-icon-btn:hover { background: rgba(56, 189, 248, .18); }
.call-icon-btn.danger:hover { background: rgba(239, 68, 68, .25); color: #fecaca; }
.call-body { padding: 10px; }
.call-stage { position: relative; aspect-ratio: 16 / 10; border-radius: 10px; overflow: hidden; background: radial-gradient(circle at 50% 40%, #144260, #06121e 75%); }
.call-stage.audio { aspect-ratio: auto; height: 150px; }
.call-audio-stage { height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 9px; color: #9cc8db; font-size: 12px; }
.call-audio-stage .call-avatar { width: 62px; height: 62px; }
.call-remote-video { width: 100%; height: 100%; object-fit: cover; display: block; }
.call-local-video { position: absolute; right: 8px; bottom: 8px; width: 31%; aspect-ratio: 4 / 3; object-fit: cover; border-radius: 7px; border: 1px solid rgba(148, 233, 255, .6); background: #020b12; }
.call-waiting { position: absolute; inset: 0; display: grid; place-items: center; color: #bfefff; font-size: 12px; background: rgba(3, 16, 26, .42); }
.call-video-placeholder { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; color: #8eb6cc; font-size: 11px; text-align: center; padding: 16px; }
.call-video-placeholder .call-avatar { width: 58px; height: 58px; }
.call-stage:not(.audio) { cursor: zoom-in; }
.call-icon-btn:disabled { opacity: .35; cursor: not-allowed; }
.call-camera-off { position: absolute; bottom: 8px; right: 8px; padding: 5px 8px; border-radius: 5px; background: rgba(0, 0, 0, .55); color: #a9c7d6; font-size: 10px; }
.call-hidden-audio { position: absolute; width: 1px; height: 1px; opacity: 0; pointer-events: none; overflow: hidden; }
.call-audio-enable { margin: 8px 0 0; border: 1px solid #0ea5e9; border-radius: 7px; padding: 6px 10px; background: rgba(14, 165, 233, .16); color: #bae6fd; font-size: 12px; cursor: pointer; display: inline-flex; align-items: center; gap: 5px; animation: im-audio-hint 1.8s ease-in-out infinite; }
@keyframes im-audio-hint { 0%,100% { box-shadow: 0 0 0 rgba(14,165,233,0); } 50% { box-shadow: 0 0 14px rgba(14,165,233,.35); } }
.call-controls { display: flex; align-items: center; gap: 8px; padding-top: 9px; }
.call-control { border: 1px solid #1c4a60; background: rgba(18, 55, 75, .8); color: #c9e6f4; border-radius: 8px; padding: 6px 8px; display: inline-flex; align-items: center; gap: 5px; font-size: 11px; cursor: pointer; }
.call-control.off { color: #fbbf24; border-color: #7c5a1d; }
.call-control.danger { color: #fca5a5; border-color: #7f2b2b; }
.call-control.danger:hover { background: rgba(239, 68, 68, .2); }
.call-bg-tip { margin-left: auto; color: #5f8195; font-size: 10px; }
.im-call-window.minimized .call-head { border-bottom: 0; }

/* 群通话窗口 */
.im-group-window { pointer-events: auto; position: fixed; right: 22px; bottom: 92px; width: min(760px, calc(100vw - 44px)); max-height: min(78vh, 720px); display: flex; flex-direction: column; border-radius: 15px; overflow: hidden; background: linear-gradient(165deg, #09243a, #071725); border: 1px solid #245f78; box-shadow: 0 18px 55px rgba(0, 0, 0, .55); color: #e8f8ff; animation: im-incoming-in .2s ease-out; }
.im-group-window.minimized { width: min(340px, calc(100vw - 44px)); }
.im-group-window.minimized .call-head { border-bottom: 0; }
.group-call-body { padding: 10px; overflow-y: auto; }
.group-tile-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 8px; }
.group-tile { position: relative; aspect-ratio: 4 / 3; border-radius: 10px; overflow: hidden; background: radial-gradient(circle at 50% 42%, #144260, #06121e 78%); border: 1px solid #17485e; }
.group-tile.videocam { background: #020b12; }
.group-tile.invited { opacity: .62; }
.group-tile.invited .group-tile-video { filter: grayscale(1); }
.group-tile-video { width: 100%; height: 100%; object-fit: cover; display: block; }
.group-tile-avatar { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; }
.group-tile-avatar > span { width: 52px; height: 52px; border-radius: 50%; display: grid; place-items: center; font-size: 20px; font-weight: 800; color: #d9f5ff; background: linear-gradient(145deg, #145b7d, #0b2d45); border: 1px solid #38bdf8; }
.group-tile-avatar > em { font-style: normal; font-size: 10px; color: #7fa6b8; }
.group-tile-bar { position: absolute; left: 0; right: 0; bottom: 0; display: flex; align-items: center; gap: 5px; padding: 5px 8px; background: linear-gradient(0deg, rgba(3, 12, 20, .88), transparent); font-size: 11px; }
.group-tile-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #dff4ff; }
.group-tile-muted { color: #fbbf24; font-size: 13px; }
.group-tile-tag { position: absolute; top: 6px; left: 6px; padding: 1px 6px; border-radius: 5px; background: rgba(34, 211, 238, .18); border: 1px solid rgba(34, 211, 238, .45); color: #a5f3fc; font-size: 9px; }
.group-tile-tag.pending { background: rgba(251, 191, 36, .16); border-color: rgba(251, 191, 36, .45); color: #fde68a; }
.group-call-waiting { padding: 8px 2px 0; color: #67e8f9; font-size: 11px; text-align: center; }
.group-offline-tip { padding: 6px 2px 0; color: #8ba9ba; font-size: 10px; }
.group-controls { flex-wrap: wrap; }
.group-controls .call-bg-tip { font-size: 9px; }

@keyframes im-incoming-in { from { opacity: 0; transform: translateY(10px) scale(.97); } to { opacity: 1; transform: translateY(0) scale(1); } }
@keyframes im-call-pulse { 0%, 100% { box-shadow: 0 0 0 0 rgba(56, 189, 248, .28); } 50% { box-shadow: 0 0 0 14px rgba(56, 189, 248, 0); } }
@media (max-width: 760px) {
  .im-call-window, .im-incoming { right: 10px; width: min(300px, calc(100vw - 20px)); }
  .im-call-window { bottom: 80px; }
  .im-group-window { right: 10px; width: calc(100vw - 20px); bottom: 80px; }
  .group-tile-grid { grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); }
}
</style>
