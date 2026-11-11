<template>
  <el-dialog
    :model-value="modelValue"
    :title="dialogTitle"
    width="760px"
    class="resource-share-dialog"
    :close-on-click-modal="false"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div v-loading="loading" class="share-dialog-body">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="共享给其他用户后默认只读；对方可在共享入口提交编辑申请，你同意后才会获得编辑权限。"
      />

      <div v-if="resource" class="share-link-row">
        <span class="share-section-label">共享链接</span>
        <el-input :model-value="shareUrl" readonly size="small" />
        <el-button size="small" @click="copyShareUrl">复制</el-button>
        <el-button size="small" :loading="syncing" @click="syncConfig">更新共享内容</el-button>
      </div>

      <div class="share-section">
        <div class="share-section-title">
          <span>共享给用户</span>
          <small>可多选；已共享成员不会被自动移除，除非点击“保存成员”</small>
        </div>
        <div class="share-member-editor">
          <el-select
            v-model="selectedUserIds"
            multiple
            filterable
            collapse-tags
            collapse-tags-tooltip
            placeholder="选择需要共享的用户"
            style="flex: 1"
          >
            <el-option
              v-for="user in users"
              :key="user.id"
              :label="`${user.real_name || user.username}（${user.username}）`"
              :value="user.id"
            />
          </el-select>
          <el-button type="primary" size="small" :loading="savingMembers" @click="saveMembers">保存成员</el-button>
        </div>
      </div>

      <div v-if="resource && resource.members?.length" class="share-section">
        <div class="share-section-title"><span>已共享成员</span><small>{{ resource.members.length }} 人</small></div>
        <div class="share-member-list">
          <div v-for="member in resource.members" :key="member.user.id" class="share-member-row">
            <div>
              <b>{{ member.user.real_name || member.user.username }}</b>
              <span>{{ member.user.username }}</span>
            </div>
            <el-tag size="small" :type="member.can_edit ? 'success' : 'info'" effect="plain">
              {{ member.can_edit ? '可编辑' : '只读' }}
            </el-tag>
            <el-button link type="danger" size="small" @click="removeMember(member.user.id)">移除</el-button>
          </div>
        </div>
      </div>

      <div class="share-section">
        <div class="share-section-title">
          <span>编辑申请</span>
          <small>{{ pendingRequests.length }} 条待处理</small>
        </div>
        <div v-if="pendingRequests.length" class="share-request-list">
          <div v-for="item in pendingRequests" :key="item.id" class="share-request-row">
            <div class="share-request-main">
              <b>{{ item.user.real_name || item.user.username }}</b>
              <span>{{ item.message || '申请编辑该共享资源' }}</span>
            </div>
            <span class="share-request-time">{{ formatTime(item.created_at) }}</span>
            <el-button size="small" type="success" plain @click="decideRequest(item.id, true)">同意</el-button>
            <el-button size="small" type="danger" plain @click="decideRequest(item.id, false)">拒绝</el-button>
          </div>
        </div>
        <el-empty v-else description="暂无待审批的编辑申请" :image-size="54" />
      </div>
    </div>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { sharingApi } from '@/api'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  resourceType: { type: String, required: true },
  resourceKey: { type: String, required: true },
  title: { type: String, default: '' },
  config: { type: [Object, Array], default: () => ({}) },
})
const emit = defineEmits(['update:modelValue'])

const loading = ref(false)
const syncing = ref(false)
const savingMembers = ref(false)
const resource = ref(null)
const users = ref([])
const selectedUserIds = ref([])
const shareUrl = computed(() => {
  if (!resource.value) return ''
  const origin = window.location.origin
  if (props.resourceType === 'dashboard') return `${origin}/${props.resourceKey === 'instrument' ? 'instrument' : 'dashboard'}?shared=${resource.value.id}`
  if (props.resourceType === 'topology') return `${origin}/topology?shared=${resource.value.id}`
  return `${origin}/bigscreen/view/${encodeURIComponent(props.resourceKey)}?shared=${resource.value.id}`
})
const pendingRequests = computed(() => (resource.value?.requests || []).filter((item) => item.status === 'pending'))
const dialogTitle = computed(() => {
  const labels = { dashboard: '仪表盘', topology: '拓扑图', bigscreen: '大屏' }
  return `共享${labels[props.resourceType] || '资源'}`
})

function configPayload() {
  try {
    return JSON.parse(JSON.stringify(props.config || {}))
  } catch {
    return {}
  }
}

function formatTime(value) {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('zh-CN', { hour12: false })
}

async function loadResource() {
  const owned = await sharingApi.owned(props.resourceType)
  let item = (owned.data?.items || []).find((row) => row.resource_key === props.resourceKey)
  if (item) {
    const res = await sharingApi.updateResource(item.id, {
      title: props.title || item.title,
      config: configPayload(),
    })
    item = res.data?.resource || item
  } else {
    const res = await sharingApi.saveResource({
      resource_type: props.resourceType,
      resource_key: props.resourceKey,
      title: props.title,
      config: configPayload(),
    })
    item = res.data?.resource
  }
  resource.value = item
  selectedUserIds.value = (item?.members || []).map((member) => member.user.id)
}

async function load() {
  loading.value = true
  try {
    const userRes = await sharingApi.users()
    users.value = userRes.data?.items || []
    await loadResource()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '共享信息加载失败')
  } finally {
    loading.value = false
  }
}

async function syncConfig() {
  if (!resource.value) return
  syncing.value = true
  try {
    const res = await sharingApi.updateResource(resource.value.id, {
      title: props.title || resource.value.title,
      config: configPayload(),
    })
    resource.value = res.data?.resource || resource.value
    ElMessage.success('共享内容已更新')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '更新共享内容失败')
  } finally {
    syncing.value = false
  }
}

async function saveMembers() {
  if (!resource.value) return
  savingMembers.value = true
  try {
    const res = await sharingApi.saveMembers(resource.value.id, selectedUserIds.value)
    resource.value = res.data?.resource || resource.value
    selectedUserIds.value = (resource.value.members || []).map((member) => member.user.id)
    ElMessage.success('共享成员已更新')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '保存共享成员失败')
  } finally {
    savingMembers.value = false
  }
}

async function removeMember(userId) {
  if (!resource.value) return
  try {
    await sharingApi.removeMember(resource.value.id, userId)
    await loadResource()
    ElMessage.success('成员已移除')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '移除成员失败')
  }
}

async function decideRequest(requestId, approve) {
  try {
    if (approve) await sharingApi.approveRequest(requestId)
    else await sharingApi.rejectRequest(requestId)
    await loadResource()
    ElMessage.success(approve ? '已同意编辑申请' : '已拒绝编辑申请')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '审批失败')
  }
}

async function copyShareUrl() {
  try {
    await navigator.clipboard.writeText(shareUrl.value)
    ElMessage.success('共享链接已复制')
  } catch {
    ElMessage.warning('浏览器不允许自动复制，请手动选择链接')
  }
}

watch(() => props.modelValue, (visible) => {
  if (visible) load()
}, { immediate: true })
</script>

<style scoped>
.share-dialog-body { display: flex; flex-direction: column; gap: 16px; max-height: 68vh; overflow-y: auto; padding-right: 4px; }
.share-link-row { display: flex; align-items: center; gap: 8px; }
.share-link-row .el-input { flex: 1; }
.share-section-label { color: #64748b; font-size: 12px; white-space: nowrap; }
.share-section { padding: 13px 14px; border: 1px solid #e2e8f0; border-radius: 9px; background: #fafcff; }
.share-section-title { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; margin-bottom: 10px; }
.share-section-title span { color: #0f172a; font-size: 13px; font-weight: 600; }
.share-section-title small { color: #94a3b8; font-size: 11px; }
.share-member-editor { display: flex; gap: 8px; align-items: center; }
.share-member-list, .share-request-list { display: flex; flex-direction: column; gap: 6px; }
.share-member-row, .share-request-row { display: flex; align-items: center; gap: 10px; padding: 7px 9px; border-radius: 6px; background: #fff; border: 1px solid #eef2f7; }
.share-member-row > div, .share-request-main { display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 0; }
.share-member-row b, .share-request-main b { color: #1e293b; font-size: 12px; font-weight: 500; }
.share-member-row span, .share-request-main span { color: #64748b; font-size: 11px; }
.share-request-time { color: #94a3b8; font-size: 10px; white-space: nowrap; }
:deep(.el-empty) { padding: 6px 0; }
</style>
