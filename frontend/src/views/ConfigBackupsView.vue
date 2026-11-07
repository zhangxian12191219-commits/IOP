<template>
  <div class="config-backup-view">
    <el-card>
      <template #header>
        <div class="cb-head">
          <div>
            <div class="cb-title">设备配置备份</div>
            <div class="cb-sub">华为 / 华三 / 飞塔 / 深信服 / 锐捷等网络设备配置自动与手动备份</div>
          </div>
          <div class="cb-head-actions">
            <el-tag v-if="!globalBackupEnabled" type="warning" size="small">全局自动备份已关闭</el-tag>
            <el-tag v-if="overview?.scheduler" :type="overview.scheduler.running ? 'success' : 'info'" size="small">
              调度器 {{ overview.scheduler.running ? '运行中' : '未运行' }}
            </el-tag>
            <el-button size="small" :loading="loading" @click="loadAll">刷新</el-button>
          </div>
        </div>
      </template>

      <div class="cb-stats">
        <div><span>纳管设备</span><b>{{ overview?.stats?.devices ?? 0 }}</b></div>
        <div><span>设备开关开启</span><b>{{ overview?.stats?.enabled ?? 0 }}</b></div>
        <div><span>SSH 已配置</span><b>{{ overview?.stats?.configured ?? 0 }}</b></div>
        <div><span>成功记录</span><b class="ok">{{ overview?.stats?.success ?? 0 }}</b></div>
        <div><span>失败记录</span><b class="danger">{{ overview?.stats?.failed ?? 0 }}</b></div>
      </div>

      <el-tabs v-model="activeTab" @tab-change="onTabChange">
        <el-tab-pane label="设备与批量操作" name="devices">
          <el-alert
            v-if="!globalBackupEnabled"
            type="warning"
            :closable="false"
            show-icon
            class="mb12"
            title="全局自动备份当前未开启：设备上的自动备份开关不会执行。请到「自动备份设置」开启全局自动备份。"
          >
            <template #default>
              <el-button link type="primary" @click="openGlobalBackupSettings">去开启全局自动备份</el-button>
            </template>
          </el-alert>
          <div class="cb-toolbar">
            <el-select v-model="deviceFilters.group_id" clearable placeholder="全部设备分组" size="small" style="width: 150px" @change="applyDeviceFilters">
              <el-option v-for="group in groups" :key="group.id" :label="group.name" :value="group.id" />
            </el-select>
            <el-input v-model="deviceFilters.keyword" clearable placeholder="设备名称/IP" size="small" style="width: 180px" @keyup.enter="applyDeviceFilters" />
            <el-select v-model="deviceFilters.status" clearable placeholder="备份状态" size="small" style="width: 130px" @change="applyDeviceFilters">
              <el-option label="设备开关已开启" value="enabled" />
              <el-option label="已加入备份" value="managed" />
              <el-option label="未加入备份" value="unmanaged" />
              <el-option label="未配置 SSH" value="unconfigured" />
              <el-option label="最近失败" value="failed" />
            </el-select>
            <el-button size="small" @click="applyDeviceFilters">查询</el-button>
            <el-button size="small" type="primary" plain :disabled="!editable" @click="openImportDialog">添加设备</el-button>
            <div class="cb-batch-actions">
              <el-checkbox
                :model-value="allPageDevicesSelected"
                :indeterminate="somePageDevicesSelected"
                @change="toggleSelectPage"
              >全选本页</el-checkbox>
              <el-button size="small" link :disabled="!selectedDevices.length" @click="clearDeviceSelection">取消选择</el-button>
              <span class="selected-hint">已选 {{ selectedDevices.length }} 台</span>
              <el-button size="small" :disabled="!selectedDevices.length || !editable" @click="openBatchAdd">批量加入</el-button>
              <el-button size="small" type="danger" plain :disabled="!selectedDevices.length || !editable" @click="batchDelete">批量删除</el-button>
              <el-button size="small" :disabled="!selectedDevices.length || !editable" :loading="batchBusy" @click="batchRun">批量备份</el-button>
              <el-button size="small" :disabled="!selectedDevices.length || !editable" @click="batchToggle(true)">批量启用</el-button>
              <el-button size="small" :disabled="!selectedDevices.length || !editable" @click="batchToggle(false)">批量停用</el-button>
            </div>
          </div>
          <div class="cb-device-cards">
            <article v-for="row in devices" :key="row.id" class="cb-device-card">
              <div class="cb-card-top">
                <el-checkbox :model-value="isDeviceSelected(row)" @change="(checked) => toggleDeviceCard(row, checked)">选择</el-checkbox>
                <el-tag size="small" :type="row.backup_password_set ? 'success' : 'info'">{{ row.backup_password_set ? 'SSH 已配置' : 'SSH 未配置' }}</el-tag>
                <el-tag v-if="row.backup_enabled && !globalBackupEnabled" size="small" type="warning">自动备份·全局未开启</el-tag>
                <el-tag v-else size="small" :type="row.backup_enabled ? 'success' : 'info'">{{ row.backup_enabled ? '自动备份' : '未自动备份' }}</el-tag>
              </div>
              <div class="cb-card-head">
                <strong>{{ row.name }}</strong>
                <span class="cb-device-ip">{{ row.ip_address }}</span>
              </div>
              <div class="cb-card-meta">
                <span>{{ row.vendor || '-' }} · {{ row.device_type }}</span>
                <span>{{ row.group_name || '未分组' }}</span>
                <span v-if="row.backup_password_set">{{ row.backup_username }}@{{ row.backup_port }}</span>
              </div>
              <div class="cb-card-backup">
                <template v-if="row.last_backup">
                  <div class="cb-backup-head">
                    <el-tag :type="row.last_backup.status === 'success' ? 'success' : (row.last_backup.status === 'running' ? 'warning' : 'danger')" size="small">
                      {{ row.last_backup.status === 'success' ? '备份成功' : (row.last_backup.status === 'running' ? '备份中' : '备份失败') }}
                    </el-tag>
                    <span class="cb-backup-label">最近备份</span>
                    <span class="cb-time">{{ formatDateTime(row.last_backup.created_at) }}</span>
                  </div>
                  <div v-if="row.last_backup.error" class="cb-error">{{ row.last_backup.error }}</div>
                </template>
                <span v-else class="muted">暂无备份记录</span>
              </div>
              <div class="cb-card-actions">
                <el-button type="primary" link size="small" :disabled="!editable" @click="openDeviceDialog(row)">配置</el-button>
                <el-button type="success" link size="small" :loading="runningId === row.id" :disabled="!row.backup_password_set || !editable" @click="runNow(row)">立即备份</el-button>
                <el-button type="info" link size="small" @click="showDeviceRecords(row)">记录</el-button>
                <el-button type="danger" link size="small" :disabled="!editable" @click="removeBackupDevice(row)">删除</el-button>
              </div>
            </article>
          </div>
          <div class="cb-pager">
            <el-pagination
              v-model:current-page="devicePage"
              :page-size="devicePageSize"
              :page-sizes="devicePageSizes"
              :total="deviceTotal"
              layout="total, sizes, prev, pager, next, jumper"
              @size-change="onDevicePageSizeChange"
              @current-change="loadDevices"
            />
          </div>
          <el-empty v-if="!devicesLoading && !devices.length" description="没有符合条件的设备" :image-size="60">
            <el-button v-if="editable" type="primary" size="small" @click="openImportDialog">添加备份设备</el-button>
          </el-empty>
        </el-tab-pane>

        <el-tab-pane label="备份记录与对比" name="records">
          <div class="cb-toolbar">
            <el-select v-model="recordFilters.device_id" clearable filterable placeholder="全部设备" size="small" style="width: 180px" @change="loadRecords(1)">
              <el-option v-for="item in devices" :key="item.id" :label="`${item.name}（${item.ip_address}）`" :value="item.id" />
            </el-select>
            <el-select v-model="recordFilters.status" clearable placeholder="全部状态" size="small" style="width: 120px" @change="loadRecords(1)">
              <el-option label="成功" value="success" />
              <el-option label="失败" value="failed" />
              <el-option label="进行中" value="running" />
            </el-select>
            <el-select v-model="recordFilters.order" size="small" style="width: 150px" @change="loadRecords(1)">
              <el-option label="时间倒序（最新在前）" value="desc" />
              <el-option label="时间正序（最早在前）" value="asc" />
            </el-select>
            <el-button size="small" @click="loadRecords(1)">查询</el-button>
            <div class="cb-batch-actions">
              <span class="selected-hint">已选 {{ selectedRecords.length }} 条</span>
              <el-button size="small" type="primary" plain :disabled="!canCompareRecords" title="选择两条成功的备份记录进行在线对比" @click="compareSelected">在线对比</el-button>
              <el-button size="small" @click="exportRecords">导出 ZIP</el-button>
            </div>
          </div>
          <div v-for="group in recordGroups" :key="group.device_id" class="record-asset-group">
            <div class="record-asset-head">
              <div class="record-asset-title">
                <strong>{{ group.device_name }}</strong>
                <span class="cb-device-ip">{{ group.ip_address }}</span>
                <el-tag v-if="group.vendor" size="small" effect="plain">{{ group.vendor }}</el-tag>
                <el-tag v-if="group.group_name" size="small" type="info" effect="plain">{{ group.group_name }}</el-tag>
              </div>
              <div class="record-asset-count">
                共 <b>{{ group.total }}</b> 条记录
                <span v-if="group.total > group.records.length">（显示 {{ group.records.length }} 条）</span>
              </div>
            </div>
            <div class="cb-device-cards">
              <article v-for="row in group.records" :key="row.id" class="cb-device-card">
                <div class="cb-card-top">
                  <el-checkbox :model-value="isRecordSelected(row)" @change="(checked) => toggleRecordCard(row, checked)">选择对比</el-checkbox>
                  <el-tag :type="row.status === 'success' ? 'success' : (row.status === 'running' ? 'warning' : 'danger')" size="small">
                    {{ row.status === 'success' ? '成功' : (row.status === 'running' ? '进行中' : '失败') }}
                  </el-tag>
                  <el-tag size="small" effect="plain">{{ row.method === 'scheduled' ? '定时' : '手动' }}</el-tag>
                  <el-tag v-if="row.storage_status === 'success'" size="small" type="success" effect="plain">外部已存</el-tag>
                  <el-tag v-else-if="row.storage_status === 'failed'" size="small" type="danger" effect="plain" :title="row.storage_error">外部失败</el-tag>
                </div>
                <div class="cb-card-head">
                  <strong>{{ row.device_name }}</strong>
                  <span class="cb-device-ip">{{ row.ip_address }}</span>
                </div>
                <div class="cb-card-meta">
                  <span>{{ formatTime(row.created_at) }}</span>
                  <span>{{ formatSize(row.size_bytes) }}</span>
                  <span>{{ row.vendor_profile || '通用适配' }}</span>
                </div>
                <div v-if="row.error" class="cb-card-backup"><div class="cb-error">{{ row.error }}</div></div>
                <div class="cb-card-actions">
                  <el-button type="primary" link size="small" @click="openRecord(row)">详情</el-button>
                  <el-button v-if="row.status === 'success'" type="success" link size="small" @click="downloadRecord(row)">下载</el-button>
                  <el-button type="danger" link size="small" @click="removeRecord(row)">删除</el-button>
                </div>
              </article>
            </div>
          </div>
          <el-empty v-if="!recordsLoading && !recordGroups.length" description="暂无备份记录" :image-size="60" />
          <div class="cb-pager">
            <el-pagination
              v-model:current-page="recordPage"
              :page-size="recordPageSize"
              :total="recordTotal"
              layout="total, prev, pager, next"
              @current-change="loadRecords"
            />
          </div>
        </el-tab-pane>

        <el-tab-pane label="自动备份设置" name="settings">
          <el-alert v-if="!isSuper" type="warning" :closable="false" show-icon title="自动备份全局设置仅超级管理员可修改；设备 SSH 参数仍可在设备页配置。" />
          <el-form label-width="160px" class="cb-settings-form">
            <el-form-item label="启用自动备份">
              <el-switch v-model="settingsForm.config_backup_enabled" :disabled="!isSuper" />
              <span class="form-help">{{ settingsForm.config_backup_enabled ? '全局自动备份已开启' : '关闭后所有设备都不会自动备份（手动备份不受影响）' }}</span>
            </el-form-item>
            <el-form-item label="全局备份间隔（小时）">
              <el-input-number v-model="settingsForm.config_backup_interval_hours" :min="1" :max="168" :disabled="!isSuper" controls-position="right" />
              <span class="form-help">所有设备的默认间隔；设备独立间隔为 0 时使用该值。调度器每 60 秒检查一次。</span>
            </el-form-item>
            <el-form-item label="每台保留份数">
              <el-input-number v-model="settingsForm.config_backup_retention_count" :min="1" :max="200" :disabled="!isSuper" controls-position="right" />
            </el-form-item>
            <el-form-item label="并发设备数">
              <el-input-number v-model="settingsForm.config_backup_concurrency" :min="1" :max="10" :disabled="!isSuper" controls-position="right" />
            </el-form-item>
            <el-form-item label="SSH 超时（秒）">
              <el-input-number v-model="settingsForm.config_backup_timeout" :min="10" :max="180" :disabled="!isSuper" controls-position="right" />
            </el-form-item>
            <el-divider content-position="left">外部存储（可选）</el-divider>
            <el-form-item label="启用外部存储">
              <el-switch v-model="settingsForm.config_backup_storage_enabled" :disabled="!isSuper" />
              <span class="form-help">备份成功后额外上传一份；数据库正文仍保留作为兜底</span>
            </el-form-item>
            <el-form-item v-if="settingsForm.config_backup_storage_enabled" label="存储方式">
              <el-select v-model="settingsForm.config_backup_storage_type" :disabled="!isSuper" style="width: 220px">
                <el-option label="WebDAV / NAS" value="webdav" />
                <el-option label="SFTP / SSH 文件服务器" value="sftp" />
              </el-select>
            </el-form-item>
            <template v-if="settingsForm.config_backup_storage_enabled && settingsForm.config_backup_storage_type === 'webdav'">
              <el-form-item label="WebDAV 地址">
                <el-input v-model="settingsForm.config_backup_webdav_url" :disabled="!isSuper" placeholder="https://nas.example.com/dav" />
              </el-form-item>
              <el-form-item label="WebDAV 用户名">
                <el-input v-model="settingsForm.config_backup_webdav_username" :disabled="!isSuper" autocomplete="off" />
              </el-form-item>
              <el-form-item label="WebDAV 密码">
                <el-input v-model="settingsForm.config_backup_webdav_password" type="password" show-password :disabled="!isSuper" autocomplete="new-password" />
              </el-form-item>
              <el-form-item label="远程目录">
                <el-input v-model="settingsForm.config_backup_webdav_path" :disabled="!isSuper" placeholder="/snmp-monitor/config-backups" />
              </el-form-item>
              <el-form-item label="校验 TLS">
                <el-switch v-model="settingsForm.config_backup_webdav_verify_tls" :disabled="!isSuper" />
              </el-form-item>
            </template>
            <template v-if="settingsForm.config_backup_storage_enabled && settingsForm.config_backup_storage_type === 'sftp'">
              <el-form-item label="SFTP 主机">
                <el-input v-model="settingsForm.config_backup_sftp_host" :disabled="!isSuper" placeholder="192.168.1.20" />
              </el-form-item>
              <el-form-item label="SFTP 端口">
                <el-input-number v-model="settingsForm.config_backup_sftp_port" :min="1" :max="65535" :disabled="!isSuper" controls-position="right" />
              </el-form-item>
              <el-form-item label="SFTP 用户名">
                <el-input v-model="settingsForm.config_backup_sftp_username" :disabled="!isSuper" autocomplete="off" />
              </el-form-item>
              <el-form-item label="SFTP 密码">
                <el-input v-model="settingsForm.config_backup_sftp_password" type="password" show-password :disabled="!isSuper" autocomplete="new-password" />
              </el-form-item>
              <el-form-item label="远程目录">
                <el-input v-model="settingsForm.config_backup_sftp_path" :disabled="!isSuper" placeholder="/snmp-monitor/config-backups" />
              </el-form-item>
              <el-form-item label="SFTP 超时（秒）">
                <el-input-number v-model="settingsForm.config_backup_sftp_timeout" :min="3" :max="120" :disabled="!isSuper" controls-position="right" />
              </el-form-item>
            </template>
            <el-form-item>
              <el-button v-if="isSuper" type="primary" :loading="settingsSaving" @click="saveSettings">保存自动备份设置</el-button>
              <span v-if="overview?.scheduler?.last_run" class="form-help">上次调度：{{ formatTime(overview.scheduler.last_run) }}</span>
            </el-form-item>
          </el-form>
          <el-alert type="info" :closable="false" show-icon title="调度器运行在后台任务节点；多节点部署时只让主节点运行 RUN_BACKGROUND_TASKS=1。设备需在设备页开启自动备份并配置 SSH 凭据。" />
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <el-dialog v-model="batchAddVisible" :title="`批量加入设备配置备份（${selectedDevices.length} 台）`" width="600px">
      <el-alert v-if="batchAllHaveCredential" type="success" :closable="false" show-icon
        title="所选设备均已关联“设备凭据”，无需再填写 SSH 用户名和密码；备份会直接复用设备凭据。"
        class="mb12" />
      <el-alert v-else type="warning" :closable="false" show-icon
        title="部分设备未关联设备凭据，需要填写统一 SSH 参数；已关联凭据的设备会优先使用凭据。"
        class="mb12" />
      <el-alert v-if="!globalBackupEnabled" type="warning" :closable="false" show-icon class="mb12"
        title="全局自动备份未开启，本次设备开关即使开启也不会执行；可先到「自动备份设置」开启。" />
      <el-form label-width="120px">
        <el-form-item label="自动备份">
          <el-switch v-model="batchAddForm.backup_enabled" />
          <span class="form-help">{{ globalBackupEnabled ? '将随全局调度执行' : '当前全局未开启，不会执行' }}</span>
        </el-form-item>
        <template v-if="!batchAllHaveCredential">
          <el-form-item label="SSH 用户名" required>
            <el-input v-model="batchAddForm.backup_username" placeholder="统一 SSH 用户名" />
          </el-form-item>
          <el-form-item label="SSH 密码" required>
            <el-input v-model="batchAddForm.backup_password" type="password" show-password placeholder="统一 SSH 密码" />
          </el-form-item>
          <el-form-item label="SSH 端口">
            <el-input-number v-model="batchAddForm.backup_port" :min="1" :max="65535" controls-position="right" />
          </el-form-item>
        </template>
        <el-form-item label="备份间隔（小时）">
          <el-input-number v-model="batchAddForm.backup_interval_hours" :min="0" :max="168" controls-position="right" />
          <span class="form-help">0 = 跟随全局 {{ globalBackupInterval }} 小时；大于 0 时覆盖全局。</span>
        </el-form-item>
        <el-form-item label="配置命令">
          <div class="batch-command-list">
            <div v-for="device in selectedDevices" :key="device.id" class="batch-command-item">
              <div class="batch-command-meta">
                <b>{{ device.name }}</b>
                <el-tag size="small" type="info" effect="plain">{{ device.vendor || '未填写厂商' }}</el-tag>
                <code>{{ device.auto_command || '通用命令' }}</code>
              </div>
              <el-input
                v-model="batchCommands[device.id]"
                size="small"
                clearable
                maxlength="200"
                placeholder="留空使用厂商自动命令；可逐台覆盖"
              />
            </div>
            <div v-if="!selectedDevices.length" class="form-help">请先选择设备</div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="batchAddVisible = false">取消</el-button>
        <el-button type="primary" :loading="batchAddSaving" @click="saveBatchAdd">确认加入</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="importVisible" title="添加备份设备" width="900px" top="4vh" @closed="importSelected = []">
      <el-tabs v-model="importTab">
        <el-tab-pane label="从现有资产选择" name="existing">
          <el-alert type="info" :closable="false" show-icon title="列出尚未加入配置备份的资产；勾选后可批量加入。" class="mb12" />
          <div class="import-toolbar">
            <el-input v-model="importFilters.keyword" clearable placeholder="设备名称/IP" size="small" style="width: 200px" @keyup.enter="loadImportCandidates" />
            <el-select v-model="importFilters.group_id" clearable placeholder="全部资产群组" size="small" style="width: 170px" @change="loadImportCandidates">
              <el-option v-for="group in groups" :key="group.id" :label="group.name" :value="group.id" />
            </el-select>
            <el-button size="small" @click="loadImportCandidates">查询</el-button>
            <el-checkbox :model-value="allImportSelected" :indeterminate="someImportSelected" @change="toggleAllImport">全选</el-checkbox>
            <span class="muted">已选 {{ importSelected.length }} 台</span>
          </div>
          <div v-loading="importLoading" class="import-list">
            <el-checkbox-group v-model="importSelected">
              <el-checkbox v-for="row in importCandidates" :key="row.id" :value="row.id" class="import-item">
                <span class="import-name">{{ row.name }}</span>
                <span class="import-ip">{{ row.ip_address }}</span>
                <el-tag size="small" type="info">{{ row.group_name || '未分组' }}</el-tag>
                <el-tag v-if="row.credential_id" size="small" type="success" effect="plain">已关联凭据</el-tag>
                <span class="muted">{{ row.vendor || '-' }} · {{ row.device_type }}</span>
              </el-checkbox>
            </el-checkbox-group>
            <el-empty v-if="!importLoading && !importCandidates.length" description="没有待加入备份的现有资产" :image-size="50" />
          </div>
          <div v-if="importSelectedRows.length" class="batch-command-list import-command-list">
            <div class="batch-command-title">已选设备配置命令（可逐台覆盖）</div>
            <div v-for="device in importSelectedRows" :key="device.id" class="batch-command-item">
              <div class="batch-command-meta">
                <b>{{ device.name }}</b>
                <el-tag size="small" type="info" effect="plain">{{ device.vendor || '未填写厂商' }}</el-tag>
                <code>{{ device.auto_command || '通用命令' }}</code>
              </div>
              <el-input v-model="importCommands[device.id]" size="small" clearable maxlength="200" placeholder="留空使用厂商自动命令" />
            </div>
          </div>
        </el-tab-pane>
        <el-tab-pane label="自定义添加" name="custom">
          <el-alert type="info" :closable="false" show-icon title="创建新的资产并加入配置备份；也会在资产管理中显示。" class="mb12" />
          <el-form label-width="100px" class="import-custom-form">
            <el-form-item label="设备名称" required>
              <el-input v-model="importForm.name" placeholder="例如：核心交换机-03" />
            </el-form-item>
            <el-form-item label="IP 地址" required>
              <el-input v-model="importForm.ip_address" placeholder="例如：10.20.0.10" />
            </el-form-item>
            <el-form-item label="设备类型" required>
              <el-select v-model="importForm.device_type" style="width: 100%">
                <el-option label="路由器" value="router" />
                <el-option label="交换机" value="switch" />
                <el-option label="防火墙" value="firewall" />
                <el-option label="安全设备" value="security" />
                <el-option label="服务器" value="server" />
              </el-select>
            </el-form-item>
            <el-form-item label="厂商">
              <el-input v-model="importForm.vendor" placeholder="例如：华为、H3C、思科" />
            </el-form-item>
            <el-form-item label="型号">
              <el-input v-model="importForm.model" placeholder="可选" />
            </el-form-item>
            <el-form-item label="资产群组">
              <el-select v-model="importForm.group_id" clearable placeholder="未分组" style="width: 100%">
                <el-option v-for="group in groups" :key="group.id" :label="group.name" :value="group.id" />
              </el-select>
            </el-form-item>
          </el-form>
        </el-tab-pane>
      </el-tabs>

      <div class="import-ssh">
        <div class="import-section-title">SSH 备份参数</div>
        <el-alert v-if="importUsesCredentials" type="success" :closable="false" show-icon class="mb12"
          title="所选资产均已关联“设备凭据”，无需再填写 SSH 用户名和密码；将直接复用设备凭据。" />
        <el-alert v-else-if="importTab === 'existing' && importSelectedRows.length" type="warning" :closable="false" show-icon class="mb12"
          title="部分所选资产未关联设备凭据，请补充 SSH 用户名和密码；已关联凭据的设备优先使用凭据。" />
        <el-alert v-if="!globalBackupEnabled" type="warning" :closable="false" show-icon class="mb12"
          title="全局自动备份未开启，导入设备的自动备份开关不会执行；可先到「自动备份设置」开启。" />
        <el-form label-width="110px" class="import-ssh-form">
          <el-form-item label="自动备份">
            <el-switch v-model="importForm.backup_enabled" />
            <span class="form-help">{{ globalBackupEnabled ? '将随全局调度执行' : '当前全局未开启，不会执行' }}</span>
          </el-form-item>
          <template v-if="!importUsesCredentials">
            <el-form-item label="SSH 用户名" required>
              <el-input v-model="importForm.backup_username" placeholder="设备 SSH 用户名" />
            </el-form-item>
            <el-form-item label="SSH 密码" required>
              <el-input v-model="importForm.backup_password" type="password" show-password placeholder="设备 SSH 密码" />
            </el-form-item>
            <el-form-item label="SSH 端口">
              <el-input-number v-model="importForm.backup_port" :min="1" :max="65535" controls-position="right" />
            </el-form-item>
          </template>
          <el-form-item label="备份间隔（小时）">
            <el-input-number v-model="importForm.backup_interval_hours" :min="0" :max="168" controls-position="right" />
            <span class="form-help">0 = 跟随全局 {{ globalBackupInterval }} 小时；大于 0 时覆盖全局。</span>
          </el-form-item>
          <el-form-item label="自定义命令">
            <el-input v-model="importForm.backup_command" maxlength="200" placeholder="仅自定义单台设备时使用；留空按厂商自动选择" />
          </el-form-item>
        </el-form>
      </div>

      <template #footer>
        <el-button @click="importVisible = false">取消</el-button>
        <el-button type="primary" :loading="importSaving" @click="saveImport">
          {{ importTab === 'custom' ? '创建并加入' : `加入备份（${importSelected.length} 台）` }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="deviceDialogVisible" :title="`设备配置备份 · ${deviceForm.name || ''}`" width="620px">
      <el-alert v-if="deviceForm.credential_id" type="success" :closable="false" show-icon class="mb12"
        :title="`已关联设备凭据：${deviceForm.credential_name || '设备凭据'}；SSH 用户名/密码可留空，备份会复用该凭据。`" />
      <el-alert
        v-if="!globalBackupEnabled"
        type="warning"
        :closable="false"
        show-icon
        class="mb12"
        title="全局自动备份未开启：即使本设备开启自动备份，也不会执行。请先在「自动备份设置」开启全局自动备份。"
      >
        <template #default>
          <el-button link type="primary" @click="openGlobalBackupSettings">去设置全局自动备份</el-button>
        </template>
      </el-alert>
      <el-form label-width="130px">
        <el-form-item label="自动备份">
          <el-switch v-model="deviceForm.backup_enabled" />
          <el-tag v-if="deviceForm.backup_enabled && !globalBackupEnabled" size="small" type="warning">当前不生效</el-tag>
          <span v-else class="form-help">{{ deviceForm.backup_enabled ? '将随全局调度执行' : '关闭后仍可手动备份' }}</span>
        </el-form-item>
        <el-form-item label="SSH 用户名">
          <el-input v-model="deviceForm.backup_username" placeholder="例如 admin" />
        </el-form-item>
        <el-form-item label="SSH 密码">
          <el-input v-model="deviceForm.backup_password" type="password" show-password :placeholder="deviceForm.backup_password_set ? '已配置，留空表示不修改' : '请输入 SSH 密码'" />
        </el-form-item>
        <el-form-item label="SSH 端口">
          <el-input-number v-model="deviceForm.backup_port" :min="1" :max="65535" controls-position="right" />
        </el-form-item>
        <el-form-item label="配置命令">
          <el-input v-model="deviceForm.backup_command" maxlength="200" :placeholder="`留空使用自动命令：${deviceForm.auto_command || '按厂商匹配'}`" />
          <span class="form-help-block">厂商自动命令：{{ deviceForm.auto_command || '未匹配' }}；填写后覆盖自动命令</span>
        </el-form-item>
        <el-form-item label="独立间隔（小时）">
          <el-input-number v-model="deviceForm.backup_interval_hours" :min="0" :max="168" controls-position="right" />
          <span class="form-help-block">
            <template v-if="Number(deviceForm.backup_interval_hours) > 0">
              独立每 {{ Number(deviceForm.backup_interval_hours) }} 小时执行一次，覆盖全局 {{ globalBackupInterval }} 小时
            </template>
            <template v-else>
              跟随全局：每 {{ globalBackupInterval }} 小时执行一次
            </template>
          </span>
        </el-form-item>
        <el-form-item label="间隔说明">
          <div class="form-help-block">
            <span>0 = 使用全局间隔；大于 0 时只对当前设备生效。全局间隔在「自动备份设置 → 备份间隔（小时）」修改。调度器每 60 秒检查一次。</span>
            <el-button class="form-help-action" link type="primary" @click="openGlobalBackupSettings">查看全局设置</el-button>
          </div>
        </el-form-item>
      </el-form>
      <el-alert
        v-if="deviceForm.vendor"
        type="info"
        :closable="false"
        show-icon
        :title="`厂商适配：${deviceForm.vendor}；将优先使用对应分页关闭命令和配置查看命令`"
      />
      <template #footer>
        <el-button @click="deviceDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="deviceSaving" @click="saveDevice">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="recordDialogVisible" :title="recordDetail?.device_name || '备份详情'" width="980px" top="5vh">
      <div v-if="recordDetail" class="record-detail-meta">
        <span>状态：{{ recordDetail.status }}</span>
        <span>方式：{{ recordDetail.method === 'scheduled' ? '定时' : '手动' }}</span>
        <span>时间：{{ formatTime(recordDetail.created_at) }}</span>
        <span>大小：{{ formatSize(recordDetail.size_bytes) }}</span>
        <span>SHA256：{{ recordDetail.sha256?.slice(0, 16) || '-' }}</span>
      </div>
      <pre v-if="recordDetail.status === 'success'" ref="recordConfigPre" class="config-pre">{{ recordDetail.config_text }}</pre>
      <el-alert v-else type="error" :closable="false" :title="recordDetail.error || '无配置内容'" />
      <template #footer>
        <el-button @click="recordDialogVisible = false">关闭</el-button>
        <el-button v-if="recordDetail.status === 'success'" type="primary" @click="downloadRecord(recordDetail)">下载 .cfg</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="diffDialogVisible" title="配置变更对比" width="1200px" top="4vh">
      <div v-if="diffData" class="diff-head">
        <div><span>旧记录</span><b>{{ diffData.a.device_name }} · #{{ diffData.a.id }}</b><small>{{ formatTime(diffData.a.created_at) }}</small></div>
        <div><span>新记录</span><b>{{ diffData.b.device_name }} · #{{ diffData.b.id }}</b><small>{{ formatTime(diffData.b.created_at) }}</small></div>
        <div class="diff-stats"><span class="add">+{{ diffData.stats.add }}</span><span class="del">-{{ diffData.stats.delete }}</span></div>
      </div>
      <div v-if="diffData" class="diff-toolbar">
        <el-radio-group v-model="diffViewMode" size="small">
          <el-radio-button label="unified">统一视图</el-radio-button>
          <el-radio-button label="split">并排视图</el-radio-button>
        </el-radio-group>
        <el-checkbox v-model="diffOnlyChanges">仅看差异</el-checkbox>
      </div>
      <div v-if="diffData && diffViewMode === 'unified'" ref="diffViewRef" class="diff-view">
        <div v-for="(line, index) in visibleDiffLines" :key="index" :class="['diff-line', `is-${line.type}`]">
          <span class="diff-no">{{ line.old_no ?? '' }}</span>
          <span class="diff-no">{{ line.new_no ?? '' }}</span>
          <span class="diff-sign">{{ line.type === 'add' ? '+' : (line.type === 'delete' ? '-' : ' ') }}</span>
          <code>{{ line.text || ' ' }}</code>
        </div>
      </div>
      <div v-else-if="diffData" ref="diffSplitRef" class="diff-split">
        <div class="diff-split-head">
          <span>旧配置</span>
          <span>新配置</span>
        </div>
        <div v-for="(line, index) in visibleDiffLines" :key="index" class="diff-split-row">
          <div :class="['diff-side', 'old', `is-${line.type}`]">
            <span class="diff-no">{{ line.type === 'add' ? '' : (line.old_no ?? '') }}</span>
            <code>{{ line.type === 'add' ? '' : (line.text || ' ') }}</code>
          </div>
          <div :class="['diff-side', 'new', `is-${line.type}`]">
            <span class="diff-no">{{ line.type === 'delete' ? '' : (line.new_no ?? '') }}</span>
            <code>{{ line.type === 'delete' ? '' : (line.text || ' ') }}</code>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { assetApi, configBackupApi } from '@/api'
import { currentUser, can, downloadWithAuth } from '@/store/auth'
import { formatDateTime } from '@/utils/time'

const activeTab = ref('devices')
const loading = ref(false)
const devicesLoading = ref(false)
const recordsLoading = ref(false)
const batchBusy = ref(false)
const runningId = ref(null)
let batchPollTimer = null
const overview = ref(null)
const devices = ref([])
const deviceTotal = ref(0)
const devicePage = ref(1)
const devicePageSize = ref(12)
const devicePageSizes = [6, 12, 24, 48, 96]
const groups = ref([])
const records = ref([])
const recordGroups = ref([])
const recordTotal = ref(0)
const recordPage = ref(1)
const recordPageSize = 10
const selectedDevices = ref([])
const selectedRecords = ref([])

const allPageDevicesSelected = computed(() => (
  devices.value.length > 0 && devices.value.every((row) => isDeviceSelected(row))
))
const somePageDevicesSelected = computed(() => (
  devices.value.some((row) => isDeviceSelected(row)) && !allPageDevicesSelected.value
))

function toggleSelectPage(checked) {
  if (checked) {
    const map = new Map(selectedDevices.value.map((item) => [item.id, item]))
    devices.value.forEach((row) => map.set(row.id, row))
    selectedDevices.value = [...map.values()]
  } else {
    const ids = new Set(devices.value.map((row) => row.id))
    selectedDevices.value = selectedDevices.value.filter((item) => !ids.has(item.id))
  }
}

function clearDeviceSelection() {
  selectedDevices.value = []
}

function isDeviceSelected(row) {
  return selectedDevices.value.some((item) => item.id === row.id)
}

function toggleDeviceCard(row, checked) {
  if (checked) {
    if (!isDeviceSelected(row)) selectedDevices.value = [...selectedDevices.value, row]
  } else {
    selectedDevices.value = selectedDevices.value.filter((item) => item.id !== row.id)
  }
}

function isRecordSelected(row) {
  return selectedRecords.value.some((item) => item.id === row.id)
}

function toggleRecordCard(row, checked) {
  if (checked) {
    if (!isRecordSelected(row)) selectedRecords.value = [...selectedRecords.value, row]
  } else {
    selectedRecords.value = selectedRecords.value.filter((item) => item.id !== row.id)
  }
}

const batchAddVisible = ref(false)
const batchAddSaving = ref(false)
const batchCommands = reactive({})
const batchAddForm = reactive({
  backup_enabled: true,
  backup_username: '',
  backup_password: '',
  backup_port: 22,
  backup_interval_hours: 0,
})
const importVisible = ref(false)
const importTab = ref('existing')
const importLoading = ref(false)
const importSaving = ref(false)
const importCandidates = ref([])
const importSelected = ref([])
const importCommands = reactive({})
const importFilters = reactive({ keyword: '', group_id: null })
const importForm = reactive({
  name: '',
  ip_address: '',
  device_type: 'switch',
  vendor: '',
  model: '',
  group_id: null,
  backup_enabled: true,
  backup_username: '',
  backup_password: '',
  backup_port: 22,
  backup_interval_hours: 0,
  backup_command: '',
})
const allImportSelected = computed(() => (
  importCandidates.value.length > 0
  && importCandidates.value.every((row) => importSelected.value.includes(row.id))
))
const someImportSelected = computed(() => (
  importSelected.value.length > 0 && !allImportSelected.value
))
const importSelectedRows = computed(() => {
  const ids = new Set(importSelected.value)
  return importCandidates.value.filter((row) => ids.has(row.id))
})
const batchAllHaveCredential = computed(() => (
  selectedDevices.value.length > 0 && selectedDevices.value.every((item) => item.credential_id)
))
const importUsesCredentials = computed(() => (
  importTab.value === 'existing'
  && importSelectedRows.value.length > 0
  && importSelectedRows.value.every((item) => item.credential_id)
))
const deviceDialogVisible = ref(false)
const deviceSaving = ref(false)
const deviceForm = reactive({})
const recordDialogVisible = ref(false)
const recordDetail = ref(null)
const recordConfigPre = ref(null)
const diffViewRef = ref(null)
const diffSplitRef = ref(null)
const diffDialogVisible = ref(false)
const diffData = ref(null)
const diffViewMode = ref('unified')
const diffOnlyChanges = ref(false)
const visibleDiffLines = computed(() => {
  const lines = diffData.value?.lines || []
  return diffOnlyChanges.value ? lines.filter((line) => line.type !== 'equal') : lines
})
const canCompareRecords = computed(() => (
  selectedRecords.value.length === 2
  && selectedRecords.value.every((item) => item.status === 'success')
  && selectedRecords.value[0]?.device_id === selectedRecords.value[1]?.device_id
))
const settingsSaving = ref(false)
const isSuper = computed(() => !!currentUser.value?.is_superuser)
const deviceFilters = reactive({ group_id: null, keyword: '', status: '' })
const recordFilters = reactive({ device_id: null, status: '', order: 'desc' })
const settingsForm = reactive({
  config_backup_enabled: false,
  config_backup_interval_hours: 24,
  config_backup_retention_count: 30,
  config_backup_concurrency: 3,
  config_backup_timeout: 45,
  config_backup_storage_enabled: false,
  config_backup_storage_type: 'webdav',
  config_backup_webdav_url: '',
  config_backup_webdav_username: '',
  config_backup_webdav_password: '',
  config_backup_webdav_path: '/snmp-monitor/config-backups',
  config_backup_webdav_verify_tls: true,
  config_backup_sftp_host: '',
  config_backup_sftp_port: 22,
  config_backup_sftp_username: '',
  config_backup_sftp_password: '',
  config_backup_sftp_path: '/snmp-monitor/config-backups',
  config_backup_sftp_timeout: 15,
})

const editable = computed(() => can('config_backup:edit'))
const globalBackupEnabled = computed(() => Boolean(settingsForm.config_backup_enabled))
const globalBackupInterval = computed(() => Math.max(1, Number(settingsForm.config_backup_interval_hours) || 24))

function openGlobalBackupSettings() {
  deviceDialogVisible.value = false
  batchAddVisible.value = false
  importVisible.value = false
  activeTab.value = 'settings'
  loadOverview()
}

function formatTime(value) {
  return value ? formatDateTime(value) : '-'
}
function formatSize(value) {
  const size = Number(value || 0)
  if (!size) return '-'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(2)} MB`
}

async function loadOverview() {
  const res = await configBackupApi.overview()
  overview.value = res.data
  Object.assign(settingsForm, res.data.settings || {})
}

async function loadGroups() {
  try {
    const res = await assetApi.groups()
    const data = res.data
    groups.value = data.items || data || []
  } catch {
    groups.value = []
  }
}

async function loadDevices(page = devicePage.value) {
  devicePage.value = page
  devicesLoading.value = true
  try {
    const res = await configBackupApi.devices({
      group_id: deviceFilters.group_id || undefined,
      keyword: deviceFilters.keyword || undefined,
      status: deviceFilters.status || undefined,
      page: devicePage.value,
      page_size: devicePageSize.value,
    })
    devices.value = res.data.items || []
    deviceTotal.value = res.data.total || 0
    if (!devices.value.length && deviceTotal.value > 0 && devicePage.value > 1) {
      devicePage.value -= 1
      await loadDevices(devicePage.value)
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '加载设备失败')
  } finally {
    devicesLoading.value = false
  }
}

function applyDeviceFilters() {
  clearDeviceSelection()
  loadDevices(1)
}

function onDevicePageSizeChange(size) {
  devicePageSize.value = size
  loadDevices(1)
}

async function loadRecords(page = recordPage.value) {
  recordsLoading.value = true
  recordPage.value = page
  try {
    const res = await configBackupApi.recordGroups({
      device_id: recordFilters.device_id || undefined,
      status: recordFilters.status || undefined,
      order: recordFilters.order || 'desc',
      page,
      page_size: recordPageSize,
    })
    recordGroups.value = res.data.groups || []
    records.value = recordGroups.value.flatMap((group) => group.records || [])
    recordTotal.value = res.data.total || 0
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '加载备份记录失败')
  } finally {
    recordsLoading.value = false
  }
}

async function loadAll() {
  loading.value = true
  try {
    await Promise.all([loadOverview(), loadGroups(), loadDevices(), loadRecords(1)])
  } finally {
    loading.value = false
  }
}

function onTabChange(tab) {
  if (tab === 'records') loadRecords(1)
  if (tab === 'settings') loadOverview()
}

function openDeviceDialog(row) {
  Object.assign(deviceForm, {
    id: row.id,
    name: row.name,
    vendor: row.vendor,
    backup_enabled: row.backup_enabled,
    backup_username: row.backup_username || '',
    backup_password: '',
    backup_password_set: row.backup_password_set,
    backup_port: row.backup_port || 22,
    backup_command: row.backup_command || '',
    auto_command: row.auto_command || '',
    credential_id: row.credential_id || null,
    credential_name: row.credential_name || '',
    backup_interval_hours: row.backup_interval_hours || 0,
  })
  deviceDialogVisible.value = true
}

async function saveDevice() {
  if (!editable.value) {
    ElMessage.warning('没有编辑设备的权限')
    return
  }
  deviceSaving.value = true
  try {
    await configBackupApi.updateDevice(deviceForm.id, {
      backup_enabled: deviceForm.backup_enabled,
      backup_username: deviceForm.backup_username,
      backup_password: deviceForm.backup_password || undefined,
      backup_port: Number(deviceForm.backup_port) || 22,
      backup_command: deviceForm.backup_command,
      backup_interval_hours: Number(deviceForm.backup_interval_hours) || 0,
    })
    ElMessage.success('备份参数已保存')
    deviceDialogVisible.value = false
    await Promise.all([loadDevices(), loadOverview()])
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '保存失败')
  } finally {
    deviceSaving.value = false
  }
}

async function runNow(row) {
  try {
    await ElMessageBox.confirm(`立即通过 SSH 备份「${row.name}」的配置？可能需要等待几十秒。`, '手动设备配置备份', { type: 'warning' })
    runningId.value = row.id
    const res = await configBackupApi.run(row.id)
    if (res.data.record) row.last_backup = res.data.record
    ElMessage[res.data.record?.status === 'success' ? 'success' : 'error'](res.data.message || '备份完成')
    await Promise.all([loadDevices(), loadRecords(1), loadOverview()])
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(error?.response?.data?.detail || error?.message || '备份失败')
    }
  } finally {
    runningId.value = null
  }
}

function stopBatchPolling() {
  if (batchPollTimer) {
    clearInterval(batchPollTimer)
    batchPollTimer = null
  }
}

function startBatchPolling(deviceIds) {
  stopBatchPolling()
  const pendingIds = new Set(deviceIds)
  let attempts = 0
  batchPollTimer = setInterval(async () => {
    attempts += 1
    await Promise.allSettled([loadDevices(), loadOverview()])
    const running = devices.value.some((item) => (
      pendingIds.has(item.id) && item.last_backup?.status === 'running'
    ))
    if (attempts >= 10 || (attempts >= 4 && !running)) {
      stopBatchPolling()
      loadRecords(1)
    }
  }, 3000)
}

async function batchRun() {
  batchBusy.value = true
  const deviceIds = selectedDevices.value.map((item) => item.id)
  try {
    const res = await configBackupApi.batchRun(deviceIds)
    ElMessage.success(res.data.message || '已排队')
    startBatchPolling(deviceIds)
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '批量备份失败')
  } finally {
    batchBusy.value = false
  }
}

async function batchToggle(enabled) {
  try {
    const res = await configBackupApi.batchToggle(selectedDevices.value.map((item) => item.id), enabled)
    ElMessage.success(res.data.message || '已更新')
    await loadDevices()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '批量操作失败')
  }
}

function openBatchAdd() {
  Object.assign(batchAddForm, {
    backup_enabled: true,
    backup_username: '',
    backup_password: '',
    backup_port: 22,
    backup_interval_hours: 0,
  })
  Object.keys(batchCommands).forEach((key) => delete batchCommands[key])
  batchAddVisible.value = true
}

async function saveBatchAdd() {
  const allHaveCredential = selectedDevices.value.length > 0 && selectedDevices.value.every((item) => item.credential_id)
  if (!allHaveCredential && (!batchAddForm.backup_username || !batchAddForm.backup_password)) {
    ElMessage.warning('请填写统一的 SSH 用户名和密码，或先为所选设备关联设备凭据')
    return
  }
  batchAddSaving.value = true
  try {
    const res = await configBackupApi.batchAdd(selectedDevices.value.map((item) => item.id), {
      ...batchAddForm,
      backup_port: Number(batchAddForm.backup_port) || 22,
      backup_interval_hours: Number(batchAddForm.backup_interval_hours) || 0,
      device_commands: { ...batchCommands },
    })
    ElMessage.success(res.data.message || '已加入')
    batchAddVisible.value = false
    selectedDevices.value = []
    await Promise.all([loadDevices(), loadOverview()])
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '批量加入失败')
  } finally {
    batchAddSaving.value = false
  }
}

function resetImportForm() {
  Object.assign(importForm, {
    name: '',
    ip_address: '',
    device_type: 'switch',
    vendor: '',
    model: '',
    group_id: null,
    backup_enabled: true,
    backup_username: '',
    backup_password: '',
    backup_port: 22,
    backup_interval_hours: 0,
    backup_command: '',
  })
  Object.assign(importFilters, { keyword: '', group_id: null })
  importSelected.value = []
  Object.keys(importCommands).forEach((key) => delete importCommands[key])
}

function openImportDialog() {
  resetImportForm()
  importTab.value = 'existing'
  importVisible.value = true
  loadImportCandidates()
}

async function loadImportCandidates() {
  importLoading.value = true
  try {
    const res = await configBackupApi.devices({
      status: 'unmanaged',
      include_unmanaged: true,
      keyword: importFilters.keyword || undefined,
      group_id: importFilters.group_id || undefined,
      page: 1,
      page_size: 200,
    })
    importCandidates.value = res.data.items || []
    const ids = new Set(importCandidates.value.map((row) => row.id))
    importSelected.value = importSelected.value.filter((id) => ids.has(id))
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '加载现有资产失败')
  } finally {
    importLoading.value = false
  }
}

function toggleAllImport(checked) {
  importSelected.value = checked ? importCandidates.value.map((row) => row.id) : []
}

function importBackupPayload(perDevice = true) {
  const payload = {
    backup_enabled: importForm.backup_enabled,
    backup_username: importForm.backup_username,
    backup_password: importForm.backup_password,
    backup_port: Number(importForm.backup_port) || 22,
    backup_interval_hours: Number(importForm.backup_interval_hours) || 0,
  }
  if (perDevice) payload.device_commands = { ...importCommands }
  else if (importForm.backup_command) payload.backup_command = importForm.backup_command
  return payload
}

async function saveImport() {
  const allImportHaveCredential = importTab.value === 'existing'
    && importSelectedRows.value.length > 0
    && importSelectedRows.value.every((item) => item.credential_id)
  if (!allImportHaveCredential && (!importForm.backup_username || !importForm.backup_password)) {
    ElMessage.warning('请填写 SSH 用户名和密码，或先为所选设备关联设备凭据')
    return
  }
  importSaving.value = true
  try {
    if (importTab.value === 'existing') {
      if (!importSelected.value.length) {
        ElMessage.warning('请选择要加入备份的现有资产')
        return
      }
      const res = await configBackupApi.batchAdd(importSelected.value, importBackupPayload(true))
      ElMessage.success(res.data.message || '已加入备份')
    } else {
      if (!importForm.name.trim() || !importForm.ip_address.trim()) {
        ElMessage.warning('请填写设备名称和 IP 地址')
        return
      }
      const created = await assetApi.create({
        name: importForm.name.trim(),
        ip_address: importForm.ip_address.trim(),
        device_type: importForm.device_type,
        monitor_type: 'ping',
        vendor: importForm.vendor.trim() || undefined,
        model: importForm.model.trim() || undefined,
        group_id: importForm.group_id || undefined,
        description: '从设备配置备份自定义添加',
      })
      const deviceId = created.data?.id
      if (!deviceId) throw new Error('资产创建成功但未返回设备 ID')
      const res = await configBackupApi.batchAdd([deviceId], importBackupPayload(false))
      ElMessage.success(res.data.message || '资产已创建并加入备份')
    }
    importVisible.value = false
    importSelected.value = []
    await Promise.all([loadDevices(1), loadGroups(), loadOverview()])
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '添加备份设备失败')
  } finally {
    importSaving.value = false
  }
}

async function removeBackupDevice(row) {
  try {
    await ElMessageBox.confirm(
      `从设备配置备份中删除「${row.name}」？不会删除资产管理中的资产，也不会删除历史备份记录。`,
      '删除备份设备',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
    const res = await configBackupApi.batchRemove([row.id])
    ElMessage.success(res.data.message || '已从备份中删除')
    selectedDevices.value = selectedDevices.value.filter((item) => item.id !== row.id)
    await Promise.all([loadOverview(), loadDevices()])
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(error?.response?.data?.detail || error?.message || '删除失败')
    }
  }
}

async function batchDelete() {
  try {
    await ElMessageBox.confirm(
      `将选中的 ${selectedDevices.value.length} 台设备从设备配置备份中删除？只会清除备份配置，不会删除资产和历史备份记录。`,
      '批量删除备份设备',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
    const res = await configBackupApi.batchRemove(selectedDevices.value.map((item) => item.id))
    ElMessage.success(res.data.message || '已删除')
    selectedDevices.value = []
    await Promise.all([loadOverview(), loadDevices()])
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(error?.response?.data?.detail || error?.message || '删除失败')
    }
  }
}

function showDeviceRecords(row) {
  activeTab.value = 'records'
  recordFilters.device_id = row.id
  loadRecords(1)
}

async function openRecord(row) {
  try {
    const res = await configBackupApi.record(row.id)
    recordDetail.value = res.data
    recordDialogVisible.value = true
    await nextTick()
    if (recordConfigPre.value) recordConfigPre.value.scrollTop = 0
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '加载详情失败')
  }
}

function downloadRecord(row) {
  downloadWithAuth(configBackupApi.downloadUrl(row.id))
}

async function removeRecord(row) {
  try {
    await ElMessageBox.confirm(`删除备份记录 #${row.id}？`, '删除记录', { type: 'warning' })
    await configBackupApi.deleteRecord(row.id)
    ElMessage.success('已删除')
    await loadRecords(recordPage.value)
    await loadOverview()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(error?.response?.data?.detail || error?.message || '删除失败')
    }
  }
}

async function compareSelected() {
  if (!canCompareRecords.value) {
    ElMessage.warning('请选择同一资产的两条成功备份记录进行对比')
    return
  }
  const [a, b] = selectedRecords.value.slice().sort((left, right) => left.id - right.id)
  try {
    const res = await configBackupApi.diff(a.id, b.id)
    diffData.value = res.data
    diffViewMode.value = 'unified'
    diffOnlyChanges.value = false
    diffDialogVisible.value = true
    await nextTick()
    if (diffViewRef.value) diffViewRef.value.scrollTop = 0
    if (diffSplitRef.value) diffSplitRef.value.scrollTop = 0
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '对比失败')
  }
}

function exportRecords() {
  const params = {}
  if (selectedRecords.value.length) params.ids = selectedRecords.value.map((item) => item.id).join(',')
  else if (recordFilters.device_id) params.device_id = recordFilters.device_id
  downloadWithAuth(configBackupApi.exportUrl(params))
}

async function saveSettings() {
  settingsSaving.value = true
  try {
    await configBackupApi.saveSettings({ ...settingsForm })
    ElMessage.success('自动备份设置已保存')
    await loadOverview()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '保存失败')
  } finally {
    settingsSaving.value = false
  }
}

onMounted(loadAll)
onBeforeUnmount(stopBatchPolling)
</script>

<style scoped>
.config-backup-view {
  padding: 16px;
  background: #f5f7fa;
  min-height: 100%;
}
.cb-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; }
.cb-title { color: #1f3345; font-size: 18px; font-weight: 700; }
.cb-sub { margin-top: 5px; color: #8496a7; font-size: 12px; }
.cb-head-actions { display: flex; align-items: center; gap: 8px; }
.cb-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 10px; margin-bottom: 14px; }
.cb-stats > div { padding: 11px 14px; border: 1px solid #e5edf4; border-radius: 7px; background: #f8fbfe; }
.cb-stats span { display: block; color: #8b9bab; font-size: 10px; }
.cb-stats b { display: block; margin-top: 3px; color: #214667; font-size: 18px; }
.cb-stats b.ok { color: #1b9b6a; }
.cb-stats b.danger { color: #d9485f; }
.cb-toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 12px; }
.cb-toolbar > .el-select,
.cb-toolbar > .el-input { flex: 1 1 145px; min-width: 125px; max-width: 210px; }
.cb-batch-actions { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-left: auto; }
.record-asset-group { margin-bottom: 16px; border: 1px solid #e4edf4; border-radius: 8px; padding: 10px; background: #fbfdff; }
.record-asset-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 9px; padding-bottom: 8px; border-bottom: 1px dashed #dbe8f2; }
.record-asset-title { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.record-asset-title strong { color: #29445c; font-size: 13px; }
.record-asset-count { color: #7c91a3; font-size: 11px; white-space: nowrap; }
.record-asset-count b { color: #0f6fae; }
.cb-device-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(310px, 1fr)); gap: 10px; }
.cb-device-card { min-width: 0; padding: 11px 12px; border: 1px solid #e5edf4; border-radius: 8px; background: #f8fbfe; }
.cb-card-top { display: flex; align-items: center; flex-wrap: wrap; gap: 7px; margin-bottom: 8px; }
.cb-card-top :deep(.el-checkbox__label) { font-size: 11px; }
.cb-card-head { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
.cb-card-head strong { min-width: 0; overflow: hidden; color: #29445c; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
.cb-card-meta { display: flex; flex-wrap: wrap; gap: 5px 12px; margin-top: 5px; color: #7c8fa2; font-size: 10px; }
.cb-card-backup { margin-top: 8px; padding-top: 7px; border-top: 1px dashed #dce8f2; }
.cb-backup-head { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.cb-backup-label { color: #7c8ea1; font-size: 10px; }
.cb-card-backup .cb-time { display: inline; margin-left: 0; font-size: 11px; color: #526b80; }
.cb-card-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.selected-hint { color: #8b9bab; font-size: 11px; margin-right: 4px; }
.mb12 { margin-bottom: 12px; }
.cb-device-name { color: #29445c; font-weight: 600; }
.cb-device-ip { color: #8b9bab; font-family: Consolas, monospace; font-size: 10px; }
.cb-device-meta { margin-top: 2px; color: #9aaaba; font-size: 10px; }
.cb-time { display: block; margin-top: 3px; color: #8b9bab; font-size: 10px; }
.cb-error { color: #c4566b; font-size: 10px; line-height: 1.4; }
.cb-pager { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; margin-top: 12px; }
.import-toolbar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
.import-list { max-height: 300px; overflow-y: auto; border: 1px solid #e5edf4; border-radius: 8px; padding: 4px 10px; }
.import-item { display: flex; width: 100%; margin: 0; padding: 8px 4px; border-bottom: 1px solid #edf3f8; }
.import-item:last-child { border-bottom: 0; }
.import-item :deep(.el-checkbox__label) { display: flex; align-items: center; gap: 10px; width: 100%; min-width: 0; }
.import-name { font-weight: 600; color: #29445c; }
.import-ip { color: #8b9bab; font-family: Consolas, monospace; font-size: 11px; }
.import-ssh { margin-top: 12px; padding-top: 12px; border-top: 1px solid #e5edf4; }
.import-section-title { margin-bottom: 10px; color: #29445c; font-weight: 600; font-size: 13px; }
.import-ssh-form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: 18px; }
.import-ssh-form :deep(.el-form-item) { margin-bottom: 14px; }
.import-ssh-form :deep(.el-form-item__content) { width: 100%; }
.import-ssh-form :deep(.el-input-number),
.import-ssh-form :deep(.el-input) { width: 100%; }
.import-custom-form { max-width: 620px; }
.cb-settings-form { max-width: 620px; }
.form-help { margin-left: 8px; color: #8b9bab; font-size: 11px; }
.config-backup-view :deep(.el-form-item__content) { justify-content: flex-start; text-align: left; }
.config-backup-view :deep(.el-input-number) { text-align: left; }
.config-backup-view :deep(.el-input-number .el-input__inner) { padding-left: 8px; text-align: left; }
.config-backup-view :deep(.el-input-number .el-input__wrapper) { justify-content: flex-start; }
.form-help-block { display: block; flex: 0 0 100%; width: 100%; margin: 4px 0 0; color: #8b9bab; font-size: 11px; line-height: 1.7; text-align: left; white-space: normal; word-break: break-word; }
.form-help-action { margin-left: 4px; vertical-align: baseline; }
.cb-settings-form :deep(.el-form-item__content),
:deep(.el-form-item__content) { text-align: left; }
.record-detail-meta { display: flex; gap: 18px; flex-wrap: wrap; margin-bottom: 10px; color: #72879a; font-size: 11px; }
.config-pre { max-height: 58vh; overflow: auto; padding: 13px; border-radius: 6px; color: #d4ecf7; background: #0e1d28; font-family: Consolas, monospace; font-size: 11px; line-height: 1.55; }
.diff-head { display: flex; gap: 24px; align-items: flex-end; margin-bottom: 10px; }
.diff-head > div { display: flex; flex-direction: column; gap: 3px; }
.diff-head span, .diff-head small { color: #8b9bab; font-size: 10px; }
.diff-head b { color: #29445c; font-size: 12px; }
.diff-stats { margin-left: auto; flex-direction: row !important; gap: 10px !important; }
.diff-stats .add { color: #1b9b6a; font-weight: 700; }
.diff-stats .del { color: #d9485f; font-weight: 700; }
.diff-view { max-height: 65vh; overflow: auto; border: 1px solid #e4edf4; border-radius: 6px; background: #fbfdff; }
.diff-toolbar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 10px; }
.diff-split { max-height: 65vh; overflow: auto; border: 1px solid #e4edf4; border-radius: 6px; background: #fbfdff; }
.diff-split-head { position: sticky; top: 0; z-index: 1; display: grid; grid-template-columns: 1fr 1fr; background: #f1f7fc; color: #526b80; font-weight: 600; font-size: 11px; }
.diff-split-head span { padding: 6px 10px; border-bottom: 1px solid #e4edf4; }
.diff-split-head span + span { border-left: 1px solid #e4edf4; }
.diff-split-row { display: grid; grid-template-columns: 1fr 1fr; }
.diff-side { display: flex; align-items: flex-start; min-width: 0; min-height: 18px; font-family: Consolas, monospace; font-size: 11px; line-height: 1.55; }
.diff-side.old { border-right: 1px solid #e4edf4; }
.diff-side.old.is-delete { background: #fdecef; }
.diff-side.new.is-add { background: #eaf8ef; }
.diff-side code { min-width: 0; padding-right: 8px; white-space: pre-wrap; word-break: break-all; color: #33495b; }
.diff-line { display: flex; align-items: flex-start; min-height: 18px; font-family: Consolas, monospace; font-size: 11px; line-height: 1.55; }
.diff-line.is-add { background: #eaf8ef; }
.diff-line.is-delete { background: #fdecef; }
.diff-no { flex: 0 0 48px; padding: 0 6px; color: #a0b1bf; text-align: right; user-select: none; }
.diff-sign { flex: 0 0 16px; color: #8b9bab; }
.diff-line code { white-space: pre-wrap; word-break: break-all; color: #33495b; }

@media (max-width: 1199px) {
  .cb-toolbar > .el-select,
  .cb-toolbar > .el-input { flex: 1 1 140px; max-width: none; }
  .cb-batch-actions { width: 100%; margin-left: 0; justify-content: flex-start; }
  .cb-device-cards { grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); }
  .cb-pager { justify-content: center; }
  .import-ssh-form { grid-template-columns: 1fr; }
}

.batch-command-list { width: 100%; display: flex; flex-direction: column; gap: 7px; max-height: 300px; overflow: auto; }
.batch-command-title { color: #536b7c; font-size: 12px; font-weight: 600; }
.import-command-list { margin-top: 10px; padding-top: 8px; border-top: 1px dashed #dbe7f0; }
.batch-command-item { display: flex; flex-direction: column; gap: 4px; padding: 7px 8px; border: 1px solid #e5eef6; border-radius: 6px; background: #fbfdff; }
.batch-command-meta { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; font-size: 11px; color: #536b7c; }
.batch-command-meta b { color: #334155; font-size: 12px; }
.batch-command-meta code { color: #0f6fae; background: #eef7fd; padding: 1px 4px; border-radius: 3px; word-break: break-all; }
</style>
