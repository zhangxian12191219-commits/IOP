<template>
  <el-dialog
    :model-value="modelValue"
    title="选择设备图标"
    width="780px"
    top="8vh"
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <div class="picker-toolbar">
      <el-radio-group v-model="tab" size="small">
        <el-radio-button value="type">按设备类型</el-radio-button>
        <el-radio-button value="vendor">按厂商</el-radio-button>
        <el-radio-button value="custom">我的上传</el-radio-button>
      </el-radio-group>
      <el-input
        v-model="keyword"
        size="small"
        placeholder="搜索图标名称..."
        clearable
        style="width: 220px"
      />
      <span class="picker-tip">点击图标即可套用到当前设备（保存后生效）</span>
    </div>

    <div v-loading="loading" class="icon-grid">
      <div
        v-for="item in filtered"
        :key="item.id"
        class="icon-cell"
        :class="{ active: currentIcon === item.url }"
        @click="pick(item)"
      >
        <img :src="item.url" :alt="item.name" loading="lazy" />
        <div class="icon-name" :title="item.name">{{ item.name }}</div>
        <el-tag
          v-if="item.device_type && item.device_type === deviceType"
          class="recommend"
          size="small"
          type="success"
          effect="dark"
        >
          推荐
        </el-tag>
      </div>
      <el-empty
        v-if="!loading && !filtered.length"
        description="没有匹配的图标"
        class="icon-empty"
      />
    </div>

    <template #footer>
      <span class="picker-footer-tip">
        内置图标共 {{ presets.length }} 个（类型 {{ typeCount }} / 厂商 {{ vendorCount }}），
        也可在设备表单里上传并裁剪自定义图标
      </span>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { assetApi } from '@/api'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  deviceType: { type: String, default: null },
  currentIcon: { type: String, default: null },
})
const emit = defineEmits(['update:modelValue', 'select'])

const loading = ref(false)
const loaded = ref(false)
const presets = ref([])
const customIcons = ref([])
const tab = ref('type')
const keyword = ref('')

const typeCount = computed(() => presets.value.filter((p) => p.category === 'type').length)
const vendorCount = computed(() => presets.value.filter((p) => p.category === 'vendor').length)

const customItems = computed(() =>
  customIcons.value.map((url, index) => ({
    id: `custom-${index}`,
    name: `自定义 ${index + 1}`,
    url,
    category: 'custom',
    device_type: null,
  }))
)

const filtered = computed(() => {
  let list = []
  if (tab.value === 'type') list = presets.value.filter((p) => p.category === 'type')
  else if (tab.value === 'vendor') list = presets.value.filter((p) => p.category === 'vendor')
  else list = customItems.value

  const kw = keyword.value.trim().toLowerCase()
  if (kw) {
    list = list.filter(
      (item) =>
        String(item.name || '').toLowerCase().includes(kw) ||
        String(item.id || '').toLowerCase().includes(kw)
    )
  }
  return [...list].sort((a, b) => {
    const aRec = a.device_type && a.device_type === props.deviceType ? 0 : 1
    const bRec = b.device_type && b.device_type === props.deviceType ? 0 : 1
    if (aRec !== bRec) return aRec - bRec
    return String(a.name).localeCompare(String(b.name))
  })
})

async function loadPresets(force = false) {
  if (loading.value) return
  if (loaded.value && !force) return
  loading.value = true
  try {
    const res = await assetApi.iconPresets()
    presets.value = res.data.presets || []
    customIcons.value = res.data.custom_icons || []
    loaded.value = true
  } catch (e) {
    ElMessage.error(e.message || '加载图标库失败')
  } finally {
    loading.value = false
  }
}

function pick(item) {
  emit('select', item.url)
  emit('update:modelValue', false)
}

watch(
  () => props.modelValue,
  (visible) => {
    if (visible) {
      tab.value = 'type'
      keyword.value = ''
      loadPresets()
    }
  }
)
</script>

<style scoped>
.picker-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.picker-tip {
  margin-left: auto;
  font-size: 12px;
  color: #909399;
}

.icon-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(108px, 1fr));
  gap: 12px;
  min-height: 260px;
  max-height: 52vh;
  overflow-y: auto;
  padding: 4px;
}

.icon-cell {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 10px 6px 8px;
  border: 1px solid #ebeef5;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.15s ease;
  background: #fff;
}

.icon-cell:hover {
  border-color: #409eff;
  box-shadow: 0 4px 12px rgba(64, 158, 255, 0.16);
  transform: translateY(-1px);
}

.icon-cell.active {
  border-color: #409eff;
  background: #ecf5ff;
}

.icon-cell img {
  width: 56px;
  height: 56px;
  object-fit: contain;
  border-radius: 10px;
}

.icon-name {
  font-size: 12px;
  color: #606266;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recommend {
  position: absolute;
  top: 4px;
  right: 4px;
  transform: scale(0.82);
  transform-origin: top right;
}

.icon-empty {
  grid-column: 1 / -1;
}

.picker-footer-tip {
  margin-right: auto;
  font-size: 12px;
  color: #909399;
}
</style>
