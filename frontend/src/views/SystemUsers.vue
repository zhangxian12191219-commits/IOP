<template>
  <div class="system-users" :class="{ embedded }">
    <el-card>
      <template #header>
        <div class="card-header">
          <div class="title">
            <span>{{ t('users.title') }}</span>
            <el-tag size="small" type="info" effect="plain">{{ t('users.userCountLabel', { count: users.length }) }}</el-tag>
            <el-tag size="small" type="info" effect="plain">{{ t('users.roleCountLabel', { count: roles.length }) }}</el-tag>
            <el-tag size="small" type="info" effect="plain">{{ t('users.groupCountLabel', { count: groups.length }) }}</el-tag>
          </div>
          <div class="actions">
            <el-button size="small" @click="loadAll" :loading="loading">
              <el-icon><Refresh /></el-icon>{{ t('common.refresh') }}
            </el-button>
            <el-button
              v-if="canEdit"
              type="primary"
              size="small"
              @click="openCreate(activeTab)"
            >
              <el-icon><Plus /></el-icon>
              {{ t('users.addTab', { tab: tabName(activeTab) }) }}
            </el-button>
          </div>
        </div>
      </template>

      <el-tabs v-model="activeTab">
        <!-- ==================== 用户 ==================== -->
        <el-tab-pane :label="t('users.user')" name="users">
          <div class="filters">
            <el-input
              v-model="userKeyword"
              :placeholder="t('users.searchUserPlaceholder')"
              clearable
              style="width: 240px"
              @keyup.enter="loadUsers"
              @clear="loadUsers"
            >
              <template #prefix><el-icon><Search /></el-icon></template>
            </el-input>
            <el-select v-model="filterGroup" :placeholder="t('users.filterByGroup')" clearable style="width: 170px" @change="loadUsers">
              <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
            </el-select>
            <el-select v-model="filterRole" :placeholder="t('users.filterByRole')" clearable style="width: 170px" @change="loadUsers">
              <el-option v-for="r in roles" :key="r.id" :label="r.name" :value="r.id" />
            </el-select>
          </div>

          <el-table :data="users" v-loading="loading" stripe>
            <el-table-column prop="username" :label="t('users.username')" :width="isCompact ? 120 : 140" />
            <el-table-column prop="real_name" :label="t('users.fullName')" :width="isCompact ? 100 : 120">
              <template #default="{ row }">{{ row.real_name || '-' }}</template>
            </el-table-column>
            <el-table-column :label="t('users.role')" :min-width="isCompact ? 150 : 180">
              <template #default="{ row }">
                <el-tag v-for="r in row.roles" :key="r.id" size="small" class="tag-gap" type="info">
                  {{ r.name }}
                </el-tag>
                <span v-if="!row.roles?.length" class="muted">{{ t('users.unassigned') }}</span>
              </template>
            </el-table-column>
            <el-table-column v-if="!isTablet" :label="t('users.group')" min-width="160">
              <template #default="{ row }">
                <el-tag v-for="g in row.groups" :key="g.id" size="small" class="tag-gap">
                  {{ g.name }}
                </el-tag>
                <span v-if="!row.groups?.length" class="muted">-</span>
              </template>
            </el-table-column>
            <el-table-column v-if="!isTablet" :label="t('users.superAdmin')" width="110">
              <template #default="{ row }">
                <el-tag v-if="row.is_superuser" type="danger" size="small">{{ t('users.yes') }}</el-tag>
                <span v-else class="muted">{{ t('users.no') }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="t('users.status')" width="85">
              <template #default="{ row }">
                <el-switch
                  :model-value="row.is_active"
                  :disabled="!canEdit"
                  @change="(v) => toggleUser(row, v)"
                />
              </template>
            </el-table-column>
            <el-table-column v-if="!isCompact" :label="t('users.lastLogin')" width="170">
              <template #default="{ row }">
                {{ row.last_login ? formatDateTime(row.last_login) : t('users.neverLoggedIn') }}
              </template>
            </el-table-column>
            <el-table-column :label="t('users.actions')" :width="isCompact ? 170 : 210" fixed="right">
              <template #default="{ row }">
                <el-button type="primary" link size="small" :disabled="!canEdit" @click="openUserEdit(row)">
                  {{ t('users.edit') }}
                </el-button>
                <el-button type="primary" link size="small" :disabled="!canEdit" @click="openResetPassword(row)">
                  {{ t('users.resetPassword') }}
                </el-button>
                <el-button type="danger" link size="small" :disabled="!canEdit" @click="removeUser(row)">
                  {{ t('users.delete') }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- ==================== 角色 ==================== -->
        <el-tab-pane :label="t('users.role')" name="roles">
          <el-table :data="roles" v-loading="loading" stripe>
            <el-table-column prop="name" :label="t('users.roleName')" width="160" />
            <el-table-column prop="code" :label="t('users.identifier')" :width="isCompact ? 110 : 130">
              <template #default="{ row }">{{ row.code || '-' }}</template>
            </el-table-column>
            <el-table-column v-if="!isCompact" prop="description" :label="t('users.description')" min-width="220" show-overflow-tooltip />
            <el-table-column v-if="!isCompact" :label="t('users.permissions')" width="110">
              <template #default="{ row }">
                <el-tag v-if="row.permissions?.includes('*')" type="danger" size="small">
                  {{ t('users.allPermissions') }}
                </el-tag>
                <span v-else>{{ t('users.permissionCount', { count: row.permissions?.length || 0 }) }}</span>
              </template>
            </el-table-column>
            <el-table-column v-if="!isCompact" prop="user_count" :label="t('users.userCount')" width="90" />
            <el-table-column v-if="!isTablet" :label="t('users.type')" width="90">
              <template #default="{ row }">
                <el-tag :type="row.is_builtin ? 'warning' : 'info'" size="small">
                  {{ row.is_builtin ? t('users.builtIn') : t('users.custom') }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="t('users.actions')" :width="isCompact ? 140 : 150" fixed="right">
              <template #default="{ row }">
                <el-button type="primary" link size="small" :disabled="!canEdit" @click="openRoleEdit(row)">
                  {{ t('users.edit') }}
                </el-button>
                <el-button
                  type="danger"
                  link
                  size="small"
                  :disabled="!canEdit || row.is_builtin"
                  @click="removeRole(row)"
                >
                  {{ t('users.delete') }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- ==================== 群组 ==================== -->
        <el-tab-pane :label="t('users.group')" name="groups">
          <el-table :data="groups" v-loading="loading" stripe>
            <el-table-column prop="name" :label="t('users.groupName')" :width="isCompact ? 150 : 180" />
            <el-table-column prop="code" :label="t('users.identifier')" :width="isCompact ? 120 : 150">
              <template #default="{ row }">{{ row.code || '-' }}</template>
            </el-table-column>
            <el-table-column v-if="!isCompact" prop="description" :label="t('users.description')" min-width="260" show-overflow-tooltip />
            <el-table-column prop="user_count" :label="t('users.userCount')" :width="isCompact ? 90 : 100" />
            <el-table-column :label="t('users.actions')" :width="isCompact ? 120 : 150" fixed="right">
              <template #default="{ row }">
                <el-button type="primary" link size="small" :disabled="!canEdit" @click="openGroupEdit(row)">
                  {{ t('users.edit') }}
                </el-button>
                <el-button type="danger" link size="small" :disabled="!canEdit" @click="removeGroup(row)">
                  {{ t('users.delete') }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- ==================== 用户表单 ==================== -->
    <el-dialog v-model="userDialog" :title="editingUser ? t('users.editUser') : t('users.addUser')" width="620px">
      <el-form :model="userForm" label-width="110px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="t('users.username')" required>
              <el-input v-model="userForm.username" :disabled="!!editingUser" :placeholder="t('users.loginName')" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('users.fullName')">
              <el-input v-model="userForm.real_name" :placeholder="t('users.displayName')" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="editingUser ? t('users.newPassword') : t('users.password')" :required="!editingUser">
              <el-input
                v-model="userForm.password"
                type="password"
                show-password
                :placeholder="editingUser ? t('users.leaveBlankKeep') : t('users.atLeastChars', { n: passwordMin })"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('users.phone')">
              <el-input v-model="userForm.phone" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item :label="t('users.role')">
          <el-select v-model="userForm.role_ids" multiple :placeholder="t('users.selectRole')" style="width: 100%">
            <el-option v-for="r in roles" :key="r.id" :label="r.name" :value="r.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('users.group')">
          <el-select v-model="userForm.group_ids" multiple :placeholder="t('users.selectGroup')" style="width: 100%">
            <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
          </el-select>
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="t('users.enableAccount')">
              <el-switch v-model="userForm.is_active" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('users.superAdmin')">
              <el-switch v-model="userForm.is_superuser" :disabled="!isSuperuser" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="userDialog = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="saving" @click="saveUser">{{ t('common.save') }}</el-button>
      </template>
    </el-dialog>

    <!-- ==================== 角色表单 ==================== -->
    <el-dialog v-model="roleDialog" :title="editingRole ? t('users.editRole') : t('users.addRole')" width="980px" :close-on-click-modal="false" class="role-dialog">
      <el-form :model="roleForm" label-width="100px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="t('users.roleName')" required>
              <el-input v-model="roleForm.name" :disabled="editingRole?.is_builtin && editingRole?.code === 'admin'" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('users.identifier')">
              <el-input v-model="roleForm.code" :disabled="editingRole?.is_builtin" :placeholder="t('users.roleCodePlaceholder')" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item :label="t('users.description')">
          <el-input v-model="roleForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item :label="t('users.permissions')" class="perm-form-item">
          <div class="perm-shell">
            <div class="perm-toolbar">
              <el-input v-model="permissionSearch" clearable :placeholder="t('users.permissionSearchPlaceholder')" class="perm-search" />
              <span class="perm-selected">
                {{ t('users.permissionSelected', { count: selectedPermissionCount, total: allPermissionCodes.length }) }}
              </span>
              <el-button size="small" @click="selectAllPermissions">{{ t('users.permissionSelectAll') }}</el-button>
              <el-button size="small" @click="clearAllPermissions">{{ t('users.permissionClear') }}</el-button>
            </div>

            <el-checkbox
              :model-value="roleForm.permissions.includes('*')"
              :disabled="editingRole?.code === 'admin'"
              class="perm-all"
              @change="(v) => toggleAllPerms(v)"
            >
              {{ t('users.allPermissionsSuper') }}
              <small class="perm-all-tip">{{ t('users.permissionSuperTip') }}</small>
            </el-checkbox>

            <div v-if="filteredPermissionGroups.length" class="perm-grid">
              <section v-for="groupItem in filteredPermissionGroups" :key="groupItem.module" class="perm-card">
                <header class="perm-card-head">
                  <div>
                    <b>{{ groupItem.module }}</b>
                    <small>{{ moduleSelectedCount(groupItem) }} / {{ groupItem.permissions.length }}</small>
                  </div>
                  <el-button size="small" link :disabled="roleForm.permissions.includes('*')" @click="toggleModulePermissions(groupItem)">
                    {{ isModuleAllSelected(groupItem) ? t('users.permissionClearModule') : t('users.permissionSelectModule') }}
                  </el-button>
                </header>
                <el-checkbox-group v-model="roleForm.permissions" :disabled="roleForm.permissions.includes('*')" class="perm-list">
                  <el-checkbox v-for="p in groupItem.permissions" :key="p.code" :label="p.code" :value="p.code" class="perm-item">
                    <span class="perm-name">{{ p.name }}</span>
                    <small v-if="p.description" class="perm-desc">{{ p.description }}</small>
                  </el-checkbox>
                </el-checkbox-group>
              </section>
            </div>
            <el-empty v-else :description="t('users.permissionNoMatch')" :image-size="60" />
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="roleDialog = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="saving" @click="saveRole">{{ t('common.save') }}</el-button>
      </template>
    </el-dialog>

    <!-- ==================== 群组表单 ==================== -->
    <el-dialog v-model="groupDialog" :title="editingGroup ? t('users.editGroup') : t('users.addGroup')" width="520px">
      <el-form :model="groupForm" label-width="100px">
        <el-form-item :label="t('users.groupName')" required>
          <el-input v-model="groupForm.name" :placeholder="t('users.groupNamePlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('users.identifier')">
          <el-input v-model="groupForm.code" :placeholder="t('users.groupCodePlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('users.description')">
          <el-input v-model="groupForm.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="groupDialog = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="saving" @click="saveGroup">{{ t('common.save') }}</el-button>
      </template>
    </el-dialog>

    <!-- ==================== 重置密码 ==================== -->
    <el-dialog v-model="passwordDialog" :title="t('users.resetUserPassword')" width="460px">
      <el-form label-width="100px">
        <el-form-item :label="t('users.user')">
          <span>{{ resetTarget?.username }}</span>
        </el-form-item>
        <el-form-item :label="t('users.newPassword')" required>
          <el-input v-model="newPassword" type="password" show-password :placeholder="t('users.atLeastChars', { n: passwordMin })" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="passwordDialog = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="saving" @click="submitResetPassword">{{ t('common.confirm') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { t } from '@/i18n'
import { settings } from '@/store/settings'
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { userApi, roleApi, groupApi } from '@/api'
import { can, currentUser } from '@/store/auth'
import { formatDateTime } from '@/utils/time'
import { useResponsiveViewport } from '@/composables/useResponsiveViewport'

const { isTablet, isCompact } = useResponsiveViewport()

defineProps({
  embedded: { type: Boolean, default: false },
})

const activeTab = ref('users')
const loading = ref(false)
const saving = ref(false)
const passwordMin = computed(() => Number(settings.password_min_length) || 8)

const users = ref([])
const roles = ref([])
const groups = ref([])
const permissionGroups = ref([])
const permissionSearch = ref('')

const allPermissionCodes = computed(() => permissionGroups.value.flatMap((group) => (group.permissions || []).map((p) => p.code)))
const allPermissionCodeSet = computed(() => new Set(allPermissionCodes.value))
const selectedPermissionCount = computed(() => {
  if (roleForm.permissions.includes('*')) return allPermissionCodes.value.length
  return new Set(roleForm.permissions.filter((code) => allPermissionCodeSet.value.has(code))).size
})
const filteredPermissionGroups = computed(() => {
  const keyword = permissionSearch.value.trim().toLowerCase()
  return permissionGroups.value
    .map((group) => ({
      ...group,
      permissions: (group.permissions || []).filter((p) => !keyword
        || String(p.name || '').toLowerCase().includes(keyword)
        || String(p.code || '').toLowerCase().includes(keyword)
        || String(p.description || '').toLowerCase().includes(keyword)),
    }))
    .filter((group) => group.permissions.length)
})

const userKeyword = ref('')
const filterGroup = ref('')
const filterRole = ref('')

const canEdit = computed(() => can('users:edit'))
const isSuperuser = computed(() => !!currentUser.value?.is_superuser)

const tabName = (tab) => ({ users: t('users.user'), roles: t('users.role'), groups: t('users.group') }[tab] || '')

// ---------- 用户表单 ----------
const userDialog = ref(false)
const editingUser = ref(null)
const userForm = reactive({
  username: '',
  password: '',
  real_name: '',
  phone: '',
  is_active: true,
  is_superuser: false,
  role_ids: [],
  group_ids: [],
})

// ---------- 角色表单 ----------
const roleDialog = ref(false)
const editingRole = ref(null)
const roleForm = reactive({
  name: '',
  code: '',
  description: '',
  permissions: [],
})

// ---------- 群组表单 ----------
const groupDialog = ref(false)
const editingGroup = ref(null)
const groupForm = reactive({ name: '', code: '', description: '' })

// ---------- 重置密码 ----------
const passwordDialog = ref(false)
const resetTarget = ref(null)
const newPassword = ref('')

// ==================== 加载 ====================
async function loadUsers() {
  const params = {}
  if (userKeyword.value) params.keyword = userKeyword.value
  if (filterGroup.value) params.group_id = filterGroup.value
  if (filterRole.value) params.role_id = filterRole.value
  const res = await userApi.list(params)
  users.value = res.data.items
}

async function loadRoles() {
  const res = await roleApi.list()
  roles.value = res.data.items
}

async function loadGroups() {
  const res = await groupApi.list()
  groups.value = res.data.items
}

async function loadPermissions() {
  const res = await userApi.permissions()
  permissionGroups.value = res.data.grouped
}

async function loadAll() {
  loading.value = true
  try {
    await Promise.all([loadUsers(), loadRoles(), loadGroups(), loadPermissions()])
  } catch (e) {
    ElMessage.error(e.message || t('users.loadUsersFailed'))
  } finally {
    loading.value = false
  }
}

// ==================== 用户操作 ====================
function openCreate(tab) {
  if (tab === 'users') openUserCreate()
  else if (tab === 'roles') openRoleCreate()
  else openGroupCreate()
}

function openUserCreate() {
  editingUser.value = null
  Object.assign(userForm, {
    username: '', password: '', real_name: '', phone: '',
    is_active: true, is_superuser: false, role_ids: [], group_ids: [],
  })
  userDialog.value = true
}

function openUserEdit(row) {
  editingUser.value = row
  Object.assign(userForm, {
    username: row.username,
    password: '',
    real_name: row.real_name || '',
    phone: row.phone || '',
    is_active: row.is_active,
    is_superuser: row.is_superuser,
    role_ids: [...(row.role_ids || [])],
    group_ids: [...(row.group_ids || [])],
  })
  userDialog.value = true
}

async function saveUser() {
  if (!userForm.username.trim()) {
    ElMessage.warning(t('users.usernameRequired'))
    return
  }
  if (!editingUser.value && !userForm.password) {
    ElMessage.warning(t('users.passwordRequired'))
    return
  }
  if (!editingUser.value && userForm.password.length < passwordMin.value) {
    ElMessage.warning(t('users.passwordMinDynamic', { n: passwordMin.value }))
    return
  }
  saving.value = true
  try {
    if (editingUser.value) {
      const payload = {
        real_name: userForm.real_name || null,
        phone: userForm.phone || null,
        is_active: userForm.is_active,
        is_superuser: userForm.is_superuser,
        role_ids: userForm.role_ids,
        group_ids: userForm.group_ids,
      }
      if (userForm.password) payload.password = userForm.password
      await userApi.update(editingUser.value.id, payload)
      ElMessage.success(t('users.userUpdated'))
    } else {
      await userApi.create({ ...userForm, username: userForm.username.trim() })
      ElMessage.success(t('users.userCreated'))
    }
    userDialog.value = false
    await loadAll()
  } catch (e) {
    ElMessage.error(e.message || t('users.saveFailed'))
  } finally {
    saving.value = false
  }
}

async function toggleUser(row, value) {
  try {
    await userApi.update(row.id, { is_active: value })
    row.is_active = value
    ElMessage.success(value ? t('users.accountEnabled') : t('users.accountDisabled'))
  } catch (e) {
    ElMessage.error(e.message || t('users.operationFailed'))
  }
}

function openResetPassword(row) {
  resetTarget.value = row
  newPassword.value = ''
  passwordDialog.value = true
}

async function submitResetPassword() {
  if (!newPassword.value) {
    ElMessage.warning(t('users.passwordRequired'))
    return
  }
  if (newPassword.value.length < passwordMin.value) {
    ElMessage.warning(t('users.passwordMinDynamic', { n: passwordMin.value }))
    return
  }
  saving.value = true
  try {
    await userApi.resetPassword(resetTarget.value.id, newPassword.value)
    ElMessage.success(t('users.passwordReset'))
    passwordDialog.value = false
  } catch (e) {
    ElMessage.error(e.message || t('users.resetFailed'))
  } finally {
    saving.value = false
  }
}

async function removeUser(row) {
  try {
    await ElMessageBox.confirm(t('users.confirmDeleteUser', { username: row.username }), t('users.confirmDelete'), { type: 'warning' })
    await userApi.remove(row.id)
    ElMessage.success(t('users.userDeleted'))
    await loadAll()
  } catch {
    /* 取消 */
  }
}

// ==================== 角色操作 ====================
function moduleSelectedCount(group) {
  if (roleForm.permissions.includes('*')) return group.permissions.length
  return group.permissions.filter((p) => roleForm.permissions.includes(p.code)).length
}

function isModuleAllSelected(group) {
  return roleForm.permissions.includes('*') || group.permissions.every((p) => roleForm.permissions.includes(p.code))
}

function toggleModulePermissions(group) {
  if (roleForm.permissions.includes('*')) return
  const codes = group.permissions.map((p) => p.code)
  const selected = new Set(roleForm.permissions)
  if (codes.every((code) => selected.has(code))) codes.forEach((code) => selected.delete(code))
  else codes.forEach((code) => selected.add(code))
  roleForm.permissions = [...selected]
}

function selectAllPermissions() {
  roleForm.permissions = [...allPermissionCodes.value]
}

function clearAllPermissions() {
  roleForm.permissions = []
}

function openRoleCreate() {
  editingRole.value = null
  permissionSearch.value = ''
  loadPermissions().catch(() => {})
  Object.assign(roleForm, { name: '', code: '', description: '', permissions: [] })
  roleDialog.value = true
}

function openRoleEdit(row) {
  editingRole.value = row
  permissionSearch.value = ''
  loadPermissions().catch(() => {})
  Object.assign(roleForm, {
    name: row.name,
    code: row.code || '',
    description: row.description || '',
    permissions: [...(row.permissions || [])],
  })
  roleDialog.value = true
}

function toggleAllPerms(checked) {
  roleForm.permissions = checked ? ['*'] : []
}

async function saveRole() {
  if (!roleForm.name.trim()) {
    ElMessage.warning(t('users.roleNameRequired'))
    return
  }
  saving.value = true
  try {
    const payload = {
      name: roleForm.name.trim(),
      code: roleForm.code || null,
      description: roleForm.description || null,
      permissions: roleForm.permissions,
    }
    if (editingRole.value) {
      await roleApi.update(editingRole.value.id, payload)
      ElMessage.success(t('users.roleUpdated'))
    } else {
      await roleApi.create(payload)
      ElMessage.success(t('users.roleCreated'))
    }
    roleDialog.value = false
    await loadAll()
  } catch (e) {
    ElMessage.error(e.message || t('users.saveFailed'))
  } finally {
    saving.value = false
  }
}

async function removeRole(row) {
  try {
    await ElMessageBox.confirm(t('users.confirmDeleteRole', { name: row.name }), t('users.confirmDelete'), { type: 'warning' })
    await roleApi.remove(row.id)
    ElMessage.success(t('users.roleDeleted'))
    await loadAll()
  } catch {
    /* 取消 */
  }
}

// ==================== 群组操作 ====================
function openGroupCreate() {
  editingGroup.value = null
  Object.assign(groupForm, { name: '', code: '', description: '' })
  groupDialog.value = true
}

function openGroupEdit(row) {
  editingGroup.value = row
  Object.assign(groupForm, {
    name: row.name,
    code: row.code || '',
    description: row.description || '',
  })
  groupDialog.value = true
}

async function saveGroup() {
  if (!groupForm.name.trim()) {
    ElMessage.warning(t('users.groupNameRequired'))
    return
  }
  saving.value = true
  try {
    const payload = {
      name: groupForm.name.trim(),
      code: groupForm.code || null,
      description: groupForm.description || null,
    }
    if (editingGroup.value) {
      await groupApi.update(editingGroup.value.id, payload)
      ElMessage.success(t('users.groupUpdated'))
    } else {
      await groupApi.create(payload)
      ElMessage.success(t('users.groupCreated'))
    }
    groupDialog.value = false
    await loadAll()
  } catch (e) {
    ElMessage.error(e.message || t('users.saveFailed'))
  } finally {
    saving.value = false
  }
}

async function removeGroup(row) {
  try {
    await ElMessageBox.confirm(t('users.confirmDeleteGroup', { name: row.name }), t('users.confirmDelete'), { type: 'warning' })
    await groupApi.remove(row.id)
    ElMessage.success(t('users.groupDeleted'))
    await loadAll()
  } catch {
    /* 取消 */
  }
}

onMounted(loadAll)
</script>

<style scoped>
.system-users {
  height: 100%;
}

.system-users.embedded {
  height: auto;
}

.system-users.embedded :deep(.el-card) {
  border: 0;
  box-shadow: none;
}

.system-users.embedded :deep(.el-card__body) {
  padding: 0;
}

.system-users.embedded :deep(.el-card__header) {
  padding: 8px 0 12px;
  border-bottom: 1px solid #edf1f5;
}

.system-users.embedded :deep(.card-header .title) {
  display: none;
}

.system-users.embedded :deep(.card-header) {
  justify-content: flex-end;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.actions {
  display: flex;
  gap: 8px;
}

.filters {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.tag-gap {
  margin-right: 4px;
  margin-bottom: 2px;
}

.muted {
  color: #c0c4cc;
}

.perm-form-item :deep(.el-form-item__content) {
  min-width: 0;
}

.perm-shell {
  width: 100%;
  min-width: 0;
  padding: 12px;
  border: 1px solid #e4e9f0;
  border-radius: 10px;
  background: #fafcff;
}

.perm-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.perm-search {
  width: 260px;
}

.perm-selected {
  margin-left: auto;
  color: #606266;
  font-size: 12px;
}

.perm-all {
  display: flex;
  align-items: center;
  width: 100%;
  margin: 0 0 10px;
  padding: 8px 10px;
  border: 1px solid #f3d19e;
  border-radius: 8px;
  background: #fdf6ec;
}

.perm-all-tip {
  margin-left: 8px;
  color: #b88230;
  font-size: 11px;
  font-weight: 400;
}

.perm-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  max-height: 52vh;
  overflow-y: auto;
  padding-right: 4px;
}

.perm-card {
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid #e9edf4;
  border-radius: 9px;
  background: #fff;
}

.perm-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-bottom: 7px;
  margin-bottom: 4px;
  border-bottom: 1px dashed #edf0f5;
}

.perm-card-head b {
  font-size: 13px;
  color: #303133;
}

.perm-card-head small {
  margin-left: 6px;
  color: #909399;
  font-size: 11px;
}

.perm-list {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 2px;
}

.perm-item {
  display: flex;
  align-items: flex-start;
  height: auto;
  min-height: 30px;
  margin-right: 0;
  padding: 3px 0;
}

.perm-item :deep(.el-checkbox__input) {
  margin-top: 4px;
}

.perm-item :deep(.el-checkbox__label) {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  white-space: normal;
  line-height: 1.35;
}

.perm-name {
  color: #303133;
  font-size: 12px;
}

.perm-desc {
  color: #909399;
  font-size: 11px;
  font-weight: 400;
}

@media (max-width: 900px) {
  .perm-grid {
    grid-template-columns: 1fr;
  }
  .perm-search {
    width: 100%;
  }
  .perm-selected {
    margin-left: 0;
  }
}
</style>
