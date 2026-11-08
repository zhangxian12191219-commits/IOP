<template>
  <div class="fb-settings">
    <div class="fb-settings-head">
      <div>
        <strong><el-icon><Mouse /></el-icon>悬浮球快捷入口</strong>
        <p>配置仅对当前登录用户生效。悬浮球可拖动到页面任意位置，并记录最近访问的 3 个页面。</p>
      </div>
      <el-switch v-model="enabled" inline-prompt active-text="启用" inactive-text="隐藏" @change="saveEnabled" />
    </div>

    <div class="fb-setting-block">
      <div class="fb-setting-title">
        <span>快捷功能</span>
        <span class="fb-count">已选 {{ selected.length }} / 8</span>
      </div>
      <div class="fb-shortcut-grid">
        <button
          v-for="item in allShortcuts"
          :key="item.id"
          type="button"
          class="fb-shortcut-card"
          :class="{ active: selected.includes(item.id), disabled: !selected.includes(item.id) && selected.length >= 8 }"
          @click="toggle(item.id)"
        >
          <span class="fb-shortcut-icon"><el-icon><component :is="item.icon" /></el-icon></span>
          <span class="fb-shortcut-text">
            <strong>{{ item.label }}</strong>
            <small>{{ item.type === 'call' ? '直接选择在线联系人发起通话' : item.path }}</small>
          </span>
          <el-icon class="fb-check"><Check v-if="selected.includes(item.id)" /><Plus v-else /></el-icon>
        </button>
      </div>
    </div>

    <div class="fb-setting-block custom-block">
      <div class="fb-setting-title">
        <span>自定义快捷入口</span>
        <span class="fb-count">已添加 {{ customShortcuts.length }} 个</span>
      </div>
      <div class="fb-custom-form">
        <el-input v-model="newShortcut.label" maxlength="24" placeholder="名称，如：值班表" />
        <el-input v-model="newShortcut.path" maxlength="300" placeholder="/alerts 或 https://..." />
        <el-select v-model="newShortcut.icon" style="width: 110px">
          <el-option v-for="icon in ICON_OPTIONS" :key="icon" :label="icon" :value="icon" />
        </el-select>
        <el-button type="primary" plain @click="addCustomShortcut">添加</el-button>
      </div>
      <div v-if="customShortcuts.length" class="fb-custom-list">
        <div v-for="item in customShortcuts" :key="item.id" class="fb-custom-row">
          <span class="fb-custom-icon"><el-icon><component :is="item.icon || 'Link'" /></el-icon></span>
          <span class="fb-custom-main"><b>{{ item.label }}</b><small>{{ item.path }}</small></span>
          <el-button link type="danger" @click="removeCustomShortcut(item)">删除</el-button>
        </div>
      </div>
      <div v-else class="fb-custom-empty">还没有自定义入口，填写名称和路径后点击“添加”。</div>
      <div class="fb-custom-tip">支持站内路径和 http(s) 链接；添加后会自动选中，保存配置后出现在悬浮球。</div>
    </div>

    <div class="fb-setting-block recent-block">
      <div class="fb-setting-title"><span>最近浏览</span><span class="fb-count">最多 3 条</span></div>
      <div v-if="imState.preferences.recent?.length" class="fb-recent-list">
        <div v-for="item in imState.preferences.recent" :key="item.path" class="fb-recent-row">
          <el-icon><Clock /></el-icon>
          <span>{{ item.title || item.path }}</span>
          <small>{{ item.path }}</small>
        </div>
      </div>
      <el-empty v-else description="访问页面后会自动记录" :image-size="44" />
      <el-button v-if="imState.preferences.recent?.length" link type="primary" @click="clearRecent">清空浏览记录</el-button>
    </div>

    <div class="fb-settings-actions">
      <el-button @click="restoreDefaults">恢复默认</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存悬浮球配置</el-button>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  FLOATING_SHORTCUTS, imState, loadPreferences, savePreferences,
} from '@/store/im'

const ICON_OPTIONS = ['Link', 'Star', 'Monitor', 'Bell', 'Tools', 'Connection', 'DataBoard', 'Cpu', 'Setting', 'Grid']
const selected = ref([...(imState.preferences.shortcuts || [])])
const enabled = ref(imState.preferences.enabled !== false)
const saving = ref(false)
const customShortcuts = ref([...(imState.preferences.custom_shortcuts || [])])
const newShortcut = ref({ label: '', path: '', icon: 'Link' })
const allShortcuts = computed(() => [
  ...FLOATING_SHORTCUTS,
  ...customShortcuts.value.map((item) => ({
    id: item.id,
    label: item.label,
    icon: item.icon || 'Link',
    type: 'route',
    path: item.path,
    custom: true,
  })),
])

watch(() => imState.preferences.shortcuts, (value) => {
  if (Array.isArray(value)) selected.value = [...value]
})
watch(() => imState.preferences.custom_shortcuts, (value) => {
  if (Array.isArray(value)) customShortcuts.value = [...value]
})

function toggle(id) {
  if (selected.value.includes(id)) {
    selected.value = selected.value.filter((item) => item !== id)
    return
  }
  if (selected.value.length >= 8) {
    ElMessage.warning('最多选择 8 个快捷功能')
    return
  }
  selected.value = [...selected.value, id]
}

async function persist(patch) {
  saving.value = true
  try {
    await savePreferences(patch, true)
    ElMessage.success('悬浮球配置已保存')
  } catch {
    ElMessage.error('保存失败，请稍后重试')
  } finally {
    saving.value = false
  }
}

async function save() {
  await persist({ shortcuts: selected.value, custom_shortcuts: customShortcuts.value })
}

function addCustomShortcut() {
  const label = String(newShortcut.value.label || '').trim()
  let path = String(newShortcut.value.path || '').trim()
  if (!label) {
    ElMessage.warning('请填写快捷入口名称')
    return
  }
  if (!path) {
    ElMessage.warning('请填写站内路径或 http(s) 链接')
    return
  }
  if (!path.startsWith('/') && !/^https?:\/\//i.test(path)) {
    ElMessage.warning('路径需以 / 开头，或填写 http(s) 链接')
    return
  }
  if (customShortcuts.value.some((item) => item.path === path)) {
    ElMessage.warning('该路径已存在')
    return
  }
  if (customShortcuts.value.length >= 20) {
    ElMessage.warning('最多添加 20 个自定义入口')
    return
  }
  const id = `custom_${Date.now().toString(36)}`
  customShortcuts.value = [
    ...customShortcuts.value,
    { id, label: label.slice(0, 24), path: path.slice(0, 300), icon: newShortcut.value.icon || 'Link' },
  ]
  if (selected.value.length < 8) selected.value = [...selected.value, id]
  newShortcut.value = { label: '', path: '', icon: 'Link' }
  ElMessage.success('已添加，保存后生效')
}

function removeCustomShortcut(item) {
  customShortcuts.value = customShortcuts.value.filter((entry) => entry.id !== item.id)
  selected.value = selected.value.filter((id) => id !== item.id)
}

async function saveEnabled(value) {
  await persist({ enabled: !!value })
}

async function restoreDefaults() {
  selected.value = ['im', 'notes', 'tools', 'audio-call', 'video-call', 'alerts']
  await persist({ shortcuts: selected.value })
}

async function clearRecent() {
  await persist({ recent: [] })
}

onMounted(async () => {
  if (!imState.preferencesLoaded) {
    try {
      await loadPreferences()
      selected.value = [...(imState.preferences.shortcuts || [])]
      customShortcuts.value = [...(imState.preferences.custom_shortcuts || [])]
      enabled.value = imState.preferences.enabled !== false
    } catch {
      /* 使用默认配置 */
    }
  }
})
</script>

<style scoped>
.fb-settings { max-width: 920px; display: flex; flex-direction: column; gap: 16px; padding: 4px 2px 12px; }
.fb-settings-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding: 14px 16px; border: 1px solid #dbe6ee; border-radius: 10px; background: #f8fbfd; }
.fb-settings-head strong { display: inline-flex; align-items: center; gap: 7px; color: #1f3b50; font-size: 15px; }
.fb-settings-head p { margin: 6px 0 0; color: #6c8191; font-size: 12px; line-height: 1.7; }
.fb-setting-block { border: 1px solid #e2eaf0; border-radius: 10px; padding: 14px 16px; }
.fb-setting-title { display: flex; align-items: center; justify-content: space-between; color: #263e50; font-size: 13px; font-weight: 700; margin-bottom: 10px; }
.fb-count { color: #8aa0b0; font-size: 11px; font-weight: 400; }
.fb-shortcut-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 9px; }
.fb-shortcut-card { display: flex; align-items: center; gap: 10px; padding: 10px 11px; border-radius: 8px; border: 1px solid #e0e9ef; background: #fff; cursor: pointer; text-align: left; transition: border-color .15s, box-shadow .15s; }
.fb-shortcut-card:hover { border-color: #7cc4d8; box-shadow: 0 3px 10px rgba(38, 111, 133, .08); }
.fb-shortcut-card.active { border-color: #2b9fbd; background: #f0fbfe; }
.fb-shortcut-card.disabled { opacity: .55; }
.fb-shortcut-icon { width: 30px; height: 30px; flex: 0 0 30px; border-radius: 8px; background: #e7f6fb; color: #187d99; display: grid; place-items: center; }
.fb-shortcut-text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.fb-shortcut-text strong { color: #29495d; font-size: 12px; }
.fb-shortcut-text small { color: #8a9daa; font-size: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fb-check { color: #2b9fbd; font-size: 14px; }
.fb-custom-form { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }
.fb-custom-form .el-input { width: 180px; }
.fb-custom-list { display: flex; flex-direction: column; gap: 6px; }
.fb-custom-row { display: flex; align-items: center; gap: 9px; padding: 7px 9px; border: 1px solid #e2eaf0; border-radius: 7px; background: #f8fbfd; }
.fb-custom-icon { width: 27px; height: 27px; display: grid; place-items: center; border-radius: 7px; background: #e7f6fb; color: #187d99; }
.fb-custom-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.fb-custom-main b { color: #29495d; font-size: 12px; }
.fb-custom-main small { color: #8a9daa; font-size: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fb-custom-empty { padding: 10px; color: #8a9daa; font-size: 12px; text-align: center; border: 1px dashed #dbe6ee; border-radius: 7px; }
.fb-custom-tip { margin-top: 7px; color: #8a9daa; font-size: 10px; line-height: 1.6; }
.fb-recent-list { display: flex; flex-direction: column; gap: 5px; }
.fb-recent-row { display: flex; align-items: center; gap: 8px; color: #537184; font-size: 12px; padding: 6px 8px; border-radius: 6px; background: #f7fafc; }
.fb-recent-row small { margin-left: auto; color: #9aadb9; font-size: 10px; }
.fb-settings-actions { display: flex; justify-content: flex-end; gap: 10px; }
@media (max-width: 760px) { .fb-settings-head { flex-direction: column; } .fb-shortcut-grid { grid-template-columns: 1fr; } }
</style>
