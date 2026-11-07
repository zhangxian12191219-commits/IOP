<template>
  <div class="im-page" :class="`im-theme-${imTheme}`" :style="pageStyle">
    <div class="im-head">
      <div>
        <div class="im-title"><el-icon><ChatDotRound /></el-icon>即时通信</div>
        <div class="im-subtitle">在线用户实时消息 · 单聊 / 群聊 · 语音视频通话 · 群白板</div>
      </div>
      <div class="im-head-status">
        <div class="im-theme-picker">
          <span class="im-theme-label"><el-icon><Brush /></el-icon>界面风格</span>
          <el-select v-model="imTheme" size="small" class="im-theme-select" title="切换即时通信界面风格">
            <el-option v-for="item in themeOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-color-picker v-model="imAccent" size="small" title="自定义强调色" />
        </div>
        <span class="im-conn" :class="{ online: imState.connected }">
          <i></i>{{ imState.connected ? '通信已连接' : '通信连接中' }}
        </span>
        <el-switch
          :model-value="imMessageSoundEnabled"
          size="small"
          inline-prompt
          active-text="消息音"
          inactive-text="静音"
          title="即时通信新消息提示音"
          @change="toggleImMessageSound"
        />
        <el-button v-if="currentUser?.is_superuser" size="small" @click="$router.push('/cascade?tab=chat')">
          <el-icon><Connection /></el-icon>级联通信
        </el-button>
        <el-button size="small" @click="refreshAll">
          <el-icon><Refresh /></el-icon>刷新
        </el-button>
      </div>
    </div>

    <el-alert
      class="im-retention-alert"
      type="warning"
      :closable="false"
      show-icon
      :title="`重要提示：聊天记录（含群消息与群白板）仅保留 ${imState.retentionDays || 15} 天`"
      :description="`到期后文字消息、图片、文件与白板笔画会自动销毁，无法恢复。重要内容请及时保存到运维笔记。`"
    />

    <el-alert
      v-if="!mediaSecure"
      class="im-media-warning"
      type="warning"
      :closable="false"
      show-icon
      title="当前页面不是 HTTPS 环境，浏览器可能禁止麦克风和摄像头。请在 HTTPS 或 localhost 下使用语音/视频通话。"
    />

    <div class="im-shell">
      <aside class="im-contacts">
        <div class="im-contacts-head">
          <span><el-icon><User /></el-icon>{{ asideTab === 'groups' ? '群组' : '联系人' }}</span>
          <el-tag size="small" effect="plain">
            {{ asideTab === 'groups' ? `${imState.groups.length} 个群` : `${onlineUsers.length} 在线` }}
          </el-tag>
        </div>
        <div class="im-contact-tabs">
          <button type="button" class="im-contact-tab" :class="{ active: asideTab === 'contacts' }" @click="switchTab('contacts')">
            联系人
            <b v-if="directUnreadTotal">{{ directUnreadTotal > 99 ? '99+' : directUnreadTotal }}</b>
          </button>
          <button type="button" class="im-contact-tab" :class="{ active: asideTab === 'groups' }" @click="switchTab('groups')">
            群组
            <b v-if="groupUnreadTotal">{{ groupUnreadTotal > 99 ? '99+' : groupUnreadTotal }}</b>
          </button>
        </div>
        <el-input v-model="search" size="small" clearable placeholder="搜索姓名 / 账号 / 群组" class="im-search">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <div class="im-contact-list">
          <template v-if="asideTab === 'contacts'">
            <button
              v-for="user in filteredUsers"
              :key="user.id"
              type="button"
              class="im-contact"
              :class="{ active: user.id === imState.activePeerId }"
              @click="selectPeer(user)"
            >
              <span class="im-avatar" :class="{ busy: !user.online }">
                {{ (user.real_name || user.username || 'U').slice(0, 1).toUpperCase() }}
                <i class="im-presence" :class="{ online: user.online }"></i>
              </span>
              <span class="im-contact-main">
                <strong>{{ user.real_name || user.username }}</strong>
                <small>{{ user.online ? '在线' : '离线' }}<template v-if="user.is_superuser"> · 管理员</template></small>
              </span>
              <span v-if="unreadFor(user)" class="im-unread">{{ unreadFor(user) > 99 ? '99+' : unreadFor(user) }}</span>
            </button>
            <el-empty v-if="!filteredUsers.length" description="暂无其他用户" :image-size="60" />
          </template>
          <template v-else>
            <button type="button" class="im-group-create" @click="openCreateDialog">
              <el-icon><Plus /></el-icon>新建群组
            </button>
            <button
              v-for="group in filteredGroups"
              :key="group.id"
              type="button"
              class="im-contact im-group-contact"
              :class="{ active: group.id === imState.activeGroupId }"
              @click="selectGroup(group)"
            >
              <span class="im-avatar group-avatar">
                <el-icon><ChatLineSquare /></el-icon>
                <i class="im-presence" :class="{ online: groupOnlineCount(group) > 0 }"></i>
              </span>
              <span class="im-contact-main">
                <strong>{{ group.name }}</strong>
                <small>{{ group.member_count }} 人 · {{ groupOnlineCount(group) }} 在线</small>
                <small v-if="group.last_message" class="im-group-preview">
                  {{ group.last_message.sender_name }}：{{ group.last_message.content }}
                </small>
              </span>
              <span v-if="groupUnreadFor(group)" class="im-unread">{{ groupUnreadFor(group) > 99 ? '99+' : groupUnreadFor(group) }}</span>
            </button>
            <el-empty v-if="!filteredGroups.length" description="还没有群组，点击上方新建" :image-size="60" />
          </template>
        </div>
      </aside>

      <section class="im-chat">
        <!-- 群聊会话 -->
        <template v-if="activeGroup">
          <header class="im-chat-head">
            <div class="im-chat-user">
              <span class="im-avatar small group-avatar"><el-icon><ChatLineSquare /></el-icon></span>
              <div>
                <strong>{{ activeGroup.name }}</strong>
                <small>
                  {{ activeGroup.member_count }} 人 · {{ groupOnlineCount(activeGroup) }} 在线
                  · 群主 {{ ownerName(activeGroup) }}
                </small>
              </div>
            </div>
            <div class="im-call-actions">
              <el-button
                size="small"
                :disabled="groupOnlineCount(activeGroup) <= 1"
                :title="groupOnlineCount(activeGroup) <= 1 ? '当前没有其他在线成员' : '发起群语音'"
                @click="startGroupAudio"
              >
                <el-icon><PhoneFilled /></el-icon>群语音
              </el-button>
              <el-button
                size="small"
                type="primary"
                :disabled="groupOnlineCount(activeGroup) <= 1"
                :title="groupOnlineCount(activeGroup) <= 1 ? '当前没有其他在线成员' : '发起群视频'"
                @click="startGroupVideo"
              >
                <el-icon><VideoCameraFilled /></el-icon>群视频
              </el-button>
              <el-button size="small" @click="openWhiteboard(activeGroup.id)">
                <el-icon><EditPen /></el-icon>群白板
              </el-button>
              <el-button size="small" v-if="activeGroup.is_owner" @click="manageGroup(activeGroup)">
                <el-icon><Setting /></el-icon>管理
              </el-button>
              <el-button size="small" @click="handleLeaveGroup(activeGroup)">
                <el-icon><SwitchButton /></el-icon>退出
              </el-button>
            </div>
          </header>

          <div ref="messagesRef" class="im-messages">
            <div v-if="!imState.groupMessages.length" class="im-welcome">
              <el-icon :size="34"><ChatLineSquare /></el-icon>
              <strong>欢迎来到 {{ activeGroup.name }}</strong>
              <span>群消息实时送达；群聊记录与白板只保留 {{ imState.retentionDays || 15 }} 天。</span>
            </div>
            <div
              v-for="message in imState.groupMessages"
              :key="message.id"
              class="im-message"
              :class="{ mine: message.sender_id === meId }"
            >
              <div class="im-message-meta">
                <span>{{ message.sender_id === meId ? '我' : senderName(message) }}</span>
                <time>{{ formatTime(message.created_at) }}</time>
              </div>
              <div v-if="message.recalled" class="im-bubble im-recalled">
                {{ message.sender_id === meId ? '你撤回了一条消息' : `${senderName(message)} 撤回了一条消息` }}
              </div>
              <template v-else>
                <div v-if="message.attachment" class="im-attachment-bubble" :class="{ image: message.attachment.kind === 'image' }">
                  <a :href="attachmentUrl(message.attachment)" target="_blank" rel="noopener" :title="message.attachment.name">
                    <img
                      v-if="message.attachment.kind === 'image'"
                      :src="attachmentUrl(message.attachment)"
                      :alt="message.attachment.name"
                      loading="lazy"
                    />
                    <span v-else class="im-file-card">
                      <el-icon :size="22"><Document /></el-icon>
                      <span>
                        <strong>{{ message.attachment.name }}</strong>
                        <small>{{ formatFileSize(message.attachment.size) }}</small>
                      </span>
                    </span>
                  </a>
                </div>
                <div v-if="message.content && (!message.attachment || message.content !== message.attachment.name)" class="im-bubble">{{ message.content }}</div>
              </template>
              <div class="im-message-actions">
                <el-button v-if="canRecall(message)" link size="small" @click.stop="handleRecall(message)">撤回</el-button>
                <el-button v-if="message.sender_id === meId" link size="small" @click.stop="handleDelete(message)">删除</el-button>
              </div>
            </div>
            <div v-if="groupTypingText" class="im-typing">{{ groupTypingText }}</div>
          </div>

          <footer class="im-compose">
            <div class="im-compose-tools">
              <input ref="imageInput" type="file" accept="image/*" hidden @change="onFileSelected" />
              <input ref="fileInput" type="file" hidden @change="onFileSelected" />
              <el-button size="small" :disabled="uploading" @click="imageInput?.click()">
                <el-icon><Picture /></el-icon>图片
              </el-button>
              <el-button size="small" :disabled="uploading" @click="fileInput?.click()">
                <el-icon><Paperclip /></el-icon>文件
              </el-button>
              <span class="im-file-limit">单个文件 ≤ 500MB · 群消息仅保留 {{ imState.retentionDays || 15 }} 天</span>
              <span v-if="uploading" class="im-uploading">上传中 {{ uploadProgress }}%</span>
            </div>
            <div v-if="pendingAttachment" class="im-pending">
              <el-icon><Paperclip /></el-icon>
              <span>{{ pendingAttachment.name }}</span>
              <small>{{ formatFileSize(pendingAttachment.size) }}</small>
              <button type="button" @click="pendingAttachment = null"><el-icon><Close /></el-icon></button>
            </div>
            <el-input
              v-model="draft"
              type="textarea"
              :rows="2"
              resize="none"
              maxlength="4000"
              placeholder="发送到群组，Enter 发送，Shift + Enter 换行"
              @keydown.enter.exact.prevent="submit"
              @input="notifyTyping"
            />
            <div class="im-compose-foot">
              <span>{{ draft.length }} / 4000</span>
              <span v-if="imState.connected" class="im-connected-tip">● 实时通信</span>
              <span v-else class="im-offline-tip">通信未连接</span>
              <el-button type="primary" :disabled="uploading || (!draft.trim() && !pendingAttachment) || !imState.connected" @click="submit">
                <el-icon><Promotion /></el-icon>发送
              </el-button>
            </div>
          </footer>
        </template>

        <!-- 单聊会话 -->
        <template v-else-if="activePeer">
          <header class="im-chat-head">
            <div class="im-chat-user">
              <span class="im-avatar small">
                {{ (activePeer.real_name || activePeer.username || 'U').slice(0, 1).toUpperCase() }}
                <i class="im-presence" :class="{ online: activePeer.online }"></i>
              </span>
              <div>
                <strong>{{ activePeer.real_name || activePeer.username }}</strong>
                <small>{{ activePeer.online ? '在线' : '离线，消息会在上线后送达' }}</small>
              </div>
            </div>
            <div class="im-call-actions">
              <el-button size="small" :disabled="!activePeer.online" @click="call('audio')">
                <el-icon><PhoneFilled /></el-icon>语音通话
              </el-button>
              <el-button size="small" type="primary" :disabled="!activePeer.online" @click="call('video')">
                <el-icon><VideoCameraFilled /></el-icon>视频通话
              </el-button>
            </div>
          </header>

          <div ref="messagesRef" class="im-messages">
            <div v-if="!imState.messages.length" class="im-welcome">
              <el-icon :size="34"><ChatDotRound /></el-icon>
              <strong>开始和 {{ activePeer.real_name || activePeer.username }} 会话</strong>
              <span>消息会实时送达；对方离线时也会保留记录。</span>
            </div>
            <div
              v-for="message in imState.messages"
              :key="message.id"
              class="im-message"
              :class="{ mine: message.sender_id === meId }"
            >
              <div class="im-message-meta">
                <span>{{ message.sender_id === meId ? '我' : (activePeer.real_name || activePeer.username) }}</span>
                <time>{{ formatTime(message.created_at) }}</time>
              </div>
              <div v-if="message.recalled" class="im-bubble im-recalled">
                {{ message.sender_id === meId ? '你撤回了一条消息' : '对方撤回了一条消息' }}
              </div>
              <template v-else>
                <div v-if="message.attachment" class="im-attachment-bubble" :class="{ image: message.attachment.kind === 'image' }">
                  <a :href="attachmentUrl(message.attachment)" target="_blank" rel="noopener" :title="message.attachment.name">
                    <img
                      v-if="message.attachment.kind === 'image'"
                      :src="attachmentUrl(message.attachment)"
                      :alt="message.attachment.name"
                      loading="lazy"
                    />
                    <span v-else class="im-file-card">
                      <el-icon :size="22"><Document /></el-icon>
                      <span>
                        <strong>{{ message.attachment.name }}</strong>
                        <small>{{ formatFileSize(message.attachment.size) }}</small>
                      </span>
                    </span>
                  </a>
                </div>
                <div v-if="message.content && (!message.attachment || message.content !== message.attachment.name)" class="im-bubble">{{ message.content }}</div>
              </template>
              <div class="im-message-actions">
                <el-button
                  v-if="canRecall(message)"
                  link
                  size="small"
                  @click.stop="handleRecall(message)"
                >撤回</el-button>
                <el-button link size="small" @click.stop="handleDelete(message)">删除</el-button>
              </div>
            </div>
            <div v-if="imState.typing" class="im-typing">对方正在输入…</div>
          </div>

          <footer class="im-compose">
            <div class="im-compose-tools">
              <input ref="imageInput" type="file" accept="image/*" hidden @change="onFileSelected" />
              <input ref="fileInput" type="file" hidden @change="onFileSelected" />
              <el-button size="small" :disabled="uploading" @click="imageInput?.click()">
                <el-icon><Picture /></el-icon>图片
              </el-button>
              <el-button size="small" :disabled="uploading" @click="fileInput?.click()">
                <el-icon><Paperclip /></el-icon>文件
              </el-button>
              <span class="im-file-limit">单个文件 ≤ 500MB · 仅保留 {{ imState.retentionDays || 15 }} 天</span>
              <span v-if="uploading" class="im-uploading">上传中 {{ uploadProgress }}%</span>
            </div>
            <div v-if="pendingAttachment" class="im-pending">
              <el-icon><Paperclip /></el-icon>
              <span>{{ pendingAttachment.name }}</span>
              <small>{{ formatFileSize(pendingAttachment.size) }}</small>
              <button type="button" @click="pendingAttachment = null"><el-icon><Close /></el-icon></button>
            </div>
            <el-input
              v-model="draft"
              type="textarea"
              :rows="2"
              resize="none"
              maxlength="4000"
              placeholder="输入消息，Enter 发送，Shift + Enter 换行"
              @keydown.enter.exact.prevent="submit"
              @input="notifyTyping"
            />
            <div class="im-compose-foot">
              <span>{{ draft.length }} / 4000</span>
              <span v-if="imState.connected" class="im-connected-tip">● 实时通信</span>
              <span v-else class="im-offline-tip">通信未连接</span>
              <el-button type="primary" :disabled="uploading || (!draft.trim() && !pendingAttachment) || !imState.connected" @click="submit">
                <el-icon><Promotion /></el-icon>发送
              </el-button>
            </div>
          </footer>
        </template>

        <el-empty v-else description="选择左侧联系人或群组开始聊天" :image-size="90" />
      </section>
    </div>

    <!-- 新建群组 -->
    <el-dialog v-model="createDialogVisible" title="新建群组" width="540px" append-to-body>
      <el-form label-position="top">
        <el-form-item label="群名称" required>
          <el-input v-model="groupName" maxlength="60" show-word-limit placeholder="例如：网络运维值班群" />
        </el-form-item>
        <el-form-item :label="`选择成员（已选 ${selectedMemberIds.length} 人，最多 ${MAX_GROUP_MEMBERS - 1} 人）`">
          <el-input v-model="memberSearch" size="small" clearable placeholder="搜索姓名 / 账号" class="im-member-search">
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
          <div class="im-member-picker">
            <label v-for="user in candidateMembers" :key="user.id" class="im-member-item">
              <el-checkbox
                :model-value="selectedMemberIds.includes(user.id)"
                :disabled="!selectedMemberIds.includes(user.id) && selectedMemberIds.length >= MAX_GROUP_MEMBERS - 1"
                @change="toggleMember(user.id)"
              />
              <span class="im-avatar tiny" :class="{ busy: !user.online }">
                {{ (user.real_name || user.username || 'U').slice(0, 1).toUpperCase() }}
                <i class="im-presence" :class="{ online: user.online }"></i>
              </span>
              <span class="im-member-text">
                <strong>{{ user.real_name || user.username }}</strong>
                <small>{{ user.username }} · {{ user.online ? '在线' : '离线' }}</small>
              </span>
            </label>
            <el-empty v-if="!candidateMembers.length" description="暂无可添加的成员" :image-size="54" />
          </div>
        </el-form-item>
        <p class="im-dialog-hint">创建者自动成为群主；群成员上限 {{ MAX_GROUP_MEMBERS }} 人，群消息与白板保留 15 天。</p>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creatingGroup" :disabled="!groupName.trim()" @click="createGroupAction">
          创建群组
        </el-button>
      </template>
    </el-dialog>

    <!-- 群成员管理 -->
    <el-dialog v-model="manageDialogVisible" :title="`群成员管理 · ${manageGroupRef?.name || ''}`" width="540px" append-to-body>
      <div class="im-member-picker">
        <div v-for="member in manageGroupRef?.members || []" :key="member.id" class="im-member-item">
          <span class="im-avatar tiny" :class="{ busy: !isOnline(member.id) }">
            {{ (member.real_name || member.username || 'U').slice(0, 1).toUpperCase() }}
            <i class="im-presence" :class="{ online: isOnline(member.id) }"></i>
          </span>
          <span class="im-member-text">
            <strong>{{ member.real_name || member.username }}</strong>
            <small>{{ member.username }} · {{ isOnline(member.id) ? '在线' : '离线' }}</small>
          </span>
          <el-tag v-if="member.role === 'owner'" size="small" effect="plain">群主</el-tag>
          <el-button
            v-else
            link
            type="danger"
            size="small"
            @click="removeMember(member)"
          >移除</el-button>
        </div>
      </div>
      <el-divider>添加成员</el-divider>
      <div class="im-member-picker">
        <label v-for="user in addableMembers" :key="user.id" class="im-member-item">
          <el-checkbox
            :model-value="manageSelected.includes(user.id)"
            :disabled="!manageSelected.includes(user.id) && (manageGroupRef?.member_count || 0) + manageSelected.length >= MAX_GROUP_MEMBERS"
            @change="toggleManageMember(user.id)"
          />
          <span class="im-avatar tiny" :class="{ busy: !user.online }">
            {{ (user.real_name || user.username || 'U').slice(0, 1).toUpperCase() }}
            <i class="im-presence" :class="{ online: user.online }"></i>
          </span>
          <span class="im-member-text">
            <strong>{{ user.real_name || user.username }}</strong>
            <small>{{ user.username }} · {{ user.online ? '在线' : '离线' }}</small>
          </span>
        </label>
        <el-empty v-if="!addableMembers.length" description="没有可添加的成员" :image-size="54" />
      </div>
      <template #footer>
        <el-button @click="manageDialogVisible = false">关闭</el-button>
        <el-button type="primary" :disabled="!manageSelected.length" @click="submitAddMembers">
          添加所选成员
        </el-button>
      </template>
    </el-dialog>

    <ImWhiteboard />
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { imApi } from '@/api'
import { currentUser } from '@/store/auth'
import ImWhiteboard from '@/components/ImWhiteboard.vue'
import {
  acceptIncoming, activeGroup, activePeer, addGroupMembers, connectIM, createGroup,
  deleteGroupMessage, deleteMessage as deleteChatMessage, imMessageSoundEnabled, imState,
  leaveGroup, onlineUsers, openConversation, openGroupConversation, openWhiteboard,
  recallGroupMessage, recallMessage as recallChatMessage, removeGroupMember,
  sendGroupMessage, sendGroupTyping, sendMessage, sendTyping, startCall, startGroupCall,
  toggleImMessageSound,
} from '@/store/im'

const route = useRoute()
const IM_THEME_KEY = 'nms_im_theme_v1'
const IM_ACCENT_KEY = 'nms_im_accent_v1'
const MAX_GROUP_MEMBERS = 30
const themeOptions = [
  { value: 'fresh', label: '清爽' },
  { value: 'tech', label: '科技风' },
  { value: 'warm', label: '暖阳' },
]
const themeAccent = { fresh: '#2f7fca', tech: '#38bdf8', warm: '#c47a52' }
const savedTheme = localStorage.getItem(IM_THEME_KEY)
const imTheme = ref(themeOptions.some((item) => item.value === savedTheme) ? savedTheme : 'fresh')
const imAccent = ref(localStorage.getItem(IM_ACCENT_KEY) || themeAccent[imTheme.value])
const pageStyle = computed(() => ({
  '--im-accent': imAccent.value,
  '--el-color-primary': imAccent.value,
}))
watch(imTheme, (value) => {
  imAccent.value = themeAccent[value] || themeAccent.fresh
  localStorage.setItem(IM_THEME_KEY, value)
  localStorage.setItem(IM_ACCENT_KEY, imAccent.value)
})
watch(imAccent, (value) => {
  if (value) localStorage.setItem(IM_ACCENT_KEY, value)
})

const search = ref('')
const asideTab = ref('contacts')
const draft = ref('')
const messagesRef = ref(null)
const imageInput = ref(null)
const fileInput = ref(null)
const pendingAttachment = ref(null)
const uploading = ref(false)
const uploadProgress = ref(0)
const MAX_FILE_BYTES = 500 * 1024 * 1024
const manualPeer = ref(false)
let autoSelecting = false
let typingTimer = null

// ---- 建群 / 成员管理 ----
const createDialogVisible = ref(false)
const groupName = ref('')
const memberSearch = ref('')
const selectedMemberIds = ref([])
const creatingGroup = ref(false)
const manageDialogVisible = ref(false)
const manageGroupRef = ref(null)
const manageSelected = ref([])

const mediaSecure = computed(() => window.isSecureContext
  || ['localhost', '127.0.0.1', '::1'].includes(window.location.hostname))
const meId = computed(() => Number(currentUser.value?.id || 0))
const onlineIdSet = computed(() => new Set([
  meId.value,
  ...onlineUsers.value.map((user) => Number(user.id)),
]))
const directUnreadTotal = computed(
  () => Object.values(imState.unread || {}).reduce((sum, value) => sum + Number(value || 0), 0),
)
const groupUnreadTotal = computed(
  () => Object.values(imState.groupUnread || {}).reduce((sum, value) => sum + Number(value || 0), 0),
)
const filteredUsers = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  const users = [...imState.users].sort((a, b) => Number(b.online) - Number(a.online)
    || String(a.real_name || a.username).localeCompare(String(b.real_name || b.username)))
  if (!keyword) return users
  return users.filter((user) => `${user.real_name || ''} ${user.username || ''}`.toLowerCase().includes(keyword))
})
const filteredGroups = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  if (!keyword) return imState.groups
  return imState.groups.filter((group) => {
    const memberText = (group.members || []).map((member) => member.real_name || member.username || '').join(' ')
    return `${group.name || ''} ${memberText}`.toLowerCase().includes(keyword)
  })
})
const candidateMembers = computed(() => {
  const keyword = memberSearch.value.trim().toLowerCase()
  return imState.users
    .filter((user) => Number(user.id) !== meId.value)
    .filter((user) => !keyword
      || `${user.real_name || ''} ${user.username || ''}`.toLowerCase().includes(keyword))
})
const addableMembers = computed(() => {
  const existing = new Set((manageGroupRef.value?.members || []).map((member) => Number(member.id)))
  return candidateMembers.value.filter((user) => !existing.has(Number(user.id)))
})
const groupTypingText = computed(() => {
  const typer = imState.groupTyping[imState.activeGroupId]
  return typer ? `${typer.name} 正在输入…` : ''
})

function formatTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesRef.value) messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  })
}

function switchTab(tab) {
  asideTab.value = tab
  if (tab === 'contacts' && !activePeer.value) autoSelectPeer()
}

async function selectPeer(user) {
  if (!user) return
  asideTab.value = 'contacts'
  manualPeer.value = true
  await openPeer(user)
}

async function openPeer(user) {
  if (!user) return
  await openConversation(user.id)
  imState.unread[user.id] = 0
  scrollToBottom()
}

function unreadFor(user) {
  return Number(imState.unread[user.id] || user.unread || 0)
}

function groupUnreadFor(group) {
  return Number(imState.groupUnread[group.id] || group.unread || 0)
}

function isOnline(userId) {
  return onlineIdSet.value.has(Number(userId))
}

function groupOnlineCount(group) {
  return (group?.members || []).filter((member) => isOnline(member.id)).length
}

function ownerName(group) {
  const owner = (group?.members || []).find((member) => Number(member.id) === Number(group.owner_id))
  return owner?.real_name || owner?.username || '—'
}

function senderName(message) {
  if (message?.sender?.real_name || message?.sender?.username) {
    return message.sender.real_name || message.sender.username
  }
  const member = (activeGroup.value?.members || []).find(
    (item) => Number(item.id) === Number(message?.sender_id),
  )
  return member?.real_name || member?.username || '群成员'
}

function formatFileSize(size) {
  const value = Number(size || 0)
  if (value >= 1024 * 1024 * 1024) return `${(value / 1024 / 1024 / 1024).toFixed(2)} GB`
  if (value >= 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${value} B`
}

function attachmentUrl(attachment) {
  return imApi.attachmentUrl(attachment.id)
}

async function onFileSelected(event) {
  const file = event?.target?.files?.[0]
  if (event?.target) event.target.value = ''
  if (!file) return
  if (file.size > MAX_FILE_BYTES) {
    ElMessage.error('单个文件不能超过 500MB')
    return
  }
  if (file.size <= 0) {
    ElMessage.error('不能上传空文件')
    return
  }
  uploading.value = true
  uploadProgress.value = 0
  try {
    const res = await imApi.uploadAttachment(file, (progress) => {
      uploadProgress.value = progress
    })
    pendingAttachment.value = res.data?.attachment || null
    if (pendingAttachment.value) ElMessage.success('附件已上传，点击发送即可')
  } catch (error) {
    const detail = error?.response?.status === 413 ? '单个文件不能超过 500MB' : (error.message || '上传失败')
    ElMessage.error(detail)
  } finally {
    uploading.value = false
    uploadProgress.value = 0
  }
}

async function submit() {
  if (uploading.value) {
    ElMessage.warning('附件上传中，请稍候')
    return
  }
  const text = draft.value.trim()
  if (!text && !pendingAttachment.value) return
  const attachmentId = pendingAttachment.value?.id || null
  const sent = activeGroup.value
    ? sendGroupMessage(text, attachmentId)
    : sendMessage(text, attachmentId)
  if (sent) {
    draft.value = ''
    pendingAttachment.value = null
    if (activeGroup.value) sendGroupTyping(false)
    else sendTyping(false)
    scrollToBottom()
  }
}

function canRecall(message) {
  return Number(message.sender_id) === meId.value
    && !message.recalled
    && message.can_recall === true
}

async function handleRecall(message) {
  try {
    await ElMessageBox.confirm(
      message.group_id
        ? '撤回后群内所有成员都会看到撤回提示，且消息内容不可恢复。是否继续？'
        : '撤回后双方都会看到撤回提示，且消息内容不可恢复。是否继续？',
      '撤回消息',
      { type: 'warning', confirmButtonText: '撤回', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await (message.group_id ? recallGroupMessage(message.id) : recallChatMessage(message.id))
    ElMessage.success('消息已撤回')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '撤回失败')
  }
}

async function handleDelete(message) {
  try {
    await ElMessageBox.confirm(
      message.group_id
        ? '删除后仅当前账号不可见，其他群成员仍可看到这条消息。是否继续？'
        : '删除后仅当前账号不可见，对方仍可看到这条消息。是否继续？',
      '删除消息',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await (message.group_id ? deleteGroupMessage(message.id) : deleteChatMessage(message.id))
    ElMessage.success('消息已删除')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '删除失败')
  }
}

function notifyTyping() {
  if (typingTimer) window.clearTimeout(typingTimer)
  if (activeGroup.value) {
    sendGroupTyping(true)
    typingTimer = window.setTimeout(() => sendGroupTyping(false), 1200)
    return
  }
  sendTyping(true)
  typingTimer = window.setTimeout(() => sendTyping(false), 1200)
}

async function call(type) {
  if (!activePeer.value) return
  await startCall(activePeer.value, type)
}

async function startGroupAudio() {
  if (!activeGroup.value) return
  await startGroupCall(activeGroup.value, 'audio')
}

async function startGroupVideo() {
  if (!activeGroup.value) return
  await startGroupCall(activeGroup.value, 'video')
}

async function refreshAll() {
  try {
    await connectIM()
    ElMessage.success('通信状态已刷新')
  } catch {
    ElMessage.warning('通信服务暂不可用')
  }
}

async function autoSelectPeer() {
  if (autoSelecting) return
  if (asideTab.value !== 'contacts' || imState.activeGroupId) return
  autoSelecting = true
  try {
    const queryPeer = Number(route.query.peer || 0)
    const queryTarget = imState.users.find((user) => user.id === queryPeer)
    if (queryTarget) {
      await openPeer(queryTarget)
      return
    }
    if (manualPeer.value && activePeer.value) return
    if (activePeer.value?.online) return
    const unreadTarget = imState.users.find((user) => Number(imState.unread[user.id] || user.unread) > 0)
    const target = unreadTarget || onlineUsers.value[0] || activePeer.value || imState.users[0]
    if (target) await openPeer(target)
  } finally {
    autoSelecting = false
  }
}

/* ==================== 群组操作 ==================== */

async function selectGroup(group) {
  if (!group) return
  asideTab.value = 'groups'
  manualPeer.value = true
  await openGroup(group)
}

async function openGroup(group) {
  if (!group) return
  await openGroupConversation(group.id)
  imState.groupUnread[group.id] = 0
  scrollToBottom()
}

function openCreateDialog() {
  groupName.value = ''
  memberSearch.value = ''
  selectedMemberIds.value = []
  createDialogVisible.value = true
}

function toggleMember(userId) {
  const id = Number(userId)
  const index = selectedMemberIds.value.indexOf(id)
  if (index >= 0) {
    selectedMemberIds.value.splice(index, 1)
    return
  }
  if (selectedMemberIds.value.length >= MAX_GROUP_MEMBERS - 1) {
    ElMessage.warning(`群成员上限 ${MAX_GROUP_MEMBERS} 人（含群主）`)
    return
  }
  selectedMemberIds.value.push(id)
}

async function createGroupAction() {
  const name = groupName.value.trim()
  if (!name) {
    ElMessage.warning('请输入群名称')
    return
  }
  creatingGroup.value = true
  try {
    const group = await createGroup(name, [...selectedMemberIds.value])
    createDialogVisible.value = false
    asideTab.value = 'groups'
    ElMessage.success('群组已创建')
    if (group) await openGroup(group)
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '创建群组失败')
  } finally {
    creatingGroup.value = false
  }
}

function manageGroup(group) {
  manageGroupRef.value = group
  manageSelected.value = []
  manageDialogVisible.value = true
}

function toggleManageMember(userId) {
  const id = Number(userId)
  const index = manageSelected.value.indexOf(id)
  if (index >= 0) {
    manageSelected.value.splice(index, 1)
    return
  }
  const total = Number(manageGroupRef.value?.member_count || 0) + manageSelected.value.length
  if (total >= MAX_GROUP_MEMBERS) {
    ElMessage.warning(`群成员上限 ${MAX_GROUP_MEMBERS} 人`)
    return
  }
  manageSelected.value.push(id)
}

async function submitAddMembers() {
  if (!manageGroupRef.value || !manageSelected.value.length) return
  try {
    const groupId = manageGroupRef.value.id
    await addGroupMembers(groupId, [...manageSelected.value])
    manageSelected.value = []
    manageGroupRef.value = imState.groups.find((item) => item.id === groupId) || manageGroupRef.value
    ElMessage.success('成员已添加')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '添加成员失败')
  }
}

async function removeMember(member) {
  if (!manageGroupRef.value) return
  try {
    await ElMessageBox.confirm(
      `确定将 ${member.real_name || member.username} 移出群组？`,
      '移除群成员',
      { type: 'warning', confirmButtonText: '移除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    const groupId = manageGroupRef.value.id
    await removeGroupMember(groupId, member.id)
    manageGroupRef.value = imState.groups.find((item) => item.id === groupId) || manageGroupRef.value
    ElMessage.success('成员已移除')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '移除成员失败')
  }
}

async function handleLeaveGroup(group) {
  try {
    await ElMessageBox.confirm(
      `确定退出群组「${group.name}」？退出后将不再接收该群消息。`,
      '退出群组',
      { type: 'warning', confirmButtonText: '退出', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    const result = await leaveGroup(group.id)
    if (result?.dissolved) ElMessage.info('你已退出，群组因无其他成员而解散')
    else ElMessage.success('已退出群组')
    asideTab.value = 'groups'
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '退出群组失败')
  }
}

watch([() => imState.messages.length, () => imState.groupMessages.length], scrollToBottom)
watch([() => imState.activePeerId, () => imState.activeGroupId], scrollToBottom)
watch(() => imState.users, () => {
  if (!imState.activePeerId && !imState.activeGroupId) autoSelectPeer()
}, { deep: true })
watch(
  () => imState.users.map((user) => `${user.id}:${user.online ? 1 : 0}`).join('|'),
  () => {
    if (!manualPeer.value) autoSelectPeer()
  },
)

onMounted(async () => {
  imState.chatOpen = true
  await connectIM()
  const queryGroup = Number(route.query.group || 0)
  const queryTarget = queryGroup ? imState.groups.find((group) => group.id === queryGroup) : null
  if (queryTarget) {
    asideTab.value = 'groups'
    await openGroup(queryTarget)
  } else if (route.query.peer) {
    await autoSelectPeer()
  } else if (imState.activeGroupId && activeGroup.value) {
    await openGroup(activeGroup.value)
  } else if (imState.activePeerId && activePeer.value) {
    // 从其他页面返回时恢复上次会话，并同步清除离开期间产生的未读
    await openPeer(activePeer.value)
  } else {
    await autoSelectPeer()
  }
  if (!sessionStorage.getItem('nms_im_retention_notified')) {
    sessionStorage.setItem('nms_im_retention_notified', '1')
    ElMessageBox.alert(
      `聊天记录（含群聊、图片、文件和群白板笔画）默认只保留 ${imState.retentionDays || 15} 天，到期后自动销毁且无法恢复。重要内容请及时保存到运维笔记或下载备份。`,
      '聊天记录保留提示',
      {
        type: 'warning',
        confirmButtonText: '我知道了',
        closeOnClickModal: false,
      },
    ).catch(() => {})
  }
})

onBeforeUnmount(() => {
  imState.chatOpen = false
  imState.typing = false
  if (typingTimer) window.clearTimeout(typingTimer)
})
</script>

<style scoped>
.im-page { padding: 22px; height: calc(100vh - 72px); box-sizing: border-box; display: flex; flex-direction: column; gap: 14px; }
.im-head { display: flex; justify-content: space-between; align-items: center; gap: 16px; }
.im-title { display: flex; align-items: center; gap: 8px; font-size: 22px; font-weight: 800; color: #1d3b50; letter-spacing: .02em; }
.im-title .el-icon { color: #167e9b; }
.im-subtitle { color: #7d9ab3; font-size: 13px; margin-top: 5px; }
.im-retention-alert { margin-bottom: 0; }
.im-media-warning { margin-bottom: 0; }
.im-head-status { display: flex; align-items: center; gap: 12px; }
.im-conn { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: #91a8bc; }
.im-conn i { width: 7px; height: 7px; border-radius: 50%; background: #f59e0b; }
.im-conn.online i { background: #22c55e; box-shadow: 0 0 8px #22c55e; }
.im-shell { min-height: 0; flex: 1; display: grid; grid-template-columns: 280px minmax(0, 1fr); border: 1px solid #163a53; border-radius: 14px; overflow: hidden; background: linear-gradient(160deg, rgba(8, 25, 40, .92), rgba(5, 16, 28, .96)); }
.im-contacts { border-right: 1px solid #163a53; display: flex; flex-direction: column; min-height: 0; }
.im-contacts-head { padding: 16px 16px 10px; display: flex; align-items: center; justify-content: space-between; color: #d9edff; font-weight: 700; }
.im-contacts-head span:first-child { display: inline-flex; align-items: center; gap: 7px; }
.im-search { margin: 0 12px 8px; }
.im-contact-list { overflow-y: auto; padding: 4px 8px 12px; }
.im-contact { width: 100%; border: 0; background: transparent; display: flex; align-items: center; gap: 10px; padding: 10px 8px; border-radius: 9px; text-align: left; color: #dbeafe; cursor: pointer; transition: background .15s; }
.im-contact:hover, .im-contact.active { background: rgba(56, 189, 248, .12); }
.im-avatar { position: relative; width: 38px; height: 38px; flex: 0 0 38px; display: grid; place-items: center; border-radius: 11px; background: linear-gradient(145deg, #1e749c, #19425f); border: 1px solid #2b9cc3; color: #e9fbff; font-weight: 800; }
.im-avatar.small { width: 34px; height: 34px; flex-basis: 34px; border-radius: 10px; }
.im-avatar.busy { opacity: .58; }
.im-presence { position: absolute; right: -2px; bottom: -2px; width: 9px; height: 9px; border-radius: 50%; background: #64748b; border: 2px solid #081b2a; }
.im-presence.online { background: #22c55e; box-shadow: 0 0 7px #22c55e; }
.im-contact-main { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 3px; }
.im-contact-main strong { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.im-contact-main small { color: #789ab2; font-size: 11px; }
.im-unread { min-width: 18px; height: 18px; padding: 0 5px; border-radius: 9px; background: #ef4444; color: #fff; font-size: 11px; display: grid; place-items: center; }
.im-chat { min-width: 0; min-height: 0; display: flex; flex-direction: column; }
.im-chat-head { padding: 12px 16px; border-bottom: 1px solid #163a53; display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.im-chat-user { display: flex; align-items: center; gap: 10px; min-width: 0; }
.im-chat-user > div { display: flex; flex-direction: column; gap: 3px; }
.im-chat-user strong { color: #e8f6ff; font-size: 14px; }
.im-chat-user small { color: #7d9ab3; font-size: 11px; }
.im-call-actions { display: flex; gap: 8px; }
.im-messages { flex: 1; min-height: 0; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 14px; }
.im-welcome { margin: auto; display: flex; flex-direction: column; align-items: center; gap: 8px; color: #7f9db4; text-align: center; }
.im-welcome strong { color: #d9edff; font-size: 15px; }
.im-welcome span { font-size: 12px; }
.im-message { max-width: 76%; align-self: flex-start; }
.im-message.mine { align-self: flex-end; }
.im-message-meta { display: flex; gap: 8px; align-items: center; color: #7e9cb4; font-size: 11px; margin-bottom: 4px; }
.im-message.mine .im-message-meta { justify-content: flex-end; }
.im-message-actions { display: flex; gap: 6px; margin-top: 3px; opacity: 0; pointer-events: none; transition: opacity .15s ease; }
.im-message.mine .im-message-actions { justify-content: flex-end; }
.im-message:hover .im-message-actions,
.im-message-actions:focus-within { opacity: 1; pointer-events: auto; }
.im-message-actions .el-button { height: auto; padding: 0 2px; color: #86a9bd; font-size: 11px; }
.im-message-actions .el-button:hover { color: #67e8f9; }
.im-recalled { background: transparent !important; border-style: dashed; color: #89a5b6; font-style: italic; }
.im-bubble { padding: 10px 13px; border-radius: 4px 12px 12px 12px; background: #102f46; border: 1px solid #1d4d68; color: #e1f2ff; line-height: 1.55; font-size: 13px; white-space: pre-wrap; overflow-wrap: anywhere; }
.im-message.mine .im-bubble { border-radius: 12px 4px 12px 12px; background: #0e5b72; border-color: #168a9d; }
.im-typing { align-self: flex-start; color: #67e8f9; font-size: 12px; }
.im-attachment-bubble { max-width: 320px; }
.im-attachment-bubble a { display: block; color: #dff8ff; text-decoration: none; }
.im-attachment-bubble.image img { display: block; max-width: 280px; max-height: 220px; border-radius: 9px; border: 1px solid #1f6279; object-fit: cover; }
.im-file-card { display: flex; align-items: center; gap: 9px; min-width: 190px; padding: 9px 11px; border-radius: 8px; border: 1px solid #1d5a72; background: #0c3146; }
.im-file-card > span { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.im-file-card strong { font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.im-file-card small { color: #81a8bb; font-size: 10px; }
@media (hover: none) {
  .im-message-actions { opacity: 1; pointer-events: auto; }
}
.im-compose-tools { display: flex; align-items: center; gap: 7px; margin-bottom: 7px; }
.im-file-limit { margin-left: auto; color: #78a1b4; font-size: 10px; }
.im-uploading { color: #67e8f9; font-size: 10px; }
.im-pending { display: flex; align-items: center; gap: 7px; margin-bottom: 6px; padding: 6px 9px; border-radius: 6px; background: #103247; border: 1px solid #1b566d; color: #c9edf8; font-size: 11px; }
.im-pending span { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.im-pending small { color: #7fa7b9; }
.im-pending button { border: 0; background: transparent; color: #8cb9ca; cursor: pointer; display: grid; place-items: center; }
.im-compose { border-top: 1px solid #163a53; padding: 12px 14px; }
.im-compose-foot { display: flex; align-items: center; justify-content: flex-end; gap: 12px; padding-top: 8px; color: #7d9ab3; font-size: 11px; }
.im-compose-foot > span:first-child { margin-right: auto; }
.im-connected-tip { color: #34d399; }
.im-offline-tip { color: #fbbf24; }
@media (max-width: 760px) {
  .im-page { padding: 10px; height: calc(100vh - 56px); }
  .im-shell { grid-template-columns: 96px minmax(0, 1fr); }
  .im-contacts-head { padding: 10px 8px; font-size: 12px; }
  .im-contacts-head .el-tag, .im-search, .im-contact-main small, .im-contact-main strong { display: none; }
  .im-contact { justify-content: center; padding: 8px 0; }
  .im-call-actions .el-button { padding: 6px; }
  .im-call-actions .el-button span { display: none; }
}

/* ================= 即时通信主题：清爽 / 科技 / 暖阳 ================= */
.im-theme-picker {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 7px;
  border: 1px solid #e1e9f2;
  border-radius: 8px;
  background: #fff;
}
.im-theme-label { display: inline-flex; align-items: center; gap: 4px; color: #8496a8; font-size: 10px; white-space: nowrap; }
.im-theme-select { width: 86px; }
.im-theme-select :deep(.el-select__wrapper) { min-height: 24px; padding: 0 4px; background: transparent; box-shadow: none; }
.im-theme-select :deep(.el-select__selected-item) { color: #40566a; font-size: 11px; }

.im-theme-fresh {
  --im-bg: #f3f6fa;
  --im-panel: #ffffff;
  --im-side: #f8fafc;
  --im-border: #e5ecf3;
  --im-text: #263849;
  --im-muted: #8497a9;
  --im-soft: #f1f4f7;
  --im-hover: #edf4fb;
  --im-input: #ffffff;
  --im-shadow: 0 10px 30px rgba(31, 64, 104, .06);
}
.im-theme-warm {
  --im-bg: #f8f3ec;
  --im-panel: #fffdf9;
  --im-side: #fcf7f0;
  --im-border: #eadfd2;
  --im-text: #3d322c;
  --im-muted: #998678;
  --im-soft: #f6eee5;
  --im-hover: #f8eee4;
  --im-input: #fffdf9;
  --im-shadow: 0 10px 30px rgba(94, 66, 45, .07);
}
.im-theme-fresh, .im-theme-warm { background: var(--im-bg); color: var(--im-text); }

.im-theme-fresh .im-title, .im-theme-warm .im-title { color: var(--im-text); }
.im-theme-fresh .im-title .el-icon, .im-theme-warm .im-title .el-icon { color: var(--im-accent); }
.im-theme-fresh .im-subtitle, .im-theme-warm .im-subtitle { color: var(--im-muted); }
.im-theme-fresh .im-conn, .im-theme-warm .im-conn { color: var(--im-muted); }
.im-theme-fresh .im-shell, .im-theme-warm .im-shell {
  border-color: var(--im-border);
  background: var(--im-panel);
  box-shadow: var(--im-shadow);
}
.im-theme-fresh .im-contacts, .im-theme-warm .im-contacts { border-color: var(--im-border); background: var(--im-side); }
.im-theme-fresh .im-contacts-head, .im-theme-warm .im-contacts-head { color: var(--im-text); }
.im-theme-fresh .im-contact, .im-theme-warm .im-contact { color: var(--im-text); }
.im-theme-fresh .im-contact:hover, .im-theme-warm .im-contact:hover { background: var(--im-hover); }
.im-theme-fresh .im-contact.active, .im-theme-warm .im-contact.active {
  background: color-mix(in srgb, var(--im-accent) 10%, var(--im-panel));
  color: var(--im-text);
}
.im-theme-fresh .im-contact-main small, .im-theme-warm .im-contact-main small { color: var(--im-muted); }
.im-theme-fresh .im-avatar, .im-theme-warm .im-avatar {
  background: color-mix(in srgb, var(--im-accent) 12%, var(--im-panel));
  border-color: color-mix(in srgb, var(--im-accent) 34%, var(--im-border));
  color: var(--im-accent);
}
.im-theme-fresh .im-presence, .im-theme-warm .im-presence { border-color: var(--im-panel); }
.im-theme-fresh .im-chat-head, .im-theme-warm .im-chat-head { border-color: var(--im-border); }
.im-theme-fresh .im-chat-user strong, .im-theme-warm .im-chat-user strong { color: var(--im-text); }
.im-theme-fresh .im-chat-user small, .im-theme-warm .im-chat-user small { color: var(--im-muted); }
.im-theme-fresh .im-messages, .im-theme-warm .im-messages { background: var(--im-panel); }
.im-theme-fresh .im-welcome, .im-theme-warm .im-welcome { color: var(--im-muted); }
.im-theme-fresh .im-welcome strong, .im-theme-warm .im-welcome strong { color: var(--im-text); }
.im-theme-fresh .im-message-meta, .im-theme-warm .im-message-meta { color: var(--im-muted); }
.im-theme-fresh .im-bubble, .im-theme-warm .im-bubble {
  background: var(--im-soft);
  border-color: var(--im-border);
  color: var(--im-text);
}
.im-theme-fresh .im-message.mine .im-bubble, .im-theme-warm .im-message.mine .im-bubble {
  background: var(--im-accent);
  border-color: var(--im-accent);
  color: #fff;
}
.im-theme-fresh .im-message-actions .el-button, .im-theme-warm .im-message-actions .el-button { color: var(--im-muted); }
.im-theme-fresh .im-message-actions .el-button:hover, .im-theme-warm .im-message-actions .el-button:hover { color: var(--im-accent); }
.im-theme-fresh .im-typing, .im-theme-warm .im-typing { color: var(--im-accent); }
.im-theme-fresh .im-file-card, .im-theme-warm .im-file-card { background: var(--im-soft); border-color: var(--im-border); color: var(--im-text); }
.im-theme-fresh .im-file-card small, .im-theme-warm .im-file-card small { color: var(--im-muted); }
.im-theme-fresh .im-attachment-bubble a, .im-theme-warm .im-attachment-bubble a { color: var(--im-text); }
.im-theme-fresh .im-attachment-bubble.image img, .im-theme-warm .im-attachment-bubble.image img { border-color: var(--im-border); }
.im-theme-fresh .im-compose, .im-theme-warm .im-compose { border-color: var(--im-border); background: var(--im-panel); }
.im-theme-fresh .im-compose-foot, .im-theme-warm .im-compose-foot { color: var(--im-muted); }
.im-theme-fresh .im-file-limit, .im-theme-warm .im-file-limit { color: var(--im-muted); }
.im-theme-fresh .im-pending, .im-theme-warm .im-pending { background: var(--im-soft); border-color: var(--im-border); color: var(--im-text); }
.im-theme-fresh .im-pending button, .im-theme-warm .im-pending button { color: var(--im-muted); }
.im-theme-fresh .im-recalled, .im-theme-warm .im-recalled { color: var(--im-muted); }
.im-theme-fresh .im-page, .im-theme-warm .im-page { background: var(--im-bg); }

.im-theme-fresh :deep(.el-input__wrapper),
.im-theme-fresh :deep(.el-textarea__inner),
.im-theme-warm :deep(.el-input__wrapper),
.im-theme-warm :deep(.el-textarea__inner) {
  background: var(--im-input);
  color: var(--im-text);
  box-shadow: 0 0 0 1px var(--im-border) inset;
}
.im-theme-fresh :deep(.el-input__inner),
.im-theme-fresh :deep(.el-textarea__inner),
.im-theme-warm :deep(.el-input__inner),
.im-theme-warm :deep(.el-textarea__inner) { color: var(--im-text); }
.im-theme-fresh :deep(.el-textarea__inner::placeholder),
.im-theme-fresh :deep(.el-input__inner::placeholder),
.im-theme-warm :deep(.el-textarea__inner::placeholder),
.im-theme-warm :deep(.el-input__inner::placeholder) { color: #9aaaba; }
.im-theme-fresh .im-theme-picker, .im-theme-warm .im-theme-picker { border-color: var(--im-border); background: var(--im-panel); }

.im-theme-tech .im-theme-picker { border-color: #1d4b64; background: #0d283a; }
.im-theme-tech { background: #081725; }
.im-theme-tech .im-title { color: #e2f8ff; }
.im-theme-tech .im-title .el-icon { color: #67e8f9; }
.im-theme-tech .im-subtitle { color: #7da5b7; }
.im-theme-tech .im-conn { color: #8fb7c9; }
.im-theme-tech .im-theme-label { color: #7fa6b8; }
.im-theme-tech .im-theme-select :deep(.el-select__selected-item) { color: #c9eaf5; }
.im-theme-tech .im-avatar { background: linear-gradient(145deg, var(--im-accent), #19425f); border-color: var(--im-accent); color: #e9fbff; }
.im-theme-tech .im-message.mine .im-bubble { background: color-mix(in srgb, var(--im-accent) 48%, #073a55); border-color: var(--im-accent); }
.im-theme-tech :deep(.el-input__wrapper),
.im-theme-tech :deep(.el-textarea__inner) { background: #0b2638; color: #dff8ff; box-shadow: 0 0 0 1px #1b4a61 inset; }
.im-theme-tech :deep(.el-input__inner),
.im-theme-tech :deep(.el-textarea__inner) { color: #dff8ff; }
.im-theme-tech :deep(.el-textarea__inner::placeholder),
.im-theme-tech :deep(.el-input__inner::placeholder) { color: #6f95a8; }

@media (max-width: 760px) {
  .im-theme-picker { padding: 2px 4px; }
  .im-theme-label { display: none; }
  .im-theme-select { width: 72px; }
  .im-head-status { gap: 6px; }
}
/* ================= 群组 / 群通话 / 白板入口 ================= */
.im-chat-head { flex-wrap: wrap; row-gap: 8px; }
.im-call-actions { flex-wrap: wrap; justify-content: flex-end; }
.im-contact-tabs { display: flex; gap: 6px; margin: 0 12px 8px; }
.im-contact-tab {
  flex: 1;
  border: 1px solid #163a53;
  background: rgba(16, 52, 71, .6);
  color: #9fc4d6;
  border-radius: 7px;
  padding: 5px 8px;
  font-size: 11px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
}
.im-contact-tab:hover { background: rgba(56, 189, 248, .14); }
.im-contact-tab.active { background: #0e5b72; border-color: #168a9d; color: #eaffff; }
.im-contact-tab b {
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 8px;
  background: #ef4444;
  color: #fff;
  font-size: 10px;
  font-weight: 600;
  display: grid;
  place-items: center;
}
.im-group-create {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin: 2px 0 8px;
  padding: 7px 10px;
  border-radius: 8px;
  border: 1px dashed #2b6d86;
  background: rgba(14, 91, 114, .16);
  color: #8fd8ea;
  font-size: 11px;
  cursor: pointer;
}
.im-group-create:hover { background: rgba(56, 189, 248, .16); }
.im-group-avatar { background: linear-gradient(145deg, #2a5f86, #173c58); border-color: #3b82f6; color: #dbeafe; }
.im-group-preview { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #8bb0c2; }
.im-member-search { margin-bottom: 8px; }
.im-member-picker {
  width: 100%;
  max-height: 260px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
  border: 1px solid #e3eaf2;
  border-radius: 8px;
  padding: 6px;
}
.im-member-item { display: flex; align-items: center; gap: 8px; padding: 5px 6px; border-radius: 6px; cursor: pointer; }
.im-member-item:hover { background: #f4f8fc; }
.im-member-text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
.im-member-text strong { font-size: 12px; color: #2b3d4f; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.im-member-text small { font-size: 10px; color: #8a9bab; }
.im-avatar.tiny { width: 28px; height: 28px; flex-basis: 28px; border-radius: 8px; font-size: 12px; }
.im-avatar.tiny .im-presence { width: 8px; height: 8px; }
.im-dialog-hint { margin: 4px 0 0; font-size: 11px; color: #8a9bab; }
.im-member-picker .el-empty { padding: 8px 0; }

.im-theme-fresh .im-contact-tab, .im-theme-warm .im-contact-tab {
  border-color: var(--im-border);
  background: var(--im-soft);
  color: var(--im-muted);
}
.im-theme-fresh .im-contact-tab.active, .im-theme-warm .im-contact-tab.active {
  background: color-mix(in srgb, var(--im-accent) 14%, var(--im-panel));
  border-color: color-mix(in srgb, var(--im-accent) 45%, var(--im-border));
  color: var(--im-accent);
}
.im-theme-fresh .im-group-create, .im-theme-warm .im-group-create {
  border-color: color-mix(in srgb, var(--im-accent) 40%, var(--im-border));
  background: color-mix(in srgb, var(--im-accent) 7%, var(--im-panel));
  color: var(--im-accent);
}
.im-theme-fresh .im-group-avatar, .im-theme-warm .im-group-avatar {
  background: color-mix(in srgb, var(--im-accent) 14%, var(--im-panel));
  border-color: color-mix(in srgb, var(--im-accent) 40%, var(--im-border));
  color: var(--im-accent);
}
.im-theme-fresh .im-group-preview, .im-theme-warm .im-group-preview { color: var(--im-muted); }
.im-theme-tech .im-group-avatar { background: linear-gradient(145deg, #1e5f9c, #173c58); border-color: #3b82f6; color: #dbeafe; }

@media (max-width: 760px) {
  .im-contact-tabs { margin: 0 6px 6px; }
  .im-contact-tab { font-size: 10px; padding: 4px 4px; }
  .im-group-preview { display: none; }
  .im-chat-head { padding: 9px 10px; }
  .im-call-actions .el-button { padding: 6px; }
}
</style>
