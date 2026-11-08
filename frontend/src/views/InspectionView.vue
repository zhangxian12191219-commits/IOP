<template>
  <div class="inspection-view">
    <el-card>
      <template #header>
        <div class="ins-head">
          <div>
            <div class="ins-title">设备巡检</div>
            <div class="ins-sub">
              定时或手动汇总资产最新指标与未确认告警，生成 Word 巡检报告；也支持上传现场巡检报告留存
            </div>
          </div>
          <div class="ins-head-actions">
            <el-tag
              v-if="overview"
              :type="overview.scheduler?.running ? 'success' : 'info'"
              size="small"
            >
              调度器 {{ overview.scheduler?.running ? '运行中' : '未运行' }}
            </el-tag>
            <el-tag
              v-if="overview"
              :type="overview.docx_available ? 'success' : 'danger'"
              size="small"
            >
              {{ overview.docx_available ? 'Word 组件就绪' : '缺少 python-docx' }}
            </el-tag>
            <el-tag v-if="overview?.office_ready" type="success" size="small">在线 Office 就绪</el-tag>
            <el-tag v-if="overview" type="info" size="small">报告保留 {{ overview.retention_days ?? 15 }} 天</el-tag>
            <el-button size="small" :disabled="!canEdit" @click="openRetention">保留设置</el-button>
            <el-button size="small" :loading="loading" @click="loadAll">刷新</el-button>
          </div>
        </div>
      </template>

      <el-alert
        v-if="overview && !overview.docx_available"
        class="ins-alert"
        type="error"
        :closable="false"
        show-icon
        title="服务器未安装 python-docx，暂时无法生成内置 Word 巡检报告"
      />

      <div class="ins-stats">
        <div><span>巡检任务</span><b>{{ overview?.stats?.tasks ?? 0 }}</b></div>
        <div><span>启用中</span><b class="ok">{{ overview?.stats?.tasks_enabled ?? 0 }}</b></div>
        <div><span>巡检报告</span><b>{{ overview?.stats?.reports ?? 0 }}</b></div>
        <div><span>系统生成</span><b>{{ overview?.stats?.builtin_reports ?? 0 }}</b></div>
        <div><span>上传报告</span><b>{{ overview?.stats?.upload_reports ?? 0 }}</b></div>
      </div>

      <el-tabs v-model="activeTab" @tab-change="onTabChange">
        <!-- ==================== 巡检任务 ==================== -->
        <el-tab-pane label="巡检任务" name="tasks">
          <div class="ins-toolbar">
            <el-input
              v-model="taskKeyword"
              size="small"
              clearable
              placeholder="任务名称 / 创建人"
              style="width: 200px"
              @keyup.enter="loadTasks(1)"
              @clear="loadTasks(1)"
            />
            <el-select
              v-model="taskEnabledFilter"
              size="small"
              clearable
              placeholder="启用状态"
              style="width: 130px"
              @change="loadTasks(1)"
            >
              <el-option label="已启用" value="enabled" />
              <el-option label="已停用" value="disabled" />
            </el-select>
            <el-button size="small" @click="loadTasks(1)">查询</el-button>
            <div class="ins-toolbar-right">
              <el-button
                type="primary"
                size="small"
                :disabled="!canEdit"
                @click="openTaskDialog()"
              >
                <el-icon><Plus /></el-icon>新建巡检任务
              </el-button>
            </div>
          </div>

          <el-table v-loading="taskLoading" :data="tasks" size="small" border class="ins-task-table" style="width: 100%">
            <el-table-column label="任务名称" min-width="200">
              <template #default="{ row }">
                <div class="task-name">{{ row.name }}</div>
                <div class="task-meta">
                  <el-tag v-if="row.include_virtualization" size="small" type="info" effect="plain">含虚拟化</el-tag>
                  <span v-if="row.created_by">创建人 {{ row.created_by }}</span>
                  <span v-if="row.updated_at">更新 {{ formatDateTime(row.updated_at) }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="巡检对象" min-width="190">
              <template #default="{ row }">
                <el-tooltip :content="targetSummary(row)" placement="top">
                  <span class="target-summary">{{ targetSummary(row) }}</span>
                </el-tooltip>
                <div v-if="row.target_assets?.length" class="task-meta">
                  {{ row.target_assets.slice(0, 4).map((item) => item.name).join('、') }}
                  <span v-if="row.target_assets.length > 4">等</span>
                </div>
                <div v-if="row.custom_devices?.length" class="task-meta">
                  自定义：{{ row.custom_devices.slice(0, 3).map((item) => item.name).join('、') }}
                  <span v-if="row.custom_devices.length > 3">等</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column v-if="!isNarrowViewport" label="调度计划" min-width="150">
              <template #default="{ row }">
                <div>{{ row.schedule_text }}</div>
                <div class="task-meta">
                  下次：{{ row.enabled ? formatDateTime(row.next_run_at) : '已停用' }}
                </div>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
                  {{ row.enabled ? '已启用' : '已停用' }}
                </el-tag>
                <div class="task-meta" style="margin-top: 4px">
                  <el-tag :type="statusMeta(row.last_status).type" size="small" effect="plain">
                    {{ statusMeta(row.last_status).text }}
                  </el-tag>
                </div>
              </template>
            </el-table-column>
            <el-table-column v-if="!isCompactViewport" label="上次执行" min-width="160">
              <template #default="{ row }">
                <div>{{ row.last_run_at ? formatDateTime(row.last_run_at) : '-' }}</div>
                <el-tooltip v-if="row.last_message" :content="row.last_message" placement="top">
                  <span class="task-meta ellipsis">{{ row.last_message }}</span>
                </el-tooltip>
              </template>
            </el-table-column>
            <el-table-column label="操作" :width="isNarrowViewport ? 220 : 250" fixed="right">
              <template #default="{ row }">
                <el-button
                  type="success"
                  link
                  size="small"
                  :disabled="!canEdit"
                  :loading="runningTaskId === row.id"
                  @click="runTask(row)"
                >
                  立即巡检
                </el-button>
                <el-button v-if="row.enabled" type="warning" link size="small" :disabled="!canEdit" @click="stopTask(row)">
                  停止巡检
                </el-button>
                <el-button type="primary" link size="small" :disabled="!canEdit" @click="openTaskDialog(row)">
                  编辑
                </el-button>
                <el-button type="danger" link size="small" :disabled="!canEdit" @click="removeTask(row)">
                  删除
                </el-button>
              </template>
            </el-table-column>
            <template #empty>
              <el-empty :description="taskKeyword || taskEnabledFilter ? '没有符合条件的巡检任务' : '还没有巡检任务'" :image-size="60">
                <el-button v-if="canEdit" type="primary" size="small" @click="openTaskDialog()">
                  新建巡检任务
                </el-button>
              </el-empty>
            </template>
          </el-table>

          <div v-if="taskTotal > taskPageSize" class="ins-pager">
            <el-pagination
              v-model:current-page="taskPage"
              :page-size="taskPageSize"
              :total="taskTotal"
              layout="total, prev, pager, next"
              small
              background
              @current-change="loadTasks"
            />
          </div>
        </el-tab-pane>

        <!-- ==================== 巡检报告 ==================== -->
        <el-tab-pane label="巡检报告" name="reports">
          <div class="ins-toolbar">
            <el-input
              v-model="reportKeyword"
              size="small"
              clearable
              placeholder="报告标题 / 任务名称"
              style="width: 220px"
              @keyup.enter="loadReports(1)"
              @clear="loadReports(1)"
            />
            <el-select
              v-model="reportSource"
              size="small"
              clearable
              placeholder="报告来源"
              style="width: 130px"
              @change="loadReports(1)"
            >
              <el-option label="系统生成" value="builtin" />
              <el-option label="本地上传" value="upload" />
            </el-select>
            <el-button size="small" @click="loadReports(1)">查询</el-button>
            <div class="ins-toolbar-right">
              <el-button type="primary" plain size="small" :disabled="!canEdit" @click="openUpload">
                <el-icon><Upload /></el-icon>上传巡检报告
              </el-button>
            </div>
          </div>

          <el-table v-loading="reportLoading" :data="reports" size="small" border style="width: 100%">
            <el-table-column label="报告标题" min-width="240">
              <template #default="{ row }">
                <div class="task-name">{{ row.title }}</div>
                <div v-if="row.task_name" class="task-meta">任务：{{ row.task_name }}</div>
              </template>
            </el-table-column>
            <el-table-column label="来源" width="110">
              <template #default="{ row }">
                <el-tag :type="row.source === 'upload' ? 'warning' : 'success'" size="small" effect="plain">
                  {{ row.source === 'upload' ? '本地上传' : '系统生成' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="设备 / 在线" width="110" align="center">
              <template #default="{ row }">
                {{ row.source === 'upload' ? '-' : `${row.online_count}/${row.device_count}` }}
              </template>
            </el-table-column>
            <el-table-column label="未确认告警" width="100" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.alert_count > 0" type="danger" size="small">{{ row.alert_count }}</el-tag>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column label="文件大小" width="100">
              <template #default="{ row }">{{ fileSize(row.file_size) }}</template>
            </el-table-column>
            <el-table-column label="生成时间" width="170">
              <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="260" fixed="right">
              <template #default="{ row }">
                <el-button type="primary" link size="small" @click="openReportPreview(row)">预览</el-button>
                <el-button type="primary" link size="small" @click="openReportDetail(row)">详情</el-button>
                <el-button type="success" link size="small" @click="downloadReport(row)">下载 Word</el-button>
                <el-button type="danger" link size="small" :disabled="!canEdit" @click="removeReport(row)">
                  删除
                </el-button>
              </template>
            </el-table-column>
            <template #empty>
              <el-empty description="还没有巡检报告" :image-size="60">
                <el-button v-if="canEdit" type="primary" size="small" @click="openTaskDialog()">
                  新建巡检任务并立即巡检
                </el-button>
              </el-empty>
            </template>
          </el-table>

          <div v-if="reportTotal > reportPageSize" class="ins-pager">
            <el-pagination
              v-model:current-page="reportPage"
              :page-size="reportPageSize"
              :total="reportTotal"
              layout="total, prev, pager, next"
              small
              background
              @current-change="loadReports"
            />
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- ==================== 新建 / 编辑巡检任务 ==================== -->
    <el-dialog
      v-model="taskDialog"
      :title="taskForm.id ? '编辑巡检任务' : '新建巡检任务'"
      width="min(860px, 94vw)"
      :close-on-click-modal="false"
    >
      <el-form label-position="top" class="task-form">
        <el-row :gutter="16">
          <el-col :span="16">
            <el-form-item label="任务名称" required>
              <el-input v-model="taskForm.name" maxlength="200" show-word-limit placeholder="如：核心交换机每日巡检" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="启用定时巡检">
              <el-switch v-model="taskForm.enabled" active-text="启用" inactive-text="停用" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="巡检对象">
          <el-radio-group v-model="taskForm.target_mode">
            <el-radio-button value="assets">资产库设备</el-radio-button>
            <el-radio-button value="custom">自定义设备</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <template v-if="taskForm.target_mode === 'assets'">
          <el-form-item label="选择资产（可搜索、多选）" required>
            <el-select
              v-model="taskForm.asset_ids"
              multiple
              filterable
              remote
              reserve-keyword
              :remote-method="searchAssets"
              :loading="assetLoading"
              placeholder="输入设备名称或 IP 搜索"
              style="width: 100%"
            >
              <el-option
                v-for="item in assetOptions"
                :key="item.id"
                :label="`${item.name}（${item.ip_address}）`"
                :value="item.id"
              />
            </el-select>
            <div class="form-help asset-select-help">
              <span>已选 {{ taskForm.asset_ids.length }} 台资产；巡检时会读取最新采集指标与未确认告警</span>
              <span class="asset-select-actions">
                <el-button type="success" plain size="small" :loading="assetLoading" @click="selectAllAssets">全选设备</el-button>
                <el-button type="warning" plain size="small" :disabled="!taskForm.asset_ids.length" @click="clearAllAssets">全部取消</el-button>
              </span>
            </div>
            <el-alert v-if="credentialAssetsNotSelected.length" type="warning" :closable="false" show-icon class="credential-miss-alert"
              :title="`有 ${credentialAssetsNotSelected.length} 台已关联设备凭据的资产未选入本次巡检，可能导致巡检漏检或命令无法执行。`">
              <div class="credential-miss-list">{{ credentialAssetsNotSelected.map((item) => item.name).slice(0, 12).join('、') }}{{ credentialAssetsNotSelected.length > 12 ? '…' : '' }}</div>
              <el-button size="small" type="warning" plain @click="selectMissingCredentialAssets">补选这些资产</el-button>
            </el-alert>
          </el-form-item>

        </template>



        <template v-else>
          <el-form-item label="自定义设备">
            <div class="custom-device-box">
              <el-table :data="taskForm.custom_devices" size="small" border>
                <el-table-column label="设备名称" min-width="150">
                  <template #default="{ row }">
                    <el-input v-model="row.name" size="small" maxlength="120" placeholder="名称" />
                  </template>
                </el-table-column>
                <el-table-column label="IP / 地址" min-width="140">
                  <template #default="{ row }">
                    <el-input v-model="row.ip_address" size="small" maxlength="120" placeholder="IP 或地址" />
                  </template>
                </el-table-column>
                <el-table-column label="厂商" width="130">
                  <template #default="{ row }">
                    <el-input v-model="row.vendor" size="small" maxlength="100" placeholder="华为/H3C/山石" />
                  </template>
                </el-table-column>
                <el-table-column label="类型" width="115">
                  <template #default="{ row }">
                    <el-select v-model="row.device_type" size="small">
                      <el-option
                        v-for="item in DEVICE_TYPE_OPTIONS"
                        :key="item.value"
                        :label="item.label"
                        :value="item.value"
                      />
                    </el-select>
                  </template>
                </el-table-column>
                <el-table-column label="自定义命令" min-width="180">
                  <template #default="{ row }">
                    <el-input v-model="row.custom_command" size="small" maxlength="200" placeholder="未匹配厂商时填写" />
                  </template>
                </el-table-column>
                <el-table-column label="备注" min-width="130">
                  <template #default="{ row }">
                    <el-input v-model="row.note" size="small" maxlength="500" placeholder="备注（可选）" />
                  </template>
                </el-table-column>
                <el-table-column width="60" align="center">
                  <template #default="{ $index }">
                    <el-button link type="danger" size="small" @click="removeCustomDevice($index)">删除</el-button>
                  </template>
                </el-table-column>
                <template #empty>
                  <span class="form-help">暂未添加自定义设备</span>
                </template>
              </el-table>
              <el-button size="small" class="custom-add-btn" @click="addCustomDevice">
                <el-icon><Plus /></el-icon>添加自定义设备
              </el-button>
              <div class="form-help">
                自定义设备未纳管采集，报告中仅记录设备清单与备注；如需 CPU/内存/温度等指标，请先在资产管理中纳管
              </div>
            </div>
          </el-form-item>
        </template>

        <el-form-item label="厂商巡检命令">
          <div class="command-option-box">
            <el-switch v-model="taskForm.run_commands" active-text="执行" inactive-text="不执行" />
            <el-alert type="info" :closable="false" show-icon class="inspection-credential-tip"
              title="SSH 凭据优先复用“设备凭据”模块；设备未关联凭据时，才使用设备备份中的 SSH 用户名/密码。两者都没有时只在报告中列出命令计划。" />
            <div class="form-help">
              执行厂商命令：系统配置、运行状态、CPU、内存和日志异常检查。
            </div>
            <div v-if="commandPreviewLoading" class="form-help">正在匹配厂商命令…</div>
            <div v-else-if="commandPreview.length" class="command-preview-list">
              <div v-for="group in commandPreview" :key="group.profile" class="command-preview-group">
                <div class="command-preview-title">
                  <b>{{ group.vendor_label }}</b>
                  <span>{{ group.devices?.length || 0 }} 台设备</span>
                </div>
                <div class="command-preview-commands">
                  <span v-for="cmd in group.commands" :key="cmd.key">{{ cmd.label }}：<code>{{ cmd.command }}</code></span>
                </div>
              </div>
            </div>
            <div v-if="unmatchedVendors.length" class="command-unmatched">
              未匹配厂商：{{ unmatchedVendors.join('、') }}。请在自定义设备行填写“自定义命令”，否则只能生成指标巡检。
            </div>
            <div v-else-if="taskForm.target_mode === 'assets' && taskForm.asset_ids.length && !commandPreview.length" class="form-help">未匹配到厂商命令</div>
          </div>
        </el-form-item>

        <el-form-item label="虚拟化平台巡检">
          <el-switch v-model="taskForm.include_virtualization" active-text="纳入报告" inactive-text="不纳入" />
          <div class="form-help">
            开启后会把启用的虚拟化平台、宿主机、虚拟机和未确认虚拟化告警写入本次巡检报告；平台需先在「虚拟化管理」中配置。
          </div>
        </el-form-item>

        <el-form-item label="执行计划">
          <div class="schedule-box">
            <el-radio-group v-model="taskForm.schedule_type">
              <el-radio-button value="interval">每 N 小时</el-radio-button>
              <el-radio-button value="daily">每天固定时间</el-radio-button>
            </el-radio-group>
            <template v-if="taskForm.schedule_type === 'interval'">
              <span class="schedule-label">间隔</span>
              <el-input-number
                v-model="taskForm.interval_hours"
                :min="1"
                :max="8760"
                :step="1"
                controls-position="right"
              />
              <span class="schedule-label">小时</span>
            </template>
            <template v-else>
              <span class="schedule-label">每天</span>
              <el-time-picker
                v-model="taskForm.daily_time"
                format="HH:mm"
                value-format="HH:mm"
                placeholder="选择执行时间"
                style="width: 150px"
              />
            </template>
            <div class="form-help">
              定时任务由后台调度器每 60 秒检查一次；每日时间按系统时区（{{ systemTimezone }}）执行
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="taskDialog = false">取消</el-button>
        <el-button type="primary" :loading="taskSaving" @click="saveTask">保存任务</el-button>
      </template>
    </el-dialog>

    <!-- ==================== 报告详情 ==================== -->
    <el-dialog v-model="detailVisible" title="巡检报告详情" width="min(1000px, 96vw)" top="6vh">
      <div v-loading="detailLoading" class="ins-detail-body">
        <template v-if="reportDetail">
          <div class="detail-head">
            <div>
              <div class="detail-title">{{ reportDetail.title }}</div>
              <div class="task-meta">
                任务：{{ reportDetail.task_name || '独立报告' }} ·
                {{ reportDetail.source === 'upload' ? '本地上传' : '系统生成' }} ·
                {{ reportDetail.trigger === 'scheduled' ? '定时执行' : reportDetail.trigger === 'upload' ? '上传' : '手动执行' }}
              </div>
            </div>
            <div class="detail-head-tags">
              <el-tag :type="reportDetail.source === 'upload' ? 'warning' : 'success'" size="small" effect="plain">
                {{ reportDetail.source === 'upload' ? '本地上传' : '系统生成' }}
              </el-tag>
              <el-tag type="info" size="small" effect="plain">{{ fileSize(reportDetail.file_size) }}</el-tag>
            </div>
          </div>

          <el-descriptions :column="3" border size="small" class="detail-desc">
            <el-descriptions-item label="生成时间">
              {{ formatDateTime(reportDetail.created_at) }}
            </el-descriptions-item>
            <el-descriptions-item label="生成人">{{ reportDetail.created_by || '-' }}</el-descriptions-item>
            <el-descriptions-item label="报告文件">{{ reportDetail.original_filename || '-' }}</el-descriptions-item>
          </el-descriptions>

          <template v-if="reportDetail.payload?.kind === 'upload'">
            <el-alert
              type="info"
              :closable="false"
              show-icon
              class="ins-alert"
              title="这是用户上传的 Word 巡检报告，系统保留原始文件并提供 .docx 下载"
            />
            <p v-if="reportDetail.conclusion" class="detail-paragraph">{{ reportDetail.conclusion }}</p>
            <p v-else class="detail-paragraph">上传人未填写备注。</p>
          </template>

          <template v-else>
            <div class="detail-stats">
              <div><span>设备总数</span><b>{{ reportDetail.payload?.stats?.total ?? reportDetail.device_count }}</b></div>
              <div><span>在线</span><b class="ok">{{ reportDetail.payload?.stats?.online ?? reportDetail.online_count }}</b></div>
              <div><span>离线</span><b class="danger">{{ reportDetail.payload?.stats?.offline ?? 0 }}</b></div>
              <div><span>状态未知</span><b>{{ reportDetail.payload?.stats?.unknown ?? 0 }}</b></div>
              <div><span>未确认告警</span><b class="danger">{{ reportDetail.payload?.stats?.unack_alerts ?? reportDetail.alert_count }}</b></div>
            </div>

            <h4 class="detail-section-title">巡检结论</h4>
            <p class="detail-paragraph">{{ reportDetail.conclusion || reportDetail.summary || '-' }}</p>

            <h4 class="detail-section-title">整改建议</h4>
            <ol v-if="reportDetail.recommendations?.length" class="detail-list">
              <li v-for="(item, index) in reportDetail.recommendations" :key="index">{{ item }}</li>
            </ol>
            <p v-else class="detail-paragraph">本次巡检未发现需要整改的问题。</p>

            <h4 class="detail-section-title">
              设备明细（{{ reportDetail.payload?.devices?.length || 0 }} 台）
            </h4>
            <el-table :data="reportDetail.payload?.devices || []" size="small" border max-height="380">
              <el-table-column type="expand">
                <template #default="{ row }">
                  <div class="device-expand">
                    <div v-if="row.issues?.length">
                      <strong>发现问题：</strong>
                      <div v-for="(issue, index) in row.issues" :key="`i${index}`" class="expand-line">
                        <el-tag :type="issueTagType(issue.level)" size="small">{{ issue.level }}</el-tag>
                        <span>{{ issue.description }}</span>
                        <span class="task-meta">建议：{{ issue.recommendation }}</span>
                      </div>
                    </div>
                    <div v-else class="task-meta">未发现异常项</div>
                    <div v-if="row.alerts?.length" class="expand-alerts">
                      <strong>未确认告警：</strong>
                      <div v-for="alert in row.alerts" :key="alert.id" class="expand-line alert-detail-line" :style="{ color: alertLevelColor(alert.level) }">
                        <el-tag :type="alertTagType(alert.level)" size="small">{{ alert.level_label || alert.level }}</el-tag>
                        <span class="alert-detail-text">告警对象：{{ alert.device_name || row.name }}{{ alert.device_ip ? `（${alert.device_ip}）` : '' }}｜时间：{{ formatDateTime(alert.created_at) }}｜告警原因：{{ alert.reason || alert.message || alert.type }}</span>
                      </div>
                    </div>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="设备" min-width="190">
                <template #default="{ row }">
                  <div class="task-name">{{ row.name }}</div>
                  <div class="task-meta">{{ row.ip_address }} · {{ deviceTypeLabel(row.device_type) }}</div>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="100">
                <template #default="{ row }">
                  <el-tag :type="onlineMeta(row).type" size="small">{{ onlineMeta(row).text }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="CPU" width="80" align="center">
                <template #default="{ row }">{{ percentText(row.cpu_usage) }}</template>
              </el-table-column>
              <el-table-column label="内存" width="80" align="center">
                <template #default="{ row }">{{ percentText(row.memory_usage) }}</template>
              </el-table-column>
              <el-table-column label="温度" width="80" align="center">
                <template #default="{ row }">{{ tempText(row.temperature) }}</template>
              </el-table-column>
              <el-table-column label="磁盘" width="80" align="center">
                <template #default="{ row }">{{ percentText(row.disk_usage) }}</template>
              </el-table-column>
              <el-table-column label="电源" width="80" align="center">
                <template #default="{ row }">{{ powerText(row.power_status) }}</template>
              </el-table-column>
              <el-table-column label="未确认告警" width="100" align="center">
                <template #default="{ row }">
                  <el-tag v-if="row.unack_alert_count > 0" type="danger" size="small">{{ row.unack_alert_count }}</el-tag>
                  <span v-else>-</span>
                </template>
              </el-table-column>
              <el-table-column label="问题" width="70" align="center">
                <template #default="{ row }">
                  <el-tag v-if="row.issues?.length" type="warning" size="small">{{ row.issues.length }}</el-tag>
                  <span v-else class="ok-text">正常</span>
                </template>
              </el-table-column>
            </el-table>

            <template v-if="reportDetail.payload?.virtualization?.enabled">
              <h4 class="detail-section-title">
                虚拟化平台巡检（{{ reportDetail.payload.virtualization.stats?.platforms || 0 }} 个平台）
              </h4>
              <div class="detail-stats">
                <div><span>宿主机</span><b>{{ reportDetail.payload.virtualization.stats?.hosts || 0 }}</b></div>
                <div><span>虚拟机</span><b>{{ reportDetail.payload.virtualization.stats?.vms || 0 }}</b></div>
                <div><span>未确认虚拟化告警</span><b class="danger">{{ reportDetail.payload.virtualization.stats?.alerts || 0 }}</b></div>
              </div>
              <div v-if="!reportDetail.payload.virtualization.platforms?.length" class="task-meta">已开启虚拟化平台巡检，但当前没有启用的平台。</div>
              <el-table :data="reportDetail.payload.virtualization.platforms || []" size="small" border max-height="360">
                <el-table-column type="expand">
                  <template #default="{ row }">
                    <div class="device-expand">
                      <div v-if="row.hosts?.length">
                        <strong>宿主机：</strong>
                        <el-table :data="row.hosts" size="small" border>
                          <el-table-column prop="name" label="名称" min-width="150" />
                          <el-table-column prop="ip_address" label="IP" width="130" />
                          <el-table-column prop="status" label="状态" width="90" />
                          <el-table-column label="CPU" width="80"><template #default="{ row: h }">{{ percentText(h.cpu_usage) }}</template></el-table-column>
                          <el-table-column label="内存" width="80"><template #default="{ row: h }">{{ percentText(h.memory_usage) }}</template></el-table-column>
                          <el-table-column label="存储" width="80"><template #default="{ row: h }">{{ percentText(h.storage_usage) }}</template></el-table-column>
                        </el-table>
                      </div>
                      <div v-if="row.alerts?.length" class="expand-alerts">
                        <strong>未确认虚拟化告警：</strong>
                        <div v-for="alert in row.alerts" :key="alert.id" class="expand-line alert-detail-line" :style="{ color: alertLevelColor(alert.level) }">
                          <el-tag :type="alertTagType(alert.level)" size="small">{{ alert.level_label || alert.level }}</el-tag>
                          <span class="alert-detail-text">告警对象：{{ alert.vm_name || alert.platform_name || row.name }}｜时间：{{ formatDateTime(alert.created_at) }}｜告警原因：{{ alert.reason || alert.message }}</span>
                        </div>
                      </div>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column prop="name" label="平台" min-width="170" />
                <el-table-column prop="platform_type_label" label="类型" width="130" />
                <el-table-column label="宿主机" width="100"><template #default="{ row }">{{ row.host_online }}/{{ row.host_count }}</template></el-table-column>
                <el-table-column label="虚拟机" width="100"><template #default="{ row }">{{ row.vm_running }}/{{ row.vm_count }}</template></el-table-column>
                <el-table-column label="告警" width="80"><template #default="{ row }"><el-tag v-if="row.alerts?.length" type="danger" size="small">{{ row.alerts.length }}</el-tag><span v-else>-</span></template></el-table-column>
              </el-table>
            </template>
          </template>
        </template>
        <el-empty v-else-if="!detailLoading" description="报告内容为空" :image-size="60" />
      </div>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
        <el-button type="primary" :disabled="!reportDetail" @click="downloadReport(reportDetail)">
          下载 Word 报告
        </el-button>
      </template>
    </el-dialog>

    <!-- ==================== Word 在线预览 ==================== -->
    <el-dialog v-model="previewVisible" :title="previewTitle || 'Word 在线预览'" width="min(1100px, 96vw)" top="4vh">
      <div v-loading="previewLoading" class="report-preview-word preview-dialog-body">
        <div v-if="previewHtml" v-html="previewHtml"></div>
        <p v-else class="task-meta">正在读取 Word 内容或文件无可预览文本。</p>
      </div>
      <template #footer>
        <el-button @click="previewVisible = false">关闭</el-button>
        <el-button type="primary" :disabled="!previewReport" @click="downloadReport(previewReport)">下载 Word 报告</el-button>
      </template>
    </el-dialog>

    <!-- ==================== ONLYOFFICE 在线编辑 ==================== -->
    <el-dialog
      v-model="officeVisible"
      :title="officeTitle || 'Word 在线编辑'"
      width="min(1200px, 98vw)"
      top="2vh"
      destroy-on-close
      @closed="closeOfficeEditor"
    >
      <div class="office-editor-bar">
        <span>可直接在编辑器中修改内容，点击 ONLYOFFICE 工具栏的保存按钮写回巡检报告。</span>
        <span v-if="officeConfig?.document_server_url" class="muted">{{ officeConfig.document_server_url }}</span>
      </div>
      <div v-loading="officeLoading" class="office-editor-wrap">
        <div id="inspection-office-editor" class="office-editor-host"></div>
        <el-alert v-if="officeError" type="error" :closable="false" show-icon :title="officeError" />
      </div>
      <template #footer>
        <el-button @click="officeVisible = false">关闭</el-button>
        <el-button type="primary" :disabled="!previewReport" @click="downloadReport(previewReport)">下载 Word 报告</el-button>
      </template>
    </el-dialog>

    <!-- ==================== 上传巡检报告 ==================== -->
    <el-dialog v-model="retentionVisible" title="巡检设置" width="min(480px, 94vw)">
      <el-form label-position="top">
        <el-form-item label="报告保留天数">
          <el-input-number v-model="retentionDays" :min="0" :max="3650" :step="1" controls-position="right" style="width: 180px" />
        </el-form-item>
        <div class="form-help">
          默认保留 15 天；填 0 表示永久保留。到期报告及对应 Word 文件由巡检调度每小时自动清理。
        </div>
        <el-divider content-position="left">在线 Office 编辑（ONLYOFFICE）</el-divider>
        <el-form-item label="启用在线编辑">
          <el-switch v-model="officeSettings.enabled" />
        </el-form-item>
        <template v-if="officeSettings.enabled">
          <el-form-item label="Document Server 地址">
            <el-input v-model="officeSettings.document_server_url" placeholder="http://192.168.1.50:8080" />
            <div class="form-help">ONLYOFFICE Document Server 地址，需能被浏览器和本系统访问。</div>
          </el-form-item>
          <el-form-item label="产品对外地址">
            <el-input v-model="officeSettings.public_base_url" placeholder="https://nms.example.com" />
            <div class="form-help">Document Server 访问本系统的地址，用于拉取 Word 文件和保存回调。</div>
          </el-form-item>
          <el-form-item label="JWT 密钥">
            <el-input
              v-model="officeSettings.jwt_secret"
              type="password"
              show-password
              autocomplete="new-password"
              :placeholder="officeSettings.has_secret ? '已设置，留空保持不变' : '与 Document Server 的 JWT 密钥一致'"
            />
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="retentionVisible = false">取消</el-button>
        <el-button type="primary" :loading="retentionSaving" @click="saveRetention">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="uploadVisible" title="上传巡检报告" width="min(600px, 94vw)" :close-on-click-modal="false">
      <el-form label-position="top">
        <el-form-item label="报告标题">
          <el-input v-model="uploadForm.title" maxlength="300" placeholder="留空则使用文件名" />
        </el-form-item>
        <el-form-item label="关联巡检任务（可选）">
          <el-select v-model="uploadForm.task_id" clearable placeholder="不关联任务" style="width: 100%">
            <el-option
              v-for="item in tasks"
              :key="item.id"
              :label="item.name"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="报告备注（可选）">
          <el-input v-model="uploadForm.note" type="textarea" :rows="3" maxlength="2000" placeholder="记录现场巡检情况、整改要求等" />
        </el-form-item>
        <el-form-item label="Word 报告文件" required>
          <el-upload
            ref="uploadRef"
            drag
            :auto-upload="false"
            :limit="1"
            accept=".docx"
            :file-list="uploadFileList"
            :on-change="onUploadChange"
            :on-remove="onUploadRemove"
            :on-exceed="onUploadExceed"
            style="width: 100%"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">拖拽 .docx 文件到此处，或<em>点击选择文件</em></div>
            <template #tip>
              <div class="el-upload__tip">
                仅支持 Word .docx，最大 {{ overview?.max_upload_mb || 50 }}MB；旧版 .doc 请先在 Word/WPS 中另存为 .docx
              </div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="uploadVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploadSaving" :disabled="!uploadFile" @click="submitUpload">
          上传报告
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { assetApi, credentialApi, inspectionApi } from '@/api'
import { can, downloadWithAuth } from '@/store/auth'
import { settings } from '@/store/settings'
import { formatDateTime } from '@/utils/time'
import { DEVICE_TYPE_OPTIONS, deviceTypeLabel } from '@/constants/device'

const canEdit = computed(() => can('inspection:edit'))
const credentialAssetsNotSelected = computed(() => {
  const selected = new Set(taskForm.asset_ids)
  return credentialAssets.value.filter((item) => !selected.has(item.id))
})
const systemTimezone = computed(() => settings.timezone || '服务器本地时间')

const loading = ref(false)
const overview = ref(null)
const activeTab = ref('tasks')
const viewportWidth = ref(typeof window !== 'undefined' ? window.innerWidth : 1440)
const isCompactViewport = computed(() => viewportWidth.value < 1320)
const isNarrowViewport = computed(() => viewportWidth.value < 980)

function updateViewportWidth() {
  viewportWidth.value = window.innerWidth
}
const retentionVisible = ref(false)
const retentionDays = ref(15)
const retentionSaving = ref(false)

// ---------- 任务 ----------
const tasks = ref([])
const taskTotal = ref(0)
const taskLoading = ref(false)
const taskKeyword = ref('')
const taskEnabledFilter = ref('')
const taskPage = ref(1)
const taskPageSize = ref(20)
const runningTaskId = ref(null)

const taskDialog = ref(false)
const taskSaving = ref(false)
const taskForm = reactive({
  id: null,
  name: '',
  enabled: true,
  target_mode: 'assets',
  asset_ids: [],
  custom_devices: [],
  include_virtualization: false,
  run_commands: true,
  schedule_type: 'interval',
  interval_hours: 24,
  daily_time: '02:00',
})
const assetOptions = ref([])
const assetLoading = ref(false)
const commandPreview = ref([])
const unmatchedVendors = ref([])
const credentialAssets = ref([])
const commandPreviewLoading = ref(false)
let commandPreviewTimer = null
let assetSearchTimer = null
let assetSearchSeq = 0

// ---------- 报告 ----------
const reports = ref([])
const reportTotal = ref(0)
const reportLoading = ref(false)
const reportKeyword = ref('')
const reportSource = ref('')
const reportPage = ref(1)
const reportPageSize = ref(20)

const detailVisible = ref(false)
const detailLoading = ref(false)
const previewVisible = ref(false)
const previewLoading = ref(false)
const previewHtml = ref('')
const previewTitle = ref('')
const previewReport = ref(null)
const officeVisible = ref(false)
const officeLoading = ref(false)
const officeError = ref('')
const officeTitle = ref('')
const officeConfig = ref(null)
let officeEditor = null
let officeScriptPromise = null

const officeSettings = reactive({
  enabled: false,
  document_server_url: '',
  public_base_url: '',
  jwt_secret: '',
  has_secret: false,
})
const reportDetail = ref(null)
const reportPreviewHtml = ref('')
const reportPreviewLoading = ref(false)

// ---------- 上传 ----------
const uploadVisible = ref(false)
const uploadSaving = ref(false)
const uploadRef = ref(null)
const uploadFile = ref(null)
const uploadFileList = ref([])
const uploadForm = reactive({ title: '', note: '', task_id: null })
const MAX_UPLOAD_MB = 50

// ==================== 数据加载 ====================
async function loadOverview() {
  try {
    const res = await inspectionApi.overview()
    overview.value = res.data
  } catch (error) {
    ElMessage.error(errorText(error, '加载巡检概览失败'))
  }
}

async function loadTasks(page = taskPage.value) {
  taskPage.value = page
  taskLoading.value = true
  try {
    const params = { page, page_size: taskPageSize.value }
    if (taskKeyword.value.trim()) params.keyword = taskKeyword.value.trim()
    if (taskEnabledFilter.value === 'enabled') params.enabled = true
    if (taskEnabledFilter.value === 'disabled') params.enabled = false
    const res = await inspectionApi.tasks(params)
    tasks.value = res.data.items || []
    taskTotal.value = res.data.total || 0
    if (!tasks.value.length && taskTotal.value > 0 && taskPage.value > 1) {
      await loadTasks(taskPage.value - 1)
    }
  } catch (error) {
    ElMessage.error(errorText(error, '加载巡检任务失败'))
  } finally {
    taskLoading.value = false
  }
}

async function loadReports(page = reportPage.value) {
  reportPage.value = page
  reportLoading.value = true
  try {
    const params = { page, page_size: reportPageSize.value }
    if (reportKeyword.value.trim()) params.keyword = reportKeyword.value.trim()
    if (reportSource.value) params.source = reportSource.value
    const res = await inspectionApi.reports(params)
    reports.value = res.data.items || []
    reportTotal.value = res.data.total || 0
    if (!reports.value.length && reportTotal.value > 0 && reportPage.value > 1) {
      await loadReports(reportPage.value - 1)
    }
  } catch (error) {
    ElMessage.error(errorText(error, '加载巡检报告失败'))
  } finally {
    reportLoading.value = false
  }
}

async function loadAll() {
  loading.value = true
  try {
    await Promise.all([loadOverview(), loadTasks(1), loadReports(1)])
  } finally {
    loading.value = false
  }
}

function onTabChange(tab) {
  if (tab === 'reports') loadReports(1)
  if (tab === 'tasks') loadTasks(taskPage.value)
}

// ==================== 资产选择 ====================
function mergeAssetOptions(items) {
  const selectedIds = new Set(taskForm.asset_ids)
  const selected = assetOptions.value.filter((item) => selectedIds.has(item.id))
  const map = new Map()
  ;[...selected, ...items].forEach((item) => map.set(item.id, item))
  assetOptions.value = [...map.values()]
}

function searchAssets(keyword) {
  if (assetSearchTimer) clearTimeout(assetSearchTimer)
  assetSearchTimer = setTimeout(() => doSearchAssets(keyword), 250)
}

async function doSearchAssets(keyword) {
  assetLoading.value = true
  const seq = ++assetSearchSeq
  try {
    const res = await assetApi.getList({
      page: 1,
      size: 50,
      search: keyword?.trim() || undefined,
    })
    if (seq !== assetSearchSeq) return
    const items = (res.data.items || []).map((item) => ({
      id: item.id,
      name: item.name,
      ip_address: item.ip_address,
    }))
    mergeAssetOptions(items)
  } catch (error) {
    if (seq === assetSearchSeq) {
      ElMessage.error(errorText(error, '加载资产列表失败'))
    }
  } finally {
    if (seq === assetSearchSeq) assetLoading.value = false
  }
}

async function loadCommandPreview() {
  if (commandPreviewTimer) clearTimeout(commandPreviewTimer)
  const customVendors = taskForm.custom_devices.map((item) => String(item.vendor || '').trim()).filter(Boolean)
  if (taskForm.target_mode === 'assets' && !taskForm.asset_ids.length) {
    commandPreview.value = []
    unmatchedVendors.value = []
    return
  }
  if (taskForm.target_mode === 'custom' && !customVendors.length) {
    commandPreview.value = []
    unmatchedVendors.value = []
    return
  }
  commandPreviewTimer = setTimeout(async () => {
    commandPreviewLoading.value = true
    try {
      const res = await inspectionApi.vendorCommands(
        taskForm.target_mode === 'assets' ? taskForm.asset_ids : [],
        taskForm.target_mode === 'custom' ? customVendors : [],
      )
      commandPreview.value = res.data?.groups || []
      unmatchedVendors.value = res.data?.unmatched_vendors || []
    } catch {
      commandPreview.value = []
      unmatchedVendors.value = []
    } finally {
      commandPreviewLoading.value = false
    }
  }, 180)
}

watch(
  () => [
    taskForm.asset_ids.join(','),
    taskForm.target_mode,
    taskForm.custom_devices.map((item) => item.vendor || '').join(','),
  ],
  () => loadCommandPreview(),
)

async function loadCredentialAssets() {
  try {
    const all = []
    let page = 1
    let total = 0
    do {
      const res = await credentialApi.list({ page, size: 200 })
      const items = res.data?.items || []
      all.push(...items)
      total = Number(res.data?.total || all.length)
      if (!items.length) break
      page += 1
    } while (all.length < total && page <= 20)
    credentialAssets.value = all.flatMap((row) =>
      (row.assets || []).map((asset) => ({
        id: asset.id,
        name: asset.name || asset.ip_address || `资产${asset.id}`,
        credential_name: row.name || '设备凭据',
      }))
    )
  } catch {
    credentialAssets.value = []
  }
}

function selectMissingCredentialAssets() {
  const ids = new Set(taskForm.asset_ids)
  for (const item of credentialAssetsNotSelected.value) ids.add(item.id)
  taskForm.asset_ids = [...ids]
}

// ==================== 任务编辑 ====================
function resetTaskForm() {
  Object.assign(taskForm, {
    id: null,
    name: '',
    enabled: true,
    target_mode: 'assets',
    asset_ids: [],
    custom_devices: [],
    include_virtualization: false,
    run_commands: true,
    schedule_type: 'interval',
    interval_hours: 24,
    daily_time: '02:00',
  })
}

function openTaskDialog(row = null) {
  resetTaskForm()
  assetOptions.value = []
  if (row) {
    Object.assign(taskForm, {
      id: row.id,
      name: row.name || '',
      enabled: Boolean(row.enabled),
      target_mode: row.target_mode === 'custom' ? 'custom' : 'assets',
      asset_ids: [...(row.asset_ids || [])],
      custom_devices: (row.custom_devices || []).map((item) => ({
        name: item.name || '',
        ip_address: item.ip_address || '',
        device_type: item.device_type || 'switch',
        vendor: item.vendor || '',
        custom_command: item.custom_command || '',
        note: item.note || '',
      })),
      include_virtualization: !!row.include_virtualization,
      run_commands: row.run_commands !== false,
      schedule_type: row.schedule_type === 'daily' ? 'daily' : 'interval',
      interval_hours: Number(row.interval_hours) || 24,
      daily_time: row.daily_time || '02:00',
    })
    assetOptions.value = (row.target_assets || []).map((item) => ({
      id: item.id,
      name: item.name,
      ip_address: item.ip_address,
    }))
  }
  taskDialog.value = true
  loadCredentialAssets()
  loadCommandPreview()
  searchAssets('')
}

function addCustomDevice() {
  taskForm.custom_devices.push({
    name: '',
    ip_address: '',
    device_type: 'switch',
    vendor: '',
    custom_command: '',
    note: '',
  })
}

function removeCustomDevice(index) {
  taskForm.custom_devices.splice(index, 1)
}

function cleanCustomDevices() {
  return taskForm.custom_devices
    .map((item) => ({
      name: String(item.name || '').trim(),
      ip_address: String(item.ip_address || '').trim(),
      device_type: item.device_type || 'other',
      note: String(item.note || '').trim(),
    }))
    .filter((item) => item.name || item.ip_address)
}

async function saveTask() {
  if (!canEdit.value) {
    ElMessage.warning('没有巡检任务编辑权限')
    return
  }
  const name = taskForm.name.trim()
  if (!name) {
    ElMessage.warning('请填写巡检任务名称')
    return
  }
  const payload = {
    name,
    enabled: Boolean(taskForm.enabled),
    target_mode: taskForm.target_mode,
    asset_ids: taskForm.target_mode === 'assets' ? [...taskForm.asset_ids] : [],
    custom_devices: taskForm.target_mode === 'custom' ? cleanCustomDevices() : [],
    include_virtualization: Boolean(taskForm.include_virtualization),
    run_commands: Boolean(taskForm.run_commands),
    schedule_type: taskForm.schedule_type,
    interval_hours: Number(taskForm.interval_hours) || 24,
    daily_time: taskForm.daily_time || '02:00',
  }
  if (taskForm.target_mode === 'assets' && !payload.asset_ids.length && !taskForm.include_virtualization) {
    ElMessage.warning('请选择至少一台资产设备，或开启虚拟化平台巡检')
    return
  }
  if (taskForm.target_mode === 'custom') {
    if (!payload.custom_devices.length) {
      ElMessage.warning('请添加至少一台自定义设备')
      return
    }
    const incomplete = payload.custom_devices.find((item) => !item.name || !item.ip_address)
    if (incomplete) {
      ElMessage.warning('自定义设备需要同时填写名称和 IP/地址')
      return
    }
  }
  taskSaving.value = true
  try {
    if (taskForm.id) {
      await inspectionApi.updateTask(taskForm.id, payload)
      ElMessage.success('巡检任务已保存')
    } else {
      await inspectionApi.createTask(payload)
      ElMessage.success('巡检任务已创建')
    }
    taskDialog.value = false
    await Promise.all([loadTasks(taskForm.id ? taskPage.value : 1), loadOverview()])
  } catch (error) {
    ElMessage.error(errorText(error, '保存巡检任务失败'))
  } finally {
    taskSaving.value = false
  }
}

async function runTask(row) {
  try {
    await ElMessageBox.confirm(
      `立即执行巡检任务「${row.name}」并生成 Word 报告？${row.device_count ? `本次将巡检 ${row.device_count} 台设备。` : ''}`,
      '立即巡检',
      { type: 'info', confirmButtonText: '立即巡检', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  runningTaskId.value = row.id
  try {
    const res = await inspectionApi.runTask(row.id)
    ElMessage.success(res.data.message || '巡检完成')
    await Promise.all([loadTasks(taskPage.value), loadReports(1), loadOverview()])
    if (res.data.report) {
      reportDetail.value = res.data.report
      detailVisible.value = true
    }
  } catch (error) {
    ElMessage.error(errorText(error, '巡检执行失败'))
  } finally {
    runningTaskId.value = null
  }
}

async function stopTask(row) {
  try {
    await ElMessageBox.confirm(
      `停止巡检任务「${row.name}」？停止后不再按计划自动巡检，历史报告会保留，可再次编辑启用。`,
      '停止巡检',
      { type: 'warning', confirmButtonText: '停止巡检', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await inspectionApi.stopTask(row.id)
    ElMessage.success('巡检任务已停止')
    await Promise.all([loadTasks(taskPage.value), loadOverview()])
  } catch (error) {
    ElMessage.error(errorText(error, '停止巡检任务失败'))
  }
}

async function selectAllAssets() {
  assetLoading.value = true
  try {
    const items = []
    let page = 1
    let total = 0
    do {
      const res = await assetApi.getList({ page, size: 500 })
      const batch = res.data.items || []
      items.push(...batch.map((item) => ({ id: item.id, name: item.name, ip_address: item.ip_address })))
      total = Number(res.data.total || 0)
      if (!batch.length) break
      page += 1
    } while (items.length < total && page <= 20)
    const map = new Map()
    ;[...assetOptions.value, ...items].forEach((item) => map.set(item.id, item))
    assetOptions.value = [...map.values()]
    taskForm.asset_ids = [...new Set(items.map((item) => item.id))]
    ElMessage.success(`已选择全部 ${taskForm.asset_ids.length} 台资产设备`)
  } catch (error) {
    ElMessage.error(errorText(error, '加载全部资产失败'))
  } finally {
    assetLoading.value = false
  }
}

function clearAllAssets() {
  taskForm.asset_ids = []
  ElMessage.info('已取消全部资产设备')
}

async function removeTask(row) {
  try {
    await ElMessageBox.confirm(
      `删除巡检任务「${row.name}」？历史巡检报告会保留，可在巡检报告中查看或删除。`,
      '删除巡检任务',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
    await inspectionApi.deleteTask(row.id)
    ElMessage.success('巡检任务已删除')
    await Promise.all([loadTasks(taskPage.value), loadOverview()])
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(errorText(error, '删除巡检任务失败'))
    }
  }
}

// ==================== 报告 ====================
function escapePreviewHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

async function openReportDetail(row) {
  if (!row?.id) return
  detailLoading.value = true
  detailVisible.value = true
  reportDetail.value = null
  reportPreviewHtml.value = ''
  reportPreviewLoading.value = false
  try {
    const res = await inspectionApi.report(row.id)
    reportDetail.value = res.data
  } catch (error) {
    ElMessage.error(errorText(error, '加载报告详情失败'))
    detailVisible.value = false
  } finally {
    detailLoading.value = false
  }
}

async function openReportPreview(row) {
  if (!row?.id) return
  previewReport.value = row
  previewTitle.value = row.title || 'Word 在线预览'
  try {
    const report = await inspectionApi.report(row.id)
    previewReport.value = report.data || row
    previewTitle.value = previewReport.value?.title || row.title || 'Word 在线预览'
    // 配置了 ONLYOFFICE 时优先打开可编辑 Word；未配置则回退现有只读 HTML 预览。
    try {
      const office = await inspectionApi.officeConfig(row.id)
      if (office.data?.config) {
        await openOfficeEditor(office.data)
        return
      }
    } catch (officeErrorResponse) {
      if (officeErrorResponse?.response?.status !== 400) {
        console.warn('在线 Office 配置加载失败，回退只读预览', officeErrorResponse)
      }
    }
    previewVisible.value = true
    previewLoading.value = true
    previewHtml.value = ''
    const preview = await inspectionApi.previewReport(row.id)
    previewHtml.value = preview.data?.html || '<p>报告没有可预览的文本内容。</p>'
  } catch (error) {
    previewVisible.value = true
    previewLoading.value = false
    previewHtml.value = `<p>${escapePreviewHtml(error?.response?.data?.detail || error.message || 'Word 内容预览失败')}</p>`
  } finally {
    if (previewVisible.value) previewLoading.value = false
  }
}

function loadOfficeScript(url) {
  if (window.DocsAPI) return Promise.resolve()
  if (officeScriptPromise) return officeScriptPromise
  officeScriptPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = url
    script.async = true
    script.onload = () => resolve()
    script.onerror = () => {
      officeScriptPromise = null
      reject(new Error('ONLYOFFICE api.js 加载失败'))
    }
    document.head.appendChild(script)
  })
  return officeScriptPromise
}

async function openOfficeEditor(config) {
  officeConfig.value = config
  officeTitle.value = previewTitle.value || 'Word 在线编辑'
  officeError.value = ''
  officeVisible.value = true
  officeLoading.value = true
  await nextTick()
  try {
    await loadOfficeScript(config.api_js_url)
    closeOfficeEditorInstance()
    officeEditor = new window.DocsAPI.DocEditor('inspection-office-editor', {
      ...config.config,
      width: '100%',
      height: '100%',
      events: {
        onError: (event) => {
          officeError.value = event?.data?.message || event?.data?.error || '在线 Office 编辑器加载失败'
        },
      },
    })
  } catch (error) {
    officeError.value = error?.message || '在线 Office 编辑器加载失败'
  } finally {
    officeLoading.value = false
  }
}

function closeOfficeEditorInstance() {
  if (officeEditor) {
    try {
      officeEditor.destroyEditor()
    } catch {
      /* 编辑器可能已被销毁 */
    }
    officeEditor = null
  }
}

function closeOfficeEditor() {
  closeOfficeEditorInstance()
  officeConfig.value = null
  officeError.value = ''
}

function downloadReport(row) {
  if (!row?.id) return
  downloadWithAuth(inspectionApi.downloadUrl(row.id))
}

async function removeReport(row) {
  try {
    await ElMessageBox.confirm(
      `删除巡检报告「${row.title}」？报告文件将同时删除且不可恢复。`,
      '删除巡检报告',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
    await inspectionApi.deleteReport(row.id)
    ElMessage.success('巡检报告已删除')
    if (reportDetail.value?.id === row.id) detailVisible.value = false
    await Promise.all([loadReports(reportPage.value), loadOverview()])
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(errorText(error, '删除巡检报告失败'))
    }
  }
}

// ==================== 上传 ====================
function resetUploadForm() {
  uploadForm.title = ''
  uploadForm.note = ''
  uploadForm.task_id = null
  uploadFile.value = null
  uploadFileList.value = []
  if (uploadRef.value) uploadRef.value.clearFiles()
}

async function openRetention() {
  if (!canEdit.value) {
    ElMessage.warning('没有修改巡检设置的权限')
    return
  }
  retentionDays.value = Number(overview.value?.retention_days ?? 15)
  try {
    const res = await inspectionApi.inspectionSettings()
    const data = res.data || {}
    officeSettings.enabled = !!data.office_enabled
    officeSettings.document_server_url = data.office_document_server_url || ''
    officeSettings.public_base_url = data.office_public_base_url || ''
    officeSettings.jwt_secret = ''
    officeSettings.has_secret = !!data.office_has_secret
  } catch {
    /* 保留上一次表单值 */
  }
  retentionVisible.value = true
}

async function saveRetention() {
  if (retentionDays.value === null || retentionDays.value === undefined) {
    ElMessage.warning('请填写报告保留天数')
    return
  }
  retentionSaving.value = true
  try {
    const res = await inspectionApi.updateInspectionSettings({
      retention_days: Number(retentionDays.value),
      office_enabled: officeSettings.enabled,
      office_document_server_url: officeSettings.document_server_url,
      office_public_base_url: officeSettings.public_base_url,
      ...(officeSettings.jwt_secret ? { office_jwt_secret: officeSettings.jwt_secret } : {}),
    })
    retentionVisible.value = false
    ElMessage.success(res.data?.message || '巡检设置已保存')
    await loadOverview()
  } catch (error) {
    ElMessage.error(errorText(error, '保存报告保留设置失败'))
  } finally {
    retentionSaving.value = false
  }
}

function openUpload() {
  if (!canEdit.value) {
    ElMessage.warning('没有巡检报告上传权限')
    return
  }
  resetUploadForm()
  uploadVisible.value = true
}

function validateUploadFile(file) {
  const name = String(file?.name || '').toLowerCase()
  if (name.endsWith('.doc')) {
    ElMessage.error('暂不支持旧版 .doc，请先在 Word/WPS 中另存为 .docx 后上传')
    return false
  }
  if (!name.endsWith('.docx')) {
    ElMessage.error('仅支持 .docx 格式的 Word 巡检报告')
    return false
  }
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
    ElMessage.error(`文件不能超过 ${MAX_UPLOAD_MB}MB`)
    return false
  }
  return true
}

function onUploadChange(file, fileList) {
  if (!file.raw) return
  if (!validateUploadFile(file)) {
    uploadFile.value = null
    uploadFileList.value = []
    if (uploadRef.value) uploadRef.value.clearFiles()
    return
  }
  uploadFile.value = file.raw
  uploadFileList.value = fileList.slice(-1)
}

function onUploadRemove() {
  uploadFile.value = null
  uploadFileList.value = []
}

function onUploadExceed() {
  ElMessage.warning('一次只能上传一个文件，请先移除已选文件')
}

async function submitUpload() {
  if (!uploadFile.value) {
    ElMessage.warning('请选择要上传的 .docx 文件')
    return
  }
  uploadSaving.value = true
  try {
    const formData = new FormData()
    formData.append('file', uploadFile.value, uploadFile.value.name)
    if (uploadForm.title.trim()) formData.append('title', uploadForm.title.trim())
    if (uploadForm.note.trim()) formData.append('note', uploadForm.note.trim())
    if (uploadForm.task_id) formData.append('task_id', String(uploadForm.task_id))
    const res = await inspectionApi.uploadReport(formData)
    ElMessage.success(res.data.message || '巡检报告已上传')
    uploadVisible.value = false
    await Promise.all([loadReports(1), loadOverview()])
  } catch (error) {
    ElMessage.error(errorText(error, '上传巡检报告失败'))
  } finally {
    uploadSaving.value = false
  }
}

// ==================== 展示辅助 ====================
function errorText(error, fallback) {
  return error?.response?.data?.detail || error?.message || fallback
}

function targetSummary(row) {
  const parts = []
  if (row.asset_count) parts.push(`资产库 ${row.asset_count} 台`)
  if (row.custom_count) parts.push(`自定义 ${row.custom_count} 台`)
  return parts.length ? parts.join(' + ') : '未配置巡检对象'
}

function statusMeta(status) {
  return {
    idle: { type: 'info', text: '未执行' },
    running: { type: 'warning', text: '执行中' },
    success: { type: 'success', text: '成功' },
    failed: { type: 'danger', text: '失败' },
  }[status] || { type: 'info', text: '未执行' }
}

function onlineMeta(row) {
  if (!row.managed) return { type: 'info', text: '未纳管' }
  if (row.online === true) return { type: 'success', text: '在线' }
  if (row.online === false) return { type: 'danger', text: '离线' }
  return { type: 'info', text: '未知' }
}

function issueTagType(level) {
  return { critical: 'danger', warning: 'warning', info: 'info' }[level] || 'info'
}

function alertLevelColor(level) {
  return {
    info: '#2563eb',
    warning: '#d97706',
    critical: '#dc2626',
    emergency: '#b91c1c',
  }[level] || '#475569'
}

function alertTagType(level) {
  return { critical: 'danger', emergency: 'danger', warning: 'warning', info: 'info' }[level] || 'info'
}

function percentText(value) {
  if (value === null || value === undefined || value === '') return '-'
  const number = Number(value)
  return Number.isFinite(number) ? `${number.toFixed(1)}%` : '-'
}

function tempText(value) {
  if (value === null || value === undefined || value === '') return '-'
  const number = Number(value)
  return Number.isFinite(number) ? `${number.toFixed(1)}°C` : '-'
}

function powerText(value) {
  return { normal: '正常', failure: '故障' }[value] || '未采集'
}

function fileSize(bytes) {
  const size = Number(bytes) || 0
  if (size <= 0) return '-'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

onMounted(() => {
  loadCredentialAssets()
  updateViewportWidth()
  window.addEventListener('resize', updateViewportWidth, { passive: true })
  loadAll()
})

onBeforeUnmount(() => {
  closeOfficeEditorInstance()
  if (commandPreviewTimer) clearTimeout(commandPreviewTimer)
  window.removeEventListener('resize', updateViewportWidth)
})
</script>

<style scoped>
.inspection-view {
  width: 100%;
  max-width: 100%;
  min-width: 0;
  box-sizing: border-box;
  padding: 16px;
  background: #f5f7fa;
  min-height: 100%;
}

.inspection-view :deep(.el-card),
.inspection-view :deep(.el-card__body) {
  width: 100%;
  max-width: 100%;
  min-width: 0;
  box-sizing: border-box;
}

.ins-task-table,
.ins-task-table :deep(.el-table__inner-wrapper),
.ins-task-table :deep(.el-table__body-wrapper) {
  width: 100%;
  max-width: 100%;
}

.ins-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
}

.ins-title {
  color: #1f3345;
  font-size: 18px;
  font-weight: 700;
}

.ins-sub {
  margin-top: 5px;
  color: #8496a7;
  font-size: 12px;
}

.ins-head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.ins-alert {
  margin-bottom: 14px;
}

.ins-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}

.ins-stats > div {
  padding: 11px 14px;
  border: 1px solid #e5edf4;
  border-radius: 7px;
  background: #f8fbfe;
}

.ins-stats span {
  display: block;
  color: #8b9bab;
  font-size: 10px;
}

.ins-stats b {
  display: block;
  margin-top: 3px;
  color: #214667;
  font-size: 18px;
}

.ins-stats b.ok {
  color: #1b9b6a;
}

.ins-stats b.danger {
  color: #d9485f;
}

.ins-toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.ins-toolbar-right {
  margin-left: auto;
  display: flex;
  gap: 6px;
}

.task-name {
  color: #29445c;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-meta {
  margin-top: 3px;
  color: #8b9bab;
  font-size: 11px;
  line-height: 1.4;
}

.task-meta.ellipsis {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 160px;
}

.target-summary {
  color: #33495b;
  font-size: 12px;
}

.ins-pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

.task-form :deep(.el-form-item) {
  margin-bottom: 16px;
}

.form-help {
  margin-top: 4px;
  color: #8b9bab;
  font-size: 11px;
  line-height: 1.5;
}

.custom-device-box {
  width: 100%;
}

.custom-add-btn {
  margin-top: 8px;
}

.schedule-box {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.schedule-box .form-help {
  flex-basis: 100%;
}

.schedule-label {
  color: #526b80;
  font-size: 12px;
}

.ins-detail-body {
  min-height: 120px;
}

.detail-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.detail-title {
  color: #1f3345;
  font-size: 16px;
  font-weight: 700;
}

.detail-head-tags {
  display: flex;
  gap: 6px;
  align-items: center;
}

.detail-desc {
  margin-bottom: 14px;
}

.detail-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}

.detail-stats > div {
  padding: 9px 12px;
  border: 1px solid #e5edf4;
  border-radius: 7px;
  background: #f8fbfe;
}

.detail-stats span {
  display: block;
  color: #8b9bab;
  font-size: 10px;
}

.detail-stats b {
  display: block;
  margin-top: 3px;
  color: #214667;
  font-size: 17px;
}

.detail-stats b.ok {
  color: #1b9b6a;
}

.detail-stats b.danger {
  color: #d9485f;
}

.detail-section-title {
  margin: 14px 0 6px;
  color: #29445c;
  font-size: 13px;
}

.detail-paragraph {
  margin: 0 0 10px;
  color: #4c6276;
  font-size: 12px;
  line-height: 1.7;
}

.detail-list {
  margin: 0 0 10px;
  padding-left: 22px;
  color: #4c6276;
  font-size: 12px;
  line-height: 1.8;
}

.device-expand {
  padding: 8px 14px;
  color: #4c6276;
  font-size: 12px;
  line-height: 1.7;
}

.expand-line {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin: 4px 0;
}

.expand-alerts {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #e4edf4;
}

.ok-text {
  color: #1b9b6a;
}

@media (max-width: 1199px) {
  .ins-toolbar > .el-input,
  .ins-toolbar > .el-select {
    width: 100% !important;
    max-width: 100%;
  }

  .ins-head-actions {
    width: 100%;
  }

  .ins-toolbar-right {
    width: 100%;
    margin-left: 0;
    justify-content: flex-start;
  }

  .ins-pager {
    justify-content: center;
  }
}

@media (max-width: 760px) {
  .inspection-view {
    padding: 10px;
  }

  .ins-stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .ins-head-actions {
    gap: 6px;
  }

  .preview-dialog-body { min-height: 300px; }
.office-editor-bar { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 8px; color: #60788a; font-size: 11px; }
.office-editor-bar .muted { color: #9aabba; }
.office-editor-wrap { min-height: 70vh; }
.office-editor-host { width: 100%; height: 70vh; }
.report-preview-word {
    padding: 10px;
  }
}


.asset-select-help {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.asset-select-actions {
  display: inline-flex;
  gap: 8px;
  flex: 0 0 auto;
}
.report-preview-word {
  min-height: 160px;
  max-height: 480px;
  overflow: auto;
  padding: 16px 18px;
  border: 1px solid #e3ebf2;
  border-radius: 8px;
  background: #fff;
  color: #334155;
  line-height: 1.75;
  font-size: 12px;
}
.report-preview-word h3 {
  margin: 14px 0 8px;
  color: #1e3a4f;
  font-size: 14px;
}
.report-preview-word p { margin: 6px 0; }
.report-preview-word table {
  width: 100%;
  margin: 10px 0;
  border-collapse: collapse;
  font-size: 11px;
}
.report-preview-word td {
  padding: 5px 7px;
  border: 1px solid #e2e8f0;
  vertical-align: top;
}
.report-preview-word tr:first-child td {
  background: #f8fafc;
  font-weight: 600;
}



.alert-detail-line {
  align-items: flex-start;
}
.alert-detail-text {
  font-weight: 700;
  line-height: 1.6;
  overflow-wrap: anywhere;
}


.command-option-box { width: 100%; }
.inspection-credential-tip { margin-bottom: 8px; }
.credential-miss-alert { margin-top: 8px; }
.credential-miss-list { margin: 5px 0; color: #8a5a18; font-size: 12px; line-height: 1.6; }
.command-preview-list { margin-top: 8px; display: flex; flex-direction: column; gap: 6px; }
.command-preview-group { border: 1px solid #e4edf4; border-radius: 6px; padding: 7px 9px; background: #f8fbfd; }
.command-preview-title { display: flex; justify-content: space-between; gap: 12px; color: #334155; font-size: 12px; }
.command-preview-title span { color: #7b91a3; }
.command-preview-commands { margin-top: 4px; display: flex; flex-direction: column; gap: 2px; color: #536b7c; font-size: 11px; line-height: 1.6; }
.command-preview-commands code { color: #0f6fae; background: #eef7fd; padding: 0 3px; border-radius: 3px; }

.command-unmatched { margin-top: 6px; color: #b45309; font-size: 12px; line-height: 1.6; }
</style>
