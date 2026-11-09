<template>
  <el-dialog
    :model-value="modelValue"
    title="厂商库"
    width="900px"
    destroy-on-close
    @update:model-value="emit('update:modelValue', $event)"
    @open="load"
  >
    <div class="vendor-toolbar">
      <el-input
        v-model="keyword"
        clearable
        placeholder="搜索厂商名称、别名或备注"
        style="width: 250px"
        @keyup.enter="search"
        @clear="search"
      />
      <el-select v-model="category" clearable placeholder="全部分类" style="width: 140px" @change="search">
        <el-option v-for="item in categories" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-select v-model="enabled" placeholder="启用状态" style="width: 120px" @change="search">
        <el-option label="全部" :value="''" />
        <el-option label="启用" :value="'1'" />
        <el-option label="停用" :value="'0'" />
      </el-select>
      <el-button size="small" @click="search">查询</el-button>
      <el-button v-if="canEdit" type="primary" size="small" @click="openCreate">新增厂商</el-button>
    </div>

    <el-table :data="items" v-loading="loading" size="small" stripe>
      <el-table-column prop="name" label="厂商" min-width="130">
        <template #default="{ row }">
          <div class="vendor-name">
            <b>{{ row.name }}</b>
            <el-tag v-if="row.is_builtin" size="small" type="success" effect="plain">内置</el-tag>
          </div>
          <div v-if="row.aliases?.length" class="vendor-alias">{{ row.aliases.join(' / ') }}</div>
        </template>
      </el-table-column>
      <el-table-column prop="category_label" label="分类" width="105" />
      <el-table-column label="使用情况" width="125">
        <template #default="{ row }">
          <span class="vendor-usage">资产 {{ row.device_count }} · MIB {{ row.mib_count }}</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="78">
        <template #default="{ row }">
          <el-tag size="small" :type="row.is_enabled ? 'success' : 'info'" effect="plain">
            {{ row.is_enabled ? '启用' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="note" label="备注" min-width="140" show-overflow-tooltip />
      <el-table-column v-if="canEdit" label="操作" width="190" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
          <el-button link size="small" @click="toggle(row)">{{ row.is_enabled ? '停用' : '启用' }}</el-button>
          <el-button
            v-if="!row.is_builtin"
            link
            type="danger"
            size="small"
            @click="remove(row)"
          >删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="vendor-pager">
      <span class="muted">共 {{ total }} 个厂商</span>
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="size"
        :page-sizes="[10, 20, 50, 100]"
        :total="total"
        layout="sizes, prev, pager, next"
        background
        small
        @current-change="load"
        @size-change="search"
      />
    </div>

    <el-dialog
      v-model="editVisible"
      :title="editing?.id ? '编辑厂商' : '新增厂商'"
      width="520px"
      append-to-body
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="厂商名称" prop="name">
          <el-input v-model="form.name" :disabled="!!editing?.is_builtin" maxlength="80" placeholder="例如 Huawei / 华为" />
          <div v-if="editing?.is_builtin" class="muted form-help">内置厂商名称不可修改，可修改别名、分类或停用。</div>
          <div v-else class="muted form-help">修改名称会同步更新已引用该厂商的资产和 MIB。</div>
        </el-form-item>
        <el-form-item label="别名">
          <el-input v-model="form.aliasesText" placeholder="多个别名用逗号分隔，例如：华为, OceanStor" />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="form.category" style="width: 100%">
            <el-option v-for="item in categories" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="form.is_enabled" active-text="资产表单可选" inactive-text="停用" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.note" type="textarea" :rows="2" maxlength="500" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { vendorApi } from '@/api'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  canEdit: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'changed'])

const loading = ref(false)
const saving = ref(false)
const items = ref([])
const total = ref(0)
const page = ref(1)
const size = ref(20)
const keyword = ref('')
const category = ref('')
const enabled = ref('')
const categories = [
  { value: 'network', label: '网络设备' },
  { value: 'server', label: '服务器' },
  { value: 'storage', label: '存储' },
  { value: 'backup', label: '备份一体机' },
  { value: 'security', label: '安全设备' },
  { value: 'camera', label: '视频监控' },
  { value: 'virtualization', label: '虚拟化' },
  { value: 'other', label: '其他' },
]
const editVisible = ref(false)
const editing = ref(null)
const formRef = ref(null)
const form = reactive({
  name: '',
  aliasesText: '',
  category: 'other',
  note: '',
  is_enabled: true,
})
const rules = {
  name: [{ required: true, message: '请输入厂商名称', trigger: 'blur' }],
}

const queryParams = computed(() => ({
  keyword: keyword.value,
  category: category.value,
  enabled: enabled.value === '' ? undefined : enabled.value === '1',
  page: page.value,
  size: size.value,
}))

async function load() {
  loading.value = true
  try {
    const res = await vendorApi.list(queryParams.value)
    items.value = res.data.items || []
    total.value = Number(res.data.total) || 0
  } catch (e) {
    ElMessage.error(e.message || '加载厂商库失败')
  } finally {
    loading.value = false
  }
}

function search() {
  page.value = 1
  load()
}

function openCreate() {
  editing.value = null
  Object.assign(form, { name: '', aliasesText: '', category: 'other', note: '', is_enabled: true })
  editVisible.value = true
}

function openEdit(row) {
  editing.value = row
  Object.assign(form, {
    name: row.name,
    aliasesText: (row.aliases || []).join(', '),
    category: row.category || 'other',
    note: row.note || '',
    is_enabled: row.is_enabled !== false,
  })
  editVisible.value = true
}

async function save() {
  await formRef.value.validate()
  const aliases = String(form.aliasesText || '')
    .split(/[,，;；]/)
    .map((item) => item.trim())
    .filter(Boolean)
  const payload = {
    name: form.name.trim(),
    aliases,
    category: form.category,
    note: form.note,
    is_enabled: form.is_enabled,
  }
  saving.value = true
  try {
    if (editing.value?.id) {
      await vendorApi.update(editing.value.id, payload)
      ElMessage.success('厂商已更新')
    } else {
      await vendorApi.create(payload)
      ElMessage.success('厂商已新增')
    }
    editVisible.value = false
    emit('changed')
    await load()
  } catch (e) {
    ElMessage.error(e.message || '保存厂商失败')
  } finally {
    saving.value = false
  }
}

async function toggle(row) {
  try {
    await vendorApi.update(row.id, { is_enabled: !row.is_enabled })
    ElMessage.success(row.is_enabled ? '厂商已停用' : '厂商已启用')
    emit('changed')
    await load()
  } catch (e) {
    ElMessage.error(e.message || '更新厂商状态失败')
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(
      `确认删除厂商“${row.name}”？仅未被资产或 MIB 引用的自定义厂商可以删除。`,
      '删除厂商',
      { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await vendorApi.remove(row.id)
    ElMessage.success('厂商已删除')
    emit('changed')
    await load()
  } catch (e) {
    ElMessage.error(e.message || '删除厂商失败')
  }
}
</script>

<style scoped>
.vendor-toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px; }
.vendor-name { display: flex; align-items: center; gap: 6px; }
.vendor-alias { color: #8a9aa4; font-size: 11px; margin-top: 2px; }
.vendor-usage { color: #526b78; font-size: 12px; }
.vendor-pager { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 14px; }
.form-help { margin-top: 3px; font-size: 11px; line-height: 1.5; }
.muted { color: #8a9aa4; }
</style>
