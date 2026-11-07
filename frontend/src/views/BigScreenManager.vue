<template>
  <div class="bigscreen-manager">
    <div class="manager-head">
      <div>
        <h2>大屏展示</h2>
        <p>自定义多块大屏，内容与当前监控的设备、指标和告警实时关联。</p>
      </div>
      <div class="manager-head-actions">
        <el-button @click="openWebsiteBigScreen">
          <el-icon><Monitor /></el-icon>网站监控大屏
        </el-button>
        <el-button v-if="aiLicensed" @click="openAiBigScreen">
          <el-icon><Cpu /></el-icon>AI运维大屏
        </el-button>
        <el-button @click="openAssetBigScreen">
          <el-icon><Box /></el-icon>资产大屏
        </el-button>
        <el-button @click="openVirtualizationBigScreen">
          <el-icon><Cpu /></el-icon>虚拟化大屏
        </el-button>
        <el-button @click="sharedWithMeVisible = true">
          <el-icon><FolderOpened /></el-icon>共享给我的大屏
        </el-button>
        <el-button type="primary" @click="addScreen">
          <el-icon><Plus /></el-icon>新增大屏
        </el-button>
      </div>
    </div>

    <div class="screen-grid">
      <el-card class="screen-card" shadow="hover">
        <div class="screen-preview theme-tech website-preview">
          <div class="preview-top">
            <span>网站监控 · 全景态势</span>
            <i></i>
          </div>
          <div class="website-preview-orbit">
            <span class="orbit-dot dot-a"></span>
            <span class="orbit-dot dot-b"></span>
            <span class="orbit-dot dot-c"></span>
            <div class="website-preview-core">
              <strong>LIVE</strong>
              <small>WEBSITE</small>
            </div>
          </div>
          <div class="website-preview-kpis">
            <span><i class="ok"></i>在线</span>
            <span><i class="warn"></i>波动</span>
            <span><i class="bad"></i>离线</span>
          </div>
          <div class="preview-scan"></div>
        </div>
        <div class="screen-card-body">
          <div class="screen-title-row">
            <h3>网站监控大屏</h3>
            <el-tag size="small" type="success" effect="plain">实时</el-tag>
          </div>
          <p>在线态势、响应波动、证书倒计时与异常告警，一屏掌握所有网站健康状态。</p>
          <div class="screen-meta">
            <span>自动适应屏幕</span>
            <span>10 秒刷新</span>
          </div>
          <div class="screen-actions">
            <el-button type="primary" size="small" @click="openWebsiteBigScreen">
              <el-icon><FullScreen /></el-icon>打开大屏
            </el-button>
          </div>
        </div>
      </el-card>

      <el-card v-if="aiLicensed" class="screen-card builtin-ai-card" shadow="hover">
        <div class="screen-preview ai-preview">
          <div class="preview-top"><span>{{ aiName }} AI · 运维中心</span><i></i></div>
          <div class="ai-preview-core">
            <span class="ai-preview-ring"></span>
            <span class="ai-preview-eye"></span>
            <span class="ai-preview-eye"></span>
            <strong>AI</strong>
          </div>
          <div class="ai-preview-kpis">
            <span>资产态势</span><span>告警研判</span><span>语音问答</span>
          </div>
          <div class="preview-scan"></div>
        </div>
        <div class="screen-card-body">
          <div class="screen-title-row">
            <h3>AI 运维大屏</h3>
            <el-tag size="small" type="success" effect="plain">AI</el-tag>
          </div>
          <p>资产、告警、MIB、虚拟化与巡检态势聚合，支持连续语音对话和 AI 语音回答。</p>
          <div class="screen-meta"><span>自适应全屏</span><span>15 秒刷新</span></div>
          <div class="screen-actions">
            <el-button type="primary" size="small" @click="openAiBigScreen">
              <el-icon><FullScreen /></el-icon>打开大屏
            </el-button>
          </div>
        </div>
      </el-card>

      <el-card class="screen-card builtin-asset-card" shadow="hover">
        <div class="screen-preview asset-preview">
          <div class="preview-top"><span>资产数字孪生 · 3D</span><i></i></div>
          <div class="asset-preview-grid">
            <span v-for="i in 18" :key="i" :style="{ height: `${20 + (i * 17) % 68}px`, animationDelay: `${i * 0.12}s` }"></span>
          </div>
          <div class="preview-scan"></div>
        </div>
        <div class="screen-card-body">
          <div class="screen-title-row"><h3>资产数字孪生大屏</h3><el-tag size="small" type="success" effect="plain">3D</el-tag></div>
          <p>资产总数、在线状态、类型/厂商分布、CPU/内存热点和告警，配 3D 资产柱阵。</p>
          <div class="screen-meta"><span>3D 自适应</span><span>10 秒刷新</span></div>
          <div class="screen-actions">
            <el-button type="primary" size="small" @click="openAssetBigScreen"><el-icon><FullScreen /></el-icon>打开大屏</el-button>
          </div>
        </div>
      </el-card>

      <el-card class="screen-card builtin-virtual-card" shadow="hover">
        <div class="screen-preview virtual-preview">
          <div class="preview-top"><span>虚拟化资源轨道 · 3D</span><i></i></div>
          <div class="virtual-preview-orbit">
            <span class="virtual-core"></span>
            <i v-for="i in 7" :key="i" :style="{ transform: `rotate(${i * 51}deg) translateX(62px)` }"></i>
          </div>
          <div class="preview-scan"></div>
        </div>
        <div class="screen-card-body">
          <div class="screen-title-row"><h3>虚拟化资源大屏</h3><el-tag size="small" type="success" effect="plain">3D</el-tag></div>
          <p>平台、宿主机、虚拟机运行状态、资源负载和告警，配 3D 资源轨道。</p>
          <div class="screen-meta"><span>3D 自适应</span><span>10 秒刷新</span></div>
          <div class="screen-actions">
            <el-button type="primary" size="small" @click="openVirtualizationBigScreen"><el-icon><FullScreen /></el-icon>打开大屏</el-button>
          </div>
        </div>
      </el-card>

      <el-card v-for="screen in screens" :key="screen.id" class="screen-card" shadow="hover">
        <div class="screen-preview" :class="[`theme-${screen.theme || 'tech'}`, { 'is-virtualization': screen.kind === 'virtualization' }]">
          <div class="preview-top">
            <span>{{ screen.name }}</span>
            <i></i>
          </div>
          <div class="preview-widgets">
            <span
              v-for="widget in screen.widgets.slice(0, 8)"
              :key="widget.id"
              class="preview-block"
              :class="`type-${widget.type}`"
              :style="{ flex: Math.max(1, widget.span || 3) }"
            ></span>
          </div>
          <div class="preview-scan"></div>
        </div>
        <div class="screen-card-body">
          <div class="screen-title-row">
            <h3>{{ screen.name }}</h3>
            <el-tag size="small" type="info" effect="plain">{{ screen.widgets.length }} 个组件</el-tag>
          </div>
          <p>{{ screen.description || '未填写描述' }}</p>
          <div class="screen-meta">
            <span>刷新 {{ screen.refresh || 10 }} 秒</span>
            <span>宽屏 12 列</span>
          </div>
          <div class="screen-actions">
            <el-button type="primary" size="small" @click="openScreen(screen)">
              <el-icon><FullScreen /></el-icon>打开大屏
            </el-button>
            <el-button size="small" @click="editScreen(screen)">
              <el-icon><Setting /></el-icon>配置
            </el-button>
            <el-button size="small" @click="openShare(screen)">
              <el-icon><Share /></el-icon>分享
            </el-button>
            <el-dropdown trigger="click" @command="(cmd) => screenCommand(cmd, screen)">
              <el-button size="small" text><el-icon><MoreFilled /></el-icon></el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="duplicate">复制大屏</el-dropdown-item>
                  <el-dropdown-item command="delete" divided>删除大屏</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
      </el-card>

      <button type="button" class="screen-add-card" @click="addScreen">
        <el-icon :size="26"><Plus /></el-icon>
        <span>新增大屏</span>
        <small>从空白开始自由配置</small>
      </button>
    </div>

    <el-dialog
      v-model="editorVisible"
      :title="editing?.name ? `配置大屏 · ${editing.name}` : '配置大屏'"
      width="1180px"
      top="3vh"
      class="bigscreen-editor-dialog"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <div v-if="editing" class="editor-layout">
        <div class="editor-main">
          <div class="editor-basic">
            <el-form label-width="82px" label-position="left">
              <el-row :gutter="14">
                <el-col :span="13">
                  <el-form-item label="大屏名称">
                    <el-input v-model="editing.name" maxlength="30" placeholder="例如：机房运行态势" />
                  </el-form-item>
                </el-col>
                <el-col :span="11">
                  <el-form-item label="刷新间隔">
                    <div class="refresh-input-row">
                      <el-input-number v-model="editing.refresh" :min="3" :max="300" :step="1" />
                      <span class="refresh-unit">秒</span>
                    </div>
                  </el-form-item>
                </el-col>
              </el-row>
              <el-form-item label="描述">
                <el-input v-model="editing.description" maxlength="60" placeholder="一句话说明大屏用途" />
              </el-form-item>
              <el-form-item label="显示设置">
                <div class="display-settings">
                  <span class="display-label">字体</span>
                  <el-select
                    v-model="editing.display.fontFamily"
                    size="small"
                    filterable
                    allow-create
                    default-first-option
                    style="width: 250px"
                  >
                    <el-option
                      v-for="font in CLOCK_FONT_OPTIONS"
                      :key="font.value"
                      :label="font.label"
                      :value="font.value"
                    />
                  </el-select>
                  <span class="display-label">全局字号</span>
                  <el-input-number
                    v-model="editing.display.fontSize"
                    :min="8"
                    :max="40"
                    size="small"
                    controls-position="right"
                    style="width: 112px"
                  />
                  <span class="display-unit">px</span>
                </div>
                <div class="form-tip">组件字号「跟随全局」时使用这里的基础字号；字号以 14px 为基准等比缩放，单个组件可在下方单独设置字号。</div>
              </el-form-item>
              <el-form-item label="Zabbix 数据源">
                <div class="zabbix-source-config">
                  <div class="zabbix-source-row">
                    <el-input v-model="editing.zabbix.url" placeholder="https://zabbix.example.com" class="zabbix-url" />
                    <el-switch v-model="editing.zabbix.verify_tls" size="small" active-text="校验 TLS" />
                  </div>
                  <div class="zabbix-source-row">
                    <el-input v-model="editing.zabbix.token" type="password" show-password placeholder="API Token（推荐）" />
                    <el-input v-model="editing.zabbix.username" placeholder="用户名（可选）" class="zabbix-account" />
                    <el-input v-model="editing.zabbix.password" type="password" show-password placeholder="密码（可选）" class="zabbix-account" />
                  </div>
                  <div class="form-tip">
                    Zabbix 数据用于「Zabbix 指标」组件；凭据随当前大屏配置保存在浏览器 localStorage，请在可信管理机使用。
                  </div>
                </div>
              </el-form-item>
              <el-form-item label="时间显示">
                <div class="clock-config">
                  <div class="clock-row">
                    <span class="clock-label">字号</span>
                    <el-input-number
                      v-model="editing.clock.fontSize"
                      :min="10"
                      :max="46"
                      :step="1"
                      size="small"
                      controls-position="right"
                      style="width: 100px"
                    />
                    <span class="clock-label">加粗</span>
                    <el-switch v-model="editing.clock.bold" size="small" />
                    <span class="clock-label">时制</span>
                    <el-radio-group v-model="editing.clock.hour12" size="small">
                      <el-radio-button :value="false">24 小时</el-radio-button>
                      <el-radio-button :value="true">12 小时</el-radio-button>
                    </el-radio-group>
                  </div>
                  <div class="clock-row">
                    <span class="clock-label">显示日期</span>
                    <el-checkbox v-model="editing.clock.showYear">年</el-checkbox>
                    <el-checkbox v-model="editing.clock.showMonth">月</el-checkbox>
                    <el-checkbox v-model="editing.clock.showDay">日</el-checkbox>
                    <el-checkbox v-model="editing.clock.showWeekday">星期</el-checkbox>
                  </div>
                  <div class="clock-row">
                    <span class="clock-label">字体</span>
                    <el-select
                      v-model="editing.clock.fontFamily"
                      size="small"
                      filterable
                      allow-create
                      default-first-option
                      style="width: 310px"
                    >
                      <el-option
                        v-for="font in CLOCK_FONT_OPTIONS"
                        :key="font.value"
                        :label="font.label"
                        :value="font.value"
                      />
                    </el-select>
                    <span class="clock-label">时区</span>
                    <el-select
                      v-model="editing.clock.timezone"
                      size="small"
                      filterable
                      style="width: 240px"
                    >
                      <el-option
                        v-for="zone in TIMEZONE_OPTIONS"
                        :key="zone.value"
                        :label="zone.label"
                        :value="zone.value"
                      />
                    </el-select>
                  </div>
                </div>
              </el-form-item>
            </el-form>
          </div>

          <div class="widget-toolbar">
            <div>
              <strong>内容组件</strong>
              <span class="widget-total">组件总宽 {{ totalSpan }} · {{ editing.widgets.length }} 个</span>
              <span class="field-hint">保存后打开大屏，点「编辑布局」可拖动和缩放组件</span>
            </div>
            <el-dropdown trigger="click" @command="addWidget">
              <el-button type="primary" size="small">
                <el-icon><Plus /></el-icon>添加组件
                <el-icon class="el-icon--right"><ArrowDown /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item v-for="type in WIDGET_TYPES" :key="type.value" :command="type.value">
                    {{ type.label }}
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>

          <div class="widget-list">
            <div v-for="(widget, index) in editing.widgets" :key="widget.id" class="widget-row">
              <div class="widget-row-head">
                <span class="widget-index">{{ String(index + 1).padStart(2, '0') }}</span>
                <el-select v-model="widget.type" size="small" style="width: 118px" @change="onWidgetTypeChange(widget)">
                  <el-option v-for="type in WIDGET_TYPES" :key="type.value" :label="type.label" :value="type.value" />
                </el-select>
                <el-input v-model="widget.title" size="small" placeholder="组件标题" class="widget-title-input" />
                <div class="widget-row-actions">
                  <el-button link :disabled="index === 0" @click="moveWidget(index, -1)">↑</el-button>
                  <el-button link :disabled="index === editing.widgets.length - 1" @click="moveWidget(index, 1)">↓</el-button>
                  <el-button link type="danger" @click="removeWidget(index)">删除</el-button>
                </div>
              </div>

              <div class="widget-fields">
                <template v-if="widget.type === 'kpi'">
                  <el-select v-model="widget.kpiKey" size="small" style="width: 160px">
                    <el-option v-for="item in KPI_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
                  </el-select>
                </template>
                <template v-else-if="widget.type === 'gauge'">
                  <el-select v-model="widget.deviceId" filterable clearable size="small" placeholder="选择设备" style="width: 210px">
                    <el-option
                      v-for="device in devices"
                      :key="device.id"
                      :label="`${device.name} · ${device.ip_address}`"
                      :value="device.id"
                    />
                  </el-select>
                  <el-select v-model="widget.metric" size="small" style="width: 150px">
                    <el-option v-for="item in metricOptions" :key="item.value" :label="item.label" :value="item.value" />
                  </el-select>
                </template>
                <template v-else-if="widget.type === 'bar' || widget.type === 'table'">
                  <el-select v-model="widget.metric" size="small" style="width: 150px">
                    <el-option v-for="item in metricOptions" :key="item.value" :label="item.label" :value="item.value" />
                  </el-select>
                  <span class="field-label">TOP</span>
                  <el-input-number v-model="widget.limit" :min="3" :max="20" size="small" controls-position="right" style="width: 88px" />
                </template>
                <template v-else-if="widget.type === 'alerts'">
                  <span class="field-label">显示条数</span>
                  <el-input-number v-model="widget.limit" :min="3" :max="20" size="small" controls-position="right" style="width: 88px" />
                </template>
                <template v-else-if="widget.type === 'topology'">
                  <span class="field-hint">自动读取当前网络拓扑、设备状态与链路，大屏内每 15 秒刷新</span>
                </template>
                <template v-else-if="widget.type === 'virtualization'">
                  <span class="field-hint">自动读取虚拟化平台、宿主机、虚拟机资源与未恢复告警，组件内每轮刷新同步</span>
                </template>
                <template v-else-if="widget.type === 'zabbix'">
                  <el-input v-model="widget.host" size="small" placeholder="Zabbix 主机技术名" style="width: 190px" />
                  <el-input v-model="widget.item" size="small" placeholder="监控项 key，如 system.cpu.util" style="width: 240px" />
                  <el-select v-model="widget.aggregation" size="small" style="width: 110px">
                    <el-option label="最新值" value="last" />
                    <el-option label="平均值" value="avg" />
                    <el-option label="最小值" value="min" />
                    <el-option label="最大值" value="max" />
                  </el-select>
                  <template v-if="widget.aggregation !== 'last'">
                    <span class="field-label">最近</span>
                    <el-input-number v-model="widget.minutes" :min="1" :max="10080" size="small" controls-position="right" style="width: 100px" />
                    <span class="field-label">分钟</span>
                  </template>
                  <el-input v-model="widget.unit" size="small" placeholder="单位，可留空" style="width: 100px" />
                  <span class="field-label">小数</span>
                  <el-input-number v-model="widget.precision" :min="0" :max="4" size="small" controls-position="right" style="width: 78px" />
                </template>
                <template v-else-if="widget.type === 'website'">
                  <span class="field-label">显示条数</span>
                  <el-input-number v-model="widget.websiteLimit" :min="3" :max="20" size="small" controls-position="right" style="width: 88px" />
                  <span class="field-hint">自动读取网站监控的在线状态、响应时间和证书剩余天数</span>
                </template>
                <template v-else-if="widget.type === 'text'">
                  <el-input
                    v-model="widget.content"
                    type="textarea"
                    :rows="2"
                    size="small"
                    placeholder="输入标题、说明或任意文字"
                    style="width: 100%"
                  />
                  <el-select v-model="widget.align" size="small" style="width: 100px">
                    <el-option label="左对齐" value="left" />
                    <el-option label="居中" value="center" />
                    <el-option label="右对齐" value="right" />
                  </el-select>
                  <el-color-picker v-model="widget.color" size="small" />
                </template>
                <template v-else>
                  <span class="field-hint">{{ widget.type === 'server' ? '自动汇总所有服务器硬件传感器' : '展示最近 24 小时告警趋势' }}</span>
                </template>

                <span class="field-label">字号</span>
                <el-select v-model="widget.fontSize" size="small" style="width: 126px">
                  <el-option label="跟随全局" :value="0" />
                  <el-option v-for="size in WIDGET_FONT_SIZES" :key="size" :label="`${size} px`" :value="size" />
                </el-select>
                <span class="field-label">字体</span>
                <el-select v-model="widget.fontFamily" size="small" style="width: 170px">
                  <el-option label="跟随全局" value="" />
                  <el-option v-for="font in CLOCK_FONT_OPTIONS" :key="font.value" :label="font.label" :value="font.value" />
                </el-select>
                <span class="field-label">占宽</span>
                <el-input-number v-model="widget.span" :min="2" :max="12" size="small" controls-position="right" style="width: 88px" />
              </div>
            </div>
            <el-empty v-if="!editing.widgets.length" description="还没有组件，点击右上角添加" :image-size="56" />
          </div>
        </div>

        <aside class="suggestion-panel">
          <div class="suggestion-head">
            <el-icon><MagicStick /></el-icon>
            <div>
              <strong>配置建议</strong>
              <small>根据当前设备和组件实时生成</small>
            </div>
          </div>
          <div class="suggestion-list">
            <div v-for="(tip, index) in suggestions" :key="index" class="suggestion-item" :class="tip.level || 'info'">
              <span class="suggestion-dot"></span>
              <div>
                <p>{{ tip.text }}</p>
                <el-button v-if="tip.action" link size="small" type="primary" @click="tip.action()">立即应用</el-button>
              </div>
            </div>
            <div v-if="!suggestions.length" class="suggestion-empty">当前配置不错，继续保持。</div>
          </div>

          <div class="suggestion-summary">
            <div><span>设备数据</span><b>{{ devices.length }}</b></div>
            <div><span>服务器硬件</span><b>{{ serverDevices.length }}</b></div>
            <div><span>总占宽</span><b>{{ totalSpan }}</b></div>
            <div><span>刷新</span><b>{{ editing.refresh }} 秒</b></div>
          </div>
        </aside>
      </div>

      <template #footer>
        <el-button @click="editorVisible = false">取消</el-button>
        <el-button type="primary" @click="saveEditor">保存大屏</el-button>
      </template>
    </el-dialog>

    <ResourceShareDialog
      v-if="sharingScreen"
      v-model="shareVisible"
      resource-type="bigscreen"
      :resource-key="String(sharingScreen.id)"
      :title="sharingScreen.name"
      :config="sharingScreen"
    />
    <SharedWithMeDialog v-model="sharedWithMeVisible" resource-type="bigscreen" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getToken, handoffToken } from '@/store/auth'
import { aiApi, licenseApi } from '@/api'
import ResourceShareDialog from '@/components/ResourceShareDialog.vue'
import SharedWithMeDialog from '@/components/SharedWithMeDialog.vue'
import {
  WIDGET_TYPES, KPI_OPTIONS, METRIC_OPTIONS, TIMEZONE_OPTIONS, CLOCK_FONT_OPTIONS, WIDGET_FONT_SIZES,
  readScreens, writeScreens, createScreen, cloneScreen,
  defaultWidget, makeId, fetchAllDevices,
} from '@/utils/bigscreen'

const screens = ref([])
const aiLicensed = ref(true)
const aiName = ref('玄武')
const shareVisible = ref(false)
const sharedWithMeVisible = ref(false)
const sharingScreen = ref(null)
const devices = ref([])
const editorVisible = ref(false)
const editing = ref(null)

const serverDevices = computed(() => devices.value.filter((device) => (device.server_sensors || []).length))
const metricOptions = computed(() => {
  const options = [...METRIC_OPTIONS]
  devices.value.forEach((device) => {
    ;(device.server_sensors || []).forEach((sensor) => {
      if (!options.some((item) => item.value === sensor.key)) {
        options.push({ value: sensor.key, label: sensor.name || sensor.key, unit: sensor.unit || '' })
      }
    })
  })
  return options
})
const totalSpan = computed(() => (editing.value?.widgets || []).reduce((sum, widget) => sum + Number(widget.span || 3), 0))

const suggestions = computed(() => {
  if (!editing.value) return []
  const list = []
  const widgets = editing.value.widgets
  if (!widgets.length) {
    list.push({
      text: '当前大屏没有内容，建议先添加设备总数、实时告警和 CPU TOP5。',
      action: () => {
        editing.value.widgets.push(
          { ...defaultWidget('kpi'), id: makeId('w'), title: '设备总数', kpiKey: 'total_devices', span: 3 },
          { ...defaultWidget('alerts'), id: makeId('w'), title: '实时告警', span: 6, limit: 6 },
          { ...defaultWidget('bar'), id: makeId('w'), title: 'CPU TOP5', span: 6, limit: 5 },
        )
      },
    })
    return list
  }
  if (!widgets.some((widget) => widget.type === 'alerts')) {
    list.push({
      text: '建议增加「实时告警」，大屏上可以第一时间看到异常。',
      action: () => widgets.push({ ...defaultWidget('alerts'), id: makeId('w'), title: '实时告警', span: 6, limit: 6 }),
    })
  }
  if (!widgets.some((widget) => widget.type === 'trend')) {
    list.push({
      text: '建议增加「告警趋势」，用 24 小时曲线观察异常变化。',
      action: () => widgets.push({ ...defaultWidget('trend'), id: makeId('w'), title: '24 小时告警趋势', span: 12 }),
    })
  }
  if (!widgets.some((widget) => widget.type === 'table' || widget.type === 'gauge')) {
    list.push({
      text: '建议增加设备表格或单设备仪表，方便在大屏上查看具体设备。',
      action: () => widgets.push({ ...defaultWidget('table'), id: makeId('w'), title: '设备运行状态', span: 6, limit: 8 }),
    })
  }
  if (widgets.length >= 6) {
    list.push({ text: '组件较多时建议按「顶部 KPI、中部排行、底部明细/趋势」组织，大屏层次更清楚。' })
  }
  if (serverDevices.value.length && !widgets.some((widget) => widget.type === 'server')) {
    list.push({
      text: `检测到 ${serverDevices.value.length} 台服务器配置了硬件传感器，建议增加服务器硬件区域。`,
      action: () => widgets.push({ ...defaultWidget('server'), id: makeId('w'), title: '服务器硬件状态', span: 12 }),
    })
  }
  const emptyGauge = widgets.find((widget) => widget.type === 'gauge' && !widget.deviceId)
  if (emptyGauge) {
    list.push({ text: '存在未选择设备的单设备仪表，配置后才会显示实时数据。', level: 'warning' })
  }
  const gaugeWidget = widgets.find((widget) => widget.type === 'gauge' && widget.deviceId)
  if (gaugeWidget) {
    const device = devices.value.find((item) => item.id === gaugeWidget.deviceId)
    const sensors = device?.server_sensors || []
    if (sensors.length && !sensors.some((sensor) => sensor.key === gaugeWidget.metric)) {
      const first = sensors.find((sensor) => sensor.oid)
      if (first) {
        list.push({
          text: `该设备配置了服务器硬件传感器，建议改为展示「${first.name}」，更贴近服务器健康状态。`,
          action: () => { gaugeWidget.metric = first.key },
        })
      }
    }
    if (device && device.metric?.collected_at) {
      const at = device.metric.collected_at
      const normalized = /[zZ]|[+-]\d{2}:\d{2}$/.test(at) ? at : `${at}Z`
      if (Date.now() - new Date(normalized).getTime() > 10 * 60 * 1000) {
        list.push({ text: '当前选中的设备超过 10 分钟没有上报指标，请确认设备在线或采集配置。', level: 'warning' })
      }
    }
  }
  const faultMetric = widgets.find((widget) => ['bar', 'table'].includes(widget.type) && ['srv_mem_fault', 'srv_disk_fault'].includes(widget.metric))
  if (faultMetric) {
    list.push({ text: '故障状态量不适合做排行，建议改用 CPU、内存、温度或电源电压等数值指标。', level: 'warning' })
  }
  if (totalSpan.value > 12 && totalSpan.value % 12 !== 0) {
    list.push({ text: '组件总宽度不是 12 的整数倍，右侧或底部可能出现留白。', level: 'warning' })
  }
  if (Number(editing.value.refresh) > 30) {
    list.push({ text: '刷新间隔超过 30 秒，大屏实时性会下降，建议 5~15 秒。' })
  }
  if (widgets.some((widget) => widget.type === 'table') && widgets.length > 6) {
    list.push({ text: '组件较多时，设备表格建议只保留 5~8 行，避免大屏拥挤。' })
  }
  return list.slice(0, 4)
})

function loadDevices() {
  fetchAllDevices().then((items) => {
    devices.value = items
  }).catch(() => {
    devices.value = []
  })
}

function addScreen() {
  editing.value = createScreen(`新大屏 ${screens.value.length + 1}`)
  editorVisible.value = true
}

function editScreen(screen) {
  editing.value = cloneScreen(screen)
  editorVisible.value = true
}

function openScreen(screen) {
  // 新标签页与当前标签页不共享 sessionStorage，先交接一次登录令牌，避免二次登录
  handoffToken(getToken())
  window.open(`/bigscreen/view/${screen.id}`, '_blank', 'noopener,noreferrer')
}

function openWebsiteBigScreen() {
  handoffToken(getToken())
  window.open('/bigscreen/website', '_blank', 'noopener,noreferrer')
}

function openAiBigScreen() {
  handoffToken(getToken())
  // 保留 opener，AI 输出中的功能标签才能回到打开大屏前的原页签。
  window.open('/bigscreen/ai', 'nms-ai-screen')
}

function openAssetBigScreen() {
  handoffToken(getToken())
  window.open('/bigscreen/assets', '_blank', 'noopener,noreferrer')
}

function openVirtualizationBigScreen() {
  handoffToken(getToken())
  window.open('/bigscreen/virtualization', '_blank', 'noopener,noreferrer')
}

function openShare(screen) {
  sharingScreen.value = screen
  shareVisible.value = true
}

async function removeScreen(screen) {
  try {
    await ElMessageBox.confirm(`确定删除大屏「${screen.name}」吗？`, '删除大屏', { type: 'warning' })
  } catch {
    return
  }
  const list = readScreens().filter((item) => item.id !== screen.id)
  writeScreens(list)
  screens.value = list
  ElMessage.success('大屏已删除')
}

function duplicateScreen(screen) {
  const copy = cloneScreen(screen)
  copy.id = makeId('screen')
  copy.name = `${screen.name} - 副本`
  const list = [...readScreens(), copy]
  writeScreens(list)
  screens.value = list
  ElMessage.success('已复制大屏')
}

function screenCommand(command, screen) {
  if (command === 'duplicate') duplicateScreen(screen)
  if (command === 'delete') removeScreen(screen)
}

function addWidget(type) {
  if (!editing.value) return
  editing.value.widgets.push(defaultWidget(type))
}

function onWidgetTypeChange(widget) {
  const fresh = defaultWidget(widget.type)
  widget.title = fresh.title
  widget.span = fresh.span
  widget.limit = fresh.limit
  if (!widget.metric) widget.metric = fresh.metric
  if (!widget.kpiKey) widget.kpiKey = fresh.kpiKey
  if (widget.type === 'zabbix') {
    if (!widget.aggregation) widget.aggregation = fresh.aggregation
    if (widget.minutes === undefined) widget.minutes = fresh.minutes
    if (widget.precision === undefined) widget.precision = fresh.precision
    if (widget.unit === undefined) widget.unit = fresh.unit
  }
}

function moveWidget(index, delta) {
  const target = index + delta
  if (!editing.value || target < 0 || target >= editing.value.widgets.length) return
  const widgets = editing.value.widgets
  ;[widgets[index], widgets[target]] = [widgets[target], widgets[index]]
}

async function removeWidget(index) {
  if (!editing.value) return
  const widget = editing.value.widgets[index]
  if (!widget) return
  try {
    await ElMessageBox.confirm(
      `确定删除组件「${widget.title || '未命名组件'}」吗？保存大屏后生效。`,
      '删除组件',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  editing.value.widgets.splice(index, 1)
  ElMessage.success('组件已删除，保存大屏后生效')
}

function saveEditor() {
  if (!editing.value?.name?.trim()) {
    ElMessage.warning('请填写大屏名称')
    return
  }
  const payload = cloneScreen(editing.value)
  payload.name = payload.name.trim()
  payload.widgets = payload.widgets.map((widget) => ({ ...widget, id: widget.id || makeId('w') }))
  const list = readScreens()
  const index = list.findIndex((item) => item.id === payload.id)
  if (index >= 0) list.splice(index, 1, payload)
  else list.push(payload)
  writeScreens(list)
  screens.value = list
  editorVisible.value = false
  ElMessage.success('大屏配置已保存')
}

function cleanupLegacyScreens() {
  const legacyIds = new Set(['screen-virtualization', 'screen-default'])
  const legacyNames = new Set(['虚拟化平台资源监控', '网络运行态势'])
  const list = readScreens()
  const removed = list.filter((screen) => legacyIds.has(screen.id) || legacyNames.has(screen.name))
  const kept = list.filter((screen) => !legacyIds.has(screen.id) && !legacyNames.has(screen.name))
  if (removed.length) {
    try {
      const archived = JSON.parse(localStorage.getItem('nms_bigscreen_legacy_archive_v3') || '[]')
      localStorage.setItem('nms_bigscreen_legacy_archive_v3', JSON.stringify([...archived, ...removed]))
    } catch {
      /* localStorage 空间不足时仍继续清理 */
    }
    writeScreens(kept)
    ElMessage.info('已删除“虚拟化平台资源监控”和“网络运行态势”两个旧大屏')
  }
  return kept
}

async function loadAiName() {
  try {
    const res = await aiApi.status()
    aiName.value = String(res.data?.name || 'AI').trim() || 'AI'
  } catch { aiName.value = 'AI' }
}

async function loadAiLicense() {
  try {
    const res = await licenseApi.publicStatus()
    const features = res.data?.features
    aiLicensed.value = !Array.isArray(features) || features.includes('ai')
  } catch {
    // 状态接口异常时保留入口，由后端 AI 接口统一做授权拦截
    aiLicensed.value = true
  }
}

onMounted(() => {
  screens.value = cleanupLegacyScreens()
  loadDevices()
  loadAiName()
  loadAiLicense()
})
</script>

<style scoped>
.bigscreen-manager {
  padding: 4px 0 24px;
}

.manager-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.manager-head h2 {
  margin: 0 0 5px;
  color: #0f172a;
  font-size: 22px;
}

.manager-head p {
  margin: 0;
  color: #64748b;
  font-size: 12px;
}

.manager-head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.screen-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}

.screen-card {
  border: 1px solid #e2e8f0;
  border-radius: 12px;
}

.screen-preview {
  position: relative;
  height: 146px;
  overflow: hidden;
  border-radius: 9px;
  padding: 12px;
  background:
    radial-gradient(circle at 84% 10%, rgba(56, 189, 248, 0.22), transparent 35%),
    linear-gradient(145deg, #061525, #0b2238 65%, #071321);
}

.screen-preview.is-virtualization {
  background:
    radial-gradient(circle at 20% 20%, rgba(34, 211, 238, .24), transparent 32%),
    radial-gradient(circle at 82% 78%, rgba(99, 102, 241, .26), transparent 38%),
    linear-gradient(145deg, #020a17, #071a31 58%, #04101f);
  animation: previewGlow 5s ease-in-out infinite alternate;
}

.screen-preview.is-virtualization::before {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(34, 211, 238, .1) 1px, transparent 1px),
    linear-gradient(90deg, rgba(34, 211, 238, .1) 1px, transparent 1px);
  background-size: 22px 22px;
  content: '';
  opacity: .55;
}

@keyframes previewGlow {
  from { filter: saturate(1); }
  to { filter: saturate(1.3); }
}

.preview-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #bae6fd;
  font-size: 11px;
  letter-spacing: 1px;
}

.preview-top i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #34d399;
  box-shadow: 0 0 8px #34d399;
}

.preview-widgets {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 12px;
}

.preview-block {
  height: 28px;
  min-width: 28px;
  border: 1px solid rgba(56, 189, 248, 0.18);
  border-radius: 4px;
  background: rgba(14, 165, 233, 0.08);
}

.preview-block.type-kpi { background: rgba(52, 211, 153, 0.16); }
.preview-block.type-alerts { background: rgba(251, 113, 133, 0.18); }
.preview-block.type-bar { height: 44px; }
.preview-block.type-server { background: rgba(167, 139, 250, 0.16); }
.preview-block.type-gauge { border-radius: 50%; height: 38px; }
.preview-scan {
  position: absolute;
  inset: 0;
  background: linear-gradient(transparent 0%, rgba(56, 189, 248, 0.08) 50%, transparent 100%);
  background-size: 100% 8px;
  opacity: 0.35;
  pointer-events: none;
}

.screen-card-body {
  padding-top: 11px;
}

.screen-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.screen-title-row h3 {
  margin: 0;
  color: #0f172a;
  font-size: 15px;
}

.screen-card-body p {
  min-height: 18px;
  margin: 6px 0 8px;
  color: #64748b;
  font-size: 12px;
}

.screen-meta {
  display: flex;
  gap: 14px;
  color: #94a3b8;
  font-size: 11px;
}

.screen-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 12px;
}

.screen-add-card {
  min-height: 320px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: 1px dashed #cbd5e1;
  border-radius: 12px;
  background: #f8fafc;
  color: #64748b;
  cursor: pointer;
  transition: border-color 0.2s ease, background 0.2s ease, color 0.2s ease;
}

.screen-add-card:hover {
  border-color: #60a5fa;
  background: #eff6ff;
  color: #1d4ed8;
}

.screen-add-card span {
  font-size: 13px;
  font-weight: 500;
}

.screen-add-card small {
  color: #94a3b8;
  font-size: 11px;
}

.editor-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  gap: 16px;
  max-height: 72vh;
}

.editor-main {
  overflow: auto;
  padding-right: 4px;
}

.editor-basic {
  padding: 12px 14px 2px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #f8fafc;
}

.clock-config {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.display-settings {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  width: 100%;
}

.display-label {
  color: #64748b;
  font-size: 11px;
}

.display-unit {
  color: #64748b;
  font-size: 11px;
}

.refresh-input-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.refresh-input-row :deep(.el-input-number) {
  flex: 1;
}

.refresh-unit {
  flex-shrink: 0;
  color: #64748b;
  font-size: 12px;
}

.clock-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.clock-label {
  color: #64748b;
  font-size: 11px;
  white-space: nowrap;
}

.clock-row :deep(.el-checkbox) {
  margin-right: 0;
}

.widget-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 16px 0 10px;
}

.widget-toolbar strong {
  color: #0f172a;
  font-size: 13px;
}

.widget-total {
  margin-left: 8px;
  color: #94a3b8;
  font-size: 11px;
}

.widget-list {
  display: flex;
  flex-direction: column;
  gap: 9px;
}

.widget-row {
  padding: 9px 10px;
  border: 1px solid #e2e8f0;
  border-radius: 9px;
  background: #fff;
}

.widget-row-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.widget-index {
  color: #94a3b8;
  font-family: Consolas, monospace;
  font-size: 10px;
}

.widget-title-input {
  flex: 1;
}

.widget-row-actions {
  display: flex;
  gap: 1px;
  flex-shrink: 0;
}

.widget-fields {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 7px;
  margin-top: 7px;
  padding-left: 28px;
}

.field-label {
  color: #64748b;
  font-size: 11px;
}

.field-hint {
  color: #94a3b8;
  font-size: 11px;
}

.suggestion-panel {
  display: flex;
  flex-direction: column;
  padding: 14px;
  border: 1px solid #dbeafe;
  border-radius: 11px;
  background: linear-gradient(160deg, #f8fbff, #eff6ff);
  overflow: auto;
}

.suggestion-head {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  color: #1d4ed8;
}

.suggestion-head strong {
  display: block;
  font-size: 13px;
}

.suggestion-head small {
  display: block;
  margin-top: 3px;
  color: #64748b;
  font-size: 10px;
}

.suggestion-list {
  display: flex;
  flex-direction: column;
  gap: 9px;
  margin-top: 14px;
}

.suggestion-item {
  display: flex;
  gap: 8px;
  padding: 8px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.75);
}

.suggestion-dot {
  flex-shrink: 0;
  width: 6px;
  height: 6px;
  margin-top: 6px;
  border-radius: 50%;
  background: #38bdf8;
}

.suggestion-item.warning .suggestion-dot {
  background: #f59e0b;
}

.suggestion-item p {
  margin: 0;
  color: #475569;
  font-size: 11px;
  line-height: 1.55;
}

.suggestion-empty {
  margin-top: 14px;
  color: #94a3b8;
  font-size: 11px;
}

.suggestion-summary {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-top: auto;
  padding-top: 14px;
}

.suggestion-summary div {
  padding: 8px;
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.72);
}

.suggestion-summary span {
  display: block;
  color: #94a3b8;
  font-size: 10px;
}

.suggestion-summary b {
  display: block;
  margin-top: 2px;
  color: #1e293b;
  font-family: Consolas, monospace;
  font-size: 14px;
}

@media (max-width: 1000px) {
  .editor-layout {
    grid-template-columns: 1fr;
  }

  .suggestion-panel {
    max-height: 260px;
  }
}
</style>

<!-- 弹窗被 teleport 到 body，使用非 scoped 样式保证高度与滚动稳定 -->
<style>
.bigscreen-editor-dialog {
  max-width: 94vw;
  margin-bottom: 0;
}

.bigscreen-editor-dialog .el-dialog__body {
  padding: 10px 18px 4px;
  overflow: hidden;
}

.bigscreen-editor-dialog .editor-layout {
  height: clamp(440px, calc(100vh - 235px), 720px);
  max-height: none;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 286px;
  gap: 16px;
}

.bigscreen-editor-dialog .editor-main {
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding-right: 8px;
}

.bigscreen-editor-dialog .editor-main::-webkit-scrollbar {
  width: 7px;
}

.bigscreen-editor-dialog .editor-main::-webkit-scrollbar-track {
  background: transparent;
}

.bigscreen-editor-dialog .editor-main::-webkit-scrollbar-thumb {
  border-radius: 4px;
  background: #cbd5e1;
}

.bigscreen-editor-dialog .editor-main::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}

.bigscreen-editor-dialog .suggestion-panel {
  min-height: 0;
  max-height: none;
  overflow-y: auto;
}

.bigscreen-editor-dialog .el-dialog__footer {
  padding-top: 10px;
}

@media (max-width: 1000px) {
  .bigscreen-editor-dialog .editor-layout {
    height: calc(100vh - 215px);
    grid-template-columns: 1fr;
  }

  .bigscreen-editor-dialog .suggestion-panel {
    max-height: 240px;
  }
}

@media (max-width: 720px) {
  .bigscreen-editor-dialog {
    width: 96vw !important;
    margin-top: 1vh !important;
  }

  .bigscreen-editor-dialog .editor-layout {
    height: calc(100vh - 190px);
  }
}

.zabbix-source-config {
  width: 100%;
}

.zabbix-source-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 7px;
}

.zabbix-url {
  flex: 1;
}

.zabbix-account {
  width: 170px;
}

/* AI 运维大屏预设卡片 */
.ai-preview {
  overflow: hidden;
  background:
    radial-gradient(circle at 50% 45%, rgba(45, 212, 191, 0.18), transparent 38%),
    linear-gradient(145deg, #06222a, #031018);
}
.ai-preview-core {
  position: absolute;
  left: 50%;
  top: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 112px;
  height: 112px;
  transform: translate(-50%, -50%);
  border: 1px solid rgba(94, 234, 212, 0.5);
  border-radius: 50%;
  background: rgba(3, 24, 31, 0.85);
  box-shadow: 0 0 32px rgba(45, 212, 191, 0.2), inset 0 0 24px rgba(45, 212, 191, 0.1);
}
.ai-preview-core::before {
  content: '';
  position: absolute;
  inset: -18px;
  border: 1px dashed rgba(94, 234, 212, 0.2);
  border-radius: 50%;
  animation: ai-preview-spin 12s linear infinite;
}
.ai-preview-core strong {
  color: #99f6e4;
  font-family: Consolas, monospace;
  font-size: 22px;
  letter-spacing: 2px;
  text-shadow: 0 0 14px rgba(45, 212, 191, 0.55);
}
.ai-preview-eye {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #5eead4;
  box-shadow: 0 0 10px #2dd4bf;
}
.ai-preview-kpis {
  position: absolute;
  left: 13px;
  right: 13px;
  bottom: 12px;
  display: flex;
  justify-content: space-between;
  padding: 7px 9px;
  border: 1px solid rgba(94, 234, 212, 0.15);
  border-radius: 5px;
  background: rgba(2, 16, 22, 0.66);
  color: #7dd3c7;
  font-size: 8px;
}
@keyframes ai-preview-spin { to { transform: rotate(360deg); } }

/* 网站监控大屏预设卡片 */
.website-preview {
  overflow: hidden;
  background:
    radial-gradient(circle at 50% 48%, rgba(34, 211, 238, 0.16), transparent 42%),
    linear-gradient(145deg, #071a2d, #04101f);
}

.website-preview-orbit {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 180px;
  height: 180px;
  transform: translate(-50%, -50%);
  border: 1px solid rgba(34, 211, 238, 0.28);
  border-radius: 50%;
  box-shadow: inset 0 0 32px rgba(34, 211, 238, 0.08), 0 0 35px rgba(34, 211, 238, 0.08);
  animation: website-orbit 12s linear infinite;
}

.website-preview-orbit::before,
.website-preview-orbit::after {
  content: '';
  position: absolute;
  inset: 18px;
  border: 1px dashed rgba(56, 189, 248, 0.22);
  border-radius: 50%;
}

.website-preview-orbit::after {
  inset: 38px;
  border-style: solid;
}

.website-preview-core {
  position: absolute;
  left: 50%;
  top: 50%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 82px;
  height: 82px;
  transform: translate(-50%, -50%);
  border: 1px solid rgba(34, 211, 238, 0.45);
  border-radius: 50%;
  background: rgba(3, 18, 32, 0.92);
  box-shadow: 0 0 24px rgba(34, 211, 238, 0.2);
}

.website-preview-core strong {
  color: #67e8f9;
  font-size: 26px;
  line-height: 1;
}

.website-preview-core small {
  margin-top: 4px;
  color: #7dd3fc;
  font-size: 9px;
  letter-spacing: 2px;
}

.orbit-dot {
  position: absolute;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #67e8f9;
  box-shadow: 0 0 10px #22d3ee;
}

.orbit-dot.dot-a { left: 16px; top: 38px; }
.orbit-dot.dot-b { right: 10px; top: 92px; animation-delay: -1.2s; background: #fbbf24; box-shadow: 0 0 10px #f59e0b; }
.orbit-dot.dot-c { left: 66px; bottom: 8px; animation-delay: -2.4s; background: #fb7185; box-shadow: 0 0 10px #f43f5e; }

.website-preview-kpis {
  position: absolute;
  left: 13px;
  right: 13px;
  bottom: 12px;
  display: flex;
  justify-content: space-between;
  padding: 7px 10px;
  border: 1px solid rgba(56, 189, 248, 0.14);
  border-radius: 5px;
  background: rgba(2, 12, 23, 0.65);
  color: #9fc9dd;
  font-size: 9px;
}

.website-preview-kpis span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.website-preview-kpis i {
  width: 5px;
  height: 5px;
  border-radius: 50%;
}

.website-preview-kpis .ok { background: #34d399; box-shadow: 0 0 7px #34d399; }
.website-preview-kpis .warn { background: #fbbf24; box-shadow: 0 0 7px #fbbf24; }
.website-preview-kpis .bad { background: #fb7185; box-shadow: 0 0 7px #fb7185; }

@keyframes website-orbit {
  from { transform: translate(-50%, -50%) rotate(0deg); }
  to { transform: translate(-50%, -50%) rotate(360deg); }
}

@media (max-width: 720px) {
  .website-preview-orbit {
    width: 145px;
    height: 145px;
  }
}

.builtin-asset-card,
.builtin-virtual-card {
  border-color: #e2e8f0;
}

.asset-preview {
  background:
    radial-gradient(circle at 50% 45%, rgba(52, 211, 153, 0.16), transparent 48%),
    linear-gradient(145deg, #041923, #06131f);
}

.asset-preview-grid {
  position: absolute;
  left: 22px;
  right: 22px;
  bottom: 34px;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  gap: 5px;
  height: 88px;
}

.asset-preview-grid span {
  flex: 1;
  max-width: 12px;
  border-radius: 2px 2px 0 0;
  background: linear-gradient(180deg, #67e8f9, #0e7490);
  box-shadow: 0 0 8px rgba(34, 211, 238, 0.35);
  animation: asset-bar 2.6s ease-in-out infinite alternate;
}

.asset-preview-grid span:nth-child(3n) {
  background: linear-gradient(180deg, #6ee7b7, #047857);
}

.asset-preview-grid span:nth-child(5n) {
  background: linear-gradient(180deg, #fbbf24, #b45309);
}

.virtual-preview {
  background:
    radial-gradient(circle at 50% 48%, rgba(167, 139, 250, 0.2), transparent 44%),
    linear-gradient(145deg, #061324, #0b1024);
}

.virtual-preview-orbit {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 150px;
  height: 150px;
  transform: translate(-50%, -50%);
  border: 1px solid rgba(167, 139, 250, 0.22);
  border-radius: 50%;
  animation: website-orbit 14s linear infinite;
}

.virtual-preview-orbit::before,
.virtual-preview-orbit::after {
  content: "";
  position: absolute;
  inset: 20px;
  border: 1px dashed rgba(56, 189, 248, 0.22);
  border-radius: 50%;
}

.virtual-preview-orbit::after {
  inset: 45px;
  border-style: solid;
}

.virtual-core {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 36px;
  height: 36px;
  transform: translate(-50%, -50%);
  border: 1px solid rgba(34, 211, 238, 0.65);
  border-radius: 50%;
  background: rgba(8, 47, 73, 0.9);
  box-shadow: 0 0 18px rgba(34, 211, 238, 0.38);
}

.virtual-preview-orbit i {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 7px;
  height: 7px;
  margin: -3.5px;
  border-radius: 50%;
  background: #c4b5fd;
  box-shadow: 0 0 9px #a78bfa;
}

@keyframes asset-bar {
  from { transform: scaleY(0.55); opacity: 0.55; }
  to { transform: scaleY(1); opacity: 1; }
}
</style>
