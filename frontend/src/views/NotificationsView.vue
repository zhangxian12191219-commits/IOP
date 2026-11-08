<template>
  <div class="notify-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>{{ t('notify.title') }}</span>
          <div class="actions">
            <el-button size="small" @click="dispatchTest" :loading="dispatching">
              <el-icon><Promotion /></el-icon>{{ t('notify.simulateDispatch') }}
            </el-button>
            <el-button type="primary" size="small" @click="openCreate">
              <el-icon><Plus /></el-icon>{{ t('notify.addChannel') }}
            </el-button>
          </div>
        </div>
      </template>

      <el-tabs v-model="activeTab">
        <!-- 通道 -->
        <el-tab-pane :label="t('notify.channels')" name="channels">
          <el-table :data="channels" v-loading="loading" stripe>
            <el-table-column prop="name" :label="t('notify.name')" :width="isCompact ? 140 : 180" />
            <el-table-column v-if="!isCompact" :label="t('notify.type')" width="110">
              <template #default="{ row }">
                <el-tag :type="typeTag(row.channel_type)" size="small">
                  {{ typeName(row.channel_type) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="t('notify.minLevel')" width="110">
              <template #default="{ row }">
                <el-tag :type="row.min_level === 'critical' || row.min_level === 'emergency' ? 'danger' : 'warning'" size="small">
                  {{ minLevelText(row.min_level) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="t('notify.target')" :min-width="isCompact ? 170 : 240" show-overflow-tooltip>
              <template #default="{ row }">{{ describeTarget(row) }}</template>
            </el-table-column>
            <el-table-column :label="t('notify.enable')" width="80">
              <template #default="{ row }">
                <el-switch
                  :model-value="row.enabled"
                  @change="(v) => toggleChannel(row, v)"
                />
              </template>
            </el-table-column>
            <el-table-column :label="t('notify.actions')" :width="isCompact ? 150 : 200" fixed="right">
              <template #default="{ row }">
                <el-button type="primary" link size="small" @click="testChannel(row)" :loading="row._testing">
                  {{ t('notify.test') }}
                </el-button>
                <el-button type="primary" link size="small" @click="openEdit(row)">{{ t('notify.edit') }}</el-button>
                <el-button type="danger" link size="small" @click="removeChannel(row)">{{ t('notify.delete') }}</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!loading && channels.length === 0" :description="t('notify.noChannelsHint')" />
        </el-tab-pane>

        <!-- 日志 -->
        <el-tab-pane :label="t('notify.sendLogs')" name="logs">
          <el-table :data="logs" v-loading="loadingLogs" stripe>
            <el-table-column type="expand" width="36">
              <template #default="{ row }">
                <div class="notify-log-body">{{ row.message || '-' }}</div>
              </template>
            </el-table-column>
            <el-table-column :label="t('notify.time')" width="170">
              <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column prop="channel_name" :label="t('notify.channel')" :width="isCompact ? 130 : 150" />
            <el-table-column v-if="!isCompact" :label="t('notify.source')" width="100">
              <template #default="{ row }">
                {{ { device: t('notify.device'), website: t('notify.website'), upstream: '上级平台', test: t('notify.test') }[row.source] || row.source }}
              </template>
            </el-table-column>
            <el-table-column prop="title" :label="t('notify.heading')" :min-width="isCompact ? 160 : 220" show-overflow-tooltip />
            <el-table-column v-if="!isCompact" :label="t('notify.content')" min-width="320" show-overflow-tooltip>
              <template #default="{ row }">{{ row.message || '-' }}</template>
            </el-table-column>
            <el-table-column :label="t('notify.status')" width="100">
              <template #default="{ row }">
                <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">
                  {{ row.status === 'success' ? t('notify.success') : t('notify.failed') }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column v-if="!isCompact" prop="error" :label="t('notify.error')" min-width="200" show-overflow-tooltip />
          </el-table>
          <el-pagination
            v-model:current-page="logPage"
            :total="logTotal"
            :page-size="logSize"
            layout="total, prev, pager, next"
            class="pager"
            @current-change="loadLogs"
          />
        </el-tab-pane>

        <!-- 上级平台接收 -->
        <el-tab-pane label="上级平台接收" name="upstream">
          <div class="upstream-receiver-head">
            <div>
              <strong>统一告警汇聚入口</strong>
              <p>下级节点把告警上报到此处，再由本节点已配置的邮件、Webhook、短信统一外发。上级接收入口不会再次转发给其他上级，避免环路。</p>
            </div>
            <el-button type="primary" plain size="small" :loading="upstreamGenerating" @click="generateUpstreamToken">
              {{ upstreamSettings.configured ? '重置接收令牌' : '生成接收令牌' }}
            </el-button>
          </div>

          <el-alert
            v-if="!upstreamSettings.configured"
            type="warning"
            :closable="false"
            show-icon
            title="尚未生成上级平台接收令牌，下级节点暂时无法上报告警。"
            class="ins-alert"
          />

          <el-form label-width="120px" class="upstream-settings-form" v-loading="upstreamLoading">
            <el-form-item label="接收入口">
              <el-input :model-value="upstreamEndpoint" readonly>
                <template #append>
                  <el-button @click="copyUpstreamText(upstreamEndpoint)">复制</el-button>
                </template>
              </el-input>
            </el-form-item>
            <el-form-item label="接收令牌">
              <el-input :model-value="upstreamSettings.token" readonly placeholder="尚未生成">
                <template #append>
                  <el-button :disabled="!upstreamSettings.token" @click="copyUpstreamText(upstreamSettings.token)">复制</el-button>
                </template>
              </el-input>
            </el-form-item>
            <el-form-item label="本地外发通道">
              <el-tag type="success" effect="plain">{{ upstreamSettings.local_channel_count || 0 }} 个非上级平台通道</el-tag>
              <span class="upstream-muted">邮件 / Webhook / 短信</span>
            </el-form-item>
            <el-form-item label="累计接收">
              <el-tag type="info" effect="plain">{{ upstreamSettings.received_count || 0 }} 条</el-tag>
              <span v-if="upstreamSettings.last_source_node" class="upstream-muted">最近来源：{{ upstreamSettings.last_source_node }}</span>
            </el-form-item>
          </el-form>

          <el-divider content-position="left">最近接收的下级告警</el-divider>
          <el-table :data="upstreamReceived" size="small" border v-loading="upstreamLoading">
            <el-table-column label="接收时间" width="170">
              <template #default="{ row }">{{ formatDateTime(row.received_at) }}</template>
            </el-table-column>
            <el-table-column prop="source_node_name" label="来源节点" min-width="150" />
            <el-table-column prop="level" label="级别" width="90" />
            <el-table-column prop="alert_type" label="类型" width="110" />
            <el-table-column prop="title" label="告警标题" min-width="220" show-overflow-tooltip />
            <el-table-column label="外发" width="80">
              <template #default="{ row }">{{ row.forwarded_count }}</template>
            </el-table-column>
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <el-tag size="small" :type="row.status === 'forwarded' ? 'success' : row.status === 'failed' ? 'danger' : 'info'">
                  {{ row.status === 'forwarded' ? '已外发' : row.status === 'failed' ? '外发失败' : row.status }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!upstreamLoading && !upstreamReceived.length" description="还没有收到下级节点告警" :image-size="60" />
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 新增/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="editing ? t('notify.editNotificationChannel') : t('notify.addNotificationChannel')" width="min(840px, 96vw)" class="notification-channel-dialog">
      <el-form :model="form" label-position="top" class="notification-channel-form">
        <div class="channel-section-title"><b>基本信息</b><span>通道名称、接收级别和通道类型</span></div>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="t('notify.channelName')" required>
              <el-input v-model="form.name" :placeholder="t('notify.channelNamePlaceholder')" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('notify.minLevel')">
              <el-select v-model="form.min_level" style="width: 100%">
                <el-option label="提示及以上" value="info" />
                <el-option :label="t('notify.warningAndAbove')" value="warning" />
                <el-option :label="t('notify.criticalOnly')" value="critical" />
                <el-option label="仅紧急" value="emergency" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item :label="t('notify.channelType')" required>
          <el-radio-group v-model="form.channel_type" :disabled="!!editing" class="channel-type-group">
            <el-radio-button label="email">{{ t('notify.emailSmtp') }}</el-radio-button>
            <el-radio-button label="webhook">Webhook</el-radio-button>
            <el-radio-button label="upstream">上级平台</el-radio-button>
            <el-radio-button label="sms">{{ t('notify.sms') }}</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <!-- 邮件 -->
        <template v-if="form.channel_type === 'email'">
          <div class="channel-section-title"><b>邮件服务器</b><span>SMTP 服务器与发件人信息</span></div>
          <el-row :gutter="16">
            <el-col :span="14">
              <el-form-item :label="t('notify.smtpServer')" required>
                <el-input v-model="email.smtp_host" placeholder="smtp.example.com" />
              </el-form-item>
            </el-col>
            <el-col :span="10">
              <el-form-item :label="t('notify.port')">
                <el-input-number v-model="email.smtp_port" :min="1" :max="65535" style="width: 100%" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item :label="t('notify.encryption')">
                <el-select v-model="email.encryption" style="width: 100%">
                  <el-option label="STARTTLS (587)" value="tls" />
                  <el-option label="SSL/TLS (465)" value="ssl" />
                  <el-option :label="t('notify.noEncryption')" value="none" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="t('notify.fromName')">
                <el-input v-model="email.from_name" :placeholder="t('notify.defaultFromName')" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item :label="t('notify.loginAccount')">
                <el-input v-model="email.smtp_user" placeholder="alert@example.com" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="t('notify.loginPassword')">
                <el-input
                  v-model="email.smtp_password"
                  type="password"
                  show-password
                  :placeholder="email.passwordSet ? t('notify.configuredKeepHint') : t('notify.smtpPasswordPlaceholder')"
                />
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item :label="t('notify.fromAddress')" required>
            <el-input v-model="email.mail_from" placeholder="alert@example.com" />
          </el-form-item>
          <el-form-item :label="t('notify.recipients')" required>
            <el-input v-model="email.mail_to" :placeholder="t('notify.emailsPlaceholder')" />
          </el-form-item>
        </template>

        <!-- Webhook -->
        <template v-else-if="form.channel_type === 'webhook'">
          <div class="channel-section-title"><b>Webhook 通知</b><span>地址、消息模板和请求头</span></div>
          <el-form-item :label="t('notify.webhookUrl')" required>
            <el-input v-model="webhook.url" placeholder="https://oapi.dingtalk.com/robot/send?access_token=..." />
          </el-form-item>
          <el-form-item :label="t('notify.messageTemplate')">
            <el-select v-model="webhook.template" style="width: 100%">
              <el-option :label="t('notify.genericJson')" value="generic" />
              <el-option :label="t('notify.dingtalkBot')" value="dingtalk" />
              <el-option :label="t('notify.wecomBot')" value="wecom" />
              <el-option :label="t('notify.feishuBot')" value="feishu" />
              <el-option label="Slack" value="slack" />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('notify.customRequestHeaders')">
            <el-input
              v-model="webhook.headersText"
              type="textarea"
              :rows="2"
              :placeholder="t('notify.headersPlaceholderAlt')"
            />
          </el-form-item>
          <el-form-item :label="t('notify.timeoutSeconds')">
            <el-input-number v-model="webhook.timeout" :min="1" :max="60" style="width: 100%" />
          </el-form-item>
        </template>

        <!-- 上级平台 -->
        <template v-else-if="form.channel_type === 'upstream'">
          <div class="channel-section-title"><b>上级平台</b><span>下级节点向总部上报告警</span></div>
          <el-alert
            type="info"
            :closable="false"
            show-icon
            title="仅对接本套系统。下级节点把告警上报到上级节点，由上级节点使用自己的邮件、Webhook 或短信通道统一外发。"
            class="upstream-channel-alert"
          />
          <el-form-item label="上级接收地址" required>
            <el-input v-model="upstream.url" placeholder="https://上级平台地址/api/notifications/upstream/ingest" />
          </el-form-item>
          <el-form-item label="接收令牌" required>
            <el-input
              v-model="upstream.token"
              type="password"
              show-password
              :placeholder="upstream.tokenSet ? '已配置，留空保持不变' : '粘贴上级平台生成的接收令牌'"
            />
          </el-form-item>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="来源节点名称" required>
                <el-input v-model="upstream.source_node_name" placeholder="例如：北京节点" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="来源节点标识">
                <el-input v-model="upstream.source_node_id" placeholder="留空使用本机实例 ID" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="来源地址">
            <el-input v-model="upstream.source_url" placeholder="当前系统访问地址，例如 https://beijing.example.com" />
          </el-form-item>
          <el-form-item label="超时秒数">
            <el-input-number v-model="upstream.timeout" :min="1" :max="60" style="width: 100%" />
          </el-form-item>
        </template>

        <!-- 短信 -->
        <template v-else>
          <div class="channel-section-title"><b>短信通知</b><span>联系人、网关和短信正文模板</span></div>
          <el-form-item :label="t('notify.smsContacts')" required>
            <div class="sms-contacts">
              <div class="sms-contacts-toolbar">
                <span class="sms-contacts-label">{{ t('notify.smsContactList') }}</span>
                <el-button size="small" plain type="primary" class="sms-contact-add" @click="addSmsContact">
                  {{ t('notify.addContact') }}
                </el-button>
              </div>
              <div class="sms-contacts-hint">{{ t('notify.smsContactHint') }}</div>
              <div class="sms-contact-head">
                <span>{{ t('notify.linkUser') }}</span>
                <span>{{ t('notify.contactName') }}</span>
                <span>{{ t('notify.contactPhone') }}</span>
                <span></span>
              </div>
              <div v-for="(contact, index) in sms.contacts" :key="index" class="sms-contact-row">
                <el-select
                  v-model="contact.user_id"
                  clearable
                  filterable
                  :placeholder="t('notify.linkUser')"
                  class="sms-contact-user"
                  @change="applySmsUser(contact)"
                >
                  <el-option
                    v-for="user in phoneUsers"
                    :key="user.id"
                    :label="userOptionLabel(user)"
                    :value="user.id"
                  />
                </el-select>
                <el-input v-model="contact.name" :placeholder="t('notify.contactName')" class="sms-contact-name" />
                <el-input v-model="contact.phone" :placeholder="t('notify.contactPhone')" class="sms-contact-phone" />
                <el-button link type="danger" class="sms-contact-remove" @click="removeSmsContact(index)">{{ t('common.delete') }}</el-button>
              </div>
              <div v-if="!sms.contacts.length" class="sms-contact-empty">{{ t('notify.smsNoContacts') }}</div>
            </div>
          </el-form-item>
          <el-form-item :label="t('notify.gatewayMethod')" required>
            <el-select v-model="sms.provider" style="width: 100%">
              <el-option label="MFM-920E 智能告警模块" value="mfm920e" />
              <el-option :label="t('notify.httpSmsGateway')" value="http" />
              <el-option :label="t('notify.smppGateway')" value="smpp" />
              <el-option :label="t('notify.serialGsmModule')" value="serial" />
            </el-select>
          </el-form-item>

          <el-form-item label="短信正文模板">
            <el-input
              v-model="sms.message_template"
              type="textarea"
              :rows="2"
              maxlength="500"
              placeholder="【{level_label}】{device_name} {message}"
            />
            <div class="form-help">
              已预置模板；可用变量：{level_label}、{device_name}、{ip_address}、{message}、{value}、{threshold}、{time}。留空则使用系统默认精简文案。
            </div>
          </el-form-item>

          <div class="sms-gateway-guide">
            <div class="sms-gateway-guide-head">
              <b>支持的短信网关 / 设备</b>
              <span>选择后按下方字段配置；详细说明见 SMS-GATEWAY.md</span>
            </div>
            <div class="sms-gateway-tags">
              <el-tag size="small" effect="plain" type="success">MFM-920E</el-tag>
              <el-tag size="small" effect="plain">通用 HTTP 网关</el-tag>
              <el-tag size="small" effect="plain">SMPP 3.4 短信中心</el-tag>
              <el-tag size="small" effect="plain">串口 GSM / AT 短信猫</el-tag>
            </div>
            <div v-if="sms.provider === 'mfm920e'" class="sms-gateway-current">
              推荐：MFM-920E 原生 HTTP，`POST /cgi-bin/NoticePush`，`To` 为手机号数组，成功响应必须为 `Reply=OK`。
            </div>
            <div v-else-if="sms.provider === 'http'" class="sms-gateway-current">
              通用 HTTP：适用于第三方短信平台/其他厂商网关，可自定义 JSON、表单或 Query 参数与成功判定。
            </div>
            <div v-else-if="sms.provider === 'smpp'" class="sms-gateway-current">
              SMPP 3.4：适用于运营商短信中心/短信平台，需要 SMSC 地址、端口、system_id 和密码。
            </div>
            <div v-else class="sms-gateway-current">
              串口 GSM：适用于标准 AT 指令短信猫；MFM-920E 的串口 JSON 协议请优先使用 HTTP 方式。
            </div>
          </div>

          <!-- MFM-920E 原生 HTTP 接口 -->
          <template v-if="sms.provider === 'mfm920e'">
            <el-form-item label="网关地址" required>
              <el-input v-model="sms.url" placeholder="http://192.168.0.100 或 http://192.168.0.100/cgi-bin/NoticePush" />
              <span class="form-help">只填设备 IP 时自动补全 /cgi-bin/NoticePush</span>
            </el-form-item>
            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="通知类型">
                  <el-select v-model="sms.message_type" style="width: 100%">
                    <el-option label="短信 SMS" value="SMS" />
                    <el-option label="电话语音 Call" value="Call" />
                    <el-option label="短信 + 电话 All" value="All" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="超时（秒）">
                  <el-input-number v-model="sms.timeout" :min="1" :max="60" style="width: 100%" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-alert
              type="info"
              :closable="false"
              show-icon
              title="平台发送 JSON：To 为手机号数组、Type 为 SMS/Call/All、Encoding=UTF-8、Text 为告警正文；只有设备返回 Reply=OK 才算成功。"
            />
          </template>

          <!-- HTTP 网关 -->
          <template v-else-if="sms.provider === 'http'">
            <el-form-item :label="t('notify.gatewayUrl')" required>
              <el-input v-model="sms.url" placeholder="http://192.168.1.50:8080/api/sms/send" />
            </el-form-item>
            <el-row :gutter="16">
              <el-col :span="8">
                <el-form-item :label="t('notify.method')" label-position="top">
                  <el-select v-model="sms.method" style="width: 100%">
                    <el-option label="POST" value="POST" />
                    <el-option label="GET" value="GET" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item :label="t('notify.messageFormat')" label-position="top">
                  <el-select v-model="sms.content_type" style="width: 100%">
                    <el-option label="JSON" value="json" />
                    <el-option :label="t('notify.form')" value="form" />
                    <el-option :label="t('notify.urlParams')" value="query" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item :label="t('notify.timeoutSeconds')" label-position="top">
                  <el-input-number v-model="sms.timeout" :min="1" :max="60" style="width: 100%" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item :label="t('notify.paramTemplate')">
              <el-input
                v-model="sms.paramsText"
                type="textarea"
                :rows="3"
                :placeholder="t('notify.jsonTemplatePlaceholder')"
              />
            </el-form-item>
            <el-form-item :label="t('notify.requestHeaders')">
              <el-input
                v-model="sms.headersText"
                type="textarea"
                :rows="2"
                :placeholder="t('notify.headersPlaceholder')"
              />
            </el-form-item>
            <el-row :gutter="16">
              <el-col :span="8">
                <el-form-item :label="t('notify.successCheck')" label-position="top">
                  <el-select v-model="sms.success_mode" style="width: 100%">
                    <el-option :label="t('notify.httpStatusCode')" value="status" />
                    <el-option :label="t('notify.responseKeyword')" value="keyword" />
                    <el-option :label="t('notify.jsonFields')" value="json" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item :label="t('notify.checkValue')" label-position="top">
                  <el-input
                    v-model="sms.success_value"
                    :placeholder="sms.success_mode === 'json' ? t('notify.successCodePlaceholder') : t('notify.successValuePlaceholder')"
                  />
                </el-form-item>
              </el-col>
              <el-col v-if="sms.success_mode === 'json'" :span="8">
                <el-form-item :label="t('notify.fieldName')" label-position="top">
                  <el-input v-model="sms.success_json_path" :placeholder="t('notify.jsonPathPlaceholder')" />
                </el-form-item>
              </el-col>
            </el-row>
          </template>

          <!-- SMPP -->
          <template v-else-if="sms.provider === 'smpp'">
            <el-row :gutter="16">
              <el-col :span="14">
                <el-form-item :label="t('notify.smscAddress')" required>
                  <el-input v-model="sms.host" placeholder="10.0.0.10" />
                </el-form-item>
              </el-col>
              <el-col :span="10">
                <el-form-item :label="t('notify.port')">
                  <el-input-number v-model="sms.port" :min="1" :max="65535" style="width: 100%" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="system_id" required>
                  <el-input v-model="sms.system_id" :placeholder="t('notify.account')" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="password" required>
                  <el-input
                    v-model="sms.password"
                    type="password"
                    show-password
                    :placeholder="sms.passwordSet ? t('notify.configuredKeepHint') : t('notify.password')"
                  />
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item :label="t('notify.callerNumber')">
                  <el-input v-model="sms.source_addr" :placeholder="t('notify.phonePlaceholder')" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="system_type">
                  <el-input v-model="sms.system_type" :placeholder="t('notify.usuallyBlank')" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="16">
              <el-col :span="8">
                <el-form-item label="source TON">
                  <el-input-number v-model="sms.source_ton" :min="0" :max="255" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="dest TON">
                  <el-input-number v-model="sms.dest_ton" :min="0" :max="255" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item :label="t('notify.longSms')">
                  <el-switch v-model="sms.use_message_payload" />
                </el-form-item>
              </el-col>
            </el-row>
          </template>

          <!-- 串口模块 -->
          <template v-else-if="sms.provider === 'serial'">
            <el-row :gutter="16">
              <el-col :span="14">
                <el-form-item :label="t('notify.serialDevice')" required>
                  <el-input v-model="sms.serial_port" :placeholder="t('notify.serialPortPlaceholder')" />
                </el-form-item>
              </el-col>
              <el-col :span="10">
                <el-form-item :label="t('notify.baudRate')">
                  <el-select v-model="sms.baudrate" style="width: 100%">
                    <el-option label="9600" :value="9600" />
                    <el-option label="19200" :value="19200" />
                    <el-option label="38400" :value="38400" />
                    <el-option label="115200" :value="115200" />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>
            <el-alert
              type="info"
              :closable="false"
              show-icon
              :title="t('notify.serialTooltip')"
            />
          </template>
        </template>

        <div class="channel-enabled-row">
          <div><b>{{ t('notify.enable') }}</b><span>保存后立即按最低级别参与告警通知</span></div>
          <el-switch v-model="form.enabled" />
        </div>
      </el-form>

      <template #footer>
        <el-button @click="testCurrent" :loading="testingInline">{{ t('notify.sendTest') }}</el-button>
        <el-button @click="dialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" @click="saveChannel" :loading="saving">{{ t('common.save') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { t } from '@/i18n'
import { computed, ref, reactive, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { notificationApi, userApi } from '@/api'
import { formatDateTime } from '@/utils/time'
import { useResponsiveViewport } from '@/composables/useResponsiveViewport'

const { isCompact } = useResponsiveViewport()

const activeTab = ref('channels')
const loading = ref(false)
const loadingLogs = ref(false)
const channels = ref([])
const logs = ref([])
const logPage = ref(1)
const logSize = ref(20)
const logTotal = ref(0)
const dialogVisible = ref(false)
const editing = ref(null)
const saving = ref(false)
const testingInline = ref(false)
const dispatching = ref(false)
const upstreamSettings = ref({ token: '', configured: false, local_channel_count: 0, received_count: 0, last_source_node: '', endpoint: '/api/notifications/upstream/ingest' })
const upstreamReceived = ref([])
const upstreamLoading = ref(false)
const upstreamGenerating = ref(false)
const upstreamEndpoint = computed(() => `${window.location.origin}${upstreamSettings.value.endpoint || '/api/notifications/upstream/ingest'}`)

const form = reactive({
  name: '',
  channel_type: 'email',
  min_level: 'warning',
  enabled: true,
})

const email = reactive({
  smtp_host: '',
  smtp_port: 587,
  encryption: 'tls',
  smtp_user: '',
  smtp_password: '',
  mail_from: '',
  from_name: t('notify.defaultFromName'),
  mail_to: '',
  passwordSet: false,
})

const webhook = reactive({
  url: '',
  template: 'generic',
  headersText: '',
  timeout: 10,
})

const upstream = reactive({
  url: '',
  token: '',
  tokenSet: false,
  source_node_name: '',
  source_node_id: '',
  source_url: '',
  timeout: 10,
})

const sms = reactive({
  provider: 'mfm920e',
  phones: '',
  contacts: [{ name: '', phone: '', user_id: null }],
  message_template: '【{level_label}】{device_name} {message}',
  // MFM-920E
  message_type: 'SMS',
  // HTTP 网关
  url: '',
  method: 'POST',
  content_type: 'json',
  paramsText: '{"phones":"{phones}","content":"{text}"}',
  headersText: '',
  success_mode: 'status',
  success_value: '200',
  success_json_path: 'code',
  timeout: 10,
  // SMPP
  host: '',
  port: 2775,
  system_id: '',
  password: '',
  passwordSet: false,
  system_type: '',
  source_addr: '',
  source_ton: 5,
  source_npi: 0,
  dest_ton: 1,
  dest_npi: 1,
  use_message_payload: true,
  // 串口
  serial_port: '',
  baudrate: 115200,
})

const phoneUsers = ref([])

function userOptionLabel(user) {
  const name = user.real_name || user.username || ''
  return user.phone ? `${name}（${user.phone}）` : name
}

function addSmsContact() {
  sms.contacts.push({ name: '', phone: '', user_id: null })
}

function removeSmsContact(index) {
  sms.contacts.splice(index, 1)
}

function applySmsUser(contact) {
  if (!contact.user_id) return
  const user = phoneUsers.value.find((item) => item.id === contact.user_id)
  if (!user) return
  contact.name = user.real_name || user.username || contact.name
  if (user.phone) contact.phone = user.phone
}

async function loadPhoneUsers() {
  try {
    const res = await userApi.list({ page: 1, size: 500 })
    phoneUsers.value = (res.data?.items || []).filter((user) => user.phone && user.is_active !== false)
  } catch {
    phoneUsers.value = []
  }
}

const TYPE_NAMES = { get email() { return t('notify.email') }, webhook: 'Webhook', sms: '短信', upstream: '上级平台' }
const TYPE_TAGS = { email: '', webhook: 'success', sms: 'warning', upstream: 'danger' }

function typeName(type) {
  return TYPE_NAMES[type] || type
}

function typeTag(type) {
  return TYPE_TAGS[type] ?? 'info'
}

function minLevelText(level) {
  return { info: '提示及以上', warning: t('notify.warningAndAbove'), critical: t('notify.criticalOnly'), emergency: '仅紧急' }[level] || level
}

function describeTarget(row) {
  const cfg = row.config || {}
  if (row.channel_type === 'upstream') {
    Object.assign(upstream, {
      url: cfg.url || '',
      token: '',
      tokenSet: !!cfg.token,
      source_node_name: cfg.source_node_name || '',
      source_node_id: cfg.source_node_id || '',
      source_url: cfg.source_url || '',
      timeout: cfg.timeout || 10,
    })
  } else if (row.channel_type === 'email') {
    return `${cfg.smtp_host || '-'}:${cfg.smtp_port || '-'} → ${cfg.mail_to || '-'}`
  }
  if (row.channel_type === 'upstream') {
    return `${cfg.source_node_name || '未命名节点'} → ${cfg.url || '-'}`
  }
  if (row.channel_type === 'sms') {
    const contacts = Array.isArray(cfg.contacts) ? cfg.contacts : []
    const phones = contacts.length
      ? contacts.map((item) => item.name ? `${item.name}(${item.phone})` : item.phone).join(',')
      : (Array.isArray(cfg.phones) ? cfg.phones.join(',') : cfg.phones || '-')
    const provider = { mfm920e: 'MFM-920E HTTP', http: t('notify.httpGateway'), smpp: 'SMPP', serial: t('notify.serialModule') }[cfg.provider] || cfg.provider
    const target = cfg.provider === 'smpp'
      ? `${cfg.host || '-'}:${cfg.port || '-'}`
      : cfg.provider === 'serial'
        ? cfg.port || '-'
        : cfg.url || '-'
    return `${provider} ${target} → ${phones}`
  }
  return cfg.url || '-'
}

async function loadChannels() {
  loading.value = true
  try {
    const res = await notificationApi.getChannels()
    channels.value = res.data.map((c) => ({ ...c, _testing: false }))
  } catch (e) {
    ElMessage.error(e.message || t('notify.loadChannelsFailed'))
  } finally {
    loading.value = false
  }
}

async function loadLogs() {
  loadingLogs.value = true
  try {
    const res = await notificationApi.getLogs({ page: logPage.value, size: logSize.value })
    logs.value = res.data.items
    logTotal.value = res.data.total
  } catch (e) {
    ElMessage.error(e.message || t('notify.loadLogsFailed'))
  } finally {
    loadingLogs.value = false
  }
}

function resetForms() {
  Object.assign(email, {
    smtp_host: '',
    smtp_port: 587,
    encryption: 'tls',
    smtp_user: '',
    smtp_password: '',
    mail_from: '',
    from_name: t('notify.defaultFromName'),
    mail_to: '',
    passwordSet: false,
  })
  Object.assign(webhook, { url: '', template: 'generic', headersText: '', timeout: 10 })
  Object.assign(upstream, {
    url: '',
    token: '',
    tokenSet: false,
    source_node_name: '',
    source_node_id: '',
    source_url: '',
    timeout: 10,
  })
  Object.assign(sms, {
    provider: 'mfm920e',
    phones: '',
    contacts: [{ name: '', phone: '', user_id: null }],
    message_template: '【{level_label}】{device_name} {message}',
    url: '',
    method: 'POST',
    content_type: 'json',
    paramsText: '{"phones":"{phones}","content":"{text}"}',
    headersText: '',
    success_mode: 'status',
    success_value: '200',
    success_json_path: 'code',
    timeout: 10,
    host: '',
    port: 2775,
    system_id: '',
    password: '',
    passwordSet: false,
    system_type: '',
    source_addr: '',
    source_ton: 5,
    source_npi: 0,
    dest_ton: 1,
    dest_npi: 1,
    use_message_payload: true,
    serial_port: '',
    baudrate: 115200,
  })
  Object.assign(form, { name: '', channel_type: 'email', min_level: 'warning', enabled: true })
}

function openCreate() {
  editing.value = null
  resetForms()
  dialogVisible.value = true
}

function openEdit(row) {
  editing.value = row
  resetForms()
  const cfg = row.config || {}
  Object.assign(form, {
    name: row.name,
    channel_type: row.channel_type,
    min_level: row.min_level,
    enabled: row.enabled,
  })
  if (row.channel_type === 'email') {
    Object.assign(email, {
      smtp_host: cfg.smtp_host || '',
      smtp_port: cfg.smtp_port || 587,
      encryption: cfg.use_ssl ? 'ssl' : cfg.use_tls ? 'tls' : 'none',
      smtp_user: cfg.smtp_user || '',
      smtp_password: '',
      mail_from: cfg.mail_from || '',
      from_name: cfg.from_name || t('notify.defaultFromName'),
      mail_to: Array.isArray(cfg.mail_to) ? cfg.mail_to.join(', ') : cfg.mail_to || '',
      passwordSet: !!cfg.smtp_password,
    })
  } else if (row.channel_type === 'webhook') {
    Object.assign(webhook, {
      url: cfg.url || '',
      template: cfg.template || 'generic',
      headersText: cfg.headers && Object.keys(cfg.headers).length
        ? JSON.stringify(cfg.headers, null, 2)
        : '',
      timeout: cfg.timeout || 10,
    })
  } else {
    Object.assign(sms, {
      provider: cfg.provider || 'http',
      phones: Array.isArray(cfg.phones) ? cfg.phones.join(', ') : cfg.phones || '',
      contacts: Array.isArray(cfg.contacts) && cfg.contacts.length
        ? cfg.contacts.map((item) => ({
            name: item.name || '',
            phone: item.phone || '',
            user_id: item.user_id || null,
          }))
        : (Array.isArray(cfg.phones) ? cfg.phones : String(cfg.phones || '').split(/[,;\s]+/))
            .map((phone) => ({ name: '', phone: String(phone).trim(), user_id: null }))
            .filter((item) => item.phone),
      url: cfg.url || '',
      message_type: cfg.message_type || 'SMS',
      method: cfg.method || 'POST',
      content_type: cfg.content_type || 'json',
      paramsText: cfg.params ? JSON.stringify(cfg.params, null, 2) : '',
      headersText: cfg.headers && Object.keys(cfg.headers).length
        ? JSON.stringify(cfg.headers, null, 2)
        : '',
      success_mode: cfg.success_mode || 'status',
      success_value: String(
        cfg.success_mode === 'keyword'
          ? cfg.success_keyword || 'ok'
          : cfg.success_mode === 'json'
            ? cfg.success_json_value ?? '0'
            : cfg.success_status ?? 200
      ),
      success_json_path: cfg.success_json_path || 'code',
      timeout: cfg.timeout || 10,
      host: cfg.host || '',
      port: cfg.port || 2775,
      system_id: cfg.system_id || '',
      password: '',
      passwordSet: !!cfg.password,
      system_type: cfg.system_type || '',
      source_addr: cfg.source_addr || '',
      source_ton: cfg.source_ton ?? 5,
      source_npi: cfg.source_npi ?? 0,
      dest_ton: cfg.dest_ton ?? 1,
      dest_npi: cfg.dest_npi ?? 1,
      use_message_payload: cfg.use_message_payload !== false,
      serial_port: cfg.port && cfg.provider === 'serial' ? cfg.port : '',
      baudrate: cfg.baudrate || 115200,
    })
    if (cfg.provider === 'serial') {
      sms.serial_port = cfg.port || ''
    }
  }
  dialogVisible.value = true
}

function buildConfig() {
  if (form.channel_type === 'upstream') {
    const url = upstream.url.trim()
    if (!url) throw new Error('请填写上级平台接收地址')
    if (!/^https?:\/\//i.test(url)) throw new Error('上级平台地址必须以 http:// 或 https:// 开头')
    if (!upstream.token.trim() && !upstream.tokenSet) throw new Error('请填写上级平台接收令牌')
    if (!upstream.source_node_name.trim()) throw new Error('请填写来源节点名称')
    return {
      url,
      token: upstream.token.trim(),
      source_node_name: upstream.source_node_name.trim(),
      source_node_id: upstream.source_node_id.trim(),
      source_url: upstream.source_url.trim(),
      timeout: Number(upstream.timeout) || 10,
    }
  }
  if (form.channel_type === 'email') {
    const toList = String(email.mail_to || '')
      .split(/[,;]/)
      .map((s) => s.trim())
      .filter(Boolean)
    return {
      smtp_host: email.smtp_host.trim(),
      smtp_port: Number(email.smtp_port) || 25,
      use_tls: email.encryption === 'tls',
      use_ssl: email.encryption === 'ssl',
      smtp_user: email.smtp_user.trim() || null,
      smtp_password: email.smtp_password || null,
      mail_from: email.mail_from.trim() || email.smtp_user.trim(),
      from_name: email.from_name || t('notify.defaultFromName'),
      mail_to: toList,
    }
  }

  // ---------- 短信 ----------
  if (form.channel_type === 'sms') {
    const contacts = (sms.contacts || [])
      .map((item) => ({
        name: String(item.name || '').trim(),
        phone: String(item.phone || '').trim(),
        user_id: item.user_id || null,
      }))
      .filter((item) => item.phone)
    const phoneList = [...new Set(contacts.map((item) => item.phone))]
    if (phoneList.length === 0) throw new Error(t('notify.recipientPhonesRequired'))

    const base = {
      provider: sms.provider,
      phones: phoneList,
      contacts,
      message_template: String(sms.message_template || '').trim(),
    }

    if (sms.provider === 'mfm920e') {
      if (!sms.url.trim()) throw new Error('请填写 MFM-920E 网关地址')
      return {
        ...base,
        url: sms.url.trim(),
        message_type: sms.message_type || 'SMS',
        encoding: 'UTF-8',
        timeout: Number(sms.timeout) || 10,
      }
    }

    if (sms.provider === 'http') {
      if (!sms.url.trim()) throw new Error(t('notify.gatewayUrlRequired'))
      let params = null
      if (sms.paramsText.trim()) {
        try {
          params = JSON.parse(sms.paramsText)
        } catch {
          throw new Error(t('notify.paramTemplateInvalid'))
        }
      }
      let headers = {}
      if (sms.headersText.trim()) {
        try {
          headers = JSON.parse(sms.headersText)
        } catch {
          throw new Error(t('notify.headersInvalid'))
        }
      }
      const successMode = sms.success_mode
      const cfg = {
        ...base,
        url: sms.url.trim(),
        method: sms.method,
        content_type: sms.content_type,
        params,
        headers,
        success_mode: successMode,
        timeout: Number(sms.timeout) || 10,
      }
      if (successMode === 'status') cfg.success_status = Number(sms.success_value) || 200
      if (successMode === 'keyword') cfg.success_keyword = sms.success_value || 'ok'
      if (successMode === 'json') {
        cfg.success_json_path = sms.success_json_path || 'code'
        cfg.success_json_value = sms.success_value ?? '0'
      }
      return cfg
    }

    if (sms.provider === 'smpp') {
      if (!sms.host.trim()) throw new Error(t('notify.smscAddressRequired'))
      if (!sms.system_id.trim()) throw new Error(t('notify.systemIdRequired'))
      const cfg = {
        ...base,
        host: sms.host.trim(),
        port: Number(sms.port) || 2775,
        system_id: sms.system_id.trim(),
        system_type: sms.system_type || '',
        source_addr: sms.source_addr || '',
        source_ton: Number(sms.source_ton) || 0,
        source_npi: Number(sms.source_npi) || 0,
        dest_ton: Number(sms.dest_ton) || 0,
        dest_npi: Number(sms.dest_npi) || 0,
        use_message_payload: !!sms.use_message_payload,
        timeout: Number(sms.timeout) || 10,
      }
      if (sms.password) cfg.password = sms.password
      return cfg
    }

    // serial
    if (!sms.serial_port.trim()) throw new Error(t('notify.serialPortRequired'))
    return {
      ...base,
      port: sms.serial_port.trim(),
      baudrate: Number(sms.baudrate) || 115200,
      timeout: 5,
    }
  }

  // ---------- Webhook ----------
  let headers = {}
  if (webhook.headersText.trim()) {
    try {
      headers = JSON.parse(webhook.headersText)
    } catch {
      throw new Error(t('notify.customHeadersInvalid'))
    }
  }
  return {
    url: webhook.url.trim(),
    template: webhook.template,
    headers,
    timeout: Number(webhook.timeout) || 10,
  }
}

async function loadUpstream() {
  upstreamLoading.value = true
  try {
    const [settingsRes, receivedRes] = await Promise.all([
      notificationApi.upstreamSettings(),
      notificationApi.upstreamReceived(20),
    ])
    upstreamSettings.value = settingsRes.data || upstreamSettings.value
    upstreamReceived.value = receivedRes.data?.items || []
  } catch (e) {
    ElMessage.error(e.message || '加载上级平台接收配置失败')
  } finally {
    upstreamLoading.value = false
  }
}

async function generateUpstreamToken() {
  try {
    await ElMessageBox.confirm(
      upstreamSettings.value.configured
        ? '重置后，所有下级节点使用旧令牌的上级平台通道都会发送失败，需要同步更新令牌。继续？'
        : '生成后请把接收入口和令牌配置到下级节点的「上级平台」告警渠道。继续？',
      upstreamSettings.value.configured ? '重置接收令牌' : '生成接收令牌',
      { type: 'warning', confirmButtonText: '继续', cancelButtonText: '取消' },
    )
    upstreamGenerating.value = true
    const res = await notificationApi.createUpstreamToken()
    upstreamSettings.value = res.data || upstreamSettings.value
    await loadUpstream()
    ElMessage.success('上级平台接收令牌已生成')
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e?.message || '生成接收令牌失败')
  } finally {
    upstreamGenerating.value = false
  }
}

async function copyUpstreamText(text) {
  if (!text) return
  try {
    await navigator.clipboard.writeText(String(text))
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败，请手动选择文本复制')
  }
}

watch(activeTab, (tab) => {
  if (tab === 'upstream') loadUpstream()
  if (tab === 'logs') loadLogs()
})

async function saveChannel() {
  if (!form.name.trim()) {
    ElMessage.warning(t('notify.channelNameRequired'))
    return
  }
  let config
  try {
    config = buildConfig()
  } catch (e) {
    ElMessage.error(e.message)
    return
  }

  saving.value = true
  try {
    const payload = { ...form, config }
    if (editing.value) {
      await notificationApi.updateChannel(editing.value.id, payload)
      ElMessage.success(t('notify.saved'))
    } else {
      await notificationApi.createChannel(payload)
      ElMessage.success(t('notify.created'))
    }
    dialogVisible.value = false
    await loadChannels()
  } catch (e) {
    ElMessage.error(e.message || t('notify.saveFailed'))
  } finally {
    saving.value = false
  }
}

async function testCurrent() {
  let config
  try {
    config = buildConfig()
  } catch (e) {
    ElMessage.error(e.message)
    return
  }
  testingInline.value = true
  try {
    await notificationApi.testInline({ channel_type: form.channel_type, config })
    ElMessage.success(t('notify.testSentCheck'))
  } catch (e) {
    ElMessage.error(e.message || t('notify.testFailed'))
  } finally {
    testingInline.value = false
  }
}

async function testChannel(row) {
  row._testing = true
  try {
    await notificationApi.testChannel(row.id)
    ElMessage.success(t('notify.testSent'))
  } catch (e) {
    ElMessage.error(e.message || t('notify.testFailed'))
  } finally {
    row._testing = false
  }
}

async function toggleChannel(row, value) {
  try {
    await notificationApi.updateChannel(row.id, { enabled: value })
    row.enabled = value
    ElMessage.success(value ? t('notify.enabled') : t('notify.disabled'))
  } catch (e) {
    ElMessage.error(e.message || t('notify.operationFailed'))
  }
}

async function removeChannel(row) {
  try {
    await ElMessageBox.confirm(t('notify.confirmDeleteChannel', { name: row.name }), t('notify.confirmDelete'), { type: 'warning' })
    await notificationApi.deleteChannel(row.id)
    ElMessage.success(t('notify.deleted'))
    await loadChannels()
  } catch {
    /* 取消 */
  }
}

async function dispatchTest() {
  dispatching.value = true
  try {
    const res = await notificationApi.dispatchTest({})
    const count = res.data.count || 0
    if (count === 0) {
      ElMessage.warning(t('notify.noMatchingChannel'))
    } else {
      const ok = (res.data.results || []).filter((r) => r.status === 'success').length
      ElMessage.success(t('notify.dispatchResult', { count, ok }))
    }
    if (activeTab.value === 'logs') await loadLogs()
  } catch (e) {
    ElMessage.error(e.message || t('notify.dispatchFailed'))
  } finally {
    dispatching.value = false
  }
}

onMounted(async () => {
  await loadPhoneUsers()
  await loadChannels()
  await loadLogs()
})
</script>

<style scoped>
:global(.notification-channel-dialog .el-dialog__body) {
  max-height: 72vh;
  overflow-y: auto;
  padding-top: 4px;
}
.notification-channel-form :deep(.el-form-item) { margin-bottom: 16px; }
.notification-channel-form :deep(.el-form-item__label) {
  padding-bottom: 5px;
  color: #526b80;
  font-size: 12px;
  line-height: 1.3;
}
.notification-channel-form :deep(.el-input-number) { width: 100%; }
.channel-section-title {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin: 18px 0 12px;
  padding-bottom: 7px;
  border-bottom: 1px solid #e8eff6;
}
.channel-section-title:first-child { margin-top: 0; }
.channel-section-title b { color: #1f3b52; font-size: 13px; }
.channel-section-title span { color: #93a6b6; font-size: 11px; }
.channel-type-group { display: flex; flex-wrap: wrap; gap: 8px; }
.channel-type-group :deep(.el-radio-button) { margin: 0; }
.channel-enabled-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 20px;
  padding: 12px 14px;
  border: 1px solid #e4edf5;
  border-radius: 8px;
  background: #f8fbfe;
}
.channel-enabled-row > div { display: flex; flex-direction: column; gap: 3px; }
.channel-enabled-row b { color: #2b465c; font-size: 12px; }
.channel-enabled-row span { color: #91a4b3; font-size: 11px; }
.notify-page {
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

.sms-contacts {
  width: 100%;
  max-width: 100%;
  padding: 12px;
  border: 1px solid #e5edf5;
  border-radius: 8px;
  background: #fbfdff;
}

.sms-contacts-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 4px;
}

.sms-contacts-label {
  color: #334155;
  font-size: 13px;
  font-weight: 600;
}

.sms-contacts-hint {
  margin-bottom: 8px;
  color: #98a9b7;
  font-size: 11px;
  line-height: 1.5;
  white-space: nowrap;
}

.sms-contact-add {
  flex-shrink: 0;
}

.sms-contact-head,
.sms-contact-row {
  display: grid;
  grid-template-columns: minmax(190px, 1.35fr) minmax(110px, 0.75fr) minmax(150px, 0.9fr) 48px;
  gap: 10px;
  align-items: center;
}

.sms-contact-head {
  padding: 0 0 6px;
  color: #8ba0af;
  font-size: 11px;
}

.sms-contact-row {
  padding: 7px 0;
  border-top: 1px dashed #e8eef5;
}

.sms-contact-user,
.sms-contact-name,
.sms-contact-phone {
  width: 100%;
}

.sms-contact-remove {
  justify-self: center;
}

.sms-contact-empty {
  padding: 18px 0;
  color: #9aaebd;
  font-size: 12px;
  text-align: center;
}

@media (max-width: 720px) {
  .sms-contacts {
    padding: 10px;
  }

  .sms-contacts-toolbar {
    align-items: center;
    gap: 10px;
  }

  .sms-contacts-hint {
    white-space: normal;
  }

  .sms-contact-head {
    display: none;
  }

  .sms-contact-row {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 8px;
    padding: 10px 0;
  }

  .sms-contact-user {
    grid-column: 1 / -1;
  }

  .sms-contact-remove {
    justify-self: end;
  }
}

.pager {
  margin-top: 16px;
  justify-content: flex-end;
}

.notify-log-body {
  padding: 4px 12px;
  color: #475569;
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}


.upstream-channel-alert { margin-bottom: 16px; }
.upstream-receiver-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
  padding: 14px 16px;
  border: 1px solid #dbeafe;
  border-radius: 10px;
  background: #f8fbff;
}
.upstream-receiver-head strong { color: #1e3a5f; font-size: 14px; }
.upstream-receiver-head p { margin: 5px 0 0; color: #7b91a5; font-size: 11px; line-height: 1.7; }
.upstream-settings-form { max-width: 940px; }
.upstream-muted { margin-left: 10px; color: #94a3b8; font-size: 11px; }
@media (max-width: 760px) {
  .upstream-receiver-head { flex-direction: column; }
  .upstream-settings-form { max-width: 100%; }
}


.sms-gateway-guide { margin: 0 0 14px 0; padding: 10px 12px; border: 1px solid #e1edf6; border-radius: 7px; background: #f8fbfe; }
.sms-gateway-guide-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px; color: #334155; font-size: 12px; }
.sms-gateway-guide-head span { color: #8ba0af; font-size: 11px; }
.sms-gateway-tags { display: flex; flex-wrap: wrap; gap: 5px; margin: 7px 0 5px; }
.sms-gateway-current { color: #536b7c; font-size: 11px; line-height: 1.65; }
@media (max-width: 720px) { .sms-gateway-guide { margin-left: 0; } }
</style>
