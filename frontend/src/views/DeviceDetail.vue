<template>
  <div class="device-detail">
    <el-card v-loading="loading">
      <template #header>
        <div class="card-header">
          <el-button link @click="backToAssetList">
            <el-icon><Back /></el-icon>{{ t('device.back') }}
          </el-button>
          <div class="device-title">
            <img v-if="device?.icon" :src="device.icon" class="detail-icon" alt="icon" />
            <span>{{ device?.name }}（{{ device?.ip_address }}）</span>
          </div>
          <div>
            <div class="device-nav">
              <el-button
                size="small"
                :disabled="navLoading || !prevDevice"
                :title="prevDevice ? prevDevice.name : ''"
                @click="goSibling(-1)"
              >
                <el-icon><ArrowLeft /></el-icon>上一台
              </el-button>
              <span class="device-nav-pos">{{ navPosition }}</span>
              <el-button
                size="small"
                :disabled="navLoading || !nextDevice"
                :title="nextDevice ? nextDevice.name : ''"
                @click="goSibling(1)"
              >
                下一台<el-icon><ArrowRight /></el-icon>
              </el-button>
            </div>
            <el-tag :type="statusType" size="small">{{ statusText }}</el-tag>
            <el-button type="primary" link @click="openQrcode">
              <el-icon><Postcard /></el-icon>{{ t('device.assetTag') }}
            </el-button>
            <el-button type="primary" link @click="refreshAll">
              <el-icon><Refresh /></el-icon>{{ t('common.refresh') }}
            </el-button>
            <el-button type="primary" link @click="editDeviceFromDetail">
              {{ t('device.edit') }}
            </el-button>
          </div>
        </div>
      </template>

      <!-- 关键指标卡片 -->
      <el-row :gutter="16" class="metric-cards">
        <template v-if="hasMetricsDevice">
        <el-col :span="4">
          <div class="mcard" :class="metricAlertClass('cpu_usage')">
            <div class="mcard-label">CPU</div>
            <div class="mcard-value" :class="levelClass(metric?.cpu_usage, metricThresholds.cpu_usage + 10, metricThresholds.cpu_usage)">
              {{ fmt(metric?.cpu_usage, '%') }}
            </div>
            <div class="mcard-sub">{{ cpuDetail || '整机 CPU 使用率' }}</div>
          </div>
        </el-col>
        <el-col :span="4">
          <div class="mcard" :class="metricAlertClass('memory_usage')">
            <div class="mcard-label">{{ t('device.memory') }}</div>
            <div class="mcard-value" :class="levelClass(metric?.memory_usage, metricThresholds.memory_usage + 10, metricThresholds.memory_usage)">
              {{ fmt(metric?.memory_usage, '%') }}
            </div>
            <div class="mcard-sub">
              {{ metric?.memory_used ? metric.memory_used.toFixed(0) : '-' }} /
              {{ metric?.memory_total ? metric.memory_total.toFixed(0) : '-' }} MB
            </div>
            <div v-if="memoryModuleDetail" class="mcard-sub">{{ memoryModuleDetail }}</div>
          </div>
        </el-col>
        <el-col :span="4">
          <div class="mcard" :class="metricAlertClass('temperature')">
            <div class="mcard-label">最高部件温度</div>
            <div class="mcard-value" :class="levelClass(metric?.temperature, metricThresholds.temperature_critical, metricThresholds.temperature)">
              {{ fmt(metric?.temperature, '°C') }}
            </div>
            <div v-if="temperatureDetail" class="mcard-sub">{{ temperatureDetail }}</div>
          </div>
        </el-col>
        <el-col :span="4">
          <div class="mcard" :class="metricAlertClass('power')">
            <div class="mcard-label">{{ t('device.powerStatus') }}</div>
            <div class="mcard-value">
              <el-tag :type="powerTag" size="small">{{ powerText }}</el-tag>
            </div>
          </div>
        </el-col>
        <el-col :span="4">
          <div class="mcard">
            <div class="mcard-label">{{ t('device.uptime') }}</div>
            <div class="mcard-value small">{{ uptimeText }}</div>
          </div>
        </el-col>
        <el-col :span="4">
          <div class="mcard">
            <div class="mcard-label">{{ t('device.interfacesOnline') }}</div>
            <div class="mcard-value" :title="`接口总数 ${interfaces.length}，在线 ${upCount}`">{{ interfaces.length }} / {{ upCount }}</div>
            <div class="mcard-sub">接口总数 / 在线数</div>
          </div>
        </el-col>
        </template>
        <template v-else>
          <el-col :span="6">
            <div class="mcard">
              <div class="mcard-label">监控方式</div>
              <div class="mcard-value small">{{ monitorTypeText }}</div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="mcard">
              <div class="mcard-label">探测结果</div>
              <div class="mcard-value">
                <el-tag :type="probeAlive === 1 ? 'success' : probeAlive === 0 ? 'danger' : 'info'" size="small">
                  {{ probeAlive === 1 ? '在线' : probeAlive === 0 ? '离线' : '待探测' }}
                </el-tag>
              </div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="mcard">
              <div class="mcard-label">探测延迟</div>
              <div class="mcard-value">{{ probeLatency === null ? '-' : `${probeLatency} ms` }}</div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="mcard">
              <div class="mcard-label">{{ monitorType === 'tcp' ? 'TCP 端口' : '探测地址' }}</div>
              <div class="mcard-value small">{{ monitorType === 'tcp' ? `${device?.ip_address}:${device?.tcp_port || 80}` : device?.ip_address }}</div>
            </div>
          </el-col>
        </template>
      </el-row>

      <!-- 时间范围筛选：作用于历史曲线、告警与维保记录 -->
      <div v-if="['alerts', 'maintenance', 'custom'].includes(activeTab)" class="time-filter">
        <span class="time-filter-label">{{ t('device.timeRange') }}</span>
        <el-button-group>
          <el-button
            v-for="item in TIME_PRESETS"
            :key="item.value"
            size="small"
            :type="isPresetActive(item.value) ? 'primary' : 'default'"
            @click="setPreset(item.value)"
          >
            {{ t(item.labelKey) }}
          </el-button>
        </el-button-group>
        <el-date-picker
          v-model="customRange"
          type="datetimerange"
          size="small"
          :start-placeholder="t('device.startTime')"
          :end-placeholder="t('device.endTime')"
          :clearable="true"
          style="width: 360px"
          @change="onCustomRangeChange"
        />
        <el-button size="small" @click="resetTimeRange">{{ t('device.resetRange') }}</el-button>
        <el-tag v-if="rangeMode === 'custom'" size="small" type="warning" effect="plain">
          {{ rangeText }}
        </el-tag>
        <span class="time-filter-hint">{{ t('device.timeRangeHint') }}</span>
      </div>

      <el-tabs v-model="activeTab" @tab-change="onTabChange">
        <el-tab-pane :label="t('device.basicInfo')" name="info">
          <el-descriptions :column="3" border>
            <el-descriptions-item :label="t('device.deviceName')">{{ device?.name }}</el-descriptions-item>
            <el-descriptions-item :label="t('device.source')">
              <el-tag v-if="device?.source === 'auto'" type="warning" size="small" effect="plain">
                {{ t('device.sourceAuto') }}
              </el-tag>
              <span v-else>{{ t('device.sourceManual') }}</span>
              <span v-if="device?.discovered_at" class="muted" style="margin-left: 6px">
                {{ formatDateTime(device.discovered_at) }}
              </span>
            </el-descriptions-item>
            <el-descriptions-item :label="t('device.ipAddress')">{{ device?.ip_address }}</el-descriptions-item>
            <el-descriptions-item :label="t('device.deviceType')">{{ getTypeName(device?.device_type) }}</el-descriptions-item>
            <el-descriptions-item label="资产群组">{{ device?.group_name || '-' }}</el-descriptions-item>
            <el-descriptions-item label="监控状态">
              <el-tag size="small" :type="device?.is_enabled ? 'success' : 'info'" effect="plain">{{ device?.is_enabled ? '已启用' : '已停用' }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item :label="t('device.vendor')">{{ device?.vendor || '-' }}</el-descriptions-item>
            <el-descriptions-item :label="t('device.model')">{{ device?.model || '-' }}</el-descriptions-item>
            <el-descriptions-item :label="t('device.serialNumber')">{{ device?.serial_number || '-' }}</el-descriptions-item>
            <el-descriptions-item :label="t('device.roomCabinet')">
              <template v-if="device?.cabinet">
                {{ device.cabinet.room_name || t('device.room') }} / {{ device.cabinet.name }}
              </template>
              <span v-else>-</span>
            </el-descriptions-item>
            <el-descriptions-item :label="t('device.uPosition')">
              <template v-if="device?.u_position">
                U{{ device.u_position }}<template v-if="(device.u_height || 1) > 1">-{{ device.u_position + device.u_height - 1 }}</template>
                （{{ device.u_height || 1 }}U）
              </template>
              <span v-else>-</span>
            </el-descriptions-item>
            <el-descriptions-item :label="t('device.ratedPower')">
              {{ device?.power_watts ? device.power_watts + ' W' : '-' }}
            </el-descriptions-item>
            <el-descriptions-item label="接入方式">
              <el-tag size="small" :type="monitorType === 'snmp' ? 'info' : (monitorType === 'api' ? 'warning' : 'success')">{{ monitorTypeText }}</el-tag>
            </el-descriptions-item>
            <template v-if="isSnmpDevice">
              <el-descriptions-item :label="t('device.snmpVersion')">{{ device?.snmp_version || '-' }}</el-descriptions-item>
              <el-descriptions-item label="SNMP 端口">{{ device?.port || 161 }}</el-descriptions-item>
              <template v-if="isSnmpV3">
                <el-descriptions-item label="用户名（安全名）">{{ device?.v3_username || '-' }}</el-descriptions-item>
                <el-descriptions-item label="认证密码">
                  <el-tag size="small" effect="plain" :type="device?.v3_auth_password_set ? 'success' : 'info'">
                    {{ device?.v3_auth_password_set ? '已设置' : '未设置' }}
                  </el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="加密密码">
                  <el-tag size="small" effect="plain" :type="device?.v3_priv_password_set ? 'success' : 'info'">
                    {{ device?.v3_priv_password_set ? '已设置' : '未设置' }}
                  </el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="认证协议">{{ device?.v3_auth_protocol || '-' }}</el-descriptions-item>
                <el-descriptions-item label="加密协议">{{ device?.v3_priv_protocol || '-' }}</el-descriptions-item>
                <el-descriptions-item label="安全级别">{{ v3SecurityLevelText }}</el-descriptions-item>
                <el-descriptions-item label="Context Name">{{ device?.v3_context_name || '-' }}</el-descriptions-item>
              </template>
              <el-descriptions-item v-else label="团体名">
                <span class="secret-value">{{ communityVisible ? (device?.community || '-') : '••••••••' }}</span>
                <el-button
                  class="secret-toggle"
                  link
                  size="small"
                  :title="communityVisible ? '隐藏团体名' : '显示团体名'"
                  @click="communityVisible = !communityVisible"
                >
                  <el-icon><Hide v-if="communityVisible" /><View v-else /></el-icon>
                </el-button>
              </el-descriptions-item>
            </template>
            <template v-else-if="isApiDevice">
              <el-descriptions-item label="API 地址">{{ device?.ip_address }}:{{ device?.storage_api_port || 443 }}</el-descriptions-item>
              <el-descriptions-item label="API 认证">{{ device?.api_auth_type || 'auto' }}</el-descriptions-item>
              <el-descriptions-item label="API 基础路径">{{ device?.api_base_path || '按厂商自动探测' }}</el-descriptions-item>
              <el-descriptions-item label="监控说明">统一 API 只读采集，不依赖 MIB</el-descriptions-item>
            </template>
            <template v-else-if="isIpmiDevice">
              <el-descriptions-item label="IPMI 地址">{{ device?.ip_address }}:{{ device?.ipmi_port || 623 }}</el-descriptions-item>
              <el-descriptions-item label="IPMI 协议">{{ device?.ipmi_protocol || 'auto' }}</el-descriptions-item>
              <el-descriptions-item label="IPMI 用户名">{{ device?.ipmi_username || '-' }}</el-descriptions-item>
              <el-descriptions-item label="监控说明">IPMI 只读采集，支持 RMCP / RMCP+</el-descriptions-item>
            </template>
            <template v-else>
              <el-descriptions-item label="探测目标">{{ device?.ip_address }}<template v-if="monitorType === 'tcp'">:{{ device?.tcp_port || 80 }}</template></el-descriptions-item>
              <el-descriptions-item label="监控说明">{{ monitorType === 'tcp' ? '仅监控 TCP 端口连通性' : '仅监控 ICMP 连通性' }}</el-descriptions-item>
            </template>
            <el-descriptions-item :label="t('device.description')" :span="3">{{ device?.description || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('device.assetNo')">{{ device?.asset_no || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('device.purchaseDate')">{{ device?.purchase_date || '-' }}</el-descriptions-item>
          <el-descriptions-item label="维保开始时间">{{ device?.warranty_start || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('device.maintenanceExpiry')">
            <span>{{ device?.warranty_until || '-' }}</span>
            <el-tag v-if="warrantyTag" :type="warrantyTag.type" size="small" class="warranty-tag">
              {{ warrantyTag.text }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('device.maintenanceVendor')">{{ device?.maintenance_vendor || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('device.maintenanceContact')">{{ device?.maintenance_contact || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('device.maintenancePhone')">{{ device?.maintenance_phone || '-' }}</el-descriptions-item>
          </el-descriptions>
        </el-tab-pane>

        <el-tab-pane v-if="hasMetricsDevice" label="CPU" name="cpu">
          <div class="time-filter">
            <span class="time-filter-label">{{ t('device.timeRange') }}</span>
            <el-button-group>
              <el-button v-for="item in TIME_PRESETS" :key="item.value" size="small" :type="isChartPresetActive('cpu', item.value) ? 'primary' : 'default'" @click="setChartPreset('cpu', item.value)">{{ t(item.labelKey) }}</el-button>
            </el-button-group>
            <el-date-picker v-model="chartRanges.cpu.custom" type="datetimerange" size="small" :start-placeholder="t('device.startTime')" :end-placeholder="t('device.endTime')" :clearable="true" style="width: 320px" @change="onChartCustomRangeChange('cpu', $event)" />
            <el-button size="small" @click="resetChartRange('cpu')">{{ t('device.resetRange') }}</el-button>
            <el-tag v-if="chartRanges.cpu.mode === 'custom'" size="small" type="warning" effect="plain">{{ chartRangeText('cpu') }}</el-tag>
          </div>
          <div ref="cpuChartRef" class="chart"></div>
        </el-tab-pane>

        <el-tab-pane v-if="hasMetricsDevice" :label="t('device.memory')" name="memory">
          <div class="time-filter">
            <span class="time-filter-label">{{ t('device.timeRange') }}</span>
            <el-button-group>
              <el-button v-for="item in TIME_PRESETS" :key="item.value" size="small" :type="isChartPresetActive('memory', item.value) ? 'primary' : 'default'" @click="setChartPreset('memory', item.value)">{{ t(item.labelKey) }}</el-button>
            </el-button-group>
            <el-date-picker v-model="chartRanges.memory.custom" type="datetimerange" size="small" :start-placeholder="t('device.startTime')" :end-placeholder="t('device.endTime')" :clearable="true" style="width: 320px" @change="onChartCustomRangeChange('memory', $event)" />
            <el-button size="small" @click="resetChartRange('memory')">{{ t('device.resetRange') }}</el-button>
            <el-tag v-if="chartRanges.memory.mode === 'custom'" size="small" type="warning" effect="plain">{{ chartRangeText('memory') }}</el-tag>
          </div>
          <div ref="memoryChartRef" class="chart"></div>
        </el-tab-pane>

        <el-tab-pane v-if="hasMetricsDevice" :label="t('device.maxTemperature')" name="temperature">
          <div class="time-filter">
            <span class="time-filter-label">{{ t('device.timeRange') }}</span>
            <el-button-group>
              <el-button v-for="item in TIME_PRESETS" :key="item.value" size="small" :type="isChartPresetActive('temperature', item.value) ? 'primary' : 'default'" @click="setChartPreset('temperature', item.value)">{{ t(item.labelKey) }}</el-button>
            </el-button-group>
            <el-date-picker v-model="chartRanges.temperature.custom" type="datetimerange" size="small" :start-placeholder="t('device.startTime')" :end-placeholder="t('device.endTime')" :clearable="true" style="width: 320px" @change="onChartCustomRangeChange('temperature', $event)" />
            <el-button size="small" @click="resetChartRange('temperature')">{{ t('device.resetRange') }}</el-button>
            <el-tag v-if="chartRanges.temperature.mode === 'custom'" size="small" type="warning" effect="plain">{{ chartRangeText('temperature') }}</el-tag>
          </div>
          <div ref="tempChartRef" class="chart"></div>
        </el-tab-pane>

        <el-tab-pane v-if="hasMetricsDevice" label="硬件信息" name="hardware">
      <div v-if="hasMetricsDevice" class="hardware-strip">
        <div class="hardware-item" :class="metricAlertClass('disk_usage')">
          <div class="hardware-label">磁盘容量</div>
          <div class="hardware-value">{{ hardwareInfo.diskCapacity }}</div>
          <div class="hardware-sub">{{ hardwareInfo.diskUsage }}</div>
        </div>
        <div class="hardware-item" :class="metricAlertClass('fan_speed')">
          <div class="hardware-label">风扇转速</div>
          <div class="hardware-value">{{ hardwareInfo.fanSpeed }}</div>
          <div class="hardware-sub">{{ hardwareInfo.fanSub }}</div>
        </div>
        <div class="hardware-item" :class="metricAlertClass('power')">
          <div class="hardware-label">电源信息</div>
          <div class="hardware-value">{{ hardwareInfo.powerLabel }}</div>
          <div class="hardware-sub">{{ hardwareInfo.powerSub }}</div>
        </div>
        <div class="hardware-item hardware-note">
          <div class="hardware-label">数据来源</div>
          <div class="hardware-sub">SNMP 实时采集；设备或型号不支持的项目显示“未采集”，可在 MIB 管理中补充厂商私有 OID。</div>
        </div>
      </div>

        <div v-if="hasMetricsDevice && hasServerComponents" class="server-components-panel">
          <div class="server-components-head">
            <div>
              <strong>硬件组件明细</strong>
              <span>按实体组件展示电源、风扇、硬盘、温度等硬件状态</span>
            </div>
            <el-tag size="small" type="info" effect="plain">{{ serverComponents.vendor || 'SNMP' }}</el-tag>
          </div>
          <div class="server-component-grid">
            <section v-if="serverComponents.cpus?.length" class="server-component-card">
              <h4>CPU <small>{{ serverComponents.cpus.length }} 颗</small></h4>
              <div v-for="cpu in serverComponents.cpus" :key="`cpu-${cpu.index}`" class="component-row">
                <div class="component-main">
                  <b>{{ cpu.name }}</b>
                  <span>{{ cpu.model || '型号未提供' }}</span>
                </div>
                <em>{{ cpu.cores ? `${cpu.cores} 核 / ${cpu.threads || '-'} 线程` : (cpu.status_label || '状态未知') }}</em>
              </div>
            </section>
            <section v-if="serverComponents.memory_modules?.length" class="server-component-card">
              <h4>内存 <small>{{ serverComponents.memory_modules.length }} 条 · {{ serverComponents.summary?.memory_total_gb || 0 }} GB</small></h4>
              <div v-for="mem in serverComponents.memory_modules" :key="`mem-${mem.index}`" class="component-row">
                <div class="component-main">
                  <b>{{ mem.name }}</b>
                  <span>内存通道 {{ mem.bank || '-' }}</span>
                </div>
                <em>{{ mem.size_gb }} GB</em>
              </div>
            </section>
            <section v-if="serverComponents.temperatures?.length" class="server-component-card">
              <h4>温度探头 <small>{{ serverComponents.temperatures.length }} 个 · 明确区分 CPU/主板/进风/排风</small></h4>
              <div v-for="temp in serverComponents.temperatures" :key="`temp-${temp.index}`" class="component-row">
                <div class="component-main">
                  <b>{{ temperatureDisplayName(temp.name) }}</b>
                  <span class="component-kind">{{ temperatureKindLabel(temp.kind) }}</span>
                </div>
                <em :class="temp.value >= 90 ? 'component-bad' : temp.value >= 80 ? 'component-warn' : ''">{{ temp.value }} {{ temp.unit }}</em>
              </div>
            </section>
            <section v-if="serverComponents.fans?.length" class="server-component-card">
              <h4>风扇 <small>{{ serverComponents.fans.length }} 个</small></h4>
              <div v-for="fan in serverComponents.fans" :key="`fan-${fan.index}`" class="component-row">
                <div class="component-main">
                  <b>{{ fan.name }}</b>
                  <span>{{ fan.status_label || '转速' }}<template v-if="fan.percent != null"> · {{ fan.percent }}%</template></span>
                </div>
                <em>{{ fan.value }} {{ fan.unit }}</em>
              </div>
            </section>
            <section v-if="serverComponents.power_supplies?.length" class="server-component-card">
              <h4>电源 <small>{{ serverComponents.power_supplies.length }} 个</small></h4>
              <div v-for="psu in serverComponents.power_supplies" :key="`psu-${psu.index}`" class="component-row">
                <div class="component-main">
                  <b>{{ psu.name }}</b>
                  <span>{{ psu.status_label || '状态未知' }}<template v-if="psu.model"> · {{ psu.model }}</template><template v-if="psu.rating_watts"> · 额定 {{ psu.rating_watts }} W</template></span>
                </div>
                <em>{{ psu.watts != null ? `${psu.watts} W` : '功率未采集' }}</em>
              </div>
            </section>
            <section v-if="serverComponents.disks?.length" class="server-component-card">
              <h4>硬盘 <small>{{ serverComponents.disks.length }} 块<template v-if="serverComponents.summary?.disk_total_gb"> · {{ serverComponents.summary.disk_total_gb }} GB</template></small></h4>
              <div v-for="disk in serverComponents.disks" :key="`disk-${disk.index}`" class="component-row">
                <div class="component-main"><b>{{ disk.name }}</b><span>{{ disk.model || '型号未提供' }} · {{ disk.status_label || '状态未知' }}</span></div>
                <em>{{ disk.size_gb != null ? `${disk.size_gb} GB` : '容量未提供' }}</em>
              </div>
            </section>
          </div>
        </div>

        </el-tab-pane>

        <el-tab-pane v-if="hasMetricsDevice" :label="t('device.customMetrics')" name="custom">
          <div class="custom-metric-toolbar">
            <div>
              <strong>自定义指标</strong>
              <span>通过任意 SNMP OID 采集光功率、风扇、硬盘健康等指标，数值会自动记录到历史中</span>
            </div>
            <div class="custom-toolbar-actions">
              <el-button v-if="can('monitor:edit')" size="small" :loading="customCollecting" @click="collectCustomNow">
                <el-icon><Refresh /></el-icon>立即采集
              </el-button>
              <el-button v-if="can('assets:edit')" type="primary" size="small" @click="openCustomConfig">
                <el-icon><Setting /></el-icon>配置指标
              </el-button>
            </div>
          </div>
          <div v-if="customMetricDefs.length" class="custom-metric-cards">
            <div v-for="m in customMetricDefs" :key="m.key" class="cm-card">
              <div class="cm-name">{{ m.name || m.key }}</div>
              <div class="cm-value">
                {{ currentCustomValue(m.key) }}
                <small v-if="m.unit">{{ m.unit }}</small>
              </div>
              <div class="cm-oid">{{ m.oid }}</div>
            </div>
          </div>
          <el-empty v-else :description="t('device.noCustomMetrics')">
            <el-button v-if="can('assets:edit')" type="primary" size="small" @click="openCustomConfig">
              <el-icon><Setting /></el-icon>配置第一个自定义指标
            </el-button>
          </el-empty>

          <template v-if="customMetricDefs.length">
            <div class="custom-chart-head">
              <span>{{ t('device.customMetricHistory') }}</span>
              <el-select
                v-model="selectedCustomKey"
                size="small"
                style="width: 240px"
                @change="renderCustomChart"
              >
                <el-option
                  v-for="m in customMetricDefs"
                  :key="m.key"
                  :label="m.name || m.key"
                  :value="m.key"
                />
              </el-select>
            </div>
            <div ref="customChartRef" class="chart"></div>
          </template>
        </el-tab-pane>

        <el-tab-pane v-if="isSnmpDevice || isApiDevice" :label="t('device.interfacesTraffic')" name="interfaces">
          <el-alert
            v-if="isApiDevice && !interfaces.length"
            type="info"
            :closable="false"
            show-icon
            title="正在通过设备 API 获取接口信息"
            description="API 设备通常只提供端口状态、速率和描述；流量计数取决于厂商 API 是否返回端口统计。"
            style="margin-bottom: 12px"
          >
            <el-button size="small" type="primary" plain :loading="apiIfLoading" @click="loadApiInterfaces">立即获取接口</el-button>
          </el-alert>
          <!-- 概览 -->
          <div class="if-summary">
            <div class="if-stat">
              <span class="if-k">{{ t('device.totalInterfaces') }}</span>
              <b>{{ interfaces.length }}</b>
            </div>
            <div class="if-stat up">
              <span class="if-k">UP</span>
              <b>{{ ifSummary.up }}</b>
            </div>
            <div class="if-stat down">
              <span class="if-k">DOWN</span>
              <b>{{ ifSummary.down }}</b>
            </div>
            <div class="if-stat">
              <span class="if-k">{{ t('device.availability') }}</span>
              <b>{{ ifSummary.available }}%</b>
            </div>
            <div class="if-stat">
              <span class="if-k">{{ t('device.totalRate') }}</span>
              <b>{{ bpsText(ifSummary.totalBps) }}</b>
            </div>
            <div class="if-actions">
              <el-radio-group v-model="ifFilter" size="small">
                <el-radio-button value="all">{{ t('device.all') }}</el-radio-button>
                <el-radio-button value="up">{{ t('device.upOnly') }}</el-radio-button>
                <el-radio-button value="down">{{ t('device.downOnly') }}</el-radio-button>
              </el-radio-group>
              <el-select v-model="ifUtilFilter" size="small" style="width: 128px" @change="ifPage = 1">
                <el-option label="全部利用率" value="all" />
                <el-option label="利用率 ≥ 50%" value="50" />
                <el-option label="利用率 ≥ 80%" value="80" />
                <el-option label="利用率 ≥ 90%" value="90" />
              </el-select>
              <el-input
                v-model="ifKeyword"
                size="small"
                :placeholder="t('device.searchInterfacePlaceholder')"
                clearable
                style="width: 200px"
              />
              <el-select
                v-model="ifSortKey"
                size="small"
                class="if-sort-select"
                :placeholder="t('device.sortBy')"
                @change="saveIfSort"
              >
                <el-option :label="t('device.sortIndex')" value="index" />
                <el-option :label="t('device.sortName')" value="name" />
                <el-option :label="t('device.sortIn')" value="in_bps" />
                <el-option :label="t('device.sortOut')" value="out_bps" />
                <el-option :label="t('device.sortTotal')" value="total_bps" />
                <el-option :label="t('device.sortUtil')" value="util" />
              </el-select>
              <el-button size="small" @click="toggleIfSortOrder">
                {{ ifSortOrder === 'asc' ? t('device.sortAsc') : t('device.sortDesc') }}
                <span class="sort-arrow">{{ ifSortOrder === 'asc' ? '↑' : '↓' }}</span>
              </el-button>
            </div>
          </div>
          <div class="if-hint">{{ t('device.clickInterfaceHint') }}</div>

          <!-- 所有接口卡片：UP/DOWN 状态 + 实时流量 + 利用率 -->
          <div class="if-grid">
            <div
              v-for="row in pagedInterfaces"
              :key="row.id"
              class="if-card"
              :class="row.oper_status === 'up' ? 'is-up' : 'is-down'"
              :title="t('device.clickInterfaceHint')"
              tabindex="0"
              @click="openInterfaceDetail(row)"
              @keydown.enter="openInterfaceDetail(row)"
            >
              <div class="if-top">
                <span class="if-name" :title="row.name">{{ row.name }}</span>
                <el-tag
                  :type="row.oper_status === 'up' ? 'success' : 'danger'"
                  size="small"
                  effect="dark"
                >
                  {{ row.oper_status === 'up' ? 'UP' : 'DOWN' }}
                </el-tag>
              </div>
              <div class="if-desc">{{ row.description || '—' }}</div>

              <div class="if-rates">
                <div class="if-rate">
                  <span class="if-rate-label">{{ t('device.inbound') }}</span>
                  <span class="if-rate-value in">{{ bpsText(row.in_bps) }}</span>
                </div>
                <div class="if-rate">
                  <span class="if-rate-label">{{ t('device.outbound') }}</span>
                  <span class="if-rate-value out">{{ bpsText(row.out_bps) }}</span>
                </div>
                <div class="if-rate">
                  <span class="if-rate-label">{{ t('device.bandwidth') }}</span>
                  <span class="if-rate-value">{{ speedText(row.speed) }}</span>
                </div>
              </div>

              <div class="if-util">
                <div class="if-util-line">
                  <span>{{ t('device.inUtilization') }}</span>
                  <el-progress
                    :percentage="ifUtil(row, 'in')"
                    :stroke-width="8"
                    :color="ifUtilColor(ifUtil(row, 'in'))"
                    :format="(p) => `${p}%`"
                    style="flex: 1"
                  />
                </div>
                <div class="if-util-line">
                  <span>{{ t('device.outUtilization') }}</span>
                  <el-progress
                    :percentage="ifUtil(row, 'out')"
                    :stroke-width="8"
                    :color="ifUtilColor(ifUtil(row, 'out'))"
                    :format="(p) => `${p}%`"
                    style="flex: 1"
                  />
                </div>
              </div>

              <div class="if-foot">
                <span>{{ t('device.cumulativeIn', { value: bytesText(row.in_octets) }) }}</span>
                <span>{{ t('device.cumulativeOut', { value: bytesText(row.out_octets) }) }}</span>
                <span :class="{ 'if-err': (row.in_errors || 0) + (row.out_errors || 0) > 0 }">
                  {{ t('device.errorCount', { inCount: row.in_errors ?? 0, outCount: row.out_errors ?? 0 }) }}
                </span>
              </div>
            </div>
            <el-empty
              v-if="filteredInterfaces.length === 0"
              :description="t('device.noMatchingInterfaces')"
              class="if-empty"
            />
          </div>
          <div v-if="filteredInterfaces.length" class="if-pagination">
            <el-pagination
              v-model:current-page="ifPage"
              v-model:page-size="ifPageSize"
              :page-sizes="[8, 12, 24, 48]"
              :total="filteredInterfaces.length"
              layout="total, sizes, prev, pager, next, jumper"
              small
              background
            />
          </div>
        </el-tab-pane>

        <el-tab-pane v-if="isIpmiDevice" :label="t('device.interfacesTraffic')" name="interfaces">
          <el-empty description="IPMI 协议不提供主机网卡和接口流量数据">
            <p style="max-width: 520px; color: #8a9bab; line-height: 1.8">
              IPMI 只能读取 BMC 传感器、电源、温度和 SEL 事件，无法获取操作系统网卡、端口速率或流量计数。
              如需接口与流量，请为该设备配置 SNMP 或 API 接入。
            </p>
          </el-empty>
        </el-tab-pane>

        <el-tab-pane label="当前告警" name="alerts">
          <el-table
            :data="currentAlerts"
            stripe
            size="small"
            max-height="calc(100vh - 420px)"
            class="device-alert-table"
            style="width: 100%"
          >
            <el-table-column :label="t('device.level')" width="90">
              <template #default="{ row }">
                <el-tag :type="alertLevelType(row.alert_level)" size="small" effect="dark">
                  {{ row.level_label || alertLevelText(row.alert_level) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="alert_type" :label="t('device.type')" width="110" />
            <el-table-column prop="message" :label="t('device.info')" show-overflow-tooltip />
            <el-table-column :label="t('device.time')" width="180">
              <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column :label="t('device.status')" width="100">
              <template #default="{ row }">
                <el-tag :type="row.is_acknowledged ? 'success' : 'info'" size="small">
                  {{ row.is_acknowledged ? t('device.acknowledged') : t('device.unacknowledged') }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="currentAlerts.length === 0" :description="t('device.noDataInRange')" />
        </el-tab-pane>
        <el-tab-pane label="当前告警指标" name="current-metrics">
          <div class="current-metrics-panel">
            <div class="current-metrics-head">
              <div>
                <strong>当前告警指标</strong>
                <span>读取仪表盘指标设置，共 {{ currentDashboardMetrics.length }} 项；完整展示指标项、当前值、预警值和告警值</span>
              </div>
              <el-button size="small" plain @click="refreshDashboardMetrics">
                <el-icon><Refresh /></el-icon>刷新配置
              </el-button>
            </div>
            <el-table v-if="currentDashboardMetrics.length" :data="currentDashboardMetrics" stripe style="width: 100%">
              <el-table-column prop="label" label="指标项" min-width="220" show-overflow-tooltip />
              <el-table-column label="当前值" width="130">
                <template #default="{ row }">
                  <span :class="['current-metric-value', row.severity]">{{ formatMetricValue(row) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="预警值" width="130">
                <template #default="{ row }">{{ formatMetricValue(row, row.warning) }}</template>
              </el-table-column>
              <el-table-column label="告警值" width="130">
                <template #default="{ row }">{{ formatMetricValue(row, row.critical) }}</template>
              </el-table-column>
              <el-table-column label="状态" width="100" align="center">
                <template #default="{ row }">
                  <el-tag :type="['critical','emergency'].includes(row.severity) ? 'danger' : row.severity === 'warning' ? 'warning' : row.status === '无数据' ? 'info' : 'success'" size="small">
                    {{ row.status }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-else description="该设备尚未在仪表盘指标设置中配置指标" :image-size="70" />
          </div>
        </el-tab-pane>
        <el-tab-pane label="自定义告警规则" name="rules">
          <AlertRulesPanel :device-id="Number(route.params.id)" @changed="refreshDashboardMetrics" />
        </el-tab-pane>
        <el-tab-pane label="历史告警" name="history">
          <div class="alert-history-toolbar">
            <span class="muted">共 {{ alertHistoryTotal }} 条历史告警</span>
            <el-button size="small" :loading="alertHistoryLoading" @click="loadAlertHistory">刷新</el-button>
          </div>
          <el-table
            :data="alertHistory"
            stripe
            v-loading="alertHistoryLoading"
            style="width: 100%"
            max-height="calc(100vh - 360px)"
          >
            <el-table-column label="告警时间" width="170">
              <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="级别" width="90">
              <template #default="{ row }">
                <el-tag :type="alertLevelType(row.alert_level)" size="small">
                  {{ row.level_label || alertLevelText(row.alert_level) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="类型" width="130" show-overflow-tooltip>
              <template #default="{ row }">{{ row.alert_type_text || row.alert_type }}</template>
            </el-table-column>
            <el-table-column prop="message" label="告警内容" min-width="260" show-overflow-tooltip />
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag v-if="row.resolved_at" type="success" size="small">已恢复</el-tag>
                <el-tag v-else-if="row.is_acknowledged" type="warning" size="small">已确认</el-tag>
                <el-tag v-else type="danger" size="small">未恢复</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="恢复时间" width="170">
              <template #default="{ row }">{{ row.resolved_at ? formatDateTime(row.resolved_at) : '-' }}</template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!alertHistoryLoading && !alertHistory.length" description="暂无历史告警" />
          <el-pagination
            v-model:current-page="alertHistoryPage"
            v-model:page-size="alertHistorySize"
            :total="alertHistoryTotal"
            :page-sizes="[10, 20, 50, 100]"
            layout="total, sizes, prev, pager, next"
            class="alert-history-pager"
            @current-change="loadAlertHistory"
            @size-change="onAlertHistorySizeChange"
          />
        </el-tab-pane>
        <el-tab-pane :label="t('device.maintenanceRecords')" name="maintenance">
          <div class="maint-toolbar">
            <el-button type="primary" size="small" @click="openAddMaintenance">
              <el-icon><Plus /></el-icon>{{ t('device.addMaintenanceRecord') }}
            </el-button>
            <span class="muted">{{ t('device.maintenanceCount', { count: filteredMaintenance.length }) }}</span>
          </div>
          <el-table :data="filteredMaintenance" stripe style="width: 100%">
            <el-table-column :label="t('device.maintenanceTime')" width="170">
              <template #default="{ row }">{{ formatDateTime(row.maintained_at) }}</template>
            </el-table-column>
            <el-table-column :label="t('device.type')" width="110">
              <template #default="{ row }">
                <el-tag size="small" :type="maintTypeTag(row.maint_type)">
                  {{ row.maint_type_label }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="title" :label="t('device.item')" min-width="180" show-overflow-tooltip />
            <el-table-column prop="description" :label="t('device.note')" min-width="220" show-overflow-tooltip />
            <el-table-column prop="engineer" :label="t('device.engineer')" width="110" />
            <el-table-column :label="t('device.cost')" width="100">
              <template #default="{ row }">{{ row.cost ? `¥${row.cost}` : '-' }}</template>
            </el-table-column>
            <el-table-column prop="created_by" :label="t('device.registeredBy')" width="100" />
            <el-table-column :label="t('device.actions')" width="80" fixed="right">
              <template #default="{ row }">
                <el-button type="danger" link size="small" @click="removeMaintenance(row)">
                  {{ t('device.delete') }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="filteredMaintenance.length === 0" :description="t('device.noDataInRange')" />
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 接口流量详情 -->
    <el-dialog
      v-model="ifDetailVisible"
      :title="`${t('device.interfaceDetail')} · ${ifDetail?.name || ''}`"
      width="960px"
      class="if-detail-dialog"
      destroy-on-close
      @closed="onIfDetailClosed"
      @opened="resizeIfDetailChart"
    >
      <div v-if="ifDetail" class="if-detail-body">
        <div class="if-detail-meta">
          <el-tag :type="ifDetail.oper_status === 'up' ? 'success' : 'danger'" size="small" effect="dark">
            {{ ifDetail.oper_status === 'up' ? 'UP' : 'DOWN' }}
          </el-tag>
          <span>{{ ifDetail.description || '—' }}</span>
          <span class="if-detail-index">IF {{ ifDetail.index || ifDetail.if_index || '-' }}</span>
          <span class="if-detail-speed">{{ t('device.bandwidth') }}：{{ speedText(ifDetail.speed) }}</span>
        </div>

        <div class="if-detail-stats">
          <template v-if="ifDetailView === 'traffic'">
            <div class="if-detail-stat">
              <span>{{ t('device.detailCurrent') }} · {{ t('device.inbound') }}</span>
              <b class="in">{{ bpsText(ifDetail.in_bps) }}</b>
            </div>
            <div class="if-detail-stat">
              <span>{{ t('device.detailCurrent') }} · {{ t('device.outbound') }}</span>
              <b class="out">{{ bpsText(ifDetail.out_bps) }}</b>
            </div>
            <div class="if-detail-stat">
              <span>{{ t('device.detailAvg') }} · {{ t('device.detailIn') }}</span>
              <b>{{ bpsText(ifDetailStats.inAvg) }}</b>
            </div>
            <div class="if-detail-stat">
              <span>{{ t('device.detailPeak') }} · {{ t('device.detailIn') }}</span>
              <b>{{ bpsText(ifDetailStats.inPeak) }}</b>
            </div>
            <div class="if-detail-stat">
              <span>{{ t('device.detailAvg') }} · {{ t('device.detailOut') }}</span>
              <b>{{ bpsText(ifDetailStats.outAvg) }}</b>
            </div>
            <div class="if-detail-stat">
              <span>{{ t('device.detailPeak') }} · {{ t('device.detailOut') }}</span>
              <b>{{ bpsText(ifDetailStats.outPeak) }}</b>
            </div>
          </template>
          <template v-else>
            <div class="if-detail-stat">
              <span>区间新增 · 入错误包</span>
              <b class="error-in">{{ ifDetailStats.inErrorTotal }} <small>包</small></b>
            </div>
            <div class="if-detail-stat">
              <span>区间新增 · 出错误包</span>
              <b class="error-out">{{ ifDetailStats.outErrorTotal }} <small>包</small></b>
            </div>
            <div class="if-detail-stat">
              <span>峰值 · 入错误包</span>
              <b>{{ ifDetailStats.inErrorPeak }} <small>包</small></b>
            </div>
            <div class="if-detail-stat">
              <span>峰值 · 出错误包</span>
              <b>{{ ifDetailStats.outErrorPeak }} <small>包</small></b>
            </div>
            <div class="if-detail-stat">
              <span>接口累计 · 入错误包</span>
              <b>{{ ifErrorAnalysis.accumIn }} <small>包</small></b>
            </div>
            <div class="if-detail-stat">
              <span>接口累计 · 出错误包</span>
              <b>{{ ifErrorAnalysis.accumOut }} <small>包</small></b>
            </div>
          </template>
        </div>

        <div v-if="ifDetailView === 'errors'" class="if-error-analysis" :class="`is-${ifErrorAnalysis.level}`">
          <div class="if-error-analysis-head">
            <div class="if-error-analysis-title">
              <el-icon><Warning /></el-icon>
              <strong>错误包原因分析</strong>
            </div>
            <el-tag :type="ifErrorAnalysis.tagType" size="small" effect="plain">{{ ifErrorAnalysis.label }}</el-tag>
          </div>
          <p class="if-error-summary">{{ ifErrorAnalysis.summary }}</p>
          <div class="if-error-analysis-grid">
            <div>
              <h4>可能原因</h4>
              <ul>
                <li v-for="item in ifErrorAnalysis.causes" :key="item">{{ item }}</li>
              </ul>
            </div>
            <div>
              <h4>建议排查</h4>
              <ol>
                <li v-for="item in ifErrorAnalysis.actions" :key="item">{{ item }}</li>
              </ol>
            </div>
          </div>
        </div>

        <div class="if-detail-toolbar">
          <span class="if-detail-label">查看</span>
          <el-radio-group v-model="ifDetailView" size="small" @change="renderIfDetailChart">
            <el-radio-button value="traffic">流量</el-radio-button>
            <el-radio-button value="errors">错误包</el-radio-button>
          </el-radio-group>
          <span class="if-detail-label">{{ t('device.detailTimeRange') }}</span>
          <el-radio-group v-model="ifDetailRange" size="small" @change="onIfPresetChange">
            <el-radio-button value="1">1h</el-radio-button>
            <el-radio-button value="6">6h</el-radio-button>
            <el-radio-button value="24">24h</el-radio-button>
            <el-radio-button value="168">7d</el-radio-button>
          </el-radio-group>
          <el-date-picker
            v-model="ifDetailCustomRange"
            type="datetimerange"
            size="small"
            :start-placeholder="t('device.startTime')"
            :end-placeholder="t('device.endTime')"
            :clearable="true"
            style="width: 310px"
            @change="onIfCustomRangeChange"
          />
          <el-button size="small" type="primary" plain :loading="ifDetailLoading" @click="loadInterfaceHistory">
            {{ t('device.detailQuery') }}
          </el-button>
        </div>

        <div v-loading="ifDetailLoading" class="if-detail-chart-wrap">
          <div v-show="ifDetailPoints.length" ref="ifDetailChartRef" class="if-detail-chart"></div>
          <el-empty
            v-if="!ifDetailLoading && ifDetailPoints.length === 0"
            :description="t('device.detailNoData')"
            :image-size="70"
          />
        </div>
      </div>
    </el-dialog>

    <!-- 资产标签二维码 -->
    <el-dialog v-model="qrVisible" :title="t('device.assetTagQr')" width="460px">
      <div v-loading="qrLoading" class="qr-box">
        <img v-if="qr.image" :src="qr.image" class="qr-image" :alt="t('device.assetTagQr')" />
        <div class="qr-info">
          <div><span class="muted">{{ t('device.deviceLabel') }}</span>{{ device?.name }}</div>
          <div><span class="muted">{{ t('device.assetNoLabel') }}</span>{{ device?.asset_no || '-' }}</div>
          <div><span class="muted">IP：</span>{{ device?.ip_address }}</div>
          <div class="qr-content">{{ qr.content }}</div>
        </div>
      </div>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="qr-tip"
        :title="t('device.qrTooltip')"
      />
      <template #footer>
        <el-radio-group v-model="qrKind" size="small" @change="loadQrcode">
          <el-radio-button value="url">{{ t('device.urlMode') }}</el-radio-button>
          <el-radio-button value="text">{{ t('device.textMode') }}</el-radio-button>
        </el-radio-group>
        <el-button @click="downloadQrcode">{{ t('device.downloadPng') }}</el-button>
        <el-button type="primary" @click="qrVisible = false">{{ t('device.close') }}</el-button>
      </template>
    </el-dialog>

    <!-- 新增维保记录 -->
    <el-dialog v-model="maintDialog" :title="t('device.addMaintenanceRecord')" width="560px">
      <el-form :model="maintForm" label-width="90px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="t('device.type')">
              <el-select v-model="maintForm.maint_type" style="width: 100%">
                <el-option :label="t('device.inspection')" value="inspection" />
                <el-option :label="t('device.repair')" value="repair" />
                <el-option :label="t('device.replaceParts')" value="parts" />
                <el-option :label="t('device.others')" value="other" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('device.maintenanceTime')">
              <el-date-picker v-model="maintForm.maintained_at" type="datetime"
                              value-format="YYYY-MM-DDTHH:mm:ss" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item :label="t('device.item')" required>
          <el-input v-model="maintForm.title" maxlength="200" :placeholder="t('device.maintenanceTitlePlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('device.note')">
          <el-input v-model="maintForm.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="t('device.engineer')">
              <el-input v-model="maintForm.engineer" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('device.costYuan')">
              <el-input-number v-model="maintForm.cost" :min="0" :precision="2" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="maintDialog = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="maintSaving" @click="saveMaintenance">{{ t('common.save') }}</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="customConfigVisible" title="配置自定义指标" width="820px" :close-on-click-modal="false">
      <div class="custom-config-hint">
        每个指标由指标 Key、显示名称、SNMP OID、单位和倍率组成。采集时读取 OID 数值并乘以倍率；
        指标 Key 可用于自定义告警规则和自定义图表。
      </div>
      <el-table :data="customConfigRows" size="small" border style="width:100%">
        <el-table-column label="指标 Key" width="135">
          <template #default="{ row }"><el-input v-model="row.key" size="small" placeholder="optical_rx" /></template>
        </el-table-column>
        <el-table-column label="显示名称" width="135">
          <template #default="{ row }"><el-input v-model="row.name" size="small" placeholder="光模块收光" /></template>
        </el-table-column>
        <el-table-column label="SNMP OID" min-width="220">
          <template #default="{ row }"><el-input v-model="row.oid" size="small" placeholder="1.3.6.1.4.1..." /></template>
        </el-table-column>
        <el-table-column label="单位" width="70">
          <template #default="{ row }"><el-input v-model="row.unit" size="small" placeholder="dBm" /></template>
        </el-table-column>
        <el-table-column label="倍率" width="100">
          <template #default="{ row }"><el-input-number v-model="row.scale" size="small" :step="0.01" controls-position="right" style="width:100%" /></template>
        </el-table-column>
        <el-table-column width="54">
          <template #default="{ $index }">
            <el-button link type="danger" @click="customConfigRows.splice($index, 1)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-button class="custom-add-row" size="small" @click="addCustomConfigRow">
        <el-icon><Plus /></el-icon>添加指标
      </el-button>
      <template #footer>
        <el-button @click="customConfigVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="customConfigSaving" @click="saveCustomConfig">保存指标配置</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { t } from '@/i18n'
import { ref, reactive, computed, nextTick, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as echarts from 'echarts'
import { ElMessage, ElMessageBox } from 'element-plus'
import { assetApi, monitorApi } from '@/api'
import AlertRulesPanel from '@/components/AlertRulesPanel.vue'
import { refreshMs } from '@/store/settings'
import { downloadWithAuth } from '@/store/auth'
import { can } from '@/store/auth'
import { deviceTypeLabel } from '@/constants/device'
import { formatDateTime, formatHM, ageSeconds } from '@/utils/time'
import { temperatureDisplayName } from '@/utils/serverComponentLabels'
import { readDashboardMetricsConfig, buildDeviceDashboardMetrics, formatMetricValue } from '@/utils/dashboardMetrics'

const route = useRoute()
const loading = ref(false)
const device = ref(null)
const communityVisible = ref(false)

// ---------- 维保 / 资产标签 ----------
const maintenance = ref([])
const maintDialog = ref(false)
const maintSaving = ref(false)
const maintForm = ref({
  maint_type: 'inspection',
  title: '',
  description: '',
  engineer: '',
  cost: 0,
  maintained_at: '',
})
const qrVisible = ref(false)
const qrLoading = ref(false)
const qrKind = ref('url')
const qr = ref({ image: '', content: '' })
const TABS_EXTRA = ['maintenance']
const warrantyTag = computed(() => {
  const days = device.value?.warranty_days_left
  if (days === null || days === undefined) return null
  if (days < 0) return { type: 'danger', text: t('device.warrantyExpired', { days: Math.abs(days) }) }
  if (days <= 30) return { type: 'warning', text: t('device.warrantyExpiring', { days }) }
  return { type: 'success', text: t('device.warrantyRemaining', { days }) }
})

function maintTypeTag(type) {
  return { repair: 'danger', inspection: 'success', parts: 'warning', other: 'info' }[type] || 'info'
}

async function loadMaintenance() {
  if (!device.value) return
  try {
    const res = await assetApi.listMaintenance(device.value.id)
    maintenance.value = res.data.items || []
  } catch {
    maintenance.value = []
  }
}

function openAddMaintenance() {
  maintForm.value = {
    maint_type: 'inspection',
    title: '',
    description: '',
    engineer: '',
    cost: 0,
    maintained_at: '',
  }
  maintDialog.value = true
}

async function saveMaintenance() {
  if (!maintForm.value.title.trim()) {
    ElMessage.warning(t('device.maintenanceItemRequired'))
    return
  }
  maintSaving.value = true
  try {
    const payload = { ...maintForm.value }
    if (!payload.maintained_at) delete payload.maintained_at
    await assetApi.addMaintenance(device.value.id, payload)
    ElMessage.success(t('device.maintenanceAdded'))
    maintDialog.value = false
    await loadMaintenance()
  } catch (e) {
    ElMessage.error(e.message || t('device.saveFailed'))
  } finally {
    maintSaving.value = false
  }
}

async function removeMaintenance(row) {
  try {
    await ElMessageBox.confirm(t('device.confirmDeleteMaintenance', { title: row.title }), t('device.confirmDelete'), { type: 'warning' })
    await assetApi.removeMaintenance(row.id)
    ElMessage.success(t('device.deleted'))
    await loadMaintenance()
  } catch {
    /* 取消 */
  }
}

async function openQrcode() {
  qrVisible.value = true
  qrKind.value = 'url'
  await loadQrcode()
}

async function loadQrcode() {
  qrLoading.value = true
  try {
    const res = await assetApi.getQrcode(device.value.id, qrKind.value)
    qr.value = {
      image: `data:image/png;base64,${res.data.png_base64}`,
      content: res.data.content,
    }
  } catch (e) {
    ElMessage.error(e.message || t('device.qrGenerateFailed'))
  } finally {
    qrLoading.value = false
  }
}

function downloadQrcode() {
  downloadWithAuth(`/api/assets/${device.value.id}/qrcode.png?kind=${qrKind.value}`)
}

// MIB 自定义采集 OID
const METRIC_META = [
  { key: 'cpu', label: 'CPU', type: 'danger' },
  { key: 'memory', get label() { return t('device.memory') }, type: 'warning' },
  { key: 'temperature', get label() { return t('device.maxTemperature') }, type: 'success' },
  { key: 'power', get label() { return t('device.power') }, type: 'info' },
]
const customOidCount = computed(() =>
  Object.values(device.value?.custom_oids || {}).filter(Boolean).length
)
const metric = ref(null)
const metricThresholds = ref({ cpu_usage: 80, memory_usage: 85, temperature: 80, temperature_critical: 90, disk_usage: 90 })
const interfaces = ref([])
const ifFilter = ref('all')
const ifKeyword = ref('')
const IF_PAGE_SIZE_STORAGE = 'nms_if_page_size'
const ifPage = ref(1)
const ifPageSize = ref([8, 12, 24, 48].includes(Number(localStorage.getItem(IF_PAGE_SIZE_STORAGE)))
  ? Number(localStorage.getItem(IF_PAGE_SIZE_STORAGE))
  : 8)
const IF_SORT_STORAGE = 'nms_interface_sort_v1'
const ifUtilFilter = ref('all')
const ifSortKey = ref(localStorage.getItem(`${IF_SORT_STORAGE}_key`) || 'index')
const ifSortOrder = ref(localStorage.getItem(`${IF_SORT_STORAGE}_order`) || 'asc')

function saveIfSort() {
  try {
    localStorage.setItem(`${IF_SORT_STORAGE}_key`, ifSortKey.value)
    localStorage.setItem(`${IF_SORT_STORAGE}_order`, ifSortOrder.value)
  } catch {
    /* 忽略存储异常 */
  }
}

function toggleIfSortOrder() {
  ifSortOrder.value = ifSortOrder.value === 'asc' ? 'desc' : 'asc'
  saveIfSort()
}

function interfaceIndexValue(row) {
  const raw = row.index ?? row.if_index ?? ''
  const value = parseInt(String(raw), 10)
  return Number.isNaN(value) ? Number.MAX_SAFE_INTEGER : value
}

function interfaceSortValue(row) {
  if (ifSortKey.value === 'name') return String(row.name || '')
  if (ifSortKey.value === 'in_bps') return Number(row.in_bps) || 0
  if (ifSortKey.value === 'out_bps') return Number(row.out_bps) || 0
  if (ifSortKey.value === 'total_bps') return (Number(row.in_bps) || 0) + (Number(row.out_bps) || 0)
  if (ifSortKey.value === 'util') return ifUtil(row, 'in') + ifUtil(row, 'out')
  return interfaceIndexValue(row)
}

// 接口概览与筛选排序
const apiIfLoading = ref(false)

async function loadApiInterfaces() {
  if (!isApiDevice.value) return
  apiIfLoading.value = true
  try {
    const res = await monitorApi.getDeviceInterfaces(route.params.id, true)
    interfaces.value = Array.isArray(res.data) ? res.data : []
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '获取 API 接口失败')
  } finally {
    apiIfLoading.value = false
  }
}

const ifSummary = computed(() => {
  const total = interfaces.value.length
  const up = interfaces.value.filter((i) => i.oper_status === 'up').length
  const totalBps = interfaces.value.reduce(
    (sum, i) => sum + (i.in_bps || 0) + (i.out_bps || 0), 0
  )
  return {
    total,
    up,
    down: total - up,
    available: total ? Math.round((up / total) * 100) : 0,
    totalBps,
  }
})

const filteredInterfaces = computed(() => {
  let list = interfaces.value
  if (ifFilter.value === 'up') {
    list = list.filter((i) => i.oper_status === 'up')
  } else if (ifFilter.value === 'down') {
    list = list.filter((i) => i.oper_status !== 'up')
  }
  const keyword = ifKeyword.value.trim().toLowerCase()
  if (keyword) {
    list = list.filter(
      (i) =>
        (i.name || '').toLowerCase().includes(keyword) ||
        (i.description || '').toLowerCase().includes(keyword)
    )
  }
  if (ifUtilFilter.value !== 'all') {
    const threshold = Number(ifUtilFilter.value) || 0
    list = list.filter((i) => Math.max(ifUtil(i, 'in'), ifUtil(i, 'out')) >= threshold)
  }
  return [...list].sort((a, b) => {
    const av = interfaceSortValue(a)
    const bv = interfaceSortValue(b)
    let compare
    if (typeof av === 'string' || typeof bv === 'string') {
      compare = String(av).localeCompare(String(bv), 'zh-CN', { numeric: true })
    } else {
      compare = Number(av) - Number(bv)
    }
    if (compare === 0) compare = interfaceIndexValue(a) - interfaceIndexValue(b)
    return ifSortOrder.value === 'asc' ? compare : -compare
  })
})

const pagedInterfaces = computed(() => {
  const start = (ifPage.value - 1) * ifPageSize.value
  return filteredInterfaces.value.slice(start, start + ifPageSize.value)
})

watch([ifFilter, ifKeyword, ifUtilFilter, ifSortKey, ifSortOrder], () => {
  ifPage.value = 1
})

watch(ifPageSize, (value) => {
  try {
    localStorage.setItem(IF_PAGE_SIZE_STORAGE, String(value))
  } catch {
    /* 忽略存储异常 */
  }
  ifPage.value = 1
})

watch(() => filteredInterfaces.value.length, (length) => {
  const maxPage = Math.max(1, Math.ceil(length / ifPageSize.value))
  if (ifPage.value > maxPage) ifPage.value = maxPage
})

/** 接口利用率（入/出方向速率 / 带宽） */
function ifUtil(row, dir) {
  const speed = Number(row.speed) || 0
  const bps = Number(dir === 'in' ? row.in_bps : row.out_bps) || 0
  if (speed <= 0) return 0
  return Math.min(100, Math.round((bps / speed) * 1000) / 10)
}

/** 利用率进度条颜色（用颜色区分，保留百分比文字） */
function ifUtilColor(percent) {
  if (percent >= 80) return '#f56c6c'
  if (percent >= 50) return '#e6a23c'
  return '#67c23a'
}

// ---------- 接口流量详情 ----------
const ifDetailVisible = ref(false)
const ifDetail = ref(null)
const ifDetailRange = ref('24')
const ifDetailView = ref('traffic')
const ifDetailCustomRange = ref([])
const ifDetailLoading = ref(false)
const ifDetailPoints = ref([])
const ifDetailChartRef = ref(null)
let ifDetailChart = null

const ifDetailErrorSeries = computed(() => {
  let prevIn = 0
  let prevOut = 0
  return ifDetailPoints.value.map((point, index) => {
    const inErrors = Number(point.in_errors) || 0
    const outErrors = Number(point.out_errors) || 0
    const result = {
      in: index === 0 ? 0 : Math.max(0, inErrors - prevIn),
      out: index === 0 ? 0 : Math.max(0, outErrors - prevOut),
    }
    prevIn = inErrors
    prevOut = outErrors
    return result
  })
})

const ifDetailStats = computed(() => {
  const points = ifDetailPoints.value
  if (!points.length) {
    return { inAvg: 0, inPeak: 0, outAvg: 0, outPeak: 0, inErrorTotal: 0, outErrorTotal: 0, inErrorPeak: 0, outErrorPeak: 0 }
  }
  const inValues = points.map((point) => Number(point.in_bps) || 0)
  const outValues = points.map((point) => Number(point.out_bps) || 0)
  const errorSeries = ifDetailErrorSeries.value
  const inErrors = errorSeries.map((point) => point.in)
  const outErrors = errorSeries.map((point) => point.out)
  const avg = (values) => values.reduce((sum, value) => sum + value, 0) / values.length
  return {
    inAvg: avg(inValues),
    inPeak: Math.max(...inValues),
    outAvg: avg(outValues),
    outPeak: Math.max(...outValues),
    inErrorTotal: inErrors.reduce((sum, value) => sum + value, 0),
    outErrorTotal: outErrors.reduce((sum, value) => sum + value, 0),
    inErrorPeak: Math.max(...inErrors),
    outErrorPeak: Math.max(...outErrors),
  }
})

const ifErrorAnalysis = computed(() => {
  const detail = ifDetail.value || {}
  const stats = ifDetailStats.value
  const inNew = Number(stats.inErrorTotal || 0)
  const outNew = Number(stats.outErrorTotal || 0)
  const inTotal = Math.max(Number(detail.in_errors || 0), inNew)
  const outTotal = Math.max(Number(detail.out_errors || 0), outNew)
  const hasNew = inNew > 0 || outNew > 0
  const hasHistory = inTotal > 0 || outTotal > 0
  const online = String(detail.oper_status || '').toLowerCase() === 'up'
  const inUtil = Number(ifUtil(detail, 'in')) || 0
  const outUtil = Number(ifUtil(detail, 'out')) || 0
  const causes = []
  const actions = []

  if (!online) {
    causes.push('接口当前为 DOWN：链路中断、对端端口关闭、光模块/跳线故障或端口被禁用')
    actions.push('先检查本端和对端接口状态、光模块收发光功率及跳线连接')
  }
  if (inNew > 0 || outNew > 0) {
    if (inNew > 0 && outNew > 0) {
      causes.push('双向均有新增错误包：优先怀疑物理链路、光模块、网线/光纤或端口硬件')
    } else if (inNew > 0) {
      causes.push('入方向新增错误包（接收侧）：对端发送、光纤/网线、光模块或本端接收端口')
    } else {
      causes.push('出方向新增错误包（发送侧）：本端发送端口、线缆或对端接收侧')
    }
    causes.push('速率/双工协商不一致，常见 CRC、Alignment、Runts、Giants 等错误')
    causes.push('接口接触不良、跳线/法兰污染、光模块老化或端口硬件故障')
    actions.push('在两端执行 show interface，查看 CRC/input errors/output errors 是否持续增长')
    actions.push('检查光模块收发光功率、换跳线/法兰或更换端口交叉验证')
    actions.push('确认两端速率、双工和自协商配置一致')
  }
  if ((inUtil >= 70 || outUtil >= 70) && online) {
    causes.push(`接口利用率偏高（入 ${inUtil.toFixed(1)}% / 出 ${outUtil.toFixed(1)}%），可能伴随拥塞和队列丢包`)
    actions.push('检查上联带宽、QoS 队列及突发流量，必要时扩容或调整流量路径')
  }
  if (!hasNew && !hasHistory) {
    causes.push('当前查询区间未发现错误包；接口状态正常时暂无需处理')
    actions.push('继续观察；如需主动巡检，可在两端清除计数器后观察 10 分钟')
  } else if (!hasNew && hasHistory) {
    causes.push(`接口累计错误包记录（入 ${inTotal} / 出 ${outTotal}），但当前区间没有新增，可能是历史遗留或升级前累计`)
    actions.push('清除接口计数器后观察 5～10 分钟，确认错误包是否仍在增长')
  }
  if (hasNew || hasHistory) {
    actions.push('若错误包持续增长，保留 show interface 和光模块诊断结果，联动物理链路/设备厂商排查')
  }

  const level = hasNew ? ((inNew + outNew) > 1000 ? 'danger' : 'warning') : (hasHistory ? 'info' : 'success')
  return {
    level,
    tagType: level === 'danger' ? 'danger' : level === 'warning' ? 'warning' : level === 'success' ? 'success' : 'info',
    label: hasNew ? '发现新增错误包' : hasHistory ? '仅有历史累计' : '当前区间正常',
    accumIn: inTotal,
    accumOut: outTotal,
    summary: hasNew
      ? `当前区间新增入错误包 ${inNew} 包、出错误包 ${outNew} 包；接口累计入 ${inTotal} / 出 ${outTotal} 包，建议优先排查物理链路和端口协商。`
      : hasHistory
        ? `当前区间未新增错误包，但接口累计入 ${inTotal} / 出 ${outTotal} 包；请清除计数器后继续观察。`
        : '当前区间未检测到错误包，接口流量与状态未见明显异常。',
    causes: causes.slice(0, 5),
    actions: actions.slice(0, 6),
  }
})

function openInterfaceDetail(row) {
  ifDetail.value = row
  ifDetailRange.value = '24'
  ifDetailView.value = 'traffic'
  ifDetailCustomRange.value = []
  ifDetailPoints.value = []
  ifDetailVisible.value = true
  nextTick(() => loadInterfaceHistory())
}

function onIfPresetChange(value) {
  if (value !== 'custom') {
    ifDetailCustomRange.value = []
  }
  loadInterfaceHistory()
}

function onIfCustomRangeChange(value) {
  if (Array.isArray(value) && value.length === 2) {
    ifDetailRange.value = 'custom'
    loadInterfaceHistory()
  } else {
    ifDetailRange.value = '24'
    ifDetailCustomRange.value = []
    loadInterfaceHistory()
  }
}

async function loadInterfaceHistory() {
  if (!ifDetail.value) return
  ifDetailLoading.value = true
  try {
    const params = {}
    if (ifDetailRange.value === 'custom' && ifDetailCustomRange.value?.length === 2) {
      params.start = new Date(ifDetailCustomRange.value[0]).toISOString()
      params.end = new Date(ifDetailCustomRange.value[1]).toISOString()
    } else {
      params.hours = Number(ifDetailRange.value) || 24
    }
    const res = await monitorApi.getInterfaceHistory(
      route.params.id,
      ifDetail.value.id,
      params
    )
    ifDetailPoints.value = res.data.points || []
    await nextTick()
    renderIfDetailChart()
  } catch (e) {
    ElMessage.error(e.message || t('device.loadDeviceFailed'))
    ifDetailPoints.value = []
  } finally {
    ifDetailLoading.value = false
  }
}

function renderIfDetailChart() {
  if (!ifDetailChartRef.value || !ifDetailPoints.value.length) return
  if (!ifDetailChart) {
    ifDetailChart = echarts.init(ifDetailChartRef.value)
  }
  ifDetailChart.resize()
  const points = ifDetailPoints.value
  const showSymbol = points.length <= 2
  const errorsMode = ifDetailView.value === 'errors'
  const errorSeries = ifDetailErrorSeries.value
  const series = errorsMode
    ? [
        {
          name: '入错误包',
          type: 'line',
          smooth: true,
          showSymbol,
          data: errorSeries.map((point) => point.in),
          itemStyle: { color: '#fb7185' },
        },
        {
          name: '出错误包',
          type: 'line',
          smooth: true,
          showSymbol,
          data: errorSeries.map((point) => point.out),
          itemStyle: { color: '#f59e0b' },
        },
      ]
    : [
        {
          name: t('device.detailIn'),
          type: 'line',
          smooth: true,
          showSymbol,
          data: points.map((point) => point.in_bps || 0),
          itemStyle: { color: '#38bdf8' },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(56, 189, 248, 0.34)' },
              { offset: 1, color: 'rgba(56, 189, 248, 0.02)' },
            ]),
          },
        },
        {
          name: t('device.detailOut'),
          type: 'line',
          smooth: true,
          showSymbol,
          data: points.map((point) => point.out_bps || 0),
          itemStyle: { color: '#a78bfa' },
        },
      ]
  ifDetailChart.setOption({
    tooltip: {
      trigger: 'axis',
      valueFormatter: (value) => (errorsMode ? `${value ?? 0} 包` : bpsText(value)),
    },
    legend: {
      data: errorsMode ? ['入错误包', '出错误包'] : [t('device.detailIn'), t('device.detailOut')],
      top: 0,
    },
    grid: { left: '3%', right: '4%', bottom: '8%', top: 42, containLabel: true },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: points.map((point) => formatHM(point.collected_at)),
      axisLabel: { fontSize: 10 },
    },
    yAxis: {
      type: 'value',
      minInterval: errorsMode ? 1 : undefined,
      axisLabel: { fontSize: 10, formatter: (value) => (errorsMode ? `${value} 包` : bpsText(value)) },
    },
    series,
  }, true)
}

function resizeIfDetailChart() {
  ifDetailChart?.resize()
}

function onIfDetailClosed() {
  ifDetailChart?.dispose()
  ifDetailChart = null
}

const alerts = ref([])
const activeAlerts = ref([])
const alertHistory = ref([])
const alertHistoryTotal = ref(0)
const alertHistoryPage = ref(1)
const alertHistorySize = ref(20)
const alertHistoryLoading = ref(false)
const dashboardMetricsConfig = ref(readDashboardMetricsConfig())
const currentDashboardMetrics = computed(() => {
  const rows = buildDeviceDashboardMetrics(dashboardMetricsConfig.value, device.value)
  return rows.map((row) => {
    const alertLevel = highestAlertLevelNameForMetric(row.key)
    if (!alertLevel) return row
    const currentRank = ALERT_LEVEL_RANK[row.severity] || 0
    const alertRank = ALERT_LEVEL_RANK[alertLevel] || 0
    const severity = alertRank > currentRank ? alertLevel : row.severity
    return {
      ...row,
      severity,
      alertLevel,
      status: ['critical', 'emergency'].includes(severity) ? '告警' : severity === 'warning' ? '预警' : row.status,
    }
  })
})

function refreshDashboardMetrics() {
  dashboardMetricsConfig.value = readDashboardMetricsConfig()
}
const TABS = ['info', 'hardware', 'cpu', 'memory', 'temperature', 'interfaces', 'alerts', 'current-metrics', 'rules', 'history', 'maintenance', 'custom']
const activeTab = ref(
  TABS.includes(String(route.query.tab || '')) ? String(route.query.tab) : 'info'
)

// ---------- 时间范围筛选（历史曲线 / 告警 / 维保记录）----------
const TIME_PRESETS = [
  { value: 1, labelKey: 'device.range1h' },
  { value: 6, labelKey: 'device.range6h' },
  { value: 24, labelKey: 'device.range24h' },
  { value: 168, labelKey: 'device.range7d' },
  { value: 720, labelKey: 'device.range30d' },
]
const presetHours = ref(24)
const customRange = ref([])
const rangeMode = ref('preset') // preset | custom

function toServerTime(value) {
  return new Date(value).toISOString().slice(0, 19)
}

function isPresetActive(hours) {
  return rangeMode.value === 'preset' && presetHours.value === hours
}

const rangeText = computed(() => {
  if (rangeMode.value !== 'custom' || customRange.value?.length !== 2) return ''
  const fmt = (value) => new Date(value).toLocaleString()
  return `${fmt(customRange.value[0])} ~ ${fmt(customRange.value[1])}`
})

const historyParams = computed(() => {
  if (rangeMode.value === 'custom' && customRange.value?.length === 2) {
    return {
      start: toServerTime(customRange.value[0]),
      end: toServerTime(customRange.value[1]),
    }
  }
  return { hours: presetHours.value || 24 }
})

const chartRanges = reactive({
  cpu: { mode: 'preset', hours: 24, custom: [] },
  memory: { mode: 'preset', hours: 24, custom: [] },
  temperature: { mode: 'preset', hours: 24, custom: [] },
})

function chartRangeParams(kind) {
  const range = chartRanges[kind] || chartRanges.cpu
  if (range.mode === 'custom' && range.custom?.length === 2) {
    return { start: toServerTime(range.custom[0]), end: toServerTime(range.custom[1]) }
  }
  return { hours: range.hours || 24 }
}

function isChartPresetActive(kind, hours) {
  const range = chartRanges[kind]
  return !!range && range.mode === 'preset' && range.hours === hours
}

function setChartPreset(kind, hours) {
  const range = chartRanges[kind]
  if (!range) return
  range.mode = 'preset'
  range.hours = hours
  range.custom = []
  renderCharts()
}

function onChartCustomRangeChange(kind, value) {
  const range = chartRanges[kind]
  if (!range) return
  if (Array.isArray(value) && value.length === 2) range.mode = 'custom'
  else if (!value || value.length === 0) range.mode = 'preset'
  renderCharts()
}

function resetChartRange(kind) {
  const range = chartRanges[kind]
  if (!range) return
  range.mode = 'preset'
  range.hours = 24
  range.custom = []
  renderCharts()
}

function chartRangeText(kind) {
  const range = chartRanges[kind]
  if (!range || range.mode !== 'custom' || range.custom?.length !== 2) return ''
  const fmt = (value) => new Date(value).toLocaleString()
  return `${fmt(range.custom[0])} ~ ${fmt(range.custom[1])}`
}

function getRangeBounds() {
  if (rangeMode.value === 'custom' && customRange.value?.length === 2) {
    return [new Date(customRange.value[0]), new Date(customRange.value[1])]
  }
  const end = new Date()
  const start = new Date(end.getTime() - (presetHours.value || 24) * 3600 * 1000)
  return [start, end]
}

// 服务端时间为 UTC 无时区字符串，统一按 UTC 解析后再比较
function parseServerTime(value) {
  if (!value) return null
  let text = String(value).replace(' ', 'T')
  if (!/[zZ]|[+-]\d{2}:?\d{2}$/.test(text)) text += 'Z'
  const date = new Date(text)
  return Number.isNaN(date.getTime()) ? null : date
}

// “当前告警”展示所有未恢复告警，不按时间范围过滤；时间筛选只用于历史类页签。
const currentAlerts = computed(() => activeAlerts.value || [])

const filteredAlerts = computed(() => {
  const [start, end] = getRangeBounds()
  return alerts.value.filter((item) => {
    const time = parseServerTime(item.created_at)
    return time && time >= start && time <= end
  })
})

const filteredMaintenance = computed(() => {
  const [start, end] = getRangeBounds()
  return maintenance.value.filter((item) => {
    const time = parseServerTime(item.maintained_at)
    return time && time >= start && time <= end
  })
})

async function refreshCharts() {
  await nextTick()
  await renderCharts()
}

function setPreset(hours) {
  rangeMode.value = 'preset'
  presetHours.value = hours
  customRange.value = []
  refreshCharts()
}

function onCustomRangeChange(value) {
  if (Array.isArray(value) && value.length === 2) {
    rangeMode.value = 'custom'
    refreshCharts()
  } else if (!value || value.length === 0) {
    rangeMode.value = 'preset'
    refreshCharts()
  }
}

function resetTimeRange() {
  rangeMode.value = 'preset'
  presetHours.value = 24
  customRange.value = []
  refreshCharts()
}

const cpuChartRef = ref(null)
const memoryChartRef = ref(null)
const tempChartRef = ref(null)
const customChartRef = ref(null)

let cpuChart = null
let memoryChart = null
let tempChart = null
let customChart = null
let timer = null

// 自定义指标
const customMetricDefs = computed(() => device.value?.custom_metrics || [])
const selectedCustomKey = ref('')
const customConfigVisible = ref(false)
const customConfigSaving = ref(false)
const customCollecting = ref(false)
const customConfigRows = ref([])

function currentCustomValue(key) {
  const value = metric.value?.custom?.[key]
  return value === null || value === undefined ? '-' : value
}

function openCustomConfig() {
  customConfigRows.value = customMetricDefs.value.map((item) => ({
    key: item.key || '',
    name: item.name || '',
    oid: item.oid || '',
    unit: item.unit || '',
    scale: Number(item.scale ?? 1),
  }))
  if (!customConfigRows.value.length) addCustomConfigRow()
  customConfigVisible.value = true
}

function addCustomConfigRow() {
  customConfigRows.value.push({ key: '', name: '', oid: '', unit: '', scale: 1 })
}

async function saveCustomConfig() {
  const rows = customConfigRows.value.filter((row) => row.key?.trim() || row.oid?.trim())
  const keys = new Set()
  for (const row of rows) {
    const key = String(row.key || '').trim()
    const oid = String(row.oid || '').trim()
    if (!key || !oid) {
      ElMessage.warning('指标 Key 和 OID 不能为空')
      return
    }
    if (!/^[a-zA-Z0-9_]{1,30}$/.test(key)) {
      ElMessage.warning(`指标 Key「${key}」只能包含字母、数字、下划线，最长 30 位`)
      return
    }
    if (!/^\d+(\.\d+)+$/.test(oid)) {
      ElMessage.warning(`指标「${key}」的 OID 格式不正确`)
      return
    }
    if (keys.has(key)) {
      ElMessage.warning(`指标 Key「${key}」重复`)
      return
    }
    keys.add(key)
  }
  customConfigSaving.value = true
  try {
    const res = await assetApi.update(device.value.id, {
      custom_metrics: rows.map((row) => ({
        key: row.key.trim(),
        name: row.name?.trim() || row.key.trim(),
        oid: row.oid.trim(),
        unit: row.unit?.trim() || '',
        scale: Number(row.scale ?? 1) || 1,
      })),
    })
    device.value = { ...device.value, ...res.data }
    customConfigVisible.value = false
    selectedCustomKey.value = customMetricDefs.value[0]?.key || ''
    ElMessage.success('自定义指标已保存，下一次采集生效')
    if (can('monitor:edit')) await collectCustomNow(false)
  } catch (error) {
    ElMessage.error(error.message || '保存自定义指标失败')
  } finally {
    customConfigSaving.value = false
  }
}

async function collectCustomNow(notify = true) {
  if (!device.value?.id) return
  customCollecting.value = true
  try {
    await monitorApi.collectDevice(device.value.id)
    await loadBase()
    await loadOverview()
    if (notify) ElMessage.success('采集完成，自定义指标结果已刷新')
  } catch (error) {
    if (notify) ElMessage.error(error.message || '立即采集失败')
  } finally {
    customCollecting.value = false
  }
}

const upCount = computed(() => interfaces.value.filter((i) => i.oper_status === 'up').length)

const monitorType = computed(() => device.value?.monitor_type || 'snmp')
const isSnmpDevice = computed(() => monitorType.value === 'snmp')
const isApiDevice = computed(() => monitorType.value === 'api')
const isIpmiDevice = computed(() => monitorType.value === 'ipmi')
const hasMetricsDevice = computed(() => isSnmpDevice.value || isApiDevice.value || isIpmiDevice.value)
const isSnmpV3 = computed(
  () => isSnmpDevice.value && String(device.value?.snmp_version || '').toLowerCase() === 'v3'
)
const v3SecurityLevelText = computed(() => {
  const value = String(device.value?.v3_security_level || '').trim()
  const labels = {
    noAuthNoPriv: '不认证不加密（noAuthNoPriv）',
    authNoPriv: '认证不加密（authNoPriv）',
    authPriv: '认证并加密（authPriv）',
  }
  return labels[value] || value || '-'
})
const monitorTypeText = computed(() => ({
  snmp: 'SNMP',
  ping: 'ICMP Ping',
  tcp: 'TCP 端口',
  api: 'API 对接',
  ipmi: 'IPMI 对接',
}[monitorType.value] || monitorType.value))
const probeAlive = computed(() => {
  const value = metric.value?.custom?.probe_alive
  if (value === 1 || value === '1' || value === true) return 1
  if (value === 0 || value === '0' || value === false) return 0
  return null
})
const probeLatency = computed(() => {
  const value = metric.value?.custom?.probe_latency_ms
  return value === null || value === undefined || value === '' ? null : Number(value)
})

const statusType = computed(() => {
  if (!metric.value) return 'info'
  if (probeAlive.value === 0) return 'danger'
  if (ageSeconds(metric.value.collected_at) > 300) return 'danger'
  if (alerts.value.some((a) => !a.is_acknowledged && a.alert_level === 'critical')) return 'warning'
  return 'success'
})
const statusText = computed(
  () => ({ success: t('device.online'), warning: t('device.alert'), danger: t('device.offline'), info: t('device.unknown') }[statusType.value])
)

const powerTag = computed(() => {
  const alertRank = highestAlertLevelForMetric('power')
  if (alertRank >= 3) return 'danger'
  if (alertRank === 2) return 'warning'
  const p = metric.value?.power_status
  if (p === 'normal') return 'success'
  if (p === 'failure') return 'danger'
  return 'info'
})
const powerText = computed(() => {
  const p = metric.value?.power_status
  return p === 'normal' ? t('device.normal') : p === 'failure' ? t('device.abnormal') : t('device.unknown')
})

function formatCapacity(mb) {
  const value = Number(mb) || 0
  if (value <= 0) return '未采集'
  if (value >= 1024 * 1024) return `${(value / 1024 / 1024).toFixed(2)} TB`
  if (value >= 1024) return `${(value / 1024).toFixed(1)} GB`
  return `${value.toFixed(0)} MB`
}

function findCustomValue(patterns) {
  const custom = metric.value?.custom || {}
  for (const [key, value] of Object.entries(custom)) {
    const lower = key.toLowerCase()
    if (patterns.some((pattern) => lower.includes(pattern))) {
      return { key, value: Number(value) }
    }
  }
  return null
}

const serverComponents = computed(() => (
  metric.value?.components
  || metric.value?.custom?.server_components
  || {}
))
const hasServerComponents = computed(() => {
  const components = serverComponents.value || {}
  return ['cpus', 'memory_modules', 'temperatures', 'fans', 'power_supplies', 'disks']
    .some((key) => Array.isArray(components[key]) && components[key].length > 0)
})
const temperatureKindLabel = (kind) => ({
  cpu: 'CPU 温度',
  inlet: '进风温度',
  exhaust: '排风温度',
  board: '主板温度',
  ambient: '环境温度',
  other: '其他温度',
}[kind] || '温度')
const temperatureDetail = computed(() => {
  const temps = serverComponents.value?.temperatures || []
  if (!temps.length) return ''
  const hottest = [...temps].sort((a, b) => Number(b.value) - Number(a.value))[0]
  return `${temperatureDisplayName(hottest.name)} ${hottest.value}${hottest.unit || '°C'}（最高）`
})
const cpuDetail = computed(() => {
  const cpus = serverComponents.value?.cpus || []
  return cpus.length ? `共 ${cpus.length} 颗 CPU` : ''
})
const memoryModuleDetail = computed(() => {
  const modules = serverComponents.value?.memory_modules || []
  return modules.length ? `共 ${modules.length} 条内存 · ${serverComponents.value?.summary?.memory_total_gb || 0} GB` : ''
})

const hardwareInfo = computed(() => {
  const m = metric.value || {}
  const custom = m.custom || {}
  const components = serverComponents.value || {}
  let totalMb = Number(m.disk_total) || 0
  let usedMb = Number(m.disk_used) || 0
  if (!totalMb && custom.disk_total_gb) totalMb = Number(custom.disk_total_gb) * 1024
  if (!usedMb && custom.disk_used_gb) usedMb = Number(custom.disk_used_gb) * 1024
  if (!totalMb && components.summary?.disk_total_gb) totalMb = Number(components.summary.disk_total_gb) * 1024
  const usage = Number(m.disk_usage ?? custom.disk_usage)
  const diskCapacity = totalMb > 0 ? formatCapacity(totalMb) : '未采集'
  const diskUsage = usage !== undefined && usage !== null && Number.isFinite(Number(usage))
    ? `使用率 ${Number(usage).toFixed(1)}%${totalMb > 0 && usedMb > 0 ? ` · 已用 ${formatCapacity(usedMb)}` : ''}`
    : (totalMb > 0 ? '使用率未采集' : '主机未提供磁盘容量')

  const fan = findCustomValue(['fan_speed', 'fanrpm', 'fan_rpm', 'srv_fan_speed'])
  const componentFans = components.fans || []
  const fanDef = (device.value?.custom_metrics || []).find((item) => item.key === fan?.key)
    || (device.value?.server_sensors || []).find((item) => item.key === fan?.key)
  const fanUnit = fanDef?.unit || ''
  const maxFan = componentFans.length
    ? Math.max(...componentFans.map((item) => Number(item.value) || 0))
    : null
  const fanSpeed = componentFans.length
    ? `${Math.round(maxFan)} RPM`
    : fan && Number.isFinite(fan.value)
      ? `${Math.round(fan.value)}${fanUnit ? ` ${fanUnit}` : ''}`
      : '未采集'
  const fanSub = componentFans.length
    ? `共 ${componentFans.length} 个风扇 · 最高 ${Math.round(maxFan)} RPM`
    : fan ? `OID 指标 ${fan.key}` : '设备/型号未提供风扇转速 OID'

  const watts = findCustomValue(['power_watts', 'srv_power_watts', 'current_power'])
  const voltage = findCustomValue(['power_voltage', 'srv_power_voltage', 'voltage'])
  const powerStatus = m.power_status
  const componentPsus = components.power_supplies || []
  const totalWatts = componentPsus.reduce((sum, item) => sum + (Number(item.watts) || 0), 0)
  const powerLabel = componentPsus.length
    ? `${Math.round(totalWatts)} W`
    : watts && Number.isFinite(watts.value)
      ? `${Math.round(watts.value)} W`
      : voltage && Number.isFinite(voltage.value)
        ? `${voltage.value.toFixed(1)} V`
        : (powerStatus === 'normal' ? t('device.normal') : powerStatus === 'failure' ? t('device.abnormal') : '未采集')
  const powerParts = []
  if (componentPsus.length) powerParts.push(`${componentPsus.length} 个电源`)
  if (powerStatus === 'normal') powerParts.push(t('device.normal'))
  else if (powerStatus === 'failure') powerParts.push(t('device.abnormal'))
  if (voltage && Number.isFinite(voltage.value)) powerParts.push(`${voltage.value.toFixed(1)} V`)
  if (componentPsus.length) powerParts.push(`合计 ${Math.round(totalWatts)} W`)
  else if (watts && Number.isFinite(watts.value)) powerParts.push(`${Math.round(watts.value)} W`)
  return {
    diskCapacity,
    diskUsage,
    fanSpeed,
    fanSub,
    powerLabel,
    powerSub: powerParts.length ? powerParts.join(' · ') : '设备/型号未提供电源 OID',
  }
})

const uptimeText = computed(() => {
  const s = metric.value?.uptime
  if (!s) return '-'
  const d = Math.floor(s / 86400)
  const h = Math.floor((s % 86400) / 3600)
  const m = Math.floor((s % 3600) / 60)
  return d > 0 ? t('device.uptimeDaysHours', { days: d, hours: h }) : t('device.uptimeHoursMinutes', { hours: h, minutes: m })
})

function getTypeName(type) {
  return deviceTypeLabel(type)
}

function fmt(v, unit = '') {
  return v === null || v === undefined ? '-' : `${Number(v).toFixed(1)}${unit}`
}

function levelClass(v, bad, warn) {
  if (v === null || v === undefined) return ''
  if (v >= bad) return 'lv-bad'
  if (v >= warn) return 'lv-warn'
  return 'lv-ok'
}

const ALERT_LEVEL_RANK = { info: 1, warning: 2, critical: 3, emergency: 4 }

function alertMatchesMetric(alert, metricKey) {
  const key = String(metricKey || '').toLowerCase()
  const rawKey = String(alert?.metric_key || '').toLowerCase()
  const type = String(alert?.alert_type || '').toLowerCase()
  const aliases = {
    cpu_usage: ['cpu_usage', 'cpu'],
    memory_usage: ['memory_usage', 'memory'],
    temperature: ['temperature', 'temp'],
    disk_usage: ['disk_usage', 'disk', 'storage_disk_fault'],
    fan_speed: ['fan_speed', 'fan'],
    power: ['power', 'power_status'],
  }[key] || [key]
  if (aliases.includes(rawKey)) return true
  if (aliases.includes(type)) return true
  if (key === 'disk_usage' && (type === 'storage_disk_fault' || type === 'srv_disk_fault')) return true
  if (key === 'fan_speed' && type === 'srv_fan_fault') return true
  const text = `${alert?.alert_type_text || ''} ${alert?.metric_label || ''} ${alert?.message || ''}`.toLowerCase()
  const words = {
    cpu_usage: ['cpu'], memory_usage: ['内存', 'memory'],
    temperature: ['温度', 'temperature'], disk_usage: ['磁盘', 'disk'],
    fan_speed: ['风扇', 'fan'], power: ['电源', 'power'],
  }[key] || []
  return words.some((word) => text.includes(word))
}

function highestAlertLevelForMetric(metricKey) {
  let highest = 0
  for (const alert of activeAlerts.value) {
    if (alert?.resolved_at || !alertMatchesMetric(alert, metricKey)) continue
    const rank = ALERT_LEVEL_RANK[alert.alert_level] || 0
    if (rank > highest) highest = rank
  }
  return highest
}

function highestAlertLevelNameForMetric(metricKey) {
  let highest = ''
  let rank = 0
  for (const alert of activeAlerts.value) {
    if (alert?.resolved_at || !alertMatchesMetric(alert, metricKey)) continue
    const value = ALERT_LEVEL_RANK[alert.alert_level] || 0
    if (value > rank) { rank = value; highest = alert.alert_level }
  }
  return highest
}

function metricAlertClass(metricKey) {
  const rank = highestAlertLevelForMetric(metricKey)
  if (rank >= 3) return 'metric-alert-critical'
  if (rank === 2) return 'metric-alert-warning'
  return ''
}

function alertLevelText(level) {
  return { info: '提示', warning: '警告', critical: '严重', emergency: '紧急' }[level] || level || '警告'
}

function alertLevelType(level) {
  return { info: 'info', warning: 'warning', critical: 'danger', emergency: 'danger' }[level] || 'warning'
}

function speedText(bps) {
  if (!bps) return '-'
  const mbps = bps / 1_000_000
  return mbps >= 1000 ? `${(mbps / 1000).toFixed(1)} Gbps` : `${mbps.toFixed(0)} Mbps`
}

function bpsText(v) {
  if (v === null || v === undefined) return '-'
  if (v >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(2)} Gbps`
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)} Mbps`
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)} Kbps`
  return `${Number(v).toFixed(0)} bps`
}

function bytesText(v) {
  if (v === null || v === undefined) return '-'
  if (v >= 1024 ** 4) return `${(v / 1024 ** 4).toFixed(2)} TB`
  if (v >= 1024 ** 3) return `${(v / 1024 ** 3).toFixed(2)} GB`
  if (v >= 1024 ** 2) return `${(v / 1024 ** 2).toFixed(1)} MB`
  if (v >= 1024) return `${(v / 1024).toFixed(1)} KB`
  return `${Number(v).toFixed(0)} B`
}

async function loadBase() {
  const res = await assetApi.getOne(route.params.id)
  device.value = res.data
  communityVisible.value = false
  metric.value = res.data.metric
  if (!['snmp', 'api', 'ipmi'].includes(res.data.monitor_type || 'snmp') && ['cpu', 'memory', 'temperature', 'custom', 'interfaces'].includes(activeTab.value)) {
    activeTab.value = 'info'
  }
  await loadMaintenance()
}

async function loadAlertHistory() {
  alertHistoryLoading.value = true
  try {
    const res = await monitorApi.getAlerts(route.params.id, {
      page: alertHistoryPage.value,
      size: alertHistorySize.value,
    })
    alertHistory.value = res.data?.items || []
    alertHistoryTotal.value = Number(res.data?.total || 0)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '加载历史告警失败')
  } finally {
    alertHistoryLoading.value = false
  }
}

function onAlertHistorySizeChange() {
  alertHistoryPage.value = 1
  loadAlertHistory()
}

async function loadOverview() {
  const res = await monitorApi.getDeviceOverview(route.params.id)
  if (res.data?.metric_thresholds) metricThresholds.value = { ...metricThresholds.value, ...res.data.metric_thresholds }
  device.value = { ...(device.value || {}), ...res.data.device }
  metric.value = res.data.metric || metric.value
  interfaces.value = res.data.interfaces || []
  alerts.value = res.data.alerts || []
  activeAlerts.value = res.data.active_alerts || res.data.alerts || []
}

async function loadHistory(type, rangeKind = '') {
  try {
    const res = await monitorApi.getMetricHistory(route.params.id, {
      metric_type: type,
      ...(rangeKind ? chartRangeParams(rangeKind) : historyParams.value),
    })
    return res.data.data || []
  } catch {
    return []
  }
}

function lineOption(title, points, field, color, unit) {
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: '3%', right: '4%', bottom: '8%', top: '14%', containLabel: true },
    xAxis: {
      type: 'category',
      data: points.map((p) => formatHM(p.collected_at)),
      axisLabel: { fontSize: 10 },
    },
    yAxis: { type: 'value', name: unit, axisLabel: { fontSize: 10 } },
    series: [{
      name: title,
      type: 'line',
      smooth: true,
      showSymbol: false,
      data: points.map((p) => p[field]),
      itemStyle: { color },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: `${color}66` },
          { offset: 1, color: `${color}08` },
        ]),
      },
    }],
  }
}

/**
 * 图表在对应页签可见时才初始化（隐藏容器宽度为 0，提前初始化会导致图表空白）
 */
function ensureChart(refEl, chart) {
  const el = refEl?.value
  if (!el || !el.clientWidth || !el.clientHeight) return chart
  if (!chart) chart = echarts.init(el)
  chart.resize()
  return chart
}

async function renderCharts() {
  if (activeTab.value === 'cpu') {
    cpuChart = ensureChart(cpuChartRef, cpuChart)
    if (cpuChart) {
      const pts = await loadHistory('cpu_usage', 'cpu')
      cpuChart.setOption(
        lineOption(t('device.cpuUsage'), pts, 'cpu_usage', '#409eff', '%'), true
      )
    }
  } else if (activeTab.value === 'memory') {
    memoryChart = ensureChart(memoryChartRef, memoryChart)
    if (memoryChart) {
      const pts = await loadHistory('memory_usage', 'memory')
      memoryChart.setOption(
        lineOption(t('device.memoryUsage'), pts, 'memory_usage', '#67c23a', '%'), true
      )
    }
  } else if (activeTab.value === 'temperature') {
    tempChart = ensureChart(tempChartRef, tempChart)
    if (tempChart) {
      const pts = await loadHistory('temperature', 'temperature')
      tempChart.setOption(
        lineOption(t('device.temperature'), pts, 'temperature', '#f56c6c', '°C'), true
      )
    }
  } else if (activeTab.value === 'custom') {
    await renderCustomChart()
  }
  // 接口页为原生卡片展示，无需图表
}

async function renderCustomChart() {
  if (!customMetricDefs.value.length) return
  if (!selectedCustomKey.value) {
    selectedCustomKey.value = customMetricDefs.value[0].key
  }
  const key = selectedCustomKey.value
  customChart = ensureChart(customChartRef, customChart)
  if (!customChart) return
  const field = `custom_${key}`
  const points = await loadHistory(field)
  const meta = customMetricDefs.value.find((item) => item.key === key)
  customChart.setOption(
    lineOption(meta?.name || key, points, field, '#8b5cf6', meta?.unit || ''), true
  )
}

async function onTabChange() {
  await nextTick()
  if (activeTab.value === 'current-metrics') refreshDashboardMetrics()
  if (activeTab.value === 'history') await loadAlertHistory()
  await renderCharts()
  // 页签切换后容器尺寸可能变化，主动 resize 已初始化的图表
  cpuChart?.resize()
  memoryChart?.resize()
  tempChart?.resize()
  customChart?.resize()
}

async function refreshAll() {
  loading.value = true
  try {
    await loadBase()
    await loadOverview()
    if (activeTab.value === 'history') await loadAlertHistory()
    await renderCharts()
  } catch (e) {
    ElMessage.error(e.message || t('device.loadDeviceFailed'))
  } finally {
    loading.value = false
  }
}

// ---------- 上一台 / 下一台（同一资产列表内导航）----------
const NAV_PAGE_SIZE = 100
const NAV_CACHE_TTL = 60 * 1000
const NAV_MAX_PAGES = 50
const router = useRouter()
const navList = ref([])
const navTotal = ref(0)
const navLoading = ref(false)
// 列表缓存在组件模块作用域，同一详情页多次打开/切换设备时复用，避免重复请求
let navCache = { items: [], total: 0, fetchedAt: 0 }

const navIndex = computed(
  () => navList.value.findIndex((item) => String(item.id) === String(route.params.id))
)
const prevDevice = computed(() => (navIndex.value > 0 ? navList.value[navIndex.value - 1] : null))
const nextDevice = computed(() => {
  const index = navIndex.value
  return index >= 0 && index < navList.value.length - 1 ? navList.value[index + 1] : null
})
const navPosition = computed(() => {
  const total = navTotal.value || navList.value.length
  if (navIndex.value < 0 || !total) return '—'
  return `${navIndex.value + 1}/${total}`
})

/**
 * 拉取与资产管理默认排序一致的资产列表（后端按 Device.id 升序），按页加载后缓存。
 * 仅在首次进入 / 缓存过期 / 当前设备不在缓存中时请求，不随定时刷新重复拉取。
 */
async function loadNavList() {
  navLoading.value = true
  try {
    const items = []
    let total = 0
    for (let page = 1; page <= NAV_MAX_PAGES; page += 1) {
      const res = await assetApi.getList({ page, size: NAV_PAGE_SIZE })
      total = Number(res.data.total) || 0
      const batch = res.data.items || []
      items.push(
        ...batch.map((item) => ({ id: item.id, name: item.name, ip_address: item.ip_address }))
      )
      if (!batch.length || items.length >= total) break
    }
    navCache = { items, total: total || items.length, fetchedAt: Date.now() }
    navList.value = items
    navTotal.value = navCache.total
  } catch {
    // 列表加载失败不影响详情主体，仅禁用上一台/下一台
  } finally {
    navLoading.value = false
  }
}

async function ensureNavList(force = false) {
  const fresh = navCache.fetchedAt && Date.now() - navCache.fetchedAt < NAV_CACHE_TTL
  if (!force && fresh) {
    navList.value = navCache.items
    navTotal.value = navCache.total
    return
  }
  await loadNavList()
}

async function syncNavForRoute() {
  await ensureNavList()
  // 当前设备不在缓存列表（例如刚新增、列表已变更）时最多再强制刷新一次
  if (navIndex.value < 0 && navCache.fetchedAt) await ensureNavList(true)
}

function backToAssetList() {
  const query = {}
  for (const key of ['page', 'size', 'search', 'device_type', 'group_id']) {
    const value = route.query[key]
    if (typeof value === 'string' && value) query[key] = value
  }
  router.push({ path: '/devices', query })
}

function editDeviceFromDetail() {
  const query = {}
  for (const key of ['page', 'size', 'search', 'device_type', 'group_id']) {
    const value = route.query[key]
    if (typeof value === 'string' && value) query[key] = value
  }
  router.push({ path: `/devices/edit/${route.params.id}`, query })
}

function goSibling(step) {
  const target = step < 0 ? prevDevice.value : nextDevice.value
  if (!target) return
  // 保留查询参数与当前页签，切换设备后详情页布局不变
  const query = { ...route.query }
  if (activeTab.value) query.tab = activeTab.value
  router.push({ path: `/devices/${target.id}`, query })
}

// /devices/:id 复用同一组件实例，参数变化时不会重新 mount，需要手动刷新详情数据
watch(activeTab, (tab) => {
  if (tab === 'interfaces' && isApiDevice.value && !interfaces.value.length) {
    loadApiInterfaces()
  }
})

watch(
  () => route.params.id,
  async (id, oldId) => {
    if (!id || id === oldId) return
    ifDetailVisible.value = false
    ifDetail.value = null
    nextTick(() => {
      window.scrollTo({ top: 0, behavior: 'auto' })
      document.querySelector('.el-main')?.scrollTo?.({ top: 0, behavior: 'auto' })
    })
    interfaces.value = []
    alerts.value = []
    maintenance.value = []
    selectedCustomKey.value = ''
    await Promise.all([refreshAll(), ensureNavList()])
  }
)

onMounted(async () => {
  await Promise.all([refreshAll(), syncNavForRoute()])
  if (activeTab.value === 'interfaces' && isApiDevice.value && !interfaces.value.length) {
    loadApiInterfaces()
  }
  if (activeTab.value === 'history') await loadAlertHistory()
  timer = setInterval(refreshAll, refreshMs())
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
  cpuChart?.dispose()
  memoryChart?.dispose()
  tempChart?.dispose()
  customChart?.dispose()
  ifDetailChart?.dispose()
})

window.addEventListener('resize', () => {
  cpuChart?.resize()
  memoryChart?.resize()
  tempChart?.resize()
  customChart?.resize()
})
</script>

<style scoped>
.alert-history-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
.alert-history-pager { margin-top: 12px; justify-content: flex-end; }

.current-metrics-panel { padding: 4px 2px; }
.current-metrics-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 14px; padding: 12px 14px; border: 1px solid #e3edf5; border-radius: 8px; background: #f8fbfe; }
.current-metrics-head > div { display: flex; flex-direction: column; gap: 4px; }
.current-metrics-head strong { color: #1f3b52; font-size: 14px; }
.current-metrics-head span { color: #8498a8; font-size: 11px; line-height: 1.5; }
.current-metric-value { color: #0f766e; font-family: Consolas, monospace; font-weight: 600; }
.current-metric-value.warning { color: #b45309; }
.current-metric-value.critical { color: #dc2626; }
.current-metric-value.emergency { color: #991b1b; font-weight: 700; }
.device-detail {
  height: 100%;
}

.secret-value {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  letter-spacing: 1px;
}

.secret-toggle {
  margin-left: 6px;
  vertical-align: middle;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.device-nav {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.device-nav-pos {
  min-width: 48px;
  text-align: center;
  font-size: 12px;
  color: #606266;
  font-variant-numeric: tabular-nums;
}

.device-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.detail-icon {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  object-fit: contain;
  background: #f5f7fa;
}

.muted {
  color: #a8abb2;
  font-size: 12px;
}

.custom-oids {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
}

.custom-oid-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.oid-value {
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
  color: #409eff;
}

.warranty-tag {
  margin-left: 8px;
}

.maint-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.muted {
  color: #a8abb2;
  font-size: 12px;
}

.qr-box {
  display: flex;
  gap: 18px;
  align-items: flex-start;
}

.qr-image {
  width: 180px;
  height: 180px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fff;
}

.qr-info {
  flex: 1;
  font-size: 13px;
  line-height: 2;
  color: #303133;
  word-break: break-all;
}

.qr-content {
  margin-top: 8px;
  padding: 8px;
  background: #f5f7fa;
  border-radius: 6px;
  font-family: Consolas, Monaco, monospace;
  font-size: 11px;
  color: #606266;
}

.qr-tip {
  margin-top: 12px;
}

.card-header > div {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 10px;
}

.metric-cards {
  margin-bottom: 16px;
}

.device-alert-table {
  width: 100%;
}
.device-alert-table :deep(.el-table__body-wrapper) {
  max-height: calc(100vh - 470px);
}
@media (max-width: 900px) {
  .device-alert-table :deep(.el-table__body-wrapper) {
    max-height: calc(100vh - 520px);
  }
}
.hardware-inline-tags {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: 8px;
  flex-wrap: wrap;
}
.hardware-inline-tags :deep(.el-tag) {
  height: 20px;
  font-size: 10px;
  padding: 0 6px;
}
.hardware-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.hardware-item {
  padding: 11px 13px;
  border: 1px solid #e4eaf1;
  border-radius: 8px;
  background: linear-gradient(180deg, #fbfdff, #f6faff);
}
.hardware-label { color: #7b8fa1; font-size: 11px; }
.hardware-value { margin-top: 4px; color: #23384a; font-size: 16px; font-weight: 700; }
.hardware-sub { margin-top: 3px; color: #91a3b2; font-size: 10px; line-height: 1.5; }
.hardware-note { background: #fafbfc; border-style: dashed; }
.server-components-panel {
  margin-bottom: 16px;
  padding: 13px 14px;
  border: 1px solid #e4eaf1;
  border-radius: 9px;
  background: #fcfeff;
}
.server-components-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}
.server-components-head strong { color: #23384a; font-size: 14px; }
.server-components-head span { display: block; margin-top: 3px; color: #91a3b2; font-size: 11px; }
.server-component-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(270px, 1fr));
  gap: 10px;
}
.server-component-card {
  border: 1px solid #edf2f7;
  border-radius: 8px;
  background: #fff;
  padding: 9px 10px;
  min-width: 0;
}
.server-component-card h4 {
  display: flex;
  align-items: baseline;
  gap: 7px;
  margin: 0 0 6px;
  color: #334155;
  font-size: 12px;
}
.server-component-card h4 small { color: #94a3b8; font-size: 10px; font-weight: 400; }
.component-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 5px 0;
  border-top: 1px dashed #f0f4f8;
}
.component-main { min-width: 0; }
.component-main b { display: block; overflow: hidden; color: #334155; font-size: 11px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.component-main span { display: block; overflow: hidden; margin-top: 1px; color: #94a3b8; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.component-kind { color: #64748b !important; }
.component-row em { flex-shrink: 0; color: #2563eb; font-size: 11px; font-style: normal; font-weight: 700; }
.component-row em.component-warn { color: #d97706; }
.component-row em.component-bad { color: #dc2626; }
@media (max-width: 1100px) {
  .hardware-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .server-component-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 700px) {
  .server-component-grid { grid-template-columns: 1fr; }
}

.mcard {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 12px;
  background: #fafcff;
  text-align: center;
}

.mcard-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 6px;
}

.mcard-value {
  font-size: 22px;
  font-weight: bold;
  color: #303133;
}

.mcard-value.small {
  font-size: 15px;
  padding-top: 5px;
}

.mcard-sub {
  font-size: 11px;
  color: #c0c4cc;
  margin-top: 2px;
}

.lv-ok { color: #67c23a; }
.lv-warn { color: #e6a23c; }
.lv-bad { color: #f56c6c; }
.mcard.metric-alert-warning { border-color: #f3c27a; background: #fffaf1; }
.mcard.metric-alert-critical { border-color: #f19999; background: #fff6f6; }
.hardware-item.metric-alert-warning { border-color: #f3c27a; background: #fffaf1; }
.hardware-item.metric-alert-critical { border-color: #f19999; background: #fff6f6; }
.hardware-item.metric-alert-warning .hardware-value { color: #d48806; }
.hardware-item.metric-alert-critical .hardware-value { color: #e45656; }

.chart {
  width: 100%;
  height: 380px;
}

/* ==================== 接口与流量卡片 ==================== */
.if-summary {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 12px 16px;
  margin-bottom: 14px;
  background: #f8fafc;
  border: 1px solid #ebeef5;
  border-radius: 10px;
  flex-wrap: wrap;
}

.if-stat {
  display: flex;
  flex-direction: column;
  min-width: 72px;
}

.if-stat .if-k {
  font-size: 12px;
  color: #909399;
}

.if-stat b {
  font-size: 20px;
  font-weight: 700;
  color: #303133;
  line-height: 1.3;
}

.if-stat.up b {
  color: #22c55e;
}

.if-stat.down b {
  color: #ef4444;
}

.if-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 10px;
}

.if-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 10px;
}

.if-card {
  border: 1px solid #ebeef5;
  border-left: 4px solid #cbd5e1;
  border-radius: 10px;
  padding: 10px 12px;
  background: #fff;
  transition: box-shadow 0.2s ease;
}

.if-card:hover {
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.08);
}

.if-card.is-up {
  border-left-color: #22c55e;
}

.if-card.is-down {
  border-left-color: #ef4444;
  background: #fff8f8;
}

.if-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.if-name {
  font-weight: 600;
  font-size: 14px;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.if-desc {
  margin-top: 2px;
  font-size: 12px;
  color: #909399;
  height: 18px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.if-rates {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin: 8px 0 4px;
  padding: 7px 9px;
  background: #f8fafc;
  border-radius: 8px;
}

.if-rate {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.if-rate-label {
  font-size: 11px;
  color: #909399;
}

.if-rate-value {
  font-family: Consolas, Monaco, monospace;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.if-rate-value.in {
  color: #409eff;
}

.if-rate-value.out {
  color: #67c23a;
}

.if-util {
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin-bottom: 6px;
}

.if-util-line {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #909399;
}

.if-util-line > span:first-child {
  width: 62px;
  flex-shrink: 0;
}

.if-foot {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 11px;
  color: #909399;
  border-top: 1px dashed #ebeef5;
  padding-top: 6px;
  flex-wrap: wrap;
}

.if-err {
  color: #e6a23c;
  font-weight: 600;
}

.if-empty {
  grid-column: 1 / -1;
}

.if-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
  padding: 8px 10px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fbfdff;
}

/* 时间范围筛选 */
.time-filter {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  padding: 10px 12px;
  margin-bottom: 12px;
  background: #f5f7fa;
  border: 1px solid #ebeef5;
  border-radius: 8px;
}

.time-filter-label {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.time-filter-hint {
  font-size: 12px;
  color: #909399;
}

/* 自定义指标 */
.custom-metric-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
  padding: 11px 13px;
  border: 1px solid #e4eef6;
  border-radius: 9px;
  background: #f8fbfe;
}

.custom-metric-toolbar strong { display: block; color: #24425b; font-size: 13px; }
.custom-metric-toolbar > div > span { display: block; margin-top: 4px; color: #8ca0af; font-size: 10px; line-height: 1.5; }
.custom-toolbar-actions { display: flex; flex-shrink: 0; gap: 6px; }
.custom-config-hint { margin-bottom: 10px; padding: 9px 11px; border-radius: 7px; background: #f5faff; color: #7d94a5; font-size: 10px; line-height: 1.6; }
.custom-add-row { margin-top: 9px; }
.custom-metric-cards {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.cm-card {
  border: 1px solid #ebeef5;
  border-radius: 10px;
  padding: 12px 16px;
  min-width: 210px;
  background: #fff;
}

.cm-name {
  font-size: 12px;
  color: #909399;
}

.cm-value {
  font-size: 22px;
  font-weight: 700;
  color: #303133;
  margin: 4px 0;
}

.cm-value small {
  font-size: 12px;
  color: #909399;
  margin-left: 4px;
  font-weight: 400;
}

.cm-oid {
  font-family: Consolas, Monaco, monospace;
  font-size: 11px;
  color: #a8abb2;
}

.custom-chart-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 12px 0;
  font-size: 13px;
  color: #606266;
}

.bps-in { color: #409eff; }
.bps-out { color: #67c23a; }

/* 接口排序与详情 */
.if-actions {
  flex-wrap: wrap;
  justify-content: flex-end;
}

.if-sort-select {
  width: 132px;
}

.sort-arrow {
  margin-left: 4px;
}

.if-hint {
  margin: -6px 0 12px;
  color: #909399;
  font-size: 12px;
}

.if-card {
  cursor: pointer;
}

.if-card:focus-visible {
  outline: 2px solid #409eff;
  outline-offset: 2px;
}

.if-detail-body {
  padding: 0 2px;
}

.if-detail-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  background: #f5f7fa;
  color: #606266;
  font-size: 12px;
}

.if-detail-index,
.if-detail-speed {
  color: #909399;
  font-family: Consolas, monospace;
}

.if-detail-stats {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
  margin: 14px 0;
}

.if-detail-stat {
  padding: 10px 12px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fff;
  min-width: 0;
}

.if-detail-stat span {
  display: block;
  color: #909399;
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.if-detail-stat b {
  display: block;
  margin-top: 5px;
  color: #303133;
  font-size: 15px;
  font-family: Consolas, monospace;
  white-space: nowrap;
}

.if-detail-stat b.in { color: #0ea5e9; }
.if-detail-stat b.out { color: #8b5cf6; }
.if-detail-stat b.error-in { color: #e11d48; }
.if-detail-stat b.error-out { color: #ea580c; }
.if-detail-stat b small { margin-left: 2px; color: #909399; font-size: 10px; font-weight: 500; }

.if-detail-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  padding: 10px 0 12px;
  border-top: 1px dashed #ebeef5;
}

.if-detail-label {
  color: #606266;
  font-size: 12px;
}

.if-error-analysis {
  margin: 0 0 12px;
  padding: 12px 14px;
  border: 1px solid #e4eaf1;
  border-left: 4px solid #38bdf8;
  border-radius: 8px;
  background: #f8fbfd;
}
.if-error-analysis.is-warning { border-left-color: #f59e0b; background: #fffdf5; }
.if-error-analysis.is-danger { border-left-color: #ef4444; background: #fff8f8; }
.if-error-analysis.is-success { border-left-color: #10b981; background: #f7fdfa; }
.if-error-analysis.is-info { border-left-color: #94a3b8; background: #f8fafc; }
.if-error-analysis-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.if-error-analysis-title { display: flex; align-items: center; gap: 7px; color: #24425b; font-size: 13px; }
.if-error-analysis-title .el-icon { color: #f59e0b; }
.if-error-summary { margin: 8px 0 10px; color: #526b7d; font-size: 11px; line-height: 1.7; }
.if-error-analysis-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.if-error-analysis-grid h4 { margin: 0 0 5px; color: #3e5a6c; font-size: 11px; }
.if-error-analysis-grid ul,
.if-error-analysis-grid ol { margin: 0; padding-left: 18px; color: #6c8292; font-size: 10px; line-height: 1.8; }
.if-error-analysis-grid li::marker { color: #f59e0b; }
.if-error-analysis.is-success .if-error-analysis-grid li::marker { color: #10b981; }

.if-detail-chart-wrap {
  min-height: 330px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 8px;
}

.if-detail-chart {
  width: 100%;
  height: 330px;
}

@media (max-width: 900px) {
  .if-detail-stats {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
