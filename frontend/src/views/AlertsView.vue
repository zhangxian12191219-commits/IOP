<template>
  <div class="alerts-view">
    <el-card>
      <template #header>
        <div class="card-header">
          <div class="title">
            <span>{{ t('alerts.title') }}</span>
            <el-tag v-if="unackTotal > 0" type="danger" effect="dark" size="small">
              {{ activeMode ? `活动告警 ${unackTotal} 条` : t('alerts.unackCount', { count: unackTotal }) }}
            </el-tag>
            <el-tag v-if="emergencyAlertCount > 0" class="emergency-pulse-tag" type="danger" effect="dark" size="small">
              紧急 {{ emergencyAlertCount }} 条
            </el-tag>
          </div>
          <div class="actions">
            <el-dropdown @command="handleExport">
              <el-button size="small">
                <el-icon><Download /></el-icon>{{ t('alerts.export') }}
                <el-icon class="el-icon--right"><ArrowDown /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="xlsx">{{ t('alerts.exportExcel') }}</el-dropdown-item>
                  <el-dropdown-item command="csv">{{ t('alerts.exportCsv') }}</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button size="small" @click="loadAll" :loading="loading">
              <el-icon><Refresh /></el-icon>{{ t('common.refresh') }}
            </el-button>
            <el-button size="small" @click="openSuppressionRules">
              {{ t('alerts.suppressionRules') }}
            </el-button>
            <el-button size="small" @click="openHiddenAlerts">
              已抑制告警<span v-if="hiddenAlerts.length">（{{ hiddenAlerts.length }}）</span>
            </el-button>
            <el-button
              type="primary"
              size="small"
              :disabled="unackAlerts.length === 0"
              @click="ackAllUnack"
            >
              {{ t('alerts.acknowledgeAll') }}
            </el-button>
          </div>
        </div>
      </template>

      <!-- 筛选 -->
      <div class="filters">
        <el-select v-model="filters.level" :placeholder="t('alerts.allLevels')" clearable style="width: 130px" @change="onFilterChange">
          <el-option label="紧急" value="emergency" />
          <el-option :label="t('alerts.critical')" value="critical" />
          <el-option :label="t('alerts.warning')" value="warning" />
          <el-option label="提示" value="info" />
        </el-select>
        <el-select v-model="filters.type" :placeholder="t('alerts.allTypes')" clearable style="width: 130px" @change="onFilterChange">
          <el-option label="CPU" value="cpu" />
          <el-option :label="t('alerts.memory')" value="memory" />
          <el-option :label="t('alerts.temperature')" value="temperature" />
          <el-option :label="t('alerts.power')" value="power" />
          <el-option :label="t('alerts.offline')" value="offline" />
          <el-option :label="t('alerts.warrantyExpiry')" value="warranty" />
          <el-option :label="t('alerts.websiteDown')" value="down" />
          <el-option :label="t('alerts.websiteSlow')" value="slow" />
          <el-option :label="t('alerts.websiteSsl')" value="ssl_expired" />
          <el-option label="虚拟机 CPU" value="vm_cpu" />
          <el-option label="虚拟机内存" value="vm_memory" />
          <el-option label="虚拟机磁盘" value="vm_disk" />
          <el-option label="虚拟机已关机" value="vm_shutdown" />
          <el-option label="平台连接失败" value="platform_unreachable" />
          <el-option label="平台认证失败" value="platform_auth_failed" />
          <el-option label="平台同步失败" value="platform_sync_failed" />
          <el-option label="平台同步超时" value="platform_sync_stale" />
          <el-option label="平台存储告警" value="platform_storage" />
          <el-option label="Ceph 集群健康" value="platform_ceph_health" />
          <el-option label="Ceph OSD 状态" value="platform_ceph_osd" />
          <el-option label="Ceph PG 状态" value="platform_ceph_pg" />
          <el-option label="Ceph MON 仲裁" value="platform_ceph_mon" />
          <el-option label="Ceph 磁盘/设备健康" value="platform_ceph_device" />
          <el-option label="平台存储状态" value="platform_storage_health" />
          <el-option label="平台存储容量" value="platform_storage_usage" />
        </el-select>
        <el-select v-model="filters.source" :placeholder="t('alerts.allSources')" clearable style="width: 130px" @change="onFilterChange">
          <el-option :label="t('alerts.sourceDevice')" value="device" />
          <el-option :label="t('alerts.sourceWebsite')" value="website" />
          <el-option label="虚拟化" value="virtualization" />
        </el-select>
        <el-select v-model="filters.ack" :placeholder="t('alerts.allStatus')" clearable style="width: 130px" @change="onFilterChange">
          <el-option :label="t('alerts.unacknowledged')" :value="false" />
          <el-option :label="t('alerts.acknowledged')" :value="true" />
        </el-select>
        <el-select v-model="filters.days" :placeholder="t('alerts.allTime')" clearable style="width: 130px" @change="onFilterChange">
          <el-option :label="t('alerts.last1Day')" :value="1" />
          <el-option :label="t('alerts.last7Days')" :value="7" />
          <el-option :label="t('alerts.last30Days')" :value="30" />
        </el-select>
        <el-input
          v-model="filters.search"
          :placeholder="t('alerts.searchAlertPlaceholder')"
          clearable
          style="width: 260px"
          @keyup.enter="onFilterChange"
          @clear="onFilterChange"
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-button @click="onFilterChange">
          <el-icon><Search /></el-icon>{{ t('alerts.query') }}
        </el-button>
      </div>

      <div class="alert-view-mode">
        <el-checkbox v-model="activeMode" @change="onActiveModeChange">显示已确认但仍未恢复的告警</el-checkbox>
        <span>活动告警包含已确认未恢复项，与 AI 智能运维统计一致</span>
      </div>
      <el-tabs v-model="activeTab" @tab-change="onTabChange">
        <!-- 未确认 -->
        <el-tab-pane :label="activeMode ? '活动告警' : t('alerts.unacknowledged')" name="unack">
          <div v-if="selectedAlertRows.length" class="alert-selection-bar">
            <span>已选择 <b>{{ selectedAlertRows.length }}</b> 条告警</span>
            <el-button size="small" type="primary" @click="ackSelectedAlerts">批量确认</el-button>
            <el-button size="small" type="danger" :loading="batchDeleting" @click="deleteSelectedAlerts">批量删除</el-button>
            <el-button size="small" @click="clearAlertSelection">清空选择</el-button>
            <span class="alert-selection-tip">已选告警时自动刷新已暂停，清空选择后恢复；按住 Shift 点击复选框可连续选择区间</span>
          </div>
          <el-table :data="unackPageAlerts" stripe v-loading="loading" style="width: 100%" :height="tableHeight"
            :row-class-name="alertRowClassName" @row-click="onAlertRowClick" @cell-click="onAlertCellClick">
            <el-table-column width="44" fixed="left">
              <template #header>
                <el-checkbox :model-value="pageAllSelected" :indeterminate="pageSomeSelected" @change="togglePageAlertSelection" />
              </template>
              <template #default="{ row }">
                <el-checkbox :model-value="isAlertSelected(row)" @click.stop="toggleAlertSelection(row, $event)" />
              </template>
            </el-table-column>
            <el-table-column :label="t('alerts.time')" width="165">
              <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column v-if="!isCompact" :label="t('alerts.level')" width="80">
              <template #default="{ row }">
                <el-tag :type="alertLevelType(row.alert_level)" size="small" effect="dark">
                  {{ row.level_label || alertLevelText(row.alert_level) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column v-if="showAlertExtras" :label="t('alerts.type')" width="80">
              <template #default="{ row }">{{ row.alert_type_text || row.alert_type }}</template>
            </el-table-column>
            <el-table-column v-if="showAlertExtras" :label="t('alerts.source')" width="80">
              <template #default="{ row }">
                <el-tag :type="sourceTagType(row)" size="small">
                  {{ sourceLabel(row) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="message" :label="t('alerts.alertInfo')" min-width="220" show-overflow-tooltip />
            <el-table-column v-if="showAlertExtras" label="告警指标" width="130" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="alert-metric-label">{{ row.metric_label || row.alert_type_text || row.alert_type }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="t('alerts.device')" width="150" show-overflow-tooltip>
              <template #default="{ row }">
                <el-link v-if="row.device_id" type="primary" :underline="false"
                         @click="$router.push(`/devices/${row.device_id}`)">
                  {{ row.device_name || row.ip_address }}
                </el-link>
                <el-link v-else-if="row.website_target_id" type="success" :underline="false"
                         @click="$router.push(`/website/${row.website_target_id}`)">
                  {{ row.device_name || row.ip_address }}
                </el-link>
                <el-link v-else-if="row.source === 'virtualization'" type="warning" :underline="false"
                         @click="$router.push('/virtualization')">
                  {{ row.device_name || row.platform_name || '虚拟机' }}
                </el-link>
                <span v-else class="muted">-</span>
                <small v-if="!showAlertIp" class="alert-device-ip">{{ row.ip_address || '-' }}</small>
              </template>
            </el-table-column>
            <el-table-column v-if="showAlertIp" :label="t('alerts.ipAddress')" width="130">
              <template #default="{ row }">{{ row.ip_address || '-' }}</template>
            </el-table-column>
            <el-table-column v-if="showAlertExtras" :label="t('alerts.roomCabinet')" width="210" show-overflow-tooltip>
              <template #default="{ row }">
                <div v-if="row.room_name || row.cabinet_name" class="alert-room-cell">
                  <span>{{ row.room_name || '-' }} / {{ row.cabinet_name || '-' }}</span>
                  <small v-if="row.room_floor || row.room_location">楼层 {{ row.room_floor || '-' }} · 位置 {{ row.room_location || '-' }}</small>
                </div>
                <span v-else class="muted">{{ t('alerts.notRacked') }}</span>
              </template>
            </el-table-column>
            <el-table-column v-if="showAlertExtras" :label="t('alerts.uPositionCompact')" width="80">
              <template #default="{ row }">
                <span v-if="row.u_position">
                  U{{ row.u_position }}<template v-if="(row.u_height || 1) > 1">-{{ row.u_position + row.u_height - 1 }}</template>
                </span>
                <span v-else class="muted">-</span>
                <small v-if="!showAlertIp" class="alert-device-ip">{{ row.ip_address || '-' }}</small>
              </template>
            </el-table-column>
            <el-table-column v-if="!isCompact" :label="t('alerts.currentThreshold')" width="115">
              <template #default="{ row }">
                {{ fmtAlertValue(row.value, row.metric_unit) }} / {{ fmtAlertValue(row.threshold, row.metric_unit) }}
              </template>
            </el-table-column>
            <el-table-column v-if="activeMode" :label="t('alerts.status')" width="90">
              <template #default="{ row }">
                <el-tag :type="row.is_acknowledged ? 'success' : 'info'" size="small">
                  {{ row.is_acknowledged ? t('alerts.acknowledged') : t('alerts.unacknowledged') }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="t('alerts.actions')" width="300" fixed="right">
              <template #default="{ row }">
                <div class="alert-actions">
                  <el-button type="primary" link size="small" @click="openAlertDetail(row)">详情</el-button>
                  <el-button v-if="!row.is_acknowledged && !row.resolved_at" type="primary" link size="small" @click="ackAlert(row)">{{ t('alerts.acknowledge') }}</el-button>
                  <el-button type="warning" link size="small" @click="hideActiveAlert(row)">抑制</el-button>
                  <el-button v-if="row.source !== 'virtualization'" type="warning" link size="small" title="按设备/类型创建抑制规则" @click="openSuppress(row)">规则</el-button>
                  <el-button type="danger" link size="small" @click="deleteActiveAlert(row)">删除</el-button>
                </div>
              </template>
            </el-table-column>
          </el-table>
          <el-pagination
            v-model:current-page="unackPage"
            v-model:page-size="unackSize"
            @current-change="clearAlertSelection"
            :total="unackAlerts.length"
            :page-sizes="[10, 20, 50, 100]"
            layout="total, sizes, prev, pager, next"
            class="pager"
            @size-change="onUnackSizeChange"
          />
          <el-empty v-if="!loading && unackAlerts.length === 0" :description="activeMode ? '当前没有未恢复告警' : t('alerts.noUnackAlerts')" />
        </el-tab-pane>

        <!-- 全部告警 -->
        <el-tab-pane :label="t('alerts.allAlerts')" name="all">
          <div v-if="selectedAlertRows.length" class="alert-selection-bar">
            <span>已选择 <b>{{ selectedAlertRows.length }}</b> 条告警</span>
            <el-button size="small" type="primary" @click="ackSelectedAlerts">批量确认</el-button>
            <el-button size="small" type="danger" :loading="batchDeleting" @click="deleteSelectedAlerts">批量删除</el-button>
            <el-button size="small" @click="clearAlertSelection">清空选择</el-button>
            <span class="alert-selection-tip">已选告警时自动刷新已暂停，清空选择后恢复；按住 Shift 点击复选框可连续选择区间</span>
          </div>
          <el-table :data="allAlerts" stripe v-loading="loading" style="width: 100%" :height="tableHeight"
            :row-class-name="alertRowClassName" @row-click="onAlertRowClick" @cell-click="onAlertCellClick">
            <el-table-column width="44" fixed="left">
              <template #header>
                <el-checkbox :model-value="pageAllSelected" :indeterminate="pageSomeSelected" @change="togglePageAlertSelection" />
              </template>
              <template #default="{ row }">
                <el-checkbox :model-value="isAlertSelected(row)" @click.stop="toggleAlertSelection(row, $event)" />
              </template>
            </el-table-column>
            <el-table-column :label="t('alerts.time')" width="165">
              <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column v-if="!isCompact" :label="t('alerts.level')" width="80">
              <template #default="{ row }">
                <el-tag :type="alertLevelType(row.alert_level)" size="small" effect="dark">
                  {{ row.level_label || alertLevelText(row.alert_level) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column v-if="showAlertExtras" :label="t('alerts.type')" width="80">
              <template #default="{ row }">{{ row.alert_type_text || row.alert_type }}</template>
            </el-table-column>
            <el-table-column v-if="showAlertExtras" :label="t('alerts.source')" width="80">
              <template #default="{ row }">
                <el-tag :type="sourceTagType(row)" size="small">
                  {{ sourceLabel(row) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="message" :label="t('alerts.alertInfo')" min-width="220" show-overflow-tooltip />
            <el-table-column v-if="showAlertExtras" label="告警指标" width="130" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="alert-metric-label">{{ row.metric_label || row.alert_type_text || row.alert_type }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="t('alerts.device')" width="150" show-overflow-tooltip>
              <template #default="{ row }">
                <el-link v-if="row.device_id" type="primary" :underline="false"
                         @click="$router.push(`/devices/${row.device_id}`)">
                  {{ row.device_name || row.ip_address }}
                </el-link>
                <el-link v-else-if="row.website_target_id" type="success" :underline="false"
                         @click="$router.push(`/website/${row.website_target_id}`)">
                  {{ row.device_name || row.ip_address }}
                </el-link>
                <el-link v-else-if="row.source === 'virtualization'" type="warning" :underline="false"
                         @click="$router.push('/virtualization')">
                  {{ row.device_name || row.platform_name || '虚拟机' }}
                </el-link>
                <span v-else class="muted">-</span>
                <small v-if="!showAlertIp" class="alert-device-ip">{{ row.ip_address || '-' }}</small>
              </template>
            </el-table-column>
            <el-table-column v-if="showAlertIp" :label="t('alerts.ipAddress')" width="130">
              <template #default="{ row }">{{ row.ip_address || '-' }}</template>
            </el-table-column>
            <el-table-column v-if="showAlertExtras" :label="t('alerts.roomCabinet')" width="210" show-overflow-tooltip>
              <template #default="{ row }">
                <div v-if="row.room_name || row.cabinet_name" class="alert-room-cell">
                  <span>{{ row.room_name || '-' }} / {{ row.cabinet_name || '-' }}</span>
                  <small v-if="row.room_floor || row.room_location">楼层 {{ row.room_floor || '-' }} · 位置 {{ row.room_location || '-' }}</small>
                </div>
                <span v-else class="muted">{{ t('alerts.notRacked') }}</span>
              </template>
            </el-table-column>
            <el-table-column v-if="showAlertExtras" :label="t('alerts.uPositionCompact')" width="80">
              <template #default="{ row }">
                <span v-if="row.u_position">
                  U{{ row.u_position }}<template v-if="(row.u_height || 1) > 1">-{{ row.u_position + row.u_height - 1 }}</template>
                </span>
                <span v-else class="muted">-</span>
                <small v-if="!showAlertIp" class="alert-device-ip">{{ row.ip_address || '-' }}</small>
              </template>
            </el-table-column>
            <el-table-column v-if="!isCompact" :label="t('alerts.currentThreshold')" width="115">
              <template #default="{ row }">
                {{ fmtAlertValue(row.value, row.metric_unit) }} / {{ fmtAlertValue(row.threshold, row.metric_unit) }}
              </template>
            </el-table-column>
            <el-table-column :label="t('alerts.status')" width="90">
              <template #default="{ row }">
                <el-tag v-if="row.resolved_at" type="success" size="small">已恢复</el-tag>
                <el-tag v-else :type="row.is_acknowledged ? 'success' : 'info'" size="small">
                  {{ row.is_acknowledged ? t('alerts.acknowledged') : t('alerts.unacknowledged') }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="t('alerts.actions')" width="300" fixed="right">
              <template #default="{ row }">
                <div class="alert-actions">
                  <el-button type="primary" link size="small" @click="openAlertDetail(row)">详情</el-button>
                  <el-button
                    v-if="!row.is_acknowledged && !row.resolved_at"
                    type="primary"
                    link
                    size="small"
                    @click="ackAlert(row)"
                  >
                    {{ t('alerts.acknowledge') }}
                  </el-button>
                  <el-button type="warning" link size="small" @click="hideActiveAlert(row)">抑制</el-button>
                  <el-button v-if="row.source !== 'virtualization'" type="warning" link size="small" title="按设备/类型创建抑制规则" @click="openSuppress(row)">规则</el-button>
                  <el-button type="danger" link size="small" @click="deleteActiveAlert(row)">删除</el-button>
                </div>
              </template>
            </el-table-column>
          </el-table>

          <el-pagination
            v-model:current-page="page"
            v-model:page-size="size"
            @current-change="onAllPageChange"
            :total="total"
            :page-sizes="[10, 20, 50, 100]"
            layout="total, sizes, prev, pager, next"
            class="pager"
            @size-change="loadAll"
          />
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <el-dialog v-model="detailVisible" title="告警详情" width="760px" top="6vh">
      <template v-if="detailAlert">
        <div class="alert-detail-head">
          <el-tag :type="alertLevelType(detailAlert.alert_level)" size="small" effect="dark">
            {{ detailAlert.level_label || alertLevelText(detailAlert.alert_level) }}
          </el-tag>
          <el-tag :type="sourceTagType(detailAlert)" size="small">
            {{ sourceLabel(detailAlert) }}
          </el-tag>
          <el-tag v-if="detailAlert.resolved_at" type="success" size="small">已恢复</el-tag>
          <el-tag v-else :type="detailAlert.is_acknowledged ? 'info' : 'warning'" size="small">
            {{ detailAlert.is_acknowledged ? t('alerts.acknowledged') : t('alerts.unacknowledged') }}
          </el-tag>
          <span class="alert-detail-message">{{ detailAlert.message }}</span>
        </div>

        <el-alert
          v-if="probeResult"
          :title="probeResult"
          :type="probeResult.startsWith('设备在线') || probeResult.startsWith('设备已恢复') ? 'success' : 'warning'"
          :closable="true"
          show-icon
          class="alert-probe-result"
          @close="probeResult = ''"
        />

        <div v-if="detailMetric" class="alert-metric-card" :class="`level-${detailAlert.alert_level}`">
          <div class="metric-card-head">
            <div class="metric-card-title">
              <span>告警指标</span>
              <strong>{{ detailMetric.label }}</strong>
              <el-tag v-if="detailMetric.ruleName" size="small" effect="plain" type="info">
                {{ detailMetric.ruleName }}
              </el-tag>
            </div>
            <span class="metric-condition">{{ detailMetric.conditionText }}</span>
          </div>
          <div class="metric-card-body">
            <div class="metric-value-block">
              <small>触发值</small>
              <strong>{{ detailMetric.valueText }}</strong>
              <em v-if="detailMetric.unit && !detailMetric.isState">{{ detailMetric.unit }}</em>
            </div>
            <div class="metric-threshold-block">
              <small>{{ detailMetric.isState ? '判定条件' : `${detailMetric.operatorText} 阈值` }}</small>
              <strong>{{ detailMetric.thresholdText }}</strong>
            </div>
            <div v-if="detailMetric.diffText" class="metric-diff">{{ detailMetric.diffText }}</div>
          </div>
          <div v-if="detailMetric.gaugePercent !== null" class="metric-meter">
            <span class="metric-meter-threshold"></span>
            <i :style="{ width: `${detailMetric.gaugePercent}%` }"></i>
          </div>
        </div>

        <el-descriptions :column="2" border size="small" class="alert-detail-desc">
          <el-descriptions-item label="告警类型">{{ detailAlert.alert_type_text || detailAlert.alert_type }}</el-descriptions-item>
          <el-descriptions-item label="发生时间">{{ formatDateTime(detailAlert.created_at) }}</el-descriptions-item>
          <el-descriptions-item v-if="detailAlert.resolved_at" label="恢复时间">
            {{ formatDateTime(detailAlert.resolved_at) }}
          </el-descriptions-item>
          <el-descriptions-item label="设备 / 网站">
            <el-link
              v-if="detailAlert.device_id"
              type="primary"
              :underline="false"
              @click="$router.push(`/devices/${detailAlert.device_id}`)"
            >{{ detailAlert.device_name || detailAlert.ip_address }}</el-link>
            <el-link
              v-else-if="detailAlert.website_target_id"
              type="success"
              :underline="false"
              @click="$router.push(`/website/${detailAlert.website_target_id}`)"
            >{{ detailAlert.device_name || detailAlert.ip_address }}</el-link>
            <span v-else>{{ detailAlert.device_name || '-' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="IP / 域名">{{ detailAlert.ip_address || '-' }}</el-descriptions-item>
          <el-descriptions-item label="设备类型">{{ detailAlert.device_type_text || '-' }}</el-descriptions-item>
          <el-descriptions-item label="厂商 / 型号">
            {{ [detailAlert.vendor, detailAlert.model].filter(Boolean).join(' / ') || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="机房 / 机柜">
            {{ [detailAlert.room_name, detailAlert.cabinet_name].filter(Boolean).join(' / ') || '-' }}
            <template v-if="detailAlert.room_floor || detailAlert.room_location">
              · 楼层 {{ detailAlert.room_floor || '-' }} · 位置 {{ detailAlert.room_location || '-' }}
            </template>
          </el-descriptions-item>
          <el-descriptions-item label="U 位">
            <span v-if="detailAlert.u_position">
              U{{ detailAlert.u_position }}<template v-if="(detailAlert.u_height || 1) > 1">-{{ detailAlert.u_position + detailAlert.u_height - 1 }}</template>
            </span>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="告警规则">
            {{ detailAlert.rule_name || (detailAlert.rule_id ? `#${detailAlert.rule_id}` : '内置阈值') }}
          </el-descriptions-item>
          <el-descriptions-item label="指标标识">{{ detailAlert.metric_key || '-' }}</el-descriptions-item>
          <el-descriptions-item label="网站 URL" :span="2">{{ detailAlert.url || '-' }}</el-descriptions-item>
        </el-descriptions>

        <div v-if="detailAlert.details && Object.keys(detailAlert.details).length" class="alert-detail-extra">
          <strong>探测明细</strong>
          <pre>{{ JSON.stringify(detailAlert.details, null, 2) }}</pre>
        </div>
      </template>

      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
        <el-button
          v-if="detailAlert?.device_id"
          type="primary"
          plain
          :loading="probing"
          @click="probeDetailDevice"
        >再次探测</el-button>
        <el-button
          v-if="detailAlert && !detailAlert.is_acknowledged"
          type="primary"
          :loading="acking"
          @click="ackFromDetail"
        >确认告警</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="suppressVisible" :title="t('alerts.suppression')" width="560px">
      <el-alert
        v-if="suppressAlertRow"
        type="warning"
        :closable="false"
        show-icon
        :title="`${suppressAlertRow.device_name || suppressAlertRow.ip_address || '-'} · ${suppressAlertRow.alert_type_text || suppressAlertRow.alert_type} · ${suppressAlertRow.level_label || alertLevelText(suppressAlertRow.alert_level)}`"
        :description="t('alerts.suppressionHelp')"
      />
      <el-form label-width="112px" class="suppress-form">
        <el-form-item :label="t('alerts.suppressDuration')">
          <el-input-number v-model="suppressForm.duration_minutes" :min="0" :max="43200" :step="10" />
          <span class="suppress-unit">{{ t('alerts.minutes') }}</span>
          <span class="suppress-hint">{{ t('alerts.suppressZeroHint') }}</span>
        </el-form-item>
        <el-form-item :label="t('alerts.suppressReason')">
          <el-input
            v-model="suppressForm.reason"
            type="textarea"
            :rows="2"
            maxlength="500"
            show-word-limit
            :placeholder="t('alerts.suppressReasonPlaceholder')"
          />
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="suppressForm.acknowledge_current">
            {{ t('alerts.ackCurrent') }}
          </el-checkbox>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="suppressVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="warning" :loading="suppressSaving" @click="submitSuppress">
          {{ t('alerts.createSuppression') }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="hiddenVisible" title="已抑制告警" width="1040px" append-to-body>
      <div class="suppression-toolbar">
        <span class="muted">抑制单条告警后不会参与活动告警和再提醒；可在此恢复显示。</span>
        <el-button size="small" :loading="hiddenLoading" @click="loadHiddenAlerts">刷新</el-button>
      </div>
      <el-table :data="hiddenAlerts" stripe size="small" max-height="520" v-loading="hiddenLoading">
        <el-table-column :label="t('alerts.time')" width="160">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column :label="t('alerts.level')" width="80">
          <template #default="{ row }">
            <el-tag :type="alertLevelType(row.alert_level)" size="small" effect="dark">
              {{ row.level_label || alertLevelText(row.alert_level) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="90">
          <template #default="{ row }">{{ sourceLabel(row) }}</template>
        </el-table-column>
        <el-table-column :label="t('alerts.device')" width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.device_name || row.ip_address || '-' }}</template>
        </el-table-column>
        <el-table-column prop="message" :label="t('alerts.alertInfo')" min-width="260" show-overflow-tooltip />
        <el-table-column :label="t('alerts.actions')" width="100" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="restoreHiddenAlert(row)">恢复</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!hiddenLoading && hiddenAlerts.length === 0" description="当前没有被抑制的告警" :image-size="60" />
    </el-dialog>

    <el-dialog v-model="suppressionRulesVisible" :title="t('alerts.suppressionManage')" width="980px">
      <div class="suppression-toolbar">
        <span class="muted">{{ t('alerts.suppressionListHint') }}</span>
        <el-button size="small" :loading="suppressionLoading" @click="loadSuppressions">
          {{ t('common.refresh') }}
        </el-button>
      </div>
      <el-table :data="suppressions" stripe size="small" max-height="480" v-loading="suppressionLoading">
        <el-table-column prop="target_label" :label="t('alerts.suppressionTarget')" min-width="150" show-overflow-tooltip />
        <el-table-column :label="t('alerts.suppressionSource')" width="90">
          <template #default="{ row }">
            {{ row.source === 'website' ? t('alerts.sourceWebsite') : row.source === 'all' ? t('alerts.allSources') : t('alerts.sourceDevice') }}
          </template>
        </el-table-column>
        <el-table-column :label="t('alerts.suppressionType')" width="130">
          <template #default="{ row }">{{ row.alert_type || t('alerts.allTypes') }}</template>
        </el-table-column>
        <el-table-column :label="t('alerts.suppressionLevel')" width="90">
          <template #default="{ row }">{{ row.alert_level || t('alerts.allLevels') }}</template>
        </el-table-column>
        <el-table-column prop="reason" :label="t('alerts.suppressReason')" min-width="150" show-overflow-tooltip />
        <el-table-column :label="t('alerts.suppressionUntil')" width="170">
          <template #default="{ row }">{{ row.ends_at ? formatDateTime(row.ends_at) : t('alerts.suppressionPermanent') }}</template>
        </el-table-column>
        <el-table-column :label="t('alerts.suppressionStatus')" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === 'active' ? 'success' : row.status === 'expired' ? 'info' : 'warning'">
              {{ row.status === 'active' ? t('alerts.suppressionActive') : row.status === 'expired' ? t('alerts.suppressionExpired') : row.status === 'scheduled' ? t('alerts.suppressionScheduled') : t('alerts.suppressionDisabled') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('alerts.actions')" width="100" fixed="right">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="removeSuppression(row)">{{ t('common.delete') }}</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!suppressionLoading && suppressions.length === 0" :description="t('alerts.noSuppressions')" />
    </el-dialog>
  </div>
</template>

<script setup>
import { t } from '@/i18n'
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute } from 'vue-router'
import { monitorApi } from '@/api'
import { downloadWithAuth } from '@/store/auth'
import { formatDateTime } from '@/utils/time'
import { useResponsiveViewport } from '@/composables/useResponsiveViewport'

const { viewportWidth, isCompact } = useResponsiveViewport()
const showAlertExtras = computed(() => viewportWidth.value >= 2000)
const showAlertIp = computed(() => viewportWidth.value >= 1400)

const route = useRoute()
const activeTab = ref('unack')
const activeMode = ref(route.query.view === 'active')
const loading = ref(false)
const unackAlerts = ref([])
const unackTotal = ref(0)
const emergencyAlertCount = computed(() => unackAlerts.value.filter(
  (item) => !item.resolved_at && item.alert_level === 'emergency'
).length)
const allAlerts = ref([])
const page = ref(1)
const size = ref(20)
const unackPage = ref(1)
const unackSize = ref(20)
const total = ref(0)
const tableHeight = ref(520)

function updateTableHeight() {
  // 顶部栏、筛选区、页签和分页占用约 360px，剩余高度全部给告警表格
  tableHeight.value = Math.max(300, window.innerHeight - 360)
}
const unackPageAlerts = computed(() => {
  const start = (unackPage.value - 1) * unackSize.value
  return unackAlerts.value.slice(start, start + unackSize.value)
})
const detailVisible = ref(false)
const detailAlert = ref(null)
const acking = ref(false)
const probing = ref(false)
const probeResult = ref('')
let refreshTimer = null
const suppressVisible = ref(false)
const suppressAlertRow = ref(null)
const suppressSaving = ref(false)
const suppressForm = reactive({
  duration_minutes: 60,
  reason: '',
  acknowledge_current: true,
})
const suppressionRulesVisible = ref(false)
const suppressions = ref([])
const suppressionLoading = ref(false)
const hiddenVisible = ref(false)
const hiddenAlerts = ref([])
const hiddenLoading = ref(false)

const ALERT_LEVELS = ['info', 'warning', 'critical', 'emergency']
const initialLevel = String(route.query.level || '').toLowerCase()
const filters = reactive({
  level: ALERT_LEVELS.includes(initialLevel) ? initialLevel : '',
  type: '',
  source: '',
  ack: '',
  days: '',
  search: '',
})

watch(() => route.query.level, (value) => {
  const level = String(value || '').toLowerCase()
  const next = ALERT_LEVELS.includes(level) ? level : ''
  if (filters.level === next) return
  filters.level = next
  page.value = 1
  unackPage.value = 1
  clearAlertSelection()
  loadAll()
})

function fmtVal(v) {
  if (v === null || v === undefined) return '-'
  return Number(v).toFixed(1)
}

function fmtNumber(v) {
  if (v === null || v === undefined) return '-'
  const num = Number(v)
  if (Number.isNaN(num)) return '-'
  return Number.isInteger(num) ? String(num) : num.toFixed(1)
}

function fmtAlertValue(v, unit = '') {
  if (v === null || v === undefined) return '-'
  return `${fmtNumber(v)}${unit || ''}`
}

const ALERT_METRIC_FALLBACK = {
  cpu_usage: { label: 'CPU 使用率', unit: '%' },
  memory_usage: { label: '内存使用率', unit: '%' },
  temperature: { label: '温度', unit: '°C' },
  disk_usage: { label: '磁盘使用率', unit: '%' },
  cpu: { label: 'CPU 使用率', unit: '%' },
  memory: { label: '内存使用率', unit: '%' },
  power: { label: '电源状态', unit: '', state: '异常' },
  offline: { label: '设备连通性', unit: '', state: '离线' },
  warranty: { label: '维保剩余天数', unit: '天' },
  response_time: { label: '响应时间', unit: 'ms' },
  availability: { label: '网站可用性', unit: '', state: '不可达' },
  down: { label: '网站可用性', unit: '', state: '不可达' },
  ssl_expiry: { label: 'SSL 证书剩余天数', unit: '天' },
  cpu_usage: { label: 'CPU 使用率', unit: '%' },
  vm_cpu: { label: '虚拟机 CPU', unit: '%' },
  vm_memory: { label: '虚拟机内存', unit: '%' },
  vm_disk: { label: '虚拟机磁盘', unit: '%' },
  vm_shutdown: { label: '虚拟机电源状态', unit: '', state: '已关机' },
  platform_unreachable: { label: '平台连接状态', unit: '', state: '连接失败' },
  platform_auth_failed: { label: '平台认证状态', unit: '', state: '认证失败' },
  platform_sync_failed: { label: '平台同步状态', unit: '', state: '同步失败' },
  platform_sync_stale: { label: '平台同步状态', unit: '', state: '同步超时' },
  platform_storage: { label: '平台存储使用率', unit: '%' },
  platform_ceph_health: { label: 'Ceph 集群健康', unit: '' },
  platform_ceph_osd: { label: 'Ceph OSD 状态', unit: '个' },
  platform_ceph_pg: { label: 'Ceph PG 状态', unit: '个' },
  platform_ceph_mon: { label: 'Ceph MON 仲裁', unit: '个' },
  platform_ceph_device: { label: 'Ceph 设备健康', unit: '条' },
  platform_storage_health: { label: '平台存储状态', unit: '' },
  platform_storage_usage: { label: '平台存储使用率', unit: '%' },
}

const detailMetric = computed(() => {
  const alert = detailAlert.value
  if (!alert) return null
  const key = alert.metric_key || alert.alert_type || ''
  const fallback = ALERT_METRIC_FALLBACK[key] || ALERT_METRIC_FALLBACK[alert.alert_type] || {}
  const label = alert.metric_label || fallback.label || alert.alert_type_text || '告警指标'
  const unit = alert.metric_unit || fallback.unit || ''
  const isState = ['power', 'offline', 'availability', 'down'].includes(key)
  const hasValue = alert.value !== null && alert.value !== undefined && !Number.isNaN(Number(alert.value))
  const hasThreshold = alert.threshold !== null && alert.threshold !== undefined && !Number.isNaN(Number(alert.threshold))
  const operator = alert.operator || 'gt'
  const operatorText = alert.operator_text || { gt: '>', gte: '≥', lt: '<', lte: '≤', eq: '=', ne: '≠' }[operator] || '>'

  let valueText = hasValue ? fmtNumber(alert.value) : (isState ? (fallback.state || '异常') : '—')
  if (key === 'power') valueText = '异常'
  if (key === 'offline') valueText = '离线'
  if (key === 'availability' || key === 'down') valueText = '不可达'
  if (alert.resolved_at && isState) valueText = '已恢复'

  let thresholdText = hasThreshold ? fmtAlertValue(alert.threshold, unit) : (isState ? '状态异常' : '—')
  if (alert.resolved_at && isState) thresholdText = '设备已恢复在线'
  let diffText = ''
  let gaugePercent = null
  if (hasValue && hasThreshold && !isState) {
    const value = Number(alert.value)
    const threshold = Number(alert.threshold)
    const exceeded = ['gt', 'gte'].includes(operator) ? value > threshold : ['lt', 'lte'].includes(operator) ? value < threshold : false
    const diff = ['lt', 'lte'].includes(operator) ? threshold - value : value - threshold
    if (exceeded && diff >= 0) {
      const pct = threshold !== 0 ? `（${Math.abs(diff / threshold * 100).toFixed(1)}%）` : ''
      diffText = ['lt', 'lte'].includes(operator)
        ? `低于阈值 ${fmtNumber(Math.abs(diff))}${unit}${pct}`
        : `超出阈值 ${fmtNumber(diff)}${unit}${pct}`
    } else {
      diffText = '当前值未超出触发条件'
    }
    if (threshold > 0) gaugePercent = Math.max(0, Math.min(100, value / (threshold * 1.25) * 100))
  }

  return {
    key,
    label,
    unit,
    isState,
    valueText,
    thresholdText,
    diffText,
    gaugePercent,
    operatorText,
    ruleName: alert.rule_name || '',
    conditionText: alert.resolved_at && isState
      ? '设备已恢复在线'
      : (alert.condition_text || `${label} ${operatorText} ${thresholdText}`),
  }
})

function alertLevelText(level) {
  return { info: '提示', warning: '警告', critical: '严重', emergency: '紧急' }[level] || level || '警告'
}

function alertLevelType(level) {
  return { info: 'info', warning: 'warning', critical: 'danger', emergency: 'danger' }[level] || 'warning'
}

function sourceLabel(row) {
  return { website: t('alerts.sourceWebsite'), virtualization: '虚拟化' }[row?.source] || t('alerts.sourceDevice')
}

function sourceTagType(row) {
  return { website: 'success', virtualization: 'warning' }[row?.source] || 'info'
}

const selectedAlertKeys = ref([])
const batchDeleting = ref(false)
const autoRefreshPaused = computed(() => selectedAlertKeys.value.length > 0)
let lastAlertRowKey = ''

function alertSelectKey(row) {
  return `${row?.source || 'device'}:${row?.id}:${row?.created_at || ''}`
}

function alertRowClassName({ row }) {
  return row && !row.resolved_at && row.alert_level === 'emergency'
    ? 'emergency-pulse-row'
    : ''
}

function currentAlertRows() {
  return activeTab.value === 'unack' ? unackPageAlerts.value : allAlerts.value
}

const selectedAlertRows = computed(() => {
  const keys = new Set(selectedAlertKeys.value)
  return currentAlertRows().filter((row) => keys.has(alertSelectKey(row)))
})

const pageAllSelected = computed(() => {
  const rows = currentAlertRows()
  return rows.length > 0 && rows.every((row) => selectedAlertKeys.value.includes(alertSelectKey(row)))
})

const pageSomeSelected = computed(() => {
  const rows = currentAlertRows()
  const count = rows.filter((row) => selectedAlertKeys.value.includes(alertSelectKey(row))).length
  return count > 0 && count < rows.length
})

function isAlertSelected(row) {
  return selectedAlertKeys.value.includes(alertSelectKey(row))
}

function setAlertSelected(row, selected) {
  const key = alertSelectKey(row)
  const keys = new Set(selectedAlertKeys.value)
  if (selected) keys.add(key)
  else keys.delete(key)
  selectedAlertKeys.value = [...keys]
}

function toggleAlertSelection(row, event) {
  const rows = currentAlertRows()
  const index = rows.findIndex((item) => alertSelectKey(item) === alertSelectKey(row))
  const target = !isAlertSelected(row)
  if (event?.shiftKey) {
    const lastIndex = rows.findIndex((item) => alertSelectKey(item) === lastAlertRowKey)
    if (lastIndex >= 0 && index >= 0) {
      const start = Math.min(lastIndex, index)
      const end = Math.max(lastIndex, index)
      for (let i = start; i <= end; i += 1) setAlertSelected(rows[i], target)
      lastAlertRowKey = alertSelectKey(row)
      return
    }
  }
  setAlertSelected(row, target)
  lastAlertRowKey = alertSelectKey(row)
}

function onAlertRowClick(row, event) {
  if (!event.shiftKey) return
  if (event.target?.closest?.('button,a,input,.el-checkbox,.el-link')) return
  toggleAlertSelection(row, event)
}

function onAlertCellClick(row, column, cell, event) {
  // 兼容部分 Element Plus 版本只在 cell-click 上暴露 Shift 事件
  if (!event.shiftKey) return
  if (cell?.querySelector?.('button,a,input,.el-checkbox,.el-link')) return
}

function togglePageAlertSelection(checked) {
  for (const row of currentAlertRows()) setAlertSelected(row, Boolean(checked))
  lastAlertRowKey = ''
}

function clearAlertSelection() {
  selectedAlertKeys.value = []
  lastAlertRowKey = ''
}

async function ackSelectedAlerts() {
  const selected = [...selectedAlertRows.value]
  const rows = selected.filter((row) => !row.is_acknowledged && !row.resolved_at)
  if (!selected.length) return
  let ok = 0
  const removedKeys = new Set()
  for (const row of rows) {
    try {
      await monitorApi.acknowledgeAlert(row.id, row.source || 'device')
      ok += 1
      removedKeys.add(alertSelectKey(row))
    } catch {
      /* 单条失败继续 */
    }
  }
  // 活动告警视图包含“已确认但未恢复”，批量确认后如果不主动移除，
  // 重新加载会把刚确认的行再次带回列表，看起来像批量确认没有生效。
  if (activeMode.value) {
    for (const row of selected) {
      if (row.is_acknowledged || row.resolved_at) {
        removedKeys.add(alertSelectKey(row))
      }
    }
    if (removedKeys.size) {
      unackAlerts.value = unackAlerts.value.filter((row) => !removedKeys.has(alertSelectKey(row)))
      unackTotal.value = unackAlerts.value.length
      const maxPage = Math.max(1, Math.ceil(unackAlerts.value.length / unackSize.value))
      if (unackPage.value > maxPage) unackPage.value = maxPage
    }
    clearAlertSelection()
    ElMessage.success(
      rows.length
        ? `${t('alerts.acknowledgedCount', { count: ok })}；已退出“显示已确认”模式`
        : `已将 ${removedKeys.size} 条已确认告警从当前活动视图移除`
    )
    // 批量确认后退出“显示已确认”模式：确认项不再被活动查询带回列表。
    activeMode.value = false
    await loadUnack()
    return
  }
  ElMessage.success(t('alerts.acknowledgedCount', { count: ok }))
  clearAlertSelection()
  await loadAll()
}

function buildParams() {
  const params = {}
  if (filters.level) params.alert_level = filters.level
  if (filters.type) params.alert_type = filters.type
  if (filters.source) params.source = filters.source
  if (filters.days) params.days = filters.days
  if (filters.search) params.search = filters.search
  if (filters.ack === true || filters.ack === false) params.acknowledged = filters.ack
  return params
}

async function loadUnack() {
  loading.value = true
  try {
    const res = activeMode.value ? await monitorApi.getActiveAlerts() : await monitorApi.getUnackAlerts()
    let items = res.data
    if (filters.level) items = items.filter((a) => a.alert_level === filters.level)
    if (filters.type) items = items.filter((a) => a.alert_type === filters.type)
    if (filters.source) items = items.filter((a) => (a.source || 'device') === filters.source)
    if (filters.search) {
      const kw = filters.search.toLowerCase()
      items = items.filter((a) =>
        (a.message || '').toLowerCase().includes(kw) ||
        (a.device_name || '').toLowerCase().includes(kw) ||
        (a.ip_address || '').toLowerCase().includes(kw)
      )
    }
    if (filters.days) {
      const cutoff = Date.now() - Number(filters.days) * 86400000
      items = items.filter((a) => new Date(`${a.created_at}Z`).getTime() >= cutoff)
    }
    unackAlerts.value = items
    unackTotal.value = res.data.length
    window.dispatchEvent(new CustomEvent('nms:alerts-updated'))
    const maxPage = Math.max(1, Math.ceil(items.length / unackSize.value))
    if (unackPage.value > maxPage) unackPage.value = maxPage
  } catch (e) {
    ElMessage.error(e.message || t('alerts.loadUnackAlertsFailed'))
  } finally {
    loading.value = false
  }
}

async function loadAll() {
  if (activeTab.value === 'unack') {
    await loadUnack()
    return
  }
  loading.value = true
  try {
    const params = { page: page.value, size: size.value, ...buildParams() }
    const res = await monitorApi.listAlerts(params)
    allAlerts.value = res.data.items
    total.value = res.data.total
    await loadUnack()
  } catch (e) {
    ElMessage.error(e.message || t('alerts.loadAlertsFailed'))
  } finally {
    loading.value = false
  }
}

function onFilterChange() {
  page.value = 1
  unackPage.value = 1
  clearAlertSelection()
  loadAll()
}

function onUnackSizeChange() {
  unackPage.value = 1
  clearAlertSelection()
}

function onActiveModeChange() {
  unackPage.value = 1
  clearAlertSelection()
  loadUnack()
}

function onTabChange(name) {
  clearAlertSelection()
  if (name === 'all') loadAll()
  else loadUnack()
}

function onAllPageChange() {
  clearAlertSelection()
  loadAll()
}

function handleExport(format) {
  const params = new URLSearchParams(buildParams())
  params.set('format', format)
  downloadWithAuth(`/api/monitor/alerts/export?${params.toString()}`)
}

function openAlertDetail(row) {
  detailAlert.value = { ...row }
  probeResult.value = ''
  detailVisible.value = true
}

async function loadHiddenAlerts() {
  hiddenLoading.value = true
  try {
    const res = await monitorApi.getHiddenAlerts()
    hiddenAlerts.value = Array.isArray(res.data) ? res.data : []
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '加载已抑制告警失败')
  } finally {
    hiddenLoading.value = false
  }
}

async function openHiddenAlerts() {
  hiddenVisible.value = true
  await loadHiddenAlerts()
}

async function hideActiveAlert(row) {
  if (!row) return
  try {
    await ElMessageBox.confirm(
      '抑制后该告警将不再显示在活动告警中，也不会参与再提醒；可在“已抑制告警”中恢复显示。',
      '抑制告警',
      { type: 'warning', confirmButtonText: '抑制', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await monitorApi.hideAlert(row.id, row.source || 'device')
    ElMessage.success('告警已抑制，可在“已抑制告警”中恢复')
    clearAlertSelection()
    await loadAll()
    await loadHiddenAlerts()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '抑制告警失败')
  }
}

async function restoreHiddenAlert(row) {
  try {
    await monitorApi.restoreAlert(row.id, row.source || 'device')
    ElMessage.success('告警已恢复显示')
    await loadHiddenAlerts()
    await loadAll()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '恢复告警失败')
  }
}

function openSuppress(row) {
  suppressAlertRow.value = row
  suppressForm.duration_minutes = 60
  suppressForm.reason = ''
  suppressForm.acknowledge_current = true
  suppressVisible.value = true
}

async function submitSuppress() {
  if (!suppressAlertRow.value) return
  suppressSaving.value = true
  try {
    const res = await monitorApi.suppressAlert(suppressAlertRow.value.id, {
      source: suppressAlertRow.value.source || 'device',
      duration_minutes: Number(suppressForm.duration_minutes) || 0,
      reason: suppressForm.reason || '',
      acknowledge_current: suppressForm.acknowledge_current,
    })
    const count = res.data?.acknowledged || 0
    ElMessage.success(t('alerts.suppressSuccess', { count }))
    suppressVisible.value = false
    await loadAll()
    if (suppressionRulesVisible.value) await loadSuppressions()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || t('alerts.operationFailed'))
  } finally {
    suppressSaving.value = false
  }
}

async function loadSuppressions() {
  suppressionLoading.value = true
  try {
    const res = await monitorApi.getSuppressions()
    suppressions.value = res.data.items || []
  } catch (e) {
    ElMessage.error(e.message || t('alerts.loadSuppressionFailed'))
  } finally {
    suppressionLoading.value = false
  }
}

async function openSuppressionRules() {
  suppressionRulesVisible.value = true
  await loadSuppressions()
}

async function removeSuppression(row) {
  try {
    await ElMessageBox.confirm(t('alerts.deleteSuppressionConfirm'), t('common.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await monitorApi.deleteSuppression(row.id)
    ElMessage.success(t('alerts.suppressionDeleted'))
    await loadSuppressions()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || t('alerts.operationFailed'))
  }
}

async function deleteSelectedAlerts() {
  const rows = [...selectedAlertRows.value]
  if (!rows.length) return
  try {
    await ElMessageBox.confirm(
      `确定批量删除选中的 ${rows.length} 条告警吗？虚拟化告警在条件未变化时不会立即重建。`,
      '批量删除活动告警',
      { type: 'warning', confirmButtonText: '批量删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  batchDeleting.value = true
  try {
    const items = rows.map((row) => ({ id: row.id, source: row.source || 'device' }))
    const res = await monitorApi.bulkDeleteAlerts(items)
    const deleted = Number(res.data?.deleted || 0)
    const skipped = Number(res.data?.skipped || 0)
    ElMessage.success(skipped ? `已删除 ${deleted} 条，跳过 ${skipped} 条` : `已删除 ${deleted} 条告警`)
    clearAlertSelection()
    await loadAll()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '批量删除失败')
  } finally {
    batchDeleting.value = false
  }
}

async function deleteActiveAlert(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除这条告警吗？删除后当前活动列表不再显示。${row.source === 'virtualization' ? '虚拟机/平台条件未变化时不会立即重建。' : ''}`,
      '删除活动告警',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await monitorApi.deleteAlert(row.id, row.source || 'device')
    ElMessage.success('告警已删除')
    clearAlertSelection()
    await loadAll()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '删除告警失败')
  }
}

async function ackAlert(row) {
  try {
    await monitorApi.acknowledgeAlert(row.id, row.source || 'device')
    ElMessage.success(t('alerts.alertAcknowledged'))
    if (activeMode.value) {
      const key = alertSelectKey(row)
      unackAlerts.value = unackAlerts.value.filter((item) => alertSelectKey(item) !== key)
      unackTotal.value = unackAlerts.value.length
      const maxPage = Math.max(1, Math.ceil(unackAlerts.value.length / unackSize.value))
      if (unackPage.value > maxPage) unackPage.value = maxPage
    } else {
      await loadAll()
    }
    return true
  } catch (e) {
    ElMessage.error(e.message || t('alerts.operationFailed'))
    return false
  }
}

async function ackFromDetail() {
  if (!detailAlert.value) return
  acking.value = true
  try {
    const ok = await ackAlert(detailAlert.value)
    if (ok) {
      detailVisible.value = false
      detailAlert.value = null
    }
  } finally {
    acking.value = false
  }
}

async function ackAllUnack() {
  if (unackAlerts.value.length === 0) return
  let ok = 0
  for (const alert of unackAlerts.value) {
    try {
      await monitorApi.acknowledgeAlert(alert.id, alert.source || 'device')
      ok += 1
    } catch {
      /* 单条失败继续 */
    }
  }
  ElMessage.success(t('alerts.acknowledgedCount', { count: ok }))
  await loadAll()
}

async function probeDetailDevice() {
  if (!detailAlert.value?.device_id) return
  probing.value = true
  probeResult.value = ''
  try {
    const { data } = await monitorApi.probeAlert(detailAlert.value.id)
    probeResult.value = data.message || (data.alive ? '设备在线' : '设备仍不可达')
    if (data.alert) detailAlert.value = data.alert
    if (data.alive) {
      if (data.recovered) {
        ElMessage.success(`设备已恢复在线，自动关闭 ${data.recovered} 条离线告警`)
      } else {
        ElMessage.success('设备在线；当前没有待恢复的离线告警')
      }
    } else {
      ElMessage.warning(probeResult.value)
    }
    await loadAll()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '设备再次探测失败')
  } finally {
    probing.value = false
  }
}

async function refreshCurrentTab() {
  if (loading.value || document.hidden) return
  // 已有勾选时暂停自动刷新，避免刚选中/准备操作时表格被替换。
  if (autoRefreshPaused.value) return
  if (activeTab.value === 'all') await loadAll()
  else await loadUnack()
}

function onVisibilityChange() {
  if (!document.hidden) refreshCurrentTab()
}

onMounted(() => {
  updateTableHeight()
  window.addEventListener('resize', updateTableHeight, { passive: true })
  window.addEventListener('focus', onVisibilityChange)
  document.addEventListener('visibilitychange', onVisibilityChange)
  loadUnack()
  loadHiddenAlerts()
  // 告警恢复对账在接口读取时执行，缩短轮询以尽快移出已恢复告警
  refreshTimer = window.setInterval(refreshCurrentTab, 5000)
})

onBeforeUnmount(() => {
  if (refreshTimer) window.clearInterval(refreshTimer)
  refreshTimer = null
  window.removeEventListener('resize', updateTableHeight)
  window.removeEventListener('focus', onVisibilityChange)
  document.removeEventListener('visibilitychange', onVisibilityChange)
})
</script>

<style scoped>
.alert-view-mode { display: flex; align-items: center; gap: 12px; margin-bottom: 4px; color: #8496a6; font-size: 11px; }
.alert-view-mode :deep(.el-checkbox) { height: 24px; }
.alerts-view {
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
  align-items: center;
  gap: 8px;
}

.filters {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.pager {
  margin-top: 16px;
  justify-content: flex-end;
}

.muted {
  color: #c0c4cc;
}

.alert-detail-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 12px;
  margin-bottom: 12px;
  border-radius: 8px;
  background: #f7fafc;
}

.alert-probe-result {
  margin-bottom: 12px;
}

.alert-detail-message {
  flex: 1;
  min-width: 220px;
  color: #30475e;
  font-size: 12px;
  line-height: 1.5;
}

.alert-metric-card {
  --metric-accent: #f59e0b;
  margin-bottom: 12px;
  padding: 13px 15px;
  border: 1px solid #e8eef6;
  border-left: 3px solid var(--metric-accent);
  border-radius: 9px;
  background: linear-gradient(135deg, #f8fbfe, #ffffff 62%);
}

.alert-metric-card.level-info {
  --metric-accent: #38bdf8;
}

.alert-metric-card.level-warning {
  --metric-accent: #f59e0b;
}

.alert-metric-card.level-critical,
.alert-metric-card.level-emergency {
  --metric-accent: #ef4444;
}

.suppress-form {
  margin-top: 18px;
}

.suppress-unit {
  margin-left: 8px;
  color: #64748b;
}

.suppress-hint {
  margin-left: 10px;
  color: #94a3b8;
  font-size: 12px;
}

.suppression-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.metric-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.metric-card-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.metric-card-title > span {
  color: #8a9cac;
  font-size: 10px;
  letter-spacing: 0.5px;
}

.metric-card-title > strong {
  color: #203a4f;
  font-size: 15px;
  font-weight: 600;
}

.metric-condition {
  padding: 4px 8px;
  border-radius: 6px;
  color: #5d7487;
  background: #f2f7fb;
  font-family: Consolas, monospace;
  font-size: 10px;
}

.metric-card-body {
  display: flex;
  align-items: flex-end;
  gap: 26px;
  margin-top: 12px;
  flex-wrap: wrap;
}

.metric-value-block small,
.metric-threshold-block small {
  display: block;
  margin-bottom: 3px;
  color: #94a3b8;
  font-size: 10px;
}

.metric-value-block strong {
  color: var(--metric-accent);
  font-family: Rajdhani, 'DIN Alternate', Consolas, monospace;
  font-size: 32px;
  font-weight: 700;
  line-height: 1;
}

.metric-value-block em {
  margin-left: 3px;
  color: #7f95a6;
  font-family: Consolas, monospace;
  font-size: 12px;
  font-style: normal;
}

.metric-threshold-block strong {
  color: #416078;
  font-family: Consolas, monospace;
  font-size: 16px;
  font-weight: 500;
}

.metric-diff {
  margin-bottom: 3px;
  padding: 3px 8px;
  border-radius: 10px;
  color: var(--metric-accent);
  background: color-mix(in srgb, var(--metric-accent) 9%, transparent);
  font-size: 10px;
}

.metric-meter {
  position: relative;
  height: 5px;
  margin-top: 13px;
  overflow: hidden;
  border-radius: 3px;
  background: #eef3f8;
}

.metric-meter i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, color-mix(in srgb, var(--metric-accent) 55%, #fff), var(--metric-accent));
  transition: width 0.5s ease;
}

.metric-meter-threshold {
  position: absolute;
  top: -2px;
  bottom: -2px;
  left: 80%;
  z-index: 1;
  width: 1px;
  background: #94a3b8;
}

.alert-metric-label {
  color: #2f5d7a;
  font-size: 12px;
}

.alert-device-ip {
  display: block;
  margin-top: 2px;
  color: #8b9bab;
  font-family: Consolas, monospace;
  font-size: 10px;
}

.alert-detail-desc {
  margin-bottom: 12px;
}

.alert-detail-extra strong {
  display: block;
  margin-bottom: 6px;
  color: #38566b;
  font-size: 12px;
}

.alert-detail-extra pre {
  max-height: 280px;
  margin: 0;
  padding: 10px 12px;
  overflow: auto;
  border: 1px solid #e4eef6;
  border-radius: 7px;
  background: #f8fbfe;
  color: #45657b;
  font-family: Consolas, Monaco, monospace;
  font-size: 10px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-all;
}

.alert-room-cell { display: flex; flex-direction: column; align-items: center; gap: 2px; text-align: center; }
.alert-room-cell small { color: #8ba0af; font-size: 10px; }

@keyframes emergency-row-pulse {
  0%, 100% { background-color: rgba(245, 108, 108, 0.10); }
  50% { background-color: rgba(245, 108, 108, 0.30); }
}
@keyframes emergency-tag-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(245, 108, 108, 0.55); }
  50% { box-shadow: 0 0 0 6px rgba(245, 108, 108, 0); }
}
.emergency-pulse-tag { animation: emergency-tag-pulse 1.2s ease-in-out infinite; }
:deep(.el-table__row.emergency-pulse-row > td.el-table__cell) {
  animation: emergency-row-pulse 1.25s ease-in-out infinite;
}
@media (prefers-reduced-motion: reduce) {
  .emergency-pulse-tag,
  :deep(.el-table__row.emergency-pulse-row > td.el-table__cell) { animation: none; }
}
.alert-actions { position: relative; z-index: 3; display: flex; align-items: center; gap: 8px; white-space: nowrap; }
.alert-actions :deep(.el-button) { margin-left: 0; }
:deep(.el-table__fixed-right),
:deep(.el-table-fixed-column--right) {
  z-index: 12 !important;
  background: var(--el-bg-color, #fff) !important;
}
:deep(.el-table__fixed-right .el-table__cell),
:deep(.el-table-fixed-column--right .el-table__cell),
:deep(.el-table-fixed-column--right) {
  background: var(--el-bg-color, #fff) !important;
}
:deep(.el-table__fixed-right .el-table__header-wrapper),
:deep(.el-table-fixed-column--right.el-table__header-wrapper) {
  background: var(--el-fill-color-light, #f5f7fa) !important;
}
.alert-selection-bar { display: flex; align-items: center; gap: 8px; padding: 7px 10px; margin-bottom: 8px; border: 1px solid #cfe4f5; border-radius: 6px; background: #f2f9ff; color: #45647b; font-size: 12px; }
.alert-selection-bar b { color: #0f6fae; }
.alert-selection-tip { margin-left: auto; color: #8ba0af; font-size: 11px; }
</style>
