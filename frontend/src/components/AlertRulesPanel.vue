<template>
  <div class="alert-rules-panel">
    <div class="rules-toolbar">
      <div>
        <div class="rules-title">自定义告警规则</div>
        <div class="rules-sub">按 CPU、内存、温度、磁盘、电源、离线和自定义指标设置阈值；阈值会同步到仪表盘告警指标</div>
      </div>
      <el-button v-if="canEdit" type="primary" size="small" @click="openCreate()">
        <el-icon><Plus /></el-icon>新增告警规则
      </el-button>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="rule-sync-tip"
      title="此处配置的预警/告警阈值会同步到仪表盘的指标设置，修改后仪表盘对应告警值自动更新并锁定。"
    />

    <div class="preset-row">
      <span>常用模板</span>
      <el-button v-for="preset in presets" :key="preset.label" size="small" plain :disabled="!canEdit" @click="applyPreset(preset)">
        {{ preset.label }}
      </el-button>
    </div>

    <el-table :data="rules" v-loading="loading" size="small" empty-text="尚未配置告警规则，可使用上方模板快速创建">
      <el-table-column prop="name" label="规则名称" min-width="150" show-overflow-tooltip />
      <el-table-column label="监控指标" width="150">
        <template #default="{ row }">{{ row.metric_label }}</template>
      </el-table-column>
      <el-table-column prop="condition" label="触发条件" min-width="170" />
      <el-table-column label="级别" width="100">
        <template #default="{ row }">
          <el-tag :type="levelType(row.level)" size="small" effect="dark">{{ row.level_label }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="通知方式" min-width="170">
        <template #default="{ row }">
          <template v-if="row.notify_channel_ids?.length">
            <el-tag v-for="channel in channelsFor(row.notify_channel_ids)" :key="channel.id" size="small" effect="plain" class="channel-tag">
              {{ channel.name }}
            </el-tag>
          </template>
          <span v-else class="muted">仅站内告警</span>
        </template>
      </el-table-column>
      <el-table-column label="启用" width="76">
        <template #default="{ row }">
          <el-switch :model-value="row.enabled" size="small" :disabled="!canEdit" @change="(value) => toggleRule(row, value)" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button v-if="canEdit" link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button v-if="canEdit" link type="danger" @click="removeRule(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑告警规则' : '新增告警规则'" width="620px" :close-on-click-modal="false" append-to-body>
      <el-form :model="form" label-width="106px">
        <el-form-item label="规则名称" required>
          <el-input v-model="form.name" maxlength="100" placeholder="例如：核心交换机 CPU 过载" />
        </el-form-item>
        <el-form-item label="监控指标" required>
          <el-select v-model="form.metric" style="width:100%" @change="onMetricChange">
            <el-option v-for="item in metrics" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.metric === 'custom'" label="指标 Key" required>
          <el-input v-model="form.custom_key" placeholder="例如：disk_health、fan_speed、光模块温度" />
          <div class="form-hint">对应设备自定义指标/服务器传感器中配置的指标 key。</div>
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="10">
            <el-form-item label="判断条件" required>
              <el-select v-model="form.operator" style="width:100%">
                <el-option v-for="item in operators" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="14">
            <el-form-item :label="`阈值${currentMetric.unit ? `（${currentMetric.unit}）` : ''}`" required>
              <el-input-number v-model="form.threshold" :precision="2" :step="1" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="严重级别" required>
          <el-radio-group v-model="form.level">
            <el-radio-button v-for="item in levels" :key="item.value" :value="item.value">{{ item.label }}</el-radio-button>
          </el-radio-group>
          <div class="form-hint">级别决定告警颜色、声音和通知通道的最低级别过滤。</div>
        </el-form-item>
        <el-form-item label="自定义级别名">
          <el-input v-model="form.level_label" maxlength="50" :placeholder="`留空使用「${currentLevel.label}」`" />
        </el-form-item>
        <el-form-item label="通知方式">
          <el-select v-model="form.notify_channel_ids" multiple collapse-tags clearable placeholder="选择通知通道；不选则仅站内告警" style="width:100%">
            <el-option
              v-for="channel in channels"
              :key="channel.id"
              :label="`${channel.name}（${channel.channel_type}${channel.enabled ? '' : ' · 已停用'}）`"
              :value="channel.id"
            />
          </el-select>
          <div class="form-hint">只会通过这里选中的通道发送；未选择通道时仍会在告警中心产生记录。</div>
        </el-form-item>
        <el-form-item label="启用规则">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <div class="threshold-tip">
        <el-icon><InfoFilled /></el-icon>
        <span v-if="form.metric === 'disk_usage'">磁盘使用率从主机 HOST-RESOURCES 存储表采集，取最高磁盘分区使用率。</span>
        <span v-else-if="form.metric === 'power'">电源故障值为 1、正常为 0，通常使用「= 1」触发。</span>
        <span v-else-if="form.metric === 'offline'">设备离线值为 1，通常使用「= 1」触发；离线规则优先于全局离线告警。</span>
        <span v-else-if="form.metric === 'custom'">磁盘健康、风扇、光功率等可先在设备自定义指标中配置 OID，再在这里按 key 设置规则，例如 disk_health = 1。</span>
        <span v-else>达到条件后产生告警；同一规则在未确认前不会重复产生告警。</span>
      </div>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveRule">保存规则</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { alertRuleApi } from '@/api'
import { syncRuleToDashboardConfig, removeRuleFromDashboardConfig } from '@/utils/dashboardRuleConfigSync'
import { can } from '@/store/auth'

const props = defineProps({
  deviceId: { type: [Number, String], default: null },
})

const metrics = [
  { value: 'cpu_usage', label: 'CPU 使用率', unit: '%', threshold: 90 },
  { value: 'memory_usage', label: '内存使用率', unit: '%', threshold: 75 },
  { value: 'temperature', label: '最高部件温度', unit: '°C', threshold: 80 },
  { value: 'fan_speed', label: '风扇转速（最高）', unit: 'RPM', threshold: 500 },
  { value: 'disk_usage', label: '磁盘使用率', unit: '%', threshold: 85 },
  { value: 'power', label: '电源故障（1=故障）', unit: '', threshold: 1 },
  { value: 'offline', label: '设备离线（1=离线）', unit: '', threshold: 1 },
  { value: 'uptime', label: '运行时间', unit: '秒', threshold: 60 },
  { value: 'custom', label: '自定义指标', unit: '', threshold: 1 },
]
const levels = [
  { value: 'info', label: '提示' },
  { value: 'warning', label: '警告' },
  { value: 'critical', label: '严重' },
  { value: 'emergency', label: '紧急' },
]
const operators = [
  { value: 'gt', label: '大于 >' },
  { value: 'gte', label: '大于等于 ≥' },
  { value: 'lt', label: '小于 <' },
  { value: 'lte', label: '小于等于 ≤' },
  { value: 'eq', label: '等于 =' },
  { value: 'ne', label: '不等于 ≠' },
]
const presets = [
  { label: 'CPU > 90%', name: 'CPU 使用率过高', metric: 'cpu_usage', operator: 'gt', threshold: 90, level: 'warning' },
  { label: 'CPU > 95% 严重', name: 'CPU 严重过载', metric: 'cpu_usage', operator: 'gt', threshold: 95, level: 'critical' },
  { label: '内存 > 75%', name: '内存使用率过高', metric: 'memory_usage', operator: 'gt', threshold: 75, level: 'warning' },
  { label: '最高部件温度 ≥ 80°C 预警', name: '最高部件温度预警', metric: 'temperature', operator: 'gte', threshold: 80, level: 'warning' },
  { label: '最高部件温度 ≥ 90°C 告警', name: '最高部件温度过高', metric: 'temperature', operator: 'gte', threshold: 90, level: 'critical' },
  { label: '风扇最高转速 < 500 RPM', name: '风扇转速过低', metric: 'fan_speed', operator: 'lt', threshold: 500, level: 'warning' },
  { label: '磁盘 > 85%', name: '磁盘使用率过高', metric: 'disk_usage', operator: 'gt', threshold: 85, level: 'warning' },
  { label: '电源故障', name: '电源状态异常', metric: 'power', operator: 'eq', threshold: 1, level: 'critical' },
  { label: '设备离线', name: '设备离线', metric: 'offline', operator: 'eq', threshold: 1, level: 'critical' },
  { label: '硬盘故障', name: '硬盘健康异常', metric: 'custom', custom_key: 'disk_health', operator: 'eq', threshold: 1, level: 'critical' },
]

const rules = ref([])
const channels = ref([])
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editingId = ref(null)
const form = reactive({
  name: '',
  metric: 'cpu_usage',
  custom_key: '',
  operator: 'gt',
  threshold: 90,
  level: 'warning',
  level_label: '',
  notify_channel_ids: [],
  enabled: true,
})
const emit = defineEmits(['changed'])
const canEdit = computed(() => can('assets:edit'))
const currentMetric = computed(() => metrics.find((item) => item.value === form.metric) || metrics[0])
const currentLevel = computed(() => levels.find((item) => item.value === form.level) || levels[1])

function levelType(level) {
  return { info: 'info', warning: 'warning', critical: 'danger', emergency: 'danger' }[level] || 'info'
}

function channelsFor(ids) {
  return channels.value.filter((channel) => ids.includes(channel.id))
}

async function loadRules() {
  if (!props.deviceId) return
  loading.value = true
  try {
    const { data } = await alertRuleApi.list(props.deviceId)
    rules.value = data || []
    // 自定义规则优先：现有规则也同步回仪表盘指标配置。
    rules.value.forEach((rule) => syncRuleToDashboardConfig(props.deviceId, rule))
  } catch (error) {
    ElMessage.error(error.message || '加载告警规则失败')
  } finally {
    loading.value = false
  }
}

async function loadChannels() {
  try {
    const { data } = await alertRuleApi.channels()
    channels.value = data || []
  } catch {
    channels.value = []
  }
}

function resetForm() {
  Object.assign(form, {
    name: '',
    metric: 'cpu_usage',
    custom_key: '',
    operator: 'gt',
    threshold: 90,
    level: 'warning',
    level_label: '',
    notify_channel_ids: [],
    enabled: true,
  })
}

function onMetricChange() {
  form.threshold = currentMetric.value.threshold
  if (form.metric === 'power' || form.metric === 'offline') form.operator = 'eq'
  else if (form.operator === 'eq' || form.operator === 'ne') form.operator = 'gt'
}

function openCreate() {
  editingId.value = null
  resetForm()
  dialogVisible.value = true
}

function applyPreset(preset) {
  editingId.value = null
  resetForm()
  Object.assign(form, {
    name: preset.name,
    metric: preset.metric,
    custom_key: preset.custom_key || '',
    operator: preset.operator,
    threshold: preset.threshold,
    level: preset.level,
  })
  dialogVisible.value = true
}

function openEdit(rule) {
  editingId.value = rule.id
  Object.assign(form, {
    name: rule.name,
    metric: rule.metric,
    custom_key: rule.custom_key || '',
    operator: rule.operator,
    threshold: rule.threshold,
    level: rule.level,
    level_label: rule.level_label || '',
    notify_channel_ids: [...(rule.notify_channel_ids || [])],
    enabled: rule.enabled,
  })
  dialogVisible.value = true
}

async function saveRule() {
  if (!form.name.trim()) {
    ElMessage.warning('请填写规则名称')
    return
  }
  if (form.metric === 'custom' && !form.custom_key.trim()) {
    ElMessage.warning('请填写自定义指标 Key')
    return
  }
  saving.value = true
  try {
    const payload = {
      device_id: Number(props.deviceId),
      name: form.name.trim(),
      metric: form.metric,
      custom_key: form.custom_key.trim() || null,
      operator: form.operator,
      threshold: Number(form.threshold),
      level: form.level,
      level_label: form.level_label.trim() || null,
      notify_channel_ids: form.notify_channel_ids,
      enabled: form.enabled,
    }
    if (editingId.value) await alertRuleApi.update(editingId.value, payload)
    else await alertRuleApi.create(payload)
    syncRuleToDashboardConfig(props.deviceId, payload)
    ElMessage.success(editingId.value ? '告警规则已更新' : '告警规则已创建')
    dialogVisible.value = false
    await loadRules()
    emit('changed')
  } catch (error) {
    ElMessage.error(error.message || '保存告警规则失败')
  } finally {
    saving.value = false
  }
}

async function toggleRule(rule, enabled) {
  try {
    await alertRuleApi.update(rule.id, {
      device_id: Number(props.deviceId),
      name: rule.name,
      metric: rule.metric,
      custom_key: rule.custom_key || null,
      operator: rule.operator,
      threshold: rule.threshold,
      level: rule.level,
      level_label: rule.level_label || null,
      notify_channel_ids: rule.notify_channel_ids || [],
      enabled,
    })
    rule.enabled = enabled
    syncRuleToDashboardConfig(props.deviceId, rule)
    emit('changed')
    ElMessage.success(enabled ? '规则已启用' : '规则已停用')
  } catch (error) {
    ElMessage.error(error.message || '更新规则失败')
  }
}

async function removeRule(rule) {
  try {
    await ElMessageBox.confirm(`确定删除告警规则「${rule.name}」吗？删除后该规则不再产生新告警。`, '删除告警规则', {
      type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await alertRuleApi.remove(rule.id)
    const remaining = rules.value.filter((item) => item.id !== rule.id)
    rules.value = remaining
    removeRuleFromDashboardConfig(props.deviceId, rule, remaining)
    ElMessage.success('告警规则已删除')
    await loadRules()
    emit('changed')
  } catch (error) {
    ElMessage.error(error.message || '删除告警规则失败')
  }
}

onMounted(() => {
  loadRules()
  loadChannels()
})
watch(() => props.deviceId, () => loadRules())
</script>

<style scoped>
.alert-rules-panel { display: flex; flex-direction: column; gap: 10px; }
.rules-toolbar { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; }
.rules-title { color: #24425b; font-size: 14px; font-weight: 600; }
.rules-sub { margin-top: 4px; color: #8ca0af; font-size: 10px; line-height: 1.5; }
.rule-sync-tip { margin: 10px 0 12px; }
.preset-row { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; padding: 7px 9px; border-radius: 7px; background: #f6fbfe; }
.preset-row > span { color: #8ca0af; font-size: 10px; margin-right: 2px; }
.preset-row .el-button { margin: 0; height: 25px; padding: 0 8px; font-size: 10px; }
.channel-tag { margin: 1px 3px 1px 0; }
.muted { color: #9aacba; font-size: 10px; }
.form-hint { margin-top: 3px; color: #91a5b4; font-size: 9px; line-height: 1.5; }
.threshold-tip { display: flex; align-items: flex-start; gap: 6px; padding: 8px 10px; border-radius: 6px; background: #f5faff; color: #7d94a5; font-size: 10px; line-height: 1.6; }
.threshold-tip .el-icon { flex-shrink: 0; margin-top: 1px; color: #0ea5e9; }
</style>
