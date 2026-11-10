<template>
  <div class="room-list">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>{{ t('room.roomsAndCabinets') }}</span>
          <div class="actions">
            <el-button size="small" @click="loadAll" :loading="loading">
              <el-icon><Refresh /></el-icon>{{ t('common.refresh') }}
            </el-button>
            <el-button type="primary" size="small" @click="openRoomCreate">
              <el-icon><Plus /></el-icon>{{ t('room.addRoom') }}
            </el-button>
          </div>
        </div>
      </template>

      <el-table :data="rooms" v-loading="loading" stripe>
        <el-table-column prop="name" :label="t('room.room')" min-width="160">
          <template #default="{ row }">
            <div class="room-name">{{ row.name }}</div>
            <div class="room-sub">{{ row.building || '-' }} {{ row.floor || '' }}</div>
          </template>
        </el-table-column>
        <el-table-column :label="t('room.sizeM')" width="140">
          <template #default="{ row }">
            {{ row.length_m }} × {{ row.width_m }} × {{ row.height_m }}
          </template>
        </el-table-column>
        <el-table-column :label="t('room.cabinet')" width="90">
          <template #default="{ row }">{{ row.summary.cabinet_count }}</template>
        </el-table-column>
        <el-table-column :label="t('room.device')" width="90">
          <template #default="{ row }">{{ row.summary.device_count }}</template>
        </el-table-column>
        <el-table-column :label="t('room.uUsage')" width="170">
          <template #default="{ row }">
            <el-progress
              :percentage="Math.min(row.summary.u_percent || 0, 100)"
              :stroke-width="14"
              :status="percentStatus(row.summary.u_percent)"
            />
            <span class="hint">
              {{ row.summary.used_u }} / {{ row.summary.u_capacity }}U
            </span>
          </template>
        </el-table-column>
        <el-table-column :label="t('room.power')" width="190">
          <template #default="{ row }">
            <el-progress
              :percentage="Math.min(row.summary.used_power_w / Math.max(row.summary.cabinet_power_capacity_w, 1) * 100, 100)"
              :stroke-width="14"
              :status="percentStatus(row.summary.used_power_w / Math.max(row.summary.cabinet_power_capacity_w, 1) * 100)"
            />
            <span class="hint">
              {{ (row.summary.used_power_w / 1000).toFixed(1) }} /
              {{ (row.summary.cabinet_power_capacity_w / 1000).toFixed(1) }} kW
            </span>
          </template>
        </el-table-column>
        <el-table-column :label="t('room.actions')" width="430" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="openRoomShowcase(row)">
              <el-icon><DataBoard /></el-icon>机房展示
            </el-button>
            <el-button type="primary" link size="small" @click="openCabinetManager(row)">
              {{ t('room.cabinetManagement') }}
            </el-button>
            <el-button type="primary" link size="small" @click="openSensorManager(row)">
              {{ t('room.temperatureHumidity') }}
            </el-button>
            <el-button type="primary" link size="small" @click="openRoomEdit(row)">{{ t('room.edit') }}</el-button>
            <el-button type="danger" link size="small" @click="removeRoom(row)">{{ t('room.delete') }}</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!loading && rooms.length === 0" :description="t('room.noRoomsHint')" />
    </el-card>

    <!-- 机房表单 -->
    <el-dialog v-model="roomDialog" :title="editingRoom ? t('room.editRoom') : t('room.addRoom')" width="620px">
      <el-form :model="roomForm" label-width="160px" label-position="right" class="room-form">
        <el-form-item :label="t('room.roomName')" required>
          <el-input v-model="roomForm.name" :placeholder="t('room.roomNameExample')" />
        </el-form-item>
        <el-form-item :label="t('room.building')">
          <el-input v-model="roomForm.building" :placeholder="t('room.buildingPlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('room.floor')">
          <el-input v-model="roomForm.floor" placeholder="B1" />
        </el-form-item>
        <el-form-item :label="t('room.location')">
          <el-input v-model="roomForm.location" :placeholder="t('room.locationExamplePlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('room.roomTotalPowerW')">
          <div class="room-field-stack">
            <el-input-number v-model="roomForm.power_capacity_w" :min="0" :max="1000000" :step="1000" />
            <span class="form-hint">{{ t('room.powerShareHint') }}</span>
          </div>
        </el-form-item>
        <el-form-item :label="t('room.description')">
          <el-input v-model="roomForm.description" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="roomDialog = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="saving" @click="saveRoom">{{ t('common.save') }}</el-button>
      </template>
    </el-dialog>

    <!-- 机柜管理 -->
    <el-dialog
      v-model="cabinetDialog"
      :title="t('room.cabinetManagementTitle', { name: currentRoom?.name || '' })"
      width="1080px"
    >
      <div class="cab-toolbar">
        <el-button type="primary" size="small" @click="openCabinetCreate">
          <el-icon><Plus /></el-icon>{{ t('room.addCabinet') }}
        </el-button>
        <span class="hint">
          {{ t('room.deviceRackHint') }}
          {{ t('room.cabinetValidationHint') }}
        </span>
      </div>

      <el-table :data="cabinets" v-loading="cabinetLoading" stripe max-height="460">
        <el-table-column prop="name" :label="t('room.cabinet')" min-width="150" />
        <el-table-column :label="t('room.positionRowCol')" width="110">
          <template #default="{ row }">第 {{ Number(row.row_index || 0) + 1 }} 排 / 第 {{ Number(row.col_index || 0) + 1 }} 列</template>
        </el-table-column>
        <el-table-column :label="t('room.uCapacity')" width="100">
          <template #default="{ row }">{{ row.usage.used_u }} / {{ row.u_capacity }}U</template>
        </el-table-column>
        <el-table-column :label="t('room.power')" width="190">
          <template #default="{ row }">
            <el-progress
              :percentage="Math.min(row.usage.power_percent, 100)"
              :stroke-width="12"
              :status="percentStatus(row.usage.power_percent)"
            />
            <span class="hint">
              {{ row.usage.used_power_w.toFixed(0) }} / {{ row.power_capacity_w.toFixed(0) }} W
            </span>
          </template>
        </el-table-column>
        <el-table-column :label="t('room.device')" width="80">
          <template #default="{ row }">{{ row.usage.device_count }}</template>
        </el-table-column>
        <el-table-column :label="t('room.doorStatus')" width="100">
          <template #default="{ row }">
            <el-tag :type="row.door_state === 'open' ? 'warning' : 'info'" size="small">
              {{ row.door_state === 'open' ? t('room.opened') : t('room.closed') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('room.actions')" width="230" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="toggleDoor(row)">
              {{ row.door_state === 'open' ? t('room.closeDoor') : t('room.openDoor') }}
            </el-button>
            <el-button type="primary" link size="small" @click="openCabinetEdit(row)">{{ t('room.edit') }}</el-button>
            <el-button type="danger" link size="small" @click="removeCabinet(row)">{{ t('room.delete') }}</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 机柜表单 -->
    <el-dialog v-model="cabinetFormDialog" :title="editingCabinet ? t('room.editCabinet') : t('room.addCabinet')" width="620px">
      <el-form :model="cabinetForm" label-width="120px">
        <el-row :gutter="16">
          <el-col :span="14">
            <el-form-item :label="t('room.cabinetName')" required>
              <el-input v-model="cabinetForm.name" :placeholder="t('room.cabinetNamePlaceholder')" />
            </el-form-item>
          </el-col>
          <el-col :span="10">
            <el-form-item :label="t('room.model')">
              <el-input v-model="cabinetForm.model" :placeholder="t('room.standardCabinetModel')" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item :label="t('room.row')">
              <el-input-number v-model="cabinetRowDisplay" :min="1" :max="51" controls-position="right" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item :label="t('room.column')">
              <el-input-number v-model="cabinetColDisplay" :min="1" :max="51" controls-position="right" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item :label="t('room.orientation')">
              <el-input-number v-model="cabinetForm.rotation" :min="0" :max="270" :step="90" controls-position="right" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <div class="cabinet-pos-preview">
          3D 排布预览：第 {{ Number(cabinetForm.row_index || 0) + 1 }} 排 · 第 {{ Number(cabinetForm.col_index || 0) + 1 }} 列
          · U01 - U{{ String(Math.max(1, Number(cabinetForm.u_capacity) || 1)).padStart(2, '0') }}
        </div>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="t('room.uCapacity')">
              <div class="cabinet-u-field">
                <el-input-number v-model="cabinetForm.u_capacity" :min="1" :max="60" controls-position="right" style="width:100%" />
                <el-button-group size="small">
                  <el-button @click="cabinetForm.u_capacity = 42">42U</el-button>
                  <el-button @click="cabinetForm.u_capacity = 47">47U</el-button>
                </el-button-group>
              </div>
              <div class="form-tip">
                3D 机柜刻度：01U - {{ String(Math.max(1, Number(cabinetForm.u_capacity) || 1)).padStart(2, '0') }}U
              </div>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('room.ratedPowerW')">
              <el-input-number v-model="cabinetForm.power_capacity_w" :min="0" :max="100000" :step="500" controls-position="right" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="t('room.widthM')">
              <el-input-number v-model="cabinetForm.width_m" :min="0.4" :max="2" :step="0.1" controls-position="right" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('room.depthM')">
              <el-input-number v-model="cabinetForm.depth_m" :min="0.4" :max="2" :step="0.1" controls-position="right" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-divider content-position="left">{{ t('room.electronicLockOptional') }}</el-divider>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="t('room.lockType')">
              <el-select v-model="cabinetForm.lock_type" style="width: 100%">
                <el-option :label="t('room.unconfiguredSoftwareOnly')" value="none" />
                <el-option :label="t('room.demoMode')" value="demo" />
                <el-option :label="t('room.httpLockGateway')" value="http" />
                <el-option :label="t('room.tcpRelayBoard')" value="relay_tcp" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('room.initialStatus')">
              <el-switch
                v-model="cabinetForm.is_locked"
                :active-text="t('room.lockToggle')"
                :inactive-text="t('room.unlock')"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <template v-if="cabinetForm.lock_type === 'http'">
          <el-form-item :label="t('room.lockUrl')">
            <el-input v-model="cabinetForm.lock_url" :placeholder="t('room.lockUrlPlaceholder')" />
          </el-form-item>
          <el-form-item :label="t('room.authToken')">
            <el-input v-model="cabinetForm.lock_token" :placeholder="t('room.authHeaderPlaceholder')" />
          </el-form-item>
        </template>
        <template v-else-if="cabinetForm.lock_type === 'relay_tcp'">
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item :label="t('room.relayHost')">
                <el-input v-model="cabinetForm.lock_host" placeholder="10.0.0.9" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="t('room.port')">
                <el-input-number v-model="cabinetForm.lock_port" :min="1" :max="65535" style="width: 100%" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item :label="t('room.channelNo')">
                <el-input-number v-model="cabinetForm.lock_channel" :min="1" :max="16" style="width: 100%" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="t('room.autoLockOnClose')">
                <el-switch v-model="cabinetForm.auto_lock" />
              </el-form-item>
            </el-col>
          </el-row>
        </template>
        <el-form-item v-if="cabinetForm.lock_type !== 'none'" :label="t('room.autoLockOnClose')">
          <el-switch v-model="cabinetForm.auto_lock" />
        </el-form-item>

        <el-form-item :label="t('room.description')">
          <el-input v-model="cabinetForm.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="cabinetFormDialog = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="saving" @click="saveCabinet">{{ t('common.save') }}</el-button>
      </template>
    </el-dialog>

    <!-- 温湿度传感器管理 -->
    <el-dialog
      v-model="sensorDialog"
      :title="t('room.sensorTitle', { name: currentRoom?.name || '' })"
      width="920px"
    >
      <div class="sensor-toolbar">
        <el-button type="primary" size="small" @click="openSensorCreate">
          <el-icon><Plus /></el-icon>{{ t('room.addSensor') }}
        </el-button>
        <span class="hint">{{ t('room.sensorSupportHint') }}</span>
      </div>

      <el-table :data="sensors" v-loading="sensorLoading" size="small">
        <el-table-column prop="name" :label="t('room.name')" min-width="130" show-overflow-tooltip />
        <el-table-column :label="t('room.type')" width="90">
          <template #default="{ row }">{{ sensorTypeText(row.sensor_type) }}</template>
        </el-table-column>
        <el-table-column :label="t('room.source')" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="sensorSourceTagType(row.source)">
              {{ sensorSourceText(row.source) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('room.temperature')" width="100">
          <template #default="{ row }">{{ row.last_temperature ?? '-' }} ℃</template>
        </el-table-column>
        <el-table-column :label="t('room.humidity')" width="100">
          <template #default="{ row }">{{ row.last_humidity ?? '-' }} %</template>
        </el-table-column>
        <el-table-column :label="t('room.threshold')" width="160">
          <template #default="{ row }">
            {{ t('room.tempRange', { low: row.temp_low, high: row.temp_high }) }}<br />
            {{ t('room.humidityRange', { low: row.humidity_low, high: row.humidity_high }) }}
          </template>
        </el-table-column>
        <el-table-column :label="t('room.status')" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="sensorStatusType(row.status)">
              {{ sensorStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('room.address')" width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ sensorAddress(row) }}</template>
        </el-table-column>
        <el-table-column :label="t('room.updateTime')" width="165">
          <template #default="{ row }">{{ formatDateTime(row.last_updated) }}</template>
        </el-table-column>
        <el-table-column :label="t('room.actions')" width="150" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="openSensorEdit(row)">{{ t('room.edit') }}</el-button>
            <el-button type="primary" link size="small" @click="showSensorStats(row)">
              {{ t('room.stats24h') }}
            </el-button>
            <el-button type="danger" link size="small" @click="removeSensor(row)">{{ t('room.delete') }}</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!sensorLoading && sensors.length === 0" :description="t('room.noSensorsHint')" />

      <el-alert
        v-if="sensorStats"
        :title="t('room.sensorStatsTitle', { tAvg: sensorStats.temperature_avg ?? '-', tMax: sensorStats.temperature_max ?? '-', tMin: sensorStats.temperature_min ?? '-', hAvg: sensorStats.humidity_avg ?? '-', hMax: sensorStats.humidity_max ?? '-', hMin: sensorStats.humidity_min ?? '-', count: sensorStats.count })"
        type="info"
        :closable="true"
        class="sensor-stats"
        @close="sensorStats = null"
      />
    </el-dialog>

    <!-- 传感器表单 -->
    <el-dialog
      v-model="sensorFormDialog"
      :title="editingSensor ? t('room.editSensor') : t('room.addSensor')"
      width="780px"
    >
      <el-form :model="sensorForm" label-width="110px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="t('room.name')" required>
              <el-input v-model="sensorForm.name" :placeholder="t('room.sensorNamePlaceholder')" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('room.sensorType')">
              <el-select v-model="sensorForm.sensor_type" style="width: 100%">
                <el-option :label="t('room.temperatureHumidity')" value="combined" />
                <el-option :label="t('room.temperature')" value="temperature" />
                <el-option :label="t('room.humidity')" value="humidity" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="t('room.dataSource')">
              <el-radio-group v-model="sensorForm.source">
                <el-radio-button value="demo">{{ t('room.demo') }}</el-radio-button>
                <el-radio-button value="snmp">SNMP</el-radio-button>
                <el-radio-button value="xiaomi">{{ t('room.xiaomi') }}</el-radio-button>
                <el-radio-button value="rs485">RS485</el-radio-button>
                <el-radio-button value="modbus_tcp">Modbus TCP</el-radio-button>
                <el-radio-button value="mqtt">MQTT</el-radio-button>
              </el-radio-group>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('room.enable')">
              <el-switch v-model="sensorForm.is_enabled" />
            </el-form-item>
          </el-col>
        </el-row>

        <template v-if="sensorForm.source === 'snmp'">
          <el-divider content-position="left">{{ t('room.snmpConfig') }}</el-divider>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item :label="t('room.ipAddress')" required>
                <el-input v-model="sensorForm.ip" placeholder="10.0.0.50" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="团体名">
                <el-input v-model="sensorForm.community" placeholder="public" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item :label="t('room.port')">
                <el-input-number v-model="sensorForm.port" :min="1" :max="65535" style="width: 100%" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="t('room.snmpVersion')">
                <el-select v-model="sensorForm.snmp_version" style="width: 100%">
                  <el-option label="v2c" value="v2c" />
                  <el-option label="v1" value="v1" />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item :label="t('room.temperatureOid')">
            <el-input v-model="sensorForm.oid_temperature" :placeholder="t('room.tempOidPlaceholder')" />
          </el-form-item>
          <el-form-item :label="t('room.humidityOid')">
            <el-input v-model="sensorForm.oid_humidity" :placeholder="t('room.humidityOidPlaceholder')" />
          </el-form-item>
        </template>

        <template v-if="sensorForm.source === 'xiaomi'">
          <el-divider content-position="left">{{ t('room.xiaomiConfig') }}</el-divider>
          <el-form-item :label="t('room.xiaomiUrl')" required>
            <el-input v-model="sensorForm.xiaomi_url" placeholder="http://192.168.1.50/api/xiaomi/sensor" />
            <span class="form-help">{{ t('room.xiaomiUrlHint') }}</span>
          </el-form-item>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item :label="t('room.tokenOptional')">
                <el-input v-model="sensorForm.xiaomi_token" show-password placeholder="Bearer Token" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="t('room.deviceIdOptional')">
                <el-input v-model="sensorForm.xiaomi_device_id" placeholder="device_id" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item :label="t('room.temperaturePath')">
                <el-input v-model="sensorForm.xiaomi_temperature_path" placeholder="temperature 或 data.temperature" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="t('room.humidityPath')">
                <el-input v-model="sensorForm.xiaomi_humidity_path" placeholder="humidity 或 data.humidity" />
              </el-form-item>
            </el-col>
          </el-row>
        </template>

        <template v-if="sensorForm.source === 'rs485'">
          <el-divider content-position="left">{{ t('room.rs485Config') }}</el-divider>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item :label="t('room.serialPort')" required>
                <el-input v-model="sensorForm.serial_port" placeholder="COM3 或 /dev/ttyUSB0" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="t('room.baudrate')">
                <el-input-number v-model="sensorForm.baudrate" :min="1200" :max="115200" :step="1200" style="width: 100%" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="8">
              <el-form-item :label="t('room.slaveId')">
                <el-input-number v-model="sensorForm.slave_id" :min="1" :max="247" style="width: 100%" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item :label="t('room.functionCode')">
                <el-select v-model="sensorForm.function_code" style="width: 100%">
                  <el-option label="03 保持寄存器" :value="3" />
                  <el-option label="04 输入寄存器" :value="4" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item :label="t('room.registerCount')">
                <el-select v-model="sensorForm.register_count" style="width: 100%">
                  <el-option label="1 个寄存器" :value="1" />
                  <el-option label="2 个寄存器（32 位）" :value="2" />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item :label="t('room.temperatureRegister')">
                <el-input-number v-model="sensorForm.register_temperature" :min="0" :max="65535" style="width: 100%" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="t('room.humidityRegister')">
                <el-input-number v-model="sensorForm.register_humidity" :min="0" :max="65535" style="width: 100%" />
                <span class="form-help">{{ t('room.humidityRegisterHint') }}</span>
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item :label="t('room.temperatureScale')">
                <el-input-number v-model="sensorForm.temperature_scale" :min="0.001" :precision="4" style="width: 100%" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="t('room.humidityScale')">
                <el-input-number v-model="sensorForm.humidity_scale" :min="0.001" :precision="4" style="width: 100%" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="8">
              <el-form-item :label="t('room.signedTemperature')">
                <el-switch v-model="sensorForm.signed_temperature" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item :label="t('room.wordOrder')">
                <el-select v-model="sensorForm.word_order" style="width: 100%">
                  <el-option label="大端 ABCD" value="big" />
                  <el-option label="小端 CDAB" value="little" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item :label="t('room.serialTimeout')">
                <el-input-number v-model="sensorForm.serial_timeout" :min="0.2" :max="10" :step="0.1" :precision="1" style="width: 100%" />
              </el-form-item>
            </el-col>
          </el-row>
        </template>

        <template v-if="sensorForm.source === 'modbus_tcp'">
          <el-divider content-position="left">{{ t('room.modbusTcpConfig') }}</el-divider>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item :label="t('room.host')" required>
                <el-input v-model="sensorForm.modbus_host" placeholder="192.168.1.60" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="t('room.port')">
                <el-input-number v-model="sensorForm.modbus_port" :min="1" :max="65535" style="width: 100%" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="8">
              <el-form-item :label="t('room.unitId')">
                <el-input-number v-model="sensorForm.modbus_unit_id" :min="1" :max="255" style="width: 100%" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item :label="t('room.functionCode')">
                <el-select v-model="sensorForm.function_code" style="width: 100%">
                  <el-option label="03 保持寄存器" :value="3" />
                  <el-option label="04 输入寄存器" :value="4" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item :label="t('room.registerCount')">
                <el-select v-model="sensorForm.register_count" style="width: 100%">
                  <el-option label="1 个寄存器" :value="1" />
                  <el-option label="2 个寄存器（32 位）" :value="2" />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item :label="t('room.temperatureRegister')">
                <el-input-number v-model="sensorForm.register_temperature" :min="0" :max="65535" style="width: 100%" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="t('room.humidityRegister')">
                <el-input-number v-model="sensorForm.register_humidity" :min="0" :max="65535" style="width: 100%" />
                <span class="form-help">{{ t('room.humidityRegisterHint') }}</span>
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="8">
              <el-form-item :label="t('room.temperatureScale')">
                <el-input-number v-model="sensorForm.temperature_scale" :min="0.001" :precision="4" style="width: 100%" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item :label="t('room.humidityScale')">
                <el-input-number v-model="sensorForm.humidity_scale" :min="0.001" :precision="4" style="width: 100%" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item :label="t('room.serialTimeout')">
                <el-input-number v-model="sensorForm.modbus_timeout" :min="0.2" :max="10" :step="0.1" :precision="1" style="width: 100%" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item :label="t('room.signedTemperature')">
                <el-switch v-model="sensorForm.signed_temperature" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="t('room.wordOrder')">
                <el-select v-model="sensorForm.word_order" style="width: 100%">
                  <el-option label="大端 ABCD" value="big" />
                  <el-option label="小端 CDAB" value="little" />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
        </template>

        <template v-if="sensorForm.source === 'mqtt'">
          <el-divider content-position="left">{{ t('room.mqttConfig') }}</el-divider>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item :label="t('room.brokerHost')" required>
                <el-input v-model="sensorForm.mqtt_host" placeholder="192.168.1.70" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="t('room.port')">
                <el-input-number v-model="sensorForm.mqtt_port" :min="1" :max="65535" style="width: 100%" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item :label="t('room.mqttTopic')" required>
            <el-input v-model="sensorForm.mqtt_topic" placeholder="sensors/room1/temp-humidity" />
          </el-form-item>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item :label="t('room.username')">
                <el-input v-model="sensorForm.mqtt_username" autocomplete="off" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="t('room.password')">
                <el-input v-model="sensorForm.mqtt_password" type="password" show-password autocomplete="new-password" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="8">
              <el-form-item :label="t('room.mqttTls')">
                <el-switch v-model="sensorForm.mqtt_tls" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item :label="t('room.clientIdOptional')">
                <el-input v-model="sensorForm.mqtt_client_id" placeholder="自动生成" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item :label="t('room.readTimeout')">
                <el-input-number v-model="sensorForm.mqtt_timeout" :min="1" :max="60" style="width: 100%" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item :label="t('room.temperaturePath')">
                <el-input v-model="sensorForm.mqtt_temperature_path" placeholder="temperature" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="t('room.humidityPath')">
                <el-input v-model="sensorForm.mqtt_humidity_path" placeholder="humidity" />
              </el-form-item>
            </el-col>
          </el-row>
        </template>

        <el-divider content-position="left">{{ t('room.threshold') }}</el-divider>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="t('room.tempLow')">
              <el-input-number v-model="sensorForm.temp_low" :precision="1" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('room.tempHigh')">
              <el-input-number v-model="sensorForm.temp_high" :precision="1" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="t('room.humidityLow')">
              <el-input-number v-model="sensorForm.humidity_low" :precision="1" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('room.humidityHigh')">
              <el-input-number v-model="sensorForm.humidity_high" :precision="1" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="sensorFormDialog = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="saving" @click="saveSensor">{{ t('common.save') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { t } from '@/i18n'
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { roomApi } from '@/api'
import { getToken, handoffToken } from '@/store/auth'
import { formatDateTime } from '@/utils/time'

const router = useRouter()
const rooms = ref([])

function openRoomShowcase(row) {
  // 机房数字孪生用于长期展示：新页签打开，并交接当前登录态。
  handoffToken(getToken())
  window.open(`/rooms/${row.id}/showcase`, '_blank', 'noopener,noreferrer')
}
const loading = ref(false)
const saving = ref(false)

const roomDialog = ref(false)
const editingRoom = ref(null)
const roomForm = reactive({
  name: '', building: '', floor: '', location: '', description: '',
  length_m: 12, width_m: 8, height_m: 3.2, power_capacity_w: 60000,
})

const cabinetDialog = ref(false)
const cabinetFormDialog = ref(false)
const cabinetLoading = ref(false)
const currentRoom = ref(null)
const cabinets = ref([])
const editingCabinet = ref(null)
const cabinetForm = reactive({
  name: '', row_index: 0, col_index: 0, u_capacity: 42, power_capacity_w: 6000,
  width_m: 0.6, depth_m: 1.2, rotation: 0, model: '', description: '',
  // 电子锁
  lock_type: 'none', is_locked: true, auto_lock: true,
  lock_url: '', lock_token: '', lock_host: '', lock_port: 8080, lock_channel: 1,
})

// 数据库行列从 0 开始，界面统一按“第 N 排 / 第 N 列”展示和输入
const cabinetRowDisplay = computed({
  get: () => Number(cabinetForm.row_index || 0) + 1,
  set: (value) => { cabinetForm.row_index = Math.max(0, (Number(value) || 1) - 1) },
})
const cabinetColDisplay = computed({
  get: () => Number(cabinetForm.col_index || 0) + 1,
  set: (value) => { cabinetForm.col_index = Math.max(0, (Number(value) || 1) - 1) },
})

/** 把表单里的电子锁字段组装成 lock_config */
function buildLockConfig() {
  const type = cabinetForm.lock_type
  if (type === 'http') {
    return { url: cabinetForm.lock_url, token: cabinetForm.lock_token, auto_lock: cabinetForm.auto_lock }
  }
  if (type === 'relay_tcp') {
    return {
      host: cabinetForm.lock_host,
      port: cabinetForm.lock_port,
      channel: cabinetForm.lock_channel,
      auto_lock: cabinetForm.auto_lock,
    }
  }
  if (type === 'demo') {
    return { auto_lock: cabinetForm.auto_lock }
  }
  return {}
}

function percentStatus(p) {
  if (p >= 90) return 'exception'
  if (p >= 70) return 'warning'
  return 'success'
}

async function loadAll() {
  loading.value = true
  try {
    const res = await roomApi.list()
    rooms.value = res.data
  } catch (e) {
    ElMessage.error(e.message || t('room.loadRoomsFailed'))
  } finally {
    loading.value = false
  }
}

// ---------- 机房 ----------
function openRoomCreate() {
  editingRoom.value = null
  Object.assign(roomForm, {
    name: '', building: '', floor: '', location: '', description: '',
    length_m: 12, width_m: 8, height_m: 3.2, power_capacity_w: 60000,
  })
  roomDialog.value = true
}

function openRoomEdit(row) {
  editingRoom.value = row
  Object.assign(roomForm, {
    name: row.name, building: row.building || '', floor: row.floor || '',
    location: row.location || '', description: row.description || '',
    length_m: row.length_m, width_m: row.width_m, height_m: row.height_m,
    power_capacity_w: row.power_capacity_w || 0,
  })
  roomDialog.value = true
}

async function saveRoom() {
  if (!roomForm.name.trim()) {
    ElMessage.warning(t('room.roomNameRequired'))
    return
  }
  saving.value = true
  try {
    if (editingRoom.value) {
      await roomApi.update(editingRoom.value.id, { ...roomForm })
      ElMessage.success(t('room.saved'))
    } else {
      await roomApi.create({ ...roomForm })
      ElMessage.success(t('room.created'))
    }
    roomDialog.value = false
    await loadAll()
  } catch (e) {
    ElMessage.error(e.message || t('room.saveFailed'))
  } finally {
    saving.value = false
  }
}

async function removeRoom(row) {
  try {
    await ElMessageBox.confirm(
      t('room.confirmDeleteRoom', { name: row.name }),
      t('room.confirmDelete'),
      { type: 'warning' }
    )
    await roomApi.remove(row.id)
    ElMessage.success(t('room.deleted'))
    await loadAll()
  } catch {
    /* 取消 */
  }
}

// ---------- 机柜 ----------
async function openCabinetManager(row) {
  currentRoom.value = row
  cabinetDialog.value = true
  await loadCabinets(row.id)
}

async function loadCabinets(roomId) {
  cabinetLoading.value = true
  try {
    const res = await roomApi.listCabinets(roomId)
    cabinets.value = res.data
  } catch (e) {
    ElMessage.error(e.message || t('room.loadCabinetsFailed'))
  } finally {
    cabinetLoading.value = false
  }
}

function openCabinetCreate() {
  editingCabinet.value = null
  const nextCol = cabinets.value.length
  Object.assign(cabinetForm, {
    name: `CAB-${String(nextCol + 1).padStart(2, '0')}`,
    row_index: 0, col_index: nextCol, u_capacity: 42, power_capacity_w: 6000,
    width_m: 0.6, depth_m: 1.2, rotation: 0, model: t('room.standardCabinetModel'), description: '',
    lock_type: 'none', is_locked: true, auto_lock: true,
    lock_url: '', lock_token: '', lock_host: '', lock_port: 8080, lock_channel: 1,
  })
  cabinetFormDialog.value = true
}

function openCabinetEdit(row) {
  editingCabinet.value = row
  const cfg = row.lock_config || {}
  Object.assign(cabinetForm, {
    name: row.name, row_index: row.row_index, col_index: row.col_index,
    u_capacity: row.u_capacity, power_capacity_w: row.power_capacity_w,
    width_m: row.width_m, depth_m: row.depth_m, rotation: row.rotation,
    model: row.model || '', description: row.description || '',
    lock_type: row.lock_type || 'none',
    is_locked: row.is_locked !== false,
    auto_lock: cfg.auto_lock !== false,
    lock_url: cfg.url || '',
    lock_token: '',
    lock_host: cfg.host || '',
    lock_port: cfg.port || 8080,
    lock_channel: cfg.channel || 1,
  })
  cabinetFormDialog.value = true
}

async function saveCabinet() {
  if (!cabinetForm.name.trim()) {
    ElMessage.warning(t('room.cabinetNameRequired'))
    return
  }
  saving.value = true
  try {
    const {
      lock_url, lock_token, lock_host, lock_port, lock_channel, auto_lock, ...base
    } = cabinetForm
    const payload = { ...base, lock_config: buildLockConfig() }
    if (editingCabinet.value) {
      await roomApi.updateCabinet(editingCabinet.value.id, payload)
      ElMessage.success(t('room.saved'))
    } else {
      await roomApi.createCabinet({ ...payload, room_id: currentRoom.value.id })
      ElMessage.success(t('room.created'))
    }
    cabinetFormDialog.value = false
    await loadCabinets(currentRoom.value.id)
    await loadAll()
  } catch (e) {
    ElMessage.error(e.message || t('room.saveFailed'))
  } finally {
    saving.value = false
  }
}

async function removeCabinet(row) {
  try {
    await ElMessageBox.confirm(t('room.confirmDeleteCabinet', { name: row.name }), t('room.confirmDelete'), { type: 'warning' })
    await roomApi.removeCabinet(row.id)
    ElMessage.success(t('room.deleted'))
    await loadCabinets(currentRoom.value.id)
    await loadAll()
  } catch {
    /* 取消 */
  }
}

async function toggleDoor(row) {
  try {
    const res = await roomApi.setDoor(row.id, row.door_state === 'open' ? 'closed' : 'open')
    row.door_state = res.data.door_state
    ElMessage.success(res.data.door_state === 'open' ? t('room.cabinetDoorOpened') : t('room.cabinetDoorClosed'))
  } catch (e) {
    ElMessage.error(e.message || t('room.operationFailed'))
  }
}

// ---------- 温湿度传感器 ----------
const sensorDialog = ref(false)
const sensorFormDialog = ref(false)
const sensorLoading = ref(false)
const sensors = ref([])
const editingSensor = ref(null)
const sensorStats = ref(null)
const sensorForm = reactive({
  name: '',
  sensor_type: 'combined',
  source: 'demo',
  ip: '',
  snmp_version: 'v2c',
  community: 'public',
  port: 161,
  oid_temperature: '',
  oid_humidity: '',
  xiaomi_url: '',
  xiaomi_token: '',
  xiaomi_device_id: '',
  xiaomi_temperature_path: 'temperature',
  xiaomi_humidity_path: 'humidity',
  serial_port: '',
  baudrate: 9600,
  bytesize: 8,
  parity: 'N',
  stopbits: 1,
  slave_id: 1,
  function_code: 3,
  register_temperature: 0,
  register_humidity: null,
  register_count: 1,
  temperature_scale: 0.1,
  humidity_scale: 0.1,
  signed_temperature: true,
  word_order: 'big',
  serial_timeout: 1.0,
  modbus_host: '',
  modbus_port: 502,
  modbus_unit_id: 1,
  modbus_timeout: 3.0,
  mqtt_host: '',
  mqtt_port: 1883,
  mqtt_username: '',
  mqtt_password: '',
  mqtt_topic: '',
  mqtt_tls: false,
  mqtt_client_id: '',
  mqtt_timeout: 5.0,
  mqtt_temperature_path: 'temperature',
  mqtt_humidity_path: 'humidity',
  temp_high: 30,
  temp_low: 15,
  humidity_high: 70,
  humidity_low: 30,
  is_enabled: true,
})

function sensorTypeText(type) {
  return { combined: t('room.temperatureHumidity'), temperature: t('room.temperature'), humidity: t('room.humidity') }[type] || type
}

function sensorSourceText(source) {
  return {
    snmp: 'SNMP',
    xiaomi: t('room.xiaomi'),
    rs485: 'RS485',
    modbus_tcp: 'Modbus TCP',
    mqtt: 'MQTT',
    demo: t('room.demo'),
  }[source] || source || t('room.demo')
}

function sensorSourceTagType(source) {
  return { snmp: 'success', xiaomi: 'warning', rs485: '', modbus_tcp: 'success', mqtt: 'warning', demo: 'info' }[source] || 'info'
}

function sensorAddress(row) {
  if (row.source === 'xiaomi') return row.xiaomi_url || '-'
  if (row.source === 'rs485') return row.serial_port || '-'
  if (row.source === 'modbus_tcp') return row.modbus_host ? `${row.modbus_host}:${row.modbus_port || 502}` : '-'
  if (row.source === 'mqtt') return row.mqtt_topic || row.mqtt_host || '-'
  return row.ip || '-'
}

function sensorStatusType(status) {
  return { normal: 'success', alarm: 'danger', unknown: 'info' }[status] || 'info'
}

function sensorStatusText(status) {
  return { normal: t('room.normal'), alarm: t('room.overLimit'), unknown: t('room.unknown') }[status] || status
}

async function openSensorManager(row) {
  currentRoom.value = row
  sensorDialog.value = true
  sensorStats.value = null
  await loadSensors()
}

async function loadSensors() {
  if (!currentRoom.value) return
  sensorLoading.value = true
  try {
    const res = await roomApi.sensors(currentRoom.value.id)
    sensors.value = res.data.items || []
  } catch (e) {
    ElMessage.error(e.message || t('room.loadSensorsFailed'))
  } finally {
    sensorLoading.value = false
  }
}

function openSensorCreate() {
  editingSensor.value = null
  Object.assign(sensorForm, {
    name: '',
    sensor_type: 'combined',
    source: 'demo',
    ip: '',
    snmp_version: 'v2c',
    community: 'public',
    port: 161,
    oid_temperature: '',
    oid_humidity: '',
    temp_high: 30,
    temp_low: 15,
    humidity_high: 70,
    humidity_low: 30,
    is_enabled: true,
  })
  sensorFormDialog.value = true
}

function openSensorEdit(row) {
  editingSensor.value = row
  Object.assign(sensorForm, {
    name: row.name,
    sensor_type: row.sensor_type,
    source: row.source,
    ip: row.ip || '',
    snmp_version: row.snmp_version || 'v2c',
    community: row.community || 'public',
    port: row.port || 161,
    oid_temperature: row.oid_temperature || '',
    oid_humidity: row.oid_humidity || '',
    xiaomi_url: row.xiaomi_url || '',
    xiaomi_token: row.xiaomi_token || '',
    xiaomi_device_id: row.xiaomi_device_id || '',
    xiaomi_temperature_path: row.xiaomi_temperature_path || 'temperature',
    xiaomi_humidity_path: row.xiaomi_humidity_path || 'humidity',
    serial_port: row.serial_port || '',
    baudrate: row.baudrate || 9600,
    bytesize: row.bytesize || 8,
    parity: row.parity || 'N',
    stopbits: row.stopbits || 1,
    slave_id: row.slave_id || 1,
    function_code: row.function_code || 3,
    register_temperature: row.register_temperature ?? 0,
    register_humidity: row.register_humidity ?? null,
    register_count: row.register_count || 1,
    temperature_scale: row.temperature_scale ?? 0.1,
    humidity_scale: row.humidity_scale ?? 0.1,
    signed_temperature: row.signed_temperature !== false,
    word_order: row.word_order || 'big',
    serial_timeout: row.serial_timeout ?? 1.0,
    modbus_host: row.modbus_host || '',
    modbus_port: row.modbus_port || 502,
    modbus_unit_id: row.modbus_unit_id || 1,
    modbus_timeout: row.modbus_timeout ?? 3.0,
    mqtt_host: row.mqtt_host || '',
    mqtt_port: row.mqtt_port || 1883,
    mqtt_username: row.mqtt_username || '',
    mqtt_password: row.mqtt_password || '',
    mqtt_topic: row.mqtt_topic || '',
    mqtt_tls: row.mqtt_tls === true,
    mqtt_client_id: row.mqtt_client_id || '',
    mqtt_timeout: row.mqtt_timeout ?? 5.0,
    mqtt_temperature_path: row.mqtt_temperature_path || 'temperature',
    mqtt_humidity_path: row.mqtt_humidity_path || 'humidity',
    temp_high: row.temp_high,
    temp_low: row.temp_low,
    humidity_high: row.humidity_high,
    humidity_low: row.humidity_low,
    is_enabled: row.is_enabled,
  })
  sensorFormDialog.value = true
}

async function saveSensor() {
  if (!sensorForm.name.trim()) {
    ElMessage.warning(t('room.sensorNameRequired'))
    return
  }
  if (sensorForm.source === 'snmp' && !sensorForm.ip) {
    ElMessage.warning(t('room.snmpIpRequired'))
    return
  }
  if (sensorForm.source === 'xiaomi' && !String(sensorForm.xiaomi_url || '').trim()) {
    ElMessage.warning(t('room.xiaomiUrlRequired'))
    return
  }
  if (sensorForm.source === 'rs485' && !String(sensorForm.serial_port || '').trim()) {
    ElMessage.warning(t('room.serialPortRequired'))
    return
  }
  if (sensorForm.source === 'modbus_tcp' && !String(sensorForm.modbus_host || '').trim()) {
    ElMessage.warning(t('room.hostRequired'))
    return
  }
  if (sensorForm.source === 'mqtt' && (!String(sensorForm.mqtt_host || '').trim() || !String(sensorForm.mqtt_topic || '').trim())) {
    ElMessage.warning(t('room.mqttRequired'))
    return
  }
  saving.value = true
  try {
    const payload = { ...sensorForm, name: sensorForm.name.trim() }
    if (editingSensor.value) {
      await roomApi.updateSensor(editingSensor.value.id, payload)
      ElMessage.success(t('room.sensorUpdated'))
    } else {
      await roomApi.createSensor(currentRoom.value.id, payload)
      ElMessage.success(t('room.sensorCreated'))
    }
    sensorFormDialog.value = false
    await loadSensors()
  } catch (e) {
    ElMessage.error(e.message || t('room.saveFailed'))
  } finally {
    saving.value = false
  }
}

async function removeSensor(row) {
  try {
    await ElMessageBox.confirm(t('room.confirmDeleteSensor', { name: row.name }), t('room.confirmDelete'), { type: 'warning' })
    await roomApi.removeSensor(row.id)
    ElMessage.success(t('room.deleted'))
    await loadSensors()
  } catch {
    /* 取消 */
  }
}

async function showSensorStats(row) {
  try {
    const res = await roomApi.sensorReadings(row.id, 24)
    sensorStats.value = res.data.stats
  } catch (e) {
    ElMessage.error(e.message || t('room.loadHistoryFailed'))
  }
}

onMounted(loadAll)
</script>

<style scoped>
.room-list {
  height: 100%;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.actions {
  display: flex;
  gap: 8px;
}

.room-name {
  font-weight: 600;
  color: #303133;
}

.room-sub {
  font-size: 12px;
  color: #909399;
}

.hint {
  font-size: 12px;
  color: #909399;
}

.form-hint {
  margin-left: 10px;
  font-size: 12px;
  color: #c0c4cc;
}

/* 机房表单：每行标签与控件保持同一纵向基线，标签右对齐、输入文字左对齐 */
.room-form :deep(.el-form-item) {
  display: flex;
  align-items: flex-start;
  margin-bottom: 18px;
}

.room-form :deep(.el-form-item__label) {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  padding-right: 12px;
  line-height: 32px;
  text-align: right;
  font-weight: 500;
  color: #303133;
}

.room-form :deep(.el-form-item__content) {
  flex: 1;
  min-width: 0;
  margin-left: 0 !important;
  line-height: 32px;
  align-items: center;
}

.room-form :deep(.el-input),
.room-form :deep(.el-input-number),
.room-form :deep(.el-textarea) {
  width: 100%;
}

.room-form :deep(.el-input__inner),
.room-form :deep(.el-input-number .el-input__inner),
.room-form :deep(.el-textarea__inner) {
  text-align: left;
}

.room-field-stack {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
}

.room-field-stack .form-hint {
  margin-left: 0;
}

.cab-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}

.sensor-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}

.sensor-stats {
  margin-top: 12px;
}

.cabinet-u-field {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.cabinet-pos-preview {
  margin: -4px 0 12px 120px;
  padding: 6px 9px;
  border-radius: 6px;
  color: #5f8298;
  background: #f5faff;
  font-size: 10px;
}

.cabinet-u-field + .form-tip {
  margin-top: 5px;
  color: #8ca0af;
  font-size: 10px;
  line-height: 1.5;
}
</style>
