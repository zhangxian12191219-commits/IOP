/**
 * 全局即时通信 / WebRTC 通话状态。
 *
 * 该模块由 App.vue 持有，不随路由切换销毁，因此通话中的媒体流
 * 和 WebSocket 会继续在后台运行。
 */
import { computed, reactive, ref, shallowRef } from 'vue'
import { ElMessage } from 'element-plus'
import { imApi } from '@/api'
import { currentUser, getToken } from '@/store/auth'
import { playCallRingtone, playMessageSound, stopCallRingtone } from '@/utils/alertSound'

const DEFAULT_PREFERENCES = {
  enabled: true,
  shortcuts: ['im', 'notes', 'tools', 'audio-call', 'video-call', 'alerts'],
  custom_shortcuts: [],
  recent: [],
  position: null,
}

export const FLOATING_SHORTCUTS = [
  { id: 'im', label: '即时通信', icon: 'ChatDotRound', type: 'route', path: '/im' },
  { id: 'notes', label: '运维笔记', icon: 'Notebook', type: 'route', path: '/tools?tab=notes' },
  { id: 'tools', label: '系统工具', icon: 'Tools', type: 'route', path: '/tools' },
  { id: 'topology', label: '网络拓扑', icon: 'Connection', type: 'route', path: '/topology' },
  { id: 'devices', label: '资产管理', icon: 'Monitor', type: 'route', path: '/devices' },
  { id: 'alerts', label: '告警中心', icon: 'Bell', type: 'route', path: '/alerts' },
  { id: 'virtualization', label: '虚拟化管理', icon: 'Cpu', type: 'route', path: '/virtualization' },
  { id: 'bigscreen', label: '大屏展示', icon: 'DataBoard', type: 'route', path: '/bigscreen' },
  { id: 'audio-call', label: '语音通话', icon: 'PhoneFilled', type: 'call', callType: 'audio' },
  { id: 'video-call', label: '视频通话', icon: 'VideoCameraFilled', type: 'call', callType: 'video' },
]

export function floatingShortcutItems() {
  const custom = Array.isArray(imState.preferences.custom_shortcuts)
    ? imState.preferences.custom_shortcuts
    : []
  return [
    ...FLOATING_SHORTCUTS,
    ...custom
      .filter((item) => item && item.id && item.path)
      .map((item) => ({
        id: item.id,
        label: item.label || item.path,
        icon: item.icon || 'Link',
        type: 'route',
        path: item.path,
        custom: true,
      })),
  ]
}

export const imState = reactive({
  connected: false,
  connecting: false,
  users: [],
  activePeerId: null,
  chatOpen: false,
  messages: [],
  unread: {},
  incoming: null,
  call: {
    active: false,
    type: 'audio',
    peer: null,
    peerId: null,
    callId: '',
    status: 'idle',
    startedAt: null,
    muted: false,
    cameraOn: true,
    minimized: false,
  },
  // ---- 群聊 ----
  groups: [],
  activeGroupId: null,
  groupMessages: [],
  groupUnread: {},
  groupTyping: {},
  groupCall: {
    active: false,
    groupId: null,
    groupName: '',
    callId: '',
    type: 'audio',
    status: 'idle',
    startedAt: null,
    hostId: null,
    participants: [],
    offlineMembers: [],
    muted: false,
    cameraOn: false,
    minimized: false,
  },
  groupIncoming: null,
  // ---- 群白板 ----
  whiteboard: {
    open: false,
    groupId: null,
    boardId: 'main',
    strokes: [],
    loading: false,
  },
  whiteboardPointers: {},
  typing: false,
  preferences: { ...DEFAULT_PREFERENCES, shortcuts: [...DEFAULT_PREFERENCES.shortcuts] },
  preferencesLoaded: false,
  retentionDays: 15,
  maxAttachmentBytes: 500 * 1024 * 1024,
})

function emptyGroupCall() {
  return {
    active: false,
    groupId: null,
    groupName: '',
    callId: '',
    type: 'audio',
    status: 'idle',
    startedAt: null,
    hostId: null,
    participants: [],
    offlineMembers: [],
    muted: false,
    cameraOn: false,
    minimized: false,
  }
}

export const localStream = shallowRef(null)
export const remoteStream = shallowRef(null)
/** 群通话每个远端成员一路 MediaStream：{ [peerId]: MediaStream } */
export const groupStreams = shallowRef({})
export const imMessageSoundEnabled = ref(localStorage.getItem('nms_im_sound_enabled') !== '0')

export function toggleImMessageSound(value = !imMessageSoundEnabled.value) {
  imMessageSoundEnabled.value = !!value
  try {
    localStorage.setItem('nms_im_sound_enabled', imMessageSoundEnabled.value ? '1' : '0')
  } catch {
    /* 忽略存储异常 */
  }
  return imMessageSoundEnabled.value
}

let socket = null
let reconnectTimer = null
let manualClose = false
let preferenceTimer = null
let connectPromise = null
let callTimeout = null
let peerConnection = null
let pendingIce = []
let rtcConfig = { iceServers: [], iceTransportPolicy: 'all', iceCandidatePoolSize: 2 }
let rtcConfigPromise = null

async function ensureRtcConfig() {
  if (rtcConfigPromise) return rtcConfigPromise
  rtcConfigPromise = imApi.webrtcConfig()
    .then((res) => {
      const data = res?.data || {}
      rtcConfig = {
        iceServers: Array.isArray(data.iceServers) ? data.iceServers : [],
        iceTransportPolicy: data.iceTransportPolicy === 'relay' ? 'relay' : 'all',
        iceCandidatePoolSize: Number(data.iceCandidatePoolSize) || 2,
      }
      return rtcConfig
    })
    .catch(() => rtcConfig)
  return rtcConfigPromise
}

function rtcPeerOptions() {
  return {
    iceServers: Array.isArray(rtcConfig.iceServers) ? rtcConfig.iceServers : [],
    iceTransportPolicy: rtcConfig.iceTransportPolicy || 'all',
    iceCandidatePoolSize: Number(rtcConfig.iceCandidatePoolSize) || 2,
    bundlePolicy: 'max-bundle',
  }
}
let peerCount = 0

/** 群通话 mesh：每个远端成员一个 RTCPeerConnection */
const groupPeers = new Map()
const pendingGroupIce = new Map()
const groupTypingTimers = new Map()
const whiteboardPointerTimers = new Map()
let lastWhiteboardPointerAt = 0
let groupIncomingTimer = null

const meId = computed(() => Number(currentUser.value?.id || 0))
export const activePeer = computed(
  () => imState.users.find((user) => user.id === imState.activePeerId) || null,
)
export const activeGroup = computed(
  () => imState.groups.find((group) => group.id === imState.activeGroupId) || null,
)
export const onlineUsers = computed(() => imState.users.filter((user) => user.online))
export const unreadTotal = computed(() => {
  const direct = Object.values(imState.unread || {}).reduce((sum, value) => sum + Number(value || 0), 0)
  const groups = Object.values(imState.groupUnread || {}).reduce((sum, value) => sum + Number(value || 0), 0)
  return direct + groups
})
export const isCalling = computed(() => imState.call.active || !!imState.incoming
  || imState.groupCall.active || !!imState.groupIncoming)

function wsUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/api/im/ws?token=${encodeURIComponent(getToken())}`
}

function sendSocket(payload) {
  if (!socket || socket.readyState !== WebSocket.OPEN) return false
  socket.send(JSON.stringify(payload))
  return true
}

function upsertIncomingMessage(message) {
  if (!message) return
  if (imState.messages.some((item) => item.id === message.id)) return
  imState.messages.push(message)
  imState.messages.sort((a, b) => String(a.created_at || '').localeCompare(String(b.created_at || '')))
}

function replaceMessage(message) {
  if (!message) return
  const index = imState.messages.findIndex((item) => item.id === message.id)
  if (index >= 0) imState.messages.splice(index, 1, message)
}

function handleSocketMessage(payload) {
  if (!payload || typeof payload !== 'object') return
  if (payload.type === 'ready') {
    imState.connected = true
    return
  }
  if (payload.type === 'presence') {
    const visible = (payload.users || []).filter((user) => Number(user.id) !== meId.value)
    const previous = new Map(imState.users.map((user) => [user.id, user]))
    imState.users = visible.map((user) => ({ ...previous.get(user.id), ...user }))
    if (imState.activePeerId && !imState.users.some((user) => user.id === imState.activePeerId)) {
      imState.activePeerId = null
    }
    const onlineIds = new Set(visible.filter((user) => user.online).map((user) => Number(user.id)))
    imState.groups.forEach((group) => {
      (group.members || []).forEach((member) => {
        member.online = Number(member.id) === meId.value || onlineIds.has(Number(member.id))
      })
      group.online_count = (group.members || []).filter((member) => member.online).length
    })
    return
  }
  // ---- 群组列表变化（创建/加人/移人/退群/群主变更）----
  if (payload.type === 'group-updated') {
    refreshGroups().catch(() => {})
    return
  }
  // ---- 群消息 ----
  if (payload.type === 'message' && (payload.group_id || payload.message?.group_id)) {
    handleGroupIncomingMessage(payload)
    return
  }
  // ---- 群白板 ----
  if (payload.type === 'whiteboard-state') {
    handleWhiteboardState(payload)
    return
  }
  if (payload.type === 'whiteboard-stroke') {
    handleWhiteboardStrokeEvent(payload)
    return
  }
  if (payload.type === 'whiteboard-clear') {
    if (imState.whiteboard.open && Number(payload.group_id) === imState.whiteboard.groupId) {
      imState.whiteboard.strokes = []
    }
    return
  }
  if (payload.type === 'whiteboard-undo') {
    if (imState.whiteboard.open && Number(payload.group_id) === imState.whiteboard.groupId && payload.stroke_id) {
      imState.whiteboard.strokes = imState.whiteboard.strokes.filter((stroke) => stroke.id !== payload.stroke_id)
    }
    return
  }
  if (payload.type === 'whiteboard-pointer') {
    showWhiteboardPointer(payload)
    return
  }
  // ---- 群通话 ----
  if (payload.type === 'group-call-invite') {
    handleGroupCallInvite(payload)
    return
  }
  if (payload.type === 'group-call-started') {
    if (payload.call_id !== imState.groupCall.callId) return
    imState.groupCall.participants = payload.participants || []
    imState.groupCall.offlineMembers = payload.offline_members || []
    imState.groupCall.status = 'active'
    imState.groupCall.startedAt = Date.now()
    return
  }
  if (payload.type === 'group-call-roster') {
    if (!imState.groupCall.active || payload.call_id !== imState.groupCall.callId) return
    imState.groupCall.participants = payload.participants || []
    imState.groupCall.status = 'active'
    if (!imState.groupCall.startedAt) imState.groupCall.startedAt = Date.now()
    imState.groupCall.participants.forEach((participant) => {
      // 只向已加入通话的成员发起 mesh offer，避免向“仅被邀请未接听”的成员产生 glare
      if (Number(participant.id) !== meId.value && participant.joined !== false) {
        offerToGroupPeer(participant.id)
      }
    })
    return
  }
  if (payload.type === 'group-call-participant-joined') {
    if (payload.call_id !== imState.groupCall.callId) return
    imState.groupCall.participants = payload.participants || imState.groupCall.participants
    return
  }
  if (payload.type === 'group-call-participant-left') {
    if (payload.call_id !== imState.groupCall.callId) return
    removeGroupPeer(payload.user_id)
    imState.groupCall.participants = imState.groupCall.participants
      .filter((participant) => Number(participant.id) !== Number(payload.user_id))
    return
  }
  if (payload.type === 'group-call-media') {
    const participant = imState.groupCall.participants
      .find((item) => Number(item.id) === Number(payload.user_id))
    if (participant) {
      participant.muted = !!payload.muted
      participant.camera = !!payload.camera
    }
    return
  }
  if (payload.type === 'group-call-rejected') {
    const name = payload.user?.real_name || payload.user?.username || '成员'
    ElMessage.info(`${name} 拒绝了群通话`)
    return
  }
  if (payload.type === 'group-call-ended') {
    if (payload.call_id && payload.call_id !== imState.groupCall.callId) return
    if (imState.groupCall.active) ElMessage.info('群通话已结束')
    cleanupGroupCall()
    return
  }
  if (payload.type === 'group-read') {
    const groupId = Number(payload.group_id)
    if (Number(payload.user_id) === meId.value) imState.groupUnread[groupId] = 0
    const group = imState.groups.find((item) => item.id === groupId)
    const member = group?.members?.find((item) => Number(item.id) === Number(payload.user_id))
    if (member) member.last_read_at = payload.last_read_at
    return
  }
  if (payload.type === 'group-typing') {
    const groupId = Number(payload.group_id)
    if (!groupId || Number(payload.from?.id) === meId.value) return
    if (!payload.typing) {
      delete imState.groupTyping[groupId]
      return
    }
    imState.groupTyping[groupId] = {
      id: payload.from?.id,
      name: payload.from?.real_name || payload.from?.username || '成员',
    }
    window.clearTimeout(groupTypingTimers.get(groupId))
    groupTypingTimers.set(groupId, window.setTimeout(() => {
      delete imState.groupTyping[groupId]
      groupTypingTimers.delete(groupId)
    }, 2600))
    return
  }
  if (payload.type === 'message') {
    const message = payload.message
    if (!message) return
    if (imMessageSoundEnabled.value && Number(message.sender_id) !== meId.value) {
      playMessageSound()
    }
    const senderId = Number(message.sender_id)
    const isActiveConversation = imState.chatOpen && senderId === Number(imState.activePeerId)
    if (isActiveConversation) {
      upsertIncomingMessage(message)
      if (document.visibilityState === 'visible') {
        imState.unread[senderId] = 0
        sendSocket({ type: 'read', peer_id: senderId })
      } else {
        imState.unread[senderId] = Number(imState.unread[senderId] || 0) + 1
      }
    } else {
      imState.unread[senderId] = Number(imState.unread[senderId] || 0) + 1
    }
    return
  }
  if (payload.type === 'message-ack') {
    if (payload.message?.group_id) {
      upsertGroupMessageIfActive(payload.message)
      return
    }
    upsertIncomingMessage(payload.message)
    return
  }
  if (payload.type === 'message-recall') {
    if (payload.message?.group_id) {
      replaceGroupMessage(payload.message)
      return
    }
    replaceMessage(payload.message)
    return
  }
  if (payload.type === 'read') {
    if (payload.self || Number(payload.by) === meId.value) {
      const peerId = Number(payload.peer_id)
      if (peerId) imState.unread[peerId] = 0
    }
    return
  }
  if (payload.type === 'typing') {
    if (payload.from?.id === imState.activePeerId) {
      imState.typing = !!payload.typing
      window.clearTimeout(imState._typingTimer)
      imState._typingTimer = window.setTimeout(() => { imState.typing = false }, 2500)
    }
    return
  }
  if (payload.type === 'call-offer') {
    if (payload.group_id) {
      handleGroupOffer(payload)
      return
    }
    if (imState.call.active || imState.incoming) {
      sendSocket({
        type: 'call-reject',
        to: payload.from?.id,
        call_id: payload.call_id,
        reason: 'busy',
      })
      return
    }
    imState.incoming = payload
    playCallRingtone('incoming')
    return
  }
  if (payload.type === 'call-answer') {
    if (payload.group_id) {
      handleGroupAnswer(payload)
      return
    }
    stopCallRingtone()
    if (!peerConnection) return
    peerConnection.setRemoteDescription(new RTCSessionDescription(payload.sdp))
      .then(async () => {
        await flushPendingIce()
        if (payload.call_type === 'audio' && imState.call.type === 'video') {
          imState.call.type = 'audio'
          imState.call.cameraOn = false
          ElMessage.warning('对方摄像头不可用，已切换为语音通话')
        }
        imState.call.status = 'active'
        imState.call.startedAt = Date.now()
        window.clearTimeout(callTimeout)
      })
      .catch(() => {
        ElMessage.error('通话连接失败')
        endCall()
      })
    return
  }
  if (payload.type === 'call-ice') {
    if (payload.group_id) {
      handleGroupIce(payload)
      return
    }
    if (!payload.candidate) return
    if (!peerConnection || !peerConnection.remoteDescription) {
      pendingIce.push(payload.candidate)
      return
    }
    peerConnection.addIceCandidate(new RTCIceCandidate(payload.candidate)).catch(() => {})
    return
  }
  if (payload.type === 'call-hangup') {
    if (payload.group_id) {
      removeGroupPeer(payload.from?.id)
      return
    }
    stopCallRingtone()
    if (payload.call_id && imState.call.callId && payload.call_id !== imState.call.callId) return
    ElMessage.info('对方已结束通话')
    cleanupCall()
    return
  }
  if (payload.type === 'call-reject') {
    if (payload.group_id) return
    stopCallRingtone()
    if (imState.call.callId && payload.call_id && payload.call_id !== imState.call.callId) return
    ElMessage.warning(payload.reason === 'busy' ? '对方正在通话中' : '对方已拒绝通话')
    cleanupCall()
    return
  }
  if (payload.type === 'call-error') {
    if (payload.group_id) {
      ElMessage.error(payload.message || '群通话连接失败')
      if (imState.groupCall.active && payload.call_id === imState.groupCall.callId) cleanupGroupCall()
      return
    }
    stopCallRingtone()
    ElMessage.error(payload.message || '通话失败')
    cleanupCall()
    return
  }
  if (payload.type === 'error') {
    ElMessage.error(payload.message || '即时通信发生错误')
  }
}

/* ==================== 群聊消息 ==================== */

function upsertGroupMessage(message) {
  if (!message) return
  const index = imState.groupMessages.findIndex((item) => item.id === message.id)
  if (index >= 0) {
    imState.groupMessages.splice(index, 1, message)
    return
  }
  imState.groupMessages.push(message)
  imState.groupMessages.sort((a, b) => String(a.created_at || '').localeCompare(String(b.created_at || '')))
}

function replaceGroupMessage(message) {
  if (!message?.group_id) return
  const index = imState.groupMessages.findIndex((item) => item.id === message.id)
  if (index >= 0) imState.groupMessages.splice(index, 1, message)
}

function touchGroupLastMessage(groupId, message) {
  const group = imState.groups.find((item) => item.id === Number(groupId))
  if (!group) return
  group.last_message = {
    content: message.recalled ? '[消息已撤回]' : (Number(message.group_id) ? message.content : ''),
    created_at: message.created_at,
    sender_id: message.sender_id,
    sender_name: message.sender?.real_name || message.sender?.username || '',
    message_type: message.message_type,
  }
}

function upsertGroupMessageIfActive(message) {
  const groupId = Number(message?.group_id)
  if (!groupId) return
  touchGroupLastMessage(groupId, message)
  if (imState.activeGroupId === groupId) upsertGroupMessage(message)
}

function handleGroupIncomingMessage(payload) {
  const message = payload.message
  if (!message) return
  const groupId = Number(message.group_id || payload.group_id)
  if (!groupId || Number(message.sender_id) === meId.value) return
  if (imMessageSoundEnabled.value) playMessageSound()
  touchGroupLastMessage(groupId, message)
  if (imState.chatOpen && imState.activeGroupId === groupId) {
    upsertGroupMessage(message)
    if (document.visibilityState === 'visible') {
      imState.groupUnread[groupId] = 0
      sendSocket({ type: 'group-read', group_id: groupId })
    } else {
      imState.groupUnread[groupId] = Number(imState.groupUnread[groupId] || 0) + 1
    }
  } else {
    imState.groupUnread[groupId] = Number(imState.groupUnread[groupId] || 0) + 1
    if (!imState.groups.some((group) => group.id === groupId)) {
      refreshGroups().catch(() => {})
    }
  }
}

/* ==================== 群通话（mesh WebRTC） ==================== */

function ensureGroupPeer(peerId) {
  const id = Number(peerId)
  const existing = groupPeers.get(id)
  if (existing) return existing
  const pc = new RTCPeerConnection(rtcPeerOptions())
  const entry = { pc, pendingIce: [], stream: null, offered: false }
  groupPeers.set(id, entry)
  if (localStream.value) {
    localStream.value.getTracks().forEach((track) => pc.addTrack(track, localStream.value))
  }
  pc.onicecandidate = (event) => {
    if (!event.candidate || !imState.groupCall.active) return
    sendSocket({
      type: 'call-ice',
      group_id: imState.groupCall.groupId,
      call_id: imState.groupCall.callId,
      to: id,
      candidate: event.candidate.toJSON ? event.candidate.toJSON() : event.candidate,
    })
  }
  pc.ontrack = (event) => {
    let stream = event.streams?.[0]
    if (!stream) {
      stream = entry.stream || new MediaStream()
      stream.addTrack(event.track)
    }
    entry.stream = stream
    groupStreams.value = { ...groupStreams.value, [id]: stream }
  }
  pc.onconnectionstatechange = () => {
    if (!imState.groupCall.active) return
    if (pc.connectionState === 'failed') {
      ensureGroupPeer(id).offered = false
    }
  }
  const orphanIce = pendingGroupIce.get(id) || []
  pendingGroupIce.delete(id)
  if (orphanIce.length) entry.pendingIce.push(...orphanIce)
  return entry
}

async function offerToGroupPeer(peerId) {
  const id = Number(peerId)
  if (!imState.groupCall.active || !id || id === meId.value) return
  const entry = ensureGroupPeer(id)
  if (entry.offered) return
  entry.offered = true
  try {
    const offer = await entry.pc.createOffer()
    await entry.pc.setLocalDescription(offer)
    sendSocket({
      type: 'call-offer',
      group_id: imState.groupCall.groupId,
      call_id: imState.groupCall.callId,
      to: id,
      call_type: imState.groupCall.type,
      sdp: entry.pc.localDescription,
    })
  } catch {
    entry.offered = false
  }
}

async function flushGroupIce(entry) {
  while (entry.pendingIce.length) {
    const candidate = entry.pendingIce.shift()
    try {
      await entry.pc.addIceCandidate(new RTCIceCandidate(candidate))
    } catch {
      /* 忽略过期 candidate */
    }
  }
}

async function handleGroupOffer(payload) {
  if (!imState.groupCall.active || payload.call_id !== imState.groupCall.callId) return
  const peerId = Number(payload.from?.id)
  if (!peerId || peerId === meId.value || !payload.sdp) return
  const entry = ensureGroupPeer(peerId)
  try {
    await entry.pc.setRemoteDescription(new RTCSessionDescription(payload.sdp))
    await flushGroupIce(entry)
    const answer = await entry.pc.createAnswer()
    await entry.pc.setLocalDescription(answer)
    sendSocket({
      type: 'call-answer',
      group_id: imState.groupCall.groupId,
      call_id: imState.groupCall.callId,
      to: peerId,
      sdp: entry.pc.localDescription,
    })
  } catch {
    ElMessage.warning('群通话连接失败，请重试')
  }
}

async function handleGroupAnswer(payload) {
  if (!imState.groupCall.active || payload.call_id !== imState.groupCall.callId) return
  const peerId = Number(payload.from?.id)
  const entry = groupPeers.get(peerId)
  if (!entry || !payload.sdp) return
  try {
    await entry.pc.setRemoteDescription(new RTCSessionDescription(payload.sdp))
    await flushGroupIce(entry)
  } catch {
    ElMessage.warning('群通话连接失败，请重试')
  }
}

function handleGroupIce(payload) {
  if (!imState.groupCall.active || payload.call_id !== imState.groupCall.callId) return
  const candidate = payload.candidate
  if (!candidate) return
  const peerId = Number(payload.from?.id)
  const entry = groupPeers.get(peerId)
  if (entry && entry.pc.remoteDescription) {
    entry.pc.addIceCandidate(new RTCIceCandidate(candidate)).catch(() => {})
    return
  }
  if (entry) {
    entry.pendingIce.push(candidate)
    return
  }
  const list = pendingGroupIce.get(peerId) || []
  list.push(candidate)
  pendingGroupIce.set(peerId, list)
}

function removeGroupPeer(peerId) {
  const id = Number(peerId)
  const entry = groupPeers.get(id)
  if (entry) {
    try {
      entry.pc.close()
    } catch {
      /* ignore */
    }
    groupPeers.delete(id)
  }
  if (groupStreams.value[id]) {
    const next = { ...groupStreams.value }
    delete next[id]
    groupStreams.value = next
  }
}

function handleGroupCallInvite(payload) {
  if (imState.groupCall.active && payload.call_id === imState.groupCall.callId) return
  if (imState.groupIncoming?.call_id === payload.call_id) return
  if (imState.groupCall.active || imState.groupIncoming || imState.call.active || imState.incoming) {
    sendSocket({
      type: 'group-call-reject',
      group_id: payload.group_id,
      call_id: payload.call_id,
      reason: 'busy',
    })
    return
  }
  imState.groupIncoming = payload
  playCallRingtone('incoming')
  window.clearTimeout(groupIncomingTimer)
  groupIncomingTimer = window.setTimeout(() => {
    if (imState.groupIncoming?.call_id === payload.call_id) {
      sendSocket({
        type: 'group-call-reject',
        group_id: payload.group_id,
        call_id: payload.call_id,
        reason: 'timeout',
      })
      imState.groupIncoming = null
      stopCallRingtone()
    }
  }, 45000)
}

export async function startGroupCall(group, type = 'audio') {
  await ensureRtcConfig()
  const groupId = Number(group?.id)
  if (!groupId) return false
  if (!imState.connected) {
    ElMessage.warning('即时通信尚未连接')
    return false
  }
  const onlineMembers = (group.members || []).filter((member) => Number(member.id) !== meId.value && member.online)
  if (!onlineMembers.length) {
    ElMessage.warning('当前没有其他在线成员，无法发起群通话')
    return false
  }
  cleanupCall()
  cleanupGroupCall()
  const callType = type === 'video' ? 'video' : 'audio'
  const self = group.members?.find((member) => Number(member.id) === meId.value)
  imState.groupCall = {
    ...emptyGroupCall(),
    active: true,
    groupId,
    groupName: group.name || '群通话',
    callId: `g${meId.value}-${groupId}-${Date.now()}`,
    type: callType,
    status: 'connecting',
    hostId: meId.value,
    participants: [
      {
        id: meId.value,
        real_name: self?.real_name || currentUser.value?.real_name || currentUser.value?.username || '我',
        username: self?.username || currentUser.value?.username || '',
        online: true,
        muted: false,
        camera: callType === 'video',
      },
      ...onlineMembers.map((member) => ({ ...member, muted: false, camera: callType === 'video' })),
    ],
    cameraOn: callType === 'video',
  }
  try {
    localStream.value = await getMedia(callType)
    const actualType = effectiveCallType(localStream.value, callType)
    if (actualType !== callType) {
      imState.groupCall.type = 'audio'
      imState.groupCall.cameraOn = false
      imState.groupCall.participants = (imState.groupCall.participants || []).map((item) => ({ ...item, camera: false }))
      ElMessage.warning(localStream.value.__videoError || '摄像头不可用，已切换为群语音通话')
    }
    const sent = sendSocket({
      type: 'group-call-start',
      group_id: groupId,
      call_id: imState.groupCall.callId,
      call_type: actualType,
    })
    if (!sent) throw new Error('通信连接已断开')
    return true
  } catch (error) {
    ElMessage.error(error?.message || '无法发起群通话，请检查麦克风/摄像头权限')
    cleanupGroupCall()
    return false
  }
}

export async function acceptGroupIncoming() {
  await ensureRtcConfig()
  const incoming = imState.groupIncoming
  if (!incoming) return
  const type = incoming.call_type === 'video' ? 'video' : 'audio'
  stopCallRingtone()
  window.clearTimeout(groupIncomingTimer)
  cleanupCall()
  const participants = incoming.participants || []
  cleanupGroupCall()
  imState.groupCall = {
    ...emptyGroupCall(),
    active: true,
    groupId: Number(incoming.group_id),
    groupName: incoming.group_name || '群通话',
    callId: incoming.call_id,
    type,
    status: 'connecting',
    hostId: incoming.from?.id || null,
    participants,
    cameraOn: type === 'video',
  }
  try {
    localStream.value = await getMedia(type)
    if (effectiveCallType(localStream.value, type) !== type) {
      imState.groupCall.type = 'audio'
      imState.groupCall.cameraOn = false
      imState.groupCall.participants = (imState.groupCall.participants || []).map((item) => ({ ...item, camera: false }))
      ElMessage.warning(localStream.value.__videoError || '摄像头不可用，已切换为群语音通话')
    }
    const sent = sendSocket({
      type: 'group-call-join',
      group_id: imState.groupCall.groupId,
      call_id: imState.groupCall.callId,
    })
    if (!sent) throw new Error('通信连接已断开')
  } catch (error) {
    ElMessage.error(error?.message || '加入群通话失败，请检查麦克风/摄像头权限')
    sendSocket({
      type: 'group-call-reject',
      group_id: incoming.group_id,
      call_id: incoming.call_id,
      reason: 'media-error',
    })
    cleanupGroupCall()
  }
}

export function rejectGroupIncoming() {
  const incoming = imState.groupIncoming
  if (!incoming) return
  stopCallRingtone()
  window.clearTimeout(groupIncomingTimer)
  sendSocket({
    type: 'group-call-reject',
    group_id: incoming.group_id,
    call_id: incoming.call_id,
    reason: 'rejected',
  })
  imState.groupIncoming = null
}

export function leaveGroupCall() {
  if (!imState.groupCall.active) return
  sendSocket({
    type: 'group-call-leave',
    group_id: imState.groupCall.groupId,
    call_id: imState.groupCall.callId,
  })
  cleanupGroupCall()
}

export function endGroupCall() {
  if (!imState.groupCall.active) return
  sendSocket({
    type: 'group-call-end',
    group_id: imState.groupCall.groupId,
    call_id: imState.groupCall.callId,
  })
  cleanupGroupCall()
}

export function cleanupGroupCall() {
  window.clearTimeout(groupIncomingTimer)
  groupIncomingTimer = null
  imState.groupIncoming = null
  if (!imState.groupCall.active && !groupPeers.size) {
    imState.groupCall = emptyGroupCall()
    stopCallRingtone()
    return
  }
  groupPeers.forEach((entry) => {
    try {
      entry.pc.close()
    } catch {
      /* ignore */
    }
  })
  groupPeers.clear()
  pendingGroupIce.clear()
  groupStreams.value = {}
  if (imState.groupCall.active && localStream.value) {
    localStream.value.getTracks().forEach((track) => track.stop())
    localStream.value = null
  }
  imState.groupCall = emptyGroupCall()
  stopCallRingtone()
}

export function toggleGroupMute() {
  const tracks = localStream.value?.getAudioTracks?.() || []
  tracks.forEach((track) => { track.enabled = !track.enabled })
  imState.groupCall.muted = tracks.length ? !tracks[0].enabled : !imState.groupCall.muted
  sendGroupMediaState()
}

export function toggleGroupCamera() {
  const tracks = localStream.value?.getVideoTracks?.() || []
  tracks.forEach((track) => { track.enabled = !track.enabled })
  imState.groupCall.cameraOn = tracks.length ? tracks[0].enabled : !imState.groupCall.cameraOn
  sendGroupMediaState()
}

function sendGroupMediaState() {
  if (!imState.groupCall.active) return
  sendSocket({
    type: 'group-call-media',
    group_id: imState.groupCall.groupId,
    call_id: imState.groupCall.callId,
    muted: !!imState.groupCall.muted,
    camera: !!imState.groupCall.cameraOn,
  })
}

export function minimizeGroupCall(minimized = true) {
  imState.groupCall.minimized = !!minimized
}

/* ==================== 群组列表 / 群会话 ==================== */

export async function refreshGroups() {
  const res = await imApi.groups()
  imState.groups = res.data?.items || []
  imState.groupUnread = Object.fromEntries(
    Object.entries(res.data?.group_unread || {}).map(([key, value]) => [Number(key), Number(value)]),
  )
  if (imState.activeGroupId && !imState.groups.some((group) => group.id === imState.activeGroupId)) {
    imState.activeGroupId = null
    imState.groupMessages = []
    if (imState.whiteboard.open) closeWhiteboard()
    if (imState.groupCall.active) cleanupGroupCall()
  }
  if (imState.activeGroupId) imState.groupUnread[imState.activeGroupId] = 0
  return imState.groups
}

export async function openGroupConversation(groupId) {
  const id = Number(groupId)
  if (!id) return
  imState.activeGroupId = id
  imState.activePeerId = null
  imState.groupMessages = []
  imState.typing = false
  delete imState.groupTyping[id]
  const res = await imApi.groupMessages(id)
  imState.groupMessages = res.data?.items || []
  const fresh = res.data?.group
  if (fresh) {
    const index = imState.groups.findIndex((group) => group.id === id)
    if (index >= 0) imState.groups.splice(index, 1, fresh)
    else imState.groups.unshift(fresh)
  }
  imState.groupUnread[id] = 0
  imState.retentionDays = Number(res.data?.retention_days || imState.retentionDays || 15)
  sendSocket({ type: 'group-read', group_id: id })
}

export function sendGroupMessage(content, attachmentId = null) {
  const text = String(content || '').trim()
  if (!text && !attachmentId) return false
  if (!imState.activeGroupId) return false
  const sent = sendSocket({
    type: 'message',
    group_id: imState.activeGroupId,
    content: text,
    attachment_id: attachmentId || null,
    temp_id: `g-${Date.now()}`,
  })
  if (!sent) ElMessage.warning('通信尚未连接，请稍后重试')
  return sent
}

export function sendGroupTyping(typing) {
  if (!imState.activeGroupId) return
  sendSocket({ type: 'group-typing', group_id: imState.activeGroupId, typing: !!typing })
}

export function markActiveGroupRead() {
  if (!imState.chatOpen || !imState.activeGroupId) return
  if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return
  const groupId = Number(imState.activeGroupId)
  imState.groupUnread[groupId] = 0
  sendSocket({ type: 'group-read', group_id: groupId })
}

export async function createGroup(name, memberIds = []) {
  const res = await imApi.createGroup({ name, member_ids: memberIds })
  await refreshGroups()
  return res.data?.group
}

export async function addGroupMembers(groupId, userIds) {
  const res = await imApi.addGroupMembers(groupId, userIds)
  await refreshGroups()
  return res.data?.group
}

export async function removeGroupMember(groupId, userId) {
  await imApi.removeGroupMember(groupId, userId)
  await refreshGroups()
}

export async function leaveGroup(groupId) {
  const res = await imApi.leaveGroup(groupId)
  if (Number(imState.activeGroupId) === Number(groupId)) {
    imState.activeGroupId = null
    imState.groupMessages = []
    if (imState.whiteboard.open) closeWhiteboard()
  }
  await refreshGroups()
  return res.data
}

/* ==================== 群白板 ==================== */

function resetWhiteboardPointers() {
  whiteboardPointerTimers.forEach((timer) => window.clearTimeout(timer))
  whiteboardPointerTimers.clear()
  imState.whiteboardPointers = {}
}

function upsertWhiteboardStroke(stroke, replaceSameTemp = true) {
  if (!stroke) return
  const list = imState.whiteboard.strokes.slice()
  let index = -1
  if (stroke.id) index = list.findIndex((item) => item.id === stroke.id)
  if (index < 0 && replaceSameTemp && stroke.temp_id) {
    index = list.findIndex((item) => item.temp_id === stroke.temp_id)
  }
  if (index >= 0) list.splice(index, 1, { ...list[index], ...stroke })
  else list.push(stroke)
  imState.whiteboard.strokes = list
}

function handleWhiteboardState(payload) {
  if (!imState.whiteboard.open || Number(payload.group_id) !== imState.whiteboard.groupId) return
  imState.whiteboard.strokes = payload.strokes || []
  if (payload.board_id) imState.whiteboard.boardId = payload.board_id
}

function handleWhiteboardStrokeEvent(payload) {
  if (!imState.whiteboard.open || Number(payload.group_id) !== imState.whiteboard.groupId) return
  upsertWhiteboardStroke(payload.stroke)
}

function showWhiteboardPointer(payload) {
  if (!imState.whiteboard.open || Number(payload.group_id) !== imState.whiteboard.groupId) return
  const userId = Number(payload.from?.id)
  if (!userId || userId === meId.value) return
  imState.whiteboardPointers[userId] = {
    x: Number(payload.x) || 0,
    y: Number(payload.y) || 0,
    name: payload.from?.real_name || payload.from?.username || '成员',
    at: Date.now(),
  }
  window.clearTimeout(whiteboardPointerTimers.get(userId))
  whiteboardPointerTimers.set(userId, window.setTimeout(() => {
    delete imState.whiteboardPointers[userId]
    whiteboardPointerTimers.delete(userId)
  }, 3000))
}

export async function openWhiteboard(groupId) {
  const id = Number(groupId)
  if (!id) return
  imState.whiteboard.open = true
  imState.whiteboard.groupId = id
  imState.whiteboard.boardId = 'main'
  imState.whiteboard.strokes = []
  imState.whiteboard.loading = true
  resetWhiteboardPointers()
  try {
    const res = await imApi.groupWhiteboard(id)
    if (imState.whiteboard.open && imState.whiteboard.groupId === id) {
      imState.whiteboard.strokes = res.data?.strokes || []
      imState.whiteboard.boardId = res.data?.board_id || 'main'
    }
  } catch {
    ElMessage.warning('白板历史加载失败，仍可继续书写')
  } finally {
    imState.whiteboard.loading = false
  }
  sendSocket({ type: 'whiteboard-sync', group_id: id, board_id: imState.whiteboard.boardId })
}

export function closeWhiteboard() {
  imState.whiteboard.open = false
  imState.whiteboard.groupId = null
  imState.whiteboard.strokes = []
  imState.whiteboard.loading = false
  resetWhiteboardPointers()
  lastWhiteboardPointerAt = 0
}

export function sendWhiteboardStroke(stroke) {
  if (!imState.whiteboard.open) return false
  if (!stroke || !Array.isArray(stroke.points) || stroke.points.length < 2) return false
  const tempId = stroke.temp_id || `t-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  const outgoing = { ...stroke, temp_id: tempId }
  upsertWhiteboardStroke(outgoing)
  sendSocket({
    type: 'whiteboard-draw',
    group_id: imState.whiteboard.groupId,
    board_id: imState.whiteboard.boardId,
    stroke: outgoing,
  })
  return true
}

export function undoWhiteboard() {
  if (!imState.whiteboard.open) return
  sendSocket({
    type: 'whiteboard-undo',
    group_id: imState.whiteboard.groupId,
    board_id: imState.whiteboard.boardId,
  })
}

export function clearWhiteboard() {
  if (!imState.whiteboard.open) return
  imState.whiteboard.strokes = []
  sendSocket({
    type: 'whiteboard-clear',
    group_id: imState.whiteboard.groupId,
    board_id: imState.whiteboard.boardId,
  })
}

export function sendWhiteboardPointer(x, y, visible = true) {
  if (!imState.whiteboard.open) return
  const now = Date.now()
  if (visible && now - lastWhiteboardPointerAt < 60) return
  lastWhiteboardPointerAt = now
  sendSocket({
    type: 'whiteboard-pointer',
    group_id: imState.whiteboard.groupId,
    board_id: imState.whiteboard.boardId,
    x,
    y,
    visible,
  })
}

async function openSocket() {
  const token = getToken()
  if (!token || manualClose) return
  if (socket && [WebSocket.OPEN, WebSocket.CONNECTING].includes(socket.readyState)) return
  imState.connecting = true
  try {
    socket = new WebSocket(wsUrl())
    socket.onopen = () => {
      imState.connected = true
      imState.connecting = false
    }
    socket.onmessage = (event) => {
      try {
        handleSocketMessage(JSON.parse(event.data))
      } catch {
        /* 忽略非法消息 */
      }
    }
    socket.onerror = () => {
      imState.connecting = false
    }
    socket.onclose = (event) => {
      imState.connected = false
      imState.connecting = false
      socket = null
      if (event?.code === 4401) {
        manualClose = true
        return
      }
      if (!manualClose) scheduleReconnect()
    }
  } catch {
    imState.connecting = false
    scheduleReconnect()
  }
}

function scheduleReconnect() {
  if (manualClose || reconnectTimer) return
  reconnectTimer = window.setTimeout(() => {
    reconnectTimer = null
    openSocket()
  }, 3000)
}

export async function connectIM() {
  if (!getToken()) return
  manualClose = false
  if (socket && [WebSocket.OPEN, WebSocket.CONNECTING].includes(socket.readyState)) {
    await Promise.all([refreshUsers(), refreshUnread(), refreshGroups().catch(() => {})])
    return
  }
  if (connectPromise) return connectPromise
  connectPromise = (async () => {
    imState.connecting = true
    try {
      await Promise.all([refreshUsers(), loadPreferences(), refreshUnread(), refreshGroups().catch(() => {}), ensureRtcConfig().catch(() => {})])
    } catch {
      /* 网络异常时仍尝试建立 WebSocket */
    } finally {
      imState.connecting = false
    }
    openSocket()
  })()
  try {
    await connectPromise
  } finally {
    connectPromise = null
  }
}

export function disconnectIM() {
  manualClose = true
  if (reconnectTimer) {
    window.clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  if (socket) {
    socket.close()
    socket = null
  }
  imState.connected = false
  cleanupCall()
  cleanupGroupCall()
  closeWhiteboard()
  imState.incoming = null
  imState.groupIncoming = null
  imState.groups = []
  imState.groupMessages = []
  imState.groupUnread = {}
  imState.groupTyping = {}
  imState.activeGroupId = null
}

export async function refreshUsers() {
  const res = await imApi.users()
  imState.users = (res.data?.items || []).map((user) => ({
    ...user,
    online: !!user.online,
  }))
  imState.unread = Object.fromEntries(
    Object.entries(res.data?.unread || {}).map(([key, value]) => [Number(key), Number(value)]),
  )
  imState.retentionDays = Number(res.data?.retention_days || 15)
  return imState.users
}

export async function refreshUnread() {
  const res = await imApi.unread()
  imState.unread = Object.fromEntries(
    Object.entries(res.data?.counts || {}).map(([key, value]) => [Number(key), Number(value)]),
  )
  imState.groupUnread = Object.fromEntries(
    Object.entries(res.data?.group_counts || {}).map(([key, value]) => [Number(key), Number(value)]),
  )
}

export async function openConversation(peerId) {
  const id = Number(peerId)
  if (!id) return
  if (imState.whiteboard.open) closeWhiteboard()
  imState.activePeerId = id
  imState.activeGroupId = null
  imState.typing = false
  const res = await imApi.messages(id)
  imState.messages = res.data?.items || []
  imState.retentionDays = Number(res.data?.retention_days || imState.retentionDays || 15)
  imState.unread[id] = 0
  sendSocket({ type: 'read', peer_id: id })
}

/** 当前会话页面可见时，把该会话标记为已读（含从后台标签页切回）。 */
export function markActiveConversationRead() {
  if (!imState.chatOpen) return
  if (imState.activeGroupId) {
    markActiveGroupRead()
    return
  }
  if (!imState.activePeerId) return
  if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return
  const peerId = Number(imState.activePeerId)
  imState.unread[peerId] = 0
  sendSocket({ type: 'read', peer_id: peerId })
}

if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) markActiveConversationRead()
  })
}

export function sendMessage(content, attachmentId = null) {
  const text = String(content || '').trim()
  if (!text && !attachmentId) return false
  if (!imState.activePeerId) return false
  const sent = sendSocket({
    type: 'message',
    to: imState.activePeerId,
    content: text,
    attachment_id: attachmentId || null,
    temp_id: `m-${Date.now()}`,
  })
  if (!sent) ElMessage.warning('通信尚未连接，请稍后重试')
  return sent
}

export function sendTyping(typing) {
  if (!imState.activePeerId) return
  sendSocket({ type: 'typing', to: imState.activePeerId, typing: !!typing })
}

export async function recallMessage(messageId) {
  const res = await imApi.recallMessage(messageId)
  replaceMessage(res.data?.message)
  return res.data?.message
}

export async function deleteMessage(messageId) {
  await imApi.deleteMessage(messageId)
  imState.messages = imState.messages.filter((item) => item.id !== Number(messageId))
}

export async function recallGroupMessage(messageId) {
  const res = await imApi.recallMessage(messageId)
  replaceGroupMessage(res.data?.message)
  return res.data?.message
}

export async function deleteGroupMessage(messageId) {
  await imApi.deleteMessage(messageId)
  imState.groupMessages = imState.groupMessages.filter((item) => item.id !== Number(messageId))
}

export async function loadPreferences() {
  const res = await imApi.preferences()
  imState.preferences = {
    ...DEFAULT_PREFERENCES,
    ...(res.data?.settings || {}),
    shortcuts: [...(res.data?.settings?.shortcuts || DEFAULT_PREFERENCES.shortcuts)],
    custom_shortcuts: [...(res.data?.settings?.custom_shortcuts || [])],
    recent: [...(res.data?.settings?.recent || [])],
  }
  imState.preferencesLoaded = true
  return imState.preferences
}

export async function savePreferences(patch = {}, immediate = false) {
  imState.preferences = {
    ...imState.preferences,
    ...(patch || {}),
  }
  if (preferenceTimer) {
    window.clearTimeout(preferenceTimer)
    preferenceTimer = null
  }
  const commit = async () => {
    try {
      await imApi.savePreferences(imState.preferences)
    } catch {
      /* 本地状态仍保留，下次进入页面再同步 */
    }
  }
  if (immediate) await commit()
  else {
    preferenceTimer = window.setTimeout(commit, 500)
  }
}

export function recordRecentRoute(route) {
  if (!route || route.meta?.public || route.path === '/login' || route.path === '/') return
  const path = route.fullPath || route.path
  if (!path) return
  const title = String(route.meta?.title || route.name || path)
  const recent = (imState.preferences.recent || []).filter((item) => item.path !== path)
  recent.unshift({ path, title, visited_at: new Date().toISOString() })
  savePreferences({ recent: recent.slice(0, 3) })
}

function mediaErrorMessage(error, type) {
  if (!window.isSecureContext) {
    return '音视频通话必须通过 HTTPS 或 localhost 打开；当前页面不是安全上下文'
  }
  const name = String(error?.name || '')
  if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
    return type === 'video'
      ? '摄像头权限被拒绝，请点击地址栏左侧站点图标，允许摄像头和麦克风后重试'
      : '麦克风权限被拒绝，请点击地址栏左侧站点图标，允许麦克风后重试'
  }
  if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
    return type === 'video' ? '未检测到摄像头，已切换为语音通话' : '未检测到麦克风设备'
  }
  if (name === 'NotReadableError' || name === 'TrackStartError') {
    return type === 'video'
      ? '摄像头正被其他程序占用，已切换为语音通话'
      : '麦克风正被其他程序占用'
  }
  if (name === 'OverconstrainedError' || name === 'ConstraintNotSatisfiedError') {
    return type === 'video' ? '摄像头不支持请求的分辨率，已切换为语音通话' : '麦克风参数不受支持'
  }
  return error?.message || '无法获取麦克风/摄像头，请检查设备与权限'
}

async function getMedia(type) {
  const localHost = ['localhost', '127.0.0.1', '::1'].includes(window.location.hostname)
  if (!window.isSecureContext && !localHost) {
    throw new Error('局域网音视频通话必须使用 HTTPS 访问（浏览器禁止 HTTP 页面调用麦克风/摄像头）')
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error('当前浏览器不支持音视频通话（需要 HTTPS 与 getUserMedia）')
  }
  const audio = { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
  try {
    return await navigator.mediaDevices.getUserMedia({
      audio,
      video: type === 'video' ? { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' } : false,
    })
  } catch (error) {
    // 视频不可用时不能让整通电话失败：保留麦克风，降级为语音并提示原因。
    if (type === 'video') {
      try {
        const audioOnly = await navigator.mediaDevices.getUserMedia({ audio, video: false })
        audioOnly.__videoError = mediaErrorMessage(error, 'video')
        return audioOnly
      } catch (audioError) {
        throw new Error(mediaErrorMessage(audioError, 'audio'))
      }
    }
    throw new Error(mediaErrorMessage(error, type))
  }
}

function effectiveCallType(stream, requested) {
  return requested === 'video' && !(stream?.getVideoTracks?.().length) ? 'audio' : requested
}

function createPeerConnection(peerId) {
  const pc = new RTCPeerConnection(rtcPeerOptions())
  peerConnection = pc
  pendingIce = []
  if (localStream.value) {
    localStream.value.getTracks().forEach((track) => pc.addTrack(track, localStream.value))
  }
  pc.onicecandidate = (event) => {
    if (event.candidate) {
      sendSocket({
        type: 'call-ice',
        to: peerId,
        call_id: imState.call.callId,
        candidate: event.candidate.toJSON ? event.candidate.toJSON() : event.candidate,
      })
    }
  }
  pc.ontrack = (event) => {
    if (event.streams && event.streams[0]) {
      remoteStream.value = event.streams[0]
    } else {
      // 部分浏览器不提供 event.streams：必须累加音轨和视轨，不能每条轨道覆盖整个流。
      const current = remoteStream.value
      const tracks = current
        ? current.getTracks().filter((track) => track.id !== event.track.id)
        : []
      remoteStream.value = new MediaStream([...tracks, event.track])
    }
  }
  pc.onconnectionstatechange = () => {
    if (pc !== peerConnection || !imState.call.active) return
    if (pc.connectionState === 'failed') {
      ElMessage.error('音视频连接失败：请确认双方网络互通；跨网段/防火墙环境需配置 TURN 服务')
      cleanupCall()
    } else if (pc.connectionState === 'disconnected') {
      // 局域网短暂抖动不要立即挂断，给 ICE 恢复留时间。
      window.setTimeout(() => {
        if (pc === peerConnection && pc.connectionState === 'disconnected' && imState.call.active) {
          ElMessage.warning('通话连接已断开')
          cleanupCall()
        }
      }, 6000)
    }
  }
  return pc
}

async function flushPendingIce() {
  if (!peerConnection) return
  while (pendingIce.length) {
    const candidate = new RTCIceCandidate(pendingIce.shift())
    try {
      await peerConnection.addIceCandidate(candidate)
    } catch {
      /* 忽略过期 candidate */
    }
  }
}

function resetCallState() {
  imState.call.active = false
  imState.call.peer = null
  imState.call.peerId = null
  imState.call.callId = ''
  imState.call.status = 'idle'
  imState.call.startedAt = null
  imState.call.muted = false
  imState.call.cameraOn = true
  imState.call.minimized = false
  imState.call.type = 'audio'
  imState.incoming = null
  window.clearTimeout(callTimeout)
}

export async function startCall(peer, type = 'audio') {
  await ensureRtcConfig()
  const peerId = Number(peer?.id || peer)
  const target = imState.users.find((user) => user.id === peerId)
  if (!target) {
    ElMessage.warning('请选择联系人')
    return false
  }
  if (!target.online) {
    ElMessage.warning('对方当前不在线')
    return false
  }
  if (!imState.connected) {
    ElMessage.warning('即时通信尚未连接')
    return false
  }
  cleanupGroupCall()
  if (imState.whiteboard.open) closeWhiteboard()
  cleanupCall()
  imState.call.callId = `${meId.value}-${peerId}-${Date.now()}`
  imState.call.peer = target
  imState.call.peerId = peerId
  imState.call.type = type
  imState.call.status = 'calling'
  imState.call.active = true
  imState.call.muted = false
  imState.call.cameraOn = type === 'video'
  imState.call.minimized = false
  try {
    localStream.value = await getMedia(type)
    const callType = effectiveCallType(localStream.value, type)
    if (callType !== type) {
      imState.call.type = 'audio'
      imState.call.cameraOn = false
      ElMessage.warning(localStream.value.__videoError || '摄像头不可用，已切换为语音通话')
    }
    const pc = createPeerConnection(peerId)
    const offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    const sent = sendSocket({
      type: 'call-offer',
      to: peerId,
      call_id: imState.call.callId,
      call_type: callType,
      sdp: pc.localDescription,
    })
    if (!sent) throw new Error('通信连接已断开')
    playCallRingtone('outgoing')
    callTimeout = window.setTimeout(() => {
      if (imState.call.status === 'calling') {
        ElMessage.warning('对方暂未接听')
        endCall()
      }
    }, 45000)
    return true
  } catch (error) {
    ElMessage.error(error?.message || '无法发起通话，请检查麦克风/摄像头权限')
    cleanupCall()
    return false
  }
}

export async function acceptIncoming() {
  await ensureRtcConfig()
  const incoming = imState.incoming
  if (!incoming) return
  stopCallRingtone()
  const type = incoming.call_type === 'video' ? 'video' : 'audio'
  cleanupGroupCall()
  cleanupCall()
  imState.incoming = null
  imState.call.callId = incoming.call_id
  imState.call.peer = imState.users.find((user) => user.id === incoming.from?.id) || incoming.from
  imState.call.peerId = incoming.from?.id
  imState.call.type = type
  imState.call.status = 'active'
  imState.call.active = true
  imState.call.cameraOn = type === 'video'
  imState.call.startedAt = Date.now()
  try {
    localStream.value = await getMedia(type)
    if (effectiveCallType(localStream.value, type) !== type) {
      imState.call.type = 'audio'
      imState.call.cameraOn = false
      ElMessage.warning(localStream.value.__videoError || '摄像头不可用，已切换为语音通话')
    }
    const pc = createPeerConnection(imState.call.peerId)
    await pc.setRemoteDescription(new RTCSessionDescription(incoming.sdp))
    await flushPendingIce()
    const answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    sendSocket({
      type: 'call-answer',
      to: imState.call.peerId,
      call_id: imState.call.callId,
      call_type: imState.call.type,
      sdp: pc.localDescription,
    })
  } catch (error) {
    ElMessage.error(error?.message || '接听失败，请检查麦克风/摄像头权限')
    sendSocket({ type: 'call-hangup', to: imState.call.peerId, call_id: imState.call.callId })
    cleanupCall()
  }
}

export function rejectIncoming() {
  if (!imState.incoming) return
  stopCallRingtone()
  sendSocket({
    type: 'call-reject',
    to: imState.incoming.from?.id,
    call_id: imState.incoming.call_id,
    reason: 'rejected',
  })
  imState.incoming = null
}

export function endCall(notify = true) {
  if (notify && imState.call.callId && imState.call.peerId) {
    sendSocket({
      type: 'call-hangup',
      to: imState.call.peerId,
      call_id: imState.call.callId,
    })
  }
  cleanupCall()
}

export function cleanupCall() {
  stopCallRingtone()
  if (peerConnection) {
    try {
      peerConnection.close()
    } catch {
      /* ignore */
    }
    peerConnection = null
  }
  pendingIce = []
  if (localStream.value) {
    localStream.value.getTracks().forEach((track) => track.stop())
    localStream.value = null
  }
  remoteStream.value = null
  resetCallState()
}

export function toggleMute() {
  const tracks = localStream.value?.getAudioTracks?.() || []
  tracks.forEach((track) => { track.enabled = !track.enabled })
  imState.call.muted = tracks.length ? !tracks[0].enabled : !imState.call.muted
}

export function toggleCamera() {
  const tracks = localStream.value?.getVideoTracks?.() || []
  tracks.forEach((track) => { track.enabled = !track.enabled })
  imState.call.cameraOn = tracks.length ? tracks[0].enabled : !imState.call.cameraOn
}

export function minimizeCall(minimized = true) {
  imState.call.minimized = !!minimized
}
