<template>
  <div class="asset-list">
    <el-card>
      <!-- 搜索和操作栏 -->
      <div class="toolbar">
        <div class="toolbar-filters">
          <el-input
            v-model="searchForm.search"
            :placeholder="t('asset.list.searchDevicePlaceholder')"
            clearable
            class="toolbar-search"
            @keyup.enter="handleSearch"
            @clear="handleSearch"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>

          <el-select v-model="searchForm.device_type" :placeholder="t('asset.list.deviceType')" clearable filterable allow-create default-first-option class="toolbar-select" @change="handleSearch">
            <el-option
              v-for="item in typeFilterOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>

          <el-select v-model="searchForm.group_id" :placeholder="t('asset.list.assetGroup')" clearable class="toolbar-select" @change="handleSearch">
            <el-option
              v-for="group in groupOptions"
              :key="group.id"
              :label="group.name"
              :value="group.id"
            />
          </el-select>

          <el-button type="primary" @click="handleSearch">
            <el-icon><Search /></el-icon>
            {{ t('asset.list.search') }}
          </el-button>

          <el-button type="success" @click="addDevice">
            <el-icon><Plus /></el-icon>
            {{ t('asset.list.addDevice') }}
          </el-button>
        </div>

        <div class="toolbar-right">
          <el-button
            v-if="can('assets:edit')"
            :disabled="!selectedDevices.length"
            @click="openBulkEdit"
          >
            <el-icon><EditPen /></el-icon>
            {{ t('asset.list.bulkEdit') }}
            <span v-if="selectedDevices.length" class="selection-count">{{ selectedDevices.length }}</span>
          </el-button>

          <el-button
            v-if="can('assets:edit')"
            type="danger"
            plain
            :disabled="!selectedDevices.length"
            @click="bulkDeleteSelected"
          >
            <el-icon><Delete /></el-icon>
            {{ t('asset.list.bulkDelete') }}
            <span v-if="selectedDevices.length" class="selection-count">{{ selectedDevices.length }}</span>
          </el-button>

          <el-dropdown @command="handleMoreAction">
            <el-button>
              更多操作
              <el-icon class="el-icon--right"><ArrowDown /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="match-icons">{{ t('asset.list.iconMatching') }}</el-dropdown-item>
                <el-dropdown-item command="batch-icons">{{ t('asset.list.batchIcons') }}</el-dropdown-item>
                <el-dropdown-item divided command="export-xlsx">{{ t('asset.list.exportExcel') }}</el-dropdown-item>
                <el-dropdown-item command="export-csv">{{ t('asset.list.exportCsv') }}</el-dropdown-item>
                <el-dropdown-item command="export-selected-xlsx" :disabled="!selectedDevices.length">
                  {{ t('asset.list.exportSelectedExcel', { count: selectedDevices.length }) }}
                </el-dropdown-item>
                <el-dropdown-item command="export-selected-csv" :disabled="!selectedDevices.length">
                  {{ t('asset.list.exportSelectedCsv', { count: selectedDevices.length }) }}
                </el-dropdown-item>
                <el-dropdown-item divided command="import">{{ t('asset.list.import') }}</el-dropdown-item>
                <el-dropdown-item command="template">{{ t('asset.list.downloadTemplate') }}</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>

      <!-- 设备列表表格 -->
      <el-table
        ref="tableRef"
        :data="deviceList"
        stripe
        v-loading="loading"
        style="width: 100%"
        row-key="id"
        @sort-change="handleSort"
        @selection-change="onSelectionChange"
      >
        <el-table-column type="selection" width="44" />
        <el-table-column prop="name" :label="t('asset.list.deviceName')" :min-width="isCompact ? 140 : 160" sortable="custom">
          <template #default="{ row }">
            <div class="device-name-cell">
              <img v-if="row.icon" :src="row.icon" class="device-icon" alt="icon" />
              <span class="device-icon placeholder" v-else>{{ (row.name || '?').slice(0, 1) }}</span>
              <span>{{ row.name }}</span>
              <span v-if="row.alert_count > 0" class="device-alert" title="当前未恢复告警">
                <el-icon :size="16" color="#f5222d"><Bell /></el-icon>
                <el-tag type="danger" size="small" round>
                  {{ row.alert_count > 99 ? '99+' : row.alert_count }}
                </el-tag>
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="ip_address" :label="t('asset.list.ipAddress')" :width="isCompact ? 125 : 140" align="center" sortable="custom" />
        <el-table-column v-if="showAssetExtras" :label="t('asset.list.source')" width="78" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.source === 'auto'" type="warning" size="small" effect="plain">
              {{ t('asset.list.sourceAuto') }}
            </el-tag>
            <span v-else class="muted">{{ t('asset.list.sourceManual') }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="device_type" :label="t('asset.list.type')" width="88" align="center">
          <template #default="{ row }">
            <el-tag :type="getTypeTagColor(row.device_type)" size="small">
              {{ getTypeName(row.device_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="showAssetExtras" prop="group_name" :label="t('asset.list.assetGroup')" width="96" align="center">
          <template #default="{ row }">
            <span v-if="row.group_name">{{ row.group_name }}</span>
            <span v-else class="muted">{{ t('asset.list.ungrouped') }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="showAssetExtras" :label="t('asset.list.roomCabinet')" min-width="175" align="center" show-overflow-tooltip>
          <template #default="{ row }">
            <div v-if="row.cabinet" class="cabinet-location-cell">
              <div class="cabinet-location-main">
                <el-tag size="small" type="info" effect="plain">
                  {{ row.cabinet.room_name || t('asset.list.room') }}
                </el-tag>
                <span class="cabinet-name">{{ row.cabinet.name }}</span>
              </div>
              <div v-if="row.cabinet.room_floor || row.cabinet.room_location" class="cabinet-location-meta">
                <span v-if="row.cabinet.room_floor">楼层 {{ row.cabinet.room_floor }}</span>
                <span v-if="row.cabinet.room_location">位置 {{ row.cabinet.room_location }}</span>
              </div>
            </div>
            <span v-else class="muted">{{ t('asset.list.notRacked') }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="showAssetExtras" :label="t('asset.list.uPosition')" width="72" align="center">
          <template #default="{ row }">
            <span v-if="row.u_position">
              U{{ row.u_position }}<template v-if="(row.u_height || 1) > 1">-{{ row.u_position + row.u_height - 1 }}</template>
            </span>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="showAssetExtras" :label="t('asset.list.power')" width="76" align="center">
          <template #default="{ row }">
            <span v-if="row.power_watts">{{ row.power_watts }} W</span>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="showAssetExtras" prop="vendor" :label="t('asset.list.vendor')" width="88" align="center" show-overflow-tooltip />
        <el-table-column v-if="showAssetExtras" prop="model" :label="t('asset.form.model')" width="110" align="center" show-overflow-tooltip>
          <template #default="{ row }">{{ row.model || '-' }}</template>
        </el-table-column>
        <el-table-column v-if="!isCompact" label="接入方式" width="88" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="monitorTypeTag(row)">
              {{ monitorTypeLabel(row) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('asset.list.monitoringStatus')" width="86" align="center">
          <template #default="{ row }">
            <el-switch
              v-model="row.is_enabled"
              @change="handleToggle(row)"
              inline-prompt
              :active-text="t('asset.list.on')"
              :inactive-text="t('asset.list.off')"
            />
          </template>
        </el-table-column>
        <el-table-column label="当前告警指标" :min-width="isCompact ? 300 : 350" align="center">
          <template #default="{ row }">
            <div v-if="deviceDashboardMetrics(row).length" class="asset-dashboard-metrics">
              <div
                v-for="metric in visibleDashboardMetrics(row)"
                :key="metric.key"
                class="asset-dashboard-metric"
                :class="metric.severity"
              >
                <div class="asset-dashboard-metric-head">
                  <span class="asset-dashboard-metric-name">{{ metric.label }}</span>
                  <b>{{ formatDashboardMetricValue(metric) }}</b>
                </div>
                <div class="asset-dashboard-metric-thresholds">
                  <span>预警 <em>{{ formatThreshold(metric, metric.warning) }}</em></span>
                  <span>告警 <em>{{ formatThreshold(metric, metric.critical) }}</em></span>
                </div>
              </div>
              <span v-if="extraDashboardMetricCount(row)" class="asset-dashboard-more">+{{ extraDashboardMetricCount(row) }} 项</span>
            </div>
            <span v-else class="muted">未配置</span>
          </template>
        </el-table-column>
        <el-table-column label="自定义告警规则" :min-width="isCompact ? 260 : 325" align="center">
          <template #default="{ row }">
            <div v-if="row.alert_rules?.length" class="asset-rule-list">
              <div
                v-for="rule in visibleRules(row)"
                :key="rule.id"
                class="asset-rule-item"
                :class="{ triggered: rule.triggered, disabled: !rule.enabled }"
                :title="rule.name"
              >
                <span class="asset-rule-metric">{{ rule.metric_label }}</span>
                <b class="asset-rule-value">{{ formatRuleValue(rule.current_value) }}{{ rule.unit }}</b>
                <small class="asset-rule-threshold">{{ rule.operator_text }}{{ rule.threshold }}{{ rule.unit }}</small>
                <el-tag v-if="!rule.enabled" size="small" type="info" effect="plain">停用</el-tag>
                <el-tag v-else-if="rule.triggered" size="small" :type="ruleLevelType(rule.level)" effect="dark">{{ rule.level_label }}</el-tag>
                <el-tag v-else size="small" type="success" effect="plain">正常</el-tag>
              </div>
              <span v-if="extraRuleCount(row)" class="asset-rule-more">+{{ extraRuleCount(row) }} 条</span>
            </div>
            <span v-else class="muted">未设置</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('asset.list.actions')" :width="isCompact ? 180 : 180" fixed="right" align="center">
          <template #default="{ row }">
            <el-button type="primary" link size="small" :title="t('asset.list.view')" @click="viewDetail(row.id)">
              <el-icon><View /></el-icon>
            </el-button>
            <el-button type="primary" link size="small" :title="t('asset.list.edit')" @click="editDevice(row)">
              <el-icon><Edit /></el-icon>
            </el-button>
            <el-button
              v-if="can('assets:edit')"
              type="success"
              link
              size="small"
              :title="t('asset.list.copy')"
              @click="copyDevice(row)"
            >
              <el-icon><CopyDocument /></el-icon>{{ t('asset.list.copy') }}
            </el-button>
            <el-button type="danger" link size="small" :title="t('asset.list.delete')" @click="handleDelete(row)">
              <el-icon><Delete /></el-icon>
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      
      <!-- 分页 -->
      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.size"
          :total="pagination.total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>

    <!-- 导入对话框 -->
    <el-dialog v-model="importDialog" :title="t('asset.list.importDeviceAssets')" width="760px" @closed="resetImport">
      <el-alert type="info" :closable="false" show-icon class="import-tip">
        <template #title>
          {{ t('asset.list.templateColumnsHint') }}
          {{ t('asset.list.suggestFirst') }}<el-button link type="primary" @click="downloadTemplate">{{ t('asset.list.downloadTemplate') }}</el-button>{{ t('asset.list.tipComma') }}
          {{ t('asset.list.exportReferenceHint') }}
        </template>
      </el-alert>

      <el-form label-width="120px">
        <el-form-item :label="t('asset.list.selectFile')">
          <el-upload
            drag
            :auto-upload="false"
            :limit="1"
            accept=".xlsx,.csv"
            :file-list="importFileList"
            :on-change="onFileChange"
            :on-remove="onFileRemove"
            :on-exceed="onFileExceed"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">{{ t('asset.list.dragFileHint') }} <em>{{ t('asset.list.clickToSelect') }}</em></div>
            <template #tip>
              <div class="el-upload__tip">{{ t('asset.list.uploadFileHint') }}</div>
            </template>
          </el-upload>
        </el-form-item>

        <el-form-item :label="t('asset.list.importMode')">
          <el-radio-group v-model="importMode">
            <el-radio-button label="skip">{{ t('asset.list.skipExisting') }}</el-radio-button>
            <el-radio-button label="update">{{ t('asset.list.updateExisting') }}</el-radio-button>
            <el-radio-button label="fail">{{ t('asset.list.conflictError') }}</el-radio-button>
          </el-radio-group>
          <div class="mode-hint">
            {{ importMode === 'skip'
              ? t('asset.list.skipModeHint')
              : importMode === 'update'
                ? t('asset.list.updateModeHint')
                : t('asset.list.failModeHint') }}
          </div>
        </el-form-item>

        <el-form-item :label="t('asset.list.whenCabinetMissing')">
          <el-checkbox v-model="autoCreateCabinet">{{ t('asset.list.autoCreateRoomCabinet') }}</el-checkbox>
        </el-form-item>
      </el-form>

      <div v-if="importResult" class="import-result">
        <el-descriptions :column="5" border size="small">
          <el-descriptions-item :label="t('asset.list.totalRows')">{{ importResult.total }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.list.created')">{{ importResult.created }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.list.updated')">{{ importResult.updated }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.list.skipped')">{{ importResult.skipped }}</el-descriptions-item>
          <el-descriptions-item :label="t('asset.list.failed')">
            <span :class="importResult.failed > 0 ? 'text-danger' : ''">
              {{ importResult.failed }}
            </span>
          </el-descriptions-item>
        </el-descriptions>

        <el-table
          v-if="importResult.errors && importResult.errors.length"
          :data="importResult.errors"
          size="small"
          max-height="240"
          class="error-table"
        >
          <el-table-column prop="row" :label="t('asset.list.rowNumber')" width="70" />
          <el-table-column prop="ip" label="IP" width="150" />
          <el-table-column prop="message" :label="t('asset.list.failureReason')" show-overflow-tooltip />
        </el-table>
      </div>

      <template #footer>
        <el-button @click="importDialog = false">{{ t('asset.list.close') }}</el-button>
        <el-button type="primary" :loading="importing" :disabled="!importFile" @click="submitImport">
          {{ t('asset.list.startImport') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 按厂商自动匹配图标 -->
    <el-dialog v-model="matchDialog" :title="t('asset.list.autoMatchByVendor')" width="560px">
      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 14px">
        按设备「厂商」优先匹配厂商图标（Cisco / Huawei / H3C / Ruijie / Fortinet /
        Sangfor / TopSec / 海康 / 大华 等），厂商未匹配时按设备类型匹配路由器、交换机、防火墙等图标。
      </el-alert>
      <el-form label-width="120px">
        <el-form-item :label="t('asset.list.overwriteIcons')">
          <el-switch v-model="matchOverwrite" />
          <span class="form-hint">{{ t('asset.list.iconKeepHint') }}</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="matchDialog = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="matching" @click="submitMatchIcons">
          {{ t('asset.list.startMatching') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 批量修改 -->
    <el-dialog
      v-model="bulkEditVisible"
      :title="t('asset.list.bulkEditTitle', { count: selectedDevices.length })"
      width="640px"
      class="bulk-edit-dialog"
    >
      <el-alert
        :title="t('asset.list.bulkEditHint')"
        type="info"
        :closable="false"
        show-icon
        class="bulk-edit-tip"
      />
      <el-form label-width="120px" class="bulk-edit-form">
        <el-form-item :label="t('asset.list.assetGroup')">
          <div class="bulk-field">
            <el-checkbox v-model="bulkEditForm.groupEnabled">{{ t('asset.list.modifyThisField') }}</el-checkbox>
            <el-select
              v-model="bulkEditForm.group_id"
              clearable
              :disabled="!bulkEditForm.groupEnabled"
              :placeholder="t('asset.form.assetGroupPlaceholder')"
              style="flex: 1"
            >
              <el-option v-for="group in groupOptions" :key="group.id" :label="group.name" :value="group.id" />
            </el-select>
          </div>
        </el-form-item>

        <el-form-item :label="t('asset.list.deviceType')">
          <div class="bulk-field">
            <el-checkbox v-model="bulkEditForm.typeEnabled">{{ t('asset.list.modifyThisField') }}</el-checkbox>
            <el-select
              v-model="bulkEditForm.device_type"
              filterable
              allow-create
              default-first-option
              :disabled="!bulkEditForm.typeEnabled"
              :placeholder="t('asset.form.deviceTypePlaceholder')"
              style="flex: 1"
            >
              <el-option v-for="item in typeFilterOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </div>
        </el-form-item>

        <el-form-item :label="t('asset.list.location')">
          <div class="bulk-field">
            <el-checkbox v-model="bulkEditForm.locationEnabled">{{ t('asset.list.modifyThisField') }}</el-checkbox>
            <el-input
              v-model="bulkEditForm.location"
              :disabled="!bulkEditForm.locationEnabled"
              :placeholder="t('asset.form.roomNamePlaceholder')"
              style="flex: 1"
            />
          </div>
        </el-form-item>

        <el-form-item :label="t('asset.list.vendor')">
          <div class="bulk-field">
            <el-checkbox v-model="bulkEditForm.vendorEnabled">{{ t('asset.list.modifyThisField') }}</el-checkbox>
            <el-input
              v-model="bulkEditForm.vendor"
              :disabled="!bulkEditForm.vendorEnabled"
              :placeholder="t('asset.form.vendorPlaceholder')"
              style="flex: 1"
            />
          </div>
        </el-form-item>

        <el-form-item :label="t('asset.list.tags')">
          <div class="bulk-field">
            <el-checkbox v-model="bulkEditForm.tagsEnabled">{{ t('asset.list.modifyThisField') }}</el-checkbox>
            <el-input
              v-model="bulkEditForm.tags"
              :disabled="!bulkEditForm.tagsEnabled"
              :placeholder="t('asset.list.bulkTagsPlaceholder')"
              style="flex: 1"
            />
          </div>
        </el-form-item>

        <el-form-item :label="t('asset.list.monitorStatus')">
          <div class="bulk-field">
            <el-checkbox v-model="bulkEditForm.enabledEnabled">{{ t('asset.list.modifyThisField') }}</el-checkbox>
            <el-switch
              v-model="bulkEditForm.is_enabled"
              :disabled="!bulkEditForm.enabledEnabled"
              inline-prompt
              :active-text="t('asset.list.on')"
              :inactive-text="t('asset.list.off')"
            />
          </div>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="bulkEditVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="bulkEditSaving" @click="submitBulkEdit">
          {{ t('asset.list.bulkEditSubmit', { count: selectedDevices.length }) }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 按分组批量套用图标 -->
    <el-dialog v-model="batchDialog" :title="t('asset.list.batchSetIconsByGroup')" width="780px" @open="loadBatchPresets">
      <el-form label-width="100px">
        <el-row :gutter="16">
          <el-col :span="10">
            <el-form-item :label="t('asset.list.groupBy')">
              <el-select v-model="batchScope" style="width: 100%">
                <el-option :label="t('asset.list.byDeviceType')" value="type" />
                <el-option :label="t('asset.list.byVendor')" value="vendor" />
                <el-option :label="t('asset.list.currentPageDevices')" value="ids" />
                <el-option :label="t('asset.list.allDevices')" value="all" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="14">
            <el-form-item v-if="batchScope === 'type'" :label="t('asset.list.deviceType')">
              <el-select v-model="batchType" clearable :placeholder="t('asset.list.selectDeviceType')" style="width: 100%">
                <el-option
                  v-for="opt in DEVICE_TYPE_OPTIONS"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
            </el-form-item>
            <el-form-item v-else-if="batchScope === 'vendor'" :label="t('asset.list.vendorKeyword')">
              <el-input v-model="batchVendor" :placeholder="t('asset.list.vendorKeywordPlaceholder')" />
            </el-form-item>
            <el-form-item v-else-if="batchScope === 'ids'" :label="t('asset.list.range')">
              <span class="form-hint">{{ t('asset.list.currentPageDevicesCount', { count: deviceList.length }) }}</span>
            </el-form-item>
            <el-form-item v-else :label="t('asset.list.range')">
              <span class="form-hint">{{ t('asset.list.allDevicesCount', { count: pagination.total }) }}</span>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>

      <div class="preset-title">
        <span>{{ t('asset.list.selectIcon') }}</span>
        <span class="form-hint">
          {{ t('asset.list.iconCountHint', { count: batchPresets.length }) }}
        </span>
      </div>
      <div v-loading="presetLoading" class="preset-grid">
        <div
          v-for="item in batchPresets"
          :key="item.id"
          class="preset-cell"
          :class="{ active: batchIcon === item.url }"
          @click="batchIcon = item.url"
        >
          <img :src="item.url" :alt="item.name" loading="lazy" />
          <span>{{ item.name }}</span>
        </div>
        <el-empty v-if="!presetLoading && !batchPresets.length" :description="t('asset.list.noIconsAvailable')" />
      </div>

      <template #footer>
        <span v-if="batchIcon" class="batch-preview">
          <img :src="batchIcon" :alt="t('asset.list.preview')" />
          {{ t('asset.list.selected') }}
        </span>
        <el-button @click="batchDialog = false">{{ t('common.cancel') }}</el-button>
        <el-button
          type="primary"
          :loading="batchApplying"
          :disabled="!batchIcon"
          @click="submitBatchIcon"
        >
          {{ t('asset.list.applyToGroup') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { t } from '@/i18n'
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { assetApi } from '@/api'
import { temperatureDisplayName } from '@/utils/serverComponentLabels'
import { buildDeviceDashboardMetrics } from '@/utils/dashboardMetrics'
import { downloadWithAuth, can } from '@/store/auth'
import { useResponsiveViewport } from '@/composables/useResponsiveViewport'
import {
  DEVICE_TYPE_OPTIONS, deviceTypeLabel, deviceTypeTagType,
} from '@/constants/device'

const { viewportWidth, isCompact } = useResponsiveViewport()
const showAssetExtras = computed(() => viewportWidth.value >= 1800)

const router = useRouter()
const route = useRoute()
const loading = ref(false)
const deviceList = ref([])
const selectedDevices = ref([])
const DASHBOARD_CONFIG_KEY = 'nms_hex_dashboard_v1'
const dashboardMetricsConfig = ref(readDashboardMetricsConfig())

function readDashboardMetricsConfig() {
  try {
    const raw = localStorage.getItem(DASHBOARD_CONFIG_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

const BASE_DASHBOARD_METRICS = {
  cpu_usage: { label: 'CPU 使用率', unit: '%' },
  memory_usage: { label: '内存使用率', unit: '%' },
  temperature: { label: '最高部件温度', unit: '°C' },
  disk_usage: { label: '磁盘使用率', unit: '%' },
  power_status: { label: '电源状态', unit: '' },
  alert_count: { label: '未处理告警', unit: '条' },
  warranty_days_left: { label: '维保剩余天数', unit: '天', direction: 'lower' },
}

function dashboardComponentName(row, kind, index) {
  const components = row?.metric?.components || row?.metric?.custom?.server_components || {}
  return (components[kind] || [])[Number(index)] || null
}

function dashboardMetricMeta(item, row) {
  const key = String(item.metric || '')
  if (BASE_DASHBOARD_METRICS[key]) return BASE_DASHBOARD_METRICS[key]
  const tempMatch = key.match(/^srv_component_temp_(\d+)$/)
  if (tempMatch) {
    const component = dashboardComponentName(row, 'temperatures', tempMatch[1])
    return { label: component ? temperatureDisplayName(component.name) : '温度', unit: '°C' }
  }
  const fanMatch = key.match(/^srv_component_fan_(\d+)$/)
  if (fanMatch) {
    const component = dashboardComponentName(row, 'fans', fanMatch[1])
    return { label: component ? `风扇 · ${component.name || '#' + (Number(fanMatch[1]) + 1)}` : '风扇转速', unit: 'RPM' }
  }
  const psuWatts = key.match(/^srv_component_psu_watts_(\d+)$/)
  if (psuWatts) {
    const component = dashboardComponentName(row, 'power_supplies', psuWatts[1])
    return { label: component ? `电源功率 · ${component.name || '电源'}` : '电源功率', unit: 'W' }
  }
  const psuVoltage = key.match(/^srv_component_psu_voltage_(\d+)$/)
  if (psuVoltage) {
    const component = dashboardComponentName(row, 'power_supplies', psuVoltage[1])
    return { label: component ? `电源电压 · ${component.name || '电源'}` : '电源电压', unit: 'V' }
  }
  const diskMatch = key.match(/^srv_component_disk_(\d+)$/)
  if (diskMatch) {
    const component = dashboardComponentName(row, 'disks', diskMatch[1])
    return { label: component ? `硬盘容量 · ${component.name || '硬盘'}` : '硬盘容量', unit: 'GB' }
  }
  const sensorLabels = {
    srv_cpu_temp: ['CPU 温度', '°C'],
    srv_inlet_temp: ['系统板入口温度', '°C'],
    srv_exhaust_temp: ['系统板排气温度', '°C'],
    srv_fan_speed: ['风扇转速', 'RPM'],
    srv_power_watts: ['电源功率', 'W'],
    srv_power_voltage: ['电源电压', 'V'],
    srv_disk_usage: ['硬盘使用率', '%'],
  }
  if (sensorLabels[key]) return { label: sensorLabels[key][0], unit: sensorLabels[key][1] }
  const custom = (row?.custom_metrics || []).find((entry) => String(entry.key) === key)
    || (row?.server_sensors || []).find((entry) => String(entry.key) === key)
  return { label: custom?.name || key, unit: custom?.unit || '' }
}

function dashboardMetricValue(item, row) {
  const key = String(item.metric || '')
  const metric = row?.metric || {}
  if (key === 'alert_count') return Number(row?.alert_count) || 0
  if (['cpu_usage', 'memory_usage', 'temperature', 'disk_usage', 'power_status'].includes(key)) return metric[key]
  if (key === 'warranty_days_left') return row?.warranty_days_left
  if (key === 'srv_inlet_temp' || key === 'srv_exhaust_temp' || key === 'srv_cpu_temp') {
    const temps = (metric.components || metric.custom?.server_components || {}).temperatures || []
    const pattern = key === 'srv_inlet_temp' ? /inlet|进气|进风/i : key === 'srv_exhaust_temp' ? /exhaust|排气|排风/i : /cpu|处理器/i
    return temps.find((entry) => pattern.test(String(entry.name || '')))?.value
  }
  if (key === 'srv_fan_speed') {
    const values = (metric.components?.fans || metric.custom?.server_components?.fans || []).map((entry) => Number(entry.value)).filter(Number.isFinite)
    return values.length ? Math.max(...values) : metric.custom?.[key]
  }
  if (key === 'srv_power_watts') {
    const values = (metric.components?.power_supplies || metric.custom?.server_components?.power_supplies || []).map((entry) => Number(entry.watts)).filter(Number.isFinite)
    return values.length ? values.reduce((a, b) => a + b, 0) : metric.custom?.[key]
  }
  const tempMatch = key.match(/^srv_component_temp_(\d+)$/)
  if (tempMatch) return dashboardComponentName(row, 'temperatures', tempMatch[1])?.value
  const fanMatch = key.match(/^srv_component_fan_(\d+)$/)
  if (fanMatch) return dashboardComponentName(row, 'fans', fanMatch[1])?.value
  const psuWatts = key.match(/^srv_component_psu_watts_(\d+)$/)
  if (psuWatts) return dashboardComponentName(row, 'power_supplies', psuWatts[1])?.watts
  const psuVoltage = key.match(/^srv_component_psu_voltage_(\d+)$/)
  if (psuVoltage) return dashboardComponentName(row, 'power_supplies', psuVoltage[1])?.voltage
  const diskMatch = key.match(/^srv_component_disk_(\d+)$/)
  if (diskMatch) return dashboardComponentName(row, 'disks', diskMatch[1])?.size_gb
  return metric.custom?.[key]
}

function dashboardMetricSeverity(item, value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return ''
  const warning = Number(item.warning)
  const critical = Number(item.critical)
  const direction = BASE_DASHBOARD_METRICS[item.metric]?.direction || 'higher'
  if (Number.isFinite(critical) && (direction === 'lower' ? number <= critical : number >= critical)) return 'critical'
  if (Number.isFinite(warning) && (direction === 'lower' ? number <= warning : number >= warning)) return 'warning'
  return ''
}

function deviceDashboardMetrics(row) {
  return buildDeviceDashboardMetrics(dashboardMetricsConfig.value, row)
}

function formatDashboardMetricValue(metric) {
  if (metric.value === null || metric.value === undefined || metric.value === '') return '--'
  return `${metric.value}${metric.unit || ''}`
}

function formatThreshold(metric, value) {
  if (value === null || value === undefined || value === '') return '-'
  return `${value}${metric.unit || ''}`
}

function visibleDashboardMetrics(row) {
  return deviceDashboardMetrics(row).slice(0, 2)
}

function extraDashboardMetricCount(row) {
  return Math.max(0, deviceDashboardMetrics(row).length - 2)
}
const tableRef = ref(null)

function onSelectionChange(rows) {
  selectedDevices.value = rows || []
}

// ---------- 批量修改 ----------
const bulkEditVisible = ref(false)
const bulkEditSaving = ref(false)
const bulkEditForm = reactive({
  groupEnabled: false,
  group_id: null,
  typeEnabled: false,
  device_type: '',
  locationEnabled: false,
  location: '',
  vendorEnabled: false,
  vendor: '',
  tagsEnabled: false,
  tags: '',
  enabledEnabled: false,
  is_enabled: true,
})

function openBulkEdit() {
  if (!selectedDevices.value.length) {
    ElMessage.warning(t('asset.list.selectDevicesFirst'))
    return
  }
  Object.assign(bulkEditForm, {
    groupEnabled: false,
    group_id: null,
    typeEnabled: false,
    device_type: '',
    locationEnabled: false,
    location: '',
    vendorEnabled: false,
    vendor: '',
    tagsEnabled: false,
    tags: '',
    enabledEnabled: false,
    is_enabled: true,
  })
  bulkEditVisible.value = true
}

async function submitBulkEdit() {
  const fields = {}
  if (bulkEditForm.groupEnabled) fields.group_id = bulkEditForm.group_id || null
  if (bulkEditForm.typeEnabled) {
    if (!bulkEditForm.device_type.trim()) {
      ElMessage.warning(t('asset.list.deviceTypeRequired'))
      return
    }
    fields.device_type = bulkEditForm.device_type.trim()
  }
  if (bulkEditForm.locationEnabled) fields.location = bulkEditForm.location
  if (bulkEditForm.vendorEnabled) fields.vendor = bulkEditForm.vendor
  if (bulkEditForm.tagsEnabled) fields.tags = bulkEditForm.tags
  if (bulkEditForm.enabledEnabled) fields.is_enabled = bulkEditForm.is_enabled
  if (!Object.keys(fields).length) {
    ElMessage.warning(t('asset.list.selectAtLeastOneField'))
    return
  }

  try {
    await ElMessageBox.confirm(
      t('asset.list.bulkEditConfirm', { count: selectedDevices.value.length }),
      t('asset.list.bulkEditConfirmTitle'),
      { type: 'warning', confirmButtonText: t('common.confirm'), cancelButtonText: t('common.cancel') }
    )
  } catch {
    return
  }

  bulkEditSaving.value = true
  try {
    const res = await assetApi.bulkUpdate(
      selectedDevices.value.map((device) => device.id),
      fields
    )
    ElMessage.success(res.data?.message || t('asset.list.bulkUpdated', { count: selectedDevices.value.length }))
    bulkEditVisible.value = false
    tableRef.value?.clearSelection()
    await loadDevices()
  } catch (e) {
    ElMessage.error(e.message || t('asset.list.bulkUpdateFailed'))
  } finally {
    bulkEditSaving.value = false
  }
}

async function bulkDeleteSelected() {
  if (!selectedDevices.value.length) {
    ElMessage.warning(t('asset.list.selectDevicesFirst'))
    return
  }
  const names = selectedDevices.value
    .slice(0, 5)
    .map((device) => device.name)
    .join('、')
  const suffix = selectedDevices.value.length > 5 ? ' ...' : ''
  try {
    await ElMessageBox.confirm(
      t('asset.list.bulkDeleteConfirm', {
        count: selectedDevices.value.length,
        names: `${names}${suffix}`,
      }),
      t('asset.list.bulkDeleteConfirmTitle'),
      { type: 'warning', confirmButtonText: t('common.delete'), cancelButtonText: t('common.cancel') }
    )
  } catch {
    return
  }

  try {
    const res = await assetApi.bulkDelete(selectedDevices.value.map((device) => device.id))
    ElMessage.success(res.data?.message || t('asset.list.bulkDeleted', { count: selectedDevices.value.length }))
    tableRef.value?.clearSelection()
    await loadDevices()
  } catch (e) {
    ElMessage.error(e.message || t('asset.list.bulkDeleteFailed'))
  }
}

// 类型筛选：内置类型 + 当前列表中的自定义类型
const typeFilterOptions = computed(() => {
  const map = new Map(DEVICE_TYPE_OPTIONS.map((item) => [item.value, item.label]))
  for (const device of deviceList.value) {
    if (device.device_type && !map.has(device.device_type)) {
      map.set(device.device_type, device.device_type)
    }
  }
  return [...map.entries()].map(([value, label]) => ({ value, label }))
})

// 图标匹配 / 批量图标
const matchDialog = ref(false)
const matchOverwrite = ref(false)
const matching = ref(false)
const batchDialog = ref(false)
const batchScope = ref('type')
const batchType = ref('')
const batchVendor = ref('')
const batchIcon = ref('')
const batchApplying = ref(false)
const batchPresets = ref([])
const presetLoading = ref(false)

function monitorTypeLabel(row) {
  const type = String(row.monitor_type || 'snmp').toLowerCase()
  if (type === 'snmp') return `SNMP ${row.snmp_version || 'v2c'}`
  if (type === 'tcp') return `TCP:${row.tcp_port || 80}`
  if (type === 'api') return 'API 对接'
  if (type === 'ipmi') return 'IPMI'
  return 'Ping'
}

function monitorTypeTag(row) {
  const type = String(row.monitor_type || 'snmp').toLowerCase()
  if (type === 'snmp') return 'info'
  if (type === 'ping' || type === 'tcp') return 'success'
  return 'warning'
}

const searchForm = reactive({
  search: '',
  device_type: '',
  group_id: '',
})

const groupOptions = ref([])

async function loadGroups() {
  try {
    const res = await assetApi.groups()
    groupOptions.value = res.data.items || []
  } catch {
    groupOptions.value = []
  }
}

const pagination = reactive({
  page: 1,
  size: 20,
  total: 0,
})

// 设备类型：统一映射（见 constants/device.js）
function formatRuleValue(value) {
  if (value === null || value === undefined || value === '') return '-'
  const num = Number(value)
  if (Number.isNaN(num)) return String(value)
  return Number.isInteger(num) ? String(num) : num.toFixed(1)
}

function ruleLevelType(level) {
  return { info: 'info', warning: 'warning', critical: 'danger', emergency: 'danger' }[level] || 'warning'
}

const getTypeTagColor = (type) => deviceTypeTagType(type)
const getTypeName = (type) => deviceTypeLabel(type)

// 加载设备列表
async function loadDevices() {
  loading.value = true
  try {
    const params = {
      page: pagination.page,
      size: pagination.size,
    }
    if (searchForm.search) params.search = searchForm.search
    if (searchForm.device_type) params.device_type = searchForm.device_type
    if (searchForm.group_id) params.group_id = searchForm.group_id
    
    const res = await assetApi.getList(params)
    deviceList.value = res.data.items
    dashboardMetricsConfig.value = readDashboardMetricsConfig()
    pagination.total = res.data.total
  } catch (e) {
    ElMessage.error(t('asset.list.loadDevicesFailed'))
  } finally {
    loading.value = false
  }
}

function syncListQuery() {
  router.replace({ path: '/devices', query: listReturnQuery() })
}

function handleSearch() {
  pagination.page = 1
  syncListQuery()
  loadDevices()
}

function handlePageChange(page) {
  pagination.page = Number(page) || 1
  syncListQuery()
  loadDevices()
}

function handleSizeChange(size) {
  pagination.size = Number(size) || 20
  pagination.page = 1
  syncListQuery()
  loadDevices()
}

// ==================== 导入 / 导出 ====================
const importDialog = ref(false)
const importFile = ref(null)
const importFileList = ref([])
const importMode = ref('skip')
const autoCreateCabinet = ref(false)
const importing = ref(false)
const importResult = ref(null)

function buildFilterQuery() {
  const params = new URLSearchParams()
  if (searchForm.search) params.set('search', searchForm.search)
  if (searchForm.device_type) params.set('device_type', searchForm.device_type)
  if (searchForm.group_id) params.set('group_id', searchForm.group_id)
  return params
}

function exportSelected(format = 'xlsx') {
  if (!selectedDevices.value.length) {
    ElMessage.warning(t('asset.list.selectDevicesFirst'))
    return
  }
  const params = buildFilterQuery()
  params.set('format', format)
  params.set('ids', selectedDevices.value.map((device) => device.id).join(','))
  downloadWithAuth(`/api/assets/export?${params.toString()}`)
}

function handleExport(command) {
  const [format, scope] = String(command).split('-')
  if (scope === 'selected') {
    exportSelected(format)
    return
  }
  const params = buildFilterQuery()
  params.set('format', format)
  downloadWithAuth(`/api/assets/export?${params.toString()}`)
}

function downloadTemplate() {
  downloadWithAuth('/api/assets/import-template')
}

function openImport() {
  importResult.value = null
  importFile.value = null
  importFileList.value = []
  importMode.value = 'skip'
  autoCreateCabinet.value = false
  importDialog.value = true
}

function resetImport() {
  importFile.value = null
  importFileList.value = []
  importResult.value = null
}

function onFileChange(file, files) {
  const name = (file.name || '').toLowerCase()
  if (!name.endsWith('.xlsx') && !name.endsWith('.csv')) {
    ElMessage.error(t('asset.list.onlyXlsxCsv'))
    importFileList.value = []
    importFile.value = null
    return
  }
  if (file.size && file.size > 10 * 1024 * 1024) {
    ElMessage.error(t('asset.list.fileTooLarge'))
    importFileList.value = []
    importFile.value = null
    return
  }
  importFile.value = file.raw
  importFileList.value = files.slice(-1)
}

function onFileRemove() {
  importFile.value = null
  importFileList.value = []
}

function onFileExceed() {
  ElMessage.warning(t('asset.list.onlyOneFile'))
}

async function submitImport() {
  if (!importFile.value) {
    ElMessage.warning(t('asset.list.selectFileFirst'))
    return
  }
  importing.value = true
  try {
    const form = new FormData()
    form.append('file', importFile.value)
    form.append('mode', importMode.value)
    form.append('auto_create_cabinet', autoCreateCabinet.value ? 'true' : 'false')

    const res = await assetApi.importAssets(form)
    importResult.value = res.data
    const r = res.data
    if (r.failed > 0) {
      ElMessage.warning(
        t('asset.list.importResult', { created: r.created, updated: r.updated, skipped: r.skipped, failed: r.failed })
      )
    } else {
      ElMessage.success(t('asset.list.importSuccess', { created: r.created, updated: r.updated, skipped: r.skipped }))
    }
    await loadDevices()
  } catch (e) {
    ElMessage.error(e.message || t('asset.list.importFailed'))
  } finally {
    importing.value = false
  }
}

async function handleToggle(row) {
  try {
    await assetApi.toggle(row.id)
    ElMessage.success(row.is_enabled ? t('asset.list.monitoringEnabled') : t('asset.list.monitoringDisabled'))
  } catch {
    ElMessage.error(t('asset.list.operationFailed'))
    row.is_enabled = !row.is_enabled
  }
}

// ==================== 图标匹配 / 批量图标 ====================
function openMatchIcons() {
  matchOverwrite.value = false
  matchDialog.value = true
}

async function submitMatchIcons() {
  matching.value = true
  try {
    const res = await assetApi.matchIcons({ overwrite: matchOverwrite.value })
    const r = res.data
    ElMessage.success(
      t('asset.list.iconMatchResult', { matched: r.matched, skipped: r.skipped, total: r.total })
    )
    matchDialog.value = false
    await loadDevices()
  } catch (e) {
    ElMessage.error(e.message || t('asset.list.iconMatchFailed'))
  } finally {
    matching.value = false
  }
}

function openBatchIcon() {
  batchIcon.value = ''
  batchType.value = ''
  batchVendor.value = ''
  batchScope.value = 'type'
  batchDialog.value = true
}

async function loadBatchPresets() {
  if (batchPresets.value.length) return
  presetLoading.value = true
  try {
    const res = await assetApi.iconPresets()
    batchPresets.value = res.data.presets || []
  } catch (e) {
    ElMessage.error(e.message || t('asset.list.loadIconsFailed'))
  } finally {
    presetLoading.value = false
  }
}

async function submitBatchIcon() {
  if (!batchIcon.value) {
    ElMessage.warning(t('asset.list.selectIconFirst'))
    return
  }
  const payload = { icon: batchIcon.value, scope: batchScope.value }
  if (batchScope.value === 'type') {
    if (!batchType.value) {
      ElMessage.warning(t('asset.list.deviceTypeRequired'))
      return
    }
    payload.value = batchType.value
  } else if (batchScope.value === 'vendor') {
    if (!batchVendor.value.trim()) {
      ElMessage.warning(t('asset.list.vendorKeywordRequired'))
      return
    }
    payload.value = batchVendor.value.trim()
  } else if (batchScope.value === 'ids') {
    payload.ids = deviceList.value.map((d) => d.id)
    if (!payload.ids.length) {
      ElMessage.warning(t('asset.list.noDevicesOnPage'))
      return
    }
  }
  batchApplying.value = true
  try {
    const res = await assetApi.applyIcon(payload)
    ElMessage.success(t('asset.list.iconUpdated', { count: res.data.updated }))
    batchDialog.value = false
    await loadDevices()
  } catch (e) {
    ElMessage.error(e.message || t('asset.list.batchIconFailed'))
  } finally {
    batchApplying.value = false
  }
}

function visibleRules(row) {
  return (row.alert_rules || []).slice(0, 2)
}

function extraRuleCount(row) {
  return Math.max(0, (row.alert_rules?.length || 0) - 2)
}

function handleMoreAction(command) {
  const actions = {
    'match-icons': openMatchIcons,
    'batch-icons': openBatchIcon,
    'export-xlsx': () => handleExport('xlsx'),
    'export-csv': () => handleExport('csv'),
    'export-selected-xlsx': () => exportSelected('xlsx'),
    'export-selected-csv': () => exportSelected('csv'),
    import: openImport,
    template: downloadTemplate,
  }
  actions[command]?.()
}

function viewDetail(id) {
  router.push({ path: `/devices/${id}`, query: listReturnQuery() })
}

function addDevice() {
  router.push({ path: '/devices/add', query: listReturnQuery() })
}

function listReturnQuery() {
  const query = {}
  if (pagination.page > 1) query.page = String(pagination.page)
  if (pagination.size !== 20) query.size = String(pagination.size)
  if (searchForm.search) query.search = searchForm.search
  if (searchForm.device_type) query.device_type = searchForm.device_type
  if (searchForm.group_id) query.group_id = String(searchForm.group_id)
  return query
}

function editDevice(row) {
  router.push({ path: `/devices/edit/${row.id}`, query: listReturnQuery() })
}

function copyDevice(row) {
  router.push({ path: `/devices/copy/${row.id}`, query: listReturnQuery() })
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(t('asset.list.confirmDeleteDevice', { name: row.name }), t('asset.list.confirmDelete'), {
      type: 'warning',
    })
    await assetApi.delete(row.id)
    ElMessage.success(t('asset.list.deviceDeleted'))
    if (deviceList.value.length === 1 && pagination.page > 1) pagination.page -= 1
    syncListQuery()
    loadDevices()
  } catch {
    // cancelled or error
  }
}

function handleSort() {
  // 支持排序
  loadDevices()
}

function restoreListContext() {
  const query = route.query
  const page = Number(query.page)
  const size = Number(query.size)
  if (Number.isFinite(page) && page > 0) pagination.page = Math.floor(page)
  if (Number.isFinite(size) && [10, 20, 50, 100].includes(Math.floor(size))) {
    pagination.size = Math.floor(size)
  }
  if (typeof query.search === 'string') searchForm.search = query.search
  if (typeof query.device_type === 'string') searchForm.device_type = query.device_type
  if (typeof query.group_id === 'string') searchForm.group_id = query.group_id
}

onMounted(() => {
  restoreListContext()
  loadGroups()
  loadDevices()
})
</script>

<style scoped>
.asset-list {
  height: 100%;
}

.toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
}

.toolbar-filters,
.toolbar-right {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.toolbar-right {
  margin-left: auto;
  justify-content: flex-end;
}

.toolbar-search { width: 250px; }
.toolbar-select { width: 145px; }

.import-tip {
  margin-bottom: 14px;
}

.mode-hint {
  font-size: 12px;
  color: #909399;
  line-height: 1.4;
  margin-top: 4px;
}

.import-result {
  margin-top: 8px;
}

.error-table {
  margin-top: 12px;
}

.text-danger {
  color: #f56c6c;
  font-weight: 600;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 20px;
}

.cabinet-name {
  margin-left: 6px;
  font-size: 12px;
  color: #606266;
}

.muted {
  color: #c0c4cc;
}

.device-name-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.device-icon {
  width: 26px;
  height: 26px;
  border-radius: 6px;
  object-fit: contain;
  background: #f5f7fa;
  flex-shrink: 0;
}

.device-icon.placeholder {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: #909399;
  border: 1px solid #e4e7ed;
}

.form-hint {
  margin-left: 10px;
  font-size: 12px;
  color: #909399;
}

.preset-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  margin: 6px 0 10px;
}

.preset-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(92px, 1fr));
  gap: 10px;
  max-height: 300px;
  overflow-y: auto;
  padding: 2px;
}

.preset-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 8px 4px 6px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.preset-cell:hover {
  border-color: #409eff;
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.16);
}

.preset-cell.active {
  border-color: #409eff;
  background: #ecf5ff;
}

.preset-cell img {
  width: 44px;
  height: 44px;
  object-fit: contain;
  border-radius: 8px;
}

.preset-cell span {
  font-size: 11px;
  color: #606266;
  text-align: center;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.batch-preview {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-right: auto;
  font-size: 12px;
  color: #67c23a;
}

.batch-preview img {
  width: 24px;
  height: 24px;
  object-fit: contain;
}

/* 设备名称旁的告警铃铛 + 数量，避免表格横向滚动时被遮挡 */
.device-alert {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: 6px;
  flex-shrink: 0;
}

.device-alert .el-tag {
  min-width: 22px;
  justify-content: center;
}

.selection-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  margin-left: 6px;
  padding: 0 5px;
  border-radius: 9px;
  background: rgba(64, 158, 255, 0.14);
  color: #409eff;
  font-size: 11px;
}

.bulk-edit-tip {
  margin-bottom: 16px;
}

.bulk-field {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.bulk-field .el-checkbox {
  flex-shrink: 0;
  width: 52px;
  margin-right: 0;
}

.bulk-field .el-select,
.bulk-field .el-input {
  flex: 1;
}
.cabinet-location-cell { display: flex; flex-direction: column; align-items: center; gap: 3px; min-width: 0; text-align: center; }
.cabinet-location-main { display: flex; align-items: center; justify-content: center; gap: 6px; min-width: 0; }
.cabinet-location-meta { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; color: #7b91a3; font-size: 10px; line-height: 1.4; }
.cabinet-location-meta span { white-space: nowrap; }
.asset-rule-list { width: 100%; max-height: 76px; overflow-y: auto; padding-right: 2px; text-align: center; }
.asset-rule-item { display: flex; align-items: center; justify-content: center; gap: 6px; min-height: 22px; color: #536b7c; font-size: 11px; text-align: center; }
.asset-rule-item + .asset-rule-item { border-top: 1px dashed #e7eef4; }
.asset-rule-item.triggered { color: #b45309; }
.asset-rule-item.disabled { color: #94a3b8; }
.asset-rule-metric { min-width: 72px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.asset-rule-value { min-width: 42px; color: #0f766e; font-family: Consolas, monospace; font-size: 11px; }
.asset-rule-item.triggered .asset-rule-value { color: #dc2626; }
.asset-rule-threshold { color: #8ba0af; white-space: nowrap; }
.asset-rule-more { display: inline-block; padding-top: 2px; color: #8ba0af; font-size: 10px; }
.asset-dashboard-metrics { display: flex; flex-direction: column; gap: 3px; text-align: left; }
.asset-dashboard-metric { display: flex; flex-direction: column; gap: 2px; padding: 4px 7px; border: 1px solid #e4edf5; border-radius: 5px; background: #f8fbfe; color: #536b7c; font-size: 10px; }
.asset-dashboard-metric-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.asset-dashboard-metric-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.asset-dashboard-metric b { color: #0f766e; font-family: Consolas, monospace; font-size: 10px; white-space: nowrap; }
.asset-dashboard-metric-thresholds { display: flex; gap: 10px; color: #8ba0af; font-size: 9px; }
.asset-dashboard-metric-thresholds em { color: #64748b; font-style: normal; font-family: Consolas, monospace; }
.asset-dashboard-metric.warning { border-color: #fde68a; background: #fffbeb; color: #a16207; }
.asset-dashboard-metric.warning b { color: #b45309; }
.asset-dashboard-metric.warning .asset-dashboard-metric-thresholds em { color: #b45309; }
.asset-dashboard-metric.critical { border-color: #fecaca; background: #fef2f2; color: #b91c1c; }
.asset-dashboard-metric.critical b { color: #dc2626; }
.asset-dashboard-metric.critical .asset-dashboard-metric-thresholds em { color: #dc2626; }
.asset-dashboard-more { padding-left: 2px; color: #8ba0af; font-size: 10px; }
@media (max-width: 900px) {
  .toolbar-search { width: 100%; }
  .toolbar-filters { width: 100%; }
  .toolbar-select { flex: 1 1 140px; width: auto; }
}
</style>
