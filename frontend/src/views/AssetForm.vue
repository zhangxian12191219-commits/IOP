<template>
  <div class="asset-form-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>{{ isEdit ? t('asset.form.editDevice') : isCopy ? t('asset.form.copyDevice') : t('asset.form.addDevice') }}</span>
          <div>
            <el-button size="small" @click="testConnection" :loading="testing">
              <el-icon><Connection /></el-icon>{{ t('asset.form.testConnectivity') }}
            </el-button>
            <el-button
              v-if="isEdit"
              size="small"
              :loading="navLoading"
              :disabled="!prevDevice"
              :title="prevDevice ? prevDevice.name : '已经是第一台设备'"
              @click="goPrevDevice"
            >
              <el-icon><ArrowLeft /></el-icon>上一台
            </el-button>
            <el-button
              v-if="isEdit"
              size="small"
              :loading="navLoading"
              :disabled="!nextDevice"
              :title="nextDevice ? nextDevice.name : '已经是最后一台设备'"
              @click="goNextDevice"
            >
              下一台<el-icon><ArrowRight /></el-icon>
            </el-button>
            <el-tooltip
              v-if="isEdit"
              content="保存当前设备，保存后仍停留在编辑页，不返回资产列表"
              placement="bottom"
            >
              <el-button
                size="small"
                type="primary"
                plain
                :loading="savingStay"
                :disabled="submitting"
                @click="saveCurrent"
              >
                保存当前（不返回）
              </el-button>
            </el-tooltip>
            <el-button size="small" type="primary" plain @click="returnToList">{{ t('asset.form.back') }}</el-button>
          </div>
        </div>
      </template>

      <el-alert
        v-if="isCopy"
        type="info"
        :title="t('asset.form.copyHint')"
        :closable="false"
        show-icon
        class="copy-alert"
      />

      <el-alert
        v-if="testResult"
        :type="testResult.reachable ? 'success' : 'error'"
        :closable="true"
        show-icon
        class="test-alert"
        @close="testResult = null"
      >
        <template #title>
          {{ testResult.reachable ? t('asset.form.connected') : t('asset.form.connectionFailed') }}
          <span v-if="testResult.reachable && testResult.method !== 'snmp'">
            — {{ testResult.target || form.ip_address }} · {{ testResult.latency_ms }}ms
          </span>
          <span v-else-if="testResult.reachable">
            — {{ testResult.sys_name || '-' }} / {{ testResult.sys_descr || '-' }}
          </span>
          <span v-else>— {{ testResult.error || (testResult.method === 'snmp' ? t('asset.form.checkCredentialsHint') : '探测失败') }}</span>
        </template>
      </el-alert>

      <el-form ref="formRef" :model="form" :rules="rules" label-width="120px" class="asset-form" style="max-width: 1120px">
        <el-divider content-position="left">{{ t('asset.form.basicInfo') }}</el-divider>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="t('asset.form.deviceName')" prop="name">
              <el-input v-model="form.name" :placeholder="t('asset.form.deviceNamePlaceholder')" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('asset.form.ipAddress')" prop="ip_address">
              <el-input v-model="form.ip_address" placeholder="10.0.0.1" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="t('asset.form.deviceType')" prop="device_type">
              <el-select
                v-model="form.device_type"
                filterable
                allow-create
                default-first-option
                :reserve-keyword="false"
                :placeholder="t('asset.form.deviceTypePlaceholder')"
                style="width: 100%"
              >
                <el-option
                  v-for="item in DEVICE_TYPE_OPTIONS"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('asset.form.assetGroup')">
              <div class="group-select-row">
                <el-select
                  v-model="form.group_id"
                  clearable
                  :placeholder="t('asset.form.assetGroupPlaceholder')"
                  style="flex: 1"
                >
                  <el-option
                    v-for="group in groupOptions"
                    :key="group.id"
                    :label="group.name"
                    :value="group.id"
                  />
                </el-select>
                <el-button link type="primary" @click="createGroupInline">
                  + {{ t('asset.form.newGroup') }}
                </el-button>
              </div>
              <div class="field-tip">{{ t('asset.form.newGroupTip') }}</div>
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider content-position="left">接入与监控方式</el-divider>
        <el-form-item label="接入方式" prop="monitor_type">
          <el-radio-group v-model="form.monitor_type">
            <el-radio-button value="snmp">SNMP</el-radio-button>
            <el-radio-button value="ping">ICMP Ping</el-radio-button>
            <el-radio-button value="tcp">TCP 端口</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-row v-if="form.monitor_type !== 'snmp'" :gutter="20">
          <el-col :span="12">
            <el-form-item v-if="form.monitor_type === 'tcp'" label="TCP 端口" prop="tcp_port">
              <el-input-number v-model="form.tcp_port" :min="1" :max="65535" controls-position="right" />
              <span class="field-unit">例如 80 / 443 / 22 / 3389</span>
            </el-form-item>
          </el-col>
        </el-row>
        <el-alert
          v-if="form.monitor_type !== 'snmp'"
          type="info"
          :closable="false"
          show-icon
          class="probe-mode-hint"
          :title="form.monitor_type === 'ping' ? 'Ping 接入：仅监控 ICMP 连通性和延迟，不采集 CPU/内存等 SNMP 指标。' : 'TCP 接入：仅监控指定端口连通性和连接延迟，不采集 CPU/内存等 SNMP 指标。'"
        />

        <el-form-item :label="t('asset.form.deviceIcon')">
          <div class="icon-field">
            <div class="icon-preview" :class="{ empty: !form.icon }" @click="pickIcon">
              <img v-if="form.icon" :src="form.icon" :alt="t('asset.form.deviceIcon')" />
              <el-icon v-else :size="22"><Picture /></el-icon>
            </div>
            <div class="icon-actions">
              <el-button size="small" :loading="iconUploading" @click="pickIcon">
                {{ form.icon ? t('asset.form.changeIcon') : t('asset.form.uploadIcon') }}
              </el-button>
              <el-button size="small" @click="presetVisible = true">
                <el-icon><Grid /></el-icon>{{ t('asset.form.builtInIconLibrary') }}
              </el-button>
              <el-button size="small" @click="autoMatchIcon()">
                <el-icon><MagicStick /></el-icon>{{ t('asset.form.matchByVendor') }}
              </el-button>
              <el-button
                v-if="form.icon && form.icon.startsWith('/uploads/icons/')"
                size="small"
                @click="openCropper"
              >
                {{ t('asset.form.cropScale') }}
              </el-button>
              <el-button v-if="form.icon" size="small" link type="danger" @click="form.icon = null">
                {{ t('common.reset') }}
              </el-button>
              <div class="form-tip">
                {{ t('asset.form.iconUploadHint') }}
                {{ t('asset.form.builtInIconHint') }}
              </div>
            </div>
            <input
              ref="iconInputRef"
              type="file"
              accept=".png,.jpg,.jpeg,.gif,.webp"
              style="display: none"
              @change="onIconSelected"
            />
          </div>
        </el-form-item>

        <IconPickerDialog
          v-model="presetVisible"
          :device-type="form.device_type"
          :current-icon="form.icon"
          @select="onPresetSelect"
        />
        <IconCropper v-model="cropperVisible" :src="cropSrc" @done="onCropDone" />

        <!-- 从 MIB 选择自定义指标 -->
        <el-dialog v-model="metricPickerVisible" :title="t('asset.form.pickFromMib')" width="900px">
          <div class="filters">
            <el-input
              v-model="metricKeyword"
              :placeholder="t('mib.searchObjectPlaceholder')"
              clearable
              style="width: 300px"
              @keyup.enter="loadMetricObjects"
              @clear="loadMetricObjects"
            />
            <el-button @click="loadMetricObjects">{{ t('mib.query') }}</el-button>
            <span class="muted">{{ t('asset.form.pickFromMibHint') }}</span>
          </div>
          <el-table :data="metricObjects" v-loading="metricLoading" size="small" max-height="420">
            <el-table-column prop="name" :label="t('mib.objectName')" width="230" show-overflow-tooltip />
            <el-table-column prop="oid" label="OID" width="220" />
            <el-table-column prop="category" :label="t('mib.category')" width="100">
              <template #default="{ row }">{{ row.category || '-' }}</template>
            </el-table-column>
            <el-table-column prop="description" :label="t('mib.description')" min-width="200" show-overflow-tooltip />
            <el-table-column :label="t('mib.actions')" width="90" fixed="right">
              <template #default="{ row }">
                <el-button type="primary" link size="small" @click="addMetricFromObject(row)">
                  {{ t('asset.form.add') }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>
          <template #footer>
            <el-button @click="metricPickerVisible = false">{{ t('mib.close') }}</el-button>
          </template>
        </el-dialog>

        <template v-if="form.monitor_type === 'snmp' && !isDellStorageApi">
        <el-divider content-position="left">{{ t('asset.form.mibOptimizationOptional') }}</el-divider>

        <el-form-item :label="t('asset.form.referencedMib')">
          <el-select
            v-model="form.mib_id"
            clearable
            :placeholder="t('asset.form.selectMibPlaceholder')"
            style="width: 320px"
            @change="onMibChange"
          >
            <el-option
              v-for="m in mibOptions"
              :key="m.id"
              :label="t('asset.form.mibOptionLabel', { name: m.module_name, count: m.object_count })"
              :value="m.id"
            />
          </el-select>
          <el-button
            size="small"
            style="margin-left: 8px"
            :disabled="!form.mib_id"
            :loading="recLoading"
            @click="autoDetectOids"
          >
            {{ t('asset.form.autoDetectOid') }}
          </el-button>
          <el-button size="small" :loading="templateLoading" @click="matchMibTemplate()">
            <el-icon><MagicStick /></el-icon>{{ t('asset.form.matchMibTemplate') }}
          </el-button>
          <el-button size="small" link @click="$router.push('/mibs')">{{ t('asset.form.manageMib') }}</el-button>
          <div class="form-tip">
            {{ t('asset.form.mibOptimizationHint') }}
          </div>
        </el-form-item>

        <el-form-item v-if="hasCustomOids" :label="t('asset.form.customOid')">
          <div class="custom-oid-list">
            <div v-for="meta in METRIC_META" :key="meta.key" class="custom-oid-row">
              <el-tag size="small" :type="meta.type" class="metric-tag">{{ meta.label }}</el-tag>
              <el-input
                v-model="form.custom_oids[meta.key]"
                size="small"
                :placeholder="t('asset.form.defaultOidHint')"
                class="oid-input"
              >
                <template #append>
                  <el-button
                    :disabled="!form.custom_oids[meta.key]"
                    @click="form.custom_oids[meta.key] = ''"
                  >
                    {{ t('asset.form.clear') }}
                  </el-button>
                </template>
              </el-input>
              <span v-if="metricName(form.custom_oids[meta.key])" class="oid-name">
                {{ metricName(form.custom_oids[meta.key]) }}
              </span>
            </div>
          </div>
        </el-form-item>

        <!-- 自定义指标：光功率、风扇转速等任意 OID -->
        <el-form-item :label="t('asset.form.customMetrics')">
          <div class="custom-metrics">
            <div class="cm-toolbar">
              <el-button size="small" @click="addCustomMetric">
                <el-icon><Plus /></el-icon>{{ t('asset.form.addCustomMetric') }}
              </el-button>
              <el-button size="small" :disabled="!form.mib_id" @click="openMetricPicker">
                {{ t('asset.form.pickFromMib') }}
              </el-button>
              <span class="form-tip">{{ t('asset.form.customMetricsHint') }}</span>
            </div>
            <el-table
              v-if="form.custom_metrics.length"
              :data="form.custom_metrics"
              size="small"
              border
              style="width: 100%"
            >
              <el-table-column :label="t('asset.form.metricKey')" width="130">
                <template #default="{ row }">
                  <el-input v-model="row.key" size="small" placeholder="optical_rx" />
                </template>
              </el-table-column>
              <el-table-column :label="t('asset.form.metricName')" width="150">
                <template #default="{ row }">
                  <el-input v-model="row.name" size="small" placeholder="光模块收光功率" />
                </template>
              </el-table-column>
              <el-table-column label="OID" min-width="200">
                <template #default="{ row }">
                  <el-input v-model="row.oid" size="small" placeholder="1.3.6.1.4.1.2011..." />
                </template>
              </el-table-column>
              <el-table-column :label="t('asset.form.metricUnit')" width="90">
                <template #default="{ row }">
                  <el-input v-model="row.unit" size="small" placeholder="dBm / RPM" />
                </template>
              </el-table-column>
              <el-table-column :label="t('asset.form.metricScale')" width="110">
                <template #default="{ row }">
                  <el-input-number v-model="row.scale" size="small" :step="0.001" :min="0" style="width: 90px" />
                </template>
              </el-table-column>
              <el-table-column :label="t('mib.actions')" width="130" fixed="right">
                <template #default="{ row }">
                  <el-button type="primary" link size="small" @click="testOidValue(row.oid)">
                    {{ t('mib.test') }}
                  </el-button>
                  <el-button type="danger" link size="small" @click="removeCustomMetric(row)">
                    {{ t('mib.delete') }}
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
            <div v-else class="form-tip">{{ t('asset.form.noCustomMetrics') }}</div>
          </div>
        </el-form-item>
        </template>

        <el-alert
          v-if="form.monitor_type === 'snmp' && isDellStorageApi"
          type="success"
          :closable="false"
          show-icon
          title="戴尔 ME5/PowerVault 已切换为只读 HTTPS API 采集：CPU/内存/温度/风扇/电源/磁盘/端口均来自 API，已禁用 MIB 与自定义 OID。"
        />

        <!-- 服务器硬件监控（仅 server 类型） -->
        <template v-if="form.device_type === 'server' && form.monitor_type === 'snmp'">
          <el-divider content-position="left">{{ t('asset.form.serverHardware') }}</el-divider>
          <el-form-item :label="t('asset.form.serverSensors')">
            <div class="server-sensors">
              <el-alert
                type="info"
                :closable="false"
                show-icon
                class="server-sensor-tip"
                :title="t('asset.form.serverSensorsHint')"
              />
              <el-table :data="form.server_sensors" size="small" border style="width: 100%">
                <el-table-column prop="name" :label="t('asset.form.sensorName')" width="150" />
                <el-table-column label="OID" min-width="220">
                  <template #default="{ row }">
                    <el-input v-model="row.oid" size="small" placeholder="1.3.6.1.4.1..." />
                  </template>
                </el-table-column>
                <el-table-column :label="t('asset.form.metricUnit')" width="90">
                  <template #default="{ row }">
                    <el-input v-model="row.unit" size="small" />
                  </template>
                </el-table-column>
                <el-table-column :label="t('asset.form.metricScale')" width="100">
                  <template #default="{ row }">
                    <el-input-number v-model="row.scale" size="small" :step="0.1" :min="0" style="width: 82px" />
                  </template>
                </el-table-column>
                <el-table-column :label="t('mib.actions')" width="120" fixed="right">
                  <template #default="{ row }">
                    <el-tag v-if="row.kind === 'fault'" size="small" type="warning" effect="plain">
                      {{ t('asset.form.sensorFault') }}
                    </el-tag>
                    <el-button type="primary" link size="small" @click="testOidValue(row.oid)">
                      {{ t('mib.test') }}
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </el-form-item>
        </template>

        <template v-if="form.monitor_type === 'snmp'">
        <el-divider content-position="left">{{ t('asset.form.snmpConfig') }}</el-divider>

        <el-row :gutter="20">
          <el-col :span="form.snmp_version === 'v3' ? 12 : 8">
            <el-form-item :label="t('asset.form.snmpVersion')" prop="snmp_version" label-width="100px">
              <el-radio-group v-model="form.snmp_version">
                <el-radio-button label="v1" />
                <el-radio-button label="v2c" />
                <el-radio-button label="v3" />
              </el-radio-group>
            </el-form-item>
          </el-col>
          <el-col :span="form.snmp_version === 'v3' ? 12 : 8">
            <el-form-item :label="t('asset.form.snmpPort')" label-width="100px">
              <el-input-number v-model="form.port" :min="1" :max="65535" controls-position="right" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col v-if="form.snmp_version !== 'v3'" :span="8">
            <el-form-item label="团体名" prop="community" label-width="100px">
              <el-input v-model="form.community" placeholder="public" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>

        <!-- v3 -->
        <template v-if="form.snmp_version === 'v3'">
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item :label="t('asset.form.v3Username')" prop="v3_username">
                <el-input v-model="form.v3_username" placeholder="monitor" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="t('asset.form.securityLevel')">
                <el-select v-model="form.v3_security_level" style="width: 100%">
                  <el-option :label="t('asset.form.noAuthNoPriv')" value="noAuthNoPriv" />
                  <el-option :label="t('asset.form.authNoPriv')" value="authNoPriv" />
                  <el-option :label="t('asset.form.authPriv')" value="authPriv" />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>

          <el-row v-if="form.v3_security_level !== 'noAuthNoPriv'" :gutter="20">
            <el-col :span="12">
              <el-form-item :label="t('asset.form.authProtocol')">
                <el-select v-model="form.v3_auth_protocol" style="width: 100%">
                  <el-option label="MD5" value="MD5" />
                  <el-option label="SHA (SHA-1)" value="SHA" />
                  <el-option label="SHA-224" value="SHA224" />
                  <el-option label="SHA-256" value="SHA256" />
                  <el-option label="SHA-384" value="SHA384" />
                  <el-option label="SHA-512" value="SHA512" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="t('asset.form.authPassword')">
                <el-input
                  v-model="form.v3_auth_password"
                  type="password"
                  show-password
                  :placeholder="passwordPlaceholder('auth')"
                />
              </el-form-item>
            </el-col>
          </el-row>

          <el-row v-if="form.v3_security_level === 'authPriv'" :gutter="20">
            <el-col :span="12">
              <el-form-item :label="t('asset.form.privProtocol')">
                <el-select v-model="form.v3_priv_protocol" style="width: 100%">
                  <el-option label="DES" value="DES" />
                  <el-option label="AES-128" value="AES" />
                  <el-option label="AES-192" value="AES192" />
                  <el-option label="AES-256" value="AES256" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="t('asset.form.privPassword')">
                <el-input
                  v-model="form.v3_priv_password"
                  type="password"
                  show-password
                  :placeholder="passwordPlaceholder('priv')"
                />
              </el-form-item>
            </el-col>
          </el-row>

          <el-form-item :label="t('asset.form.contextNameOptional')">
            <el-input v-model="form.v3_context_name" :placeholder="t('asset.form.leaveBlank')" style="max-width: 300px" />
          </el-form-item>
        </template>
        </template>

        <el-divider content-position="left">{{ t('asset.form.rackMountOptional') }}</el-divider>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="t('asset.form.room')">
              <el-select
                v-model="selectedRoomId"
                :placeholder="t('asset.form.selectRoom')"
                clearable
                style="width: 100%"
                @change="onRoomChange"
              >
                <el-option
                  v-for="r in rooms"
                  :key="r.id"
                  :label="`${r.name}${r.floor ? ' · ' + r.floor : ''}`"
                  :value="r.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('asset.form.cabinet')">
              <el-select
                v-model="form.cabinet_id"
                :placeholder="t('asset.form.selectCabinetPlaceholder')"
                clearable
                style="width: 100%"
                :disabled="!selectedRoomId"
                @change="onCabinetChange"
              >
                <el-option
                  v-for="c in cabinets"
                  :key="c.id"
                  :label="`${c.name}（${c.usage.used_u}/${c.u_capacity}U，${c.usage.used_power_w.toFixed(0)}/${c.power_capacity_w.toFixed(0)}W）`"
                  :value="c.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row v-if="form.cabinet_id" :gutter="20">
          <el-col :span="8">
            <el-form-item :label="t('asset.form.startU')">
              <el-select
                v-model="form.u_position"
                clearable
                filterable
                :placeholder="t('asset.form.autoAssignIfBlank')"
                style="width: 100%"
              >
                <el-option
                  v-for="option in uPositionOptions"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                  :disabled="option.occupied"
                />
              </el-select>
              <div class="form-tip" :class="{ 'u-range-conflict': uRangeConflict }">
                {{ uRangeLabel }}<template v-if="uRangeConflict"> · 与已占用 U 位重叠</template>
              </div>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item :label="t('asset.form.occupiedU')">
              <el-input-number v-model="form.u_height" :min="1" :max="cabinetInfo?.u_capacity || 42" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item :label="t('asset.form.devicePowerW')">
              <el-input-number v-model="form.power_watts" :min="0" :max="100000" :step="50" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-alert
          v-if="cabinetInfo"
          :type="powerExceeded ? 'error' : 'info'"
          :closable="false"
          show-icon
          class="cabinet-alert"
        >
          <template #title>
            {{ t('asset.form.cabinetCapacityU', { used: cabinetInfo.usage.used_u, total: cabinetInfo.u_capacity }) }}
            {{ t('asset.form.cabinetRemainingU', { free: cabinetInfo.usage.free_u }) }}
            {{ t('asset.form.cabinetPower', { used: cabinetInfo.usage.used_power_w.toFixed(0), total: cabinetInfo.power_capacity_w.toFixed(0) }) }}
            {{ t('asset.form.cabinetRemainingPower', { free: cabinetInfo.usage.free_power_w.toFixed(0) }) }}
            <span v-if="powerExceeded" class="exceed">
              {{ t('asset.form.powerWarning', { power: form.power_watts }) }}
            </span>
            <span v-else-if="uExceeded" class="exceed">
              {{ t('asset.form.uOutOfRangeWarning') }}
            </span>
          </template>
        </el-alert>

        <el-divider content-position="left">{{ t('asset.form.assetInfoOptional') }}</el-divider>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="t('asset.form.vendor')">
              <div class="vendor-select-row">
                <el-select
                  v-model="form.vendor"
                  filterable
                  allow-create
                  clearable
                  default-first-option
                  :reserve-keyword="false"
                  :placeholder="t('asset.form.vendorSelectPlaceholder')"
                  class="vendor-select"
                >
                  <el-option v-for="item in vendorOptions" :key="item" :label="item" :value="item" />
                </el-select>
                <el-button size="small" plain type="primary" class="vendor-add-btn" @click="addCustomVendor">
                  {{ t('asset.form.addVendor') }}
                </el-button>
              </div>
              <div class="form-help vendor-help">{{ t('asset.form.vendorAddHint') }}</div>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('asset.form.model')">
              <el-input v-model="form.model" placeholder="S5735" />
            </el-form-item>
          </el-col>
        </el-row>

        <template v-if="isDellStorage">
          <el-alert type="info" :closable="false" show-icon class="storage-api-hint"
            title="戴尔存储 SNMP 通常只提供 MIB-II，CPU、温度、风扇、电源、磁盘健康需使用只读账号通过 HTTPS API 采集。" />
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item label="存储只读账号">
                <el-input v-model="form.storage_username" placeholder="例如 snmp-user" autocomplete="off" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="存储只读密码">
                <el-input v-model="form.storage_password" type="password" show-password autocomplete="new-password"
                  :placeholder="passwordSet.storage ? '已保存，留空不修改' : '输入只读密码'" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="存储 API 端口">
            <el-input-number v-model="form.storage_api_port" :min="1" :max="65535" controls-position="right" style="width: 160px" />
            <span class="storage-api-port-tip">默认 HTTPS 443，仅执行只读 GET</span>
          </el-form-item>
        </template>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="t('asset.form.serialNumber')">
              <el-input v-model="form.serial_number" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('asset.form.monitorEnabled')">
              <el-switch v-model="form.is_enabled" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item :label="t('asset.form.description')">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>

        <el-divider content-position="left">{{ t('asset.form.maintenanceOptional') }}</el-divider>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="t('asset.form.assetNo')">
              <el-input v-model="form.asset_no" :placeholder="t('asset.form.assetNoPlaceholder')" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('asset.form.purchaseDate')">
              <el-date-picker
                v-model="form.purchase_date"
                type="date"
                value-format="YYYY-MM-DD"
                :placeholder="t('asset.form.selectDate')"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="维保开始时间">
              <el-date-picker
                v-model="form.warranty_start"
                type="date"
                value-format="YYYY-MM-DD"
                :placeholder="t('asset.form.selectDate')"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('asset.form.maintenanceExpiry')">
              <el-date-picker
                v-model="form.warranty_until"
                type="date"
                value-format="YYYY-MM-DD"
                :placeholder="t('asset.form.selectDate')"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="t('asset.form.maintenanceVendor')">
              <el-input v-model="form.maintenance_vendor" :placeholder="t('asset.form.vendorPlaceholder')" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('asset.form.maintenanceContact')">
              <el-input v-model="form.maintenance_contact" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="t('asset.form.maintenancePhone')">
              <el-input v-model="form.maintenance_phone" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="handleSubmit">
            {{ isEdit ? '保存并返回列表' : isCopy ? t('asset.form.createFromCopy') : t('asset.form.create') }}
          </el-button>
          <el-button @click="returnToList">{{ t('common.cancel') }}</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- OID 自动识别结果 -->
    <el-dialog v-model="recVisible" :title="t('asset.form.autoDetectCollectOid')" width="820px">
      <el-alert
        type="success"
        :closable="false"
        show-icon
        class="rec-tip"
        :title="t('asset.form.customOidTooltip')"
      />
      <el-row :gutter="12">
        <el-col v-for="meta in METRIC_META" :key="meta.key" :span="12" class="rec-col">
          <div class="rec-card">
            <div class="rec-title">
              <el-tag size="small" :type="meta.type">{{ meta.label }}</el-tag>
              <span v-if="form.custom_oids[meta.key]" class="rec-chosen">
                {{ t('asset.form.selectedMetric', { value: metricName(form.custom_oids[meta.key]) || form.custom_oids[meta.key] }) }}
              </span>
            </div>
            <div v-if="recommendations[meta.key]?.length" class="rec-list">
              <div
                v-for="item in recommendations[meta.key]"
                :key="item.oid"
                class="rec-item"
                :class="{ active: form.custom_oids[meta.key] === item.oid }"
                @click="pickOid(meta.key, item.oid)"
              >
                <div class="rec-name">
                  {{ item.name }}
                  <el-tag v-if="autoMap[meta.key]?.oid === item.oid" size="small" type="success" effect="dark">
                    {{ t('asset.form.autoRecommend') }}
                  </el-tag>
                </div>
                <div class="rec-oid">{{ item.oid }}</div>
              </div>
            </div>
            <div v-else class="muted">{{ t('asset.form.mibNoOidMetric', { metric: meta.label }) }}</div>
          </div>
        </el-col>
      </el-row>
      <template #footer>
        <el-button @click="recVisible = false">{{ t('asset.form.done') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { t } from '@/i18n'
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { assetApi, roomApi, mibApi } from '@/api'
import { DEVICE_TYPE_OPTIONS, VENDOR_OPTIONS } from '@/constants/device'
import IconPickerDialog from '@/components/IconPickerDialog.vue'
import IconCropper from '@/components/IconCropper.vue'

const router = useRouter()
const route = useRoute()

function returnQuery() {
  const query = {}
  for (const key of ['page', 'size', 'search', 'device_type', 'group_id']) {
    const value = route.query[key]
    if (typeof value === 'string' && value) query[key] = value
  }
  return query
}

function returnToList() {
  router.push({ path: '/devices', query: returnQuery() })
}
const formRef = ref(null)
const submitting = ref(false)
const savingStay = ref(false)
const testing = ref(false)
const testResult = ref(null)
const passwordSet = reactive({ auth: false, priv: false, storage: false })

// 自定义图标
const iconInputRef = ref(null)
const iconUploading = ref(false)
const presetVisible = ref(false)
const cropperVisible = ref(false)
const cropSrc = ref('')
let iconPresetsCache = null
// MIB 模板 / 自定义指标
const templateLoading = ref(false)
const metricPickerVisible = ref(false)
const metricKeyword = ref('')
const metricObjects = ref([])
const metricLoading = ref(false)
let templateTimer = null

// MIB 采集优化
const METRIC_META = [
  { key: 'cpu', label: 'CPU', type: 'danger' },
  { key: 'memory', get label() { return t('asset.form.memory') }, type: 'warning' },
  { key: 'temperature', get label() { return t('asset.form.temperature') }, type: 'success' },
  { key: 'power', get label() { return t('asset.form.power') }, type: 'info' },
]
const mibOptions = ref([])
const mibObjects = ref([])
const recLoading = ref(false)
const recVisible = ref(false)
const recommendations = ref({})
const autoMap = ref({})

const hasCustomOids = computed(() =>
  Object.values(form.custom_oids || {}).some((v) => !!v)
)

function metricName(oid) {
  if (!oid) return ''
  const obj = mibObjects.value.find((o) => o.oid === oid)
  return obj ? obj.name : ''
}

// 机房 / 机柜
const rooms = ref([])
const cabinets = ref([])
const selectedRoomId = ref(null)
const cabinetInfo = ref(null)
// 资产群组
const groupOptions = ref([])

async function loadGroups() {
  try {
    const res = await assetApi.groups()
    groupOptions.value = res.data.items || []
  } catch {
    groupOptions.value = []
  }
}

async function createGroupInline() {
  let name = ''
  try {
    const result = await ElMessageBox.prompt(
      t('asset.form.newGroupPrompt'),
      t('asset.form.newGroupTitle'),
      {
        confirmButtonText: t('asset.form.newGroupConfirm'),
        cancelButtonText: t('common.cancel'),
        inputPlaceholder: t('asset.form.newGroupPlaceholder'),
        inputValidator: (value) => Boolean(String(value || '').trim()) || t('asset.form.newGroupRequired'),
      },
    )
    name = String(result.value || '').trim()
  } catch {
    return
  }
  try {
    const { data } = await assetApi.createGroup({ name })
    if (!groupOptions.value.some((item) => item.id === data.id)) {
      groupOptions.value.push(data)
    }
    form.group_id = data.id
    ElMessage.success(t('asset.form.newGroupSuccess', { name: data.name }))
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error?.message || t('asset.form.newGroupFailed'))
  }
}

const isCopy = computed(() => route.name === 'CopyDevice' && !!route.params.id)
const isEdit = computed(() => route.name === 'EditDevice' && !!route.params.id)

const SERVER_SENSOR_DEFS = [
  { key: 'srv_cpu_temp', name: 'CPU 温度', unit: '°C', kind: 'temperature' },
  { key: 'srv_mem_fault', name: '内存物理状态', unit: '', kind: 'fault' },
  { key: 'srv_power_voltage', name: '电源电压', unit: 'V', kind: 'voltage' },
  { key: 'srv_power_current', name: '电源电流', unit: 'A', kind: 'current' },
  { key: 'srv_power_watts', name: '电源功率', unit: 'W', kind: 'watts' },
  { key: 'srv_disk_fault', name: '硬盘状态', unit: '', kind: 'fault' },
  { key: 'srv_disk_usage', name: '硬盘使用率', unit: '%', kind: 'percent' },
  { key: 'srv_inlet_temp', name: '进气温度', unit: '°C', kind: 'temperature' },
  { key: 'srv_exhaust_temp', name: '排气温度', unit: '°C', kind: 'temperature' },
  { key: 'srv_fan_speed', name: '风扇转速', unit: 'RPM', kind: 'value' },
  { key: 'srv_fan_fault', name: '风扇状态', unit: '', kind: 'fault' },
]

function defaultServerSensors() {
  return SERVER_SENSOR_DEFS.map((item) => ({
    ...item,
    oid: '',
    scale: 1,
  }))
}

function normalizeServerSensors(saved) {
  const byKey = new Map((Array.isArray(saved) ? saved : []).map((item) => [item.key, item]))
  return SERVER_SENSOR_DEFS.map((def) => {
    const existing = byKey.get(def.key) || {}
    return {
      ...def,
      oid: existing.oid || '',
      scale: Number(existing.scale) || 1,
      name: existing.name || def.name,
      unit: existing.unit ?? def.unit,
    }
  })
}

const form = reactive({
  name: '',
  ip_address: '',
  device_type: '',
  monitor_type: 'snmp',
  tcp_port: 80,
  snmp_version: 'v2c',
  community: 'public',
  port: 161,
  v3_username: '',
  v3_security_level: 'authPriv',
  v3_auth_protocol: 'SHA',
  v3_auth_password: '',
  v3_priv_protocol: 'AES',
  v3_priv_password: '',
  v3_context_name: '',
  storage_username: '',
  storage_password: '',
  storage_api_port: 443,
  location: '',
  vendor: '',
  model: '',
  serial_number: '',
  description: '',
  // 维保 / 资产标签
  asset_no: '',
  purchase_date: null,
  warranty_start: null,
  warranty_until: null,
  maintenance_vendor: '',
  maintenance_contact: '',
  maintenance_phone: '',
  is_enabled: true,
  tags: [],
  icon: null,
  // MIB 采集优化
  mib_id: null,
  custom_oids: { cpu: '', memory: '', temperature: '', power: '' },
  custom_metrics: [],
  server_sensors: defaultServerSensors(),
  // 机柜上架
  cabinet_id: null,
  u_position: null,
  u_height: 1,
  power_watts: 0,
  group_id: null,
})

// 编辑设备连续操作：当前资产列表中的上一台 / 下一台
const navLoading = ref(false)
const navDevices = ref([])
const currentNavIndex = computed(() => {
  if (!isEdit.value) return -1
  return navDevices.value.findIndex((item) => String(item.id) === String(route.params.id))
})
const prevDevice = computed(() => {
  const index = currentNavIndex.value
  return index > 0 ? navDevices.value[index - 1] : null
})
const nextDevice = computed(() => {
  const index = currentNavIndex.value
  return index >= 0 && index < navDevices.value.length - 1 ? navDevices.value[index + 1] : null
})
const formDefaults = JSON.parse(JSON.stringify(form))
const isDellStorage = computed(() => (
  form.device_type === 'storage' && /dell|戴尔/i.test(String(form.vendor || ''))
))
const isDellStorageApi = computed(() => isDellStorage.value && /ME|POWERVAULT/i.test(String(form.model || '')))
let initialSnapshot = JSON.stringify(form)

async function loadNavDevices() {
  if (!isEdit.value) return
  navLoading.value = true
  try {
    const items = []
    let total = 0
    for (let page = 1; page <= 50; page += 1) {
      const res = await assetApi.getList({ page, size: 100 })
      total = Number(res.data.total) || 0
      const batch = res.data.items || []
      items.push(...batch.map((item) => ({ id: item.id, name: item.name, ip_address: item.ip_address })))
      if (!batch.length || items.length >= total) break
    }
    navDevices.value = items
  } catch {
    navDevices.value = []
  } finally {
    navLoading.value = false
  }
}

async function goPrevDevice() {
  if (!prevDevice.value) return
  if (JSON.stringify(form) !== initialSnapshot) {
    try {
      await ElMessageBox.confirm('当前设备有未保存修改，继续上一台将丢弃这些修改。是否继续？', '上一台设备', {
        type: 'warning', confirmButtonText: '继续上一台', cancelButtonText: '留在当前设备',
      })
    } catch {
      return
    }
  }
  await router.push({ path: `/devices/edit/${prevDevice.value.id}`, query: returnQuery() })
}

async function goNextDevice() {
  if (!nextDevice.value) return
  if (JSON.stringify(form) !== initialSnapshot) {
    try {
      await ElMessageBox.confirm('当前设备有未保存修改，继续下一台将丢弃这些修改。是否继续？', '下一台设备', {
        type: 'warning', confirmButtonText: '继续下一台', cancelButtonText: '留在当前设备',
      })
    } catch {
      return
    }
  }
  await router.push({ path: `/devices/edit/${nextDevice.value.id}`, query: returnQuery() })
}

// 前端即时提示（最终以后端校验为准）
const powerExceeded = computed(() => {
  if (!cabinetInfo.value) return false
  const free = cabinetInfo.value.usage.free_power_w
  return Number(form.power_watts || 0) > free + 1e-6
})

const uExceeded = computed(() => {
  if (!cabinetInfo.value) return false
  const cap = cabinetInfo.value.u_capacity || 42
  const start = Number(form.u_position || 0)
  const height = Number(form.u_height || 1)
  if (!start) return false
  return start + height - 1 > cap
})

function formatU(value) {
  return String(Math.max(1, Number(value) || 1)).padStart(2, '0')
}

const occupiedU = computed(() => {
  const result = new Set()
  if (!cabinetInfo.value) return result
  const currentDeviceId = isEdit.value ? Number(route.params.id) : null
  for (const device of cabinetInfo.value.devices || []) {
    if (currentDeviceId && Number(device.id) === currentDeviceId) continue
    const start = Math.max(1, Number(device.u_position) || 1)
    const height = Math.max(1, Number(device.u_height) || 1)
    for (let u = start; u < start + height; u += 1) result.add(u)
  }
  return result
})

const uPositionOptions = computed(() => {
  const capacity = Math.max(1, Number(cabinetInfo.value?.u_capacity) || 42)
  return Array.from({ length: capacity }, (_, index) => {
    const value = index + 1
    const occupied = occupiedU.value.has(value)
    return {
      value,
      label: `${formatU(value)}U${occupied ? '（已占用）' : ''}`,
      occupied,
    }
  })
})

const uRangeConflict = computed(() => {
  if (!form.u_position) return false
  const start = Number(form.u_position)
  const height = Math.max(1, Number(form.u_height) || 1)
  for (let u = start; u < start + height; u += 1) {
    if (occupiedU.value.has(u)) return true
  }
  return false
})

const uRangeLabel = computed(() => {
  if (!form.u_position) return '未指定，保存时自动分配最低空闲 U 位'
  const start = Number(form.u_position)
  const height = Math.max(1, Number(form.u_height) || 1)
  const end = start + height - 1
  return end > start ? `${formatU(start)}U - ${formatU(end)}U（${height}U）` : `${formatU(start)}U`
})

const rules = computed(() => ({
  name: [{ required: true, message: t('asset.form.deviceNameRequired'), trigger: 'blur' }],
  ip_address: [
    { required: true, message: t('asset.form.ipRequired'), trigger: 'blur' },
    {
      pattern: /^(\d{1,3}\.){3}\d{1,3}$/,
      message: t('asset.form.validIpRequired'),
      trigger: 'blur',
    },
  ],
  device_type: [{ required: true, message: t('asset.form.deviceTypeRequired'), trigger: 'change' }],
  tcp_port: form.monitor_type === 'tcp'
    ? [{ required: true, message: '请输入 TCP 探测端口', trigger: 'change' }]
    : [],
  snmp_version: form.monitor_type === 'snmp'
    ? [{ required: true, message: t('asset.form.snmpVersionRequired'), trigger: 'change' }]
    : [],
  community:
    form.monitor_type === 'snmp' && form.snmp_version !== 'v3'
      ? [{ required: true, message: t('asset.form.communityRequired'), trigger: 'blur' }]
      : [],
  v3_username:
    form.monitor_type === 'snmp' && form.snmp_version === 'v3'
      ? [{ required: true, message: t('asset.form.v3UsernameRequired'), trigger: 'blur' }]
      : [],
}))

function passwordPlaceholder(kind) {
  const set = kind === 'auth' ? passwordSet.auth : passwordSet.priv
  return set ? t('asset.form.configuredKeepHint') : t('asset.form.passwordRequired')
}

async function loadDevice() {
  if (!isEdit.value && !isCopy.value) return
  try {
    Object.assign(form, JSON.parse(JSON.stringify(formDefaults)))
    selectedRoomId.value = null
    cabinetInfo.value = null
    passwordSet.auth = false
    passwordSet.priv = false
    passwordSet.storage = false
    testResult.value = null
    const res = await assetApi.getOne(route.params.id)
    const d = res.data
    const copyName = (value) => `${String(value || '设备').slice(0, 90)}${t('asset.form.copySuffix')}`
    Object.assign(form, {
      name: isCopy.value ? copyName(d.name) : d.name,
      ip_address: isCopy.value ? '' : d.ip_address,
      device_type: d.device_type,
      monitor_type: d.monitor_type || 'snmp',
      tcp_port: d.tcp_port || 80,
      snmp_version: d.snmp_version || 'v2c',
      community: d.community || 'public',
      port: d.port || 161,
      v3_username: d.v3_username || '',
      v3_security_level: d.v3_security_level || 'authPriv',
      v3_auth_protocol: d.v3_auth_protocol || 'SHA',
      v3_priv_protocol: d.v3_priv_protocol || 'AES',
      v3_context_name: d.v3_context_name || '',
      storage_username: d.storage_username || '',
      storage_password: '',
      storage_api_port: d.storage_api_port || 443,
      location: d.location || '',
      vendor: d.vendor || '',
      model: d.model || '',
      serial_number: isCopy.value ? '' : d.serial_number || '',
      description: d.description || '',
      asset_no: isCopy.value ? '' : d.asset_no || '',
      purchase_date: isCopy.value ? null : d.purchase_date || null,
      warranty_start: isCopy.value ? null : d.warranty_start || null,
      warranty_until: isCopy.value ? null : d.warranty_until || null,
      maintenance_vendor: d.maintenance_vendor || '',
      maintenance_contact: d.maintenance_contact || '',
      maintenance_phone: d.maintenance_phone || '',
      is_enabled: d.is_enabled !== false,
      tags: d.tags || [],
      icon: d.icon || null,
      mib_id: d.mib_id || null,
          custom_oids: {
        cpu: d.custom_oids?.cpu || '',
        memory: d.custom_oids?.memory || '',
        temperature: d.custom_oids?.temperature || '',
        power: d.custom_oids?.power || '',
      },
      custom_metrics: (d.custom_metrics || []).map((item) => ({
        key: item.key || '',
        name: item.name || '',
        oid: item.oid || '',
        unit: item.unit || '',
        scale: item.scale ?? 1,
      })),
      server_sensors: normalizeServerSensors(d.server_sensors),
      cabinet_id: d.cabinet_id || null,
      u_position: isCopy.value ? null : d.u_position ?? null,
      u_height: d.u_height || 1,
      power_watts: d.power_watts || 0,
      group_id: d.group_id || null,
    })
    passwordSet.auth = false
    passwordSet.priv = false
    if (!isCopy.value) {
      passwordSet.auth = !!d.v3_auth_password_set
      passwordSet.priv = !!d.v3_priv_password_set
      passwordSet.storage = !!d.storage_password_set
    }
    testResult.value = null

    initialSnapshot = JSON.stringify(form)
    // 恢复机房与机柜选择
    if (d.cabinet_id) {
      await loadRooms()
      const cab = d.cabinet || {}
      if (cab.room_id) {
        selectedRoomId.value = cab.room_id
        await loadCabinets(cab.room_id, true)
        cabinetInfo.value = cabinets.value.find((c) => c.id === d.cabinet_id) || null
      }
    }
  } catch (e) {
    ElMessage.error(e.message || t('asset.form.loadDeviceFailed'))
  }
}

// ---------- 机房 / 机柜 ----------
async function loadRooms() {
  try {
    const res = await roomApi.list()
    rooms.value = res.data
  } catch (e) {
    console.error('加载机房失败', e)
  }
}

async function loadCabinets(roomId, keepSelection = false) {
  if (!roomId) {
    cabinets.value = []
    cabinetInfo.value = null
    return
  }
  try {
    const res = await roomApi.listCabinets(roomId)
    cabinets.value = res.data
    if (!keepSelection) {
      form.cabinet_id = null
      cabinetInfo.value = null
    } else if (form.cabinet_id) {
      cabinetInfo.value = cabinets.value.find((c) => c.id === form.cabinet_id) || null
    }
  } catch (e) {
    ElMessage.error(e.message || t('asset.form.loadCabinetsFailed'))
  }
}

async function onRoomChange(roomId) {
  form.cabinet_id = null
  form.u_position = null
  cabinetInfo.value = null
  await loadCabinets(roomId)
}

function onCabinetChange(cabinetId) {
  cabinetInfo.value = cabinets.value.find((c) => c.id === cabinetId) || null
  // 切换机柜后 U 位必须重新选择，避免沿用上一个机柜的 U 位
  form.u_position = null
  form.u_height = 1
}

// ---------- 自定义图标 ----------
function pickIcon() {
  iconInputRef.value?.click()
}

async function onIconSelected(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return

  const name = (file.name || '').toLowerCase()
  const allowed = ['.png', '.jpg', '.jpeg', '.gif', '.webp']
  if (!allowed.some((ext) => name.endsWith(ext))) {
    ElMessage.error(t('asset.form.iconFormatUnsupported'))
    return
  }
  if (file.size > 2 * 1024 * 1024) {
    ElMessage.error(t('asset.form.iconTooLarge'))
    return
  }

  // 位图先进入裁剪/缩放对话框；SVG/GIF 保持原样直接上传
  const raster = ['.png', '.jpg', '.jpeg', '.webp'].some((ext) => name.endsWith(ext))
  if (raster) {
    const reader = new FileReader()
    reader.onload = () => {
      cropSrc.value = String(reader.result || '')
      if (cropSrc.value) cropperVisible.value = true
    }
    reader.readAsDataURL(file)
    return
  }

  await uploadIconFile(file)
}

async function uploadIconFile(file) {
  iconUploading.value = true
  try {
    const formData = new FormData()
    formData.append('file', file)
    const res = await assetApi.uploadIcon(formData)
    form.icon = res.data.url
    ElMessage.success(t('asset.form.iconUploadedHint'))
  } catch (e) {
    ElMessage.error(e.message || t('asset.form.iconUploadFailed'))
  } finally {
    iconUploading.value = false
  }
}

async function onCropDone(file) {
  await uploadIconFile(file)
}

function onPresetSelect(url) {
  form.icon = url
  ElMessage.success(t('asset.form.builtInIconSelectedHint'))
}

function openCropper() {
  if (!form.icon || !form.icon.startsWith('/uploads/icons/')) {
    ElMessage.info(t('asset.form.builtInNoCropHint'))
    return
  }
  cropSrc.value = form.icon
  cropperVisible.value = true
}

async function loadIconPresets() {
  if (iconPresetsCache) return iconPresetsCache
  try {
    const res = await assetApi.iconPresets()
    iconPresetsCache = res.data
    return iconPresetsCache
  } catch {
    return null
  }
}

const customVendors = ref([])
const vendorOptions = computed(() => {
  const values = [...VENDOR_OPTIONS, ...customVendors.value]
  if (form.vendor && !values.includes(form.vendor)) values.push(form.vendor)
  return [...new Set(values)]
})

async function addCustomVendor() {
  try {
    const { value } = await ElMessageBox.prompt(
      t('asset.form.vendorAddPrompt'),
      t('asset.form.addVendor'),
      {
        inputPlaceholder: t('asset.form.vendorAddPlaceholder'),
        inputPattern: /^[\s\S]{1,80}$/,
        inputErrorMessage: t('asset.form.vendorAddInvalid'),
      },
    )
    const name = String(value || '').trim()
    if (!name) return
    if (!VENDOR_OPTIONS.includes(name) && !customVendors.value.includes(name)) {
      customVendors.value.push(name)
    }
    form.vendor = name
  } catch {
    /* 取消 */
  }
}

/** 按厂商自动匹配图标；silent=true 用于供应商输入后自动套用 */
async function autoMatchIcon(silent = false) {
  const data = await loadIconPresets()
  if (!data) {
    if (!silent) ElMessage.error(t('asset.form.iconLibraryLoadFailed'))
    return
  }
  const vendor = String(form.vendor || '').trim().toLowerCase()
  let url = null
  if (vendor) {
    for (const rule of data.vendor_rules || []) {
      if ((rule.keys || []).some((key) => vendor.includes(String(key).toLowerCase()))) {
        url = rule.preset_url
        break
      }
    }
  }
  if (!url) {
    const preset = (data.presets || []).find(
      (p) => p.category === 'type' && p.device_type === form.device_type
    )
    url = preset?.url || null
  }
  if (!url) {
    if (!silent) ElMessage.warning(t('asset.form.noMatchingIcon'))
    return false
  }
  form.icon = url
  ElMessage.success(silent ? t('asset.form.iconMatchedByVendor') : t('asset.form.iconMatchedByVendorType'))
  return true
}

watch(
  () => form.vendor,
  (vendor) => {
    if (vendor && !form.icon) autoMatchIcon(true)
  }
)

watch(
  () => form.device_type,
  () => {
    if (!form.icon) autoMatchIcon(true)
  }
)

function pickOid(key, oid) {
  form.custom_oids[key] = oid
}

async function loadMibs() {
  try {
    const res = await mibApi.list()
    mibOptions.value = res.data.items
  } catch {
    mibOptions.value = []
  }
}

async function onMibChange(id) {
  mibObjects.value = []
  if (!id) return
  try {
    const res = await mibApi.objects(id, { size: 500 })
    mibObjects.value = res.data.items
  } catch {
    /* 忽略 */
  }
}

async function autoDetectOids() {
  if (!form.mib_id) return
  recLoading.value = true
  try {
    const res = await mibApi.get(form.mib_id)
    recommendations.value = res.data.recommendations || {}
    autoMap.value = res.data.auto_map || {}

    for (const meta of METRIC_META) {
      const best = autoMap.value[meta.key]
      if (best?.oid) form.custom_oids[meta.key] = best.oid
    }

    const objRes = await mibApi.objects(form.mib_id, { size: 500 })
    mibObjects.value = objRes.data.items

    recVisible.value = true
    const count = METRIC_META.filter((m) => form.custom_oids[m.key]).length
    if (count) ElMessage.success(t('asset.form.autoDetectedFilled', { count }))
    else ElMessage.warning(t('asset.form.mibNoMetricsHint'))
  } catch (e) {
    ElMessage.error(e.message || t('asset.form.autoDetectFailed'))
  } finally {
    recLoading.value = false
  }
}

// ---------- 自定义指标 / MIB 模板 ----------
function addCustomMetric() {
  form.custom_metrics.push({ key: '', name: '', oid: '', unit: '', scale: 1 })
}

function removeCustomMetric(row) {
  const index = form.custom_metrics.indexOf(row)
  if (index >= 0) form.custom_metrics.splice(index, 1)
}

function sanitizeMetricKey(name) {
  const key = String(name || '')
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 30)
  return key || `metric_${Date.now() % 100000}`
}

function openMetricPicker() {
  if (!form.mib_id) {
    ElMessage.warning(t('asset.form.selectMibFirst'))
    return
  }
  metricPickerVisible.value = true
  metricKeyword.value = ''
  loadMetricObjects()
}

async function loadMetricObjects() {
  metricLoading.value = true
  try {
    const params = { size: 100 }
    if (metricKeyword.value.trim()) params.keyword = metricKeyword.value.trim()
    const res = await mibApi.objects(form.mib_id, params)
    metricObjects.value = res.data.items || []
  } catch (e) {
    ElMessage.error(e.message || t('mib.loadMibObjectsFailed'))
  } finally {
    metricLoading.value = false
  }
}

function addMetricFromObject(row) {
  const key = sanitizeMetricKey(row.name)
  if (form.custom_metrics.some((item) => item.key === key)) {
    ElMessage.info(t('asset.form.metricExists'))
    return
  }
  let unit = ''
  if (row.category === 'optical') unit = 'dBm'
  else if (row.category === 'fan') unit = 'RPM'
  form.custom_metrics.push({
    key, name: row.name, oid: row.oid, unit, scale: 1,
  })
  ElMessage.success(t('asset.form.metricAdded', { name: row.name }))
}

async function testOidValue(oid) {
  if (!oid) {
    ElMessage.warning(t('mib.enterOid'))
    return
  }
  const payload = { oid }
  if (isEdit.value) {
    payload.device_id = route.params.id
  } else {
    if (!form.ip_address) {
      ElMessage.warning(t('asset.form.ipRequiredForTest'))
      return
    }
    payload.ip_address = form.ip_address
    payload.community = form.community
    payload.snmp_version = form.snmp_version
    payload.port = form.port
    if (form.snmp_version === 'v3') {
      payload.v3_username = form.v3_username
      payload.v3_security_level = form.v3_security_level
      payload.v3_auth_protocol = form.v3_auth_protocol
      payload.v3_auth_password = form.v3_auth_password
      payload.v3_priv_protocol = form.v3_priv_protocol
      payload.v3_priv_password = form.v3_priv_password
    }
  }
  try {
    const res = await assetApi.testOid(payload)
    const r = res.data
    if (r.ok) {
      ElMessageBox.alert(
        t('mib.testOk', { value: r.value, numeric: r.numeric ?? '-', ms: r.elapsed_ms }),
        t('mib.testOidTitle'),
        { type: 'success' }
      )
    } else {
      ElMessageBox.alert(r.error || t('mib.testFailed'), t('mib.testOidTitle'), { type: 'error' })
    }
  } catch (e) {
    ElMessage.error(e.message || t('mib.testFailed'))
  }
}

async function matchMibTemplate(silent = false) {
  if (!form.vendor && !form.model) {
    if (!silent) ElMessage.warning(t('asset.form.vendorRequiredForTemplate'))
    return
  }
  templateLoading.value = true
  try {
    const params = {
      vendor: form.vendor,
      model: form.model,
      device_type: form.device_type,
    }
    if (isEdit.value) params.device_id = route.params.id
    const res = await mibApi.matchTemplate(params)
    const data = res.data
    if (!data.matched) {
      if (!silent) ElMessage.warning(t('asset.form.templateNotFound'))
      return
    }
    const preview = data.preview || {}
    const matched = preview.matched_metrics || {}
    const customs = preview.custom_metrics || []

    if (isEdit.value) {
      if (!silent) {
        await ElMessageBox.confirm(
          t('asset.form.templateApplyConfirm', { name: data.template.name }),
          t('asset.form.matchMibTemplate'),
          { type: 'warning' }
        )
      }
      await mibApi.applyTemplate({
        device_id: route.params.id,
        template_id: data.template.id,
        overwrite: false,
      })
      await loadDevice()
      ElMessage.success(t('asset.form.templateApplied', { name: data.template.name }))
    } else {
      if (preview.mib_id) form.mib_id = preview.mib_id
      for (const [key, info] of Object.entries(matched)) {
        if (info?.oid) form.custom_oids[key] = info.oid
      }
      for (const item of customs) {
        if (form.custom_metrics.some((m) => m.key === item.key)) continue
        form.custom_metrics.push({
          key: item.key,
          name: item.name,
          oid: item.oid,
          unit: item.unit || '',
          scale: item.scale || 1,
        })
      }
      const count = Object.keys(matched).length + customs.length
      ElMessage.success(
        count
          ? t('asset.form.templateFilled', { name: data.template.name, count })
          : t('asset.form.templateNoMetrics', { name: data.template.name })
      )
    }
  } catch (e) {
    if (e !== 'cancel' && !silent) {
      ElMessage.error(e.message || t('asset.form.templateFailed'))
    }
  } finally {
    templateLoading.value = false
  }
}

// 新设备填写厂商/型号后自动匹配模板（只在没有任何自定义配置时）
watch(
  [() => form.vendor, () => form.model],
  () => {
    if (isEdit.value) return
    if (!form.vendor || !form.model || form.mib_id || hasCustomOids.value || form.custom_metrics.length) return
    clearTimeout(templateTimer)
    templateTimer = setTimeout(() => {
      if (form.vendor && !form.mib_id) matchMibTemplate(true)
    }, 800)
  }
)

async function testConnection() {
  testing.value = true
  testResult.value = null
  try {
    if (form.monitor_type !== 'snmp') {
      const res = await assetApi.testProbe({
        host: form.ip_address,
        monitor_type: form.monitor_type,
        tcp_port: form.tcp_port,
        timeout: 5,
      })
      testResult.value = { ...res.data, method: form.monitor_type }
      if (res.data.reachable) ElMessage.success(`${form.monitor_type === 'tcp' ? 'TCP' : 'Ping'} 探测成功：${res.data.latency_ms}ms`)
      else ElMessage.warning(res.data.error || '探测失败，请检查地址或端口')
      return
    }
    let payload
    if (isEdit.value) {
      payload = { device_id: Number(route.params.id) }
    } else {
      payload = {
        ip_address: form.ip_address,
        snmp_version: form.snmp_version,
        port: form.port,
        community: form.community,
        timeout: 5,
      }
      if (form.snmp_version === 'v3') {
        Object.assign(payload, {
          v3_username: form.v3_username,
          v3_security_level: form.v3_security_level,
          v3_auth_protocol: form.v3_auth_protocol,
          v3_auth_password: form.v3_auth_password || undefined,
          v3_priv_protocol: form.v3_priv_protocol,
          v3_priv_password: form.v3_priv_password || undefined,
          v3_context_name: form.v3_context_name || undefined,
        })
      }
    }
    const res = await assetApi.testSnmp(payload)
    testResult.value = { ...res.data, method: 'snmp' }
    if (res.data.reachable) ElMessage.success(t('asset.form.snmpOk'))
    else ElMessage.warning(t('asset.form.snmpFailHint'))
  } catch (e) {
    testResult.value = { reachable: false, method: form.monitor_type, error: e.message }
    ElMessage.error(e.message || t('asset.form.testFailed'))
  } finally {
    testing.value = false
  }
}

function buildPayload() {
  const payload = {
    name: form.name,
    ip_address: form.ip_address,
    device_type: form.device_type,
    monitor_type: form.monitor_type,
    tcp_port: form.tcp_port,
    snmp_version: form.snmp_version,
    community: form.community,
    port: form.port,
    location: form.location,
    vendor: form.vendor,
    model: form.model,
    serial_number: form.serial_number,
    description: form.description,
    asset_no: form.asset_no || null,
    purchase_date: form.purchase_date || null,
    warranty_start: form.warranty_start || null,
    warranty_until: form.warranty_until || null,
    maintenance_vendor: form.maintenance_vendor || null,
    maintenance_contact: form.maintenance_contact || null,
    maintenance_phone: form.maintenance_phone || null,
    is_enabled: form.is_enabled,
    tags: form.tags || [],
    icon: form.icon || null,
    mib_id: form.mib_id || null,
    custom_oids: Object.fromEntries(
      Object.entries(form.custom_oids || {}).filter(([, v]) => v && v.trim())
    ),
    custom_metrics: (form.custom_metrics || []).filter(
      (item) => item.key && item.oid
    ),
    server_sensors: (form.server_sensors || []).filter(
      (item) => item.key && item.oid
    ).map((item) => ({
      key: item.key,
      name: item.name,
      oid: item.oid,
      unit: item.unit,
      scale: Number(item.scale) || 1,
      kind: item.kind || 'value',
    })),
    cabinet_id: form.cabinet_id || null,
    u_position: form.cabinet_id ? (form.u_position || null) : null,
    u_height: form.u_height || 1,
    power_watts: Number(form.power_watts || 0),
    group_id: form.group_id || null,
    storage_username: form.storage_username || null,
    storage_api_port: Number(form.storage_api_port || 443),
  }
  if (form.storage_password) payload.storage_password = form.storage_password
  if (form.snmp_version === 'v3') {
    Object.assign(payload, {
      v3_username: form.v3_username,
      v3_security_level: form.v3_security_level,
      v3_auth_protocol: form.v3_auth_protocol,
      v3_priv_protocol: form.v3_priv_protocol,
      v3_context_name: form.v3_context_name || null,
    })
    // 密码留空表示不修改（编辑场景）
    if (form.v3_auth_password) payload.v3_auth_password = form.v3_auth_password
    if (form.v3_priv_password) payload.v3_priv_password = form.v3_priv_password
  }
  return payload
}

async function saveCurrent() {
  if (!isEdit.value || !formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    savingStay.value = true
    try {
      await assetApi.update(route.params.id, buildPayload())
      ElMessage.success('当前设备已保存，仍停留在编辑页')
      await loadDevice()
      await loadNavDevices()
    } catch (e) {
      ElMessage.error(e.message || t('asset.form.operationFailed'))
    } finally {
      savingStay.value = false
    }
  })
}

async function handleSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    submitting.value = true
    try {
      if (isEdit.value) {
        await assetApi.update(route.params.id, buildPayload())
        ElMessage.success(t('asset.form.deviceUpdated'))
      } else {
        await assetApi.create(buildPayload())
        ElMessage.success(t('asset.form.deviceCreated'))
      }
      returnToList()
    } catch (e) {
      ElMessage.error(e.message || t('asset.form.operationFailed'))
    } finally {
      submitting.value = false
    }
  })
}

watch(
  () => route.params.id,
  async (id, oldId) => {
    if (!id || id === oldId || !isEdit.value) return
    await loadDevice()
    if (!navDevices.value.some((item) => String(item.id) === String(id))) {
      await loadNavDevices()
    }
  }
)

onMounted(async () => {
  await loadGroups()
  await loadRooms()
  await loadMibs()
  await loadDevice()
  await loadNavDevices()
})
</script>

<style scoped>
.storage-api-hint { margin: 4px 0 14px; }
.storage-api-port-tip { margin-left: 10px; color: #8a9bab; font-size: 11px; }
.asset-form :deep(.el-row) { row-gap: 2px; }
.asset-form :deep(.el-form-item) { margin-bottom: 18px; }
.asset-form :deep(.el-divider) { margin: 22px 0 16px; }
.asset-form :deep(.el-divider__text) { color: #31526b; font-size: 13px; font-weight: 600; }
.vendor-select-row { display: flex; align-items: center; gap: 8px; width: 100%; }
.vendor-select { flex: 1; min-width: 0; }
.vendor-add-btn { flex-shrink: 0; }
.vendor-help { margin-top: 4px; }
.asset-form-page {
  height: 100%;
}

.group-select-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.group-select-row .el-button {
  flex: none;
  white-space: nowrap;
}

.field-tip {
  margin-top: 4px;
  color: #9aabb9;
  font-size: 10px;
}

.copy-alert {
  margin-bottom: 14px;
}

.field-unit {
  margin-left: 7px;
  color: #91a4b4;
  font-size: 10px;
}

.probe-mode-hint {
  margin: 0 0 14px 130px;
  max-width: 760px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-header > div {
  display: flex;
  gap: 8px;
}

.test-alert {
  margin-bottom: 16px;
}

.cabinet-alert {
  margin-bottom: 8px;
}

.form-tip {
  font-size: 11px;
  color: #c0c4cc;
  line-height: 1.4;
}

.form-tip.u-range-conflict {
  color: #dc2626;
}

.exceed {
  color: #f56c6c;
  font-weight: 600;
}

.icon-field {
  display: flex;
  align-items: flex-start;
  gap: 14px;
}

.icon-preview {
  width: 64px;
  height: 64px;
  border-radius: 10px;
  border: 1px dashed #c0c4cc;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  overflow: hidden;
  background: #fafcff;
  flex-shrink: 0;
  transition: border-color 0.2s;
}

.icon-preview:hover {
  border-color: #409eff;
}

.icon-preview.empty {
  color: #a8abb2;
}

.icon-preview img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.icon-actions {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
}

/* 纵向排列时消除 Element Plus 相邻按钮的 margin-left，保证“更换图标/内置图标库/按厂商匹配”三行左对齐 */
.icon-actions :deep(.el-button + .el-button) {
  margin-left: 0;
}

.custom-oid-list {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.custom-oid-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.metric-tag {
  width: 52px;
  text-align: center;
}

.oid-input {
  max-width: 380px;
}

.oid-name {
  font-size: 12px;
  color: #909399;
}

.rec-tip {
  margin-bottom: 12px;
}

.rec-col {
  margin-bottom: 12px;
}

.rec-card {
  border: 1px solid #ebeef5;
  border-radius: 10px;
  padding: 12px;
  background: #fafcff;
  height: 100%;
}

.rec-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-weight: 600;
}

.rec-chosen {
  font-size: 12px;
  font-weight: normal;
  color: #67c23a;
}

.rec-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 240px;
  overflow-y: auto;
}

.rec-item {
  padding: 6px 8px;
  border-radius: 6px;
  border: 1px solid #f0f2f5;
  background: #fff;
  cursor: pointer;
}

.rec-item:hover {
  border-color: #c6e2ff;
}

.rec-item.active {
  border-color: #67c23a;
  background: #f0f9eb;
}

.rec-name {
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.rec-oid {
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
  color: #409eff;
}

.muted {
  color: #a8abb2;
  font-size: 12px;
}

.server-sensors {
  width: 100%;
}

.server-sensor-tip {
  margin-bottom: 10px;
}
</style>
