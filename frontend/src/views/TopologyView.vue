<template>
  <div
    ref="viewRef"
    class="topology-view"
    :class="{ 'is-fullscreen-edit': fullscreenActive && editMode, 'is-pseudo-fullscreen': pseudoFullscreen }"
  >
    <el-card>
      <template #header>
        <div class="card-header">
          <div class="title">
            <span>{{ t('topology.title') }}</span>
            <el-tag size="small" type="info" effect="plain">{{ t('topology.deviceCount', { count: nodeCount }) }}</el-tag>
            <el-tag size="small" type="info" effect="plain">{{ t('topology.linkCount', { count: edgeCount }) }}</el-tag>
            <el-tag v-if="cloudNodes.length" size="small" type="info" effect="plain">云出口 {{ cloudNodes.length }}</el-tag>
            <el-tag size="small" type="success" effect="plain">
              {{ t('topology.realtimeTotalTraffic', { value: fmtBps(totalBps) }) }}
            </el-tag>
            <span class="updated" v-if="updatedAt">{{ t('topology.updatedAt', { time: formatHMS(updatedAt) }) }}</span>
          </div>
          <div class="actions">
            <el-button v-if="!sharedResource || sharedResource.is_owner" size="small" @click="shareVisible = true">
              <el-icon><Share /></el-icon>分享
            </el-button>
            <el-button size="small" @click="sharedWithMeVisible = true">
              <el-icon><FolderOpened /></el-icon>共享给我
            </el-button>
            <el-button
              v-if="sharedResource && !sharedResource.can_edit"
              size="small"
              type="primary"
              plain
              @click="requestSharedEdit"
            >申请编辑</el-button>
            <el-tag v-if="sharedResource" size="small" :type="sharedResource.can_edit ? 'success' : 'info'" effect="plain">
              共享{{ sharedResource.can_edit ? '可编辑' : '只读' }}
            </el-tag>
            <el-radio-group v-model="mode" size="small" @change="applyMode">
              <el-radio-button value="view">{{ t('topology.view') }}</el-radio-button>
              <el-radio-button value="edit" :disabled="!canEdit">{{ t('topology.edit') }}</el-radio-button>
            </el-radio-group>
            <el-button
              v-if="canEdit && !fullscreenActive"
              size="small"
              type="primary"
              plain
              class="topo-fullscreen-edit-btn"
              @click="enterEditFullscreen"
            >
              <el-icon><FullScreen /></el-icon>满屏编辑
            </el-button>
            <el-switch
              v-model="showTraffic"
              inline-prompt
              :active-text="t('topology.rate')"
              :inactive-text="t('topology.hide')"
              @change="applyTrafficVisibility"
            />
            <el-tooltip :content="t('topology.autoRefreshHint')" placement="bottom">
              <div class="topo-auto-refresh">
                <el-switch v-model="autoRefresh" size="small" />
                <span>{{ autoRefresh ? t('topology.auto') : t('topology.manual') }}</span>
              </div>
            </el-tooltip>
            <el-button size="small" @click="toggleFullscreen">
              <el-icon><Close v-if="fullscreenActive" /><FullScreen v-else /></el-icon>
              {{ fullscreenActive
                ? (editMode ? '退出满屏编辑' : t('topology.exitFullscreen'))
                : t('topology.fullscreen') }}
            </el-button>
            <el-button size="small" @click="fitView">
              <el-icon><FullScreen /></el-icon>{{ t('topology.fitCanvas') }}
            </el-button>
            <el-button size="small" @click="loadTopology(true)" :loading="loading">
              <el-icon><Refresh /></el-icon>{{ t('common.refresh') }}
            </el-button>
            <template v-if="editMode">
            <el-radio-group v-model="editTool" size="small" class="topo-edit-tool" @change="applyEditTool">
              <el-radio-button value="move">移动布局</el-radio-button>
              <el-radio-button value="connect">拖拽连线</el-radio-button>
            </el-radio-group>
            <div class="topo-size-control">
              <span class="size-control-label device-size-color">设备大小</span>
              <el-input-number
                v-model="nodeSizePercent"
                class="device-size-field"
                size="small"
                :min="70"
                :max="200"
                :step="5"
                controls-position="right"
                :disabled="!sizeNodeIds.length"
                @change="applyNodeSize"
              />
              <span>%</span>
              <span class="size-control-divider"></span>
              <span class="size-control-label flow-label-color">标签大小</span>
              <el-input-number
                v-model="flowLabelPercent"
                class="flow-label-field"
                size="small"
                :min="60"
                :max="200"
                :step="10"
                :precision="0"
                controls-position="right"
                @change="applyFlowLabelScale"
              />
              <span>%</span>
              <el-button size="small" :disabled="!sizeNodeIds.length" @click="applyNodeSize">应用</el-button>
              <el-button size="small" @click="selectAllSizeNodes">全选</el-button>
              <el-button size="small" :disabled="!sizeNodeIds.length" @click="clearSizeSelection">清空</el-button>
              <el-button
                v-if="canEditAssets"
                size="small"
                type="danger"
                plain
                :disabled="!sizeNodeIds.length"
                @click="deleteSelectedDevices"
              >删除选中</el-button>
              <span class="topo-size-tip">
                {{ sizeNodeIds.length ? `已选中 ${sizeNodeIds.length} 台设备` : '移动布局下点选设备，Ctrl 多选；全选后拖动任一选中设备可整组移动' }}
              </span>
            </div>
            <el-button v-if="canEditAssets" type="primary" size="small" @click="openCreateDevice">
              <el-icon><Plus /></el-icon>新增设备
            </el-button>
            <el-button size="small" @click="addCloudNode">
              <el-icon><Plus /></el-icon>添加云出口
            </el-button>
            <el-button size="small" @click="openAddConnection">
              <el-icon><Plus /></el-icon>{{ t('topology.addConnection') }}
            </el-button>
            <el-button type="success" size="small" @click="autoDiscover" :loading="discovering">
              <el-icon><Search /></el-icon>{{ t('topology.autoDiscoverLldp') }}
            </el-button>
            <el-button
              type="primary"
              size="small"
              :loading="savingLayout"
              @click="saveLayout"
            >
              <el-icon><Check /></el-icon>{{ t('topology.saveLayout') }}
            </el-button>
            <el-button
              size="small"
              :disabled="!dirty || savingLayout || discardingLayout"
              :loading="discardingLayout"
              @click="discardLayoutChanges"
            >
              <el-icon><RefreshLeft /></el-icon>取消更改
            </el-button>
            <el-button size="small" :loading="savingLayout" @click="resetLayout">
              <el-icon><RefreshLeft /></el-icon>{{ t('topology.resetLayout') }}
            </el-button>
          </template>
          </div>
        </div>
      </template>

      <el-alert
        v-if="nodeCount === 0 && !cloudNodes.length"
        :title="t('topology.noDevicesHint')"
        type="info"
        :closable="false"
        show-icon
      />

      <el-alert
        v-if="editMode"
        type="warning"
        :closable="false"
        show-icon
        class="edit-hint"
        :title="editTool === 'connect'
          ? '拖拽连线模式：按住源设备拖到目标设备，松开后自动吸附并弹出两端接口选择；双击连线可删除（需二次确认）；「添加云出口」可创建不关联资产的虚拟节点，拖到真实设备可建出口链路；切换「移动布局」可拖动节点。'
          : '移动布局模式：拖动节点调整位置，拖动选中设备可整组移动；双击连线不会删除，删除连线请使用链路详情中的「删除连线」按钮。「添加云出口」可创建虚拟云节点，选中后可添加出口链路或删除云节点。全选或 Ctrl 多选后，拖动任一选中设备可整组移动；智能布线会自动选择面向对端的锚点和最短路径，拖拽连线时实时推荐最近设备与最佳锚点。拖动已有连线的任意端点可重新吸附到其他设备，画布会自动展开所有设备锚点；按住线身可微调路径，拖动上传/下载标签组可沿当前连线移动并以「标签」调整字号，调整后点击「保存布局」。'"
      />

      <div
        v-if="largeMode || statusFilter !== 'all' || typeFilter !== 'all' || locationFilter !== 'all' || keywordFilter"
        class="topo-scale-filterbar"
      >
        <span class="scale-badge">大规模拓扑 · {{ allNodes.length }} 台</span>
        <el-select v-model="statusFilter" size="small" style="width: 108px">
          <el-option label="全部状态" value="all" />
          <el-option label="在线" value="online" />
          <el-option label="告警" value="warning" />
          <el-option label="离线" value="offline" />
          <el-option label="未知" value="unknown" />
        </el-select>
        <el-select v-model="typeFilter" size="small" style="width: 120px">
          <el-option label="全部类型" value="all" />
          <el-option v-for="item in typeFilterOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
        <el-select v-model="locationFilter" size="small" style="width: 150px">
          <el-option label="全部位置" value="all" />
          <el-option v-for="item in locationFilterOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
        <el-input v-model="keywordFilter" size="small" clearable placeholder="搜索名称 / IP / 厂商" style="width: 190px" />
        <el-button size="small" @click="resetScaleFilters">重置</el-button>
        <span class="scale-filtered">筛选后 {{ filteredNodes.length }} 台</span>
      </div>

      <div class="topology-stage">
        <div ref="containerRef" class="topology-container"></div>

        <div v-if="largeOverview" class="topo-scale-overview">
          <div class="topo-scale-overview-head">
            <div>
              <strong>大规模拓扑总览</strong>
              <span>默认按分组聚合，点击分组查看设备；筛选条件：{{ filteredNodes.length }} 台</span>
            </div>
            <el-radio-group :model-value="scaleGroupMode" size="small" @change="changeScaleGroupMode">
              <el-radio-button value="type">按设备类型</el-radio-button>
              <el-radio-button value="location">按机房位置</el-radio-button>
            </el-radio-group>
          </div>
          <div class="topo-scale-grid">
            <button
              v-for="group in scaleGroups"
              :key="group.key"
              type="button"
              class="topo-scale-card"
              :style="{ '--group-color': group.color }"
              @click="openScaleGroup(group)"
            >
              <span class="scale-card-dot"></span>
              <strong>{{ group.label }}</strong>
              <b>{{ group.count }} 台</b>
              <small>
                <span class="online">{{ group.online }} 在线</span>
                <span class="warning">{{ group.warning }} 告警</span>
                <span class="offline">{{ group.offline }} 离线</span>
              </small>
            </button>
            <div v-if="!scaleGroups.length" class="topo-scale-empty">当前筛选条件下没有设备</div>
          </div>
        </div>

        <div v-else-if="activeScaleGroup" class="topo-scale-back">
          <el-button size="small" @click="closeScaleGroup">← 返回分组总览</el-button>
          <span>
            {{ activeScaleGroupInfo?.label || '当前分组' }}
            · {{ activeScaleGroupInfo?.count ?? filteredNodes.length }} 台
            <template v-if="scaleTruncated">（为避免卡顿仅显示前 {{ maxGroupNodes }} 台，请继续筛选）</template>
          </span>
        </div>

        <div class="topo-search">
          <el-select
            v-model="locateNodeId"
            filterable
            clearable
            size="small"
            placeholder="搜索设备，快速定位"
            class="topo-search-select"
            @change="locateNode"
          >
            <el-option
              v-for="node in nodeOptions"
              :key="node.id"
              :label="`${node.label} · ${node.ip_address}`"
              :value="node.device_id"
            />
          </el-select>
        </div>

        <div
          v-if="connectSuggestion"
          class="topo-connect-suggestion"
          :class="{ active: connectSuggestion.active }"
          :style="{ left: `${connectSuggestion.left}px`, top: `${connectSuggestion.top}px` }"
        >
          <span class="suggestion-kicker">{{ connectSuggestion.kicker }}</span>
          <strong>{{ connectSuggestion.title }}</strong>
          <small>{{ connectSuggestion.detail }}</small>
        </div>

        <div class="topo-zoom">
          <el-button circle size="small" title="放大" @click="zoomBy(0.12)">
            <el-icon><Plus /></el-icon>
          </el-button>
          <el-button circle size="small" title="缩小" @click="zoomBy(-0.12)">
            <el-icon><Minus /></el-icon>
          </el-button>
          <el-button circle size="small" title="适应画布" @click="fitView">
            <el-icon><Aim /></el-icon>
          </el-button>
        </div>

        <div v-if="selectedNode" class="topo-node-panel">
          <div class="topo-node-head">
            <div class="topo-node-title">
              <i :style="{ background: selectedNode.is_cloud ? '#0ea5e9' : (STATUS_COLORS[selectedNode.status] || '#94a3b8') }"></i>
              <div>
                <strong>{{ selectedNode.label }}</strong>
                <span v-if="selectedNode.is_cloud">拓扑虚拟节点 · 无资产记录</span>
                <span v-else>{{ selectedNode.ip_address || '未配置地址' }}</span>
              </div>
            </div>
            <el-button link @click="closeNodePanel"><el-icon><Close /></el-icon></el-button>
          </div>
          <template v-if="selectedNode.is_cloud">
            <div class="topo-node-meta">
              <div><span>节点类型</span><b>{{ deviceTypeLabel('cloud') }}</b></div>
              <div><span>性质</span><b>拓扑虚拟节点</b></div>
              <div><span>出口链路</span><b>{{ nodeLinkCount(selectedNode.id) }} 条</b></div>
              <div><span>资产 / 采集</span><b>未关联</b></div>
            </div>
            <div class="topo-node-actions">
              <el-button v-if="editMode" size="small" @click="renameCloudNode(selectedNode)">
                <el-icon><Edit /></el-icon>重命名
              </el-button>
              <el-button v-if="editMode" type="primary" size="small" plain @click="openCloudLinkDialog(selectedNode)">
                <el-icon><Plus /></el-icon>添加出口链路
              </el-button>
              <el-button size="small" @click="focusOnNode(selectedNode.id)">
                <el-icon><Aim /></el-icon>定位
              </el-button>
              <el-button v-if="editMode" size="small" type="danger" plain @click="deleteCloudNode(selectedNode)">
                <el-icon><Delete /></el-icon>删除云节点
              </el-button>
            </div>
            <div v-if="!editMode" class="edge-tip">切换到编辑模式后可添加出口链路或删除云节点</div>
          </template>
          <template v-else>
            <div class="topo-node-meta">
              <div><span>设备类型</span><b>{{ deviceTypeLabel(selectedNode.device_type) }}</b></div>
              <div><span>状态</span><b :style="{ color: STATUS_COLORS[selectedNode.status] || '#94a3b8' }">
                {{ STATUS_TEXT[selectedNode.status] || selectedNode.status || '未知' }}
              </b></div>
              <div><span>厂商</span><b>{{ selectedNode.vendor || '-' }}</b></div>
              <div><span>关联链路</span><b>{{ nodeLinkCount(selectedNode.id) }} 条</b></div>
            </div>
            <div class="topo-node-actions">
              <el-button type="primary" size="small" plain @click="openNodeDevice(selectedNode)">
                <el-icon><Monitor /></el-icon>设备详情
              </el-button>
              <el-button size="small" @click="focusOnNode(selectedNode.id)">
                <el-icon><Aim /></el-icon>定位
              </el-button>
              <el-button v-if="canEditAssets" size="small" @click="openNodeIconPicker(selectedNode)">
                <el-icon><Picture /></el-icon>图标
              </el-button>
              <el-button v-if="canEditAssets" size="small" @click="openEditDevice(selectedNode)">
                <el-icon><Edit /></el-icon>编辑
              </el-button>
              <el-button v-if="canEditAssets" size="small" type="danger" plain @click="deleteDevice(selectedNode)">
                <el-icon><Delete /></el-icon>删除
              </el-button>
            </div>
          </template>
        </div>
      </div>

      <!-- 链路详情（点击连线） -->
      <div v-if="selectedEdge" class="edge-panel">
        <div class="edge-head">
          <span>{{ selectedEdge.is_cloud_link ? '云出口链路' : t('topology.linkDetails') }}</span>
          <el-button link @click="selectedEdge = null"><el-icon><Close /></el-icon></el-button>
        </div>
        <template v-if="selectedEdge.is_cloud_link">
          <div class="edge-row">
            <span class="k">云节点</span>
            <span class="v">{{ cloudLinkCloudEndpoint(selectedEdge)?.label || '互联网出口' }}</span>
          </div>
          <div class="edge-row">
            <span class="k">真实设备</span>
            <span class="v">{{ cloudLinkDeviceEndpoint(selectedEdge)?.label || '-' }}</span>
          </div>
          <div class="edge-row">
            <span class="k">出口接口</span>
            <span class="v">{{ cloudLinkInterface(selectedEdge) || '-' }}</span>
          </div>
          <div class="edge-row">
            <span class="k">链路类型</span>
            <span class="v">拓扑虚拟链路（不写入设备连接）</span>
          </div>
        </template>
        <template v-else>
          <div class="edge-row">
            <span class="k">{{ t('topology.sourceInterface') }}</span>
            <span class="v">{{ selectedEdge.source_interface || '-' }}</span>
          </div>
          <div class="edge-row">
            <span class="k">{{ t('topology.targetInterfaceLabel') }}</span>
            <span class="v">{{ selectedEdge.target_interface || '-' }}</span>
          </div>
          <div class="edge-row">
            <span class="k">{{ t('topology.realtimeRate') }}</span>
            <span class="v">
              <span class="flow-upload">↑ {{ fmtBps(selectedEdgeFlow.upload) }} 上传</span>
              <span class="flow-download">↓ {{ fmtBps(selectedEdgeFlow.download) }} 下载</span>
            </span>
          </div>
          <div class="edge-row">
            <span class="k">{{ t('topology.linkBandwidth') }}</span>
            <span class="v">{{ fmtBps(selectedEdge.capacity_bps) }}</span>
          </div>
          <div class="edge-row">
            <span class="k">{{ t('topology.utilization') }}</span>
            <span class="v">
              {{ selectedEdge.utilization === null || selectedEdge.utilization === undefined
                ? '-' : selectedEdge.utilization + '%' }}
            </span>
          </div>
          <div class="edge-row">
            <span class="k">{{ t('topology.linkStatus') }}</span>
            <el-tag :type="selectedEdge.oper_up === false ? 'danger' : 'success'" size="small">
              {{ selectedEdge.oper_up === false ? t('topology.disconnected') : t('topology.normal') }}
            </el-tag>
          </div>
        </template>
        <el-button
          v-if="editMode && !selectedEdge.is_cloud_link && selectedEdge.edge_offset"
          size="small"
          plain
          class="edge-reset-btn"
          @click="resetEdgeOffset"
        >恢复自动路径</el-button>
        <el-button
          v-if="editMode"
          type="danger"
          plain
          size="small"
          class="edge-delete-btn"
          @click="deleteSelectedEdge"
        >
          <el-icon><Delete /></el-icon>{{ selectedEdge.is_cloud_link ? '删除出口链路' : '删除连线' }}
        </el-button>
        <div class="edge-tip">{{ selectedEdge.is_cloud_link ? '云出口链路由拓扑布局保存；点击「保存布局」持久化' : edgeDeleteHint }}</div>
        <div v-if="editMode && !selectedEdge.is_cloud_link" class="edge-tip">按住连线拖动可微调路径；拖动上传/下载标签组可沿当前连线移动并以「标签」调整字号，调整后点击「保存布局」持久化</div>
      </div>

      <div class="legend">
        <span
          v-for="item in topologyLegend"
          :key="item.type"
          class="legend-group"
          :title="`${item.label} × ${item.count}`"
        >
          <i class="ic" v-html="legendIcon(item.type)"></i>{{ item.label }}
          <b class="legend-count">{{ item.count }}</b>
        </span>
        <span v-if="!topologyLegend.length" class="legend-tip">{{ t('topology.noDevicesHint') }}</span>
        <span class="legend-sep"></span>
        <span class="legend-group"><i class="dot" style="background:#22c55e"></i>{{ t('topology.online') }}</span>
        <span class="legend-group"><i class="dot" style="background:#f59e0b"></i>{{ t('topology.alert') }}</span>
        <span class="legend-group"><i class="dot" style="background:#ef4444"></i>{{ t('topology.offline') }}</span>
        <span class="legend-sep"></span>
        <span class="legend-group"><i class="line low"></i>&lt;50%</span>
        <span class="legend-group"><i class="line mid"></i>50-80%</span>
        <span class="legend-group"><i class="line high"></i>&ge;80%</span>
        <span class="legend-tip">
          {{ editMode ? modeShortHint : t('topology.viewModeShort') }}
        </span>
      </div>
    </el-card>

    <!-- 添加连接 -->
    <el-dialog v-model="dialogVisible" :title="t('topology.addDeviceLink')" width="560px">
      <el-form label-width="100px">
        <el-form-item :label="t('topology.sourceDevice')">
          <el-select
            v-model="form.source_device_id"
            filterable
            :placeholder="t('topology.selectSourceDevice')"
            style="width: 100%"
            @change="onSourceDeviceChange"
          >
            <el-option
              v-for="d in nodeOptions"
              :key="d.device_id"
              :label="`${d.label} (${d.ip_address})`"
              :value="d.device_id"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('topology.sourceInterface')">
          <el-select
            v-model="form.source_interface"
            filterable
            allow-create
            clearable
            default-first-option
            :reserve-keyword="false"
            :loading="sourceIfLoading"
            :disabled="!form.source_device_id"
            :placeholder="t('topology.interfacePlaceholder')"
            style="width: 100%"
          >
            <el-option
              v-for="item in sourceInterfaces"
              :key="item.name"
              :label="interfaceOptionLabel(item)"
              :value="item.name"
            />
          </el-select>
          <div v-if="noSourceInterfaces" class="if-hint">{{ t('topology.noInterfacesHint') }}</div>
        </el-form-item>
        <el-form-item :label="t('topology.targetDevice')">
          <el-select
            v-model="form.dest_device_id"
            filterable
            :placeholder="t('topology.selectTargetDevice')"
            style="width: 100%"
            @change="onDestDeviceChange"
          >
            <el-option
              v-for="d in nodeOptions"
              :key="d.device_id"
              :label="`${d.label} (${d.ip_address})`"
              :value="d.device_id"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('topology.targetInterface')">
          <el-select
            v-model="form.dest_interface"
            filterable
            allow-create
            clearable
            default-first-option
            :reserve-keyword="false"
            :loading="destIfLoading"
            :disabled="!form.dest_device_id"
            :placeholder="t('topology.interfacePlaceholder2')"
            style="width: 100%"
          >
            <el-option
              v-for="item in destInterfaces"
              :key="item.name"
              :label="interfaceOptionLabel(item)"
              :value="item.name"
            />
          </el-select>
          <div v-if="noDestInterfaces" class="if-hint">{{ t('topology.noInterfacesHint') }}</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" @click="submitConnection">{{ t('topology.confirmAdd') }}</el-button>
      </template>
    </el-dialog>

    <!-- 添加云出口链路（拓扑虚拟节点 ↔ 真实设备） -->
    <el-dialog v-model="cloudLinkDialogVisible" title="添加云出口链路" width="560px">
      <el-form label-width="100px">
        <el-form-item label="云节点">
          <el-input :model-value="cloudLinkForm.cloud_label" disabled />
        </el-form-item>
        <el-form-item label="出口设备" required>
          <el-select
            v-model="cloudLinkForm.device_id"
            filterable
            clearable
            placeholder="选择真实设备"
            style="width: 100%"
            @change="onCloudLinkDeviceChange"
          >
            <el-option
              v-for="device in nodeOptions"
              :key="device.device_id"
              :label="`${device.label} (${device.ip_address})`"
              :value="device.device_id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="出口接口">
          <el-select
            v-model="cloudLinkForm.interface"
            filterable
            allow-create
            clearable
            default-first-option
            :reserve-keyword="false"
            :loading="cloudLinkIfLoading"
            :disabled="!cloudLinkForm.device_id"
            placeholder="选择或输入出口接口"
            style="width: 100%"
          >
            <el-option
              v-for="item in cloudLinkInterfaces"
              :key="item.name"
              :label="interfaceOptionLabel(item)"
              :value="item.name"
            />
          </el-select>
          <div class="if-hint">接口可留空；链路只写入拓扑布局，不写入设备连接表</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="cloudLinkDialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" @click="submitCloudLink">保存出口链路</el-button>
      </template>
    </el-dialog>

    <!-- 拓扑内新增/编辑设备 -->
    <el-dialog
      v-model="deviceDialogVisible"
      :title="editingDeviceId ? '编辑设备' : '从现有资产新增设备'"
      width="620px"
      :close-on-click-modal="false"
    >
      <el-form v-if="editingDeviceId" :model="deviceForm" label-width="96px" class="device-form">
        <el-row :gutter="14">
          <el-col :span="12">
            <el-form-item label="设备名称" required>
              <el-input v-model="deviceForm.name" placeholder="设备名称" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="IP 地址" required>
              <el-input v-model="deviceForm.ip_address" placeholder="192.168.1.1" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="设备类型" required>
              <el-select v-model="deviceForm.device_type" style="width:100%">
                <el-option
                  v-for="item in DEVICE_TYPES"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="厂商">
              <el-input v-model="deviceForm.vendor" placeholder="Huawei / Cisco / ..." />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="型号">
              <el-input v-model="deviceForm.model" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="设备位置">
              <el-input v-model="deviceForm.location" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="SNMP 版本">
              <el-select v-model="deviceForm.snmp_version" style="width:100%">
                <el-option label="v1" value="v1" />
                <el-option label="v2c" value="v2c" />
                <el-option label="v3" value="v3" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="团体名">
              <el-input v-model="deviceForm.community" show-password />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="端口">
              <el-input-number v-model="deviceForm.port" :min="1" :max="65535" controls-position="right" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="启用监控">
              <el-switch v-model="deviceForm.is_enabled" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <div v-else class="topo-asset-picker">
        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="从资产库选择已有设备，不再在拓扑页重复创建设备"
          description="资产库中的全部资产会自动同步到拓扑，未启用资产以灰色显示；可在此直接定位。"
          class="asset-picker-alert"
        />
        <el-form label-width="96px" class="asset-picker-form">
          <el-form-item label="选择资产" required>
            <el-select
              v-model="selectedAssetId"
              filterable
              clearable
              :loading="assetOptionsLoading"
              placeholder="搜索资产名称或 IP 地址"
              style="width:100%"
              @change="onAssetSelected"
            >
              <el-option
                v-for="asset in assetOptions"
                :key="asset.id"
                :label="`${asset.name} · ${asset.ip_address}`"
                :value="asset.id"
              >
                <span class="asset-option-name">{{ asset.name }}</span>
                <span class="asset-option-ip">{{ asset.ip_address }}</span>
                <span v-if="nodes.some((node) => node.device_id === asset.id)" class="asset-option-tag">已在拓扑</span>
                <span v-else-if="asset.is_enabled === false" class="asset-option-tag disabled">未启用</span>
              </el-option>
            </el-select>
          </el-form-item>
        </el-form>
        <div v-if="selectedAsset" class="asset-preview">
          <div class="asset-preview-icon">
            <img v-if="newDeviceIcon || selectedAsset.icon" :src="newDeviceIcon || selectedAsset.icon" alt="icon" />
            <div v-else v-html="iconSvg(selectedAsset.device_type, 'unknown', 42)"></div>
          </div>
          <div class="asset-preview-main">
            <div class="asset-preview-title">
              <strong>{{ selectedAsset.name }}</strong>
              <el-tag v-if="selectedAssetInTopology" size="small" type="success" effect="plain">已在拓扑中</el-tag>
              <el-tag v-else-if="selectedAsset.is_enabled === false" size="small" type="warning" effect="plain">未启用监控</el-tag>
            </div>
            <span>{{ selectedAsset.ip_address }} · {{ deviceTypeLabel(selectedAsset.device_type) }} · {{ selectedAsset.vendor || '未填写厂商' }}</span>
            <span v-if="selectedAssetInTopology" class="asset-preview-hint">该资产已经在拓扑图中，选择后将直接定位，不会重复创建。</span>
            <span v-else class="asset-preview-hint">将使用该资产加入拓扑，可重新定义节点图标。</span>
          </div>
          <el-button size="small" @click="newIconPickerVisible = true">
            <el-icon><Picture /></el-icon>定义图标
          </el-button>
        </div>
        <el-empty v-else description="请选择一个现有资产" :image-size="52" />
      </div>
      <template #footer>
        <el-button @click="deviceDialogVisible = false">取消</el-button>
        <el-button v-if="editingDeviceId" type="primary" :loading="deviceSaving" @click="saveDevice">保存</el-button>
        <el-button v-else type="primary" :loading="deviceSaving" :disabled="!selectedAsset" @click="addExistingAsset">
          {{ selectedAssetInTopology ? '定位到拓扑' : '添加到拓扑' }}
        </el-button>
      </template>
    </el-dialog>

    <IconPickerDialog
      v-model="newIconPickerVisible"
      :device-type="selectedAsset?.device_type || 'other'"
      :current-icon="newDeviceIcon || selectedAsset?.icon || ''"
      @select="applyNewDeviceIcon"
    />

    <IconPickerDialog
      v-model="iconPickerVisible"
      :device-type="iconPickerDevice?.device_type || 'other'"
      :current-icon="iconPickerDevice?.icon || ''"
      @select="applyNodeIcon"
    />

    <ResourceShareDialog
      v-model="shareVisible"
      resource-type="topology"
      resource-key="global"
      title="网络拓扑图"
      :config="{}"
    />
    <SharedWithMeDialog v-model="sharedWithMeVisible" resource-type="topology" />
  </div>
</template>

<script setup>
import { t } from '@/i18n'
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Graph, Shape } from '@antv/x6'
import { topologyApi, assetApi, sharingApi } from '@/api'
import { DEVICE_TYPES, deviceTypeColor, deviceTypeLabel } from '@/constants/device'
import IconPickerDialog from '@/components/IconPickerDialog.vue'
import ResourceShareDialog from '@/components/ResourceShareDialog.vue'
import SharedWithMeDialog from '@/components/SharedWithMeDialog.vue'
import { can } from '@/store/auth'
import { formatHMS } from '@/utils/time'

const containerRef = ref(null)
const viewRef = ref(null)
const isFullscreen = ref(false)
const pseudoFullscreen = ref(false)
const fullscreenActive = computed(() => isFullscreen.value || pseudoFullscreen.value)
const loading = ref(false)
const discovering = ref(false)
const dialogVisible = ref(false)
const showTraffic = ref(true)
const flowLabelPercent = ref(Math.max(60, Math.min(200, Number(localStorage.getItem('nms_topo_flow_label_scale')) || 100)))
const flowLabelScale = computed(() => flowLabelPercent.value / 100)
const autoRefresh = ref(true)
const selectedNode = ref(null)
const locateNodeId = ref(null)
const router = useRouter()
const route = useRoute()
const shareVisible = ref(false)
const sharedWithMeVisible = ref(false)
const sharedResource = ref(null)
const sharedReadOnly = computed(() => Boolean(sharedResource.value && !sharedResource.value.can_edit))
let hoveredTopoNode = ''

// 视图 / 编辑模式（默认视图模式只读）
const mode = ref('view')
// 编辑模式默认进入拖拽连线，移动布局可切换到「移动布局」
const editTool = ref('connect')
const sizeNodeIds = ref([])
const nodeSizePercent = ref(100)
const canEdit = computed(() => (can('topology:edit') || Boolean(sharedResource.value?.can_edit)) && !sharedReadOnly.value)
const canEditAssets = computed(() => can('assets:edit'))
const editMode = computed(() => mode.value === 'edit' && canEdit.value)
const modeShortHint = computed(() => (
  editTool.value === 'connect'
    ? '编辑模式（拖拽连线）：拖动设备创建连接 · 添加云出口 · 双击连线删除需确认 · 完成后保存布局'
    : '编辑模式（移动布局）：拖动节点调整位置 · 添加云出口 · 双击连线不会删除 · 完成后保存布局'
))
const edgeDeleteHint = computed(() => {
  if (!editMode.value) return '视图模式只读：切换到「编辑」后可调整连线'
  if (editTool.value === 'connect') return '拖拽连线模式：双击连线可删除（需二次确认）'
  return '移动布局模式：拖动节点不会删除连线；如需删除请使用下方「删除连线」按钮'
})
const savingLayout = ref(false)
const discardingLayout = ref(false)
const dirty = ref(false)
const deviceDialogVisible = ref(false)
const deviceSaving = ref(false)
const editingDeviceId = ref(null)
const assetOptions = ref([])
const assetOptionsLoading = ref(false)
const selectedAssetId = ref(null)
const newDeviceIcon = ref('')
const newIconPickerVisible = ref(false)
const selectedAsset = computed(() => assetOptions.value.find((item) => item.id === selectedAssetId.value) || null)
const selectedAssetInTopology = computed(() => (
  !!selectedAsset.value && nodes.value.some((node) => node.device_id === selectedAsset.value.id)
))
const deviceForm = reactive({
  name: '',
  ip_address: '',
  device_type: 'switch',
  vendor: '',
  model: '',
  location: '',
  snmp_version: 'v2c',
  community: 'public',
  port: 161,
  is_enabled: true,
})

const nodes = ref([])
const edges = ref([])
const allNodes = ref([])
const allEdges = ref([])
// 拓扑专用虚拟云节点/云链路（不写入设备资产表）
const cloudNodes = ref([])
const cloudLinks = ref([])
const activeScaleGroup = ref('')
const scaleGroupMode = ref('type')
const statusFilter = ref('all')
const typeFilter = ref('all')
const locationFilter = ref('all')
const keywordFilter = ref('')
const largeModeThreshold = 150
const maxGroupNodes = 120
const scaleTruncated = ref(false)
const totalBps = ref(0)
const updatedAt = ref(null)
const selectedEdge = ref(null)
const selectedEdgeFlow = computed(() => (
  selectedEdge.value ? edgeFlowValues(selectedEdge.value) : { upload: null, download: null }
))
const nodeOptions = computed(() => nodes.value.filter((node) => node.device_id))
const iconPickerVisible = ref(false)
const iconPickerDeviceId = ref(null)
const iconPickerDevice = computed(
  () => nodes.value.find((node) => node.device_id === iconPickerDeviceId.value) || null
)

function finiteNumberOrNull(value) {
  if (value === null || value === undefined || value === '') return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

function normalizeCloudNode(raw) {
  if (!raw || typeof raw !== 'object') return null
  const rawId = raw.cloud_id ?? raw.cloud_node_id ?? raw.id
  const cloudId = Number.parseInt(String(rawId ?? '').replace(/^cloud_/, ''), 10)
  if (!Number.isFinite(cloudId) || cloudId <= 0) return null
  return {
    ...raw,
    id: `cloud_${cloudId}`,
    cloud_id: cloudId,
    cloud_node_id: cloudId,
    device_id: null,
    is_cloud: true,
    cloud: true,
    label: String(raw.label || '互联网出口').slice(0, 100) || '互联网出口',
    device_type: 'cloud',
    status: 'unknown',
    ip_address: '',
    location: '',
    vendor: '',
    model: '',
    icon: '',
    x: finiteNumberOrNull(raw.x),
    y: finiteNumberOrNull(raw.y),
    width: Number(raw.width) >= 70 ? Number(raw.width) : 104,
    height: Number(raw.height) >= 50 ? Number(raw.height) : 74,
  }
}

function normalizeCloudLink(raw) {
  if (!raw || typeof raw !== 'object') return null
  const rawId = raw.cloud_link_id ?? raw.id
  const linkId = Number.parseInt(String(rawId ?? '').replace(/^cloudlink_/, ''), 10)
  if (!Number.isFinite(linkId) || linkId <= 0) return null
  const source = String(raw.source || '')
  const target = String(raw.target || '')
  if (!source || !target || source === target) return null
  return {
    ...raw,
    id: `cloudlink_${linkId}`,
    cloud_link_id: linkId,
    connection_id: null,
    is_cloud_link: true,
    cloud_link: true,
    source,
    target,
    source_interface: String(raw.source_interface || ''),
    target_interface: String(raw.target_interface || ''),
  }
}

function nextCloudNodeId() {
  return cloudNodes.value.reduce((max, node) => Math.max(max, Number(node.cloud_id) || 0), 0) + 1
}

function nextCloudLinkId() {
  return cloudLinks.value.reduce((max, link) => Math.max(max, Number(link.cloud_link_id) || 0), 0) + 1
}

function nodeModelForCell(cell) {
  const data = cell?.getData?.() || {}
  return data.node || null
}

function nodeById(nodeId) {
  return nodes.value.find((node) => node.id === nodeId)
    || cloudNodes.value.find((node) => node.id === nodeId)
    || allNodes.value.find((node) => node.id === nodeId)
    || null
}

const topologyLegend = computed(() => {
  const counts = new Map()
  filteredNodes.value.forEach((node) => {
    const type = node.device_type || 'other'
    counts.set(type, (counts.get(type) || 0) + 1)
  })
  const legacyCloudCount = counts.get('cloud') || 0
  counts.delete('cloud')
  const items = [...counts.entries()].map(([type, count]) => ({
    type,
    count,
    label: deviceTypeLabel(type),
    color: deviceTypeColor(type),
  }))
  const cloudCount = cloudNodes.value.length + legacyCloudCount
  if (cloudCount) {
    items.push({
      type: 'cloud',
      count: cloudCount,
      label: deviceTypeLabel('cloud'),
      color: deviceTypeColor('cloud'),
    })
  }
  return items.sort((a, b) => {
    const order = (value) => {
      if (value === 'cloud') return 97
      const index = DEVICE_TYPES.findIndex((item) => item.value === value)
      return index < 0 ? 99 : index
    }
    return order(a.type) - order(b.type)
  })
})

const nodeCount = computed(() => allNodes.value.length || nodes.value.filter((node) => !node.is_cloud).length)
const edgeCount = computed(() => allEdges.value.length + cloudLinks.value.length)

const largeMode = computed(() => allNodes.value.length > largeModeThreshold)
const largeOverview = computed(() => (
  largeMode.value && !activeScaleGroup.value && !editMode.value
))

const typeFilterOptions = computed(() => {
  const values = new Set(allNodes.value.map((node) => node.device_type || 'other'))
  return [...values].map((value) => ({ value, label: deviceTypeLabel(value) }))
})

const locationFilterOptions = computed(() => {
  const values = new Set(allNodes.value.map((node) => node.location || '未分配位置'))
  return [...values].map((value) => ({ value, label: value }))
})

const filteredNodes = computed(() => {
  const keyword = keywordFilter.value.trim().toLowerCase()
  return allNodes.value.filter((node) => {
    if (statusFilter.value !== 'all' && (node.status || 'unknown') !== statusFilter.value) return false
    if (typeFilter.value !== 'all' && (node.device_type || 'other') !== typeFilter.value) return false
    if (locationFilter.value !== 'all' && (node.location || '未分配位置') !== locationFilter.value) return false
    if (keyword) {
      const text = `${node.label || ''} ${node.ip_address || ''} ${node.vendor || ''}`.toLowerCase()
      if (!text.includes(keyword)) return false
    }
    return true
  })
})

const scaleGroups = computed(() => {
  const groups = new Map()
  filteredNodes.value.forEach((node) => {
    const isLocation = scaleGroupMode.value === 'location'
    const raw = isLocation ? (node.location || '未分配位置') : (node.device_type || 'other')
    const key = `${isLocation ? 'location' : 'type'}:${raw}`
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        raw,
        label: isLocation ? raw : deviceTypeLabel(raw),
        color: isLocation ? '#38bdf8' : deviceTypeColor(raw),
        count: 0,
        online: 0,
        warning: 0,
        offline: 0,
        unknown: 0,
      })
    }
    const item = groups.get(key)
    item.count += 1
    const status = node.status || 'unknown'
    item[status] = (item[status] || 0) + 1
  })
  return [...groups.values()].sort((a, b) => b.count - a.count)
})

const activeScaleGroupInfo = computed(() => (
  scaleGroups.value.find((group) => group.key === activeScaleGroup.value) || null
))

function nodeMatchesActiveGroup(node) {
  if (!activeScaleGroup.value) return true
  const value = scaleGroupMode.value === 'location'
    ? (node.location || '未分配位置')
    : (node.device_type || 'other')
  return activeScaleGroup.value === `${scaleGroupMode.value === 'location' ? 'location' : 'type'}:${value}`
}

function applyScaleView(fitAfter = false) {
  let visible = filteredNodes.value
  scaleTruncated.value = false
  if (largeMode.value && !editMode.value) {
    if (!activeScaleGroup.value) {
      visible = []
    } else {
      visible = visible.filter(nodeMatchesActiveGroup)
      if (visible.length > maxGroupNodes) {
        visible = visible.slice(0, maxGroupNodes)
        scaleTruncated.value = true
      }
    }
  }
  // 大规模总览不画云节点；进入编辑或打开分组后保留云出口上下文
  const visibleCloudNodes = largeMode.value && !editMode.value && !activeScaleGroup.value
    ? []
    : cloudNodes.value
  nodes.value = [...visible, ...visibleCloudNodes]
  const ids = new Set(nodes.value.map((node) => node.id))
  const visibleEdges = allEdges.value.filter((edge) => ids.has(edge.source) && ids.has(edge.target))
  const visibleCloudLinks = cloudLinks.value.filter((edge) => ids.has(edge.source) && ids.has(edge.target))
  edges.value = [...visibleEdges, ...visibleCloudLinks]
  if (selectedNode.value && !ids.has(selectedNode.value.id)) selectedNode.value = null
  if (selectedEdge.value && !edges.value.some((edge) => edge.id === selectedEdge.value.id)) {
    selectedEdge.value = null
  }
  if (graph) render()
  if (fitAfter && nodes.value.length) setTimeout(fitView, 50)
}

function openScaleGroup(group) {
  activeScaleGroup.value = group.key
  applyScaleView(true)
}

function closeScaleGroup() {
  activeScaleGroup.value = ''
  applyScaleView()
}

function changeScaleGroupMode(value) {
  scaleGroupMode.value = value
  activeScaleGroup.value = ''
  applyScaleView()
}

function resetScaleFilters() {
  statusFilter.value = 'all'
  typeFilter.value = 'all'
  locationFilter.value = 'all'
  keywordFilter.value = ''
  activeScaleGroup.value = ''
  applyScaleView()
}

watch(
  [editMode, statusFilter, typeFilter, locationFilter, keywordFilter],
  () => applyScaleView(),
)

const form = reactive({
  source_device_id: null,
  source_interface: '',
  dest_device_id: null,
  dest_interface: '',
})
// 拖拽连线的两端锚点：设备框内相对坐标 0~1；手动新增连接时为空，沿用自动边界
const connectionAnchors = ref({ source: null, dest: null })
const connectSuggestion = ref(null)

function setConnectSuggestion(payload, clientX, clientY) {
  if (!payload) {
    connectSuggestion.value = null
    return
  }
  const rect = containerRef.value?.getBoundingClientRect()
  if (!rect) {
    connectSuggestion.value = payload
    return
  }
  const width = 228
  const left = Math.max(10, Math.min(rect.width - width - 10, clientX - rect.left + 16))
  const top = Math.max(10, Math.min(rect.height - 76, clientY - rect.top + 16))
  connectSuggestion.value = { ...payload, left, top }
}

function clearConnectSuggestion() {
  connectSuggestion.value = null
}

function anchorSideLabel(ratio) {
  if (!ratio) return '自动锚点'
  if (ratio.y <= 0.05) return '顶部'
  if (ratio.y >= 0.95) return '底部'
  if (ratio.x <= 0.05) return '左侧'
  if (ratio.x >= 0.95) return '右侧'
  return '边缘'
}

// 设备接口选项（选择源/目的设备后加载；按设备 ID 做短缓存并共享并发请求）
const sourceInterfaces = ref([])
const destInterfaces = ref([])
const sourceIfLoading = ref(false)
const destIfLoading = ref(false)
const noSourceInterfaces = computed(
  () => !!form.source_device_id && !sourceIfLoading.value && sourceInterfaces.value.length === 0
)
const noDestInterfaces = computed(
  () => !!form.dest_device_id && !destIfLoading.value && destInterfaces.value.length === 0
)

const INTERFACE_CACHE_TTL = 60 * 1000
const interfaceCache = new Map()
const interfaceRequests = new Map()
const interfaceLoadSeq = { source: 0, dest: 0 }

function interfaceSideRefs(side) {
  return side === 'source'
    ? { target: sourceInterfaces, loading: sourceIfLoading }
    : { target: destInterfaces, loading: destIfLoading }
}

function fetchDeviceInterfaces(deviceId) {
  const key = Number(deviceId)
  const pending = interfaceRequests.get(key)
  if (pending) return pending
  const request = topologyApi.getDeviceInterfaces(deviceId)
    .then((res) => {
      const items = res.data || []
      interfaceCache.set(key, { items, at: Date.now() })
      return items
    })
    .finally(() => {
      if (interfaceRequests.get(key) === request) interfaceRequests.delete(key)
    })
  interfaceRequests.set(key, request)
  return request
}

function interfaceOptionLabel(item) {
  const status = String(item.oper_status || '').toLowerCase() === 'up' ? 'UP' : 'DOWN'
  const parts = [item.name, status]
  if (item.description) parts.push(item.description)
  if (item.speed) parts.push(fmtBps(item.speed))
  return parts.join(' · ')
}

async function loadDeviceInterfaces(deviceId, side) {
  const { target, loading } = interfaceSideRefs(side)
  const seq = ++interfaceLoadSeq[side]
  const key = Number(deviceId)
  if (!deviceId) {
    target.value = []
    loading.value = false
    return
  }
  const cached = interfaceCache.get(key)
  if (cached) {
    // 已加载过的设备先即时回显选项，TTL 内直接复用，不再转圈等待
    target.value = cached.items
    if (Date.now() - cached.at < INTERFACE_CACHE_TTL) {
      loading.value = false
      return
    }
  } else {
    target.value = []
  }
  loading.value = true
  try {
    const items = await fetchDeviceInterfaces(deviceId)
    if (seq === interfaceLoadSeq[side]) target.value = items
  } catch {
    if (seq === interfaceLoadSeq[side] && !cached) target.value = []
  } finally {
    if (seq === interfaceLoadSeq[side]) loading.value = false
  }
}

function onSourceDeviceChange(deviceId) {
  form.source_interface = ''
  connectionAnchors.value.source = null
  loadDeviceInterfaces(deviceId, 'source')
}

function onDestDeviceChange(deviceId) {
  form.dest_interface = ''
  connectionAnchors.value.dest = null
  loadDeviceInterfaces(deviceId, 'dest')
}

function openConnectionDialog(sourceDeviceId = null, destDeviceId = null, sourceAnchor = null, destAnchor = null) {
  form.source_device_id = sourceDeviceId || null
  form.source_interface = ''
  form.dest_device_id = destDeviceId || null
  form.dest_interface = ''
  connectionAnchors.value = { source: sourceAnchor, dest: destAnchor }
  sourceInterfaces.value = []
  destInterfaces.value = []
  // 先展示对话框，接口选项并发加载，绝不让网络请求阻塞弹窗
  dialogVisible.value = true
  if (sourceDeviceId) loadDeviceInterfaces(sourceDeviceId, 'source')
  if (destDeviceId) loadDeviceInterfaces(destDeviceId, 'dest')
}

function openAddConnection() {
  openConnectionDialog()
}

// 云出口链路（拓扑虚拟节点 ↔ 真实设备，不写 DeviceConnection）
const cloudLinkDialogVisible = ref(false)
const cloudLinkInterfaces = ref([])
const cloudLinkIfLoading = ref(false)
const cloudLinkForm = reactive({
  cloud_node_id: null,
  cloud_label: '',
  device_id: null,
  interface: '',
})

// ==================== 拖拽连线 ====================
let connectDrag = null
// ==================== 连线路径微调 ====================
let edgeDrag = null
let flowLabelDrag = null
const flowLabelState = new Map()
let syncingFlowLabels = false

function applyEditTool() {
  if (!graph) return
  groupDrag = null
  const connecting = editMode.value && editTool.value === 'connect'
  graph.options.interacting.nodeMovable = editMode.value && !connecting
  graph.options.interacting.edgeLabelMovable = false
  graph.options.panning = !connecting
  containerRef.value?.classList.toggle('topo-connect-mode', connecting)
  if (!connecting) cleanupConnectDrag()
  if (connecting || !editMode.value) {
    clearSizeSelection()
  }
}

function clientToLocalPoint(clientX, clientY) {
  if (!graph) return { x: 0, y: 0 }
  if (typeof graph.clientToLocal === 'function') {
    return graph.clientToLocal(clientX, clientY)
  }
  const rect = containerRef.value?.getBoundingClientRect() || { left: 0, top: 0 }
  return graph.pageToLocal(clientX + window.scrollX - rect.left, clientY + window.scrollY - rect.top)
}

function connectTargetAt(clientX, clientY) {
  const elements = typeof document.elementsFromPoint === 'function'
    ? document.elementsFromPoint(clientX, clientY)
    : [document.elementFromPoint(clientX, clientY)]
  for (const el of elements) {
    const nodeEl = el?.closest?.('.x6-node[data-shape="topo-device"]')
    if (!nodeEl) continue
    const cellId = nodeEl.getAttribute('data-cell-id')
    const node = cellId && graph ? graph.getCellById(cellId) : null
    return { node: node || null, el: nodeEl }
  }
  return { node: null, el: null }
}

// ==================== 拖拽连线锚点 ====================
const CONNECT_ANCHORS = (() => {
  const count = 24
  const points = []
  for (let index = 0; index < count; index += 1) {
    const t = index / count
    if (t < 0.25) {
      points.push({ x: (t / 0.25), y: 0 })
    } else if (t < 0.5) {
      points.push({ x: 1, y: (t - 0.25) / 0.25 })
    } else if (t < 0.75) {
      points.push({ x: 1 - (t - 0.5) / 0.25, y: 1 })
    } else {
      points.push({ x: 0, y: 1 - (t - 0.75) / 0.25 })
    }
  }
  return points
})()

const SMART_CONNECT_RADIUS = 180

function smartAnchorPair(sourceNode, targetNode, spreadIndex = 0, spreadTotal = 1) {
  if (!sourceNode || !targetNode) return null
  const sourceBox = sourceNode.getBBox?.()
  const targetBox = targetNode.getBBox?.()
  if (!sourceBox || !targetBox) return null
  const dx = (targetBox.x + targetBox.width / 2) - (sourceBox.x + sourceBox.width / 2)
  const dy = (targetBox.y + targetBox.height / 2) - (sourceBox.y + sourceBox.height / 2)
  const spread = spreadTotal > 1
    ? (spreadIndex - (spreadTotal - 1) / 2) * 0.12
    : 0
  const clamp = (value) => Math.max(0.12, Math.min(0.88, value))
  if (Math.abs(dx) >= Math.abs(dy)) {
    return {
      axis: 'horizontal',
      source: { x: dx >= 0 ? 1 : 0, y: clamp(0.5 + spread) },
      target: { x: dx >= 0 ? 0 : 1, y: clamp(0.5 - spread) },
    }
  }
  return {
    axis: 'vertical',
    source: { x: clamp(0.5 + spread), y: dy >= 0 ? 1 : 0 },
    target: { x: clamp(0.5 - spread), y: dy >= 0 ? 0 : 1 },
  }
}

function anchorTerminal(cell, ratio) {
  if (!cell || !ratio) return null
  const size = cell.getSize()
  return {
    cell: cell.id,
    anchor: {
      name: 'topLeft',
      args: {
        dx: Number(ratio.x) * size.width,
        dy: Number(ratio.y) * size.height,
      },
    },
    // 使用 anchor 连接点，避免 X6 再次把端点投影到节点边界而偏离锚点
    connectionPoint: { name: 'anchor', args: { offset: 0 } },
  }
}

function anchorPoint(cell, ratio) {
  if (!cell || !ratio) return null
  const box = cell.getBBox()
  return {
    x: box.x + Number(ratio.x) * box.width,
    y: box.y + Number(ratio.y) * box.height,
  }
}

function dotForRatio(nodeEl, ratio) {
  if (!nodeEl || !ratio) return null
  addAnchorDots(nodeEl)
  const dots = [...nodeEl.querySelectorAll('.topo-anchor-dot')]
  let best = null
  dots.forEach((dot) => {
    const dx = Number(dot.dataset.ax) - Number(ratio.x)
    const dy = Number(dot.dataset.ay) - Number(ratio.y)
    const distance = Math.hypot(dx, dy)
    if (!best || distance < best.distance) best = { dot, distance }
  })
  return best?.dot || null
}

function smartConnectCandidate(clientX, clientY, sourceNode) {
  if (!graph || !sourceNode) return null
  const direct = connectTargetAt(clientX, clientY)
  if (direct.node && direct.node.id !== sourceNode.id) {
    return { node: direct.node, el: direct.el, distance: 0, direct: true }
  }
  const local = clientToLocalPoint(clientX, clientY)
  const zoom = Math.max(0.25, Number(graph.zoom()) || 1)
  const threshold = SMART_CONNECT_RADIUS / zoom
  let best = null
  graph.getNodes().forEach((node) => {
    if (node.id === sourceNode.id) return
    const box = node.getBBox?.()
    if (!box) return
    const dx = Math.max(box.x - local.x, 0, local.x - (box.x + box.width))
    const dy = Math.max(box.y - local.y, 0, local.y - (box.y + box.height))
    const distance = Math.hypot(dx, dy)
    if (distance > threshold) return
    const el = containerRef.value?.querySelector(`.x6-node[data-cell-id="${node.id}"]`)
    if (!el) return
    if (!best || distance < best.distance) best = { node, el, distance, direct: false }
  })
  return best
}

function applyReattachCandidate(drag, candidate, clientX, clientY) {
  if (!drag || !candidate?.node || !graph) return false
  if (candidate.node.id === drag.fixedNode.id) return false
  const snapped = nearestAnchor(candidate.node, candidate.el, clientX, clientY, 22)
  let anchor = snapped?.ratio || null
  if (!anchor) {
    const pair = drag.endpoint === 'source'
      ? smartAnchorPair(candidate.node, drag.fixedNode)
      : smartAnchorPair(drag.fixedNode, candidate.node)
    if (!pair) return false
    anchor = drag.endpoint === 'source' ? pair.source : pair.target
  }
  const terminal = anchorTerminal(candidate.node, anchor)
  if (!terminal) return false
  if (drag.endpoint === 'source') drag.edge.setSource(terminal)
  else drag.edge.setTarget(terminal)
  drag.candidateNode = candidate.node
  drag.candidateEl = candidate.el
  drag.anchor = anchor
  addAnchorDots(candidate.el)
  candidate.el.classList.add('topo-connect-target', 'topo-smart-target')
  setActiveAnchor(candidate.el, dotForRatio(candidate.el, anchor))
  setConnectSuggestion({
    active: true,
    kicker: '智能重连建议',
    title: candidate.node.getData()?.node?.label || candidate.node.id,
    detail: `吸附${anchorSideLabel(anchor)}锚点 · 松开完成改接`,
  }, clientX, clientY)
  return true
}

function addAnchorDots(nodeEl) {
  if (!nodeEl) return
  const card = nodeEl.querySelector('.topo-compact-node')
  if (!card || card.querySelector('.topo-anchor-dot')) return
  CONNECT_ANCHORS.forEach((anchor) => {
    const dot = document.createElement('span')
    dot.className = 'topo-anchor-dot'
    dot.dataset.ax = String(anchor.x)
    dot.dataset.ay = String(anchor.y)
    dot.style.left = `${anchor.x * 100}%`
    dot.style.top = `${anchor.y * 100}%`
    card.appendChild(dot)
  })
}

function removeAnchorDots(nodeEl) {
  nodeEl?.querySelectorAll('.topo-anchor-dot').forEach((dot) => dot.remove())
}

function removeAllAnchorDots() {
  containerRef.value?.querySelectorAll('.topo-anchor-dot').forEach((dot) => dot.remove())
}

function addAllAnchorDots() {
  containerRef.value?.querySelectorAll('.x6-node[data-shape="topo-device"]').forEach((el) => addAnchorDots(el))
}

function setActiveAnchor(nodeEl, dot) {
  nodeEl?.querySelectorAll('.topo-anchor-dot.active').forEach((item) => item.classList.remove('active'))
  dot?.classList.add('active')
}

function nearestAnchor(node, nodeEl, clientX, clientY, threshold = 18) {
  if (!node || !nodeEl) return null
  addAnchorDots(nodeEl)
  const dots = [...nodeEl.querySelectorAll('.topo-anchor-dot')]
  let best = null
  dots.forEach((dot) => {
    const rect = dot.getBoundingClientRect()
    const distance = Math.hypot(clientX - (rect.left + rect.width / 2), clientY - (rect.top + rect.height / 2))
    if (distance <= threshold && (!best || distance < best.distance)) {
      const ratio = { x: Number(dot.dataset.ax), y: Number(dot.dataset.ay) }
      const bbox = node.getBBox()
      best = {
        distance,
        dot,
        ratio,
        point: { x: bbox.x + ratio.x * bbox.width, y: bbox.y + ratio.y * bbox.height },
      }
    }
  })
  return best
}

function updateConnectDragTarget(targetNode, targetEl) {
  if (!connectDrag) return
  const oldEl = connectDrag.targetEl
  if (oldEl && oldEl !== targetEl) {
    oldEl.classList.remove('topo-connect-target')
    oldEl.classList.remove('topo-smart-target')
    setActiveAnchor(oldEl, null)
    if (oldEl !== connectDrag.sourceEl) removeAnchorDots(oldEl)
  }
  connectDrag.targetEl = targetEl
  connectDrag.targetNode = targetNode
  if (targetEl) {
    targetEl.classList.add('topo-connect-target')
    addAnchorDots(targetEl)
  }
}

function anchorFromPoint(node, point) {
  const bbox = node?.getBBox?.()
  if (!bbox || !bbox.width || !bbox.height) return null
  const clamp = (value) => Math.max(0.02, Math.min(0.98, value))
  return {
    x: clamp((point.x - bbox.x) / bbox.width),
    y: clamp((point.y - bbox.y) / bbox.height),
  }
}

function onConnectDragMove(event) {
  if (!connectDrag || !graph) return
  event.preventDefault?.()
  const candidate = smartConnectCandidate(event.clientX, event.clientY, connectDrag.sourceNode)
  const valid = candidate?.node || null
  updateConnectDragTarget(valid, valid ? candidate.el : null)
  const local = clientToLocalPoint(event.clientX, event.clientY)
  const pair = valid ? smartAnchorPair(connectDrag.sourceNode, valid) : null
  const snapped = valid
    ? nearestAnchor(valid, candidate.el, event.clientX, event.clientY, 22)
    : null
  const targetRatio = snapped?.ratio || pair?.target || null
  if (valid) {
    setActiveAnchor(candidate.el, dotForRatio(candidate.el, targetRatio))
  }
  const point = valid ? (anchorPoint(valid, targetRatio) || local) : local
  connectDrag.targetAnchor = valid ? targetRatio : null
  if (valid) {
    const nodeData = valid.getData()?.node || {}
    setConnectSuggestion({
      active: true,
      kicker: candidate?.direct ? '最优连线建议' : '智能吸附建议',
      title: nodeData.label || valid.id,
      detail: `推荐${anchorSideLabel(targetRatio)}锚点 · 自动选择曼哈顿最短路径 · 松开即可连接`,
    }, event.clientX, event.clientY)
    candidate.el.classList.add('topo-smart-target')
  } else {
    setConnectSuggestion({
      active: false,
      kicker: '智能连线',
      title: '继续靠近目标设备',
      detail: '将自动推荐最近设备和最佳锚点',
    }, event.clientX, event.clientY)
  }
  if (typeof connectDrag.edge.setTargetPoint === 'function') {
    connectDrag.edge.setTargetPoint(point)
  } else {
    connectDrag.edge.setTarget(point)
  }
}

function cleanupConnectDrag() {
  if (!connectDrag) return
  window.removeEventListener('mousemove', onConnectDragMove, true)
  window.removeEventListener('mouseup', onConnectDragEnd, true)
  connectDrag.targetEl?.classList.remove('topo-connect-target')
  containerRef.value?.querySelectorAll('.topo-smart-target').forEach((el) => el.classList.remove('topo-smart-target'))
  setActiveAnchor(connectDrag.targetEl, null)
  try {
    if (connectDrag.edge && graph) graph.removeCell(connectDrag.edge)
  } catch {
    /* 临时连线可能已被销毁 */
  }
  connectDrag = null
  clearConnectSuggestion()
  removeAllAnchorDots()
  containerRef.value?.classList.remove('topo-connecting')
}

function onConnectDragEnd(event) {
  if (!connectDrag) return
  const drag = connectDrag
  const validTarget = drag.targetNode || null
  const targetAnchor = drag.targetAnchor || null
  cleanupConnectDrag()
  if (!validTarget) {
    ElMessage.warning('请拖拽到另一台设备附近松开，才能创建连线')
    return
  }
  const sourceNodeData = drag.sourceNode.getData()?.node
  const targetNodeData = validTarget.getData()?.node
  if (sourceNodeData?.is_cloud || targetNodeData?.is_cloud) {
    if (sourceNodeData?.is_cloud && targetNodeData?.is_cloud) {
      ElMessage.warning('云出口节点只能连接真实设备')
      return
    }
    const cloudNode = sourceNodeData?.is_cloud ? sourceNodeData : targetNodeData
    const deviceNode = sourceNodeData?.is_cloud ? targetNodeData : sourceNodeData
    if (!deviceNode?.device_id) {
      ElMessage.warning('设备信息不完整，无法创建云出口链路')
      return
    }
    openCloudLinkDialog(cloudNode, deviceNode.device_id)
    return
  }
  const sourceDeviceId = drag.sourceNode.getData()?.deviceId
  const targetDeviceId = validTarget.getData()?.deviceId
  if (!sourceDeviceId || !targetDeviceId) {
    ElMessage.warning('设备信息不完整，无法创建连线')
    return
  }
  openConnectionDialog(sourceDeviceId, targetDeviceId, drag.sourceAnchor, targetAnchor)
}

function startConnectDrag(node, nativeEvent) {
  if (!graph || !editMode.value || editTool.value !== 'connect') return
  cleanupConnectDrag()
  const sourceEl = containerRef.value?.querySelector(`.x6-node[data-cell-id="${node.id}"]`)
  addAnchorDots(sourceEl)
  const local = clientToLocalPoint(nativeEvent.clientX, nativeEvent.clientY)
  const snap = nearestAnchor(node, sourceEl, nativeEvent.clientX, nativeEvent.clientY, Number.POSITIVE_INFINITY)
  if (sourceEl) setActiveAnchor(sourceEl, snap?.dot || null)
  const point = snap?.point || local
  const sourceAnchor = snap?.ratio || anchorFromPoint(node, point)
  const edge = graph.addEdge({
    // 使用真实鼠标点作为临时连线起点，不再吸附到左边/右边框
    source: { x: point.x, y: point.y },
    target: { x: point.x, y: point.y },
    connector: { name: 'rounded', args: { radius: 8 } },
    zIndex: 100,
    attrs: {
      line: {
        stroke: '#38bdf8',
        strokeWidth: 2,
        strokeDasharray: '7 5',
        sourceMarker: null,
        targetMarker: null,
      },
    },
  })
  connectDrag = { sourceNode: node, sourceEl, edge, sourceAnchor, targetNode: null, targetEl: null, targetAnchor: null }
  containerRef.value?.classList.add('topo-connecting')
  setConnectSuggestion({
    active: false,
    kicker: '智能连线',
    title: '拖动到目标设备附近',
    detail: '自动高亮最佳目标与锚点',
  }, nativeEvent.clientX, nativeEvent.clientY)
  window.addEventListener('mousemove', onConnectDragMove, true)
  window.addEventListener('mouseup', onConnectDragEnd, true)
}

function edgeMidpoint(edge) {
  const source = edge.getSourceCell()
  const target = edge.getTargetCell()
  if (!source || !target) return { x: 0, y: 0 }
  const sp = source.position()
  const ss = source.size()
  const tp = target.position()
  const ts = target.size()
  return {
    x: (sp.x + ss.width / 2 + tp.x + ts.width / 2) / 2,
    y: (sp.y + ss.height / 2 + tp.y + ts.height / 2) / 2,
  }
}

function edgeRenderedEndpoints(edge) {
  const view = graph?.findViewByCell(edge)
  const connection = view?.getConnection?.()
  try {
    if (connection && typeof connection.pointAtLength === 'function') {
      const total = Number(
        (typeof connection.length === 'function' ? connection.length() : connection.getTotalLength?.()) || 0
      )
      const source = connection.pointAtLength(0)
      const target = total > 0 ? connection.pointAtLength(total) : connection.pointAtLength(1)
      if (source && target) return { source, target }
    }
  } catch {
    /* 回退到几何端点 */
  }
  return {
    source: edge.getSourcePoint(),
    target: edge.getTargetPoint(),
  }
}

function startEdgeDrag(edge, event) {
  if (!graph || !editMode.value) return
  const native = event?.originalEvent || event
  if (native?.button !== 0) return
  cleanupEdgeDrag()
  const local = clientToLocalPoint(native.clientX, native.clientY)
  const endpoints = edgeRenderedEndpoints(edge)
  const sourcePoint = endpoints.source
  const targetPoint = endpoints.target
  const threshold = 96 / Math.max(0.25, graph.zoom() || 1)
  const sourceDistance = Math.hypot(local.x - sourcePoint.x, local.y - sourcePoint.y)
  const targetDistance = Math.hypot(local.x - targetPoint.x, local.y - targetPoint.y)
  let endpoint = null
  if (sourceDistance <= threshold && sourceDistance <= targetDistance) {
    endpoint = 'source'
  } else if (targetDistance <= threshold) {
    endpoint = 'target'
  }

  if (endpoint) {
    const node = endpoint === 'source' ? edge.getSourceCell() : edge.getTargetCell()
    const fixedNode = endpoint === 'source' ? edge.getTargetCell() : edge.getSourceCell()
    if (!node || !fixedNode) return
    const nodeEl = containerRef.value?.querySelector(`.x6-node[data-cell-id="${node.id}"]`)
    const originalTerminal = endpoint === 'source' ? { ...edge.getSource() } : { ...edge.getTarget() }
    addAllAnchorDots()
    setActiveAnchor(nodeEl, nearestAnchor(node, nodeEl, native.clientX, native.clientY)?.dot || null)
    edgeDrag = {
      mode: 'reattach',
      endpoint,
      originalNode: node,
      originalTerminal,
      fixedNode,
      edge,
      startX: local.x,
      startY: local.y,
      candidateNode: null,
      candidateEl: null,
      anchor: null,
      moved: false,
      zIndex: edge.getZIndex(),
    }
    setConnectSuggestion({
      active: false,
      kicker: '智能重连',
      title: '拖动连线端点',
      detail: '靠近任意设备可自动吸附，设备已显示锚点',
    }, native.clientX, native.clientY)
    window.addEventListener('mousemove', onEdgeDragMove, true)
    window.addEventListener('mouseup', onEdgeDragEnd, true)
    return
  }

  const data = edge.getData() || {}
  const midpoint = edgeMidpoint(edge)
  const autoVertex = data.autoVertex && Number.isFinite(Number(data.autoVertex.x))
    ? { x: Number(data.autoVertex.x), y: Number(data.autoVertex.y) }
    : midpoint
  const existing = data.edgeOffset && Number.isFinite(Number(data.edgeOffset.x))
    ? { x: Number(data.edgeOffset.x), y: Number(data.edgeOffset.y) }
    : { x: 0, y: 0 }
  edgeDrag = {
    mode: 'offset',
    edge,
    startX: local.x,
    startY: local.y,
    baseX: autoVertex.x,
    baseY: autoVertex.y,
    baseOffset: existing,
    offset: existing,
    moved: false,
    zIndex: edge.getZIndex(),
  }
  window.addEventListener('mousemove', onEdgeDragMove, true)
  window.addEventListener('mouseup', onEdgeDragEnd, true)
}

function onEdgeDragMove(event) {
  if (!edgeDrag) return
  event.preventDefault?.()
  const local = clientToLocalPoint(event.clientX, event.clientY)
  const dx = local.x - (edgeDrag.startX || local.x)
  const dy = local.y - (edgeDrag.startY || local.y)
  if (!edgeDrag.moved && Math.hypot(dx, dy) < 2) return
  edgeDrag.moved = true
  edgeDrag.edge.setZIndex(50)

  if (edgeDrag.mode === 'reattach') {
    const candidate = smartConnectCandidate(event.clientX, event.clientY, edgeDrag.fixedNode)
    if (edgeDrag.candidateEl && edgeDrag.candidateEl !== candidate?.el) {
      edgeDrag.candidateEl.classList.remove('topo-connect-target', 'topo-smart-target')
      setActiveAnchor(edgeDrag.candidateEl, null)
      edgeDrag.candidateEl = null
      edgeDrag.candidateNode = null
      edgeDrag.anchor = null
    }
    if (candidate?.node && candidate.node.id !== edgeDrag.fixedNode.id) {
      if (applyReattachCandidate(edgeDrag, candidate, event.clientX, event.clientY)) return
    }
    if (edgeDrag.endpoint === 'source') edgeDrag.edge.setSource({ x: local.x, y: local.y })
    else edgeDrag.edge.setTarget({ x: local.x, y: local.y })
    setConnectSuggestion({
      active: false,
      kicker: '智能重连',
      title: '继续靠近目标设备',
      detail: '设备锚点已展开，自动吸附最近锚点',
    }, event.clientX, event.clientY)
    return
  }

  const offset = {
    x: Math.round((edgeDrag.baseOffset.x + dx) * 100) / 100,
    y: Math.round((edgeDrag.baseOffset.y + dy) * 100) / 100,
  }
  edgeDrag.offset = offset
  edgeDrag.edge.setVertices([{
    x: edgeDrag.baseX + offset.x,
    y: edgeDrag.baseY + offset.y,
  }])
}

function cleanupEdgeDrag() {
  if (!edgeDrag) return
  window.removeEventListener('mousemove', onEdgeDragMove, true)
  window.removeEventListener('mouseup', onEdgeDragEnd, true)
  if (edgeDrag.mode === 'reattach') removeAllAnchorDots()
  containerRef.value?.querySelectorAll('.topo-connect-target, .topo-smart-target').forEach((el) => {
    el.classList.remove('topo-connect-target', 'topo-smart-target')
  })
  clearConnectSuggestion()
  edgeDrag = null
}

function onEdgeDragEnd(event) {
  if (!edgeDrag) return
  const drag = edgeDrag
  // 鼠标释放时再做一次几何吸附兜底，避免移动过程中事件抖动导致未吸附
  if (drag.mode === 'reattach' && drag.moved && !drag.candidateNode
    && Number.isFinite(event?.clientX) && Number.isFinite(event?.clientY)) {
    const fallback = smartConnectCandidate(event.clientX, event.clientY, drag.fixedNode)
    if (fallback?.node) applyReattachCandidate(drag, fallback, event.clientX, event.clientY)
  }
  cleanupEdgeDrag()
  drag.edge.setZIndex(drag.zIndex == null ? 1 : drag.zIndex)
  if (!drag.moved) return
  const connId = drag.edge.getData()?.connectionId
  const item = edges.value.find((edge) => edge.connection_id === connId)
    || allEdges.value.find((edge) => edge.connection_id === connId)

  if (drag.mode === 'reattach') {
    const candidate = drag.candidateNode
    if (!candidate) {
      if (drag.endpoint === 'source') drag.edge.setSource(drag.originalTerminal)
      else drag.edge.setTarget(drag.originalTerminal)
      ElMessage.warning('未吸附到设备，已恢复原连接')
      return
    }
    const isSource = drag.endpoint === 'source'
    const anchor = drag.anchor ? { ...drag.anchor } : null
    const data = drag.edge.getData() || {}
    if (candidate.id === drag.originalNode.id) {
      const nextData = {
        ...data,
        ...(isSource ? { sourceAnchor: anchor } : { destAnchor: anchor }),
      }
      drag.edge.setData(nextData)
      if (item) {
        if (isSource) item.source_anchor = anchor
        else item.dest_anchor = anchor
      }
      if (selectedEdge.value && selectedEdge.value.connection_id === connId) {
        selectedEdge.value = {
          ...selectedEdge.value,
          ...(isSource ? { source_anchor: anchor } : { dest_anchor: anchor }),
        }
      }
      dirty.value = true
      ElMessage.success('连线锚点已更新，点击「保存布局」持久化')
      return
    }

    const newSourceNode = isSource ? candidate : drag.fixedNode
    const newTargetNode = isSource ? drag.fixedNode : candidate
    const sourceDeviceId = newSourceNode.getData()?.deviceId
    const targetDeviceId = newTargetNode.getData()?.deviceId
    if (!sourceDeviceId || !targetDeviceId || sourceDeviceId === targetDeviceId) {
      if (isSource) drag.edge.setSource(drag.originalTerminal)
      else drag.edge.setTarget(drag.originalTerminal)
      ElMessage.warning('设备信息不完整，无法改接连线')
      return
    }
    const sourceAnchor = isSource ? anchor : (data.sourceAnchor || null)
    const destAnchor = isSource ? (data.destAnchor || null) : anchor
    drag.edge.setData({
      ...data,
      sourceAnchor,
      destAnchor,
    })
    if (item) {
      item.source = `device_${sourceDeviceId}`
      item.target = `device_${targetDeviceId}`
      item.source_anchor = sourceAnchor
      item.dest_anchor = destAnchor
      if (isSource) item.source_interface = ''
      else item.target_interface = ''
    }
    if (selectedEdge.value && selectedEdge.value.connection_id === connId) {
      selectedEdge.value = {
        ...selectedEdge.value,
        source_anchor: sourceAnchor,
        dest_anchor: destAnchor,
        ...(isSource
          ? { source_interface: '', device_name: newSourceNode.getData()?.node?.label || selectedEdge.value.device_name }
          : { target_interface: '' }),
      }
    }
    dirty.value = true
    ElMessage.success(`连线已改接到「${candidate.getData()?.node?.label || candidate.id}」，点击「保存布局」持久化`)
    return
  }

  if (item) item.edge_offset = { ...drag.offset }
  drag.edge.setData({
    ...(drag.edge.getData() || {}),
    edgeOffset: { ...drag.offset },
  })
  if (selectedEdge.value && selectedEdge.value.connection_id === connId) {
    selectedEdge.value = { ...selectedEdge.value, edge_offset: { ...drag.offset } }
  }
  dirty.value = true
}

function resetEdgeOffset() {
  if (!selectedEdge.value || !graph) return
  const connId = selectedEdge.value.connection_id
  const edge = graph.getEdges().find((item) => item.getData()?.connectionId === connId)
  if (edge) {
    const autoVertex = edge.getData()?.autoVertex
    edge.setVertices(autoVertex ? [autoVertex] : [])
  }
  const item = edges.value.find((entry) => entry.connection_id === connId)
    || allEdges.value.find((entry) => entry.connection_id === connId)
  if (item) item.edge_offset = null
  if (edge) edge.setData({ ...(edge.getData() || {}), edgeOffset: null })
  selectedEdge.value = { ...selectedEdge.value, edge_offset: null }
  dirty.value = true
  ElMessage.success('已恢复该连线的自动路径，点击「保存布局」持久化')
}

function labelPositionParts(label) {
  const raw = label?.position
  const position = typeof raw === 'object' && raw ? raw : { distance: Number(raw) || 0.5 }
  const offset = position.offset && typeof position.offset === 'object'
    ? position.offset
    : { x: 0, y: 0 }
  return {
    distance: Number(position.distance ?? 0.5),
    x: Number(offset.x || 0),
    y: Number(offset.y || 0),
  }
}

function rememberFlowLabels(edge) {
  if (!edge) return
  const labels = edge.getLabels()
  if (labels.length !== 2) return
  flowLabelState.set(edge.id, labels.map(labelPositionParts))
}

function applyFlowLabelGroup(edge, offset) {
  const labels = edge.getLabels()
  if (labels.length !== 2) return
  edge.setLabels(labels.map((label, index) => ({
    ...label,
    position: {
      ...(typeof label.position === 'object' && label.position ? label.position : {}),
      distance: 0.5,
      offset: {
        x: Number(offset.x || 0) + (index === 0 ? -flowLabelGap() : flowLabelGap()),
        y: Number(offset.y || 0),
      },
    },
  })))
}

function startFlowLabelDrag(edge, nativeEvent) {
  if (!graph || !editMode.value || nativeEvent?.button !== 0) return
  cleanupFlowLabelDrag()
  const native = nativeEvent
  native.preventDefault?.()
  native.stopPropagation?.()
  const local = clientToLocalPoint(native.clientX, native.clientY)
  const data = edge.getData() || {}
  const baseOffset = data.labelOffset || edge.edge_label_offset || { x: 0, y: 0 }
  const offset = { x: Number(baseOffset.x || 0), y: Number(baseOffset.y || 0) }
  const edgeView = graph.findViewByCell(edge)
  const viewEl = edgeView?.container || null
  viewEl?.classList.add('flow-label-dragging')
  flowLabelDrag = {
    edge,
    viewEl,
    startX: local.x,
    startY: local.y,
    baseOffset: { ...offset },
    offset: { ...offset },
    moved: false,
    zIndex: edge.getZIndex(),
  }
  const connId = data.connectionId
  selectedNode.value = null
  clearNodeHighlight()
  selectedEdge.value = edges.value.find((item) => item.connection_id === connId)
    || allEdges.value.find((item) => item.connection_id === connId)
    || null
  window.addEventListener('mousemove', onFlowLabelDragMove, true)
  window.addEventListener('mouseup', onFlowLabelDragEnd, true)
}

function onFlowLabelMouseDown(event) {
  if (!editMode.value) return
  const labelEl = event.target?.closest?.('.x6-edge-label')
  if (!labelEl) return
  const edgeEl = labelEl.closest('.x6-edge')
  const edgeId = edgeEl?.getAttribute('data-cell-id')
  const edge = edgeId && graph ? graph.getCellById(edgeId) : null
  if (!edge) return
  event.preventDefault?.()
  event.stopPropagation?.()
  startFlowLabelDrag(edge, event)
}

function onFlowLabelDragMove(event) {
  if (!flowLabelDrag) return
  event.preventDefault?.()
  const local = clientToLocalPoint(event.clientX, event.clientY)
  const dx = local.x - flowLabelDrag.startX
  const dy = local.y - flowLabelDrag.startY
  if (!flowLabelDrag.moved && Math.hypot(dx, dy) < 2) return
  flowLabelDrag.moved = true
  flowLabelDrag.edge.setZIndex(50)
  const offset = {
    x: flowLabelDrag.baseOffset.x + dx,
    y: flowLabelDrag.baseOffset.y + dy,
  }
  flowLabelDrag.offset = offset
  applyFlowLabelGroup(flowLabelDrag.edge, offset)
}

function flowLabelConflict(edge) {
  if (!graph) return false
  const viewEl = graph.findViewByCell(edge)?.container
  const labelEls = [...(viewEl?.querySelectorAll('.x6-edge-label') || [])]
  if (!labelEls.length) return false
  const center = labelEls.reduce((acc, element) => {
    const rect = element.getBoundingClientRect()
    acc.x += rect.x + rect.width / 2
    acc.y += rect.y + rect.height / 2
    return acc
  }, { x: 0, y: 0 })
  center.x /= labelEls.length
  center.y /= labelEls.length
  const local = clientToLocalPoint(center.x, center.y)
  const threshold = 22 / Math.max(0.25, graph.zoom() || 1)
  return graph.getEdges().some((other) => {
    if (other.id === edge.id) return false
    const path = graph.findViewByCell(other)?.getConnection?.()
    if (!path) return false
    const closestLength = path.closestPointLength(local)
    const closest = path.pointAtLength(closestLength)
    if (!closest) return false
    return Math.hypot(local.x - closest.x, local.y - closest.y) <= threshold
  })
}

function cleanupFlowLabelDrag() {
  if (!flowLabelDrag) return
  window.removeEventListener('mousemove', onFlowLabelDragMove, true)
  window.removeEventListener('mouseup', onFlowLabelDragEnd, true)
  const drag = flowLabelDrag
  flowLabelDrag = null
  drag.viewEl?.classList.remove('flow-label-dragging')
  return drag
}

function onFlowLabelDragEnd() {
  const drag = cleanupFlowLabelDrag()
  if (!drag) return
  drag.edge.setZIndex(drag.zIndex == null ? 1 : drag.zIndex)
  if (!drag.moved) return
  if (flowLabelConflict(drag.edge)) {
    applyFlowLabelGroup(drag.edge, drag.baseOffset)
    ElMessage.warning(t('topology.flowLabelMismatch'))
    return
  }
  const connId = drag.edge.getData()?.connectionId
  const item = edges.value.find((edge) => edge.connection_id === connId)
    || allEdges.value.find((edge) => edge.connection_id === connId)
  if (item) item.edge_label_offset = { ...drag.offset }
  drag.edge.setData({ ...(drag.edge.getData() || {}), labelOffset: { ...drag.offset } })
  if (selectedEdge.value && selectedEdge.value.connection_id === connId) {
    selectedEdge.value = { ...selectedEdge.value, edge_label_offset: { ...drag.offset } }
  }
  dirty.value = true
}

function syncFlowLabelGroup(edge) {
  if (!edge || syncingFlowLabels) return
  const labels = edge.getLabels()
  if (labels.length !== 2) return
  const current = labels.map(labelPositionParts)
  const previous = flowLabelState.get(edge.id)
  if (!previous) {
    flowLabelState.set(edge.id, current)
    return
  }
  const changed = current
    .map((position, index) => {
      const old = previous[index]
      if (!old) return false
      return Math.abs(position.distance - old.distance) > 0.1
        || Math.abs(position.x - old.x) > 0.1
        || Math.abs(position.y - old.y) > 0.1
    })
    .map((value, index) => (value ? index : -1))
    .filter((index) => index >= 0)
  if (changed.length !== 1) {
    flowLabelState.set(edge.id, current)
    return
  }
  const index = changed[0]
  const centerX = current[index].x - (index === 0 ? -FLOW_LABEL_GAP : FLOW_LABEL_GAP)
  const centerY = current[index].y
  const next = labels.map((label, itemIndex) => ({
    ...label,
    position: {
      ...(typeof label.position === 'object' && label.position ? label.position : {}),
      distance: 0.5,
      offset: {
        x: centerX + (itemIndex === 0 ? -FLOW_LABEL_GAP : FLOW_LABEL_GAP),
        y: centerY,
      },
    },
  }))
  syncingFlowLabels = true
  edge.setLabels(next)
  syncingFlowLabels = false
  flowLabelState.set(edge.id, next.map(labelPositionParts))
  const connId = edge.getData()?.connectionId
  const item = edges.value.find((entry) => entry.connection_id === connId)
    || allEdges.value.find((entry) => entry.connection_id === connId)
  const offset = { x: Math.round(centerX * 100) / 100, y: Math.round(centerY * 100) / 100 }
  if (item) item.edge_label_offset = offset
  edge.setData({ ...(edge.getData() || {}), labelOffset: offset })
  dirty.value = true
}

const TYPE_COLORS = {
  router: '#38bdf8',
  switch: '#34d399',
  firewall: '#f87171',
  security: '#c084fc',
  server: '#fbbf24',
  cloud: '#0ea5e9',
}
const STATUS_COLORS = {
  online: '#22c55e',
  warning: '#f59e0b',
  offline: '#ef4444',
  disabled: '#64748b',
  unknown: '#94a3b8',
}
const STATUS_TEXT = { get online() { return t('topology.online') }, get warning() { return t('topology.alert') }, get offline() { return t('topology.offline') }, get disabled() { return '未启用' }, get unknown() { return t('topology.unknown') } }

let graph = null
let groupDrag = null
let suppressNodeClickUntil = 0
let smartAnchorFrame = null

function refreshSmartEdgeAnchors() {
  smartAnchorFrame = null
  if (!graph) return
  graph.getEdges().forEach((edge) => {
    const sourceCell = edge.getSourceCell()
    const targetCell = edge.getTargetCell()
    if (!sourceCell || !targetCell) return
    const data = edge.getData() || {}
    const pair = smartAnchorPair(sourceCell, targetCell)
    if (!pair) return
    if (!data.sourceAnchor) {
      const source = anchorTerminal(sourceCell, pair.source)
      if (source) edge.setSource(source)
    }
    if (!data.destAnchor) {
      const target = anchorTerminal(targetCell, pair.target)
      if (target) edge.setTarget(target)
    }
  })
}

function scheduleSmartEdgeAnchors() {
  if (!graph || smartAnchorFrame) return
  smartAnchorFrame = requestAnimationFrame(refreshSmartEdgeAnchors)
}
let refreshTimer = null
let resizeObserver = null
let resizeTimer = null
let needsFit = true

// ==================== 图标（SVG） ====================
function glyph(type, colorOverride = '') {
  const c = colorOverride || TYPE_COLORS[type] || '#94a3b8'
  const stroke = `stroke="${c}" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round"`
  if (type === 'router') {
    // 圆形 + 四向箭头
    return `
      <circle cx="32" cy="32" r="15" ${stroke}/>
      <path d="M32 20v24M20 32h24" ${stroke} stroke-width="2.2" opacity="0.9"/>
      <path d="M32 16l4 5-4 5M32 48l-4-5 4-5" ${stroke} stroke-width="2.2"/>
      <path d="M16 32l5-4 5 4M48 32l-5 4-5-4" ${stroke} stroke-width="2.2"/>
    `
  }
  if (type === 'switch') {
    // 矩形 + 双向箭头
    return `
      <rect x="14" y="22" width="36" height="20" rx="3" ${stroke}/>
      <path d="M22 30h20M22 36h20" ${stroke} stroke-width="2.2"/>
      <path d="M40 27l4 3-4 3M24 33l-4 3 4 3" ${stroke} stroke-width="2.2"/>
    `
  }
  if (type === 'firewall') {
    // 砖墙
    return `
      <rect x="14" y="16" width="36" height="32" rx="2" ${stroke}/>
      <path d="M14 26h36M14 38h36" ${stroke} stroke-width="2"/>
      <path d="M26 16v10M38 16v10M20 26v12M32 26v12M44 26v12M26 38v10M38 38v10" ${stroke} stroke-width="2"/>
    `
  }
  if (type === 'security') {
    // 盾牌 + 对勾
    return `
      <path d="M32 12l16 6v13c0 10-7 17-16 21-9-4-16-11-16-21V18l16-6z" ${stroke}/>
      <path d="M24 32l6 6 11-12" ${stroke} stroke-width="3"/>
    `
  }
  if (type === 'server') {
    return `
      <rect x="18" y="12" width="28" height="40" rx="3" ${stroke}/>
      <path d="M18 24h28M18 36h28" ${stroke} stroke-width="2.2"/>
      <circle cx="23" cy="18" r="1.6" fill="${c}"/><circle cx="23" cy="30" r="1.6" fill="${c}"/>
      <circle cx="23" cy="42" r="1.6" fill="${c}"/>
    `
  }
  if (type === 'wireless') {
    return `
      <path d="M16 28a24 24 0 0 1 32 0" ${stroke}/>
      <path d="M22 35a16 16 0 0 1 20 0" ${stroke}/>
      <path d="M28 41a8 8 0 0 1 8 0" ${stroke}/>
      <circle cx="32" cy="47" r="2.2" fill="${c}"/>
    `
  }
  if (type === 'loadbalancer') {
    return `
      <circle cx="16" cy="22" r="4" ${stroke}/><circle cx="16" cy="42" r="4" ${stroke}/>
      <circle cx="48" cy="32" r="5" ${stroke}/>
      <path d="M20 22l12 8M20 42l12-8M41 32H30" ${stroke} stroke-width="2.2"/>
    `
  }
  if (type === 'storage') {
    return `
      <ellipse cx="32" cy="18" rx="15" ry="5" ${stroke}/>
      <path d="M17 18v10c0 3 7 5 15 5s15-2 15-5V18" ${stroke}/>
      <path d="M17 30v10c0 3 7 5 15 5s15-2 15-5V30" ${stroke}/>
      <circle cx="22" cy="23" r="1.4" fill="${c}"/><circle cx="22" cy="35" r="1.4" fill="${c}"/>
    `
  }
  if (type === 'camera') {
    return `
      <rect x="14" y="21" width="24" height="20" rx="3" ${stroke}/>
      <path d="M38 27l11-5v18l-11-5" ${stroke}/>
      <circle cx="25" cy="31" r="4" ${stroke}/>
    `
  }
  if (type === 'printer') {
    return `
      <path d="M20 24v-10h24v10" ${stroke}/>
      <rect x="14" y="24" width="36" height="16" rx="3" ${stroke}/>
      <rect x="22" y="34" width="20" height="12" ${stroke}/>
    `
  }
  if (type === 'ups') {
    return `
      <rect x="20" y="12" width="24" height="40" rx="3" ${stroke}/>
      <path d="M32 20l-6 11h8l-4 12" ${stroke} stroke-width="3"/>
    `
  }
  if (type === 'pc') {
    return `
      <rect x="14" y="16" width="36" height="24" rx="3" ${stroke}/>
      <path d="M26 48h12M32 40v8" ${stroke} stroke-width="2.4"/>
    `
  }
  if (type === 'cloud') {
    // 云朵 / 互联网出口：作为出口链路节点指示
    return `
      <path d="M44 28h-2.5A16 16 0 1 0 26 48h9a10 10 0 0 0 0-20z" ${stroke}/>
    `
  }
  return `<rect x="16" y="16" width="32" height="32" rx="4" ${stroke}/>`
}

function iconSvg(type, status, size = 64, colorOverride = '') {
  const ring = colorOverride || STATUS_COLORS[status] || STATUS_COLORS.unknown
  return `
    <svg viewBox="0 0 64 64" width="${size}" height="${size}" xmlns="http://www.w3.org/2000/svg">
      <circle cx="32" cy="32" r="30" fill="rgba(15,23,42,0.9)" stroke="${ring}" stroke-width="2.5"/>
      <circle cx="32" cy="32" r="26" fill="none" stroke="${ring}" stroke-width="1" opacity="0.25"/>
      ${glyph(type, colorOverride)}
    </svg>
  `
}

function legendIcon(type) {
  return `<svg viewBox="0 0 64 64" width="18" height="18">${glyph(type)}</svg>`
}

// ==================== 工具 ====================
function fmtBps(bps) {
  if (bps === null || bps === undefined) return '-'
  if (bps >= 1e9) return `${(bps / 1e9).toFixed(2)} Gbps`
  if (bps >= 1e6) return `${(bps / 1e6).toFixed(1)} Mbps`
  if (bps >= 1e3) return `${(bps / 1e3).toFixed(0)} Kbps`
  return `${Math.round(bps)} bps`
}

function shortBps(bps) {
  if (bps === null || bps === undefined) return '-'
  if (bps >= 1e9) return `${(bps / 1e9).toFixed(2)}G`
  if (bps >= 1e6) return `${(bps / 1e6).toFixed(1)}M`
  if (bps >= 1e3) return `${(bps / 1e3).toFixed(0)}K`
  return `${Math.round(bps)}`
}

function utilColor(util, up) {
  if (!up) return '#ef4444'
  if (util === null || util === undefined) return '#64748b'
  if (util >= 80) return '#ef4444'
  if (util >= 50) return '#f59e0b'
  return '#22c55e'
}

// ==================== 图 ====================
let htmlShapeRegistered = false

/** 注册自定义 HTML 节点（设备图标卡片） */
function registerDeviceShape() {
  if (htmlShapeRegistered) return
  const HTML = Shape && Shape.HTML
  if (!HTML || typeof HTML.register !== 'function') return

  HTML.register({
    shape: 'topo-device',
    effect: [],
    html: (cell) => {
      const wrap = document.createElement('div')
      wrap.innerHTML = nodeHtml(cell.getData()?.node || {})
      return wrap.firstElementChild || wrap
    },
  })
  htmlShapeRegistered = true
}

function initGraph() {
  if (!containerRef.value) return
  registerDeviceShape()

  graph = new Graph({
    container: containerRef.value,
    // 关闭 X6 自动尺寸（它会写内联 width/height 导致容器被撑大），
    // 由下方 ResizeObserver 调用 graph.resize() 做自适应
    autoResize: false,
    background: { color: '#0b1220' },
    grid: { visible: true, type: 'dot', args: { color: '#1e293b' } },
    panning: true,
    mousewheel: { enabled: true, modifiers: ['ctrl', 'meta'] },
    interacting: {
      nodeMovable: editMode.value,
      edgeMovable: false,
      edgeLabelMovable: false,
    },
  })

  graph.on('scale', ({ sx }) => {
    containerRef.value?.classList.toggle('topo-zoom-far', Number(sx) < 0.55)
  })

  graph.on('node:click', ({ node, e }) => {
    const nodeData = node.getData()?.node
    // 云节点：详情面板走虚拟节点专属逻辑，不进入设备资产操作
    if (nodeData?.is_cloud) {
      selectedEdge.value = null
      selectedNode.value = nodeData
      locateNodeId.value = null
      if (editMode.value && editTool.value === 'move') {
        const native = e?.originalEvent || e
        selectNodeForSize(node, Boolean(native?.ctrlKey || native?.metaKey))
      }
      highlightNode(node.id)
      return
    }
    // 视图模式点击设备打开右侧详情面板；编辑模式用于拖拽调整
    if (editMode.value) {
      if (Date.now() < suppressNodeClickUntil && sizeNodeIds.value.includes(node.id)) return
      if (editTool.value === 'move') {
        const native = e?.originalEvent || e
        selectNodeForSize(node, Boolean(native?.ctrlKey || native?.metaKey))
      }
      return
    }
    const id = node.getData()?.deviceId
    if (!id) return
    selectedEdge.value = null
    selectedNode.value = nodes.value.find((item) => item.device_id === id) || null
    locateNodeId.value = id
    highlightNode(node.id)
  })

  graph.on('blank:click', () => {
    if (!editMode.value) return
    clearSizeSelection()
  })

  graph.on('node:mousedown', ({ node, e }) => {
    if (!editMode.value || editTool.value !== 'connect') return
    const native = e?.originalEvent || e
    if (native?.button !== 0) return
    e?.stopPropagation?.()
    native?.preventDefault?.()
    startConnectDrag(node, native)
  })

  graph.on('node:mousedown', ({ node, e }) => {
    if (!editMode.value || editTool.value !== 'move') return
    const native = e?.originalEvent || e
    if (native?.button !== 0) return
    beginGroupDrag(node)
  })

  graph.on('node:moving', ({ node }) => {
    if (groupDrag) moveGroupFollowers(node)
    scheduleSmartEdgeAnchors()
  })

  graph.on('node:mouseenter', ({ node }) => {
    if (editMode.value) return
    const nodeData = node.getData()?.node
    if (nodeData?.device_id || nodeData?.is_cloud) highlightNode(node.id)
  })

  graph.on('node:mouseleave', () => {
    clearNodeHighlight()
  })

  graph.on('node:dblclick', ({ node }) => {
    const nodeData = node.getData()?.node
    if (nodeData?.is_cloud) {
      selectedEdge.value = null
      selectedNode.value = nodeData
      locateNodeId.value = null
      highlightNode(node.id)
      return
    }
    if (!editMode.value) return
    const deviceId = node.getData()?.deviceId
    iconPickerDeviceId.value = deviceId
    iconPickerVisible.value = true
  })

  graph.on('node:moved', ({ node }) => {
    if (!editMode.value) return
    if (groupDrag) {
      if (node.id === groupDrag.leaderId) finishGroupDrag(node)
      scheduleSmartEdgeAnchors()
      return
    }
    const item = nodeModelForCell(node)
    if (item) {
      const pos = node.position()
      item.x = Math.round(pos.x)
      item.y = Math.round(pos.y)
      dirty.value = true
    }
    scheduleSmartEdgeAnchors()
  })

  graph.on('edge:mousedown', ({ edge, e }) => {
    if (!editMode.value) return
    // 云出口链路由拓扑布局 JSON 维护，不参与 DeviceConnection 的端点改接/偏移逻辑
    if (edge.getData()?.isCloudLink) return
    const native = e?.originalEvent || e
    if (native?.target?.closest?.('.x6-edge-label')) {
      startFlowLabelDrag(edge, native)
      return
    }
    startEdgeDrag(edge, e)
  })

  graph.on('edge:click', ({ edge }) => {
    const edgeId = edge.id
    selectedNode.value = null
    clearNodeHighlight()
    selectedEdge.value = edges.value.find((e) => e.id === edgeId) || null
  })

  graph.on('edge:dblclick', async ({ edge }) => {
    if (!editMode.value) {
      ElMessage.info(t('topology.readonlyModeHint'))
      return
    }
    // 移动布局模式只允许拖动节点，双击连线不得删除，避免拖动过程中误丢连线
    if (editTool.value !== 'connect') {
      ElMessage.info('移动布局模式下双击不会删除连线；如需删除请使用链路详情中的「删除连线」按钮')
      return
    }
    const cloudLinkId = edge.getData()?.cloudLinkId
    if (cloudLinkId) {
      await removeCloudLink(cloudLinkId, edge)
      return
    }
    const connId = edge.getData()?.connectionId
    if (!connId) return
    await removeConnection(connId, edge)
  })
}

/** 横向分层布局：路由 → 安全边界 → 交换 → 安全设备 → 服务器 */
const NODE_WIDTH = 104
const NODE_HEIGHT = 74
const NODE_MIN_PERCENT = 70
const NODE_MAX_PERCENT = 200

function nodeWidth(node) {
  const value = Number(node?.width)
  return Number.isFinite(value) && value >= 70 ? value : NODE_WIDTH
}

function nodeHeight(node) {
  const value = Number(node?.height)
  return Number.isFinite(value) && value >= 50 ? value : NODE_HEIGHT
}

function highlightSizeNodes() {
  const container = containerRef.value
  if (!container) return
  container.querySelectorAll('.x6-node.topo-size-selected').forEach((el) => {
    el.classList.remove('topo-size-selected')
  })
  container.querySelectorAll('.topo-selected-badge').forEach((el) => el.remove())
  if (!sizeNodeIds.value.length) return
  sizeNodeIds.value.forEach((nodeId, index) => {
    const el = container.querySelector(`.x6-node[data-cell-id="${nodeId}"]`)
    if (!el) return
    el.classList.add('topo-size-selected')
    if (index !== 0) return
    const card = el.querySelector('.topo-compact-node')
    if (card && !card.querySelector('.topo-selected-badge')) {
      const badge = document.createElement('span')
      badge.className = 'topo-selected-badge'
      badge.textContent = sizeNodeIds.value.length > 1
        ? `已选中 ${sizeNodeIds.value.length} 台`
        : '已选中'
      card.appendChild(badge)
    }
  })
}

function syncSizeInputFromNode(node) {
  if (!node) return
  const size = node.getSize()
  nodeSizePercent.value = Math.round((size.width / NODE_WIDTH) * 100)
}

function selectNodeForSize(node, additive = false) {
  if (!node) return
  if (additive) {
    const index = sizeNodeIds.value.indexOf(node.id)
    if (index >= 0) {
      sizeNodeIds.value.splice(index, 1)
    } else {
      sizeNodeIds.value.push(node.id)
    }
  } else {
    sizeNodeIds.value = [node.id]
  }
  const primary = sizeNodeIds.value.length
    ? graph?.getCellById(sizeNodeIds.value[0])
    : null
  syncSizeInputFromNode(primary)
  highlightSizeNodes()
}

function selectAllSizeNodes() {
  if (!editMode.value || !graph) return
  sizeNodeIds.value = graph.getNodes()
    .filter((node) => node.getData()?.deviceId)
    .map((node) => node.id)
  syncSizeInputFromNode(sizeNodeIds.value.length ? graph.getCellById(sizeNodeIds.value[0]) : null)
  highlightSizeNodes()
}

function beginGroupDrag(node) {
  groupDrag = null
  if (!graph || !editMode.value || editTool.value !== 'move') return
  if (sizeNodeIds.value.length <= 1 || !sizeNodeIds.value.includes(node.id)) return
  const positions = new Map()
  sizeNodeIds.value.forEach((nodeId) => {
    const cell = graph.getCellById(nodeId)
    if (!cell || typeof cell.position !== 'function') return
    const pos = cell.position()
    positions.set(nodeId, { x: Number(pos.x) || 0, y: Number(pos.y) || 0 })
  })
  if (positions.size <= 1 || !positions.has(node.id)) return
  groupDrag = {
    leaderId: node.id,
    positions,
    moved: false,
  }
}

function moveGroupFollowers(node) {
  if (!groupDrag || node.id !== groupDrag.leaderId || !graph) return
  const start = groupDrag.positions.get(node.id)
  if (!start) return
  const position = node.position()
  const dx = Number(position.x) - start.x
  const dy = Number(position.y) - start.y
  if (!groupDrag.moved && Math.hypot(dx, dy) < 1) return
  groupDrag.moved = true
  groupDrag.positions.forEach((base, nodeId) => {
    if (nodeId === groupDrag.leaderId) return
    const cell = graph.getCellById(nodeId)
    if (cell && typeof cell.position === 'function') {
      cell.position(base.x + dx, base.y + dy)
    }
  })
}

function updateNodeModelPosition(node) {
  if (!node) return
  const item = nodeModelForCell(node)
  if (!item) return
  const position = node.position()
  item.x = Math.round(position.x)
  item.y = Math.round(position.y)
}

function finishGroupDrag(node) {
  const drag = groupDrag
  groupDrag = null
  if (!drag || !graph || node.id !== drag.leaderId) return
  const start = drag.positions.get(node.id)
  if (!start) return
  const position = node.position()
  const dx = Number(position.x) - start.x
  const dy = Number(position.y) - start.y
  if (!drag.moved && Math.hypot(dx, dy) < 1) return
  drag.positions.forEach((base, nodeId) => {
    const cell = graph.getCellById(nodeId)
    if (!cell) return
    if (nodeId !== drag.leaderId && typeof cell.position === 'function') {
      cell.position(base.x + dx, base.y + dy)
    }
    updateNodeModelPosition(cell)
  })
  dirty.value = true
  suppressNodeClickUntil = Date.now() + 500
  scheduleSmartEdgeAnchors()
}

function clearSizeSelection() {
  groupDrag = null
  sizeNodeIds.value = []
  highlightSizeNodes()
}

function onTopologyKeydown(event) {
  if (!editMode.value || editTool.value !== 'move') return
  if (!(event.ctrlKey || event.metaKey) || String(event.key).toLowerCase() !== 'a') return
  const tag = String(event.target?.tagName || '').toLowerCase()
  if (tag === 'input' || tag === 'textarea' || tag === 'select' || event.target?.isContentEditable) return
  event.preventDefault()
  selectAllSizeNodes()
}

function applyNodeSize() {
  if (!editMode.value || !graph || !sizeNodeIds.value.length) return
  const percent = Math.max(NODE_MIN_PERCENT, Math.min(NODE_MAX_PERCENT, Number(nodeSizePercent.value) || 100))
  nodeSizePercent.value = percent
  const width = Math.round(NODE_WIDTH * percent / 100)
  const height = Math.round(NODE_HEIGHT * percent / 100)
  sizeNodeIds.value.forEach((nodeId) => {
    const node = graph.getCellById(nodeId)
    if (!node) return
    const item = nodeModelForCell(node)
    if (item) {
      item.width = width
      item.height = height
    }
    node.resize(width, height)
  })
  dirty.value = true
  render()
  // X6 HTML 节点重绘是异步的，等 DOM 完成后再恢复批量选中提示
  setTimeout(highlightSizeNodes, 80)
}

function layoutNodes(list) {
  // 无层级网格布局：设备只按顺序排成紧凑网格，不绘制层级底板/标题
  const items = [...list].sort((a, b) => String(a.label || '').localeCompare(String(b.label || ''), 'zh-CN'))
  const startX = 72
  const startY = 80
  const columnGap = 32
  const rowGap = 36
  const columns = Math.min(8, Math.max(1, Math.ceil(Math.sqrt(items.length || 1))))
  const rows = Math.max(1, Math.ceil(items.length / columns))
  const width = Math.max(
    720,
    startX * 2 + columns * NODE_WIDTH + Math.max(0, columns - 1) * columnGap,
  )
  const positions = {}
  items.forEach((node, index) => {
    const row = Math.floor(index / columns)
    const column = index % columns
    const countInRow = Math.min(columns, items.length - row * columns)
    const rowWidth = countInRow * NODE_WIDTH + Math.max(0, countInRow - 1) * columnGap
    const rowStartX = startX + Math.max(0, (width - startX * 2 - rowWidth) / 2)
    positions[node.id] = {
      x: rowStartX + column * (NODE_WIDTH + columnGap),
      y: startY + row * (NODE_HEIGHT + rowGap),
    }
  })
  return {
    positions,
    width,
    height: startY * 2 + rows * NODE_HEIGHT + Math.max(0, rows - 1) * rowGap,
  }
}

async function applyNodeIcon(url) {
  const device = iconPickerDevice.value
  if (!device?.device_id) return
  const previous = device.icon
  try {
    await assetApi.update(device.device_id, { icon: url })
    device.icon = url
    render()
    ElMessage.success(t('topology.iconUpdated'))
  } catch (error) {
    device.icon = previous
    ElMessage.error(error.message || t('topology.saveLayoutFailed'))
  }
}

function nodeHtml(node) {
  const isCloud = Boolean(node.is_cloud)
  const status = node.status || 'unknown'
  const statusColor = isCloud ? '#ffffff' : (STATUS_COLORS[status] || STATUS_COLORS.unknown)
  const statusLabel = isCloud ? '虚拟节点' : (STATUS_TEXT[status] || status || '未知')
  const alerting = !isCloud && (status === 'warning' || status === 'offline')
  const alertSymbol = status === 'offline' ? '×' : '!'
  const tooltip = isCloud
    ? `${node.label || '互联网出口'} · 云 / 互联网出口 · 拓扑虚拟节点`
    : `${node.label || ''} · ${node.ip_address || '未配置地址'} · ${node.vendor || '未知厂商'} · ${statusLabel}`
  const nodeScale = Math.min(nodeWidth(node) / NODE_WIDTH, nodeHeight(node) / NODE_HEIGHT)

  const iconBlock = !isCloud && node.icon
    ? `<img src="${escapeHtml(node.icon)}" alt="icon"
         style="width:34px;height:34px;object-fit:contain;border-radius:8px;
                background:rgba(15,23,42,0.9);border:1px solid ${statusColor};padding:2px;" />`
    : `<div style="width:34px;height:34px;display:flex;align-items:center;justify-content:center;
         border-radius:50%;background:rgba(15,23,42,0.9);border:1px solid ${statusColor}66;
         box-shadow:0 0 12px ${statusColor}${alerting ? '55' : '22'};">
         ${iconSvg(isCloud ? 'cloud' : node.device_type, status, 31, isCloud ? '#ffffff' : '')}</div>`

  return `
    <div xmlns="http://www.w3.org/1999/xhtml" class="topo-compact-node topo-status-${status}${isCloud ? ' topo-cloud-node' : ''}"
      title="${escapeHtml(tooltip)}"
      style="
      width:100%;height:100%;display:flex;align-items:center;justify-content:center;
      box-sizing:border-box;padding:0;border-radius:10px;position:relative;overflow:visible;
      background:linear-gradient(160deg, rgba(12,30,48,.97), rgba(7,19,32,.98));
      border:1px solid ${statusColor}${alerting ? 'cc' : '66'};
      box-shadow:0 5px 16px rgba(0,0,0,.32), inset 0 0 16px ${statusColor}${alerting ? '20' : '0b'};
      font-family:-apple-system,'Microsoft YaHei',sans-serif;user-select:none;cursor:pointer;">
      <div style="width:${NODE_WIDTH}px;height:${NODE_HEIGHT}px;display:flex;flex-direction:column;
        align-items:center;justify-content:center;box-sizing:border-box;padding:4px 6px;
        transform:scale(${nodeScale});transform-origin:center;">
        <div style="position:relative;flex-shrink:0;filter:drop-shadow(0 3px 7px rgba(0,0,0,.4));">
          ${iconBlock}
          ${alerting ? `<span class="topo-alert-badge" style="position:absolute;right:-7px;top:-7px;width:16px;height:16px;
            border-radius:50%;background:${statusColor};color:#0b1220;border:2px solid #0b1220;
            display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:900;
            line-height:1;box-shadow:0 0 10px ${statusColor}bb;">${alertSymbol}</span>` : ''}
        </div>
        <div class="device-name" style="max-width:92px;margin-top:2px;overflow:hidden;text-overflow:ellipsis;
          white-space:nowrap;font-size:10.5px;font-weight:700;line-height:1.15;color:#e6f3fb;">${escapeHtml(node.label)}</div>
        <div class="device-status" style="margin-top:2px;display:flex;align-items:center;gap:4px;
          color:${statusColor};font-size:9px;line-height:1.1;white-space:nowrap;">
          <span style="width:5px;height:5px;border-radius:50%;background:${statusColor};box-shadow:0 0 5px ${statusColor};"></span>
          ${escapeHtml(statusLabel)}
        </div>
      </div>
    </div>
  `
}

function escapeHtml(text) {
  return String(text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function edgeFlowValues(edge) {
  return {
    upload: edge.src_out_bps ?? edge.dst_in_bps,
    download: edge.src_in_bps ?? edge.dst_out_bps,
  }
}

const FLOW_LABEL_GAP = 28
const MAX_FLOW_LABEL_LINE_OFFSET = 0

function flowLabelGap() {
  return FLOW_LABEL_GAP * flowLabelScale.value
}

function applyFlowLabelScale() {
  const percent = Math.max(60, Math.min(200, Number(flowLabelPercent.value) || 100))
  flowLabelPercent.value = percent
  try {
    localStorage.setItem('nms_topo_flow_label_scale', String(percent))
  } catch {
    /* 忽略存储异常 */
  }
  if (!graph) return
  const scale = percent / 100
  const gap = flowLabelGap()
  graph.getEdges().forEach((edge) => {
    const labels = edge.getLabels()
    if (!labels.length) return
    if (labels.length === 2) {
      const rawOffset = edge.getData()?.labelOffset || { x: 0, y: 0 }
      const offset = {
        x: Number(rawOffset.x || 0),
        y: Number(rawOffset.y || 0),
      }
      edge.setLabels(labels.map((label, index) => ({
        ...label,
        position: {
          ...(typeof label.position === 'object' && label.position ? label.position : {}),
          distance: 0.5,
          offset: {
            x: offset.x + (index === 0 ? -gap : gap),
            y: offset.y,
          },
        },
        attrs: {
          ...(label.attrs || {}),
          label: { ...(label.attrs?.label || {}), fontSize: 10 * scale },
          body: {
            ...(label.attrs?.body || {}),
            rx: 6 * scale,
            ry: 6 * scale,
            refWidth: 10 * scale,
            refHeight: 4 * scale,
          },
        },
      })))
      return
    }
    edge.setLabels(labels.map((label) => ({
      ...label,
      attrs: {
        ...(label.attrs || {}),
        label: { ...(label.attrs?.label || {}), fontSize: 10 * scale },
        body: {
          ...(label.attrs?.body || {}),
          rx: 6 * scale,
          ry: 6 * scale,
          refWidth: 10 * scale,
          refHeight: 4 * scale,
        },
      },
    })))
  })
}

function clampFlowLabelOffset(edge, offset) {
  const polyline = edge?.getPolyline?.()
  if (!polyline) return offset
  const midpoint = polyline.pointAt(0.5)
  if (!midpoint) return offset
  const center = { x: midpoint.x + Number(offset.x || 0), y: midpoint.y + Number(offset.y || 0) }
  const closest = polyline.closestPoint(center)
  if (!closest) return offset
  const dx = center.x - closest.x
  const dy = center.y - closest.y
  const distance = Math.hypot(dx, dy)
  if (distance <= MAX_FLOW_LABEL_LINE_OFFSET || distance < 0.01) return offset
  const ratio = MAX_FLOW_LABEL_LINE_OFFSET / distance
  return {
    x: closest.x + dx * ratio - midpoint.x,
    y: closest.y + dy * ratio - midpoint.y,
  }
}

function edgeFlowLabels(edge) {
  if (edge.is_cloud_link) return []
  const scale = flowLabelScale.value
  const gap = flowLabelGap()
  const labelOffset = edge.edge_label_offset && typeof edge.edge_label_offset === 'object'
    ? { x: Number(edge.edge_label_offset.x || 0), y: Number(edge.edge_label_offset.y || 0) }
    : { x: 0, y: 0 }
  const centerPosition = {
    distance: 0.5,
    offset: { x: labelOffset.x, y: labelOffset.y },
  }
  const labelAttrs = (text, color) => ({
    label: { text, fill: color, fontSize: 10 * scale, fontWeight: 700 },
    body: {
      fill: 'rgba(15,23,42,0.94)',
      stroke: color,
      strokeWidth: 1,
      rx: 6 * scale,
      ry: 6 * scale,
      refWidth: 10 * scale,
      refHeight: 4 * scale,
    },
  })
  if (edge.oper_up === false) {
    return [{
      position: centerPosition,
      attrs: labelAttrs(t('topology.linkDown'), '#f87171'),
    }]
  }
  const { upload, download } = edgeFlowValues(edge)
  return [
    {
      flow: 'upload',
      position: {
        distance: 0.5,
        offset: { x: labelOffset.x - gap, y: labelOffset.y },
      },
      attrs: labelAttrs(`↑${shortBps(upload)}`, '#38bdf8'),
    },
    {
      flow: 'download',
      position: {
        distance: 0.5,
        offset: { x: labelOffset.x + gap, y: labelOffset.y },
      },
      attrs: labelAttrs(`↓${shortBps(download)}`, '#fbbf24'),
    },
  ]
}

function edgeStyle(edge) {
  if (edge.is_cloud_link) {
    return { color: '#0ea5e9', width: 1.8, dashed: true, animated: false }
  }
  const up = edge.oper_up !== false
  const color = utilColor(edge.utilization, up)
  const util = edge.utilization || 0
  const width = Math.min(3.5, 1.4 + util / 45)
  const flow = Math.max(edge.src_out_bps || 0, edge.src_in_bps || 0,
    edge.dst_out_bps || 0, edge.dst_in_bps || 0)
  return { color, width, animated: up && flow > 0 }
}

function render() {
  if (!graph) return
  graph.clearCells()
  flowLabelState.clear()

  const layout = layoutNodes(nodes.value)
  const layoutPos = layout.positions
  const centers = {}

  nodes.value.forEach((n) => {
    const fallback = layoutPos[n.id] || { x: 72, y: 92 }
    // 手动布局优先：保存的是节点左上角坐标；自动布局给的是左上角坐标
    const hasSaved =
      n.x !== null && n.x !== undefined && n.y !== null && n.y !== undefined
    const x = hasSaved ? Number(n.x) : fallback.x
    const y = hasSaved ? Number(n.y) : fallback.y
    const nodeW = nodeWidth(n)
    const nodeH = nodeHeight(n)
    centers[n.id] = { cx: x + nodeW / 2, cy: y + nodeH / 2 }

    graph.addNode({
      id: n.id,
      shape: 'topo-device',
      x,
      y,
      width: nodeW,
      height: nodeH,
      zIndex: 10,
      data: { deviceId: n.device_id, node: n },
    })
  })

  const edgePairStats = new Map()
  edges.value.forEach((e) => {
    const key = [e.source, e.target].sort().join('|')
    edgePairStats.set(key, (edgePairStats.get(key) || 0) + 1)
  })
  const edgePairSeen = new Map()

  edges.value.forEach((e) => {
    if (!graph.getCellById(e.source) || !graph.getCellById(e.target)) return
    const style = edgeStyle(e)
    const srcPos = centers[e.source]
    const dstPos = centers[e.target]
    const pairKey = [e.source, e.target].sort().join('|')
    const pairTotal = edgePairStats.get(pairKey) || 1
    const pairSeen = edgePairSeen.get(pairKey) || 0
    edgePairSeen.set(pairKey, pairSeen + 1)
    // 同一对设备存在多条链路时，为每条链路加一个垂直于两端连线的偏移点，避免完全重叠
    let parallelVertex = null
    if (pairTotal > 1 && srcPos && dstPos) {
      const dx = dstPos.cx - srcPos.cx
      const dy = dstPos.cy - srcPos.cy
      const length = Math.hypot(dx, dy) || 1
      const offset = (pairSeen - (pairTotal - 1) / 2) * 26
      parallelVertex = {
        x: (srcPos.cx + dstPos.cx) / 2 + (-dy / length) * offset,
        y: (srcPos.cy + dstPos.cy) / 2 + (dx / length) * offset,
      }
    }

    let routeVertex = parallelVertex
    if (e.edge_offset && srcPos && dstPos) {
      const base = routeVertex || {
        x: (srcPos.cx + dstPos.cx) / 2,
        y: (srcPos.cy + dstPos.cy) / 2,
      }
      routeVertex = {
        x: base.x + Number(e.edge_offset.x || 0),
        y: base.y + Number(e.edge_offset.y || 0),
      }
    }

    const sourceNodeData = nodes.value.find((item) => item.id === e.source)
    const targetNodeData = nodes.value.find((item) => item.id === e.target)
    const sourceWidth = nodeWidth(sourceNodeData)
    const sourceHeight = nodeHeight(sourceNodeData)
    const targetWidth = nodeWidth(targetNodeData)
    const targetHeight = nodeHeight(targetNodeData)
    const sourceCell = graph.getCellById(e.source)
    const targetCell = graph.getCellById(e.target)
    const smartPair = smartAnchorPair(sourceCell, targetCell, pairSeen, pairTotal)
    // 自动连线优先使用面向对端设备的智能锚点；用户手动拖拽过的端点保持原锚点
    const sourceAnchor = e.source_anchor || smartPair?.source
    const targetAnchor = e.dest_anchor || smartPair?.target
    const sourceTerminal = sourceAnchor
      ? {
          cell: e.source,
          anchor: {
            name: 'topLeft',
            args: {
              dx: Number(sourceAnchor.x) * sourceWidth,
              dy: Number(sourceAnchor.y) * sourceHeight,
            },
          },
          connectionPoint: { name: 'anchor', args: { offset: 0 } },
        }
      : {
          cell: e.source,
          anchor: { name: 'center' },
          connectionPoint: { name: 'boundary', args: { offset: 8 } },
        }
    const targetTerminal = targetAnchor
      ? {
          cell: e.target,
          anchor: {
            name: 'topLeft',
            args: {
              dx: Number(targetAnchor.x) * targetWidth,
              dy: Number(targetAnchor.y) * targetHeight,
            },
          },
          connectionPoint: { name: 'anchor', args: { offset: 0 } },
        }
      : {
          cell: e.target,
          anchor: { name: 'center' },
          connectionPoint: { name: 'boundary', args: { offset: 8 } },
        }

    graph.addEdge({
      id: e.id,
      source: sourceTerminal,
      target: targetTerminal,
      connector: { name: 'rounded', args: { radius: 10 } },
      router: {
        name: 'manhattan',
        args: {
          padding: 32,
          step: 16,
          startDirections: ['bottom', 'top', 'left', 'right'],
          endDirections: ['top', 'bottom', 'left', 'right'],
        },
      },
      ...(routeVertex ? { vertices: [routeVertex] } : {}),
      zIndex: 1,
      attrs: {
        line: {
          stroke: style.color,
          strokeWidth: style.width,
          strokeDasharray: style.dashed ? '7 5' : (style.animated ? '8 6' : ''),
          sourceMarker: null,
          targetMarker: null,
          style: style.animated
            ? { animation: 'topo-dash 1.2s linear infinite' }
            : {},
          opacity: e.oper_up === false ? 0.55 : 1,
        },
      },
      labels: showTraffic.value ? edgeFlowLabels(e) : [],
      data: {
        connectionId: e.connection_id,
        cloudLinkId: e.cloud_link_id || null,
        isCloudLink: Boolean(e.is_cloud_link),
        edgeOffset: e.edge_offset || null,
        labelOffset: e.edge_label_offset || null,
        autoVertex: parallelVertex,
        sourceAnchor: e.source_anchor || null,
        destAnchor: e.dest_anchor || null,
      },
    })
  })
  graph.getEdges().forEach(rememberFlowLabels)

  if (needsFit) {
    needsFit = false
    // 等卡片、图例和 flex 布局完成后再做首次适配
    setTimeout(() => {
      resizeGraphToContainer()
      fitView()
    }, 120)
  }
}

function onCanvasPointerMove(event) {
  if (editMode.value) return
  const nodeEl = event.target?.closest?.('.x6-node[data-shape="topo-device"]')
  const nodeId = nodeEl?.getAttribute('data-cell-id') || ''
  if (nodeId === hoveredTopoNode) return
  hoveredTopoNode = nodeId
  if (nodeId) highlightNode(nodeId)
  else clearNodeHighlight()
}

function onCanvasPointerLeave() {
  hoveredTopoNode = ''
  clearNodeHighlight()
}

// 删除连线统一入口：双击（仅拖拽连线模式）和链路详情按钮都必须二次确认
async function removeConnection(connectionId, edge = null) {
  if (!connectionId) return
  const sourceLabel = edge?.getSourceCell?.()?.getData?.()?.node?.label
  const targetLabel = edge?.getTargetCell?.()?.getData?.()?.node?.label
  const linkName = sourceLabel && targetLabel ? `${sourceLabel} → ${targetLabel}` : ''
  try {
    await ElMessageBox.confirm(
      linkName
        ? `确定删除「${linkName}」这条连线吗？删除后不可恢复。`
        : '确定删除这条连线吗？删除后不可恢复。',
      '删除连线',
      { type: 'warning', confirmButtonText: '删除连线', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await topologyApi.deleteConnection(connectionId)
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || t('topology.deleteFailed'))
    return
  }
  const graphEdge = edge
    || graph?.getEdges().find((item) => item.getData()?.connectionId === connectionId)
  if (graphEdge && graph) graph.removeEdge(graphEdge)
  if (selectedEdge.value && selectedEdge.value.connection_id === connectionId) selectedEdge.value = null
  ElMessage.success(t('topology.connectionDeleted'))
  await loadTopology(false)
}

function cloudLinkCloudEndpoint(link) {
  const endpoint = String(link?.source || '').startsWith('cloud_') ? link.source : link.target
  return nodeById(endpoint)
}

function cloudLinkDeviceEndpoint(link) {
  const endpoint = String(link?.source || '').startsWith('device_') ? link.source : link.target
  return nodeById(endpoint)
}

function cloudLinkInterface(link) {
  return String(link?.source || '').startsWith('device_')
    ? link.source_interface
    : link.target_interface
}

function cloudDefaultPosition() {
  const devices = allNodes.value.filter((node) => !node.is_cloud && node.device_id)
  if (devices.length) {
    const layout = layoutNodes(devices)
    const positions = layout.positions || {}
    const boxes = devices.map((node) => {
      const fallback = positions[node.id] || { x: 72, y: 92 }
      const hasSaved = node.x !== null && node.x !== undefined && node.y !== null && node.y !== undefined
      return {
        x: hasSaved ? Number(node.x) : fallback.x,
        y: hasSaved ? Number(node.y) : fallback.y,
        width: nodeWidth(node),
        height: nodeHeight(node),
      }
    })
    const minX = Math.min(...boxes.map((box) => box.x))
    const maxRight = Math.max(...boxes.map((box) => box.x + box.width))
    const minY = Math.min(...boxes.map((box) => box.y))
    return {
      x: Math.round((minX + maxRight) / 2 - NODE_WIDTH / 2),
      // 位于所有真实设备上方，留出 40px 间距
      y: Math.round(minY - NODE_HEIGHT - 40),
    }
  }
  const rect = containerRef.value?.getBoundingClientRect()
  if (rect) {
    const center = clientToLocalPoint(rect.left + rect.width / 2, rect.top + rect.height / 2)
    return {
      x: Math.round(center.x - NODE_WIDTH / 2),
      y: Math.round(center.y - NODE_HEIGHT / 2),
    }
  }
  return { x: 120, y: 120 }
}

function addCloudNode() {
  if (!editMode.value || !graph) return
  const cloudId = nextCloudNodeId()
  const { x, y } = cloudDefaultPosition()
  const node = normalizeCloudNode({
    id: `cloud_${cloudId}`,
    cloud_id: cloudId,
    label: '互联网出口',
    x,
    y,
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
  })
  if (!node) return
  cloudNodes.value.push(node)
  dirty.value = true
  selectedEdge.value = null
  selectedNode.value = node
  applyScaleView()
  highlightNode(node.id)
  ElMessage.success('已添加云出口节点，拖动调整位置后点击「保存布局」持久化')
}

async function renameCloudNode(node) {
  if (!node?.is_cloud || !editMode.value) return
  try {
    const { value } = await ElMessageBox.prompt(
      '输入云出口名称（仅保存在拓扑布局，不会创建资产）',
      '重命名云出口',
      {
        inputValue: node.label || '互联网出口',
        inputPattern: /^.{1,60}$/s,
        inputErrorMessage: '名称长度需为 1~60 个字符',
        confirmButtonText: '确定',
        cancelButtonText: '取消',
      },
    )
    const label = String(value || '').trim()
    if (!label) return
    node.label = label
    dirty.value = true
    applyScaleView()
    ElMessage.success('云出口已重命名，点击「保存布局」持久化')
  } catch {
    /* 用户取消 */
  }
}

async function deleteCloudNode(node) {
  if (!node?.is_cloud) return
  const relatedLinks = cloudLinks.value.filter(
    (link) => link.source === node.id || link.target === node.id,
  )
  try {
    await ElMessageBox.confirm(
      `确定删除云出口「${node.label}」吗？该拓扑虚拟节点及其 ${relatedLinks.length} 条出口链路会一并删除，不会删除任何设备资产。`,
      '删除云节点',
      { type: 'warning', confirmButtonText: '删除云节点', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  cloudLinks.value = cloudLinks.value.filter((link) => link.source !== node.id && link.target !== node.id)
  cloudNodes.value = cloudNodes.value.filter((item) => item.id !== node.id)
  sizeNodeIds.value = sizeNodeIds.value.filter((nodeId) => nodeId !== node.id)
  if (selectedNode.value?.id === node.id) selectedNode.value = null
  if (selectedEdge.value && (selectedEdge.value.source === node.id || selectedEdge.value.target === node.id)) {
    selectedEdge.value = null
  }
  dirty.value = true
  applyScaleView()
  ElMessage.success('已删除云出口节点，点击「保存布局」持久化')
}

async function loadCloudLinkInterfaces(deviceId) {
  cloudLinkInterfaces.value = []
  if (!deviceId) return
  const cached = interfaceCache.get(Number(deviceId))
  if (cached) {
    cloudLinkInterfaces.value = cached.items
    if (Date.now() - cached.at < INTERFACE_CACHE_TTL) {
      cloudLinkIfLoading.value = false
      return
    }
  }
  cloudLinkIfLoading.value = true
  try {
    cloudLinkInterfaces.value = await fetchDeviceInterfaces(deviceId)
  } catch {
    if (!cached) cloudLinkInterfaces.value = []
  } finally {
    cloudLinkIfLoading.value = false
  }
}

function openCloudLinkDialog(node, presetDeviceId = null) {
  if (!node?.is_cloud) return
  cloudLinkForm.cloud_node_id = node.cloud_id
  cloudLinkForm.cloud_label = node.label || '互联网出口'
  cloudLinkForm.device_id = presetDeviceId || null
  cloudLinkForm.interface = ''
  cloudLinkInterfaces.value = []
  cloudLinkDialogVisible.value = true
  if (presetDeviceId) loadCloudLinkInterfaces(presetDeviceId)
}

function onCloudLinkDeviceChange(deviceId) {
  cloudLinkForm.interface = ''
  loadCloudLinkInterfaces(deviceId)
}

function submitCloudLink() {
  const cloudNode = cloudNodes.value.find(
    (node) => Number(node.cloud_id) === Number(cloudLinkForm.cloud_node_id),
  )
  if (!cloudNode) {
    ElMessage.warning('云节点不存在，请刷新拓扑后重试')
    return
  }
  if (!cloudLinkForm.device_id) {
    ElMessage.warning('请选择出口设备')
    return
  }
  const target = `device_${cloudLinkForm.device_id}`
  const exists = cloudLinks.value.some(
    (link) => (link.source === cloudNode.id && link.target === target)
      || (link.target === cloudNode.id && link.source === target),
  )
  if (exists) {
    ElMessage.warning('该云节点与设备之间已存在出口链路')
    return
  }
  const linkId = nextCloudLinkId()
  cloudLinks.value.push({
    id: `cloudlink_${linkId}`,
    cloud_link_id: linkId,
    connection_id: null,
    is_cloud_link: true,
    cloud_link: true,
    source: cloudNode.id,
    target,
    source_interface: '',
    target_interface: String(cloudLinkForm.interface || ''),
  })
  dirty.value = true
  cloudLinkDialogVisible.value = false
  applyScaleView()
  ElMessage.success('已添加云出口链路，点击「保存布局」持久化')
}

async function removeCloudLink(linkId, edge = null) {
  const link = cloudLinks.value.find(
    (item) => String(item.cloud_link_id) === String(linkId) || item.id === linkId,
  )
  if (!link) return
  const cloudLabel = cloudLinkCloudEndpoint(link)?.label || '互联网出口'
  const deviceLabel = cloudLinkDeviceEndpoint(link)?.label || link.target
  try {
    await ElMessageBox.confirm(
      `确定删除云出口「${cloudLabel}」到「${deviceLabel}」的出口链路吗？删除后点击「保存布局」生效。`,
      '删除云出口链路',
      { type: 'warning', confirmButtonText: '删除链路', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  cloudLinks.value = cloudLinks.value.filter((item) => item !== link)
  if (selectedEdge.value?.id === link.id) selectedEdge.value = null
  dirty.value = true
  applyScaleView()
  ElMessage.success('已删除云出口链路，点击「保存布局」持久化')
  if (edge && graph) {
    try {
      graph.removeEdge(edge)
    } catch {
      /* render 已重建画布 */
    }
  }
}

function deleteSelectedEdge() {
  const edge = selectedEdge.value
  if (!edge) return
  if (edge.is_cloud_link) {
    removeCloudLink(edge.cloud_link_id)
    return
  }
  if (edge.connection_id) removeConnection(edge.connection_id)
}

// ==================== 画布自适应 / 编辑模式 ====================
async function requestPageFullscreen() {
  if (!viewRef.value || !document.fullscreenEnabled) return false
  try {
    await viewRef.value.requestFullscreen()
    return !!document.fullscreenElement
  } catch {
    return false
  }
}

function refreshFullscreenCanvas() {
  window.setTimeout(() => {
    resizeGraphToContainer()
    fitView()
  }, 220)
}

async function enterEditFullscreen() {
  if (!canEdit.value) return
  mode.value = 'edit'
  editTool.value = 'move'
  applyMode()
  if (!fullscreenActive.value) {
    const ok = await requestPageFullscreen()
    if (!ok) {
      pseudoFullscreen.value = true
      ElMessage.info('浏览器未启用原生全屏，已切换为页面满屏编辑')
    }
  }
  refreshFullscreenCanvas()
}

async function toggleFullscreen() {
  if (pseudoFullscreen.value) {
    pseudoFullscreen.value = false
    refreshFullscreenCanvas()
    return
  }
  if (!document.fullscreenElement) {
    const ok = await requestPageFullscreen()
    if (!ok) {
      pseudoFullscreen.value = true
      refreshFullscreenCanvas()
    }
  } else {
    try {
      await document.exitFullscreen()
    } catch {
      /* 浏览器不允许时忽略 */
    }
  }
}

function onFullscreenChange() {
  isFullscreen.value = !!document.fullscreenElement
  refreshFullscreenCanvas()
}

function resizeGraphToContainer() {
  const el = containerRef.value
  if (!graph || !el) return false
  const width = el.clientWidth
  const height = el.clientHeight
  if (!width || !height) return false
  // 显式传入容器尺寸，避免 X6 继续使用初始化时的旧宽高
  graph.resize(width, height)
  return true
}

function fitView() {
  if (!graph) return
  const nodesAll = graph.getNodes()
  if (!nodesAll.length) return
  const el = containerRef.value
  if (!el || !el.clientWidth || !el.clientHeight) return
  try {
    // 先按当前容器尺寸重算画布，再让全部节点适配视口
    resizeGraphToContainer()
    const padding = Math.max(20, Math.min(56, Math.round(el.clientWidth * 0.025)))
    graph.zoomToFit({ padding, maxScale: 1.45, minScale: 0.1 })
    graph.centerContent()
  } catch {
    graph.centerContent()
  }
}

function scheduleCanvasFit(delay = 180) {
  if (resizeTimer) clearTimeout(resizeTimer)
  resizeTimer = setTimeout(() => {
    if (!graph) return
    resizeGraphToContainer()
    // 等 X6 完成一次布局后再计算节点包围盒，避免窗口缩小时沿用旧视口
    setTimeout(fitView, 60)
  }, delay)
}

function onWindowResize() {
  scheduleCanvasFit(140)
  setTimeout(() => scheduleCanvasFit(60), 360)
}

function nodeLinkCount(nodeId) {
  return edges.value.filter((edge) => edge.source === nodeId || edge.target === nodeId).length
}

function cellContainer(cell) {
  try {
    return graph?.findViewByCell(cell)?.container || null
  } catch {
    return null
  }
}

function highlightNode(nodeId) {
  if (!graph) return
  const related = new Set([nodeId])
  edges.value.forEach((edge) => {
    if (edge.source === nodeId) related.add(edge.target)
    if (edge.target === nodeId) related.add(edge.source)
  })
  graph.getNodes().forEach((node) => {
    if (!node.getData()?.node) return
    const container = cellContainer(node)
    if (!container) return
    container.style.transition = 'opacity .18s ease'
    container.style.opacity = related.has(node.id) ? '1' : '0.16'
  })
  graph.getEdges().forEach((edge) => {
    const container = cellContainer(edge)
    if (!container) return
    const connected = edge.getSourceCellId() === nodeId || edge.getTargetCellId() === nodeId
    container.style.transition = 'opacity .18s ease'
    container.style.opacity = connected ? '1' : '0.1'
  })
}

function clearNodeHighlight() {
  if (!graph) return
  if (selectedNode.value) {
    highlightNode(selectedNode.value.id)
    return
  }
  graph.getNodes().forEach((node) => {
    if (!node.getData()?.node) return
    const container = cellContainer(node)
    if (container) container.style.opacity = '1'
  })
  graph.getEdges().forEach((edge) => {
    const container = cellContainer(edge)
    if (container) container.style.opacity = '1'
  })
}

function focusOnNode(nodeId) {
  if (!graph) return
  const cell = graph.getCellById(nodeId)
  if (!cell) return
  try {
    graph.centerCell(cell)
    if (graph.zoom() < 0.85) graph.zoomTo(0.95)
  } catch {
    graph.centerContent()
  }
}

function locateNode(deviceId) {
  if (!deviceId) return
  const node = nodes.value.find((item) => item.device_id === deviceId)
  if (!node) return
  selectedNode.value = node
  selectedEdge.value = null
  focusOnNode(node.id)
  highlightNode(node.id)
}

function closeNodePanel() {
  selectedNode.value = null
  locateNodeId.value = null
  clearNodeHighlight()
}

function openNodeDevice(node) {
  if (node?.device_id) router.push(`/devices/${node.device_id}`)
}

function resetDeviceForm() {
  Object.assign(deviceForm, {
    name: '',
    ip_address: '',
    device_type: 'switch',
    vendor: '',
    model: '',
    location: '',
    snmp_version: 'v2c',
    community: 'public',
    port: 161,
    is_enabled: true,
  })
}

async function loadAssetOptions() {
  assetOptionsLoading.value = true
  try {
    const all = []
    let page = 1
    let total = 0
    do {
      const { data } = await assetApi.getList({ page, size: 100 })
      const items = data.items || []
      all.push(...items)
      total = Number(data.total || all.length)
      if (!items.length) break
      page += 1
    } while (all.length < total && page <= 10)
    assetOptions.value = all
  } catch (error) {
    assetOptions.value = []
    ElMessage.error(error.message || '加载资产列表失败')
  } finally {
    assetOptionsLoading.value = false
  }
}

async function openCreateDevice() {
  editingDeviceId.value = null
  selectedAssetId.value = null
  newDeviceIcon.value = ''
  resetDeviceForm()
  deviceDialogVisible.value = true
  await loadAssetOptions()
}

function onAssetSelected() {
  newDeviceIcon.value = selectedAsset.value?.icon || ''
}

function applyNewDeviceIcon(url) {
  newDeviceIcon.value = url || ''
  newIconPickerVisible.value = false
}

function openNodeIconPicker(node) {
  if (!node?.device_id) return
  iconPickerDeviceId.value = node.device_id
  iconPickerVisible.value = true
}

async function addExistingAsset() {
  if (!selectedAsset.value) {
    ElMessage.warning('请从资产库选择设备')
    return
  }
  const asset = selectedAsset.value
  const iconChanged = !!newDeviceIcon.value && newDeviceIcon.value !== asset.icon
  if (selectedAssetInTopology.value) {
    if (iconChanged) {
      try {
        await assetApi.update(asset.id, { icon: newDeviceIcon.value })
        const targetNode = nodes.value.find((node) => node.device_id === asset.id)
        if (targetNode) targetNode.icon = newDeviceIcon.value
        render()
      } catch (error) {
        ElMessage.error(error.message || '更新图标失败')
        return
      }
    }
    deviceDialogVisible.value = false
    const targetNode = nodes.value.find((node) => node.device_id === asset.id)
    if (targetNode) {
      selectedNode.value = targetNode
      locateNodeId.value = targetNode.device_id
      focusOnNode(targetNode.id)
    }
    ElMessage.info('该资产已在拓扑中，已为你定位')
    return
  }
  if (asset.is_enabled === false) {
    try {
      await ElMessageBox.confirm(
        `资产「${asset.name}」当前未启用监控。\n加入拓扑会同时启用该资产的监控并开始采集，是否继续？`,
        '启用并加入拓扑',
        { type: 'warning', confirmButtonText: '启用并添加', cancelButtonText: '取消' },
      )
    } catch {
      return
    }
  }
  deviceSaving.value = true
  try {
    const payload = {}
    if (iconChanged) payload.icon = newDeviceIcon.value
    if (asset.is_enabled === false) payload.is_enabled = true
    if (Object.keys(payload).length) await assetApi.update(asset.id, payload)
    deviceDialogVisible.value = false
    selectedNode.value = null
    await loadTopology(true)
    const targetNode = nodes.value.find((node) => node.device_id === asset.id)
    if (targetNode) {
      selectedNode.value = targetNode
      locateNodeId.value = targetNode.device_id
      focusOnNode(targetNode.id)
      ElMessage.success('资产已加入拓扑')
    } else {
      ElMessage.warning('资产已启用，但当前拓扑不可见，请检查资产群组权限')
    }
    setTimeout(fitView, 100)
  } catch (error) {
    ElMessage.error(error.message || '加入拓扑失败')
  } finally {
    deviceSaving.value = false
  }
}

async function openEditDevice(node) {
  if (!node?.device_id) return
  editingDeviceId.value = node.device_id
  resetDeviceForm()
  try {
    const { data } = await assetApi.getOne(node.device_id)
    Object.assign(deviceForm, {
      name: data.name || node.label || '',
      ip_address: data.ip_address || node.ip_address || '',
      device_type: data.device_type || node.device_type || 'switch',
      vendor: data.vendor || node.vendor || '',
      model: data.model || node.model || '',
      location: data.location || node.location || '',
      snmp_version: data.snmp_version || 'v2c',
      community: data.community || 'public',
      port: Number(data.port || 161),
      is_enabled: data.is_enabled !== false,
    })
  } catch (error) {
    ElMessage.error(error.message || '加载设备信息失败')
    return
  }
  deviceDialogVisible.value = true
}

async function saveDevice() {
  if (!deviceForm.name.trim() || !deviceForm.ip_address.trim()) {
    ElMessage.warning('请填写设备名称和 IP 地址')
    return
  }
  if (!/^(\d{1,3}\.){3}\d{1,3}$/.test(deviceForm.ip_address.trim())) {
    ElMessage.warning('请输入合法的 IPv4 地址')
    return
  }
  if (!deviceForm.device_type) {
    ElMessage.warning('请选择设备类型')
    return
  }
  deviceSaving.value = true
  try {
    const payload = {
      name: deviceForm.name.trim(),
      ip_address: deviceForm.ip_address.trim(),
      device_type: deviceForm.device_type,
      vendor: deviceForm.vendor.trim(),
      model: deviceForm.model.trim(),
      location: deviceForm.location.trim(),
      snmp_version: deviceForm.snmp_version,
      community: deviceForm.community,
      port: Number(deviceForm.port || 161),
      is_enabled: deviceForm.is_enabled,
    }
    if (editingDeviceId.value) {
      await assetApi.update(editingDeviceId.value, payload)
      ElMessage.success('设备已更新')
    } else {
      ElMessage.warning('请从现有资产中选择设备')
      return
    }
    deviceDialogVisible.value = false
    selectedNode.value = null
    await loadTopology(true)
    setTimeout(fitView, 100)
  } catch (error) {
    ElMessage.error(error.message || '保存设备失败')
  } finally {
    deviceSaving.value = false
  }
}

async function deleteSelectedDevices() {
  const selected = sizeNodeIds.value
    .map((nodeId) => nodes.value.find((node) => node.id === nodeId))
    .filter((node) => node?.device_id)
  if (!selected.length) return
  const names = selected.slice(0, 5).map((node) => node.label).join('、')
  try {
    await ElMessageBox.confirm(
      `确定删除选中的 ${selected.length} 台设备吗？${names}${selected.length > 5 ? ' 等' : ''}。删除后拓扑链路也会一并清理。`,
      '批量删除设备',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  let deleted = 0
  const failed = []
  for (const node of selected) {
    try {
      await assetApi.delete(node.device_id)
      deleted += 1
    } catch (error) {
      failed.push(`${node.label}: ${error?.response?.data?.detail || error?.message || '删除失败'}`)
    }
  }
  clearSizeSelection()
  selectedNode.value = null
  if (deleted) {
    ElMessage.success(`已删除 ${deleted} 台设备`)
    await loadTopology(true)
    setTimeout(fitView, 100)
  }
  if (failed.length) {
    ElMessage.error(failed[0])
  }
}

async function deleteDevice(node) {
  if (!node?.device_id) return
  try {
    await ElMessageBox.confirm(
      `确定删除设备“${node.label}”吗？删除后该设备的拓扑链路也会一并清理。`,
      '删除设备',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
    await assetApi.delete(node.device_id)
    selectedNode.value = null
    ElMessage.success('设备已删除')
    await loadTopology(true)
    setTimeout(fitView, 100)
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(error.message || '删除设备失败')
    }
  }
}

function zoomBy(delta) {
  if (!graph) return
  const next = Math.max(0.25, Math.min(2.4, graph.zoom() + delta))
  graph.zoomTo(next)
}

function applyMode() {
  if (!graph) return
  applyEditTool()
  const el = containerRef.value
  if (el) {
    el.classList.toggle('edit-mode', editMode.value)
  }
  // 编辑模式进入时取消重新适配，保持当前视角
  if (editMode.value) dirty.value = false
}

async function saveLayout() {
  if (!editMode.value || !graph) return
  const devicePayload = graph
    .getNodes()
    .map((node) => ({
      device_id: node.getData()?.deviceId,
      x: Math.round(node.position().x),
      y: Math.round(node.position().y),
      width: Math.round(node.getSize().width),
      height: Math.round(node.getSize().height),
    }))
    .filter((item) => item.device_id)
  const cloudNodePayload = graph
    .getNodes()
    .filter((node) => node.getData()?.node?.is_cloud)
    .map((node) => {
      const model = node.getData()?.node || {}
      return {
        id: Number(model.cloud_id),
        label: model.label || '互联网出口',
        x: Math.round(node.position().x),
        y: Math.round(node.position().y),
        width: Math.round(node.getSize().width),
        height: Math.round(node.getSize().height),
      }
    })
    .filter((item) => Number.isFinite(item.id) && item.id > 0)
  const edgePayload = []
  const graphEdgeIds = new Set()
  graph.getEdges()
    .filter((edge) => edge.getData()?.connectionId)
    .forEach((edge) => {
      const connectionId = edge.getData()?.connectionId
      graphEdgeIds.add(String(connectionId))
      const offset = edge.getData()?.edgeOffset || {}
      const labelOffset = edge.getData()?.labelOffset || {}
      edgePayload.push({
        connection_id: connectionId,
        source_device_id: edge.getSourceCell()?.getData()?.deviceId,
        dest_device_id: edge.getTargetCell()?.getData()?.deviceId,
        offset_x: Number(offset.x || 0),
        offset_y: Number(offset.y || 0),
        label_offset_x: Number(labelOffset.x || 0),
        label_offset_y: Number(labelOffset.y || 0),
        source_anchor: edge.getData()?.sourceAnchor || null,
        dest_anchor: edge.getData()?.destAnchor || null,
      })
    })
  // 连线数据兜底：当前画布未渲染但模型里仍存在的设备连线也写入保存请求。
  // 这里不携带端点信息，避免把已有连线误改接，只同步偏移与锚点。
  edges.value.forEach((edge) => {
    if (!edge.connection_id || graphEdgeIds.has(String(edge.connection_id))) return
    const item = {
      connection_id: edge.connection_id,
      offset_x: Number(edge.edge_offset?.x || 0),
      offset_y: Number(edge.edge_offset?.y || 0),
      label_offset_x: Number(edge.edge_label_offset?.x || 0),
      label_offset_y: Number(edge.edge_label_offset?.y || 0),
    }
    if (edge.source_anchor) item.source_anchor = edge.source_anchor
    if (edge.dest_anchor) item.dest_anchor = edge.dest_anchor
    edgePayload.push(item)
  })
  const cloudLinkPayload = cloudLinks.value
    .map((link) => ({
      id: Number(link.cloud_link_id),
      source: link.source,
      target: link.target,
      source_interface: link.source_interface || '',
      target_interface: link.target_interface || '',
    }))
    .filter((link) => Number.isFinite(link.id) && link.id > 0)
  savingLayout.value = true
  try {
    const res = await topologyApi.saveLayout({
      nodes: devicePayload,
      edges: edgePayload,
      cloud_nodes: cloudNodePayload,
      cloud_links: cloudLinkPayload,
    })
    dirty.value = false
    ElMessage.success(res.data.message || t('topology.layoutSaved'))
  } catch (e) {
    ElMessage.error(e.message || t('topology.saveLayoutFailed'))
  } finally {
    savingLayout.value = false
  }
}

async function discardLayoutChanges() {
  if (!editMode.value || discardingLayout.value) return
  try {
    await ElMessageBox.confirm(
      '确定放弃本次未保存的布局更改吗？节点位置、设备尺寸和连线偏移将恢复为后端已保存的状态。',
      '取消更改',
      { type: 'warning', confirmButtonText: '放弃更改', cancelButtonText: '继续编辑' },
    )
  } catch {
    return
  }
  discardingLayout.value = true
  try {
    const ok = await loadTopology(true, { preserveDirty: false })
    if (ok === false) {
      ElMessage.error('取消更改失败，未保存的布局仍保留')
      return
    }
    clearSizeSelection()
    dirty.value = false
    ElMessage.success('已放弃未保存的更改，布局已恢复')
  } catch (error) {
    ElMessage.error(error.message || '取消更改失败')
  } finally {
    discardingLayout.value = false
  }
}

async function resetLayout() {
  try {
    await ElMessageBox.confirm(
      t('topology.resetLayoutConfirm'),
      t('topology.resetLayout'),
      { type: 'warning' }
    )
  } catch {
    return
  }
  savingLayout.value = true
  try {
    await topologyApi.saveLayout({ reset: true })
    needsFit = true
    dirty.value = false
    await loadTopology(true)
    ElMessage.success(t('topology.autoLayoutRestored'))
  } catch (e) {
    ElMessage.error(e.message || t('topology.resetLayoutFailed'))
  } finally {
    savingLayout.value = false
  }
}

function applyTrafficVisibility() {
  render()
}

// ==================== 数据 ====================
async function loadTopology(showLoading = true, { preserveDirty = true } = {}) {
  if (showLoading) loading.value = true
  try {
    const localLayouts = new Map(
      (allNodes.value.length ? allNodes.value : nodes.value)
        .filter((n) => !n.is_cloud && n.device_id)
        .filter((n) => n.x !== null && n.x !== undefined && n.y !== null && n.y !== undefined)
        .map((n) => [n.device_id, {
          x: n.x,
          y: n.y,
          width: n.width,
          height: n.height,
        }])
    )
    const localCloudNodes = cloudNodes.value.map((node) => ({ ...node }))
    const localCloudLinks = cloudLinks.value.map((link) => ({ ...link }))
    const preserveLocal = dirty.value && preserveDirty
    const res = await topologyApi.getTopology()
    const fetched = res.data.nodes || []
    // 编辑中未保存的拖动位置和自定义尺寸，刷新时保留本地值，避免被服务端覆盖
    if (preserveLocal) {
      fetched.forEach((n) => {
        const local = localLayouts.get(n.device_id)
        if (local) {
          n.x = local.x
          n.y = local.y
          if (local.width !== null && local.width !== undefined) n.width = local.width
          if (local.height !== null && local.height !== undefined) n.height = local.height
        }
      })
    }
    const fetchedCloudNodes = (res.data.cloud_nodes || []).map(normalizeCloudNode).filter(Boolean)
    const fetchedCloudLinks = (res.data.cloud_links || []).map(normalizeCloudLink).filter(Boolean)
    allNodes.value = fetched
    allEdges.value = res.data.edges || []
    cloudNodes.value = preserveLocal ? localCloudNodes : fetchedCloudNodes
    cloudLinks.value = preserveLocal ? localCloudLinks : fetchedCloudLinks
    if (fetched.length <= largeModeThreshold) activeScaleGroup.value = ''
    totalBps.value = res.data.total_bps || 0
    updatedAt.value = res.data.timestamp
    // 刷新时同步链路详情面板
    if (selectedEdge.value) {
      const previous = selectedEdge.value
      selectedEdge.value = previous.is_cloud_link
        ? cloudLinks.value.find((link) => link.cloud_link_id === previous.cloud_link_id) || null
        : allEdges.value.find((edge) => edge.connection_id === previous.connection_id) || null
    }
    if (selectedNode.value) {
      const previous = selectedNode.value
      selectedNode.value = previous.is_cloud
        ? cloudNodes.value.find((node) => node.id === previous.id) || null
        : allNodes.value.find((node) => node.device_id === previous.device_id) || null
      locateNodeId.value = selectedNode.value?.device_id || null
    }
    applyScaleView()
    return true
  } catch (e) {
    ElMessage.error(e.message || t('topology.loadTopologyFailed'))
    return false
  } finally {
    loading.value = false
  }
}

async function autoDiscover() {
  discovering.value = true
  try {
    const res = await topologyApi.discover()
    ElMessage.success(res.data.message || t('topology.autoDiscoverDone'))
    await loadTopology(true)
  } catch (e) {
    ElMessage.error(e.message || t('topology.autoDiscoverFailed'))
  } finally {
    discovering.value = false
  }
}

async function submitConnection() {
  if (!form.source_device_id || !form.dest_device_id) {
    ElMessage.warning(t('topology.selectBothDevices'))
    return
  }
  if (form.source_device_id === form.dest_device_id) {
    ElMessage.warning(t('topology.sameDeviceNotAllowed'))
    return
  }
  try {
    await topologyApi.addConnection({
      ...form,
      source_anchor: connectionAnchors.value.source,
      dest_anchor: connectionAnchors.value.dest,
    })
    ElMessage.success(t('topology.connectionAdded'))
    dialogVisible.value = false
    await loadTopology(true)
  } catch (e) {
    ElMessage.error(e.message || t('topology.addFailed'))
  }
}

async function loadSharedAccess() {
  const sharedId = Number(route.query.shared)
  if (!sharedId) return
  try {
    const res = await sharingApi.resource(sharedId)
    const item = res.data?.resource
    if (!item || item.resource_type !== 'topology') {
      ElMessage.error('该共享资源不是拓扑图')
      return
    }
    sharedResource.value = item
    if (!item.can_edit) mode.value = 'view'
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '共享拓扑加载失败')
  }
}

async function requestSharedEdit() {
  if (!sharedResource.value) return
  try {
    await sharingApi.requestEdit(sharedResource.value.id)
    sharedResource.value = { ...sharedResource.value, pending_request: { status: 'pending' } }
    ElMessage.success('编辑申请已提交，等待共享者审批')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || error.message || '提交编辑申请失败')
  }
}

watch(() => route.query.shared, (value) => {
  if (value) loadSharedAccess()
  else sharedResource.value = null
})

function onTopologyVisibility() {
  if (document.hidden) return
  if (autoRefresh.value && !editMode.value && !dirty.value) loadTopology(false)
}

onMounted(() => {
  initGraph()
  loadSharedAccess()
  containerRef.value?.addEventListener('mousemove', onCanvasPointerMove)
  containerRef.value?.addEventListener('mouseleave', onCanvasPointerLeave)
  containerRef.value?.addEventListener('mousedown', onFlowLabelMouseDown, true)
  loadTopology(true)
  document.addEventListener('fullscreenchange', onFullscreenChange)
  window.addEventListener('keydown', onTopologyKeydown)
  refreshTimer = setInterval(() => {
    // 编辑期间暂停自动刷新，避免拖拽中的节点、未保存的尺寸被服务端数据覆盖
    if (autoRefresh.value && !editMode.value && !dirty.value) loadTopology(false)
  }, 3000)
  document.addEventListener('visibilitychange', onTopologyVisibility)
  window.addEventListener('focus', onTopologyVisibility)

  // 容器尺寸变化时自适应（窗口缩放/侧边栏折叠等）
  if (containerRef.value && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => scheduleCanvasFit(180))
    resizeObserver.observe(containerRef.value)
  }
  window.addEventListener('resize', onWindowResize)
})

onBeforeUnmount(() => {
  if (refreshTimer) clearInterval(refreshTimer)
  document.removeEventListener('visibilitychange', onTopologyVisibility)
  window.removeEventListener('focus', onTopologyVisibility)
  if (resizeTimer) clearTimeout(resizeTimer)
  window.removeEventListener('resize', onWindowResize)
  window.removeEventListener('keydown', onTopologyKeydown)
  containerRef.value?.removeEventListener('mousemove', onCanvasPointerMove)
  containerRef.value?.removeEventListener('mouseleave', onCanvasPointerLeave)
  containerRef.value?.removeEventListener('mousedown', onFlowLabelMouseDown, true)
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  cleanupConnectDrag()
  cleanupEdgeDrag()
  cleanupFlowLabelDrag()
  resizeObserver?.disconnect()
  graph?.dispose()
})
</script>

<style>
@keyframes topo-dash {
  to {
    stroke-dashoffset: -28;
  }
}

.if-hint {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.4;
  color: #909399;
}

/* X6 动态节点没有 Vue 的 scoped 属性，选中/吸附样式必须放在全局块 */
.x6-node.topo-connect-target .topo-compact-node {
  border-color: #22d3ee !important;
  box-shadow: 0 0 0 3px rgba(34, 211, 238, 0.25), 0 0 22px rgba(34, 211, 238, 0.42) !important;
}

.topo-cloud-node {
  border-style: dashed !important;
}

.x6-node.topo-size-selected .topo-compact-node {
  outline: 2px solid #38bdf8;
  outline-offset: 2px;
  box-shadow: 0 0 0 4px rgba(56, 189, 248, 0.2), 0 8px 24px rgba(0, 0, 0, 0.4) !important;
}

.topo-selected-badge {
  position: absolute;
  top: 4px;
  left: 4px;
  z-index: 20;
  padding: 1px 4px;
  border-radius: 7px;
  background: #38bdf8;
  color: #082f49;
  font-size: 9px;
  font-weight: 700;
  line-height: 13px;
  white-space: nowrap;
  pointer-events: none;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.35);
}

.topo-anchor-dot {
  position: absolute;
  z-index: 30;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #0b1220;
  border: 1.5px solid #38bdf8;
  box-shadow: 0 0 5px rgba(56, 189, 248, 0.75);
  transform: translate(-50%, -50%);
  pointer-events: none;
  transition: width 0.12s ease, height 0.12s ease, background 0.12s ease;
}

.topo-anchor-dot.active {
  width: 11px;
  height: 11px;
  background: #38bdf8;
  border-color: #e0f2fe;
}

.topology-container.topo-connect-mode .x6-node,
.topology-container.topo-connecting {
  cursor: crosshair !important;
}

.topology-container.edit-mode .x6-edge {
  cursor: grab;
}

.topology-container.edit-mode .x6-edge-label {
  cursor: move;
}

.topology-container .x6-edge.edge-moving {
  cursor: grabbing;
}

.topology-container .x6-edge.flow-label-dragging path {
  stroke: #fbbf24 !important;
  stroke-width: 2.3px !important;
  filter: drop-shadow(0 0 5px rgba(251, 191, 36, 0.75));
}

.edge-reset-btn,
.edge-delete-btn {
  width: 100%;
  margin-top: 8px;
}
</style>

<style scoped>
.topology-view {
  height: calc(100vh - 104px);
  height: calc(100dvh - 104px);
  min-height: 620px;
  position: relative;
  display: flex;
  flex-direction: column;
}

.topology-view > .el-card {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.topology-view :deep(.el-card__body) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 600;
}

.updated {
  font-size: 12px;
  color: #94a3b8;
  font-weight: 400;
}

.actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.topology-stage {
  position: relative;
  flex: 1;
  height: auto;
  min-height: 420px;
  border-radius: 12px;
  overflow: hidden;
  background:
    radial-gradient(ellipse at 50% 0%, rgba(14, 116, 144, 0.12), transparent 62%),
    #0b1220;
  box-shadow: inset 0 0 0 1px rgba(56, 189, 248, 0.08);
}

.topology-container {
  width: 100% !important;
  height: 100% !important;
  min-height: 0;
  background: #0b1220;
  overflow: hidden;
}

.topo-scale-filterbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
  padding: 8px 10px;
  border: 1px solid rgba(56, 189, 248, 0.16);
  border-radius: 9px;
  background: rgba(6, 20, 35, 0.82);
}

.scale-badge {
  margin-right: 4px;
  padding: 3px 8px;
  border: 1px solid rgba(251, 191, 36, 0.38);
  border-radius: 5px;
  color: #fbbf24;
  background: rgba(251, 191, 36, 0.08);
  font-size: 10px;
  white-space: nowrap;
}

.scale-filtered {
  margin-left: auto;
  color: #7796a8;
  font-family: Consolas, monospace;
  font-size: 10px;
}

.topo-scale-overview {
  position: absolute;
  z-index: 8;
  top: 58px;
  right: 18px;
  bottom: 18px;
  left: 18px;
  padding: 14px;
  overflow: auto;
  border: 1px solid rgba(56, 189, 248, 0.2);
  border-radius: 10px;
  background: rgba(4, 14, 27, 0.94);
  backdrop-filter: blur(8px);
}

.topo-scale-overview-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 14px;
}

.topo-scale-overview-head strong {
  display: block;
  color: #d9f3ff;
  font-size: 15px;
}

.topo-scale-overview-head span {
  display: block;
  margin-top: 4px;
  color: #7192a6;
  font-size: 11px;
}

.topo-scale-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: 12px;
}

.topo-scale-card {
  position: relative;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 8px;
  padding: 14px;
  border: 1px solid color-mix(in srgb, var(--group-color) 38%, transparent);
  border-radius: 9px;
  color: #d9f3ff;
  background: linear-gradient(135deg, color-mix(in srgb, var(--group-color) 11%, transparent), rgba(6, 20, 35, 0.92));
  text-align: left;
  cursor: pointer;
  transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
}

.topo-scale-card:hover {
  transform: translateY(-2px);
  border-color: var(--group-color);
  box-shadow: 0 8px 22px color-mix(in srgb, var(--group-color) 16%, transparent);
}

.scale-card-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--group-color);
  box-shadow: 0 0 9px var(--group-color);
}

.topo-scale-card strong {
  overflow: hidden;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.topo-scale-card b {
  color: var(--group-color);
  font-family: Consolas, monospace;
  font-size: 13px;
}

.topo-scale-card small {
  grid-column: 2 / 4;
  display: flex;
  gap: 9px;
  color: #7d9bad;
  font-size: 9px;
}

.topo-scale-card small .online { color: #34d399; }
.topo-scale-card small .warning { color: #fbbf24; }
.topo-scale-card small .offline { color: #fb7185; }

.topo-scale-empty {
  grid-column: 1 / -1;
  padding: 32px;
  color: #6f8fa2;
  text-align: center;
  font-size: 12px;
}

.topo-scale-back {
  position: absolute;
  z-index: 7;
  top: 60px;
  left: 14px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 9px;
  border: 1px solid rgba(56, 189, 248, 0.2);
  border-radius: 7px;
  background: rgba(5, 16, 28, 0.9);
}

.topo-scale-back span {
  color: #8eafc2;
  font-size: 11px;
}

.topology-container.edit-mode {
  cursor: grab;
}

.topo-edit-tool {
  margin-right: 2px;
}

.topo-size-control {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-right: 4px;
  color: #94a3b8;
  font-size: 12px;
  white-space: nowrap;
}

.topo-size-control .el-input-number {
  width: 88px;
}

.flow-label-size {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #94a3b8;
  font-size: 12px;
  white-space: nowrap;
}

.flow-label-size .el-input-number {
  width: 78px;
}

.size-control-label {
  font-weight: 600;
  padding: 1px 5px;
  border-radius: 5px;
}

.device-size-color {
  color: #38bdf8;
  background: rgba(56, 189, 248, 0.12);
}

.flow-label-color {
  color: #fbbf24;
  background: rgba(251, 191, 36, 0.12);
}

.size-control-divider {
  width: 1px;
  height: 18px;
  margin: 0 2px;
  background: rgba(148, 163, 184, 0.35);
}

.device-size-field :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px rgba(56, 189, 248, 0.55) inset;
}

.flow-label-field :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px rgba(251, 191, 36, 0.6) inset;
}

.topo-size-tip {
  color: #64748b;
  font-size: 11px;
}

.topo-auto-refresh {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #94a3b8;
  font-size: 12px;
  line-height: 1;
  white-space: nowrap;
}

.x6-node.topo-size-selected .topo-compact-node {
  outline: 2px solid #38bdf8;
  outline-offset: 2px;
  box-shadow: 0 0 0 4px rgba(56, 189, 248, 0.2), 0 8px 24px rgba(0, 0, 0, 0.4) !important;
}

.topo-selected-badge {
  position: absolute;
  top: 4px;
  left: 4px;
  z-index: 20;
  padding: 1px 4px;
  border-radius: 7px;
  background: #38bdf8;
  color: #082f49;
  font-size: 9px;
  font-weight: 700;
  line-height: 13px;
  white-space: nowrap;
  pointer-events: none;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.35);
}

.topo-anchor-dot {
  position: absolute;
  z-index: 30;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #0b1220;
  border: 1.5px solid #38bdf8;
  box-shadow: 0 0 5px rgba(56, 189, 248, 0.75);
  transform: translate(-50%, -50%);
  pointer-events: none;
  transition: width 0.12s ease, height 0.12s ease, background 0.12s ease;
}

.topo-anchor-dot.active {
  width: 11px;
  height: 11px;
  background: #38bdf8;
  border-color: #e0f2fe;
}

.topology-container.topo-connect-mode,
.topology-container.topo-connect-mode .x6-node,
.topology-container.topo-connecting {
  cursor: crosshair !important;
}

.topology-container.edit-mode .x6-edge {
  cursor: grab;
}

.topology-container.edit-mode .x6-edge-label {
  cursor: move;
}

.topology-container .x6-edge.edge-moving {
  cursor: grabbing;
}

.topology-container .x6-edge.flow-label-dragging path {
  stroke: #fbbf24 !important;
  stroke-width: 2.3px !important;
  filter: drop-shadow(0 0 5px rgba(251, 191, 36, 0.75));
}

.edge-reset-btn,
.edge-delete-btn {
  width: 100%;
  margin-top: 8px;
}

.x6-node.topo-connect-target .topo-compact-node {
  border-color: #22d3ee !important;
  box-shadow: 0 0 0 3px rgba(34, 211, 238, 0.25), 0 0 22px rgba(34, 211, 238, 0.42) !important;
}

.x6-node.topo-smart-target .topo-compact-node {
  border-color: #fbbf24 !important;
  box-shadow: 0 0 0 3px rgba(251, 191, 36, 0.18), 0 0 22px rgba(251, 191, 36, 0.35) !important;
}

.topo-connect-suggestion {
  position: absolute;
  z-index: 80;
  width: 228px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  border: 1px solid rgba(56, 189, 248, 0.32);
  border-radius: 8px;
  background: rgba(5, 18, 33, 0.94);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
  pointer-events: none;
  backdrop-filter: blur(8px);
}

.topo-connect-suggestion.active {
  border-color: rgba(251, 191, 36, 0.55);
  box-shadow: 0 8px 26px rgba(251, 191, 36, 0.16);
}

.topo-connect-suggestion .suggestion-kicker {
  color: #38bdf8;
  font-family: Consolas, monospace;
  font-size: 9px;
  letter-spacing: 1px;
}

.topo-connect-suggestion.active .suggestion-kicker {
  color: #fbbf24;
}

.topo-connect-suggestion strong {
  overflow: hidden;
  color: #e0f2fe;
  font-size: 12px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.topo-connect-suggestion small {
  color: #94a3b8;
  font-size: 10px;
  line-height: 1.35;
}

.topology-container :deep(.topo-alert-badge) {
  animation: topo-alert-pulse 1.5s ease-in-out infinite;
}

@keyframes topo-alert-pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.18); opacity: 0.78; }
}

.topo-search {
  position: absolute;
  left: 14px;
  top: 14px;
  z-index: 6;
  width: 250px;
}

.topo-search-select :deep(.el-select__wrapper) {
  background: rgba(8, 22, 37, 0.92);
  box-shadow: 0 0 0 1px rgba(56, 189, 248, 0.22) inset, 0 8px 20px rgba(0, 0, 0, 0.25);
  backdrop-filter: blur(8px);
}

.topo-search-select :deep(.el-select__placeholder),
.topo-search-select :deep(.el-select__selected-item) {
  color: #b9d9e8;
  font-size: 11px;
}

.topo-search-select :deep(.el-input__prefix),
.topo-search-select :deep(.el-select__caret) {
  color: #5d8ba3;
}

.topo-zoom {
  position: absolute;
  right: 14px;
  top: 14px;
  z-index: 6;
  display: flex;
  gap: 6px;
}

.topo-zoom .el-button {
  margin: 0;
  background: rgba(8, 22, 37, 0.9);
  border-color: rgba(56, 189, 248, 0.2);
  color: #8fc7dd;
  backdrop-filter: blur(8px);
}

.topo-node-panel {
  position: absolute;
  right: 14px;
  top: 58px;
  z-index: 7;
  width: 264px;
  padding: 12px;
  border: 1px solid rgba(56, 189, 248, 0.3);
  border-radius: 12px;
  background: rgba(6, 20, 34, 0.94);
  color: #cfe8f4;
  box-shadow: 0 14px 34px rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(10px);
}

.topo-node-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  padding-bottom: 9px;
  border-bottom: 1px solid rgba(56, 189, 248, 0.12);
}

.topo-node-title {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  min-width: 0;
}

.topo-node-title i {
  width: 7px;
  height: 7px;
  margin-top: 4px;
  border-radius: 50%;
  flex-shrink: 0;
  box-shadow: 0 0 8px currentColor;
}

.topo-node-title strong {
  display: block;
  overflow: hidden;
  color: #e4f7ff;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.topo-node-title span {
  display: block;
  margin-top: 2px;
  color: #698da2;
  font-family: Consolas, monospace;
  font-size: 9px;
}

.topo-node-meta {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 9px;
  padding: 10px 0;
}

.topo-node-meta span {
  display: block;
  color: #55768a;
  font-size: 9px;
}

.topo-node-meta b {
  display: block;
  margin-top: 2px;
  overflow: hidden;
  color: #a9d2e2;
  font-size: 10px;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.topo-node-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding-top: 2px;
}

.topo-node-actions .el-button {
  margin: 0;
}

/* 全屏：工具栏 + 画布 + 图例铺满屏幕 */
.topology-view:fullscreen {
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  background: #f5f7fa;
  display: flex;
  flex-direction: column;
}

.topology-view:fullscreen > .el-card {
  flex: 1;
  width: 100%;
  min-height: 0;
  margin: 0;
  border-radius: 0;
  display: flex;
  flex-direction: column;
}

.topology-view:fullscreen :deep(.el-card__body) {
  flex: 1;
  width: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 14px 18px;
}

.topology-view:fullscreen .topology-stage {
  flex: 1;
  height: auto;
  min-height: 0;
  border-radius: 0;
}

.topology-view:fullscreen .topology-container {
  width: 100% !important;
  height: 100% !important;
  min-height: 0;
}

.topology-view:fullscreen .legend {
  flex-shrink: 0;
}

.topology-view:fullscreen .edge-panel {
  max-height: 60vh;
  overflow: auto;
}

.topology-view.is-fullscreen-edit :deep(.el-card__header) {
  padding: 8px 12px;
}

.topology-view.is-fullscreen-edit :deep(.el-card__body) {
  padding: 8px 12px 6px;
}

.topology-view.is-fullscreen-edit .edit-hint {
  display: none;
}

.topology-view.is-fullscreen-edit .topo-scale-filterbar {
  margin-bottom: 5px;
  padding: 5px 8px;
}

.topology-view.is-fullscreen-edit .topology-stage {
  min-height: 0;
  border-radius: 4px;
}

.topology-view.is-pseudo-fullscreen {
  position: fixed;
  inset: 0;
  z-index: 3000;
  width: 100vw;
  height: 100dvh;
  min-height: 0;
  margin: 0;
  background: #f5f7fa;
  overflow: hidden;
}

.topology-view.is-pseudo-fullscreen > .el-card {
  flex: 1;
  width: 100%;
  min-height: 0;
  margin: 0;
  border-radius: 0;
  display: flex;
  flex-direction: column;
}

.topology-view.is-pseudo-fullscreen :deep(.el-card__body) {
  flex: 1;
  width: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 14px 18px;
}

.topology-view.is-pseudo-fullscreen.is-fullscreen-edit :deep(.el-card__body) {
  padding: 8px 12px 6px;
}

.topology-view.is-pseudo-fullscreen .topology-stage {
  flex: 1;
  height: auto;
  min-height: 0;
  border-radius: 0;
}

.topology-view.is-pseudo-fullscreen .topology-container {
  width: 100% !important;
  height: 100% !important;
  min-height: 0;
}

.topology-view.is-pseudo-fullscreen .legend {
  flex-shrink: 0;
}

.topology-view.is-pseudo-fullscreen .edge-panel {
  max-height: 60vh;
  overflow: auto;
}

.topo-fullscreen-edit-btn {
  white-space: nowrap;
}

.edit-hint {
  margin-bottom: 10px;
}

.legend {
  display: flex;
  align-items: center;
  gap: 14px;
  padding-top: 10px;
  font-size: 12px;
  color: #64748b;
  flex-wrap: wrap;
}

.legend-group {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.legend-count {
  padding: 0 4px;
  border-radius: 7px;
  background: #f1f5f9;
  color: #64748b;
  font-size: 10px;
  line-height: 16px;
  font-weight: 500;
}

.legend-group .ic {
  display: inline-flex;
  width: 18px;
  height: 18px;
}

.legend-group .dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  display: inline-block;
}

.legend-group .line {
  width: 20px;
  height: 3px;
  border-radius: 2px;
  display: inline-block;
}

.line.low { background: #22c55e; }
.line.mid { background: #f59e0b; }
.line.high { background: #ef4444; }

.legend-sep {
  width: 1px;
  height: 14px;
  background: #e5e7eb;
}

.legend-tip {
  color: #94a3b8;
  margin-left: auto;
}

.edge-panel {
  position: absolute;
  left: 32px;
  bottom: 56px;
  z-index: 20;
  width: 270px;
  padding: 12px 14px;
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.95);
  border: 1px solid rgba(56, 189, 248, 0.35);
  color: #e2e8f0;
  font-size: 12px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45);
}

.edge-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
  color: #93c5fd;
}

.edge-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 3px 0;
}

.edge-row .k {
  color: #94a3b8;
}

.edge-row .v {
  color: #e2e8f0;
  font-weight: 600;
  text-align: right;
  word-break: break-all;
}

.flow-upload {
  color: #38bdf8;
  margin-right: 10px;
}

.flow-download {
  color: #fbbf24;
}

.edge-tip {
  margin-top: 8px;
  font-size: 11px;
  color: #64748b;
}

.asset-picker-alert {
  margin-bottom: 14px;
}

.asset-picker-form {
  margin-bottom: 4px;
}

.asset-option-name {
  color: #24425b;
  font-weight: 600;
}

.asset-option-ip {
  margin-left: 10px;
  color: #8aa0b1;
  font-family: Consolas, monospace;
  font-size: 11px;
}

.asset-option-tag {
  float: right;
  margin-left: 8px;
  padding: 0 5px;
  border-radius: 3px;
  color: #059669;
  background: #ecfdf5;
  font-size: 10px;
}

.asset-option-tag.disabled {
  color: #b45309;
  background: #fffbeb;
}

.asset-preview {
  display: flex;
  align-items: flex-start;
  gap: 11px;
  margin-top: 8px;
  padding: 13px;
  border: 1px solid #dce9f3;
  border-radius: 9px;
  background: #f8fbfe;
}

.asset-preview-icon {
  width: 54px;
  height: 54px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border: 1px solid #d6e6f1;
  border-radius: 10px;
  background: #fff;
}

.asset-preview-icon img {
  width: 46px;
  height: 46px;
  object-fit: contain;
}

.asset-preview-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.asset-preview-title {
  display: flex;
  align-items: center;
  gap: 7px;
  color: #24425b;
  font-size: 13px;
}

.asset-preview-main > span {
  color: #7891a5;
  font-size: 11px;
}

.asset-preview-main .asset-preview-hint {
  color: #8fa3b3;
  font-size: 10px;
  line-height: 1.5;
}
</style>
