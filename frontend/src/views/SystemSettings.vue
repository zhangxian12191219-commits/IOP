<template>
  <div class="settings-view">
    <el-card>
      <template #header>
        <div class="card-header">
          <div class="title">
            <span>{{ t('settings.title') }}</span>
            <el-tag size="small" type="info" effect="plain">{{ t('settings.headerHint') }}</el-tag>
          </div>
          <div class="actions">
            <el-button v-if="currentUser?.is_superuser" size="small" @click="$router.push('/system/license')">
              <el-icon><Key /></el-icon>{{ t('menu.license') }}
            </el-button>
            <el-button size="small" @click="activeTab === 'update' ? loadUpdateInfo() : activeTab === 'time' ? loadTimeStatus() : activeTab === 'startup' ? loadStartup() : loadAll()" :loading="activeTab === 'time' ? timeLoading : loading" v-if="activeTab !== 'users'">
              <el-icon><Refresh /></el-icon>{{ t('common.refresh') }}
            </el-button>
            <el-button v-if="canEdit && activeTab !== 'users' && activeTab !== 'status' && activeTab !== 'startup' && activeTab !== 'time' && activeTab !== 'cluster' && activeTab !== 'network' && activeTab !== 'update'" type="primary" size="small" :loading="saving" @click="saveAll">
              <el-icon><Check /></el-icon>{{ t('settings.saveConfig') }}
            </el-button>
          </div>
        </div>
      </template>

      <el-alert
        v-if="!canEdit"
        type="info"
        :closable="false"
        show-icon
        title="系统关键配置为只读"
        description="只有超级管理员可以修改系统配置、登录安全策略和授权信息。当前账号可以查看，但不能保存或导入配置。"
        class="settings-readonly-alert"
      />

      <el-skeleton v-if="loading && !loaded" :rows="8" animated />

      <el-tabs v-else v-model="activeTab">
        <!-- ==================== 当前状态 ==================== -->
        <el-tab-pane :label="t('settings.tabStatus')" name="status">
          <div class="host-status-head">
            <div>
              <strong>当前主机运行状态</strong>
              <span v-if="hostStatus">采集于 {{ hostStatus.collected_at?.replace('T', ' ') }} · {{ hostStatus.host?.hostname }}</span>
              <span v-else>CPU、内存、磁盘、服务与网卡状态（Windows / Linux）</span>
            </div>
            <el-button size="small" :loading="hostStatusLoading" @click="loadHostStatus">
              <el-icon><Refresh /></el-icon>刷新主机状态
            </el-button>
          </div>

          <el-alert v-if="hostStatusError" type="error" :closable="false" show-icon :title="hostStatusError" class="host-status-error" />

          <div v-if="hostStatus" v-loading="hostStatusLoading" class="host-status-wrap">
            <div class="host-metric-grid">
              <div class="host-metric-card">
                <div class="host-metric-title"><span>CPU 使用率</span><b>{{ hostStatus.cpu?.percent }}%</b></div>
                <el-progress :percentage="Number(hostStatus.cpu?.percent || 0)" :stroke-width="7" :show-text="false" :status="usageStatus(hostStatus.cpu?.percent)" />
                <div class="host-metric-foot">{{ hostStatus.cpu?.logical }} 逻辑核 · {{ hostStatus.cpu?.physical }} 物理核<span v-if="hostStatus.cpu?.frequency_mhz"> · {{ hostStatus.cpu.frequency_mhz }} MHz</span></div>
                <div v-if="hostStatus.cpu?.load_average?.length" class="host-metric-foot">负载 {{ hostStatus.cpu.load_average.join(' / ') }}</div>
              </div>
              <div class="host-metric-card">
                <div class="host-metric-title"><span>内存使用率</span><b>{{ hostStatus.memory?.percent }}%</b></div>
                <el-progress :percentage="Number(hostStatus.memory?.percent || 0)" :stroke-width="7" :show-text="false" :status="usageStatus(hostStatus.memory?.percent)" />
                <div class="host-metric-foot">{{ formatBytes(hostStatus.memory?.used) }} / {{ formatBytes(hostStatus.memory?.total) }}<span v-if="hostStatus.memory?.swap_total"> · Swap {{ hostStatus.memory.swap_percent }}%</span></div>
                <div class="host-metric-foot">进程占用 {{ formatBytes(hostStatus.process?.rss) }}</div>
              </div>
              <div class="host-metric-card">
                <div class="host-metric-title"><span>磁盘整体使用率</span><b>{{ diskSummary.percent }}%</b></div>
                <el-progress :percentage="diskSummary.percent" :stroke-width="7" :show-text="false" :status="usageStatus(diskSummary.percent)" />
                <div class="host-metric-foot">{{ formatBytes(diskSummary.used) }} / {{ formatBytes(diskSummary.total) }}</div>
                <div class="host-metric-foot">{{ hostStatus.disks?.length || 0 }} 个磁盘卷 · 可用 {{ formatBytes(diskSummary.free) }}</div>
              </div>
              <div class="host-metric-card">
                <div class="host-metric-title"><span>运行时长</span><b class="host-uptime">{{ formatUptime(hostStatus.host?.uptime_seconds) }}</b></div>
                <div class="host-metric-foot host-os">{{ hostStatus.host?.platform }} {{ hostStatus.host?.platform_release }}</div>
                <div class="host-metric-foot">{{ hostStatus.host?.architecture }} · Python {{ hostStatus.host?.python }}</div>
                <div class="host-metric-foot">应用进程 PID {{ hostStatus.process?.pid }} · 已运行 {{ formatUptime(hostStatus.host?.app_uptime_seconds) }}</div>
              </div>
            </div>

            <div class="host-panel web-health-panel">
              <div class="host-panel-head">
                <div>
                  <strong>Web 服务与中间件</strong>
                  <span class="muted">登录网关、数据库与缓存实时状态</span>
                </div>
                <span class="web-health-live" :class="hostStatus.web?.status === 'running' ? 'ok' : 'bad'">
                  <i></i>{{ hostStatus.web?.status === 'running' ? 'Web 服务正常' : 'Web 服务异常' }}
                </span>
              </div>
              <div class="web-health-grid">
                <div class="web-health-card" :class="hostStatus.web?.status === 'running' ? 'is-ok' : 'is-bad'">
                  <div class="web-health-icon"><el-icon><Monitor /></el-icon></div>
                  <div class="web-health-main">
                    <div class="web-health-title"><strong>Web 登录服务</strong><el-tag :type="hostStatus.web?.status === 'running' ? 'success' : 'danger'" size="small">{{ hostStatus.web?.status === 'running' ? '运行中' : '异常' }}</el-tag></div>
                    <span>{{ String(hostStatus.web?.protocol || 'http').toUpperCase() }} :{{ hostStatus.web?.login_port || 80 }} · 内部 API :{{ hostStatus.web?.internal_port || 8000 }}</span>
                    <div class="web-health-chips">
                      <span v-for="listener in hostStatus.web?.listeners || []" :key="`${listener.protocol}-${listener.port}`" class="web-listener-chip">{{ listener.protocol?.toUpperCase() }} :{{ listener.port }}{{ listener.mode ? ` · ${listener.mode === 'login' ? '登录' : listener.mode}` : '' }}</span>
                      <span v-if="!(hostStatus.web?.listeners || []).length" class="web-listener-chip is-muted">无监听入口</span>
                    </div>
                  </div>
                </div>
                <div class="web-health-card" :class="hostStatus.database?.status === 'connected' ? 'is-ok' : 'is-bad'">
                  <div class="web-health-icon"><el-icon><Coin /></el-icon></div>
                  <div class="web-health-main">
                    <div class="web-health-title"><strong>数据库</strong><el-tag :type="hostStatus.database?.status === 'connected' ? 'success' : 'danger'" size="small">{{ hostStatus.database?.status === 'connected' ? '已连接' : '异常' }}</el-tag></div>
                    <span>{{ hostStatus.database?.type || '未知类型' }}{{ hostStatus.database?.latency_ms ? ` · ${hostStatus.database.latency_ms}ms` : '' }}</span>
                    <div class="web-health-chips"><span class="web-listener-chip">连接探测正常</span></div>
                  </div>
                </div>
                <div class="web-health-card" :class="hostStatus.cache?.backend === 'disabled' ? 'is-warn' : 'is-ok'">
                  <div class="web-health-icon"><el-icon><Connection /></el-icon></div>
                  <div class="web-health-main">
                    <div class="web-health-title"><strong>缓存 / Redis</strong><el-tag :type="hostStatus.cache?.backend === 'redis' ? 'success' : 'info'" size="small">{{ hostStatus.cache?.backend === 'redis' ? 'Redis' : hostStatus.cache?.backend === 'memory' ? '内存缓存' : '未启用' }}</el-tag></div>
                    <span>{{ hostStatus.cache?.backend === 'redis' ? (hostStatus.cache?.redis_version || 'Redis 已连接') : 'Redis 未配置时自动使用内存缓存' }}</span>
                    <div class="web-health-chips">
                      <span class="web-listener-chip">命中 {{ hostStatus.cache?.stats?.hits || 0 }}</span>
                      <span class="web-listener-chip">错误 {{ hostStatus.cache?.stats?.errors || 0 }}</span>
                    </div>
                  </div>
                </div>
              </div>
              <div class="web-health-url">当前访问入口：{{ currentOrigin }}<span v-if="hostStatus.web?.self_signed"> · 当前 HTTPS 使用自签名证书</span></div>
            </div>

            <div class="host-panel host-status-table host-port-panel">
              <div class="host-panel-head">
                <div>
                  <strong>端口状态监控</strong>
                  <span class="muted">监听 {{ hostStatus.ports?.listening || 0 }} / 共 {{ hostStatus.ports?.total || 0 }} 个 · {{ (hostStatus.ports?.checked_at || '').replace('T', ' ') }}</span>
                </div>
                <div class="host-port-actions">
                  <el-radio-group v-model="portScope" size="small">
                    <el-radio-button value="all">全部</el-radio-button>
                    <el-radio-button value="expected">关键端口</el-radio-button>
                  </el-radio-group>
                  <el-button size="small" :loading="hostStatusLoading" @click="loadHostStatus"><el-icon><Refresh /></el-icon>刷新</el-button>
                </div>
              </div>
              <el-alert v-if="hostStatus.ports?.psutil_error" type="info" :closable="false" show-icon :title="hostStatus.ports.psutil_error" class="port-psutil-alert" />
              <el-table :data="displayPorts" size="small" border max-height="360">
                <el-table-column label="端口" width="88">
                  <template #default="{ row }"><b class="host-port-number">{{ row.port }}</b></template>
                </el-table-column>
                <el-table-column prop="service" label="用途" min-width="175" show-overflow-tooltip />
                <el-table-column prop="protocol" label="协议" width="70" />
                <el-table-column label="监听状态" width="100">
                  <template #default="{ row }">
                    <el-tag :type="portStatusType(row)" size="small" effect="plain">{{ portStatusText(row) }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="绑定地址" min-width="130">
                  <template #default="{ row }">
                      <span v-if="row.addresses?.length" class="host-port-address">{{ row.addresses.join(', ') }}</span>
                    <span v-else class="muted">—</span>
                    <el-tag v-if="row.bind_all && row.scope !== 'internal'" size="small" type="warning" effect="plain" class="port-bind-all">对外</el-tag>
                    <el-tag v-else-if="row.scope === 'internal'" size="small" type="info" effect="plain" class="port-bind-all">内部</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="process" label="进程" min-width="120" show-overflow-tooltip>
                  <template #default="{ row }">{{ row.process || '—' }}<span v-if="row.pid" class="host-port-pid">PID {{ row.pid }}</span></template>
                </el-table-column>
                <el-table-column label="类型" width="82">
                  <template #default="{ row }">
                    <el-tag v-if="row.critical" size="small" type="danger" effect="plain">关键</el-tag>
                    <el-tag v-else-if="row.expected" size="small" type="info" effect="plain">常用</el-tag>
                    <span v-else class="muted">其他</span>
                  </template>
                </el-table-column>
              </el-table>
              <div v-if="!displayPorts.length" class="host-port-empty">暂未读取到端口信息</div>
              <div class="host-port-note">内部 API 端口只接受本机/登录网关转发，外部客户端请使用 HTTP/HTTPS 登录入口。</div>
            </div>

            <div class="host-status-two-col">
              <div class="host-panel">
                <div class="host-panel-head"><strong>服务启动状态</strong><span class="muted">应用内部服务与后台任务</span></div>
                <div class="host-service-list">
                  <div v-for="service in hostStatus.services" :key="service.key" class="host-service-item">
                    <span class="host-service-dot" :class="`is-${service.status}`"></span>
                    <div class="host-service-main"><strong>{{ service.name }}</strong><small>{{ service.detail }}</small></div>
                    <el-tag :type="serviceStatusType(service.status)" size="small">{{ serviceStatusText(service.status) }}</el-tag>
                  </div>
                </div>
              </div>
              <div class="host-panel">
                <div class="host-panel-head"><strong>主机信息</strong><span class="muted">当前运行实例</span></div>
                <div class="host-info-list">
                  <div><span>主机名</span><b>{{ hostStatus.host?.hostname }}</b></div>
                  <div><span>操作系统</span><b>{{ hostStatus.host?.platform }} {{ hostStatus.host?.platform_release }}</b></div>
                  <div><span>内核版本</span><b>{{ hostStatus.host?.platform_version }}</b></div>
                  <div><span>系统架构</span><b>{{ hostStatus.host?.architecture }}</b></div>
                  <div><span>启动时间</span><b>{{ (hostStatus.host?.boot_time || '').replace('T', ' ') }}</b></div>
                  <div><span>数据库</span><b>{{ hostStatus.database?.status === 'connected' ? `已连接 · ${hostStatus.database?.latency_ms}ms` : '异常' }}</b></div>
                </div>
              </div>
            </div>

            <div class="host-panel host-status-table">
              <div class="host-panel-head"><strong>磁盘容量使用</strong><span class="muted">物理磁盘卷使用率</span></div>
              <el-table :data="hostStatus.disks || []" size="small" border>
                <el-table-column prop="mountpoint" label="挂载点 / 盘符" min-width="150" />
                <el-table-column prop="device" label="设备" min-width="150" show-overflow-tooltip />
                <el-table-column prop="fstype" label="文件系统" width="115" />
                <el-table-column label="已用 / 总量" width="170">
                  <template #default="{ row }">{{ formatBytes(row.used) }} / {{ formatBytes(row.total) }}</template>
                </el-table-column>
                <el-table-column label="使用率" min-width="180">
                  <template #default="{ row }">
                    <el-progress :percentage="Number(row.percent || 0)" :stroke-width="7" />
                  </template>
                </el-table-column>
              </el-table>
            </div>

            <div class="host-panel host-status-table">
              <div class="host-panel-head"><strong>网卡状态</strong><span class="muted">连接状态、地址、速率与错误包</span></div>
              <el-table :data="hostStatus.network || []" size="small" border max-height="340">
                <el-table-column label="网卡" min-width="150">
                  <template #default="{ row }">
                    <strong class="host-nic-name">{{ row.name }}</strong>
                    <small class="host-nic-mac">{{ row.mac || '无 MAC' }}</small>
                  </template>
                </el-table-column>
                <el-table-column label="状态" width="86">
                  <template #default="{ row }"><el-tag :type="row.is_up ? 'success' : 'info'" size="small">{{ row.is_up ? '已连接' : '未连接' }}</el-tag></template>
                </el-table-column>
                <el-table-column label="速率" width="85"><template #default="{ row }">{{ row.speed_mbps ? `${row.speed_mbps} Mbps` : '-' }}</template></el-table-column>
                <el-table-column label="IP 地址" min-width="190">
                  <template #default="{ row }"><span v-for="ip in row.ips" :key="ip" class="host-ip">{{ ip }}</span><span v-if="!row.ips?.length">-</span></template>
                </el-table-column>
                <el-table-column label="实时流量" width="165">
                  <template #default="{ row }">↓ {{ formatBps(row.rx_bytes_per_second) }} / ↑ {{ formatBps(row.tx_bytes_per_second) }}</template>
                </el-table-column>
                <el-table-column label="累计收发" width="150">
                  <template #default="{ row }">↓ {{ formatBytes(row.bytes_recv) }} / ↑ {{ formatBytes(row.bytes_sent) }}</template>
                </el-table-column>
                <el-table-column label="错误/丢包" width="105">
                  <template #default="{ row }">{{ (row.errors_in || 0) + (row.errors_out || 0) }} / {{ (row.drops_in || 0) + (row.drops_out || 0) }}</template>
                </el-table-column>
              </el-table>
            </div>
          </div>

          <el-divider content-position="left">系统配置与实例状态</el-divider>
          <el-descriptions :column="2" border>
            <el-descriptions-item :label="t('settings.systemName')">{{ form.system_name }}</el-descriptions-item>
            <el-descriptions-item :label="t('settings.language')">{{ form.language }}</el-descriptions-item>
            <el-descriptions-item :label="t('settings.timezone')">{{ form.timezone }}</el-descriptions-item>
            <el-descriptions-item :label="t('settings.refreshInterval')">{{ form.refresh_interval }} {{ t('settings.unitSeconds') }}</el-descriptions-item>
            <el-descriptions-item :label="t('settings.captchaEnabled')">{{ form.captcha_enabled ? t('settings.on') : t('settings.off') }}</el-descriptions-item>
            <el-descriptions-item :label="t('settings.autoLogin')">{{ form.auto_login ? t('settings.on') : t('settings.off') }}</el-descriptions-item>
            <el-descriptions-item :label="t('settings.autoLogoutStatus')">
              {{ form.auto_logout_minutes > 0 ? t('settings.autoLogoutValue', { minutes: form.auto_logout_minutes }) : t('settings.noAutoLogout') }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('settings.collectionInterval')">{{ form.collection_interval }} {{ t('settings.unitSeconds') }}</el-descriptions-item>
            <el-descriptions-item :label="t('settings.database')">
              <el-tag v-if="health" :type="health.database === 'ok' ? 'success' : 'danger'" size="small">
                {{ health.database === 'ok' ? t('settings.connected') : t('settings.abnormal') }}
              </el-tag>
              <span class="muted" style="margin-left: 8px">{{ health?.database_type || '-' }}</span>
            </el-descriptions-item>
            <el-descriptions-item :label="t('settings.cache')">
              <el-tag v-if="health" :type="health.cache?.backend === 'redis' ? 'success' : 'info'" size="small">
                {{ cacheBackendText }}
              </el-tag>
              <span class="muted" style="margin-left: 8px">{{ cacheStatsText }}</span>
            </el-descriptions-item>
            <el-descriptions-item :label="t('settings.instanceId')">
              {{ health?.instance_id || '-' }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('settings.backgroundTasks')">
              <el-tag :type="health?.background_tasks ? 'success' : 'info'" size="small">
                {{ health?.background_tasks ? t('settings.enabled') : t('settings.workerOnly') }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item :label="t('settings.systemdWatchdog')">
              {{ health?.systemd_watchdog ? t('settings.enabled') : t('settings.disabled') }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('settings.currentAccount')" :span="2">
              {{ currentUser.real_name || currentUser.username }}
              <el-tag v-if="currentUser.is_superuser" type="danger" size="small">{{ t('settings.superAdmin') }}</el-tag>
            </el-descriptions-item>
          </el-descriptions>
        </el-tab-pane>

        <!-- ==================== 开机自启 ==================== -->
        <el-tab-pane label="开机自启" name="startup">
          <div class="startup-panel" v-loading="startupLoading">
            <div class="startup-head">
              <div>
                <strong>系统开机自启</strong>
                <span>控制本系统是否随服务器 / 主机开机自动启动，不会影响当前正在运行的服务。</span>
              </div>
              <el-tag :type="startupInfo?.enabled ? 'success' : 'info'" effect="plain">
                {{ startupInfo?.enabled ? '已启用' : '未启用' }}
              </el-tag>
            </div>

            <el-alert
              v-if="startupInfo && !startupInfo.supported"
              type="warning"
              :closable="false"
              show-icon
              :title="startupInfo.message || '当前环境不支持一键设置开机自启'"
            />

            <div v-if="startupInfo" class="startup-status-grid">
              <div><span>运行平台</span><b>{{ startupInfo.platform || '未知' }}</b></div>
              <div><span>管理方式</span><b>{{ startupInfo.mode === 'systemd' ? 'systemd 服务' : startupInfo.mode === 'startup-registry' ? 'Windows 启动项' : startupInfo.mode }}</b></div>
              <div><span>服务 / 启动项</span><b>{{ startupInfo.service || '-' }}</b></div>
              <div><span>当前进程</span><b :class="startupInfo.active ? 'ok' : ''">{{ startupInfo.active ? '运行中' : (startupInfo.supported ? '未检测到运行中服务' : '未知') }}</b></div>
            </div>

            <div v-if="startupInfo?.command" class="startup-command">
              <span>Windows 启动命令</span>
              <code>{{ startupInfo.command }}</code>
            </div>

            <div class="startup-actions">
              <div>
                <strong>随系统启动</strong>
                <small>{{ startupInfo?.enabled ? '开机后自动启动本系统' : '开机后需要手动启动本系统' }}</small>
              </div>
              <el-switch
                :model-value="!!startupInfo?.enabled"
                :loading="startupSaving"
                :disabled="!canEdit || !startupInfo?.supported || startupSaving"
                active-text="启用"
                inactive-text="停用"
                @change="toggleStartup"
              />
            </div>

            <div class="startup-hint">
              <p>Linux 使用 systemd 服务管理；Windows 使用当前用户登录启动项。</p>
              <p>部署环境请确认服务单元已安装：<code>systemctl enable {{ startupInfo?.service || 'snmp-nms' }}</code>。修改后下一次开机生效，立即启动/停止请使用服务管理命令。</p>
              <p v-if="startupInfo?.message">{{ startupInfo.message }}</p>
            </div>
          </div>
        </el-tab-pane>

        <!-- ==================== 基本设置 ==================== -->
        <el-tab-pane :label="t('settings.tabBasic')" name="basic">
          <el-form :model="form" label-width="150px" class="settings-form" :disabled="!canEdit">
            <el-form-item :label="t('settings.systemName')">
              <el-input v-model="form.system_name" maxlength="60" show-word-limit style="max-width: 420px" />
              <div class="form-tip">{{ t('settings.systemNameTip') }}</div>
            </el-form-item>

            <el-form-item :label="t('settings.loginSubtitle')">
              <el-input v-model="form.login_subtitle" maxlength="200" show-word-limit style="max-width: 680px" />
              <div class="form-tip">{{ t('settings.loginSubtitleTip') }}</div>
            </el-form-item>

            <el-form-item :label="t('settings.systemLogo')">
              <div class="logo-setting">
                <div class="logo-preview">
                  <img v-if="form.system_logo" :src="form.system_logo" alt="system logo" />
                  <img v-else src="/logo-default.svg" alt="default system logo" />
                </div>
                <div class="logo-setting-actions">
                  <input
                    ref="logoFileRef"
                    type="file"
                    accept="image/png,image/jpeg,image/webp,image/gif,image/x-icon,.png,.jpg,.jpeg,.webp,.gif,.ico"
                    style="display: none"
                    @change="onLogoFileChange"
                  />
                  <el-button size="small" :loading="logoUploading" :disabled="!canEdit" @click="pickLogo">
                    <el-icon><Upload /></el-icon>{{ t('settings.uploadLogo') }}
                  </el-button>
                  <el-button
                    v-if="form.system_logo"
                    size="small"
                    type="danger"
                    plain
                    :disabled="!canEdit || logoUploading"
                    @click="resetLogo"
                  >
                    {{ t('settings.resetLogo') }}
                  </el-button>
                  <div class="form-tip">{{ t('settings.systemLogoTip') }}</div>
                </div>
              </div>
            </el-form-item>

            <el-divider content-position="left">{{ t('settings.copyrightSection') }}</el-divider>
            <el-form-item>
              <el-alert
                type="info"
                :closable="false"
                show-icon
                title="版权信息默认锁定，修改需要授权签发平台生成的品牌特权口令。"
                :description="copyrightUnlocked ? `已解锁，剩余约 ${copyrightUnlockText} 分钟` : '特权口令绑定本机机器码，由销售方在授权签发平台生成。'"
              />
              <div class="copyright-privilege-actions">
                <el-button size="small" type="primary" plain @click="openCopyrightPrivilege">
                  {{ copyrightUnlocked ? '重新验证特权口令' : '验证品牌特权口令' }}
                </el-button>
                <el-button v-if="copyrightUnlocked" link size="small" @click="lockCopyrightPrivilege">立即锁定</el-button>
              </div>
            </el-form-item>
            <el-form-item :label="t('settings.copyrightEnabled')">
              <el-switch v-model="form.copyright_enabled" :disabled="!canEdit || !copyrightUnlocked" />
              <div class="form-tip">{{ t('settings.copyrightEnabledTip') }}</div>
            </el-form-item>
            <el-form-item :label="t('settings.copyrightName')">
              <el-input
                v-model="form.copyright_name"
                maxlength="60"
                show-word-limit
                style="max-width: 560px"
                :disabled="!canEdit || !copyrightUnlocked"
                :placeholder="t('settings.copyrightNamePlaceholder')"
              />
              <div class="form-tip">{{ t('settings.copyrightNameTip') }}</div>
            </el-form-item>
            <el-form-item :label="t('settings.copyrightColor')">
              <el-color-picker v-model="form.copyright_color" color-format="hex" :disabled="!canEdit || !copyrightUnlocked" />
              <span
                class="copyright-preview"
                :style="{ color: form.copyright_color || '#94a3b8' }"
              >
                {{ copyrightPreview }}
              </span>
              <div class="form-tip">{{ t('settings.copyrightColorTip') }}</div>
            </el-form-item>

            <el-form-item :label="t('settings.language')">
              <el-select v-model="form.language" style="width: 220px">
                <el-option
                  v-for="item in languageOptions"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
              <div class="form-tip">{{ t('settings.languageTip') }}</div>
            </el-form-item>

            <el-form-item :label="t('settings.timezone')">
              <el-select v-model="form.timezone" filterable style="width: 260px">
                <el-option
                  v-for="item in timezoneOptions"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
              <div class="form-tip">{{ t('settings.timezoneTip') }}</div>
            </el-form-item>

            <el-form-item :label="t('settings.refreshInterval')">
              <el-input-number v-model="form.refresh_interval" :min="5" :max="600" :step="5" />
              <span class="unit">{{ t('settings.unitSeconds') }}</span>
              <div class="form-tip">{{ t('settings.refreshTip') }}</div>
            </el-form-item>

            <el-form-item :label="t('settings.alertSound')">
              <el-switch v-model="alertSoundEnabled" />
              <div class="form-tip">{{ t('settings.alertSoundTip') }}</div>
            </el-form-item>
            <el-form-item :label="t('settings.alertSoundInterval')">
              <el-input-number v-model="form.alert_sound_interval" :min="10" :max="3600" :step="10" />
              <span class="unit">{{ t('settings.unitSeconds') }}</span>
              <div class="form-tip">{{ t('settings.alertSoundIntervalTip') }}</div>
            </el-form-item>
            <el-form-item :label="t('settings.alertSoundFile')">
              <div class="sound-level-list">
                <div v-for="level in SOUND_LEVELS" :key="level.value" class="sound-level-row">
                  <div class="sound-level-name">
                    <b>{{ t(level.labelKey) }}</b>
                    <small>{{ t(level.builtinKey) }}</small>
                  </div>
                  <el-tag
                    size="small"
                    :type="soundLevelInfo(level.value).custom ? 'success' : 'info'"
                    class="sound-level-tag"
                  >
                    {{ soundLevelInfo(level.value).custom
                      ? soundLevelInfo(level.value).filename
                      : t('settings.builtinSound') }}
                  </el-tag>
                  <div class="sound-level-actions">
                    <el-button
                      size="small"
                      :disabled="!canEdit || soundUploading"
                      :loading="soundUploading && soundEditLevel === level.value"
                      @click="pickSoundFile(level.value)"
                    >
                      {{ t('settings.uploadSound') }}
                    </el-button>
                    <el-button
                      size="small"
                      :disabled="!alertSoundEnabled"
                      @click="testSound(level.value)"
                    >
                      {{ t('settings.testSound') }}
                    </el-button>
                    <el-button
                      v-if="soundLevelInfo(level.value).custom"
                      size="small"
                      type="danger"
                      plain
                      :disabled="!canEdit"
                      @click="resetSound(level.value)"
                    >
                      {{ t('settings.resetSound') }}
                    </el-button>
                  </div>
                </div>
              </div>
              <input
                ref="soundFileRef"
                type="file"
                accept="audio/mpeg,audio/wav,audio/ogg,audio/mp4,.mp3,.wav,.ogg,.m4a"
                style="display: none"
                @change="onSoundFileChange"
              />
              <div class="form-tip">{{ t('settings.soundFileTip') }}</div>
              <div class="sound-level-tip">
                {{ t('settings.soundLevelTip') }}
              </div>
              <div class="sound-reset-all">
                <el-button
                  size="small"
                  type="warning"
                  plain
                  :disabled="!canEdit || soundUploading"
                  @click="resetAllSounds"
                >
                  {{ t('settings.alertSoundResetAll') }}
                </el-button>
                <span class="form-tip">{{ t('settings.alertSoundResetAllTip') }}</span>
              </div>
            </el-form-item>

            <el-form-item :label="t('settings.alertBroadcast')">
              <div class="broadcast-settings">
                <div class="broadcast-head">
                  <el-switch v-model="form.alert_broadcast_enabled" />
                  <span class="broadcast-desc">{{ t('settings.alertBroadcastTip') }}</span>
                </div>
                <template v-if="form.alert_broadcast_enabled">
                  <div class="broadcast-options">
                    <el-checkbox v-model="form.alert_broadcast_counts">
                      {{ t('settings.alertBroadcastCounts') }}
                    </el-checkbox>
                    <el-checkbox v-model="form.alert_broadcast_details">
                      {{ t('settings.alertBroadcastDetails') }}
                    </el-checkbox>
                  </div>
                  <div class="broadcast-level-row">
                    <span class="broadcast-label">{{ t('settings.alertBroadcastLevels') }}</span>
                    <el-checkbox-group v-model="broadcastLevels">
                      <el-checkbox-button
                        v-for="item in BROADCAST_LEVEL_OPTIONS"
                        :key="item.value"
                        :label="item.value"
                      >
                        {{ t(item.labelKey) }}
                      </el-checkbox-button>
                    </el-checkbox-group>
                  </div>
                  <div class="broadcast-level-row">
                    <span class="broadcast-label">{{ t('settings.alertBroadcastScope') }}</span>
                    <span class="broadcast-desc">{{ t('settings.alertBroadcastAll') }}</span>
                    <el-button size="small" plain :disabled="!canEdit || !alertSoundEnabled" @click="previewBroadcast">
                      {{ t('settings.alertBroadcastPreview') }}
                    </el-button>
                  </div>
                  <div class="form-tip">{{ t('settings.alertBroadcastExampleTip') }}</div>
                </template>
              </div>
            </el-form-item>

            <el-form-item label="活动告警再提醒">
              <div class="realert-setting">
                <el-input-number v-model="form.alert_realert_minutes" :min="1" :max="1440" :step="1" controls-position="right" />
                <span>分钟</span>
                <span class="form-tip">所有未恢复告警人工确认后，超过该时间仍未恢复会再次告警；默认 30 分钟。</span>
              </div>
            </el-form-item>

            <el-divider content-position="left">{{ t('version.title') }}</el-divider>
            <el-form-item :label="t('version.currentAuto')">
              <div v-if="effectiveVersion" class="version-info-card">
                <div class="version-info-main">
                  <strong>{{ effectiveVersionText }}</strong>
                  <el-tag
                    size="small"
                    effect="plain"
                    :type="effectiveVersion.source === 'auto' ? 'success' : 'info'"
                  >
                    {{ t(`version.source.${effectiveVersion.source || 'fallback'}`) }}
                  </el-tag>
                </div>
                <div v-if="effectiveVersion.build" class="version-info-meta">
                  {{ t('version.build') }} <b>{{ effectiveVersion.build }}</b>
                  <span v-if="effectiveVersion.build_id">· {{ t('version.buildId') }} {{ effectiveVersion.build_id }}</span>
                </div>
                <div v-if="versionBuiltAtText" class="version-info-meta">{{ t('version.builtAt') }} {{ versionBuiltAtText }}</div>
              </div>
              <el-tag v-else type="info" effect="plain">{{ t('version.notAvailable') }}</el-tag>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <!-- ==================== 时间设置（系统时间 / NTP） ==================== -->
        <el-tab-pane label="时间设置" name="time">
          <div class="time-tab">
            <div class="time-hero">
              <div class="time-hero-main">
                <span class="time-hero-label">当前系统时间</span>
                <strong class="time-hero-clock">{{ timeNow || timeStatus?.now || '--' }}</strong>
                <span class="time-hero-sub">{{ timeStatus?.now_local || timeStatus?.utc_now || '' }}</span>
              </div>
              <div class="time-hero-side">
                <div class="time-meta"><span>时区</span><b>{{ timeStatus?.timezone || '-' }}</b></div>
                <div class="time-meta"><span>UTC 偏移</span><b>UTC{{ timeStatus?.utc_offset || '' }}</b></div>
                <div class="time-meta"><span>操作系统</span><b>{{ timeStatus?.platform_label || '-' }} {{ timeStatus?.platform_release || '' }}</b></div>
                <div class="time-meta"><span>主机名</span><b>{{ timeStatus?.hostname || '-' }}</b></div>
                <div class="time-meta"><span>检测时间</span><b>{{ (timeStatus?.checked_at || '').replace('T', ' ') }}</b></div>
              </div>
              <el-button class="time-refresh" size="small" :loading="timeLoading" @click="loadTimeStatus">
                <el-icon><Refresh /></el-icon>刷新状态
              </el-button>
            </div>

            <div class="time-stat-grid">
              <div class="time-stat-card" :class="timeStatus?.ntp_synchronized === true ? 'is-ok' : timeStatus?.ntp_synchronized === false ? 'is-warn' : 'is-unknown'">
                <span class="time-stat-title">NTP 自动同步</span>
                <b>{{ timeStatus?.ntp_enabled ? '已启用' : '未启用' }}</b>
                <span class="time-stat-sub">
                  {{ timeStatus?.ntp_synchronized === true ? '已同步' : timeStatus?.ntp_synchronized === false ? '未同步' : '状态未知' }}
                  <template v-if="timeStatus?.ntp_source"> · 时间源 {{ timeStatus.ntp_source }}</template>
                </span>
              </div>
              <div class="time-stat-card">
                <span class="time-stat-title">时间同步服务</span>
                <b>{{ timeStatus?.ntp_service || '未检测到' }}</b>
                <span class="time-stat-sub">已配置 {{ (timeStatus?.ntp_servers || []).length }} 个 NTP 服务器</span>
              </div>
              <div class="time-stat-card">
                <span class="time-stat-title">手动设置时间</span>
                <b>{{ timeStatus?.capabilities?.manual_set_time ? '可用' : '不可用' }}</b>
                <span class="time-stat-sub">{{ timeStatus?.platform_label || '' }} 平台{{ timeStatus?.capabilities?.set_timezone ? ' · 支持网页设置时区' : ' · 时区请在本机系统设置中修改' }}</span>
              </div>
            </div>

            <el-alert
              v-for="(warning, index) in timeStatus?.warnings || []"
              :key="`time-warning-${index}`"
              :title="warning"
              type="warning"
              :closable="false"
              show-icon
              class="time-warning"
            />
            <el-alert
              v-if="timeStatus && !timeStatus.ntp_enabled"
              title="当前未启用 NTP 自动同步，系统时间以本机时间为准；建议启用 NTP 以避免时间漂移导致日志与告警时间不准。"
              type="info"
              :closable="false"
              show-icon
              class="time-warning"
            />

            <el-divider content-position="left">NTP 自动同步</el-divider>
            <el-form :model="timeForm" label-width="150px" class="settings-form" :disabled="!canEdit">
              <el-form-item label="启用 NTP 自动同步">
                <el-switch v-model="timeForm.ntp_enabled" />
                <div class="form-tip">
                  关闭时使用本机时间；启用后由 NTP 服务器校准系统时间（Windows 使用 w32time，Linux 使用 systemd-timesyncd / chrony）。
                </div>
              </el-form-item>
              <el-form-item label="NTP 服务器">
                <div class="ntp-server-list">
                  <el-tag
                    v-for="server in timeForm.ntp_servers"
                    :key="server"
                    class="ntp-server-tag"
                    :closable="canEdit"
                    :disable-transitions="false"
                    @close="removeNtpServer(server)"
                  >
                    {{ server }}
                  </el-tag>
                  <span v-if="!timeForm.ntp_servers.length" class="muted">尚未配置 NTP 服务器</span>
                </div>
                <div class="ntp-server-add">
                  <el-input
                    v-model="timeServerInput"
                    placeholder="例如 ntp.aliyun.com 或 10.0.0.1"
                    style="max-width: 280px"
                    :disabled="!canEdit"
                    @keyup.enter="addNtpServer"
                  />
                  <el-button :disabled="!canEdit" @click="addNtpServer">添加</el-button>
                </div>
                <div class="form-tip">支持域名或 IP，最多 8 个；生产环境建议使用内网 NTP 服务器。</div>
              </el-form-item>
              <el-form-item v-if="timeStatus?.capabilities?.set_timezone" label="系统时区">
                <el-select v-model="timeForm.timezone" filterable style="width: 260px">
                  <el-option
                    v-for="item in timezoneOptions"
                    :key="item.value"
                    :label="item.label"
                    :value="item.value"
                  />
                </el-select>
                <div class="form-tip">仅 Linux 支持通过网页修改系统时区（timedatectl set-timezone）。</div>
              </el-form-item>
              <el-form-item>
                <el-button type="primary" :loading="timeSaving" :disabled="!canEdit" @click="applyTimeSettings">
                  保存并应用
                </el-button>
                <el-button
                  :loading="timeSyncing"
                  :disabled="!canEdit || !timeStatus?.ntp_enabled"
                  @click="syncTimeNow"
                >
                  立即同步
                </el-button>
              </el-form-item>
            </el-form>

            <el-divider content-position="left">手动设置系统时间</el-divider>
            <el-form label-width="150px" class="settings-form" :disabled="!canEdit">
              <el-form-item label="日期时间">
                <el-date-picker
                  v-model="timeForm.datetime"
                  type="datetime"
                  value-format="YYYY-MM-DDTHH:mm:ss"
                  placeholder="选择要设置的系统时间"
                  :disabled="!canEdit"
                  style="width: 250px"
                />
                <el-button
                  style="margin-left: 10px"
                  :loading="timeSetting"
                  :disabled="!canEdit"
                  @click="setTimeManually"
                >
                  设置时间
                </el-button>
                <div class="form-tip">
                  手动设置前需关闭 NTP 自动同步；Windows 使用 PowerShell Set-Date，Linux 使用 timedatectl set-time / date -s。
                </div>
              </el-form-item>
            </el-form>

            <el-collapse v-if="timeResults.length" class="time-results">
              <el-collapse-item :title="`最近一次系统命令执行结果（${timeResults.length} 条）`" name="time-results">
                <div v-for="(item, index) in timeResults" :key="`time-result-${index}`" class="time-result-item">
                  <div class="time-result-head">
                    <el-tag size="small" :type="item.ok ? 'success' : 'danger'">{{ item.ok ? '成功' : (item.code || '失败') }}</el-tag>
                    <code>{{ item.command || '-' }}</code>
                  </div>
                  <pre v-if="item.error || item.stdout || item.stderr">{{ [item.error, item.stdout, item.stderr].filter(Boolean).join('\n') }}</pre>
                </div>
              </el-collapse-item>
            </el-collapse>
            <el-collapse v-if="timeStatus?.commands?.length" class="time-results">
              <el-collapse-item :title="`系统时间探测命令输出（${timeStatus.commands.length} 条，仅供排查）`" name="time-probe">
                <div v-for="(item, index) in timeStatus.commands" :key="`time-probe-${index}`" class="time-result-item">
                  <div class="time-result-head">
                    <el-tag size="small" :type="item.ok ? 'success' : 'warning'">{{ item.ok ? '成功' : (item.code || '失败') }}</el-tag>
                    <code>{{ item.command || '-' }}</code>
                  </div>
                  <pre v-if="item.error || item.stdout || item.stderr">{{ [item.error, item.stdout, item.stderr].filter(Boolean).join('\n') }}</pre>
                </div>
              </el-collapse-item>
            </el-collapse>
          </div>
        </el-tab-pane>

        <!-- ==================== 用户与权限 ==================== -->
        <el-tab-pane :label="t('settings.tabUsers')" name="users">
          <SystemUsers embedded />
        </el-tab-pane>

        <!-- ==================== 登录与安全 ==================== -->
        <el-tab-pane :label="t('settings.tabSecurity')" name="security">
          <el-form :model="form" label-width="150px" class="settings-form" :disabled="!canEdit">
            <el-form-item :label="t('settings.captchaEnabled')">
              <el-switch v-model="form.captcha_enabled" />
              <div class="form-tip">{{ t('settings.captchaTip') }}</div>
            </el-form-item>

            <el-form-item :label="t('settings.autoLogin')">
              <el-switch v-model="form.auto_login" />
              <div class="form-tip">
                {{ t('settings.autoLoginTip') }}
              </div>
            </el-form-item>

            <el-form-item :label="t('settings.autoLogout')">
              <el-input-number v-model="form.auto_logout_minutes" :min="0" :max="1440" :step="5" />
              <span class="unit">{{ t('settings.unitMinutes') }}</span>
              <div class="form-tip">{{ t('settings.autoLogoutTip') }}</div>
            </el-form-item>

            <el-divider content-position="left">{{ t('settings.webAccessSection') }}</el-divider>
            <el-form-item :label="t('settings.webLoginProtocol')">
              <el-radio-group v-model="form.web_protocol" @change="onWebProtocolChange">
                <el-radio-button value="http">HTTP</el-radio-button>
                <el-radio-button value="https">HTTPS</el-radio-button>
              </el-radio-group>
              <div class="form-tip">{{ t('settings.webProtocolTip') }}</div>
            </el-form-item>
            <el-form-item :label="t('settings.webLoginPort')">
              <el-input-number v-model="form.web_login_port" :min="1" :max="65535" :step="1" />
              <span class="web-access-port-label">
                {{ form.web_protocol === 'https' ? t('settings.webHttpsDefaultPort') : t('settings.webHttpDefaultPort') }}
              </span>
              <div class="form-tip">{{ t('settings.webPortAutoTip') }}</div>
            </el-form-item>
            <el-form-item v-if="form.web_protocol === 'https'" :label="t('settings.webSslCertificate')">
              <el-alert
                type="success"
                :closable="false"
                show-icon
                :title="t('settings.webAutoCertTitle')"
                :description="t('settings.webAutoCertDesc')"
              />
              <el-button link type="primary" size="small" @click="showWebCertTrustGuide">
                {{ t('settings.webSslTrustGuide') }}
              </el-button>
            </el-form-item>
            <el-form-item :label="t('settings.webGatewayStatus')">
              <div class="web-gateway-status">
                <el-alert
                  v-if="webGateway.error"
                  type="error"
                  :closable="false"
                  show-icon
                  :title="webGateway.error"
                />
                <el-alert
                  v-else-if="webGateway.running"
                  type="success"
                  :closable="false"
                  show-icon
                  :title="webGatewayListenersText"
                />
                <el-alert
                  v-else
                  type="info"
                  :closable="false"
                  show-icon
                  :title="t('settings.webGatewayStopped')"
                />
                <el-button :loading="webGatewayApplying" @click="loadWebGatewayStatus">
                  <el-icon><Refresh /></el-icon>{{ t('settings.webGatewayRefresh') }}
                </el-button>
                <el-button :loading="webDiagnoseLoading" @click="diagnoseWebAccess">
                  {{ t('settings.webGatewayDiagnose') }}
                </el-button>
              </div>
              <div class="form-tip">{{ t('settings.webGatewayAutoTip') }}</div>
            </el-form-item>

            <el-divider content-position="left">{{ t('settings.passwordPolicy') }}</el-divider>
            <el-form-item :label="t('settings.passwordMinLength')">
              <el-input-number v-model="form.password_min_length" :min="4" :max="32" />
              <span class="unit">{{ t('settings.unitChars') }}</span>
              <div class="form-tip">{{ t('settings.passwordPolicyTip') }}</div>
            </el-form-item>
            <el-form-item :label="t('settings.passwordRequire')">
              <div class="password-requirements">
                <el-checkbox v-model="form.password_require_uppercase">{{ t('settings.passwordUppercase') }}</el-checkbox>
                <el-checkbox v-model="form.password_require_lowercase">{{ t('settings.passwordLowercase') }}</el-checkbox>
                <el-checkbox v-model="form.password_require_digit">{{ t('settings.passwordDigit') }}</el-checkbox>
                <el-checkbox v-model="form.password_require_special">{{ t('settings.passwordSpecial') }}</el-checkbox>
              </div>
            </el-form-item>

            <el-form-item :label="t('settings.passwordExpiryDays')">
              <el-input-number v-model="form.password_expiry_days" :min="0" :max="36500" :step="30" />
              <span class="unit">{{ t('settings.unitDays') }}</span>
              <el-tag v-if="!form.password_expiry_days" size="small" type="success" effect="plain" style="margin-left:8px">
                {{ t('settings.passwordExpiryPermanent') }}
              </el-tag>
              <div class="form-tip">{{ t('settings.passwordExpiryTip') }}</div>
            </el-form-item>

            <el-form-item :label="t('settings.firstLoginPasswordChange')">
              <el-switch v-model="form.first_login_password_change" />
              <div class="form-tip">{{ t('settings.firstLoginPasswordChangeTip') }}</div>
            </el-form-item>

            <el-divider content-position="left">{{ t('settings.loginLock') }}</el-divider>
            <el-form-item :label="t('settings.loginLockEnabled')">
              <el-switch v-model="form.login_lock_enabled" />
              <div class="form-tip">{{ t('settings.loginLockTip') }}</div>
            </el-form-item>
            <el-row v-if="form.login_lock_enabled" :gutter="16">
              <el-col :span="12">
                <el-form-item :label="t('settings.loginMaxAttempts')">
                  <el-input-number v-model="form.login_max_attempts" :min="3" :max="20" />
                  <span class="unit">{{ t('settings.unitTimes') }}</span>
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item :label="t('settings.loginLockMinutes')">
                  <el-input-number v-model="form.login_lock_minutes" :min="1" :max="1440" />
                  <span class="unit">{{ t('settings.unitMinutes') }}</span>
                </el-form-item>
              </el-col>
            </el-row>

            <el-divider content-position="left">{{ t('settings.ipWhitelist') }}</el-divider>
            <el-form-item :label="t('settings.ipWhitelistEnabled')">
              <el-switch v-model="form.ip_whitelist_enabled" />
              <div class="form-tip">
                {{ t('settings.whitelistTipBefore') }}<code>/api/health</code>{{ t('settings.whitelistTipAfter') }}
              </div>
            </el-form-item>
            <el-form-item :label="t('settings.ipWhitelistAllowed')">
              <el-input
                v-model="form.ip_whitelist"
                type="textarea"
                :rows="4"
                :placeholder="t('settings.ipWhitelistPlaceholder')"
                style="max-width: 560px"
              />
              <div class="form-tip">
                {{ t('settings.currentIpLabel') }}<b>{{ securityInfo?.current_ip || '-' }}</b>
                <el-tag
                  v-if="securityInfo"
                  :type="securityInfo.ip_whitelisted ? 'success' : 'danger'"
                  size="small"
                  style="margin-left: 8px"
                >
                  {{ securityInfo.ip_whitelisted ? t('settings.inWhitelist') : t('settings.notInWhitelist') }}
                </el-tag>
                <div class="warn-tip">
                  ⚠ {{ t('settings.whitelistWarning1') }}
                  {{ t('settings.whitelistWarning2') }}<code>IP_WHITELIST_BYPASS=1</code>{{ t('settings.whitelistWarning3') }}
                </div>
              </div>
            </el-form-item>
            <el-form-item :label="t('settings.trustProxy')">
              <el-switch v-model="form.trust_proxy" />
              <div class="form-tip">
                {{ t('settings.trustProxyTip') }}
              </div>
            </el-form-item>
            <el-form-item :label="t('settings.auditRetention')">
              <el-input-number v-model="form.audit_retention_days" :min="0" :max="3650" />
              <span class="unit">{{ t('settings.unitDays') }}</span>
              <div class="form-tip">{{ t('settings.auditRetentionTip') }}</div>
            </el-form-item>
          </el-form>

          <el-divider content-position="left">{{ t('settings.changePassword') }}</el-divider>

          <el-form ref="passwordFormRef" :model="passwordForm" :rules="passwordRules" label-width="150px" class="settings-form">
            <el-form-item :label="t('settings.oldPassword')" prop="old_password">
              <el-input v-model="passwordForm.old_password" type="password" show-password style="max-width: 320px" />
            </el-form-item>
            <el-form-item :label="t('settings.newPassword')" prop="new_password">
              <el-input v-model="passwordForm.new_password" type="password" show-password style="max-width: 320px" />
              <div class="form-tip">{{ passwordPolicyHint }}</div>
            </el-form-item>
            <el-form-item :label="t('settings.confirmPassword')" prop="confirm">
              <el-input v-model="passwordForm.confirm" type="password" show-password style="max-width: 320px" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="passwordSaving" @click="changePassword">{{ t('settings.changePassword') }}</el-button>
            </el-form-item>
          </el-form>

        </el-tab-pane>

        <!-- ==================== 二次验证策略 ==================== -->
        <el-tab-pane label="二次身份验证" name="totp">
          <div class="totp-policy-card">
            <div class="totp-policy-head">
              <div>
                <strong>二次验证策略</strong>
                <span>这里只配置全局要求；用户自己的二维码绑定、启用和停用请在「个人账户」中操作。</span>
              </div>
              <el-tag :type="form.totp_policy === 'off' ? 'info' : 'warning'" size="small">
                {{ form.totp_policy === 'off' ? '未要求' : form.totp_policy === 'all' ? '全部用户' : '指定用户' }}
              </el-tag>
            </div>
            <el-form :model="form" label-width="150px" class="settings-form" :disabled="!canEdit">
              <el-form-item label="二次验证范围">
                <el-radio-group v-model="form.totp_policy">
                  <el-radio label="off">关闭</el-radio>
                  <el-radio label="all">全部用户</el-radio>
                  <el-radio label="selected">指定用户</el-radio>
                </el-radio-group>
                <div class="form-tip">关闭表示不要求任何账号开启；全部用户表示所有账号都必须开启；指定用户仅要求选中账号。</div>
              </el-form-item>
              <el-form-item v-if="form.totp_policy === 'selected'" label="指定用户">
                <el-select
                  v-model="totpSelectedUserIds"
                  multiple
                  filterable
                  collapse-tags
                  collapse-tags-tooltip
                  placeholder="选择需要开启二次验证的用户"
                  style="width: 100%; max-width: 620px"
                >
                  <el-option
                    v-for="item in settingsUsers"
                    :key="item.id"
                    :label="`${item.real_name || item.username} (${item.username})`"
                    :value="item.id"
                  />
                </el-select>
                <div class="form-tip">已选择 {{ totpSelectedUserIds.length }} 个用户；保存后生效。</div>
              </el-form-item>
              <el-alert
                type="info"
                :closable="false"
                show-icon
                title="用户绑定入口：个人账户 → 二次身份验证。管理员要求开启但用户尚未绑定时，用户登录后会在个人账户看到提示；指定用户不能自行停用。"
              />
            </el-form>
          </div>
        </el-tab-pane>

        <!-- ==================== 数据库与缓存 ==================== -->
        <el-tab-pane :label="t('settings.tabIntegration')" name="integration">
          <el-form :model="form" label-width="160px" class="settings-form" :disabled="!canEdit">
            <el-alert
              type="info"
              :closable="false"
              show-icon
              :title="t('settings.integrationOnlySuperuserTip')"
              class="settings-readonly-alert"
            />

            <el-alert
              v-if="runtimeInfo"
              type="success"
              :closable="false"
              show-icon
              class="runtime-connection-alert"
            >
              <template #title>{{ t('settings.runtimeTitle') }}</template>
              <div class="runtime-connection-grid">
                <div class="runtime-connection-item">
                  <span class="runtime-connection-label">{{ t('settings.runtimeDatabase') }}</span>
                  <b>{{ runtimeInfo.database.display }}</b>
                  <el-tag size="small" effect="plain" type="success">
                    {{ runtimeSourceLabel(runtimeInfo.database.source) }}
                  </el-tag>
                  <el-tag v-if="runtimeInfo.database.connected === true" size="small" type="success">已连接</el-tag>
                  <el-tag v-else-if="runtimeInfo.database.connected === false" size="small" type="danger">连接异常</el-tag>
                  <span v-if="runtimeInfo.database.connected === true && runtimeInfo.database.latency_ms != null" class="runtime-connection-note">
                    {{ runtimeInfo.database.latency_ms }} ms
                  </span>
                  <span v-if="runtimeInfo.database.server_version" class="runtime-connection-note" :title="runtimeInfo.database.server_version">
                    {{ runtimeInfo.database.server_version }}
                  </span>
                  <span
                    v-if="runtimeInfo.database.connected === false && runtimeInfo.database.error"
                    class="runtime-connection-note runtime-connection-error"
                    :title="runtimeInfo.database.error"
                  >
                    连接失败：{{ runtimeInfo.database.error.slice(0, 60) }}
                  </span>
                  <span v-if="runtimeInfo.database.driver_ready === false" class="runtime-connection-note runtime-connection-error">
                    缺少对应数据库驱动，连接无法建立
                  </span>
                  <span v-if="runtimeInfo.database.password_set" class="runtime-connection-note">
                    {{ t('settings.runtimePasswordSet') }}
                  </span>
                </div>
                <div class="runtime-connection-item">
                  <span class="runtime-connection-label">{{ t('settings.runtimeCache') }}</span>
                  <b>{{ runtimeInfo.cache.display }}</b>
                  <el-tag size="small" effect="plain" :type="runtimeInfo.cache.backend === 'redis' ? 'success' : 'info'">
                    {{ runtimeSourceLabel(runtimeInfo.cache.source) }}
                  </el-tag>
                  <el-tag v-if="runtimeInfo.cache.backend === 'disabled'" size="small" type="warning">缓存未启用</el-tag>
                  <el-tag v-else-if="runtimeInfo.cache.source === 'memory'" size="small" type="info">进程内缓存</el-tag>
                  <el-tag v-else-if="runtimeInfo.cache.connected === true" size="small" type="success">Redis 已连接</el-tag>
                  <el-tag v-else size="small" type="danger">Redis 连接异常</el-tag>
                  <span v-if="runtimeInfo.cache.connected === true && runtimeInfo.cache.latency_ms != null" class="runtime-connection-note">
                    {{ runtimeInfo.cache.latency_ms }} ms
                  </span>
                  <span v-if="runtimeInfo.cache.redis_version" class="runtime-connection-note">v{{ runtimeInfo.cache.redis_version }}</span>
                  <span
                    v-if="runtimeInfo.cache.source !== 'memory' && runtimeInfo.cache.connected === false && runtimeInfo.cache.error"
                    class="runtime-connection-note runtime-connection-error"
                    :title="runtimeInfo.cache.error"
                  >
                    连接失败：{{ runtimeInfo.cache.error.slice(0, 60) }}
                  </span>
                </div>
              </div>
            </el-alert>

            <el-alert
              v-if="runtimeInfo?.database?.auto_filled"
              type="warning"
              :closable="false"
              show-icon
              :title="t('settings.runtimeAutoFilledTip')"
              class="runtime-autofill-alert"
            />

            <el-divider content-position="left">{{ t('settings.integrationSection') }}</el-divider>
            <el-form-item :label="t('settings.integrationEnabled')">
              <el-switch v-model="form.integration_enabled" />
              <div class="form-tip">{{ t('settings.integrationEnabledTip') }}</div>
            </el-form-item>
            <el-row :gutter="20">
              <el-col :span="12">
                <el-form-item :label="t('settings.integrationName')">
                  <el-input v-model="form.integration_name" maxlength="100" :placeholder="t('settings.integrationNamePlaceholder')" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item :label="t('settings.integrationDbType')">
                  <el-select v-model="form.integration_db_type" style="width: 100%" @change="onIntegrationDbTypeChange">
                    <el-option label="MySQL" value="mysql" />
                    <el-option label="PostgreSQL" value="postgresql" />
                    <el-option label="SQLite" value="sqlite" />
                  </el-select>
                  <div class="form-tip">{{ t('settings.integrationDbTypeTip') }}</div>
                </el-form-item>
              </el-col>
            </el-row>

            <template v-if="form.integration_db_type === 'sqlite'">
              <el-form-item :label="t('settings.integrationSqlitePath')">
                <el-input
                  v-model="form.integration_sqlite_path"
                  maxlength="500"
                  :placeholder="t('settings.integrationSqlitePathPlaceholder')"
                  style="max-width: 720px"
                />
                <div class="form-tip">{{ t('settings.integrationSqlitePathTip') }}</div>
              </el-form-item>
            </template>

            <template v-else>
              <el-row :gutter="20">
                <el-col :span="16">
                  <el-form-item :label="t('settings.integrationHost')">
                    <el-input v-model="form.integration_host" maxlength="255" :placeholder="t('settings.integrationHostPlaceholder')" />
                  </el-form-item>
                </el-col>
                <el-col :span="8">
                  <el-form-item :label="t('settings.integrationPort')">
                    <el-input-number v-model="form.integration_port" :min="1" :max="65535" controls-position="right" style="width: 100%" />
                  </el-form-item>
                </el-col>
              </el-row>
              <el-form-item :label="t('settings.integrationDatabase')">
                <el-input v-model="form.integration_database" maxlength="255" :placeholder="t('settings.integrationDatabasePlaceholder')" style="max-width: 520px" />
              </el-form-item>
              <el-row :gutter="20">
                <el-col :span="12">
                  <el-form-item :label="t('settings.integrationUsername')">
                    <el-input v-model="form.integration_username" maxlength="255" :placeholder="t('settings.integrationUsernamePlaceholder')" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item :label="t('settings.integrationPassword')">
                    <el-input
                      v-model="form.integration_password"
                      type="password"
                      show-password
                      maxlength="2000"
                      :placeholder="t('settings.integrationPasswordPlaceholder')"
                    />
                    <div class="form-tip">{{ t('settings.integrationPasswordTip') }}</div>
                    <div
                      v-if="runtimeInfo?.database?.auto_filled && runtimeInfo?.database?.password_set && !form.integration_password"
                      class="form-tip"
                    >
                      {{ t('settings.runtimePasswordSet') }}
                    </div>
                  </el-form-item>
                </el-col>
              </el-row>
              <el-form-item v-if="form.integration_db_type === 'mysql'" :label="t('settings.integrationCharset')">
                <el-input v-model="form.integration_charset" maxlength="32" style="max-width: 220px" />
                <div class="form-tip">{{ t('settings.integrationCharsetTip') }}</div>
              </el-form-item>
            </template>
            <el-row :gutter="20">
              <el-col :span="12">
                <el-form-item :label="t('settings.integrationTimeout')">
                  <el-input-number v-model="form.integration_timeout" :min="1" :max="60" />
                  <span class="unit">{{ t('settings.unitSeconds') }}</span>
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item :label="t('settings.integrationSyncInterval')">
                  <el-input-number v-model="form.integration_sync_interval" :min="1" :max="1440" />
                  <span class="unit">{{ t('settings.unitMinutes') }}</span>
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item :label="t('settings.integrationTest')">
              <el-button :loading="integrationTesting" @click="testIntegration">
                {{ t('settings.integrationTestButton') }}
              </el-button>
              <div class="form-tip">{{ t('settings.integrationTestTip') }}</div>
              <div
                v-if="integrationTestResult"
                class="connection-result"
                :class="{ ok: integrationTestResult.ok }"
              >
                <strong>{{ integrationTestResult.ok ? t('settings.integrationTestSuccess') : t('settings.integrationTestFailed') }}</strong>
                <span v-if="integrationTestResult.server_version">{{ integrationTestResult.server_version }}</span>
                <span v-if="integrationTestResult.table_count !== undefined">{{ integrationTestResult.table_count }} {{ t('settings.integrationTableCount') }}</span>
                <span v-if="integrationTestResult.latency_ms !== undefined">{{ integrationTestResult.latency_ms }}ms</span>
                <span v-if="integrationTestResult.error">{{ integrationTestResult.error }}</span>
              </div>
            </el-form-item>

            <el-divider content-position="left">{{ t('settings.redisSection') }}</el-divider>
            <el-form-item :label="t('settings.redisEnabled')">
              <el-switch v-model="form.redis_enabled" />
              <div class="form-tip">{{ t('settings.redisEnabledTip') }}</div>
            </el-form-item>
            <el-form-item :label="t('settings.redisUrl')">
              <el-input
                v-model="form.redis_url"
                maxlength="500"
                :placeholder="t('settings.redisUrlPlaceholder')"
                style="max-width: 720px"
              />
              <div class="form-tip">{{ t('settings.redisUrlTip') }}</div>
              <div v-if="runtimeInfo?.cache" class="form-tip">
                {{ t('settings.redisEffectiveTip') }}
                <el-tag size="small" effect="plain" :type="runtimeInfo.cache.source === 'memory' ? 'info' : 'success'">
                  {{ runtimeSourceLabel(runtimeInfo.cache.source) }}
                </el-tag>
              </div>
            </el-form-item>
            <el-row :gutter="20">
              <el-col :span="12">
                <el-form-item :label="t('settings.cacheTtlTopology')">
                  <el-input-number v-model="form.cache_ttl_topology" :min="1" :max="300" />
                  <span class="unit">{{ t('settings.unitSeconds') }}</span>
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item :label="t('settings.cacheTtlDashboard')">
                  <el-input-number v-model="form.cache_ttl_dashboard" :min="1" :max="60" />
                  <span class="unit">{{ t('settings.unitSeconds') }}</span>
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item :label="t('settings.redisTest')">
              <el-button :loading="redisTesting" @click="testRedis">
                {{ t('settings.redisTestButton') }}
              </el-button>
              <div class="form-tip">{{ t('settings.redisTestTip') }}</div>
              <div v-if="redisTestResult" class="connection-result" :class="{ ok: redisTestResult.ok }">
                <strong>{{ redisTestResult.ok ? t('settings.redisTestSuccess') : t('settings.redisTestFailed') }}</strong>
                <span v-if="redisTestResult.latency_ms !== undefined">{{ redisTestResult.latency_ms }}ms</span>
                <span v-if="redisTestResult.version">Redis {{ redisTestResult.version }}</span>
                <span v-if="redisTestResult.error">{{ redisTestResult.error }}</span>
              </div>
            </el-form-item>
            <el-alert
              type="warning"
              :closable="false"
              show-icon
              :title="t('settings.redisFallbackTip')"
            />
          </el-form>
        </el-tab-pane>

        <!-- ==================== 采集设置 ==================== -->
        <el-tab-pane :label="t('settings.tabCollection')" name="collection">
          <el-form :model="form" label-width="150px" class="settings-form" :disabled="!canEdit">
            <el-form-item :label="t('settings.collectionInterval')">
              <el-input-number v-model="form.collection_interval" :min="10" :max="3600" :step="10" />
              <span class="unit">{{ t('settings.unitSeconds') }}</span>
              <div class="form-tip">
                {{ t('settings.collectionIntervalCurrent', { seconds: form.collection_interval, minutes: (form.collection_interval / 60).toFixed(1) }) }}
                {{ t('settings.collectionIntervalTip2') }}
              </div>
            </el-form-item>
            <el-form-item :label="t('settings.description')">
              <div class="hint-box">
                {{ t('settings.collectionHint') }}<br />
                {{ t('settings.collectionAdvice') }}
              </div>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <!-- ==================== 日志转发 ==================== -->
        <el-tab-pane :label="t('settings.tabLogForward')" name="logforward">
          <el-form :model="form" label-width="150px" class="settings-form" :disabled="!canEdit">
            <el-form-item :label="t('settings.logForwardEnabled')">
              <el-switch v-model="form.log_forward_enabled" />
              <div class="form-tip">
                {{ t('settings.logForwardTip') }}
              </div>
            </el-form-item>

            <el-form-item :label="t('settings.logForwardType')">
              <el-radio-group v-model="form.log_forward_type">
                <el-radio-button value="syslog">Syslog</el-radio-button>
                <el-radio-button value="http">HTTP Webhook</el-radio-button>
                <el-radio-button value="file">{{ t('settings.targetFile') }}</el-radio-button>
              </el-radio-group>
              <div class="form-tip">{{ t('settings.forwardTargetTip') }}</div>
            </el-form-item>

            <el-form-item :label="t('settings.minLogLevel')">
              <el-select v-model="form.log_forward_min_level" style="width: 200px">
                <el-option :label="t('settings.levelDebug')" value="DEBUG" />
                <el-option :label="t('settings.levelInfo')" value="INFO" />
                <el-option :label="t('settings.levelWarning')" value="WARNING" />
                <el-option :label="t('settings.levelError')" value="ERROR" />
              </el-select>
            </el-form-item>

            <!-- Syslog -->
            <template v-if="form.log_forward_type === 'syslog'">
              <el-divider content-position="left">{{ t('settings.syslogSettings') }}</el-divider>
              <el-row :gutter="16">
                <el-col :span="12">
                  <el-form-item :label="t('settings.serverAddress')">
                    <el-input v-model="form.log_forward_host" :placeholder="t('settings.hostPlaceholder')" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item :label="t('settings.port')">
                    <el-input-number v-model="form.log_forward_port" :min="1" :max="65535" />
                  </el-form-item>
                </el-col>
              </el-row>
              <el-row :gutter="16">
                <el-col :span="8">
                  <el-form-item :label="t('settings.transportProtocol')">
                    <el-select v-model="form.log_forward_protocol">
                      <el-option label="UDP" value="udp" />
                      <el-option label="TCP" value="tcp" />
                    </el-select>
                  </el-form-item>
                </el-col>
                <el-col :span="8">
                  <el-form-item :label="t('settings.format')">
                    <el-select v-model="form.log_forward_format">
                      <el-option :label="t('settings.rfc5424')" value="rfc5424" />
                      <el-option :label="t('settings.rfc3164')" value="rfc3164" />
                    </el-select>
                  </el-form-item>
                </el-col>
                <el-col :span="8">
                  <el-form-item label="Facility">
                    <el-select v-model="form.log_forward_facility" filterable>
                      <el-option
                        v-for="item in FACILITY_OPTIONS"
                        :key="item"
                        :label="item"
                        :value="item"
                      />
                    </el-select>
                  </el-form-item>
                </el-col>
              </el-row>
              <el-form-item :label="t('settings.appName')">
                <el-input v-model="form.log_forward_app_name" style="width: 260px" />
              </el-form-item>
            </template>

            <!-- HTTP -->
            <template v-else-if="form.log_forward_type === 'http'">
              <el-divider content-position="left">{{ t('settings.httpSettings') }}</el-divider>
              <el-form-item :label="t('settings.receiveUrl')">
                <el-input v-model="form.log_forward_http_url" placeholder="https://collector.example.com/api/logs" />
              </el-form-item>
              <el-form-item :label="t('settings.requestHeaders')">
                <el-input
                  v-model="form.log_forward_http_headers"
                  type="textarea"
                  :rows="3"
                  :placeholder="t('settings.requestHeadersPlaceholder')"
                />
              </el-form-item>
              <el-form-item :label="t('settings.requestBodyFormat')">
                <div class="hint-box">
                  {{ t('settings.requestBodyLabel') }}<code>{"app":"snmp-monitor","host":"...","sent_at":"...","logs":[{"time":"...","level":"INFO","logger":"...","message":"..."}]}</code>
                </div>
              </el-form-item>
            </template>

            <!-- File -->
            <template v-else>
              <el-divider content-position="left">{{ t('settings.fileSettings') }}</el-divider>
              <el-form-item :label="t('settings.filePath')">
                <el-input v-model="form.log_forward_file_path" :placeholder="t('settings.filePathPlaceholder')" />
              </el-form-item>
              <el-form-item :label="t('settings.description')">
                <div class="hint-box">{{ t('settings.fileHint') }}</div>
              </el-form-item>
            </template>

            <el-form-item>
              <el-button v-if="canEdit" type="primary" :loading="saving" @click="saveAll">{{ t('settings.saveConfig') }}</el-button>
              <el-button v-if="canEdit" :loading="testing" :disabled="!form.log_forward_enabled && !forwardEnabled" @click="testForward">
                {{ t('settings.sendTestLog') }}
              </el-button>
              <el-button @click="loadForwardStatus" :loading="statusLoading">{{ t('settings.refreshStatus') }}</el-button>
              <el-button @click="openRecentLogs">{{ t('settings.viewRecentLogs') }}</el-button>
            </el-form-item>
          </el-form>

          <el-divider content-position="left">{{ t('settings.runtimeStatus') }}</el-divider>
          <el-descriptions v-if="forwardStatus" :column="3" border class="forward-status">
            <el-descriptions-item :label="t('settings.forwardStatus')">
              <el-tag :type="forwardStatus.settings.enabled ? 'success' : 'info'" size="small">
                {{ forwardStatus.settings.enabled ? t('settings.enabled') : t('settings.disabled') }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item :label="t('settings.targetType')">{{ forwardStatus.settings.type }}</el-descriptions-item>
            <el-descriptions-item :label="t('settings.minLevel')">{{ forwardStatus.settings.min_level }}</el-descriptions-item>
            <el-descriptions-item :label="t('settings.sent')">{{ forwardStatus.stats.sent }} {{ t('settings.unitEntries') }}</el-descriptions-item>
            <el-descriptions-item :label="t('settings.failed')">{{ forwardStatus.stats.failed }} {{ t('settings.unitEntries') }}</el-descriptions-item>
            <el-descriptions-item :label="t('settings.dropped')">{{ forwardStatus.stats.dropped }} {{ t('settings.unitEntries') }}</el-descriptions-item>
            <el-descriptions-item :label="t('settings.queueLength')">
              {{ forwardStatus.queue_size }} / {{ forwardStatus.queue_capacity }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('settings.lastSent')">{{ forwardStatus.stats.last_sent_at || '-' }}</el-descriptions-item>
            <el-descriptions-item :label="t('settings.lastError')">
              <span :class="forwardStatus.stats.last_error ? 'warn-text' : ''">
                {{ forwardStatus.stats.last_error || '-' }}
              </span>
            </el-descriptions-item>
          </el-descriptions>
        </el-tab-pane>

        <!-- ==================== 配置备份 ==================== -->
        <el-tab-pane :label="t('settings.tabBackup')" name="backup">
          <el-alert
            type="info"
            :closable="false"
            show-icon
            :title="t('settings.exportDesc')"
            style="margin-bottom: 16px"
          />

          <div class="backup-actions">
            <el-button type="primary" @click="exportConfig" :loading="exporting">
              <el-icon><Download /></el-icon>{{ t('settings.exportConfig') }}
            </el-button>
            <el-button @click="triggerImport" :disabled="!canEdit" :loading="importing">
              <el-icon><Upload /></el-icon>{{ t('settings.importConfig') }}
            </el-button>
            <el-checkbox v-model="importDryRun" :disabled="!canEdit">{{ t('settings.dryRun') }}</el-checkbox>
            <input
              ref="configFileRef"
              type="file"
              accept=".json,application/json"
              style="display: none"
              @change="onConfigSelected"
            />
          </div>
          <div class="form-tip" style="margin-bottom: 12px">
            {{ t('settings.backupHint1') }}
            {{ t('settings.backupHint2') }}
          </div>

          <el-alert
            v-if="importError"
            type="error"
            :closable="true"
            show-icon
            :title="importError"
            style="margin-bottom: 12px"
          />

          <template v-if="importResult">
            <el-descriptions :column="3" border size="small">
              <el-descriptions-item :label="t('settings.mode')">
                {{ importResult.dry_run ? t('settings.modeDryRun') : t('settings.modeImported') }}
              </el-descriptions-item>
              <el-descriptions-item :label="t('settings.configFile')">{{ importResult.filename || '-' }}</el-descriptions-item>
              <el-descriptions-item :label="t('settings.settingsChanged')">{{ importResult.settings_count ?? 0 }}</el-descriptions-item>
              <el-descriptions-item :label="t('settings.channelNew')">{{ importResult.channel_new ?? 0 }}</el-descriptions-item>
              <el-descriptions-item :label="t('settings.channelUpdated')">{{ importResult.channel_updated ?? 0 }}</el-descriptions-item>
              <el-descriptions-item :label="t('settings.autoBackup')">
                {{ importResult.backup_file ? t('settings.generated') : '-' }}
              </el-descriptions-item>
            </el-descriptions>
            <div v-if="importResult.settings_changed?.length" class="import-changed">
              {{ t('settings.changedKeys') }}
              <el-tag
                v-for="key in importResult.settings_changed"
                :key="key"
                size="small"
                type="warning"
                effect="plain"
                style="margin: 2px 4px 2px 0"
              >
                {{ key }}
              </el-tag>
            </div>
            <el-alert
              v-if="importResult.warnings?.length"
              type="warning"
              :closable="false"
              show-icon
              style="margin-top: 12px"
            >
              <template #title>
                <div v-for="(w, i) in importResult.warnings" :key="i">{{ w }}</div>
              </template>
            </el-alert>
            <div v-if="importResult.backup_file" class="form-tip" style="margin-top: 8px">
              {{ t('settings.backupPathLabel') }}<code>{{ importResult.backup_file }}</code>
            </div>
          </template>

          <el-divider content-position="left">{{ t('settings.dbBackupTitle') }}</el-divider>
          <el-form :model="form" label-width="150px" class="settings-form" :disabled="!canEdit">
            <el-form-item :label="t('settings.autoBackupEnabled')">
              <el-switch v-model="form.backup_enabled" />
              <div class="form-tip">{{ t('settings.dbBackupHint') }}</div>
            </el-form-item>
            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item :label="t('settings.backupInterval')">
                  <el-input-number v-model="form.backup_interval_hours" :min="1" :max="168" />
                  <span class="unit">{{ t('settings.unitHours') }}</span>
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item :label="t('settings.backupRetention')">
                  <el-input-number v-model="form.backup_retention_count" :min="1" :max="90" />
                  <span class="unit">{{ t('settings.unitCount') }}</span>
                </el-form-item>
              </el-col>
            </el-row>
          </el-form>

          <div class="backup-actions">
            <el-button type="primary" :loading="backupCreating" :disabled="!canEdit" @click="createDbBackup">
              <el-icon><Download /></el-icon>{{ t('settings.backupNow') }}
            </el-button>
            <el-button :loading="backupLoading" @click="loadBackups">
              <el-icon><Refresh /></el-icon>{{ t('common.refresh') }}
            </el-button>
            <span v-if="backupConfig" class="form-tip">
              {{ t('settings.backupDir') }}<code>{{ backupConfig.backup_dir }}</code>
            </span>
          </div>
          <el-table :data="backups" v-loading="backupLoading" size="small" border>
            <el-table-column prop="name" :label="t('settings.backupFile')" min-width="260" />
            <el-table-column :label="t('settings.backupTime')" width="175">
              <template #default="{ row }">{{ (row.created_at || '').replace('T', ' ') }}</template>
            </el-table-column>
            <el-table-column :label="t('settings.backupSize')" width="110">
              <template #default="{ row }">{{ (row.size / 1024 / 1024).toFixed(2) }} MB</template>
            </el-table-column>
            <el-table-column :label="t('mib.actions')" width="150">
              <template #default="{ row }">
                <el-button type="primary" link size="small" @click="downloadDbBackup(row)">
                  {{ t('settings.download') }}
                </el-button>
                <el-button type="danger" link size="small" @click="removeDbBackup(row)">
                  {{ t('mib.delete') }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!backupLoading && !backups.length" :description="t('settings.noBackups')" />
        </el-tab-pane>

        <el-tab-pane v-if="currentUser?.is_superuser" label="系统更新" name="update">
          <div v-loading="updateLoading" class="update-panel">
            <el-alert
              type="warning"
              :closable="false"
              show-icon
              title="系统更新会自动备份当前程序、替换代码、安装必要依赖并重启服务"
              description="更新包需为构建好的 ZIP，包含 run_backend.py、backend/version.json 和 frontend/dist/index.html。更新期间请勿关闭页面或重复提交。"
            />

            <el-descriptions :column="3" border class="update-current">
              <el-descriptions-item label="当前版本">
                <strong>{{ updateInfo?.current?.display_version || updateInfo?.current?.version || '-' }}</strong>
              </el-descriptions-item>
              <el-descriptions-item label="构建号">{{ updateInfo?.current?.build || '-' }}</el-descriptions-item>
              <el-descriptions-item label="重启方式">
                {{ updateRestartModeText(updateInfo?.restart_mode) }}
              </el-descriptions-item>
            </el-descriptions>

            <el-divider content-position="left">版本回退</el-divider>
            <div class="version-history-head">
              <div>
                <strong>历史版本文件</strong>
                <span class="update-hint">默认保留最近 {{ updateInfo?.limits?.backup_retention || 5 }} 个版本备份；回退会先备份当前版本，再替换程序并重启服务。</span>
              </div>
              <el-button size="small" :loading="updateLoading" @click="loadUpdateInfo">刷新版本</el-button>
            </div>
            <el-table
              v-if="updateInfo?.backups?.length"
              :data="updateInfo.backups"
              size="small"
              stripe
              class="version-history-table"
            >
              <el-table-column label="版本" min-width="130">
                <template #default="{ row }">
                  <strong>{{ row.display_version || row.version }}</strong>
                  <el-tag size="small" effect="plain" type="info" class="version-tag">{{ row.version }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="build" label="构建号" width="145" show-overflow-tooltip />
              <el-table-column label="备份时间" width="170">
                <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
              </el-table-column>
              <el-table-column label="大小" width="105">
                <template #default="{ row }">{{ formatBytes(row.size_bytes) }}</template>
              </el-table-column>
              <el-table-column label="文件数" width="85">
                <template #default="{ row }">{{ row.file_count }}</template>
              </el-table-column>
              <el-table-column label="查看文件" width="92" align="center">
                <template #default="{ row }">
                  <el-button link type="primary" size="small" @click="viewBackupFiles(row)">查看</el-button>
                </template>
              </el-table-column>
              <el-table-column label="版本回退" width="108" align="center">
                <template #default="{ row }">
                  <el-button
                    link
                    type="warning"
                    size="small"
                    :loading="rollbackStarting"
                    :disabled="updateStarting || updateInfo?.active"
                    @click="rollbackToVersion(row)"
                  >回退</el-button>
                </template>
              </el-table-column>
              <el-table-column label="删除" width="80" align="center">
                <template #default="{ row }">
                  <el-button
                    link
                    type="danger"
                    size="small"
                    :loading="deletingBackupId === row.job_id"
                    :disabled="updateStarting || updateInfo?.active"
                    @click="deleteBackupVersion(row)"
                  >删除</el-button>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-else description="暂无历史版本备份；完成一次系统更新后会自动保留最近 5 个版本" :image-size="60" />

            <el-divider content-position="left">在线更新</el-divider>
            <el-form label-width="150px" class="update-config-form" @submit.prevent>
              <el-form-item label="在线更新地址">
                <el-input
                  v-model="updateUrl"
                  placeholder="http://192.168.1.10:9000/updates 或完整 latest.json / zip 地址"
                  clearable
                >
                  <template #append>
                    <el-button :loading="updateSaving" @click="saveUpdateUrl">保存地址</el-button>
                  </template>
                </el-input>
                <div class="update-hint">
                  填目录地址时自动读取 <code>latest.json</code>；也可直接填写 latest.json 或 ZIP 下载地址。
                </div>
              </el-form-item>
            </el-form>

            <div class="update-actions">
              <el-button :loading="onlineChecking" :disabled="updateStarting" @click="checkOnline">
                检查在线更新
              </el-button>
              <el-button
                type="primary"
                :loading="updateStarting"
                :disabled="!onlineCheck?.version || !onlineCheck?.update_available"
                @click="runOnlineUpdate"
              >
                在线更新到 {{ onlineCheck?.version || '-' }}
              </el-button>
            </div>

            <el-alert
              v-if="onlineCheck"
              class="update-check-result"
              :type="onlineCheck.update_available ? 'success' : 'info'"
              :closable="false"
              show-icon
              :title="onlineCheck.update_available
                ? `发现新版本 v${onlineCheck.display_version || onlineCheck.version}`
                : `当前已是最新版本 v${onlineCheck.current?.display_version || onlineCheck.version}`"
              :description="onlineCheck.notes || ''"
            />

            <el-divider content-position="left">上传更新包</el-divider>
            <input
              ref="updateFileInput"
              type="file"
              accept=".zip,application/zip"
              class="update-file-input"
              @change="onUpdateFileChange"
            />
            <div class="update-upload-row">
              <el-button @click="updateFileInput?.click()" :disabled="updateStarting">选择更新包</el-button>
              <span class="update-file-name">{{ updateFile?.name || '未选择 ZIP 更新包' }}</span>
              <el-checkbox v-model="updateForce" :disabled="updateStarting">强制重装同版本</el-checkbox>
              <el-button
                type="primary"
                :loading="updateStarting"
                :disabled="!updateFile || updateStarting"
                @click="uploadAndUpdate"
              >
                上传并更新
              </el-button>
            </div>
            <div class="update-hint">
              上传的 ZIP 会先校验目录结构和版本号，校验失败不会改动当前系统。
            </div>

            <div v-if="updateUploading || updateUploadProgress > 0" class="update-upload-progress">
              <div class="update-upload-progress-head">
                <span>{{ updateUploading ? '正在上传更新包' : '上传完成' }}</span>
                <span v-if="updateUploadTotal">
                  {{ formatBytes(updateUploadLoaded) }} / {{ formatBytes(updateUploadTotal) }}
                </span>
                <span v-else-if="updateUploadLoaded">{{ formatBytes(updateUploadLoaded) }}</span>
              </div>
              <el-progress
                :percentage="updateUploadProgress"
                :stroke-width="10"
                :status="updateUploadProgress >= 100 ? 'success' : undefined"
              />
              <div class="update-hint">
                {{ updateUploadProgress >= 100
                  ? '上传完成，服务端正在校验更新包，校验通过后自动开始更新。'
                  : '请保持页面打开，上传完成后会自动进入校验和更新流程。' }}
              </div>
            </div>

            <el-divider content-position="left">更新状态</el-divider>
            <div v-if="updateJob" class="update-job">
              <el-steps :active="updateStep" finish-status="success" :process-status="updateProcessStatus" align-center>
                <el-step title="备份" />
                <el-step title="替换文件" />
                <el-step title="安装依赖" />
                <el-step title="重启服务" />
                <el-step title="健康检查" />
              </el-steps>
              <el-alert
                class="update-job-alert"
                :type="updateJobAlertType"
                :closable="false"
                show-icon
                :title="updateJob.message || updateJob.status"
                :description="`${updateJob.current_version || '-'} → ${updateJob.new_version || '-'} · 任务 ${updateJob.job_id || ''}`"
              />
              <div v-if="updateJob.error" class="update-error">{{ updateJob.error }}</div>
            </div>
            <el-empty v-else description="暂无更新任务" :image-size="70" />

            <el-alert
              v-if="updateJob && !['success', 'failed', 'rolled_back'].includes(updateJob.status)"
              type="info"
              :closable="false"
              show-icon
              title="服务重启期间页面可能短暂断开，系统会自动重连并刷新"
            />

            <el-dialog v-model="backupFilesVisible" :title="`版本文件 · ${backupFilesData?.display_version || backupFilesData?.version || ''}`" width="760px">
              <div v-loading="backupFilesLoading">
                <el-descriptions :column="3" border size="small" class="backup-files-meta">
                  <el-descriptions-item label="版本">{{ backupFilesData?.display_version || backupFilesData?.version || '-' }}</el-descriptions-item>
                  <el-descriptions-item label="构建号">{{ backupFilesData?.build || '-' }}</el-descriptions-item>
                  <el-descriptions-item label="备份时间">{{ formatDateTime(backupFilesData?.created_at) }}</el-descriptions-item>
                </el-descriptions>
                <el-table :data="backupFilesData?.files || []" size="small" max-height="430" stripe>
                  <el-table-column prop="path" label="文件相对路径" min-width="360" show-overflow-tooltip />
                  <el-table-column label="大小" width="110">
                    <template #default="{ row }">{{ formatBytes(row.size_bytes) }}</template>
                  </el-table-column>
                </el-table>
                <div class="update-hint">
                  共 {{ backupFilesData?.total || 0 }} 个文件{{ backupFilesData?.truncated ? '（仅显示前 500 个）' : '' }}。
                </div>
              </div>
              <template #footer>
                <el-button @click="backupFilesVisible = false">关闭</el-button>
              </template>
            </el-dialog>
          </div>
        </el-tab-pane>

        <el-tab-pane :label="t('settings.tabCluster')" name="cluster">
          <div v-loading="clusterLoading" class="cluster-panel">
            <el-alert
              v-if="!clusterSummary.license_licensed"
              type="error"
              :closable="false"
              show-icon
              title="集群部署需要有效的商业授权；试用/过期/无效授权不能启用多节点集群。"
            />
            <el-alert
              v-if="clusterSummary.max_nodes <= 1"
              type="warning"
              :closable="false"
              show-icon
              title="当前授权仅允许 1 个集群节点。多节点部署需要重新签发包含 --max-nodes 的授权，每个节点仍需各自完成机器码绑定的商业授权。"
            />

            <el-row :gutter="16" class="cluster-overview">
              <el-col :span="8">
                <div class="cluster-stat">
                  <span>授权节点上限</span>
                  <b>{{ clusterSummary.max_nodes ?? 0 }} 个</b>
                </div>
              </el-col>
              <el-col :span="8">
                <div class="cluster-stat">
                  <span>当前在线节点</span>
                  <b>{{ clusterSummary.online ?? 0 }} / {{ clusterSummary.total ?? 0 }}</b>
                </div>
              </el-col>
              <el-col :span="8">
                <div class="cluster-stat">
                  <span>本机节点 ID</span>
                  <b class="mono">{{ clusterIdentity.node_id?.slice(0, 12) || '-' }}</b>
                </div>
              </el-col>
            </el-row>

            <el-card shadow="never" class="cluster-card">
              <template #header>
                <div class="settings-card-head">
                  <span>集群配置</span>
                  <el-tag :type="clusterForm.cluster_enabled ? 'success' : 'info'" size="small">
                    {{ clusterForm.cluster_enabled ? '已启用' : '未启用' }}
                  </el-tag>
                </div>
              </template>
              <el-form label-width="140px" class="cluster-form">
                <el-form-item label="启用多节点集群">
                  <el-switch v-model="clusterForm.cluster_enabled" />
                  <span class="form-help">需要有效商业授权；节点上限由授权文件控制</span>
                </el-form-item>
                <el-form-item label="集群名称">
                  <el-input v-model="clusterForm.cluster_name" maxlength="100" placeholder="例如 生产网管集群" />
                </el-form-item>
                <el-form-item label="心跳间隔（秒）">
                  <el-input-number v-model="clusterForm.cluster_heartbeat_interval" :min="10" :max="300" :step="5" controls-position="right" />
                </el-form-item>
                <el-form-item label="本节点名称">
                  <el-input v-model="clusterIdentity.name" maxlength="120" placeholder="例如 nms-node-01" />
                </el-form-item>
                <el-form-item label="本节点地址">
                  <el-input v-model="clusterIdentity.address" maxlength="255" placeholder="192.168.10.11:8000" />
                  <span class="form-help">负载均衡配置会使用这个 host:port；每台节点需在本机设置不同地址</span>
                </el-form-item>
                <el-form-item label="本机节点 ID">
                  <el-input :model-value="clusterIdentity.node_id" readonly class="mono" />
                </el-form-item>
                <el-form-item>
                  <el-button type="primary" :loading="clusterSaving" @click="saveClusterConfig">保存集群配置</el-button>
                  <el-button :loading="clusterIdentitySaving" @click="saveClusterIdentity">保存本节点身份</el-button>
                  <el-button @click="loadCluster">刷新</el-button>
                </el-form-item>
              </el-form>
              <el-alert
                type="info"
                :closable="false"
                show-icon
                title="所有节点必须连接同一个外部数据库和 Redis，并设置相同集群名称。节点身份保存在各自服务器的 data/cluster_node.json，不会写入共享配置。"
              />
            </el-card>

            <el-card shadow="never" class="cluster-card">
              <template #header>
                <div class="settings-card-head">
                  <span>节点状态</span>
                  <span class="settings-card-sub">节点数受授权 max_nodes 限制；超限节点不会注册成功</span>
                </div>
              </template>
              <el-table :data="clusterNodes" size="small" stripe>
                <el-table-column label="状态" width="90">
                  <template #default="{ row }">
                    <el-tag :type="row.online ? 'success' : 'info'" size="small">{{ row.online ? '在线' : '离线' }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="节点" min-width="190">
                  <template #default="{ row }">
                    <div class="node-name">
                      {{ row.name }}
                      <el-tag v-if="row.local" size="small" effect="plain">本机</el-tag>
                    </div>
                    <div class="node-address">{{ row.address || '-' }}</div>
                  </template>
                </el-table-column>
                <el-table-column prop="version" label="版本" width="100" />
                <el-table-column label="授权" width="130">
                  <template #default="{ row }">
                    <el-tag :type="row.license_status === 'licensed' ? 'success' : 'danger'" size="small" effect="plain">
                      {{ row.license_status || '未知' }}
                    </el-tag>
                    <span class="node-limit">≤{{ row.license_max_nodes }} 节点</span>
                  </template>
                </el-table-column>
                <el-table-column label="权重" width="125">
                  <template #default="{ row }">
                    <el-input-number
                      v-model="row.weight"
                      :min="1"
                      :max="100"
                      size="small"
                      controls-position="right"
                      @change="saveNodeWeight(row)"
                    />
                  </template>
                </el-table-column>
                <el-table-column label="最后心跳" width="165">
                  <template #default="{ row }">{{ row.last_heartbeat ? row.last_heartbeat.replace('T', ' ').slice(0, 19) : '-' }}</template>
                </el-table-column>
                <el-table-column label="操作" width="80" fixed="right">
                  <template #default="{ row }">
                    <el-button v-if="!row.local" type="danger" link size="small" @click="removeClusterNode(row)">移除</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-card>

            <el-card shadow="never" class="cluster-card">
              <template #header>
                <div class="settings-card-head">
                  <span>负载均衡</span>
                  <el-button size="small" @click="refreshLbConfig">生成 Nginx 配置</el-button>
                </div>
              </template>
              <el-form label-width="140px" class="cluster-form">
                <el-form-item label="启用负载均衡配置">
                  <el-switch v-model="clusterForm.lb_enabled" />
                </el-form-item>
                <el-form-item label="调度策略">
                  <el-radio-group v-model="clusterForm.lb_strategy">
                    <el-radio-button value="round_robin">轮询</el-radio-button>
                    <el-radio-button value="least_conn">最少连接</el-radio-button>
                    <el-radio-button value="ip_hash">IP 哈希</el-radio-button>
                  </el-radio-group>
                </el-form-item>
                <el-form-item label="对外访问地址">
                  <el-input v-model="clusterForm.lb_public_url" placeholder="https://nms.example.com" />
                </el-form-item>
                <el-form-item label="会话保持">
                  <el-switch v-model="clusterForm.lb_sticky" />
                  <span class="form-help">开启后使用 ip_hash，与调度策略二选一</span>
                </el-form-item>
                <el-form-item>
                  <el-button type="primary" :loading="clusterSaving" @click="saveClusterConfig">保存负载均衡配置</el-button>
                </el-form-item>
              </el-form>
              <div v-if="lbConfig" class="lb-preview">
                <div class="lb-preview-head">
                  <span>节点：{{ lbConfig.nodes.length }} 个 · 策略：{{ lbConfig.strategy }}</span>
                  <el-button size="small" link type="primary" @click="copyLbConfig">复制配置</el-button>
                </div>
                <pre>{{ lbConfig.config }}</pre>
                <div class="form-help">{{ lbConfig.warning }}</div>
              </div>
              <el-empty v-else description="保存配置后点击「生成 Nginx 配置」" :image-size="50" />
            </el-card>
          </div>
        </el-tab-pane>

        <el-tab-pane :label="t('settings.tabNetwork')" name="network">
          <div v-loading="networkLoading" class="network-panel">
            <el-alert
              v-if="!networkLoading && !networkData"
              type="error"
              :closable="false"
              show-icon
              title="无法读取主机网络信息，请检查后端运行账户权限。"
            />
            <template v-if="networkData">
              <el-alert
                v-if="!networkData.admin"
                type="error"
                :closable="false"
                show-icon
                title="当前后端进程没有管理员/root 权限：可以查看主机信息，但修改网卡、路由、服务、防火墙和计划任务会失败。请以管理员身份运行服务。"
              />
              <el-alert
                type="warning"
                :closable="false"
                show-icon
                title="高风险操作：修改网卡 IP 或防火墙可能导致当前 Web 连接中断。请提前准备服务器控制台/带外管理，并确认已保存当前配置。修改后如未生效，可使用「重启网络服务」重新加载配置。"
              />

              <div class="network-stat-grid">
                <div class="network-stat">
                  <span>操作系统</span>
                  <b>{{ networkData.system }} {{ networkData.release }}</b>
                </div>
                <div class="network-stat">
                  <span>主机名</span>
                  <b>{{ networkData.hostname }}</b>
                </div>
                <div class="network-stat">
                  <span>执行权限</span>
                  <b :class="networkData.admin ? 'ok' : 'danger'">{{ networkData.admin ? '管理员 / root' : '普通权限' }}</b>
                </div>
                <div class="network-stat">
                  <span>防火墙</span>
                  <b :class="networkData.firewall?.enabled ? 'ok' : 'danger'">
                    {{ networkData.firewall?.backend || '-' }} ·
                    {{ networkData.firewall?.enabled ? '已启用' : '已关闭' }}
                  </b>
                </div>
              </div>

              <el-card shadow="never" class="network-card">
                <template #header>
                  <div class="settings-card-head">
                    <span>网卡与 IP</span>
                    <div>
                      <el-button
                        v-if="networkData.supports?.network_restart"
                        type="danger"
                        plain
                        size="small"
                        :loading="networkRestarting"
                        @click="restartNetworkService"
                      >
                        重启网络服务
                      </el-button>
                      <el-button size="small" @click="loadNetwork">刷新</el-button>
                    </div>
                  </div>
                </template>
                <el-table :data="networkData.adapters" size="small" stripe>
                  <el-table-column label="网卡" min-width="180">
                    <template #default="{ row }">
                      <div class="node-name">{{ row.name }}</div>
                      <div class="node-address">{{ row.description || '-' }}</div>
                    </template>
                  </el-table-column>
                  <el-table-column label="状态" width="90">
                    <template #default="{ row }">
                      <el-tag :type="row.status === 'Up' || row.status === 'UP' ? 'success' : 'info'" size="small">
                        {{ row.status || '-' }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column label="IP / 前缀" width="180">
                    <template #default="{ row }">
                      <span class="mono">{{ row.ip || '-' }}<template v-if="row.ip">/{{ row.prefix }}</template></span>
                    </template>
                  </el-table-column>
                  <el-table-column label="网关" width="140">
                    <template #default="{ row }"><span class="mono">{{ row.gateway || '-' }}</span></template>
                  </el-table-column>
                  <el-table-column label="DNS" min-width="170">
                    <template #default="{ row }"><span class="mono">{{ (row.dns || []).join(', ') || '-' }}</span></template>
                  </el-table-column>
                  <el-table-column label="地址模式" width="100">
                    <template #default="{ row }">
                      {{ row.dhcp === true ? 'DHCP' : (row.dhcp === false ? '静态' : '-') }}
                    </template>
                  </el-table-column>
                  <el-table-column label="操作" width="110" fixed="right">
                    <template #default="{ row }">
                      <el-button
                        type="primary"
                        link
                        size="small"
                        :disabled="!networkData.admin || !networkData.supports.adapter_config"
                        @click="openAdapterDialog(row)"
                      >配置 IP</el-button>
                    </template>
                  </el-table-column>
                </el-table>
                <div v-if="!networkData.supports.adapter_config" class="form-help network-note">
                  Linux 修改网卡 IP 目前要求安装 NetworkManager（nmcli）；未检测到 nmcli 时只支持查看。
                </div>
              </el-card>

              <el-card shadow="never" class="network-card">
                <template #header>
                  <div class="settings-card-head">
                    <span>明细路由</span>
                    <el-button
                      type="primary"
                      size="small"
                      :disabled="!networkData.admin"
                      @click="openRouteDialog"
                    >添加路由</el-button>
                  </div>
                </template>
                <el-table :data="networkData.routes" size="small" stripe max-height="330">
                  <el-table-column label="目标网段" min-width="180">
                    <template #default="{ row }"><span class="mono">{{ row.destination }}</span></template>
                  </el-table-column>
                  <el-table-column label="下一跳" min-width="150">
                    <template #default="{ row }"><span class="mono">{{ row.gateway || '直连' }}</span></template>
                  </el-table-column>
                  <el-table-column label="网卡" min-width="120">
                    <template #default="{ row }">{{ row.interface || '-' }}</template>
                  </el-table-column>
                  <el-table-column prop="metric" label="Metric" width="80" />
                  <el-table-column label="操作" width="80" fixed="right">
                    <template #default="{ row }">
                      <el-button type="danger" link size="small" :disabled="!networkData.admin" @click="removeRoute(row)">删除</el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </el-card>

              <el-card shadow="never" class="network-card">
                <template #header>
                  <div class="settings-card-head">
                    <span>防火墙</span>
                    <el-tag :type="networkData.firewall?.enabled ? 'success' : 'warning'" size="small">
                      {{ networkData.firewall?.backend || '-' }} · {{ networkData.firewall?.enabled ? '已启用' : '已关闭' }}
                    </el-tag>
                  </div>
                </template>
                <div class="firewall-row">
                  <div>
                    <strong>{{ networkData.firewall?.enabled ? '防火墙正在保护主机' : '防火墙当前已关闭' }}</strong>
                    <p>关闭后主机端口将直接暴露；请确认已有其他边界防护或临时操作窗口。</p>
                  </div>
                  <el-button
                    :type="networkData.firewall?.enabled ? 'danger' : 'success'"
                    :disabled="!networkData.admin || !networkData.firewall?.available"
                    @click="toggleFirewall"
                  >
                    {{ networkData.firewall?.enabled ? '关闭防火墙' : '启用防火墙' }}
                  </el-button>
                </div>
                <div v-if="!networkData.firewall?.available" class="form-help">未检测到 Windows Firewall / ufw / firewalld。</div>
              </el-card>

              <el-card shadow="never" class="network-card">
                <template #header>
                  <div class="settings-card-head">
                    <span>系统服务</span>
                    <div class="network-search">
                      <el-input
                        v-model="networkServiceQuery"
                        clearable
                        placeholder="搜索服务名/显示名"
                        size="small"
                        @keyup.enter="reloadNetworkServices"
                      />
                      <el-button size="small" @click="reloadNetworkServices">查询</el-button>
                    </div>
                  </div>
                </template>
                <el-table :data="networkServices" v-loading="networkServicesLoading" size="small" stripe max-height="360">
                  <el-table-column prop="display_name" label="服务" min-width="220" show-overflow-tooltip />
                  <el-table-column prop="name" label="服务名" min-width="170" show-overflow-tooltip />
                  <el-table-column label="状态" width="90">
                    <template #default="{ row }">
                      <el-tag :type="String(row.status).toLowerCase().includes('running') ? 'success' : 'info'" size="small">
                        {{ row.status }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="startup" label="启动类型" width="110" />
                  <el-table-column label="操作" width="250" fixed="right">
                    <template #default="{ row }">
                      <el-button
                        link type="primary" size="small"
                        :loading="networkActionBusy === `service:${row.name}:start`"
                        :disabled="!networkData.admin"
                        @click="performServiceAction(row, 'start')"
                      >启动</el-button>
                      <el-button link type="warning" size="small" :disabled="!networkData.admin" @click="performServiceAction(row, 'stop')">停止</el-button>
                      <el-button link type="primary" size="small" :disabled="!networkData.admin" @click="performServiceAction(row, 'restart')">重启</el-button>
                      <el-button link type="success" size="small" :disabled="!networkData.admin" @click="performServiceAction(row, 'enable')">自启</el-button>
                      <el-button link type="info" size="small" :disabled="!networkData.admin" @click="performServiceAction(row, 'disable')">禁用</el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </el-card>

              <el-card shadow="never" class="network-card">
                <template #header>
                  <div class="settings-card-head">
                    <span>计划任务</span>
                    <el-button size="small" @click="loadNetwork">刷新</el-button>
                  </div>
                </template>
                <el-table :data="networkTasks" v-loading="networkTasksLoading" size="small" stripe max-height="330">
                  <el-table-column prop="name" label="任务" min-width="230" show-overflow-tooltip />
                  <el-table-column prop="path" label="路径/类型" min-width="150" show-overflow-tooltip />
                  <el-table-column prop="status" label="状态" width="120" />
                  <el-table-column label="操作" width="220" fixed="right">
                    <template #default="{ row }">
                      <el-button link type="primary" size="small" :disabled="!networkData.admin" @click="performTaskAction(row, 'start')">启动</el-button>
                      <el-button link type="warning" size="small" :disabled="!networkData.admin" @click="performTaskAction(row, 'stop')">停止</el-button>
                      <el-button link type="success" size="small" :disabled="!networkData.admin" @click="performTaskAction(row, 'enable')">启用</el-button>
                      <el-button link type="info" size="small" :disabled="!networkData.admin" @click="performTaskAction(row, 'disable')">停用</el-button>
                    </template>
                  </el-table-column>
                </el-table>
                <div class="form-help network-note">计划任务当前支持现有任务的启动/停止/启用/停用；出于安全考虑，暂不开放网页创建任意命令任务。</div>
              </el-card>
            </template>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <el-dialog v-model="adapterDialogVisible" :title="`配置网卡 IP · ${adapterForm.name}`" width="620px">
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="提交后网卡配置立即生效，可能导致当前 Web 连接中断。请确认可以通过服务器控制台恢复。"
        class="adapter-alert"
      />
      <el-form label-width="105px" class="adapter-form">
        <el-form-item label="网卡">
          <el-input v-model="adapterForm.name" readonly />
          <div class="form-help">{{ adapterForm.description }}</div>
        </el-form-item>
        <el-form-item label="地址模式">
          <el-radio-group v-model="adapterForm.mode">
            <el-radio-button value="static">静态 IP</el-radio-button>
            <el-radio-button value="dhcp">DHCP 自动</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <template v-if="adapterForm.mode === 'static'">
          <el-form-item label="IP 地址">
            <el-input v-model="adapterForm.ip" placeholder="例如 192.168.10.20" />
          </el-form-item>
          <el-form-item label="子网前缀">
            <el-input-number v-model="adapterForm.prefix" :min="1" :max="32" controls-position="right" />
            <span class="form-help">例如 /24 对应 255.255.255.0</span>
          </el-form-item>
          <el-form-item label="默认网关">
            <el-input v-model="adapterForm.gateway" placeholder="例如 192.168.10.1；可留空" />
          </el-form-item>
          <el-form-item label="DNS">
            <el-input v-model="adapterForm.dns" placeholder="多个 DNS 用英文逗号分隔" />
          </el-form-item>
        </template>
        <el-alert
          v-else
          type="info"
          :closable="false"
          show-icon
          title="DHCP 模式会清除该网卡的静态地址、网关和 DNS，改为从 DHCP 获取。"
        />
      </el-form>
      <template #footer>
        <el-button @click="adapterDialogVisible = false">取消</el-button>
        <el-button type="danger" :loading="adapterSaving" @click="saveAdapter">确认修改网卡</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="routeDialogVisible" title="添加明细路由" width="540px">
      <el-form label-width="100px">
        <el-form-item label="目标网段">
          <el-input v-model="routeForm.destination" placeholder="例如 10.30.0.0/16" />
        </el-form-item>
        <el-form-item label="下一跳">
          <el-input v-model="routeForm.gateway" placeholder="例如 192.168.10.1；与出口网卡至少填写一项" />
        </el-form-item>
        <el-form-item label="出口网卡">
          <el-select v-model="routeForm.interface" clearable placeholder="自动/选择网卡" style="width: 100%">
            <el-option v-for="item in networkData?.adapters || []" :key="item.name" :label="item.name" :value="item.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="Metric">
          <el-input-number v-model="routeForm.metric" :min="1" :max="9999" controls-position="right" />
        </el-form-item>
      </el-form>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="Windows 使用持久化路由；Linux 使用 ip route 立即生效。下一跳和出口网卡至少填写一项；都留空时自动使用默认出口网卡。"
      />
      <template #footer>
        <el-button @click="routeDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="routeSaving" @click="saveRoute">确认添加</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="copyrightPrivilegeVisible" title="验证品牌特权口令" width="560px">
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="版权信息属于品牌保护项"
        description="请在授权签发平台输入本机机器码生成品牌特权口令；口令只对本机有效，默认 15 分钟。"
        class="ins-alert"
      />
      <el-input
        v-model="copyrightPrivilegeInput"
        type="textarea"
        :rows="6"
        placeholder="粘贴授权签发平台生成的品牌特权口令"
        spellcheck="false"
      />
      <template #footer>
        <el-button @click="copyrightPrivilegeVisible = false">取消</el-button>
        <el-button type="primary" :loading="copyrightVerifying" @click="verifyCopyrightPrivilege">验证并解锁</el-button>
      </template>
    </el-dialog>

    <!-- 最近日志 -->
    <el-dialog v-model="recentVisible" :title="t('settings.recentLogsTitle')" width="980px" top="6vh">
      <div class="filters">
        <el-select v-model="recentLevel" :placeholder="t('settings.allLevels')" clearable style="width: 150px" @change="loadRecentLogs">
          <el-option label="ERROR" value="ERROR" />
          <el-option label="WARNING" value="WARNING" />
          <el-option label="INFO" value="INFO" />
        </el-select>
        <el-input
          v-model="recentKeyword"
          :placeholder="t('settings.keywordFilter')"
          clearable
          style="width: 260px"
          @keyup.enter="loadRecentLogs"
          @clear="loadRecentLogs"
        />
        <el-button @click="loadRecentLogs" :loading="recentLoading">{{ t('common.refresh') }}</el-button>
        <span class="muted">{{ recentFile }}</span>
      </div>
      <pre class="log-lines">{{ recentLines.join('\n') || t('settings.noLogs') }}</pre>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { settingsApi, authApi, healthApi, systemApi, clusterApi, networkApi, websiteApi, userApi, licenseApi } from '@/api'
import apiRequest from '@/api'
import SystemUsers from '@/views/SystemUsers.vue'
import {
  alertSoundEnabled,
  playAlertSound,
  loadAlertSoundInfo,
  speakAlertBroadcast,
} from '@/utils/alertSound'
import { currentUser, can, logout, downloadWithAuth } from '@/store/auth'
import { settings, loadPublicSettings } from '@/store/settings'
import { availableLocales, t } from '@/i18n'
import { TIMEZONE_OPTIONS } from '@/store/settings'
import { formatDateTime } from '@/utils/time'

const loading = ref(false)
const loaded = ref(false)
const saving = ref(false)
const copyrightPrivilegeVisible = ref(false)
const copyrightPrivilegeInput = ref('')
const copyrightPrivilegeToken = ref('')
const copyrightUnlockedUntil = ref(0)
const copyrightPrivilegeNow = ref(Date.now())
const copyrightVerifying = ref(false)
const copyrightUnlocked = computed(() => copyrightUnlockedUntil.value > copyrightPrivilegeNow.value)
const copyrightUnlockText = computed(() => Math.max(0, Math.ceil((copyrightUnlockedUntil.value - copyrightPrivilegeNow.value) / 60000)))
let copyrightPrivilegeTimer = null
const startupInfo = ref(null)
const startupLoading = ref(false)
const startupSaving = ref(false)

// 系统更新
const updateInfo = ref(null)
const updateUrl = ref('')
const updateLoading = ref(false)
const updateSaving = ref(false)
const onlineChecking = ref(false)
const updateStarting = ref(false)
const updateUploading = ref(false)
const updateUploadProgress = ref(0)
const updateUploadLoaded = ref(0)
const updateUploadTotal = ref(0)
const onlineCheck = ref(null)
const updateFile = ref(null)
const updateFileInput = ref(null)
const updateForce = ref(false)
const updateJob = ref(null)
const rollbackStarting = ref(false)
const deletingBackupId = ref('')
const backupFilesVisible = ref(false)
const backupFilesLoading = ref(false)
const backupFilesData = ref(null)
let updatePollTimer = null
let updatePollCount = 0
let updateAuthFailures = 0

const updateStep = computed(() => {
  const status = updateJob.value?.status
  return ({ queued: 0, backup: 1, applying: 2, dependencies: 3, restarting: 4, rollback: 4, success: 5, failed: 2, rolled_back: 2 }[status] ?? 0)
})
const updateProcessStatus = computed(() => (
  ['failed', 'rolled_back'].includes(updateJob.value?.status) ? 'error' : 'process'
))
const updateJobAlertType = computed(() => {
  const status = updateJob.value?.status
  if (status === 'success') return 'success'
  if (['failed', 'rolled_back'].includes(status)) return 'error'
  return 'info'
})
const route = useRoute()
const allowedTabs = ['basic', 'users', 'security', 'integration', 'collection', 'logforward', 'backup', 'status', 'startup', 'time', 'totp', 'cluster', 'network', 'update']
const activeTab = ref(allowedTabs.includes(String(route.query.tab || '')) ? String(route.query.tab) : 'status')

watch(
  () => route.query.tab,
  (tab) => {
    const value = String(tab || '')
    if (allowedTabs.includes(value)) activeTab.value = value
  }
)

watch(activeTab, (tab) => {
  if (tab === 'network' && !networkData.value && !networkLoading.value) loadNetwork()
  if (tab === 'update') loadUpdateInfo()
})

// 运行状态（数据库 / 缓存）
const health = ref(null)
const integrationTesting = ref(false)
const integrationTestResult = ref(null)
const redisTesting = ref(false)
const redisTestResult = ref(null)
const runtimeInfo = ref(null)
const clusterLoading = ref(false)
const clusterSaving = ref(false)
const clusterIdentitySaving = ref(false)
const clusterData = ref(null)
const clusterNodes = ref([])
const clusterSummary = ref({})
const clusterIdentity = reactive({ name: '', address: '' })
const clusterForm = reactive({
  cluster_enabled: false,
  cluster_name: '',
  cluster_heartbeat_interval: 30,
  lb_enabled: false,
  lb_strategy: 'round_robin',
  lb_public_url: '',
  lb_sticky: false,
})
const CLUSTER_SETTING_KEYS = new Set([
  'cluster_enabled', 'cluster_name', 'cluster_heartbeat_interval',
  'lb_enabled', 'lb_strategy', 'lb_public_url', 'lb_sticky',
])
const lbConfig = ref(null)

// 主机网络
const networkLoading = ref(false)
const networkServicesLoading = ref(false)
const networkTasksLoading = ref(false)
const networkRestarting = ref(false)
const networkData = ref(null)
const networkServices = ref([])
const networkTasks = ref([])
const networkServiceQuery = ref('')
const networkActionBusy = ref('')
const adapterDialogVisible = ref(false)
const routeDialogVisible = ref(false)
const adapterSaving = ref(false)
const routeSaving = ref(false)
const adapterForm = reactive({
  name: '', description: '', mode: 'static', ip: '', prefix: 24, gateway: '', dns: '',
})
const routeForm = reactive({
  destination: '', gateway: '', interface: '', metric: 10,
})
const versionInfo = ref(null)
const effectiveVersion = computed(() => versionInfo.value?.effective || null)
const effectiveVersionText = computed(() => {
  const value = String(effectiveVersion.value?.display_version || effectiveVersion.value?.version || '').trim()
  if (!value) return ''
  return value.startsWith('v') ? value : `v${value}`
})
const versionBuiltAtText = computed(() => {
  const raw = effectiveVersion.value?.built_at
  if (!raw) return ''
  const date = new Date(raw)
  return Number.isNaN(date.getTime()) ? raw : date.toLocaleString('zh-CN', { hour12: false })
})
const hostStatus = ref(null)
const hostStatusLoading = ref(false)
const hostStatusError = ref('')
const portScope = ref('all')
const currentOrigin = window.location.origin
const displayPorts = computed(() => {
  const items = hostStatus.value?.ports?.items || []
  if (portScope.value === 'expected') return items.filter((item) => item.expected || item.critical)
  return items
})

function portStatusType(row) {
  if (row.listening) return 'success'
  return row.critical ? 'danger' : 'warning'
}

function portStatusText(row) {
  if (row.scope === 'internal') return row.listening ? '内部监听' : '内部未监听'
  if (row.listening) return row.bind_all ? '对外监听' : '本机监听'
  return row.critical ? '关键端口未监听' : '未监听'
}
const diskSummary = computed(() => {
  const disks = hostStatus.value?.disks || []
  const total = disks.reduce((sum, disk) => sum + Number(disk.total || 0), 0)
  const used = disks.reduce((sum, disk) => sum + Number(disk.used || 0), 0)
  const free = Math.max(0, total - used)
  return { total, used, free, percent: total ? Math.round(used / total * 1000) / 10 : 0 }
})
// 登录安全状态
const securityInfo = ref(null)
// Web 登录网关 / HTTPS 证书
const webCertificates = ref([])
const webGateway = ref({ running: false, listeners: [], error: '', internal_port: 8000 })
const webGatewayApplying = ref(false)
const webDiagnoseLoading = ref(false)
const webSslUploading = ref(false)
const webCertFileInput = ref(null)
const webKeyFileInput = ref(null)
const webChainFileInput = ref(null)
const webSslFiles = reactive({ cert: null, key: null, chain: null })
const webGatewayListenersText = computed(() => {
  const listeners = (webGateway.value.listeners || [])
    .filter((item) => item.port)
    .map((item) => {
      const mode = item.mode === 'redirect' ? '（跳转）' : ''
      return `${String(item.protocol || '').toUpperCase()} :${item.port}${mode}`
    })
  if (!listeners.length) return t('settings.webGatewayStopped')
  return `${t('settings.webGatewayRunning')}：${listeners.join(' / ')}`
})
// 配置导入导出
const exporting = ref(false)
const importing = ref(false)
const importDryRun = ref(false)
const importResult = ref(null)
const importError = ref('')
const configFileRef = ref(null)
// 数据库备份
const backups = ref([])
const backupConfig = ref(null)
const backupLoading = ref(false)
const backupCreating = ref(false)
// 告警声音文件（按严重级别）
const SOUND_LEVELS = [
  { value: 'info', labelKey: 'settings.soundLevelInfo', builtinKey: 'settings.soundBuiltinInfo' },
  { value: 'warning', labelKey: 'settings.soundLevelWarning', builtinKey: 'settings.soundBuiltinWarning' },
  { value: 'critical', labelKey: 'settings.soundLevelCritical', builtinKey: 'settings.soundBuiltinCritical' },
  { value: 'emergency', labelKey: 'settings.soundLevelEmergency', builtinKey: 'settings.soundBuiltinEmergency' },
]
const BROADCAST_LEVEL_OPTIONS = SOUND_LEVELS
const broadcastLevels = computed({
  get: () => String(form.alert_broadcast_levels || '')
    .split(',')
    .map((item) => item.trim())
    .filter((item) => SOUND_LEVELS.some((level) => level.value === item)),
  set: (value) => {
    form.alert_broadcast_levels = (Array.isArray(value) ? value : []).join(',')
  },
})
const soundInfo = ref(null)
const soundFileRef = ref(null)
const soundUploading = ref(false)
const soundEditLevel = ref('emergency')

function soundLevelInfo(level) {
  return soundInfo.value?.levels?.[level]
    || (level === 'emergency' ? soundInfo.value : null)
    || { custom: false, filename: '', url: '' }
}
const logoFileRef = ref(null)
const logoUploading = ref(false)
const cacheBackendText = computed(() => {
  const backend = health.value?.cache?.backend
  if (backend === 'redis') return 'Redis'
  if (backend === 'memory') return t('settings.cacheMemory')
  if (backend === 'disabled') return t('settings.cacheDisabled')
  return '-'
})
const cacheStatsText = computed(() => {
  const stats = health.value?.cache?.stats
  if (!stats) return ''
  return t('settings.cacheStats', { hits: stats.hits ?? 0, misses: stats.misses ?? 0 })
})

async function loadHealth() {
  try {
    const res = await healthApi.check()
    health.value = res.data
  } catch {
    health.value = null
  }
}

function formatBytes(value) {
  const num = Number(value || 0)
  if (!num) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let index = 0
  let size = num
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024
    index += 1
  }
  return `${size >= 100 ? size.toFixed(0) : size.toFixed(index ? 1 : 0)} ${units[index]}`
}

function formatBps(value) {
  return `${formatBytes(value)}/s`
}

function formatUptime(seconds) {
  const total = Math.max(0, Number(seconds || 0))
  const days = Math.floor(total / 86400)
  const hours = Math.floor((total % 86400) / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  if (days) return `${days}天${hours}小时`
  if (hours) return `${hours}小时${minutes}分`
  return `${minutes}分`
}

function usageStatus(percent) {
  const value = Number(percent || 0)
  if (value >= 90) return 'exception'
  if (value >= 75) return 'warning'
  return 'success'
}

function serviceStatusText(status) {
  return { running: '运行中', stopped: '已停止', error: '异常', disabled: '未启用' }[status] || status || '未知'
}

function serviceStatusType(status) {
  return { running: 'success', stopped: 'danger', error: 'danger', disabled: 'info' }[status] || 'info'
}

async function loadHostStatus() {
  hostStatusLoading.value = true
  hostStatusError.value = ''
  try {
    const res = await systemApi.hostStatus()
    hostStatus.value = res.data
  } catch (error) {
    hostStatusError.value = error.message || '读取主机状态失败'
  } finally {
    hostStatusLoading.value = false
  }
}

async function loadSecurityInfo() {
  try {
    const res = await settingsApi.securityInfo()
    securityInfo.value = res.data
  } catch {
    securityInfo.value = null
  }
}

async function exportConfig() {
  exporting.value = true
  try {
    await downloadWithAuth('/api/settings/export')
    ElMessage.success(t('settings.exportStarted'))
  } catch (e) {
    ElMessage.error(e.message || t('settings.exportFailed'))
  } finally {
    exporting.value = false
  }
}

function triggerImport() {
  configFileRef.value?.click()
}

async function onConfigSelected(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  if (!file.name.toLowerCase().endsWith('.json')) {
    ElMessage.error(t('settings.selectJsonFile'))
    return
  }
  if (!importDryRun.value) {
    try {
      await ElMessageBox.confirm(
        t('settings.importConfirm'),
        t('settings.importConfig'),
        { type: 'warning', confirmButtonText: t('settings.confirmImport'), cancelButtonText: t('common.cancel') }
      )
    } catch {
      return
    }
  }
  importing.value = true
  importError.value = ''
  importResult.value = null
  try {
    const formData = new FormData()
    formData.append('file', file)
    const res = await settingsApi.importConfig(formData, importDryRun.value, copyrightUnlocked.value ? copyrightPrivilegeToken.value : '')
    importResult.value = { ...res.data, filename: file.name }
    ElMessage.success(
      importDryRun.value
        ? t('settings.dryRunSuccess', { count: res.data.settings_count })
        : t('settings.importSuccess', { count: res.data.settings_count, added: res.data.channel_new, updated: res.data.channel_updated })
    )
    if (!importDryRun.value) {
      await loadAll()
      await loadSecurityInfo()
    }
  } catch (e) {
    importError.value = e.message || t('settings.importFailed')
  } finally {
    importing.value = false
  }
}

// 日志转发
const FACILITY_OPTIONS = [
  'local0', 'local1', 'local2', 'local3', 'local4',
  'local5', 'local6', 'local7',
  'user', 'daemon', 'auth', 'authpriv', 'syslog', 'kern',
]
const forwardStatus = ref(null)
const statusLoading = ref(false)
const testing = ref(false)
const forwardEnabled = computed(() => !!form.log_forward_enabled)

// 最近日志
const recentVisible = ref(false)
const recentLoading = ref(false)
const recentLevel = ref('')
const recentKeyword = ref('')
const recentLines = ref([])
const recentFile = ref('')

const languageOptions = availableLocales
const timezoneOptions = TIMEZONE_OPTIONS

const canEdit = computed(() => currentUser.value?.is_superuser === true)

const form = reactive({
  system_name: t('header.defaultSystemName'),
  login_subtitle: '设备监测 · 机房与网站监测 · 即时通信 · 设备备份 · 虚拟化纳管 · 智能运维',
  system_logo: '',
  copyright_enabled: true,
  copyright_name: '智能运维服务平台',
  copyright_text: `© ${new Date().getFullYear()} 智能运维服务平台 版权所有`,
  copyright_color: '#94a3b8',
  language: 'zh-CN',
  timezone: 'Asia/Shanghai',
  refresh_interval: 30,
  auto_logout_minutes: 30,
  auto_login: false,
  captcha_enabled: true,
  collection_interval: 60,
  // 登录安全
  login_lock_enabled: true,
  login_max_attempts: 5,
  login_lock_minutes: 15,
  web_http_enabled: true,
  web_http_port: 80,
  web_https_enabled: false,
  web_https_port: 443,
  web_protocol: 'http',
  web_login_port: 80,
  web_https_redirect_http: true,
  web_ssl_certificate_id: 0,
  ip_whitelist_enabled: false,
  ip_whitelist: '',
  trust_proxy: false,
  audit_retention_days: 180,
  // 密码复杂度
  password_min_length: 8,
  password_require_uppercase: true,
  password_require_lowercase: true,
  password_require_digit: true,
  password_require_special: true,
  password_expiry_days: 90,
  first_login_password_change: true,
  totp_policy: 'off',
  totp_required_user_ids: '',
  // 数据库自动备份
  backup_enabled: true,
  backup_interval_hours: 24,
  backup_retention_count: 7,
  // 告警声音提醒间隔（秒）
  alert_sound_interval: 60,
  // 告警详细语音播报
  alert_broadcast_enabled: true,
  alert_broadcast_counts: true,
  alert_broadcast_details: true,
  alert_broadcast_levels: 'info,warning,critical,emergency',
  alert_broadcast_max_items: 3,
  alert_realert_minutes: 30,
  // 日志转发
  log_forward_enabled: false,
  log_forward_type: 'syslog',
  log_forward_min_level: 'INFO',
  log_forward_host: '',
  log_forward_port: 514,
  log_forward_protocol: 'udp',
  log_forward_format: 'rfc5424',
  log_forward_facility: 'local0',
  log_forward_app_name: 'snmp-nms',
  log_forward_http_url: '',
  log_forward_http_headers: '',
  log_forward_file_path: '',
  // 外部数据接口对接
  integration_enabled: false,
  integration_name: '',
  integration_db_type: 'mysql',
  integration_host: '',
  integration_port: 3306,
  integration_database: '',
  integration_username: '',
  integration_password: '',
  integration_sqlite_path: '',
  integration_charset: 'utf8mb4',
  integration_timeout: 10,
  integration_sync_interval: 60,
  // Redis / 缓存
  redis_enabled: true,
  redis_url: '',
  cache_ttl_topology: 5,
  cache_ttl_dashboard: 3,
})

const copyrightPreview = computed(() => {
  const currentText = String(form.copyright_text || '')
  const year = (currentText.match(/©\s*(\d{4})/) || [])[1] || String(new Date().getFullYear())
  const name = String(form.copyright_name || '').trim() || t('settings.copyrightNamePlaceholder')
  return `© ${year} ${name} 版权所有`
})

const settingsUsers = ref([])
const totpSelectedUserIds = computed({
  get: () => String(form.totp_required_user_ids || '')
    .split(',')
    .map((item) => Number(item.trim()))
    .filter((item) => Number.isFinite(item) && item > 0),
  set: (value) => {
    form.totp_required_user_ids = (Array.isArray(value) ? value : []).join(',')
  },
})

async function loadSettingsUsers() {
  try {
    const res = await userApi.list({})
    settingsUsers.value = res.data?.items || []
  } catch {
    settingsUsers.value = []
  }
}

const passwordFormRef = ref(null)
const passwordForm = reactive({ old_password: '', new_password: '', confirm: '' })
const passwordSaving = ref(false)

const passwordPolicyHint = computed(() => {
  const min = Number(form.password_min_length) || 8
  const parts = [t('settings.passwordMinDynamic', { min })]
  if (form.password_require_uppercase) parts.push(t('settings.passwordUppercase'))
  if (form.password_require_lowercase) parts.push(t('settings.passwordLowercase'))
  if (form.password_require_digit) parts.push(t('settings.passwordDigit'))
  if (form.password_require_special) parts.push(t('settings.passwordSpecial'))
  return `${t('settings.passwordPolicyCurrent')}：${parts.join('，')}`
})

const passwordRules = computed(() => {
  const min = Number(form.password_min_length) || 8
  const rules = {
    old_password: [{ required: true, message: t('settings.oldPasswordRequired'), trigger: 'blur' }],
    new_password: [
      { required: true, message: t('settings.newPasswordRequired'), trigger: 'blur' },
      {
        min,
        message: t('settings.passwordMinDynamic', { min }),
        trigger: 'blur',
      },
    ],
    confirm: [
      { required: true, message: t('settings.confirmPasswordRequired'), trigger: 'blur' },
      {
        validator: (_rule, value, callback) => {
          if (value !== passwordForm.new_password) callback(new Error(t('settings.passwordMismatch')))
          else callback()
        },
        trigger: 'blur',
      },
    ],
  }
  const addPattern = (enabled, regex, messageKey) => {
    if (!enabled) return
    rules.new_password.push({
      validator: (_rule, value, callback) => {
        if (value && !regex.test(value)) callback(new Error(t(messageKey)))
        else callback()
      },
      trigger: 'blur',
    })
  }
  addPattern(form.password_require_uppercase, /[A-Z]/, 'settings.passwordNeedUppercase')
  addPattern(form.password_require_lowercase, /[a-z]/, 'settings.passwordNeedLowercase')
  addPattern(form.password_require_digit, /\d/, 'settings.passwordNeedDigit')
  addPattern(form.password_require_special, /[^A-Za-z0-9]/, 'settings.passwordNeedSpecial')
  return rules
})

async function loadCluster() {
  clusterLoading.value = true
  try {
    const res = await clusterApi.status()
    clusterData.value = res.data
    clusterNodes.value = res.data.nodes || []
    clusterSummary.value = res.data.summary || {}
    Object.assign(clusterIdentity, res.data.identity || {})
    Object.assign(clusterForm, res.data.settings || {})
    try {
      const lb = await clusterApi.lbConfig()
      lbConfig.value = lb.data
    } catch {
      lbConfig.value = null
    }
  } catch (error) {
    ElMessage.warning(error?.response?.data?.detail || error?.message || '加载集群状态失败')
  } finally {
    clusterLoading.value = false
  }
}

async function saveClusterConfig() {
  clusterSaving.value = true
  try {
    const res = await clusterApi.updateConfig({ ...clusterForm })
    clusterData.value = res.data.status
    clusterNodes.value = res.data.status.nodes || []
    clusterSummary.value = res.data.status.summary || {}
    ElMessage.success('集群配置已保存')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '集群配置保存失败')
  } finally {
    clusterSaving.value = false
  }
}

async function saveClusterIdentity() {
  clusterIdentitySaving.value = true
  try {
    const res = await clusterApi.updateIdentity({ ...clusterIdentity })
    Object.assign(clusterIdentity, res.data.identity || {})
    ElMessage.success('节点身份已保存，下一次心跳生效')
    await loadCluster()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '节点身份保存失败')
  } finally {
    clusterIdentitySaving.value = false
  }
}

async function refreshLbConfig() {
  try {
    const res = await clusterApi.lbConfig()
    lbConfig.value = res.data
    ElMessage.success('负载均衡配置已生成')
  } catch (error) {
    lbConfig.value = null
    ElMessage.warning(error?.response?.data?.detail || error?.message || '生成负载均衡配置失败')
  }
}

async function copyLbConfig() {
  if (!lbConfig.value?.config) return
  try {
    await navigator.clipboard.writeText(lbConfig.value.config)
    ElMessage.success('负载均衡配置已复制')
  } catch {
    ElMessage.warning('复制失败，请手动选择文本')
  }
}

async function saveNodeWeight(node) {
  try {
    await clusterApi.updateWeight(node.node_id, Number(node.weight) || 1)
    ElMessage.success('节点权重已更新')
    await loadCluster()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '节点权重更新失败')
  }
}

async function removeClusterNode(node) {
  try {
    await ElMessageBox.confirm(`确定移除节点「${node.name}」吗？`, '移除节点', { type: 'warning' })
    await clusterApi.removeNode(node.node_id)
    ElMessage.success('节点已移除')
    await loadCluster()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(error?.response?.data?.detail || error?.message || '移除节点失败')
    }
  }
}

async function loadNetworkExtras() {
  networkServicesLoading.value = true
  networkTasksLoading.value = true
  const [servicesResult, tasksResult] = await Promise.allSettled([
    networkApi.services({ query: networkServiceQuery.value, limit: 300 }),
    networkApi.scheduledTasks(),
  ])
  if (servicesResult.status === 'fulfilled') {
    networkServices.value = servicesResult.value.data.items || []
  }
  if (tasksResult.status === 'fulfilled') {
    networkTasks.value = tasksResult.value.data.items || []
  }
  networkServicesLoading.value = false
  networkTasksLoading.value = false
}

async function loadNetwork() {
  networkLoading.value = true
  try {
    // 先只加载网卡/路由/防火墙，页面立即可用；服务与计划任务在后台补载
    const overview = await networkApi.overview()
    networkData.value = overview.data
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '读取主机网络信息失败')
    networkLoading.value = false
    return
  }
  networkLoading.value = false
  loadNetworkExtras()
}

async function restartNetworkService() {
  try {
    await ElMessageBox.confirm(
      '重启网络服务会重新加载网卡配置，可能导致当前网页连接短暂中断。请确认已准备好服务器控制台或带外管理，并已保存当前配置。',
      '重启网络服务',
      { type: 'warning', confirmButtonText: '确认重启', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  networkRestarting.value = true
  try {
    const res = await networkApi.restartNetwork({ confirm: true })
    const service = res.data.service || '网络服务'
    ElMessage.success(`${service} 已重启，请重新检查网卡 IP 和服务状态`)
    await loadNetwork()
  } catch (error) {
    const detail = error?.response?.data?.detail || error?.message || '重启网络服务失败'
    ElMessage.error(detail)
  } finally {
    networkRestarting.value = false
  }
}

async function reloadNetworkServices() {
  networkServicesLoading.value = true
  try {
    const res = await networkApi.services({ query: networkServiceQuery.value, limit: 300 })
    networkServices.value = res.data.items || []
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '读取服务列表失败')
  } finally {
    networkServicesLoading.value = false
  }
}

function openAdapterDialog(adapter) {
  Object.assign(adapterForm, {
    name: adapter.name,
    description: adapter.description,
    mode: adapter.dhcp === false ? 'static' : (adapter.ip ? 'static' : 'dhcp'),
    ip: adapter.ip || '',
    prefix: adapter.prefix || 24,
    gateway: adapter.gateway || '',
    dns: (adapter.dns || []).join(', '),
  })
  adapterDialogVisible.value = true
}

async function saveAdapter() {
  if (!adapterForm.name) return
  if (adapterForm.mode === 'static' && (!adapterForm.ip || !adapterForm.prefix)) {
    ElMessage.warning('静态模式需要填写 IP 和前缀')
    return
  }
  try {
    await ElMessageBox.confirm(
      '修改网卡 IP 可能导致当前网页连接中断，需要到服务器控制台恢复。确认提交吗？',
      '高风险网络变更',
      { type: 'warning', confirmButtonText: '确认提交', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  adapterSaving.value = true
  try {
    const payload = {
      name: adapterForm.name,
      mode: adapterForm.mode,
      ip: adapterForm.ip,
      prefix: Number(adapterForm.prefix),
      gateway: adapterForm.gateway,
      dns: adapterForm.dns.split(',').map((item) => item.trim()).filter(Boolean),
      confirm: true,
    }
    const res = await networkApi.configureAdapter(payload)
    ElMessage.success(res.data.message || '网卡配置已提交')
    adapterDialogVisible.value = false
    await loadNetwork()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '网卡配置失败')
  } finally {
    adapterSaving.value = false
  }
}

function openRouteDialog() {
  Object.assign(routeForm, {
    destination: '',
    gateway: networkData.value?.adapters?.[0]?.gateway || '',
    interface: networkData.value?.adapters?.[0]?.name || '',
    metric: 10,
  })
  routeDialogVisible.value = true
}

async function saveRoute() {
  if (!routeForm.destination) {
    ElMessage.warning('请填写目标网段')
    return
  }
  try {
    await ElMessageBox.confirm(
      '添加明细路由会立即修改主机路由表，请确认目标网段和下一跳。',
      '添加路由',
      { type: 'warning', confirmButtonText: '确认添加', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  routeSaving.value = true
  try {
    const res = await networkApi.addRoute({ ...routeForm, metric: Number(routeForm.metric), confirm: true })
    ElMessage.success(res.data.message || '路由已添加')
    routeDialogVisible.value = false
    await loadNetwork()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '添加路由失败')
  } finally {
    routeSaving.value = false
  }
}

async function removeRoute(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除路由 ${row.destination}${row.gateway ? ` → ${row.gateway}` : ''} 吗？`,
      '删除路由',
      { type: 'warning' },
    )
    await networkApi.deleteRoute({
      destination: row.destination, gateway: row.gateway,
      interface: row.interface, confirm: true,
    })
    ElMessage.success('路由已删除')
    await loadNetwork()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(error?.response?.data?.detail || error?.message || '删除路由失败')
    }
  }
}

async function toggleFirewall() {
  if (!networkData.value?.firewall) return
  const enable = !networkData.value.firewall.enabled
  try {
    if (!enable) {
      const { value } = await ElMessageBox.prompt(
        '关闭防火墙会显著增加主机暴露面。请输入 CONFIRM 确认关闭。',
        '高风险防火墙变更',
        { type: 'error', inputPattern: /^CONFIRM$/, inputErrorMessage: '请输入 CONFIRM' },
      )
      if (value !== 'CONFIRM') return
    } else {
      await ElMessageBox.confirm('确定重新启用防火墙吗？', '启用防火墙', { type: 'warning' })
    }
    const res = await networkApi.setFirewall({ action: enable ? 'enable' : 'disable', confirm: true })
    ElMessage.success(res.data.message || '防火墙状态已更新')
    await loadNetwork()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(error?.response?.data?.detail || error?.message || '切换防火墙失败')
    }
  }
}

async function performServiceAction(row, action) {
  const labels = { start: '启动', stop: '停止', restart: '重启', enable: '开机自启', disable: '取消自启' }
  try {
    await ElMessageBox.confirm(`确定${labels[action]}服务「${row.display_name || row.name}」吗？`, '服务操作', { type: 'warning' })
    networkActionBusy.value = `service:${row.name}:${action}`
    const res = await networkApi.serviceAction({ name: row.name, action, confirm: true })
    ElMessage.success(res.data.message || '操作完成')
    await reloadNetworkServices()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(error?.response?.data?.detail || error?.message || '服务操作失败')
    }
  } finally {
    networkActionBusy.value = ''
  }
}

async function performTaskAction(row, action) {
  const labels = { start: '启动', stop: '停止', enable: '启用', disable: '停用' }
  try {
    await ElMessageBox.confirm(`确定${labels[action]}计划任务「${row.name}」吗？`, '计划任务操作', { type: 'warning' })
    networkActionBusy.value = `task:${row.name}:${action}`
    const res = await networkApi.scheduledTaskAction({ name: row.name, action, confirm: true })
    ElMessage.success(res.data.message || '操作完成')
    await loadNetwork()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(error?.response?.data?.detail || error?.message || '计划任务操作失败')
    }
  } finally {
    networkActionBusy.value = ''
  }
}

async function loadVersionInfo() {
  try {
    const res = await settingsApi.version()
    versionInfo.value = res.data || null
  } catch {
    versionInfo.value = null
  }
}

async function testIntegration() {
  integrationTesting.value = true
  integrationTestResult.value = null
  try {
    const res = await settingsApi.integrationTest()
    integrationTestResult.value = res.data
    if (res.data?.ok) ElMessage.success(t('settings.integrationTestSuccess'))
    else ElMessage.warning(res.data?.error || t('settings.integrationTestFailed'))
  } catch (e) {
    integrationTestResult.value = { ok: false, error: e.message || t('settings.integrationTestFailed') }
    ElMessage.error(integrationTestResult.value.error)
  } finally {
    integrationTesting.value = false
  }
}

function runtimeSourceLabel(source) {
  return {
    environment: t('settings.runtimeSourceEnv'),
    settings: t('settings.runtimeSourceSettings'),
    default: t('settings.runtimeSourceDefault'),
    memory: t('settings.runtimeSourceMemory'),
  }[source] || t('settings.runtimeSourceMemory')
}

function onIntegrationDbTypeChange(type) {
  if (type === 'mysql') {
    form.integration_port = 3306
    if (!form.integration_charset) form.integration_charset = 'utf8mb4'
  } else if (type === 'postgresql') {
    form.integration_port = 5432
  }
  integrationTestResult.value = null
}

async function testRedis() {
  redisTesting.value = true
  redisTestResult.value = null
  try {
    const res = await settingsApi.redisTest()
    redisTestResult.value = res.data
    if (res.data?.ok) ElMessage.success(t('settings.redisTestSuccess'))
    else ElMessage.warning(res.data?.error || t('settings.redisTestFailed'))
  } catch (e) {
    redisTestResult.value = { ok: false, error: e.message || t('settings.redisTestFailed') }
    ElMessage.error(redisTestResult.value.error)
  } finally {
    redisTesting.value = false
  }
}

function updateRestartModeText(mode) {
  return {
    systemd: 'systemd 服务自动重启',
    start_sh: 'start.sh 守护进程自动重启',
    process: '应用进程自动重启',
    docker: 'Docker 容器（请在宿主机更新镜像）',
  }[mode] || mode || '-'
}

async function loadUpdateInfo() {
  updateLoading.value = true
  try {
    const res = await systemApi.updateInfo()
    updateInfo.value = res.data
    updateUrl.value = res.data.online_url || ''
    updateJob.value = res.data.job || null
    if (updateJob.value && !['success', 'failed', 'rolled_back'].includes(updateJob.value.status)) {
      beginUpdatePolling()
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '加载系统更新信息失败')
  } finally {
    updateLoading.value = false
  }
}

async function viewBackupFiles(row) {
  backupFilesVisible.value = true
  backupFilesLoading.value = true
  backupFilesData.value = null
  try {
    const res = await systemApi.backupFiles(row.job_id)
    backupFilesData.value = res.data
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '读取版本文件失败')
  } finally {
    backupFilesLoading.value = false
  }
}

async function deleteBackupVersion(row) {
  if (updateStarting.value || updateInfo.value?.active || deletingBackupId.value) return
  const version = row.display_version || row.version
  try {
    await ElMessageBox.confirm(
      `确定删除历史版本 v${version} 的备份文件吗？删除后无法恢复，也不会影响当前运行版本。`,
      '删除历史版本',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  deletingBackupId.value = row.job_id
  try {
    const res = await systemApi.deleteBackup(row.job_id)
    updateInfo.value = {
      ...(updateInfo.value || {}),
      backups: (updateInfo.value?.backups || []).filter((item) => item.job_id !== row.job_id),
    }
    if (backupFilesData.value?.job_id === row.job_id) {
      backupFilesVisible.value = false
      backupFilesData.value = null
    }
    ElMessage.success(res.data?.message || `历史版本 v${version} 已删除`)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '删除历史版本失败')
  } finally {
    deletingBackupId.value = ''
  }
}

async function rollbackToVersion(row) {
  if (updateStarting.value || updateInfo.value?.active) return
  try {
    await ElMessageBox.confirm(
      `确认回退到 v${row.display_version || row.version}？系统会先备份当前版本，然后替换程序并自动重启服务。`,
      '版本回退',
      { type: 'warning', confirmButtonText: '开始回退', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  rollbackStarting.value = true
  updateStarting.value = true
  try {
    const res = await systemApi.rollbackVersion(row.job_id)
    updateJob.value = res.data.job
    ElMessage.success('版本回退已开始，正在备份当前版本并重启服务')
    beginUpdatePolling()
  } catch (e) {
    updateStarting.value = false
    ElMessage.error(e?.response?.data?.detail || e.message || '启动版本回退失败')
  } finally {
    rollbackStarting.value = false
  }
}

async function saveUpdateUrl() {
  updateSaving.value = true
  try {
    const res = await systemApi.saveUpdateConfig(updateUrl.value)
    updateUrl.value = res.data.online_url || ''
    ElMessage.success('在线更新地址已保存')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '保存在线更新地址失败')
  } finally {
    updateSaving.value = false
  }
}

async function checkOnline() {
  onlineChecking.value = true
  onlineCheck.value = null
  try {
    const res = await systemApi.checkOnlineUpdate()
    onlineCheck.value = res.data
    if (res.data.update_available) {
      ElMessage.success(`发现新版本 v${res.data.display_version || res.data.version}`)
    } else {
      ElMessage.info('当前已经是最新版本')
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '检查在线更新失败')
  } finally {
    onlineChecking.value = false
  }
}

function beginUpdatePolling() {
  if (updatePollTimer) clearTimeout(updatePollTimer)
  updatePollCount = 0
  updateAuthFailures = 0
  updatePollTimer = setTimeout(pollUpdate, 800)
}

function applyUpdateStatus(nextJob) {
  if (!nextJob) return false
  updateJob.value = nextJob
  onlineChecking.value = false
  updateStarting.value = false
  const status = updateJob.value?.status
  if (['success', 'failed', 'rolled_back'].includes(status)) {
    if (status === 'success') {
      ElMessage.success('系统更新/版本回退成功，正在刷新页面')
      setTimeout(() => window.location.reload(), 1800)
    } else {
      ElMessage.error(updateJob.value?.message || '系统更新/版本回退未完成')
    }
    return true
  }
  return false
}

async function pollUpdate() {
  updatePollCount += 1
  const job = updateJob.value
  const jobId = job?.job_id || ''
  let resolved = false
  try {
    const res = await systemApi.updateStatus(jobId)
    resolved = applyUpdateStatus(res.data.job || updateJob.value)
  } catch (error) {
    const statusCode = Number(error?.response?.status || 0)
    if ((statusCode === 401 || statusCode === 403) && jobId && job?.status_token) {
      // 升级可能轮换登录密钥，服务重启后旧 token 会 401。
      // 更新任务自带独立随机状态令牌，可在未登录状态安全读取脱敏进度。
      updateAuthFailures += 1
      try {
        const publicRes = await systemApi.publicUpdateStatus(jobId, job.status_token)
        resolved = applyUpdateStatus(publicRes.data.job || job)
        if (resolved) return
      } catch {
        /* 新服务可能尚未起来，继续重试 */
      }
      if (updateAuthFailures >= 20 && !resolved) {
        ElMessage.warning('登录状态已失效，服务可能已完成重启；请重新登录查看版本')
        setTimeout(() => { window.location.href = '/login?updated=1' }, 1500)
        return
      }
    }
    if (!resolved) {
      updateJob.value = {
        ...(updateJob.value || {}),
        status: 'restarting',
        message: '服务正在重启，正在通过更新任务状态令牌自动重连...',
      }
    }
  }
  if (resolved) return
  if (updatePollCount < 900) {
    updatePollTimer = setTimeout(pollUpdate, 1000)
  } else {
    ElMessage.warning('更新状态轮询时间较长，请稍后重新登录或刷新页面查看版本')
  }
}

async function runOnlineUpdate() {
  if (!onlineCheck.value?.version) return
  try {
    await ElMessageBox.confirm(
      `确认在线更新到 v${onlineCheck.value.display_version || onlineCheck.value.version}？更新完成后服务会自动重启。`,
      '在线更新',
      { type: 'warning', confirmButtonText: '开始更新', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  updateStarting.value = true
  try {
    const res = await systemApi.startOnlineUpdate()
    updateJob.value = res.data.job
    ElMessage.success('更新已开始，正在自动备份并重启服务')
    beginUpdatePolling()
  } catch (e) {
    updateStarting.value = false
    ElMessage.error(e?.response?.data?.detail || e.message || '在线更新启动失败')
  }
}

function onUpdateFileChange(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  if (!file.name.toLowerCase().endsWith('.zip')) {
    ElMessage.error('请选择 .zip 更新包')
    return
  }
  if (file.size > 512 * 1024 * 1024) {
    ElMessage.error('更新包不能超过 512MB')
    return
  }
  updateFile.value = file
  updateUploadProgress.value = 0
  updateUploadLoaded.value = 0
  updateUploadTotal.value = 0
}

function onUpdateUploadProgress(event) {
  updateUploadLoaded.value = Number(event.loaded) || 0
  updateUploadTotal.value = Number(event.total) || 0
  if (updateUploadTotal.value > 0) {
    // 预留 1% 给服务端校验完成，避免上传刚到 100% 就误以为更新已完成
    updateUploadProgress.value = Math.min(
      99,
      Math.floor((updateUploadLoaded.value / updateUploadTotal.value) * 100),
    )
  }
}

async function uploadAndUpdate() {
  if (!updateFile.value) return
  try {
    await ElMessageBox.confirm(
      `确认上传并更新 ${updateFile.value.name}？系统会先备份当前程序，更新后自动重启服务。`,
      '上传更新',
      { type: 'warning', confirmButtonText: '上传并更新', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  updateStarting.value = true
  updateUploading.value = true
  updateUploadProgress.value = 0
  updateUploadLoaded.value = 0
  updateUploadTotal.value = 0
  try {
    const res = await systemApi.uploadUpdate(updateFile.value, {
      force: updateForce.value,
      onProgress: onUpdateUploadProgress,
    })
    updateUploadProgress.value = 100
    updateFile.value = null
    updateJob.value = res.data.job
    ElMessage.success('更新包校验通过，已开始自动更新')
    beginUpdatePolling()
  } catch (e) {
    updateStarting.value = false
    updateUploadProgress.value = 0
    updateUploadLoaded.value = 0
    updateUploadTotal.value = 0
    ElMessage.error(e?.response?.data?.detail || e.message || '上传更新失败')
  } finally {
    updateUploading.value = false
  }
}

async function loadWebCertificates() {
  try {
    const res = await websiteApi.certificates({})
    webCertificates.value = res.data?.items || []
  } catch {
    webCertificates.value = []
  }
}

async function loadWebGatewayStatus() {
  try {
    const res = await settingsApi.webAccessStatus()
    webGateway.value = res.data || webGateway.value
  } catch {
    /* 非关键状态，保留上次结果 */
  }
}

function pickWebSslFile(kind, event) {
  const file = event.target.files?.[0] || null
  event.target.value = ''
  webSslFiles[kind] = file
}

async function uploadWebSslCertificate() {
  if (!webSslFiles.cert || !webSslFiles.key) {
    ElMessage.warning(t('settings.webSslUploadRequired'))
    return
  }
  webSslUploading.value = true
  try {
    const data = new FormData()
    data.append('cert_file', webSslFiles.cert)
    data.append('key_file', webSslFiles.key)
    if (webSslFiles.chain) data.append('chain_file', webSslFiles.chain)
    const res = await settingsApi.uploadWebCertificate(data)
    form.web_ssl_certificate_id = res.data?.certificate?.id || 0
    webSslFiles.cert = null
    webSslFiles.key = null
    webSslFiles.chain = null
    await loadWebCertificates()
    ElMessage.success(t('settings.webSslUploaded'))
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || t('settings.webSslUploadFailed'))
  } finally {
    webSslUploading.value = false
  }
}

async function applyWebAccess() {
  if (!canEdit.value) return
  webGatewayApplying.value = true
  try {
    const payload = {
      web_http_enabled: form.web_http_enabled,
      web_http_port: Number(form.web_http_port) || 80,
      web_https_enabled: form.web_https_enabled,
      web_https_port: Number(form.web_https_port) || 443,
      web_https_redirect_http: form.web_https_redirect_http !== false,
      web_ssl_certificate_id: Number(form.web_ssl_certificate_id) || 0,
    }
    if (payload.web_https_enabled) payload.web_http_enabled = false
    const saved = await settingsApi.update(payload, copyrightUnlocked.value ? copyrightPrivilegeToken.value : '')
    Object.assign(form, saved.data?.settings || {})
    const res = await settingsApi.applyWebAccess()
    webGateway.value = res.data || webGateway.value
    ElMessage.success(t('settings.webGatewayApplied'))
  } catch (e) {
    const message = e?.response?.data?.detail || e.message || t('settings.webGatewayApplyFailed')
    webGateway.value = { ...webGateway.value, running: false, error: message }
    ElMessage.error(message)
  } finally {
    webGatewayApplying.value = false
  }
}

function onWebProtocolChange(value) {
  const port = Number(form.web_login_port) || 0
  if (value === 'https' && (port === 80 || port === 0)) {
    form.web_login_port = 443
  } else if (value === 'http' && (port === 443 || port === 0)) {
    form.web_login_port = 80
  }
}

function showWebCertTrustGuide() {
  const cert = webCertificates.value.find((item) => Number(item.id) === Number(form.web_ssl_certificate_id))
  const name = cert ? `${cert.name}（${cert.primary_host}）` : '系统自动签发的当前设备证书（有效期 10 年）'
  const lines = [
    `证书：${name}`,
    'HTTPS 登录不再需要手动上传证书；保存配置时会自动为当前设备签发 10 年有效证书。',
    '',
    '一、先下载证书',
    '进入「网站监控 → 证书管理 → 证书详情」，找到“设备自动证书”并下载证书或根链。',
    '自签名证书需要把签发它的根证书安装到客户端；仅安装叶子证书不一定生效。',
    '',
    '二、Windows',
    '双击 .cer/.crt → 安装证书 → 本地计算机 → 将证书放入“受信任的根证书颁发机构” → 完成，重启浏览器。',
    '',
    '三、macOS',
    '钥匙串访问 → 系统 → 导入证书 → 双击证书 → 信任 → 始终信任；Safari/Chrome 重启。',
    '',
    '四、Linux',
    '复制根证书到 /usr/local/share/ca-certificates/ 后执行 sudo update-ca-certificates；Firefox 需在证书管理器单独导入。',
    '',
    '五、iPhone/iPad',
    '通过 AirDrop/邮件安装描述文件，再到 设置 → 通用 → VPN与设备管理 安装，最后在“关于本机 → 证书信任设置”中启用完全信任。',
    '',
    '六、Android',
    '设置 → 安全 → 加密与凭据 → 安装证书 → CA 证书；不同品牌路径略有差异。',
    '',
    '注意：自动签发的设备证书是自签名证书。远端/公网 HTTPS 如果无法信任，需要安装内部 CA 根证书，或改用受信任 CA 证书。',
    '如证书 SAN 不包含访问地址（如 192.0.2.10），导入后仍会报名称不匹配。',
  ]
  ElMessageBox.alert(lines.join('\n'), t('settings.webSslTrustGuideTitle'), {
    confirmButtonText: t('common.confirm'),
    customClass: 'web-diagnose-message',
  })
}

async function diagnoseWebAccess() {
  webDiagnoseLoading.value = true
  try {
    const res = await settingsApi.diagnoseWebAccess()
    const data = res.data || {}
    const status = data.status || {}
    const certificate = data.certificate
    const listeners = (status.listeners || [])
      .map((item) => `${String(item.protocol || '').toUpperCase()} :${item.port}`)
      .join('、') || '无'
    const hints = data.hints || []
    const lines = [
      `网关状态：${status.running ? '运行中' : '未运行'}`,
      `监听端口：${listeners}`,
      status.error ? `错误：${status.error}` : '',
      certificate
        ? `HTTPS 证书：${certificate.name}（${certificate.primary_host}，${certificate.status_label}）`
        : 'HTTPS 证书：未选择/未找到',
      certificate?.valid_to ? `有效期至：${formatDateTime(certificate.valid_to)}` : '',
      certificate?.san?.length ? `SAN：${certificate.san.join(', ')}` : '',
      data.self_signed ? '证书类型：自签名（浏览器默认不信任）' : '',
      data.direct_fallback ? '应急直连：已保留内部端口' : '',
      '',
      ...hints.map((item) => `• ${item}`),
    ].filter(Boolean)
    await ElMessageBox.alert(lines.join('\n'), t('settings.webGatewayDiagnoseTitle'), {
      confirmButtonText: t('common.confirm'),
      customClass: 'web-diagnose-message',
    })
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || t('settings.webGatewayDiagnoseFailed'))
  } finally {
    webDiagnoseLoading.value = false
  }
}

async function loadAll() {
  loading.value = true
  try {
    const res = await settingsApi.get()
    Object.assign(form, res.data.settings)
    form.web_protocol = res.data.settings.web_protocol || (res.data.settings.web_https_enabled ? 'https' : 'http')
    form.web_login_port = Number(
      res.data.settings.web_login_port
      || (form.web_protocol === 'https' ? res.data.settings.web_https_port : res.data.settings.web_http_port)
      || (form.web_protocol === 'https' ? 443 : 80),
    )
    runtimeInfo.value = res.data.runtime || null
    loaded.value = true
    await loadVersionInfo()
    // 同步到前端全局配置
    await loadPublicSettings()
    await Promise.all([loadWebCertificates(), loadWebGatewayStatus()])
  } catch (e) {
    ElMessage.error(e.message || t('settings.loadFailed'))
  } finally {
    loading.value = false
  }
}

function openCopyrightPrivilege() {
  copyrightPrivilegeInput.value = ''
  copyrightPrivilegeVisible.value = true
}

async function verifyCopyrightPrivilege() {
  const token = copyrightPrivilegeInput.value.trim()
  if (!token) {
    ElMessage.warning('请粘贴品牌特权口令')
    return
  }
  copyrightVerifying.value = true
  try {
    const res = await licenseApi.verifyBrandingPrivilege(token)
    copyrightPrivilegeToken.value = token
    copyrightUnlockedUntil.value = Date.now() + Math.max(1, Number(res.data?.seconds_left) || 0) * 1000
    copyrightPrivilegeNow.value = Date.now()
    copyrightPrivilegeVisible.value = false
    ElMessage.success(`特权口令验证通过，版权信息已解锁约 ${copyrightUnlockText.value} 分钟`)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '特权口令验证失败')
  } finally {
    copyrightVerifying.value = false
  }
}

function lockCopyrightPrivilege() {
  copyrightPrivilegeToken.value = ''
  copyrightUnlockedUntil.value = 0
  copyrightPrivilegeNow.value = Date.now()
  ElMessage.info('版权信息已重新锁定')
}

async function saveAll() {
  if (!canEdit.value) {
    ElMessage.warning('系统关键配置仅超级管理员可修改')
    return
  }
  if (!form.system_name || !form.system_name.trim()) {
    ElMessage.warning(t('settings.systemNameRequired'))
    return
  }
  saving.value = true
  try {
    // 普通配置保存时剔除集群/负载均衡字段，避免被后端判定为集群配置；
    // 集群配置由「集群」页签的 saveClusterConfig 单独提交。
    const payload = Object.fromEntries(
      Object.entries(form).filter(([key]) => !CLUSTER_SETTING_KEYS.has(key)),
    )
    const res = await settingsApi.update(payload, copyrightUnlocked.value ? copyrightPrivilegeToken.value : '')
    Object.assign(form, res.data.settings)
    form.web_protocol = res.data.settings.web_protocol || form.web_protocol
    form.web_login_port = Number(
      res.data.settings.web_login_port
      || (form.web_protocol === 'https' ? res.data.settings.web_https_port : res.data.settings.web_http_port)
      || (form.web_protocol === 'https' ? 443 : 80),
    )
    if (res.data.gateway) webGateway.value = res.data.gateway
    runtimeInfo.value = res.data.runtime || runtimeInfo.value
    // 立即应用：标题、语言、时区、刷新间隔
    await loadPublicSettings()
    await loadVersionInfo()
    await loadWebGatewayStatus()
    ElMessage.success(t('settings.saved'))
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || e.message || t('settings.saveFailed'))
    try {
      const refreshed = await settingsApi.get()
      Object.assign(form, refreshed.data.settings)
      form.web_protocol = refreshed.data.settings.web_protocol || (refreshed.data.settings.web_https_enabled ? 'https' : 'http')
      form.web_login_port = Number(
        refreshed.data.settings.web_login_port
        || (form.web_protocol === 'https' ? refreshed.data.settings.web_https_port : refreshed.data.settings.web_http_port)
        || (form.web_protocol === 'https' ? 443 : 80),
      )
    } catch {
      /* 保留当前表单，等待用户刷新 */
    }
    await loadWebGatewayStatus()
  } finally {
    saving.value = false
  }
}

async function changePassword() {
  const { old_password, new_password, confirm } = passwordForm
  if (!passwordFormRef.value) return
  const valid = await passwordFormRef.value.validate().catch(() => false)
  if (!valid) return
  if (!old_password || !new_password) {
    ElMessage.warning(t('settings.passwordRequired'))
    return
  }
  if (new_password !== confirm) {
    ElMessage.warning(t('settings.passwordMismatch'))
    return
  }
  passwordSaving.value = true
  try {
    await authApi.changePassword({ old_password, new_password })
    ElMessage.success(t('settings.passwordChanged'))
    setTimeout(() => logout(), 800)
  } catch (e) {
    ElMessage.error(e.message || t('settings.changeFailed'))
  } finally {
    passwordSaving.value = false
  }
}

async function loadForwardStatus() {
  statusLoading.value = true
  try {
    const res = await settingsApi.forwardStatus()
    forwardStatus.value = res.data
  } catch (e) {
    ElMessage.error(e.message || t('settings.forwardStatusFailed'))
  } finally {
    statusLoading.value = false
  }
}

async function testForward() {
  testing.value = true
  try {
    const res = await settingsApi.forwardTest()
    if (res.data.ok) {
      ElMessage.success(t('settings.testSuccess', { type: res.data.type, ms: res.data.elapsed_ms }))
    } else {
      ElMessage.error(t('settings.testFailedDetail', { error: res.data.error || t('settings.unknownError') }))
    }
    await loadForwardStatus()
  } catch (e) {
    ElMessage.error(e.message || t('settings.testFailed'))
  } finally {
    testing.value = false
  }
}

async function openRecentLogs() {
  recentVisible.value = true
  await loadRecentLogs()
}

async function loadRecentLogs() {
  recentLoading.value = true
  try {
    const params = { lines: 200 }
    if (recentLevel.value) params.level = recentLevel.value
    if (recentKeyword.value) params.keyword = recentKeyword.value
    const res = await settingsApi.recentLogs(params)
    recentLines.value = res.data.lines || []
    recentFile.value = res.data.file || ''
  } catch (e) {
    ElMessage.error(e.message || t('settings.recentLogsFailed'))
  } finally {
    recentLoading.value = false
  }
}

async function loadBackups() {
  if (!canEdit.value) return
  backupLoading.value = true
  try {
    const res = await systemApi.backups()
    backups.value = res.data.items || []
    backupConfig.value = res.data.config || null
  } catch (e) {
    if (!e.message?.includes('403')) ElMessage.error(e.message || '加载备份列表失败')
  } finally {
    backupLoading.value = false
  }
}

async function createDbBackup() {
  backupCreating.value = true
  try {
    await systemApi.createBackup()
    ElMessage.success(t('settings.backupCreated'))
    await loadBackups()
  } catch (e) {
    ElMessage.error(e.message || t('settings.backupFailed'))
  } finally {
    backupCreating.value = false
  }
}

function downloadDbBackup(row) {
  downloadWithAuth(systemApi.downloadUrl(row.name))
}

async function removeDbBackup(row) {
  try {
    await ElMessageBox.confirm(
      t('settings.backupDeleteConfirm', { name: row.name }),
      t('common.confirm'),
      { type: 'warning' }
    )
    await systemApi.removeBackup(row.name)
    ElMessage.success(t('settings.backupDeleted'))
    await loadBackups()
  } catch {
    /* 取消 */
  }
}

async function loadSoundInfo() {
  try {
    const res = await settingsApi.getAlertSound()
    soundInfo.value = res.data
  } catch {
    soundInfo.value = null
  }
}

function pickLogo() {
  logoFileRef.value?.click()
}

async function onLogoFileChange(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  const allowed = ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.ico']
  const suffix = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
  if (!allowed.includes(suffix)) {
    ElMessage.error(t('settings.logoFormatError'))
    return
  }
  if (file.size > 2 * 1024 * 1024) {
    ElMessage.error(t('settings.logoTooLarge'))
    return
  }
  logoUploading.value = true
  try {
    const res = await settingsApi.uploadLogo(file)
    form.system_logo = res.data?.url || ''
    await loadPublicSettings()
    ElMessage.success(t('settings.logoUploaded'))
  } catch (e) {
    ElMessage.error(e.message || t('settings.logoUploadFailed'))
  } finally {
    logoUploading.value = false
  }
}

async function resetLogo() {
  try {
    await ElMessageBox.confirm(
      t('settings.logoResetConfirm'),
      t('common.confirm'),
      { type: 'warning' }
    )
    await settingsApi.deleteLogo()
    form.system_logo = ''
    await loadPublicSettings()
    ElMessage.success(t('settings.logoResetDone'))
  } catch {
    /* 取消 */
  }
}

function pickSoundFile(level = 'emergency') {
  soundEditLevel.value = level
  soundFileRef.value?.click()
}

async function onSoundFileChange(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  const allowed = ['.mp3', '.wav', '.ogg', '.m4a']
  const suffix = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
  if (!allowed.includes(suffix)) {
    ElMessage.error(t('settings.soundFormatError'))
    return
  }
  if (file.size > 2 * 1024 * 1024) {
    ElMessage.error(t('settings.soundTooLarge'))
    return
  }
  soundUploading.value = true
  const level = soundEditLevel.value
  try {
    await settingsApi.uploadAlertSound(file, level)
    await loadSoundInfo()
    await loadAlertSoundInfo()
    ElMessage.success(t('settings.soundUploaded'))
  } catch (e) {
    ElMessage.error(e.message || t('settings.soundUploadFailed'))
  } finally {
    soundUploading.value = false
  }
}

async function resetSound(level = 'emergency') {
  const name = t(SOUND_LEVELS.find((item) => item.value === level)?.labelKey || 'settings.alertSoundFile')
  try {
    await ElMessageBox.confirm(
      t('settings.soundResetLevelConfirm', { level: name }),
      t('common.confirm'),
      { type: 'warning' }
    )
    await settingsApi.deleteAlertSound(level)
    await loadSoundInfo()
    await loadAlertSoundInfo()
    ElMessage.success(t('settings.soundResetDone'))
  } catch {
    /* 取消 */
  }
}

async function resetAllSounds() {
  try {
    await ElMessageBox.confirm(
      t('settings.alertSoundResetAllConfirm'),
      t('common.confirm'),
      { type: 'warning' }
    )
    await settingsApi.resetAllAlertSounds()
    await loadSoundInfo()
    await loadAlertSoundInfo()
    ElMessage.success(t('settings.alertSoundResetAllDone'))
  } catch {
    /* 取消 */
  }
}

function previewBroadcast() {
  if (!alertSoundEnabled.value) {
    ElMessage.warning(t('settings.alertSoundDisabledTip'))
    return
  }
  const sampleAlerts = [
    { alert_level: 'info', device_name: '核心交换机-01', alert_type_text: '端口流量提示', value: 62, threshold: 50, operator: 'gt', metric_unit: '%' },
    { alert_level: 'warning', device_name: '核心交换机-01', alert_type_text: 'CPU 使用率过高', value: 86.5, threshold: 80, operator: 'gt', metric_unit: '%' },
    { alert_level: 'critical', device_name: '出口防火墙-01', alert_type_text: '温度过高', value: 78, threshold: 70, operator: 'gt', metric_unit: '℃' },
    { alert_level: 'emergency', device_name: '数据库服务器-01', alert_type_text: '电源故障', value: null, metric_unit: '' },
  ]
  const played = speakAlertBroadcast(sampleAlerts, {
    enabled: true,
    counts: form.alert_broadcast_counts,
    details: form.alert_broadcast_details,
    levels: broadcastLevels.value,
    maxItems: 0,
  }, true)
  if (!played) ElMessage.warning(t('settings.alertBroadcastUnsupported'))
}

async function testSound(level = 'critical') {
  await loadAlertSoundInfo()
  await playAlertSound(level, true)
}

// ==================== 系统时间 / NTP ====================
const timeStatus = ref(null)
const timeLoading = ref(false)
const timeSaving = ref(false)
const timeSyncing = ref(false)
const timeSetting = ref(false)
const timeResults = ref([])
const timeNow = ref('')
const timeServerInput = ref('')
const timeForm = reactive({ ntp_enabled: false, ntp_servers: [], timezone: '', datetime: '' })
let timeClockTimer = null

function pad2(value) {
  return String(value).padStart(2, '0')
}

function updateTimeNow() {
  const now = new Date()
  timeNow.value = `${now.getFullYear()}-${pad2(now.getMonth() + 1)}-${pad2(now.getDate())} ${pad2(now.getHours())}:${pad2(now.getMinutes())}:${pad2(now.getSeconds())}`
}

function applyTimeStatus(status) {
  if (!status) return
  timeStatus.value = status
  timeForm.ntp_enabled = !!status.ntp_enabled
  timeForm.ntp_servers = Array.isArray(status.ntp_servers) ? [...status.ntp_servers] : []
  timeForm.timezone = status.timezone_iana || status.timezone || timeForm.timezone
}

async function loadTimeStatus() {
  timeLoading.value = true
  try {
    const res = await apiRequest.get('/system/time')
    applyTimeStatus(res.data)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '获取系统时间状态失败')
  } finally {
    timeLoading.value = false
  }
}

function addNtpServer() {
  const value = String(timeServerInput.value || '').trim()
  if (!value) return
  if (!/^[A-Za-z0-9.\-]+$/.test(value)) {
    ElMessage.warning('NTP 服务器仅支持域名或 IP 地址')
    return
  }
  if (timeForm.ntp_servers.includes(value)) {
    ElMessage.info('该 NTP 服务器已在列表中')
    return
  }
  if (timeForm.ntp_servers.length >= 8) {
    ElMessage.warning('最多配置 8 个 NTP 服务器')
    return
  }
  timeForm.ntp_servers.push(value)
  timeServerInput.value = ''
}

function removeNtpServer(server) {
  timeForm.ntp_servers = timeForm.ntp_servers.filter((item) => item !== server)
}

async function applyTimeSettings() {
  if (!canEdit.value) {
    ElMessage.warning('系统时间设置仅超级管理员可修改')
    return
  }
  if (timeForm.ntp_enabled && !timeForm.ntp_servers.length) {
    ElMessage.warning('启用 NTP 自动同步时，至少需要配置一个 NTP 服务器')
    return
  }
  timeSaving.value = true
  try {
    const payload = {
      ntp_enabled: timeForm.ntp_enabled,
      ntp_servers: timeForm.ntp_servers,
    }
    // Windows 的时区标识（如 China Standard Time）不是 IANA 名称，仅在支持网页设置时区时提交
    if (timeStatus.value?.capabilities?.set_timezone && timeForm.timezone) {
      payload.timezone = timeForm.timezone
    }
    const res = await apiRequest.post('/system/time/configure', payload)
    const data = res.data || {}
    applyTimeStatus(data.status)
    if (Array.isArray(data.results)) timeResults.value = data.results
    if (data.ok) ElMessage.success(data.message || 'NTP 设置已保存并应用')
    else ElMessage.warning(data.message || '设置已保存，但系统命令未全部成功')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '保存 NTP 设置失败')
  } finally {
    timeSaving.value = false
  }
}

async function syncTimeNow() {
  if (!timeStatus.value?.ntp_enabled) {
    ElMessage.warning('请先启用 NTP 自动同步')
    return
  }
  timeSyncing.value = true
  try {
    const res = await apiRequest.post('/system/time/sync')
    const data = res.data || {}
    applyTimeStatus(data.status)
    if (Array.isArray(data.results)) timeResults.value = data.results
    if (data.ok) ElMessage.success(data.message || '时间同步已触发')
    else ElMessage.warning(data.message || '时间同步失败')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '时间同步失败')
  } finally {
    timeSyncing.value = false
  }
}

async function setTimeManually() {
  if (!canEdit.value) {
    ElMessage.warning('系统时间设置仅超级管理员可修改')
    return
  }
  if (!timeForm.datetime) {
    ElMessage.warning('请选择要设置的日期时间')
    return
  }
  if (timeForm.ntp_enabled) {
    ElMessage.warning('请先关闭 NTP 自动同步，再手动设置系统时间')
    return
  }
  const text = String(timeForm.datetime).replace('T', ' ')
  try {
    await ElMessageBox.confirm(
      `确定将系统时间设置为 ${text} 吗？设置后日志与采集时间将以新时间为准。`,
      '手动设置系统时间',
      { type: 'warning', confirmButtonText: '确定设置', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  timeSetting.value = true
  try {
    const payload = { datetime: timeForm.datetime }
    if (timeStatus.value?.capabilities?.set_timezone && timeForm.timezone) {
      payload.timezone = timeForm.timezone
    }
    const res = await apiRequest.post('/system/time/set', payload)
    const data = res.data || {}
    applyTimeStatus(data.status)
    if (Array.isArray(data.results)) timeResults.value = data.results
    if (data.ok) ElMessage.success(data.message || '系统时间已设置')
    else ElMessage.error(data.message || '设置系统时间失败')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '设置系统时间失败')
  } finally {
    timeSetting.value = false
  }
}

// ==================== 二次身份验证（TOTP，仅当前账号） ====================
const totpStatus = ref(null)
const totpSetup = ref(null)
const totpCode = ref('')
const totpSetupLoading = ref(false)
const totpEnabling = ref(false)
const totpDisabling = ref(false)
const totpDisableForm = reactive({ password: '', code: '' })

async function loadTotpStatus() {
  try {
    const res = await apiRequest.get('/auth/2fa/status')
    totpStatus.value = res.data
    if (!res.data?.enabled) {
      // 未启用时清空停用表单，避免残留输入
      totpDisableForm.password = ''
      totpDisableForm.code = ''
    }
  } catch {
    totpStatus.value = null
  }
}

async function startTotpSetup() {
  totpSetupLoading.value = true
  try {
    const res = await apiRequest.post('/auth/2fa/setup')
    totpSetup.value = res.data
    totpStatus.value = res.data?.status || totpStatus.value
    totpCode.value = ''
    ElMessage.success('密钥已生成，请用身份验证器扫码')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '生成二次身份验证密钥失败')
  } finally {
    totpSetupLoading.value = false
  }
}

async function enableTotp() {
  const code = String(totpCode.value || '').replace(/\s/g, '')
  if (!/^\d{6}$/.test(code)) {
    ElMessage.warning('请输入身份验证器中的 6 位动态验证码')
    return
  }
  totpEnabling.value = true
  try {
    const res = await apiRequest.post('/auth/2fa/enable', { code })
    totpStatus.value = res.data?.status || { ...(totpStatus.value || {}), enabled: true }
    totpSetup.value = null
    totpCode.value = ''
    ElMessage.success(res.data?.message || '二次身份验证已启用')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '启用二次身份验证失败')
  } finally {
    totpEnabling.value = false
  }
}

async function disableTotp() {
  const code = String(totpDisableForm.code || '').replace(/\s/g, '')
  if (!/^\d{6}$/.test(code)) {
    ElMessage.warning('请输入身份验证器中的 6 位动态验证码')
    return
  }
  if (!totpDisableForm.password) {
    ElMessage.warning('请输入当前登录密码')
    return
  }
  try {
    await ElMessageBox.confirm(
      '停用后登录将不再校验动态验证码，确定停用二次身份验证吗？',
      '停用二次身份验证',
      { type: 'warning', confirmButtonText: '确定停用', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  totpDisabling.value = true
  try {
    const res = await apiRequest.post('/auth/2fa/disable', {
      code,
      password: totpDisableForm.password,
    })
    totpStatus.value = res.data?.status || { ...(totpStatus.value || {}), enabled: false }
    totpDisableForm.password = ''
    totpDisableForm.code = ''
    ElMessage.success(res.data?.message || '二次身份验证已停用')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '停用二次身份验证失败')
  } finally {
    totpDisabling.value = false
  }
}

async function copyTotpText(text) {
  if (!text) return
  try {
    await navigator.clipboard.writeText(String(text))
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败，请手动选择文本复制')
  }
}

watch(activeTab, (tab) => {
  if (tab === 'status') loadHostStatus()
  if (tab === 'startup') loadStartup()
  if (tab === 'time' && !timeStatus.value && !timeLoading.value) loadTimeStatus()
})

async function loadStartup() {
  startupLoading.value = true
  try {
    const res = await settingsApi.startupStatus()
    startupInfo.value = res.data
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '加载开机自启状态失败')
  } finally {
    startupLoading.value = false
  }
}

async function toggleStartup(enabled) {
  if (!canEdit.value) {
    ElMessage.warning('系统关键配置仅超级管理员可修改')
    return
  }
  startupSaving.value = true
  try {
    const res = await settingsApi.updateStartup(!!enabled)
    startupInfo.value = res.data
    ElMessage.success(enabled ? '已启用开机自启，下次开机生效' : '已停用开机自启')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || '设置开机自启失败')
    await loadStartup()
  } finally {
    startupSaving.value = false
  }
}

onMounted(async () => {
  updateTimeNow()
  timeClockTimer = setInterval(updateTimeNow, 1000)
  copyrightPrivilegeTimer = setInterval(() => { copyrightPrivilegeNow.value = Date.now() }, 30000)
  await loadAll()
  await loadSettingsUsers()
  await loadForwardStatus()
  await loadHealth()
  await loadHostStatus()
  await loadSecurityInfo()
  await loadBackups()
  await loadSoundInfo()
  await loadCluster()
  if (activeTab.value === 'startup') await loadStartup()
  if (activeTab.value === 'time') await loadTimeStatus()
  if (activeTab.value === 'network') await loadNetwork()
  if (activeTab.value === 'update') await loadUpdateInfo()
})

onBeforeUnmount(() => {
  if (updatePollTimer) clearTimeout(updatePollTimer)
  if (timeClockTimer) clearInterval(timeClockTimer)
  if (copyrightPrivilegeTimer) clearInterval(copyrightPrivilegeTimer)
})
</script>

<style scoped>
.settings-readonly-alert { margin-bottom: 14px; }
.realert-setting { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.realert-setting .form-tip { flex-basis: 100%; margin: 2px 0 0; }

.runtime-connection-alert {
  margin-bottom: 14px;
}

.runtime-connection-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 6px;
}

.runtime-connection-item {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
}

.runtime-connection-label {
  min-width: 48px;
  color: #6b7c8a;
}

.runtime-connection-item b {
  color: #1f2d3d;
  font-weight: 600;
}

.runtime-connection-note {
  color: #6b7c8a;
  font-size: 11px;
}

.runtime-connection-error {
  color: #b91c1c;
}

.runtime-autofill-alert {
  margin-bottom: 14px;
}

.connection-result {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  width: 100%;
  margin-top: 8px;
  padding: 8px 10px;
  border: 1px solid #f3d6d6;
  border-radius: 7px;
  color: #b42318;
  background: #fff6f5;
  font-size: 11px;
}

.connection-result.ok {
  border-color: #cceadd;
  color: #087443;
  background: #f4fcf8;
}

.connection-result span {
  color: #7d8f9c;
  font-family: Consolas, monospace;
  font-size: 10px;
}
.settings-view {
  height: 100%;
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

.settings-form {
  max-width: 860px;
  padding-top: 8px;
}

.unit {
  margin-left: 8px;
  color: #606266;
}

.sound-file-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  width: 100%;
}

.sound-level-list {
  width: 100%;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  overflow: hidden;
}

.sound-level-row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 46px;
  padding: 7px 10px;
  border-bottom: 1px solid #eef2f7;
}

.sound-level-row:last-child {
  border-bottom: 0;
}

.sound-level-name {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 118px;
  flex-shrink: 0;
}

.sound-level-name b {
  color: #334155;
  font-size: 13px;
}

.sound-level-name small {
  color: #94a3b8;
  font-size: 10px;
}

.sound-level-tag {
  min-width: 118px;
  max-width: 230px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sound-level-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
  flex-wrap: wrap;
}

.sound-level-tip {
  margin-top: 5px;
  color: #9aacba;
  font-size: 10px;
  line-height: 1.5;
}

.sound-reset-all {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 9px;
  flex-wrap: wrap;
}

.broadcast-settings {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fbfdff;
}

.broadcast-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.broadcast-desc {
  color: #64748b;
  font-size: 12px;
}

.broadcast-options {
  display: flex;
  align-items: center;
  gap: 18px;
  margin-top: 10px;
  flex-wrap: wrap;
}

.broadcast-level-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
  flex-wrap: wrap;
}

.broadcast-label {
  color: #475569;
  font-size: 12px;
  white-space: nowrap;
}

.logo-setting {
  display: flex;
  align-items: flex-start;
  gap: 14px;
}

.logo-preview {
  width: 64px;
  height: 64px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border: 1px solid #dcdfe6;
  border-radius: 12px;
  color: #1890ff;
  background: #f8fafc;
}

.logo-preview img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.logo-setting-actions {
  flex: 1;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.logo-setting-actions .el-button {
  margin-left: 0;
}

.version-info-card {
  width: 100%;
  max-width: 640px;
  padding: 12px 14px;
  border: 1px solid #e4eef7;
  border-radius: 9px;
  background: linear-gradient(135deg, #f7fbff, #fbfdff);
}

.version-info-main {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.version-info-main strong {
  color: #1f3b52;
  font-family: Consolas, monospace;
  font-size: 20px;
  line-height: 1.2;
  overflow-wrap: anywhere;
}

.version-info-meta {
  margin-top: 4px;
  color: #8aa0b1;
  font-family: Consolas, monospace;
  font-size: 10px;
  line-height: 1.5;
}

.version-info-meta b {
  color: #4c7087;
  font-weight: 500;
}

.form-tip {
  width: 100%;
  font-size: 12px;
  color: #909399;
  line-height: 1.6;
  margin-top: 4px;}

.hint-box {
  padding: 10px 14px;
  background: #f5f7fa;
  border-radius: 8px;
  font-size: 12px;
  color: #606266;
  line-height: 1.8;
}

.filters {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.muted {
  color: #a8abb2;
  font-size: 12px;
}

.warn-text {
  color: #e6a23c;
}

.warn-tip {
  color: #e6a23c;
  line-height: 1.6;
  margin-top: 6px;
}

.backup-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.import-changed {
  margin-top: 12px;
  font-size: 13px;
  color: #606266;
}

.host-status-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.host-status-head strong { display: block; color: #24425b; font-size: 14px; }
.host-status-head span { display: block; margin-top: 4px; color: #8ca0af; font-size: 10px; }
.host-status-error { margin-bottom: 12px; }
.host-status-wrap { display: flex; flex-direction: column; gap: 12px; }
.host-metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.host-metric-card { padding: 12px 14px; border: 1px solid #e4eef6; border-radius: 9px; background: #fbfdff; min-width: 0; }
.host-metric-title { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin-bottom: 7px; }
.host-metric-title span { color: #7d94a5; font-size: 10px; }
.host-metric-title b { color: #24425b; font-family: Consolas, monospace; font-size: 20px; }
.host-metric-title .host-uptime { font-family: inherit; font-size: 16px; }
.host-metric-foot { margin-top: 6px; color: #91a4b4; font-size: 9px; line-height: 1.5; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.host-metric-foot.host-os { color: #45657b; font-size: 10px; }
.host-status-two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.host-panel { border: 1px solid #e4eef6; border-radius: 9px; background: #fbfdff; overflow: hidden; }
.host-panel-head { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; padding: 10px 13px; border-bottom: 1px solid #eef4f8; }
.host-panel-head strong { color: #24425b; font-size: 12px; }
.host-panel-head span { font-size: 9px; }
.host-service-list { padding: 4px 13px; }
.host-service-item { display: flex; align-items: center; gap: 9px; padding: 8px 0; border-bottom: 1px solid #f1f6fa; }
.host-service-item:last-child { border-bottom: 0; }
.host-service-dot { width: 7px; height: 7px; flex-shrink: 0; border-radius: 50%; background: #94a3b8; }
.host-service-dot.is-running { background: #10b981; box-shadow: 0 0 0 3px #d1fae5; }
.host-service-dot.is-error, .host-service-dot.is-stopped { background: #ef4444; box-shadow: 0 0 0 3px #fee2e2; }
.host-service-main { flex: 1; min-width: 0; }
.host-service-main strong { display: block; color: #38566b; font-size: 11px; }
.host-service-main small { display: block; margin-top: 2px; color: #94a8b7; font-size: 9px; }
.host-info-list { display: grid; grid-template-columns: 1fr 1fr; gap: 0 14px; padding: 9px 13px; }
.host-info-list > div { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; padding: 6px 0; border-bottom: 1px solid #f1f6fa; min-width: 0; }
.host-info-list span { flex-shrink: 0; color: #91a4b4; font-size: 9px; }
.host-info-list b { color: #45657b; font-size: 10px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.host-status-table :deep(.el-table) { font-size: 10px; }
.host-nic-name { display: block; color: #38566b; font-size: 10px; }
.host-nic-mac { display: block; margin-top: 2px; color: #9aacba; font-family: Consolas, monospace; font-size: 9px; }
.host-ip { display: block; color: #45657b; font-family: Consolas, monospace; font-size: 9px; line-height: 1.5; }
@media (max-width: 1100px) {
  .host-metric-grid { grid-template-columns: repeat(2, 1fr); }
  .host-status-two-col { grid-template-columns: 1fr; }
}
@media (max-width: 700px) {
  .host-metric-grid { grid-template-columns: 1fr; }
  .host-info-list { grid-template-columns: 1fr; }
  .host-status-head { flex-direction: column; }
}

.forward-status {
  max-width: 1100px;
}

.log-lines {
  margin: 0;
  padding: 12px;
  background: #0f172a;
  color: #cbd5e1;
  border-radius: 8px;
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
  line-height: 1.6;
  max-height: 60vh;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.password-requirements {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 18px;
  align-items: center;
}

.cluster-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.cluster-overview {
  margin-top: 2px;
}

.cluster-stat {
  padding: 12px 16px;
  border: 1px solid #e5edf4;
  border-radius: 7px;
  background: #f8fbfe;
}

.cluster-stat span {
  display: block;
  color: #8b9bab;
  font-size: 11px;
}

.cluster-stat b {
  display: block;
  margin-top: 4px;
  color: #214667;
  font-size: 18px;
}

.mono {
  font-family: Consolas, monospace;
  font-size: 12px !important;
}

.cluster-card {
  border: 1px solid #e5edf4;
}

.settings-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: #263e52;
  font-size: 13px;
  font-weight: 700;
}

.settings-card-sub {
  color: #8b9bab;
  font-size: 10px;
  font-weight: 400;
}

.cluster-form {
  max-width: 780px;
}

.form-help {
  margin-left: 9px;
  color: #8b9bab;
  font-size: 11px;
}

.node-name {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #29445c;
  font-weight: 600;
}

.node-address {
  margin-top: 2px;
  color: #8b9bab;
  font-family: Consolas, monospace;
  font-size: 10px;
}

.node-limit {
  margin-left: 4px;
  color: #8b9bab;
  font-size: 10px;
}

.lb-preview {
  margin-top: 8px;
  padding: 11px 13px;
  border: 1px solid #e5edf4;
  border-radius: 7px;
  background: #f8fbfe;
}

.lb-preview-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #60788c;
  font-size: 11px;
}

.lb-preview pre {
  max-height: 280px;
  overflow: auto;
  margin: 8px 0;
  padding: 11px;
  border-radius: 5px;
  color: #c9e7ff;
  background: #122433;
  font-family: Consolas, monospace;
  font-size: 11px;
  line-height: 1.55;
}

.network-panel {
  display: flex;
  flex-direction: column;
  gap: 13px;
}

.network-stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.network-stat {
  padding: 12px 15px;
  border: 1px solid #e5edf4;
  border-radius: 7px;
  background: #f8fbfe;
}

.network-stat span {
  display: block;
  color: #8b9bab;
  font-size: 11px;
}

.network-stat b {
  display: block;
  margin-top: 4px;
  overflow: hidden;
  color: #214667;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.network-stat b.ok { color: #1b9b6a; }
.network-stat b.danger { color: #d9485f; }

.network-card {
  border: 1px solid #e5edf4;
}

.network-note {
  margin-top: 8px;
}

.network-search {
  display: flex;
  gap: 7px;
  align-items: center;
}

.network-search .el-input {
  width: 220px;
}

.firewall-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}

.firewall-row strong {
  color: #29445c;
  font-size: 13px;
}

.firewall-row p {
  margin: 5px 0 0;
  color: #8b9bab;
  font-size: 11px;
}

.adapter-alert {
  margin-bottom: 14px;
}

.adapter-form {
  max-width: 100%;
}

.update-panel {
  max-width: 1050px;
}

.copyright-preview {
  margin-left: 14px;
  font-size: 13px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.update-current {
  margin-top: 16px;
}

.update-config-form {
  margin-top: 16px;
}

.update-hint {
  margin-top: 5px;
  color: #8b9bab;
  font-size: 12px;
  line-height: 1.5;
}

.version-history-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 10px;
}

.version-history-head strong {
  display: block;
  color: #2c4054;
  font-size: 13px;
}

.version-history-head .update-hint {
  display: block;
  margin-top: 3px;
}

.version-history-table {
  width: 100%;
}

.version-tag {
  margin-left: 7px;
}

.backup-files-meta {
  margin-bottom: 12px;
}

.update-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.update-check-result {
  margin-top: 12px;
}

.update-file-input {
  display: none;
}

.update-upload-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.update-file-name {
  color: #64748b;
  font-size: 13px;
  overflow-wrap: anywhere;
}

.update-upload-progress {
  margin-top: 14px;
  padding: 12px 14px;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  background: #f8fbff;
}

.update-upload-progress-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 8px;
  color: #1f4f82;
  font-size: 13px;
  font-weight: 600;
}

.update-upload-progress-head span:last-child {
  color: #64748b;
  font-weight: 400;
  font-family: Consolas, monospace;
  font-size: 11px;
}

.update-job {
  margin-top: 16px;
}

.update-job-alert {
  margin-top: 20px;
}

.update-error {
  margin-top: 10px;
  color: #b91c1c;
  font-size: 12px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.web-access-port-label {
  margin: 0 8px 0 18px;
  color: #6f8798;
  font-size: 12px;
}
.web-ssl-upload-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  margin-bottom: 5px;
}
.web-ssl-upload-row .file-name {
  max-width: 280px;
  overflow: hidden;
  color: #8a9dad;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.web-gateway-status {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  width: 100%;
}
.web-gateway-status .el-alert {
  flex: 1;
  min-width: 260px;
  padding: 8px 12px;
}

/* Web 服务、中间件与端口状态 */
.web-health-panel { padding-bottom: 10px; }
.web-health-panel .host-panel-head { align-items: center; }
.web-health-panel .host-panel-head > div { display: flex; flex-direction: column; gap: 2px; }
.web-health-live { display: inline-flex; align-items: center; gap: 6px; padding: 4px 8px; border-radius: 20px; font-size: 10px; font-weight: 600; }
.web-health-live i { width: 6px; height: 6px; border-radius: 50%; }
.web-health-live.ok { color: #047857; background: #ecfdf5; }
.web-health-live.ok i { background: #10b981; box-shadow: 0 0 0 3px #d1fae5; }
.web-health-live.bad { color: #b91c1c; background: #fef2f2; }
.web-health-live.bad i { background: #ef4444; box-shadow: 0 0 0 3px #fee2e2; }
.web-health-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; padding: 10px 13px 0; }
.web-health-card { display: flex; align-items: flex-start; gap: 10px; min-width: 0; padding: 12px; border: 1px solid #e7eff5; border-radius: 9px; background: #fbfdff; }
.web-health-card.is-ok { border-left: 3px solid #10b981; }
.web-health-card.is-warn { border-left: 3px solid #f59e0b; }
.web-health-card.is-bad { border-left: 3px solid #ef4444; background: #fffafa; }
.web-health-icon { display: grid; place-items: center; width: 30px; height: 30px; flex: 0 0 30px; border-radius: 8px; color: #167e9b; background: #e7f7fb; }
.web-health-main { display: flex; flex-direction: column; min-width: 0; gap: 4px; }
.web-health-title { display: flex; align-items: center; gap: 7px; }
.web-health-title strong { color: #24425b; font-size: 11px; white-space: nowrap; }
.web-health-main > span { overflow: hidden; color: #748b9d; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.web-health-chips { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 2px; }
.web-listener-chip { display: inline-flex; align-items: center; padding: 2px 5px; border-radius: 4px; color: #53798c; background: #f0f7fa; font-family: Consolas, monospace; font-size: 8px; }
.web-listener-chip.is-muted { color: #9aa9b5; background: #f5f7f9; }
.web-health-url { padding: 8px 13px 0; color: #91a4b4; font-size: 9px; }
.host-port-actions { display: flex; align-items: center; gap: 8px; }
.host-port-panel .host-panel-head { align-items: center; }
.host-port-panel .host-panel-head > div:first-child { display: flex; flex-direction: column; gap: 2px; }
.host-port-number { color: #1e5f86; font-family: Consolas, monospace; font-size: 12px; }
.host-port-address { color: #58778b; font-family: Consolas, monospace; font-size: 9px; }
.port-bind-all { margin-left: 5px; }
.host-port-pid { display: block; color: #9aabb8; font-size: 8px; }
.host-port-empty { padding: 20px; color: #95a8b7; font-size: 11px; text-align: center; }
.host-port-note { padding: 7px 13px 9px; color: #91a4b4; font-size: 9px; }
.port-psutil-alert { margin: 8px 13px 0; }
@media (max-width: 1100px) {
  .web-health-grid { grid-template-columns: 1fr; }
  .web-health-card { align-items: center; }
}
@media (max-width: 760px) {
  .host-port-actions { flex-direction: column; align-items: flex-end; }
  .web-health-live { display: none; }
}

/* ==================== 时间设置 ==================== */
.time-tab { display: flex; flex-direction: column; gap: 12px; }
.time-hero {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr);
  gap: 18px;
  padding: 16px 18px;
  border: 1px solid #e2eef6;
  border-radius: 10px;
  background: linear-gradient(135deg, #f6fbfe, #fbfdff);
}
.time-hero-main { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.time-hero-label { color: #6c8ba0; font-size: 11px; letter-spacing: 1px; }
.time-hero-clock {
  color: #17596f;
  font-family: Consolas, 'SFMono-Regular', monospace;
  font-size: 26px;
  font-weight: 600;
  letter-spacing: 1px;
  font-variant-numeric: tabular-nums;
}
.time-hero-sub { color: #8aa4b5; font-family: Consolas, monospace; font-size: 11px; }
.time-hero-side {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px 14px;
  min-width: 0;
}
.time-meta { display: flex; flex-direction: column; min-width: 0; }
.time-meta span { color: #93a9b8; font-size: 10px; }
.time-meta b { overflow: hidden; color: #33536a; font-size: 12px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.time-refresh { position: absolute; top: 12px; right: 14px; }
.time-stat-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.time-stat-card {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 11px 13px;
  border: 1px solid #e7eff5;
  border-left: 3px solid #c9d9e4;
  border-radius: 8px;
  background: #fbfdff;
}
.time-stat-card.is-ok { border-left-color: #10b981; }
.time-stat-card.is-warn { border-left-color: #f59e0b; }
.time-stat-card.is-unknown { border-left-color: #94a3b8; }
.time-stat-title { color: #7b93a4; font-size: 10px; }
.time-stat-card b { color: #24425b; font-size: 14px; }
.time-stat-sub { color: #8aa2b2; font-size: 10px; line-height: 1.5; }
.time-warning { margin: 0; }
.ntp-server-list { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.ntp-server-tag { font-family: Consolas, monospace; }
.ntp-server-add { display: flex; align-items: center; gap: 8px; }
.time-results { margin-top: 4px; }
.time-result-item { padding: 8px 0; border-bottom: 1px dashed #e6eef4; }
.time-result-item:last-child { border-bottom: 0; }
.time-result-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.time-result-head code { color: #456275; font-family: Consolas, monospace; font-size: 10px; word-break: break-all; }
.time-result-item pre {
  max-height: 180px;
  margin: 0;
  padding: 7px 9px;
  overflow: auto;
  border-radius: 6px;
  color: #4a6273;
  background: #f6fafc;
  font-family: Consolas, monospace;
  font-size: 10px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-all;
}

/* ==================== 二次身份验证 ==================== */
.totp-policy-card {
  padding: 14px 16px;
  border: 1px solid #e2eef6;
  border-radius: 10px;
  background: #fbfdff;
}
.totp-policy-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 14px; }
.totp-policy-head strong { display: block; color: #24425b; font-size: 14px; }
.totp-policy-head span { display: block; margin-top: 4px; color: #7d95a6; font-size: 11px; line-height: 1.6; }
.totp-card {
  padding: 14px 16px;
  border: 1px solid #e2eef6;
  border-radius: 10px;
  background: #fbfdff;
}
.totp-card-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.totp-card-title { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.totp-card-title strong { display: inline-flex; align-items: center; gap: 6px; color: #24425b; font-size: 13px; }
.totp-card-title span { color: #7d95a6; font-size: 11px; line-height: 1.6; }
.totp-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-top: 10px; }
.totp-setup { margin-top: 12px; }
.totp-setup-grid { display: grid; grid-template-columns: 190px minmax(0, 1fr); gap: 16px; align-items: start; }
.totp-qr { display: flex; flex-direction: column; align-items: center; gap: 6px; }
.totp-qr img { width: 170px; height: 170px; padding: 6px; border: 1px solid #e2eef6; border-radius: 8px; background: #fff; }
.totp-qr .muted { color: #93a9b8; font-size: 10px; }
.totp-setup-form { max-width: 640px; }
.totp-secret {
  padding: 3px 7px;
  margin-right: 8px;
  border-radius: 5px;
  color: #17596f;
  background: #eef7fb;
  font-family: Consolas, monospace;
  font-size: 12px;
  letter-spacing: 1px;
}
.totp-disable-form { margin-top: 10px; }
@media (max-width: 900px) {
  .time-hero { grid-template-columns: 1fr; }
  .time-hero-side { grid-template-columns: 1fr; }
  .time-stat-grid { grid-template-columns: 1fr; }
  .totp-setup-grid { grid-template-columns: 1fr; }
  .totp-qr { align-items: flex-start; }
}


.startup-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 980px;
  padding: 8px 4px 12px;
}
.startup-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #edf2f6;
}
.startup-head strong {
  display: block;
  color: #1e293b;
  font-size: 15px;
}
.startup-head span {
  display: block;
  margin-top: 4px;
  color: #7c8e9e;
  font-size: 11px;
}
.startup-status-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.startup-status-grid > div {
  padding: 12px 14px;
  border: 1px solid #e8eff5;
  border-radius: 8px;
  background: #fbfdff;
}
.startup-status-grid span {
  display: block;
  color: #8496a5;
  font-size: 10px;
}
.startup-status-grid b {
  display: block;
  margin-top: 4px;
  color: #334e63;
  font-family: Consolas, monospace;
  font-size: 12px;
}
.startup-status-grid b.ok { color: #0b8f68; }
.startup-command {
  padding: 10px 12px;
  border: 1px solid #e8eff5;
  border-radius: 8px;
  background: #fbfdff;
}
.startup-command span { display: block; color: #8496a5; font-size: 10px; }
.startup-command code { display: block; margin-top: 4px; color: #48697f; font-size: 10px; overflow-wrap: anywhere; }
.startup-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px;
  border: 1px solid #e1eaf2;
  border-radius: 9px;
  background: linear-gradient(135deg, #f8fbff, #fff);
}
.startup-actions strong { display: block; color: #263d50; font-size: 12px; }
.startup-actions small { display: block; margin-top: 3px; color: #8496a5; font-size: 10px; }
.startup-hint { color: #8598a8; font-size: 10px; line-height: 1.7; }
.startup-hint p { margin: 3px 0; }
.startup-hint code { color: #47677c; background: #f2f7fb; padding: 1px 4px; border-radius: 3px; }
@media (max-width: 760px) {
  .startup-status-grid { grid-template-columns: 1fr; }
  .startup-actions { align-items: flex-start; flex-direction: column; }
}



.copyright-privilege-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
}

</style>
