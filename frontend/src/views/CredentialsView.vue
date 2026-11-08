<template>
  <div class="credential-view">
    <el-card shadow="never">
      <div class="credential-head">
        <div>
          <h2>设备凭据</h2>
          <p>统一维护 SSH 用户名、密码和端口，并分配给资产；设备巡检和配置备份共用同一份凭据，无需重复录入。</p>
        </div>
        <div class="credential-actions">
          <el-input v-model="keyword" clearable placeholder="搜索名称/用户名/说明" size="small" style="width: 210px" @keyup.enter="loadCredentials(1)" />
          <el-button size="small" @click="loadCredentials(1)">查询</el-button>
          <el-button size="small" @click="openImport">批量导入</el-button>
          <el-dropdown @command="exportCredentials">
            <el-button size="small">导出<el-icon class="el-icon--right"><ArrowDown /></el-icon></el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="no_password">导出（不含密码）</el-dropdown-item>
                <el-dropdown-item command="password" divided>导出（含明文密码）</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button v-if="canEdit" type="primary" size="small" @click="openCreate">新增凭据</el-button>
        </div>
      </div>

      <el-alert type="warning" :closable="false" show-icon class="credential-alert"
        title="安全建议：请使用仅具备查看权限的只读 SSH 账号，不要使用管理员账号，不要复用网络设备超级管理员密码。" />
      <el-alert type="info" :closable="false" show-icon class="credential-alert"
        title="一个凭据可分配给多台资产；设备的备份参数中单独填写的用户名/密码优先于关联凭据。凭据密码不会在页面回显。" />

      <div v-if="selectedIds.length" class="credential-batch-bar">
        <span>已选择 <b>{{ selectedIds.length }}</b> 个凭据</span>
        <el-button size="small" @click="exportCredentials('no_password')">导出选中</el-button>
        <el-button v-if="canEdit" size="small" type="danger" plain @click="batchDelete">批量删除</el-button>
        <el-button size="small" @click="selectedIds = []">清空选择</el-button>
      </div>
      <el-table :data="credentials" v-loading="loading" stripe class="credential-table" @selection-change="onSelectionChange">
        <el-table-column type="selection" width="44" fixed="left" />
        <el-table-column prop="name" label="凭据名称" min-width="150">
          <template #default="{ row }"><strong>{{ row.name }}</strong></template>
        </el-table-column>
        <el-table-column prop="username" label="SSH 用户名" min-width="120" />
        <el-table-column prop="port" label="端口" width="90" />
        <el-table-column label="关联资产" min-width="260">
          <template #default="{ row }">
            <div v-if="row.assets?.length" class="asset-tags">
              <el-tag v-for="asset in row.assets.slice(0, 8)" :key="asset.id" size="small" effect="plain">
                {{ asset.name }} <span class="asset-ip">{{ asset.ip_address }}</span>
              </el-tag>
              <el-tag v-if="row.assets.length > 8" size="small" type="info">+{{ row.assets.length - 8 }}</el-tag>
            </div>
            <span v-else class="muted">未分配资产</span>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="说明" min-width="180" show-overflow-tooltip />
        <el-table-column label="密码" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.password_set ? 'success' : 'info'" effect="plain">{{ row.password_set ? '已设置' : '未设置' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button v-if="canEdit" link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="canEdit" link type="danger" size="small" @click="removeCredential(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty><el-empty description="还没有设备凭据" :image-size="60" /></template>
      </el-table>
      <div class="credential-pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          @current-change="loadCredentials"
          @size-change="onPageSizeChange"
        />
      </div>
    </el-card>

    <el-dialog v-model="importVisible" title="批量导入设备凭据" width="min(650px, 94vw)" top="8vh">
      <el-alert type="info" :closable="false" show-icon class="mb12"
        title="支持 .xlsx / .csv；列名：凭据名称、SSH用户名、SSH密码、端口、说明、关联资产。关联资产可填 IP 或资产名称，多个用分号分隔。" />
      <el-form label-width="100px">
        <el-form-item label="导入文件">
          <el-upload
            :auto-upload="false"
            :limit="1"
            accept=".xlsx,.csv"
            :on-change="onImportFileChange"
            :on-remove="() => { importFile = null }"
          >
            <el-button>选择文件</el-button>
            <template #tip><div class="form-tip">最大 10MB；同名列可跳过或覆盖。</div></template>
          </el-upload>
        </el-form-item>
        <el-form-item label="重复凭据">
          <el-radio-group v-model="importMode">
            <el-radio value="skip">跳过同名列</el-radio>
            <el-radio value="update">覆盖同名列</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <el-alert v-if="importResult" :type="importResult.errors?.length ? 'warning' : 'success'" :closable="false" show-icon
        :title="importResult.message || '导入完成'" />
      <div v-if="importResult?.errors?.length" class="import-errors">
        <div v-for="item in importResult.errors" :key="item.row">第 {{ item.row }} 行：{{ item.message }}</div>
      </div>
      <template #footer>
        <el-button @click="importVisible = false">取消</el-button>
        <el-button type="primary" :loading="importLoading" :disabled="!importFile" @click="submitImport">开始导入</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑设备凭据' : '新增设备凭据'" width="min(680px, 94vw)" top="6vh" :close-on-click-modal="false">
      <el-form :model="form" label-width="100px">
        <el-form-item label="凭据名称" required>
          <el-input v-model="form.name" maxlength="120" placeholder="例如：核心网络 SSH 管理账号" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="SSH 用户名" required><el-input v-model="form.username" maxlength="120" placeholder="admin" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="SSH 端口"><el-input-number v-model="form.port" :min="1" :max="65535" controls-position="right" style="width: 100%" /></el-form-item></el-col>
        </el-row>
        <el-form-item label="SSH 密码">
          <el-input v-model="form.password" type="password" show-password
            :placeholder="form.id && form.password_set ? '已设置，留空表示不修改' : '请输入 SSH 密码'" />
          <div class="form-tip credential-security-tip">
            建议使用只读账号：只授予查看配置、运行状态、CPU/内存和日志的权限；不要使用管理员账号或复用超级管理员密码。
          </div>
        </el-form-item>
        <el-form-item label="说明"><el-input v-model="form.description" maxlength="500" placeholder="可选，例如：只读运维账号" /></el-form-item>
        <el-form-item label="关联资产">
          <el-select v-model="form.asset_ids" multiple filterable clearable collapse-tags collapse-tags-tooltip
            :loading="assetLoading" placeholder="选择使用该凭据的资产" style="width: 100%">
            <el-option v-for="asset in assets" :key="asset.id" :label="`${asset.name} · ${asset.ip_address}`" :value="asset.id" />
          </el-select>
          <div class="form-tip">关联后，设备巡检和设备配置备份会自动复用该凭据；一个资产只能关联一个凭据。</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { assetApi, credentialApi } from '@/api'
import { can, downloadWithAuth } from '@/store/auth'

const canEdit = computed(() => can('credentials:edit'))
const loading = ref(false)
const saving = ref(false)
const credentials = ref([])
const assets = ref([])
const assetLoading = ref(false)
const dialogVisible = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const keyword = ref('')
const selectedIds = ref([])
const importVisible = ref(false)
const importLoading = ref(false)
const importMode = ref('skip')
const importFile = ref(null)
const importResult = ref(null)
const form = reactive({ id: null, name: '', username: '', password: '', port: 22, description: '', asset_ids: [], password_set: false })

async function loadCredentials(targetPage = page.value) {
  loading.value = true
  page.value = Math.max(1, Number(targetPage) || 1)
  try {
    const res = await credentialApi.list({ page: page.value, size: pageSize.value, keyword: keyword.value.trim() || undefined })
    credentials.value = res.data?.items || []
    total.value = Number(res.data?.total || 0)
    selectedIds.value = []
    if (!credentials.value.length && total.value > 0 && page.value > 1) {
      page.value -= 1
      await loadCredentials(page.value)
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '加载设备凭据失败')
  } finally {
    loading.value = false
  }
}

function onPageSizeChange() {
  page.value = 1
  loadCredentials(1)
}

function onSelectionChange(rows) {
  selectedIds.value = (rows || []).map((row) => row.id)
}

function openImport() {
  importVisible.value = true
  importFile.value = null
  importMode.value = 'skip'
  importResult.value = null
}

function onImportFileChange(uploadFile) {
  importFile.value = uploadFile?.raw || null
  importResult.value = null
}

async function submitImport() {
  if (!importFile.value) return ElMessage.warning('请选择导入文件')
  importLoading.value = true
  try {
    const formData = new FormData()
    formData.append('file', importFile.value)
    formData.append('mode', importMode.value)
    const res = await credentialApi.importCredentials(formData)
    importResult.value = res.data
    ElMessage.success(res.data?.message || '导入完成')
    await loadCredentials(1)
    await loadAssets()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '批量导入失败')
  } finally {
    importLoading.value = false
  }
}

async function batchDelete() {
  if (!selectedIds.value.length) return
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selectedIds.value.length} 个凭据吗？关联资产会保留。`, '批量删除设备凭据', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
    await credentialApi.batchDelete(selectedIds.value)
    ElMessage.success('批量删除完成')
    await loadCredentials(page.value)
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(error?.response?.data?.detail || error.message || '批量删除失败')
  }
}

async function exportCredentials(command) {
  const includePassword = command === 'password'
  if (includePassword) {
    try {
      await ElMessageBox.confirm(
        '导出的 Excel 将包含 SSH 明文密码，请仅在受控环境中保存和传输，使用后及时删除。',
        '导出明文密码',
        { type: 'warning', confirmButtonText: '继续导出', cancelButtonText: '取消' },
      )
    } catch {
      return
    }
  }
  const params = { include_password: includePassword }
  if (selectedIds.value.length) params.ids = selectedIds.value.join(',')
  downloadWithAuth(credentialApi.exportUrl(params))
}

async function loadAssets() {
  assetLoading.value = true
  try {
    // 资产接口单页最多 100 条，逐页加载避免只显示前 100 台。
    const all = []
    let page = 1
    let total = 0
    do {
      const res = await assetApi.getList({ page, size: 100 })
      const items = res.data?.items || []
      all.push(...items)
      total = Number(res.data?.total || all.length)
      if (!items.length) break
      page += 1
    } while (all.length < total && page <= 20)
    assets.value = all
  } catch {
    assets.value = []
  } finally {
    assetLoading.value = false
  }
}

function resetForm() {
  Object.assign(form, { id: null, name: '', username: '', password: '', port: 22, description: '', asset_ids: [], password_set: false })
}

function openCreate() {
  resetForm()
  dialogVisible.value = true
}

function openEdit(row) {
  Object.assign(form, {
    id: row.id, name: row.name || '', username: row.username || '', password: '', port: row.port || 22,
    description: row.description || '', asset_ids: [...(row.asset_ids || [])], password_set: !!row.password_set,
  })
  dialogVisible.value = true
}

async function save() {
  if (!form.name.trim()) return ElMessage.warning('请填写凭据名称')
  if (!form.username.trim()) return ElMessage.warning('请填写 SSH 用户名')
  saving.value = true
  try {
    const payload = { name: form.name.trim(), username: form.username.trim(), port: Number(form.port) || 22, description: form.description.trim(), asset_ids: form.asset_ids }
    if (form.password) payload.password = form.password
    if (form.id) {
      await credentialApi.update(form.id, payload)
      ElMessage.success('设备凭据已保存')
    } else {
      if (!form.password) { ElMessage.warning('请填写 SSH 密码'); return }
      await credentialApi.create(payload)
      ElMessage.success('设备凭据已创建')
    }
    dialogVisible.value = false
    await loadCredentials()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '保存设备凭据失败')
  } finally {
    saving.value = false
  }
}

async function removeCredential(row) {
  try {
    await ElMessageBox.confirm(`确定删除凭据「${row.name}」吗？关联资产会保留，但会解除凭据关联。`, '删除设备凭据', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
    await credentialApi.remove(row.id)
    ElMessage.success('设备凭据已删除')
    await loadCredentials()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(error?.response?.data?.detail || error.message || '删除失败')
  }
}

onMounted(() => { loadCredentials(); loadAssets() })
</script>

<style scoped>
.credential-view { padding: 16px; }
.credential-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 12px; }
.credential-head h2 { margin: 0 0 6px; color: #1f3a52; font-size: 18px; }
.credential-head p { margin: 0; color: #7b91a3; font-size: 12px; line-height: 1.7; }
.credential-alert { margin-bottom: 14px; }
.asset-tags { display: flex; flex-wrap: wrap; gap: 5px; }
.asset-ip { color: #8ba0af; font-family: Consolas, monospace; font-size: 10px; }
.muted { color: #9aaaba; font-size: 12px; }
.form-tip { width: 100%; margin-top: 5px; color: #8ba0af; font-size: 11px; line-height: 1.5; }
.credential-security-tip { color: #b45309; }
.credential-actions { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; justify-content: flex-end; }
.credential-batch-bar { display: flex; align-items: center; gap: 8px; margin: 0 0 9px; padding: 7px 10px; border: 1px solid #d7e7f4; border-radius: 7px; background: #f4faff; color: #587286; font-size: 12px; }
.credential-batch-bar b { color: #0f6fae; }
.credential-pager { display: flex; justify-content: flex-end; padding-top: 12px; }
.import-errors { max-height: 180px; overflow: auto; margin-top: 8px; padding: 8px 10px; border-radius: 6px; background: #fff8ed; color: #9a5b18; font-size: 11px; line-height: 1.7; }
@media (max-width: 760px) { .credential-head { flex-direction: column; } .credential-actions { justify-content: flex-start; } }
</style>
