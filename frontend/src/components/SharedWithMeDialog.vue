<template>
  <el-dialog
    :model-value="modelValue"
    :title="`共享给我的${typeLabel}`"
    width="660px"
    @update:model-value="$emit('update:modelValue', $event)"
    @open="load"
  >
    <div v-loading="loading" class="shared-with-me">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="默认只能查看；如需编辑，请点击“申请编辑”，等待共享者审批。"
      />
      <div v-if="items.length" class="shared-list">
        <div v-for="item in items" :key="item.id" class="shared-item">
          <div class="shared-item-main">
            <b>{{ item.title || '未命名资源' }}</b>
            <span>来自 {{ item.owner?.real_name || item.owner?.username }} · 更新于 {{ formatTime(item.updated_at) }}</span>
          </div>
          <el-tag size="small" :type="item.can_edit ? 'success' : 'info'" effect="plain">
            {{ item.can_edit ? '可编辑' : '只读' }}
          </el-tag>
          <el-button size="small" type="primary" plain @click="openResource(item)">打开</el-button>
          <el-button
            v-if="!item.can_edit && item.pending_request"
            size="small"
            disabled
          >待审批</el-button>
          <el-button
            v-else-if="!item.can_edit"
            size="small"
            :loading="requesting === item.id"
            @click="requestEdit(item)"
          >申请编辑</el-button>
        </div>
      </div>
      <el-empty v-else description="暂时没有共享给你的资源" :image-size="64" />
    </div>
  </el-dialog>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { sharingApi } from '@/api'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  resourceType: { type: String, required: true },
})
const emit = defineEmits(['update:modelValue'])
const router = useRouter()
const loading = ref(false)
const items = ref([])
const requesting = ref(0)
const typeLabel = computed(() => ({ dashboard: '仪表盘', topology: '拓扑图', bigscreen: '大屏' }[props.resourceType] || '资源'))

function formatTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString('zh-CN', { hour12: false })
}

async function load() {
  loading.value = true
  try {
    const res = await sharingApi.sharedWithMe(props.resourceType)
    items.value = res.data?.items || []
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '共享资源加载失败')
  } finally {
    loading.value = false
  }
}

function openResource(item) {
  emit('update:modelValue', false)
  if (props.resourceType === 'dashboard') {
    const path = item.resource_key === 'instrument' ? '/instrument' : '/dashboard'
    router.push({ path, query: { shared: item.id } })
  } else if (props.resourceType === 'topology') router.push({ path: '/topology', query: { shared: item.id } })
  else router.push({ path: `/bigscreen/view/${encodeURIComponent(item.resource_key)}`, query: { shared: item.id } })
}

async function requestEdit(item) {
  requesting.value = item.id
  try {
    await sharingApi.requestEdit(item.id)
    ElMessage.success('编辑申请已提交，等待共享者审批')
    await load()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '提交编辑申请失败')
  } finally {
    requesting.value = 0
  }
}
</script>

<style scoped>
.shared-with-me { display: flex; flex-direction: column; gap: 13px; max-height: 62vh; overflow-y: auto; }
.shared-list { display: flex; flex-direction: column; gap: 8px; }
.shared-item { display: flex; align-items: center; gap: 9px; padding: 10px 11px; border: 1px solid #e2e8f0; border-radius: 8px; background: #fff; }
.shared-item-main { display: flex; flex-direction: column; gap: 3px; flex: 1; min-width: 0; }
.shared-item-main b { color: #1e293b; font-size: 13px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.shared-item-main span { color: #64748b; font-size: 11px; }
</style>
