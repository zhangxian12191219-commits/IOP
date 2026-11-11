<template>
  <div class="virtualization-page">
    <el-card class="hero-card">
      <div class="hero-main">
        <div class="hero-copy">
          <span class="hero-kicker">VIRTUAL INFRASTRUCTURE / 只读纳管</span>
          <h1>虚拟化管理</h1>
          <p>统一查看 VMware vCenter、H3C CAS、Proxmox VE、OpenStack、KVM、Docker 与 Kubernetes 节点/容器资源和使用率排行，不执行开关机、删除等写操作。</p>
        </div>
        <div class="hero-actions">
          <el-button :loading="syncingAll" @click="syncAll">
            <el-icon><Refresh /></el-icon>立即同步
          </el-button>
          <el-button type="primary" @click="openPlatformDialog()">
            <el-icon><Plus /></el-icon>添加平台
          </el-button>
        </div>
      </div>

      <div class="stat-grid">
        <div v-for="card in statCards" :key="card.key" class="stat-card" :class="card.tone">
          <span class="stat-label">{{ card.label }}</span>
          <strong class="stat-value">{{ card.value }}</strong>
          <span class="stat-foot">{{ card.foot }}</span>
        </div>
      </div>
    </el-card>

    <el-card class="platform-card">
      <template #header>
        <div class="section-head">
          <div>
            <strong>平台连接</strong>
            <small>VMware vCenter 8.0+ / H3C CAS / Proxmox VE / OpenStack / KVM libvirt over SSH</small>
          </div>
          <el-button link type="primary" @click="loadAll" :loading="loading">刷新</el-button>
        </div>
      </template>
      <el-empty v-if="!platforms.length" description="还没有虚拟化平台，请先添加一个连接" :image-size="60">
        <el-button type="primary" @click="openPlatformDialog()">添加虚拟化 / 容器平台</el-button>
      </el-empty>
      <div v-else class="platform-list">
        <div v-for="platform in platforms" :key="platform.id" class="platform-item">
          <div class="platform-top">
            <div class="platform-name">
              <span class="platform-icon" :class="platform.platform_type">
                <el-icon><Cpu v-if="platform.platform_type === 'vmware'" /><Box v-else-if="['cas','docker'].includes(platform.platform_type)" /><Monitor v-else /></el-icon>
              </span>
              <div>
                <strong>{{ platform.name }}</strong>
                <small>{{ platformTypeName(platform.platform_type) }} · {{ platform.address }}:{{ platform.port }}</small>
              </div>
            </div>
            <el-tag :type="platform.last_sync_status === 'success' ? 'success' : platform.last_sync_status === 'failed' ? 'danger' : 'info'" size="small" effect="plain">
              {{ syncStatusText(platform.last_sync_status) }}
            </el-tag>
          </div>
          <div class="platform-meta">
            <span>宿主机 <b>{{ platform.host_count }}</b></span>
            <span>虚拟机 <b>{{ platform.vm_count }}</b></span>
            <span>同步间隔 <b>{{ platform.sync_interval_minutes }} 分钟</b></span>
            <span>最后同步 <b>{{ fmtDate(platform.last_sync_at) }}</b></span>
          </div>
          <div v-if="platform.health?.ceph?.available" class="platform-ceph-health">
            <el-tag size="small" :type="platform.health.ceph.status === 'HEALTH_OK' ? 'success' : platform.health.ceph.status === 'HEALTH_ERR' ? 'danger' : 'warning'" effect="plain">
              Ceph {{ platform.health.ceph.status }}
            </el-tag>
            <span>OSD {{ platform.health.ceph.osd_up }}/{{ platform.health.ceph.osd_total }} up、{{ platform.health.ceph.osd_in }}/{{ platform.health.ceph.osd_total }} in</span>
            <span v-if="platform.health.ceph.osd_down || platform.health.ceph.osd_out" class="danger">down/out {{ Math.max(platform.health.ceph.osd_down || 0, platform.health.ceph.osd_out || 0) }}</span>
            <span v-if="platform.health.ceph.pg_degraded" class="danger">PG 异常 {{ platform.health.ceph.pg_degraded }}</span>
          </div>
          <div v-if="platform.health?.storage?.available" class="platform-ceph-health">
            <span>平台存储 <b>{{ platform.health.storage.items?.length || 0 }}</b> 个</span>
            <span v-if="platform.health.storage.items?.some((s) => s.status !== 'available')" class="danger">
              异常 {{ platform.health.storage.items.filter((s) => s.status !== 'available').length }}
            </span>
            <span v-if="platform.health.storage.items?.some((s) => s.usage > 85)" class="danger">
              超 85% {{ platform.health.storage.items.filter((s) => s.usage > 85).length }}
            </span>
          </div>
          <p v-if="platform.last_error" class="platform-error">{{ platform.last_error }}</p>
          <div class="platform-actions">
            <el-button size="small" :loading="testingId === platform.id" @click="testPlatform(platform)">
              <el-icon><Connection /></el-icon>测试连接
            </el-button>
            <el-button size="small" :loading="syncingId === platform.id" @click="syncPlatform(platform)">
              <el-icon><Refresh /></el-icon>同步
            </el-button>
            <el-button size="small" @click="openPlatformDialog(platform)">编辑</el-button>
            <el-button size="small" type="danger" plain @click="removePlatform(platform)">删除</el-button>
          </div>
        </div>
      </div>
    </el-card>

    <el-card class="content-card" v-loading="loading">
      <el-tabs v-model="activeTab" @tab-change="onTabChange">
        <el-tab-pane label="虚拟机" name="vms">
          <div class="filter-row">
            <el-select v-model="vmFilters.platform_id" clearable placeholder="全部平台" style="width: 165px" @change="onVmPlatformChange">
              <el-option v-for="platform in platforms" :key="platform.id" :label="platform.name" :value="platform.id" />
            </el-select>
            <el-select v-model="vmFilters.host_id" clearable filterable placeholder="全部宿主机" style="width: 170px" @change="loadVms(1)">
              <el-option v-for="host in vmHostOptions" :key="host.id" :label="host.name" :value="host.id" />
            </el-select>
            <el-select v-model="vmFilters.status" clearable placeholder="全部状态" style="width: 120px" @change="loadVms(1)">
              <el-option label="运行中" value="running" />
              <el-option label="已关机" value="stopped" />
              <el-option label="已暂停" value="paused" />
              <el-option label="未知" value="unknown" />
            </el-select>
            <el-select v-model="vmFilters.guest_os" clearable filterable placeholder="全部系统" style="width: 160px" @change="loadVms(1)">
              <el-option v-for="item in filterOptions.guest_os" :key="item" :label="item" :value="item" />
            </el-select>
            <el-select v-model="vmFilters.min_cpu" clearable placeholder="CPU 使用率" style="width: 145px" @change="loadVms(1)">
              <el-option label="CPU ≥ 50%" :value="50" />
              <el-option label="CPU ≥ 70%" :value="70" />
              <el-option label="CPU ≥ 80%" :value="80" />
              <el-option label="CPU ≥ 90%" :value="90" />
            </el-select>
            <el-select v-model="vmFilters.min_memory" clearable placeholder="内存使用率" style="width: 145px" @change="loadVms(1)">
              <el-option label="内存 ≥ 50%" :value="50" />
              <el-option label="内存 ≥ 70%" :value="70" />
              <el-option label="内存 ≥ 80%" :value="80" />
              <el-option label="内存 ≥ 90%" :value="90" />
            </el-select>
            <el-select v-model="vmFilters.min_disk" clearable placeholder="磁盘使用率" style="width: 145px" @change="loadVms(1)">
              <el-option label="磁盘 ≥ 50%" :value="50" />
              <el-option label="磁盘 ≥ 70%" :value="70" />
              <el-option label="磁盘 ≥ 80%" :value="80" />
              <el-option label="磁盘 ≥ 90%" :value="90" />
            </el-select>
            <el-popover placement="bottom-start" :width="300" trigger="click">
              <template #reference>
                <el-button plain>资源条件<span v-if="resourceFilterCount" class="filter-badge">{{ resourceFilterCount }}</span></el-button>
              </template>
              <div class="resource-filter-panel">
                <div class="resource-filter-row">
                  <span>vCPU ≥</span>
                  <el-select v-model="vmFilters.min_vcpu" clearable placeholder="不限" style="width: 170px" @change="loadVms(1)">
                    <el-option label="2 核" :value="2" />
                    <el-option label="4 核" :value="4" />
                    <el-option label="8 核" :value="8" />
                    <el-option label="16 核" :value="16" />
                    <el-option label="32 核" :value="32" />
                  </el-select>
                </div>
                <div class="resource-filter-row">
                  <span>内存 ≥</span>
                  <el-select v-model="vmFilters.min_memory_mb" clearable placeholder="不限" style="width: 170px" @change="loadVms(1)">
                    <el-option label="4 GB" :value="4096" />
                    <el-option label="8 GB" :value="8192" />
                    <el-option label="16 GB" :value="16384" />
                    <el-option label="32 GB" :value="32768" />
                    <el-option label="64 GB" :value="65536" />
                  </el-select>
                </div>
                <div class="resource-filter-row">
                  <span>磁盘容量 ≥</span>
                  <el-select v-model="vmFilters.min_disk_gb" clearable placeholder="不限" style="width: 170px" @change="loadVms(1)">
                    <el-option label="100 GB" :value="100" />
                    <el-option label="500 GB" :value="500" />
                    <el-option label="1000 GB" :value="1000" />
                    <el-option label="2000 GB" :value="2000" />
                  </el-select>
                </div>
              </div>
            </el-popover>
            <el-input v-model="vmFilters.keyword" clearable placeholder="搜索名称 / 操作系统" style="width: 215px" @keyup.enter="loadVms(1)" @clear="loadVms(1)" />
            <el-button type="primary" plain @click="loadVms(1)">查询</el-button>
            <el-button @click="resetVmFilters">重置</el-button>
            <span class="result-count">共 {{ vmTotal }} 台</span>
          </div>
          <el-table :data="vms" size="small" stripe class="virtual-table" @row-click="openVm" @sort-change="onVmSortChange">
            <el-table-column prop="name" label="虚拟机" min-width="180" sortable="custom">
              <template #default="{ row }">
                <div class="vm-name-cell">
                  <span class="vm-state-dot" :class="row.power_state"></span>
                  <div><strong>{{ row.name }}</strong><small>{{ row.guest_os || '操作系统未识别' }}</small></div>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="platform_name" label="平台" width="120" />
            <el-table-column prop="host_name" label="宿主机" min-width="130">
              <template #default="{ row }">{{ row.host_name || '-' }}</template>
            </el-table-column>
            <el-table-column prop="power_state" label="状态" width="92" sortable="custom">
              <template #default="{ row }">
                <el-tag size="small" :type="powerTag(row.power_state)" effect="light">{{ powerText(row.power_state) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="vcpu" label="vCPU / CPU" width="150" sortable="custom">
              <template #default="{ row }">
                <div class="usage-cell"><span>{{ row.vcpu || '-' }} 核</span><b :class="usageClass(row.cpu_usage)">{{ fmtPct(row.cpu_usage) }}</b></div>
                <el-progress :percentage="safePct(row.cpu_usage)" :show-text="false" :stroke-width="4" />
              </template>
            </el-table-column>
            <el-table-column prop="memory_mb" label="内存 / 使用率" width="180" sortable="custom">
              <template #default="{ row }">
                <div class="usage-cell"><span>{{ fmtMb(row.memory_mb) }}</span><b :class="usageClass(row.memory_usage)">{{ fmtPct(row.memory_usage) }}</b></div>
                <el-progress :percentage="safePct(row.memory_usage)" :show-text="false" :stroke-width="4" />
              </template>
            </el-table-column>
            <el-table-column prop="disk_total_gb" label="磁盘 / 使用率" width="195" sortable="custom">
              <template #default="{ row }">
                <div class="usage-cell"><span>{{ fmtGb(row.disk_total_gb) }}</span><b :class="usageClass(row.disk_usage)">{{ fmtPct(row.disk_usage) }}</b></div>
                <el-progress :percentage="safePct(row.disk_usage)" :show-text="false" :stroke-width="4" />
              </template>
            </el-table-column>
            <el-table-column prop="ip_address" label="IP" min-width="140" sortable="custom">
              <template #default="{ row }">{{ (row.ip_addresses || []).join(', ') || '-' }}</template>
            </el-table-column>
          </el-table>
          <el-pagination
            v-if="vmTotal > 0"
            class="table-pager"
            layout="total, sizes, prev, pager, next"
            :total="vmTotal"
            :page-size="vmPageSize"
            :page-sizes="vmPageSizeOptions"
            :current-page="vmPage"
            @current-change="loadVms"
            @size-change="onVmPageSizeChange"
          />
        </el-tab-pane>

        <el-tab-pane label="宿主机" name="hosts">
          <div class="filter-row">
            <el-select v-model="hostFilters.platform_id" clearable placeholder="全部平台" style="width: 170px" @change="loadHosts(1)">
              <el-option v-for="platform in platforms" :key="platform.id" :label="platform.name" :value="platform.id" />
            </el-select>
            <el-select v-model="hostFilters.status" clearable placeholder="全部状态" style="width: 130px" @change="loadHosts(1)">
              <el-option label="在线" value="online" />
              <el-option label="离线" value="offline" />
              <el-option label="未知" value="unknown" />
            </el-select>
            <el-select v-model="hostFilters.cluster_name" clearable filterable placeholder="全部集群" style="width: 170px" @change="loadHosts(1)">
              <el-option v-for="item in filterOptions.clusters" :key="item" :label="item" :value="item" />
            </el-select>
            <el-select v-model="hostFilters.min_cpu" clearable placeholder="CPU 使用率" style="width: 145px" @change="loadHosts(1)">
              <el-option label="CPU ≥ 50%" :value="50" />
              <el-option label="CPU ≥ 70%" :value="70" />
              <el-option label="CPU ≥ 80%" :value="80" />
              <el-option label="CPU ≥ 90%" :value="90" />
            </el-select>
            <el-select v-model="hostFilters.min_memory" clearable placeholder="内存使用率" style="width: 145px" @change="loadHosts(1)">
              <el-option label="内存 ≥ 50%" :value="50" />
              <el-option label="内存 ≥ 70%" :value="70" />
              <el-option label="内存 ≥ 80%" :value="80" />
              <el-option label="内存 ≥ 90%" :value="90" />
            </el-select>
            <el-select v-model="hostFilters.min_storage" clearable placeholder="存储使用率" style="width: 145px" @change="loadHosts(1)">
              <el-option label="存储 ≥ 50%" :value="50" />
              <el-option label="存储 ≥ 70%" :value="70" />
              <el-option label="存储 ≥ 80%" :value="80" />
              <el-option label="存储 ≥ 90%" :value="90" />
            </el-select>
            <el-select v-model="hostFilters.min_vm_count" clearable placeholder="虚拟机数量" style="width: 145px" @change="loadHosts(1)">
              <el-option label="虚拟机 ≥ 1" :value="1" />
              <el-option label="虚拟机 ≥ 10" :value="10" />
              <el-option label="虚拟机 ≥ 20" :value="20" />
              <el-option label="虚拟机 ≥ 50" :value="50" />
            </el-select>
            <el-input v-model="hostFilters.keyword" clearable placeholder="搜索宿主机 / 集群" style="width: 220px" @keyup.enter="loadHosts(1)" @clear="loadHosts(1)" />
            <el-button type="primary" plain @click="loadHosts(1)">查询</el-button>
            <el-button @click="resetHostFilters">重置</el-button>
            <span class="result-count">共 {{ hostTotal }} 台</span>
          </div>
          <el-table :data="hosts" size="small" stripe class="virtual-table" @row-click="openHost" @sort-change="onHostSortChange">
            <el-table-column prop="name" label="宿主机" min-width="180" sortable="custom">
              <template #default="{ row }">
                <div class="vm-name-cell">
                  <span class="host-icon"><el-icon><Monitor /></el-icon></span>
                  <div><strong>{{ row.name }}</strong><small>{{ row.cluster_name || '未分组' }}</small></div>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="platform_name" label="平台" width="120" />
            <el-table-column prop="status" label="状态" width="90" sortable="custom">
              <template #default="{ row }"><el-tag size="small" :type="row.status === 'online' ? 'success' : 'info'">{{ row.status === 'online' ? '在线' : '离线' }}</el-tag></template>
            </el-table-column>
            <el-table-column prop="cpu_usage" label="CPU" width="150" sortable="custom">
              <template #default="{ row }">
                <div class="usage-cell"><span>{{ row.cpu_cores || '-' }} 核</span><b>{{ fmtPct(row.cpu_usage) }}</b></div>
                <el-progress class="host-progress" :percentage="safePct(row.cpu_usage)" :show-text="false" :stroke-width="5" :color="progressColor(row.cpu_usage)" striped striped-flow :duration="1.8" />
              </template>
            </el-table-column>
            <el-table-column prop="memory_usage" label="内存" width="150" sortable="custom">
              <template #default="{ row }">
                <div class="usage-cell"><span>{{ fmtGb(row.memory_total_mb / 1024) }}</span><b>{{ fmtPct(row.memory_usage) }}</b></div>
                <el-progress class="host-progress" :percentage="safePct(row.memory_usage)" :show-text="false" :stroke-width="5" :color="progressColor(row.memory_usage)" striped striped-flow :duration="1.8" />
              </template>
            </el-table-column>
            <el-table-column prop="storage_usage" label="存储" width="150" sortable="custom">
              <template #default="{ row }">
                <div class="usage-cell"><span>{{ fmtGb(row.storage_used_gb) }} / {{ fmtGb(row.storage_total_gb) }}</span><b>{{ fmtPct(row.storage_usage) }}</b></div>
                <el-progress class="host-progress" :percentage="safePct(row.storage_usage)" :show-text="false" :stroke-width="5" :color="progressColor(row.storage_usage)" striped striped-flow :duration="1.8" />
              </template>
            </el-table-column>
            <el-table-column prop="ip_address" label="IP" width="155" sortable="custom">
              <template #default="{ row }">{{ row.ip_address || row.name || '-' }}</template>
            </el-table-column>
            <el-table-column prop="vm_count" label="虚拟机" width="92" sortable="custom">
              <template #default="{ row }">{{ row.vm_count }} 台</template>
            </el-table-column>
            <el-table-column prop="last_seen" label="最后同步" min-width="150" sortable="custom">
              <template #default="{ row }">{{ fmtDate(row.last_seen) }}</template>
            </el-table-column>
          </el-table>
          <el-pagination
            v-if="hostTotal > hostPageSize"
            class="table-pager"
            layout="total, prev, pager, next"
            :total="hostTotal"
            :page-size="hostPageSize"
            :current-page="hostPage"
            @current-change="loadHosts"
          />
        </el-tab-pane>

        <el-tab-pane label="虚拟机告警" name="alerts">
          <div class="filter-row alert-toolbar">
            <el-radio-group v-model="vmAlertStatus" @change="loadVmAlerts(1)">
              <el-radio-button value="active">当前告警</el-radio-button>
              <el-radio-button value="history">告警历史</el-radio-button>
              <el-radio-button value="all">全部</el-radio-button>
            </el-radio-group>
            <el-tag v-if="vmAlertCounts.unacknowledged" type="danger" effect="plain" size="small">
              未确认 {{ vmAlertCounts.unacknowledged }}
            </el-tag>
            <el-tag type="warning" effect="plain" size="small">当前 {{ vmAlertCounts.active }}</el-tag>
            <el-tag type="info" effect="plain" size="small">历史 {{ vmAlertCounts.history || 0 }}</el-tag>
            <span class="result-count">虚拟机 CPU / 内存 / 磁盘使用率超过阈值，或虚拟机已关机时自动告警</span>
            <div class="alert-toolbar-actions">
              <el-button v-if="vmAlertStatus === 'history'" size="small" type="danger" plain
                :disabled="!selectedVmAlerts.length" title="勾选历史告警后批量删除"
                @click="batchDeleteAlerts('vm')">删除历史</el-button>
              <el-button size="small" @click="openAlertRules">告警规则</el-button>
              <el-button size="small" :loading="vmAlertLoading" @click="loadVmAlerts(vmAlertPage)">刷新</el-button>
            </div>
          </div>
          <div v-if="selectedVmAlerts.length" class="alert-batch-bar">
            <span class="alert-batch-text">已选择 <b>{{ selectedVmAlerts.length }}</b> 条告警</span>
            <el-button size="small" type="primary" :loading="batchAlertSaving" @click="openBatchAckDialog">批量确认</el-button>
            <el-button v-if="selectedVmAlerts.every((item) => item.is_resolved)" size="small" type="danger" plain @click="batchDeleteAlerts('vm')">批量删除历史</el-button>
            <el-button size="small" @click="clearVmAlertSelection">取消选择</el-button>
            <span class="alert-batch-tip">批量确认后隐藏所选活动告警；历史告警可批量删除</span>
          </div>
          <el-table
            ref="vmAlertTableRef"
            :data="vmAlerts"
            size="small"
            stripe
            class="virtual-table"
            v-loading="vmAlertLoading"
            :row-class-name="vmAlertRowClassName"
            @selection-change="onVmAlertSelectionChange"
          >
            <el-table-column type="selection" width="44" fixed="left" />
            <el-table-column label="时间" width="165">
              <template #default="{ row }">{{ fmtDate(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="级别" width="82">
              <template #default="{ row }">
                <el-tag size="small" :type="alertLevelType(row.alert_level)" effect="dark">{{ alertLevelText(row.alert_level) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="对象" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">
                <span>{{ row.vm_name || row.platform_name || '虚拟化平台' }}</span>
                <el-tag v-if="row.target_type === 'platform'" size="small" type="warning" effect="plain" style="margin-left: 6px">平台</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="platform_name" label="平台" width="120" show-overflow-tooltip />
            <el-table-column prop="alert_type_text" label="指标" width="110" />
            <el-table-column prop="message" label="告警内容" min-width="280" show-overflow-tooltip />
            <el-table-column label="当前值 / 阈值" width="145">
              <template #default="{ row }">
                <span v-if="row.value !== null && row.value !== undefined">{{ fmtPct(row.value) }}</span>
                <span v-else>{{ row.alert_type === 'vm_shutdown' ? '关机' : '平台状态' }}</span>
                <span v-if="row.threshold !== null && row.threshold !== undefined" class="threshold-text"> / {{ fmtPct(row.threshold) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="通知" width="82">
              <template #default="{ row }">
                <el-tag size="small" :type="row.send_notification === false ? 'info' : 'success'" effect="plain">
                  {{ row.send_notification === false ? '不发送' : '发送' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag size="small" :type="row.is_resolved ? 'success' : row.is_acknowledged ? 'info' : 'danger'" effect="plain">
                  {{ row.is_resolved ? '已恢复' : row.is_acknowledged ? '已确认' : '未确认' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="135" fixed="right">
              <template #default="{ row }">
                <el-button
                  link
                  type="primary"
                  size="small"
                  @click.stop="openAlertHandleDialog(row)"
                >{{ !row.is_resolved && !row.is_acknowledged ? '确认' : '详情' }}</el-button>
                <el-button
                  v-if="row.is_resolved"
                  link
                  type="danger"
                  size="small"
                  @click.stop="deleteAlertHistory(row, 'vm')"
                >删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!vmAlerts.length && !vmAlertLoading" description="当前没有虚拟机告警" :image-size="60" />
          <el-pagination
            v-if="vmAlertTotal > vmAlertPageSize"
            class="table-pager"
            layout="total, sizes, prev, pager, next, jumper"
            :total="vmAlertTotal"
            :page-size="vmAlertPageSize"
            :page-sizes="[20, 50, 100]"
            :current-page="vmAlertPage"
            @current-change="loadVmAlerts"
            @size-change="onVmAlertPageSizeChange"
          />
        </el-tab-pane>

        <el-tab-pane label="虚拟化/容器平台告警" name="platform-alerts">
          <div class="filter-row alert-toolbar">
            <el-radio-group v-model="platformAlertStatus" @change="loadPlatformAlerts(1)">
              <el-radio-button value="active">当前告警</el-radio-button>
              <el-radio-button value="history">告警历史</el-radio-button>
              <el-radio-button value="all">全部</el-radio-button>
            </el-radio-group>
            <el-tag v-if="platformAlertCounts.unacknowledged" type="danger" effect="plain" size="small">
              未确认 {{ platformAlertCounts.unacknowledged }}
            </el-tag>
            <el-tag type="warning" effect="plain" size="small">当前 {{ platformAlertCounts.active }}</el-tag>
            <el-tag type="info" effect="plain" size="small">历史 {{ platformAlertCounts.history || 0 }}</el-tag>
            <span class="result-count">平台连接、认证/登录、同步失败、同步超时及宿主机存储汇总超阈值自动告警</span>
            <div class="alert-toolbar-actions">
              <el-button v-if="platformAlertStatus === 'history'" size="small" type="danger" plain
                :disabled="!selectedPlatformAlerts.length" title="勾选历史告警后批量删除"
                @click="batchDeleteAlerts('platform')">删除历史</el-button>
              <el-button size="small" @click="openAlertRules">告警规则</el-button>
              <el-button size="small" :loading="platformAlertLoading" @click="loadPlatformAlerts(platformAlertPage)">刷新</el-button>
            </div>
          </div>
          <div v-if="selectedPlatformAlerts.length" class="alert-batch-bar">
            <span class="alert-batch-text">已选择 <b>{{ selectedPlatformAlerts.length }}</b> 条平台告警</span>
            <el-button size="small" type="primary" :loading="batchAlertSaving" @click="openBatchAckDialog('platform')">批量确认</el-button>
            <el-button v-if="selectedPlatformAlerts.every((item) => item.is_resolved)" size="small" type="danger" plain @click="batchDeleteAlerts('platform')">批量删除历史</el-button>
            <el-button size="small" @click="clearPlatformAlertSelection">取消选择</el-button>
            <span class="alert-batch-tip">批量确认后隐藏所选活动告警；历史告警可批量删除</span>
          </div>
          <el-table
            ref="platformAlertTableRef"
            :data="platformAlerts"
            size="small"
            stripe
            class="virtual-table"
            v-loading="platformAlertLoading"
            :row-class-name="platformAlertRowClassName"
            @selection-change="onPlatformAlertSelectionChange"
          >
            <el-table-column type="selection" width="44" fixed="left" />
            <el-table-column label="时间" width="165">
              <template #default="{ row }">{{ fmtDate(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="级别" width="82">
              <template #default="{ row }">
                <el-tag size="small" :type="alertLevelType(row.alert_level)" effect="dark">{{ alertLevelText(row.alert_level) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="platform_name" label="虚拟化/容器平台" min-width="200" show-overflow-tooltip />
            <el-table-column prop="alert_type_text" label="告警类型" width="140" />
            <el-table-column prop="message" label="告警内容" min-width="300" show-overflow-tooltip />
            <el-table-column label="当前值 / 阈值" width="145">
              <template #default="{ row }">
                <span v-if="row.value !== null && row.value !== undefined">{{ fmtPct(row.value) }}</span>
                <span v-else>状态异常</span>
                <span v-if="row.threshold !== null && row.threshold !== undefined" class="threshold-text"> / {{ fmtPct(row.threshold) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="通知" width="82">
              <template #default="{ row }">
                <el-tag size="small" :type="row.send_notification === false ? 'info' : 'success'" effect="plain">
                  {{ row.send_notification === false ? '不发送' : '发送' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag size="small" :type="row.is_resolved ? 'success' : row.is_acknowledged ? 'info' : 'danger'" effect="plain">
                  {{ row.is_resolved ? '已恢复' : row.is_acknowledged ? '已确认' : '未确认' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="135" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click.stop="openAlertHandleDialog(row)">
                  {{ !row.is_resolved && !row.is_acknowledged ? '确认' : '详情' }}
                </el-button>
                <el-button
                  v-if="row.is_resolved"
                  link
                  type="danger"
                  size="small"
                  @click.stop="deleteAlertHistory(row, 'platform')"
                >删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!platformAlerts.length && !platformAlertLoading" description="当前没有虚拟化/容器平台告警" :image-size="60" />
          <el-pagination
            v-if="platformAlertTotal > platformAlertPageSize"
            class="table-pager"
            layout="total, sizes, prev, pager, next, jumper"
            :total="platformAlertTotal"
            :page-size="platformAlertPageSize"
            :page-sizes="[20, 50, 100]"
            :current-page="platformAlertPage"
            @current-change="loadPlatformAlerts"
            @size-change="onPlatformAlertPageSizeChange"
          />
        </el-tab-pane>

        <el-tab-pane label="Top 排行" name="top">
          <div class="filter-row">
            <el-select v-model="topMetric" style="width: 170px" @change="loadTop">
              <el-option label="CPU 使用率" value="cpu_usage" />
              <el-option label="内存使用率" value="memory_usage" />
              <el-option label="硬盘使用率" value="disk_usage" />
            </el-select>
            <el-select v-model="topPlatformId" clearable placeholder="全部平台" style="width: 170px" @change="loadTop">
              <el-option v-for="platform in platforms" :key="platform.id" :label="platform.name" :value="platform.id" />
            </el-select>
            <el-radio-group v-model="topLimit" @change="loadTop">
              <el-radio-button :value="5">Top 5</el-radio-button>
              <el-radio-button :value="10">Top 10</el-radio-button>
            </el-radio-group>
            <span class="result-count">虚拟机 Top 与宿主机 Top 分开统计；宿主机“硬盘”对应存储使用率</span>
          </div>
          <div class="top-split">
            <div class="top-section">
              <div class="top-section-head">
                <div><strong>虚拟机 Top</strong><span>仅统计运行中的虚拟机</span></div>
                <el-tag size="small" type="success" effect="plain">{{ vmTopItems.length }} 台</el-tag>
              </div>
              <el-empty v-if="!vmTopItems.length" description="暂无运行中虚拟机使用率数据" :image-size="50" />
              <div v-else class="top-list" :key="`vm-${topRenderKey}`">
                <div v-for="(item, index) in vmTopItems" :key="item.id" class="top-item">
                  <span class="top-rank" :class="{ first: index === 0, second: index === 1, third: index === 2 }">{{ String(index + 1).padStart(2, '0') }}</span>
                  <div class="top-info">
                    <div class="top-name-row"><strong>{{ item.name }}</strong><span>{{ item.platform_name }} · {{ item.host_name || '-' }}</span></div>
                    <div class="top-bar"><i :style="{ '--target': safePct(item.value) / 100, animationDelay: `${index * 70}ms` }"></i></div>
                  </div>
                  <b class="top-value">{{ fmtPct(item.value) }}</b>
                </div>
              </div>
            </div>
            <div class="top-section host-top-section">
              <div class="top-section-head">
                <div><strong>宿主机 Top</strong><span>仅统计在线宿主机</span></div>
                <el-tag size="small" type="info" effect="plain">{{ hostTopItems.length }} 台</el-tag>
              </div>
              <el-empty v-if="!hostTopItems.length" description="暂无在线宿主机使用率数据" :image-size="50" />
              <div v-else class="top-list" :key="`host-${topRenderKey}`">
                <div v-for="(item, index) in hostTopItems" :key="item.id" class="top-item">
                  <span class="top-rank" :class="{ first: index === 0, second: index === 1, third: index === 2 }">{{ String(index + 1).padStart(2, '0') }}</span>
                  <div class="top-info">
                    <div class="top-name-row"><strong>{{ item.name }}</strong><span>{{ item.platform_name }} · {{ item.host_name || '-' }}</span></div>
                    <div class="top-bar"><i :style="{ '--target': safePct(item.value) / 100, animationDelay: `${index * 70}ms` }"></i></div>
                  </div>
                  <b class="top-value">{{ fmtPct(item.value) }}</b>
                </div>
              </div>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <el-dialog v-model="platformDialogVisible" :title="editingPlatform ? '编辑虚拟化平台' : '添加虚拟化平台'" width="640px" top="4vh" class="platform-dialog">
      <el-form :model="platformForm" label-width="100px" label-position="left" class="platform-form">
        <el-form-item label="平台名称" required>
          <el-input v-model="platformForm.name" placeholder="例如：生产 vCenter" />
        </el-form-item>
        <el-form-item label="平台类型" required>
          <el-radio-group v-model="platformForm.platform_type" size="small" @change="onPlatformTypeChange">
            <el-radio-button value="vmware">VMware vCenter</el-radio-button>
            <el-radio-button value="proxmox">Proxmox VE</el-radio-button>
            <el-radio-button value="cas">H3C CAS</el-radio-button>
            <el-radio-button value="kvm">KVM / libvirt</el-radio-button>
            <el-radio-button value="docker">Docker</el-radio-button>
            <el-radio-button value="kubernetes">Kubernetes</el-radio-button>
            <el-radio-button value="openstack">OpenStack</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <div class="connect-guide">
          <div class="connect-guide-head">
            <span>连接指引</span>
            <small>{{ connectionGuide.title }}</small>
          </div>
          <ol class="connect-guide-steps">
            <li v-for="step in connectionGuide.steps" :key="step">{{ step }}</li>
          </ol>
          <div class="connect-guide-note">{{ connectionGuide.note }}</div>
        </div>
        <el-form-item label="管理地址" required>
          <el-input v-model="platformForm.address" :placeholder="platformForm.platform_type === 'docker' ? 'Docker 主机 IP 或域名，例如 10.10.0.40' : platformForm.platform_type === 'kubernetes' ? 'Kubernetes API 地址，例如 10.10.0.50' : platformForm.platform_type === 'cas' ? 'CAS 管理 IP 或域名，例如 10.10.0.20' : platformForm.platform_type === 'proxmox' ? 'Proxmox 节点 IP 或域名，例如 10.10.0.30' : platformForm.platform_type === 'openstack' ? 'Keystone 地址，例如 10.10.0.60 或 https://keystone.example.com' : 'IP 或域名，例如 10.10.0.20'" />
        </el-form-item>
        <el-form-item label="端口" required>
          <el-input-number v-model="platformForm.port" :min="1" :max="65535" controls-position="right" style="width: 160px" />
          <span class="form-hint">{{ platformForm.platform_type === 'vmware' ? 'HTTPS 默认 443' : platformForm.platform_type === 'proxmox' ? 'Proxmox 默认 8006' : platformForm.platform_type === 'cas' ? 'CAS 默认 8080' : platformForm.platform_type === 'docker' ? 'Docker 默认 2375 / TLS 2376' : platformForm.platform_type === 'kubernetes' ? 'Kubernetes API 默认 6443' : platformForm.platform_type === 'openstack' ? 'Keystone 默认 5000' : 'SSH 默认 22' }}</span>
        </el-form-item>
        <el-form-item label="用户名" required>
          <el-input v-model="platformForm.username" :placeholder="platformForm.platform_type === 'vmware' ? '只读 SSO 账号，如 snmp-nms@vsphere.local' : platformForm.platform_type === 'proxmox' ? 'root@pam 或 root@pam!tokenid' : platformForm.platform_type === 'docker' ? 'Docker API 用户名，无认证可填 docker' : platformForm.platform_type === 'kubernetes' ? 'Kubernetes（令牌填在密码栏）' : platformForm.platform_type === 'openstack' ? 'OpenStack 用户名' : '只读账号'" />
          <span v-if="platformForm.platform_type === 'vmware'" class="form-hint">
            必须使用 vSphere SSO 账号，格式 user@vsphere.local 或 user@AD域；只填用户名时自动补 @vsphere.local
          </span>
          <span v-else-if="platformForm.platform_type === 'proxmox'" class="form-hint">
            密码登录填 root@pam；API Token 填 user@realm!tokenid，密码填 Token Secret
          </span>
        </el-form-item>
        <el-form-item v-if="platformForm.platform_type === 'openstack'" label="项目/租户" required>
          <el-input v-model="platformForm.project_name" placeholder="例如 admin、demo 或项目名称" />
          <span class="form-hint">OpenStack 项目（tenant）名称，用于认证后读取 Nova/Cinder 资源。</span>
        </el-form-item>
        <el-form-item v-if="platformForm.platform_type === 'openstack'" label="认证域">
          <el-input v-model="platformForm.domain_name" placeholder="默认 Default" />
          <span class="form-hint">Keystone 用户和项目所属域，通常为 Default；LDAP 环境请填写实际域名。</span>
        </el-form-item>
        <el-form-item label="密码" :required="!editingPlatform">
          <el-input v-model="platformForm.password" type="password" show-password :placeholder="editingPlatform ? '留空表示不修改' : platformForm.platform_type === 'kubernetes' ? 'ServiceAccount Bearer Token' : platformForm.platform_type === 'proxmox' ? '密码或 API Token Secret' : platformForm.platform_type === 'openstack' ? 'OpenStack 用户密码' : '平台密码'" />
        </el-form-item>
        <el-form-item v-if="['vmware','proxmox','cas','docker','kubernetes','openstack'].includes(platformForm.platform_type)" label="TLS 校验">
          <el-switch v-model="platformForm.verify_tls" />
          <span class="form-hint">{{ platformForm.platform_type === 'docker' ? 'Docker TLS 使用自签名证书时可关闭' : platformForm.platform_type === 'kubernetes' ? 'Kubernetes API 使用自签名证书时可关闭' : platformForm.platform_type === 'cas' ? 'HTTPS 管理地址使用自签名证书时可关闭' : platformForm.platform_type === 'proxmox' ? 'Proxmox 自签名证书可关闭' : platformForm.platform_type === 'openstack' ? 'Keystone 自签名证书可关闭' : 'vCenter 自签名证书可关闭' }}</span>
        </el-form-item>
        <el-form-item label="同步间隔">
          <el-input-number v-model="platformForm.sync_interval_minutes" :min="1" :max="1440" controls-position="right" style="width: 160px" />
          <span class="form-hint">分钟</span>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="platformForm.enabled" />
        </el-form-item>
        <el-alert
          v-if="platformForm.platform_type === 'kvm'"
          type="info"
          :closable="false"
          show-icon
          title="KVM 使用 SSH + virsh 只读采集，请确保 SSH 账号有 libvirt 只读权限。"
        />
        <el-alert
          v-else-if="platformForm.platform_type === 'cas'"
          type="info"
          :closable="false"
          show-icon
          title="H3C CAS 使用 REST API + HTTP Digest 只读采集，需填写 CAS 管理平台账号和密码；默认 HTTP 8080，HTTPS 可用 8443 或地址带 https://。"
        />
        <el-alert
          v-else-if="platformForm.platform_type === 'docker'"
          type="info"
          :closable="false"
          show-icon
          title="Docker 使用 Engine API 只读采集。默认 2375；启用 TLS 时使用 2376，并在密码栏填写认证信息（无认证时用户名可填 docker）。"
        />
        <el-alert
          v-else-if="platformForm.platform_type === 'kubernetes'"
          type="info"
          :closable="false"
          show-icon
          title="Kubernetes 使用 API Server 只读采集。密码栏填写 ServiceAccount Bearer Token；账号需具备 nodes、pods 只读权限，默认 6443。"
        />
        <el-alert
          v-else-if="platformForm.platform_type === 'proxmox'"
          type="info"
          :closable="false"
          show-icon
          title="Proxmox VE 使用 API2 只读采集，默认 HTTPS 8006；支持 root@pam 密码或 user@realm!tokenid + Token Secret，只读账号建议分配 PVEAuditor 角色。"
        />
        <el-alert
          v-else-if="platformForm.platform_type === 'openstack'"
          type="info"
          :closable="false"
          show-icon
          title="OpenStack 使用 Keystone v3 认证，通过 Nova 读取宿主机/虚拟机、Cinder 读取磁盘容量；只读账号需要 compute、volume 查询权限。虚拟机实时 CPU/内存使用率需额外部署 Ceilometer/Gnocchi。"
        />
      </el-form>
      <template #footer>
        <el-button @click="platformDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingPlatform" @click="savePlatform">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="alertRulesVisible" title="虚拟化/容器平台告警规则" width="640px">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="规则对所有纳管虚拟化/容器平台与虚拟机生效，保存后立即重新评估；指标恢复到阈值以内或平台成功同步后会自动标记为已恢复。"
      />
      <el-form label-width="150px" class="alert-rules-form">
        <el-form-item label="CPU 使用率告警">
          <el-switch v-model="alertRulesForm.cpu_enabled" />
          <span class="rule-threshold-label">超过</span>
          <el-input-number v-model="alertRulesForm.cpu_threshold" :min="1" :max="100" :step="1" controls-position="right" style="width: 110px" :disabled="!alertRulesForm.cpu_enabled" />
          <span class="rule-unit">%</span>
        </el-form-item>
        <el-form-item label="内存使用率告警">
          <el-switch v-model="alertRulesForm.memory_enabled" />
          <span class="rule-threshold-label">超过</span>
          <el-input-number v-model="alertRulesForm.memory_threshold" :min="1" :max="100" :step="1" controls-position="right" style="width: 110px" :disabled="!alertRulesForm.memory_enabled" />
          <span class="rule-unit">%</span>
        </el-form-item>
        <el-form-item label="磁盘使用率告警">
          <el-switch v-model="alertRulesForm.disk_enabled" />
          <span class="rule-threshold-label">超过</span>
          <el-input-number v-model="alertRulesForm.disk_threshold" :min="1" :max="100" :step="1" controls-position="right" style="width: 110px" :disabled="!alertRulesForm.disk_enabled" />
          <span class="rule-unit">%</span>
        </el-form-item>
        <el-form-item label="关机告警">
          <el-switch v-model="alertRulesForm.shutdown_enabled" />
          <span class="rule-threshold-label">虚拟机状态为已关机时告警</span>
        </el-form-item>
        <el-divider content-position="left">虚拟化/容器平台</el-divider>
        <el-form-item label="平台状态告警">
          <el-switch v-model="alertRulesForm.platform_enabled" />
          <span class="rule-threshold-label">连接、认证/登录、同步失败或同步超时</span>
        </el-form-item>
        <el-form-item label="平台存储告警">
          <el-switch v-model="alertRulesForm.storage_enabled" />
          <span class="rule-threshold-label">宿主机存储汇总超过</span>
          <el-input-number v-model="alertRulesForm.storage_threshold" :min="1" :max="100" :step="1" controls-position="right" style="width: 110px" :disabled="!alertRulesForm.storage_enabled" />
          <span class="rule-unit">%</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="alertRulesVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingAlertRules" @click="saveAlertRules">保存规则</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="alertHandleVisible" title="处理虚拟化告警" width="620px">
      <template v-if="editingVmAlert">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item :label="editingVmAlert.target_type === 'platform' ? '虚拟化/容器平台' : '虚拟机'">
            {{ editingVmAlert.target_type === 'platform' ? (editingVmAlert.platform_name || editingVmAlert.target_name) : editingVmAlert.vm_name }}
            <span v-if="editingVmAlert.target_type !== 'platform' && editingVmAlert.platform_name" class="muted-text">（{{ editingVmAlert.platform_name }}）</span>
          </el-descriptions-item>
          <el-descriptions-item label="告警内容">{{ editingVmAlert.alert_type_text }} · {{ editingVmAlert.message }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag size="small" :type="editingVmAlert.is_resolved ? 'success' : editingVmAlert.is_acknowledged ? 'info' : 'danger'" effect="plain">
              {{ editingVmAlert.is_resolved ? '已恢复' : editingVmAlert.is_acknowledged ? '已确认' : '未确认' }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>
        <el-form label-width="140px" class="alert-rules-form alert-handle-form">
          <el-form-item label="告警级别">
            <el-select v-model="alertHandleForm.alert_level" style="width: 220px">
              <el-option label="提示（info）" value="info" />
              <el-option label="警告（warning）" value="warning" />
              <el-option label="严重（critical）" value="critical" />
              <el-option label="紧急（emergency）" value="emergency" />
            </el-select>
          </el-form-item>
          <el-form-item label="发送到告警渠道">
            <el-switch v-model="alertHandleForm.send_notification" active-text="发送" inactive-text="不发送" />
            <div class="alert-handle-tip">关闭后该告警不会发送到邮件 / Webhook 等告警渠道；重新开启时会补发一次通知，已成功发送过的渠道会自动去重，告警渠道自身的最低级别过滤仍然生效。</div>
          </el-form-item>
        </el-form>
      </template>
      <template #footer>
        <el-button @click="alertHandleVisible = false">取消</el-button>
        <el-button :loading="alertHandleSaving" @click="saveAlertHandle(false)">保存设置</el-button>
        <el-button
          v-if="editingVmAlert && !editingVmAlert.is_resolved && !editingVmAlert.is_acknowledged"
          type="primary"
          :loading="alertHandleSaving"
          @click="saveAlertHandle(true)"
        >确认告警</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="batchAlertVisible" title="批量确认虚拟化告警" width="580px">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        :title="`将处理已选择的 ${batchAlertSource === 'platform' ? selectedPlatformAlerts.length : selectedVmAlerts.length} 条告警。批量确认后这些告警会从当前活动列表隐藏；告警级别与通知开关可选统一调整。`"
      />
      <el-form label-width="150px" class="alert-rules-form alert-handle-form">
        <el-form-item label="告警级别">
          <el-select v-model="batchAlertForm.alert_level" style="width: 220px">
            <el-option label="保持原级别" value="" />
            <el-option label="提示（info）" value="info" />
            <el-option label="警告（warning）" value="warning" />
            <el-option label="严重（critical）" value="critical" />
            <el-option label="紧急（emergency）" value="emergency" />
          </el-select>
        </el-form-item>
        <el-form-item label="发送到告警渠道">
          <el-checkbox v-model="batchAlertForm.apply_notification">统一设置通知开关</el-checkbox>
          <el-switch v-model="batchAlertForm.send_notification" :disabled="!batchAlertForm.apply_notification" active-text="发送" inactive-text="不发送" />
          <div class="alert-handle-tip">不勾选「统一设置通知开关」时，保留每条告警原有的通知设置；告警渠道最低级别过滤仍然生效。</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="batchAlertVisible = false">取消</el-button>
        <el-button type="primary" :loading="batchAlertSaving" @click="submitBatchAck">批量确认</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="vmDrawerVisible" title="虚拟机详情" size="520px">
      <template v-if="selectedVm">
        <div class="drawer-title"><span class="vm-state-dot" :class="selectedVm.power_state"></span><strong>{{ selectedVm.name }}</strong><el-tag size="small" :type="powerTag(selectedVm.power_state)">{{ powerText(selectedVm.power_state) }}</el-tag></div>
        <el-descriptions :column="1" border size="small" class="detail-desc">
          <el-descriptions-item label="平台">{{ selectedVm.platform_name }}</el-descriptions-item>
          <el-descriptions-item label="宿主机">{{ selectedVm.host_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="操作系统">{{ selectedVm.guest_os || '-' }}</el-descriptions-item>
          <el-descriptions-item label="IP 地址">{{ (selectedVm.ip_addresses || []).join(', ') || '-' }}</el-descriptions-item>
          <el-descriptions-item label="网卡数量">{{ selectedVm.nic_count || 0 }}</el-descriptions-item>
          <el-descriptions-item label="Tools / Agent">{{ selectedVm.tools_status || '-' }}</el-descriptions-item>
          <el-descriptions-item label="最后同步">{{ fmtDate(selectedVm.last_seen) }}</el-descriptions-item>
        </el-descriptions>
        <div class="drawer-resource-grid">
          <div v-for="metric in vmResourceCards" :key="metric.key" class="drawer-resource">
            <span class="resource-label">{{ metric.label }}</span>
            <div class="resource-main">
              <strong>{{ metric.total }}</strong>
              <b :class="usageClass(metric.value)">{{ metric.usageText }}</b>
            </div>
            <el-progress :percentage="safePct(metric.value)" :show-text="false" :stroke-width="5" />
            <small>{{ metric.hint }}</small>
          </div>
        </div>
      </template>
    </el-drawer>

    <el-drawer v-model="hostDrawerVisible" title="宿主机详情" size="520px">
      <template v-if="selectedHost">
        <div class="drawer-title"><span class="host-icon"><el-icon><Monitor /></el-icon></span><strong>{{ selectedHost.name }}</strong><el-tag size="small" :type="selectedHost.status === 'online' ? 'success' : 'info'">{{ selectedHost.status === 'online' ? '在线' : '离线' }}</el-tag></div>
        <el-descriptions :column="1" border size="small" class="detail-desc">
          <el-descriptions-item label="平台">{{ selectedHost.platform_name }}</el-descriptions-item>
          <el-descriptions-item label="IP 地址">{{ selectedHost.ip_address || selectedHost.name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="集群">{{ selectedHost.cluster_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="CPU">{{ selectedHost.cpu_model || '-' }} · {{ selectedHost.cpu_cores || '-' }} 核</el-descriptions-item>
          <el-descriptions-item label="内存总量">{{ fmtGb(selectedHost.memory_total_mb / 1024) }}</el-descriptions-item>
          <el-descriptions-item label="存储">{{ fmtGb(selectedHost.storage_used_gb) }} / {{ fmtGb(selectedHost.storage_total_gb) }}</el-descriptions-item>
          <el-descriptions-item label="虚拟机数量">{{ selectedHost.vm_count || 0 }} 台</el-descriptions-item>
        </el-descriptions>
        <div class="drawer-metrics">
          <div v-for="metric in hostMetricCards" :key="metric.key" class="drawer-metric">
            <span>{{ metric.label }}</span>
            <strong :class="usageClass(metric.value)">{{ metric.text || fmtPct(metric.value) }}</strong>
          </div>
        </div>
        <div class="drawer-subtitle">该宿主机上的虚拟机</div>
        <el-table :data="selectedHost.vms || []" size="small" stripe>
          <el-table-column prop="name" label="名称" min-width="150" />
          <el-table-column label="状态" width="82">
            <template #default="{ row }">{{ powerText(row.power_state) }}</template>
          </el-table-column>
          <el-table-column label="CPU" width="76">
            <template #default="{ row }">{{ fmtPct(row.cpu_usage) }}</template>
          </el-table-column>
        </el-table>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { virtualizationApi } from '@/api'
import { formatDateTime } from '@/utils/time'

function preferredVmPageSize() {
  const height = typeof window === 'undefined' ? 900 : window.innerHeight
  if (height >= 1200) return 50
  if (height >= 860) return 20
  return 10
}

const loading = ref(false)
const syncingAll = ref(false)
const syncingId = ref(null)
const testingId = ref(null)
const savingPlatform = ref(false)
const activeTab = ref('vms')
const platforms = ref([])
const overview = ref({ total: 0, running: 0, stopped: 0, paused: 0, unknown: 0, hosts: 0, platforms: 0 })
const vms = ref([])
const vmTotal = ref(0)
const vmPage = ref(1)
const vmPageSizeOptions = [10, 20, 50, 100]
const vmPageSize = ref(preferredVmPageSize())
const vmPageSizeTouched = ref(false)
const hosts = ref([])
const hostTotal = ref(0)
const hostPage = ref(1)
const hostPageSize = 50
const vmTopItems = ref([])
const hostTopItems = ref([])
const topRenderKey = ref(0)
const topMetric = ref('cpu_usage')
const topLimit = ref(10)
const topPlatformId = ref(null)
const vmAlertStatus = ref('active')
const vmAlerts = ref([])
const vmAlertTotal = ref(0)
const vmAlertPage = ref(1)
const vmAlertPageSize = ref(20)
const vmAlertLoading = ref(false)
const vmAlertCounts = ref({ active: 0, unacknowledged: 0, history: 0 })
const vmAlertTableRef = ref(null)
const selectedVmAlerts = ref([])
const flashingVmAlertIds = ref([])
const platformAlertStatus = ref('active')
const platformAlerts = ref([])
const platformAlertTotal = ref(0)
const platformAlertPage = ref(1)
const platformAlertPageSize = ref(20)
const platformAlertLoading = ref(false)
const platformAlertCounts = ref({ active: 0, unacknowledged: 0, history: 0 })
const platformAlertTableRef = ref(null)
const selectedPlatformAlerts = ref([])
const flashingPlatformAlertIds = ref([])
const batchAlertSource = ref('vm')
const alertHandleVisible = ref(false)
const alertHandleSaving = ref(false)
const editingVmAlert = ref(null)
const alertHandleForm = reactive({ alert_level: 'warning', send_notification: true })
const batchAlertVisible = ref(false)
const batchAlertSaving = ref(false)
const batchAlertForm = reactive({ alert_level: '', apply_notification: false, send_notification: true })
const alertRulesVisible = ref(false)
const savingAlertRules = ref(false)
const alertRulesForm = reactive({
  cpu_enabled: true,
  cpu_threshold: 80,
  memory_enabled: true,
  memory_threshold: 85,
  disk_enabled: true,
  disk_threshold: 85,
  shutdown_enabled: true,
  platform_enabled: true,
  storage_enabled: true,
  storage_threshold: 85,
})
const filterOptions = ref({ platforms: [], hosts: [], clusters: [], guest_os: [] })
const vmFilters = reactive({
  platform_id: null, host_id: null, status: '', guest_os: '',
  min_cpu: null, min_memory: null, min_disk: null,
  min_vcpu: null, min_memory_mb: null, min_disk_gb: null, keyword: '',
})
const hostFilters = reactive({
  platform_id: null, status: '', cluster_name: '',
  min_cpu: null, min_memory: null, min_storage: null, min_vm_count: null, keyword: '',
})
const vmSort = reactive({ prop: '', order: '' })
const hostSort = reactive({ prop: '', order: '' })
const platformDialogVisible = ref(false)
const editingPlatform = ref(null)
const platformForm = reactive({
  name: '', platform_type: 'vmware', address: '', port: 443, username: '',
  password: '', project_name: '', domain_name: 'Default', verify_tls: true, enabled: true, sync_interval_minutes: 5,
})
const vmDrawerVisible = ref(false)
const selectedVm = ref(null)
const hostDrawerVisible = ref(false)
const selectedHost = ref(null)

const vmHostOptions = computed(() => {
  const platformId = vmFilters.platform_id
  return (filterOptions.value.hosts || []).filter(
    (host) => !platformId || host.platform_id === platformId
  )
})

const resourceFilterCount = computed(() => [
  vmFilters.min_vcpu, vmFilters.min_memory_mb, vmFilters.min_disk_gb,
].filter((value) => value !== null && value !== undefined && value !== '').length)

const statCards = computed(() => [
  { key: 'total', label: '虚拟机总数', value: overview.value.total, foot: `${overview.value.platforms || 0} 个平台`, tone: 'blue' },
  { key: 'running', label: '运行中', value: overview.value.running, foot: 'Powered On / Running', tone: 'green' },
  { key: 'stopped', label: '已关机', value: overview.value.stopped, foot: 'Powered Off / Shutoff', tone: 'slate' },
  { key: 'paused', label: '已暂停', value: overview.value.paused, foot: 'Suspended / Paused', tone: 'amber' },
  { key: 'hosts', label: '宿主机', value: overview.value.hosts, foot: '纳管宿主机总数', tone: 'violet' },
  { key: 'vm_alerts', label: '虚拟机未处理告警', value: overview.value.vm_alerts_unack || 0, foot: `未恢复 ${overview.value.vm_alerts_active || 0} 条`, tone: 'rose' },
])

const vmResourceCards = computed(() => selectedVm.value ? [
  {
    key: 'vcpu',
    label: 'vCPU / CPU 使用率',
    total: `${selectedVm.value.vcpu || 0} 核`,
    usageText: fmtPct(selectedVm.value.cpu_usage),
    value: selectedVm.value.cpu_usage,
    hint: 'vCPU 分配总量',
  },
  {
    key: 'memory',
    label: '内存 / 使用率',
    total: fmtMb(selectedVm.value.memory_mb),
    usageText: fmtPct(selectedVm.value.memory_usage),
    value: selectedVm.value.memory_usage,
    hint: '分配内存总量',
  },
  {
    key: 'disk',
    label: '磁盘 / 使用率',
    total: fmtGb(selectedVm.value.disk_total_gb),
    usageText: fmtPct(selectedVm.value.disk_usage),
    value: selectedVm.value.disk_usage,
    hint: `已用 ${fmtGb(selectedVm.value.disk_used_gb)}`,
  },
] : [])

const hostMetricCards = computed(() => selectedHost.value ? [
  { key: 'cpu', label: 'CPU 使用率', value: selectedHost.value.cpu_usage },
  { key: 'memory', label: '内存使用率', value: selectedHost.value.memory_usage },
  { key: 'storage', label: '存储使用率', value: selectedHost.value.storage_usage },
  { key: 'net_rx', label: '网络接收', value: null, text: fmtBps(selectedHost.value.net_rx_bps) },
  { key: 'net_tx', label: '网络发送', value: null, text: fmtBps(selectedHost.value.net_tx_bps) },
] : [])

function safePct(value) {
  const n = Number(value)
  return Number.isFinite(n) ? Math.max(0, Math.min(100, n)) : 0
}

function progressColor(value) {
  const pct = safePct(value)
  if (pct >= 90) return '#ef4444'
  if (pct >= 75) return '#f59e0b'
  return '#3b82f6'
}

function fmtPct(value) {
  const n = Number(value)
  return Number.isFinite(n) ? `${n.toFixed(1)}%` : '--'
}

function fmtMb(value) {
  const n = Number(value)
  if (!Number.isFinite(n) || n <= 0) return '-'
  return n >= 1024 ? `${(n / 1024).toFixed(1)} GB` : `${n.toFixed(0)} MB`
}

function fmtGb(value) {
  const n = Number(value)
  if (!Number.isFinite(n) || n <= 0) return '-'
  return n >= 1024 ? `${(n / 1024).toFixed(2)} TB` : `${n.toFixed(1)} GB`
}

function fmtBps(value) {
  const n = Number(value)
  if (!Number.isFinite(n) || n <= 0) return '-'
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)} Gbps`
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)} Mbps`
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)} Kbps`
  return `${n.toFixed(0)} bps`
}

function fmtDate(value) {
  if (!value) return '未同步'
  // 后端返回 UTC 朴素时间，统一按系统配置时区转换后显示。
  return formatDateTime(value)
}

function usageClass(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return 'muted'
  if (n >= 90) return 'danger'
  if (n >= 70) return 'warning'
  return 'normal'
}

function powerText(value) {
  return { running: '运行中', stopped: '已关机', paused: '已暂停', unknown: '未知' }[value] || '未知'
}

function powerTag(value) {
  return { running: 'success', stopped: 'info', paused: 'warning', unknown: 'info' }[value] || 'info'
}

function syncStatusText(value) {
  return { success: '同步正常', failed: '同步失败', never: '未同步' }[value] || '未同步'
}

function platformTypeName(type) {
  return { vmware: 'VMware vCenter', proxmox: 'Proxmox VE', cas: 'H3C CAS', kvm: 'KVM / libvirt', docker: 'Docker Engine', kubernetes: 'Kubernetes', openstack: 'OpenStack' }[type] || type
}

const connectionGuide = computed(() => {
  const guides = {
    vmware: {
      title: 'VMware vCenter',
      steps: [
        '在 vCenter 创建只读 SSO 账号，格式为 user@vsphere.local 或 user@AD域，并先确认可在 vSphere Client 登录。',
        '填写 vCenter 地址和 443 端口；自签名证书可关闭 TLS 校验。',
        '保存后点击「测试连接」，成功会返回 vCenter 版本和 API 类型。',
      ],
      note: '账号必须带 SSO 域；只填用户名时系统会自动补 @vsphere.local，无法登录时先检查账号锁定和密码。',
    },
    proxmox: {
      title: 'Proxmox VE',
      steps: [
        '准备只读用户并分配 PVEAuditor 角色，或创建 API Token；密码登录使用 root@pam。',
        '填写节点地址和 8006 端口；API Token 用户名填 user@realm!tokenid，密码填 Token Secret。',
        '自签名证书可关闭 TLS 校验，保存后点击「测试连接」验证 API2 和节点数量。',
      ],
      note: '只读账号至少需要 VM.Audit、Sys.Audit 权限；未安装 Guest Agent 时虚拟机 IP/OS 可能为空，资源指标仍可采集。',
    },
    cas: {
      title: 'H3C CAS',
      steps: [
        '准备 CAS 管理平台只读账号，确认管理地址、HTTP Digest 认证和网络可达。',
        '默认 HTTP 8080；HTTPS 可用 8443，或将管理地址填写为 https://IP。',
        '自签名证书可关闭 TLS 校验，保存后点击「测试连接」确认主机池和虚拟机接口。',
      ],
      note: 'CAS 只调用 hostpool / cluster / host / vm 查询接口，不执行开关机、删除、迁移等写操作。',
    },
    kvm: {
      title: 'KVM / libvirt',
      steps: [
        '确认目标宿主机可通过 SSH 登录，账号具有 libvirt 只读权限（通常加入 libvirt 组）。',
        '填写地址、22 端口和 SSH 账号密码；应用服务器需要能访问该 SSH 端口。',
        '保存后点击「测试连接」；如需虚拟机 IP 和 Guest OS，请在虚拟机内安装 qemu-guest-agent。',
      ],
      note: 'KVM 使用 SSH + virsh 只读命令采集，不会修改 libvirt 配置或虚拟机电源状态。',
    },
    docker: {
      title: 'Docker Engine',
      steps: [
        '在 Docker 主机启用只读远程 Engine API（默认 TCP 2375；TLS 使用 2376），或通过受控反向代理暴露 API。',
        '填写 Docker 主机地址和端口；如启用 TLS，请关闭自签名证书校验或使用受信任证书。',
        '保存后点击「测试连接」，成功会读取 Docker 版本、容器、镜像和资源信息。',
      ],
      note: '仅调用 /version、/info、/containers/json 等只读接口；不启动、停止、删除容器。无认证时用户名可填 docker。',
    },
    openstack: {
      title: 'OpenStack',
      steps: [
        '准备只读 OpenStack 用户，并确认该用户可访问 Keystone v3、Nova compute 和 Cinder volume 查询接口。',
        '填写 Keystone 地址和 5000 端口，填写用户名、密码、项目/租户；LDAP 域不是 Default 时填写认证域。',
        '保存后测试连接；同步会读取 hypervisor、server、flavor 和 volume，虚拟机实时 CPU/内存使用率取决于 Ceilometer/Gnocchi。',
      ],
      note: '只调用认证、hypervisor、server、flavor、volume 查询接口，不启动、停止、删除或迁移任何资源。',
    },
    kubernetes: {
      title: 'Kubernetes',
      steps: [
        '创建只读 ServiceAccount，并授予 nodes、pods、namespaces 的 get/list 权限。',
        '填写 API Server 地址和 6443 端口，密码栏粘贴 ServiceAccount Bearer Token。',
        '自签名集群证书可关闭 TLS 校验；保存后点击「测试连接」读取版本、节点和 Pod。',
      ],
      note: '仅调用 /version、/api/v1/nodes、/api/v1/pods 只读接口，不创建、删除或重启工作负载。',
    },
  }
  return guides[platformForm.platform_type] || guides.vmware
})

function onPlatformTypeChange(value) {
  platformForm.port = value === 'vmware' ? 443 : value === 'proxmox' ? 8006 : value === 'cas' ? 8080 : value === 'docker' ? 2375 : value === 'kubernetes' ? 6443 : value === 'openstack' ? 5000 : 22
  if (value === 'docker') { platformForm.username = platformForm.username || 'docker'; platformForm.verify_tls = false }
  if (value === 'kubernetes') { platformForm.username = 'kubernetes'; platformForm.verify_tls = true }
}

function openPlatformDialog(platform = null) {
  editingPlatform.value = platform
  Object.assign(platformForm, platform ? {
    name: platform.name, platform_type: platform.platform_type, address: platform.address,
    port: platform.port, username: platform.username, password: '', project_name: platform.project_name || '', domain_name: platform.domain_name || 'Default', verify_tls: platform.verify_tls,
    enabled: platform.enabled, sync_interval_minutes: platform.sync_interval_minutes,
  } : {
    name: '', platform_type: 'vmware', address: '', port: 443, username: '',
    password: '', project_name: '', domain_name: 'Default', verify_tls: true, enabled: true, sync_interval_minutes: 5,
  })
  platformDialogVisible.value = true
}

async function loadPlatforms() {
  const res = await virtualizationApi.platforms()
  platforms.value = res.data.items || []
}

async function loadFilters() {
  const res = await virtualizationApi.filters()
  filterOptions.value = {
    platforms: res.data.platforms || [],
    hosts: res.data.hosts || [],
    clusters: res.data.clusters || [],
    guest_os: res.data.guest_os || [],
  }
}

async function loadOverview() {
  const res = await virtualizationApi.overview()
  overview.value = res.data || overview.value
}

function onVmPlatformChange() {
  if (vmFilters.host_id && !vmHostOptions.value.some((host) => host.id === vmFilters.host_id)) {
    vmFilters.host_id = null
  }
  loadVms(1)
}

function resetVmFilters() {
  Object.assign(vmFilters, {
    platform_id: null, host_id: null, status: '', guest_os: '',
    min_cpu: null, min_memory: null, min_disk: null,
    min_vcpu: null, min_memory_mb: null, min_disk_gb: null, keyword: '',
  })
  vmSort.prop = ''
  vmSort.order = ''
  loadVms(1)
}

function resetHostFilters() {
  Object.assign(hostFilters, {
    platform_id: null, status: '', cluster_name: '',
    min_cpu: null, min_memory: null, min_storage: null, min_vm_count: null, keyword: '',
  })
  hostSort.prop = ''
  hostSort.order = ''
  loadHosts(1)
}

function onVmSortChange({ prop, order }) {
  vmSort.prop = order ? prop : ''
  vmSort.order = order === 'descending' ? 'desc' : order === 'ascending' ? 'asc' : ''
  loadVms(1)
}

function onHostSortChange({ prop, order }) {
  hostSort.prop = order ? prop : ''
  hostSort.order = order === 'descending' ? 'desc' : order === 'ascending' ? 'asc' : ''
  loadHosts(1)
}

async function loadVms(page = vmPage.value) {
  vmPage.value = page
  const res = await virtualizationApi.vms({
    platform_id: vmFilters.platform_id || undefined,
    host_id: vmFilters.host_id || undefined,
    status: vmFilters.status || undefined,
    guest_os: vmFilters.guest_os || undefined,
    min_cpu: vmFilters.min_cpu || undefined,
    min_memory: vmFilters.min_memory || undefined,
    min_disk: vmFilters.min_disk || undefined,
    min_vcpu: vmFilters.min_vcpu || undefined,
    min_memory_mb: vmFilters.min_memory_mb || undefined,
    min_disk_gb: vmFilters.min_disk_gb || undefined,
    keyword: vmFilters.keyword || undefined,
    sort_by: vmSort.prop || undefined,
    sort_order: vmSort.order || undefined,
    page: vmPage.value,
    page_size: vmPageSize.value,
  })
  vms.value = res.data.items || []
  vmTotal.value = res.data.total || 0
}

function onVmPageSizeChange(size) {
  vmPageSizeTouched.value = true
  vmPageSize.value = size
  loadVms(1)
}

function onViewportResize() {
  if (vmPageSizeTouched.value) return
  const next = preferredVmPageSize()
  if (next === vmPageSize.value) return
  vmPageSize.value = next
  loadVms(1)
}

async function loadHosts(page = hostPage.value) {
  hostPage.value = page
  const res = await virtualizationApi.hosts({
    platform_id: hostFilters.platform_id || undefined,
    status: hostFilters.status || undefined,
    cluster: hostFilters.cluster_name || undefined,
    min_cpu: hostFilters.min_cpu || undefined,
    min_memory: hostFilters.min_memory || undefined,
    min_storage: hostFilters.min_storage || undefined,
    min_vm_count: hostFilters.min_vm_count || undefined,
    keyword: hostFilters.keyword || undefined,
    sort_by: hostSort.prop || undefined,
    sort_order: hostSort.order || undefined,
    page: hostPage.value,
    page_size: hostPageSize,
  })
  hosts.value = res.data.items || []
  hostTotal.value = res.data.total || 0
}

async function loadTop() {
  const [vmRes, hostRes] = await Promise.all([
    virtualizationApi.top(topMetric.value, topLimit.value, topPlatformId.value, 'vm'),
    virtualizationApi.top(topMetric.value, topLimit.value, topPlatformId.value, 'host'),
  ])
  vmTopItems.value = vmRes.data.items || []
  hostTopItems.value = hostRes.data.items || []
  topRenderKey.value += 1
}

async function loadAlertSettings() {
  try {
    const res = await virtualizationApi.alertSettings()
    const data = res.data || {}
    Object.assign(alertRulesForm, {
      cpu_enabled: data.cpu_enabled !== false,
      cpu_threshold: Number(data.cpu_threshold) || 80,
      memory_enabled: data.memory_enabled !== false,
      memory_threshold: Number(data.memory_threshold) || 85,
      disk_enabled: data.disk_enabled !== false,
      disk_threshold: Number(data.disk_threshold) || 85,
      shutdown_enabled: data.shutdown_enabled !== false,
      platform_enabled: data.platform_enabled !== false,
      storage_enabled: data.storage_enabled !== false,
      storage_threshold: Number(data.storage_threshold) || 85,
    })
  } catch {
    /* 使用默认规则，不阻断页面 */
  }
}

async function loadVmAlerts(page = vmAlertPage.value) {
  vmAlertPage.value = page
  clearVmAlertSelection()
  vmAlertLoading.value = true
  try {
    const res = await virtualizationApi.vmAlerts({
      status: vmAlertStatus.value,
      target_type: 'vm',
      page: vmAlertPage.value,
      size: vmAlertPageSize.value,
    })
    vmAlerts.value = res.data.items || []
    vmAlertTotal.value = res.data.total || 0
    vmAlertCounts.value = res.data.counts || vmAlertCounts.value
    if (!vmAlerts.value.length && vmAlertTotal.value > 0 && vmAlertPage.value > 1) {
      vmAlertPage.value -= 1
      await loadVmAlerts(vmAlertPage.value)
      return
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '虚拟化告警加载失败')
  } finally {
    vmAlertLoading.value = false
  }
}

async function loadPlatformAlerts(page = platformAlertPage.value) {
  platformAlertPage.value = page
  clearPlatformAlertSelection()
  platformAlertLoading.value = true
  try {
    const res = await virtualizationApi.vmAlerts({
      status: platformAlertStatus.value,
      target_type: 'platform',
      page: platformAlertPage.value,
      size: platformAlertPageSize.value,
    })
    platformAlerts.value = res.data.items || []
    platformAlertTotal.value = res.data.total || 0
    platformAlertCounts.value = res.data.counts || platformAlertCounts.value
    if (!platformAlerts.value.length && platformAlertTotal.value > 0 && platformAlertPage.value > 1) {
      platformAlertPage.value -= 1
      await loadPlatformAlerts(platformAlertPage.value)
      return
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '平台告警加载失败')
  } finally {
    platformAlertLoading.value = false
  }
}

function onTabChange(name) {
  if (name === 'alerts') {
    loadAlertSettings()
    loadVmAlerts(1)
  } else if (name === 'platform-alerts') {
    loadPlatformAlerts(1)
  }
}

function openAlertRules() {
  loadAlertSettings()
  alertRulesVisible.value = true
}

async function saveAlertRules() {
  savingAlertRules.value = true
  try {
    await virtualizationApi.saveAlertSettings({ ...alertRulesForm })
    ElMessage.success('虚拟化告警规则已保存，并已重新评估')
    alertRulesVisible.value = false
    await Promise.all([loadOverview(), loadVmAlerts(1), loadPlatformAlerts(1), loadVms(1)])
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '保存虚拟化告警规则失败')
  } finally {
    savingAlertRules.value = false
  }
}

function onVmAlertSelectionChange(rows) {
  selectedVmAlerts.value = rows || []
}

function clearVmAlertSelection() {
  vmAlertTableRef.value?.clearSelection()
  selectedVmAlerts.value = []
}

function flashVmAlert(ids) {
  flashingVmAlertIds.value = [...new Set((ids || []).map(Number))]
}

function vmAlertRowClassName({ row }) {
  return flashingVmAlertIds.value.includes(Number(row.id)) ? 'vm-alert-flash-row' : ''
}

function platformAlertRowClassName({ row }) {
  return flashingPlatformAlertIds.value.includes(Number(row.id)) ? 'vm-alert-flash-row' : ''
}

function onPlatformAlertSelectionChange(rows) {
  selectedPlatformAlerts.value = rows || []
}

function clearPlatformAlertSelection() {
  platformAlertTableRef.value?.clearSelection()
  selectedPlatformAlerts.value = []
}

function flashPlatformAlert(ids) {
  flashingPlatformAlertIds.value = [...new Set((ids || []).map(Number))]
}

function openAlertHandleDialog(row) {
  editingVmAlert.value = row
  alertHandleForm.alert_level = row.alert_level || 'warning'
  alertHandleForm.send_notification = row.send_notification !== false
  alertHandleVisible.value = true
}

async function saveAlertHandle(acknowledge = false) {
  const row = editingVmAlert.value
  if (!row) return
  alertHandleSaving.value = true
  try {
    const payload = {
      alert_level: alertHandleForm.alert_level,
      send_notification: alertHandleForm.send_notification,
    }
    if (acknowledge) {
      await virtualizationApi.acknowledgeVmAlert(row.id, payload)
      ElMessage.success('虚拟化告警已确认，将保留显示直到恢复')
      alertHandleVisible.value = false
      if (row.target_type === 'platform') flashPlatformAlert([row.id])
      else flashVmAlert([row.id])
      window.setTimeout(async () => {
        flashingVmAlertIds.value = []
        flashingPlatformAlertIds.value = []
        await Promise.all([loadVmAlerts(vmAlertPage.value), loadPlatformAlerts(platformAlertPage.value), loadOverview()])
      }, 850)
      return
    }
    await virtualizationApi.updateVmAlert(row.id, payload)
    ElMessage.success('虚拟化告警设置已保存')
    alertHandleVisible.value = false
    await Promise.all([loadVmAlerts(vmAlertPage.value), loadPlatformAlerts(platformAlertPage.value), loadOverview()])
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '处理虚拟化告警失败')
  } finally {
    alertHandleSaving.value = false
  }
}

function onVmAlertPageSizeChange() {
  loadVmAlerts(1)
}

function onPlatformAlertPageSizeChange() {
  loadPlatformAlerts(1)
}

async function deleteAlertHistory(row, source = 'vm') {
  try {
    await ElMessageBox.confirm(`确定删除这条告警历史吗？删除后不可恢复。`, '删除告警历史', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
    await virtualizationApi.deleteVmAlert(row.id)
    ElMessage.success('告警历史已删除')
    await Promise.all([
      source === 'platform' ? loadPlatformAlerts(platformAlertPage.value) : loadVmAlerts(vmAlertPage.value),
      loadOverview(),
    ])
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(error?.response?.data?.detail || error.message || '删除告警历史失败')
    }
  }
}

async function batchDeleteAlerts(source = 'vm') {
  const rows = source === 'platform' ? selectedPlatformAlerts.value : selectedVmAlerts.value
  if (!rows.length) return
  try {
    await ElMessageBox.confirm(`确定批量删除选中的 ${rows.length} 条告警历史吗？删除后不可恢复。`, '批量删除告警历史', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
    const res = await virtualizationApi.bulkDeleteVmAlerts(rows.map((item) => item.id))
    ElMessage.success(res.data?.message || '告警历史已删除')
    if (source === 'platform') clearPlatformAlertSelection()
    else clearVmAlertSelection()
    await Promise.all([
      source === 'platform' ? loadPlatformAlerts(platformAlertPage.value) : loadVmAlerts(vmAlertPage.value),
      loadOverview(),
    ])
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(error?.response?.data?.detail || error.message || '批量删除告警历史失败')
    }
  }
}

function openBatchAckDialog(source = 'vm') {
  batchAlertSource.value = source
  const selected = source === 'platform' ? selectedPlatformAlerts.value : selectedVmAlerts.value
  if (!selected.length) {
    ElMessage.warning(source === 'platform' ? '请先选择需要确认的平台告警' : '请先选择需要确认的虚拟机告警')
    return
  }
  batchAlertForm.alert_level = ''
  batchAlertForm.apply_notification = false
  batchAlertForm.send_notification = true
  batchAlertVisible.value = true
}

async function submitBatchAck() {
  const source = batchAlertSource.value
  const ids = (source === 'platform' ? selectedPlatformAlerts.value : selectedVmAlerts.value).map((item) => item.id)
  if (!ids.length) {
    batchAlertVisible.value = false
    return
  }
  const payload = {}
  if (batchAlertForm.alert_level) payload.alert_level = batchAlertForm.alert_level
  if (batchAlertForm.apply_notification) payload.send_notification = batchAlertForm.send_notification
  batchAlertSaving.value = true
  try {
    const res = await virtualizationApi.bulkAcknowledgeVmAlerts(ids, payload)
    ElMessage.success(res.data?.message || `已处理 ${res.data?.updated || ids.length} 条虚拟化告警`)
    batchAlertVisible.value = false
    if (source === 'platform') clearPlatformAlertSelection()
    else clearVmAlertSelection()
    await Promise.all([loadVmAlerts(vmAlertPage.value), loadPlatformAlerts(platformAlertPage.value), loadOverview()])
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '批量确认虚拟化告警失败')
  } finally {
    batchAlertSaving.value = false
  }
}

function alertLevelText(level) {
  return { info: '提示', warning: '警告', critical: '严重', emergency: '紧急' }[level] || level || '警告'
}

function alertLevelType(level) {
  return { info: 'info', warning: 'warning', critical: 'danger', emergency: 'danger' }[level] || 'warning'
}

async function loadAll() {
  loading.value = true
  try {
    await Promise.all([
      loadPlatforms(), loadFilters(), loadOverview(), loadVms(1), loadHosts(), loadTop(),
      loadAlertSettings(), activeTab.value === 'alerts' ? loadVmAlerts(1) : activeTab.value === 'platform-alerts' ? loadPlatformAlerts(1) : Promise.resolve(),
    ])
  } catch (error) {
    ElMessage.error(error.message || '虚拟化数据加载失败')
  } finally {
    loading.value = false
  }
}

async function savePlatform() {
  if (!platformForm.name.trim() || !platformForm.address.trim() || !platformForm.username.trim()) {
    ElMessage.warning('请填写平台名称、地址和用户名')
    return
  }
  if (platformForm.platform_type === 'openstack' && !platformForm.project_name.trim()) {
    ElMessage.warning('OpenStack 必须填写项目/租户')
    return
  }
  if (!editingPlatform.value && !platformForm.password) {
    ElMessage.warning('新增平台必须填写密码')
    return
  }
  savingPlatform.value = true
  try {
    const payload = { ...platformForm }
    if (!payload.password) delete payload.password
    if (editingPlatform.value) {
      await virtualizationApi.updatePlatform(editingPlatform.value.id, payload)
      ElMessage.success('平台已更新')
    } else {
      await virtualizationApi.createPlatform(payload)
      ElMessage.success('平台已添加，可以点击测试连接')
    }
    platformDialogVisible.value = false
    await loadPlatforms()
  } catch (error) {
    ElMessage.error(error.message || '保存平台失败')
  } finally {
    savingPlatform.value = false
  }
}

async function testPlatform(platform) {
  testingId.value = platform.id
  try {
    const res = await virtualizationApi.testPlatform(platform.id)
    const detail = res.data.detail || {}
    ElMessage.success(`连接成功：${detail.hostname || detail.address || platform.address}${detail.version ? ` / ${detail.version}` : ''}`)
    await loadPlatforms()
  } catch (error) {
    ElMessage.error(error.message || '连接测试失败')
  } finally {
    testingId.value = null
  }
}

async function syncPlatform(platform) {
  syncingId.value = platform.id
  try {
    const res = await virtualizationApi.syncPlatform(platform.id)
    ElMessage.success(`同步完成：${res.data.hosts || 0} 台宿主机，${res.data.vms || 0} 台虚拟机`)
    await Promise.all([
      loadPlatforms(), loadFilters(), loadOverview(), loadVms(1), loadHosts(), loadTop(),
      activeTab.value === 'alerts' ? loadVmAlerts(1) : activeTab.value === 'platform-alerts' ? loadPlatformAlerts(1) : Promise.resolve(),
    ])
  } catch (error) {
    ElMessage.error(error.message || '同步失败')
    await loadPlatforms()
  } finally {
    syncingId.value = null
  }
}

async function syncAll() {
  syncingAll.value = true
  try {
    const res = await virtualizationApi.syncAll()
    const failed = (res.data.items || []).filter((item) => !item.ok)
    if (failed.length) ElMessage.warning(`同步完成，其中 ${failed.length} 个平台失败`)
    else ElMessage.success('所有平台同步完成')
    await Promise.all([
      loadPlatforms(), loadFilters(), loadOverview(), loadVms(1), loadHosts(), loadTop(),
      activeTab.value === 'alerts' ? loadVmAlerts(1) : activeTab.value === 'platform-alerts' ? loadPlatformAlerts(1) : Promise.resolve(),
    ])
  } catch (error) {
    ElMessage.error(error.message || '同步失败')
  } finally {
    syncingAll.value = false
  }
}

async function removePlatform(platform) {
  try {
    await ElMessageBox.confirm(`确定删除平台「${platform.name}」吗？其虚拟机与宿主机快照也会删除。`, '删除平台', { type: 'warning' })
    await virtualizationApi.deletePlatform(platform.id)
    ElMessage.success('平台已删除')
    await loadAll()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(error.message || '删除失败')
  }
}

async function openVm(row) {
  try {
    const res = await virtualizationApi.vm(row.id)
    selectedVm.value = res.data
    vmDrawerVisible.value = true
  } catch (error) {
    ElMessage.error(error.message || '虚拟机详情加载失败')
  }
}

async function openHost(row) {
  try {
    const res = await virtualizationApi.host(row.id)
    selectedHost.value = res.data
    hostDrawerVisible.value = true
  } catch (error) {
    ElMessage.error(error.message || '宿主机详情加载失败')
  }
}

onMounted(() => {
  loadAll()
  window.addEventListener('resize', onViewportResize, { passive: true })
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onViewportResize)
})
</script>

<style scoped>
.virtualization-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 4px 0 20px;
}

.hero-card,
.platform-card,
.content-card {
  border: 1px solid #e2e8f0;
  border-radius: 14px;
}

.hero-card :deep(.el-card__body) {
  padding: 22px 24px 18px;
}

.hero-main {
  display: flex;
  justify-content: space-between;
  gap: 24px;
}

.hero-kicker {
  color: #2563eb;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1.2px;
}

.hero-copy h1 {
  margin: 6px 0 6px;
  color: #0f172a;
  font-size: 25px;
}

.hero-copy p {
  margin: 0;
  color: #64748b;
  font-size: 13px;
}

.hero-actions {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  flex-shrink: 0;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
  margin-top: 22px;
}

.stat-card {
  padding: 14px 16px;
  border: 1px solid #e2e8f0;
  border-radius: 11px;
  background: #f8fafc;
}

.stat-card.blue { border-color: #bfdbfe; background: #eff6ff; }
.stat-card.green { border-color: #bbf7d0; background: #f0fdf4; }
.stat-card.slate { border-color: #cbd5e1; background: #f8fafc; }
.stat-card.amber { border-color: #fde68a; background: #fffbeb; }
.stat-card.violet { border-color: #ddd6fe; background: #faf5ff; }
.stat-card.rose { border-color: #fecdd3; background: #fff1f2; }
.stat-card.rose .stat-value { color: #be123c; }

.stat-label {
  display: block;
  color: #64748b;
  font-size: 12px;
}

.stat-value {
  display: block;
  margin: 7px 0 3px;
  color: #0f172a;
  font-size: 28px;
  line-height: 1;
}

.stat-foot {
  color: #94a3b8;
  font-size: 10px;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.section-head strong {
  display: block;
  color: #0f172a;
  font-size: 15px;
}

.section-head small {
  display: block;
  margin-top: 4px;
  color: #94a3b8;
  font-size: 11px;
}

.platform-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(410px, 1fr));
  gap: 12px;
}

.platform-item {
  padding: 14px 16px;
  border: 1px solid #e2e8f0;
  border-radius: 11px;
  background: #fff;
}

.platform-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.platform-name {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.platform-name strong {
  display: block;
  color: #0f172a;
  font-size: 14px;
}

.platform-name small {
  display: block;
  margin-top: 4px;
  overflow: hidden;
  color: #94a3b8;
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.platform-icon,
.host-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  border-radius: 9px;
  background: #eff6ff;
  color: #2563eb;
}

.platform-icon.docker { background: linear-gradient(135deg, #0ea5e9, #2563eb); }
.platform-icon.kubernetes { background: linear-gradient(135deg, #326ce5, #1d4ed8); }

.platform-icon.kvm {
  background: #f0fdf4;
  color: #16a34a;
}

.platform-icon.cas {
  background: #fff7ed;
  color: #ea580c;
}

.platform-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 12px;
  color: #64748b;
  font-size: 11px;
}

.platform-meta b {
  color: #334155;
}

.platform-ceph-health { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 7px; color: #64748b; font-size: 11px; }
.platform-ceph-health .danger { color: #d9485f; font-weight: 600; }
.platform-error {
  margin: 8px 0 0;
  color: #dc2626;
  font-size: 11px;
}

.platform-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 12px;
}

.filter-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 14px;
}

.result-count {
  margin-left: auto;
  color: #94a3b8;
  font-size: 11px;
}

.filter-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  margin-left: 4px;
  padding: 0 4px;
  border-radius: 8px;
  background: #2563eb;
  color: #fff;
  font-size: 9px;
}

.resource-filter-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.resource-filter-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: #475569;
  font-size: 12px;
}

.virtual-table {
  width: 100%;
}

.virtual-table :deep(.el-table__row) {
  cursor: pointer;
}

.vm-name-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.vm-name-cell strong {
  display: block;
  color: #0f172a;
  font-size: 12px;
}

.vm-name-cell small {
  display: block;
  margin-top: 2px;
  color: #94a3b8;
  font-size: 10px;
}

.vm-state-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  flex-shrink: 0;
  border-radius: 50%;
  background: #94a3b8;
}

.vm-state-dot.running { background: #22c55e; box-shadow: 0 0 0 3px rgba(34, 197, 94, .12); }
.vm-state-dot.stopped { background: #94a3b8; }
.vm-state-dot.paused { background: #f59e0b; }

.usage-cell {
  display: flex;
  justify-content: space-between;
  color: #64748b;
  font-size: 10px;
}

.usage-cell b {
  color: #334155;
}

.net-cell {
  color: #64748b;
  font-family: Consolas, monospace;
  font-size: 10px;
  line-height: 1.6;
}

.normal { color: #16a34a; }
.warning { color: #d97706; }
.danger { color: #dc2626; }
.muted { color: #94a3b8; }

.table-pager {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
  justify-content: flex-end;
}

.host-progress :deep(.el-progress-bar__inner) {
  transition: width .8s cubic-bezier(.22, 1, .36, 1);
  box-shadow: 0 0 10px rgba(59, 130, 246, .18);
}

.top-split {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 18px;
}
.top-section {
  min-width: 0;
  padding: 12px;
  border: 1px solid #e5eef6;
  border-radius: 10px;
  background: #fbfdff;
}
.top-section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}
.top-section-head > div { display: flex; align-items: baseline; gap: 8px; }
.top-section-head strong { color: #1e3a5f; font-size: 13px; }
.top-section-head span { color: #8ba0af; font-size: 11px; }
@media (max-width: 1180px) {
  .top-split { grid-template-columns: 1fr; }
}

.top-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.top-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 9px;
  background: linear-gradient(90deg, #f8fafc 0%, #ffffff 70%);
  transition: transform .2s ease, border-color .2s ease, box-shadow .2s ease;
}

.top-item:hover {
  border-color: #bfdbfe;
  box-shadow: 0 5px 16px rgba(37, 99, 235, .08);
  transform: translateX(2px);
}

.top-rank {
  width: 26px;
  color: #94a3b8;
  font-family: Consolas, monospace;
  font-size: 13px;
  font-weight: 700;
}

.top-rank.first { color: #d97706; }
.top-rank.second { color: #64748b; }
.top-rank.third { color: #b45309; }

.top-info {
  flex: 1;
  min-width: 0;
}

.top-name-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 6px;
}

.top-name-row strong {
  color: #0f172a;
  font-size: 12px;
}

.top-name-row span {
  overflow: hidden;
  color: #94a3b8;
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.top-bar {
  height: 7px;
  overflow: hidden;
  border-radius: 6px;
  background: linear-gradient(90deg, #e2e8f0, #f1f5f9);
}

.top-bar i {
  position: relative;
  display: block;
  width: 100%;
  height: 100%;
  overflow: hidden;
  border-radius: 6px;
  background: linear-gradient(90deg, #60a5fa, #2563eb);
  box-shadow: 0 0 10px rgba(37, 99, 235, .22);
  transform: scaleX(0);
  transform-origin: left center;
  animation: topBarGrow .9s cubic-bezier(.22, 1, .36, 1) forwards;
}

.top-bar i::after {
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, .55), transparent);
  content: '';
  transform: translateX(-120%);
  animation: topBarShimmer 2.2s ease-in-out infinite;
}

@keyframes topBarGrow {
  to { transform: scaleX(var(--target)); }
}

@keyframes topBarShimmer {
  0% { transform: translateX(-120%); }
  55%, 100% { transform: translateX(220%); }
}

.top-value {
  width: 58px;
  color: #2563eb;
  font-size: 13px;
  text-align: right;
}

.form-hint {
  margin-left: 8px;
  color: #94a3b8;
  font-size: 11px;
}

.connect-guide {
  margin: -2px 0 16px 100px;
  padding: 10px 12px;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  background: linear-gradient(135deg, #eff6ff, #f8fbff);
}

.connect-guide-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 7px;
}

.connect-guide-head span {
  color: #1d4ed8;
  font-size: 11px;
  font-weight: 700;
}

.connect-guide-head small {
  color: #64748b;
  font-size: 10px;
}

.connect-guide-steps {
  margin: 0;
  padding-left: 17px;
  color: #475569;
  font-size: 11px;
  line-height: 1.65;
}

.connect-guide-steps li::marker {
  color: #3b82f6;
  font-weight: 700;
}

.connect-guide-note {
  margin-top: 7px;
  padding-top: 7px;
  border-top: 1px dashed #bfdbfe;
  color: #64748b;
  font-size: 10px;
  line-height: 1.55;
}

.platform-dialog :deep(.el-dialog__body) {
  max-height: calc(100vh - 150px);
  overflow-y: auto;
}

.platform-dialog :deep(.el-form-item__label) {
  justify-content: flex-start;
  text-align: left;
}

.platform-dialog :deep(.el-form-item__content),
.virtualization-page :deep(.el-form-item__content) {
  min-width: 0;
  justify-content: flex-start;
  text-align: left;
}

.platform-dialog :deep(.el-input-number),
.platform-dialog :deep(.el-input-number .el-input__inner) {
  text-align: left;
}

.platform-dialog .form-hint {
  display: block;
  width: 100%;
  margin: 4px 0 0;
  line-height: 1.55;
}

.platform-dialog :deep(.el-alert) {
  margin-left: 100px;
  width: calc(100% - 100px);
  box-sizing: border-box;
}

@media (max-width: 760px) {
  .connect-guide {
    margin-left: 0;
  }
  .platform-dialog :deep(.el-alert) {
    margin-left: 0;
    width: 100%;
  }
}

.drawer-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
  color: #0f172a;
  font-size: 16px;
}

.detail-desc {
  margin-bottom: 16px;
}

.drawer-subtitle {
  margin: 18px 0 8px;
  color: #475569;
  font-size: 12px;
  font-weight: 700;
}

.drawer-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.drawer-metric {
  padding: 12px;
  border: 1px solid #e2e8f0;
  border-radius: 9px;
  background: #f8fafc;
}

.drawer-metric span {
  display: block;
  margin-bottom: 6px;
  color: #64748b;
  font-size: 10px;
}

.drawer-metric strong {
  font-size: 18px;
}

.alert-toolbar .result-count {
  margin-left: 0;
}

.alert-toolbar-actions {
  margin-left: auto;
  display: flex;
  gap: 8px;
}

.alert-rules-form {
  margin-top: 18px;
}

.alert-batch-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin: 12px 0 4px;
  padding: 10px 14px;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  background: #eff6ff;
  font-size: 13px;
}

.alert-batch-text b {
  color: #2563eb;
}

.alert-batch-tip {
  color: #64748b;
  font-size: 12px;
}

.alert-handle-form {
  margin-top: 16px;
}

.alert-handle-tip {
  width: 100%;
  margin-top: 2px;
  color: #94a3b8;
  font-size: 12px;
  line-height: 1.6;
}

.rule-threshold-label {
  margin: 0 8px;
  color: #64748b;
  font-size: 12px;
}

.rule-unit {
  margin-left: 4px;
  color: #64748b;
  font-size: 12px;
}

.threshold-text {
  color: #94a3b8;
}

.muted-text {
  color: #cbd5e1;
}

.drawer-resource-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 9px;
  margin-top: 14px;
}

.drawer-resource {
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding: 12px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #f8fafc;
}

.resource-label {
  color: #64748b;
  font-size: 10px;
}

.resource-main {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 6px;
}

.resource-main strong {
  color: #0f172a;
  font-size: 17px;
}

.resource-main b {
  font-size: 13px;
}

.drawer-resource small {
  color: #94a3b8;
  font-size: 10px;
}

@media (max-width: 1200px) {
  .stat-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .platform-list { grid-template-columns: 1fr; }
}

@media (max-width: 760px) {
  .hero-main { flex-direction: column; }
  .stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .table-pager { justify-content: center; }
  .table-pager :deep(.el-pagination__total) { display: none; }
  .top-name-row span { display: none; }
}
.vm-alert-flash-row > td {
  animation: vm-alert-flash .85s ease-in-out;
}

@keyframes vm-alert-flash {
  0%, 100% { background-color: transparent; }
  25% { background-color: rgba(250, 204, 21, .32); }
  50% { background-color: rgba(34, 197, 94, .28); }
  75% { background-color: rgba(250, 204, 21, .28); }
}
</style>
