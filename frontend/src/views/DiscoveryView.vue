<template>
  <div class="discovery-view">
    <el-card class="discovery-card">
      <template #header>
        <div class="discovery-header">
          <div>
            <div class="discovery-title">
              <span class="title-icon"><el-icon><Aim /></el-icon></span>
              自动发现
            </div>
            <div class="discovery-sub">即时扫描或按计划循环扫描网段，自动识别 SNMP 设备并入库；也可快速探测 IP 存活状态</div>
          </div>
          <div class="header-badges">
            <span><i class="dot cyan"></i>SNMP v1 / v2c / v3</span>
            <span><i class="dot green"></i>即时扫描 / 定时扫描</span>
          </div>
        </div>
      </template>

      <el-alert
        v-if="!canEdit"
        type="warning"
        :closable="false"
        show-icon
        title="当前账号只有查看权限，扫描和探测按钮已禁用"
        class="permission-alert"
      />
      <el-tabs v-model="activeTab" class="discovery-tabs">
        <el-tab-pane name="snmp">
          <template #label>
            <span class="tab-label"><el-icon><Connection /></el-icon>即时扫描</span>
          </template>

          <div class="scan-intro">
            <div>
              <strong>按网段即时发现 SNMP 资产</strong>
              <p>一次性扫描，读取 sysName / sysDescr / sysLocation，自动识别厂商与设备类型，可直接加入资产库。</p>
            </div>
            <el-tag type="info" effect="plain">单次最多 512 个地址</el-tag>
          </div>

          <el-form :model="snmpForm" label-position="top" class="scan-form">
            <div class="form-grid">
              <el-form-item label="扫描范围" class="span-2">
                <el-input
                  v-model="snmpForm.target"
                  clearable
                  placeholder="例如 192.168.1.0/24，或 192.168.1.10-192.168.1.200"
                >
                  <template #prefix><el-icon><Search /></el-icon></template>
                </el-input>
                <div class="field-tip">支持 CIDR、起止 IP、末段简写（192.168.1.10-200）及逗号分隔</div>
              </el-form-item>
              <el-form-item label="SNMP 版本">
                <el-select v-model="snmpForm.version" style="width: 100%">
                  <el-option label="SNMP v2c（常用）" value="v2c" />
                  <el-option label="SNMP v1" value="v1" />
                  <el-option label="SNMP v3" value="v3" />
                </el-select>
              </el-form-item>
              <el-form-item label="端口">
                <el-input-number v-model="snmpForm.port" :min="1" :max="65535" controls-position="right" style="width: 100%" />
              </el-form-item>
              <el-form-item label="超时（秒）">
                <el-input-number v-model="snmpForm.timeout" :min="1" :max="10" controls-position="right" style="width: 100%" />
              </el-form-item>
              <el-form-item label="并发数">
                <el-input-number v-model="snmpForm.concurrency" :min="1" :max="128" controls-position="right" style="width: 100%" />
              </el-form-item>
            </div>

            <template v-if="snmpForm.version !== 'v3'">
              <div class="form-grid compact">
                <el-form-item label="团体名">
                  <el-input v-model="snmpForm.community" placeholder="public" show-password />
                </el-form-item>
              </div>
            </template>
            <template v-else>
              <div class="form-grid v3-grid">
                <el-form-item label="v3 用户名">
                  <el-input v-model="snmpForm.v3_username" placeholder="安全名 / 用户名" />
                </el-form-item>
                <el-form-item label="安全级别">
                  <el-select v-model="snmpForm.v3_security_level" style="width: 100%">
                    <el-option label="authPriv（认证+加密）" value="authPriv" />
                    <el-option label="authNoPriv（仅认证）" value="authNoPriv" />
                    <el-option label="noAuthNoPriv（不认证）" value="noAuthNoPriv" />
                  </el-select>
                </el-form-item>
                <el-form-item label="认证协议">
                  <el-select v-model="snmpForm.v3_auth_protocol" style="width: 100%">
                    <el-option v-for="item in ['SHA', 'SHA224', 'SHA256', 'SHA384', 'SHA512', 'MD5']" :key="item" :label="item" :value="item" />
                  </el-select>
                </el-form-item>
                <el-form-item label="认证密码">
                  <el-input v-model="snmpForm.v3_auth_password" show-password />
                </el-form-item>
                <el-form-item label="加密协议">
                  <el-select v-model="snmpForm.v3_priv_protocol" style="width: 100%">
                    <el-option v-for="item in ['AES', 'AES192', 'AES256', 'DES']" :key="item" :label="item" :value="item" />
                  </el-select>
                </el-form-item>
                <el-form-item label="加密密码">
                  <el-input v-model="snmpForm.v3_priv_password" show-password />
                </el-form-item>
              </div>
            </template>

            <div class="scan-actions">
              <div class="auto-add">
                <el-switch v-model="snmpForm.auto_add" />
                <div><strong>扫描后自动添加资产</strong><small>关闭后先在结果中预览，再手动选择添加</small></div>
              </div>
              <el-button type="primary" size="large" :loading="snmpLoading" :disabled="!canEdit" @click="scanSnmp">
                <el-icon><Search /></el-icon>开始扫描
              </el-button>
            </div>
          </el-form>

          <div v-if="snmpSummary" class="summary-row">
            <div><span>扫描地址</span><b>{{ snmpSummary.total }}</b></div>
            <div class="success"><span>发现设备</span><b>{{ snmpSummary.discovered }}</b></div>
            <div class="added"><span>自动添加</span><b>{{ snmpSummary.added }}</b></div>
            <div class="muted"><span>耗时</span><b>{{ snmpSummary.duration_seconds }}s</b></div>
          </div>

          <div v-if="snmpResults.length" class="result-block">
            <div class="result-toolbar">
              <div><strong>发现结果</strong><span>{{ snmpResults.length }} 台设备</span></div>
              <el-button type="primary" plain :disabled="!selectedSnmp.length || !canEdit" :loading="addLoading" @click="addSelected">
                <el-icon><Plus /></el-icon>添加选中资产（{{ selectedSnmp.length }}）
              </el-button>
            </div>
            <el-table
              ref="snmpTableRef"
              :data="pagedSnmpResults"
              row-key="ip_address"
              size="small"
              max-height="430"
              @selection-change="selectedSnmp = $event"
            >
              <el-table-column type="selection" width="42" :selectable="(row) => !row.exists" reserve-selection />
              <el-table-column prop="ip_address" label="IP 地址" width="142">
                <template #default="{ row }"><span class="mono">{{ row.ip_address }}</span></template>
              </el-table-column>
              <el-table-column prop="name" label="设备名称" min-width="140" show-overflow-tooltip />
              <el-table-column label="设备类型" width="90">
                <template #default="{ row }"><el-tag size="small" effect="plain">{{ deviceTypeLabel(row.device_type) }}</el-tag></template>
              </el-table-column>
              <el-table-column prop="vendor" label="厂商" width="100">
                <template #default="{ row }">{{ row.vendor || '-' }}</template>
              </el-table-column>
              <el-table-column prop="sys_descr" label="系统描述" min-width="180" show-overflow-tooltip />
              <el-table-column label="延迟" width="80">
                <template #default="{ row }">{{ row.latency_ms }}ms</template>
              </el-table-column>
              <el-table-column label="状态" width="94" fixed="right">
                <template #default="{ row }">
                  <el-tag v-if="row.added" type="success" size="small">已添加</el-tag>
                  <el-tag v-else-if="row.exists" type="info" size="small">已存在</el-tag>
                  <el-tag v-else type="warning" size="small">待添加</el-tag>
                </template>
              </el-table-column>
            </el-table>
            <div class="result-pagination">
              <el-pagination
                v-model:current-page="snmpPage"
                v-model:page-size="snmpPageSize"
                :page-sizes="[20, 50, 100]"
                :total="snmpResults.length"
                layout="total, sizes, prev, pager, next, jumper"
                small
              />
            </div>
          </div>
          <el-empty v-else-if="!snmpLoading" description="输入网段后开始扫描，发现结果会显示在这里" :image-size="72" />
        </el-tab-pane>

        <el-tab-pane name="scheduled">
          <template #label>
            <span class="tab-label"><el-icon><Timer /></el-icon>定时扫描</span>
          </template>

          <div class="scan-intro schedule-intro">
            <div>
              <strong>多任务定时扫描</strong>
              <p>每个任务独立配置 IP 范围、间隔和团体名，与即时扫描互不影响；已存在的 IP 不重复添加，新资产标记为「自动发现」。</p>
            </div>
            <el-button type="primary" :disabled="!canEdit || !isSuperuser" @click="openCreateSchedule">
              <el-icon><Plus /></el-icon>新建定时任务
            </el-button>
          </div>

          <div class="schedule-task-list">
            <div class="result-toolbar">
              <div><strong>定时任务</strong><span>共 {{ scheduleTasks.length }} 个</span></div>
              <el-button size="small" :loading="scheduleLoading" @click="loadSchedules">刷新</el-button>
            </div>
            <el-table v-if="scheduleTasks.length" :data="scheduleTasks" v-loading="scheduleLoading" row-key="id" size="small">
              <el-table-column prop="name" label="任务名称" min-width="150">
                <template #default="{ row }">
                  <div class="schedule-name-cell">
                    <span>{{ row.name }}</span>
                    <el-tag :type="row.enabled ? 'success' : 'info'" size="small" effect="plain">
                      {{ row.enabled ? '已启用' : '未启用' }}
                    </el-tag>
                  </div>
                </template>
              </el-table-column>
              <el-table-column prop="target" label="扫描范围" min-width="160" show-overflow-tooltip />
              <el-table-column label="间隔" width="82">
                <template #default="{ row }">{{ row.interval_minutes }} 分钟</template>
              </el-table-column>
              <el-table-column label="凭据" width="130" show-overflow-tooltip>
                <template #default="{ row }">
                  <span v-if="row.version === 'v3'">v3 · {{ row.v3_username || '未填写' }}</span>
                  <span v-else>v2c · {{ row.communities?.length || 0 }} 个团体名</span>
                </template>
              </el-table-column>
              <el-table-column label="自动添加" width="90">
                <template #default="{ row }">
                  <el-tag :type="row.auto_add ? 'success' : 'info'" size="small" effect="plain">
                    {{ row.auto_add ? '开启' : '关闭' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="上次执行" min-width="180">
                <template #default="{ row }">
                  <div class="schedule-last-run">
                    <el-tag :type="scheduleStatusType(row.last_status)" size="small" effect="plain">
                      {{ scheduleStatusLabel(row.last_status) }}
                    </el-tag>
                    <span v-if="row.last_run_at">{{ formatDateTime(row.last_run_at) }}</span>
                    <span v-else class="muted">尚未执行</span>
                  </div>
                  <div v-if="row.last_run_at" class="schedule-result-text">
                    发现 {{ row.last_found }} 台，新增 {{ row.last_added }} 台
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="下次执行" width="160">
                <template #default="{ row }">
                  <span v-if="row.enabled && row.next_run_at">{{ formatDateTime(row.next_run_at) }}</span>
                  <span v-else class="muted">-</span>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="190" fixed="right">
                <template #default="{ row }">
                  <el-button link type="primary" size="small" :disabled="!canEdit || !isSuperuser" @click="openEditSchedule(row)">编辑</el-button>
                  <el-button
                    link
                    type="success"
                    size="small"
                    :loading="scheduleRunningId === row.id"
                    :disabled="!canEdit || !isSuperuser"
                    @click="runScheduleTask(row)"
                  >立即执行</el-button>
                  <el-button link type="danger" size="small" :disabled="!canEdit || !isSuperuser" @click="deleteScheduleTask(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-if="!scheduleLoading && !scheduleTasks.length" description="还没有定时扫描任务，点击右上角新建" :image-size="64" />          </div>

          <el-dialog
            v-model="scheduleDialogVisible"
            :title="scheduleEditingId ? `编辑定时任务 · ${scheduleForm.name}` : '新建定时任务'"
            width="860px"
            destroy-on-close
          >
            <el-form :model="scheduleForm" label-position="top" class="scan-form schedule-dialog-form">
              <div class="form-grid schedule-dialog-base">
                <el-form-item label="任务名称" class="span-2">
                  <el-input v-model="scheduleForm.name" maxlength="100" show-word-limit placeholder="例如：核心网络每日发现" />
                </el-form-item>
                <el-form-item label="扫描范围" class="span-2">
                  <el-input v-model="scheduleForm.target" clearable placeholder="例如 192.168.1.0/24，或 192.168.1.10-192.168.1.200">
                    <template #prefix><el-icon><Search /></el-icon></template>
                  </el-input>
                  <div class="field-tip">与即时扫描独立保存；支持 CIDR、起止 IP、末段简写及逗号分隔</div>
                </el-form-item>
                <el-form-item label="SNMP 版本">
                  <el-select v-model="scheduleForm.version" style="width: 100%">
                    <el-option label="SNMP v2c（常用）" value="v2c" />
                    <el-option label="SNMP v1" value="v1" />
                    <el-option label="SNMP v3" value="v3" />
                  </el-select>
                </el-form-item>
                <el-form-item label="端口">
                  <el-input-number v-model="scheduleForm.port" :min="1" :max="65535" controls-position="right" style="width: 100%" />
                </el-form-item>
                <el-form-item label="超时（秒）">
                  <el-input-number v-model="scheduleForm.timeout" :min="1" :max="10" controls-position="right" style="width: 100%" />
                </el-form-item>
                <el-form-item label="并发数">
                  <el-input-number v-model="scheduleForm.concurrency" :min="1" :max="128" controls-position="right" style="width: 100%" />
                </el-form-item>
              </div>

              <div class="schedule-dialog-options">
                <div class="schedule-option">
                  <span>扫描间隔</span>
                  <el-input-number v-model="scheduleForm.interval_minutes" :min="5" :max="1440" :step="5" controls-position="right" />
                  <span class="muted">分钟</span>
                </div>
                <div class="schedule-option">
                  <el-switch v-model="scheduleForm.enabled" />
                  <span>启用任务</span>
                </div>
                <div class="schedule-option">
                  <el-switch v-model="scheduleForm.auto_add" />
                  <span>扫描后自动添加资产</span>
                </div>
              </div>

              <template v-if="scheduleForm.version !== 'v3'">
                <el-form-item label="团体名（可配置多个）">
                  <el-select
                    v-model="scheduleForm.communities"
                    multiple
                    filterable
                    allow-create
                    default-first-option
                    :reserve-keyword="false"
                    placeholder="输入团体名后回车，可添加多个"
                    class="schedule-community-select"
                  >
                    <el-option v-for="item in scheduleCommunityOptions" :key="item" :label="item" :value="item" />
                  </el-select>
                  <div class="field-tip">按顺序尝试，最多 10 个；同一 IP 只添加一次，保存实际可用的团体名</div>
                </el-form-item>
              </template>
              <template v-else>
                <div class="form-grid v3-grid">
                  <el-form-item label="v3 用户名">
                    <el-input v-model="scheduleForm.v3_username" placeholder="安全名 / 用户名" />
                  </el-form-item>
                  <el-form-item label="安全级别">
                    <el-select v-model="scheduleForm.v3_security_level" style="width: 100%">
                      <el-option label="authPriv（认证+加密）" value="authPriv" />
                      <el-option label="authNoPriv（仅认证）" value="authNoPriv" />
                      <el-option label="noAuthNoPriv（不认证）" value="noAuthNoPriv" />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="认证协议">
                    <el-select v-model="scheduleForm.v3_auth_protocol" style="width: 100%">
                      <el-option v-for="item in ['SHA', 'SHA224', 'SHA256', 'SHA384', 'SHA512', 'MD5']" :key="item" :label="item" :value="item" />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="认证密码">
                    <el-input v-model="scheduleForm.v3_auth_password" show-password />
                  </el-form-item>
                  <el-form-item label="加密协议">
                    <el-select v-model="scheduleForm.v3_priv_protocol" style="width: 100%">
                      <el-option v-for="item in ['AES', 'AES192', 'AES256', 'DES']" :key="item" :label="item" :value="item" />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="加密密码">
                    <el-input v-model="scheduleForm.v3_priv_password" show-password />
                  </el-form-item>
                </div>
              </template>
            </el-form>
            <template #footer>
              <el-button @click="scheduleDialogVisible = false">取消</el-button>
              <el-button type="primary" :loading="scheduleSaving" @click="saveSchedule">保存</el-button>
            </template>
          </el-dialog>
        </el-tab-pane>

        <el-tab-pane name="ping">
          <template #label>
            <span class="tab-label"><el-icon><Position /></el-icon>IP 存活探测</span>
          </template>

          <div class="scan-intro ping-intro">
            <div>
              <strong>快速探测 IP 是否在线</strong>
              <p>通过 ICMP Ping 探测网段内存活地址；无 ping 命令时自动回退到常见 TCP 端口探测。</p>
            </div>
            <el-tag type="info" effect="plain">单次最多 1024 个地址</el-tag>
          </div>

          <el-form :model="pingForm" label-position="top" class="scan-form">
            <div class="form-grid">
              <el-form-item label="探测范围" class="span-2">
                <el-input v-model="pingForm.target" clearable placeholder="例如 192.168.1.0/24，或 192.168.1.1-254">
                  <template #prefix><el-icon><Search /></el-icon></template>
                </el-input>
                <div class="field-tip">支持 CIDR、起止 IP、末段简写及逗号分隔</div>
              </el-form-item>
              <el-form-item label="超时（秒）">
                <el-input-number v-model="pingForm.timeout" :min="1" :max="5" controls-position="right" style="width: 100%" />
              </el-form-item>
              <el-form-item label="并发数">
                <el-input-number v-model="pingForm.concurrency" :min="1" :max="128" controls-position="right" style="width: 100%" />
              </el-form-item>
            </div>
            <div class="scan-actions ping-actions">
              <div class="auto-add">
                <el-icon><InfoFilled /></el-icon>
                <div><strong>探测只读取网络状态</strong><small>不会添加资产，结果可导出后用于规划</small></div>
              </div>
              <el-button type="primary" size="large" :loading="pingLoading" :disabled="!canEdit" @click="scanPing">
                <el-icon><Position /></el-icon>开始探测
              </el-button>
            </div>
          </el-form>

          <div v-if="pingSummary" class="summary-row">
            <div><span>探测地址</span><b>{{ pingSummary.total }}</b></div>
            <div class="success"><span>存活</span><b>{{ pingSummary.alive }}</b></div>
            <div class="danger"><span>离线</span><b>{{ pingSummary.offline }}</b></div>
            <div class="muted"><span>耗时</span><b>{{ pingSummary.duration_seconds }}s</b></div>
          </div>

          <div v-if="pingResults.length" class="result-block">
            <div class="result-toolbar">
              <div><strong>存活探测结果</strong><span>共 {{ pingResults.length }} 个地址</span></div>
              <el-radio-group v-model="pingFilter" size="small">
                <el-radio-button value="all">全部</el-radio-button>
                <el-radio-button value="alive">存活</el-radio-button>
                <el-radio-button value="offline">离线</el-radio-button>
              </el-radio-group>
            </div>
            <el-table :data="pagedPingResults" size="small" max-height="430">
              <el-table-column prop="ip_address" label="IP 地址" width="160">
                <template #default="{ row }"><span class="mono">{{ row.ip_address }}</span></template>
              </el-table-column>
              <el-table-column label="状态" width="110">
                <template #default="{ row }">
                  <span class="alive-status" :class="row.alive ? 'ok' : 'bad'"><i></i>{{ row.alive ? '在线' : '离线' }}</span>
                </template>
              </el-table-column>
              <el-table-column label="延迟" width="110">
                <template #default="{ row }">{{ row.latency_ms !== null ? `${row.latency_ms}ms` : '-' }}</template>
              </el-table-column>
              <el-table-column label="探测方式" width="100">
                <template #default="{ row }">{{ row.method === 'icmp' ? 'ICMP' : 'TCP' }}</template>
              </el-table-column>
            </el-table>
            <div class="result-pagination">
              <el-pagination
                v-model:current-page="pingPage"
                v-model:page-size="pingPageSize"
                :page-sizes="[20, 50, 100]"
                :total="filteredPingResults.length"
                layout="total, sizes, prev, pager, next, jumper"
                small
              />
            </div>
          </div>
          <el-empty v-else-if="!pingLoading" description="输入探测范围后开始，结果会显示在这里" :image-size="72" />
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { discoveryApi } from '@/api'
import { can, currentUser } from '@/store/auth'
import { formatDateTime } from '@/utils/time'

const activeTab = ref('snmp')
const canEdit = computed(() => can('discovery:edit'))
const isSuperuser = computed(() => Boolean(currentUser.value?.is_superuser))

const scheduleForm = reactive({
  name: '',
  enabled: false,
  target: '',
  interval_minutes: 60,
  auto_add: true,
  version: 'v2c',
  community: 'public',
  communities: ['public'],
  port: 161,
  timeout: 2,
  concurrency: 32,
  v3_username: '',
  v3_security_level: 'authPriv',
  v3_auth_protocol: 'SHA',
  v3_auth_password: '',
  v3_priv_protocol: 'AES',
  v3_priv_password: '',
  v3_context_name: '',
})
const scheduleTasks = ref([])
const scheduleLoading = ref(false)
const scheduleSaving = ref(false)
const scheduleDialogVisible = ref(false)
const scheduleEditingId = ref(null)
const scheduleRunningId = ref(null)

const scheduleCommunityOptions = computed(() => [...new Set([
  ...(scheduleForm.communities || []),
  'public',
].filter(Boolean))])

const snmpLoading = ref(false)
const addLoading = ref(false)
const pingLoading = ref(false)
const snmpResults = ref([])
const snmpSummary = ref(null)
const selectedSnmp = ref([])
const pingResults = ref([])
const pingSummary = ref(null)
const pingFilter = ref('all')
const snmpTableRef = ref(null)
const snmpPage = ref(1)
const snmpPageSize = ref(20)
const pingPage = ref(1)
const pingPageSize = ref(20)

const pagedSnmpResults = computed(() => {
  const start = (snmpPage.value - 1) * snmpPageSize.value
  return snmpResults.value.slice(start, start + snmpPageSize.value)
})

const pagedPingResults = computed(() => {
  const start = (pingPage.value - 1) * pingPageSize.value
  return filteredPingResults.value.slice(start, start + pingPageSize.value)
})

watch([() => snmpResults.value.length, snmpPageSize], () => {
  const maxPage = Math.max(1, Math.ceil(snmpResults.value.length / snmpPageSize.value))
  if (snmpPage.value > maxPage) snmpPage.value = maxPage
})

watch(pingFilter, () => { pingPage.value = 1 })

const snmpForm = reactive({
  target: '',
  version: 'v2c',
  community: 'public',
  port: 161,
  timeout: 2,
  concurrency: 32,
  auto_add: true,
  v3_username: '',
  v3_security_level: 'authPriv',
  v3_auth_protocol: 'SHA',
  v3_auth_password: '',
  v3_priv_protocol: 'AES',
  v3_priv_password: '',
  v3_context_name: '',
})

const pingForm = reactive({
  target: '',
  timeout: 1,
  concurrency: 64,
})

const filteredPingResults = computed(() => {
  if (pingFilter.value === 'alive') return pingResults.value.filter((item) => item.alive)
  if (pingFilter.value === 'offline') return pingResults.value.filter((item) => !item.alive)
  return pingResults.value
})

function deviceTypeLabel(type) {
  return {
    router: '路由器',
    switch: '交换机',
    firewall: '防火墙',
    server: '服务器',
    security: '安全设备',
    other: '其他',
  }[type] || type || '其他'
}

function errorMessage(error) {
  return error?.response?.data?.detail || error?.message || '操作失败'
}

function scheduleStatusLabel(status) {
  return { idle: '未运行', running: '执行中', success: '上次成功', failed: '上次失败' }[status] || '未运行'
}

function scheduleStatusType(status) {
  return { running: 'warning', success: 'success', failed: 'danger' }[status] || 'info'
}

function resetScheduleForm() {
  Object.assign(scheduleForm, {
    name: '',
    enabled: false,
    target: '',
    interval_minutes: 60,
    auto_add: true,
    version: 'v2c',
    community: 'public',
    communities: ['public'],
    port: 161,
    timeout: 2,
    concurrency: 32,
    v3_username: '',
    v3_security_level: 'authPriv',
    v3_auth_protocol: 'SHA',
    v3_auth_password: '',
    v3_priv_protocol: 'AES',
    v3_priv_password: '',
    v3_context_name: '',
  })
}

async function loadSchedules() {
  scheduleLoading.value = true
  try {
    const { data } = await discoveryApi.listSchedules()
    scheduleTasks.value = data.items || []
  } catch (error) {
    if (error?.response?.status !== 403) ElMessage.error(errorMessage(error))
  } finally {
    scheduleLoading.value = false
  }
}

function openCreateSchedule() {
  resetScheduleForm()
  scheduleEditingId.value = null
  scheduleDialogVisible.value = true
}

function openEditSchedule(row) {
  Object.assign(scheduleForm, {
    name: row.name || '',
    enabled: Boolean(row.enabled),
    target: row.target || '',
    interval_minutes: Number(row.interval_minutes || 60),
    auto_add: row.auto_add !== false,
    version: row.version || 'v2c',
    community: row.community || 'public',
    communities: Array.isArray(row.communities) && row.communities.length
      ? [...row.communities]
      : [row.community || 'public'],
    port: Number(row.port || 161),
    timeout: Number(row.timeout || 2),
    concurrency: Number(row.concurrency || 32),
    v3_username: row.v3_username || '',
    v3_security_level: row.v3_security_level || 'authPriv',
    v3_auth_protocol: row.v3_auth_protocol || 'SHA',
    v3_auth_password: row.v3_auth_password || '',
    v3_priv_protocol: row.v3_priv_protocol || 'AES',
    v3_priv_password: row.v3_priv_password || '',
    v3_context_name: row.v3_context_name || '',
  })
  if (scheduleForm.version === 'v3') scheduleForm.communities = []
  scheduleEditingId.value = row.id
  scheduleDialogVisible.value = true
}

async function saveSchedule() {
  if (!scheduleForm.name.trim()) {
    ElMessage.warning('请填写任务名称')
    return
  }
  if (scheduleForm.enabled && !scheduleForm.target.trim()) {
    ElMessage.warning('启用定时扫描前请填写扫描范围')
    return
  }
  const communities = [...new Set(
    (scheduleForm.communities || [])
      .map((item) => String(item || '').trim())
      .filter(Boolean),
  )]
  if (scheduleForm.version !== 'v3' && !communities.length) {
    ElMessage.warning('请至少填写一个 SNMP 团体名')
    return
  }
  if (communities.length > 10) {
    ElMessage.warning('每个定时任务最多配置 10 个团体名')
    return
  }
  const payload = {
    name: scheduleForm.name.trim(),
    enabled: scheduleForm.enabled,
    target: scheduleForm.target.trim(),
    interval_minutes: scheduleForm.interval_minutes,
    auto_add: scheduleForm.auto_add,
    version: scheduleForm.version,
    community: communities[0] || scheduleForm.community,
    communities: scheduleForm.version === 'v3' ? [] : communities,
    port: scheduleForm.port,
    timeout: scheduleForm.timeout,
    concurrency: scheduleForm.concurrency,
    v3_username: scheduleForm.v3_username || null,
    v3_security_level: scheduleForm.v3_security_level,
    v3_auth_protocol: scheduleForm.v3_auth_protocol,
    v3_auth_password: scheduleForm.v3_auth_password || null,
    v3_priv_protocol: scheduleForm.v3_priv_protocol,
    v3_priv_password: scheduleForm.v3_priv_password || null,
    v3_context_name: scheduleForm.v3_context_name || null,
  }
  scheduleSaving.value = true
  try {
    if (scheduleEditingId.value) {
      await discoveryApi.updateSchedule(scheduleEditingId.value, payload)
      ElMessage.success('定时扫描任务已更新')
    } else {
      await discoveryApi.createSchedule(payload)
      ElMessage.success(scheduleForm.enabled ? '定时扫描任务已创建并启用' : '定时扫描任务已创建')
    }
    scheduleDialogVisible.value = false
    await loadSchedules()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    scheduleSaving.value = false
  }
}

async function runScheduleTask(row) {
  if (!row.target) {
    ElMessage.warning('该任务尚未配置扫描范围')
    return
  }
  scheduleRunningId.value = row.id
  try {
    const { data } = await discoveryApi.runScheduleById(row.id)
    ElMessage.success(`任务「${row.name}」执行完成：发现 ${data.last_found || 0} 台，新增 ${data.last_added || 0} 台`)
    await loadSchedules()
  } catch (error) {
    ElMessage.error(errorMessage(error))
    await loadSchedules()
  } finally {
    scheduleRunningId.value = null
  }
}

async function deleteScheduleTask(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除定时扫描任务「${row.name}」吗？已入库资产不会被删除。`,
      '删除定时任务',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await discoveryApi.deleteSchedule(row.id)
    ElMessage.success('定时扫描任务已删除')
    await loadSchedules()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

function credentialPayload() {
  return {
    version: snmpForm.version,
    community: snmpForm.community,
    port: snmpForm.port,
    timeout: snmpForm.timeout,
    concurrency: snmpForm.concurrency,
    v3_username: snmpForm.v3_username || null,
    v3_security_level: snmpForm.v3_security_level,
    v3_auth_protocol: snmpForm.v3_auth_protocol,
    v3_auth_password: snmpForm.v3_auth_password || null,
    v3_priv_protocol: snmpForm.v3_priv_protocol,
    v3_priv_password: snmpForm.v3_priv_password || null,
    v3_context_name: snmpForm.v3_context_name || null,
  }
}

async function scanSnmp() {
  if (!snmpForm.target.trim()) {
    ElMessage.warning('请输入扫描范围')
    return
  }
  snmpLoading.value = true
  snmpResults.value = []
  snmpSummary.value = null
  snmpPage.value = 1
  selectedSnmp.value = []
  snmpTableRef.value?.clearSelection()
  try {
    const { data } = await discoveryApi.scanSnmp({ ...snmpForm, ...credentialPayload() })
    snmpResults.value = data.items || []
    snmpSummary.value = data
    ElMessage.success(`扫描完成：发现 ${data.discovered} 台 SNMP 设备，自动添加 ${data.added} 台`)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    snmpLoading.value = false
  }
}

async function addSelected() {
  if (!selectedSnmp.value.length) return
  addLoading.value = true
  try {
    const { data } = await discoveryApi.addSnmp({
      ips: selectedSnmp.value.map((item) => item.ip_address),
      ...credentialPayload(),
    })
    const addedIps = new Set((data.added || []).map((item) => item.ip_address))
    snmpResults.value = snmpResults.value.map((item) => (
      addedIps.has(item.ip_address) ? { ...item, exists: true, added: true } : item
    ))
    ElMessage.success(`已添加 ${data.added?.length || 0} 台设备`)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    addLoading.value = false
  }
}

async function scanPing() {
  if (!pingForm.target.trim()) {
    ElMessage.warning('请输入探测范围')
    return
  }
  pingLoading.value = true
  pingResults.value = []
  pingSummary.value = null
  pingPage.value = 1
  try {
    const { data } = await discoveryApi.scanPing({ ...pingForm })
    pingResults.value = data.items || []
    pingSummary.value = data
    ElMessage.success(`探测完成：在线 ${data.alive}，离线 ${data.offline}`)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    pingLoading.value = false
  }
}

onMounted(loadSchedules)
</script>

<style scoped>
.discovery-view {
  padding: 4px 0;
}

.discovery-card {
  border-radius: 12px;
}

.discovery-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
}

.discovery-title {
  display: flex;
  align-items: center;
  gap: 9px;
  color: #1f2d3d;
  font-size: 17px;
  font-weight: 600;
}

.title-icon {
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 9px;
  color: #0ea5e9;
  background: #e0f2fe;
}

.discovery-sub {
  margin-top: 5px;
  color: #8a99a8;
  font-size: 12px;
}

.header-badges {
  display: flex;
  gap: 14px;
  color: #64748b;
  font-size: 11px;
}

.header-badges span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.dot.cyan { background: #0ea5e9; box-shadow: 0 0 0 3px rgba(14, 165, 233, 0.1); }
.dot.green { background: #10b981; box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.1); }

.discovery-tabs :deep(.el-tabs__header) {
  margin-bottom: 18px;
}

.permission-alert {
  margin-bottom: 14px;
}

.tab-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.scan-intro {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 13px 16px;
  border: 1px solid #e2edf7;
  border-radius: 10px;
  background: linear-gradient(90deg, #f5fbff, #fbfdff);
}

.scan-intro strong {
  color: #24425b;
  font-size: 13px;
}

.scan-intro p {
  margin: 4px 0 0;
  color: #8295a7;
  font-size: 11px;
}

.ping-intro {
  background: linear-gradient(90deg, #f4fbf9, #fbfefc);
  border-color: #dcefe7;
}

.scan-form {
  margin-top: 16px;
}

.form-grid {
  display: grid;
  grid-template-columns: minmax(210px, 1.4fr) minmax(120px, 0.8fr) minmax(150px, 0.9fr) repeat(3, minmax(86px, 0.55fr));
  gap: 0 14px;
}

.form-grid.compact {
  grid-template-columns: minmax(240px, 360px);
}

.form-grid.v3-grid {
  grid-template-columns: repeat(3, minmax(180px, 1fr));
}

.form-grid .span-2 {
  grid-column: span 2;
}

.form-grid :deep(.el-form-item) {
  margin-bottom: 14px;
}

.field-tip {
  margin-top: 4px;
  color: #9aa9b8;
  font-size: 10px;
}

.scan-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-top: 4px;
  padding-top: 14px;
  border-top: 1px solid #eef3f8;
}

.auto-add {
  display: flex;
  align-items: center;
  gap: 10px;
}

.auto-add strong {
  display: block;
  color: #334e63;
  font-size: 12px;
  font-weight: 500;
}

.auto-add small {
  display: block;
  margin-top: 2px;
  color: #93a3b2;
  font-size: 10px;}

.auto-add .el-icon {
  color: #10b981;
  font-size: 18px;
}

.schedule-panel {
  margin-top: 18px;
  padding: 14px 16px;
  border: 1px solid #dbeafe;
  border-radius: 10px;
  background: #f8fbff;
}

.schedule-intro {
  background: linear-gradient(90deg, #f7f4ff, #fbfdff);
  border-color: #e5def7;
}

.schedule-task-list {
  margin-top: 16px;
}

.schedule-task-list .result-toolbar {
  margin-bottom: 10px;
}

.schedule-name-cell {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}

.schedule-name-cell > span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.schedule-last-run {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  font-size: 11px;
}

.schedule-result-text {
  margin-top: 3px;
  color: #8b9dab;
  font-size: 10px;
}

.schedule-dialog-form {
  margin-top: 2px;
}

.schedule-dialog-base {
  grid-template-columns: repeat(4, minmax(150px, 1fr));
}

.schedule-dialog-options {
  display: flex;
  align-items: center;
  gap: 22px;
  flex-wrap: wrap;
  margin: 2px 0 16px;
  padding: 10px 12px;
  border: 1px solid #e8eef5;
  border-radius: 8px;
  background: #fbfdff;
}

.schedule-option {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #526b80;
  font-size: 12px;
}

.schedule-enable {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
  color: #5e6f80;
  font-size: 12px;
}

.schedule-interval {
  display: flex;
  align-items: center;
  gap: 9px;
  margin: 2px 0 14px;
  color: #526b80;
  font-size: 11px;
}

.schedule-submit {
  display: flex;
  gap: 8px;
}

.schedule-actions-bar {
  align-items: center;
}

.schedule-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.schedule-head strong {
  color: #24425b;
  font-size: 13px;
}

.schedule-head p {
  margin: 4px 0 0;
  color: #8799a9;
  font-size: 11px;
}

.schedule-row {
  display: flex;
  align-items: center;
  gap: 9px;
  flex-wrap: wrap;
  margin-top: 12px;
  color: #526b80;
  font-size: 11px;
}

.schedule-actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
}

.schedule-community-row {
  align-items: flex-start;
}

.schedule-community-row > span:first-child {
  padding-top: 7px;
  flex: none;
}

.schedule-community-select {
  width: min(460px, 100%);
}

.schedule-community-row > .muted {
  padding-top: 7px;
}

.schedule-status {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 10px;
  color: #71889a;
  font-size: 11px;
}

.schedule-message {
  margin-top: 7px;
  color: #8a9cab;
  font-size: 11px;
  overflow-wrap: anywhere;
}

.schedule-hint {
  margin-top: 7px;
  color: #9aabb9;
  font-size: 10px;
}

.search-loading {
  min-height: 80px;
}

.summary-row {
  display: flex;
  gap: 10px;
  margin-top: 16px;
}

.summary-row > div {
  flex: 1;
  padding: 10px 14px;
  border: 1px solid #e8eef5;
  border-radius: 9px;
  background: #fbfdff;
}

.summary-row span {
  display: block;
  color: #94a3b8;
  font-size: 10px;
}

.summary-row b {
  display: block;
  margin-top: 3px;
  color: #1e3a52;
  font-family: Consolas, monospace;
  font-size: 20px;
}

.summary-row .success b { color: #059669; }
.summary-row .added b { color: #0284c7; }
.summary-row .danger b { color: #e11d48; }
.summary-row .muted b { color: #64748b; font-size: 16px; }

.result-block {
  margin-top: 16px;
}

.result-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.result-toolbar strong {
  color: #24425b;
  font-size: 13px;
}

.result-toolbar span {
  margin-left: 8px;
  color: #94a3b8;
  font-size: 11px;
}

.result-pagination {
  display: flex;
  justify-content: flex-end;
  padding-top: 10px;
}

.mono {
  font-family: Consolas, monospace;
  font-size: 12px;
}

.alive-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
}

.alive-status i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.alive-status.ok { color: #059669; }
.alive-status.ok i { background: #10b981; box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.1); }
.alive-status.bad { color: #dc2626; }
.alive-status.bad i { background: #ef4444; box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.08); }

.ping-actions {
  border-top-color: #e7f3ee;
}

@media (max-width: 900px) {
  .discovery-header { align-items: flex-start; flex-direction: column; }
  .header-badges { flex-wrap: wrap; }
  .form-grid { grid-template-columns: 1fr 1fr; }
  .form-grid .span-2 { grid-column: span 2; }
  .form-grid.v3-grid { grid-template-columns: 1fr 1fr; }
  .scan-actions { align-items: flex-start; flex-direction: column; }
}
</style>
