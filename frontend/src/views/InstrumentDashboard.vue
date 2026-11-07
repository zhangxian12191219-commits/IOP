<template>
  <div class="instrument-page">
    <div class="instrument-share-bar">
      <div class="instrument-share-meta">
        <span v-if="sharedResource" class="shared-mode-tip">
          共享自 {{ sharedResource.owner?.real_name || sharedResource.owner?.username || '其他用户' }}
          <el-tag size="small" :type="sharedResource.can_edit ? 'success' : 'info'" effect="plain">
            {{ sharedResource.can_edit ? '可编辑' : '只读' }}
          </el-tag>
        </span>
        <span v-else class="instrument-share-hint">实时仪表盘 · 布局、球体指标与字号可配置</span>
      </div>
      <div class="instrument-share-actions">
        <el-button v-if="sharedResource && !sharedResource.can_edit" size="small" type="primary" plain @click="requestSharedEdit">
          <el-icon><Edit /></el-icon>申请编辑
        </el-button>
        <el-button v-if="!sharedResource || sharedResource.is_owner" size="small" @click="openShare">
          <el-icon><Share /></el-icon>分享仪表盘
        </el-button>
        <el-button size="small" @click="sharedWithMeVisible = true">
          <el-icon><FolderOpened /></el-icon>共享给我
        </el-button>
      </div>
    </div>
    <HexDashboard
      v-if="ready"
      :shared-config="sharedConfig"
      :shared-read-only="sharedReadOnly"
      @shared-change="onHexChange"
    />
    <div v-else class="instrument-loading" v-loading="true"></div>

    <ResourceShareDialog
      v-model="shareVisible"
      resource-type="dashboard"
      resource-key="instrument"
      title="实时仪表盘"
      :config="shareSnapshot"
    />
    <SharedWithMeDialog v-model="sharedWithMeVisible" resource-type="dashboard" />
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Edit, FolderOpened, Share } from '@element-plus/icons-vue'
import HexDashboard from '@/components/HexDashboard.vue'
import ResourceShareDialog from '@/components/ResourceShareDialog.vue'
import SharedWithMeDialog from '@/components/SharedWithMeDialog.vue'
import { sharingApi } from '@/api'

const HEX_CONFIG_KEY = 'nms_hex_dashboard_v1'
const HEX_LAYOUT_KEY = 'nms_hex_dashboard_positions_v1'
const HEX_MODE_KEY = 'nms_hex_dashboard_mode_v1'
const HEX_FONT_KEY = 'nms_hex_font_scale'

const route = useRoute()
const ready = ref(false)
const sharedResource = ref(null)
const sharedConfig = ref(null)
const shareVisible = ref(false)
const sharedWithMeVisible = ref(false)
const shareSnapshot = ref({})
const sharedReadOnly = computed(() => Boolean(sharedResource.value && !sharedResource.value.can_edit))
let saveTimer = null

function parseJson(key, fallback) {
  try {
    const raw = localStorage.getItem(key)
    return raw ? JSON.parse(raw) : fallback
  } catch {
    return fallback
  }
}

function openShare() {
  shareSnapshot.value = {
    config: parseJson(HEX_CONFIG_KEY, []),
    layout: parseJson(HEX_LAYOUT_KEY, {}),
    mode: localStorage.getItem(HEX_MODE_KEY) === 'free' ? 'free' : 'device',
    fontScale: Number(localStorage.getItem(HEX_FONT_KEY)) || 1,
  }
  shareVisible.value = true
}

async function loadShared() {
  const resourceId = route.query.shared
  if (!resourceId) {
    ready.value = true
    return
  }
  try {
    const res = await sharingApi.resource(resourceId)
    sharedResource.value = res.data
    sharedConfig.value = res.data?.config || null
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '共享仪表盘加载失败')
  } finally {
    ready.value = true
  }
}

async function requestSharedEdit() {
  if (!sharedResource.value) return
  try {
    await sharingApi.requestEdit(sharedResource.value.id)
    sharedResource.value = { ...sharedResource.value, pending_request: { status: 'pending' } }
    ElMessage.success('编辑申请已提交，等待所有者审批')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '提交编辑申请失败')
  }
}

function onHexChange(payload) {
  if (!sharedResource.value?.can_edit || !sharedResource.value?.id) return
  window.clearTimeout(saveTimer)
  saveTimer = window.setTimeout(async () => {
    try {
      await sharingApi.updateResource(sharedResource.value.id, { config: payload })
    } catch {
      /* 自动保存失败时保持当前页面，不打断操作 */
    }
  }, 450)
}

onMounted(loadShared)
onBeforeUnmount(() => window.clearTimeout(saveTimer))
</script>

<style scoped>
.instrument-page { height: calc(100vh - 120px); height: calc(100dvh - 120px); min-height: 0; display: flex; flex-direction: column; padding: 4px 0 8px; overflow: hidden; }
.instrument-page :deep(.hex-dashboard) { flex: 1; min-height: 0; }
.instrument-share-bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex: 0 0 38px; padding: 0 2px 4px; }
.instrument-share-meta { display: flex; align-items: center; gap: 8px; min-width: 0; }
.instrument-share-hint { color: #7d8fa3; font-size: 12px; }
.shared-mode-tip { display: inline-flex; align-items: center; gap: 6px; color: #64748b; font-size: 12px; }
.instrument-share-actions { display: flex; align-items: center; gap: 8px; flex: 0 0 auto; }
.instrument-loading { flex: 1; min-height: 240px; }
</style>
